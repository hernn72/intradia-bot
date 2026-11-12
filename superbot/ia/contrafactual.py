"""Contrafactual de las decisiones de compra: qué hizo después cada candidata, aprobada o no.

Responde a una sola pregunta: ¿las candidatas que el comité aprueba rinden mejor que las que
descarta? Cada decisión de compra se sigue con las mismas reglas que opera la cartera —el gate
de apertura y el stop obligatorio de ``cartera.py``, con los niveles congelados al decidir— como
si se hubiera comprado, y se cierra a un horizonte fijo.

Solo observa, y enseña desenlaces de valores que el bot no compró: es el canal lateral que el
propietario aceptó en D-82 §7. Todo sale de ``ia_decision`` y de barras de mercado: no abre
ninguna base de T-024 ni de T-025.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from statistics import mean, median
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from advisor.data.sessions import session_date_of, trim_unclosed_bar
from superbot.ia.cartera import evaluar_gate_apertura, evaluar_stop

logger = logging.getLogger(__name__)

HORIZONTE_SESIONES = 20
HORIZONTE_CORTO = 5

PENDIENTE = "PENDIENTE"
ABIERTA = "ABIERTA"
NO_EJECUTABLE = "NO_EJECUTABLE"
STOP = "STOP"
HORIZONTE = "HORIZONTE"
SIN_BARRA_DE_ENTRADA = "SIN_BARRA_DE_ENTRADA"
DATOS_INCOMPLETOS = "DATOS_INCOMPLETOS"
_FINALES = frozenset({NO_EJECUTABLE, STOP, HORIZONTE, SIN_BARRA_DE_ENTRADA, DATOS_INCOMPLETOS})

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS ia_contrafactual (
    decision_id INTEGER PRIMARY KEY REFERENCES ia_decision(id),
    symbol TEXT NOT NULL,
    resolucion TEXT NOT NULL,
    target_session TEXT NOT NULL,
    estado TEXT NOT NULL,
    motivo_gate TEXT,
    entrada REAL,
    salida REAL,
    sesiones INTEGER NOT NULL DEFAULT 0,
    hasta_session TEXT,
    retorno_pct REAL,
    retorno_r REAL,
    retorno_corto_pct REAL,
    final INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
"""

Barra = Tuple[date, float, float, float]


def asegurar_esquema(conn: sqlite3.Connection) -> None:
    conn.executescript(_ESQUEMA)


@dataclass(frozen=True)
class Desenlace:
    estado: str
    motivo_gate: Optional[str] = None
    entrada: Optional[float] = None
    salida: Optional[float] = None
    sesiones: int = 0
    hasta_session: Optional[date] = None
    retorno_pct: Optional[float] = None
    retorno_r: Optional[float] = None
    retorno_corto_pct: Optional[float] = None

    @property
    def final(self) -> bool:
        return self.estado in _FINALES


def _recorrer(barras: Sequence[Barra], entrada: float, stop: float, limite: int) -> Tuple[str, Optional[float], int]:
    """Sigue la posición hasta ``limite`` sesiones: estado, precio de salida (o último cierre) y sesiones vistas."""

    for numero, (_sesion, apertura, minimo, cierre) in enumerate(barras[:limite], start=1):
        resultado = evaluar_stop(stop, apertura, minimo)
        if not resultado.verificable or not (math.isfinite(cierre) and cierre > 0):
            return DATOS_INCOMPLETOS, None, numero
        if resultado.disparado:
            return STOP, resultado.precio_fill, numero
        if numero == limite:
            return HORIZONTE, cierre, numero
    return ABIERTA, barras[min(len(barras), limite) - 1][3], min(len(barras), limite)


