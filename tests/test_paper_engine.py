"""T-025 — ``engine_v1`` frente a ``p6_sim`` (test de equivalencia, ficha §3.4 y §16) y reglas del motor."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List

import pytest

from advisor.research.p6_sim import (
    LEDGER_COLUMNS,
    PHASE_RANK,
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
    CatchupBar,
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


def test_estado_json_ida_y_vuelta_reproduce_el_mismo_avance() -> None:
    import json

    from paper.engine_v1 import engine_from_state, engine_to_state

    syn = build(seed=11)
    spec = EngineSpec(policy_id="B2", system_sha256="x" * 64, risk_pct=2.0, max_position_pct=25.0)
    cuts = _cuts(syn)
    straight = Engine(spec)
    rows_a: List[Dict[str, Any]] = []
    for cut in cuts:
        rows_a.extend(straight.advance(view_at(syn, cut)).rows)
    restored = Engine(spec)
    rows_b: List[Dict[str, Any]] = []
    for k, cut in enumerate(cuts):
        rows_b.extend(restored.advance(view_at(syn, cut)).rows)
        if k % 9 == 0:
            text = json.dumps(engine_to_state(restored), sort_keys=True, allow_nan=False)
            restored = engine_from_state(spec, json.loads(text))
    assert rows_a == rows_b


def test_dividendo_conocido_entre_la_apertura_y_el_cierre_ex_no_se_pierde() -> None:
    d = _days(5)
    bars = [(d[i], 100, 101, 99, 100) for i in range(5)]
    signal = _signal("X", d[0], 0, 95, 120, 101)
    engine = Engine(EngineSpec("B2", "h" * 64))
    # La frontera se para dentro de la sesión ex (d[2]): su apertura ya está procesada, su cierre no.
    engine.advance(_view(_series("X", bars), [signal], datetime.combine(d[2], time(12), UTC)))
    units = engine.positions["X"].units
    result = engine.advance(_view(_series("X", bars, dividends={2: 1.0}), [signal], datetime(2027, 1, 1, tzinfo=UTC)))
    divs = [r for r in result.rows if r["event_type"] == "DIVIDEND"]
    assert len(divs) == 1 and divs[0]["late"] == 1 and divs[0]["dividend_base"] == pytest.approx(units)


def test_mae_y_mfe_en_la_misma_escala_a_traves_de_un_split() -> None:
    d = _days(8)
    bars = [(d[0], 100, 101, 99, 100), (d[1], 100, 104, 97, 100), (d[2], 100, 103, 98, 100),
            (d[3], 50, 51.5, 49, 50), (d[4], 50, 52, 49.5, 51), (d[5], 51, 60.5, 50, 60)]
    signal = _signal("X", d[0], 0, 90, 120, 101)
    engine = Engine(EngineSpec("B2", "h" * 64))
    result = engine.advance(_view(_series("X", bars, splits={3: 2.0}), [signal], datetime(2027, 1, 1, tzinfo=UTC)))
    outcome = result.outcomes[0]
    entry = outcome.trade.entry_eff  # en la escala nueva tras el split
    units = outcome.trade.units
    risk = outcome.trade.risk_local
    assert outcome.mae_R == pytest.approx((97 / 2 - entry) * units / risk)
    assert outcome.mfe_R == pytest.approx((60.5 - entry) * units / risk)


def test_contrasplit_reescala_al_reves_sin_disparar_salidas() -> None:
    d = _days(5)
    bars = [(d[0], 10, 10.1, 9.9, 10), (d[1], 10, 10.1, 9.9, 10), (d[2], 20, 20.2, 19.8, 20), (d[3], 20, 20.2, 19.8, 20)]
    signal = _signal("X", d[0], 0, 9.5, 12, 10.1)
    engine = Engine(EngineSpec("B2", "h" * 64))
    result = engine.advance(_view(_series("X", bars, splits={2: 0.5}), [signal], datetime(2027, 1, 1, tzinfo=UTC)))
    assert [r["event_type"] for r in result.rows if r["event_type"] in ("SPLIT_ADJUST", "EXIT")] == ["SPLIT_ADJUST"]
    assert engine.positions["X"].stop == pytest.approx(19.0) and engine.positions["X"].target2 == pytest.approx(24.0)


# ---------------------------------------------------------------------------- D-80: catch-up de un hueco real


def _catchup_case(bar: CatchupBar, *, splits=None, dividends=None, other: bool = False, scale: float = 1.0):
    """X entra en d1 y su frontera se detiene en d3 (``SCALE_MISMATCH``); d3 se declara ausente y se libera como
    hueco real (``bar``); vuelve la serie normal en d9. Con ``other``, Y también tiene posición y la frontera
    la detiene Y en la apertura de d2, antes de la sesión liberada."""

    d = _days(14)
    flat = [(d[i], 100, 101, 99, 100) for i in range(14)]
    signals = [_signal("X", d[0], 0, 95, 130, 101)] + ([_signal("Y", d[0], 0, 95, 130, 101)] if other else [])
    limit = datetime.combine(d[13], time(6), UTC)

    def view(assets):
        return EngineView(assets={a.meta.symbol: a for a in assets}, fx=FxTable({}), signals=tuple(signals), start=d[0],
                          snapshot_days=tuple(d), limit=limit)

    engine = Engine(EngineSpec("B2", "h" * 64))
    first = [_series("X", flat[:3], horizon=datetime.combine(d[3], time(8), UTC))]
    if other:
        first.append(_series("Y", flat[:2], horizon=datetime.combine(d[2], time(8), UTC)))
    engine.advance(view(first))
    later = [(day, *(price / scale for price in prices)) for day, *prices in flat[9:12]]
    x = _series("X", flat[:3] + later, splits=splits, dividends=dividends, horizon=datetime.combine(d[12], time(8), UTC))
    second = [AssetView(**{**x.__dict__, "catchup": (bar,)})]
    if other:
        second.append(_series("Y", flat[:12], horizon=datetime.combine(d[12], time(8), UTC)))
    return d, engine, engine.advance(view(second))


def _x(rows, kind):
    return [r for r in rows if r["asset"] == "X" and r["event_type"] == kind]


def test_catch_up_espera_a_que_la_frontera_alcance_la_sesion_liberada() -> None:
    """D-80: con la frontera detenida por otro activo antes de la sesión liberada, la barra vigente anterior de X se
    procesa primero y la del hueco solo cuando la frontera llega a su apertura."""

    d = _days(14)
    bar = CatchupBar(d[3], datetime.combine(d[3], time(8), UTC), datetime.combine(d[3], time(16, 30), UTC), 50.0, 51.0, 49.0, 50.0)
    _d, _engine, result = _catchup_case(bar, other=True)
    exits = _x(result.rows, "EXIT")
    assert len(exits) == 1
    exit_row = exits[0]
    assert exit_row["session_date"] == str(d[3]) and exit_row["reason"] == "stop" and exit_row["market_price"] == 50.0
    assert datetime.fromisoformat(exit_row["timestamp_utc"].replace("Z", "+00:00")) >= bar.open_utc
    assert exit_row["late_processing"] == 1
    snapshot_rows = [r for r in result.rows if r["event_type"] != "EXIT" and r["session_date"] == str(d[2]) and r["asset"] == "X"]
    assert all(r["seq"] < exit_row["seq"] for r in snapshot_rows), "la barra d2 de X va antes que el hueco"
    events = [e for e in result.position_events if e["event_type"] == "EXIT"]
    assert events and events[0]["late"] == 1 and events[0]["late_processing"] == 1


def test_split_con_fecha_ex_en_el_catch_up_se_aplica_una_sola_vez() -> None:
    d = _days(14)
    bar = CatchupBar(d[3], datetime.combine(d[3], time(8), UTC), datetime.combine(d[3], time(16, 30), UTC), 50.0, 50.5, 49.5, 50.0, split=2.0)
    _d, engine, result = _catchup_case(bar, splits={3: 2.0}, scale=2.0)
    assert not _x(result.rows, "EXIT"), "en la escala nueva el stop es 47.5: sin stop ficticio"
    adjusts = _x(result.rows, "SPLIT_ADJUST")
    assert len(adjusts) == 1 and adjusts[0]["session_date"] == str(d[3]) and adjusts[0]["late_processing"] == 1
    assert len([e for e in result.position_events if e["event_type"] == "SPLIT_ADJUST"]) == 1
    held = engine.positions["X"]
    assert held.stop == pytest.approx(47.5) and held.units == pytest.approx(adjusts[0]["units_before"] * 2)
    assert held.split_carried == 1.0


def test_dividendo_con_fecha_ex_en_el_catch_up_se_abona_una_sola_vez() -> None:
    d = _days(14)
    bar = CatchupBar(d[3], datetime.combine(d[3], time(8), UTC), datetime.combine(d[3], time(16, 30), UTC), 100.0, 101.0, 99.0, 100.0, dividend=2.0)
    _d, engine, result = _catchup_case(bar, dividends={3: 2.0})
    credits = _x(result.rows, "DIVIDEND")
    assert len(credits) == 1 and credits[0]["session_date"] == str(d[3]) and credits[0]["late_processing"] == 1
    held = engine.positions["X"]
    assert credits[0]["market_price"] == 2.0 and held.dividends_local == pytest.approx(held.units * 2.0)
    assert held.dividend_carried == 0.0


def test_dividendo_del_catch_up_se_abona_en_su_close_dividend_y_no_financia_la_apertura() -> None:
    """D-80 con el orden de fases de P6 (OPEN_EXIT < OPEN_ENTRY < CLOSE_EXIT < CLOSE_DIVIDEND < CLOSE_VALUATION):
    el dividendo de la barra liberada no está en el cash de su apertura, así que no financia la entrada de Z en
    esa misma apertura (que sí cabría con él), y se abona una sola vez en el cierre de la sesión."""

    d = _days(14)
    bar = CatchupBar(d[3], datetime.combine(d[3], time(8), UTC), datetime.combine(d[3], time(16, 30), UTC),
                     100.0, 101.0, 99.0, 100.0, dividend=1.0)
    flat = [(d[i], 100, 101, 99, 100) for i in range(14)]
    signals = (_signal("X", d[0], 0, 1, 1000, 101), _signal("Z", d[2], 2, 1, 1000, 101))
    spec = EngineSpec("B2", "h" * 64, risk_pct=100.0, max_position_pct=50.0)

    def view(assets):
        return EngineView(assets={a.meta.symbol: a for a in assets}, fx=FxTable({}), signals=signals, start=d[0],
                          snapshot_days=tuple(d), limit=datetime.combine(d[13], time(6), UTC))

    engine = Engine(spec)
    z = _series("Z", flat[:12], horizon=datetime.combine(d[12], time(8), UTC))
    engine.advance(view([_series("X", flat[:3], horizon=datetime.combine(d[3], time(8), UTC)), z]))
    x = _series("X", flat[:3] + flat[9:12], dividends={3: 1.0}, horizon=datetime.combine(d[12], time(8), UTC))
    released = AssetView(**{**x.__dict__, "catchup": (bar,)})
    assert released.catchup[0].dividend == 1.0, "la barra liberada trae dividendo"
    result = engine.advance(view([released, z]))
    rows = result.rows

    held = engine.positions["X"]
    dividend_eur = held.units * bar.dividend
    rejected = [r for r in rows if r["asset"] == "Z" and r["event_type"] == "ENTRY_REJECTED"]
    assert len(rejected) == 1 and rejected[0]["reason"] == "INSUFFICIENT_CASH"
    assert rejected[0]["session_date"] == str(d[3]) and rejected[0]["fase"] == "OPEN_ENTRY"
    cash_at_open = rejected[0]["cash_before"]
    required = float(rejected[0]["cash_requerido_base"])
    assert cash_at_open < required < cash_at_open + dividend_eur, "el dividendo la habría financiado"
    assert cash_at_open == pytest.approx(spec.capital - held.units * held.entry_eff * (1 + spec.fee_rate))
    assert not [r for r in rows if r["asset"] == "Z" and r["event_type"] == "ENTRY"]

    credits = _x(rows, "DIVIDEND")
    assert len(credits) == 1, "una sola vez: la barra vigente d9 no lo repite"
    credit = credits[0]
    assert credit["session_date"] == str(d[3]) and credit["fase"] == "CLOSE_DIVIDEND"
    assert credit["late"] == 1 and credit["late_processing"] == 1
    assert datetime.fromisoformat(credit["timestamp_utc"].replace("Z", "+00:00")) >= bar.close_utc
    assert credit["seq"] > rejected[0]["seq"]
    assert credit["dividend_base"] == pytest.approx(dividend_eur)
    assert credit["cash_after"] - credit["cash_before"] == pytest.approx(dividend_eur)
    assert held.dividends_local == pytest.approx(dividend_eur) and held.dividend_carried == 0.0
    assert engine.catchup_dividends == []
    assert not [r for r in rows if r["event_type"] == "DIVIDEND" and r["asset"] != "X"]

    order = [(datetime.fromisoformat(r["timestamp_utc"].replace("Z", "+00:00")), PHASE_RANK[r["fase"]]) for r in rows]
    assert [r["seq"] for r in rows] == sorted(r["seq"] for r in rows)
    assert order == sorted(order), "ledger en el orden de fases de P6"
    events = [e for e in result.position_events if e["event_type"] == "DIVIDEND_CREDIT"]
    assert len(events) == 1 and events[0]["late"] == 1 and events[0]["late_processing"] == 1


def test_dividendo_del_catch_up_pendiente_sobrevive_al_estado_y_a_la_salida_por_hueco() -> None:
    """D-80: la frontera se detiene entre la apertura y el cierre de la sesión liberada. X sale por hueco en esa
    apertura; su derecho al dividendo queda pendiente (persistido en el estado), se abona en el CLOSE_DIVIDEND y
    el desenlace de X espera a ese abono."""

    import json

    from paper.engine_v1 import engine_from_state, engine_to_state

    d = _days(14)
    bar = CatchupBar(d[3], datetime.combine(d[3], time(8), UTC), datetime.combine(d[3], time(16, 30), UTC),
                     85.0, 86.0, 84.0, 85.0, dividend=1.0)
    flat = [(d[i], 100, 101, 99, 100) for i in range(14)]
    signals = (_signal("X", d[0], 0, 90, 130, 101),)
    spec = EngineSpec("B2", "h" * 64)
    z = _series("Z", flat[:12], horizon=datetime.combine(d[12], time(8), UTC))

    def view(assets, limit):
        return EngineView(assets={a.meta.symbol: a for a in assets}, fx=FxTable({}), signals=signals, start=d[0],
                          snapshot_days=tuple(d), limit=limit)

    engine = Engine(spec)
    engine.advance(view([_series("X", flat[:3], horizon=datetime.combine(d[3], time(8), UTC)), z],
                        datetime.combine(d[13], time(6), UTC)))
    x = _series("X", flat[:3] + flat[9:12], dividends={3: 1.0}, horizon=datetime.combine(d[12], time(8), UTC))
    released = [AssetView(**{**x.__dict__, "catchup": (bar,)}), z]

    midday = engine.advance(view(released, datetime.combine(d[3], time(12), UTC)))
    exits = _x(midday.rows, "EXIT")
    assert len(exits) == 1 and exits[0]["fase"] == "OPEN_EXIT" and exits[0]["market_price"] == 85.0
    assert not _x(midday.rows, "DIVIDEND") and midday.outcomes == []
    closed = exits[0]
    assert len(engine.catchup_dividends) == 1

    engine = engine_from_state(spec, json.loads(json.dumps(engine_to_state(engine), sort_keys=True, allow_nan=False)))
    assert len(engine.catchup_dividends) == 1
    rest = engine.advance(view(released, datetime.combine(d[13], time(6), UTC)))
    credits = _x(rest.rows, "DIVIDEND")
    assert len(credits) == 1 and credits[0]["fase"] == "CLOSE_DIVIDEND" and credits[0]["session_date"] == str(d[3])
    assert credits[0]["late"] == 1 and credits[0]["late_processing"] == 1
    assert datetime.fromisoformat(credits[0]["timestamp_utc"].replace("Z", "+00:00")) >= bar.close_utc
    assert credits[0]["dividend_base"] == pytest.approx(closed["units_before"] * 1.0)
    assert credits[0]["units_after"] == 0.0
    assert engine.catchup_dividends == []
    assert len(rest.outcomes) == 1
    assert rest.outcomes[0].trade.dividends_eur == pytest.approx(credits[0]["dividend_base"])


def test_catch_up_no_usa_el_minimo_ni_el_cierre_antes_del_cierre_de_la_sesion() -> None:
    """D-80: con la frontera detenida antes de la sesión liberada, el toque intradía del stop se procesa en su
    cierre, no en su apertura (así el cash que libera no está disponible en esa apertura)."""

    d = _days(14)
    bar = CatchupBar(d[3], datetime.combine(d[3], time(8), UTC), datetime.combine(d[3], time(16, 30), UTC),
                     100.0, 100.5, 90.0, 92.0)
    _d, _engine, result = _catchup_case(bar, other=True)
    exits = _x(result.rows, "EXIT")
    assert len(exits) == 1 and exits[0]["reason"] == "stop" and exits[0]["market_price"] == 95.0
    assert datetime.fromisoformat(exits[0]["timestamp_utc"].replace("Z", "+00:00")) >= bar.close_utc
    assert exits[0]["fase"] == "CLOSE_EXIT" and exits[0]["late_processing"] == 1
