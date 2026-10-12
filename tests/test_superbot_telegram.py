"""Mensajes de Telegram del superbot: solo las operaciones que hizo el paper.

Un mensaje por ejecución con compras/ventas ejecutadas y objetivos tocados,
más un resumen breve de cartera; sin operaciones no hay mensaje, y nunca lleva
análisis técnico (eso se queda en superbot.db y en el dashboard).
"""

from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path
from typing import List

import pytest

from superbot import notify
from superbot.store import SuperbotStore
from tests.test_superbot_engine import BREAK, BUY, NEUTRAL, START, FakeFx, bar, make_store, rows, run, series

HEADER = "PAPER OPERACIONAL — NO VALIDADA PARA CAPITAL REAL"
TECHNICAL = re.compile(r"\b(sma\w*|rsi|momentum|atr|score|barras?|símbolos?|indicador\w*|tendencia)\b", re.I)


def messages(store: SuperbotStore) -> List[str]:
    found = [row["text"] for row in rows(store, "SELECT text FROM notifications ORDER BY id")]
    for text in found:
        assert HEADER in text.splitlines()[1]
        assert TECHNICAL.search(text) is None, text
    return found


def blocks(text: str) -> List[str]:
    """Títulos de los bloques de operación, en orden (sin cabecera ni cartera)."""
    return [part.splitlines()[0] for part in text.split("\n\n")[1:-1]]


def es(value: float) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# --- formato exacto -----------------------------------------------------------


def test_formato_de_compra() -> None:
    position = {"symbol": "ASML", "currency": "EUR", "entry_price_native": 812.40, "quantity": 2.0,
                "cost_eur": 1624.80, "stop": 771.78, "target1": 893.64, "target2": 974.88}
    assert notify.buy_block(position) == "\n".join([
        "🟢 COMPRAR",
        "- ASML",
        "- Entrada aprox.: 812,40 €",
        "- Cantidad: 2",
        "- Inversión: 1.624,80 €",
        "- Stop: 771,78 €",
        "- T1: 893,64 €",
        "- T2: 974,88 €",
    ])


def test_formato_de_venta_en_dolares_con_resultado_en_euros() -> None:
    position = {"symbol": "AAPL", "currency": "USD", "quantity": 5.0, "exit_price_native": 246.20,
                "pnl_eur": 82.40, "pnl_pct": 0.031}
    assert notify.sell_block(position, "SIGNAL_EXIT") == "\n".join([
        "🔴 VENDER",
        "- AAPL",
        "- Cantidad: 5",
        "- Precio aprox.: 246,20 $",
        "- Motivo: señal de salida",
        "- Resultado de la operación: +82,40 € (+3,1 %)",
    ])
    loss = {**position, "pnl_eur": -1234.5, "pnl_pct": -0.052}
    assert notify.sell_block(loss, "STOP").splitlines()[-2:] == [
        "- Motivo: STOP", "- Resultado de la operación: -1.234,50 € (-5,2 %)"]


def test_formato_de_objetivo_y_cartera() -> None:
    position = {"symbol": "SAP", "currency": "EUR", "target1": 245.30, "target2": 260.0}
    assert notify.target_block(position, "T1") == "🎯 OBJETIVO\n- SAP\n- T1 alcanzado: 245,30 €\n" \
                                                  "- Posición continúa abierta."
    assert notify.portfolio_block(10_245.0, 6_120.0, 3, 10_000.0) == "\n".join([
        "Cartera",
        "- Capital/equity: 10.245 €",
        "- Cash: 6.120 €",
        "- Posiciones abiertas: 3",
        "- Rentabilidad: +2,45 %",
    ])


# --- lo que manda el motor ----------------------------------------------------


