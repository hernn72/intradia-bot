"""Contrato del evaluador final con datos exclusivamente sintéticos."""

from __future__ import annotations

import json
import math
import os
import random
import shutil
import sqlite3
import subprocess
from dataclasses import FrozenInstanceError, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from advisor.data.calendars import expected_sessions
from advisor.research.vintage import freeze_vintage
from superbot.ia import madurez
from superbot.ia.madurez import CORTE
from superbot.ia.medicion import coste_orden_eur
from superbot_lab import evaluacion
from superbot_lab import evaluar as cli_evaluar
from superbot_lab.evaluacion import Episodio, _inconcluso_previo, abrir_fase
from superbot_lab.evaluador import (
    Caso,
    Intervalo,
    Observacion,
    SeriePrecios,
    bloque_de,
    carteras,
    coste_api_por_aprobado,
    estimador,
    exceso_neto,
    fx_de,
    intervalo_bloques,
    veredicto,
)

D0 = date(2026, 11, 25)


def _caso(**cambios: object) -> Caso:
    base = {
        "decision_id": 1, "symbol": "A", "market": "XETRA", "currency": "EUR", "grupo": "COMPRAR",
        "sesion_entrada": D0, "sesion_salida": D0, "entrada": 100.0, "salida": 95.0, "stop": 95.0,
        "score": 70.0, "target_open": datetime(2026, 11, 25, 8, tzinfo=timezone.utc), "estado": "STOP",
    }
    return Caso(**{**base, **cambios})  # type: ignore[arg-type]


def _repo_autorizado_minimo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, desfase: timedelta = timedelta(),
) -> tuple[Path, Path, datetime]:
    raiz, db = tmp_path / "repo", tmp_path / "base.db"
    (raiz / "docs/superbot-ia").mkdir(parents=True)
    shutil.copy("docs/superbot-ia/CRITERIO-CONTRAFACTUAL.md", raiz / "docs/superbot-ia")
    for nombre in evaluacion._EVALUADOR:
        destino = raiz / nombre
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(nombre, destino)
    instante = datetime(2027, 1, 4, 12, tzinfo=timezone.utc)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE ia_pasada(id INTEGER PRIMARY KEY,decision_ts TEXT,status TEXT)")
        conn.execute("INSERT INTO ia_pasada VALUES(1,?,'OK')", (instante.isoformat(),))
    autorizacion = {
        "criterio_sha256": evaluacion._sha(raiz / evaluacion._CRITERIO),
        "codigo_sha256": evaluacion.huella_evaluador(raiz), "base_sha256": evaluacion._sha(db),
        "cosecha": "sintetica", "autoriza": True, "instante": (instante + desfase).isoformat(),
        "entorno": evaluacion._entorno(),
    }
    (raiz / evaluacion._AUTORIZACION).write_text(json.dumps(autorizacion), encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(raiz)], check=True)
    subprocess.run(["git", "-C", str(raiz), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(raiz), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(raiz), "add", "."], check=True)
    subprocess.run(["git", "-C", str(raiz), "commit", "-qm", "sintético"], check=True)
    monkeypatch.chdir(raiz)
    return raiz, db, instante


@dataclass(frozen=True)
class LaboratorioPuertas:
    raiz: Path
    db: Path
    instante: datetime
    autorizacion: Path


def _laboratorio_puertas(
    tmp_path: Path, *, autorizacion: str = "normal", cambios: dict[str, object] | None = None,
    instante: datetime | None = None, ultima_status: str = "OK", congelacion_rota: bool = False,
) -> LaboratorioPuertas:
    """Monta un repo Git y una base completa, ambos sintéticos y parametrizables."""

    from tests.test_superbot_ia import paquete_compra
    from tests.test_superbot_ia_madurez import SESIONES, TRAS_CORTE, _base, _decision

    raiz, zona_base = tmp_path / "repo", tmp_path / "base"
    (raiz / "docs/superbot-ia").mkdir(parents=True)
    shutil.copy("docs/superbot-ia/CRITERIO-CONTRAFACTUAL.md", raiz / evaluacion._CRITERIO)
    shutil.copy("config.yaml", raiz / "config.yaml")
    for nombre in evaluacion._EVALUADOR:
        destino = raiz / nombre
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(nombre, destino)
    (raiz / "centinela.txt").write_text("limpio\n", encoding="utf-8")
    reg = _base(zona_base)
    for grupo, prefijo in (("COMPRAR", "A"), ("DESCARTAR", "D")):
        for numero in range(30):
            _decision(reg, f"{prefijo}{numero}", SESIONES[0], grupo)
    reg.conn.execute(
        "UPDATE ia_decision SET cuantitativo=?",
        (json.dumps({"currency": "EUR", "score": 70.0, "niveles": {"stop": 95.0}}),),
    )
    t = instante or datetime(2027, 5, 31, 12, tzinfo=timezone.utc)
    reg.conn.execute("UPDATE ia_pasada SET status='OK'")
    reg.conn.execute(
        "UPDATE ia_pasada SET decision_ts=?,status=? WHERE id=(SELECT MAX(id) FROM ia_pasada)",
        (t.isoformat(), ultima_status),
    )
    if congelacion_rota:
        pasada_id = int(reg.conn.execute("SELECT MAX(id) FROM ia_pasada").fetchone()[0])
        for modelo in ("m1", "m2"):
            reg.guardar_llamada(
                pasada_id=pasada_id, asesor="oportunidad", provider="sintetico", model=modelo,
                prompt_version="v", schema_version="1", input_hash=paquete_compra().input_hash,
                input_source_ids="[]", observaciones="[]", analysis_timestamp=TRAS_CORTE.isoformat(),
                estado="OK", coste_eur=0.0, created_at=TRAS_CORTE.isoformat(timespec="seconds"),
            )
    reg.conn.commit()
    reg.close()
    ruta_autorizacion = raiz / evaluacion._AUTORIZACION
    datos: dict[str, object] = {
        "criterio_sha256": evaluacion._sha(raiz / evaluacion._CRITERIO),
        "codigo_sha256": evaluacion.huella_evaluador(raiz), "base_sha256": evaluacion._sha(reg.path),
        "cosecha": "sintetica", "autoriza": True, "instante": t.isoformat(),
        "entorno": evaluacion._entorno(),
    }
    datos.update(cambios or {})
    if autorizacion == "normal":
        ruta_autorizacion.write_text(json.dumps(datos), encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(raiz)], check=True)
    subprocess.run(["git", "-C", str(raiz), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(raiz), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(raiz), "add", "."], check=True)
    entorno_git = {
        "GIT_AUTHOR_DATE": "2026-11-24T12:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-11-24T12:00:00+00:00",
    }
    subprocess.run(
        ["git", "-C", str(raiz), "commit", "-qm", "sintético"], check=True,
        env={**os.environ, **entorno_git},
    )
    if autorizacion == "no_comiteada":
        ruta_autorizacion.write_text(json.dumps(datos), encoding="utf-8")
    return LaboratorioPuertas(raiz, reg.path, t, ruta_autorizacion)


