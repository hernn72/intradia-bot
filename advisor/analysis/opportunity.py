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
from advisor.analysis.scoring import Score
from advisor.analysis.sizing import PositionSizing, calculate_position_sizing, conviction_label
from advisor.analysis.snapshot import TechnicalSnapshot
from advisor.config import PortfolioConfig, RiskConfig, ScoringConfig
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
    sizing: PositionSizing
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
    horizonte: str = "",
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
    # queda son vetos por contexto o disponibilidad y advertencias de precio.
    #
    # La extensión sobre la media rápida ADVIERTE pero no veta. Se midió con
    # el backtest (europa, 2y y 5y, 2026-08): como veto dejaba al asesor sin
    # operar (2 señales COMPRAR en 5 años) y las señales que bloqueaba
    # ganaban el 62-67% de las veces con +2,6%/+4,0% de media. La
    # especificación (§14) solo manda ESPERAR cuando el precio subió Y perdió
    # el ratio favorable; la extensión sola no cumple la segunda condición.
    # El veto de ratio de más abajo sigue cubriendo el caso completo.
    if levels.chase:
        extension = levels.extension_atr
        reasons.append(
            "precio extendido "
            + (f"{extension:.1f}·ATR" if extension is not None else "varios ATR")
            + " sobre su media rápida: no persigas, prioriza la zona de entrada ideal o un pullback"
        )

    if context.is_hostile:
        reasons.append(f"contexto de mercado adverso ({context.reason})")
        return RADAR_VIGILAR, ACCION_ESPERAR, reasons

    # En el horizonte medio (meses) existe una alternativa casi sin riesgo
    # que ya renta risk_free_annual_pct: inmovilizar capital y asumir riesgo
    # de mercado solo compensa si el potencial la supera con holgura.
    if horizonte == "medio":
        required_pct = risk.risk_free_annual_pct * risk.risk_free_multiple
        if levels.reward_pct < required_pct:
            reasons.append(
                f"potencial {levels.reward_pct:.1f}% hasta el objetivo 2: no supera con holgura "
                f"la alternativa sin riesgo ({risk.risk_free_annual_pct:.2f}% anual × {risk.risk_free_multiple:g})"
            )
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
    portfolio: PortfolioConfig,
) -> Opportunity:
    """Ensambla la oportunidad ya clasificada y dimensionada."""

    radar, accion, reasons = classify(score, levels, context, scoring, risk, asset, horizonte)
    sizing = calculate_position_sizing(levels, portfolio, conviction_label(score))

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
        sizing=sizing,
    )
