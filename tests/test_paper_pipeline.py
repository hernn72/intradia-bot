"""T-025 — flujo completo, separación de intradia.db, idempotencia, concurrencia, sellado y reglas de D-78/D-79.

Sin red: proveedor falso determinista y calendarios reales de tres plazas del universo.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import sqlite3
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest

from paper import LABEL
from paper.audit import replay
from paper.cli import main as cli_main
from paper.environment import Environment, cohort_state, equivalence_check, resolve_investigation
from paper.inputs import Downtime, series_info
from paper.schema import SCHEMA_VERSION, SchemaError
from paper.store import DivergenceError, LockTimeout, NotAPaperDatabase, PaperStore, UnknownReferenceValue
from paper.telegram import shadow_message
from paper.visibility import (
    SEALED_TABLES,
    SealedError,
    close_window,
    cohort_states,
    eligible_for_p7,
    open_window,
    read_outcomes,
    seal_break,
    visible_signals,
    visible_status,
)
from tests.paper_fixtures import (
    ENV,
    ENVS,
    START,
    UNIVERSE,
    Clock,
    FakeProvider,
    fake_evaluator,
    frames,
    make_store,
    passes_between,
    run_passes,
)

UTC = timezone.utc
PAPER = Path(__file__).resolve().parents[1] / "paper"
FORBIDDEN_VISIBLE = ("FILLED", "INSUFFICIENT_CASH", "IGNORED_ALREADY_OPEN", "POSITION_TOO_SMALL", "equity_eur",
                     "cash_eur", "pnl", "units", "exit_reason", "net_R", "mae_R", "mfe_R")


def _cohort(store: PaperStore, policy: str) -> str:
    row = store.one("SELECT cohort_id FROM paper_cohort WHERE policy_id = ?", (policy,))
    assert row is not None
    return str(row["cohort_id"])


def _flow(tmp_path: Path, *, last: date = date(2026, 3, 27), name: str = "paper.db", **provider_kw: Any):
    store = make_store(tmp_path, name)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    provider = FakeProvider(frames(), clock, **provider_kw)
    reports = run_passes(store, provider, clock, passes_between(START, last))
    return store, clock, provider, reports


@pytest.fixture(scope="module")
def flow(tmp_path_factory: pytest.TempPathFactory):
    return _flow(tmp_path_factory.mktemp("flow"))


# ---------------------------------------------------------------------------- flujo completo


def test_flujo_completo_senal_market_pass_orden_posicion_cierre_y_desenlace(flow) -> None:
    store, _clock, _provider, reports = flow
    assert all(r.status == "OK" for r in reports)
    b2 = _cohort(store, "B2")
    kinds = {r["event_type"] for r in store.rows("SELECT event_type FROM paper_ledger WHERE cohort_id = ?", (b2,))}
    assert {"SIGNAL_PENDING", "ENTRY", "EXIT"} <= kinds
    assert store.rows("SELECT * FROM paper_trade_outcome WHERE cohort_id = ?", (b2,))
    assert store.rows("SELECT * FROM paper_equity_snapshot WHERE cohort_id = ?", (_cohort(store, "BH"),))
    checks = {r["check_code"] for r in store.rows("SELECT check_code FROM paper_open_check")}
    assert "MARKET_PASS" in checks


def test_reconstruccion_byte_a_byte_de_todas_las_cohortes(flow) -> None:
    store = flow[0]
    for policy in ("B2", "S2", "C0", "BH"):
        report = replay(store, UNIVERSE, _cohort(store, policy))
        assert report.match, report.as_dict()
        assert report.runs == len(flow[3])


def test_una_pasada_repetida_no_duplica_nada(tmp_path: Path) -> None:
    store, clock, provider, _reports = _flow(tmp_path, last=date(2026, 3, 13))
    before = store.table_counts()
    passes = passes_between(START, date(2026, 3, 13))
    again = run_passes(store, provider, clock, [passes[-1], passes[5]])  # la última y una anterior ya hechas
    assert {r.status for r in again} == {"ALREADY_DONE"}
    assert store.table_counts() == before
    with pytest.raises(DivergenceError):
        row = dict(store.one("SELECT * FROM paper_open_check LIMIT 1"))
        row["entry_effective"] = row["entry_effective"] * 2
        store.insert("paper_open_check", row, ("policy_id", "t025_code_sha", "signal_id"), compare_exclude=("paper_run_id",))


def test_concurrencia_la_segunda_ejecucion_espera_y_sale_sin_escribir(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    other = PaperStore.open(tmp_path / "paper.db")
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    with other.lock(), pytest.raises(LockTimeout):
        run_passes(store, FakeProvider(frames(), clock), clock, passes_between(START, START)[:1])
    assert store.table_counts()["paper_run"] == 0


def test_append_only_y_application_id(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    with pytest.raises(sqlite3.DatabaseError):
        store.conn.execute("UPDATE paper_cohort SET capital_inicial_eur = 1")
    with pytest.raises(sqlite3.DatabaseError):
        store.conn.execute("DELETE FROM paper_cohort")
    with pytest.raises(sqlite3.DatabaseError):
        store.conn.execute("DELETE FROM paper_ref_cohort_state")
    plain = tmp_path / "otra.db"
    sqlite3.connect(plain).execute("CREATE TABLE x (a)").connection.commit()
    with pytest.raises(NotAPaperDatabase):
        PaperStore.open(plain)
    with pytest.raises(NotAPaperDatabase):
        PaperStore.open(tmp_path / "intradia.db", create=True)
    with pytest.raises(UnknownReferenceValue):
        store.check_reference("cohort_state", "ESTADO_FUTURO")


def test_esquema_futuro_solo_si_las_migraciones_son_aditivas(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.conn.execute(f"INSERT INTO paper_schema_migration VALUES ({SCHEMA_VERSION + 1}, 1, 'aditiva')")
    store.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    store.close()
    assert PaperStore.open(tmp_path / "paper.db").schema_version == SCHEMA_VERSION + 1
    other = make_store(tmp_path, "b.db")
    other.conn.execute(f"INSERT INTO paper_schema_migration VALUES ({SCHEMA_VERSION + 1}, 0, 'no aditiva')")
    other.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    other.close()
    with pytest.raises(SchemaError):
        PaperStore.open(tmp_path / "b.db")


# ---------------------------------------------------------------------------- separación de intradia.db


def test_separacion_absoluta_de_intradia_db(tmp_path: Path) -> None:
    from advisor.storage.db import AdvisorDB

    intradia = AdvisorDB(str(tmp_path / "intradia.db"))
    before = sorted(r[0] for r in sqlite3.connect(tmp_path / "intradia.db").execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"))
    _flow(tmp_path, last=date(2026, 3, 6))
    conn = sqlite3.connect(tmp_path / "intradia.db")
    after = sorted(r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'"))
    assert before == after and not [t for t in after if t.startswith("paper_")]
    assert intradia.list_open_positions() == []
    for path in PAPER.glob("*.py"):
        tokens = _code_tokens(path)
        assert not any(t.startswith("advisor.storage") for t in tokens), path.name
        assert "AdvisorDB" not in tokens, path.name


def _code_tokens(path: Path) -> set:
    """Nombres, atributos, imports y literales de código (sin docstrings ni comentarios)."""

    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                  if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body
                  and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)}
    tokens = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            tokens.add(node.id)
        elif isinstance(node, ast.Attribute):
            tokens.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            tokens.update(alias.name for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.module:
                tokens.add(node.module)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            tokens.update(re.findall(r"[A-Za-z_][A-Za-z_0-9.]*", node.value))
    return tokens


def test_el_camino_de_precios_es_get_raw_history_y_nunca_la_cache() -> None:
    for path in PAPER.glob("*.py"):
        tokens = _code_tokens(path)
        for forbidden in ("validated_bar", "CachedBarProvider", "advisor.data.bar_cache", "get_history",
                          "fetch_point_in_time_market_context"):
            assert forbidden not in tokens, (path.name, forbidden)
    assert "get_raw_history" in _code_tokens(PAPER / "ingest.py")


# ---------------------------------------------------------------------------- sellado


def _visible(store: PaperStore) -> Dict[str, Any]:
    status = visible_status(store)
    status.pop("commitments")
    return {"signals": visible_signals(store), "status": status, "telegram": shadow_message(store),
            "cohorts": cohort_states(store)}


def _cli(db: Path, *args: str) -> str:
    out = io.StringIO()
    with redirect_stdout(out):
        cli_main(["--db", str(db), *args])
    return out.getvalue()


def test_dos_libros_con_desenlaces_distintos_dan_la_misma_salida_visible(tmp_path: Path) -> None:
    a_dir, b_dir = tmp_path / "a", tmp_path / "b"
    a_dir.mkdir()
    b_dir.mkdir()
    store_a = _flow(a_dir, last=date(2026, 3, 27))[0]
    # Mismas aperturas y cierres (mismas señales y comprobaciones de apertura), mínimos intradía más bajos:
    # los stops saltan distinto, así que los desenlaces, el cash y la equity del libro B son otros.
    deeper = frames()
    for symbol in ("TSTA.DE", "TSTB", "TSTC.HK"):
        deeper[symbol]["Low"] = deeper[symbol]["Low"] * 0.93
    store_b = make_store(b_dir)
    clock_b = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    run_passes(store_b, FakeProvider(deeper, clock_b), clock_b, passes_between(START, date(2026, 3, 27)))
    b2a, b2b = _cohort(store_a, "B2"), _cohort(store_b, "B2")
    outcomes_a = [r["trade_json"] for r in store_a.rows("SELECT trade_json FROM paper_trade_outcome WHERE cohort_id = ?", (b2a,))]
    outcomes_b = [r["trade_json"] for r in store_b.rows("SELECT trade_json FROM paper_trade_outcome WHERE cohort_id = ?", (b2b,))]
    assert outcomes_a != outcomes_b, "los dos libros tienen que tener desenlaces distintos"
    assert _visible(store_a) == _visible(store_b)
    for command in (("signals",), ("telegram",)):
        text_a, text_b = _cli(a_dir / "paper.db", *command), _cli(b_dir / "paper.db", *command)
        assert text_a == text_b
        assert text_a.startswith(LABEL) or text_a.startswith("🧪")
        for word in FORBIDDEN_VISIBLE:
            assert word not in text_a, (command, word)
    status = _cli(a_dir / "paper.db", "status")
    for word in FORBIDDEN_VISIBLE:
        assert word not in status, word


def test_market_pass_visible_y_filled_sellado(flow) -> None:
    store = flow[0]
    statuses = {r["status"] for r in store.rows("SELECT status FROM paper_entry_decision")}
    assert "FILLED" in statuses
    visible = json.dumps(visible_signals(store))
    assert "MARKET_PASS" in visible
    for word in FORBIDDEN_VISIBLE:
        assert word not in visible
    text = shadow_message(store)
    assert text.splitlines()[0].endswith(LABEL)
    assert "B2-P6" in text and "FILLED" not in text


def test_presentacion_no_lee_tablas_selladas() -> None:
    for name in ("cli.py", "telegram.py"):
        tokens = _code_tokens(PAPER / name)
        for table in SEALED_TABLES:
            assert table not in tokens, (name, table)


def test_desenlaces_sellados_por_la_via_normal_y_ruptura_registrada(flow) -> None:
    store, clock = flow[0], flow[1]
    b2 = _cohort(store, "B2")
    with pytest.raises(SealedError):
        read_outcomes(store, b2, who="propietario", purpose="curiosidad", now=clock())
    assert not store.rows("SELECT * FROM paper_outcome_access WHERE cohort_id = ?", (b2,))
    with pytest.raises(SealedError):
        seal_break(store, b2, who="tecnico", purpose="recuperación", now=clock(), confirm=False)
    payload = seal_break(store, b2, who="tecnico", purpose="recuperación de un fallo", now=clock(), confirm=True)
    access = store.rows("SELECT * FROM paper_outcome_access WHERE cohort_id = ?", (b2,))
    assert len(access) == 1 and access[0]["access_kind"] == "SEAL_BREAK_AUDIT"
    assert json.loads(access[0]["sessions_json"]) and payload["trades"]


def test_bh_visible_consume_sesiones_y_embargo_levantado_desella(tmp_path: Path) -> None:
    store, clock, _p, _r = _flow(tmp_path, last=date(2026, 3, 13))
    bh = _cohort(store, "BH")
    read_outcomes(store, bh, who="propietario", purpose="benchmark", now=clock())
    row = store.one("SELECT * FROM paper_outcome_access WHERE cohort_id = ?", (bh,))
    assert row["access_kind"] == "NORMAL" and json.loads(row["sessions_json"])
    with store.transaction():
        close_window(store, window_id="EMBARGO_T024", closure="EMBARGO_LIFTED", decision_ref="D-nn", now=clock())
    assert read_outcomes(store, _cohort(store, "B2"), who="propietario", purpose="tras T-024", now=clock())["snapshots"]


# ---------------------------------------------------------------------------- ventana de P7 (D-75, D-78, D-79)


def test_ventana_p7_sella_lo_acumulado_y_abandono_virgen_sigue_sellado(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    provider = FakeProvider(frames(), clock)
    run_passes(store, provider, clock, passes_between(START, date(2026, 3, 6)))
    bh = _cohort(store, "BH")
    with pytest.raises(ValueError), store.transaction():
        open_window(store, window_id="P7-A", kind="P7_WINDOW", cohorts=[], sessions_from=date(2026, 3, 2),
                    sessions_to=date(2026, 3, 20), decision_ref="D-x", now=clock())
    with store.transaction():
        open_window(store, window_id="P7-A", kind="P7_WINDOW", cohorts=[], sessions_from=date(2026, 3, 16),
                    sessions_to=date(2026, 3, 20), decision_ref="D-x", now=clock())
    run_passes(store, provider, clock, passes_between(date(2026, 3, 9), date(2026, 3, 27)))
    with pytest.raises(SealedError):
        read_outcomes(store, bh, who="propietario", purpose="equity", now=clock())  # lo acumulado incluye la ventana
    with store.transaction():
        evidence = close_window(store, window_id="P7-A", closure="P7_ABANDONED", decision_ref="D-y", now=clock())
    assert evidence["sessions_status"] == "VIRGEN_REUTILIZABLE" and evidence["seal_still_active"]
    with pytest.raises(SealedError):
        read_outcomes(store, bh, who="propietario", purpose="equity", now=clock())
    first_open = datetime(2026, 3, 16, 0, 0, tzinfo=UTC)
    assert eligible_for_p7(store, "P7-A", first_open - timedelta(days=1), first_open)
    assert not eligible_for_p7(store, "P7-A", first_open + timedelta(days=1), first_open)


def test_ventana_p7_abandonada_con_un_acceso_queda_consumida(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    provider = FakeProvider(frames(), clock)
    run_passes(store, provider, clock, passes_between(START, date(2026, 3, 6)))
    with store.transaction():
        open_window(store, window_id="P7-B", kind="P7_WINDOW", cohorts=[], sessions_from=date(2026, 3, 16),
                    sessions_to=date(2026, 3, 20), decision_ref="D-x", now=clock())
    run_passes(store, provider, clock, passes_between(date(2026, 3, 9), date(2026, 3, 24)))
    seal_break(store, _cohort(store, "BH"), who="tecnico", purpose="auditoría", now=clock(), confirm=True)
    with store.transaction():
        evidence = close_window(store, window_id="P7-B", closure="P7_ABANDONED", decision_ref="D-y", now=clock())
    assert evidence["sessions_status"] == "CONSUMIDA" and not evidence["seal_still_active"]


# ---------------------------------------------------------------------------- caídas y plazos (D-78)


def test_caida_de_la_pi_no_consume_plazos_y_las_senales_quedan_sin_evaluar(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    provider = FakeProvider(frames(), clock)
    all_passes = passes_between(START, date(2026, 3, 27))
    down = {p for p in all_passes if date(2026, 3, 10) <= p.date() <= date(2026, 3, 18)}
    # Mientras la Pi está caída, el proveedor tampoco sirve TSTB; al volver la Pi, la primera petición aún no
    # trae esas barras (llegan dos días después): ni la caída ni esa primera petición consumen el plazo.
    resume = datetime(2026, 3, 21, tzinfo=UTC)
    for day in (date(2026, 3, d) for d in range(10, 19)):
        provider.delays[("TSTB", day)] = resume
    reports = run_passes(store, provider, clock, all_passes, skip=down)
    assert all(r.status == "OK" for r in reports)
    assert store.rows("SELECT * FROM paper_engine_downtime WHERE subcause = 'SIN_EJECUCION'")
    causes = {r["cause"] for r in store.rows("SELECT cause FROM paper_signal_not_evaluated")}
    assert "ENGINE_DOWNTIME" in causes
    now = clock()
    downtime = Downtime(store, now)
    for asset in UNIVERSE.assets:
        info = series_info(store, asset, START, now, UNIVERSE.settlement_minutes, downtime)
        assert info.missing is not None and not info.missing.declared and info.missing.data_loss_since is None
    assert store.rows("SELECT * FROM paper_ledger WHERE row_json LIKE '%\"late_processing\":1%'")
    for policy in ("B2", "BH"):
        assert replay(store, UNIVERSE, _cohort(store, policy)).match


def test_ausencia_del_proveedor_con_motor_operativo_declara_y_suspende(tmp_path: Path) -> None:
    hide = {"TSTB": (date(2026, 3, 9), date(2026, 5, 29), None)}
    store, clock, _provider, _reports = _flow(tmp_path, last=date(2026, 4, 10), hide=hide)
    now = clock()
    info = series_info(store, UNIVERSE.assets[1], START, now, UNIVERSE.settlement_minutes, Downtime(store, now))
    assert info.missing is not None
    assert date(2026, 3, 9) in info.missing.declared
    assert info.missing.data_loss_since == date(2026, 3, 9)
    kinds = {r["kind"] for r in store.rows("SELECT kind FROM paper_data_alert WHERE object = 'TSTB'")}
    assert {"BAR_MISSING", "ENTRY_BAR_DECLARED_MISSING", "NO_DATA_20_SESSIONS"} <= kinds


def test_fetch_failure_es_caida_del_motor_y_no_avanza_plazos(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    provider = FakeProvider(frames(), clock)
    passes = passes_between(START, date(2026, 3, 20))
    run_passes(store, provider, clock, passes[:8])
    provider.down = True
    progress_before = store.table_counts()["paper_cohort_progress"]
    failed = run_passes(store, provider, clock, passes[8:30])
    assert {r.status for r in failed} == {"FETCH_FAILURE"}
    assert sum(r.evaluations for r in failed) > 0, "FETCH_FAILURE no impide confirmar evaluaciones (§5, §7.1)"
    assert store.table_counts()["paper_cohort_progress"] == progress_before, "con FETCH_FAILURE no avanzan los libros"
    assert store.rows("SELECT * FROM paper_engine_downtime WHERE subcause = 'FETCH_FAILURE'")
    assert not store.rows("SELECT * FROM paper_bar_request WHERE result != 'OBTAINED'")
    provider.down = False
    run_passes(store, provider, clock, passes[30:])
    now = clock()
    for asset in UNIVERSE.assets:
        info = series_info(store, asset, START, now, UNIVERSE.settlement_minutes, Downtime(store, now))
        assert info.missing is not None and not info.missing.declared


# ---------------------------------------------------------------------------- épocas de entorno (D-78)


def test_cambio_de_entorno_investigacion_equivalencia_y_epoca_nueva(tmp_path: Path) -> None:
    store, clock, provider, _r = _flow(tmp_path, last=date(2026, 3, 13))
    env2 = Environment(ENV.python_version, ("pandas==3.0.5", "yfinance==1.8.0"), ENV.requirements_sha256)
    reports = run_passes(store, provider, clock, passes_between(date(2026, 3, 16), date(2026, 3, 16)), env=env2)
    assert set(reports[0].cohorts.values()) == {"ENVIRONMENT_INVESTIGATION"}
    b2 = _cohort(store, "B2")
    ledger_before = store.table_counts()["paper_ledger"]
    evals_before = store.table_counts()["paper_signal_evaluation"]
    run_passes(store, provider, clock, passes_between(date(2026, 3, 17), date(2026, 3, 17)), env=env2)
    assert store.table_counts()["paper_ledger"] == ledger_before
    assert store.table_counts()["paper_signal_evaluation"] == evals_before, "en investigación no se evalúa (§13)"
    for policy in ("B2", "S2", "C0", "BH"):
        cohort = _cohort(store, policy)
        result = equivalence_check(store, UNIVERSE, cohort, contract_ok=True, interpretation_ok=True, envs=ENVS,
                                   evaluator=fake_evaluator)
        assert result.passed
        resolve_investigation(store, cohort, env2, passed=True, decision_ref="D-nn", code_sha="c" * 40, now=clock(),
                              first_scheduled_pass="", commitment=result.commitment)
    run_passes(store, provider, clock, passes_between(date(2026, 3, 18), date(2026, 3, 27)), env=env2)
    assert cohort_state(store, b2) == "ACTIVE"
    assert store.rows("SELECT * FROM paper_ledger WHERE cohort_id = ? AND epoch_no = 2", (b2,))


def test_equivalencia_fallida_lleva_a_engine_unrunnable_sin_salidas(tmp_path: Path) -> None:
    store, clock, provider, _r = _flow(tmp_path, last=date(2026, 3, 20))
    b2 = _cohort(store, "B2")
    opened = {r["position_id"] for r in store.rows("SELECT position_id FROM paper_position WHERE cohort_id = ?", (b2,))}
    closed = {r["position_id"] for r in store.rows("SELECT position_id FROM paper_trade_outcome WHERE cohort_id = ?", (b2,))}
    still_open = opened - closed
    env2 = Environment(ENV.python_version, ("pandas==9.9.9",), ENV.requirements_sha256)
    run_passes(store, provider, clock, passes_between(date(2026, 3, 23), date(2026, 3, 23)), env=env2)
    result = equivalence_check(store, UNIVERSE, b2, contract_ok=True, interpretation_ok=False, envs=ENVS,
                               evaluator=fake_evaluator)
    assert not result.passed
    resolve_investigation(store, b2, env2, passed=False, decision_ref="D-nn", code_sha="c" * 40, now=clock(),
                          first_scheduled_pass="", commitment=result.commitment)
    exits_before = len(store.rows("SELECT * FROM paper_ledger WHERE cohort_id = ? AND event_type = 'EXIT'", (b2,)))
    run_passes(store, provider, clock, passes_between(date(2026, 3, 24), date(2026, 3, 27)), env=env2)
    assert cohort_state(store, b2) == "ENGINE_UNRUNNABLE"
    exits_after = len(store.rows("SELECT * FROM paper_ledger WHERE cohort_id = ? AND event_type = 'EXIT'", (b2,)))
    assert exits_after == exits_before
    assert still_open, "el escenario necesita posiciones abiertas"
    flagged = {r["position_id"] for r in store.rows(
        "SELECT position_id FROM paper_position_event WHERE cohort_id = ? AND event_type = 'NO_EVALUABLE_ENGINE_UNRUNNABLE'", (b2,))}
    assert flagged == still_open


# ---------------------------------------------------------------------------- acciones corporativas


def test_split_observado_no_rompe_la_escala_ni_crea_escala_dudosa(tmp_path: Path) -> None:
    ex = date(2026, 3, 16)
    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    provider = FakeProvider(frames(splits={"TSTA.DE": {ex: 2.0}}), clock, splits={"TSTA.DE": (ex, 2.0)})
    run_passes(store, provider, clock, passes_between(START, date(2026, 3, 27)))
    assert store.rows("SELECT * FROM paper_corporate_action WHERE kind = 'SPLIT' AND data_symbol = 'TSTA.DE'")
    assert not store.rows("SELECT * FROM paper_data_alert WHERE kind = 'SCALE_CHANGE_UNEXPLAINED'")
    now = clock()
    info = series_info(store, UNIVERSE.assets[0], START, now, UNIVERSE.settlement_minutes, Downtime(store, now))
    i = info.sessions.index(ex)
    jump = info.view.open[i] / info.view.close[i - 1]
    assert 0.4 < jump < 0.6, "la serie de ejecución conserva el salto real del split (escala de cada sesión)"
    assert info.view.splits.get(i) == 2.0
    from paper.signals import signal_frame

    frame = signal_frame(info, store, "TSTA.DE", now)
    assert 0.9 < frame["Open"].iloc[i] / frame["Close"].iloc[i - 1] < 1.1, "la vista de señal no mezcla escalas"


def test_dividendo_observado_queda_registrado_en_su_sesion(tmp_path: Path) -> None:
    ex = date(2026, 3, 12)
    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    provider = FakeProvider(frames(dividends={"TSTA.DE": {ex: 0.8}}), clock)
    run_passes(store, provider, clock, passes_between(START, date(2026, 3, 20)))
    now = clock()
    info = series_info(store, UNIVERSE.assets[0], START, now, UNIVERSE.settlement_minutes, Downtime(store, now))
    assert info.view.dividends.get(info.sessions.index(ex)) == pytest.approx(0.8)
    assert info.view.splits == {}


def test_cli_status_y_audit(flow, monkeypatch: pytest.MonkeyPatch) -> None:
    import paper.universe

    monkeypatch.setattr(paper.universe, "load_p6_universe", lambda: UNIVERSE)
    db = flow[0].path
    out = _cli(db, "audit")
    assert out.startswith(LABEL)
    payload = json.loads(out[len(LABEL):])
    assert all(item["coincide"] for item in payload)
    assert all("detalle" not in item for item in payload if item["cohort"] in ("B2", "S2", "C0"))
    assert re.search(r'"state": "ACTIVE"', _cli(db, "status"))



# ---------------------------------------------------------------------------- ronda de revisión del código


def test_revision_menor_de_un_cierre_no_mata_el_activo(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    provider = FakeProvider(frames(), clock)
    provider.revisions[("TSTB", date(2026, 3, 12))] = (datetime(2026, 3, 13, tzinfo=UTC), 1.0002)
    run_passes(store, provider, clock, passes_between(START, date(2026, 4, 10)))
    assert not store.rows("SELECT * FROM paper_bar_observation WHERE scale_doubtful = 1")
    now = clock()
    info = series_info(store, UNIVERSE.assets[1], START, now, UNIVERSE.settlement_minutes, Downtime(store, now))
    assert info.missing is not None and not info.missing.declared and info.missing.data_loss_since is None


def test_split_publicado_tarde_no_bloquea_ni_rompe_la_escala(tmp_path: Path) -> None:
    ex = date(2026, 3, 16)
    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    provider = FakeProvider(frames(splits={"TSTB": {ex: 2.0}}), clock, splits={"TSTB": (ex, 2.0)},
                            split_published_at={"TSTB": datetime(2026, 3, 18, 12, tzinfo=UTC)})
    reports = run_passes(store, provider, clock, passes_between(START, date(2026, 3, 27)))
    assert {r.status for r in reports} == {"OK"}, "una divergencia nunca bloquea las pasadas siguientes"
    assert store.rows("SELECT * FROM paper_data_alert WHERE object = 'TSTB' AND kind = 'SCALE_CHANGE_UNEXPLAINED'")
    now = clock()
    info = series_info(store, UNIVERSE.assets[1], START, now, UNIVERSE.settlement_minutes, Downtime(store, now))
    i = info.sessions.index(ex)
    assert info.view.splits.get(i) == 2.0
    for policy in ("B2", "S2", "BH"):
        assert replay(store, UNIVERSE, _cohort(store, policy)).match


def test_fila_del_proveedor_en_festivo_se_descarta_con_alerta(tmp_path: Path) -> None:
    from zoneinfo import ZoneInfo

    import pandas as pd

    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 30, tzinfo=UTC))
    good_friday = pd.Timestamp(datetime(2026, 4, 3, tzinfo=ZoneInfo("Europe/Berlin")))
    extra = pd.DataFrame([{"Open": 5000.0, "High": 5010.0, "Low": 4990.0, "Close": 5000.0, "Volume": 0.0,
                           "Dividends": 0.0, "Stock Splits": 0.0}], index=[good_friday])
    provider = FakeProvider(frames(), clock, extra_rows={"^STOXX50E": extra})
    reports = run_passes(store, provider, clock, passes_between(date(2026, 3, 30), date(2026, 4, 10)))
    assert {r.status for r in reports} == {"OK"}
    assert store.rows("SELECT * FROM paper_data_alert WHERE kind = 'NON_SESSION_ROW' AND object = '^STOXX50E'")


def test_caida_tras_escribir_los_libros_no_reutiliza_run_seq(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import paper.runner as runner

    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    provider = FakeProvider(frames(), clock)
    passes = passes_between(START, date(2026, 3, 20))
    run_passes(store, provider, clock, passes[:10])
    original = runner._finish
    monkeypatch.setattr(runner, "_finish", lambda *a, **k: (_ for _ in ()).throw(SystemExit("corte de luz")))
    with pytest.raises(SystemExit):
        run_passes(store, provider, clock, passes[10:11])
    monkeypatch.setattr(runner, "_finish", original)
    reports = run_passes(store, provider, clock, passes[11:])
    assert {r.status for r in reports} == {"OK"}
    seqs = [r["run_seq"] for r in store.rows("SELECT run_seq FROM paper_run_start ORDER BY run_seq")]
    assert seqs == sorted(set(seqs))
    for policy in ("B2", "S2", "C0", "BH"):
        assert replay(store, UNIVERSE, _cohort(store, policy)).match


def test_lote_cortado_a_mitad_se_reanuda_igual_que_una_pasada_limpia(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import paper.runner as runner

    clean = _flow(tmp_path / "limpio", last=date(2026, 3, 20))[0] if (tmp_path / "limpio").mkdir() is None else None
    assert clean is not None
    (tmp_path / "corte").mkdir()
    store = make_store(tmp_path / "corte")
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    provider = FakeProvider(frames(), clock)
    passes = passes_between(START, date(2026, 3, 20))
    run_passes(store, provider, clock, passes[:12])
    original = runner.persist_progress

    def broken(*args: Any, **kwargs: Any) -> str:
        raise RuntimeError("corte a mitad de la transacción del libro")

    monkeypatch.setattr(runner, "persist_progress", broken)
    run_passes(store, provider, clock, passes[12:13])
    monkeypatch.setattr(runner, "persist_progress", original)
    run_passes(store, provider, clock, passes[13:])
    for policy in ("B2", "S2", "C0", "BH"):
        a = [r["row_json"] for r in clean.rows("SELECT row_json FROM paper_ledger l JOIN paper_cohort c ON c.cohort_id = l.cohort_id "
                                               "WHERE c.policy_id = ? ORDER BY seq", (policy,))]
        b = [json.loads(r["row_json"]) for r in store.rows("SELECT row_json FROM paper_ledger l JOIN paper_cohort c ON c.cohort_id = l.cohort_id "
                                                           "WHERE c.policy_id = ? ORDER BY seq", (policy,))]
        drop = ("late_processing",)
        assert [{k: v for k, v in json.loads(x).items() if k not in drop} for x in a] == [
            {k: v for k, v in y.items() if k not in drop} for y in b], policy


def test_identity_mismatch_no_evalua_y_deja_senales_sin_evaluar_por_caida(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    provider = FakeProvider(frames(), clock)
    passes = passes_between(START, date(2026, 3, 13))
    run_passes(store, provider, clock, passes[:8])
    before = store.table_counts()["paper_signal_evaluation"]
    reports = run_passes(store, provider, clock, passes[8:], identity_ok=lambda _sha: False)
    assert {v for r in reports for v in r.cohorts.values()} == {"IDENTITY_MISMATCH"}
    assert store.table_counts()["paper_signal_evaluation"] == before
    causes = {r["cause"] for r in store.rows("SELECT cause FROM paper_signal_not_evaluated")}
    assert causes == {"ENGINE_DOWNTIME"}


def test_aborted_invalid_engine_congela_la_cohorte(tmp_path: Path) -> None:
    from paper.environment import set_state

    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    provider = FakeProvider(frames(), clock)
    passes = passes_between(START, date(2026, 3, 20))
    run_passes(store, provider, clock, passes[:10])
    b2 = _cohort(store, "B2")
    with store.transaction():
        set_state(store, b2, "ABORTED_INVALID_ENGINE", at=clock(), reason="defecto crítico", decision_ref="D-nn")
    ledger = len(store.rows("SELECT * FROM paper_ledger WHERE cohort_id = ?", (b2,)))
    evals = len(store.rows("SELECT * FROM paper_signal_evaluation WHERE cohort_id = ?", (b2,)))
    run_passes(store, provider, clock, passes[10:])
    assert len(store.rows("SELECT * FROM paper_ledger WHERE cohort_id = ?", (b2,))) == ledger
    assert len(store.rows("SELECT * FROM paper_signal_evaluation WHERE cohort_id = ?", (b2,))) == evals


def test_closed_no_se_publica_durante_el_sellado(tmp_path: Path) -> None:
    from paper.environment import set_state

    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    provider = FakeProvider(frames(), clock)
    run_passes(store, provider, clock, passes_between(START, date(2026, 3, 13)))
    b2 = _cohort(store, "B2")
    with store.transaction():
        set_state(store, b2, "CLOSING", at=clock(), reason="cierre ordinario", decision_ref="D-nn")
    run_passes(store, provider, clock, passes_between(date(2026, 3, 16), date(2026, 3, 27)))
    assert store.rows("SELECT * FROM paper_cohort_event WHERE cohort_id = ? AND state = 'CLOSED'", (b2,))
    state = next(c for c in cohort_states(store) if c["cohort_id"] == b2)["state"]
    assert state == "CLOSING", "CLOSED es un instante que depende de los libros: no se publica sellado"
    with store.transaction():
        close_window(store, window_id="EMBARGO_T024", closure="EMBARGO_LIFTED", decision_ref="D-nn", now=clock())
    assert next(c for c in cohort_states(store) if c["cohort_id"] == b2)["state"] == "CLOSED"


def test_valor_de_referencia_desconocido_falla_cerrado(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    provider = FakeProvider(frames(), clock)
    passes = passes_between(START, date(2026, 3, 13))
    run_passes(store, provider, clock, passes[:6])
    store.conn.execute("INSERT INTO paper_ref_corporate_action_kind(value) VALUES ('MERGER')")
    store.conn.execute("INSERT INTO paper_corporate_action (data_symbol, kind, ex_date, amount, ratio, currency, "
                       "observed_at, provider) VALUES ('TSTB', 'MERGER', '2026-03-10', 0, 0, 'USD', ?, 'futuro')",
                       (clock().isoformat(),))
    reports = run_passes(store, provider, clock, passes[6:7])
    assert reports[0].status == "ERROR"
    codes = {r["code"] for r in store.rows("SELECT code FROM paper_run_diagnostic")}
    assert "UnknownReferenceValue" in codes


def test_interrupcion_del_sellado_deja_la_ventana_consumida(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    now = datetime(2026, 3, 2, tzinfo=UTC)
    with store.transaction():
        open_window(store, window_id="P7-C", kind="P7_WINDOW", cohorts=[], sessions_from=date(2026, 4, 1),
                    sessions_to=date(2026, 4, 30), decision_ref="D-x", now=now)
        row = dict(store.one("SELECT * FROM paper_seal_window WHERE window_id = 'P7-C'"))
        store.insert("paper_seal_window", {**row, "revision": 2, "seal_still_active": 0}, ("window_id", "revision"))
        store.insert("paper_seal_window", {**row, "revision": 3, "seal_still_active": 1}, ("window_id", "revision"))
        evidence = close_window(store, window_id="P7-C", closure="P7_ABANDONED", decision_ref="D-y", now=now)
    assert evidence["sessions_status"] == "CONSUMIDA"


def test_d21_la_barra_europea_guardada_la_vispera_hace_vinculante_la_pasada_de_las_07(tmp_path: Path) -> None:
    from paper.inputs import bindings
    from paper.universe import binding_pass

    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    provider = FakeProvider(frames(), clock)
    # Patrón de D-21: por la mañana el proveedor no sirve la sesión europea anterior (vuelve por la tarde).
    passes = passes_between(START, date(2026, 3, 20))
    for p in passes:
        provider.delays.clear()
        if p.hour < 9:
            previous = p.date() - timedelta(days=3 if p.weekday() == 0 else 1)
            provider.delays[("TSTA.DE", previous)] = p + timedelta(hours=8)
        run_passes(store, provider, clock, [p])
    assert store.rows("SELECT * FROM paper_signal_evaluation WHERE symbol = 'TSTA.DE' AND pass_scheduled_ts LIKE '%T07:00:00%'")
    found = [b for b in bindings(store, _cohort(store, "B2"), UNIVERSE, clock()) if b.asset == "TSTA.DE" and b.final]
    assert found
    for b in found:
        assert b.pass_ts == binding_pass("XETRA", b.signal_session, b.entry_session, UNIVERSE.settlement_minutes)


def test_el_contexto_pit_del_flujo_sale_de_los_cierres_guardados(flow) -> None:
    store = flow[0]
    flags = {json.loads(r["context_json"])["calculable"] for r in store.rows("SELECT context_json FROM paper_signal_evaluation")}
    assert True in flags


def test_caida_de_25_sesiones_y_primera_peticion_sin_barra_no_declara(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    provider = FakeProvider(frames(), clock)
    passes = passes_between(START, date(2026, 4, 24))
    down = {p for p in passes if date(2026, 3, 9) <= p.date() <= date(2026, 4, 10)}
    for day in (date(2026, 3, 9) + timedelta(days=k) for k in range(40)):
        provider.delays[("TSTC.HK", day)] = datetime(2026, 4, 15, tzinfo=UTC)
    run_passes(store, provider, clock, passes, skip=down)
    now = datetime(2026, 4, 14, 23, tzinfo=UTC)
    info = series_info(store, UNIVERSE.assets[2], START, now, UNIVERSE.settlement_minutes, Downtime(store, now))
    assert info.missing is not None and not info.missing.declared and info.missing.data_loss_since is None


def test_el_compromiso_cambia_en_cada_ejecucion_aunque_no_haya_filas_nuevas(flow) -> None:
    store = flow[0]
    b2 = _cohort(store, "B2")
    rows = store.rows("SELECT c.commitment_sha256, s.run_seq FROM paper_seal_commitment c JOIN paper_run_start s "
                      "ON s.paper_run_id = c.paper_run_id WHERE c.cohort_id = ? ORDER BY s.run_seq", (b2,))
    quiet = [r for r in rows if not store.rows("SELECT 1 FROM paper_ledger WHERE cohort_id = ? AND run_seq = ?", (b2, r["run_seq"]))]
    assert len(quiet) >= 2
    assert len({r["commitment_sha256"] for r in rows}) == len(rows)


def _hold_tstb(asset: Any, info: Any, frame: Any, j: int, env: Any, resolver: Any, benchmark: Any, analysis_ts: Any):
    """Evaluador de prueba: OPERAR siempre en TSTB con niveles anchos, para tener una posición abierta."""

    out = fake_evaluator(asset, info, frame, j, env, resolver, benchmark, analysis_ts)
    if asset.symbol != "TSTB":
        return {**out, "operar": 0, "setup_radar": "VIGILAR", "setup_accion": "ESPERAR"}
    close = float(frame["Close"].iloc[j])
    return {**out, "operar": 1, "setup_radar": "OPERAR", "setup_accion": "COMPRAR", "stop": close * 0.6,
            "target2": close * 1.9, "entry_max": close * 1.01}


def _run_held(store: PaperStore, provider: FakeProvider, clock: Clock, first: date, last: date) -> None:
    from paper.runner import run_pass

    for pass_ts in passes_between(first, last):
        clock.current = max(clock.current, pass_ts + timedelta(minutes=2))
        run_pass(store, UNIVERSE, provider, pass_ts=pass_ts, clock=clock, code_sha="c" * 40, environment=ENV,
                 envs=ENVS, identity_ok=lambda _sha: True, evaluator=_hold_tstb, lock_wait_seconds=2.0)


def _tstb_rows(store: PaperStore, policy: str, since: date) -> List[Dict[str, Any]]:
    rows = store.rows("SELECT l.row_json FROM paper_ledger l JOIN paper_cohort c ON c.cohort_id = l.cohort_id "
                      "WHERE c.policy_id = ? ORDER BY l.seq", (policy,))
    out = [json.loads(r["row_json"]) for r in rows]
    return [r for r in out if r["asset"] == "TSTB" and r["session_date"] and r["session_date"] >= since.isoformat()]


@pytest.mark.parametrize("resolution", ["proveedor", "manual", "manual_y_proveedor"])
def test_split_no_publicado_bloquea_la_escala_y_se_reanuda_con_el_split_oficial(tmp_path: Path, resolution: str) -> None:
    from paper.ingest import register_manual_split

    ex = date(2026, 3, 18)
    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    published = {"proveedor": datetime(2026, 3, 24, 12, tzinfo=UTC), "manual": datetime(2027, 1, 1, tzinfo=UTC),
                 "manual_y_proveedor": datetime(2026, 3, 27, 12, tzinfo=UTC)}[resolution]
    provider = FakeProvider(frames(splits={"TSTB": {ex: 2.0}}), clock, splits={"TSTB": (ex, 2.0)},
                            split_published_at={"TSTB": published})
    # Sin publicar, el proveedor sirve la barra ex y las siguientes en la escala nueva y el histórico sin reajustar.
    _run_held(store, provider, clock, START, date(2026, 3, 13))
    b2 = _cohort(store, "B2")
    held_before = [r for r in _tstb_rows(store, "B2", START) if r["event_type"] == "ENTRY"]
    assert held_before, "B2 tiene que tener TSTB abierta antes del split"
    _run_held(store, provider, clock, date(2026, 3, 16), date(2026, 3, 23))

    alerts = store.rows("SELECT session_date FROM paper_data_alert WHERE object = 'TSTB' AND kind = 'SCALE_CHANGE_UNEXPLAINED'")
    assert [a["session_date"] for a in alerts] == [ex.isoformat()], "la primera barra sospechosa abre SCALE_MISMATCH"
    now = clock()
    info = series_info(store, UNIVERSE.assets[1], START, now, UNIVERSE.settlement_minutes, Downtime(store, now))
    assert info.sessions[-1] < ex, "ninguna barra en la escala nueva entra mientras no hay split"
    assert not store.rows("SELECT 1 FROM paper_bar_observation WHERE data_symbol = 'TSTB' AND session_date >= ? AND scale_doubtful = 0",
                          (ex.isoformat(),))
    blocked = [r for r in _tstb_rows(store, "B2", ex) if r["event_type"] in ("EXIT", "SPLIT_ADJUST", "DIVIDEND")]
    assert blocked == [], "ni stop, ni objetivo, ni P&L mientras dura el SCALE_MISMATCH"
    assert not [o for o in store.rows("SELECT position_id, exit_ts_utc FROM paper_trade_outcome WHERE cohort_id = ?", (b2,))
                if o["exit_ts_utc"] >= ex.isoformat()]
    ledger_before = [r["row_json"] for r in store.rows("SELECT row_json FROM paper_ledger WHERE cohort_id = ? ORDER BY seq", (b2,))]

    if resolution in ("manual", "manual_y_proveedor"):
        with store.transaction():
            register_manual_split(store, "TSTB", ex_date=ex, ratio=2.0, currency="USD",
                                  source_url="https://example.invalid/aviso-oficial", source_sha256="f" * 64,
                                  decision_ref="D-nn", now=clock())
    _run_held(store, provider, clock, date(2026, 3, 24), date(2026, 4, 3))
    ledger_after = [r["row_json"] for r in store.rows("SELECT row_json FROM paper_ledger WHERE cohort_id = ? ORDER BY seq", (b2,))]
    assert ledger_after[: len(ledger_before)] == ledger_before, "reanudar no reescribe la historia"
    resumed = _tstb_rows(store, "B2", ex)
    adjust = [r for r in resumed if r["event_type"] == "SPLIT_ADJUST"]
    assert len(adjust) == 1 and adjust[0]["units_after"] == pytest.approx(2 * adjust[0]["units_before"])
    assert not [r for r in resumed if r["event_type"] == "EXIT" and r["reason"] == "stop"], "sin stop ficticio"
    now = clock()
    info = series_info(store, UNIVERSE.assets[1], START, now, UNIVERSE.settlement_minutes, Downtime(store, now))
    assert info.sessions[-1] > ex
    assert [a["session_date"] for a in store.rows(
        "SELECT session_date FROM paper_data_alert WHERE object = 'TSTB' AND kind = 'SCALE_CHANGE_UNEXPLAINED'")] == [ex.isoformat()]
    assert replay(store, UNIVERSE, b2).match


def test_split_nunca_publicado_acaba_en_data_loss_y_no_evaluable(tmp_path: Path) -> None:
    from paper.environment import set_state

    ex = date(2026, 3, 18)
    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    provider = FakeProvider(frames(splits={"TSTB": {ex: 2.0}}), clock, splits={"TSTB": (ex, 2.0)},
                            split_published_at={"TSTB": datetime(2027, 1, 1, tzinfo=UTC)})
    _run_held(store, provider, clock, START, date(2026, 4, 24))
    b2 = _cohort(store, "B2")
    now = clock()
    info = series_info(store, UNIVERSE.assets[1], START, now, UNIVERSE.settlement_minutes, Downtime(store, now))
    assert info.missing is not None and info.missing.data_loss_since == ex
    events = {r["event_type"] for r in store.rows("SELECT event_type FROM paper_position_event WHERE cohort_id = ?", (b2,))}
    assert "DATA_LOSS_SUSPENDED" in events
    assert not [r for r in _tstb_rows(store, "B2", ex) if r["event_type"] == "EXIT"]
    with store.transaction():
        set_state(store, b2, "CLOSING", at=clock(), reason="cierre ordinario", decision_ref="D-nn")
    _run_held(store, provider, clock, date(2026, 4, 27), date(2026, 5, 15))
    events = {r["event_type"] for r in store.rows("SELECT event_type FROM paper_position_event WHERE cohort_id = ?", (b2,))}
    assert "NO_EVALUABLE_DATA_LOSS" in events
    assert not [r for r in _tstb_rows(store, "B2", ex) if r["event_type"] == "EXIT"]


def test_cierre_de_cohorte_no_aparece_como_caida_visible(tmp_path: Path) -> None:
    from paper.environment import set_state

    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    provider = FakeProvider(frames(), clock)
    run_passes(store, provider, clock, passes_between(START, date(2026, 3, 13)))
    b2 = _cohort(store, "B2")
    with store.transaction():
        set_state(store, b2, "CLOSING", at=clock(), reason="cierre ordinario", decision_ref="D-nn")
    run_passes(store, provider, clock, passes_between(date(2026, 3, 16), date(2026, 3, 27)))
    status = json.dumps(visible_status(store))
    assert b2 not in status.split('"downtime"')[1].split('"seal_windows"')[0]
    assert "CLOSED" not in status


def test_late_processing_tras_una_caida_de_la_cohorte(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    provider = FakeProvider(frames(), clock)
    passes = passes_between(START, date(2026, 3, 27))
    run_passes(store, provider, clock, passes[:12])
    run_passes(store, provider, clock, passes[12:24], identity_ok=lambda _sha: False)
    run_passes(store, provider, clock, passes[24:])
    b2 = _cohort(store, "B2")
    assert store.rows("SELECT 1 FROM paper_ledger WHERE cohort_id = ? AND row_json LIKE '%\"late_processing\":1%'", (b2,))
    assert replay(store, UNIVERSE, b2).match


def test_hueco_real_con_forma_de_split_queda_bloqueado_por_la_regla_del_8_6(tmp_path: Path) -> None:
    """Regresión explícita de la regla elegida (§8.6): con una sola barra, un hueco real de −33 % no se
    distingue de un split no publicado; sin split observado nunca se desbloquea y acaba en DATA_LOSS. Es la
    consecuencia declarada de no adivinar el ratio ni mezclar escalas."""

    gap_day = date(2026, 3, 18)
    data = frames()
    tstb = data["TSTB"]
    after = [ts.date() >= gap_day for ts in tstb.index]
    for column in ("Open", "High", "Low", "Close"):
        tstb.loc[after, column] = tstb.loc[after, column] * (2 / 3)
    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    run_passes(store, FakeProvider(data, clock), clock, passes_between(START, date(2026, 4, 17)))
    now = clock()
    info = series_info(store, UNIVERSE.assets[1], START, now, UNIVERSE.settlement_minutes, Downtime(store, now))
    assert info.missing is not None and info.missing.data_loss_since == gap_day
    assert info.sessions[-1] < gap_day


def test_bloqueo_por_solape_se_resuelve_con_un_split_posterior_a_la_ultima_vigente(tmp_path: Path) -> None:
    from paper.ingest import unresolved_scale_mismatch

    store = make_store(tmp_path)
    now = datetime(2026, 3, 30, tzinfo=UTC)
    with store.transaction():
        for day in ("2026-03-16", "2026-03-17"):
            store.conn.execute("INSERT INTO paper_bar_observation VALUES ('TSTB', ?, ?, 10, 10, 10, 10, 0, ?, 'p', 'r', 0)",
                               (day, day + "T00:00:00-04:00", "2026-03-18T00:00:00+00:00"))
        store.conn.execute("INSERT INTO paper_data_alert VALUES ('TSTB', 'SCALE_CHANGE_UNEXPLAINED', '2026-03-18', ?)",
                           ("2026-03-21T00:00:00+00:00",))
    assert unresolved_scale_mismatch(store, "TSTB", as_of=now.isoformat()) == date(2026, 3, 18)
    with store.transaction():
        store.conn.execute("INSERT INTO paper_corporate_action (data_symbol, kind, ex_date, amount, ratio, currency, "
                           "observed_at, provider) VALUES ('TSTB', 'SPLIT', '2026-03-20', 0, 2, 'USD', ?, 'yfinance')",
                           ("2026-03-25T00:00:00+00:00",))
    assert unresolved_scale_mismatch(store, "TSTB", as_of=now.isoformat()) is None


GAP_DAY = date(2026, 3, 18)
GAP_URL = "https://example.invalid/fuente-del-hueco"


def _gap_frames(factor: float = 0.5) -> Dict[str, Any]:
    """TSTB cae un 50 % en la apertura de ``GAP_DAY`` y se queda ahí: hueco real con forma de split 2:1."""

    data = frames()
    tstb = data["TSTB"]
    after = [stamp.date() >= GAP_DAY for stamp in tstb.index]
    for column in ("Open", "High", "Low", "Close"):
        tstb.loc[after, column] = tstb.loc[after, column] * factor
    return data


def _b2_ledger(store: PaperStore, b2: str) -> List[str]:
    return [r["row_json"] for r in store.rows("SELECT row_json FROM paper_ledger WHERE cohort_id = ? ORDER BY seq", (b2,))]


def test_hueco_real_ambiguo_sin_resolucion_sigue_bloqueado_y_acaba_no_evaluable(tmp_path: Path) -> None:
    """D-80 (1): sin ``REAL_GAP_CONFIRMED`` el hueco con forma de split nunca se libera solo:
    SCALE_MISMATCH → DATA_LOSS_SUSPENDED → NO_EVALUABLE_DATA_LOSS, sin stop ni P&L desde esas barras."""

    from paper.environment import set_state
    from paper.ingest import unresolved_scale_mismatch

    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    provider = FakeProvider(_gap_frames(), clock)
    _run_held(store, provider, clock, START, date(2026, 4, 24))
    b2 = _cohort(store, "B2")
    assert [r for r in _tstb_rows(store, "B2", START) if r["event_type"] == "ENTRY"]
    assert unresolved_scale_mismatch(store, "TSTB", as_of=clock().isoformat()) == GAP_DAY
    assert not store.rows("SELECT 1 FROM paper_scale_resolution"), "la resolución nunca se infiere"
    now = clock()
    info = series_info(store, UNIVERSE.assets[1], START, now, UNIVERSE.settlement_minutes, Downtime(store, now))
    assert info.missing is not None and info.missing.data_loss_since == GAP_DAY and not info.view.catchup
    events = {r["event_type"] for r in store.rows("SELECT event_type FROM paper_position_event WHERE cohort_id = ?", (b2,))}
    assert "DATA_LOSS_SUSPENDED" in events
    with store.transaction():
        set_state(store, b2, "CLOSING", at=clock(), reason="cierre ordinario", decision_ref="D-nn")
    _run_held(store, provider, clock, date(2026, 4, 27), date(2026, 5, 15))
    events = {r["event_type"] for r in store.rows("SELECT event_type FROM paper_position_event WHERE cohort_id = ?", (b2,))}
    assert "NO_EVALUABLE_DATA_LOSS" in events
    assert not [r for r in _tstb_rows(store, "B2", GAP_DAY) if r["event_type"] == "EXIT"]
    assert replay(store, UNIVERSE, b2).match


@pytest.mark.parametrize("moment", ["antes_de_declarar", "despues_de_declarar"])
def test_real_gap_confirmed_libera_y_procesa_causalmente_las_barras_bloqueadas(tmp_path: Path, moment: str) -> None:
    """D-80 (2): con la resolución manual, las barras bloqueadas cuentan como precios reales desde que se registra:
    el hueco bajo el stop cierra al precio de apertura del hueco, sin reescribir nada anterior. Si la sesión ya se
    había declarado ausente, se recorre en la frontera, marcada ``late`` y ``late_processing``."""

    from paper.ingest import register_real_gap, unresolved_scale_mismatch

    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    data = _gap_frames()
    provider = FakeProvider(data, clock)
    blocked_until = {"antes_de_declarar": date(2026, 3, 20), "despues_de_declarar": date(2026, 4, 1)}[moment]
    _run_held(store, provider, clock, START, blocked_until)
    b2 = _cohort(store, "B2")
    assert [r for r in _tstb_rows(store, "B2", START) if r["event_type"] == "ENTRY"]
    assert not [r for r in _tstb_rows(store, "B2", GAP_DAY) if r["event_type"] == "EXIT"], "bloqueado sin resolución"
    now = clock()
    info = series_info(store, UNIVERSE.assets[1], START, now, UNIVERSE.settlement_minutes, Downtime(store, now))
    assert (GAP_DAY in info.missing.declared) == (moment == "despues_de_declarar")  # type: ignore[union-attr]
    before = _b2_ledger(store, b2)

    resolved_at = clock()
    with store.transaction():
        assert register_real_gap(store, "TSTB", session_date=GAP_DAY, source_url=GAP_URL, evidence_sha256="e" * 64,
                                 decision_ref="D-80", now=resolved_at)
    assert unresolved_scale_mismatch(store, "TSTB", as_of=resolved_at.isoformat()) is None
    _run_held(store, provider, clock, blocked_until + timedelta(days=3), blocked_until + timedelta(days=14))

    after = _b2_ledger(store, b2)
    assert after[: len(before)] == before, "no se reescribe ninguna decisión anterior"
    exits = [r for r in _tstb_rows(store, "B2", GAP_DAY) if r["event_type"] == "EXIT"]
    assert len(exits) == 1
    exit_row = exits[0]
    assert exit_row["reason"] == "stop" and exit_row["session_date"] == GAP_DAY.isoformat()
    assert exit_row["seq"] > max((json.loads(r)["seq"] for r in before), default=0), "solo tras la resolución"
    gap_open = float(data["TSTB"].loc[[s.date() == GAP_DAY for s in data["TSTB"].index], "Open"].iloc[0])
    assert exit_row["market_price"] == pytest.approx(gap_open), "el stop se ejecuta al precio real del hueco"
    late = moment == "despues_de_declarar"
    assert (exit_row["late"], exit_row["late_processing"]) == ((1, 1) if late else (0, 0))
    now = clock()
    info = series_info(store, UNIVERSE.assets[1], START, now, UNIVERSE.settlement_minutes, Downtime(store, now))
    assert info.missing is not None and info.missing.data_loss_since is None
    assert info.sessions[-1] > GAP_DAY and (GAP_DAY in info.sessions) == (not late)
    outcome = store.one("SELECT exit_session FROM paper_trade_outcome WHERE cohort_id = ? AND position_id = ?",
                        (b2, exit_row["position_id"]))
    assert outcome is not None and outcome["exit_session"] == GAP_DAY.isoformat()
    assert replay(store, UNIVERSE, b2).match


def test_split_real_no_publicado_no_se_libera_como_hueco_sin_resolucion_explicita(tmp_path: Path) -> None:
    """D-80 (3): un split real que el proveedor no publica tiene la misma forma que un hueco; nada lo libera
    como hueco salvo la resolución manual, que exige fuente, sha256, D-nn y el SCALE_MISMATCH de esa sesión exacta."""

    from paper.ingest import register_real_gap, unresolved_scale_mismatch

    ex = date(2026, 3, 18)
    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    provider = FakeProvider(frames(splits={"TSTB": {ex: 2.0}}), clock, splits={"TSTB": (ex, 2.0)},
                            split_published_at={"TSTB": datetime(2027, 1, 1, tzinfo=UTC)})
    _run_held(store, provider, clock, START, date(2026, 4, 3))
    assert unresolved_scale_mismatch(store, "TSTB", as_of=clock().isoformat()) == ex
    assert not store.rows("SELECT 1 FROM paper_scale_resolution")
    now = clock()
    info = series_info(store, UNIVERSE.assets[1], START, now, UNIVERSE.settlement_minutes, Downtime(store, now))
    assert info.sessions[-1] < ex and not info.view.catchup
    assert not [r for r in _tstb_rows(store, "B2", ex) if r["event_type"] == "EXIT"]

    good = {"session_date": ex, "source_url": GAP_URL, "evidence_sha256": "e" * 64, "decision_ref": "D-80", "now": clock()}
    for wrong in ({"source_url": " "}, {"evidence_sha256": "e" * 10}, {"evidence_sha256": "E" * 64},
                  {"decision_ref": ""}, {"decision_ref": "propietario"},
                  {"session_date": ex + timedelta(days=1)}):
        with pytest.raises(ValueError):
            register_real_gap(store, "TSTB", **{**good, **wrong})  # type: ignore[arg-type]
    assert not store.rows("SELECT 1 FROM paper_scale_resolution")
    assert unresolved_scale_mismatch(store, "TSTB", as_of=clock().isoformat()) == ex

    evidence = tmp_path / "evidencia-hueco.txt"
    evidence.write_text("captura de la fuente oficial")
    command = ["real-gap-confirmed", "--symbol", "TSTB", "--session", ex.isoformat(), "--source-url", GAP_URL,
               "--evidence", str(evidence)]
    assert cli_main(["--db", str(tmp_path / "paper.db"), *command, "--decision", "D80"]) == 6
    assert not store.rows("SELECT 1 FROM paper_scale_resolution")
    assert '"registrada": true' in _cli(tmp_path / "paper.db", *command, "--decision", "D-80")
    stored = store.one("SELECT * FROM paper_scale_resolution")
    assert stored is not None and stored["evidence_sha256"] == hashlib.sha256(evidence.read_bytes()).hexdigest()
    assert (stored["data_symbol"], stored["session_date"], stored["resolution"]) == ("TSTB", ex.isoformat(), "REAL_GAP_CONFIRMED")
    with pytest.raises(sqlite3.Error), store.transaction():
        store.conn.execute("DELETE FROM paper_scale_resolution")
    with pytest.raises(sqlite3.Error), store.transaction():
        store.conn.execute("UPDATE paper_scale_resolution SET decision_ref = 'D-99'")
    assert store.one("SELECT decision_ref FROM paper_scale_resolution")["decision_ref"] == "D-80"
