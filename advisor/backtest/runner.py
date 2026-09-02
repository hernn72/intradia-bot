"""Ejecución del backtest sobre el universo real: descarga, alinea y simula.

Única capa de ``advisor.backtest`` con I/O. La alineación temporal evita
mirar el futuro: para cada vela del activo, el VIX disponible es el del día
anterior (en un análisis real a media sesión europea, el último cierre del
VIX es el de ayer), y la tendencia del índice europeo es la de ese mismo
cierre, que sí es simultáneo al del activo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from advisor.analysis.benchmark import resolve_benchmark_symbol
from advisor.backtest.engine import POLICY_OPERAR, POLICY_TODAS, BacktestTrade, simulate_asset
from advisor.config import AdvisorConfig
from advisor.data.market_data import MarketDataProvider
from advisor.indicators.technical import sma
from advisor.universe.models import Universe

logger = logging.getLogger(__name__)

# Histórico de contexto (VIX y tendencia): más largo que el del activo para
# que la SMA de 200 sesiones exista desde la primera vela del backtest.
_CONTEXT_PERIOD = "10y"


@dataclass(frozen=True)
class BacktestResult:
    """Resultado completo de una pasada de backtest."""

    horizonte: str
    period: str
    cost_pct: float
    warmup_bars: int
    trades_operar: List[BacktestTrade] = field(default_factory=list)
    trades_todas: List[BacktestTrade] = field(default_factory=list)
    buy_hold_pct: Dict[str, float] = field(default_factory=dict)
    evaluated: List[str] = field(default_factory=list)
    skipped: List[Tuple[str, str]] = field(default_factory=list)


def _naive_dates(index: pd.Index) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return idx.normalize()


def _align(series: Optional[pd.Series], index: pd.Index) -> Optional[pd.Series]:
    """Reindexa ``series`` sobre las fechas de ``index`` arrastrando el último
    valor conocido (mercados con festivos distintos no comparten calendario)."""

    if series is None or series.empty:
        return None
    s = series.copy()
    s.index = _naive_dates(s.index)
    s = s[~s.index.duplicated(keep="last")]
    target = _naive_dates(index)
    aligned = s.reindex(s.index.union(target)).ffill().reindex(target)
    aligned.index = index
    return aligned


def _as_optional_list(series: Optional[pd.Series]) -> Optional[Sequence[Optional[float]]]:
    if series is None:
        return None
    return [None if pd.isna(v) else float(v) for v in series]


def _fetch_close(provider: MarketDataProvider, symbol: str) -> Optional[pd.Series]:
    try:
        return provider.get_history(symbol, period=_CONTEXT_PERIOD, interval="1d")["Close"]
    except Exception as exc:
        logger.warning("Backtest — sin datos de %s: %s", symbol, exc)
        return None


def run_backtest(
    config: AdvisorConfig,
    universe: Universe,
    provider: MarketDataProvider,
    horizonte: str = "swing",
    groups: Optional[List[str]] = None,
    period: str = "5y",
    cost_pct: float = 0.2,
) -> BacktestResult:
    """Simula el asesor sobre ``period`` de histórico diario.

    Ejecuta las dos políticas sobre los mismos datos: la real (solo señales
    COMPRAR) para medir lo que el asesor propone, y la de todas las señales
    para poder comparar tramos de puntuación y el efecto de los vetos.
    """

    if horizonte not in ("swing", "medio"):
        raise ValueError(
            f"el backtest solo cubre swing y medio: el horizonte '{horizonte}' usa velas "
            "intradía y yfinance no conserva histórico suficiente para reproducirlas"
        )

    assets = universe.analizables(groups)
    if not assets:
        raise ValueError("no hay activos analizables en el universo seleccionado")

    window = config.horizonte(horizonte)
    logger.info(
        "Backtest de %d activos (horizonte %s, periodo %s, coste %.2f%% ida y vuelta)",
        len(assets), horizonte, period, cost_pct,
    )

    vix_close = _fetch_close(provider, config.market_context.vix_symbol)
    trend_close = _fetch_close(provider, config.market_context.trend_symbol)
    trend_sma_close = sma(trend_close, config.market_context.trend_sma) if trend_close is not None else None
    benchmark_cache: Dict[str, Optional[pd.Series]] = {}
    if trend_close is not None:
        benchmark_cache[config.market_context.trend_symbol] = trend_close

    result = BacktestResult(
        horizonte=horizonte, period=period, cost_pct=cost_pct, warmup_bars=window.min_bars
    )

    for asset in assets:
        try:
            df = provider.get_history(asset.primary_symbol, period=period, interval="1d")
        except Exception as exc:
            result.skipped.append((asset.symbol, str(exc)))
            continue
        if len(df) < window.min_bars + 10:
            result.skipped.append(
                (asset.symbol, f"histórico insuficiente: {len(df)} velas para un calentamiento de {window.min_bars}")
            )
            continue

        # VIX con una vela de retraso (sin mirar el futuro); tendencia y
        # benchmark al cierre del mismo día, simultáneo al del activo.
        vix_aligned = _align(vix_close, df.index)
        vix_at = _as_optional_list(vix_aligned.shift(1) if vix_aligned is not None else None)
        trend_at = _as_optional_list(_align(trend_close, df.index))
        trend_sma_at = _as_optional_list(_align(trend_sma_close, df.index))
        benchmark_symbol = resolve_benchmark_symbol(asset, config.report)
        benchmark_close = None
        if benchmark_symbol is not None:
            if benchmark_symbol not in benchmark_cache:
                benchmark_cache[benchmark_symbol] = _fetch_close(provider, benchmark_symbol)
            benchmark_close = benchmark_cache[benchmark_symbol]
        for policy, bucket in ((POLICY_OPERAR, result.trades_operar), (POLICY_TODAS, result.trades_todas)):
            bucket.extend(
                simulate_asset(
                    asset, df, config, horizonte, policy, cost_pct,
                    benchmark_close=benchmark_close, vix_at=vix_at,
                    trend_price_at=trend_at, trend_sma_at=trend_sma_at,
                )
            )

        first_entry = float(df.iloc[window.min_bars]["Open"])
        last_close = float(df.iloc[-1]["Close"])
        if first_entry > 0:
            result.buy_hold_pct[asset.symbol] = (last_close / first_entry - 1) * 100 - cost_pct
        result.evaluated.append(asset.symbol)

    return result
