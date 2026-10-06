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
        t024_code_sha=CODE_SHA,
        hoy=checkpoint,
        downloaded_at=datetime.combine(checkpoint, datetime.min.time(), UTC) + timedelta(hours=9),
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
    # `end` es estricto; una barra anterior a `start` es historia de más y no invalida el símbolo.
    assert result.succeeded == ["A", "C"]
    assert set(result.failed) == {"B"} and "2026-10-26" in result.failed["B"]
    assert "barras fuera de la petición" in result.failed["B"]


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
    # Los tests de procedencia usan un universo doble que resuelve cualquier símbolo; el real también debe
    # resolver los 126, o la comprobación de rango fallaría cerrada en el checkpoint.
    assert all(universe.get(symbol) is not None for symbol in fwd.simbolos_forward())


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
        fwd.congelar_checkpoint(peticion, provider, root_dir=tmp_path, universe_vintage=fwd.UNIVERSE_VINTAGE_ID, t024_code_sha=CODE_SHA, hoy=date(2026, 11, 2))
    with pytest.raises(fwd.T024ForwardError):
        fwd.congelar_checkpoint(peticion, provider, root_dir=tmp_path, universe_vintage="x" * 64, t024_code_sha=CODE_SHA, hoy=CHECKPOINT_1)
    assert provider.calls == [] and not any(tmp_path.iterdir())


