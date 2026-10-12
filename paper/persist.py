"""Persistencia de lo que produce ``engine_v1`` (ficha §5, §12).

Cada avance de una cohorte se escribe en una sola transacción (más estricta que «una por lote τ»): o entra
entero o no entra. Las filas de hechos llevan un ``content_sha256`` sobre su contenido económico; reescribir
una clave con otro contenido es ``ERROR_DIVERGENCIA``.

El estado del motor se guarda como JSON canónico comprimido (nunca ``pickle``) en una **caché** de una fila
por cohorte, que no es un hecho: solo se usa si su sha256 coincide con el ``state_sha256`` append-only de la
última ejecución en ``paper_cohort_progress``. Si no, se descarta y el estado se reconstruye repitiendo la
secuencia registrada, comprobando que regenera exactamente lo escrito (``paper.audit`` lo verifica desde cero).
"""

from __future__ import annotations

import hashlib
import json
import zlib
from dataclasses import asdict
from typing import Any, Dict, Tuple

from paper.engine_v1 import AdvanceResult, Engine, EngineSpec, engine_from_state, engine_to_state
from paper.store import PaperStore, canonical, content_sha256

META = ("run_seq", "content_sha256")


class ReplayMismatch(RuntimeError):
    """La repetición de una ejecución no regenera lo escrito: el estado no se puede restaurar."""


def state_digest(engine: Engine) -> Tuple[str, str]:
    text = canonical(engine_to_state(engine))
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()


def restore_engine(store: PaperStore, spec: EngineSpec, cohort_id: str, rebuild_view: Any) -> Engine:
    """Estado del libro al final de su última ejecución.

    Primero la caché, si su sha256 cuadra con el ``state_sha256`` (append-only) de esa ejecución en
    ``paper_cohort_progress`` y es la última. Si no, se descarta y se repite desde cero toda la secuencia
    registrada, comprobando en cada ejecución que regenera lo escrito y su ``state_sha256``.
    """

    last = store.one("SELECT run_seq, state_sha256 FROM paper_cohort_progress WHERE cohort_id = ? ORDER BY run_seq DESC LIMIT 1",
                     (cohort_id,))
    if last is None:
        return Engine(spec)
    cached = store.one("SELECT * FROM paper_engine_state_cache WHERE cohort_id = ?", (cohort_id,))
    if cached is not None and int(cached["run_seq"]) == int(last["run_seq"]):
        text = zlib.decompress(bytes(cached["state_json_zlib"])).decode("utf-8")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest == cached["state_sha256"] == last["state_sha256"]:
            return engine_from_state(spec, json.loads(text))
    engine = Engine(spec)
    for run in store.rows(
        "SELECT d.*, p.state_sha256 AS expected FROM paper_cohort_progress p JOIN paper_run_decision d ON d.run_seq = p.run_seq "
        "WHERE p.cohort_id = ? ORDER BY p.run_seq", (cohort_id,),
    ):
        result = engine.advance(rebuild_view(run))
        stored = {int(r["seq"]): r["row_json"] for r in store.rows(
            "SELECT seq, row_json FROM paper_ledger WHERE cohort_id = ? AND run_seq = ?", (cohort_id, run["run_seq"]))}
        regenerated = {int(r["seq"]): canonical(r) for r in result.rows}
        if stored != regenerated or state_digest(engine)[1] != run["expected"]:
            raise ReplayMismatch(f"{cohort_id}: la ejecución {run['run_seq']} no se reproduce")
    return engine


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
            "exit_session": outcome.exit_session or _session_of_ts(engine, trade.asset, trade.exit_ts),
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
    text, digest = state_digest(engine)
    frontier = result.frontier
    counters = dict(engine.counters)
    if result.late_signals:
        counters["late_signals"] = len(result.late_signals)
    store.insert("paper_cohort_progress", {
        "cohort_id": cohort_id, "run_seq": run_seq, "paper_run_id": paper_run_id,
        "frontier_ts_utc": frontier[0].isoformat() if frontier else "",
        "frontier_key": canonical([frontier[0].isoformat(), frontier[1], frontier[2]]) if frontier else "",
        "stop_reason": result.stop_reason, "stalled_on": canonical(list(result.stalled_on)),
        "counters_json": canonical(counters), "state_sha256": digest,
    }, ("cohort_id", "run_seq"))
    store.conn.execute(
        "INSERT OR REPLACE INTO paper_engine_state_cache (cohort_id, run_seq, state_json_zlib, state_sha256) VALUES (?, ?, ?, ?)",
        (cohort_id, run_seq, zlib.compress(text.encode("utf-8"), 9), digest),
    )
    return digest


