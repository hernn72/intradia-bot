"""Superbot con IA, Entrega C (fase 2): COMPRAR real, gate de apertura y tamaño por riesgo."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Tuple

import pandas as pd
import pytest

from superbot.ia.cartera import (
    ABOVE_MAX_ENTRY,
    DATA_NOT_EXECUTABLE,
    ENTRY_OK,
    INVALID_STOP,
    INVALID_TARGET,
    RR_TOO_LOW,
    CarteraIA,
    OrdenYaResuelta,
    calcular_tamano_entrada,
    evaluar_gate_apertura,
    procesar_pendientes,
)
from tests.test_superbot_ia import APERTURA, ClienteFalso, _analisis, _pasada, compra_ok, registro

# Esquema real de la fase 1 (commit eef6987), para probar la migración contra una base tal como
# habría quedado entonces: ``ia_orden`` con ``position_id NOT NULL`` y sin las columnas de la fase 2.
_ESQUEMA_FASE_1 = """
CREATE TABLE IF NOT EXISTS ia_cartera (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    estado TEXT NOT NULL CHECK (estado IN ('INACTIVA', 'PAPER')),
    capital_inicial_eur REAL,
    cash_eur REAL NOT NULL DEFAULT 0,
    activated_at TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ia_movimiento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL CHECK (tipo IN ('APORTACION', 'COMPRA', 'VENTA', 'AJUSTE')),
    importe_eur REAL NOT NULL,
    referencia TEXT,
    detalle TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ia_posicion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    currency TEXT NOT NULL,
    estado TEXT NOT NULL CHECK (estado IN ('ABIERTA', 'CERRADA')),
    units REAL NOT NULL,
    entry_price REAL NOT NULL,
    entry_price_eur REAL NOT NULL,
    entry_session TEXT NOT NULL,
    stop_verificado_hasta TEXT NOT NULL,
    decision_apertura_id INTEGER,
    stop REAL NOT NULL,
    invalidation_level REAL,
    entry_max REAL,
    target1 REAL,
    target2 REAL,
    rr_minimo REAL,
    exit_price REAL,
    exit_price_eur REAL,
    exit_session TEXT,
    motivo_cierre TEXT,
    pnl_eur REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ia_posicion_abierta_unica ON ia_posicion (symbol) WHERE estado = 'ABIERTA';
CREATE TABLE IF NOT EXISTS ia_orden (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER NOT NULL REFERENCES ia_posicion(id),
    decision_id INTEGER,
    symbol TEXT NOT NULL,
    proposito TEXT NOT NULL CHECK (proposito IN ('ENTRY', 'EXIT_IA', 'STOP')),
    origen TEXT NOT NULL CHECK (origen IN ('DECISION_IA', 'STOP_OBLIGATORIO')),
    estado TEXT NOT NULL CHECK (estado IN ('EJECUTADA', 'RECHAZADA')),
    motivo TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ia_fill (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL UNIQUE REFERENCES ia_orden(id),
    symbol TEXT NOT NULL,
    lado TEXT NOT NULL CHECK (lado IN ('COMPRA', 'VENTA')),
    precio REAL NOT NULL,
    precio_eur REAL NOT NULL,
    units REAL NOT NULL,
    importe_eur REAL NOT NULL,
    session TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ia_evento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL,
    symbol TEXT,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

T_ACTIVACION = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)
T_DECISION = datetime(2026, 11, 5, 21, 45, tzinfo=timezone.utc)
SESION_OBJETIVO = date(2026, 11, 6)


def _cartera(tmp_path: Any) -> Tuple[CarteraIA, Any]:
    reg = registro(tmp_path)
    return CarteraIA(reg.conn), reg


def _proveedor_ohlc(barras: Dict[str, Dict[date, Tuple[float, float, float]]]) -> Any:
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

    return _Prov()


NIVELES = {"stop": 90.0, "invalidation_level": 90.0, "entry_max": 105.0, "target1": 110.0, "target2": 115.0, "min_rr_ratio": 1.5}


def _crear_decision_y_orden(cartera_ia: CarteraIA, reg: Any, symbol: str = "A", currency: str = "EUR") -> int:
    reg.conn.execute(
        "INSERT INTO ia_paquete (input_hash, tipo, symbol, contenido) VALUES (?, 'COMPRA', ?, '{}')", (f"h-{symbol}", symbol)
    )
    pasada_id = reg.abrir_pasada(T_ACTIVACION, "activo", "sha")
    decision_id = reg.guardar_decision(
        clave=f"{symbol}|2026-11-05|2026-11-06|x", pasada_id=pasada_id, symbol=symbol, market="NYSE", tipo="COMPRA",
        signal_session="2026-11-05", target_session="2026-11-06", target_open="2026-11-06T14:30:00+00:00",
        decision_ts=T_ACTIVACION.isoformat(), input_hash=f"h-{symbol}", cuantitativo="{}", votos="{}",
        predicados=None, resolucion="COMPRAR", motivo="APROBADA_POR_AMBOS", prioridad="ALTA", causa=None,
    )
    cartera_ia.materializar_decision_compra(
        decision_id=decision_id, symbol=symbol, market="NYSE", currency=currency, target_session=SESION_OBJETIVO,
        target_open=APERTURA, niveles=NIVELES, instante=T_ACTIVACION,
    )
    return decision_id


# --- gate de apertura ---------------------------------------------------------------


class TestEvaluarGateApertura:
    def test_aprobado_con_apertura_mejor_que_el_limite(self) -> None:
        r = evaluar_gate_apertura(95.0, stop=90.0, target2=115.0, entry_max=105.0, min_rr_ratio=1.5)
        assert r.aprobado and r.motivo == ENTRY_OK and r.eff == 95.0

    def test_aprobado_exactamente_en_el_limite_por_tolerancia(self) -> None:
        # Con stop=90 y target2=115, entry_max=100 es justo el precio al que el RR vale 1,5 (el
        # mínimo): entry_max_for_rr(115, 90, 1.5) = (115 + 1.5*90) / 2.5 = 100.
        r = evaluar_gate_apertura(100.0, stop=90.0, target2=115.0, entry_max=100.0 * (1 + 1e-12), min_rr_ratio=1.5)
        assert r.aprobado

    @pytest.mark.parametrize("open_native", [float("nan"), 0.0, -1.0])
    def test_apertura_no_ejecutable(self, open_native: float) -> None:
        r = evaluar_gate_apertura(open_native, stop=90.0, target2=115.0, entry_max=105.0, min_rr_ratio=1.5)
        assert not r.aprobado and r.motivo == DATA_NOT_EXECUTABLE

    def test_stop_invalido_si_no_es_menor_que_la_apertura(self) -> None:
        r = evaluar_gate_apertura(95.0, stop=95.0, target2=115.0, entry_max=105.0, min_rr_ratio=1.5)
        assert not r.aprobado and r.motivo == INVALID_STOP

    def test_target_invalido_si_no_supera_la_apertura(self) -> None:
        r = evaluar_gate_apertura(95.0, stop=90.0, target2=95.0, entry_max=105.0, min_rr_ratio=1.5)
        assert not r.aprobado and r.motivo == INVALID_TARGET

    def test_rechaza_gap_por_encima_del_limite(self) -> None:
        r = evaluar_gate_apertura(110.0, stop=90.0, target2=115.0, entry_max=105.0, min_rr_ratio=1.5)
        assert not r.aprobado and r.motivo == ABOVE_MAX_ENTRY

    def test_rechaza_ratio_beneficio_riesgo_insuficiente(self) -> None:
        # Entra a 101: riesgo 11, recompensa hasta 115 = 14 -> ratio 1.27, por debajo de 1.5.
        r = evaluar_gate_apertura(101.0, stop=90.0, target2=115.0, entry_max=105.0, min_rr_ratio=1.5)
        assert not r.aprobado and r.motivo == RR_TOO_LOW

    def test_sin_min_rr_ratio_no_rechaza_por_eso(self) -> None:
        r = evaluar_gate_apertura(101.0, stop=90.0, target2=115.0, entry_max=105.0, min_rr_ratio=None)
        assert r.aprobado


# --- tamaño de la entrada ------------------------------------------------------------


class TestCalcularTamanoEntrada:
    def test_limitado_por_riesgo(self) -> None:
        # 0,5% de 10.000 = 50 EUR de riesgo; (100-90)=10 de riesgo por unidad -> 5 unidades.
        # 10% de 10.000 = 1.000 EUR; a 100 EUR serían 10 unidades: manda el riesgo.
        unidades, importe = calcular_tamano_entrada(10_000.0, eff_native=100.0, stop_native=90.0, fx_rate=1.0)
        assert unidades == pytest.approx(5.0) and importe == pytest.approx(500.0)

    def test_limitado_por_tamano_de_posicion(self) -> None:
        # Riesgo pequeño (99 vs 100): 50/1 = 50 unidades, pero el 10% de equity a 100 EUR son 10.
        unidades, _importe = calcular_tamano_entrada(10_000.0, eff_native=100.0, stop_native=99.0, fx_rate=1.0)
        assert unidades == pytest.approx(10.0)

    def test_convierte_a_euros_con_el_tipo_de_cambio(self) -> None:
        unidades, importe = calcular_tamano_entrada(10_000.0, eff_native=100.0, stop_native=90.0, fx_rate=0.9)
        assert importe == pytest.approx(unidades * 100.0 * 0.9)

    @pytest.mark.parametrize("eff,stop", [(100.0, 100.0), (100.0, 110.0), (float("nan"), 90.0), (0.0, -1.0)])
    def test_sin_riesgo_valido_no_da_tamano(self, eff: float, stop: float) -> None:
        unidades, importe = calcular_tamano_entrada(10_000.0, eff_native=eff, stop_native=stop, fx_rate=1.0)
        assert unidades == 0.0 and importe == 0.0


# --- ciclo completo: decisión -> orden pendiente -> resolución ----------------------


class TestCicloDeEntrada:
    def test_idempotente_crear_la_misma_orden_dos_veces(self, tmp_path: Any) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        decision_id = _crear_decision_y_orden(cartera_ia, reg)
        primera = cartera_ia.pendientes_entrada()[0]
        cartera_ia.materializar_decision_compra(
            decision_id=decision_id, symbol="A", market="NYSE", currency="EUR", target_session=SESION_OBJETIVO,
            target_open=APERTURA, niveles=NIVELES, instante=T_ACTIVACION,
        )
        assert len(cartera_ia.pendientes_entrada()) == 1
        assert cartera_ia.pendientes_entrada()[0].id == primera.id

    def test_se_ejecuta_en_la_apertura_siguiente_con_el_tamano_correcto(self, tmp_path: Any) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _crear_decision_y_orden(cartera_ia, reg)
        proveedor = _proveedor_ohlc({"A": {SESION_OBJETIVO: (100.0, 95.0, 102.0)}})

        resultado = procesar_pendientes(cartera_ia, proveedor, T_ACTIVACION + timedelta(days=5), 0, [])

        assert resultado.abiertas == ["A"] and resultado.rechazadas == []
        posiciones = cartera_ia.posiciones_abiertas()
        assert len(posiciones) == 1 and posiciones[0].entry_price == 100.0 and posiciones[0].units == pytest.approx(5.0)
        assert cartera_ia.cash_eur() == pytest.approx(10_000.0 - 500.0)
        assert cartera_ia.verificar_invariante_contable()
        assert cartera_ia.pendientes_entrada() == ()

    def test_gap_por_encima_del_limite_rechaza_sin_tocar_cash(self, tmp_path: Any) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _crear_decision_y_orden(cartera_ia, reg)
        # Abre por encima de entry_max (105) pero por debajo de target2 (115): aísla ABOVE_MAX_ENTRY.
        proveedor = _proveedor_ohlc({"A": {SESION_OBJETIVO: (110.0, 108.0, 111.0)}})

        resultado = procesar_pendientes(cartera_ia, proveedor, T_ACTIVACION + timedelta(days=5), 0, [])

        assert resultado.abiertas == [] and resultado.rechazadas == ["A"]
        assert cartera_ia.posiciones_abiertas() == ()
        assert cartera_ia.cash_eur() == 10_000.0
        assert cartera_ia.verificar_invariante_contable()
        fila = reg.conn.execute("SELECT estado, motivo FROM ia_orden WHERE symbol = 'A'").fetchone()
        assert fila["estado"] == "RECHAZADA" and fila["motivo"] == ABOVE_MAX_ENTRY

    def test_efectivo_insuficiente_rechaza(self, tmp_path: Any) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        # Otra posición ya abierta consume casi todo el efectivo, pero la equity por coste (lo que
        # usa el tamaño) sigue contando su valor de entrada: la orden de "A" se dimensiona sobre una
        # equity de 10.000, pero solo quedan 50 EUR reales de caja.
        cartera_ia.abrir_posicion(
            symbol="B", market="NYSE", currency="EUR", units=99.5, entry_price=100.0, entry_price_eur=100.0,
            entry_session=date(2026, 11, 2), decision_apertura_id=None, stop=90.0, invalidation_level=90.0,
            entry_max=105.0, target1=110.0, target2=115.0, rr_minimo=1.5, instante=T_ACTIVACION,
        )
        assert cartera_ia.cash_eur() == pytest.approx(50.0)
        _crear_decision_y_orden(cartera_ia, reg)
        proveedor = _proveedor_ohlc({"A": {SESION_OBJETIVO: (100.0, 95.0, 102.0)}})

        resultado = procesar_pendientes(cartera_ia, proveedor, T_ACTIVACION + timedelta(days=5), 0, [])

        assert resultado.rechazadas == ["A"]
        assert cartera_ia.cash_eur() == pytest.approx(50.0)
        fila = reg.conn.execute("SELECT motivo FROM ia_orden WHERE symbol = 'A'").fetchone()
        assert fila["motivo"] == "CASH_INSUFICIENTE"

    def test_sin_tipo_de_cambio_sigue_pendiente_no_se_rechaza(self, tmp_path: Any) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _crear_decision_y_orden(cartera_ia, reg, currency="USD")
        proveedor = _proveedor_ohlc({"A": {SESION_OBJETIVO: (100.0, 95.0, 102.0)}})

        resultado = procesar_pendientes(cartera_ia, proveedor, T_ACTIVACION + timedelta(days=5), 0, [])

        assert resultado.abiertas == [] and resultado.rechazadas == []
        assert len(cartera_ia.pendientes_entrada()) == 1  # sigue pendiente, no rechazada

    def test_no_resuelve_antes_de_que_la_apertura_sea_observable(self, tmp_path: Any) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _crear_decision_y_orden(cartera_ia, reg)
        proveedor = _proveedor_ohlc({"A": {SESION_OBJETIVO: (100.0, 95.0, 102.0)}})

        # Antes de que cierre la sesión objetivo (causalmente no observable todavía).
        resultado = procesar_pendientes(cartera_ia, proveedor, APERTURA, 0, [])

        assert resultado.abiertas == [] and resultado.rechazadas == []
        assert len(cartera_ia.pendientes_entrada()) == 1

    def test_no_se_puede_ejecutar_dos_veces_la_misma_orden(self, tmp_path: Any) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _crear_decision_y_orden(cartera_ia, reg)
        orden = cartera_ia.pendientes_entrada()[0]
        cartera_ia.ejecutar_entrada(
            orden, eff_native=100.0, eff_eur=100.0, units=5.0, fx_rate=1.0, fx_as_of=None, equity_before_eur=10_000.0,
            cash_before_eur=10_000.0, requested_units=5.0, requested_notional_eur=500.0, session=SESION_OBJETIVO,
        )
        with pytest.raises(OrdenYaResuelta):
            cartera_ia.ejecutar_entrada(
                orden, eff_native=100.0, eff_eur=100.0, units=5.0, fx_rate=1.0, fx_as_of=None,
                equity_before_eur=10_000.0, cash_before_eur=9_500.0, requested_units=5.0, requested_notional_eur=500.0,
                session=SESION_OBJETIVO,
            )
        assert len(cartera_ia.posiciones_abiertas()) == 1
        assert cartera_ia.cash_eur() == pytest.approx(9_500.0)
        assert cartera_ia.verificar_invariante_contable()


# --- recuperación cronológica: el punto que corrigió Codex ---------------------------


class TestRecuperacionCronologica:
    def test_una_compra_del_lunes_no_usa_el_efectivo_liberado_por_un_stop_del_miercoles(self, tmp_path: Any) -> None:
        """Si se barriera primero todos los stops y luego todas las entradas, esta compra usaría
        efectivo que en la realidad todavía no existía el lunes."""

        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 1_000.0)
        # Posición ya abierta que absorbe casi todo el efectivo, y que el stop cerrará el miércoles.
        cartera_ia.abrir_posicion(
            symbol="B", market="NYSE", currency="EUR", units=9.0, entry_price=100.0, entry_price_eur=100.0,
            entry_session=date(2026, 11, 2), decision_apertura_id=None, stop=90.0, invalidation_level=90.0,
            entry_max=105.0, target1=110.0, target2=115.0, rr_minimo=1.5, instante=T_ACTIVACION,
        )
        # Cash restante: 1.000 - 900 = 100 EUR. Una compra de A (lunes 2 nov) pediría por riesgo
        # 0,5%*equity_coste(1000)=5 EUR / (100-90)=10 -> 0,5 unidades = 50 EUR: cabe con 100 EUR.
        reg.conn.execute("INSERT INTO ia_paquete (input_hash, tipo, symbol, contenido) VALUES ('hA','COMPRA','A','{}')")
        pasada_id = reg.abrir_pasada(T_ACTIVACION, "activo", "sha")
        decision_id = reg.guardar_decision(
            clave="A|2026-11-02|2026-11-02|x", pasada_id=pasada_id, symbol="A", market="NYSE", tipo="COMPRA",
            signal_session="2026-11-01", target_session="2026-11-02", target_open="2026-11-02T14:30:00+00:00",
            decision_ts=T_ACTIVACION.isoformat(), input_hash="hA", cuantitativo="{}", votos="{}", predicados=None,
            resolucion="COMPRAR", motivo="APROBADA_POR_AMBOS", prioridad="ALTA", causa=None,
        )
        cartera_ia.materializar_decision_compra(
            decision_id=decision_id, symbol="A", market="NYSE", currency="EUR", target_session=date(2026, 11, 2),
            target_open=datetime(2026, 11, 2, 14, 30, tzinfo=timezone.utc), niveles=NIVELES, instante=T_ACTIVACION,
        )
        proveedor = _proveedor_ohlc({
            "A": {date(2026, 11, 2): (100.0, 95.0, 102.0)},
            # "B" rompe su stop (90) el miércoles 4 de noviembre.
            "B": {date(2026, 11, 4): (85.0, 80.0, 88.0)},
        })

        resultado = procesar_pendientes(cartera_ia, proveedor, T_ACTIVACION + timedelta(days=10), 0, [])

        assert resultado.abiertas == ["A"]
        assert resultado.cerradas_stop == {"B": date(2026, 11, 4)}
        posicion_a = next(p for p in cartera_ia.posiciones_abiertas() if p.symbol == "A")
        # Si hubiese usado el efectivo liberado el miércoles (900 EUR extra), el tamaño habría sido
        # mucho mayor: 0,5 unidades es justo lo que da una equity de 1.000, no de 1.900.
        assert posicion_a.units == pytest.approx(0.5)
        assert cartera_ia.verificar_invariante_contable()

    def test_una_posicion_abierta_hoy_tambien_verifica_su_stop_el_mismo_dia(self, tmp_path: Any) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _crear_decision_y_orden(cartera_ia, reg)
        # Abre a 100 (por encima del stop 90) pero el mínimo del propio día lo rompe.
        proveedor = _proveedor_ohlc({"A": {SESION_OBJETIVO: (100.0, 85.0, 102.0)}})

        resultado = procesar_pendientes(cartera_ia, proveedor, T_ACTIVACION + timedelta(days=5), 0, [])

        assert resultado.abiertas == ["A"]
        assert resultado.cerradas_stop == {"A": SESION_OBJETIVO}
        assert cartera_ia.posiciones_abiertas() == ()


# --- integración con la pasada: modo registro nunca produce órdenes -----------------


class TestIntegracionConLaPasada:
    def test_modo_registro_sin_cartera_ia_nunca_crea_una_orden(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        candidata = _analisis("A", score=72.0)
        cliente = ClienteFalso(por_defecto=compra_ok())

        resultado, reg = _pasada(tmp_path, monkeypatch, [candidata], cliente)  # sin cartera_ia

        assert resultado.compras == ["A"]
        # Ni siquiera existen las tablas de la cartera: nadie construyó un CarteraIA en modo registro.
        CarteraIA(reg.conn)  # crea el esquema (vacío) solo para poder consultarlo en la prueba
        assert reg.conn.execute("SELECT COUNT(*) FROM ia_orden").fetchone()[0] == 0

    def test_modo_activo_crea_la_orden_pendiente_y_marca_aplicada(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        candidata = _analisis("A", score=72.0)
        cliente = ClienteFalso(por_defecto=compra_ok())

        resultado, _reg2 = _pasada(
            tmp_path, monkeypatch, [candidata], cliente, cartera_ia=cartera_ia, registro_existente=reg,
            instante=T_DECISION,
        )

        assert resultado.compras == ["A"]
        pendientes = cartera_ia.pendientes_entrada()
        assert len(pendientes) == 1 and pendientes[0].symbol == "A"
        fila = next(d for d in reg.decisiones(resultado.pasada_id) if d["symbol"] == "A")
        assert fila["resolucion"] == "COMPRAR" and fila["aplicada"] == 1


# --- segunda ronda de Codex: el orden dentro de una misma fecha y tras recuperar una entrada -----


class TestOrdenDentroDeLaMismaFecha:
    def test_un_stop_intradia_no_financia_una_compra_de_la_misma_apertura(self, tmp_path: Any) -> None:
        """Lo que señaló Codex: un stop por mínimo intradía libera caja en algún momento POSTERIOR
        a la apertura, nunca disponible para una compra que se ejecuta en esa misma apertura."""

        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 1_000.0)
        cartera_ia.abrir_posicion(
            symbol="B", market="NYSE", currency="EUR", units=9.9, entry_price=100.0, entry_price_eur=100.0,
            entry_session=date(2026, 11, 2), decision_apertura_id=None, stop=90.0, invalidation_level=90.0,
            entry_max=105.0, target1=110.0, target2=115.0, rr_minimo=1.5, instante=T_ACTIVACION,
        )
        assert cartera_ia.cash_eur() == pytest.approx(10.0)
        _crear_decision_y_orden(cartera_ia, reg)  # objetivo: 2026-11-06, igual que el stop de B

        proveedor = _proveedor_ohlc({
            "A": {SESION_OBJETIVO: (100.0, 95.0, 102.0)},  # pediría 0,5 unidades = 50 EUR
            "B": {SESION_OBJETIVO: (85.0, 80.0, 88.0)},  # hueco bajo el stop: libera ~841,5 EUR
        })

        resultado = procesar_pendientes(cartera_ia, proveedor, T_ACTIVACION + timedelta(days=10), 0, [])

        # Si A hubiese visto la caja ya liberada por B, 50 EUR habrían cabido de sobra.
        assert resultado.rechazadas == ["A"]
        assert resultado.cerradas_stop == {"B": SESION_OBJETIVO}
        fila = reg.conn.execute("SELECT motivo, cash_before_eur FROM ia_orden WHERE symbol = 'A'").fetchone()
        assert fila["motivo"] == "CASH_INSUFICIENTE" and fila["cash_before_eur"] == pytest.approx(10.0)

    def test_una_entrada_recuperada_tambien_arrastra_sus_propios_stops_posteriores(self, tmp_path: Any) -> None:
        """Lo que señaló Codex: si la orden abre atrasada (recuperando varias sesiones de golpe),
        un stop suyo posterior que ya es observable no debe quedar para la pasada siguiente."""

        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        reg.conn.execute("INSERT INTO ia_paquete (input_hash, tipo, symbol, contenido) VALUES ('hA','COMPRA','A','{}')")
        pasada_id = reg.abrir_pasada(T_ACTIVACION, "activo", "sha")
        decision_id = reg.guardar_decision(
            clave="A|2026-11-01|2026-11-02|x", pasada_id=pasada_id, symbol="A", market="NYSE", tipo="COMPRA",
            signal_session="2026-11-01", target_session="2026-11-02", target_open="2026-11-02T14:30:00+00:00",
            decision_ts=T_ACTIVACION.isoformat(), input_hash="hA", cuantitativo="{}", votos="{}", predicados=None,
            resolucion="COMPRAR", motivo="APROBADA_POR_AMBOS", prioridad="ALTA", causa=None,
        )
        cartera_ia.materializar_decision_compra(
            decision_id=decision_id, symbol="A", market="NYSE", currency="EUR", target_session=date(2026, 11, 2),
            target_open=datetime(2026, 11, 2, 14, 30, tzinfo=timezone.utc), niveles=NIVELES, instante=T_ACTIVACION,
        )
        proveedor = _proveedor_ohlc({
            "A": {
                date(2026, 11, 2): (100.0, 95.0, 102.0),  # abre a salvo
                date(2026, 11, 4): (89.0, 80.0, 85.0),  # rompe el stop (90) dos sesiones después
            }
        })

        resultado = procesar_pendientes(cartera_ia, proveedor, T_ACTIVACION + timedelta(days=10), 0, [])

        assert resultado.abiertas == ["A"]
        assert resultado.cerradas_stop == {"A": date(2026, 11, 4)}
        assert cartera_ia.posiciones_abiertas() == ()

    def test_una_entry_pendiente_junto_a_una_posicion_ya_abierta_del_mismo_symbol_se_rechaza(self, tmp_path: Any) -> None:
        """No debería darse por el flujo normal (la elegibilidad ya excluye esto), pero si los
        datos llegan a ese estado de todos modos, no debe abortar el resto del lote."""

        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        cartera_ia.abrir_posicion(
            symbol="A", market="NYSE", currency="EUR", units=1.0, entry_price=100.0, entry_price_eur=100.0,
            entry_session=date(2026, 11, 2), decision_apertura_id=None, stop=90.0, invalidation_level=90.0,
            entry_max=105.0, target1=110.0, target2=115.0, rr_minimo=1.5, instante=T_ACTIVACION,
        )
        _crear_decision_y_orden(cartera_ia, reg)
        proveedor = _proveedor_ohlc({"A": {SESION_OBJETIVO: (100.0, 95.0, 102.0)}})

        resultado = procesar_pendientes(cartera_ia, proveedor, T_ACTIVACION + timedelta(days=5), 0, [])

        assert resultado.rechazadas == ["A"] and resultado.abiertas == []
        assert len(cartera_ia.posiciones_abiertas()) == 1  # sigue siendo la original, no una segunda
        fila = reg.conn.execute("SELECT motivo FROM ia_orden WHERE estado = 'RECHAZADA'").fetchone()
        assert fila["motivo"] == "YA_EN_CARTERA"


# --- migración real desde una base de la fase 1 (hallazgo bloqueante de Codex) -------------------


class TestMigracionDesdeFase1:
    def _base_fase_1(self, tmp_path: Any) -> Any:
        """Una base real de ``RegistroIA`` (con ``ia_decision``/``ia_paquete``/``ia_pasada`` ya
        creadas, como en producción) con las tablas de la cartera en el esquema exacto de la fase 1.
        """

        reg = registro(tmp_path)
        conn = reg.conn
        conn.executescript(_ESQUEMA_FASE_1)
        conn.execute(
            "INSERT INTO ia_cartera (id, estado, capital_inicial_eur, cash_eur, activated_at, updated_at) "
            "VALUES (1,'PAPER',10000,9500,'2026-11-03T08:00:00+00:00','x')"
        )
        conn.execute(
            "INSERT INTO ia_posicion (symbol, market, currency, estado, units, entry_price, entry_price_eur, "
            "entry_session, stop_verificado_hasta, decision_apertura_id, stop, invalidation_level, entry_max, "
            "target1, target2, rr_minimo, created_at, updated_at) VALUES ('A','NYSE','EUR','ABIERTA',5.0,100.0,"
            "100.0,'2026-11-03','2026-11-02',NULL,90.0,90.0,105.0,110.0,115.0,1.5,'x','x')"
        )
        pos_id = conn.execute("SELECT id FROM ia_posicion").fetchone()[0]
        conn.execute(
            "INSERT INTO ia_orden (position_id, decision_id, symbol, proposito, origen, estado, motivo, "
            "created_at) VALUES (?, NULL, 'A', 'ENTRY', 'DECISION_IA', 'EJECUTADA', NULL, 'x')", (pos_id,)
        )
        orden_id = conn.execute("SELECT id FROM ia_orden").fetchone()[0]
        conn.execute(
            "INSERT INTO ia_fill (order_id, symbol, lado, precio, precio_eur, units, importe_eur, session, "
            "created_at) VALUES (?, 'A', 'COMPRA', 100.0, 100.0, 5.0, 500.0, '2026-11-03', 'x')", (orden_id,)
        )
        conn.execute(
            "INSERT INTO ia_movimiento (tipo, importe_eur, referencia, detalle, created_at) "
            "VALUES ('APORTACION', 10000, NULL, 'x', 'x')"
        )
        conn.execute(
            "INSERT INTO ia_movimiento (tipo, importe_eur, referencia, detalle, created_at) "
            "VALUES ('COMPRA', -500, 'A', 'x', 'x')"
        )
        conn.commit()
        return reg

    def test_abre_una_base_de_fase_1_sin_perder_nada(self, tmp_path: Any) -> None:
        reg = self._base_fase_1(tmp_path)
        conn = reg.conn

        cartera_ia = CarteraIA(conn)

        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        posiciones = cartera_ia.posiciones_abiertas()
        assert len(posiciones) == 1 and posiciones[0].symbol == "A" and posiciones[0].units == 5.0
        orden = conn.execute("SELECT * FROM ia_orden WHERE symbol = 'A'").fetchone()
        assert orden["id"] == 1 and orden["estado"] == "EJECUTADA" and orden["market"] == "NYSE"
        fill = conn.execute("SELECT * FROM ia_fill WHERE order_id = 1").fetchone()
        assert fill["units"] == 5.0 and fill["comision_eur"] == 0.0 and fill["deslizamiento_eur"] == 0.0
        assert cartera_ia.verificar_invariante_contable()

    def test_reabrir_la_base_ya_migrada_es_idempotente(self, tmp_path: Any) -> None:
        reg = self._base_fase_1(tmp_path)
        conn = reg.conn
        CarteraIA(conn)

        cartera_otra_vez = CarteraIA(conn)  # como si se reabriera el proceso tras la migración

        assert len(cartera_otra_vez.posiciones_abiertas()) == 1
        assert conn.execute("SELECT COUNT(*) FROM ia_orden").fetchone()[0] == 1
        assert cartera_otra_vez.verificar_invariante_contable()

    def test_tras_migrar_se_puede_operar_con_normalidad(self, tmp_path: Any) -> None:
        """La migración deja la base lista para la fase 2, no solo legible: abrir una entrada nueva
        y comprobar el stop de la posición heredada deben funcionar igual que en una base nueva."""

        reg = self._base_fase_1(tmp_path)
        cartera_ia = CarteraIA(reg.conn)
        _crear_decision_y_orden(cartera_ia, reg, symbol="B")
        proveedor = _proveedor_ohlc({
            "A": {date(2026, 11, 4): (85.0, 80.0, 88.0)},  # rompe el stop de la posición heredada
            "B": {SESION_OBJETIVO: (100.0, 95.0, 102.0)},
        })

        resultado = procesar_pendientes(cartera_ia, proveedor, T_ACTIVACION + timedelta(days=10), 0, [])

        assert resultado.cerradas_stop == {"A": date(2026, 11, 4)}
        assert resultado.abiertas == ["B"]
        assert cartera_ia.verificar_invariante_contable()

    def test_reanuda_una_migracion_interrumpida_justo_tras_crear_la_tabla_de_respaldo(self, tmp_path: Any) -> None:
        """Hallazgo de Codex: una caída entre crear ``ia_orden_v1`` y borrar la ``ia_orden`` vieja no
        debe hacer fallar el siguiente arranque."""

        reg = self._base_fase_1(tmp_path)
        conn = reg.conn
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("CREATE TABLE ia_orden_v1 AS SELECT * FROM ia_orden")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()  # como si el proceso hubiera muerto justo aquí

        cartera_ia = CarteraIA(conn)  # el siguiente arranque

        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'ia_orden_v1'").fetchone() is None
        assert len(cartera_ia.posiciones_abiertas()) == 1
        assert cartera_ia.verificar_invariante_contable()

    def test_reanuda_una_migracion_interrumpida_justo_antes_de_borrar_el_respaldo(self, tmp_path: Any) -> None:
        """Hallazgo de Codex: una caída después de copiar los datos a la ``ia_orden`` nueva, pero
        antes de borrar ``ia_orden_v1``, no debe duplicar la fila al reintentarlo."""

        reg = self._base_fase_1(tmp_path)
        conn = reg.conn
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("CREATE TABLE ia_orden_v1 AS SELECT * FROM ia_orden")
        conn.execute("DROP TABLE ia_orden")
        from superbot.ia import cartera as cartera_mod

        conn.executescript(cartera_mod._ESQUEMA_CARTERA)
        conn.execute(
            "INSERT INTO ia_orden (id, decision_id, position_id, symbol, market, currency, proposito, origen, "
            "estado, motivo, created_at, resolved_at) "
            "SELECT v1.id, v1.decision_id, v1.position_id, v1.symbol, p.market, p.currency, v1.proposito, "
            "v1.origen, v1.estado, v1.motivo, v1.created_at, v1.created_at "
            "FROM ia_orden_v1 v1 JOIN ia_posicion p ON p.id = v1.position_id"
        )
        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()  # como si el proceso hubiera muerto justo aquí, con ia_orden_v1 todavía viva

        cartera_ia = CarteraIA(conn)  # el siguiente arranque: no debe duplicar la fila ya copiada

        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'ia_orden_v1'").fetchone() is None
        assert conn.execute("SELECT COUNT(*) FROM ia_orden").fetchone()[0] == 1
        assert len(cartera_ia.posiciones_abiertas()) == 1
        assert cartera_ia.verificar_invariante_contable()

    def test_un_conflicto_real_de_la_fase_1_detiene_la_migracion_sin_perder_filas(self, tmp_path: Any) -> None:
        """Hallazgo de Codex: dos órdenes antiguas podían compartir ``decision_id`` (el esquema de
        la fase 1 no lo impedía); el nuevo índice único sí lo impide. Un ``INSERT OR IGNORE`` habría
        descartado una de las dos en silencio y borrado igualmente el respaldo. Debe fallar ruidoso
        y conservar ``ia_orden_v1`` intacta, nunca perder la fila callado."""

        reg = self._base_fase_1(tmp_path)
        conn = reg.conn
        conn.execute("INSERT INTO ia_paquete (input_hash, tipo, symbol, contenido) VALUES ('hB','POSICION','B','{}')")
        pasada_id = reg.abrir_pasada(T_ACTIVACION, "activo", "sha")
        decision_id = reg.guardar_decision(
            clave="B|2026-11-02|2026-11-03|x", pasada_id=pasada_id, symbol="B", market="NYSE", tipo="POSICION",
            signal_session="2026-11-02", target_session="2026-11-03", target_open="2026-11-03T14:30:00+00:00",
            decision_ts=T_ACTIVACION.isoformat(), input_hash="hB", cuantitativo="{}", votos="{}", predicados=None,
            resolucion="VENDER", motivo="CAUSA_VERIFICADA", prioridad=None, causa="INVALIDACION_CRUZADA",
        )
        conn.execute(
            "INSERT INTO ia_posicion (symbol, market, currency, estado, units, entry_price, entry_price_eur, "
            "entry_session, stop_verificado_hasta, decision_apertura_id, stop, invalidation_level, entry_max, "
            "target1, target2, rr_minimo, created_at, updated_at) VALUES ('B','NYSE','EUR','CERRADA',1.0,100.0,"
            "100.0,'2026-11-03','2026-11-02',NULL,90.0,90.0,105.0,110.0,115.0,1.5,'x','x')"
        )
        pos_b = conn.execute("SELECT id FROM ia_posicion WHERE symbol = 'B'").fetchone()[0]
        # Dos EXIT_IA con el mismo decision_id: permitido en el esquema de la fase 1.
        conn.execute(
            "INSERT INTO ia_orden (position_id, decision_id, symbol, proposito, origen, estado, motivo, "
            "created_at) VALUES (?, ?, 'B', 'EXIT_IA', 'DECISION_IA', 'RECHAZADA', 'intento1', 'x')",
            (pos_b, decision_id),
        )
        conn.execute(
            "INSERT INTO ia_orden (position_id, decision_id, symbol, proposito, origen, estado, motivo, "
            "created_at) VALUES (?, ?, 'B', 'EXIT_IA', 'DECISION_IA', 'EJECUTADA', 'intento2', 'x')",
            (pos_b, decision_id),
        )
        conn.commit()
        filas_v1_antes = conn.execute("SELECT COUNT(*) FROM ia_orden").fetchone()[0]

        with pytest.raises(sqlite3.IntegrityError):
            CarteraIA(conn)

        # Nada se perdió: el respaldo sigue con todas sus filas, listo para resolverse a mano.
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'ia_orden_v1'").fetchone() is not None
        assert conn.execute("SELECT COUNT(*) FROM ia_orden_v1").fetchone()[0] == filas_v1_antes
        # La conexión (isolation_level=None, como siempre en RegistroIA/CarteraIA: sin BEGIN propio)
        # no queda a medio camino de una transacción, y el PRAGMA del `finally` sí surtió efecto.
        assert conn.in_transaction is False
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
