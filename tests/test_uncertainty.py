"""Infraestructura P2.6 de incertidumbre por bloques."""

from __future__ import annotations

import os
import random
import subprocess
import sys
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from advisor.config import LevelsConfig, RiskConfig
from advisor.research.bootstrap import (
    HETEROGENEITY_HIGH,
    HETEROGENEITY_NOISE,
    HETEROGENEITY_NOT_ESTIMABLE,
    PairedDelta,
    _constant_effect_noise,
    bootstrap_block_delta,
    resample_blocks,
)
from advisor.research.event_study import (
    AMBIGUOUS,
    TARGET_FIRST,
    EventStudyResult,
    replay_managed_population,
)
from advisor.research.uncertainty import NO_CONCLUYENTE, format_paired_comparison, pair_populations
from advisor.research.vintage import VintageLoad, VintageViews
from tests.test_event_study import _df_for_status, _signal


def test_pareado_por_signal_id_y_no_por_posicion() -> None:
    a1 = _managed("A", net=1.0)
    a2 = _managed("B", net=2.0)
    b1 = _managed("A", net=1.5)
    b2 = _managed("B", net=1.8)

    paired = pair_populations({"A": a1, "B": a2}, {"B": b2, "A": b1})

    assert [delta.signal_id for delta in paired.deltas] == ["A", "B"]
    assert [delta.delta_r for delta in paired.deltas] == pytest.approx([0.5, -0.2])


def test_replay_managed_population_reproduce_mismos_niveles() -> None:
    signal = _signal(score=85.0, status=TARGET_FIRST)
    levels_config = LevelsConfig(target_atr_multiples=[1.5, 4.0, 5.0])
    result = EventStudyResult(
        data_vintage_id="vintage",
        horizonte="swing",
        cost_pct=0.2,
        warmup_bars=120,
        max_hold_bars=40,
        signals=[signal],
    )
    df = _df_for_status(TARGET_FIRST)
    vintage = VintageLoad(
        data_vintage_id="vintage",
        manifest={},
        by_symbol={"TEST": VintageViews(raw=df, execution_prices=df, signal_prices=df, gap_for_catalyst=df)},
    )

    replayed = replay_managed_population(result, vintage, levels_config, RiskConfig().min_rr_ratio)

    assert replayed[signal.observation.signal_id] == signal.managed


def test_replay_managed_population_aborta_con_cosecha_distinta() -> None:
    result = EventStudyResult(data_vintage_id="a", horizonte="swing", cost_pct=0.2, warmup_bars=120, max_hold_bars=40)
    vintage = VintageLoad(data_vintage_id="b", manifest={}, by_symbol={})

    with pytest.raises(ValueError, match="cosecha distinta"):
        replay_managed_population(result, vintage, LevelsConfig(), RiskConfig().min_rr_ratio)


def test_pareado_aborta_si_signal_ids_no_coinciden() -> None:
    with pytest.raises(ValueError, match="sobran_en_b=1; faltan_en_b=1"):
        pair_populations({"A": _managed("A", net=1.0)}, {"B": _managed("B", net=1.0)})


def test_delta_usa_net_r_y_no_gross_r() -> None:
    managed_a = _managed("A", net=1.0, gross=99.0)
    managed_b = _managed("A", net=1.2, gross=-99.0)

    paired = pair_populations({"A": managed_a}, {"A": managed_b})

    assert paired.deltas[0].delta_r == pytest.approx(0.2)


def test_ambiguos_descartados_y_contados_por_brazo() -> None:
    paired = pair_populations(
        {
            "ok": _managed("ok", net=1.0),
            "only_a": _managed("only_a", net=None),
            "only_b": _managed("only_b", net=1.0),
            "both": _managed("both", net=None),
        },
        {
            "ok": _managed("ok", net=1.1),
            "only_a": _managed("only_a", net=1.0),
            "only_b": _managed("only_b", net=None),
            "both": _managed("both", net=None),
        },
    )

    assert len(paired.deltas) == 1
    assert paired.dropped_only_a == 1
    assert paired.dropped_only_b == 1
    assert paired.dropped_both == 1
    assert paired.dropped_rate == pytest.approx(0.75)


def test_bloque_entra_entero_en_resample_y_media() -> None:
    rng = random.Random(7)
    indices = resample_blocks(4, rng)

    assert len(indices) == 4
    assert all(0 <= index < 4 for index in indices)
    means = [10.0, 20.0, 30.0, 40.0]
    reconstructed = sum(means[index] for index in indices) / len(indices)
    assert reconstructed in {sum(means[index] for index in indices) / 4}


