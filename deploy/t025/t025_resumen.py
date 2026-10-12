"""Vista resumida del mensaje shadow de T-025 para Telegram.

Pegamento de despliegue (``deploy/t025``, fuera de ``EXECUTOR_PATHS_T025``): el código de
``paper`` está congelado en el ``t025_code_sha`` de la cohorte (cambiarlo deja la pasada sin
ejecutar), así que el resumen se hace aquí, sobre el texto que ya imprime
``python -m paper telegram``. En la Pi se ejecuta copiado en ``~/t025-forward/bin/``.

Solo reordena y recorta lo que ese texto ya muestra: nunca añade un dato. Las señales
se agrupan por estado (pendiente, MARKET_PASS, rechazo) y política; los niveles de
cada señal siguen en paper.db y en ``python -m paper signals``. Si alguna línea no
tiene la forma conocida, se devuelve el texto original sin tocar.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

LABEL_LINE = "🧪 SHADOW / PAPER — estrategia en investigación, no validada para capital real"
SEAL_LINE = "Desenlaces sellados hasta que T-024 se resuelva (D-73, D-75)."
PENDING = "pendiente de la apertura"
# El texto congelado dice «apertura», pero la ingesta solo guarda barras cerradas más el
# settlement: la comprobación espera a que se valide la barra de entrada, no a que abra el mercado.
PENDING_LABEL = "⏳ Pendientes de validar la barra de entrada"

_SIGNAL = re.compile(
    r"^(?P<policy>\S+) · (?P<symbol>\S+) · sesión (?P<day>\S+): "
    r"entrada máx \S+, stop \S+, obj2 \S+, RR \S+ → (?P<status>.+)$"
)
_MARKET_PASS = re.compile(r"^MARKET_PASS a (?P<price>\S+) \(\S+\), tamaño (?P<weight>\S+) % de la equity$")
_REJECTED = re.compile(r"^rechazo de mercado: (?P<code>.+)$")


def _original(text: str, session: str) -> str:
    return f"{text}\nSesión de señal {session}"


def _parse(text: str, session: str) -> Optional[List[Tuple[str, str, str]]]:
    """``(policy, symbol, status)`` de cada señal, o ``None`` si el texto no es el esperado."""

    lines = text.split("\n")
    if len(lines) < 3 or lines[0] != LABEL_LINE or lines[-1] != SEAL_LINE:
        return None
    signals: List[Tuple[str, str, str]] = []
    for line in lines[1:-1]:
        match = _SIGNAL.match(line)
        if match is None or match["day"] != session:
            return None
        status = match["status"]
        if status != PENDING and not _MARKET_PASS.match(status) and not _REJECTED.match(status):
            return None
        signals.append((match["policy"], match["symbol"], status))
    return signals


def _grouped(items: List[Tuple[str, str]]) -> List[str]:
    """Una línea por política con sus activos, en el orden del mensaje original."""

    by_policy: Dict[str, List[str]] = {}
    for policy, entry in items:
        by_policy.setdefault(policy, []).append(entry)
    return [f"{policy} ({len(entries)}): {', '.join(entries)}" for policy, entries in sorted(by_policy.items())]


def resumir(text: str, session: str) -> str:
    """Mensaje de Telegram de una sesión de señal: agrupado si se reconoce, original si no."""

    signals = _parse(text, session)
    if not signals:
        return _original(text, session)

    pending: List[Tuple[str, str]] = []
    passed: List[Tuple[str, str]] = []
    rejected: List[Tuple[str, str]] = []
    for policy, symbol, status in signals:
        market_pass = _MARKET_PASS.match(status)
        rejection = _REJECTED.match(status)
        if market_pass is not None:
            passed.append((policy, f"{symbol} a {market_pass['price']} ({market_pass['weight']} %)"))
        elif rejection is not None:
            rejected.append((policy, f"{symbol} ({rejection['code']})"))
        else:
            pending.append((policy, symbol))

    total = len(signals)
    lines = [LABEL_LINE, f"Sesión de señal {session} · {total} {'señal' if total == 1 else 'señales'} OPERAR"]
    for title, items in (
        ("✅ MARKET_PASS", passed),
        ("❌ Rechazo de mercado", rejected),
        (PENDING_LABEL, pending),
    ):
        if items:
            lines.append("")
            lines.append(title)
            lines.extend(_grouped(items))
    lines.append("")
    lines.append("Niveles de cada señal: python -m paper signals (paper.db).")
    lines.append(SEAL_LINE)
    return "\n".join(lines)
