"""Motor incremental ``engine_v1`` de T-025 (ficha §7–§9, §12–§13).

Reproduce la semántica de ``advisor.research.p6_sim`` evento a evento —fases
``OPEN_EXIT < OPEN_ENTRY < CLOSE_EXIT < CLOSE_DIVIDEND < CLOSE_VALUATION < SIGNAL < SNAPSHOT``,
desempate ``tiebreak_key``, lote de entradas con la equity anterior al lote, comprobaciones de entrada en
el orden de ``_process_entries``, salidas con el stop ganando en la misma barra, dividendos con derecho al
cierre de la víspera— pero avanza por tramos: cada llamada a :meth:`Engine.advance` procesa solo los eventos
posteriores a la frontera ya escrita y anteriores al primer instante en que falta información (una barra
esperada de un activo con posición u orden pendiente, un tipo FX, el límite de la ejecución).

El estado no se persiste: se reconstruye repitiendo la secuencia registrada de ejecuciones, cada una con
sus propias entradas (§12, «reconstrucción»). Así la idempotencia y la detección de divergencias son la
misma operación.

Adaptaciones en vivo declaradas en la ficha §8 que este motor implementa: dividendos tardíos (``late``),
``SPLIT_ADJUST`` solo por split observado, cierre de cohorte (``EXIT_COHORT_CLOSED``), suspensión por
``DATA_LOSS`` (sin venta sintética), salida por acción corporativa terminal verificable, cancelación de
órdenes en ``CLOSING`` y en ``ENGINE_UNRUNNABLE`` y procesamiento tardío tras una caída
(``late_processing``). No hay salida ``final`` de ventana: T-025 no tiene final fijo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from advisor.analysis.levels import rr_at_least
from advisor.research.p6_sim import (
    ABOVE_MAX_ENTRY,
    ACCOUNTING_TOLERANCE_EUR,
    CLOSE_DIVIDEND,
    CLOSE_EXIT,
    CLOSE_VALUATION,
    DATA_NOT_EXECUTABLE,
    ENTRY_OK,
    EXIT_STOP,
    EXIT_TARGET,
    EXIT_TIME,
    IGNORED_ALREADY_OPEN,
    INSUFFICIENT_CASH,
    INVALID_STOP,
    INVALID_TARGET,
    LEDGER_COLUMNS,
    OPEN_ENTRY,
    OPEN_EXIT,
    PHASE_RANK,
    POSITION_TOO_SMALL,
    RR_TOO_LOW,
    SIGNAL,
    SNAPSHOT,
    SNAPSHOT_TIME,
    AccountingError,
    FxTable,
    FxUnavailableError,
    Position,
    Signal,
    Snapshot,
    Trade,
    _trade,
    check_ledger_flows,
    tiebreak_key,
    utc_iso,
)

KIND_POLICY = "POLICY"
KIND_BENCHMARK = "BENCHMARK"

EXIT_COHORT_CLOSED = "EXIT_COHORT_CLOSED"
EXIT_CORPORATE_ACTION = "EXIT_CORPORATE_ACTION"
IGNORED_COHORT_CLOSING = "IGNORED_COHORT_CLOSING"
CANCELLED_COHORT_CLOSING = "CANCELLED_COHORT_CLOSING"
CANCELLED_ENGINE_UNRUNNABLE = "CANCELLED_ENGINE_UNRUNNABLE"

EV_OPEN = "OPEN"
EV_SPLIT_ADJUST = "SPLIT_ADJUST"
EV_DIVIDEND_CREDIT = "DIVIDEND_CREDIT"
EV_EXIT = "EXIT"
EV_DATA_LOSS_SUSPENDED = "DATA_LOSS_SUSPENDED"
EV_DATA_RESUMED = "DATA_RESUMED"
EV_NO_EVALUABLE_DATA_LOSS = "NO_EVALUABLE_DATA_LOSS"
EV_NO_EVALUABLE_ENGINE_UNRUNNABLE = "NO_EVALUABLE_ENGINE_UNRUNNABLE"

STOP_LIMIT = "LIMIT"
STOP_HORIZON = "HORIZON"
STOP_FX = "FX"
STOP_DONE = "DONE"
STOP_UNRUNNABLE = "UNRUNNABLE"

EXTRA_COLUMNS = ("late", "late_processing")
ROW_COLUMNS = LEDGER_COLUMNS + EXTRA_COLUMNS

EventKey = Tuple[datetime, int, str]


@dataclass(frozen=True)
class EngineSpec:
    """Contrato económico de un libro: el de ``p6_sim.SimSpec`` (D-75: 100.000 EUR por libro)."""

    policy_id: str
    system_sha256: str
    kind: str = KIND_POLICY
    capital: float = 100_000.0
    risk_pct: float = 0.5
    max_position_pct: float = 10.0
    fee_rate: float = 0.001
    slippage_bps: float = 5.0
    min_rr: float = 1.5
    max_hold_bars: int = 40
    universe_size: int = 0

    @property
    def slip(self) -> float:
        return self.slippage_bps / 10_000.0


@dataclass(frozen=True)
class AssetMeta:
    symbol: str
    market: str
    currency: str
    economic_currency: str = ""
    region: str = ""
    sector: str = ""


@dataclass(frozen=True)
class AssetView:
    """Serie vigente y contigua de un activo en la escala de ejecución de cada sesión (§3.3).

    ``horizon`` es el instante a partir del cual faltan barras esperadas de este activo (la apertura de la
    primera sesión esperada sin barra y no declarada ausente); ``None`` significa que no falta ninguna.
    ``dividends`` y ``splits`` van indexados por la barra de la fecha ex; el importe del dividendo está en
    la escala de esa sesión.
    """

    meta: AssetMeta
    session_dates: Tuple[date, ...]
    open_utc: Tuple[datetime, ...]
    close_utc: Tuple[datetime, ...]
    open: Tuple[float, ...]
    high: Tuple[float, ...]
    low: Tuple[float, ...]
    close: Tuple[float, ...]
    dividends: Mapping[int, float] = field(default_factory=dict)
    splits: Mapping[int, float] = field(default_factory=dict)
    horizon: Optional[datetime] = None
    data_loss: bool = False
    terminal: Optional[Tuple[datetime, float]] = None

    def __post_init__(self) -> None:
        n = len(self.session_dates)
        for name in ("open_utc", "close_utc", "open", "high", "low", "close"):
            if len(getattr(self, name)) != n:
                raise ValueError(f"{self.meta.symbol}: {name} no tiene {n} barras")
        for i in range(n):
            if not self.open_utc[i] < self.close_utc[i]:
                raise ValueError(f"{self.meta.symbol}: apertura no anterior al cierre en la barra {i}")
            if i and not self.close_utc[i - 1] < self.open_utc[i]:
                raise ValueError(f"{self.meta.symbol}: barras solapadas en {i}")


@dataclass(frozen=True)
class EngineView:
    """Todo lo que el motor puede usar en una ejecución (entradas con ``observed_at`` ≤ corte).

    ``limit`` es exclusivo: se procesan los eventos con ``τ < limit``.
    """

    assets: Mapping[str, AssetView]
    fx: FxTable
    signals: Tuple[Signal, ...]
    start: date
    snapshot_days: Tuple[date, ...]
    limit: datetime
    fx_horizon: Optional[datetime] = None
    closing_at: Optional[datetime] = None
    unrunnable: bool = False
    late_before: Optional[datetime] = None


@dataclass
class PaperPosition(Position):
    """``p6_sim.Position`` más MAE/MFE (ficha §5), el rastro de splits y el estado de suspensión."""

    min_low: float = math.inf
    max_high: float = -math.inf
    split_factor: float = 1.0
    suspended: bool = False
    non_evaluable: str = ""


@dataclass(frozen=True)
class Outcome:
    trade: Trade
    mae_R: float
    mfe_R: float
    late_dividends_eur: float = 0.0


@dataclass
class _Holding:
    asset: str
    currency: str
    units: float
    mark_price: float


@dataclass
class AdvanceResult:
    rows: List[Dict[str, Any]] = field(default_factory=list)
    position_events: List[Dict[str, Any]] = field(default_factory=list)
    snapshots: List[Snapshot] = field(default_factory=list)
    stale_values: List[float] = field(default_factory=list)
    outcomes: List[Outcome] = field(default_factory=list)
    frontier: Optional[EventKey] = None
    stop_reason: str = STOP_DONE
    stalled_on: Tuple[str, ...] = ()
    late_signals: Tuple[str, ...] = ()


@dataclass(frozen=True)
class _Event:
    at: datetime
    phase: str
    key: str
    asset: str = ""
    index: int = -1
    signal: Optional[Signal] = None
    day: Optional[date] = None

    def sort_key(self) -> EventKey:
        return (self.at, PHASE_RANK[self.phase], self.key)


class Engine:
    """Estado de un libro (cohorte) que avanza por tramos sobre vistas crecientes de los datos."""

    def __init__(self, spec: EngineSpec) -> None:
        if spec.kind not in (KIND_POLICY, KIND_BENCHMARK):
            raise ValueError(f"tipo de libro desconocido: {spec.kind}")
        if spec.kind == KIND_BENCHMARK and spec.universe_size <= 0:
            raise ValueError("el benchmark necesita el tamaño del universo")
        self.spec = spec
        self.cash = spec.capital
        self.positions: Dict[str, PaperPosition] = {}
        self.closed: List[PaperPosition] = []
        self.pending: Dict[str, Signal] = {}
        self.holdings: Dict[str, _Holding] = {}
        self.first_buy_done: Set[str] = set()
        self.reinvest: Dict[str, float] = {}
        self.bh_entitlements: Dict[Tuple[str, int], float] = {}
        self.entitlements: Dict[Tuple[str, int], List[Tuple[PaperPosition, float]]] = {}
        self.eve_units: Dict[Tuple[str, int], List[Tuple[PaperPosition, float]]] = {}
        self.dividend_settled: Dict[Tuple[str, int], bool] = {}
        self.late_dividends_done: Set[Tuple[str, int]] = set()
        self.seen_signals: Set[str] = set()
        self.awaiting_outcome: List[PaperPosition] = []
        self.applied_splits: Set[Tuple[str, int]] = set()
        self.bh_eve_units: Dict[Tuple[str, int], float] = {}
        self.bh_dividend_settled: Dict[Tuple[str, int], bool] = {}
        self.bh_late_done: Set[Tuple[str, int]] = set()
        self.cancelled_closing = False
        self.unrunnable_done = False
        self.counters: Dict[str, int] = {}
        self.notional = 0.0
        self.fees = 0.0
        self.slippage = 0.0
        self.dividends = 0.0
        self.seq = 0
        self.position_seq = 0
        self.last_key: Optional[EventKey] = None
        self._view: Optional[EngineView] = None
        self._result = AdvanceResult()
        self._cash_at_start = self.cash

    # ------------------------------------------------------------------ utilidades

    def count(self, name: str) -> None:
        self.counters[name] = self.counters.get(name, 0) + 1

    @property
    def view(self) -> EngineView:
        assert self._view is not None
        return self._view

    def equity(self, at: datetime) -> float:
        fx = self.view.fx
        total = self.cash
        if self.spec.kind == KIND_BENCHMARK:
            # Mismo orden de suma que ``p6_sim.simulate_benchmark`` (equivalencia bit a bit).
            return self.cash + sum(h.units * h.mark_price * fx.quote(h.currency, at).rate_to_eur for h in self.holdings.values())
        for position in self.positions.values():
            total += position.units * position.mark_price * fx.quote(position.currency, at).rate_to_eur
        return total

    def _late_processing(self, at: datetime) -> int:
        late_before = self.view.late_before
        return int(late_before is not None and at < late_before)

    def write(self, at: datetime, phase: str, event_type: str, *, late: bool = False, **fields: Any) -> None:
        self.seq += 1
        row: Dict[str, Any] = dict.fromkeys(ROW_COLUMNS, "")
        row.update(
            {
                "seq": self.seq,
                "timestamp_utc": utc_iso(at),
                "fase": phase,
                "system_sha256": self.spec.system_sha256,
                "policy_id": self.spec.policy_id,
                "event_type": event_type,
                "receivable_after": 0.0,
                "equity_after": self.equity(at),
                "late": int(late),
                "late_processing": self._late_processing(at),
            }
        )
        row.update(fields)
        if self.cash < -ACCOUNTING_TOLERANCE_EUR:
            raise AccountingError(f"cash negativo ({self.cash}) en {utc_iso(at)}")
        self._result.rows.append(row)

    def position_event(self, at: datetime, phase: str, position: PaperPosition, event_type: str, **fields: Any) -> None:
        self._result.position_events.append(
            {
                "position_id": position.position_id,
                "asset": position.asset,
                "event_type": event_type,
                "event_ts_utc": utc_iso(at),
                "phase": phase,
                "late_processing": self._late_processing(at),
                **fields,
            }
        )

    # ------------------------------------------------------------------ avance

    def _events(self) -> List[_Event]:
        view = self.view
        events: List[_Event] = []
        for symbol in sorted(view.assets):
            series = view.assets[symbol]
            key = f"{series.meta.market}|{symbol}"
            for i, day in enumerate(series.session_dates):
                if day < view.start:
                    continue
                events.append(_Event(series.open_utc[i], OPEN_EXIT, key, symbol, i))
                events.append(_Event(series.open_utc[i], OPEN_ENTRY, key, symbol, i))
                events.append(_Event(series.close_utc[i], CLOSE_EXIT, key, symbol, i))
                events.append(_Event(series.close_utc[i], CLOSE_DIVIDEND, key, symbol, i))
                events.append(_Event(series.close_utc[i], CLOSE_VALUATION, key, symbol, i))
        for day in view.snapshot_days:
            if day >= view.start:
                events.append(_Event(datetime.combine(day, SNAPSHOT_TIME, timezone.utc), SNAPSHOT, "", day=day))
        if self.spec.kind == KIND_POLICY:
            late: List[str] = []
            for signal in sorted(view.signals, key=lambda item: (item.analysis_ts, item.signal_id)):
                if signal.signal_id in self.seen_signals:
                    continue
                series_opt = view.assets.get(signal.asset)
                if series_opt is None:
                    raise ValueError(f"{signal.signal_id}: activo {signal.asset} ausente")
                event = _Event(signal.analysis_ts, SIGNAL, tiebreak_key(signal.signal_id), signal.asset, signal.bar_index, signal)
                if self.last_key is not None and event.sort_key() <= self.last_key:
                    # Una señal vinculante nunca puede llegar detrás de la frontera (la ejecución solo avanza
                    # hasta la hora programada de su pasada): si ocurre, no se procesa y se informa.
                    late.append(signal.signal_id)
                    continue
                series = series_opt
                entry_index = signal.bar_index + 1
                if entry_index < len(series.session_dates):
                    if not (series.close_utc[signal.bar_index] <= signal.analysis_ts < series.open_utc[entry_index]):
                        raise ValueError(f"{signal.signal_id}: analysis_timestamp fuera de [cierre t, apertura t+1)")
                elif not series.close_utc[signal.bar_index] <= signal.analysis_ts:
                    raise ValueError(f"{signal.signal_id}: analysis_timestamp anterior al cierre de t")
                if entry_index < len(series.session_dates) and series.session_dates[entry_index] < view.start:
                    continue
                events.append(event)
            self._result.late_signals = tuple(late)
        if self.last_key is not None:
            events = [event for event in events if event.sort_key() > self.last_key]
        events.sort(key=lambda event: event.sort_key())
        return events

    def _constrained(self) -> Set[str]:
        if self.spec.kind == KIND_BENCHMARK:
            return {asset for asset in self.view.assets if asset not in self.first_buy_done} | set(self.holdings)
        return set(self.positions) | set(self.pending)

    def _horizon(self) -> Tuple[Optional[datetime], Tuple[str, ...]]:
        limits: List[Tuple[datetime, str]] = []
        for asset in self._constrained():
            series = self.view.assets.get(asset)
            if series is not None and series.horizon is not None:
                limits.append((series.horizon, asset))
        if not limits:
            return None, ()
        first = min(at for at, _asset in limits)
        return first, tuple(sorted(asset for at, asset in limits if at == first))

    def _fx_ready(self, at: datetime, extra: Sequence[str] = ()) -> bool:
        view = self.view
        if view.fx_horizon is not None and at >= view.fx_horizon:
            return False
        currencies = {p.currency for p in self.positions.values()} | {h.currency for h in self.holdings.values()}
        currencies.update(extra)
        try:
            for currency in currencies:
                view.fx.quote(currency, at)
        except FxUnavailableError:
            return False
        return True

    def advance(self, view: EngineView) -> AdvanceResult:
        """Procesa los eventos nuevos hasta el primer instante sin información completa."""

        self._view = view
        self._result = AdvanceResult()
        self._cash_at_start = self.cash
        if view.unrunnable:
            self._unrunnable()
            self._result.stop_reason = STOP_UNRUNNABLE
            self._result.frontier = self.last_key
            return self._result
        self._apply_data_loss_flags()
        events = self._events()
        position = 0
        while position < len(events):
            event = events[position]
            if event.at >= view.limit:
                # El límite es la hora programada de la pasada, exclusiva: la señal de esa pasada se procesa en
                # la ejecución siguiente, cuando ya se sabe si es la vinculante (§7.1).
                self._result.stop_reason = STOP_LIMIT
                break
            horizon, stalled = self._horizon()
            if horizon is not None and event.at >= horizon:
                self._result.stop_reason = STOP_HORIZON
                self._result.stalled_on = stalled
                break
            if event.phase == OPEN_ENTRY:
                batch: List[_Event] = []
                cursor = position
                while cursor < len(events) and events[cursor].phase == OPEN_ENTRY and events[cursor].at == event.at:
                    batch.append(events[cursor])
                    cursor += 1
                needed = [view.assets[item.asset].meta.currency for item in batch]
                if not self._fx_ready(event.at, needed):
                    self._result.stop_reason = STOP_FX
                    break
                self._before_event(event)
                if self.spec.kind == KIND_BENCHMARK:
                    for item in batch:
                        self._bh_entry(item)
                else:
                    self._process_entries(batch, event.at)
                self.last_key = batch[-1].sort_key()
                position = cursor
                continue
            extra = [view.assets[event.asset].meta.currency] if event.asset else []
            if not self._fx_ready(event.at, extra):
                self._result.stop_reason = STOP_FX
                break
            self._before_event(event)
            self._dispatch(event)
            self.last_key = event.sort_key()
            position += 1
        self._emit_outcomes()
        self._check_identities()
        self._result.frontier = self.last_key
        return self._result

    def _check_identities(self) -> None:
        """Identidades contables de P6 §19 en cada avance: el cash encadena con los flujos de cada fila y el
        cash final es el del libro; ``cash ≥ 0``. Si falla, la ejecución aborta (§12)."""

        final = check_ledger_flows(self._result.rows, self._cash_at_start)
        if abs(final - self.cash) > ACCOUNTING_TOLERANCE_EUR * max(1.0, len(self._result.rows)):
            raise AccountingError(f"cash del libro {self.cash} ≠ cash del ledger {final}")
        if self.cash < -ACCOUNTING_TOLERANCE_EUR:
            raise AccountingError(f"cash negativo ({self.cash})")
        if self.spec.kind == KIND_POLICY:
            # V_T − V_0 sobre lo realizado: cash − capital = Σ P&L bruto cerrado + dividendos − comisiones −
            # coste de lo abierto (P6 §19, en cada avance y no solo al final de una ventana).
            closed = sum(p.units * ((p.exit_eff or 0.0) * (p.fx_exit or 0.0) - p.entry_eff * p.fx_entry) for p in self.closed)
            open_cost = sum(p.units * p.entry_eff * p.fx_entry for p in self.positions.values())
            expected = self.spec.capital + closed + self.dividends - self.fees - open_cost
            tolerance = ACCOUNTING_TOLERANCE_EUR * max(1.0, len(self.closed) + len(self.positions)) * 10
            if abs(self.cash - expected) > tolerance:
                raise AccountingError(f"V_T − V_0 no cuadra: cash {self.cash} ≠ {expected}")

    def _emit_outcomes(self) -> None:
        """El desenlace de una posición cerrada se fija cuando ya no le queda ningún dividendo con derecho por
        abonar (P6 abona al cierre ex el derecho de una posición que salió en la apertura ex)."""

        owed = {id(held) for entries in self.entitlements.values() for held, _dividend in entries}
        waiting: List[PaperPosition] = []
        for position in self.awaiting_outcome:
            if id(position) in owed:
                waiting.append(position)
            else:
                self._result.outcomes.append(outcome_of(position))
        self.awaiting_outcome = waiting

    # ------------------------------------------------------------------ eventos

    def _before_event(self, event: _Event) -> None:
        if self.spec.kind == KIND_POLICY:
            self._late_splits(event)
            self._terminal_exits(event)
        closing_at = self.view.closing_at
        if closing_at is not None and event.at >= closing_at and not self.cancelled_closing:
            self.cancelled_closing = True
            for asset in sorted(self.pending):
                signal = self.pending.pop(asset)
                series = self.view.assets[asset]
                self.count(CANCELLED_COHORT_CLOSING)
                self.write(
                    event.at, event.phase, "ORDER_CANCELLED", market=series.meta.market, asset=asset,
                    session_date=str(series.session_dates[signal.bar_index]), signal_id=signal.signal_id,
                    cash_before=self.cash, cash_after=self.cash, currency=series.meta.currency,
                    reason=CANCELLED_COHORT_CLOSING,
                )
            for held in sorted(self.positions.values(), key=lambda item: item.position_id):
                if held.suspended and not held.non_evaluable:
                    held.non_evaluable = EV_NO_EVALUABLE_DATA_LOSS
                    self.position_event(event.at, event.phase, held, EV_NO_EVALUABLE_DATA_LOSS)

    def _dispatch(self, event: _Event) -> None:
        if self.spec.kind == KIND_BENCHMARK:
            self._bh_dispatch(event)
            return
        if event.phase == OPEN_EXIT:
            self._open_exit(event)
        elif event.phase == CLOSE_EXIT:
            self._close_exit(event)
        elif event.phase == CLOSE_DIVIDEND:
            self._dividend(event)
        elif event.phase == CLOSE_VALUATION:
            held = self.positions.get(event.asset)
            if held is not None:
                held.mark_price = self.view.assets[event.asset].close[event.index]
        elif event.phase == SIGNAL:
            assert event.signal is not None
            self._signal(event.signal)
        elif event.phase == SNAPSHOT:
            assert event.day is not None
            self._snapshot(event.day, event.at)

    def _signal(self, signal: Signal) -> None:
        self.seen_signals.add(signal.signal_id)
        series = self.view.assets[signal.asset]
        common: Dict[str, Any] = dict(
            market=series.meta.market, asset=signal.asset, session_date=str(series.session_dates[signal.bar_index]),
            signal_id=signal.signal_id, cash_before=self.cash, cash_after=self.cash, currency=series.meta.currency,
        )
        closing_at = self.view.closing_at
        if closing_at is not None and signal.analysis_ts >= closing_at:
            self.count(IGNORED_COHORT_CLOSING)
            self.write(signal.analysis_ts, SIGNAL, "SIGNAL_IGNORED", reason=IGNORED_COHORT_CLOSING, **common)
            return
        if signal.asset in self.positions:
            self.count(IGNORED_ALREADY_OPEN)
            self.write(signal.analysis_ts, SIGNAL, "SIGNAL_IGNORED", reason=IGNORED_ALREADY_OPEN, **common)
            return
        if signal.asset in self.pending:
            raise AccountingError(f"{signal.asset}: dos órdenes pendientes a la vez")
        self.pending[signal.asset] = signal
        self.count("senales_pendientes")
        self.write(signal.analysis_ts, SIGNAL, "SIGNAL_PENDING", reason="ORDEN_PARA_APERTURA_SIGUIENTE", **common)

    def _process_entries(self, batch: List[_Event], at: datetime) -> None:
        candidates = []
        for event in batch:
            signal = self.pending.get(event.asset)
            if signal is not None and signal.bar_index + 1 == event.index:
                del self.pending[event.asset]
                candidates.append((tiebreak_key(signal.signal_id), signal, event))
            elif signal is not None and signal.bar_index + 1 < event.index:
                raise AccountingError(f"{signal.signal_id}: orden pendiente no ejecutada en su apertura")
        if not candidates:
            return
        candidates.sort(key=lambda item: item[0])
        equity = self.equity(at)
        spec = self.spec
        for _key, signal, event in candidates:
            series = self.view.assets[signal.asset]
            i = event.index
            ratio = series.splits.get(i, 1.0)
            stop, target2, entry_max = signal.stop / ratio, signal.target2 / ratio, signal.entry_max / ratio
            market_open = series.open[i]
            eff = market_open * (1.0 + spec.slip)
            quote = self.view.fx.quote(series.meta.currency, at)
            reason = market_check(market_open, eff, stop, target2, entry_max, spec.min_rr)
            units = 0.0
            required: Any = ""
            if reason == ENTRY_OK:
                risk_unit_eur = (eff - stop) * quote.rate_to_eur
                units_risk = equity * spec.risk_pct / 100.0 / risk_unit_eur
                units_cap = equity * spec.max_position_pct / 100.0 / (eff * quote.rate_to_eur)
                units = min(units_risk, units_cap)
                if not (units > 0 and math.isfinite(units)):
                    reason = POSITION_TOO_SMALL
                else:
                    required = units * eff * quote.rate_to_eur * (1.0 + spec.fee_rate)
                    if float(required) > self.cash + ACCOUNTING_TOLERANCE_EUR:
                        reason = INSUFFICIENT_CASH
            common: Dict[str, Any] = dict(
                market=series.meta.market, asset=signal.asset, session_date=str(series.session_dates[i]),
                signal_id=signal.signal_id, currency=series.meta.currency, market_price=market_open, effective_price=eff,
                fx_pair=quote.pair, fx_rate=quote.rate_to_eur, fx_timestamp_available=utc_iso(quote.available_at),
                stop=stop, target2=target2, cash_requerido_base=required,
            )
            if reason != ENTRY_OK:
                self.count(reason)
                self.write(at, OPEN_ENTRY, "ENTRY_REJECTED", cash_before=self.cash, cash_after=self.cash, reason=reason, **common)
                continue
            notional_eur = units * eff * quote.rate_to_eur
            fee_eur = notional_eur * spec.fee_rate
            slip_eur = units * (eff - market_open) * quote.rate_to_eur
            cash_before = self.cash
            self.cash -= notional_eur + fee_eur
            if -ACCOUNTING_TOLERANCE_EUR < self.cash < 0:
                self.cash = 0.0
            self.notional += notional_eur
            self.fees += fee_eur
            self.slippage += slip_eur
            self.position_seq += 1
            held = PaperPosition(
                position_id=f"{spec.policy_id}-{self.position_seq:06d}", asset=signal.asset, signal_id=signal.signal_id,
                currency=series.meta.currency, entry_index=i, entry_ts=at, units=units, stop=stop, target2=target2,
                market_entry=market_open, entry_eff=eff, fx_entry=quote.rate_to_eur, fee_entry_eur=fee_eur,
                fee_entry_local=units * eff * spec.fee_rate, slippage_entry_eur=slip_eur, mark_price=eff,
            )
            self.positions[signal.asset] = held
            self.count("entradas")
            self.write(
                at, OPEN_ENTRY, "ENTRY", position_id=held.position_id, cash_before=cash_before, cash_after=self.cash,
                units_before=0.0, units_after=units, notional_base=notional_eur, fee_base=fee_eur, slippage_base=slip_eur,
                reason=ENTRY_OK, **common,
            )
            self.position_event(at, OPEN_ENTRY, held, EV_OPEN, units_after=units, effective_price=eff)

    def _late_splits(self, event: _Event) -> None:
        """Un split observado después de procesar su apertura ex se aplica en la frontera, marcado ``late``,
        sin reescribir nada (§8.6, §12). Lo normal es que la barra ex espere al split (escala dudosa en la
        ingesta), así que este camino es la red de seguridad."""

        for held in sorted(self.positions.values(), key=lambda item: item.position_id):
            series = self.view.assets[held.asset]
            key = f"{series.meta.market}|{held.asset}"
            for index in sorted(series.splits):
                if (held.asset, index) in self.applied_splits or index <= held.entry_index:
                    continue
                if index >= len(series.open_utc) or self.last_key is None:
                    continue
                if (series.open_utc[index], PHASE_RANK[OPEN_EXIT], key) <= self.last_key:
                    self._split_adjust(held, _Event(event.at, event.phase, key, held.asset, index), late=True)

    def _split_adjust(self, held: PaperPosition, event: _Event, *, late: bool = False) -> None:
        series = self.view.assets[event.asset]
        ratio = series.splits.get(event.index)
        if ratio is None or held.entry_index >= event.index or (event.asset, event.index) in self.applied_splits:
            return
        self.applied_splits.add((event.asset, event.index))
        before = held.units
        held.units *= ratio
        for name in ("stop", "target2", "entry_eff", "market_entry", "mark_price"):
            setattr(held, name, getattr(held, name) / ratio)
        held.min_low /= ratio
        held.max_high /= ratio
        held.split_factor *= ratio
        self.write(
            event.at, event.phase if late else OPEN_EXIT, "SPLIT_ADJUST", late=late, market=series.meta.market, asset=event.asset,
            session_date=str(series.session_dates[event.index]), signal_id=held.signal_id, position_id=held.position_id,
            cash_before=self.cash, cash_after=self.cash, units_before=before, units_after=held.units,
            currency=held.currency, reason=f"SPLIT_{ratio:g}", stop=held.stop, target2=held.target2,
        )
        self.position_event(event.at, OPEN_EXIT, held, EV_SPLIT_ADJUST, units_before=before, units_after=held.units, ratio=ratio,
                            late=int(late))

    def _track_range(self, held: PaperPosition, series: AssetView, i: int) -> None:
        held.min_low = min(held.min_low, series.low[i])
        held.max_high = max(held.max_high, series.high[i])

    def _open_exit(self, event: _Event) -> None:
        held = self.positions.get(event.asset)
        if held is None or held.entry_index >= event.index:
            return
        series = self.view.assets[event.asset]
        i = event.index
        self._split_adjust(held, event)
        if held.suspended:
            held.suspended = False
            self.position_event(event.at, OPEN_EXIT, held, EV_DATA_RESUMED)
        if held.non_evaluable:
            return
        self.eve_units.setdefault((event.asset, i), []).append((held, held.units))
        dividend = series.dividends.get(i, 0.0)
        if dividend > 0:
            self.entitlements.setdefault((event.asset, i), []).append((held, dividend))
        bar_open, bar_low = series.open[i], series.low[i]
        closing_at = self.view.closing_at
        if bar_open <= held.stop:
            self._track_range(held, series, i)
            self._exit(held, event.at, OPEN_EXIT, i, bar_open, EXIT_STOP)
        elif bar_open >= held.target2 and bar_low > held.stop:
            self._track_range(held, series, i)
            self._exit(held, event.at, OPEN_EXIT, i, bar_open, EXIT_TARGET)
        elif closing_at is not None and event.at >= closing_at:
            self._track_range(held, series, i)
            self._exit(held, event.at, OPEN_EXIT, i, bar_open, EXIT_COHORT_CLOSED)

    def _close_exit(self, event: _Event) -> None:
        held = self.positions.get(event.asset)
        if held is None or held.non_evaluable:
            return
        series = self.view.assets[event.asset]
        i = event.index
        if held.entry_index > i:
            return
        self._track_range(held, series, i)
        if series.low[i] <= held.stop:
            self._exit(held, event.at, CLOSE_EXIT, i, held.stop, EXIT_STOP)
        elif series.high[i] >= held.target2:
            self._exit(held, event.at, CLOSE_EXIT, i, held.target2, EXIT_TARGET)
        elif i - held.entry_index >= self.spec.max_hold_bars:
            self._exit(held, event.at, CLOSE_EXIT, i, series.close[i], EXIT_TIME)

    def _terminal_exits(self, event: _Event) -> None:
        """Salida real verificable (§8.7): al precio de liquidación, con comisión y sin slippage, en el primer
        evento procesado en o después de su fecha efectiva. El precio está en la escala vigente en esa fecha."""

        for held in sorted(self.positions.values(), key=lambda item: item.position_id):
            series = self.view.assets[held.asset]
            if series.terminal is None or series.terminal[0] > event.at or not series.session_dates:
                continue
            held.non_evaluable = ""
            held.suspended = False
            index = len(series.session_dates) - 1
            late = series.terminal[0] < event.at
            self._exit(held, event.at, event.phase, index, series.terminal[1], EXIT_CORPORATE_ACTION, slippage=False, late=late)

    def _exit(self, position: PaperPosition, at: datetime, phase: str, index: int, market_price: float, reason: str,
              *, slippage: bool = True, late: bool = False) -> None:
        series = self.view.assets[position.asset]
        quote = self.view.fx.quote(position.currency, at)
        eff = market_price * (1.0 - self.spec.slip) if slippage else market_price
        gross_eur = position.units * eff * quote.rate_to_eur
        fee_eur = position.units * eff * self.spec.fee_rate * quote.rate_to_eur
        slip_eur = position.units * (market_price - eff) * quote.rate_to_eur
        cash_before = self.cash
        self.cash += gross_eur - fee_eur
        self.notional += gross_eur
        self.fees += fee_eur
        self.slippage += slip_eur
        pnl_bruto = position.units * (eff * quote.rate_to_eur - position.entry_eff * position.fx_entry)
        position.exit_ts = at
        position.exit_index = index
        position.exit_reason = reason
        position.market_exit = market_price
        position.exit_eff = eff
        position.fx_exit = quote.rate_to_eur
        position.fee_exit_eur = fee_eur
        position.fee_exit_local = position.units * eff * self.spec.fee_rate
        position.slippage_exit_eur = slip_eur
        del self.positions[position.asset]
        self.closed.append(position)
        self.count(f"salida_{reason}")
        self.write(
            at, phase, "EXIT", late=late, market=series.meta.market, asset=position.asset, session_date=str(series.session_dates[index]),
            signal_id=position.signal_id, position_id=position.position_id, cash_before=cash_before, cash_after=self.cash,
            units_before=position.units, units_after=0.0, market_price=market_price, effective_price=eff,
            currency=position.currency, fx_pair=quote.pair, fx_rate=quote.rate_to_eur,
            fx_timestamp_available=utc_iso(quote.available_at), notional_base=gross_eur, fee_base=fee_eur,
            slippage_base=slip_eur, realized_pnl_base=pnl_bruto - position.fee_entry_eur - fee_eur, reason=reason,
        )
        self.position_event(at, phase, position, EV_EXIT, reason=reason, effective_price=eff)
        self.awaiting_outcome.append(position)

    def _dividend(self, event: _Event) -> None:
        series = self.view.assets[event.asset]
        key = (event.asset, event.index)
        entries = self.entitlements.pop(key, [])
        dividend_now = series.dividends.get(event.index, 0.0)
        self.dividend_settled[key] = dividend_now > 0
        for held, dividend in entries:
            self._credit(held, dividend, held.units, event, late=False)
        if not entries and dividend_now > 0 and key not in self.late_dividends_done:
            # Conocido después de procesar su apertura ex (la frontera se detuvo a mitad de la barra): mismo
            # derecho, con las unidades de la víspera, marcado ``late``.
            self.late_dividends_done.add(key)
            for held, units in self.eve_units.get(key, []):
                self._credit(held, dividend_now, units, event, late=True)
        self._late_dividends(event)

    def _late_dividends(self, event: _Event) -> None:
        """Dividendos conocidos después de procesar su cierre ex: se abonan al cierre de la primera sesión
        del activo procesada después de conocerlos, marcados ``late``, sin reescribir nada (§8.5, D-75)."""

        series = self.view.assets[event.asset]
        for index, dividend in sorted(series.dividends.items()):
            key = (event.asset, index)
            if index >= event.index or key in self.late_dividends_done or self.dividend_settled.get(key, True):
                continue
            if dividend <= 0:
                continue
            self.late_dividends_done.add(key)
            for held, units in self.eve_units.get(key, []):
                # Mismo valor económico que en su fecha ex: unidades y precio en la escala de aquella sesión.
                self._credit(held, dividend, units, event, late=True)

    def _credit(self, held: PaperPosition, dividend: float, units: float, event: _Event, *, late: bool) -> None:
        series = self.view.assets[event.asset]
        quote = self.view.fx.quote(held.currency, event.at)
        amount_local = units * dividend
        amount_eur = amount_local * quote.rate_to_eur
        cash_before = self.cash
        self.cash += amount_eur
        self.dividends += amount_eur
        held.dividends_local += amount_local
        held.dividends_eur += amount_eur
        self.count("dividendos_abonados")
        self.write(
            event.at, CLOSE_DIVIDEND, "DIVIDEND", late=late, market=series.meta.market, asset=event.asset,
            session_date=str(series.session_dates[event.index]), signal_id=held.signal_id,
            position_id=held.position_id, cash_before=cash_before, cash_after=self.cash, units_before=held.units,
            units_after=held.units if event.asset in self.positions else 0.0, market_price=dividend,
            currency=held.currency, fx_pair=quote.pair, fx_rate=quote.rate_to_eur,
            fx_timestamp_available=utc_iso(quote.available_at), dividend_base=amount_eur, reason="DIVIDENDO_BRUTO",
        )
        self.position_event(event.at, CLOSE_DIVIDEND, held, EV_DIVIDEND_CREDIT, late=int(late), dividend_eur=amount_eur)

    def _snapshot(self, day: date, at: datetime) -> None:
        by_region: Dict[str, float] = {}
        by_currency: Dict[str, float] = {}
        by_economic: Dict[str, float] = {}
        by_sector: Dict[str, float] = {}
        long_value = 0.0
        if self.spec.kind == KIND_BENCHMARK:
            long_value = sum(h.units * h.mark_price * self.view.fx.quote(h.currency, at).rate_to_eur for h in self.holdings.values())
            count = len(self.holdings)
        stale = 0.0
        if self.spec.kind != KIND_BENCHMARK:
            for held in self.positions.values():
                meta = self.view.assets[held.asset].meta
                value = held.units * held.mark_price * self.view.fx.quote(held.currency, at).rate_to_eur
                long_value += value
                if held.suspended or held.non_evaluable:
                    stale += value
                for bucket, name in ((by_region, meta.region), (by_currency, meta.currency),
                                     (by_economic, meta.economic_currency), (by_sector, meta.sector)):
                    bucket[name] = bucket.get(name, 0.0) + value
            count = len(self.positions)
        self._result.snapshots.append(
            Snapshot(day=day, at=at, equity=self.cash + long_value, cash=self.cash, long_value=long_value,
                     positions=count, by_region=by_region, by_currency=by_currency,
                     by_economic_currency=by_economic, by_sector=by_sector)
        )
        self._result.stale_values.append(stale)

    def _apply_data_loss_flags(self) -> None:
        if self.last_key is None:
            return
        at = self.last_key[0]
        for held in sorted(self.positions.values(), key=lambda item: item.position_id):
            series = self.view.assets.get(held.asset)
            if series is not None and series.data_loss and not held.suspended and not held.non_evaluable:
                held.suspended = True
                self.position_event(at, "FRONTIER", held, EV_DATA_LOSS_SUSPENDED)

    def _unrunnable(self) -> None:
        """``ENGINE_UNRUNNABLE`` (D-78): desde el último evento válido, órdenes canceladas y posiciones
        abiertas ``NO_EVALUABLE``; sin salidas fabricadas ni P&L inventado."""

        if self.unrunnable_done:
            return
        self.unrunnable_done = True
        at = self.last_key[0] if self.last_key is not None else datetime.combine(self.view.start, SNAPSHOT_TIME, timezone.utc)
        for asset in sorted(self.pending):
            signal = self.pending.pop(asset)
            series = self.view.assets[asset]
            self.count(CANCELLED_ENGINE_UNRUNNABLE)
            self.write(
                at, "UNRUNNABLE", "ORDER_CANCELLED", market=series.meta.market, asset=asset,
                session_date=str(series.session_dates[signal.bar_index]), signal_id=signal.signal_id,
                cash_before=self.cash, cash_after=self.cash, currency=series.meta.currency,
                reason=CANCELLED_ENGINE_UNRUNNABLE,
            )
        for held in sorted(self.positions.values(), key=lambda item: item.position_id):
            if not held.non_evaluable:
                held.non_evaluable = EV_NO_EVALUABLE_ENGINE_UNRUNNABLE
                self.position_event(at, "UNRUNNABLE", held, EV_NO_EVALUABLE_ENGINE_UNRUNNABLE)

    # ------------------------------------------------------------------ benchmark (P6 §14)

    def _bh_dispatch(self, event: _Event) -> None:
        series: Optional[AssetView] = self.view.assets.get(event.asset) if event.asset else None
        if event.phase == OPEN_EXIT and series is not None:
            held = self.holdings.get(event.asset)
            dividend = series.dividends.get(event.index, 0.0)
            if held is not None:
                self.bh_eve_units[(event.asset, event.index)] = held.units
            if held is not None and dividend > 0:
                self.bh_entitlements[(event.asset, event.index)] = held.units * dividend
        elif event.phase == CLOSE_DIVIDEND and series is not None:
            key = (event.asset, event.index)
            amount_local = self.bh_entitlements.pop(key, 0.0)
            dividend_now = series.dividends.get(event.index, 0.0)
            self.bh_dividend_settled[key] = dividend_now > 0
            if amount_local > 0:
                self._bh_credit(series, event, amount_local, late=False)
            elif dividend_now > 0 and key in self.bh_eve_units and key not in self.bh_late_done:
                self.bh_late_done.add(key)
                self._bh_credit(series, event, self.bh_eve_units[key] * dividend_now, late=True)
            for index, dividend in sorted(series.dividends.items()):
                late_key = (event.asset, index)
                if index >= event.index or dividend <= 0 or late_key in self.bh_late_done:
                    continue
                if self.bh_dividend_settled.get(late_key, True) or late_key not in self.bh_eve_units:
                    continue
                self.bh_late_done.add(late_key)
                self._bh_credit(series, event, self.bh_eve_units[late_key] * dividend, late=True)
        elif event.phase == CLOSE_VALUATION and series is not None:
            held = self.holdings.get(event.asset)
            if held is not None:
                held.mark_price = series.close[event.index]
        elif event.phase == SNAPSHOT:
            assert event.day is not None
            self._snapshot(event.day, event.at)

    def _bh_credit(self, series: AssetView, event: _Event, amount_local: float, *, late: bool) -> None:
        quote = self.view.fx.quote(series.meta.currency, event.at)
        amount_eur = amount_local * quote.rate_to_eur
        cash_before = self.cash
        self.cash += amount_eur
        self.dividends += amount_eur
        self.reinvest[event.asset] = self.reinvest.get(event.asset, 0.0) + amount_eur
        self.write(
            event.at, CLOSE_DIVIDEND, "BH_DIVIDEND", late=late, market=series.meta.market, asset=event.asset,
            session_date=str(series.session_dates[event.index]), cash_before=cash_before, cash_after=self.cash,
            currency=series.meta.currency, fx_pair=quote.pair, fx_rate=quote.rate_to_eur,
            fx_timestamp_available=utc_iso(quote.available_at), dividend_base=amount_eur, reason="DIVIDENDO_BRUTO",
        )

    def _bh_entry(self, event: _Event) -> None:
        if event.asset not in self.first_buy_done:
            self.first_buy_done.add(event.asset)
            self._bh_buy(event.asset, event.index, event.at, self.spec.capital / self.spec.universe_size, "BH_COMPRA_INICIAL")
        amount = self.reinvest.pop(event.asset, 0.0)
        if amount > 0:
            self._bh_buy(event.asset, event.index, event.at, amount, "BH_REINVERSION_DIVIDENDO")

    def _bh_buy(self, symbol: str, index: int, at: datetime, amount_eur: float, reason: str) -> None:
        series = self.view.assets[symbol]
        spec = self.spec
        quote = self.view.fx.quote(series.meta.currency, at)
        market_open = series.open[index]
        eff = market_open * (1.0 + spec.slip)
        notional = amount_eur / (1.0 + spec.fee_rate)
        fee = amount_eur - notional
        units = notional / (eff * quote.rate_to_eur)
        cash_before = self.cash
        self.cash -= amount_eur
        if abs(self.cash) < ACCOUNTING_TOLERANCE_EUR:
            self.cash = 0.0
        self.notional += notional
        self.fees += fee
        self.slippage += units * (eff - market_open) * quote.rate_to_eur
        held = self.holdings.get(symbol)
        before = held.units if held else 0.0
        if held is None:
            self.holdings[symbol] = _Holding(symbol, series.meta.currency, units, eff)
        else:
            held.units += units
        self.write(
            at, OPEN_ENTRY, "BH_BUY", market=series.meta.market, asset=symbol, session_date=str(series.session_dates[index]),
            cash_before=cash_before, cash_after=self.cash, units_before=before, units_after=before + units,
            market_price=market_open, effective_price=eff, currency=series.meta.currency, fx_pair=quote.pair,
            fx_rate=quote.rate_to_eur, fx_timestamp_available=utc_iso(quote.available_at), notional_base=notional,
            fee_base=fee, slippage_base=units * (eff - market_open) * quote.rate_to_eur, reason=reason,
        )


def market_check(market_open: float, eff: float, stop: float, target2: float, entry_max: float, min_rr: float) -> str:
    """Comprobaciones de mercado de la apertura, en el orden exacto de ``p6_sim._process_entries``.

    No dependen de ningún libro: son la base de ``MARKET_PASS`` (D-78). El sizing y el cash vienen después
    y son internos del libro.
    """

    if not (math.isfinite(market_open) and market_open > 0):
        return DATA_NOT_EXECUTABLE
    if stop >= eff:
        return INVALID_STOP
    if target2 <= eff:
        return INVALID_TARGET
    if eff > entry_max and not math.isclose(eff, entry_max, rel_tol=1e-9):
        return ABOVE_MAX_ENTRY
    if not rr_at_least((target2 - eff) / (eff - stop), min_rr):
        return RR_TOO_LOW
    return ENTRY_OK


def requested_weight(eff: float, stop: float, risk_pct: float = 0.5, max_position_pct: float = 10.0) -> float:
    """Tamaño solicitado como fracción de la equity: no depende de la equity ni del FX (ficha §5, D-78)."""

    return min(risk_pct / 100.0 * eff / (eff - stop), max_position_pct / 100.0)


def outcome_of(position: PaperPosition) -> Outcome:
    trade = _trade(position)
    risk_local = trade.risk_local
    mae = (position.min_low - position.entry_eff) * position.units / risk_local if math.isfinite(position.min_low) else 0.0
    mfe = (position.max_high - position.entry_eff) * position.units / risk_local if math.isfinite(position.max_high) else 0.0
    return Outcome(trade=trade, mae_R=mae, mfe_R=mfe)


# ---------------------------------------------------------------------------- estado persistible (JSON, sin pickle)

_POSITION_DATETIMES = ("entry_ts", "exit_ts")


def _dt(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


def _num(value: float) -> Any:
    return None if not math.isfinite(value) else value


def _position_state(position: PaperPosition) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name in PaperPosition.__dataclass_fields__:
        value = getattr(position, name)
        if isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, float):
            value = _num(value) if name in ("min_low", "max_high") else value
        out[name] = value
    return out


def _position_from(state: Mapping[str, Any]) -> PaperPosition:
    values = dict(state)
    for name in _POSITION_DATETIMES:
        values[name] = _dt(values.get(name))
    values["min_low"] = math.inf if values.get("min_low") is None else values["min_low"]
    values["max_high"] = -math.inf if values.get("max_high") is None else values["max_high"]
    return PaperPosition(**values)


def _signal_state(signal: Signal) -> Dict[str, Any]:
    return {"signal_id": signal.signal_id, "asset": signal.asset, "bar_index": signal.bar_index,
            "analysis_ts": signal.analysis_ts.isoformat(), "stop": signal.stop, "target2": signal.target2,
            "entry_max": signal.entry_max}


def _signal_from(state: Mapping[str, Any]) -> Signal:
    return Signal(state["signal_id"], state["asset"], int(state["bar_index"]), datetime.fromisoformat(state["analysis_ts"]),
                  float(state["stop"]), float(state["target2"]), float(state["entry_max"]))


def engine_to_state(engine: Engine) -> Dict[str, Any]:
    """Estado completo del libro en JSON canónico (tipos explícitos; nunca ``pickle``)."""

    registry: Dict[str, PaperPosition] = {}
    for position in [*engine.positions.values(), *engine.closed, *engine.awaiting_outcome]:
        registry[position.position_id] = position
    for entries in [*engine.entitlements.values(), *engine.eve_units.values()]:
        for position, _value in entries:
            registry[position.position_id] = position

    def pairs(mapping: Mapping[Tuple[str, int], List[Tuple[PaperPosition, float]]]) -> List[Any]:
        return [[asset, index, [[p.position_id, v] for p, v in entries]] for (asset, index), entries in sorted(mapping.items())]

    return {
        "schema": "paper.engine_v1.state.v1",
        "cash": engine.cash,
        "positions_registry": {pid: _position_state(p) for pid, p in sorted(registry.items())},
        # Listas en el orden de inserción: las sumas de equity recorren ese orden (equivalencia bit a bit).
        "open": [[asset, p.position_id] for asset, p in engine.positions.items()],
        "closed": [p.position_id for p in engine.closed],
        "awaiting_outcome": [p.position_id for p in engine.awaiting_outcome],
        "pending": [[asset, _signal_state(s)] for asset, s in engine.pending.items()],
        "holdings": [[a, h.currency, h.units, h.mark_price] for a, h in engine.holdings.items()],
        "first_buy_done": sorted(engine.first_buy_done),
        "reinvest": dict(sorted(engine.reinvest.items())),
        "bh_entitlements": [[a, i, v] for (a, i), v in sorted(engine.bh_entitlements.items())],
        "entitlements": pairs(engine.entitlements),
        "eve_units": pairs(engine.eve_units),
        "dividend_settled": [[a, i, v] for (a, i), v in sorted(engine.dividend_settled.items())],
        "late_dividends_done": sorted([a, i] for a, i in engine.late_dividends_done),
        "seen_signals": sorted(engine.seen_signals),
        "applied_splits": sorted([a, i] for a, i in engine.applied_splits),
        "bh_eve_units": [[a, i, v] for (a, i), v in sorted(engine.bh_eve_units.items())],
        "bh_dividend_settled": [[a, i, v] for (a, i), v in sorted(engine.bh_dividend_settled.items())],
        "bh_late_done": sorted([a, i] for a, i in engine.bh_late_done),
        "cancelled_closing": engine.cancelled_closing,
        "unrunnable_done": engine.unrunnable_done,
        "counters": dict(sorted(engine.counters.items())),
        "totals": [engine.notional, engine.fees, engine.slippage, engine.dividends],
        "seq": engine.seq,
        "position_seq": engine.position_seq,
        "last_key": [engine.last_key[0].isoformat(), engine.last_key[1], engine.last_key[2]] if engine.last_key else None,
    }


def engine_from_state(spec: EngineSpec, state: Mapping[str, Any]) -> Engine:
    if state.get("schema") != "paper.engine_v1.state.v1":
        raise ValueError("estado del motor con un esquema desconocido")
    engine = Engine(spec)
    registry = {pid: _position_from(p) for pid, p in state["positions_registry"].items()}
    engine.cash = float(state["cash"])
    engine.positions = {asset: registry[pid] for asset, pid in state["open"]}
    engine.closed = [registry[pid] for pid in state["closed"]]
    engine.awaiting_outcome = [registry[pid] for pid in state["awaiting_outcome"]]
    engine.pending = {asset: _signal_from(s) for asset, s in state["pending"]}
    engine.holdings = {a: _Holding(a, cur, float(units), float(mark)) for a, cur, units, mark in state["holdings"]}
    engine.first_buy_done = set(state["first_buy_done"])
    engine.reinvest = {a: float(v) for a, v in state["reinvest"].items()}
    engine.bh_entitlements = {(a, int(i)): float(v) for a, i, v in state["bh_entitlements"]}
    engine.entitlements = {(a, int(i)): [(registry[pid], float(v)) for pid, v in e] for a, i, e in state["entitlements"]}
    engine.eve_units = {(a, int(i)): [(registry[pid], float(v)) for pid, v in e] for a, i, e in state["eve_units"]}
    engine.dividend_settled = {(a, int(i)): bool(v) for a, i, v in state["dividend_settled"]}
    engine.late_dividends_done = {(a, int(i)) for a, i in state["late_dividends_done"]}
    engine.seen_signals = set(state["seen_signals"])
    engine.applied_splits = {(a, int(i)) for a, i in state["applied_splits"]}
    engine.bh_eve_units = {(a, int(i)): float(v) for a, i, v in state["bh_eve_units"]}
    engine.bh_dividend_settled = {(a, int(i)): bool(v) for a, i, v in state["bh_dividend_settled"]}
    engine.bh_late_done = {(a, int(i)) for a, i in state["bh_late_done"]}
    engine.cancelled_closing = bool(state["cancelled_closing"])
    engine.unrunnable_done = bool(state["unrunnable_done"])
    engine.counters = {k: int(v) for k, v in state["counters"].items()}
    engine.notional, engine.fees, engine.slippage, engine.dividends = (float(v) for v in state["totals"])
    engine.seq = int(state["seq"])
    engine.position_seq = int(state["position_seq"])
    key = state["last_key"]
    engine.last_key = (datetime.fromisoformat(key[0]), int(key[1]), str(key[2])) if key else None
    engine._cash_at_start = engine.cash
    return engine
