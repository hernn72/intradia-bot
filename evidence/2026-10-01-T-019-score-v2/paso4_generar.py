"""Genera la evidencia documental de T-019 paso 4 sin ejecutar P3."""

from __future__ import annotations

import csv
import hashlib
import json
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import advisor.research.event_study as event_study  # noqa: E402
from advisor.config import load_config  # noqa: E402
from advisor.context.point_in_time import PointInTimeContextResolver, analysis_timestamp_for_signal  # noqa: E402
from advisor.data.freshness import mercado_para_simbolo  # noqa: E402
from advisor.data.sessions import session_date_of  # noqa: E402
from advisor.research.p3 import (  # noqa: E402
    DATA_VINTAGE_ID,
    EXPECTED_POPULATION,
    MEDIO_FORCED_VERDICT,
    QUINTILE_LABELS,
    UNIVERSE_LABEL,
    build_population,
    canonical_score,
    nearest_rank_cut,
    quintile_cuts,
    quintile_of,
)
from advisor.research.vintage import frozen_close, load_vintage  # noqa: E402
from advisor.universe.loader import load_universe  # noqa: E402

OUT = Path(__file__).resolve().parent
TABLES = OUT / "tablas"
P3 = ROOT / "evidence/2026-09-30-T-019-paso3-p3"
RUN = P3 / "run"
PASO2A = ROOT / "evidence/2026-09-30-T-019-paso2a-code"
PERCENTILES = (1, 5, 10, 25, 50, 75, 90, 95, 99)
SCALES = (
    ("A", "v1 PIT: catalizador + técnico + RR + contexto + convicción; fundamental ausente; sobre 80"),
    ("B", "v1 PIT sin RR; sobre 60"),
    ("C", "v1 PIT sin convicción; sobre 70"),
    ("D", "v2 PIT: catalizador + técnico + contexto; sobre 50"),
)
Key = tuple[str, int]


def _no_outcome(*_args: object, **_kwargs: object) -> None:
    return None


def main() -> None:
    TABLES.mkdir(exist_ok=True)
    cfg = load_config("config.yaml")
    universe = load_universe(cfg.universe_path)
    vintage = load_vintage(DATA_VINTAGE_ID)
    populations: dict[str, Any] = {}
    v1_pit: dict[str, dict[Key, Any]] = {}
    for horizonte in ("swing", "medio"):
        populations[horizonte] = _population(cfg, universe, vintage, horizonte)
        v1_pit[horizonte] = _v1_observations(cfg, universe, vintage, horizonte)
    generate_impact(populations, v1_pit)
    generate_context(cfg, universe, vintage, populations)
    generate_sap(universe, vintage, populations, v1_pit)
    generate_delta_block()
    generate_resultado_p3()
    generate_hashes()


def _population(cfg: Any, universe: Any, vintage: Any, horizonte: str) -> Any:
    population = build_population(cfg, universe, vintage, horizonte, with_outcomes=False)
    expected = EXPECTED_POPULATION[horizonte]
    if len(population.records) != expected["final"]:
        raise SystemExit(f"{horizonte}: población {len(population.records)} != {expected['final']}")
    if population.population_sha256 != expected["sha256"]:
        raise SystemExit(f"{horizonte}: hash {population.population_sha256} != {expected['sha256']}")
    return population


def _v1_observations(cfg: Any, universe: Any, vintage: Any, horizonte: str) -> dict[Key, Any]:
    with (
        patch.object(event_study, "evaluate_managed_event", _no_outcome),
        patch.object(event_study, "evaluate_potential_event", _no_outcome),
    ):
        result = event_study.run_event_study_on_vintage(
            cfg,
            universe,
            vintage,
            horizonte=horizonte,
            context_mode="point_in_time",
            score_model_version="1.0",
        )
    return {(s.observation.asset, s.observation.signal_idx): s.observation for s in result.signals}


def _score_without(obs: Any, names: Iterable[str]) -> float:
    excluded = set(names)
    points = sum(d.points for d in obs.dimensions if d.available and d.name not in excluded)
    max_points = sum(d.max for d in obs.dimensions if d.available and d.name not in excluded)
    return canonical_score(100.0 * points / max_points)


