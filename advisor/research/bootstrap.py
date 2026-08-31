"""Bootstrap por bloques temporales completos para P2.6.

Núcleo puro y determinista: no conoce configuración, pandas ni I/O.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Sequence, Tuple

DEFAULT_SEED = 20260830
DEFAULT_RESAMPLES = 2000

HETEROGENEITY_LOW = "BAJA"
HETEROGENEITY_NOISE = "COMPATIBLE_CON_RUIDO"
HETEROGENEITY_HIGH = "ALTA"
HETEROGENEITY_NOT_ESTIMABLE = "NO_ESTIMABLE"


@dataclass(frozen=True)
class PairedDelta:
    signal_id: str
    asset: str
    session: date
    net_r_a: float
    net_r_b: float
    delta_r: float


@dataclass(frozen=True)
class BlockDelta:
    block_index: int
    first_session: date
    last_session: date
    sessions: int
    n: int
    mean_delta_r: float


@dataclass(frozen=True)
class BlockBootstrapResult:
    block_length: int
    n_pairs: int
    n_blocks: int
    blocks: Tuple[BlockDelta, ...]
    mean_delta_r: float
    pooled_mean_delta_r: float
    ci_lower: float
    ci_upper: float
    ci_level: float
    bootstrap_sd: float
    observed_dispersion: float
    noise_lower: float
    noise_upper: float
    noise_median: float
    noise_level: float
    tau_excess_dispersion: float
    heterogeneity: str
    exceedance_fraction: float
    blocks_with_one_session: int
    overlaps_holding_period: bool
    seed: int
    seed_ci: int
    seed_het: int
    n_resamples: int


def session_block_lookup(sessions: Sequence[date], block_length: int) -> Dict[date, int]:
    """Asigna sesiones ordenadas a bloques de longitud fija."""

    if block_length <= 0:
        raise ValueError("block_length debe ser > 0")
    return {session: index // block_length for index, session in enumerate(tuple(sorted(sessions)))}


def resample_blocks(n_blocks: int, rng: random.Random) -> List[int]:
    """Sortea índices de bloque con reemplazo."""

    if n_blocks <= 0:
        return []
    return [rng.randrange(n_blocks) for _ in range(n_blocks)]


def bootstrap_block_mean_interval(
    block_values: Sequence[Tuple[float, int]],
    *,
    seed: int,
    n_resamples: int = DEFAULT_RESAMPLES,
    confidence: float = 0.95,
) -> Tuple[float, float]:
    """Intervalo bootstrap sobre medias por bloque."""

    if not block_values:
        return 0.0, 0.0
    values = [value for value, _ in block_values]
    if len(values) < 2:
        return 0.0, 1.0
    samples = _bootstrap_means(values, random.Random(seed), n_resamples)
    return _quantile_interval(samples, confidence)


def bootstrap_block_delta(
    deltas: Sequence[PairedDelta],
    *,
    block_length: int,
    seed: int,
    n_resamples: int = DEFAULT_RESAMPLES,
    confidence: float = 0.95,
    noise_level: float = 0.90,
    session_spine: Sequence[date] | None = None,
) -> BlockBootstrapResult:
    """Estima ΔR por bloques completos y heterogeneidad frente a ruido."""

    if not (0.0 < confidence < 1.0):
        raise ValueError("confidence debe estar entre 0 y 1")
    if not (0.0 < noise_level < 1.0):
        raise ValueError("noise_level debe estar entre 0 y 1")
    if n_resamples <= 0:
        raise ValueError("n_resamples debe ser > 0")

    ordered = tuple(sorted(deltas, key=lambda item: (item.session, item.asset, item.signal_id)))
    sessions = tuple(sorted(session_spine)) if session_spine is not None else tuple(sorted({item.session for item in ordered}))
    lookup = session_block_lookup(sessions, block_length)
    by_block: Dict[int, List[PairedDelta]] = {}
    for delta in ordered:
        by_block.setdefault(lookup[delta.session], []).append(delta)

    blocks: List[BlockDelta] = []
    session_sums_by_block: List[List[Tuple[float, int]]] = []
    for block_index, items in sorted(by_block.items()):
        block_sessions = tuple(sorted({item.session for item in items}))
        mean_delta = sum(item.delta_r for item in items) / len(items)
        blocks.append(
            BlockDelta(
                block_index=block_index,
                first_session=block_sessions[0],
                last_session=block_sessions[-1],
                sessions=len(block_sessions),
                n=len(items),
                mean_delta_r=mean_delta,
            )
        )
        session_sums: List[Tuple[float, int]] = []
        for session in block_sessions:
            values = [item.delta_r for item in items if item.session == session]
            session_sums.append((sum(values), len(values)))
        session_sums_by_block.append(session_sums)

    block_means = [block.mean_delta_r for block in blocks]
    n_blocks = len(blocks)
    n_pairs = len(ordered)
    mean_delta = sum(block_means) / n_blocks if n_blocks else 0.0
    pooled_mean = sum(item.delta_r for item in ordered) / n_pairs if n_pairs else 0.0
    seed_ci = _derive_seed(seed, 1)
    seed_het = _derive_seed(seed, 2)
    if n_blocks >= 2:
        ci_samples = _bootstrap_means(block_means, random.Random(seed_ci), n_resamples)
        ci_lower, ci_upper = _quantile_interval(ci_samples, confidence)
        bootstrap_sd = _sample_sd(ci_samples)
        observed_dispersion = _sample_sd(block_means)
    elif n_blocks == 1:
        ci_lower = ci_upper = block_means[0]
        bootstrap_sd = 0.0
        observed_dispersion = 0.0
    else:
        ci_lower = ci_upper = bootstrap_sd = observed_dispersion = 0.0

    blocks_with_one_session = sum(1 for block in blocks if block.sessions == 1)
    if n_blocks < 2 or blocks_with_one_session == n_blocks:
        noise_lower = noise_upper = noise_median = 0.0
        tau = 0.0
        heterogeneity = HETEROGENEITY_NOT_ESTIMABLE
        exceedance = 0.0
    else:
        noise_samples = _constant_effect_noise(
            session_sums_by_block,
            block_means,
            mean_delta,
            random.Random(seed_het),
            n_resamples,
        )
        noise_lower, noise_upper = _quantile_interval(noise_samples, noise_level)
        noise_median = _quantile(noise_samples, 0.5)
        tau = math.sqrt(max(0.0, observed_dispersion * observed_dispersion - noise_median * noise_median))
        if observed_dispersion < noise_lower:
            heterogeneity = HETEROGENEITY_LOW
        elif observed_dispersion > noise_upper:
            heterogeneity = HETEROGENEITY_HIGH
        else:
            heterogeneity = HETEROGENEITY_NOISE
        exceedance = sum(1 for sample in noise_samples if sample >= observed_dispersion) / len(noise_samples)

    return BlockBootstrapResult(
        block_length=block_length,
        n_pairs=n_pairs,
        n_blocks=n_blocks,
        blocks=tuple(blocks),
        mean_delta_r=mean_delta,
        pooled_mean_delta_r=pooled_mean,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        ci_level=confidence,
        bootstrap_sd=bootstrap_sd,
        observed_dispersion=observed_dispersion,
        noise_lower=noise_lower,
        noise_upper=noise_upper,
        noise_median=noise_median,
        noise_level=noise_level,
        tau_excess_dispersion=tau,
        heterogeneity=heterogeneity,
        exceedance_fraction=exceedance,
        blocks_with_one_session=blocks_with_one_session,
        overlaps_holding_period=False,
        seed=seed,
        seed_ci=seed_ci,
        seed_het=seed_het,
        n_resamples=n_resamples,
    )


def _derive_seed(seed: int, stream: int) -> int:
    return seed * 1_000_003 + stream * 97


def _bootstrap_means(values: Sequence[float], rng: random.Random, n_resamples: int) -> List[float]:
    n = len(values)
    samples: List[float] = []
    for _ in range(n_resamples):
        indices = resample_blocks(n, rng)
        samples.append(sum(values[index] for index in indices) / n)
    return sorted(samples)


def _constant_effect_noise(
    session_sums_by_block: Sequence[Sequence[Tuple[float, int]]],
    block_means: Sequence[float],
    global_mean: float,
    rng: random.Random,
    n_resamples: int,
) -> List[float]:
    adjusted: List[List[Tuple[float, int]]] = []
    for block_sessions, block_mean in zip(session_sums_by_block, block_means):
        adjusted.append([(session_sum + count * (global_mean - block_mean), count) for session_sum, count in block_sessions])

    samples: List[float] = []
    for _ in range(n_resamples):
        block_sample_means: List[float] = []
        for block_sessions in adjusted:
            drawn_sum = 0.0
            drawn_n = 0
            for index in resample_blocks(len(block_sessions), rng):
                session_sum, count = block_sessions[index]
                drawn_sum += session_sum
                drawn_n += count
            block_sample_means.append(drawn_sum / drawn_n if drawn_n else 0.0)
        samples.append(_sample_sd(block_sample_means))
    return sorted(samples)


def _quantile_interval(sorted_values: Sequence[float], level: float) -> Tuple[float, float]:
    alpha = 1.0 - level
    return _quantile(sorted_values, alpha / 2.0), _quantile(sorted_values, 1.0 - alpha / 2.0)


def _quantile(sorted_values: Sequence[float], probability: float) -> float:
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    low = math.floor(probability * n)
    high = math.ceil(probability * n) - 1
    index = max(0, min(n - 1, low if probability <= 0.5 else high))
    return sorted_values[index]


def _sample_sd(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))
