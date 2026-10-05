from __future__ import annotations

import ast
import hashlib
import json
import math
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

import pandas as pd
import pytest

import advisor.research.p6_sim as p6_sim
from advisor.research import t024_captura as cap
from advisor.research import t024_decision as dec
from advisor.research.t024_comun import CUTOFF_CONSUMIDA, SenalT024
from advisor.research.vintage import VintageLoad, VintageViews

UTC = timezone.utc


def days(start: date, n: int) -> list[date]:
    out: list[date] = []
    current = start
    while len(out) < n:
        if current.weekday() < 5:
            out.append(current)
        current += timedelta(days=1)
    return out


def bars(n: int, price: float = 100.0, *, start: date = date(2026, 8, 28)) -> list[dec.BarraDecision]:
    return [dec.BarraDecision(d, price, price, price, price) for d in days(start, n)]


def senal(
    *,
    policy: str = "B2",
    asset: str = "AAA",
    s_index: int = 0,
    stop: float = 95.0,
    target: float = 110.0,
    entry_max: float = 200.0,
    start: date = date(2026, 8, 28),
    sid: str = "s1",
) -> SenalT024:
    ds = days(start, s_index + 2)
    return SenalT024(
        sid,
        policy,
        asset,
        s_index,
        ds[s_index],
        ds[s_index + 1],
        datetime.combine(ds[s_index], time(17, 0), UTC),
        stop,
        target,
        entry_max,
    )


def test_d1_sin_dividendo_formula_manual() -> None:
    sigma, fee = 0.0005, 0.001
    expected = math.log((1 - sigma) * (1 - fee)) - math.log((1 + sigma) * (1 + fee))
    assert dec.d1_cerrada(100, 110, 0) == pytest.approx(expected)


def test_d1_con_dividendo_formula_manual() -> None:
    sigma, fee = 0.0005, 0.001
    expected = math.log((110 * (1 - sigma) * (1 - fee) + 2) / 112) - math.log((1 + sigma) * (1 + fee))
    assert dec.d1_cerrada(100, 110, 2) == pytest.approx(expected)


def test_d1_slippage_separado() -> None:
    assert dec.d1_cerrada(100, 110, 0, fee=0, slip_bps=5) == pytest.approx(math.log(0.9995) - math.log(1.0005))


def test_d1_comision_separada() -> None:
    assert dec.d1_cerrada(100, 110, 0, fee=0.001, slip_bps=0) == pytest.approx(math.log(0.999) - math.log(1.001))


def test_d2_cero_si_ventana_rinde_el_drift_con_costes_incluidos() -> None:
    rows = bars(80)
    mu = math.log(1.002)
    e, x, h = 1, 5, 5
    sigma, fee = 0.0005, 0.001
    exit_price = math.exp(h * mu) * rows[e].open * (1 + sigma) * (1 + fee) / ((1 - sigma) * (1 - fee))
    rows = [replace(row, close=100 * (1.002**i)) for i, row in enumerate(rows)]
    v = dec.calcular_ventana(senal(target=10_000), rows, x, dec.EXIT_FINAL, exit_price, 0, t0=rows[1].session, t1=rows[-1].session, truncada_t1=False)
    assert v.d2 == pytest.approx(0.0, abs=1e-12)


def test_convencion_b_noche_dia_manual() -> None:
    rows: list[dec.BarraDecision] = []
    price = 100.0
    for d in days(date(2026, 8, 28), 80):
        rows.append(dec.BarraDecision(d, price * 1.001, price * 1.003, price, price * 1.003))
        price *= 1.003
    s = senal(target=10_000, stop=1)
    v = dec.calcular_ventana(s, rows, 4, dec.EXIT_FINAL, rows[4].close, 0, t0=rows[1].session, t1=rows[-1].session, truncada_t1=False)
    mu_noche, mu_dia = dec.drift_noche_dia(rows[1:])
    expected = v.l_i - ((v.x_index - v.e_index) * mu_noche + (v.x_index - v.e_index + 1) * mu_dia)
    assert v.d2_b == pytest.approx(expected)


@pytest.mark.parametrize(("rows", "reason", "price"), [([100, 100, 90], dec.EXIT_STOP, 90), ([100, 100, 112], dec.EXIT_TARGET, 112)])
def test_salida_por_gap_en_apertura(rows: list[int], reason: str, price: float) -> None:
    ds = days(date(2026, 8, 28), 3)
    data = [dec.BarraDecision(d, o, max(o, 100), min(o, 100), o) for d, o in zip(ds, rows)]
    assert dec.salida_p6(senal(), data)[:3] == (2, reason, price)


def test_salida_stop_intradia() -> None:
    rows = [dec.BarraDecision(d, 100, 101, 94 if i == 1 else 99, 100) for i, d in enumerate(days(date(2026, 8, 28), 3))]
    assert dec.salida_p6(senal(), rows)[:3] == (1, dec.EXIT_STOP, 95)


def test_salida_objetivo_intradia() -> None:
    rows = [dec.BarraDecision(d, 100, 111 if i == 1 else 101, 99, 100) for i, d in enumerate(days(date(2026, 8, 28), 3))]
    assert dec.salida_p6(senal(), rows)[:3] == (1, dec.EXIT_TARGET, 110)


def test_salida_por_tiempo() -> None:
    assert dec.salida_p6(senal(target=200), bars(45))[:3] == (41, dec.EXIT_TIME, 100)


def test_salida_final_truncada() -> None:
    assert dec.salida_p6(senal(target=200), bars(4))[:3] == (3, dec.EXIT_FINAL, 100)


def test_dividendo_en_exdate_con_salida_en_apertura() -> None:
    rows = bars(4)
    rows[2] = replace(rows[2], open=90, high=91, low=89, close=90, dividend=2)
    assert dec.salida_p6(senal(), rows)[:4] == (2, dec.EXIT_STOP, 90, 2)


def test_split_vista_de_ejecucion_equivalente_en_escala_ajustada() -> None:
    rows = bars(5, 50)
    assert dec.salida_p6(senal(stop=45, target=55, entry_max=80), rows)[:3] == (4, dec.EXIT_FINAL, 50)


def test_phi_y_d2o_son_por_politica_activo_con_dos_ventanas() -> None:
    rows = bars(90)
    first = dec.calcular_ventana(senal(sid="a", target=200), rows, 3, dec.EXIT_FINAL, 100, 0, t0=rows[1].session, t1=rows[-1].session, truncada_t1=False)
    second = dec.calcular_ventana(senal(sid="b", s_index=45, target=200), rows, 48, dec.EXIT_FINAL, 100, 0, t0=rows[1].session, t1=rows[-1].session, truncada_t1=False)
    result = dec.recalcular_por_politica_activo([first, second], {"AAA": rows})
    assert result.ventanas[0].phi_a == pytest.approx(6 / 90)
    assert result.ventanas[0].d2o is not None and result.ventanas[1].d2o is not None