def _score_maps(population: Any, v1: Mapping[Key, Any]) -> tuple[dict[str, dict[Key, float]], dict[Key, tuple[str, str]]]:
    scores: dict[str, dict[Key, float]] = {name: {} for name, _label in SCALES}
    meta: dict[Key, tuple[str, str]] = {}
    for i, record in enumerate(population.records):
        obs_v2 = population.result.signals[i].observation
        key = (obs_v2.asset, obs_v2.signal_idx)
        if key not in v1:
            raise SystemExit(f"{population.horizonte}: señal sin v1 PIT: {key}")
        obs_v1 = v1[key]
        scores["A"][key] = canonical_score(obs_v1.score_value)
        scores["B"][key] = _score_without(obs_v1, ("beneficio_riesgo",))
        scores["C"][key] = _score_without(obs_v1, ("conviccion",))
        scores["D"][key] = canonical_score(record.score)
        if _score_without(obs_v1, ("beneficio_riesgo", "conviccion")) != scores["D"][key]:
            raise SystemExit(f"{population.horizonte}: v1 sin RR ni convicción != v2 en {key}")
        meta[key] = (record.region, record.asset)
    return scores, meta


def generate_impact(populations: Mapping[str, Any], v1_pit: Mapping[str, Mapping[Key, Any]]) -> None:
    lines = [
        "# Impacto v1 PIT -> v2",
        "",
        f"- {UNIVERSE_LABEL}.",
        "- Todas las escalas usan contexto `point_in_time`; no se usa contexto legacy.",
        "- Desenlaces parcheados a `None`; población con `build_population(..., with_outcomes=False)`.",
        "- Un valor de una escala no equivale a la misma cifra de otra escala.",
        "- Los desplazamientos son del score, no rendimiento; no atribuyen mejora de expectancy a ninguna dimensión.",
        "",
    ]
    for horizonte, population in populations.items():
        scores, meta = _score_maps(population, v1_pit[horizonte])
        title = "swing" if horizonte == "swing" else f"medio: {MEDIO_FORCED_VERDICT}"
        lines += [f"## {title}", "", f"n={len(population.records)}; population_sha256=`{population.population_sha256}`.", ""]
        lines += _impact_distribution(horizonte, scores)
        lines += _impact_shifts(horizonte, scores)
        lines += _impact_quintiles(scores)
        lines += _impact_migration(horizonte, scores)
        lines += _impact_regions_assets(horizonte, scores, meta)
    lines += ["## Clasificación operativa", "", "no aplica: Score v2 no dispone de umbrales calibrados", ""]
    (OUT / "impacto.md").write_text("\n".join(lines), encoding="utf-8")


