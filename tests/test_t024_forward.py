"""Contrato de captura forward de T-024: petición exacta, cosecha apta, registro y conteos. Sin red."""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, ClassVar, Optional

import pandas as pd
import pytest

from advisor.data import market_data
from advisor.research import t024_captura as cap
from advisor.research import t024_decision as dec
from advisor.research import t024_forward as fwd
from advisor.research import vintage as vintage_mod
from advisor.research.t024_comun import DEV_VINTAGE_ID, ConteoCaptura
from advisor.research.vintage import freeze_vintage, hash_manifest, load_vintage

UTC = timezone.utc
CHECKPOINT_1 = date(2026, 11, 3)
FESTIVOS_1 = (date(2026, 11, 2),)
CHECKPOINT_2 = date(2026, 12, 1)
CODE_SHA = "b" * 40
DOWNLOADED = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Dobles sin red
# ---------------------------------------------------------------------------


def _frame(sessions: list[date], *, tz: str = "UTC", close: float = 100.0) -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.Timestamp(d).tz_localize(tz) for d in sessions])
    n = len(sessions)
    return pd.DataFrame(
        {
            "Open": [close] * n,
            "High": [close + 1] * n,
            "Low": [close - 1] * n,
            "Close": [close] * n,
            "Adj Close": [close] * n,
            "Volume": [1000.0] * n,
            "Dividends": [0.0] * n,
            "Stock Splits": [0.0] * n,
        },
        index=index,
    )


def _business_days(start: date, end: date) -> list[date]:
    out = []
    day = start
    while day < end:
        if day.weekday() < 5:
            out.append(day)
        day += timedelta(days=1)
    return out


class ExactProvider:
    """Sirve barras hábiles en `[start, end)`; registra cada llamada con sus kwargs."""

    def __init__(
        self,
        *,
        first: date = date(2026, 10, 19),
        fail: frozenset[str] = frozenset(),
        extra_bar: Optional[date] = None,
        revise: Optional[tuple[str, date, float]] = None,
    ) -> None:
        self.first = first
        self.fail = fail
        self.extra_bar = extra_bar
        self.revise = revise
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get_raw_history(self, symbol: str, **kwargs: Any) -> pd.DataFrame:
        self.calls.append((symbol, kwargs))
        if symbol in self.fail:
            raise ValueError(f"No se han recibido datos para el símbolo '{symbol}'")
        sessions = _business_days(max(self.first, date.fromisoformat(kwargs["start"])), date.fromisoformat(kwargs["end"]))
        if self.extra_bar is not None:
            sessions.append(self.extra_bar)
        frame = _frame(sessions)
        if self.revise is not None and self.revise[0] == symbol:
            stamp = pd.Timestamp(self.revise[1]).tz_localize("UTC")
            frame.loc[stamp, "Close"] = self.revise[2]
        return frame


