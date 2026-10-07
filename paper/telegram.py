"""Mensaje shadow de Telegram de T-025 (ficha §4, §10.2; D-78).

Solo usa la capa de visibilidad. Primera línea: la etiqueta SHADOW / PAPER. Las políticas se nombran
``B2-P6``, ``S2-P6`` y ``C0-P6`` para no confundir sus niveles con los de C0 del informe de la Pi
(contexto ``legacy_v1`` y serie ajustada por dividendos). Nunca muestra ``FILLED``, tamaños en EUR o
unidades, cash, equity, posiciones ni desenlaces.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from paper import LABEL
from paper.store import PaperStore
from paper.visibility import visible_signals


def _fmt(value: Optional[float], digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def shadow_message(store: PaperStore, *, session: Optional[str] = None) -> str:
    signals = visible_signals(store, since=session)
    if session:
        signals = [s for s in signals if s["signal_session_date"] == session]
    latest: Dict[tuple, Dict[str, Any]] = {}
    for item in signals:
        if item["operar"]:
            latest[(item["policy"], item["symbol"], item["signal_session_date"])] = item
    lines: List[str] = [f"🧪 {LABEL}"]
    if not latest:
        lines.append("Sin señales OPERAR de B2-P6, S2-P6 ni C0-P6.")
        return "\n".join(lines)
    for (policy, symbol, day), item in sorted(latest.items()):
        line = (f"{policy} · {symbol} · sesión {day}: entrada máx {_fmt(item['entry_max'])}, "
                f"stop {_fmt(item['stop'])}, obj2 {_fmt(item['target2'])}, RR {_fmt(item['rr_at_reference'])}")
        check = item["check_code"]
        if check == "MARKET_PASS":
            line += (f" → MARKET_PASS a {_fmt(item['entry_effective'])} ({item['entry_session']}),"
                     f" tamaño {100 * (item['requested_weight'] or 0):.1f} % de la equity")
        elif check:
            line += f" → rechazo de mercado: {check}"
        else:
            line += " → pendiente de la apertura"
        lines.append(line)
    lines.append("Desenlaces sellados hasta que T-024 se resuelva (D-73, D-75).")
    return "\n".join(lines)


def send(text: str) -> bool:
    import os

    from advisor.telegram.notifier import TelegramNotifier

    notifier = TelegramNotifier(bot_token=os.getenv("TELEGRAM_BOT_TOKEN"), chat_id=os.getenv("TELEGRAM_CHAT_ID"))
    return notifier.send_long_message(text)