def simular(niveles: Mapping[str, Any], barras: Sequence[Barra], target_session: date) -> Desenlace:
    """Desenlace de una decisión de compra con las barras ya cerradas, en orden cronológico.

    La entrada es la apertura de la sesión objetivo y solo esa: si la serie no la trae pero sí
    una posterior, no se entra otro día. El gate y el stop son los del motor real.
    """

    desde = [barra for barra in barras if barra[0] >= target_session]
    if not desde:
        return Desenlace(PENDIENTE)
    if desde[0][0] != target_session:
        return Desenlace(SIN_BARRA_DE_ENTRADA)
    try:
        stop, objetivo, maxima = float(niveles["stop"]), float(niveles["target2"]), float(niveles["entry_max"])
    except (KeyError, TypeError, ValueError):
        return Desenlace(DATOS_INCOMPLETOS)
    minimo_rr = niveles.get("min_rr_ratio")
    gate = evaluar_gate_apertura(desde[0][1], stop, objetivo, maxima, None if minimo_rr is None else float(minimo_rr))
    if not gate.aprobado or gate.eff is None:
        return Desenlace(NO_EJECUTABLE, motivo_gate=gate.motivo)
    entrada = gate.eff

    estado, salida, sesiones = _recorrer(desde, entrada, stop, HORIZONTE_SESIONES)
    if salida is None:
        return Desenlace(estado, entrada=entrada, sesiones=sesiones, hasta_session=desde[sesiones - 1][0])
    estado_corto, salida_corta, _n = _recorrer(desde, entrada, stop, HORIZONTE_CORTO)
    corto = None if estado_corto in (ABIERTA, DATOS_INCOMPLETOS) or salida_corta is None else salida_corta
    return Desenlace(
        estado, entrada=entrada, salida=salida, sesiones=sesiones, hasta_session=desde[sesiones - 1][0],
        retorno_pct=100.0 * (salida / entrada - 1.0),
        retorno_r=(salida - entrada) / (entrada - stop),
        retorno_corto_pct=None if corto is None else 100.0 * (corto / entrada - 1.0),
    )


def barras_de(df: pd.DataFrame, market: str) -> List[Barra]:
    barras: List[Barra] = []
    for marca, fila in df.iterrows():
        sesion = session_date_of(marca, market)
        if sesion is None:
            continue
        try:
            barras.append((sesion, float(fila["Open"]), float(fila["Low"]), float(fila["Close"])))
        except (KeyError, TypeError, ValueError):
            continue
    return barras


def actualizar(
    conn: sqlite3.Connection, proveedor: Any, universe: Any, instante: datetime, periodo: str, intervalo: str,
    settlement_minutes: int,
) -> int:
    """Recalcula el desenlace de toda decisión de compra que aún no sea definitiva. Devuelve cuántas tocó."""

    asegurar_esquema(conn)
    pendientes = conn.execute(
        "SELECT d.id, d.symbol, d.market, d.resolucion, d.target_session, d.cuantitativo FROM ia_decision d "
        "LEFT JOIN ia_contrafactual c ON c.decision_id = d.id "
        "WHERE d.tipo = 'COMPRA' AND COALESCE(c.final, 0) = 0 ORDER BY d.id"
    ).fetchall()
    series: Dict[Tuple[str, str], Optional[List[Barra]]] = {}
    tocadas = 0
    for decision_id, symbol, market, resolucion, target_session, cuantitativo in pendientes:
        niveles = json.loads(cuantitativo).get("niveles")
        if not isinstance(niveles, dict):
            continue
        clave = (symbol, market)
        if clave not in series:
            series[clave] = _serie(proveedor, universe, symbol, market, instante, periodo, intervalo, settlement_minutes)
        barras = series[clave]
        if barras is None:
            continue
        d = simular(niveles, barras, date.fromisoformat(target_session))
        conn.execute(
            "INSERT INTO ia_contrafactual (decision_id, symbol, resolucion, target_session, estado, motivo_gate, "
            "entrada, salida, sesiones, hasta_session, retorno_pct, retorno_r, retorno_corto_pct, final, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(decision_id) DO UPDATE SET estado = excluded.estado, motivo_gate = excluded.motivo_gate, "
            "entrada = excluded.entrada, salida = excluded.salida, sesiones = excluded.sesiones, "
            "hasta_session = excluded.hasta_session, retorno_pct = excluded.retorno_pct, "
            "retorno_r = excluded.retorno_r, retorno_corto_pct = excluded.retorno_corto_pct, "
            "final = excluded.final, updated_at = excluded.updated_at",
            (
                decision_id, symbol, resolucion, target_session, d.estado, d.motivo_gate, d.entrada, d.salida,
                d.sesiones, None if d.hasta_session is None else d.hasta_session.isoformat(), d.retorno_pct,
                d.retorno_r, d.retorno_corto_pct, int(d.final),
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ),
        )
        tocadas += 1
    return tocadas