def test_caso_es_inmutable() -> None:
    with pytest.raises(FrozenInstanceError):
        _caso().score = 1.0  # type: ignore[misc]


def test_fx_invierte_el_par_y_solo_retrocede_cinco_dias() -> None:
    assert fx_de([D0], [2.0], D0, "USD") == 0.5
    assert fx_de([D0], [2.0], D0 + timedelta(days=5), "USD") == 0.5
    assert fx_de([D0], [2.0], D0 + timedelta(days=6), "USD") is None
    assert fx_de([], [], D0, "EUR") == 1.0


def test_fx_ignora_valores_invalidos_y_retrocede_hasta_cinco_dias() -> None:
    fechas = [D0 - timedelta(days=2), D0 - timedelta(days=1), D0]
    assert fx_de(fechas, [2.0, float("nan"), 0.0], D0, "USD") == 0.5


def test_exceso_eur_stop_mismo_dia_y_euro_fijo() -> None:
    caso = _caso()
    ref = SeriePrecios((D0 + timedelta(days=1),), (100.0,), (100.0,))
    exceso, nocional = exceso_neto(caso, 1.0, 1.0, ref)
    esperado = (5 * 95 - 500 - coste_orden_eur(500) - coste_orden_eur(475)) / 500
    assert nocional == pytest.approx(500.0)
    assert exceso == pytest.approx(esperado)


def test_exceso_usd_usa_un_cambio_distinto_por_lado_y_referencia_sin_euro_fijo() -> None:
    caso = _caso(currency="USD", salida=110.0, stop=90.0, sesion_salida=D0 + timedelta(days=1), estado="HORIZONTE")
    ref = SeriePrecios((D0, D0 + timedelta(days=1)), (100.0, 100.0), (100.0, 100.0))
    exceso, nocional = exceso_neto(caso, 0.5, 0.4, ref)
    valor = (220 - 250 - coste_orden_eur(250) - coste_orden_eur(220)) / 250
    assert nocional == pytest.approx(250.0)
    assert exceso == pytest.approx(valor + 0.002)


def test_referencia_con_split_posterior_usa_una_escala_coherente() -> None:
    caso = _caso(salida=100.0, stop=90.0, sesion_salida=D0 + timedelta(days=1), estado="HORIZONTE")
    referencia = SeriePrecios(
        (D0, D0 + timedelta(days=1)), (50.0, 55.0), (50.0, 55.0),
        ((D0 + timedelta(days=2), 2.0),),
    )
    exceso, _ = exceso_neto(caso, 1.0, 1.0, referencia)
    equivalente = SeriePrecios((D0, D0 + timedelta(days=1)), (100.0, 110.0), (100.0, 110.0))
    assert exceso == pytest.approx(exceso_neto(caso, 1.0, 1.0, equivalente)[0])


@pytest.mark.parametrize(
    "ic,esperado",
    [
        (Intervalo(0.01, 0.02, 1, 0), "LA IA APORTA"),
        (Intervalo(-0.02, 0.0, 1, 0), "LA IA NO APORTA"),
        (Intervalo(0.0, 0.02, 1, 0), "INCONCLUSO"),
        (Intervalo(-0.01, 0.01, 1, 0), "INCONCLUSO"),
    ],
)
def test_veredictos_y_frontera_cero(ic: Intervalo, esperado: str) -> None:
    assert veredicto(ic) == esperado


