"""Tests pre-registrados del ejecutor de P5 (T-021 / A-05).

Los tests ejecutables aquí son sintéticos o estructurales. Los que tocan la
cosecha real se saltan si falta un CSV real; no basta con que exista el
manifiesto versionado.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import replace
from inspect import signature
from pathlib import Path
from typing import Any, Dict, Iterator

import pytest

import advisor.research.event_study as event_study
import advisor.research.p5 as p5
from advisor.config import load_config
from advisor.research.vintage import load_vintage
from advisor.universe.loader import load_universe

REAL_CSV = Path("data/vintages") / p5.DATA_VINTAGE_ID / "AAPL.csv"


def _cosecha_disponible() -> bool:
    return REAL_CSV.is_file()


def _primary(mean: float = 0.1, lower: float = 0.02) -> Dict[str, float]:
    return {"media_delta_r": mean, "ic_inferior": lower}


def _conservative(mean: float = 0.05) -> Dict[str, float]:
    return {"media_delta_r": mean}


def _level(mean: float = 0.2) -> Dict[str, float]:
    return {"media_net_r": mean}


def _capacity(ok: bool = True) -> Dict[str, Any]:
    return {"ok": ok, "motivos": [] if ok else ["sin capacidad"]}


def _p4_conditions(**changes: bool) -> Dict[str, bool]:
    conditions = dict.fromkeys(sorted(p5.EXPECTED_P4_VETO_CONDITIONS), True)
    conditions.update(changes)
    return conditions


def _center(**changes: Any) -> p5.CenterEvidence:
    base = p5.CenterEvidence(
        center_id="B2",
        p4_reproducido=True,
        p4_conditions=_p4_conditions(),
        first_half_mean=0.1,
        second_half_mean=0.1,
        sensitivity_120_mean=0.1,
        sensitivity_120_lower=0.02,
        conservative_bound_mean=0.05,
        level_mean=0.2,
        profit_factor=1.4,
    )
    return replace(base, **changes)


def _classes(center: str = "B2", klass: str = p5.ACEPTABLE) -> Dict[str, str]:
    return {cell.gid: klass for cell in p5.neighbors(center)}


def _locro_row(center: str, region: str, ok: bool = True, lower: float = 0.01) -> Dict[str, Any]:
    return {
        "centro": center,
        "sin_region": region,
        "denominador": p5.LOCRO_DENOMINATORS[region],
        "pares_minimos": p5.LOCRO_MIN_PAIRS[region],
        "estimacion": {"ic_inferior": lower},
        "capacidad": {"ok": ok},
    }


def _locro(ok: bool = True, lower: float = 0.01, center: str = "B2") -> Dict[str, Dict[str, Any]]:
    return {region: _locro_row(center, region, ok, lower) for region in p5.CORE_REGIONS}


@pytest.fixture(scope="module")
def real_p5_reproduction() -> Iterator[Dict[str, Any]]:
    if not _cosecha_disponible():
        pytest.skip(f"falta {REAL_CSV}: la cosecha no está en esta máquina")
    config = load_config("config.yaml")
    universe = load_universe(config.universe_path)
    vintage = load_vintage(p5.DATA_VINTAGE_ID)
    started = time.perf_counter()
    population = p5.build_population(config, universe, vintage)
    levels = p5._levels_by_cell(population, config.levels)
    gate = p5.OutcomeGate(marker_exists=False, phase="preflight")
    calls: list[str] = []
    original = p5.OutcomeGate.evaluate_frozen

    def spy(
        self: p5.OutcomeGate,
        population_arg: Any,
        vintage_arg: Any,
        cell: p5.P5Cell,
        levels_arg: Any,
        *,
        token: Any = None,
    ) -> Any:
        calls.append(cell.gid)
        return original(self, population_arg, vintage_arg, cell, levels_arg, token=token)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(p5.OutcomeGate, "evaluate_frozen", spy)
    try:
        reproduction = p5.reproduce_p4_whitelist(gate, population, vintage, config, config.levels, levels)
        yield {
            "config": config,
            "population": population,
            "reproduction": reproduction,
            "calls": tuple(calls),
            "elapsed": time.perf_counter() - started,
        }
    finally:
        monkeypatch.undo()


def test_constantes_de_identidad_exactas() -> None:
    assert p5.P5_PREREG_SHA == "a7c3d238d651b4ea8f48834848c03c0a5a462dfa"
    assert p5.DATA_VINTAGE_ID == "071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841"
    assert p5.UNIVERSE_VINTAGE_ID == "237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19"
    assert p5.P5_POPULATION_SHA256 == "78024050f7081ad4e1dd5cefaefbfa1a1668ff5b1a2ced8c34e62b6501873141"
    assert p5.P5_SIGNAL_IDS_SHA256 == "9faa4a45beaba3eb8dafabf7990906cd8c89e8e06ae2f25edec7839cd48e629f"
    assert p5.COST_PCT == 0.2 and p5.SEED == 20260830
    assert p5.RESAMPLES == 2000 and p5.CONFIDENCE == 0.95
    assert p5.EXPECTED_P5_COMPARISONS == 71
    assert p5.NEW_CONFIRMATORY == ()


def test_geometrias_c0_b2_s2_exactas() -> None:
    assert p5.C0_CELL.key == (2.0, 3.0, 5.0)
    assert p5.B2_CELL.key == (2.0, 4.875, 5.0)
    assert p5.S2_CELL.key == (2.5, 3.75, 5.0)
    assert p5.C0_CELL.role == p5.ROLE_CONTROL
    assert p5.B2_CELL.role == p5.ROLE_CENTER
    assert p5.S2_CELL.role == p5.ROLE_CENTER


def test_rejilla_b2_exacta() -> None:
    assert [(c.atr_stop_multiple, c.target_atr_multiples, c.m3_auxiliar) for c in p5.neighbors("B2")] == [
        (1.75, (1.5, 4.5, 5.0), False),
        (1.75, (1.5, 4.875, 5.0), False),
        (1.75, (1.5, 5.25, 5.625), True),
        (2.0, (1.5, 4.5, 5.0), False),
        (2.0, (1.5, 5.25, 5.625), True),
        (2.25, (1.5, 4.5, 5.0), False),
        (2.25, (1.5, 4.875, 5.0), False),
        (2.25, (1.5, 5.25, 5.625), True),
    ]


def test_rejilla_s2_exacta_y_ausencias() -> None:
    assert [(c.atr_stop_multiple, c.target_atr_multiples) for c in p5.neighbors("S2")] == [
        (2.25, (1.5, 3.375, 5.0)),
        (2.25, (1.5, 3.75, 5.0)),
        (2.25, (1.5, 4.125, 5.0)),
        (2.5, (1.5, 4.125, 5.0)),
        (2.75, (1.5, 4.125, 5.0)),
    ]
    assert [(c.atr_stop_multiple, c.target_atr_multiples[1], c.absence_reason) for c in p5.absences("S2")] == [
        (2.5, 3.375, "RR < 1.5"),
        (2.75, 3.375, "RR < 1.5"),
        (2.75, 3.75, "RR < 1.5"),
    ]


def test_recuentos_roles_y_target3_auxiliar() -> None:
    assert len(p5.neighbors("B2")) + len(p5.neighbors("S2")) == 13
    assert len(p5.absences()) == 3
    assert all(cell.role == p5.ROLE_ABSENCE for cell in p5.absences())
    auxiliar = [cell for cell in p5.GRID if cell.m3_auxiliar]
    assert len(auxiliar) == 3
    assert {cell.target_atr_multiples[2] for cell in auxiliar} == {5.625}
    assert p5.B2_CELL.target_atr_multiples[2] == 5.0
    assert all(cell.target_atr_multiples[2] == 5.0 for cell in p5.GRID if not cell.m3_auxiliar)


def test_frontera_rr_de_s2() -> None:
    for cell in p5.neighbors("S2"):
        assert cell.target_atr_multiples[1] / cell.atr_stop_multiple >= 1.5 - 1e-12
    for cell in p5.absences("S2"):
        assert cell.target_atr_multiples[1] / cell.atr_stop_multiple < 1.5


def test_semiplanos_exactos() -> None:
    b2 = p5.SEMIPLANES["B2"]
    assert len(b2["s_minus"]) == len(b2["s_plus"]) == len(b2["m2_minus"]) == len(b2["m2_plus"]) == 3
    s2 = p5.SEMIPLANES["S2"]
    assert len(s2["s_minus"]) == 3
    assert len(s2["s_plus"]) == 1
    assert len(s2["m2_minus"]) == 1
    assert len(s2["m2_plus"]) == 3


def test_recuento_derivado_71_y_locro() -> None:
    count = p5.planned_comparisons()
    assert count["subtotales"] == {"B2": 43, "S2": 28}
    assert count["total"] == 71 and count["ok"] is True
    den = p5.locro_denominators()
    assert den["USA"] == {"poblacion": 56353, "pares_minimos": 50718}
    assert den["EUROPA"] == {"poblacion": 66629, "pares_minimos": 59967}
    assert den["ASIA"] == {"poblacion": 83298, "pares_minimos": 74969}
    assert all(row["pares_minimos"] != p5.CELL_MIN_PAIRS for row in den.values())


def test_target3_auxiliar_inerte_con_barras_sinteticas() -> None:
    obs = __import__("tests.test_p4", fromlist=["_obs"]). _obs()
    frame = __import__("tests.test_p4", fromlist=["_frame"]). _frame(
        [(100, 100, 100, 100), (100, 106, 99, 105), (100, 106, 99, 105)]
    )
    levels_a = p5.B2_CELL.as_geometry().levels_config(__import__("tests.test_p4", fromlist=["BASE"]).BASE)
    cell = next(c for c in p5.neighbors("B2") if c.m3_auxiliar)
    levels_b = cell.as_geometry().levels_config(__import__("tests.test_p4", fromlist=["BASE"]).BASE)
    la = p5.geometry_levels(obs, p5.B2_CELL.as_geometry(), levels_a)
    lb = p5.geometry_levels(obs, cell.as_geometry(), levels_b)
    assert la is not None and lb is not None
    lb = replace(lb, stop=la.stop, target2=la.target2)
    ea = event_study.evaluate_managed_event(obs, frame, obs.signal_idx, la, 40, p5.COST_PCT)
    eb = event_study.evaluate_managed_event(obs, frame, obs.signal_idx, lb, 40, p5.COST_PCT)
    assert (ea.exit_status, ea.net_r_multiple) == (eb.exit_status, eb.net_r_multiple)


def test_hash_canonico_y_publicacion_de_vecinos() -> None:
    config = load_config("config.yaml")
    assert p5.advisor_config_hash(config, p5.C0_CELL) == p5.EXPECTED_CONFIG_HASH
    first = p5.policy_sha256(config, p5.B2_CELL)
    second = p5.policy_sha256(config, p5.B2_CELL)
    assert first == second
    neighbor = p5.neighbors("B2")[0]
    published = p5.published_cell_hash(config, neighbor)
    assert "diagnostico_sha256" in published and "policy_sha256" not in published
    assert p5.policy_payload(config, p5.B2_CELL)["geometria"]["entry_max_atr"] == config.levels.entry_max_atr
    assert p5.policy_payload(config, p5.B2_CELL)["geometria"]["min_rr"] == config.risk.min_rr_ratio
    with pytest.raises(ValueError):
        p5.canonical_json({"bad": math.nan})


def test_canonical_json_nan_lanza_value_error() -> None:
    with pytest.raises(ValueError):
        p5.canonical_json({"x": float("nan")})


def test_config_hash_c0_y_score_model_version_reales() -> None:
    config = load_config("config.yaml")
    assert config.scoring.score_model_version == "1.0"
    assert p5.advisor_config_hash(config, p5.C0_CELL) == p5.EXPECTED_CONFIG_HASH
    assert p5.config_hash(config) == p5.EXPECTED_CONFIG_HASH


def test_guarda_pre_marca_solo_autoriza_c0_b2_s2() -> None:
    gate = p5.OutcomeGate(marker_exists=False, phase="preflight")
    for cell in (p5.C0_CELL, p5.B2_CELL, p5.S2_CELL):
        gate.require_pre_marker_allowed(cell)
    with pytest.raises(p5.P5OutcomeGateError):
        gate.require_pre_marker_allowed(p5.neighbors("B2")[0])
    with pytest.raises(p5.P5OutcomeGateError):
        gate.require_pre_marker_allowed(p5.neighbors("S2")[0])


def test_estimaciones_nuevas_exigen_token() -> None:
    with pytest.raises(p5.P5OutcomeGateError):
        p5.estimate_region(token=None)
    with pytest.raises(p5.P5OutcomeGateError):
        p5.estimate_asset_concentration(None, [])
    with pytest.raises(p5.P5OutcomeGateError):
        p5.estimate_locro(None, p5.B2_CELL, "USA", None, {}, {})  # type: ignore[arg-type]


def test_estimate_region_sin_token_error() -> None:
    with pytest.raises(p5.P5OutcomeGateError):
        p5.estimate_region()


def test_clasificacion_de_celdas() -> None:
    assert p5.classify_cell(_primary(), _conservative(), _level(), _capacity(), 1.2) == p5.ACEPTABLE
    assert p5.classify_cell(_primary(lower=-0.01), _conservative(), _level(), _capacity(), 1.2) == p5.DÉBIL
    assert p5.classify_cell(_primary(mean=0.0), _conservative(), _level(), _capacity(), 1.2) == p5.CONTRARIA
    assert p5.classify_cell(_primary(), _conservative(), _level(), _capacity(False), 1.2) == p5.NO_ESTIMABLE
    assert p5.classify_cell(_primary(), _conservative(mean=0.0), _level(), _capacity(), 1.2) == p5.DÉBIL


def test_criterio_meseta_y_precedencia() -> None:
    robust = p5.evaluate_candidate(_center(), _classes(), _locro())
    assert robust["etiqueta"] == p5.ROBUSTA and robust["sobrevive"] is True
    classes = _classes()
    classes[p5.neighbors("B2")[0].gid] = p5.CONTRARIA
    assert p5.evaluate_candidate(_center(), classes, _locro())["etiqueta"] == p5.FRÁGIL
    weak = _classes()
    for cell in p5.neighbors("B2")[:3]:
        weak[cell.gid] = p5.DÉBIL
    assert p5.evaluate_candidate(_center(), weak, _locro())["condiciones"]["F4"] is True
    dependent = p5.evaluate_candidate(_center(), _classes(), _locro(ok=True, lower=0.0))
    assert dependent["etiqueta"] == p5.DEPENDIENTE_DE_MERCADO
    inconclusive = p5.evaluate_candidate(_center(), _classes(), _locro(ok=False))
    assert inconclusive["etiqueta"] == p5.NO_CONCLUYENTE
    fragile_wins = p5.evaluate_candidate(_center(sensitivity_120_lower=-0.1), _classes(), _locro(ok=True, lower=0.0))
    assert fragile_wins["etiqueta"] == p5.FRÁGIL


def test_meseta_b2_seis_de_ocho_aceptables_robusta_cinco_fragil() -> None:
    six_of_eight = _classes("B2")
    six_of_eight[p5.neighbors("B2")[0].gid] = p5.DÉBIL
    six_of_eight[p5.neighbors("B2")[-1].gid] = p5.DÉBIL
    assert p5.evaluate_candidate(_center(), six_of_eight, _locro())["etiqueta"] == p5.ROBUSTA
    five_of_eight = dict(six_of_eight)
    five_of_eight[p5.neighbors("B2")[4].gid] = p5.DÉBIL
    verdict = p5.evaluate_candidate(_center(), five_of_eight, _locro())
    assert verdict["etiqueta"] == p5.FRÁGIL
    assert verdict["condiciones"]["F4"] is True


def test_no_estimables_uno_robusta_dos_no_concluyente() -> None:
    one = _classes("B2")
    one[p5.neighbors("B2")[0].gid] = p5.NO_ESTIMABLE
    assert p5.evaluate_candidate(_center(), one, _locro())["etiqueta"] == p5.ROBUSTA
    two = dict(one)
    two[p5.neighbors("B2")[-1].gid] = p5.NO_ESTIMABLE
    assert p5.evaluate_candidate(_center(), two, _locro())["etiqueta"] == p5.NO_CONCLUYENTE


def test_ausencias_no_entran_en_recuentos_de_vecinos() -> None:
    classes = _classes("S2")
    absence = p5.absences("S2")[0]
    with pytest.raises(ValueError, match="no esperadas"):
        p5.evaluate_candidate(replace(_center(), center_id="S2"), {**classes, absence.gid: p5.ACEPTABLE}, _locro(center="S2"))


def test_s2_vecinos_criticos_deben_ser_aceptables() -> None:
    classes = _classes("S2")
    critical = [*p5.SEMIPLANES["S2"]["s_plus"], *p5.SEMIPLANES["S2"]["m2_minus"]]
    assert len(set(critical)) == 2
    for gid in critical:
        changed = dict(classes)
        changed[gid] = p5.DÉBIL
        verdict = p5.evaluate_candidate(replace(_center(), center_id="S2"), changed, _locro(center="S2"))
        assert verdict["etiqueta"] == p5.FRÁGIL


def test_survivors_solo_b2_s2_y_vecino_no_elegible() -> None:
    assert p5.survivors({"B2": {"sobrevive": True}, "S2": {"sobrevive": False}}) == ("B2",)
    assert p5.survivors({"B2": {"sobrevive": True}, "S2": {"sobrevive": True}}) == ("B2", "S2")
    with pytest.raises(ValueError):
        p5.survivors({p5.neighbors("B2")[0].gid: {"sobrevive": True}})


def test_preflight_json_no_serializa_eventos_por_senal() -> None:
    report = {
        "new_p5_outcomes_read": False,
        "p4_reproduccion": {"checks": [{"clave": ["B2", "primaria_60", ""], "ok": True}]},
    }
    text = json.dumps(report)
    for forbidden in ("exit_status", "net_r_multiple", "signal_id"):
        assert forbidden not in text


def test_poblacion_real_skip_mira_un_csv_real() -> None:
    assert REAL_CSV.suffix == ".csv" and REAL_CSV.parent.name == p5.DATA_VINTAGE_ID
    if not _cosecha_disponible():
        pytest.skip(f"falta {REAL_CSV}: la cosecha no está en esta máquina")


def test_token_fabricado_sin_marca_rechazado(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "run"
    monkeypatch.setattr(p5, "CONFIRMATORY_OUTPUT_DIR", run_dir)
    token = p5.ConfirmatoryToken(run_dir / p5.RUN_MARKER, "0" * 64)
    with pytest.raises(p5.P5OutcomeGateError):
        p5.estimate_asset_concentration(token, [])


def test_token_con_sha_incorrecto_rechazado(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    marker = run_dir / p5.RUN_MARKER
    marker.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(p5, "CONFIRMATORY_OUTPUT_DIR", run_dir)
    with pytest.raises(p5.P5OutcomeGateError):
        p5.estimate_asset_concentration(p5.ConfirmatoryToken(marker, "0" * 64), [])


def test_outcome_gate_confirmatoria_sin_token_no_autoriza_vecino() -> None:
    gate = p5.OutcomeGate(marker_exists=True, phase="confirmatoria")
    with pytest.raises(p5.P5OutcomeGateError):
        gate.require_pre_marker_allowed(p5.neighbors("B2")[0])


def test_dependiente_de_mercado_con_formato_locro_real() -> None:
    locro = _locro(lower=0.1)
    locro["USA"] = _locro_row("B2", "USA", lower=0.0)
    verdict = p5.evaluate_candidate(_center(), _classes(), locro)
    assert verdict["etiqueta"] == p5.DEPENDIENTE_DE_MERCADO


def test_centro_p4_falso_veta_como_fragil() -> None:
    verdict = p5.evaluate_candidate(_center(p4_reproducido=False), _classes(), _locro())
    assert verdict["etiqueta"] == p5.FRÁGIL
    assert verdict["condiciones"]["centro_p4"] is False


def test_evaluate_candidate_no_acepta_heterogeneidad_ni_concentracion() -> None:
    params = signature(p5.evaluate_candidate).parameters
    assert tuple(params) == ("center_evidence", "neighbor_classes", "locro")


def test_capacidad_de_celda_exige_91126_y_locro_no() -> None:
    base = {"ok": True, "motivos": []}
    cell = p5._capacity_with_min_pairs(base, 91_125, p5.CELL_MIN_PAIRS, "celda")
    assert cell["ok"] is False
    assert "91126" in cell["motivos"][-1]
    locro = p5._capacity_with_min_pairs(base, 50_718, p5.LOCRO_MIN_PAIRS["USA"], "locro")
    assert locro["ok"] is True


def test_censo_estructural_y_locro_sinteticos_no_leen_desenlaces(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("no debe evaluar desenlaces")

    monkeypatch.setattr(event_study, "evaluate_managed_event", fail)
    monkeypatch.setattr(event_study, "evaluate_potential_event", fail)

    class Signal:
        def __init__(self, region: str) -> None:
            self.region = region

    population = _FakePopulation()
    population.signals = [Signal("USA"), Signal("EUROPA"), Signal("ASIA"), Signal("USA")]
    assert p5.structural_region_census(population) == {"sin_ASIA": 3, "sin_EUROPA": 3, "sin_USA": 2}
    assert p5.locro_denominators(population)["USA"]["poblacion"] == 2


def test_compare_p4_rows_estricto_detecta_un_digito(tmp_path: Path) -> None:
    tables = tmp_path
    (tables / "estimaciones.tsv").write_text(
        "comparacion\testimacion\testrato\tpapel\tn_pares\tn_bloques\tmin_pares_bloque\tmedia_delta_r\tmedia_agrupada_delta_r\tic_inferior\tic_superior\tic_nivel\tremuestreos\theterogeneidad\ttau\texceedance\n"
        + "\n".join(
            f"B2\t{name}\t{stratum}\trol\t1\t1\t1\t0.100000\t0.100000\t0.010000\t0.200000\t0.950000\t2000\tBAJA\t0.000000\t0.000000"
            for name, stratum in (
                ("primaria_60", ""),
                ("bloque_120", ""),
                ("cota_conservadora", ""),
                ("cota_favorable", ""),
                ("mitades", "bloques_2_11"),
                ("mitades", "bloques_12_21"),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (tables / "nivel.tsv").write_text("geometria\tmedia_net_r\nB2\t0.100000\n", encoding="utf-8")
    (tables / "capacidad.tsv").write_text("comparacion\tok\tmotivos\ttasa_descarte\texit_final_c\texit_final_v\tanchura_ic95\nB2\tTrue\t\t0.010000\t0.020000\t0.030000\t0.190000\n", encoding="utf-8")
    (tables / "emparejamiento.tsv").write_text("comparacion\tclave\tvalor\nB2\tpares_finales\t1\n", encoding="utf-8")
    estimate = {
        "papel": "rol",
        "n_pares": 1,
        "n_bloques": 1,
        "min_pares_bloque": 1,
        "media_delta_r": 0.1,
        "media_agrupada_delta_r": 0.1,
        "ic_inferior": 0.01,
        "ic_superior": 0.2,
        "ic_nivel": 0.95,
        "remuestreos": 2000,
        "heterogeneidad": "BAJA",
        "tau": 0.0,
        "exceedance": 0.0,
    }
    observed = {
        "estimaciones": {
            "primaria_60": {**estimate, "media_delta_r": 0.100001},
            "bloque_120": estimate,
            "cota_conservadora": estimate,
            "cota_favorable": estimate,
            "mitades": {"bloques_2_11": estimate, "bloques_12_21": estimate},
            "nivel": {"media_net_r": 0.1},
        },
        "capacidad": {"ok": True, "motivos": [], "tasa_descarte_ambiguedad": 0.01, "exit_final_control": 0.02, "exit_final_variante": 0.03, "anchura_ic95": 0.19},
        "emparejamiento": {"pares_finales": 1},
    }
    checks = p5.compare_p4_rows("B2", observed, tables)
    assert any(not row["ok"] and row["columna"] == "media_delta_r" for row in checks)


@pytest.mark.parametrize("gid", ["B2", "S2"])
def test_compare_p4_rows_resuelve_cabeceras_reales(gid: str) -> None:
    estimate = {
        "papel": "rol",
        "n_pares": 1,
        "n_bloques": 1,
        "min_pares_bloque": 1,
        "media_delta_r": 0.1,
        "media_agrupada_delta_r": 0.1,
        "ic_inferior": 0.01,
        "ic_superior": 0.2,
        "ic_nivel": 0.95,
        "remuestreos": 2000,
        "heterogeneidad": "BAJA",
        "tau": 0.0,
        "exceedance": 0.0,
    }
    observed = {
        "estimaciones": {
            "primaria_60": estimate,
            "bloque_120": estimate,
            "cota_conservadora": estimate,
            "cota_favorable": estimate,
            "mitades": {"bloques_2_11": estimate, "bloques_12_21": estimate},
            "nivel": {"n": 1, "n_bloques": 1, "media_net_r": 0.1, "ic_inferior": 0.0, "ic_superior": 0.2, "profit_factor_agrupado": 1.1},
        },
        "capacidad": {
            "ok": True,
            "motivos": [],
            "bloques_con_pares": 1,
            "min_pares_bloque": 1,
            "tasa_descarte_ambiguedad": 0.0,
            "exit_final_control": 0.0,
            "exit_final_variante": 0.0,
            "anchura_ic95": 0.2,
        },
        "emparejamiento": {
            "senales_poblacion": 1,
            "sin_niveles": 0,
            "con_niveles": 1,
            "dropped_only_c0": 0,
            "dropped_only_variant": 0,
            "dropped_both": 0,
            "pares_finales": 1,
            "bloques_60_sin_pares": 0,
            "fraccion_pares": 1.0,
            "tasa_descarte_ambiguedad": 0.0,
            "pares_no_calculable_context": 0,
            "ambiguas_en_los_dos_brazos": 0,
            "vela_ambigua_compartida": 0,
        },
    }
    checks = p5.compare_p4_rows(gid, observed)
    assert checks
    assert not any("ausente" in str(row["esperado"]) for row in checks)


_FAKE_LEVEL_HASHES = {
    cell.gid: p5.PRE_MARKER_LEVELS_SHA256.get(cell.gid, f"h-{cell.gid}") for cell in p5.GRID if cell.role != p5.ROLE_ABSENCE
}


def _fake_preflight() -> Dict[str, Any]:
    hashes = {}
    niveles = {}
    for cell in p5.GRID:
        if cell.role == p5.ROLE_ABSENCE:
            continue
        hashes[cell.gid] = {"advisor_config_hash": "cfg"}
        if cell.role in (p5.ROLE_CONTROL, p5.ROLE_CENTER):
            hashes[cell.gid]["policy_sha256"] = f"p-{cell.gid}"
        else:
            hashes[cell.gid]["diagnostico_sha256"] = f"d-{cell.gid}"
        niveles[cell.gid] = {"levels_sha256": _FAKE_LEVEL_HASHES[cell.gid]}
    center_agg = {
        "estimaciones": {
            "mitades": {"bloques_2_11": {"media_delta_r": 0.1}, "bloques_12_21": {"media_delta_r": 0.1}},
            "bloque_120": {"media_delta_r": 0.1, "ic_inferior": 0.1},
            "cota_conservadora": {"media_delta_r": 0.1},
            "nivel": {"media_net_r": 0.1, "profit_factor_agrupado": 1.2},
        }
    }
    return {
        "ok": True,
        "definitivo": True,
        "identidad": {"p5_executor_sha": "sha-preflight"},
        "poblacion": {"p5": 0},
        "bloques": {},
        "rejilla": [cell.as_dict() for cell in p5.GRID],
        "semiplanos": p5.SEMIPLANES,
        "locro": p5.locro_denominators(),
        "recuento": p5.planned_comparisons(),
        "grid_sha256": p5.grid_sha256(),
        "hashes": hashes,
        "niveles": niveles,
        "p4_reproduccion": {
            "p4_published_results_reproduced": True,
            "checks": [],
            "B2": {"agregados": center_agg, "checks": [{"ok": True}]},
            "S2": {"agregados": center_agg, "checks": [{"ok": True}]},
            "condiciones_p4": {"B2": _p4_conditions(), "S2": _p4_conditions()},
        },
        "p4_evidencia_sha256": dict(p5.P4_EVIDENCE_SHA256),
    }


class _FakePopulation:
    def __init__(self) -> None:
        self.signals: list[Any] = []
        self.spine: list[Any] = []


def test_confirmatoria_sintetica_marca_antes_de_vecino(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_config("config.yaml")
    preflight_dir = tmp_path / "preflight"
    run_dir = tmp_path / "run"
    preflight_dir.mkdir()
    preflight = _fake_preflight()
    (preflight_dir / "p5-preflight.json").write_text(json.dumps(preflight), encoding="utf-8")
    monkeypatch.setattr(p5, "PREFLIGHT_DIR", preflight_dir)
    monkeypatch.setattr(p5, "CONFIRMATORY_OUTPUT_DIR", run_dir)
    monkeypatch.setattr(p5, "executor_unchanged_since", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(p5, "build_population", lambda *_args, **_kwargs: _FakePopulation())
    monkeypatch.setattr(p5, "_levels_for_cell", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(p5, "levels_sha256", lambda levels: _FAKE_LEVEL_HASHES[levels["gid"]])
    frozen_levels = {cell.gid: {"gid": cell.gid} for cell in p5.GRID if cell.role != p5.ROLE_ABSENCE}
    monkeypatch.setattr(p5, "_run_preflight_frozen", lambda *_args, **_kwargs: p5.P5FrozenPreflight(_FakePopulation(), frozen_levels, preflight))
    monkeypatch.setattr(p5.OutcomeGate, "evaluate_frozen", lambda *_args, **_kwargs: ({}, {}, ()))
    seen_marker = {"ok": False}

    def fake_neighbor(token: p5.ConfirmatoryToken, cell: p5.P5Cell, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        assert (run_dir / p5.RUN_MARKER).is_file()
        p5._require_token(token)
        seen_marker["ok"] = True
        return {
            "celda": cell.as_dict(),
            "estimaciones": {
                "primaria_60": _primary(),
                "bloque_120": _primary(),
                "cota_conservadora": _conservative(),
                "cota_favorable": _primary(),
                "nivel": _level(),
            },
            "capacidad": _capacity(),
            "profit_factor": 1.2,
        }

    monkeypatch.setattr(p5, "estimate_neighbor", fake_neighbor)
    monkeypatch.setattr(
        p5,
        "estimate_locro",
        lambda _token, center, region, *_args: _locro_row(center.gid, region, lower=0.1),
    )
    monkeypatch.setattr(p5, "estimate_asset_concentration", lambda *_args, **_kwargs: {"participacion": {}})
    ident = p5.P5Identity("sha-run", False, True, p5.EXPECTED_CONFIG_HASH, "1.0")
    code, text = p5.run_confirmatory(config, None, None, ident, run_dir)  # type: ignore[arg-type]
    assert code == 0, text
    assert seen_marker["ok"] is True
    result = json.loads((run_dir / "p5-resultado.json").read_text(encoding="utf-8"))
    assert result["recuento_derivado"] == 71
    assert (run_dir / "tablas" / "criterio.tsv").is_file()


def test_confirmatoria_rechaza_segunda_ejecucion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / p5.RUN_MARKER).write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(p5, "CONFIRMATORY_OUTPUT_DIR", run_dir)
    ident = p5.P5Identity("sha", False, True, p5.EXPECTED_CONFIG_HASH, "1.0")
    with pytest.raises(p5.P5AlreadyExecutedError):
        p5.run_confirmatory(load_config("config.yaml"), None, None, ident, run_dir)  # type: ignore[arg-type]


def test_confirmatoria_rechaza_run_previo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "otro.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(p5, "CONFIRMATORY_OUTPUT_DIR", run_dir)
    ident = p5.P5Identity("sha", False, True, p5.EXPECTED_CONFIG_HASH, "1.0")
    with pytest.raises(p5.P5AlreadyExecutedError):
        p5.run_confirmatory(load_config("config.yaml"), None, None, ident, run_dir)  # type: ignore[arg-type]


def test_confirmatoria_rechaza_executor_cambiado(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    preflight_dir = tmp_path / "preflight"
    run_dir = tmp_path / "run"
    preflight_dir.mkdir()
    preflight = _fake_preflight()
    (preflight_dir / "p5-preflight.json").write_text(json.dumps(preflight), encoding="utf-8")
    monkeypatch.setattr(p5, "PREFLIGHT_DIR", preflight_dir)
    monkeypatch.setattr(p5, "CONFIRMATORY_OUTPUT_DIR", run_dir)
    monkeypatch.setattr(p5, "executor_unchanged_since", lambda *_args, **_kwargs: False)
    ident = p5.P5Identity("sha", False, True, p5.EXPECTED_CONFIG_HASH, "1.0")
    with pytest.raises(p5.P5PreflightError):
        p5.run_confirmatory(load_config("config.yaml"), None, None, ident, run_dir)  # type: ignore[arg-type]


@pytest.mark.parametrize("cell", [cell for cell in p5.GRID if cell.role != p5.ROLE_ABSENCE], ids=lambda cell: cell.gid)
def test_publicacion_hash_por_rol_parametrizada(cell: p5.P5Cell) -> None:
    published = p5.published_cell_hash(load_config("config.yaml"), cell)
    if cell.role in (p5.ROLE_CONTROL, p5.ROLE_CENTER):
        assert "policy_sha256" in published
        assert "diagnostico_sha256" not in published
    else:
        assert "diagnostico_sha256" in published
        assert "policy_sha256" not in published


@pytest.mark.parametrize(
    ("primary", "conservative", "level", "capacity", "pf", "expected"),
    [
        (_primary(0.1, 0.01), _conservative(0.1), _level(0.1), _capacity(True), 1.1, p5.ACEPTABLE),
        (_primary(0.1, 0.0), _conservative(0.1), _level(0.1), _capacity(True), 1.1, p5.DÉBIL),
        (_primary(0.1, 0.01), _conservative(0.0), _level(0.1), _capacity(True), 1.1, p5.DÉBIL),
        (_primary(0.1, 0.01), _conservative(0.1), _level(0.0), _capacity(True), 1.1, p5.DÉBIL),
        (_primary(0.1, 0.01), _conservative(0.1), _level(0.1), _capacity(True), 1.0, p5.DÉBIL),
        (_primary(-0.1, -0.2), _conservative(0.1), _level(0.1), _capacity(True), 1.1, p5.CONTRARIA),
        (_primary(0.1, 0.01), _conservative(0.1), _level(0.1), _capacity(False), 1.1, p5.NO_ESTIMABLE),
    ],
)
def test_clasificacion_parametrizada(
    primary: Dict[str, float],
    conservative: Dict[str, float],
    level: Dict[str, float],
    capacity: Dict[str, Any],
    pf: float,
    expected: str,
) -> None:
    assert p5.classify_cell(primary, conservative, level, capacity, pf) == expected


@pytest.mark.parametrize("condition", ["F1", "F2", "F3", "F4", "F5", "F6"])
def test_condiciones_f1_f6_parametrizadas(condition: str) -> None:
    classes = _classes()
    center = _center()
    if condition == "F1":
        classes[p5.neighbors("B2")[0].gid] = p5.CONTRARIA
    elif condition == "F2":
        for gid in p5.SEMIPLANES["B2"]["s_minus"]:
            classes[gid] = p5.DÉBIL
    elif condition == "F3":
        for gid in p5.SEMIPLANES["B2"]["m2_minus"]:
            classes[gid] = p5.DÉBIL
    elif condition == "F4":
        for cell in p5.neighbors("B2")[:3]:
            classes[cell.gid] = p5.DÉBIL
    elif condition == "F5":
        center = _center(first_half_mean=0.0)
    elif condition == "F6":
        center = _center(level_mean=0.0)
    verdict = p5.evaluate_candidate(center, classes, _locro())
    assert verdict["condiciones"][condition] is True
    assert verdict["etiqueta"] == p5.FRÁGIL


@pytest.mark.parametrize(
    ("verdicts", "expected"),
    [
        ({"B2": {"sobrevive": False}, "S2": {"sobrevive": False}}, ()),
        ({"B2": {"sobrevive": True}, "S2": {"sobrevive": False}}, ("B2",)),
        ({"B2": {"sobrevive": False}, "S2": {"sobrevive": True}}, ("S2",)),
        ({"B2": {"sobrevive": True}, "S2": {"sobrevive": True}}, ("B2", "S2")),
    ],
)
def test_survivors_parametrizado(verdicts: Dict[str, Dict[str, bool]], expected: tuple[str, ...]) -> None:
    assert p5.survivors(verdicts) == expected


def test_vecino_publica_sus_cinco_ic_y_mitades_solo_como_puntos() -> None:
    estimate = {
        "n_pares": 10, "n_bloques": 12, "media_delta_r": 0.02, "ic_inferior": 0.01, "ic_superior": 0.03,
        "ic_nivel": 0.95, "remuestreos": 2000,
    }
    observed = {
        "celda": {"centro": "B2"},
        "deltas": ["no se publica"],
        "estimaciones": {
            "primaria_60": dict(estimate),
            "bloque_120": dict(estimate),
            "cota_conservadora": dict(estimate),
            "cota_favorable": dict(estimate),
            "nivel": {"n": 10, "n_bloques": 12, "media_net_r": 0.1, "ic_inferior": 0.05, "ic_superior": 0.2,
                      "profit_factor_agrupado": 1.2},
            "mitades": {"bloques_2_11": dict(estimate), "bloques_12_21": dict(estimate)},
        },
    }
    view = p5._neighbor_publication_view(observed)
    assert "deltas" not in view
    for key in ("primaria_60", "bloque_120", "cota_conservadora", "cota_favorable", "nivel"):
        assert view["estimaciones"][key]["ic_inferior"] is not None
        assert view["estimaciones"][key]["ic_superior"] is not None
    for half in view["estimaciones"]["mitades"].values():
        assert not any(column.startswith("ic_") for column in half)
        assert half["media_delta_r"] == 0.02


def test_reproduccion_compara_solo_las_columnas_de_la_lista_blanca() -> None:
    # OD-P5-16 / D-66: n_pares, n_bloques, min_pares_bloque, medias, IC, nivel y remuestreos.
    # `papel` (texto) y la heterogeneidad (`heterogeneidad`, `tau`, `exceedance`) no se comparan.
    assert p5.P4_ESTIMATE_WHITELIST_COLUMNS == (
        "n_pares", "n_bloques", "min_pares_bloque", "media_delta_r", "media_agrupada_delta_r",
        "ic_inferior", "ic_superior", "ic_nivel", "remuestreos",
    )
    assert not hasattr(p5, "P4_ESTIMATE_COLUMNS")


def test_mitades_negativas_de_vecino_no_cambian_su_clase() -> None:
    observed = {
        "estimaciones": {
            "primaria_60": _primary(0.1, 0.01),
            "cota_conservadora": _conservative(0.1),
            "nivel": _level(0.1),
            "mitades": {
                "bloques_2_11": {"media_delta_r": -1.0},
                "bloques_12_21": {"media_delta_r": -1.0},
            },
        },
        "capacidad": _capacity(True),
        "profit_factor": 1.2,
    }
    assert p5._classify_neighbor(observed) == p5.ACEPTABLE


def test_poblacion_real_recuentos_hashes_y_regiones(real_p5_reproduction: Dict[str, Any]) -> None:
    population = real_p5_reproduction["population"]
    assert len(population.signals) == 101_251
    assert len({signal.asset for signal in population.signals}) == 90
    assert population.population_sha256 == p5.P5_POPULATION_SHA256
    assert population.signal_ids_sha256 == p5.P5_SIGNAL_IDS_SHA256
    assert population.regions == {
        "ASIA": 17_953,
        "EMERGING_MARKETS": 1_151,
        "EUROPA": 34_622,
        "GLOBAL": 2_627,
        "USA": 44_898,
    }


def test_reproduccion_real_cadenas_b2_s2_y_c0(real_p5_reproduction: Dict[str, Any]) -> None:
    reproduction = real_p5_reproduction["reproduction"]
    assert all(row["ok"] for row in reproduction["B2"]["checks"])
    assert all(row["ok"] for row in reproduction["S2"]["checks"])
    assert reproduction["C0"]["advisor_config_hash_ok"] is True
    assert reproduction["C0"]["niveles_event_study_diferencias"] == 0
    assert reproduction["C0"]["sin_niveles"] == 0
    assert set(real_p5_reproduction["calls"]) == {"C0", "B2", "S2"}
    assert real_p5_reproduction["calls"].count("C0") == 1
    assert real_p5_reproduction["calls"].count("B2") == 1
    assert real_p5_reproduction["calls"].count("S2") == 1


def test_reproduccion_real_primaria_y_capacidad_publicadas(real_p5_reproduction: Dict[str, Any]) -> None:
    primary = real_p5_reproduction["reproduction"]["B2"]["agregados"]["estimaciones"]["primaria_60"]
    assert primary["ic_nivel"] == 0.9875
    assert primary["remuestreos"] == 20000
    capacity = real_p5_reproduction["reproduction"]["B2"]["agregados"]["capacidad"]
    assert "anchura_ic95" in capacity
    assert "ic_inferior" not in capacity
    assert "ic_superior" not in capacity


# ---------------------------------------------------------------------------
# Regresión de la revisión de look-ahead (I-1, I-2, M-1 a M-6).
# ---------------------------------------------------------------------------


def _s2_center() -> p5.CenterEvidence:
    return replace(_center(), center_id="S2")


@pytest.mark.parametrize("gid", [cell.gid for cell in p5.neighbors("B2")])
def test_omitir_cualquier_vecino_b2_es_error(gid: str) -> None:
    classes = _classes("B2")
    classes.pop(gid)
    with pytest.raises(ValueError, match="faltan"):
        p5.evaluate_candidate(_center(), classes, _locro())


@pytest.mark.parametrize("gid", ["S2_s2p25_m23p375", "S2_s2p75_m24p125"])
def test_omitir_vecino_critico_s2_es_error(gid: str) -> None:
    classes = _classes("S2")
    assert gid in classes
    classes.pop(gid)
    with pytest.raises(ValueError, match="faltan"):
        p5.evaluate_candidate(_s2_center(), classes, _locro(center="S2"))


def test_mapas_de_vecinos_incompletos_o_ajenos_son_error() -> None:
    first = p5.neighbors("B2")[0].gid
    contrary_omitted = _classes("B2")
    contrary_omitted.pop(first)
    cases = [
        {},
        {first: p5.ACEPTABLE},
        contrary_omitted,
        {**_classes("B2"), p5.neighbors("S2")[0].gid: p5.ACEPTABLE},
        {**_classes("B2"), "B2": p5.ACEPTABLE},
    ]
    for classes in cases:
        with pytest.raises(ValueError):
            p5.evaluate_candidate(_center(), classes, _locro())


@pytest.mark.parametrize("klass", ["XYZ", None, "", "aceptable", p5.AUSENCIA_ESTRUCTURAL])
def test_clase_de_vecino_desconocida_es_error(klass: Any) -> None:
    classes: Dict[str, Any] = _classes("B2")
    classes[p5.neighbors("B2")[0].gid] = klass
    with pytest.raises(ValueError, match="desconocidas"):
        p5.evaluate_candidate(_center(), classes, _locro())


@pytest.mark.parametrize("region", p5.CORE_REGIONS)
def test_falta_una_region_locro_es_error(region: str) -> None:
    locro = _locro()
    locro.pop(region)
    with pytest.raises(ValueError, match="LOCRO"):
        p5.evaluate_candidate(_center(), _classes(), locro)


def test_locro_vacio_extra_o_de_otro_centro_es_error() -> None:
    extra = _locro()
    extra["GLOBAL"] = _locro_row("B2", "USA")
    other_center = _locro(center="S2")
    wrong_region = _locro()
    wrong_region["USA"] = _locro_row("B2", "EUROPA")
    wrong_denominator = _locro()
    wrong_denominator["ASIA"] = {**_locro_row("B2", "ASIA"), "denominador": 91_126}
    wrong_minimum = _locro()
    wrong_minimum["ASIA"] = {**_locro_row("B2", "ASIA"), "pares_minimos": 91_126}
    for locro in ({}, extra, other_center, wrong_region, wrong_denominator, wrong_minimum):
        with pytest.raises(ValueError):
            p5.evaluate_candidate(_center(), _classes(), locro)


def test_locro_sin_atajo_estimable_capacidad_manda() -> None:
    locro = _locro()
    locro["USA"] = {**_locro_row("B2", "USA", ok=False, lower=0.5), "estimable": True, "ic_inferior": 0.5}
    verdict = p5.evaluate_candidate(_center(), _classes(), locro)
    assert verdict["etiqueta"] == p5.NO_CONCLUYENTE and verdict["sobrevive"] is False
    assert p5.locro_row(locro["USA"]).estimable is False
    with pytest.raises(ValueError):
        p5.locro_row({"estimable": True, "ic_inferior": 0.5})


@pytest.mark.parametrize("lower", [math.nan, math.inf, True, None, "0.1"])
def test_locro_estimable_exige_ic_inferior_finito(lower: Any) -> None:
    locro = _locro()
    locro["EUROPA"] = {**_locro_row("B2", "EUROPA"), "estimacion": {"ic_inferior": lower}}
    with pytest.raises(ValueError):
        p5.evaluate_candidate(_center(), _classes(), locro)


def test_condiciones_p4_parciales_o_inventadas_son_error() -> None:
    full = _p4_conditions()
    seven = dict(full)
    seven.pop("P4_10")
    nine = {**full, "P4_11": True}
    for conditions in ({}, {"P4_1": True}, seven, nine, {**full, "P4_4": True}, {**full, "P4_1": 1}):
        with pytest.raises(ValueError, match="condiciones P4"):
            p5.evaluate_candidate(_center(p4_conditions=conditions), _classes(), _locro())


@pytest.mark.parametrize("key", sorted(p5.EXPECTED_P4_VETO_CONDITIONS))
def test_una_condicion_p4_falsa_veta_como_fragil(key: str) -> None:
    verdict = p5.evaluate_candidate(_center(p4_conditions=_p4_conditions(**{key: False})), _classes(), _locro())
    assert verdict["condiciones"]["centro_p4"] is False and verdict["etiqueta"] == p5.FRÁGIL


def test_criterio_p4_real_da_las_ocho_condiciones_cumplidas() -> None:
    for gid in ("B2", "S2"):
        assert p5._p4_veto_conditions(gid) == _p4_conditions()


def _criterio_copy(tmp_path: Path, mutate: Any) -> Path:
    tables = tmp_path / "tablas"
    tables.mkdir()
    lines = (p5.P4_RUN_TABLES / "criterio.tsv").read_text(encoding="utf-8").splitlines()
    (tables / "criterio.tsv").write_text("\n".join(mutate(lines)) + "\n", encoding="utf-8")
    return tables


def _mutate_row(lines: list[str], geometry: str, condition: str, column: int, value: str) -> list[str]:
    out = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) > column and parts[0] == geometry and parts[1] == condition:
            parts[column] = value
        out.append("\t".join(parts))
    return out


@pytest.mark.parametrize(
    "mutate",
    [
        lambda lines: [line for line in lines if not line.startswith("B2\t9\t")],
        lambda lines: [*lines, next(line for line in lines if line.startswith("B2\t3\t"))],
        lambda lines: _mutate_row(lines, "B2", "5", 3, "False"),
        lambda lines: _mutate_row(lines, "B2", "4", 3, "True"),
        lambda lines: _mutate_row(lines, "B2", "7", 4, "True"),
        lambda lines: _mutate_row(lines, "B2", "2", 4, "N/D"),
    ],
    ids=["falta", "duplicada", "veta_cambiada", "descriptiva_veta", "descriptiva_cumple", "veto_sin_valor"],
)
def test_criterio_p4_alterado_es_error(tmp_path: Path, mutate: Any) -> None:
    tables = _criterio_copy(tmp_path, mutate)
    with pytest.raises(p5.P5PreflightError):
        p5._p4_veto_conditions("B2", tables)


def test_evidencia_p4_real_coincide_con_los_hashes_fijados() -> None:
    assert p5.p4_evidence_sha256() == p5.P4_EVIDENCE_SHA256
    assert {Path(key).name for key in p5.P4_EVIDENCE_SHA256} >= {
        "criterio.tsv", "estimaciones.tsv", "nivel.tsv", "capacidad.tsv", "emparejamiento.tsv",
    }


def test_evidencia_p4_modificada_no_se_lee(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key = "evidence/2026-10-01-T-020-p4/run/tablas/criterio.tsv"
    copy = tmp_path / "criterio.tsv"
    copy.write_bytes(Path(key).read_bytes() + b"\n")
    monkeypatch.setitem(p5.P4_EVIDENCE_SHA256, str(copy), p5.P4_EVIDENCE_SHA256[key])
    with pytest.raises(p5.P5PreflightError, match="sha256"):
        p5.read_evidence_text(copy)
    with pytest.raises(p5.P5PreflightError):
        p5._p4_veto_conditions("B2", tmp_path)


def test_center_evidence_usa_condiciones_congeladas_sin_leer_criterio(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("criterio.tsv no se lee tras la marca")

    monkeypatch.setattr(p5, "_p4_veto_conditions", forbidden)
    monkeypatch.setattr(p5, "_read_tsv", forbidden)
    repro = _fake_preflight()["p4_reproduccion"]
    repro["condiciones_p4"]["B2"] = _p4_conditions(P4_3=False)
    evidence = p5._center_evidence("B2", repro)
    assert evidence.p4_conditions == _p4_conditions(P4_3=False)


def test_huella_y_marca_incluyen_condiciones_y_evidencia_p4() -> None:
    preflight = _fake_preflight()
    fingerprint = p5.preflight_fingerprint(preflight)
    assert fingerprint["p4_reproduccion"]["condiciones_p4"] == preflight["p4_reproduccion"]["condiciones_p4"]
    assert fingerprint["p4_evidencia_sha256"] == p5.P4_EVIDENCE_SHA256
    changed = _fake_preflight()
    changed["p4_reproduccion"]["condiciones_p4"]["S2"] = _p4_conditions(P4_8=False)
    assert p5._normalized(p5.preflight_fingerprint(changed)) != p5._normalized(fingerprint)
    ident = p5.P5Identity("sha", False, True, p5.EXPECTED_CONFIG_HASH, "1.0")
    payload = p5.marker_payload("t", ident, "sha", preflight)
    assert payload["condiciones_p4"] == preflight["p4_reproduccion"]["condiciones_p4"]
    assert payload["p4_evidencia_sha256"] == p5.P4_EVIDENCE_SHA256
    assert payload["levels_sha256"] == _FAKE_LEVEL_HASHES


class _NoEvaluation:
    def __init__(self) -> None:
        self.signals: list[Any] = []


def _levels_hash_by_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(p5, "levels_sha256", lambda levels: _FAKE_LEVEL_HASHES.get(levels.get("gid"), "otro"))
    monkeypatch.setattr(p5, "p4_evaluate_frozen", lambda *_args: ({}, {}, ()))


@pytest.mark.parametrize(
    ("cell", "levels_of"),
    [
        (p5.B2_CELL, p5.neighbors("B2")[0].gid),
        (p5.S2_CELL, p5.neighbors("S2")[-1].gid),
        (p5.C0_CELL, "B2"),
        (p5.B2_CELL, "S2"),
        (p5.S2_CELL, "C0"),
    ],
)
def test_guarda_rechaza_niveles_ajenos(monkeypatch: pytest.MonkeyPatch, cell: p5.P5Cell, levels_of: str) -> None:
    _levels_hash_by_marker(monkeypatch)
    gate = p5.OutcomeGate()
    gate.evaluate_frozen(_NoEvaluation(), None, cell, {"gid": cell.gid})  # type: ignore[arg-type]
    with pytest.raises(p5.P5OutcomeGateError, match="niveles"):
        gate.evaluate_frozen(_NoEvaluation(), None, cell, {"gid": levels_of})  # type: ignore[arg-type]


def test_guarda_rechaza_niveles_reales_alterados_en_una_senal() -> None:
    from advisor.analysis.levels import Levels

    level = Levels(
        price=100.0, entry_ideal_low=99.0, entry_ideal_high=100.0, entry_max=101.0, stop=96.0,
        invalidation_level=None, invalidation_reason="", stop_basis="VOL", target1=103.0, target2=106.0,
        target3=110.0, risk_pp=4.0, reward_pct=6.0, rr_ratio=1.5, extension_atr=0.0, chase=False,
        entry_max_tecnica=101.0, entry_max_rr=101.0,
    )
    levels = {"a": level, "b": level}
    gate = p5.OutcomeGate(expected_levels_sha256={**p5.PRE_MARKER_LEVELS_SHA256, "B2_s2p00_m24p500": p5.levels_sha256(levels)})
    gate.require_levels_of(p5.CELLS_BY_ID["B2_s2p00_m24p500"], levels)
    altered = {"a": level, "b": replace(level, stop=95.99)}
    with pytest.raises(p5.P5OutcomeGateError):
        gate.require_levels_of(p5.CELLS_BY_ID["B2_s2p00_m24p500"], altered)


def test_guarda_rechaza_celdas_disfrazadas(monkeypatch: pytest.MonkeyPatch) -> None:
    _levels_hash_by_marker(monkeypatch)
    neighbor = p5.neighbors("B2")[0]
    disguised = [
        p5.P5Cell("B2", "B2", neighbor.atr_stop_multiple, neighbor.target_atr_multiples, p5.ROLE_CENTER),
        p5.P5Cell(neighbor.gid, "B2", p5.B2_CELL.atr_stop_multiple, p5.B2_CELL.target_atr_multiples, p5.ROLE_CENTER),
        replace(p5.B2_CELL, role=p5.ROLE_NEIGHBOR),
        p5.P5Cell("INVENTADA", "B2", 2.0, (1.5, 4.875, 5.0), p5.ROLE_CENTER),
    ]
    gate = p5.OutcomeGate()
    for cell in disguised:
        with pytest.raises(p5.P5OutcomeGateError):
            gate.evaluate_frozen(_NoEvaluation(), None, cell, {"gid": "B2"})  # type: ignore[arg-type]


def test_guarda_tras_marca_exige_los_hashes_de_p4_para_c0_b2_s2() -> None:
    with pytest.raises(p5.P5OutcomeGateError):
        p5.OutcomeGate(marker_exists=True, phase="confirmatoria", expected_levels_sha256={**_FAKE_LEVEL_HASHES, "B2": "x"})


def test_hash_publicado_rechaza_celdas_no_canonicas() -> None:
    config = load_config("config.yaml")
    neighbor = p5.neighbors("B2")[0]
    cases = [
        replace(neighbor, role=p5.ROLE_CENTER),
        replace(p5.B2_CELL, role=p5.ROLE_NEIGHBOR),
        replace(neighbor, gid="B2"),
        p5.P5Cell("INVENTADA", "B2", 2.0, (1.5, 4.875, 5.0), p5.ROLE_CENTER),
    ]
    for cell in cases:
        with pytest.raises(ValueError):
            p5.published_cell_hash(config, cell)
    with pytest.raises(ValueError):
        p5.policy_sha256(config, neighbor)
    with pytest.raises(ValueError):
        p5.diagnostico_sha256(config, p5.B2_CELL)
    assert "policy_sha256" in p5.published_cell_hash(config, p5.S2_CELL)
    absence = p5.absences("S2")[0]
    assert set(p5.published_cell_hash(config, absence)) == {"procedencia", "advisor_config_hash"}


def test_estimate_neighbor_sin_guarda_de_la_marca_es_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    marker = run_dir / p5.RUN_MARKER
    marker.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(p5, "CONFIRMATORY_OUTPUT_DIR", run_dir)
    token = p5.build_confirmatory_token(marker, {})
    with pytest.raises(p5.P5OutcomeGateError, match="guarda"):
        p5.estimate_neighbor(token, p5.neighbors("B2")[0], None, None, {}, {}, None, None, {})  # type: ignore[arg-type]


def test_marca_exclusiva_solo_una_gana(tmp_path: Path) -> None:
    marker = tmp_path / p5.RUN_MARKER
    fd = p5.create_marker_exclusive(marker)
    import os

    os.close(fd)
    with pytest.raises(p5.P5AlreadyExecutedError):
        p5.create_marker_exclusive(marker)


def _synthetic_confirmatory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    neighbor: Any = None,
) -> tuple[Path, Any, p5.P5Identity, Dict[str, int]]:
    preflight_dir = tmp_path / "preflight"
    run_dir = tmp_path / "run"
    preflight_dir.mkdir()
    preflight = _fake_preflight()
    (preflight_dir / "p5-preflight.json").write_text(json.dumps(preflight), encoding="utf-8")
    monkeypatch.setattr(p5, "PREFLIGHT_DIR", preflight_dir)
    monkeypatch.setattr(p5, "CONFIRMATORY_OUTPUT_DIR", run_dir)
    monkeypatch.setattr(p5, "executor_unchanged_since", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(p5, "levels_sha256", lambda levels: _FAKE_LEVEL_HASHES[levels["gid"]])
    frozen_levels = {cell.gid: {"gid": cell.gid} for cell in p5.GRID if cell.role != p5.ROLE_ABSENCE}
    monkeypatch.setattr(
        p5, "_run_preflight_frozen", lambda *_args, **_kwargs: p5.P5FrozenPreflight(_FakePopulation(), frozen_levels, preflight)
    )
    monkeypatch.setattr(p5, "p4_evaluate_frozen", lambda *_args: ({}, {}, ()))
    calls = {"vecinos": 0}

    def default_neighbor(cell: p5.P5Cell) -> Dict[str, Any]:
        return {
            "celda": cell.as_dict(),
            "estimaciones": {
                "primaria_60": _primary(),
                "bloque_120": _primary(),
                "cota_conservadora": _conservative(),
                "cota_favorable": _primary(),
                "nivel": _level(),
            },
            "capacidad": _capacity(),
            "profit_factor": 1.2,
        }

    def fake_neighbor(token: p5.ConfirmatoryToken, cell: p5.P5Cell, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        p5._require_token(token)
        calls["vecinos"] += 1
        return (neighbor or default_neighbor)(cell)

    monkeypatch.setattr(p5, "estimate_neighbor", fake_neighbor)
    monkeypatch.setattr(p5, "estimate_locro", lambda _token, center, region, *_args: _locro_row(center.gid, region, lower=0.1))
    monkeypatch.setattr(p5, "estimate_asset_concentration", lambda *_args, **_kwargs: {"participacion": {}})
    monkeypatch.setattr(p5, "pair_populations", lambda *_args: type("P", (), {"deltas": []})())
    ident = p5.P5Identity("sha-run", False, True, p5.EXPECTED_CONFIG_HASH, "1.0")
    return run_dir, load_config("config.yaml"), ident, calls


def test_confirmatoria_completa_con_guarda_real(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir, config, ident, calls = _synthetic_confirmatory(tmp_path, monkeypatch)
    code, text = p5.run_confirmatory(config, None, None, ident, run_dir)  # type: ignore[arg-type]
    assert code == 0, text
    assert calls["vecinos"] == 13
    marker = json.loads((run_dir / p5.RUN_MARKER).read_text(encoding="utf-8"))
    assert marker["condiciones_p4"]["B2"] == _p4_conditions()
    assert marker["p4_evidencia_sha256"] == p5.P4_EVIDENCE_SHA256
    assert json.loads((run_dir / "p5-resultado.json").read_text(encoding="utf-8"))["recuento_derivado"] == 71


def test_caso_a_no_estimable_con_pares_conserva_71(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = p5.neighbors("B2")[0].gid

    def neighbor(cell: p5.P5Cell) -> Dict[str, Any]:
        return {
            "celda": cell.as_dict(),
            "estimaciones": {
                "primaria_60": _primary(),
                "bloque_120": _primary(),
                "cota_conservadora": _conservative(),
                "cota_favorable": _primary(),
                "nivel": _level(),
            },
            "capacidad": _capacity(cell.gid != target),
            "profit_factor": 1.2,
        }

    run_dir, config, ident, _calls = _synthetic_confirmatory(tmp_path, monkeypatch, neighbor)
    code, text = p5.run_confirmatory(config, None, None, ident, run_dir)  # type: ignore[arg-type]
    assert code == 0, text
    result = json.loads((run_dir / "p5-resultado.json").read_text(encoding="utf-8"))
    assert result["clases"]["B2"][target] == p5.NO_ESTIMABLE
    assert result["recuento_derivado"] == 71
    assert not (run_dir / "p5-parada.json").exists()


def test_celda_sin_pares_para_con_marca_y_sin_resultado(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = p5.neighbors("S2")[0].gid

    def neighbor(cell: p5.P5Cell) -> Dict[str, Any]:
        estimates: Dict[str, Any] = {"nivel": _level()}
        if cell.gid != target:
            estimates.update(primaria_60=_primary(), bloque_120=_primary(), cota_conservadora=_conservative(), cota_favorable=_primary())
        return {"celda": cell.as_dict(), "estimaciones": estimates, "capacidad": _capacity(cell.gid != target), "profit_factor": 1.2}

    run_dir, config, ident, _calls = _synthetic_confirmatory(tmp_path, monkeypatch, neighbor)
    code, text = p5.run_confirmatory(config, None, None, ident, run_dir)  # type: ignore[arg-type]
    assert code == 2 and "recuento derivado" in text
    assert (run_dir / p5.RUN_MARKER).is_file() and (run_dir / "p5-parada.json").is_file()
    assert not (run_dir / "p5-resultado.json").exists()


def test_fallo_del_token_tras_la_marca_deja_parada(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir, config, ident, calls = _synthetic_confirmatory(tmp_path, monkeypatch)

    def broken(*_args: Any) -> p5.ConfirmatoryToken:
        raise p5.P5OutcomeGateError("token roto")

    monkeypatch.setattr(p5, "build_confirmatory_token", broken)
    code, text = p5.run_confirmatory(config, None, None, ident, run_dir)  # type: ignore[arg-type]
    assert code == 2 and "token roto" in text
    assert (run_dir / p5.RUN_MARKER).is_file()
    assert json.loads((run_dir / "p5-parada.json").read_text(encoding="utf-8"))["parada"] == "P5OutcomeGateError"
    assert calls["vecinos"] == 0
    with pytest.raises(p5.P5AlreadyExecutedError):
        p5.run_confirmatory(config, None, None, ident, run_dir)  # type: ignore[arg-type]


def test_interrupcion_tras_la_marca_deja_parada_y_se_relanza(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupt(cell: p5.P5Cell) -> Dict[str, Any]:
        raise KeyboardInterrupt

    run_dir, config, ident, _calls = _synthetic_confirmatory(tmp_path, monkeypatch, interrupt)
    with pytest.raises(KeyboardInterrupt):
        p5.run_confirmatory(config, None, None, ident, run_dir)  # type: ignore[arg-type]
    assert (run_dir / p5.RUN_MARKER).is_file() and (run_dir / "p5-parada.json").is_file()


def test_marca_creada_por_otra_ejecucion_durante_el_preflight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir, config, ident, calls = _synthetic_confirmatory(tmp_path, monkeypatch)
    frozen = p5._run_preflight_frozen(config, None, None, ident)  # type: ignore[arg-type]

    def racing_preflight(*_args: Any, **_kwargs: Any) -> p5.P5FrozenPreflight:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / p5.RUN_MARKER).write_text("OTRA EJECUCION\n", encoding="utf-8")
        return frozen

    monkeypatch.setattr(p5, "_run_preflight_frozen", racing_preflight)
    with pytest.raises(p5.P5AlreadyExecutedError):
        p5.run_confirmatory(config, None, None, ident, run_dir)  # type: ignore[arg-type]
    assert (run_dir / p5.RUN_MARKER).read_text(encoding="utf-8") == "OTRA EJECUCION\n"
    assert not (run_dir / "p5-parada.json").exists()
    assert calls["vecinos"] == 0


def test_dos_ejecuciones_concurrentes_solo_una_abre_desenlaces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir, config, ident, calls = _synthetic_confirmatory(tmp_path, monkeypatch)
    real_create = p5.create_marker_exclusive
    run_dir.mkdir(parents=True)

    def create_then_rival(marker: Path) -> int:
        fd = real_create(marker)
        with pytest.raises(p5.P5AlreadyExecutedError):
            real_create(marker)
        return fd

    monkeypatch.setattr(p5, "create_marker_exclusive", create_then_rival)
    code, text = p5.run_confirmatory(config, None, None, ident, run_dir)  # type: ignore[arg-type]
    assert code == 0, text
    assert calls["vecinos"] == 13
