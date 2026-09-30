"""Mide el cambio de etiqueta de confianza de D-46 sin leer desenlaces."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import advisor.research.event_study as event_study  # noqa: E402
from advisor.config import load_config  # noqa: E402
from advisor.research.vintage import load_vintage  # noqa: E402
from advisor.universe.loader import load_universe  # noqa: E402

VID = "071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841"
OUT = Path(__file__).resolve().parent
ORDER = {"Baja": 0, "Media": 1, "Alta": 2}


def main() -> None:
    cfg = load_config("config.yaml")
    universe = load_universe(cfg.universe_path)
    vintage = load_vintage(VID)
    lines: list[str] = [
        "# Impacto D-46 en Opportunity.confianza",
        "",
        f"cosecha={VID}",
        "desenlaces=parcheados_a_None",
        "",
    ]
    for horizonte in ("swing", "medio"):
        with (
            patch.object(event_study, "evaluate_managed_event", _no_outcome),
            patch.object(event_study, "evaluate_potential_event", _no_outcome),
        ):
            result = event_study.run_event_study_on_vintage(
                cfg,
                universe,
                vintage,
                horizonte=horizonte,
                context_mode="legacy_v1",
            )
        counts: Counter[tuple[str, str, str]] = Counter()
        matrix: Counter[tuple[str, str]] = Counter()
        window = cfg.horizonte(horizonte)
        for signal in result.signals:
            old = _old_confidence(signal.observation)
            new = _new_confidence(signal.observation, min_bars=window.min_bars)
            matrix[(old, new)] += 1
            counts[(old, new, _reason(old, new))] += 1
        lines.extend(_format_horizon(horizonte, len(result.signals), matrix, counts))
    output = "\n".join(lines) + "\n"
    (OUT / "confidence_impact.txt").write_text(output, encoding="utf-8")
    print(output, end="")


def _old_confidence(observation) -> str:
    missing = sum(1 for dimension in observation.dimensions if not dimension.available)
    conviccion = next((dimension for dimension in observation.dimensions if dimension.name == "conviccion"), None)
    ratio = conviccion.points / conviccion.max if conviccion is not None and conviccion.max else 0.0
    return _confidence_label(ratio, missing)


def _new_confidence(observation, *, min_bars: int) -> str:
    missing = sum(1 for dimension in observation.dimensions if not dimension.available)
    coverage_points = 4.0 * min(1.0, observation.bars / min_bars) if min_bars > 0 else 4.0
    indicator_points = 4.0 * observation.confidence_indicators_present / 6.0
    return _confidence_label((coverage_points + indicator_points) / 8.0, missing)


def _confidence_label(ratio: float, missing: int) -> str:
    if missing == 0 and ratio >= 0.8:
        return "Alta"
    if missing <= 1 and ratio >= 0.6:
        return "Media"
    return "Baja"


def _reason(old: str, new: str) -> str:
    if old == new:
        return "sin_cambio"
    if ORDER[new] < ORDER[old]:
        return "baja_al_retirar_atr_de_confianza"
    return "sube_al_retirar_penalizacion_atr_de_confianza"


def _format_horizon(
    horizonte: str,
    total: int,
    matrix: Counter[tuple[str, str]],
    counts: Counter[tuple[str, str, str]],
) -> list[str]:
    labels = ("Alta", "Media", "Baja")
    lines = [f"=== {horizonte} ===", f"senales_A02_v1={total}", "matriz antigua -> nueva:"]
    for old in labels:
        row = " ".join(f"{new}={matrix[(old, new)]}" for new in labels)
        lines.append(f"  {old}: {row}")
    lines.append("motivos:")
    for (old, new, reason), n in sorted(counts.items()):
        lines.append(f"  {old}->{new} {reason}: {n}")
    lines.append("")
    return lines


def _no_outcome(*args: object, **kwargs: object) -> None:
    return None


if __name__ == "__main__":
    main()
