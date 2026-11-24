"""Evaluador final de punta a punta: repositorio, base y cosecha sintéticos, con las puertas reales."""

from __future__ import annotations

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
from superbot_lab.evaluador import DatoCompartidoInvalido, SeriePrecios, carteras
from tests.test_superbot_evaluador import D0, _caso
from tests.test_superbot_ia import paquete_compra
from tests.test_superbot_ia_madurez import TRAS_CORTE, _base, _decision

T = datetime(2027, 5, 31, 20, 0, tzinfo=timezone.utc)
INICIO = madurez.CORTE.date() - timedelta(days=10)
XETRA = expected_sessions("XETRA", D0, T.date())
H = contrafactual.HORIZONTE_SESIONES
DIVISA = {"XETRA": "EUR", "NASDAQ": "USD", "JPX": "JPY"}
TABLA_T = {3: 3.182446, 4: 2.776445, 5: 2.570582, 6: 2.446912}


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
        datos = {"score": 70.0, "currency": DIVISA[c.market], "niveles": {"stop": 90.0, "target2": 120.0, "entry_max": 105.0}}
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
    series_ausentes: Mapping[str, str] | None = None, truncados: Sequence[Mapping[str, Any]] = (), fin: date = T.date() + timedelta(days=1),
    crear: Callable[[Path, Sequence[C], float], Path] = base,
) -> Lab:
    db = crear(tmp / "base", casos, api)
    raiz = tmp / "repo"
    repo(raiz)
    plazas = {c.symbol: c.market for c in casos}
    pares = {f"EUR{DIVISA[c.market]}=X" for c in casos if c.market != "XETRA"}
    vid = freeze_vintage(
        sorted(({*plazas, *pares, "EUNL.DE"}) - set(sin)), Proveedor(plazas, alterar or {}), interval="1d",  # type: ignore[arg-type]
        start=INICIO.isoformat(), end=fin.isoformat(), root_dir=tmp / "cosechas", downloaded_at=T,
    ).data_vintage_id
    autorizar(raiz, db, vid, **({"series_ausentes": dict(series_ausentes)} if series_ausentes else {}), **(
        {"episodios_truncados": list(truncados)} if truncados else {}
    ))
    fases: list[int] = []
    real = evaluacion.abrir_fase
    monkeypatch.setattr(evaluacion, "abrir_fase", lambda ruta, fase: (fases.append(fase), real(ruta, fase))[1])
    monkeypatch.chdir(raiz)
    return Lab(raiz, db, tmp / "cosechas", fases)


def poblacion(aprobada: float = 112.0, descartada: float = 92.0, ruido: float = 0.0, **cambios: Any) -> list[C]:
    """36 por grupo, en tres plazas y seis bloques; el ruido cambia de signo entre bloques de aprobadas."""

    plazas = ("XETRA", "NASDAQ", "JPX")
    casos = []
    for grupo, prefijo, salida in (("COMPRAR", "A", aprobada), ("DESCARTAR", "D", descartada)):
        for i in range(36):
            market, bloque = plazas[i % 3], i // 3 % 6
            desde = expected_sessions(market, D0 + timedelta(days=28 * bloque), T.date())[0]
            variacion = (ruido if bloque % 2 else -ruido) * (grupo == "COMPRAR")
            casos.append(C(f"{prefijo}{i}", grupo, desde, salida + variacion, market, **cambios))
    return casos


def efectos(casos: Sequence[C]) -> dict[str, list[tuple[date, float, float]]]:
    """Sesión, exceso neto y nocional de cada caso (§4), escrito aparte y sin el código del evaluador."""

    sesiones_ref = expected_sessions("XETRA", INICIO, T.date())
    grupos: dict[str, list[tuple[date, float, float]]] = {"COMPRAR": [], "DESCARTAR": []}
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
        grupos[c.grupo].append((c.sesion, valor - (cierra - abre - 0.001 * (abre + cierra)) / abre, compra))
    return grupos


