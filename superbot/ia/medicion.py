"""Medición de la cartera paper: valor a mercado, referencia y costes estimados.

Solo observa. No toca efectivo, posiciones ni órdenes, y nada de aquí decide una operación:
la contabilidad sigue siendo la de ``cartera.py``, a coste y sin comisiones. Lo que este módulo
añade es la respuesta a «¿está ganando?»: una foto por pasada del valor a mercado, de lo que
valdría el mismo dinero en un fondo indexado y de lo que costaría operar así de verdad.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from advisor.data.sessions import market_for_symbol, session_close_at, session_date_of, trim_unclosed_bar
from superbot.ia.cartera import CarteraIA, ValorPosicion
from superbot.ia.registro import RegistroIA

logger = logging.getLogger(__name__)

REFERENCIA = "EUNL.DE"
# Supuestos de ejecución real, no medidas: la orden de Trade Republic y una horquilla prudente
# para valores líquidos. Se aplican igual a la cartera y a la referencia.
COMISION_EUR_POR_ORDEN = 1.0
DESLIZAMIENTO_PCT_POR_LADO = 0.10

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS ia_valoracion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pasada_id INTEGER NOT NULL REFERENCES ia_pasada(id),
    -- ``ia_cartera.activated_at``: cambia con cada reinicio, así que separa una cartera de la siguiente.
    generacion TEXT NOT NULL,
    instante TEXT NOT NULL,
    cash_eur REAL NOT NULL,
    valor_posiciones_eur REAL NOT NULL,
    equity_eur REAL NOT NULL,
    capital_neto_eur REAL NOT NULL,
    sin_valorar INTEGER NOT NULL,
    costes_ejecucion_eur REAL NOT NULL,
    gasto_api_eur REAL NOT NULL,
    referencia_symbol TEXT NOT NULL,
    referencia_session TEXT,
    referencia_eur REAL,
    posiciones TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ia_valoracion_generacion ON ia_valoracion (generacion, id);
"""


def asegurar_esquema(conn: sqlite3.Connection) -> None:
    conn.executescript(_ESQUEMA)


def _generacion(conn: sqlite3.Connection) -> Optional[str]:
    # Una base de solo registro (sin ``CarteraIA``) todavía no tiene la tabla de la cartera.
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'ia_cartera'").fetchone() is None:
        return None
    fila = conn.execute("SELECT activated_at FROM ia_cartera WHERE id = 1 AND estado = 'PAPER'").fetchone()
    return None if fila is None or fila[0] is None else str(fila[0])


def _utc(texto: str) -> datetime:
    instante = datetime.fromisoformat(texto)
    return instante.replace(tzinfo=timezone.utc) if instante.tzinfo is None else instante.astimezone(timezone.utc)


def coste_orden_eur(importe_eur: float) -> float:
    return COMISION_EUR_POR_ORDEN + abs(importe_eur) * DESLIZAMIENTO_PCT_POR_LADO / 100.0


def costes_de_ejecucion_eur(conn: sqlite3.Connection) -> float:
    """Lo que habrían costado los fills de la cartera activa con los supuestos de arriba."""

    return sum(coste_orden_eur(fila[0]) for fila in conn.execute("SELECT importe_eur FROM ia_fill"))


def flujos_de_capital(conn: sqlite3.Connection) -> List[Tuple[datetime, float]]:
    filas = conn.execute("SELECT created_at, importe_eur FROM ia_movimiento WHERE tipo = 'APORTACION' ORDER BY id")
    return [(_utc(fila[0]), float(fila[1])) for fila in filas]


def valor_referencia(
    flujos: Sequence[Tuple[datetime, float]], cierres: Sequence[Tuple[date, datetime, float]],
) -> Optional[Tuple[float, date]]:
    """Lo que valdrían los mismos flujos de capital invertidos en la referencia.

    ``cierres`` son las sesiones ya cerradas, en orden: fecha, instante de cierre y precio. Cada
    flujo entra (o sale) al primer cierre igual o posterior a su instante, pagando la misma
    comisión y deslizamiento que se le suponen a la cartera; mientras ese cierre no exista, el
    dinero cuenta como efectivo. ``None`` si la serie no alcanza a cubrir un flujo: una serie que
    empieza después del dinero no permite saber cuál fue su primer cierre.
    """

    if not cierres or not flujos:
        return None
    unidades, efectivo = 0.0, 0.0
    for instante, importe in flujos:
        if instante < cierres[0][1]:
            return None
        precio = next((p for _s, cierre, p in cierres if cierre >= instante), None)
        if precio is None:
            efectivo += importe
        elif not (math.isfinite(precio) and precio > 0):
            return None
        else:
            unidades += (importe - coste_orden_eur(importe)) / precio
    return unidades * cierres[-1][2] + efectivo, cierres[-1][0]


