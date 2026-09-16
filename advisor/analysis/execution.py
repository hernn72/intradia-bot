"""Evaluación explícita de ejecutabilidad a un precio de entrada efectivo."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

from advisor.analysis.levels import Levels, reward_risk, rr_at_least
from advisor.analysis.sizing import PositionSizing, calculate_position_sizing
from advisor.config import DataQualityConfig, PortfolioConfig, RiskConfig
from advisor.data.freshness import DataFreshness
from advisor.universe.models import Asset

EXECUTABLE = "EXECUTABLE"
ABOVE_MAX_ENTRY = "ABOVE_MAX_ENTRY"
RR_TOO_LOW = "RR_TOO_LOW"
INVALID_STOP = "INVALID_STOP"
INVALID_TARGET = "INVALID_TARGET"
POSITION_TOO_SMALL = "POSITION_TOO_SMALL"
DATA_NOT_EXECUTABLE = "DATA_NOT_EXECUTABLE"
BROKER_UNVERIFIED = "BROKER_UNVERIFIED"
BROKER_UNAVAILABLE = "BROKER_UNAVAILABLE"


@dataclass(frozen=True)
class ExecutionEvaluation:
    """Resultado de ejecución recalculado al precio efectivo de entrada."""

    reference_price: float
    entry_price: float
    entry_max: float
    stop: float
    targets: Tuple[float, float, float]
    rr: Optional[float]
    risk_pct: float
    potential_pct: float
    position_size: PositionSizing
    capital_at_risk: Optional[float]
    executable: bool
    reason: str


def evaluate_trade_at_entry(
    *,
    levels: Levels,
    entry_price: float,
    risk: RiskConfig,
    portfolio: PortfolioConfig,
    label: str,
    asset: Optional[Asset] = None,
    data_freshness: Optional[DataFreshness] = None,
    data_quality: Optional[DataQualityConfig] = None,
) -> ExecutionEvaluation:
    """Recalcula ejecutabilidad y sizing usando ``entry_price``."""

    sizing = calculate_position_sizing(levels, portfolio, label, entry_price=entry_price)
    rr = reward_risk(entry_price, levels.target2, levels.stop)
    risk_pct = (entry_price - levels.stop) / entry_price * 100 if entry_price > 0 else 0.0
    potential_pct = (levels.target2 / entry_price - 1) * 100 if entry_price > 0 else 0.0
    capital_at_risk = None
    if portfolio.capital is not None:
        capital_at_risk = portfolio.capital * sizing.risk_pct / 100

    reason = EXECUTABLE
    executable = True
    if levels.stop >= entry_price or risk_pct <= 0:
        reason, executable = INVALID_STOP, False
    elif levels.target2 <= entry_price:
        reason, executable = INVALID_TARGET, False
    elif entry_price > levels.entry_max and not math.isclose(entry_price, levels.entry_max, rel_tol=1e-9):
        reason, executable = ABOVE_MAX_ENTRY, False
    elif rr is None or not rr_at_least(rr, risk.min_rr_ratio):
        reason, executable = RR_TOO_LOW, False
    elif sizing.position_pct <= 0:
        reason, executable = POSITION_TOO_SMALL, False
    elif data_freshness is not None and data_freshness.data_quality is not None and (
        not data_freshness.data_quality.execution_readiness
    ) and (
        data_quality is None or data_quality.veto_incomplete_open
    ):
        reason, executable = DATA_NOT_EXECUTABLE, False
    elif asset is not None and not asset.is_recommendable:
        reason, executable = BROKER_UNAVAILABLE, False
    elif asset is not None and asset.trade_republic == "unknown":
        reason = BROKER_UNVERIFIED

    return ExecutionEvaluation(
        reference_price=levels.price,
        entry_price=entry_price,
        entry_max=levels.entry_max,
        stop=levels.stop,
        targets=(levels.target1, levels.target2, levels.target3),
        rr=rr,
        risk_pct=risk_pct,
        potential_pct=potential_pct,
        position_size=sizing,
        capital_at_risk=capital_at_risk,
        executable=executable,
        reason=reason,
    )
