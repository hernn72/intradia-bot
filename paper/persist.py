"""Persistencia de lo que produce ``engine_v1`` (ficha §5, §12).

Cada avance de una cohorte se escribe en una sola transacción (más estricta que «una por lote τ»): o entra
entero o no entra. Las filas de hechos llevan un ``content_sha256`` sobre su contenido económico; reescribir
una clave con otro contenido es ``ERROR_DIVERGENCIA``.

El estado del motor se guarda como checkpoint (``pickle``) con su sha256 en ``paper_cohort_progress``; la
reconstrucción completa desde las ejecuciones registradas (``paper.audit``) lo verifica.
"""

from __future__ import annotations

import hashlib
import pickle
from dataclasses import asdict
from typing import Any, Dict, Optional, Tuple

from paper.engine_v1 import AdvanceResult, Engine
from paper.store import PaperStore, canonical, content_sha256

META = ("run_seq", "content_sha256")


def engine_blob(engine: Engine) -> Tuple[bytes, str]:
    view, result = engine._view, engine._result
    engine._view = None
    try:
        blob = pickle.dumps(engine, protocol=4)
    finally:
        engine._view, engine._result = view, result
    return blob, hashlib.sha256(blob).hexdigest()


def load_engine(store: PaperStore, cohort_id: str) -> Tuple[Optional[Engine], int]:
    row = store.one(
        "SELECT c.run_seq, c.state_blob, c.state_sha256, p.state_sha256 AS expected FROM paper_engine_checkpoint c "
        "JOIN paper_cohort_progress p ON p.cohort_id = c.cohort_id AND p.run_seq = c.run_seq "
        "WHERE c.cohort_id = ? ORDER BY c.run_seq DESC LIMIT 1", (cohort_id,),
    )
    if row is None:
        return None, 0
    blob = bytes(row["state_blob"])
    digest = hashlib.sha256(blob).hexdigest()
    if digest != row["state_sha256"] or digest != row["expected"]:
        raise RuntimeError(f"{cohort_id}: checkpoint del motor corrupto (sha256 no cuadra)")
    engine = pickle.loads(blob)
    if not isinstance(engine, Engine):
        raise RuntimeError(f"{cohort_id}: checkpoint no es un Engine")
    return engine, int(row["run_seq"])


def _next(store: PaperStore, table: str, column: str, cohort_id: str) -> int:
    row = store.one(f"SELECT COALESCE(MAX({column}), 0) AS m FROM {table} WHERE cohort_id = ?", (cohort_id,))
    assert row is not None
    return int(row["m"]) + 1


def persist_advance(store: PaperStore, cohort_id: str, run_seq: int, epoch_no: int, result: AdvanceResult,
                    engine: Engine) -> Dict[str, int]:
    counts = {"ledger": 0, "events": 0, "snapshots": 0, "outcomes": 0}
    for row in result.rows:
        fact = {
            "cohort_id": cohort_id, "seq": int(row["seq"]), "run_seq": run_seq, "epoch_no": epoch_no,
            "event_type": row["event_type"], "timestamp_utc": row["timestamp_utc"], "signal_id": str(row["signal_id"]),
            "position_id": str(row["position_id"]), "row_json": canonical(row),
        }
        fact["content_sha256"] = content_sha256(fact, META)
        store.insert("paper_ledger", fact, ("cohort_id", "seq"), compare_exclude=META)
        counts["ledger"] += 1
        _derived(store, cohort_id, row)
    seq = _next(store, "paper_position_event", "event_seq", cohort_id)
    for event in result.position_events:
        fact = {
            "cohort_id": cohort_id, "event_seq": seq, "run_seq": run_seq, "epoch_no": epoch_no,
            "position_id": event["position_id"], "event_type": event["event_type"], "event_ts_utc": event["event_ts_utc"],
            "payload_json": canonical(event),
        }
        fact["content_sha256"] = content_sha256(fact, META)
        store.insert("paper_position_event", fact, ("cohort_id", "event_seq"), compare_exclude=META)
        seq += 1
        counts["events"] += 1
    for snap, stale in zip(result.snapshots, result.stale_values):
        fact = {
            "cohort_id": cohort_id, "snapshot_day": snap.day.isoformat(), "run_seq": run_seq, "epoch_no": epoch_no,
            "equity_eur": snap.equity, "cash_eur": snap.cash, "long_value_eur": snap.long_value, "stale_value_eur": stale,
            "n_positions": snap.positions,
            "exposure_json": canonical({"region": snap.by_region, "currency": snap.by_currency,
                                        "economic_currency": snap.by_economic_currency, "sector": snap.by_sector}),
        }
        fact["content_sha256"] = content_sha256(fact, META)
        store.insert("paper_equity_snapshot", fact, ("cohort_id", "snapshot_day"), compare_exclude=META)
        counts["snapshots"] += 1
    for outcome in result.outcomes:
        trade = outcome.trade
        fact = {
            "cohort_id": cohort_id, "position_id": trade.position_id, "run_seq": run_seq, "epoch_no": epoch_no,
            "entry_session": _session_of_ts(engine, trade.asset, trade.entry_ts),
            "exit_session": _session_of_ts(engine, trade.asset, trade.exit_ts),
            "exit_ts_utc": trade.exit_ts, "exit_reason": trade.exit_reason, "trade_json": canonical(asdict(trade)),
            "mae_R": outcome.mae_R, "mfe_R": outcome.mfe_R,
        }
        fact["content_sha256"] = content_sha256(fact, META)
        store.insert("paper_trade_outcome", fact, ("cohort_id", "position_id"), compare_exclude=META)
        counts["outcomes"] += 1
    return counts


