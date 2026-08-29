"""Dimensionamiento de posición a partir del riesgo asumido.

El cálculo es puro y solo devuelve magnitudes adimensionales. Si hay capital
configurado, convertirlo a la divisa nativa y calcular acciones corresponde a
la capa de informe, que es donde existe el tipo de cambio.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from advisor.analysis.levels import Levels
from advisor.analysis.scoring import Score
from advisor.config import PortfolioConfig


@dataclass(frozen=True)
class PositionSizing:
    """Tamaño de posición recomendado para un presupuesto de riesgo dado."""

    label: str
    risk_pct: float
    position_pct: float
    uncapped_position_pct: float
    capped_by: Optional[str] = None


def conviction_label(score: Score) -> str:
    """Etiqueta informativa de convicción; no dimensiona la posición."""

    value = score.value
    if value >= 80:
        return "Alta convicción"
    if value >= 70:
        return "Convicción media"
    return "Especulativa"


def calculate_position_sizing(
    levels: Levels,
    portfolio: PortfolioConfig,
    label: str,
) -> PositionSizing:
    """Calcula tamaño de posición desde presupuesto de riesgo y distancia al stop."""

    if levels.price <= 0 or levels.risk_pp <= 0:
        return PositionSizing(
            label=label,
            risk_pct=0.0,
            position_pct=0.0,
            uncapped_position_pct=0.0,
            capped_by="riesgo no calculable",
        )

    uncapped_position_pct = portfolio.risk_per_trade_pct / (levels.risk_pp / 100)
    position_pct = min(uncapped_position_pct, portfolio.max_position_pct)
    capped_by = (
        f"tope máximo por posición ({portfolio.max_position_pct:g}%)"
        if position_pct < uncapped_position_pct
        else None
    )

    risk_pct = min(portfolio.risk_per_trade_pct, position_pct * levels.risk_pp / 100)

    return PositionSizing(
        label=label,
        risk_pct=risk_pct,
        position_pct=position_pct,
        uncapped_position_pct=uncapped_position_pct,
        capped_by=capped_by,
    )
