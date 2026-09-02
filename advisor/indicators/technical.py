"""Indicadores técnicos del asesor.

``sma``, ``rsi``, ``atr`` y ``last_atr`` son una copia literal de
``app/indicators/technical.py`` del proyecto trading-bot (módulo puro, sin
dependencias del resto de aquel paquete). Se copian en vez de importarse para
que este bot sea independiente; si allí se corrige un cálculo, hay que
replicarlo aquí.

``ema``, ``macd`` y ``relative_strength`` son nuevos: el análisis técnico que
pide el asesor (EMA 20/50, MACD, fortaleza relativa) va más allá del que
necesitaba la estrategia de tendencia original.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range sobre ``period`` periodos.

    Requiere columnas ``High``, ``Low`` y ``Close`` en ``df``.
    """

    if period <= 0:
        raise ValueError("period debe ser mayor que 0")
    if df is None or df.empty:
        raise ValueError("df no puede estar vacío")
    for col in ("High", "Low", "Close"):
        if col not in df.columns:
            raise ValueError(f"df debe contener la columna '{col}'")

    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)

    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)

    return tr.rolling(window=period, min_periods=period).mean()


def last_atr(window: pd.DataFrame, period: int) -> float | None:
    """Último valor de ATR, o ``None`` si faltan columnas OHLC o histórico."""

    if not {"High", "Low", "Close"}.issubset(window.columns):
        return None
    series = atr(window, period)
    last = series.iloc[-1]
    return float(last) if pd.notna(last) else None


def sma(series: pd.Series, window: int) -> pd.Series:
    """Media móvil simple sobre ``window`` periodos."""

    if window <= 0:
        raise ValueError("window debe ser mayor que 0")
    if series.empty:
        raise ValueError("series no puede estar vacía")

    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    """Media móvil exponencial sobre ``window`` periodos.

    ``min_periods=window`` evita que las primeras velas produzcan un valor
    apoyado en muy pocos datos, igual que hace ``sma``.
    """

    if window <= 0:
        raise ValueError("window debe ser mayor que 0")
    if series.empty:
        raise ValueError("series no puede estar vacía")

    return series.ewm(span=window, adjust=False, min_periods=window).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (RSI) sobre ``period`` periodos.

    Casos límite:
    - Si en una ventana no hay pérdidas y sí ganancias -> RSI = 100.
    - Si no hay ganancias ni pérdidas (precio plano) -> RSI = 50 (neutro).
    """

    if period <= 0:
        raise ValueError("period debe ser mayor que 0")
    if series.empty:
        raise ValueError("series no puede estar vacía")

    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))

    result = result.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    result = result.mask((avg_loss == 0) & (avg_gain == 0), 50.0)

    return result


def macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """MACD: devuelve ``(macd, señal, histograma)``.

    A diferencia de ``ema``, las EMAs internas usan ``min_periods`` corto
    (el de ``ewm`` por defecto) porque el MACD estándar se calcula así; el
    histograma solo es fiable a partir de ``slow + signal`` velas, algo que
    el llamante controla mediante ``min_bars``.
    """

    if fast <= 0 or slow <= 0 or signal <= 0:
        raise ValueError("fast, slow y signal deben ser mayores que 0")
    if fast >= slow:
        raise ValueError(f"fast ({fast}) debe ser menor que slow ({slow})")
    if series.empty:
        raise ValueError("series no puede estar vacía")

    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line, macd_line - signal_line


def relative_strength_series(series: pd.Series, benchmark: pd.Series, lookback: int) -> pd.Series:
    """Fortaleza relativa por intersección de sesiones comunes.

    Activo y benchmark se reducen simétricamente a las mismas fechas antes de
    calcular retornos. No se arrastra el último cierre del benchmark ni se
    compara por posición de índice.
    """

    if lookback <= 0:
        raise ValueError("lookback debe ser mayor que 0")
    if series.empty:
        raise ValueError("series no puede estar vacía")
    if benchmark.empty:
        return pd.Series(index=series.index, dtype=float)

    asset = series.dropna().copy()
    bench = benchmark.dropna().copy()
    asset_dates = _session_index(asset.index)
    bench_dates = _session_index(bench.index)
    asset.index = asset_dates
    bench.index = bench_dates
    asset = asset[~asset.index.duplicated(keep="last")]
    bench = bench[~bench.index.duplicated(keep="last")]

    common = asset.index.intersection(bench.index)
    if len(common) <= lookback:
        return pd.Series(index=series.index, dtype=float)

    aligned_asset = asset.reindex(common)
    aligned_bench = bench.reindex(common)
    rs_common = aligned_asset.pct_change(lookback) * 100 - aligned_bench.pct_change(lookback) * 100

    target = _session_index(series.index)
    values = rs_common.reindex(target)
    values.index = series.index
    return values


def relative_strength(series: pd.Series, benchmark: pd.Series, lookback: int) -> float | None:
    """Fortaleza relativa: diferencia (en puntos porcentuales) entre el retorno
    del activo y el del índice de referencia en las últimas ``lookback`` velas.

    Devuelve ``None`` si alguna de las series no tiene histórico suficiente o
    si el precio de partida es cero. Positivo = el activo lo hace mejor que su
    referencia.
    """

    values = relative_strength_series(series, benchmark, lookback)
    if values.empty:
        return None
    value = values.iloc[-1]
    if pd.isna(value):
        return None
    return float(value)


def _session_index(index: pd.Index) -> pd.Index:
    if isinstance(index, pd.DatetimeIndex):
        idx = index
    else:
        try:
            idx = pd.DatetimeIndex(index)
        except (TypeError, ValueError):
            return pd.Index(index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return idx.normalize()
