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
from dataclasses import dataclass, replace
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
CREATE TABLE IF NOT EXISTS ia_referencia_cierre (
    symbol TEXT NOT NULL,
    session TEXT NOT NULL,
    precio REAL NOT NULL,
    observado_en TEXT NOT NULL,
    PRIMARY KEY (symbol, session)
);
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


def completar_cierres(
    conn: sqlite3.Connection, market: str, cierres: Sequence[Tuple[date, datetime, float]],
) -> List[Tuple[date, datetime, float]]:
    """La serie descargada, más los cierres ya observados que el proveedor ha dejado de servir.

    yfinance retira por la mañana barras europeas que había servido la noche anterior: sin esto, la
    referencia retrocedía de sesión. La descarga manda sobre lo guardado; lo guardado solo rellena
    huecos posteriores a su primera barra, porque la serie tiene que seguir empezando donde empieza
    la descarga (``valor_referencia`` decide con eso si alcanza a cubrir un flujo).
    """

    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    validos = [c for c in cierres if math.isfinite(c[2]) and c[2] > 0]
    for session, _cierre, precio in validos:
        conn.execute(
            "INSERT INTO ia_referencia_cierre (symbol, session, precio, observado_en) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(symbol, session) DO UPDATE SET precio = excluded.precio, observado_en = excluded.observado_en "
            "WHERE precio <> excluded.precio",
            (REFERENCIA, session.isoformat(), precio, ahora),
        )
    if not validos:
        return list(cierres)
    presentes = {c[0] for c in cierres}
    completos = list(cierres)
    for texto, precio in conn.execute(
        "SELECT session, precio FROM ia_referencia_cierre WHERE symbol = ? AND session > ?",
        (REFERENCIA, cierres[0][0].isoformat()),
    ):
        session = date.fromisoformat(texto)
        cierre = session_close_at(market, session)
        if session not in presentes and cierre is not None:
            completos.append((session, cierre, float(precio)))
    return sorted(completos, key=lambda c: c[0])


def _sin_retroceder(
    conn: sqlite3.Connection, generacion: str, valores: Sequence[ValorPosicion],
) -> List[ValorPosicion]:
    """Cada posición, con su último cierre ya visto si esta pasada solo trae uno más viejo.

    Cubre también la recién comprada cuya única barra se retira: ``valorar_abiertas`` la devuelve a
    su coste (valorada, sin sesión). La que no se puede valorar sigue a coste, porque eso se declara.
    """

    vistos: Dict[int, Mapping[str, Any]] = {}
    for (texto,) in conn.execute("SELECT posiciones FROM ia_valoracion WHERE generacion = ? ORDER BY id", (generacion,)):
        for previa in json.loads(texto):
            anterior = vistos.get(previa["position_id"])
            if previa["session"] is not None and (anterior is None or previa["session"] >= anterior["session"]):
                vistos[previa["position_id"]] = previa
    resultado: List[ValorPosicion] = []
    for valor in valores:
        visto = vistos.get(valor.position_id)
        if visto is not None and valor.valorada and (
            valor.session is None or valor.session.isoformat() < visto["session"]
        ):
            precio = float(visto["precio_eur"])
            valor = replace(
                valor, session=date.fromisoformat(visto["session"]), precio_eur=precio, valor_eur=valor.units * precio,
            )
        resultado.append(valor)
    return resultado


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
    market = market_for_symbol(REFERENCIA)
    try:
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
        valores = _sin_retroceder(conn, generacion, valores)
        cash = cartera_ia.cash_eur()
        valor_posiciones = sum(v.valor_eur for v in valores)
        referencia = valor_referencia(flujos_de_capital(conn), completar_cierres(conn, market, cierres))
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
    # Falso si la referencia y la cartera van a cierres de sesiones distintas: restarlas mezclaría días.
    comparable: bool


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


def _comparable(conn: sqlite3.Connection, foto: Mapping[str, Any], posiciones: Sequence[Mapping[str, Any]]) -> bool:
    referencia = foto["referencia_session"]
    if referencia is None:
        return False
    ultimo_fill = conn.execute(
        "SELECT MAX(session) FROM ia_fill WHERE created_at <= ?", (foto["created_at"],)
    ).fetchone()[0]
    if ultimo_fill is not None and str(ultimo_fill) > referencia:
        return False
    # Una posición a coste (``session`` nula) no tiene cierre que comparar con el de la referencia.
    return all(p["session"] == referencia for p in posiciones)


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
    posiciones: Tuple[Mapping[str, Any], ...] = tuple(json.loads(ultima["posiciones"]))

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
        posiciones=posiciones,
        fotos=len(fotos),
        comparable=_comparable(conn, ultima, posiciones),
    )


__all__ = [
    "COMISION_EUR_POR_ORDEN",
    "DESLIZAMIENTO_PCT_POR_LADO",
    "REFERENCIA",
    "Medicion",
    "asegurar_esquema",
    "cierres_de",
    "completar_cierres",
    "coste_orden_eur",
    "costes_de_ejecucion_eur",
    "flujos_de_capital",
    "leer_medicion",
    "periodo_para",
    "registrar_valoracion",
    "valor_referencia",
]
