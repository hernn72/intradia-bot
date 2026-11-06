"""Cartera paper de Superbot IA (Entrega C, fase 1): contabilidad y stop obligatorio.

Fase 1 cierra el ciclo de vida de una posición ya abierta (contabilidad, cierre
y su stop mecánico, independiente de la IA) y deja la cartera lista para que
las fases siguientes conecten ``COMPRAR`` (abre, en la apertura de la sesión
objetivo) y ``VENDER`` (cierra, en la apertura siguiente a la decisión, nunca
en el mismo cierre que la motivó: eso sería mirar hacia atrás). Por eso esta
fase todavía no abre posiciones desde una decisión de compra: solo ofrece la
primitiva ``abrir_posicion`` que las fases siguientes reutilizarán una vez
resuelto el hueco de apertura.

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
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterator, List, Mapping, Optional, Set, Tuple

from advisor.data.fx import FxConverter
from advisor.data.market_data import MarketDataProvider
from advisor.data.sessions import session_close_at, session_date_of
from superbot.ia.datos import Analisis
from superbot.ia.paquete import EstadoCartera, PosicionIA

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


class CarteraPoliticaDistinta(RuntimeError):
    """La cartera ya existe con otro estado o capital: no se reactiva por encima."""


class CarteraInactiva(RuntimeError):
    """No se puede abrir una posición sin una cartera ``PAPER`` activa."""


class PosicionYaCerrada(RuntimeError):
    """La posición ya no estaba ``ABIERTA``: no se liquida dos veces."""


class CarteraIA:
    """Estado persistido de la cartera paper, sobre la misma conexión que ``RegistroIA``."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.executescript(_ESQUEMA_CARTERA)

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
                "INSERT INTO ia_orden (position_id, decision_id, symbol, proposito, origen, estado, motivo, "
                "created_at) VALUES (?, ?, ?, 'ENTRY', 'DECISION_IA', 'EJECUTADA', NULL, ?)",
                (posicion_id, decision_apertura_id, symbol, _ahora_iso()),
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
        origen: str, motivo: str, decision_id: Optional[int] = None,
    ) -> None:
        """Cierra la posición, liquida el efectivo y lo registra, en una sola transacción.

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
                "INSERT INTO ia_orden (position_id, decision_id, symbol, proposito, origen, estado, motivo, "
                "created_at) VALUES (?, ?, ?, ?, ?, 'EJECUTADA', ?, ?)",
                (
                    posicion.id, decision_id, posicion.symbol, "STOP" if origen == "STOP_OBLIGATORIO" else "EXIT_IA",
                    origen, motivo, _ahora_iso(),
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
    cartera_ia: CarteraIA, analizadas: Mapping[str, Analisis], tasas_eur: Mapping[str, float],
    ordenes_pendientes: Tuple[str, ...] = (), excluir_de_ia: Tuple[str, ...] = (),
) -> Tuple[EstadoCartera, Dict[str, str]]:
    """``EstadoCartera`` que ven los asesores, valorado causalmente con lo ya analizado en esta pasada.

    Una posición sin análisis esta pasada (``analizadas`` no la trae) se
    conserva con su valor de entrada, sin inventar ganancia ni pérdida, y se
    señala en las incidencias devueltas; nunca se la da por segura frente al
    stop (eso lo decide, por separado, ``verificar_stops``, con su propia
    descarga de barras). ``excluir_de_ia`` oculta de la lista que ve el
    comité (aunque sigue contando en el ``equity``) una posición cuyo stop ya
    se confirmó disparado pero no se pudo liquidar por falta de tipo de
    cambio: no debe ofrecérsela a la IA como si estuviera simplemente
    mantenida.
    """

    cash = cartera_ia.cash_eur()
    abiertas = cartera_ia.posiciones_abiertas()
    incidencias: Dict[str, str] = {}
    valores_eur: Dict[str, float] = {}
    pnl_pct_por_symbol: Dict[str, float] = {}
    for posicion in abiertas:
        analisis = analizadas.get(posicion.symbol)
        tasa = tasas_eur.get(posicion.currency)
        if analisis is None or tasa is None:
            incidencias[posicion.symbol] = "SIN_VALORACION_CAUSAL"
            precio_actual = posicion.entry_price
            valores_eur[posicion.symbol] = posicion.units * posicion.entry_price_eur
        else:
            precio_actual = analisis.close
            valores_eur[posicion.symbol] = posicion.units * precio_actual * tasa
        pnl_pct_por_symbol[posicion.symbol] = (
            100.0 * (precio_actual - posicion.entry_price) / posicion.entry_price if posicion.entry_price else 0.0
        )

    equity = cash + sum(valores_eur.values())
    posiciones = tuple(
        PosicionIA(
            symbol=posicion.symbol, entry_date=posicion.entry_session, signal_session=posicion.entry_session,
            decision_apertura="cartera_ia", entry_price=posicion.entry_price, stop=posicion.stop,
            invalidation_level=posicion.invalidation_level, pnl_pct=pnl_pct_por_symbol[posicion.symbol],
            exposicion_pct=100.0 * valores_eur[posicion.symbol] / equity if equity > 0 else 0.0,
        )
        for posicion in abiertas
        if posicion.symbol not in excluir_de_ia
    )
    return EstadoCartera(
        equity_eur=equity, cash_eur=cash, posiciones=posiciones, ordenes_pendientes=ordenes_pendientes,
        ventas_ia=_ventas_ia_recientes(cartera_ia),
    ), incidencias


def verificar_stops(
    cartera_ia: CarteraIA, proveedor: MarketDataProvider, instante: datetime, settlement_minutes: int,
    fx: FxConverter, incidencias: List[str],
) -> Tuple[Dict[str, date], Set[str]]:
    """Protección mecánica, antes de cualquier IA: recorre TODA sesión pendiente desde la última
    verificada, no solo la última barra disponible.

    Una sesión sin analizar (p. ej. un fallo del análisis técnico completo)
    no debe dejar un hueco sin comprobar para siempre: aquí se descargan las
    barras directamente, independientes de si ``analizar()`` tuvo éxito ese
    día, y se recorren en orden; la primera que confirme el stop decide el
    cierre con su propio precio, no con el de la barra más reciente.

    Devuelve (símbolo -> sesión del cierre por stop, símbolos cuyo stop se
    confirmó pero no se pudo liquidar por falta de tipo de cambio: estos
    siguen ``ABIERTA`` y el llamador debe excluirlos de la IA esta pasada, sin
    dárselos nunca por mantenidos sin comprobar).
    """

    cerradas: Dict[str, date] = {}
    bloqueadas: Set[str] = set()
    for posicion in cartera_ia.posiciones_abiertas():
        try:
            bruto = proveedor.get_raw_history(posicion.symbol, period="2y", interval="1d")
        except Exception as exc:
            incidencias.append(f"{posicion.symbol}: stop sin verificar; {type(exc).__name__}: {exc}"[:200])
            continue

        pendientes: List[Tuple[date, Any]] = []
        for ts in bruto.index:
            sesion = session_date_of(ts, posicion.market)
            if sesion is None or sesion <= posicion.stop_verificado_hasta:
                continue
            cierre = session_close_at(posicion.market, sesion)
            if cierre is None:
                continue
            if cierre + timedelta(minutes=settlement_minutes) > instante:
                continue
            pendientes.append((sesion, ts))
        pendientes.sort(key=lambda par: par[0])

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
        tasa = fx.rate(posicion.currency)
        if tasa is None or verificacion.precio_fill is None:
            incidencias.append(f"{posicion.symbol}: stop disparado en {sesion.isoformat()} sin tipo de cambio; no se cierra")
            bloqueadas.add(posicion.symbol)
            continue
        cartera_ia.cerrar_posicion(
            posicion, exit_price=verificacion.precio_fill, exit_price_eur=verificacion.precio_fill * tasa,
            exit_session=sesion, origen="STOP_OBLIGATORIO", motivo=verificacion.motivo,
        )
        cerradas[posicion.symbol] = sesion
    return cerradas, bloqueadas


__all__ = [
    "DATOS_INCOMPLETOS",
    "GAP_BAJO_STOP",
    "NO_TOCADO",
    "STOP_TOCADO",
    "CarteraIA",
    "CarteraInactiva",
    "CarteraPoliticaDistinta",
    "PosicionAbierta",
    "PosicionYaCerrada",
    "ResultadoStop",
    "construir_estado_cartera",
    "evaluar_stop",
    "verificar_stops",
]
