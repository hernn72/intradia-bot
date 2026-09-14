"""Tests de la ablación P2.4 del score."""

from __future__ import annotations

import ast
import inspect
import math
from dataclasses import replace
from datetime import date, timedelta

import pytest

import advisor.research.ablation as ablation
from advisor.analysis.levels import compute_levels_from_inputs
from advisor.config import LevelsConfig, RiskConfig
from advisor.research.ablation import build_ablation_record, format_ablation_report, run_ablation
from advisor.research.event_study import (
    AMBIGUOUS,
    STOP_FIRST,
    TARGET_FIRST,
    EventStudyResult,
    evaluate_managed_event,
)
from advisor.research.observations import DimensionObservation, SignalObservation
from advisor.research.timestamps import parse_timestamp
from advisor.universe.models import Asset, Universe
from tests.test_event_study import _df_for_status, _levels, _observation, _signal


def test_score_sin_rr_usa_evaluable_max_no_la_suma_de_maximos() -> None:
    signal = _signal_with_dimensions(
        score=70.0,
        dims=(
            DimensionObservation("catalizador", 20.0, 20.0, True),
            DimensionObservation("fundamental", 0.0, 20.0, False),
            DimensionObservation("tecnico", 16.0, 20.0, True),
            DimensionObservation("beneficio_riesgo", 10.0, 20.0, True),
            DimensionObservation("contexto", 10.0, 10.0, True),
        ),
    )

    record, reason = build_ablation_record(signal, 0.2)

    assert reason is None
    assert record is not None
    assert record.score_without_rr == pytest.approx(100.0 * 46.0 / 60.0)
    assert record.score_without_rr != pytest.approx(100.0 * 46.0 / 80.0)


def test_denominador_sin_rr_es_60_con_fundamentales_desactivados() -> None:
    signal = _signal_with_dimensions(score=70.0)

    record, reason = build_ablation_record(signal, 0.2)

    assert reason is None
    assert record is not None
    assert record.evaluable_max_without_rr == pytest.approx(60.0)


def test_contribucion_rr_es_la_diferencia_de_notas_y_puede_ser_negativa() -> None:
    positivo, _ = build_ablation_record(_signal_with_dimensions(score=62.5, rr_points=20.0), 0.2)
    negativo, _ = build_ablation_record(_signal_with_dimensions(score=75.0, rr_points=0.0), 0.2)

    assert positivo is not None
    assert negativo is not None
    assert positivo.rr_contribution_points == pytest.approx(positivo.score_full - positivo.score_without_rr)
    assert negativo.rr_contribution_points == pytest.approx(negativo.score_full - negativo.score_without_rr)
    assert positivo.rr_contribution_points > 0
    assert negativo.rr_contribution_points < 0
    assert positivo.rr_contribution_points != pytest.approx(positivo.rr_dimension_points)


def test_rr_bruto_reconstruido_coincide_con_levels_rr_ratio() -> None:
    cases = [
        dict(price=100.0, atr=2.0, low_lookback=90.0, high_lookback=106.0, ema_fast=99.0),
        dict(price=100.0, atr=2.0, low_lookback=98.0, high_lookback=106.0, ema_fast=99.0),
    ]
    for kwargs in cases:
        levels = compute_levels_from_inputs(**kwargs, config=LevelsConfig(), min_rr_ratio=RiskConfig().min_rr_ratio)
        assert levels is not None
        signal = _signal_with_dimensions(score=70.0, levels=levels)

        record, reason = build_ablation_record(signal, 0.2)

        assert reason is None
        assert record is not None
        assert math.isclose(record.rr_gross, levels.rr_ratio, rel_tol=1e-12)


def test_rr_neto_cumple_la_identidad_del_contrato() -> None:
    signal = _signal_with_dimensions(score=70.0, levels=_levels(price=100.0, stop=95.0, target=110.0))

    record, reason = build_ablation_record(signal, 0.20)

    assert reason is None
    assert record is not None
    assert record.risk_pp == pytest.approx(5.0)
    assert record.rr_gross == pytest.approx(2.0)
    assert record.rr_net == pytest.approx(1.96)


