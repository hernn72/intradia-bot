"""Regresiones de timestamps: texto congelado y datetime de cálculo."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from advisor.config import load_config
from advisor.research.event_study import run_event_study
from advisor.research.observations import stable_signal_id
from advisor.research.timestamps import parse_timestamp
from advisor.research.vintage import load_vintage
from advisor.universe.loader import load_universe

VINTAGE_ID = "071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841"


def test_iso_equivalentes_no_sustituyen_el_texto_canonico() -> None:
    raw_z = "2026-09-10T00:00:00Z"
    raw_offset = "2026-09-10T00:00:00+00:00"

    assert parse_timestamp(raw_z) == parse_timestamp(raw_offset)
    assert stable_signal_id("AAPL", "swing", raw_z) != stable_signal_id("AAPL", "swing", raw_offset)
    assert stable_signal_id("AAPL", "swing", raw_z).endswith(raw_z)


def test_cosecha_real_mantiene_hashes_y_bytes_tras_parsear_y_serializar_salidas() -> None:
    vintage_dir = Path("data/vintages") / VINTAGE_ID
    if not vintage_dir.is_dir():
        pytest.skip(f"cosecha real no disponible: {vintage_dir}")

    before = {path.relative_to(vintage_dir): path.read_bytes() for path in vintage_dir.iterdir() if path.is_file()}
    vintage = load_vintage(VINTAGE_ID)
    assert len(vintage.manifest["assets"]) == 126

    config = load_config("config.yaml")
    universe = load_universe(config.universe_path)
    result = run_event_study(config, universe, VINTAGE_ID, horizonte="swing")
    assert result.signals

    sample = result.signals[0]
    assert isinstance(sample.observation.signal_timestamp_raw, str)
    assert sample.observation.signal_timestamp.tzinfo is not None
    assert isinstance(sample.managed.exit_timestamp_raw, str)
    assert sample.managed.exit_timestamp.tzinfo is not None
    json.dumps(
        {
            "signal_timestamp_raw": sample.observation.signal_timestamp_raw,
            "signal_timestamp": sample.observation.signal_timestamp.isoformat(),
            "exit_timestamp_raw": sample.managed.exit_timestamp_raw,
            "exit_timestamp": sample.managed.exit_timestamp.isoformat(),
        },
        ensure_ascii=False,
    )

    after = {path.relative_to(vintage_dir): path.read_bytes() for path in vintage_dir.iterdir() if path.is_file()}
    assert after == before
