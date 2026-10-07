"""Reconstrucción y auditoría (ficha §12, §13; D-78).

Repite desde cero la secuencia registrada de ejecuciones de una cohorte, cada una con sus propias entradas
(``observed_at ≤`` su ``decision_ts``) y su límite (la hora programada de su pasada), y compara fila a fila
lo que regenera con lo escrito. Es la prueba de idempotencia, la de reconstrucción y la base de la
equivalencia de una época de entorno. En una cohorte sellada solo es visible si coincide o no.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from paper.contract import contract_from_row
from paper.engine_v1 import Engine
from paper.inputs import build_view, ts
from paper.store import PaperStore, canonical, content_sha256

META = ("run_seq", "content_sha256")


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


def replay(store: PaperStore, universe: Any, cohort_id: str) -> ReplayReport:
    cohort = store.one("SELECT * FROM paper_cohort WHERE cohort_id = ?", (cohort_id,))
    if cohort is None:
        raise ValueError(f"cohorte {cohort_id} inexistente")
    contract = contract_from_row(dict(cohort))
    engine = Engine(contract.engine_spec())
    report = ReplayReport(cohort_id)
    persisted = {int(r["seq"]): r for r in store.rows("SELECT * FROM paper_ledger WHERE cohort_id = ?", (cohort_id,))}
    runs = store.rows(
        "SELECT r.* FROM paper_run r JOIN paper_cohort_progress p ON p.run_seq = r.run_seq AND p.cohort_id = ? "
        "ORDER BY r.run_seq", (cohort_id,),
    )
    for run in runs:
        late_before = ts(run["late_before"]) if run["late_before"] else None
        view, _infos = build_view(store, universe, contract, cohort_id, cutoff=ts(run["decision_ts"]),
                                  limit=ts(run["pass_scheduled_ts"]), late_before=late_before)
        result = engine.advance(view)
        report.runs += 1
        for row in result.rows:
            report.rows += 1
            fact = {
                "cohort_id": cohort_id, "seq": int(row["seq"]), "run_seq": int(run["run_seq"]), "epoch_no": 0,
                "event_type": row["event_type"], "timestamp_utc": row["timestamp_utc"],
                "signal_id": str(row["signal_id"]), "position_id": str(row["position_id"]), "row_json": canonical(row),
            }
            stored = persisted.get(int(row["seq"]))
            if stored is None or stored["row_json"] != fact["row_json"] or int(stored["run_seq"]) != int(run["run_seq"]):
                report.match = False
                report.first_divergence = {
                    "seq": int(row["seq"]), "run_seq": int(run["run_seq"]),
                    "regenerada": json.loads(fact["row_json"]),
                    "escrita": json.loads(stored["row_json"]) if stored is not None else None,
                }
                return report
            _ = content_sha256(fact, META)
    if report.rows != len(persisted):
        report.match = False
        report.notes.append(f"filas escritas {len(persisted)} ≠ regeneradas {report.rows}")
    return report