class LegacyProvider:
    """Firma histórica del proveedor de tests: sin `start`/`end`. El modo `period` debe seguir llamándola así."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def get_raw_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        self.calls.append((symbol, period, interval))
        if symbol == "MSFT":
            raise ValueError("sin datos")
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


@dataclass(frozen=True)
class _Asset:
    timezone: str = "UTC"


class _Universe:
    def get(self, _symbol: str) -> _Asset:
        return _Asset()


class FakeTicker:
    calls: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    def history(self, **kwargs: Any) -> pd.DataFrame:
        FakeTicker.calls.append(kwargs)
        return _frame([date(2026, 10, 22), date(2026, 10, 23)])


@pytest.fixture(autouse=True)
def _version_fija(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vintage_mod, "_provider_version", lambda: "0.0-test")


def _congelar(tmp_path: Path, checkpoint: date = CHECKPOINT_1, festivos: tuple[date, ...] = FESTIVOS_1, **provider: Any) -> fwd.CosechaForward:
    peticion = fwd.peticion_checkpoint(checkpoint, festivos)
    return fwd.congelar_checkpoint(
        peticion,
        ExactProvider(**provider),
        root_dir=tmp_path,
        universe_vintage=fwd.UNIVERSE_VINTAGE_ID,
        hoy=checkpoint,
        downloaded_at=DOWNLOADED,
    )


# ---------------------------------------------------------------------------
# Proveedor: kwargs de yfinance
# ---------------------------------------------------------------------------


def test_proveedor_period_legacy_envia_exactamente_los_kwargs_de_siempre(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeTicker.calls = []
    monkeypatch.setattr(market_data.yf, "Ticker", FakeTicker)
    market_data.MarketDataProvider(0).get_raw_history("SAP.DE", period="5y", interval="1d")
    assert FakeTicker.calls == [{"period": "5y", "interval": "1d", "auto_adjust": False, "actions": True}]


def test_proveedor_start_end_envia_peticion_exacta_sin_period(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeTicker.calls = []
    monkeypatch.setattr(market_data.yf, "Ticker", FakeTicker)
    market_data.MarketDataProvider(0).get_raw_history("SAP.DE", interval="1d", start="2021-08-30", end="2026-10-26")
    assert FakeTicker.calls == [
        {"start": "2021-08-30", "end": "2026-10-26", "interval": "1d", "auto_adjust": False, "actions": True}
    ]


@pytest.mark.parametrize(
    "start,end",
    [("2021-08-30", None), (None, "2026-10-26"), ("2021-8-30", "2026-10-26"), ("2026-10-26", "2026-10-26"), ("2026-10-27", "2026-10-26")],
)
def test_proveedor_rechaza_peticion_exacta_mal_formada_sin_llamar(monkeypatch: pytest.MonkeyPatch, start: Optional[str], end: Optional[str]) -> None:
    FakeTicker.calls = []
    monkeypatch.setattr(market_data.yf, "Ticker", FakeTicker)
    with pytest.raises(ValueError):
        market_data.MarketDataProvider(0).get_raw_history("SAP.DE", start=start, end=end)
    assert FakeTicker.calls == []


# ---------------------------------------------------------------------------
# freeze_vintage: modo legacy intacto y modo exacto
# ---------------------------------------------------------------------------


def test_freeze_period_legacy_reproduce_el_id_y_el_manifiesto_de_main(tmp_path: Path) -> None:
    # Valores obtenidos con `git show 3bec864:advisor/research/vintage.py` sobre esta misma entrada.
    provider = LegacyProvider()
    result = freeze_vintage(
        ["AAPL", "MSFT"],
        provider,
        period="1y",
        interval="1d",
        root_dir=tmp_path,
        downloaded_at=datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        universe_vintage="uuuu",
    )
    assert result.data_vintage_id == "6214dfccb9fdb11080b7a36d813f400e0faa06d01bedaf315b90ca83d32aec3d"
    assert hashlib.sha256(result.manifest_path.read_bytes()).hexdigest() == "5fd016a32a0e41024ae68c2a63b888492a2ba79e26c15eeea6ac7c106bd14802"
    assert provider.calls == [("AAPL", "1y", "1d"), ("MSFT", "1y", "1d")]
    manifest = json.loads(result.manifest_path.read_text())
    assert manifest["schema_version"] == 1 and "request" not in manifest
    assert manifest["assets"][0]["requested_range"] == "1y"


@pytest.mark.parametrize("kwargs", [{}, {"period": "1y", "start": "2021-08-30", "end": "2026-10-26"}, {"start": "2021-08-30"}])
def test_freeze_exige_exactamente_una_peticion(tmp_path: Path, kwargs: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        freeze_vintage(["AAPL"], ExactProvider(), interval="1d", root_dir=tmp_path, **kwargs)  # type: ignore[arg-type]


def test_freeze_exacto_registra_la_peticion_completa_en_el_manifiesto(tmp_path: Path) -> None:
    provider = ExactProvider()
    result = freeze_vintage(
        ["SAP.DE", "AAPL"], provider, interval="1d", start="2021-08-30", end="2026-10-26", root_dir=tmp_path, downloaded_at=DOWNLOADED
    )
    assert [kw for _s, kw in provider.calls] == [{"interval": "1d", "start": "2021-08-30", "end": "2026-10-26"}] * 2
    manifest = json.loads(result.manifest_path.read_text())
    assert manifest["schema_version"] == 2
    assert manifest["request"] == {
        "symbols": ["SAP.DE", "AAPL"],
        "symbols_sha256": hashlib.sha256(b"SAP.DE\nAAPL").hexdigest(),
        "start": "2021-08-30",
        "end": "2026-10-26",
        "end_exclusive": True,
        "interval": "1d",
        "auto_adjust": False,
        "actions": True,
        "provider": "yfinance",
        "provider_version": "0.0-test",
    }
    entry = manifest["assets"][0]
    assert {k: entry[k] for k in ("requested_start", "requested_end", "end_exclusive", "auto_adjust", "actions")} == {
        "requested_start": "2021-08-30",
        "requested_end": "2026-10-26",
        "end_exclusive": True,
        "auto_adjust": False,
        "actions": True,
    }
    assert "requested_range" not in entry
    loaded = load_vintage(result.data_vintage_id, root_dir=tmp_path)
    assert list(loaded.by_symbol["SAP.DE"].raw.index)[-1] == "2026-10-23T00:00:00Z"


def test_freeze_exacto_start_inclusivo_end_exclusivo(tmp_path: Path) -> None:
    ok = freeze_vintage(["A"], ExactProvider(first=date(2026, 10, 19)), interval="1d", start="2026-10-19", end="2026-10-26", root_dir=tmp_path)
    raw = load_vintage(ok.data_vintage_id, root_dir=tmp_path).by_symbol["A"].raw
    assert raw.index[0] == "2026-10-19T00:00:00Z" and raw.index[-1] == "2026-10-23T00:00:00Z"

    class Extra:
        """`A` limpio; `B` con una barra en `end` (exclusivo); `C` con una barra antes de `start`."""

        def get_raw_history(self, symbol: str, **kwargs: Any) -> pd.DataFrame:
            sessions = _business_days(date(2026, 10, 19), date(2026, 10, 26))
            extra = {"B": [date(2026, 10, 26)], "C": [date(2026, 10, 16)]}.get(symbol, [])
            return _frame(sorted(sessions + extra))

    result = freeze_vintage(["A", "B", "C"], Extra(), interval="1d", start="2026-10-19", end="2026-10-26", root_dir=tmp_path)
    assert result.succeeded == ["A"]
    assert "2026-10-26" in result.failed["B"] and "2026-10-16" in result.failed["C"]
    assert all("barras fuera de la petición" in error for error in result.failed.values())


def test_freeze_exacto_fecha_de_barra_en_la_zona_de_la_plaza(tmp_path: Path) -> None:
    """Una sesión de Tokio del día `end` (medianoche local = día anterior en UTC) queda fuera."""

    class Tokyo:
        def get_raw_history(self, symbol: str, **kwargs: Any) -> pd.DataFrame:
            sessions = [date(2026, 10, 23)] if symbol == "OK.T" else [date(2026, 10, 23), date(2026, 10, 26)]
            return _frame(sessions, tz="Asia/Tokyo")

    result = freeze_vintage(["OK.T", "MAL.T"], Tokyo(), interval="1d", start="2026-10-19", end="2026-10-26", root_dir=tmp_path)
    assert result.succeeded == ["OK.T"]
    assert "2026-10-26" in result.failed["MAL.T"]


# ---------------------------------------------------------------------------
# Cosecha consumida intacta y lista de símbolos
# ---------------------------------------------------------------------------


def test_cosecha_consumida_manifiesto_verifica_con_su_id_original() -> None:
    _dir, manifest = vintage_mod._verified_manifest(DEV_VINTAGE_ID, "data/vintages")
    body = {k: v for k, v in manifest.items() if k not in {"manifest_hash", "data_vintage_id"}}
    assert hash_manifest(body) == DEV_VINTAGE_ID == manifest["data_vintage_id"]
    assert manifest["schema_version"] == 1 and "request" not in manifest


def test_cosecha_consumida_carga_completa_con_su_id_original() -> None:
    if not (Path("data/vintages") / DEV_VINTAGE_ID / "AAPL.csv").is_file():
        pytest.skip("data/vintages no está disponible")
    loaded = load_vintage(DEV_VINTAGE_ID)
    assert loaded.data_vintage_id == DEV_VINTAGE_ID and len(loaded.by_symbol) == 126


def test_simbolos_forward_estables_y_derivados_del_manifiesto_consumido() -> None:
    first = fwd.simbolos_forward()
    assert first == fwd.simbolos_forward()
    assert len(first) == 126 and list(first) == sorted(first)
    assert hashlib.sha256("\n".join(first).encode()).hexdigest() == fwd.SIMBOLOS_FORWARD_SHA256
    _dir, manifest = vintage_mod._verified_manifest(DEV_VINTAGE_ID, "data/vintages")
    assert set(first) == {asset["symbol"] for asset in manifest["assets"]}


def test_simbolos_forward_cubren_activos_benchmarks_y_contexto() -> None:
    from advisor.analysis.benchmark import resolve_benchmark_symbol
    from advisor.config import load_config
    from advisor.research.p4 import context_assets_of
    from advisor.universe.loader import load_universe
    from advisor.universe.vintage import universe_vintage_id

    config = load_config("config.yaml")
    universe = load_universe(config.universe_path)
    assert universe_vintage_id(universe) == fwd.UNIVERSE_VINTAGE_ID
    needed = set(cap.asset_list())
    needed |= {b for s in cap.asset_list() if (b := resolve_benchmark_symbol(universe.get(s), config.report))}
    needed |= {config.market_context.vix_symbol, config.market_context.trend_symbol}
    needed |= {a.primary_symbol for a in context_assets_of(universe) if a.region == "ASIA"}
    assert needed <= set(fwd.simbolos_forward())


def test_universo_congelado_igual_al_de_p5() -> None:
    from advisor.research import p5

    assert fwd.UNIVERSE_VINTAGE_ID == p5.UNIVERSE_VINTAGE_ID


def test_simbolos_forward_detecta_manifiesto_alterado(tmp_path: Path) -> None:
    src = Path("data/vintages") / DEV_VINTAGE_ID / "manifest.json"
    manifest = json.loads(src.read_text())
    manifest["assets"] = manifest["assets"][1:]
    body = {k: v for k, v in manifest.items() if k not in {"manifest_hash", "data_vintage_id"}}
    manifest["manifest_hash"] = manifest["data_vintage_id"] = hash_manifest(body)
    # Rehasheado: el id cambia y ya no es la cosecha consumida.
    (tmp_path / manifest["data_vintage_id"]).mkdir()
    (tmp_path / manifest["data_vintage_id"] / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(FileNotFoundError):
        fwd.simbolos_forward(tmp_path)
    # Mismo id, cuerpo editado: el hash no cuadra.
    (tmp_path / DEV_VINTAGE_ID).mkdir()
    manifest["manifest_hash"] = manifest["data_vintage_id"] = DEV_VINTAGE_ID
    (tmp_path / DEV_VINTAGE_ID / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        fwd.simbolos_forward(tmp_path)


# ---------------------------------------------------------------------------
# Días hábiles y petición del primer checkpoint
# ---------------------------------------------------------------------------


def test_primer_checkpoint_end_exclusivo_2026_10_26() -> None:
    end = fwd.end_exclusivo(CHECKPOINT_1, FESTIVOS_1)
    assert end == date(2026, 10, 26)
    fuera = [d for d in _business_days(end, CHECKPOINT_1) if d not in FESTIVOS_1]
    assert fuera == [date(2026, 10, 26), date(2026, 10, 27), date(2026, 10, 28), date(2026, 10, 29), date(2026, 10, 30)]


def test_checkpoint_debe_ser_primer_dia_habil_con_sus_festivos() -> None:
    with pytest.raises(fwd.T024ForwardError):
        fwd.end_exclusivo(CHECKPOINT_1, ())
    with pytest.raises(fwd.T024ForwardError):
        fwd.end_exclusivo(date(2026, 11, 2), FESTIVOS_1)
    assert fwd.primer_dia_habil(2026, 11, FESTIVOS_1) == CHECKPOINT_1
    assert fwd.end_exclusivo(CHECKPOINT_2, ()) == date(2026, 11, 24)


def test_peticion_primer_checkpoint_canonica() -> None:
    peticion = fwd.peticion_checkpoint(CHECKPOINT_1, FESTIVOS_1).serializable()
    assert {k: v for k, v in peticion.items() if k != "symbols"} == {
        "checkpoint": "2026-11-03",
        "start": "2021-08-30",
        "end": "2026-10-26",
        "end_exclusive": True,
        "interval": "1d",
        "auto_adjust": False,
        "actions": True,
        "symbols_sha256": fwd.SIMBOLOS_FORWARD_SHA256,
        "n_symbols": 126,
        "festivos": ["2026-11-02"],
    }


def test_peticion_anterior_al_primer_checkpoint_se_niega() -> None:
    with pytest.raises(fwd.T024ForwardError):
        fwd.peticion_checkpoint(date(2026, 10, 1), ())


# ---------------------------------------------------------------------------
# Congelación apta o no registrable
# ---------------------------------------------------------------------------


def test_congelar_antes_del_checkpoint_se_niega_sin_llamar_al_proveedor(tmp_path: Path) -> None:
    provider = ExactProvider()
    peticion = fwd.peticion_checkpoint(CHECKPOINT_1, FESTIVOS_1)
    with pytest.raises(fwd.T024ForwardError):
        fwd.congelar_checkpoint(peticion, provider, root_dir=tmp_path, universe_vintage=fwd.UNIVERSE_VINTAGE_ID, hoy=date(2026, 11, 2))
    with pytest.raises(fwd.T024ForwardError):
        fwd.congelar_checkpoint(peticion, provider, root_dir=tmp_path, universe_vintage="x" * 64, hoy=CHECKPOINT_1)
    assert provider.calls == [] and not any(tmp_path.iterdir())


def test_congelar_completa_es_apta_y_pide_los_126_con_start_end(tmp_path: Path) -> None:
    provider = ExactProvider()
    peticion = fwd.peticion_checkpoint(CHECKPOINT_1, FESTIVOS_1)
    cosecha = fwd.congelar_checkpoint(
        peticion, provider, root_dir=tmp_path, universe_vintage=fwd.UNIVERSE_VINTAGE_ID, hoy=CHECKPOINT_1, downloaded_at=DOWNLOADED
    )
    assert cosecha.apta and cosecha.motivos == () and cosecha.data_vintage_id
    assert [s for s, _kw in provider.calls] == list(fwd.simbolos_forward())
    assert {json.dumps(kw, sort_keys=True) for _s, kw in provider.calls} == {
        json.dumps({"interval": "1d", "start": "2021-08-30", "end": "2026-10-26"}, sort_keys=True)
    }


def test_cosecha_parcial_no_apta_no_se_registra_y_deja_evidencia(tmp_path: Path) -> None:
    cosecha = _congelar(tmp_path, fail=frozenset({"SAP.DE"}))
    assert not cosecha.apta
    assert any("SAP.DE" in motivo for motivo in cosecha.motivos)
    assert cosecha.data_vintage_id and (tmp_path / cosecha.data_vintage_id / "manifest.json").is_file()
    with pytest.raises(fwd.T024ForwardError):
        fwd.entrada_registro(cosecha.data_vintage_id, cosecha.peticion, t024_code_sha=CODE_SHA, root_dir=tmp_path)


def test_cosecha_sin_ningun_simbolo_no_apta(tmp_path: Path) -> None:
    cosecha = _congelar(tmp_path, fail=frozenset(fwd.simbolos_forward()))
    assert not cosecha.apta and cosecha.data_vintage_id is None


def test_cosecha_con_otra_peticion_no_es_apta_para_otro_checkpoint(tmp_path: Path) -> None:
    cosecha = _congelar(tmp_path)
    assert cosecha.data_vintage_id
    otra = fwd.peticion_checkpoint(CHECKPOINT_2, ())
    motivos = fwd.verificar_cosecha_forward(cosecha.data_vintage_id, otra, root_dir=tmp_path)
    assert any("end" in motivo for motivo in motivos)


def test_csv_alterado_deja_la_cosecha_no_apta(tmp_path: Path) -> None:
    cosecha = _congelar(tmp_path)
    assert cosecha.data_vintage_id
    csv = tmp_path / cosecha.data_vintage_id / "AAPL.csv"
    csv.write_text(csv.read_text().replace(",101,99,", ",101,98,", 1))
    assert fwd.verificar_cosecha_forward(cosecha.data_vintage_id, cosecha.peticion, root_dir=tmp_path)


# ---------------------------------------------------------------------------
# Registro forward
# ---------------------------------------------------------------------------


def _registro_con(tmp_path: Path, *cosechas: fwd.CosechaForward) -> dict[str, object]:
    registro = fwd.registro_vacio()
    for cosecha in cosechas:
        assert cosecha.data_vintage_id
        entrada = fwd.entrada_registro(cosecha.data_vintage_id, cosecha.peticion, t024_code_sha=CODE_SHA, root_dir=tmp_path)
        registro = fwd.anadir_entrada(registro, entrada)
    return registro


def test_entrada_registro_canonica_sin_desenlaces(tmp_path: Path) -> None:
    cosecha = _congelar(tmp_path)
    assert cosecha.data_vintage_id
    entrada = fwd.entrada_registro(cosecha.data_vintage_id, cosecha.peticion, t024_code_sha=CODE_SHA, root_dir=tmp_path)
    assert set(entrada) == fwd.CLAVES_ENTRADA
    assert entrada["checkpoint"] == "2026-11-03"
    assert entrada["requested_start"] == "2021-08-30" and entrada["requested_end"] == "2026-10-26"
    assert entrada["manifest_hash"] == entrada["data_vintage_id"] == cosecha.data_vintage_id
    assert entrada["manifest_file_sha256"] == hashlib.sha256((tmp_path / cosecha.data_vintage_id / "manifest.json").read_bytes()).hexdigest()
    assert entrada["universe_vintage_id"] == fwd.UNIVERSE_VINTAGE_ID
    assert entrada["provider_version"] == "0.0-test"
    assert entrada["T024_PREREG_SHA"] == "dfcca0ef3428df916089480a0ca574f47e550c24"
    assert entrada["T024_CODE_SHA"] == CODE_SHA


def test_registro_forward_determinista_y_compatible(tmp_path: Path) -> None:
    a = _congelar(tmp_path / "a")
    b = _congelar(tmp_path / "b")
    assert a.data_vintage_id == b.data_vintage_id
    texto_a = fwd.serializar_registro(_registro_con(tmp_path / "a", a))
    texto_b = fwd.serializar_registro(_registro_con(tmp_path / "b", b))
    assert texto_a == texto_b
    path = tmp_path / "registro-forward.json"
    fwd.escribir_registro(path, json.loads(texto_a))
    assert path.read_text() == texto_a
    assert a.data_vintage_id
    cargado = dec.cargar_registro_forward(path, a.data_vintage_id)
    assert cargado.cosechas == ((a.data_vintage_id, CHECKPOINT_1),)
    assert fwd.leer_registro(path) == json.loads(texto_a)


@pytest.mark.parametrize("clave", ["R", "d1", "D2", "pnl", "salida", "exit_reason"])
def test_registro_rechaza_cualquier_clave_de_desenlace(tmp_path: Path, clave: str) -> None:
    cosecha = _congelar(tmp_path)
    assert cosecha.data_vintage_id
    entrada = fwd.entrada_registro(cosecha.data_vintage_id, cosecha.peticion, t024_code_sha=CODE_SHA, root_dir=tmp_path)
    with pytest.raises(fwd.T024ForwardError):
        fwd.anadir_entrada(fwd.registro_vacio(), {**entrada, clave: 0.0})
    registro = _registro_con(tmp_path, cosecha)
    registro[clave] = 1
    with pytest.raises(fwd.T024ForwardError):
        fwd.validar_registro(registro)


def test_registro_detecta_edicion_orden_duplicado_y_checkpoint_previo(tmp_path: Path) -> None:
    c1 = _congelar(tmp_path)
    c2 = _congelar(tmp_path, CHECKPOINT_2, (), first=date(2026, 10, 19))
    registro = _registro_con(tmp_path, c1, c2)
    editado = json.loads(json.dumps(registro))
    editado["cosechas"][0]["provider_version"] = "9.9"
    with pytest.raises(fwd.T024ForwardError):
        fwd.validar_registro(editado)
    with pytest.raises(fwd.T024ForwardError):
        _registro_con(tmp_path, c2, c1)
    assert c1.data_vintage_id
    e1 = fwd.entrada_registro(c1.data_vintage_id, c1.peticion, t024_code_sha=CODE_SHA, root_dir=tmp_path)
    with pytest.raises(fwd.T024ForwardError):
        fwd.anadir_entrada(fwd.anadir_entrada(fwd.registro_vacio(), e1), {**e1, "checkpoint": "2026-12-01", "requested_end": "2026-11-24", "festivos": []})
    with pytest.raises(fwd.T024ForwardError):
        fwd.anadir_entrada(fwd.registro_vacio(), {**e1, "checkpoint": "2026-10-01", "requested_end": "2026-09-24", "festivos": []})
    with pytest.raises(fwd.T024ForwardError):
        fwd.anadir_entrada(fwd.registro_vacio(), {**e1, "requested_end": "2026-10-27"})
    with pytest.raises(fwd.T024ForwardError):
        fwd.anadir_entrada(fwd.registro_vacio(), {**e1, "T024_PREREG_SHA": "c" * 40})


def test_previa_primera_ninguna_segunda_la_inmediatamente_anterior(tmp_path: Path) -> None:
    c1 = _congelar(tmp_path)
    c2 = _congelar(tmp_path, CHECKPOINT_2, ())
    registro = _registro_con(tmp_path, c1, c2)
    assert c1.data_vintage_id and c2.data_vintage_id
    assert fwd.entrada_de(registro, c1.data_vintage_id)[1] is None
    assert fwd.entrada_de(registro, c2.data_vintage_id)[1] == c1.data_vintage_id


# ---------------------------------------------------------------------------
# Captura del checkpoint: solo conteos
# ---------------------------------------------------------------------------


def test_calidad_sin_previa_y_con_previa(tmp_path: Path) -> None:
    c1 = _congelar(tmp_path, first=date(2026, 10, 19))
    c2 = _congelar(tmp_path, CHECKPOINT_2, (), first=date(2026, 10, 20), revise=("AAPL", date(2026, 10, 21), 101.0))
    assert c1.data_vintage_id and c2.data_vintage_id
    v1 = load_vintage(c1.data_vintage_id, root_dir=tmp_path)
    v2 = load_vintage(c2.data_vintage_id, root_dir=tmp_path)
    assert fwd.calidad_cosechas(v1, None, _Universe(), c_e=CHECKPOINT_1) == (None, None)
    nuevas, revisadas = fwd.calidad_cosechas(v2, v1, _Universe(), c_e=CHECKPOINT_2)
    # c1: 19–23 oct; c2: 20 oct–23 nov. Nuevas: 26 oct–23 nov (21 sesiones) × 126. Revisadas: AAPL 21 oct
    # (cambia) + 19 oct desaparecida en los 126.
    assert nuevas == 21 * 126
    assert revisadas == 1 + 126


def _registro_en_disco(tmp_path: Path, *cosechas: fwd.CosechaForward) -> Path:
    path = tmp_path / "registro-forward.json"
    fwd.escribir_registro(path, _registro_con(tmp_path, *cosechas))
    return path


def _resultado_captura() -> cap.ResultadoCaptura:
    conteo = ConteoCaptura("B2", 7, 5, {"ABOVE_MAX_ENTRY": 2}, 4, 3, barras_nuevas=999, barras_revisadas=999)
    return cap.ResultadoCaptura({"B2": conteo}, {"B2:no_operar": 11, "S2:sin_niveles": 1}, "")


class _Prohibido:
    def __init__(self, name: str) -> None:
        self.name = name

    def __call__(self, *_a: Any, **_k: Any) -> Any:
        raise AssertionError(f"la captura llamó a {self.name}")


def _blindar_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "construir_resultado",
        "construir_ventanas",
        "calcular_ventana",
        "barras_decision",
        "salida_p6",
        "d1_cerrada",
        "bootstrap_semanal",
        "ejecutar_mirada",
        "crear_marca_exclusiva",
        "_crear_token_mirada",
    ):
        monkeypatch.setattr(dec, name, _Prohibido(name))


def test_capturar_checkpoint_primero_sin_previa_y_segundo_con_revisiones(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _blindar_decision(monkeypatch)
    monkeypatch.setattr(dec, "verificar_identidad", lambda: CODE_SHA)
    llamadas: list[dict[str, Any]] = []

    def fake_capturar(config: Any, universe: Any, vintage: Any, **kwargs: Any) -> cap.ResultadoCaptura:
        llamadas.append({"id": vintage.data_vintage_id, **kwargs})
        return _resultado_captura()

    monkeypatch.setattr(fwd, "capturar", fake_capturar)
    c1 = _congelar(tmp_path)
    c2 = _congelar(tmp_path, CHECKPOINT_2, (), revise=("AAPL", date(2026, 10, 21), 101.0))
    path = _registro_en_disco(tmp_path, c1, c2)
    assert c1.data_vintage_id and c2.data_vintage_id

    s1 = fwd.capturar_checkpoint(None, _Universe(), data_vintage_id=c1.data_vintage_id, registro_path=path, root_dir=tmp_path)
    s2 = fwd.capturar_checkpoint(None, _Universe(), data_vintage_id=c2.data_vintage_id, registro_path=path, root_dir=tmp_path)
    assert llamadas == [
        {"id": c1.data_vintage_id, "c_e": CHECKPOINT_1, "desarrollo": False},
        {"id": c2.data_vintage_id, "c_e": CHECKPOINT_2, "desarrollo": False},
    ]
    assert s1["previa_data_vintage_id"] is None and s1["barras_nuevas"] is None and s1["barras_revisadas"] is None
    assert s2["previa_data_vintage_id"] == c1.data_vintage_id
    assert s2["barras_nuevas"] == 21 * 126 and s2["barras_revisadas"] == 1
    assert set(s1) == fwd.CLAVES_SALIDA
    assert s1["politicas"] == {
        "B2": {"senales_operar": 7, "ejecutables": 5, "rechazos": {"ABOVE_MAX_ENTRY": 2}, "q_p": 4, "w_p": 3, "exclusiones": {"no_operar": 11}},
        "S2": {"senales_operar": 0, "ejecutables": 0, "rechazos": {}, "q_p": 0, "w_p": 0, "exclusiones": {"sin_niveles": 1}},
        "C0": {"senales_operar": 0, "ejecutables": 0, "rechazos": {}, "q_p": 0, "w_p": 0, "exclusiones": {}},
    }
    assert not list(tmp_path.glob("*.consumida")) and not list(Path(".").glob("*.t024.consumida"))


def test_capturar_checkpoint_niega_otro_code_sha_o_cosecha_no_registrada(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(fwd, "capturar", _Prohibido("capturar"))
    c1 = _congelar(tmp_path)
    path = _registro_en_disco(tmp_path, c1)
    assert c1.data_vintage_id
    monkeypatch.setattr(dec, "verificar_identidad", lambda: "c" * 40)
    with pytest.raises(fwd.T024ForwardError):
        fwd.capturar_checkpoint(None, _Universe(), data_vintage_id=c1.data_vintage_id, registro_path=path, root_dir=tmp_path)
    monkeypatch.setattr(dec, "verificar_identidad", lambda: CODE_SHA)
    parcial = _congelar(tmp_path / "p", fail=frozenset({"AAPL"}))
    assert parcial.data_vintage_id
    with pytest.raises(dec.T024DecisionError):
        fwd.capturar_checkpoint(None, _Universe(), data_vintage_id=parcial.data_vintage_id, registro_path=path, root_dir=tmp_path / "p")


def test_capturar_checkpoint_falla_si_identidad_falla(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def deniega() -> str:
        raise dec.T024DecisionError("ejecutor cambiado desde T024_CODE_SHA")

    monkeypatch.setattr(dec, "verificar_identidad", deniega)
    monkeypatch.setattr(fwd, "capturar", _Prohibido("capturar"))
    with pytest.raises(dec.T024DecisionError):
        fwd.capturar_checkpoint(None, _Universe(), data_vintage_id="x", registro_path=tmp_path / "r.json", root_dir=tmp_path)


def test_salida_rechaza_claves_fuera_del_contrato() -> None:
    salida = fwd.salida_captura(
        _resultado_captura(), checkpoint=CHECKPOINT_1, data_vintage_id="v", previa_data_vintage_id=None, barras_nuevas=None, barras_revisadas=None
    )
    fwd.validar_salida(salida)
    with pytest.raises(fwd.T024ForwardError):
        fwd.validar_salida({**salida, "mean_R": 0.1})
    politicas = json.loads(json.dumps(salida["politicas"]))
    politicas["B2"]["d2"] = 0.0
    with pytest.raises(fwd.T024ForwardError):
        fwd.validar_salida({**salida, "politicas": politicas})


def test_imports_de_forward_no_alcanzan_desenlaces() -> None:
    tree = ast.parse(Path("advisor/research/t024_forward.py").read_text(encoding="utf-8"))
    importados: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("advisor."):
            importados.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            assert not any(alias.name.startswith("advisor.research") for alias in node.names)
    decision = {name for name in importados if name.startswith("advisor.research.t024_decision.")}
    assert decision == {"advisor.research.t024_decision.cargar_registro_forward", "advisor.research.t024_decision.verificar_identidad"}
    prohibidos = {"p6", "p6_sim", "simulate", "salida_p6", "construir_resultado", "construir_ventanas", "barras_decision", "ejecutar_mirada", "d1_cerrada"}
    assert not {name.rsplit(".", 1)[-1] for name in importados} & prohibidos
    assert not any(".p6" in name for name in importados)
    callables = {
        name
        for name in importados
        if name.startswith("advisor.research.") and not name.rsplit(".", 1)[-1].lstrip("_")[:1].isupper() and "t024_comun" not in name
    }
    assert callables == set(fwd.T024_FORWARD_IMPORTED_CALLABLES)


# ---------------------------------------------------------------------------
# CLI: la petición se calcula; la congelación hoy se niega antes de tocar la red
# ---------------------------------------------------------------------------


def test_cli_peticion_no_descarga(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(market_data.yf, "Ticker", _Prohibido("yf.Ticker"))
    assert fwd.main(["peticion", "--checkpoint", "2026-11-03", "--festivo", "2026-11-02"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["end"] == "2026-10-26" and out["start"] == "2021-08-30" and out["n_symbols"] == 126


def test_cli_congelar_antes_del_checkpoint_se_niega_sin_red(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(market_data.yf, "Ticker", _Prohibido("yf.Ticker"))
    monkeypatch.setattr(fwd, "hoy_checkpoint", lambda: date(2026, 10, 6))
    with pytest.raises(fwd.T024ForwardError):
        fwd.main(["congelar", "--checkpoint", "2026-11-03", "--festivo", "2026-11-02", "--data-dir", str(tmp_path)])
    assert not any(tmp_path.iterdir())


def test_cli_registrar_parcial_no_escribe_registro(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dec, "verificar_identidad", lambda: CODE_SHA)
    parcial = _congelar(tmp_path, fail=frozenset({"AAPL"}))
    assert parcial.data_vintage_id
    registro = tmp_path / "registro-forward.json"
    with pytest.raises(fwd.T024ForwardError):
        fwd.main(
            ["registrar", "--data-vintage-id", parcial.data_vintage_id, "--checkpoint", "2026-11-03", "--festivo", "2026-11-02",
             "--registro", str(registro), "--data-dir", str(tmp_path)]
        )
    assert not registro.exists()


def test_cli_registrar_apta_escribe_registro_compatible(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(dec, "verificar_identidad", lambda: CODE_SHA)
    cosecha = _congelar(tmp_path)
    assert cosecha.data_vintage_id
    registro = tmp_path / "registro-forward.json"
    args = ["registrar", "--data-vintage-id", cosecha.data_vintage_id, "--checkpoint", "2026-11-03", "--festivo", "2026-11-02",
            "--registro", str(registro), "--data-dir", str(tmp_path)]
    assert fwd.main(args) == 0
    assert dec.cargar_registro_forward(registro, cosecha.data_vintage_id).cosechas == ((cosecha.data_vintage_id, CHECKPOINT_1),)
    with pytest.raises(fwd.T024ForwardError):
        fwd.main(args)
    shutil.rmtree(tmp_path / cosecha.data_vintage_id)
