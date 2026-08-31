"""Aceptación P2.5 contra la cosecha real, si está disponible."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from advisor.config import load_config
from advisor.research.capacity import _temporal_block_lookup
from advisor.research.event_study import TARGET_FIRST, EventStudyResult
from advisor.research.timestamps import parse_timestamp, timestamp_raw
from advisor.research.vintage import load_vintage
from advisor.universe.loader import load_universe
from tests.test_event_study import _signal

VINTAGE_ID = "071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841"


def test_bloques_de_sesion_reales_no_desplazan_europa_ni_incluyen_fines_de_semana() -> None:
    vintage_dir = Path("data/vintages") / VINTAGE_ID
    if not vintage_dir.is_dir():
        pytest.skip("data/vintages no está disponible")

    config = load_config("config.yaml")
    universe = load_universe(config.universe_path)
    vintage = load_vintage(VINTAGE_ID)
    sap = universe.get("SAP.DE")
    aapl = universe.get("AAPL")
    assert sap is not None
    assert aapl is not None

    sap_raw = timestamp_raw(vintage.by_symbol["SAP.DE"].signal_prices.index[0])
    aapl_raw = timestamp_raw(vintage.by_symbol["AAPL"].signal_prices.index[0])
    signals = [_signal_at("SAP.DE", sap_raw), _signal_at("AAPL", aapl_raw)]
    session_dates_by_asset = {
        symbol: tuple(
            parse_timestamp(timestamp_raw(ts)).astimezone(ZoneInfo(universe.get(symbol).timezone)).date()
            for ts in vintage.by_symbol[symbol].signal_prices.index
        )
        for symbol in ("SAP.DE", "AAPL")
    }
    result = EventStudyResult(
        data_vintage_id=VINTAGE_ID,
        horizonte="swing",
        cost_pct=0.2,
        warmup_bars=120,
        max_hold_bars=40,
        signals=signals,
        evaluated_assets=["SAP.DE", "AAPL"],
        asset_bar_counts={symbol: len(vintage.by_symbol[symbol].signal_prices) for symbol in ("SAP.DE", "AAPL")},
        session_dates_by_asset=session_dates_by_asset,
    )

    blocks = _temporal_block_lookup(result, block_length=60, universe=universe)

    assert blocks.session_date(signals[0]) == blocks.session_date(signals[1])
    assert blocks.block_for(signals[0]) == blocks.block_for(signals[1])
    assert all(day.weekday() < 5 for day in blocks.session_spine)


def _signal_at(symbol: str, raw: str):
    signal = _signal(score=55.0, status=TARGET_FIRST)
    timestamp = parse_timestamp(raw)
    obs = replace(
        signal.observation,
        asset=symbol,
        signal_id=f"{symbol}|swing|{raw}",
        signal_timestamp_raw=raw,
        signal_timestamp=timestamp,
    )
    return replace(signal, observation=obs, managed=replace(signal.managed, observation=obs))
