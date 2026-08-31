"""Gate P2.5 de capacidad estadística."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

import advisor.research.capacity as capacity
from advisor.research.capacity import INSUFICIENTE, assess_capacity, format_capacity_report
from advisor.research.event_study import AMBIGUOUS, STOP_FIRST, TARGET_FIRST, EventStudyResult, band_of_full_score
from advisor.research.timestamps import parse_timestamp
from advisor.universe.models import Asset, Universe
from tests.test_event_study import _signal


def test_banda_80_no_calibra_threshold_con_pocas_observaciones() -> None:
    signals = [
        _with_day(_signal(score=85.0, status="TARGET_FIRST" if i < 40 else "STOP_FIRST"), i)
        for i in range(78)
    ]
    result = _result(signals)

    report = assess_capacity(result, universe=_universe())
    by_label = {summary.label: summary for summary in report.bands}

    assert by_label["80+"].verdict == INSUFICIENTE
    assert by_label["80+"].nominal_n == 78
    assert by_label["80+"].n_blocks == 2
    assert by_label["80+"].block_length == 60
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

    result = _result(signals)

    report = assess_capacity(result, universe=_universe())
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

    result = _result(signals)

    report = assess_capacity(result, universe=_universe("A", "B", "C"))

    assert report.global_summary.nominal_n == 240
    assert report.global_summary.n_blocks == 2


def test_assess_capacity_por_defecto_no_cambia() -> None:
    signals = [_with_day(_signal(score=55.0 if i < 120 else 85.0, status="TARGET_FIRST"), i) for i in range(240)]
    result = _result(signals)

    assert assess_capacity(result, universe=_universe()) == assess_capacity(
        result,
        universe=_universe(),
        band_of=band_of_full_score,
    )


def test_gate_cuenta_ambiguous_como_cota_inferior_no_como_resultado_resuelto() -> None:
    signals = [
        _signal(score=55.0, status=TARGET_FIRST),
        _signal(score=55.0, status=AMBIGUOUS),
        _signal(score=55.0, status=STOP_FIRST),
    ]

    assert capacity._target_first(signals) == 1
    assert "cota inferior" in capacity._target_first.__doc__


def test_intervalo_de_capacidad_delega_en_bootstrap_p26() -> None:
    block_rates = [(0.2, 10), (0.4, 10), (0.8, 10), (0.6, 10)]

    assert capacity._block_mean_interval(block_rates) == capacity.bootstrap_block_mean_interval(
        block_rates,
        seed=capacity.DEFAULT_SEED,
        n_resamples=capacity.DEFAULT_RESAMPLES,
        confidence=0.95,
    )


def test_plaza_sin_zona_falla_ruidosamente() -> None:
    signal = _with_day(_signal(score=55.0, status=TARGET_FIRST), 0)
    universe = _universe(market="SIN_TABLA")
    result = _result([signal])

    with pytest.raises(ValueError, match="plaza 'SIN_TABLA' sin zona horaria"):
        assess_capacity(result, universe=universe)


def _with_day(signal, day: int):
    timestamp = parse_timestamp("2026-01-05T00:00:00Z") + timedelta(days=_business_day_offset(day))
    raw = timestamp.isoformat().replace("+00:00", "Z")
    object.__setattr__(signal.observation, "signal_timestamp", timestamp)
    object.__setattr__(signal.observation, "signal_timestamp_raw", raw)
    return signal


def _business_day_offset(index: int) -> int:
    day = date(2026, 1, 5)
    offset = 0
    seen = 0
    while seen < index:
        offset += 1
        if (day + timedelta(days=offset)).weekday() < 5:
            seen += 1
    return offset


def _result(signals) -> EventStudyResult:
    assets = sorted({signal.observation.asset for signal in signals})
    session_dates_by_asset = {
        asset: tuple(
            sorted({
                signal.observation.signal_timestamp.date()
                for signal in signals
                if signal.observation.asset == asset
            })
        )
        for asset in assets
    }
    return EventStudyResult(
        data_vintage_id="vintage",
        horizonte="swing",
        cost_pct=0.2,
        warmup_bars=120,
        max_hold_bars=40,
        signals=list(signals),
        evaluated_assets=assets,
        asset_bar_counts=dict.fromkeys(assets, 1255),
        session_dates_by_asset=session_dates_by_asset,
    )


def _universe(*symbols: str, market: str = "XETRA") -> Universe:
    if not symbols:
        symbols = ("TEST",)
    assets = [
        Asset(
            primary_symbol=symbol,
            primary_market=market,
            primary_currency="EUR",
            name=symbol,
            asset_class="stock",
            region="EUROPA",
            economic_currency="EUR",
            timezone="Europe/Berlin",
            isin=None,
            requires_isin=True,
        )
        for symbol in symbols
    ]
    return Universe(groups={"test": assets})