def test_congelar_completa_es_apta_y_pide_los_126_con_start_end(tmp_path: Path) -> None:
    provider = ExactProvider()
    peticion = fwd.peticion_checkpoint(CHECKPOINT_1, FESTIVOS_1)
    cosecha = fwd.congelar_checkpoint(
        peticion, provider, root_dir=tmp_path, universe_vintage=fwd.UNIVERSE_VINTAGE_ID, t024_code_sha=CODE_SHA, hoy=CHECKPOINT_1, downloaded_at=DOWNLOADED
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
    motivos = fwd.verificar_cosecha_forward(cosecha.data_vintage_id, otra, t024_code_sha=CODE_SHA, root_dir=tmp_path)
    assert any("end" in motivo for motivo in motivos)


def test_csv_alterado_deja_la_cosecha_no_apta(tmp_path: Path) -> None:
    cosecha = _congelar(tmp_path)
    assert cosecha.data_vintage_id
    csv = tmp_path / cosecha.data_vintage_id / "AAPL.csv"
    csv.write_text(csv.read_text().replace(",101,99,", ",101,98,", 1))
    assert fwd.verificar_cosecha_forward(cosecha.data_vintage_id, cosecha.peticion, t024_code_sha=CODE_SHA, root_dir=tmp_path)


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


# ---------------------------------------------------------------------------
# Revisión Codex r1: el lector decisorio solo acepta el registro canónico
# ---------------------------------------------------------------------------


def _escribir_json(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_lector_decisorio_rechaza_registro_contaminado_aunque_cuadre_el_sha_minimo(tmp_path: Path) -> None:
    cosecha = _congelar(tmp_path)
    assert cosecha.data_vintage_id
    vid = cosecha.data_vintage_id
    canonico = _registro_con(tmp_path, cosecha)
    path = tmp_path / "r.json"

    contaminado = json.loads(json.dumps(canonico))
    contaminado["cosechas"][0]["D2"] = 0.01  # el sha256 mínimo (id + checkpoint) sigue cuadrando
    assert contaminado["sha256"] == fwd._sha256_compatible(contaminado["cosechas"])
    with pytest.raises(dec.T024DecisionError, match="no canónico"):
        dec.cargar_registro_forward(_escribir_json(path, contaminado), vid)

    arriba = {**json.loads(json.dumps(canonico)), "mean_R": 0.3}
    with pytest.raises(dec.T024DecisionError, match="no canónico"):
        dec.cargar_registro_forward(_escribir_json(path, arriba), vid)

    editado = json.loads(json.dumps(canonico))
    editado["cosechas"][0]["T024_CODE_SHA"] = "c" * 40
    with pytest.raises(dec.T024DecisionError, match="no canónico"):
        dec.cargar_registro_forward(_escribir_json(path, editado), vid)

    minimo = {"cosechas": [{"data_vintage_id": vid, "checkpoint": "2026-11-03"}], "sha256": canonico["sha256"]}
    with pytest.raises(dec.T024DecisionError, match="no canónico"):
        dec.cargar_registro_forward(_escribir_json(path, minimo), vid)

    assert dec.cargar_registro_forward(_escribir_json(path, canonico), vid).cosechas == ((vid, CHECKPOINT_1),)


def test_lector_decisorio_rechaza_checkpoint_repetido(tmp_path: Path) -> None:
    c1 = _congelar(tmp_path)
    c2 = _congelar(tmp_path, CHECKPOINT_2, ())
    assert c1.data_vintage_id and c2.data_vintage_id
    e1 = fwd.entrada_registro(c1.data_vintage_id, c1.peticion, t024_code_sha=CODE_SHA, root_dir=tmp_path)
    e2 = {**e1, "data_vintage_id": c2.data_vintage_id, "manifest_hash": c2.data_vintage_id}
    with pytest.raises(dec.T024DecisionError, match="no canónico"):
        dec.cargar_registro_forward(_escribir_json(tmp_path / "r.json", fwd._registro([e1, e2])), c2.data_vintage_id)


# ---------------------------------------------------------------------------
# Revisión Codex r1: la salida se valida también por contenido
# ---------------------------------------------------------------------------


def _salida_valida(**calidad: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"previa_data_vintage_id": None, "barras_nuevas": None, "barras_revisadas": None, **calidad}
    return fwd.salida_captura(_resultado_captura(), checkpoint=CHECKPOINT_1, data_vintage_id="v", **kwargs)


@pytest.mark.parametrize(
    "mutar",
    [
        lambda s: s["politicas"]["B2"]["rechazos"].update({"R": 1}),
        lambda s: s["politicas"]["B2"]["rechazos"].update({"exit_reason=stop": 1}),
        lambda s: s["politicas"]["S2"]["exclusiones"].update({"D2_media": 0}),
        lambda s: s["politicas"]["S2"]["exclusiones"].update({"no_operar": 0.5}),
        lambda s: s["politicas"]["C0"].update({"q_p": True}),
        lambda s: s["politicas"]["C0"].update({"w_p": -1}),
        lambda s: s.update({"barras_nuevas": 3}),
        lambda s: s.update({"previa_data_vintage_id": "p"}),
    ],
)
def test_salida_rechaza_fugas_dentro_de_los_mapas_permitidos(mutar: Any) -> None:
    salida = json.loads(json.dumps(_salida_valida()))
    fwd.validar_salida(salida)
    mutar(salida)
    with pytest.raises(fwd.T024ForwardError):
        fwd.validar_salida(salida)


def test_salida_con_previa_exige_calidad() -> None:
    fwd.validar_salida(_salida_valida(previa_data_vintage_id="p", barras_nuevas=5, barras_revisadas=0))


def test_simbolos_forward_no_dependen_del_directorio_de_trabajo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    esperado = fwd.simbolos_forward()
    monkeypatch.chdir(tmp_path)
    assert fwd.simbolos_forward() == esperado
    assert fwd.peticion_checkpoint(CHECKPOINT_1, FESTIVOS_1).symbols == esperado


def test_cli_congelar_exige_identidad_antes_de_tocar_la_red(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def deniega() -> str:
        raise dec.T024DecisionError("árbol de ejecutor no limpio")

    monkeypatch.setattr(market_data.yf, "Ticker", _Prohibido("yf.Ticker"))
    monkeypatch.setattr(fwd, "hoy_checkpoint", lambda: CHECKPOINT_1)
    monkeypatch.setattr(dec, "verificar_identidad", deniega)
    with pytest.raises(dec.T024DecisionError):
        fwd.main(["congelar", "--checkpoint", "2026-11-03", "--festivo", "2026-11-02", "--data-dir", str(tmp_path)])
    assert not any(tmp_path.iterdir())


def test_cache_de_barras_pasa_la_peticion_exacta_sin_tocarla() -> None:
    from advisor.data.bar_cache import CachedBarProvider

    inner = ExactProvider()
    cached = CachedBarProvider(
        inner, store=None, resolve_market=lambda _s: None, reference=DOWNLOADED, settlement_minutes=0, window_sessions=5,
        readjustment_tolerance=0.0,
    )
    cached.get_raw_history("A", interval="1d", start="2026-10-19", end="2026-10-26")
    assert inner.calls == [("A", {"period": "1y", "interval": "1d", "drop_na": True, "start": "2026-10-19", "end": "2026-10-26"})]


# ---------------------------------------------------------------------------
# Revisión r1 (revisor): la cosecha queda ligada a su checkpoint, festivos e identidad
# ---------------------------------------------------------------------------


def test_manifiesto_forward_guarda_el_contexto_del_checkpoint(tmp_path: Path) -> None:
    cosecha = _congelar(tmp_path)
    assert cosecha.data_vintage_id
    manifest = json.loads((tmp_path / cosecha.data_vintage_id / "manifest.json").read_text())
    assert manifest["request"]["context"] == {
        "estudio": "T-024",
        "checkpoint": "2026-11-03",
        "festivos": ["2026-11-02"],
        "T024_PREREG_SHA": "dfcca0ef3428df916089480a0ca574f47e550c24",
        "T024_CODE_SHA": CODE_SHA,
    }


def test_cosecha_congelada_con_otro_codigo_no_se_registra(tmp_path: Path) -> None:
    cosecha = _congelar(tmp_path)
    assert cosecha.data_vintage_id
    with pytest.raises(fwd.T024ForwardError, match="context"):
        fwd.entrada_registro(cosecha.data_vintage_id, cosecha.peticion, t024_code_sha="c" * 40, root_dir=tmp_path)


def test_cosecha_registrada_con_otro_checkpoint_o_festivos_se_niega(tmp_path: Path) -> None:
    cosecha = _congelar(tmp_path, CHECKPOINT_2, ())
    assert cosecha.data_vintage_id
    desplazada = fwd.peticion_checkpoint(date(2026, 12, 2), (date(2026, 12, 1),))
    assert desplazada.end == cosecha.peticion.end
    with pytest.raises(fwd.T024ForwardError, match="context"):
        fwd.entrada_registro(cosecha.data_vintage_id, desplazada, t024_code_sha=CODE_SHA, root_dir=tmp_path)


def test_cosecha_descargada_antes_del_checkpoint_no_es_apta(tmp_path: Path) -> None:
    peticion = fwd.peticion_checkpoint(CHECKPOINT_1, FESTIVOS_1)
    cosecha = fwd.congelar_checkpoint(
        peticion, ExactProvider(), root_dir=tmp_path, universe_vintage=fwd.UNIVERSE_VINTAGE_ID, t024_code_sha=CODE_SHA,
        hoy=CHECKPOINT_1, downloaded_at=datetime(2026, 11, 2, 23, 30, tzinfo=UTC),  # 23:30 en Canarias: día 2
    )
    assert not cosecha.apta and "cosecha descargada antes del checkpoint" in cosecha.motivos


def test_registro_rechaza_dos_checkpoints_del_mismo_mes() -> None:
    from tests.test_t024 import _entrada_sintetica

    with pytest.raises(fwd.T024ForwardError, match="mismo mes"):
        fwd.validar_registro(fwd._registro([_entrada_sintetica("v1", CHECKPOINT_2), _entrada_sintetica("v2", date(2026, 12, 2))]))


def test_request_context_solo_en_peticion_exacta(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="request_context"):
        freeze_vintage(["AAPL"], LegacyProvider(), period="1y", interval="1d", root_dir=tmp_path, request_context={"x": 1})


# ---------------------------------------------------------------------------
# Revisión Codex r2: rango revalidado, procedencia en la mirada y contenido del registro
# ---------------------------------------------------------------------------


def _forjar_con_barras_excluidas(tmp_path: Path, cosecha: fwd.CosechaForward) -> None:
    """Reescribe un CSV con barras del 26 al 30 de octubre y rehace hashes y manifiesto (mismo id falsificado)."""

    assert cosecha.data_vintage_id
    vdir = tmp_path / cosecha.data_vintage_id
    raw = _frame(_business_days(date(2026, 10, 19), date(2026, 10, 31)))
    vintage_mod._write_raw_csv(vintage_mod.normalize_raw_history(raw), vdir / "AAPL.csv")
    manifest = json.loads((vdir / "manifest.json").read_text())
    entry = next(a for a in manifest["assets"] if a["symbol"] == "AAPL")
    entry["series_hash"] = vintage_mod.hash_series(raw)
    entry["corporate_actions_hash"] = vintage_mod.hash_actions(raw)
    body = {k: v for k, v in manifest.items() if k not in {"manifest_hash", "data_vintage_id"}}
    nuevo = hash_manifest(body)
    shutil.move(str(vdir), str(tmp_path / nuevo))
    manifest["manifest_hash"] = manifest["data_vintage_id"] = nuevo
    (tmp_path / nuevo / "manifest.json").write_text(vintage_mod._canonical_json(manifest) + "\n")
    object.__setattr__(cosecha, "data_vintage_id", nuevo)


def test_cosecha_forjada_con_dias_excluidos_no_se_registra_ni_se_captura(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cosecha = _congelar(tmp_path)
    _forjar_con_barras_excluidas(tmp_path, cosecha)
    assert cosecha.data_vintage_id
    # Autoconsistente: hashes y petición cuadran, así que la entrada se puede construir…
    entrada = fwd.entrada_registro(cosecha.data_vintage_id, cosecha.peticion, t024_code_sha=CODE_SHA, root_dir=tmp_path)
    vintage = load_vintage(cosecha.data_vintage_id, root_dir=tmp_path)
    # …pero la procedencia revalida el rango de lo cargado.
    with pytest.raises(fwd.T024ForwardError, match="end exclusivo"):
        fwd.exigir_procedencia(entrada, vintage, _Universe(), CODE_SHA)
    monkeypatch.setattr(dec, "verificar_identidad", lambda: CODE_SHA)
    monkeypatch.setattr(fwd, "_universo", lambda: _Universe())
    registro = tmp_path / "registro-forward.json"
    with pytest.raises(fwd.T024ForwardError, match="end exclusivo"):
        fwd.main(["registrar", "--data-vintage-id", cosecha.data_vintage_id, "--checkpoint", "2026-11-03", "--festivo", "2026-11-02",
                  "--registro", str(registro), "--data-dir", str(tmp_path)])
    assert not registro.exists()
    fwd.escribir_registro(registro, fwd.anadir_entrada(fwd.registro_vacio(), entrada))
    monkeypatch.setattr(fwd, "capturar", _Prohibido("capturar"))
    with pytest.raises(fwd.T024ForwardError, match="end exclusivo"):
        fwd.capturar_checkpoint(None, _Universe(), data_vintage_id=cosecha.data_vintage_id, registro_path=registro, root_dir=tmp_path)


def test_rango_cargado_en_la_zona_del_activo_solo_limite_superior() -> None:
    cosecha_ok = VintageLoadFake.de({"A": [date(2026, 10, 23)]})
    fwd.verificar_rango_cargado(cosecha_ok, _Universe(), date(2026, 10, 26))
    with pytest.raises(fwd.T024ForwardError):
        fwd.verificar_rango_cargado(VintageLoadFake.de({"A": [date(2026, 10, 26)]}), _Universe(), date(2026, 10, 26))
    # Barras anteriores a start no son fuga: no se comprueban (la zona del activo puede adelantar un día).
    fwd.verificar_rango_cargado(VintageLoadFake.de({"A": [date(2021, 8, 29)]}), _Universe(), date(2026, 10, 26))


class VintageLoadFake:
    @staticmethod
    def de(rows: dict[str, list[date]]) -> Any:
        from advisor.research.vintage import VintageLoad, build_views

        return VintageLoad("x", {}, {s: build_views(_frame(d)) for s, d in rows.items()})


def _mirada(tmp_path: Path, cosecha: Any, registro: Path, vid: str) -> dict[str, Any]:
    return dict(
        mirada="mirada_1", c_e=CHECKPOINT_1, config=None, universe=_Universe(), cosecha_decisiva=cosecha,
        cosecha_decisiva_id=vid, registro_forward_path=registro, evidence_dir=tmp_path / "ev",
    )


def test_ejecutar_mirada_exige_procedencia_de_la_decisiva_sin_marca(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ejecutar_mirada = dec.ejecutar_mirada
    _blindar_decision(monkeypatch)
    monkeypatch.setattr(dec, "ejecutar_mirada", ejecutar_mirada)
    monkeypatch.setattr(dec, "capturar", _Prohibido("capturar"))
    c1 = _congelar(tmp_path)
    c2 = _congelar(tmp_path, date(2027, 2, 1), ())
    assert c1.data_vintage_id and c2.data_vintage_id
    registro = _registro_en_disco(tmp_path, c1, c2)
    decisiva = load_vintage(c2.data_vintage_id, root_dir=tmp_path)

    monkeypatch.setattr(dec, "verificar_identidad", lambda: "c" * 40)  # otro código vigente
    with pytest.raises(dec.T024DecisionError, match="otro T024_CODE_SHA"):
        dec.ejecutar_mirada(**_mirada(tmp_path, decisiva, registro, c2.data_vintage_id))

    monkeypatch.setattr(dec, "verificar_identidad", lambda: CODE_SHA)
    otra = load_vintage(c1.data_vintage_id, root_dir=tmp_path)
    from dataclasses import replace as dc_replace

    disfrazada = dc_replace(otra, data_vintage_id=c2.data_vintage_id)
    with pytest.raises(dec.T024DecisionError, match="procedencia"):
        dec.ejecutar_mirada(**_mirada(tmp_path, disfrazada, registro, c2.data_vintage_id))
    assert not (tmp_path / "ev").exists()


@pytest.mark.parametrize(
    "campo,valor",
    [("n_symbols", 0), ("provider", "evil"), ("manifest_file_sha256", "x"), ("provider_version", ""), ("data_vintage_id", 1)],
)
def test_registro_valida_el_contenido_de_cada_campo(tmp_path: Path, campo: str, valor: object) -> None:
    cosecha = _congelar(tmp_path)
    assert cosecha.data_vintage_id
    entrada = fwd.entrada_registro(cosecha.data_vintage_id, cosecha.peticion, t024_code_sha=CODE_SHA, root_dir=tmp_path)
    with pytest.raises(fwd.T024ForwardError):
        fwd.validar_registro(fwd._registro([{**entrada, campo: valor}]))



# ---------------------------------------------------------------------------
# Revisión Codex r3: la mirada revalida la cosecha completa contra su entrada
# ---------------------------------------------------------------------------


def test_primera_barra_de_fx_en_londres_no_invalida_la_cosecha(tmp_path: Path) -> None:
    """`EURUSD=X` llega a medianoche de Londres: 2021-08-30 local es 2021-08-29T23:00Z."""

    class Fx:
        def get_raw_history(self, symbol: str, **kwargs: Any) -> pd.DataFrame:
            return _frame([date(2021, 8, 30), date(2021, 8, 31)], tz="Europe/London")

    result = freeze_vintage(["EURUSD=X"], Fx(), interval="1d", start="2021-08-30", end="2026-10-26", root_dir=tmp_path)
    assert result.succeeded == ["EURUSD=X"]
    raw = load_vintage(result.data_vintage_id, root_dir=tmp_path).by_symbol["EURUSD=X"].raw
    assert raw.index[0] == "2021-08-29T23:00:00Z"


def test_mirada_niega_cosecha_parcial_con_registro_canonico_forjado(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ejecutar_mirada = dec.ejecutar_mirada
    _blindar_decision(monkeypatch)
    monkeypatch.setattr(dec, "ejecutar_mirada", ejecutar_mirada)
    monkeypatch.setattr(dec, "capturar", _Prohibido("capturar"))
    monkeypatch.setattr(dec, "verificar_identidad", lambda: CODE_SHA)
    c1 = _congelar(tmp_path)
    parcial = _congelar(tmp_path, date(2027, 2, 1), (), fail=frozenset({"EURUSD=X"}))
    assert c1.data_vintage_id and parcial.data_vintage_id and not parcial.apta
    e1 = fwd.entrada_registro(c1.data_vintage_id, c1.peticion, t024_code_sha=CODE_SHA, root_dir=tmp_path)
    vdir = tmp_path / parcial.data_vintage_id
    forjada = {
        **e1,
        "checkpoint": "2027-02-01",
        "requested_end": "2027-01-25",
        "festivos": [],
        "data_vintage_id": parcial.data_vintage_id,
        "manifest_hash": parcial.data_vintage_id,
        "manifest_file_sha256": hashlib.sha256((vdir / "manifest.json").read_bytes()).hexdigest(),
    }
    registro = _escribir_json(tmp_path / "r.json", fwd._registro([e1, forjada]))
    decisiva = load_vintage(parcial.data_vintage_id, root_dir=tmp_path)
    with pytest.raises(dec.T024DecisionError, match="procedencia"):
        dec.ejecutar_mirada(**_mirada(tmp_path, decisiva, registro, parcial.data_vintage_id))
    assert not (tmp_path / "ev").exists()


@pytest.mark.parametrize("campo,valor", [("manifest_file_sha256", "f" * 64), ("provider_version", "9.9")])
def test_procedencia_cruza_campos_bien_formados_pero_falsos(tmp_path: Path, campo: str, valor: str) -> None:
    cosecha = _congelar(tmp_path)
    assert cosecha.data_vintage_id
    entrada = fwd.entrada_registro(cosecha.data_vintage_id, cosecha.peticion, t024_code_sha=CODE_SHA, root_dir=tmp_path)
    vintage = load_vintage(cosecha.data_vintage_id, root_dir=tmp_path)
    fwd.exigir_procedencia(entrada, vintage, _Universe(), CODE_SHA)
    fwd.validar_registro(fwd._registro([{**entrada, campo: valor}]))  # bien formado: el registro lo admite…
    with pytest.raises(fwd.T024ForwardError):
        fwd.exigir_procedencia({**entrada, campo: valor}, vintage, _Universe(), CODE_SHA)  # …la procedencia no


# ---------------------------------------------------------------------------
# Revisión Codex r4: la cosecha recibida en memoria es la de disco
# ---------------------------------------------------------------------------


def test_procedencia_liga_la_cosecha_en_memoria_a_sus_hashes(tmp_path: Path) -> None:
    from dataclasses import replace as dc_replace

    from advisor.research.vintage import VintageViews

    cosecha = _congelar(tmp_path)
    assert cosecha.data_vintage_id
    entrada = fwd.entrada_registro(cosecha.data_vintage_id, cosecha.peticion, t024_code_sha=CODE_SHA, root_dir=tmp_path)
    vintage = load_vintage(cosecha.data_vintage_id, root_dir=tmp_path)
    fwd.exigir_procedencia(entrada, vintage, _Universe(), CODE_SHA)

    # Manifiesto falso con id «v1»: no reproduce su data_vintage_id.
    falso = dc_replace(vintage, data_vintage_id="v1", manifest={**vintage.manifest, "manifest_hash": "v1", "data_vintage_id": "v1"})
    entrada_falsa = {
        **entrada,
        "data_vintage_id": "v1",
        "manifest_hash": "v1",
        "manifest_file_sha256": hashlib.sha256((vintage_mod._canonical_json(falso.manifest) + "\n").encode()).hexdigest(),
    }
    with pytest.raises(fwd.T024ForwardError, match="no reproduce su data_vintage_id"):
        fwd.exigir_procedencia(entrada_falsa, falso, _Universe(), CODE_SHA)

    # Barras alteradas en memoria.
    views = vintage.by_symbol["AAPL"]
    otras = vintage_mod.build_views(views.raw.assign(Close=views.raw["Close"] * 1.01))
    with pytest.raises(fwd.T024ForwardError, match="no son las del manifiesto"):
        fwd.exigir_procedencia(entrada, dc_replace(vintage, by_symbol={**vintage.by_symbol, "AAPL": otras}), _Universe(), CODE_SHA)

    # Barras intactas, vista de ejecución alterada.
    exec_mod = views.execution_prices.assign(Open=views.execution_prices["Open"] + 1)
    vistas = VintageViews(views.raw, exec_mod, views.signal_prices, views.gap_for_catalyst)
    with pytest.raises(fwd.T024ForwardError, match="vistas cargadas"):
        fwd.exigir_procedencia(entrada, dc_replace(vintage, by_symbol={**vintage.by_symbol, "AAPL": vistas}), _Universe(), CODE_SHA)
