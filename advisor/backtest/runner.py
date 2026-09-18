"""Ejecución del backtest sobre el universo real: descarga, alinea y simula.

Única capa de ``advisor.backtest`` con I/O. La alineación temporal evita
mirar el futuro: para cada vela del activo, el VIX disponible es el del día
anterior (en un análisis real a media sesión europea, el último cierre del
VIX es el de ayer), y la tendencia del índice europeo es la de ese mismo
cierre, que sí es simultáneo al del activo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from advisor.analysis.benchmark import resolve_benchmark_symbol
from advisor.backtest.engine import POLICY_OPERAR, POLICY_TODAS, BacktestTrade, simulate_asset
from advisor.config import AdvisorConfig
from advisor.data.freshness import mercado_para_simbolo
from advisor.data.market_data import MarketDataProvider
from advisor.data.sessions import trim_unclosed_bar
from advisor.indicators.technical import sma
from advisor.research.vintage import VintageLoad, frozen_close
from advisor.universe.models import Asset, Universe

logger = logging.getLogger(__name__)

# Histórico de contexto (VIX y tendencia): más largo que el del activo para
# que la SMA de 200 sesiones exista desde la primera vela del backtest.
_CONTEXT_PERIOD = "10y"


@dataclass(frozen=True)
class BacktestResult:
    """Resultado completo de una pasada de backtest.

    ``data_vintage_id`` es lo que separa un resultado reproducible de uno que no
    lo es: con cosecha, repetir el comando da el mismo fichero; en vivo, no, y el
    informe tiene que decirlo (INV-16).
    """

    horizonte: str
    period: str
    cost_pct: float
    warmup_bars: int
    trades_operar: List[BacktestTrade] = field(default_factory=list)
    trades_todas: List[BacktestTrade] = field(default_factory=list)
    buy_hold_pct: Dict[str, float] = field(default_factory=dict)
    evaluated: List[str] = field(default_factory=list)
    skipped: List[Tuple[str, str]] = field(default_factory=list)
    data_vintage_id: Optional[str] = None
    data_range: Optional[Tuple[str, str]] = None
    context_sin_sma: int = 0
    context_sin_tendencia: bool = False

    @property
    def reproducible(self) -> bool:
        return self.data_vintage_id is not None


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
    provider: Optional[MarketDataProvider],
    horizonte: str = "swing",
    groups: Optional[List[str]] = None,
    period: str = "5y",
    cost_pct: float = 0.2,
    vintage: Optional[VintageLoad] = None,
    reference: Optional[datetime] = None,
    settlement_minutes: int = 20,
) -> BacktestResult:
    """Simula el asesor sobre histórico diario.

    Ejecuta las dos políticas sobre los mismos datos: la real (solo señales
    COMPRAR) para medir lo que el asesor propone, y la de todas las señales
    para poder comparar tramos de puntuación y el efecto de los vetos.

    Con ``vintage``, los datos salen de una cosecha congelada y el resultado es
    reproducible. Sin ella se descargan en vivo, y entonces **no lo es**: el
    proveedor revisa barras y la última vela se mueve dentro de la sesión, así
    que dos ejecuciones del mismo commit con minutos de diferencia dan cifras
    distintas. Lo que cambia entre los dos modos es de dónde salen los datos;
    lo que se hace con ellos es idéntico.
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

    if vintage is None and provider is None:
        raise ValueError("el backtest necesita un proveedor de datos o una cosecha congelada")

    referencia = reference or datetime.now(timezone.utc)

    def mercado_de(asset: Asset) -> str:
        # El mismo resolutor que usa el análisis: prioriza la plaza declarada en
        # el universo y solo infiere del símbolo cuando no la hay (INV-06).
        return mercado_para_simbolo(asset, asset.primary_symbol)

    def cierres(symbol: Optional[str]) -> Optional[pd.Series]:
        if vintage is not None:
            return frozen_close(vintage, symbol)
        assert provider is not None
        return _fetch_close(provider, symbol) if symbol is not None else None

    vix_close = cierres(config.market_context.vix_symbol)
    trend_close = cierres(config.market_context.trend_symbol)
    trend_sma_close = sma(trend_close, config.market_context.trend_sma) if trend_close is not None else None
    benchmark_cache: Dict[str, Optional[pd.Series]] = {}
    if trend_close is not None:
        benchmark_cache[config.market_context.trend_symbol] = trend_close

    result = BacktestResult(
        horizonte=horizonte,
        period=period,
        cost_pct=cost_pct,
        warmup_bars=window.min_bars,
        data_vintage_id=vintage.data_vintage_id if vintage is not None else None,
        context_sin_sma=_sesiones_sin_sma(trend_sma_close),
        context_sin_tendencia=trend_close is None,
    )

    rango: List[Optional[str]] = [None, None]
    for asset in assets:
        if vintage is not None:
            views = vintage.by_symbol.get(asset.primary_symbol)
            if views is None:
                result.skipped.append((asset.symbol, "no está en la cosecha congelada"))
                continue
            df = _con_indice_de_fechas(views.signal_prices)
        else:
            assert provider is not None
            try:
                df = provider.get_history(asset.primary_symbol, period=period, interval="1d")
            except Exception as exc:
                result.skipped.append((asset.symbol, str(exc)))
                continue
            # Una barra en curso no es un dato ni aquí: simular con la vela de
            # hoy a medias metería en el backtest un precio que todavía se
            # mueve (D-37). En modo cosecha no aplica: lo congelado ya está.
            df = trim_unclosed_bar(
                df,
                market=mercado_de(asset),
                reference=referencia,
                settlement_minutes=settlement_minutes,
            ).df
            if df.empty:
                result.skipped.append((asset.symbol, "sin barras cerradas"))
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
                benchmark_cache[benchmark_symbol] = cierres(benchmark_symbol)
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
        _ampliar_rango(rango, df.index)

    return replace(result, data_range=(rango[0], rango[1]) if rango[0] and rango[1] else None)


