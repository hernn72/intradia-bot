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
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional

from paper import ENGINE_VERSION
from paper.contract import contract_from_row
from paper.environment import Environment, cohort_state, environment_matches, latest_epoch, set_state
from paper.ingest import Ingestor, Provider
from paper.inputs import build_view, ts
from paper.persist import persist_advance, persist_progress, restore_engine
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
    """Cada pasada programada sin decisión confirmada desde la última que sí la tuvo → ``ENGINE_DOWNTIME``
    (una fila por pasada perdida). Devuelve la última pasada perdida (``late_before``) o ``None``."""

    last = store.one("SELECT pass_scheduled_ts FROM paper_run_decision ORDER BY run_seq DESC LIMIT 1")
    if last is None:
        return None
    previous = ts(last["pass_scheduled_ts"])
    decided = {r["pass_scheduled_ts"] for r in store.rows("SELECT pass_scheduled_ts FROM paper_run_decision")}
    missed = [p for p in scheduled_passes(previous + timedelta(seconds=1), pass_ts - timedelta(seconds=1))
              if p.isoformat() not in decided]
    for moment in missed:
        _downtime(store, "ALL", moment, "SIN_EJECUCION", now)
    # Todo evento anterior a la última pasada perdida que se procese a partir de ahora es procesamiento
    # tardío (§8.7), aunque la barra que lo bloqueaba llegue varias ejecuciones después de la recuperación.
    row = store.one(
        "SELECT MAX(from_scheduled_pass) AS m FROM paper_engine_downtime WHERE scope = 'ALL' AND from_scheduled_pass < ?",
        (pass_ts.isoformat(),),
    )
    return ts(row["m"]) if row is not None and row["m"] else None


def _downtime(store: PaperStore, scope: str, moment: datetime, subcause: str, now: datetime) -> None:
    store.insert_first("paper_engine_downtime", {
        "scope": scope, "from_scheduled_pass": moment.isoformat(), "to_scheduled_pass": moment.isoformat(),
        "cause": "ENGINE_DOWNTIME", "subcause": subcause, "detected_at": now.isoformat(),
    }, ("scope", "from_scheduled_pass"))


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


def view_builder(store: PaperStore, universe: PaperUniverse, contract: Any, cohort_id: str) -> Callable[[Any], Any]:
    """Vista de una ejecución registrada (``paper_run_decision``), la misma en la ejecución y en el replay."""

    def build(run: Any) -> Any:
        # Procesamiento tardío tras una caída general o de la propia cohorte (§8.7, §13): la última pasada
        # perdida anterior a esta, con lo registrado hasta su decisión.
        row = store.one(
            "SELECT MAX(from_scheduled_pass) AS m FROM paper_engine_downtime WHERE scope IN ('ALL', ?) "
            "AND from_scheduled_pass < ? AND detected_at <= ?",
            (cohort_id, run["pass_scheduled_ts"], run["decision_ts"]),
        )
        late = ts(row["m"]) if row is not None and row["m"] else None
        view, _infos = build_view(store, universe, contract, cohort_id, cutoff=ts(run["decision_ts"]),
                                  limit=ts(run["pass_scheduled_ts"]), late_before=late, scope=cohort_id)
        return view

    return build


