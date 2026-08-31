"""Frescura de datos de mercado.

El cálculo de sesiones excluye fines de semana, pero no festivos: es una
aproximación explícita porque el proyecto no mantiene calendarios bursátiles.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd

from advisor.universe.models import Asset


@dataclass(frozen=True)
class DataFreshness:
    """Antigüedad de una última barra.

    ``sessions_approx`` cuenta sesiones laborables cerradas perdidas entre la
    última barra y la referencia, excluyendo fines de semana pero no festivos
    de cada plaza.
    """

    last_bar_date: date
    natural_days: int
    sessions_approx: int
    label: str


@dataclass(frozen=True)
class FreshnessRow:
    """Resultado de medir un símbolo del universo."""

    symbol: str
    data_symbol: str
    market: str
    freshness: Optional[DataFreshness]
    error: Optional[str] = None


@dataclass(frozen=True)
class FreshnessBucket:
    """Escalón agrupado por fecha de última barra."""

    last_bar_date: date
    freshness: DataFreshness
    rows: List[FreshnessRow]

    @property
    def symbols_count(self) -> int:
        return len(self.rows)

    @property
    def markets_label(self) -> str:
        counts: Dict[str, int] = {}
        for row in self.rows:
            counts[row.market] = counts.get(row.market, 0) + 1
        parts = [
            f"{market} ({count})" if count > 1 else market
            for market, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]
        return ", ".join(parts)


def calcular_frescura_dato(last_bar_timestamp: object, reference: datetime) -> DataFreshness:
    """Calcula antigüedad natural y en sesiones aproximadas de una última barra.

    La antigüedad en sesiones cerradas perdidas es aproximada: cuenta
    lunes-viernes estrictamente anteriores a la fecha de referencia y no resta
    festivos ni cierres parciales de cada mercado.
    """

    last_bar_date = _fecha(last_bar_timestamp)
    reference_date = reference.date()
    natural_days = max(0, (reference_date - last_bar_date).days)
    sessions_approx = _sesiones_cerradas_perdidas_entre(last_bar_date, reference_date)
    return DataFreshness(
        last_bar_date=last_bar_date,
        natural_days=natural_days,
        sessions_approx=sessions_approx,
        label=_freshness_label(natural_days, sessions_approx),
    )


def agrupar_frescura_por_fecha(rows: List[FreshnessRow]) -> List[FreshnessBucket]:
    buckets: Dict[date, List[FreshnessRow]] = {}
    for row in rows:
        if row.freshness is None:
            continue
        buckets.setdefault(row.freshness.last_bar_date, []).append(row)
    grouped: List[FreshnessBucket] = []
    for last_date, rows_for_date in sorted(buckets.items(), reverse=True):
        freshness = rows_for_date[0].freshness
        if freshness is None:
            continue
        grouped.append(FreshnessBucket(last_bar_date=last_date, freshness=freshness, rows=rows_for_date))
    return grouped


def mercado_para_simbolo(asset: Asset, data_symbol: str) -> str:
    """Plaza usada para ``data_symbol``, priorizando metadatos del universo."""

    if asset.european_symbol is not None and data_symbol == asset.european_symbol:
        return asset.european_market or _mercado_por_sufijo(data_symbol)
    if data_symbol == asset.primary_symbol:
        return asset.primary_market
    return _mercado_por_sufijo(data_symbol)


def _fecha(value: object) -> date:
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise TypeError(f"timestamp no soportado para frescura: {value!r}")


def _sesiones_cerradas_perdidas_entre(last_bar_date: date, reference_date: date) -> int:
    """Cuenta días laborables cerrados perdidos, sin incluir la sesión en curso."""

    if reference_date <= last_bar_date:
        return 0
    current = last_bar_date + timedelta(days=1)
    sessions = 0
    while current < reference_date:
        if current.weekday() < 5:
            sessions += 1
        current += timedelta(days=1)
    return sessions


def _freshness_label(natural_days: int, sessions_approx: int) -> str:
    if sessions_approx == 0:
        sessions_text = "al día"
    elif sessions_approx == 1:
        sessions_text = "≈1 sesión sin festivos"
    else:
        sessions_text = f"≈{sessions_approx} sesiones sin festivos"

    if natural_days == 0:
        days_text = "hoy"
    elif natural_days == 1:
        days_text = "hace 1 día natural"
    else:
        days_text = f"hace {natural_days} días naturales"
    return f"{days_text}; {sessions_text}"


def _mercado_por_sufijo(symbol: str) -> str:
    suffixes = {
        ".DE": "XETRA",
        ".PA": "EURONEXT",
        ".AS": "EURONEXT",
        ".MI": "MILAN",
        ".CO": "COPENHAGEN",
        ".MC": "BME",
        ".T": "JPX",
        ".HK": "HKG",
        ".KS": "KSC",
    }
    for suffix, market in suffixes.items():
        if symbol.endswith(suffix):
            return market
    if symbol.startswith("^"):
        return "INDICE"
    if "-" in symbol:
        return "CRYPTO"
    return "DESCONOCIDO"
