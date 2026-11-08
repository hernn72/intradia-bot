"""Avisos de Telegram de Superbot IA.

Mismo patrón ya aprobado del Superbot antiguo (``superbot/notify.py``): un único mensaje por
pasada que tuvo algo real que contar, encolado en ``ia_notificacion`` (nunca enviado directamente
desde dentro de la pasada) y entregado después por ``flush()``, que nunca reenvía lo ya ENVIADA
pero sí reintenta lo FALLIDA. Solo se notifican operaciones REALMENTE ejecutadas (compras y
ventas ya resueltas, incluidos los stops) — nunca una decisión del comité todavía sin ejecutar,
nunca un activo descartado.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from advisor.telegram.notifier import TelegramNotifier
from superbot.ia.cartera import CarteraIA
from superbot.ia.dashboard import build_stats

if TYPE_CHECKING:
    # Solo para anotar tipos: importar pasada.py en tiempo de ejecución crearía un ciclo
    # (pasada.py importa este módulo para encolar los avisos al final de cada pasada).
    from superbot.ia.pasada import ResultadoPasada

HEADER = "🧪 SUPERBOT IA\nPAPER OPERACIONAL — NO VALIDADA PARA CAPITAL REAL"
BOT_TOKEN_ENV = "SUPERBOT_IA_TELEGRAM_BOT_TOKEN"
CHAT_ID_ENV = "SUPERBOT_IA_TELEGRAM_CHAT_ID"
INTERVALO_RESUMEN = timedelta(days=1)


def _num(value: float, digits: int = 2) -> str:
    return f"{value:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _eur(value: float) -> str:
    return f"{_num(value)} EUR"


def _sign_eur(value: float) -> str:
    return ("+" if value >= 0 else "") + _eur(value)


def notifier_from_env() -> TelegramNotifier:
    return TelegramNotifier(bot_token=os.getenv(BOT_TOKEN_ENV), chat_id=os.getenv(CHAT_ID_ENV))


def _detalle_entrada(cartera_ia: CarteraIA, symbol: str) -> Optional[Dict[str, Any]]:
    """Los datos de ENTRADA (precio, unidades, stop) de la posición de este símbolo, siga
    ``ABIERTA`` o ya se haya cerrado — incluso dentro de la MISMA pasada que la abrió (hallazgo de
    Codex: antes solo se miraba entre las abiertas, así que una posición que abría y tocaba el
    stop en la misma llamada a ``procesar_pendientes`` perdía su aviso de COMPRA)."""

    abierta = next((p for p in cartera_ia.posiciones_abiertas() if p.symbol == symbol), None)
    if abierta is not None:
        return {
            "symbol": abierta.symbol, "entry_price": abierta.entry_price, "units": abierta.units,
            "entry_price_eur": abierta.entry_price_eur, "stop": abierta.stop, "currency": abierta.currency,
        }
    return cartera_ia.ultima_posicion_cerrada_de(symbol)


def _bloque_compra(cartera_ia: CarteraIA, symbol: str) -> Optional[str]:
    posicion = _detalle_entrada(cartera_ia, symbol)
    if posicion is None:
        return None
    return "\n".join([
        "🟢 COMPRA ejecutada",
        f"- {posicion['symbol']}",
        f"- Entrada: {_num(posicion['entry_price'])} {posicion['currency']}",
        f"- Unidades: {float(posicion['units']):g}",
        f"- Coste: {_eur(float(posicion['units']) * float(posicion['entry_price_eur']))}",
        f"- Stop: {_num(posicion['stop'])} {posicion['currency']}",
    ])


def _bloque_venta(cartera_ia: CarteraIA, symbol: str, motivo_label: str) -> Optional[str]:
    # Por símbolo exacto, sin límite global (hallazgo de Codex): un límite por recencia GLOBAL
    # podía dejar fuera el cierre real de este símbolo si otros 200 cerraron más tarde.
    fila = cartera_ia.ultima_posicion_cerrada_de(symbol)
    if fila is None:
        return None
    pnl = float(fila["pnl_eur"]) if fila["pnl_eur"] is not None else 0.0
    return "\n".join([
        "🔴 VENTA ejecutada",
        f"- {fila['symbol']}",
        f"- Unidades: {float(fila['units']):g}",
        f"- Motivo: {motivo_label}",
        f"- Resultado: {_sign_eur(pnl)}",
    ])


def encolar_resumen_pasada(cartera_ia: CarteraIA, resultado: ResultadoPasada) -> bool:
    """Un único aviso para TODO lo que de verdad se ejecutó en esta pasada (compras y ventas ya
    resueltas, nunca lo que el comité decidió pero todavía no se ejecutó, ni un activo
    descartado). Si no hubo ninguna operación real, no encola nada.
    """

    bloques: List[str] = []
    for symbol in resultado.aperturas:
        bloque = _bloque_compra(cartera_ia, symbol)
        if bloque is not None:
            bloques.append(bloque)
    for symbol in resultado.cerradas_stop:
        bloque = _bloque_venta(cartera_ia, symbol, "STOP obligatorio")
        if bloque is not None:
            bloques.append(bloque)
    for symbol in resultado.salidas_ia:
        bloque = _bloque_venta(cartera_ia, symbol, "venta de la IA")
        if bloque is not None:
            bloques.append(bloque)
    if not bloques:
        return False
    texto = "\n\n".join([HEADER, *bloques])
    return cartera_ia.encolar_notificacion(
        clave=f"pasada:{resultado.pasada_id}", tipo="OPERACIONES", texto=texto,
    )


def encolar_error_pasada(cartera_ia: CarteraIA, resultado: ResultadoPasada) -> bool:
    """Solo si la pasada entera falló (``status == 'ERROR'``) — nunca por una incidencia menor y
    rutinaria (p. ej. "sin tipo de cambio todavía, sigue pendiente"), para no generar ruido."""

    if resultado.status != "ERROR":
        return False
    detalle = "; ".join(resultado.incidencias)[:1000] or "sin detalle"
    texto = "\n\n".join([HEADER, "🚨 ERROR en la pasada", f"- {detalle}"])
    return cartera_ia.encolar_notificacion(
        clave=f"pasada:{resultado.pasada_id}:error", tipo="ERROR", texto=texto,
    )


def encolar_resumen_periodico(cartera_ia: CarteraIA, ahora: datetime) -> bool:
    """Resumen de cartera cada ``INTERVALO_RESUMEN`` como máximo (nunca uno por pasada: evita el
    ruido de un resumen repetido varias veces el mismo día si la pasada se ejecuta a menudo)."""

    if not cartera_ia.activa():
        return False
    ultimo = cartera_ia.ultimo_resumen_enviado_en()
    if ultimo is not None and datetime.fromisoformat(ultimo) + INTERVALO_RESUMEN > ahora:
        return False
    stats = build_stats(cartera_ia)
    if not stats["activa"]:
        return False
    abiertas = cartera_ia.posiciones_abiertas()
    lineas = [
        HEADER, "📊 RESUMEN DE CARTERA",
        f"Capital inicial {_eur(stats['capital_inicial_eur'])} · Equity (a coste) {_eur(stats['equity_contable_eur'])}",
        f"Cash {_eur(stats['cash_eur'])} · Coste abierto {_eur(stats['coste_abierto_eur'])}",
        f"P&L realizado {_sign_eur(stats['pnl_realizado_eur'])} · Rentabilidad {('+' if stats['rentabilidad_contable_pct'] >= 0 else '')}{_num(stats['rentabilidad_contable_pct'] * 100)} %",
        f"Posiciones abiertas: {len(abiertas)}",
    ]
    for p in abiertas:
        lineas.append(f"• {p.symbol} {p.units:g} uds · coste {_eur(p.units * p.entry_price_eur)} · stop {_num(p.stop)} {p.currency}")
    texto = "\n".join(lineas)
    return cartera_ia.encolar_notificacion(
        clave=f"resumen:{ahora.date().isoformat()}", tipo="RESUMEN", texto=texto, creado_en=ahora.isoformat(),
    )


def encolar_notificaciones_de_la_pasada(cartera_ia: CarteraIA, resultado: ResultadoPasada, ahora: datetime) -> None:
    """Punto de entrada único desde ``pasada.py``: encola lo que corresponda (nunca envía nada
    por red — eso lo hace ``flush()``, aparte, para que un fallo de Telegram nunca afecte a la
    pasada en sí)."""

    encolar_error_pasada(cartera_ia, resultado)
    encolar_resumen_pasada(cartera_ia, resultado)
    encolar_resumen_periodico(cartera_ia, ahora)


def flush(cartera_ia: CarteraIA, notifier: TelegramNotifier) -> Dict[str, int]:
    """Envía los avisos pendientes; sin Telegram configurado los deja ``PENDIENTE`` (nunca se
    marcan como enviados sin haberlo estado: así, en cuanto se configure, se entregan).

    Cada aviso se RECLAMA (``ENVIANDO``) antes de intentar enviarlo (hallazgo de Codex): si dos
    ``flush()`` corrieran a la vez, solo uno de los dos lo reclama, así que nunca se envía el
    mismo aviso dos veces por esa vía — no elimina la ventana, inevitable con la API de Telegram,
    entre que Telegram confirma la entrega y se marca ``ENVIADA`` en la base (si el proceso muere
    justo ahí, se reintentará); ``superbot/notify.py`` acepta la misma limitación.
    """

    contadores = {"ENVIADA": 0, "FALLIDA": 0, "SIN_CONFIGURAR": 0}
    for item in cartera_ia.notificaciones_pendientes():
        if not cartera_ia.reclamar_notificacion(int(item["id"])):
            continue  # otro flush() ya la reclamó
        if not notifier.enabled:
            cartera_ia.marcar_notificacion(int(item["id"]), "PENDIENTE")  # no se intentó: se libera
            contadores["SIN_CONFIGURAR"] += 1
            continue
        if notifier.send_long_message(item["texto"]):
            cartera_ia.marcar_notificacion(int(item["id"]), "ENVIADA")
            contadores["ENVIADA"] += 1
        else:
            cartera_ia.marcar_notificacion(int(item["id"]), "FALLIDA")
            contadores["FALLIDA"] += 1
    return contadores


__all__ = [
    "encolar_error_pasada",
    "encolar_notificaciones_de_la_pasada",
    "encolar_resumen_pasada",
    "encolar_resumen_periodico",
    "flush",
    "notifier_from_env",
]
