"""Orquestador del análisis: del universo a una lista de oportunidades
puntuadas y ordenadas.

Es la única capa de ``advisor.analysis`` que hace I/O (descargas). Todo lo
que hay por debajo —``snapshot``, ``levels``, ``scoring``, ``opportunity``—
es puro y se puede probar sin red.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import pandas as pd

from advisor.analysis.levels import compute_levels
from advisor.analysis.market_context import MarketContext, fetch_market_context
from advisor.analysis.opportunity import Opportunity, build_opportunity
from advisor.analysis.overview import IndexQuote, asia_session_change, fetch_overview
from advisor.analysis.scoring import compute_score
from advisor.analysis.snapshot import build_snapshot
from advisor.config import AdvisorConfig
from advisor.data.market_data import MarketDataProvider
from advisor.universe.models import Asset, Universe

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnalysisResult:
    """Resultado de una pasada completa del asesor."""

    generated_at: datetime
    horizonte: str
    interval: str
    context: MarketContext
    opportunities: List[Opportunity] = field(default_factory=list)
    skipped: List[Tuple[str, str]] = field(default_factory=list)
    overview: List[IndexQuote] = field(default_factory=list)

    def by_radar(self, radar: str) -> List[Opportunity]:
        return [o for o in self.opportunities if o.radar == radar]


def _fetch_benchmark(
    provider: MarketDataProvider, symbol: str, period: str, interval: str
) -> Optional[pd.Series]:
    """Cierres del índice de referencia para la fortaleza relativa.

    Devuelve ``None`` si no se puede descargar: la fortaleza relativa queda
    entonces sin dato y su factor sale del reparto de puntos, en vez de
    penalizar a todos los activos por igual.
    """

    try:
        history = provider.get_history(symbol, period=period, interval=interval)
    except Exception as exc:
        logger.warning("Sin datos del índice de referencia %s: %s", symbol, exc)
        return None
    return history["Close"]


def analyze_asset(
    asset: Asset,
    config: AdvisorConfig,
    provider: MarketDataProvider,
    context: MarketContext,
    horizonte: str,
    benchmark_close: Optional[pd.Series] = None,
    now: Optional[datetime] = None,
) -> Opportunity:
    """Analiza un único activo.

    Lanza ``ValueError`` con un motivo legible si el activo no puede
    analizarse (histórico insuficiente, sin ATR, niveles incoherentes). El
    llamante decide si eso aborta la ejecución o solo descarta ese activo.
    """

    window = config.horizonte(horizonte)
    data_symbol = asset.data_symbol(now)
    history = provider.get_history(data_symbol, period=window.period, interval=window.interval)

    if len(history) < window.min_bars:
        raise ValueError(
            f"histórico insuficiente: {len(history)} velas, se requieren {window.min_bars}"
        )

    snapshot = build_snapshot(
        symbol=asset.symbol,
        df=history,
        indicators=config.indicators,
        levels=config.levels,
        interval=window.interval,
        benchmark_close=benchmark_close,
    )

    levels = compute_levels(snapshot, config.levels)
    if levels is None:
        raise ValueError("no se pueden situar los niveles (ATR no disponible o stop incoherente)")

    score = compute_score(snapshot, levels, context, config.scoring, window.min_bars)

    return build_opportunity(
        asset=asset,
        horizonte=horizonte,
        snapshot=snapshot,
        levels=levels,
        score=score,
        context=context,
        scoring=config.scoring,
        risk=config.risk,
    )


def run_analysis(
    config: AdvisorConfig,
    universe: Universe,
    provider: MarketDataProvider,
    horizonte: str = "swing",
    groups: Optional[List[str]] = None,
    now: Optional[datetime] = None,
) -> AnalysisResult:
    """Analiza el universo completo y devuelve las oportunidades ordenadas.

    ``now`` es inyectable para que los tests no dependan del reloj.
    """

    window = config.horizonte(horizonte)
    assets = universe.analizables(groups)
    if not assets:
        raise ValueError("no hay activos analizables en el universo seleccionado")

    logger.info("Analizando %d activos (horizonte %s, velas de %s)", len(assets), horizonte, window.interval)

    # El panorama se descarga antes que el contexto: la sesión asiática, ya
    # cerrada cuando Europa abre, entra como señal en la puntuación de
    # contexto en vez de quedarse en un adorno del informe.
    overview = fetch_overview(provider, universe)
    context = fetch_market_context(provider, config.market_context, asia_session_change(overview))
    benchmark_close = _fetch_benchmark(
        provider, config.report.benchmark_symbol, window.period, window.interval
    )

    opportunities: List[Opportunity] = []
    skipped: List[Tuple[str, str]] = []

    for asset in assets:
        try:
            opportunities.append(
                analyze_asset(asset, config, provider, context, horizonte, benchmark_close, now)
            )
        except Exception as exc:
            logger.warning("%s descartado del análisis: %s", asset.symbol, exc)
            skipped.append((asset.symbol, str(exc)))

    opportunities.sort(key=lambda o: (o.score.value, o.levels.rr_ratio), reverse=True)

    return AnalysisResult(
        generated_at=now or datetime.now(timezone.utc),
        horizonte=horizonte,
        interval=window.interval,
        context=context,
        opportunities=opportunities,
        skipped=skipped,
        overview=overview,
    )