def _session_of_ts(engine: Engine, asset: str, stamp: str) -> str:
    view = engine._view
    if view is not None and asset in view.assets:
        series = view.assets[asset]
        for day, opened, closed in zip(series.session_dates, series.open_utc, series.close_utc):
            if stamp in (opened.strftime("%Y-%m-%dT%H:%M:%SZ"), closed.strftime("%Y-%m-%dT%H:%M:%SZ")):
                return day.isoformat()
    return stamp[:10]


def _derived(store: PaperStore, cohort_id: str, row: Dict[str, Any]) -> None:
    kind = row["event_type"]
    seq = int(row["seq"])
    signal_id = str(row["signal_id"])
    if kind in ("SIGNAL_PENDING", "SIGNAL_IGNORED"):
        disposition = "ORDER" if kind == "SIGNAL_PENDING" else str(row["reason"])
        store.insert("paper_signal_disposition", {"cohort_id": cohort_id, "signal_id": signal_id,
                     "event_ts_utc": row["timestamp_utc"], "disposition": disposition, "ledger_seq": seq},
                     ("cohort_id", "signal_id"))
        if kind == "SIGNAL_PENDING":
            store.insert("paper_order", {"cohort_id": cohort_id, "signal_id": signal_id,
                         "order_type": "OPEN_NEXT_BAR_WITH_MAX", "ledger_seq": seq}, ("cohort_id", "signal_id"))
    elif kind in ("ENTRY", "ENTRY_REJECTED"):
        status = "FILLED" if kind == "ENTRY" else str(row["reason"])
        store.insert("paper_entry_decision", {"cohort_id": cohort_id, "signal_id": signal_id, "status": status,
                     "event_ts_utc": row["timestamp_utc"], "ledger_seq": seq}, ("cohort_id", "signal_id"))
        if kind == "ENTRY":
            store.insert("paper_position", {"cohort_id": cohort_id, "position_id": str(row["position_id"]),
                         "signal_id": signal_id, "asset": str(row["asset"]), "opened_ts_utc": row["timestamp_utc"],
                         "ledger_seq": seq}, ("cohort_id", "position_id"))


def persist_progress(store: PaperStore, cohort_id: str, run_seq: int, paper_run_id: str, result: AdvanceResult,
                     engine: Engine) -> str:
    blob, digest = engine_blob(engine)
    frontier = result.frontier
    store.insert("paper_engine_checkpoint", {"cohort_id": cohort_id, "run_seq": run_seq, "state_blob": blob,
                 "state_sha256": digest}, ("cohort_id", "run_seq"))
    store.insert("paper_cohort_progress", {
        "cohort_id": cohort_id, "run_seq": run_seq, "paper_run_id": paper_run_id,
        "frontier_ts_utc": frontier[0].isoformat() if frontier else "",
        "frontier_key": canonical([frontier[0].isoformat(), frontier[1], frontier[2]]) if frontier else "",
        "stop_reason": result.stop_reason, "stalled_on": canonical(list(result.stalled_on)),
        "counters_json": canonical(engine.counters), "state_sha256": digest,
    }, ("cohort_id", "run_seq"))
    return digest
