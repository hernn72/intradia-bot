"""Orquestador del agente IA: añade la capa narrativa a las oportunidades.

Degrada siempre hacia el informe sin IA: si la clave no está configurada, si
el paquete ``anthropic`` no está instalado, si la API falla o si el modelo
devuelve algo que no es JSON válido, las oportunidades se devuelven tal cual
y el informe usa sus textos calculados. La ausencia de IA nunca impide
generar el informe.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import replace
from typing import Any, Dict, List, Optional

from advisor.analysis.opportunity import Narrative, Opportunity
from advisor.config import AiConfig

logger = logging.getLogger(__name__)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def extract_json(raw: str) -> Optional[Dict[str, Any]]:
    """Extrae el primer objeto JSON de una respuesta del modelo.

    Tolera que el modelo envuelva el JSON en texto o en un bloque de código.
    Devuelve ``None`` si no hay JSON válido.
    """

    if not raw or not raw.strip():
        return None

    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        match = _JSON_BLOCK.search(raw)
        if match is None:
            return None
        try:
            parsed = json.loads(match.group(0))
        except (ValueError, TypeError):
            return None

    return parsed if isinstance(parsed, dict) else None


def parse_narrative(raw: str) -> Optional[Narrative]:
    """Convierte la respuesta del agente en un ``Narrative``.

    Devuelve ``None`` si la respuesta no contiene JSON utilizable: es
    preferible caer a los textos calculados que publicar una recomendación
    con campos a medias.
    """

    data = extract_json(raw)
    if data is None:
        return None

    risks = data.get("que_podria_salir_mal", [])
    if not isinstance(risks, list):
        risks = [str(risks)]

    return Narrative(
        tesis=str(data.get("tesis", "")).strip(),
        catalizador=str(data.get("catalizador", "")).strip(),
        escenario_alcista=str(data.get("escenario_alcista", "")).strip(),
        escenario_base=str(data.get("escenario_base", "")).strip(),
        escenario_bajista=str(data.get("escenario_bajista", "")).strip(),
        que_podria_salir_mal=[str(r).strip() for r in risks if str(r).strip()],
        raw=raw,
    )


def enrich_with_narrative(opportunities: List[Opportunity], config: AiConfig) -> List[Opportunity]:
    """Añade la narrativa del agente a las primeras ``max_opportunities``.

    Devuelve una lista nueva; las oportunidades que no se enriquecen (por
    estar fuera del límite o por fallo del agente) se devuelven intactas.
    """

    if not config.enabled or not opportunities:
        return opportunities

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("IA habilitada pero ANTHROPIC_API_KEY no configurada — informe sin capa narrativa")
        return opportunities

    try:
        from anthropic import Anthropic
    except ImportError:
        logger.error("Paquete 'anthropic' no instalado (pip install anthropic) — informe sin capa narrativa")
        return opportunities

    from advisor.ai.agents import run_advisor_agent

    client = Anthropic(api_key=api_key)
    enriched: List[Opportunity] = []

    for index, opportunity in enumerate(opportunities):
        if index >= config.max_opportunities:
            enriched.append(opportunity)
            continue

        try:
            raw = run_advisor_agent(client, config.model, opportunity)
        except Exception as exc:
            logger.error("Agente IA — error analizando %s: %s", opportunity.asset.symbol, exc)
            enriched.append(opportunity)
            continue

        narrative = parse_narrative(raw)
        if narrative is None:
            logger.warning("Agente IA — %s no devolvió JSON válido; se usa el texto calculado", opportunity.asset.symbol)
            enriched.append(opportunity)
            continue

        enriched.append(replace(opportunity, narrative=narrative))

    return enriched