def _con_indice_de_fechas(df: pd.DataFrame) -> pd.DataFrame:
    """Índice de la cosecha a fechas, para que una operación se feche igual en los dos modos.

    La cosecha guarda sus marcas de tiempo como texto —es lo que hace estables
    los hashes de INV-13—, así que sin esto `entry_date` sería un `str` sobre
    cosecha y un `pd.Timestamp` en vivo: la misma operación no se podría
    comparar entre modos, y el informe ordena por ese campo. La conversión es
    solo para simular: no se reescribe nada de la cosecha.
    """

    if isinstance(df.index, pd.DatetimeIndex):
        return df
    convertido = df.copy()
    convertido.index = pd.to_datetime(df.index, utc=False, format="mixed")
    return convertido


def _sesiones_sin_sma(trend_sma_close: Optional[pd.Series]) -> int:
    """Sesiones de **la serie de tendencia** sin media, que es contexto que falta.

    En vivo el contexto se descarga con 10 años, así que la SMA de 200 existe
    desde la primera vela simulada. Una cosecha de 5 años no tiene ese margen:
    las primeras sesiones del índice no tienen media, y el contexto de tendencia
    de esas fechas puntúa como desconocido. No se corrige inventando datos: se
    cuenta y se declara en el informe (INV-16).

    Cuenta sesiones **del índice de tendencia**, no filas de cada activo: un
    activo con otro calendario —cripto cotiza fines de semana— tendrá un número
    distinto de velas afectadas. El informe lo dice así para no prometer una
    cifra por activo que aquí no se mide.

    Devuelve 0 si no hay serie: ese caso no es «no falta nada», sino que falta
    **toda**, y lo declara `context_sin_tendencia` por separado.
    """

    if trend_sma_close is None:
        return 0
    return int(trend_sma_close.isna().sum())


def _ampliar_rango(rango: List[Optional[str]], index: pd.Index) -> None:
    if len(index) == 0:
        return
    fechas = _naive_dates(index)
    primera, ultima = fechas[0].date().isoformat(), fechas[-1].date().isoformat()
    rango[0] = primera if rango[0] is None else min(rango[0], primera)
    rango[1] = ultima if rango[1] is None else max(rango[1], ultima)
