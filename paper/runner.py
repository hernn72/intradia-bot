"""Una ejecución de T-025 asociada a una pasada programada (ficha §7, §10, §12, §13; D-78).

Orden, siempre el mismo:

1. lock con espera acotada (un solo escritor);
2. caídas: las pasadas programadas sin ejecución desde la última se registran como ``ENGINE_DOWNTIME``;
3. **fase de datos** (una transacción): testigo, peticiones, observaciones y alertas a nivel de dato;
   con ``FETCH_FAILURE`` la pasada es una caída del motor y no hay más;
4. **transacción única de evaluaciones**, antes de tocar ningún libro: evaluaciones de B2, S2 y C0 con
   ``decision_ts`` = instante de su commit, comprobaciones de apertura por política y
   ``SIGNAL_NOT_EVALUATED`` con su causa;
5. **libros**, uno por cohorte y en su propia transacción: identidad (código y entorno de su época),
   avance de ``engine_v1`` hasta la frontera, filas de hechos, checkpoint y compromiso con nonce;
6. ``paper_run`` con su estado genérico.
"""

from __future__ import annotations

import traceback
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Mapping, Optional

from paper import ENGINE_VERSION
from paper.contract import contract_from_row
from paper.engine_v1 import Engine
from paper.environment import Environment, cohort_state, environment_matches, latest_epoch, set_state
from paper.ingest import Ingestor, Provider
from paper.inputs import build_view, ts
from paper.persist import load_engine, persist_advance, persist_progress
from paper.schema import SCHEMA_VERSION
from paper.signals import PolicyEnv, evaluate_pass, not_evaluated, open_checks, write_evaluations
from paper.store import PaperStore, canonical
from paper.universe import PaperUniverse, scheduled_passes
from paper.visibility import is_sealed, write_commitment

RUNNABLE_STATES = ("ACTIVE", "CLOSING")


@dataclass
class RunReport:
    paper_run_id: str
    run_seq: int
    status: str
    pass_ts: datetime
    decision_ts: Optional[datetime] = None
    evaluations: int = 0
    open_checks: int = 0
    cohorts: Dict[str, str] = field(default_factory=dict)
    missed_passes: List[str] = field(default_factory=list)


def _record_downtime(store: PaperStore, pass_ts: datetime, now: datetime) -> Optional[datetime]:
    """Pasadas programadas entre la última ejecución y esta sin ejecución completa → ``ENGINE_DOWNTIME``.
    Devuelve la última pasada perdida (``late_before``) o ``None``."""

    last = store.one("SELECT pass_scheduled_ts FROM paper_run WHERE status = 'OK' ORDER BY run_seq DESC LIMIT 1")
    if last is None:
        return None
    previous = ts(last["pass_scheduled_ts"])
    missed = list(scheduled_passes(previous + timedelta(seconds=1), pass_ts - timedelta(seconds=1)))
    if not missed:
        return None
    store.insert_first("paper_engine_downtime", {
        "scope": "ALL", "from_scheduled_pass": missed[0].isoformat(), "to_scheduled_pass": missed[-1].isoformat(),
        "cause": "ENGINE_DOWNTIME", "subcause": "SIN_EJECUCION", "detected_at": now.isoformat(),
    }, ("scope", "from_scheduled_pass"))
    return missed[-1]


def _data_alerts(store: PaperStore, universe: PaperUniverse, *, start: date, now: datetime) -> None:
    """Alertas a nivel de dato derivadas de los plazos, para **todo** el universo (no delatan libros, §10.3):
    sesión declarada ausente, barra tardía de una sesión ya declarada y 20 sesiones sin datos."""

    from paper.inputs import Downtime, series_info

    downtime = Downtime(store, now)
    for asset in universe.assets:
        info = series_info(store, asset, start, now, universe.settlement_minutes, downtime)
        assert info.missing is not None
        for day, declared_at in sorted(info.missing.declared.items()):
            _alert(store, asset.data_symbol, "ENTRY_BAR_DECLARED_MISSING", day, now)
            late = store.one(
                "SELECT 1 FROM paper_bar_observation WHERE data_symbol = ? AND session_date = ? AND observed_at >= ?",
                (asset.data_symbol, day.isoformat(), declared_at.isoformat()),
            )
            if late is not None:
                _alert(store, asset.data_symbol, "LATE_BAR", day, now)
        if info.missing.data_loss_since is not None:
            _alert(store, asset.data_symbol, "NO_DATA_20_SESSIONS", info.missing.data_loss_since, now)


