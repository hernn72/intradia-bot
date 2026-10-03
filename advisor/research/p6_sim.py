"""Motor puro de P6 (T-022 / A-06): cartera con capital finito, cronología global y ledger.

Este módulo no lee la cosecha ni ningún fichero: recibe series, señales y FX ya preparados y
devuelve un ledger, una serie diaria y las operaciones. Las reglas son las de T-022 y D-69:

- cartera long only, sin margen ni apalancamiento, cash ≥ 0, unidades fraccionarias;
- sizing sobre la equity causal anterior al lote (0,5 % de riesgo, 10 % máximo por posición);
- una posición por activo; una señal con posición abierta es ``IGNORED_ALREADY_OPEN``;
- entrada en la apertura de la barra siguiente a la señal, con comprobaciones a precio efectivo;
- salidas con la semántica de ``advisor.backtest.engine._check_exit`` (el stop gana si la vela
  toca stop y objetivo; ``target3`` no interviene);
- fases en empate ``OPEN_EXIT < OPEN_ENTRY < CLOSE_EXIT < CLOSE_DIVIDEND < CLOSE_VALUATION <
  SIGNAL`` y desempate de entradas por ``sha256(b"intradia.p6.desempate.v1" + signal_id)``;
- dividendos con derecho al cierre de la víspera de la fecha ex, abonados en el cierre ex;
- FX causal (último tipo con ``timestamp_available < τ``), ``fx_rate_to_EUR = 1 / rate``;
- una sola caja en EUR.

Los datos reales (``MarketData.origin == "real"``) solo se aceptan con una autorización que
comprueba el ``ConfirmatoryToken`` de P6; sin ella el motor se niega a abrir desenlaces.

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from statistics import median
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from advisor.analysis.levels import rr_at_least

ORIGIN_SYNTHETIC = "synthetic"
ORIGIN_REAL = "real"

OPEN_EXIT = "OPEN_EXIT"
OPEN_ENTRY = "OPEN_ENTRY"
CLOSE_EXIT = "CLOSE_EXIT"
CLOSE_DIVIDEND = "CLOSE_DIVIDEND"
CLOSE_VALUATION = "CLOSE_VALUATION"
SIGNAL = "SIGNAL"
SNAPSHOT = "SNAPSHOT"
PHASE_ORDER = (OPEN_EXIT, OPEN_ENTRY, CLOSE_EXIT, CLOSE_DIVIDEND, CLOSE_VALUATION, SIGNAL, SNAPSHOT)
PHASE_RANK = {phase: rank for rank, phase in enumerate(PHASE_ORDER)}

TIEBREAK_PREFIX = b"intradia.p6.desempate.v1"
SNAPSHOT_TIME = time(23, 59, 59)

EXIT_STOP = "stop"
EXIT_TARGET = "objetivo"
EXIT_TIME = "tiempo"
EXIT_FINAL = "final"

ENTRY_OK = "EXECUTABLE"
INVALID_STOP = "INVALID_STOP"
INVALID_TARGET = "INVALID_TARGET"
ABOVE_MAX_ENTRY = "ABOVE_MAX_ENTRY"
RR_TOO_LOW = "RR_TOO_LOW"
POSITION_TOO_SMALL = "POSITION_TOO_SMALL"
DATA_NOT_EXECUTABLE = "DATA_NOT_EXECUTABLE"
INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
IGNORED_ALREADY_OPEN = "IGNORED_ALREADY_OPEN"
OUTSIDE_WINDOW = "OUTSIDE_WINDOW"

LEDGER_COLUMNS = (
    "seq", "timestamp_utc", "fase", "system_sha256", "policy_id", "event_type", "market", "asset",
    "session_date", "signal_id", "position_id", "cash_before", "cash_after", "units_before", "units_after",
    "market_price", "effective_price", "currency", "fx_pair", "fx_rate", "fx_timestamp_available",
    "notional_base", "fee_base", "slippage_base", "dividend_base", "receivable_after", "realized_pnl_base",
    "equity_after", "reason", "stop", "target2", "cash_requerido_base",
)
ACCOUNTING_TOLERANCE_EUR = 1e-6


class P6OutcomeGateError(RuntimeError):
    """Se intentó abrir un desenlace de P6 sin autorización confirmatoria."""


class FxUnavailableError(RuntimeError):
    """No hay ningún tipo FX disponible antes del instante pedido."""


class AccountingError(RuntimeError):
    """Una identidad contable de P6 no cuadra."""


def tiebreak_key(signal_id: str) -> str:
    """Clave de desempate común a todos los sistemas (T-022 §8.3, OD-P6-6 = D)."""

    return hashlib.sha256(TIEBREAK_PREFIX + signal_id.encode("utf-8")).hexdigest()


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def utc_iso(value: Optional[datetime]) -> str:
    if value is None:
        return ""
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class AssetSeries:
    """Barras de un activo con sus marcas reales de apertura y cierre en UTC."""

    symbol: str
    market: str
    currency: str
    economic_currency: str
    region: str
    sector: str
    session_dates: Tuple[date, ...]
    open_utc: Tuple[datetime, ...]
    close_utc: Tuple[datetime, ...]
    open: Tuple[float, ...]
    high: Tuple[float, ...]
    low: Tuple[float, ...]
    close: Tuple[float, ...]
    dividends: Tuple[float, ...]
    eligible_from: int = 0

    def __post_init__(self) -> None:
        n = len(self.session_dates)
        for name in ("open_utc", "close_utc", "open", "high", "low", "close", "dividends"):
            if len(getattr(self, name)) != n:
                raise ValueError(f"{self.symbol}: {name} no tiene {n} barras")
        for i in range(n):
            if not self.open_utc[i] < self.close_utc[i]:
                raise ValueError(f"{self.symbol}: apertura no anterior al cierre en la barra {i}")
            if i and not self.close_utc[i - 1] < self.open_utc[i]:
                raise ValueError(f"{self.symbol}: barras solapadas en {i}")

    def window_indices(self, start: date, end: date) -> List[int]:
        return [i for i, day in enumerate(self.session_dates) if start <= day <= end]


@dataclass(frozen=True)
class MarketData:
    assets: Mapping[str, AssetSeries]
    window_start: date
    window_end: date
    origin: str = ORIGIN_SYNTHETIC

    def __post_init__(self) -> None:
        if self.origin not in (ORIGIN_SYNTHETIC, ORIGIN_REAL):
            raise ValueError(f"origen desconocido: {self.origin}")
        if self.window_end < self.window_start:
            raise ValueError("ventana vacía")


@dataclass(frozen=True)
class FxQuote:
    rate_to_eur: float
    pair: str
    rate: Optional[float]
    available_at: Optional[datetime]


class FxTable:
    """Tipos FX causales: para un evento en τ, el último con ``available_at < τ``."""

    def __init__(self, series: Mapping[str, Sequence[Tuple[datetime, float]]], *, base: str = "EUR") -> None:
        self.base = base
        self._series: Dict[str, Tuple[Tuple[datetime, ...], Tuple[float, ...]]] = {}
        for currency, points in series.items():
            ordered = sorted(points, key=lambda item: item[0])
            stamps = tuple(item[0] for item in ordered)
            rates = tuple(float(item[1]) for item in ordered)
            if any(rate <= 0 or not math.isfinite(rate) for rate in rates):
                raise ValueError(f"{currency}: tipo FX no válido")
            self._series[currency] = (stamps, rates)

    def quote(self, currency: str, at: datetime) -> FxQuote:
        if currency == self.base:
            return FxQuote(1.0, self.base, None, None)
        if currency not in self._series:
            raise FxUnavailableError(f"sin serie FX para {currency}")
        stamps, rates = self._series[currency]
        lo, hi = 0, len(stamps)
        while lo < hi:
            mid = (lo + hi) // 2
            if stamps[mid] < at:
                lo = mid + 1
            else:
                hi = mid
        if lo == 0:
            raise FxUnavailableError(f"sin tipo {currency} disponible antes de {utc_iso(at)}")
        rate = rates[lo - 1]
        return FxQuote(1.0 / rate, f"{self.base}{currency}", rate, stamps[lo - 1])


@dataclass(frozen=True)
class Signal:
    signal_id: str
    asset: str
    bar_index: int
    analysis_ts: datetime
    stop: float
    target2: float
    entry_max: float


@dataclass(frozen=True)
class SimSpec:
    policy_id: str
    system_sha256: str
    capital: float = 100_000.0
    risk_pct: float = 0.5
    max_position_pct: float = 10.0
    fee_rate: float = 0.001
    slippage_bps: float = 5.0
    min_rr: float = 1.5
    max_hold_bars: int = 40

    @property
    def slip(self) -> float:
        return self.slippage_bps / 10_000.0


@dataclass
class Position:
    position_id: str
    asset: str
    signal_id: str
    currency: str
    entry_index: int
    entry_ts: datetime
    units: float
    stop: float
    target2: float
    market_entry: float
    entry_eff: float
    fx_entry: float
    fee_entry_eur: float
    fee_entry_local: float
    slippage_entry_eur: float
    mark_price: float
    exit_ts: Optional[datetime] = None
    exit_index: Optional[int] = None
    exit_reason: Optional[str] = None
    market_exit: Optional[float] = None
    exit_eff: Optional[float] = None
    fx_exit: Optional[float] = None
    fee_exit_eur: float = 0.0
    fee_exit_local: float = 0.0
    slippage_exit_eur: float = 0.0
    dividends_local: float = 0.0
    dividends_eur: float = 0.0


@dataclass(frozen=True)
class Trade:
    position_id: str
    asset: str
    signal_id: str
    currency: str
    entry_ts: str
    exit_ts: str
    exit_reason: str
    bars_held: int
    units: float
    entry_eff: float
    exit_eff: float
    stop: float
    fx_entry: float
    fx_exit: float
    risk_local: float
    pnl_bruto_local: float
    fees_local: float
    dividends_local: float
    pnl_neto_local: float
    trade_R_local: float
    risk_eur: float
    pnl_bruto_eur: float
    fees_eur: float
    dividends_eur: float
    pnl_neto_eur: float
    trade_R_eur: float
    slippage_eur: float
    fx_eur: float


@dataclass
class Snapshot:
    day: date
    at: datetime
    equity: float
    cash: float
    long_value: float
    positions: int
    by_region: Dict[str, float]
    by_currency: Dict[str, float]
    by_economic_currency: Dict[str, float]
    by_sector: Dict[str, float]


@dataclass
class SimResult:
    policy_id: str
    system_sha256: str
    v0: float
    v0_day: date
    ledger: List[Dict[str, Any]]
    snapshots: List[Snapshot]
    trades: List[Trade]
    counters: Dict[str, int]
    notional_traded_eur: float
    fees_eur: float
    slippage_eur: float
    dividends_eur: float


@dataclass(frozen=True)
class _Event:
    at: datetime
    phase: str
    key: str
    asset: str = ""
    index: int = -1
    signal: Optional[Signal] = None
    day: Optional[date] = None

    def sort_key(self) -> Tuple[datetime, int, str]:
        return (self.at, PHASE_RANK[self.phase], self.key)


def _require_authorization(market: MarketData, authorize: Optional[Callable[[], None]]) -> None:
    if market.origin == ORIGIN_REAL:
        if authorize is None:
            raise P6OutcomeGateError("P6: los datos reales solo se simulan con el ConfirmatoryToken de la marca")
        authorize()


def _session_events(market: MarketData) -> List[_Event]:
    events: List[_Event] = []
    days: set[date] = set()
    for symbol in sorted(market.assets):
        series = market.assets[symbol]
        for i in series.window_indices(market.window_start, market.window_end):
            key = f"{series.market}|{symbol}"
            events.append(_Event(series.open_utc[i], OPEN_EXIT, key, symbol, i))
            events.append(_Event(series.open_utc[i], OPEN_ENTRY, key, symbol, i))
            events.append(_Event(series.close_utc[i], CLOSE_EXIT, key, symbol, i))
            events.append(_Event(series.close_utc[i], CLOSE_DIVIDEND, key, symbol, i))
            events.append(_Event(series.close_utc[i], CLOSE_VALUATION, key, symbol, i))
            days.add(series.session_dates[i])
    for day in sorted(days):
        events.append(_Event(datetime.combine(day, SNAPSHOT_TIME, timezone.utc), SNAPSHOT, "", day=day))
    return events


def _last_window_index(series: AssetSeries, end: date) -> Optional[int]:
    candidates = [i for i, day in enumerate(series.session_dates) if day <= end]
    return candidates[-1] if candidates else None


class _Book:
    """Estado de la cartera y escritura del ledger."""

    def __init__(
        self,
        market: MarketData,
        fx: FxTable,
        spec: SimSpec,
        valuer: Optional[Callable[[datetime], float]] = None,
    ) -> None:
        self.valuer = valuer
        self.market = market
        self.fx = fx
        self.spec = spec
        self.cash = spec.capital
        self.positions: Dict[str, Position] = {}
        self.closed: List[Position] = []
        self.ledger: List[Dict[str, Any]] = []
        self.counters: Dict[str, int] = {}
        self.notional = 0.0
        self.fees = 0.0
        self.slippage = 0.0
        self.dividends = 0.0
        self.realized_bruto = 0.0
        self.seq = 0
        self.position_seq = 0

    def count(self, name: str) -> None:
        self.counters[name] = self.counters.get(name, 0) + 1

    def equity(self, at: datetime) -> float:
        if self.valuer is not None:
            return self.valuer(at)
        total = self.cash
        for position in self.positions.values():
            total += position.units * position.mark_price * self.fx.quote(position.currency, at).rate_to_eur
        return total

    def write(self, at: datetime, phase: str, event_type: str, **fields: Any) -> None:
        self.seq += 1
        row: Dict[str, Any] = dict.fromkeys(LEDGER_COLUMNS, "")
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
            }
        )
        row.update(fields)
        if self.cash < -ACCOUNTING_TOLERANCE_EUR:
            raise AccountingError(f"cash negativo ({self.cash}) en {utc_iso(at)}")
        self.ledger.append(row)


def _exit_position(book: _Book, position: Position, at: datetime, phase: str, index: int, market_price: float, reason: str) -> None:
    series = book.market.assets[position.asset]
    quote = book.fx.quote(position.currency, at)
    eff = market_price * (1.0 - book.spec.slip)
    gross_eur = position.units * eff * quote.rate_to_eur
    fee_eur = position.units * eff * book.spec.fee_rate * quote.rate_to_eur
    slip_eur = position.units * (market_price - eff) * quote.rate_to_eur
    cash_before = book.cash
    book.cash += gross_eur - fee_eur
    book.notional += gross_eur
    book.fees += fee_eur
    book.slippage += slip_eur
    pnl_bruto = position.units * (eff * quote.rate_to_eur - position.entry_eff * position.fx_entry)
    book.realized_bruto += pnl_bruto
    position.exit_ts = at
    position.exit_index = index
    position.exit_reason = reason
    position.market_exit = market_price
    position.exit_eff = eff
    position.fx_exit = quote.rate_to_eur
    position.fee_exit_eur = fee_eur
    position.fee_exit_local = position.units * eff * book.spec.fee_rate
    position.slippage_exit_eur = slip_eur
    del book.positions[position.asset]
    book.closed.append(position)
    book.count(f"salida_{reason}")
    book.write(
        at, phase, "EXIT", market=series.market, asset=position.asset, session_date=str(series.session_dates[index]),
        signal_id=position.signal_id, position_id=position.position_id, cash_before=cash_before, cash_after=book.cash,
        units_before=position.units, units_after=0.0, market_price=market_price, effective_price=eff,
        currency=position.currency, fx_pair=quote.pair, fx_rate=quote.rate_to_eur,
        fx_timestamp_available=utc_iso(quote.available_at), notional_base=gross_eur, fee_base=fee_eur,
        slippage_base=slip_eur, realized_pnl_base=pnl_bruto - position.fee_entry_eur - fee_eur, reason=reason,
    )


def simulate(
    market: MarketData,
    signals: Iterable[Signal],
    fx: FxTable,
    spec: SimSpec,
    *,
    authorize: Optional[Callable[[], None]] = None,
) -> SimResult:
    """Simula un sistema completo. Con ``origin == "real"`` exige ``authorize`` (token de la marca)."""

    _require_authorization(market, authorize)
    book = _Book(market, fx, spec)
    events = _session_events(market)
    signal_list = sorted(signals, key=lambda item: (item.analysis_ts, item.signal_id))
    for signal in signal_list:
        series = market.assets.get(signal.asset)
        if series is None:
            raise ValueError(f"{signal.signal_id}: activo {signal.asset} ausente")
        entry_index = signal.bar_index + 1
        if entry_index >= len(series.session_dates):
            book.count("senal_sin_barra_de_entrada")
            continue
        entry_day = series.session_dates[entry_index]
        if not (market.window_start <= entry_day <= market.window_end) or entry_index < series.eligible_from:
            book.count("senal_fuera_de_ventana")
            continue
        if not (series.close_utc[signal.bar_index] <= signal.analysis_ts < series.open_utc[entry_index]):
            raise ValueError(f"{signal.signal_id}: analysis_timestamp fuera de [cierre t, apertura t+1)")
        events.append(_Event(signal.analysis_ts, SIGNAL, tiebreak_key(signal.signal_id), signal.asset, signal.bar_index, signal))
    events.sort(key=lambda event: event.sort_key())

    pending: Dict[str, Signal] = {}
    entitlements: Dict[Tuple[str, int], List[Tuple[Position, float]]] = {}
    last_index = {symbol: _last_window_index(series, market.window_end) for symbol, series in market.assets.items()}
    snapshots: List[Snapshot] = []

    position = 0
    while position < len(events):
        event = events[position]
        if event.phase == OPEN_ENTRY:
            batch = []
            while position < len(events) and events[position].phase == OPEN_ENTRY and events[position].at == event.at:
                batch.append(events[position])
                position += 1
            _process_entries(book, batch, pending, event.at)
            continue
        position += 1
        if event.phase == OPEN_EXIT:
            _process_open_exit(book, event, entitlements)
        elif event.phase == CLOSE_EXIT:
            _process_close_exit(book, event, last_index)
        elif event.phase == CLOSE_DIVIDEND:
            _process_dividend(book, event, entitlements)
        elif event.phase == CLOSE_VALUATION:
            held = book.positions.get(event.asset)
            if held is not None:
                held.mark_price = market.assets[event.asset].close[event.index]
        elif event.phase == SIGNAL:
            assert event.signal is not None
            _process_signal(book, event.signal, pending)
        elif event.phase == SNAPSHOT:
            assert event.day is not None
            snapshots.append(_snapshot(book, event.day, event.at))

    if book.positions:
        raise AccountingError(f"posiciones abiertas tras la ventana: {sorted(book.positions)}")
    trades = [_trade(position) for position in sorted(book.closed, key=lambda item: item.position_id)]
    _check_identity(book, trades)
    return SimResult(
        policy_id=spec.policy_id,
        system_sha256=spec.system_sha256,
        v0=spec.capital,
        v0_day=market.window_start,
        ledger=book.ledger,
        snapshots=snapshots,
        trades=trades,
        counters=dict(sorted(book.counters.items())),
        notional_traded_eur=book.notional,
        fees_eur=book.fees,
        slippage_eur=book.slippage,
        dividends_eur=book.dividends,
    )


def _process_signal(book: _Book, signal: Signal, pending: Dict[str, Signal]) -> None:
    series = book.market.assets[signal.asset]
    common = dict(
        market=series.market, asset=signal.asset, session_date=str(series.session_dates[signal.bar_index]),
        signal_id=signal.signal_id, cash_before=book.cash, cash_after=book.cash, currency=series.currency,
    )
    if signal.asset in book.positions:
        book.count(IGNORED_ALREADY_OPEN)
        book.write(signal.analysis_ts, SIGNAL, "SIGNAL_IGNORED", reason=IGNORED_ALREADY_OPEN, **common)
        return
    if signal.asset in pending:
        raise AccountingError(f"{signal.asset}: dos órdenes pendientes a la vez")
    pending[signal.asset] = signal
    book.count("senales_pendientes")
    book.write(signal.analysis_ts, SIGNAL, "SIGNAL_PENDING", reason="ORDEN_PARA_APERTURA_SIGUIENTE", **common)


def _process_entries(book: _Book, batch: List[_Event], pending: Dict[str, Signal], at: datetime) -> None:
    candidates = []
    for event in batch:
        signal = pending.get(event.asset)
        if signal is not None and signal.bar_index + 1 == event.index:
            del pending[event.asset]
            candidates.append((tiebreak_key(signal.signal_id), signal, event))
        elif signal is not None and signal.bar_index + 1 < event.index:
            raise AccountingError(f"{signal.signal_id}: orden pendiente no ejecutada en su apertura")
    if not candidates:
        return
    candidates.sort(key=lambda item: item[0])
    equity = book.equity(at)
    spec = book.spec
    for _key, signal, event in candidates:
        series = book.market.assets[signal.asset]
        i = event.index
        market_open = series.open[i]
        eff = market_open * (1.0 + spec.slip)
        quote = book.fx.quote(series.currency, at)
        reason = ENTRY_OK
        units = 0.0
        required: Any = ""
        if not (math.isfinite(market_open) and market_open > 0):
            reason = DATA_NOT_EXECUTABLE
        elif signal.stop >= eff:
            reason = INVALID_STOP
        elif signal.target2 <= eff:
            reason = INVALID_TARGET
        elif eff > signal.entry_max and not math.isclose(eff, signal.entry_max, rel_tol=1e-9):
            reason = ABOVE_MAX_ENTRY
        elif not rr_at_least((signal.target2 - eff) / (eff - signal.stop), spec.min_rr):
            reason = RR_TOO_LOW
        else:
            risk_unit_eur = (eff - signal.stop) * quote.rate_to_eur
            units_risk = equity * spec.risk_pct / 100.0 / risk_unit_eur
            units_cap = equity * spec.max_position_pct / 100.0 / (eff * quote.rate_to_eur)
            units = min(units_risk, units_cap)
            if not (units > 0 and math.isfinite(units)):
                reason = POSITION_TOO_SMALL
            else:
                required = units * eff * quote.rate_to_eur * (1.0 + spec.fee_rate)
                if float(required) > book.cash + ACCOUNTING_TOLERANCE_EUR:
                    reason = INSUFFICIENT_CASH
        common = dict(
            market=series.market, asset=signal.asset, session_date=str(series.session_dates[i]),
            signal_id=signal.signal_id, currency=series.currency, market_price=market_open, effective_price=eff,
            fx_pair=quote.pair, fx_rate=quote.rate_to_eur, fx_timestamp_available=utc_iso(quote.available_at),
            stop=signal.stop, target2=signal.target2, cash_requerido_base=required,
        )
        if reason != ENTRY_OK:
            book.count(reason)
            book.write(at, OPEN_ENTRY, "ENTRY_REJECTED", cash_before=book.cash, cash_after=book.cash, reason=reason, **common)
            continue
        notional_eur = units * eff * quote.rate_to_eur
        fee_eur = notional_eur * spec.fee_rate
        slip_eur = units * (eff - market_open) * quote.rate_to_eur
        cash_before = book.cash
        book.cash -= notional_eur + fee_eur
        if -ACCOUNTING_TOLERANCE_EUR < book.cash < 0:
            book.cash = 0.0
        book.notional += notional_eur
        book.fees += fee_eur
        book.slippage += slip_eur
        book.position_seq += 1
        held = Position(
            position_id=f"{spec.policy_id}-{book.position_seq:06d}", asset=signal.asset, signal_id=signal.signal_id,
            currency=series.currency, entry_index=i, entry_ts=at, units=units, stop=signal.stop, target2=signal.target2,
            market_entry=market_open, entry_eff=eff, fx_entry=quote.rate_to_eur, fee_entry_eur=fee_eur,
            fee_entry_local=units * eff * spec.fee_rate, slippage_entry_eur=slip_eur, mark_price=eff,
        )
        book.positions[signal.asset] = held
        book.count("entradas")
        book.write(
            at, OPEN_ENTRY, "ENTRY", position_id=held.position_id, cash_before=cash_before, cash_after=book.cash,
            units_before=0.0, units_after=units, notional_base=notional_eur, fee_base=fee_eur, slippage_base=slip_eur,
            reason=ENTRY_OK, **common,
        )


def _process_open_exit(book: _Book, event: _Event, entitlements: Dict[Tuple[str, int], List[Tuple[Position, float]]]) -> None:
    held = book.positions.get(event.asset)
    if held is None or held.entry_index >= event.index:
        return
    series = book.market.assets[event.asset]
    i = event.index
    dividend = series.dividends[i]
    if dividend > 0:
        entitlements.setdefault((event.asset, i), []).append((held, dividend))
    bar_open, bar_low = series.open[i], series.low[i]
    if bar_open <= held.stop:
        _exit_position(book, held, event.at, OPEN_EXIT, i, bar_open, EXIT_STOP)
    elif bar_open >= held.target2 and bar_low > held.stop:
        _exit_position(book, held, event.at, OPEN_EXIT, i, bar_open, EXIT_TARGET)


def _process_close_exit(book: _Book, event: _Event, last_index: Mapping[str, Optional[int]]) -> None:
    held = book.positions.get(event.asset)
    if held is None:
        return
    series = book.market.assets[event.asset]
    i = event.index
    if held.entry_index > i:
        return
    if series.low[i] <= held.stop:
        _exit_position(book, held, event.at, CLOSE_EXIT, i, held.stop, EXIT_STOP)
    elif series.high[i] >= held.target2:
        _exit_position(book, held, event.at, CLOSE_EXIT, i, held.target2, EXIT_TARGET)
    elif i - held.entry_index >= book.spec.max_hold_bars:
        _exit_position(book, held, event.at, CLOSE_EXIT, i, series.close[i], EXIT_TIME)
    elif last_index.get(event.asset) == i:
        _exit_position(book, held, event.at, CLOSE_EXIT, i, series.close[i], EXIT_FINAL)


def _process_dividend(book: _Book, event: _Event, entitlements: Dict[Tuple[str, int], List[Tuple[Position, float]]]) -> None:
    entries = entitlements.pop((event.asset, event.index), [])
    series = book.market.assets[event.asset]
    for held, dividend in entries:
        quote = book.fx.quote(held.currency, event.at)
        amount_local = held.units * dividend
        amount_eur = amount_local * quote.rate_to_eur
        cash_before = book.cash
        book.cash += amount_eur
        book.dividends += amount_eur
        held.dividends_local += amount_local
        held.dividends_eur += amount_eur
        book.count("dividendos_abonados")
        book.write(
            event.at, CLOSE_DIVIDEND, "DIVIDEND", market=series.market, asset=event.asset,
            session_date=str(series.session_dates[event.index]), signal_id=held.signal_id,
            position_id=held.position_id, cash_before=cash_before, cash_after=book.cash, units_before=held.units,
            units_after=held.units if event.asset in book.positions else 0.0, market_price=dividend,
            currency=held.currency, fx_pair=quote.pair, fx_rate=quote.rate_to_eur,
            fx_timestamp_available=utc_iso(quote.available_at), dividend_base=amount_eur, reason="DIVIDENDO_BRUTO",
        )


def _snapshot(book: _Book, day: date, at: datetime) -> Snapshot:
    by_region: Dict[str, float] = {}
    by_currency: Dict[str, float] = {}
    by_economic: Dict[str, float] = {}
    by_sector: Dict[str, float] = {}
    long_value = 0.0
    for held in book.positions.values():
        series = book.market.assets[held.asset]
        value = held.units * held.mark_price * book.fx.quote(held.currency, at).rate_to_eur
        long_value += value
        for bucket, key in ((by_region, series.region), (by_currency, series.currency),
                            (by_economic, series.economic_currency), (by_sector, series.sector)):
            bucket[key] = bucket.get(key, 0.0) + value
    return Snapshot(
        day=day, at=at, equity=book.cash + long_value, cash=book.cash, long_value=long_value,
        positions=len(book.positions), by_region=by_region, by_currency=by_currency,
        by_economic_currency=by_economic, by_sector=by_sector,
    )


def _trade(position: Position) -> Trade:
    assert position.exit_eff is not None and position.fx_exit is not None and position.exit_ts is not None
    assert position.exit_reason is not None and position.exit_index is not None
    units = position.units
    risk_local = (position.entry_eff - position.stop) * units
    pnl_bruto_local = units * (position.exit_eff - position.entry_eff)
    fees_local = position.fee_entry_local + position.fee_exit_local
    pnl_neto_local = pnl_bruto_local - fees_local + position.dividends_local
    risk_eur = risk_local * position.fx_entry
    pnl_bruto_eur = units * (position.exit_eff * position.fx_exit - position.entry_eff * position.fx_entry)
    fees_eur = position.fee_entry_eur + position.fee_exit_eur
    pnl_neto_eur = pnl_bruto_eur - fees_eur + position.dividends_eur
    return Trade(
        position_id=position.position_id, asset=position.asset, signal_id=position.signal_id,
        currency=position.currency, entry_ts=utc_iso(position.entry_ts), exit_ts=utc_iso(position.exit_ts),
        exit_reason=position.exit_reason, bars_held=position.exit_index - position.entry_index, units=units,
        entry_eff=position.entry_eff, exit_eff=position.exit_eff, stop=position.stop, fx_entry=position.fx_entry,
        fx_exit=position.fx_exit, risk_local=risk_local, pnl_bruto_local=pnl_bruto_local, fees_local=fees_local,
        dividends_local=position.dividends_local, pnl_neto_local=pnl_neto_local,
        trade_R_local=pnl_neto_local / risk_local, risk_eur=risk_eur, pnl_bruto_eur=pnl_bruto_eur,
        fees_eur=fees_eur, dividends_eur=position.dividends_eur, pnl_neto_eur=pnl_neto_eur,
        trade_R_eur=pnl_neto_eur / risk_eur,
        slippage_eur=position.slippage_entry_eur + position.slippage_exit_eur,
        fx_eur=units * position.exit_eff * (position.fx_exit - position.fx_entry),
    )


CASH_OUT = ("ENTRY", "BH_BUY")
CASH_IN = ("EXIT", "BH_SELL_FINAL")
DIVIDEND_EVENTS = ("DIVIDEND", "BH_DIVIDEND")


def check_ledger_flows(ledger: Sequence[Mapping[str, Any]], capital: float) -> float:
    """Cada fila cuadra su cash con sus flujos publicados y encadena con la anterior; devuelve el cash final."""

    cash = capital
    for row in ledger:
        before, after = float(row["cash_before"] if row["cash_before"] != "" else cash), row["cash_after"]
        after = float(after if after != "" else before)
        if abs(before - cash) > ACCOUNTING_TOLERANCE_EUR:
            raise AccountingError(f"fila {row['seq']}: cash_before {before} no encadena con {cash}")
        if row["event_type"] in CASH_OUT:
            expected = before - float(row["notional_base"]) - float(row["fee_base"])
        elif row["event_type"] in CASH_IN:
            expected = before + float(row["notional_base"]) - float(row["fee_base"])
        elif row["event_type"] in DIVIDEND_EVENTS:
            expected = before + float(row["dividend_base"])
        else:
            expected = before
        if abs(after - expected) > ACCOUNTING_TOLERANCE_EUR or after < -ACCOUNTING_TOLERANCE_EUR:
            raise AccountingError(f"fila {row['seq']} ({row['event_type']}): cash {after} ≠ {expected}")
        cash = after
    return cash


def _check_identity(book: _Book, trades: Sequence[Trade]) -> None:
    check_ledger_flows(book.ledger, book.spec.capital)
    final_equity = book.cash
    lhs = final_equity - book.spec.capital
    rhs = sum(trade.pnl_bruto_eur for trade in trades) + book.dividends - book.fees
    if abs(lhs - rhs) > ACCOUNTING_TOLERANCE_EUR * max(1.0, len(trades)):
        raise AccountingError(f"V_T − V_0 = {lhs} no cuadra con Σ pnl_bruto + dividendos − comisiones = {rhs}")
    if abs(sum(trade.pnl_neto_eur for trade in trades) - lhs) > ACCOUNTING_TOLERANCE_EUR * max(1.0, len(trades)):
        raise AccountingError("V_T − V_0 no cuadra con Σ pnl_neto_EUR")


# ---------------------------------------------------------------------------
# Benchmark: buy-and-hold del propio universo (T-022 §14, OD-P6-22 a 25).
# ---------------------------------------------------------------------------


@dataclass
class _Holding:
    asset: str
    currency: str
    units: float
    mark_price: float


@dataclass
class BenchmarkResult:
    benchmark_sha256: str
    v0: float
    v0_day: date
    ledger: List[Dict[str, Any]]
    snapshots: List[Snapshot]
    notional_traded_eur: float
    fees_eur: float
    dividends_eur: float


def simulate_benchmark(
    market: MarketData,
    fx: FxTable,
    spec: SimSpec,
    *,
    authorize: Optional[Callable[[], None]] = None,
) -> BenchmarkResult:
    """Pesos iguales sobre todos los activos, sin rebalanceo; comisión dentro del importe asignado."""

    _require_authorization(market, authorize)
    holdings: Dict[str, _Holding] = {}

    def bh_equity(at: datetime) -> float:
        return book.cash + sum(h.units * h.mark_price * fx.quote(h.currency, at).rate_to_eur for h in holdings.values())

    book = _Book(market, fx, spec, valuer=bh_equity)
    allocation = spec.capital / len(market.assets)
    first_buy: Dict[str, int] = {}
    for symbol, asset_series in market.assets.items():
        candidates = [
            i for i in asset_series.window_indices(market.window_start, market.window_end) if i >= asset_series.eligible_from
        ]
        if candidates:
            first_buy[symbol] = candidates[0]
    last_index = {symbol: _last_window_index(series, market.window_end) for symbol, series in market.assets.items()}
    reinvest: Dict[str, float] = {}
    entitlements: Dict[Tuple[str, int], float] = {}
    snapshots: List[Snapshot] = []
    events = sorted(_session_events(market), key=lambda event: event.sort_key())

    def buy(symbol: str, index: int, at: datetime, amount_eur: float, reason: str) -> None:
        series = market.assets[symbol]
        quote = fx.quote(series.currency, at)
        market_open = series.open[index]
        eff = market_open * (1.0 + spec.slip)
        notional = amount_eur / (1.0 + spec.fee_rate)
        fee = amount_eur - notional
        units = notional / (eff * quote.rate_to_eur)
        cash_before = book.cash
        book.cash -= amount_eur
        if abs(book.cash) < ACCOUNTING_TOLERANCE_EUR:
            book.cash = 0.0
        book.notional += notional
        book.fees += fee
        book.slippage += units * (eff - market_open) * quote.rate_to_eur
        held = holdings.get(symbol)
        before = held.units if held else 0.0
        if held is None:
            holdings[symbol] = _Holding(symbol, series.currency, units, eff)
        else:
            held.units += units
        book.write(
            at, OPEN_ENTRY, "BH_BUY", market=series.market, asset=symbol, session_date=str(series.session_dates[index]),
            cash_before=cash_before, cash_after=book.cash, units_before=before, units_after=before + units,
            market_price=market_open, effective_price=eff, currency=series.currency, fx_pair=quote.pair,
            fx_rate=quote.rate_to_eur, fx_timestamp_available=utc_iso(quote.available_at), notional_base=notional,
            fee_base=fee, slippage_base=units * (eff - market_open) * quote.rate_to_eur, reason=reason,
        )

    for event in events:
        series: Optional[AssetSeries] = market.assets.get(event.asset) if event.asset else None
        if event.phase == OPEN_EXIT and series is not None:
            held = holdings.get(event.asset)
            if held is not None and series.dividends[event.index] > 0 and first_buy.get(event.asset, 10**9) < event.index:
                entitlements[(event.asset, event.index)] = held.units * series.dividends[event.index]
        elif event.phase == OPEN_ENTRY and series is not None:
            if first_buy.get(event.asset) == event.index:
                buy(event.asset, event.index, event.at, allocation, "BH_COMPRA_INICIAL")
            amount = reinvest.pop(event.asset, 0.0)
            if amount > 0:
                buy(event.asset, event.index, event.at, amount, "BH_REINVERSION_DIVIDENDO")
        elif event.phase == CLOSE_DIVIDEND and series is not None:
            amount_local = entitlements.pop((event.asset, event.index), 0.0)
            if amount_local > 0:
                quote = fx.quote(series.currency, event.at)
                amount_eur = amount_local * quote.rate_to_eur
                cash_before = book.cash
                book.cash += amount_eur
                book.dividends += amount_eur
                if last_index.get(event.asset) != event.index:
                    reinvest[event.asset] = reinvest.get(event.asset, 0.0) + amount_eur
                book.write(
                    event.at, CLOSE_DIVIDEND, "BH_DIVIDEND", market=series.market, asset=event.asset,
                    session_date=str(series.session_dates[event.index]), cash_before=cash_before, cash_after=book.cash,
                    currency=series.currency, fx_pair=quote.pair, fx_rate=quote.rate_to_eur,
                    fx_timestamp_available=utc_iso(quote.available_at), dividend_base=amount_eur, reason="DIVIDENDO_BRUTO",
                )
        elif event.phase == CLOSE_EXIT and series is not None:
            held = holdings.get(event.asset)
            if held is not None and last_index.get(event.asset) == event.index:
                quote = fx.quote(series.currency, event.at)
                eff = series.close[event.index] * (1.0 - spec.slip)
                gross = held.units * eff * quote.rate_to_eur
                fee = gross * spec.fee_rate
                cash_before = book.cash
                book.cash += gross - fee
                book.notional += gross
                book.fees += fee
                units = held.units
                del holdings[event.asset]
                book.write(
                    event.at, CLOSE_EXIT, "BH_SELL_FINAL", market=series.market, asset=event.asset,
                    session_date=str(series.session_dates[event.index]), cash_before=cash_before,
                    cash_after=book.cash, units_before=units, units_after=0.0,
                    market_price=series.close[event.index], effective_price=eff, currency=series.currency,
                    fx_pair=quote.pair, fx_rate=quote.rate_to_eur,
                    fx_timestamp_available=utc_iso(quote.available_at), notional_base=gross, fee_base=fee,
                    reason=EXIT_FINAL,
                )
        elif event.phase == CLOSE_VALUATION and series is not None:
            held = holdings.get(event.asset)
            if held is not None:
                held.mark_price = series.close[event.index]
        elif event.phase == SNAPSHOT:
            assert event.day is not None
            long_value = sum(h.units * h.mark_price * fx.quote(h.currency, event.at).rate_to_eur for h in holdings.values())
            snapshots.append(Snapshot(event.day, event.at, book.cash + long_value, book.cash, long_value,
                                      len(holdings), {}, {}, {}, {}))
    if holdings:
        raise AccountingError(f"benchmark con posiciones abiertas tras la ventana: {sorted(holdings)}")
    final_cash = check_ledger_flows(book.ledger, spec.capital)
    if abs(final_cash - book.cash) > ACCOUNTING_TOLERANCE_EUR:
        raise AccountingError("el cash final del benchmark no cuadra con su ledger")
    if snapshots and abs(snapshots[-1].equity - book.cash) > ACCOUNTING_TOLERANCE_EUR:
        raise AccountingError("la equity final del benchmark no es su cash tras la liquidación")
    return BenchmarkResult(
        benchmark_sha256=spec.system_sha256, v0=spec.capital, v0_day=market.window_start, ledger=book.ledger,
        snapshots=snapshots, notional_traded_eur=book.notional, fees_eur=book.fees, dividends_eur=book.dividends,
    )


# ---------------------------------------------------------------------------
# Métricas (T-022 §15) y criterio (§16, D-69).
# ---------------------------------------------------------------------------

N_MIN = 100
DD_MAX = 0.25
LABEL_PASS = "PASA"
LABEL_NO_SAMPLE = "NO EVALUABLE POR MUESTRA"
LABEL_FAIL = "NO PASA"


def _nearest_rank(values: Sequence[float], p: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100.0 * len(ordered)))
    return ordered[rank - 1]


def equity_series(v0: float, v0_day: date, snapshots: Sequence[Snapshot]) -> List[Tuple[date, float]]:
    return [(v0_day, v0)] + [(snap.day, snap.equity) for snap in snapshots]


def periods_per_year(series: Sequence[Tuple[date, float]]) -> Optional[float]:
    days = (series[-1][0] - series[0][0]).days
    if days <= 0:
        return None
    return (len(series) - 1) / (days / 365.25)


def path_metrics(series: Sequence[Tuple[date, float]], expected_ppy: Optional[float] = None) -> Dict[str, Any]:
    """Métricas de trayectoria; con ``expected_ppy`` exige el ``periodos_por_año`` del contrato."""

    v0, vt = series[0][1], series[-1][1]
    days = (series[-1][0] - series[0][0]).days
    returns = [series[k][1] / series[k - 1][1] - 1.0 for k in range(1, len(series))]
    ppy = periods_per_year(series)
    if expected_ppy is not None and (ppy is None or abs(ppy - expected_ppy) > 1e-9):
        raise AccountingError(f"periodos_por_año observado {ppy} distinto del contrato {expected_ppy}")
    total = vt / v0 - 1.0
    cagr = (vt / v0) ** (365.25 / days) - 1.0 if days > 0 and vt > 0 else None
    vol = sharpe = sortino = None
    if len(returns) >= 2 and ppy:
        mean = sum(returns) / len(returns)
        std = math.sqrt(sum((r - mean) ** 2 for r in returns) / (len(returns) - 1))
        vol = std * math.sqrt(ppy)
        sharpe = mean * ppy / (std * math.sqrt(ppy)) if std > 0 else None
        downside = math.sqrt(sum(min(r, 0.0) ** 2 for r in returns) / len(returns))
        sortino = mean * ppy / (downside * math.sqrt(ppy)) if downside > 0 else None
    peak_value, peak_day = series[0][1], series[0][0]
    mdd, mdd_peak, mdd_trough = 0.0, series[0][0], series[0][0]
    for day, value in series:
        if value > peak_value:
            peak_value, peak_day = value, day
        drawdown = value / peak_value - 1.0
        if drawdown < mdd:
            mdd, mdd_peak, mdd_trough = drawdown, peak_day, day
    recovery = None
    if mdd < 0:
        peak_level = next(value for day, value in series if day == mdd_peak)
        for day, value in series:
            if day > mdd_trough and value >= peak_level:
                recovery = day
                break
    duration = ((recovery or series[-1][0]) - mdd_peak).days if mdd < 0 else 0
    calmar = cagr / abs(mdd) if cagr is not None and mdd < 0 else None
    return {
        "equity_inicial": v0,
        "equity_final": vt,
        "retorno_total": total,
        "cagr": cagr,
        "dias": days,
        "periodos_por_año": ppy,
        "volatilidad": vol,
        "sharpe_rf0": sharpe,
        "sortino_mar0": sortino,
        "max_drawdown": mdd,
        "dd_pico": str(mdd_peak) if mdd < 0 else None,
        "dd_valle": str(mdd_trough) if mdd < 0 else None,
        "dd_recuperacion": str(recovery) if recovery else ("sin recuperar" if mdd < 0 else None),
        "dd_duracion_dias": duration,
        "calmar": calmar,
    }


def trade_metrics(trades: Sequence[Trade]) -> Dict[str, Any]:
    r_local = [trade.trade_R_local for trade in trades]
    r_eur = [trade.trade_R_eur for trade in trades]

    def pf(values: Sequence[float]) -> Tuple[Optional[float], bool]:
        gains = sum(v for v in values if v > 0)
        losses = sum(v for v in values if v < 0)
        if not values:
            return None, False
        if losses == 0:
            return None, gains > 0
        return gains / abs(losses), False

    pf_local, no_losses_local = pf(r_local)
    pf_eur, no_losses_eur = pf([trade.pnl_neto_eur for trade in trades])
    return {
        "n_closed": len(trades),
        "n_exit_final": sum(1 for trade in trades if trade.exit_reason == EXIT_FINAL),
        "win_rate": (sum(1 for trade in trades if trade.pnl_neto_eur > 0) / len(trades)) if trades else None,
        "profit_factor_local": pf_local,
        "profit_factor_local_sin_perdidas": no_losses_local,
        "mean_R_local": (sum(r_local) / len(r_local)) if r_local else None,
        "median_R_local": median(r_local) if r_local else None,
        "R_total_local": sum(r_local),
        "profit_factor_eur": pf_eur,
        "profit_factor_eur_sin_perdidas": no_losses_eur,
        "mean_R_eur": (sum(r_eur) / len(r_eur)) if r_eur else None,
        "median_R_eur": median(r_eur) if r_eur else None,
        "R_total_eur": sum(r_eur),
        "holding_medio_barras": (sum(trade.bars_held for trade in trades) / len(trades)) if trades else None,
    }


def block_mean_R(trades: Sequence[Trade]) -> Optional[float]:
    """Media por bloque INV-14 (por año natural de salida), solo descriptiva (T-022 §16)."""

    by_year: Dict[int, List[float]] = {}
    for trade in trades:
        by_year.setdefault(int(trade.exit_ts[:4]), []).append(trade.trade_R_local)
    if not by_year:
        return None
    return sum(sum(values) / len(values) for values in by_year.values()) / len(by_year)


def exposure_metrics(snapshots: Sequence[Snapshot]) -> Dict[str, Any]:
    if not snapshots:
        return {}
    gross = [snap.long_value / snap.equity for snap in snapshots]
    cash = [snap.cash / snap.equity for snap in snapshots]
    out: Dict[str, Any] = {
        "exposicion_media": sum(gross) / len(gross),
        "exposicion_max": max(gross),
        "exposicion_p95": _nearest_rank(gross, 95),
        "cash_medio": sum(cash) / len(cash),
        "cash_minimo_eur": min(snap.cash for snap in snapshots),
        "posiciones_media": sum(snap.positions for snap in snapshots) / len(snapshots),
        "posiciones_max": max(snap.positions for snap in snapshots),
        "distribucion_posiciones": {
            str(n): sum(1 for snap in snapshots if snap.positions == n) / len(snapshots)
            for n in sorted({snap.positions for snap in snapshots})
        },
    }
    for name, attr in (("region", "by_region"), ("divisa_cotizacion", "by_currency"),
                       ("divisa_economica", "by_economic_currency"), ("sector", "by_sector")):
        keys = sorted({key for snap in snapshots for key in getattr(snap, attr)})
        out[f"por_{name}"] = {
            key: {
                "media": sum(getattr(snap, attr).get(key, 0.0) / snap.equity for snap in snapshots) / len(snapshots),
                "max": max(getattr(snap, attr).get(key, 0.0) / snap.equity for snap in snapshots),
                "p95": _nearest_rank([getattr(snap, attr).get(key, 0.0) / snap.equity for snap in snapshots], 95),
            }
            for key in keys
        }
    return out


def turnover(notional_traded_eur: float, series: Sequence[Tuple[date, float]]) -> Dict[str, Optional[float]]:
    mean_equity = sum(value for _, value in series) / len(series)
    days = (series[-1][0] - series[0][0]).days
    total = notional_traded_eur / mean_equity if mean_equity > 0 else None
    return {
        "turnover_total": total,
        "turnover_anual": (total / (days / 365.25)) if total is not None and days > 0 else None,
    }


def excess(policy_path: Mapping[str, Any], benchmark_path: Mapping[str, Any]) -> Dict[str, Optional[float]]:
    cagr_p, cagr_b = policy_path.get("cagr"), benchmark_path.get("cagr")
    return {
        "excess_terminal_pp": 100.0 * (policy_path["retorno_total"] - benchmark_path["retorno_total"]),
        "excess_CAGR_pp": 100.0 * (cagr_p - cagr_b) if cagr_p is not None and cagr_b is not None else None,
    }


def criterion(trades_m: Mapping[str, Any], path_m: Mapping[str, Any], excess_m: Mapping[str, Any]) -> Dict[str, Any]:
    """Criterio único y simultáneo de P6 (D-69). Nada más veta ni rescata."""

    n = trades_m["n_closed"]
    pf = trades_m["profit_factor_local"]
    pf_ok = (pf is not None and pf > 1.0) or (pf is None and trades_m["profit_factor_local_sin_perdidas"] and n >= N_MIN)
    mean_r = trades_m["mean_R_local"]
    exc = excess_m["excess_CAGR_pp"]
    conditions = {
        "N_closed>=100": n >= N_MIN,
        "profit_factor_local>1": bool(pf_ok),
        "mean_R_local>0": mean_r is not None and mean_r > 0,
        "max_drawdown>=-25%": path_m["max_drawdown"] >= -DD_MAX,
        "excess_CAGR_pp>0": exc is not None and exc > 0,
    }
    if not conditions["N_closed>=100"]:
        label = LABEL_NO_SAMPLE
    elif all(conditions.values()):
        label = LABEL_PASS
    else:
        label = LABEL_FAIL
    return {"condiciones": conditions, "etiqueta": label, "pasa": label == LABEL_PASS}


def survivors(labels: Mapping[str, str]) -> Tuple[str, ...]:
    for policy in labels:
        if policy not in ("B2", "S2"):
            raise ValueError(f"{policy} no puede salir de P6")
    return tuple(policy for policy in ("B2", "S2") if labels.get(policy) == LABEL_PASS)


def subperiods(series: Sequence[Tuple[date, float]], trades: Sequence[Trade]) -> Dict[str, Any]:
    """Robustez temporal interna sobre datos de desarrollo: solo descriptiva."""

    out: Dict[str, Any] = {"rotulo": "robustez temporal interna sobre datos de desarrollo", "por_año": {}, "mitades": {}}
    years = sorted({day.year for day, _ in series})
    for year in years:
        points = [(day, value) for day, value in series if day.year == year]
        previous = [(day, value) for day, value in series if day.year < year]
        start_value = previous[-1][1] if previous else points[0][1]
        year_trades = [trade for trade in trades if int(trade.exit_ts[:4]) == year]
        out["por_año"][str(year)] = {
            "retorno": points[-1][1] / start_value - 1.0,
            "operaciones": len(year_trades),
            "mean_R_local": (sum(t.trade_R_local for t in year_trades) / len(year_trades)) if year_trades else None,
        }
    middle = series[0][0] + (series[-1][0] - series[0][0]) / 2
    for name, part in (("primera", [p for p in series if p[0] <= middle]), ("segunda", [p for p in series if p[0] >= middle])):
        part_trades = [t for t in trades if (date.fromisoformat(t.exit_ts[:10]) <= middle) == (name == "primera")]
        out["mitades"][name] = {
            "retorno": part[-1][1] / part[0][1] - 1.0 if len(part) > 1 else None,
            "operaciones": len(part_trades),
            "mean_R_local": (sum(t.trade_R_local for t in part_trades) / len(part_trades)) if part_trades else None,
        }
    out["media_por_bloque_R_local_INV14_descriptiva"] = block_mean_R(trades)
    return out


def ledger_csv(rows: Sequence[Mapping[str, Any]]) -> str:
    """Serialización determinista del ledger (floats con ``repr``)."""

    def cell(value: Any) -> str:
        if isinstance(value, float):
            return repr(value)
        return str(value)

    lines = [",".join(LEDGER_COLUMNS)]
    for row in rows:
        lines.append(",".join(cell(row.get(column, "")) for column in LEDGER_COLUMNS))
    return "\n".join(lines) + "\n"


TRADE_COLUMNS = tuple(Trade.__dataclass_fields__)


def trades_csv(trades: Sequence[Trade]) -> str:
    lines = [",".join(TRADE_COLUMNS)]
    for trade in trades:
        values = [getattr(trade, column) for column in TRADE_COLUMNS]
        lines.append(",".join(repr(v) if isinstance(v, float) else str(v) for v in values))
    return "\n".join(lines) + "\n"


def cash_occupancy(counters: Mapping[str, int], ledger: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Ocupación: señales ejecutables rechazadas por cash y capital pedido frente a disponible."""

    rejected = [row for row in ledger if row["event_type"] == "ENTRY_REJECTED" and row["reason"] == INSUFFICIENT_CASH]
    entries = counters.get("entradas", 0)
    executable = entries + len(rejected)
    return {
        "entradas": entries,
        "rechazadas_por_cash": len(rejected),
        "fraccion_ejecutables_rechazadas_por_cash": (len(rejected) / executable) if executable else None,
        "capital_pedido_rechazado_eur": sum(float(row["cash_requerido_base"]) for row in rejected),
        "capital_disponible_en_esos_rechazos_eur": sum(float(row["cash_before"]) for row in rejected),
    }


def series_csv(series: Sequence[Tuple[date, float]]) -> str:
    return "dia,equity_eur\n" + "".join(f"{day.isoformat()},{value!r}\n" for day, value in series)


def snapshot_days(market: MarketData) -> List[date]:
    """Días con al menos una sesión en la ventana (estructural: no lee precios)."""

    days = set()
    for series in market.assets.values():
        for i in series.window_indices(market.window_start, market.window_end):
            days.add(series.session_dates[i])
    return sorted(days)
