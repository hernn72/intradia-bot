"""Conversión explícita entre texto congelado y tiempo de cálculo.

La cosecha usa cadenas como formato canónico y esas cadenas entran en los
hashes. Interpretarlas como ``datetime`` es necesario para cálculo, pero no
autoriza a reserializarlas y sustituir el texto original.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd


def timestamp_raw(value: object) -> str:
    """Texto canónico que identifica una barra sin normalizarlo si ya es texto."""

    if isinstance(value, str):
        return value
    if isinstance(value, pd.Timestamp):
        if value.tzinfo is not None:
            return value.tz_convert(timezone.utc).isoformat().replace("+00:00", "Z")
        if value.time() == datetime.min.time():
            return value.date().isoformat()
        return value.isoformat()
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        if value.time() == datetime.min.time():
            return value.date().isoformat()
        return value.isoformat()
    return str(value)


def parse_timestamp(raw: str) -> datetime:
    """Interpreta el texto canónico como ``datetime`` timezone-aware."""

    text = raw.strip()
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
