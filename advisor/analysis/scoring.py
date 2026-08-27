"""Sistema de puntuación 0-100 de una oportunidad.

Seis dimensiones con peso fijo:

    catalizador 20 · fundamental 20 · técnico 20
    beneficio/riesgo 20 · contexto 10 · convicción 10

**Todo se calcula en Python.** El agente IA redacta el texto de la
recomendación, pero no puntúa: si un LLM pudiera mover la nota, la nota
dejaría de ser comparable entre ejecuciones.

Dimensiones sin datos
---------------------
Una dimensión que no puede evaluarse (hoy: los fundamentales, que exigen una
fuente de datos que este bot no tiene) **se excluye del cómputo** y la
puntuación se normaliza sobre los puntos realmente evaluables. La alternativa
—puntuarla a cero— haría que ninguna acción superase nunca el umbral por una
carencia del bot, no del activo. El informe indica siempre sobre cuántos
puntos evaluables se ha calculado la nota.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from advisor.analysis.levels import Levels, rr_at_least
from advisor.analysis.market_context import MarketContext
from advisor.analysis.snapshot import TechnicalSnapshot
from advisor.config import ScoringConfig

WEIGHTS = {
    "catalizador": 20.0,
    "fundamental": 20.0,
    "tecnico": 20.0,
    "beneficio_riesgo": 20.0,
    "contexto": 10.0,
    "conviccion": 10.0,
}


@dataclass(frozen=True)
class Component:
    """Un factor concreto dentro de una dimensión.

    ``points is None`` significa "sin dato": el factor no suma ni resta,
    simplemente sale del reparto de esa dimensión.
    """

    name: str
    points: Optional[float]
    max_points: float
    detail: str = ""


@dataclass(frozen=True)
class Dimension:
    """Una de las seis dimensiones de la puntuación."""

    name: str
    weight: float
    components: List[Component] = field(default_factory=list)
    unavailable_reason: Optional[str] = None

    @property
    def raw_max(self) -> float:
        """Puntos máximos de los factores que sí tienen dato."""
        return sum(c.max_points for c in self.components if c.points is not None)

    @property
    def raw_points(self) -> float:
        return sum(c.points for c in self.components if c.points is not None)

    @property
    def available(self) -> bool:
        return self.unavailable_reason is None and self.raw_max > 0

    @property
    def points(self) -> float:
        """Puntos de la dimensión, reescalados a su peso."""
        if not self.available:
            return 0.0
        return round(self.weight * self.raw_points / self.raw_max, 2)


@dataclass(frozen=True)
class Score:
    """Resultado de la puntuación de una oportunidad."""

    dimensions: List[Dimension]

    @property
    def evaluable_max(self) -> float:
        """Puntos máximos sobre los que se ha podido puntuar realmente."""
        return sum(d.weight for d in self.dimensions if d.available)

    @property
    def points(self) -> float:
        return round(sum(d.points for d in self.dimensions), 2)

    @property
    def value(self) -> float:
        """Puntuación normalizada a 0-100 sobre los puntos evaluables."""
        if self.evaluable_max <= 0:
            return 0.0
        return round(100.0 * self.points / self.evaluable_max, 1)

    @property
    def missing_dimensions(self) -> List[str]:
        return [d.name for d in self.dimensions if not d.available]

    @property
    def grade(self) -> str:
        """Clasificación cualitativa de la puntuación."""
        value = self.value
        if value >= 90:
            return "Excepcional"
        if value >= 80:
            return "Muy atractiva"
        if value >= 70:
            return "Interesante"
        if value >= 60:
            return "Vigilancia"
        return "No operar"


def _catalizador(snapshot: TechnicalSnapshot) -> Dimension:
    """Catalizador observable en el precio: volumen anormal, hueco y ruptura.

    Es una versión reducida del catalizador que pide el asesor: sin fuente de
    noticias, resultados ni operaciones corporativas, solo puede detectarse la
    huella que un catalizador deja en el gráfico, no el catalizador en sí.
    """

    components: List[Component] = []

    ratio = snapshot.volume_ratio
    if ratio is None:
        components.append(Component("volumen", None, 8.0, "sin datos de volumen"))
    elif ratio >= 2.0:
        components.append(Component("volumen", 8.0, 8.0, f"volumen {ratio:.1f}× la media"))
    elif ratio >= 1.5:
        components.append(Component("volumen", 5.0, 8.0, f"volumen {ratio:.1f}× la media"))
    elif ratio >= 1.2:
        components.append(Component("volumen", 3.0, 8.0, f"volumen {ratio:.1f}× la media"))
    else:
        components.append(Component("volumen", 0.0, 8.0, f"volumen {ratio:.1f}× la media (sin anomalía)"))

    gap = snapshot.gap_pct
    if gap is None:
        components.append(Component("hueco", None, 6.0, "sin datos de apertura"))
    elif gap >= 2.0:
        components.append(Component("hueco", 6.0, 6.0, f"hueco alcista {gap:+.1f}%"))
    elif gap >= 1.0:
        components.append(Component("hueco", 3.0, 6.0, f"hueco alcista {gap:+.1f}%"))
    elif gap <= -2.0:
        components.append(Component("hueco", 0.0, 6.0, f"hueco bajista {gap:+.1f}%"))
    else:
        components.append(Component("hueco", 1.0, 6.0, f"apertura sin hueco relevante ({gap:+.1f}%)"))

    high = snapshot.high_lookback
    if high is None or high <= 0:
        components.append(Component("ruptura", None, 6.0, "sin máximos de referencia"))
    else:
        distance = (snapshot.price / high - 1) * 100
        if distance >= -0.1:
            components.append(Component("ruptura", 6.0, 6.0, f"ruptura del máximo de la ventana ({distance:+.1f}%)"))
        elif distance >= -2.0:
            components.append(Component("ruptura", 3.0, 6.0, f"a {distance:+.1f}% del máximo de la ventana"))
        else:
            components.append(Component("ruptura", 0.0, 6.0, f"a {distance:+.1f}% del máximo de la ventana"))

    return Dimension("catalizador", WEIGHTS["catalizador"], components)


def _fundamental(config: ScoringConfig) -> Dimension:
    """Dimensión fundamental.

    Sin una fuente de datos de PER, márgenes, deuda o flujo de caja, esta
    dimensión no puede evaluarse y queda fuera del cómputo.
    """

    if not config.fundamentals_enabled:
        return Dimension(
            "fundamental",
            WEIGHTS["fundamental"],
            components=[],
            unavailable_reason="sin fuente de datos fundamentales configurada",
        )
    return Dimension(
        "fundamental",
        WEIGHTS["fundamental"],
        components=[],
        unavailable_reason="fundamentals_enabled=true pero no hay proveedor implementado",
    )


def _tecnico(snapshot: TechnicalSnapshot) -> Dimension:
    """Confluencia técnica: tendencia, momento y fortaleza relativa."""

    components: List[Component] = []

    if snapshot.ema_fast is None or snapshot.ema_slow is None:
        components.append(Component("cruce de medias", None, 5.0, "histórico insuficiente"))
    elif snapshot.ema_fast > snapshot.ema_slow:
        components.append(Component("cruce de medias", 5.0, 5.0, "EMA rápida por encima de la lenta"))
    else:
        components.append(Component("cruce de medias", 0.0, 5.0, "EMA rápida por debajo de la lenta"))

    if snapshot.sma_long is None:
        components.append(Component("tendencia de fondo", None, 4.0, "histórico insuficiente para la SMA larga"))
    elif snapshot.price > snapshot.sma_long:
        components.append(Component("tendencia de fondo", 4.0, 4.0, "precio por encima de la SMA larga"))
    else:
        components.append(Component("tendencia de fondo", 0.0, 4.0, "precio por debajo de la SMA larga"))

    rsi = snapshot.rsi
    if rsi is None:
        components.append(Component("RSI", None, 4.0, "histórico insuficiente"))
    elif 50 <= rsi <= 70:
        components.append(Component("RSI", 4.0, 4.0, f"RSI {rsi:.0f}, en zona de entrada"))
    elif 45 <= rsi < 50:
        components.append(Component("RSI", 2.0, 4.0, f"RSI {rsi:.0f}, momento aún débil"))
    elif 70 < rsi <= 75:
        components.append(Component("RSI", 1.0, 4.0, f"RSI {rsi:.0f}, cerca de sobrecompra"))
    else:
        components.append(Component("RSI", 0.0, 4.0, f"RSI {rsi:.0f}, fuera de la zona operativa"))

    hist = snapshot.macd_hist
    if hist is None:
        components.append(Component("MACD", None, 4.0, "histórico insuficiente"))
    elif hist > 0:
        components.append(Component("MACD", 4.0, 4.0, "histograma MACD positivo"))
    else:
        components.append(Component("MACD", 0.0, 4.0, "histograma MACD negativo"))

    rs = snapshot.relative_strength
    if rs is None:
        components.append(Component("fortaleza relativa", None, 3.0, "sin índice de referencia comparable"))
    elif rs > 2:
        components.append(Component("fortaleza relativa", 3.0, 3.0, f"bate a su índice en {rs:+.1f} pp"))
    elif rs > 0:
        components.append(Component("fortaleza relativa", 2.0, 3.0, f"bate a su índice en {rs:+.1f} pp"))
    else:
        components.append(Component("fortaleza relativa", 0.0, 3.0, f"por detrás de su índice ({rs:+.1f} pp)"))

    return Dimension("tecnico", WEIGHTS["tecnico"], components)


def _beneficio_riesgo(levels: Levels) -> Dimension:
    """Puntúa el ratio beneficio/riesgo con los tramos de referencia del asesor."""

    rr = levels.rr_ratio
    if rr_at_least(rr, 3.0):
        points, detail = 20.0, f"ratio {rr:.1f}:1 — muy atractivo"
    elif rr_at_least(rr, 2.0):
        points, detail = 15.0, f"ratio {rr:.1f}:1 — atractivo"
    elif rr_at_least(rr, 1.5):
        points, detail = 10.0, f"ratio {rr:.1f}:1 — aceptable"
    elif rr_at_least(rr, 1.0):
        points, detail = 5.0, f"ratio {rr:.1f}:1 — insuficiente"
    else:
        points, detail = 0.0, f"ratio {rr:.1f}:1 — descartable"

    return Dimension(
        "beneficio_riesgo",
        WEIGHTS["beneficio_riesgo"],
        [Component("ratio B/R", points, 20.0, detail)],
    )


def _contexto(context: MarketContext) -> Dimension:
    """Traslada la puntuación del contexto de mercado a una dimensión."""

    return Dimension(
        "contexto",
        WEIGHTS["contexto"],
        [Component("régimen", context.points, 10.0, f"{context.label}: {context.reason}")],
    )


def _conviccion(snapshot: TechnicalSnapshot, min_bars: int) -> Dimension:
    """Calidad de los datos sobre los que se ha construido el análisis.

    No mide el activo: mide cuánto se puede confiar en lo que el bot ha
    calculado sobre él.
    """

    components: List[Component] = []

    coverage = min(1.0, snapshot.bars / min_bars) if min_bars > 0 else 1.0
    components.append(
        Component("histórico", round(4.0 * coverage, 2), 4.0, f"{snapshot.bars} velas ({coverage:.0%} de lo requerido)")
    )

    indicators = [snapshot.ema_fast, snapshot.ema_slow, snapshot.sma_long, snapshot.rsi, snapshot.atr, snapshot.macd_hist]
    present = sum(1 for value in indicators if value is not None)
    components.append(
        Component("indicadores", round(4.0 * present / len(indicators), 2), 4.0, f"{present}/{len(indicators)} disponibles")
    )

    atr_pct = snapshot.atr_pct
    if atr_pct is None:
        components.append(Component("estabilidad", None, 2.0, "sin ATR"))
    elif atr_pct < 3:
        components.append(Component("estabilidad", 2.0, 2.0, f"ATR {atr_pct:.1f}% del precio"))
    elif atr_pct < 6:
        components.append(Component("estabilidad", 1.5, 2.0, f"ATR {atr_pct:.1f}% del precio"))
    elif atr_pct < 10:
        components.append(Component("estabilidad", 1.0, 2.0, f"ATR {atr_pct:.1f}% del precio"))
    else:
        components.append(Component("estabilidad", 0.5, 2.0, f"ATR {atr_pct:.1f}% del precio — muy volátil"))

    return Dimension("conviccion", WEIGHTS["conviccion"], components)


def compute_score(
    snapshot: TechnicalSnapshot,
    levels: Levels,
    context: MarketContext,
    config: ScoringConfig,
    min_bars: int,
) -> Score:
    """Puntúa una oportunidad combinando las seis dimensiones."""

    return Score(
        dimensions=[
            _catalizador(snapshot),
            _fundamental(config),
            _tecnico(snapshot),
            _beneficio_riesgo(levels),
            _contexto(context),
            _conviccion(snapshot, min_bars),
        ]
    )


def suggest_sizing(score: Score, levels: Levels, atr_pct: Optional[float]) -> Tuple[str, float, float]:
    """Porcentaje máximo razonable de cartera para la operación.

    Devuelve ``(etiqueta, mínimo_pct, máximo_pct)``. Los tramos siguen la
    clasificación de convicción del asesor; un activo muy volátil baja un
    escalón porque el mismo porcentaje de cartera implica más riesgo real.
    """

    value = score.value
    if value >= 80 and rr_at_least(levels.rr_ratio, 2.0):
        label, low, high = "Alta convicción", 5.0, 10.0
    elif value >= 70:
        label, low, high = "Convicción media", 2.0, 5.0
    else:
        label, low, high = "Especulativa", 0.5, 2.0

    if atr_pct is not None and atr_pct >= 6.0 and label != "Especulativa":
        if label == "Alta convicción":
            return "Convicción media (rebajada por volatilidad)", 2.0, 5.0
        return "Especulativa (rebajada por volatilidad)", 0.5, 2.0

    return label, low, high
