"""Pruebas finales de la Entrega C (condición 4 de la autorización): el ciclo completo
compra -> mantener -> venta a través de la pasada real, con reconexiones que simulan un
reinicio del proceso entre cada paso, comprobando en cada uno que el dashboard y los avisos
de Telegram quedan consistentes y sin duplicados; además, recuperación segura ante un fallo
de contexto a mitad de pasada.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional, Tuple

import pytest

from superbot.ia import dashboard, datos, telegram
from superbot.ia.cartera import CarteraIA
from superbot.ia.paquete import Observacion
from superbot.ia.registro import RegistroIA
from tests.test_superbot_ia import ClienteFalso, T, _analisis, _pasada, compra_ok, registro
from tests.test_superbot_ia_cartera import _abrir, _proveedor_ohlc
from tests.test_superbot_ia_fase2 import SESION_OBJETIVO
from tests.test_superbot_ia_telegram import _NotifierFalso

T_ACTIVACION = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)
# ``_analisis`` (de ``test_superbot_ia``) fecha la sesión objetivo de forma fija al 2026-11-06:
# sirve para la compra inicial, pero ``validar_causal`` exige que toda decisión (también un
# MANTENER o un VENDER) tenga ``decision_ts < target_open`` — así que una evaluación posterior
# sobre la MISMA posición, ya en un día distinto, necesita sus propias fechas, desplazadas día a
# día como pasaría en una cadencia diaria real.
DIA_DECISION_MANTENER = date(2026, 11, 7)
SESION_MANTENER = date(2026, 11, 8)
APERTURA_MANTENER = datetime(2026, 11, 8, 14, 30, tzinfo=timezone.utc)
DIA_DECISION_VENDER = date(2026, 11, 8)
SESION_SALIDA = date(2026, 11, 9)
APERTURA_SALIDA = datetime(2026, 11, 9, 14, 30, tzinfo=timezone.utc)


def _analisis_en(
    symbol: str, decision_day: date, target_session: date, target_open: datetime, score: float = 72.0,
    close: float = 100.0, sma: Optional[float] = 90.0,
) -> datos.Analisis:
    """Como ``_analisis``, pero con las fechas causales desplazadas al día de la decisión que
    corresponda — necesario para evaluar una posición ya abierta en una pasada de un día
    posterior a la de su compra."""

    instante_decision = datetime(decision_day.year, decision_day.month, decision_day.day, 21, 45, tzinfo=timezone.utc)
    s = SimpleNamespace(
        price=close, ema_fast=97.0, ema_slow=93.0, sma_long=88.0, rsi=61.0, atr=2.4, macd_hist=0.3, volume_ratio=1.2,
        gap_pct=0.1, return_short=5.0, return_medium=9.0, return_long=20.0, volatility_pct=25.0, relative_strength=2.0, bars=250,
    )
    op = SimpleNamespace(
        snapshot=s,
        levels=SimpleNamespace(
            entry_max=101.0, target1=103.0, target2=107.0, rr_ratio=1.5, invalidation_level=95.0, stop=95.0,
            min_rr_ratio=1.5,
        ),
        score=SimpleNamespace(value=score, model_version="1.0", missing_dimensions=[]),
        accion="COMPRAR",
        data_freshness=SimpleNamespace(data_quality=SimpleNamespace(execution_readiness=True, indicator_readiness=True)),
    )
    asset = SimpleNamespace(symbol=symbol, name=symbol, asset_class="stock", region="USA", currency="USD", trade_republic="yes")
    return datos.Analisis(
        asset=asset, oportunidad=op, market="NYSE", signal_session=decision_day,  # type: ignore[arg-type]
        target_session=target_session, target_open=target_open, close=close, open=close, low=close, sma=sma,
        observaciones=(
            Observacion(
                "barras", symbol, decision_day.isoformat(), instante_decision - timedelta(minutes=30),
                instante_decision, "h",
            ),
        ),
    )


def _reabrir(tmp_path: Path) -> Tuple[RegistroIA, CarteraIA]:
    """Simula el reinicio del proceso: cierra la conexión y abre una nueva contra el mismo
    fichero, exactamente como pasaría si ``pasada``/``dashboard``/``telegram`` se invocaran como
    comandos CLI independientes (cron, systemd) en vez de dentro de un único proceso largo."""

    reg = registro(tmp_path)
    return reg, CarteraIA(reg.conn)


class TestCicloCompletoConReinicios:
    def test_compra_mantener_venta_con_reinicios_entre_cada_paso(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        reg, cartera_ia = _reabrir(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)

        # --- Pasada 1: el comité decide COMPRAR -> orden de entrada pendiente, nada ejecutado ---
        resultado1, reg = _pasada(
            tmp_path, monkeypatch, [_analisis("A", score=72.0)], ClienteFalso(por_defecto=compra_ok()),
            cartera_ia=cartera_ia, registro_existente=reg, proveedor=_proveedor_ohlc({}), instante=T,
        )
        assert resultado1.compras == ["A"] and resultado1.aperturas == []
        assert cartera_ia.posiciones_abiertas() == ()
        assert dashboard.build_stats(cartera_ia)["num_abiertas"] == 0
        # Nada se ejecutó: ningún aviso de OPERACIONES (el resumen periódico de la primera pasada
        # tras activar sí se encola, pero eso no es una notificación de compra/venta).
        assert not any(n["tipo"] == "OPERACIONES" for n in cartera_ia.notificaciones_pendientes())
        reg.close()

        # --- "Reinicio" ---
        reg, cartera_ia = _reabrir(tmp_path)
        assert len(cartera_ia.pendientes_entrada()) == 1  # la orden pendiente sobrevive al reinicio

        # --- Pasada 2: se ejecuta la entrada en la apertura de la sesión objetivo ---
        # ``_analisis`` genera activos en USD: sin la barra de ``EURUSD=X`` de esa sesión exacta la
        # orden se queda pendiente para siempre (nunca se rechaza, nunca se ejecuta).
        # Apertura a 98,0: con los niveles por defecto de ``_analisis`` (target2 107, stop 95), una
        # apertura de 100 deja la relación beneficio/riesgo por debajo del mínimo (1,4 < 1,5) y el
        # propio gate de apertura rechaza la orden.
        proveedor2 = _proveedor_ohlc({
            "A": {SESION_OBJETIVO: (98.0, 96.0, 99.0)}, "EURUSD=X": {SESION_OBJETIVO: (1.1, 1.1, 1.1)},
        })
        resultado2, reg = _pasada(
            tmp_path, monkeypatch, [_analisis("A", score=72.0)],
            ClienteFalso(respuestas=[Exception("sin disparador: no debería llamarse a la IA")]),
            cartera_ia=cartera_ia, registro_existente=reg, proveedor=proveedor2,
            instante=T_ACTIVACION + timedelta(days=4), reloj=lambda: T_ACTIVACION + timedelta(days=4),
        )
        assert resultado2.aperturas == ["A"]
        stats2 = dashboard.build_stats(cartera_ia)
        assert stats2["num_abiertas"] == 1 and stats2["num_cerradas"] == 0
        assert stats2["cash_eur"] < 10_000.0  # el coste de la entrada redujo el efectivo
        pendientes2 = [n for n in cartera_ia.notificaciones_pendientes() if n["tipo"] == "OPERACIONES"]
        assert len(pendientes2) == 1 and "COMPRA ejecutada" in pendientes2[0]["texto"] and "A" in pendientes2[0]["texto"]
        reg.close()

        # --- "Reinicio" ---
        reg, cartera_ia = _reabrir(tmp_path)
        assert len(cartera_ia.posiciones_abiertas()) == 1  # la posición abierta sobrevive al reinicio
        assert len([n for n in cartera_ia.notificaciones_pendientes() if n["tipo"] == "OPERACIONES"]) == 1

        # --- Pasada 3: MANTENER sobre la posición ya abierta ---
        mantiene: Dict[str, Any] = {
            "decision": "MANTENER", "causa": None, "motivos": ["Todavía razonable mantenerla"],
            "riesgos": ["Puede seguir cayendo"], "datos_citados": ["posicion.cierre"],
        }
        instante_mantener = datetime(2026, 11, 7, 21, 45, tzinfo=timezone.utc)
        # ``construir_estado_cartera`` valora cada posición abierta con el FX de SU PROPIA
        # ``signal_session`` (aquí, el día de esta decisión), no el de la sesión objetivo.
        proveedor3 = _proveedor_ohlc({
            "A": {SESION_MANTENER: (99.0, 97.0, 99.0)}, "EURUSD=X": {DIA_DECISION_MANTENER: (1.1, 1.1, 1.1)},
        })
        resultado3, reg = _pasada(
            tmp_path, monkeypatch,
            # El predicado SMA exige un margen del 2% (``sma_holgura``): un cierre de 95 bajo una
            # SMA de 100 sí lo dispara (95 < 98); 99 no lo haría.
            [_analisis_en("A", DIA_DECISION_MANTENER, SESION_MANTENER, APERTURA_MANTENER, close=95.0, sma=100.0)],
            ClienteFalso(por_defecto=mantiene), cartera_ia=cartera_ia, registro_existente=reg, proveedor=proveedor3,
            instante=instante_mantener, reloj=lambda: instante_mantener,
        )
        assert resultado3.ventas == [] and resultado3.cerradas_stop == []
        fila3 = next(d for d in reg.decisiones(resultado3.pasada_id) if d["symbol"] == "A")
        assert fila3["resolucion"] == "MANTENER" and fila3["aplicada"] == 1
        stats3 = dashboard.build_stats(cartera_ia)
        assert stats3["num_abiertas"] == 1 and stats3["num_cerradas"] == 0
        assert stats3["cash_eur"] == stats2["cash_eur"]  # MANTENER nunca mueve dinero
        # MANTENER nunca genera un aviso de operación (no es una ejecución real).
        nuevos3 = [n for n in cartera_ia.notificaciones_pendientes() if n["clave"] == f"pasada:{resultado3.pasada_id}"]
        assert nuevos3 == []
        reg.close()

        # --- "Reinicio" ---
        reg, cartera_ia = _reabrir(tmp_path)
        assert len(cartera_ia.posiciones_abiertas()) == 1

        # --- Pasada 4: el comité decide VENDER (causa real) -> salida IA pendiente ---
        vende: Dict[str, Any] = {
            "decision": "VENDER", "causa": "CIERRE_BAJO_SMA", "motivos": ["Perdió la media"],
            "riesgos": ["Puede rebotar"], "datos_citados": ["predicados.CIERRE_BAJO_SMA"],
        }
        instante_vender = datetime(2026, 11, 8, 21, 45, tzinfo=timezone.utc)
        resultado4, reg = _pasada(
            tmp_path, monkeypatch,
            [_analisis_en("A", DIA_DECISION_VENDER, SESION_SALIDA, APERTURA_SALIDA, close=85.0, sma=90.0)],
            ClienteFalso(por_defecto=vende), cartera_ia=cartera_ia, registro_existente=reg,
            proveedor=_proveedor_ohlc({"EURUSD=X": {DIA_DECISION_VENDER: (1.1, 1.1, 1.1)}}),
            instante=instante_vender, reloj=lambda: instante_vender,
        )
        assert resultado4.ventas == ["A"] and resultado4.salidas_ia == []  # decidida, no ejecutada todavía
        assert len(cartera_ia.posiciones_abiertas()) == 1  # sigue abierta: se liquida en la apertura siguiente
        assert len(cartera_ia.pendientes_salida()) == 1
        assert dashboard.build_stats(cartera_ia)["num_abiertas"] == 1  # el dashboard no adelanta nada
        assert [n for n in cartera_ia.notificaciones_pendientes() if n["clave"] == f"pasada:{resultado4.pasada_id}"] == []
        reg.close()

        # --- "Reinicio" ---
        reg, cartera_ia = _reabrir(tmp_path)
        assert len(cartera_ia.pendientes_salida()) == 1  # la salida pendiente sobrevive al reinicio

        # --- Pasada 5: se ejecuta la venta IA en la apertura de su sesión objetivo ---
        proveedor5 = _proveedor_ohlc({
            "A": {SESION_SALIDA: (98.0, 96.0, 99.0)}, "EURUSD=X": {SESION_SALIDA: (1.1, 1.1, 1.1)},
        })  # por encima del stop vigente
        resultado5, reg = _pasada(
            tmp_path, monkeypatch, [_analisis("A", score=72.0)],
            ClienteFalso(respuestas=[Exception("salida IA ya pendiente: no debería llamarse de nuevo")]),
            cartera_ia=cartera_ia, registro_existente=reg, proveedor=proveedor5,
            # La orden solo es "causalmente observable" cuando toda la barra diaria de su sesión
            # objetivo ya cerró (``session_close_at``), no apenas tras su apertura.
            instante=APERTURA_SALIDA + timedelta(days=1), reloj=lambda: APERTURA_SALIDA + timedelta(days=1),
        )
        assert resultado5.salidas_ia == ["A"] and resultado5.rechazos_salida == []
        assert cartera_ia.posiciones_abiertas() == ()
        stats5 = dashboard.build_stats(cartera_ia)
        assert stats5["num_abiertas"] == 0 and stats5["num_cerradas"] == 1
        assert cartera_ia.verificar_invariante_contable()

        pendientes5 = [n for n in cartera_ia.notificaciones_pendientes() if n["tipo"] == "OPERACIONES"]
        venta_avisos = [n for n in pendientes5 if n["clave"] == f"pasada:{resultado5.pasada_id}"]
        assert len(venta_avisos) == 1
        assert "VENTA ejecutada" in venta_avisos[0]["texto"] and "venta de la IA" in venta_avisos[0]["texto"]

        # --- Reintentar el encolado de la misma pasada (como si el proceso hubiera muerto justo
        # después de ejecutar y se repitiera la notificación al reiniciar): nunca duplica. ---
        total_antes_de_reintentar = len(cartera_ia.notificaciones_pendientes())
        telegram.encolar_notificaciones_de_la_pasada(cartera_ia, resultado5, APERTURA_SALIDA + timedelta(days=1))
        assert len(cartera_ia.notificaciones_pendientes()) == total_antes_de_reintentar  # nada nuevo
        assert len([n for n in cartera_ia.notificaciones_pendientes() if n["clave"] == f"pasada:{resultado5.pasada_id}"]) == 1

        # --- Vaciar la cola de verdad: cada aviso se envía exactamente una vez ---
        # (incluye también el resumen periódico encolado tras activar, en la pasada 1, que
        # seguía sin enviarse: la cola acumula avisos de distinto tipo hasta que algo la vacía.)
        total_antes_del_flush = len(cartera_ia.notificaciones_pendientes())
        notifier = _NotifierFalso()
        contadores = telegram.flush(cartera_ia, notifier)
        assert contadores["ENVIADA"] == total_antes_del_flush
        assert cartera_ia.notificaciones_pendientes() == ()
        contadores_repetido = telegram.flush(cartera_ia, notifier)
        assert contadores_repetido == {"ENVIADA": 0, "FALLIDA": 0, "SIN_CONFIGURAR": 0}  # nada que reenviar
        assert len(notifier.enviados) == total_antes_del_flush  # cada mensaje se envió una sola vez

    def test_un_fallo_de_contexto_no_corrompe_nada_y_encola_un_aviso_de_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        reg, cartera_ia = _reabrir(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        resultado_ok, reg = _pasada(
            tmp_path, monkeypatch, [_analisis("A", score=72.0)], ClienteFalso(por_defecto=compra_ok()),
            cartera_ia=cartera_ia, registro_existente=reg, proveedor=_proveedor_ohlc({}), instante=T,
        )
        assert resultado_ok.compras == ["A"]
        pendientes_antes = len(cartera_ia.pendientes_entrada())
        cash_antes = cartera_ia.cash_eur()
        reg.close()

        reg, cartera_ia = _reabrir(tmp_path)
        resultado_error, reg = _pasada(
            tmp_path, monkeypatch, [], ClienteFalso(respuestas=[Exception("no debería llamarse")]),
            cartera_ia=cartera_ia, registro_existente=reg, proveedor=_proveedor_ohlc({}),
            contexto=RuntimeError("fallo simulado al cargar el contexto de mercado"),
            instante=T_ACTIVACION + timedelta(days=1), reloj=lambda: T_ACTIVACION + timedelta(days=1),
        )

        assert resultado_error.status == "ERROR"
        # Nada se corrompió: la orden pendiente y el efectivo quedan exactamente como estaban.
        assert len(cartera_ia.pendientes_entrada()) == pendientes_antes
        assert cartera_ia.cash_eur() == pytest.approx(cash_antes)
        assert cartera_ia.verificar_invariante_contable()
        avisos_error = [n for n in cartera_ia.notificaciones_pendientes() if n["tipo"] == "ERROR"]
        assert len(avisos_error) == 1 and "fallo simulado" in avisos_error[0]["texto"]

        # Una pasada posterior, ya sana, sigue funcionando con normalidad sobre el mismo estado.
        reg.close()
        reg, cartera_ia = _reabrir(tmp_path)
        proveedor_fin = _proveedor_ohlc({
            "A": {SESION_OBJETIVO: (98.0, 96.0, 99.0)}, "EURUSD=X": {SESION_OBJETIVO: (1.1, 1.1, 1.1)},
        })
        resultado_recuperada, reg = _pasada(
            tmp_path, monkeypatch, [_analisis("A", score=72.0)],
            ClienteFalso(respuestas=[Exception("sin disparador: no debería llamarse a la IA")]),
            cartera_ia=cartera_ia, registro_existente=reg, proveedor=proveedor_fin,
            instante=T_ACTIVACION + timedelta(days=5), reloj=lambda: T_ACTIVACION + timedelta(days=5),
        )
        assert resultado_recuperada.status == "OK" and resultado_recuperada.aperturas == ["A"]
        assert cartera_ia.verificar_invariante_contable()

    def test_un_stop_real_durante_el_mantenimiento_se_notifica_aunque_el_contexto_falle_despues(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Hallazgo de Codex sobre la condición 4: el caso más exigente no es que el contexto
        falle ANTES de que haya nada que ejecutar (trivial para la caja), sino que el
        mantenimiento SÍ ejecute una operación real (aquí, un stop) y el contexto falle justo
        DESPUÉS, en la misma pasada — ambos avisos (OPERACIONES por el stop y ERROR por el fallo)
        deben quedar encolados, nunca solo uno de los dos."""

        reg, cartera_ia = _reabrir(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", stop=90.0, entry_price=100.0, units=10.0, entry_session=date(2026, 11, 3))
        cash_antes = cartera_ia.cash_eur()
        # Abre ya por debajo del stop: se liquida en el mantenimiento, antes de que se intente
        # cargar el contexto de mercado.
        proveedor = _proveedor_ohlc({"A": {date(2026, 11, 4): (85.0, 80.0, 86.0)}})

        resultado, reg = _pasada(
            tmp_path, monkeypatch, [], ClienteFalso(respuestas=[Exception("no debería llamarse")]),
            cartera_ia=cartera_ia, registro_existente=reg, proveedor=proveedor,
            contexto=RuntimeError("fallo simulado al cargar el contexto de mercado"),
            instante=T_ACTIVACION + timedelta(days=2), reloj=lambda: T_ACTIVACION + timedelta(days=2),
        )

        assert resultado.status == "ERROR" and resultado.cerradas_stop == ["A"]
        assert cartera_ia.posiciones_abiertas() == ()  # el stop sí se ejecutó de verdad
        assert cartera_ia.cash_eur() == pytest.approx(cash_antes + 10 * 85.0)
        assert cartera_ia.verificar_invariante_contable()

        pendientes = cartera_ia.notificaciones_pendientes()
        operaciones = [n for n in pendientes if n["tipo"] == "OPERACIONES"]
        errores = [n for n in pendientes if n["tipo"] == "ERROR"]
        assert len(operaciones) == 1 and "VENTA ejecutada" in operaciones[0]["texto"]
        assert len(errores) == 1 and "fallo simulado" in errores[0]["texto"]
