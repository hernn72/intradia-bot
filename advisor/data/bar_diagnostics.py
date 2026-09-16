"""Diagnostico de barras ausentes sin persistir resultados."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable, Protocol
from zoneinfo import ZoneInfo

import pandas as pd

from advisor.analysis.snapshot import build_snapshot_series
from advisor.config import AdvisorConfig
from advisor.data.calendars import calendar_mic, expected_sessions, session_override_kind
from advisor.data.freshness import mercado_para_simbolo
from advisor.data.sessions import _session_date, trim_unclosed_bar
from advisor.storage.db import AdvisorDB
from advisor.universe.models import Asset, Universe

DIAGNOSTIC_PERIODS = ("1mo", "1y", "5y")
CLASE_MERCADO_CERRADO = "mercado cerrado"
CLASE_PROVEEDOR_NO_ENTREGA = "proveedor no la entrega"
CLASE_PIPELINE_LA_PIERDE = "pipeline la pierde"
CLASE_BARRA_PRESENTE = "barra presente"
CLASE_DESCARGA_FALLIDA = "descarga fallida"
CLASE_FUERA_RANGO_CONSULTADO = "fuera del rango consultado"
CLASE_PLAZA_SIN_CALENDARIO = "plaza sin calendario declarado"
CLASE_SIMBOLO_FUERA_UNIVERSO = "simbolo fuera del universo"


class DiagnosticProvider(Protocol):
    def get_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        ...

    def get_raw_history(
        self,
        symbol: str,
        period: str = "1y",
        interval: str = "1d",
        *,
        drop_na: bool = True,
    ) -> pd.DataFrame:
        ...


@dataclass(frozen=True)
class PeriodBarDiagnosis:
    period: str
    raw_timestamp: str | None
    original_timezone: str
    converted_timestamp: str | None
    converted_timezone: str
    session_date: date | None
    present_raw: bool
    present_after_dropna: bool
    present_after_trim: bool
    present_in_snapshot: bool
    range_start: date | None = None
    range_end: date | None = None
    error: str | None = None


@dataclass(frozen=True)
class BarDiagnosis:
    symbol: str
    data_symbol: str
    market: str
    mic: str
    fecha: date
    calendar_session: bool
    calendar_override: str | None
    periods: tuple[PeriodBarDiagnosis, ...]
    status: str | None = None

    @property
    def classification(self) -> str:
        if self.status is not None:
            return self.status
        if self.periods and all(item.error is not None for item in self.periods) and not any(
            item.present_raw for item in self.periods
        ):
            return CLASE_DESCARGA_FALLIDA
        if not self.calendar_session and not any(item.present_raw for item in self.periods):
            return CLASE_MERCADO_CERRADO
        if any(item.present_raw and not item.present_after_trim for item in self.periods):
            return CLASE_PIPELINE_LA_PIERDE
        if any(item.present_raw and item.present_after_trim and not item.present_in_snapshot for item in self.periods):
            return CLASE_PIPELINE_LA_PIERDE
        if self.calendar_session and not any(item.present_raw for item in self.periods):
            return CLASE_PROVEEDOR_NO_ENTREGA
        return CLASE_BARRA_PRESENTE


def diagnose_bar(
    asset: Asset,
    fecha: date,
    *,
    provider: DiagnosticProvider,
    config: AdvisorConfig,
    reference: datetime | None = None,
    periods: Iterable[str] = DIAGNOSTIC_PERIODS,
) -> BarDiagnosis:
    reference_time = reference or datetime.now(timezone.utc)
    data_symbol = asset.data_symbol(reference_time)
    market = mercado_para_simbolo(asset, data_symbol)
    try:
        mic = calendar_mic(market)
        calendar_session = fecha in set(expected_sessions(market, fecha, fecha))
        override = session_override_kind(market, fecha)
    except ValueError as exc:
        return BarDiagnosis(
            symbol=asset.symbol,
            data_symbol=data_symbol,
            market=market,
            mic="N/D",
            fecha=fecha,
            calendar_session=False,
            calendar_override=str(exc),
            periods=(),
            status=CLASE_PLAZA_SIN_CALENDARIO,
        )
    period_results = tuple(
        _diagnose_period(
            data_symbol,
            fecha,
            market=market,
            asset_timezone=asset.timezone,
            provider=provider,
            config=config,
            reference=reference_time,
            period=period,
        )
        for period in periods
    )
    status = _range_status(fecha, reference_time, period_results)
    return BarDiagnosis(
        symbol=asset.symbol,
        data_symbol=data_symbol,
        market=market,
        mic=mic,
        fecha=fecha,
        calendar_session=calendar_session,
        calendar_override=override,
        periods=period_results,
        status=status,
    )


def diagnose_all_saved_gaps(
    *,
    db: AdvisorDB,
    universe: Universe,
    provider: DiagnosticProvider,
    config: AdvisorConfig,
    reference: datetime | None = None,
) -> tuple[BarDiagnosis, ...]:
    gaps = db.get_latest_freshness_absences()
    diagnoses: list[BarDiagnosis] = []
    cached_provider = _CachedDiagnosticProvider(provider)
    for symbol, missing_date in gaps:
        asset = universe.get(symbol)
        if asset is None:
            diagnoses.append(_missing_asset_diagnosis(symbol, missing_date))
            continue
        diagnoses.append(
            diagnose_bar(asset, missing_date, provider=cached_provider, config=config, reference=reference)
        )
    return tuple(diagnoses)


def _diagnose_period(
    symbol: str,
    fecha: date,
    *,
    market: str,
    asset_timezone: str,
    provider: DiagnosticProvider,
    config: AdvisorConfig,
    reference: datetime,
    period: str,
) -> PeriodBarDiagnosis:
    try:
        raw = provider.get_raw_history(symbol, period=period, interval="1d", drop_na=False)
    except Exception as exc:
        return PeriodBarDiagnosis(
            period=period,
            raw_timestamp=None,
            original_timezone="N/D",
            converted_timestamp=None,
            converted_timezone=asset_timezone,
            session_date=None,
            present_raw=False,
            present_after_dropna=False,
            present_after_trim=False,
            present_in_snapshot=False,
            error=str(exc),
        )

    zone = ZoneInfo(asset_timezone)
    raw_match = _first_row_for_session(raw, fecha, zone)
    range_start, range_end = _session_range(raw, zone)
    dropna = raw.dropna(subset=["Close"]) if "Close" in raw.columns else raw.iloc[0:0]
    dropna_match = _first_row_for_session(dropna, fecha, zone)
    history_error: str | None = None
    try:
        history = provider.get_history(symbol, period=period, interval="1d")
    except Exception as exc:
        history = raw.iloc[0:0]
        history_error = str(exc)
    trim = trim_unclosed_bar(
        history,
        market=market,
        reference=reference,
        settlement_minutes=config.data_quality.settlement_minutes,
        interval="1d",
    )
    trim_match = _first_row_for_session(trim.df, fecha, zone)
    snapshot_present = _snapshot_contains_session(trim.df, fecha, zone, config)
    raw_timestamp = raw_match.isoformat() if raw_match is not None else None
    converted = raw_match.tz_convert(zone) if raw_match is not None and raw_match.tzinfo is not None else raw_match
    original_tz = _timezone_label(raw_match)
    return PeriodBarDiagnosis(
        period=period,
        raw_timestamp=raw_timestamp,
        original_timezone=original_tz,
        converted_timestamp=converted.isoformat() if converted is not None else None,
        converted_timezone=asset_timezone,
        session_date=_session_date(raw_match, zone) if raw_match is not None else None,
        present_raw=raw_match is not None,
        present_after_dropna=dropna_match is not None,
        present_after_trim=trim_match is not None,
        present_in_snapshot=snapshot_present,
        range_start=range_start,
        range_end=range_end,
        error=history_error,
    )


@dataclass
class _CachedDiagnosticProvider:
    provider: DiagnosticProvider

    def __post_init__(self) -> None:
        self._history_cache: dict[tuple[str, str, str], pd.DataFrame] = {}
        self._raw_cache: dict[tuple[str, str, str, bool], pd.DataFrame] = {}

    def get_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        key = (symbol, period, interval)
        if key not in self._history_cache:
            self._history_cache[key] = self.provider.get_history(symbol, period=period, interval=interval)
        return self._history_cache[key]

    def get_raw_history(
        self,
        symbol: str,
        period: str = "1y",
        interval: str = "1d",
        *,
        drop_na: bool = True,
    ) -> pd.DataFrame:
        key = (symbol, period, interval, drop_na)
        if key not in self._raw_cache:
            self._raw_cache[key] = self.provider.get_raw_history(
                symbol,
                period=period,
                interval=interval,
                drop_na=drop_na,
            )
        return self._raw_cache[key]


def _missing_asset_diagnosis(symbol: str, fecha: date) -> BarDiagnosis:
    return BarDiagnosis(
        symbol=symbol,
        data_symbol=symbol,
        market="N/D",
        mic="N/D",
        fecha=fecha,
        calendar_session=False,
        calendar_override=CLASE_SIMBOLO_FUERA_UNIVERSO,
        periods=(),
        status=CLASE_SIMBOLO_FUERA_UNIVERSO,
    )


def _range_status(
    fecha: date,
    reference: datetime,
    periods: tuple[PeriodBarDiagnosis, ...],
) -> str | None:
    if fecha > reference.date():
        return CLASE_FUERA_RANGO_CONSULTADO
    ranges = [(item.range_start, item.range_end) for item in periods if item.range_start and item.range_end]
    if ranges and all(start is not None and end is not None and (fecha < start or fecha > end) for start, end in ranges):
        return CLASE_FUERA_RANGO_CONSULTADO
    return None


def _first_row_for_session(df: pd.DataFrame, fecha: date, zone: ZoneInfo) -> pd.Timestamp | None:
    if df.empty:
        return None
    for value in df.index:
        timestamp = pd.Timestamp(value)
        if _session_date(timestamp, zone) == fecha:
            return timestamp
    return None


def _session_range(df: pd.DataFrame, zone: ZoneInfo) -> tuple[date | None, date | None]:
    if df.empty:
        return None, None
    dates = [_session_date(pd.Timestamp(value), zone) for value in df.index]
    return min(dates), max(dates)


def _snapshot_contains_session(df: pd.DataFrame, fecha: date, zone: ZoneInfo, config: AdvisorConfig) -> bool:
    if df.empty or _first_row_for_session(df, fecha, zone) is None:
        return False
    try:
        series = build_snapshot_series(df, config.indicators, config.levels, "1d")
    except Exception:
        return False
    return _first_row_for_session(series.df, fecha, zone) is not None


def _timezone_label(timestamp: pd.Timestamp | None) -> str:
    if timestamp is None:
        return "N/D"
    if timestamp.tzinfo is None:
        return "naive"
    return str(timestamp.tzinfo)


def format_bar_diagnosis(diagnosis: BarDiagnosis) -> str:
    override = f" ({diagnosis.calendar_override})" if diagnosis.calendar_override else ""
    lines = [
        (
            f"{diagnosis.symbol} · datos {diagnosis.data_symbol} · plaza {diagnosis.market} · "
            f"MIC {diagnosis.mic} · fecha {diagnosis.fecha.isoformat()}"
        ),
        f"Calendario dice sesion: {'si' if diagnosis.calendar_session else 'no'}{override}",
        f"Clase: {diagnosis.classification}",
        (
            "| period | raw timestamp | tz original | timestamp convertido | tz convertida | "
            "session_date | dropna | trim | snapshot | error |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for item in diagnosis.periods:
        lines.append(
            f"| {item.period} | {item.raw_timestamp or 'N/D'} | {item.original_timezone} | "
            f"{item.converted_timestamp or 'N/D'} | {item.converted_timezone} | "
            f"{item.session_date.isoformat() if item.session_date else 'N/D'} | {_yes_no(item.present_after_dropna)} | "
            f"{_yes_no(item.present_after_trim)} | {_yes_no(item.present_in_snapshot)} | {item.error or ''} |"
        )
    return "\n".join(lines)


def format_many_bar_diagnoses(diagnoses: Iterable[BarDiagnosis], measured_at: str | None = None) -> str:
    # La poblacion sale de la ultima pasada guardada, que puede ser de hace
    # semanas y haberse medido con reglas anteriores. Sin decir de cuando es,
    # la tabla se lee como si fuera de hoy.
    lines: list[str] = []
    if measured_at is None:
        lines.append("Poblacion: sin pasada de frescura guardada")
    else:
        lines.append(f"Poblacion: ausencias de la pasada de frescura del {measured_at}")
    lines.append("")
    lines += [
        "| Simbolo | Fecha | Plaza | MIC | Sesion | Override | Clase | Error |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for diagnosis in diagnoses:
        errors = "; ".join(item.error for item in diagnosis.periods if item.error)
        lines.append(
            f"| {diagnosis.symbol} | {diagnosis.fecha.isoformat()} | {diagnosis.market} | {diagnosis.mic} | "
            f"{_yes_no(diagnosis.calendar_session)} | {diagnosis.calendar_override or ''} | "
            f"{diagnosis.classification} | {errors} |"
        )
    return "\n".join(lines)


def decode_absent_sessions(raw: str) -> tuple[date, ...]:
    values = json.loads(raw)
    if not isinstance(values, list):
        return ()
    return tuple(date.fromisoformat(str(value)) for value in values)


def _yes_no(value: bool) -> str:
    return "si" if value else "no"
