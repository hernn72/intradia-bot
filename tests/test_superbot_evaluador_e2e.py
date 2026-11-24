"""Evaluador final de punta a punta: repositorio, base y cosecha sintéticos, con las puertas reales."""

from __future__ import annotations

import functools
import json
import os
import shutil
import sqlite3
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import pandas as pd
import pytest

from advisor.data.calendars import expected_sessions
from advisor.research.vintage import freeze_vintage
from superbot.ia import contrafactual, madurez
from superbot_lab import evaluacion
from superbot_lab import evaluar as cli
from superbot_lab.evaluador import SeriePrecios, carteras
from tests.test_superbot_evaluador import D0, _caso
from tests.test_superbot_ia import paquete_compra
from tests.test_superbot_ia_madurez import TRAS_CORTE, _base, _decision

T = datetime(2027, 5, 31, 20, 0, tzinfo=timezone.utc)
INICIO = madurez.CORTE.date() - timedelta(days=10)
XETRA = expected_sessions("XETRA", D0, T.date())
H = contrafactual.HORIZONTE_SESIONES
DIVISA = {"XETRA": "EUR", "NASDAQ": "USD", "JPX": "JPY"}


@dataclass(frozen=True)
class C:
    symbol: str
    grupo: str
    sesion: date = XETRA[0]
    salida: Any = 100.0
    market: str = "XETRA"
    estado: str = contrafactual.HORIZONTE
    entrada: Any = 100.0
    final: int = 1
    ejecutable: int | None = 1
    cuando: datetime = TRAS_CORTE
    hasta: date | None = None
    retorno: Any = 0.0


def fx(moneda: str, dia: date) -> float:
    return {"USD": 1.25, "JPY": 160.0}[moneda] * (1 + (dia - INICIO).days / 1000)


def eunl(dia: date) -> tuple[float, float]:
    base = 100 + (dia - INICIO).days / 10
    return base, base + 0.5


def ultima(c: C) -> date:
    return c.hasta or expected_sessions(c.market, c.sesion, c.sesion + timedelta(days=90))[H - 1]


@dataclass
class Proveedor:
    plazas: Mapping[str, str]
    alterar: Mapping[str, Callable[[pd.DataFrame], pd.DataFrame]] = field(default_factory=dict)

    def get_raw_history(self, symbol: str, **_: object) -> pd.DataFrame:
        if symbol.endswith("=X"):
            indice = pd.date_range(INICIO, T.date(), freq="B", tz="Europe/London")
            pares = [(fx(symbol[3:6], d.date()),) * 2 for d in indice]
        else:
            indice = pd.DatetimeIndex(expected_sessions(self.plazas.get(symbol, "XETRA"), INICIO, T.date()))
            pares = [eunl(d.date()) if symbol == "EUNL.DE" else (100.0, 100.0) for d in indice]
        barras = pd.DataFrame({
            "Open": [a for a, _c in pares], "High": [max(p) + 1 for p in pares], "Low": [min(p) / 2 for p in pares],
            "Close": [c for _a, c in pares], "Adj Close": [c for _a, c in pares], "Volume": 1000.0,
            "Dividends": 0.0, "Stock Splits": 0.0,
        }, index=indice)
        return self.alterar.get(symbol, lambda b: b)(barras)


@dataclass
class Lab:
    raiz: Path
    db: Path
    cosechas: Path
    fases: list[int]

    @property
    def apertura(self) -> Path:
        return self.raiz / evaluacion._SALIDA / "apertura.json"

    @property
    def resultado(self) -> Path:
        return self.raiz / evaluacion._SALIDA / "resultado.json"

    def evaluar(self) -> dict[str, Any]:
        return evaluacion.evaluar(self.db, self.cosechas, raiz=self.raiz, reloj=lambda: T + timedelta(days=1))


