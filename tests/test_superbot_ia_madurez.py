"""Madurez del contrafactual: cuenta episodios por calendario, avisa una vez y no puede ver rendimientos."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Optional

import pytest

from advisor.data.calendars import expected_sessions
from superbot.ia import __main__ as cli
from superbot.ia import contrafactual, dashboard, madurez, pasada, telegram
from superbot.ia.registro import RegistroIA
from tests.test_superbot_ia import ClienteFalso, _analisis, _pasada, compra_ok, paquete_compra, registro
from tests.test_superbot_ia_cartera import _cartera, _proveedor_ohlc

SESIONES = expected_sessions("XETRA", date(2026, 11, 25), date(2027, 6, 30))
TRAS_CORTE = madurez.CORTE + timedelta(hours=5)
H = contrafactual.HORIZONTE_SESIONES


def _tras(sesion: date) -> datetime:
    """Con esa sesión de Xetra ya cerrada y liquidada."""

    return datetime(sesion.year, sesion.month, sesion.day, 22, 0, tzinfo=timezone.utc)


def _base(tmp_path: Path) -> RegistroIA:
    reg = registro(tmp_path)
    reg.guardar_paquete(paquete_compra())
    contrafactual.asegurar_esquema(reg.conn)
    return reg


def _decision(
    reg: RegistroIA, symbol: str, sesion: date, resolucion: str = "COMPRAR", estado: Optional[str] = "ABIERTA", *,
    final: int = 0, entrada: Optional[float] = 100.0, retorno: Optional[float] = None, cuando: datetime = TRAS_CORTE,
) -> None:
    pasada_id = reg.abrir_pasada(cuando, "activo", "sha")
    n = reg.conn.execute("SELECT COUNT(*) FROM ia_decision").fetchone()[0]
    cursor = reg.conn.execute(
        "INSERT INTO ia_decision (clave, pasada_id, policy, symbol, market, tipo, signal_session, target_session, "
        "target_open, decision_ts, input_hash, cuantitativo, votos, predicados, resolucion, motivo, aplicada, created_at) "
        "VALUES (?, ?, 'p', ?, 'XETRA', 'COMPRA', ?, ?, ?, ?, ?, '{}', '[]', '{}', ?, 'm', 1, ?)",
        (f"k{n}", pasada_id, symbol, sesion.isoformat(), sesion.isoformat(), cuando.isoformat(), cuando.isoformat(),
         paquete_compra().input_hash, resolucion, cuando.isoformat()),
    )
    if estado is not None:
        reg.conn.execute(
            "INSERT INTO ia_contrafactual (decision_id, symbol, resolucion, target_session, estado, entrada, retorno_pct, "
            "final, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'x')",
            (cursor.lastrowid, symbol, resolucion, sesion.isoformat(), estado, entrada, retorno, final),
        )


class TestContar:
    def test_madura_a_las_veinte_sesiones_y_no_antes(self, tmp_path: Path) -> None:
        reg = _base(tmp_path)
        _decision(reg, "A", SESIONES[0])
        assert madurez.contar(reg.conn, _tras(SESIONES[H - 2])).aprobadas == madurez.GrupoMadurez(0, 1, 0, 0)
        assert madurez.contar(reg.conn, _tras(SESIONES[H - 1])).aprobadas == madurez.GrupoMadurez(1, 0, 0, 0)

    def test_un_stop_no_adelanta_la_madurez_ni_cambia_el_recuento(self, tmp_path: Path) -> None:
        conteos: List[Any] = []
        for n, (estado, final, retorno) in enumerate((("STOP", 1, -9.0), ("ABIERTA", 0, 40.0), ("HORIZONTE", 1, 3.0))):
            (tmp_path / str(n)).mkdir()
            reg = _base(tmp_path / str(n))
            _decision(reg, "A", SESIONES[0], estado=estado, final=final, retorno=retorno)
            _decision(reg, "B", SESIONES[0], "DESCARTAR", estado=estado, final=final, retorno=retorno)
            conteos.append([madurez.contar(reg.conn, _tras(SESIONES[i])) for i in (0, 5, H - 1, H + 5)])
        assert conteos[0] == conteos[1] == conteos[2]

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
        _decision(reg, "A", SESIONES[0], "COMPRAR", "NO_EJECUTABLE", final=1, entrada=None)
        _decision(reg, "A", SESIONES[1], "DESCARTAR")
        cuenta = madurez.contar(reg.conn, _tras(SESIONES[H]))
        assert cuenta.aprobadas == madurez.GrupoMadurez(0, 0, 0, 1) and cuenta.descartadas.maduros == 1

    @pytest.mark.parametrize("estado", ["SIN_BARRA_DE_ENTRADA", "SPLIT_POSTERIOR"])
    def test_sin_datos_definitivo_se_excluye_y_no_abre_episodio(self, tmp_path: Path, estado: str) -> None:
        reg = _base(tmp_path)
        _decision(reg, "A", SESIONES[0], estado=estado, final=1, entrada=None)
        _decision(reg, "A", SESIONES[1])
        assert madurez.contar(reg.conn, _tras(SESIONES[H])).aprobadas == madurez.GrupoMadurez(1, 0, 1, 0)

    def test_datos_rotos_tras_la_entrada_se_excluyen_al_madurar(self, tmp_path: Path) -> None:
        reg = _base(tmp_path)
        _decision(reg, "A", SESIONES[0], estado="DATOS_INCOMPLETOS", final=1)
        assert madurez.contar(reg.conn, _tras(SESIONES[H])).aprobadas == madurez.GrupoMadurez(0, 0, 1, 0)

    @pytest.mark.parametrize("estado", [None, "PENDIENTE", "SIN_BARRA_DE_ENTRADA"])
    def test_una_sin_resolver_detiene_a_su_valor_y_no_a_los_demas(self, tmp_path: Path, estado: Optional[str]) -> None:
        reg = _base(tmp_path)
        _decision(reg, "A", SESIONES[0], estado=estado, entrada=None)
        _decision(reg, "A", SESIONES[1])
        _decision(reg, "B", SESIONES[0])
        cuenta = madurez.contar(reg.conn, _tras(SESIONES[H]))
        assert cuenta.sin_resolver == 1 and cuenta.aprobadas.maduros == 1

    def test_lo_anterior_al_corte_no_entra(self, tmp_path: Path) -> None:
        reg = _base(tmp_path)
        _decision(reg, "A", SESIONES[0], cuando=madurez.CORTE - timedelta(seconds=1))
        _decision(reg, "B", SESIONES[0], cuando=madurez.CORTE)
        assert madurez.contar(reg.conn, _tras(SESIONES[H])).aprobadas.maduros == 1

    def test_no_lee_ninguna_columna_de_rendimiento(self, tmp_path: Path) -> None:
        """El motor de sqlite veta las columnas de resultado: si algo las leyera, la consulta fallaría."""

        import sqlite3

        reg = _base(tmp_path)
        _decision(reg, "A", SESIONES[0], estado="STOP", final=1, retorno=-9.0)
        vetadas = {"salida", "sesiones", "hasta_session", "retorno_pct", "retorno_r", "retorno_corto_pct"}

        def autorizar(accion: int, tabla: Any, columna: Any, *_r: Any) -> int:
            leida = accion == sqlite3.SQLITE_READ and tabla == "ia_contrafactual" and columna in vetadas
            return sqlite3.SQLITE_DENY if leida else sqlite3.SQLITE_OK

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

    def test_el_cli_imprime_solo_recuentos(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _base(tmp_path).close()
        assert cli.main(["--db", str(tmp_path / "ia.db"), "madurez"]) == 0
        salida = json.loads(capsys.readouterr().out)
        assert set(salida) == {
            "aprobadas", "descartadas", "sin_resolver", "toca_evaluar", "motivo", "minimo_alcanzado", "congelacion_rota",
        }
        assert set(salida["aprobadas"]) == {"maduros", "madurando", "excluidos", "no_ejecutables"}

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
