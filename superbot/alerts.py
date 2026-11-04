"""Avisos de errores operativos: independientes de los avisos de operaciones.

``SUPERBOT_ALERTAS`` los gobierna: vacío los apaga y entonces no se lee ni se
escribe nada; ``seco`` deja en el log lo que se enviaría; ``1`` lo envía con
``SUPERBOT_ALERTAS_BOT_TOKEN`` y ``SUPERBOT_ALERTAS_CHAT_ID``.

Cada causa es un episodio. Avisa una vez, recuerda a las 24 h y después cada 72 h,
y se cierra tras dos ejecuciones limpias: con menos, un fallo intermitente daría
un mensaje por ejecución. Un aviso sin enviar se reintenta en la ejecución
siguiente, y nada de esto puede cambiar el estado de la ejecución ni su salida.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Callable, Dict

from advisor.telegram.notifier import TelegramNotifier
from superbot.store import SuperbotStore

logger = logging.getLogger(__name__)

STATE_KEY = "alertas"
HEADER = "SUPERBOT · OPERATIVO"
FIRST_REMINDER = timedelta(hours=24)
NEXT_REMINDER = timedelta(hours=72)
CLEAN_RUNS_TO_CLOSE = 2

TITLES = {
    "PARADA": "Ejecución detenida: la cartera no se ha tocado",
    "SIN_VIGILAR": "Posición sin vigilar",
    "COBERTURA": "Cobertura insuficiente",
    "SIN_FX": "Falta un tipo de cambio",
    "SPLIT_RETENIDO": "Split sin decidir",
    "REGISTRO_INCOMPLETO": "Registro de decisiones incompleto",
}
# Protegen la cartera o no se recuperan: no esperan a ver si la siguiente lo arregla.
IMMEDIATE = {"PARADA", "SIN_VIGILAR", "REGISTRO_INCOMPLETO"}
# No bloquean entradas: la cartera sigue su curso normal.
WITHOUT_BLOCK = {"PARADA", "REGISTRO_INCOMPLETO"}


def _text(kind: str, cause: str, detail: str) -> str:
    if kind == "RECUPERADO":
        return f"✅ {HEADER}\nRecuperado: {TITLES[cause]}"
    prefix = "Sigue: " if kind == "SIGUE" else ""
    tail = "" if cause in WITHOUT_BLOCK else "\nEntradas bloqueadas; lo abierto sigue protegido si hay datos."
    return f"⚠️ {HEADER}\n{prefix}{TITLES[cause]}\n- {detail}{tail}"


def advance(state: Dict[str, Any], now: datetime, causes: Dict[str, str],
            send: Callable[[str], bool]) -> Dict[str, Any]:
    """Aplica una ejecución a los episodios abiertos y devuelve el estado nuevo."""

    episodes = {cause: dict(episode) for cause, episode in state.items()}
    for cause, detail in causes.items():
        episode = episodes.setdefault(cause, {"sent": None, "seen": 0, "clean": 0, "reminders": 0})
        episode["seen"] += 1
        episode["clean"] = 0
        if episode["sent"] is None:
            if (cause in IMMEDIATE or episode["seen"] >= 2) and send(_text("ALERTA", cause, detail)):
                episode["sent"] = now.isoformat()
            continue
        wait = NEXT_REMINDER if episode["reminders"] else FIRST_REMINDER
        if now - datetime.fromisoformat(episode["sent"]) >= wait and send(_text("SIGUE", cause, detail)):
            episode["sent"] = now.isoformat()
            episode["reminders"] += 1
    # Una ejecución parada no ha mirado nada: no cuenta como limpia para las demás causas.
    for cause in [] if "PARADA" in causes else [c for c in episodes if c not in causes]:
        episode = episodes[cause]
        episode["clean"] += 1
        if episode["clean"] >= CLEAN_RUNS_TO_CLOSE and (
            episode["sent"] is None or send(_text("RECUPERADO", cause, ""))
        ):
            del episodes[cause]
    return episodes


def _dry_run(text: str) -> bool:
    print(f"[aviso operativo, modo seco] {text!r}")
    return True


def report(store: SuperbotStore, now: datetime, causes: Dict[str, str]) -> None:
    """Evalúa los avisos de una ejecución terminada; un fallo aquí solo deja rastro en el log."""

    mode = os.getenv("SUPERBOT_ALERTAS", "").strip()
    if not mode:
        return
    try:
        send = _dry_run
        if mode != "seco":
            send = TelegramNotifier(
                bot_token=os.getenv("SUPERBOT_ALERTAS_BOT_TOKEN"),
                chat_id=os.getenv("SUPERBOT_ALERTAS_CHAT_ID"),
            ).send_message
        state = json.loads(store.get_meta(STATE_KEY) or "{}")
        store.set_meta(STATE_KEY, json.dumps(advance(state, now, causes, send)))
    except Exception as exc:
        logger.warning("Avisos operativos sin evaluar: %s", type(exc).__name__)
