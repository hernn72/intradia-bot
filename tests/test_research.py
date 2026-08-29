"""Tests de instrumentación de señal para investigación."""

from __future__ import annotations

from dataclasses import fields, replace

import numpy as np
import pandas as pd
import pytest
from numpy.testing import assert_allclose

from advisor.analysis.snapshot import TechnicalSnapshot, build_snapshot, build_snapshot_series, snapshot_from_series
from advisor.backtest.engine import _signal, _signal_prefix
from advisor.backtest.runner import _align


def _serie_larga(n: int = 420) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")
    x = np.arange(n, dtype=float)
    close = 100 + 0.18 * x + 2.5 * np.sin(x / 7)
    open_ = close + 0.4 * np.sin(x / 3)
    high = np.maximum(open_, close) + 1.2 + 0.3 * np.cos(x / 5)
    low = np.minimum(open_, close) - 1.1 - 0.2 * np.sin(x / 4)
    volume = 1_000_000 + 100_000 * np.sin(x / 6)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=index,
    )


def _benchmark_alineado(df: pd.DataFrame) -> pd.Series:
    x = np.arange(len(df), dtype=float)
    return pd.Series(3000 + 0.9 * x + 12 * np.sin(x / 11), index=df.index)


def _benchmark_con_huecos(df: pd.DataFrame) -> pd.Series:
    benchmark = _benchmark_calendario_propio(df).reindex(df.index)
    mask = np.arange(len(benchmark)) % 6 == 0
    benchmark.iloc[mask] = np.nan
    return benchmark


def _benchmark_calendario_propio(df: pd.DataFrame) -> pd.Series:
    index = pd.date_range(df.index[0] - pd.Timedelta(days=15), periods=len(df) + 30, freq="2D", tz="UTC")
    x = np.arange(len(index), dtype=float)
    return pd.Series(3000 + 1.4 * x + 10 * np.sin(x / 9), index=index)


def _assert_optional_float_close(actual, expected, field_name: str) -> None:
    if expected is None:
        assert actual is None, field_name
        return
    assert actual is not None, field_name
    assert_allclose(actual, expected, rtol=1e-12, atol=1e-12, err_msg=field_name)


def _assert_snapshot_equivalent(asset, df, config, j: int, benchmark_close: pd.Series | None) -> None:
    series = build_snapshot_series(df, config.indicators, config.levels, "1d", benchmark_close)
    vectorizado = snapshot_from_series(asset.symbol, series, j)
    bench_prefix = benchmark_close.iloc[: j + 1].dropna() if benchmark_close is not None else None
    prefijo = build_snapshot(asset.symbol, df.iloc[: j + 1], config.indicators, config.levels, "1d", bench_prefix)

    for field in fields(TechnicalSnapshot):
        if field.name in {"symbol", "timestamp", "interval", "bars"}:
            continue
        _assert_optional_float_close(getattr(vectorizado, field.name), getattr(prefijo, field.name), field.name)


def _assert_signal_equivalent(asset, df, config, j: int, benchmark_close: pd.Series | None) -> None:
    series = build_snapshot_series(df, config.indicators, config.levels, "1d", benchmark_close)
    vectorizada = _signal(asset, series, j, config, "swing", 120, None, None, None)
    prefijo = _signal_prefix(asset, df, j, config, "swing", "1d", 120, benchmark_close, None, None, None)

    assert vectorizada is not None
    assert prefijo is not None
    assert vectorizada["radar"] == prefijo["radar"]
    assert vectorizada["accion"] == prefijo["accion"]
    assert_allclose(
        [vectorizada["score"], vectorizada["stop"], vectorizada["target"], vectorizada["entry_max"]],
        [prefijo["score"], prefijo["stop"], prefijo["target"], prefijo["entry_max"]],
        rtol=1e-12,
        atol=1e-12,
    )

    obs_vector = vectorizada["observation"]
    obs_prefix = prefijo["observation"]
    assert obs_vector.signal_id == obs_prefix.signal_id
    assert obs_vector.asset == obs_prefix.asset
    assert obs_vector.horizonte == obs_prefix.horizonte
    assert obs_vector.signal_idx == obs_prefix.signal_idx
    assert obs_vector.signal_timestamp == obs_prefix.signal_timestamp
    assert [d.name for d in obs_vector.dimensions] == [d.name for d in obs_prefix.dimensions]
    assert [d.available for d in obs_vector.dimensions] == [d.available for d in obs_prefix.dimensions]
    assert_allclose(
        [obs_vector.score_value, obs_vector.evaluable_max, obs_vector.price, obs_vector.atr, obs_vector.low_lookback,
         obs_vector.high_lookback, obs_vector.ema_fast],
        [obs_prefix.score_value, obs_prefix.evaluable_max, obs_prefix.price, obs_prefix.atr, obs_prefix.low_lookback,
         obs_prefix.high_lookback, obs_prefix.ema_fast],
        rtol=1e-12,
        atol=1e-12,
    )
    assert_allclose(
        [d.points for d in obs_vector.dimensions],
        [d.points for d in obs_prefix.dimensions],
        rtol=1e-12,
        atol=1e-12,
    )
    assert_allclose(
        [d.max for d in obs_vector.dimensions],
        [d.max for d in obs_prefix.dimensions],
        rtol=0,
        atol=0,
    )


@pytest.mark.parametrize(
    "benchmark_case",
    ["sin_benchmark", "alineado_sin_huecos", "nan_interiores", "alineado_por_runner"],
)
def test_senal_vectorizada_equivale_al_prefijo_causal(asset_eur, config, benchmark_case: str) -> None:
    """calcular el futuro no altera el valor en t.

    Si alguien introduce un ``shift(-1)``, un rolling centrado o cualquier
    otra forma de look-ahead, la comparación contra el prefijo debe romperse.
    """

    df = _serie_larga()
    benchmark_close = None
    if benchmark_case == "alineado_sin_huecos":
        benchmark_close = _benchmark_alineado(df)
    elif benchmark_case == "nan_interiores":
        benchmark_close = _benchmark_con_huecos(df)
    elif benchmark_case == "alineado_por_runner":
        benchmark_close = _align(_benchmark_calendario_propio(df), df.index)

    for j in range(120, 391):
        _assert_snapshot_equivalent(asset_eur, df, config, j, benchmark_close)
        _assert_signal_equivalent(asset_eur, df, config, j, benchmark_close)


def test_la_guarda_detecta_lookahead_deliberado(asset_eur, config) -> None:
    def _build_snapshot_series_con_lookahead(df):
        base = build_snapshot_series(df, config.indicators, config.levels, "1d")
        return replace(base, ema_fast=base.ema_fast.shift(-1))

    df = _serie_larga()
    j = 137
    serie_con_futuro = _build_snapshot_series_con_lookahead(df)
    vectorizada = _signal(asset_eur, serie_con_futuro, j, config, "swing", 120, None, None, None)
    prefijo = _signal_prefix(asset_eur, df, j, config, "swing", "1d", 120, None, None, None, None)

    assert vectorizada is not None
    assert prefijo is not None
    with pytest.raises(AssertionError):
        assert_allclose(
            [vectorizada["observation"].ema_fast],
            [prefijo["observation"].ema_fast],
            rtol=1e-12,
            atol=1e-12,
        )