def _alert(store: PaperStore, obj: str, kind: str, day: date, now: datetime) -> None:
    store.insert_first("paper_data_alert", {"object": obj, "kind": kind, "session_date": day.isoformat(),
                                            "detected_at": now.isoformat()}, ("object", "kind", "session_date"))


def _finish(store: PaperStore, report: RunReport, *, source_run_id: str, started: datetime, data_cutoff: datetime,
            late_before: Optional[datetime], code_sha: str, clock: Callable[[], datetime], manifest: Mapping[str, Any]) -> None:
    with store.transaction():
        store.insert("paper_run", {
            "paper_run_id": report.paper_run_id, "run_seq": report.run_seq, "source_run_id": source_run_id,
            "pass_scheduled_ts": report.pass_ts.isoformat(), "started_at": started.isoformat(),
            "data_cutoff_ts": data_cutoff.isoformat(),
            "decision_ts": (report.decision_ts or data_cutoff).isoformat(), "finished_at": clock().isoformat(),
            "late_before": late_before.isoformat() if late_before else "", "status": report.status,
            "engine_version": ENGINE_VERSION, "schema_version": SCHEMA_VERSION, "code_sha": code_sha,
            "manifest_json": canonical(manifest),
        }, ("paper_run_id",))


def run_pass(store: PaperStore, universe: PaperUniverse, provider: Provider, *, pass_ts: datetime,
             clock: Callable[[], datetime], code_sha: str, environment: Environment,
             envs: Mapping[str, PolicyEnv], identity_ok: Callable[[str], bool], source_run_id: str = "",
             evaluator: Any = None, lock_wait_seconds: float = 1200.0) -> RunReport:
    with store.lock(lock_wait_seconds):
        started = clock()
        paper_run_id = str(uuid.uuid4())
        run_seq = store.next_run_seq()
        report = RunReport(paper_run_id, run_seq, "OK", pass_ts)
        cohorts = store.rows("SELECT * FROM paper_cohort ORDER BY policy_id")
        if not cohorts:
            raise RuntimeError("paper.db sin cohortes (`python -m paper init`)")
        start = min(date.fromisoformat(c["start_date"]) for c in cohorts)

        with store.transaction():
            late_before = _record_downtime(store, pass_ts, started)
            ingest = Ingestor(store, universe, provider, now=started, paper_run_id=paper_run_id, start=start).run()
            if ingest.fetch_failure:
                store.insert_first("paper_engine_downtime", {
                    "scope": "ALL", "from_scheduled_pass": pass_ts.isoformat(), "to_scheduled_pass": pass_ts.isoformat(),
                    "cause": "ENGINE_DOWNTIME", "subcause": "FETCH_FAILURE", "detected_at": started.isoformat(),
                }, ("scope", "from_scheduled_pass"))
            else:
                _data_alerts(store, universe, start=start, now=started)
        data_cutoff = clock()
        manifest = {"ingest": ingest.__dict__, "environment": {"python": environment.python_version,
                                                               "packages_sha256": environment.packages_sha256}}
        if ingest.fetch_failure:
            report.status = "FETCH_FAILURE"
            _finish(store, report, source_run_id=source_run_id, started=started, data_cutoff=data_cutoff,
                    late_before=late_before, code_sha=code_sha, clock=clock, manifest=manifest)
            return report

        policy_cohorts = {c["policy_id"]: c["cohort_id"] for c in cohorts if c["kind"] == "POLICY"}
        rows = evaluate_pass(store, universe, policy_cohorts, envs, pass_ts=pass_ts, now=data_cutoff, start=start,
                             paper_run_id=paper_run_id, source_run_id=source_run_id, evaluator=evaluator)
        with store.transaction():
            decision_ts = clock()
            report.evaluations = write_evaluations(store, rows, decision_ts)
            report.decision_ts = decision_ts
        with store.transaction():
            report.open_checks = open_checks(store, universe, policy_cohorts, envs, code_sha, now=decision_ts, start=start,
                                             paper_run_id=paper_run_id)
            not_evaluated(store, universe, policy_cohorts, now=decision_ts, start=start)

        for cohort in cohorts:
            cohort_id = cohort["cohort_id"]
            contract = contract_from_row(dict(cohort))
            state = cohort_state(store, cohort_id)
            if state not in RUNNABLE_STATES and state != "ENGINE_UNRUNNABLE":
                report.cohorts[cohort["policy_id"]] = state
                continue
            if not identity_ok(contract.t025_code_sha):
                report.cohorts[cohort["policy_id"]] = "IDENTITY_MISMATCH"
                continue
            if state != "ENGINE_UNRUNNABLE" and not environment_matches(store, cohort_id, environment):
                with store.transaction():
                    set_state(store, cohort_id, "ENVIRONMENT_INVESTIGATION", at=decision_ts,
                              reason="entorno distinto del de la época vigente (D-78)")
                report.cohorts[cohort["policy_id"]] = "ENVIRONMENT_INVESTIGATION"
                continue
            try:
                engine, _last = load_engine(store, cohort_id)
                engine = engine or Engine(contract.engine_spec())
                view, _infos = build_view(store, universe, contract, cohort_id, cutoff=decision_ts, limit=pass_ts,
                                          late_before=late_before)
                result = engine.advance(view)
                epoch = latest_epoch(store, cohort_id)
                epoch_no = int(epoch["epoch_no"]) if epoch else 0
                with store.transaction():
                    persist_advance(store, cohort_id, run_seq, epoch_no, result, engine)
                    persist_progress(store, cohort_id, run_seq, paper_run_id, result, engine)
                    if is_sealed(store, cohort_id):
                        write_commitment(store, cohort_id, paper_run_id)
                report.cohorts[cohort["policy_id"]] = "OK"
            except Exception as exc:
                report.status = "ERROR"
                report.cohorts[cohort["policy_id"]] = "ERROR"
                with store.transaction():
                    store.insert_first("paper_run_diagnostic", {
                        "paper_run_id": paper_run_id, "cohort_id": cohort_id, "code": type(exc).__name__,
                        "detail_json": canonical({"error": str(exc), "traceback": traceback.format_exc()}),
                    }, ("paper_run_id", "cohort_id", "code"))
        manifest["cohorts"] = report.cohorts
        _finish(store, report, source_run_id=source_run_id, started=started, data_cutoff=data_cutoff,
                late_before=late_before, code_sha=code_sha, clock=clock, manifest=manifest)
        return report


