"""Gate P2.5 de capacidad estadística."""

from __future__ import annotations

from datetime import timedelta

from advisor.research.capacity import INSUFICIENTE, assess_capacity, format_capacity_report
from advisor.research.event_study import EventStudyResult
from advisor.research.timestamps import parse_timestamp
from tests.test_event_study import _signal


def test_banda_80_no_calibra_threshold_con_pocas_observaciones() -> None:
    signals = [
        _with_day(_signal(score=85.0, status="TARGET_FIRST" if i < 40 else "STOP_FIRST"), i)
        for i in range(78)
    ]
    result = EventStudyResult(
        data_vintage_id="vintage",
        horizonte="swing",
        cost_pct=0.2,
        warmup_bars=120,
        max_hold_bars=40,
        signals=signals,
        evaluated_assets=["TEST"],
        asset_bar_counts={"TEST": 1255},
    )

    report = assess_capacity(result)
    by_label = {summary.label: summary for summary in report.bands}

    assert by_label["80+"].verdict == INSUFICIENTE
    assert by_label["80+"].nominal_n == 78
    assert by_label["80+"].n_blocks == 2
    assert by_label["80+"].block_length == 40
    assert by_label["80+"].interval_width > 0
    assert by_label["80+"].conclusive is False
    assert "no se permite calibrar un threshold apoyándose en 80+" in format_capacity_report(report)


def test_capacidad_distingue_global_banda_y_comparacion() -> None:
    signals = []
    for i in range(180):
        signal = _with_day(_signal(score=55.0, status="TARGET_FIRST"), i)
        object.__setattr__(signal.observation, "signal_idx", i)
        signals.append(signal)
    for i in range(180):
        signal = _with_day(_signal(score=85.0, status="STOP_FIRST"), i)
        object.__setattr__(signal.observation, "signal_idx", i)
        signals.append(signal)

    result = EventStudyResult(
        data_vintage_id="vintage",
        horizonte="swing",
        cost_pct=0.2,
        warmup_bars=120,
        max_hold_bars=40,
        signals=signals,
        evaluated_assets=["TEST"],
        asset_bar_counts={"TEST": 1255},
    )

    report = assess_capacity(result)
    by_label = {summary.label: summary for summary in report.bands}

    assert report.global_summary.verdict == INSUFICIENTE
    assert by_label["50-60"].nominal_n == 180
    assert by_label["80+"].nominal_n == 180
    assert report.comparisons[0].label == "50-60 vs 80+"
    assert report.comparisons[0].conclusive is False


def test_bloques_son_temporales_y_no_activo_por_tiempo() -> None:
    signals = []
    for day in range(80):
        for asset in ("A", "B", "C"):
            signal = _with_day(_signal(score=55.0, status="TARGET_FIRST"), day)
            object.__setattr__(signal.observation, "asset", asset)
            signals.append(signal)

    result = EventStudyResult(
        data_vintage_id="vintage",
        horizonte="swing",
        cost_pct=0.2,
        warmup_bars=120,
        max_hold_bars=40,
        signals=signals,
        evaluated_assets=["A", "B", "C"],
        asset_bar_counts={"A": 80, "B": 80, "C": 80},
    )

    report = assess_capacity(result)

    assert report.global_summary.nominal_n == 240
    assert report.global_summary.n_blocks == 2


def _with_day(signal, day: int):
    timestamp = parse_timestamp("2026-01-01T00:00:00Z") + timedelta(days=day)
    raw = timestamp.isoformat().replace("+00:00", "Z")
    object.__setattr__(signal.observation, "signal_timestamp", timestamp)
    object.__setattr__(signal.observation, "signal_timestamp_raw", raw)
    return signal
