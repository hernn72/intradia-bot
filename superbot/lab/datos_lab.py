"""Datos de las simulaciones: cosecha propia, acabada el 2026-08-27, y fichas al cierre de cada sesión.

La ventana termina donde los gates ya declaran consumidos los datos (D-73). No se abre ninguna
cosecha de T-024, ni ``paper.db``, ni la base de Superbot IA.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import pandas as pd

from advisor.analysis.benchmark import resolve_benchmark_symbol
from advisor.analysis.overview import context_assets_of
from advisor.analysis.snapshot import build_snapshot_series
from advisor.backtest.engine import _signal
from advisor.config import AdvisorConfig
from advisor.data.freshness import mercado_para_simbolo
from advisor.data.sessions import market_for_symbol, market_session, session_date_of
from advisor.research.p4 import _context_resolver
from advisor.research.p6 import WARMUP_BARS
from advisor.research.vintage import VintageLoad, freeze_vintage, frozen_close
from advisor.universe.models import Universe
from superbot.config import SuperbotConfig
from superbot.data import select_assets
from superbot.ia.medicion import REFERENCIA
from superbot.ia.pasada import BROKER_VERIFICADO
from superbot.ia.politica import PoliticaIA
from superbot.lab.simulador import Ficha, Serie

# Antes del inicio solo sirve para calentar indicadores.
DESCARGA_INICIO, DESCARGA_FIN_EXCLUSIVO = "2020-06-01", "2026-08-28"
FIN = date(2026, 8, 27)
INICIO_5A, INICIO_2A = date(2021, 8, 30), date(2024, 8, 28)


def activos(universe: Universe) -> List[Any]:
    """Los que el bot puede comprar hoy: de ahí el sesgo de supervivencia, que no se corrige."""

    return [a for a in select_assets(universe, SuperbotConfig()) if a.trade_republic == BROKER_VERIFICADO]


def par_fx(currency: str) -> str:
    return f"{currency}EUR=X"


def simbolos(config: AdvisorConfig, universe: Universe) -> List[str]:
    elegidos = activos(universe)
    extra = {config.market_context.vix_symbol, config.market_context.trend_symbol, REFERENCIA}
    extra |= {a.primary_symbol for a in context_assets_of(universe) if a.region == "ASIA"}
    extra |= {b for a in elegidos if (b := resolve_benchmark_symbol(a, config.report))}
    extra |= {par_fx(a.currency) for a in elegidos if a.currency != "EUR"}
    return sorted({a.symbol for a in elegidos} | extra)


def congelar(config: AdvisorConfig, universe: Universe, proveedor: Any, raiz: Path) -> Any:
    return freeze_vintage(
        simbolos(config, universe), proveedor, interval="1d", start=DESCARGA_INICIO, end=DESCARGA_FIN_EXCLUSIVO,
        root_dir=raiz, request_context={"uso": "superbot-ia simulaciones de reglas (D-84)"},
    )


def _fechas(index: pd.Index, market: str) -> List[date]:
    fechas = [session_date_of(marca, market) for marca in index]
    if any(f is None for f in fechas):
        raise ValueError(f"plaza {market} sin sesión")
    return [f for f in fechas if f is not None]


def serie_de(asset: Any, barras: pd.DataFrame, market: str) -> Serie:
    columnas = ("Open", "High", "Low", "Close")
    return Serie(
        asset.symbol, market, asset.currency, tuple(_fechas(barras.index, market)),
        *(tuple(float(v) for v in barras[c]) for c in columnas),
    )


def cierres(vintage: VintageLoad, symbol: str) -> Tuple[Sequence[date], Sequence[float]]:
    barras = vintage.by_symbol[symbol].execution_prices
    # Los pares de divisa no tienen plaza: su fecha es la de la propia barra.
    fechas = [date.fromisoformat(str(m)[:10]) for m in barras.index] if symbol.endswith("=X") else _fechas(barras.index, market_for_symbol(symbol))
    return fechas, [float(v) for v in barras["Close"]]


def fichas_de(
    asset: Any, vintage: VintageLoad, config: AdvisorConfig, resolver: Any, market: str, politica: PoliticaIA,
) -> Tuple[Dict[date, Ficha], Dict[str, int]]:
    """Score v1, niveles y SMA de cada sesión con lo conocido a su cierre, y por qué falta cada una que falte."""

    barras = vintage.by_symbol[asset.symbol].execution_prices
    ventana = config.horizonte(politica.horizonte)
    benchmark = resolve_benchmark_symbol(asset, config.report)
    cierre_benchmark = frozen_close(vintage, benchmark) if benchmark else None
    series = build_snapshot_series(
        barras, config.indicators, config.levels, ventana.interval, cierre_benchmark,
        asset_timezone=market_session(market).timezone,
        benchmark_timezone=market_session(market_for_symbol(benchmark)).timezone if benchmark else None,
    )
    contextos = resolver.contexts_for_index(barras.index, signal_market=market)
    fechas = _fechas(barras.index, market)
    sma = barras["Close"].rolling(politica.sma_periodo).mean()
    fichas: Dict[date, Ficha] = {}
    faltan: Dict[str, int] = {}
    for j in range(WARMUP_BARS, len(barras)):
        resuelto = contextos[j]
        if resuelto is None or not resuelto.calculable or resuelto.context is None:
            faltan["contexto"] = faltan.get("contexto", 0) + 1
            continue
        contexto: List[Any] = [None] * len(barras)
        contexto[j] = resuelto.context
        senal = _signal(asset, series, j, config, politica.horizonte, WARMUP_BARS, None, None, None, contexto, "1.0")
        if senal is None:
            faltan["niveles"] = faltan.get("niveles", 0) + 1
            continue
        n = senal["levels"]
        media = float(sma.iloc[j])
        fichas[fechas[j]] = Ficha(
            float(senal["score"]), n.price, n.stop, n.target2, n.entry_max, n.min_rr_ratio, n.rr_ratio,
            (n.target3 - n.price) / config.levels.target_atr_multiples[2], n.invalidation_level,
            None if pd.isna(media) else media,
        )
    return fichas, faltan


def preparar(
    vintage: VintageLoad, config: AdvisorConfig, universe: Universe,
) -> Tuple[Dict[str, Serie], Dict[str, Mapping[date, Ficha]], Dict[str, Tuple[Sequence[date], Sequence[float]]], Dict[str, Any]]:
    resolver, politica = _context_resolver(config, universe, vintage), PoliticaIA()
    series: Dict[str, Serie] = {}
    fichas: Dict[str, Mapping[date, Ficha]] = {}
    fx: Dict[str, Tuple[Sequence[date], Sequence[float]]] = {}
    informe: Dict[str, Any] = {"sin_datos": [], "fichas": 0, "faltan": {}}
    for asset in activos(universe):
        if asset.symbol not in vintage.by_symbol or (
            asset.currency != "EUR" and par_fx(asset.currency) not in vintage.by_symbol
        ):
            informe["sin_datos"].append(asset.symbol)
            continue
        market = mercado_para_simbolo(asset, asset.symbol)
        series[asset.symbol] = serie_de(asset, vintage.by_symbol[asset.symbol].execution_prices, market)
        fichas[asset.symbol], faltan = fichas_de(asset, vintage, config, resolver, market, politica)
        informe["fichas"] += len(fichas[asset.symbol])
        for motivo, cuantas in faltan.items():
            informe["faltan"][motivo] = informe["faltan"].get(motivo, 0) + cuantas
        if asset.currency != "EUR" and asset.currency not in fx:
            fx[asset.currency] = cierres(vintage, par_fx(asset.currency))
    informe["valores"] = len(series)
    return series, fichas, fx, informe


__all__ = ["FIN", "INICIO_2A", "INICIO_5A", "activos", "cierres", "congelar", "preparar", "simbolos"]