def test_bloques_son_reproducibles_y_el_coste_api_es_constante() -> None:
    lunes = CORTE.date() - timedelta(days=CORTE.date().weekday())
    aprobadas = [Observacion(lunes, 0.10, 500.0), Observacion(lunes + timedelta(days=28), 0.20, 500.0)]
    descartadas = [Observacion(lunes, 0.0, 500.0), Observacion(lunes + timedelta(days=28), 0.0, 500.0)]
    uno = intervalo_bloques(aprobadas, descartadas, 0.01, replicas=500)
    assert uno == intervalo_bloques(aprobadas, descartadas, 0.01, replicas=500)
    assert uno.validas == 500 and uno.bajo is not None and uno.alto is not None


def test_api_se_resta_solo_a_las_aprobadas() -> None:
    aprobadas = [Observacion(D0, 0.10, 200.0), Observacion(D0, 0.20, 300.0)]
    descartadas = [Observacion(D0, 0.05, 500.0)]
    coste = coste_api_por_aprobado(5.0, aprobadas)
    assert coste == pytest.approx(0.01)
    assert estimador(aprobadas, descartadas, coste) == pytest.approx(0.09)


def test_bloques_sin_un_grupo_superan_el_cinco_por_ciento() -> None:
    lunes = CORTE.date() - timedelta(days=CORTE.date().weekday())
    aprobadas = [Observacion(lunes, 0.1, 500.0)]
    descartadas = [Observacion(lunes + timedelta(days=28), 0.0, 500.0)]
    assert intervalo_bloques(aprobadas, descartadas, 0.0, replicas=1000).bajo is None


def test_cinco_por_ciento_exacto_de_replicas_es_valido_y_superarlo_no() -> None:
    lunes = CORTE.date() - timedelta(days=CORTE.date().weekday())
    aprobadas = [Observacion(lunes + timedelta(days=28 * i), 0.1, 1.0) for i in range(2)]
    descartadas = [Observacion(lunes + timedelta(days=28 * i), 0.0, 1.0) for i in range(3)]
    exacto = intervalo_bloques(aprobadas, descartadas, 0.0, replicas=20, semilla=11)
    superado = intervalo_bloques(aprobadas, descartadas, 0.0, replicas=20, semilla=6)
    assert exacto.descartadas == 1 and exacto.bajo is not None
    assert superado.descartadas == 2 and superado.bajo is None


def test_bloque_anterior_al_corte_es_error_y_frontera_domingo_lunes() -> None:
    lunes = CORTE.date() - timedelta(days=CORTE.date().weekday())
    assert bloque_de(lunes + timedelta(days=27)) == 0
    assert bloque_de(lunes + timedelta(days=28)) == 1
    with pytest.raises(ValueError, match="anterior"):
        bloque_de(lunes - timedelta(days=1))


def test_percentil_por_rango_mas_cercano_es_calculable() -> None:
    lunes = CORTE.date() - timedelta(days=CORTE.date().weekday())
    aprobadas = [Observacion(lunes, float(i), 1.0) for i in range(1, 5)]
    descartadas = [Observacion(lunes, 0.0, 1.0)]
    ic = intervalo_bloques(aprobadas, descartadas, 0.0, replicas=40)
    assert ic == Intervalo(2.5, 2.5, 40, 0)


def test_percentil_exacto_usa_floor_y_ceil_sobre_las_validas() -> None:
    lunes = CORTE.date() - timedelta(days=CORTE.date().weekday())
    aprobadas = [Observacion(lunes + timedelta(days=28 * i), float(10**i), 1.0) for i in range(7)]
    descartadas = [Observacion(lunes + timedelta(days=28 * i), 0.0, 1.0) for i in range(7)]
    replicas = 137
    azar = random.Random(20261124)
    valores = []
    for _ in range(replicas):
        elegidos = [azar.randrange(7) for _ in range(7)]
        valores.append(sum(10**i for i in elegidos) / 7)
    valores.sort()
    ic = intervalo_bloques(aprobadas, descartadas, 0.0, replicas=replicas)
    assert (ic.bajo, ic.alto) == (
        valores[math.floor(0.025 * replicas)], valores[math.ceil(0.975 * replicas) - 1],
    )


def test_cinco_por_ciento_exacto_no_invalida_y_treinta_exacto_basta() -> None:
    usables = [
        Episodio(i, f"{grupo}{i}", "XETRA", grupo, D0, "maduros")
        for grupo in ("COMPRAR", "DESCARTAR") for i in range(30)
    ]
    assert _inconcluso_previo(usables, usables, {"COMPRAR": {}, "DESCARTAR": {}}) is None
    amplios = [
        Episodio(i, f"{grupo}{i}", "XETRA", grupo, D0, "maduros")
        for grupo in ("COMPRAR", "DESCARTAR") for i in range(38)
    ]
    lista = [*amplios]
    for grupo in ("COMPRAR", "DESCARTAR"):
        lista.extend(Episodio(1000 + i, f"X{grupo}{i}", "XETRA", grupo, D0, "sin_entrada") for i in range(2))
    excluidos = {
        "COMPRAR": {"SIN_BARRA_DE_ENTRADA": 2}, "DESCARTAR": {"SIN_BARRA_DE_ENTRADA": 2},
    }
    assert _inconcluso_previo(lista, amplios, excluidos) is None
    excluidos["COMPRAR"]["SIN_BARRA_DE_ENTRADA"] = 3
    assert _inconcluso_previo(lista, amplios, excluidos) == "DATOS"


