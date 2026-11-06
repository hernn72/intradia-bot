"""Cartera paper de Superbot IA (Entrega C): contabilidad, stop obligatorio y ciclo completo.

Fase 1 cerró el ciclo de vida de una posición ya abierta (contabilidad, cierre
y su stop mecánico, independiente de la IA). Fase 2 añadió la compra: una
decisión ``COMPRAR`` crea una orden ``ENTRY`` pendiente, que una pasada
posterior resuelve en la apertura de su sesión objetivo —nunca
retrospectivamente— con un gate de apertura (estilo D-78, sin importar el
motor antiguo) y un tamaño por riesgo. Fase 3 añade la venta de la IA
(``VENDER`` crea una orden ``EXIT_IA`` pendiente, ligada a la posición
concreta, resuelta igual de tarde), fija el orden de prioridad frente al
stop obligatorio, sustituye el tipo de cambio por uno fechado a la sesión
exacta del evento (nunca "el último disponible"), y cierra el hueco entre
decidir, crear la orden y marcar ``aplicada`` con una sola operación atómica
y reanudable (``materializar_decision_*``).

Todo vive en la misma base de ``RegistroIA`` (una sola fuente de verdad para
Superbot IA, sin mezclarla con la del Superbot técnico ni con la del asesor).
La cartera nace ``INACTIVA`` y solo pasa a ``PAPER`` con ``activar()``: nadie
la activa automáticamente, así que desplegar este código no activa nada.
"""

from __future__ import annotations

import json
import math
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import AbstractSet, Any, Dict, Iterator, List, Mapping, Optional, Sequence, Set, Tuple

from advisor.analysis.levels import reward_risk, rr_at_least
from advisor.data.market_data import MarketDataProvider
from advisor.data.sessions import session_close_at, session_date_of
from superbot.ia.datos import Analisis
from superbot.ia.paquete import EstadoCartera, PosicionIA
from superbot.ia.politica import CAUSAS

