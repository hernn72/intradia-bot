"""Madurez del contrafactual: cuenta episodios por calendario, avisa una vez y no puede ver rendimientos."""

from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar, List, Optional

import pytest

from advisor.data.calendars import expected_sessions
from superbot.ia import __main__ as cli
from superbot.ia import contrafactual, dashboard, datos, madurez, pasada, telegram
from superbot.ia.registro import RegistroIA
from tests.test_superbot_ia import POLITICA, ClienteFalso, _analisis, _pasada, compra_ok, paquete_compra, registro
from tests.test_superbot_ia_cartera import _cartera, _proveedor_ohlc

SESIONES = expected_sessions("XETRA", date(2026, 11, 25), date(2027, 6, 30))
TRAS_CORTE = madurez.CORTE + timedelta(hours=5)
H = contrafactual.HORIZONTE_SESIONES
NIVELES = {"stop": 95.0, "target2": 107.0, "entry_max": 101.0, "min_rr_ratio": 1.5}


def _tras(sesion: date) -> datetime:
    """Con esa sesión de Xetra ya cerrada y liquidada."""

    return datetime(sesion.year, sesion.month, sesion.day, 22, 0, tzinfo=timezone.utc)


def _base(tmp_path: Path) -> RegistroIA:
    reg = registro(tmp_path)
    reg.guardar_paquete(paquete_compra())
    contrafactual.asegurar_esquema(reg.conn)
    return reg


def _decision(
    reg: RegistroIA, symbol: str, sesion: date, resolucion: str = "COMPRAR", ejecutable: Optional[int] = 1, *,
    cuando: datetime = TRAS_CORTE,
) -> None:
    pasada_id = reg.abrir_pasada(cuando, "activo", "sha")
    n = reg.conn.execute("SELECT COUNT(*) FROM ia_decision").fetchone()[0]
    cursor = reg.conn.execute(
        "INSERT INTO ia_decision (clave, pasada_id, policy, symbol, market, tipo, signal_session, target_session, "
        "target_open, decision_ts, input_hash, cuantitativo, votos, predicados, resolucion, motivo, aplicada, created_at) "
        "VALUES (?, ?, 'p', ?, 'XETRA', 'COMPRA', ?, ?, ?, ?, ?, ?, '[]', '{}', ?, 'm', 1, ?)",
        (f"k{n}", pasada_id, symbol, sesion.isoformat(), sesion.isoformat(), cuando.isoformat(), cuando.isoformat(),
         paquete_compra().input_hash, json.dumps({"niveles": NIVELES}), resolucion, cuando.isoformat()),
    )
    if ejecutable is not None:
        reg.conn.execute(
            "INSERT INTO ia_contrafactual_entrada VALUES (?, ?, 'x')", (cursor.lastrowid, ejecutable),
        )


class TestContar:
    def test_madura_a_las_veinte_sesiones_y_no_antes(self, tmp_path: Path) -> None:
        reg = _base(tmp_path)
        _decision(reg, "A", SESIONES[0])
        assert madurez.contar(reg.conn, _tras(SESIONES[H - 2])).aprobadas == madurez.GrupoMadurez(0, 1, 0, 0)
        assert madurez.contar(reg.conn, _tras(SESIONES[H - 1])).aprobadas == madurez.GrupoMadurez(1, 0, 0, 0)

    def test_el_grupo_lo_fija_la_primera_ejecutable_y_lo_demas_del_episodio_se_ignora(self, tmp_path: Path) -> None:
        reg = _base(tmp_path)
        _decision(reg, "A", SESIONES[0], "DESCARTAR")
        _decision(reg, "A", SESIONES[1], "COMPRAR")
        _decision(reg, "A", SESIONES[H - 1], "COMPRAR")
        _decision(reg, "A", SESIONES[H], "COMPRAR")
        cuenta = madurez.contar(reg.conn, _tras(SESIONES[H]))
        assert cuenta.descartadas.maduros == 1 and (cuenta.aprobadas.maduros, cuenta.aprobadas.madurando) == (0, 1)

    def test_una_no_ejecutable_se_cuenta_y_no_abre_episodio(self, tmp_path: Path) -> None:
        reg = _base(tmp_path)
        _decision(reg, "A", SESIONES[0], "COMPRAR", 0)
        _decision(reg, "A", SESIONES[1], "DESCARTAR")
        cuenta = madurez.contar(reg.conn, _tras(SESIONES[H]))
        assert cuenta.aprobadas == madurez.GrupoMadurez(0, 0, 1, 0) and cuenta.descartadas.maduros == 1

    def test_una_apertura_sin_ver_detiene_a_su_valor_y_al_final_deja_paso(self, tmp_path: Path) -> None:
        reg = _base(tmp_path)
        _decision(reg, "A", SESIONES[0], ejecutable=None)
        _decision(reg, "A", SESIONES[1])
        _decision(reg, "B", SESIONES[0])
        antes = madurez.contar(reg.conn, _tras(SESIONES[H - 2]))
        assert antes.sin_resolver == 1 and antes.aprobadas == madurez.GrupoMadurez(0, 1, 0, 0)
        despues = madurez.contar(reg.conn, _tras(SESIONES[H - 1]))
        assert despues.sin_resolver == 0 and despues.aprobadas == madurez.GrupoMadurez(1, 1, 0, 1)

    def test_lo_anterior_al_corte_no_entra(self, tmp_path: Path) -> None:
        reg = _base(tmp_path)
        _decision(reg, "A", SESIONES[0], cuando=madurez.CORTE - timedelta(seconds=1))
        _decision(reg, "B", SESIONES[0], cuando=madurez.CORTE)
        assert madurez.contar(reg.conn, _tras(SESIONES[H])).aprobadas.maduros == 1