def test_autorizador_separa_las_tres_fases(tmp_path: Path) -> None:
    db = tmp_path / "sintetica.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE ia_contrafactual(decision_id INTEGER, estado TEXT, final INTEGER, retorno_r REAL);"
        "CREATE TABLE ia_posicion(id INTEGER);"
        "INSERT INTO ia_contrafactual VALUES(1,'STOP',1,2.0);"
    )
    conn.close()
    with abrir_fase(db, 0) as fase0, pytest.raises(sqlite3.DatabaseError):
        fase0.execute("SELECT COUNT(*) FROM ia_contrafactual").fetchone()
    with abrir_fase(db, 1) as fase1:
        assert tuple(fase1.execute("SELECT decision_id,estado,final FROM ia_contrafactual").fetchone()) == (1, "STOP", 1)
        with pytest.raises(sqlite3.DatabaseError):
            fase1.execute("SELECT retorno_r FROM ia_contrafactual").fetchone()
    with abrir_fase(db, 2) as fase2:
        assert fase2.execute("SELECT retorno_r FROM ia_contrafactual").fetchone()[0] == 2.0
        assert fase2.execute("SELECT COUNT(*) FROM ia_posicion").fetchone()[0] == 0


def test_autorizador_fase_dos_admite_solo_posiciones_y_ordenes_de_venta(tmp_path: Path) -> None:
    db = tmp_path / "sintetica.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE ia_posicion(id INTEGER); CREATE TABLE ia_orden(id INTEGER);"
        "CREATE TABLE ia_fill(id INTEGER); CREATE TABLE ia_movimiento(id INTEGER);"
        "CREATE TABLE ia_valoracion(id INTEGER); CREATE TABLE ia_orden_archivo(id INTEGER);"
    )
    conn.close()
    with abrir_fase(db, 2) as fase:
        assert fase.execute("SELECT COUNT(*) FROM ia_posicion").fetchone()[0] == 0
        assert fase.execute("SELECT COUNT(*) FROM ia_orden").fetchone()[0] == 0
        for tabla in ("ia_fill", "ia_movimiento", "ia_valoracion", "ia_orden_archivo"):
            with pytest.raises(sqlite3.DatabaseError):
                fase.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()


def test_huella_evaluador_cubre_dependencias_congeladas(tmp_path: Path) -> None:
    rutas = [
        "superbot_lab/evaluador.py", "superbot_lab/evaluacion.py", "superbot_lab/evaluar.py",
        "superbot_lab/datos_lab.py", "superbot/ia/contrafactual.py", "superbot/ia/madurez.py",
        "superbot/ia/medicion.py", "superbot/ia/cartera.py", "superbot/ia/registro.py",
        "advisor/research/vintage.py", "advisor/data/calendars.py", "advisor/data/sessions.py",
        "exchange_overrides.yaml",
    ]
    for ruta in rutas:
        destino = tmp_path / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(ruta, encoding="utf-8")
    antes = evaluacion.huella_evaluador(tmp_path)
    (tmp_path / "advisor/data/sessions.py").write_text("alterado", encoding="utf-8")
    assert evaluacion.huella_evaluador(tmp_path) != antes


def test_fase_uno_excluye_no_ejecutable_y_rechaza_contradiccion_sin_entrada(tmp_path: Path) -> None:
    from tests.test_superbot_ia_madurez import SESIONES, _base, _decision

    reg = _base(tmp_path)
    _decision(reg, "A", SESIONES[0], "COMPRAR")
    _decision(reg, "B", SESIONES[0], "DESCARTAR")
    ids = [int(f[0]) for f in reg.conn.execute("SELECT id FROM ia_decision ORDER BY id")]
    reg.conn.executemany(
        "INSERT INTO ia_contrafactual(decision_id,symbol,resolucion,target_session,estado,final,updated_at) "
        "VALUES(?,?,?,?,?,1,'x')",
        [(ids[0], "A", "COMPRAR", SESIONES[0].isoformat(), "NO_EJECUTABLE"),
         (ids[1], "B", "DESCARTAR", SESIONES[0].isoformat(), "STOP")],
    )
    reg.conn.commit()
    lista = [
        Episodio(ids[0], "A", "XETRA", "COMPRAR", D0, "maduros"),
        Episodio(ids[1], "B", "XETRA", "DESCARTAR", D0, "sin_entrada"),
    ]
    with pytest.raises(evaluacion.EvaluacionDenegada, match="contradicción") as error:
        evaluacion._fase1(reg.path, lista)
    assert "STOP" not in str(error.value)
    reg.conn.execute("UPDATE ia_contrafactual SET estado='SIN_BARRA_DE_ENTRADA' WHERE decision_id=?", (ids[1],))
    reg.conn.commit()
    usables, excluidos = evaluacion._fase1(reg.path, lista)
    assert usables == []
    assert excluidos == {
        "COMPRAR": {"NO_EJECUTABLE": 1}, "DESCARTAR": {"SIN_BARRA_DE_ENTRADA": 1},
    }


def test_cuantitativo_incompleto_se_rechaza_antes_de_apertura(tmp_path: Path) -> None:
    db = tmp_path / "cuantitativo.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE ia_decision(id INTEGER, cuantitativo TEXT)")
    conn.execute("INSERT INTO ia_decision VALUES(1,?)", (json.dumps({"niveles": {"stop": 9}}),))
    conn.commit()
    conn.close()
    with pytest.raises(evaluacion.EvaluacionDenegada, match="cuantitativo"):
        evaluacion._cuantitativos(db, [1])