def test_ambiguas_no_entran_en_net_r_medio_y_su_numero_se_publica() -> None:
    result = _result(
        [
            _signal_with_dimensions(score=55.0, status=TARGET_FIRST),
            _signal_with_dimensions(score=55.0, status=STOP_FIRST),
            _signal_with_dimensions(score=55.0, status=AMBIGUOUS),
        ]
    )

    out = run_ablation(result, universe=_universe())
    report = format_ablation_report(out)
    band = {item.label: item for item in out.bands_full}["50-60"]

    assert band.band_summary.mean_net_r_multiple == pytest.approx((1.96 - 1.04) / 2)
    assert out.n_without_net_r == 1
    assert "Sin net_R: 1" in report


def test_señal_sin_descomposicion_se_descarta_y_se_declara() -> None:
    out = run_ablation(_result([_signal(score=70.0, status=TARGET_FIRST)]), universe=_universe())

    assert len(out.records) == 0
    assert out.skipped[0][1] == "observación sin descomposición por dimensión"
    assert "observación sin descomposición por dimensión=1" in format_ablation_report(out)


def test_invariante_de_reconstruccion_descarta_en_vez_de_corregir() -> None:
    signal = _signal_with_dimensions(score=70.0)
    bad_obs = replace(signal.observation, score_value=71.0)
    signal = _replace_observation(signal, bad_obs)

    out = run_ablation(_result([signal]), universe=_universe())

    assert len(out.records) == 0
    assert out.skipped[0][1] == "score incoherente con la descomposición por dimensión"


def test_bandas_sin_capacidad_salen_como_no_concluyente() -> None:
    signals = [_with_day(_signal_with_dimensions(score=85.0, status=TARGET_FIRST if i < 40 else STOP_FIRST), i) for i in range(78)]

    report = format_ablation_report(run_ablation(_result(signals), universe=_universe()))

    row = next(line for line in report.splitlines() if line.startswith("80+"))
    assert "NO CONCLUYENTE" in row
    assert "bloques 2 < 12" in row
    assert " 78 " in row


def test_capacidad_se_reevalua_sobre_la_banda_ablacionada() -> None:
    signals = []
    for i in range(120):
        signals.append(_with_day(_signal_with_dimensions(score=75.0, rr_points=20.0), i))
    for i in range(120):
        signals.append(_with_day(_signal_with_dimensions(score=55.0, rr_points=0.0), i))

    out = run_ablation(_result(signals), universe=_universe())
    full = {summary.label: summary.nominal_n for summary in out.capacity_full.bands}
    sin_rr = {summary.label: summary.nominal_n for summary in out.capacity_ablated.bands}

    assert full != sin_rr
    assert sin_rr["50-60"] != full["50-60"]


def test_migracion_cuadra() -> None:
    signals = [
        _signal_with_dimensions(score=45.0, rr_points=0.0),
        _signal_with_dimensions(score=55.0, rr_points=10.0),
        _signal_with_dimensions(score=65.0, rr_points=20.0),
        _signal_with_dimensions(score=75.0, rr_points=0.0),
        _signal_with_dimensions(score=85.0, rr_points=20.0),
    ]

    out = run_ablation(_result(signals), universe=_universe())

    for band in out.bands_full:
        assert sum(count for (left, _), count in out.migration.items() if left == band.label) == band.n
    for band in out.bands_ablated:
        assert sum(count for (_, right), count in out.migration.items() if right == band.label) == band.n
    assert sum(out.migration.values()) == len(out.records)


