"""Universo, calendarios y pasadas de T-025 (ficha §6, §7.1; D-50).

El universo es el de P6: 90 activos (``asset_list_sha256 36355796…``), sin altas ni bajas. Los calendarios,
las marcas de apertura y cierre y las pasadas programadas salen de ``advisor`` (INV-06), no se copian.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple

UTC = timezone.utc
FX_MARKET = "FX"
SNAPSHOT_TIME = time(23, 59, 59)


@dataclass(frozen=True)
class PaperAsset:
    symbol: str
    data_symbol: str
    market: str
    currency: str
    economic_currency: str
    region: str
    sector: str
    instrument_id: str
    benchmark_symbol: Optional[str] = None


@dataclass(frozen=True)
class PaperUniverse:
    assets: Tuple[PaperAsset, ...]
    context_symbols: Tuple[str, ...]
    asia_symbols: Tuple[str, ...]
    vix_symbol: str
    trend_symbol: str
    settlement_minutes: int

    def by_symbol(self) -> Dict[str, PaperAsset]:
        return {asset.symbol: asset for asset in self.assets}

    def currencies(self) -> Tuple[str, ...]:
        return tuple(sorted({a.currency for a in self.assets if a.currency != "EUR"}))

    def fx_pairs(self) -> Tuple[str, ...]:
        return tuple(f"EUR{currency}=X" for currency in self.currencies())

    def benchmark_symbols(self) -> Tuple[str, ...]:
        return tuple(sorted({a.benchmark_symbol for a in self.assets if a.benchmark_symbol} - {a.symbol for a in self.assets}))

    def market_of(self, symbol: str) -> str:
        for asset in self.assets:
            if asset.data_symbol == symbol:
                return asset.market
        from advisor.data.sessions import market_for_symbol

        return market_for_symbol(symbol)


def load_p6_universe() -> PaperUniverse:
    """El universo congelado de P6, con el mapa sectorial verificado por su sha256."""

    from advisor.analysis.benchmark import resolve_benchmark_symbol
    from advisor.analysis.overview import context_assets_of
    from advisor.data.freshness import mercado_para_simbolo
    from advisor.research import p6

    config, universe = p6._sources()
    sectors = p6.load_sector_map()
    assets: List[PaperAsset] = []
    for symbol in p6.asset_list():
        asset = universe.get(symbol)
        if asset is None:
            raise RuntimeError(f"{symbol}: no está en universe.yaml")
        assets.append(
            PaperAsset(
                symbol=symbol, data_symbol=symbol, market=mercado_para_simbolo(asset, symbol),
                currency=asset.primary_currency or asset.currency, economic_currency=asset.economic_currency,
                region=asset.region, sector=sectors[symbol], instrument_id=asset.instrument_id or symbol,
                benchmark_symbol=resolve_benchmark_symbol(asset, config.report),
            )
        )
    asia = tuple(sorted(a.primary_symbol for a in context_assets_of(universe) if a.region == "ASIA"))
    context = (config.market_context.vix_symbol, config.market_context.trend_symbol, *asia)
    return PaperUniverse(
        assets=tuple(assets), context_symbols=context, asia_symbols=asia, vix_symbol=config.market_context.vix_symbol,
        trend_symbol=config.market_context.trend_symbol, settlement_minutes=config.data_quality.settlement_minutes,
    )


# ---------------------------------------------------------------------------- calendarios


@lru_cache(maxsize=4096)
def _sessions(market: str, start: date, end: date) -> Tuple[date, ...]:
    if market == FX_MARKET:
        out: List[date] = []
        day = start
        while day <= end:
            if day.weekday() < 5:
                out.append(day)
            day += timedelta(days=1)
        return tuple(out)
    from advisor.data.calendars import expected_sessions

    return tuple(expected_sessions(market, start, end))


def sessions(market: str, start: date, end: date) -> Tuple[date, ...]:
    return _sessions(market, start, end)


@lru_cache(maxsize=65536)
def open_close(market: str, day: date) -> Tuple[datetime, datetime]:
    """Apertura y cierre reales en UTC (las de ``p6.bar_times``); FX: el día UTC completo."""

    if market == FX_MARKET:
        start = datetime.combine(day, time(0, 0), UTC)
        return start, start + timedelta(hours=23, minutes=59)
    from advisor.research.p6 import bar_times

    opens, closes = bar_times(market, (day,))
    return opens[0], closes[0]


def next_session(market: str, day: date) -> date:
    following = sessions(market, day + timedelta(days=1), day + timedelta(days=20))
    if not following:
        raise RuntimeError(f"{market}: sin sesión en los 20 días posteriores a {day}")
    return following[0]


def closed_by(market: str, day: date, at: datetime, settlement_minutes: int) -> bool:
    """La barra de ``day`` ya se puede exigir en ``at`` (cierre más liquidación)."""

    if market == FX_MARKET:
        return at >= datetime.combine(day + timedelta(days=1), time(0, 0), UTC) + timedelta(minutes=settlement_minutes)
    return at >= open_close(market, day)[1] + timedelta(minutes=settlement_minutes)


def scheduled_passes(start: datetime, end: datetime) -> List[datetime]:
    from advisor.context.point_in_time import scheduled_production_passes

    return [p for p in scheduled_production_passes(start, end) if start <= p <= end]


def binding_pass(market: str, signal_session: date, entry_session: date, settlement_minutes: int) -> Optional[datetime]:
    """D-50: la última pasada programada antes de la apertura de la sesión de entrada."""

    from advisor.context.point_in_time import analysis_timestamp_for_signal

    return analysis_timestamp_for_signal(market, signal_session, entry_session, settlement_minutes=settlement_minutes)


def snapshot_days(markets: Sequence[str], start: date, end: date) -> Tuple[date, ...]:
    days: set[date] = set()
    for market in set(markets):
        days.update(sessions(market, start, end))
    return tuple(sorted(days))
