"""Superbot con IA, Entrega C (fase 1): cartera paper, contabilidad y stop obligatorio."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import pytest

from superbot.ia.cartera import (
    DATOS_INCOMPLETOS,
    GAP_BAJO_STOP,
    NO_TOCADO,
    STOP_TOCADO,
    CarteraIA,
    CarteraInactiva,
    CarteraPoliticaDistinta,
    PosicionYaCerrada,
    construir_estado_cartera,
    evaluar_stop,
    verificar_stops,
)
from tests.test_superbot_ia import ClienteFalso, _analisis, _pasada, registro

T_ACTIVACION = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)
CONFIG_SIN_RETRASO = SimpleNamespace(data_quality=SimpleNamespace(settlement_minutes=0))


def _cartera(tmp_path: Any) -> tuple[CarteraIA, Any]:
    """Comparte la base con ``_pasada``: ``CarteraIA`` e ``ia_decision`` deben vivir en la misma conexión."""

    reg = registro(tmp_path)
    return CarteraIA(reg.conn), reg


def _abrir(
    cartera_ia: CarteraIA, symbol: str = "A", stop: float = 90.0, entry_price: float = 100.0, units: float = 10.0,
    entry_session: date = date(2026, 11, 3), currency: str = "EUR",
) -> int:
    return cartera_ia.abrir_posicion(
        symbol=symbol, market="NYSE", currency=currency, units=units, entry_price=entry_price,
        entry_price_eur=entry_price, entry_session=entry_session, decision_apertura_id=None, stop=stop,
        invalidation_level=stop, entry_max=105.0, target1=110.0, target2=115.0, rr_minimo=1.5, instante=T_ACTIVACION,
    )


def _proveedor_ohlc(
    barras: Dict[str, Dict[date, Tuple[float, float, float]]], fx_eur_usd: Optional[float] = None,
) -> Any:
    """Falso proveedor: ``get_raw_history`` sirve Open/Low/Close por sesión; ``get_last_close`` el FX."""

    class _Prov:
        def get_raw_history(self, symbol: str, period: str = "2y", interval: str = "1d", **_kw: Any) -> pd.DataFrame:
            datos_symbol = barras.get(symbol)
            if not datos_symbol:
                return pd.DataFrame(columns=["Open", "Low", "Close"])
            sesiones = sorted(datos_symbol)
            return pd.DataFrame(
                {
                    "Open": [datos_symbol[s][0] for s in sesiones], "Low": [datos_symbol[s][1] for s in sesiones],
                    "Close": [datos_symbol[s][2] for s in sesiones],
                },
                index=[pd.Timestamp(s) for s in sesiones],
            )

        def get_last_close(self, pair: str) -> Tuple[Optional[float], Optional[pd.Timestamp]]:
            if pair == "EURUSD=X" and fx_eur_usd is not None:
                return fx_eur_usd, pd.Timestamp(T_ACTIVACION)
            return None, None

    return _Prov()


class _FxFake:
    """Evita depender de ``FxConverter``/red en las pruebas unitarias de ``verificar_stops``."""

    def __init__(self, tasa_no_eur: Optional[float]) -> None:
        self._tasa_no_eur = tasa_no_eur

    def rate(self, currency: str) -> Optional[float]:
        return 1.0 if currency == "EUR" else self._tasa_no_eur


# --- evaluar_stop (función pura) ---------------------------------------------------


class TestEvaluarStop:
    def test_no_tocado(self) -> None:
        r = evaluar_stop(stop=90.0, open_native=100.0, low_native=95.0)
        assert r.verificable and not r.disparado and r.precio_fill is None and r.motivo == NO_TOCADO

    def test_tocado_en_el_minimo_ejecuta_al_stop(self) -> None:
        r = evaluar_stop(stop=90.0, open_native=98.0, low_native=88.0)
        assert r.verificable and r.disparado and r.precio_fill == 90.0 and r.motivo == STOP_TOCADO

    def test_gap_bajo_el_stop_ejecuta_a_la_apertura(self) -> None:
        r = evaluar_stop(stop=90.0, open_native=85.0, low_native=80.0)
        assert r.verificable and r.disparado and r.precio_fill == 85.0 and r.motivo == GAP_BAJO_STOP

    @pytest.mark.parametrize(
        "stop,open_native,low_native",
        [
            (90.0, float("nan"), 95.0), (90.0, 100.0, float("nan")), (90.0, 0.0, 95.0), (90.0, -1.0, 95.0),
            (float("nan"), 100.0, 95.0), (0.0, 100.0, 95.0), (-1.0, 100.0, 95.0),
        ],
    )
    def test_datos_incompletos_nunca_se_declara_a_salvo(self, stop: float, open_native: float, low_native: float) -> None:
        r = evaluar_stop(stop=stop, open_native=open_native, low_native=low_native)
        assert not r.verificable and not r.disparado and r.precio_fill is None and r.motivo == DATOS_INCOMPLETOS

    def test_el_stop_toca_exactamente_en_el_minimo(self) -> None:
        r = evaluar_stop(stop=90.0, open_native=95.0, low_native=90.0)
        assert r.disparado and r.precio_fill == 90.0


# --- activación ----------------------------------------------------------------------


class TestActivacion:
    def test_nace_inactiva(self, tmp_path: Any) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        assert not cartera_ia.activa()
        assert cartera_ia.cash_eur() == 0.0

    def test_activar_es_idempotente(self, tmp_path: Any) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        assert cartera_ia.activar(T_ACTIVACION, 10_000.0) is True
        assert cartera_ia.activa() and cartera_ia.cash_eur() == 10_000.0
        assert cartera_ia.activar(T_ACTIVACION, 999.0) is False
        # El segundo intento, con otro capital, no cambia nada: no se reactiva por encima.
        assert cartera_ia.cash_eur() == 10_000.0
        assert cartera_ia.verificar_invariante_contable()

    def test_no_reactiva_una_cartera_inactivada_con_otro_estado(self, tmp_path: Any) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.conn.execute(
            "INSERT INTO ia_cartera (id, estado, cash_eur, updated_at) VALUES (1, 'INACTIVA', 0, ?)", ("x",)
        )
        with pytest.raises(CarteraPoliticaDistinta):
            cartera_ia.activar(T_ACTIVACION, 10_000.0)


# --- apertura y cierre de posiciones -------------------------------------------------


class TestPosiciones:
    def test_abrir_posicion_descuenta_el_efectivo_y_registra_el_movimiento(self, tmp_path: Any) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, entry_price=100.0, units=10.0)
        assert cartera_ia.cash_eur() == 10_000.0 - 1_000.0
        assert cartera_ia.verificar_invariante_contable()
        abiertas = cartera_ia.posiciones_abiertas()
        assert len(abiertas) == 1 and abiertas[0].symbol == "A" and abiertas[0].stop == 90.0
        # Un día calendario antes de la entrada: la propia sesión de entrada también se verifica.
        assert abiertas[0].stop_verificado_hasta == date(2026, 11, 2)

    def test_no_se_pueden_abrir_dos_posiciones_del_mismo_symbol_a_la_vez(self, tmp_path: Any) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A")
        with pytest.raises(sqlite3.IntegrityError):
            _abrir(cartera_ia, symbol="A")

    def test_no_se_abre_una_posicion_sin_cartera_activa(self, tmp_path: Any) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        with pytest.raises(CarteraInactiva):
            _abrir(cartera_ia, symbol="A")
        assert cartera_ia.posiciones_abiertas() == ()
        assert cartera_ia.verificar_invariante_contable()  # nada se movió: 0 == 0

    def test_cerrar_posicion_liquida_el_efectivo_y_calcula_el_pnl(self, tmp_path: Any) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, entry_price=100.0, units=10.0)
        posicion = cartera_ia.posiciones_abiertas()[0]
        cartera_ia.cerrar_posicion(
            posicion, exit_price=110.0, exit_price_eur=110.0, exit_session=date(2026, 11, 4), origen="DECISION_IA",
            motivo="CAUSA_VERIFICADA",
        )
        assert cartera_ia.posiciones_abiertas() == ()
        # Entró con 1.000 EUR (10 x 100) y salió con 1.100 (10 x 110): +100 EUR de beneficio.
        assert cartera_ia.cash_eur() == pytest.approx(10_000.0 + 100.0)
        assert cartera_ia.verificar_invariante_contable()

    def test_no_se_puede_liquidar_dos_veces_la_misma_posicion(self, tmp_path: Any) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 1_000.0)
        _abrir(cartera_ia, entry_price=100.0, units=1.0)  # 100 EUR
        posicion = cartera_ia.posiciones_abiertas()[0]
        cartera_ia.cerrar_posicion(
            posicion, exit_price=110.0, exit_price_eur=110.0, exit_session=date(2026, 11, 4), origen="DECISION_IA",
            motivo="m",
        )
        cash_tras_primer_cierre = cartera_ia.cash_eur()
        with pytest.raises(PosicionYaCerrada):
            cartera_ia.cerrar_posicion(
                posicion, exit_price=110.0, exit_price_eur=110.0, exit_session=date(2026, 11, 4),
                origen="DECISION_IA", motivo="m",
            )
        assert cartera_ia.cash_eur() == cash_tras_primer_cierre  # el segundo intento no movió nada
        assert cartera_ia.conn.execute("SELECT COUNT(*) FROM ia_fill WHERE lado = 'VENTA'").fetchone()[0] == 1
        assert cartera_ia.verificar_invariante_contable()

    def test_se_puede_reabrir_el_mismo_symbol_tras_cerrarlo(self, tmp_path: Any) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A")
        posicion = cartera_ia.posiciones_abiertas()[0]
        cartera_ia.cerrar_posicion(
            posicion, exit_price=95.0, exit_price_eur=95.0, exit_session=date(2026, 11, 4), origen="STOP_OBLIGATORIO",
            motivo=STOP_TOCADO,
        )
        _abrir(cartera_ia, symbol="A")  # no debe chocar con la unicidad: la anterior ya está CERRADA
        assert len(cartera_ia.posiciones_abiertas()) == 1


# --- invariante contable --------------------------------------------------------------


class TestInvarianteContable:
    def test_falla_si_hay_movimientos_sin_cartera_detras(self, tmp_path: Any) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        # Simula el escenario que antes pasaba inadvertido: un movimiento sin fila de cartera.
        cartera_ia.conn.execute(
            "INSERT INTO ia_movimiento (tipo, importe_eur, created_at) VALUES ('AJUSTE', -100.0, 'x')"
        )
        assert cartera_ia.verificar_invariante_contable() is False

    def test_una_cartera_virgen_es_consistente(self, tmp_path: Any) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        assert cartera_ia.verificar_invariante_contable() is True


# --- valoración causal de la cartera --------------------------------------------------


class TestConstruirEstadoCartera:
    def test_usa_el_cierre_ya_analizado_para_pnl_y_exposicion(self, tmp_path: Any) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)
        analizadas = {"A": _analisis("A", close=110.0)}
        estado, incidencias = construir_estado_cartera(cartera_ia, analizadas, {"EUR": 1.0})
        assert incidencias == {}
        assert estado.cash_eur == pytest.approx(9_000.0)
        assert estado.equity_eur == pytest.approx(9_000.0 + 10 * 110.0)
        assert estado.posiciones[0].pnl_pct == pytest.approx(10.0)
        assert estado.posiciones[0].exposicion_pct == pytest.approx(100.0 * 1_100.0 / estado.equity_eur)

    def test_sin_analisis_no_inventa_ganancia_y_lo_marca_como_incidencia(self, tmp_path: Any) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)
        estado, incidencias = construir_estado_cartera(cartera_ia, {}, {"EUR": 1.0})
        assert incidencias == {"A": "SIN_VALORACION_CAUSAL"}
        assert estado.posiciones[0].pnl_pct == 0.0

    def test_sin_tipo_de_cambio_tampoco_inventa_valoracion(self, tmp_path: Any) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)
        analizadas = {"A": _analisis("A", close=120.0)}
        estado, incidencias = construir_estado_cartera(cartera_ia, analizadas, {})
        assert incidencias == {"A": "SIN_VALORACION_CAUSAL"}
        assert estado.posiciones[0].pnl_pct == 0.0

    def test_excluir_de_ia_oculta_la_posicion_pero_no_el_equity(self, tmp_path: Any) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)
        analizadas = {"A": _analisis("A", close=110.0)}
        estado, _incidencias = construir_estado_cartera(cartera_ia, analizadas, {"EUR": 1.0}, excluir_de_ia=("A",))
        assert estado.posiciones == ()
        assert estado.equity_eur == pytest.approx(9_000.0 + 10 * 110.0)

    def test_ventas_ia_se_deriva_de_posiciones_cerradas_persistidas(self, tmp_path: Any) -> None:
        """Hallazgo de Codex: la espera de recompra no debe desaparecer al terminar la pasada del cierre."""

        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)
        posicion = cartera_ia.posiciones_abiertas()[0]
        cartera_ia.cerrar_posicion(
            posicion, exit_price=95.0, exit_price_eur=95.0, exit_session=date(2026, 11, 4), origen="STOP_OBLIGATORIO",
            motivo=STOP_TOCADO,
        )
        # Una llamada completamente nueva (como la de una pasada posterior), sin pasar nada explícito.
        estado, _incidencias = construir_estado_cartera(cartera_ia, {}, {"EUR": 1.0})
        assert estado.ventas_ia == {"A": date(2026, 11, 4)}


# --- integración con la pasada: stop obligatorio antes que la IA ----------------------


class TestStopObligatorioEnLaPasada:
    def test_stop_disparado_cierra_sin_llamar_a_la_ia_ni_gastar_presupuesto(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", stop=90.0, entry_price=100.0, units=10.0)
        proveedor = _proveedor_ohlc({"A": {date(2026, 11, 4): (85.0, 80.0, 88.0)}})  # abre ya por debajo del stop
        cliente = ClienteFalso(respuestas=[Exception("no debería llamarse"), Exception("no debería llamarse")])

        resultado, _reg2 = _pasada(
            tmp_path, monkeypatch, [], cliente, cartera_ia=cartera_ia, registro_existente=reg, proveedor=proveedor,
        )

        assert resultado.status == "OK"
        assert resultado.ventas == ["A"]
        assert cliente.llamadas == 0
        assert cartera_ia.posiciones_abiertas() == ()
        assert cartera_ia.verificar_invariante_contable()
        decisiones = reg.decisiones(resultado.pasada_id)
        assert not any(d["symbol"] == "A" and d["tipo"] == "POSICION" for d in decisiones)

    def test_stop_no_disparado_deja_evaluar_la_posicion_con_la_ia(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", stop=80.0, entry_price=100.0, units=10.0)
        # Cierre bajo la SMA: dispara el predicado CAUSA_SMA y pide dictamen, pero el precio no toca el stop.
        analisis_a = _analisis("A", close=85.0, sma=90.0)
        proveedor = _proveedor_ohlc({"A": {date(2026, 11, 4): (92.0, 86.0, 85.0)}})  # por encima del stop 80
        mantiene: Dict[str, Any] = {
            "decision": "MANTENER", "causa": None, "motivos": ["Todavía por encima del stop"],
            "riesgos": ["Puede seguir cayendo"], "datos_citados": ["posicion.cierre"],
        }
        cliente = ClienteFalso(por_defecto=mantiene)

        resultado, _reg2 = _pasada(
            tmp_path, monkeypatch, [analisis_a], cliente, cartera_ia=cartera_ia, registro_existente=reg,
            proveedor=proveedor,
        )

        assert resultado.status == "OK"
        assert resultado.ventas == []
        assert cliente.llamadas == 1
        assert len(cartera_ia.posiciones_abiertas()) == 1
        decisiones = reg.decisiones(resultado.pasada_id)
        fila = next(d for d in decisiones if d["symbol"] == "A")
        assert fila["resolucion"] == "MANTENER" and fila["aplicada"] == 1

    def test_descartar_en_modo_activo_se_marca_aplicada(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        candidata = _analisis("B", score=72.0)
        rechazo: Dict[str, Any] = {
            "decision": "DESCARTAR", "prioridad": "ALTA", "motivos": ["No cumple el riesgo"],
            "riesgos": ["Volatilidad alta"], "datos_citados": ["tecnico.rsi"],
        }
        cliente = ClienteFalso(por_defecto=rechazo)

        resultado, _reg2 = _pasada(tmp_path, monkeypatch, [candidata], cliente, cartera_ia=cartera_ia, registro_existente=reg)

        assert resultado.compras == []
        fila = next(d for d in reg.decisiones(resultado.pasada_id) if d["symbol"] == "B")
        assert fila["resolucion"] == "DESCARTAR" and fila["aplicada"] == 1

    def test_en_modo_registro_sin_cartera_ia_nunca_se_marca_aplicada(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        candidata = _analisis("B", score=72.0)
        rechazo: Dict[str, Any] = {
            "decision": "DESCARTAR", "prioridad": "ALTA", "motivos": ["No cumple el riesgo"],
            "riesgos": ["Volatilidad alta"], "datos_citados": ["tecnico.rsi"],
        }
        cliente = ClienteFalso(por_defecto=rechazo)

        resultado, reg = _pasada(tmp_path, monkeypatch, [candidata], cliente)  # sin cartera_ia: modo registro

        fila = next(d for d in reg.decisiones(resultado.pasada_id) if d["symbol"] == "B")
        assert fila["aplicada"] == 0

    def test_una_posicion_sin_datos_del_proveedor_no_se_declara_a_salvo_del_stop(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", stop=90.0)
        proveedor = _proveedor_ohlc({})  # el proveedor no tiene ninguna barra para "A"
        otra = _analisis("B", score=72.0)
        cliente = ClienteFalso(por_defecto={
            "decision": "DESCARTAR", "prioridad": "ALTA", "motivos": ["m"], "riesgos": ["r"], "datos_citados": ["tecnico.rsi"],
        })

        _resultado, _reg2 = _pasada(
            tmp_path, monkeypatch, [otra], cliente, cartera_ia=cartera_ia, registro_existente=reg, proveedor=proveedor,
        )

        assert len(cartera_ia.posiciones_abiertas()) == 1  # sigue abierta: no se tocó sin verificar

    def test_recupera_el_stop_de_una_sesion_perdida_aunque_la_ultima_barra_este_a_salvo(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Hallazgo de Codex: una sesión intermedia que rompió el stop no debe perderse para siempre."""

        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", stop=90.0, entry_session=date(2026, 11, 3))
        proveedor = _proveedor_ohlc({
            "A": {
                date(2026, 11, 4): (89.0, 85.0, 87.0),   # rompió el stop ese día (no comprobado hasta ahora)
                date(2026, 11, 5): (95.0, 93.0, 96.0),   # la barra "más reciente" ya está a salvo
            }
        })
        cliente = ClienteFalso(respuestas=[Exception("no debería llamarse")])

        resultado, _reg2 = _pasada(
            tmp_path, monkeypatch, [], cliente, cartera_ia=cartera_ia, registro_existente=reg, proveedor=proveedor,
        )

        assert resultado.ventas == ["A"]
        assert cliente.llamadas == 0
        fila = cartera_ia.conn.execute("SELECT exit_session, exit_price FROM ia_posicion WHERE symbol = 'A'").fetchone()
        assert fila["exit_session"] == "2026-11-04" and fila["exit_price"] == 89.0  # el hueco del día 4, no el del 5

    def test_stop_disparado_sin_tipo_de_cambio_no_se_ofrece_a_la_ia_como_mantenida(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Hallazgo de Codex: un stop confirmado no debe acabar pidiendo dictamen por un hueco contable."""

        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", stop=90.0, currency="USD")
        proveedor = _proveedor_ohlc(
            {"A": {date(2026, 11, 4): (85.0, 80.0, 88.0)}}, fx_eur_usd=None,  # FX no disponible
        )
        cliente = ClienteFalso(respuestas=[Exception("no debería llamarse"), Exception("no debería llamarse")])

        resultado, _reg2 = _pasada(
            tmp_path, monkeypatch, [], cliente, cartera_ia=cartera_ia, registro_existente=reg, proveedor=proveedor,
        )

        assert resultado.ventas == []  # no se pudo liquidar: sigue abierta
        assert cliente.llamadas == 0  # pero tampoco se le pidió dictamen a la IA
        assert len(cartera_ia.posiciones_abiertas()) == 1
        assert any("tipo de cambio" in incidencia for incidencia in resultado.incidencias)


# --- verificar_stops: cursor y sesión de entrada (segunda ronda de hallazgos de Codex) ------


class TestVerificarStopsCursor:
    def test_un_stop_sin_fx_no_se_pierde_en_la_pasada_siguiente(self, tmp_path: Any) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", stop=90.0, currency="USD")
        instante = T_ACTIVACION + timedelta(days=5)

        proveedor_1 = _proveedor_ohlc({"A": {date(2026, 11, 4): (85.0, 80.0, 88.0)}})
        cerradas_1, bloqueadas_1 = verificar_stops(cartera_ia, proveedor_1, instante, 0, _FxFake(None), [])
        assert cerradas_1 == {} and bloqueadas_1 == {"A"}
        assert cartera_ia.posiciones_abiertas()[0].stop_verificado_hasta < date(2026, 11, 4)

        # Pasada siguiente: aparece una barra posterior ya a salvo, pero el FX sigue sin resolverse.
        proveedor_2 = _proveedor_ohlc(
            {"A": {date(2026, 11, 4): (85.0, 80.0, 88.0), date(2026, 11, 5): (95.0, 93.0, 96.0)}}
        )
        cerradas_2, bloqueadas_2 = verificar_stops(cartera_ia, proveedor_2, instante, 0, _FxFake(None), [])
        # Sigue bloqueada por la sesión del día 4: el cursor no saltó a la del día 5 sin resolverla.
        assert bloqueadas_2 == {"A"} and cerradas_2 == {}

    def test_un_stop_sin_fx_se_cierra_en_cuanto_el_fx_esta_disponible(self, tmp_path: Any) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", stop=90.0, currency="USD")
        instante = T_ACTIVACION + timedelta(days=5)
        proveedor = _proveedor_ohlc({"A": {date(2026, 11, 4): (85.0, 80.0, 88.0)}})

        verificar_stops(cartera_ia, proveedor, instante, 0, _FxFake(None), [])
        cerradas, bloqueadas = verificar_stops(cartera_ia, proveedor, instante, 0, _FxFake(1.1), [])

        assert cerradas == {"A": date(2026, 11, 4)} and bloqueadas == set()
        assert cartera_ia.posiciones_abiertas() == ()

    def test_un_minimo_adverso_en_la_propia_sesion_de_entrada_tambien_se_verifica(self, tmp_path: Any) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", stop=90.0, entry_session=date(2026, 11, 3))
        # El mínimo del propio día de entrada rompe el stop.
        proveedor = _proveedor_ohlc({"A": {date(2026, 11, 3): (99.0, 85.0, 95.0)}})
        incidencias: List[str] = []

        cerradas, bloqueadas = verificar_stops(
            cartera_ia, proveedor, T_ACTIVACION + timedelta(days=5), 0, _FxFake(1.0), incidencias
        )

        assert cerradas == {"A": date(2026, 11, 3)} and bloqueadas == set()
