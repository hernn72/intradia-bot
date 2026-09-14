"""Una oportunidad analizada: activo, niveles, puntuación y decisión.

La decisión (``radar`` y ``accion``) es determinista y se calcula aquí, no en
el agente IA. Que una oportunidad con buena puntuación acabe en ESPERAR en
vez de COMPRAR siempre tiene un motivo explícito en ``decision_reasons``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from advisor.analysis.execution import (
    ABOVE_MAX_ENTRY,
    BROKER_UNAVAILABLE,
    BROKER_UNVERIFIED,
    DATA_NOT_EXECUTABLE,
    EXECUTABLE,
    INVALID_STOP,
    INVALID_TARGET,
    POSITION_TOO_SMALL,
    RR_TOO_LOW,
    ExecutionEvaluation,
    evaluate_trade_at_entry,
)
from advisor.analysis.levels import Levels
from advisor.analysis.market_context import MarketContext
from advisor.analysis.scoring import Score
from advisor.analysis.sizing import PositionSizing, conviction_label
from advisor.analysis.snapshot import TechnicalSnapshot
from advisor.config import DataQualityConfig, PortfolioConfig, RiskConfig, ScoringConfig
from advisor.data.freshness import QUALITY_DEGRADED, DataFreshness
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
    setup_radar: str
    setup_accion: str
    setup_reasons: List[str]
    radar: str
    accion: str
    decision_reasons: List[str]
    sizing: PositionSizing
    execution: ExecutionEvaluation
    data_freshness: Optional[DataFreshness] = None
    narrative: Optional[Narrative] = None

    @property
    def tipo_operacion(self) -> str:
        return TIPO_OPERACION.get(self.horizonte, self.horizonte)

    @property
    def duracion(self) -> str:
        return DURACION.get(self.horizonte, "no definida")

    @property
    def signal_label(self) -> str:
        """Calidad de la señal, separada de si el broker permite ejecutarla."""

        if self.setup_radar == RADAR_OPERAR:
            return "🟢 OPERAR"
        if self.setup_radar == RADAR_VIGILAR:
            return "🟡 VIGILAR"
        return "🔴 DESCARTAR"

    @property
    def broker_execution_label(self) -> str:
        """Estado operativo en el broker, sin contaminar la puntuación."""

        if self.asset.trade_republic == "yes":
            return "✅ disponible verificado"
        if self.asset.trade_republic == "no":
            return "⛔ no disponible"
        return "❓ pendiente de verificación"

    @property
    def executable_in_broker(self) -> bool:
        """Solo un 'yes' explícito permite hablar de ejecución confirmada."""

        return self.asset.trade_republic == "yes"

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
    data_freshness: Optional[DataFreshness] = None,
    data_quality: Optional[DataQualityConfig] = None,
    portfolio: Optional[PortfolioConfig] = None,
) -> tuple:
    """Decide radar y acción a partir de criterios objetivos.

    Devuelve ``(radar, accion, motivos)``. Los motivos explican siempre por
    qué una oportunidad no llega a COMPRAR, para que la decisión sea
    auditable y no un veredicto sin justificar.
    """

    setup_radar, setup_accion, reasons = classify_setup(score, levels, context, scoring, risk, horizonte)
    if setup_accion != ACCION_COMPRAR:
        return setup_radar, setup_accion, reasons

    if data_freshness is not None and data_freshness.quality == QUALITY_DEGRADED:
        reasons.extend(data_freshness.quality_reasons)

    execution = evaluate_trade_at_entry(
        levels=levels,
        entry_price=levels.price,
        risk=risk,
        portfolio=portfolio or PortfolioConfig(),
        label="clasificación",
        asset=asset,
        data_freshness=data_freshness,
        data_quality=data_quality,
    )
    if not execution.executable:
        reasons.extend(_execution_reasons(execution, risk, data_freshness))
        return RADAR_VIGILAR, ACCION_ESPERAR, reasons
    if execution.reason == BROKER_UNVERIFIED:
        reasons.extend(_execution_reasons(execution, risk, data_freshness))

    return RADAR_OPERAR, ACCION_COMPRAR, reasons


def classify_setup(
    score: Score,
    levels: Levels,
    context: MarketContext,
    scoring: ScoringConfig,
    risk: RiskConfig,
    horizonte: str = "",
) -> tuple:
    """Clasifica la calidad del setup sin vetos de ejecutabilidad."""

    reasons: List[str] = []
    value = score.value

    if value < scoring.min_score_vigilar:
        reasons.append(f"puntuación {value:.0f} por debajo del mínimo de vigilancia ({scoring.min_score_vigilar:.0f})")
        return RADAR_DESCARTAR, ACCION_DESCARTAR, reasons

    if value < scoring.min_score_operar:
        reasons.append(f"puntuación {value:.0f}, insuficiente para operar ({scoring.min_score_operar:.0f})")
        return RADAR_VIGILAR, ACCION_ESPERAR, reasons

    # La extensión sobre la media rápida ADVIERTE pero no veta. Se midió con
    # el backtest (europa, 2y y 5y, 2026-08): como veto dejaba al asesor sin
    # operar (2 señales COMPRAR en 5 años) y las señales que bloqueaba
    # ganaban el 62-67% de las veces con +2,6%/+4,0% de media. La
    # especificación (§14) solo manda ESPERAR cuando el precio subió Y perdió
    # el ratio favorable; la extensión sola no cumple la segunda condición.
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

    return RADAR_OPERAR, ACCION_COMPRAR, reasons


def _execution_reasons(
    execution: ExecutionEvaluation,
    risk: RiskConfig,
    data_freshness: Optional[DataFreshness] = None,
) -> List[str]:
    """Traduce el estado de ejecución a motivos legibles."""

    reason = execution.reason
    if reason == EXECUTABLE:
        return []
    if reason == ABOVE_MAX_ENTRY:
        return [
            f"precio de entrada {execution.entry_price:.2f} por encima de la entrada máxima "
            f"{execution.entry_max:.2f}: NO_CHASE"
        ]
    if reason == RR_TOO_LOW:
        rr = 0.0 if execution.rr is None else execution.rr
        return [
            f"ratio beneficio/riesgo {rr:.1f}:1 al precio de entrada por debajo del mínimo exigido "
            f"({risk.min_rr_ratio:.1f}:1)"
        ]
    if reason == INVALID_STOP:
        return ["stop inválido para el precio de entrada: riesgo no calculable"]
    if reason == INVALID_TARGET:
        return ["objetivo inválido para el precio de entrada: potencial no positivo"]
    if reason == POSITION_TOO_SMALL:
        return ["posición demasiado pequeña para ejecutarse con el riesgo configurado"]
    if reason == DATA_NOT_EXECUTABLE:
        quality = list(data_freshness.quality_reasons) if data_freshness is not None else []
        return [*quality, "apertura vetada por calidad del dato INCOMPLETO; la puntuación se conserva sin ajustar"]
    if reason == BROKER_UNVERIFIED:
        return ["disponibilidad en Trade Republic sin verificar: confírmala antes de ejecutar"]
    if reason == BROKER_UNAVAILABLE:
        return ["no disponible en Trade Republic: no puede ejecutarse"]
    return [f"ejecución no válida: {reason}"]


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
    data_quality: Optional[DataQualityConfig] = None,
    data_freshness: Optional[DataFreshness] = None,
) -> Opportunity:
    """Ensambla la oportunidad ya clasificada y dimensionada."""

    label = conviction_label(score)
    setup_radar, setup_accion, setup_reasons = classify_setup(score, levels, context, scoring, risk, horizonte)
    radar, accion, reasons = classify(
        score,
        levels,
        context,
        scoring,
        risk,
        asset,
        horizonte,
        data_freshness,
        data_quality,
        portfolio,
    )
    execution = evaluate_trade_at_entry(
        levels=levels,
        entry_price=levels.price,
        risk=risk,
        portfolio=portfolio,
        label=label,
        asset=asset,
        data_freshness=data_freshness,
        data_quality=data_quality,
    )
    sizing = execution.position_size

    return Opportunity(
        asset=asset,
        horizonte=horizonte,
        snapshot=snapshot,
        levels=levels,
        score=score,
        context=context,
        setup_radar=setup_radar,
        setup_accion=setup_accion,
        setup_reasons=setup_reasons,
        radar=radar,
        accion=accion,
        decision_reasons=reasons,
        sizing=sizing,
        execution=execution,
        data_freshness=data_freshness,
    )