_ESQUEMA_CARTERA = """
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
CREATE UNIQUE INDEX IF NOT EXISTS ia_posicion_decision_apertura_unica
    ON ia_posicion (decision_apertura_id) WHERE decision_apertura_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS ia_orden (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id INTEGER REFERENCES ia_decision(id),
    position_id INTEGER REFERENCES ia_posicion(id),
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    currency TEXT NOT NULL,
    proposito TEXT NOT NULL CHECK (proposito IN ('ENTRY', 'EXIT_IA', 'STOP')),
    origen TEXT NOT NULL CHECK (origen IN ('DECISION_IA', 'STOP_OBLIGATORIO')),
    estado TEXT NOT NULL CHECK (estado IN ('PENDIENTE', 'EJECUTADA', 'RECHAZADA')),
    -- Para ENTRY/EXIT_IA: la sesión y apertura en que se resuelve (nunca retrospectivamente).
    target_session TEXT,
    target_open TEXT,
    -- Foto JSON de los niveles vigentes al decidir (stop, invalidation_level, entry_max, target1,
    -- target2, min_rr_ratio): el gate que resuelve la orden nunca recalcula con datos posteriores.
    -- Solo lo usa ENTRY; EXIT_IA no tiene gate, se vende al Open sin más condición que la posición
    -- seguir ABIERTA.
    niveles TEXT,
    equity_before_eur REAL,
    cash_before_eur REAL,
    fx_rate REAL,
    fx_as_of TEXT,
    requested_units REAL,
    requested_notional_eur REAL,
    motivo TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    -- Una orden ENTRY real siempre trae ``decision_id`` (lo exige el código que la crea, no este
    -- CHECK): la primitiva de más abajo (``abrir_posicion``) también la usa para sembrar posiciones
    -- en pruebas, sin una decisión real detrás.
    -- ENTRY pendiente todavía no tiene posición (position_id nulo); EXIT_IA pendiente SÍ está
    -- ligada a una posición concreta desde que se crea (position_id obligatorio desde el principio,
    -- nunca solo por símbolo: una posición nueva del mismo símbolo no debe heredar una salida vieja).
    CHECK (proposito <> 'ENTRY' OR estado <> 'PENDIENTE' OR position_id IS NULL),
    CHECK (proposito <> 'EXIT_IA' OR estado <> 'PENDIENTE' OR position_id IS NOT NULL),
    CHECK (proposito <> 'ENTRY' OR estado <> 'EJECUTADA' OR position_id IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS ia_orden_decision_unica ON ia_orden (decision_id, proposito) WHERE decision_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ia_orden_entry_pendiente_unica
    ON ia_orden (symbol) WHERE proposito = 'ENTRY' AND estado = 'PENDIENTE';
CREATE UNIQUE INDEX IF NOT EXISTS ia_orden_exit_pendiente_unica
    ON ia_orden (position_id) WHERE proposito = 'EXIT_IA' AND estado = 'PENDIENTE';
CREATE INDEX IF NOT EXISTS ia_orden_pendientes ON ia_orden (estado, target_open);
CREATE TABLE IF NOT EXISTS ia_fill (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL UNIQUE REFERENCES ia_orden(id),
    symbol TEXT NOT NULL,
    lado TEXT NOT NULL CHECK (lado IN ('COMPRA', 'VENTA')),
    precio REAL NOT NULL,
    precio_eur REAL NOT NULL,
    units REAL NOT NULL,
    importe_eur REAL NOT NULL,
    comision_eur REAL NOT NULL DEFAULT 0,
    deslizamiento_eur REAL NOT NULL DEFAULT 0,
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


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonico(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class PosicionAbierta:
    """Una fila de ``ia_posicion`` con ``estado = 'ABIERTA'``, para el motor de la pasada."""

    id: int
    symbol: str
    market: str
    currency: str
    units: float
    entry_price: float
    entry_price_eur: float
    entry_session: date
    stop_verificado_hasta: date
    decision_apertura_id: Optional[int]
    stop: float
    invalidation_level: Optional[float]
    entry_max: Optional[float]
    target1: Optional[float]
    target2: Optional[float]
    rr_minimo: Optional[float]


@dataclass(frozen=True)
class OrdenEntradaPendiente:
    """Una fila de ``ia_orden`` con ``proposito = 'ENTRY'`` y ``estado = 'PENDIENTE'``."""

    id: int
    decision_id: int
    symbol: str
    market: str
    currency: str
    target_session: date
    target_open: datetime
    niveles: Dict[str, Any]


@dataclass(frozen=True)
class OrdenSalidaPendiente:
    """Una fila de ``ia_orden`` con ``proposito = 'EXIT_IA'`` y ``estado = 'PENDIENTE'``.

    Ligada a ``position_id``, no solo al símbolo: una posición nueva del
    mismo símbolo, abierta después de que la original se cerrara, nunca
    debe heredar esta salida.
    """

    id: int
    decision_id: int
    position_id: int
    symbol: str
    market: str
    currency: str
    target_session: date
    target_open: datetime
    causa: Optional[str]


@dataclass(frozen=True)
class ResultadoStop:
    """Qué dice el gate mecánico del stop sobre la sesión de un ``Analisis``.

    ``verificable=False`` significa que el dato de apertura o de mínimo no
    sirve: nunca se declara a partir de ahí que el stop sobrevivió, así que el
    llamador debe tratarlo como una posición sin comprobar esa sesión, nunca
    como una posición a salvo.
    """

    verificable: bool
    disparado: bool
    precio_fill: Optional[float]
    motivo: str


DATOS_INCOMPLETOS = "DATOS_INCOMPLETOS"
GAP_BAJO_STOP = "GAP_BAJO_STOP"
STOP_TOCADO = "STOP_TOCADO"
NO_TOCADO = "NO_TOCADO"


def evaluar_stop(stop: float, open_native: float, low_native: float) -> ResultadoStop:
    """Regla de ejecución del stop sobre OHLC diario, antes de cualquier IA.

    Si la apertura ya está por debajo del stop, el hueco es adverso y se
    ejecuta ahí (no se puede fingir que se vendió al stop si el mercado abrió
    más bajo). Si no, pero el mínimo de la sesión tocó el stop, se ejecuta al
    propio stop.
    """

    if not (
        math.isfinite(stop) and stop > 0 and math.isfinite(open_native) and open_native > 0
        and math.isfinite(low_native) and low_native > 0
    ):
        return ResultadoStop(False, False, None, DATOS_INCOMPLETOS)
    if open_native <= stop:
        return ResultadoStop(True, True, open_native, GAP_BAJO_STOP)
    if low_native <= stop:
        return ResultadoStop(True, True, stop, STOP_TOCADO)
    return ResultadoStop(True, False, None, NO_TOCADO)


@dataclass(frozen=True)
class ResultadoGate:
    """Qué dice el gate de apertura (estilo D-78) sobre la apertura real de la sesión objetivo.

    ``eff`` es la propia apertura, nunca ``entry_max``: si el mercado abre
    por debajo del límite, se compra a ese precio mejor, no al límite.
    """

    aprobado: bool
    motivo: str
    eff: Optional[float]


DATA_NOT_EXECUTABLE = "DATA_NOT_EXECUTABLE"
INVALID_STOP = "INVALID_STOP"
INVALID_TARGET = "INVALID_TARGET"
ABOVE_MAX_ENTRY = "ABOVE_MAX_ENTRY"
RR_TOO_LOW = "RR_TOO_LOW"
ENTRY_OK = "ENTRY_OK"


def evaluar_gate_apertura(
    open_native: float, stop: float, target2: float, entry_max: float, min_rr_ratio: Optional[float],
) -> ResultadoGate:
    """Gate de apertura en el orden exacto de ``market_check`` (D-78, motor técnico antiguo): solo
    se toma el orden y los criterios ya revisados allí, sin importar ese módulo ni su base.
    """

    eff = open_native
    if not (math.isfinite(eff) and eff > 0):
        return ResultadoGate(False, DATA_NOT_EXECUTABLE, None)
    if not (math.isfinite(stop) and stop > 0) or stop >= eff:
        return ResultadoGate(False, INVALID_STOP, None)
    if not (math.isfinite(target2) and target2 > 0) or target2 <= eff:
        return ResultadoGate(False, INVALID_TARGET, None)
    if not (math.isfinite(entry_max) and entry_max > 0):
        return ResultadoGate(False, DATA_NOT_EXECUTABLE, None)
    if eff > entry_max and not math.isclose(eff, entry_max, rel_tol=1e-9, abs_tol=0.0):
        return ResultadoGate(False, ABOVE_MAX_ENTRY, None)
    if min_rr_ratio is not None and math.isfinite(min_rr_ratio):
        rr = reward_risk(eff, target2, stop)
        if rr is None or not rr_at_least(rr, min_rr_ratio):
            return ResultadoGate(False, RR_TOO_LOW, None)
    return ResultadoGate(True, ENTRY_OK, eff)


# Riesgo y tamaño máximo por operación, fijados por el propietario para la fase 2: no configurables
# por PoliticaIA (cambiar su forma rompería la congelación de ``RegistroIA._congelar`` sobre bases
# ya creadas, incluida la que vive en la Pi).
RIESGO_PCT_POR_OPERACION = 0.5
MAX_POSICION_PCT = 10.0


def calcular_tamano_entrada(equity_eur: float, eff_native: float, stop_native: float, fx_rate: float) -> Tuple[float, float]:
    """Unidades solicitadas: lo que sea menor entre el riesgo presupuestado y el límite por posición.

    Fraccionarias y sin redondear: el llamador decide si el efectivo alcanza
    antes de ejecutar nada; aquí nunca se recorta el tamaño en silencio.
    """

    riesgo_por_unidad_eur = (eff_native - stop_native) * fx_rate
    eff_eur = eff_native * fx_rate
    if not (
        math.isfinite(riesgo_por_unidad_eur) and riesgo_por_unidad_eur > 0 and math.isfinite(eff_eur) and eff_eur > 0
    ):
        return 0.0, 0.0
    unidades_por_riesgo = (RIESGO_PCT_POR_OPERACION / 100.0 * equity_eur) / riesgo_por_unidad_eur
    unidades_por_limite = (MAX_POSICION_PCT / 100.0 * equity_eur) / eff_eur
    unidades = min(unidades_por_riesgo, unidades_por_limite)
    return unidades, unidades * eff_eur


@dataclass(frozen=True)
class ResultadoFx:
    tasa: float
    as_of: str


def fx_en_sesion(
    proveedor: MarketDataProvider, currency: str, session: date, base_currency: str = "EUR",
) -> Optional[ResultadoFx]:
    """Tipo de cambio de la sesión EXACTA, nunca "el último disponible".

    ``FxConverter`` (el conversor de presentación del asesor) siempre da el
    cierre más reciente: correcto para un informe que se lee al momento,
    pero no para resolver, días después, una orden fechada a una sesión
    concreta — un reintento tardío usaría una tasa de un día distinto al del
    propio evento económico. Aquí se pide la barra de ESA sesión y solo esa;
    si no está (festivo del par, hueco del proveedor), se devuelve ``None``
    y la orden sigue pendiente: nunca se retrocede al cierre anterior.
    """

    ccy = currency.strip().upper()
    base = base_currency.strip().upper()
    if ccy == base:
        return ResultadoFx(1.0, session.isoformat())
    par = f"{base}{ccy}=X"
    try:
        # Rango exacto, igual que el reintento del contexto Asia (fase B): pide solo esa sesión.
        bruto = proveedor.get_raw_history(par, start=session.isoformat(), end=(session + timedelta(days=1)).isoformat())
    except Exception:
        return None
    if bruto is None or bruto.empty or "Close" not in bruto:
        return None
    # Nunca se confía en que el proveedor respetó start/end al pie de la letra (hallazgo de Codex):
    # un par que no declare una plaza no tiene ``session_date_of`` para fecharlo, así que se exige
    # aquí mismo que exista una barra de ESA fecha exacta, nunca "la última servida".
    de_la_sesion = bruto[[ts.date() == session for ts in bruto.index]]
    if de_la_sesion.empty:
        return None
    try:
        cierre = float(de_la_sesion["Close"].iloc[-1])
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(cierre) and cierre > 0):
        return None
    # EURUSD=X cotiza USD por 1 EUR; para tener EUR por 1 USD hay que invertir.
    return ResultadoFx(1.0 / cierre, session.isoformat())


class CarteraPoliticaDistinta(RuntimeError):
    """La cartera ya existe con otro estado o capital: no se reactiva por encima."""


class CarteraInactiva(RuntimeError):
    """No se puede abrir una posición sin una cartera ``PAPER`` activa."""


class PosicionYaCerrada(RuntimeError):
    """La posición ya no estaba ``ABIERTA``: no se liquida dos veces."""


class OrdenYaResuelta(RuntimeError):
    """La orden ya no estaba ``PENDIENTE``: no se ejecuta ni se rechaza dos veces."""


class EfectivoInsuficiente(RuntimeError):
    """La mutación de caja detectó que no había efectivo suficiente, aunque la comprobación previa
    del lote dijera que sí: defensa en la propia escritura, no solo en la lectura de antes."""


class CarteraIA:
    """Estado persistido de la cartera paper, sobre la misma conexión que ``RegistroIA``."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        if self._orden_antigua_pendiente_de_migrar():
            try:
                self.conn.execute("PRAGMA foreign_keys = OFF")
                self._renombrar_orden_antigua()
                self.conn.executescript(_ESQUEMA_CARTERA)
                self._migrar_datos_orden_antigua()
            finally:
                self.conn.execute("PRAGMA foreign_keys = ON")
        else:
            self.conn.executescript(_ESQUEMA_CARTERA)
        self._migrar_columnas_fill()

    # Marca literal del CHECK ya relajado (fase 3): si el texto de ``ia_orden`` no la contiene,
    # el CHECK sigue siendo el estricto de la fase 2 (``PENDIENTE`` exigía ``position_id IS NULL``
    # sin distinguir ``ENTRY`` de ``EXIT_IA``).
    _MARCA_CHECK_FASE_3 = "proposito <> 'ENTRY' OR estado <> 'PENDIENTE'"

    def _orden_antigua_pendiente_de_migrar(self) -> bool:
        """Si queda cualquier rastro de una migración sin terminar (``ia_orden_v1`` todavía viva), o
        la ``ia_orden`` actual es la de la fase 1 (sin ``target_open``) o la de la fase 2 (con
        ``target_open`` pero el CHECK todavía estricto, que impediría una ``EXIT_IA`` pendiente),
        hay trabajo de migración pendiente. Cada paso de abajo es, a su vez, idempotente: puede
        repetirse sobre un intento interrumpido en cualquiera de sus puntos sin duplicar ni perder
        nada.
        """

        if self.conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'ia_orden_v1'").fetchone():
            return True
        fila = self.conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'ia_orden'").fetchone()
        if fila is None:
            return False
        columnas = {f[1] for f in self.conn.execute("PRAGMA table_info(ia_orden)")}
        if "target_open" not in columnas:
            return True  # fase 1
        return self._MARCA_CHECK_FASE_3 not in fila[0]  # fase 2, CHECK todavía estricto

    def _renombrar_orden_antigua(self) -> None:
        """``CREATE TABLE IF NOT EXISTS`` no toca una ``ia_orden`` ya existente con un esquema más
        antiguo (fase 1: ``position_id NOT NULL``, sin las columnas nuevas; fase 2: ya con esas
        columnas, pero un CHECK que exige ``position_id IS NULL`` para CUALQUIER ``PENDIENTE``, lo
        que impediría una ``EXIT_IA`` pendiente). SQLite no permite relajar un ``CHECK`` ni una
        columna ``NOT NULL`` con ``ALTER TABLE``, así que hay que reconstruirla.

        Se copia a una tabla aparte y se borra la original (con ``foreign_keys`` ya en ``OFF``,
        puesto por el llamador): ``ALTER TABLE ... RENAME`` reescribiría el
        ``REFERENCES ia_orden(id)`` de ``ia_fill`` para que apuntara a esa tabla aparte, dejándolo
        colgado al borrarla después. Cada paso comprueba si ya se hizo, para poder reanudar un
        intento interrumpido justo donde se quedó.
        """

        existe_v1 = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'ia_orden_v1'"
        ).fetchone()
        if existe_v1 is None:
            existe_vieja = self.conn.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'ia_orden'"
            ).fetchone()
            if existe_vieja is None:
                return  # ya se migró del todo en un intento anterior; solo falta recrear el esquema
            columnas = {fila[1] for fila in self.conn.execute("PRAGMA table_info(ia_orden)")}
            if "target_open" in columnas and self._MARCA_CHECK_FASE_3 in existe_vieja[0]:
                return  # ya es la tabla de la fase 3: nada que renombrar
            self.conn.execute("CREATE TABLE ia_orden_v1 AS SELECT * FROM ia_orden")
        existe_vieja = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'ia_orden'"
        ).fetchone()
        if existe_vieja is not None and (
            "target_open" not in existe_vieja[0] or self._MARCA_CHECK_FASE_3 not in existe_vieja[0]
        ):
            self.conn.execute("DROP TABLE ia_orden")

    def _migrar_datos_orden_antigua(self) -> None:
        existe_v1 = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'ia_orden_v1'"
        ).fetchone()
        if existe_v1 is None:
            return
        columnas_v1 = {f[1] for f in self.conn.execute("PRAGMA table_info(ia_orden_v1)")}
        # El filtro ``NOT EXISTS`` —no ``INSERT OR IGNORE``— es lo que hace la copia reanudable sin
        # esconder nada: una fila con el mismo ``id`` que ya se copió en un intento anterior se
        # salta sin más, pero cualquier OTRO conflicto (p. ej. dos órdenes con la misma
        # ``(decision_id, proposito)``, que un esquema más antiguo permitía y el índice único ya
        # no) hace fallar el INSERT entero: ``ia_orden_v1`` queda intacta en vez de perder una fila
        # en silencio.
        if "market" in columnas_v1:
            # De la fase 2 a la fase 3: mismas columnas, solo cambia el CHECK; copia directa.
            self.conn.execute(
                "INSERT INTO ia_orden (id, decision_id, position_id, symbol, market, currency, proposito, "
                "origen, estado, target_session, target_open, niveles, equity_before_eur, cash_before_eur, "
                "fx_rate, fx_as_of, requested_units, requested_notional_eur, motivo, created_at, resolved_at) "
                "SELECT id, decision_id, position_id, symbol, market, currency, proposito, origen, estado, "
                "target_session, target_open, niveles, equity_before_eur, cash_before_eur, fx_rate, fx_as_of, "
                "requested_units, requested_notional_eur, motivo, created_at, resolved_at "
                "FROM ia_orden_v1 WHERE NOT EXISTS (SELECT 1 FROM ia_orden existente WHERE existente.id = ia_orden_v1.id)"
            )
            self.conn.execute("DROP TABLE ia_orden_v1")
            return
        # De la fase 1 a la fase 3: ``market``/``currency`` no existían; se recuperan de la
        # posición que la orden abrió o cerró (siempre tenía ``position_id``, nunca nulo en ese
        # esquema). Conserva el ``id`` original: ``ia_fill.order_id`` ya apunta a él.
        self.conn.execute(
            "INSERT INTO ia_orden (id, decision_id, position_id, symbol, market, currency, proposito, "
            "origen, estado, motivo, created_at, resolved_at) "
            "SELECT v1.id, v1.decision_id, v1.position_id, v1.symbol, p.market, p.currency, v1.proposito, "
            "v1.origen, v1.estado, v1.motivo, v1.created_at, v1.created_at "
            "FROM ia_orden_v1 v1 JOIN ia_posicion p ON p.id = v1.position_id "
            "WHERE NOT EXISTS (SELECT 1 FROM ia_orden existente WHERE existente.id = v1.id)"
        )
        self.conn.execute("DROP TABLE ia_orden_v1")

    def _migrar_columnas_fill(self) -> None:
        columnas = {fila[1] for fila in self.conn.execute("PRAGMA table_info(ia_fill)")}
        if "comision_eur" not in columnas:
            self.conn.execute("ALTER TABLE ia_fill ADD COLUMN comision_eur REAL NOT NULL DEFAULT 0")
        if "deslizamiento_eur" not in columnas:
            self.conn.execute("ALTER TABLE ia_fill ADD COLUMN deslizamiento_eur REAL NOT NULL DEFAULT 0")

    @contextmanager
    def _transaccion(self) -> Iterator[sqlite3.Connection]:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")

    def _evento(self, conn: sqlite3.Connection, tipo: str, symbol: Optional[str], payload: Mapping[str, Any]) -> None:
        conn.execute(
            "INSERT INTO ia_evento (tipo, symbol, payload, created_at) VALUES (?, ?, ?, ?)",
            (tipo, symbol, _canonico(payload), _ahora_iso()),
        )

    # --- activación --------------------------------------------------------

    def activa(self) -> bool:
        fila = self.conn.execute("SELECT estado FROM ia_cartera WHERE id = 1").fetchone()
        return fila is not None and fila[0] == "PAPER"

    def activar(self, instante: datetime, capital_inicial_eur: float) -> bool:
        """Pasa la cartera a ``PAPER`` con el capital dado. Idempotente: no reactiva una ya activa.

        Nadie llama a esto automáticamente: una cartera nace ``INACTIVA`` y
        solo un llamador explícito (nunca el desplegado por defecto) decide
        activarla, conforme a que la Entrega C no se activa en producción
        todavía.
        """

        with self._transaccion() as conn:
            fila = conn.execute("SELECT estado, capital_inicial_eur FROM ia_cartera WHERE id = 1").fetchone()
            if fila is not None:
                if fila[0] == "PAPER":
                    return False
                raise CarteraPoliticaDistinta(f"id=1 existe en estado {fila[0]!r}: no se reactiva con otro capital")
            conn.execute(
                "INSERT INTO ia_cartera (id, estado, capital_inicial_eur, cash_eur, activated_at, updated_at) "
                "VALUES (1, 'PAPER', ?, ?, ?, ?)",
                (capital_inicial_eur, capital_inicial_eur, instante.isoformat(), _ahora_iso()),
            )
            conn.execute(
                "INSERT INTO ia_movimiento (tipo, importe_eur, referencia, detalle, created_at) "
                "VALUES ('APORTACION', ?, NULL, 'activación de la cartera paper', ?)",
                (capital_inicial_eur, _ahora_iso()),
            )
            self._evento(conn, "CARTERA_ACTIVADA", None, {"capital_inicial_eur": capital_inicial_eur})
        return True

    def cash_eur(self) -> float:
        fila = self.conn.execute("SELECT cash_eur FROM ia_cartera WHERE id = 1").fetchone()
        return float(fila[0]) if fila is not None else 0.0

    # --- posiciones ----------------------------------------------------------

    def posiciones_abiertas(self) -> Tuple[PosicionAbierta, ...]:
        filas = self.conn.execute("SELECT * FROM ia_posicion WHERE estado = 'ABIERTA' ORDER BY id").fetchall()
        return tuple(
            PosicionAbierta(
                id=f["id"], symbol=f["symbol"], market=f["market"], currency=f["currency"], units=f["units"],
                entry_price=f["entry_price"], entry_price_eur=f["entry_price_eur"],
                entry_session=date.fromisoformat(f["entry_session"]),
                stop_verificado_hasta=date.fromisoformat(f["stop_verificado_hasta"]),
                decision_apertura_id=f["decision_apertura_id"],
                stop=f["stop"], invalidation_level=f["invalidation_level"], entry_max=f["entry_max"],
                target1=f["target1"], target2=f["target2"], rr_minimo=f["rr_minimo"],
            )
            for f in filas
        )

    def abrir_posicion(
        self, *, symbol: str, market: str, currency: str, units: float, entry_price: float, entry_price_eur: float,
        entry_session: date, decision_apertura_id: Optional[int], stop: float, invalidation_level: Optional[float],
        entry_max: Optional[float], target1: Optional[float], target2: Optional[float], rr_minimo: Optional[float],
        instante: datetime,
    ) -> int:
        """Abre la posición, descuenta el efectivo y lo registra, en una sola transacción.

        Primitiva común para cualquier apertura futura (hoy no hay ninguna
        decisión ``COMPRAR`` que la invoque: eso llega con el gate de
        apertura de la fase 2). Exige una cartera ``PAPER`` activa: nunca se
        abre una posición -y su movimiento de caja- sin una cartera real
        detrás, aunque quien llame se equivoque de orden.
        """

        for nombre, valor in (("units", units), ("entry_price", entry_price), ("entry_price_eur", entry_price_eur), ("stop", stop)):
            if not (math.isfinite(valor) and valor > 0):
                raise ValueError(f"{nombre} debe ser un número finito y positivo, no {valor!r}")

        importe_eur = units * entry_price_eur
        with self._transaccion() as conn:
            if not self.activa():
                raise CarteraInactiva("no se abre una posición sin una cartera PAPER activa")
            cursor = conn.execute(
                "INSERT INTO ia_posicion (symbol, market, currency, estado, units, entry_price, entry_price_eur, "
                "entry_session, stop_verificado_hasta, decision_apertura_id, stop, invalidation_level, entry_max, "
                "target1, target2, rr_minimo, created_at, updated_at) "
                "VALUES (?, ?, ?, 'ABIERTA', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    symbol, market, currency, units, entry_price, entry_price_eur, entry_session.isoformat(),
                    # Un día calendario antes de la entrada, nunca una sesión real: solo marca el
                    # límite para que la propia sesión de entrada SÍ quede sujeta a verificar su
                    # stop (un mínimo intradía adverso el mismo día que se abre también cuenta).
                    (entry_session - timedelta(days=1)).isoformat(), decision_apertura_id, stop, invalidation_level,
                    entry_max, target1,
                    target2, rr_minimo, _ahora_iso(), _ahora_iso(),
                ),
            )
            posicion_id = int(cursor.lastrowid or 0)
            orden = conn.execute(
                "INSERT INTO ia_orden (position_id, decision_id, symbol, market, currency, proposito, origen, "
                "estado, motivo, created_at, resolved_at) "
                "VALUES (?, ?, ?, ?, ?, 'ENTRY', 'DECISION_IA', 'EJECUTADA', NULL, ?, ?)",
                (posicion_id, decision_apertura_id, symbol, market, currency, _ahora_iso(), _ahora_iso()),
            )
            conn.execute(
                "INSERT INTO ia_fill (order_id, symbol, lado, precio, precio_eur, units, importe_eur, session, "
                "created_at) VALUES (?, ?, 'COMPRA', ?, ?, ?, ?, ?, ?)",
                (orden.lastrowid, symbol, entry_price, entry_price_eur, units, importe_eur, entry_session.isoformat(), _ahora_iso()),
            )
            conn.execute("UPDATE ia_cartera SET cash_eur = cash_eur - ?, updated_at = ? WHERE id = 1", (importe_eur, _ahora_iso()))
            conn.execute(
                "INSERT INTO ia_movimiento (tipo, importe_eur, referencia, detalle, created_at) "
                "VALUES ('COMPRA', ?, ?, ?, ?)",
                (-importe_eur, symbol, f"apertura {units} a {entry_price_eur} EUR", _ahora_iso()),
            )
            self._evento(conn, "POSICION_ABIERTA", symbol, {"position_id": posicion_id, "units": units, "entry_price_eur": entry_price_eur})
        return posicion_id

    def cerrar_posicion(
        self, posicion: PosicionAbierta, *, exit_price: float, exit_price_eur: float, exit_session: date,
        origen: str, motivo: str, decision_id: Optional[int] = None, fx_rate: Optional[float] = None,
        fx_as_of: Optional[str] = None,
    ) -> None:
        """Cierra la posición y crea su PROPIA orden nueva (nunca reclama una ya existente): válido
        para el stop obligatorio (nunca hay una orden pendiente que reclamar, no pasa por la fase de
        decisión) y como primitiva de pruebas. Una salida YA DECIDIDA por la IA, con su orden
        ``EXIT_IA`` pendiente desde que se decidió, usa ``ejecutar_salida_ia`` en su lugar: crear
        aquí una segunda orden chocaría con el índice único de la decisión.

        Una ``PosicionAbierta`` es una foto: si ya se cerró entre medias (otra
        llamada, un reintento, una referencia obsoleta), liquidar de nuevo
        duplicaría la venta. Por eso el cierre en ``ia_posicion`` exige
        ``estado = 'ABIERTA'`` y se aborta si no afecta a ninguna fila, antes
        de tocar caja, orden o fill.
        """

        for nombre, valor in (("exit_price", exit_price), ("exit_price_eur", exit_price_eur)):
            if not (math.isfinite(valor) and valor > 0):
                raise ValueError(f"{nombre} debe ser un número finito y positivo, no {valor!r}")

        importe_eur = posicion.units * exit_price_eur
        pnl_eur = importe_eur - posicion.units * posicion.entry_price_eur
        with self._transaccion() as conn:
            cerrada = conn.execute(
                "UPDATE ia_posicion SET estado = 'CERRADA', exit_price = ?, exit_price_eur = ?, exit_session = ?, "
                "motivo_cierre = ?, pnl_eur = ?, updated_at = ? WHERE id = ? AND estado = 'ABIERTA'",
                (exit_price, exit_price_eur, exit_session.isoformat(), motivo, pnl_eur, _ahora_iso(), posicion.id),
            )
            if cerrada.rowcount == 0:
                raise PosicionYaCerrada(f"la posición {posicion.id} ({posicion.symbol}) ya no estaba ABIERTA")
            orden = conn.execute(
                "INSERT INTO ia_orden (position_id, decision_id, symbol, market, currency, proposito, origen, "
                "estado, fx_rate, fx_as_of, motivo, created_at, resolved_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'EJECUTADA', ?, ?, ?, ?, ?)",
                (
                    posicion.id, decision_id, posicion.symbol, posicion.market, posicion.currency,
                    "STOP" if origen == "STOP_OBLIGATORIO" else "EXIT_IA", origen, fx_rate, fx_as_of, motivo,
                    _ahora_iso(), _ahora_iso(),
                ),
            )
            conn.execute(
                "INSERT INTO ia_fill (order_id, symbol, lado, precio, precio_eur, units, importe_eur, session, "
                "created_at) VALUES (?, ?, 'VENTA', ?, ?, ?, ?, ?, ?)",
                (orden.lastrowid, posicion.symbol, exit_price, exit_price_eur, posicion.units, importe_eur, exit_session.isoformat(), _ahora_iso()),
            )
            conn.execute("UPDATE ia_cartera SET cash_eur = cash_eur + ?, updated_at = ? WHERE id = 1", (importe_eur, _ahora_iso()))
            conn.execute(
                "INSERT INTO ia_movimiento (tipo, importe_eur, referencia, detalle, created_at) "
                "VALUES ('VENTA', ?, ?, ?, ?)",
                (importe_eur, posicion.symbol, f"cierre ({motivo}) {posicion.units} a {exit_price_eur} EUR", _ahora_iso()),
            )
            if origen == "STOP_OBLIGATORIO":
                self._evento(conn, "STOP_ACTIVADO", posicion.symbol, {"position_id": posicion.id, "precio_eur": exit_price_eur, "motivo": motivo})
            self._evento(conn, "POSICION_CERRADA", posicion.symbol, {"position_id": posicion.id, "pnl_eur": pnl_eur, "origen": origen})

    # --- órdenes de entrada pendientes (fase 2) ---------------------------------

    def materializar_decision_compra(
        self, *, decision_id: int, symbol: str, market: str, currency: str, target_session: date,
        target_open: datetime, niveles: Mapping[str, Any], instante: datetime,
    ) -> None:
        """Convierte una decisión ``COMPRAR`` en su efecto durable, marcando ``aplicada`` en la
        MISMA transacción: crea la orden ``ENTRY`` pendiente, o — si el símbolo ya tenía otra
        pendiente de una decisión distinta — un rechazo terminal explícito, nunca una decisión sin
        ningún rastro que un barrido posterior pudiera reintentar con una orden ya desaparecida (y
        por tanto obsoleta) días después.

        Reanudable: vuelve a comprobar el estado real antes de actuar, así que vale igual la
        primera vez, repetida sin cambios, o retomada tras una caída a mitad (entre crear la orden
        y marcar ``aplicada``, o incluso antes de haber creado nada).
        """

        with self._transaccion() as conn:
            decision = conn.execute(
                "SELECT aplicada, resolucion, tipo, symbol FROM ia_decision WHERE id = ? AND pasada_id IN "
                "(SELECT id FROM ia_pasada WHERE modo = 'activo')", (decision_id,)
            ).fetchone()
            if decision is None:
                return  # no es una decisión de una pasada activa (o no existe): nunca se materializa
            if decision["resolucion"] != "COMPRAR" or decision["tipo"] != "COMPRA" or decision["symbol"] != symbol:
                raise ValueError(
                    f"decisión {decision_id} no es una COMPRAR de {symbol}: resolucion="
                    f"{decision['resolucion']!r} tipo={decision['tipo']!r} symbol={decision['symbol']!r}"
                )
            existente = conn.execute(
                "SELECT 1 FROM ia_orden WHERE decision_id = ? AND proposito = 'ENTRY'", (decision_id,)
            ).fetchone()
            if existente is None:
                conflicto = conn.execute(
                    "SELECT 1 FROM ia_orden WHERE symbol = ? AND proposito = 'ENTRY' AND estado = 'PENDIENTE'",
                    (symbol,),
                ).fetchone()
                if conflicto is not None:
                    conn.execute(
                        "INSERT INTO ia_orden (decision_id, symbol, market, currency, proposito, origen, estado, "
                        "target_session, target_open, niveles, motivo, created_at, resolved_at) "
                        "VALUES (?, ?, ?, ?, 'ENTRY', 'DECISION_IA', 'RECHAZADA', ?, ?, ?, "
                        "'ENTRY_PENDIENTE_PREEXISTENTE', ?, ?)",
                        (
                            decision_id, symbol, market, currency, target_session.isoformat(),
                            target_open.isoformat(), _canonico(dict(niveles)), _ahora_iso(), _ahora_iso(),
                        ),
                    )
                    self._evento(conn, "ORDEN_ENTRADA_BLOQUEADA", symbol, {"decision_id": decision_id})
                else:
                    conn.execute(
                        "INSERT INTO ia_orden (decision_id, symbol, market, currency, proposito, origen, estado, "
                        "target_session, target_open, niveles, created_at) "
                        "VALUES (?, ?, ?, ?, 'ENTRY', 'DECISION_IA', 'PENDIENTE', ?, ?, ?, ?)",
                        (
                            decision_id, symbol, market, currency, target_session.isoformat(),
                            target_open.isoformat(), _canonico(dict(niveles)), _ahora_iso(),
                        ),
                    )
            if decision["aplicada"] == 0:
                conn.execute(
                    "UPDATE ia_decision SET aplicada = 1 WHERE id = ? AND pasada_id IN "
                    "(SELECT id FROM ia_pasada WHERE modo = 'activo')", (decision_id,)
                )

    def materializar_decision_venta(
        self, *, decision_id: int, position_id: int, symbol: str, market: str, currency: str,
        target_session: date, target_open: datetime, causa: Optional[str], instante: datetime,
    ) -> None:
        """Lo mismo que ``materializar_decision_compra``, para una decisión ``VENDER``: crea la
        orden ``EXIT_IA`` pendiente ligada a ESA posición (``position_id``, no solo el símbolo), o
        un rechazo terminal si esa posición ya tenía otra ``EXIT_IA`` pendiente de otra decisión.

        Condición 3 del propietario: una venta IA solo con una causa autorizada y comprobada por
        código. Esta frontera lo exige explícitamente (hallazgo de Codex) — no basta con que la
        ruta normal (``comite.resolver_posicion``) ya la verifique, porque esta función también se
        llama desde el barrido de recuperación con lo persistido en ``cuantitativo``.
        """

        if causa not in CAUSAS:
            raise ValueError(f"causa {causa!r} no autorizada para una venta IA")
        with self._transaccion() as conn:
            decision = conn.execute(
                "SELECT aplicada, resolucion, tipo, symbol, causa FROM ia_decision WHERE id = ? AND pasada_id IN "
                "(SELECT id FROM ia_pasada WHERE modo = 'activo')", (decision_id,)
            ).fetchone()
            if decision is None:
                return
            if (
                decision["resolucion"] != "VENDER" or decision["tipo"] != "POSICION"
                or decision["symbol"] != symbol or decision["causa"] != causa
            ):
                raise ValueError(
                    f"decisión {decision_id} no es una VENDER de {symbol} con causa {causa!r}: resolucion="
                    f"{decision['resolucion']!r} tipo={decision['tipo']!r} symbol={decision['symbol']!r} "
                    f"causa={decision['causa']!r}"
                )
            existente = conn.execute(
                "SELECT 1 FROM ia_orden WHERE decision_id = ? AND proposito = 'EXIT_IA'", (decision_id,)
            ).fetchone()
            if existente is None:
                conflicto = conn.execute(
                    "SELECT 1 FROM ia_orden WHERE position_id = ? AND proposito = 'EXIT_IA' AND estado = 'PENDIENTE'",
                    (position_id,),
                ).fetchone()
                if conflicto is not None:
                    conn.execute(
                        "INSERT INTO ia_orden (decision_id, position_id, symbol, market, currency, proposito, "
                        "origen, estado, target_session, target_open, motivo, created_at, resolved_at) "
                        "VALUES (?, ?, ?, ?, ?, 'EXIT_IA', 'DECISION_IA', 'RECHAZADA', ?, ?, "
                        "'EXIT_PENDIENTE_PREEXISTENTE', ?, ?)",
                        (
                            decision_id, position_id, symbol, market, currency, target_session.isoformat(),
                            target_open.isoformat(), _ahora_iso(), _ahora_iso(),
                        ),
                    )
                    self._evento(conn, "ORDEN_SALIDA_BLOQUEADA", symbol, {"decision_id": decision_id})
                else:
                    conn.execute(
                        "INSERT INTO ia_orden (decision_id, position_id, symbol, market, currency, proposito, "
                        "origen, estado, target_session, target_open, motivo, created_at) "
                        "VALUES (?, ?, ?, ?, ?, 'EXIT_IA', 'DECISION_IA', 'PENDIENTE', ?, ?, ?, ?)",
                        (
                            decision_id, position_id, symbol, market, currency, target_session.isoformat(),
                            target_open.isoformat(), causa, _ahora_iso(),
                        ),
                    )
            if decision["aplicada"] == 0:
                conn.execute(
                    "UPDATE ia_decision SET aplicada = 1 WHERE id = ? AND pasada_id IN "
                    "(SELECT id FROM ia_pasada WHERE modo = 'activo')", (decision_id,)
                )

    def materializar_decision_sin_efecto(self, decision_id: int) -> None:
        """``DESCARTAR``/``MANTENER`` no crean ningún efecto durable: marcar ``aplicada`` es su
        único rastro. Misma defensa de modo activo que las otras dos materializaciones."""

        self.conn.execute(
            "UPDATE ia_decision SET aplicada = 1 WHERE id = ? AND pasada_id IN "
            "(SELECT id FROM ia_pasada WHERE modo = 'activo')", (decision_id,)
        )

    def recuperar_decisiones_sin_aplicar(self, instante: datetime, incidencias: List[str]) -> None:
        """Materializa cualquier decisión de una pasada ACTIVA anterior que quedó ``aplicada=0``,
        de la que sea (incluida esta misma pasada si algo falló entre registrar y materializar).

        Se llama SIEMPRE antes de ``procesar_pendientes``: una venta o compra antigua recuperada
        debe entrar en el procesador cronológico desde el principio, para que una fecha anterior
        (la suya) no quede detrás de otra que el cursor ya hubiera adelantado.
        """

        filas = self.conn.execute(
            "SELECT * FROM ia_decision WHERE aplicada = 0 "
            "AND pasada_id IN (SELECT id FROM ia_pasada WHERE modo = 'activo')"
        ).fetchall()
        for fila in filas:
            if fila["resolucion"] in ("DESCARTAR", "MANTENER"):
                self.materializar_decision_sin_efecto(fila["id"])
                continue
            try:
                datos = json.loads(fila["cuantitativo"]) if fila["cuantitativo"] else {}
            except (TypeError, ValueError):
                incidencias.append(f"{fila['symbol']}: decisión {fila['id']} con cuantitativo ilegible; sin aplicar")
                continue
            if fila["resolucion"] == "COMPRAR" and fila["tipo"] == "COMPRA":
                niveles, currency = datos.get("niveles"), datos.get("currency")
                if niveles is None or currency is None:
                    incidencias.append(f"{fila['symbol']}: decisión {fila['id']} COMPRAR sin niveles/currency; sin aplicar")
                    continue
                self.materializar_decision_compra(
                    decision_id=fila["id"], symbol=fila["symbol"], market=fila["market"], currency=currency,
                    target_session=date.fromisoformat(fila["target_session"]),
                    target_open=datetime.fromisoformat(fila["target_open"]), niveles=niveles, instante=instante,
                )
            elif fila["resolucion"] == "VENDER" and fila["tipo"] == "POSICION":
                position_id, currency = datos.get("position_id"), datos.get("currency")
                if position_id is None or currency is None:
                    incidencias.append(f"{fila['symbol']}: decisión {fila['id']} VENDER sin position_id/currency; sin aplicar")
                    continue
                self.materializar_decision_venta(
                    decision_id=fila["id"], position_id=position_id, symbol=fila["symbol"], market=fila["market"],
                    currency=currency, target_session=date.fromisoformat(fila["target_session"]),
                    target_open=datetime.fromisoformat(fila["target_open"]), causa=fila["causa"], instante=instante,
                )

    def pendientes_entrada(self) -> Tuple[OrdenEntradaPendiente, ...]:
        filas = self.conn.execute(
            "SELECT * FROM ia_orden WHERE proposito = 'ENTRY' AND estado = 'PENDIENTE' ORDER BY target_open, symbol"
        ).fetchall()
        return tuple(
            OrdenEntradaPendiente(
                id=f["id"], decision_id=f["decision_id"], symbol=f["symbol"], market=f["market"],
                currency=f["currency"], target_session=date.fromisoformat(f["target_session"]),
                target_open=datetime.fromisoformat(f["target_open"]), niveles=json.loads(f["niveles"]),
            )
            for f in filas
        )

    def rechazar_entrada(
        self, orden: OrdenEntradaPendiente, motivo: str, *, equity_before_eur: float, cash_before_eur: float,
        fx_rate: Optional[float] = None, fx_as_of: Optional[str] = None, requested_units: Optional[float] = None,
        requested_notional_eur: Optional[float] = None,
    ) -> bool:
        """Reclama la orden con ``WHERE estado = 'PENDIENTE'``: si no afecta a nada, ya se resolvió.

        Los campos de FX y tamaño son opcionales porque un rechazo por el gate (``ABOVE_MAX_ENTRY``,
        ``INVALID_STOP``...) ocurre antes de pedir el tipo de cambio o calcular el tamaño: en ese
        caso no hay nada que congelar. Cuando sí se llegó a calcular (``CASH_INSUFICIENTE``,
        ``TAMANO_NO_VALIDO``), el llamador los pasa para que el rechazo quede igual de auditable que
        una ejecución.
        """

        with self._transaccion() as conn:
            cursor = conn.execute(
                "UPDATE ia_orden SET estado = 'RECHAZADA', motivo = ?, equity_before_eur = ?, cash_before_eur = ?, "
                "fx_rate = ?, fx_as_of = ?, requested_units = ?, requested_notional_eur = ?, resolved_at = ? "
                "WHERE id = ? AND estado = 'PENDIENTE'",
                (
                    motivo, equity_before_eur, cash_before_eur, fx_rate, fx_as_of, requested_units,
                    requested_notional_eur, _ahora_iso(), orden.id,
                ),
            )
            reclamada = cursor.rowcount > 0
            if reclamada:
                self._evento(conn, "ORDEN_RECHAZADA", orden.symbol, {"orden_id": orden.id, "motivo": motivo})
        return reclamada

    def ejecutar_entrada(
        self, orden: OrdenEntradaPendiente, *, eff_native: float, eff_eur: float, units: float, fx_rate: float,
        fx_as_of: Optional[str], equity_before_eur: float, cash_before_eur: float, requested_units: float,
        requested_notional_eur: float, session: date,
    ) -> int:
        """Reclama la orden pendiente, abre la posición y liquida el efectivo, en una sola transacción."""

        for nombre, valor in (("units", units), ("eff_native", eff_native), ("eff_eur", eff_eur)):
            if not (math.isfinite(valor) and valor > 0):
                raise ValueError(f"{nombre} debe ser un número finito y positivo, no {valor!r}")

        importe_eur = units * eff_eur
        niveles = orden.niveles
        with self._transaccion() as conn:
            if not self.activa():
                raise CarteraInactiva("no se ejecuta una entrada sin una cartera PAPER activa")
            # Reclama la orden ANTES de crear nada: si ya no está PENDIENTE (otro intento, una
            # llamada repetida), no se inserta una segunda posición para la misma decisión.
            vigente = conn.execute("SELECT estado FROM ia_orden WHERE id = ?", (orden.id,)).fetchone()
            if vigente is None or vigente[0] != "PENDIENTE":
                raise OrdenYaResuelta(f"la orden {orden.id} ({orden.symbol}) ya no estaba PENDIENTE")
            cursor = conn.execute(
                "INSERT INTO ia_posicion (symbol, market, currency, estado, units, entry_price, entry_price_eur, "
                "entry_session, stop_verificado_hasta, decision_apertura_id, stop, invalidation_level, entry_max, "
                "target1, target2, rr_minimo, created_at, updated_at) "
                "VALUES (?, ?, ?, 'ABIERTA', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    orden.symbol, orden.market, orden.currency, units, eff_native, eff_eur, session.isoformat(),
                    (session - timedelta(days=1)).isoformat(), orden.decision_id, niveles["stop"],
                    niveles.get("invalidation_level"), niveles.get("entry_max"), niveles.get("target1"),
                    niveles.get("target2"), niveles.get("min_rr_ratio"), _ahora_iso(), _ahora_iso(),
                ),
            )
            posicion_id = int(cursor.lastrowid or 0)
            actualizada = conn.execute(
                "UPDATE ia_orden SET estado = 'EJECUTADA', position_id = ?, equity_before_eur = ?, "
                "cash_before_eur = ?, fx_rate = ?, fx_as_of = ?, requested_units = ?, requested_notional_eur = ?, "
                "resolved_at = ? WHERE id = ? AND estado = 'PENDIENTE'",
                (
                    posicion_id, equity_before_eur, cash_before_eur, fx_rate, fx_as_of, requested_units,
                    requested_notional_eur, _ahora_iso(), orden.id,
                ),
            )
            if actualizada.rowcount == 0:
                raise OrdenYaResuelta(f"la orden {orden.id} ({orden.symbol}) ya no estaba PENDIENTE")
            conn.execute(
                "INSERT INTO ia_fill (order_id, symbol, lado, precio, precio_eur, units, importe_eur, session, "
                "created_at) VALUES (?, ?, 'COMPRA', ?, ?, ?, ?, ?, ?)",
                (orden.id, orden.symbol, eff_native, eff_eur, units, importe_eur, session.isoformat(), _ahora_iso()),
            )
            # La invariante vive en la propia mutación, no solo en la comprobación previa del lote:
            # si otro camino hubiera dejado la caja por debajo de lo esperado, esto lo detiene aquí
            # en vez de dejarla en negativo.
            descuento = conn.execute(
                "UPDATE ia_cartera SET cash_eur = cash_eur - ?, updated_at = ? "
                "WHERE id = 1 AND cash_eur >= ? - 0.01",
                (importe_eur, _ahora_iso(), importe_eur),
            )
            if descuento.rowcount == 0:
                raise EfectivoInsuficiente(f"efectivo insuficiente para ejecutar la orden {orden.id} ({orden.symbol})")
            conn.execute(
                "INSERT INTO ia_movimiento (tipo, importe_eur, referencia, detalle, created_at) "
                "VALUES ('COMPRA', ?, ?, ?, ?)",
                (-importe_eur, orden.symbol, f"entrada {units} a {eff_eur} EUR (orden {orden.id})", _ahora_iso()),
            )
            self._evento(
                conn, "ORDEN_EJECUTADA", orden.symbol,
                {"orden_id": orden.id, "position_id": posicion_id, "units": units, "eff_eur": eff_eur},
            )
            self._evento(
                conn, "POSICION_ABIERTA", orden.symbol,
                {"position_id": posicion_id, "units": units, "entry_price_eur": eff_eur},
            )
        return posicion_id

    # --- órdenes de salida pendientes (fase 3: VENDER de la IA) -----------------

    def pendientes_salida(self) -> Tuple[OrdenSalidaPendiente, ...]:
        filas = self.conn.execute(
            "SELECT * FROM ia_orden WHERE proposito = 'EXIT_IA' AND estado = 'PENDIENTE' ORDER BY target_open, symbol"
        ).fetchall()
        return tuple(
            OrdenSalidaPendiente(
                id=f["id"], decision_id=f["decision_id"], position_id=f["position_id"], symbol=f["symbol"],
                market=f["market"], currency=f["currency"], target_session=date.fromisoformat(f["target_session"]),
                target_open=datetime.fromisoformat(f["target_open"]), causa=f["motivo"],
            )
            for f in filas
        )

    def rechazar_salida_ia(self, orden: OrdenSalidaPendiente, motivo: str) -> bool:
        """Reclama la orden con ``WHERE estado = 'PENDIENTE'``: si no afecta a nada, ya se resolvió."""

        with self._transaccion() as conn:
            cursor = conn.execute(
                "UPDATE ia_orden SET estado = 'RECHAZADA', motivo = ?, resolved_at = ? "
                "WHERE id = ? AND estado = 'PENDIENTE'",
                (motivo, _ahora_iso(), orden.id),
            )
            reclamada = cursor.rowcount > 0
            if reclamada:
                self._evento(conn, "ORDEN_RECHAZADA", orden.symbol, {"orden_id": orden.id, "motivo": motivo})
        return reclamada

    def ejecutar_salida_ia(
        self, orden: OrdenSalidaPendiente, *, exit_price: float, exit_price_eur: float, fx_rate: float,
        fx_as_of: Optional[str], session: date,
    ) -> None:
        """Reclama la orden ``EXIT_IA`` pendiente y cierra ESA posición concreta, en una sola
        transacción: nunca crea una orden nueva (ya existe desde que se decidió ``VENDER``), al
        contrario que ``cerrar_posicion`` (la del stop).

        Si la posición ya no está ``ABIERTA`` (el stop obligatorio la cerró antes, tiene prioridad:
        ver ``procesar_pendientes``), lanza ``PosicionYaCerrada`` SIN reclamar la orden: el llamador
        decide entonces rechazarla con un motivo explícito, nunca liquidar dos veces la misma venta.
        """

        for nombre, valor in (("exit_price", exit_price), ("exit_price_eur", exit_price_eur)):
            if not (math.isfinite(valor) and valor > 0):
                raise ValueError(f"{nombre} debe ser un número finito y positivo, no {valor!r}")

        with self._transaccion() as conn:
            vigente = conn.execute("SELECT estado FROM ia_orden WHERE id = ?", (orden.id,)).fetchone()
            if vigente is None or vigente[0] != "PENDIENTE":
                raise OrdenYaResuelta(f"la orden {orden.id} ({orden.symbol}) ya no estaba PENDIENTE")
            posicion = conn.execute(
                "SELECT * FROM ia_posicion WHERE id = ? AND estado = 'ABIERTA'", (orden.position_id,)
            ).fetchone()
            if posicion is None:
                raise PosicionYaCerrada(f"la posición {orden.position_id} ({orden.symbol}) ya no estaba ABIERTA")

            importe_eur = posicion["units"] * exit_price_eur
            pnl_eur = importe_eur - posicion["units"] * posicion["entry_price_eur"]
            conn.execute(
                "UPDATE ia_posicion SET estado = 'CERRADA', exit_price = ?, exit_price_eur = ?, exit_session = ?, "
                "motivo_cierre = ?, pnl_eur = ?, updated_at = ? WHERE id = ?",
                (exit_price, exit_price_eur, session.isoformat(), orden.causa, pnl_eur, _ahora_iso(), posicion["id"]),
            )
            actualizada = conn.execute(
                "UPDATE ia_orden SET estado = 'EJECUTADA', fx_rate = ?, fx_as_of = ?, resolved_at = ? "
                "WHERE id = ? AND estado = 'PENDIENTE'",
                (fx_rate, fx_as_of, _ahora_iso(), orden.id),
            )
            if actualizada.rowcount == 0:
                raise OrdenYaResuelta(f"la orden {orden.id} ({orden.symbol}) ya no estaba PENDIENTE")
            conn.execute(
                "INSERT INTO ia_fill (order_id, symbol, lado, precio, precio_eur, units, importe_eur, session, "
                "created_at) VALUES (?, ?, 'VENTA', ?, ?, ?, ?, ?, ?)",
                (orden.id, orden.symbol, exit_price, exit_price_eur, posicion["units"], importe_eur, session.isoformat(), _ahora_iso()),
            )
            conn.execute("UPDATE ia_cartera SET cash_eur = cash_eur + ?, updated_at = ? WHERE id = 1", (importe_eur, _ahora_iso()))
            conn.execute(
                "INSERT INTO ia_movimiento (tipo, importe_eur, referencia, detalle, created_at) "
                "VALUES ('VENTA', ?, ?, ?, ?)",
                (importe_eur, orden.symbol, f"salida IA ({orden.causa}) {posicion['units']} a {exit_price_eur} EUR", _ahora_iso()),
            )
            self._evento(
                conn, "ORDEN_EJECUTADA", orden.symbol,
                {"orden_id": orden.id, "position_id": posicion["id"], "pnl_eur": pnl_eur},
            )
            self._evento(
                conn, "POSICION_CERRADA", orden.symbol,
                {"position_id": posicion["id"], "pnl_eur": pnl_eur, "origen": "DECISION_IA", "causa": orden.causa},
            )

    # --- auditoría -------------------------------------------------------------

    def actualizar_stop_verificado(self, position_id: int, sesion: date) -> None:
        self.conn.execute(
            "UPDATE ia_posicion SET stop_verificado_hasta = ?, updated_at = ? WHERE id = ? AND estado = 'ABIERTA'",
            (sesion.isoformat(), _ahora_iso(), position_id),
        )

    def verificar_invariante_contable(self, tolerancia_eur: float = 0.01) -> bool:
        """``suma de movimientos == cash`` — la aportación inicial ya es el primer movimiento.

        Sin fila en ``ia_cartera`` ``cash`` vale 0: si hubiera movimientos de
        todos modos (una apertura que no debió ocurrir, ver ``CarteraInactiva``),
        la comparación ya los detecta como inconsistentes en vez de darlos por
        buenos.
        """

        fila = self.conn.execute("SELECT cash_eur FROM ia_cartera WHERE id = 1").fetchone()
        cash = float(fila[0]) if fila is not None else 0.0
        movimientos = float(self.conn.execute("SELECT COALESCE(SUM(importe_eur), 0) FROM ia_movimiento").fetchone()[0])
        return abs(movimientos - cash) < tolerancia_eur


