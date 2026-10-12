"""Tests pre-registrados de P6 (T-022 §20): los 48 obligatorios, numerados, más regresiones.

Todo es sintético o estructural (calendarios, hashes, identidades): ningún test simula la cosecha
real ni abre un desenlace de P6.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

import pandas as pd
import pytest

import advisor.research.p6 as p6
import advisor.research.p6_sim as sim
from advisor.backtest.engine import EXIT_STOP as ENGINE_STOP
from advisor.backtest.engine import EXIT_TARGET as ENGINE_TARGET
from advisor.backtest.engine import _check_exit
from advisor.config import load_config
from advisor.context.point_in_time import PointInTimeContextResolver, analysis_timestamp_for_signal
from advisor.data.calendars import expected_sessions
from advisor.data.sessions import session_close_at

UTC = timezone.utc
EUR = sim.FxTable({})


def business_days(start: date, n: int, *, skip: Sequence[date] = ()) -> List[date]:
    days: List[date] = []
    current = start
    while len(days) < n:
        if current.weekday() < 5 and current not in skip:
            days.append(current)
        current += timedelta(days=1)
    return days


def asset(
    symbol: str,
    rows: Sequence[Sequence[float]],
    *,
    currency: str = "EUR",
    market: str = "XETRA",
    open_at: time = time(8, 0),
    close_at: time = time(16, 30),
    region: str = "EUROPA",
    economic: Optional[str] = None,
    sector: str = "Technology",
    days: Optional[Sequence[date]] = None,
    eligible_from: int = 0,
) -> sim.AssetSeries:
    sessions = list(days) if days is not None else business_days(date(2024, 1, 1), len(rows))
    return sim.AssetSeries(
        symbol=symbol, market=market, currency=currency, economic_currency=economic or currency, region=region,
        sector=sector, session_dates=tuple(sessions),
        open_utc=tuple(datetime.combine(d, open_at, UTC) for d in sessions),
        close_utc=tuple(datetime.combine(d, close_at, UTC) for d in sessions),
        open=tuple(float(r[0]) for r in rows), high=tuple(float(r[1]) for r in rows),
        low=tuple(float(r[2]) for r in rows), close=tuple(float(r[3]) for r in rows),
        dividends=tuple(float(r[4]) if len(r) > 4 else 0.0 for r in rows), eligible_from=eligible_from,
    )


def flat(n: int, price: float = 100.0) -> List[Tuple[float, float, float, float]]:
    return [(price, price + 0.5, price - 0.5, price)] * n


def market(*assets: sim.AssetSeries, start: Optional[date] = None, end: Optional[date] = None) -> sim.MarketData:
    days = sorted({d for a in assets for d in a.session_dates})
    return sim.MarketData({a.symbol: a for a in assets}, start or days[0], end or days[-1])


def signal(series: sim.AssetSeries, j: int, stop: float, target: float, entry_max: Optional[float] = None,
           sid: Optional[str] = None, delay: timedelta = timedelta(minutes=30)) -> sim.Signal:
    return sim.Signal(sid or f"{series.symbol}|swing|{j}", series.symbol, j, series.close_utc[j] + delay,
                      stop, target, entry_max if entry_max is not None else target)


def spec(**changes: Any) -> sim.SimSpec:
    base = sim.SimSpec("T", "t" * 64, fee_rate=0.0, slippage_bps=0.0)
    return replace(base, **changes)


def rows_of(result: sim.SimResult, event_type: str) -> List[Dict[str, Any]]:
    return [row for row in result.ledger if row["event_type"] == event_type]


# ---------------------------------------------------------------------------
# Los 48 tests de T-022 §20.
# ---------------------------------------------------------------------------


def test_t01_operacion_simple_sin_costes() -> None:
    rows = [(100, 100.5, 99.5, 100), (100, 101, 99, 100), (100, 111, 99.5, 110), *flat(3, 110)]
    a = asset("A", rows)
    result = sim.simulate(market(a), [signal(a, 0, 95, 110)], EUR, spec())
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.units == pytest.approx(100.0) and trade.exit_reason == sim.EXIT_TARGET
    assert trade.pnl_neto_eur == pytest.approx(1000.0) and trade.trade_R_local == pytest.approx(2.0)
    assert result.snapshots[-1].equity == pytest.approx(101_000.0)


def test_t02_sizing_por_riesgo() -> None:
    a = asset("A", flat(8))
    result = sim.simulate(market(a), [signal(a, 0, 90, 200)], EUR, spec(max_hold_bars=2))
    assert result.trades[0].units == pytest.approx(0.005 * 100_000 / 10)


def test_t03_tope_del_10_por_ciento() -> None:
    a = asset("A", flat(8))
    result = sim.simulate(market(a), [signal(a, 0, 99, 200)], EUR, spec(max_hold_bars=2))
    assert result.trades[0].units * 100 == pytest.approx(10_000.0)


def test_t04_cash_insuficiente() -> None:
    a, b = asset("A", flat(8)), asset("B", flat(8))
    result = sim.simulate(market(a, b), [signal(a, 0, 99, 200), signal(b, 0, 99, 200)], EUR,
                          spec(max_position_pct=60, risk_pct=50, max_hold_bars=2))
    assert result.counters.get(sim.INSUFFICIENT_CASH) == 1
    assert len(rows_of(result, "ENTRY")) == 1


def test_t05_dos_entradas_simultaneas() -> None:
    a, b = asset("A", flat(8)), asset("B", flat(8))
    result = sim.simulate(market(a, b), [signal(a, 0, 95, 200), signal(b, 0, 95, 200)], EUR, spec(max_hold_bars=2))
    entries = rows_of(result, "ENTRY")
    assert len(entries) == 2 and entries[0]["timestamp_utc"] == entries[1]["timestamp_utc"]


def _ids_with_hash_order_opposite_to_alphabet() -> Tuple[str, str]:
    for k in range(1000):
        first, second = f"A|swing|{k}", f"B|swing|{k}"
        if sim.tiebreak_key(second) < sim.tiebreak_key(first):
            return first, second
    raise AssertionError("sin par")


def test_t06_desempate_sha256_sin_alfabeto() -> None:
    sid_a, sid_b = _ids_with_hash_order_opposite_to_alphabet()
    a, b = asset("A", flat(8)), asset("B", flat(8))
    signals = [signal(a, 0, 99, 200, sid=sid_a), signal(b, 0, 99, 200, sid=sid_b)]
    result = sim.simulate(market(a, b), signals, EUR, spec(max_position_pct=60, risk_pct=50, max_hold_bars=2))
    entered = rows_of(result, "ENTRY")[0]
    assert entered["signal_id"] == sid_b
    assert sim.tiebreak_key(sid_b) == hashlib.sha256(b"intradia.p6.desempate.v1" + sid_b.encode("utf-8")).hexdigest()


def test_t07_stop_por_hueco() -> None:
    rows = [*flat(2), (90, 92, 88, 91), *flat(3, 91)]
    a = asset("A", rows)
    result = sim.simulate(market(a), [signal(a, 0, 95, 200)], EUR, spec())
    exit_row = rows_of(result, "EXIT")[0]
    assert exit_row["fase"] == sim.OPEN_EXIT and exit_row["market_price"] == 90.0
    assert result.trades[0].exit_reason == sim.EXIT_STOP


def test_t08_stop_y_objetivo_misma_vela_gana_stop() -> None:
    rows = [*flat(2), (100, 120, 90, 100), *flat(3)]
    a = asset("A", rows)
    result = sim.simulate(market(a), [signal(a, 0, 95, 110)], EUR, spec())
    assert result.trades[0].exit_reason == sim.EXIT_STOP and result.trades[0].exit_eff == pytest.approx(95.0)


def test_t09_salida_intradia_no_financia_entrada_anterior() -> None:
    days = business_days(date(2024, 1, 1), 6)
    us = asset("US", [*flat(2), (100, 100.5, 90, 95), *flat(3)], market="NYSE", open_at=time(14, 30),
               close_at=time(21, 0), days=days)
    eu = asset("EU", flat(6), days=days)
    signals = [signal(us, 0, 95, 200), signal(eu, 1, 90, 200)]
    result = sim.simulate(market(us, eu), signals, EUR, spec(max_position_pct=100, risk_pct=100))
    rejected = rows_of(result, "ENTRY_REJECTED")
    assert rejected and rejected[0]["asset"] == "EU" and rejected[0]["reason"] == sim.INSUFFICIENT_CASH


def test_t10_salida_en_asia_financia_apertura_posterior_en_eeuu() -> None:
    days = business_days(date(2024, 1, 1), 6)
    jp = asset("JP", [*flat(2), (100, 100.5, 90, 95), *flat(3)], market="JPX", open_at=time(0, 0),
               close_at=time(6, 0), days=days, region="ASIA")
    us = asset("US", flat(6), market="NYSE", open_at=time(14, 30), close_at=time(21, 0), days=days, region="USA")
    signals = [signal(jp, 0, 95, 200), signal(us, 1, 90, 200)]
    result = sim.simulate(market(jp, us), signals, EUR, spec(max_position_pct=100, risk_pct=100))
    us_entries = [row for row in rows_of(result, "ENTRY") if row["asset"] == "US"]
    assert len(us_entries) == 1


def test_t11_dividendo_ex() -> None:
    rows = [*flat(3), (100, 100.5, 99.5, 100, 2.0), *flat(3)]
    a = asset("A", rows)
    result = sim.simulate(market(a), [signal(a, 0, 95, 200)], EUR, spec(max_hold_bars=4))
    dividends = rows_of(result, "DIVIDEND")
    assert len(dividends) == 1 and dividends[0]["fase"] == sim.CLOSE_DIVIDEND
    assert dividends[0]["dividend_base"] == pytest.approx(100.0 * 2.0)


def test_t12_compra_en_fecha_ex_sin_dividendo() -> None:
    rows = [*flat(1), (100, 100.5, 99.5, 100, 2.0), *flat(4)]
    a = asset("A", rows)
    result = sim.simulate(market(a), [signal(a, 0, 95, 200)], EUR, spec(max_hold_bars=2))
    assert not rows_of(result, "DIVIDEND")


def test_t13_venta_en_apertura_ex_con_derecho() -> None:
    rows = [*flat(3), (90, 91, 89, 90, 2.0), *flat(2, 90)]
    a = asset("A", rows)
    result = sim.simulate(market(a), [signal(a, 0, 95, 200)], EUR, spec())
    assert rows_of(result, "EXIT")[0]["fase"] == sim.OPEN_EXIT
    assert len(rows_of(result, "DIVIDEND")) == 1 and result.trades[0].dividends_local == pytest.approx(200.0)


def _split_case(factor: float) -> Tuple[sim.SimResult, sim.SimResult]:
    base = [(100, 101, 99, 100), (100, 101, 99, 100), (100, 103, 99, 102, 1.0), (102, 104, 101, 103),
            (103, 106, 102, 105), *flat(2, 105)]
    adjusted = [tuple(v * factor for v in row) for row in base]
    a, b = asset("A", base), asset("A", adjusted)
    ra = sim.simulate(market(a), [signal(a, 0, 95, 200)], EUR, spec(fee_rate=0.001, slippage_bps=5, max_hold_bars=4))
    rb = sim.simulate(market(b), [signal(b, 0, 95 * factor, 200 * factor)], EUR,
                      spec(fee_rate=0.001, slippage_bps=5, max_hold_bars=4))
    return ra, rb


def test_t14_split_2_a_1() -> None:
    ra, rb = _split_case(0.5)
    assert rb.trades[0].units == pytest.approx(2 * ra.trades[0].units)
    assert rb.snapshots[-1].equity == pytest.approx(ra.snapshots[-1].equity)
    assert rb.trades[0].trade_R_local == pytest.approx(ra.trades[0].trade_R_local)


def test_t15_fx_constante() -> None:
    a = asset("A", [(100, 100.5, 99.5, 100), (100, 101, 99, 100), (100, 111, 99.5, 110), *flat(3, 110)], currency="USD")
    fx = sim.FxTable({"USD": [(datetime(2023, 12, 1, tzinfo=UTC), 1.25)]})
    result = sim.simulate(market(a), [signal(a, 0, 95, 110)], fx, spec())
    trade = result.trades[0]
    assert trade.pnl_neto_eur == pytest.approx(trade.pnl_neto_local * 0.8)
    assert trade.trade_R_eur == pytest.approx(trade.trade_R_local)


def test_t16_fx_se_mueve_sin_mover_el_activo() -> None:
    a = asset("A", flat(6), currency="USD")
    fx = sim.FxTable({"USD": [(datetime(2023, 12, 1, tzinfo=UTC), 1.25), (datetime(2024, 1, 2, 12, tzinfo=UTC), 1.0)]})
    result = sim.simulate(market(a), [signal(a, 0, 95, 200)], fx, spec(max_hold_bars=2))
    trade = result.trades[0]
    assert trade.pnl_bruto_local == pytest.approx(0.0) and trade.trade_R_local == pytest.approx(0.0)
    assert trade.pnl_bruto_eur == pytest.approx(trade.fx_eur) and trade.fx_eur > 0


def test_t17_exposicion_divisa_cotizacion_frente_a_economica() -> None:
    a = asset("A", flat(6), currency="USD", economic="MULTI", region="GLOBAL", sector="EQUITY_ETF")
    fx = sim.FxTable({"USD": [(datetime(2023, 12, 1, tzinfo=UTC), 1.0)]})
    result = sim.simulate(market(a), [signal(a, 0, 95, 200)], fx, spec(max_hold_bars=3))
    exposure = sim.exposure_metrics(result.snapshots)
    assert "USD" in exposure["por_divisa_cotizacion"] and "MULTI" in exposure["por_divisa_economica"]
    assert "USD" not in exposure["por_divisa_economica"]


def test_t18_turnover() -> None:
    series = [(date(2024, 1, 1), 100.0), (date(2024, 12, 31), 110.0), (date(2025, 12, 31), 90.0)]
    out = sim.turnover(300.0, series)
    assert out["turnover_total"] == pytest.approx(300.0 / 100.0)
    assert out["turnover_anual"] == pytest.approx(3.0 / ((date(2025, 12, 31) - date(2024, 1, 1)).days / 365.25))


def test_t19_max_drawdown_con_fechas() -> None:
    series = [(date(2024, 1, 1), 100.0), (date(2024, 1, 2), 120.0), (date(2024, 1, 3), 90.0),
              (date(2024, 1, 4), 121.0), (date(2024, 1, 5), 110.0)]
    out = sim.path_metrics(series)
    assert out["max_drawdown"] == pytest.approx(90 / 120 - 1)
    assert (out["dd_pico"], out["dd_valle"], out["dd_recuperacion"]) == ("2024-01-02", "2024-01-03", "2024-01-04")
    assert out["dd_duracion_dias"] == 2


def test_t20_sharpe_y_sortino() -> None:
    values = [100.0, 101.0, 100.0, 102.0, 101.5]
    series = [(date(2024, 1, 1) + timedelta(days=k), v) for k, v in enumerate(values)]
    out = sim.path_metrics(series)
    returns = [values[k] / values[k - 1] - 1 for k in range(1, len(values))]
    ppy = 4 / (4 / 365.25)
    mean = sum(returns) / 4
    std = math.sqrt(sum((r - mean) ** 2 for r in returns) / 3)
    down = math.sqrt(sum(min(r, 0) ** 2 for r in returns) / 4)
    assert out["sharpe_rf0"] == pytest.approx(mean * ppy / (std * math.sqrt(ppy)))
    assert out["sortino_mar0"] == pytest.approx(mean * ppy / (down * math.sqrt(ppy)))


def test_t21_benchmark_pesos_iguales() -> None:
    a, b = asset("A", flat(5)), asset("B", flat(5, 50))
    bench = sim.simulate_benchmark(market(a, b), EUR, spec(fee_rate=0.001, slippage_bps=5))
    buys = rows_of_bench(bench, "BH_BUY")
    assert len(buys) == 2
    for row in buys:
        assert row["notional_base"] + row["fee_base"] == pytest.approx(50_000.0)
    assert min(row["cash_after"] for row in bench.ledger) >= 0


def rows_of_bench(bench: sim.BenchmarkResult, event_type: str) -> List[Dict[str, Any]]:
    return [row for row in bench.ledger if row["event_type"] == event_type]


def test_t22_dividendo_del_benchmark_reinvertido() -> None:
    a = asset("A", [*flat(2), (100, 100.5, 99.5, 100, 3.0), *flat(3)])
    bench = sim.simulate_benchmark(market(a), EUR, spec(fee_rate=0.001))
    buys = rows_of_bench(bench, "BH_BUY")
    assert [row["reason"] for row in buys] == ["BH_COMPRA_INICIAL", "BH_REINVERSION_DIVIDENDO"]
    dividend = rows_of_bench(bench, "BH_DIVIDEND")[0]["dividend_base"]
    assert buys[1]["notional_base"] + buys[1]["fee_base"] == pytest.approx(dividend)


def test_t23_conciliacion_del_ledger() -> None:
    m, fx, signals = p6.synthetic_market()
    result = sim.simulate(m, signals, fx, spec(fee_rate=0.001, slippage_bps=5))
    previous = 100_000.0
    for row in result.ledger:
        assert row["cash_before"] == pytest.approx(previous)
        previous = row["cash_after"]
    total = sum(t.pnl_bruto_eur for t in result.trades) + result.dividends_eur - result.fees_eur
    assert result.snapshots[-1].equity - 100_000.0 == pytest.approx(total, abs=1e-6)


def _window() -> p6.Window:
    return p6.Window(date(2022, 6, 14), date(2026, 8, 27), date(2022, 2, 25), date(2022, 6, 13), 27, 1100, 255.0)


def test_t24_system_sha256_de_b2_y_s2() -> None:
    config = load_config("config.yaml")
    hashes = p6.system_hashes(config, _window())
    assert hashes["B2_primaria_5pb"]["system_sha256"] != hashes["S2_primaria_5pb"]["system_sha256"]
    assert hashes == p6.system_hashes(config, _window())
    payload = p6.system_payload(config, "B2", p6.POPULATION_OPERAR, 5.0, _window())
    for field in ("p5_policy_sha256", "poblacion_de_senales", "modo_de_contexto", "predicado_OPERAR",
                  "estimador_decisorio", "regla_analysis_timestamp", "fuente_fx", "criterio_de_supervivencia",
                  "p6_data_id", "periodos_por_año", "ventana", "contrato_del_benchmark"):
        assert field in payload


def test_t25_c0_como_control() -> None:
    config = load_config("config.yaml")
    assert p6.system_payload(config, "C0", p6.POPULATION_OPERAR, 5.0, _window())["papel"] == "control_descriptivo"
    with pytest.raises(ValueError):
        sim.survivors({"C0": sim.LABEL_PASS})


def test_t26_mismo_resultado_byte_a_byte() -> None:
    assert p6.synthetic_determinism()["identico"] is True


def test_t27_ignored_already_open_contado() -> None:
    a = asset("A", flat(8))
    result = sim.simulate(market(a), [signal(a, 0, 95, 200), signal(a, 2, 95, 200)], EUR, spec())
    assert result.counters.get(sim.IGNORED_ALREADY_OPEN) == 1


def test_t28_fx_posterior_al_evento_no_se_usa() -> None:
    at = datetime(2024, 1, 2, 10, tzinfo=UTC)
    fx = sim.FxTable({"USD": [(datetime(2024, 1, 1, 15, tzinfo=UTC), 1.10), (datetime(2024, 1, 2, 10, tzinfo=UTC), 2.0)]})
    assert fx.quote("USD", at).rate == 1.10
    with pytest.raises(sim.FxUnavailableError):
        fx.quote("USD", datetime(2024, 1, 1, 15, tzinfo=UTC))


def test_t29_instantanea_sin_cierres_futuros() -> None:
    a = asset("A", [*flat(2), (100, 101, 99, 100), (100, 101, 99, 105), *flat(3, 105)], market="NYSE",
              open_at=time(14, 30), close_at=time(21, 0))
    result = sim.simulate(market(a), [signal(a, 0, 90, 200)], EUR, spec(max_hold_bars=4))
    snap = next(s for s in result.snapshots if s.day == a.session_dates[2])
    units = result.trades[0].units
    assert snap.at == datetime.combine(a.session_dates[2], time(23, 59, 59), UTC)
    assert snap.long_value == pytest.approx(units * 100.0)


def test_t30_activo_tardio_entra_al_terminar_su_calentamiento() -> None:
    a = asset("ARM", flat(8), eligible_from=4)
    b = asset("B", flat(8))
    result = sim.simulate(market(a, b), [signal(a, 1, 95, 200), signal(a, 4, 95, 200)], EUR, spec(max_hold_bars=1))
    assert result.counters.get("senal_fuera_de_ventana") == 1 and len(result.trades) == 1
    bench = sim.simulate_benchmark(market(a, b), EUR, spec())
    first = next(row for row in rows_of_bench(bench, "BH_BUY") if row["asset"] == "ARM")
    assert first["session_date"] == str(a.session_dates[4])


def test_t31_dividendo_en_activo_con_split() -> None:
    ra, rb = _split_case(0.5)
    assert rb.dividends_eur == pytest.approx(ra.dividends_eur) and ra.dividends_eur > 0


def test_t32_precio_efectivo_rechaza_lo_que_el_observado_admitiria() -> None:
    a = asset("A", flat(6))
    result = sim.simulate(market(a), [signal(a, 0, 95, 200, entry_max=100.0)], EUR, spec(slippage_bps=5))
    assert rows_of(result, "ENTRY_REJECTED")[0]["reason"] == sim.ABOVE_MAX_ENTRY
    admitted = sim.simulate(market(a), [signal(a, 0, 95, 200, entry_max=100.0)], EUR, spec(slippage_bps=0, max_hold_bars=2))
    assert len(admitted.trades) == 1


def test_t33_coste_igual_a_p4_cuando_salida_igual_a_entrada() -> None:
    a = asset("A", flat(6))
    result = sim.simulate(market(a), [signal(a, 0, 95, 200)], EUR, spec(fee_rate=0.001, max_hold_bars=2))
    trade = result.trades[0]
    assert trade.exit_eff == trade.entry_eff
    assert trade.fees_local == pytest.approx(0.002 * trade.entry_eff * trade.units)


def test_t34_cash_nunca_negativo_con_entradas_simultaneas() -> None:
    assets = [asset(f"S{k}", flat(8)) for k in range(15)]
    signals = [signal(x, 0, 99, 200) for x in assets]
    result = sim.simulate(market(*assets), signals, EUR, spec(fee_rate=0.001, slippage_bps=5, max_hold_bars=2))
    assert min(row["cash_after"] for row in result.ledger if row["cash_after"] != "") >= 0
    assert result.counters.get(sim.INSUFFICIENT_CASH, 0) >= 1


def test_t35_policy_sha256_de_p5_se_regenera() -> None:
    config = load_config("config.yaml")
    identities = p6.policy_identities(config)
    for policy, (policy_hash, cfg_hash) in p6.POLICY_HASHES.items():
        assert identities[policy] == {"policy_sha256": policy_hash, "advisor_config_hash": cfg_hash}


def test_t36_contrasplit() -> None:
    ra, rb = _split_case(2.0)
    assert rb.trades[0].units == pytest.approx(ra.trades[0].units / 2)
    assert rb.snapshots[-1].equity == pytest.approx(ra.snapshots[-1].equity)


def test_t37_cash_insuficiente_solo_por_la_comision() -> None:
    a = asset("A", flat(6))
    result = sim.simulate(market(a), [signal(a, 0, 50, 200)], EUR,
                          spec(fee_rate=0.001, max_position_pct=100, risk_pct=100))
    assert rows_of(result, "ENTRY_REJECTED")[0]["reason"] == sim.INSUFFICIENT_CASH
    no_fee = sim.simulate(market(a), [signal(a, 0, 50, 200)], EUR, spec(max_position_pct=100, risk_pct=100, max_hold_bars=2))
    assert len(no_fee.trades) == 1


def test_t38_pf_sin_perdidas_con_n_minimo() -> None:
    trades_m = {"n_closed": 100, "profit_factor_local": None, "profit_factor_local_sin_perdidas": True, "mean_R_local": 0.5}
    out = sim.criterion(trades_m, {"max_drawdown": -0.1}, {"excess_CAGR_pp": 1.0})
    assert out["condiciones"]["profit_factor_local>1"] is True and out["etiqueta"] == sim.LABEL_PASS
    short = sim.criterion({**trades_m, "n_closed": 99}, {"max_drawdown": -0.1}, {"excess_CAGR_pp": 1.0})
    assert short["etiqueta"] == sim.LABEL_NO_SAMPLE


def test_t39_sesion_sin_barra_entra_en_la_barra_siguiente() -> None:
    days = business_days(date(2024, 1, 1), 6, skip=(date(2024, 1, 3),))
    a = asset("A", flat(6), days=days)
    result = sim.simulate(market(a), [signal(a, 1, 95, 200)], EUR, spec(max_hold_bars=2))
    entry = rows_of(result, "ENTRY")[0]
    assert entry["session_date"] == str(date(2024, 1, 4))


def _context_closes() -> Dict[str, pd.Series]:
    out: Dict[str, pd.Series] = {}
    for symbol, market_name, tz in (("^VIX", "NYSE", "America/New_York"), ("^STOXX50E", "XETRA", "Europe/Berlin"),
                                    ("^N225", "JPX", "Asia/Tokyo"), ("^HSI", "HKG", "Asia/Hong_Kong")):
        sessions = expected_sessions(market_name, date(2023, 1, 2), date(2024, 6, 28))
        index = [pd.Timestamp(d).tz_localize(tz).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ") for d in sessions]
        out[symbol] = pd.Series([20.0 + (k % 7) for k in range(len(sessions))], index=index)
    return out


def test_t40_contexto_point_in_time_causal() -> None:
    config = load_config("config.yaml")
    settle = config.data_quality.settlement_minutes
    resolver = PointInTimeContextResolver(_context_closes(), config.market_context, asia_symbols=("^HSI", "^N225"),
                                          settlement_minutes=settle)
    for market_name in ("XETRA", "NYSE", "JPX", "HKG"):
        sessions = expected_sessions(market_name, date(2024, 3, 1), date(2024, 4, 30))
        for signal_day, entry_day in zip(sessions, sessions[1:]):
            ts = analysis_timestamp_for_signal(market_name, signal_day, entry_day, settlement_minutes=settle)
            if ts is None:
                continue
            result = resolver.resolve(ts)
            if result.vix_session is not None:
                assert session_close_at("NYSE", result.vix_session) + timedelta(minutes=settle) <= ts
            if result.trend_used_session is not None:
                assert session_close_at("XETRA", result.trend_used_session) + timedelta(minutes=settle) <= ts
            for symbol, (_, last) in result.asia_sessions.items():
                asia_market = {"^N225": "JPX", "^HSI": "HKG"}[symbol]
                assert session_close_at(asia_market, last) + timedelta(minutes=settle) <= ts
            # Fortaleza relativa: el benchmark de la plaza cierra antes del analysis_timestamp.
            for bench_market in ("NYSE", "XETRA", "JPX"):
                if signal_day in expected_sessions(bench_market, signal_day, signal_day):
                    assert session_close_at(bench_market, signal_day) <= ts


def test_t41_desempate_comun_e_independiente_del_system_sha256() -> None:
    sid_a, sid_b = _ids_with_hash_order_opposite_to_alphabet()
    a, b = asset("A", flat(8)), asset("B", flat(8))
    signals = [signal(a, 0, 99, 200, sid=sid_a), signal(b, 0, 99, 200, sid=sid_b)]
    entered = []
    for system in ("1" * 64, "f" * 64):
        result = sim.simulate(market(a, b), signals, EUR,
                              replace(spec(max_position_pct=60, risk_pct=50, max_hold_bars=2), system_sha256=system))
        entered.append(rows_of(result, "ENTRY")[0]["signal_id"])
    assert entered[0] == entered[1] == sid_b


def test_t42_r_local_frente_a_r_eur_decide_el_local() -> None:
    a = asset("A", [(100, 100.5, 99.5, 100), (100, 101, 99, 100), (100, 103, 99.5, 102), *flat(2, 102)], currency="USD")
    fx = sim.FxTable({"USD": [(datetime(2023, 12, 1, tzinfo=UTC), 1.0), (datetime(2024, 1, 2, 12, tzinfo=UTC), 1.2)]})
    result = sim.simulate(market(a), [signal(a, 0, 95, 200)], fx, spec(max_hold_bars=2))
    trade = result.trades[0]
    assert trade.trade_R_local > 0 > trade.trade_R_eur
    trades_m = sim.trade_metrics(result.trades)
    out = sim.criterion(trades_m, {"max_drawdown": -0.01}, {"excess_CAGR_pp": 1.0})
    assert out["condiciones"]["mean_R_local>0"] is True


def test_t43_sentido_del_fx() -> None:
    fx = sim.FxTable({"USD": [(datetime(2024, 1, 1, tzinfo=UTC), 1.10)]})
    quote = fx.quote("USD", datetime(2024, 1, 2, tzinfo=UTC))
    assert quote.rate_to_eur == pytest.approx(1 / 1.10) and round(quote.rate_to_eur, 3) == 0.909


def test_t44_sizing_una_vez_por_lote() -> None:
    a, b = asset("A", flat(8)), asset("B", flat(8))
    result = sim.simulate(market(a, b), [signal(a, 0, 90, 200), signal(b, 0, 80, 200)], EUR,
                          spec(fee_rate=0.001, max_hold_bars=2))
    units = {row["asset"]: row["units_after"] for row in rows_of(result, "ENTRY")}
    # Las dos usan la equity del lote (100.000), no la que queda tras la comisión de la primera.
    assert units["A"] == 0.005 * 100_000 / 10 and units["B"] == 0.005 * 100_000 / 20


def test_t45_posicion_comprada_tras_su_cierre_se_valora_a_su_entrada() -> None:
    days = business_days(date(2024, 1, 1), 6)
    eu = asset("EU", [(100, 100.5, 99.5, 100), (150, 151, 149, 150), *flat(4, 150)], days=days)
    us = asset("US", flat(6), market="NYSE", open_at=time(14, 30), close_at=time(21, 0), days=days)
    result = sim.simulate(market(eu, us), [signal(eu, 0, 140, 300, entry_max=200), signal(us, 0, 95, 200)], EUR,
                          spec(max_hold_bars=2))
    us_units = next(row["units_after"] for row in rows_of(result, "ENTRY") if row["asset"] == "US")
    assert us_units == pytest.approx(0.005 * 100_000 / 5)


def test_t46_contexto_point_in_time_nunca_legacy() -> None:
    config = load_config("config.yaml")
    resolver = PointInTimeContextResolver(_context_closes(), config.market_context, asia_symbols=("^HSI", "^N225"),
                                          settlement_minutes=config.data_quality.settlement_minutes)
    result = resolver.resolve(datetime(2024, 4, 3, 6, 0, tzinfo=UTC))
    assert result.context is not None and result.context.source == "point_in_time"
    assert p6.system_payload(config, "B2", p6.POPULATION_OPERAR, 5.0, _window())["modo_de_contexto"] == "point_in_time"


def test_t47_salida_de_cierre_empatada_no_financia_apertura_de_otra_plaza() -> None:
    days = business_days(date(2024, 1, 1), 6)
    hk = asset("HK", [*flat(2), (100, 100.5, 90, 95), *flat(3)], market="HKG", open_at=time(1, 30),
               close_at=time(8, 0), days=days, region="ASIA")
    eu = asset("EU", flat(6), open_at=time(8, 0), close_at=time(16, 30), days=days)
    result = sim.simulate(market(hk, eu), [signal(hk, 0, 95, 200), signal(eu, 1, 90, 200)], EUR,
                          spec(max_position_pct=100, risk_pct=100))
    rejected = rows_of(result, "ENTRY_REJECTED")
    assert rejected and rejected[0]["asset"] == "EU" and rejected[0]["reason"] == sim.INSUFFICIENT_CASH


@pytest.mark.parametrize("market_name", ["XETRA", "PAR", "AMS", "MIL", "MCE", "NYSE", "NASDAQ", "JPX", "HKG"])
def test_t48_cadena_causal_por_plaza(market_name: str) -> None:
    settle = load_config("config.yaml").data_quality.settlement_minutes
    from advisor.data.calendars import exchange_calendar

    calendar: Any = exchange_calendar(market_name)
    checked = 0
    for start, end in ((date(2024, 3, 4), date(2024, 4, 12)), (date(2024, 10, 14), date(2024, 11, 15))):
        sessions = expected_sessions(market_name, start, end)
        for signal_day, entry_day in zip(sessions, sessions[1:]):
            ts = analysis_timestamp_for_signal(market_name, signal_day, entry_day, settlement_minutes=settle)
            if ts is None:
                continue
            opened = calendar.session_open(pd.Timestamp(entry_day)).to_pydatetime()
            assert session_close_at(market_name, signal_day) + timedelta(minutes=settle) <= ts < opened
            checked += 1
    assert checked > 10


# ---------------------------------------------------------------------------
# Regresiones y guardas.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("bar", "entry_bar"),
    [
        ((90, 92, 88, 91), False), ((100, 101, 94, 99), False), ((112, 113, 111, 112), False),
        ((112, 113, 94, 100), False), ((100, 111, 99, 105), False), ((100, 101, 99, 100), False),
        ((100, 111, 94, 100), True), ((100, 101, 94, 99), True),
    ],
)
def test_regresion_semantica_de_check_exit(bar: Tuple[float, float, float, float], entry_bar: bool) -> None:
    stop, target = 95.0, 110.0
    engine_price, engine_reason = _check_exit(pd.Series({"Open": bar[0], "High": bar[1], "Low": bar[2], "Close": bar[3]}),
                                              stop, target, entry_bar)
    rows = [(100, 100.5, 99.5, 100), (100, 100.5, 99.5, 100) if not entry_bar else tuple(bar), tuple(bar), *flat(2)]
    a = asset("A", rows)
    result = sim.simulate(market(a), [signal(a, 0, stop, target)], EUR, spec(max_hold_bars=10))
    trade = result.trades[0]
    exit_bar = 1 if entry_bar else 2
    if engine_reason is None:
        assert trade.exit_reason in (sim.EXIT_TIME, sim.EXIT_FINAL) or trade.exit_ts > sim.utc_iso(a.close_utc[exit_bar])
    else:
        expected = {ENGINE_STOP: sim.EXIT_STOP, ENGINE_TARGET: sim.EXIT_TARGET}[engine_reason]
        assert (trade.exit_reason, trade.exit_eff) == (expected, pytest.approx(engine_price))


def test_regresion_p4_p5_y_motor_intactos() -> None:
    import advisor.research.p4 as p4
    import advisor.research.p5 as p5

    assert p5.P5_PREREG_SHA == "a7c3d238d651b4ea8f48834848c03c0a5a462dfa"
    assert p4.SEED == 20260830 and p5.EXPECTED_P5_COMPARISONS == 71
    assert Path("advisor/backtest/engine.py").read_text(encoding="utf-8").count("Sin deslizamiento") == 1


def test_guarda_datos_reales_sin_autorizacion() -> None:
    """Fuera de la ejecución sellada no se pueden ni construir datos reales, con o sin contrato."""

    for contract in (None, frozenset({spec()})):
        with pytest.raises(sim.P6OutcomeGateError):
            sim.MarketData({}, date(2024, 1, 1), date(2024, 1, 2), origin=sim.ORIGIN_REAL, contract=contract)


def _frozen_report(**extra: Any) -> Dict[str, Any]:
    """Informe de preflight definitivo con las identidades congeladas (sin desenlaces)."""

    return {
        "ok": True,
        "definitivo": True,
        "identidad": {
            "p6_prereg_sha": p6.P6_PREREG_SHA, "p6_executor_sha": "sha", "git_dirty": False,
            "prereg_en_historia": True, "p6_data_id": p6.P6_DATA_ID, "data_vintage_id": p6.DATA_VINTAGE_ID,
            "universe_vintage_id": p6.UNIVERSE_VINTAGE_ID, "fx_vintage_id": p6.FX_VINTAGE_ID,
            "sector_map": p6.SECTOR_MAP_SHA256,
        },
        "politicas": {policy: {"policy_sha256": ph, "advisor_config_hash": ch} for policy, (ph, ch) in p6.POLICY_HASHES.items()},
        **extra,
    }


def test_confirmatoria_rechaza_marca_existente(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / p6.RUN_MARKER).write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(p6, "RUN_DIR", run_dir)
    ident = p6.P6Identity("sha", False, True, p6.EXPECTED_CONFIG_HASH, "1.0")
    with pytest.raises(p6.P6AlreadyExecutedError):
        p6.run_confirmatory(load_config("config.yaml"), None, ident, run_dir)  # type: ignore[arg-type]


def test_criterio_solo_cinco_condiciones_y_salidas_permitidas() -> None:
    out = sim.criterion({"n_closed": 150, "profit_factor_local": 1.2, "profit_factor_local_sin_perdidas": False,
                         "mean_R_local": 0.1}, {"max_drawdown": -0.26}, {"excess_CAGR_pp": 3.0})
    assert set(out["condiciones"]) == {"N_closed>=100", "profit_factor_local>1", "mean_R_local>0",
                                       "max_drawdown>=-25%", "excess_CAGR_pp>0"}
    assert out["etiqueta"] == sim.LABEL_FAIL
    for labels, expected in (({"B2": sim.LABEL_PASS, "S2": sim.LABEL_FAIL}, ("B2",)),
                             ({"B2": sim.LABEL_PASS, "S2": sim.LABEL_PASS}, ("B2", "S2")),
                             ({"B2": sim.LABEL_NO_SAMPLE, "S2": sim.LABEL_FAIL}, ())):
        assert sim.survivors(labels) == expected


def test_identidades_congeladas_de_datos() -> None:
    assert p6.p6_data_id() == p6.P6_DATA_ID
    fx, meta = p6.load_fx()
    assert meta["fuente_usada"] == "B" and fx.quote("USD", datetime(2023, 1, 5, tzinfo=UTC)).rate > 0
    assert len(p6.load_sector_map()) == 90


def _synthetic_vintage(symbols: Dict[str, Tuple[str, str]], start: date, end: date) -> Any:
    """Cosecha **sintética** (precios inventados) con símbolos reales, para ejercitar la ruta real sin desenlaces."""

    import numpy as np

    from advisor.research.vintage import VintageLoad, build_views

    rng = np.random.default_rng(20261003)
    by_symbol = {}
    for symbol, (market_name, tz) in symbols.items():
        sessions = expected_sessions(market_name, start, end)
        index = [pd.Timestamp(d).tz_localize(tz).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ") for d in sessions]
        steps = rng.normal(0.0006, 0.015, len(sessions))
        close = 100.0 * np.exp(np.cumsum(steps))
        open_ = np.concatenate([[100.0], close[:-1]]) * (1 + rng.normal(0, 0.003, len(sessions)))
        high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.006, len(sessions))))
        low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.006, len(sessions))))
        dividends = np.where(np.arange(len(sessions)) % 63 == 40, 0.5, 0.0)
        raw = pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Adj Close": close,
                            "Volume": 1_000_000.0, "Dividends": dividends, "Stock Splits": 0.0}, index=index)
        by_symbol[symbol] = build_views(raw)
    return VintageLoad(data_vintage_id=p6.DATA_VINTAGE_ID, manifest={}, by_symbol=by_symbol)


def test_r_reconstruible_desde_el_ledger_publicado() -> None:
    m, fx, signals = p6.synthetic_market()
    result = sim.simulate(m, signals, fx, spec(fee_rate=0.001, slippage_bps=5))
    entries = {row["position_id"]: row for row in result.ledger if row["event_type"] == "ENTRY"}
    exits = {row["position_id"]: row for row in result.ledger if row["event_type"] == "EXIT"}
    divs: Dict[str, float] = {}
    for row in result.ledger:
        if row["event_type"] == "DIVIDEND":
            divs[row["position_id"]] = divs.get(row["position_id"], 0.0) + row["market_price"] * row["units_before"]
    for trade in result.trades:
        entry, exit_ = entries[trade.position_id], exits[trade.position_id]
        units = entry["units_after"]
        risk = (entry["effective_price"] - entry["stop"]) * units
        pnl = units * (exit_["effective_price"] - entry["effective_price"]) - 0.001 * units * (
            entry["effective_price"] + exit_["effective_price"]) + divs.get(trade.position_id, 0.0)
        assert pnl / risk == pytest.approx(trade.trade_R_local)
    assert sim.trades_csv(result.trades).count("\n") == len(result.trades) + 1


def test_benchmark_liquida_en_close_exit_y_cuadra() -> None:
    a = asset("A", [*flat(2), (100, 100.5, 99.5, 100, 3.0), *flat(2)])
    bench = sim.simulate_benchmark(market(a), EUR, spec(fee_rate=0.001, slippage_bps=5))
    final = rows_of_bench(bench, "BH_SELL_FINAL")[0]
    assert final["fase"] == sim.CLOSE_EXIT
    assert sim.check_ledger_flows(bench.ledger, 100_000.0) == pytest.approx(bench.snapshots[-1].equity)


def test_periodos_por_año_del_contrato() -> None:
    series = [(date(2024, 1, 1), 100.0), (date(2024, 1, 2), 101.0), (date(2024, 1, 3), 102.0)]
    ppy = sim.periods_per_year(series)
    assert sim.path_metrics(series, expected_ppy=ppy)["periodos_por_año"] == ppy
    with pytest.raises(sim.AccountingError):
        sim.path_metrics(series, expected_ppy=252.0)


def test_capital_pedido_frente_a_disponible() -> None:
    a, b = asset("A", flat(8)), asset("B", flat(8))
    result = sim.simulate(market(a, b), [signal(a, 0, 99, 200), signal(b, 0, 99, 200)], EUR,
                          spec(max_position_pct=60, risk_pct=50, max_hold_bars=2))
    occupancy = sim.cash_occupancy(result.counters, result.ledger)
    assert occupancy["rechazadas_por_cash"] == 1 and occupancy["fraccion_ejecutables_rechazadas_por_cash"] == 0.5
    assert occupancy["capital_pedido_rechazado_eur"] == pytest.approx(60_000.0)
    assert occupancy["capital_disponible_en_esos_rechazos_eur"] == pytest.approx(40_000.0)


def _structure_with_dividends(dividend_scale: float) -> Tuple[Any, Any]:
    """Activo sintético con split 2:1 y dos fechas ex; ``Adj Close`` construido como Yahoo."""

    index = [f"2024-01-0{d}" for d in range(1, 8)]
    close = [100.0, 101.0, 50.0, 51.0, 52.0, 53.0, 54.0]
    dividends = [0.0, 0.5, 0.0, 0.0, 0.3, 0.0, 0.0]
    splits = [0.0, 0.0, 2.0, 0.0, 0.0, 0.0, 0.0]
    factor = [1.0] * len(index)
    for k in range(len(index) - 1, 0, -1):
        factor[k - 1] = factor[k] * (1.0 - dividends[k] / close[k - 1] if dividends[k] else 1.0)
    prices = pd.DataFrame({"Close": close, "Adj Close": [c * f for c, f in zip(close, factor)]}, index=index)
    # La escala solo se aplica antes del split: así se ve un dividendo previo sin ajustar.
    scaled = [d * dividend_scale if k < 2 else d for k, d in enumerate(dividends)]
    actions = pd.DataFrame({"Dividends": scaled, "Stock Splits": splits}, index=index)
    structure = p6.VintageStructure("sintetica", {}, {"SPL": actions,
                                                       "R6C0.DE": pd.DataFrame({"Dividends": [0.0, 0.20711999],
                                                                                "Stock Splits": [0.0, 0.0]})})

    def rows(_vid: str, symbol: str, stamps: Sequence[str], columns: Sequence[str]) -> pd.DataFrame:
        assert symbol == "SPL"
        return prices.loc[list(stamps), list(columns)]

    return structure, rows


def test_coherencia_dividendo_split_detecta_dividendo_sin_ajustar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(p6, "asset_list", lambda: ["R6C0.DE", "SPL"])
    monkeypatch.setattr(p6, "DIVIDEND_SPLIT_ASSETS", 1)
    monkeypatch.setattr(p6, "XETRA_FX_SUSPECTS", ())

    structure, rows = _structure_with_dividends(1.0)
    checks, section = p6._dividend_split_checks(structure, rows)
    assert all(ok for *_, ok in checks), checks
    assert section["activos_con_split"]["SPL"]["fechas_ex"] == 2 and section["xetra_importe_no_redondo"] == ["R6C0.DE"]
    assert section["activos_con_split"]["SPL"]["fechas_ex_previas_a_split"] == 1

    # Un dividendo previo al split en unidades sin ajustar (×2) rompe la identidad en esa fecha ex.
    structure, rows = _structure_with_dividends(2.0)
    checks, section = p6._dividend_split_checks(structure, rows)
    failed = [name for name, *_, ok in checks if not ok]
    assert failed == ["coherencia algebraica Dividends/splits (fechas ex fuera de tolerancia)"]
    assert len(section["fuera_de_tolerancia"]) == 1 and "2024-01-02" in section["fuera_de_tolerancia"][0]


def test_cli_preflight_no_carga_la_cosecha_de_precios(monkeypatch: pytest.MonkeyPatch) -> None:
    import argparse

    import advisor.main as main

    def forbidden(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("el preflight no debe cargar la cosecha de precios")

    seen: Dict[str, Any] = {}

    def fake_preflight(_config: Any, _universe: Any, structure: Any, _ident: Any, **_k: Any) -> Tuple[bool, Dict[str, Any]]:
        seen["structure"] = structure
        return True, {"modo": "x", "ventana": {"inicio": "a", "fin": "b"}, "new_p6_outcomes_read": False, "checks": []}

    import advisor.research.vintage as vintage_module

    monkeypatch.setattr(main, "load_vintage", forbidden)
    monkeypatch.setattr(vintage_module, "load_vintage", forbidden)
    monkeypatch.setattr(p6, "load_structure", lambda: "estructura")
    monkeypatch.setattr(p6, "run_preflight", fake_preflight)
    monkeypatch.setattr(p6, "synthetic_determinism", lambda: {})
    monkeypatch.setattr(p6, "development_mode", lambda: True)
    monkeypatch.setattr(p6, "current_identity", lambda _c: p6.P6Identity("sha", True, True, "h", "1.0"))

    assert main.cmd_p6(argparse.Namespace(fase="preflight"), load_config("config.yaml"), None) == 0  # type: ignore[arg-type]
    assert seen["structure"] == "estructura"


def test_preflight_real_sin_cargar_precios(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """El run_preflight real, sobre la cosecha congelada, con la carga de precios prohibida.

    RUN_DIR apunta a un directorio vacío: el test comprueba el preflight en un entorno anterior a la
    ejecución y no depende de que la ejecución histórica de P6 exista ya en el repositorio.
    """

    import advisor.research.vintage as vintage_module
    from advisor.universe.loader import load_universe

    # En CI el manifiesto está versionado pero los CSV no: se comprueba un CSV.
    if not (Path("data/vintages") / p6.DATA_VINTAGE_ID / "AAPL.csv").is_file():
        pytest.skip("data/vintages no está disponible")

    def forbidden(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("el preflight no debe cargar la cosecha de precios")

    for module, name in ((vintage_module, "load_vintage"), (vintage_module, "build_views")):
        monkeypatch.setattr(module, name, forbidden)
    monkeypatch.setattr(p6, "RUN_DIR", tmp_path / "run")
    config = load_config("config.yaml")
    ok, report = p6.run_preflight(config, load_universe(config.universe_path), p6.load_structure(),
                                  p6.current_identity(config), development=True, write=False)
    assert ok, [row for row in report["checks"] if not row["ok"]]
    assert report["ventana"]["inicio"] == "2022-06-14" and report["ventana"]["fin"] == "2026-08-27"
    assert not report["dividendos_splits"]["fuera_de_tolerancia"]


def test_marca_en_run_dir_consume_p6(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Con la marca en RUN_DIR la guarda da P6 por consumido y no deja iniciar otra ejecución."""

    from advisor.universe.loader import load_universe

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    monkeypatch.setattr(p6, "RUN_DIR", run_dir)
    config = load_config("config.yaml")
    universe = load_universe(config.universe_path)

    def marker_check() -> Tuple[Any, Any, bool]:
        rows = [row for row in p6.guard_checks(config, universe, _window()) if row[0] == "marca confirmatoria ausente"]
        assert len(rows) == 1
        return rows[0][1], rows[0][2], rows[0][3]

    assert marker_check() == (False, False, True)
    (run_dir / p6.RUN_MARKER).write_text("{}\n", encoding="utf-8")
    assert marker_check() == (True, False, False)
    ident = p6.P6Identity("sha", False, True, p6.EXPECTED_CONFIG_HASH, "1.0")
    with pytest.raises(p6.P6AlreadyExecutedError):
        p6.run_confirmatory(config, universe, ident, run_dir)
    assert sorted(path.name for path in run_dir.iterdir()) == [p6.RUN_MARKER]