def test_leer_casos_incluye_abierta_solo_en_carteras(tmp_path: Path) -> None:
    from tests.test_superbot_ia_madurez import NIVELES, SESIONES, _base, _decision

    reg = _base(tmp_path)
    _decision(reg, "ABIERTA", SESIONES[0], "COMPRAR")
    decision_id = int(reg.conn.execute("SELECT MAX(id) FROM ia_decision").fetchone()[0])
    cuantitativo = {"score": 75.0, "currency": "EUR", "niveles": NIVELES}
    reg.conn.execute("UPDATE ia_decision SET cuantitativo=? WHERE id=?", (json.dumps(cuantitativo), decision_id))
    reg.conn.execute(
        "INSERT INTO ia_contrafactual(decision_id,symbol,resolucion,target_session,estado,entrada,final,updated_at) "
        "VALUES(?,?,?,?,?,100,0,'x')",
        (decision_id, "ABIERTA", "COMPRAR", SESIONES[0].isoformat(), "ABIERTA"),
    )
    reg.conn.commit()
    casos, candidatas, _retornos, error = evaluacion._leer_casos(reg.path, [])
    assert casos == []
    assert error is None
    assert len(candidatas) == 1
    assert candidatas[0].sesion_salida is None and candidatas[0].salida is None
    reg.conn.close()


def test_ventas_ia_son_descriptivas_y_comparan_con_mantener(tmp_path: Path) -> None:
    db = tmp_path / "ventas.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE ia_pasada(id INTEGER,decision_ts TEXT);"
        "CREATE TABLE ia_decision(id INTEGER,pasada_id INTEGER);"
        "CREATE TABLE ia_contrafactual(decision_id INTEGER,retorno_pct REAL,final INTEGER,estado TEXT);"
        "CREATE TABLE ia_posicion(id INTEGER,estado TEXT,entry_price REAL,exit_price REAL,decision_apertura_id INTEGER);"
        "CREATE TABLE ia_orden(position_id INTEGER,proposito TEXT,estado TEXT);"
    )
    conn.execute("INSERT INTO ia_pasada VALUES(1,?)", (CORTE.isoformat(),))
    conn.execute("INSERT INTO ia_decision VALUES(10,1)")
    conn.execute("INSERT INTO ia_contrafactual VALUES(10,20,1,'HORIZONTE')")
    conn.execute("INSERT INTO ia_posicion VALUES(5,'CERRADA',100,110,10)")
    conn.execute("INSERT INTO ia_orden VALUES(5,'EXIT_IA','EJECUTADA')")
    conn.commit()
    conn.close()
    assert evaluacion._ventas_ia(db) == {
        "n": 1, "retorno_real_pct_medio": pytest.approx(10.0), "retorno_mantener_pct_medio": 20.0,
    }


def test_episodios_equivalen_a_madurez_en_doscientas_semillas(tmp_path: Path) -> None:
    from tests.test_superbot_ia_madurez import SESIONES, H, _base, _decision, _tras

    categorias = ("maduros", "madurando", "no_ejecutables", "sin_entrada")
    for semilla in range(200):
        raiz = tmp_path / str(semilla)
        raiz.mkdir()
        reg = _base(raiz)
        azar = random.Random(semilla)
        for _numero in range(18):
            ejecutable = azar.choice((0, 1, 1, None))
            _decision(
                reg, f"S{azar.randrange(6)}", SESIONES[azar.randrange(0, H + 3)],
                azar.choice(("COMPRAR", "DESCARTAR")), ejecutable,
            )
        instante = _tras(SESIONES[H + 1])
        cuenta = madurez.contar(reg.conn, instante)
        lista = evaluacion.episodios(reg.conn, instante)
        for grupo, esperado in (("COMPRAR", cuenta.aprobadas), ("DESCARTAR", cuenta.descartadas)):
            reales = tuple(sum(e.grupo == grupo and e.categoria == categoria for e in lista) for categoria in categorias)
            assert reales == (
                esperado.maduros, esperado.madurando, esperado.no_ejecutables, esperado.sin_entrada,
            )
        reg.conn.close()


