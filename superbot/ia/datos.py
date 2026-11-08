"""Adaptador cuantitativo: el cálculo del asesor con contrato causal, sin tocar ``advisor/``.

No llama a ``run_analysis``, que fija ``legacy_v1`` con Score v1 y usa barras
ajustadas. Llama a ``analyze_asset`` con barras sin ajustar y con un contexto
point-in-time inyectado, la misma combinación que P6. No abre la base del asesor.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

import pandas as pd

from advisor.analysis.analyzer import _fetch_benchmark, analyze_asset
from advisor.analysis.benchmark import resolve_benchmark_symbol
from advisor.analysis.market_context import MarketContext
from advisor.analysis.opportunity import Opportunity
from advisor.analysis.overview import context_assets_of
from advisor.config import AdvisorConfig
from advisor.context.point_in_time import (
    EXCLUDED_ASIA_MISSING,
    PointInTimeContextResult,
    resolve_point_in_time_context,
)
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


def _huella(datos: pd.DataFrame | pd.Series) -> str:
    return hashlib.sha256(pd.util.hash_pandas_object(datos, index=True).values.tobytes()).hexdigest()[:16]


def _hasta_sesion(serie: pd.Series, market: str, session: date) -> pd.Series:
    """Los puntos causales usados: la huella no depende de barras posteriores a ``session``."""

    sesiones = [session_date_of(ts, market) for ts in serie.index]
    return serie[[s is not None and s <= session for s in sesiones]]


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


# Política de cobertura parcial del contexto Asia. No toca la semántica
# point-in-time congelada en T-019 (``advisor/context/point_in_time.py``):
# esta constante solo decide, aquí en el adaptador, cuántos de los proxies
# Asia *configurados* hay que perder antes de declarar el contexto no
# calculable. Se tolera perder como máximo un tercio de ellos, redondeado
# hacia abajo; con menos de 3 proxies configurados cualquier ausencia ya es
# una minoría insuficiente. La tolerancia depende de cuántos proxies hay,
# nunca de qué símbolo falte: ningún proxy está exento por su nombre.
ASIA_TOLERANCIA_DIVISOR = 3


@dataclass(frozen=True)
class CoberturaAsia:
    """Estado explícito de la cobertura Asia de una pasada, para auditoría.

    - ``completo``: todos los proxies configurados tenían su barra (o se
      recuperó la que faltaba con un segundo intento).
    - ``parcial_valido``: faltaba alguno fuera de lo recuperable, dentro de
      la tolerancia; el contexto se recalculó solo con los proxies
      presentes, con la misma función point-in-time y sin imputar nada en
      lugar de los ausentes.
    - ``no_calculable``: fuera de tolerancia, o sin proxies útiles; la
      pasada aborta sin decisiones, como exige el fallo seguro.
    """

    estado: str
    configurados: Tuple[str, ...]
    presentes: Tuple[str, ...]
    ausentes: Tuple[Tuple[str, str], ...]
    recuperados: Tuple[str, ...]


@dataclass(frozen=True)
class Contexto:
    mercado: MarketContext
    resultado: PointInTimeContextResult
    observaciones: Tuple[Observacion, ...]
    cobertura_asia: CoberturaAsia = field(
        default_factory=lambda: CoberturaAsia("completo", (), (), (), ())
    )


def _disponible(symbol: str, session: date, settlement_minutes: int) -> Optional[datetime]:
    cierre = session_close_at(market_for_symbol(symbol), session)
    return None if cierre is None else cierre + timedelta(minutes=settlement_minutes)


def _recuperar_barra_asia(crudo: ProveedorCrudo, symbol: str, session: date) -> Optional[pd.Series]:
    """Segundo intento, con rango exacto, antes de aceptar que falta la barra.

    No es una excepción para un símbolo concreto: cualquier proxy Asia pasa
    por el mismo reintento. Solo pide la sesión que ``_asia_change`` ya
    declaró exigible —nunca una posterior a ella—, así que no adelanta
    información que no estuviera disponible a la pasada original.
    """

    base = getattr(crudo, "_base", None)
    if base is None:
        return None
    try:
        extra = base.get_raw_history(symbol, start=session.isoformat(), end=(session + timedelta(days=1)).isoformat())
    except Exception:
        return None
    if extra is None or extra.empty or "Close" not in extra:
        return None
    return extra["Close"]


def _resolver_cobertura_asia(
    crudo: ProveedorCrudo,
    ajustes: Any,
    settlement: int,
    asia: Tuple[str, ...],
    closes: Dict[str, pd.Series],
    instante: datetime,
) -> Tuple[PointInTimeContextResult, CoberturaAsia, Dict[str, pd.Series]]:
    """Decide, sin tocar ``point_in_time.py``, a qué subconjunto de proxies Asia
    pedirle el contexto. La función point-in-time congelada en T-019 sigue
    siendo la única que calcula VIX, tendencia y el cambio medio de Asia;
    aquí solo se elige, tras un intento de recuperación, con qué proxies se
    la llama.
    """

    resultado = resolve_point_in_time_context(
        instante, closes, ajustes, asia_symbols=asia, settlement_minutes=settlement
    )

    def _presentes(r: PointInTimeContextResult) -> Tuple[str, ...]:
        sesiones = getattr(r, "asia_sessions", {})
        return tuple(symbol for symbol in asia if symbol in sesiones)

    def _razones(r: PointInTimeContextResult) -> Tuple[Tuple[str, str], ...]:
        return tuple((ausencia.symbol, ausencia.missing) for ausencia in getattr(r, "asia_missing", ()))

    solo_asia = resultado.exclusions == (EXCLUDED_ASIA_MISSING,) and not resultado.no_calculable_codes
    if not solo_asia:
        # VIX o tendencia fallan por su cuenta (o el contexto está completo): la
        # cobertura Asia se audita igual, aunque no sea ella la que bloquea.
        estado = "completo" if resultado.calculable else "no_calculable"
        return resultado, CoberturaAsia(estado, asia, _presentes(resultado), _razones(resultado), ()), closes

    # 1) Recuperación: un segundo intento de descarga exacta por cada barra ausente.
    # ``recuperados`` se calcula por diferencia de ausencias antes/después, nunca por
    # haber recibido una respuesta no vacía: una barra recuperada que el resolver
    # sigue rechazando (p. ej. cierre <= 0) no cuenta como recuperada.
    closes_final = dict(closes)
    intentados: List[str] = []
    for ausencia in resultado.asia_missing:
        extra = _recuperar_barra_asia(crudo, ausencia.symbol, ausencia.session)
        if extra is None:
            continue
        previa = closes_final.get(ausencia.symbol)
        closes_final[ausencia.symbol] = pd.concat([previa, extra]).sort_index() if previa is not None else extra
        intentados.append(ausencia.symbol)

    if intentados:
        resultado = resolve_point_in_time_context(
            instante, closes_final, ajustes, asia_symbols=asia, settlement_minutes=settlement
        )
        ausentes_despues = {ausencia.symbol for ausencia in resultado.asia_missing}
        recuperados = tuple(symbol for symbol in intentados if symbol not in ausentes_despues)
        # El reloj solo se adelanta para los proxies que de verdad quedaron
        # resueltos: si falla, no hay observación recuperada que fechar, así que
        # no se silencia nada (D-81, fallo seguro ante un reloj que no responde).
        for symbol in recuperados:
            crudo.observado[symbol] = crudo._reloj()
        if resultado.calculable:
            return resultado, CoberturaAsia("completo", asia, asia, (), recuperados), closes_final
    else:
        recuperados = ()

    # 2) Cobertura parcial: lo que no se recuperó sigue ausente. Se recalcula
    # el mismo contexto point-in-time, pero pidiéndolo solo con los proxies
    # presentes, dentro de una tolerancia fija por número de proxies, nunca
    # por nombre de símbolo.
    ausentes = resultado.asia_missing
    if not ausentes:
        return resultado, CoberturaAsia("completo", asia, asia, (), recuperados), closes_final

    faltan = {ausencia.symbol for ausencia in ausentes}
    presentes = tuple(symbol for symbol in asia if symbol not in faltan)
    razones = _razones(resultado)
    tolerancia = len(asia) // ASIA_TOLERANCIA_DIVISOR
    if len(ausentes) > tolerancia or not presentes:
        return resultado, CoberturaAsia("no_calculable", asia, presentes, razones, recuperados), closes_final

    parcial = resolve_point_in_time_context(
        instante, closes_final, ajustes, asia_symbols=presentes, settlement_minutes=settlement
    )
    if not parcial.calculable:
        # VIX o tendencia fallan por su cuenta sobre el mismo cierre: no hay cobertura parcial que valga.
        return parcial, CoberturaAsia("no_calculable", asia, presentes, razones, recuperados), closes_final
    return parcial, CoberturaAsia("parcial_valido", asia, presentes, razones, recuperados), closes_final


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
    closes = {symbol: df["Close"] for symbol, df in series.items()}
    resultado, cobertura_asia, closes = _resolver_cobertura_asia(proveedor, ajustes, settlement, asia, closes, instante)
    if not resultado.calculable or resultado.context is None:
        raise ContextoNoCalculable(", ".join((*resultado.exclusions, *resultado.no_calculable_codes)) or "sin contexto")
    if resultado.context.source != "point_in_time":
        raise ContextoNoCalculable(f"contexto con fuente {resultado.context.source}")

    usadas: List[Tuple[str, Optional[date]]] = [
        (ajustes.vix_symbol, resultado.vix_session),
        (ajustes.trend_symbol, resultado.trend_used_session),
        *((symbol, max(sesiones)) for symbol, sesiones in sorted(resultado.asia_sessions.items())),
    ]
    observaciones: List[Observacion] = []
    for symbol, session in usadas:
        if session is None:
            raise ContextoNoCalculable(f"{symbol} sin sesión usada")
        disponible = _disponible(symbol, session, settlement)
        if disponible is None:
            raise ContextoNoCalculable(f"{symbol} sin hora de cierre")
        causal = _hasta_sesion(closes[symbol], market_for_symbol(symbol), session)
        observaciones.append(
            Observacion("contexto", symbol, session.isoformat(), disponible, proveedor.observado[symbol], _huella(causal))
        )
    return Contexto(resultado.context, resultado, tuple(observaciones), cobertura_asia)


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
    open: float
    low: float
    sma: Optional[float]
    observaciones: Tuple[Observacion, ...]


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
    observaciones = [
        Observacion(
            "barras", data_symbol, signal.isoformat(), cierre + timedelta(minutes=settlement),
            proveedor.observado[data_symbol], _huella(barras),
        )
    ]
    if benchmark_symbol and benchmark_close is not None and len(benchmark_close):
        plaza = market_for_symbol(benchmark_symbol)
        sesion = session_date_of(benchmark_close.index[-1], plaza)
        disponible = _disponible(benchmark_symbol, sesion, settlement) if sesion is not None else None
        if sesion is None or disponible is None:
            raise ValueError(f"benchmark {benchmark_symbol} sin sesión fechable")
        observaciones.append(
            Observacion(
                "benchmark", benchmark_symbol, sesion.isoformat(), disponible, proveedor.observado[benchmark_symbol],
                _huella(benchmark_close),
            )
        )
    return Analisis(
        asset=asset,
        oportunidad=oportunidad,
        market=market,
        signal_session=signal,
        target_session=target,
        target_open=apertura,
        close=float(barras["Close"].iloc[-1]),
        open=float(barras["Open"].iloc[-1]),
        low=float(barras["Low"].iloc[-1]),
        sma=None if pd.isna(media) else float(media),
        observaciones=tuple(observaciones),
    )
