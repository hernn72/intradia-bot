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
from advisor.data.quality import (
    INVALID_INDICATORS as QUALITY_INVALID_INDICATORS,
)
from advisor.data.quality import (
    MISSING_RECENT_DATA,
    PARTIAL_BAR,
    STALE_DATA,
    DataQuality,
)
from advisor.universe.models import Asset

RADAR_OPERAR = "OPERAR"
RADAR_VIGILAR = "VIGILAR"
RADAR_DESCARTAR = "DESCARTAR"

ACCION_COMPRAR = "COMPRAR"
ACCION_ESPERAR = "ESPERAR"
ACCION_DESCARTAR = "DESCARTAR"

LOW_SCORE = "LOW_SCORE"
INVALID_TREND = "INVALID_TREND"
OVEREXTENDED = "OVEREXTENDED"
VOLATILITY_TOO_HIGH = "VOLATILITY_TOO_HIGH"
EVENT_RISK = "EVENT_RISK"
HOSTILE_CONTEXT = "HOSTILE_CONTEXT"
BELOW_RISK_FREE = "BELOW_RISK_FREE"
NO_LEVELS = "NO_LEVELS"
INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
INVALID_INDICATORS = "INVALID_INDICATORS"
# Para el fallo que no se ha sabido clasificar. Existe porque atribuirlo a
# INVALID_INDICATORS afirmaba una causa técnica que nadie había comprobado:
# un 404 del proveedor, un timeout de red o una plaza sin calendario se
# publicaban como indicadores inválidos (INV-16).
ANALYSIS_ERROR = "ANALYSIS_ERROR"

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
    data_quality: Optional[DataQuality] = None
    discard_code: Optional[str] = None
    execution_code: str = EXECUTABLE
    warnings: tuple[str, ...] = field(default_factory=tuple)
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


@dataclass(frozen=True)
class SetupClassification:
    radar: str
    accion: str
    reasons: List[str]
    discard_code: Optional[str]
    warnings: tuple[str, ...] = ()


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

    setup = classify_setup_detailed(score, levels, context, scoring, risk, horizonte)
    setup_radar, setup_accion, reasons = setup.radar, setup.accion, list(setup.reasons)
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

    result = classify_setup_detailed(score, levels, context, scoring, risk, horizonte)
    return result.radar, result.accion, result.reasons


def classify_setup_detailed(
    score: Score,
    levels: Levels,
    context: MarketContext,
    scoring: ScoringConfig,
    risk: RiskConfig,
    horizonte: str = "",
) -> SetupClassification:
    """Clasifica la calidad del setup y asigna código estructurado."""

    reasons: List[str] = []
    warnings: list[str] = []
    value = score.value

    if value < scoring.min_score_vigilar:
        reasons.append(
            f"puntuación {value:.0f} por debajo del mínimo de vigilancia "
            f"({scoring.min_score_vigilar:.0f}); code={LOW_SCORE}; threshold={scoring.min_score_vigilar:.0f}"
        )
        return SetupClassification(RADAR_DESCARTAR, ACCION_DESCARTAR, reasons, LOW_SCORE)

    if value < scoring.min_score_operar:
        reasons.append(
            f"puntuación {value:.0f}, insuficiente para operar "
            f"({scoring.min_score_operar:.0f}); code={LOW_SCORE}; threshold={scoring.min_score_operar:.0f}"
        )
        return SetupClassification(RADAR_VIGILAR, ACCION_ESPERAR, reasons, LOW_SCORE)

    # La extensión sobre la media rápida ADVIERTE pero no veta. Se midió con
    # el backtest (europa, 2y y 5y, 2026-08): como veto dejaba al asesor sin
    # operar (2 señales COMPRAR en 5 años) y las señales que bloqueaba
    # ganaban el 62-67% de las veces con +2,6%/+4,0% de media. La
    # especificación (§14) solo manda ESPERAR cuando el precio subió Y perdió
    # el ratio favorable; la extensión sola no cumple la segunda condición.
    if levels.chase:
        extension = levels.extension_atr
        warnings.append(
            "precio extendido "
            + (f"{extension:.1f}·ATR" if extension is not None else "varios ATR")
            + " sobre su media rápida: no persigas, prioriza la zona de entrada ideal o un pullback"
        )

    if context.is_hostile:
        reasons.append(f"contexto de mercado adverso ({context.reason})")
        return SetupClassification(RADAR_VIGILAR, ACCION_ESPERAR, reasons, HOSTILE_CONTEXT, tuple(warnings))

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
            return SetupClassification(RADAR_VIGILAR, ACCION_ESPERAR, reasons, BELOW_RISK_FREE, tuple(warnings))

    return SetupClassification(RADAR_OPERAR, ACCION_COMPRAR, reasons, None, tuple(warnings))


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
    setup = classify_setup_detailed(score, levels, context, scoring, risk, horizonte)
    setup_radar, setup_accion, setup_reasons = setup.radar, setup.accion, setup.reasons
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
        data_quality=data_freshness.data_quality if data_freshness is not None else None,
        discard_code=_discard_code(setup),
        execution_code=_execution_code(execution, data_freshness),
        warnings=setup.warnings,
    )


def _discard_code(setup: SetupClassification) -> Optional[str]:
    """Por qué cayó el **setup**, que es lo que agrupa el bloque DESCARTADOS.

    Son dos preguntas distintas y antes se mezclaban: el código de calidad se
    devolvía por delante del del setup, así que un activo descartado por nota
    baja aparecía etiquetado `STALE_DATA`, y la misma línea del informe llegaba
    a imprimir `[MISSING_RECENT_DATA]` en el marcador y `code=LOW_SCORE` en el
    texto. El estado del dato no descarta un setup: impide ejecutarlo, y eso
    vive en ``execution_code``.
    """

    return setup.discard_code


def _execution_code(
    execution: ExecutionEvaluation,
    data_freshness: Optional[DataFreshness],
) -> str:
    """Por qué no se puede ejecutar, con el motivo del dato si es el que manda."""

    quality_code = _data_quality_blocking_code(data_freshness)
    if quality_code is not None:
        return quality_code
    return execution.reason


def _data_quality_blocking_code(data_freshness: Optional[DataFreshness]) -> Optional[str]:
    if data_freshness is None or data_freshness.data_quality is None:
        return None
    data_quality = data_freshness.data_quality
    if data_quality.execution_readiness:
        return None
    if not data_quality.indicator_readiness:
        return INVALID_INDICATORS
    for preferred in (QUALITY_INVALID_INDICATORS, MISSING_RECENT_DATA, STALE_DATA, PARTIAL_BAR):
        if any(reason.code == preferred for reason in data_quality.reasons):
            return INVALID_INDICATORS if preferred == QUALITY_INVALID_INDICATORS else preferred
    return DATA_NOT_EXECUTABLE
