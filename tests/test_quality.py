"""Calidad del dato por dimensiones y severidad por antigüedad."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd

from advisor.config import DataQualityConfig
from advisor.data.calendars import closed_sessions_between, expected_sessions
from advisor.data.freshness import calcular_frescura_serie
from advisor.data.quality import MISSING_HISTORICAL_DATA, MISSING_RECENT_DATA, STALE_DATA, FreshnessState, Severity

REFERENCE = datetime(2026, 9, 14, 7, 0, tzinfo=timezone.utc)
REAL_REFERENCE = datetime(2026, 9, 16, 7, 0, tzinfo=timezone.utc)


def _history_without(
    absent: set[date],
    *,
    start: date = date(2026, 1, 2),
    end: date = date(2026, 9, 11),
) -> pd.DataFrame:
    sessions = [value for value in expected_sessions("XETRA", start, end) if value not in absent]
    index = pd.DatetimeIndex([pd.Timestamp(value, tz="UTC") for value in sessions])
    values = [100.0 + index for index, _ in enumerate(sessions)]
    return pd.DataFrame(
        {
            "Open": values,
            "High": [value + 1 for value in values],
            "Low": [value - 1 for value in values],
            "Close": values,
            "Volume": [1_000_000.0] * len(values),
        },
        index=index,
    )


def _freshness_for(
    absent: set[date],
    *,
    reference: datetime = REFERENCE,
    end: date = date(2026, 9, 11),
    indicators_missing: tuple[str, ...] = (),
):
    freshness = calcular_frescura_serie(
        _history_without(absent, end=end),
        reference,
        market="XETRA",
        strength_benchmark="^STOXX50E",
        recent_reference_sessions=220,
        veto_window_sessions=20,
        indicators_missing=indicators_missing,
        measurement_period="1y",
        measurement_interval="1d",
    )
    return freshness


def _quality_for(absent: date, *, indicators_missing: tuple[str, ...] = ()):
    return _freshness_for({absent}, indicators_missing=indicators_missing).data_quality


def test_exh1_retraso_sin_ausencias_no_fabrica_missing_recent_data() -> None:
    freshness = _freshness_for(set(), reference=REAL_REFERENCE, end=date(2026, 9, 14))
    quality = freshness.data_quality

    assert freshness.absent_recent_sessions == ()
    assert freshness.absent_reference_sessions == ()
    assert quality.freshness is FreshnessState.STALE_1
    assert quality.recent_completeness is Severity.OK
    assert quality.historical_completeness is Severity.OK
    assert quality.execution_readiness is False
    assert [(reason.code, reason.severity) for reason in quality.reasons] == [(STALE_DATA, Severity.HIGH)]


def test_ausente_reciente_usa_absent_recent_sessions() -> None:
    quality = _quality_for(date(2026, 9, 8))

    assert quality.recent_completeness is Severity.HIGH
    assert quality.historical_completeness is Severity.OK
    assert quality.execution_readiness is False
    assert quality.reasons[0].code == MISSING_RECENT_DATA


def test_ausente_hace_quince_sesiones_es_medium_y_no_ejecutable() -> None:
    quality = _quality_for(date(2026, 8, 21))

    assert quality.recent_completeness is Severity.MEDIUM
    assert quality.historical_completeness is Severity.OK
    assert quality.execution_readiness is False


def test_sxr8_ausencia_fuera_de_ventana_es_historical_warning() -> None:
    freshness = _freshness_for({date(2026, 3, 6)}, reference=REAL_REFERENCE, end=date(2026, 9, 14))
    quality = freshness.data_quality

    assert freshness.absent_recent_sessions == ()
    assert freshness.absent_reference_sessions == (date(2026, 3, 6),)
    assert quality.recent_completeness is Severity.OK
    assert quality.historical_completeness is Severity.WARNING
    assert quality.reasons[0].code == MISSING_HISTORICAL_DATA


def test_sessions_ago_de_ausencia_historica_usa_calendario_de_plaza() -> None:
    quality = _freshness_for({date(2026, 3, 6)}, reference=REAL_REFERENCE, end=date(2026, 9, 14)).data_quality

    reason = next(reason for reason in quality.reasons if reason.code == MISSING_HISTORICAL_DATA)
    assert reason.sessions_ago == closed_sessions_between(date(2026, 3, 6), REAL_REFERENCE.date(), "XETRA")
    assert reason.sessions_ago > 20


def test_d05_hueco_fuera_de_ventana_degrada_sin_marcar_incompleto() -> None:
    freshness = _freshness_for({date(2026, 3, 6)}, reference=REAL_REFERENCE, end=date(2026, 9, 14))

    assert freshness.quality == "DEGRADADO"
    assert freshness.data_quality.recent_completeness is Severity.OK
    assert any(reason.startswith("DEGRADADO: faltan sesiones") for reason in freshness.quality_reasons)
    assert not any(reason.startswith("INCOMPLETO") for reason in freshness.quality_reasons)


def test_festivo_de_plaza_no_es_ausencia() -> None:
    freshness = calcular_frescura_serie(
        _history_without(set(), start=date(2026, 3, 30)),
        datetime(2026, 4, 7, 7, 0, tzinfo=timezone.utc),
        market="XETRA",
        recent_reference_sessions=20,
        veto_window_sessions=20,
        measurement_period="1mo",
        measurement_interval="1d",
    )

    assert date(2026, 4, 3) not in freshness.absent_reference_sessions
    assert freshness.data_quality.recent_completeness is Severity.OK


def test_sma_long_no_calculable_por_hueco_veta_indicadores() -> None:
    quality = _quality_for(date(2026, 2, 10), indicators_missing=("sma_long",))

    assert quality.indicator_readiness is False
    assert quality.indicators_missing == ("sma_long",)
    assert quality.execution_readiness is False


def test_ventana_medida_queda_en_data_quality() -> None:
    quality = _quality_for(date(2026, 2, 10))

    assert quality.measurement_period == "1y"
    assert quality.measurement_interval == "1d"
    assert DataQualityConfig().medium_after_sessions == DataQualityConfig().veto_window_sessions
