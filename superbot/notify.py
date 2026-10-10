"""Textos de aviso y envío por Telegram de la bandeja ``notifications``.

Los avisos se encolan dentro de la misma transacción que el evento que
describen (clave única por evento), y se envían después. Si Telegram falla, el
aviso queda ``FAILED`` y la cartera no se ve afectada; ``flush`` no reenvía lo
ya enviado.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any, Dict, Optional

from advisor.telegram.notifier import TelegramNotifier
from superbot import LABEL
from superbot.config import SuperbotConfig
from superbot.store import SuperbotStore

logger = logging.getLogger(__name__)

HEADER = f"🧪 SUPERBOT — {LABEL}"


def _eur(value: float) -> str:
    return f"{value:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")


def _px(value: float, currency: str) -> str:
    return f"{value:,.2f} {currency}".replace(",", "X").replace(".", ",").replace("X", ".")


def _sign(value: float) -> str:
    return ("+" if value >= 0 else "") + _eur(value)


def buy_signal_text(symbol: str, name: str, currency: str, session: date, close: float, reason: str,
                    config: SuperbotConfig, cash: float, fx_rate: Optional[float]) -> str:
    params = config.strategy
    stop = close * (1 - params.stop_loss_pct)
    risk = close - stop
    budget = min(cash * config.sizing.max_risk_pct_per_trade / params.stop_loss_pct,
                 cash * config.sizing.max_position_pct)
    units = int(budget // (close * fx_rate)) if fx_rate else 0
    return "\n".join([
        HEADER,
        f"🟢 ORDEN DE COMPRA PAPER — {symbol} ({name})",
        f"Señal al cierre del {session.isoformat()}: {reason}",
        f"Cierre: {_px(close, currency)} · se ejecuta en la próxima apertura",
        f"Stop inicial ≈ {_px(stop, currency)} (−{params.stop_loss_pct:.0%}) · trailing {params.atr_multiplier:g}·ATR",
        f"T1 ≈ {_px(close + params.target1_r * risk, currency)} · T2 ≈ {_px(close + params.target2_r * risk, currency)}",
        f"Unidades estimadas ≈ {units} · presupuesto ≈ {_eur(budget)}",
    ])


def sell_signal_text(symbol: str, name: str, session: date, close: float, reason: str) -> str:
    return "\n".join([
        HEADER,
        f"🔴 ORDEN DE VENTA PAPER — {symbol} ({name})",
        f"Señal al cierre del {session.isoformat()}: {reason}",
        "Se ejecuta en la próxima apertura.",
    ])


def entry_text(position: Dict[str, Any], cash: float) -> str:
    cur = position["currency"]
    return "\n".join([
        HEADER,
        f"✅ COMPRA EJECUTADA — {position['symbol']} ({position['name']})",
        f"{position['entry_date']}: {position['quantity']:g} uds a {_px(position['entry_price_native'], cur)}",
        f"Coste total {_eur(position['cost_eur'])} (comisión incluida)",
        f"Stop {_px(position['stop'], cur)} · T1 {_px(position['target1'], cur)} · T2 {_px(position['target2'], cur)}",
        f"Cash restante {_eur(cash)}",
    ])


def exit_text(position: Dict[str, Any], cash: float) -> str:
    pnl = float(position["pnl_eur"])
    icon = "💰" if pnl >= 0 else "🔻"
    return "\n".join([
        HEADER,
        f"{icon} POSICIÓN CERRADA — {position['symbol']} ({position['name']})",
        f"{position['exit_date']}: {position['quantity']:g} uds a "
        f"{_px(position['exit_price_native'], position['currency'])}",
        f"Motivo: {position['exit_reason']}",
        f"P&L realizado {_sign(pnl)} ({float(position['pnl_pct']):+.2%})",
        f"Cash {_eur(cash)}",
    ])


def target_text(position: Dict[str, Any], label: str, session: date) -> str:
    level = position["target1"] if label == "T1" else position["target2"]
    return "\n".join([
        HEADER,
        f"🎯 {label} TOCADO — {position['symbol']} ({position['name']})",
        f"{session.isoformat()}: máximo ≥ {_px(level, position['currency'])}. Aviso: la posición sigue abierta "
        "con el trailing stop.",
    ])


def split_text(symbol: str, name: str, ratio: float, session: date) -> str:
    return "\n".join([
        HEADER,
        f"✂️ SPLIT — {symbol} ({name})",
        f"{session.isoformat()}: factor {ratio:g}. Unidades, entrada, stop y objetivos reescalados; "
        "el coste y el P&L no cambian.",
    ])


def reject_text(symbol: str, session: date, detail: str) -> str:
    return "\n".join([HEADER, f"⚪ ORDEN RECHAZADA — {symbol}", f"{session.isoformat()}: {detail}"])


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
