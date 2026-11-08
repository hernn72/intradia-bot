"""Superbot con IA, Entrega C (fase 3): VENDER/MANTENER integrados con la cartera paper.

Cubre las diez condiciones de la autorización de fase 3: una venta IA decidida al cierre de la
sesión N nunca se ejecuta antes de la apertura siguiente; el stop obligatorio tiene prioridad
absoluta sobre una venta IA pendiente de la misma posición; nada se liquida dos veces; el efectivo,
las posiciones, los fills y el PnL quedan correctos tras una venta; las decisiones de modo
``registro`` jamás producen un efecto durable; y la recuperación tras una caída entre decisión,
orden y ``aplicada`` no pierde nada ni duplica nada.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import pytest

from superbot.ia.cartera import (
    CarteraIA,
    OrdenYaResuelta,
    PosicionYaCerrada,
    construir_estado_cartera,
    fx_en_sesion,
    procesar_pendientes,
)
from superbot.ia.paquete import EstadoCartera, Observacion, PosicionIA
from tests.test_superbot_ia import APERTURA, ClienteFalso, T, _analisis, _pasada, compra_ok, posicion_ok
from tests.test_superbot_ia_cartera import _abrir, _cartera, _proveedor_ohlc
from tests.test_superbot_ia_fase2 import SESION_OBJETIVO

T_ACTIVACION = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)
NIVELES_COMPRA = {
    "stop": 90.0, "invalidation_level": 90.0, "entry_max": 105.0, "target1": 110.0, "target2": 115.0,
    "min_rr_ratio": 1.5,
}


def _comprar_pendiente(
    cartera_ia: CarteraIA, reg: Any, symbol: str = "A", target_session: date = SESION_OBJETIVO, currency: str = "EUR",
) -> int:
    hash_ = f"hc-{symbol}-{target_session.isoformat()}"
    reg.conn.execute(
        "INSERT INTO ia_paquete (input_hash, tipo, symbol, contenido) VALUES (?, 'COMPRA', ?, '{}')", (hash_, symbol)
    )
    pasada_id = reg.abrir_pasada(T_ACTIVACION, "activo", "sha")
    decision_id = reg.guardar_decision(
        clave=f"{symbol}|c|2026-11-05|{target_session.isoformat()}|x", pasada_id=pasada_id, symbol=symbol,
        market="NYSE", tipo="COMPRA", signal_session="2026-11-05", target_session=target_session.isoformat(),
        target_open=APERTURA.isoformat(), decision_ts=T_ACTIVACION.isoformat(), input_hash=hash_,
        cuantitativo="{}", votos="{}", predicados=None, resolucion="COMPRAR", motivo="APROBADA_POR_AMBOS",
        prioridad="ALTA", causa=None,
    )
    cartera_ia.materializar_decision_compra(
        decision_id=decision_id, symbol=symbol, market="NYSE", currency=currency, target_session=target_session,
        target_open=APERTURA, niveles=NIVELES_COMPRA, instante=T_ACTIVACION,
    )
    return decision_id


def _vender_pendiente(
    cartera_ia: CarteraIA, reg: Any, position_id: int, symbol: str = "A", currency: str = "EUR",
    target_session: date = SESION_OBJETIVO, causa: str = "CIERRE_BAJO_SMA",
) -> int:
    """Como ``_crear_decision_y_orden`` de la fase 2, para una decisión ``VENDER``."""

    hash_ = f"hv-{symbol}-{position_id}-{causa}"
    reg.conn.execute(
        "INSERT INTO ia_paquete (input_hash, tipo, symbol, contenido) VALUES (?, 'POSICION', ?, '{}')",
        (hash_, symbol),
    )
    pasada_id = reg.abrir_pasada(T_ACTIVACION, "activo", "sha")
    decision_id = reg.guardar_decision(
        clave=f"{symbol}|{causa}|2026-11-05|{target_session.isoformat()}|x", pasada_id=pasada_id, symbol=symbol,
        market="NYSE", tipo="POSICION", signal_session="2026-11-05", target_session=target_session.isoformat(),
        target_open=APERTURA.isoformat(), decision_ts=T_ACTIVACION.isoformat(), input_hash=hash_,
        cuantitativo="{}", votos="{}", predicados=None, resolucion="VENDER", motivo="CAUSA_VERIFICADA", prioridad=None,
        causa=causa,
    )
    cartera_ia.materializar_decision_venta(
        decision_id=decision_id, position_id=position_id, symbol=symbol, market="NYSE", currency=currency,
        target_session=target_session, target_open=APERTURA, causa=causa, instante=T_ACTIVACION,
    )
    return decision_id


# --- materializar_decision_venta: primitiva atómica ----------------------------------


class TestMaterializarDecisionVenta:
    def test_crea_una_exit_ia_pendiente_ligada_a_la_posicion_y_marca_aplicada(self, tmp_path: Path) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        position_id = _abrir(cartera_ia, symbol="A")

        decision_id = _vender_pendiente(cartera_ia, reg, position_id)

        pendientes = cartera_ia.pendientes_salida()
        assert len(pendientes) == 1
        assert pendientes[0].position_id == position_id and pendientes[0].symbol == "A"
        assert pendientes[0].causa == "CIERRE_BAJO_SMA"
        fila = reg.conn.execute("SELECT aplicada FROM ia_decision WHERE id = ?", (decision_id,)).fetchone()
        assert fila["aplicada"] == 1
        # No se toca nada contable: crear la orden pendiente no es todavía una venta.
        assert cartera_ia.posiciones_abiertas()[0].id == position_id
        assert cartera_ia.verificar_invariante_contable()

    def test_es_idempotente_llamada_dos_veces_con_la_misma_decision(self, tmp_path: Path) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        position_id = _abrir(cartera_ia, symbol="A")
        decision_id = _vender_pendiente(cartera_ia, reg, position_id)
        primera = cartera_ia.pendientes_salida()[0]

        cartera_ia.materializar_decision_venta(
            decision_id=decision_id, position_id=position_id, symbol="A", market="NYSE", currency="EUR",
            target_session=SESION_OBJETIVO, target_open=APERTURA, causa="CIERRE_BAJO_SMA", instante=T_ACTIVACION,
        )

        assert len(cartera_ia.pendientes_salida()) == 1
        assert cartera_ia.pendientes_salida()[0].id == primera.id

    def test_una_segunda_decision_vender_sobre_la_misma_posicion_se_rechaza_terminal(self, tmp_path: Path) -> None:
        """Dos decisiones VENDER distintas (de pasadas distintas) sobre la misma posición: la
        segunda nunca debe quedar sin ningún rastro — eso permitiría que, si la primera orden
        desapareciera días después, la segunda decisión "reviviera" como si nunca se hubiera
        resuelto."""

        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        position_id = _abrir(cartera_ia, symbol="A")
        _vender_pendiente(cartera_ia, reg, position_id, causa="CIERRE_BAJO_SMA")

        otra_decision_id = _vender_pendiente(cartera_ia, reg, position_id, causa="INVALIDACION_CRUZADA")

        assert len(cartera_ia.pendientes_salida()) == 1  # la primera sigue, intacta
        rechazada = reg.conn.execute(
            "SELECT estado, motivo FROM ia_orden WHERE decision_id = ? AND proposito = 'EXIT_IA'", (otra_decision_id,)
        ).fetchone()
        assert rechazada["estado"] == "RECHAZADA" and rechazada["motivo"] == "EXIT_PENDIENTE_PREEXISTENTE"
        fila = reg.conn.execute("SELECT aplicada FROM ia_decision WHERE id = ?", (otra_decision_id,)).fetchone()
        assert fila["aplicada"] == 1  # con rastro propio, nunca "sin aplicar" para siempre

    def test_una_decision_de_pasada_en_modo_registro_nunca_se_materializa(self, tmp_path: Path) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        position_id = _abrir(cartera_ia, symbol="A")
        reg.conn.execute(
            "INSERT INTO ia_paquete (input_hash, tipo, symbol, contenido) VALUES ('hr','POSICION','A','{}')"
        )
        pasada_id = reg.abrir_pasada(T_ACTIVACION, "registro", "sha")
        decision_id = reg.guardar_decision(
            clave="A|2026-11-05|2026-11-06|x", pasada_id=pasada_id, symbol="A", market="NYSE", tipo="POSICION",
            signal_session="2026-11-05", target_session="2026-11-06", target_open=APERTURA.isoformat(),
            decision_ts=T_ACTIVACION.isoformat(), input_hash="hr", cuantitativo="{}", votos="{}", predicados=None,
            resolucion="VENDER", motivo="CAUSA_VERIFICADA", prioridad=None, causa="CIERRE_BAJO_SMA",
        )

        cartera_ia.materializar_decision_venta(
            decision_id=decision_id, position_id=position_id, symbol="A", market="NYSE", currency="EUR",
            target_session=SESION_OBJETIVO, target_open=APERTURA, causa="CIERRE_BAJO_SMA", instante=T_ACTIVACION,
        )

        assert cartera_ia.pendientes_salida() == ()
        fila = reg.conn.execute("SELECT aplicada FROM ia_decision WHERE id = ?", (decision_id,)).fetchone()
        assert fila["aplicada"] == 0


# --- ciclo completo: decisión VENDER -> EXIT_IA pendiente -> resolución ---------------


class TestCicloDeSalidaIA:
    def test_la_venta_decidida_al_cierre_se_ejecuta_en_la_apertura_siguiente_nunca_antes(self, tmp_path: Path) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        position_id = _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0, stop=50.0)
        _vender_pendiente(cartera_ia, reg, position_id)
        proveedor = _proveedor_ohlc({"A": {SESION_OBJETIVO: (110.0, 108.0, 112.0)}})

        # Causalmente anterior a la apertura de la sesión objetivo: no debe resolverse todavía.
        resultado_temprano = procesar_pendientes(cartera_ia, proveedor, APERTURA, 0, [])
        assert resultado_temprano.salidas_ia == [] and resultado_temprano.rechazos_salida == []
        assert len(cartera_ia.posiciones_abiertas()) == 1

        resultado = procesar_pendientes(cartera_ia, proveedor, T_ACTIVACION + timedelta(days=5), 0, [])

        assert resultado.salidas_ia == ["A"] and resultado.rechazos_salida == []
        assert cartera_ia.posiciones_abiertas() == ()
        assert cartera_ia.pendientes_salida() == ()
        fila = cartera_ia.conn.execute(
            "SELECT exit_price, exit_session, motivo_cierre FROM ia_posicion WHERE id = ?", (position_id,)
        ).fetchone()
        # Se ejecuta a la APERTURA de la sesión objetivo (110.0), no a su cierre (112.0).
        assert fila["exit_price"] == 110.0 and fila["exit_session"] == SESION_OBJETIVO.isoformat()
        assert cartera_ia.verificar_invariante_contable()

    def test_la_venta_actualiza_correctamente_caja_fill_y_pnl(self, tmp_path: Path) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        position_id = _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0, stop=50.0)
        _vender_pendiente(cartera_ia, reg, position_id)
        proveedor = _proveedor_ohlc({"A": {SESION_OBJETIVO: (110.0, 108.0, 112.0)}})
        cash_antes = cartera_ia.cash_eur()

        procesar_pendientes(cartera_ia, proveedor, T_ACTIVACION + timedelta(days=5), 0, [])

        # Entró con 1.000 EUR (10 x 100) y sale con 1.100 (10 x 110 a la apertura): +100 EUR.
        assert cartera_ia.cash_eur() == pytest.approx(cash_antes + 1_100.0)
        fill = cartera_ia.conn.execute(
            "SELECT lado, precio, units, importe_eur FROM ia_fill f JOIN ia_orden o ON o.id = f.order_id "
            "WHERE o.position_id = ? AND o.proposito = 'EXIT_IA'", (position_id,)
        ).fetchone()
        assert fill["lado"] == "VENTA" and fill["precio"] == 110.0 and fill["units"] == 10.0
        assert fill["importe_eur"] == pytest.approx(1_100.0)
        pnl = cartera_ia.conn.execute("SELECT pnl_eur FROM ia_posicion WHERE id = ?", (position_id,)).fetchone()[0]
        assert pnl == pytest.approx(100.0)
        assert cartera_ia.verificar_invariante_contable()

    def test_el_stop_tiene_prioridad_y_nunca_se_liquida_dos_veces_el_mismo_dia(self, tmp_path: Path) -> None:
        """Condiciones 4 y 5 de la autorización: el stop obligatorio manda sobre la venta IA
        pendiente, y la posición termina cerrada exactamente una vez, con un único fill."""

        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        position_id = _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0, stop=90.0)
        _vender_pendiente(cartera_ia, reg, position_id)
        # La misma sesión objetivo: abre ya por debajo del stop (gap adverso).
        proveedor = _proveedor_ohlc({"A": {SESION_OBJETIVO: (85.0, 80.0, 86.0)}})

        resultado = procesar_pendientes(cartera_ia, proveedor, T_ACTIVACION + timedelta(days=5), 0, [])

        assert resultado.cerradas_stop == {"A": SESION_OBJETIVO}
        assert resultado.salidas_ia == []
        assert resultado.rechazos_salida == ["A"]
        assert cartera_ia.posiciones_abiertas() == ()
        orden_exit = cartera_ia.conn.execute(
            "SELECT estado, motivo FROM ia_orden WHERE position_id = ? AND proposito = 'EXIT_IA'", (position_id,)
        ).fetchone()
        assert orden_exit["estado"] == "RECHAZADA" and orden_exit["motivo"] == "POSICION_YA_CERRADA_POR_STOP"
        orden_stop = cartera_ia.conn.execute(
            "SELECT estado, origen FROM ia_orden WHERE position_id = ? AND proposito = 'STOP'", (position_id,)
        ).fetchone()
        assert orden_stop["estado"] == "EJECUTADA" and orden_stop["origen"] == "STOP_OBLIGATORIO"
        # Un único fill de SALIDA (el del stop): la EXIT_IA rechazada nunca llegó a crear el suyo.
        assert cartera_ia.conn.execute(
            "SELECT COUNT(*) FROM ia_fill f JOIN ia_orden o ON o.id = f.order_id "
            "WHERE o.position_id = ? AND o.proposito != 'ENTRY'", (position_id,)
        ).fetchone()[0] == 1
        assert cartera_ia.verificar_invariante_contable()

    def test_ejecutar_salida_ia_nunca_liquida_una_posicion_ya_cerrada(self, tmp_path: Path) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        position_id = _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)
        _vender_pendiente(cartera_ia, reg, position_id)
        posicion = cartera_ia.posiciones_abiertas()[0]
        cartera_ia.cerrar_posicion(
            posicion, exit_price=95.0, exit_price_eur=95.0, exit_session=SESION_OBJETIVO, origen="STOP_OBLIGATORIO",
            motivo="STOP_TOCADO",
        )
        orden = cartera_ia.pendientes_salida()[0]

        with pytest.raises(PosicionYaCerrada):
            cartera_ia.ejecutar_salida_ia(
                orden, exit_price=110.0, exit_price_eur=110.0, fx_rate=1.0, fx_as_of=None, session=SESION_OBJETIVO,
            )

        # La orden sigue PENDIENTE: el llamador (resolver_salidas_del_dia) es quien la rechaza.
        assert cartera_ia.pendientes_salida() == (orden,)

    def test_no_se_puede_ejecutar_dos_veces_la_misma_orden_de_salida(self, tmp_path: Path) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        position_id = _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)
        _vender_pendiente(cartera_ia, reg, position_id)
        orden = cartera_ia.pendientes_salida()[0]
        cartera_ia.ejecutar_salida_ia(
            orden, exit_price=110.0, exit_price_eur=110.0, fx_rate=1.0, fx_as_of=None, session=SESION_OBJETIVO,
        )

        with pytest.raises(OrdenYaResuelta):
            cartera_ia.ejecutar_salida_ia(
                orden, exit_price=110.0, exit_price_eur=110.0, fx_rate=1.0, fx_as_of=None, session=SESION_OBJETIVO,
            )

        # Un único fill de VENTA (el de la primera ejecución): el segundo intento no creó el suyo.
        assert cartera_ia.conn.execute(
            "SELECT COUNT(*) FROM ia_fill f JOIN ia_orden o ON o.id = f.order_id "
            "WHERE o.position_id = ? AND o.proposito = 'EXIT_IA'", (position_id,)
        ).fetchone()[0] == 1
        assert cartera_ia.verificar_invariante_contable()


# --- recuperación tras una caída entre decisión, orden y aplicada --------------------


class TestRecuperacionDeVentaInterrumpida:
    def test_recupera_una_decision_vender_sin_aplicar_de_una_pasada_activa_anterior(self, tmp_path: Path) -> None:
        """Simula una caída justo después de ``Motor.registrar`` (la decisión quedó persistida,
        ``aplicada=0``) y antes de crear la orden: el barrido de recuperación debe completar lo que
        faltaba, sin que el propietario tenga que intervenir."""

        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        position_id = _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)
        reg.conn.execute(
            "INSERT INTO ia_paquete (input_hash, tipo, symbol, contenido) VALUES ('hc','POSICION','A','{}')"
        )
        pasada_id = reg.abrir_pasada(T_ACTIVACION, "activo", "sha")
        cuantitativo = f'{{"currency": "EUR", "position_id": {position_id}}}'
        decision_id = reg.guardar_decision(
            clave="A|2026-11-05|2026-11-06|x", pasada_id=pasada_id, symbol="A", market="NYSE", tipo="POSICION",
            signal_session="2026-11-05", target_session=SESION_OBJETIVO.isoformat(), target_open=APERTURA.isoformat(),
            decision_ts=T_ACTIVACION.isoformat(), input_hash="hc", cuantitativo=cuantitativo, votos="{}",
            predicados=None, resolucion="VENDER", motivo="CAUSA_VERIFICADA", prioridad=None, causa="CIERRE_BAJO_SMA",
        )
        # Nunca se llegó a crear la orden ni a marcar aplicada: aquí se "cayó" el proceso.

        incidencias: list[str] = []
        cartera_ia.recuperar_decisiones_sin_aplicar(T_ACTIVACION, incidencias)

        assert incidencias == []
        pendientes = cartera_ia.pendientes_salida()
        assert len(pendientes) == 1 and pendientes[0].position_id == position_id
        fila = reg.conn.execute("SELECT aplicada FROM ia_decision WHERE id = ?", (decision_id,)).fetchone()
        assert fila["aplicada"] == 1

    def test_recuperar_dos_veces_no_duplica_la_orden(self, tmp_path: Path) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        position_id = _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)
        reg.conn.execute(
            "INSERT INTO ia_paquete (input_hash, tipo, symbol, contenido) VALUES ('hc','POSICION','A','{}')"
        )
        pasada_id = reg.abrir_pasada(T_ACTIVACION, "activo", "sha")
        cuantitativo = f'{{"currency": "EUR", "position_id": {position_id}}}'
        reg.guardar_decision(
            clave="A|2026-11-05|2026-11-06|x", pasada_id=pasada_id, symbol="A", market="NYSE", tipo="POSICION",
            signal_session="2026-11-05", target_session=SESION_OBJETIVO.isoformat(), target_open=APERTURA.isoformat(),
            decision_ts=T_ACTIVACION.isoformat(), input_hash="hc", cuantitativo=cuantitativo, votos="{}",
            predicados=None, resolucion="VENDER", motivo="CAUSA_VERIFICADA", prioridad=None, causa="CIERRE_BAJO_SMA",
        )

        incidencias: list[str] = []
        cartera_ia.recuperar_decisiones_sin_aplicar(T_ACTIVACION, incidencias)
        cartera_ia.recuperar_decisiones_sin_aplicar(T_ACTIVACION, incidencias)  # como si se reintentara el barrido

        assert len(cartera_ia.pendientes_salida()) == 1
        assert incidencias == []

    def test_una_decision_vender_con_cuantitativo_ilegible_no_se_pierde_silenciosa(self, tmp_path: Path) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)
        reg.conn.execute(
            "INSERT INTO ia_paquete (input_hash, tipo, symbol, contenido) VALUES ('hc','POSICION','A','{}')"
        )
        pasada_id = reg.abrir_pasada(T_ACTIVACION, "activo", "sha")
        decision_id = reg.guardar_decision(
            clave="A|2026-11-05|2026-11-06|x", pasada_id=pasada_id, symbol="A", market="NYSE", tipo="POSICION",
            signal_session="2026-11-05", target_session=SESION_OBJETIVO.isoformat(), target_open=APERTURA.isoformat(),
            decision_ts=T_ACTIVACION.isoformat(), input_hash="hc", cuantitativo="no es json", votos="{}",
            predicados=None, resolucion="VENDER", motivo="CAUSA_VERIFICADA", prioridad=None, causa="CIERRE_BAJO_SMA",
        )

        incidencias: list[str] = []
        cartera_ia.recuperar_decisiones_sin_aplicar(T_ACTIVACION, incidencias)

        assert cartera_ia.pendientes_salida() == ()
        assert any(str(decision_id) in i for i in incidencias)
        # Sigue sin aplicar: una pasada posterior con el dato corregido podría todavía recuperarla.
        fila = reg.conn.execute("SELECT aplicada FROM ia_decision WHERE id = ?", (decision_id,)).fetchone()
        assert fila["aplicada"] == 0

    def test_un_mantener_sin_aplicar_se_recupera_sin_crear_ningun_efecto(self, tmp_path: Path) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)
        reg.conn.execute(
            "INSERT INTO ia_paquete (input_hash, tipo, symbol, contenido) VALUES ('hm','POSICION','A','{}')"
        )
        pasada_id = reg.abrir_pasada(T_ACTIVACION, "activo", "sha")
        decision_id = reg.guardar_decision(
            clave="A|2026-11-05|2026-11-06|x", pasada_id=pasada_id, symbol="A", market="NYSE", tipo="POSICION",
            signal_session="2026-11-05", target_session=SESION_OBJETIVO.isoformat(), target_open=APERTURA.isoformat(),
            decision_ts=T_ACTIVACION.isoformat(), input_hash="hm", cuantitativo="{}", votos="{}", predicados=None,
            resolucion="MANTENER", motivo="SIN_DISPARO", prioridad=None, causa=None,
        )

        cartera_ia.recuperar_decisiones_sin_aplicar(T_ACTIVACION, [])

        assert cartera_ia.pendientes_salida() == () and cartera_ia.pendientes_entrada() == ()
        fila = reg.conn.execute("SELECT aplicada FROM ia_decision WHERE id = ?", (decision_id,)).fetchone()
        assert fila["aplicada"] == 1


# --- integración con la pasada: VENDER y MANTENER desde el comité --------------------


class TestIntegracionVenderMantener:
    def test_vender_crea_la_salida_pendiente_y_la_posicion_sigue_abierta_esta_misma_pasada(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0, stop=50.0)
        # Cierre bajo la SMA: dispara CAUSA_SMA.
        analisis_a = _analisis("A", close=85.0, sma=90.0)
        cliente = ClienteFalso(por_defecto=posicion_ok())

        resultado, _reg2 = _pasada(
            tmp_path, monkeypatch, [analisis_a], cliente, cartera_ia=cartera_ia, registro_existente=reg,
            proveedor=_proveedor_ohlc({}),
        )

        assert resultado.status == "OK"
        assert resultado.ventas == ["A"]  # el comité decidió vender esta pasada
        assert resultado.salidas_ia == [] and resultado.rechazos_salida == []  # nada se ejecutó todavía
        assert len(cartera_ia.posiciones_abiertas()) == 1  # sigue abierta: se vende en la apertura siguiente
        assert len(cartera_ia.pendientes_salida()) == 1
        fila = reg.decisiones(resultado.pasada_id)[0]
        assert fila["resolucion"] == "VENDER" and fila["aplicada"] == 1

    def test_mantener_no_crea_ningun_efecto_durable(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0, stop=50.0)
        analisis_a = _analisis("A", close=85.0, sma=90.0)
        mantiene: Dict[str, Any] = {
            "decision": "MANTENER", "causa": None, "motivos": ["Todavía razonable"],
            "riesgos": ["Puede seguir cayendo"], "datos_citados": ["posicion.cierre"],
        }
        cliente = ClienteFalso(por_defecto=mantiene)

        resultado, _reg2 = _pasada(
            tmp_path, monkeypatch, [analisis_a], cliente, cartera_ia=cartera_ia, registro_existente=reg,
            proveedor=_proveedor_ohlc({}),
        )

        assert resultado.ventas == []
        assert len(cartera_ia.posiciones_abiertas()) == 1
        assert cartera_ia.pendientes_salida() == ()
        fila = reg.decisiones(resultado.pasada_id)[0]
        assert fila["resolucion"] == "MANTENER" and fila["aplicada"] == 1

    def test_en_modo_registro_vender_nunca_crea_una_orden(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        analisis_a = _analisis("A", close=85.0, sma=90.0)
        cliente = ClienteFalso(por_defecto=posicion_ok())
        cartera_registro = EstadoCartera(
            10_000.0, 10_000.0, posiciones=(
                PosicionIA(
                    symbol="A", entry_date=date(2026, 11, 2), signal_session=date(2026, 10, 30),
                    decision_apertura="apertura-1", entry_price=100.0, stop=50.0, invalidation_level=50.0,
                    pnl_pct=-15.0, exposicion_pct=10.0,
                ),
            ),
        )

        resultado, reg = _pasada(
            tmp_path, monkeypatch, [analisis_a], cliente, cartera=cartera_registro,
        )  # sin cartera_ia: modo registro

        assert resultado.ventas == ["A"]  # el comité sí decide, solo se registra
        fila = reg.decisiones(resultado.pasada_id)[0]
        assert fila["resolucion"] == "VENDER" and fila["aplicada"] == 0
        # Nadie construyó un CarteraIA en modo registro: ni siquiera existe la tabla de órdenes.
        CarteraIA(reg.conn)  # crea el esquema (vacío) solo para poder consultarlo en la prueba
        assert reg.conn.execute("SELECT COUNT(*) FROM ia_orden").fetchone()[0] == 0

    def test_una_posicion_con_salida_ia_pendiente_no_se_le_vuelve_a_preguntar_a_la_ia(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Una vez decidida la venta, la posición queda excluida de una segunda evaluación mientras
        la ``EXIT_IA`` siga pendiente: nunca se le pide al comité una segunda decisión de venta sobre
        lo mismo."""

        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        position_id = _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0, stop=50.0)
        _vender_pendiente(cartera_ia, reg, position_id)
        analisis_a = _analisis("A", close=85.0, sma=90.0)
        cliente = ClienteFalso(respuestas=[Exception("no debería llamarse a la IA otra vez")])
        # Objetivo todavía no observable: la EXIT_IA sigue pendiente durante esta pasada.
        proveedor = _proveedor_ohlc({"A": {SESION_OBJETIVO: (110.0, 108.0, 112.0)}})

        resultado, _reg2 = _pasada(
            tmp_path, monkeypatch, [analisis_a], cliente, cartera_ia=cartera_ia, registro_existente=reg,
            proveedor=proveedor,
        )

        assert cliente.llamadas == 0
        assert resultado.ventas == []
        decisiones = reg.decisiones(resultado.pasada_id)
        assert not any(d["symbol"] == "A" and d["tipo"] == "POSICION" for d in decisiones)