def base(tmp: Path, casos: Sequence[C], api: float = 0.0) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    reg = _base(tmp)
    for c in casos:
        _decision(reg, c.symbol, c.sesion, c.grupo, c.ejecutable, cuando=c.cuando)
        decision = int(reg.conn.execute("SELECT MAX(id) FROM ia_decision").fetchone()[0])
        datos = {"score": 70.0, "currency": DIVISA[c.market], "niveles": {"stop": 90.0, "target2": 120.0}}
        reg.conn.execute(
            "UPDATE ia_decision SET market=?, cuantitativo=?, target_open=? WHERE id=?",
            (c.market, json.dumps(datos), f"{c.sesion.isoformat()}T08:00:00+00:00", decision),
        )
        reg.conn.execute(
            "INSERT INTO ia_contrafactual (decision_id, symbol, resolucion, target_session, estado, entrada, salida, "
            "hasta_session, retorno_pct, retorno_r, final, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,'x')",
            (decision, c.symbol, c.grupo, c.sesion.isoformat(), c.estado, c.entrada, c.salida, ultima(c).isoformat(),
             c.retorno, c.retorno, c.final),
        )
    pasada = reg.abrir_pasada(T, "activo", "sha")
    if api:
        reg.guardar_llamada(
            pasada_id=pasada, asesor="oportunidad", provider="s", model="m", prompt_version="v", schema_version="1",
            input_hash=paquete_compra().input_hash, input_source_ids="[]", observaciones="[]",
            analysis_timestamp=T.isoformat(), estado="OK", coste_eur=api,
        )
    reg.conn.execute("UPDATE ia_pasada SET status='OK'")
    # Las fechas de escritura son del reloj: fijas, para que la base sea la misma byte a byte.
    for tabla in ("ia_pasada", "ia_llamada"):
        columna = "started_at" if tabla == "ia_pasada" else "created_at"
        reg.conn.execute(f"UPDATE {tabla} SET {columna}=?", (T.isoformat(timespec="seconds"),))
    reg.conn.commit()
    reg.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    reg.close()
    return reg.path


def repo(raiz: Path) -> None:
    for nombre in (*evaluacion._EVALUADOR, evaluacion._CRITERIO.as_posix(), "config.yaml"):
        destino = raiz / nombre
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(nombre, destino)
    subprocess.run(["git", "init", "-q", str(raiz)], check=True)
    comitear(raiz)


def comitear(raiz: Path) -> None:
    fecha = "2027-06-01T00:00:00+00:00"
    identidad = {f"GIT_{quien}_{que}": valor for quien in ("AUTHOR", "COMMITTER") for que, valor in (
        ("NAME", "t"), ("EMAIL", "t@example.invalid"), ("DATE", fecha),
    )}
    for orden in (["add", "."], ["commit", "-qm", "sintético"]):
        subprocess.run(["git", "-C", str(raiz), *orden], check=True, env={**os.environ, **identidad})


def autorizar(raiz: Path, db: Path, cosecha: str, **extra: Any) -> None:
    datos = {**cli.identidades(db, raiz=raiz), "cosecha": cosecha, "autoriza": True, **extra}
    (raiz / evaluacion._AUTORIZACION).write_text(json.dumps(datos), encoding="utf-8")
    comitear(raiz)


def montar(
    tmp: Path, monkeypatch: pytest.MonkeyPatch, casos: Sequence[C], *, api: float = 0.0,
    alterar: Mapping[str, Callable[[pd.DataFrame], pd.DataFrame]] | None = None, sin: Sequence[str] = (),
    series_ausentes: Sequence[str] = (), fin: date = T.date() + timedelta(days=1), replicas: int = 400,
) -> Lab:
    db = base(tmp / "base", casos, api)
    raiz = tmp / "repo"
    repo(raiz)
    plazas = {c.symbol: c.market for c in casos}
    pares = {f"EUR{DIVISA[c.market]}=X" for c in casos if c.market != "XETRA"}
    monkeypatch.setattr(evaluacion, "intervalo_bloques", functools.partial(
        evaluacion.intervalo_bloques, replicas=replicas,
    ))
    vid = freeze_vintage(
        sorted(({*plazas, *pares, "EUNL.DE"}) - set(sin)), Proveedor(plazas, alterar or {}), interval="1d",  # type: ignore[arg-type]
        start=INICIO.isoformat(), end=fin.isoformat(), root_dir=tmp / "cosechas", downloaded_at=T,
    ).data_vintage_id
    autorizar(raiz, db, vid, **({"series_ausentes": list(series_ausentes)} if series_ausentes else {}))
    fases: list[int] = []
    real = evaluacion.abrir_fase
    monkeypatch.setattr(evaluacion, "abrir_fase", lambda ruta, fase: (fases.append(fase), real(ruta, fase))[1])
    monkeypatch.chdir(raiz)
    return Lab(raiz, db, tmp / "cosechas", fases)