@pytest.mark.parametrize(
    "escenario",
    [
        "ausente", "no_comiteada", "cambiada_assume", "criterio_disco", "criterio_sha", "codigo_sha",
        "base_sha", "cosecha", "instante", "entorno", "mismo_dia", "wal", "resultado", "apertura",
        "git_sucio", "congelacion", "aun_no_toca", "ultima_no_ok", "cwd",
    ],
)
def test_puertas_reales_denegadas_sin_apertura_ni_fases_selladas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, escenario: str,
) -> None:
    cambios: dict[str, object] = {}
    modo = "normal"
    instante = datetime(2027, 5, 31, 12, tzinfo=timezone.utc)
    ultima_status = "OK"
    rota = escenario == "congelacion"
    if escenario == "ausente":
        modo = "ausente"
    elif escenario == "no_comiteada":
        modo = "no_comiteada"
    elif escenario == "criterio_sha":
        cambios["criterio_sha256"] = "0" * 64
    elif escenario == "codigo_sha":
        cambios["codigo_sha256"] = "0" * 64
    elif escenario == "base_sha":
        cambios["base_sha256"] = "0" * 64
    elif escenario == "instante":
        cambios["instante"] = (instante - timedelta(seconds=1)).isoformat()
    elif escenario == "entorno":
        cambios["entorno"] = {"python": "0", "pandas": "0", "exchange_calendars": "0"}
    elif escenario == "aun_no_toca":
        instante = datetime(2027, 5, 30, 12, tzinfo=timezone.utc)
    elif escenario == "ultima_no_ok":
        ultima_status = "ERROR"
    lab = _laboratorio_puertas(
        tmp_path, autorizacion=modo, cambios=cambios, instante=instante,
        ultima_status=ultima_status, congelacion_rota=rota,
    )
    if escenario != "cwd":
        monkeypatch.chdir(lab.raiz)
    if escenario == "cambiada_assume":
        datos = json.loads(lab.autorizacion.read_text(encoding="utf-8"))
        datos["autoriza"] = False
        lab.autorizacion.write_text(json.dumps(datos), encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(lab.raiz), "update-index", "--assume-unchanged", str(evaluacion._AUTORIZACION)],
            check=True,
        )
    elif escenario == "criterio_disco":
        (lab.raiz / evaluacion._CRITERIO).write_text("cambiado\n", encoding="utf-8")
    elif escenario == "wal":
        Path(str(lab.db) + "-wal").write_bytes(b"wal")
    elif escenario in {"resultado", "apertura"}:
        resultado, apertura = evaluacion._salidas(lab.raiz)
        destino = resultado if escenario == "resultado" else apertura
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text("{}\n", encoding="utf-8")
    elif escenario == "git_sucio":
        (lab.raiz / "centinela.txt").write_text("sucio\n", encoding="utf-8")
    apertura_ruta = lab.raiz / evaluacion._SALIDA / "apertura.json"
    apertura_previa = apertura_ruta.read_bytes() if apertura_ruta.exists() else None
    fases: list[int] = []
    abrir_real = evaluacion.abrir_fase

    def espiar(db: Path, fase: int) -> sqlite3.Connection:
        fases.append(fase)
        return abrir_real(db, fase)

    monkeypatch.setattr(evaluacion, "abrir_fase", espiar)

    def reloj() -> datetime:
        return lab.instante + (timedelta(hours=1) if escenario == "mismo_dia" else timedelta(days=1))

    motivo = {"congelacion": "congelación está rota", "aun_no_toca": "todavía no toca", "mismo_dia": "no están completas"}
    with pytest.raises(evaluacion.EvaluacionDenegada, match=motivo.get(escenario)):
        if escenario == "cosecha":
            evaluacion._autorizacion(lab.raiz, "otra", lab.db, reloj)
        else:
            evaluacion.evaluar(lab.db, tmp_path / "cosechas", raiz=lab.raiz, reloj=reloj)
    assert 1 not in fases and 2 not in fases
    if escenario == "ausente":
        assert fases == []
    if apertura_previa is None:
        assert not apertura_ruta.exists()
    else:
        assert apertura_ruta.read_bytes() == apertura_previa


@pytest.mark.parametrize("fallido,critico", [("A0", False), ("EUNL.DE", True), ("EURUSD=X", True)])
def test_congelar_conserva_id_y_publica_solo_valores_ausentes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fallido: str, critico: bool,
) -> None:
    lab = _laboratorio_puertas(tmp_path)
    with sqlite3.connect(lab.db) as conn:
        conn.execute(
            "UPDATE ia_decision SET cuantitativo=? WHERE id=(SELECT MIN(id) FROM ia_decision)",
            (json.dumps({"currency": "USD", "score": 70.0, "niveles": {"stop": 95.0}}),),
        )
    monkeypatch.chdir(lab.raiz)
    sesiones = pd.DatetimeIndex(expected_sessions(
        "XETRA", CORTE.date() - timedelta(days=10), lab.instante.astimezone(timezone.utc).date(),
    ))
    naturales = pd.date_range(
        CORTE.date() - timedelta(days=10), lab.instante.astimezone(timezone.utc).date(),
        tz="Europe/London",
    )

    class Proveedor:
        def get_raw_history(self, symbol: str, **_kwargs: object) -> pd.DataFrame:
            if symbol == fallido:
                return pd.DataFrame()
            indice = naturales if symbol.startswith("EUR") and symbol.endswith("=X") else sesiones
            return pd.DataFrame({
                "Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Adj Close": 100.0,
                "Volume": 1000.0, "Dividends": 0.0, "Stock Splits": 0.0,
            }, index=indice)

    if critico:
        with pytest.raises(evaluacion.EvaluacionDenegada, match="failed"):
            cli_evaluar.congelar(
                lab.db, tmp_path / "cosechas", raiz=lab.raiz,
                reloj=lambda: lab.instante + timedelta(days=1), proveedor=Proveedor(),
            )
    else:
        resultado = cli_evaluar.congelar(
            lab.db, tmp_path / "cosechas", raiz=lab.raiz,
            reloj=lambda: lab.instante + timedelta(days=1), proveedor=Proveedor(),
        )
        assert resultado["cosecha"]
        assert resultado["series_ausentes"] == [fallido]
        assert fallido in resultado["failed"]