def periodo_para(flujos: Sequence[Tuple[datetime, float]], instante: datetime) -> str:
    """El periodo de descarga más corto que alcanza al flujo más antiguo, con holgura."""

    if not flujos:
        return "2y"
    dias = (instante - min(momento for momento, _importe in flujos)).days
    return next((periodo for limite, periodo in ((550, "2y"), (1_600, "5y"), (3_400, "10y")) if dias < limite), "max")


def cierres_de(barras: pd.DataFrame, market: str) -> List[Tuple[date, datetime, float]]:
    cierres: List[Tuple[date, datetime, float]] = []
    for marca, precio in barras["Close"].items():
        session = session_date_of(marca, market)
        cierre = session_close_at(market, session) if session is not None else None
        if session is None or cierre is None or pd.isna(precio):
            continue
        cierres.append((session, cierre, float(precio)))
    return cierres


def registrar_valoracion(
    registro: RegistroIA, cartera_ia: CarteraIA, valores: Sequence[ValorPosicion], proveedor: Any,
    pasada_id: int, instante: datetime, settlement_minutes: int,
) -> None:
    """Guarda la foto de esta pasada. Sin referencia disponible la guarda igual, con ese hueco."""

    conn = registro.conn
    asegurar_esquema(conn)
    if _generacion(conn) is None:
        return

    # La descarga va antes y fuera de la transacción: una aportación hecha desde el dashboard
    # mientras dura no puede quedar a medias entre el efectivo y el capital de la misma foto.
    cierres: List[Tuple[date, datetime, float]] = []
    try:
        market = market_for_symbol(REFERENCIA)
        bruto = proveedor.get_history(
            REFERENCIA, period=periodo_para(flujos_de_capital(conn), instante), interval="1d"
        )
        barras = trim_unclosed_bar(
            bruto, market=market, reference=instante, settlement_minutes=settlement_minutes, interval="1d"
        ).df
        cierres = cierres_de(barras, market)
    except Exception as exc:
        logger.warning("referencia %s sin valorar: %s: %s", REFERENCIA, type(exc).__name__, exc)

    conn.execute("BEGIN IMMEDIATE")
    try:
        generacion = _generacion(conn)
        if generacion is None:
            conn.execute("ROLLBACK")
            return
        cash = cartera_ia.cash_eur()
        valor_posiciones = sum(v.valor_eur for v in valores)
        referencia = valor_referencia(flujos_de_capital(conn), cierres)
        conn.execute(
            "INSERT INTO ia_valoracion (pasada_id, generacion, instante, cash_eur, valor_posiciones_eur, equity_eur, "
            "capital_neto_eur, sin_valorar, costes_ejecucion_eur, gasto_api_eur, referencia_symbol, "
            "referencia_session, referencia_eur, posiciones, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                pasada_id, generacion, instante.isoformat(), cash, valor_posiciones, cash + valor_posiciones,
                cartera_ia.capital_neto_aportado_eur(), sum(1 for v in valores if not v.valorada),
                costes_de_ejecucion_eur(conn),
                registro.gasto_desde(_utc(generacion).isoformat(timespec="seconds")),
                REFERENCIA, None if referencia is None else referencia[1].isoformat(),
                None if referencia is None else referencia[0],
                json.dumps([
                    {
                        "position_id": v.position_id, "symbol": v.symbol, "units": v.units,
                        "session": None if v.session is None else v.session.isoformat(),
                        "precio_eur": v.precio_eur, "valor_eur": v.valor_eur, "coste_eur": v.coste_eur,
                        "valorada": v.valorada,
                    }
                    for v in valores
                ], sort_keys=True),
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ),
        )
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


# --- lectura ----------------------------------------------------------------------


@dataclass(frozen=True)
class Medicion:
    instante: str
    equity_eur: float
    capital_neto_eur: float
    sin_valorar: int
    costes_ejecucion_eur: float
    gasto_api_eur: float
    equity_neta_eur: float
    rentabilidad: Optional[float]
    rentabilidad_neta: Optional[float]
    caida_maxima: Optional[float]
    referencia_symbol: str
    referencia_eur: Optional[float]
    referencia_session: Optional[str]
    rentabilidad_referencia: Optional[float]
    posiciones: Tuple[Mapping[str, Any], ...]
    fotos: int