# ---------------------------------------------------------------------------
# Ejecución confirmatoria sellada (guarda de desenlaces). Todo con datos sintéticos en tmp_path.
# ---------------------------------------------------------------------------


def _sealed_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    stored: Optional[Dict[str, Any]] = None,
    live: Optional[Dict[str, Any]] = None,
    fail_signals: bool = False,
) -> Tuple[Path, Any, Any, Dict[str, Any]]:
    """Preflight definitivo en disco (tmp), preflight vivo y cosecha sintéticos; constructores reales falsos."""

    m, fx, signals = p6.synthetic_market()
    days = sim.snapshot_days(m)
    ppy = len(days) / ((days[-1] - m.window_start).days / 365.25)
    window = p6.Window(m.window_start, m.window_end, m.window_start, m.window_start, 0, len(days), ppy)
    config = load_config("config.yaml")
    report = _frozen_report(ventana=window.as_dict(), system_hashes=p6.system_hashes(config, window),
                            determinismo=p6.synthetic_determinism())
    run_dir, pre_dir = tmp_path / "run", tmp_path / "preflight"
    pre_dir.mkdir(exist_ok=True)
    (pre_dir / "p6-preflight.json").write_text(json.dumps(report if stored is None else stored), encoding="utf-8")
    monkeypatch.setattr(p6, "RUN_DIR", run_dir)
    monkeypatch.setattr(p6, "PREFLIGHT_DIR", pre_dir)
    monkeypatch.setattr(p6, "executor_unchanged_since", lambda *_a, **_k: True)
    monkeypatch.setattr(p6, "_sources", lambda: (config, None))
    monkeypatch.setattr(p6, "_live_preflight", lambda *_a, **_k: (True, report if live is None else live))
    monkeypatch.setattr(p6, "derive_window", lambda *_a, **_k: window)
    monkeypatch.setattr(p6, "load_fx", lambda: (fx, {"fuente_usada": "B"}))
    monkeypatch.setattr(p6, "load_sector_map", lambda: {})
    import advisor.research.vintage as vintage_module

    monkeypatch.setattr(vintage_module, "load_vintage", lambda *_a, **_k: p6.VintageLoad("sintetica", {}, {}))

    def fake_market(token: Any, *a: Any, **_k: Any) -> sim.MarketData:
        p6.require_token(token)
        return replace(m, origin=sim.ORIGIN_REAL, contract=a[-1])

    def fake_signals(token: Any, *_a: Any, **_k: Any) -> Tuple[List[sim.Signal], Dict[str, int]]:
        p6.require_token(token)
        if fail_signals:
            raise RuntimeError("fallo inyectado tras la marca")
        return list(signals), {"senales": len(signals)}

    monkeypatch.setattr(p6, "build_real_market", fake_market)
    monkeypatch.setattr(p6, "build_real_signals", fake_signals)
    ident = p6.P6Identity("sha", False, True, p6.EXPECTED_CONFIG_HASH, "1.0")
    return run_dir, config, ident, report