def test_bootstrap_no_comprime_espina_de_sesiones_del_gate() -> None:
    start = date(2026, 1, 1)
    deltas = (
        PairedDelta("a", "A", start, 0.0, 0.1, 0.1),
        PairedDelta("b", "A", start + timedelta(days=9), 0.0, 0.2, 0.2),
    )
    compressed = bootstrap_block_delta(deltas, block_length=5, seed=1, n_resamples=20)
    full_spine = [start + timedelta(days=i) for i in range(10)]
    aligned = bootstrap_block_delta(deltas, block_length=5, seed=1, n_resamples=20, session_spine=full_spine)

    assert compressed.n_blocks == 1
    assert aligned.n_blocks == 2
    assert [block.block_index for block in aligned.blocks] == [0, 1]


def test_bootstrap_determinista_misma_semilla_bit_a_bit() -> None:
    deltas = _deltas()

    one = bootstrap_block_delta(deltas, block_length=5, seed=123, n_resamples=200)
    two = bootstrap_block_delta(deltas, block_length=5, seed=123, n_resamples=200)

    assert one == two


def test_bootstrap_semillas_distintas_cambian_intervalo() -> None:
    deltas = _deltas()

    one = bootstrap_block_delta(deltas, block_length=5, seed=123, n_resamples=200)
    two = bootstrap_block_delta(deltas, block_length=5, seed=456, n_resamples=200)

    assert (one.ci_lower, one.ci_upper) != (two.ci_lower, two.ci_upper)


def test_bootstrap_ordena_entrada_para_reproducibilidad() -> None:
    deltas = list(_deltas())
    shuffled = list(deltas)
    random.Random(1234).shuffle(shuffled)

    assert bootstrap_block_delta(deltas, block_length=5, seed=99, n_resamples=200) == bootstrap_block_delta(
        shuffled,
        block_length=5,
        seed=99,
        n_resamples=200,
    )


def test_seed_es_obligatoria() -> None:
    with pytest.raises(TypeError):
        bootstrap_block_delta(_deltas(), block_length=5)  # type: ignore[call-arg]


def test_pythonhashseed_no_cambia_salida() -> None:
    code = """
import json
from datetime import date, timedelta
from advisor.research.bootstrap import PairedDelta, bootstrap_block_delta
d=[]
for i in range(30):
    d.append(PairedDelta(f'id-{i}', 'A', date(2026,1,1)+timedelta(days=i), 0.0, (i % 7)/10, (i % 7)/10))
r=bootstrap_block_delta(d, block_length=5, seed=42, n_resamples=100)
print(json.dumps(r.__dict__, default=str, sort_keys=True))
"""
    env0 = {**os.environ, "PYTHONHASHSEED": "0"}
    env1 = {**os.environ, "PYTHONHASHSEED": "1"}
    out0 = subprocess.check_output([sys.executable, "-c", code], cwd=Path.cwd(), env=env0)
    out1 = subprocess.check_output([sys.executable, "-c", code], cwd=Path.cwd(), env=env1)

    assert out0 == out1


def test_heterogeneidad_compatible_con_ruido() -> None:
    result = bootstrap_block_delta(_constant_effect_deltas(), block_length=5, seed=11, n_resamples=300)

    assert result.heterogeneity == HETEROGENEITY_NOISE
    assert result.tau_excess_dispersion < 0.05


def test_heterogeneidad_alta_en_regimenes() -> None:
    deltas = []
    start = date(2026, 1, 1)
    for block in range(8):
        base = 0.5 if block < 4 else -0.3
        for offset in range(5):
            deltas.append(PairedDelta(f"{block}-{offset}", "A", start + timedelta(days=block * 5 + offset), 0.0, base, base))

    result = bootstrap_block_delta(deltas, block_length=5, seed=22, n_resamples=300)

    assert result.heterogeneity == HETEROGENEITY_HIGH
    assert result.observed_dispersion > result.noise_upper
    assert result.tau_excess_dispersion > 0.2


def test_heterogeneidad_no_estimable_con_menos_de_dos_bloques_o_una_sesion_por_bloque() -> None:
    one = bootstrap_block_delta(_deltas(n=3), block_length=10, seed=1, n_resamples=50)
    single_session_blocks = bootstrap_block_delta(_deltas(n=4), block_length=1, seed=1, n_resamples=50)

    assert one.heterogeneity == HETEROGENEITY_NOT_ESTIMABLE
    assert single_session_blocks.heterogeneity == HETEROGENEITY_NOT_ESTIMABLE


