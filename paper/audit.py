"""Reconstrucción y auditoría (ficha §12, §13; D-78).

:func:`replay` repite desde cero la secuencia registrada de ejecuciones de una cohorte, cada una con su corte
(``paper_run_decision``), y compara con lo escrito **todos** los hechos sellados que regenera: ledger, eventos
de posición, instantáneas de equity y desenlaces. :func:`replay_evaluations` recalcula las evaluaciones de
cada pasada con el código y el entorno actuales y las compara con las escritas. Juntas son la prueba de
reconstrucción y la base de la equivalencia de una época de entorno. En una cohorte sellada solo es visible
si coinciden o no.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from paper.contract import contract_from_row
from paper.engine_v1 import Engine
from paper.store import PaperStore, canonical


@dataclass
class ReplayReport:
    cohort_id: str
    runs: int = 0
    rows: int = 0
    match: bool = True
    first_divergence: Optional[Dict[str, Any]] = None
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {"cohort_id": self.cohort_id, "runs": self.runs, "rows": self.rows, "match": self.match,
                "first_divergence": self.first_divergence, "notes": self.notes}


def _stored(store: PaperStore, cohort_id: str) -> Dict[str, List[Any]]:
    return {
        "ledger": [r["row_json"] for r in store.rows("SELECT row_json FROM paper_ledger WHERE cohort_id = ? ORDER BY seq", (cohort_id,))],
        "events": [r["payload_json"] for r in store.rows(
            "SELECT payload_json FROM paper_position_event WHERE cohort_id = ? ORDER BY event_seq", (cohort_id,))],
        "snapshots": [canonical([r["snapshot_day"], r["equity_eur"], r["cash_eur"], r["long_value_eur"], r["stale_value_eur"],
                                 r["n_positions"], r["exposure_json"]])
                      for r in store.rows("SELECT * FROM paper_equity_snapshot WHERE cohort_id = ? ORDER BY snapshot_day", (cohort_id,))],
        "outcomes": [canonical([r["position_id"], r["trade_json"], r["mae_R"], r["mfe_R"]])
                     for r in store.rows("SELECT * FROM paper_trade_outcome WHERE cohort_id = ? ORDER BY position_id", (cohort_id,))],
    }


def replay(store: PaperStore, universe: Any, cohort_id: str) -> ReplayReport:
    from paper.runner import view_builder

    cohort = store.one("SELECT * FROM paper_cohort WHERE cohort_id = ?", (cohort_id,))
    if cohort is None:
        raise ValueError(f"cohorte {cohort_id} inexistente")
    contract = contract_from_row(dict(cohort))
    build = view_builder(store, universe, contract, cohort_id)
    engine = Engine(contract.engine_spec())
    report = ReplayReport(cohort_id)
    regenerated: Dict[str, List[Any]] = {"ledger": [], "events": [], "snapshots": [], "outcomes": []}
    for run in store.rows(
        "SELECT d.* FROM paper_run_decision d JOIN paper_cohort_progress p ON p.run_seq = d.run_seq AND p.cohort_id = ? "
        "ORDER BY d.run_seq", (cohort_id,),
    ):
        result = engine.advance(build(run))
        report.runs += 1
        report.rows += len(result.rows)
        regenerated["ledger"].extend(canonical(r) for r in result.rows)
        regenerated["events"].extend(canonical(e) for e in result.position_events)
        regenerated["snapshots"].extend(
            canonical([s.day.isoformat(), s.equity, s.cash, s.long_value, stale, s.positions,
                       canonical({"region": s.by_region, "currency": s.by_currency,
                                  "economic_currency": s.by_economic_currency, "sector": s.by_sector})])
            for s, stale in zip(result.snapshots, result.stale_values))
        regenerated["outcomes"].extend(
            canonical([o.trade.position_id, canonical(asdict(o.trade)), o.mae_R, o.mfe_R]) for o in result.outcomes)
    stored = _stored(store, cohort_id)
    regenerated["outcomes"].sort()
    stored["outcomes"].sort()
    for table in ("ledger", "events", "snapshots", "outcomes"):
        a, b = stored[table], regenerated[table]
        if a != b:
            report.match = False
            index = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            report.first_divergence = {
                "tabla": table, "indice": index, "escritas": len(a), "regeneradas": len(b),
                "escrita": json.loads(a[index]) if index < len(a) else None,
                "regenerada": json.loads(b[index]) if index < len(b) else None,
            }
            return report
    return report


@dataclass
class EvaluationReplay:
    passes: int = 0
    rows: int = 0
    match: bool = True
    first_divergence: Optional[Dict[str, Any]] = None


def replay_evaluations(store: PaperStore, universe: Any, envs: Mapping[str, Any], cohort_id: str, *,
                       evaluator: Any = None) -> EvaluationReplay:
    """Recalcula, pasada a pasada y con su corte, las evaluaciones escritas de una cohorte de política."""

    from datetime import date

    from paper.inputs import ts
    from paper.signals import evaluate_pass

    cohort = store.one("SELECT policy_id, start_date FROM paper_cohort WHERE cohort_id = ?", (cohort_id,))
    if cohort is None:
        raise ValueError(f"cohorte {cohort_id} inexistente")
    out = EvaluationReplay()
    starts = [date.fromisoformat(r["start_date"]) for r in store.rows("SELECT start_date FROM paper_cohort")]
    start = min(starts)
    for run in store.rows("SELECT * FROM paper_run_decision ORDER BY run_seq"):
        written = {r["signal_id"]: r["content_sha256"] for r in store.rows(
            "SELECT signal_id, content_sha256 FROM paper_signal_evaluation WHERE cohort_id = ? AND paper_run_id = ?",
            (cohort_id, run["paper_run_id"]))}
        if not written:
            continue
        rows = evaluate_pass(store, universe, {cohort["policy_id"]: cohort_id}, envs, pass_ts=ts(run["pass_scheduled_ts"]),
                             now=ts(run["data_cutoff_ts"]), start=start, paper_run_id=run["paper_run_id"],
                             source_run_id="", evaluator=evaluator)
        regenerated = {r["signal_id"]: r["content_sha256"] for r in rows}
        out.passes += 1
        out.rows += len(written)
        if any(regenerated.get(signal_id) != digest for signal_id, digest in written.items()):
            out.match = False
            out.first_divergence = {"run_seq": int(run["run_seq"]), "escritas": len(written), "regeneradas": len(regenerated)}
            return out
    return out