def test_atenuacion_uno_menos_phi_en_caso_construido() -> None:
    rows = bars(80)
    v = dec.calcular_ventana(senal(target=200), rows, 10, dec.EXIT_FINAL, 100, 0, t0=rows[1].session, t1=rows[-1].session, truncada_t1=False)
    result = dec.recalcular_por_politica_activo([v], {"AAA": rows})
    assert result.ventanas[0].phi_a == pytest.approx(10 / 80)


def test_exclusiones_por_sesiones_insuficientes_se_cuentan() -> None:
    rows = bars(10)
    v = dec.calcular_ventana(senal(target=200), rows, 3, dec.EXIT_FINAL, 100, 0, t0=rows[1].session, t1=rows[-1].session, truncada_t1=True)
    result = dec.recalcular_por_politica_activo([v], {"AAA": rows})
    assert result.ventanas_excluidas_d2 == 1
    assert result.activos_excluidos_d2 == 1


def test_no_solapamiento_por_activo() -> None:
    rows = bars(90)
    result = dec.construir_ventanas([senal(sid="a", target=200), senal(sid="b", s_index=2, target=200)], {"AAA": rows}, c_e=date(2027, 8, 27))
    assert len(result.ventanas) == 1
    assert result.ignoradas_no_solapamiento == 1


def test_elegibilidad_temporal_y_frontera_t1() -> None:
    rows = bars(90)
    old = SenalT024("old", "B2", "AAA", 0, CUTOFF_CONSUMIDA, date(2026, 8, 28), datetime(2026, 8, 27, tzinfo=UTC), 95, 200, 300)
    ok = senal(sid="ok", target=200)
    result = dec.construir_ventanas([old, ok], {"AAA": rows}, c_e=rows[1].session, t1_por_activo={"AAA": rows[3].session})
    assert [v.senal.signal_id for v in result.ventanas] == ["ok"]
    assert result.ventanas[0].x_index == 3
    assert result.ventanas[0].exit_reason == dec.EXIT_FINAL


def test_d3_indice_por_fecha_con_calendarios_distintos() -> None:
    a = [dec.BarraDecision(d, 100, 100, 100, 100 + i) for i, d in enumerate(days(date(2026, 8, 28), 5))]
    b = [dec.BarraDecision(d, 200, 200, 200, 200 + 2 * i) for i, d in enumerate(days(date(2026, 8, 31), 4))]
    idx = dec.indice_equiponderado_region({"A": a, "B": b})
    v = dec.calcular_ventana(senal(asset="A", target=200), a, 3, dec.EXIT_FINAL, 103, 0, t0=a[1].session, t1=a[-1].session, truncada_t1=False)
    expected = v.l_i - math.log(idx[a[3].session] / idx[a[0].session])
    assert dec.d3_region(v, a, idx) == pytest.approx(expected)


def test_d4_trunca_en_t1() -> None:
    rows = bars(80)
    v = dec.calcular_ventana(senal(target=200), rows, 3, dec.EXIT_FINAL, 100, 0, t0=rows[1].session, t1=rows[-1].session, truncada_t1=False)
    assert dec.d4_40_sesiones(v, rows, t1=rows[10].session)[1] is True


def test_construir_resultado_end_to_end_sintetico_con_d3_d4(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rows_a = [cap.BarraCiega(d, 100, 101, 99, 100) for d in days(date(2026, 8, 28), 90)]
    rows_b = [cap.BarraCiega(d, 200, 202, 198, 200) for d in days(date(2026, 8, 28), 90)]
    vintage = _vintage_multi({"AAA": rows_a, "BBB": rows_b})
    universe = _RegionalUniverse({"AAA": "USA", "BBB": "EUROPA"})
    token = _activar_token(tmp_path, monkeypatch)

    def fixed_signals(**kwargs: Any) -> tuple[list[SenalT024], dict[str, int]]:
        policy = kwargs["policy"]
        if policy == "B2":
            return [senal(policy="B2", asset="AAA", s_index=1, stop=90, target=200, entry_max=200, sid="b2")], {}
        if policy == "C0":
            return [senal(policy="C0", asset="BBB", s_index=3, stop=180, target=400, entry_max=400, sid="c0")], {}
        return [], {}

    monkeypatch.setattr(cap, "generar_senales_operar", fixed_signals)
    result = dec.construir_resultado(token, None, universe, vintage, c_e=date(2027, 8, 27), policies=["B2"])  # type: ignore[arg-type]
    sigma = 0.0005
    expected_l = math.log((100 * (1 - sigma) * (1 - 0.001)) / (100 * (1 + sigma) * (1 + 0.001)))
    assert result.politicas["B2"].n == 1
    assert result.politicas["B2"].etiqueta == dec.NO_EVALUABLE
    assert result.descriptivas["d2_media_por_politica"]["B2"] == pytest.approx(expected_l)  # type: ignore[index]
    assert result.descriptivas["d3_media"] is not None
    assert result.descriptivas["d4_media"] is not None
    assert result.descriptivas["d4_truncadas"] == 0


def test_coste_prorrateado_exacto() -> None:
    assert dec.coste_roundtrip() == pytest.approx(math.log(1.0005 * 1.001) - math.log(0.9995 * 0.999))


def test_captura_vista_ciega_bloquea_high_low_close_de_ei_y_futuro() -> None:
    s = senal()
    rows = [cap.BarraCiega(d, 100, 500, 1, 200) for d in days(date(2026, 8, 28), 5)]
    view = cap.VistaCiega(rows, s)
    assert view.open_e() == 100
    with pytest.raises(cap.T024LookaheadError):
        view.get(1, "high")
    with pytest.raises(cap.T024LookaheadError):
        view.get(2, "open")


def test_captura_invariante_al_prefijo_adversarial() -> None:
    s = senal()
    rows = [cap.BarraCiega(d, 100, 101, 99, 100) for d in days(date(2026, 8, 28), 6)]

    def poison(seq: Sequence[cap.BarraCiega]) -> Sequence[cap.BarraCiega]:
        out = list(seq)
        out[2:] = [cap.BarraCiega(r.session, math.nan, -1e9, 1e9, math.nan) for r in out[2:]]
        return out

    assert cap.verificar_invariante_prefijo(s, rows, poison)


def _vintage_from_rows(symbol: str, rows: Sequence[cap.BarraCiega]) -> VintageLoad:
    idx = pd.DatetimeIndex([pd.Timestamp(r.session, tz="UTC") for r in rows])
    frame = pd.DataFrame(
        {
            "Open": [r.open for r in rows],
            "High": [r.high for r in rows],
            "Low": [r.low for r in rows],
            "Close": [r.close for r in rows],
            "Volume": [r.volume for r in rows],
            "Dividends": [0.0 for _ in rows],
            "Stock Splits": [0.0 for _ in rows],
        },
        index=idx,
    )
    views = VintageViews(raw=frame, execution_prices=frame, signal_prices=frame, gap_for_catalyst=frame)
    return VintageLoad("dev", {}, {symbol: views})


def _vintage_multi(data: Mapping[str, Sequence[cap.BarraCiega]]) -> VintageLoad:
    by_symbol: dict[str, VintageViews] = {}
    for symbol, rows in data.items():
        by_symbol.update(_vintage_from_rows(symbol, rows).by_symbol)
    return VintageLoad("synthetic", {}, by_symbol)


class _Asset:
    timezone = "UTC"
    region = "USA"


class _Universe:
    def get(self, _symbol: str) -> _Asset:
        return _Asset()


class _RegionalUniverse:
    def __init__(self, regiones: dict[str, str]) -> None:
        self._regiones = regiones

    def get(self, symbol: str) -> _Asset:
        asset = _Asset()
        asset.region = self._regiones.get(symbol, "USA")  # type: ignore[misc]
        return asset


def _activar_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contenido: str = "marca") -> dec.TokenMirada:
    marca = tmp_path / "mirada_1.t024.consumida"
    marca.write_text(contenido, encoding="utf-8")
    token = dec.TokenMirada(marca, hashlib.sha256(marca.read_bytes()).hexdigest(), "nonce")
    monkeypatch.setattr(dec, "_TOKEN_ACTIVO", token)
    return token


