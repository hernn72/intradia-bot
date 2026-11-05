"""Comité determinista: consolida dictámenes válidos. Sin modelo, sin azar y sin reloj.

Un dictamen ausente o inválido nunca cuenta como aprobación. En compra acaba en
descarte y en posición, en mantener.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from superbot.ia.politica import PoliticaIA

COMPRAR = "COMPRAR"
DESCARTAR = "DESCARTAR"
MANTENER = "MANTENER"
VENDER = "VENDER"

PRIORIDADES = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}


@dataclass(frozen=True)
class Voto:
    """Lo que el comité necesita de un dictamen ya validado."""

    asesor: str
    decision: str
    prioridad: Optional[str] = None
    causa: Optional[str] = None


@dataclass(frozen=True)
class Resolucion:
    decision: str
    motivo: str
    prioridad: Optional[str] = None
    causa: Optional[str] = None


def resolver_compra(oportunidad: Optional[Voto], riesgo: Optional[Voto]) -> Resolucion:
    if oportunidad is None or riesgo is None:
        return Resolucion(DESCARTAR, "FALTA_DICTAMEN_VALIDO")
    if oportunidad.decision == COMPRAR and riesgo.decision == COMPRAR:
        return Resolucion(COMPRAR, "APROBADA_POR_AMBOS", prioridad=oportunidad.prioridad)
    return Resolucion(DESCARTAR, "RECHAZADA_POR_ASESOR")


def resolver_posicion(votos: Sequence[Optional[Voto]], predicados: Mapping[str, Optional[bool]]) -> Resolucion:
    validos = [voto for voto in votos if voto is not None]
    if not validos:
        return Resolucion(MANTENER, "FALTA_DICTAMEN_VALIDO")
    ventas = [voto for voto in validos if voto.decision == VENDER]
    if not ventas:
        return Resolucion(MANTENER, "MANTENIDA_POR_ASESORES")
    for voto in ventas:
        if voto.causa is not None and predicados.get(voto.causa) is True:
            return Resolucion(VENDER, "CAUSA_VERIFICADA", causa=voto.causa)
    return Resolucion(MANTENER, "CAUSA_NO_VERIFICADA")


def ordenar_compras(aprobadas: Sequence[Tuple[str, Resolucion, float]]) -> List[str]:
    """Prioridad del asesor, después score, después símbolo: mismo orden con la misma entrada."""

    orden = sorted(aprobadas, key=lambda item: (PRIORIDADES.get(item[1].prioridad or "", 9), -item[2], item[0]))
    return [symbol for symbol, _resolucion, _score in orden]


def limitar_ventas(candidatas: Mapping[str, float], politica: PoliticaIA) -> Dict[str, bool]:
    """Qué ventas pasan el límite por pasada: primero la de peor resultado no realizado."""

    orden = sorted(candidatas, key=lambda symbol: (candidatas[symbol], symbol))
    elegidas = set(orden[: politica.max_ventas_por_pasada])
    return {symbol: symbol in elegidas for symbol in candidatas}
