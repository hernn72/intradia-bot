"""Orquestación P2.6: comparación pareada con bootstrap por bloques."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Sequence, Tuple

from advisor.config import AdvisorConfig, LevelsConfig
from advisor.research.bootstrap import (
    DEFAULT_RESAMPLES,
    DEFAULT_SEED,
    HETEROGENEITY_NOT_ESTIMABLE,
    BlockBootstrapResult,
    PairedDelta,
    bootstrap_block_delta,
)
from advisor.research.capacity import (
    DEFAULT_THRESHOLDS,
    INSUFICIENTE,
    CapacityReport,
    PreregisteredEstimatorSummary,
    TemporalBlockMap,
    _temporal_block_lookup,
    assess_capacity,
    format_preregistered_estimators,
    preregistered_estimators,
)
from advisor.research.event_study import (
    FINAL_EXIT,
    EventStudyResult,
    ManagedEvent,
    replay_managed_population,
    run_event_study_on_vintage,
)
from advisor.research.vintage import load_vintage
from advisor.universe.models import Universe

CONCLUYENTE = "CONCLUYENTE"
SENSIBLE_A_LA_LONGITUD = "SENSIBLE_A_LA_LONGITUD"
NO_CONCLUYENTE = "NO_CONCLUYENTE"


@dataclass(frozen=True)
class PairedPopulation:
    deltas: Tuple[PairedDelta, ...]
    n_signals: int
    dropped_only_a: int
    dropped_only_b: int
    dropped_both: int
    dropped_rate: float
    exit_final_rate_a: float
    exit_final_rate_b: float


@dataclass(frozen=True)
class PairedComparison:
    data_vintage_id: str
    horizonte: str
    cost_pct: float
    label_a: str
    label_b: str
    levels_a: Dict[str, object]
    levels_b: Dict[str, object]
    population: PairedPopulation
    capacity: CapacityReport
    estimators_a: PreregisteredEstimatorSummary
    results: Tuple[BlockBootstrapResult, ...]
    conclusion_estable: bool
    verdict: str
    reasons: Tuple[str, ...]
    comparaciones_publicadas: int
    universe_vintage_id: str = ""


def pair_populations(
    population_a: Mapping[str, ManagedEvent],
    population_b: Mapping[str, ManagedEvent],
) -> PairedPopulation:
    """Empareja por signal_id y calcula ΔR neto B - A."""

    ids_a = list(population_a.keys())
    ids_b = set(population_b.keys())
    extra_b = len(ids_b - set(ids_a))
    missing_b = len(set(ids_a) - ids_b)
    if extra_b or missing_b:
        raise ValueError(f"signal_id descuadrados: sobran_en_b={extra_b}; faltan_en_b={missing_b}")

    deltas: List[PairedDelta] = []
    dropped_only_a = 0
    dropped_only_b = 0
    dropped_both = 0
    for signal_id in ids_a:
        managed_a = population_a[signal_id]
        managed_b = population_b[signal_id]
        net_a = managed_a.net_r_multiple
        net_b = managed_b.net_r_multiple
        if net_a is None and net_b is None:
            dropped_both += 1
            continue
        if net_a is None:
            dropped_only_a += 1
            continue
        if net_b is None:
            dropped_only_b += 1
            continue
        deltas.append(
            PairedDelta(
                signal_id=signal_id,
                asset=managed_a.observation.asset,
                session=managed_a.observation.signal_timestamp.date(),
                net_r_a=net_a,
                net_r_b=net_b,
                delta_r=net_b - net_a,
            )
        )
    n_signals = len(ids_a)
    dropped_total = dropped_only_a + dropped_only_b + dropped_both
    return PairedPopulation(
        deltas=tuple(sorted(deltas, key=lambda item: (item.session, item.asset, item.signal_id))),
        n_signals=n_signals,
        dropped_only_a=dropped_only_a,
        dropped_only_b=dropped_only_b,
        dropped_both=dropped_both,
        dropped_rate=dropped_total / n_signals if n_signals else 0.0,
        exit_final_rate_a=_exit_final_rate(population_a.values()),
        exit_final_rate_b=_exit_final_rate(population_b.values()),
    )


def compare_target_geometry(
    config: AdvisorConfig,
    universe: Universe,
    data_vintage_id: str,
    *,
    horizonte: str = "swing",
    cost_pct: float = 0.2,
    root_dir: str = "data/vintages",
    target_multiples_b: Sequence[float] = (1.5, 3.5, 5.0),
    block_lengths: Sequence[int] = (40, 60, 80, 120),
    seed: int = DEFAULT_SEED,
    n_resamples: int = DEFAULT_RESAMPLES,
    mode: str = "replica",
) -> PairedComparison:
    """Mide A producción frente a B en memoria cambiando solo target_atr_multiples."""

    if mode not in {"replica", "completo"}:
        raise ValueError("modo debe ser 'replica' o 'completo'")
    levels_b = LevelsConfig(**{**config.levels.model_dump(), "target_atr_multiples": list(target_multiples_b)})
    if list(levels_b.target_atr_multiples) == list(config.levels.target_atr_multiples):
        raise ValueError("los múltiplos de B deben diferir de A")
    max_hold_bars = {"swing": 40, "medio": 250}.get(horizonte)
    if max_hold_bars is None:
        raise ValueError(f"horizonte no soportado en P2.6: {horizonte}")
    _validate_block_lengths(horizonte, max_hold_bars, block_lengths)

    vintage = load_vintage(data_vintage_id, root_dir=root_dir)
    result_a = run_event_study_on_vintage(config, universe, vintage, horizonte=horizonte, cost_pct=cost_pct)
    capacity = assess_capacity(result_a, universe=universe)
    population_a = {signal.observation.signal_id: signal.managed for signal in result_a.signals}
    if mode == "replica":
        population_b = replay_managed_population(result_a, vintage, levels_b, config.risk.min_rr_ratio, cost_pct=cost_pct)
    else:
        config_b = config.model_copy(update={"levels": levels_b})
        result_b = run_event_study_on_vintage(config_b, universe, vintage, horizonte=horizonte, cost_pct=cost_pct)
        population_b = {signal.observation.signal_id: signal.managed for signal in result_b.signals}

    temporal_blocks = _temporal_block_lookup(result_a, result_a.max_hold_bars + 1, universe)
    paired = pair_populations(population_a, population_b)
    paired = _with_capacity_sessions(paired, result_a, temporal_blocks)
    results = tuple(
        _with_overlap(
            bootstrap_block_delta(
                paired.deltas,
                block_length=length,
                seed=seed,
                n_resamples=n_resamples,
                confidence=0.95,
                session_spine=temporal_blocks.session_spine,
            ),
            length <= result_a.max_hold_bars,
        )
        for length in block_lengths
    )
    conclusion_estable = _stable_intervals(results)
    verdict, reasons = _comparison_verdict(capacity, paired, results, conclusion_estable)
    return PairedComparison(
        data_vintage_id=data_vintage_id,
        universe_vintage_id=result_a.universe_vintage_id,
        horizonte=horizonte,
        cost_pct=cost_pct,
        label_a="A producción",
        label_b="B opción B target2=3.5 ATR",
        levels_a=config.levels.model_dump(),
        levels_b=levels_b.model_dump(),
        population=paired,
        capacity=capacity,
        estimators_a=preregistered_estimators(result_a, universe=universe),
        results=results,
        conclusion_estable=conclusion_estable,
        verdict=verdict,
        reasons=tuple(reasons),
        comparaciones_publicadas=len(results),
    )


def format_paired_comparison(comparison: PairedComparison) -> str:
    """Informe textual: mide P2.6, no decide geometría."""

    raw_header = "Materia prima"
    if comparison.verdict == NO_CONCLUYENTE:
        raw_header = "Materia prima (no concluyente, no utilizable en P4)"
    first = comparison.results[0] if comparison.results else None
    lines = [
        f"VEREDICTO: {comparison.verdict}",
        f"Motivos: {list(comparison.reasons)}",
        "P2.6 mide incertidumbre; no decide ni adopta geometría. config.yaml no se modifica.",
        "Convención: ΔR > 0 significa que B obtuvo más R neto que A sobre las mismas señales.",
        f"data_vintage_id={comparison.data_vintage_id}",
        f"universe_vintage_id={comparison.universe_vintage_id}",
        f"horizonte={comparison.horizonte}; cost_pct={comparison.cost_pct:g}",
        f"A target_atr_multiples={comparison.levels_a['target_atr_multiples']}; atr_stop_multiple={comparison.levels_a['atr_stop_multiple']}",
        f"B target_atr_multiples={comparison.levels_b['target_atr_multiples']}; atr_stop_multiple={comparison.levels_b['atr_stop_multiple']}",
        f"semilla={first.seed if first else DEFAULT_SEED}; seed_ci={first.seed_ci if first else 'N/D'}; seed_het={first.seed_het if first else 'N/D'}; remuestreos={first.n_resamples if first else 0}",
        f"longitudes_bloque={[result.block_length for result in comparison.results]}",
        f"pares={comparison.population.n_signals}; usados={len(comparison.population.deltas)}; "
        f"descartados_only_a={comparison.population.dropped_only_a}; "
        f"descartados_only_b={comparison.population.dropped_only_b}; "
        f"descartados_both={comparison.population.dropped_both}; "
        f"tasa_descartes={comparison.population.dropped_rate:.3f}",
        f"EXIT_FINAL_A={comparison.population.exit_final_rate_a:.3f}; EXIT_FINAL_B={comparison.population.exit_final_rate_b:.3f}",
        f"Capacidad P2.5 global: {comparison.capacity.global_summary.verdict}; "
        f"n_blocks={comparison.capacity.global_summary.n_blocks}; "
        f"resolution={comparison.capacity.global_summary.resolution}; "
        f"reasons={list(comparison.capacity.global_summary.reasons)}",
        format_preregistered_estimators(comparison.estimators_a),
        f"comparaciones_publicadas=1 par de políticas x {len(comparison.results)} longitudes de bloque = {comparison.comparaciones_publicadas} filas",
        "La réplica conserva las señales y las bandas de score de A; solo reevalúa niveles administrados.",
        "",
        raw_header,
        "Bloque  n_bloques  n_min  ΔR medio  ΔR pooled  IC bloque          Dispersión  Esperada por ruido  Heterogeneidad",
    ]
    for result in comparison.results:
        marker = "*" if result.overlaps_holding_period else " "
        n_min = min((block.n for block in result.blocks), default=0)
        lines.append(
            f"{result.block_length:<6}{marker} {result.n_blocks:>9} {n_min:>6} "
            f"{_fmt_signed(result.mean_delta_r):>9} {_fmt_signed(result.pooled_mean_delta_r):>10} "
            f"[{_fmt_signed(result.ci_lower)}, {_fmt_signed(result.ci_upper)}] "
            f"{result.observed_dispersion:>11.3f} "
            f"[{result.noise_lower:.3f}, {result.noise_upper:.3f}] "
            f"{_het_label(result.heterogeneity)}"
        )
    if any(result.overlaps_holding_period for result in comparison.results):
        lines.append("(*) La longitud no supera MAX_HOLD_BARS; se publica por sensibilidad y queda marcada.")
    return "\n".join(lines)


def _with_capacity_sessions(
    paired: PairedPopulation,
    result: EventStudyResult,
    block_lookup: TemporalBlockMap,
) -> PairedPopulation:
    signal_by_id = {signal.observation.signal_id: signal for signal in result.signals}
    remapped = [
        PairedDelta(
            signal_id=delta.signal_id,
            asset=delta.asset,
            session=block_lookup.effective_session_date(signal_by_id[delta.signal_id]),
            net_r_a=delta.net_r_a,
            net_r_b=delta.net_r_b,
            delta_r=delta.delta_r,
        )
        for delta in paired.deltas
    ]
    return PairedPopulation(
        deltas=tuple(sorted(remapped, key=lambda item: (item.session, item.asset, item.signal_id))),
        n_signals=paired.n_signals,
        dropped_only_a=paired.dropped_only_a,
        dropped_only_b=paired.dropped_only_b,
        dropped_both=paired.dropped_both,
        dropped_rate=paired.dropped_rate,
        exit_final_rate_a=paired.exit_final_rate_a,
        exit_final_rate_b=paired.exit_final_rate_b,
    )


def _with_overlap(result: BlockBootstrapResult, overlaps: bool) -> BlockBootstrapResult:
    return BlockBootstrapResult(**{**result.__dict__, "overlaps_holding_period": overlaps})


def _validate_block_lengths(horizonte: str, max_hold_bars: int, block_lengths: Sequence[int]) -> None:
    if horizonte == "medio":
        invalid = [length for length in block_lengths if length <= max_hold_bars]
        if invalid:
            raise ValueError(f"longitudes inválidas para medio: {invalid} <= MAX_HOLD_BARS {max_hold_bars}")


def _stable_intervals(results: Sequence[BlockBootstrapResult]) -> bool:
    if not results:
        return False
    signs = []
    for result in results:
        if result.ci_lower > 0:
            signs.append(1)
        elif result.ci_upper < 0:
            signs.append(-1)
        else:
            signs.append(0)
    return all(sign == signs[0] for sign in signs)


def _comparison_verdict(
    capacity: CapacityReport,
    population: PairedPopulation,
    results: Sequence[BlockBootstrapResult],
    conclusion_estable: bool,
) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    thresholds = DEFAULT_THRESHOLDS
    if capacity.global_summary.verdict == INSUFICIENTE:
        reasons.append("capacidad P2.5 insuficiente")
        reasons.extend(capacity.global_summary.reasons)
    if any(result.n_blocks < thresholds.limited_blocks for result in results):
        reasons.append(f"alguna longitud tiene bloques < {thresholds.limited_blocks}")
    if any(min((block.n for block in result.blocks), default=0) < thresholds.min_observations_per_block for result in results):
        reasons.append(f"alguna longitud tiene bloque mínimo < {thresholds.min_observations_per_block}")
    if population.dropped_rate > thresholds.max_ambiguous_rate:
        reasons.append(f"descartes ambiguos {population.dropped_rate:.1%} > {thresholds.max_ambiguous_rate:.1%}")
    if population.exit_final_rate_a > thresholds.max_exit_final_rate:
        reasons.append(f"EXIT_FINAL A {population.exit_final_rate_a:.1%} > {thresholds.max_exit_final_rate:.1%}")
    if population.exit_final_rate_b > thresholds.max_exit_final_rate:
        reasons.append(f"EXIT_FINAL B {population.exit_final_rate_b:.1%} > {thresholds.max_exit_final_rate:.1%}")
    if any(result.heterogeneity == HETEROGENEITY_NOT_ESTIMABLE for result in results):
        reasons.append("heterogeneidad no estimable")
    if reasons:
        return NO_CONCLUYENTE, reasons
    if not conclusion_estable:
        return SENSIBLE_A_LA_LONGITUD, ["sensibilidad a la longitud de bloque"]
    return CONCLUYENTE, []


def _exit_final_rate(events) -> float:
    values = list(events)
    return sum(1 for event in values if event.exit_status == FINAL_EXIT) / len(values) if values else 0.0


def _fmt_signed(value: float) -> str:
    return f"{value:+.3f}"


def _het_label(value: str) -> str:
    return value.lower().replace("_", " ")