def test_etapa2_eficiente_equivale_a_ingenua() -> None:
    session_sums = [[(1.0, 2), (3.0, 2)], [(2.0, 2), (4.0, 2)]]
    block_means = [1.0, 1.5]
    efficient = _constant_effect_noise(session_sums, block_means, 1.25, random.Random(5), 25)
    naive = _constant_effect_noise(session_sums, block_means, 1.25, random.Random(5), 25)

    assert efficient == naive


def test_informe_no_concluyente_no_decide() -> None:
    from advisor.research.capacity import CapacityReport
    from tests.test_capacity import _result, _universe, _with_day

    signals = [_with_day(_signal(score=55.0, status=TARGET_FIRST), i) for i in range(20)]
    capacity = __import__("advisor.research.capacity", fromlist=["assess_capacity"]).assess_capacity(
        _result(signals),
        universe=_universe(),
    )
    population = pair_populations({"A": _managed("A", net=1.0)}, {"A": _managed("A", net=1.1)})
    comparison = __import__("advisor.research.uncertainty", fromlist=["PairedComparison"]).PairedComparison(
        data_vintage_id="vintage",
        horizonte="swing",
        cost_pct=0.2,
        label_a="A",
        label_b="B",
        levels_a={"target_atr_multiples": [1.5, 3.0, 5.0], "atr_stop_multiple": 2.0},
        levels_b={"target_atr_multiples": [1.5, 3.5, 5.0], "atr_stop_multiple": 2.0},
        population=population,
        capacity=capacity,
        estimators_a=__import__("advisor.research.capacity", fromlist=["PreregisteredEstimatorSummary"]).PreregisteredEstimatorSummary(
            block_length=60,
            n_blocks=1,
            n_observable=1,
            primary_block_expectancy_net_r=1.0,
            secondary_pooled_expectancy_net_r=1.0,
            secondary_pooled_target_first_rate=1.0,
            secondary_target_first_lower=1.0,
            secondary_target_first_upper=1.0,
        ),
        results=(bootstrap_block_delta(_deltas(n=20), block_length=5, seed=1, n_resamples=50),),
        conclusion_estable=True,
        verdict=NO_CONCLUYENTE,
        reasons=("capacidad P2.5 insuficiente",),
        comparaciones_publicadas=1,
    )
    assert isinstance(capacity, CapacityReport)

    report = format_paired_comparison(comparison)

    assert report.splitlines()[0] == "VEREDICTO: NO_CONCLUYENTE"
    assert "Materia prima (no concluyente, no utilizable en P4)" in report
    lowered = report.lower()
    assert "recomend" not in lowered
    assert "mejor" not in lowered
    assert "gana" not in lowered
    assert "elegir" not in lowered
    assert "mide" in lowered
    assert "ΔR > 0" in report


def _managed(signal_id: str, *, net: float | None, gross: float | None = None):
    signal = _signal(score=85.0, status=AMBIGUOUS if net is None else TARGET_FIRST)
    managed = signal.managed
    obs = replace(managed.observation, signal_id=signal_id)
    return replace(
        managed,
        observation=obs,
        net_r_multiple=net,
        gross_r_multiple=net if gross is None else gross,
        exit_price=None if net is None else managed.exit_price,
    )


def _deltas(n: int = 40) -> tuple[PairedDelta, ...]:
    start = date(2026, 1, 1)
    return tuple(
        PairedDelta(
            signal_id=f"id-{i}",
            asset="A" if i % 2 else "B",
            session=start + timedelta(days=i),
            net_r_a=0.0,
            net_r_b=((i * 17) % 11 - 5) / 20,
            delta_r=((i * 17) % 11 - 5) / 20,
        )
        for i in range(n)
    )


def _constant_effect_deltas() -> tuple[PairedDelta, ...]:
    start = date(2026, 1, 1)
    deltas = []
    for block in range(8):
        base = 0.1 + ((block % 3) - 1) * 0.1
        for offset in range(5):
            value = base + ((offset % 5) - 2) * 0.2
            deltas.append(PairedDelta(f"{block}-{offset}", "A", start + timedelta(days=block * 5 + offset), 0.0, value, value))
    return tuple(deltas)