def test_no_hay_redondeo_antes_del_calculo() -> None:
    low = _signal_with_dimensions(score=64.985, rr_points=10.0)
    high = _signal_with_dimensions(score=65.015, rr_points=10.0)

    out = run_ablation(_result([low, high]), universe=_universe())
    bands = {record.signal_id: record.band_without_rr for record in out.records}
    values = [record.score_without_rr for record in out.records]

    assert values[0] == pytest.approx(69.98)
    assert values[1] == pytest.approx(70.02)
    assert set(bands.values()) == {"60-70", "70-80"}


def test_la_ablacion_no_depende_de_classify() -> None:
    tree = ast.parse(inspect.getsource(ablation))
    imports = [
        name.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for name in node.names
    ]
    imports.extend(
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )

    assert "advisor.analysis.opportunity" not in imports


def _signal_with_dimensions(
    *,
    score: float,
    status: str = TARGET_FIRST,
    rr_points: float = 10.0,
    dims: tuple[DimensionObservation, ...] | None = None,
    levels=None,
):
    if dims is None:
        other_points = score * 80.0 / 100.0 - rr_points
        dims = (
            DimensionObservation("catalizador", other_points / 3, 20.0, True),
            DimensionObservation("fundamental", 0.0, 20.0, False),
            DimensionObservation("tecnico", other_points / 3, 20.0, True),
            DimensionObservation("beneficio_riesgo", rr_points, 20.0, True),
            DimensionObservation("contexto", other_points / 6, 10.0, True),
            DimensionObservation("conviccion", other_points / 6, 10.0, True),
        )
    base = _observation(score)
    obs = replace(base, dimensions=dims)
    if levels is None:
        levels = _levels()
    managed = evaluate_managed_event(obs, _df_for_status(status), 0, levels, max_hold_bars=1, cost_pct=0.2)
    potential = replace(_signal(score=score, status=STOP_FIRST).potential, observation=obs)
    return _replace_observation(replace(_signal(score=score, status=status), managed=managed, potential=potential), obs)


def _replace_observation(signal, obs: SignalObservation):
    return replace(signal, observation=obs, managed=replace(signal.managed, observation=obs), potential=replace(signal.potential, observation=obs))


def _with_day(signal, day: int):
    timestamp = parse_timestamp("2026-01-05T00:00:00Z") + timedelta(days=_business_day_offset(day))
    raw = timestamp.isoformat().replace("+00:00", "Z")
    obs = replace(signal.observation, signal_timestamp=timestamp, signal_timestamp_raw=raw, signal_id=f"TEST|swing|{raw}|{day}")
    return _replace_observation(signal, obs)


def _result(signals) -> EventStudyResult:
    unique_signals = []
    for index, signal in enumerate(signals):
        raw = signal.observation.signal_timestamp_raw
        obs = replace(signal.observation, signal_id=f"{signal.observation.asset}|{signal.observation.horizonte}|{raw}|{index}")
        unique_signals.append(_replace_observation(signal, obs))
    session_dates = tuple(sorted({signal.observation.signal_timestamp.date() for signal in unique_signals}))
    return EventStudyResult(
        data_vintage_id="vintage",
        horizonte="swing",
        cost_pct=0.2,
        warmup_bars=120,
        max_hold_bars=40,
        signals=unique_signals,
        evaluated_assets=["TEST"],
        asset_bar_counts={"TEST": 1255},
        session_dates_by_asset={"TEST": session_dates},
    )


def _business_day_offset(index: int) -> int:
    day = date(2026, 1, 5)
    offset = 0
    seen = 0
    while seen < index:
        offset += 1
        if (day + timedelta(days=offset)).weekday() < 5:
            seen += 1
    return offset


def _universe() -> Universe:
    return Universe(
        groups={
            "test": [
                Asset(
                    primary_symbol="TEST",
                    primary_market="XETRA",
                    primary_currency="EUR",
                    name="TEST",
                    asset_class="stock",
                    region="EUROPA",
                    economic_currency="EUR",
                    timezone="Europe/Berlin",
                    isin=None,
                    requires_isin=True,
                )
            ]
        }
    )
