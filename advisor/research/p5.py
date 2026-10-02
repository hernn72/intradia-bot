"""Ejecutor único de P5 (T-021 / A-05): regiones robustas de B2 y S2.

P5 es un filtro de robustez posterior a P4: solo puede descartar B2 y S2, nunca
promover vecinos. El preflight calcula estructura y reproduce agregados ya
publicados de P4; las estimaciones nuevas de vecinos y LOCRO exigen una marca
confirmatoria escrita y un token que solo nace después de esa marca.

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y
selección no corregido)._
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, cast

from advisor.analysis.levels import _SUPPORT_BUFFER_ATR, Levels, rr_at_least
from advisor.config import AdvisorConfig, LevelsConfig
from advisor.research.bootstrap import BlockBootstrapResult, PairedDelta
from advisor.research.capacity import DEFAULT_THRESHOLDS
from advisor.research.event_study import (
    AMBIGUOUS,
    FINAL_EXIT,
    STOP_FIRST,
    TARGET_FIRST,
    TIME_EXIT,
    ManagedEvent,
    PotentialEvent,
)
from advisor.research.p3 import _finite, _json_default, utc_now, write_json
from advisor.research.p4 import (
    C0,
    NO_CALCULABLE_CONTEXT,
    Geometry,
    P4Population,
    P4Signal,
    _blocks_without_pairs,
    _cell,
    _delta,
    _exit_final_rate,
    _levels_with,
    _primary_estimates,
    ambiguity_bound_deltas,
    binding_limit,
    block_estimate,
    build_population,
    capacity_check,
    coherence_violations,
    executor_unchanged_since,
    levels_none_reason,
    levels_sha256,
    profit_factor,
    run_git,
    stop_basis_of,
    stop_basis_pair,
    tree_dirty,
)
from advisor.research.p4 import evaluate_frozen as p4_evaluate_frozen
from advisor.research.p4 import geometry_levels as geometry_levels
from advisor.research.uncertainty import pair_populations
from advisor.research.vintage import VintageLoad
from advisor.run.git import git_sha
from advisor.run.manifest import config_hash
from advisor.universe.models import Universe

P5_PREREG_SHA = "a7c3d238d651b4ea8f48834848c03c0a5a462dfa"
DATA_VINTAGE_ID = "071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841"
UNIVERSE_VINTAGE_ID = "237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19"
P5_POPULATION_SHA256 = "78024050f7081ad4e1dd5cefaefbfa1a1668ff5b1a2ced8c34e62b6501873141"
P5_SIGNAL_IDS_SHA256 = "9faa4a45beaba3eb8dafabf7990906cd8c89e8e06ae2f25edec7839cd48e629f"
EXPECTED_CONFIG_HASH = "89406d28c7b4b6e6c4f032cd63b6868c927af3e926dfb52d430dfa6654d06387"
COST_PCT = 0.2
SEED = 20260830
RESAMPLES = 2000
CONFIDENCE = 0.95
EXPECTED_P5_COMPARISONS = 71
EXPECTED_NEW_CONFIRMATORY = 0
NEW_CONFIRMATORY: Tuple[str, ...] = ()
P4_ACCUMULATED = 447
UNIVERSE_LABEL = "condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)"
PREFLIGHT_DIR = Path("evidence/2026-10-02-T-021-p5/preflight")
CONFIRMATORY_OUTPUT_DIR = Path("evidence/2026-10-02-T-021-p5/run")
RUN_MARKER = "EJECUCION_CONFIRMATORIA_P5_INICIADA"
DEVELOPMENT_ENV = "INTRADIA_P5_PREFLIGHT_DESARROLLO"
P4_RUN_TABLES = Path("evidence/2026-10-01-T-020-p4/run/tablas")
P4_PREFLIGHT_JSON = Path("evidence/2026-10-01-T-020-p4/preflight/p4-preflight.json")
P5_STRUCTURAL_INVENTORY = Path("evidence/2026-10-02-T-021-p5-diseno/inventario-estructural.json")

PRIMARY_BLOCK_LENGTH = 60
SENSITIVITY_BLOCK_LENGTH = 120
FIRST_HALF_BLOCKS = tuple(range(2, 12))
SECOND_HALF_BLOCKS = tuple(range(12, 22))
CORE_REGIONS = ("USA", "EUROPA", "ASIA")
LOCRO_DENOMINATORS = {"USA": 56_353, "EUROPA": 66_629, "ASIA": 83_298}
LOCRO_MIN_PAIRS = {"USA": 50_718, "EUROPA": 59_967, "ASIA": 74_969}
CELL_MIN_PAIRS = 91_126

ROLE_CONTROL = "CONTROL"
ROLE_CENTER = "CENTER_CANDIDATE"
ROLE_NEIGHBOR = "DIAGNOSTIC_NEIGHBOR"
ROLE_ABSENCE = "STRUCTURAL_ABSENCE"

AUSENCIA_ESTRUCTURAL = "AUSENCIA_ESTRUCTURAL"
NO_ESTIMABLE = "NO_ESTIMABLE"
ACEPTABLE = "ACEPTABLE"
DÉBIL = "DÉBIL"
CONTRARIA = "CONTRARIA"
FRÁGIL = "FRÁGIL"
DEPENDIENTE_DE_MERCADO = "DEPENDIENTE_DE_MERCADO"
NO_CONCLUYENTE = "NO_CONCLUYENTE"
ROBUSTA = "ROBUSTA"


class P5PreflightError(RuntimeError):
    """Una identidad del pre-registro no se reproduce: P5 no se ejecuta."""


class P5AlreadyExecutedError(RuntimeError):
    """La ejecución confirmatoria ya se inició una vez: no se repite."""


class P5OutcomeGateError(RuntimeError):
    """Un cálculo intentó abrir desenlaces fuera de la guarda de P5."""


@dataclass(frozen=True)
class P5Identity:
    executor_sha: str
    git_dirty: Optional[bool]
    prereg_in_history: Optional[bool]
    config_hash: str
    score_model_version: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "p5_prereg_sha": P5_PREREG_SHA,
            "p5_executor_sha": self.executor_sha,
            "git_dirty": self.git_dirty,
            "prereg_en_historia": self.prereg_in_history,
            "data_vintage_id": DATA_VINTAGE_ID,
            "universe_vintage_id": UNIVERSE_VINTAGE_ID,
            "config_hash": self.config_hash,
            "config_score_model_version": self.score_model_version,
            "cost_pct": COST_PCT,
            "seed": SEED,
            "standard": {"confidence": CONFIDENCE, "resamples": RESAMPLES},
            "new_confirmatory": list(NEW_CONFIRMATORY),
            "label": UNIVERSE_LABEL,
        }


def prereg_in_history(repo: str | Path = ".") -> Optional[bool]:
    if run_git(["merge-base", "--is-ancestor", P5_PREREG_SHA, "HEAD"], repo).ok:
        return True
    kind = run_git(["cat-file", "-t", P5_PREREG_SHA], repo)
    if kind.ok and kind.output == "commit":
        return False
    return None


def current_identity(config: AdvisorConfig, repo: str | Path = ".") -> P5Identity:
    return P5Identity(
        executor_sha=git_sha(repo),
        git_dirty=tree_dirty(repo),
        prereg_in_history=prereg_in_history(repo),
        config_hash=config_hash(config),
        score_model_version=config.scoring.score_model_version,
    )


def development_mode() -> bool:
    return os.getenv(DEVELOPMENT_ENV) == "1"


@dataclass(frozen=True)
class P5Cell:
    gid: str
    center_id: str
    atr_stop_multiple: float
    target_atr_multiples: Tuple[float, float, float]
    role: str
    m3_auxiliar: bool = False
    absence_reason: Optional[str] = None
    target2_structural: bool = False
    entry_max_atr: float = 0.75
    min_rr: float = 1.5

    @property
    def key(self) -> Tuple[float, float, float]:
        return (self.atr_stop_multiple, self.target_atr_multiples[1], self.target_atr_multiples[2])

    def as_geometry(self) -> Geometry:
        return Geometry(
            self.gid,
            self.atr_stop_multiple,
            self.target_atr_multiples,
            self.role,
            confirmatory=False,
            eligible_for_p5=self.role == ROLE_CENTER,
            bonferroni=False,
            target2_structural=self.target2_structural,
            entry_max_atr=self.entry_max_atr,
            min_rr=self.min_rr,
        )

    def levels_config(self, base: LevelsConfig) -> LevelsConfig:
        return self.as_geometry().levels_config(base)

    def as_dict(self) -> Dict[str, Any]:
        data = {
            "id": self.gid,
            "centro": self.center_id,
            "atr_stop_multiple": self.atr_stop_multiple,
            "target_atr_multiples": list(self.target_atr_multiples),
            "target2_structural": self.target2_structural,
            "entry_max_atr": self.entry_max_atr,
            "min_rr": self.min_rr,
            "rol": self.role,
            "m3_auxiliar": self.m3_auxiliar,
        }
        if self.absence_reason is not None:
            data["motivo"] = self.absence_reason
        return data


def _rr_valid(s: float, m2: float) -> bool:
    return rr_at_least(m2 / s, 1.5) or math.isclose(m2, 1.5 * s, rel_tol=1e-12, abs_tol=1e-12)


def _cell_id(center: str, s: float, m2: float) -> str:
    if center == "B2" and math.isclose(s, 2.0) and math.isclose(m2, 4.875):
        return "B2"
    if center == "S2" and math.isclose(s, 2.5) and math.isclose(m2, 3.75):
        return "S2"
    return f"{center}_s{s:.2f}_m2{m2:.3f}".replace(".", "p")


def build_grid() -> Tuple[P5Cell, ...]:
    cells: List[P5Cell] = [
        P5Cell("C0", "C0", C0.atr_stop_multiple, C0.target_atr_multiples, ROLE_CONTROL),
    ]
    specs = (("B2", 2.0, 4.875), ("S2", 2.5, 3.75))
    for center, s0, m20 in specs:
        for s in (s0 - 0.25, s0, s0 + 0.25):
            for m2 in (m20 - 0.375, m20, m20 + 0.375):
                m3 = 5.625 if m2 >= 5.0 else 5.0
                role = ROLE_CENTER if math.isclose(s, s0) and math.isclose(m2, m20) else ROLE_NEIGHBOR
                reason = None
                if not _rr_valid(s, m2):
                    role = ROLE_ABSENCE
                    reason = "RR < 1.5"
                cells.append(
                    P5Cell(
                        _cell_id(center, s, m2),
                        center,
                        s,
                        (1.5, m2, m3),
                        role,
                        m3_auxiliar=m3 > 5.0,
                        absence_reason=reason,
                    )
                )
    _assert_grid_contract(tuple(cells))
    return tuple(cells)


def _triples(cells: Iterable[P5Cell]) -> Tuple[Tuple[float, float, float, bool], ...]:
    return tuple((c.atr_stop_multiple, c.target_atr_multiples[1], c.target_atr_multiples[2], c.m3_auxiliar) for c in cells)


def _assert_grid_contract(cells: Tuple[P5Cell, ...]) -> None:
    b2_neighbors = tuple(c for c in cells if c.center_id == "B2" and c.role == ROLE_NEIGHBOR)
    s2_neighbors = tuple(c for c in cells if c.center_id == "S2" and c.role == ROLE_NEIGHBOR)
    absences = tuple(c for c in cells if c.role == ROLE_ABSENCE)
    expected_b2 = (
        (1.75, 4.5, 5.0, False), (1.75, 4.875, 5.0, False), (1.75, 5.25, 5.625, True),
        (2.0, 4.5, 5.0, False), (2.0, 5.25, 5.625, True),
        (2.25, 4.5, 5.0, False), (2.25, 4.875, 5.0, False), (2.25, 5.25, 5.625, True),
    )
    expected_s2 = (
        (2.25, 3.375, 5.0, False), (2.25, 3.75, 5.0, False), (2.25, 4.125, 5.0, False),
        (2.5, 4.125, 5.0, False), (2.75, 4.125, 5.0, False),
    )
    expected_absences = (
        (2.5, 3.375, 5.0, False), (2.75, 3.375, 5.0, False), (2.75, 3.75, 5.0, False),
    )
    if _triples(b2_neighbors) != expected_b2 or _triples(s2_neighbors) != expected_s2 or _triples(absences) != expected_absences:
        raise P5PreflightError("la rejilla P5 no coincide con D-66")


GRID = build_grid()
CELLS_BY_ID = {cell.gid: cell for cell in GRID}
C0_CELL = CELLS_BY_ID["C0"]
B2_CELL = CELLS_BY_ID["B2"]
S2_CELL = CELLS_BY_ID["S2"]


def neighbors(center_id: str) -> Tuple[P5Cell, ...]:
    return tuple(c for c in GRID if c.center_id == center_id and c.role == ROLE_NEIGHBOR)


def absences(center_id: Optional[str] = None) -> Tuple[P5Cell, ...]:
    return tuple(c for c in GRID if c.role == ROLE_ABSENCE and (center_id is None or c.center_id == center_id))


def semiplanes(center_id: str) -> Dict[str, Tuple[str, ...]]:
    center = CELLS_BY_ID[center_id]
    valid = neighbors(center_id)
    planes = {
        "s_minus": tuple(c.gid for c in valid if c.atr_stop_multiple < center.atr_stop_multiple),
        "s_plus": tuple(c.gid for c in valid if c.atr_stop_multiple > center.atr_stop_multiple),
        "m2_minus": tuple(c.gid for c in valid if c.target_atr_multiples[1] < center.target_atr_multiples[1]),
        "m2_plus": tuple(c.gid for c in valid if c.target_atr_multiples[1] > center.target_atr_multiples[1]),
    }
    expected = {
        "B2": {
            "s_minus": (1.75, None), "s_plus": (2.25, None),
            "m2_minus": (None, 4.5), "m2_plus": (None, 5.25),
        },
        "S2": {
            "s_minus": (2.25, None), "s_plus": (2.75, None),
            "m2_minus": (None, 3.375), "m2_plus": (None, 4.125),
        },
    }
    for name, (s, m2) in expected[center_id].items():
        wanted = tuple(
            c.gid for c in valid
            if (s is None or math.isclose(c.atr_stop_multiple, s)) and (m2 is None or math.isclose(c.target_atr_multiples[1], m2))
        )
        if planes[name] != wanted:
            raise P5PreflightError(f"semiplano {center_id}/{name} no coincide con los vecinos válidos")
    return planes


SEMIPLANES = {"B2": semiplanes("B2"), "S2": semiplanes("S2")}


def planned_comparisons() -> Dict[str, Any]:
    subtotals = {center: 5 * len(neighbors(center)) + 3 for center in ("B2", "S2")}
    total = sum(subtotals.values())
    return {
        "formula": "Σ_{B2,S2}(5·|vecinos válidos|+3)",
        "subtotales": subtotals,
        "total": total,
        "confirmatorias_nuevas": len(NEW_CONFIRMATORY),
        "acumulado_con_p4": P4_ACCUMULATED + total,
        "ok": total == EXPECTED_P5_COMPARISONS and len(NEW_CONFIRMATORY) == EXPECTED_NEW_CONFIRMATORY,
    }


def structural_region_census(population: P4Population) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for region in CORE_REGIONS:
        counts[f"sin_{region}"] = sum(1 for signal in population.signals if signal.region != region)
    return counts


def locro_denominators(population: Optional[P4Population] = None) -> Dict[str, Dict[str, int]]:
    observed = structural_region_census(population) if population is not None else {f"sin_{k}": v for k, v in LOCRO_DENOMINATORS.items()}
    return {
        region: {
            "poblacion": observed[f"sin_{region}"],
            "pares_minimos": LOCRO_MIN_PAIRS[region],
        }
        for region in CORE_REGIONS
    }


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def advisor_config_hash(config: AdvisorConfig, cell: P5Cell) -> str:
    levels = config.levels.model_copy(
        update={
            "atr_stop_multiple": cell.atr_stop_multiple,
            "target_atr_multiples": list(cell.target_atr_multiples),
        }
    )
    return config_hash(config.model_copy(update={"levels": levels}))


def policy_payload(config: AdvisorConfig, cell: P5Cell) -> Dict[str, Any]:
    return {
        "esquema": "intradia.p5.politica.v1",
        "advisor_config_hash": advisor_config_hash(config, cell),
        "geometria": {
            "atr_stop_multiple": cell.atr_stop_multiple,
            "target_atr_multiples": list(cell.target_atr_multiples),
            "target2_structural": cell.target2_structural,
            "entry_max_atr": cell.entry_max_atr,
            "min_rr": cell.min_rr,
            "regla_soporte": "E",
            "support_buffer_atr": _SUPPORT_BUFFER_ATR,
            "m3_auxiliar": cell.m3_auxiliar,
        },
        "laboratorio": {
            "horizonte": "swing",
            "max_hold_bars": 40,
            "coste_pct_ida_vuelta": COST_PCT,
            "entrada": "cierre_de_la_senal",
            "salidas": [STOP_FIRST, TARGET_FIRST, TIME_EXIT, FINAL_EXIT],
            "ambiguous": "no_resuelto",
        },
    }


def policy_sha256(config: AdvisorConfig, cell: P5Cell) -> str:
    return hashlib.sha256(canonical_json(policy_payload(config, cell)).encode("utf-8")).hexdigest()


def published_cell_hash(config: AdvisorConfig, cell: P5Cell) -> Dict[str, Any]:
    data = {"procedencia": {"rol": cell.role}, "advisor_config_hash": advisor_config_hash(config, cell)}
    if cell.role in (ROLE_CONTROL, ROLE_CENTER):
        data["policy_sha256"] = policy_sha256(config, cell)
    elif cell.role == ROLE_NEIGHBOR:
        data["diagnostico_sha256"] = policy_sha256(config, cell)
    return data


def grid_sha256() -> str:
    payload = [cell.as_dict() for cell in GRID]
    return hashlib.sha256(canonical_json({"celdas": payload}).encode("utf-8")).hexdigest()


def _geometry_key(cell: P5Cell | Geometry) -> Tuple[float, Tuple[float, float, float]]:
    targets = tuple(cell.target_atr_multiples)
    if len(targets) != 3:
        raise ValueError("la geometría P5 debe tener tres objetivos")
    return (cell.atr_stop_multiple, targets)


class OutcomeGate:
    """Autoriza todos los desenlaces de P5 y bloquea vecinos antes de la marca."""

    def __init__(self, *, marker_exists: bool = False, phase: str = "preflight") -> None:
        self.marker_exists = marker_exists
        self.phase = phase
        self._allowed_pre_marker = {_geometry_key(C0_CELL), _geometry_key(B2_CELL), _geometry_key(S2_CELL)}

    def require_pre_marker_allowed(self, cell: P5Cell, *, token: Optional[ConfirmatoryToken] = None) -> None:
        if _geometry_key(cell) not in self._allowed_pre_marker:
            if self.phase == "confirmatoria" and self.marker_exists:
                _require_token(token)
                return
            raise P5OutcomeGateError(f"{cell.gid}: P5 no puede leer desenlaces de esta geometría antes de la marca")

    def evaluate_frozen(
        self,
        population: P4Population,
        vintage: VintageLoad,
        cell: P5Cell,
        levels: Mapping[str, Optional[Levels]],
        *,
        token: Optional[ConfirmatoryToken] = None,
    ) -> Tuple[Dict[str, ManagedEvent], Dict[str, PotentialEvent], Tuple[str, ...]]:
        self.require_pre_marker_allowed(cell, token=token)
        return p4_evaluate_frozen(population, vintage, levels)


@dataclass(frozen=True)
class ConfirmatoryToken:
    marker_path: Path
    marker_payload_sha256: str


@dataclass(frozen=True)
class P5FrozenPreflight:
    population: P4Population
    levels: Dict[str, Dict[str, Optional[Levels]]]
    report: Dict[str, Any]


def build_confirmatory_token(marker_path: Path, payload: Mapping[str, Any]) -> ConfirmatoryToken:
    if not marker_path.is_file():
        raise P5OutcomeGateError("la marca confirmatoria no existe")
    observed = marker_path.read_text(encoding="utf-8")
    expected = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if observed != expected:
        raise P5OutcomeGateError("la marca confirmatoria no coincide con el payload recién escrito")
    return ConfirmatoryToken(marker_path=marker_path, marker_payload_sha256=hashlib.sha256(observed.encode()).hexdigest())


def _require_token(token: Optional[ConfirmatoryToken]) -> ConfirmatoryToken:
    if token is None:
        raise P5OutcomeGateError("esta estimación P5 exige ConfirmatoryToken")
    expected_path = (CONFIRMATORY_OUTPUT_DIR / RUN_MARKER).resolve()
    if token.marker_path.resolve() != expected_path:
        raise P5OutcomeGateError("ConfirmatoryToken apunta a una marca que no pertenece a P5")
    if not token.marker_path.is_file():
        raise P5OutcomeGateError("ConfirmatoryToken no tiene marca existente")
    observed = token.marker_path.read_bytes()
    observed_sha = hashlib.sha256(observed).hexdigest()
    if observed_sha != token.marker_payload_sha256:
        raise P5OutcomeGateError("ConfirmatoryToken no coincide con la marca en disco")
    return token


def _levels_by_cell(population: P4Population, base: LevelsConfig) -> Dict[str, Dict[str, Optional[Levels]]]:
    return {cell.gid: _levels_for_cell(population, base, cell) for cell in GRID if cell.role != ROLE_ABSENCE}


def _structural_cell_key(cell: P5Cell) -> str:
    return f"{cell.atr_stop_multiple}|{cell.target_atr_multiples[1]}|{cell.target_atr_multiples[2]}"


def _count_values(values: Iterable[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def structural_levels_report(
    population: P4Population,
    base: LevelsConfig,
    cell_levels: Optional[Mapping[str, Mapping[str, Optional[Levels]]]] = None,
) -> Dict[str, Any]:
    report: Dict[str, Any] = {}
    levels_by_gid = cell_levels if cell_levels is not None else _levels_by_cell(population, base)
    center_levels = {"C0": levels_by_gid["C0"], "B2": levels_by_gid["B2"], "S2": levels_by_gid["S2"]}
    observations = {signal.signal_id: signal.observation for signal in population.signals}
    for cell in GRID:
        # Las ausencias estructurales no se congelan ni se evalúan nunca; sus niveles se
        # calculan aquí solo para publicar, sin desenlaces, que violan la condición 6 (RR < 1,5).
        levels = levels_by_gid[cell.gid] if cell.role != ROLE_ABSENCE else _levels_for_cell(population, base, cell)
        none = {sid: levels_none_reason(observations[sid], cell.as_geometry()) for sid, val in levels.items() if val is None}
        incoherence_types = [
            violation
            for level in levels.values()
            if level is not None
            for violation in coherence_violations(level, cell.min_rr)
        ]
        bindings: Dict[str, int] = {}
        stop_basis_counts: Dict[str, int] = {}
        stop_basis_vs_c0: Dict[str, int] = {}
        min_rr_values: List[float] = []
        stop_equal_center = 0
        stop_equal_c0 = 0
        stop_t2_equal_center = 0
        reference = center_levels.get(cell.center_id)
        for sid, level in levels.items():
            if level is None:
                continue
            bindings[binding_limit(level)] = bindings.get(binding_limit(level), 0) + 1
            stop_basis_counts[stop_basis_of(level)] = stop_basis_counts.get(stop_basis_of(level), 0) + 1
            c0_level = center_levels["C0"].get(sid)
            if c0_level is not None:
                pair = stop_basis_pair(c0_level, level)
                stop_basis_vs_c0[pair] = stop_basis_vs_c0.get(pair, 0) + 1
            min_rr_values.append(level.rr_ratio)
            reference_level = reference.get(sid) if reference is not None else None
            if reference_level is not None and level.stop == reference_level.stop:
                stop_equal_center += 1
            if c0_level is not None and level.stop == c0_level.stop:
                stop_equal_c0 += 1
            if reference_level is not None and level.stop == reference_level.stop and level.target2 == reference_level.target2:
                stop_t2_equal_center += 1
        report[cell.gid] = {
            **cell.as_dict(),
            "none": len(none),
            "none_por_motivo": _count_values(none.values()),
            "incoherencias": _count_values(incoherence_types),
            "validos": sum(1 for value in levels.values() if value is not None),
            "levels_sha256": None if cell.role == ROLE_ABSENCE else levels_sha256(levels),
            "denominador": cell.role != ROLE_ABSENCE,
            "stop_basis": dict(sorted(stop_basis_counts.items())),
            "pares_stop_basis_vs_c0": dict(sorted(stop_basis_vs_c0.items())),
            "stop_igual_centro": stop_equal_center,
            "stop_igual_c0": stop_equal_c0,
            "stop_y_target2_iguales_centro": stop_t2_equal_center,
            "manda": dict(sorted(bindings.items())),
            "rr_efectivo_min": min(min_rr_values) if min_rr_values else None,
            "inventario_clave": _structural_cell_key(cell),
        }
    return report


def _levels_for_cell(population: P4Population, base: LevelsConfig, cell: P5Cell) -> Dict[str, Optional[Levels]]:
    geometry = cell.as_geometry()
    levels_config = geometry.levels_config(base)
    return {signal.signal_id: _levels_with(signal.observation, levels_config, geometry.min_rr) for signal in population.signals}


def _estimate_from_events(
    cell: P5Cell,
    population: P4Population,
    control: Mapping[str, ManagedEvent],
    variant_events: Mapping[str, ManagedEvent],
    without_levels: Sequence[str],
    potentials: Mapping[str, PotentialEvent],
    control_potentials: Mapping[str, PotentialEvent],
    control_levels: Optional[Mapping[str, Optional[Levels]]] = None,
    variant_levels: Optional[Mapping[str, Optional[Levels]]] = None,
    *,
    confirmatory_primary: bool = False,
) -> Dict[str, Any]:
    signal_by_id = {s.signal_id: s for s in population.signals}
    subset_control = {signal_id: control[signal_id] for signal_id in variant_events}
    paired = pair_populations(subset_control, variant_events)
    deltas = [_delta(signal_by_id[d.signal_id], d.net_r_a, d.net_r_b) for d in paired.deltas]
    deltas.sort(key=lambda item: (item.session, item.asset, item.signal_id))
    primary, width95, _standard = _primary_estimates(deltas, population.spine, confirmatory=confirmatory_primary)
    estimates: Dict[str, Any] = {}
    if primary is not None:
        estimates["primaria_60"] = p4_estimate_dict(primary, "primaria P5 de vecino (IC95)")
    sens = block_estimate(deltas, population.spine, block_length=SENSITIVITY_BLOCK_LENGTH, confidence=CONFIDENCE, n_resamples=RESAMPLES)
    if sens is not None:
        estimates["bloque_120"] = p4_estimate_dict(sens, "sensibilidad 120 descriptiva")
    for bound in ("conservadora", "favorable"):
        result = block_estimate(
            ambiguity_bound_deltas(control, variant_events, signal_by_id, bound),
            population.spine,
            block_length=PRIMARY_BLOCK_LENGTH,
            confidence=CONFIDENCE,
            n_resamples=RESAMPLES,
        )
        if result is not None:
            estimates[f"cota_{bound}"] = p4_estimate_dict(result, f"envolvente {bound} de ambigüedad")
    estimates["mitades"] = {}
    for name, blocks in (("bloques_2_11", FIRST_HALF_BLOCKS), ("bloques_12_21", SECOND_HALF_BLOCKS)):
        items = [d for d in deltas if signal_by_id[d.signal_id].blocks[PRIMARY_BLOCK_LENGTH] in blocks]
        if items:
            value = block_estimate(items, population.spine, block_length=PRIMARY_BLOCK_LENGTH, confidence=CONFIDENCE, n_resamples=RESAMPLES)
            if value is not None:
                estimates["mitades"][name] = p4_estimate_dict(value, "mitades P5" if not confirmatory_primary else "mitades P4 reproducidas")
    level = p4_level_estimate(variant_events.values(), signal_by_id)
    estimates["nivel"] = level
    primary_capacity = capacity_check(
        primary,
        None if width95 is None else width95,
        dropped_rate=paired.dropped_rate,
        exit_final_control=_exit_final_rate(control.values()),
        exit_final_variant=_exit_final_rate(variant_events.values()),
    )
    no_calc_pairs = 0
    shared_candle = 0
    both_ambiguous = 0
    for delta in deltas:
        signal = signal_by_id[delta.signal_id]
        if signal.regime == NO_CALCULABLE_CONTEXT:
            no_calc_pairs += 1
    for signal_id, event in variant_events.items():
        control_event = control[signal_id]
        if event.exit_status == AMBIGUOUS and control_event.exit_status == AMBIGUOUS:
            both_ambiguous += 1
            if control_event.exit_idx == event.exit_idx:
                shared_candle += 1
    return {
        "celda": cell.as_dict(),
        "comparacion": f"{cell.gid}_vs_C0",
        "emparejamiento": {
            "senales_poblacion": len(signal_by_id),
            "sin_niveles": len(without_levels),
            "con_niveles": len(variant_events),
            "dropped_only_c0": paired.dropped_only_a,
            "dropped_only_variant": paired.dropped_only_b,
            "dropped_both": paired.dropped_both,
            "pares_finales": len(deltas),
            "bloques_60_sin_pares": _blocks_without_pairs(population, primary),
            "fraccion_pares": len(deltas) / len(signal_by_id) if signal_by_id else 0.0,
            "tasa_descarte_ambiguedad": paired.dropped_rate,
            "pares_no_calculable_context": no_calc_pairs,
            "ambiguas_en_los_dos_brazos": both_ambiguous,
            "vela_ambigua_compartida": shared_candle,
        },
        "estimaciones": estimates,
        "capacidad": primary_capacity,
        "profit_factor": profit_factor(event.net_r_multiple for event in variant_events.values() if event.net_r_multiple is not None),
        "potenciales": len(potentials),
        "control_potenciales": len(control_potentials),
        "deltas": deltas,
    }


def p4_estimate_dict(result: BlockBootstrapResult, role: str) -> Dict[str, Any]:
    return {
        "papel": role,
        "n_pares": result.n_pairs,
        "n_bloques": result.n_blocks,
        "min_pares_bloque": min((block.n for block in result.blocks), default=0),
        "media_delta_r": result.mean_delta_r,
        "media_agrupada_delta_r": result.pooled_mean_delta_r,
        "ic_inferior": result.ci_lower,
        "ic_superior": result.ci_upper,
        "ic_nivel": result.ci_level,
        "remuestreos": result.n_resamples,
        "heterogeneidad": result.heterogeneity,
        "tau": result.tau_excess_dispersion,
        "exceedance": result.exceedance_fraction,
    }


def p4_level_estimate(events: Iterable[ManagedEvent], signal_by_id: Mapping[str, P4Signal]) -> Dict[str, Any]:
    from advisor.research.p4 import level_estimate

    return level_estimate(events, signal_by_id)


def _capacity_with_min_pairs(capacity: Dict[str, Any], pairs: int, minimum: int, label: str) -> Dict[str, Any]:
    out = dict(capacity)
    motivos = list(out.get("motivos", []))
    pairs_ok = pairs >= minimum
    if not pairs_ok:
        motivos.append(f"pares {label} {pairs} < {minimum}")
    out["ok"] = bool(out.get("ok", False)) and pairs_ok
    out["motivos"] = motivos
    out[f"pares_minimos_{label}"] = minimum
    out[f"pares_minimos_{label}_ok"] = pairs_ok
    return out


def estimate_neighbor(
    token: Optional[ConfirmatoryToken],
    cell: P5Cell,
    population: P4Population,
    vintage: VintageLoad,
    control: Mapping[str, ManagedEvent],
    control_potentials: Mapping[str, PotentialEvent],
    base: LevelsConfig,
    gate: Optional[OutcomeGate] = None,
    levels: Optional[Mapping[str, Optional[Levels]]] = None,
) -> Dict[str, Any]:
    token = _require_token(token)
    if cell.role != ROLE_NEIGHBOR:
        raise ValueError(f"{cell.gid} no es vecino válido")
    cell_levels = levels if levels is not None else _levels_for_cell(population, base, cell)
    outcome_gate = gate or OutcomeGate(marker_exists=True, phase="confirmatoria")
    events, potentials, without_levels = outcome_gate.evaluate_frozen(population, vintage, cell, cell_levels, token=token)
    observed = _estimate_from_events(cell, population, control, events, without_levels, potentials, control_potentials)
    pairs = observed["emparejamiento"]["pares_finales"]
    observed["capacidad"] = _capacity_with_min_pairs(observed["capacidad"], pairs, CELL_MIN_PAIRS, "celda")
    return observed


def estimate_locro(
    token: Optional[ConfirmatoryToken],
    center: P5Cell,
    region: str,
    population: P4Population,
    control: Mapping[str, ManagedEvent],
    variant_events: Mapping[str, ManagedEvent],
) -> Dict[str, Any]:
    _require_token(token)
    if center.gid not in ("B2", "S2") or region not in CORE_REGIONS:
        raise ValueError("LOCRO solo se define para B2/S2 y regiones núcleo")
    signal_by_id = {s.signal_id: s for s in population.signals if s.region != region}
    subset_control = {sid: control[sid] for sid in signal_by_id if sid in control and sid in variant_events}
    subset_variant = {sid: variant_events[sid] for sid in subset_control}
    paired = pair_populations(subset_control, subset_variant)
    deltas = [_delta(signal_by_id[d.signal_id], d.net_r_a, d.net_r_b) for d in paired.deltas]
    deltas.sort(key=lambda item: (item.session, item.asset, item.signal_id))
    primary = block_estimate(deltas, population.spine, block_length=PRIMARY_BLOCK_LENGTH, confidence=CONFIDENCE, n_resamples=RESAMPLES)
    capacity = capacity_check(
        primary,
        None if primary is None else primary.ci_upper - primary.ci_lower,
        dropped_rate=paired.dropped_rate,
        exit_final_control=_exit_final_rate(subset_control.values()),
        exit_final_variant=_exit_final_rate(subset_variant.values()),
        thresholds=DEFAULT_THRESHOLDS,
    )
    pairs_ok = len(deltas) >= LOCRO_MIN_PAIRS[region]
    if not pairs_ok:
        capacity["ok"] = False
        capacity["motivos"] = [*capacity["motivos"], f"pares LOCRO {len(deltas)} < {LOCRO_MIN_PAIRS[region]}"]
    capacity["pares_minimos_locro"] = LOCRO_MIN_PAIRS[region]
    capacity["pares_minimos_locro_ok"] = pairs_ok
    return {
        "centro": center.gid,
        "sin_region": region,
        "denominador": LOCRO_DENOMINATORS[region],
        "pares_minimos": LOCRO_MIN_PAIRS[region],
        "estimacion": None if primary is None else p4_estimate_dict(primary, "LOCRO decisorio IC95"),
        "capacidad": capacity,
        "bloques_60_sin_pares": _blocks_without_pairs(population, primary),
    }


def estimate_region(*args: Any, token: Optional[ConfirmatoryToken] = None, **kwargs: Any) -> Dict[str, Any]:
    _require_token(token)
    raise NotImplementedError("P5 no define estimación regional nueva fuera de LOCRO")


def estimate_asset_concentration(
    token: Optional[ConfirmatoryToken],
    deltas: Sequence[PairedDelta],
) -> Dict[str, Any]:
    _require_token(token)
    by_asset: Dict[str, List[float]] = {}
    for delta in deltas:
        by_asset.setdefault(delta.asset, []).append(delta.delta_r)
    means = [sum(values) / len(values) for values in by_asset.values() if values]
    means_sorted = sorted(means)
    total = sum(delta.delta_r for delta in deltas)
    contributions = sorted((sum(values), asset) for asset, values in by_asset.items())
    positive = sum(1 for value in means if value > 0)
    negative = sum(1 for value in means if value < 0)

    def percentile(p: int) -> Optional[float]:
        if not means_sorted:
            return None
        index = max(0, min(len(means_sorted) - 1, math.ceil(p / 100 * len(means_sorted)) - 1))
        return means_sorted[index]

    shares: Dict[str, Optional[float]] = {"mayor": None, "top5": None, "top10": None}
    if total > 0:
        ordered = sorted((value for value, _ in contributions), reverse=True)
        shares = {
            "mayor": ordered[0] / total if ordered else None,
            "top5": sum(ordered[:5]) / total,
            "top10": sum(ordered[:10]) / total,
        }
    return {
        "activos_positivos": positive,
        "activos_negativos": negative,
        "percentiles_media_agrupada": {f"p{p}": percentile(p) for p in (10, 25, 50, 75, 90)},
        "participacion": shares,
    }


def classify_cell(primary: Mapping[str, Any], conservative: Mapping[str, Any], level: Mapping[str, Any], capacity: Mapping[str, Any], pf: Optional[float]) -> str:
    if not capacity.get("ok", False):
        return NO_ESTIMABLE
    mean = primary.get("media_delta_r")
    if mean is None or mean <= 0:
        return CONTRARIA
    acceptable = (
        primary.get("ic_inferior") is not None
        and primary["ic_inferior"] > 0
        and conservative.get("media_delta_r") is not None
        and conservative["media_delta_r"] > 0
        and level.get("media_net_r") is not None
        and level["media_net_r"] > 0
        and pf is not None
        and pf > 1
    )
    return ACEPTABLE if acceptable else DÉBIL


@dataclass(frozen=True)
class CenterEvidence:
    center_id: str
    p4_reproducido: bool
    p4_conditions: Mapping[str, bool]
    first_half_mean: Optional[float]
    second_half_mean: Optional[float]
    sensitivity_120_mean: Optional[float]
    sensitivity_120_lower: Optional[float]
    conservative_bound_mean: Optional[float]
    level_mean: Optional[float]
    profit_factor: Optional[float]


@dataclass(frozen=True)
class LocroRow:
    estimable: bool
    ic_inferior: Optional[float]


def locro_row(row: Mapping[str, Any]) -> LocroRow:
    estimation = row.get("estimacion")
    capacity = row.get("capacidad")
    if "estimable" in row or "ic_inferior" in row:
        return LocroRow(bool(row.get("estimable", False)), cast(Optional[float], row.get("ic_inferior")))
    estimable = bool(capacity.get("ok", False)) if isinstance(capacity, Mapping) else False
    lower = estimation.get("ic_inferior") if isinstance(estimation, Mapping) else None
    return LocroRow(estimable, cast(Optional[float], lower))


def evaluate_candidate(
    center_evidence: CenterEvidence,
    neighbor_classes: Mapping[str, str],
    locro: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    if center_evidence.center_id not in ("B2", "S2"):
        raise ValueError("P5 solo evalúa B2 y S2")
    planes = SEMIPLANES[center_evidence.center_id]
    valid_neighbor_ids = {cell.gid for cell in neighbors(center_evidence.center_id)}
    unexpected = set(neighbor_classes) - valid_neighbor_ids
    if unexpected:
        raise ValueError(f"{center_evidence.center_id}: clases de vecinos no esperadas: {sorted(unexpected)}")
    estimable = {gid for gid, klass in neighbor_classes.items() if gid in valid_neighbor_ids and klass in (ACEPTABLE, DÉBIL, CONTRARIA)}
    acceptable = {gid for gid, klass in neighbor_classes.items() if gid in valid_neighbor_ids and klass == ACEPTABLE}
    non_estimable = {gid for gid, klass in neighbor_classes.items() if gid in valid_neighbor_ids and klass == NO_ESTIMABLE}
    conditions: Dict[str, Any] = {}
    conditions["centro_p4"] = center_evidence.p4_reproducido and all(center_evidence.p4_conditions.values())
    conditions["F1"] = any(klass == CONTRARIA for klass in neighbor_classes.values())
    conditions["F2"] = any(any(g in estimable for g in planes[name]) and not any(g in acceptable for g in planes[name]) for name in ("s_minus", "s_plus"))
    conditions["F3"] = any(any(g in estimable for g in planes[name]) and not any(g in acceptable for g in planes[name]) for name in ("m2_minus", "m2_plus"))
    conditions["F4"] = False if not estimable else (len(acceptable) / len(estimable)) < 0.75
    conditions["F5"] = not (
        (center_evidence.first_half_mean or 0) > 0
        and (center_evidence.second_half_mean or 0) > 0
        and (center_evidence.sensitivity_120_mean or 0) > 0
        and (center_evidence.sensitivity_120_lower or 0) > 0
    )
    conditions["F6"] = not (
        (center_evidence.conservative_bound_mean or 0) > 0
        and (center_evidence.level_mean or 0) > 0
        and center_evidence.profit_factor is not None
        and center_evidence.profit_factor > 1
    )
    capacity_unknown = len(non_estimable) >= 2 or not estimable
    for name, gids in planes.items():
        if gids and all(neighbor_classes.get(gid) == NO_ESTIMABLE for gid in gids):
            capacity_unknown = True
            conditions[f"{name}_todo_no_estimable"] = True
    locro_rows = [locro_row(row) for row in locro.values()]
    locro_not_estimable = any(not row.estimable for row in locro_rows)
    market_dependent = any(row.estimable and row.ic_inferior is not None and row.ic_inferior <= 0 for row in locro_rows)
    fragile = (not conditions["centro_p4"]) or any(bool(conditions[f"F{i}"]) for i in range(1, 7))
    if fragile:
        label = FRÁGIL
    elif market_dependent:
        label = DEPENDIENTE_DE_MERCADO
    elif capacity_unknown or locro_not_estimable:
        label = NO_CONCLUYENTE
    else:
        label = ROBUSTA
    return {
        "centro": center_evidence.center_id,
        "etiqueta": label,
        "sobrevive": label == ROBUSTA and conditions["centro_p4"],
        "condiciones": conditions,
        "vecinos": {"estimables": len(estimable), "aceptables": len(acceptable), "no_estimables": len(non_estimable)},
        "locro_dependiente": market_dependent,
        "locro_no_concluyente": locro_not_estimable,
    }


def survivors(verdicts: Mapping[str, Mapping[str, Any]]) -> Tuple[str, ...]:
    allowed = ("B2", "S2")
    out: List[str] = []
    for gid, verdict in verdicts.items():
        if gid not in allowed:
            raise ValueError(f"{gid} no puede sobrevivir en P5")
        if CELLS_BY_ID[gid].role != ROLE_CENTER:
            raise ValueError(f"{gid} no es CENTER_CANDIDATE")
        if verdict.get("sobrevive") is True:
            out.append(gid)
    return tuple(gid for gid in allowed if gid in out)


def _read_tsv(path: Path) -> List[Dict[str, str]]:
    rows = []
    header: Optional[List[str]] = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if header is None:
            header = parts
            continue
        rows.append(dict(zip(header, parts)))
    return rows


def _failed_p4_check(gid: str, table: str, column: str, reason: str) -> Dict[str, Any]:
    return {"clave": [gid, table], "columna": column, "esperado": reason, "observado": "N/D", "ok": False}


P4_CAPACITY_COLUMNS = (
    "ok", "motivos", "bloques_con_pares", "min_pares_bloque", "tasa_descarte", "exit_final_c", "exit_final_v", "anchura_ic95",
)


def _p4_capacity_value(capacity: Mapping[str, Any], column: str) -> Any:
    mapping = {
        "ok": "ok",
        "motivos": "motivos",
        "bloques_con_pares": "bloques_con_pares",
        "min_pares_bloque": "min_pares_bloque",
        "tasa_descarte": "tasa_descarte_ambiguedad",
        "exit_final_c": "exit_final_control",
        "exit_final_v": "exit_final_variante",
        "anchura_ic95": "anchura_ic95",
    }
    key = mapping[column]
    value = capacity.get(key)
    if column == "motivos":
        return "; ".join(str(item) for item in value) if isinstance(value, list) else value
    return value


def compare_p4_rows(gid: str, observed: Mapping[str, Any], tables_dir: Path = P4_RUN_TABLES) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    estimate_rows = {
        (row["comparacion"], row["estimacion"], row["estrato"]): row
        for row in _read_tsv(tables_dir / "estimaciones.tsv")
        if row.get("comparacion") == gid
    }
    targets = [
        ("primaria_60", ""),
        ("bloque_120", ""),
        ("cota_conservadora", ""),
        ("cota_favorable", ""),
        ("mitades", "bloques_2_11"),
        ("mitades", "bloques_12_21"),
    ]
    for estimation, stratum in targets:
        got = observed["estimaciones"].get(estimation) if not stratum else observed["estimaciones"].get(estimation, {}).get(stratum)
        expected = estimate_rows.get((gid, estimation, stratum))
        if expected is None or not isinstance(got, Mapping):
            checks.append(_failed_p4_check(gid, "estimaciones.tsv", estimation, "fila P4 u observación P5 ausente"))
            continue
        for column in P4_ESTIMATE_WHITELIST_COLUMNS:
            if column not in expected:
                checks.append(_failed_p4_check(gid, "estimaciones.tsv", column, "columna P4 ausente"))
                continue
            observed_cell = _cell(got.get(column))
            checks.append({"clave": [gid, estimation, stratum], "columna": column, "esperado": expected[column], "observado": observed_cell, "ok": expected[column] == observed_cell})
    table_specs = (
        ("nivel.tsv", "geometria", "nivel", observed.get("estimaciones", {}).get("nivel")),
        ("capacidad.tsv", "comparacion", "capacidad", observed.get("capacidad")),
    )
    for table_name, row_key, observed_key, got in table_specs:
        row = next((row for row in _read_tsv(tables_dir / table_name) if row.get(row_key) == gid), None)
        if row is None or not isinstance(got, Mapping):
            checks.append(_failed_p4_check(gid, table_name, observed_key, f"fila {row_key}={gid} u observación ausente"))
            continue
        for column, expected_value in row.items():
            if column == row_key:
                continue
            observed_value = _p4_capacity_value(got, column) if table_name == "capacidad.tsv" else got.get(column)
            observed_cell = _cell(observed_value)
            checks.append({"clave": [gid, table_name], "columna": column, "esperado": expected_value, "observado": observed_cell, "ok": expected_value == observed_cell})
    for row in (r for r in _read_tsv(tables_dir / "emparejamiento.tsv") if r.get("comparacion") == gid):
        key = row["clave"]
        observed_cell = _cell(observed["emparejamiento"].get(key))
        checks.append({"clave": [gid, "emparejamiento", key], "columna": "valor", "esperado": row["valor"], "observado": observed_cell, "ok": row["valor"] == observed_cell})
    if not any(row.get("comparacion") == gid for row in _read_tsv(tables_dir / "emparejamiento.tsv")):
        checks.append(_failed_p4_check(gid, "emparejamiento.tsv", "comparacion", f"fila comparacion={gid} ausente"))
    return checks


def reproduce_p4_whitelist(
    gate: OutcomeGate,
    population: P4Population,
    vintage: VintageLoad,
    config: AdvisorConfig,
    base: LevelsConfig,
    precomputed_levels: Optional[Mapping[str, Mapping[str, Optional[Levels]]]] = None,
) -> Dict[str, Any]:
    levels = precomputed_levels if precomputed_levels is not None else _levels_by_cell(population, base)
    control, control_potentials, c0_missing = gate.evaluate_frozen(population, vintage, C0_CELL, levels["C0"])
    c0_mismatches = sum(1 for sid, level in levels["C0"].items() if level != population.enumerated_levels.get(sid))
    result: Dict[str, Any] = {
        "C0": {
            "advisor_config_hash_ok": advisor_config_hash(config, C0_CELL) == EXPECTED_CONFIG_HASH,
            "niveles_event_study_diferencias": c0_mismatches,
            "sin_niveles": len(c0_missing),
        },
        "checks": [],
    }
    for cell in (B2_CELL, S2_CELL):
        events, potentials, without_levels = gate.evaluate_frozen(population, vintage, cell, levels[cell.gid])
        observed = _estimate_from_events(
            cell,
            population,
            control,
            events,
            without_levels,
            potentials,
            control_potentials,
            levels["C0"],
            levels[cell.gid],
            confirmatory_primary=True,
        )
        checks = compare_p4_rows(cell.gid, observed)
        result[cell.gid] = {"agregados": _p4_whitelist_view(observed), "checks": checks}
        result["checks"].extend(checks)
    result["p4_published_results_reproduced"] = all(check["ok"] for check in result["checks"])
    return result


P4_ESTIMATE_WHITELIST_COLUMNS = (
    "n_pares", "n_bloques", "min_pares_bloque", "media_delta_r", "media_agrupada_delta_r",
    "ic_inferior", "ic_superior", "ic_nivel", "remuestreos",
)


def _p4_whitelist_view(observed: Mapping[str, Any]) -> Dict[str, Any]:
    """Solo las filas y columnas de la lista blanca de OD-P5-16, ya publicadas por P4.

    La heterogeneidad no está en la lista blanca: en la primaria del centro, además, saldría
    del bootstrap de 20.000 y no del de 2.000 que publicó P4, así que no se publica.
    """

    estimates = cast(Mapping[str, Any], observed.get("estimaciones", {}))

    def trim(row: Mapping[str, Any]) -> Dict[str, Any]:
        return {column: row.get(column) for column in P4_ESTIMATE_WHITELIST_COLUMNS}

    view: Dict[str, Any] = {}
    for key in ("primaria_60", "bloque_120", "cota_conservadora", "cota_favorable"):
        if isinstance(estimates.get(key), Mapping):
            view[key] = trim(cast(Mapping[str, Any], estimates[key]))
    halves = estimates.get("mitades")
    if isinstance(halves, Mapping):
        view["mitades"] = {name: trim(cast(Mapping[str, Any], row)) for name, row in halves.items() if isinstance(row, Mapping)}
    if isinstance(estimates.get("nivel"), Mapping):
        level = cast(Mapping[str, Any], estimates["nivel"])
        view["nivel"] = {column: level.get(column) for column in ("n", "n_bloques", "media_net_r", "ic_inferior", "ic_superior", "profit_factor_agrupado")}
    capacity = cast(Mapping[str, Any], observed.get("capacidad", {}))
    return {
        "comparacion": observed.get("comparacion"),
        "emparejamiento": dict(cast(Mapping[str, Any], observed.get("emparejamiento", {}))),
        "estimaciones": view,
        "capacidad": {column: _p4_capacity_value(capacity, column) for column in P4_CAPACITY_COLUMNS},
    }


def _checks_dicts(checks: Iterable[Tuple[str, Any, Any, bool]]) -> List[Dict[str, Any]]:
    return [{"control": name, "observado": observed, "esperado": expected, "ok": ok} for name, observed, expected, ok in checks]


def _load_json_if_present(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    return cast(Dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _inventory_view(row: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "validos": row.get("validos"),
        "none": row.get("none_por_motivo"),
        "stop_basis": row.get("stop_basis"),
        "pares_stop_basis_vs_c0": row.get("pares_stop_basis_vs_c0"),
        "stop_igual_c0": row.get("stop_igual_c0"),
        "stop_igual_centro": row.get("stop_igual_centro"),
        "stop_y_target2_iguales_centro": row.get("stop_y_target2_iguales_centro"),
        "incoherencias": row.get("incoherencias"),
        "manda": row.get("manda"),
        "rr_efectivo_min": row.get("rr_efectivo_min"),
    }


def _append_structural_inventory_checks(checks: List[Tuple[str, Any, Any, bool]], niveles: Mapping[str, Mapping[str, Any]]) -> None:
    inventory = _load_json_if_present(P5_STRUCTURAL_INVENTORY)
    if inventory is None:
        checks.append(("inventario estructural presente", False, True, False))
        return
    expected_cells = cast(Mapping[str, Any], inventory.get("celdas", {}))
    for cell in GRID:
        key = _structural_cell_key(cell)
        observed = _inventory_view(niveles[cell.gid])
        expected_row = expected_cells.get(key)
        expected = None if expected_row is None else {k: v for k, v in expected_row.items() if k in observed}
        if cell.gid == C0_CELL.gid and expected is not None:
            # El inventario de diseño midió C0 «contra el centro» S2; aquí C0 es su propio
            # control, así que esos dos recuentos relativos no son comparables y se omiten.
            for relative in ("stop_igual_centro", "stop_y_target2_iguales_centro"):
                observed.pop(relative, None)
                expected.pop(relative, None)
        checks.append((f"inventario estructural {key}", observed, expected, observed == expected))


def _append_p4_level_hash_checks(checks: List[Tuple[str, Any, Any, bool]], niveles: Mapping[str, Mapping[str, Any]]) -> None:
    p4_preflight = _load_json_if_present(P4_PREFLIGHT_JSON)
    expected = None if p4_preflight is None else p4_preflight.get("niveles_sha256", {})
    if not isinstance(expected, Mapping):
        checks.append(("p4-preflight niveles_sha256 presente", False, True, False))
        return
    for gid in ("C0", "B2", "S2"):
        observed_hash = niveles.get(gid, {}).get("levels_sha256")
        expected_hash = expected.get(gid)
        checks.append((f"levels_sha256 {gid} coincide con P4", observed_hash, expected_hash, observed_hash == expected_hash))


def preflight_fingerprint(report: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "poblacion": report.get("poblacion"),
        "bloques": report.get("bloques"),
        "rejilla": report.get("rejilla"),
        "semiplanos": report.get("semiplanos"),
        "locro": report.get("locro"),
        "recuento": report.get("recuento"),
        "grid_sha256": report.get("grid_sha256"),
        "hashes": report.get("hashes"),
        "p4_reproduccion": {
            "p4_published_results_reproduced": report.get("p4_reproduccion", {}).get("p4_published_results_reproduced"),
            "checks": report.get("p4_reproduccion", {}).get("checks"),
        },
    }


def run_preflight(
    config: AdvisorConfig,
    universe: Universe,
    vintage: VintageLoad,
    ident: P5Identity,
    *,
    development: bool = False,
    write: bool = True,
    out_dir: Path = PREFLIGHT_DIR,
) -> Tuple[bool, Dict[str, Any]]:
    frozen = _run_preflight_frozen(config, universe, vintage, ident, development=development, write=write, out_dir=out_dir)
    return bool(frozen.report["ok"]), frozen.report


def _run_preflight_frozen(
    config: AdvisorConfig,
    universe: Universe,
    vintage: VintageLoad,
    ident: P5Identity,
    *,
    development: bool = False,
    write: bool = True,
    out_dir: Path = PREFLIGHT_DIR,
) -> P5FrozenPreflight:
    population = build_population(config, universe, vintage)
    levels = _levels_by_cell(population, config.levels) if population.ok else {}
    checks: List[Tuple[str, Any, Any, bool]] = []

    def check(name: str, observed: Any, expected: Any) -> None:
        checks.append((name, observed, expected, observed == expected))

    check("population_sha256", population.population_sha256, P5_POPULATION_SHA256)
    check("signal_ids_sha256", population.signal_ids_sha256, P5_SIGNAL_IDS_SHA256)
    check("config_hash", ident.config_hash, EXPECTED_CONFIG_HASH)
    check("score_model_version", config.scoring.score_model_version, "1.0")
    check("P5_PREREG_SHA en la historia", ident.prereg_in_history, True)
    check("C0 levels_config igual a config.levels", C0_CELL.levels_config(config.levels).model_dump(), config.levels.model_dump())
    check("C0 min_rr igual a config.risk.min_rr_ratio", C0_CELL.min_rr, config.risk.min_rr_ratio)
    check("recuento P5", planned_comparisons()["total"], EXPECTED_P5_COMPARISONS)
    check("confirmatorias nuevas", len(NEW_CONFIRMATORY), EXPECTED_NEW_CONFIRMATORY)
    locro = locro_denominators(population)
    for region, expected in LOCRO_DENOMINATORS.items():
        check(f"LOCRO sin {region}", locro[region]["poblacion"], expected)

    hashes = {cell.gid: published_cell_hash(config, cell) for cell in GRID if cell.role != ROLE_ABSENCE}
    gate = OutcomeGate(marker_exists=(CONFIRMATORY_OUTPUT_DIR / RUN_MARKER).exists(), phase="preflight")
    p4_repro = reproduce_p4_whitelist(gate, population, vintage, config, config.levels, levels) if population.ok else {"p4_published_results_reproduced": False, "checks": []}
    check("P4 publicado reproducido", p4_repro.get("p4_published_results_reproduced"), True)
    niveles = structural_levels_report(population, config.levels, levels) if population.ok else {}
    _append_structural_inventory_checks(checks, niveles)
    _append_p4_level_hash_checks(checks, niveles)
    report: Dict[str, Any] = {
        "fase": "preflight",
        "modo": "DESARROLLO (no es evidencia)" if development else "DEFINITIVO",
        "identidad": ident.as_dict(),
        "inicio_utc": utc_now(),
        "new_p5_outcomes_read": False,
        "outcomes_leidos": "solo C0/B2/S2, solo estimaciones ya publicadas en P4",
        "p5_confirmatory_executed": (CONFIRMATORY_OUTPUT_DIR / RUN_MARKER).exists(),
        "poblacion": {
            "p5": len(population.signals),
            "activos": len({s.asset for s in population.signals}),
            "p5_population_sha256": population.population_sha256,
            "signal_ids_sha256": population.signal_ids_sha256,
            "regiones": population.regions,
            "ok": population.ok,
        },
        "bloques": {str(length): summary for length, summary in population.blocks.items() if length in (60, 120)},
        "rejilla": [cell.as_dict() for cell in GRID],
        "semiplanos": SEMIPLANES,
        "niveles": niveles,
        "locro": locro,
        "recuento": planned_comparisons(),
        "grid_sha256": grid_sha256(),
        "hashes": hashes,
        "p4_reproduccion": p4_repro,
        "checks": _checks_dicts(tuple(population.checks) + tuple(checks)),
        "label": UNIVERSE_LABEL,
        "fin_utc": utc_now(),
    }
    ok = all(row["ok"] for row in report["checks"])
    report["ok"] = ok
    report["definitivo"] = bool(ok and not development and ident.git_dirty is False and ident.prereg_in_history is True)
    if write and not development:
        if ident.git_dirty is not False:
            raise P5PreflightError("el preflight definitivo solo se escribe con árbol limpio")
        out_dir.mkdir(parents=True, exist_ok=True)
        write_json(out_dir / "p5-preflight.json", report)
        (out_dir / "p5-preflight.txt").write_text(format_preflight(report), encoding="utf-8")
    return P5FrozenPreflight(population=population, levels=dict(levels), report=report)


def format_preflight(report: Mapping[str, Any]) -> str:
    lines = [
        "# P5 preflight",
        f"modo: {report['modo']}",
        f"ok: {report.get('ok')}",
        f"definitivo: {report.get('definitivo')}",
        f"poblacion: {report['poblacion'].get('p5')} señales",
        f"recuento P5: {report['recuento']['total']} comparaciones; confirmatorias nuevas {report['recuento']['confirmatorias_nuevas']}",
        f"P4 reproducido: {report['p4_reproduccion'].get('p4_published_results_reproduced')}",
        f"label: {UNIVERSE_LABEL}",
        "",
    ]
    failed = [row for row in report["checks"] if not row["ok"]]
    if failed:
        lines.append("Checks fallidos:")
        lines.extend(f"- {row['control']}: observado={row['observado']} esperado={row['esperado']}" for row in failed)
    else:
        lines.append("Checks: todos OK.")
    p4_checks = cast(Sequence[Mapping[str, Any]], report.get("p4_reproduccion", {}).get("checks", ()))
    failed_p4 = [row for row in p4_checks if not row.get("ok")]
    lines.append(f"Reproducción de P4: {len(p4_checks) - len(failed_p4)}/{len(p4_checks)} cadenas iguales.")
    lines.extend(
        f"- P4 {row.get('clave')} {row.get('columna')}: observado={row.get('observado')} esperado={row.get('esperado')}"
        for row in failed_p4
    )
    return "\n".join(lines) + "\n"


def _load_stored_preflight(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise P5PreflightError(f"falta el preflight definitivo en {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not (data.get("ok") is True and data.get("definitivo") is True):
        raise P5PreflightError(f"{path} no es un preflight definitivo y correcto")
    return cast(Dict[str, Any], data)


def _p4_veto_conditions(center_id: str, tables_dir: Path = P4_RUN_TABLES) -> Dict[str, bool]:
    conditions: Dict[str, bool] = {}
    for row in _read_tsv(tables_dir / "criterio.tsv"):
        if row.get("geometria") != center_id or row.get("veta") != "True":
            continue
        condition_id = row.get("condicion", "")
        conditions[f"P4_{condition_id}"] = row.get("cumple") == "True"
    return conditions


def _normalized(value: Any) -> Any:
    return json.loads(json.dumps(_finite(value), default=_json_default, sort_keys=True))


def marker_payload(started: str, ident: P5Identity, executor: str, preflight: Mapping[str, Any]) -> Dict[str, Any]:
    valid_cell_ids = [cell.gid for cell in GRID if cell.role != ROLE_ABSENCE]
    return {
        "inicio_utc": started,
        "p5_prereg_sha": P5_PREREG_SHA,
        "p5_code_sha_preflight": executor,
        "head_sha": ident.executor_sha,
        "data_vintage_id": DATA_VINTAGE_ID,
        "universe_vintage_id": UNIVERSE_VINTAGE_ID,
        "population_sha256": P5_POPULATION_SHA256,
        "signal_ids_sha256": P5_SIGNAL_IDS_SHA256,
        "grid_sha256": preflight["grid_sha256"],
        "policy_sha256_centros": {gid: preflight["hashes"][gid]["policy_sha256"] for gid in ("B2", "S2")},
        "diagnostico_sha256_vecinos": {
            cell.gid: preflight["hashes"][cell.gid]["diagnostico_sha256"] for cell in GRID if cell.role == ROLE_NEIGHBOR
        },
        "levels_sha256": {
            gid: preflight.get("niveles", {}).get(gid, {}).get("levels_sha256")
            for gid in valid_cell_ids
        },
        "semiplanos": SEMIPLANES,
        "locro": preflight["locro"],
        "seed": SEED,
        "recuento": planned_comparisons()["total"],
        "label": UNIVERSE_LABEL,
    }


def _center_evidence(center_id: str, p4_repro: Mapping[str, Any]) -> CenterEvidence:
    center_data = cast(Mapping[str, Any], p4_repro.get(center_id, {}))
    aggregates = cast(Mapping[str, Any], center_data.get("agregados", {}))
    estimates = cast(Mapping[str, Any], aggregates.get("estimaciones", {}))
    halves = cast(Mapping[str, Any], estimates.get("mitades", {}))
    first = cast(Mapping[str, Any], halves.get("bloques_2_11", {}))
    second = cast(Mapping[str, Any], halves.get("bloques_12_21", {}))
    sensitivity = cast(Mapping[str, Any], estimates.get("bloque_120", {}))
    conservative = cast(Mapping[str, Any], estimates.get("cota_conservadora", {}))
    level = cast(Mapping[str, Any], estimates.get("nivel", {}))
    p4_conditions = _p4_veto_conditions(center_id)
    if not p4_conditions:
        p4_conditions = {"p4_condiciones_publicadas": False}
    return CenterEvidence(
        center_id=center_id,
        p4_reproducido=bool(p4_repro.get("p4_published_results_reproduced")),
        p4_conditions=p4_conditions,
        first_half_mean=cast(Optional[float], first.get("media_delta_r")),
        second_half_mean=cast(Optional[float], second.get("media_delta_r")),
        sensitivity_120_mean=cast(Optional[float], sensitivity.get("media_delta_r")),
        sensitivity_120_lower=cast(Optional[float], sensitivity.get("ic_inferior")),
        conservative_bound_mean=cast(Optional[float], conservative.get("media_delta_r")),
        level_mean=cast(Optional[float], level.get("media_net_r")),
        profit_factor=cast(Optional[float], level.get("profit_factor_agrupado")),
    )


def _classify_neighbor(observed: Mapping[str, Any]) -> str:
    estimates = cast(Mapping[str, Any], observed.get("estimaciones", {}))
    return classify_cell(
        cast(Mapping[str, Any], estimates.get("primaria_60", {})),
        cast(Mapping[str, Any], estimates.get("cota_conservadora", {})),
        cast(Mapping[str, Any], estimates.get("nivel", {})),
        cast(Mapping[str, Any], observed.get("capacidad", {})),
        cast(Optional[float], observed.get("profit_factor")),
    )


def _strip_transient_estimate(observed: Mapping[str, Any]) -> Dict[str, Any]:
    out = dict(observed)
    out.pop("deltas", None)
    return out


def _neighbor_publication_view(observed: Mapping[str, Any]) -> Dict[str, Any]:
    """Lo que se publica de un vecino (D-66): sus 5 estimaciones con IC95 y las mitades solo como puntos.

    Primaria 60, bloque 120, las dos cotas y el nivel llevan su IC: son las 5 comparaciones
    pre-registradas del vecino. Las mitades de un vecino son descriptivas y puntuales, y un IC
    suyo sería un intervalo no pre-registrado: se publican sin `ic_*`.
    """

    out = _strip_transient_estimate(observed)
    estimates = cast(Mapping[str, Any], out.get("estimaciones", {}))
    published: Dict[str, Any] = {}
    for key, value in estimates.items():
        if key == "mitades" and isinstance(value, Mapping):
            published[key] = {
                name: {
                    "n_pares": row.get("n_pares"),
                    "n_bloques": row.get("n_bloques"),
                    "media_delta_r": row.get("media_delta_r"),
                }
                for name, row in value.items()
                if isinstance(row, Mapping)
            }
        elif isinstance(value, Mapping):
            published[key] = dict(value)
    out["estimaciones"] = published
    return out


def _write_tsv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    prefix = [f"# {UNIVERSE_LABEL}"]
    if not rows:
        path.write_text("\n".join(prefix) + "\n", encoding="utf-8")
        return
    columns = list(rows[0].keys())
    lines = [*prefix, "\t".join(columns)]
    for row in rows:
        lines.append("\t".join(_cell(row.get(column)) for column in columns))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _estimate_value(estimates: Mapping[str, Any], name: str, column: str) -> Any:
    row = estimates.get(name)
    return row.get(column) if isinstance(row, Mapping) else None


def _surface_row(gid: str, observed: Mapping[str, Any], klass: str, p4_repro: Mapping[str, Any]) -> Dict[str, Any]:
    cell_data = cast(Mapping[str, Any], observed["celda"])
    center_id = str(cell_data["centro"])
    estimates = cast(Mapping[str, Any], observed.get("estimaciones", {}))
    capacity = cast(Mapping[str, Any], observed.get("capacidad", {}))
    halves = cast(Mapping[str, Any], estimates.get("mitades", {}))
    first = cast(Mapping[str, Any], halves.get("bloques_2_11", {}))
    second = cast(Mapping[str, Any], halves.get("bloques_12_21", {}))
    center_data = cast(Mapping[str, Any], p4_repro.get(center_id, {}))
    center_aggregates = cast(Mapping[str, Any], center_data.get("agregados", {}))
    center_estimates = cast(Mapping[str, Any], center_aggregates.get("estimaciones", {}))
    center_primary = cast(Mapping[str, Any], center_estimates.get("primaria_60", {}))
    primary_mean = _estimate_value(estimates, "primaria_60", "media_delta_r")
    center_mean = center_primary.get("media_delta_r")
    retention = primary_mean / center_mean if isinstance(primary_mean, (int, float)) and isinstance(center_mean, (int, float)) and center_mean else None
    return {
        "celda": gid,
        "centro": center_id,
        "s": cell_data.get("atr_stop_multiple"),
        "m2": cast(Sequence[Any], cell_data.get("target_atr_multiples", []))[1],
        "m3": cast(Sequence[Any], cell_data.get("target_atr_multiples", []))[2],
        "m3_auxiliar": cell_data.get("m3_auxiliar"),
        "rol": cell_data.get("rol"),
        "clase": klass,
        "delta_r": primary_mean,
        "ic95_inferior": _estimate_value(estimates, "primaria_60", "ic_inferior"),
        "ic95_superior": _estimate_value(estimates, "primaria_60", "ic_superior"),
        "pares": _estimate_value(estimates, "primaria_60", "n_pares"),
        "capacidad_ok": capacity.get("ok"),
        "capacidad_motivos": "; ".join(capacity.get("motivos", [])) if isinstance(capacity.get("motivos"), list) else capacity.get("motivos"),
        "bloque_120_media": _estimate_value(estimates, "bloque_120", "media_delta_r"),
        "bloque_120_ic95_inferior": _estimate_value(estimates, "bloque_120", "ic_inferior"),
        "bloque_120_ic95_superior": _estimate_value(estimates, "bloque_120", "ic_superior"),
        "cota_conservadora_media": _estimate_value(estimates, "cota_conservadora", "media_delta_r"),
        "cota_conservadora_ic95_inferior": _estimate_value(estimates, "cota_conservadora", "ic_inferior"),
        "cota_conservadora_ic95_superior": _estimate_value(estimates, "cota_conservadora", "ic_superior"),
        "cota_favorable_media": _estimate_value(estimates, "cota_favorable", "media_delta_r"),
        "cota_favorable_ic95_inferior": _estimate_value(estimates, "cota_favorable", "ic_inferior"),
        "cota_favorable_ic95_superior": _estimate_value(estimates, "cota_favorable", "ic_superior"),
        "nivel_media": _estimate_value(estimates, "nivel", "media_net_r"),
        "nivel_ic95_inferior": _estimate_value(estimates, "nivel", "ic_inferior"),
        "nivel_ic95_superior": _estimate_value(estimates, "nivel", "ic_superior"),
        "pf": _estimate_value(estimates, "nivel", "profit_factor_agrupado"),
        "mitad_2_11_media": first.get("media_delta_r"),
        "mitad_12_21_media": second.get("media_delta_r"),
        "retencion_delta_r_centro": retention,
        "heterogeneidad": _estimate_value(estimates, "primaria_60", "heterogeneidad"),
        "fraccion_pares": cast(Mapping[str, Any], observed.get("emparejamiento", {})).get("fraccion_pares"),
        "tasa_descarte": cast(Mapping[str, Any], observed.get("emparejamiento", {})).get("tasa_descarte_ambiguedad"),
    }


def run_confirmatory(
    config: AdvisorConfig,
    universe: Universe,
    vintage: VintageLoad,
    ident: P5Identity,
    out_dir: Path,
) -> Tuple[int, str]:
    if out_dir.resolve() != CONFIRMATORY_OUTPUT_DIR.resolve():
        raise P5PreflightError(f"la ejecución confirmatoria solo escribe en {CONFIRMATORY_OUTPUT_DIR}")
    marker = out_dir / RUN_MARKER
    if marker.exists():
        raise P5AlreadyExecutedError(f"la ejecución confirmatoria ya se inició ({marker}); P5 no se repite")
    if ident.git_dirty is not False:
        raise P5PreflightError(f"el árbol no está limpio o no se pudo comprobar (git_dirty={ident.git_dirty})")
    if ident.prereg_in_history is not True:
        raise P5PreflightError(f"P5_PREREG_SHA {P5_PREREG_SHA} no está en la historia de HEAD")
    if out_dir.exists() and any(out_dir.iterdir()):
        raise P5AlreadyExecutedError(f"{out_dir} no está vacío: P5 no se repite ni se sobrescribe")
    stored = _load_stored_preflight(PREFLIGHT_DIR / "p5-preflight.json")
    executor = str(stored["identidad"]["p5_executor_sha"])
    if not executor_unchanged_since(executor, "."):
        raise P5PreflightError(f"el ejecutor cambió desde el preflight definitivo ({executor}): P5 no se ejecuta")
    frozen = _run_preflight_frozen(config, universe, vintage, ident, write=False)
    ok = bool(frozen.report["ok"])
    preflight = frozen.report
    if not ok:
        return 2, format_preflight(preflight) + "PREFLIGHT FALLIDO: P5 NO SE EJECUTA.\n"
    if _normalized(preflight_fingerprint(preflight)) != _normalized(preflight_fingerprint(stored)):
        return 2, "STOP: el preflight interno no coincide con el preflight definitivo guardado. P5 NO SE EJECUTA.\n"
    out_dir.mkdir(parents=True, exist_ok=True)
    started = utc_now()
    payload = marker_payload(started, ident, executor, preflight)
    marker.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    token = build_confirmatory_token(marker, payload)
    try:
        population = frozen.population
        levels = frozen.levels
        observed_level_hashes = {gid: levels_sha256(value) for gid, value in levels.items()}
        if observed_level_hashes != payload["levels_sha256"]:
            raise P5PreflightError("los levels_sha256 de ejecución no coinciden con la marca confirmatoria")
        gate = OutcomeGate(marker_exists=True, phase="confirmatoria")
        control, control_potentials, _ = gate.evaluate_frozen(population, vintage, C0_CELL, levels["C0"], token=token)
        centers: Dict[str, Tuple[Dict[str, ManagedEvent], Dict[str, PotentialEvent], Tuple[str, ...]]] = {}
        for center_cell in (B2_CELL, S2_CELL):
            centers[center_cell.gid] = gate.evaluate_frozen(population, vintage, center_cell, levels[center_cell.gid], token=token)

        neighbor_outputs: Dict[str, Dict[str, Any]] = {}
        neighbor_full_outputs: Dict[str, Dict[str, Any]] = {}
        neighbor_classes: Dict[str, Dict[str, str]] = {"B2": {}, "S2": {}}
        concentration: Dict[str, Dict[str, Any]] = {}
        for center_id in ("B2", "S2"):
            for cell in neighbors(center_id):
                observed = estimate_neighbor(
                    token,
                    cell,
                    population,
                    vintage,
                    control,
                    control_potentials,
                    config.levels,
                    gate,
                    levels[cell.gid],
                )
                neighbor_classes[center_id][cell.gid] = _classify_neighbor(observed)
                neighbor_full_outputs[cell.gid] = _strip_transient_estimate(observed)
                neighbor_outputs[cell.gid] = _neighbor_publication_view(observed)

        locro_outputs: Dict[str, Dict[str, Any]] = {"B2": {}, "S2": {}}
        for center_cell in (B2_CELL, S2_CELL):
            center_events = centers[center_cell.gid][0]
            for region in CORE_REGIONS:
                locro_outputs[center_cell.gid][region] = estimate_locro(token, center_cell, region, population, control, center_events)
            paired = pair_populations({sid: control[sid] for sid in center_events}, center_events)
            signal_by_id = {signal.signal_id: signal for signal in population.signals}
            deltas = [_delta(signal_by_id[delta.signal_id], delta.net_r_a, delta.net_r_b) for delta in paired.deltas]
            concentration[center_cell.gid] = estimate_asset_concentration(token, deltas)

        criteria = {
            center_id: evaluate_candidate(_center_evidence(center_id, preflight["p4_reproduccion"]), neighbor_classes[center_id], locro_outputs[center_id])
            for center_id in ("B2", "S2")
        }
        survivor_ids = survivors(criteria)
        derived_count = sum(
            sum(1 for key in ("primaria_60", "bloque_120", "cota_conservadora", "cota_favorable", "nivel") if key in row["estimaciones"])
            for row in neighbor_outputs.values()
        ) + sum(len(rows) for rows in locro_outputs.values())
        if derived_count != planned_comparisons()["total"]:
            raise P5PreflightError(f"recuento derivado de salidas {derived_count} != {planned_comparisons()['total']}")

        tables_dir = out_dir / "tablas"
        tables_dir.mkdir(parents=True, exist_ok=True)
        _write_tsv(
            tables_dir / "clases.tsv",
            [{"centro": center, "celda": gid, "clase": klass} for center, rows in neighbor_classes.items() for gid, klass in rows.items()],
        )
        _write_tsv(
            tables_dir / "locro.tsv",
            [
                {
                    "centro": center,
                    "sin_region": region,
                    "denominador": row.get("denominador"),
                    "pares": (row.get("estimacion") or {}).get("n_pares") if isinstance(row.get("estimacion"), Mapping) else None,
                    "estimable": locro_row(row).estimable,
                    "media_delta_r": (row.get("estimacion") or {}).get("media_delta_r") if isinstance(row.get("estimacion"), Mapping) else None,
                    "ic_inferior": locro_row(row).ic_inferior,
                    "ic_superior": (row.get("estimacion") or {}).get("ic_superior") if isinstance(row.get("estimacion"), Mapping) else None,
                    "pares_minimos": row.get("pares_minimos"),
                    "motivos": "; ".join(row.get("capacidad", {}).get("motivos", [])) if isinstance(row.get("capacidad"), Mapping) else None,
                }
                for center, rows in locro_outputs.items()
                for region, row in rows.items()
            ],
        )
        _write_tsv(
            tables_dir / "criterio.tsv",
            [
                {"centro": center_id, "condicion": condition, "valor": value, "etiqueta": row["etiqueta"], "sobrevive": row["sobrevive"]}
                for center_id, row in criteria.items()
                for condition, value in row["condiciones"].items()
            ],
        )
        _write_tsv(tables_dir / "recuento.tsv", [{"comparaciones_derivadas": derived_count, "esperadas": planned_comparisons()["total"]}])
        _write_tsv(
            tables_dir / "semiplanos.tsv",
            [{"centro": center, "semiplano": name, "celdas": ",".join(gids)} for center, planes in SEMIPLANES.items() for name, gids in planes.items()],
        )
        _write_tsv(
            tables_dir / "concentracion.tsv",
            [
                {
                    "centro": center,
                    "activos_positivos": row.get("activos_positivos"),
                    "activos_negativos": row.get("activos_negativos"),
                    **cast(Mapping[str, Any], row.get("percentiles_media_agrupada", {})),
                    **cast(Mapping[str, Any], row.get("participacion", {})),
                }
                for center, row in concentration.items()
            ],
        )
        _write_tsv(
            tables_dir / "superficie.tsv",
            [_surface_row(gid, row, neighbor_classes[row["celda"]["centro"]][gid], preflight["p4_reproduccion"]) for gid, row in neighbor_full_outputs.items()],
        )

        result = {
            "fase": "confirmatoria",
            "token_sha256": token.marker_payload_sha256,
            "preflight": preflight_fingerprint(preflight),
            "levels_sha256": observed_level_hashes,
            "vecinos": neighbor_outputs,
            "clases": neighbor_classes,
            "locro": locro_outputs,
            "concentracion": concentration,
            "criterio": criteria,
            "survivors": list(survivor_ids),
            "recuento_derivado": derived_count,
            "label": UNIVERSE_LABEL,
            "fin_utc": utc_now(),
        }
        write_json(out_dir / "p5-resultado.json", result)
        summary = (
            "# P5 confirmatoria\n\n"
            f"- marca: {RUN_MARKER}\n"
            f"- comparaciones derivadas: {derived_count}\n"
            f"- B2: {criteria['B2']['etiqueta']}\n"
            f"- S2: {criteria['S2']['etiqueta']}\n"
            f"- survivors: {', '.join(survivor_ids) if survivor_ids else 'ninguno'}\n"
        )
        (out_dir / "p5-resumen.md").write_text(summary, encoding="utf-8")
        return 0, summary
    except Exception as exc:
        parada = {"fase": "confirmatoria", "parada": type(exc).__name__, "detalle": str(exc), "fin_utc": utc_now()}
        write_json(out_dir / "p5-parada.json", parada)
        return 2, f"STOP P5 confirmatoria: {type(exc).__name__}: {exc}\n"