def test_cartera_api_solo_con_ia_y_no_cambia_operaciones() -> None:
    caso = _caso(sesion_salida=D0 + timedelta(days=1), salida=100.0, estado="HORIZONTE")
    serie = SeriePrecios((D0, D0 + timedelta(days=1)), (100.0, 100.0), (100.0, 100.0))
    resultado = carteras([caso], {"A": serie}, {}, serie, {D0: 3.0}, D0 + timedelta(days=1))
    assert resultado["sin_ia"].patrimonio_final - resultado["con_ia"].patrimonio_final == pytest.approx(3.0)
    assert len(resultado["sin_ia"].operaciones) == len(resultado["con_ia"].operaciones) == 1


def test_cartera_no_reutiliza_el_efectivo_hasta_el_dia_siguiente_y_marca_abiertas() -> None:
    d1, d2 = D0 + timedelta(days=1), D0 + timedelta(days=2)
    casos = [
        _caso(
            decision_id=i, symbol=f"S{i}", score=100.0 - i,
            sesion_salida=d1 if i == 0 else None, salida=100.0 if i == 0 else None,
            estado="HORIZONTE" if i == 0 else "ABIERTA",
        )
        for i in range(9)
    ]
    casos.extend([
        _caso(decision_id=20, symbol="TARDE", sesion_entrada=d1, sesion_salida=None, salida=None, estado="ABIERTA"),
        _caso(decision_id=21, symbol="DIA_SIGUIENTE", sesion_entrada=d2, sesion_salida=None, salida=None, estado="ABIERTA"),
    ])
    serie = SeriePrecios((D0, d1, d2), (100.0,) * 3, (100.0,) * 3)
    resultado = carteras(casos, {c.symbol: serie for c in casos}, {}, serie, {}, d2)["sin_ia"]
    simbolos = {op.symbol for op in resultado.operaciones}
    assert "TARDE" not in simbolos
    assert "DIA_SIGUIENTE" in simbolos
    abierta = next(op for op in resultado.operaciones if op.symbol == "DIA_SIGUIENTE")
    assert abierta.salida is None and abierta.pnl_eur is None and abierta.estado == "ABIERTA"


def test_abierta_de_produccion_conserva_ultimo_cierre_y_entra_en_cartera(tmp_path: Path) -> None:
    from superbot.ia import contrafactual
    from tests.test_superbot_ia_madurez import NIVELES, SESIONES, _base, _decision

    reg = _base(tmp_path)
    _decision(reg, "VIVO", SESIONES[0], "COMPRAR")
    decision_id = int(reg.conn.execute("SELECT MAX(id) FROM ia_decision").fetchone()[0])
    reg.conn.execute(
        "UPDATE ia_decision SET cuantitativo=? WHERE id=?",
        (json.dumps({"score": 80.0, "currency": "EUR", "niveles": NIVELES}), decision_id),
    )

    class Proveedor:
        def get_history(self, *_args: object, **_kwargs: object) -> pd.DataFrame:
            return pd.DataFrame(
                    {"Open": [99.0, 99.0], "High": [102.0, 103.0], "Low": [98.0, 98.0],
                 "Close": [101.0, 102.0], "Stock Splits": [0.0, 0.0]},
                index=pd.DatetimeIndex(SESIONES[:2]),
            )

    class Universo:
        class Activo:
            def data_symbol(self, _instante: datetime) -> str:
                return "VIVO"

        def get(self, _symbol: str) -> object:
            return self.Activo()

    contrafactual.actualizar(
        reg.conn, Proveedor(), Universo(), datetime(2027, 1, 1, tzinfo=timezone.utc), "3mo", "1d", 20,
    )
    fila = reg.conn.execute(
        "SELECT estado,final,salida,hasta_session FROM ia_contrafactual WHERE decision_id=?", (decision_id,),
    ).fetchone()
    assert tuple(fila[:2]) == ("ABIERTA", 0)
    assert fila[2] is not None and fila[3] is not None
    _metrica, candidatas, _retornos, error = evaluacion._leer_casos(reg.path, [])
    assert error is None
    assert [caso.decision_id for caso in candidatas] == [decision_id]
    assert candidatas[0].sesion_salida is None and candidatas[0].salida is None
    reg.conn.close()


def test_referencia_de_cartera_usa_cierres_cosechados_sin_reescalar_split() -> None:
    d1 = D0 + timedelta(days=1)
    caso = _caso(sesion_salida=d1, salida=100.0, estado="HORIZONTE")
    valor = SeriePrecios((D0, d1), (100.0, 100.0), (100.0, 100.0))
    referencia = SeriePrecios((D0, d1), (50.0, 55.0), (50.0, 55.0), ((d1 + timedelta(days=1), 2.0),))
    resultado = carteras([caso], {"A": valor}, {}, referencia, {}, d1)["sin_ia"]
    sin_split = SeriePrecios((D0, d1), (50.0, 55.0), (50.0, 55.0))
    esperado = carteras([caso], {"A": valor}, {}, sin_split, {}, d1)["sin_ia"]
    assert resultado == esperado


def test_autorizador_es_lista_blanca_por_fase(tmp_path: Path) -> None:
    db = tmp_path / "blanca.db"
    with sqlite3.connect(db) as conn:
        conn.executescript("CREATE TABLE secreto(valor TEXT); INSERT INTO secreto VALUES('VENENO');")
    for fase in (0, 1, 2):
        with abrir_fase(db, fase) as conn, pytest.raises(sqlite3.DatabaseError):
            conn.execute("SELECT valor FROM secreto").fetchone()


