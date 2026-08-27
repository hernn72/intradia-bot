"""Fixtures compartidas: datos sintéticos y objetos de configuración.

Ningún test toca la red. Los precios se generan de forma determinista para
que un fallo sea siempre reproducible.
"""

from __future__ import annotations

from typing import List, Optional

import pandas as pd
import pytest

from advisor.analysis.market_context import MarketContext
from advisor.config import AdvisorConfig
from advisor.universe.models import Asset, Universe


def make_ohlcv(
    n: int = 300,
    start: float = 100.0,
    drift: float = 0.3,
    volume: float = 1_000_000.0,
    last_volume: Optional[float] = None,
    start_date: str = "2026-01-01",
) -> pd.DataFrame:
    """Serie OHLCV sintética con tendencia lineal y rango intradía constante.

    ``drift`` es el incremento por vela: positivo genera tendencia alcista.
    """

    index = pd.date_range(start=start_date, periods=n, freq="D", tz="UTC")
    closes = [start + drift * i for i in range(n)]
    opens = [c - drift * 0.5 for c in closes]
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    volumes: List[float] = [volume] * n
    if last_volume is not None:
        volumes[-1] = last_volume

    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes},
        index=index,
    )


class FakeProvider:
    """Sustituto de ``MarketDataProvider`` que sirve datos de un diccionario."""

    def __init__(self, histories: Optional[dict] = None, closes: Optional[dict] = None) -> None:
        self.histories = histories or {}
        self.closes = closes or {}
        self.calls: List[str] = []

    def get_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        self.calls.append(symbol)
        if symbol not in self.histories:
            raise ValueError(f"sin datos para '{symbol}'")
        return self.histories[symbol]

    def get_last_close(self, symbol: str, period: str = "5d", interval: str = "1d"):
        self.calls.append(symbol)
        if symbol in self.closes:
            return self.closes[symbol], pd.Timestamp("2026-08-27", tz="UTC")
        if symbol in self.histories:
            history = self.histories[symbol]
            return float(history["Close"].iloc[-1]), history.index[-1]
        return None, None


@pytest.fixture
def config() -> AdvisorConfig:
    """Configuración mínima válida, equivalente a la del ``config.yaml`` real."""

    return AdvisorConfig(
        base_currency="EUR",
        horizontes={
            "intradia": {"interval": "15m", "period": "60d", "min_bars": 120},
            "swing": {"interval": "1d", "period": "1y", "min_bars": 120},
            "medio": {"interval": "1d", "period": "2y", "min_bars": 250},
        },
    )


@pytest.fixture
def asset_eur() -> Asset:
    return Asset(
        symbol="SAP.DE",
        name="SAP",
        asset_class="stock",
        region="EUROPA",
        market="XETRA",
        currency="EUR",
        timezone="Europe/Berlin",
        trade_republic="yes",
        isin=None,
    )


@pytest.fixture
def asset_usd() -> Asset:
    return Asset(
        symbol="AAPL",
        name="Apple",
        asset_class="stock",
        region="USA",
        market="NASDAQ",
        currency="USD",
        timezone="America/New_York",
        trade_republic="unknown",
    )


@pytest.fixture
def universe(asset_eur: Asset, asset_usd: Asset) -> Universe:
    context_index = Asset(
        symbol="^STOXX50E",
        name="Euro Stoxx 50",
        asset_class="index",
        region="EUROPA",
        market="EU",
        currency="EUR",
        timezone="Europe/Berlin",
        analizable=False,
    )
    return Universe(groups={"europa": [asset_eur], "usa": [asset_usd], "contexto": [context_index]})


@pytest.fixture
def benign_context() -> MarketContext:
    """Contexto de mercado favorable, para aislar el efecto del activo."""

    return MarketContext(
        vix_value=14.0,
        vix_threshold=25.0,
        trend_price=5000.0,
        trend_sma=4800.0,
        label="RISK_ON",
        reason="tendencia alcista y volatilidad contenida",
    )


@pytest.fixture
def hostile_context() -> MarketContext:
    return MarketContext(
        vix_value=32.0,
        vix_threshold=25.0,
        trend_price=4500.0,
        trend_sma=4800.0,
        label="RISK_OFF",
        reason="VIX 32,0 ≥ 25,0 y tendencia no alcista",
    )