# --- una venta IA sin tipo de cambio no se pierde ni se declara ejecutada ------------


class TestSalidaIaSinTipoDeCambio:
    def test_sin_tipo_de_cambio_la_salida_sigue_pendiente_no_se_rechaza(self, tmp_path: Path) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        position_id = _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0, currency="USD")
        _vender_pendiente(cartera_ia, reg, position_id, currency="USD")
        # Sin barra de "EURUSD=X": fx_en_sesion no se resuelve.
        proveedor = _proveedor_ohlc({"A": {SESION_OBJETIVO: (110.0, 108.0, 112.0)}})

        resultado = procesar_pendientes(cartera_ia, proveedor, T_ACTIVACION + timedelta(days=5), 0, [])

        assert resultado.salidas_ia == [] and resultado.rechazos_salida == []
        assert len(cartera_ia.pendientes_salida()) == 1  # sigue pendiente, no rechazada ni perdida
        assert len(cartera_ia.posiciones_abiertas()) == 1


# --- hallazgos de la revisión de Codex a la fase 3 ------------------------------------


class TestOrdenIrresolubleNoMonopolizaElHorizonteDeLosStops:
    def test_una_entry_sin_barra_no_bloquea_el_stop_de_otra_posicion(self, tmp_path: Path) -> None:
        """Antes, el cursor único de ``procesar_pendientes`` se quedaba permanentemente en la
        fecha de una ``ENTRY`` sin datos, y el stop de una posición totalmente distinta, con fecha
        posterior, nunca llegaba a comprobarse mientras esa ENTRY siguiera sin resolver."""

        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="B", stop=90.0, entry_price=100.0, units=1.0, entry_session=date(2026, 11, 3))
        _comprar_pendiente(cartera_ia, reg, symbol="A", target_session=date(2026, 11, 6))
        # "A" no tiene ninguna barra (nunca se resuelve); "B" rompe su stop el 9, DESPUÉS de la
        # fecha objetivo (sin datos) de la ENTRY de A.
        proveedor = _proveedor_ohlc({"B": {date(2026, 11, 9): (85.0, 80.0, 86.0)}})

        resultado = procesar_pendientes(cartera_ia, proveedor, T_ACTIVACION + timedelta(days=15), 0, [])

        assert resultado.cerradas_stop == {"B": date(2026, 11, 9)}
        assert cartera_ia.posiciones_abiertas() == ()
        assert len(cartera_ia.pendientes_entrada()) == 1  # A sigue pendiente, a la espera de datos