def _run(config: Any, ident: Any, run_dir: Path) -> Tuple[int, str]:
    return p6.run_confirmatory(config, None, ident, run_dir)  # type: ignore[arg-type]


def test_s01_s03_no_existen_piezas_componibles() -> None:
    """(1–3) _issue_clearance, create_marker_exclusive y build_confirmatory_token ya no existen."""

    for name in ("_issue_clearance", "create_marker_exclusive", "build_confirmatory_token", "authorization",
                 "_abrir_confirmatoria", "_CLEARANCES", "_CREATED_MARKERS", "_ISSUED_TOKENS"):
        assert not hasattr(p6, name), name


def test_s04_token_fabricado_no_vale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(4) Un ConfirmatoryToken construido a mano no se acepta, ni siquiera tras una apertura real."""

    run_dir, config, ident, _ = _sealed_env(tmp_path, monkeypatch)
    with pytest.raises(sim.P6OutcomeGateError):
        p6.require_token(None)
    code, text = _run(config, ident, run_dir)
    assert code == 0 and isinstance(text, str)
    marker = run_dir / p6.RUN_MARKER
    digest = hashlib.sha256(marker.read_bytes()).hexdigest()
    for fake in (p6.ConfirmatoryToken(marker, digest), p6.ConfirmatoryToken(marker, digest, "0" * 64)):
        with pytest.raises(sim.P6OutcomeGateError):
            p6.require_token(fake)
    # Terminada la ejecución, no se pueden construir datos reales, ni con un contrato propio.
    with pytest.raises(sim.P6OutcomeGateError):
        replace(p6.synthetic_market()[0], origin=sim.ORIGIN_REAL,
                contract=frozenset({sim.SimSpec("B2", "0" * 64)}))


def test_s05_s07_no_se_aceptan_payload_preflight_ni_ventana() -> None:
    """(5–7) Ningún punto de entrada acepta payload, preflight, ventana, token ni hashes."""

    import inspect

    assert list(inspect.signature(p6._ejecutar_confirmatoria_sellada).parameters) == []
    assert list(inspect.signature(p6._verified_authorization).parameters) == []
    assert list(inspect.signature(p6.run_confirmatory).parameters) == ["config", "universe", "ident", "out_dir"]
    forbidden = {"payload", "preflight", "stored", "live", "window", "ventana", "token", "clearance", "hashes",
                 "fingerprint", "marker", "marker_path"}
    for name in ("run_confirmatory", "_ejecutar_confirmatoria_sellada", "_verified_authorization"):
        assert not forbidden & set(inspect.signature(getattr(p6, name)).parameters), name


def test_s08_sin_preflight_definitivo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(8) Sin preflight definitivo en disco no hay apertura ni marca."""

    run_dir, config, ident, _ = _sealed_env(tmp_path, monkeypatch)
    (p6.PREFLIGHT_DIR / "p6-preflight.json").unlink()
    with pytest.raises(sim.P6OutcomeGateError, match="no existe el preflight definitivo"):
        _run(config, ident, run_dir)
    assert not (run_dir / p6.RUN_MARKER).exists()


