"""Tipos e identidad de T-024, sin lógica de precios."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping, Tuple
from zoneinfo import ZoneInfo

T024_PREREG_SHA = "dfcca0ef3428df916089480a0ca574f47e550c24"
# `T024_CODE_SHA` no vive en `advisor/`: escribirlo aquí cambiaría el propio ejecutor después de ese SHA y
# `executor_unchanged_since` fallaría siempre. Se lee de un sidecar versionado fuera de los EXECUTOR_PATHS.
T024_CODE_LOCK = "evidence/2026-10-05-T-024-code-lock/T024_CODE_SHA.txt"
DEV_VINTAGE_ID = "071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841"

CUTOFF_CONSUMIDA = date(2026, 8, 27)
C_E_FINAL = date(2027, 8, 27)
Q_MIN = 120
W_MIN = 26
N_MIN = 100
BLOCK_WEEKS = 10
B = 10_000
SEED = 20261005
Q_LO = 0.00625
Q_HI = 0.99375
FEE = 0.001
SLIP_BPS = 5.0
MAX_HOLD = 40
MIN_RR = 1.5
MIN_SESIONES_DRIFT = 60
MIN_SESIONES_FUERA = 20
DIAS_COSECHA_DECISIVA = 75
POLITICAS_DECISORIAS = ("B2", "S2")
POLITICAS_DESCRIPTIVAS = ("C0",)
HORIZONTE = "swing"
WARMUP_BARS = 120


@dataclass(frozen=True)
class SenalT024:
    signal_id: str
    policy: str
    asset: str
    s_index: int
    s_session: date
    e_session: date
    analysis_ts: datetime
    stop: float
    target2: float
    entry_max: float


@dataclass(frozen=True)
class ConteoCaptura:
    policy: str
    senales_operar: int
    ejecutables: int
    rechazos: Mapping[str, int]
    q_p: int
    w_p: int
    barras_nuevas: int = 0
    barras_revisadas: int = 0
    cumple: bool = False
    exclusiones: Mapping[str, int] | None = None


def semana_iso(dia: date) -> Tuple[int, int]:
    """Semana ISO estable para agrupar capacidad."""

    iso = dia.isocalendar()
    return iso.year, iso.week


def es_elegible_temporal(s_session: date, e_session: date, c_e: date) -> bool:
    """Elegibilidad literal de T-024: señal posterior al corte consumido y entrada dentro del corte."""

    return s_session > CUTOFF_CONSUMIDA and e_session <= c_e


def local_dates(index: Any, tz: str) -> Tuple[date, ...]:
    """Sesiones locales exactamente como `_local_dates` de P6 (`advisor/research/p6.py`)."""

    import pandas as pd

    stamps = pd.DatetimeIndex(pd.to_datetime(index, utc=True, format="mixed"))
    return tuple(stamp.date() for stamp in stamps.tz_convert(ZoneInfo(tz)))
