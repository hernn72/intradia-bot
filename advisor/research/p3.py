"""Ejecutor único de P3 (T-019 paso 3): Score v2 sobre la cosecha congelada.

Implementa literalmente el pre-registro `8b2dddb` (ficha T-019, «P3 —
experimento pre-registrado», D-50 a D-57 y D-59). Nada de lo que sigue es un
parámetro: los percentiles, bloques, semilla, remuestreos, niveles, umbrales de
capacidad, coste y versión de score están fijados aquí o en los instrumentos
P2.5 que se reutilizan sin cambios.

Dos fases, separadas por una frontera que no se cruza dos veces:

- ``preflight``: reproduce población, hashes, bloques y cortes **sin
  desenlaces** (el event study corre con ``evaluate_*`` sustituidos por
  ``None``). Se puede repetir.
- ``confirmatoria``: una sola ejecución sobre un árbol limpio. Deja una marca
  antes de calcular desenlaces y se niega a arrancar si la marca ya existe.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from unittest.mock import patch

import advisor.research.event_study as event_study
from advisor.config import AdvisorConfig
from advisor.data.freshness import mercado_para_simbolo
from advisor.data.sessions import session_date_of
from advisor.research.bootstrap import DEFAULT_RESAMPLES, DEFAULT_SEED, bootstrap_block_mean_interval
from advisor.research.capacity import (
    DEFAULT_THRESHOLDS,
    LIMITADA,
    SUFICIENTE,
    CapacitySummary,
    CapacityThresholds,
    TemporalBlockMap,
    _primary_expectancy_row,
    _protocol_block_length,
    _summary,
    _temporal_block_lookup,
)
from advisor.research.event_study import (
    AMBIGUOUS,
    FINAL_EXIT,
    STOP_FIRST,
    TARGET_FIRST,
    EventStudyResult,
    EventStudySignal,
)
from advisor.research.p3_population import P3PopulationControl, census_p3_population
from advisor.research.vintage import VintageLoad
from advisor.run.manifest import config_hash
from advisor.universe.models import Universe

PREREGISTRATION_SHA = "8b2dddb8fd66423d9550df496d1a2a85abd066b6"
DATA_VINTAGE_ID = "071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841"
UNIVERSE_VINTAGE_ID = "237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19"
SCORE_MODEL_VERSION = "2.0"
ACTIVE_SCORE_MODEL_VERSION = "1.0"
COST_PCT = 0.2
SEED = DEFAULT_SEED
STANDARD_RESAMPLES = DEFAULT_RESAMPLES
STANDARD_CONFIDENCE = 0.95
BONFERRONI_M = 20
BONFERRONI_CONFIDENCE = 1.0 - 0.05 / BONFERRONI_M
BONFERRONI_RESAMPLES = 20_000
QUINTILE_PERCENTILES = (20, 40, 60, 80)
CANDIDATE_PERCENTILES = (50, 60, 70, 80, 90)
QUINTILE_LABELS = ("Q1", "Q2", "Q3", "Q4", "Q5")
HORIZONTES = ("swing", "medio")
CONFIRMATORY_HORIZONTE = "swing"
ABLATED_DIMENSIONS = ("catalizador", "tecnico", "contexto")
UNIVERSE_LABEL = "condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)"
MEDIO_FORCED_VERDICT = "NO CONCLUYENTE — inválido (bloque parcial 102 ≤ 250)"

SCORE_RESOLUTION_INSUFFICIENT = "SCORE_RESOLUTION_INSUFFICIENT"
NO_CONCLUYENTE = "NO CONCLUYENTE"
VEREDICTO_SUFICIENTE = "SUFICIENTE"
VEREDICTO_LIMITADA = "LIMITADA"
VEREDICTO_INSUFICIENTE = "INSUFICIENTE"

# Identidades del pre-registro que el preflight tiene que reproducir antes de
# permitir la ejecución confirmatoria (censo `06` de 2a-doc, reproducido en
# 2a-code). No son parámetros: si una diverge, P3 no se ejecuta.
EXPECTED_POPULATION: Dict[str, Dict[str, Any]] = {
    "swing": {
        "a02": 106_363,
        "excluded_crypto": 5_112,
        "excluded_asia_missing": 396,
        "excluded_trend_sma_history": 6_937,
        "asia_and_sma": 176,
        "union": 12_269,
        "final": 94_094,
        "assets": 90,
        "regions": 5,
        "blocks": 19,
        "sha256": "4aa12d85eb54d7a01c10a4a3e4cf04e8077c842829235a93b75f7bd19c62011a",
        "stoxx_gaps": 1_406,
    },
    "medio": {
        "a02": 94_273,
        "excluded_crypto": 4_722,
        "excluded_asia_missing": 218,
        "excluded_trend_sma_history": 0,
        "asia_and_sma": 0,
        "union": 4_940,
        "final": 89_333,
        "assets": 90,
        "regions": 5,
        "blocks": 5,
        "sha256": "4d6eaab9b84ff23bade1df86a82e95f46da546917a226dc8438a8e88493020f8",
        "stoxx_gaps": 1_312,
    },
}
ALLOWED_STOXX_AGES = frozenset({1, 3, 4})
RUN_MARKER = "EJECUCION_CONFIRMATORIA_INICIADA"
# `config_hash` de `config.yaml` en `8b2dddb`/`5953300` (manifiesto de la Pi en
# v0.4.1): la geometría de niveles y todo lo que decide los desenlaces. Un
# `--config` distinto no puede pasar el preflight.
EXPECTED_CONFIG_HASH = "89406d28c7b4b6e6c4f032cd63b6868c927af3e926dfb52d430dfa6654d06387"
# La ejecución confirmatoria escribe siempre aquí: una sola marca, en una sola
# ruta, para que no se pueda repetir cambiando el directorio de salida.
CONFIRMATORY_OUTPUT_DIR = Path("evidence/2026-09-30-T-019-paso3-p3/run")
# Los scores son cocientes de puntos por dimensión sobre 50, 30 o 40: dos
# cálculos del mismo valor exacto pueden diferir en el último bit (218/3 →
# …666 o …667). Se comparan y se cortan con 9 decimales, que es la fórmula
# exacta: en la cosecha, valores realmente distintos difieren en ≥ 0,0078 y el
# ruido de un mismo valor es ≤ 3e-14 (revisión previa a P3).
SCORE_DECIMALS = 9


def canonical_score(value: float) -> float:
    return round(value, SCORE_DECIMALS)


class P3PreflightError(RuntimeError):
    """Una identidad del pre-registro no se reproduce: P3 no se ejecuta."""


class P3AlreadyExecutedError(RuntimeError):
    """La ejecución confirmatoria ya se inició una vez: no se repite."""


# ---------------------------------------------------------------------------
# Percentiles y cortes: solo `Score.value`, nunca desenlaces.
# ---------------------------------------------------------------------------


def nearest_rank_index(k: int, n: int) -> int:
    """Índice cero-based de `cut(k/100)` en aritmética entera (ficha T-019)."""

    if n <= 0:
        raise ValueError("nearest-rank necesita al menos un valor")
    if not 0 < k <= 100:
        raise ValueError(f"percentil fuera de rango: {k}")
    return (k * n + 99) // 100 - 1


def nearest_rank_cut(sorted_values: Sequence[float], k: int) -> float:
    return sorted_values[nearest_rank_index(k, len(sorted_values))]


@dataclass(frozen=True)
class QuintileCuts:
    percentiles: Tuple[int, ...]
    values: Tuple[float, ...]
    n: int
    distinct_scores: int
    n_by_quintile: Dict[str, int]
    resolution_insufficient: bool
    tied_pairs: Tuple[Tuple[int, int], ...]

    @property
    def status(self) -> str:
        return SCORE_RESOLUTION_INSUFFICIENT if self.resolution_insufficient else "OK"


def quintile_cuts(scores: Sequence[float]) -> QuintileCuts:
    ordered = sorted(scores)
    values = tuple(nearest_rank_cut(ordered, k) for k in QUINTILE_PERCENTILES)
    tied = tuple(
        (QUINTILE_PERCENTILES[i], QUINTILE_PERCENTILES[i + 1])
        for i in range(len(values) - 1)
        if values[i] == values[i + 1]
    )
    counts = Counter(quintile_of(score, values) for score in ordered)
    return QuintileCuts(
        percentiles=QUINTILE_PERCENTILES,
        values=values,
        n=len(ordered),
        distinct_scores=len(set(ordered)),
        n_by_quintile={label: counts.get(label, 0) for label in QUINTILE_LABELS},
        resolution_insufficient=bool(tied),
        tied_pairs=tied,
    )


def quintile_of(score: float, cuts: Sequence[float]) -> str:
    """Q1=[mín,c20) … Q5=[c80,máx]; un score igual a un corte sube de banda."""

    for index, cut in enumerate(cuts):
        if score < cut:
            return QUINTILE_LABELS[index]
    return QUINTILE_LABELS[-1]


@dataclass(frozen=True)
class CandidateSet:
    percentiles: Tuple[int, ...]
    values: Tuple[float, ...]
    distinct: Tuple[float, ...]
    collapses: Dict[str, List[int]]


def candidate_set(scores: Sequence[float]) -> CandidateSet:
    ordered = sorted(scores)
    values = tuple(nearest_rank_cut(ordered, k) for k in CANDIDATE_PERCENTILES)
    by_value: Dict[float, List[int]] = {}
    for k, value in zip(CANDIDATE_PERCENTILES, values):
        by_value.setdefault(value, []).append(k)
    collapses = {_fmt_key(value): ks for value, ks in by_value.items() if len(ks) > 1}
    return CandidateSet(
        percentiles=CANDIDATE_PERCENTILES,
        values=values,
        distinct=tuple(sorted(by_value)),
        collapses=collapses,
    )


# ---------------------------------------------------------------------------
# Registros y estimadores por bloque (datos ya cargados; testables con
# desenlaces sintéticos).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class P3Record:
    """Una señal de la población de P3 con lo que usan los estimadores."""

    asset: str
    region: str
    block: int
    score: float
    net_r: Optional[float]
    exit_status: str
    mae_r: float
    mfe_unbounded_lower_r: float
    mfe_unbounded_upper_r: float
    ablated_scores: Mapping[str, float]
    signal: Optional[EventStudySignal] = None


@dataclass(frozen=True)
class BlockInterval:
    label: str
    mean: Optional[float]
    n: int
    n_blocks: int
    lower: Optional[float]
    upper: Optional[float]
    confidence: float
    n_resamples: int
    excluded_blocks: Tuple[int, ...] = ()

    @property
    def width(self) -> Optional[float]:
        if self.lower is None or self.upper is None:
            return None
        return self.upper - self.lower


def block_means(records: Iterable[P3Record]) -> List[Tuple[int, float, int]]:
    """(bloque, media de net_R, n) de los bloques con algún net_R observable."""

    buckets: Dict[int, List[float]] = {}
    for record in records:
        if record.net_r is None:
            continue
        buckets.setdefault(record.block, []).append(record.net_r)
    return [(block, sum(values) / len(values), len(values)) for block, values in sorted(buckets.items())]


def _interval(
    block_values: Sequence[Tuple[float, int]],
    *,
    confidence: float,
    n_resamples: int,
) -> Tuple[Optional[float], Optional[float]]:
    if len(block_values) < 2:
        return None, None
    lower, upper = bootstrap_block_mean_interval(
        block_values,
        seed=SEED,
        n_resamples=n_resamples,
        confidence=confidence,
    )
    return lower, upper


def primary_interval(
    label: str,
    records: Sequence[P3Record],
    *,
    confidence: float = STANDARD_CONFIDENCE,
    n_resamples: int = STANDARD_RESAMPLES,
) -> BlockInterval:
    """Primario INV-14: media simple por bloque de la expectancy neta en R."""

    means = block_means(records)
    values = [(mean, n) for _, mean, n in means]
    lower, upper = _interval(values, confidence=confidence, n_resamples=n_resamples)
    return BlockInterval(
        label=label,
        mean=(sum(mean for mean, _ in values) / len(values)) if values else None,
        n=sum(n for _, n in values),
        n_blocks=len(values),
        lower=lower,
        upper=upper,
        confidence=confidence,
        n_resamples=n_resamples,
    )


def paired_block_contrast(
    label: str,
    high: Sequence[P3Record],
    low: Sequence[P3Record],
    *,
    confidence: float = STANDARD_CONFIDENCE,
    n_resamples: int = STANDARD_RESAMPLES,
) -> BlockInterval:
    """Contraste pareado por bloque: media(high) − media(low) donde hay ambas."""

    high_means = {block: (mean, n) for block, mean, n in block_means(high)}
    low_means = {block: (mean, n) for block, mean, n in block_means(low)}
    both = sorted(set(high_means) & set(low_means))
    excluded = tuple(sorted((set(high_means) | set(low_means)) - set(both)))
    values = [(high_means[b][0] - low_means[b][0], high_means[b][1] + low_means[b][1]) for b in both]
    lower, upper = _interval(values, confidence=confidence, n_resamples=n_resamples)
    return BlockInterval(
        label=label,
        mean=(sum(delta for delta, _ in values) / len(values)) if values else None,
        n=sum(n for _, n in values),
        n_blocks=len(values),
        lower=lower,
        upper=upper,
        confidence=confidence,
        n_resamples=n_resamples,
        excluded_blocks=excluded,
    )


def veredicto_ordenacion(
    delta: BlockInterval,
    *,
    horizon_valid: bool,
    resolution_insufficient: bool,
    thresholds: CapacityThresholds = DEFAULT_THRESHOLDS,
) -> Tuple[str, List[str]]:
    """Tabla del veredicto de ordenación, aplicada en su orden."""

    reasons: List[str] = []
    if not horizon_valid:
        reasons.append("horizonte inválido (bloque parcial)")
    if delta.mean is None or delta.width is None:
        reasons.append("Δ no calculable")
    if delta.n_blocks < thresholds.limited_blocks:
        reasons.append(f"bloques con Δ {delta.n_blocks} < {thresholds.limited_blocks}")
    if delta.width is not None and delta.width > thresholds.limited_interval_width:
        reasons.append(f"anchura IC95 {delta.width:.4f} > {thresholds.limited_interval_width}")
    if resolution_insufficient:
        reasons.append(SCORE_RESOLUTION_INSUFFICIENT)
    if reasons:
        return NO_CONCLUYENTE, reasons
    assert delta.lower is not None and delta.width is not None
    if (
        delta.n_blocks >= thresholds.sufficient_blocks
        and delta.width <= thresholds.sufficient_interval_width
        and delta.lower > 0
    ):
        return VEREDICTO_SUFICIENTE, []
    if delta.width <= thresholds.limited_interval_width and delta.lower > 0:
        return VEREDICTO_LIMITADA, []
    sign = "negativo (ordena al revés)" if (delta.mean or 0.0) < 0 else "no negativo"
    return VEREDICTO_INSUFICIENTE, [f"cota inferior IC95 {delta.lower:.4f} ≤ 0; signo del Δ {sign}"]


def profit_factor(records: Iterable[P3Record]) -> Optional[float]:
    values = [record.net_r for record in records if record.net_r is not None]
    gains = sum(value for value in values if value > 0)
    losses = sum(value for value in values if value < 0)
    if losses == 0:
        # Sin pérdidas el cociente es infinito si hubo ganancias; sin ninguna
        # operación con signo no hay profit factor que publicar.
        return math.inf if gains > 0 else None
    return gains / abs(losses)


@dataclass(frozen=True)
class Secondaries:
    n: int
    expectancy_pooled_net_r: Optional[float]
    target_first_rate: Optional[float]
    target_before_stop_lower: Optional[float]
    target_before_stop_upper: Optional[float]
    profit_factor: Optional[float]
    median_mae_winners_r: Optional[float]
    median_mfe_without_target_lower_r: Optional[float]
    median_mfe_without_target_upper_r: Optional[float]
    exit_final_rate: Optional[float]
    ambiguous_rate: Optional[float]


def secondaries(records: Sequence[P3Record]) -> Secondaries:
    total = len(records)
    statuses = Counter(record.exit_status for record in records)
    target = statuses.get(TARGET_FIRST, 0)
    stop = statuses.get(STOP_FIRST, 0)
    ambiguous = statuses.get(AMBIGUOUS, 0)
    net = [record.net_r for record in records if record.net_r is not None]
    winners_mae = [record.mae_r for record in records if record.exit_status == TARGET_FIRST]
    return Secondaries(
        n=total,
        expectancy_pooled_net_r=(sum(net) / len(net)) if net else None,
        target_first_rate=(target / (target + stop)) if (target + stop) else None,
        target_before_stop_lower=(target / total) if total else None,
        target_before_stop_upper=((target + ambiguous) / total) if total else None,
        profit_factor=profit_factor(records),
        median_mae_winners_r=statistics.median(winners_mae) if winners_mae else None,
        median_mfe_without_target_lower_r=(
            statistics.median([r.mfe_unbounded_lower_r for r in records]) if records else None
        ),
        median_mfe_without_target_upper_r=(
            statistics.median([r.mfe_unbounded_upper_r for r in records]) if records else None
        ),
        exit_final_rate=(statuses.get(FINAL_EXIT, 0) / total) if total else None,
        ambiguous_rate=(ambiguous / total) if total else None,
    )


# ---------------------------------------------------------------------------
# Calibración swing: meseta OPERAR y recorrido VIGILAR, literales.
# ---------------------------------------------------------------------------


def meseta_operar(distinct: Sequence[float], cumple: Mapping[float, bool]) -> Optional[float]:
    """Menor candidato tal que él y todos los superiores cumplen; None si no hay."""

    operar: Optional[float] = None
    for candidate in sorted(distinct, reverse=True):
        if not cumple[candidate]:
            break
        operar = candidate
    return operar


def recorrido_vigilar(
    distinct: Sequence[float],
    operar: float,
    cumple_vigilar: Callable[[float, float], bool],
) -> Tuple[float, List[Tuple[float, bool]]]:
    """Recorrido pre-registrado: baja desde `operar`, el primer fallo corta."""

    ordered = sorted(set(distinct))
    candidatos_bajo = [c for c in reversed(ordered) if c < operar]
    vigilar = operar
    visited: List[Tuple[float, bool]] = []
    for v in candidatos_bajo:
        ok = cumple_vigilar(v, operar)
        visited.append((v, ok))
        if ok:
            vigilar = v
        else:
            break
    return vigilar, visited


# ---------------------------------------------------------------------------
# Contadores de comparaciones, derivados de las salidas publicadas.
# ---------------------------------------------------------------------------


def comparison_counters(horizon_outputs: Mapping[str, Mapping[str, Any]]) -> Dict[str, int]:
    def descriptive(out: Mapping[str, Any]) -> int:
        return (
            len(out["quintiles"])
            + len(out["adjacent_contrasts"])
            + len(out["regions"]["primary"])
            + len(out["regions"]["delta"])
            + len(out["assets"]["primary"])
            + len(out["assets"]["delta"])
            + 1  # intra-activo agregado
            + len(out["intra_asset"]["by_asset"])
            + sum(len(ab["quintiles"]) + 1 for ab in out["ablations"].values())
        )

    counters: Dict[str, int] = {}
    swing = horizon_outputs["swing"]
    counters["comparaciones_swing"] = 1 + len(swing["calibration"]["bonferroni_family"]) + descriptive(swing)
    medio = horizon_outputs["medio"]
    counters["comparaciones_medio_trazabilidad"] = 1 + descriptive(medio)
    counters["comparaciones_totales"] = counters["comparaciones_swing"] + counters["comparaciones_medio_trazabilidad"]
    return counters


# ---------------------------------------------------------------------------
# Población: el mismo event study PIT v2 de P3, con o sin desenlaces.
# ---------------------------------------------------------------------------


@dataclass
class HorizonPopulation:
    horizonte: str
    census: P3PopulationControl
    result: EventStudyResult
    lookup: TemporalBlockMap
    block_length: int
    records: List[P3Record]
    population_sha256: str
    horizon_valid: bool
    shortest_block_sessions: Optional[int]
    checks: List[Tuple[str, Any, Any, bool]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(passed for *_, passed in self.checks)


def _no_outcome(*args: object, **kwargs: object) -> None:
    return None


def run_p3_event_study(
    config: AdvisorConfig,
    universe: Universe,
    vintage: VintageLoad,
    horizonte: str,
    *,
    with_outcomes: bool,
) -> EventStudyResult:
    """Event study PIT con Score v2 (D-59); sin desenlaces en el preflight."""

    def run() -> EventStudyResult:
        return event_study.run_event_study_on_vintage(
            config,
            universe,
            vintage,
            horizonte=horizonte,
            cost_pct=COST_PCT,
            context_mode="point_in_time",
            score_model_version=SCORE_MODEL_VERSION,
        )

    if with_outcomes:
        return run()
    with (
        patch.object(event_study, "evaluate_managed_event", _no_outcome),
        patch.object(event_study, "evaluate_potential_event", _no_outcome),
    ):
        return run()


def build_population(
    config: AdvisorConfig,
    universe: Universe,
    vintage: VintageLoad,
    horizonte: str,
    *,
    with_outcomes: bool,
) -> HorizonPopulation:
    census = census_p3_population(config, universe, vintage, horizonte=horizonte)
    result = run_p3_event_study(config, universe, vintage, horizonte, with_outcomes=with_outcomes)
    block_length = _protocol_block_length(horizonte, result.max_hold_bars)
    lookup = _temporal_block_lookup(result, block_length, universe)
    records: List[P3Record] = []
    keys: List[Tuple[str, date]] = []
    for signal in result.signals:
        asset = universe.get(signal.observation.asset)
        if asset is None:
            raise P3PreflightError(f"{signal.observation.asset}: señal sin activo en el universo")
        views = vintage.by_symbol[asset.primary_symbol]
        market = mercado_para_simbolo(asset, asset.primary_symbol)
        session = session_date_of(views.signal_prices.index[signal.observation.signal_idx], market)
        if session is None:
            raise P3PreflightError(f"{asset.symbol}: señal sin sesión de plaza")
        keys.append((asset.symbol, session))
        records.append(_record(signal, asset.region, lookup.block_for(signal), with_outcomes=with_outcomes))
    population_sha256 = hashlib.sha256(
        "\n".join(sorted(f"{symbol}\t{session}" for symbol, session in keys)).encode()
    ).hexdigest()
    occupied = {record.block for record in records}
    shortest = min((lookup.sessions_in_block(block) for block in occupied), default=None)
    population = HorizonPopulation(
        horizonte=horizonte,
        census=census,
        result=result,
        lookup=lookup,
        block_length=block_length,
        records=records,
        population_sha256=population_sha256,
        horizon_valid=shortest is not None and shortest > result.max_hold_bars,
        shortest_block_sessions=shortest,
    )
    population.checks = _identity_checks(config, population, keys)
    return population


def _record(signal: EventStudySignal, region: str, block: int, *, with_outcomes: bool) -> P3Record:
    observation = signal.observation
    if observation.score_model_version != SCORE_MODEL_VERSION:
        raise P3PreflightError(f"{observation.signal_id}: score {observation.score_model_version}, no {SCORE_MODEL_VERSION}")
    ablated = ablated_scores(observation)
    if with_outcomes:
        managed = signal.managed
        potential = signal.potential
        return P3Record(
            asset=observation.asset,
            region=region,
            block=block,
            score=canonical_score(observation.score_value),
            net_r=managed.net_r_multiple,
            exit_status=managed.exit_status,
            mae_r=managed.mae_r,
            mfe_unbounded_lower_r=potential.mfe_unbounded_lower_r,
            mfe_unbounded_upper_r=potential.mfe_unbounded_upper_r,
            ablated_scores=ablated,
            signal=signal,
        )
    return P3Record(
        asset=observation.asset,
        region=region,
        block=block,
        score=canonical_score(observation.score_value),
        net_r=None,
        exit_status="SIN_DESENLACE",
        mae_r=0.0,
        mfe_unbounded_lower_r=0.0,
        mfe_unbounded_upper_r=0.0,
        ablated_scores=ablated,
        signal=None,
    )


def ablated_scores(observation: Any) -> Dict[str, float]:
    """`score_sin_X = 100·(points − points_X)/(evaluable_max − max_X)`."""

    dims = {dim.name: dim for dim in observation.dimensions}
    points = sum(dim.points for dim in observation.dimensions if dim.available)
    evaluable_max = observation.evaluable_max
    if evaluable_max <= 0:
        raise P3PreflightError(f"{observation.signal_id}: evaluable_max {evaluable_max}")
    if abs(100.0 * points / evaluable_max - observation.score_value) > 1e-9:
        raise P3PreflightError(f"{observation.signal_id}: los puntos por dimensión no reconstruyen Score.value")
    scores: Dict[str, float] = {}
    for name in ABLATED_DIMENSIONS:
        dim = dims.get(name)
        points_x = dim.points if dim is not None and dim.available else 0.0
        max_x = dim.max if dim is not None and dim.available else 0.0
        denominator = evaluable_max - max_x
        if denominator <= 0:
            raise P3PreflightError(f"{observation.signal_id}: sin {name} no queda denominador")
        scores[name] = canonical_score(100.0 * (points - points_x) / denominator)
    return scores


def _identity_checks(
    config: AdvisorConfig,
    population: HorizonPopulation,
    keys: Sequence[Tuple[str, date]],
) -> List[Tuple[str, Any, Any, bool]]:
    expected = EXPECTED_POPULATION[population.horizonte]
    census = population.census
    rows = census.rows_by_reason
    asia = {(str(r[0]), r[1]) for r in rows["excluded_asia_missing"]}
    sma = {(str(r[0]), r[1]) for r in rows["excluded_trend_sma_history"]}
    ages = set(census.stoxx_gap_ages)
    assets = {record.asset for record in population.records}
    regions = {record.region for record in population.records}
    blocks = {record.block for record in population.records}
    checks: List[Tuple[str, Any, Any, bool]] = []

    def check(name: str, observed: Any, wanted: Any) -> None:
        checks.append((name, observed, wanted, observed == wanted))

    check("población A-02", census.a02_population, expected["a02"])
    check("excluded_crypto", len(rows["excluded_crypto"]), expected["excluded_crypto"])
    check("excluded_asia_missing", len(rows["excluded_asia_missing"]), expected["excluded_asia_missing"])
    check("excluded_trend_sma_history", len(rows["excluded_trend_sma_history"]), expected["excluded_trend_sma_history"])
    check("Asia ∩ SMA200", len(asia & sma), expected["asia_and_sma"])
    check("unión deduplicada", census.union_excluded, expected["union"])
    check("población final (censo)", len(census.final_population), expected["final"])
    check("sha256 población (censo)", census.final_sha256, expected["sha256"])
    check("señales del event study PIT v2", len(keys), expected["final"])
    check("sha256 población (event study PIT v2)", population.population_sha256, expected["sha256"])
    check("activos", len(assets), expected["assets"])
    check("regiones", len(regions), expected["regions"])
    check("bloques ocupados", len(blocks), expected["blocks"])
    check("bloques del censo", census.blocks_with_signals, expected["blocks"])
    check("huecos intermedios ^STOXX50E", len(census.stoxx_gap_rows), expected["stoxx_gaps"])
    check("antigüedades STOXX ⊆ {1,3,4}", ages <= ALLOWED_STOXX_AGES, True)
    check("config.yaml activo", config.scoring.score_model_version, ACTIVE_SCORE_MODEL_VERSION)
    check("config_hash", config_hash(config), EXPECTED_CONFIG_HASH)
    check("universe_vintage_id", population.result.universe_vintage_id, UNIVERSE_VINTAGE_ID)
    check("data_vintage_id", population.result.data_vintage_id, DATA_VINTAGE_ID)
    return checks


# ---------------------------------------------------------------------------
# Análisis con desenlaces (solo en la ejecución confirmatoria).
# ---------------------------------------------------------------------------


def analyze_horizon(population: HorizonPopulation, *, thresholds: CapacityThresholds = DEFAULT_THRESHOLDS) -> Dict[str, Any]:
    records = population.records
    horizonte = population.horizonte
    cuts = quintile_cuts([record.score for record in records])
    by_quintile = _group(records, lambda r: quintile_of(r.score, cuts.values))

    def capacity(label: str, subset: Sequence[P3Record]) -> CapacitySummary:
        return _summary(
            label,
            [record.signal for record in subset if record.signal is not None],
            block_length=population.block_length,
            block_lookup=population.lookup,
            thresholds=thresholds,
            max_hold_bars=population.result.max_hold_bars,
            band_of=None,
        )

    global_primary = primary_interval("GLOBAL", records)
    standard_global = _primary_expectancy_row("GLOBAL", [r.signal for r in records if r.signal is not None], population.lookup)
    quintiles = []
    for label in QUINTILE_LABELS:
        subset = by_quintile.get(label, [])
        cap = capacity(label, subset)
        quintiles.append(
            {
                "label": label,
                "primary": _interval_dict(primary_interval(label, subset)),
                "capacidad": _capacity_dict(cap),
                "secundarias": asdict(secondaries(subset)),
            }
        )
    delta = paired_block_contrast("Q5−Q1", by_quintile.get("Q5", []), by_quintile.get("Q1", []))
    adjacent = [
        _interval_dict(
            paired_block_contrast(
                f"{QUINTILE_LABELS[i + 1]}−{QUINTILE_LABELS[i]}",
                by_quintile.get(QUINTILE_LABELS[i + 1], []),
                by_quintile.get(QUINTILE_LABELS[i], []),
            )
        )
        for i in range(len(QUINTILE_LABELS) - 1)
    ]
    if horizonte == CONFIRMATORY_HORIZONTE:
        verdict, verdict_reasons = veredicto_ordenacion(
            delta,
            horizon_valid=population.horizon_valid,
            resolution_insufficient=cuts.resolution_insufficient,
            thresholds=thresholds,
        )
    else:
        verdict, verdict_reasons = MEDIO_FORCED_VERDICT, ["medio solo por trazabilidad (D-45, D-42)"]

    output: Dict[str, Any] = {
        "horizonte": horizonte,
        "confirmatorio": horizonte == CONFIRMATORY_HORIZONTE,
        "horizon_valid": population.horizon_valid,
        "shortest_occupied_block_sessions": population.shortest_block_sessions,
        "max_hold_bars": population.result.max_hold_bars,
        "block_length": population.block_length,
        "n": len(records),
        "blocks_occupied": len({r.block for r in records}),
        "cuts": _cuts_dict(cuts),
        "global_primary": _interval_dict(global_primary),
        "global_primary_instrumento_a02": asdict(standard_global),
        "global_secundarias": asdict(secondaries(records)),
        "quintiles": quintiles,
        "block_by_quintile": _block_by_quintile(records, cuts.values),
        "delta_q5_q1": _interval_dict(delta),
        "veredicto_ordenacion": verdict,
        "veredicto_ordenacion_motivos": verdict_reasons,
        "suficiente_alcanzable": horizonte == CONFIRMATORY_HORIZONTE
        and len({r.block for r in records}) >= thresholds.sufficient_blocks,
        "adjacent_contrasts": adjacent,
        "regions": _by_group(records, lambda r: r.region, cuts.values),
        "assets": _by_group(records, lambda r: r.asset, cuts.values),
        "intra_asset": _intra_asset(records, cuts.values, thresholds),
        "ablations": {name: _ablation(records, name, cuts.values, population, thresholds) for name in ABLATED_DIMENSIONS},
        "label": UNIVERSE_LABEL,
    }
    if horizonte == CONFIRMATORY_HORIZONTE:
        output["calibration"] = _calibration(records, population, capacity)
    return output


def _calibration(
    records: Sequence[P3Record],
    population: HorizonPopulation,
    capacity: Callable[[str, Sequence[P3Record]], CapacitySummary],
) -> Dict[str, Any]:
    candidates = candidate_set([record.score for record in records])
    evaluations: Dict[float, Dict[str, Any]] = {}
    cumple: Dict[float, bool] = {}
    for c in candidates.distinct:
        upper = [r for r in records if r.score >= c]
        lower = [r for r in records if r.score < c]
        cap = capacity(f"[{c:g},∞)", upper)
        primary = primary_interval(
            f"[{c:g},∞)", upper, confidence=BONFERRONI_CONFIDENCE, n_resamples=BONFERRONI_RESAMPLES
        )
        contrast = paired_block_contrast(
            f"[{c:g},∞)−[0,{c:g})",
            upper,
            lower,
            confidence=BONFERRONI_CONFIDENCE,
            n_resamples=BONFERRONI_RESAMPLES,
        )
        pf = profit_factor(upper)
        conditions = {
            "1_horizonte_valido": population.horizon_valid,
            "2_capacidad_limitada_o_mejor_y_concluyente": cap.verdict in {LIMITADA, SUFICIENTE} and cap.conclusive,
            "3_bonferroni_primario_cota_inferior_positiva": primary.lower is not None and primary.lower > 0,
            "4_bonferroni_contraste_cota_inferior_positiva": contrast.lower is not None and contrast.lower > 0,
            "5_profit_factor_mayor_que_1": pf is not None and pf > 1,
        }
        cumple[c] = all(conditions.values())
        evaluations[c] = {
            "candidato": c,
            "percentiles": [k for k, v in zip(candidates.percentiles, candidates.values) if v == c],
            "n_upper": len(upper),
            "n_lower": len(lower),
            "capacidad": _capacity_dict(cap),
            "bonferroni_primario": _interval_dict(primary),
            "bonferroni_contraste": _interval_dict(contrast),
            "profit_factor": pf,
            "condiciones": conditions,
            "cumple_operar": cumple[c],
        }
    operar = meseta_operar(candidates.distinct, cumple)

    vigilar: Optional[float] = None
    vigilar_evaluations: Dict[Tuple[float, float], Dict[str, Any]] = {}
    visited: List[Tuple[float, bool]] = []
    if operar is not None:
        def cumple_vigilar(v: float, top: float) -> bool:
            band = [r for r in records if v <= r.score < top]
            cap = capacity(f"[{v:g},{top:g})", band)
            interval = primary_interval(
                f"[{v:g},{top:g})", band, confidence=BONFERRONI_CONFIDENCE, n_resamples=BONFERRONI_RESAMPLES
            )
            ok = cap.verdict in {LIMITADA, SUFICIENTE} and interval.upper is not None and interval.upper > 0
            vigilar_evaluations[(v, top)] = {
                "banda": [v, top],
                "n": len(band),
                "capacidad": _capacity_dict(cap),
                "bonferroni_primario": _interval_dict(interval),
                "cumple_vigilar": ok,
            }
            return ok

        vigilar, visited = recorrido_vigilar(candidates.distinct, operar, cumple_vigilar)

    family = _bonferroni_family(candidates, evaluations, vigilar_evaluations, operar)
    return {
        "candidates": {
            "percentiles": list(candidates.percentiles),
            "values": list(candidates.values),
            "distinct": list(candidates.distinct),
            "collapses": candidates.collapses,
        },
        "evaluations": [evaluations[c] for c in candidates.distinct],
        "min_score_operar": operar,
        "calibrated": operar is not None,
        "vigilar_recorrido": [{"v": v, "cumple": ok} for v, ok in visited],
        "min_score_vigilar": vigilar,
        "franja_vigilar_vacia": operar is not None and vigilar == operar,
        "bonferroni_m": BONFERRONI_M,
        "bonferroni_confidence": BONFERRONI_CONFIDENCE,
        "bonferroni_resamples": BONFERRONI_RESAMPLES,
        "bonferroni_family": family,
        "drawdown": "no aplicable a un event study sin cartera; se evalúa en P6",
    }


def _bonferroni_family(
    candidates: CandidateSet,
    evaluations: Mapping[float, Mapping[str, Any]],
    vigilar_evaluations: Mapping[Tuple[float, float], Mapping[str, Any]],
    operar: Optional[float],
) -> List[Dict[str, Any]]:
    family: List[Dict[str, Any]] = []
    for k, value in zip(candidates.percentiles, candidates.values):
        evaluation = evaluations[value]
        family.append({"miembro": f"OPERAR primario [p{k}={value:g},∞)", "percentil": k, "valor": value,
                       "intervalo": evaluation["bonferroni_primario"], "estado": "evaluado"})
        family.append({"miembro": f"OPERAR contraste [p{k},∞)−[0,p{k})", "percentil": k, "valor": value,
                       "intervalo": evaluation["bonferroni_contraste"], "estado": "evaluado"})
    percentiles = list(zip(candidates.percentiles, candidates.values))
    for i, (k_low, v_low) in enumerate(percentiles):
        for k_high, v_high in percentiles[i + 1:]:
            member: Dict[str, Any] = {
                "miembro": f"VIGILAR par [p{k_low},p{k_high})",
                "percentiles": [k_low, k_high],
                "banda": [v_low, v_high],
            }
            if v_low == v_high:
                member["estado"] = "banda vacía por colapso de candidatos"
            elif operar is None:
                member["estado"] = "no evaluado: no existe min_score_operar"
            elif v_high != operar:
                member["estado"] = "no evaluado: el par no termina en el operar definitivo"
            elif (v_low, v_high) in vigilar_evaluations:
                member["estado"] = "evaluado"
                member["intervalo"] = vigilar_evaluations[(v_low, v_high)]["bonferroni_primario"]
                member["cumple_vigilar"] = vigilar_evaluations[(v_low, v_high)]["cumple_vigilar"]
            else:
                member["estado"] = "no evaluado: el recorrido VIGILAR cortó antes"
            family.append(member)
    if len(family) != BONFERRONI_M:
        raise AssertionError(f"la familia Bonferroni tiene {len(family)} miembros, no {BONFERRONI_M}")
    return family


def _group(records: Iterable[P3Record], key: Callable[[P3Record], str]) -> Dict[str, List[P3Record]]:
    groups: Dict[str, List[P3Record]] = {}
    for record in records:
        groups.setdefault(key(record), []).append(record)
    return groups


def _by_group(records: Sequence[P3Record], key: Callable[[P3Record], str], cuts: Sequence[float]) -> Dict[str, Any]:
    groups = _group(records, key)
    primary: List[Dict[str, Any]] = []
    delta: List[Dict[str, Any]] = []
    for name in sorted(groups):
        subset = groups[name]
        by_q = _group(subset, lambda r: quintile_of(r.score, cuts))
        primary.append(_interval_dict(primary_interval(name, subset)))
        delta.append(_interval_dict(paired_block_contrast(name, by_q.get("Q5", []), by_q.get("Q1", []))))
    return {"primary": primary, "delta": delta}


def _intra_asset(records: Sequence[P3Record], cuts: Sequence[float], thresholds: CapacityThresholds) -> Dict[str, Any]:
    high_q = {"Q4", "Q5"}
    low_q = {"Q1", "Q2"}
    cells: Dict[Tuple[str, int], Dict[str, List[float]]] = {}
    for record in records:
        if record.net_r is None:
            continue
        quintile = quintile_of(record.score, cuts)
        side = "high" if quintile in high_q else "low" if quintile in low_q else None
        if side is None:
            continue
        cells.setdefault((record.asset, record.block), {"high": [], "low": []})[side].append(record.net_r)
    pairs = {(asset, block) for asset, block in {(r.asset, r.block) for r in records}}
    calculable: Dict[Tuple[str, int], float] = {}
    excluded: List[Dict[str, Any]] = []
    for asset, block in sorted(pairs):
        cell = cells.get((asset, block), {"high": [], "low": []})
        if cell["high"] and cell["low"]:
            calculable[(asset, block)] = sum(cell["high"]) / len(cell["high"]) - sum(cell["low"]) / len(cell["low"])
        else:
            reason = "sin Q4∪Q5" if not cell["high"] else "sin Q1∪Q2"
            if not cell["high"] and not cell["low"]:
                reason = "sin Q4∪Q5 ni Q1∪Q2"
            excluded.append({"activo": asset, "bloque": block, "motivo": reason})
    blocks = sorted({block for _, block in pairs})
    block_values: List[Tuple[float, int]] = []
    empty_blocks: List[int] = []
    for block in blocks:
        diffs = [value for (asset, b), value in calculable.items() if b == block]
        if diffs:
            block_values.append((sum(diffs) / len(diffs), len(diffs)))
        else:
            empty_blocks.append(block)
    lower, upper = _interval(block_values, confidence=STANDARD_CONFIDENCE, n_resamples=STANDARD_RESAMPLES)
    by_asset: List[Dict[str, Any]] = []
    for asset in sorted({asset for asset, _ in pairs}):
        values = [(value, 1) for (a, _), value in sorted(calculable.items()) if a == asset]
        a_lower, a_upper = _interval(values, confidence=STANDARD_CONFIDENCE, n_resamples=STANDARD_RESAMPLES)
        by_asset.append(
            {
                "activo": asset,
                "mean": (sum(v for v, _ in values) / len(values)) if values else None,
                "n_blocks": len(values),
                "lower": a_lower,
                "upper": a_upper,
            }
        )
    n_blocks = len(block_values)
    return {
        "definicion": "media net_R(Q4∪Q5) − media net_R(Q1∪Q2) por activo y bloque, con quintiles globales",
        "primary": (sum(v for v, _ in block_values) / n_blocks) if n_blocks else None,
        "n_blocks": n_blocks,
        "lower": lower,
        "upper": upper,
        "estado": NO_CONCLUYENTE if n_blocks < thresholds.limited_blocks else "CALCULADO",
        "pares_calculables": len(calculable),
        "pares_excluidos": len(excluded),
        "pares_excluidos_detalle": excluded,
        "bloques_sin_activos_calculables": empty_blocks,
        "by_asset": by_asset,
    }


def _ablation(
    records: Sequence[P3Record],
    name: str,
    full_cuts: Sequence[float],
    population: HorizonPopulation,
    thresholds: CapacityThresholds,
) -> Dict[str, Any]:
    scores = [record.ablated_scores[name] for record in records]
    cuts = quintile_cuts(scores)
    by_q: Dict[str, List[P3Record]] = {}
    migration: Dict[str, Dict[str, int]] = {a: dict.fromkeys(QUINTILE_LABELS, 0) for a in QUINTILE_LABELS}
    for record, score in zip(records, scores):
        q = quintile_of(score, cuts.values)
        by_q.setdefault(q, []).append(record)
        migration[quintile_of(record.score, full_cuts)][q] += 1
    delta = paired_block_contrast(f"sin {name} Q5−Q1", by_q.get("Q5", []), by_q.get("Q1", []))
    if population.horizonte == CONFIRMATORY_HORIZONTE:
        verdict, reasons = veredicto_ordenacion(
            delta,
            horizon_valid=population.horizon_valid,
            resolution_insufficient=cuts.resolution_insufficient,
            thresholds=thresholds,
        )
    else:
        verdict, reasons = MEDIO_FORCED_VERDICT, ["medio solo por trazabilidad"]
    return {
        "formula": f"100·(points − points_{name})/(evaluable_max − max_{name})",
        "cuts": _cuts_dict(cuts),
        "quintiles": [_interval_dict(primary_interval(q, by_q.get(q, []))) for q in QUINTILE_LABELS],
        "delta_q5_q1": _interval_dict(delta),
        "veredicto_ordenacion": verdict,
        "veredicto_ordenacion_motivos": reasons,
        "migracion_desde_score_completo": migration,
        "nota": "descriptiva: la ablación no selecciona dimensiones ni cambia Score v2",
    }


def _block_by_quintile(records: Sequence[P3Record], cuts: Sequence[float]) -> List[Dict[str, Any]]:
    table: Dict[int, Dict[str, List[float]]] = {}
    for record in records:
        if record.net_r is None:
            continue
        table.setdefault(record.block, {q: [] for q in QUINTILE_LABELS})[quintile_of(record.score, cuts)].append(record.net_r)
    rows = []
    for block in sorted({r.block for r in records}):
        cells = table.get(block, {q: [] for q in QUINTILE_LABELS})
        rows.append(
            {
                "bloque": block,
                **{
                    q: {"n": len(cells[q]), "mean_net_r": (sum(cells[q]) / len(cells[q])) if cells[q] else None}
                    for q in QUINTILE_LABELS
                },
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Serialización
# ---------------------------------------------------------------------------


def _fmt_key(value: float) -> str:
    return repr(float(value))


def _interval_dict(interval: BlockInterval) -> Dict[str, Any]:
    data = asdict(interval)
    data["width"] = interval.width
    data["excluded_blocks"] = list(interval.excluded_blocks)
    return data


def _capacity_dict(summary: CapacitySummary) -> Dict[str, Any]:
    return {
        "capacidad": summary.verdict,
        "concluyente": summary.conclusive,
        "resolution": summary.resolution,
        "experimental_resolution": summary.resolution,
        "n": summary.nominal_n,
        "n_blocks": summary.n_blocks,
        "primary": summary.primary_expectancy_net_r,
        "lower": summary.primary_interval_lower,
        "upper": summary.primary_interval_upper,
        "width": summary.primary_interval_width,
        "exit_final_rate": summary.exit_final_rate,
        "ambiguous_rate": summary.ambiguous_rate,
        "motivos": list(summary.reasons),
    }


def _cuts_dict(cuts: QuintileCuts) -> Dict[str, Any]:
    return {
        "metodo": "nearest-rank x[(k*n + 99)//100 - 1]",
        "percentiles": list(cuts.percentiles),
        "values": list(cuts.values),
        "n": cuts.n,
        "distinct_scores": cuts.distinct_scores,
        "n_by_quintile": cuts.n_by_quintile,
        "status": cuts.status,
        "tied_pairs": [list(pair) for pair in cuts.tied_pairs],
    }


def identity(executor_sha: str, git_dirty: Optional[bool], config_hash_value: str) -> Dict[str, Any]:
    return {
        "preregistro_sha": PREREGISTRATION_SHA,
        "executor_sha": executor_sha,
        "git_dirty": git_dirty,
        "data_vintage_id": DATA_VINTAGE_ID,
        "universe_vintage_id": UNIVERSE_VINTAGE_ID,
        "config_hash": config_hash_value,
        "score_model_version": SCORE_MODEL_VERSION,
        "cost_pct": COST_PCT,
        "seed": SEED,
        "label": UNIVERSE_LABEL,
    }


def preflight_summary(population: HorizonPopulation) -> Dict[str, Any]:
    scores = [record.score for record in population.records]
    cuts = quintile_cuts(scores)
    out: Dict[str, Any] = {
        "horizonte": population.horizonte,
        "checks": [
            {"control": name, "observado": observed, "esperado": wanted, "ok": passed}
            for name, observed, wanted, passed in population.checks
        ],
        "ok": population.ok,
        "horizon_valid": population.horizon_valid,
        "shortest_occupied_block_sessions": population.shortest_block_sessions,
        "max_hold_bars": population.result.max_hold_bars,
        "cuts": _cuts_dict(cuts),
        "ablation_cuts": {
            name: _cuts_dict(quintile_cuts([r.ablated_scores[name] for r in population.records]))
            for name in ABLATED_DIMENSIONS
        },
    }
    if population.horizonte == CONFIRMATORY_HORIZONTE:
        candidates = candidate_set(scores)
        out["candidates"] = {
            "percentiles": list(candidates.percentiles),
            "values": list(candidates.values),
            "distinct": list(candidates.distinct),
            "collapses": candidates.collapses,
        }
    return out


def write_json(path: Path, data: Any) -> None:
    text = json.dumps(_finite(data), ensure_ascii=False, indent=2, default=_json_default, allow_nan=False)
    path.write_text(text + "\n", encoding="utf-8")


def _finite(value: Any) -> Any:
    """JSON estricto: infinito y NaN se escriben como texto explícito."""

    if isinstance(value, float):
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        if math.isnan(value):
            return "nan"
        return value
    if isinstance(value, dict):
        return {str(key): _finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite(item) for item in value]
    return value


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    raise TypeError(f"no serializable: {type(value).__name__}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Orquestación: preflight y ejecución confirmatoria única.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class P3Identity:
    executor_sha: str
    git_dirty: Optional[bool]
    config_hash: str

    def as_dict(self) -> Dict[str, Any]:
        return identity(self.executor_sha, self.git_dirty, self.config_hash)


def run_preflight(
    config: AdvisorConfig,
    universe: Universe,
    vintage: VintageLoad,
    ident: P3Identity,
    out_dir: Path,
) -> Tuple[bool, Dict[str, Any], Dict[str, HorizonPopulation]]:
    """Población, hashes, bloques y cortes sin desenlaces. Repetible."""

    out_dir.mkdir(parents=True, exist_ok=True)
    started = utc_now()
    populations = {
        horizonte: build_population(config, universe, vintage, horizonte, with_outcomes=False)
        for horizonte in HORIZONTES
    }
    report: Dict[str, Any] = {
        "fase": "preflight",
        "identidad": ident.as_dict(),
        "inicio_utc": started,
        "fin_utc": utc_now(),
        "horizontes": {h: preflight_summary(p) for h, p in populations.items()},
    }
    ok = all(p.ok for p in populations.values())
    report["ok"] = ok
    write_json(out_dir / "p3-preflight.json", report)
    (out_dir / "p3-preflight.txt").write_text(format_preflight(report), encoding="utf-8")
    return ok, report, populations


def run_confirmatory(
    config: AdvisorConfig,
    universe: Universe,
    vintage: VintageLoad,
    ident: P3Identity,
    out_dir: Path,
) -> Tuple[int, str]:
    """La única ejecución de P3. Devuelve el código de salida y el texto que imprime la CLI."""

    if out_dir.resolve() != CONFIRMATORY_OUTPUT_DIR.resolve():
        raise P3PreflightError(f"la ejecución confirmatoria solo escribe en {CONFIRMATORY_OUTPUT_DIR}")
    marker = out_dir / RUN_MARKER
    if marker.exists():
        raise P3AlreadyExecutedError(
            f"la ejecución confirmatoria ya se inició ({marker}); P3 no se repite (T-019 paso 3)"
        )
    if ident.git_dirty is not False:
        raise P3PreflightError(
            f"el árbol no está limpio o no se pudo comprobar (git_dirty={ident.git_dirty}): "
            "P3 solo se ejecuta sobre un commit congelado"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    if any(out_dir.iterdir()):
        raise P3AlreadyExecutedError(f"{out_dir} no está vacío: P3 no se repite ni se sobrescribe")

    ok, preflight, _ = run_preflight(config, universe, vintage, ident, out_dir / "preflight-interno")
    if not ok:
        return 2, format_preflight(preflight) + "PREFLIGHT FALLIDO: P3 NO SE EJECUTA.\n"

    started = utc_now()
    marker.write_text(
        json.dumps({"inicio_utc": started, "identidad": ident.as_dict()}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Las dos poblaciones con desenlaces se construyen y se verifican contra el
    # preflight ANTES de analizar ninguna: si una no lo reproduce, se para sin
    # haber calculado ningún estimador.
    populations: Dict[str, HorizonPopulation] = {}
    for horizonte in HORIZONTES:
        population = build_population(config, universe, vintage, horizonte, with_outcomes=True)
        expected_cuts = preflight["horizontes"][horizonte]["cuts"]["values"]
        observed_cuts = list(quintile_cuts([r.score for r in population.records]).values)
        if not population.ok or observed_cuts != expected_cuts:
            write_json(
                out_dir / "p3-parada.json",
                {
                    "identidad": ident.as_dict(),
                    "motivo": "la población o los cortes con desenlaces no coinciden con el preflight",
                    "horizonte": horizonte,
                    "checks": preflight_summary(population)["checks"],
                    "cortes_preflight": expected_cuts,
                    "cortes_ejecucion": observed_cuts,
                    "label": UNIVERSE_LABEL,
                },
            )
            return 3, "STOP → OWNER_DECISION_REQUIRED: la ejecución no reproduce el preflight. P3 no se repite.\n"
        populations[horizonte] = population

    outputs: Dict[str, Any] = {horizonte: analyze_horizon(populations[horizonte]) for horizonte in HORIZONTES}

    counters = comparison_counters(outputs)
    expected_counters = {"comparaciones_swing": 329, "comparaciones_medio_trazabilidad": 309, "comparaciones_totales": 638}
    result = {
        "fase": "confirmatoria",
        "identidad": ident.as_dict(),
        "inicio_utc": started,
        "fin_utc": utc_now(),
        "preflight": preflight,
        "horizontes": outputs,
        "contadores": counters,
        "contadores_preregistro": expected_counters,
        "contadores_coinciden": counters == expected_counters,
        "label": UNIVERSE_LABEL,
    }
    write_json(out_dir / "p3-resultado.json", result)
    write_tables(out_dir / "tablas", result)
    summary = format_result(result)
    (out_dir / "p3-resumen.md").write_text(summary, encoding="utf-8")
    return 0, summary


# ---------------------------------------------------------------------------
# Tablas TSV y resúmenes legibles
# ---------------------------------------------------------------------------


def _tsv(path: Path, header: Sequence[str], rows: Iterable[Sequence[Any]], ident: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# preregistro={ident['preregistro_sha']} executor={ident['executor_sha']} "
        f"data_vintage_id={ident['data_vintage_id']} universe_vintage_id={ident['universe_vintage_id']} "
        f"config_hash={ident['config_hash']} score_model_version={ident['score_model_version']} "
        f"cost_pct={ident['cost_pct']} seed={ident['seed']}",
        f"# {UNIVERSE_LABEL}",
        "\t".join(header),
    ]
    lines.extend("\t".join(_cell(value) for value in row) for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(value)
    return str(value)


def write_tables(directory: Path, result: Mapping[str, Any]) -> None:
    ident = result["identidad"]
    for horizonte, out in result["horizontes"].items():
        _tsv(
            directory / f"{horizonte}-quintiles.tsv",
            ["quintil", "n", "n_blocks", "primario", "ic_lower", "ic_upper", "capacidad", "concluyente",
             "experimental_resolution",
             "expectancy_agrupada", "tf_sobre_tf_sf", "p_obj_antes_stop_lower", "p_obj_antes_stop_upper",
             "profit_factor", "mediana_mae_ganadoras", "mediana_mfe_sin_objetivo_lower",
             "mediana_mfe_sin_objetivo_upper", "exit_final", "ambiguedad"],
            (
                [q["label"], q["primary"]["n"], q["primary"]["n_blocks"], q["primary"]["mean"],
                 q["primary"]["lower"], q["primary"]["upper"], q["capacidad"]["capacidad"],
                 q["capacidad"]["concluyente"], q["capacidad"]["experimental_resolution"],
                 q["secundarias"]["expectancy_pooled_net_r"],
                 q["secundarias"]["target_first_rate"], q["secundarias"]["target_before_stop_lower"],
                 q["secundarias"]["target_before_stop_upper"], q["secundarias"]["profit_factor"],
                 q["secundarias"]["median_mae_winners_r"], q["secundarias"]["median_mfe_without_target_lower_r"],
                 q["secundarias"]["median_mfe_without_target_upper_r"], q["secundarias"]["exit_final_rate"],
                 q["secundarias"]["ambiguous_rate"]]
                for q in out["quintiles"]
            ),
            ident,
        )
        _tsv(
            directory / f"{horizonte}-bloque-x-quintil.tsv",
            ["bloque", *[f"{q}_{m}" for q in QUINTILE_LABELS for m in ("n", "mean_net_r")]],
            ([row["bloque"], *[row[q][m] for q in QUINTILE_LABELS for m in ("n", "mean_net_r")]]
             for row in out["block_by_quintile"]),
            ident,
        )
        contrasts = [out["delta_q5_q1"], *out["adjacent_contrasts"]]
        _tsv(
            directory / f"{horizonte}-contrastes.tsv",
            ["contraste", "mean", "n_blocks", "ic_lower", "ic_upper", "width", "bloques_excluidos"],
            ([c["label"], c["mean"], c["n_blocks"], c["lower"], c["upper"], c["width"],
              ",".join(str(b) for b in c["excluded_blocks"])] for c in contrasts),
            ident,
        )
        for group in ("regions", "assets"):
            _tsv(
                directory / f"{horizonte}-{'regiones' if group == 'regions' else 'activos'}.tsv",
                ["grupo", "n", "n_blocks", "primario", "ic_lower", "ic_upper",
                 "delta_q5_q1", "delta_n_blocks", "delta_ic_lower", "delta_ic_upper"],
                ([p["label"], p["n"], p["n_blocks"], p["mean"], p["lower"], p["upper"],
                  d["mean"], d["n_blocks"], d["lower"], d["upper"]]
                 for p, d in zip(out[group]["primary"], out[group]["delta"])),
                ident,
            )
        intra = out["intra_asset"]
        _tsv(
            directory / f"{horizonte}-intra-activo.tsv",
            ["activo", "mean", "n_blocks", "ic_lower", "ic_upper"],
            ([row["activo"], row["mean"], row["n_blocks"], row["lower"], row["upper"]] for row in intra["by_asset"]),
            ident,
        )
        _tsv(
            directory / f"{horizonte}-intra-activo-pares-excluidos.tsv",
            ["activo", "bloque", "motivo"],
            ([row["activo"], row["bloque"], row["motivo"]] for row in intra["pares_excluidos_detalle"]),
            ident,
        )
        _tsv(
            directory / f"{horizonte}-ablaciones.tsv",
            ["dimension", "quintil", "n", "n_blocks", "primario", "ic_lower", "ic_upper"],
            ([name, q["label"], q["n"], q["n_blocks"], q["mean"], q["lower"], q["upper"]]
             for name, ab in out["ablations"].items() for q in ab["quintiles"]),
            ident,
        )
        if "calibration" in out:
            cal = out["calibration"]
            _tsv(
                directory / f"{horizonte}-candidatos.tsv",
                ["candidato", "percentiles", "n_upper", "capacidad", "concluyente",
                 "bonf_primario_lower", "bonf_primario_upper", "bonf_contraste_lower", "bonf_contraste_upper",
                 "profit_factor", "c1", "c2", "c3", "c4", "c5", "cumple_operar"],
                ([e["candidato"], ",".join(str(k) for k in e["percentiles"]), e["n_upper"],
                  e["capacidad"]["capacidad"], e["capacidad"]["concluyente"],
                  e["bonferroni_primario"]["lower"], e["bonferroni_primario"]["upper"],
                  e["bonferroni_contraste"]["lower"], e["bonferroni_contraste"]["upper"], e["profit_factor"],
                  *e["condiciones"].values(), e["cumple_operar"]] for e in cal["evaluations"]),
                ident,
            )
            _tsv(
                directory / f"{horizonte}-familia-bonferroni.tsv",
                ["miembro", "estado", "ic_lower", "ic_upper"],
                ([m["miembro"], m["estado"], (m.get("intervalo") or {}).get("lower"),
                  (m.get("intervalo") or {}).get("upper")] for m in cal["bonferroni_family"]),
                ident,
            )


def _f(value: Any, digits: int = 4) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "sí" if value else "no"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def format_preflight(report: Mapping[str, Any]) -> str:
    ident = report["identidad"]
    lines = [
        "P3 — PREFLIGHT SIN DESENLACES",
        *(f"{key}: {value}" for key, value in ident.items()),
        f"resultado: {'OK' if report['ok'] else 'FALLIDO'}",
        "",
    ]
    for horizonte, out in report["horizontes"].items():
        lines.append(f"=== {horizonte} ===")
        for check in out["checks"]:
            lines.append(f"  [{'OK' if check['ok'] else 'FALLA'}] {check['control']}: {check['observado']} (esperado {check['esperado']})")
        lines.append(
            f"  horizonte válido: {_f(out['horizon_valid'])} (bloque ocupado más corto "
            f"{out['shortest_occupied_block_sessions']} sesiones; MAX_HOLD_BARS {out['max_hold_bars']})"
        )
        cuts = out["cuts"]
        lines.append(
            f"  cortes p20/p40/p60/p80: {cuts['values']} | distintos {cuts['distinct_scores']} | "
            f"n por quintil {cuts['n_by_quintile']} | {cuts['status']}"
        )
        for name, ab in out["ablation_cuts"].items():
            lines.append(f"  ablación sin {name}: cortes {ab['values']} | {ab['status']} | n {ab['n_by_quintile']}")
        if "candidates" in out:
            cand = out["candidates"]
            lines.append(
                f"  candidatos p50..p90: {cand['values']} | distintos {cand['distinct']} | colapsos {cand['collapses'] or 'ninguno'}"
            )
        lines.append("")
    lines.append(UNIVERSE_LABEL)
    return "\n".join(lines) + "\n"


def format_result(result: Mapping[str, Any]) -> str:
    ident = result["identidad"]
    lines = ["# P3 — resultado de la ejecución confirmatoria única", ""]
    lines += [f"- {key}: `{value}`" for key, value in ident.items()]
    lines += [f"- inicio: {result['inicio_utc']}", f"- fin: {result['fin_utc']}", "", f"_{UNIVERSE_LABEL}_", ""]
    for horizonte, out in result["horizontes"].items():
        lines.append(f"## {horizonte} ({'confirmatorio' if out['confirmatorio'] else 'solo trazabilidad'})")
        g = out["global_primary"]
        lines.append(f"- n {out['n']}, bloques {out['blocks_occupied']}, horizonte válido {_f(out['horizon_valid'])}")
        lines.append(f"- primario global: {_f(g['mean'])} R, IC95 [{_f(g['lower'])}, {_f(g['upper'])}], {g['n_blocks']} bloques")
        cuts = out["cuts"]
        lines.append(f"- cortes p20/p40/p60/p80: {cuts['values']} ({cuts['status']}; {cuts['distinct_scores']} valores distintos)")
        d = out["delta_q5_q1"]
        lines.append(
            f"- **Δ Q5−Q1: {_f(d['mean'])} R, IC95 [{_f(d['lower'])}, {_f(d['upper'])}], anchura {_f(d['width'])}, "
            f"{d['n_blocks']} bloques** (excluidos {d['excluded_blocks'] or 'ninguno'})"
        )
        lines.append(f"- **veredicto_ordenacion: {out['veredicto_ordenacion']}** {out['veredicto_ordenacion_motivos'] or ''}")
        if out["confirmatorio"]:
            lines.append("- SUFICIENTE alcanzable: " + ("sí" if out["suficiente_alcanzable"] else "no (menos de 25 bloques)"))
        lines.append("")
        lines.append("| quintil | n | primario | IC95 | capacidad | expectancy agrupada | PF |")
        lines.append("|---|---|---|---|---|---|---|")
        for q in out["quintiles"]:
            p = q["primary"]
            lines.append(
                f"| {q['label']} | {p['n']} | {_f(p['mean'])} | [{_f(p['lower'])}, {_f(p['upper'])}] | "
                f"{q['capacidad']['capacidad']}{'' if q['capacidad']['concluyente'] else ' (no concluyente)'} | "
                f"{_f(q['secundarias']['expectancy_pooled_net_r'])} | {_f(q['secundarias']['profit_factor'])} |"
            )
        lines.append("")
        lines.append("Contrastes adyacentes: " + "; ".join(
            f"{c['label']} {_f(c['mean'])} [{_f(c['lower'])}, {_f(c['upper'])}]" for c in out["adjacent_contrasts"]
        ))
        lines.append("")
        lines.append("Regiones (primario | Δ Q5−Q1): " + "; ".join(
            f"{p['label']} {_f(p['mean'])} | {_f(dd['mean'])}" for p, dd in zip(out["regions"]["primary"], out["regions"]["delta"])
        ))
        intra = out["intra_asset"]
        lines.append(
            f"Intra-activo (Q4∪Q5 − Q1∪Q2): {_f(intra['primary'])} R, IC95 [{_f(intra['lower'])}, {_f(intra['upper'])}], "
            f"{intra['n_blocks']} bloques, {intra['estado']}; pares calculables {intra['pares_calculables']}, "
            f"excluidos {intra['pares_excluidos']}, bloques sin activos {intra['bloques_sin_activos_calculables'] or 'ninguno'}"
        )
        for name, ab in out["ablations"].items():
            dd = ab["delta_q5_q1"]
            lines.append(
                f"Ablación sin {name}: Δ Q5−Q1 {_f(dd['mean'])} [{_f(dd['lower'])}, {_f(dd['upper'])}], "
                f"{dd['n_blocks']} bloques, cortes {ab['cuts']['status']}, veredicto {ab['veredicto_ordenacion']} (descriptiva)"
            )
        if "calibration" in out:
            cal = out["calibration"]
            lines.append("")
            lines.append(f"### Calibración swing (Bonferroni m={cal['bonferroni_m']}, {cal['bonferroni_confidence']}, {cal['bonferroni_resamples']} remuestreos)")
            lines.append(f"- candidatos p50..p90: {cal['candidates']['values']}; distintos {cal['candidates']['distinct']}; colapsos {cal['candidates']['collapses'] or 'ninguno'}")
            for e in cal["evaluations"]:
                lines.append(
                    f"- c={e['candidato']:g} (p{','.join(str(k) for k in e['percentiles'])}): n {e['n_upper']}, "
                    f"capacidad {e['capacidad']['capacidad']}{'' if e['capacidad']['concluyente'] else ' no concluyente'}, "
                    f"Bonf. primario [{_f(e['bonferroni_primario']['lower'])}, {_f(e['bonferroni_primario']['upper'])}], "
                    f"Bonf. contraste [{_f(e['bonferroni_contraste']['lower'])}, {_f(e['bonferroni_contraste']['upper'])}], "
                    f"PF {_f(e['profit_factor'])} → {'CUMPLE' if e['cumple_operar'] else 'no cumple'} {e['condiciones']}"
                )
            if cal["min_score_operar"] is None:
                lines.append("- **min_score_operar: ninguno → swing queda calibrated: false; no se publica umbral**")
            else:
                lines.append(f"- **min_score_operar: {cal['min_score_operar']:g}**")
                lines.append(f"- recorrido VIGILAR: {cal['vigilar_recorrido']}")
                lines.append(f"- **min_score_vigilar: {cal['min_score_vigilar']:g}**" + (" (franja VIGILAR vacía)" if cal["franja_vigilar_vacia"] else ""))
            lines.append(f"- familia Bonferroni: {len(cal['bonferroni_family'])} miembros")
        lines.append("")
    lines.append("## Contadores")
    lines += [f"- {key}: {value} (pre-registro {result['contadores_preregistro'][key]})" for key, value in result["contadores"].items()]
    if not result["contadores_coinciden"]:
        lines.append("- **LOS CONTADORES DIVERGEN DEL PRE-REGISTRO: interpretación detenida hasta explicarlo.**")
    lines.append("")
    lines.append(f"_{UNIVERSE_LABEL}_")
    return "\n".join(lines) + "\n"