def _ventas_ia_recientes(cartera_ia: CarteraIA) -> Dict[str, date]:
    """Última sesión de salida por símbolo, de cualquier cierre ya persistido (IA o stop).

    ``motivo_no_elegible`` es quien decide si la espera de recompra ya pasó
    (cuenta sesiones de mercado): esta función solo da el dato, sin filtrar
    por fecha.
    """

    filas = cartera_ia.conn.execute(
        "SELECT symbol, MAX(exit_session) AS ultima FROM ia_posicion WHERE estado = 'CERRADA' GROUP BY symbol"
    ).fetchall()
    return {f["symbol"]: date.fromisoformat(f["ultima"]) for f in filas}


def construir_estado_cartera(
    cartera_ia: CarteraIA, analizadas: Mapping[str, Analisis], proveedor: MarketDataProvider,
    ordenes_pendientes: Tuple[str, ...] = (), excluir_de_ia: Tuple[str, ...] = (),
) -> Tuple[EstadoCartera, Dict[str, str]]:
    """``EstadoCartera`` que ven los asesores, valorado causalmente con lo ya analizado en esta pasada.

    Una posición sin análisis esta pasada (``analizadas`` no la trae) se
    conserva con su valor de entrada, sin inventar ganancia ni pérdida, y se
    señala en las incidencias devueltas; nunca se la da por segura frente al
    stop (eso lo decide, por separado, ``verificar_stops``, con su propia
    descarga de barras). El tipo de cambio de cada posición es el de SU
    PROPIA ``signal_session`` (``fx_en_sesion``), no uno común para toda la
    pasada: dos posiciones en la misma divisa pero analizadas en sesiones
    distintas usan tasas distintas, cada una fechada a su propio evento.
    ``excluir_de_ia`` oculta de la lista que ve el comité (aunque sigue
    contando en el ``equity``) una posición cuyo stop ya se confirmó
    disparado pero no se pudo liquidar por falta de tipo de cambio, o que ya
    tiene una ``EXIT_IA`` pendiente (para no pedirle a la IA una segunda
    decisión de venta sobre lo que ya está en camino de venderse).
    """

    cash = cartera_ia.cash_eur()
    abiertas = cartera_ia.posiciones_abiertas()
    incidencias: Dict[str, str] = {}
    valores_eur: Dict[str, float] = {}
    pnl_pct_por_symbol: Dict[str, float] = {}
    for posicion in abiertas:
        analisis = analizadas.get(posicion.symbol)
        fx_resultado = fx_en_sesion(proveedor, posicion.currency, analisis.signal_session) if analisis else None
        if analisis is None or fx_resultado is None:
            incidencias[posicion.symbol] = "SIN_VALORACION_CAUSAL"
            valor_actual_eur = posicion.entry_price_eur
            valores_eur[posicion.symbol] = posicion.units * posicion.entry_price_eur
        else:
            valor_actual_eur = analisis.close * fx_resultado.tasa
            valores_eur[posicion.symbol] = posicion.units * valor_actual_eur
        # En EUR, no en precio nativo (hallazgo de Codex): con precio nativo sin cambios pero el
        # tipo de cambio movido, el precio nativo no refleja ninguna pérdida o ganancia real, pero
        # el equity en EUR sí la sufre — la IA debe ver la misma cifra que el equity que se le muestra.
        pnl_pct_por_symbol[posicion.symbol] = (
            100.0 * (valor_actual_eur - posicion.entry_price_eur) / posicion.entry_price_eur
            if posicion.entry_price_eur else 0.0
        )

    equity = cash + sum(valores_eur.values())
    posiciones = tuple(
        PosicionIA(
            symbol=posicion.symbol, entry_date=posicion.entry_session, signal_session=posicion.entry_session,
            decision_apertura="cartera_ia", entry_price=posicion.entry_price, stop=posicion.stop,
            invalidation_level=posicion.invalidation_level, pnl_pct=pnl_pct_por_symbol[posicion.symbol],
            exposicion_pct=100.0 * valores_eur[posicion.symbol] / equity if equity > 0 else 0.0,
            id=posicion.id,
        )
        for posicion in abiertas
        if posicion.symbol not in excluir_de_ia
    )
    return EstadoCartera(
        equity_eur=equity, cash_eur=cash, posiciones=posiciones, ordenes_pendientes=ordenes_pendientes,
        ventas_ia=_ventas_ia_recientes(cartera_ia),
    ), incidencias


