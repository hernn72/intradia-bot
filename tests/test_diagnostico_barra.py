"""Diagnostico de barras ausentes."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd

from advisor.data.bar_diagnostics import (
    CLASE_DESCARGA_FALLIDA,
    CLASE_FUERA_RANGO_CONSULTADO,
    CLASE_MERCADO_CERRADO,
    CLASE_PIPELINE_LA_PIERDE,
    CLASE_PLAZA_SIN_CALENDARIO,
    CLASE_PROVEEDOR_NO_ENTREGA,
    CLASE_SIMBOLO_FUERA_UNIVERSO,
    diagnose_all_saved_gaps,
    diagnose_bar,
    format_many_bar_diagnoses,
)
from advisor.universe.loader import load_universe
from advisor.universe.models import Asset, Universe
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


class _GapDB:
    def __init__(self, gaps: list[tuple[str, date]]) -> None:
        self.gaps = gaps

    def get_latest_freshness_absences(self) -> list[tuple[str, date]]:
        return self.gaps


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


def test_diagnostico_distingue_descarga_fallida_de_proveedor_no_entrega(config) -> None:
    universe = load_universe("universe.yaml")
    sap = universe.get("SAP.DE")
    assert sap is not None
    provider = FakeProvider(histories={}, raw_histories={})

    diagnosis = diagnose_bar(
        sap,
        date(2026, 9, 8),
        provider=provider,
        config=config,
        reference=datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc),
        periods=("1mo", "1y"),
    )
    formatted = format_many_bar_diagnoses([diagnosis])

    assert diagnosis.classification == CLASE_DESCARGA_FALLIDA
    assert "Error" in formatted
    assert "sin datos crudos para 'SAP.DE'" in formatted


def test_diagnostico_pide_crudo_sin_dropna_y_atribuye_fila_vacia_a_pipeline(config) -> None:
    universe = load_universe("universe.yaml")
    exsa = universe.get("EXSA.DE")
    assert exsa is not None
    raw = _history(["2026-09-14T22:00:00Z"])
    raw.loc[:, ["Open", "High", "Low", "Close"]] = float("nan")
    provider = FakeProvider(histories={"EXSA.DE": _empty_history()}, raw_histories={"EXSA.DE": raw})

    diagnosis = diagnose_bar(
        exsa,
        date(2026, 9, 15),
        provider=provider,
        config=config,
        reference=datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc),
        periods=("1y",),
    )

    assert diagnosis.periods[0].present_raw is True
    assert diagnosis.periods[0].present_after_dropna is False
    assert diagnosis.classification == CLASE_PIPELINE_LA_PIERDE


def test_diagnostico_fecha_futura_es_fuera_del_rango_consultado(config) -> None:
    universe = load_universe("universe.yaml")
    aapl = universe.get("AAPL")
    assert aapl is not None
    raw = _history(["2026-09-15T13:30:00Z"])
    provider = FakeProvider(histories={"AAPL": raw}, raw_histories={"AAPL": raw})

    diagnosis = diagnose_bar(
        aapl,
        date(2026, 10, 1),
        provider=provider,
        config=config,
        reference=datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc),
        periods=("1y",),
    )

    assert diagnosis.classification == CLASE_FUERA_RANGO_CONSULTADO


def test_diagnostico_fecha_anterior_al_periodo_consultado_es_fuera_del_rango(config) -> None:
    universe = load_universe("universe.yaml")
    aapl = universe.get("AAPL")
    assert aapl is not None
    raw = _history(["2026-09-15T13:30:00Z"])
    provider = FakeProvider(histories={"AAPL": raw}, raw_histories={"AAPL": raw})

    diagnosis = diagnose_bar(
        aapl,
        date(2015, 1, 5),
        provider=provider,
        config=config,
        reference=datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc),
        periods=("5y",),
    )

    assert diagnosis.classification == CLASE_FUERA_RANGO_CONSULTADO


def test_diagnostico_plaza_sin_calendario_degrada_el_simbolo(config) -> None:
    universe = load_universe("universe.yaml")
    vix = universe.get("^VIX")
    assert vix is not None
    provider = FakeProvider()

    diagnosis = diagnose_bar(
        vix,
        date(2026, 9, 7),
        provider=provider,
        config=config,
        reference=datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc),
    )

    assert diagnosis.symbol == "^VIX"
    assert diagnosis.classification == CLASE_PLAZA_SIN_CALENDARIO
    assert "CBOE" in (diagnosis.calendar_override or "")


def test_diagnose_all_saved_gaps_memoiza_descargas_por_simbolo_y_periodo(config) -> None:
    universe = load_universe("universe.yaml")
    raw = _history(["2026-09-06T22:00:00Z", "2026-09-07T22:00:00Z"])
    provider = FakeProvider(histories={"SAP.DE": raw}, raw_histories={"SAP.DE": raw})
    db = _GapDB([("SAP.DE", date(2026, 9, 7)), ("SAP.DE", date(2026, 9, 8))])

    diagnoses = diagnose_all_saved_gaps(
        db=db,
        universe=universe,
        provider=provider,
        config=config,
        reference=datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc),
    )

    assert len(diagnoses) == 2
    assert len(provider.calls) == 6


def test_diagnose_all_saved_gaps_emite_fila_para_simbolo_fuera_del_universo(config) -> None:
    sap = Asset(
        symbol="SAP.DE",
        name="SAP",
        asset_class="stock",
        region="EUROPA",
        market="XETRA",
        currency="EUR",
        economic_currency="EUR",
        timezone="Europe/Berlin",
        primary_symbol="SAP.DE",
        primary_market="XETRA",
        primary_currency="EUR",
        isin="DE0007164600",
        isin_verified_at="2026-08-27",
        isin_source="universe inicial 2026-08-27",
        requires_isin=True,
    )
    universe = Universe(groups={"main": [sap]})
    provider = FakeProvider()

    diagnoses = diagnose_all_saved_gaps(
        db=_GapDB([("RETIRADO.DE", date(2026, 9, 8))]),
        universe=universe,
        provider=provider,
        config=config,
        reference=datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc),
    )

    assert diagnoses[0].symbol == "RETIRADO.DE"
    assert diagnoses[0].classification == CLASE_SIMBOLO_FUERA_UNIVERSO


def test_la_tabla_masiva_declara_de_que_pasada_es_la_poblacion() -> None:
    """La población puede ser de hace semanas y medida con reglas anteriores."""

    from advisor.data.bar_diagnostics import format_many_bar_diagnoses

    salida = format_many_bar_diagnoses((), measured_at="2026-09-02T17:18:41+00:00")
    assert "Poblacion: ausencias de la pasada de frescura del 2026-09-02T17:18:41+00:00" in salida

    sin_pasada = format_many_bar_diagnoses(())
    assert "Poblacion: sin pasada de frescura guardada" in sin_pasada
