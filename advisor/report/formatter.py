"""Formato de texto del informe del asesor.

Dos salidas:

- ``format_opportunity``: la ficha completa de una recomendación.
- ``format_report``: el informe diario (situación global, tabla de
  oportunidades, fichas, radar y conclusión).

Todos los importes pasan por ``MoneyFormatter``, de modo que cualquier precio
que aparezca en una recomendación es legible en euros.
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime
from typing import List, Optional

import pandas as pd

from advisor.analysis.analyzer import AnalysisResult
from advisor.analysis.opportunity import (
    ACCION_COMPRAR,
    RADAR_DESCARTAR,
    RADAR_OPERAR,
    RADAR_VIGILAR,
    Opportunity,
)
from advisor.analysis.overview import REGION_ORDER, IndexQuote
from advisor.config import AdvisorConfig, PortfolioConfig
from advisor.data.freshness import (
    DataFreshness,
    FreshnessBucket,
    FreshnessRow,
    agrupar_frescura_por_fecha,
    calcular_frescura_dato,
    classify_data_quality,
    mercado_para_simbolo,
)
from advisor.data.fx import FxConverter
from advisor.events.calendar import EventCalendar
from advisor.events.models import TIPO_BANCO_CENTRAL, TIPO_RESULTADOS, MarketEvent
from advisor.report.money import MoneyFormatter

WIDTH = 90
_SEPARATOR = "=" * WIDTH
_THIN = "-" * WIDTH
logger = logging.getLogger(__name__)

_REGION_LABEL = {
    "ASIA": "Asia",
    "EUROPA": "Europa",
    "USA": "EE. UU.",
    "GLOBAL": "Global",
    "EMERGING_MARKETS": "Emergentes",
}


# Un evento deja de ser contexto y pasa a ser riesgo cuando cae dentro del
# plazo en el que la operación sigue abierta. El de banco central es más
# corto porque mueve el mercado entero un solo día.
_RESULTADOS_INMINENTES_DIAS = 10
_BANCO_CENTRAL_INMINENTE_DIAS = 3


def _pct(value: Optional[float], decimals: int = 1) -> str:
    if value is None:
        return "N/D"
    return f"{value:+.{decimals}f}%".replace(".", ",")


def _num(value: Optional[float], decimals: int = 1) -> str:
    if value is None:
        return "N/D"
    return f"{value:.{decimals}f}".replace(".", ",")


def _quote_line(quote: IndexQuote) -> str:
    if not quote.available:
        return f"{quote.name} ({quote.symbol}): datos no disponibles"
    return f"{quote.name} ({quote.symbol}): {_num(quote.price, 2)} {quote.currency} {_pct(quote.change_pct)}"


def format_overview(quotes: List[IndexQuote]) -> str:
    """Sección de situación global, agrupada por región."""

    if not quotes:
        return "Sin índices de contexto configurados en el universo."

    lines: List[str] = []
    for region in REGION_ORDER:
        region_quotes = [q for q in quotes if q.region == region]
        if not region_quotes:
            continue
        lines.append(f"{_REGION_LABEL.get(region, region)}:")
        for quote in region_quotes:
            lines.append(f"  - {_quote_line(quote)}")
    return "\n".join(lines)


def format_opportunity(
    opportunity: Opportunity,
    fx: FxConverter,
    reference: datetime,
    eventos: Optional[List[MarketEvent]] = None,
    portfolio: Optional[PortfolioConfig] = None,
) -> str:
    """Ficha completa de una recomendación."""

    asset = opportunity.asset
    levels = opportunity.levels
    snapshot = opportunity.snapshot
    score = opportunity.score
    money = MoneyFormatter(fx, asset.currency)

    target_pcts = levels.target_pcts

    lines: List[str] = []
    lines.append(f"## {asset.name}")
    lines.append("")
    lines.append(f"**Ticker:** {asset.symbol}")
    if asset.european_symbol is not None:
        lines.append(f"**Ticker europeo:** {asset.european_symbol}")
    lines.append(f"**ISIN:** {asset.isin_label}")
    lines.append(f"**Mercado de datos:** {asset.market} ({_REGION_LABEL.get(asset.region, asset.region)})")
    lines.append(f"**Divisa de cotización:** {asset.currency}")
    lines.append(f"**Exposición económica:** {asset.economic_currency}")
    lines.append(f"**Broker / ejecución:** {asset.broker} / {asset.execution_mode}")
    lines.append(f"**Disponible en Trade Republic:** {asset.availability_label}")
    lines.append("")
    lines.append(f"**Precio actual:** {money(snapshot.price)}")
    lines.append(f"**Tipo de operación:** {opportunity.tipo_operacion}")
    lines.append(f"**Señal:** {opportunity.signal_label}")
    lines.append(f"**Ejecutabilidad en broker:** {opportunity.broker_execution_label}")
    freshness = _freshness_for_opportunity(opportunity, reference)
    lines.append(
        f"**Datos de mercado:** {freshness.quality}; última barra {freshness.last_bar_date.isoformat()} "
        f"({freshness.label})"
    )
    if freshness.session_close_status:
        lines.append(f"**Cierre de sesión:** {freshness.session_close_status}")
    if freshness.sessions_approx >= 1:
        lines.append(
            "⚠️ Dato retrasado: esta recomendación usa una última barra con "
            f"{freshness.sessions_approx} sesiones cerradas aproximadas perdidas."
        )
    if freshness.absent_recent_sessions:
        lines.append(
            "⚠️ Calidad INCOMPLETO: faltan sesiones recientes del calendario "
            f"{freshness.calendar}: {_dates_label(freshness.absent_recent_sessions)}."
        )
    for reason in freshness.quality_reasons:
        if reason.startswith("INCOMPLETO"):
            continue
        lines.append(f"⚠️ Calidad {reason}")
    if freshness.may_be_partial_current_session:
        lines.append(
            "⚠️ Barra potencialmente parcial: la última barra es de hoy y puede no ser un cierre."
        )
    lines.append(
        f"**Puntuación:** {score.value:.0f}/100 ({score.grade})"
        + (
            f" — calculada sobre {score.evaluable_max:.0f} puntos evaluables"
            if score.missing_dimensions
            else ""
        )
    )
    lines.append("")

    lines.append("### Tesis")
    narrative = opportunity.narrative
    if narrative and narrative.tesis:
        lines.append(narrative.tesis)
    else:
        lines.append(_default_thesis(opportunity))
    lines.append("")

    lines.append("### Catalizador")
    if narrative and narrative.catalizador:
        lines.append(narrative.catalizador)
    else:
        lines.append(_default_catalyst(opportunity))
    lines.append("")

    lines.append("### Entrada")
    lines.append(f"Zona de entrada ideal: {money(levels.entry_ideal_low)} — {money(levels.entry_ideal_high)}")
    lines.append(f"Entrada máxima aceptable: {money(levels.entry_max)}")
    if levels.chase:
        lines.append("⚠️ ESPERAR PULLBACK / NO PERSEGUIR PRECIO — el precio está extendido sobre su media rápida.")
    lines.append("")

    lines.append("### Stop / invalidación")
    lines.append(f"Stop de precio: {money(levels.stop)} ({levels.stop_basis})")
    if levels.invalidation_level is not None:
        lines.append(f"Invalidación de la tesis: {money(levels.invalidation_level)} — {levels.invalidation_reason}")
    else:
        lines.append(f"Invalidación de la tesis: {levels.invalidation_reason}")
    lines.append(f"Pérdida máxima estimada desde el precio actual: {_pct(-levels.risk_pp)}")
    lines.append("")

    lines.append("### Objetivos")
    lines.append(f"Objetivo 1: {money(levels.target1)}  ({_pct(target_pcts[0])})")
    lines.append(f"Objetivo 2: {money(levels.target2)}  ({_pct(target_pcts[1])})")
    lines.append(f"Objetivo 3: {money(levels.target3)}  ({_pct(target_pcts[2])})")
    lines.append("")

    lines.append(f"### Potencial\n{_pct(levels.reward_pct)} hasta el objetivo 2 (escenario principal)")
    lines.append("")
    lines.append(f"### Riesgo\n{_pct(-levels.risk_pp)} hasta el stop")
    lines.append("")
    lines.append(f"### Ratio beneficio/riesgo\n{_num(levels.rr_ratio, 1)} : 1")
    lines.append("")
    lines.append(f"### Horizonte temporal\n{opportunity.duracion}")
    lines.append("")
    lines.append(f"### Confianza\n{opportunity.confianza}")
    lines.append("")

    lines.append("### Próximo evento importante")
    if eventos:
        hoy = opportunity.snapshot.timestamp.date()
        for evento in eventos:
            dias = evento.dias_hasta(hoy)
            cuando = "hoy" if dias == 0 else ("mañana" if dias == 1 else f"en {dias} días")
            lines.append(f"  - {evento.fecha.isoformat()} ({cuando}) — {evento.titulo} [{evento.etiqueta_fuente}]")
            if evento.detalle:
                lines.append(f"      {evento.detalle}")
    else:
        lines.append("Ninguno con fecha conocida en la ventana consultada.")
    lines.append("")

    lines.append("### Escenarios")
    if narrative and (narrative.escenario_alcista or narrative.escenario_base or narrative.escenario_bajista):
        if narrative.escenario_alcista:
            lines.append(f"Alcista: {narrative.escenario_alcista}")
        if narrative.escenario_base:
            lines.append(f"Base: {narrative.escenario_base}")
        if narrative.escenario_bajista:
            lines.append(f"Bajista: {narrative.escenario_bajista}")
    else:
        lines.append(f"Alcista: el precio alcanza el objetivo 3 ({money(levels.target3)}, {_pct(target_pcts[2])}).")
        lines.append(f"Base: el precio alcanza el objetivo 2 ({money(levels.target2)}, {_pct(target_pcts[1])}).")
        lines.append(f"Bajista: se activa el stop en {money(levels.stop)} ({_pct(-levels.risk_pp)}).")
        lines.append(
            "Sin datos de probabilidad histórica de cada escenario: el bot no estima probabilidades que no ha medido."
        )
    lines.append("")

    lines.append("### Qué podría salir mal")
    risks = list(narrative.que_podria_salir_mal) if narrative and narrative.que_podria_salir_mal else []
    if not risks:
        risks = _default_risks(opportunity)
    # Este riesgo se añade siempre, venga o no narrativa de la IA: es un
    # hecho con fecha, no una opinión, y entrar días antes de unos resultados
    # convierte la operación en una apuesta binaria que ninguna configuración
    # técnica controla.
    risks.extend(_risk_por_eventos(eventos, opportunity))
    for risk in risks:
        lines.append(f"  - {risk}")
    lines.append("")

    lines.append("### Dimensionamiento sugerido")
    sizing = opportunity.sizing
    execution = opportunity.execution
    lines.append(
        f"{sizing.label}: {_num(sizing.position_pct)}% de la cartera, arriesgando "
        f"{_num(sizing.risk_pct, 2)}% si salta el stop."
    )
    if sizing.capped_by is not None:
        lines.append(
            f"El {sizing.capped_by} limita la posición; sin tope serían "
            f"{_num(sizing.uncapped_position_pct)}% de la cartera."
        )
    if portfolio is not None and portfolio.capital is not None:
        capital_native = fx.from_base(portfolio.capital, asset.currency)
        if capital_native is None:
            lines.append(
                f"Capital configurado en {fx.base_currency}, pero no hay tipo de cambio para {asset.currency}: "
                "no se calcula un número de acciones."
            )
        else:
            max_position_value = capital_native * sizing.position_pct / 100
            shares = math.floor(max_position_value / execution.entry_price) if execution.entry_price > 0 else 0
            if shares == 0:
                lines.append("Con el capital configurado no alcanza para comprar una acción al precio de referencia.")
            else:
                position_value = shares * execution.entry_price
                risk_per_share = execution.entry_price - levels.stop
                risk_amount = shares * risk_per_share if risk_per_share > 0 else 0.0
                risk_pct = fx.to_base(risk_amount, asset.currency)
                risk_pct = risk_pct / portfolio.capital * 100 if risk_pct is not None else None
                risk_text = f" ({_num(risk_pct, 2)}% de la cartera)" if risk_pct is not None else ""
                lines.append(
                    f"{shares} acciones; posición {money(position_value)}; "
                    f"riesgo si salta el stop {money(risk_amount)}{risk_text}."
                )
    lines.append(
        f"Cálculo hecho con entrada de referencia {money(execution.entry_price)}; si introduces otro precio en "
        "Trade Republic, recalcula el tamaño."
    )
    lines.append("")

    lines.append("### Desglose de la puntuación")
    for dimension in score.dimensions:
        if not dimension.available:
            lines.append(f"  - {dimension.name}: excluida — {dimension.unavailable_reason}")
            continue
        lines.append(f"  - {dimension.name}: {dimension.points:.1f}/{dimension.weight:.0f}")
        for component in dimension.components:
            if component.detail:
                marker = "·" if component.points is not None else "×"
                lines.append(f"      {marker} {component.name}: {component.detail}")
    lines.append("")

    lines.append(f"### Acción\n**{opportunity.accion}**")
    lines.append(f"**Señal:** {opportunity.signal_label}")
    lines.append(f"**Disponibilidad:** {opportunity.broker_execution_label}")
    for reason in opportunity.decision_reasons:
        lines.append(f"  - {reason}")
    # Las advertencias no descartan, pero tienen que verse: el aviso de precio
    # extendido salió de los motivos de descarte y se quedó sin imprimir en
    # ninguna parte, que es como borrarlo.
    for warning in opportunity.warnings:
        lines.append(f"  ⚠️ {warning}")

    return "\n".join(lines)


def _default_thesis(opportunity: Opportunity) -> str:
    """Tesis construida con los datos calculados, cuando la IA está desactivada."""

    snapshot = opportunity.snapshot
    parts: List[str] = []
    if snapshot.trend_up:
        parts.append("el activo mantiene estructura alcista (EMA rápida sobre la lenta y precio sobre la SMA larga)")
    elif snapshot.ema_fast is not None and snapshot.ema_slow is not None and snapshot.ema_fast > snapshot.ema_slow:
        parts.append("las medias cortas apuntan al alza aunque el precio no supera su tendencia de fondo")
    else:
        parts.append("la estructura de medias todavía no acompaña")

    if snapshot.rsi is not None:
        parts.append(f"con el RSI en {snapshot.rsi:.0f}")
    if snapshot.relative_strength is not None:
        comparison = "por delante de" if snapshot.relative_strength > 0 else "por detrás de"
        parts.append(f"y {comparison} su índice de referencia ({snapshot.relative_strength:+.1f} pp)")

    parts.append(
        f". El planteamiento arriesga un {opportunity.levels.risk_pp:.1f}% para buscar un "
        f"{opportunity.levels.reward_pct:.1f}%, un ratio de {opportunity.levels.rr_ratio:.1f}:1"
    )
    return " ".join(parts).replace(" .", ".")


def _default_catalyst(opportunity: Opportunity) -> str:
    """Catalizador deducible del precio, cuando la IA está desactivada."""

    catalizador = next((d for d in opportunity.score.dimensions if d.name == "catalizador"), None)
    if catalizador is None or not catalizador.available:
        return "Sin catalizador observable en el precio."

    details = [c.detail for c in catalizador.components if c.points is not None and c.points > 0 and c.detail]
    if not details:
        return (
            "Sin catalizador observable en el precio. Este bot no consulta noticias, resultados ni "
            "eventos macro: si existe un catalizador externo, no está recogido aquí."
        )
    return (
        "Huella en el precio: " + "; ".join(details) + ". "
        "El bot no consulta noticias ni resultados, así que la causa de fondo no está verificada."
    )


def _risk_por_eventos(eventos: Optional[List[MarketEvent]], opportunity: Opportunity) -> List[str]:
    """Riesgos que salen del calendario, no del precio."""

    if not eventos:
        return []
    hoy = opportunity.snapshot.timestamp.date()
    avisos: List[str] = []
    for evento in eventos:
        dias = evento.dias_hasta(hoy)
        if evento.tipo == TIPO_RESULTADOS and dias <= _RESULTADOS_INMINENTES_DIAS:
            cuando = "hoy" if dias == 0 else ("mañana" if dias == 1 else f"dentro de {dias} días")
            avisos.append(
                f"Publica resultados {cuando} ({evento.fecha.isoformat()}): el precio se moverá por la "
                "publicación y no por la configuración técnica que motiva esta entrada."
            )
        elif evento.tipo == TIPO_BANCO_CENTRAL and dias <= _BANCO_CENTRAL_INMINENTE_DIAS:
            avisos.append(
                f"{evento.titulo} el {evento.fecha.isoformat()}: un cambio de tipos mueve todo el mercado "
                "a la vez, con independencia del activo."
            )
    return avisos


def _default_risks(opportunity: Opportunity) -> List[str]:
    """Riesgos derivados de lo que el propio análisis ha medido."""

    risks: List[str] = []
    snapshot = opportunity.snapshot
    context = opportunity.context

    atr_pct = snapshot.atr_pct
    if atr_pct is not None and atr_pct >= 4:
        risks.append(f"Volatilidad elevada (ATR = {atr_pct:.1f}% del precio): el stop puede activarse por ruido.")
    if context.vix_value is not None and context.vix_value >= context.vix_threshold:
        risks.append(f"VIX en {context.vix_value:.1f}, por encima del umbral de {context.vix_threshold:.1f}.")
    if snapshot.rsi is not None and snapshot.rsi > 70:
        risks.append(f"RSI en {snapshot.rsi:.0f}: entrada en zona de sobrecompra.")
    if opportunity.asset.trade_republic != "yes":
        risks.append("Disponibilidad en Trade Republic sin confirmar: la operación puede no ser ejecutable.")
    if opportunity.score.missing_dimensions:
        risks.append(
            "Análisis sin dimensión "
            + ", ".join(opportunity.score.missing_dimensions)
            + ": la puntuación no recoge ese factor."
        )
    if not risks:
        risks.append("Ningún riesgo destacado en los datos medidos; siguen aplicando los riesgos de mercado generales.")
    return risks


def _opportunity_row(opportunity: Opportunity, fx: FxConverter) -> str:
    money = MoneyFormatter(fx, opportunity.asset.currency)
    levels = opportunity.levels
    return (
        f"| {opportunity.asset.symbol:<10} "
        f"| {opportunity.tipo_operacion:<22} "
        f"| {money.compact(levels.price):>16} "
        f"| {money.compact(levels.entry_max):>16} "
        f"| {money.compact(levels.target2):>16} "
        f"| {money.compact(levels.stop):>16} "
        f"| {_pct(levels.reward_pct):>8} "
        f"| {_pct(-levels.risk_pp):>8} "
        f"| {opportunity.score.value:>5.0f} |"
    )


def _opportunity_table(opportunities: List[Opportunity], fx: FxConverter) -> str:
    header = (
        f"| {'Activo':<10} | {'Tipo':<22} | {'Precio':>16} | {'Entrada máx.':>16} "
        f"| {'Objetivo 2':>16} | {'Stop':>16} | {'Potenc.':>8} | {'Riesgo':>8} | {'Score':>5} |"
    )
    divider = (
        f"|{'-' * 12}|{'-' * 24}|{'-' * 18}|{'-' * 18}|{'-' * 18}|{'-' * 18}|{'-' * 10}|{'-' * 10}|{'-' * 7}|"
    )
    rows = [_opportunity_row(o, fx) for o in opportunities]
    return "\n".join([header, divider, *rows])


def _fx_footnote(fx: FxConverter, opportunities: List[Opportunity]) -> Optional[str]:
    """Nota al pie sobre el tipo de cambio, solo si se ha usado alguno."""

    currencies = {o.asset.currency for o in opportunities if fx.needs_conversion(o.asset.currency)}
    if not currencies:
        return None

    parts: List[str] = []
    for currency in sorted(currencies):
        rate = fx.rate(currency)
        if rate is None:
            parts.append(f"{currency}: tipo de cambio no disponible")
        else:
            parts.append(f"1 {currency} ≈ {rate:.4f} {fx.base_currency}".replace(".", ","))

    as_of = f" (cierre del {fx.as_of:%Y-%m-%d})" if fx.as_of is not None else ""
    return (
        "Conversión a euros aproximada" + as_of + " — " + "; ".join(parts) + ". "
        "El importe que aplicará Trade Republic al ejecutar puede diferir."
    )


def format_report(
    result: AnalysisResult,
    config: AdvisorConfig,
    fx: FxConverter,
    calendar: Optional[EventCalendar] = None,
) -> str:
    """Informe diario completo."""

    operar = result.by_radar(RADAR_OPERAR)
    vigilar = result.by_radar(RADAR_VIGILAR)
    descartar = result.by_radar(RADAR_DESCARTAR)

    lines: List[str] = []
    lines.append(_SEPARATOR)
    lines.append(
        f"ASESOR DE INVERSIÓN — {result.generated_at:%Y-%m-%d %H:%M} UTC"
        f"  |  horizonte: {result.horizonte}  |  velas: {result.interval}"
    )
    lines.append(_SEPARATOR)
    lines.append("")

    lines.append("## 🌍 SITUACIÓN GLOBAL")
    lines.append("")
    lines.append(format_overview(result.overview))
    lines.append("")
    vix = result.context.vix_value
    lines.append(
        f"Volatilidad: VIX {_num(vix, 1) if vix is not None else 'N/D'}"
        f" (umbral {_num(result.context.vix_threshold, 1)})  |  Contexto: {result.context.label}"
        f" — {result.context.reason}"
    )
    lines.append("")
    lines.append(_report_freshness_summary(result.opportunities, result.generated_at))
    lines.append(
        "Cierre de barras: se descarta la última barra diaria si no ha pasado el cierre regular local "
        f"+ {config.data_quality.settlement_minutes} min. Las ausencias se validan contra el calendario "
        "de plaza con festivos; cripto no tiene sesión de cierre."
    )
    lines.append("")

    lines.append("## 🔥 OPORTUNIDADES DETECTADAS")
    lines.append("")
    if operar:
        lines.append(_opportunity_table(operar[: config.report.top_n], fx))
    else:
        lines.append("Ninguna oportunidad cumple hoy los criterios de entrada.")
    lines.append("")

    if operar:
        for opportunity in operar[: config.report.top_n]:
            lines.append(_THIN)
            # Los eventos se consultan solo de lo que se imprime: el
            # calendario de resultados es una llamada de red por activo y el
            # universo tiene más de cien.
            eventos = (
                calendar.proximos(opportunity.asset.symbol, dias=config.events.ventana_dias)
                if calendar is not None
                else None
            )
            lines.append(format_opportunity(opportunity, fx, result.generated_at, eventos, config.portfolio))
            lines.append("")

    lines.append("## 👀 RADAR")
    lines.append("")
    if vigilar:
        for opportunity in vigilar[: config.report.top_n * 2]:
            reason = opportunity.decision_reasons[0] if opportunity.decision_reasons else "sin motivo registrado"
            lines.append(
                f"  - {opportunity.asset.symbol} ({opportunity.asset.name}) — "
                f"score {opportunity.score.value:.0f}, ratio {_num(opportunity.levels.rr_ratio)}:1"
                f"{_compact_freshness_marker(opportunity, result.generated_at)}"
                f"{_code_marker(opportunity.discard_code or opportunity.execution_code)} — {reason}"
            )
    else:
        lines.append("Sin activos en vigilancia.")
    lines.append("")

    lines.append("## 🔴 DESCARTADOS")
    lines.append("")
    if descartar:
        lines.append(f"{len(descartar)} activos descartados por código:")
        for code, grouped in _group_discarded_by_code(descartar).items():
            symbols = ", ".join(opportunity.asset.symbol for opportunity in grouped)
            lines.append(f"  - {code}: {len(grouped)} activos — {symbols}")
    else:
        lines.append("Ninguno.")
    if result.skipped:
        lines.append("")
        lines.append("No analizados por falta de datos:")
        for skipped in result.skipped:
            lines.append(f"  - {skipped.symbol} [{skipped.code}]: {skipped.reason}")
    lines.append("")

    lines.append("## 🎯 CONCLUSIÓN")
    lines.append("")
    lines.append(_conclusion(result, operar))
    lines.append("")

    footnote = _fx_footnote(fx, operar + vigilar)
    if footnote:
        lines.append(_THIN)
        lines.append(footnote)

    lines.append(_THIN)
    # El pie describe el alcance real del análisis y hay que mantenerlo
    # sincronizado con lo que el bot mira de verdad: un descargo de
    # responsabilidad desactualizado engaña igual que una recomendación mala.
    alcance = (
        "Este informe analiza precio y volumen, y consulta el calendario de resultados y de bancos "
        "centrales para avisar de eventos con fecha conocida."
        if calendar is not None
        else "Este informe se basa exclusivamente en precio y volumen, sin calendario de eventos."
    )
    lines.append(
        f"{alcance} NO consulta noticias ni fundamentales, así que no recoge catalizadores "
        "imprevistos ni valoración. No es asesoramiento financiero."
    )
    lines.append(_SEPARATOR)

    return "\n".join(lines)


def _conclusion(result: AnalysisResult, operar: List[Opportunity]) -> str:
    """Cierre del informe: mejor idea por horizonte y postura de liquidez."""

    if not operar:
        return (
            "**NO OPERAR / MANTENER LIQUIDEZ** — ninguna oportunidad ofrece hoy una relación "
            "rentabilidad/riesgo suficiente. Mantener liquidez también es una decisión de inversión."
        )

    best = operar[0]
    tipo = best.tipo_operacion
    lines = [
        f"Mejor oportunidad ({tipo}): {best.asset.symbol} — score {best.score.value:.0f}, "
        f"ratio {best.levels.rr_ratio:.1f}:1.",
        f"Principal riesgo del mercado: {result.context.reason}.",
    ]

    comprar = [o for o in operar if o.accion == ACCION_COMPRAR]
    exposure = sum(o.sizing.position_pct for o in comprar[:3])
    liquidez = max(0.0, 100.0 - exposure)
    lines.append(
        f"Liquidez recomendada: {liquidez:.0f}% — suma de las {min(len(comprar), 3)} mejores ideas "
        "por señal en su dimensionamiento máximo. La disponibilidad del broker se informa aparte."
    )
    return "\n".join(lines)


def _freshness_for_snapshot(timestamp: pd.Timestamp, reference: datetime, market: str) -> DataFreshness:
    return classify_data_quality(calcular_frescura_dato(timestamp, reference, market), market)


def _freshness_for_opportunity(opportunity: Opportunity, reference: datetime) -> DataFreshness:
    if opportunity.data_freshness is not None:
        return opportunity.data_freshness
    data_symbol = opportunity.asset.data_symbol(reference)
    return _freshness_for_snapshot(
        opportunity.snapshot.timestamp,
        reference,
        mercado_para_simbolo(opportunity.asset, data_symbol),
    )


def _freshness_rows_for_opportunities(opportunities: List[Opportunity], reference: datetime) -> List[FreshnessRow]:
    rows: List[FreshnessRow] = []
    for opportunity in opportunities:
        data_symbol = opportunity.asset.data_symbol(reference)
        rows.append(
            FreshnessRow(
                symbol=opportunity.asset.symbol,
                data_symbol=data_symbol,
                market=mercado_para_simbolo(opportunity.asset, data_symbol),
                freshness=_freshness_for_opportunity(opportunity, reference),
            )
        )
    return rows


def _session_step(sessions_approx: int) -> int:
    if sessions_approx <= 0:
        return 0
    if sessions_approx == 1:
        return 1
    return 2


def _session_step_label(step: int) -> str:
    if step == 0:
        return "0 sesiones cerradas perdidas"
    if step == 1:
        return "1 sesión cerrada perdida"
    return "2 o más sesiones cerradas perdidas"


def _plural_activos(count: int) -> str:
    return "1 activo" if count == 1 else f"{count} activos"


def _bucket_detail(bucket: FreshnessBucket) -> str:
    return f"{bucket.last_bar_date.isoformat()} ({bucket.markets_label})"


def _report_freshness_summary(opportunities: List[Opportunity], reference: datetime) -> str:
    rows = _freshness_rows_for_opportunities(opportunities, reference)
    if not rows:
        return "**Frescura de datos:** 0 activos analizados con snapshot; no hay barras que declarar."

    buckets = agrupar_frescura_por_fecha(rows)
    grouped: dict[int, List[FreshnessBucket]] = {0: [], 1: [], 2: []}
    for bucket in buckets:
        grouped[_session_step(bucket.freshness.sessions_approx)].append(bucket)

    lines = [f"**Frescura de datos:** {_plural_activos(len(rows))} analizados con snapshot."]
    quality_counts: dict[str, int] = {}
    for row in rows:
        if row.freshness is None:
            continue
        quality_counts[row.freshness.quality] = quality_counts.get(row.freshness.quality, 0) + 1
    if quality_counts:
        lines.append(
            "  - Calidad: "
            + ", ".join(f"{quality}={quality_counts[quality]}" for quality in sorted(quality_counts))
            + "."
        )
    for step in (0, 1, 2):
        step_buckets = grouped[step]
        count = sum(bucket.symbols_count for bucket in step_buckets)
        if count == 0:
            lines.append(f"  - {_session_step_label(step)}: 0 activos.")
            continue
        marker = "⚠️ " if step >= 1 else "  - "
        detail = "; ".join(_bucket_detail(bucket) for bucket in step_buckets)
        lines.append(f"{marker}{_session_step_label(step)}: {_plural_activos(count)}; última barra {detail}.")

    absent_rows = [
        row
        for row in rows
        if row.freshness is not None and row.freshness.has_absent_reference_sessions
    ]
    if absent_rows:
        lines.append(
            f"⚠️ Sesiones ausentes frente al calendario de su plaza: {_plural_activos(len(absent_rows))}."
        )
        for row in absent_rows:
            assert row.freshness is not None
            absent_label = _dates_label_limited(row.freshness.absent_reference_sessions)
            if len(row.freshness.absent_reference_sessions) > 5:
                logger.info(
                    "%s: sesiones ausentes completas frente a %s: %s",
                    row.symbol,
                    row.freshness.calendar,
                    _dates_label(row.freshness.absent_reference_sessions),
                )
            lines.append(
                f"  - {row.symbol}: faltan {absent_label} en {row.freshness.calendar}."
            )
    else:
        lines.append("  - Sesiones ausentes frente al calendario de su plaza: 0 activos.")

    no_reference = [
        row
        for row in rows
        if row.freshness is not None and not row.freshness.has_reference_calendar
    ]
    if no_reference:
        symbols = ", ".join(row.symbol for row in no_reference)
        lines.append(f"  - Sin calendario de referencia comparable: {symbols}.")

    partial_rows = [
        row
        for row in rows
        if row.freshness is not None and row.freshness.may_be_partial_current_session
    ]
    if partial_rows:
        lines.append("⚠️ Barra potencialmente parcial: última barra fechada hoy, puede no ser cierre de sesión.")
        for row in partial_rows:
            lines.append(f"  - {row.symbol}")
    return "\n".join(lines)


def _compact_freshness_marker(opportunity: Opportunity, reference: datetime) -> str:
    freshness = _freshness_for_opportunity(opportunity, reference)
    markers: List[str] = []
    if freshness.quality != "OK":
        markers.append(f"calidad {freshness.quality}")
    if freshness.has_absent_reference_sessions:
        markers.append(f"⚠️ falta sesión {_dates_label(freshness.absent_reference_sessions)}")
    if freshness.sessions_approx >= 1:
        sessions = "1s" if freshness.sessions_approx == 1 else f"{freshness.sessions_approx}s"
        markers.append(f"⚠️ dato {freshness.last_bar_date.isoformat()} ({sessions})")
    if not markers:
        return ""
    return " " + "; ".join(markers)


def _code_marker(code: str | None) -> str:
    if not code:
        return ""
    return f" [{code}]"


def _group_discarded_by_code(opportunities: List[Opportunity]) -> dict[str, List[Opportunity]]:
    grouped: dict[str, List[Opportunity]] = {}
    for opportunity in opportunities:
        code = opportunity.discard_code or opportunity.execution_code or "SIN_CODIGO"
        grouped.setdefault(code, []).append(opportunity)
    return dict(sorted(grouped.items()))


def _dates_label(values: tuple[date, ...]) -> str:
    return ", ".join(value.isoformat() for value in values)


def _dates_label_limited(values: tuple[date, ...], limit: int = 5) -> str:
    shown = values[:limit]
    suffix = f" (+{len(values) - limit} más)" if len(values) > limit else ""
    return _dates_label(shown) + suffix
