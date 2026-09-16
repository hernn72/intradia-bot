"""Calendarios bursátiles por plaza.

Las sesiones esperadas de un activo salen de su propia plaza. Para activos
cripto se usa un calendario natural 24/7, porque no tienen cierre bursátil.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from functools import cache
from pathlib import Path
from typing import Protocol

import exchange_calendars as xcals
import pandas as pd
import yaml

from advisor.data.sessions import MARKET_SESSIONS, market_session

MARKET_TO_MIC = {market: session.mic for market, session in MARKET_SESSIONS.items()}
EXCHANGE_OVERRIDES_PATH = Path("exchange_overrides.yaml")
_REQUIRED_OVERRIDE_FIELDS = frozenset({"fecha", "motivo", "fuente", "verificado_el"})


@dataclass(frozen=True)
class CalendarOverrideEntry:
    fecha: date
    motivo: str
    fuente: str
    verificado_el: date


@dataclass(frozen=True)
class ExchangeOverride:
    cierres_adicionales: tuple[CalendarOverrideEntry, ...]
    aperturas_forzadas: tuple[CalendarOverrideEntry, ...]


class _Calendar(Protocol):
    def sessions_in_range(self, start: date | str, end: date | str) -> pd.DatetimeIndex:
        ...

    def is_session(self, value: date | str) -> bool:
        ...


class Crypto247Calendar:
    """Calendario 24/7 para cripto."""

    name = "CRYPTO_24_7"

    def sessions_in_range(self, start: date | str, end: date | str) -> pd.DatetimeIndex:
        start_date = pd.Timestamp(start).date()
        end_date = pd.Timestamp(end).date()
        if end_date < start_date:
            return pd.DatetimeIndex([])
        return pd.date_range(start_date, end_date, freq="D")

    def is_session(self, value: date | str) -> bool:
        pd.Timestamp(value)
        return True


@cache
def exchange_calendar(market: str) -> _Calendar:
    mic = calendar_mic(market)
    if mic == "CRYPTO_24_7":
        return Crypto247Calendar()
    return xcals.get_calendar(mic)


def calendar_mic(market: str) -> str:
    try:
        return MARKET_TO_MIC[market]
    except KeyError:
        raise ValueError(f"plaza '{market}' sin calendario declarado") from None


def market_timezone(market: str) -> str:
    return market_session(market).timezone


def load_exchange_overrides(path: Path | str | None = None) -> dict[str, ExchangeOverride]:
    override_path = Path(path) if path is not None else EXCHANGE_OVERRIDES_PATH
    return _load_exchange_overrides(override_path)


@cache
def _load_exchange_overrides(override_path: Path) -> dict[str, ExchangeOverride]:
    # Su ausencia no puede significar «sin correcciones»: eso devolvería en
    # silencio los huecos falsos que estas correcciones eliminan. Falla como
    # falta config.yaml o universe.yaml.
    if not override_path.exists():
        raise FileNotFoundError(
            f"{override_path}: falta el fichero de correcciones de calendario. "
            "Sin él no se puede afirmar qué sesiones esperaba cada plaza."
        )
    with override_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{override_path}: debe ser un mapeo por MIC")

    known_mics = set(MARKET_TO_MIC.values())
    overrides: dict[str, ExchangeOverride] = {}
    for mic, payload in raw.items():
        if mic not in known_mics:
            raise ValueError(f"{override_path}: MIC desconocido en overrides: {mic}")
        if not isinstance(payload, dict):
            raise ValueError(f"{override_path}: override de {mic} debe ser un mapeo")
        cierres = _parse_override_entries(override_path, mic, payload, "cierres_adicionales")
        aperturas = _parse_override_entries(override_path, mic, payload, "aperturas_forzadas")
        fechas_cierre = {entry.fecha for entry in cierres}
        fechas_apertura = {entry.fecha for entry in aperturas}
        solapadas = sorted(fechas_cierre & fechas_apertura)
        if solapadas:
            labels = ", ".join(value.isoformat() for value in solapadas)
            raise ValueError(f"{override_path}: {mic} tiene fechas en ambas listas: {labels}")
        _validar_aperturas_forzadas(override_path, mic, aperturas)
        overrides[mic] = ExchangeOverride(
            cierres_adicionales=tuple(cierres),
            aperturas_forzadas=tuple(aperturas),
        )
    return overrides


def _validar_aperturas_forzadas(path: Path, mic: str, aperturas: list[CalendarOverrideEntry]) -> None:
    """Una apertura forzada declara que la librería marcó cerrado un día que sí operó.

    Se valida al cargar y no al consultar, para que un error se vea al
    arrancar y no se traduzca en una fecha descartada en silencio a mitad de
    una pasada. No se prohíben fines de semana: existen sesiones especiales, y
    cada entrada viene con fuente y fecha de verificación.
    """

    if not aperturas:
        return
    calendar = xcals.get_calendar(mic)
    for entry in aperturas:
        try:
            ya_es_sesion = bool(calendar.is_session(pd.Timestamp(entry.fecha)))
        except Exception as exc:
            raise ValueError(
                f"{path}: {mic} declara una apertura forzada el {entry.fecha.isoformat()} "
                f"fuera del rango del calendario ({exc})"
            ) from None
        if ya_es_sesion:
            raise ValueError(
                f"{path}: {mic} declara una apertura forzada el {entry.fecha.isoformat()}, "
                "pero el calendario ya la considera sesión: la entrada no corrige nada"
            )


def _parse_override_entries(
    path: Path,
    mic: str,
    payload: dict,
    list_name: str,
) -> list[CalendarOverrideEntry]:
    raw_entries = payload.get(list_name, [])
    if not isinstance(raw_entries, list):
        raise ValueError(f"{path}: {mic}.{list_name} debe ser una lista")

    entries: list[CalendarOverrideEntry] = []
    for index, raw_entry in enumerate(raw_entries, start=1):
        if not isinstance(raw_entry, dict):
            raise ValueError(f"{path}: {mic}.{list_name}[{index}] debe ser un mapeo")
        missing = sorted(_REQUIRED_OVERRIDE_FIELDS - set(raw_entry))
        if missing:
            raise ValueError(f"{path}: falta {missing[0]} en {mic}.{list_name}[{index}]")
        entries.append(
            CalendarOverrideEntry(
                fecha=_parse_override_date(raw_entry["fecha"], path, mic, list_name, index, "fecha"),
                motivo=_parse_non_empty_text(raw_entry["motivo"], path, mic, list_name, index, "motivo"),
                fuente=_parse_non_empty_text(raw_entry["fuente"], path, mic, list_name, index, "fuente"),
                verificado_el=_parse_override_date(
                    raw_entry["verificado_el"], path, mic, list_name, index, "verificado_el"
                ),
            )
        )
    return entries


def _parse_override_date(value: object, path: Path, mic: str, list_name: str, index: int, field: str) -> date:
    try:
        return pd.Timestamp(value).date()
    except Exception:
        raise ValueError(f"{path}: {mic}.{list_name}[{index}].{field} no es una fecha valida") from None


def _parse_non_empty_text(value: object, path: Path, mic: str, list_name: str, index: int, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: {mic}.{list_name}[{index}].{field} debe ser texto no vacio")
    return value.strip()


def expected_sessions(market: str, start: date, end: date) -> list[date]:
    if end < start:
        return []
    calendar = exchange_calendar(market)
    sessions = {pd.Timestamp(value).date() for value in calendar.sessions_in_range(start, end)}
    mic = calendar_mic(market)
    override = load_exchange_overrides().get(mic)
    if override is not None:
        sessions -= {entry.fecha for entry in override.cierres_adicionales if start <= entry.fecha <= end}
        for entry in override.aperturas_forzadas:
            if start <= entry.fecha <= end:
                sessions.add(entry.fecha)
    return sorted(sessions)


def session_override_kind(market: str, value: date) -> str | None:
    """Tipo de override que afecta a una fecha de plaza, si existe."""

    mic = calendar_mic(market)
    override = load_exchange_overrides().get(mic)
    if override is None:
        return None
    if any(entry.fecha == value for entry in override.cierres_adicionales):
        return "cierre_adicional"
    if any(entry.fecha == value for entry in override.aperturas_forzadas):
        return "apertura_forzada"
    return None


def missing_sessions(actual: set[date], market: str, start: date, end: date) -> tuple[date, ...]:
    return tuple(value for value in expected_sessions(market, start, end) if value not in actual)


def closed_sessions_between(last_bar_date: date, reference_date: date, market: str) -> int:
    """Cuenta sesiones cerradas tras la última barra y antes de la fecha de referencia."""

    if reference_date <= last_bar_date:
        return 0
    start = last_bar_date + timedelta(days=1)
    end = reference_date - timedelta(days=1)
    if end < start:
        return 0
    return len(expected_sessions(market, start, end))