@pytest.mark.parametrize("cambio, motivo", [
    ({"ok": False}, "ok != true"),
    ({"definitivo": False}, "no es definitivo"),
    ({"ventana": {"inicio": "otra"}}, "no coincide"),
    ({"identidad": {**_frozen_report()["identidad"], "p6_prereg_sha": "0" * 40}}, "identidades congeladas"),
    ({"identidad": {**_frozen_report()["identidad"], "p6_data_id": "0" * 64}}, "identidades congeladas"),
    ({"politicas": {}}, "identidades congeladas"),
])
def test_s09_preflight_de_disco_modificado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cambio: Dict[str, Any], motivo: str
) -> None:
    """(9) Preflight de disco modificado → rechazo, sin marca."""

    run_dir, config, ident, report = _sealed_env(tmp_path, monkeypatch)
    (p6.PREFLIGHT_DIR / "p6-preflight.json").write_text(json.dumps({**report, **cambio}), encoding="utf-8")
    with pytest.raises(sim.P6OutcomeGateError, match=motivo):
        _run(config, ident, run_dir)
    assert not (run_dir / p6.RUN_MARKER).exists()


def test_s09_preflight_vivo_distinto_o_incorrecto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir, config, ident, report = _sealed_env(tmp_path, monkeypatch)
    for live, motivo in (({**report, "ventana": {"inicio": "otra"}}, "no coincide"),
                         ({**report, "ok": False}, "no es correcto")):
        monkeypatch.setattr(p6, "_live_preflight", lambda *_a, live=live, **_k: (True, live))
        with pytest.raises(sim.P6OutcomeGateError, match=motivo):
            _run(config, ident, run_dir)
    assert not (run_dir / p6.RUN_MARKER).exists()