def _impact_distribution(horizonte: str, scores: Mapping[str, Mapping[Key, float]]) -> list[str]:
    rows = ["escala\t" + "\t".join(f"p{k}" for k in PERCENTILES) + "\tmedia\tdistintos"]
    lines = ["### Distribución", "", "| escala | " + " | ".join(f"p{k}" for k in PERCENTILES) + " | media | distintos |", "|" + "---|" * 12]
    for name, label in SCALES:
        ordered = sorted(scores[name].values())
        vals = [nearest_rank_cut(ordered, k) for k in PERCENTILES]
        rows.append(name + "\t" + "\t".join(f"{v:.1f}" for v in vals) + f"\t{statistics.fmean(ordered):.2f}\t{len(set(ordered))}")
        lines.append(f"| {label} | " + " | ".join(f"{v:.1f}" for v in vals) + f" | {statistics.fmean(ordered):.2f} | {len(set(ordered))} |")
    (TABLES / f"{horizonte}-percentiles.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    hist = ["tramo_5\t" + "\t".join(scores.keys())]
    for low in range(0, 100, 5):
        high = low + 5
        label = f"[{low},{high}{']' if low == 95 else ')'}"
        hist.append(label + "\t" + "\t".join(str(sum(1 for v in scores[s].values() if low <= v < high or (low == 95 and v == 100.0))) for s in scores))
    (TABLES / f"{horizonte}-histograma-5.tsv").write_text("\n".join(hist) + "\n", encoding="utf-8")
    return [*lines, "", f"Histograma en `tablas/{horizonte}-histograma-5.tsv`.", ""]


def _impact_shifts(horizonte: str, scores: Mapping[str, Mapping[Key, float]]) -> list[str]:
    rows = ["comparacion\tmedia\tmediana\tp5\tp25\tp75\tp95\tmin\tmax\tpct_sube\tpct_baja\tpct_igual"]
    lines = ["### Desplazamientos", "", "| comparación | media | mediana | p5 | p25 | p75 | p95 | min | max | % sube | % baja | % igual |", "|" + "---|" * 12]
    for after in ("B", "C", "D"):
        diffs = sorted(scores[after][k] - scores["A"][k] for k in scores["A"])
        n = len(diffs)
        up = sum(d > 0 for d in diffs)
        down = sum(d < 0 for d in diffs)
        same = n - up - down
        vals = [statistics.fmean(diffs), statistics.median(diffs), nearest_rank_cut(diffs, 5), nearest_rank_cut(diffs, 25), nearest_rank_cut(diffs, 75), nearest_rank_cut(diffs, 95), diffs[0], diffs[-1], 100 * up / n, 100 * down / n, 100 * same / n]
        rows.append(f"{after}-A\t" + "\t".join(f"{v:.4f}" for v in vals))
        lines.append(f"| {after} - A | " + " | ".join(f"{v:+.2f}" if i < 8 else f"{v:.2f}" for i, v in enumerate(vals)) + " |")
    (TABLES / f"{horizonte}-desplazamientos.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return [*lines, ""]


def _impact_quintiles(scores: Mapping[str, Mapping[Key, float]]) -> list[str]:
    lines = ["### n por quintil", "", "| escala | cortes p20/p40/p60/p80 | Q1 | Q2 | Q3 | Q4 | Q5 |", "|" + "---|" * 7]
    for name, label in SCALES:
        cuts = quintile_cuts(list(scores[name].values()))
        lines.append(f"| {label} | " + " / ".join(f"{v:.1f}" for v in cuts.values) + " | " + " | ".join(str(cuts.n_by_quintile[q]) for q in QUINTILE_LABELS) + " |")
    return [*lines, ""]


def _tramo10(value: float) -> str:
    low = min(int(value // 10) * 10, 90)
    return f"[{low},{low + 10}{']' if low == 90 else ')'}"


def _impact_migration(horizonte: str, scores: Mapping[str, Mapping[Key, float]]) -> list[str]:
    tramos = [_tramo10(10.0 * i) for i in range(10)]
    counts = Counter((_tramo10(scores["A"][k]), _tramo10(scores["D"][k])) for k in scores["A"])
    rows = ["A_tramo\\D_tramo\t" + "\t".join(tramos)]
    lines = ["### migración entre tramos de escala; no son bandas operativas equivalentes", "", "| A \\ D | " + " | ".join(tramos) + " | total |", "|" + "---|" * 12]
    for row in tramos:
        rows.append(row + "\t" + "\t".join(str(counts[(row, col)]) for col in tramos))
        total = sum(counts[(row, col)] for col in tramos)
        if total:
            lines.append(f"| {row} | " + " | ".join(str(counts[(row, col)]) for col in tramos) + f" | {total} |")
    (TABLES / f"{horizonte}-migracion-tramos-10-A-D.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return [*lines, ""]


def _impact_regions_assets(horizonte: str, scores: Mapping[str, Mapping[Key, float]], meta: Mapping[Key, tuple[str, str]]) -> list[str]:
    by_region: dict[str, list[float]] = defaultdict(list)
    by_asset: dict[str, list[float]] = defaultdict(list)
    asset_region: dict[str, str] = {}
    for key, (region, asset) in meta.items():
        diff = scores["D"][key] - scores["A"][key]
        by_region[region].append(diff)
        by_asset[asset].append(diff)
        asset_region[asset] = region
    lines = ["### Región", "", "| región | n | mediana D-A | p25 | p75 |", "|---|---|---|---|---|"]
    for region in sorted(by_region):
        vals = sorted(by_region[region])
        lines.append(f"| {region} | {len(vals)} | {statistics.median(vals):+.1f} | {nearest_rank_cut(vals, 25):+.1f} | {nearest_rank_cut(vals, 75):+.1f} |")
    asset_rows = ["activo\tregion\tn\tmediana_D_menos_A"]
    medians = []
    for asset in sorted(by_asset):
        med = statistics.median(by_asset[asset])
        medians.append(med)
        asset_rows.append(f"{asset}\t{asset_region[asset]}\t{len(by_asset[asset])}\t{med:.4f}")
    (TABLES / f"{horizonte}-activos-D-menos-A.tsv").write_text("\n".join(asset_rows) + "\n", encoding="utf-8")
    medians = sorted(medians)
    lines += [
        "",
        "### Activo",
        "",
        f"{len(medians)} activos; mediana D-A por activo: mín {medians[0]:+.1f}, p25 {nearest_rank_cut(medians, 25):+.1f}, mediana {statistics.median(medians):+.1f}, p75 {nearest_rank_cut(medians, 75):+.1f}, máx {medians[-1]:+.1f}.",
        f"Tabla completa: `tablas/{horizonte}-activos-D-menos-A.tsv`.",
        "",
    ]
    return lines


def generate_context(cfg: Any, universe: Any, vintage: Any, populations: Mapping[str, Any]) -> None:
    from advisor.analysis.overview import context_assets_of

    asia_symbols = tuple(sorted(asset.primary_symbol for asset in context_assets_of(universe) if asset.region == "ASIA"))
    symbols = (cfg.market_context.vix_symbol, cfg.market_context.trend_symbol, *asia_symbols)
    closes = {symbol: frozen_close(vintage, symbol) for symbol in symbols if frozen_close(vintage, symbol) is not None}
    resolver = PointInTimeContextResolver(
        closes,
        cfg.market_context,
        asia_symbols=asia_symbols,
        settlement_minutes=cfg.data_quality.settlement_minutes,
    )
    lines = ["# Contexto / H-6", "", "No se mezcla exclusión con imputación. El hueco puntual de STOXX se publica aparte.", ""]
    for horizonte, population in populations.items():
        counts = Counter()
        stoxx_age = Counter()
        for signal in population.result.signals:
            obs = signal.observation
            asset = universe.get(obs.asset)
            views = vintage.by_symbol[asset.primary_symbol]
            market = mercado_para_simbolo(asset, asset.primary_symbol)
            session = session_date_of(views.signal_prices.index[obs.signal_idx], market)
            entry = session_date_of(views.signal_prices.index[obs.signal_idx + 1], market)
            analysis_ts = analysis_timestamp_for_signal(market, session, entry, settlement_minutes=cfg.data_quality.settlement_minutes)
            if analysis_ts is None:
                counts["sin_analysis_timestamp"] += 1
                continue
            resolved = resolver.resolve(analysis_ts)
            if "NO_CALCULABLE_CONTEXT_VIX" in resolved.no_calculable_codes:
                counts["vix_no_calculable"] += 1
            if resolved.asia_missing:
                counts["asia_imputada"] += 1
            if resolved.context is None or resolved.context.vix_value is None:
                counts["vix_imputado"] += 1
            if resolved.context is None or resolved.context.trend_sma is None:
                counts["trend_sma_imputada"] += 1
            if resolved.stoxx_age_days:
                stoxx_age[resolved.stoxx_age_days] += 1
        exp = EXPECTED_POPULATION[horizonte]
        lines += [
            f"## {horizonte}",
            "",
            f"- Asia imputada en población final: {counts['asia_imputada']}.",
            f"- VIX imputado en población final: {counts['vix_imputado']}.",
            f"- Tendencia/SMA imputada en población final: {counts['trend_sma_imputada']}.",
            f"- Exclusiones previas: Asia ausente {exp['excluded_asia_missing']}; SMA200 sin historia {exp['excluded_trend_sma_history']}; VIX no calculable {counts['vix_no_calculable']}; crypto {exp['excluded_crypto']}; unión excluida {exp['union']}.",
            f"- STOXX último cierre causal, ni excluido ni imputado: {exp['stoxx_gaps']} señales; edades observadas {dict(sorted(stoxx_age.items()))}.",
            "",
        ]
        if counts["sin_analysis_timestamp"] > 0:
            lines += [f"- sin_analysis_timestamp: {counts['sin_analysis_timestamp']}.", ""]
    lines += [
        "El recuento de imputados se obtiene re-resolviendo el contexto con `PointInTimeContextResolver` sobre cada señal final.",
        "El recuento de VIX no calculable sale de la misma re-resolución; `census_p3_population` falla cerrada ante `NO_CALCULABLE_CONTEXT_VIX`, por eso el censo congelado no publica filas excluidas de VIX.",
        f"Fuente de censo: `{PASO2A.relative_to(ROOT)}/` y constantes reproducidas por `advisor.research.p3.EXPECTED_POPULATION`.",
        "",
    ]
    (OUT / "contexto-h6.md").write_text("\n".join(lines), encoding="utf-8")


def generate_sap(universe: Any, vintage: Any, populations: Mapping[str, Any], v1_pit: Mapping[str, Mapping[Key, Any]]) -> None:
    population = populations["swing"]
    p3 = json.loads((RUN / "p3-resultado.json").read_text(encoding="utf-8"))
    cuts = p3["horizontes"]["swing"]["cuts"]["values"]
    for i, record in enumerate(population.records):
        obs_v2 = population.result.signals[i].observation
        if obs_v2.asset == "SAP.DE":
            obs_v1 = v1_pit["swing"][(obs_v2.asset, obs_v2.signal_idx)]
            dims = {d.name: d for d in obs_v1.dimensions}
            score_v2 = canonical_score(record.score)
            formula_score = canonical_score(
                100.0
                * (dims["catalizador"].points + dims["tecnico"].points + dims["contexto"].points)
                / 50.0
            )
            if formula_score != score_v2:
                raise SystemExit(f"SAP.DE: fórmula v2 {formula_score} != record.score {score_v2}")
            q = quintile_of(score_v2, cuts)
            asset = universe.get(obs_v2.asset)
            if asset is None:
                raise SystemExit("SAP.DE sin activo en universo")
            market = mercado_para_simbolo(asset, asset.primary_symbol)
            views = vintage.by_symbol[asset.primary_symbol]
            signal_session = session_date_of(obs_v2.signal_timestamp, market)
            entry_session = session_date_of(views.signal_prices.index[obs_v2.signal_idx + 1], market)
            if signal_session is None or entry_session is None:
                raise SystemExit("SAP.DE sin sesión de señal o entrada")
            lines = [
                "# Cálculo manual SAP.DE",
                "",
                f"- signal_id: `{obs_v2.signal_id}`",
                f"- signal_timestamp crudo: `{obs_v2.signal_timestamp.isoformat()}`",
                f"- sesión de señal ({market}): `{signal_session.isoformat()}`",
                f"- sesión de entrada ({market}): `{entry_session.isoformat()}`",
                f"- catalizador v1: {dims['catalizador'].points:.9f} / {dims['catalizador'].max:.1f}",
                f"- técnico v1: {dims['tecnico'].points:.9f} / {dims['tecnico'].max:.1f}",
                f"- contexto PIT: {dims['contexto'].points:.9f} / {dims['contexto'].max:.1f}",
                f"- RR v1: {dims['beneficio_riesgo'].points:.9f} / {dims['beneficio_riesgo'].max:.1f}",
                f"- convicción v1: {dims['conviccion'].points:.9f} / {dims['conviccion'].max:.1f}",
                f"- evaluable_max v1: {obs_v1.evaluable_max:.1f}",
                f"- Score v1 PIT: {canonical_score(obs_v1.score_value):.9f}",
                f"- Score v2: {score_v2:.9f}",
                "",
                f"Score v2 = 100 x ({dims['catalizador'].points:.9f} + {dims['tecnico'].points:.9f} + {dims['contexto'].points:.9f}) / 50 = {score_v2:.9f}.",
                f"Comprobación automática: `100·(cat+tec+ctx)/50 == record.score` -> `{formula_score:.9f} == {score_v2:.9f}`.",
                f"Cortes swing congelados: {' / '.join(f'{v:.1f}' for v in cuts)}; quintil: {q}.",
                "",
                "No se consulta `net_R`.",
                "",
            ]
            (OUT / "calculo-manual-sap.md").write_text("\n".join(lines), encoding="utf-8")
            return
    raise SystemExit("SAP.DE no encontrado en swing")


def generate_delta_block() -> None:
    raw_lines = [
        line
        for line in (RUN / "tablas/swing-bloque-x-quintil.tsv").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    rows = list(csv.DictReader(raw_lines, delimiter="\t"))
    first = rows[0]
    keys = list(first)
    q1_key = next(k for k in keys if k == "Q1_mean_net_r")
    q5_key = next(k for k in keys if k == "Q5_mean_net_r")
    block_key = next(k for k in keys if "bloque" in k.lower())
    chosen = next(row for row in rows if row[q1_key] and row[q5_key])
    deltas = []
    weighted_num = 0.0
    weighted_den = 0
    for row in rows:
        if not row[q1_key] or not row[q5_key]:
            continue
        row_delta = float(row[q5_key]) - float(row[q1_key])
        deltas.append((row[block_key], row_delta))
        weight = int(row["Q1_n"]) + int(row["Q5_n"])
        weighted_num += row_delta * weight
        weighted_den += weight
    contrast_rows = _read_tsv(RUN / "tablas/swing-contrastes.tsv")
    published = next(row for row in contrast_rows if row["contraste"] == "Q5−Q1")
    simple_mean = statistics.fmean(delta for _block, delta in deltas)
    weighted_mean = weighted_num / weighted_den
    if len(deltas) != int(published["n_blocks"]):
        raise SystemExit(f"Delta bloque: {len(deltas)} bloques != {published['n_blocks']}")
    if abs(simple_mean - float(published["mean"])) > 1e-6:
        raise SystemExit(f"Delta bloque: media simple {simple_mean} != publicada {published['mean']}")
    q1 = float(chosen[q1_key])
    q5 = float(chosen[q5_key])
    delta = q5 - q1
    lines = [
        "# Cálculo manual de un Delta de bloque",
        "",
        "Fuente única: `evidence/2026-09-30-T-019-paso3-p3/run/tablas/swing-bloque-x-quintil.tsv`.",
        f"Bloque elegido: {chosen[block_key]}.",
        "",
        f"- media Q1: {q1:.6f}",
        f"- media Q5: {q5:.6f}",
        f"- Delta_bloque = media(Q5) - media(Q1) = {q5:.6f} - {q1:.6f} = {delta:.6f}",
        "",
        "`paired_block_contrast` calcula por bloque `media(high) - media(low)` solo donde existen ambas medias; su `mean` es la media simple de esos deltas de bloque. La `n` de la TSV no pondera el contraste, solo acompaña al intervalo por bootstrap de bloques.",
        "",
        f"Comprobación automática: {len(deltas)} bloques calculables; media simple {simple_mean:.12f}; `p3-resultado.json`/`swing-contrastes.tsv` {float(published['mean']):.12f}; diferencia {abs(simple_mean - float(published['mean'])):.12g}.",
        f"Media ponderada por Q1_n+Q5_n (no usada por `paired_block_contrast`): {weighted_mean:.12f}.",
        "",
    ]
    (OUT / "calculo-manual-delta-bloque.md").write_text("\n".join(lines), encoding="utf-8")


def _read_tsv(path: Path) -> list[dict[str, str]]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
    return list(csv.DictReader(lines, delimiter="\t"))


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    number = float(value)
    return f"{number:.{digits}f}"


def _interval_text(item: Mapping[str, Any], digits: int = 4) -> str:
    return f"{_fmt(item['mean'], digits)} [{_fmt(item['lower'], digits)}, {_fmt(item['upper'], digits)}]"


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    return [
        "| " + " | ".join(headers) + " |",
        "|" + "---|" * len(headers),
        *("| " + " | ".join(str(cell) for cell in row) + " |" for row in rows),
        "",
    ]


def _asset_delta_summary(rows: Sequence[Mapping[str, str]]) -> dict[str, int]:
    calculable = [row for row in rows if row["delta_q5_q1"]]
    negative = [row for row in calculable if float(row["delta_q5_q1"]) < 0]
    with_interval = [row for row in calculable if row["delta_ic_lower"] and row["delta_ic_upper"]]
    below = [row for row in with_interval if float(row["delta_ic_upper"]) < 0]
    above = [row for row in with_interval if float(row["delta_ic_lower"]) > 0]
    return {
        "calculable": len(calculable),
        "negative": len(negative),
        "below": len(below),
        "above": len(above),
    }


def _calibration_rows(path: Path) -> list[list[str]]:
    return [
        [
            row["candidato"],
            row["percentiles"],
            row["n_upper"],
            row["capacidad"],
            f"[{_fmt(row['bonf_primario_lower'])}, {_fmt(row['bonf_primario_upper'])}]",
            f"[{_fmt(row['bonf_contraste_lower'])}, {_fmt(row['bonf_contraste_upper'])}]",
            _fmt(row["profit_factor"]),
            ", ".join(name for name in ("c1", "c2", "c3", "c4", "c5") if row[name] == "False"),
            row["cumple_operar"],
        ]
        for row in _read_tsv(path)
    ]


def _verify_frozen_hashes() -> str:
    proc = subprocess.run(
        ["shasum", "-a", "256", "-c", "SHA256SUMS-ejecucion.txt"],
        cwd=P3,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stdout + proc.stderr)
    return proc.stdout


def generate_resultado_p3() -> None:
    verify = _verify_frozen_hashes()
    data = json.loads((RUN / "p3-resultado.json").read_text(encoding="utf-8"))
    swing = data["horizontes"]["swing"]
    medio = data["horizontes"]["medio"]
    cal = swing["calibration"]
    swing_quintiles = _read_tsv(RUN / "tablas/swing-quintiles.tsv")
    swing_contrasts = _read_tsv(RUN / "tablas/swing-contrastes.tsv")
    swing_regions = _read_tsv(RUN / "tablas/swing-regiones.tsv")
    swing_assets = _read_tsv(RUN / "tablas/swing-activos.tsv")
    swing_intra = _read_tsv(RUN / "tablas/swing-intra-activo.tsv")
    swing_intra_excluded = _read_tsv(RUN / "tablas/swing-intra-activo-pares-excluidos.tsv")
    swing_ablations = _read_tsv(RUN / "tablas/swing-ablaciones.tsv")
    swing_family = _read_tsv(RUN / "tablas/swing-familia-bonferroni.tsv")
    medio_quintiles = _read_tsv(RUN / "tablas/medio-quintiles.tsv")
    medio_contrasts = _read_tsv(RUN / "tablas/medio-contrastes.tsv")
    medio_assets = _read_tsv(RUN / "tablas/medio-activos.tsv")
    medio_summary = _asset_delta_summary(medio_assets)
    asset_summary = _asset_delta_summary(swing_assets)
    intra_below = sum(1 for row in swing_intra if row["ic_upper"] and float(row["ic_upper"]) < 0)
    intra_above = sum(1 for row in swing_intra if row["ic_lower"] and float(row["ic_lower"]) > 0)
    evaluated_family = sum(1 for row in swing_family if row["estado"] == "evaluado")
    not_evaluated_family = len(swing_family) - evaluated_family
    if data["contadores"] != data["contadores_preregistro"] or not data["contadores_coinciden"]:
        raise SystemExit("contadores P3 no coinciden con pre-registro")
    lines = [
        "# Resultado P3",
        "",
        f"- P3_EXECUTOR_SHA: `{data['identidad']['executor_sha']}`",
        f"- SHA pre-registro: `{data['identidad']['preregistro_sha']}`",
        f"- data_vintage_id: `{data['identidad']['data_vintage_id']}`",
        f"- universe_vintage_id: `{data['identidad']['universe_vintage_id']}`",
        f"- config_hash: `{data['identidad']['config_hash']}`",
        f"- ejecución única: inicio `{data['inicio_utc']}`, fin `{data['fin_utc']}`, exit code `{(P3 / 'consola/exit_code.txt').read_text().strip()}`, marca `{(RUN / 'EJECUCION_CONFIRMATORIA_INICIADA').name}`",
        f"- etiqueta de universo: {data['label']}",
        f"- contadores: {data['contadores']['comparaciones_swing']}/{data['contadores']['comparaciones_medio_trazabilidad']}/{data['contadores']['comparaciones_totales']}; comprobación contra pre-registro: {data['contadores_coinciden']}",
        "",
        "## Swing",
        "",
        f"Primario global: {_interval_text(swing['global_primary'])}; bloques {swing['global_primary']['n_blocks']}; n {swing['global_primary']['n']}.",
        f"Cortes: {' / '.join(_fmt(v, 1) for v in swing['cuts']['values'])}; bloques ocupados {swing['blocks_occupied']}; n población {swing['n']}.",
        "",
        "### Quintiles",
        "",
    ]
    lines += _table(
        ["quintil", "n con net_R observable", "primario IC95", "capacidad", "experimental_resolution", "expectancy agrupada", "PF"],
        [
            [
                row["quintil"],
                row["n"],
                f"{_fmt(row['primario'])} [{_fmt(row['ic_lower'])}, {_fmt(row['ic_upper'])}]",
                row["capacidad"],
                row["experimental_resolution"],
                _fmt(row["expectancy_agrupada"]),
                _fmt(row["profit_factor"]),
            ]
            for row in swing_quintiles
        ],
    )
    lines += [
        "### Delta Q5-Q1",
        "",
        f"Δ Q5−Q1: {_interval_text(swing['delta_q5_q1'])}; anchura {_fmt(swing['delta_q5_q1']['width'])}; bloques {swing['delta_q5_q1']['n_blocks']}.",
        f"Veredicto: {swing['veredicto_ordenacion']} porque {', '.join(swing['veredicto_ordenacion_motivos'])}; motivo mecánico {_fmt(swing['delta_q5_q1']['width'])} > 0.2000.",
        "",
        "### Contrastes Adyacentes",
        "",
    ]
    lines += _table(
        ["contraste", "media", "IC95", "anchura", "bloques"],
        [[row["contraste"], _fmt(row["mean"]), f"[{_fmt(row['ic_lower'])}, {_fmt(row['ic_upper'])}]", _fmt(row["width"]), row["n_blocks"]] for row in swing_contrasts if row["contraste"] != "Q5−Q1"],
    )
    lines += [
        "## descriptivo, no modifica el veredicto",
        "",
        "### Regiones",
        "",
    ]
    lines += _table(
        ["región", "n", "primario IC95", "Δ Q5-Q1 IC95", "bloques Δ"],
        [[row["grupo"], row["n"], f"{_fmt(row['primario'])} [{_fmt(row['ic_lower'])}, {_fmt(row['ic_upper'])}]", f"{_fmt(row['delta_q5_q1'])} [{_fmt(row['delta_ic_lower'])}, {_fmt(row['delta_ic_upper'])}]", row["delta_n_blocks"]] for row in swing_regions],
    )
    lines += [
        "### Activos",
        "",
        f"Δ calculable en {asset_summary['calculable']} activos; negativos {asset_summary['negative']}; IC entero bajo 0: {asset_summary['below']}; IC entero sobre 0: {asset_summary['above']}.",
        "",
        "### Intra-Activo",
        "",
        f"Estimación global intra-activo: {_fmt(swing['intra_asset']['primary'])} [{_fmt(swing['intra_asset']['lower'])}, {_fmt(swing['intra_asset']['upper'])}]; bloques {swing['intra_asset']['n_blocks']}; pares calculables {swing['intra_asset']['pares_calculables']}; pares excluidos {swing['intra_asset']['pares_excluidos']} (TSV: {len(swing_intra_excluded)}); IC entero bajo 0: {intra_below}; IC entero sobre 0: {intra_above}.",
        "",
        "## Calibración Swing",
        "",
        f"min_score_operar={json.dumps(cal['min_score_operar'])}; min_score_vigilar={json.dumps(cal['min_score_vigilar'])}; calibrated={json.dumps(cal['calibrated'])}.",
        f"Familia Bonferroni: m={cal['bonferroni_m']}; {evaluated_family} evaluados + {not_evaluated_family} VIGILAR no evaluados.",
        "",
    ]
    lines += _table(
        ["candidato", "percentil", "n", "capacidad", "IC primario Bonf.", "IC contraste Bonf.", "PF", "condiciones que fallan", "cumple OPERAR"],
        _calibration_rows(RUN / "tablas/swing-candidatos.tsv"),
    )
    lines += [
        "## Ablaciones Swing",
        "",
    ]
    ablation_rows = []
    for name, ablation in swing["ablations"].items():
        delta = ablation["delta_q5_q1"]
        q_rows = [row for row in swing_ablations if row["dimension"] == name]
        primary = "; ".join(f"{row['quintil']}={_fmt(row['primario'])}" for row in q_rows)
        ablation_rows.append(
            [
                name,
                primary,
                _fmt(delta["mean"]),
                f"[{_fmt(delta['lower'])}, {_fmt(delta['upper'])}]",
                _fmt(delta["width"]),
                ablation["veredicto_ordenacion"],
            ]
        )
    lines += _table(["ablación", "primario por quintil", "Δ", "IC95", "anchura", "veredicto"], ablation_rows)
    lines += [
        "",
        "## Medio",
        "",
        f"Cifras de trazabilidad, no calibración: primario global {_interval_text(medio['global_primary'])}; Δ Q5−Q1 {_interval_text(medio['delta_q5_q1'])}; anchura {_fmt(medio['delta_q5_q1']['width'])}; bloques {medio['delta_q5_q1']['n_blocks']}.",
        f"Veredicto forzado: {medio['veredicto_ordenacion']}; motivo: {', '.join(medio['veredicto_ordenacion_motivos'])}.",
        f"Activos medio con Δ calculable {medio_summary['calculable']}; negativos {medio_summary['negative']}; IC entero bajo 0: {medio_summary['below']}; IC entero sobre 0: {medio_summary['above']}.",
        "",
    ]
    lines += _table(
        ["quintil", "n con net_R observable", "primario IC95", "capacidad", "experimental_resolution", "PF"],
        [[row["quintil"], row["n"], f"{_fmt(row['primario'])} [{_fmt(row['ic_lower'])}, {_fmt(row['ic_upper'])}]", row["capacidad"], row["experimental_resolution"], _fmt(row["profit_factor"])] for row in medio_quintiles],
    )
    lines += _table(
        ["contraste medio", "media", "IC95", "anchura", "bloques"],
        [[row["contraste"], _fmt(row["mean"]), f"[{_fmt(row['ic_lower'])}, {_fmt(row['ic_upper'])}]", _fmt(row["width"]), row["n_blocks"]] for row in medio_contrasts],
    )
    lines += [
        "## Calibración Tres Horizontes",
        "",
        f"- swing: calibrated={json.dumps(cal['calibrated'])}; `min_score_operar`={json.dumps(cal['min_score_operar'])}; `min_score_vigilar`={json.dumps(cal['min_score_vigilar'])}.",
        "- medio: calibrated=false (D-45; trazabilidad inválida por bloque parcial).",
        "- intradía: calibrated=false (sin laboratorio y sin umbrales, D-45).",
        "",
        "## Identidad Y Hashes",
        "",
        f"Score model version: `{data['identidad']['score_model_version']}`; coste: {data['identidad']['cost_pct']}; seed: {data['identidad']['seed']}.",
        "Hashes de artefactos originales verificados contra `SHA256SUMS-ejecucion.txt`:",
        "",
        "```text",
        verify.strip(),
        "```",
        "",
    ]
    (OUT / "resultado-p3.md").write_text("\n".join(lines), encoding="utf-8")


def generate_hashes() -> None:
    frozen = _verify_frozen_hashes()
    produced = []
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path.name != "hashes-de-tablas.txt" and "__pycache__" not in path.parts:
            produced.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(OUT)}")
    lines = ["# Verificación congelada #33", "", frozen.strip(), "", "# SHA256 salidas paso 4", "", *produced, ""]
    (OUT / "hashes-de-tablas.txt").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