def _sesiones_pendientes(
    proveedor: MarketDataProvider, symbol: str, market: str, desde: date, instante: datetime,
    settlement_minutes: int, limite_fecha: Optional[date] = None,
) -> Tuple[List[Tuple[date, Any]], Optional[Any]]:
    """Sesiones de ``symbol`` posteriores a ``desde``, causalmente observables a ``instante``.

    ``limite_fecha`` acota además a sesiones ``<= limite_fecha``: lo usa el
    procesador cronológico para avanzar fecha a fecha sin adelantarse.
    """

    try:
        bruto = proveedor.get_raw_history(symbol, period="2y", interval="1d")
    except Exception:
        return [], None
    pendientes: List[Tuple[date, Any]] = []
    for ts in bruto.index:
        sesion = session_date_of(ts, market)
        if sesion is None or sesion <= desde:
            continue
        if limite_fecha is not None and sesion > limite_fecha:
            continue
        cierre = session_close_at(market, sesion)
        if cierre is None:
            continue
        if cierre + timedelta(minutes=settlement_minutes) > instante:
            continue
        pendientes.append((sesion, ts))
    pendientes.sort(key=lambda par: par[0])
    return pendientes, bruto


def verificar_stops(
    cartera_ia: CarteraIA, proveedor: MarketDataProvider, instante: datetime, settlement_minutes: int,
    incidencias: List[str], limite_fecha: Optional[date] = None,
) -> Tuple[Dict[str, date], Set[str]]:
    """Protección mecánica, antes de cualquier IA: recorre TODA sesión pendiente desde la última
    verificada, no solo la última barra disponible.

    Una sesión sin analizar (p. ej. un fallo del análisis técnico completo)
    no debe dejar un hueco sin comprobar para siempre: aquí se descargan las
    barras directamente, independientes de si ``analizar()`` tuvo éxito ese
    día, y se recorren en orden; la primera que confirme el stop decide el
    cierre con su propio precio, no con el de la barra más reciente.
    ``limite_fecha`` acota el barrido a sesiones hasta esa fecha (inclusive):
    lo usa ``procesar_pendientes`` para interrumpirse al tiempo que resuelve
    entradas, sin adelantarse a sesiones que todavía no les tocan.

    Devuelve (símbolo -> sesión del cierre por stop, símbolos cuyo stop se
    confirmó pero no se pudo liquidar por falta de tipo de cambio: estos
    siguen ``ABIERTA`` y el llamador debe excluirlos de la IA esta pasada, sin
    dárselos nunca por mantenidos sin comprobar).
    """

    cerradas: Dict[str, date] = {}
    bloqueadas: Set[str] = set()
    for posicion in cartera_ia.posiciones_abiertas():
        pendientes, bruto = _sesiones_pendientes(
            proveedor, posicion.symbol, posicion.market, posicion.stop_verificado_hasta, instante,
            settlement_minutes, limite_fecha,
        )
        if bruto is None:
            incidencias.append(f"{posicion.symbol}: stop sin verificar; proveedor sin datos")
            continue

        ultima_segura = posicion.stop_verificado_hasta
        disparo: Optional[Tuple[date, ResultadoStop]] = None
        for sesion, ts in pendientes:
            fila = bruto.loc[ts]
            verificacion = evaluar_stop(posicion.stop, float(fila["Open"]), float(fila["Low"]))
            if not verificacion.verificable:
                incidencias.append(f"{posicion.symbol}: stop sin verificar en {sesion.isoformat()}; {verificacion.motivo}")
                break  # no se salta una sesión sin comprobar: hay que resolverla antes de avanzar
            if verificacion.disparado:
                disparo = (sesion, verificacion)
                break
            # Solo una sesión confirmada A SALVO adelanta el cursor: si dispara pero no se puede
            # liquidar (sin tipo de cambio), la siguiente pasada debe volver a verla como pendiente,
            # no como ya resuelta.
            ultima_segura = sesion

        if ultima_segura != posicion.stop_verificado_hasta:
            cartera_ia.actualizar_stop_verificado(posicion.id, ultima_segura)

        if disparo is None:
            continue
        sesion, verificacion = disparo
        fx_resultado = fx_en_sesion(proveedor, posicion.currency, sesion)
        if fx_resultado is None or verificacion.precio_fill is None:
            incidencias.append(f"{posicion.symbol}: stop disparado en {sesion.isoformat()} sin tipo de cambio; no se cierra")
            bloqueadas.add(posicion.symbol)
            continue
        cartera_ia.cerrar_posicion(
            posicion, exit_price=verificacion.precio_fill, exit_price_eur=verificacion.precio_fill * fx_resultado.tasa,
            exit_session=sesion, origen="STOP_OBLIGATORIO", motivo=verificacion.motivo, fx_rate=fx_resultado.tasa,
            fx_as_of=fx_resultado.as_of,
        )
        cerradas[posicion.symbol] = sesion
    return cerradas, bloqueadas


