"""Tests pre-registrados del ejecutor de P4 (T-020 / A-04, paso 2).

Todos usan datos sintéticos o desenlaces fabricados. Los que tocan la cosecha
real solo reproducen el preflight, que no abre desenlaces, y se saltan
únicamente si falta un CSV real de la cosecha (no basta con el directorio: el
manifiesto sí se commitea).
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import pytest

import advisor.research.event_study as event_study
import advisor.research.p4 as p4
from advisor.analysis.execution import (
    ABOVE_MAX_ENTRY,
    EXECUTABLE,
    INVALID_STOP,
    INVALID_TARGET,
    RR_TOO_LOW,
    evaluate_trade_at_entry,
)
from advisor.analysis.levels import Levels
from advisor.config import LevelsConfig, PortfolioConfig, RiskConfig, load_config
from advisor.data.calendars import expected_sessions
from advisor.research.bootstrap import session_block_lookup
from advisor.research.capacity import TemporalBlockMap
from advisor.research.event_study import (
    AMBIGUOUS,
    FINAL_EXIT,
    STOP_FIRST,
    TARGET_FIRST,
    TIME_EXIT,
    EventStudyResult,
    EventStudySignal,
    ManagedEvent,
    PotentialEvent,
)
from advisor.research.observations import SignalObservation, stable_signal_id
from advisor.research.timestamps import parse_timestamp, timestamp_raw
from advisor.research.vintage import VintageLoad, VintageViews
from advisor.universe.loader import load_universe

BASE = LevelsConfig()
REAL_CSV = Path("data/vintages") / p4.DATA_VINTAGE_ID / "AAPL.csv"


def _cosecha_disponible() -> bool:
    return REAL_CSV.is_file()


def forbidden(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("PREFLIGHT_LEYO_DESENLACE")


# Todas las rutas que pueden producir un desenlace (ManagedEvent, PotentialEvent,
# net_R o una salida futura) o una estimación con desenlaces.
OUTCOME_PATHS = (
    (event_study, "evaluate_managed_event"),
    (event_study, "evaluate_potential_event"),
    (event_study, "event_economics"),
    (event_study, "classify_target_stop_bar"),
    (event_study, "run_event_study_on_vintage"),
    (event_study, "run_event_study"),
    (event_study, "replay_managed_population"),
    (event_study, "replay_managed_population_counting_missing"),
    (p4, "simulate_e1_open_entry"),
    (p4, "analyze_variant"),
    (p4, "analyze_e1"),
    (p4, "ambiguity_bound_deltas"),
    (p4, "execute_with_outcomes"),
    (p4, "bootstrap_block_delta"),
    (p4, "bootstrap_block_mean_interval"),
    (p4, "pair_populations"),
)


def _forbid_outcomes(monkeypatch: pytest.MonkeyPatch) -> None:
    for module, name in OUTCOME_PATHS:
        monkeypatch.setattr(module, name, forbidden)


# --- constructores sintéticos ---------------------------------------------------


def _obs(
    asset: str = "AAA",
    idx: int = 0,
    day: date = date(2024, 1, 2),
    *,
    price: float = 100.0,
    atr: Optional[float] = 2.0,
    low: Optional[float] = None,
    high: Optional[float] = None,
) -> SignalObservation:
    ts = pd.Timestamp(day.isoformat(), tz="UTC")
    raw = timestamp_raw(ts)
    return SignalObservation(
        signal_id=stable_signal_id(asset, "swing", ts),
        data_vintage_id=p4.DATA_VINTAGE_ID,
        asset=asset,
        horizonte="swing",
        signal_idx=idx,
        signal_timestamp_raw=raw,
        signal_timestamp=parse_timestamp(raw),
        score_value=50.0,
        evaluable_max=80.0,
        dimensions=(),
        price=price,
        atr=atr,
        low_lookback=low,
        high_lookback=high,
        ema_fast=None,
    )


def _levels(geometry: p4.Geometry = p4.C0, **kwargs: Any) -> Levels:
    obs = _obs(**kwargs)
    levels = p4.geometry_levels(obs, geometry, BASE)
    assert levels is not None
    return levels


def _managed(
    obs: SignalObservation,
    net: Optional[float],
    status: str = TARGET_FIRST,
    *,
    entry: float = 100.0,
    stop: float = 96.0,
    target: float = 106.0,
    exit_idx: int = 5,
) -> ManagedEvent:
    raw = "2026-01-01T00:00:00Z"
    return ManagedEvent(
        observation=obs,
        entry_price=entry,
        stop=stop,
        target=target,
        exit_status=status,
        exit_idx=exit_idx,
        exit_timestamp_raw=raw,
        exit_timestamp=parse_timestamp(raw),
        exit_price=None if status == AMBIGUOUS else entry,
        bars_held=exit_idx,
        risk_pp=(entry - stop) / entry * 100,
        gross_return_pp=None if net is None else net,
        net_return_pp=None if net is None else net,
        gross_r_multiple=net,
        net_r_multiple=net,
        mae_r=0.2,
        mfe_lower_r=0.5,
        mfe_upper_r=0.6,
    )


def _potential(obs: SignalObservation) -> PotentialEvent:
    raw = "2026-01-01T00:00:00Z"
    return PotentialEvent(
        observation=obs,
        entry_price=100.0,
        stop=96.0,
        exit_status=STOP_FIRST,
        exit_idx=3,
        exit_timestamp_raw=raw,
        exit_timestamp=parse_timestamp(raw),
        mfe_unbounded_lower_r=1.0,
        mfe_unbounded_upper_r=1.2,
    )


SPINE = tuple(date(2020, 1, 1) + timedelta(days=i) for i in range(22 * 60))


def _p4_signal(
    obs: SignalObservation,
    session_index: int,
    *,
    region: str = "USA",
    regime: str = "RISK_ON",
    next_open: float = 100.0,
) -> p4.P4Signal:
    session = SPINE[session_index]
    return p4.P4Signal(
        observation=obs,
        region=region,
        plaza_session=session,
        spine_session=session,
        blocks={length: session_index // length for length in p4.BLOCK_LENGTHS},
        regime=regime,
        next_open=next_open,
    )


def _population(signals: List[p4.P4Signal]) -> p4.P4Population:
    lookups = {
        length: TemporalBlockMap(
            block_length=length, session_spine=SPINE, session_to_block=session_block_lookup(SPINE, length), assets={}
        )
        for length in p4.BLOCK_LENGTHS
    }
    return p4.P4Population(
        signals=signals,
        meta=EventStudyResult(data_vintage_id=p4.DATA_VINTAGE_ID, horizonte="swing", cost_pct=0.2, warmup_bars=0, max_hold_bars=40),
        lookups=lookups,
        a02=len(signals),
        crypto_excluded=0,
        crypto_assets=(),
        population_sha256="",
        signal_ids_sha256="",
        regions={},
        regimes={},
        no_calculable_codes={},
        blocks={},
        enumerated_levels={
            s.signal_id: levels
            for s in signals
            if (levels := p4.geometry_levels(s.observation, p4.C0, BASE)) is not None
        },
    )


def _synthetic_population(n_sessions_from: int = 120, deltas: Optional[Dict[int, float]] = None) -> p4.P4Population:
    """Una señal por sesión en los bloques 2–21 de 60, con regiones, regímenes y ATR variados."""

    rng = random.Random(7)
    signals = []
    regions = ("USA", "EUROPA", "ASIA")
    regimes = ("RISK_ON", "CAUTELA", "RISK_OFF", p4.NO_CALCULABLE_CONTEXT)
    for i in range(n_sessions_from, len(SPINE)):
        atr = 1.0 + rng.random() * 3.0
        low = 100.0 - atr * (0.5 + rng.random()) if i % 5 == 0 else None
        obs = _obs(asset=f"A{i % 4}", idx=10, day=SPINE[i], atr=atr, low=low)
        signals.append(_p4_signal(obs, i, region=regions[i % 3], regime=regimes[i % 4], next_open=100.0 + rng.uniform(-1, 3)))
    return _population(signals)


# --- 1. identidad -----------------------------------------------------------------


def test_constantes_de_identidad_exactas() -> None:
    assert p4.P4_PREREG_SHA == "48b884722ef027e99857a4e65f9ab6b11da4758f"
    assert p4.DATA_VINTAGE_ID == "071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841"
    assert p4.UNIVERSE_VINTAGE_ID == "237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19"
    assert p4.P4_POPULATION_SHA256 == "78024050f7081ad4e1dd5cefaefbfa1a1668ff5b1a2ced8c34e62b6501873141"
    assert p4.P4_SIGNAL_IDS_SHA256 == "9faa4a45beaba3eb8dafabf7990906cd8c89e8e06ae2f25edec7839cd48e629f"
    assert p4.COST_PCT == 0.2 and p4.SEED == 20260830
    assert p4.STANDARD_RESAMPLES == 2000 and p4.STANDARD_CONFIDENCE == 0.95
    assert p4.BONFERRONI_M == 4 and p4.BONFERRONI_RESAMPLES == 20_000
    assert p4.BONFERRONI_CONFIDENCE == 0.9875
    assert math.isclose(p4.BONFERRONI_CONFIDENCE, 1 - 0.05 / p4.BONFERRONI_M)
    assert p4.UNIVERSE_LABEL == (
        "condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)"
    )
    ident = p4.P4Identity("abc", False, True, "h", "1.0").as_dict()
    assert ident["p4_prereg_sha"] == p4.P4_PREREG_SHA and ident["label"] == p4.UNIVERSE_LABEL
    assert ident["bonferroni"] == {"m": 4, "confidence": 0.9875, "resamples": 20000}


# --- 2-5. geometrías, álgebra y niveles --------------------------------------------


def test_geometrias_exactas() -> None:
    expected = {
        "C0": (2.0, (1.5, 3.0, 5.0)),
        "B1": (2.0, (1.5, 3.5, 5.0)),
        "B2": (2.0, (1.5, 4.875, 5.0)),
        "S1": (1.5, (1.5, 2.25, 5.0)),
        "S2": (2.5, (1.5, 3.75, 5.0)),
    }
    assert [g.gid for g in p4.GEOMETRIES] == list(expected)
    for geometry in p4.GEOMETRIES:
        assert (geometry.atr_stop_multiple, geometry.target_atr_multiples) == expected[geometry.gid]
        assert geometry.target2_structural is False
        assert geometry.entry_max_atr == 0.75 and geometry.min_rr == 1.5
        config = geometry.levels_config(BASE)
        assert config.target2_structural is False and config.entry_max_atr == 0.75
        assert config.lookback_bars == BASE.lookback_bars and config.entry_pullback_atr == BASE.entry_pullback_atr
    assert p4.B1.label == "previamente expuesta en esta misma cosecha; no confirmatoria; no elegible para sustituir C0"
    assert (p4.B1.confirmatory, p4.B1.eligible_for_p5, p4.B1.bonferroni) == (False, False, False)
    for geometry in (p4.B2, p4.S1, p4.S2):
        assert (geometry.confirmatory, geometry.eligible_for_p5, geometry.bonferroni) == (True, True, True)


def test_algebra_de_las_cinco_geometrias() -> None:
    table = {
        "C0": (1.5, 0.0, 0.0),
        "B1": (1.75, 0.2, 0.2),
        "B2": (2.4375, 0.75, 0.75),
        "S1": (1.5, 0.0, 0.0),
        "S2": (1.5, 0.0, 0.0),
    }
    for geometry in p4.GEOMETRIES:
        formula = p4.algebra(geometry)
        measured = p4.synthetic_algebra(geometry, BASE)
        rr, slack_rr, slack_eff = table[geometry.gid]
        for values in (formula, measured):
            assert values["rr_en_p"] == pytest.approx(rr, abs=1e-12)
            assert values["holgura_rr_atr"] == pytest.approx(slack_rr, abs=1e-12)
            assert values["holgura_efectiva_atr"] == pytest.approx(slack_eff, abs=1e-12)


def test_niveles_efectivos_con_y_sin_soporte() -> None:
    # Sin soporte: stop por volatilidad en todas.
    for geometry in p4.GEOMETRIES:
        levels = _levels(geometry)
        assert p4.stop_basis_of(levels) == p4.BASIS_VOLATILITY
        assert levels.stop == pytest.approx(100.0 - geometry.atr_stop_multiple * 2.0)
        assert p4.coherence_violations(levels, geometry.min_rr) == []
    # Soporte a 97 con A=2: acerca el stop de C0 (96,5 > 96) pero no el de S1 (97 cae bajo su stop 97).
    c0 = _levels(p4.C0, low=97.0)
    s1 = _levels(p4.S1, low=97.0)
    s2 = _levels(p4.S2, low=97.0)
    assert p4.stop_basis_of(c0) == p4.BASIS_SUPPORT and c0.stop == pytest.approx(96.5)
    assert p4.stop_basis_of(s1) == p4.BASIS_VOLATILITY and s1.stop == pytest.approx(97.0)
    assert p4.stop_basis_of(s2) == p4.BASIS_SUPPORT and s2.stop == pytest.approx(96.5)
    assert p4.stop_basis_pair(c0, s1) == "MIXTO" and p4.stop_basis_pair(c0, s2) == "SOP/SOP"
    assert p4.stop_basis_pair(_levels(p4.C0), _levels(p4.S1)) == "VOL/VOL"
    # Con soporte, el RR efectivo sube y la holgura deja de ser 0 en C0; S1 la pierde (§7).
    assert c0.rr_ratio > 1.5 and c0.entry_max > c0.price
    assert s1.entry_max <= c0.entry_max
    # Resistencia por debajo de target1: target1 cede y sigue coherente.
    resisted = _levels(p4.S1, high=101.0)
    assert resisted.target1 == 101.0 and p4.coherence_violations(resisted, 1.5) == []
    for geometry in p4.GEOMETRIES:
        for low, high in ((97.0, 101.0), (None, 100.5), (99.9, None)):
            levels = _levels(geometry, low=low, high=high)
            assert p4.coherence_violations(levels, geometry.min_rr) == []


def test_s2_devuelve_none_con_atr_extremo_y_se_cuenta() -> None:
    extreme = _obs(atr=45.0)  # ATR/P = 0,45 ≥ 0,4: el stop de S2 quedaría ≤ 0
    assert p4.geometry_levels(extreme, p4.S2, BASE) is None
    assert p4.levels_none_reason(extreme, p4.S2) == "STOP_FUERA_DE_RANGO"
    assert p4.geometry_levels(extreme, p4.C0, BASE) is not None
    assert p4.levels_none_reason(_obs(atr=None), p4.S2) == "SIN_ATR"
    signals = [_p4_signal(extreme, 130), _p4_signal(_obs(day=SPINE[131]), 131)]
    population = _population(signals)
    levels = p4.levels_by_geometry(population, BASE)
    census = p4.levels_census(population, p4.S2, levels["S2"], levels["C0"])
    assert census["none"] == 1 and census["none_por_motivo"] == {"STOP_FUERA_DE_RANGO": 1}
    assert census["validos"] == 1


# --- 6-12. población y bloques ------------------------------------------------------


def _real_inputs() -> Tuple[Any, Any, VintageLoad]:
    from advisor.research.vintage import load_vintage

    config = load_config("config.yaml")
    return config, load_universe(config.universe_path), load_vintage(p4.DATA_VINTAGE_ID)


def test_preflight_real_reproduce_poblacion_bloques_y_recuento_sin_desenlaces(monkeypatch: pytest.MonkeyPatch) -> None:
    if not _cosecha_disponible():
        pytest.skip(f"falta {REAL_CSV}: la cosecha no está en esta máquina")
    config, universe, vintage = _real_inputs()
    _forbid_outcomes(monkeypatch)
    ident = p4.P4Identity("test", False, True, p4.EXPECTED_CONFIG_HASH, "1.0")
    ok, report = p4.run_preflight(config, universe, vintage, ident, write=False)
    failed = [c for c in report["checks"] if not c["ok"]]
    assert failed == [] and ok
    population = report["poblacion"]
    assert (population["a02_swing"], population["cripto_excluido"], population["p4"], population["activos"]) == (
        106_363, 5_112, 101_251, 90,
    )
    assert population["cripto_activos"] == ["BTC-EUR", "ETH-EUR", "SOL-EUR"]
    assert population["p4_population_sha256"] == p4.P4_POPULATION_SHA256
    assert population["signal_ids_sha256"] == p4.P4_SIGNAL_IDS_SHA256
    assert population["regiones"] == dict(sorted(p4.EXPECTED_REGIONS.items()))
    # Las exclusiones de P3 NO se aplican: Asia ausente y SMA200 siguen dentro.
    assert report["contexto_pit"]["regimen"][p4.NO_CALCULABLE_CONTEXT] == 7_157
    assert report["contexto_pit"]["no_calculable_por_codigo"] == {
        "excluded_asia_missing": 396, "excluded_trend_sma_history": 6_937,
    }
    blocks = report["bloques"]
    assert (blocks["60"]["bloques_ocupados"], blocks["60"]["bloque_ocupado_mas_corto"]) == (20, 42)
    assert (blocks["120"]["bloques_ocupados"], blocks["120"]["bloque_ocupado_mas_corto"]) == (10, 102)
    assert (blocks["40"]["bloques_ocupados"], blocks["40"]["bloque_ocupado_mas_corto"]) == (30, 22)
    assert (blocks["80"]["bloques_ocupados"], blocks["80"]["bloque_ocupado_mas_corto"]) == (16, 22)
    assert not blocks["40"]["valida_P2_5"] and not blocks["80"]["valida_P2_5"]
    assert report["recuento"]["subtotales"] == {"B1": 110, "B2": 110, "S1": 113, "S2": 113, "E1": 1}
    assert report["recuento"]["total"] == 447 and report["recuento"]["confirmatorias"] == 4
    assert report["niveles"]["S2"]["none"] == 0
    assert report["holgura_d06"]["C0"]["GLOBAL"]["categoria_open_t1"][RR_TOO_LOW] == 0
    # El preflight nunca lee desenlaces; si P4 ya se ejecutó, el informe tiene que decirlo.
    assert report["outcomes_read"] is False
    marker_exists = (p4.CONFIRMATORY_OUTPUT_DIR / p4.RUN_MARKER).is_file()
    assert report["p4_confirmatory_executed"] is marker_exists


def test_skip_de_la_cosecha_mira_un_csv_real() -> None:
    assert REAL_CSV.suffix == ".csv" and REAL_CSV.parent.name == p4.DATA_VINTAGE_ID
    assert _cosecha_disponible() == REAL_CSV.is_file()


def test_poblacion_no_hereda_las_exclusiones_de_p3() -> None:
    import inspect

    source = inspect.getsource(p4)
    assert "p3_population" not in source and "census_p3_population" not in source
    build = inspect.getsource(p4.build_population)
    assert 'asset_class == "crypto"' in build
    assert "excluded_asia_missing" not in build and "excluded_trend_sma_history" not in build


def test_no_calculable_context_permanece_en_la_primaria(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(p4, "STANDARD_RESAMPLES", 50)
    monkeypatch.setattr(p4, "BONFERRONI_RESAMPLES", 50)
    population = _synthetic_population()
    outputs = _fabricated_outputs(population, lambda s: 0.1)
    b2 = outputs["B2"]
    no_calc = sum(1 for s in population.signals if s.regime == p4.NO_CALCULABLE_CONTEXT)
    assert no_calc > 0
    assert b2["emparejamiento"]["pares_no_calculable_context"] == no_calc
    assert b2["estimaciones"]["primaria_60"]["n_pares"] == len(population.signals)
    assert set(b2["estimaciones"]["regimenes"]) == set(p4.CALCULABLE_REGIMES)
    strata = p4.strata_of(next(s for s in population.signals if s.regime == p4.NO_CALCULABLE_CONTEXT), (0.01, 0.02), None)
    assert strata["regimenes"] is None


def test_bloques_y_papeles_pre_registrados() -> None:
    assert p4.BLOCK_LENGTHS == (40, 60, 80, 120)
    assert p4.EXPECTED_BLOCKS == {40: (30, 22), 60: (20, 42), 80: (16, 22), 120: (10, 102)}
    assert p4.PRIMARY_BLOCK_LENGTH == 60 and p4.SENSITIVITY_BLOCK_LENGTH == 120
    assert p4.INVALID_BLOCK_LENGTHS == (40, 80)
    assert p4.block_role(60) == "PRIMARIA" and p4.block_role(120).startswith("SENSIBILIDAD")
    assert p4.block_role(40).startswith("INVÁLIDA") and p4.block_role(80).startswith("INVÁLIDA")


def test_40_y_80_no_aprueban_ni_vetan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(p4, "STANDARD_RESAMPLES", 50)
    monkeypatch.setattr(p4, "BONFERRONI_RESAMPLES", 50)
    population = _synthetic_population()
    outputs = _fabricated_outputs(population, lambda s: 0.1)
    assert outputs["B2"]["estimaciones"]["bloque_40"]["longitud_valida"] is False
    assert outputs["B2"]["estimaciones"]["bloque_80"]["longitud_valida"] is False
    census = {"coherentes": True}
    base = p4.evaluate_candidate(p4.candidate_evidence("B2", outputs["B2"], census, {}))
    tampered = json.loads(json.dumps(outputs["B2"]))
    for length in ("40", "80"):
        tampered["estimaciones"][f"bloque_{length}"].update(media_delta_r=-9.0, ic_inferior=-9.0, ic_superior=-8.0)
    again = p4.evaluate_candidate(p4.candidate_evidence("B2", tampered, census, {}))
    assert [c.passed for c in again.conditions] == [c.passed for c in base.conditions]
    tampered["estimaciones"]["bloque_120"].update(media_delta_r=-1.0, ic_inferior=-2.0)
    worse = p4.evaluate_candidate(p4.candidate_evidence("B2", tampered, census, {}))
    assert worse.conditions[1].passed is False  # 120 sí es la sensibilidad que cuenta


# --- 13-19. familia y criterio ------------------------------------------------------


def test_familia_confirmatoria_exacta_m4() -> None:
    assert len(p4.CONFIRMATORY_FAMILY) == 4
    assert set(p4.CONFIRMATORY_FAMILY) == {"B2_vs_C0", "S1_vs_C0", "S2_vs_C0", "E1"}
    assert p4.BONFERRONI_M == 4 == len(p4.CONFIRMATORY_FAMILY)
    assert p4.CANDIDATE_IDS == ("B2", "S1", "S2")


def test_b1_fuera_de_la_familia() -> None:
    assert "B1_vs_C0" not in p4.CONFIRMATORY_FAMILY
    assert not any(member.startswith("B1") for member in p4.CONFIRMATORY_FAMILY)
    assert "B1" not in p4.CANDIDATE_IDS


def _evidence(gid: str = "B2", **changes: Any) -> p4.CandidateEvidence:
    base = p4.CandidateEvidence(
        geometry_id=gid,
        bonferroni_lower=0.05,
        sensitivity_120_mean=0.1,
        sensitivity_120_lower=0.02,
        capacity_ok=True,
        capacity_reasons=(),
        heterogeneity="BAJA",
        conservative_bound_mean=0.04,
        levels_coherent=True,
        executability={ABOVE_MAX_ENTRY: 0.05},
        first_half_mean=0.1,
        second_half_mean=0.1,
        pairs=p4.EXPECTED_P4,
        population=p4.EXPECTED_P4,
        level_mean=0.2,
        level_profit_factor=1.3,
    )
    return replace(base, **changes)


def test_b1_jamas_candidata_aunque_sea_extremadamente_favorable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(p4, "STANDARD_RESAMPLES", 50)
    monkeypatch.setattr(p4, "BONFERRONI_RESAMPLES", 50)
    with pytest.raises(ValueError):
        p4.evaluate_candidate(_evidence("B1", bonferroni_lower=99.0))
    fake_verdict = p4.CandidateVerdict("B1", True, ())
    with pytest.raises(ValueError):
        p4.candidates_for_p5([fake_verdict])
    population = _synthetic_population()
    baseline = _fabricated_outputs(population, lambda s: -0.05)
    favorable_b1 = _fabricated_outputs(population, lambda s: -0.05, b1_delta=lambda s: 5.0)
    preflight = _fake_preflight()
    ident = p4.P4Identity("x", False, True, "h", "1.0")
    first = p4.assemble_result(ident, preflight, baseline)
    second = p4.assemble_result(ident, preflight, favorable_b1)
    assert "B1" not in second["candidatas_p5"] and second["b1"]["candidata"] is False
    assert first["criterio"] == second["criterio"]  # B1 no toca ninguna condición de B2/S1/S2
    assert second["salidas"]["B1"]["estimaciones"]["primaria_60"]["confirmatoria"] is False
    assert second["salidas"]["B1"]["estimaciones"]["primaria_60"]["ic_nivel"] == 0.95
    assert second["salidas"]["B1"]["estimaciones"]["primaria_60"]["remuestreos"] == p4.STANDARD_RESAMPLES


def test_e1_jamas_candidata() -> None:
    with pytest.raises(ValueError):
        p4.evaluate_candidate(_evidence("E1", bonferroni_lower=99.0))
    with pytest.raises(ValueError):
        p4.candidates_for_p5([p4.CandidateVerdict("E1", True, ())])
    with pytest.raises(ValueError):
        p4.candidate_evidence("E1", {}, {}, {})


def test_criterio_solo_admite_b2_s1_s2_y_varias_pasan() -> None:
    for gid in ("C0", "B1", "E1", "X"):
        with pytest.raises(ValueError):
            p4.evaluate_candidate(_evidence(gid))
    verdicts = [p4.evaluate_candidate(_evidence(gid)) for gid in p4.CANDIDATE_IDS]
    assert all(v.passes for v in verdicts)
    assert p4.candidates_for_p5(verdicts) == ("B2", "S1", "S2")  # todas, sin elegir un máximo
    failing = [p4.evaluate_candidate(_evidence(gid, bonferroni_lower=-0.01)) for gid in p4.CANDIDATE_IDS]
    assert p4.candidates_for_p5(failing) == ()  # ninguna → C0 permanece
    vetoing = {c.number for c in verdicts[0].conditions if c.vetoes}
    assert vetoing == {1, 2, 3, 5, 6, 8, 9, 10}
    for number, change in (
        (1, {"bonferroni_lower": 0.0}),
        (2, {"sensitivity_120_lower": -0.01}),
        (2, {"sensitivity_120_mean": -0.01}),
        (3, {"capacity_ok": False}),
        (5, {"conservative_bound_mean": -0.01}),
        (6, {"levels_coherent": False}),
        (8, {"second_half_mean": -0.01}),
        (10, {"level_profit_factor": 1.0}),
    ):
        verdict = p4.evaluate_candidate(_evidence("S1", **change))
        assert not verdict.passes and not verdict.conditions[number - 1].passed


def test_heterogeneidad_alta_no_cambia_pass_fail() -> None:
    for changes in ({}, {"bonferroni_lower": -0.1}, {"level_mean": -0.1}):
        low = p4.evaluate_candidate(_evidence("B2", heterogeneity="BAJA", **changes))
        high = p4.evaluate_candidate(_evidence("B2", heterogeneity="ALTA", **changes))
        assert low.passes == high.passes
        assert [(c.passed, c.vetoes) for c in low.conditions] == [(c.passed, c.vetoes) for c in high.conditions]
    condition = p4.evaluate_candidate(_evidence("B2", heterogeneity="ALTA")).conditions[3]
    assert condition.number == 4 and condition.vetoes is False and condition.passed is None


def test_ejecutabilidad_no_cambia_pass_fail() -> None:
    for changes in ({}, {"pairs": 1}):
        good = p4.evaluate_candidate(_evidence("S1", executability={ABOVE_MAX_ENTRY: 0.0}, **changes))
        bad = p4.evaluate_candidate(_evidence("S1", executability={ABOVE_MAX_ENTRY: 0.99}, **changes))
        assert good.passes == bad.passes
        assert [c.passed for c in good.conditions] == [c.passed for c in bad.conditions]
    condition = p4.evaluate_candidate(_evidence("S1")).conditions[6]
    assert condition.number == 7 and condition.vetoes is False


# --- 20-27. E1 ---------------------------------------------------------------------------


def _frame(rows: List[Tuple[float, float, float, float]], start: date = date(2024, 1, 1)) -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.Timestamp((start + timedelta(days=i)).isoformat(), tz="UTC") for i in range(len(rows))])
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=index)


def _e1(rows: List[Tuple[float, float, float, float]], levels: Optional[Levels] = None) -> p4.E1Outcome:
    levels = levels or _levels()
    return p4.simulate_e1_open_entry(
        _obs(), _frame(rows), levels, max_hold_bars=p4.MAX_HOLD_BARS, cost_pct=p4.COST_PCT, min_rr=1.5
    )


def test_e1_no_ejecutada_r0_y_conserva_signal_id() -> None:
    # C0 sin soporte: stop 96, target2 106, entry_max = P = 100. Apertura 101 > 100.
    outcome = _e1([(100, 100, 100, 100), (101, 103, 100.5, 102)])
    assert outcome.entry_category == ABOVE_MAX_ENTRY and outcome.status == "NO_EJECUTADA_ABOVE_MAX_ENTRY"
    assert outcome.net_r == 0.0 and outcome.managed is None
    assert outcome.signal_id == _obs().signal_id
    for open_, code in ((95.0, INVALID_STOP), (107.0, INVALID_TARGET)):
        other = _e1([(100, 100, 100, 100), (open_, open_, open_, open_)])
        assert other.entry_category == code and other.net_r == 0.0


def test_e1_conserva_el_signal_id_en_el_pareado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(p4, "BONFERRONI_RESAMPLES", 50)
    population = _synthetic_population()
    control = {s.signal_id: _managed(s.observation, 0.3) for s in population.signals}
    outcomes = {
        s.signal_id: p4.E1Outcome(s.signal_id, ABOVE_MAX_ENTRY, "NO_EJECUTADA_ABOVE_MAX_ENTRY", 0.0, 101.0, None)
        for s in population.signals
    }
    result = p4.analyze_e1(population, control, outcomes)
    primary = result["estimaciones"]["primaria_60"]
    assert primary["n_pares"] == len(population.signals)
    assert primary["media_delta_r"] == pytest.approx(-0.3)
    assert result["categorias_open_t1"][ABOVE_MAX_ENTRY] == len(population.signals)


def test_orden_de_categorias_como_produccion() -> None:
    weird = replace(_levels(), stop=100.0, target2=99.0, entry_max=98.0)
    assert p4.classify_open_entry(weird, 99.5, 1.5) == INVALID_STOP  # también ≥ target2 y > entry_max
    weird = replace(_levels(), stop=90.0, target2=99.0, entry_max=98.0)
    assert p4.classify_open_entry(weird, 101.0, 1.5) == INVALID_TARGET  # también > entry_max
    assert p4.classify_open_entry(weird, 98.5, 1.5) == ABOVE_MAX_ENTRY
    risk, portfolio = RiskConfig(), PortfolioConfig(capital=10_000.0)
    for geometry in p4.GEOMETRIES:
        for low in (None, 97.0, 99.0):
            levels = _levels(geometry, low=low)
            for open_ in (90.0, levels.stop, levels.stop + 0.01, 99.0, levels.entry_max, levels.entry_max + 0.3,
                          levels.target2 - 0.01, levels.target2, 120.0):
                ours = p4.classify_open_entry(levels, open_, geometry.min_rr)
                theirs = evaluate_trade_at_entry(
                    levels=levels, entry_price=open_, risk=risk, portfolio=portfolio, label="OPERAR"
                ).reason
                if theirs in (INVALID_STOP, INVALID_TARGET, ABOVE_MAX_ENTRY, RR_TOO_LOW):
                    assert ours == theirs, (geometry.gid, low, open_)
                else:
                    assert ours == EXECUTABLE, (geometry.gid, low, open_, theirs)


def test_rr_too_low_inalcanzable_tras_las_tres_comprobaciones_en_c0() -> None:
    rng = random.Random(3)
    for _ in range(3000):
        price = rng.uniform(1, 5000)
        atr = price * rng.uniform(0.002, 0.2)
        low = price - atr * rng.uniform(0.0, 2.5) if rng.random() < 0.5 else None
        high = price + atr * rng.uniform(0.0, 2.0) if rng.random() < 0.5 else None
        levels = _levels(p4.C0, price=price, atr=atr, low=low, high=high)
        for open_ in (
            levels.entry_max, levels.price, levels.stop * (1 + 1e-12),
            rng.uniform(levels.stop, levels.entry_max), levels.entry_max * (1 + 1e-12),
        ):
            assert p4.classify_open_entry(levels, open_, 1.5) != RR_TOO_LOW


def test_isclose_en_entry_max() -> None:
    levels = _levels()  # C0 sin soporte: entry_max = P
    assert p4.classify_open_entry(levels, levels.entry_max * (1 + 1e-12), 1.5) == EXECUTABLE
    assert p4.classify_open_entry(levels, levels.entry_max * (1 + 1e-6), 1.5) == ABOVE_MAX_ENTRY
    assert p4.classify_open_entry(levels, levels.entry_max, 1.5) == EXECUTABLE


def test_e1_ejecutada_usa_open_t1_mismos_niveles_y_barras() -> None:
    # C0 con soporte a 97: stop 96,5, target2 106 y entry_max = (106 + 1,5·96,5)/2,5 = 100,3 > P.
    levels = _levels(low=97.0)
    assert levels.stop == pytest.approx(96.5) and levels.entry_max == pytest.approx(100.3)
    rows = [(100, 100, 100, 100), (100.2, 101, 100, 100.8)] + [(101, 101.5, 100.5, 101)] * 45
    outcome = _e1(rows, levels)
    assert outcome.entry_category == EXECUTABLE and outcome.entry_price == 100.2
    event = outcome.managed
    assert event is not None
    assert (event.entry_price, event.stop, event.target) == (100.2, levels.stop, levels.target2)
    assert event.exit_status == TIME_EXIT and event.exit_idx == p4.MAX_HOLD_BARS  # t+1 … t+40
    expected = ((101 / 100.2 - 1) * 100 - 0.2) / ((100.2 - 96.5) / 100.2 * 100)
    assert outcome.net_r == pytest.approx(expected)
    # Objetivo tocado más tarde: sale a target2 con el riesgo E − stop.
    rows_target = [(100, 100, 100, 100), (100.2, 101, 100, 100.8), (101, 106.5, 100.5, 106)]
    hit = _e1(rows_target + [(106, 107, 105, 106)] * 40, levels)
    assert hit.status == TARGET_FIRST
    assert hit.net_r == pytest.approx(((106 / 100.2 - 1) * 100 - 0.2) / ((100.2 - 96.5) / 100.2 * 100))
    # Serie que se acaba antes de t+40: FINAL.
    short = _e1([(100, 100, 100, 100), (100.2, 101, 100, 100.8), (101, 101.5, 100.5, 101)], levels)
    assert short.status == FINAL_EXIT


def test_e1_barra_de_entrada_ambigua() -> None:
    outcome = _e1([(100, 100, 100, 100), (99.0, 107.0, 95.0, 100.0)] + [(100, 101, 99, 100)] * 40)
    assert outcome.entry_category == EXECUTABLE
    assert outcome.status == AMBIGUOUS and outcome.net_r is None
    stopped = _e1([(100, 100, 100, 100), (99.0, 100.0, 95.0, 96.5)] + [(100, 101, 99, 100)] * 40)
    assert stopped.status == STOP_FIRST and stopped.managed is not None and stopped.managed.exit_idx == 1


def _alta_population() -> p4.P4Population:
    signals = []
    for i in range(120, len(SPINE)):
        signals.append(_p4_signal(_obs(day=SPINE[i]), i))
    return _population(signals)


def test_e1_una_sola_comparacion_sin_estratos_cotas_mitades_ni_sensibilidad(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(p4, "BONFERRONI_RESAMPLES", 200)
    population = _alta_population()
    # Media muy distinta por bloque y constante dentro: heterogeneidad ALTA.
    control = {s.signal_id: _managed(s.observation, 0.0) for s in population.signals}
    outcomes = {
        s.signal_id: p4.E1Outcome(s.signal_id, EXECUTABLE, TARGET_FIRST, float(s.blocks[60] % 5), 100.0, None)
        for s in population.signals
    }
    result = p4.analyze_e1(population, control, outcomes)
    assert result["estimaciones"]["primaria_60"]["heterogeneidad"] == "ALTA"
    assert set(result["estimaciones"]) == {"primaria_60"}
    primary = result["estimaciones"]["primaria_60"]
    assert primary["confirmatoria"] is True and primary["ic_nivel"] == 0.9875 and primary["block_length"] == 60
    for forbidden_key in ("bloque_120", "regiones", "mitades", "nivel", "cota_conservadora", "activos", "stop_basis"):
        assert forbidden_key not in result["estimaciones"]
    assert result["eligible_for_p5"] is False
    assert result["lectura"] in (p4.E1_WINS, p4.E1_LOSES, p4.E1_INCONCLUSIVE)


def test_lectura_de_e1() -> None:
    def fake(lower: float, upper: float) -> Any:
        return type("R", (), {"ci_lower": lower, "ci_upper": upper})()

    assert p4.e1_reading(fake(0.01, 0.2), True) == "GANA"
    assert p4.e1_reading(fake(-0.2, -0.01), True) == "PIERDE"
    assert p4.e1_reading(fake(-0.1, 0.1), True) == "NO CONCLUYENTE"
    assert p4.e1_reading(fake(0.01, 0.2), False) == "NO CONCLUYENTE"  # capacidad
    assert p4.e1_reading(None, True) == "NO CONCLUYENTE"


# --- 28-33. ambigüedad, holgura, terciles, mitades, pares, nivel -----------------------


def test_cotas_de_ambiguedad_geometrica() -> None:
    obs = _obs()
    signal = _p4_signal(obs, 130)
    control = {obs.signal_id: _managed(obs, None, AMBIGUOUS, stop=96.0, target=106.0, exit_idx=4)}
    variant = {obs.signal_id: _managed(obs, None, AMBIGUOUS, stop=97.0, target=104.5, exit_idx=4)}
    by_id = {obs.signal_id: signal}
    economics = event_study.event_economics
    conservative = p4.ambiguity_bound_deltas(control, variant, by_id, "conservadora")[0]
    assert conservative.net_r_b == pytest.approx(economics(100.0, 97.0, 97.0, 0.2).net_r_multiple)  # V a stop
    assert conservative.net_r_a == pytest.approx(economics(100.0, 96.0, 106.0, 0.2).net_r_multiple)  # C0 a objetivo
    favorable = p4.ambiguity_bound_deltas(control, variant, by_id, "favorable")[0]
    assert favorable.net_r_b == pytest.approx(economics(100.0, 97.0, 104.5, 0.2).net_r_multiple)
    assert favorable.net_r_a == pytest.approx(economics(100.0, 96.0, 96.0, 0.2).net_r_multiple)
    assert conservative.delta_r < 0 < favorable.delta_r
    observable = {obs.signal_id: _managed(obs, 0.5)}
    assert p4.ambiguity_bound_deltas(observable, variant, by_id, "favorable")[0].net_r_a == 0.5
    with pytest.raises(ValueError):
        p4.ambiguity_bound_deltas(control, variant, by_id, "otra")


def test_holgura_d06_y_que_manda() -> None:
    opens = [95.0, 107.0, 100.5, 100.0, 99.0]
    signals = [_p4_signal(_obs(day=SPINE[130 + i]), 130 + i, next_open=o) for i, o in enumerate(opens)]
    population = _population(signals)
    levels = p4.levels_by_geometry(population, BASE)
    c0 = p4.entry_slack(population, p4.C0, levels["C0"])["GLOBAL"]
    assert c0["categoria_open_t1"] == {INVALID_STOP: 1, INVALID_TARGET: 1, ABOVE_MAX_ENTRY: 1, RR_TOO_LOW: 0, EXECUTABLE: 2}
    assert c0["manda"] == {p4.BINDING_RR: 5, p4.BINDING_TECHNICAL: 0, p4.BINDING_TIE: 0}
    assert c0["holgura"]["efectiva_atr"]["p50"] == pytest.approx(0.0, abs=1e-12)
    assert c0["distancia_above_max_entry_atr"]["p50"] == pytest.approx(0.25)  # (100,5 − 100)/2
    b2 = p4.entry_slack(population, p4.B2, levels["B2"])["GLOBAL"]
    assert b2["manda"][p4.BINDING_TIE] == 5  # 0,75·A exacto: empate declarado con isclose
    assert b2["holgura"]["rr_atr"]["p50"] == pytest.approx(0.75)
    # B2: entry_max = P + 0,75·A = 101,5 y target2 = 109,75; solo la apertura a 107 queda por encima.
    assert b2["categoria_open_t1"] == {INVALID_STOP: 1, INVALID_TARGET: 0, ABOVE_MAX_ENTRY: 1, RR_TOO_LOW: 0, EXECUTABLE: 3}
    assert "region:USA" in p4.entry_slack(population, p4.C0, levels["C0"])


def test_terciles_nearest_rank() -> None:
    assert p4.tercile_cuts([float(v) for v in range(1, 10)]) == (3.0, 6.0)
    assert p4.tercile_cuts([float(v) for v in range(1, 11)]) == (4.0, 7.0)  # ⌈10/3⌉−1 = 3, ⌈20/3⌉−1 = 6
    assert p4.tercile_index(1, 1) == 0 and p4.tercile_index(2, 1) == 0
    assert p4.tercile_of(2.9, (3.0, 6.0)) == "T1"
    assert p4.tercile_of(3.0, (3.0, 6.0)) == "T2"  # igual a un corte sube
    assert p4.tercile_of(6.0, (3.0, 6.0)) == "T3"
    with pytest.raises(ValueError):
        p4.tercile_index(3, 10)


def _fabricated_outputs(
    population: p4.P4Population,
    delta: Any,
    *,
    b1_delta: Any = None,
) -> Dict[str, Any]:
    """Salidas completas de las cuatro variantes y E1 con desenlaces fabricados."""

    levels = p4.levels_by_geometry(population, BASE)
    cuts = p4.tercile_cuts([s.atr_ratio for s in population.signals])
    control = {s.signal_id: _managed(s.observation, 0.1) for s in population.signals}
    potentials = {s.signal_id: _potential(s.observation) for s in population.signals}
    outputs: Dict[str, Any] = {}
    for geometry in p4.VARIANTS:
        fn = b1_delta if (geometry.gid == "B1" and b1_delta is not None) else delta
        events = {s.signal_id: _managed(s.observation, 0.1 + fn(s)) for s in population.signals}
        outputs[geometry.gid] = p4.analyze_variant(
            geometry, population, control, events, (), potentials, potentials, cuts, levels["C0"], levels[geometry.gid]
        )
    outcomes = {s.signal_id: p4.E1Outcome(s.signal_id, EXECUTABLE, TARGET_FIRST, 0.1, 100.0, None) for s in population.signals}
    outputs[p4.E1_ID] = p4.analyze_e1(population, control, outcomes)
    return outputs


def _fake_preflight() -> Dict[str, Any]:
    return {
        "niveles": {gid: {"coherentes": True} for gid in ("C0", "B1", "B2", "S1", "S2")},
        "holgura_d06": {gid: {"GLOBAL": {"categoria_open_t1_fraccion": {}}} for gid in ("C0", "B1", "B2", "S1", "S2")},
        "recuento": {"total": 0, "componentes": {}},
    }


def test_robustez_interna_usa_bloques_2_11_y_12_21(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(p4, "STANDARD_RESAMPLES", 50)
    monkeypatch.setattr(p4, "BONFERRONI_RESAMPLES", 50)
    assert tuple(range(2, 12)) == p4.FIRST_HALF_BLOCKS and tuple(range(12, 22)) == p4.SECOND_HALF_BLOCKS
    population = _synthetic_population()
    outputs = _fabricated_outputs(population, lambda s: 1.0 if s.blocks[60] <= 11 else -1.0)
    halves = outputs["S1"]["estimaciones"]["mitades"]
    assert halves["bloques_2_11"]["media_delta_r"] == pytest.approx(1.0)
    assert halves["bloques_12_21"]["media_delta_r"] == pytest.approx(-1.0)
    assert halves["bloques_2_11"]["papel"] == "robustez temporal interna sobre datos de desarrollo"
    assert "validación" not in json.dumps(halves, ensure_ascii=False).lower()
    evidence = p4.candidate_evidence("S1", outputs["S1"], {"coherentes": True}, {})
    assert evidence.first_half_mean == pytest.approx(1.0) and evidence.second_half_mean == pytest.approx(-1.0)
    assert not p4.evaluate_candidate(evidence).conditions[7].passed


def test_condicion_90_por_ciento_de_pares() -> None:
    threshold = math.ceil(0.9 * p4.EXPECTED_P4)
    assert p4.evaluate_candidate(_evidence("B2", pairs=threshold)).passes
    below = p4.evaluate_candidate(_evidence("B2", pairs=threshold - 1))
    assert not below.passes and below.conditions[8].passed is False


def test_condicion_nivel_mayor_que_cero_y_pf_mayor_que_uno() -> None:
    assert p4.evaluate_candidate(_evidence("S2", level_mean=0.001, level_profit_factor=1.001)).passes
    for change in ({"level_mean": 0.0}, {"level_mean": None}, {"level_profit_factor": 1.0}, {"level_profit_factor": None}):
        verdict = p4.evaluate_candidate(_evidence("S2", **change))
        assert not verdict.passes and verdict.conditions[9].passed is False
    assert p4.profit_factor([1.0, -0.5]) == 2.0 and p4.profit_factor([1.0]) == math.inf and p4.profit_factor([]) is None


# --- 34. recuento -------------------------------------------------------------------------


def _census_strata(assets: int = 90) -> Dict[str, Dict[str, Dict[str, int]]]:
    base = {
        "regiones": dict.fromkeys(p4.EXPECTED_REGIONS, 1),
        "regimenes": dict.fromkeys(p4.CALCULABLE_REGIMES, 1),
        "terciles": dict.fromkeys(p4.TERCILE_LABELS, 1),
        "activos": {f"A{i}": 1 for i in range(assets)},
        "stop_basis": {},
    }
    strata = {}
    for gid in ("B1", "B2", "S1", "S2"):
        strata[gid] = dict(base)
        if gid in p4.STOP_BASIS_GEOMETRIES:
            strata[gid] = {**base, "stop_basis": dict.fromkeys(p4.STOP_BASIS_PAIRS, 1)}
    return strata


def test_recuento_derivado_447_y_no_escrito_a_mano(monkeypatch: pytest.MonkeyPatch) -> None:
    planned = p4.planned_comparisons(_census_strata())
    assert planned["subtotales"] == {"B1": 110, "B2": 110, "S1": 113, "S2": 113, "E1": 1}
    assert planned["total"] == 447 and planned["confirmatorias"] == 4
    assert p4.planned_comparisons(_census_strata(assets=89))["total"] == 443  # deriva, no fija 447
    # El recuento real cuenta las estimaciones con IC de las salidas, con su propia ruta.
    monkeypatch.setattr(p4, "STANDARD_RESAMPLES", 30)
    monkeypatch.setattr(p4, "BONFERRONI_RESAMPLES", 30)
    population = _synthetic_population()
    outputs = _fabricated_outputs(population, lambda s: 0.05)
    derived = p4.derived_comparisons(outputs)
    # 3 regiones, 3 regímenes, 3 terciles, 4 activos y 3 pares de stop_basis en la población sintética.
    expected_b = 1 + 3 + 2 + 3 + 3 + 3 + 2 + 1 + 4
    stop_pairs = {g: len(outputs[g]["estimaciones"]["stop_basis"]) for g in ("S1", "S2")}
    assert derived["subtotales"] == {
        "B1": expected_b, "B2": expected_b,
        "S1": expected_b + stop_pairs["S1"], "S2": expected_b + stop_pairs["S2"], "E1": 1,
    }
    assert derived["confirmatorias"] == 4


# --- 35-37. preflight sin desenlaces y ejecución única ---------------------------------------


def _synthetic_vintage(n: int = 300) -> VintageLoad:
    sessions = expected_sessions("NYSE", date(2023, 1, 2), date(2024, 12, 31))[:n]
    rng = random.Random(11)
    rows = []
    close = 100.0
    for _ in sessions:
        open_ = close * (1 + rng.uniform(-0.01, 0.01))
        close = open_ * (1 + rng.uniform(-0.02, 0.025))
        rows.append((open_, max(open_, close) * 1.01, min(open_, close) * 0.99, close, 1_000_000))
    index = pd.DatetimeIndex([pd.Timestamp(d.isoformat(), tz="America/New_York").tz_convert("UTC") for d in sessions])
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"], index=index)
    views = VintageViews(raw=df, execution_prices=df, signal_prices=df, gap_for_catalyst=df)
    return VintageLoad(data_vintage_id="sintetica", manifest={}, by_symbol={"AAPL": views})


def test_enumeracion_sin_evaluadores_equivale_al_event_study() -> None:
    config = load_config("config.yaml")
    universe = load_universe(config.universe_path)
    vintage = _synthetic_vintage()
    full = event_study.run_event_study_on_vintage(config, universe, vintage, horizonte="swing", score_model_version="1.0")
    meta, enumerated = event_study.enumerate_event_signals_on_vintage(
        config, universe, vintage, horizonte="swing", score_model_version="1.0"
    )
    assert full.signals, "sin señales el test no probaría nada"
    assert [s.observation for s in full.signals] == [e.observation for e in enumerated]
    assert meta.signals == []
    assert (meta.evaluated_assets, meta.asset_bar_counts, meta.session_dates_by_asset, meta.skipped) == (
        full.evaluated_assets, full.asset_bar_counts, full.session_dates_by_asset, full.skipped,
    )
    for signal, item in zip(full.signals, enumerated):
        assert signal.managed.stop == item.levels.stop and signal.managed.target == item.levels.target2


def test_replay_cuenta_variantes_sin_niveles_y_el_original_sigue_abortando() -> None:
    obs_ok = _obs("AAPL", idx=0, day=date(2024, 1, 1))
    obs_bad = _obs("AAPL", idx=1, day=date(2024, 1, 2), atr=45.0)
    df = _frame([(100, 101, 99, 100)] * 50)
    signals = [
        EventStudySignal(observation=o, managed=_managed(o, 0.1), potential=_potential(o)) for o in (obs_ok, obs_bad)
    ]
    result = EventStudyResult(data_vintage_id="v", horizonte="swing", cost_pct=0.2, warmup_bars=0, max_hold_bars=40, signals=signals)
    vintage = VintageLoad(data_vintage_id="v", manifest={}, by_symbol={"AAPL": VintageViews(df, df, df, df)})
    counted = event_study.replay_managed_population_counting_missing(vintage=vintage, result=result,
                                                                    levels_config=p4.S2.levels_config(BASE), min_rr_ratio=1.5)
    assert set(counted.events) == {obs_ok.signal_id} and counted.without_levels == (obs_bad.signal_id,)
    with pytest.raises(ValueError, match="no produce niveles comparables"):
        event_study.replay_managed_population(result, vintage, p4.S2.levels_config(BASE), 1.5)
    c0 = event_study.replay_managed_population(result, vintage, p4.C0.levels_config(BASE), 1.5)
    assert set(c0) == {obs_ok.signal_id, obs_bad.signal_id}


def test_preflight_no_lee_desenlaces(monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_config("config.yaml")
    universe = load_universe(config.universe_path)
    vintage = _synthetic_vintage()
    _forbid_outcomes(monkeypatch)
    ident = p4.P4Identity("test", False, True, p4.EXPECTED_CONFIG_HASH, "1.0")
    # La población sintética no reproduce el censo: el preflight se para, pero termina sin leer desenlaces.
    ok, report = p4.run_preflight(config, universe, vintage, ident, write=False)
    assert not ok and "abortado" in report and report["outcomes_read"] is False
    population = p4.build_population(config, universe, vintage)
    assert population.signals
    sections, checks, levels = p4.compute_preflight_sections(population, config.levels)
    assert set(levels) == {"C0", "B1", "B2", "S1", "S2"}
    assert {"algebra", "niveles", "holgura_d06", "volatilidad", "estratos", "recuento"} <= set(sections)
    assert ("C0 recalculado = niveles de la enumeración", 0, 0, True) in checks


def _stored_preflight(path: Path, report: Dict[str, Any]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "p4-preflight.json").write_text(json.dumps(report), encoding="utf-8")


def _ok_report() -> Dict[str, Any]:
    return {
        "ok": True,
        "definitivo": True,
        "identidad": {"p4_executor_sha": "abc"},
        "poblacion": {"p4": 1, "p4_population_sha256": "pob", "signal_ids_sha256": "ids"},
        "bloques": {},
        "volatilidad": {"cortes_atr_sobre_precio": [0.01, 0.02]},
        "niveles": {},
        "recuento": {},
        "rejilla": {},
        "niveles_sha256": {"C0": "n0"},
    }


def test_marca_confirmatoria_antes_de_abrir_desenlaces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "run"
    monkeypatch.setattr(p4, "CONFIRMATORY_OUTPUT_DIR", run_dir)
    monkeypatch.setattr(p4, "PREFLIGHT_DIR", tmp_path / "preflight")
    _stored_preflight(tmp_path / "preflight", _ok_report())
    monkeypatch.setattr(p4, "executor_unchanged_since", lambda sha, repo: True)
    monkeypatch.setattr(p4, "_preflight", lambda *a, **k: (True, _ok_report(), "congelado"))
    seen: List[Dict[str, Any]] = []

    def spy(*args: Any, **kwargs: Any) -> Tuple[int, Dict[str, Any]]:
        assert (run_dir / p4.RUN_MARKER).exists()
        seen.append(json.loads((run_dir / p4.RUN_MARKER).read_text(encoding="utf-8")))
        assert args[-1] == "congelado"  # recibe lo congelado antes de la marca
        return 3, {"motivo": "parada de prueba"}

    monkeypatch.setattr(p4, "execute_with_outcomes", spy)
    ident = p4.P4Identity("abc", False, True, "h", "1.0")
    code, text = p4.run_confirmatory(None, None, None, ident, run_dir)  # type: ignore[arg-type]
    assert len(seen) == 1  # la marca existía antes de abrir ningún desenlace
    marker = seen[0]
    assert marker["p4_prereg_sha"] == p4.P4_PREREG_SHA
    assert marker["p4_executor_sha_preflight"] == "abc" and marker["head_sha"] == "abc"
    assert marker["p4_population_sha256"] == "pob" and marker["signal_ids_sha256"] == "ids"
    assert marker["niveles_sha256"] == {"C0": "n0"} and marker["cortes_terciles"] == [0.01, 0.02]
    assert marker["familia_confirmatoria"] == list(p4.CONFIRMATORY_FAMILY) and marker["seed"] == p4.SEED
    assert code == 3 and "OWNER_DECISION_REQUIRED" in text
    assert (run_dir / "p4-parada.json").exists()
    with pytest.raises(p4.P4AlreadyExecutedError):  # y ya no se repite
        p4.run_confirmatory(None, None, None, ident, run_dir)  # type: ignore[arg-type]


def test_confirmatoria_no_abre_desenlaces_si_el_preflight_no_coincide(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "run"
    monkeypatch.setattr(p4, "CONFIRMATORY_OUTPUT_DIR", run_dir)
    monkeypatch.setattr(p4, "PREFLIGHT_DIR", tmp_path / "preflight")
    _stored_preflight(tmp_path / "preflight", _ok_report())
    monkeypatch.setattr(p4, "executor_unchanged_since", lambda sha, repo: True)
    different = {**_ok_report(), "poblacion": {"p4": 2}}
    monkeypatch.setattr(p4, "_preflight", lambda *a, **k: (True, different, "congelado"))
    monkeypatch.setattr(p4, "execute_with_outcomes", forbidden)
    ident = p4.P4Identity("abc", False, True, "h", "1.0")
    code, _ = p4.run_confirmatory(None, None, None, ident, run_dir)  # type: ignore[arg-type]
    assert code == 2 and not (run_dir / p4.RUN_MARKER).exists()
    monkeypatch.setattr(p4, "executor_unchanged_since", lambda sha, repo: False)
    with pytest.raises(p4.P4PreflightError, match="ejecutor cambió"):
        p4.run_confirmatory(None, None, None, ident, run_dir)  # type: ignore[arg-type]
    _stored_preflight(tmp_path / "preflight", {**_ok_report(), "definitivo": False})
    with pytest.raises(p4.P4PreflightError, match="definitivo"):
        p4.run_confirmatory(None, None, None, ident, run_dir)  # type: ignore[arg-type]


def test_segunda_confirmatoria_se_niega_y_ruta_fija(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert Path("evidence/2026-10-01-T-020-p4/run") == p4.CONFIRMATORY_OUTPUT_DIR
    assert Path("evidence/2026-10-01-T-020-p4/preflight") == p4.PREFLIGHT_DIR
    ident = p4.P4Identity("abc", False, True, "h", "1.0")
    with pytest.raises(p4.P4PreflightError, match="solo escribe"):
        p4.run_confirmatory(None, None, None, ident, tmp_path / "otra")  # type: ignore[arg-type]
    run_dir = tmp_path / "run"
    monkeypatch.setattr(p4, "CONFIRMATORY_OUTPUT_DIR", run_dir)
    run_dir.mkdir()
    (run_dir / p4.RUN_MARKER).write_text("{}", encoding="utf-8")
    with pytest.raises(p4.P4AlreadyExecutedError):
        p4.run_confirmatory(None, None, None, ident, run_dir)  # type: ignore[arg-type]
    (run_dir / p4.RUN_MARKER).unlink()
    (run_dir / "algo.txt").write_text("x", encoding="utf-8")
    with pytest.raises(p4.P4AlreadyExecutedError):
        p4.run_confirmatory(None, None, None, ident, run_dir)  # type: ignore[arg-type]
    for dirty in (True, None):
        with pytest.raises(p4.P4PreflightError):
            p4.run_confirmatory(None, None, None, p4.P4Identity("abc", dirty, True, "h", "1.0"), run_dir)  # type: ignore[arg-type]
    with pytest.raises(p4.P4PreflightError, match="historia"):
        p4.run_confirmatory(None, None, None, p4.P4Identity("abc", False, False, "h", "1.0"), run_dir)  # type: ignore[arg-type]


# --- 38-39. producción y regresión ------------------------------------------------------


def test_produccion_y_config_intactas() -> None:
    config = load_config("config.yaml")
    assert config.scoring.score_model_version == "1.0"
    from advisor.run.manifest import config_hash

    assert config_hash(config) == p4.EXPECTED_CONFIG_HASH
    before = config.levels.model_dump()
    for geometry in p4.GEOMETRIES:
        geometry.levels_config(config.levels)
    assert config.levels.model_dump() == before
    assert p4.C0.levels_config(config.levels) == config.levels
    assert config.risk.min_rr_ratio == p4.C0.min_rr
    checks = p4.tree_checks(config, p4.P4Identity("x", False, True, config_hash(config), "1.0"))
    assert all(passed for *_, passed in checks)
    other = p4.tree_checks(config, p4.P4Identity("x", False, True, "otro", "1.0"))
    assert ("config_hash", "otro", p4.EXPECTED_CONFIG_HASH, False) in other


def test_la_cli_solo_expone_la_fase() -> None:
    from advisor.main import build_parser

    parser = build_parser()
    sub = next(a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction")
    p4_parser = sub.choices["p4"]  # type: ignore[attr-defined]
    options = {opt for action in p4_parser._actions for opt in action.option_strings}
    assert options == {"-h", "--help", "--fase"}
    fase = next(a for a in p4_parser._actions if "--fase" in a.option_strings)
    assert list(fase.choices) == ["preflight", "confirmatoria"]


def test_regresion_backtest_v1() -> None:
    """El backtest `--vintage` normalizado sigue en 866 operaciones y su hash (D-47)."""

    if not _cosecha_disponible():
        pytest.skip(f"falta {REAL_CSV}: la cosecha no está en esta máquina")
    import hashlib
    import re
    import subprocess
    import sys

    # Igual que el comando documentado: `… 2>&1 | sed 's/^[0-9-]* [0-9:]* //' | shasum -a 256`.
    completed = subprocess.run(
        [sys.executable, "-m", "advisor.main", "backtest", "--horizonte", "swing", "--vintage", p4.DATA_VINTAGE_ID],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=True,
    )
    text = completed.stdout
    normalized = "".join(re.sub(r"^[0-9-]* [0-9:]* ", "", line) + "\n" for line in text.splitlines())
    assert "866 operaciones" in text
    assert hashlib.sha256(normalized.encode()).hexdigest() == (
        "49b12c855c2d2681d9ecd0f592248cd03b11cd8428273014238e04f0ddefbc3c"
    )


# --- correcciones de la revisión independiente ----------------------------------------


def test_un_ejecutor_sin_seguimiento_ensucia_el_arbol(tmp_path: Path) -> None:
    import subprocess

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (tmp_path / "advisor").mkdir()
    (tmp_path / "advisor" / "a.py").write_text("x = 1\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "base")
    assert p4.tree_dirty(tmp_path) is False
    (tmp_path / "notas.txt").write_text("ajeno al ejecutor\n", encoding="utf-8")
    assert p4.tree_dirty(tmp_path) is False  # lo sin seguimiento fuera del ejecutor no cuenta
    (tmp_path / "advisor" / "p4.py").write_text("y = 2\n", encoding="utf-8")
    assert p4.tree_dirty(tmp_path) is True
    (tmp_path / "advisor" / "p4.py").unlink()
    (tmp_path / "advisor" / "a.py").write_text("x = 2\n", encoding="utf-8")
    assert p4.tree_dirty(tmp_path) is True


def test_el_preflight_no_se_reescribe_tras_la_ejecucion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / p4.RUN_MARKER).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(p4, "CONFIRMATORY_OUTPUT_DIR", run_dir)
    config = load_config("config.yaml")
    universe = load_universe(config.universe_path)
    ident = p4.P4Identity("test", False, True, p4.EXPECTED_CONFIG_HASH, "1.0")
    with pytest.raises(p4.P4AlreadyExecutedError):
        p4.run_preflight(config, universe, _synthetic_vintage(), ident, out_dir=tmp_path / "preflight")
    assert not (tmp_path / "preflight").exists()


def test_heterogeneidad_con_2000_y_bonferroni_con_20000(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(p4, "STANDARD_RESAMPLES", 40)
    monkeypatch.setattr(p4, "BONFERRONI_RESAMPLES", 60)
    population = _synthetic_population()
    outputs = _fabricated_outputs(population, lambda s: 0.1)
    for gid in ("B2", "S1", "S2", "E1"):
        primary = outputs[gid]["estimaciones"]["primaria_60"]
        assert primary["remuestreos"] == 60 and primary["ic_nivel"] == 0.9875
        assert primary["heterogeneidad_remuestreos"] == 40
    b1 = outputs["B1"]["estimaciones"]["primaria_60"]
    assert b1["remuestreos"] == 40 and b1["heterogeneidad_remuestreos"] == 40
    assert outputs["B2"]["emparejamiento"]["bloques_60_sin_pares"] == []


# --- checklist de la revisión de look-ahead ------------------------------------------


def _frozen_synthetic() -> Tuple[p4.FrozenRun, VintageLoad, Dict[str, Any]]:
    population = _synthetic_population()
    rng = random.Random(5)
    by_symbol = {}
    for asset in {s.asset for s in population.signals}:
        rows = []
        price = 100.0
        for _ in range(60):
            open_ = price * (1 + rng.uniform(-0.01, 0.01))
            price = open_ * (1 + rng.uniform(-0.03, 0.03))
            rows.append((open_, max(open_, price) * 1.01, min(open_, price) * 0.99, price))
        df = _frame(rows)
        by_symbol[asset] = VintageViews(df, df, df, df)
    vintage = VintageLoad(data_vintage_id=p4.DATA_VINTAGE_ID, manifest={}, by_symbol=by_symbol)
    levels = p4.levels_by_geometry(population, BASE)
    cuts = p4.tercile_cuts([s.atr_ratio for s in population.signals])
    preflight = {
        **_fake_preflight(),
        "niveles_sha256": {gid: p4.levels_sha256(values) for gid, values in levels.items()},
    }
    return p4.FrozenRun(population=population, levels=levels, cuts=cuts), vintage, preflight


def test_tras_la_marca_no_se_reconstruye_poblacion_ni_se_recalculan_niveles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(p4, "STANDARD_RESAMPLES", 30)
    monkeypatch.setattr(p4, "BONFERRONI_RESAMPLES", 30)
    frozen, vintage, preflight = _frozen_synthetic()
    for module, name in (
        (p4, "build_population"),
        (p4, "levels_by_geometry"),
        (p4, "geometry_levels"),
        (p4, "compute_levels_from_inputs"),
        (p4, "tercile_cuts"),
        (p4, "_preflight"),
        (event_study, "compute_levels_from_inputs"),
        (event_study, "run_event_study_on_vintage"),
        (event_study, "enumerate_event_signals_on_vintage"),
        (event_study, "replay_managed_population"),
        (event_study, "replay_managed_population_counting_missing"),
    ):
        monkeypatch.setattr(module, name, forbidden)
    ident = p4.P4Identity("abc", False, True, "h", "1.0")
    code, result = p4.execute_with_outcomes(vintage, ident, preflight, frozen)
    assert code == 0
    assert set(result["salidas"]) == {"B1", "B2", "S1", "S2", "E1"}
    assert [v["geometria"] for v in result["criterio"]] == ["B2", "S1", "S2"]
    for gid in ("B1", "B2", "S1", "S2"):
        assert result["salidas"][gid]["emparejamiento"]["senales_poblacion"] == len(frozen.population.signals)


def test_niveles_congelados_distintos_paran_la_ejecucion(monkeypatch: pytest.MonkeyPatch) -> None:
    frozen, vintage, preflight = _frozen_synthetic()
    preflight["niveles_sha256"]["S1"] = "otro"
    monkeypatch.setattr(p4, "evaluate_frozen", forbidden)
    code, result = p4.execute_with_outcomes(vintage, p4.P4Identity("abc", False, True, "h", "1.0"), preflight, frozen)
    assert code == 3 and "S1" in result["motivo"]


def test_huella_de_niveles_detecta_cualquier_cambio() -> None:
    signals = [_p4_signal(_obs(day=SPINE[130 + i]), 130 + i) for i in range(3)]
    levels = p4.levels_by_geometry(_population(signals), BASE)["C0"]
    base_hash = p4.levels_sha256(levels)
    first = signals[0].signal_id
    current = levels[first]
    assert current is not None
    assert p4.levels_sha256({**levels, first: replace(current, target2=current.target2 + 1e-9)}) != base_hash
    assert p4.levels_sha256({**levels, first: None}) != base_hash


def test_la_confirmatoria_no_admite_parametros_que_cambien_el_experimento() -> None:
    import inspect

    assert list(inspect.signature(p4.run_confirmatory).parameters) == ["config", "universe", "vintage", "ident", "out_dir"]
    assert list(inspect.signature(p4.execute_with_outcomes).parameters) == ["vintage", "ident", "preflight", "frozen"]
    source = inspect.getsource(p4.execute_with_outcomes) + inspect.getsource(p4.evaluate_frozen)
    for name in ("SEED", "CONFIRMATORY_FAMILY", "GEOMETRIES", "levels_config", "build_population"):
        assert f"{name} =" not in source


def test_el_preflight_declara_si_p4_ya_se_ejecuto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_config("config.yaml")
    universe = load_universe(config.universe_path)
    vintage = _synthetic_vintage()
    ident = p4.P4Identity("test", False, True, p4.EXPECTED_CONFIG_HASH, "1.0")
    run_dir = tmp_path / "run"
    monkeypatch.setattr(p4, "CONFIRMATORY_OUTPUT_DIR", run_dir)
    _, without = p4.run_preflight(config, universe, vintage, ident, write=False)
    assert without["p4_confirmatory_executed"] is False and without["outcomes_read"] is False
    run_dir.mkdir()
    (run_dir / p4.RUN_MARKER).write_text("{}", encoding="utf-8")
    _, with_marker = p4.run_preflight(config, universe, vintage, ident, write=False)
    assert with_marker["p4_confirmatory_executed"] is True and with_marker["outcomes_read"] is False
