"""Evaluador final de punta a punta: repositorio, base y cosecha sintéticos, con las puertas reales."""

from __future__ import annotations

import functools
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any, ClassVar

import pandas as pd
import pytest

from advisor.data.calendars import expected_sessions
from advisor.research import vintage
from advisor.research.vintage import freeze_vintage, load_vintage
from superbot.ia import contrafactual, madurez
from superbot_lab import evaluacion
from superbot_lab import evaluar as cli
from superbot_lab.evaluador import DatoCompartidoInvalido, Intervalo, SeriePrecios, carteras
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
    barras: int | None = None


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
            "Open": [a for a, _c in pares], "High": [max(p) + 1 for p in pares], "Low": [min(p) * 0.97 for p in pares],
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
            "hasta_session, retorno_pct, retorno_r, final, sesiones, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'x')",
            (decision, c.symbol, c.grupo, c.sesion.isoformat(), c.estado, c.entrada, c.salida, ultima(c).isoformat(),
             c.retorno, c.retorno, c.final,
             len(expected_sessions(c.market, c.sesion, ultima(c))) if c.barras is None else c.barras),
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


_TEMPORAL = tempfile.TemporaryDirectory(prefix="plantilla-")


@functools.cache
def _plantilla() -> Path:
    raiz = Path(_TEMPORAL.name) / "repo"
    for nombre in (*evaluacion._EVALUADOR, evaluacion._CRITERIO.as_posix(), "config.yaml"):
        destino = raiz / nombre
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(nombre, destino)
    subprocess.run(["git", "init", "-q", str(raiz)], check=True)
    comitear(raiz)
    return raiz


def repo(raiz: Path) -> None:
    shutil.copytree(_plantilla(), raiz)


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


@pytest.fixture(scope="module", autouse=True)
def _huellas_recordadas() -> Iterator[None]:
    """Las huellas de una misma serie se calculan una vez: son las reales, y eran la mitad del tiempo del módulo."""

    def recordar(real: Callable[[pd.DataFrame], str]) -> Callable[[pd.DataFrame], str]:
        vistas: dict[Any, str] = {}

        def huella(serie: pd.DataFrame) -> str:
            clave = (
                tuple(serie.columns), tuple(map(str, serie.dtypes)), str(serie.index.dtype),
                pd.util.hash_pandas_object(serie, index=True).to_numpy().tobytes(),
            )
            if clave not in vistas:
                vistas[clave] = real(serie)
            return vistas[clave]

        return huella

    with pytest.MonkeyPatch.context() as parche:
        for nombre in ("hash_series", "hash_actions"):
            parche.setattr(vintage, nombre, recordar(getattr(vintage, nombre)))
        yield


_COSECHAS: dict[Any, tuple[str, Path]] = {}


@functools.cache
def _cargar(vid: str, *, root_dir: Path) -> Any:
    return load_vintage(vid, root_dir=root_dir)


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
    pedidos = tuple(sorted(({*plazas, *pares, "EUNL.DE"}) - set(sin)))
    clave = (pedidos, tuple(sorted(plazas.items())), fin, tuple(sorted((alterar or {}).items(), key=lambda x: x[0])))
    # Escribir y verificar una cosecha es casi todo el tiempo de la prueba: las de mismo contenido (su
    # identificador es su hash) se comparten, y cada una se verifica una vez.
    if clave not in _COSECHAS:
        vid = freeze_vintage(
            pedidos, Proveedor(plazas, alterar or {}), interval="1d", start=INICIO.isoformat(),  # type: ignore[arg-type]
            end=fin.isoformat(), root_dir=tmp / "cosechas", downloaded_at=T,
        ).data_vintage_id
        _COSECHAS[clave] = (vid, tmp / "cosechas")
    vid, cosechas = _COSECHAS[clave]
    monkeypatch.setattr(evaluacion, "load_vintage", _cargar)
    autorizar(raiz, db, vid, **({"series_ausentes": dict(series_ausentes)} if series_ausentes else {}), **(
        {"episodios_truncados": list(truncados)} if truncados else {}
    ))
    fases: list[int] = []
    real = evaluacion.abrir_fase
    monkeypatch.setattr(evaluacion, "abrir_fase", lambda ruta, fase: (fases.append(fase), real(ruta, fase))[1])
    monkeypatch.chdir(raiz)
    return Lab(raiz, db, cosechas, fases)


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
        r = montar(tmp_path, monkeypatch, casos, alterar={"A0": cae(sale)}).evaluar()
        assert r["estimador"] == pytest.approx(a_mano(casos, 0.0), abs=1e-12)


