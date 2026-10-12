"""Integración INV-06 de Score v2 sobre la cosecha real."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from numpy.testing import assert_allclose

from advisor.analysis.scoring import compute_score
from advisor.analysis.snapshot import snapshot_from_series
from advisor.backtest import engine
from advisor.config import load_config, scoring_for_requested_model
from advisor.research import event_study
from advisor.research.observations import SignalObservation
from advisor.research.vintage import load_vintage
from advisor.universe.loader import load_universe
from advisor.universe.models import Asset, Universe

VINTAGE_ID = "071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841"
TARGET_ASSETS = ("AAPL", "SAP.DE", "SXR8.DE")
CONTEXT_ASSETS = ("^GSPC", "^STOXX", "^STOXX50E", "^VIX", "^N225", "^HSI", "^KS11", "^TWII", "510300.SS")


def _require_real_vintage() -> None:
    if not (Path("data/vintages") / VINTAGE_ID / "AAPL.csv").is_file():
        pytest.skip("data/vintages no está disponible")


def _small_universe() -> Universe:
    config = load_config("config.yaml")
    universe = load_universe(config.universe_path)
    target_assets = [_asset(universe, symbol) for symbol in TARGET_ASSETS]
    context_assets = [_asset(universe, symbol) for symbol in CONTEXT_ASSETS]
    return Universe(groups={"test": target_assets, "context": context_assets})


def _asset(universe: Universe, symbol: str) -> Asset:
    asset = universe.get(symbol)
    if asset is None:
        raise AssertionError(f"{symbol} no está en el universo")
    return asset


def _small_vintage():
    keep = set(TARGET_ASSETS) | set(CONTEXT_ASSETS)
    vintage = load_vintage(VINTAGE_ID)
    return replace(vintage, by_symbol={symbol: views for symbol, views in vintage.by_symbol.items() if symbol in keep})


@pytest.fixture
def score_v2_records(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    _require_real_vintage()
    config = load_config("config.yaml")
    universe = _small_universe()
    vintage = _small_vintage()
    records: list[dict[str, Any]] = []
    original_build = event_study._build_event_signal

    def capture_signal(*args: Any, **kwargs: Any):
        built = original_build(*args, **kwargs)
        if built is None:
            return None

        (
            asset,
            snapshot_series,
            signal_idx,
            received_config,
            horizonte,
            min_bars,
            vix_at,
            trend_price_at,
            trend_sma_at,
            market_context_at,
            score_model_version,
        ) = args
        levels, event_observation = built
        if asset.symbol not in TARGET_ASSETS:
            return built
        if score_model_version != "2.0":
            raise AssertionError(f"score_model_version inesperada: {score_model_version}")
        if market_context_at is None or market_context_at[signal_idx] is None:
            raise AssertionError(f"{asset.symbol} {signal_idx}: falta contexto point-in-time")

        snapshot = snapshot_from_series(asset.symbol, snapshot_series, signal_idx)
        context = market_context_at[signal_idx]
        scoring_v2 = scoring_for_requested_model(received_config.scoring, "2.0")
        analyzer_score = compute_score(snapshot, context, scoring_v2, model_version="2.0")

        engine_signal = engine._signal(
            asset,
            snapshot_series,
            signal_idx,
            received_config,
            horizonte,
            min_bars,
            vix_at,
            trend_price_at,
            trend_sma_at,
            market_context_at,
            score_model_version,
        )
        if engine_signal is None:
            raise AssertionError(f"{asset.symbol} {signal_idx}: engine no reconstruye la señal")

        scoring_v1 = scoring_for_requested_model(received_config.scoring, "1.0")
        v1_score = compute_score(
            snapshot,
            context,
            scoring_v1,
            model_version="1.0",
            levels=levels,
            min_bars=min_bars,
        )
        records.append(
            {
                "asset": asset.symbol,
                "signal_idx": signal_idx,
                "event": event_observation,
                "engine": engine_signal["observation"],
                "analyzer_value": analyzer_score.value,
                "v1_points": v1_score.points,
                "v1_evaluable_max": v1_score.evaluable_max,
                "v1_dimensions": {
                    dimension.name: dimension
                    for dimension in v1_score.dimensions
                    if dimension.name in {"beneficio_riesgo", "conviccion"}
                },
            }
        )
        return built

    monkeypatch.setattr(event_study, "_build_event_signal", capture_signal)
    monkeypatch.setattr(event_study, "evaluate_managed_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(event_study, "evaluate_potential_event", lambda *args, **kwargs: None)

    result = event_study.run_event_study_on_vintage(
        config,
        universe,
        vintage,
        horizonte="swing",
        score_model_version="2.0",
    )

    assert set(result.evaluated_assets) == set(TARGET_ASSETS)
    assert set(result.skipped) == set()
    assert records
    assert {record["asset"] for record in records} == set(TARGET_ASSETS)
    return records


def test_inv06_score_v2_coincide_en_analyzer_engine_y_event_study(
    score_v2_records: list[dict[str, Any]],
) -> None:
    for record in score_v2_records:
        event_observation: SignalObservation = record["event"]
        engine_observation: SignalObservation = record["engine"]
        assert event_observation.signal_id == engine_observation.signal_id
        assert event_observation.score_model_version == "2.0"
        assert engine_observation.score_model_version == "2.0"
        assert_allclose(event_observation.score_value, record["analyzer_value"], rtol=0, atol=1e-12)
        assert_allclose(event_observation.score_value, engine_observation.score_value, rtol=0, atol=1e-12)


def test_score_v2_equivale_a_reconstruccion_desde_observaciones_v1(
    score_v2_records: list[dict[str, Any]],
) -> None:
    for record in score_v2_records:
        removed_points = 0.0
        removed_max = 0.0
        for dimension in record["v1_dimensions"].values():
            if dimension.available:
                removed_points += dimension.points
                removed_max += dimension.weight

        reconstructed_max = record["v1_evaluable_max"] - removed_max
        assert reconstructed_max > 0
        reconstructed = 100.0 * (record["v1_points"] - removed_points) / reconstructed_max
        event_observation: SignalObservation = record["event"]
        assert_allclose(event_observation.score_value, reconstructed, rtol=0, atol=1e-12)
