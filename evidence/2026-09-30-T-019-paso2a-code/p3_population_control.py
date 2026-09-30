"""Control de población P3 para T-019 paso 2a-code."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import advisor.research.event_study as event_study  # noqa: E402
from advisor.config import load_config  # noqa: E402
from advisor.context.point_in_time import (  # noqa: E402
    EXCLUDED_ASIA_MISSING,
    EXCLUDED_CRYPTO,
    EXCLUDED_TREND_SMA_HISTORY,
)
from advisor.data.freshness import mercado_para_simbolo  # noqa: E402
from advisor.data.sessions import session_date_of  # noqa: E402
from advisor.research.p3_population import P3PopulationControl, census_p3_population  # noqa: E402
from advisor.research.vintage import load_vintage  # noqa: E402
from advisor.universe.loader import load_universe  # noqa: E402

VID = "071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841"
OUT = Path(__file__).resolve().parent
REF = Path("evidence/2026-09-29-T-019-paso2a-doc-inspeccion")


def main() -> None:
    cfg = load_config("config.yaml")
    universe = load_universe(cfg.universe_path)
    vintage = load_vintage(VID)
    lines: list[str] = []
    for horizonte in ("swing", "medio"):
        result = census_p3_population(cfg, universe, vintage, horizonte=horizonte)
        _write_outputs(result)
        lines.extend(_summary(result))
        lines.extend(_cross_check_event_study(cfg, universe, vintage, result))
        lines.extend(_compare_reference(horizonte))
    output = "\n".join(lines) + "\n"
    (OUT / "p3_population_control.txt").write_text(output, encoding="utf-8")
    print(output, end="")


def _summary(result: P3PopulationControl) -> list[str]:
    rows = result.rows_by_reason
    return [
        f"=== {result.horizonte} ===",
        f"A-02 población: {result.a02_population} | saltados: {len(result.skipped)}",
        f"{EXCLUDED_CRYPTO}: {len(rows[EXCLUDED_CRYPTO])}",
        f"{EXCLUDED_ASIA_MISSING}: {len(rows[EXCLUDED_ASIA_MISSING])}",
        f"{EXCLUDED_TREND_SMA_HISTORY}: {len(rows[EXCLUDED_TREND_SMA_HISTORY])}",
        f"excluidas unión deduplicada: {result.union_excluded}",
        (
            f"POBLACION FINAL: {len(result.final_population)} señales | "
            f"{len({asset for asset, _ in result.final_population})} activos"
        ),
        f"bloques con señales: {result.blocks_with_signals}",
        f"sha256 población final: {result.final_sha256}",
        (
            "hueco intermedio de ^STOXX50E: "
            f"{len(result.stoxx_gap_rows)} | antigüedad: {dict(result.stoxx_gap_ages)}"
        ),
    ]


def _write_outputs(result: P3PopulationControl) -> None:
    reason_headers = {
        EXCLUDED_CRYPTO: ("activo", "sesion_senal"),
        EXCLUDED_ASIA_MISSING: ("activo", "sesion_senal", "analysis_timestamp_utc", "faltas"),
        EXCLUDED_TREND_SMA_HISTORY: (
            "activo",
            "sesion_senal",
            "analysis_timestamp_utc",
            "cierres_disponibles",
        ),
    }
    for reason, header in reason_headers.items():
        _write_tsv(OUT / f"06-{reason}-{result.horizonte}.tsv", header, result.rows_by_reason[reason])
    _write_tsv(
        OUT / f"06-stoxx_hueco_intermedio-{result.horizonte}.tsv",
        ("activo", "sesion_senal", "analysis_timestamp_utc", "sesion_exigible", "sesion_usada", "dias"),
        result.stoxx_gap_rows,
    )


def _write_tsv(path: Path, header: tuple[str, ...], rows: tuple[tuple[object, ...], ...]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write("\t".join(header) + "\n")
        for row in rows:
            handle.write("\t".join(str(value) for value in row) + "\n")


def _cross_check_event_study(cfg, universe, vintage, control: P3PopulationControl) -> list[str]:
    with (
        patch.object(event_study, "evaluate_managed_event", _no_outcome),
        patch.object(event_study, "evaluate_potential_event", _no_outcome),
    ):
        result = event_study.run_event_study_on_vintage(
            cfg,
            universe,
            vintage,
            horizonte=control.horizonte,
            context_mode="point_in_time",
        )
    final = []
    for signal in result.signals:
        asset = universe.get(signal.observation.asset)
        if asset is None:
            continue
        views = vintage.by_symbol[asset.primary_symbol]
        market = mercado_para_simbolo(asset, asset.primary_symbol)
        session = session_date_of(views.signal_prices.index[signal.observation.signal_idx], market)
        if session is not None:
            final.append((asset.symbol, session))
    cross = P3PopulationControl(
        horizonte=control.horizonte,
        a02_population=control.a02_population,
        rows_by_reason=control.rows_by_reason,
        final_population=tuple(final),
        stoxx_gap_rows=(),
        blocks_with_signals=0,
    )
    return [
        f"control cruzado event_study PIT {control.horizonte}:",
        f"  señales: {len(cross.final_population)} ({'OK' if len(cross.final_population) == len(control.final_population) else 'DIFIERE'})",
        f"  sha256: {cross.final_sha256} ({'OK' if cross.final_sha256 == control.final_sha256 else 'DIFIERE'})",
    ]


def _compare_reference(horizonte: str) -> list[str]:
    names = (
        f"06-{EXCLUDED_CRYPTO}-{horizonte}.tsv",
        f"06-{EXCLUDED_ASIA_MISSING}-{horizonte}.tsv",
        f"06-{EXCLUDED_TREND_SMA_HISTORY}-{horizonte}.tsv",
        f"06-stoxx_hueco_intermedio-{horizonte}.tsv",
    )
    lines = [f"comparación TSV {horizonte}:"]
    for name in names:
        current = (OUT / name).read_text(encoding="utf-8")
        reference = (REF / name).read_text(encoding="utf-8")
        lines.append(f"  {name}: {'OK' if current == reference else 'DIFIERE'}")
    return lines


def _no_outcome(*args: object, **kwargs: object) -> None:
    return None


if __name__ == "__main__":
    main()
