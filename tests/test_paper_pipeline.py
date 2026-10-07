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
    START,
    UNIVERSE,
    Clock,
    FakeProvider,
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
    last_pass = passes_between(START, date(2026, 3, 13))[-1]
    run_passes(store, provider, clock, [last_pass])
    after = store.table_counts()
    for table in ("paper_ledger", "paper_signal_evaluation", "paper_open_check", "paper_position", "paper_trade_outcome"):
        assert after[table] == before[table], table
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
    store_a = _flow(a_dir, last=date(2026, 3, 20))[0]
    store_b = _flow(b_dir, last=date(2026, 3, 20))[0]
    b2 = _cohort(store_b, "B2")
    # El libro B tiene desenlaces, cash y estados distintos: nada de eso puede asomar en la salida visible.
    store_b.conn.execute("INSERT INTO paper_entry_decision VALUES (?, 'X|swing|2026-03-10', 'INSUFFICIENT_CASH', '2026-03-11T08:00:00Z', 99999)", (b2,))
    store_b.conn.execute("INSERT INTO paper_equity_snapshot VALUES (?, '2026-12-31', 99, 0, 1, 2, 3, 0, 4, '{}', 'x')", (b2,))
    store_b.conn.execute("INSERT INTO paper_ledger VALUES (?, 99999, 99, 0, 'EXIT', '2026-12-31T00:00:00Z', 's', 'p', '{}', 'x')", (b2,))
    assert _visible(store_a) == _visible(store_b)
    for command in (("status",), ("signals",), ("telegram",)):
        text_a, text_b = _cli(a_dir / "paper.db", *command), _cli(b_dir / "paper.db", *command)
        if command != ("status",):
            assert text_a == text_b
        assert text_a.startswith(LABEL) or text_a.startswith("🧪")
        for word in FORBIDDEN_VISIBLE:
            assert word not in text_a, (command, word)


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
    failed = run_passes(store, provider, clock, passes[8:30])
    assert {r.status for r in failed} == {"FETCH_FAILURE"}
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
    run_passes(store, provider, clock, passes_between(date(2026, 3, 17), date(2026, 3, 17)), env=env2)
    assert store.table_counts()["paper_ledger"] == ledger_before
    for policy in ("B2", "S2", "C0", "BH"):
        cohort = _cohort(store, policy)
        result = equivalence_check(store, UNIVERSE, cohort, contract_ok=True, interpretation_ok=True)
        assert result.passed
        resolve_investigation(store, cohort, env2, passed=True, decision_ref="D-nn", code_sha="c" * 40, now=clock(),
                              first_scheduled_pass="", commitment=result.commitment)
    run_passes(store, provider, clock, passes_between(date(2026, 3, 18), date(2026, 3, 27)), env=env2)
    assert cohort_state(store, b2) == "ACTIVE"
    assert store.rows("SELECT * FROM paper_ledger WHERE cohort_id = ? AND epoch_no = 2", (b2,))


def test_equivalencia_fallida_lleva_a_engine_unrunnable_sin_salidas(tmp_path: Path) -> None:
    store, clock, provider, _r = _flow(tmp_path, last=date(2026, 3, 20))
    b2 = _cohort(store, "B2")
    open_before = store.rows("SELECT COUNT(*) AS n FROM paper_position WHERE cohort_id = ?", (b2,))[0]["n"]
    env2 = Environment(ENV.python_version, ("pandas==9.9.9",), ENV.requirements_sha256)
    run_passes(store, provider, clock, passes_between(date(2026, 3, 23), date(2026, 3, 23)), env=env2)
    result = equivalence_check(store, UNIVERSE, b2, contract_ok=True, interpretation_ok=False)
    assert not result.passed
    resolve_investigation(store, b2, env2, passed=False, decision_ref="D-nn", code_sha="c" * 40, now=clock(),
                          first_scheduled_pass="", commitment=result.commitment)
    exits_before = len(store.rows("SELECT * FROM paper_ledger WHERE cohort_id = ? AND event_type = 'EXIT'", (b2,)))
    run_passes(store, provider, clock, passes_between(date(2026, 3, 24), date(2026, 3, 27)), env=env2)
    assert cohort_state(store, b2) == "ENGINE_UNRUNNABLE"
    exits_after = len(store.rows("SELECT * FROM paper_ledger WHERE cohort_id = ? AND event_type = 'EXIT'", (b2,)))
    assert exits_after == exits_before
    events = {r["event_type"] for r in store.rows("SELECT event_type FROM paper_position_event WHERE cohort_id = ?", (b2,))}
    if open_before:
        assert "NO_EVALUABLE_ENGINE_UNRUNNABLE" in events or "EXIT" in events


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

