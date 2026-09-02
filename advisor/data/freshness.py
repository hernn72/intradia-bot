"""Frescura de datos de mercado.

El cálculo de sesiones excluye fines de semana, pero no festivos: es una
aproximación explícita porque el proyecto no mantiene calendarios bursátiles.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd

from advisor.universe.models import Asset

QUALITY_OK = "OK"
QUALITY_DEGRADED = "DEGRADADO"
QUALITY_INCOMPLETE = "INCOMPLETO"


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
    may_be_partial_current_session: bool = False
    benchmark_symbol: Optional[str] = None
    absent_reference_sessions: tuple[date, ...] = field(default_factory=tuple)
    absent_recent_sessions: tuple[date, ...] = field(default_factory=tuple)
    reference_sessions_checked: int = 0
    veto_window_sessions: int = 0
    session_close_status: str = ""
    quality: str = QUALITY_OK
    quality_reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_absent_reference_sessions(self) -> bool:
        return bool(self.absent_reference_sessions)

    @property
    def has_reference_calendar(self) -> bool:
        return self.benchmark_symbol is not None


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
        may_be_partial_current_session=last_bar_date == reference_date,
    )


def calcular_frescura_serie(
    history: pd.DataFrame,
    reference: datetime,
    benchmark_close: Optional[pd.Series] = None,
    benchmark_symbol: Optional[str] = None,
    recent_reference_sessions: int = 10,
    veto_window_sessions: int = 10,
    asset_timezone: Optional[str] = None,
    benchmark_timezone: Optional[str] = None,
) -> DataFreshness:
    """Calcula frescura de cola y sesiones ausentes frente al benchmark.

    Las ausencias se buscan solo en sesiones interiores: fechas que existen
    en el benchmark hasta la última fecha del activo, y faltan en el activo.
    Las sesiones posteriores a la última barra del activo ya están cubiertas
    por ``sessions_approx``.

    Se distinguen dos ventanas a propósito. ``recent_reference_sessions`` cubre
    todo lo que alimenta los indicadores y sirve para declarar; sobre ella se
    informa, no se veta. ``veto_window_sessions`` es la ventana corta en la que
    un hueco distorsiona de verdad la señal viva —RSI, ATR, MACD y los retornos
    cortos— y es la única que bloquea abrir. Medido el 2026-09-02 sobre el
    universo real: con la ventana larga se vetaban tres activos por huecos de
    hace meses, que quedarían vetados para siempre.
    """

    if history.empty:
        raise ValueError("el histórico está vacío")

    freshness = calcular_frescura_dato(history.index[-1], reference)
    if benchmark_symbol is None:
        return classify_data_quality(freshness)
    if benchmark_close is None or benchmark_close.empty:
        return classify_data_quality(DataFreshness(
            **_freshness_kwargs(freshness),
            benchmark_symbol=benchmark_symbol,
        ))

    asset_dates = _fechas_indice(history.index, asset_timezone)
    benchmark_dates = _fechas_indice(benchmark_close.dropna().index, benchmark_timezone)
    if not asset_dates or not benchmark_dates:
        return classify_data_quality(DataFreshness(
            **_freshness_kwargs(freshness),
            benchmark_symbol=benchmark_symbol,
        ))

    last_asset_date = asset_dates[-1]
    reference_dates = [value for value in benchmark_dates if value <= last_asset_date]
    checked_dates = reference_dates[-recent_reference_sessions:]
    veto_dates = set(reference_dates[-veto_window_sessions:])
    asset_date_set = set(asset_dates)
    absent = tuple(value for value in checked_dates if value not in asset_date_set)
    absent_recent = tuple(value for value in absent if value in veto_dates)
    return classify_data_quality(DataFreshness(
        **_freshness_kwargs(freshness),
        benchmark_symbol=benchmark_symbol,
        absent_reference_sessions=absent,
        absent_recent_sessions=absent_recent,
        reference_sessions_checked=len(checked_dates),
        veto_window_sessions=veto_window_sessions,
    ))


def classify_data_quality(freshness: DataFreshness) -> DataFreshness:
    """Asigna OK/DEGRADADO/INCOMPLETO sin cambiar ningún cálculo técnico."""

    reasons: List[str] = []
    if freshness.absent_recent_sessions:
        reasons.append(
            "INCOMPLETO: faltan sesiones cerradas recientes frente al calendario del benchmark "
            + ", ".join(value.isoformat() for value in freshness.absent_recent_sessions)
            + f" (ventana de veto: {freshness.veto_window_sessions} sesiones)"
        )
        return replace(freshness, quality=QUALITY_INCOMPLETE, quality_reasons=tuple(reasons))
    if freshness.absent_reference_sessions:
        reasons.append(
            "DEGRADADO: faltan sesiones frente al benchmark fuera de la ventana de veto "
            + ", ".join(value.isoformat() for value in freshness.absent_reference_sessions)
        )
    if freshness.sessions_approx > 0:
        reasons.append(f"DEGRADADO: dato viejo ({freshness.label})")
    if freshness.benchmark_symbol is None or freshness.reference_sessions_checked == 0:
        reasons.append("DEGRADADO: sin calendario de referencia")
    if reasons:
        return replace(freshness, quality=QUALITY_DEGRADED, quality_reasons=tuple(reasons))
    return replace(freshness, quality=QUALITY_OK, quality_reasons=())


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


def _fecha(value: object, timezone_name: Optional[str] = None) -> date:
    zone = None
    if timezone_name is not None:
        from zoneinfo import ZoneInfo

        zone = ZoneInfo(timezone_name)
    if isinstance(value, pd.Timestamp):
        if zone is not None and value.tzinfo is not None:
            return value.to_pydatetime().astimezone(zone).date()
        return value.date()
    if isinstance(value, datetime):
        if zone is not None and value.tzinfo is not None:
            return value.astimezone(zone).date()
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        parsed = pd.Timestamp(value)
        if zone is not None and parsed.tzinfo is not None:
            return parsed.to_pydatetime().astimezone(zone).date()
        return parsed.date()
    raise TypeError(f"timestamp no soportado para frescura: {value!r}")


def _fechas_indice(index: pd.Index, timezone_name: Optional[str] = None) -> List[date]:
    dates = sorted({_fecha(value, timezone_name) for value in index})
    return dates


def _freshness_kwargs(freshness: DataFreshness) -> dict:
    return {
        "last_bar_date": freshness.last_bar_date,
        "natural_days": freshness.natural_days,
        "sessions_approx": freshness.sessions_approx,
        "label": freshness.label,
        "may_be_partial_current_session": freshness.may_be_partial_current_session,
        "session_close_status": freshness.session_close_status,
    }


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