def test_s10_codigo_cambiado_desde_el_preflight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir, config, ident, _ = _sealed_env(tmp_path, monkeypatch)
    monkeypatch.setattr(p6, "executor_unchanged_since", lambda *_a, **_k: False)
    with pytest.raises(sim.P6OutcomeGateError, match="ejecutor cambió"):
        _run(config, ident, run_dir)
    assert not (run_dir / p6.RUN_MARKER).exists()


def test_s11_p6_data_id_distinto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir, config, ident, _ = _sealed_env(tmp_path, monkeypatch)
    monkeypatch.setattr(p6, "p6_data_id", lambda: "f" * 64)
    with pytest.raises(sim.P6OutcomeGateError, match="P6_DATA_ID"):
        _run(config, ident, run_dir)
    assert not (run_dir / p6.RUN_MARKER).exists()


def test_s12_ventana_de_la_cosecha_completa_distinta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(12) Si la cosecha completa no reproduce la ventana, se para antes de crear la marca."""

    run_dir, config, ident, _ = _sealed_env(tmp_path, monkeypatch)
    otra = p6.Window(date(2022, 6, 15), date(2026, 8, 27), date(2022, 2, 25), date(2022, 6, 13), 27, 1094, 260.0)
    monkeypatch.setattr(p6, "derive_window", lambda *_a, **_k: otra)
    with pytest.raises(p6.P6PreflightError, match="ventana"):
        _run(config, ident, run_dir)
    assert not (run_dir / p6.RUN_MARKER).exists()


def test_s13_marca_existente(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir, config, ident, _ = _sealed_env(tmp_path, monkeypatch)
    run_dir.mkdir()
    (run_dir / p6.RUN_MARKER).write_text("{}\n", encoding="utf-8")
    with pytest.raises(p6.P6AlreadyExecutedError):
        _run(config, ident, run_dir)
    with pytest.raises(p6.P6AlreadyExecutedError):
        p6._ejecutar_confirmatoria_sellada()


def test_s14_ruta_alternativa_de_marca(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(14) Ninguna función recibe la ruta de la marca y run_confirmatory solo escribe en RUN_DIR."""

    run_dir, config, ident, _ = _sealed_env(tmp_path, monkeypatch)
    with pytest.raises(p6.P6PreflightError, match="solo escribe"):
        _run(config, ident, tmp_path / "otra")
    assert not (tmp_path / "otra").exists() and not (run_dir / p6.RUN_MARKER).exists()