def _serie(
    proveedor: Any, universe: Any, symbol: str, market: str, instante: datetime, periodo: str, intervalo: str,
    settlement_minutes: int,
) -> Optional[List[Barra]]:
    try:
        asset = universe.get(symbol)
        data_symbol = asset.data_symbol(instante) if asset is not None else symbol
        bruto = proveedor.get_history(data_symbol, period=periodo, interval=intervalo)
        recortado = trim_unclosed_bar(
            bruto, market=market, reference=instante, settlement_minutes=settlement_minutes, interval=intervalo
        ).df
        return barras_de(recortado, market)
    except Exception as exc:
        logger.info("contrafactual: %s sin serie: %s: %s", symbol, type(exc).__name__, exc)
        return None


# --- lectura ----------------------------------------------------------------------


@dataclass(frozen=True)
class Grupo:
    resolucion: str
    decisiones: int
    valores: int
    no_ejecutables: int
    seguidas: int
    stops: int
    retorno_medio_pct: Optional[float]
    retorno_mediano_pct: Optional[float]
    positivas_pct: Optional[float]
    r_medio: Optional[float]
    cortas: int
    retorno_corto_medio_pct: Optional[float]


def resumen(conn: sqlite3.Connection) -> Tuple[Grupo, ...]:
    """Aprobadas frente a descartadas. Una decisión ``PENDIENTE`` (sin sesión objetivo aún) no cuenta."""

    asegurar_esquema(conn)
    grupos: List[Grupo] = []
    for resolucion in ("COMPRAR", "DESCARTAR"):
        filas = conn.execute(
            "SELECT symbol, estado, retorno_pct, retorno_r, retorno_corto_pct FROM ia_contrafactual "
            "WHERE resolucion = ? AND estado <> ?", (resolucion, PENDIENTE),
        ).fetchall()
        seguidas = [f for f in filas if f[2] is not None]
        retornos = [float(f[2]) for f in seguidas]
        cortos = [float(f[4]) for f in filas if f[4] is not None]
        grupos.append(Grupo(
            resolucion=resolucion,
            decisiones=len(filas),
            valores=len({f[0] for f in filas}),
            no_ejecutables=sum(1 for f in filas if f[1] == NO_EJECUTABLE),
            seguidas=len(seguidas),
            stops=sum(1 for f in seguidas if f[1] == STOP),
            retorno_medio_pct=mean(retornos) if retornos else None,
            retorno_mediano_pct=median(retornos) if retornos else None,
            positivas_pct=100.0 * sum(1 for r in retornos if r > 0) / len(retornos) if retornos else None,
            r_medio=mean(float(f[3]) for f in seguidas) if seguidas else None,
            cortas=len(cortos),
            retorno_corto_medio_pct=mean(cortos) if cortos else None,
        ))
    return tuple(grupos)


__all__ = [
    "ABIERTA",
    "DATOS_INCOMPLETOS",
    "HORIZONTE",
    "HORIZONTE_CORTO",
    "HORIZONTE_SESIONES",
    "NO_EJECUTABLE",
    "PENDIENTE",
    "SIN_BARRA_DE_ENTRADA",
    "STOP",
    "Desenlace",
    "Grupo",
    "actualizar",
    "asegurar_esquema",
    "barras_de",
    "resumen",
    "simular",
]
