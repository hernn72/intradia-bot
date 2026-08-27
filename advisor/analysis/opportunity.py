"""Una oportunidad analizada: activo, niveles, puntuación y decisión.

La decisión (``radar`` y ``accion``) es determinista y se calcula aquí, no en
el agente IA. Que una oportunidad con buena puntuación acabe en ESPERAR en
vez de COMPRAR siempre tiene un motivo explícito en ``decision_reasons``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from advisor.analysis.levels import Levels, rr_at_least
from advisor.analysis.market_context import MarketContext
from advisor.analysis.scoring import Score, suggest_sizing
from advisor.analysis.snapshot import TechnicalSnapshot
from advisor.config import RiskConfig, ScoringConfig
from advisor.universe.models import Asset

RADAR_OPERAR = "OPERAR"
RADAR_VIGILAR = "VIGILAR"
RADAR_DESCARTAR = "DESCARTAR"

ACCION_COMPRAR = "COMPRAR"
ACCION_ESPERAR = "ESPERAR"
ACCION_DESCARTAR = "DESCARTAR"

# Tipo de operación asociado a cada horizonte de análisis.
TIPO_OPERACION = {
    "intradia": "⚡ Intradía",
    "swing": "🚀 Swing / corto plazo",
    "medio": "📈 Medio plazo",
}

# Duración orientativa de cada horizonte, para el campo "Horizonte temporal".
DURACION = {
    "intradia": "minutos u horas, dentro de la sesión",
    "swing": "de 2 días a 8 semanas",
    "medio": "de 1 a 12 meses",
}


@dataclass(frozen=True)
class Narrative:
    """Texto redactado por el agente IA. Vacío si la IA está desactivada."""

    tesis: str = ""
    catalizador: str = ""
    que_podria_salir_mal: List[str] = field(default_factory=list)
    escenario_alcista: str = ""
    escenario_base: str = ""
    escenario_bajista: str = ""
    raw: str = ""


@dataclass(frozen=True)
class Opportunity:
    """Resultado completo del análisis de un activo."""

    asset: Asset
    horizonte: str
    snapshot: TechnicalSnapshot
    levels: Levels
    score: Score
    context: MarketContext
    radar: str
    accion: str
    decision_reasons: List[str]
    sizing_label: str
    sizing_min_pct: float
    sizing_max_pct: float
    narrative: Optional[Narrative] = None

    @property
    def tipo_operacion(self) -> str:
        return TIPO_OPERACION.get(self.horizonte, self.horizonte)

    @property
    def duracion(self) -> str:
        return DURACION.get(self.horizonte, "no definida")

    @property
    def confianza(self) -> str:
        """Confianza en el análisis: alta, media o baja.

        Depende de la calidad de los datos y de cuántas dimensiones se han
        podido evaluar, no de lo prometedora que parezca la operación.
        """
        missing = len(self.score.missing_dimensions)
        conviccion = next((d for d in self.score.dimensions if d.name == "conviccion"), None)
        conviccion_ratio = (conviccion.points / conviccion.weight) if conviccion and conviccion.weight else 0.0

        if missing == 0 and conviccion_ratio >= 0.8:
            return "Alta"
        if missing <= 1 and conviccion_ratio >= 0.6:
            return "Media"
        return "Baja"


def classify(
    score: Score,
    levels: Levels,
    context: MarketContext,
    scoring: ScoringConfig,
    risk: RiskConfig,
    asset: Asset,
) -> tuple:
    """Decide radar y acción a partir de criterios objetivos.

    Devuelve ``(radar, accion, motivos)``. Los motivos explican siempre por
    qué una oportunidad no llega a COMPRAR, para que la decisión sea
    auditable y no un veredicto sin justificar.
    """

    reasons: List[str] = []
    value = score.value

    if value < scoring.min_score_vigilar:
        reasons.append(f"puntuación {value:.0f} por debajo del mínimo de vigilancia ({scoring.min_score_vigilar:.0f})")
        return RADAR_DESCARTAR, ACCION_DESCARTAR, reasons

    if not rr_at_least(levels.rr_ratio, risk.min_rr_ratio):
        reasons.append(
            f"ratio beneficio/riesgo {levels.rr_ratio:.1f}:1 por debajo del mínimo exigido "
            f"({risk.min_rr_ratio:.1f}:1)"
        )
        return RADAR_DESCARTAR, ACCION_DESCARTAR, reasons

    if value < scoring.min_score_operar:
        reasons.append(f"puntuación {value:.0f}, insuficiente para operar ({scoring.min_score_operar:.0f})")
        return RADAR_VIGILAR, ACCION_ESPERAR, reasons

    # A partir de aquí la oportunidad es puntuable como operable; lo que
    # queda son vetos por precio, contexto o disponibilidad.
    if levels.chase:
        extension = levels.extension_atr
        reasons.append(
            "ESPERAR PULLBACK / NO PERSEGUIR PRECIO: el precio está "
            f"{extension:.1f}·ATR por encima de su media rápida"
            if extension is not None
            else "ESPERAR PULLBACK / NO PERSEGUIR PRECIO: el precio está extendido"
        )
        return RADAR_VIGILAR, ACCION_ESPERAR, reasons

    if context.is_hostile:
        reasons.append(f"contexto de mercado adverso ({context.reason})")
        return RADAR_VIGILAR, ACCION_ESPERAR, reasons

    if not asset.is_recommendable:
        reasons.append("no disponible en Trade Republic: no puede ejecutarse")
        return RADAR_DESCARTAR, ACCION_DESCARTAR, reasons

    if asset.trade_republic == "unknown":
        reasons.append("disponibilidad en Trade Republic sin verificar: confírmala antes de ejecutar")

    return RADAR_OPERAR, ACCION_COMPRAR, reasons


def build_opportunity(
    asset: Asset,
    horizonte: str,
    snapshot: TechnicalSnapshot,
    levels: Levels,
    score: Score,
    context: MarketContext,
    scoring: ScoringConfig,
    risk: RiskConfig,
) -> Opportunity:
    """Ensambla la oportunidad ya clasificada y dimensionada."""

    radar, accion, reasons = classify(score, levels, context, scoring, risk, asset)
    sizing_label, sizing_min, sizing_max = suggest_sizing(score, levels, snapshot.atr_pct)

    return Opportunity(
        asset=asset,
        horizonte=horizonte,
        snapshot=snapshot,
        levels=levels,
        score=score,
        context=context,
        radar=radar,
        accion=accion,
        decision_reasons=reasons,
        sizing_label=sizing_label,
        sizing_min_pct=sizing_min,
        sizing_max_pct=sizing_max,
    )