def _equity_coste_base(cartera_ia: CarteraIA) -> float:
    """Equity por coste (efectivo + valor de entrada de lo abierto), sin marcar a mercado.

    Solo para dimensionar una entrada nueva: es siempre conocida
    causalmente (nunca mira un precio posterior a la propia entrada), a
    diferencia de ``construir_estado_cartera``, que sí marca a mercado con
    el cierre ya analizado esta pasada para lo que ve la IA.
    """

    cash = cartera_ia.cash_eur()
    coste_abierto = sum(p.units * p.entry_price_eur for p in cartera_ia.posiciones_abiertas())
    return cash + coste_abierto


def resolver_entradas_del_dia(
    cartera_ia: CarteraIA, pendientes: Sequence[OrdenEntradaPendiente], fecha: date, proveedor: MarketDataProvider,
    incidencias: List[str],
) -> Tuple[List[str], List[str]]:
    """Resuelve, con una única equity congelada, todas las ``ENTRY`` pendientes cuya sesión es ``fecha``.

    El efectivo sí se descuenta tras cada ejecución dentro del lote: una
    orden posterior en el mismo lote puede acabar rechazada por
    ``CASH_INSUFICIENTE`` aunque la equity congelada sea la misma para
    todas. Una orden sin tipo de cambio sigue ``PENDIENTE`` (se reintenta),
    nunca se rechaza por un hueco contable.
    """

    abiertas: List[str] = []
    rechazadas: List[str] = []
    if not pendientes:
        return abiertas, rechazadas
    equity_before_eur = _equity_coste_base(cartera_ia)
    cache: Dict[str, Any] = {}
    for orden in sorted(pendientes, key=lambda o: (o.target_open, o.symbol)):
        cash_before_eur = cartera_ia.cash_eur()
        if orden.symbol in {p.symbol for p in cartera_ia.posiciones_abiertas()}:
            # No debería ocurrir por el flujo normal (la elegibilidad ya mira posiciones y
            # pendientes), pero si de algún modo coinciden, nunca se intenta abrir una segunda
            # posición del mismo símbolo: se rechaza explícito en vez de que lo impida una
            # excepción de integridad que abortaría el resto del lote.
            cartera_ia.rechazar_entrada(orden, "YA_EN_CARTERA", equity_before_eur=equity_before_eur, cash_before_eur=cash_before_eur)
            rechazadas.append(orden.symbol)
            continue
        if orden.symbol not in cache:
            try:
                cache[orden.symbol] = proveedor.get_raw_history(orden.symbol, period="2y", interval="1d")
            except Exception as exc:
                incidencias.append(f"{orden.symbol}: entrada sin resolver; {type(exc).__name__}: {exc}"[:200])
                continue
        bruto = cache[orden.symbol]
        sesion_ts = next((ts for ts in bruto.index if session_date_of(ts, orden.market) == fecha), None)
        if sesion_ts is None:
            incidencias.append(f"{orden.symbol}: entrada sin resolver; sin barra de {fecha.isoformat()} todavía")
            continue
        fila = bruto.loc[sesion_ts]
        gate = evaluar_gate_apertura(
            float(fila["Open"]), orden.niveles["stop"], orden.niveles["target2"], orden.niveles["entry_max"],
            orden.niveles.get("min_rr_ratio"),
        )
        if not gate.aprobado or gate.eff is None:
            cartera_ia.rechazar_entrada(orden, gate.motivo, equity_before_eur=equity_before_eur, cash_before_eur=cash_before_eur)
            rechazadas.append(orden.symbol)
            continue
        fx_resultado = fx_en_sesion(proveedor, orden.currency, fecha)
        if fx_resultado is None:
            incidencias.append(f"{orden.symbol}: entrada sin resolver; sin tipo de cambio de {fecha.isoformat()}")
            continue
        tasa, fx_as_of = fx_resultado.tasa, fx_resultado.as_of
        eff_eur = gate.eff * tasa
        unidades, importe_eur = calcular_tamano_entrada(equity_before_eur, gate.eff, orden.niveles["stop"], tasa)
        if unidades <= 0 or not math.isfinite(unidades):
            cartera_ia.rechazar_entrada(
                orden, "TAMANO_NO_VALIDO", equity_before_eur=equity_before_eur, cash_before_eur=cash_before_eur,
                fx_rate=tasa, fx_as_of=fx_as_of, requested_units=unidades, requested_notional_eur=importe_eur,
            )
            rechazadas.append(orden.symbol)
            continue
        if importe_eur > cash_before_eur:
            cartera_ia.rechazar_entrada(
                orden, "CASH_INSUFICIENTE", equity_before_eur=equity_before_eur, cash_before_eur=cash_before_eur,
                fx_rate=tasa, fx_as_of=fx_as_of, requested_units=unidades, requested_notional_eur=importe_eur,
            )
            rechazadas.append(orden.symbol)
            continue
        try:
            cartera_ia.ejecutar_entrada(
                orden, eff_native=gate.eff, eff_eur=eff_eur, units=unidades, fx_rate=tasa, fx_as_of=fx_as_of,
                equity_before_eur=equity_before_eur, cash_before_eur=cash_before_eur, requested_units=unidades,
                requested_notional_eur=importe_eur, session=fecha,
            )
        except (OrdenYaResuelta, EfectivoInsuficiente) as exc:
            # Defensa en profundidad: con el candado de pasada no debería dispararse en el camino
            # normal, pero si lo hace, esta orden se trata como no resuelta esta vez, sin abortar
            # las demás del lote.
            incidencias.append(f"{orden.symbol}: entrada sin resolver; {type(exc).__name__}")
            continue
        abiertas.append(orden.symbol)
    return abiertas, rechazadas