class TestNoFiltraResultados:
    """Con el contrafactual real y los defectos reales del proveedor, el recuento no depende del stop."""

    SANA: ClassVar[Any] = (98.0, 97.0, 99.0)
    STOP: ClassVar[Any] = (98.0, 94.0, 96.0)

    def _actualizar(self, reg: RegistroIA, barras: Any, sesion: date) -> None:
        crudo = datos.ProveedorCrudo(_proveedor_ohlc(barras), lambda: _tras(sesion))
        universo = SimpleNamespace(get=lambda symbol: None)
        contrafactual.actualizar(reg.conn, crudo, universo, _tras(sesion), "1y", "1d", 0)

    def _historia(self, tmp_path: Path, stops: int, defecto: str) -> List[Any]:
        (tmp_path / str(stops)).mkdir()
        reg = _base(tmp_path / str(stops))
        for i, symbol in enumerate(("A", "B")):
            _decision(reg, symbol, SESIONES[0], ("COMPRAR", "DESCARTAR")[i], None)
            _decision(reg, symbol, SESIONES[3], ("DESCARTAR", "COMPRAR")[i], None)
        entrada = {s: {SESIONES[0]: self.STOP if i < stops else self.SANA} for i, s in enumerate(("A", "B"))}
        previa = date(2026, 11, 24)
        fotos = []
        self._actualizar(reg, entrada, SESIONES[0])
        fotos.append(madurez.contar(reg.conn, _tras(SESIONES[0])))
        if defecto == "retirada":
            rota = {s: {previa: self.SANA} for s in entrada}
        elif defecto == "sin_entrada":
            rota = {s: {previa: self.SANA, SESIONES[1]: self.SANA} for s in entrada}
        else:
            rota = {s: {**b, SESIONES[1]: (98.0, float("nan"), 99.0)} for s, b in entrada.items()}
        self._actualizar(reg, rota, SESIONES[1])
        for sesion in (SESIONES[1], SESIONES[H - 1], SESIONES[H + 3]):
            fotos.append(madurez.contar(reg.conn, _tras(sesion)))
        return fotos

    @pytest.mark.parametrize("defecto", ["retirada", "sin_entrada", "rota"])
    def test_el_recuento_es_el_mismo_con_cero_uno_o_dos_stops(self, tmp_path: Path, defecto: str) -> None:
        historias = [self._historia(tmp_path, stops, defecto) for stops in (0, 1, 2)]
        assert historias[0] == historias[1] == historias[2]
        assert historias[0][0].aprobadas.madurando == 1 and historias[0][2].aprobadas.maduros == 1

    def test_la_entrada_no_se_reescribe_y_las_anteriores_al_cambio_se_completan(self, tmp_path: Path) -> None:
        reg = _base(tmp_path)
        _decision(reg, "A", SESIONES[0], ejecutable=None)
        self._actualizar(reg, {"A": {SESIONES[0]: self.STOP}}, SESIONES[0])
        # Una base anterior a este cambio: definitiva y sin su fila de entrada.
        antes = reg.conn.execute("SELECT * FROM ia_contrafactual").fetchall()
        reg.conn.execute("DELETE FROM ia_contrafactual_entrada")
        self._actualizar(reg, {"A": {SESIONES[0]: self.SANA}}, SESIONES[0])
        assert reg.conn.execute("SELECT ejecutable FROM ia_contrafactual_entrada").fetchone()[0] == 1
        assert [tuple(f) for f in reg.conn.execute("SELECT * FROM ia_contrafactual")] == [tuple(f) for f in antes]

    def test_no_lee_la_tabla_de_desenlaces_ni_escribe(self, tmp_path: Path) -> None:
        reg = _base(tmp_path)
        _decision(reg, "A", SESIONES[0])

        def autorizar(accion: int, tabla: Any, *_r: Any) -> int:
            prohibida = accion == sqlite3.SQLITE_READ and tabla == "ia_contrafactual"
            escribe = accion in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE)
            return sqlite3.SQLITE_DENY if prohibida or escribe else sqlite3.SQLITE_OK

        reg.conn.set_authorizer(autorizar)
        assert madurez.contar(reg.conn, _tras(SESIONES[H])).aprobadas.maduros == 1


