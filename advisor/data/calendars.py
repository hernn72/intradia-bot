"""Calendarios bursátiles por plaza.

Las sesiones esperadas de un activo salen de su propia plaza. Para activos
cripto se usa un calendario natural 24/7, porque no tienen cierre bursátil.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import cache
from typing import Protocol

import exchange_calendars as xcals
import pandas as pd

from advisor.data.sessions import MARKET_SESSIONS, market_session

MARKET_TO_MIC = {market: session.mic for market, session in MARKET_SESSIONS.items()}


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


def expected_sessions(market: str, start: date, end: date) -> list[date]:
    if end < start:
        return []
    sessions = exchange_calendar(market).sessions_in_range(start, end)
    return [pd.Timestamp(value).date() for value in sessions]


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