def test_capturar_usa_vista_ciega_para_aperturas(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [cap.BarraCiega(d, 100, 999, 1, 999) for d in days(date(2026, 8, 28), 4)]
    s = senal(asset="AAA")
    monkeypatch.setattr(cap, "asset_list", lambda: ["AAA"])
    monkeypatch.setattr(cap, "generar_senales_operar", lambda **_kw: ([s], {"senales": 1}))
    result = cap.capturar(None, _Universe(), _vintage_from_rows("AAA", rows), c_e=date(2026, 12, 31))  # type: ignore[arg-type]
    assert result.conteos["B2"].ejecutables == 3


def test_k1_desarrollo_rotulo_y_cutoff_ficticio(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [cap.BarraCiega(d, 100, 101, 99, 100) for d in days(date(2026, 1, 1), 4)]
    vintage = _vintage_from_rows("AAA", rows)
    monkeypatch.setattr(cap, "asset_list", lambda: ["AAA"])
    monkeypatch.setattr(cap, "generar_senales_operar", lambda **_kw: ([], {}))
    result = cap.capturar(None, _Universe(), vintage, c_e=date(2026, 6, 30), cutoff=date(2026, 3, 31), desarrollo=True)  # type: ignore[arg-type]
    assert result.rotulo == "DESARROLLO — no decide"


def test_k1_no_desarrollo_rechaza_cutoff_ficticio_y_cosecha_consumida(monkeypatch: pytest.MonkeyPatch) -> None:
    vintage = replace(_vintage_from_rows("AAA", []), data_vintage_id=cap.DEV_VINTAGE_ID)
    monkeypatch.setattr(cap, "asset_list", lambda: ["AAA"])
    with pytest.raises(ValueError):
        cap.capturar(None, _Universe(), vintage, c_e=date(2026, 6, 30), cutoff=date(2026, 3, 31), desarrollo=False)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        cap.capturar(None, _Universe(), vintage, c_e=date(2026, 6, 30), desarrollo=False)  # type: ignore[arg-type]


def test_reconfirmacion_ciega_llama_capturar(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fake(*_args: Any, **_kwargs: Any) -> cap.ResultadoCaptura:
        nonlocal called
        called = True
        return cap.ResultadoCaptura({"B2": cap.ConteoCaptura("B2", 0, 0, {}, 0, 0)}, {})

    monkeypatch.setattr(cap, "capturar", fake)
    cap.reconfirmar_capacidad(None, _Universe(), _vintage_from_rows("AAA", []), c_e=date(2026, 12, 31))  # type: ignore[arg-type]
    assert called


def test_ejecutabilidad_motivos_equivalen_a_p6() -> None:
    cases = [
        (math.nan, p6_sim.DATA_NOT_EXECUTABLE, senal()),
        (100, p6_sim.INVALID_STOP, senal(stop=101)),
        (100, p6_sim.INVALID_TARGET, senal(target=99)),
        (100, p6_sim.ABOVE_MAX_ENTRY, senal(entry_max=99)),
        (100, p6_sim.RR_TOO_LOW, senal(stop=99, target=101, entry_max=200)),
        (100, p6_sim.ENTRY_OK, senal()),
    ]
    for apertura, reason, s in cases:
        assert cap.evaluar_ejecutabilidad(s, apertura).reason == reason


@pytest.mark.parametrize(
    ("bad", "motivo"),
    [
        (senal(entry_max=90), p6_sim.ABOVE_MAX_ENTRY),
        (senal(stop=101), p6_sim.INVALID_STOP),
        (senal(target=99), p6_sim.INVALID_TARGET),
        (senal(stop=99, target=101, entry_max=200), p6_sim.RR_TOO_LOW),
        (senal(sid="nan"), p6_sim.DATA_NOT_EXECUTABLE),
    ],
)
def test_construir_ventanas_rechaza_senales_no_ejecutables(bad: SenalT024, motivo: str) -> None:
    rows = bars(90)
    if bad.signal_id == "nan":
        rows[1] = replace(rows[1], open=math.nan)
    result = dec.construir_ventanas([bad], {"AAA": rows}, c_e=date(2027, 8, 27))
    assert result.ventanas == ()
    assert result.rechazos_ejecutabilidad == {motivo: 1}


def test_senal_no_ejecutable_no_bloquea_posterior_mismo_activo() -> None:
    rows = bars(90)
    bad = senal(sid="bad", entry_max=90, target=200)
    good = senal(sid="good", s_index=2, target=200)
    result = dec.construir_ventanas([bad, good], {"AAA": rows}, c_e=date(2027, 8, 27))
    assert [v.senal.signal_id for v in result.ventanas] == ["good"]
    assert result.rechazos_ejecutabilidad == {p6_sim.ABOVE_MAX_ENTRY: 1}


@pytest.mark.parametrize(
    ("rows", "stop", "target", "expected_reason"),
    [
        ([(100, 101, 99, 100), (100, 101, 99, 100), (90, 91, 89, 90)], 95, 200, p6_sim.EXIT_STOP),
        ([(100, 101, 99, 100), (100, 101, 99, 100), (120, 121, 119, 120)], 95, 110, p6_sim.EXIT_TARGET),
        ([(100, 101, 99, 100), (100, 101, 99, 100), (100, 101, 94, 100)], 95, 200, p6_sim.EXIT_STOP),
        ([(100, 101, 99, 100), (100, 101, 99, 100), (100, 111, 99, 100)], 95, 110, p6_sim.EXIT_TARGET),
        ([(100, 101, 99, 100)] * 45, 95, 200, p6_sim.EXIT_TIME),
        ([(100, 101, 99, 100)] * 4, 95, 200, p6_sim.EXIT_FINAL),
    ],
)
def test_salidas_equivalen_a_p6_sim(rows: list[tuple[int, int, int, int]], stop: float, target: float, expected_reason: str) -> None:
    from tests.test_p6 import EUR, asset, market, signal, spec

    a = asset("AAA", rows)
    p6_result = p6_sim.simulate(market(a), [signal(a, 0, stop, target)], EUR, spec())
    dec_rows = [dec.BarraDecision(d, o, h, lo, c, div) for d, o, h, lo, c, div in zip(a.session_dates, a.open, a.high, a.low, a.close, a.dividends)]
    x, reason, price, _div, _trunc = dec.salida_p6(senal(asset="AAA", stop=stop, target=target), dec_rows)
    trade = p6_result.trades[0]
    assert reason == expected_reason == trade.exit_reason
    assert x - 1 == trade.bars_held
    assert price == pytest.approx(trade.exit_eff)


def test_p6_sim_equivale_con_no_ejecutable_seguida_de_ejecutable() -> None:
    from tests.test_p6 import EUR, asset, market, signal, spec

    a = asset("AAA", [(100, 101, 99, 100)] * 50)
    signals = [signal(a, 0, 95, 200, entry_max=90, sid="bad"), signal(a, 2, 95, 200, entry_max=200, sid="good")]
    p6_result = p6_sim.simulate(market(a), signals, EUR, spec(max_hold_bars=40))
    dec_rows = [dec.BarraDecision(d, 100, 101, 99, 100) for d in days(date(2026, 8, 28), 50)]
    ours = dec.construir_ventanas(
        [senal(asset="AAA", s_index=0, entry_max=90, sid="bad", target=200), senal(asset="AAA", s_index=2, entry_max=200, sid="good", target=200)],
        {"AAA": dec_rows},
        c_e=date(2027, 8, 27),
    )
    assert [trade.signal_id for trade in p6_result.trades] == ["good"]
    assert [v.senal.signal_id for v in ours.ventanas] == ["good"]
    assert ours.ventanas[0].x_index - ours.ventanas[0].e_index == p6_result.trades[0].bars_held
    assert ours.ventanas[0].exit_price == pytest.approx(p6_result.trades[0].exit_eff)


def test_bootstrap_10_semanas_determinista_con_vacias() -> None:
    vals = [(date.fromisocalendar(2027, 1, 1), 1.0), (date.fromisocalendar(2027, 12, 1), 3.0)]
    a = dec.bootstrap_semanal(vals, b=50, seed=123)
    b = dec.bootstrap_semanal(vals, b=50, seed=123)
    assert a.draws == b.draws
    assert len(dec.semanas_consecutivas((2027, 1), (2027, 12))) == 12


def test_ic_bonferroni_delta_cuatro_estados() -> None:
    assert dec.etiquetar(0.1, 0.2, n=100) == dec.POSITIVO
    assert dec.etiquetar(-0.2, 0.0, n=100) == dec.NO_POSITIVO
    assert dec.etiquetar(-0.1, 0.1, n=100) == dec.NO_CONCLUYENTE
    assert dec.etiquetar(0.1, 0.2, n=99) == dec.NO_EVALUABLE


def _registro_forward(tmp_path: Path, ids: list[str], checkpoints: Optional[list[date]] = None) -> Path:
    fechas = checkpoints or [date(2027, 4, 1) + timedelta(days=i) for i in range(len(ids))]
    entries = [{"data_vintage_id": item, "checkpoint": fecha.isoformat()} for item, fecha in zip(ids, fechas)]
    digest = hashlib.sha256(json.dumps({"cosechas": entries}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    path = tmp_path / "forward.json"
    path.write_text(json.dumps({"cosechas": entries, "sha256": digest}), encoding="utf-8")
    return path


def _conteo(policy: str, cumple: bool) -> cap.ConteoCaptura:
    return cap.ConteoCaptura(policy, 130, 130, {}, 130, 30, cumple=cumple)


def test_verificar_identidad_ramas_no_tautologicas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dec, "cargar_t024_code_sha", lambda _repo=".": "c" * 40)
    monkeypatch.setattr(dec, "executor_unchanged_since", lambda *_a, **_k: True)
    monkeypatch.setattr(dec, "tree_dirty", lambda *_a, **_k: False)
    monkeypatch.setattr(dec, "_git", lambda *_a, **_k: None)
    with pytest.raises(dec.T024DecisionError, match=r"PREREG.*ancestro"):
        dec.verificar_identidad()
    monkeypatch.setattr(dec, "_git", lambda args, _repo: args[2] == dec.comun.T024_PREREG_SHA)
    with pytest.raises(dec.T024DecisionError, match="CODE_SHA no es ancestro"):
        dec.verificar_identidad()
    monkeypatch.setattr(dec, "_git", lambda *_a, **_k: True)
    monkeypatch.setattr(dec, "executor_unchanged_since", lambda *_a, **_k: False)
    with pytest.raises(dec.T024DecisionError, match="ejecutor"):
        dec.verificar_identidad()
    monkeypatch.setattr(dec, "executor_unchanged_since", lambda *_a, **_k: True)
    monkeypatch.setattr(dec, "tree_dirty", lambda *_a, **_k: True)
    with pytest.raises(dec.T024DecisionError, match="limpio"):
        dec.verificar_identidad()
    monkeypatch.setattr(dec, "tree_dirty", lambda *_a, **_k: None)
    with pytest.raises(dec.T024DecisionError, match="limpio"):
        dec.verificar_identidad()
    monkeypatch.setattr(dec, "tree_dirty", lambda *_a, **_k: False)
    assert dec.verificar_identidad() == "c" * 40


# --- Mecanismo real del lock de T024_CODE_SHA, en un repositorio git temporal (sin monkeypatch del SHA) ---


def _git_tmp(repo: Path, *args: str) -> str:
    import subprocess

    out = subprocess.run(
        ["git", "-c", "user.name=t024", "-c", "user.email=t024@example.invalid", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def _repo_t024(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str, str]:
    """Repo con P (pre-registro) y A (ejecutor). Devuelve (repo, sha_P, sha_A)."""

    repo = tmp_path / "repo"
    (repo / "advisor" / "research").mkdir(parents=True)
    _git_tmp(repo, "init", "-q", "-b", "main")
    (repo / "docs").mkdir()
    (repo / "docs" / "prereg.md").write_text("pre-registro\n", encoding="utf-8")
    _git_tmp(repo, "add", "-A")
    _git_tmp(repo, "commit", "-q", "-m", "P")
    sha_p = _git_tmp(repo, "rev-parse", "HEAD")
    (repo / "advisor" / "research" / "ejecutor.py").write_text("X = 1\n", encoding="utf-8")
    (repo / "config.yaml").write_text("a: 1\n", encoding="utf-8")
    _git_tmp(repo, "add", "-A")
    _git_tmp(repo, "commit", "-q", "-m", "A")
    sha_a = _git_tmp(repo, "rev-parse", "HEAD")
    # Solo el pre-registro del repo temporal sustituye al real; T024_CODE_SHA no se toca en ningún test.
    monkeypatch.setattr(dec.comun, "T024_PREREG_SHA", sha_p)
    return repo, sha_p, sha_a


def _commit_lock(repo: Path, contenido: str) -> str:
    lock = repo / dec.comun.T024_CODE_LOCK
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(contenido, encoding="utf-8")
    _git_tmp(repo, "add", "-A")
    _git_tmp(repo, "commit", "-q", "-m", "lock")
    return _git_tmp(repo, "rev-parse", "HEAD")


def test_lock_real_sidecar_correcto_y_ejecutor_sin_cambios_pasa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, _p, sha_a = _repo_t024(tmp_path, monkeypatch)
    _commit_lock(repo, sha_a + "\n")
    assert dec.cargar_t024_code_sha(repo) == sha_a
    assert dec.verificar_identidad(repo) == sha_a


def test_lock_real_ejecutor_cambiado_despues_del_sha_deniega(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, _p, sha_a = _repo_t024(tmp_path, monkeypatch)
    _commit_lock(repo, sha_a + "\n")
    assert dec.verificar_identidad(repo) == sha_a
    (repo / "advisor" / "research" / "ejecutor.py").write_text("X = 2\n", encoding="utf-8")
    _git_tmp(repo, "add", "-A")
    _git_tmp(repo, "commit", "-q", "-m", "C")
    with pytest.raises(dec.T024DecisionError, match="ejecutor cambiado"):
        dec.verificar_identidad(repo)


def test_lock_real_reproduce_la_circularidad_de_fijar_el_sha_en_advisor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Escribir el SHA dentro de advisor/ cambia el ejecutor tras ese SHA: la identidad nunca pasaría."""

    repo, _p, sha_a = _repo_t024(tmp_path, monkeypatch)
    (repo / "advisor" / "research" / "lock.py").write_text(f'T024_CODE_SHA = "{sha_a}"\n', encoding="utf-8")
    lock = repo / dec.comun.T024_CODE_LOCK
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(sha_a + "\n", encoding="utf-8")
    _git_tmp(repo, "add", "-A")
    _git_tmp(repo, "commit", "-q", "-m", "SHA dentro de advisor")
    with pytest.raises(dec.T024DecisionError, match="ejecutor cambiado"):
        dec.verificar_identidad(repo)


def test_lock_real_sidecar_ausente_deniega(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, _p, _a = _repo_t024(tmp_path, monkeypatch)
    with pytest.raises(dec.T024DecisionError, match="ausente o no versionado"):
        dec.verificar_identidad(repo)


def test_lock_real_sidecar_sin_commitear_deniega(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, _p, sha_a = _repo_t024(tmp_path, monkeypatch)
    lock = repo / dec.comun.T024_CODE_LOCK
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(sha_a + "\n", encoding="utf-8")
    with pytest.raises(dec.T024DecisionError, match="ausente o no versionado"):
        dec.verificar_identidad(repo)


def test_lock_real_sidecar_modificado_en_copia_de_trabajo_deniega(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, sha_p, sha_a = _repo_t024(tmp_path, monkeypatch)
    _commit_lock(repo, sha_a + "\n")
    (repo / dec.comun.T024_CODE_LOCK).write_text(sha_p + "\n", encoding="utf-8")
    with pytest.raises(dec.T024DecisionError, match="no coincide con HEAD"):
        dec.verificar_identidad(repo)


@pytest.mark.parametrize(
    "contenido",
    ["", "\n", "abc\n", "A" * 40 + "\n", "a" * 39 + "\n", "a" * 41 + "\n", " " + "a" * 40 + "\n", "a" * 40 + "\n\n", "a" * 40 + " \n"],
)
def test_lock_real_sidecar_invalido_deniega(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contenido: str) -> None:
    repo, _p, _a = _repo_t024(tmp_path, monkeypatch)
    _commit_lock(repo, contenido)
    with pytest.raises(dec.T024DecisionError, match="formato inválido"):
        dec.verificar_identidad(repo)


def test_lock_real_sha_no_ancestro_deniega(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, _p, _a = _repo_t024(tmp_path, monkeypatch)
    _git_tmp(repo, "checkout", "-q", "-b", "lateral")
    (repo / "docs" / "lateral.md").write_text("x\n", encoding="utf-8")
    _git_tmp(repo, "add", "-A")
    _git_tmp(repo, "commit", "-q", "-m", "lateral")
    sha_lateral = _git_tmp(repo, "rev-parse", "HEAD")
    _git_tmp(repo, "checkout", "-q", "main")
    _commit_lock(repo, sha_lateral + "\n")
    with pytest.raises(dec.T024DecisionError, match="CODE_SHA no es ancestro"):
        dec.verificar_identidad(repo)
    # Un SHA bien formado que no existe en el repositorio tampoco pasa.
    _commit_lock(repo, "0123456789abcdef0123456789abcdef01234567\n")
    with pytest.raises(dec.T024DecisionError, match="CODE_SHA no es ancestro"):
        dec.verificar_identidad(repo)


def test_cargar_lock_no_admite_otra_ruta_ni_override() -> None:
    import inspect

    assert list(inspect.signature(dec.cargar_t024_code_sha).parameters) == ["repo"]
    assert list(inspect.signature(dec.verificar_identidad).parameters) == ["repo"]
    assert "code_sha" not in inspect.signature(dec.ejecutar_mirada).parameters
    assert not hasattr(dec.comun, "T024_CODE_SHA")


def test_construir_resultado_y_barras_decision_exigen_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    vintage = _vintage_from_rows("AAA", [cap.BarraCiega(d, 100, 101, 99, 100) for d in days(date(2026, 8, 28), 80)])
    with pytest.raises(dec.T024DecisionError, match="ausente"):
        dec.construir_resultado(None, None, _Universe(), vintage, c_e=date(2027, 8, 27), policies=["B2"])  # type: ignore[arg-type]
    with pytest.raises(dec.T024DecisionError, match="ausente"):
        dec.barras_decision(None, vintage, _Universe(), "AAA")
    marca = tmp_path / "m"
    marca.write_text("x", encoding="utf-8")
    inactive = dec.TokenMirada(marca, hashlib.sha256(marca.read_bytes()).hexdigest(), "n")
    with pytest.raises(dec.T024DecisionError, match="no activo"):
        dec.barras_decision(inactive, vintage, _Universe(), "AAA")
    monkeypatch.setattr(dec, "_TOKEN_ACTIVO", inactive)
    marca.write_text("y", encoding="utf-8")
    with pytest.raises(dec.T024DecisionError, match="modificada"):
        dec.barras_decision(inactive, vintage, _Universe(), "AAA")


def test_token_se_desactiva_tras_excepcion_en_ejecutar_mirada(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dec, "verificar_identidad", lambda _repo=".": "a" * 40)
    monkeypatch.setattr(dec, "capturar", lambda *_a, **_k: cap.ResultadoCaptura({"B2": _conteo("B2", True), "S2": _conteo("S2", True)}, {}))

    def boom(*_args: Any, **_kwargs: Any) -> dec.ResultadoDecision:
        raise RuntimeError("boom")

    monkeypatch.setattr(dec, "construir_resultado", boom)
    with pytest.raises(RuntimeError, match="boom"):
        dec.ejecutar_mirada(
            mirada="mirada_1",
            c_e=date(2027, 1, 1),
            config=None,  # type: ignore[arg-type]
            universe=_Universe(),
            cosecha_decisiva=replace(_vintage_from_rows("AAA", []), data_vintage_id="v1"),
            cosecha_decisiva_id="v1",
            registro_forward_path=_registro_forward(tmp_path, ["v0", "v1"], [date(2027, 1, 1), date(2027, 4, 1)]),
            evidence_dir=tmp_path,
        )
    assert dec._TOKEN_ACTIVO is None


def test_mirada_reconfirmacion_fallida_no_consume_ni_abre(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dec, "verificar_identidad", lambda _repo=".": "a" * 40)
    monkeypatch.setattr(dec, "capturar", lambda *_a, **_k: cap.ResultadoCaptura({"B2": _conteo("B2", False), "S2": _conteo("S2", True)}, {}))
    called = False

    def construir(*_args: Any, **_kwargs: Any) -> dec.ResultadoDecision:
        nonlocal called
        called = True
        return dec.ResultadoDecision({}, {}, {}, 0, 0, None)

    monkeypatch.setattr(dec, "construir_resultado", construir)
    out = dec.ejecutar_mirada(
        mirada="mirada_1",
        c_e=date(2027, 1, 1),
        config=None,  # type: ignore[arg-type]
        universe=_Universe(),
        cosecha_decisiva=replace(_vintage_from_rows("AAA", []), data_vintage_id="v1"),
        cosecha_decisiva_id="v1",
        registro_forward_path=_registro_forward(tmp_path, ["v0", "v1"], [date(2027, 1, 1), date(2027, 4, 1)]),
        evidence_dir=tmp_path,
    )
    assert out == dec.REPROPONER
    assert not called
    assert not (tmp_path / "mirada_1.t024.consumida").exists()


def test_marca_exclusiva_y_registro_de_cosechas(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dec, "verificar_identidad", lambda _repo=".": "a" * 40)
    monkeypatch.setattr(dec, "capturar", lambda *_a, **_k: cap.ResultadoCaptura({"B2": _conteo("B2", True), "S2": _conteo("S2", True)}, {}))
    result = dec.ResultadoDecision(
        {"B2": dec.ResultadoPolitica("B2", dec.NO_CONCLUYENTE, 100, 0.0, (-1, 1)), "S2": dec.ResultadoPolitica("S2", dec.NO_POSITIVO, 100, -1.0, (-2, 0))},
        {},
        {},
        0,
        0,
        None,
    )
    monkeypatch.setattr(dec, "construir_resultado", lambda *_a, **_k: result)
    out = dec.ejecutar_mirada(
        mirada="mirada_1",
        c_e=date(2027, 1, 1),
        config=None,  # type: ignore[arg-type]
        universe=_Universe(),
        cosecha_decisiva=replace(_vintage_from_rows("AAA", []), data_vintage_id="v1"),
        cosecha_decisiva_id="v1",
        registro_forward_path=_registro_forward(tmp_path, ["v0", "v1"], [date(2027, 1, 1), date(2027, 4, 1)]),
        evidence_dir=tmp_path,
    )
    assert out == result
    mark = tmp_path / "mirada_1.t024.consumida"
    assert json.loads(mark.read_text())["cosecha_decisiva"] == "v1"
    with pytest.raises(FileExistsError):
        dec.crear_marca_exclusiva(mark, "")


def test_r2_calendario_estricto_mirada_1_y_final(tmp_path: Path) -> None:
    with pytest.raises(dec.T024DecisionError):
        dec.validar_mirada(mirada="mirada_1", c_e=dec.C_E_FINAL, evidence_dir=tmp_path)
    assert dec.politicas_para_mirada(mirada="mirada_final", c_e=dec.C_E_FINAL, evidence_dir=tmp_path) == ("B2", "S2")
    with pytest.raises(dec.T024DecisionError):
        dec.validar_mirada(mirada="mirada_final", c_e=date(2027, 1, 1), evidence_dir=tmp_path)


def test_r3_registro_forward_con_checkpoint_y_75_dias(tmp_path: Path) -> None:
    path = _registro_forward(tmp_path, ["v1"])
    registro = dec.cargar_registro_forward(path, "v1")
    assert dec.checkpoint_de(registro, "v1") == date(2027, 4, 1)
    dec.exigir_regla_75_dias(date(2027, 1, 1), date(2027, 3, 17))
    with pytest.raises(dec.T024DecisionError):
        dec.exigir_regla_75_dias(date(2027, 1, 1), date(2027, 3, 16))


def test_r5_marca_existente_deniega_aunque_no_haya_registro(tmp_path: Path) -> None:
    (tmp_path / "mirada_1.t024.consumida").write_text("x", encoding="utf-8")
    with pytest.raises(dec.T024DecisionError):
        dec.validar_mirada(mirada="mirada_1", c_e=date(2027, 1, 1), evidence_dir=tmp_path)


def test_final_denegada_si_mirada_1_tiene_marca_sin_estados(tmp_path: Path) -> None:
    (tmp_path / "mirada_1.t024.consumida").write_text("x", encoding="utf-8")
    with pytest.raises(dec.T024DecisionError, match="sin estados"):
        dec.politicas_para_mirada(mirada="mirada_final", c_e=dec.C_E_FINAL, evidence_dir=tmp_path)


def test_c_e_debe_ser_checkpoint_del_registro(tmp_path: Path) -> None:
    path = _registro_forward(tmp_path, ["v0", "v1"], [date(2027, 1, 1), date(2027, 4, 1)])
    registro = dec.cargar_registro_forward(path, "v1")
    dec.exigir_calendario_registro(registro, date(2027, 1, 1), "v1")
    with pytest.raises(dec.T024DecisionError, match="no es un checkpoint"):
        dec.exigir_calendario_registro(registro, date(2027, 1, 2), "v1")


def test_cosecha_decisiva_es_la_primera_a_75_dias(tmp_path: Path) -> None:
    fechas = [date(2027, 1, 1), date(2027, 2, 1), date(2027, 3, 1), date(2027, 4, 1), date(2027, 5, 3)]
    path = _registro_forward(tmp_path, ["v0", "v1", "v2", "v3", "v4"], fechas)
    registro = dec.cargar_registro_forward(path, "v3")
    # c_e = 2027-01-01 → límite 2027-03-17: la primera a 75 días o más es v3 (2027-04-01), no v4.
    dec.exigir_calendario_registro(registro, date(2027, 1, 1), "v3")
    with pytest.raises(dec.T024DecisionError, match="primer checkpoint"):
        dec.exigir_calendario_registro(registro, date(2027, 1, 1), "v4")
    with pytest.raises(dec.T024DecisionError, match="primer checkpoint"):
        dec.exigir_calendario_registro(registro, date(2027, 1, 1), "v2")


def _mirada_kwargs(tmp_path: Path, mirada: str, c_e: date, vintage_id: str) -> dict[str, Any]:
    return dict(
        mirada=mirada,
        c_e=c_e,
        config=None,
        universe=_Universe(),
        cosecha_decisiva=replace(_vintage_from_rows("AAA", []), data_vintage_id=vintage_id),
        cosecha_decisiva_id="v1",
        registro_forward_path=_registro_forward(tmp_path, ["v0", "v1"], [date(2027, 1, 1), date(2027, 4, 1)]),
        evidence_dir=tmp_path,
    )


def test_cosecha_recibida_distinta_de_la_declarada_se_deniega_sin_marca(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dec, "verificar_identidad", lambda _repo=".": "a" * 40)
    capturas: list[Any] = []
    monkeypatch.setattr(dec, "capturar", lambda *a, **_k: capturas.append(a) or cap.ResultadoCaptura({}, {}))
    with pytest.raises(dec.T024DecisionError, match="no es la cosecha decisiva declarada"):
        dec.ejecutar_mirada(**_mirada_kwargs(tmp_path, "mirada_1", date(2027, 1, 1), "otra"))
    assert capturas == []
    assert not (tmp_path / "mirada_1.t024.consumida").exists()


def test_mirada_final_capacidad_por_politica(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dec, "verificar_identidad", lambda _repo=".": "a" * 40)
    monkeypatch.setattr(
        dec, "capturar", lambda *_a, **_k: cap.ResultadoCaptura({"B2": _conteo("B2", False), "S2": _conteo("S2", True)}, {})
    )
    pedidas: list[tuple[str, ...]] = []

    def construir(_token: Any, *_a: Any, policies: Sequence[str], **_k: Any) -> dec.ResultadoDecision:
        pedidas.append(tuple(policies))
        return dec.ResultadoDecision({"S2": dec.ResultadoPolitica("S2", dec.NO_POSITIVO, 120, -0.01, (-0.02, -0.001))}, {}, {}, 0, 0, None)

    monkeypatch.setattr(dec, "construir_resultado", construir)
    kwargs = _mirada_kwargs(tmp_path, "mirada_final", dec.C_E_FINAL, "v1")
    kwargs["registro_forward_path"] = _registro_forward(tmp_path, ["v0", "v1"], [dec.C_E_FINAL - timedelta(days=30), dec.C_E_FINAL + timedelta(days=80)])
    out = dec.ejecutar_mirada(**kwargs)
    assert pedidas == [("S2",)]
    assert isinstance(out, dec.ResultadoDecision)
    assert out.politicas["B2"].etiqueta == dec.NO_EVALUABLE
    assert out.politicas["S2"].etiqueta == dec.NO_POSITIVO


def test_d3_indice_region_incluye_analizables_sin_senal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rows = {s: [cap.BarraCiega(d, 100, 101, 99, 100) for d in days(date(2026, 8, 28), 90)] for s in ("AAA", "BBB", "CCC")}
    vintage = _vintage_multi(rows)
    universe = _RegionalUniverse({"AAA": "USA", "BBB": "USA", "CCC": "EUROPA"})
    token = _activar_token(tmp_path, monkeypatch)
    monkeypatch.setattr(cap, "asset_list", lambda: ["AAA", "BBB", "CCC"])
    monkeypatch.setattr(
        cap,
        "generar_senales_operar",
        lambda **kw: ([senal(policy="B2", asset="AAA", s_index=1, stop=90, target=200, entry_max=200, sid="b2")], {})
        if kw["policy"] == "B2"
        else ([], {}),
    )
    vistos: list[set[str]] = []
    original = dec.indice_equiponderado_region

    def espia(series: Mapping[str, Sequence[dec.BarraDecision]]) -> dict[date, float]:
        vistos.append(set(series))
        return original(series)

    monkeypatch.setattr(dec, "indice_equiponderado_region", espia)
    dec.construir_resultado(token, None, universe, vintage, c_e=date(2027, 8, 27), policies=["B2"])  # type: ignore[arg-type]
    assert {"AAA", "BBB"} in vistos and {"CCC"} in vistos


def test_ninguna_ruta_publica_abre_desenlaces_de_cosecha_sin_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Con barras de una cosecha, toda función de desenlace exige el token; con sintéticas, no."""

    reales = tuple(replace(b, origen="cosecha:v1") for b in bars(70))
    sint = tuple(bars(70))
    s1 = senal(stop=90, target=200, entry_max=200)
    ventana_sint = dec.construir_ventanas([s1], {"AAA": sint}, c_e=date(2027, 8, 27)).ventanas[0]
    ventana_real = replace(ventana_sint, origen="cosecha:v1")
    llamadas: list[Callable[[], object]] = [
        lambda: dec.salida_p6(s1, reales),
        lambda: dec.retornos_cierre(reales),
        lambda: dec.drift_noche_dia(reales),
        lambda: dec.construir_ventanas([s1], {"AAA": reales}, c_e=date(2027, 8, 27)),
        lambda: dec.calcular_ventana(s1, reales, 5, dec.EXIT_FINAL, 100.0, 0.0, t0=reales[0].session, t1=reales[-1].session, truncada_t1=False),
        lambda: dec.recalcular_por_politica_activo([ventana_real], {"AAA": sint}),
        lambda: dec.indice_equiponderado_region({"AAA": reales}),
        lambda: dec.d3_region(ventana_real, sint, {}),
        lambda: dec.d4_40_sesiones(ventana_real, sint),
        lambda: dec.decidir_politica("B2", [ventana_real]),
    ]
    for llamada in llamadas:
        with pytest.raises(dec.T024DecisionError, match="token de mirada ausente"):
            llamada()
    # Con datos sintéticos siguen siendo utilizables sin token (tests y desarrollo).
    assert dec.salida_p6(s1, sint)[1] == dec.EXIT_TIME
    assert dec.decidir_politica("B2", [ventana_sint]).etiqueta == dec.NO_EVALUABLE
    # Con el token de una mirada activo, las barras de cosecha se aceptan.
    _activar_token(tmp_path, monkeypatch)
    assert dec.salida_p6(s1, reales)[1] == dec.EXIT_TIME
    assert dec.construir_ventanas([s1], {"AAA": reales}, c_e=date(2027, 8, 27)).ventanas[0].origen == "cosecha:v1"


def test_barras_decision_marca_origen_de_cosecha(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rows = [cap.BarraCiega(d, 100, 101, 99, 100) for d in days(date(2026, 8, 28), 5)]
    vintage = replace(_vintage_from_rows("AAA", rows), data_vintage_id="v1")
    token = _activar_token(tmp_path, monkeypatch)
    barras = dec.barras_decision(token, vintage, _Universe(), "AAA")  # type: ignore[arg-type]
    assert {b.origen for b in barras} == {"cosecha:v1"}


def test_truncada_t1_solo_para_regla_final() -> None:
    s1 = senal(s_index=0, stop=95, target=200, entry_max=200)
    rows = bars(3)
    stop_en_ultima = list(rows)
    stop_en_ultima[2] = dec.BarraDecision(rows[2].session, 90, 90, 90, 90)
    x, motivo, _precio, _div, truncada = dec.salida_p6(s1, stop_en_ultima)
    assert (x, motivo, truncada) == (2, dec.EXIT_STOP, False)
    x, motivo, _precio, _div, truncada = dec.salida_p6(s1, rows)
    assert (x, motivo, truncada) == (2, dec.EXIT_FINAL, True)


def test_r6_eur_descriptivo_sin_fx_declara_motivo() -> None:
    assert dec._fx_eur_descriptivo([], {}, None) == {"motivo": "FX forward no congelado"}


def test_maximo_dos_miradas_y_final_solo_pendientes(tmp_path: Path) -> None:
    data = {
        "consumidas": {"mirada_1": {"c_e": "2027-01-01", "policies": ["B2", "S2"]}},
        "mirada_1_estados": {"B2": dec.NO_CONCLUYENTE, "S2": dec.NO_POSITIVO},
    }
    (tmp_path / "miradas-t024.json").write_text(json.dumps(data), encoding="utf-8")
    assert dec.politicas_para_mirada(mirada="mirada_final", c_e=date(2027, 8, 27), evidence_dir=tmp_path) == ("B2",)
    with pytest.raises(dec.T024DecisionError):
        dec.validar_mirada(mirada="mirada_2", c_e=date(2027, 8, 27), evidence_dir=tmp_path)
    (tmp_path / "miradas-t024.json").write_text(json.dumps({"consumidas": {"mirada_1": {}}, "mirada_1_estados": {"B2": dec.NO_POSITIVO, "S2": dec.NO_POSITIVO}}), encoding="utf-8")
    with pytest.raises(dec.T024DecisionError):
        dec.validar_mirada(mirada="mirada_final", c_e=date(2027, 8, 27), evidence_dir=tmp_path)


def _imports_resueltos(source: str, module: str = "advisor.research.t024_captura") -> set[str]:
    tree = ast.parse(source)
    package = module.rsplit(".", 1)[0]
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")
                base = ".".join(parts[: len(parts) - node.level + 1])
                mod = f"{base}.{node.module}" if node.module else base
            else:
                mod = node.module or ""
            imported.add(mod)
            imported.update(f"{mod}.{alias.name}" if mod else alias.name for alias in node.names)
            imported.update(alias.name for alias in node.names)
    return imported


def test_imports_cerrados_de_captura_grafo_local() -> None:
    source = Path("advisor/research/t024_captura.py").read_text(encoding="utf-8")
    banned = {
        "advisor.research.t024_decision",
        "advisor.research.p6",
        "advisor.research.p6_sim",
        "simulate",
        "simulate_benchmark",
        "build_real_market",
        "build_real_signals",
        "salida_p6",
        "construir_resultado",
        "construir_ventanas",
        "barras_decision",
        "ejecutar_mirada",
    }
    imported = _imports_resueltos(source)
    assert not (banned & imported)
    assert "advisor.analysis.levels.rr_at_least" in cap.T024_CAPTURA_IMPORTED_CALLABLES


def test_imports_cerrados_detecta_from_advisor_research_import_t024_decision() -> None:
    imported = _imports_resueltos("def f():\n    from advisor.research import t024_decision\n")
    assert "advisor.research.t024_decision" in imported


def test_constantes_policy_config_y_asset_list_igualan_p6() -> None:
    import advisor.research.p6 as p6

    assert cap.HORIZONTE == p6.HORIZONTE
    assert cap.WARMUP_BARS == p6.WARMUP_BARS
    assert cap.asset_list() == p6.asset_list()


def _dev_context(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Any, VintageLoad, list[str]]:
    from advisor.config import load_config
    from advisor.research.vintage import load_vintage
    from advisor.universe.loader import load_universe

    # En CI el manifiesto está versionado pero los CSV no (como en tests/test_p6.py): solo en local.
    if not (Path("data/vintages") / cap.DEV_VINTAGE_ID / "AAPL.csv").is_file():
        pytest.skip("data/vintages no está disponible")
    config = load_config("config.yaml")
    universe = load_universe(config.universe_path)
    vintage = load_vintage(cap.DEV_VINTAGE_ID)
    symbols = cap.asset_list()[:20]
    monkeypatch.setattr(cap, "asset_list", lambda: symbols)
    return config, universe, vintage, symbols


def test_smoke_desarrollo_capturar_consumida_solo_conteos(monkeypatch: pytest.MonkeyPatch) -> None:
    config, universe, vintage, _symbols = _dev_context(monkeypatch)
    result = cap.capturar(
        config,
        universe,
        vintage,
        c_e=date(2026, 6, 30),
        cutoff=date(2026, 3, 31),
        desarrollo=True,
    )
    assert result.rotulo == "DESARROLLO — no decide"
    for conteo in result.conteos.values():
        assert conteo.senales_operar >= 0
        assert conteo.ejecutables <= conteo.senales_operar
        assert conteo.q_p <= conteo.ejecutables
        assert conteo.w_p <= conteo.q_p


def test_generacion_t024_igual_a_p6_en_subventana_desarrollo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import advisor.research.p6 as p6

    config, universe, vintage, symbols = _dev_context(monkeypatch)
    monkeypatch.setattr(p6, "asset_list", lambda: symbols)
    monkeypatch.setattr(p6, "RUN_DIR", tmp_path)
    marker = tmp_path / p6.RUN_MARKER
    marker.write_text("{}\n", encoding="utf-8")
    token = p6.ConfirmatoryToken(marker, hashlib.sha256(marker.read_bytes()).hexdigest())
    monkeypatch.setattr(p6, "_ACTIVE_TOKEN", token)
    window = p6.Window(date(2026, 4, 1), date(2026, 6, 30), date(2026, 3, 31), date(2026, 3, 31), 0, 60, 252.0)
    p6_signals, _ = p6.build_real_signals(token, config, universe, vintage, "B2", p6.POPULATION_OPERAR, window)
    t024_signals, _ = cap.generar_senales_operar(config=config, universe=universe, vintage=vintage, policy="B2", c_e=date(2026, 6, 30), cutoff_desarrollo=date(2026, 3, 31))
    left = [(s.signal_id, s.asset, s.bar_index, s.stop, s.target2, s.entry_max) for s in p6_signals]
    right = [(s.signal_id, s.asset, s.s_index, s.stop, s.target2, s.entry_max) for s in t024_signals]
    assert right == left
