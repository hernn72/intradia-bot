"""Diagnostico de barras ausentes."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd

from advisor.data.bar_diagnostics import (
    CLASE_MERCADO_CERRADO,
    CLASE_PIPELINE_LA_PIERDE,
    CLASE_PROVEEDOR_NO_ENTREGA,
    diagnose_bar,
)
from advisor.universe.loader import load_universe
from tests.conftest import FakeProvider


def _history(timestamps: list[str]) -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.Timestamp(value) for value in timestamps])
    return pd.DataFrame(
        {
            "Open": [100.0 + i for i in range(len(index))],
            "High": [101.0 + i for i in range(len(index))],
            "Low": [99.0 + i for i in range(len(index))],
            "Close": [100.0 + i for i in range(len(index))],
            "Volume": [1_000_000.0] * len(index),
        },
        index=index,
    )


def _empty_history() -> pd.DataFrame:
    return _history([])


def test_diagnostico_deriva_session_date_en_zona_de_plaza(config) -> None:
    universe = load_universe("universe.yaml")
    sap = universe.get("SAP.DE")
    aapl = universe.get("AAPL")
    assert sap is not None
    assert aapl is not None
    raw = _history(["2026-09-06T22:00:00Z"])
    provider = FakeProvider(histories={"SAP.DE": raw, "AAPL": raw}, raw_histories={"SAP.DE": raw, "AAPL": raw})

    xetra = diagnose_bar(
        sap,
        date(2026, 9, 7),
        provider=provider,
        config=config,
        reference=datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc),
        periods=("1y",),
    )
    nyse = diagnose_bar(
        aapl,
        date(2026, 9, 6),
        provider=provider,
        config=config,
        reference=datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc),
        periods=("1y",),
    )

    assert xetra.periods[0].session_date == date(2026, 9, 7)
    assert nyse.periods[0].session_date == date(2026, 9, 6)


def test_diagnostico_declara_calendario_cerrado(config) -> None:
    universe = load_universe("universe.yaml")
    aapl = universe.get("AAPL")
    assert aapl is not None
    provider = FakeProvider(histories={"AAPL": _empty_history()}, raw_histories={"AAPL": _empty_history()})

    diagnosis = diagnose_bar(
        aapl,
        date(2026, 9, 7),
        provider=provider,
        config=config,
        reference=datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc),
        periods=("1y",),
    )

    assert diagnosis.calendar_session is False
    assert diagnosis.classification == CLASE_MERCADO_CERRADO


def test_diagnostico_clasifica_proveedor_no_entrega(config) -> None:
    universe = load_universe("universe.yaml")
    sap = universe.get("SAP.DE")
    assert sap is not None
    provider = FakeProvider(histories={"SAP.DE": _empty_history()}, raw_histories={"SAP.DE": _empty_history()})

    diagnosis = diagnose_bar(
        sap,
        date(2026, 9, 7),
        provider=provider,
        config=config,
        reference=datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc),
        periods=("1y",),
    )

    assert diagnosis.calendar_session is True
    assert diagnosis.classification == CLASE_PROVEEDOR_NO_ENTREGA


def test_diagnostico_detecta_perdida_en_pipeline(config) -> None:
    universe = load_universe("universe.yaml")
    sap = universe.get("SAP.DE")
    assert sap is not None
    raw = _history(["2026-09-06T22:00:00Z"])
    provider = FakeProvider(histories={"SAP.DE": _empty_history()}, raw_histories={"SAP.DE": raw})

    diagnosis = diagnose_bar(
        sap,
        date(2026, 9, 7),
        provider=provider,
        config=config,
        reference=datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc),
        periods=("1y",),
    )

    assert diagnosis.periods[0].present_raw is True
    assert diagnosis.periods[0].present_after_trim is False
    assert diagnosis.classification == CLASE_PIPELINE_LA_PIERDE