def poblacion(aprobada: float = 112.0, descartada: float = 92.0, ruido: float = 0.0, **cambios: Any) -> list[C]:
    """33 por grupo, en tres plazas y tres bloques; el ruido cambia de signo entre bloques de aprobadas."""

    plazas = ("XETRA", "NASDAQ", "JPX")
    casos = []
    for grupo, prefijo, salida in (("COMPRAR", "A", aprobada), ("DESCARTAR", "D", descartada)):
        for i in range(33):
            market = plazas[i % 3]
            desde = expected_sessions(market, D0 + timedelta(days=28 * (i % 4 % 3)), T.date())[0]
            casos.append(C(f"{prefijo}{i}", grupo, desde, salida + (ruido if i % 4 % 3 == 0 else -ruido) * (grupo == "COMPRAR"), market, **cambios))
    return casos


def a_mano(casos: Sequence[C], api: float) -> float:
    """El estimador de §4, escrito aparte y sin el código del evaluador."""

    sesiones_ref = expected_sessions("XETRA", INICIO, T.date())
    grupos: dict[str, list[tuple[float, float]]] = {"COMPRAR": [], "DESCARTAR": []}
    for c in casos:
        moneda, fuera = DIVISA[c.market], ultima(c)
        previo = fuera
        while previo.weekday() > 4:
            previo -= timedelta(days=1)
        dentro_eur = 1.0 if moneda == "EUR" else 1 / fx(moneda, c.sesion)
        fuera_eur = 1.0 if moneda == "EUR" else 1 / fx(moneda, previo)
        riesgo = (c.entrada - 90.0) * dentro_eur
        unidades = min(25.0 / riesgo, 500.0 / (c.entrada * dentro_eur))
        compra, venta = unidades * c.entrada * dentro_eur, unidades * c.salida * fuera_eur
        valor = (venta - compra - 2 - 0.001 * (compra + venta)) / compra
        abre = eunl(next(d for d in sesiones_ref if d >= c.sesion))[0]
        cierra = eunl([d for d in sesiones_ref if d <= fuera][-1])[1]
        grupos[c.grupo].append((valor - (cierra - abre - 0.001 * (abre + cierra)) / abre, compra))
    coste = api / sum(n for _e, n in grupos["COMPRAR"])
    return mean(e for e, _n in grupos["COMPRAR"]) - coste - mean(e for e, _n in grupos["DESCARTAR"])


