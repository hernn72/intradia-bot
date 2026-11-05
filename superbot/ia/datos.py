"""Adaptador cuantitativo: el cálculo del asesor con contrato causal, sin tocar ``advisor/``.

No llama a ``run_analysis``, que fija ``legacy_v1`` con Score v1 y usa barras
ajustadas. Llama a ``analyze_asset`` con barras sin ajustar y con un contexto
point-in-time inyectado, la misma combinación que P6. No abre la base del asesor.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

import pandas as pd

from advisor.analysis.analyzer import _fetch_benchmark, analyze_asset
from advisor.analysis.benchmark import resolve_benchmark_symbol
from advisor.analysis.market_context import MarketContext
from advisor.analysis.opportunity import Opportunity
from advisor.analysis.overview import context_assets_of
from advisor.config import AdvisorConfig
from advisor.context.point_in_time import PointInTimeContextResult, resolve_point_in_time_context
from advisor.data.calendars import exchange_calendar, expected_sessions
from advisor.data.freshness import mercado_para_simbolo
from advisor.data.market_data import MarketDataProvider
from advisor.data.sessions import market_for_symbol, session_close_at, session_date_of, trim_unclosed_bar
from advisor.universe.models import Asset, Universe
from superbot.ia.paquete import Observacion
from superbot.ia.politica import PoliticaIA

logger = logging.getLogger(__name__)

SCORE_MODEL = "1.0"


class ContextoNoCalculable(RuntimeError):
    """Sin contexto point-in-time no hay análisis ni decisiones."""


def _huella(df: pd.DataFrame) -> str:
    return hashlib.sha256(pd.util.hash_pandas_object(df, index=True).values.tobytes()).hexdigest()[:16]


class ProveedorCrudo:
    """Proveedor para ``analyze_asset``: barras sin ajustar, una descarga por símbolo y pasada."""

    def __init__(self, base: MarketDataProvider, reloj: Callable[[], datetime]) -> None:
        self._base = base
        self._reloj = reloj
        self._cache: Dict[Tuple[str, str, str], pd.DataFrame] = {}
        self.observado: Dict[str, datetime] = {}

    def get_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        clave = (symbol, period, interval)
        if clave not in self._cache:
            self._cache[clave] = self._base.get_raw_history(symbol, period=period, interval=interval)
            self.observado[symbol] = self._reloj()
        return self._cache[clave]


@dataclass(frozen=True)
class Contexto:
    mercado: MarketContext
    resultado: PointInTimeContextResult
    observaciones: Tuple[Observacion, ...]


def _disponible(symbol: str, session: date, settlement_minutes: int) -> Optional[datetime]:
    cierre = session_close_at(market_for_symbol(symbol), session)
    return None if cierre is None else cierre + timedelta(minutes=settlement_minutes)


def cargar_contexto(
    proveedor: ProveedorCrudo, config: AdvisorConfig, universe: Universe, instante: datetime
) -> Contexto:
    ajustes = config.market_context
    settlement = config.data_quality.settlement_minutes
    asia = tuple(sorted(a.primary_symbol for a in context_assets_of(universe) if a.region == "ASIA"))
    series = {
        symbol: proveedor.get_history(symbol, period="2y", interval="1d")
        for symbol in (ajustes.vix_symbol, ajustes.trend_symbol, *asia)
    }
    resultado = resolve_point_in_time_context(
        instante,
        {symbol: df["Close"] for symbol, df in series.items()},
        ajustes,
        asia_symbols=asia,
        settlement_minutes=settlement,
    )
    if not resultado.calculable or resultado.context is None:
        raise ContextoNoCalculable(", ".join((*resultado.exclusions, *resultado.no_calculable_codes)) or "sin contexto")
    if resultado.context.source != "point_in_time":
        raise ContextoNoCalculable(f"contexto con fuente {resultado.context.source}")

    observaciones: List[Observacion] = []
    for symbol, session in (
        (ajustes.vix_symbol, resultado.vix_session),
        (ajustes.trend_symbol, resultado.trend_used_session),
    ):
        if session is None:
            raise ContextoNoCalculable(f"{symbol} sin sesión usada")
        disponible = _disponible(symbol, session, settlement)
        if disponible is None:
            raise ContextoNoCalculable(f"{symbol} sin hora de cierre")
        observaciones.append(
            Observacion(
                "contexto", symbol, session.isoformat(), disponible, proveedor.observado[symbol], _huella(series[symbol])
            )
        )
    return Contexto(resultado.context, resultado, tuple(observaciones))


def sesion_objetivo(market: str, signal: date) -> Tuple[date, datetime]:
    """Primera sesión de la plaza tras la señal y su apertura en UTC."""

    siguiente = expected_sessions(market, signal + timedelta(days=1), signal + timedelta(days=21))[0]
    apertura = cast(Any, exchange_calendar(market)).session_open(pd.Timestamp(siguiente)).to_pydatetime()
    if apertura.tzinfo is None:
        apertura = apertura.replace(tzinfo=timezone.utc)
    return siguiente, apertura


@dataclass(frozen=True)
class Analisis:
    asset: Asset
    oportunidad: Opportunity
    market: str
    signal_session: date
    target_session: date
    target_open: datetime
    close: float
    sma: Optional[float]
    observacion: Observacion


def analizar(
    asset: Asset,
    config: AdvisorConfig,
    proveedor: ProveedorCrudo,
    contexto: Contexto,
    instante: datetime,
    politica: PoliticaIA,
) -> Analisis:
    """Análisis de un valor a ``instante``. Lanza ``ValueError`` si no se puede analizar."""

    ventana = config.horizonte(politica.horizonte)
    settlement = config.data_quality.settlement_minutes
    data_symbol = asset.data_symbol(instante)
    market = mercado_para_simbolo(asset, data_symbol)
    benchmark_symbol = resolve_benchmark_symbol(asset, config.report)
    benchmark_close = (
        _fetch_benchmark(
            cast(MarketDataProvider, proveedor), benchmark_symbol, ventana.period, ventana.interval, instante, settlement
        )
        if benchmark_symbol
        else None
    )
    oportunidad = analyze_asset(
        asset,
        config,
        cast(MarketDataProvider, proveedor),
        contexto.mercado,
        politica.horizonte,
        benchmark_close=benchmark_close,
        benchmark_symbol=benchmark_symbol,
        now=instante,
        score_model_version=SCORE_MODEL,
    )

    bruto = proveedor.get_history(data_symbol, period=ventana.period, interval=ventana.interval)
    barras = trim_unclosed_bar(
        bruto, market=market, reference=instante, settlement_minutes=settlement, interval=ventana.interval
    ).df
    signal = session_date_of(barras.index[-1], market)
    if signal is None:
        raise ValueError("barra sin sesión")
    cierre = session_close_at(market, signal)
    if cierre is None:
        raise ValueError("sesión sin hora de cierre")
    target, apertura = sesion_objetivo(market, signal)
    media = barras["Close"].rolling(politica.sma_periodo).mean().iloc[-1]
    return Analisis(
        asset=asset,
        oportunidad=oportunidad,
        market=market,
        signal_session=signal,
        target_session=target,
        target_open=apertura,
        close=float(barras["Close"].iloc[-1]),
        sma=None if pd.isna(media) else float(media),
        observacion=Observacion(
            "barras",
            data_symbol,
            signal.isoformat(),
            cierre + timedelta(minutes=settlement),
            proveedor.observado[data_symbol],
            _huella(barras),
        ),
    )
