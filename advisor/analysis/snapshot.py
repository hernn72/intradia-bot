"""Foto técnica de un activo: todos los indicadores que el asesor necesita,
calculados a partir del OHLCV ya descargado.

Núcleo puro: no descarga datos, no consulta la red, no escribe en disco.
Recibe un ``DataFrame`` y devuelve un ``TechnicalSnapshot``.

Los retornos se miden **en velas, no en calendario** (``return_short`` = 20
velas, ``return_medium`` = 60, ``return_long`` = 120). Así el mismo cálculo
sirve para el horizonte intradía (velas de 15 min) y para el de medio plazo
(velas diarias); es el informe quien traduce esas ventanas a lenguaje humano
según el intervalo analizado.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from advisor.config import IndicatorsConfig, LevelsConfig
from advisor.indicators.technical import ema, last_atr, macd, relative_strength, rsi, sma

RETURN_SHORT_BARS = 20
RETURN_MEDIUM_BARS = 60
RETURN_LONG_BARS = 120

# Nº de velas por año, por intervalo, para anualizar la volatilidad.
# Intradía: ~26 velas de 15 min por sesión × 252 sesiones.
_BARS_PER_YEAR = {
    "1d": 252,
    "1h": 6 * 252,
    "60m": 6 * 252,
    "30m": 13 * 252,
    "15m": 26 * 252,
    "5m": 78 * 252,
}


@dataclass(frozen=True)
class TechnicalSnapshot:
    """Estado técnico de un activo en un momento dado."""

    symbol: str
    timestamp: pd.Timestamp
    interval: str
    bars: int
    price: float
    ema_fast: Optional[float]
    ema_slow: Optional[float]
    sma_long: Optional[float]
    rsi: Optional[float]
    atr: Optional[float]
    macd: Optional[float]
    macd_signal: Optional[float]
    macd_hist: Optional[float]
    volume: Optional[float]
    volume_avg: Optional[float]
    volume_ratio: Optional[float]
    gap_pct: Optional[float]
    high_lookback: Optional[float]
    low_lookback: Optional[float]
    return_short: Optional[float]
    return_medium: Optional[float]
    return_long: Optional[float]
    volatility_pct: Optional[float]
    relative_strength: Optional[float]

    @property
    def trend_up(self) -> bool:
        """Tendencia alcista: EMA rápida por encima de la lenta y precio sobre la SMA larga.

        Sin SMA larga no se afirma: una tendencia de fondo que no se ha
        podido medir no se da por supuesta.
        """
        if self.ema_fast is None or self.ema_slow is None or self.sma_long is None:
            return False
        return self.ema_fast > self.ema_slow and self.price > self.sma_long

    @property
    def atr_pct(self) -> Optional[float]:
        """ATR como porcentaje del precio (volatilidad relativa)."""
        if self.atr is None or self.price <= 0:
            return None
        return self.atr / self.price * 100


def _last_float(series: pd.Series) -> Optional[float]:
    """Último valor de una serie como ``float``, o ``None`` si es NaN o está vacía."""
    if series is None or series.empty:
        return None
    value = series.iloc[-1]
    if value is None or pd.isna(value):
        return None
    return float(value)


def _bar_return(close: pd.Series, bars: int) -> Optional[float]:
    """Retorno porcentual respecto al cierre de ``bars`` velas atrás."""
    if len(close) <= bars:
        return None
    past = float(close.iloc[-(bars + 1)])
    if past == 0:
        return None
    return (float(close.iloc[-1]) / past - 1) * 100


def _annualized_volatility(close: pd.Series, interval: str) -> Optional[float]:
    """Volatilidad anualizada (%) de los retornos vela a vela."""
    if len(close) < 21:
        return None
    returns = close.pct_change().dropna()
    if returns.empty:
        return None
    std = float(returns.std())
    if math.isnan(std):
        return None
    bars_per_year = _BARS_PER_YEAR.get(interval, 252)
    return std * math.sqrt(bars_per_year) * 100


def build_snapshot(
    symbol: str,
    df: pd.DataFrame,
    indicators: IndicatorsConfig,
    levels: LevelsConfig,
    interval: str,
    benchmark_close: Optional[pd.Series] = None,
) -> TechnicalSnapshot:
    """Calcula el ``TechnicalSnapshot`` de ``symbol`` a partir de su OHLCV.

    Lanza ``ValueError`` si ``df`` está vacío o no tiene columna ``Close``.
    Los indicadores para los que no haya histórico suficiente quedan en
    ``None`` en vez de aproximarse con menos datos de los que necesitan.
    """

    if df is None or df.empty:
        raise ValueError(f"{symbol}: el histórico está vacío")
    if "Close" not in df.columns:
        raise ValueError(f"{symbol}: el histórico debe contener una columna 'Close'")

    close = df["Close"]
    price = float(close.iloc[-1])
    if price <= 0:
        raise ValueError(f"{symbol}: precio no válido ({price})")

    n = len(close)

    ema_fast = _last_float(ema(close, indicators.ema_fast)) if n >= indicators.ema_fast else None
    ema_slow = _last_float(ema(close, indicators.ema_slow)) if n >= indicators.ema_slow else None
    sma_long = _last_float(sma(close, indicators.sma_long)) if n >= indicators.sma_long else None
    rsi_value = _last_float(rsi(close, indicators.rsi_period)) if n > indicators.rsi_period else None
    atr_value = last_atr(df, indicators.atr_period) if n > indicators.atr_period else None

    macd_value = macd_signal_value = macd_hist_value = None
    if n >= indicators.macd_slow + indicators.macd_signal:
        macd_line, signal_line, hist = macd(
            close, indicators.macd_fast, indicators.macd_slow, indicators.macd_signal
        )
        macd_value = _last_float(macd_line)
        macd_signal_value = _last_float(signal_line)
        macd_hist_value = _last_float(hist)

    volume = volume_avg = volume_ratio = None
    if "Volume" in df.columns:
        volumes = df["Volume"].dropna()
        # Algunos activos (índices, ciertos ETFs) reportan volumen 0 en yfinance:
        # tratarlo como "sin dato" en vez de como volumen realmente nulo.
        if not volumes.empty and float(volumes.iloc[-1]) > 0:
            volume = float(volumes.iloc[-1])
            if len(volumes) > indicators.volume_lookback:
                avg = float(volumes.iloc[-(indicators.volume_lookback + 1):-1].mean())
                if avg > 0:
                    volume_avg = avg
                    volume_ratio = volume / avg

    gap_pct = None
    if "Open" in df.columns and n >= 2:
        prev_close = float(close.iloc[-2])
        current_open = df["Open"].iloc[-1]
        if prev_close > 0 and pd.notna(current_open):
            gap_pct = (float(current_open) / prev_close - 1) * 100

    high_lookback = low_lookback = None
    if n >= 2 and {"High", "Low"}.issubset(df.columns):
        window = df.iloc[-min(levels.lookback_bars, n):]
        high_lookback = float(window["High"].max())
        low_lookback = float(window["Low"].min())

    rs = None
    if benchmark_close is not None and not benchmark_close.empty:
        rs = relative_strength(close, benchmark_close, RETURN_SHORT_BARS)

    return TechnicalSnapshot(
        symbol=symbol,
        timestamp=df.index[-1],
        interval=interval,
        bars=n,
        price=price,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        sma_long=sma_long,
        rsi=rsi_value,
        atr=atr_value,
        macd=macd_value,
        macd_signal=macd_signal_value,
        macd_hist=macd_hist_value,
        volume=volume,
        volume_avg=volume_avg,
        volume_ratio=volume_ratio,
        gap_pct=gap_pct,
        high_lookback=high_lookback,
        low_lookback=low_lookback,
        return_short=_bar_return(close, RETURN_SHORT_BARS),
        return_medium=_bar_return(close, RETURN_MEDIUM_BARS),
        return_long=_bar_return(close, RETURN_LONG_BARS),
        volatility_pct=_annualized_volatility(close, interval),
        relative_strength=rs,
    )