class TestDesenlaceDesmentido:
    """El recuento de barras no ve una repetida que compensa un hueco: se contrasta con la cosecha (§9.2)."""

    @pytest.mark.parametrize("vista", ["stop_antes", "sin_stop", "stop_otro_dia", "hueco", "dos_precios"])
    def test_es_dato_incompleto_y_no_entra_en_carteras(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, vista: str,
    ) -> None:
        parada = {"estado": contrafactual.STOP, "hasta": XETRA[6], "salida": 90.0}
        a0, alterar = {
            "stop_antes": ({}, cae(XETRA[5])), "sin_stop": (parada, lambda b: b),
            "stop_otro_dia": (parada, cae(XETRA[5])), "hueco": ({}, quita(XETRA[5], XETRA[5])),
            "dos_precios": (parada, cae(XETRA[6])),
        }[vista]
        ausentes = {}
        if vista == "dos_precios":
            def alterar(b: pd.DataFrame) -> pd.DataFrame:
                b = cae(XETRA[6])(b)
                fila = next(i for i, m in enumerate(b.index) if m.date() == XETRA[3])
                return pd.concat([b, b.iloc[[fila]].assign(Low=95.0)])
            ausentes = {"A0": "repite una sesión"}
        casos = poblacion()
        casos[0] = C("A0", "COMPRAR", **a0)  # type: ignore[arg-type]
        # Otro valor con el mismo defecto dentro de un episodio: no está en la métrica y tampoco en carteras.
        dentro = C("A18", "COMPRAR", XETRA[3], salida=1e6)
        r = montar(
            tmp_path, monkeypatch, [*casos, dentro], alterar={"A0": alterar, "A18": cae(XETRA[21])}, series_ausentes=ausentes,
        ).evaluar()
        assert r["excluidos"]["COMPRAR"] == {"DATOS_INCOMPLETOS": 1} and r["n"] == {"COMPRAR": 35, "DESCARTAR": 36}
        assert r["estimador"] == pytest.approx(a_mano(casos[1:], 0.0), abs=1e-12)
        assert r["omitidos_en_carteras"] == [1, 73] and "error" not in r["carteras"]

    def test_una_barra_en_festivo_no_es_un_hueco_posterior(self) -> None:
        from types import SimpleNamespace

        # Serie que acaba en la sesión 3 y una barra suelta en domingo: no hay nada que contradiga lo guardado.
        dias = pd.DatetimeIndex([*XETRA[:3], XETRA[2] + timedelta(days=6 - XETRA[2].weekday() + 7)])
        assert dias[-1].weekday() == 6
        b = pd.DataFrame({"Open": 100.0, "Low": 98.0, "Close": 100.0, "Stock Splits": 0.0}, index=dias)
        vista: Any = SimpleNamespace(by_symbol={"A": SimpleNamespace(raw=b, execution_prices=b)})
        assert evaluacion._contraste(vista, "A", "XETRA", XETRA[0], contrafactual.HORIZONTE, XETRA[19], 90.0) is None

    @pytest.mark.parametrize("fila", [0, 1, 2])
    def test_dos_precios_en_cualquier_sesion_no_se_sostienen(self, fila: int) -> None:
        from types import SimpleNamespace

        b = pd.DataFrame(
            {"Open": 100.0, "Low": [98.0, 98.0, 89.0], "Close": 100.0, "Stock Splits": 0.0}, index=pd.DatetimeIndex(XETRA[:3]),
        )
        for repetida, esperado in ((b.iloc[[fila]].assign(Low=80.0), evaluacion.FALTA), (b.iloc[[fila]], None)):
            doble = pd.concat([b, repetida]).sort_index()
            vista: Any = SimpleNamespace(by_symbol={"A": SimpleNamespace(raw=doble, execution_prices=doble)})
            assert evaluacion._contraste(
                vista, "A", "XETRA", XETRA[0], contrafactual.STOP, XETRA[2], 90.0,
            ) == esperado

    def test_con_menos_de_veinticinco_sesiones_espera(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        tarde = C("TARDE", "COMPRAR", XETRA[-22])
        lab = montar(tmp_path, monkeypatch, [*poblacion(), tarde], alterar={"TARDE": cae(XETRA[-15])})
        with pytest.raises(evaluacion.EvaluacionDenegada, match="faltan 1 casos"):
            lab.evaluar()
        assert not lab.apertura.exists() and 2 not in lab.fases

    def test_un_split_posterior_no_lo_desmiente(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def partido(b: pd.DataFrame) -> pd.DataFrame:
            b = cae(XETRA[6])(b)
            precios = ["Open", "High", "Low", "Close", "Adj Close"]
            b[precios] = b[precios] / 4
            b.loc[[m.date() == XETRA[40] for m in b.index], "Stock Splits"] = 4.0
            return b

        casos = poblacion()
        casos[0] = C("A0", "COMPRAR", estado=contrafactual.STOP, hasta=XETRA[6], salida=90.0)
        r = montar(tmp_path, monkeypatch, casos, alterar={"A0": partido}).evaluar()
        assert r["estimador"] == pytest.approx(a_mano(casos, 0.0), abs=1e-12) and r["excluidos"]["COMPRAR"] == {}

    @pytest.mark.parametrize("minimo,desmentido", [(90.0, False), (90.008, False), (90.02, True), (80.0, False)])
    def test_el_stop_lleva_holgura(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, minimo: float, desmentido: bool,
    ) -> None:
        casos = poblacion()
        casos[0] = C("A0", "COMPRAR", estado=contrafactual.STOP, hasta=XETRA[6], salida=90.0)
        r = montar(tmp_path, monkeypatch, casos, alterar={"A0": cae(XETRA[6], minimo)}).evaluar()
        assert r["excluidos"]["COMPRAR"] == ({"DATOS_INCOMPLETOS": 1} if desmentido else {})

    def test_lo_que_escribe_produccion_con_las_mismas_barras_nunca_se_desmiente(self) -> None:
        """``simular`` de producción y la comprobación recorren igual una serie completa."""

        import random
        from types import SimpleNamespace

        azar, estados = random.Random(7), set()
        for _ in range(60):
            cierres, precio = [], 100.0
            for _dia in XETRA[:30]:
                precio *= 1 + azar.uniform(-0.03, 0.028)
                cierres.append(precio)
            b = pd.DataFrame({
                "Open": [100.0, *cierres[:-1]], "Low": [c * 0.985 for c in cierres], "Close": cierres, "Stock Splits": 0.0,
            }, index=pd.DatetimeIndex(XETRA[:30]))
            b["Low"] = b[["Open", "Low"]].min(axis=1)
            niveles = {"stop": 90.0, "target2": 120.0, "entry_max": 105.0}
            d = contrafactual.simular(niveles, contrafactual.barras_de(b, "XETRA"), XETRA[0])
            # Con las sesiones oficiales (D-90), lo mismo.
            assert contrafactual.simular_en_calendario(
                niveles, contrafactual.barras_de(b, "XETRA"), XETRA[0], XETRA[:30],
            ) == d
            estados.add(d.estado)
            vista: Any = SimpleNamespace(by_symbol={"A": SimpleNamespace(raw=b, execution_prices=b)})
            assert d.hasta_session is not None
            assert evaluacion._contraste(vista, "A", "XETRA", XETRA[0], d.estado, d.hasta_session, 90.0) is None
            # El caso de Codex: una sesión omitida y la anterior repetida dan 20 barras y otra fecha o estado.
            if d.estado == contrafactual.STOP and d.sesiones > 3 and d.hasta_session < XETRA[19]:
                i = d.sesiones - 1
                roto = pd.concat([b.iloc[:i], b.iloc[[i - 1]], b.iloc[i + 1:]])
                malo = contrafactual.simular(niveles, contrafactual.barras_de(roto, "XETRA"), XETRA[0])
                assert malo.hasta_session is not None
                assert evaluacion._contraste(vista, "A", "XETRA", XETRA[0], malo.estado, malo.hasta_session, 90.0)
                assert contrafactual.simular_en_calendario(
                    niveles, contrafactual.barras_de(roto, "XETRA"), XETRA[0], XETRA[:24],
                ).estado == contrafactual.DATOS_INCOMPLETOS
        assert estados == {contrafactual.STOP, contrafactual.HORIZONTE}


class TestExclusionSinEntradaVista:
    """El bot no llegó a ver la apertura y el valor dejó de cotizar: la pérdida no se descarta (§9.2)."""

    def montar(
        self, tmp: Path, monkeypatch: pytest.MonkeyPatch, *, sin: Sequence[str] = (), otros: Sequence[C] = (),
        tipo: str = "EXCLUSION", corte: Any = None, **cambios: Any,
    ) -> Lab:
        casos = [*poblacion(), C(
            "X", "COMPRAR", market="NASDAQ", sesion=XETRA[2], estado=contrafactual.SIN_BARRA_DE_ENTRADA, entrada=None,
            salida=None, ejecutable=None,
        ), *otros]
        datos = {"sesion_salida": XETRA[10].isoformat(), "precio_entrada": 100.0, "precio_salida": 2.0}
        declarada = declarar(casos, "X", tipo, **({**datos, **cambios} if tipo == "EXCLUSION" else {}))
        self.casos = casos
        return montar(
            tmp, monkeypatch, casos, sin=sin, truncados=[declarada],
            alterar={"X": corte or quita(XETRA[8], date(2100, 1, 1))},
        )

    @pytest.mark.parametrize("sin", [(), ("X",)])
    def test_entra_con_su_perdida(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sin: Sequence[str]) -> None:
        r = self.montar(tmp_path, monkeypatch, sin=sin).evaluar()
        real = [*poblacion(), C("X", "COMPRAR", XETRA[2], 2.0, "NASDAQ", hasta=XETRA[10])]
        assert r["n"]["COMPRAR"] == 37 and r["excluidos"]["COMPRAR"] == {} and r["con_resultado_de_exclusion"] == [73]
        assert r["estimador"] == pytest.approx(a_mano(real, 0.0), abs=1e-12)
        assert "error" not in r["carteras"]
        # Sin serie no hay con qué valorarla: se omite igual en las dos carteras y se publica.
        assert r["omitidos_en_carteras"] == ([73] if sin else [])

    def test_una_serie_que_empieza_tarde_se_omite_en_carteras(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        r = self.montar(
            tmp_path, monkeypatch, corte=lambda b: b[[XETRA[4] <= m.date() <= XETRA[7] for m in b.index]],
        ).evaluar()
        assert "error" not in r["carteras"] and r["omitidos_en_carteras"] == [73]
        assert r["con_resultado_de_exclusion"] == [73] and r["n"]["COMPRAR"] == 37

    def test_sin_datos_cuenta_en_el_cinco_por_ciento(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        r = self.montar(tmp_path, monkeypatch, tipo="SIN_DATOS").evaluar()
        assert r["excluidos"]["COMPRAR"] == {"SIN_BARRA_DE_ENTRADA": 1} and r["n"]["COMPRAR"] == 36

    @pytest.mark.parametrize("cambios", [
        {"precio_entrada": 106.0}, {"precio_entrada": 89.0}, {"precio_entrada": 101.0}, {"sesion_salida": "2026-11-29"},
    ])
    def test_entrada_que_el_gate_o_la_cosecha_no_admiten(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cambios: dict[str, Any],
    ) -> None:
        lab = self.montar(tmp_path, monkeypatch, **cambios)
        with pytest.raises(evaluacion.EvaluacionDenegada, match="episodios_truncados ilegible"):
            lab.evaluar()
        assert not lab.apertura.exists() and set(lab.fases) == {0}

    def test_sin_serie_la_entrada_declarada_tambien_pasa_por_el_gate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        with pytest.raises(evaluacion.EvaluacionDenegada, match="episodios_truncados ilegible"):
            self.montar(tmp_path, monkeypatch, sin=["X"], precio_entrada=106.0).evaluar()

    def test_no_cuenta_dos_veces_el_mismo_episodio(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Cuatro sesiones después el bot sí entró en el mismo valor: ese episodio es el que se declara.
        otro = C("X", "COMPRAR", XETRA[6], market="NASDAQ", estado=contrafactual.ABIERTA, final=0)
        with pytest.raises(evaluacion.EvaluacionDenegada, match="episodios_truncados ilegible"):
            self.montar(tmp_path, monkeypatch, otros=[otro]).evaluar()

    def test_lo_que_cae_dentro_de_su_episodio_se_ignora(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        nada = {"estado": contrafactual.SIN_BARRA_DE_ENTRADA, "entrada": None, "salida": None, "ejecutable": None}
        dentro = C("X", "DESCARTAR", XETRA[5], market="NASDAQ", **nada)  # type: ignore[arg-type]
        lab = self.montar(tmp_path, monkeypatch, otros=[dentro])
        r = lab.evaluar()
        assert r["excluidos"] == {"COMPRAR": {}, "DESCARTAR": {}} and r["n"] == {"COMPRAR": 37, "DESCARTAR": 36}
        assert [d["decision_id"] for d in r["episodios_truncados"]] == [73]

    @pytest.mark.parametrize("tipo", ["SIN_DATOS", "EXCLUSION"])
    def test_declarar_la_ignorada_solo_vale_como_sin_datos(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tipo: str,
    ) -> None:
        nada = {"estado": contrafactual.SIN_BARRA_DE_ENTRADA, "entrada": None, "salida": None, "ejecutable": None}
        dentro = C("X", "DESCARTAR", XETRA[5], market="NASDAQ", **nada)  # type: ignore[arg-type]
        lab = self.montar(tmp_path, monkeypatch, otros=[dentro])
        datos = {"sesion_salida": XETRA[10].isoformat(), "precio_entrada": 100.0, "precio_salida": 2.0}
        dos = [
            declarar(self.casos, "X", "EXCLUSION", **datos),
            {**declarar(self.casos, "X", tipo, **datos), "decision_id": 74},
        ]
        autorizar(lab.raiz, lab.db, next(iter(lab.cosechas.iterdir())).name, episodios_truncados=dos)
        if tipo == "EXCLUSION":
            with pytest.raises(evaluacion.EvaluacionDenegada, match="episodios_truncados"):
                lab.evaluar()
        else:
            assert lab.evaluar()["excluidos"] == {"COMPRAR": {}, "DESCARTAR": {}}

    def test_si_el_gate_la_habria_rechazado_no_hay_que_declarar_nada(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def cara(b: pd.DataFrame) -> pd.DataFrame:
            return quita(XETRA[8], date(2100, 1, 1))(b.assign(Open=110.0, High=111.0))

        lab = self.montar(tmp_path, monkeypatch, corte=cara)
        with pytest.raises(evaluacion.EvaluacionDenegada, match="episodios_truncados"):
            lab.evaluar()
        autorizar(lab.raiz, lab.db, next(iter(lab.cosechas.iterdir())).name)
        r = lab.evaluar()
        assert r["excluidos"]["COMPRAR"] == {} and r["n"]["COMPRAR"] == 36

    @pytest.mark.parametrize("apertura", [float("nan"), 0.0])
    def test_una_apertura_vacia_no_es_un_rechazo_del_gate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, apertura: float,
    ) -> None:
        def vacia(b: pd.DataFrame) -> pd.DataFrame:
            return b.assign(Open=[apertura if m.date() == XETRA[2] else v for m, v in zip(b.index, b["Open"])])

        lab = self.montar(tmp_path, monkeypatch, corte=vacia)
        autorizar(lab.raiz, lab.db, next(iter(lab.cosechas.iterdir())).name)
        assert lab.evaluar()["excluidos"]["COMPRAR"] == {"SIN_BARRA_DE_ENTRADA": 1}

    def test_congelar_descarga_su_serie_y_su_divisa(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        solo_xetra = [C(f"{g}{i}", g, XETRA[0] + timedelta(days=28 * (i % 5))) for g in ("COMPRAR", "DESCARTAR") for i in range(32)]
        casos = [*solo_xetra, C("X", "COMPRAR", market="NASDAQ", ejecutable=None, estado="PENDIENTE", final=0, entrada=None, salida=None)]
        lab = montar(tmp_path, monkeypatch, casos)
        hecho = cli.congelar(
            lab.db, tmp_path / "otras", raiz=lab.raiz, reloj=lambda: T + timedelta(days=1),
            proveedor=Proveedor({c.symbol: c.market for c in casos}),
        )
        assert {"X", "EURUSD=X"} <= set(load_vintage(hecho["cosecha"], root_dir=tmp_path / "otras").by_symbol)
        assert hecho["episodios_truncados"] == []


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


def test_sin_variacion_entre_bloques_tambien_vigila_la_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    casos = [C(f"{g}{i}", g, XETRA[0] + timedelta(days=28 * (i % 4)), salida=100.0)
             for g in ("COMPRAR", "DESCARTAR") for i in range(32)]
    monkeypatch.setattr(evaluacion, "intervalo_jackknife", lambda *_a: Intervalo(None, None, 4, None))
    lab = montar(tmp_path, monkeypatch, casos)
    original = evaluacion._leer_casos

    def toca(*args: Any) -> Any:
        hecho = original(*args)
        conn = sqlite3.connect(lab.db)
        conn.execute("CREATE TABLE intrusa(x)")
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        return hecho

    monkeypatch.setattr(evaluacion, "_leer_casos", toca)
    with pytest.raises(evaluacion.EvaluacionDenegada, match="la base cambió"):
        lab.evaluar()
    assert lab.apertura.exists() and not lab.resultado.exists()


def cae(dia: date, minimo: float = 89.0) -> Callable[[pd.DataFrame], pd.DataFrame]:
    return lambda b: b.assign(Low=[minimo if m.date() == dia else v for m, v in zip(b.index, b["Low"])])


def declarar(casos: Sequence[C], symbol: str, tipo: str = "SIN_DATOS", **extra: Any) -> dict[str, Any]:
    decision = next(i for i, c in enumerate(casos, start=1) if c.symbol == symbol)
    return {"decision_id": decision, "tipo": tipo, "justificacion": "prueba", "fuente": "prueba", **extra}


def quita(desde: date, hasta: date) -> Callable[[pd.DataFrame], pd.DataFrame]:
    return lambda b: b[[not desde <= m.date() <= hasta for m in b.index]]


def con_nan(b: pd.DataFrame) -> pd.DataFrame:
    return b.assign(Close=[float("nan") if m.date() == XETRA[10] else v for m, v in b["Close"].items()])


class TestCobertura:
    @pytest.mark.parametrize("que", [
        "eunl_cola", "eunl_hueco", "eunl_nan", "eunl_repetida", "peticion", "fx_ausente", "fx_cola", "fx_roto", "valor_ausente", "valor_tarde",
    ])
    def test_denegada_antes_de_abrir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, que: str) -> None:
        lejos = date(2100, 1, 1)
        alterar: dict[str, Any] = {
            "eunl_cola": {"EUNL.DE": quita(XETRA[-2], lejos)}, "eunl_hueco": {"EUNL.DE": quita(XETRA[9], XETRA[9])},
            "eunl_nan": {"EUNL.DE": con_nan}, "eunl_repetida": {"EUNL.DE": lambda b: pd.concat([b, b.iloc[[20]]])},
            "fx_cola": {"EURUSD=X": quita(T.date() - timedelta(days=9), lejos)},
            "fx_roto": {"EURUSD=X": lambda b: b.assign(Open=1e-320, High=1e-320, Low=1e-320, Close=1e-320)},
            "valor_tarde": {"A0": quita(INICIO, XETRA[3])},
        }.get(que, {})
        sin = {"fx_ausente": ["EURUSD=X"], "valor_ausente": ["A0"]}.get(que, [])
        fin = T.date() + timedelta(days=1 if que != "peticion" else 2)
        lab = montar(tmp_path, monkeypatch, poblacion(), alterar=alterar, sin=sin, fin=fin)
        with pytest.raises(evaluacion.EvaluacionDenegada):
            lab.evaluar()
        assert not lab.apertura.exists() and not lab.resultado.exists() and 2 not in lab.fases

    def test_serie_tardia_autorizada_no_toca_el_veredicto(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        entero = montar(tmp_path / "1", monkeypatch, poblacion()).evaluar()
        otro_montaje(monkeypatch)
        parte = montar(
            tmp_path / "2", monkeypatch, poblacion(), series_ausentes={"A0": "yfinance ya no sirve su principio"},
            alterar={"A0": lambda b: quita(INICIO, XETRA[2])(b)},
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

    @pytest.mark.parametrize("roto", ["falta", "apertura", "cierre"])
    def test_un_hueco_de_eunl_se_justifica_y_se_usa_la_sesion_contigua(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, roto: str,
    ) -> None:
        casos = poblacion()
        entra = casos[0].sesion
        columna = {"apertura": "Open", "cierre": "Close"}.get(roto)
        altera = quita(entra, entra) if columna is None else (lambda b: b.assign(
            **{columna: [0.0 if m.date() == entra else v for m, v in zip(b.index, b[columna])]},
        ))
        lab = montar(tmp_path, monkeypatch, casos, alterar={"EUNL.DE": altera})
        with pytest.raises(evaluacion.EvaluacionDenegada, match=r"EUNL\.DE sin declarar"):
            lab.evaluar()
        cosecha = next(iter(lab.cosechas.iterdir())).name
        for mala in ({entra.isoformat(): " "}, {"ayer": "x"}, {entra.isoformat(): "x", XETRA[9].isoformat(): "x"}, [entra.isoformat()]):
            autorizar(lab.raiz, lab.db, cosecha, referencia_ausente=mala)
            with pytest.raises(evaluacion.EvaluacionDenegada, match="referencia_ausente"):
                lab.evaluar()
        assert not lab.apertura.exists() and set(lab.fases) == {0}
        autorizar(lab.raiz, lab.db, cosecha, referencia_ausente={entra.isoformat(): "el proveedor no la sirve"})
        r = lab.evaluar()
        assert r["referencia_ausente"] == {entra.isoformat(): "el proveedor no la sirve"}
        # Con la primera apertura posterior, como en un festivo de Xetra (§4).
        todas = expected_sessions
        with monkeypatch.context() as parche:
            parche.setattr(sys.modules[__name__], "expected_sessions", lambda m, a, b: [
                d for d in todas(m, a, b) if m != "XETRA" or a != INICIO or d != entra
            ])
            assert r["estimador"] == pytest.approx(a_mano(casos, 0.0), abs=1e-12)

    @pytest.mark.parametrize("dias,denegada", [((9, 10, 11), False), ((9, 10, 11, 12), True), ((9, 10, 12, 13), False)])
    def test_un_hueco_largo_de_eunl_se_deniega(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dias: tuple[int, ...], denegada: bool,
    ) -> None:
        fuera = {XETRA[i] for i in dias}
        lab = montar(
            tmp_path, monkeypatch, poblacion(), alterar={"EUNL.DE": lambda b: b[[m.date() not in fuera for m in b.index]]},
        )
        autorizar(
            lab.raiz, lab.db, next(iter(lab.cosechas.iterdir())).name, referencia_ausente={d.isoformat(): "x" for d in fuera},
        )
        if denegada:
            with pytest.raises(evaluacion.EvaluacionDenegada, match="más de 3 sesiones seguidas"):
                lab.evaluar()
            assert not lab.apertura.exists()
        else:
            assert len(lab.evaluar()["referencia_ausente"]) == len(dias)

    @pytest.mark.parametrize("valor,denegada", [(10.0, True), (None, False)])
    def test_dos_cambios_para_el_mismo_dia(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, valor: float | None, denegada: bool,
    ) -> None:
        def repetido(b: pd.DataFrame) -> pd.DataFrame:
            fila = next(i for i, m in enumerate(b.index) if m.date() == XETRA[0])
            copia = b.iloc[[fila]]
            return pd.concat([b, copia if valor is None else copia.assign(Open=valor, High=valor, Low=valor, Close=valor)])

        lab = montar(tmp_path, monkeypatch, poblacion(), alterar={"EURUSD=X": repetido})
        if denegada:
            with pytest.raises(evaluacion.EvaluacionDenegada, match="dos valores"):
                lab.evaluar()
            assert not lab.apertura.exists() and set(lab.fases) == {0}
        else:
            assert lab.evaluar()["estimador"] == pytest.approx(a_mano(poblacion(), 0.0), abs=1e-12)

    def test_una_serie_que_empieza_tarde_no_es_una_apertura_retirada(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        tarde = {"A0": quita(INICIO, XETRA[3])}
        r = montar(tmp_path, monkeypatch, poblacion(), alterar=tarde, series_ausentes={"A0": "sin histórico"}).evaluar()
        assert r["excluidos"]["COMPRAR"] == {} and r["aperturas_invalidadas"] == {}
        assert r["estimador"] == pytest.approx(a_mano(poblacion(), 0.0), abs=1e-12)

    def test_un_valor_con_sesiones_repetidas_se_autoriza_fuera_de_carteras(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repetida = {"A0": lambda b: pd.concat([b, b.iloc[[20]].assign(Close=1.0, Low=0.5)])}
        lab = montar(tmp_path, monkeypatch, poblacion(), alterar=repetida)
        with pytest.raises(evaluacion.EvaluacionDenegada, match="repetidas: A0"):
            lab.evaluar()
        autorizar(lab.raiz, lab.db, next(iter(lab.cosechas.iterdir())).name, series_ausentes={"A0": "repite una sesión"})
        # Dos precios para una sesión de su ventana: además, el desenlace guardado no se puede sostener.
        assert lab.evaluar()["estimador"] == pytest.approx(a_mano(poblacion()[1:], 0.0), abs=1e-12)

    @pytest.mark.parametrize("que,esperado", [
        ("tarde", ["A0"]), ("ausente", ["A0"]), ("fx", None), ("eunl", []),
    ])
    def test_congelar_avisa_de_lo_que_evaluar_exigira(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, que: str, esperado: list[str] | None,
    ) -> None:
        lab = montar(tmp_path, monkeypatch, poblacion())
        alterar: dict[str, Any] = {
            "tarde": {"A0": quita(INICIO, XETRA[3])}, "ausente": {"A0": quita(INICIO, date(2100, 1, 1))},
            "fx": {"EURUSD=X": quita(XETRA[30], XETRA[45])}, "eunl": {"EUNL.DE": quita(XETRA[9], XETRA[9])},
        }[que]

        def congela() -> dict[str, Any]:
            return cli.congelar(
                lab.db, tmp_path / "otras", raiz=lab.raiz, reloj=lambda: T + timedelta(days=1),
                proveedor=Proveedor({c.symbol: c.market for c in poblacion()}, alterar),
            )

        if esperado is None:
            with pytest.raises(evaluacion.EvaluacionDenegada):
                congela()
        else:
            hecho = congela()
            assert hecho["series_ausentes"] == esperado
            assert hecho["referencia_ausente"] == ([XETRA[9].isoformat()] if que == "eunl" else [])
        assert set(lab.fases) == {0}

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

    def test_puertas_coincide_con_evaluar_cuando_falta_muestra(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        casos = [c for c in poblacion() if c.symbol not in {f"A{i}" for i in range(7)}]
        lab = montar(tmp_path, monkeypatch, casos, alterar={"EUNL.DE": quita(XETRA[9], XETRA[9])})
        estado = evaluacion.puertas(
            lab.db, raiz=lab.raiz, reloj=lambda: T + timedelta(days=1), cosecha_raiz=lab.cosechas,
        )
        assert estado.motivo is None and not estado.muestra_minima
        assert lab.evaluar()["motivo"] == "MUESTRA"

    def test_lo_excluido_con_entrada_siempre_se_publica_como_omitido(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        casos = poblacion()
        casos[0] = C("A0", "COMPRAR", estado=contrafactual.NO_EJECUTABLE, entrada=None, salida=None)
        r = montar(tmp_path, monkeypatch, casos).evaluar()
        assert r["excluidos"]["COMPRAR"] == {contrafactual.NO_EJECUTABLE: 1} and r["omitidos_en_carteras"] == [1]

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

    def test_una_barra_en_festivo_no_hace_que_siga_cotizando(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def festiva(b: pd.DataFrame) -> pd.DataFrame:
            domingo = next(d for d in (XETRA[40] + timedelta(days=i) for i in range(7)) if d.weekday() == 6)
            fila = b.iloc[[-1]].set_axis(pd.DatetimeIndex([domingo]))
            return pd.concat([self.CORTE_A0(b), fila])

        lab = montar(tmp_path, monkeypatch, self.casos(), alterar={"A0": festiva})
        with pytest.raises(evaluacion.EvaluacionDenegada, match=r"A0 \(decisión 1\)"):
            lab.evaluar()

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
        assert r["omitidos_en_carteras"] == [1]
        for cartera in r["carteras"].values():
            assert "A0" not in {o["symbol"] for o in cartera["operaciones"]}

    @pytest.mark.parametrize("sin,estado,hasta", [
        ((), contrafactual.STOP, XETRA[8]), (("A0",), contrafactual.HORIZONTE, XETRA[19]), ((), contrafactual.STOP, XETRA[5]),
    ])
    def test_un_desenlace_completo_sin_cosecha_es_inconcluso(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sin: Sequence[str], estado: str, hasta: date,
    ) -> None:
        # Contado sería INCONCLUSO y descartado, favorable: ni lo uno ni lo otro (D-89).
        casos = poblacion(102.4, 100.0, 2.0)
        casos[0] = C("A0", "COMPRAR", salida=90.0, estado=estado, hasta=hasta)
        assert intervalo_a_mano(casos[1:], 0.0)[0] > 0
        lab = montar(
            tmp_path, monkeypatch, casos, alterar={"A0": self.CORTE_A0}, sin=sin, truncados=[declarar(casos, "A0")],
            series_ausentes={"A0": "deslistada"} if sin else None,
        )
        r = lab.evaluar()
        assert (r["veredicto"], r["motivo"], r["sin_contraste"]) == ("INCONCLUSO", "SIN_CONTRASTE", [1])
        assert r["n"]["COMPRAR"] == 36 and r["excluidos"]["COMPRAR"] == {} and r["ic"] is None and r["carteras"] is None
        assert not lab.apertura.exists() and 2 not in lab.fases

    def test_si_la_cosecha_llega_hasta_el_desenlace_cuenta(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        casos = poblacion(102.4, 100.0, 2.0)
        casos[0] = C("A0", "COMPRAR", salida=90.0, estado=contrafactual.STOP, hasta=XETRA[4])
        r = montar(
            tmp_path, monkeypatch, casos, alterar={"A0": lambda b: cae(XETRA[4])(self.CORTE_A0(b))},
            truncados=[declarar(casos, "A0")],
        ).evaluar()
        assert r["motivo"] is None and r["n"]["COMPRAR"] == 36 and "sin_contraste" not in r
        assert r["ic"] == pytest.approx(intervalo_a_mano(casos, 0.0), rel=1e-6)

    @pytest.mark.parametrize("precio", [0.0, 12.5])
    @pytest.mark.parametrize("estado,entrada", [
        (contrafactual.ABIERTA, 100.0), (contrafactual.PENDIENTE, None), (contrafactual.DATOS_INCOMPLETOS, 100.0),
        (contrafactual.SIN_BARRA_DE_ENTRADA, None),
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
        r = montar(
            tmp_path, monkeypatch, self.casos(**parada), truncados=[declarada],
            alterar={"A0": lambda b: cae(XETRA[2])(self.CORTE_A0(b))},
        ).evaluar()
        assert r["estimador"] == pytest.approx(a_mano(self.casos(**parada), 0.0), abs=1e-12)
        assert r["con_resultado_de_exclusion"] == []

    def test_una_entrada_retirada_no_tapa_la_exclusion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # El proveedor retira la barra de entrada y además el valor deja de cotizar: falta el dato, no la pérdida.
        r = montar(
            tmp_path, monkeypatch, self.casos(), truncados=[self.excluida()],
            alterar={"A0": lambda b: quita(XETRA[0], XETRA[0])(self.CORTE_A0(b))},
        ).evaluar()
        real = [C("A0", "COMPRAR", salida=0.0, hasta=XETRA[40]), *self.casos()[1:]]
        assert r["estimador"] == pytest.approx(a_mano(real, 0.0), abs=1e-12)
        assert r["con_resultado_de_exclusion"] == [1] and 1 not in r["omitidos_en_carteras"]

    PARADA: ClassVar[dict[str, Any]] = {"estado": contrafactual.STOP, "final": 1, "hasta": XETRA[2], "salida": 90.0}

    def excluida(self) -> dict[str, Any]:
        return declarar(
            self.casos(), "A0", "EXCLUSION", sesion_salida=XETRA[40].isoformat(), precio_entrada=100.0, precio_salida=0.0,
        )

    @pytest.mark.parametrize("defecto", ["ninguno", "sin_entrada", "sin_la_segunda", "entrada_a_cero", "todo_a_cero", "repetida"])
    def test_un_stop_anterior_manda_aunque_a_la_cosecha_le_falten_barras(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defecto: str,
    ) -> None:
        def altera(b: pd.DataFrame) -> pd.DataFrame:
            b = cae(XETRA[2])(self.CORTE_A0(b)).copy()
            dias = [m.date() for m in b.index]
            if defecto == "sin_entrada":
                return quita(XETRA[0], XETRA[0])(b)
            if defecto == "sin_la_segunda":
                return quita(XETRA[1], XETRA[1])(b)
            if defecto == "entrada_a_cero":
                b["Open"] = [0.0 if d == XETRA[0] else v for d, v in zip(dias, b["Open"])]
            if defecto == "todo_a_cero":
                b["Open"] = [0.0 if d >= XETRA[0] else v for d, v in zip(dias, b["Open"])]
            if defecto == "repetida":
                fila = dias.index(XETRA[0])
                return pd.concat([b.iloc[:fila], b.iloc[[fila]].assign(Open=0.0), b.iloc[fila:]])
            return b

        lab = montar(
            tmp_path, monkeypatch, self.casos(**self.PARADA), truncados=[self.excluida()], alterar={"A0": altera},
            series_ausentes={"A0": "repite una sesión"} if defecto == "repetida" else {},
        )
        r = lab.evaluar()
        assert r["estimador"] == pytest.approx(a_mano(self.casos(**self.PARADA), 0.0), abs=1e-12)
        assert r["con_resultado_de_exclusion"] == [] and r["n"]["COMPRAR"] == 36

    @pytest.mark.parametrize("cosecha", ["sin_serie", "acaba_antes", "llega"])
    def test_un_stop_guardado_con_huecos_manda_sobre_la_exclusion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cosecha: str,
    ) -> None:
        parada = {"estado": contrafactual.STOP, "final": 1, "hasta": XETRA[5], "barras": 5, "salida": 90.0}
        corte = quita(XETRA[4] if cosecha == "acaba_antes" else XETRA[8], date(2100, 1, 1))
        r = montar(
            tmp_path, monkeypatch, self.casos(**parada), truncados=[self.excluida()],
            alterar={"A0": lambda b: cae(XETRA[5])(corte(b))}, sin=["A0"] if cosecha == "sin_serie" else [],
            series_ausentes={"A0": "deslistada"} if cosecha == "sin_serie" else {},
        ).evaluar()
        assert r["estimador"] == pytest.approx(a_mano(self.casos(**parada), 0.0), abs=1e-12)
        assert r["con_resultado_de_exclusion"] == [] and r["n"]["COMPRAR"] == 36

    @pytest.mark.parametrize("guardado", [
        {"estado": contrafactual.STOP, "hasta": XETRA[4] + timedelta(days=(5 - XETRA[4].weekday()) % 7), "salida": 90.0},
        {"estado": contrafactual.HORIZONTE, "salida": 130.0, "barras": 19},
    ])
    def test_ni_un_stop_en_festivo_ni_un_horizonte_con_huecos_tapan_la_exclusion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, guardado: dict[str, Any],
    ) -> None:
        r = self.montar(tmp_path, monkeypatch, self.excluida(), final=1, **guardado).evaluar()
        assert r["con_resultado_de_exclusion"] == [1]

    def test_una_entrada_a_cero_es_retirada_tambien_para_un_horizonte(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def ceros(b: pd.DataFrame) -> pd.DataFrame:
            b = self.CORTE_A0(b)
            return b.assign(Open=[0.0 if m.date() >= XETRA[0] else v for m, v in zip(b.index, b["Open"])])

        guardado = {"estado": contrafactual.HORIZONTE, "final": 1, "salida": 130.0}
        r = montar(
            tmp_path, monkeypatch, self.casos(**guardado), truncados=[self.excluida()], alterar={"A0": ceros},
        ).evaluar()
        assert r["aperturas_invalidadas"] == {1: contrafactual.SIN_BARRA_DE_ENTRADA}
        assert r["con_resultado_de_exclusion"] == [1]

    def test_un_horizonte_con_huecos_en_la_cosecha_no_tapa_la_exclusion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Una barra que falta puede esconder un stop: el horizonte guardado no se sostiene, y la exclusión sí.
        guardado = {"estado": contrafactual.HORIZONTE, "final": 1, "salida": 130.0}
        r = montar(
            tmp_path, monkeypatch, self.casos(**guardado), truncados=[self.excluida()],
            alterar={"A0": lambda b: quita(XETRA[1], XETRA[1])(self.CORTE_A0(b))},
        ).evaluar()
        real = [C("A0", "COMPRAR", salida=0.0, hasta=XETRA[40]), *self.casos()[1:]]
        assert r["con_resultado_de_exclusion"] == [1]
        assert r["estimador"] == pytest.approx(a_mano(real, 0.0), abs=1e-12)

    def test_un_stop_que_el_bot_no_vio_tambien_manda(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        for indice, (minimo, apertura, precio) in enumerate(((89.0, 100.0, 90.0), (80.0, 85.0, 85.0))):
            def altera(b: pd.DataFrame, m: float = minimo, a: float = apertura) -> pd.DataFrame:
                b = cae(XETRA[2], m)(self.CORTE_A0(b))
                return b.assign(Open=[a if d.date() == XETRA[2] else v for d, v in zip(b.index, b["Open"])])

            otro_montaje(monkeypatch)
            r = montar(
                tmp_path / str(indice), monkeypatch, self.casos(), truncados=[self.excluida()], alterar={"A0": altera},
            ).evaluar()
            real = [C("A0", "COMPRAR", salida=precio, hasta=XETRA[2]), *self.casos()[1:]]
            assert r["estimador"] == pytest.approx(a_mano(real, 0.0), abs=1e-12)
            assert r["con_resultado_de_exclusion"] == r["exclusiones_con_stop_anterior"] == [1]
            assert r["secundario"]["COMPRAR"]["stops"] == 1
            assert r["secundario"]["COMPRAR"]["media_r"] == pytest.approx((precio - 100.0) / 10.0 / 36)
            hecha = [o for o in r["carteras"]["sin_ia"]["operaciones"] if o["symbol"] == "A0"]
            assert [(o["estado"], o["salida"]) for o in hecha] == [("STOP", XETRA[2])]

    @pytest.mark.parametrize("precios", [
        [(100.0, 89.0)], [(100.0, 90.005)], [(100.0, 89.995)], [(100.0, 89.0), (100.0, 95.0)],
    ])
    def test_un_stop_dudoso_no_desplaza_la_exclusion(
        self, precios: list[tuple[float, float]],
    ) -> None:
        from types import SimpleNamespace

        b = pd.DataFrame(
            {"Open": [100.0, *(a for a, _m in precios)], "Low": [98.0, *(m for _a, m in precios)], "Close": 100.0,
             "Stock Splits": 0.0},
            index=pd.DatetimeIndex([XETRA[0], *[XETRA[1]] * len(precios)]),
        )
        vista: Any = SimpleNamespace(by_symbol={"A": SimpleNamespace(raw=b, execution_prices=b)})
        hecho = evaluacion._stop_en_cosecha(vista, "A", "XETRA", XETRA[0], XETRA[5], 90.0)
        assert hecho == ((XETRA[1], 90.0) if precios == [(100.0, 89.0)] else None)
        assert evaluacion._stop_en_cosecha(vista, "A", "XETRA", XETRA[0], XETRA[0], 90.0) is None

    @pytest.mark.parametrize("valor", [float("nan"), 0.0])
    def test_una_barra_vacia_tras_el_corte_no_es_una_entrada_retirada(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, valor: float,
    ) -> None:
        def vaciada(b: pd.DataFrame) -> pd.DataFrame:
            precios = ["Open", "High", "Low", "Close", "Adj Close"]
            b = quita(XETRA[0], XETRA[0])(b)
            b.loc[[m.date() > XETRA[0] for m in b.index], precios] = valor
            return b

        lab = montar(tmp_path, monkeypatch, self.casos(), alterar={"A0": vaciada}, truncados=[declarar(self.casos(), "A0")])
        assert lab.evaluar()["aperturas_invalidadas"] == {}

    def test_una_apertura_que_el_gate_rechaza_no_la_rescata_una_exclusion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        declarada = declarar(
            self.casos(), "A0", "EXCLUSION", sesion_salida=XETRA[40].isoformat(), precio_entrada=110.0, precio_salida=0.0,
        )
        r = montar(
            tmp_path, monkeypatch, self.casos(), truncados=[declarada],
            alterar={"A0": lambda b: self.CORTE_A0(b).assign(Open=110.0, High=111.0)},
        ).evaluar()
        assert r["excluidos"]["COMPRAR"] == {contrafactual.NO_EJECUTABLE: 1} and r["con_resultado_de_exclusion"] == []

    def test_un_stop_que_la_cosecha_desmiente_no_tapa_la_exclusion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        declarada = declarar(
            self.casos(), "A0", "EXCLUSION", sesion_salida=XETRA[40].isoformat(), precio_entrada=100.0, precio_salida=0.0,
        )
        r = self.montar(
            tmp_path, monkeypatch, declarada, estado=contrafactual.STOP, final=1, hasta=XETRA[2], salida=90.0,
        ).evaluar()
        assert r["con_resultado_de_exclusion"] == [1]
        real = [C("A0", "COMPRAR", salida=0.0, hasta=XETRA[40]), *self.casos()[1:]]
        assert r["estimador"] == pytest.approx(a_mano(real, 0.0), abs=1e-12)

    @pytest.mark.parametrize("cambio", [
        {"justificacion": " "}, {"fuente": ""}, {"tipo": "OTRO"}, {"decision_id": 2}, {"decision_id": "x"},
        {"sesion_salida": "2026-11-01"}, {"sesion_salida": "2027-06-01"}, {"sesion_salida": "2027-01-03"},
        {"sesion_salida": "2027-01-01"}, {"sesion_salida": XETRA[3].isoformat()}, {"precio_salida": -1}, {"precio_entrada": 90.0},
        {"precio_salida": "nan"}, {"precio_entrada": 100.6}, {"precio_entrada": 99.4},
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

    def test_sin_apertura_publica_la_entrada_declarada_tiene_que_superar_el_stop(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        declarada = declarar(
            self.casos(), "A0", "EXCLUSION", sesion_salida=XETRA[40].isoformat(), precio_entrada=90.0, precio_salida=1.0,
        )
        lab = montar(
            tmp_path, monkeypatch, self.casos(), sin=["A0"], series_ausentes={"A0": "deslistada"}, truncados=[declarada],
        )
        with pytest.raises(evaluacion.EvaluacionDenegada, match="episodios_truncados"):
            lab.evaluar()

    def test_la_exclusion_vale_desde_la_ultima_cotizacion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        declarada = {**self.excluida(), "sesion_salida": XETRA[4].isoformat()}
        assert self.montar(tmp_path, monkeypatch, declarada).evaluar()["con_resultado_de_exclusion"] == [1]

    def test_no_se_declara_lo_que_tiene_datos(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        lab = montar(tmp_path, monkeypatch, poblacion(), truncados=[declarar(poblacion(), "A3")])
        with pytest.raises(evaluacion.EvaluacionDenegada, match="con datos completos"):
            lab.evaluar()

    def test_si_sigue_cotizando_es_un_fallo_de_datos_sin_declarar_nada(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        r = montar(tmp_path, monkeypatch, self.casos()).evaluar()
        assert r["excluidos"]["COMPRAR"] == {"DATOS_INCOMPLETOS": 1} and r["episodios_truncados"] == []
        assert r["omitidos_en_carteras"] == [1]

    @pytest.mark.parametrize("hueco", [
        {"estado": contrafactual.HORIZONTE, "final": 1, "hasta": XETRA[20], "barras": 20, "salida": 1e6},
        {"estado": contrafactual.STOP, "final": 1, "hasta": XETRA[9], "barras": 9, "salida": 1e6},
    ])
    def test_un_desenlace_con_huecos_no_entra_en_la_metrica_ni_en_carteras(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hueco: dict[str, Any],
    ) -> None:
        r = montar(tmp_path, monkeypatch, self.casos(**hueco)).evaluar()
        assert r["excluidos"]["COMPRAR"] == {"DATOS_INCOMPLETOS": 1} and r["omitidos_en_carteras"] == [1]
        assert r["estimador"] == pytest.approx(a_mano(self.casos()[1:], 0.0), abs=1e-12)

    def test_manda_la_entrada_guardada_y_se_publica(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        declarada = declarar(
            self.casos(), "A0", "EXCLUSION", sesion_salida=XETRA[40].isoformat(), precio_entrada=100.4, precio_salida=50.0,
        )
        r = self.montar(tmp_path, monkeypatch, declarada).evaluar()
        real = [C("A0", "COMPRAR", salida=50.0, hasta=XETRA[40]), *self.casos()[1:]]
        assert r["entradas_de_exclusiones"] == {1: 100.0}
        assert r["estimador"] == pytest.approx(a_mano(real, 0.0), abs=1e-12)

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

    def test_el_gate_se_comprueba_en_la_escala_anterior_al_split(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def con_split(b: pd.DataFrame) -> pd.DataFrame:  # 2:1 posterior: la cosecha trae la mitad de 100
            return b.assign(**{"Open": 50.0, "Close": 50.0, "High": 51.0, "Low": 49.0, "Stock Splits": [
                2.0 if m.date() == XETRA[9] else 0.0 for m in b.index
            ]})

        partidas = {c.symbol: con_split for c in self.extra(2)}
        r = montar(tmp_path, monkeypatch, [*poblacion(), *self.extra(2)], alterar=partidas).evaluar()
        assert r["motivo"] == "DATOS" and r["excluidos"]["COMPRAR"] == {contrafactual.SIN_BARRA_DE_ENTRADA: 2}

    def test_las_rechazadas_en_su_momento_no_penalizan(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        rechazadas = self.extra(30, estado=contrafactual.NO_EJECUTABLE, ejecutable=0)
        r = montar(tmp_path, monkeypatch, [*poblacion(), *rechazadas]).evaluar()
        assert r["excluidos"]["COMPRAR"] == {} and r["secundario"]["COMPRAR"]["no_ejecutables"] == 30

    @pytest.mark.parametrize("defecto,estado_final", [
        (quita(XETRA[0], XETRA[0]), contrafactual.SIN_BARRA_DE_ENTRADA),
        (lambda b: b.assign(Open=125.0, High=126.0), contrafactual.NO_EJECUTABLE),
    ])
    @pytest.mark.parametrize("desenlace", [
        {"estado": contrafactual.HORIZONTE}, {"estado": contrafactual.STOP, "hasta": XETRA[2]},
        {"estado": contrafactual.ABIERTA, "final": 0},
    ])
    def test_la_invalidada_tras_ser_definitiva_penaliza_igual_sea_cual_sea_su_desenlace(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defecto: Any, estado_final: str, desenlace: dict[str, Any],
    ) -> None:
        malas = [C(f"X{i}", "COMPRAR", XETRA[0], 1e6, **desenlace) for i in range(2)]
        roto = {c.symbol: defecto for c in malas}
        dos = montar(tmp_path / "1", monkeypatch, [*poblacion(), *malas], alterar=roto).evaluar()
        assert dos["motivo"] == "DATOS" and dos["excluidos"]["COMPRAR"] == {estado_final: 2}
        otro_montaje(monkeypatch)
        una = montar(tmp_path / "2", monkeypatch, [*poblacion(), malas[0]], alterar={"X0": defecto}).evaluar()
        assert una["excluidos"]["COMPRAR"] == {estado_final: 1} and una["aperturas_invalidadas"] == {73: estado_final}
        assert una["omitidos_en_carteras"] == [73]
        assert una["estimador"] == pytest.approx(a_mano(poblacion(), 0.0), abs=1e-12)

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

    @pytest.mark.parametrize("fin", [0, 1, 2])
    def test_un_split_no_crea_ni_destruye_patrimonio(self, fin: int) -> None:
        # 2:1 el segundo día y 5:1 el tercero, precio económico plano en 100: la cosecha trae todo a 10.
        dias = (D0, self.D1, self.D2)
        valor = SeriePrecios(dias, (10.0,) * 3, (10.0,) * 3, ((self.D1, 2.0), (self.D2, 5.0)))
        plana = SeriePrecios(dias, (50.0,) * 3, (50.0,) * 3)
        caso = _caso(salida=None, sesion_salida=None, estado="ABIERTA")
        hecho = carteras([caso], {"A": valor}, {}, plana, {}, dias[fin])["sin_ia"]
        assert hecho.patrimonio_final == pytest.approx(5_000 - 1.5)

    def test_sin_cierre_desde_la_compra_se_valora_a_la_entrada(self) -> None:
        antes = D0 - timedelta(days=1)
        plana = SeriePrecios((antes, D0, self.D1), (50.0,) * 3, (50.0,) * 3)
        caso = _caso(salida=None, sesion_salida=None, estado="ABIERTA")
        for cierres, final in (((50.0, float("nan")), 5_000 - 1.5), ((50.0, 80.0), 5_000 - 1.5 - 100)):
            # 2:1 anterior a la última sesión: no toca ni la entrada guardada ni este cierre.
            valor = SeriePrecios((antes, D0), cierres, cierres, ((antes, 2.0),))
            hecho = carteras([caso], {"A": valor}, {}, plana, {}, self.D1)["sin_ia"]
            assert hecho.patrimonio_final == pytest.approx(final)

    def test_un_split_anterior_a_la_entrada_no_se_deshace(self) -> None:
        valor = SeriePrecios((D0, self.D1), (100.0,) * 2, (100.0,) * 2, ((D0 - timedelta(days=3), 2.0), (D0, 4.0)))
        hecho = carteras(
            [_caso(salida=None, sesion_salida=None, estado="ABIERTA")], {"A": valor}, {}, valor, {}, self.D1,
        )["sin_ia"]
        assert hecho.patrimonio_final == pytest.approx(5_000 - 1.5)

    def test_split_de_la_referencia(self) -> None:
        valor = SeriePrecios((D0, self.D1), (100.0,) * 2, (100.0,) * 2)
        referencia = SeriePrecios((D0, self.D1), (50.0, 55.0), (50.0, 55.0), ((self.D1, 2.0),))
        caso = _caso(salida=None, sesion_salida=None, estado="ABIERTA")
        hecho = carteras([caso], {"A": valor}, {}, referencia, {}, self.D1)["sin_ia"]
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
        assert hecho["failed"] == {} and hecho["series_ausentes"] == hecho["episodios_truncados"] == []
        assert hecho["aperturas_invalidadas"] == {} and hecho["instante"] == T.isoformat()
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