def _indice(serie: Sequence[Tuple[float, float]]) -> List[float]:
    """Índice de rentabilidad ponderada por tiempo de una serie de (valor, capital neto).

    Entre dos fotos, lo que cambia el capital neto es un flujo y no rentabilidad: se descuenta
    del valor final. La primera foto se mide contra su propio capital, que es lo aportado hasta
    entonces. Un valor de partida no positivo corta la serie: desde ahí no hay rentabilidad definida.
    """

    indice: List[float] = []
    for posicion, (valor, capital) in enumerate(serie):
        if posicion == 0:
            if capital <= 0:
                return indice
            indice.append(valor / capital)
            continue
        valor_previo, capital_previo = serie[posicion - 1]
        if valor_previo <= 0:
            return indice
        indice.append(indice[-1] * (valor - (capital - capital_previo)) / valor_previo)
    return indice


def _caida_maxima(indice: Sequence[float]) -> Optional[float]:
    if not indice:
        return None
    # Arranca en 1: una cartera que nace perdiendo ya está en caída respecto a su capital.
    maximo, peor = 1.0, 0.0
    for valor in indice:
        maximo = max(maximo, valor)
        peor = min(peor, valor / maximo - 1.0)
    return peor


def _ultimo(indice: Sequence[float], esperados: int) -> Optional[float]:
    return indice[-1] - 1.0 if indice and len(indice) == esperados else None


def leer_medicion(conn: sqlite3.Connection) -> Optional[Medicion]:
    """La última foto de la cartera activa y lo que su serie dice. ``None`` si aún no hay ninguna."""

    asegurar_esquema(conn)
    generacion = _generacion(conn)
    if generacion is None:
        return None
    cursor = conn.execute("SELECT * FROM ia_valoracion WHERE generacion = ? ORDER BY id", (generacion,))
    columnas = [d[0] for d in cursor.description]
    fotos: List[Dict[str, Any]] = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
    if not fotos:
        return None
    ultima = fotos[-1]

    bruta = _indice([(f["equity_eur"], f["capital_neto_eur"]) for f in fotos])
    neta = _indice([
        (f["equity_eur"] - f["costes_ejecucion_eur"] - f["gasto_api_eur"], f["capital_neto_eur"]) for f in fotos
    ])
    con_referencia = [f for f in fotos if f["referencia_eur"] is not None]
    referencia = _indice([(f["referencia_eur"], f["capital_neto_eur"]) for f in con_referencia])
    return Medicion(
        instante=ultima["instante"],
        equity_eur=ultima["equity_eur"],
        capital_neto_eur=ultima["capital_neto_eur"],
        sin_valorar=ultima["sin_valorar"],
        costes_ejecucion_eur=ultima["costes_ejecucion_eur"],
        gasto_api_eur=ultima["gasto_api_eur"],
        equity_neta_eur=ultima["equity_eur"] - ultima["costes_ejecucion_eur"] - ultima["gasto_api_eur"],
        rentabilidad=_ultimo(bruta, len(fotos)),
        rentabilidad_neta=_ultimo(neta, len(fotos)),
        caida_maxima=_caida_maxima(neta) if len(neta) == len(fotos) else None,
        referencia_symbol=ultima["referencia_symbol"],
        referencia_eur=ultima["referencia_eur"],
        referencia_session=ultima["referencia_session"],
        # Solo se compara si la referencia está valorada en la MISMA foto que la cartera.
        rentabilidad_referencia=(
            _ultimo(referencia, len(con_referencia)) if ultima["referencia_eur"] is not None else None
        ),
        posiciones=tuple(json.loads(ultima["posiciones"])),
        fotos=len(fotos),
    )


__all__ = [
    "COMISION_EUR_POR_ORDEN",
    "DESLIZAMIENTO_PCT_POR_LADO",
    "REFERENCIA",
    "Medicion",
    "asegurar_esquema",
    "cierres_de",
    "coste_orden_eur",
    "costes_de_ejecucion_eur",
    "flujos_de_capital",
    "leer_medicion",
    "periodo_para",
    "registrar_valoracion",
    "valor_referencia",
]