def init_cohorts(store: PaperStore, contracts: List[Any], environment: Environment, *, now: datetime,
                 embargo_ref: str = "D-73/D-75") -> List[str]:
    """Crea las cohortes, su época 1 y el embargo de T-024 sobre B2, S2 y C0 (D-75). Idempotente."""

    from paper.contract import EMBARGOED, cohort_row
    from paper.environment import record_epoch
    from paper.visibility import open_window, seal_windows

    ids = []
    with store.transaction():
        for contract in contracts:
            row = cohort_row(contract, now.isoformat())
            if store.insert("paper_cohort", row, ("cohort_id",), compare_exclude=("created_at",)):
                set_state(store, contract.cohort_id, "ACTIVE", at=now, reason="alta de cohorte")
                record_epoch(store, contract.cohort_id, environment, code_sha=contract.t025_code_sha, now=now,
                             first_scheduled_pass="")
            ids.append(contract.cohort_id)
        embargoed = [c.cohort_id for c in contracts if c.policy_id in EMBARGOED]
        if not any(w.kind == "EMBARGO_T024" for w in seal_windows(store)):
            start = min(date.fromisoformat(c.start_date) for c in contracts)
            open_window(store, window_id="EMBARGO_T024", kind="EMBARGO_T024", cohorts=embargoed, sessions_from=start,
                        sessions_to=None, decision_ref=embargo_ref, now=now)
    return ids