@dataclass
class ResultadoProcesamiento:
    cerradas_stop: Dict[str, date] = field(default_factory=dict)
    bloqueadas_fx: Set[str] = field(default_factory=set)
    abiertas: List[str] = field(default_factory=list)
    rechazadas: List[str] = field(default_factory=list)
    salidas_ia: List[str] = field(default_factory=list)
    rechazos_salida: List[str] = field(default_factory=list)


def resolver_salidas_del_dia(
    cartera_ia: CarteraIA, pendientes: Sequence[OrdenSalidaPendiente], fecha: date, proveedor: MarketDataProvider,
    incidencias: List[str],
) -> Tuple[List[str], List[str]]:
    """Resuelve, al ``Open`` de ``fecha``, todas las ``EXIT_IA`` pendientes cuya sesión es esa.

    Sin gate ni tamaño: es una venta de mercado, siempre de toda la posición.
    Se procesa DESPUÉS del barrido de stops de esa misma fecha (ver
    ``procesar_pendientes``): si el stop ya cerró la posición, aquí se
    rechaza con un motivo explícito — nunca se liquida dos veces la misma
    posición, ni por la coincidencia de un stop y una venta IA el mismo día.
    """

    ejecutadas: List[str] = []
    rechazadas: List[str] = []
    cache: Dict[str, Any] = {}
    for orden in sorted(pendientes, key=lambda o: (o.target_open, o.symbol)):
        # Antes de pedir cotización o tipo de cambio: si el stop ya cerró ESTA posición, se rechaza
        # terminal aquí mismo (hallazgo de Codex). Sin esto, una salida sobre una posición ya cerrada
        # podía quedar PENDIENTE para siempre mientras faltara el dato de mercado o de FX, y mientras
        # tanto bloqueaba (por símbolo) una posición nueva del mismo símbolo abierta después.
        abierta = cartera_ia.conn.execute(
            "SELECT 1 FROM ia_posicion WHERE id = ? AND estado = 'ABIERTA'", (orden.position_id,)
        ).fetchone()
        if abierta is None:
            cartera_ia.rechazar_salida_ia(orden, "POSICION_YA_CERRADA_POR_STOP")
            rechazadas.append(orden.symbol)
            continue
        if orden.symbol not in cache:
            try:
                cache[orden.symbol] = proveedor.get_raw_history(orden.symbol, period="2y", interval="1d")
            except Exception as exc:
                incidencias.append(f"{orden.symbol}: salida sin resolver; {type(exc).__name__}: {exc}"[:200])
                continue
        bruto = cache[orden.symbol]
        sesion_ts = next((ts for ts in bruto.index if session_date_of(ts, orden.market) == fecha), None)
        if sesion_ts is None:
            incidencias.append(f"{orden.symbol}: salida sin resolver; sin barra de {fecha.isoformat()} todavía")
            continue
        open_native = float(bruto.loc[sesion_ts, "Open"])
        if not (math.isfinite(open_native) and open_native > 0):
            incidencias.append(f"{orden.symbol}: salida sin resolver; apertura no ejecutable")
            continue
        fx_resultado = fx_en_sesion(proveedor, orden.currency, fecha)
        if fx_resultado is None:
            incidencias.append(f"{orden.symbol}: salida sin resolver; sin tipo de cambio de {fecha.isoformat()}")
            continue
        try:
            cartera_ia.ejecutar_salida_ia(
                orden, exit_price=open_native, exit_price_eur=open_native * fx_resultado.tasa,
                fx_rate=fx_resultado.tasa, fx_as_of=fx_resultado.as_of, session=fecha,
            )
        except PosicionYaCerrada:
            cartera_ia.rechazar_salida_ia(orden, "POSICION_YA_CERRADA_POR_STOP")
            rechazadas.append(orden.symbol)
            continue
        except OrdenYaResuelta as exc:
            incidencias.append(f"{orden.symbol}: salida sin resolver; {type(exc).__name__}")
            continue
        ejecutadas.append(orden.symbol)
    return ejecutadas, rechazadas


