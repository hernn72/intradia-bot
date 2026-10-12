"""Contexto de mercado point-in-time para Score v2/P3.

Este módulo concentra la semántica congelada en T-019 D-50..D-56. El camino
legacy de Score v1 sigue viviendo en sus consumidores; cualquier ruta v2/P3
debe entrar por aquí para no volver a alinear por fecha civil ni por
``shift(1)``.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from functools import cache
from typing import Any, Literal, Mapping, Optional, Sequence, cast
from zoneinfo import ZoneInfo

import pandas as pd

from advisor.analysis.market_context import MarketContext, build_market_context
from advisor.analysis.overview import context_assets_of
from advisor.config import MarketContextConfig
from advisor.data.calendars import exchange_calendar, expected_sessions
from advisor.data.market_data import MarketDataProvider
from advisor.data.sessions import (
    CRYPTO_MIC,
    market_for_symbol,
    market_session,
    session_close_at,
    session_date_of,
)
from advisor.indicators.technical import sma
from advisor.universe.models import Universe

EXCLUDED_CRYPTO = "excluded_crypto"
EXCLUDED_ASIA_MISSING = "excluded_asia_missing"
EXCLUDED_TREND_SMA_HISTORY = "excluded_trend_sma_history"
NO_CALCULABLE_CONTEXT_HISTORY = "NO_CALCULABLE_CONTEXT_HISTORY"
NO_CALCULABLE_CONTEXT_VIX = "NO_CALCULABLE_CONTEXT_VIX"

LONDON = ZoneInfo("Europe/London")
PRODUCTION_PASS_TIMES: tuple[time, ...] = (
    time(7, 0),
    time(8, 30),
    time(14, 30),
    time(21, 0),
)

ContextMode = Literal["legacy_v1", "point_in_time"]


@dataclass(frozen=True)
class SeriesPoint:
    session: date
    value: float


@dataclass(frozen=True)
class AsiaMissing:
    symbol: str
    missing: str
    session: date


@dataclass(frozen=True)
class PointInTimeContextResult:
    analysis_timestamp: datetime
    context: Optional[MarketContext]
    exclusions: tuple[str, ...]
    no_calculable_codes: tuple[str, ...]
    vix_session: Optional[date]
    trend_expected_session: Optional[date]
    trend_used_session: Optional[date]
    trend_sma_count: int
    stoxx_age_days: Optional[int]
    asia_sessions: Mapping[str, tuple[date, date]]
    asia_missing: tuple[AsiaMissing, ...]

    @property
    def calculable(self) -> bool:
        return not self.exclusions and self.context is not None


@dataclass(frozen=True)
class PreparedContextSeries:
    symbol: str
    market: str
    points: tuple[SeriesPoint, ...]
    available_at: tuple[datetime, ...]

    @property
    def by_session(self) -> Mapping[date, float]:
        return {point.session: point.value for point in self.points}


class PointInTimeContextResolver:
    """Resolver reutilizable: pre-sesiona una vez y cachea por timestamp."""

    def __init__(
        self,
        closes: Mapping[str, pd.Series],
        config: MarketContextConfig,
        *,
        asia_symbols: Sequence[str],
        settlement_minutes: int,
    ) -> None:
        self._config = config
        self._asia_symbols = tuple(asia_symbols)
        self._settlement_minutes = settlement_minutes
        self._prepared = prepare_context_closes(closes, settlement_minutes=settlement_minutes)
        self._cache: dict[datetime, PointInTimeContextResult] = {}

    def resolve(self, analysis_timestamp: datetime) -> PointInTimeContextResult:
        if analysis_timestamp.tzinfo is None:
            raise ValueError("analysis_timestamp debe ser aware")
        reference = analysis_timestamp.astimezone(timezone.utc)
        resolved = self._cache.get(reference)
        if resolved is None:
            resolved = _resolve_point_in_time_context_prepared(
                reference,
                self._prepared,
                self._config,
                asia_symbols=self._asia_symbols,
                settlement_minutes=self._settlement_minutes,
            )
            self._cache[reference] = resolved
        return resolved

    def contexts_for_index(
        self,
        index: pd.Index,
        *,
        signal_market: str,
    ) -> list[PointInTimeContextResult | None]:
        results: list[PointInTimeContextResult | None] = []
        for position, timestamp in enumerate(index):
            signal_session = session_date_of(timestamp, signal_market)
            next_session = session_date_of(index[position + 1], signal_market) if position + 1 < len(index) else None
            if signal_session is None or next_session is None:
                results.append(None)
                continue
            analysis_timestamp = analysis_timestamp_for_signal(
                signal_market,
                signal_session,
                next_session,
                settlement_minutes=self._settlement_minutes,
            )
            results.append(self.resolve(analysis_timestamp) if analysis_timestamp is not None else None)
        return results


def context_mode_for(score_model_version: str) -> ContextMode:
    """Selector único de contexto por versión de score."""

    if score_model_version == "1.0":
        return "legacy_v1"
    if score_model_version == "2.0":
        return "point_in_time"
    raise ValueError(f"score_model_version sin modo de contexto: {score_model_version}")


def resolve_context_mode(score_model_version: str, explicit: Optional[ContextMode]) -> ContextMode:
    mode = explicit or context_mode_for(score_model_version)
    if mode not in {"legacy_v1", "point_in_time"}:
        raise ValueError(f"context_mode desconocido: {mode}")
    if mode == "legacy_v1" and score_model_version != "1.0":
        raise ValueError("context_mode legacy_v1 solo está permitido con score_model_version 1.0")
    return mode


def fetch_point_in_time_market_context(
    provider: MarketDataProvider,
    config: MarketContextConfig,
    universe: Universe,
    analysis_timestamp: datetime,
    *,
    settlement_minutes: int,
) -> MarketContext:
    """Descarga contexto diario y aplica la semántica PIT de producción v2."""

    asia_symbols = tuple(
        sorted(asset.primary_symbol for asset in context_assets_of(universe) if asset.region == "ASIA")
    )
    symbols = (config.vix_symbol, config.trend_symbol, *asia_symbols)
    closes: dict[str, pd.Series] = {}
    for symbol in symbols:
        history = provider.get_history(symbol, period="2y", interval="1d")
        closes[symbol] = history["Close"]
    resolved = resolve_point_in_time_context(
        analysis_timestamp,
        closes,
        config,
        asia_symbols=asia_symbols,
        settlement_minutes=settlement_minutes,
    )
    if resolved.context is None:
        reasons = ", ".join((*resolved.exclusions, *resolved.no_calculable_codes)) or "contexto no calculable"
        raise RuntimeError(f"Contexto point-in-time no calculable: {reasons}")
    return resolved.context


def production_pass_times_from_timer(timer_text: str) -> tuple[time, ...]:
    """Extrae las pasadas del timer versionado, excluyendo el timer de eventos."""

    values: list[time] = []
    for raw_line in timer_text.splitlines():
        line = raw_line.strip()
        if not line.startswith("OnCalendar=Mon..Fri "):
            continue
        value = line.removeprefix("OnCalendar=Mon..Fri ")
        hour, minute = value.split(":", 1)
        values.append(time(int(hour), int(minute)))
    return tuple(values)


def scheduled_production_passes(start: datetime, end: datetime) -> list[datetime]:
    """Pasadas lun-vie del timer en Europe/London, convertidas a UTC."""

    current = start.astimezone(LONDON).date() - timedelta(days=1)
    last = end.astimezone(LONDON).date() + timedelta(days=1)
    passes: list[datetime] = []
    while current <= last:
        if current.weekday() < 5:
            for pass_time in PRODUCTION_PASS_TIMES:
                passes.append(datetime.combine(current, pass_time, LONDON).astimezone(timezone.utc))
        current += timedelta(days=1)
    return passes


def analysis_timestamp_for_signal(
    market: str,
    signal_session: date,
    entry_session: date,
    *,
    settlement_minutes: int,
) -> Optional[datetime]:
    """D-50: última pasada programada antes de la apertura de entrada."""

    session = market_session(market)
    if session.mic == CRYPTO_MIC:
        return None
    calendar = cast(Any, exchange_calendar(market))
    if entry_session not in expected_sessions(market, entry_session, entry_session):
        return None
    opened_at = calendar.session_open(pd.Timestamp(entry_session)).to_pydatetime()
    if opened_at.tzinfo is None:
        opened_at = opened_at.replace(tzinfo=timezone.utc)
    available_at = session_close_at(market, signal_session)
    if available_at is None:
        return None
    available_at = available_at + timedelta(minutes=settlement_minutes)
    candidates = [
        value
        for value in scheduled_production_passes(available_at, opened_at)
        if available_at <= value < opened_at
    ]
    return max(candidates) if candidates else None


def resolve_point_in_time_context(
    analysis_timestamp: datetime,
    closes: Mapping[str, pd.Series],
    config: MarketContextConfig,
    *,
    asia_symbols: Sequence[str],
    settlement_minutes: int,
) -> PointInTimeContextResult:
    """Resuelve VIX, tendencia/SMA200 y Asia con semántica D-52/D-53."""

    if analysis_timestamp.tzinfo is None:
        raise ValueError("analysis_timestamp debe ser aware")
    reference = analysis_timestamp.astimezone(timezone.utc)
    resolver = PointInTimeContextResolver(
        closes,
        config,
        asia_symbols=asia_symbols,
        settlement_minutes=settlement_minutes,
    )
    return resolver.resolve(reference)


def _resolve_point_in_time_context_prepared(
    reference: datetime,
    prepared: Mapping[str, PreparedContextSeries],
    config: MarketContextConfig,
    *,
    asia_symbols: Sequence[str],
    settlement_minutes: int,
) -> PointInTimeContextResult:
    """Resuelve contexto sobre series ya agrupadas por sesión."""

    vix_point = _latest_present_causal(
        prepared.get(config.vix_symbol),
        symbol=config.vix_symbol,
        reference=reference,
        settlement_minutes=settlement_minutes,
    )

    trend_points = _causal_points(
        prepared.get(config.trend_symbol),
        symbol=config.trend_symbol,
        reference=reference,
        settlement_minutes=settlement_minutes,
    )
    trend_market = market_for_symbol(config.trend_symbol)
    trend_expected = _latest_expected(trend_market, reference, settlement_minutes)
    trend_price: Optional[float] = None
    trend_sma: Optional[float] = None
    trend_used: Optional[date] = None
    stoxx_age_days: Optional[int] = None
    if trend_points:
        trend_used = trend_points[-1].session
        trend_price = trend_points[-1].value
        if trend_expected is not None:
            stoxx_age_days = (trend_expected - trend_used).days
        close = pd.Series([point.value for point in trend_points])
        if len(close) >= config.trend_sma:
            last_sma = sma(close, config.trend_sma).iloc[-1]
            trend_sma = float(last_sma) if last_sma == last_sma else None

    exclusions: list[str] = []
    no_calculable_codes: list[str] = []
    if vix_point is None:
        no_calculable_codes.append(NO_CALCULABLE_CONTEXT_VIX)
    if len(trend_points) < config.trend_sma:
        exclusions.append(EXCLUDED_TREND_SMA_HISTORY)
        no_calculable_codes.append(NO_CALCULABLE_CONTEXT_HISTORY)

    asia_change, asia_sessions, asia_missing = _asia_change(
        prepared,
        asia_symbols=asia_symbols,
        reference=reference,
        settlement_minutes=settlement_minutes,
    )
    if asia_missing:
        exclusions.append(EXCLUDED_ASIA_MISSING)

    context = None
    if not exclusions and not no_calculable_codes:
        assert vix_point is not None
        context = build_market_context(
            vix_point.value,
            trend_price,
            trend_sma,
            config,
            asia_change_pct=asia_change,
        )
        context = MarketContext(
            vix_value=context.vix_value,
            vix_threshold=context.vix_threshold,
            trend_price=context.trend_price,
            trend_sma=context.trend_sma,
            label=context.label,
            reason=context.reason,
            asia_change_pct=context.asia_change_pct,
            source="point_in_time",
        )

    return PointInTimeContextResult(
        analysis_timestamp=reference,
        context=context,
        exclusions=tuple(exclusions),
        no_calculable_codes=tuple(no_calculable_codes),
        vix_session=vix_point.session if vix_point is not None else None,
        trend_expected_session=trend_expected,
        trend_used_session=trend_used,
        trend_sma_count=len(trend_points),
        stoxx_age_days=stoxx_age_days,
        asia_sessions=asia_sessions,
        asia_missing=tuple(asia_missing),
    )


def point_in_time_contexts_for_index(
    index: pd.Index,
    *,
    signal_market: str,
    closes: Mapping[str, pd.Series],
    config: MarketContextConfig,
    asia_symbols: Sequence[str],
    settlement_minutes: int,
) -> list[PointInTimeContextResult | None]:
    """Contexto PIT para cada barra de señal de un DataFrame de laboratorio."""

    resolver = PointInTimeContextResolver(
        closes,
        config,
        asia_symbols=asia_symbols,
        settlement_minutes=settlement_minutes,
    )
    return resolver.contexts_for_index(index, signal_market=signal_market)


def prepare_context_closes(
    closes: Mapping[str, pd.Series],
    *,
    settlement_minutes: int,
) -> Mapping[str, PreparedContextSeries]:
    return {
        symbol: _prepare_series(series, symbol=symbol, settlement_minutes=settlement_minutes)
        for symbol, series in closes.items()
    }


def _latest_expected(market: str, reference: datetime, settlement_minutes: int) -> Optional[date]:
    from advisor.data.sessions import latest_expected_closed_session

    return latest_expected_closed_session(market, reference, settlement_minutes=settlement_minutes)


def _causal_points(
    series: Optional[PreparedContextSeries],
    *,
    symbol: str,
    reference: datetime,
    settlement_minutes: int,
) -> list[SeriesPoint]:
    if series is None or not series.points:
        return []
    cutoff = bisect_right(series.available_at, reference)
    return list(series.points[:cutoff])


def _latest_present_causal(
    series: Optional[PreparedContextSeries],
    *,
    symbol: str,
    reference: datetime,
    settlement_minutes: int,
) -> Optional[SeriesPoint]:
    points = _causal_points(
        series,
        symbol=symbol,
        reference=reference,
        settlement_minutes=settlement_minutes,
    )
    return points[-1] if points else None


def _asia_change(
    closes: Mapping[str, PreparedContextSeries],
    *,
    asia_symbols: Sequence[str],
    reference: datetime,
    settlement_minutes: int,
) -> tuple[Optional[float], Mapping[str, tuple[date, date]], list[AsiaMissing]]:
    changes: list[float] = []
    sessions: dict[str, tuple[date, date]] = {}
    missing: list[AsiaMissing] = []
    if not asia_symbols:
        return None, sessions, [AsiaMissing("ASIA", "sin series asiáticas en el universo", reference.date())]
    for symbol in asia_symbols:
        market = market_for_symbol(symbol)
        latest = _latest_expected(market, reference, settlement_minutes)
        if latest is None:
            missing.append(AsiaMissing(symbol, "falta_ultima_cerrada", reference.date()))
            continue
        previous = _previous_expected_session(market, latest)
        if previous is None:
            missing.append(AsiaMissing(symbol, "falta_anterior_cerrada", latest))
            continue
        prepared = closes.get(symbol)
        present = prepared.by_session if prepared is not None else {}
        if latest not in present:
            missing.append(AsiaMissing(symbol, "falta_ultima_cerrada", latest))
            continue
        if previous not in present:
            missing.append(AsiaMissing(symbol, "falta_anterior_cerrada", previous))
            continue
        previous_close = present[previous]
        if previous_close <= 0:
            missing.append(AsiaMissing(symbol, "falta_anterior_cerrada", previous))
            continue
        changes.append((present[latest] / previous_close - 1.0) * 100.0)
        sessions[symbol] = (latest, previous)
    if missing:
        return None, sessions, missing
    return (sum(changes) / len(changes) if changes else None), sessions, missing


def _prepare_series(series: Optional[pd.Series], *, symbol: str, settlement_minutes: int) -> PreparedContextSeries:
    if series is None or series.empty:
        return PreparedContextSeries(symbol, market_for_symbol(symbol), (), ())
    market = market_for_symbol(symbol)
    session_values: list[tuple[date, Any]] = []
    for raw_timestamp, raw_value in series.items():
        if pd.isna(raw_value):
            continue
        session = session_date_of(raw_timestamp, market)
        if session is None:
            continue
        session_values.append((session, raw_value))
    expected = _expected_session_set(market, [session for session, _ in session_values])
    present: dict[date, float] = {}
    for session, raw_value in session_values:
        if session not in expected:
            continue
        present[session] = float(raw_value)
    points: list[SeriesPoint] = []
    available: list[datetime] = []
    for session in sorted(present):
        available_at = _available_at(market, session, settlement_minutes)
        if available_at is None:
            continue
        points.append(SeriesPoint(session, present[session]))
        available.append(available_at)
    return PreparedContextSeries(symbol, market, tuple(points), tuple(available))


def _expected_session_set(market: str, sessions: Sequence[date]) -> set[date]:
    if not sessions:
        return set()
    return set(expected_sessions(market, min(sessions), max(sessions)))


@cache
def _available_at(market: str, session: date, settlement_minutes: int) -> Optional[datetime]:
    close_at = session_close_at(market, session)
    if close_at is None:
        return None
    return close_at + timedelta(minutes=settlement_minutes)


def _previous_expected_session(market: str, latest: date) -> Optional[date]:
    sessions = expected_sessions(market, latest - timedelta(days=45), latest - timedelta(days=1))
    return sessions[-1] if sessions else None
