"""Motor de la cartera paper visible (superbot): flujo completo, precedencias e idempotencia.

Las barras llevan los indicadores ya puestos: el motor solo lee columnas, así
que cada test decide exactamente qué señal sale de cada cierre.
"""

from __future__ import annotations

import ast
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import pytest

from superbot.config import SizingParams, SuperbotConfig
from superbot.engine import BarSeries, PaperEngine, commission
from superbot.store import SuperbotStore

START = date(2026, 3, 2)  # lunes

BUY = {"sma_fast": 95.0, "sma_slow": 90.0, "rsi": 60.0, "atr": 2.0, "trend_break": False}
NEUTRAL = {"sma_fast": 105.0, "sma_slow": 90.0, "rsi": 60.0, "atr": 2.0, "trend_break": False}
BREAK = {"sma_fast": 120.0, "sma_slow": 90.0, "rsi": 40.0, "atr": 2.0, "trend_break": True}


class FakeFx:
    def __init__(self, rates: Optional[Dict[str, Dict[date, float]]] = None) -> None:
        self.rates = rates or {}

    def rate(self, currency: str, on: date) -> Optional[float]:
        if currency == "EUR":
            return 1.0
        table = self.rates.get(currency, {})
        eligible = [d for d in table if d <= on]
        return table[max(eligible)] if eligible else None


def bar(o: float, h: float, low: float, c: float, ind: dict) -> dict:
    return {"Open": o, "High": h, "Low": low, "Close": c, **ind}


def series(symbol: str, bars: List[dict], start: date = START, currency: str = "EUR") -> BarSeries:
    index = [start + timedelta(days=i) for i in range(len(bars))]
    market = "XETRA" if currency == "EUR" else "NASDAQ"
    return BarSeries(symbol=symbol, name=f"{symbol} SA", currency=currency, frame=pd.DataFrame(bars, index=index),
                     market=market)


def make_store(tmp_path: Path, start: date = START, **sizing: int) -> SuperbotStore:
    config = SuperbotConfig(initial_capital_eur=10_000.0, sizing=SizingParams(**sizing))
    store = SuperbotStore(tmp_path / "superbot.db")
    store.initialize(config, start, retrospective=False)
    return store


def run(store: SuperbotStore, data: Dict[str, BarSeries], fx: Optional[FakeFx] = None,
        today: date = START + timedelta(days=30)):
    run_id = store.start_run()
    return PaperEngine(store).process(data, fx or FakeFx(), run_id, today)


def rows(store: SuperbotStore, sql: str) -> List[sqlite3.Row]:
    return store.connect().execute(sql).fetchall()


