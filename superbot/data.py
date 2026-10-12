"""Carga de barras diarias cerradas y tipos de cambio para la cartera visible.

Reutiliza las piezas de datos del asesor (proveedor yfinance, universo,
plazas y recorte de la barra no cerrada) sin pasar por su análisis ni por su
puntuación: aquí solo entran precios.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, Iterable, List, Optional, Protocol, Set

import pandas as pd

from advisor.data.freshness import mercado_para_simbolo
from advisor.data.sessions import session_date_of, trim_unclosed_bar
from advisor.universe.models import Asset, Universe
from superbot.config import SuperbotConfig
from superbot.engine import BarSeries
from superbot.strategy import enrich

logger = logging.getLogger(__name__)


class HistoryProvider(Protocol):
    def get_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame: ...


@dataclass
class LoadResult:
    series: Dict[str, BarSeries] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)


def select_assets(universe: Universe, config: SuperbotConfig, extra_symbols: Iterable[str] = ()) -> List[Asset]:
    """Activos recomendables de los grupos configurados, más los que tengan posición u orden viva."""

    selected = {a.symbol: a for a in universe.analizables(config.groups) if a.is_recommendable}
    for symbol in extra_symbols:
        asset = universe.get(symbol)
        if asset is not None:
            selected.setdefault(asset.symbol, asset)
    return [selected[s] for s in sorted(selected)]


def _by_session(df: pd.DataFrame, market: str) -> pd.DataFrame:
    sessions = [session_date_of(ts, market) for ts in df.index]
    if any(s is None for s in sessions):
        raise ValueError(f"plaza {market} sin zona horaria declarada")
    out = df.copy()
    out.index = pd.Index(sessions, name="session")
    # Dos barras en la misma sesión (cambio de horario del proveedor): vale la última.
    return out[~out.index.duplicated(keep="last")]


def load_series(
    assets: Iterable[Asset], provider: HistoryProvider, config: SuperbotConfig, now: datetime
) -> LoadResult:
    result = LoadResult()
    for asset in assets:
        try:
            market = mercado_para_simbolo(asset, asset.symbol)
            raw = provider.get_history(asset.symbol, period=config.history_period, interval="1d")
            trimmed = trim_unclosed_bar(
                raw, market=market, reference=now, settlement_minutes=config.settlement_minutes
            ).df
            frame = trimmed[["Open", "High", "Low", "Close"]].dropna()
            if "Stock Splits" in trimmed.columns:
                frame = frame.assign(**{"Stock Splits": trimmed["Stock Splits"].reindex(frame.index).fillna(0.0)})
            frame = _by_session(frame, market)
            if len(frame) < config.strategy.sma_slow:
                raise ValueError(f"histórico insuficiente: {len(frame)} sesiones")
            result.series[asset.symbol] = BarSeries(
                symbol=asset.symbol, name=asset.name, currency=asset.currency.upper(),
                frame=enrich(frame, config.strategy), market=market,
            )
        except Exception as exc:  # un símbolo sin datos no para la cartera
            logger.warning("%s: %s", asset.symbol, exc)
            result.errors[asset.symbol] = str(exc)
    return result


class FxHistory:
    """EUR por unidad de divisa, vigente en cada sesión (último cierre ≤ fecha).

    Cada fill guarda el tipo de su sesión, así que una ejecución posterior no
    revaloriza el pasado con el tipo del día.
    """

    def __init__(self, provider: HistoryProvider, currencies: Set[str], period: str) -> None:
        self._rates: Dict[str, pd.Series] = {}
        for currency in sorted(currencies - {"EUR"}):
            try:
                raw = provider.get_history(f"EUR{currency}=X", period=period, interval="1d")
                closes = raw["Close"].dropna()
                closes = closes[closes > 0]
                series = pd.Series(
                    1.0 / closes.to_numpy(), index=[ts.date() for ts in closes.index]
                )
                self._rates[currency] = series[~series.index.duplicated(keep="last")].sort_index()
            except Exception as exc:
                logger.warning("Sin tipo de cambio EUR/%s: %s", currency, exc)

    def rate(self, currency: str, on: date) -> Optional[float]:
        if currency == "EUR":
            return 1.0
        series = self._rates.get(currency)
        if series is None or series.empty:
            return None
        eligible = series[series.index <= on]
        return float(eligible.iloc[-1]) if not eligible.empty else None
