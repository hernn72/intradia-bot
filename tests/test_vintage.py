"""Tests de cosechas congeladas para investigación P2.0."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from advisor.config import LevelsConfig
from advisor.research.event_study import EventStudyResult, replay_managed_population
from advisor.research.vintage import (
    _structural_rows,
    build_views,
    freeze_vintage,
    hash_series,
    load_price_rows,
    load_vintage,
    load_vintage_structure,
    read_raw_csv,
)


class RawProvider:
    """Proveedor doble que emula la ruta bruta sin tocar la red."""

    def __init__(self, histories: dict[str, pd.DataFrame]) -> None:
        self.histories = histories
        self.calls: list[tuple[str, str, str]] = []

    def get_raw_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        self.calls.append((symbol, period, interval))
        if symbol not in self.histories:
            raise ValueError(f"sin datos para '{symbol}'")
        return self.histories[symbol].copy()


def _raw_history() -> pd.DataFrame:
    index = pd.date_range("2024-06-07", periods=4, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "Open": [120.0, 121.0, 122.0, 123.0],
            "High": [121.0, 122.0, 123.0, 124.0],
            "Low": [119.0, 120.0, 121.0, 122.0],
            "Close": [120.5, 121.5, 122.5, 123.5],
            "Adj Close": [120.1, 121.1, 122.1, 123.1],
            "Volume": [1_000_000, 1_100_000, 1_200_000, 1_300_000],
            "Dividends": [0.0, 0.0, 0.25, 0.0],
            "Stock Splits": [0.0, 10.0, 0.0, 0.0],
        },
        index=index,
    )


def _raw_history_mantisa_completa() -> pd.DataFrame:
    index = pd.date_range("2026-07-01", periods=3, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "Open": [190.00999450683594, 121.76999664306641, 3.1400000000000001],
            "High": [191.55999755859375, 122.87999725341797, 3.141592653589793],
            "Low": [188.83000183105469, 120.91000366210938, 2.718281828459045],
            "Close": [190.00999450683594, 121.76999664306641, 3.1400000000000001],
            "Adj Close": [189.8874969482422, 121.4566650390625, 3.130000114440918],
            "Volume": [2147483647.0, 123456789.12345679, 9007199254740991.0],
            "Dividends": [0.0, 0.23999999463558197, 0.10000000149011612],
            "Stock Splits": [0.0, 4.000000000000001, 1.5000000000000002],
        },
        index=index,
    )


def test_series_hash_es_determinista_y_detecta_cambios_de_precio() -> None:
    first = _raw_history()
    second = _raw_history()

    assert hash_series(first) == hash_series(second)

    changed = _raw_history()
    changed.iloc[1, changed.columns.get_loc("Close")] += 0.01

    assert hash_series(changed) != hash_series(first)


def test_ciclo_csv_preserva_mantisa_completa_y_hashes(tmp_path) -> None:
    raw = _raw_history_mantisa_completa()
    provider = RawProvider({"NVDA": raw})

    result = freeze_vintage(
        ["NVDA"],
        provider,
        period="1mo",
        interval="1d",
        root_dir=tmp_path,
        downloaded_at=datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc),
    )
    loaded = load_vintage(result.data_vintage_id, root_dir=tmp_path)

    recovered = loaded.by_symbol["NVDA"].raw
    expected = raw.copy()
    expected.index = pd.Index([ts.isoformat().replace("+00:00", "Z") for ts in raw.index], name="timestamp")

    assert loaded.manifest["assets"][0]["series_hash"] == hash_series(recovered)
    assert_frame_equal(recovered, expected, check_exact=True, check_freq=False)


def test_vistas_derivadas_respetan_split_y_neutralizan_dividendo_solo_para_gap() -> None:
    raw = _raw_history()
    views = build_views(raw)

    expected_prices = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    expected_prices.index = pd.Index([ts.isoformat().replace("+00:00", "Z") for ts in raw.index], name="timestamp")
    assert_frame_equal(views.execution_prices, expected_prices, check_freq=False)
    assert_frame_equal(views.signal_prices, expected_prices, check_freq=False)

    # El split queda como acción corporativa congelada, pero no se reescala de nuevo el OHLC.
    assert views.raw.loc["2024-06-08T00:00:00Z", "Stock Splits"] == 10.0
    assert views.execution_prices.loc["2024-06-08T00:00:00Z", "Close"] == 121.5

    assert views.gap_for_catalyst.loc["2024-06-09T00:00:00Z", "Reference Close"] == pytest.approx(121.5 - 0.25)
    assert pd.isna(views.gap_for_catalyst.iloc[0]["Reference Close"])


def test_campaign_no_aborta_por_un_simbolo_fallido(tmp_path) -> None:
    provider = RawProvider({"AAPL": _raw_history()})

    result = freeze_vintage(
        ["AAPL", "MSFT"],
        provider,
        period="1y",
        interval="1d",
        root_dir=tmp_path,
        downloaded_at=datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc),
    )

    assert result.succeeded == ["AAPL"]
    assert set(result.failed) == {"MSFT"}
    assert result.manifest_path.is_file()
    loaded = load_vintage(result.data_vintage_id, root_dir=tmp_path)
    assert set(loaded.by_symbol) == {"AAPL"}
    assert loaded.manifest["failed"][0]["symbol"] == "MSFT"


def test_cosecha_congelada_registra_el_universo_y_el_aborto_salta(tmp_path) -> None:
    """La guarda de INV-08 ampliada estaba muerta: nadie escribía el campo.

    `replay_managed_population` comparaba `manifest["universe_vintage_id"]`
    contra el del resultado, pero `freeze_vintage` nunca lo incluía en el
    manifiesto, así que el `.get()` devolvía `None` y el aborto no saltaba
    jamás. Este test congela de verdad, recarga y comprueba las dos cosas.
    """

    provider = RawProvider({"NVDA": _raw_history_mantisa_completa()})

    result = freeze_vintage(
        ["NVDA"],
        provider,
        period="1mo",
        interval="1d",
        root_dir=tmp_path,
        downloaded_at=datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc),
        universe_vintage="universo-de-la-cosecha",
    )
    loaded = load_vintage(result.data_vintage_id, root_dir=tmp_path)

    assert loaded.manifest["universe_vintage_id"] == "universo-de-la-cosecha"

    estudio = EventStudyResult(
        data_vintage_id=result.data_vintage_id,
        universe_vintage_id="otro-universo",
        horizonte="swing",
        cost_pct=0.2,
        warmup_bars=120,
        max_hold_bars=40,
    )
    with pytest.raises(ValueError, match="universo distinto"):
        replay_managed_population(estudio, loaded, LevelsConfig(), min_rr_ratio=1.5)


def test_load_vintage_rechaza_series_editadas_a_mano(tmp_path) -> None:
    provider = RawProvider({"AAPL": _raw_history()})
    result = freeze_vintage(
        ["AAPL"],
        provider,
        period="1y",
        interval="1d",
        root_dir=tmp_path,
        downloaded_at=datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc),
    )
    csv_path = result.manifest_path.parent / "AAPL.csv"
    edited = csv_path.read_text(encoding="utf-8").replace("121.5", "121.6", 1)
    csv_path.write_text(edited, encoding="utf-8")

    with pytest.raises(ValueError, match="Hash de serie inválido"):
        load_vintage(result.data_vintage_id, root_dir=tmp_path)


def _frozen(tmp_path, histories: dict[str, pd.DataFrame]):
    return freeze_vintage(
        list(histories),
        RawProvider(histories),
        period="1y",
        interval="1d",
        root_dir=tmp_path,
        downloaded_at=datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc),
    )


def test_estructura_reproduce_indice_y_acciones_sin_precios(tmp_path) -> None:
    con_hueco = _raw_history()
    con_hueco.loc[con_hueco.index[1], "Close"] = float("nan")
    result = _frozen(tmp_path, {"AAPL": _raw_history_mantisa_completa(), "MSFT": con_hueco})

    full = load_vintage(result.data_vintage_id, root_dir=tmp_path)
    structure = load_vintage_structure(result.data_vintage_id, root_dir=tmp_path)

    for symbol in ("AAPL", "MSFT"):
        frame = structure.by_symbol[symbol]
        assert list(frame.columns) == ["Dividends", "Stock Splits"]
        assert frame.index.equals(full.by_symbol[symbol].execution_prices.index)
        pd.testing.assert_frame_equal(
            frame, full.by_symbol[symbol].raw[["Dividends", "Stock Splits"]].astype(float), check_dtype=False
        )
    # La fila sin Close la descarta igual que load_vintage.
    assert len(structure.by_symbol["MSFT"]) == 3


def test_estructura_rechaza_acciones_editadas_y_no_lee_precios_editados(tmp_path) -> None:
    result = _frozen(tmp_path, {"AAPL": _raw_history()})
    csv_path = result.manifest_path.parent / "AAPL.csv"
    original = csv_path.read_text(encoding="utf-8")

    # Un precio editado no cambia ni las fechas ni las acciones: la estructura no lo ve.
    csv_path.write_text(original.replace("121.5", "121.6", 1), encoding="utf-8")
    load_vintage_structure(result.data_vintage_id, root_dir=tmp_path)

    csv_path.write_text(original.replace("0.25", "0.26", 1), encoding="utf-8")
    with pytest.raises(ValueError, match="acciones corporativas"):
        load_vintage_structure(result.data_vintage_id, root_dir=tmp_path)


def test_filas_de_precio_solo_las_pedidas(tmp_path) -> None:
    result = _frozen(tmp_path, {"AAPL": _raw_history()})
    stamps = list(load_vintage_structure(result.data_vintage_id, root_dir=tmp_path).by_symbol["AAPL"].index)

    rows = load_price_rows(result.data_vintage_id, "AAPL", stamps[1:3], ("Close", "Adj Close"), root_dir=tmp_path)

    assert list(rows.index) == stamps[1:3] and list(rows.columns) == ["Close", "Adj Close"]
    assert rows["Close"].tolist() == [121.5, 122.5]
    with pytest.raises(KeyError):
        load_price_rows(result.data_vintage_id, "AAPL", ["2030-01-01"], ("Close",), root_dir=tmp_path)


def test_filas_estructurales_coinciden_con_read_raw_csv_con_precio_vacio(tmp_path) -> None:
    """CSV escrito a mano: fila con Close vacío, dividendo vacío y orden desordenado."""

    path = tmp_path / "X.csv"
    path.write_text(
        "timestamp,Open,High,Low,Close,Adj Close,Volume,Dividends,Stock Splits\n"
        "2024-06-09T00:00:00Z,3,3,3,3,3,10,0.5,0\n"
        "2024-06-07T00:00:00Z,1,1,1,1,1,10,,0\n"
        "2024-06-08T00:00:00Z,2,2,2,,2,10,0.25,2\n",
        encoding="utf-8",
    )

    full = read_raw_csv(path)
    rows = _structural_rows(path)

    assert rows.index.equals(full.index) and list(rows.index) == ["2024-06-07T00:00:00Z", "2024-06-09T00:00:00Z"]
    pd.testing.assert_frame_equal(rows, full[["Dividends", "Stock Splits"]].astype(float), check_dtype=False)
