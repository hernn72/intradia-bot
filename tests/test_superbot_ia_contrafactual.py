"""Contrafactual de las decisiones de compra: la simulación usa el gate y el stop del motor real,
no entra en otra sesión que la objetivo, y el resumen separa aprobadas de descartadas."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar, Dict, List, Tuple

import pytest

from superbot.ia import contrafactual, dashboard, datos
from superbot.ia.contrafactual import (
    ABIERTA,
    HORIZONTE,
    NO_EJECUTABLE,
    PENDIENTE,
    SIN_BARRA_DE_ENTRADA,
    STOP,
    simular,
)
from tests.test_superbot_ia import ClienteFalso, T, _analisis, _pasada, compra_ok
from tests.test_superbot_ia_cartera import _cartera, _proveedor_ohlc

NIVELES = {"stop": 95.0, "target2": 107.0, "entry_max": 101.0, "min_rr_ratio": 1.5}
OBJETIVO = date(2026, 11, 6)
T_ACTIVACION = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)


def _barras(*ohlc: Tuple[float, float, float], desde: date = OBJETIVO) -> List[contrafactual.Barra]:
    return [(desde + timedelta(days=i), o, low, c) for i, (o, low, c) in enumerate(ohlc)]


class TestSimular:
    def test_sin_la_sesion_objetivo_cerrada_sigue_pendiente(self) -> None:
        assert simular(NIVELES, _barras((98.0, 97.0, 99.0), desde=date(2026, 11, 5))[:1], OBJETIVO).estado == PENDIENTE

    def test_no_entra_en_otra_sesion_si_falta_la_objetivo(self) -> None:
        barras = _barras((98.0, 97.0, 99.0), desde=OBJETIVO + timedelta(days=1))
        d = simular(NIVELES, barras, OBJETIVO)
        assert d.estado == SIN_BARRA_DE_ENTRADA and not d.final

    def test_la_barra_de_entrada_que_llega_tarde_todavia_se_usa(self) -> None:
        tarde = _barras((98.0, 97.0, 99.0), (99.0, 98.0, 100.94))
        assert simular(NIVELES, tarde[1:], OBJETIVO).estado == SIN_BARRA_DE_ENTRADA
        assert simular(NIVELES, tarde, OBJETIVO).estado == ABIERTA

    def test_un_hueco_de_entrada_solo_es_definitivo_pasado_el_margen(self) -> None:
        posteriores = _barras(*[(98.0, 97.0, 99.0)] * contrafactual.MARGEN_SESIONES, desde=OBJETIVO + timedelta(days=1))
        assert not simular(NIVELES, posteriores[:-1], OBJETIVO).final
        assert simular(NIVELES, posteriores, OBJETIVO).final

    def test_un_dato_roto_en_el_recorrido_se_reintenta_y_conserva_el_retorno_corto(self) -> None:
        limpias = [(98.0, 97.0, 99.0)] * 7
        d = simular(NIVELES, _barras(*limpias, (99.0, float("nan"), 99.0)), OBJETIVO)
        assert d.estado == contrafactual.DATOS_INCOMPLETOS and not d.final and d.retorno_pct is None
        assert d.retorno_corto_pct == pytest.approx(100.0 * (99.0 / 98.0 - 1.0))
        arreglada = simular(NIVELES, _barras(*limpias, (99.0, 98.0, 99.0)), OBJETIVO)
        assert arreglada.estado == ABIERTA and arreglada.retorno_pct is not None

    def test_un_dato_roto_que_no_se_arregla_acaba_siendo_definitivo(self) -> None:
        muchas = [(98.0, float("nan"), 99.0)] + [(98.0, 97.0, 99.0)] * (
            contrafactual.HORIZONTE_SESIONES + contrafactual.MARGEN_SESIONES
        )
        assert simular(NIVELES, _barras(*muchas), OBJETIVO).final

    @pytest.mark.parametrize("dias, estado", [(0, contrafactual.SPLIT_POSTERIOR), (1, contrafactual.SPLIT_POSTERIOR), (-1, ABIERTA)])
    def test_un_split_desde_la_sesion_objetivo_excluye_la_decision(self, dias: int, estado: str) -> None:
        d = simular(NIVELES, _barras((98.0, 97.0, 99.0), (99.0, 98.0, 100.0)), OBJETIVO, [OBJETIVO + timedelta(days=dias)])
        assert d.estado == estado and d.final == (estado != ABIERTA) and (d.retorno_pct is None) == (estado != ABIERTA)

    def test_una_apertura_por_encima_del_maximo_no_es_ejecutable(self) -> None:
        d = simular(NIVELES, _barras((102.0, 101.0, 104.0)), OBJETIVO)
        assert d.estado == NO_EJECUTABLE and d.motivo_gate == "ABOVE_MAX_ENTRY" and d.retorno_pct is None and d.final

    def test_abierta_cuenta_a_su_ultimo_cierre(self) -> None:
        d = simular(NIVELES, _barras((98.0, 97.0, 99.0), (99.0, 98.0, 100.94)), OBJETIVO)
        assert d.estado == ABIERTA and not d.final and d.entrada == 98.0 and d.sesiones == 2
        assert d.retorno_pct == pytest.approx(3.0) and d.retorno_r == pytest.approx(2.94 / 3.0)
        assert d.retorno_corto_pct is None and d.hasta_session == OBJETIVO + timedelta(days=1)

    def test_el_stop_cierra_al_precio_del_stop(self) -> None:
        d = simular(NIVELES, _barras((98.0, 97.0, 99.0), (99.0, 94.0, 96.0), (96.0, 96.0, 120.0)), OBJETIVO)
        assert d.estado == STOP and d.final and d.salida == 95.0 and d.sesiones == 2
        assert d.retorno_r == pytest.approx(-1.0) and d.retorno_corto_pct == pytest.approx(d.retorno_pct)

    def test_un_hueco_bajo_el_stop_cierra_en_la_apertura(self) -> None:
        d = simular(NIVELES, _barras((98.0, 97.0, 99.0), (93.0, 92.0, 94.0)), OBJETIVO)
        assert d.estado == STOP and d.salida == 93.0 and d.retorno_r == pytest.approx(-5.0 / 3.0)

    def test_el_propio_dia_de_entrada_puede_tocar_el_stop(self) -> None:
        d = simular(NIVELES, _barras((98.0, 94.5, 99.0)), OBJETIVO)
        assert d.estado == STOP and d.salida == 95.0 and d.sesiones == 1

    def test_se_cierra_al_horizonte_y_el_corto_usa_su_propia_sesion(self) -> None:
        planas = [(98.0, 97.0, 98.0 + i) for i in range(contrafactual.HORIZONTE_SESIONES + 3)]
        d = simular(NIVELES, _barras(*planas), OBJETIVO)
        assert d.estado == HORIZONTE and d.final and d.sesiones == contrafactual.HORIZONTE_SESIONES
        assert d.salida == 98.0 + contrafactual.HORIZONTE_SESIONES - 1
        assert d.retorno_corto_pct == pytest.approx(100.0 * (98.0 + contrafactual.HORIZONTE_CORTO - 1) / 98.0 - 100.0)

    def test_niveles_incompletos_no_inventan_resultado(self) -> None:
        d = simular({"stop": 95.0}, _barras((98.0, 97.0, 99.0)), OBJETIVO)
        assert d.estado == contrafactual.DATOS_INCOMPLETOS and d.retorno_pct is None and d.final


def _decidir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, respuestas: Dict[str, Any]) -> Any:
    """Una pasada en modo registro que deja una decisión de compra por valor, con sus niveles."""

    class _PorValor(ClienteFalso):
        def llamar(self, system: str, mensaje: str, esquema: Any) -> Any:
            valor = next(s for s in respuestas if f'"valor": "{s}"' in mensaje)
            self.por_defecto = respuestas[valor]
            return super().llamar(system, mensaje, esquema)

    _resultado, reg = _pasada(tmp_path, monkeypatch, [_analisis(s) for s in respuestas], _PorValor())
    return reg


def _universo() -> Any:
    return SimpleNamespace(get=lambda symbol: None)


def _actualizar(reg: Any, barras: Dict[str, Dict[date, Tuple[float, float, float]]], instante: datetime) -> int:
    crudo = datos.ProveedorCrudo(_proveedor_ohlc(barras), lambda: instante)
    return contrafactual.actualizar(reg.conn, crudo, _universo(), instante, "1y", "1d", 0)


class TestActualizarYResumen:
    RESPUESTAS: ClassVar[Dict[str, Any]] = {
        "A": compra_ok(), "B": compra_ok(decision="DESCARTAR", prioridad="BAJA"),
    }
    DESPUES = datetime(2026, 11, 10, 23, 0, tzinfo=timezone.utc)

    def test_sigue_a_las_aprobadas_y_a_las_descartadas(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        reg = _decidir(tmp_path, monkeypatch, self.RESPUESTAS)
        barras = {
            "A": {OBJETIVO: (98.0, 97.0, 99.0), date(2026, 11, 9): (99.0, 98.0, 100.94)},
            "B": {OBJETIVO: (98.0, 97.0, 99.0), date(2026, 11, 9): (99.0, 94.0, 96.0)},
        }

        assert _actualizar(reg, barras, self.DESPUES) == 2

        aprobadas, descartadas = contrafactual.resumen(reg.conn)
        assert (aprobadas.resolucion, aprobadas.decisiones, aprobadas.seguidas, aprobadas.stops) == ("COMPRAR", 1, 1, 0)
        assert aprobadas.retorno_medio_pct == pytest.approx(3.0) and aprobadas.positivas_pct == pytest.approx(100.0)
        assert (descartadas.decisiones, descartadas.stops) == (1, 1) and descartadas.r_medio == pytest.approx(-1.0)

    def test_lo_definitivo_no_se_recalcula_y_lo_abierto_si(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        reg = _decidir(tmp_path, monkeypatch, self.RESPUESTAS)
        barras = {
            "A": {OBJETIVO: (98.0, 97.0, 99.0)},
            "B": {OBJETIVO: (98.0, 94.0, 96.0)},
        }
        _actualizar(reg, barras, self.DESPUES)
        barras["A"][date(2026, 11, 9)] = (99.0, 98.0, 107.8)
        barras["B"][date(2026, 11, 9)] = (150.0, 150.0, 150.0)

        assert _actualizar(reg, barras, self.DESPUES) == 1

        aprobadas, descartadas = contrafactual.resumen(reg.conn)
        assert aprobadas.retorno_medio_pct == pytest.approx(10.0) and descartadas.r_medio == pytest.approx(-1.0)

    def test_una_barra_sin_cerrar_no_se_usa(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """La barra de la sesión objetivo tocaría el stop, pero a esa hora aún no ha cerrado."""

        reg = _decidir(tmp_path, monkeypatch, {"SAP.DE": compra_ok()})
        reg.conn.execute("UPDATE ia_decision SET market = 'XETRA'")
        barras = {"SAP.DE": {date(2026, 11, 5): (98.0, 97.0, 99.0), OBJETIVO: (98.0, 90.0, 91.0)}}
        cierre = datetime(2026, 11, 6, 16, 30, tzinfo=timezone.utc)  # 17:30 de Berlín
        crudo = lambda: datos.ProveedorCrudo(_proveedor_ohlc(barras), lambda: cierre)  # noqa: E731

        contrafactual.actualizar(reg.conn, crudo(), _universo(), cierre + timedelta(minutes=19), "1y", "1d", 20)
        antes = reg.conn.execute("SELECT estado FROM ia_contrafactual").fetchone()[0]
        contrafactual.actualizar(reg.conn, crudo(), _universo(), cierre + timedelta(minutes=21), "1y", "1d", 20)
        despues = reg.conn.execute("SELECT estado FROM ia_contrafactual").fetchone()[0]

        assert (antes, despues) == (PENDIENTE, STOP)

    def test_una_fila_ilegible_no_impide_seguir_a_las_demas(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        reg = _decidir(tmp_path, monkeypatch, self.RESPUESTAS)
        reg.conn.execute("UPDATE ia_decision SET cuantitativo = '{roto' WHERE symbol = 'A'")

        assert _actualizar(reg, {"B": {OBJETIVO: (98.0, 97.0, 99.0)}}, self.DESPUES) == 1

    def test_el_resumen_separa_cerradas_y_sin_datos(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        reg = _decidir(tmp_path, monkeypatch, self.RESPUESTAS)
        barras = {
            "A": {date(2026, 11, 9): (98.0, 97.0, 99.0)},
            "B": {OBJETIVO: (98.0, 97.0, 99.0), date(2026, 11, 9): (99.0, 94.0, 96.0)},
        }
        _actualizar(reg, barras, self.DESPUES)

        aprobadas, descartadas = contrafactual.resumen(reg.conn)

        assert (aprobadas.decisiones, aprobadas.sin_datos, aprobadas.seguidas, aprobadas.cerradas) == (1, 1, 0, 0)
        assert aprobadas.retorno_cerradas_pct is None
        assert (descartadas.cerradas, descartadas.sin_datos) == (1, 0)
        assert descartadas.retorno_cerradas_pct == pytest.approx(100.0 * (95.0 / 98.0 - 1.0))

    def test_una_decision_pendiente_no_cuenta_en_el_resumen(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        reg = _decidir(tmp_path, monkeypatch, self.RESPUESTAS)

        _actualizar(reg, {"A": {date(2026, 11, 5): (98.0, 97.0, 99.0)}}, T)

        assert [g.decisiones for g in contrafactual.resumen(reg.conn)] == [0, 0]

    def test_un_valor_sin_serie_no_impide_seguir_a_los_demas(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        reg = _decidir(tmp_path, monkeypatch, self.RESPUESTAS)

        class _RotoParaA:
            def get_history(self, symbol: str, **_k: Any) -> Any:
                if symbol == "A":
                    raise RuntimeError("sin datos")
                return _proveedor_ohlc({"B": {OBJETIVO: (98.0, 97.0, 99.0)}}).get_raw_history(symbol)

        assert contrafactual.actualizar(reg.conn, _RotoParaA(), _universo(), self.DESPUES, "1y", "1d", 0) == 1

    def test_la_pasada_activa_lo_actualiza_y_un_fallo_no_la_detiene(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        config = SimpleNamespace(
            data_quality=SimpleNamespace(settlement_minutes=0),
            horizonte=lambda nombre: SimpleNamespace(period="1y", interval="1d"),
        )
        llamadas: List[Any] = []

        def roto(*args: Any, **_k: Any) -> int:
            llamadas.append(args)
            raise RuntimeError("disco lleno")

        monkeypatch.setattr(contrafactual, "actualizar", roto)
        resultado, _reg = _pasada(
            tmp_path, monkeypatch, [_analisis("A")], ClienteFalso(por_defecto=compra_ok()), cartera_ia=cartera_ia,
            registro_existente=reg, proveedor=_proveedor_ohlc({}), config=config,
        )

        assert len(llamadas) == 1 and resultado.status == "OK" and resultado.compras == ["A"]
        assert resultado.incidencias == []


class TestDashboard:
    def test_muestra_los_dos_grupos_y_la_advertencia(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        reg = _decidir(tmp_path, monkeypatch, TestActualizarYResumen.RESPUESTAS)
        _actualizar(reg, {"A": {OBJETIVO: (98.0, 97.0, 100.94)}, "B": {OBJETIVO: (98.0, 94.0, 96.0)}},
                    TestActualizarYResumen.DESPUES)

        seccion = dashboard._contrafactual_section(contrafactual.resumen(reg.conn))

        assert "Aprobadas por el comité" in seccion and "Descartadas" in seccion
        assert "3,00 %" in seccion and "no demuestra nada" in seccion

    def test_sin_decisiones_no_lanza(self, tmp_path: Path) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)

        pagina = dashboard.render_html(cartera_ia, reg, "ahora")

        assert "Aprobadas frente a descartadas" in pagina and "N/D" in pagina
