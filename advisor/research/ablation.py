"""Ablación P2.4 del ratio beneficio/riesgo dentro del score."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from advisor.research.capacity import (
    DEFAULT_RESAMPLES,
    DEFAULT_SEED,
    DEFAULT_THRESHOLDS,
    CapacityComparison,
    CapacityReport,
    CapacitySummary,
    CapacityThresholds,
    assess_capacity,
)
from advisor.research.event_study import (
    SCORE_BANDS,
    BandSummary,
    EventStudyResult,
    EventStudySignal,
    score_band,
    summarize_by_score_band,
)
from advisor.research.observations import DimensionObservation
from advisor.universe.models import Universe

RR_DIMENSION = "beneficio_riesgo"
CAPACITY_PAIRS: Tuple[Tuple[str, str], ...] = (
    ("<50", "50-60"),
    ("50-60", "60-70"),
    ("60-70", "70-80"),
    ("70-80", "80+"),
    ("50-60", "80+"),
)


@dataclass(frozen=True)
class AblationRecord:
    signal_id: str
    data_vintage_id: str
    asset: str
    signal_timestamp: datetime
    score_full: float
    score_without_rr: float
    rr_contribution_points: float
    rr_dimension_points: float
    rr_dimension_max: float
    rr_dimension_share: float
    evaluable_max: float
    evaluable_max_without_rr: float
    risk_pp: float
    rr_gross: float
    rr_net: float
    band_full: str
    band_without_rr: str
    exit_status: str
    net_r_multiple: Optional[float]
    bars_held: int


@dataclass(frozen=True)
class AblationBand:
    label: str
    n: int
    share_of_total: float
    band_summary: BandSummary
    capacity: CapacitySummary
    median_rr_dimension_points: Optional[float]
    p10_rr_dimension_points: Optional[float]
    p90_rr_dimension_points: Optional[float]
    median_rr_contribution_points: Optional[float]
    median_risk_pp: Optional[float]
    median_rr_gross: Optional[float]
    median_rr_net: Optional[float]
    median_cost_over_risk: Optional[float]


@dataclass(frozen=True)
class AblationResult:
    data_vintage_id: str
    horizonte: str
    cost_pct: float
    warmup_bars: int
    max_hold_bars: int
    evaluated_assets: int
    source_skipped: List[Tuple[str, str]]
    rr_dimension_name: str
    rr_dimension_max: float
    records: List[AblationRecord]
    bands_full: List[AblationBand]
    bands_ablated: List[AblationBand]
    capacity_full: CapacityReport
    capacity_ablated: CapacityReport
    migration: Dict[Tuple[str, str], int]
    skipped: List[Tuple[str, str]]
    n_without_net_r: int
    evaluable_max_counts: Dict[float, int]
    evaluable_max_without_rr_counts: Dict[float, int]
    universe_vintage_id: str = ""


def build_ablation_record(signal: EventStudySignal, cost_pct: float) -> Tuple[Optional[AblationRecord], Optional[str]]:
    """Reconstruye la nota sin RR desde la descomposición guardada."""

    obs = signal.observation
    dims = obs.dimensions
    if not dims:
        return None, "observación sin descomposición por dimensión"
    rr = next((dimension for dimension in dims if dimension.name == RR_DIMENSION), None)
    if rr is None:
        return None, "sin dimensión beneficio_riesgo"

    points_total = sum(dimension.points for dimension in dims)
    if obs.evaluable_max <= 0:
        return None, "sin puntos evaluables"
    reconstructed = 100.0 * points_total / obs.evaluable_max
    if not math.isclose(reconstructed, obs.score_value, rel_tol=1e-9, abs_tol=1e-9):
        return None, "score incoherente con la descomposición por dimensión"

    if not rr.available:
        score_without_rr = obs.score_value
        evaluable_max_without_rr = obs.evaluable_max
        rr_points = 0.0
    else:
        evaluable_max_without_rr = obs.evaluable_max - rr.max
        if evaluable_max_without_rr <= 0:
            return None, "sin puntos evaluables tras quitar el RR"
        rr_points = rr.points
        score_without_rr = 100.0 * (points_total - rr_points) / evaluable_max_without_rr

    if signal.managed.risk_pp <= 0:
        return None, "risk_pp no positivo"
    rr_gross = ((signal.managed.target / signal.managed.entry_price) - 1.0) * 100.0 / signal.managed.risk_pp
    rr_net = rr_gross - cost_pct / signal.managed.risk_pp
    return (
        AblationRecord(
            signal_id=obs.signal_id,
            data_vintage_id=obs.data_vintage_id,
            asset=obs.asset,
            signal_timestamp=obs.signal_timestamp,
            score_full=obs.score_value,
            score_without_rr=score_without_rr,
            rr_contribution_points=obs.score_value - score_without_rr,
            rr_dimension_points=rr_points,
            rr_dimension_max=rr.max,
            rr_dimension_share=100.0 * rr_points / rr.max if rr.max else 0.0,
            evaluable_max=obs.evaluable_max,
            evaluable_max_without_rr=evaluable_max_without_rr,
            risk_pp=signal.managed.risk_pp,
            rr_gross=rr_gross,
            rr_net=rr_net,
            band_full=score_band(obs.score_value),
            band_without_rr=score_band(score_without_rr),
            exit_status=signal.managed.exit_status,
            net_r_multiple=signal.managed.net_r_multiple,
            bars_held=signal.managed.bars_held,
        ),
        None,
    )


def run_ablation(
    result: EventStudyResult,
    *,
    universe: Universe,
    thresholds: CapacityThresholds = DEFAULT_THRESHOLDS,
) -> AblationResult:
    records: List[AblationRecord] = []
    skipped: List[Tuple[str, str]] = []
    valid_signals: List[EventStudySignal] = []

    for signal in result.signals:
        record, reason = build_ablation_record(signal, result.cost_pct)
        if record is None:
            skipped.append((signal.observation.signal_id, reason or "señal descartada"))
            continue
        records.append(record)
        valid_signals.append(signal)

    scores_without_rr = {record.signal_id: record.score_without_rr for record in records}

    def band_of_ablated(signal: EventStudySignal) -> str:
        return score_band(scores_without_rr[signal.observation.signal_id])

    comparable = replace(result, signals=valid_signals)
    bands_full_summary = summarize_by_score_band(valid_signals)
    bands_ablated_summary = summarize_by_score_band(valid_signals, band_of=band_of_ablated)
    capacity_full = assess_capacity(comparable, universe=universe, thresholds=thresholds, comparisons=CAPACITY_PAIRS)
    capacity_ablated = assess_capacity(
        comparable,
        universe=universe,
        thresholds=thresholds,
        comparisons=CAPACITY_PAIRS,
        band_of=band_of_ablated,
    )
    migration = _migration(records)
    _validate_migration(migration, bands_full_summary, bands_ablated_summary, len(records))

    rr_dimension_max = _first_rr_dimension(records, valid_signals)
    return AblationResult(
        data_vintage_id=result.data_vintage_id,
        universe_vintage_id=result.universe_vintage_id,
        horizonte=result.horizonte,
        cost_pct=result.cost_pct,
        warmup_bars=result.warmup_bars,
        max_hold_bars=result.max_hold_bars,
        evaluated_assets=len(result.evaluated_assets),
        source_skipped=list(result.skipped),
        rr_dimension_name=RR_DIMENSION,
        rr_dimension_max=rr_dimension_max,
        records=records,
        bands_full=_build_bands(records, bands_full_summary, capacity_full.bands, result.cost_pct, by_ablated=False),
        bands_ablated=_build_bands(records, bands_ablated_summary, capacity_ablated.bands, result.cost_pct, by_ablated=True),
        capacity_full=capacity_full,
        capacity_ablated=capacity_ablated,
        migration=migration,
        skipped=skipped,
        n_without_net_r=sum(1 for record in records if record.net_r_multiple is None),
        evaluable_max_counts=_counts(record.evaluable_max for record in records),
        evaluable_max_without_rr_counts=_counts(record.evaluable_max_without_rr for record in records),
    )


def format_ablation_report(result: AblationResult) -> str:
    lines = [
        "# Ablación P2.4 del score",
        "",
        f"Cosecha: {result.data_vintage_id}",
        f"Universo: {result.universe_vintage_id}",
        f"Horizonte: {result.horizonte} | coste {result.cost_pct:.2f}% | warmup {result.warmup_bars} velas | "
        f"horizonte máximo {result.max_hold_bars} velas",
        f"Activos evaluados: {result.evaluated_assets} | señales evaluadas: {len(result.records)}",
        f"Descartes P2.3: {len(result.source_skipped)} | descartes ablación: {len(result.skipped)}"
        f"{_format_reasons(result.skipped)}",
        f"Sin net_R: {result.n_without_net_r}",
        f"evaluable_max observado: {_format_counts(result.evaluable_max_counts)}",
        f"evaluable_max sin RR observado: {_format_counts(result.evaluable_max_without_rr_counts)}",
        f"Dimensión ablacionada: {result.rr_dimension_name} | peso {result.rr_dimension_max:.1f} | "
        f"denominador resultante típico {_typical_without_rr(result):.1f}",
        "Intervalos: P(objetivo antes de stop) usa bootstrap P2.6 sobre medias por bloque; "
        "net_R se cubre en comparacion-pareada P2.6.",
        "Bootstrap capacidad: "
        f"semilla={DEFAULT_SEED}; remuestreos={DEFAULT_RESAMPLES}",
        "Umbrales NO recalibrados: la tabla B usa los mismos cortes de SCORE_BANDS sobre una nota normalizada "
        "sobre 60 puntos. Recalibrar es P3.",
        "",
        "TABLA A - Ordenación con el score COMPLETO",
        _format_order_header(),
    ]
    lines.extend(_format_order_band(band) for band in result.bands_full)
    lines.extend(["", "TABLA B - Ordenación con el score SIN RR", _format_order_header()])
    lines.extend(_format_order_band(band) for band in result.bands_ablated)
    lines.extend(["", "TABLA C - Migración de bandas (filas score completo, columnas score sin RR)"])
    lines.extend(_format_migration(result.migration))
    lines.extend(["", _format_threshold_crossings(result.records)])
    lines.extend(["", "TABLA D - Diagnóstico del RR por banda (score completo)", _format_rr_header()])
    lines.extend(_format_rr_band(band) for band in result.bands_full)
    lines.extend(["", "Conclusiones:", *_format_conclusions(result)])
    return "\n".join(lines)


def _build_bands(
    records: Sequence[AblationRecord],
    summaries: Sequence[BandSummary],
    capacities: Sequence[CapacitySummary],
    cost_pct: float,
    *,
    by_ablated: bool,
) -> List[AblationBand]:
    by_capacity = {capacity.label: capacity for capacity in capacities}
    total = len(records)
    bands: List[AblationBand] = []
    for summary in summaries:
        bucket = [
            record
            for record in records
            if (record.band_without_rr if by_ablated else record.band_full) == summary.label
        ]
        rr_points = [record.rr_dimension_points for record in bucket]
        bands.append(
            AblationBand(
                label=summary.label,
                n=len(bucket),
                share_of_total=len(bucket) / total if total else 0.0,
                band_summary=summary,
                capacity=by_capacity[summary.label],
                median_rr_dimension_points=_median(rr_points),
                p10_rr_dimension_points=_percentile(rr_points, 10),
                p90_rr_dimension_points=_percentile(rr_points, 90),
                median_rr_contribution_points=_median([record.rr_contribution_points for record in bucket]),
                median_risk_pp=_median([record.risk_pp for record in bucket]),
                median_rr_gross=_median([record.rr_gross for record in bucket]),
                median_rr_net=_median([record.rr_net for record in bucket]),
                median_cost_over_risk=_median([cost_pct / record.risk_pp for record in bucket]),
            )
        )
    return bands


def _migration(records: Sequence[AblationRecord]) -> Dict[Tuple[str, str], int]:
    values = {(left, right): 0 for left, _, _ in SCORE_BANDS for right, _, _ in SCORE_BANDS}
    for record in records:
        values[(record.band_full, record.band_without_rr)] += 1
    return values


def _validate_migration(
    migration: Dict[Tuple[str, str], int],
    full: Sequence[BandSummary],
    ablated: Sequence[BandSummary],
    total: int,
) -> None:
    if sum(migration.values()) != total:
        raise RuntimeError("la migración no cuadra con el número de registros")
    for band in full:
        if sum(count for (left, _), count in migration.items() if left == band.label) != band.total:
            raise RuntimeError(f"la migración no cuadra para la fila {band.label}")
    for band in ablated:
        if sum(count for (_, right), count in migration.items() if right == band.label) != band.total:
            raise RuntimeError(f"la migración no cuadra para la columna {band.label}")


def _first_rr_dimension(records: Sequence[AblationRecord], signals: Sequence[EventStudySignal]) -> float:
    if records:
        return records[0].rr_dimension_max
    for signal in signals:
        rr = _rr_dimension(signal.observation.dimensions)
        if rr is not None:
            return rr.max
    return 0.0


def _rr_dimension(dimensions: Sequence[DimensionObservation]) -> Optional[DimensionObservation]:
    return next((dimension for dimension in dimensions if dimension.name == RR_DIMENSION), None)


def _counts(values: Iterable[float]) -> Dict[float, int]:
    counts: Dict[float, int] = {}
    for value in values:
        key = round(float(value), 10)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _format_order_header() -> str:
    return (
        "banda   n       %total  target stop  ambig tiempo final  "
        "P(objetivo antes de stop)  net_R medio  n net_R  EXIT_FINAL  resolución    veredicto        motivos"
    )


def _format_order_band(band: AblationBand) -> str:
    summary = band.band_summary
    capacity = band.capacity
    n_net_r = summary.total - summary.ambiguous
    if capacity.conclusive:
        interval = f"[{capacity.interval_lower:.3f}, {capacity.interval_upper:.3f}]"
        mean = _fmt_optional(summary.mean_net_r_multiple)
        verdict = capacity.verdict
    else:
        interval = "NO CONCLUYENTE"
        mean = "NO CONCLUYENTE"
        verdict = "NO CONCLUYENTE"
    return (
        f"{band.label:<6} {band.n:>7} {band.share_of_total:>7.2%} "
        f"{summary.target_first:>6} {summary.stop_first:>5} {summary.ambiguous:>6} "
        f"{summary.time_exit:>6} {summary.final_exit:>5}  "
        f"{interval:>26} {mean:>12} {n_net_r:>8} {capacity.exit_final_rate:>10.2%} "
        f"{capacity.resolution:<12} {verdict:<16} {_reasons(capacity)}"
    )


def _format_rr_header() -> str:
    return (
        "banda   n       mediana RR puntos  p10    p90    mediana contrib.  "
        "mediana risk_pp  mediana RR bruto  mediana RR neto  mediana coste/riesgo  veredicto"
    )


def _format_rr_band(band: AblationBand) -> str:
    verdict = band.capacity.verdict if band.capacity.conclusive else "NO CONCLUYENTE"
    return (
        f"{band.label:<6} {band.n:>7} "
        f"{_fmt_optional(band.median_rr_dimension_points):>17} "
        f"{_fmt_optional(band.p10_rr_dimension_points):>6} "
        f"{_fmt_optional(band.p90_rr_dimension_points):>6} "
        f"{_fmt_optional(band.median_rr_contribution_points):>17} "
        f"{_fmt_optional(band.median_risk_pp):>15} "
        f"{_fmt_optional(band.median_rr_gross):>17} "
        f"{_fmt_optional(band.median_rr_net):>16} "
        f"{_fmt_optional(band.median_cost_over_risk):>21} "
        f"{verdict}"
    )


def _format_migration(migration: Dict[Tuple[str, str], int]) -> List[str]:
    labels = [label for label, _, _ in SCORE_BANDS]
    lines = ["completo\\sinRR " + " ".join(f"{label:>8}" for label in labels) + f" {'total':>8}"]
    column_totals = dict.fromkeys(labels, 0)
    for left in labels:
        row_total = 0
        cells: List[str] = []
        for right in labels:
            value = migration[(left, right)]
            row_total += value
            column_totals[right] += value
            cells.append(f"{value:>8}")
        lines.append(f"{left:<14} " + " ".join(cells) + f" {row_total:>8}")
    lines.append(
        f"{'total':<14} "
        + " ".join(f"{column_totals[label]:>8}" for label in labels)
        + f" {sum(column_totals.values()):>8}"
    )
    return lines


def _format_threshold_crossings(records: Sequence[AblationRecord]) -> str:
    down60 = sum(1 for record in records if record.score_full >= 60.0 and record.score_without_rr < 60.0)
    up60 = sum(1 for record in records if record.score_full < 60.0 and record.score_without_rr >= 60.0)
    down70 = sum(1 for record in records if record.score_full >= 70.0 and record.score_without_rr < 70.0)
    up70 = sum(1 for record in records if record.score_full < 70.0 and record.score_without_rr >= 70.0)
    return f"Cruces informativos: corte 60 baja={down60}, sube={up60}; corte 70 baja={down70}, sube={up70}."


def _format_conclusions(result: AblationResult) -> List[str]:
    conclusions: List[str] = []
    comparison = _comparison_by_label(result.capacity_ablated, "50-60 vs 80+")
    if comparison is None or not comparison.conclusive or comparison.verdict != "SUFICIENTE":
        reasons = comparison.reasons if comparison is not None else ("comparación no disponible",)
        conclusions.append(f"- Score sin RR 50-60 vs 80+: NO CONCLUYENTE ({'; '.join(reasons)})")
    else:
        conclusions.append("- Score sin RR 50-60 vs 80+: comparación suficiente según P2.5.")

    rr_ranges = [
        (band.p10_rr_dimension_points, band.p90_rr_dimension_points)
        for band in result.bands_full
        if band.capacity.conclusive and band.p10_rr_dimension_points is not None and band.p90_rr_dimension_points is not None
    ]
    if rr_ranges and all(math.isclose(p10, p90) for p10, p90 in rr_ranges):
        conclusions.append("- RR por dimensión: casi constante en bandas concluyentes; eso mide baja variación, no poder predictivo.")
    else:
        conclusions.append("- RR por dimensión: NO CONCLUYENTE en al menos una banda necesaria.")
    conclusions.append("- Ningún umbral se recalibra en P2.4.")
    return conclusions[:3]


def _comparison_by_label(report: CapacityReport, label: str) -> Optional[CapacityComparison]:
    return next((comparison for comparison in report.comparisons if comparison.label == label), None)


def _format_reasons(skipped: Sequence[Tuple[str, str]]) -> str:
    if not skipped:
        return ""
    counts: Dict[str, int] = {}
    for _, reason in skipped:
        counts[reason] = counts.get(reason, 0) + 1
    return " | motivos: " + ", ".join(f"{reason}={count}" for reason, count in sorted(counts.items()))


def _format_counts(counts: Dict[float, int]) -> str:
    return ", ".join(f"{value:.1f} ({count})" for value, count in sorted(counts.items())) or "N/D"


def _typical_without_rr(result: AblationResult) -> float:
    if not result.evaluable_max_without_rr_counts:
        return 0.0
    return max(result.evaluable_max_without_rr_counts.items(), key=lambda item: item[1])[0]


def _reasons(summary: CapacitySummary) -> str:
    return "; ".join(summary.reasons) if summary.reasons else "-"


def _fmt_optional(value: Optional[float]) -> str:
    return "N/D" if value is None else f"{value:.3f}"


def _median(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _percentile(values: Sequence[float], percentile: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile / 100.0
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[int(rank)]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)
