"""Frescura de datos de mercado."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional

import pandas as pd

from advisor.data.calendars import calendar_mic, closed_sessions_between, expected_sessions, missing_sessions
from advisor.universe.models import Asset

QUALITY_OK = "OK"
QUALITY_DEGRADED = "DEGRADADO"
QUALITY_INCOMPLETE = "INCOMPLETO"


@dataclass(frozen=True)
class DataFreshness:
    """Antigüedad de una última barra.

    ``sessions_approx`` cuenta sesiones cerradas perdidas del calendario de la
    plaza entre la última barra y la referencia.
    """

    last_bar_date: date
    natural_days: int
    sessions_approx: int
    label: str
    may_be_partial_current_session: bool = False
    calendar: str = ""
    strength_benchmark: Optional[str] = None
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
        return bool(self.calendar)


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


def calcular_frescura_dato(
    last_bar_timestamp: object,
    reference: datetime,
    market: str = "XETRA",
) -> DataFreshness:
    """Calcula antigüedad natural y en sesiones aproximadas de una última barra.

    La antigüedad en sesiones cerradas perdidas usa el calendario de la plaza.
    """

    last_bar_date = _fecha(last_bar_timestamp)
    reference_date = reference.date()
    natural_days = max(0, (reference_date - last_bar_date).days)
    sessions_approx = closed_sessions_between(last_bar_date, reference_date, market)
    return DataFreshness(
        last_bar_date=last_bar_date,
        natural_days=natural_days,
        sessions_approx=sessions_approx,
        label=_freshness_label(natural_days, sessions_approx),
        may_be_partial_current_session=_may_be_partial_current_session(last_bar_date, reference, market, 0),
        calendar=calendar_mic(market),
    )


def calcular_frescura_serie(
    history: pd.DataFrame,
    reference: datetime,
    market: str,
    strength_benchmark: Optional[str] = None,
    recent_reference_sessions: int = 10,
    veto_window_sessions: int = 10,
    asset_timezone: Optional[str] = None,
    settlement_minutes: int = 0,
) -> DataFreshness:
    """Calcula frescura de cola y sesiones ausentes frente al calendario de plaza.

    Las ausencias se buscan solo en sesiones interiores: fechas que existen
    en el calendario hasta la última fecha del activo, y faltan en el activo.
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

    freshness = calcular_frescura_dato(history.index[-1], reference, market)

    asset_dates = _fechas_indice(history.index, asset_timezone)
    if not asset_dates:
        return classify_data_quality(DataFreshness(
            **_freshness_kwargs(freshness),
            strength_benchmark=strength_benchmark,
        ))

    last_asset_date = asset_dates[-1]
    first_asset_date = asset_dates[0]
    reference_dates = expected_sessions(market, first_asset_date, last_asset_date)
    checked_dates = reference_dates[-recent_reference_sessions:]
    veto_dates = set(reference_dates[-veto_window_sessions:])
    asset_date_set = set(asset_dates)
    absent = tuple(value for value in missing_sessions(asset_date_set, market, checked_dates[0], checked_dates[-1])) if checked_dates else ()
    absent_recent = tuple(value for value in absent if value in veto_dates)
    freshness_values = _freshness_kwargs(freshness)
    freshness_values["may_be_partial_current_session"] = _may_be_partial_current_session(
        last_asset_date,
        reference,
        market,
        settlement_minutes,
    )
    return classify_data_quality(DataFreshness(
        **freshness_values,
        strength_benchmark=strength_benchmark,
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
            "INCOMPLETO: faltan sesiones cerradas recientes frente al calendario de la plaza "
            + ", ".join(value.isoformat() for value in freshness.absent_recent_sessions)
            + f" (ventana de veto: {freshness.veto_window_sessions} sesiones)"
        )
        return replace(freshness, quality=QUALITY_INCOMPLETE, quality_reasons=tuple(reasons))
    if freshness.absent_reference_sessions:
        reasons.append(
            "DEGRADADO: faltan sesiones frente al calendario de la plaza fuera de la ventana de veto "
            + ", ".join(value.isoformat() for value in freshness.absent_reference_sessions)
        )
    if freshness.sessions_approx > 0:
        reasons.append(f"DEGRADADO: dato viejo ({freshness.label})")
    if not freshness.calendar or freshness.reference_sessions_checked == 0:
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
        return asset.european_market or _market_for_data_symbol(data_symbol, asset.asset_class)
    if data_symbol == asset.primary_symbol:
        return asset.primary_market
    return _market_for_data_symbol(data_symbol, asset.asset_class)


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
        "calendar": freshness.calendar,
        "session_close_status": freshness.session_close_status,
    }

def _freshness_label(natural_days: int, sessions_approx: int) -> str:
    if sessions_approx == 0:
        sessions_text = "al día"
    elif sessions_approx == 1:
        sessions_text = "1 sesión"
    else:
        sessions_text = f"{sessions_approx} sesiones"

    if natural_days == 0:
        days_text = "hoy"
    elif natural_days == 1:
        days_text = "hace 1 día natural"
    else:
        days_text = f"hace {natural_days} días naturales"
    return f"{days_text}; {sessions_text}"


def _may_be_partial_current_session(
    last_bar_date: date,
    reference: datetime,
    market: str,
    settlement_minutes: int,
) -> bool:
    if market != "CRYPTO":
        return last_bar_date == reference.date()
    if reference.tzinfo is None:
        reference_utc = reference.replace(tzinfo=timezone.utc)
    else:
        reference_utc = reference.astimezone(timezone.utc)
    settled_at = datetime.combine(last_bar_date + timedelta(days=1), time(0, 0), tzinfo=timezone.utc)
    settled_at = settled_at + timedelta(minutes=settlement_minutes)
    return reference_utc < settled_at


def _market_for_data_symbol(symbol: str, asset_class: str) -> str:
    from advisor.data.sessions import market_for_symbol

    return market_for_symbol(symbol, asset_class=asset_class)