class TestTocaEvaluar:
    def _llenar(self, reg: RegistroIA, aprobadas: int, descartadas: int) -> None:
        for i in range(aprobadas):
            _decision(reg, f"A{i}", SESIONES[0])
        for i in range(descartadas):
            _decision(reg, f"B{i}", SESIONES[0], "DESCARTAR")

    @pytest.mark.parametrize("a, b, toca", [(50, 50, True), (49, 60, False), (60, 49, False)])
    def test_hace_falta_el_objetivo_en_los_dos_grupos(self, tmp_path: Path, a: int, b: int, toca: bool) -> None:
        reg = _base(tmp_path)
        self._llenar(reg, a, b)
        assert madurez.contar(reg.conn, _tras(SESIONES[H])).toca_evaluar is toca

    @pytest.mark.parametrize("a, b, minimo", [(30, 30, True), (29, 40, False)])
    def test_la_fecha_limite_manda_y_declara_el_minimo(self, tmp_path: Path, a: int, b: int, minimo: bool) -> None:
        reg = _base(tmp_path)
        self._llenar(reg, a, b)
        assert not madurez.contar(reg.conn, datetime(2027, 5, 30, 23, 59, tzinfo=timezone.utc)).toca_evaluar
        cuenta = madurez.contar(reg.conn, datetime(2027, 5, 31, 0, 0, tzinfo=timezone.utc))
        assert cuenta.toca_evaluar and cuenta.minimo_alcanzado is minimo
        texto = madurez.texto_avisos(cuenta)[0][1]
        assert ("INCONCLUSO" in texto) is not minimo

    def test_el_aviso_sale_una_sola_vez(self, tmp_path: Path) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        reg.guardar_paquete(paquete_compra())
        contrafactual.asegurar_esquema(reg.conn)
        self._llenar(reg, 50, 50)
        cuenta = madurez.contar(reg.conn, _tras(SESIONES[H]))
        assert telegram.encolar_madurez(cartera_ia, cuenta) == 1 and telegram.encolar_madurez(cartera_ia, cuenta) == 0


