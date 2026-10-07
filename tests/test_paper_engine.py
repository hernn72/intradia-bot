"""T-025 — ``engine_v1`` frente a ``p6_sim`` (test de equivalencia, ficha §3.4 y §16) y reglas del motor."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List

import pytest

from advisor.research.p6_sim import (
    LEDGER_COLUMNS,
    FxTable,
    Signal,
    SimSpec,
    simulate,
    simulate_benchmark,
)
from paper.engine_v1 import (
    EV_DATA_LOSS_SUSPENDED,
    EV_DATA_RESUMED,
    EV_NO_EVALUABLE_DATA_LOSS,
    EV_NO_EVALUABLE_ENGINE_UNRUNNABLE,
    EXIT_COHORT_CLOSED,
    EXIT_CORPORATE_ACTION,
    KIND_BENCHMARK,
    STOP_FX,
    STOP_HORIZON,
    AssetMeta,
    AssetView,
    Engine,
    EngineSpec,
    EngineView,
    market_check,
    requested_weight,
)
from tests.paper_synthetic import build, view_at

UTC = timezone.utc


def _project(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{k: row[k] for k in LEDGER_COLUMNS} for row in rows]


def _run_incremental(syn, spec: EngineSpec, cuts: List[datetime]):
    engine = Engine(spec)
    rows: List[Dict[str, Any]] = []
    snapshots = []
    outcomes = []
    for cut in cuts:
        result = engine.advance(view_at(syn, cut))
        rows.extend(result.rows)
        snapshots.extend(result.snapshots)
        outcomes.extend(result.outcomes)
    return engine, rows, snapshots, outcomes


def _cuts(syn, every: int = 1) -> List[datetime]:
    """Una ejecución por día a las 06:00 UTC, como una pasada programada, más un último corte lejano."""

    cuts = [datetime.combine(d, time(6, 0), UTC) for d in syn.days[1::every]]
    cuts.append(datetime.combine(syn.days[-1] + timedelta(days=3), time(0, 0), UTC))
    return cuts


@pytest.mark.parametrize("seed,risk,cap", [(7, 0.5, 10.0), (11, 2.0, 25.0), (23, 3.0, 40.0)])
def test_equivalencia_con_p6_sim_ledger_fila_a_fila(seed: int, risk: float, cap: float) -> None:
    syn = build(seed=seed)
    sim_spec = SimSpec(policy_id="B2", system_sha256="x" * 64, risk_pct=risk, max_position_pct=cap)
    p6 = simulate(syn.market, syn.signals, syn.fx, sim_spec)
    spec = EngineSpec(policy_id="B2", system_sha256="x" * 64, risk_pct=risk, max_position_pct=cap)
    _engine, rows, snapshots, outcomes = _run_incremental(syn, spec, _cuts(syn))

    assert _project(rows) == p6.ledger
    assert [o.trade for o in sorted(outcomes, key=lambda o: o.trade.position_id)] == p6.trades
    assert [(s.day, s.equity, s.cash, s.positions) for s in snapshots] == [
        (s.day, s.equity, s.cash, s.positions) for s in p6.snapshots
    ]
    counters = p6.counters
    assert counters.get("entradas", 0) > 10
    if cap >= 25.0:
        # Lote con cash escaso: hay rechazos por cash y el desempate decide quién entra.
        assert counters.get("INSUFFICIENT_CASH", 0) > 0
    assert counters.get("IGNORED_ALREADY_OPEN", 0) > 0
    assert counters.get("dividendos_abonados", 0) > 0


def test_el_troceo_no_cambia_el_resultado() -> None:
    syn = build(seed=5)
    spec = EngineSpec(policy_id="S2", system_sha256="y" * 64, risk_pct=2.0, max_position_pct=25.0)
    _e1, a, _s1, _o1 = _run_incremental(syn, spec, _cuts(syn, every=1))
    _e2, b, _s2, _o2 = _run_incremental(syn, spec, _cuts(syn, every=7))
    _e3, c, _s3, _o3 = _run_incremental(syn, spec, [datetime(2027, 1, 1, tzinfo=UTC)])
    assert a == b == c


def test_reconstruccion_reproducible_y_avance_repetido_sin_duplicados() -> None:
    syn = build(seed=9)
    spec = EngineSpec(policy_id="B2", system_sha256="z" * 64)
    cuts = _cuts(syn)
    _e1, first, _s, _o = _run_incremental(syn, spec, cuts)
    _e2, second, _s2, _o2 = _run_incremental(syn, spec, cuts)
    assert first == second
    engine = Engine(spec)
    for cut in cuts[:40]:
        engine.advance(view_at(syn, cut))
    again = engine.advance(view_at(syn, cuts[39]))
    assert again.rows == [] and again.snapshots == []


def test_benchmark_equivalente_a_p6_salvo_la_venta_final() -> None:
    syn = build(seed=13, n_assets=9)
    sim_spec = SimSpec(policy_id="BH", system_sha256="b" * 64)
    p6 = simulate_benchmark(syn.market, syn.fx, sim_spec)
    spec = EngineSpec(policy_id="BH", system_sha256="b" * 64, kind=KIND_BENCHMARK, universe_size=len(syn.market.assets))
    _engine, rows, snapshots, _outcomes = _run_incremental(syn, spec, _cuts(syn))
    expected = [r for r in p6.ledger if r["event_type"] != "BH_SELL_FINAL"]
    got = _project(rows)
    assert got[: len(expected)] == expected[: len(got)]
    assert len(got) == len(expected)
    last_day = syn.days[-1]
    assert [(s.day, s.equity) for s in snapshots if s.day != last_day] == [
        (s.day, s.equity) for s in p6.snapshots if s.day != last_day
    ]


def test_una_barra_que_falta_detiene_la_frontera_del_libro() -> None:
    syn = build(seed=7)
    spec = EngineSpec(policy_id="B2", system_sha256="x" * 64)
    engine = Engine(spec)
    cuts = _cuts(syn)
    for cut in cuts[:30]:
        engine.advance(view_at(syn, cut))
    held = sorted(engine.positions) or sorted(engine.pending)
    assert held, "el escenario necesita una posición abierta"
    asset = held[0]
    hidden_from = cuts[30] - timedelta(days=1)
    result = engine.advance(view_at(syn, cuts[33], hide={asset: hidden_from}))
    assert result.stop_reason == STOP_HORIZON
    assert asset in result.stalled_on
    # Cuando la barra llega, el libro sigue y el resultado final es el mismo que sin retraso.
    rows = [*result.rows]
    for cut in cuts[33:]:
        rows.extend(engine.advance(view_at(syn, cut)).rows)
    full = Engine(spec)
    reference: List[Dict[str, Any]] = []
    for cut in cuts:
        reference.extend(full.advance(view_at(syn, cut)).rows)
    prefix_engine = Engine(spec)
    prefix: List[Dict[str, Any]] = []
    for cut in cuts[:30]:
        prefix.extend(prefix_engine.advance(view_at(syn, cut)).rows)
    assert _project(prefix + rows) == _project(reference)


def test_fx_ausente_hace_esperar_al_evento() -> None:
    syn = build(seed=7)
    spec = EngineSpec(policy_id="B2", system_sha256="x" * 64)
    engine = Engine(spec)
    cut = datetime.combine(syn.days[20], time(6, 0), UTC)
    result = engine.advance(view_at(syn, cut, fx_horizon=datetime.combine(syn.days[10], time(0, 0), UTC)))
    assert result.stop_reason == STOP_FX


# ---------------------------------------------------------------------------- escenarios dirigidos


def _series(symbol: str, bars: List[tuple], *, dividends=None, splits=None, horizon=None, data_loss=False,
            terminal=None, market: str = "XEUR", currency: str = "EUR") -> AssetView:
    days = tuple(b[0] for b in bars)
    return AssetView(
        meta=AssetMeta(symbol, market, currency),
        session_dates=days,
        open_utc=tuple(datetime.combine(d, time(8), UTC) for d in days),
        close_utc=tuple(datetime.combine(d, time(16, 30), UTC) for d in days),
        open=tuple(float(b[1]) for b in bars), high=tuple(float(b[2]) for b in bars),
        low=tuple(float(b[3]) for b in bars), close=tuple(float(b[4]) for b in bars),
        dividends=dividends or {}, splits=splits or {}, horizon=horizon, data_loss=data_loss, terminal=terminal,
    )


def _days(n: int) -> List[date]:
    out, d = [], date(2026, 3, 2)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _view(series: AssetView, signals, limit: datetime, **kw) -> EngineView:
    return EngineView(
        assets={series.meta.symbol: series}, fx=FxTable({}), signals=tuple(signals), start=series.session_dates[0],
        snapshot_days=series.session_dates, limit=limit, **kw,
    )


def _signal(symbol: str, day: date, j: int, stop: float, target: float, entry_max: float) -> Signal:
    return Signal(f"{symbol}|swing|{day}", symbol, j, datetime.combine(day, time(17), UTC), stop, target, entry_max)


def test_stop_y_objetivo_en_la_misma_barra_gana_el_stop() -> None:
    d = _days(4)
    s = _series("X", [(d[0], 100, 101, 99, 100), (d[1], 100, 101, 99, 100), (d[2], 100, 120, 80, 100), (d[3], 100, 101, 99, 100)])
    engine = Engine(EngineSpec("B2", "h" * 64))
    result = engine.advance(_view(s, [_signal("X", d[0], 0, 95, 110, 101)], datetime(2027, 1, 1, tzinfo=UTC)))
    exits = [r for r in result.rows if r["event_type"] == "EXIT"]
    assert exits and exits[0]["reason"] == "stop" and exits[0]["market_price"] == 95


def test_hueco_al_alza_es_above_max_entry() -> None:
    d = _days(3)
    s = _series("X", [(d[0], 100, 101, 99, 100), (d[1], 104, 105, 103, 104), (d[2], 104, 105, 103, 104)])
    engine = Engine(EngineSpec("B2", "h" * 64))
    result = engine.advance(_view(s, [_signal("X", d[0], 0, 95, 110, 101)], datetime(2027, 1, 1, tzinfo=UTC)))
    assert [r["reason"] for r in result.rows if r["event_type"] == "ENTRY_REJECTED"] == ["ABOVE_MAX_ENTRY"]
    assert market_check(104, 104 * 1.0005, 95, 110, 101, 1.5) == "ABOVE_MAX_ENTRY"


def test_split_2x1_reescala_la_posicion_sin_cambiar_el_valor() -> None:
    d = _days(6)
    bars = [(d[0], 100, 101, 99, 100), (d[1], 100, 101, 99, 100), (d[2], 100, 102, 99, 101),
            (d[3], 50.5, 51, 50, 50.5), (d[4], 50.5, 51, 50, 50.6), (d[5], 50.6, 51, 50, 50.7)]
    s = _series("X", bars, splits={3: 2.0})
    engine = Engine(EngineSpec("B2", "h" * 64))
    result = engine.advance(_view(s, [_signal("X", d[0], 0, 95, 120, 101)], datetime(2027, 1, 1, tzinfo=UTC)))
    split = [r for r in result.rows if r["event_type"] == "SPLIT_ADJUST"]
    assert len(split) == 1 and split[0]["units_after"] == pytest.approx(2 * split[0]["units_before"])
    assert not [r for r in result.rows if r["event_type"] == "EXIT"], "un split no puede disparar el stop"
    held = engine.positions["X"]
    assert held.stop == pytest.approx(47.5) and held.target2 == pytest.approx(60)
    before = next(sn for sn in result.snapshots if sn.day == d[2]).equity
    after = next(sn for sn in result.snapshots if sn.day == d[3]).equity
    assert after == pytest.approx(before * 50.5 / 50.5 * (50.5 * 2) / 101, rel=1e-9)


def test_dividendo_no_reescala_y_el_tardio_se_abona_sin_reescribir() -> None:
    d = _days(6)
    bars = [(d[i], 100, 101, 99, 100) for i in range(6)]
    signal = _signal("X", d[0], 0, 95, 120, 101)
    engine = Engine(EngineSpec("B2", "h" * 64))
    first = engine.advance(_view(_series("X", bars[:4], horizon=datetime.combine(d[4], time(8), UTC)), [signal],
                                 datetime.combine(d[3], time(18), UTC)))
    assert not [r for r in first.rows if r["event_type"] == "DIVIDEND"]
    units = engine.positions["X"].units
    # El dividendo con fecha ex d[2] se conoce después de procesar su cierre: se abona tarde, en la
    # primera sesión procesada, con las unidades de la víspera.
    second = engine.advance(_view(_series("X", bars, dividends={2: 1.5}), [signal], datetime(2027, 1, 1, tzinfo=UTC)))
    divs = [r for r in second.rows if r["event_type"] == "DIVIDEND"]
    assert len(divs) == 1 and divs[0]["late"] == 1
    assert divs[0]["dividend_base"] == pytest.approx(units * 1.5)
    assert divs[0]["session_date"] == str(d[4])
    assert engine.positions["X"].units == units


def test_dividendo_tardio_tras_un_split_se_abona_en_la_misma_base() -> None:
    d = _days(7)
    bars = [(d[0], 100, 101, 99, 100), (d[1], 100, 101, 99, 100), (d[2], 100, 101, 99, 100),
            (d[3], 50, 51, 49.5, 50), (d[4], 50, 51, 49.5, 50), (d[5], 50, 51, 49.5, 50), (d[6], 50, 51, 49.5, 50)]
    signal = _signal("X", d[0], 0, 95, 120, 101)
    engine = Engine(EngineSpec("B2", "h" * 64))
    engine.advance(_view(_series("X", bars[:5], splits={3: 2.0}, horizon=datetime.combine(d[5], time(8), UTC)),
                         [signal], datetime.combine(d[4], time(18), UTC)))
    units_pre_split = engine.positions["X"].units / 2
    late = engine.advance(_view(_series("X", bars, splits={3: 2.0}, dividends={2: 2.0}), [signal],
                                datetime(2027, 1, 1, tzinfo=UTC)))
    div = next(r for r in late.rows if r["event_type"] == "DIVIDEND")
    assert div["late"] == 1
    assert div["dividend_base"] == pytest.approx(units_pre_split * 2.0)


def test_cierre_de_cohorte_cancela_ordenes_y_sale_a_la_apertura() -> None:
    d = _days(6)
    bars = [(d[i], 100, 101, 99, 100) for i in range(6)]
    signals = [_signal("X", d[0], 0, 95, 120, 101)]
    engine = Engine(EngineSpec("B2", "h" * 64))
    closing = datetime.combine(d[3], time(7), UTC)
    result = engine.advance(_view(_series("X", bars), signals, datetime(2027, 1, 1, tzinfo=UTC), closing_at=closing))
    exits = [r for r in result.rows if r["event_type"] == "EXIT"]
    assert exits[0]["reason"] == EXIT_COHORT_CLOSED and exits[0]["session_date"] == str(d[3])
    assert not engine.positions


def test_data_loss_suspende_sin_vender_y_se_reanuda_con_datos() -> None:
    d = _days(10)
    bars = [(d[i], 100, 101, 99, 100) for i in range(3)]
    signal = _signal("X", d[0], 0, 95, 120, 101)
    engine = Engine(EngineSpec("B2", "h" * 64))
    engine.advance(_view(_series("X", bars, horizon=datetime.combine(d[3], time(8), UTC)), [signal],
                         datetime.combine(d[2], time(18), UTC)))
    suspended = engine.advance(_view(_series("X", bars, horizon=datetime.combine(d[3], time(8), UTC), data_loss=True),
                                     [signal], datetime.combine(d[9], time(18), UTC)))
    assert [e["event_type"] for e in suspended.position_events] == [EV_DATA_LOSS_SUSPENDED]
    assert not [r for r in suspended.rows if r["event_type"] == "EXIT"]
    assert "X" in engine.positions
    resumed_bars = [*bars, (d[8], 100, 101, 99, 100), (d[9], 100, 101, 99, 100)]
    resumed = engine.advance(_view(_series("X", resumed_bars), [signal], datetime(2027, 1, 1, tzinfo=UTC)))
    assert EV_DATA_RESUMED in [e["event_type"] for e in resumed.position_events]


def test_cierre_con_posicion_suspendida_queda_no_evaluable() -> None:
    d = _days(6)
    bars = [(d[i], 100, 101, 99, 100) for i in range(3)]
    signal = _signal("X", d[0], 0, 95, 120, 101)
    engine = Engine(EngineSpec("B2", "h" * 64))
    engine.advance(_view(_series("X", bars), [signal], datetime.combine(d[2], time(18), UTC)))
    engine.advance(_view(_series("X", bars, data_loss=True), [signal], datetime.combine(d[2], time(19), UTC)))
    closing = engine.advance(_view(_series("X", bars, data_loss=True), [signal], datetime(2027, 1, 1, tzinfo=UTC),
                                   closing_at=datetime.combine(d[2], time(20), UTC)))
    assert EV_NO_EVALUABLE_DATA_LOSS in [e["event_type"] for e in closing.position_events]
    assert not [r for r in closing.rows if r["event_type"] == "EXIT"]


def test_salida_por_accion_corporativa_terminal_verificable() -> None:
    d = _days(4)
    bars = [(d[i], 100, 101, 99, 100) for i in range(3)]
    signal = _signal("X", d[0], 0, 95, 120, 101)
    engine = Engine(EngineSpec("B2", "h" * 64))
    terminal = (datetime.combine(d[2], time(20), UTC), 103.0)
    result = engine.advance(EngineView(
        assets={"X": _series("X", bars, terminal=terminal)}, fx=FxTable({}), signals=(signal,), start=d[0],
        snapshot_days=tuple(d), limit=datetime(2027, 1, 1, tzinfo=UTC),
    ))
    exits = [r for r in result.rows if r["event_type"] == "EXIT"]
    assert exits[0]["reason"] == EXIT_CORPORATE_ACTION
    assert exits[0]["effective_price"] == 103.0 and exits[0]["slippage_base"] == 0.0


def test_engine_unrunnable_cancela_y_no_fabrica_salidas() -> None:
    d = _days(4)
    bars = [(d[i], 100, 101, 99, 100) for i in range(3)]
    signals = [_signal("X", d[0], 0, 95, 120, 101), _signal("Y", d[1], 1, 95, 120, 101)]
    y = _series("Y", [(d[0], 100, 101, 99, 100), (d[1], 100, 101, 99, 100)], horizon=datetime.combine(d[2], time(8), UTC))
    engine = Engine(EngineSpec("B2", "h" * 64))
    view = EngineView(assets={"X": _series("X", bars), "Y": y}, fx=FxTable({}), signals=tuple(signals), start=d[0],
                      snapshot_days=tuple(d[:3]), limit=datetime.combine(d[1], time(18), UTC))
    engine.advance(view)
    assert "X" in engine.positions and "Y" in engine.pending
    result = engine.advance(EngineView(**{**view.__dict__, "unrunnable": True}))
    assert [r["reason"] for r in result.rows] == ["CANCELLED_ENGINE_UNRUNNABLE"]
    assert [e["event_type"] for e in result.position_events] == [EV_NO_EVALUABLE_ENGINE_UNRUNNABLE]
    assert not [r for r in result.rows if r["event_type"] == "EXIT"]


def test_late_processing_marca_lo_procesado_tras_una_caida() -> None:
    syn = build(seed=7)
    spec = EngineSpec(policy_id="B2", system_sha256="x" * 64)
    engine = Engine(spec)
    cuts = _cuts(syn)
    for cut in cuts[:20]:
        engine.advance(view_at(syn, cut))
    late_before = cuts[27]
    result = engine.advance(view_at(syn, cuts[28], late_before=late_before))
    assert result.rows and all(r["late_processing"] == 1 for r in result.rows if r["timestamp_utc"] < late_before.strftime("%Y-%m-%dT%H:%M:%SZ"))


def test_requested_weight_no_depende_de_equity_ni_fx() -> None:
    assert requested_weight(100.0, 95.0) == pytest.approx(0.1)
    assert requested_weight(100.0, 50.0) == pytest.approx(0.01)
