"""Observaciones numéricas de señal para el protocolo de investigación."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import pandas as pd

from advisor.analysis.scoring import Score
from advisor.analysis.snapshot import TechnicalSnapshot
from advisor.universe.models import Asset


@dataclass(frozen=True)
class DimensionObservation:
    """Resumen numérico de una dimensión, sin componentes ni texto formateado."""

    name: str
    points: float
    max: float
    available: bool


@dataclass(frozen=True)
class SignalObservation:
    """Señal potencial con insumos primitivos, no niveles de una política concreta."""

    signal_id: str
    data_vintage_id: str
    asset: str
    horizonte: str
    signal_idx: int
    signal_timestamp: pd.Timestamp
    score_value: float
    evaluable_max: float
    dimensions: Tuple[DimensionObservation, ...]
    price: float
    atr: Optional[float]
    low_lookback: Optional[float]
    high_lookback: Optional[float]
    ema_fast: Optional[float]


def stable_signal_id(asset: str, horizonte: str, timestamp: pd.Timestamp) -> str:
    """Identificador determinista del evento económico de señal."""

    stamp = timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp)
    return f"{asset}|{horizonte}|{stamp}"


def build_signal_observation(
    *,
    asset: Asset,
    horizonte: str,
    signal_idx: int,
    snapshot: TechnicalSnapshot,
    score: Score,
    data_vintage_id: str = "",
) -> SignalObservation:
    """Extrae una observación ligera desde el cálculo completo de señal."""

    return SignalObservation(
        signal_id=stable_signal_id(asset.symbol, horizonte, snapshot.timestamp),
        data_vintage_id=data_vintage_id,
        asset=asset.symbol,
        horizonte=horizonte,
        signal_idx=signal_idx,
        signal_timestamp=snapshot.timestamp,
        score_value=score.value,
        evaluable_max=score.evaluable_max,
        dimensions=tuple(
            DimensionObservation(
                name=dimension.name,
                points=dimension.points,
                max=dimension.weight,
                available=dimension.available,
            )
            for dimension in score.dimensions
        ),
        price=snapshot.price,
        atr=snapshot.atr,
        low_lookback=snapshot.low_lookback,
        high_lookback=snapshot.high_lookback,
        ema_fast=snapshot.ema_fast,
    )