class TestMantenimientoDeCarteraIndependienteDelContexto:
    def test_un_fallo_al_cargar_el_contexto_no_impide_el_stop_obligatorio(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Antes, ``cargar_contexto`` corría ANTES del mantenimiento mecánico de la cartera: un
        fallo (repetido) ahí dejaba el stop obligatorio sin comprobar indefinidamente, violando la
        condición 4 (los stops funcionan independientemente de la IA)."""

        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0, stop=90.0, entry_session=date(2026, 11, 3))
        proveedor = _proveedor_ohlc({"A": {date(2026, 11, 4): (85.0, 80.0, 86.0)}})  # gap bajo el stop
        cliente = ClienteFalso(respuestas=[Exception("no debería llamarse: el contexto falló antes")])

        resultado, _reg2 = _pasada(
            tmp_path, monkeypatch, [], cliente, cartera_ia=cartera_ia, registro_existente=reg, proveedor=proveedor,
            contexto=RuntimeError("API de contexto caída"),
        )

        assert resultado.status == "ERROR"
        assert cliente.llamadas == 0
        assert cartera_ia.posiciones_abiertas() == ()  # el stop se comprobó y cerró igualmente
        assert resultado.cerradas_stop == ["A"]


class TestFxEnSesionRobustez:
    def test_no_se_fia_de_una_barra_de_otra_fecha_aunque_el_proveedor_ignore_el_rango(self) -> None:
        """Antes se tomaba ciegamente ``Close.iloc[-1]`` sin comprobar que la fila fuera de la
        sesión pedida: un proveedor que no respetara `start`/`end` podía servir la tasa de otro día
        — exactamente lo que FX por fecha exacta debía impedir."""

        class _ProveedorQueIgnoraElRango:
            def get_raw_history(self, symbol: str, start: Any = None, end: Any = None, **_kw: Any) -> pd.DataFrame:
                return pd.DataFrame({"Close": [1.1]}, index=[pd.Timestamp(date(2026, 11, 10))])

        resultado = fx_en_sesion(_ProveedorQueIgnoraElRango(), "USD", date(2026, 11, 4))  # type: ignore[arg-type]

        assert resultado is None

    def test_un_cierre_nulo_no_lanza_una_excepcion_devuelve_none(self) -> None:
        class _ProveedorConCierreNulo:
            def get_raw_history(self, symbol: str, start: Any = None, end: Any = None, **_kw: Any) -> pd.DataFrame:
                return pd.DataFrame({"Close": [None]}, index=[pd.Timestamp(date(2026, 11, 4))])

        resultado = fx_en_sesion(_ProveedorConCierreNulo(), "USD", date(2026, 11, 4))  # type: ignore[arg-type]

        assert resultado is None


class TestSalidaIaSobrePosicionYaCerradaSinDatos:
    def test_se_rechaza_sin_necesitar_cotizacion_ni_tipo_de_cambio(self, tmp_path: Path) -> None:
        """Antes se pedía cotización y FX ANTES de comprobar si la posición seguía abierta: una
        EXIT_IA sobre una posición ya cerrada por el stop podía quedar PENDIENTE para siempre si
        faltaba el dato de mercado, bloqueando mientras tanto (por símbolo) una posición nueva."""

        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        position_id = _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0, stop=90.0)
        _vender_pendiente(cartera_ia, reg, position_id)
        posicion = cartera_ia.posiciones_abiertas()[0]
        cartera_ia.cerrar_posicion(
            posicion, exit_price=85.0, exit_price_eur=85.0, exit_session=SESION_OBJETIVO, origen="STOP_OBLIGATORIO",
            motivo="GAP_BAJO_STOP",
        )
        proveedor = _proveedor_ohlc({})  # sin ninguna barra de "A": si se pidiera cotización, no la habría

        resultado = procesar_pendientes(cartera_ia, proveedor, T_ACTIVACION + timedelta(days=5), 0, [])

        assert resultado.rechazos_salida == ["A"]
        assert cartera_ia.pendientes_salida() == ()
        orden = cartera_ia.conn.execute(
            "SELECT estado, motivo FROM ia_orden WHERE position_id = ? AND proposito = 'EXIT_IA'", (position_id,)
        ).fetchone()
        assert orden["estado"] == "RECHAZADA" and orden["motivo"] == "POSICION_YA_CERRADA_POR_STOP"


class TestPnlEnEurConsistenteConElEquity:
    def test_pnl_pct_refleja_el_movimiento_del_tipo_de_cambio_no_solo_el_precio_nativo(self, tmp_path: Path) -> None:
        """Antes el ``pnl_pct`` que ve la IA se calculaba solo con el precio nativo, ignorando el
        FX: una posición en USD podía mostrar el equity en pérdida pero ``pnl_pct == 0.0``."""

        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        cartera_ia.abrir_posicion(
            symbol="A", market="NYSE", currency="USD", units=10.0, entry_price=100.0, entry_price_eur=100.0,
            entry_session=date(2026, 11, 3), decision_apertura_id=None, stop=50.0, invalidation_level=50.0,
            entry_max=105.0, target1=110.0, target2=115.0, rr_minimo=1.5, instante=T_ACTIVACION,
        )
        analizadas = {"A": _analisis("A", close=100.0)}  # el precio nativo NO cambió
        # EURUSD=X a 2.0 (1 EUR = 2 USD): ahora 1 USD = 0,5 EUR, la mitad que al entrar.
        proveedor = _proveedor_ohlc(
            {"A": {date(2026, 11, 5): (100.0, 100.0, 100.0)}, "EURUSD=X": {date(2026, 11, 5): (2.0, 2.0, 2.0)}}
        )

        estado, _incidencias = construir_estado_cartera(cartera_ia, analizadas, proveedor)

        assert estado.posiciones[0].pnl_pct == pytest.approx(-50.0)


class TestMaterializarDecisionVentaExigeCoherenciaConLaDecisionPersistida:
    def test_rechaza_si_el_decision_id_no_es_una_vender_con_esa_causa(self, tmp_path: Path) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        position_id = _abrir(cartera_ia, symbol="A")
        reg.conn.execute(
            "INSERT INTO ia_paquete (input_hash, tipo, symbol, contenido) VALUES ('hm','POSICION','A','{}')"
        )
        pasada_id = reg.abrir_pasada(T_ACTIVACION, "activo", "sha")
        decision_id = reg.guardar_decision(
            clave="A|m|2026-11-05|2026-11-06|x", pasada_id=pasada_id, symbol="A", market="NYSE", tipo="POSICION",
            signal_session="2026-11-05", target_session=SESION_OBJETIVO.isoformat(), target_open=APERTURA.isoformat(),
            decision_ts=T_ACTIVACION.isoformat(), input_hash="hm", cuantitativo="{}", votos="{}", predicados=None,
            resolucion="MANTENER", motivo="SIN_DISPARO", prioridad=None, causa=None,
        )

        with pytest.raises(ValueError):
            cartera_ia.materializar_decision_venta(
                decision_id=decision_id, position_id=position_id, symbol="A", market="NYSE", currency="EUR",
                target_session=SESION_OBJETIVO, target_open=APERTURA, causa="CIERRE_BAJO_SMA", instante=T_ACTIVACION,
            )
        assert cartera_ia.pendientes_salida() == ()

    def test_rechaza_una_causa_no_autorizada_antes_de_tocar_la_base(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)

        with pytest.raises(ValueError):
            cartera_ia.materializar_decision_venta(
                decision_id=999, position_id=1, symbol="A", market="NYSE", currency="EUR",
                target_session=SESION_OBJETIVO, target_open=APERTURA, causa="CAUSA_INVENTADA", instante=T_ACTIVACION,
            )


# --- segunda ronda de Codex: dos hallazgos más tras corregir los cinco primeros -------


class TestDecisionTsSeFechaDespuesDeObservarLosDatos:
    def test_una_observacion_posterior_al_mantenimiento_no_invalida_el_paquete(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Hallazgo de Codex: si ``decision_ts`` se fija ANTES del mantenimiento/contexto/análisis
        (en vez de después, con todo ya observado), cualquier observación con un instante
        posterior —inevitable en producción, donde las descargas tardan— parecería "posterior a
        la decisión" y ``validar_causal`` rechazaría el paquete, anulando todas las decisiones."""

        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        # Posterior a ``T``: la observación fija del contexto (``CONTEXTO``, en
        # ``tests.test_superbot_ia``) usa ``T`` como su propio instante, y si ``base`` fuera
        # anterior, esa observación —ajena a lo que prueba este test— ya invalidaría el paquete.
        base = T + timedelta(minutes=1)
        contador = {"n": 0}

        def reloj() -> datetime:
            contador["n"] += 1
            return base + timedelta(seconds=contador["n"])

        # Instante ESTRICTAMENTE entre la 1ª llamada al reloj (el mantenimiento) y la 2ª
        # (``decision_ts``): solo valida si ``decision_ts`` es la llamada POSTERIOR a esta
        # observación, nunca la anterior.
        observado_a = base + timedelta(milliseconds=1500)
        analisis_a = replace(
            _analisis("A", score=72.0),
            observaciones=(Observacion("barras", "A", "2026-11-05", observado_a, observado_a, "h"),),
        )
        cliente = ClienteFalso(por_defecto=compra_ok())

        resultado, _reg2 = _pasada(
            tmp_path, monkeypatch, [analisis_a], cliente, cartera_ia=cartera_ia, registro_existente=reg,
            proveedor=_proveedor_ohlc({}), reloj=reloj, instante=base,
        )

        assert resultado.status == "OK"
        assert resultado.compras == ["A"]
        assert not any("PaqueteInvalido" in i for i in resultado.incidencias)


class TestOrdenPosteriorNoQuedaOcultaPorUnaAnteriorEstancada:
    def test_una_entry_posterior_resoluble_no_queda_bloqueada_por_otra_anterior_sin_datos(
        self, tmp_path: Path
    ) -> None:
        """Hallazgo de Codex: antes, una vez excluida la fecha estancada, el cursor volvía a
        recibir SOLO esa misma fecha mínima global (``_proxima_fecha_orden`` no sabía de la
        exclusión), así que una segunda ENTRY POSTERIOR y perfectamente resoluble quedaba oculta
        en TODAS las pasadas mientras la primera (sin datos) siguiera pendiente."""

        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="B", stop=90.0, entry_price=100.0, units=1.0, entry_session=date(2026, 11, 3))
        _comprar_pendiente(cartera_ia, reg, symbol="A", target_session=date(2026, 11, 6))  # sin barra: nunca se resuelve
        _comprar_pendiente(cartera_ia, reg, symbol="C", target_session=date(2026, 11, 7))  # perfectamente resoluble
        proveedor = _proveedor_ohlc({
            "C": {date(2026, 11, 7): (100.0, 95.0, 102.0)},
            "B": {date(2026, 11, 9): (85.0, 80.0, 86.0)},
            # "A" no tiene ninguna barra.
        })

        resultado = procesar_pendientes(cartera_ia, proveedor, T_ACTIVACION + timedelta(days=15), 0, [])

        assert resultado.abiertas == ["C"]  # C se resolvió aunque A (anterior, sin datos) siga pendiente
        assert resultado.cerradas_stop == {"B": date(2026, 11, 9)}
        assert len(cartera_ia.pendientes_entrada()) == 1
        assert cartera_ia.pendientes_entrada()[0].symbol == "A"

        # Una segunda pasada (nueva llamada, el estancamiento de la anterior no se recuerda):
        # A sigue sin resolverse, sin que nada más quede bloqueado por su culpa.
        resultado_2 = procesar_pendientes(cartera_ia, proveedor, T_ACTIVACION + timedelta(days=20), 0, [])
        assert resultado_2.abiertas == [] and resultado_2.cerradas_stop == {}
        assert len(cartera_ia.pendientes_entrada()) == 1
