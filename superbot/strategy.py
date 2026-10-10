"""Estrategia ``itrade_trend_v1``: la de tendencia de iTrade Bot, portada.

Reglas (``trading-bot/app/strategies/trend_strategy.py``):
- BUY sin posición si ``Close > SMA rápida > SMA lenta`` y el RSI está en
  ``[rsi_entry_min, rsi_entry_max]``.
- SELL con posición si los últimos ``exit_confirm_days`` cierres están todos
  por debajo de ``SMA rápida × (1 − exit_buffer_pct)`` (cada uno contra su SMA
  de ese día) o si ``RSI > rsi_exit``.
- Stop inicial ``stop_loss_pct`` bajo la entrada y trailing ``Close − k·ATR``
  que solo sube (``trading-bot/app/paper/broker.py::update_trailing_stop``).

Los indicadores se calculan una vez sobre toda la serie y se leen por fila:
cada fila solo depende de barras anteriores o iguales, así que leer la fila
``i`` no mira al futuro.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from advisor.indicators.technical import atr, rsi, sma
from superbot.config import StrategyParams


@dataclass(frozen=True)
class Signal:
    action: str  # "BUY", "SELL" o "HOLD"
    reason: str


def enrich(df: pd.DataFrame, params: StrategyParams) -> pd.DataFrame:
    """Añade SMA rápida/lenta, RSI, ATR y la rotura confirmada de tendencia."""

    out = df.copy()
    out["sma_fast"] = sma(out["Close"], params.sma_fast)
    out["sma_slow"] = sma(out["Close"], params.sma_slow)
    out["rsi"] = rsi(out["Close"], params.rsi_period)
    out["atr"] = atr(out, params.atr_period)
    below = (out["Close"] < out["sma_fast"] * (1 - params.exit_buffer_pct)) & out["sma_fast"].notna()
    confirm = max(1, params.exit_confirm_days)
    out["trend_break"] = below.astype(int).rolling(confirm, min_periods=confirm).sum() == confirm
    return out


def _value(row: pd.Series, column: str) -> Optional[float]:
    value = row.get(column)
    return float(value) if value is not None and pd.notna(value) else None


def evaluate(row: pd.Series, params: StrategyParams, has_position: bool) -> Signal:
    """Señal al cierre de la barra ``row`` (ya enriquecida con :func:`enrich`)."""

    close = float(row["Close"])
    fast = _value(row, "sma_fast")
    slow = _value(row, "sma_slow")
    rsi_value = _value(row, "rsi")
    if fast is None or slow is None or rsi_value is None:
        return Signal("HOLD", "Datos insuficientes para calcular los indicadores")

    if has_position:
        if bool(row.get("trend_break", False)):
            return Signal("SELL", "Rotura de tendencia confirmada bajo la SMA rápida")
        if rsi_value > params.rsi_exit:
            return Signal("SELL", f"RSI {rsi_value:.1f} por encima de {params.rsi_exit:g}")
        return Signal("HOLD", "Posición mantenida")

    uptrend = close > fast > slow
    rsi_ok = params.rsi_entry_min <= rsi_value <= params.rsi_entry_max
    if uptrend and rsi_ok:
        return Signal(
            "BUY",
            f"Tendencia alcista (Close > SMA{params.sma_fast} > SMA{params.sma_slow}) y RSI {rsi_value:.1f} en rango",
        )
    return Signal("HOLD", "Condiciones de entrada no cumplidas")


def momentum_score(close: pd.Series, params: StrategyParams) -> Optional[float]:
    """Score de momentum de iTrade para ordenar compras simultáneas.

    ``w3·ret3m + w6·ret6m + w12·ret12m`` (pesos normalizados sobre los
    componentes con histórico suficiente); solo si es positivo entra la
    volatilidad inversa como desempate. ``None`` con menos de 3 meses.
    """

    n = len(close)
    if n < params.momentum_lookback_3m:
        return None
    current = float(close.iloc[-1])
    components = [(params.momentum_3m_weight, (current / float(close.iloc[-params.momentum_lookback_3m]) - 1) * 100)]
    if n >= params.momentum_lookback_6m:
        components.append(
            (params.momentum_6m_weight, (current / float(close.iloc[-params.momentum_lookback_6m]) - 1) * 100)
        )
    if n >= params.momentum_lookback_12m:
        components.append(
            (params.momentum_12m_weight, (current / float(close.iloc[-params.momentum_lookback_12m]) - 1) * 100)
        )
    pure = sum(w * v for w, v in components) / sum(w for w, _ in components)
    if pure <= 0:
        return pure
    lookback = min(n, params.momentum_vol_lookback)
    daily_vol = float(close.pct_change().dropna().iloc[-lookback:].std())
    inv_vol = 100.0 / (daily_vol * (252 ** 0.5) * 100 + 100.0)
    components.append((params.inv_vol_weight, inv_vol))
    return sum(w * v for w, v in components) / sum(w for w, _ in components)


def initial_levels(fill_price: float, params: StrategyParams) -> tuple[float, float, float]:
    """Stop inicial y objetivos T1/T2 a partir del precio de entrada."""

    stop = fill_price * (1 - params.stop_loss_pct)
    risk = fill_price - stop
    return stop, fill_price + params.target1_r * risk, fill_price + params.target2_r * risk


def trailed_stop(current_stop: float, close: float, atr_value: Optional[float], params: StrategyParams) -> float:
    """Nuevo stop tras la barra: ``Close − k·ATR`` si mejora el actual; nunca baja."""

    if atr_value is None or atr_value <= 0:
        return current_stop
    return max(current_stop, close - params.atr_multiplier * atr_value)
