"""Predicados de venta, en código: el modelo elige la causa, esto dice si es cierta.

Cada predicado mira una posición y su última sesión cerrada. ``None`` significa
que no se puede verificar, y un dato sin verificar nunca justifica una venta.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional

from superbot.ia.politica import CAUSA_INVALIDACION, CAUSA_SCORE, CAUSA_SMA, PoliticaIA


@dataclass(frozen=True)
class DatosPredicado:
    close: Optional[float]
    sma: Optional[float]
    score: Optional[float]
    invalidation_level: Optional[float]


def _numero(value: Optional[float]) -> bool:
    return value is not None and math.isfinite(value)


def evaluar(datos: DatosPredicado, politica: PoliticaIA) -> Dict[str, Optional[bool]]:
    close = datos.close
    resultado: Dict[str, Optional[bool]] = {CAUSA_SMA: None, CAUSA_SCORE: None, CAUSA_INVALIDACION: None}
    if close is not None and _numero(close) and datos.sma is not None and _numero(datos.sma):
        resultado[CAUSA_SMA] = close < datos.sma * (1 - politica.sma_holgura)
    if datos.score is not None and _numero(datos.score):
        resultado[CAUSA_SCORE] = datos.score < politica.score_venta
    if close is not None and _numero(close) and datos.invalidation_level is not None and _numero(
        datos.invalidation_level
    ):
        resultado[CAUSA_INVALIDACION] = close < datos.invalidation_level
    return resultado


def hay_disparador(predicados: Dict[str, Optional[bool]]) -> bool:
    """Una posición solo se revisa con algún predicado verificado como cierto."""

    return any(value is True for value in predicados.values())