def test_s15_s17_solo_los_simspec_pre_registrados(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(15) SimSpec no pre-registrado, (16) system_sha256 alterado, (17) benchmark alterado → rechazo."""

    config = load_config("config.yaml")
    m, _fx, _signals = p6.synthetic_market()
    days = sim.snapshot_days(m)
    window = p6.Window(m.window_start, m.window_end, m.window_start, m.window_start, 0, len(days), 252.0)
    hashes = p6.system_hashes(config, window)
    allowed = p6._preregistered_specs(config, hashes)
    guard = p6._spec_guard(allowed)
    assert len(allowed) == 9
    for spec in allowed:
        guard(spec)
    primary = next(spec for spec in allowed if spec.run_id == "B2_primaria_5pb")
    bench = next(spec for spec in allowed if spec.run_id == "benchmark_5pb")
    for bad in (
        sim.SimSpec("B2_exploratoria", primary.system_sha256),
        replace(primary, slippage_bps=20.0),
        replace(primary, risk_pct=2.0),
        replace(primary, system_sha256="0" * 64),
        replace(bench, system_sha256="0" * 64),
        replace(bench, slippage_bps=10.0),
    ):
        with pytest.raises(sim.P6OutcomeGateError, match="no pre-registrado"):
            guard(bad)


def test_s15_flujo_sellado_con_contrato_incompleto_no_ejecuta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Las corridas salen del contrato: si le falta una, el flujo para tras la marca sin resultados."""

    run_dir, config, ident, _ = _sealed_env(tmp_path, monkeypatch)
    real = p6._preregistered_specs
    monkeypatch.setattr(p6, "_preregistered_specs",
                        lambda *a: frozenset(s for s in real(*a) if s.run_id != "C0_primaria_5pb"))
    code, text = _run(config, ident, run_dir)
    assert code == 2 and "C0_primaria_5pb" in text
    assert (run_dir / "p6-parada.json").is_file() and not (run_dir / "p6-resultado.json").exists()


def test_s18_s19_apertura_consume_la_ejecucion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(18) Tras abrir, la marca existe con el payload canónico; (19) una segunda apertura falla."""

    run_dir, config, ident, report = _sealed_env(tmp_path, monkeypatch)
    code, text = _run(config, ident, run_dir)
    assert code == 0, text
    marker = json.loads((run_dir / p6.RUN_MARKER).read_text(encoding="utf-8"))
    persisted = (run_dir / p6.RUN_PAYLOAD).read_bytes()
    assert marker == {"payload": p6.RUN_PAYLOAD, "payload_sha256": hashlib.sha256(persisted).hexdigest()}
    payload = json.loads(persisted)
    assert set(payload) == {"inicio_utc", "p6_prereg_sha", "p6_code_sha_preflight", "head_sha", "p6_data_id",
                            "ventana", "system_hashes", "benchmark_hashes", "label"}
    assert payload["p6_prereg_sha"] == p6.P6_PREREG_SHA and payload["p6_data_id"] == p6.P6_DATA_ID
    assert payload["ventana"] == report["ventana"]
    assert payload["system_hashes"] == {r: report["system_hashes"][r]["system_sha256"] for r, *_ in p6.RUNS}
    assert payload["benchmark_hashes"] == {r: report["system_hashes"][r]["benchmark_sha256"] for r, _ in p6.BENCHMARK_RUNS}
    result = json.loads((run_dir / "p6-resultado.json").read_text(encoding="utf-8"))
    assert set(result["corridas"]) == {run for run, *_ in p6.RUNS} and "token" not in result
    with pytest.raises(p6.P6AlreadyExecutedError):
        _run(config, ident, run_dir)
    with pytest.raises(p6.P6AlreadyExecutedError):
        p6._ejecutar_confirmatoria_sellada()


def test_s20_otro_proceso_ve_la_marca_en_disco(tmp_path: Path) -> None:
    """(20) Otro proceso con la marca ya en disco no puede abrir P6."""

    import subprocess
    import sys

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / p6.RUN_MARKER).write_text("{}\n", encoding="utf-8")
    script = (
        "import sys\nfrom pathlib import Path\nimport advisor.research.p6 as p6\n"
        f"p6.RUN_DIR = Path({str(run_dir)!r})\n"
        "ident = p6.P6Identity('sha', False, True, p6.EXPECTED_CONFIG_HASH, '1.0')\n"
        "try:\n    p6.run_confirmatory(None, None, ident, p6.RUN_DIR)\n"
        "except p6.P6AlreadyExecutedError:\n    print('YA_EJECUTADA'); sys.exit(0)\n"
        "print('ABRIO'); sys.exit(1)\n"
    )
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, cwd=Path.cwd())
    assert done.returncode == 0 and "YA_EJECUTADA" in done.stdout, done.stderr
    assert not (run_dir / "p6-resultado.json").exists()


def test_confirmatoria_sintetica_fallo_tras_la_marca(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir, config, ident, _ = _sealed_env(tmp_path, monkeypatch, fail_signals=True)
    code, text = _run(config, ident, run_dir)
    assert code == 2 and "fallo inyectado" in text
    assert (run_dir / p6.RUN_MARKER).is_file() and (run_dir / "p6-parada.json").is_file()
    with pytest.raises(p6.P6AlreadyExecutedError):
        _run(config, ident, run_dir)


def test_humo_flujo_sellado_con_constructores_reales_sobre_cosecha_sintetica(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """build_real_market, build_real_signals, simulate y benchmark reales, solo por el flujo sellado.

    Los precios son sintéticos (tmp_path): no se abre ningún desenlace de la cosecha real.
    """

    from advisor.universe.loader import load_universe

    config = load_config("config.yaml")
    universe = load_universe(config.universe_path)
    symbols = {
        "SAP.DE": ("XETRA", "Europe/Berlin"), "AAPL": ("NASDAQ", "America/New_York"), "7203.T": ("JPX", "Asia/Tokyo"),
        "^STOXX": ("XETRA", "Europe/Berlin"), "^GSPC": ("NYSE", "America/New_York"), "^N225": ("JPX", "Asia/Tokyo"),
        "^VIX": ("NYSE", "America/New_York"), "^STOXX50E": ("XETRA", "Europe/Berlin"), "^HSI": ("HKG", "Asia/Hong_Kong"),
        "^KS11": ("KSC", "Asia/Seoul"), "^TWII": ("TAI", "Asia/Taipei"), "510300.SS": ("SHH", "Asia/Shanghai"),
    }
    vintage = _synthetic_vintage(symbols, date(2021, 8, 30), date(2023, 3, 31))
    monkeypatch.setattr(p6, "asset_list", lambda: ["7203.T", "AAPL", "SAP.DE"])
    window = p6.derive_window(config, universe, p6.vintage_index(vintage))
    assert window.start > window.sma_complete_session and window.start > window.warmup_last_initial
    report = _frozen_report(ventana=window.as_dict(), system_hashes=p6.system_hashes(config, window))
    pre_dir, run_dir = tmp_path / "preflight", tmp_path / "run"
    pre_dir.mkdir()
    (pre_dir / "p6-preflight.json").write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(p6, "RUN_DIR", run_dir)
    monkeypatch.setattr(p6, "PREFLIGHT_DIR", pre_dir)
    monkeypatch.setattr(p6, "executor_unchanged_since", lambda *_a, **_k: True)
    monkeypatch.setattr(p6, "_sources", lambda: (config, universe))
    monkeypatch.setattr(p6, "_live_preflight", lambda *_a, **_k: (True, report))
    import advisor.research.vintage as vintage_module

    monkeypatch.setattr(vintage_module, "load_vintage", lambda *_a, **_k: vintage)
    monkeypatch.setattr(p6, "load_sector_map", lambda: dict.fromkeys(("7203.T", "AAPL", "SAP.DE"), "Technology"))

    ident = p6.P6Identity("sha", False, True, p6.EXPECTED_CONFIG_HASH, "1.0")
    code, text = _run(config, ident, run_dir)
    assert code == 0, text
    result = json.loads((run_dir / "p6-resultado.json").read_text(encoding="utf-8"))
    assert result["senales"]["B2_todas_las_barras_5pb"].get("senales", 0) > 100
    # Con precios aleatorios casi nada llega a OPERAR: basta con que el contexto PIT y el score se calculen.
    assert result["senales"]["B2_primaria_5pb"].get("no_operar", 0) > 0
    ledger = (run_dir / "tablas" / "benchmark_5pb-ledger.csv").read_text(encoding="utf-8")
    assert "BH_SELL_FINAL" in ledger



@pytest.mark.parametrize("fail_signals", [False, True])
def test_s21_token_revocado_al_terminar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail_signals: bool) -> None:
    """El token no se puede reutilizar tras la ejecución (bien o con error), ni con una autorización propia."""

    run_dir, config, ident, _ = _sealed_env(tmp_path, monkeypatch, fail_signals=fail_signals)
    captured: List[Any] = []
    real_fake_market = p6.build_real_market

    def capture(token: Any, *a: Any, **k: Any) -> sim.MarketData:
        captured.append(token)
        return real_fake_market(token, *a, **k)

    monkeypatch.setattr(p6, "build_real_market", capture)
    code, _text = _run(config, ident, run_dir)
    assert code == (2 if fail_signals else 0) and len(captured) == 1
    token = captured[0]
    assert p6._ACTIVE_TOKEN is None
    with pytest.raises(sim.P6OutcomeGateError, match="no vigente"):
        p6.require_token(token)
    for spec in (sim.SimSpec("B2_exploratoria", "0" * 64), sim.SimSpec("benchmark", "0" * 64)):
        with pytest.raises(sim.P6OutcomeGateError):
            replace(p6.synthetic_market()[0], origin=sim.ORIGIN_REAL, contract=frozenset({spec}))


@pytest.mark.parametrize("parcial", [False, True])
def test_s22_fallo_al_escribir_la_marca(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, parcial: bool) -> None:
    """Un fallo tras O_EXCL consume la ejecución; el payload canónico ya estaba persistido y verificado."""

    import os as os_module

    run_dir, config, ident, report = _sealed_env(tmp_path, monkeypatch)
    real_write = os_module.write
    calls: List[int] = []

    def failing_write(fd: int, data: bytes) -> int:
        calls.append(len(data))
        if parcial and len(calls) == 1:
            return real_write(fd, data[: len(data) // 2])
        raise OSError("disco lleno (inyectado)")

    monkeypatch.setattr(p6.os, "write", failing_write)
    code, text = _run(config, ident, run_dir)
    monkeypatch.setattr(p6.os, "write", real_write)
    assert code == 2 and "disco lleno" in text
    marker = run_dir / p6.RUN_MARKER
    assert marker.is_file() and p6._ACTIVE_TOKEN is None
    persisted = (run_dir / p6.RUN_PAYLOAD).read_bytes()
    canonical = json.loads(persisted)
    assert canonical["ventana"] == report["ventana"] and canonical["p6_data_id"] == p6.P6_DATA_ID
    stop = json.loads((run_dir / "p6-parada.json").read_text(encoding="utf-8"))
    assert stop["marca"]["payload_sha256"] == hashlib.sha256(persisted).hexdigest()
    assert stop["marca"]["bytes_escritos"] == len(marker.read_bytes()) < stop["marca"]["bytes_esperados"]
    assert not (run_dir / "p6-resultado.json").exists()
    with pytest.raises(p6.P6AlreadyExecutedError):
        _run(config, ident, run_dir)


# ---------------------------------------------------------------------------
# Contrato de corridas en los datos reales (p6_sim lo exige por sí mismo) y payload antes de la marca.
# ---------------------------------------------------------------------------


def _live_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> p6.ConfirmatoryToken:
    """Simula, solo en tests, una ejecución sellada en curso: marca en tmp y token vigente."""

    run_dir = tmp_path / "run-viva"
    run_dir.mkdir(exist_ok=True)
    marker = run_dir / p6.RUN_MARKER
    marker.write_text("{}\n", encoding="utf-8")
    token = p6.ConfirmatoryToken(marker, hashlib.sha256(marker.read_bytes()).hexdigest(), "t" * 64)
    monkeypatch.setattr(p6, "RUN_DIR", run_dir)
    monkeypatch.setattr(p6, "_ACTIVE_TOKEN", token)
    return token


@pytest.fixture
def live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> p6.ConfirmatoryToken:
    return _live_run(tmp_path, monkeypatch)


def _contract_market() -> Tuple[sim.MarketData, FrozenSet[sim.SimSpec], Dict[str, sim.SimSpec]]:
    config = load_config("config.yaml")
    m, _fx, _signals = p6.synthetic_market()
    days = sim.snapshot_days(m)
    window = p6.Window(m.window_start, m.window_end, m.window_start, m.window_start, 0, len(days), 252.0)
    contract = p6._preregistered_specs(config, p6.system_hashes(config, window))
    return replace(m, origin=sim.ORIGIN_REAL, contract=contract), contract, {s.run_id: s for s in contract}


def _allow(_spec: sim.SimSpec) -> None:
    """Autorización permisiva: aísla la comprobación propia del contrato en p6_sim."""


def test_c01_contrato_spec_exacto_valido_y_completo(live: p6.ConfirmatoryToken) -> None:
    """(1) Datos reales + spec exacto B2 primaria → válido; el contrato fija las 9 identidades."""

    market, contract, by_run = _contract_market()
    assert set(by_run) == {r for r, *_ in p6.RUNS} | {r for r, _ in p6.BENCHMARK_RUNS} and len(contract) == 9
    b2 = by_run["B2_primaria_5pb"]
    assert (b2.policy_id, b2.population, b2.slippage_bps) == ("B2", p6.POPULATION_OPERAR, 5.0)
    assert by_run["benchmark_10pb"].population == p6.BENCHMARK_POPULATION
    fx = p6.synthetic_market()[1]
    sim.simulate(market, [], fx, b2, authorize=_allow)
    sim.simulate_benchmark(market, fx, by_run["benchmark_5pb"], authorize=_allow)


@pytest.mark.parametrize("campo, valor", [
    ("system_sha256", "0" * 64),                       # (2)
    ("policy_id", "S2"),                               # (3)
    ("population", p6.POPULATION_ALL_BARS),            # (4)
    ("slippage_bps", 10.0),                            # (5)
    ("capital", 200_000.0),                            # (6)
    ("risk_pct", 1.0),                                 # (7)
    ("max_position_pct", 20.0),                        # (8)
    ("fee_rate", 0.0),                                 # (9)
    ("min_rr", 1.0),                                   # (10)
    ("max_hold_bars", 60),                             # (10)
    ("run_id", "B2_exploratoria"),
])
def test_c02_c10_un_solo_campo_distinto_se_rechaza(live: p6.ConfirmatoryToken, campo: str, valor: Any) -> None:
    """(2–10) Con autorización permisiva, p6_sim rechaza un spec que difiera en un solo campo."""

    market, _contract, by_run = _contract_market()
    bad = replace(by_run["B2_primaria_5pb"], **{campo: valor})
    with pytest.raises(sim.P6OutcomeGateError, match="no pre-registrado"):
        sim.simulate(market, [], EUR, bad, authorize=_allow)


def test_c11_c12_spec_y_benchmark_inventados(live: p6.ConfirmatoryToken) -> None:
    market, _contract, by_run = _contract_market()
    with pytest.raises(sim.P6OutcomeGateError, match="no pre-registrado"):
        sim.simulate(market, [], EUR, sim.SimSpec("B2", "0" * 64), authorize=_allow)
    for bad in (sim.SimSpec("benchmark", "0" * 64), replace(by_run["benchmark_5pb"], slippage_bps=20.0),
                replace(by_run["benchmark_5pb"], system_sha256=by_run["benchmark_10pb"].system_sha256)):
        with pytest.raises(sim.P6OutcomeGateError, match="no pre-registrado"):
            sim.simulate_benchmark(market, EUR, bad, authorize=_allow)


def test_c13_autorizacion_valida_no_basta_sin_contrato(live: p6.ConfirmatoryToken) -> None:
    """(13) Autorización que acepta todo + spec no registrado → rechazo; real sin contrato → rechazo."""

    market, _contract, _by_run = _contract_market()
    with pytest.raises(sim.P6OutcomeGateError, match="no pre-registrado"):
        sim.simulate(market, [], EUR, sim.SimSpec("C0", "1" * 64), authorize=_allow)
    with pytest.raises(sim.P6OutcomeGateError, match="sin contrato"):
        replace(market, contract=None)
    with pytest.raises(sim.P6OutcomeGateError):
        replace(market, contract=frozenset({"no es un SimSpec"}))  # type: ignore[arg-type]


def test_c14_spec_registrado_sin_autorizacion_vigente(live: p6.ConfirmatoryToken) -> None:
    """(14) Spec del contrato pero sin autorización, con un token no vigente o ya sin ejecución → rechazo."""

    market, _contract, by_run = _contract_market()
    spec = by_run["S2_primaria_5pb"]
    with pytest.raises(sim.P6OutcomeGateError, match="ConfirmatoryToken"):
        sim.simulate(market, [], EUR, spec)
    stale = p6.ConfirmatoryToken(p6.RUN_DIR / p6.RUN_MARKER, "0" * 64, "0" * 64)
    with pytest.raises(sim.P6OutcomeGateError):
        sim.simulate(market, [], EUR, spec, authorize=lambda _s: p6.require_token(stale))
    # Acabada la ejecución (token revocado), el motor rechaza incluso los datos ya construidos.
    p6._ACTIVE_TOKEN = None
    with pytest.raises(sim.P6OutcomeGateError):
        sim.simulate(market, [], EUR, spec, authorize=_allow)


def test_c15_sinteticos_sin_contrato_admiten_specs_libres() -> None:
    m, fx, signals = p6.synthetic_market()
    assert m.origin == sim.ORIGIN_SYNTHETIC and m.contract is None
    result = sim.simulate(m, signals, fx, sim.SimSpec("LIBRE", "x" * 64, risk_pct=3.0, max_hold_bars=7))
    assert result.snapshots


@pytest.mark.parametrize("fallo", ["write", "fsync", "distinto"])
def test_c16_c18_fallo_al_persistir_el_payload_no_crea_marca(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fallo: str
) -> None:
    """(16) fallo al persistir, (17) fallo de fsync, (18) payload persistido distinto → sin marca ni outcomes."""

    import os as os_module

    run_dir, config, ident, _ = _sealed_env(tmp_path, monkeypatch)
    if fallo == "write":
        real_open = open

        def broken_open(path: Any, mode: str = "r", *a: Any, **k: Any) -> Any:
            if str(path).endswith(".tmp") and "w" in mode:
                raise OSError("no se puede escribir (inyectado)")
            return real_open(path, mode, *a, **k)

        monkeypatch.setattr("builtins.open", broken_open)
    elif fallo == "fsync":
        def broken_fsync(_fd: int) -> None:
            raise OSError("fsync falló (inyectado)")

        monkeypatch.setattr(p6.os, "fsync", broken_fsync)
    else:
        real_replace = os_module.replace

        def corrupting_replace(src: Any, dst: Any) -> None:
            real_replace(src, dst)
            Path(dst).write_bytes(b"{}\n")

        monkeypatch.setattr(p6.os, "replace", corrupting_replace)
    with pytest.raises((OSError, p6.P6PreflightError)):
        _run(config, ident, run_dir)
    monkeypatch.undo()
    assert not (run_dir / p6.RUN_MARKER).exists()
    assert not (run_dir / p6.RUN_PAYLOAD).exists() and not (run_dir / f".{p6.RUN_PAYLOAD}.tmp").exists()
    assert not (run_dir / "p6-resultado.json").exists() and p6._ACTIVE_TOKEN is None


def test_c19_c20_marca_referencia_el_payload_ya_persistido(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(19) Al crear la marca el payload ya existe y su hash coincide; (20) segunda ejecución → rechazo."""

    run_dir, config, ident, _ = _sealed_env(tmp_path, monkeypatch)
    seen: Dict[str, Any] = {}
    real_open = p6.os.open

    def spy_open(path: Any, flags: int, *a: Any) -> int:
        if Path(path).name == p6.RUN_MARKER:
            persisted = run_dir / p6.RUN_PAYLOAD
            seen["payload_antes_de_la_marca"] = persisted.is_file()
            seen["sha"] = hashlib.sha256(persisted.read_bytes()).hexdigest() if persisted.is_file() else None
            seen["excl"] = bool(flags & os.O_EXCL) and bool(flags & os.O_CREAT)
        return real_open(path, flags, *a)

    import os

    monkeypatch.setattr(p6.os, "open", spy_open)
    code, text = _run(config, ident, run_dir)
    assert code == 0, text
    assert seen["payload_antes_de_la_marca"] and seen["excl"]
    marker = json.loads((run_dir / p6.RUN_MARKER).read_text(encoding="utf-8"))
    assert marker["payload_sha256"] == seen["sha"] == hashlib.sha256((run_dir / p6.RUN_PAYLOAD).read_bytes()).hexdigest()
    with pytest.raises(p6.P6AlreadyExecutedError):
        _run(config, ident, run_dir)



# ---------------------------------------------------------------------------
# P6 no expone ningún cargador de la cosecha completa fuera del flujo sellado.
# ---------------------------------------------------------------------------


def test_l01_l02_p6_no_expone_cargadores_de_la_cosecha_completa() -> None:
    """(1) sin load_full_vintage, (2) sin load_vintage, ni otro alias del cargador en el namespace de p6."""

    import advisor.research.vintage as vintage_module

    assert not hasattr(p6, "load_full_vintage") and not hasattr(p6, "load_vintage")
    assert all(value is not vintage_module.load_vintage for value in vars(p6).values())
    assert not hasattr(p6, "vintage") and not hasattr(p6, "vintage_module")


def _calls_to(name: str) -> List[Tuple[str, int]]:
    """Funciones de p6.py (con su línea) que llaman o importan ``name``."""

    import ast
    import inspect

    tree = ast.parse(inspect.getsource(p6))
    found: List[Tuple[str, int]] = []

    def visit(node: ast.AST, owner: str) -> None:
        for child in ast.iter_child_nodes(node):
            current = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else owner
            if isinstance(child, ast.Call):
                func = child.func
                called = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
                if called == name:
                    found.append((owner, child.lineno))
            if isinstance(child, ast.ImportFrom) and any(alias.name == name for alias in child.names):
                found.append((owner, child.lineno))
            visit(child, current)

    visit(tree, "<módulo>")
    return found


def test_l04_solo_el_flujo_sellado_alcanza_el_cargador_completo() -> None:
    """(4) Las únicas apariciones de load_vintage en p6 están dentro de _ejecutar_confirmatoria_sellada."""

    owners = {owner for owner, _line in _calls_to("load_vintage")}
    assert owners == {"_ejecutar_confirmatoria_sellada"}, _calls_to("load_vintage")
    # Y a esa función solo se llega desde run_confirmatory.
    assert {owner for owner, _ in _calls_to("_ejecutar_confirmatoria_sellada")} == {"run_confirmatory"}


def test_l03_l04_flujo_carga_la_cosecha_tras_verificar_y_el_preflight_nunca(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(3) el preflight no carga la cosecha; (4) run_confirmatory la carga una vez, tras la autorización."""

    import advisor.research.vintage as vintage_module

    run_dir, config, ident, _ = _sealed_env(tmp_path, monkeypatch)
    events: List[str] = []
    real_auth = p6._verified_authorization

    def spy_auth() -> Any:
        events.append("autorizacion")
        return real_auth()

    def spy_load(*_a: Any, **_k: Any) -> Any:
        events.append("cosecha_completa")
        assert not (run_dir / p6.RUN_MARKER).exists(), "la cosecha se carga antes de la marca"
        return p6.VintageLoad("sintetica", {}, {})

    monkeypatch.setattr(p6, "_verified_authorization", spy_auth)
    monkeypatch.setattr(vintage_module, "load_vintage", spy_load)
    code, text = _run(config, ident, run_dir)
    assert code == 0, text
    assert events == ["autorizacion", "cosecha_completa"]

    # Si la autorización falla, el cargador completo no se toca.
    events.clear()
    (p6.PREFLIGHT_DIR / "p6-preflight.json").unlink()
    with pytest.raises((sim.P6OutcomeGateError, p6.P6AlreadyExecutedError)):
        _run(config, ident, tmp_path / "run")
    assert "cosecha_completa" not in events


def test_l05_sin_apertura_sellada_no_hay_marketdata_real() -> None:
    """(5) Sin ejecución sellada en curso no se construye MarketData real, ni con el contrato de verdad."""

    config = load_config("config.yaml")
    m, _fx, _signals = p6.synthetic_market()
    days = sim.snapshot_days(m)
    window = p6.Window(m.window_start, m.window_end, m.window_start, m.window_start, 0, len(days), 252.0)
    contract = p6._preregistered_specs(config, p6.system_hashes(config, window))
    assert p6._ACTIVE_TOKEN is None
    with pytest.raises(sim.P6OutcomeGateError):
        replace(m, origin=sim.ORIGIN_REAL, contract=contract)



# ---------------------------------------------------------------------------
# Invariante del namespace de P6: ningún lector de precios ni cargador completo.
# ---------------------------------------------------------------------------


def _price_readers() -> Dict[str, Any]:
    import advisor.research.vintage as vintage_module

    return {name: getattr(vintage_module, name) for name in (
        "load_vintage", "load_price_rows", "frozen_close", "read_raw_csv", "build_views", "freeze_vintage",
    )}


# Política del namespace de p6: cada callable importado de otro módulo de advisor está clasificado a mano.
# Un callable nuevo hace fallar el test hasta que se incorpore conscientemente. Los de procesamiento operan
# sobre datos que les entrega el llamador; ninguno lee la cosecha ni extrae precios de un VintageLoad.
P6_IMPORTED_CALLABLES = {
    "advisor.analysis.benchmark": {"resolve_benchmark_symbol"},
    "advisor.analysis.levels": {"compute_levels"},
    "advisor.analysis.snapshot": {"build_snapshot_series", "snapshot_from_series"},
    "advisor.backtest.engine": {"_signal"},
    "advisor.config": {"AdvisorConfig"},
    "advisor.context.point_in_time": {"PointInTimeContextResolver", "analysis_timestamp_for_signal"},
    "advisor.data.calendars": {"exchange_calendar", "expected_sessions"},
    "advisor.data.freshness": {"mercado_para_simbolo"},
    "advisor.data.sessions": {"market_for_symbol", "market_session", "session_close_at"},
    "advisor.research.observations": {"stable_signal_id"},
    "advisor.research.p3": {"utc_now", "write_json"},
    # De P4 solo los helpers de git/árbol; nunca _context_resolver ni otro acceso a datos.
    "advisor.research.p4": {"executor_unchanged_since", "tree_dirty"},
    "advisor.run.git": {"git_sha", "run_git"},
    "advisor.research.p6_sim": {
        "AssetSeries", "FxTable", "MarketData", "P6OutcomeGateError", "Signal", "SimSpec", "canonical_json",
        "cash_occupancy", "criterion", "equity_series", "excess", "exposure_metrics", "ledger_csv", "path_metrics",
        "series_csv", "simulate", "simulate_benchmark", "subperiods", "survivors", "trade_metrics", "trades_csv",
        "turnover",
    },
    # De vintage solo tipos y la carga estructural (timestamps, dividendos, splits).
    "advisor.research.vintage": {"VintageLoad", "VintageStructure", "load_vintage_structure"},
    "advisor.run.manifest": {"config_hash"},
    "advisor.universe.models": {"Universe"},
}

# Funciones propias de p6 autorizadas a tocar precios o la estructura de la cosecha.
P6_OWN_PRICE_PATHS = {
    "_ejecutar_confirmatoria_sellada",   # flujo confirmatorio sellado
    "build_real_market",                 # exige token vigente
    "build_real_signals",                # exige token vigente
    "dividend_split_checks",             # §10.1, sin argumentos del llamador
    "_dividend_split_checks",            # cálculo de §10.1; el lector lo aporta quien llama
    "structure_index",                   # solo timestamps
    "vintage_index",                     # solo timestamps
}


def _p6_imported_callables() -> Dict[str, set]:
    out: Dict[str, set] = {}
    for name, value in vars(p6).items():
        module = getattr(value, "__module__", None)
        if callable(value) and module and module.startswith("advisor.") and module != p6.__name__:
            out.setdefault(module, set()).add(name)
    return out


def test_n01_n04_namespace_de_p6_sin_lectores_de_precios() -> None:
    """(1–4) Ningún lector de precios ni extractor desde VintageLoad en p6, con ningún nombre.

    Política cerrada: los callables importados de otros módulos de advisor deben coincidir exactamente con
    P6_IMPORTED_CALLABLES, y no se reexporta ningún módulo de advisor.
    """

    import types

    for name in ("load_vintage", "load_full_vintage", "load_price_rows", "frozen_close", "_context_resolver"):
        assert not hasattr(p6, name), name
    readers = _price_readers()
    import advisor.research.p4 as p4_module

    readers["_context_resolver"] = p4_module._context_resolver
    exposed = [name for name, value in vars(p6).items() if any(value is reader for reader in readers.values())]
    assert exposed == [], exposed
    assert _p6_imported_callables() == P6_IMPORTED_CALLABLES
    advisor_modules = [name for name, value in vars(p6).items()
                       if isinstance(value, types.ModuleType) and value.__name__.startswith("advisor.")]
    assert advisor_modules == [], advisor_modules


def test_n10_solo_las_rutas_autorizadas_de_p6_tocan_precios() -> None:
    """Toda función propia de p6 que toca la cosecha o accesores de precios está en la lista autorizada."""

    import inspect
    import re

    pattern = re.compile(r"\.by_symbol|frozen_close|signal_prices|execution_prices|\bload_vintage\(|load_price_rows"
                         r"|read_raw_csv|_context_resolver|build_views")
    touching = set()
    for name, value in vars(p6).items():
        if inspect.isfunction(value) and value.__module__ == p6.__name__ and pattern.search(inspect.getsource(value)):
            touching.add(name)
    assert touching == P6_OWN_PRICE_PATHS, touching ^ P6_OWN_PRICE_PATHS


def test_n05_load_structure_es_solo_estructural(tmp_path: Path) -> None:
    """(5) La carga estructural devuelve solo timestamps, dividendos y splits."""

    from advisor.research.vintage import VintageStructure, load_vintage_structure

    assert p6.load_structure.__code__.co_names.count("load_vintage_structure") == 1
    import inspect

    assert inspect.signature(load_vintage_structure).return_annotation in (VintageStructure, "VintageStructure")
    if not (Path("data/vintages") / p6.DATA_VINTAGE_ID / "AAPL.csv").is_file():
        pytest.skip("data/vintages no está disponible")
    structure = p6.load_structure()
    assert {tuple(frame.columns) for frame in structure.by_symbol.values()} == {("Dividends", "Stock Splits")}


def test_n06_seccion_10_1_lee_solo_filas_y_columnas_minimas(monkeypatch: pytest.MonkeyPatch) -> None:
    """(6) §10.1 pide solo Close/Adj Close de la víspera y la fecha ex, calculadas por la función."""

    import inspect

    assert list(inspect.signature(p6.dividend_split_checks).parameters) == []
    monkeypatch.setattr(p6, "asset_list", lambda: ["R6C0.DE", "SPL"])
    monkeypatch.setattr(p6, "DIVIDEND_SPLIT_ASSETS", 1)
    monkeypatch.setattr(p6, "XETRA_FX_SUSPECTS", ())
    structure, rows = _structure_with_dividends(1.0)
    asked: List[Tuple[str, Tuple[str, ...], Tuple[str, ...]]] = []

    def spy(vid: str, symbol: str, stamps: Sequence[str], columns: Sequence[str]) -> pd.DataFrame:
        asked.append((symbol, tuple(stamps), tuple(columns)))
        return rows(vid, symbol, stamps, columns)

    p6._dividend_split_checks(structure, spy)
    assert asked == [("SPL", ("2024-01-01", "2024-01-02", "2024-01-04", "2024-01-05"), ("Close", "Adj Close"))]


def test_n09_constructores_reales_exigen_token_vigente() -> None:
    """(9) build_real_market y build_real_signals rechazan sin token, con token fabricado o no vigente."""

    config = load_config("config.yaml")
    m, _fx, _signals = p6.synthetic_market()
    window = p6.Window(m.window_start, m.window_end, m.window_start, m.window_start, 0, 10, 252.0)
    fake = p6.ConfirmatoryToken(p6.RUN_DIR / p6.RUN_MARKER, "0" * 64, "0" * 64)
    for token in (None, fake):
        with pytest.raises(sim.P6OutcomeGateError):
            p6.build_real_market(token, config, None, None, window, {}, frozenset())  # type: ignore[arg-type]
        with pytest.raises(sim.P6OutcomeGateError):
            p6.build_real_signals(token, config, None, None, "B2", p6.POPULATION_OPERAR, window)  # type: ignore[arg-type]