def test_lectores_sellados_no_usan_joins_implicitos() -> None:
    for ruta in (Path("superbot_lab/evaluacion.py"), Path("superbot/ia/madurez.py")):
        fuente = ruta.read_text(encoding="utf-8").upper()
        assert " NATURAL JOIN " not in fuente and " USING (" not in fuente


def test_instante_es_ultima_pasada_ok_y_rechaza_ultima_incompleta(tmp_path: Path) -> None:
    db = tmp_path / "instante.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE ia_pasada(id INTEGER PRIMARY KEY, decision_ts TEXT, status TEXT)")
        conn.executemany(
            "INSERT INTO ia_pasada VALUES(?,?,?)",
            [(1, "2027-01-01T09:00:00+00:00", "OK"), (2, "2027-01-02T09:00:00+00:00", "OK")],
        )
    assert evaluacion._instante_base(db) == datetime(2027, 1, 2, 9, tzinfo=timezone.utc)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE ia_pasada SET status='ERROR' WHERE id=2")
    with pytest.raises(evaluacion.EvaluacionDenegada, match="última pasada"):
        evaluacion._instante_base(db)


def test_autorizacion_compara_base_justo_antes_de_abrir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    raiz, db, instante = _repo_autorizado_minimo(tmp_path, monkeypatch)
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO ia_pasada VALUES(2,?,'OK')", (instante.isoformat(),))
    with pytest.raises(evaluacion.EvaluacionDenegada, match="autorización no coincide"):
        evaluacion._autorizacion(raiz, None, db, lambda: instante + timedelta(days=1))


def test_autorizacion_compara_instante_con_ultima_pasada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    raiz, db, instante = _repo_autorizado_minimo(tmp_path, monkeypatch, desfase=timedelta(seconds=1))
    with pytest.raises(evaluacion.EvaluacionDenegada, match="instante autorizado no coincide"):
        evaluacion._autorizacion(raiz, None, db, lambda: instante + timedelta(days=1))


def test_fin_se_fija_por_calendario_y_no_por_la_ultima_barra(tmp_path: Path) -> None:
    instante = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)
    barras = pd.DataFrame({
        "Open": [100.0], "High": [101.0], "Low": [99.0], "Close": [100.0], "Adj Close": [100.0],
        "Volume": [1000.0], "Dividends": [0.0], "Stock Splits": [0.0],
    }, index=pd.DatetimeIndex([date(2026, 11, 24)]))

    class Proveedor:
        def get_raw_history(self, _symbol: str, **_kwargs: object) -> pd.DataFrame:
            return barras.copy()

    cosecha = freeze_vintage(
        ["A", "EUNL.DE"], Proveedor(), interval="1d", start="2026-11-14", end="2026-11-26",
        root_dir=tmp_path, downloaded_at=instante,
    )
    db = tmp_path / "filas.db"
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        decisiones = conn.execute(
            "SELECT 1 id,'A' symbol,'XETRA' market,'2026-11-24' target_session,? cuantitativo,1 ejecutable",
            (json.dumps({"currency": "EUR", "score": 1, "niveles": {"stop": 90}}),),
        ).fetchall()
    with pytest.raises(evaluacion.EvaluacionDenegada, match="sesiones de EUNL"):
        evaluacion._comprobar_cosecha(
            cosecha.data_vintage_id, tmp_path, decisiones, instante,
            {1: {"currency": "EUR", "score": 1, "niveles": {"stop": 90}}},
        )


def test_cartera_prioriza_apertura_luego_score_y_simbolo() -> None:
    tarde = datetime(2026, 11, 25, 10, tzinfo=timezone.utc)
    temprano = datetime(2026, 11, 25, 9, tzinfo=timezone.utc)
    casos = [
        _caso(decision_id=1, symbol="BAJO", score=80, stop=99, salida=None, sesion_salida=None, estado="ABIERTA"),
        _caso(
            decision_id=2, symbol="B", score=90, stop=99, target_open=tarde,
            salida=None, sesion_salida=None, estado="ABIERTA",
        ),
        _caso(
            decision_id=3, symbol="A", score=90, stop=99, target_open=temprano,
            salida=None, sesion_salida=None, estado="ABIERTA",
        ),
    ]
    serie = SeriePrecios((D0,), (100.0,), (100.0,))
    resultado = carteras(casos, {c.symbol: serie for c in casos}, {}, serie, {D0: 4_498.0}, D0)["con_ia"]
    assert [o.symbol for o in resultado.operaciones] == ["BAJO"]


def test_cartera_resta_exposicion_del_cierre_anterior_y_retrocede_nan() -> None:
    d1, d2 = D0 + timedelta(days=1), D0 + timedelta(days=2)
    caso = _caso(salida=None, sesion_salida=None, estado="ABIERTA")
    valor = SeriePrecios((D0, d1, d2), (100.0,) * 3, (100.0, float("nan"), 120.0))
    referencia = SeriePrecios((D0, d1, d2), (100.0, 110.0, 121.0), (100.0, 110.0, 121.0))
    resultado = carteras([caso], {"A": valor}, {}, referencia, {}, d2)["sin_ia"]
    assert resultado.exceso_acumulado == pytest.approx(-coste_orden_eur(500.0))