def run_pass(store: PaperStore, universe: PaperUniverse, provider: Provider, *, pass_ts: datetime,
             clock: Callable[[], datetime], code_sha: str, environment: Environment,
             envs: Mapping[str, PolicyEnv], identity_ok: Callable[[str], bool], source_run_id: str = "",
             evaluator: Any = None, lock_wait_seconds: float = 1200.0) -> RunReport:
    pass_ts = pass_ts.astimezone(timezone.utc)
    with store.lock(lock_wait_seconds):
        done = store.one(
            "SELECT paper_run_id, run_seq, status, decision_ts FROM paper_run WHERE pass_scheduled_ts = ? AND status = 'OK' "
            "ORDER BY run_seq DESC LIMIT 1", (pass_ts.isoformat(),),
        )
        if done is not None:
            # Una pasada ya completada no se repite: se devuelve sin escribir nada (idempotencia operativa).
            return RunReport(done["paper_run_id"], int(done["run_seq"]), "ALREADY_DONE", pass_ts, ts(done["decision_ts"]))
        started = clock()
        paper_run_id = str(uuid.uuid4())
        with store.transaction():
            row = store.one("SELECT COALESCE(MAX(run_seq), 0) AS m FROM paper_run_start")
            run_seq = int(row["m"]) + 1 if row else 1
            store.insert("paper_run_start", {"paper_run_id": paper_run_id, "run_seq": run_seq,
                         "pass_scheduled_ts": pass_ts.isoformat(), "started_at": started.isoformat()}, ("paper_run_id",))
        report = RunReport(paper_run_id, run_seq, "OK", pass_ts)
        cohorts = store.rows("SELECT * FROM paper_cohort ORDER BY policy_id")
        if not cohorts:
            raise RuntimeError("paper.db sin cohortes (`python -m paper init`)")
        start = min(date.fromisoformat(c["start_date"]) for c in cohorts)

        with store.transaction():
            late_before = _record_downtime(store, pass_ts, started)
            ingest = Ingestor(store, universe, provider, now=started, paper_run_id=paper_run_id, start=start).run()
            if ingest.fetch_failure:
                # Caída del motor: no avanza ningún plazo, pero no impide confirmar evaluaciones con lo guardado.
                _downtime(store, "ALL", pass_ts, "FETCH_FAILURE", started)
            else:
                _data_alerts(store, universe, start=start, now=started)
        data_cutoff = clock()
        manifest: Dict[str, Any] = {"ingest": ingest.__dict__, "environment": {
            "python": environment.python_version, "packages_sha256": environment.packages_sha256,
            "requirements_sha256": environment.requirements_sha256}}

        # Compuertas antes de evaluar: estado, identidad del código y entorno de la época (§13, D-78).
        gates: Dict[str, str] = {}
        with store.transaction():
            for cohort in cohorts:
                cohort_id = cohort["cohort_id"]
                contract = contract_from_row(dict(cohort))
                state = cohort_state(store, cohort_id)
                if state not in RUNNABLE_STATES and state != "ENGINE_UNRUNNABLE":
                    gates[cohort_id] = state
                elif not identity_ok(contract.t025_code_sha):
                    gates[cohort_id] = "IDENTITY_MISMATCH"
                elif state != "ENGINE_UNRUNNABLE" and not environment_matches(store, cohort_id, environment):
                    set_state(store, cohort_id, "ENVIRONMENT_INVESTIGATION", at=data_cutoff,
                              reason="entorno distinto del de la época vigente (D-78)")
                    gates[cohort_id] = "ENVIRONMENT_INVESTIGATION"
                else:
                    gates[cohort_id] = state
                # Solo una cohorte que debía operar y no puede (identidad o entorno) está caída (D-78). CLOSING,
                # CLOSED y los estados terminales no son caídas, y su instante no se publica (§13).
                if gates[cohort_id] in ("IDENTITY_MISMATCH", "ENVIRONMENT_INVESTIGATION"):
                    _downtime(store, cohort_id, pass_ts, "COHORTE_NO_OPERATIVA", data_cutoff)

        evaluable_cohorts = {c["policy_id"]: c["cohort_id"] for c in cohorts
                             if c["kind"] == "POLICY" and gates[c["cohort_id"]] == "ACTIVE"}
        rows = evaluate_pass(store, universe, evaluable_cohorts, envs, pass_ts=pass_ts, now=data_cutoff, start=start,
                             paper_run_id=paper_run_id, source_run_id=source_run_id, evaluator=evaluator)
        with store.transaction():
            decision_ts = clock()
            report.evaluations = write_evaluations(store, rows, decision_ts)
            report.decision_ts = decision_ts
            store.insert("paper_run_decision", {
                "paper_run_id": paper_run_id, "run_seq": run_seq, "pass_scheduled_ts": pass_ts.isoformat(),
                "data_cutoff_ts": data_cutoff.isoformat(), "decision_ts": decision_ts.isoformat(),
                "late_before": late_before.isoformat() if late_before else "", "fetch_failure": int(ingest.fetch_failure),
            }, ("paper_run_id",))
        with store.transaction():
            report.open_checks = open_checks(store, universe, evaluable_cohorts, envs, code_sha, now=decision_ts,
                                             start=start, paper_run_id=paper_run_id)
            down_cohorts = {c["policy_id"]: c["cohort_id"] for c in cohorts if c["kind"] == "POLICY"
                            and gates[c["cohort_id"]] in ("ACTIVE", "IDENTITY_MISMATCH", "ENVIRONMENT_INVESTIGATION")}
            not_evaluated(store, universe, down_cohorts, now=decision_ts, start=start)

        if ingest.fetch_failure:
            report.status = "FETCH_FAILURE"
        for cohort in cohorts:
            cohort_id = cohort["cohort_id"]
            gate = gates[cohort_id]
            runnable = gate in RUNNABLE_STATES or gate == "ENGINE_UNRUNNABLE"
            if ingest.fetch_failure or not runnable:
                report.cohorts[cohort["policy_id"]] = "FETCH_FAILURE" if ingest.fetch_failure else gate
            else:
                report.cohorts[cohort["policy_id"]] = _advance_cohort(
                    store, universe, cohort, run_seq=run_seq, paper_run_id=paper_run_id, decision_ts=decision_ts,
                    report=report)
            if is_sealed(store, cohort_id):
                with store.transaction():
                    write_commitment(store, cohort_id, paper_run_id)
        manifest["cohorts"] = report.cohorts
        _finish(store, report, source_run_id=source_run_id, started=started, data_cutoff=data_cutoff,
                late_before=late_before, code_sha=code_sha, clock=clock, manifest=manifest)
        return report


def _advance_cohort(store: PaperStore, universe: PaperUniverse, cohort: Any, *, run_seq: int, paper_run_id: str,
                    decision_ts: datetime, report: RunReport) -> str:
    cohort_id = cohort["cohort_id"]
    contract = contract_from_row(dict(cohort))
    build = view_builder(store, universe, contract, cohort_id)
    try:
        engine = restore_engine(store, contract.engine_spec(), cohort_id, build)
        decision = store.one("SELECT * FROM paper_run_decision WHERE paper_run_id = ?", (paper_run_id,))
        result = engine.advance(build(decision))
        epoch = latest_epoch(store, cohort_id)
        epoch_no = int(epoch["epoch_no"]) if epoch else 0
        with store.transaction():
            persist_advance(store, cohort_id, run_seq, epoch_no, result, engine)
            persist_progress(store, cohort_id, run_seq, paper_run_id, result, engine)
            if cohort_state(store, cohort_id) == "CLOSING" and not engine.pending and all(
                    p.non_evaluable for p in engine.positions.values()):
                set_state(store, cohort_id, "CLOSED", at=decision_ts, reason="cierre ordinario completado")
        return "OK"
    except Exception as exc:
        report.status = "ERROR"
        with store.transaction():
            store.insert_first("paper_run_diagnostic", {
                "paper_run_id": paper_run_id, "cohort_id": cohort_id, "code": type(exc).__name__,
                "detail_json": canonical({"error": str(exc), "traceback": traceback.format_exc()}),
            }, ("paper_run_id", "cohort_id", "code"))
        return "ERROR"


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