def _proxima_fecha_stop(
    cartera_ia: CarteraIA, proveedor: MarketDataProvider, instante: datetime, settlement_minutes: int,
) -> Optional[date]:
    """La sesión pendiente más próxima entre TODAS las posiciones abiertas ahora mismo.

    Se relee en vivo en cada vuelta del procesador: una posición abierta hace
    un instante (por una entrada resuelta esta misma pasada) también entra en
    este cálculo, así que sus propias sesiones posteriores —no solo la de su
    apertura— quedan cubiertas sin tener que recordarlas aparte.
    """

    proxima: Optional[date] = None
    for posicion in cartera_ia.posiciones_abiertas():
        pendientes, _bruto = _sesiones_pendientes(
            proveedor, posicion.symbol, posicion.market, posicion.stop_verificado_hasta, instante, settlement_minutes,
        )
        if pendientes and (proxima is None or pendientes[0][0] < proxima):
            proxima = pendientes[0][0]
    return proxima


def _proxima_fecha_orden(
    cartera_ia: CarteraIA, instante: datetime, settlement_minutes: int,
    excluir_entrada: AbstractSet[date] = frozenset(), excluir_salida: AbstractSet[date] = frozenset(),
) -> Tuple[Optional[date], Optional[date]]:
    """La sesión objetivo más próxima entre las ``ENTRY`` pendientes, y por separado entre las
    ``EXIT_IA`` pendientes (causalmente observables a ``instante``). Separadas porque
    ``procesar_pendientes`` necesita saber CUÁL de las dos clases está en esa fecha mínima.

    ``excluir_entrada``/``excluir_salida`` son fechas que ``procesar_pendientes`` ya probó y
    sabe irresolubles en esta misma llamada (hallazgo de Codex): se excluyen de la búsqueda, no
    solo del resultado, para que una ENTRY/EXIT_IA sin datos en la fecha más próxima no oculte
    para siempre una ORDEN POSTERIOR y perfectamente resoluble que, sin esto, nunca llegaría a
    verse porque esta función solo devuelve una única fecha mínima por clase.
    """

    proxima_entrada: Optional[date] = None
    for orden in cartera_ia.pendientes_entrada():
        if orden.target_session in excluir_entrada:
            continue
        cierre = session_close_at(orden.market, orden.target_session)
        if cierre is None or cierre + timedelta(minutes=settlement_minutes) > instante:
            continue
        if proxima_entrada is None or orden.target_session < proxima_entrada:
            proxima_entrada = orden.target_session
    proxima_salida: Optional[date] = None
    for orden_salida in cartera_ia.pendientes_salida():
        if orden_salida.target_session in excluir_salida:
            continue
        cierre = session_close_at(orden_salida.market, orden_salida.target_session)
        if cierre is None or cierre + timedelta(minutes=settlement_minutes) > instante:
            continue
        if proxima_salida is None or orden_salida.target_session < proxima_salida:
            proxima_salida = orden_salida.target_session
    return proxima_entrada, proxima_salida


