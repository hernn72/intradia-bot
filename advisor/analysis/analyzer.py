"""Orquestador del análisis: del universo a una lista de oportunidades
puntuadas y ordenadas.

Es la única capa de ``advisor.analysis`` que hace I/O (descargas). Todo lo
que hay por debajo —``snapshot``, ``levels``, ``scoring``, ``opportunity``—
es puro y se puede probar sin red.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from advisor.analysis.benchmark import resolve_benchmark_symbol
from advisor.analysis.levels import compute_levels
from advisor.analysis.market_context import MarketContext, fetch_market_context
from advisor.analysis.opportunity import (
    ANALYSIS_ERROR,
    INSUFFICIENT_HISTORY,
    NO_LEVELS,
    Opportunity,
    build_opportunity,
)
from advisor.analysis.overview import IndexQuote, asia_session_change, fetch_overview
from advisor.analysis.scoring import compute_score
from advisor.analysis.snapshot import TechnicalSnapshot, build_snapshot
from advisor.config import AdvisorConfig
from advisor.data.bar_cache import BarCacheReport
from advisor.data.freshness import DataFreshness, FreshnessRow, calcular_frescura_serie, mercado_para_simbolo
from advisor.data.market_data import MarketDataProvider
from advisor.data.sessions import market_for_symbol, market_session, trim_unclosed_bar
from advisor.universe.models import Asset, Universe

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SkippedAnalysis:
    symbol: str
    reason: str
    code: str

    def __iter__(self):
        yield self.symbol
        yield self.reason

    def __getitem__(self, index: int) -> str:
        return (self.symbol, self.reason)[index]


@dataclass(frozen=True)
class AnalysisResult:
    """Resultado de una pasada completa del asesor."""

    generated_at: datetime
    horizonte: str
    interval: str
    context: MarketContext
    opportunities: List[Opportunity] = field(default_factory=list)
    skipped: List[SkippedAnalysis] = field(default_factory=list)
    overview: List[IndexQuote] = field(default_factory=list)
    freshness_rows: List[FreshnessRow] = field(default_factory=list)
    bar_cache: Optional[BarCacheReport] = None
    """Lo que hizo la caché de barras validadas, o ``None`` si no actuó.

    Viaja en el resultado para que el informe y la persistencia declaren lo
    mismo que midió la pasada (INV-21), sin recalcularlo por separado.
    """

    def by_radar(self, radar: str) -> List[Opportunity]:
        return [o for o in self.opportunities if o.radar == radar]


def _fetch_benchmark(
    provider: MarketDataProvider,
    symbol: str,
    period: str,
    interval: str,
    reference: datetime,
    settlement_minutes: int,
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
    trimmed = trim_unclosed_bar(
        history,
        market=market_for_symbol(symbol),
        reference=reference,
        settlement_minutes=settlement_minutes,
        interval=interval,
    )
    if trimmed.removed_last_bar:
        logger.info("%s benchmark: %s", symbol, trimmed.status)
    return trimmed.df["Close"]


def analyze_asset(
    asset: Asset,
    config: AdvisorConfig,
    provider: MarketDataProvider,
    context: MarketContext,
    horizonte: str,
    benchmark_close: Optional[pd.Series] = None,
    benchmark_symbol: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Opportunity:
    """Analiza un único activo.

    Lanza ``ValueError`` con un motivo legible si el activo no puede
    analizarse (histórico insuficiente, sin ATR, niveles incoherentes). El
    llamante decide si eso aborta la ejecución o solo descarta ese activo.
    """

    window = config.horizonte(horizonte)
    data_symbol = asset.data_symbol(now)
    market = mercado_para_simbolo(asset, data_symbol)
    reference = now or datetime.now(timezone.utc)
    raw_history = provider.get_history(data_symbol, period=window.period, interval=window.interval)
    trim = trim_unclosed_bar(
        raw_history,
        market=market,
        reference=reference,
        settlement_minutes=config.data_quality.settlement_minutes,
        interval=window.interval,
    )
    if trim.removed_last_bar:
        logger.info("%s: %s", asset.symbol, trim.status)
    history = trim.df

    if len(history) < window.min_bars:
        raise ValueError(
            f"histórico insuficiente tras recorte de barra no cerrada: {len(history)} velas, "
            f"se requieren {window.min_bars}; {trim.status}"
        )

    barra_actual_cerrada = trim.removed_last_bar or trim.status.startswith("última barra cerrada")

    def _frescura(indicators_missing: tuple[str, ...] = ()) -> DataFreshness:
        """Un único sitio con los argumentos de la frescura.

        Estaban duplicados en dos llamadas y la segunda —la que se rehace
        cuando falta un indicador— se quedó sin ``barra_actual_cerrada`` y sin
        ``session_close_status``, de modo que un activo asiático con histórico
        corto volvía a registrarse como barra parcial con la sesión cerrada.
        """

        return replace(
            calcular_frescura_serie(
                history,
                reference,
                market=market,
                barra_actual_cerrada=barra_actual_cerrada,
                strength_benchmark=benchmark_symbol,
                recent_reference_sessions=indicator_reference_sessions(config),
                veto_window_sessions=config.data_quality.veto_window_sessions,
                asset_timezone=asset.timezone,
                settlement_minutes=config.data_quality.settlement_minutes,
                indicators_missing=indicators_missing,
                measurement_period=window.period,
                measurement_interval=window.interval,
                critical_latest_sessions=config.data_quality.critical_latest_sessions,
                high_after_sessions=config.data_quality.high_after_sessions,
                medium_after_sessions=config.data_quality.medium_after_sessions,
            ),
            session_close_status=trim.status,
        )

    data_freshness = _frescura()

    snapshot = build_snapshot(
        symbol=asset.symbol,
        df=history,
        indicators=config.indicators,
        levels=config.levels,
        interval=window.interval,
        benchmark_close=benchmark_close,
        asset_timezone=asset.timezone,
        benchmark_timezone=(
            market_session(market_for_symbol(benchmark_symbol)).timezone if benchmark_symbol else None
        ),
    )
    indicators_missing = _missing_indicators(snapshot)
    if indicators_missing:
        data_freshness = _frescura(indicators_missing)

    levels = compute_levels(snapshot, config.levels, config.risk.min_rr_ratio)
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
        portfolio=config.portfolio,
        data_quality=config.data_quality,
        data_freshness=data_freshness,
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
    reference = now or datetime.now(timezone.utc)
    overview = fetch_overview(provider, universe)
    context = fetch_market_context(
        provider,
        config.market_context,
        asia_session_change(overview),
        reference=reference,
        settlement_minutes=config.data_quality.settlement_minutes,
    )
    benchmark_cache: Dict[str, Optional[pd.Series]] = {}

    opportunities: List[Opportunity] = []
    skipped: List[SkippedAnalysis] = []
    freshness_rows: List[FreshnessRow] = []

    for asset in assets:
        try:
            benchmark_symbol = resolve_benchmark_symbol(asset, config.report)
            benchmark_close = None
            if benchmark_symbol is not None:
                if benchmark_symbol not in benchmark_cache:
                    benchmark_cache[benchmark_symbol] = _fetch_benchmark(
                        provider,
                        benchmark_symbol,
                        window.period,
                        window.interval,
                        reference,
                        config.data_quality.settlement_minutes,
                    )
                benchmark_close = benchmark_cache[benchmark_symbol]
            opportunity = analyze_asset(asset, config, provider, context, horizonte, benchmark_close, benchmark_symbol, now)
            opportunities.append(opportunity)
            data_symbol = asset.data_symbol(now)
            freshness_rows.append(
                FreshnessRow(
                    symbol=asset.symbol,
                    data_symbol=data_symbol,
                    market=mercado_para_simbolo(asset, data_symbol),
                    freshness=opportunity.data_freshness,
                )
            )
        except Exception as exc:
            logger.warning("%s descartado del análisis: %s", asset.symbol, exc)
            skipped.append(SkippedAnalysis(asset.symbol, str(exc), _skip_code(exc)))
            data_symbol = asset.data_symbol(now)
            freshness_rows.append(
                FreshnessRow(
                    symbol=asset.symbol,
                    data_symbol=data_symbol,
                    market=mercado_para_simbolo(asset, data_symbol),
                    freshness=None,
                    error=str(exc),
                )
            )

    opportunities.sort(key=lambda o: (o.score.value, o.levels.rr_ratio), reverse=True)

    return AnalysisResult(
        generated_at=now or datetime.now(timezone.utc),
        horizonte=horizonte,
        interval=window.interval,
        context=context,
        opportunities=opportunities,
        skipped=skipped,
        overview=overview,
        freshness_rows=freshness_rows,
        bar_cache=_bar_cache_report(provider),
    )


def _bar_cache_report(provider: Any) -> Optional[BarCacheReport]:
    """Lo que la caché declaró, si el proveedor recibido la lleva puesta.

    El analizador no construye la caché ni decide si está activa: recibe el
    proveedor que le den. Así el mismo `run_analysis` sirve a una pasada de
    producción, a un test con proveedor falso y a un backtest vivo (INV-06).
    """

    report = getattr(provider, "bar_cache_report", None)
    if not callable(report):
        return None
    value = report()
    return value if isinstance(value, BarCacheReport) else None


def indicator_reference_sessions(config: AdvisorConfig) -> int:
    return max(
        config.indicators.sma_long,
        config.indicators.ema_slow,
        config.indicators.rsi_period + 1,
        config.indicators.atr_period + 1,
        config.indicators.macd_slow + config.indicators.macd_signal,
        config.indicators.volume_lookback + 1,
        config.levels.lookback_bars,
        120,
    )


def _missing_indicators(snapshot: TechnicalSnapshot) -> tuple[str, ...]:
    missing: list[str] = []
    for name in ("sma_long", "rsi", "atr", "macd", "macd_signal"):
        if getattr(snapshot, name) is None:
            missing.append(name)
    return tuple(missing)


def _skip_code(exc: Exception) -> str:
    """Traduce el fallo a código, y declara desconocido lo que no reconoce.

    El caso por defecto era ``INVALID_INDICATORS``, de modo que un 404 del
    proveedor, un `KeyError` de pandas o una plaza sin calendario declarado se
    publicaban en el informe como indicadores inválidos: una causa concreta
    que nadie había comprobado. INV-16 exige lo contrario.
    """

    reason = str(exc).lower()
    if "histórico insuficiente" in reason or "histórico está vacío" in reason or "sin datos" in reason:
        return INSUFFICIENT_HISTORY
    if "no se pueden situar los niveles" in reason:
        return NO_LEVELS
    return ANALYSIS_ERROR
