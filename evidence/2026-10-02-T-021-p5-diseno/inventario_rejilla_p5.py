"""Inventario estructural de la rejilla de P5 (T-021), SIN DESENLACES.

Enumera la población de P4 por la misma ruta que su preflight (`p4.build_population`) y,
para cada punto de la rejilla, recalcula solo los niveles desde las primitivas en t. Los
evaluadores de desenlace se sustituyen antes de importar nada más por funciones que lanzan
un error: si algo intentara leer una trayectoria futura, el script se cae.

Uso, desde la raíz del repositorio:
    PYTHONPATH=. .venv/bin/python evidence/2026-10-02-T-021-p5-diseno/inventario_rejilla_p5.py \
        > evidence/2026-10-02-T-021-p5-diseno/inventario-estructural.json
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any, Dict, Optional

from advisor.research import event_study

OUTCOME_EVALUATORS = ("evaluate_managed_event", "evaluate_potential_event", "classify_target_stop_bar")


def _forbidden(*_args: Any, **_kwargs: Any) -> None:
    raise RuntimeError("DESENLACE PROHIBIDO en el inventario de P5")


for _name in OUTCOME_EVALUATORS:
    setattr(event_study, _name, _forbidden)

from advisor.config import load_config  # noqa: E402
from advisor.research import p4  # noqa: E402
from advisor.research.vintage import load_vintage  # noqa: E402
from advisor.universe.loader import load_universe  # noqa: E402

for _name in OUTCOME_EVALUATORS:
    if hasattr(p4, _name):
        setattr(p4, _name, _forbidden)

# (s, m2, m3, centro de referencia). m3 = 5.625 solo en la fila m2 = 5.25 de B2 (opción C
# de OD-P5-3); las tres celdas con RR en P < 1,5 de la superficie de S2 se incluyen para
# documentar que violan la condición 6. C0 se incluye como referencia.
GRID = (
    (2.0, 4.875, 5.0, "B2"),
    (1.75, 4.5, 5.0, "B2"),
    (1.75, 4.875, 5.0, "B2"),
    (1.75, 5.25, 5.625, "B2"),
    (2.0, 4.5, 5.0, "B2"),
    (2.0, 5.25, 5.625, "B2"),
    (2.25, 4.5, 5.0, "B2"),
    (2.25, 4.875, 5.0, "B2"),
    (2.25, 5.25, 5.625, "B2"),
    (2.5, 3.75, 5.0, "S2"),
    (2.25, 3.375, 5.0, "S2"),
    (2.25, 3.75, 5.0, "S2"),
    (2.25, 4.125, 5.0, "S2"),
    (2.5, 3.375, 5.0, "S2"),
    (2.5, 4.125, 5.0, "S2"),
    (2.75, 3.375, 5.0, "S2"),
    (2.75, 3.75, 5.0, "S2"),
    (2.75, 4.125, 5.0, "S2"),
    (2.0, 3.0, 5.0, "S2"),
)


def geometry(s: float, m2: float, m3: float) -> p4.Geometry:
    return p4.Geometry(
        f"s{s}_m{m2}_m3{m3}",
        s,
        (1.5, m2, m3),
        p4.ROLE_DESCRIPTIVE,
        confirmatory=False,
        eligible_for_p5=False,
        bonferroni=False,
    )


def main() -> None:
    config = load_config("config.yaml")
    universe = load_universe(config.universe_path)
    vintage = load_vintage(p4.DATA_VINTAGE_ID)
    population = p4.build_population(config, universe, vintage)
    if not population.ok:
        raise SystemExit(f"la población no reproduce el censo de P4: {[c for c in population.checks if not c[-1]]}")
    if len(population.signals) != 101_251 or not population.population_sha256.startswith("78024050"):
        raise SystemExit(f"población inesperada: {len(population.signals)} {population.population_sha256}")

    base = config.levels
    signals = population.signals
    c0_levels = {sig.signal_id: p4.geometry_levels(sig.observation, p4.C0, base) for sig in signals}
    center_levels = {
        gid: {sig.signal_id: p4.geometry_levels(sig.observation, geo, base) for sig in signals}
        for gid, geo in (("B2", p4.B2), ("S2", p4.S2))
    }

    cells: Dict[str, Any] = {}
    for s, m2, m3, center in GRID:
        geo = geometry(s, m2, m3)
        none: Counter[str] = Counter()
        basis: Counter[str] = Counter()
        pairs: Counter[str] = Counter()
        incoherent: Counter[str] = Counter()
        binding: Counter[str] = Counter()
        valid = 0
        same_stop_c0 = 0
        same_stop_center = 0
        same_stop_target_center = 0
        rr_min: Optional[float] = None
        for sig in signals:
            levels = p4.geometry_levels(sig.observation, geo, base)
            if levels is None:
                none[p4.levels_none_reason(sig.observation, geo)] += 1
                continue
            valid += 1
            control = c0_levels[sig.signal_id]
            reference = center_levels[center][sig.signal_id]
            assert control is not None and reference is not None
            basis[p4.stop_basis_of(levels)] += 1
            pairs[p4.stop_basis_pair(control, levels)] += 1
            same_stop_c0 += levels.stop == control.stop
            same_stop_center += levels.stop == reference.stop
            same_stop_target_center += levels.stop == reference.stop and levels.target2 == reference.target2
            for violation in p4.coherence_violations(levels, 1.5):
                incoherent[violation] += 1
            binding[p4.binding_limit(levels)] += 1
            rr_min = levels.rr_ratio if rr_min is None else min(rr_min, levels.rr_ratio)
        cells[f"{s}|{m2}|{m3}"] = {
            "centro": center,
            "validos": valid,
            "none": dict(none),
            "stop_basis": dict(basis),
            "pares_stop_basis_vs_c0": dict(pairs),
            "stop_igual_c0": same_stop_c0,
            "stop_igual_centro": same_stop_center,
            "stop_y_target2_iguales_centro": same_stop_target_center,
            "incoherencias": dict(incoherent),
            "manda": dict(binding),
            "rr_efectivo_min": rr_min,
        }

    report = {
        "outcomes_read": False,
        "poblacion": len(signals),
        "population_sha256": population.population_sha256,
        "atr_sobre_precio_max": max(sig.atr_ratio for sig in signals),
        "celdas": cells,
    }
    print(json.dumps(report, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