def procesar_pendientes(
    cartera_ia: CarteraIA, proveedor: MarketDataProvider, instante: datetime, settlement_minutes: int,
    incidencias: List[str],
) -> ResultadoProcesamiento:
    """Procesador cronológico: la sesión pendiente más próxima primero, repitiendo hasta agotarlas.

    No basta con barrer primero todos los stops atrasados y luego todas las
    entradas/salidas atrasadas: una compra del lunes no puede usar el
    efectivo que libera un stop del miércoles si el proceso solo se retoma
    el viernes. Tampoco basta con fijar de antemano la lista de fechas a
    recorrer: una posición abierta hoy mismo (porque entró atrasada,
    recuperando varias sesiones de golpe) puede tener su propio stop
    pendiente unos días más adelante que todavía no estaba en esa lista.

    Por eso cada vuelta busca, en el estado YA actualizado por la vuelta
    anterior, la sesión pendiente más próxima entre entradas, salidas y
    stops, y para esa fecha exacta, en este orden:

    1. ``ENTRY`` pendientes de esa fecha, con el efectivo de ANTES de
       comprobar los stops de ese día (un stop por mínimo intradía libera
       caja en algún momento posterior a la apertura, nunca disponible para
       comprar en esa misma apertura).
    2. Stops hasta esa fecha — PRIORIDAD sobre cualquier venta de la IA:
       cubre a la vez lo que ya estaba abierto y lo que se acaba de abrir
       hoy mismo.
    3. ``EXIT_IA`` pendientes de esa fecha, DESPUÉS de los stops: si el stop
       ya cerró esa posición, la salida de la IA se rechaza con un motivo
       explícito en vez de liquidar dos veces la misma posición.

    Una ``ENTRY``/``EXIT_IA`` irresoluble (sin barra todavía, por ejemplo) nunca debe monopolizar
    el horizonte de los stops de OTRAS posiciones (hallazgo de Codex): si su fecha no avanza tras
    intentarlo, se excluye de ser la fecha mínima en las vueltas siguientes de ESTA llamada — sigue
    ``PENDIENTE`` para la próxima pasada — y el cursor pasa al siguiente candidato real (un stop,
    u otra orden), preservando intacta la prioridad de fecha para todo lo demás.
    """

    def _huella() -> Tuple[int, int, int, int, int, int]:
        return (
            len(resultado.abiertas), len(resultado.rechazadas), len(resultado.cerradas_stop),
            len(resultado.bloqueadas_fx), len(resultado.salidas_ia), len(resultado.rechazos_salida),
        )

    resultado = ResultadoProcesamiento()
    fecha_anterior: Optional[date] = None
    estancadas_entrada: Set[date] = set()
    estancadas_salida: Set[date] = set()
    limite_iteraciones = 10_000  # cualquier cartera real agota sus fechas pendientes muy antes
    for _ in range(limite_iteraciones):
        fecha_stop = _proxima_fecha_stop(cartera_ia, proveedor, instante, settlement_minutes)
        fecha_entrada, fecha_salida = _proxima_fecha_orden(
            cartera_ia, instante, settlement_minutes, estancadas_entrada, estancadas_salida
        )
        candidatas = [f for f in (fecha_stop, fecha_entrada, fecha_salida) if f is not None]
        if not candidatas:
            break
        fecha = min(candidatas)
        huella_antes = _huella()

        if fecha_entrada == fecha:
            pendientes_hoy = [o for o in cartera_ia.pendientes_entrada() if o.target_session == fecha]
            abiertas, rechazadas = resolver_entradas_del_dia(cartera_ia, pendientes_hoy, fecha, proveedor, incidencias)
            resultado.abiertas.extend(abiertas)
            resultado.rechazadas.extend(rechazadas)

        cerradas, bloqueadas = verificar_stops(
            cartera_ia, proveedor, instante, settlement_minutes, incidencias, limite_fecha=fecha
        )
        resultado.cerradas_stop.update(cerradas)
        resultado.bloqueadas_fx |= bloqueadas

        if fecha_salida == fecha:
            salidas_hoy = [o for o in cartera_ia.pendientes_salida() if o.target_session == fecha]
            ejecutadas, rechazos = resolver_salidas_del_dia(cartera_ia, salidas_hoy, fecha, proveedor, incidencias)
            resultado.salidas_ia.extend(ejecutadas)
            resultado.rechazos_salida.extend(rechazos)

        # Misma fecha que la vuelta anterior y nada avanzó (p. ej. un dato irresoluble o un stop
        # disparado sin FX, que nunca adelanta su cursor): seguir solo repetiría el mismo resultado
        # hasta agotar el límite.
        if fecha == fecha_anterior and _huella() == huella_antes:
            # Si la fecha estancada era la de una ENTRY/EXIT_IA, se excluye y el cursor puede
            # avanzar a lo que de verdad quede pendiente (un stop más lejano, otra orden): nunca se
            # trata como agotado solo porque ESTA orden concreta no tiene datos todavía.
            desatascada = False
            if fecha_entrada == fecha and fecha not in estancadas_entrada:
                estancadas_entrada.add(fecha)
                desatascada = True
            if fecha_salida == fecha and fecha not in estancadas_salida:
                estancadas_salida.add(fecha)
                desatascada = True
            if not desatascada:
                break  # la fecha era de un stop (p. ej. bloqueado por FX): aquí no hay nada más que excluir
            fecha_anterior = None
            continue
        fecha_anterior = fecha
    else:
        incidencias.append("procesar_pendientes: límite de iteraciones alcanzado; quedan sesiones sin procesar")
    return resultado


__all__ = [
    "ABOVE_MAX_ENTRY",
    "DATA_NOT_EXECUTABLE",
    "DATOS_INCOMPLETOS",
    "ENTRY_OK",
    "GAP_BAJO_STOP",
    "INVALID_STOP",
    "INVALID_TARGET",
    "MAX_POSICION_PCT",
    "NO_TOCADO",
    "RIESGO_PCT_POR_OPERACION",
    "RR_TOO_LOW",
    "STOP_TOCADO",
    "CarteraIA",
    "CarteraInactiva",
    "CarteraPoliticaDistinta",
    "EfectivoInsuficiente",
    "OrdenEntradaPendiente",
    "OrdenSalidaPendiente",
    "OrdenYaResuelta",
    "PosicionAbierta",
    "PosicionYaCerrada",
    "ResultadoFx",
    "ResultadoGate",
    "ResultadoProcesamiento",
    "ResultadoStop",
    "calcular_tamano_entrada",
    "construir_estado_cartera",
    "evaluar_gate_apertura",
    "evaluar_stop",
    "fx_en_sesion",
    "procesar_pendientes",
    "resolver_entradas_del_dia",
    "resolver_salidas_del_dia",
    "verificar_stops",
]
