"""Tests pre-registrados del ejecutor de P3 (T-019 paso 3).

Todos usan datos sintéticos o desenlaces fabricados: ninguno lee desenlaces de
la cosecha real. El único test sobre la cosecha reproduce la población sin
desenlaces (preflight).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

import advisor.research.p3 as p3
from advisor.research.bootstrap import DEFAULT_RESAMPLES, DEFAULT_SEED, bootstrap_block_mean_interval
from advisor.research.capacity import DEFAULT_THRESHOLDS, PrimaryEstimatorRow
from advisor.research.observations import DimensionObservation


def _record(
    score: float,
    net_r: Optional[float],
    *,
    block: int = 0,
    asset: str = "AAA",
    region: str = "USA",
    status: str = "TARGET_FIRST",
    ablated: Optional[Dict[str, float]] = None,
) -> p3.P3Record:
    return p3.P3Record(
        asset=asset,
        region=region,
        block=block,
        score=score,
        net_r=net_r,
        exit_status=status,
        mae_r=0.3,
        mfe_unbounded_lower_r=1.0,
        mfe_unbounded_upper_r=1.5,
        ablated_scores=ablated or dict.fromkeys(p3.ABLATED_DIMENSIONS, score),
    )


# --- percentiles --------------------------------------------------------------


def test_percentil_nearest_rank_exacto() -> None:
    values = [float(v) for v in range(1, 11)]
    assert p3.nearest_rank_cut(values, 20) == 2.0
    assert p3.nearest_rank_cut(values, 25) == 3.0
    assert p3.nearest_rank_cut(values, 60) == 6.0
    hundred = [float(v) for v in range(1, 101)]
    # 0,07·100 en coma flotante es 7,000000000000001 y ceil daría 8: el índice
    # se calcula en aritmética entera y da x[6] = 7.
    assert p3.nearest_rank_index(7, 100) == 6
    assert p3.nearest_rank_cut(hundred, 7) == 7.0


def test_quintil_empate_sube_de_banda() -> None:
    cuts = (10.0, 20.0, 30.0, 40.0)
    assert p3.quintile_of(9.99, cuts) == "Q1"
    assert p3.quintile_of(10.0, cuts) == "Q2"
    assert p3.quintile_of(40.0, cuts) == "Q5"
    assert p3.quintile_of(100.0, cuts) == "Q5"


def test_quintiles_con_cortes_iguales() -> None:
    scores = [10.0] * 50 + [float(v) for v in range(11, 61)]
    cuts = p3.quintile_cuts(scores)
    assert cuts.values[0] == cuts.values[1] == 10.0
    assert cuts.resolution_insufficient
    assert cuts.status == p3.SCORE_RESOLUTION_INSUFFICIENT
    assert cuts.tied_pairs == ((20, 40),)
    assert cuts.n_by_quintile["Q1"] == 0  # no se fusionan bandas: queda vacía y se publica
    good = p3.BlockInterval("Δ", 0.3, 1000, 19, 0.2, 0.35, 0.95, 2000)
    verdict, reasons = p3.veredicto_ordenacion(good, horizon_valid=True, resolution_insufficient=True)
    assert verdict == p3.NO_CONCLUYENTE
    assert p3.SCORE_RESOLUTION_INSUFFICIENT in reasons


def test_candidatos_p50_igual_p60() -> None:
    scores = [1.0] * 60 + [float(v) for v in range(2, 42)]
    cand = p3.candidate_set(scores)
    assert cand.values[0] == cand.values[1] == 1.0
    assert cand.collapses == {repr(1.0): [50, 60]}
    assert len(cand.distinct) == 4


def test_candidatos_varios_percentiles_mismo_valor() -> None:
    scores = [float(v) for v in range(1, 56)] + [60.0] * 30 + [float(v) for v in range(61, 76)]
    cand = p3.candidate_set(scores)
    assert cand.values[1] == cand.values[2] == cand.values[3] == 60.0
    assert cand.collapses == {repr(60.0): [60, 70, 80]}
    assert len(cand.distinct) == 3


def test_quintiles_no_leen_desenlace() -> None:
    records = [_record(float(v % 37), float(v % 5) - 2.0, block=v % 7) for v in range(500)]
    altered = [_record(r.score, -r.net_r if r.net_r is not None else None, block=r.block) for r in records]
    assert p3.quintile_cuts([r.score for r in records]) == p3.quintile_cuts([r.score for r in altered])
    assert p3.candidate_set([r.score for r in records]) == p3.candidate_set([r.score for r in altered])


def test_preflight_ejecuta_el_event_study_sin_desenlaces(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: Dict[str, Any] = {}

    def fake_run(*args: Any, **kwargs: Any) -> str:
        seen.update(kwargs)
        seen["managed_is_patched"] = p3.event_study.evaluate_managed_event is p3._no_outcome
        seen["potential_is_patched"] = p3.event_study.evaluate_potential_event is p3._no_outcome
        return "resultado"

    monkeypatch.setattr(p3.event_study, "run_event_study_on_vintage", fake_run)
    p3.run_p3_event_study(None, None, None, "swing", with_outcomes=False)  # type: ignore[arg-type]
    assert seen["managed_is_patched"] and seen["potential_is_patched"]
    assert seen["context_mode"] == "point_in_time"
    assert seen["score_model_version"] == "2.0"
    assert seen["cost_pct"] == 0.2
    seen.clear()
    p3.run_p3_event_study(None, None, None, "swing", with_outcomes=True)  # type: ignore[arg-type]
    assert not seen["managed_is_patched"]
    assert seen["context_mode"] == "point_in_time" and seen["score_model_version"] == "2.0"


# --- estimadores por bloque ---------------------------------------------------


def test_primario_es_el_instrumento_de_a02() -> None:
    records = [_record(50.0, float((b * 7 + i) % 5) - 1.5, block=b) for b in range(15) for i in range(6)]
    interval = p3.primary_interval("X", records)
    means = p3.block_means(records)
    expected = bootstrap_block_mean_interval(
        [(mean, n) for _, mean, n in means], seed=DEFAULT_SEED, n_resamples=DEFAULT_RESAMPLES, confidence=0.95
    )
    assert (interval.lower, interval.upper) == expected
    assert interval.mean == pytest.approx(sum(m for _, m, _ in means) / len(means))
    assert interval.confidence == 0.95 and interval.n_resamples == 2000


def test_contraste_pareado_excluye_bloques_sin_ambas_bandas() -> None:
    high = [_record(80.0, 1.0, block=b) for b in (0, 1, 2, 3)]
    low = [_record(10.0, -1.0, block=b) for b in (1, 2, 3, 4)]
    contrast = p3.paired_block_contrast("Q5−Q1", high, low)
    assert contrast.n_blocks == 3
    assert contrast.excluded_blocks == (0, 4)
    assert contrast.mean == pytest.approx(2.0)


def test_contraste_con_un_solo_bloque_no_calculable() -> None:
    contrast = p3.paired_block_contrast("Q5−Q1", [_record(80.0, 1.0)], [_record(10.0, -1.0)])
    assert contrast.width is None
    verdict, reasons = p3.veredicto_ordenacion(contrast, horizon_valid=True, resolution_insufficient=False)
    assert verdict == p3.NO_CONCLUYENTE and "Δ no calculable" in reasons


def test_veredicto_ordenacion_tabla() -> None:
    def verdict(n_blocks: int, lower: float, upper: float, *, valid: bool = True) -> str:
        interval = p3.BlockInterval("Δ", (lower + upper) / 2, 1000, n_blocks, lower, upper, 0.95, 2000)
        return p3.veredicto_ordenacion(interval, horizon_valid=valid, resolution_insufficient=False)[0]

    assert verdict(11, 0.1, 0.2) == p3.NO_CONCLUYENTE
    assert verdict(19, 0.1, 0.35) == p3.NO_CONCLUYENTE  # anchura 0,25 > 0,20
    assert verdict(19, 0.1, 0.2, valid=False) == p3.NO_CONCLUYENTE
    assert verdict(30, 0.05, 0.15) == p3.VEREDICTO_SUFICIENTE
    assert verdict(19, 0.05, 0.15) == p3.VEREDICTO_LIMITADA  # 19 bloques con anchura 0,10: no SUFICIENTE
    assert verdict(19, -0.05, 0.10) == p3.VEREDICTO_INSUFICIENTE
    interval = p3.BlockInterval("Δ", -0.1, 1000, 19, -0.18, -0.02, 0.95, 2000)
    result, reasons = p3.veredicto_ordenacion(interval, horizon_valid=True, resolution_insufficient=False)
    assert result == p3.VEREDICTO_INSUFICIENTE and "al revés" in reasons[0]


def test_umbrales_del_veredicto_son_los_de_capacity_thresholds() -> None:
    assert DEFAULT_THRESHOLDS.limited_blocks == 12
    assert DEFAULT_THRESHOLDS.sufficient_blocks == 25
    assert DEFAULT_THRESHOLDS.limited_interval_width == 0.20
    assert DEFAULT_THRESHOLDS.sufficient_interval_width == 0.12


# --- calibración ---------------------------------------------------------------


def test_regla_de_umbral_meseta() -> None:
    distinct = [50.0, 60.0, 70.0, 80.0, 90.0]
    cumple = {50.0: False, 60.0: True, 70.0: False, 80.0: True, 90.0: True}
    assert p3.meseta_operar(distinct, cumple) == 80.0
    assert p3.meseta_operar(distinct, {**cumple, 90.0: False}) is None
    assert p3.meseta_operar(distinct, dict.fromkeys(distinct, True)) == 50.0


def test_vigilar_con_candidatos_repetidos() -> None:
    distinct = [40.0, 40.0, 50.0, 60.0, 70.0]
    calls: List[tuple] = []

    def cumple(v: float, top: float) -> bool:
        calls.append((v, top))
        return v != 40.0

    vigilar, visited = p3.recorrido_vigilar(distinct, 70.0, cumple)
    assert calls == [(60.0, 70.0), (50.0, 70.0), (40.0, 70.0)]  # valores distintos, siempre contra operar
    assert vigilar == 50.0
    assert visited[-1] == (40.0, False)


def test_vigilar_el_primer_fallo_corta_sin_saltar() -> None:
    vigilar, visited = p3.recorrido_vigilar([40.0, 50.0, 60.0, 70.0], 70.0, lambda v, top: v != 60.0)
    assert vigilar == 70.0  # franja VIGILAR vacía
    assert visited == [(60.0, False)]


def _fake_population(horizonte: str, *, valid: bool = True) -> Any:
    return SimpleNamespace(
        horizonte=horizonte,
        horizon_valid=valid,
        shortest_block_sessions=42 if valid else 20,
        result=SimpleNamespace(max_hold_bars=40 if horizonte == "swing" else 250),
        block_length=60,
        lookup=None,
    )


def _calibration_records() -> List[p3.P3Record]:
    records = []
    for block in range(20):
        for i in range(60):
            score = float(i + 20)
            net = 0.4 if score >= 55 else (-3.0 if score >= 49 else -0.2)
            records.append(_record(score, net + (block % 3) * 0.01, block=block))
    return records


def test_intervalos_capacidad_estandar_y_bonferroni_separados(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: List[tuple] = []
    original = p3.primary_interval
    original_contrast = p3.paired_block_contrast

    def spy_primary(label: str, records: Any, **kwargs: Any) -> p3.BlockInterval:
        seen.append(("primario", kwargs.get("confidence"), kwargs.get("n_resamples")))
        return original(label, records, **kwargs)

    def spy_contrast(label: str, high: Any, low: Any, **kwargs: Any) -> p3.BlockInterval:
        seen.append(("contraste", kwargs.get("confidence"), kwargs.get("n_resamples")))
        return original_contrast(label, high, low, **kwargs)

    monkeypatch.setattr(p3, "primary_interval", spy_primary)
    monkeypatch.setattr(p3, "paired_block_contrast", spy_contrast)
    capacities: List[str] = []

    def capacity(label: str, subset: Any) -> Any:
        capacities.append(label)
        return SimpleNamespace(verdict="LIMITADA", conclusive=True, resolution="MEDIUM", nominal_n=len(subset),
                               n_blocks=20, primary_expectancy_net_r=0.0, primary_interval_lower=0.0,
                               primary_interval_upper=0.1, primary_interval_width=0.1, exit_final_rate=0.0,
                               ambiguous_rate=0.0, reasons=())

    out = p3._calibration(_calibration_records(), _fake_population("swing"), capacity)
    assert seen and all(conf == p3.BONFERRONI_CONFIDENCE and n == 20_000 for _, conf, n in seen)
    assert pytest.approx(0.9975) == p3.BONFERRONI_CONFIDENCE
    assert out["bonferroni_m"] == 20
    assert capacities  # la capacidad va por el instrumento P2.5, no por el Bonferroni
    # los valores por defecto del instrumento INV-14 no cambian
    assert DEFAULT_RESAMPLES == 2000 and DEFAULT_SEED == 20260830


def test_familia_bonferroni_m20() -> None:
    def capacity(label: str, subset: Any) -> Any:
        return SimpleNamespace(verdict="INSUFICIENTE", conclusive=False, resolution="LOW", nominal_n=len(subset),
                               n_blocks=20, primary_expectancy_net_r=0.0, primary_interval_lower=None,
                               primary_interval_upper=None, primary_interval_width=None, exit_final_rate=0.0,
                               ambiguous_rate=0.0, reasons=())

    out = p3._calibration(_calibration_records(), _fake_population("swing"), capacity)
    family = out["bonferroni_family"]
    assert len(family) == 20
    assert sum(1 for m in family if m["miembro"].startswith("OPERAR primario")) == 5
    assert sum(1 for m in family if m["miembro"].startswith("OPERAR contraste")) == 5
    assert sum(1 for m in family if m["miembro"].startswith("VIGILAR par")) == 10
    assert out["min_score_operar"] is None and out["calibrated"] is False
    assert out["min_score_vigilar"] is None

    collapsed = [_record(10.0, 0.1, block=b) for b in range(20) for _ in range(75)] + [
        _record(float(v), 0.1, block=v % 20) for v in range(11, 36)
    ]
    out = p3._calibration(collapsed, _fake_population("swing"), capacity)
    assert out["candidates"]["collapses"]  # todos los percentiles colapsan en 10
    assert len(out["bonferroni_family"]) == 20  # m sigue en 20
    assert any(m["estado"] == "banda vacía por colapso de candidatos" for m in out["bonferroni_family"])


def test_calibracion_con_desenlaces_fabricados_encuentra_meseta() -> None:
    def capacity(label: str, subset: Any) -> Any:
        return SimpleNamespace(verdict="LIMITADA", conclusive=True, resolution="MEDIUM", nominal_n=len(subset),
                               n_blocks=20, primary_expectancy_net_r=0.0, primary_interval_lower=0.0,
                               primary_interval_upper=0.1, primary_interval_width=0.1, exit_final_rate=0.0,
                               ambiguous_rate=0.0, reasons=())

    out = p3._calibration(_calibration_records(), _fake_population("swing"), capacity)
    # candidatos 49, 55, 61, 67, 73 → cumplen los ≥ 55; 49 no (arrastra la franja [49,55) muy negativa)
    assert out["candidates"]["distinct"] == [49.0, 55.0, 61.0, 67.0, 73.0]
    assert out["min_score_operar"] == 55.0
    assert out["vigilar_recorrido"][0]["v"] == 49.0
    assert out["min_score_vigilar"] == 55.0  # [49,55) pierde: cota superior ≤ 0, franja vacía
    assert out["franja_vigilar_vacia"] is True

    invalid = p3._calibration(_calibration_records(), _fake_population("swing", valid=False), capacity)
    assert invalid["min_score_operar"] is None  # condición 1: horizonte inválido


# --- universo, ablaciones, contadores ------------------------------------------


def test_intra_activo_excluye_pares_incompletos() -> None:
    cuts = (20.0, 40.0, 60.0, 80.0)
    records = []
    for block in range(13):
        records += [_record(90.0, 1.0, block=block, asset="A"), _record(10.0, 0.0, block=block, asset="A")]
    records.append(_record(90.0, 1.0, block=0, asset="B"))  # sin Q1∪Q2: no calculable
    records.append(_record(50.0, 1.0, block=13, asset="C"))  # bloque sin activos calculables
    out = p3._intra_asset(records, cuts, DEFAULT_THRESHOLDS)
    assert out["pares_excluidos"] == 2
    assert {"activo": "B", "bloque": 0, "motivo": "sin Q1∪Q2"} in out["pares_excluidos_detalle"]
    assert out["bloques_sin_activos_calculables"] == [13]
    assert out["n_blocks"] == 13
    assert out["primary"] == pytest.approx(1.0)  # B no cuenta como 0
    short = p3._intra_asset([r for r in records if r.block < 11], cuts, DEFAULT_THRESHOLDS)
    assert short["estado"] == p3.NO_CONCLUYENTE


def test_ablacion_formula() -> None:
    observation = SimpleNamespace(
        signal_id="X",
        score_value=62.0,
        evaluable_max=50.0,
        dimensions=(
            DimensionObservation("catalizador", 9.0, 20.0, True),
            DimensionObservation("fundamental", 0.0, 20.0, False),
            DimensionObservation("tecnico", 15.0, 20.0, True),
            DimensionObservation("contexto", 7.0, 10.0, True),
        ),
    )
    scores = p3.ablated_scores(observation)
    assert scores["catalizador"] == pytest.approx(100 * 22 / 30)
    assert scores["tecnico"] == pytest.approx(100 * 16 / 30)
    assert scores["contexto"] == pytest.approx(100 * 24 / 40)
    bad = SimpleNamespace(**{**observation.__dict__, "score_value": 61.0})
    with pytest.raises(p3.P3PreflightError):
        p3.ablated_scores(bad)


def _synthetic_records(n_assets: int = 3, n_blocks: int = 20) -> List[p3.P3Record]:
    records = []
    for block in range(n_blocks):
        for a in range(n_assets):
            for i in range(10):
                score = float(10 + i * 8 + a)
                net = (score - 50) / 100
                records.append(
                    _record(score, net, block=block, asset=f"A{a}", region=("USA", "EUROPA", "ASIA")[a % 3],
                            ablated={"catalizador": score * 0.9, "tecnico": 100 - score, "contexto": score})
                )
    return records


def test_analyze_horizon_swing_y_medio_forzado_invalido(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_summary(label: str, signals: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(verdict="INSUFICIENTE", conclusive=False, resolution="LOW", nominal_n=len(signals),
                               n_blocks=0, primary_expectancy_net_r=0.0, primary_interval_lower=None,
                               primary_interval_upper=None, primary_interval_width=None, exit_final_rate=0.0,
                               ambiguous_rate=0.0, reasons=("sintético",))

    monkeypatch.setattr(p3, "_summary", fake_summary)
    monkeypatch.setattr(
        p3, "_primary_expectancy_row", lambda *a, **k: PrimaryEstimatorRow("GLOBAL", 0, 0, 0.0, None, None)
    )
    records = _synthetic_records()
    swing = p3.analyze_horizon(_population("swing", records))
    medio = p3.analyze_horizon(_population("medio", records, valid=False))
    assert swing["veredicto_ordenacion"] in {p3.VEREDICTO_LIMITADA, p3.VEREDICTO_INSUFICIENTE, p3.NO_CONCLUYENTE}
    assert swing["delta_q5_q1"]["mean"] > 0
    assert "calibration" in swing and "calibration" not in medio
    assert medio["veredicto_ordenacion"] == p3.MEDIO_FORCED_VERDICT
    assert all(ab["veredicto_ordenacion"] == p3.MEDIO_FORCED_VERDICT for ab in medio["ablations"].values())
    assert swing["label"] == p3.UNIVERSE_LABEL
    assert set(swing["ablations"]) == {"catalizador", "tecnico", "contexto"}
    migration = swing["ablations"]["contexto"]["migracion_desde_score_completo"]
    assert sum(sum(row.values()) for row in migration.values()) == len(records)


def _population(horizonte: str, records: List[p3.P3Record], *, valid: bool = True) -> Any:
    return SimpleNamespace(
        horizonte=horizonte,
        records=records,
        horizon_valid=valid,
        shortest_block_sessions=42 if valid else 102,
        result=SimpleNamespace(max_hold_bars=40 if horizonte == "swing" else 250),
        block_length=60 if horizonte == "swing" else 300,
        lookup=None,
    )


def _outputs(n_assets: int) -> Dict[str, Any]:
    def one(with_family: bool) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "quintiles": [{}] * 5,
            "adjacent_contrasts": [{}] * 4,
            "regions": {"primary": [{}] * 5, "delta": [{}] * 5},
            "assets": {"primary": [{}] * n_assets, "delta": [{}] * n_assets},
            "intra_asset": {"by_asset": [{}] * n_assets},
            "ablations": {name: {"quintiles": [{}] * 5} for name in p3.ABLATED_DIMENSIONS},
        }
        if with_family:
            out["calibration"] = {"bonferroni_family": [{}] * 20}
        return out

    return {"swing": one(True), "medio": one(False)}


def test_contadores_de_comparaciones_derivados() -> None:
    counters = p3.comparison_counters(_outputs(90))
    assert counters == {"comparaciones_swing": 329, "comparaciones_medio_trazabilidad": 309, "comparaciones_totales": 638}
    # se derivan de las salidas, no están codificados: con 89 activos cambian
    assert p3.comparison_counters(_outputs(89))["comparaciones_swing"] == 329 - 3


# --- ejecución única -------------------------------------------------------------


def test_confirmatoria_se_niega_a_repetir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(p3, "CONFIRMATORY_OUTPUT_DIR", tmp_path)
    ident = p3.P3Identity(executor_sha="abc", git_dirty=False, config_hash="h")
    (tmp_path / p3.RUN_MARKER).write_text("{}", encoding="utf-8")
    with pytest.raises(p3.P3AlreadyExecutedError):
        p3.run_confirmatory(None, None, None, ident, tmp_path)  # type: ignore[arg-type]


def test_confirmatoria_solo_escribe_en_la_ruta_fija(tmp_path: Path) -> None:
    ident = p3.P3Identity(executor_sha="abc", git_dirty=False, config_hash="h")
    with pytest.raises(p3.P3PreflightError, match="solo escribe"):
        p3.run_confirmatory(None, None, None, ident, tmp_path / "otra")  # type: ignore[arg-type]
    assert Path("evidence/2026-09-30-T-019-paso3-p3/run") == p3.CONFIRMATORY_OUTPUT_DIR


def test_confirmatoria_exige_arbol_limpio_y_directorio_vacio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "run"
    monkeypatch.setattr(p3, "CONFIRMATORY_OUTPUT_DIR", run_dir)
    for dirty in (True, None):
        ident = p3.P3Identity(executor_sha="abc", git_dirty=dirty, config_hash="h")
        with pytest.raises(p3.P3PreflightError):
            p3.run_confirmatory(None, None, None, ident, run_dir)  # type: ignore[arg-type]
    run_dir.mkdir()
    (run_dir / "algo.txt").write_text("x", encoding="utf-8")
    ident = p3.P3Identity(executor_sha="abc", git_dirty=False, config_hash="h")
    with pytest.raises(p3.P3AlreadyExecutedError):
        p3.run_confirmatory(None, None, None, ident, run_dir)  # type: ignore[arg-type]


def test_confirmatoria_verifica_las_dos_poblaciones_antes_de_analizar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = tmp_path / "run"
    monkeypatch.setattr(p3, "CONFIRMATORY_OUTPUT_DIR", run_dir)
    cuts = {"swing": [1.0, 2.0, 3.0, 4.0], "medio": [1.0, 2.0, 3.0, 4.0]}
    preflight = {"horizontes": {h: {"cuts": {"values": cuts[h]}} for h in p3.HORIZONTES}}
    monkeypatch.setattr(p3, "run_preflight", lambda *a, **k: (True, preflight, {}))

    def fake_population(config: Any, universe: Any, vintage: Any, horizonte: str, *, with_outcomes: bool) -> Any:
        assert with_outcomes
        records = [_record(float(v), 0.1) for v in range(1, 6)]
        checks = [("x", 1, 1, True)] if horizonte == "swing" else [("x", 1, 2, False)]
        return SimpleNamespace(records=records, ok=all(c[3] for c in checks), checks=checks, horizonte=horizonte,
                               horizon_valid=True, shortest_block_sessions=42,
                               result=SimpleNamespace(max_hold_bars=40))

    analyzed: List[str] = []
    monkeypatch.setattr(p3, "build_population", fake_population)
    monkeypatch.setattr(p3, "preflight_summary", lambda pop: {"checks": []})
    monkeypatch.setattr(p3, "analyze_horizon", lambda pop, **k: analyzed.append(pop.horizonte))
    ident = p3.P3Identity(executor_sha="abc", git_dirty=False, config_hash="h")
    code, text = p3.run_confirmatory(None, None, None, ident, run_dir)  # type: ignore[arg-type]
    assert code == 3 and "OWNER_DECISION_REQUIRED" in text
    assert analyzed == []  # swing no se analiza si medio no reproduce el preflight
    assert (run_dir / p3.RUN_MARKER).exists()
    stop = (run_dir / "p3-parada.json").read_text(encoding="utf-8")
    assert "identidad" in stop and "condicionado al universo" in stop


def test_config_hash_distinto_no_pasa_el_preflight() -> None:
    assert p3.EXPECTED_CONFIG_HASH == "89406d28c7b4b6e6c4f032cd63b6868c927af3e926dfb52d430dfa6654d06387"
    config = SimpleNamespace(scoring=SimpleNamespace(score_model_version="1.0"))
    census = SimpleNamespace(
        rows_by_reason={"excluded_crypto": [], "excluded_asia_missing": [], "excluded_trend_sma_history": []},
        stoxx_gap_ages={}, a02_population=0, union_excluded=0, final_population=(), final_sha256="",
        blocks_with_signals=0, stoxx_gap_rows=(),
    )
    population = SimpleNamespace(
        horizonte="swing", census=census, records=[], population_sha256="",
        result=SimpleNamespace(universe_vintage_id="", data_vintage_id=""),
    )
    import advisor.research.p3 as module

    original = module.config_hash
    try:
        module.config_hash = lambda cfg: "otro"  # type: ignore[assignment]
        checks = module._identity_checks(config, population, [])  # type: ignore[arg-type]
    finally:
        module.config_hash = original  # type: ignore[assignment]
    assert ("config_hash", "otro", p3.EXPECTED_CONFIG_HASH, False) in checks


def test_scores_canonicos_mismo_valor_exacto() -> None:
    # 218/3 calculado por dos caminos da floats distintos en el último bit
    a = 100.0 * 21.8 / 30.0
    b = 100.0 * (43.6 / 2) / 30.0
    assert p3.canonical_score(a) == p3.canonical_score(b) == 72.666666667
    cuts = p3.quintile_cuts([p3.canonical_score(v) for v in (a, b, 10.0, 20.0, 90.0)])
    assert cuts.distinct_scores == 4
    observation = SimpleNamespace(
        signal_id="X", score_value=62.0, evaluable_max=50.0,
        dimensions=(
            DimensionObservation("catalizador", 9.0, 20.0, True),
            DimensionObservation("tecnico", 15.0, 20.0, True),
            DimensionObservation("contexto", 7.0, 10.0, True),
        ),
    )
    assert p3.ablated_scores(observation)["catalizador"] == round(100 * 22 / 30, 9)


def test_la_cli_no_expone_parametros_de_reglas() -> None:
    from advisor.main import build_parser

    parser = build_parser()
    sub = next(a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction")
    p3_parser = sub.choices["p3"]  # type: ignore[attr-defined]
    options = {opt for action in p3_parser._actions for opt in action.option_strings}
    assert options == {"-h", "--help", "--fase", "--salida"}
    global_options = {opt for action in parser._actions for opt in action.option_strings}
    # `--config` es global a la CLI; no puede cambiar reglas porque el preflight
    # exige el `config_hash` pre-registrado.
    assert "--config" in global_options


def test_identidad_de_toda_salida() -> None:
    ident = p3.P3Identity(executor_sha="abc", git_dirty=False, config_hash="h").as_dict()
    assert ident["preregistro_sha"] == "8b2dddb8fd66423d9550df496d1a2a85abd066b6"
    assert ident["data_vintage_id"] == "071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841"
    assert ident["universe_vintage_id"] == "237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19"
    assert ident["score_model_version"] == "2.0"
    assert ident["cost_pct"] == 0.2 and ident["seed"] == 20260830
    assert ident["label"].startswith("condicionado al universo seleccionado en 2026")


# --- cosecha real, sin desenlaces -------------------------------------------------


def test_preflight_reproduce_poblacion_y_hash_swing_sin_desenlaces() -> None:
    from advisor.config import load_config
    from advisor.research.vintage import load_vintage
    from advisor.universe.loader import load_universe

    if not (Path("data/vintages") / p3.DATA_VINTAGE_ID).exists():
        pytest.skip("data/vintages no está disponible")
    config = load_config("config.yaml")
    universe = load_universe(config.universe_path)
    vintage = load_vintage(p3.DATA_VINTAGE_ID)
    population = p3.build_population(config, universe, vintage, "swing", with_outcomes=False)
    failed = [(name, observed, wanted) for name, observed, wanted, ok in population.checks if not ok]
    assert failed == []
    assert population.population_sha256 == p3.EXPECTED_POPULATION["swing"]["sha256"]
    assert population.horizon_valid and population.shortest_block_sessions == 42
    assert all(record.net_r is None and record.signal is None for record in population.records)
    assert all(record.score >= 0 for record in population.records)
