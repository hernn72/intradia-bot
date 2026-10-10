from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from superbot import LABEL
from superbot.config import SuperbotConfig
from superbot.dashboard import build_stats, render_html
from superbot.store import SuperbotStore


def _store(path: Path, retrospective: bool = True) -> SuperbotStore:
    store = SuperbotStore(path / "superbot.db")
    store.initialize(SuperbotConfig(), date(2026, 1, 2), retrospective=retrospective)
    return store


def _insert_fixture(store: SuperbotStore) -> None:
    conn = store.connect()
    conn.execute(
        "INSERT INTO runs (id, started_at, finished_at, status, symbols_ok, symbols_err, bars, detail) "
        "VALUES (1, '2026-01-02T08:00:00Z', '2026-01-02T08:01:00Z', 'OK', 3, 0, 3, 'ok')"
    )
    for idx, symbol in enumerate(("OPEN", "WIN", "LOSS"), start=1):
        conn.execute(
            "INSERT INTO signals (id, run_id, symbol, bar_date, action, close, reason) "
            "VALUES (?, 1, ?, '2026-01-02', 'BUY', 100, 'entrada')",
            (idx, symbol),
        )
        conn.execute(
            "INSERT INTO orders (id, signal_id, symbol, side, status, signal_date, created_at, resolved_date, detail) "
            "VALUES (?, ?, ?, 'BUY', 'FILLED', '2026-01-02', '2026-01-02T08:00:00Z', '2026-01-03', 'fill')",
            (idx, idx, symbol),
        )
    conn.execute(
        "INSERT INTO positions (id, symbol, name, currency, status, quantity, entry_order_id, entry_date, "
        "entry_price_native, entry_fx, cost_eur, initial_stop, stop, target1, target2, t1_hit_date, "
        "last_date, last_close, last_fx) "
        "VALUES (1, 'OPEN', '<script>alert(1)</script>', 'USD', 'OPEN', 10, 1, '2026-01-03', "
        "100, 1, 1000, 95, 98, 110, 120, '2026-01-04', '2026-01-05', 110, 1)"
    )
    conn.execute(
        "INSERT INTO positions (id, symbol, name, currency, status, quantity, entry_order_id, entry_date, "
        "entry_price_native, entry_fx, cost_eur, initial_stop, stop, target1, target2, last_date, last_close, "
        "last_fx, exit_date, exit_price_native, exit_fx, exit_reason, proceeds_eur, pnl_eur, pnl_pct) "
        "VALUES (2, 'WIN', 'Ganadora', 'EUR', 'CLOSED', 10, 2, '2026-01-03', 100, 1, 1000, 95, 98, "
        "110, 120, '2026-01-06', 120, 1, '2026-01-06', 120, 1, 'Señal', 1200, 200, 0.2)"
    )
    conn.execute(
        "INSERT INTO positions (id, symbol, name, currency, status, quantity, entry_order_id, entry_date, "
        "entry_price_native, entry_fx, cost_eur, initial_stop, stop, target1, target2, last_date, last_close, "
        "last_fx, exit_date, exit_price_native, exit_fx, exit_reason, proceeds_eur, pnl_eur, pnl_pct) "
        "VALUES (3, 'LOSS', 'Perdedora', 'EUR', 'CLOSED', 10, 3, '2026-01-03', 100, 1, 1000, 95, 98, "
        "110, 120, '2026-01-07', 90, 1, '2026-01-07', 90, 1, 'Stop', 900, -100, -0.1)"
    )
    fills = [
        (1, 1, 1, "OPEN", "BUY", "ENTRY", "2026-01-03", "USD", 100, 1, 10, 999, 1, -1000),
        (2, 2, 2, "WIN", "BUY", "ENTRY", "2026-01-03", "EUR", 100, 1, 10, 999, 1, -1000),
        (3, 2, None, "WIN", "SELL", "SIGNAL_EXIT", "2026-01-06", "EUR", 120, 1, 10, 1201, 1, 1200),
        (4, 3, 3, "LOSS", "BUY", "ENTRY", "2026-01-03", "EUR", 100, 1, 10, 999, 1, -1000),
        (5, 3, None, "LOSS", "SELL", "STOP", "2026-01-07", "EUR", 90, 1, 10, 901, 1, 900),
    ]
    conn.executemany(
        "INSERT INTO fills (id, position_id, order_id, symbol, side, kind, bar_date, currency, price_native, "
        "fx_rate, quantity, notional_eur, commission_eur, cash_delta_eur) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        fills,
    )
    conn.executemany(
        "INSERT INTO equity_snapshots (date, cash_eur, invested_eur, equity_eur, open_positions) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            ("2026-01-03", 7000, 3000, 10000, 3),
            ("2026-01-04", 7000, 3500, 10500, 3),
            ("2026-01-05", 9100, 875, 9975, 1),
            ("2026-01-06", 9100, 1100, 10200, 1),
        ],
    )
    conn.commit()


def test_build_stats_numbers(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        _insert_fixture(store)
        stats = build_stats(store)
    finally:
        store.close()

    assert stats["cash_eur"] == pytest.approx(9100)
    assert stats["invested_eur"] == pytest.approx(1100)
    assert stats["equity_eur"] == pytest.approx(10200)
    assert stats["realized_pnl_eur"] == pytest.approx(100)
    assert stats["open_pnl_eur"] == pytest.approx(100)
    assert stats["win_rate"] == pytest.approx(0.5)
    assert stats["max_drawdown_pct"] == pytest.approx(-0.05)
    assert stats["total_commissions_eur"] == pytest.approx(5)


def test_render_html_contains_core_content_and_escapes(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        _insert_fixture(store)
        page = render_html(store, "2026-01-08 10:00")
    finally:
        store.close()

    assert LABEL in page
    assert "ARRANQUE RETROSPECTIVO desde 2026-01-02" in page
    assert "OPEN" in page
    assert "WIN" in page
    assert "LOSS" in page
    assert "<svg" in page
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_empty_store_renders_without_error(tmp_path: Path) -> None:
    store = _store(tmp_path, retrospective=False)
    try:
        page = render_html(store, "2026-01-02 09:00")
    finally:
        store.close()

    assert LABEL in page
    assert "sin datos todavía" in page
