"""Calidad del dato separada por dimensiones."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from advisor.data.calendars import closed_sessions_between


class Severity(Enum):
    OK = "OK"
    WARNING = "WARNING"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FreshnessState(Enum):
    FRESH = "FRESH"
    STALE_1 = "STALE_1"
    STALE_2_PLUS = "STALE_2_PLUS"
    PARTIAL_BAR = "PARTIAL_BAR"


@dataclass(frozen=True)
class QualityReason:
    code: str
    severity: Severity
    detail: str
    sessions_ago: int


@dataclass(frozen=True)
class DataQuality:
    freshness: FreshnessState
    recent_completeness: Severity
    historical_completeness: Severity
    indicator_readiness: bool
    execution_readiness: bool
    reasons: tuple[QualityReason, ...] = field(default_factory=tuple)
    indicators_missing: tuple[str, ...] = field(default_factory=tuple)
    measurement_period: str = ""
    measurement_interval: str = ""


MISSING_RECENT_DATA = "MISSING_RECENT_DATA"
MISSING_HISTORICAL_DATA = "MISSING_HISTORICAL_DATA"
STALE_DATA = "STALE_DATA"
PARTIAL_BAR = "PARTIAL_BAR"
INVALID_INDICATORS = "INVALID_INDICATORS"


def build_data_quality(
    *,
    market: str,
    reference_date: date,
    sessions_approx: int,
    may_be_partial_current_session: bool,
    absent_reference_sessions: tuple[date, ...],
    absent_recent_sessions: tuple[date, ...],
    indicators_missing: tuple[str, ...],
    measurement_period: str,
    measurement_interval: str,
    critical_latest_sessions: int,
    high_after_sessions: int,
    medium_after_sessions: int,
    warning_after_sessions: int,
) -> DataQuality:
    """Construye calidad estructurada sin tocar indicadores ni puntuación."""

    freshness = _freshness_state(sessions_approx, may_be_partial_current_session)
    recent_completeness = Severity.OK
    historical_completeness = Severity.OK
    sessions_ago = 0
    reasons: list[QualityReason] = []

    historical_absent_sessions = tuple(
        value for value in absent_reference_sessions if value not in set(absent_recent_sessions)
    )
    if absent_recent_sessions:
        newest_recent = max(absent_recent_sessions)
        recent_sessions_ago = closed_sessions_between(newest_recent, reference_date, market)
        recent_completeness = severity_for_sessions_ago(
            recent_sessions_ago,
            critical_latest_sessions=critical_latest_sessions,
            high_after_sessions=high_after_sessions,
            medium_after_sessions=medium_after_sessions,
            warning_after_sessions=warning_after_sessions,
        )
        sessions_ago = recent_sessions_ago
        reasons.append(
            QualityReason(
                code=MISSING_RECENT_DATA,
                severity=recent_completeness,
                detail=_provider_gap_detail(absent_recent_sessions),
                sessions_ago=recent_sessions_ago,
            )
        )
    if historical_absent_sessions:
        newest_historical = max(historical_absent_sessions)
        historical_sessions_ago = closed_sessions_between(newest_historical, reference_date, market)
        historical_completeness = severity_for_sessions_ago(
            historical_sessions_ago,
            critical_latest_sessions=critical_latest_sessions,
            high_after_sessions=high_after_sessions,
            medium_after_sessions=medium_after_sessions,
            warning_after_sessions=warning_after_sessions,
        )
        if not absent_recent_sessions:
            sessions_ago = historical_sessions_ago
        reasons.append(
            QualityReason(
                code=MISSING_HISTORICAL_DATA,
                severity=historical_completeness,
                detail=_provider_gap_detail(historical_absent_sessions),
                sessions_ago=historical_sessions_ago,
            )
        )
    if freshness is not FreshnessState.FRESH:
        reasons.append(
            QualityReason(
                code=PARTIAL_BAR if freshness is FreshnessState.PARTIAL_BAR else STALE_DATA,
                severity=Severity.WARNING if freshness is FreshnessState.PARTIAL_BAR else Severity.HIGH,
                detail=f"frescura={freshness.value}",
                sessions_ago=sessions_approx,
            )
        )
    if indicators_missing:
        reasons.append(
            QualityReason(
                code=INVALID_INDICATORS,
                severity=Severity.CRITICAL,
                detail="indicadores no calculables: " + ", ".join(indicators_missing),
                sessions_ago=sessions_ago,
            )
        )

    indicator_readiness = not indicators_missing
    # El contrato escrito dice ``recent_completeness <= MEDIUM``, pero la misma
    # ficha y D-05 fijan que MEDIUM (6-20 sesiones) veta. Por eso solo OK y
    # WARNING pasan la dimensión de completitud reciente.
    execution_readiness = (
        freshness is FreshnessState.FRESH
        and recent_completeness in {Severity.OK, Severity.WARNING}
        and indicator_readiness
    )
    return DataQuality(
        freshness=freshness,
        recent_completeness=recent_completeness,
        historical_completeness=historical_completeness,
        indicator_readiness=indicator_readiness,
        indicators_missing=indicators_missing,
        execution_readiness=execution_readiness,
        reasons=tuple(reasons),
        measurement_period=measurement_period,
        measurement_interval=measurement_interval,
    )


def severity_for_sessions_ago(
    sessions_ago: int,
    *,
    critical_latest_sessions: int,
    high_after_sessions: int,
    medium_after_sessions: int,
    warning_after_sessions: int,
) -> Severity:
    if sessions_ago <= critical_latest_sessions:
        return Severity.CRITICAL
    if sessions_ago <= high_after_sessions:
        return Severity.HIGH
    if sessions_ago <= medium_after_sessions:
        return Severity.MEDIUM
    if sessions_ago > warning_after_sessions:
        return Severity.WARNING
    return Severity.WARNING


def _freshness_state(sessions_approx: int, may_be_partial_current_session: bool) -> FreshnessState:
    if may_be_partial_current_session:
        return FreshnessState.PARTIAL_BAR
    if sessions_approx <= 0:
        return FreshnessState.FRESH
    if sessions_approx == 1:
        return FreshnessState.STALE_1
    return FreshnessState.STALE_2_PLUS


def _severity_rank(severity: Severity) -> int:
    return {
        Severity.OK: 0,
        Severity.WARNING: 1,
        Severity.MEDIUM: 2,
        Severity.HIGH: 3,
        Severity.CRITICAL: 4,
    }[severity]


def _provider_gap_detail(absent: tuple[date, ...]) -> str:
    # T-004 verificó que las ausencias vivas son huecos del proveedor con la
    # plaza abierta; se reutiliza el vocabulario de bar_diagnostics en vez de
    # crear una taxonomía paralela.
    return f"{_provider_gap_class()}: " + ", ".join(value.isoformat() for value in absent)


def _provider_gap_class() -> str:
    from advisor.data.bar_diagnostics import CLASE_PROVEEDOR_NO_ENTREGA

    return CLASE_PROVEEDOR_NO_ENTREGA
