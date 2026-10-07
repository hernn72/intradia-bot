"""Capa única de visibilidad de ``paper.db`` (ficha §10; D-75, D-76, D-78, D-79).

**Toda** lectura para presentación (CLI, Telegram, exportaciones, futuros dashboard y API) pasa por aquí. Las
tablas selladas solo se leen en :func:`read_outcomes` (que registra el acceso **antes** de devolver nada y
consume las sesiones cubiertas) y en la vía extraordinaria :func:`seal_break`.

Visible siempre, porque no depende de ningún libro: evaluaciones ex ante, comprobaciones de apertura por
política (``MARKET_PASS`` o rechazo de mercado, ``requested_weight``), alertas de dato, peticiones y caídas
del motor, épocas de entorno, estado administrativo de cohorte (``CLOSED`` no durante un sellado), ventanas
de sellado y compromisos con nonce.

Sellado durante el embargo de T-024 (B2, S2, C0) y en una ventana de P7 (todas las cohortes, con lo
acumulado): ``FILLED`` y cualquier resultado por libro, tamaños en EUR o unidades, posiciones, salidas, P&L,
cash, equity, métricas, frontera y diagnósticos de libro.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from paper.store import PaperStore, canonical, sha256_text

SEALED_TABLES = (
    "paper_ledger", "paper_signal_disposition", "paper_order", "paper_entry_decision", "paper_position",
    "paper_position_event", "paper_equity_snapshot", "paper_trade_outcome", "paper_cohort_progress",
    "paper_run_diagnostic", "paper_seal_nonce", "paper_engine_state_cache",
)
VISIBLE_EVALUATION_FIELDS = (
    "policy_id", "signal_id", "symbol", "market", "signal_session_date", "pass_scheduled_ts", "analysis_timestamp",
    "decision_ts", "operar", "reference_price", "entry_max", "stop", "target1", "target2", "target3",
    "rr_at_reference", "risk_fraction", "score", "setup_radar", "setup_accion", "context_json", "data_quality",
)
VISIBLE_OPEN_CHECK_FIELDS = ("entry_session", "open_market", "entry_effective", "check_code", "requested_weight")
POLICY_DISPLAY = {"B2": "B2-P6", "S2": "S2-P6", "C0": "C0-P6", "BH": "BH"}


class SealedError(PermissionError):
    """Un desenlace cubierto por un sellado activo no se devuelve por la vía normal."""


@dataclass(frozen=True)
class SealWindow:
    window_id: str
    kind: str
    cohorts: Tuple[str, ...]
    sessions_from: date
    sessions_to: Optional[date]
    active: bool
    sessions_status: str


def seal_windows(store: PaperStore) -> List[SealWindow]:
    latest: Dict[str, Any] = {}
    for row in store.rows("SELECT * FROM paper_seal_window ORDER BY window_id, revision"):
        latest[row["window_id"]] = row
    out = []
    for row in latest.values():
        out.append(SealWindow(
            window_id=row["window_id"], kind=row["kind"], cohorts=tuple(json.loads(row["cohorts_json"])),
            sessions_from=date.fromisoformat(row["sessions_from"]),
            sessions_to=date.fromisoformat(row["sessions_to"]) if row["sessions_to"] else None,
            active=bool(row["seal_still_active"]), sessions_status=row["sessions_status"],
        ))
    return out


def _covers(window: SealWindow, cohort_id: str, first: date, last: date) -> bool:
    """¿El sellado cubre algún valor que dependa de las sesiones ``[first, last]`` de la cohorte?

    En una ventana de P7 también lo acumulado: cualquier valor cuyo tramo llegue a la ventana o la pase.
    """

    if not window.active:
        return False
    if window.cohorts and cohort_id not in window.cohorts:
        return False
    if window.kind == "EMBARGO_T024":
        return True
    return last >= window.sessions_from


def sealed_cohorts(store: PaperStore) -> List[str]:
    cohorts = [r["cohort_id"] for r in store.rows("SELECT cohort_id FROM paper_cohort")]
    windows = [w for w in seal_windows(store) if w.active and w.kind == "EMBARGO_T024"]
    return [c for c in cohorts if any(_covers(w, c, date.min, date.max) for w in windows)]


def is_sealed(store: PaperStore, cohort_id: str, first: date = date.min, last: date = date.max) -> bool:
    return any(_covers(w, cohort_id, first, last) for w in seal_windows(store))


# ---------------------------------------------------------------------------- vista visible


def visible_signals(store: PaperStore, *, since: Optional[str] = None) -> List[Dict[str, Any]]:
    """Señales ex ante por política con su comprobación de apertura de mercado. Nunca ``FILLED``."""

    params: List[Any] = []
    where = ""
    if since:
        where = "WHERE e.signal_session_date >= ?"
        params.append(since)
    rows = store.rows(
        f"SELECT e.*, c.t025_code_sha AS code_sha FROM paper_signal_evaluation e "
        f"JOIN paper_cohort c ON c.cohort_id = e.cohort_id {where} "
        "ORDER BY e.signal_session_date, e.symbol, e.policy_id, e.pass_scheduled_ts", params,
    )
    checks = {(r["policy_id"], r["t025_code_sha"], r["signal_id"]): r for r in store.rows("SELECT * FROM paper_open_check")}
    out = []
    for row in rows:
        item = {f: row[f] for f in VISIBLE_EVALUATION_FIELDS}
        item["policy"] = POLICY_DISPLAY.get(row["policy_id"], row["policy_id"])
        check = checks.get((row["policy_id"], row["code_sha"], row["signal_id"]))
        for field in VISIBLE_OPEN_CHECK_FIELDS:
            item[field] = check[field] if check is not None else None
        out.append(item)
    return out


def cohort_states(store: PaperStore) -> List[Dict[str, Any]]:
    """Estado **administrativo** de cada cohorte; ``CLOSED`` no se publica mientras rija un sellado (§13)."""

    out = []
    for cohort in store.rows("SELECT cohort_id, policy_id, kind, start_date, t025_code_sha FROM paper_cohort ORDER BY policy_id"):
        events = store.rows(
            "SELECT state, event_ts_utc FROM paper_cohort_event WHERE cohort_id = ? ORDER BY event_ts_utc, created_at",
            (cohort["cohort_id"],),
        )
        sealed = is_sealed(store, cohort["cohort_id"])
        visible = [e for e in events if not (sealed and e["state"] == "CLOSED")]
        state = visible[-1]["state"] if visible else "ACTIVE"
        out.append({
            "cohort_id": cohort["cohort_id"], "policy": POLICY_DISPLAY.get(cohort["policy_id"], cohort["policy_id"]),
            "kind": cohort["kind"], "start_date": cohort["start_date"], "state": state, "sealed": sealed,
        })
    return out


def visible_status(store: PaperStore) -> Dict[str, Any]:
    runs = store.rows("SELECT run_seq, pass_scheduled_ts, status FROM paper_run ORDER BY run_seq DESC LIMIT 10")
    alerts = store.rows("SELECT object, kind, session_date FROM paper_data_alert ORDER BY detected_at DESC, object LIMIT 50")
    epochs = store.rows("SELECT cohort_id, epoch_no, python_version, installed_packages_sha256, decision_ref FROM paper_environment_epoch")
    downtime = store.rows("SELECT scope, from_scheduled_pass, to_scheduled_pass, subcause FROM paper_engine_downtime")
    commitments = store.rows("SELECT cohort_id, paper_run_id, commitment_sha256 FROM paper_seal_commitment ORDER BY paper_run_id DESC LIMIT 8")
    return {
        "cohorts": cohort_states(store),
        "runs": [dict(r) for r in runs],
        "alerts": [dict(r) for r in alerts],
        "epochs": [dict(r) for r in epochs],
        "downtime": [dict(r) for r in downtime],
        "seal_windows": [w.__dict__ | {"sessions_from": w.sessions_from.isoformat(),
                                        "sessions_to": w.sessions_to.isoformat() if w.sessions_to else ""}
                         for w in seal_windows(store)],
        "commitments": [dict(r) for r in commitments],
    }


# ---------------------------------------------------------------------------- desenlaces y consumo


def _sessions_between(first: str, last: str) -> List[str]:
    a, b = date.fromisoformat(first[:10]), date.fromisoformat(last[:10])
    out, day = [], a
    while day <= b:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day += timedelta(days=1)
    return out


def _record_access(store: PaperStore, cohort_id: str, *, who: str, purpose: str, access_kind: str, query: str,
                   sessions: Sequence[str], payload: Any, now: datetime) -> str:
    access_id = str(uuid.uuid4())
    with store.transaction():
        store.insert("paper_outcome_access", {
            "access_id": access_id, "cohort_id": cohort_id, "accessed_at": now.isoformat(), "who": who,
            "purpose": purpose, "access_kind": access_kind, "query": query,
            "sessions_json": canonical(sorted(set(sessions))), "rows_sha256": sha256_text(canonical(payload)),
        }, ("access_id",))
    return access_id


def _outcome_payload(store: PaperStore, cohort_id: str) -> Dict[str, Any]:
    return {
        "trades": [dict(r) for r in store.rows("SELECT * FROM paper_trade_outcome WHERE cohort_id = ? ORDER BY position_id", (cohort_id,))],
        "snapshots": [dict(r) for r in store.rows("SELECT * FROM paper_equity_snapshot WHERE cohort_id = ? ORDER BY snapshot_day", (cohort_id,))],
        "entries": [dict(r) for r in store.rows("SELECT * FROM paper_entry_decision WHERE cohort_id = ? ORDER BY ledger_seq", (cohort_id,))],
    }


def _sessions_of(payload: Mapping[str, Any]) -> List[str]:
    sessions: List[str] = []
    for trade in payload["trades"]:
        sessions.extend(_sessions_between(trade["entry_session"], trade["exit_session"]))
    snaps = payload["snapshots"]
    if snaps:
        sessions.extend(_sessions_between(snaps[0]["snapshot_day"], snaps[-1]["snapshot_day"]))
    return sessions


def read_outcomes(store: PaperStore, cohort_id: str, *, who: str, purpose: str, now: datetime) -> Dict[str, Any]:
    """Vía normal: solo fuera de todo sellado. Registra el acceso y sus sesiones **antes** de devolver nada
    (§10.6): esas sesiones quedan consumidas para investigación."""

    payload = _outcome_payload(store, cohort_id)
    sessions = _sessions_of(payload)
    first = min(sessions) if sessions else "9999-12-31"
    last = max(sessions) if sessions else "0001-01-01"
    if is_sealed(store, cohort_id, date.fromisoformat(first), date.fromisoformat(last)) or (
        not sessions and is_sealed(store, cohort_id)
    ):
        raise SealedError(f"{cohort_id}: desenlaces sellados (embargo de T-024 o ventana de P7)")
    _record_access(store, cohort_id, who=who, purpose=purpose, access_kind="NORMAL", query="read_outcomes",
                   sessions=sessions, payload=payload, now=now)
    return payload


def seal_break(store: PaperStore, cohort_id: str, *, who: str, purpose: str, now: datetime, confirm: bool) -> Dict[str, Any]:
    """Vía extraordinaria (§10.4): solo recuperación o auditoría técnica. Escribe ``SEAL_BREAK_AUDIT`` con
    las sesiones cubiertas antes de devolver nada; es una ruptura del sellado y consume esas sesiones."""

    if not confirm:
        raise SealedError("la vía extraordinaria exige confirmación explícita (ruptura del sellado)")
    if not purpose.strip() or not who.strip():
        raise SealedError("la vía extraordinaria exige quién y para qué")
    payload = _outcome_payload(store, cohort_id)
    _record_access(store, cohort_id, who=who, purpose=purpose, access_kind="SEAL_BREAK_AUDIT", query="seal_break",
                   sessions=_sessions_of(payload), payload=payload, now=now)
    return payload


def consumed_sessions(store: PaperStore) -> List[str]:
    out = set()
    for row in store.rows("SELECT sessions_json FROM paper_outcome_access"):
        out.update(json.loads(row["sessions_json"]))
    return sorted(out)


# ---------------------------------------------------------------------------- compromisos de sellado


def sealed_digest(store: PaperStore, cohort_id: str) -> str:
    digest = hashlib.sha256()
    for table, order in (("paper_ledger", "seq"), ("paper_position_event", "event_seq"),
                         ("paper_equity_snapshot", "snapshot_day"), ("paper_trade_outcome", "position_id")):
        for row in store.rows(f"SELECT content_sha256 FROM {table} WHERE cohort_id = ? ORDER BY {order}", (cohort_id,)):
            digest.update(row["content_sha256"].encode("ascii"))
    return digest.hexdigest()


def write_commitment(store: PaperStore, cohort_id: str, paper_run_id: str) -> str:
    """Compromiso con nonce nuevo por ejecución: cambia aunque no haya filas nuevas y no delata nada (§5)."""

    nonce = secrets.token_hex(32)
    commitment = sha256_text(nonce + sealed_digest(store, cohort_id))
    store.insert("paper_seal_nonce", {"cohort_id": cohort_id, "paper_run_id": paper_run_id, "nonce_hex": nonce},
                 ("cohort_id", "paper_run_id"))
    store.insert("paper_seal_commitment", {"cohort_id": cohort_id, "paper_run_id": paper_run_id,
                 "commitment_sha256": commitment}, ("cohort_id", "paper_run_id"))
    return commitment


# ---------------------------------------------------------------------------- ventanas


def _window_revision(store: PaperStore, window_id: str) -> Tuple[Optional[Any], int]:
    row = store.one("SELECT * FROM paper_seal_window WHERE window_id = ? ORDER BY revision DESC LIMIT 1", (window_id,))
    return row, (int(row["revision"]) + 1 if row else 1)


def open_window(store: PaperStore, *, window_id: str, kind: str, cohorts: Sequence[str], sessions_from: date,
                sessions_to: Optional[date], decision_ref: str, now: datetime) -> None:
    row, revision = _window_revision(store, window_id)
    if row is not None:
        raise ValueError(f"la ventana {window_id} ya existe")
    if kind == "P7_WINDOW" and sessions_from <= now.date():
        raise ValueError("una ventana de P7 solo admite sesiones futuras (D-75; D-79 para las reutilizadas)")
    store.insert("paper_seal_window", {
        "window_id": window_id, "revision": revision, "kind": kind, "cohorts_json": canonical(list(cohorts)),
        "sessions_from": sessions_from.isoformat(), "sessions_to": sessions_to.isoformat() if sessions_to else "",
        "opened_at": now.isoformat(), "opened_by_ref": decision_ref,
    }, ("window_id", "revision"))


def close_window(store: PaperStore, *, window_id: str, closure: str, decision_ref: str, now: datetime) -> Dict[str, Any]:
    """Cierra una ventana con una D-nn. ``P7_ABANDONED``: ``VIRGEN_REUTILIZABLE`` si y solo si hubo 0 accesos
    a desenlaces de sus sesiones (de cualquier tipo, también a valores acumulados) y el sellado no se
    interrumpió; entonces **sigue sellada**. Si no, ``CONSUMIDA`` (D-78, OD-T25-10)."""

    row, revision = _window_revision(store, window_id)
    if row is None:
        raise ValueError(f"ventana {window_id} inexistente")
    window_from = date.fromisoformat(row["sessions_from"])
    window_to = date.fromisoformat(row["sessions_to"]) if row["sessions_to"] else date.max
    accesses = []
    for access in store.rows("SELECT access_id, sessions_json, access_kind FROM paper_outcome_access ORDER BY accessed_at"):
        days = [date.fromisoformat(d) for d in json.loads(access["sessions_json"])]
        # Un valor acumulado cubre desde el inicio de la cohorte: si su tramo llega a la ventana, la toca.
        if any(window_from <= d <= window_to for d in days) or (days and max(days) >= window_from and min(days) <= window_from):
            accesses.append(dict(access))
    history = store.rows("SELECT revision, seal_still_active FROM paper_seal_window WHERE window_id = ? ORDER BY revision", (window_id,))
    uninterrupted = all(bool(h["seal_still_active"]) for h in history)
    evidence = {"window_id": window_id, "accesses": accesses, "uninterrupted": uninterrupted,
                "access_log_sha256": sha256_text(canonical([dict(r) for r in store.rows("SELECT * FROM paper_outcome_access ORDER BY access_id")]))}
    if closure == "P7_ABANDONED":
        virgin = not accesses and uninterrupted
        status, still = ("VIRGEN_REUTILIZABLE", 1) if virgin else ("CONSUMIDA", 0)
    elif closure == "P7_CONSULTED":
        status, still = "CONSUMIDA", 0
    elif closure == "EMBARGO_LIFTED":
        status, still = "", 0
    else:
        raise ValueError(f"cierre desconocido: {closure}")
    store.insert("paper_seal_window", {
        "window_id": window_id, "revision": revision, "kind": row["kind"], "cohorts_json": row["cohorts_json"],
        "sessions_from": row["sessions_from"], "sessions_to": row["sessions_to"], "opened_at": row["opened_at"],
        "opened_by_ref": row["opened_by_ref"], "closed_at": now.isoformat(), "closed_by_ref": decision_ref,
        "closure": closure, "sessions_status": status, "seal_still_active": still,
        "evidence_sha256": sha256_text(canonical(evidence)),
    }, ("window_id", "revision"))
    return {**evidence, "sessions_status": status, "seal_still_active": bool(still)}


def eligible_for_p7(store: PaperStore, window_id: str, candidate_frozen_at: datetime, first_session_open: datetime) -> bool:
    """D-79: una ventana ``VIRGEN_REUTILIZABLE`` solo es holdout de P7 para una candidata completamente
    congelada antes de la primera sesión de esa ventana (la apertura más temprana de cualquier plaza)."""

    window = next((w for w in seal_windows(store) if w.window_id == window_id), None)
    if window is None or window.sessions_status != "VIRGEN_REUTILIZABLE" or not window.active:
        return False
    return candidate_frozen_at < first_session_open