def a_mano(casos: Sequence[C], api: float, sin_bloque: int | None = None) -> float:
    grupos = efectos(casos)
    coste = api / sum(n for _s, _e, n in grupos["COMPRAR"])
    medias = [
        mean(e for s, e, _n in grupos[g] if (s - date(2026, 11, 23)).days // 28 != sin_bloque)
        for g in ("COMPRAR", "DESCARTAR")
    ]
    return medias[0] - coste - medias[1]


def intervalo_a_mano(casos: Sequence[C], api: float) -> list[float]:
    centro, bloques = a_mano(casos, api), {(c.sesion - date(2026, 11, 23)).days // 28 for c in casos}
    k = len(bloques)
    error = ((k - 1) / k * sum((a_mano(casos, api, b) - centro) ** 2 for b in bloques)) ** 0.5
    return [centro - TABLA_T[k - 1] * error, centro + TABLA_T[k - 1] * error]


class TestVeredicto:
    @pytest.mark.parametrize("aprobada,descartada,ruido,esperado", [
        (112.0, 92.0, 2.0, "LA IA APORTA"), (92.0, 112.0, 2.0, "LA IA NO APORTA"), (100.0, 100.0, 9.0, "INCONCLUSO"),
    ])
    def test_tres_plazas_y_estimador_a_mano(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, aprobada: float, descartada: float, ruido: float,
        esperado: str,
    ) -> None:
        casos = poblacion(aprobada, descartada, ruido)
        lab = montar(tmp_path, monkeypatch, casos, api=7.5)
        r = lab.evaluar()
        assert r["veredicto"] == esperado and r["motivo"] is None and r["n"] == {"COMPRAR": 36, "DESCARTAR": 36}
        assert r["estimador"] == pytest.approx(a_mano(casos, 7.5), abs=1e-12)
        assert r["ic"] == pytest.approx(intervalo_a_mano(casos, 7.5), rel=1e-6)
        assert r["intervalo"]["bloques"] == 6 and r["ic"][0] <= r["estimador"] <= r["ic"][1]
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
        assert r["n"] == {"COMPRAR": 36, "DESCARTAR": 36}
        assert not {"0_VIEJA", "0_NUNCA"} & {o["symbol"] for o in r["carteras"]["sin_ia"]["operaciones"]}
        assert r["estimador"] == pytest.approx(a_mano(casos, 0.0), abs=1e-12)

    def test_un_caso_excluido_no_libera_sus_veinte_sesiones(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        casos = poblacion()
        roto = C("R", "COMPRAR", estado=contrafactual.SPLIT_POSTERIOR, entrada=None, salida=None)
        r = montar(tmp_path, monkeypatch, [*casos, roto, C("R", "COMPRAR", XETRA[5], salida=1e6)]).evaluar()
        assert r["n"]["COMPRAR"] == 36 and r["excluidos"]["COMPRAR"] == {contrafactual.SPLIT_POSTERIOR: 1}
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
            casos = [c for c in casos if c.symbol not in {f"A{i}" for i in range(7)}]
        elif motivo == "BLOQUES":
            casos = [C(f"{g}{i}", g, XETRA[0] + timedelta(days=28 * (i % 3)), **veneno)
                     for g in ("COMPRAR", "DESCARTAR") for i in range(30)]
        else:
            malos, fuera = (2, 0) if motivo == "DATOS" else (1, 6)
            casos = [
                C(c.symbol, c.grupo, c.sesion, market=c.market, estado=contrafactual.DATOS_INCOMPLETOS, **veneno)
                if c.symbol in {f"A{i}" for i in range(malos)} else c
                for c in casos if c.symbol not in {f"A{35 - i}" for i in range(fuera)}
            ]
        lab = montar(tmp_path, monkeypatch, casos)
        r = lab.evaluar()
        assert r["veredicto"] == "INCONCLUSO" and r["motivo"] == motivo.split("_")[0]
        assert r["ic"] is None and r["estimador"] is None and r["carteras"] is None
        assert not lab.apertura.exists() and lab.resultado.exists() and 2 not in lab.fases
        assert (1 in lab.fases) is (motivo != "MUESTRA")


def declarar(casos: Sequence[C], symbol: str, tipo: str = "SIN_DATOS", **extra: Any) -> dict[str, Any]:
    decision = next(i for i, c in enumerate(casos, start=1) if c.symbol == symbol)
    return {"decision_id": decision, "tipo": tipo, "justificacion": "prueba", "fuente": "prueba", **extra}


def quita(desde: date, hasta: date) -> Callable[[pd.DataFrame], pd.DataFrame]:
    return lambda b: b[[not desde <= m.date() <= hasta for m in b.index]]


def con_nan(b: pd.DataFrame) -> pd.DataFrame:
    return b.assign(Close=[float("nan") if m.date() == XETRA[10] else v for m, v in b["Close"].items()])


class TestCobertura:
    @pytest.mark.parametrize("que", [
        "eunl_cola", "eunl_hueco", "eunl_nan", "eunl_repetida", "peticion", "fx_ausente", "fx_cola", "valor_ausente", "valor_tarde",
    ])
    def test_denegada_antes_de_abrir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, que: str) -> None:
        lejos = date(2100, 1, 1)
        alterar: dict[str, Any] = {
            "eunl_cola": {"EUNL.DE": quita(XETRA[-2], lejos)}, "eunl_hueco": {"EUNL.DE": quita(XETRA[9], XETRA[9])},
            "eunl_nan": {"EUNL.DE": con_nan}, "eunl_repetida": {"EUNL.DE": lambda b: pd.concat([b, b.iloc[[20]]])},
            "fx_cola": {"EURUSD=X": quita(T.date() - timedelta(days=9), lejos)},
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
        parte = montar(
            tmp_path / "2", monkeypatch, poblacion(), sin=["A0"], series_ausentes={"A0": "yfinance ya no lo sirve"},
            truncados=[declarar(poblacion(), "A0")],
        ).evaluar()
        assert list(parte["series_ausentes"]) == ["A0"] and entero["series_ausentes"] == {}
        for clave in ("veredicto", "ic", "estimador", "media_grupo"):
            assert parte[clave] == entero[clave]
        simbolos = [{o["symbol"] for o in r["carteras"]["sin_ia"]["operaciones"]} for r in (entero, parte)]
        assert "A0" in simbolos[0] and "A0" not in simbolos[1]

    def test_una_barra_de_eunl_en_festivo_no_es_una_sesion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        entra = next(d for d in expected_sessions("NASDAQ", D0, T.date()) if d not in XETRA)
        casos = poblacion()
        casos[0] = C("A0", "COMPRAR", entra, 130.0, "NASDAQ")

        def con_barra_falsa(b: pd.DataFrame) -> pd.DataFrame:
            falsa = b.iloc[[0]].assign(Open=500.0, High=500.0, Low=500.0, Close=500.0)
            falsa.index = pd.DatetimeIndex([entra])
            return pd.concat([b, falsa]).sort_index()

        r = montar(tmp_path, monkeypatch, casos, alterar={"EUNL.DE": con_barra_falsa}).evaluar()
        assert r["estimador"] == pytest.approx(a_mano(casos, 0.0), abs=1e-12)

    def test_no_se_puede_autorizar_la_ausencia_de_un_valor_que_esta(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        lab = montar(tmp_path, monkeypatch, poblacion(), series_ausentes={"A0": "prueba"})
        with pytest.raises(evaluacion.EvaluacionDenegada, match="sí tienen datos"):
            lab.evaluar()
        assert not lab.apertura.exists()

    @pytest.mark.parametrize("ausentes", [{"A0": " "}, {"A0": 1}, ["A0"], "A0"])
    def test_una_serie_ausente_exige_justificacion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ausentes: Any,
    ) -> None:
        lab = montar(tmp_path, monkeypatch, poblacion(), sin=["A0"])
        datos = json.loads((lab.raiz / evaluacion._AUTORIZACION).read_text())
        (lab.raiz / evaluacion._AUTORIZACION).write_text(json.dumps({**datos, "series_ausentes": ausentes}))
        comitear(lab.raiz)
        with pytest.raises(evaluacion.EvaluacionDenegada, match="justificación"):
            lab.evaluar()
        assert not lab.apertura.exists()

    @pytest.mark.parametrize("sql,motivo", [
        ("UPDATE ia_llamada SET created_at='2027-05-31T10:00:00'", "coste API"),
        ("UPDATE ia_llamada SET coste_eur='x'", "coste API"), ("UPDATE ia_llamada SET coste_eur=-1", "coste API"),
        ("""UPDATE ia_decision SET cuantitativo='{"score":70,"currency":"EUR","niveles":{"stop":-1}}'""", "cuantitativo"),
        ("UPDATE ia_decision SET target_open='2026-11-25T08:00:00'", "target_open"),
        ("UPDATE ia_contrafactual SET resolucion='COMPRAR'", "no coinciden"),
    ])
    def test_lo_ilegible_se_descubre_antes_de_abrir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sql: str, motivo: str,
    ) -> None:
        def rota(donde: Path, casos: Sequence[C], _api: float) -> Path:
            db = base(donde, casos, 3.0)
            conn = sqlite3.connect(db)
            conn.execute(sql)
            conn.commit()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
            return db

        lab = montar(tmp_path, monkeypatch, poblacion(), crear=rota)
        with pytest.raises(evaluacion.EvaluacionDenegada, match=motivo):
            lab.evaluar()
        assert not lab.apertura.exists() and 2 not in lab.fases

    def test_una_abierta_reciente_no_bloquea_y_va_a_carteras(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        viva = C("0_VIVA", "COMPRAR", XETRA[-3], 101.0, estado=contrafactual.ABIERTA, final=0)
        r = montar(tmp_path, monkeypatch, [*poblacion(), viva]).evaluar()
        abiertas = [o for o in r["carteras"]["con_ia"]["operaciones"] if o["symbol"] == "0_VIVA"]
        assert r["n"]["COMPRAR"] == 36 and [o["estado"] for o in abiertas] == ["ABIERTA"]

    def test_faltan_casos_por_completar_no_dice_cuales(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        casos = [*poblacion(), C("X", "COMPRAR", XETRA[-22], estado=contrafactual.ABIERTA, final=0)]
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
        real = evaluacion._leer_casos

        def cambia(*a: Any) -> Any:
            hecho = real(*a)
            with sqlite3.connect(lab.db) as conn:
                conn.execute("UPDATE ia_decision SET motivo='otro'")
            return hecho

        monkeypatch.setattr(evaluacion, "_leer_casos", cambia)
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


class TestDatosCompartidos:
    def test_fallo_de_divisa_en_carteras_no_deja_publicar_veredicto(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        lab = montar(tmp_path, monkeypatch, poblacion())

        def rompe(*_a: object) -> None:
            raise DatoCompartidoInvalido("falta FX de USD")

        monkeypatch.setattr(evaluacion, "carteras", rompe)
        r = lab.evaluar()
        assert (r["veredicto"], r["motivo"]) == ("INCONCLUSO", "DATOS_COMPARTIDOS")
        assert r["ic"] is None and r["estimador"] is None and r["media_grupo"] == {"COMPRAR": None, "DESCARTAR": None}
        assert lab.apertura.exists() and lab.resultado.exists()

    def test_las_carteras_distinguen_la_divisa_de_la_serie_propia(self) -> None:
        plana = SeriePrecios((D0,), (100.0,), (100.0,))
        abierta = _caso(currency="USD", salida=None, sesion_salida=None, estado="ABIERTA")
        with pytest.raises(DatoCompartidoInvalido):
            carteras([abierta], {"A": plana}, {"USD": ((), ())}, plana, {}, D0)
        vacia = SeriePrecios((), (), ())
        with pytest.raises(ValueError, match="valoración") as error:
            carteras([_caso(salida=None, sesion_salida=None, estado="ABIERTA")], {"A": vacia}, {}, plana, {}, D0)
        assert not isinstance(error.value, DatoCompartidoInvalido)


class TestDejaDeCotizar:
    """A0 (Xetra, primer bloque) deja de tener barras tras su quinta sesión."""

    CORTE_A0 = staticmethod(quita(XETRA[5], date(2100, 1, 1)))

    def casos(self, **a0: Any) -> list[C]:
        casos = poblacion()
        casos[0] = C("A0", "COMPRAR", **{"estado": contrafactual.ABIERTA, "final": 0, "salida": 101.0, **a0})
        return casos

    def montar(self, tmp: Path, monkeypatch: pytest.MonkeyPatch, *truncados: Any, **a0: Any) -> Lab:
        return montar(tmp, monkeypatch, self.casos(**a0), alterar={"A0": self.CORTE_A0}, truncados=truncados)

    def test_sin_declarar_se_niega_y_dice_que_falta(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        lab = self.montar(tmp_path, monkeypatch)
        with pytest.raises(evaluacion.EvaluacionDenegada, match=r"falta declarar en episodios_truncados: A0 \(decisión 1\)"):
            lab.evaluar()
        assert not lab.apertura.exists() and set(lab.fases) == {0}

    def test_congelar_y_puertas_lo_avisan_antes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        lab = self.montar(tmp_path, monkeypatch)
        hecho = cli.congelar(
            lab.db, tmp_path / "otras", raiz=lab.raiz, reloj=lambda: T + timedelta(days=1),
            proveedor=Proveedor({c.symbol: c.market for c in self.casos()}, {"A0": self.CORTE_A0}),
        )
        assert hecho["episodios_truncados"] == [{
            "decision_id": 1, "symbol": "A0", "sesion_entrada": XETRA[0].isoformat(), "sesion_20": XETRA[19].isoformat(),
        }]
        estado = evaluacion.puertas(
            lab.db, raiz=lab.raiz, reloj=lambda: T + timedelta(days=1), cosecha_raiz=lab.cosechas,
        )
        assert not estado.permitida and "A0 (decisión 1)" in str(estado.motivo) and set(lab.fases) == {0}

    def test_la_lista_no_depende_del_desenlace(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        lab = self.montar(tmp_path, monkeypatch, estado=contrafactual.STOP, final=1, hasta=XETRA[2], salida=90.0)
        with pytest.raises(evaluacion.EvaluacionDenegada, match=r"A0 \(decisión 1\)"):
            lab.evaluar()
        assert set(lab.fases) == {0}

    def test_ausencia_de_datos_cuenta_en_el_cinco_por_ciento(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        r = self.montar(tmp_path, monkeypatch, declarar(self.casos(), "A0")).evaluar()
        assert r["excluidos"] == {"COMPRAR": {"DATOS_INCOMPLETOS": 1}, "DESCARTAR": {}} and r["n"]["COMPRAR"] == 35
        assert r["estimador"] == pytest.approx(a_mano(self.casos()[1:], 0.0), abs=1e-12)
        assert r["episodios_truncados"][0]["tipo"] == "SIN_DATOS" and r["con_resultado_de_exclusion"] == []

    @pytest.mark.parametrize("precio", [0.0, 12.5])
    @pytest.mark.parametrize("estado,entrada", [
        (contrafactual.ABIERTA, 100.0), (contrafactual.PENDIENTE, None), (contrafactual.DATOS_INCOMPLETOS, 100.0),
    ])
    def test_la_perdida_de_una_exclusion_entra_en_la_metrica(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, precio: float, estado: str, entrada: float | None,
    ) -> None:
        declarada = declarar(
            self.casos(), "A0", "EXCLUSION", sesion_salida=XETRA[40].isoformat(), precio_entrada=100.0, precio_salida=precio,
        )
        r = self.montar(tmp_path, monkeypatch, declarada, estado=estado, entrada=entrada).evaluar()
        real = [C("A0", "COMPRAR", salida=precio, hasta=XETRA[40]), *self.casos()[1:]]
        assert r["n"]["COMPRAR"] == 36 and r["excluidos"]["COMPRAR"] == {} and r["con_resultado_de_exclusion"] == [1]
        assert r["estimador"] == pytest.approx(a_mano(real, 0.0), abs=1e-12)
        assert r["estimador"] < a_mano(real[1:], 0.0) and "error" not in r["carteras"]
        hecha = [o for o in r["carteras"]["sin_ia"]["operaciones"] if o["symbol"] == "A0"]
        assert [(o["estado"], o["salida"]) for o in hecha] == [("EXCLUSION", XETRA[40])]

    def test_un_stop_anterior_manda_sobre_la_exclusion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        parada = {"estado": contrafactual.STOP, "final": 1, "hasta": XETRA[2], "salida": 90.0}
        declarada = declarar(
            self.casos(), "A0", "EXCLUSION", sesion_salida=XETRA[40].isoformat(), precio_entrada=100.0, precio_salida=0.0,
        )
        r = self.montar(tmp_path, monkeypatch, declarada, **parada).evaluar()
        assert r["estimador"] == pytest.approx(a_mano(self.casos(**parada), 0.0), abs=1e-12)
        assert r["con_resultado_de_exclusion"] == []

    @pytest.mark.parametrize("cambio", [
        {"justificacion": " "}, {"fuente": ""}, {"tipo": "OTRO"}, {"decision_id": 2}, {"decision_id": "x"},
        {"sesion_salida": "2026-11-01"}, {"sesion_salida": "2027-06-01"}, {"precio_salida": -1}, {"precio_entrada": 90.0},
        {"precio_salida": "nan"},
    ])
    def test_declaraciones_invalidas(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cambio: dict[str, Any],
    ) -> None:
        declarada = {**declarar(
            self.casos(), "A0", "EXCLUSION", sesion_salida=XETRA[40].isoformat(), precio_entrada=100.0, precio_salida=1.0,
        ), **cambio}
        lab = self.montar(tmp_path, monkeypatch, declarada)
        with pytest.raises(evaluacion.EvaluacionDenegada, match="episodios_truncados"):
            lab.evaluar()
        assert not lab.apertura.exists() and set(lab.fases) == {0}

    def test_no_se_declara_lo_que_tiene_datos(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        lab = montar(tmp_path, monkeypatch, poblacion(), truncados=[declarar(poblacion(), "A3")])
        with pytest.raises(evaluacion.EvaluacionDenegada, match="con datos completos"):
            lab.evaluar()

    def test_si_sigue_cotizando_es_un_fallo_de_datos_sin_declarar_nada(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        r = montar(tmp_path, monkeypatch, self.casos()).evaluar()
        assert r["excluidos"]["COMPRAR"] == {"DATOS_INCOMPLETOS": 1} and r["episodios_truncados"] == []

    def test_sin_fila_tampoco_bloquea(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def sin_fila(donde: Path, casos: Sequence[C], api: float) -> Path:
            db = base(donde, casos, api)
            conn = sqlite3.connect(db)
            conn.execute("DELETE FROM ia_contrafactual WHERE symbol='A0'")
            conn.commit()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
            return db

        r = montar(tmp_path, monkeypatch, self.casos(), crear=sin_fila).evaluar()
        assert r["excluidos"]["COMPRAR"] == {"DATOS_INCOMPLETOS": 1} and r["omitidos_en_carteras"] == [1]


class TestSinEntrada:
    def extra(self, n: int, **cambios: Any) -> list[C]:
        return [C(f"X{i}", "COMPRAR", XETRA[0], **{
            "estado": contrafactual.SIN_BARRA_DE_ENTRADA, "entrada": None, "salida": None, "ejecutable": None, **cambios,
        }) for i in range(n)]

    def test_la_que_el_gate_habria_rechazado_no_penaliza(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        extra = self.extra(8)
        cara = {c.symbol: lambda b: b.assign(Open=125.0, High=126.0) for c in extra}
        r = montar(tmp_path, monkeypatch, [*poblacion(), *extra], alterar=cara).evaluar()
        assert r["veredicto"] != "INCONCLUSO" and r["excluidos"]["COMPRAR"] == {}

    def test_la_que_falta_por_datos_si(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        sin_barra = {c.symbol: quita(XETRA[0], XETRA[0]) for c in self.extra(2)}
        r = montar(tmp_path, monkeypatch, [*poblacion(), *self.extra(2)], alterar=sin_barra).evaluar()
        assert r["motivo"] == "DATOS" and r["excluidos"]["COMPRAR"] == {contrafactual.SIN_BARRA_DE_ENTRADA: 2}

    def test_las_rechazadas_en_su_momento_no_penalizan(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        rechazadas = self.extra(30, estado=contrafactual.NO_EJECUTABLE, ejecutable=0)
        r = montar(tmp_path, monkeypatch, [*poblacion(), *rechazadas]).evaluar()
        assert r["excluidos"]["COMPRAR"] == {} and r["secundario"]["COMPRAR"]["no_ejecutables"] == 30

    def test_la_apertura_invalidada_despues_si_penaliza(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        invalidadas = self.extra(2, estado=contrafactual.NO_EJECUTABLE, ejecutable=1)
        r = montar(tmp_path, monkeypatch, [*poblacion(), *invalidadas]).evaluar()
        assert r["motivo"] == "DATOS" and r["excluidos"]["COMPRAR"] == {contrafactual.NO_EJECUTABLE: 2}


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
        fases: list[int] = []
        real = evaluacion.abrir_fase
        monkeypatch.setattr(evaluacion, "abrir_fase", lambda ruta, fase: (fases.append(fase), real(ruta, fase))[1])
        hecho = cli.congelar(
            db, tmp_path / "cosechas", raiz=raiz, reloj=lambda: manana,
            proveedor=Proveedor({c.symbol: c.market for c in casos}),
        )
        assert hecho["failed"] == {} and hecho["series_ausentes"] == hecho["episodios_truncados"] == [] and hecho["instante"] == T.isoformat()
        assert "NUNCA" not in (tmp_path / "cosechas" / hecho["cosecha"] / "manifest.json").read_text()
        for orden, codigo in (("identidades", 0), ("puertas", 2)):
            assert cli.main(["--db", str(db), "--cosecha-raiz", str(tmp_path / "cosechas"), orden]) == codigo
        assert set(fases) == {0}  # preparar la evaluación no abre ninguna fase sellada
        dicho = capsys.readouterr().out
        assert "retorno" not in dicho and "STOP" not in dicho and "HORIZONTE" not in dicho
        autorizar(raiz, db, hecho["cosecha"])
        r = evaluacion.evaluar(db, tmp_path / "cosechas", raiz=raiz, reloj=lambda: manana)
        assert r["n"]["COMPRAR"] == 37 and r["estimador"] == pytest.approx(a_mano(casos, 0.0), abs=1e-12)

    def test_mismo_contenido_mismo_resultado(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        lab = montar(tmp_path / "1", monkeypatch, poblacion(), api=3.0)
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
