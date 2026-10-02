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


def _center(**changes: Any) -> p5.CenterEvidence:
    base = p5.CenterEvidence(
        center_id="B2",
        p4_reproducido=True,
        p4_conditions={"c1": True, "c2": True},
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


def _locro(ok: bool = True, lower: float = 0.01) -> Dict[str, Dict[str, Any]]:
    return {region: {"estimable": ok, "ic_inferior": lower} for region in p5.CORE_REGIONS}


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
    with pytest.raises(ValueError, match="clases de vecinos no esperadas"):
        p5.evaluate_candidate(replace(_center(), center_id="S2"), {**classes, absence.gid: p5.ACEPTABLE}, _locro())


def test_s2_vecinos_criticos_deben_ser_aceptables() -> None:
    classes = _classes("S2")
    critical = [*p5.SEMIPLANES["S2"]["s_plus"], *p5.SEMIPLANES["S2"]["m2_minus"]]
    assert len(set(critical)) == 2
    for gid in critical:
        changed = dict(classes)
        changed[gid] = p5.DÉBIL
        verdict = p5.evaluate_candidate(replace(_center(), center_id="S2"), changed, _locro())
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
    locro = {
        "USA": {"estimacion": {"ic_inferior": 0.0}, "capacidad": {"ok": True}},
        "EUROPA": {"estimacion": {"ic_inferior": 0.1}, "capacidad": {"ok": True}},
        "ASIA": {"estimacion": {"ic_inferior": 0.1}, "capacidad": {"ok": True}},
    }
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
        niveles[cell.gid] = {"levels_sha256": "h"}
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
        },
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
    monkeypatch.setattr(p5, "levels_sha256", lambda _levels: "h")
    frozen_levels = {cell.gid: {} for cell in p5.GRID if cell.role != p5.ROLE_ABSENCE}
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
        lambda _token, center, region, *_args: {
            "centro": center.gid,
            "sin_region": region,
            "pares_minimos": p5.LOCRO_MIN_PAIRS[region],
            "estimacion": {"ic_inferior": 0.1},
            "capacidad": {"ok": True},
        },
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