def test_compra_ejecutada_un_mensaje_con_sus_niveles(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    data = {"SAP.DE": series("SAP.DE", [bar(99, 101, 98, 100, BUY), bar(100, 104, 99, 103, NEUTRAL)])}
    run(store, data, today=START + timedelta(days=1))

    [text] = messages(store)
    position = rows(store, "SELECT * FROM positions")[0]
    assert blocks(text) == ["🟢 COMPRAR"]
    for line in (
        "- SAP.DE",
        f"- Entrada aprox.: {es(position['entry_price_native'])} €",
        f"- Cantidad: {position['quantity']:g}",
        f"- Inversión: {es(position['cost_eur'])} €",
        f"- Stop: {es(position['initial_stop'])} €",
        f"- T1: {es(position['target1'])} €",
        f"- T2: {es(position['target2'])} €",
        "- Posiciones abiertas: 1",
    ):
        assert line in text.splitlines()


def test_ejecucion_sin_operaciones_no_manda_mensaje(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    # Solo una señal de compra al cierre: la orden queda pendiente, el paper aún no ha comprado.
    run(store, {"SAP.DE": series("SAP.DE", [bar(99, 101, 98, 100, BUY)])}, today=START)
    assert rows(store, "SELECT status FROM orders")[0]["status"] == "PENDING"
    # Barras sin nada que hacer (ni fills, ni stops, ni objetivos).
    run(store, {"SAP.DE": series("SAP.DE", [bar(99, 101, 98, 100, BUY)]),
                "BMW.DE": series("BMW.DE", [bar(99, 101, 98, 100, NEUTRAL)] * 2)}, today=START + timedelta(days=1))
    assert messages(store) == []


def test_venta_por_senal_de_salida(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    first = [bar(99, 101, 98, 100, BUY), bar(100, 104, 99, 103, NEUTRAL)]
    run(store, {"SAP.DE": series("SAP.DE", first)}, today=START + timedelta(days=1))
    later = [*first, bar(103, 104, 101, 102, BREAK), bar(101, 102, 100, 101, NEUTRAL)]
    run(store, {"SAP.DE": series("SAP.DE", later)}, today=START + timedelta(days=3))

    buy_msg, sell_msg = messages(store)
    assert blocks(buy_msg) == ["🟢 COMPRAR"]
    assert blocks(sell_msg) == ["🔴 VENDER"]
    position = rows(store, "SELECT * FROM positions")[0]
    lines = sell_msg.splitlines()
    assert "- SAP.DE" in lines
    assert f"- Cantidad: {position['quantity']:g}" in lines
    assert f"- Precio aprox.: {es(position['exit_price_native'])} €" in lines
    assert "- Motivo: señal de salida" in lines
    sign = "+" if position["pnl_eur"] >= 0 else ""
    assert f"- Resultado de la operación: {sign}{es(position['pnl_eur'])} € " \
           f"({sign}{position['pnl_pct'] * 100:.1f} %)".replace(".", ",") in lines
    assert "- Posiciones abiertas: 0" in lines


@pytest.mark.parametrize("bars, reason", [
    # Stop inicial ≈ 95,07 sin subir (100 − 3·2 = 94 no lo mejora); el mínimo 94 lo toca.
    ([bar(100, 101, 99, 100, NEUTRAL), bar(97, 98, 94, 95, NEUTRAL)], "STOP"),
    # Apertura ya bajo el stop.
    ([bar(100, 101, 99, 100, NEUTRAL), bar(90, 92, 89, 91, NEUTRAL)], "STOP (abrió por debajo del stop)"),
    # El trailing sube el stop a 109 − 6 = 103 y el mínimo 102 lo toca.
    ([bar(100, 104, 99, 103, NEUTRAL), bar(103, 109, 102, 109, NEUTRAL), bar(108, 108, 102, 104, NEUTRAL)],
     "STOP (trailing)"),
])
def test_venta_por_stop(tmp_path: Path, bars: List[dict], reason: str) -> None:
    store = make_store(tmp_path)
    run(store, {"SAP.DE": series("SAP.DE", [bar(99, 101, 98, 100, BUY), *bars])},
        today=START + timedelta(days=len(bars)))
    [text] = messages(store)
    assert blocks(text)[-1] == "🔴 VENDER"
    assert f"- Motivo: {reason}" in text.splitlines()


def test_objetivos_t1_y_t2_se_avisan_una_vez_y_la_posicion_sigue(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    first = [bar(99, 101, 98, 100, BUY), bar(100, 104, 99, 103, NEUTRAL)]
    run(store, {"SAP.DE": series("SAP.DE", first)}, today=START + timedelta(days=1))
    # Entrada ≈ 100,08, riesgo 5 %: T1 ≈ 110,08 y T2 ≈ 120,09; el máximo 121 toca los dos.
    later = [*first, bar(104, 121, 103, 118, NEUTRAL), bar(118, 125, 117, 124, NEUTRAL)]
    run(store, {"SAP.DE": series("SAP.DE", later)}, today=START + timedelta(days=3))

    _, targets = messages(store)
    position = rows(store, "SELECT * FROM positions")[0]
    assert position["status"] == "OPEN"
    assert blocks(targets) == ["🎯 OBJETIVO", "🎯 OBJETIVO"]
    lines = targets.splitlines()
    assert f"- T1 alcanzado: {es(position['target1'])} €" in lines
    assert f"- T2 alcanzado: {es(position['target2'])} €" in lines
    assert lines.count("- Posición continúa abierta.") == 2


def test_varias_operaciones_en_un_mismo_mensaje(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    fx = FakeFx({"USD": {START: 0.9}})
    data = {
        # Compra, T1 y salida por trailing en la misma ejecución.
        "SAP.DE": series("SAP.DE", [
            bar(99, 101, 98, 100, BUY), bar(100, 104, 99, 103, NEUTRAL),
            bar(103, 111, 102, 109, NEUTRAL), bar(108, 108, 102, 104, NEUTRAL),
        ]),
        "AAPL": series("AAPL", [bar(99, 101, 98, 100, BUY), bar(100, 101, 99, 100, NEUTRAL)], currency="USD"),
    }
    run(store, data, fx, today=START + timedelta(days=3))

    [text] = messages(store)
    assert blocks(text) == ["🟢 COMPRAR", "🟢 COMPRAR", "🎯 OBJETIVO", "🔴 VENDER"]
    assert text.index("- AAPL") < text.index("- SAP.DE")
    assert "- Motivo: STOP (trailing)" in text
    aapl = rows(store, "SELECT * FROM positions WHERE symbol = 'AAPL'")[0]
    assert f"- Entrada aprox.: {es(aapl['entry_price_native'])} $" in text
    assert f"- Inversión: {es(aapl['cost_eur'])} €" in text
    assert "- Posiciones abiertas: 1" in text.splitlines()
    assert text.split("\n\n")[-1].startswith("Cartera\n- Capital/equity: ")


def test_rechazos_splits_y_ordenes_no_generan_mensaje(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    # Al cierre cabe, pero abre a 3.000 y se rechaza; otra señal deja una orden pendiente.
    data = {
        "SAP.DE": series("SAP.DE", [bar(99, 101, 98, 100, BUY), bar(3000, 3100, 2900, 3000, NEUTRAL)]),
        "BMW.DE": series("BMW.DE", [bar(99, 101, 98, 100, NEUTRAL), bar(99, 101, 98, 100, BUY)]),
    }
    result = run(store, data, today=START + timedelta(days=1))
    assert any("RECHAZADA" in event for event in result.events)
    assert any("ORDEN COMPRA BMW.DE" in event for event in result.events)
    assert messages(store) == []
