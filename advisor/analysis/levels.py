"""Niveles operativos de una oportunidad: entrada, stop, invalidación,
objetivos y ratio beneficio/riesgo.

Todos los niveles salen de la estructura del mercado (soportes, resistencias,
medias) y de la volatilidad medida (ATR). Ninguno es un porcentaje fijo
elegido a dedo, y los objetivos se calculan antes que el ratio para que el
ratio no pueda "fabricarse" moviendo un objetivo hasta que cuadre.

Núcleo puro, en la divisa nativa del activo: la conversión a euros ocurre
después, en la capa de informe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from advisor.analysis.snapshot import TechnicalSnapshot
from advisor.config import LevelsConfig

# Holgura, en ATR, para colocar el stop por debajo de un soporte: lo justo
# para que el ruido normal alrededor del nivel no lo active.
_SUPPORT_BUFFER_ATR = 0.25

# El ratio divide dos magnitudes derivadas del mismo ATR, así que con la
# configuración por defecto (stop 2·ATR, objetivo 2 a 3·ATR) vale
# exactamente el umbral exigido — salvo por el ruido de la coma flotante,
# que lo deja en 1,49999… para la mayoría de los precios. Comparado a pelo,
# un bit de redondeo decidiría el descarte de un activo, y el informe
# mostraría "ratio 1,5:1" junto al motivo "por debajo de 1,5:1".
_RATIO_REL_TOL = 1e-9


def rr_at_least(rr_ratio: float, threshold: float) -> bool:
    """¿El ratio alcanza ``threshold``, tolerando el ruido de coma flotante?"""

    return rr_ratio >= threshold or math.isclose(rr_ratio, threshold, rel_tol=_RATIO_REL_TOL)


def reward_risk(entry: float, target: float, stop: float) -> Optional[float]:
    """Ratio beneficio/riesgo de una operación larga a un precio de entrada."""

    if not all(math.isfinite(value) for value in (entry, target, stop)):
        return None
    risk = entry - stop
    reward = target - entry
    if risk <= 0 or reward <= 0:
        return None
    return reward / risk


def entry_max_for_rr(target: float, stop: float, min_rr: float) -> Optional[float]:
    """Precio máximo compatible con ``min_rr`` para una operación larga."""

    if not all(math.isfinite(value) for value in (target, stop, min_rr)):
        return None
    if min_rr <= 0 or target <= stop:
        return None
    return (target + min_rr * stop) / (1 + min_rr)


@dataclass(frozen=True)
class Levels:
    """Niveles de una operación, en la divisa nativa del activo."""

    price: float
    entry_ideal_low: float
    entry_ideal_high: float
    entry_max: float
    stop: float
    invalidation_level: Optional[float]
    invalidation_reason: str
    stop_basis: str
    target1: float
    target2: float
    target3: float
    risk_pp: float
    reward_pct: float
    rr_ratio: float
    extension_atr: Optional[float]
    chase: bool
    entry_max_tecnica: Optional[float] = None
    entry_max_rr: Optional[float] = None
    min_rr_ratio: Optional[float] = None

    @property
    def target_pcts(self) -> tuple:
        """Potencial porcentual de cada objetivo desde el precio de referencia."""
        return (
            (self.target1 / self.price - 1) * 100,
            (self.target2 / self.price - 1) * 100,
            (self.target3 / self.price - 1) * 100,
        )


def compute_levels(snapshot: TechnicalSnapshot, config: LevelsConfig, min_rr_ratio: float) -> Optional[Levels]:
    """Calcula los niveles de una oportunidad alcista sobre ``snapshot``.

    Devuelve ``None`` si falta el ATR: sin una medida de volatilidad no se
    puede situar un stop con criterio, y una operación sin riesgo definido no
    debe recomendarse.
    """

    return compute_levels_from_inputs(
        price=snapshot.price,
        atr=snapshot.atr,
        low_lookback=snapshot.low_lookback,
        high_lookback=snapshot.high_lookback,
        ema_fast=snapshot.ema_fast,
        ema_slow=snapshot.ema_slow,
        sma_long=snapshot.sma_long,
        config=config,
        min_rr_ratio=min_rr_ratio,
    )


def compute_levels_from_inputs(
    *,
    price: float,
    atr: Optional[float],
    low_lookback: Optional[float],
    high_lookback: Optional[float],
    ema_fast: Optional[float],
    ema_slow: Optional[float] = None,
    sma_long: Optional[float] = None,
    config: LevelsConfig,
    min_rr_ratio: float,
) -> Optional[Levels]:
    """Deriva niveles desde los insumos primitivos, sin recalcular indicadores."""

    if atr is None or atr <= 0:
        return None

    entry_ideal_low = price - config.entry_pullback_atr * atr
    entry_ideal_high = price
    entry_max_tecnica = price + config.entry_max_atr * atr

    # ¿El precio ya está extendido respecto a su media rápida? Si lo está,
    # entrar ahora es perseguir el movimiento (§14).
    extension_atr = None
    chase = False
    if ema_fast is not None:
        extension_atr = (price - ema_fast) / atr
        chase = extension_atr > config.entry_max_atr

    # Stop: por volatilidad, salvo que exista un soporte más cercano que esa
    # distancia, en cuyo caso se apoya en él (más ajustado y justificado por
    # estructura, no por un porcentaje arbitrario).
    volatility_stop = price - config.atr_stop_multiple * atr
    support = low_lookback
    support_stop = None
    if support is not None and volatility_stop < support < price:
        support_stop = support - _SUPPORT_BUFFER_ATR * atr
    # El soporte solo manda si de verdad acerca el stop: cuando cae tan pegado
    # al stop por volatilidad que la holgura lo empujaría por debajo de él,
    # apoyarse en el soporte daría un stop MÁS lejano que el de volatilidad,
    # justo lo contrario de lo que lo justifica ("más ajustado y justificado
    # por estructura").
    if support_stop is not None and support_stop > volatility_stop:
        stop = support_stop
        stop_basis = f"soporte de {support:.2f} con holgura de {_SUPPORT_BUFFER_ATR:g}·ATR"
    else:
        stop = volatility_stop
        stop_basis = f"{config.atr_stop_multiple:g}·ATR por debajo del precio"

    if stop <= 0 or stop >= price:
        return None

    # Objetivos por múltiplos de ATR. Si hay una resistencia por delante más
    # cercana que el objetivo 1, ella pasa a ser el objetivo conservador: es
    # el primer obstáculo real que encontrará el precio.
    m1, m2, m3 = config.target_atr_multiples
    target1 = price + m1 * atr
    resistance = high_lookback
    if resistance is not None and price < resistance < target1:
        target1 = resistance
    target2 = price + m2 * atr
    # El objetivo 2 es el que forma el ratio beneficio/riesgo. Si también
    # cede ante la resistencia, el ratio deja de ser un múltiplo fijo del ATR
    # y pasa a medir cuánto recorrido real hay hasta el primer obstáculo; si
    # no, mide solo la geometría de la configuración. Es una decisión de
    # diseño con consecuencias medidas: docs/ratio-beneficio-riesgo.md.
    if config.target2_structural and resistance is not None and price < resistance < target2:
        target2 = resistance
    # El objetivo 3 es el escenario alcista: supone que la resistencia se
    # rompe, así que no cede ante ella ni siquiera con la opción activada.
    target3 = price + m3 * atr

    risk_pp = (price - stop) / price * 100
    reward_pct = (target2 / price - 1) * 100
    rr = reward_risk(price, target2, stop)
    rr_ratio = rr if rr is not None else 0.0
    entry_max_rr = entry_max_for_rr(target2, stop, min_rr_ratio)
    if entry_max_rr is None:
        return None
    entry_max = min(entry_max_tecnica, entry_max_rr)
    rr_at_entry_max = reward_risk(entry_max, target2, stop)
    if rr_at_entry_max is None or not rr_at_least(rr_at_entry_max, min_rr_ratio):
        return None

    # La invalidación de la tesis no es el stop de precio (§16): el stop
    # protege el capital, la invalidación dice que el motivo para estar
    # dentro ha dejado de existir.
    invalidation_level: Optional[float] = None
    invalidation_reason = "sin nivel estructural de referencia disponible"
    if ema_slow is not None and price > ema_slow:
        invalidation_level = ema_slow
        invalidation_reason = "cierre por debajo de la EMA lenta: la tendencia que sostiene la tesis desaparece"
    elif sma_long is not None:
        invalidation_level = sma_long
        invalidation_reason = "cierre por debajo de la SMA larga: el activo deja de estar en tendencia alcista"

    return Levels(
        price=price,
        entry_ideal_low=entry_ideal_low,
        entry_ideal_high=entry_ideal_high,
        entry_max=entry_max,
        stop=stop,
        invalidation_level=invalidation_level,
        invalidation_reason=invalidation_reason,
        stop_basis=stop_basis,
        target1=target1,
        target2=target2,
        target3=target3,
        risk_pp=risk_pp,
        reward_pct=reward_pct,
        rr_ratio=rr_ratio,
        extension_atr=extension_atr,
        chase=chase,
        entry_max_tecnica=entry_max_tecnica,
        entry_max_rr=entry_max_rr,
        min_rr_ratio=min_rr_ratio,
    )