def test_flujo_completo_senal_fill_trailing_stop_y_resultado(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    data = {"SAP.DE": series("SAP.DE", [
        bar(99, 101, 98, 100, BUY),          # d0: señal BUY al cierre
        bar(100, 104, 99, 103, NEUTRAL),     # d1: fill en la apertura (100), trailing 103-6=97
        bar(103, 111, 102, 109, NEUTRAL),    # d2: trailing 109-6=103 · T1 (≈ 110,08) tocado
        bar(108, 108, 102, 104, NEUTRAL),    # d3: mínimo 102 ≤ stop 103 → STOP a 103
    ])}
    result = run(store, data)

    position = rows(store, "SELECT * FROM positions")[0]
    assert position["status"] == "CLOSED"
    assert position["entry_date"] == (START + timedelta(days=1)).isoformat()
    assert position["exit_reason"].startswith("Mínimo")
    entry = 100 * (1 + 0.00025 + 0.0005)
    assert position["entry_price_native"] == pytest.approx(entry)
    assert position["t1_hit_date"] == (START + timedelta(days=2)).isoformat()
    assert position["exit_price_native"] == pytest.approx(103 * (1 - 0.00025 - 0.0005))

    # Tamaño iTrade: min(10.000·1,25 %/5 %, 10.000·25 %) = 2.500 EUR, unidades enteras.
    units = position["quantity"]
    assert units == int((2500 - commission(2500, store.config().costs)) // entry)

    fills = rows(store, "SELECT * FROM fills ORDER BY id")
    assert [f["kind"] for f in fills] == ["ENTRY", "STOP"]
    assert store.cash_eur() == pytest.approx(10_000 + sum(f["cash_delta_eur"] for f in fills))
    assert position["pnl_eur"] == pytest.approx(fills[1]["cash_delta_eur"] + fills[0]["cash_delta_eur"])
    assert result.bars == 4

    curve = store.equity_curve()
    assert len(curve) == 4
    assert curve[-1]["equity_eur"] == pytest.approx(store.cash_eur())
    assert curve[1]["invested_eur"] == pytest.approx(units * 103)


def test_repetir_la_ejecucion_no_duplica_nada(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    data = {"SAP.DE": series("SAP.DE", [bar(99, 101, 98, 100, BUY), bar(100, 104, 99, 103, NEUTRAL)])}
    run(store, data)
    counts = [len(rows(store, f"SELECT * FROM {t}")) for t in ("signals", "orders", "fills", "notifications")]
    second = run(store, data)
    assert second.bars == 0
    assert [len(rows(store, f"SELECT * FROM {t}")) for t in ("signals", "orders", "fills", "notifications")] == counts


def test_apertura_bajo_el_stop_sale_a_la_apertura(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    data = {"SAP.DE": series("SAP.DE", [
        bar(99, 101, 98, 100, BUY),
        bar(100, 101, 99, 100, NEUTRAL),     # fill 100; stop inicial ≈ 95,07; trailing 100-6=94 no lo baja
        bar(90, 92, 89, 91, NEUTRAL),        # apertura 90 bajo el stop → GAP_STOP a 90
    ])}
    run(store, data)
    fill = rows(store, "SELECT * FROM fills WHERE side = 'SELL'")[0]
    assert fill["kind"] == "GAP_STOP"
    assert fill["price_native"] == pytest.approx(90 * (1 - 0.00075))


def test_senal_de_salida_se_ejecuta_en_la_siguiente_apertura(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    data = {"SAP.DE": series("SAP.DE", [
        bar(99, 101, 98, 100, BUY),
        bar(100, 104, 99, 103, NEUTRAL),
        bar(103, 104, 101, 102, BREAK),      # rotura confirmada al cierre → orden SELL
        bar(101, 102, 100, 101, NEUTRAL),    # venta en la apertura (101)
    ])}
    run(store, data)
    position = rows(store, "SELECT * FROM positions")[0]
    assert position["status"] == "CLOSED"
    assert position["exit_date"] == (START + timedelta(days=3)).isoformat()
    assert rows(store, "SELECT kind FROM fills WHERE side = 'SELL'")[0]["kind"] == "SIGNAL_EXIT"
    sell_order = rows(store, "SELECT * FROM orders WHERE side = 'SELL'")[0]
    assert sell_order["status"] == "FILLED"


def test_la_barra_tardia_de_otra_plaza_se_procesa_en_la_ejecucion_siguiente(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    eu = series("SAP.DE", [bar(99, 101, 98, 100, NEUTRAL)] * 3)
    us_two = series("AAPL", [bar(99, 101, 98, 100, BUY), bar(100, 101, 99, 100, NEUTRAL)], currency="USD")
    fx = FakeFx({"USD": {START: 0.9}})
    run(store, {"SAP.DE": eu, "AAPL": us_two}, fx)
    assert rows(store, "SELECT COUNT(*) FROM fills")[0][0] == 1

    # La tercera barra de AAPL llega en una ejecución posterior: se procesa aunque
    # SAP.DE ya haya pasado de esa fecha.
    us_three = series("AAPL", [bar(99, 101, 98, 100, BUY), bar(100, 101, 99, 100, NEUTRAL),
                               bar(100, 101, 80, 85, NEUTRAL)], currency="USD")
    result = run(store, {"SAP.DE": eu, "AAPL": us_three}, fx)
    assert result.bars == 1
    assert rows(store, "SELECT status FROM positions")[0]["status"] == "CLOSED"


def test_fx_del_fill_es_el_de_su_sesion(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    fx = FakeFx({"USD": {START: 0.90, START + timedelta(days=1): 0.80}})
    data = {"AAPL": series("AAPL", [bar(99, 101, 98, 100, BUY), bar(100, 101, 99, 100, NEUTRAL)], currency="USD")}
    run(store, data, fx)
    fill = rows(store, "SELECT * FROM fills")[0]
    assert fill["fx_rate"] == pytest.approx(0.80)
    assert fill["notional_eur"] == pytest.approx(fill["quantity"] * fill["price_native"] * 0.80)


def _momentum_series(symbol: str, first_close: float) -> BarSeries:
    """70 barras de ``first_close`` a 100 (sin señal) y una última con señal BUY."""
    flat = {**NEUTRAL, "sma_fast": 200.0}
    closes = [first_close + (100 - first_close) * i / 69 for i in range(70)]
    bars = [bar(c, c, c, c, flat) for c in closes[:-1]] + [bar(99, 101, 98, 100, BUY), bar(100, 101, 99, 100, NEUTRAL)]
    return series(symbol, bars)


def test_con_un_hueco_solo_compra_la_de_mayor_momentum(tmp_path: Path) -> None:
    store = make_store(tmp_path, max_positions=1)
    # AAA.DE sube de 50 a 100 y BBB.DE de 95 a 100: gana AAA aunque el desempate
    # alfabético favorecería a BBB.
    run(store, {"AAA.DE": _momentum_series("AAA.DE", 50.0), "BBB.DE": _momentum_series("BBB.DE", 95.0)})
    orders = rows(store, "SELECT * FROM orders")
    assert [(o["symbol"], o["status"]) for o in orders] == [("AAA.DE", "FILLED")]
    momentum = rows(store, "SELECT momentum FROM signals")[0]["momentum"]
    assert momentum is not None and momentum > 0


def test_escalonado_limita_las_compras_por_sesion(tmp_path: Path) -> None:
    store = make_store(tmp_path, max_new_positions_per_session=2)
    data = {s: series(s, [bar(99, 101, 98, 100, BUY), bar(100, 101, 99, 100, NEUTRAL)])
            for s in ("AAA.DE", "BBB.DE", "CCC.DE")}
    run(store, data)
    assert rows(store, "SELECT COUNT(*) FROM orders WHERE side = 'BUY'")[0][0] == 2


def test_presupuesto_bajo_el_minimo_no_genera_orden(tmp_path: Path) -> None:
    store = SuperbotStore(tmp_path / "superbot.db")
    store.initialize(SuperbotConfig(initial_capital_eur=500.0), START, retrospective=False)
    run(store, {"SAP.DE": series("SAP.DE", [bar(99, 101, 98, 100, BUY), bar(100, 101, 99, 100, NEUTRAL)])})
    assert rows(store, "SELECT COUNT(*) FROM orders")[0][0] == 0


def test_un_valor_que_no_cabe_no_genera_orden_ni_quita_el_hueco(tmp_path: Path) -> None:
    store = make_store(tmp_path, max_positions=1)
    data = {
        "NVR": series("NVR", [bar(9000, 9100, 8900, 9000, BUY), bar(9000, 9100, 8900, 9000, NEUTRAL)]),
        "SAP.DE": series("SAP.DE", [bar(99, 101, 98, 100, BUY), bar(100, 101, 99, 100, NEUTRAL)]),
    }
    run(store, data)
    assert [(o["symbol"], o["status"]) for o in rows(store, "SELECT * FROM orders")] == [("SAP.DE", "FILLED")]


def test_una_apertura_que_ya_no_cabe_se_rechaza_en_el_fill(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    # Al cierre cabe (100), pero abre a 3.000: una unidad supera los 2.500 EUR.
    data = {"SAP.DE": series("SAP.DE", [bar(99, 101, 98, 100, BUY), bar(3000, 3100, 2900, 3000, NEUTRAL)])}
    run(store, data, today=START + timedelta(days=1))
    order = rows(store, "SELECT * FROM orders")[0]
    assert order["status"] == "REJECTED"
    assert store.cash_eur() == pytest.approx(10_000)
    # Un rechazo no es una operación: queda en orders y en el dashboard, no en Telegram.
    assert rows(store, "SELECT COUNT(*) FROM notifications")[0][0] == 0


def test_orden_de_compra_caduca_sin_barra(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    index = [START, START + timedelta(days=10)]
    frame = pd.DataFrame([bar(99, 101, 98, 100, BUY), bar(100, 101, 99, 100, NEUTRAL)], index=index)
    run(store, {"SAP.DE": BarSeries("SAP.DE", "SAP", "EUR", frame)})
    assert rows(store, "SELECT status FROM orders")[0]["status"] == "CANCELLED"
    assert rows(store, "SELECT COUNT(*) FROM fills")[0][0] == 0


def test_barras_anteriores_al_inicio_no_operan(tmp_path: Path) -> None:
    store = make_store(tmp_path, start=START + timedelta(days=1))
    data = {"SAP.DE": series("SAP.DE", [bar(99, 101, 98, 100, BUY), bar(100, 101, 99, 100, NEUTRAL)])}
    run(store, data)
    assert rows(store, "SELECT COUNT(*) FROM signals")[0][0] == 0


def test_eventos_antiguos_no_se_avisan_uno_a_uno(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    data = {"SAP.DE": series("SAP.DE", [bar(99, 101, 98, 100, BUY), bar(100, 101, 99, 100, NEUTRAL)])}
    run(store, data, today=START + timedelta(days=60))
    assert rows(store, "SELECT COUNT(*) FROM fills")[0][0] == 1
    assert rows(store, "SELECT COUNT(*) FROM notifications")[0][0] == 0


def test_la_base_se_niega_a_usar_las_del_asesor_o_t025(tmp_path: Path) -> None:
    for name in ("paper.db", "intradia.db", "PAPER.DB"):
        with pytest.raises(ValueError):
            SuperbotStore(tmp_path / name)


def test_no_se_puede_inicializar_dos_veces(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    with pytest.raises(ValueError):
        store.initialize(SuperbotConfig(), START, retrospective=False)


def test_superbot_no_importa_t025_ni_la_investigacion() -> None:
    raiz = Path(__file__).resolve().parent.parent / "superbot"
    prohibidos = ("paper", "advisor.research", "advisor.analysis.scoring", "advisor.analysis.opportunity")
    culpables = []
    for ruta in sorted(raiz.rglob("*.py")):
        for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
            modulos: List[str] = []
            if isinstance(nodo, ast.Import):
                modulos = [alias.name for alias in nodo.names]
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                modulos = [nodo.module]
            for modulo in modulos:
                if any(modulo == p or modulo.startswith(p + ".") for p in prohibidos):
                    culpables.append(f"{ruta.name}: {modulo}")
    assert culpables == []


def test_compra_pendiente_caduca_aunque_el_simbolo_deje_de_tener_barras(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    run(store, {"SAP.DE": series("SAP.DE", [bar(99, 101, 98, 100, BUY)])})
    other = series("OTHER.DE", [bar(99, 101, 98, 100, NEUTRAL)] * 12)
    run(store, {"OTHER.DE": other}, today=START + timedelta(days=11))
    order = rows(store, "SELECT * FROM orders WHERE symbol = 'SAP.DE'")[0]
    assert order["status"] == "CANCELLED"


def test_venta_sin_fx_del_dia_usa_el_ultimo_conocido(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    fx = FakeFx({"USD": {START: 0.9}})
    data = {"AAPL": series("AAPL", [bar(99, 101, 98, 100, BUY), bar(100, 104, 99, 103, NEUTRAL),
                                     bar(103, 104, 101, 102, BREAK), bar(101, 102, 100, 101, NEUTRAL)],
                           currency="USD")}
    run(store, data, fx)
    assert rows(store, "SELECT status FROM positions")[0]["status"] == "CLOSED"

    store2 = make_store(tmp_path / "b")
    run(store2, {"AAPL": series("AAPL", data["AAPL"].frame.iloc[:3].to_dict("records"), currency="USD")}, fx)
    # Desaparece el tipo de cambio: la venta pendiente se ejecuta con el último FX de la posición.
    run(store2, data, FakeFx())
    position = rows(store2, "SELECT * FROM positions")[0]
    assert position["status"] == "CLOSED"
    assert position["exit_fx"] == pytest.approx(0.9)


def test_simbolo_que_llega_tarde_no_opera_en_el_pasado_ni_reescribe_la_curva(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    neutral = [bar(99, 101, 98, 100, NEUTRAL)] * 10
    run(store, {"AAA.DE": series("AAA.DE", neutral)})
    curve_before = {r["date"]: r["equity_eur"] for r in store.equity_curve()}

    # BBB carga por primera vez con una señal en d0: no debe abrir nada en el pasado.
    late = series("BBB.DE", [bar(99, 101, 98, 100, BUY)] + [bar(100, 101, 99, 100, BUY)] * 9)
    run(store, {"AAA.DE": series("AAA.DE", neutral), "BBB.DE": late})
    assert rows(store, "SELECT COUNT(*) FROM orders")[0][0] == 0
    assert {r["date"]: r["equity_eur"] for r in store.equity_curve()} == curve_before


def test_barra_atrasada_en_su_plaza_gestiona_la_posicion_pero_no_compra(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    fx = FakeFx({"USD": {START: 0.9}})
    msft = series("MSFT", [bar(99, 101, 98, 100, NEUTRAL)] * 6, currency="USD")
    aapl = [bar(99, 101, 98, 100, BUY), bar(100, 101, 99, 100, NEUTRAL)]
    run(store, {"MSFT": msft, "AAPL": series("AAPL", aapl, currency="USD")}, fx)
    # AAPL llega con cuatro sesiones de retraso respecto a MSFT (misma plaza):
    # la caída sí cierra la posición; la señal BUY atrasada no abre otra.
    aapl_late = [*aapl, bar(100, 101, 80, 85, NEUTRAL), bar(99, 101, 98, 100, BUY), bar(100, 101, 99, 100, NEUTRAL)]
    run(store, {"MSFT": msft, "AAPL": series("AAPL", aapl_late, currency="USD")}, fx)
    assert [r["status"] for r in rows(store, "SELECT status FROM positions")] == ["CLOSED"]
    assert rows(store, "SELECT COUNT(*) FROM orders WHERE side = 'BUY'")[0][0] == 1


def test_split_reescala_la_posicion_sin_perdida_ficticia(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    split = {**NEUTRAL, "sma_fast": 52.0, "sma_slow": 45.0, "atr": 1.0, "Stock Splits": 2.0}
    data = {"SAP.DE": series("SAP.DE", [
        bar(99, 101, 98, 100, BUY),
        bar(100, 104, 99, 103, NEUTRAL),     # fill 100,075; trailing 97
        bar(51, 52, 50.5, 51.5, split),      # split 2:1: abre a 51 (= 102 antes)
    ])}
    run(store, data, today=START + timedelta(days=2))
    position = rows(store, "SELECT * FROM positions")[0]
    entry_units = rows(store, "SELECT quantity FROM fills")[0]["quantity"]
    assert position["status"] == "OPEN"
    assert position["quantity"] == pytest.approx(entry_units * 2)
    assert position["stop"] == pytest.approx(48.5)
    assert position["entry_price_native"] == pytest.approx(100 * 1.00075 / 2)
    # El split no se avisa: el único mensaje es el de la compra.
    [message] = rows(store, "SELECT text FROM notifications")
    assert "COMPRAR" in message["text"] and "SPLIT" not in message["text"]


def test_europa_retrasada_respecto_a_eeuu_sigue_comprando(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    fx = FakeFx({"USD": {START: 0.9}})
    us = series("AAPL", [bar(99, 101, 98, 100, NEUTRAL)] * 6, currency="USD")
    eu_short = series("SAP.DE", [bar(99, 101, 98, 100, NEUTRAL)] * 3)
    run(store, {"AAPL": us, "SAP.DE": eu_short}, fx)
    # Europa llega con tres sesiones de retraso y una señal: no es «atrasada»
    # respecto a su propia plaza, así que compra.
    eu = series("SAP.DE", [bar(99, 101, 98, 100, NEUTRAL)] * 3
                + [bar(99, 101, 98, 100, BUY), bar(100, 101, 99, 100, NEUTRAL)])
    run(store, {"AAPL": us, "SAP.DE": eu}, fx)
    assert [(o["symbol"], o["status"]) for o in rows(store, "SELECT * FROM orders")] == [("SAP.DE", "FILLED")]


def test_flujo_normal_europa_y_luego_eeuu_misma_sesion(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    fx = FakeFx({"USD": {START: 0.9}})
    eu = series("SAP.DE", [bar(99, 101, 98, 100, NEUTRAL)])
    # 18:15: Europa cerrada; EE. UU. aún sin barra de la sesión.
    run(store, {"SAP.DE": eu, "AAPL": series("AAPL", [], currency="USD")}, fx)
    # 22:45: llega la barra de EE. UU. de la misma fecha, con señal.
    run(store, {"SAP.DE": eu, "AAPL": series("AAPL", [bar(99, 101, 98, 100, BUY)], currency="USD")}, fx)
    assert [(o["symbol"], o["status"]) for o in rows(store, "SELECT * FROM orders")] == [("AAPL", "PENDING")]


def test_compra_pendiente_se_ejecuta_aunque_su_barra_llegue_tarde(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    fx = FakeFx({"USD": {START: 0.9}})
    msft = [bar(99, 101, 98, 100, NEUTRAL)]
    aapl = [bar(99, 101, 98, 100, BUY)]
    run(store, {"MSFT": series("MSFT", msft, currency="USD"), "AAPL": series("AAPL", aapl, currency="USD")}, fx)
    # MSFT avanza cinco sesiones; la barra siguiente de AAPL llega después.
    msft5 = msft * 6
    run(store, {"MSFT": series("MSFT", msft5, currency="USD"), "AAPL": series("AAPL", aapl, currency="USD")}, fx,
        today=START + timedelta(days=5))
    aapl2 = [*aapl, bar(100, 101, 99, 100, NEUTRAL)]
    run(store, {"MSFT": series("MSFT", msft5, currency="USD"), "AAPL": series("AAPL", aapl2, currency="USD")}, fx,
        today=START + timedelta(days=6))
    assert rows(store, "SELECT status FROM orders")[0]["status"] == "FILLED"
