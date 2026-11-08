"""Superbot con IA: gestión de capital del dashboard — aportar, retirar y reiniciar la cartera.

El principio que exige el propietario: se puede reiniciar el capital y la cartera, pero nunca se
pierde el historial de decisiones ni el conocimiento acumulado. Estas pruebas cubren exactamente
lo que pidió en la validación: aportación/retirada, reinicio con cartera vacía y con posiciones
abiertas, reinicio con órdenes pendientes, fallo/interrupción durante el reinicio, conservación
íntegra del historial y ausencia de órdenes antiguas reapareciendo.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from superbot.ia.cartera import (
    CarteraIA,
    CarteraInactiva,
    EfectivoInsuficiente,
)
from tests.test_superbot_ia import APERTURA
from tests.test_superbot_ia_cartera import _abrir, _cartera
from tests.test_superbot_ia_fase2 import SESION_OBJETIVO
from tests.test_superbot_ia_fase3 import NIVELES_COMPRA, _comprar_pendiente, _vender_pendiente

T_ACTIVACION = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)


class TestAportar:
    def test_aumenta_la_caja_y_registra_el_movimiento(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)

        cartera_ia.aportar(importe_eur=2_000.0, motivo="refuerzo", actor="propietario")

        assert cartera_ia.cash_eur() == pytest.approx(12_000.0)
        assert cartera_ia.verificar_invariante_contable()
        fila = cartera_ia.conn.execute(
            "SELECT tipo, importe_eur, referencia, detalle FROM ia_movimiento ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert fila["tipo"] == "APORTACION" and fila["importe_eur"] == pytest.approx(2_000.0)
        assert fila["referencia"] == "propietario" and fila["detalle"] == "refuerzo"

    def test_no_cuenta_como_rentabilidad(self, tmp_path: Path) -> None:
        """Una aportación no debe inflar el PnL realizado: solo mueve caja."""

        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        cartera_ia.aportar(importe_eur=5_000.0, motivo="refuerzo", actor="propietario")

        # El invariante contable (suma de movimientos == cash) sigue cumpliéndose exactamente:
        # una aportación es un movimiento más, no una ganancia que rompa la contabilidad.
        assert cartera_ia.verificar_invariante_contable()

    @pytest.mark.parametrize("importe", [0.0, -100.0, float("nan"), float("inf")])
    def test_rechaza_un_importe_no_valido(self, tmp_path: Path, importe: float) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        with pytest.raises(ValueError):
            cartera_ia.aportar(importe_eur=importe, motivo="x", actor="propietario")
        assert cartera_ia.cash_eur() == pytest.approx(10_000.0)

    def test_sin_cartera_activa_no_se_puede_aportar(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        with pytest.raises(CarteraInactiva):
            cartera_ia.aportar(importe_eur=100.0, motivo="x", actor="propietario")


class TestRetirar:
    def test_reduce_la_caja_y_registra_el_movimiento_negativo(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)

        cartera_ia.retirar(importe_eur=1_500.0, motivo="viaje", actor="propietario")

        assert cartera_ia.cash_eur() == pytest.approx(8_500.0)
        assert cartera_ia.verificar_invariante_contable()
        fila = cartera_ia.conn.execute(
            "SELECT tipo, importe_eur, detalle FROM ia_movimiento ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert fila["tipo"] == "APORTACION" and fila["importe_eur"] == pytest.approx(-1_500.0)
        assert fila["detalle"] == "viaje"

    def test_no_se_puede_retirar_mas_que_el_efectivo_disponible(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=50.0)  # consume 5.000 EUR de caja

        with pytest.raises(EfectivoInsuficiente):
            cartera_ia.retirar(importe_eur=6_000.0, motivo="x", actor="propietario")

        assert cartera_ia.cash_eur() == pytest.approx(5_000.0)  # intacta: la retirada no se aplicó

    @pytest.mark.parametrize("importe", [0.0, -50.0, float("nan")])
    def test_rechaza_un_importe_no_valido(self, tmp_path: Path, importe: float) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        with pytest.raises(ValueError):
            cartera_ia.retirar(importe_eur=importe, motivo="x", actor="propietario")
        assert cartera_ia.cash_eur() == pytest.approx(10_000.0)

    def test_sin_cartera_activa_no_se_puede_retirar(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        with pytest.raises(CarteraInactiva):
            cartera_ia.retirar(importe_eur=100.0, motivo="x", actor="propietario")


class TestReiniciarCarteraVacia:
    def test_archiva_una_cartera_vacia_y_activa_otra_con_el_capital_nuevo(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)

        generacion_id = cartera_ia.reiniciar_cartera(
            capital_inicial_eur=20_000.0, motivo="nueva estrategia", actor="propietario", instante=T_ACTIVACION,
        )

        assert cartera_ia.cash_eur() == pytest.approx(20_000.0)
        assert cartera_ia.posiciones_abiertas() == ()
        assert cartera_ia.verificar_invariante_contable()
        generaciones = cartera_ia.generaciones_archivadas()
        assert len(generaciones) == 1 and generaciones[0]["id"] == generacion_id
        assert generaciones[0]["capital_inicial_eur"] == pytest.approx(10_000.0)
        assert generaciones[0]["cash_final_eur"] == pytest.approx(10_000.0)
        assert generaciones[0]["actor"] == "propietario" and generaciones[0]["motivo"] == "nueva estrategia"

    @pytest.mark.parametrize("capital", [0.0, -1.0, float("nan")])
    def test_rechaza_un_capital_inicial_no_valido(self, tmp_path: Path, capital: float) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        with pytest.raises(ValueError):
            cartera_ia.reiniciar_cartera(capital_inicial_eur=capital, motivo="x", actor="y", instante=T_ACTIVACION)
        assert cartera_ia.cash_eur() == pytest.approx(10_000.0)
        assert cartera_ia.generaciones_archivadas() == ()

    def test_sin_cartera_activa_no_se_puede_reiniciar(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        with pytest.raises(CarteraInactiva):
            cartera_ia.reiniciar_cartera(capital_inicial_eur=10_000.0, motivo="x", actor="y", instante=T_ACTIVACION)


class TestReiniciarCarteraConPosicionesYOrdenes:
    def test_una_posicion_abierta_se_archiva_tal_cual_nunca_se_liquida_ficticiamente(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        position_id = _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)

        generacion_id = cartera_ia.reiniciar_cartera(
            capital_inicial_eur=5_000.0, motivo="x", actor="propietario", instante=T_ACTIVACION,
        )

        assert cartera_ia.posiciones_abiertas() == ()  # nada vivo en la cartera nueva
        archivadas = cartera_ia.posiciones_de_la_generacion(generacion_id)
        assert len(archivadas) == 1
        assert archivadas[0]["id"] == position_id and archivadas[0]["symbol"] == "A"
        # Sigue ABIERTA en el archivo: nunca se le inventó una venta para "cerrarla".
        assert archivadas[0]["estado"] == "ABIERTA"
        assert archivadas[0]["exit_price"] is None and archivadas[0]["motivo_cierre"] is None

    def test_las_ordenes_pendientes_se_rechazan_antes_de_archivarse_nunca_sobreviven(self, tmp_path: Path) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _comprar_pendiente(cartera_ia, reg, symbol="B", target_session=date(2026, 11, 6))
        position_id = _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)
        _vender_pendiente(cartera_ia, reg, position_id)

        generacion_id = cartera_ia.reiniciar_cartera(
            capital_inicial_eur=5_000.0, motivo="x", actor="propietario", instante=T_ACTIVACION,
        )

        assert cartera_ia.pendientes_entrada() == () and cartera_ia.pendientes_salida() == ()
        ordenes = cartera_ia.ordenes_de_la_generacion(generacion_id)
        # 3 órdenes en total: la ENTRY ya EJECUTADA al abrir "A" (sin tocar), más la ENTRY de "B" y
        # la EXIT_IA de "A", ambas PENDIENTES antes del reinicio y ahora rechazadas.
        assert len(ordenes) == 3
        pendientes_antes = [o for o in ordenes if o["proposito"] != "ENTRY" or o["symbol"] == "B"]
        assert len(pendientes_antes) == 2
        assert all(o["estado"] == "RECHAZADA" and o["motivo"] == "CARTERA_REINICIADA" for o in pendientes_antes)
        ejecutada = next(o for o in ordenes if o["proposito"] == "ENTRY" and o["symbol"] == "A")
        assert ejecutada["estado"] == "EJECUTADA"

    def test_una_orden_antigua_no_reaparece_ni_bloquea_un_simbolo_repetido(self, tmp_path: Path) -> None:
        """Pedido explícito de validación: que no reaparezcan órdenes antiguas tras el reinicio,
        ni que una posición archivada bloquee reabrir el mismo símbolo en la cartera nueva."""

        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)
        cartera_ia.reiniciar_cartera(capital_inicial_eur=10_000.0, motivo="x", actor="y", instante=T_ACTIVACION)

        # El mismo símbolo, en la cartera nueva: no debe chocar con la unicidad de la archivada.
        nueva_position_id = _abrir(cartera_ia, symbol="A", entry_price=50.0, units=4.0)

        assert len(cartera_ia.posiciones_abiertas()) == 1
        assert cartera_ia.posiciones_abiertas()[0].id == nueva_position_id
        assert cartera_ia.posiciones_abiertas()[0].entry_price == 50.0

    def test_conserva_integramente_el_historial_de_decisiones_de_la_ia(self, tmp_path: Path) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        reg.conn.execute("INSERT INTO ia_paquete (input_hash, tipo, symbol, contenido) VALUES ('h','COMPRA','A','{}')")
        pasada_id = reg.abrir_pasada(T_ACTIVACION, "activo", "sha")
        decision_id = reg.guardar_decision(
            clave="A|2026-11-05|2026-11-06|x", pasada_id=pasada_id, symbol="A", market="NYSE", tipo="COMPRA",
            signal_session="2026-11-05", target_session="2026-11-06", target_open=SESION_OBJETIVO.isoformat(),
            decision_ts=T_ACTIVACION.isoformat(), input_hash="h", cuantitativo="{}", votos="{}", predicados=None,
            resolucion="DESCARTAR", motivo="RECHAZADA_POR_ASESOR", prioridad="BAJA", causa=None,
        )

        cartera_ia.reiniciar_cartera(capital_inicial_eur=10_000.0, motivo="x", actor="y", instante=T_ACTIVACION)

        # ia_decision/ia_pasada/ia_paquete son ajenos a la cartera: el reinicio nunca los toca.
        fila = reg.conn.execute("SELECT id, resolucion FROM ia_decision WHERE id = ?", (decision_id,)).fetchone()
        assert fila is not None and fila["resolucion"] == "DESCARTAR"
        assert reg.conn.execute("SELECT COUNT(*) FROM ia_pasada").fetchone()[0] == 1


class TestReinicioAtomico:
    def test_una_interrupcion_a_mitad_del_reinicio_no_deja_nada_a_medias(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """El último paso del reinicio (el evento de auditoría) falla a propósito: nada de lo
        anterior —archivado, borrado de las tablas en vivo, capital nuevo— debe haberse
        confirmado. El reinicio tiene que poder reintentarse después sin ningún rastro parcial."""

        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)
        original_evento = CarteraIA._evento

        def _evento_que_falla(self: CarteraIA, conn: Any, tipo: str, symbol: Any, payload: Any) -> None:
            if tipo == "CARTERA_REINICIADA":
                raise RuntimeError("caída simulada justo antes de confirmar")
            original_evento(self, conn, tipo, symbol, payload)

        monkeypatch.setattr(CarteraIA, "_evento", _evento_que_falla)

        with pytest.raises(RuntimeError):
            cartera_ia.reiniciar_cartera(
                capital_inicial_eur=5_000.0, motivo="x", actor="y", instante=T_ACTIVACION,
            )

        assert cartera_ia.generaciones_archivadas() == ()
        assert len(cartera_ia.posiciones_abiertas()) == 1
        assert cartera_ia.cash_eur() == pytest.approx(9_000.0)  # sin tocar: 10.000 - 1.000 de la entrada
        assert cartera_ia.verificar_invariante_contable()

        # Reintentar después (ya sin el fallo inyectado) debe completar el reinicio con normalidad.
        monkeypatch.setattr(CarteraIA, "_evento", original_evento)
        generacion_id = cartera_ia.reiniciar_cartera(
            capital_inicial_eur=5_000.0, motivo="reintento", actor="y", instante=T_ACTIVACION,
        )
        assert cartera_ia.cash_eur() == pytest.approx(5_000.0)
        assert len(cartera_ia.generaciones_archivadas()) == 1
        assert cartera_ia.generaciones_archivadas()[0]["id"] == generacion_id


class TestFronteraDeDecisionesEntreGeneraciones:
    """Hallazgo bloqueante de Codex: una decisión no puede generar ningún efecto económico
    después de cruzar un reinicio, ni por repetición ni por el barrido de recuperación."""

    def test_repetir_una_decision_ya_aplicada_tras_el_reinicio_no_recrea_su_orden(self, tmp_path: Path) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        decision_id = _comprar_pendiente(cartera_ia, reg, symbol="A", target_session=date(2026, 11, 6))
        fila_antes = reg.conn.execute("SELECT aplicada FROM ia_decision WHERE id = ?", (decision_id,)).fetchone()
        assert fila_antes["aplicada"] == 1  # ya materializada antes del reinicio

        cartera_ia.reiniciar_cartera(capital_inicial_eur=5_000.0, motivo="x", actor="y", instante=T_ACTIVACION)

        # Repetir la materialización (un reintento, una llamada doble) no debe crear nada nuevo.
        cartera_ia.materializar_decision_compra(
            decision_id=decision_id, symbol="A", market="NYSE", currency="EUR", target_session=date(2026, 11, 6),
            target_open=APERTURA, niveles=NIVELES_COMPRA, instante=T_ACTIVACION,
        )

        assert cartera_ia.pendientes_entrada() == ()
        assert cartera_ia.cash_eur() == pytest.approx(5_000.0)  # intacto: ninguna ENTRY nueva que lo toque

    def test_una_decision_sin_aplicar_antes_del_reinicio_no_se_materializa_despues(self, tmp_path: Path) -> None:
        """Una decisión COMPRAR persistida pero interrumpida ANTES de materializarse (``aplicada
        = 0``), si el reinicio ocurre en ese hueco, nunca debe llegar a crear una orden contra el
        capital de la generación siguiente a través del barrido de recuperación."""

        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        reg.conn.execute(
            "INSERT INTO ia_paquete (input_hash, tipo, symbol, contenido) VALUES ('h','COMPRA','A','{}')"
        )
        pasada_id = reg.abrir_pasada(T_ACTIVACION, "activo", "sha")
        cuantitativo = (
            '{"currency": "EUR", "niveles": {"stop": 90.0, "invalidation_level": 90.0, "entry_max": 105.0, '
            '"target1": 110.0, "target2": 115.0, "min_rr_ratio": 1.5}}'
        )
        decision_id = reg.guardar_decision(
            clave="A|2026-11-05|2026-11-06|x", pasada_id=pasada_id, symbol="A", market="NYSE", tipo="COMPRA",
            signal_session="2026-11-05", target_session="2026-11-06", target_open=APERTURA.isoformat(),
            decision_ts=T_ACTIVACION.isoformat(), input_hash="h", cuantitativo=cuantitativo, votos="{}",
            predicados=None, resolucion="COMPRAR", motivo="APROBADA_POR_AMBOS", prioridad="ALTA", causa=None,
        )
        # Nunca se llamó a materializar_decision_compra: la pasada se interrumpió justo antes.

        cartera_ia.reiniciar_cartera(capital_inicial_eur=5_000.0, motivo="x", actor="y", instante=T_ACTIVACION)

        incidencias: list[str] = []
        cartera_ia.recuperar_decisiones_sin_aplicar(T_ACTIVACION, incidencias)

        assert cartera_ia.pendientes_entrada() == ()
        assert cartera_ia.cash_eur() == pytest.approx(5_000.0)
        fila = reg.conn.execute("SELECT aplicada FROM ia_decision WHERE id = ?", (decision_id,)).fetchone()
        # Neutralizada por el reinicio (no por haberse materializado): nunca generó una orden.
        assert fila["aplicada"] == 1

    def test_una_llamada_directa_tras_el_reinicio_sobre_una_decision_neutralizada_no_crea_nada(
        self, tmp_path: Path,
    ) -> None:
        """Segundo hallazgo de Codex: ``aplicada=1`` sin ninguna orden (ni viva ni archivada) es
        el estado de una decisión NEUTRALIZADA por el reinicio, no el de una materialización a
        medias. Una llamada directa a ``materializar_decision_compra`` que llegue después —un
        trabajador ya en vuelo antes del reinicio, no solo el barrido de recuperación— tampoco
        debe crear nada."""

        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        reg.conn.execute(
            "INSERT INTO ia_paquete (input_hash, tipo, symbol, contenido) VALUES ('race','COMPRA','A','{}')"
        )
        pasada_id = reg.abrir_pasada(T_ACTIVACION, "activo", "sha")
        decision_id = reg.guardar_decision(
            clave="race", pasada_id=pasada_id, symbol="A", market="NYSE", tipo="COMPRA",
            signal_session="2026-11-05", target_session="2026-11-06", target_open=APERTURA.isoformat(),
            decision_ts=T_ACTIVACION.isoformat(), input_hash="race", cuantitativo="{}", votos="{}",
            predicados=None, resolucion="COMPRAR", motivo="APROBADA_POR_AMBOS", prioridad="ALTA", causa=None,
        )

        cartera_ia.reiniciar_cartera(capital_inicial_eur=5_000.0, motivo="x", actor="y", instante=T_ACTIVACION)
        assert reg.conn.execute(
            "SELECT aplicada FROM ia_decision WHERE id = ?", (decision_id,)
        ).fetchone()["aplicada"] == 1

        cartera_ia.materializar_decision_compra(
            decision_id=decision_id, symbol="A", market="NYSE", currency="EUR", target_session=date(2026, 11, 6),
            target_open=APERTURA, niveles=NIVELES_COMPRA, instante=T_ACTIVACION,
        )

        assert cartera_ia.pendientes_entrada() == ()
        assert reg.conn.execute("SELECT COUNT(*) FROM ia_orden WHERE decision_id = ?", (decision_id,)).fetchone()[0] == 0
        assert cartera_ia.cash_eur() == pytest.approx(5_000.0)

    def test_una_llamada_directa_de_venta_tras_el_reinicio_sobre_una_decision_neutralizada_no_crea_nada(
        self, tmp_path: Path,
    ) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        position_id = _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)
        reg.conn.execute(
            "INSERT INTO ia_paquete (input_hash, tipo, symbol, contenido) VALUES ('race-v','POSICION','A','{}')"
        )
        pasada_id = reg.abrir_pasada(T_ACTIVACION, "activo", "sha")
        decision_id = reg.guardar_decision(
            clave="race-v", pasada_id=pasada_id, symbol="A", market="NYSE", tipo="POSICION",
            signal_session="2026-11-05", target_session=SESION_OBJETIVO.isoformat(), target_open=APERTURA.isoformat(),
            decision_ts=T_ACTIVACION.isoformat(), input_hash="race-v", cuantitativo="{}", votos="{}",
            predicados=None, resolucion="VENDER", motivo="CAUSA_VERIFICADA", prioridad=None, causa="CIERRE_BAJO_SMA",
        )

        cartera_ia.reiniciar_cartera(capital_inicial_eur=5_000.0, motivo="x", actor="y", instante=T_ACTIVACION)
        assert reg.conn.execute(
            "SELECT aplicada FROM ia_decision WHERE id = ?", (decision_id,)
        ).fetchone()["aplicada"] == 1

        cartera_ia.materializar_decision_venta(
            decision_id=decision_id, position_id=position_id, symbol="A", market="NYSE", currency="EUR",
            target_session=SESION_OBJETIVO, target_open=APERTURA, causa="CIERRE_BAJO_SMA", instante=T_ACTIVACION,
        )

        assert cartera_ia.pendientes_salida() == ()
        assert reg.conn.execute("SELECT COUNT(*) FROM ia_orden WHERE decision_id = ?", (decision_id,)).fetchone()[0] == 0


class TestLecturasParaElDashboard:
    def test_posiciones_cerradas_lista_lo_cerrado_mas_reciente_primero(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=1.0)
        posicion = cartera_ia.posiciones_abiertas()[0]
        cartera_ia.cerrar_posicion(
            posicion, exit_price=110.0, exit_price_eur=110.0, exit_session=SESION_OBJETIVO,
            origen="STOP_OBLIGATORIO", motivo="STOP_TOCADO",
        )

        cerradas = cartera_ia.posiciones_cerradas()

        assert len(cerradas) == 1 and cerradas[0]["symbol"] == "A" and cerradas[0]["estado"] == "CERRADA"
        assert cartera_ia.posiciones_abiertas() == ()

    def test_ordenes_y_fills_y_eventos_recientes_devuelven_lo_registrado(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=1.0)

        ordenes = cartera_ia.ordenes_recientes()
        fills = cartera_ia.fills_recientes()
        eventos = cartera_ia.eventos_recientes()

        assert len(ordenes) == 1 and ordenes[0]["symbol"] == "A" and ordenes[0]["proposito"] == "ENTRY"
        assert len(fills) == 1 and fills[0]["lado"] == "COMPRA"
        assert any(e["tipo"] == "POSICION_ABIERTA" for e in eventos)

    def test_el_limite_se_respeta(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        for symbol in ("A", "B", "C"):
            _abrir(cartera_ia, symbol=symbol, entry_price=100.0, units=1.0)

        assert len(cartera_ia.ordenes_recientes(limite=2)) == 2
        assert len(cartera_ia.fills_recientes(limite=2)) == 2

    def test_el_limite_por_estado_no_oculta_una_pendiente_antigua(self, tmp_path: Path) -> None:
        """Hallazgo de Codex: filtrar por estado DESPUÉS de aplicar el límite global podía ocultar
        una orden PENDIENTE antigua detrás de muchas EJECUTADA recientes."""

        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _comprar_pendiente(cartera_ia, reg, symbol="PEND", target_session=date(2026, 11, 6))
        for symbol in ("A", "B", "C"):  # tres ENTRY ya EJECUTADA, más recientes que la pendiente
            _abrir(cartera_ia, symbol=symbol, entry_price=100.0, units=1.0)

        pendientes = cartera_ia.ordenes_recientes(limite=2, estado="PENDIENTE")

        assert len(pendientes) == 1 and pendientes[0]["symbol"] == "PEND"

    def test_pasadas_y_gasto_total_del_registro(self, tmp_path: Path) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        reg.abrir_pasada(T_ACTIVACION, "activo", "sha1")
        reg.reservar("2026-11", 1.0)
        reg.conciliar("2026-11", 1.0, 0.4321)

        pasadas = reg.pasadas()

        assert len(pasadas) == 1 and pasadas[0]["modo"] == "activo"
        assert reg.gasto_total() == pytest.approx(0.4321)

    def test_decisiones_recientes_del_registro_esta_acotada_y_ordenada(self, tmp_path: Path) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        for n in range(3):
            reg.conn.execute(
                "INSERT INTO ia_paquete (input_hash, tipo, symbol, contenido) VALUES (?, 'COMPRA', 'A', '{}')",
                (f"h{n}",),
            )
            pasada_id = reg.abrir_pasada(T_ACTIVACION, "activo", "sha")
            reg.guardar_decision(
                clave=f"A|{n}|2026-11-05|2026-11-06|x", pasada_id=pasada_id, symbol="A", market="NYSE",
                tipo="COMPRA", signal_session="2026-11-05", target_session="2026-11-06",
                target_open="2026-11-06T14:30:00+00:00", decision_ts=T_ACTIVACION.isoformat(),
                input_hash=f"h{n}", cuantitativo="{}", votos="{}", predicados=None,
                resolucion="DESCARTAR", motivo=f"motivo-{n}", prioridad="BAJA", causa=None,
            )

        recientes = reg.decisiones_recientes(limite=2)

        assert len(recientes) == 2
        assert recientes[0]["motivo"] == "motivo-2"  # más reciente primero


class TestResumenCerradasYCapitalNeto:
    def test_resumen_cerradas_agrega_sin_cargar_filas(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=1.0)
        posicion = cartera_ia.posiciones_abiertas()[0]
        cartera_ia.cerrar_posicion(
            posicion, exit_price=110.0, exit_price_eur=110.0, exit_session=SESION_OBJETIVO,
            origen="STOP_OBLIGATORIO", motivo="m",
        )

        num_cerradas, pnl = cartera_ia.resumen_cerradas()

        assert num_cerradas == 1 and pnl == pytest.approx(10.0)

    def test_capital_neto_aportado_incluye_activacion_aportes_y_retiradas(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        cartera_ia.aportar(importe_eur=2_000.0, motivo="x", actor="y")
        cartera_ia.retirar(importe_eur=500.0, motivo="x", actor="y")

        assert cartera_ia.capital_neto_aportado_eur() == pytest.approx(11_500.0)
