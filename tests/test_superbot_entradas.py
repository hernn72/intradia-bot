"""Sin entradas: lo que una ejecución degradada puede y no puede hacer.

Con datos insuficientes la cartera no abre nada, pero tampoco deja de proteger lo
que ya tiene: ventas pendientes, stops y trailing siguen. Los símbolos sin
posición no avanzan: una ejecución sana posterior ejecuta sus órdenes en su sesión
y, de varias sesiones sin entradas, solo la última puede dar señales de compra.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import pytest

from superbot.config import SuperbotConfig
from superbot.engine import BarSeries, PaperEngine
from superbot.store import SuperbotStore

START = date(2026, 3, 2)
BUY = {"sma_fast": 95.0, "sma_slow": 90.0, "rsi": 60.0, "atr": 2.0, "trend_break": False}
HOLD = {"sma_fast": 105.0, "sma_slow": 90.0, "rsi": 60.0, "atr": 2.0, "trend_break": False}
EXIT = {**HOLD, "trend_break": True}


class NoFx:
    def rate(self, currency: str, on: date) -> Optional[float]:
        return 1.0


def bar(o: float, h: float, low: float, c: float, ind: dict = HOLD) -> dict:
    return {"Open": o, "High": h, "Low": low, "Close": c, **ind, "Stock Splits": 0.0}


FLAT = bar(100, 101, 99, 100)
SIGNAL = bar(99, 101, 98, 100, BUY)


def series(symbol: str, bars: List[dict]) -> BarSeries:
    index = [START + timedelta(days=i) for i in range(len(bars))]
    return BarSeries(symbol=symbol, name=symbol, currency="EUR", frame=pd.DataFrame(bars, index=index), market="XETRA")


def data(**bars: List[dict]) -> Dict[str, BarSeries]:
    return {f"{symbol}.DE": series(f"{symbol}.DE", rows) for symbol, rows in bars.items()}


@pytest.fixture
def store(tmp_path: Path) -> SuperbotStore:
    created = SuperbotStore(tmp_path / "superbot.db")
    created.initialize(SuperbotConfig(initial_capital_eur=10_000.0), START, retrospective=False)
    return created


def run(store: SuperbotStore, frames: Dict[str, BarSeries], entries: bool = True):
    return PaperEngine(store).process(frames, NoFx(), store.start_run(), START + timedelta(days=5),
                                      allow_entries=entries)


def table(store: SuperbotStore, name: str) -> List[dict]:
    drop = {"id", "signal_id", "position_id", "order_id", "entry_order_id", "run_id", "created_at"}
    rows = store.connect().execute(f"SELECT * FROM {name} ORDER BY symbol, 1").fetchall()
    return [{k: v for k, v in dict(row).items() if k not in drop} for row in rows]


def test_sin_entradas_no_nace_ninguna_senal_de_compra(store: SuperbotStore) -> None:
    run(store, data(SAP=[SIGNAL, FLAT]), entries=False)
    assert store.orders() == []
    assert store.connect().execute("SELECT COUNT(*) FROM signals").fetchone()[0] == 0
    assert "SAP.DE" not in store.last_bar_dates()


def test_sin_entradas_una_compra_pendiente_espera(store: SuperbotStore) -> None:
    run(store, data(SAP=[SIGNAL]))
    run(store, data(SAP=[SIGNAL, FLAT]), entries=False)
    assert store.open_positions() == []
    assert [o["status"] for o in store.orders()] == ["PENDING"]
    assert store.last_bar_dates()["SAP.DE"] == START


def test_sin_entradas_se_ejecutan_stops_y_ventas_pendientes(store: SuperbotStore) -> None:
    run(store, data(SAP=[SIGNAL, FLAT], ALV=[SIGNAL, FLAT]))
    assert len(store.open_positions()) == 2
    falls = bar(100, 100, 80, 85)
    run(store, data(SAP=[SIGNAL, FLAT, falls], ALV=[SIGNAL, FLAT, bar(100, 101, 99, 100, EXIT)]), entries=False)
    assert [p["symbol"] for p in store.open_positions()] == ["ALV.DE"]
    assert [o["side"] for o in store.pending_orders()] == ["SELL"]
    run(store, data(ALV=[SIGNAL, FLAT, bar(100, 101, 99, 100, EXIT), FLAT]), entries=False)
    assert store.open_positions() == []
    assert [f["kind"] for f in store.fills() if f["side"] == "SELL"] == ["STOP", "SIGNAL_EXIT"]


def test_sin_entradas_una_posicion_cerrada_no_recompra_en_la_sesion_siguiente(store: SuperbotStore) -> None:
    run(store, data(SAP=[SIGNAL, FLAT]))
    bars = [SIGNAL, FLAT, bar(100, 100, 80, 85), bar(85, 90, 84, 88, BUY), bar(88, 90, 87, 88)]
    run(store, data(SAP=bars), entries=False)
    assert store.open_positions() == []
    assert [o["side"] for o in store.orders()] == ["BUY"]


def test_tras_una_ejecucion_sin_entradas_la_cartera_queda_igual_que_sin_ella(tmp_path: Path) -> None:
    # Posición en SAP; ALV da la señal y su compra llega justo en la sesión degradada.
    held = [SIGNAL, FLAT, FLAT, bar(101, 103, 100, 102), bar(102, 104, 101, 103)]
    other = [FLAT, FLAT, SIGNAL, bar(100, 102, 99, 101), bar(101, 103, 100, 102)]

    def portfolio(name: str) -> SuperbotStore:
        created = SuperbotStore(tmp_path / name / "superbot.db")
        created.initialize(SuperbotConfig(initial_capital_eur=10_000.0), START, retrospective=False)
        run(created, data(SAP=held[:3], ALV=other[:3]))
        return created

    degraded, healthy = portfolio("degradada"), portfolio("sana")
    run(degraded, data(SAP=held[:4], ALV=other[:4]), entries=False)
    assert len(degraded.open_positions()) == 1
    run(degraded, data(SAP=held, ALV=other))
    run(healthy, data(SAP=held[:4], ALV=other[:4]))
    run(healthy, data(SAP=held, ALV=other))
    for name in ("positions", "fills", "orders", "signals", "equity_snapshots", "symbol_state"):
        if name == "equity_snapshots":
            assert degraded.equity_curve() == healthy.equity_curve()
        else:
            assert table(degraded, name) == table(healthy, name), name


def test_varias_sesiones_sin_entradas_no_compran_en_el_pasado(store: SuperbotStore) -> None:
    # Señal de ALV en una sesión intermedia: no se recupera. La de la última sesión sí.
    held = [SIGNAL, FLAT, FLAT, FLAT, FLAT, FLAT]
    other = [FLAT, FLAT, SIGNAL, FLAT, SIGNAL, FLAT]
    run(store, data(SAP=held[:2], ALV=other[:2]))
    run(store, data(SAP=held[:5], ALV=other[:5]), entries=False)
    run(store, data(SAP=held, ALV=other))
    [fill] = [f for f in store.fills() if f["symbol"] == "ALV.DE"]
    assert fill["bar_date"] == (START + timedelta(days=5)).isoformat()
    assert len(table(store, "signals")) == 2


def test_compra_pendiente_recuperada_entra_en_la_curva_de_su_sesion(store: SuperbotStore) -> None:
    held = [SIGNAL, FLAT, FLAT, FLAT, FLAT]
    other = [FLAT, SIGNAL, FLAT, FLAT, FLAT]
    run(store, data(SAP=held[:2], ALV=other[:2]))
    run(store, data(SAP=held[:4], ALV=other[:4]), entries=False)
    run(store, data(SAP=held, ALV=other))
    curve = {row["date"]: row["open_positions"] for row in store.equity_curve()}
    assert curve[(START + timedelta(days=2)).isoformat()] == 2
