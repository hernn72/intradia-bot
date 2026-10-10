"""Textos de aviso y envío por Telegram de la bandeja ``notifications``.

Telegram recibe un único mensaje por ejecución con las operaciones que hizo el
paper (compras y ventas ejecutadas, objetivos tocados) y un resumen breve de
cartera; si no hubo ninguna, no hay mensaje. El mensaje se encola dentro de la
misma transacción que las operaciones (clave única por ejecución) y se envía
después. Si Telegram falla, el
aviso queda ``FAILED`` y la cartera no se ve afectada; ``flush`` no reenvía lo
ya enviado.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from advisor.telegram.notifier import TelegramNotifier
from superbot import LABEL
from superbot.store import SuperbotStore

logger = logging.getLogger(__name__)

HEADER = f"🧪 SUPERBOT — {LABEL}"
TELEGRAM_HEADER = "🧪 SUPERBOT\nPAPER OPERACIONAL — NO VALIDADA PARA CAPITAL REAL"
CURRENCY_SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£", "CHF": "CHF", "JPY": "¥"}

EXIT_REASONS = {
    "STOP": "STOP",
    "TRAILING": "STOP (trailing)",
    "GAP_STOP": "STOP (abrió por debajo del stop)",
    "SIGNAL_EXIT": "señal de salida",
}


def _es(value: float, decimals: int = 2) -> str:
    return f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(value: float, decimals: int) -> str:
    return ("+" if value >= 0 else "") + f"{_es(value, decimals)} %"


def _eur(value: float) -> str:
    return f"{_es(value)} EUR"


def _px(value: float, currency: str) -> str:
    return f"{value:,.2f} {currency}".replace(",", "X").replace(".", ",").replace("X", ".")


def _money(value: float, currency: str = "EUR", decimals: int = 2) -> str:
    return f"{_es(value, decimals)} {CURRENCY_SYMBOLS.get(currency, currency)}"


def _sign(value: float) -> str:
    return ("+" if value >= 0 else "") + _eur(value)


# --- Telegram: solo lo que hizo el paper -------------------------------------
#
# Cada bloque describe una operación ya ejecutada (fill de compra o de venta) o
# un objetivo tocado; las señales y órdenes pendientes, rechazos, splits e
# indicadores se quedan en superbot.db y en el dashboard.


def buy_block(position: Dict[str, Any]) -> str:
    cur = position["currency"]
    return "\n".join([
        "🟢 COMPRAR",
        f"- {position['symbol']}",
        f"- Entrada aprox.: {_money(position['entry_price_native'], cur)}",
        f"- Cantidad: {position['quantity']:g}",
        f"- Inversión: {_money(position['cost_eur'])}",
        f"- Stop: {_money(position['stop'], cur)}",
        f"- T1: {_money(position['target1'], cur)}",
        f"- T2: {_money(position['target2'], cur)}",
    ])


def sell_block(position: Dict[str, Any], kind: str) -> str:
    pnl = float(position["pnl_eur"])
    return "\n".join([
        "🔴 VENDER",
        f"- {position['symbol']}",
        f"- Cantidad: {position['quantity']:g}",
        f"- Precio aprox.: {_money(position['exit_price_native'], position['currency'])}",
        f"- Motivo: {EXIT_REASONS[kind]}",
        f"- Resultado de la operación: {'+' if pnl >= 0 else ''}{_money(pnl)} "
        f"({_pct(float(position['pnl_pct']) * 100, 1)})",
    ])


def target_block(position: Dict[str, Any], label: str) -> str:
    level = position["target1"] if label == "T1" else position["target2"]
    return "\n".join([
        "🎯 OBJETIVO",
        f"- {position['symbol']}",
        f"- {label} alcanzado: {_money(level, position['currency'])}",
        "- Posición continúa abierta.",
    ])


def portfolio_block(equity: float, cash: float, open_positions: int, initial_capital: float) -> str:
    total = (equity / initial_capital - 1) * 100
    return "\n".join([
        "Cartera",
        f"- Capital/equity: {_money(equity, decimals=0)}",
        f"- Cash: {_money(cash, decimals=0)}",
        f"- Posiciones abiertas: {open_positions}",
        f"- Rentabilidad: {_pct(total, 2)}",
    ])


def operations_message(blocks: List[str], portfolio: str) -> str:
    return "\n\n".join([TELEGRAM_HEADER, *blocks, portfolio])


def summary_text(store: SuperbotStore) -> str:
    config = store.config()
    cash = store.cash_eur()
    open_positions = store.open_positions()
    invested = sum(float(p["quantity"]) * float(p["last_close"]) * float(p["last_fx"]) for p in open_positions)
    equity = cash + invested
    realized = sum(float(p["pnl_eur"]) for p in store.closed_positions())
    unrealized = invested - sum(float(p["cost_eur"]) for p in open_positions)
    total = equity / config.initial_capital_eur - 1
    lines = [
        HEADER,
        "📊 RESUMEN DE CARTERA",
        f"Capital inicial {_eur(config.initial_capital_eur)} · Equity {_eur(equity)} ({total:+.2%})",
        f"Cash {_eur(cash)} · Invertido {_eur(invested)}",
        f"P&L realizado {_sign(realized)} · P&L abierto {_sign(unrealized)}",
        f"Posiciones abiertas: {len(open_positions)}",
    ]
    for p in open_positions:
        value = float(p["quantity"]) * float(p["last_close"]) * float(p["last_fx"])
        lines.append(
            f"• {p['symbol']} {p['quantity']:g} uds · {_sign(value - float(p['cost_eur']))} · "
            f"stop {_px(p['stop'], p['currency'])}"
        )
    pending = store.pending_orders()
    if pending:
        lines.append("Órdenes pendientes: " + ", ".join(f"{o['side']} {o['symbol']}" for o in pending))
    return "\n".join(lines)


def notifier_from_env() -> TelegramNotifier:
    return TelegramNotifier(
        bot_token=os.getenv("SUPERBOT_TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN"),
        chat_id=os.getenv("SUPERBOT_TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID"),
    )


def flush(store: SuperbotStore, notifier: TelegramNotifier) -> Dict[str, int]:
    """Envía los avisos pendientes; sin Telegram configurado los marca ``SKIPPED``."""

    counts = {"SENT": 0, "FAILED": 0, "SKIPPED": 0}
    for item in store.pending_notifications():
        if not notifier.enabled:
            status = "SKIPPED"
        elif notifier.send_long_message(item["text"]):
            status = "SENT"
        else:
            status = "FAILED"
        store.mark_notification(int(item["id"]), status)
        counts[status] += 1
    return counts
