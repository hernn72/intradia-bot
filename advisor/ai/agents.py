"""Capa de llamada al modelo: construye el mensaje y devuelve la respuesta cruda.

Mismo patrón de tres capas que usa el trading-bot: el system prompt vive en
``advisor/ai/prompts/<nombre>.md``, esta capa hace la llamada, y el
orquestador (``advisor.ai.narrator``) valida y ensambla. Cambiar el
comportamiento del agente = editar el ``.md``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anthropic import Anthropic

    from advisor.analysis.opportunity import Opportunity

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# Margen amplio a propósito: los modelos actuales razonan antes de responder y
# ese razonamiento consume el mismo presupuesto que la respuesta. Con un techo
# ajustado el JSON se corta a medias, el parseo falla y la narrativa se pierde
# en silencio. La respuesta útil son ~400 tokens; el resto es holgura.
MAX_TOKENS = 4000


def _load_prompt(name: str) -> str:
    """Carga el system prompt desde ``advisor/ai/prompts/<name>.md``."""
    return (_PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def _call(client: Anthropic, model: str, system: str, user: str, max_tokens: int = MAX_TOKENS) -> str:
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": user}],
        system=system,
    )

    # La respuesta puede traer bloques de razonamiento por delante del texto,
    # así que se busca el primer bloque de texto en vez de dar por hecho que
    # es el primero de la lista.
    text = next((b.text for b in msg.content if b.type == "text"), None)

    if getattr(msg, "stop_reason", None) == "max_tokens":
        logger.warning(
            "Agente IA — respuesta truncada por max_tokens (%d): el JSON llegará incompleto", max_tokens
        )

    if text is None or not text.strip():
        tipos = ", ".join(getattr(b, "type", type(b).__name__) for b in msg.content) or "ninguno"
        raise RuntimeError(f"Respuesta del modelo sin bloque de texto (bloques recibidos: {tipos})")
    return text.strip()


def build_user_message(opportunity: Opportunity) -> str:
    """Contexto de una oportunidad, tal y como lo recibe el agente.

    Incluye solo lo que el sistema ha calculado. Separada de ``_call`` para
    poder comprobarla en tests sin tocar la red.
    """

    asset = opportunity.asset
    snapshot = opportunity.snapshot
    levels = opportunity.levels
    context = opportunity.context

    def _fmt(value, suffix: str = "", decimals: int = 2) -> str:
        return f"{value:.{decimals}f}{suffix}" if value is not None else "N/D"

    target_pcts = levels.target_pcts

    catalizador = next((d for d in opportunity.score.dimensions if d.name == "catalizador"), None)
    catalizador_detail = "sin datos"
    if catalizador is not None and catalizador.available:
        catalizador_detail = "; ".join(
            f"{c.name}: {c.detail}" for c in catalizador.components if c.points is not None and c.detail
        )

    return (
        f"ACTIVO: {asset.name} ({asset.symbol})\n"
        f"Clase: {asset.asset_class}  |  Región: {asset.region}  |  Mercado: {asset.market}  |  Divisa: {asset.currency}\n"
        f"Tipo de operación: {opportunity.tipo_operacion}  |  Horizonte: {opportunity.duracion}\n"
        f"\n"
        f"TÉCNICO (velas de {snapshot.interval}, {snapshot.bars} velas)\n"
        f"Precio: {_fmt(snapshot.price)}  |  EMA rápida: {_fmt(snapshot.ema_fast)}  |  EMA lenta: {_fmt(snapshot.ema_slow)}\n"
        f"SMA larga: {_fmt(snapshot.sma_long)}  |  RSI: {_fmt(snapshot.rsi, decimals=1)}  |  ATR: {_fmt(snapshot.atr)}"
        f" ({_fmt(snapshot.atr_pct, '%', 1)} del precio)\n"
        f"MACD histograma: {_fmt(snapshot.macd_hist, decimals=4)}  |  Volumen vs media: {_fmt(snapshot.volume_ratio, '×', 1)}\n"
        f"Hueco de apertura: {_fmt(snapshot.gap_pct, '%', 1)}  |  Fortaleza relativa: {_fmt(snapshot.relative_strength, ' pp', 1)}\n"
        f"Retornos (20/60/120 velas): {_fmt(snapshot.return_short, '%', 1)} / "
        f"{_fmt(snapshot.return_medium, '%', 1)} / {_fmt(snapshot.return_long, '%', 1)}\n"
        f"Volatilidad anualizada: {_fmt(snapshot.volatility_pct, '%', 1)}\n"
        f"\n"
        f"NIVELES YA FIJADOS (no los modifiques)\n"
        f"Entrada ideal: {_fmt(levels.entry_ideal_low)} — {_fmt(levels.entry_ideal_high)}"
        f"  |  Entrada máxima: {_fmt(levels.entry_max)}\n"
        f"Stop: {_fmt(levels.stop)} ({levels.stop_basis})  |  Riesgo: -{_fmt(levels.risk_pct, '%', 1)}\n"
        f"Objetivo 1: {_fmt(levels.target1)} ({_fmt(target_pcts[0], '%', 1)})  |  "
        f"Objetivo 2: {_fmt(levels.target2)} ({_fmt(target_pcts[1], '%', 1)})  |  "
        f"Objetivo 3: {_fmt(levels.target3)} ({_fmt(target_pcts[2], '%', 1)})\n"
        f"Ratio beneficio/riesgo: {_fmt(levels.rr_ratio, ':1', 1)}\n"
        f"Invalidación de la tesis: {_fmt(levels.invalidation_level)} — {levels.invalidation_reason}\n"
        f"\n"
        f"CATALIZADOR OBSERVABLE EN EL PRECIO: {catalizador_detail}\n"
        f"\n"
        f"CONTEXTO DE MERCADO: {context.label} — {context.reason}\n"
        f"VIX: {_fmt(context.vix_value, decimals=1)} (umbral {_fmt(context.vix_threshold, decimals=1)})\n"
        f"\n"
        f"PUNTUACIÓN DEL SISTEMA: {opportunity.score.value:.0f}/100 ({opportunity.score.grade}), "
        f"sobre {opportunity.score.evaluable_max:.0f} puntos evaluables\n"
        f"Dimensiones sin datos: "
        f"{', '.join(opportunity.score.missing_dimensions) if opportunity.score.missing_dimensions else 'ninguna'}\n"
        f"Decisión del sistema: {opportunity.accion}"
    )


def run_advisor_agent(client: Anthropic, model: str, opportunity: Opportunity, max_tokens: int = MAX_TOKENS) -> str:
    """Pide al agente la parte narrativa de una recomendación. Devuelve JSON crudo."""

    return _call(
        client,
        model,
        _load_prompt("advisor_agent"),
        build_user_message(opportunity),
        max_tokens=max_tokens,
    )
