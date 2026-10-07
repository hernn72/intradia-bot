"""Vista del motor en una ejecución, construida solo con lo observado hasta su corte (ficha §3.3, §7, §8).

Reglas implementadas aquí:

- **Serie vigente y contigua.** Para cada activo, la primera observación de cada sesión con
  ``observed_at ≤ corte`` y escala no dudosa. Desde el inicio de la cohorte la serie avanza sesión a sesión
  del calendario: una sesión sin barra y no declarada ausente detiene la serie (``horizon`` = su apertura).
- **Plazos de 5 y 20 sesiones (D-78).** Una sesión ``s'`` posterior a la que falta cuenta solo si cerró con
  el motor operativo (la primera pasada programada tras su cierre no está en una caída) y una petición
  posterior a su cierre dio ``PROVIDER_DATA_MISSING``. Con 5 se declara la sesión ausente (salto de P6);
  con 20 consecutivas, ``DATA_LOSS``. Una barra observada después de la declaración es tardía y no entra.
- **Escala de ejecución (§3.3).** Cada barra se multiplica por los splits que ya reflejaba cuando se
  observó (fecha ex posterior a su sesión y ``observed_at`` del split ≤ el de la barra).
- **Señal vinculante (§7.1, D-50).** La evaluación de la última pasada con hora y ``decision_ts`` anteriores
  a la apertura de entrada. Solo se entrega al motor cuando es definitiva: existe la de la pasada vinculante
  programada o ya pasó la apertura.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from advisor.research.p6_sim import FxTable, Signal
from paper.contract import CohortContract
from paper.engine_v1 import AssetMeta, AssetView, EngineView
from paper.store import PaperStore
from paper.universe import (
    FX_MARKET,
    PaperAsset,
    PaperUniverse,
    binding_pass,
    closed_by,
    next_session,
    open_close,
    scheduled_passes,
    sessions,
    snapshot_days,
)

UTC = timezone.utc
DECLARE_AFTER = 5
DATA_LOSS_AFTER = 20


def ts(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


@dataclass(frozen=True)
class MissingInfo:
    declared: Dict[date, datetime]
    counts: Dict[date, int]
    data_loss_since: Optional[date]


@dataclass
class SeriesInfo:
    view: AssetView
    sessions: Tuple[date, ...]
    bar_timestamps: Tuple[str, ...]
    observed_at: Tuple[str, ...]
    exec_factor: Tuple[float, ...]
    splits: List[Tuple[date, float, str]] = field(default_factory=list)
    missing: Optional[MissingInfo] = None


class Downtime:
    """Pasadas programadas cubiertas por una caída del motor (``paper_engine_downtime``) hasta el corte."""

    def __init__(self, store: PaperStore, cutoff: datetime, scope: str = "ALL") -> None:
        self.intervals = [
            (ts(r["from_scheduled_pass"]), ts(r["to_scheduled_pass"]))
            for r in store.rows(
                "SELECT from_scheduled_pass, to_scheduled_pass FROM paper_engine_downtime WHERE scope IN ('ALL', ?) "
                "AND detected_at <= ?", (scope, cutoff.isoformat()),
            )
        ]

    def covers(self, moment: datetime) -> bool:
        return any(start <= moment <= end for start, end in self.intervals)

    def operative_after(self, close: datetime) -> bool:
        following = scheduled_passes(close, close + timedelta(days=5))
        return bool(following) and not self.covers(following[0])


def missing_info(store: PaperStore, obj: str, market: str, missing: Sequence[date], cutoff: datetime,
                 settlement: int, downtime: Downtime) -> MissingInfo:
    declared: Dict[date, datetime] = {}
    counts: Dict[date, int] = {}
    if not missing:
        return MissingInfo(declared, counts, None)
    requests = store.rows(
        "SELECT session_date, requested_at FROM paper_bar_request WHERE object = ? AND result = 'PROVIDER_DATA_MISSING' "
        "AND due = 1 AND requested_at <= ? ORDER BY requested_at", (obj, cutoff.isoformat()),
    )
    by_session: Dict[str, List[datetime]] = {}
    for row in requests:
        by_session.setdefault(row["session_date"], []).append(ts(row["requested_at"]))
    horizon_end = cutoff.date()
    for day in missing:
        stamps = by_session.get(day.isoformat(), [])
        if not stamps:
            counts[day] = 0
            continue
        later = [s for s in sessions(market, day + timedelta(days=1), horizon_end) if closed_by(market, s, cutoff, settlement)]
        closes = [open_close(market, s)[1] if market != FX_MARKET else datetime.combine(s + timedelta(days=1), time(0), UTC)
                  for s in later]
        operative = [c for c in closes if downtime.operative_after(c)]
        best = 0
        for stamp in stamps:
            count = sum(1 for close in operative if close < stamp)
            best = max(best, count)
            if count >= DECLARE_AFTER and day not in declared:
                declared[day] = stamp
        counts[day] = best
    return MissingInfo(declared, counts, None)


def trailing_gap_start(expected: Sequence[date], absent: Sequence[date]) -> Optional[date]:
    """Primera sesión del tramo final de sesiones esperadas consecutivas sin barra (o ``None``)."""

    missing = set(absent)
    start: Optional[date] = None
    for day in reversed(list(expected)):
        if day not in missing:
            break
        start = day
    return start


def _splits(store: PaperStore, symbol: str, cutoff: datetime) -> List[Tuple[date, float, str]]:
    return [
        (date.fromisoformat(r["ex_date"]), float(r["ratio"]), r["observed_at"])
        for r in store.rows(
            "SELECT ex_date, ratio, observed_at FROM paper_corporate_action WHERE data_symbol = ? AND kind = 'SPLIT' "
            "AND observed_at <= ? ORDER BY ex_date", (symbol, cutoff.isoformat()),
        )
    ]


def exec_factor(session: date, observed_at: str, splits: Sequence[Tuple[date, float, str]]) -> float:
    """Splits que la barra ya reflejaba al observarse: para pasar a la escala de su sesión (§3.3)."""

    factor = 1.0
    for ex_date, ratio, split_observed in splits:
        if ex_date > session and split_observed <= observed_at:
            factor *= ratio
    return factor


def series_info(store: PaperStore, asset: PaperAsset, start: date, cutoff: datetime, settlement: int,
                downtime: Downtime) -> SeriesInfo:
    symbol = asset.data_symbol
    first: Dict[str, sqlite3.Row] = {}
    for row in store.rows(
        "SELECT * FROM paper_bar_observation WHERE data_symbol = ? AND scale_doubtful = 0 AND observed_at <= ? "
        "ORDER BY session_date, observed_at", (symbol, cutoff.isoformat()),
    ):
        first.setdefault(row["session_date"], row)
    splits = _splits(store, symbol, cutoff)
    expected = [d for d in sessions(asset.market, start, cutoff.date()) if closed_by(asset.market, d, cutoff, settlement)]
    absent = [d for d in expected if d.isoformat() not in first]
    info = missing_info(store, symbol, asset.market, absent, cutoff, settlement, downtime)
    gap = trailing_gap_start(expected, absent)
    if gap is not None and info.counts.get(gap, 0) >= DATA_LOSS_AFTER:
        info = MissingInfo(info.declared, info.counts, gap)
    chosen: List[sqlite3.Row] = [row for day, row in sorted(first.items()) if date.fromisoformat(day) < start]
    horizon: Optional[datetime] = None
    last_session: Optional[date] = None
    for day in expected:
        found = first.get(day.isoformat())
        declared_at = info.declared.get(day)
        if found is not None and (declared_at is None or ts(found["observed_at"]) < declared_at):
            chosen.append(found)
            last_session = day
        elif declared_at is not None:
            continue
        else:
            horizon = open_close(asset.market, day)[0]
            break
    else:
        anchor = expected[-1] if expected else (last_session or start - timedelta(days=1))
        horizon = open_close(asset.market, next_session(asset.market, anchor))[0]
    days = tuple(date.fromisoformat(r["session_date"]) for r in chosen)
    factors = tuple(exec_factor(d, r["observed_at"], splits) for d, r in zip(days, chosen))
    opens, closes = [], []
    for d in days:
        o, c = open_close(asset.market, d)
        opens.append(o)
        closes.append(c)
    index_of = {d: i for i, d in enumerate(days)}

    def first_index_on_or_after(day: date) -> Optional[int]:
        for i, d in enumerate(days):
            if d >= day:
                return i
        return None

    split_map: Dict[int, float] = {}
    for ex_date, ratio, _obs in splits:
        i = first_index_on_or_after(ex_date)
        if i is not None:
            split_map[i] = split_map.get(i, 1.0) * ratio
    dividends: Dict[int, float] = {}
    for r in store.rows(
        "SELECT ex_date, amount, observed_at FROM paper_corporate_action WHERE data_symbol = ? AND kind = 'DIVIDEND' "
        "AND observed_at <= ?", (symbol, cutoff.isoformat()),
    ):
        ex = date.fromisoformat(r["ex_date"])
        i = index_of.get(ex, first_index_on_or_after(ex))
        if i is not None:
            dividends[i] = dividends.get(i, 0.0) + float(r["amount"]) * exec_factor(ex, r["observed_at"], splits)
    terminal = None
    term = store.one(
        "SELECT ex_date, amount FROM paper_corporate_action WHERE data_symbol = ? AND kind = 'TERMINAL' "
        "AND decision_ref != '' AND observed_at <= ?", (symbol, cutoff.isoformat()),
    )
    if term is not None:
        ex = date.fromisoformat(term["ex_date"])
        effective = datetime.combine(ex, time(23, 59, 59), UTC)
        terminal = (effective, float(term["amount"]))
        if horizon is not None and effective <= horizon:
            horizon = None
    view = AssetView(
        meta=AssetMeta(asset.symbol, asset.market, asset.currency, asset.economic_currency, asset.region, asset.sector),
        session_dates=days, open_utc=tuple(opens), close_utc=tuple(closes),
        open=tuple(float(r["open"]) * f for r, f in zip(chosen, factors)),
        high=tuple(float(r["high"]) * f for r, f in zip(chosen, factors)),
        low=tuple(float(r["low"]) * f for r, f in zip(chosen, factors)),
        close=tuple(float(r["close"]) * f for r, f in zip(chosen, factors)),
        dividends=dividends, splits=split_map, horizon=horizon, data_loss=info.data_loss_since is not None,
        terminal=terminal,
    )
    return SeriesInfo(
        view=view, sessions=days, bar_timestamps=tuple(r["bar_timestamp"] for r in chosen),
        observed_at=tuple(r["observed_at"] for r in chosen), exec_factor=factors, splits=splits, missing=info,
    )


def fx_inputs(store: PaperStore, universe: PaperUniverse, start: date, cutoff: datetime,
              downtime: Downtime) -> Tuple[FxTable, Optional[datetime]]:
    points: Dict[str, List[Tuple[datetime, float]]] = {}
    horizon: Optional[datetime] = None
    for pair in universe.fx_pairs():
        currency = pair[3:6]
        rows = store.rows(
            "SELECT session_date, timestamp_available, rate FROM paper_fx_quote WHERE fx_pair = ? AND observed_at <= ? "
            "ORDER BY bar_timestamp", (pair, cutoff.isoformat()),
        )
        points[currency] = [(ts(r["timestamp_available"]), float(r["rate"])) for r in rows]
        have = {r["session_date"] for r in rows}
        expected = [d for d in sessions(FX_MARKET, start - timedelta(days=7), cutoff.date())
                    if closed_by(FX_MARKET, d, cutoff, universe.settlement_minutes)]
        absent = [d for d in expected if d.isoformat() not in have]
        info = missing_info(store, pair, FX_MARKET, absent, cutoff, universe.settlement_minutes, downtime)
        for day in absent:
            if day not in info.declared:
                available = datetime.combine(day + timedelta(days=1), time(0), UTC)
                horizon = available if horizon is None else min(horizon, available)
                break
    return FxTable(points), horizon


@dataclass(frozen=True)
class Binding:
    signal_id: str
    asset: str
    signal_session: date
    entry_session: date
    pass_ts: datetime
    final: bool
    operar: bool
    stop: Optional[float]
    target2: Optional[float]
    entry_max: Optional[float]


def bindings(store: PaperStore, cohort_id: str, universe: PaperUniverse, cutoff: datetime) -> List[Binding]:
    by_key: Dict[Tuple[str, str], List[sqlite3.Row]] = {}
    for row in store.rows(
        "SELECT * FROM paper_signal_evaluation WHERE cohort_id = ? AND decision_ts <= ?", (cohort_id, cutoff.isoformat())
    ):
        by_key.setdefault((row["symbol"], row["signal_session_date"]), []).append(row)
    assets = universe.by_symbol()
    out: List[Binding] = []
    for (symbol, session_text), rows in sorted(by_key.items()):
        asset = assets[symbol]
        t = date.fromisoformat(session_text)
        entry = next_session(asset.market, t)
        entry_open = open_close(asset.market, entry)[0]
        scheduled = binding_pass(asset.market, t, entry, universe.settlement_minutes)
        candidates = [r for r in rows if ts(r["pass_scheduled_ts"]) < entry_open and ts(r["decision_ts"]) < entry_open]
        if not candidates:
            continue
        chosen = max(candidates, key=lambda r: ts(r["pass_scheduled_ts"]))
        final = cutoff >= entry_open or (scheduled is not None and any(ts(r["pass_scheduled_ts"]) == scheduled for r in candidates))
        out.append(Binding(
            signal_id=chosen["signal_id"], asset=symbol, signal_session=t, entry_session=entry,
            pass_ts=ts(chosen["pass_scheduled_ts"]), final=final, operar=bool(chosen["operar"]),
            stop=chosen["stop"], target2=chosen["target2"], entry_max=chosen["entry_max"],
        ))
    return out


def _fail_closed(store: PaperStore, cutoff: datetime) -> None:
    """Un valor de lista cerrada escrito por una versión más nueva se rechaza, nunca se ignora (§16.3)."""

    for table, column, domain in (("paper_corporate_action", "kind", "corporate_action_kind"),
                                  ("paper_bar_request", "result", "bar_request_result")):
        stamp = "observed_at" if table == "paper_corporate_action" else "requested_at"
        for row in store.rows(f"SELECT DISTINCT {column} AS v FROM {table} WHERE {stamp} <= ?", (cutoff.isoformat(),)):
            store.check_reference(domain, row["v"])


def cohort_flags(store: PaperStore, cohort_id: str, cutoff: datetime) -> Tuple[Optional[datetime], bool]:
    closing = store.one(
        "SELECT event_ts_utc FROM paper_cohort_event WHERE cohort_id = ? AND state = 'CLOSING' AND created_at <= ?",
        (cohort_id, cutoff.isoformat()),
    )
    unrunnable = store.one(
        "SELECT 1 FROM paper_cohort_event WHERE cohort_id = ? AND state = 'ENGINE_UNRUNNABLE' AND created_at <= ?",
        (cohort_id, cutoff.isoformat()),
    )
    return (ts(closing["event_ts_utc"]) if closing else None), unrunnable is not None


def build_view(store: PaperStore, universe: PaperUniverse, contract: CohortContract, cohort_id: str, *,
               cutoff: datetime, limit: datetime, late_before: Optional[datetime],
               scope: str = "ALL") -> Tuple[EngineView, Dict[str, SeriesInfo]]:
    """``scope``: la cohorte; sus caídas propias (``ENVIRONMENT_INVESTIGATION``, ``IDENTITY_MISMATCH``…)
    tampoco hacen correr sus plazos (T25-10)."""

    start = date.fromisoformat(contract.start_date)
    _fail_closed(store, cutoff)
    downtime = Downtime(store, cutoff, scope)
    infos = {a.symbol: series_info(store, a, start, cutoff, universe.settlement_minutes, downtime) for a in universe.assets}
    fx, fx_horizon = fx_inputs(store, universe, start, cutoff, downtime)
    signals: List[Signal] = []
    if contract.kind == "POLICY":
        for b in bindings(store, cohort_id, universe, cutoff):
            if not (b.final and b.operar):
                continue
            info = infos[b.asset]
            if b.signal_session not in info.sessions:
                continue
            assert b.stop is not None and b.target2 is not None and b.entry_max is not None
            signals.append(Signal(b.signal_id, b.asset, info.sessions.index(b.signal_session), b.pass_ts,
                                  float(b.stop), float(b.target2), float(b.entry_max)))
    closing_at, unrunnable = cohort_flags(store, cohort_id, cutoff)
    view = EngineView(
        assets={s: i.view for s, i in infos.items()}, fx=fx, signals=tuple(signals), start=start,
        snapshot_days=snapshot_days([a.market for a in universe.assets], start, limit.date()),
        limit=limit, fx_horizon=fx_horizon, closing_at=closing_at, unrunnable=unrunnable, late_before=late_before,
    )
    return view, infos


def views_by_asset(view: EngineView) -> Mapping[str, AssetView]:
    return view.assets
