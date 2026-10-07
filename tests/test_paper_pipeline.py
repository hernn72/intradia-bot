"""T-025 — flujo completo, separación de intradia.db, idempotencia, concurrencia, sellado y reglas de D-78/D-79.

Sin red: proveedor falso determinista y calendarios reales de tres plazas del universo.
"""

from __future__ import annotations

import io
import json
import re
import sqlite3
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

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


def test_hueco_real_con_forma_de_split_no_mata_el_activo_ni_esconde_la_perdida(tmp_path: Path) -> None:
    gap_day = date(2026, 3, 18)
    data = frames()
    tz_frame = data["TSTB"]
    after = [ts.date() >= gap_day for ts in tz_frame.index]
    for column in ("Open", "High", "Low", "Close"):
        tz_frame.loc[after, column] = tz_frame.loc[after, column] * (2 / 3)  # caída real del −33 %, sin split
    store = make_store(tmp_path)
    clock = Clock(datetime(2026, 3, 2, tzinfo=UTC))
    run_passes(store, FakeProvider(data, clock), clock, passes_between(START, date(2026, 4, 17)))
    now = clock()
    info = series_info(store, UNIVERSE.assets[1], START, now, UNIVERSE.settlement_minutes, Downtime(store, now))
    assert info.missing is not None and info.missing.data_loss_since is None
    assert info.sessions[-1] > date(2026, 4, 10), "el activo sigue vivo después del hueco"
    assert gap_day in info.missing.declared, "la barra del salto, sin split, se declara ausente (salto de P6)"
    assert not store.rows("SELECT * FROM paper_data_alert WHERE object = 'TSTB' AND kind = 'NO_DATA_20_SESSIONS'")


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