class TestCongelacion:
    def _llamada(self, reg: RegistroIA, pasada_id: int, prompt: str, modelo: str, cuando: datetime) -> None:
        reg.guardar_llamada(
            pasada_id=pasada_id, asesor="oportunidad", provider="anthropic", model=modelo, prompt_version=prompt,
            schema_version="1", input_hash=paquete_compra().input_hash, input_source_ids="[]", observaciones="[]",
            analysis_timestamp=cuando.isoformat(), estado="OK", coste_eur=0.0, created_at=cuando.isoformat(timespec="seconds"),
        )

    def test_un_prompt_o_un_modelo_distintos_tras_el_corte_se_avisan(self, tmp_path: Path) -> None:
        reg = _base(tmp_path)
        pasada_id = reg.abrir_pasada(TRAS_CORTE, "activo", "sha")
        self._llamada(reg, pasada_id, "viejo", "m0", madurez.CORTE - timedelta(days=1))
        self._llamada(reg, pasada_id, "v", "m", TRAS_CORTE)
        assert madurez.contar(reg.conn, TRAS_CORTE).congelacion_rota == ()
        self._llamada(reg, pasada_id, "v2", "m2", TRAS_CORTE)
        cuenta = madurez.contar(reg.conn, TRAS_CORTE)
        assert len(cuenta.congelacion_rota) == 2 and "congelada" in madurez.texto_avisos(cuenta)[0][1]

    def test_la_estrategia_sigue_siendo_la_del_corte(self) -> None:
        """Si falla, se ha cambiado algo que decide operaciones: cerrar la muestra antes de tocar la huella (D-83)."""

        assert madurez.huella_estrategia() == madurez.HUELLA_CONGELADA

    @pytest.mark.parametrize("fichero", ["config.yaml", "advisor/analysis/levels.py", "superbot/ia/prompts/riesgo.md"])
    def test_cambiar_lo_que_decide_cambia_la_huella(self, tmp_path: Path, fichero: str) -> None:
        raiz = tmp_path / "copia"
        for nombre in ("advisor", "superbot"):
            shutil.copytree(nombre, raiz / nombre, ignore=shutil.ignore_patterns("__pycache__"))
        for nombre in ("config.yaml", "universe.yaml", "exchange_overrides.yaml"):
            shutil.copy(nombre, raiz / nombre)
        assert madurez.huella_estrategia(raiz) == madurez.HUELLA_CONGELADA
        (raiz / fichero).write_text((raiz / fichero).read_text(encoding="utf-8") + "\n#x\n", encoding="utf-8")
        assert madurez.huella_estrategia(raiz) != madurez.HUELLA_CONGELADA

    @pytest.mark.parametrize("parametro, rompe", [("tope_eur_mes", False), ("cache_horas", False), ("score_min", True)])
    def test_solo_rompe_un_parametro_que_decide(self, tmp_path: Path, parametro: str, rompe: bool) -> None:
        reg = _base(tmp_path)
        params = asdict(POLITICA)
        reg.conn.execute(
            "INSERT INTO ia_politica_cambio (anterior, nueva, motivo, created_at) VALUES (?, ?, 'm', ?)",
            (json.dumps({"id": "x", "params": params}), json.dumps({"id": "x", "params": {**params, parametro: 99}}),
             TRAS_CORTE.isoformat(timespec="seconds")),
        )
        rota = madurez.contar(reg.conn, TRAS_CORTE).congelacion_rota
        assert bool(rota) is rompe and (not rompe or parametro in rota[0])

    def test_con_la_congelacion_rota_no_se_pide_evaluar(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        reg = _base(tmp_path)
        monkeypatch.setattr(madurez, "HUELLA_CONGELADA", "otra")
        cuenta = madurez.contar(reg.conn, datetime(2027, 6, 1, tzinfo=timezone.utc))
        assert not cuenta.toca_evaluar
        assert [clave.split(":")[1] for clave, _texto in madurez.texto_avisos(cuenta)] == ["congelacion"]


class TestSalidas:
    def test_el_dashboard_solo_ensena_recuentos(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc), 10_000.0)
        pagina = dashboard.render_html(cartera_ia, reg, "ahora")
        assert "0 de 50" in pagina and "sellados" in pagina

        def rota(*_a: Any, **_k: Any) -> Any:
            raise RuntimeError("calendario")

        monkeypatch.setattr(madurez, "contar", rota)
        assert "No se ha podido contar" in dashboard.render_html(cartera_ia, reg, "ahora")

    def test_el_cli_no_crea_una_base_si_la_ruta_esta_mal(self, tmp_path: Path) -> None:
        with pytest.raises(sqlite3.OperationalError):
            cli.main(["--db", str(tmp_path / "no" / "ia.db"), "madurez"])
        assert not (tmp_path / "no").exists()

    def test_el_cli_imprime_solo_recuentos(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _base(tmp_path).close()
        assert cli.main(["--db", str(tmp_path / "ia.db"), "madurez"]) == 0
        salida = json.loads(capsys.readouterr().out)
        assert set(salida) == {
            "aprobadas", "descartadas", "sin_resolver", "toca_evaluar", "motivo", "minimo_alcanzado", "congelacion_rota",
        }
        assert set(salida["aprobadas"]) == {"maduros", "madurando", "no_ejecutables", "sin_entrada"}

    def test_un_fallo_al_contar_no_detiene_la_pasada(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc), 10_000.0)
        llamadas: List[int] = []

        def rota(*_a: Any, **_k: Any) -> Any:
            llamadas.append(1)
            raise RuntimeError("calendario")

        monkeypatch.setattr(pasada.madurez, "contar", rota)
        resultado, _reg = _pasada(
            tmp_path, monkeypatch, [_analisis("A")], ClienteFalso(por_defecto=compra_ok()), cartera_ia=cartera_ia,
            registro_existente=reg, proveedor=_proveedor_ohlc({}),
        )
        assert llamadas == [1] and resultado.status == "OK" and resultado.compras == ["A"]

    def test_el_contrafactual_no_ofrece_ninguna_lectura_de_rendimiento(self) -> None:
        assert not any(hasattr(contrafactual, nombre) for nombre in ("resumen", "Grupo"))