class TestVeredicto:
    @pytest.mark.parametrize("aprobada,descartada,ruido,esperado", [
        (112.0, 92.0, 0.0, "LA IA APORTA"), (92.0, 112.0, 0.0, "LA IA NO APORTA"), (100.0, 100.0, 9.0, "INCONCLUSO"),
    ])
    def test_tres_plazas_y_estimador_a_mano(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, aprobada: float, descartada: float, ruido: float,
        esperado: str,
    ) -> None:
        casos = poblacion(aprobada, descartada, ruido)
        lab = montar(tmp_path, monkeypatch, casos, api=7.5)
        r = lab.evaluar()
        assert r["veredicto"] == esperado and r["motivo"] is None and r["n"] == {"COMPRAR": 33, "DESCARTAR": 33}
        assert r["estimador"] == pytest.approx(a_mano(casos, 7.5), abs=1e-12)
        assert r["ic"][0] <= r["estimador"] <= r["ic"][1]
        if esperado == "INCONCLUSO":
            assert r["ic"][0] <= 0 < r["ic"][1]
        assert json.loads(lab.resultado.read_text()) == json.loads(json.dumps(r, default=str))
        with pytest.raises(evaluacion.EvaluacionDenegada, match="abierta o realizada"):
            lab.evaluar()

    def test_lo_anterior_al_corte_y_lo_de_dentro_del_episodio_no_entran(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        casos = poblacion()
        antes = C("0_VIEJA", "DESCARTAR", salida=1e6, cuando=madurez.CORTE - timedelta(seconds=1))
        dentro = C("A0", "DESCARTAR", XETRA[5], salida=1e6)
        nunca = C("0_NUNCA", "DESCARTAR", salida=1e6, ejecutable=0)
        r = montar(tmp_path, monkeypatch, [antes, *casos, dentro, nunca]).evaluar()
        assert r["n"] == {"COMPRAR": 33, "DESCARTAR": 33}
        assert not {"0_VIEJA", "0_NUNCA"} & {o["symbol"] for o in r["carteras"]["sin_ia"]["operaciones"]}
        assert r["estimador"] == pytest.approx(a_mano(casos, 0.0), abs=1e-12)

    def test_un_caso_excluido_no_libera_sus_veinte_sesiones(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        casos = poblacion()
        roto = C("R", "COMPRAR", estado=contrafactual.SPLIT_POSTERIOR, entrada=None, salida=None)
        r = montar(tmp_path, monkeypatch, [*casos, roto, C("R", "COMPRAR", XETRA[5], salida=1e6)]).evaluar()
        assert r["n"]["COMPRAR"] == 33 and r["excluidos"]["COMPRAR"] == {contrafactual.SPLIT_POSTERIOR: 1}
        assert r["estimador"] == pytest.approx(a_mano(casos, 0.0), abs=1e-12)

    def test_abre_en_festivo_de_xetra(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        entra = next(d for d in expected_sessions("NASDAQ", D0, T.date()) if d not in XETRA)
        sale = next(d for d in expected_sessions("NASDAQ", entra, T.date()) if d > entra and d not in XETRA)
        casos = poblacion()
        casos[0] = C("A0", "COMPRAR", entra, 130.0, "NASDAQ", estado=contrafactual.STOP, hasta=sale)
        r = montar(tmp_path, monkeypatch, casos).evaluar()
        assert r["estimador"] == pytest.approx(a_mano(casos, 0.0), abs=1e-12)


class TestSinLeerRendimientos:
    @pytest.mark.parametrize("motivo", ["MUESTRA", "DATOS", "BLOQUES", "MUESTRA_TRAS_EXCLUIR"])
    def test_inconcluso_sin_abrir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, motivo: str) -> None:
        veneno = {"salida": "VENENO", "entrada": "VENENO", "retorno": "VENENO"}
        casos = poblacion(0.0, 0.0)
        casos = [C(c.symbol, c.grupo, c.sesion, market=c.market, **veneno) for c in casos]
        if motivo == "MUESTRA":
            casos = [c for c in casos if c.symbol not in {f"A{i}" for i in range(4)}]
        elif motivo == "BLOQUES":
            lejos = expected_sessions("XETRA", D0 + timedelta(days=60), T.date())[0]
            casos = [C(f"{g}{i}", g, XETRA[0] if g == "COMPRAR" else lejos, **veneno)
                     for g in ("COMPRAR", "DESCARTAR") for i in range(30)]
        elif motivo != "MUESTRA":
            malos = 2 if motivo == "DATOS" else 1
            casos = [
                C(c.symbol, c.grupo, c.sesion, market=c.market, estado=contrafactual.DATOS_INCOMPLETOS, **veneno)
                if c.symbol in {f"A{i}" for i in range(malos)} else c
                for c in casos if motivo == "DATOS" or c.symbol not in {"A30", "A31", "A32"}
            ]
        lab = montar(tmp_path, monkeypatch, casos)
        r = lab.evaluar()
        assert r["veredicto"] == "INCONCLUSO" and r["motivo"] == motivo.split("_")[0]
        assert r["ic"] is None and r["estimador"] is None and r["carteras"] is None
        assert not lab.apertura.exists() and lab.resultado.exists() and 2 not in lab.fases
        assert (1 in lab.fases) is (motivo != "MUESTRA")


def quita(desde: date, hasta: date) -> Callable[[pd.DataFrame], pd.DataFrame]:
    return lambda b: b[[not desde <= m.date() <= hasta for m in b.index]]


def con_nan(b: pd.DataFrame) -> pd.DataFrame:
    return b.assign(Close=[float("nan") if m.date() == XETRA[10] else v for m, v in b["Close"].items()])


class TestCobertura:
    @pytest.mark.parametrize("que", [
        "eunl_cola", "eunl_hueco", "eunl_nan", "peticion", "fx_ausente", "fx_cola", "valor_ausente", "valor_tarde",
    ])
    def test_denegada_antes_de_abrir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, que: str) -> None:
        lejos = date(2100, 1, 1)
        alterar: dict[str, Any] = {
            "eunl_cola": {"EUNL.DE": quita(XETRA[-2], lejos)}, "eunl_hueco": {"EUNL.DE": quita(XETRA[9], XETRA[9])},
            "eunl_nan": {"EUNL.DE": con_nan}, "fx_cola": {"EURUSD=X": quita(T.date() - timedelta(days=9), lejos)},
            "valor_tarde": {"A0": quita(INICIO, XETRA[3])},
        }.get(que, {})
        sin = {"fx_ausente": ["EURUSD=X"], "valor_ausente": ["A0"]}.get(que, [])
        fin = T.date() + timedelta(days=1 if que != "peticion" else 2)
        lab = montar(tmp_path, monkeypatch, poblacion(), alterar=alterar, sin=sin, fin=fin)
        with pytest.raises(evaluacion.EvaluacionDenegada):
            lab.evaluar()
        assert not lab.apertura.exists() and not lab.resultado.exists() and 2 not in lab.fases

    def test_valor_ausente_autorizado_no_toca_el_veredicto(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        entero = montar(tmp_path / "1", monkeypatch, poblacion()).evaluar()
        otro_montaje(monkeypatch)
        parte = montar(tmp_path / "2", monkeypatch, poblacion(), sin=["A0"], series_ausentes=["A0"]).evaluar()
        assert parte["series_ausentes"] == ["A0"] and entero["series_ausentes"] == []
        for clave in ("veredicto", "ic", "estimador", "media_grupo"):
            assert parte[clave] == entero[clave]
        simbolos = [{o["symbol"] for o in r["carteras"]["sin_ia"]["operaciones"]} for r in (entero, parte)]
        assert "A0" in simbolos[0] and "A0" not in simbolos[1]

    def test_faltan_casos_por_completar_no_dice_cuales(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        casos = [*poblacion(), C("X", "COMPRAR", estado=contrafactual.ABIERTA, final=0)]
        lab = montar(tmp_path, monkeypatch, casos)
        with pytest.raises(evaluacion.EvaluacionDenegada, match=r"^faltan 1 casos por completar$"):
            lab.evaluar()
        assert not lab.apertura.exists() and 2 not in lab.fases


RAIZ_REAL = Path(__file__).resolve().parents[1]


def otro_montaje(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vuelve al repositorio real, de donde ``repo`` copia, entre dos montajes de una misma prueba."""

    monkeypatch.undo()
    monkeypatch.chdir(RAIZ_REAL)


class TestLoQueNoDecideNoBloquea:
    def test_caida_tras_abrir_no_se_puede_repetir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        lab = montar(tmp_path, monkeypatch, poblacion())

        def rompe(*_a: object) -> None:
            raise RuntimeError("corte")

        monkeypatch.setattr(evaluacion, "exceso_neto", rompe)
        with pytest.raises(RuntimeError, match="corte"):
            lab.evaluar()
        assert lab.apertura.exists() and not lab.resultado.exists()
        with pytest.raises(evaluacion.EvaluacionDenegada, match="abierta o realizada"):
            lab.evaluar()

    def test_la_apertura_queda_escrita_antes_de_leer(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        lab = montar(tmp_path, monkeypatch, poblacion())
        visto: list[bool] = []
        real = evaluacion.abrir_fase

        def espia(ruta: Path, fase: int) -> sqlite3.Connection:
            if fase == 2:
                visto.append(lab.apertura.exists())
            return real(ruta, fase)

        monkeypatch.setattr(evaluacion, "abrir_fase", espia)
        lab.evaluar()
        assert visto and all(visto)

    @pytest.mark.parametrize("pieza", ["carteras", "_ventas_ia", "secundario"])
    def test_un_fallo_secundario_se_publica(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pieza: str,
    ) -> None:
        sano = montar(tmp_path / "1", monkeypatch, poblacion()).evaluar()
        otro_montaje(monkeypatch)
        lab = montar(tmp_path / "2", monkeypatch, poblacion())

        def rompe(*_a: object) -> None:
            raise RuntimeError("roto")

        monkeypatch.setattr(evaluacion, pieza, rompe)
        r = lab.evaluar()
        assert r["carteras" if pieza == "carteras" else "secundario"] == {"error": "RuntimeError: roto"}
        assert all(r[k] == sano[k] for k in ("veredicto", "ic", "estimador")) and lab.resultado.exists()

    def test_un_caso_ajeno_a_la_metrica_ilegible_solo_tumba_las_carteras(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ajena = C("A0", "COMPRAR", XETRA[5], entrada=float("inf"))
        r = montar(tmp_path, monkeypatch, [*poblacion(), ajena]).evaluar()
        assert "error" in r["carteras"] and r["estimador"] == pytest.approx(a_mano(poblacion(), 0.0), abs=1e-12)

    def test_los_precios_de_los_valores_no_mueven_el_veredicto(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        uno = montar(tmp_path / "1", monkeypatch, poblacion()).evaluar()
        otro_montaje(monkeypatch)
        alterar = {"A0": lambda b: b.assign(Close=b["Close"] * 1.5, High=b["High"] * 2)}
        dos = montar(tmp_path / "2", monkeypatch, poblacion(), alterar=alterar).evaluar()
        assert all(uno[k] == dos[k] for k in ("veredicto", "ic", "estimador"))

    def test_si_la_base_cambia_tras_abrir_no_hay_resultado(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        lab = montar(tmp_path, monkeypatch, poblacion())
        real = evaluacion._euros_api

        def cambia(db: Path) -> Any:
            hecho = real(db)
            with sqlite3.connect(db) as conn:
                conn.execute("UPDATE ia_decision SET motivo='otro'")
            return hecho

        monkeypatch.setattr(evaluacion, "_euros_api", cambia)
        with pytest.raises(evaluacion.EvaluacionDenegada, match="después de abrir"):
            lab.evaluar()
        assert lab.apertura.exists() and not lab.resultado.exists()

    def test_si_la_base_cambia_antes_no_se_abre(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        lab = montar(tmp_path, monkeypatch, poblacion())
        real = evaluacion._comprobar_cosecha

        def cambia(*a: Any) -> Any:
            hecho = real(*a)
            with sqlite3.connect(lab.db) as conn:
                conn.execute("UPDATE ia_decision SET motivo='otro'")
            return hecho

        monkeypatch.setattr(evaluacion, "_comprobar_cosecha", cambia)
        with pytest.raises(evaluacion.EvaluacionDenegada, match="base_sha256"):
            lab.evaluar()
        assert not lab.apertura.exists() and 2 not in lab.fases


class TestCarteras:
    D1, D2 = D0 + timedelta(days=1), D0 + timedelta(days=2)

    def test_efectivo_para_una_sola_por_apertura_score_y_simbolo(self) -> None:
        tarde, pronto = (datetime(2026, 11, 25, h, tzinfo=timezone.utc) for h in (14, 8))
        plana = SeriePrecios((D0,), (100.0,), (100.0,))
        abierta = {"salida": None, "sesion_salida": None, "estado": "ABIERTA"}
        for quitados, gana in ((set(), "C"), ({"C"}, "D"), ({"C", "D"}, "E"), ({"C", "D", "E"}, "A")):
            casos = [c for c in (
                _caso(symbol="A", score=99.0, target_open=tarde, **abierta),
                _caso(symbol="E", score=60.0, target_open=pronto, **abierta),
                _caso(symbol="D", score=80.0, target_open=pronto, **abierta),
                _caso(symbol="C", score=80.0, target_open=pronto, **abierta),
            ) if c.symbol not in quitados]
            hecho = carteras(casos, {c.symbol: plana for c in casos}, {}, plana, {D0: 4_400.0}, D0)["con_ia"]
            assert [o.symbol for o in hecho.operaciones] == [gana]

    def test_no_repite_un_valor_en_cartera(self) -> None:
        plana = SeriePrecios((D0, self.D1), (100.0,) * 2, (100.0,) * 2)
        casos = [_caso(decision_id=i, sesion_entrada=d, salida=None, sesion_salida=None, estado="ABIERTA")
                 for i, d in enumerate((D0, self.D1))]
        assert [o.decision_id for o in carteras(casos, {"A": plana}, {}, plana, {}, self.D1)["sin_ia"].operaciones] == [0]

    def test_split_de_un_valor_abierto_y_de_la_referencia(self) -> None:
        # 2:1 el tercer día: la cosecha ya trae reescalado lo anterior.
        valor = SeriePrecios((D0, self.D1, self.D2), (50.0, 50.0, 50.0), (50.0, 50.0, 50.0), ((self.D2, 2.0),))
        referencia = SeriePrecios((D0, self.D1), (50.0, 55.0), (50.0, 55.0), ((self.D1, 2.0),))
        caso = _caso(salida=None, sesion_salida=None, estado="ABIERTA")
        hecho = carteras([caso], {"A": valor}, {}, referencia, {}, self.D1)["sin_ia"]
        assert hecho.patrimonio_final == pytest.approx(5_000 - 1.5)
        assert hecho.exceso_acumulado == pytest.approx(-1.5 - 500 * 0.10)

    def test_sale_en_festivo_de_xetra(self) -> None:
        valor = SeriePrecios((D0, self.D1), (100.0,) * 2, (100.0,) * 2)
        referencia = SeriePrecios((D0,), (50.0,), (50.0,))
        caso = _caso(salida=110.0, sesion_salida=self.D1, estado="HORIZONTE")
        hecho = carteras([caso], {"A": valor}, {}, referencia, {}, self.D1)["sin_ia"]
        assert hecho.patrimonio_final == pytest.approx(5_000 + 50 - 1.5 - 1.55)
        assert hecho.operaciones[0].salida == self.D1


class TestCiclo:
    def test_congelar_identidades_autorizar_evaluar(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        hoy = expected_sessions("XETRA", D0, T.date())[-H:]
        casos = [*poblacion(), C("HOY", "COMPRAR", hoy[0], 112.0)]
        nunca = C("NUNCA", "COMPRAR", estado=contrafactual.NO_EJECUTABLE, entrada=None, salida=None, ejecutable=0)
        assert ultima(casos[-1]) == hoy[-1] == max(XETRA)
        db, raiz = base(tmp_path / "base", [*casos, nunca]), tmp_path / "repo"
        repo(raiz)
        monkeypatch.chdir(raiz)
        monkeypatch.setattr(evaluacion, "_RAIZ", raiz)
        manana = T + timedelta(days=1)
        hecho = cli.congelar(
            db, tmp_path / "cosechas", raiz=raiz, reloj=lambda: manana,
            proveedor=Proveedor({c.symbol: c.market for c in casos}),
        )
        assert hecho["failed"] == {} and hecho["series_ausentes"] == [] and hecho["instante"] == T.isoformat()
        assert "NUNCA" not in (tmp_path / "cosechas" / hecho["cosecha"] / "manifest.json").read_text()
        for orden, codigo in (("identidades", 0), ("puertas", 2)):
            assert cli.main(["--db", str(db), "--cosecha-raiz", str(tmp_path / "cosechas"), orden]) == codigo
        dicho = capsys.readouterr().out
        assert "retorno" not in dicho and "STOP" not in dicho and "HORIZONTE" not in dicho
        autorizar(raiz, db, hecho["cosecha"])
        r = evaluacion.evaluar(db, tmp_path / "cosechas", raiz=raiz, reloj=lambda: manana)
        assert r["n"]["COMPRAR"] == 34 and r["estimador"] == pytest.approx(a_mano(casos, 0.0), abs=1e-12)

    def test_mismo_contenido_mismo_resultado(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        lab = montar(tmp_path / "1", monkeypatch, poblacion(), api=3.0, replicas=10_000)
        lab.evaluar()
        shutil.copytree(lab.raiz, tmp_path / "2", ignore=shutil.ignore_patterns("contrafactual"))
        monkeypatch.chdir(tmp_path / "2")
        evaluacion.evaluar(lab.db, lab.cosechas, raiz=tmp_path / "2", reloj=lambda: T + timedelta(days=3))
        otro = tmp_path / "2" / evaluacion._SALIDA / "resultado.json"
        assert otro.read_bytes() == lab.resultado.read_bytes()

    def test_el_repositorio_no_autoriza_ni_contiene_un_resultado(self) -> None:
        # Hoy no hay autorización: el evaluador se niega sin abrir ninguna base.
        if not (RAIZ_REAL / evaluacion._AUTORIZACION).exists():
            estado = evaluacion.puertas(RAIZ_REAL / "no-existe.db", raiz=RAIZ_REAL)
            assert not estado.permitida and estado.motivo == "falta la autorización"
