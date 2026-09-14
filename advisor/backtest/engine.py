"""Motor de backtest del asesor: reproduce sus señales sobre el pasado.

Responde a la pregunta que ninguna recomendación puede responder por sí
misma: ¿la puntuación y los vetos del asesor tienen ventaja medible, o solo
son un criterio razonado? Para cada vela histórica se calcula exactamente lo
que el asesor habría calculado ese día —foto técnica, niveles, puntuación y
decisión— usando solo datos anteriores a esa vela, y se simula la operación
con las reglas que el asesor da al humano: entrada en la apertura siguiente,
stop y objetivos fijados al entrar y nunca recalculados.

Núcleo puro: recibe DataFrames y series ya descargados, no toca la red.

Limitaciones asumidas (y declaradas en el informe):

- Una posición por activo: las señales que llegan con posición abierta se
  pierden, igual que le pasaría a un humano con el capital comprometido.
- Sin deslizamiento: las salidas se cruzan al precio exacto del stop o del
  objetivo salvo hueco de apertura, que se cruza a la apertura.
- Si una misma vela toca stop y objetivo, se asume stop (el caso peor).
- Sin señal asiática histórica: esa parte del contexto puntúa neutra.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from advisor.analysis.execution import evaluate_trade_at_entry
from advisor.analysis.levels import compute_levels
from advisor.analysis.market_context import build_market_context
from advisor.analysis.opportunity import ACCION_COMPRAR, classify
from advisor.analysis.scoring import compute_score
from advisor.analysis.snapshot import SnapshotSeries, build_snapshot, build_snapshot_series, snapshot_from_series
from advisor.config import AdvisorConfig
from advisor.research.observations import build_signal_observation
from advisor.universe.models import Asset

# Política de entrada del backtest:
#   operar → solo las señales que el asesor habría marcado COMPRAR (su política real)
#   todas  → cualquier vela con niveles válidos, registrando qué habría dicho
#            el asesor; sirve para comparar tramos de puntuación y vetos.
POLICY_OPERAR = "operar"
POLICY_TODAS = "todas"

# Máximo de velas en posición por horizonte, según la duración que la
# especificación asigna a cada tipo de operación: swing 2 días-8 semanas,
# medio 1-12 meses. Al agotarse se sale al cierre: la tesis era de ese plazo.
MAX_HOLD_BARS = {"swing": 40, "medio": 250}

EXIT_STOP = "stop"
EXIT_TARGET = "objetivo"
EXIT_TIME = "tiempo"
EXIT_FINAL = "final"


@dataclass(frozen=True)
class BacktestTrade:
    """Una operación simulada, con la decisión que el asesor tomó al entrar."""

    symbol: str
    score: float
    radar: str
    accion: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    stop: float
    target: float
    exit_reason: str
    bars_held: int
    cost_pct: float

    @property
    def gross_return_pp(self) -> float:
        return (self.exit_price / self.entry_price - 1) * 100

    @property
    def net_return_pp(self) -> float:
        """Retorno tras el coste de ida y vuelta (comisiones fijas en %)."""
        return self.gross_return_pp - self.cost_pct

    @property
    def risk_pp(self) -> float:
        return (self.entry_price - self.stop) / self.entry_price * 100

    @property
    def gross_r_multiple(self) -> Optional[float]:
        """Resultado en múltiplos del riesgo asumido al entrar (bruto)."""
        risk = self.entry_price - self.stop
        if risk <= 0:
            return None
        return (self.exit_price - self.entry_price) / risk

    @property
    def net_r_multiple(self) -> Optional[float]:
        """Resultado neto en múltiplos del riesgo asumido al entrar."""
        if self.risk_pp <= 0:
            return None
        return self.net_return_pp / self.risk_pp

    @property
    def won(self) -> bool:
        return self.net_return_pp > 0


def _signal_from_snapshot(
    asset: Asset,
    snapshot,
    j: int,
    config: AdvisorConfig,
    horizonte: str,
    min_bars: int,
    vix_at: Optional[Sequence[Optional[float]]],
    trend_price_at: Optional[Sequence[Optional[float]]],
    trend_sma_at: Optional[Sequence[Optional[float]]],
) -> Optional[Dict[str, Any]]:
    levels = compute_levels(snapshot, config.levels, config.risk.min_rr_ratio)
    if levels is None:
        return None

    context = build_market_context(
        vix_at[j] if vix_at is not None else None,
        trend_price_at[j] if trend_price_at is not None else None,
        trend_sma_at[j] if trend_sma_at is not None else None,
        config.market_context,
    )
    score = compute_score(snapshot, levels, context, config.scoring, min_bars)
    radar, accion, _ = classify(score, levels, context, config.scoring, config.risk, asset, horizonte)

    return {
        "score": score.value,
        "radar": radar,
        "accion": accion,
        "stop": levels.stop,
        "target": levels.target2,
        "entry_max": levels.entry_max,
        "levels": levels,
        "observation": build_signal_observation(
            asset=asset,
            horizonte=horizonte,
            signal_idx=j,
            snapshot=snapshot,
            score=score,
        ),
    }


def _signal_prefix(
    asset: Asset,
    df: pd.DataFrame,
    j: int,
    config: AdvisorConfig,
    horizonte: str,
    interval: str,
    min_bars: int,
    benchmark_close: Optional[pd.Series],
    vix_at: Optional[Sequence[Optional[float]]],
    trend_price_at: Optional[Sequence[Optional[float]]],
    trend_sma_at: Optional[Sequence[Optional[float]]],
) -> Optional[Dict[str, Any]]:
    """Evalúa la señal al cierre de la vela ``j`` con datos hasta esa vela."""

    prefix = df.iloc[: j + 1]
    try:
        snapshot = build_snapshot(asset.symbol, prefix, config.indicators, config.levels, interval, benchmark_close)
    except ValueError:
        return None

    return _signal_from_snapshot(
        asset, snapshot, j, config, horizonte, min_bars, vix_at, trend_price_at, trend_sma_at
    )


def _signal(
    asset: Asset,
    snapshot_series: SnapshotSeries,
    j: int,
    config: AdvisorConfig,
    horizonte: str,
    min_bars: int,
    vix_at: Optional[Sequence[Optional[float]]],
    trend_price_at: Optional[Sequence[Optional[float]]],
    trend_sma_at: Optional[Sequence[Optional[float]]],
) -> Optional[Dict[str, Any]]:
    """Evalúa la señal al cierre de la vela ``j`` desde indicadores precalculados."""

    try:
        snapshot = snapshot_from_series(asset.symbol, snapshot_series, j)
    except ValueError:
        return None
    return _signal_from_snapshot(
        asset, snapshot, j, config, horizonte, min_bars, vix_at, trend_price_at, trend_sma_at
    )


def _check_exit(
    bar: pd.Series, stop: float, target: float, entry_bar: bool
) -> Tuple[Optional[float], Optional[str]]:
    """Salida en esta vela, si la hay. Con stop y objetivo en la misma vela
    se asume stop: el orden intradía es inobservable en velas diarias y el
    backtest debe medir el caso peor, no el favorable."""

    bar_open = float(bar["Open"])
    if not entry_bar and bar_open <= stop:
        return bar_open, EXIT_STOP  # hueco por debajo del stop: se cruza a la apertura
    if float(bar["Low"]) <= stop:
        return stop, EXIT_STOP
    if not entry_bar and bar_open >= target:
        return bar_open, EXIT_TARGET
    if float(bar["High"]) >= target:
        return target, EXIT_TARGET
    return None, None


def simulate_asset(
    asset: Asset,
    df: pd.DataFrame,
    config: AdvisorConfig,
    horizonte: str,
    policy: str,
    cost_pct: float,
    benchmark_close: Optional[pd.Series] = None,
    vix_at: Optional[Sequence[Optional[float]]] = None,
    trend_price_at: Optional[Sequence[Optional[float]]] = None,
    trend_sma_at: Optional[Sequence[Optional[float]]] = None,
    min_bars: Optional[int] = None,
) -> List[BacktestTrade]:
    """Simula todas las operaciones de ``asset`` sobre su histórico.

    ``benchmark_close`` y las secuencias de contexto deben venir alineadas
    con el índice de ``df`` (una entrada por vela). ``min_bars`` permite a
    los tests acortar el calentamiento; en producción sale del horizonte.
    """

    if policy not in (POLICY_OPERAR, POLICY_TODAS):
        raise ValueError(f"política desconocida: '{policy}'")
    if horizonte not in MAX_HOLD_BARS:
        raise ValueError(f"horizonte sin backtest: '{horizonte}' (solo swing y medio)")

    window = config.horizonte(horizonte)
    warmup = min_bars if min_bars is not None else window.min_bars
    max_hold = MAX_HOLD_BARS[horizonte]

    trades: List[BacktestTrade] = []
    position: Optional[Dict[str, Any]] = None
    pending: Optional[Dict[str, Any]] = None
    try:
        snapshot_series = build_snapshot_series(df, config.indicators, config.levels, window.interval, benchmark_close)
    except ValueError:
        return []

    def close_position(j: int, exit_price: float, reason: str) -> BacktestTrade:
        assert position is not None
        return BacktestTrade(
            symbol=asset.symbol,
            score=position["score"],
            radar=position["radar"],
            accion=position["accion"],
            entry_date=df.index[position["entry_index"]],
            exit_date=df.index[j],
            entry_price=position["entry_price"],
            exit_price=exit_price,
            stop=position["stop"],
            target=position["target"],
            exit_reason=reason,
            bars_held=j - position["entry_index"],
            cost_pct=cost_pct,
        )

    for j in range(warmup, len(df)):
        bar = df.iloc[j]

        if position is not None:
            exit_price, reason = _check_exit(bar, position["stop"], position["target"], entry_bar=False)
            if exit_price is None and j - position["entry_index"] >= max_hold:
                exit_price, reason = float(bar["Close"]), EXIT_TIME
            if exit_price is not None and reason is not None:
                trades.append(close_position(j, exit_price, reason))
                position = None

        if position is None and pending is not None:
            bar_open = float(bar["Open"])
            execution = evaluate_trade_at_entry(
                levels=pending["levels"],
                entry_price=bar_open,
                risk=config.risk,
                portfolio=config.portfolio,
                label="backtest",
            )
            # Disciplina de entrada del asesor: la apertura debe ser ejecutable
            # con el mismo RR, stop y tamaño que se usarían en producción.
            if execution.executable:
                position = dict(pending, entry_index=j, entry_price=bar_open)
                exit_price, reason = _check_exit(bar, position["stop"], position["target"], entry_bar=True)
                if exit_price is not None and reason is not None:
                    trades.append(close_position(j, exit_price, reason))
                    position = None
            pending = None

        if position is None and j < len(df) - 1:
            signal = _signal(
                asset, snapshot_series, j, config, horizonte, warmup,
                vix_at, trend_price_at, trend_sma_at,
            )
            if signal is not None and (policy == POLICY_TODAS or signal["accion"] == ACCION_COMPRAR):
                pending = signal

    if position is not None:
        last = len(df) - 1
        trades.append(close_position(last, float(df.iloc[last]["Close"]), EXIT_FINAL))

    return trades
