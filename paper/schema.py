"""Esquema y migraciones de ``paper.db`` (ficha §4–§5, §12; D-75, D-78).

- ``PRAGMA application_id`` propio: el código paper se niega a abrir una base sin esa marca, así que nunca
  abre ``intradia.db``.
- ``PRAGMA user_version`` = versión del esquema. Las migraciones son **solo aditivas** (tablas, columnas con
  valor por defecto, filas de referencia); una no aditiva exige un fichero nuevo y cohortes nuevas.
- Las listas cerradas se validan con claves foráneas a tablas de referencia append-only, no con ``CHECK``:
  añadir un estado es insertar una fila (ronda 4b, N-2).
- Las tablas de hechos son append-only: triggers ``BEFORE UPDATE`` y ``BEFORE DELETE`` con ``RAISE(ABORT)``.
"""

from __future__ import annotations

import sqlite3
from typing import Dict, List, Sequence, Tuple

APPLICATION_ID = 0x54303235  # "T025"
SCHEMA_VERSION = 1

REFERENCE_DOMAINS: Dict[str, Tuple[str, ...]] = {
    "cohort_state": ("ACTIVE", "ENVIRONMENT_INVESTIGATION", "CLOSING", "CLOSED", "ENGINE_UNRUNNABLE", "ABORTED_INVALID_ENGINE"),
    "book_kind": ("PAPER",),
    "cohort_kind": ("POLICY", "BENCHMARK"),
    "run_status": ("OK", "ERROR", "IDENTITY_MISMATCH", "FETCH_FAILURE"),
    "bar_request_result": ("OBTAINED", "PROVIDER_DATA_MISSING", "FETCH_FAILURE"),
    "downtime_cause": ("ENGINE_DOWNTIME",),
    "data_alert_kind": (
        "BAR_MISSING", "ENTRY_BAR_DECLARED_MISSING", "NO_DATA_20_SESSIONS", "DATA_RESUMED", "FX_MISSING",
        "SCALE_CHANGE_UNEXPLAINED", "LATE_BAR", "LATE_DIVIDEND", "FETCH_FAILURE", "NON_SESSION_ROW",
    ),
    "corporate_action_kind": ("DIVIDEND", "SPLIT", "TERMINAL"),
    "terminal_kind": ("", "DELISTING_CASH", "LIQUIDATION", "CASH_MERGER"),
    "open_check": ("MARKET_PASS", "DATA_NOT_EXECUTABLE", "INVALID_STOP", "INVALID_TARGET", "ABOVE_MAX_ENTRY", "RR_TOO_LOW"),
    "seal_kind": ("EMBARGO_T024", "P7_WINDOW"),
    "seal_closure": ("", "EMBARGO_LIFTED", "P7_CONSULTED", "P7_ABANDONED"),
    "sessions_status": ("", "CONSUMIDA", "VIRGEN_REUTILIZABLE"),
    "access_kind": ("NORMAL", "SEAL_BREAK_AUDIT", "P7_HOLDOUT_QUERY"),
    "signal_cause": ("", "ENGINE_DOWNTIME", "PROVIDER_DATA_MISSING"),
}

# (tabla, columna, dominio)
REFERENCE_COLUMNS: Sequence[Tuple[str, str, str]] = (
    ("paper_cohort", "book_kind", "book_kind"),
    ("paper_cohort", "kind", "cohort_kind"),
    ("paper_cohort_event", "state", "cohort_state"),
    ("paper_run", "status", "run_status"),
    ("paper_bar_request", "result", "bar_request_result"),
    ("paper_engine_downtime", "cause", "downtime_cause"),
    ("paper_data_alert", "kind", "data_alert_kind"),
    ("paper_corporate_action", "kind", "corporate_action_kind"),
    ("paper_corporate_action", "terminal_kind", "terminal_kind"),
    ("paper_open_check", "check_code", "open_check"),
    ("paper_seal_window", "kind", "seal_kind"),
    ("paper_seal_window", "closure", "seal_closure"),
    ("paper_seal_window", "sessions_status", "sessions_status"),
    ("paper_outcome_access", "access_kind", "access_kind"),
    ("paper_signal_not_evaluated", "cause", "signal_cause"),
)


def _ref(table: str, column: str) -> str:
    for t, c, domain in REFERENCE_COLUMNS:
        if (t, c) == (table, column):
            return f"REFERENCES paper_ref_{domain}(value)"
    raise KeyError((table, column))


FACT_TABLES: Dict[str, str] = {
    "paper_schema_migration": """
        version INTEGER PRIMARY KEY,
        additive INTEGER NOT NULL,
        description TEXT NOT NULL
    """,
    "paper_cohort": f"""
        cohort_id TEXT PRIMARY KEY,
        book_kind TEXT NOT NULL {_ref('paper_cohort', 'book_kind')},
        kind TEXT NOT NULL {_ref('paper_cohort', 'kind')},
        policy_id TEXT NOT NULL,
        policy_sha256 TEXT NOT NULL,
        advisor_config_hash TEXT NOT NULL,
        p6_system_sha256 TEXT NOT NULL,
        t025_system_sha256 TEXT NOT NULL,
        engine_version TEXT NOT NULL,
        t025_prereg_sha TEXT NOT NULL,
        t025_code_sha TEXT NOT NULL,
        capital_inicial_eur REAL NOT NULL,
        base_currency TEXT NOT NULL,
        asset_list_sha256 TEXT NOT NULL,
        universe_vintage_id TEXT NOT NULL,
        start_date TEXT NOT NULL,
        seal_rule TEXT NOT NULL,
        label TEXT NOT NULL,
        contract_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    """,
    "paper_cohort_event": f"""
        cohort_id TEXT NOT NULL REFERENCES paper_cohort(cohort_id),
        state TEXT NOT NULL {_ref('paper_cohort_event', 'state')},
        event_ts_utc TEXT NOT NULL,
        reason TEXT NOT NULL,
        decision_ref TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (cohort_id, state, event_ts_utc)
    """,
    "paper_environment_epoch": """
        cohort_id TEXT NOT NULL REFERENCES paper_cohort(cohort_id),
        epoch_no INTEGER NOT NULL,
        epoch_code_sha TEXT NOT NULL,
        python_version TEXT NOT NULL,
        installed_packages_sha256 TEXT NOT NULL,
        packages_json TEXT NOT NULL,
        requirements_sha256 TEXT NOT NULL,
        started_at TEXT NOT NULL,
        first_scheduled_pass TEXT NOT NULL,
        decision_ref TEXT NOT NULL,
        equivalence_commitment TEXT NOT NULL,
        PRIMARY KEY (cohort_id, epoch_no)
    """,
    "paper_run_start": """
        paper_run_id TEXT PRIMARY KEY,
        run_seq INTEGER NOT NULL UNIQUE,
        pass_scheduled_ts TEXT NOT NULL,
        started_at TEXT NOT NULL
    """,
    "paper_run_decision": """
        paper_run_id TEXT PRIMARY KEY REFERENCES paper_run_start(paper_run_id),
        run_seq INTEGER NOT NULL UNIQUE,
        pass_scheduled_ts TEXT NOT NULL,
        data_cutoff_ts TEXT NOT NULL,
        decision_ts TEXT NOT NULL,
        late_before TEXT NOT NULL,
        fetch_failure INTEGER NOT NULL
    """,
    "paper_run": f"""
        paper_run_id TEXT PRIMARY KEY,
        run_seq INTEGER NOT NULL UNIQUE,
        source_run_id TEXT NOT NULL,
        pass_scheduled_ts TEXT NOT NULL,
        started_at TEXT NOT NULL,
        data_cutoff_ts TEXT NOT NULL,
        decision_ts TEXT NOT NULL,
        finished_at TEXT NOT NULL,
        late_before TEXT NOT NULL,
        status TEXT NOT NULL {_ref('paper_run', 'status')},
        engine_version TEXT NOT NULL,
        schema_version INTEGER NOT NULL,
        code_sha TEXT NOT NULL,
        manifest_json TEXT NOT NULL
    """,
    "paper_run_diagnostic": """
        paper_run_id TEXT NOT NULL,
        cohort_id TEXT NOT NULL,
        code TEXT NOT NULL,
        detail_json TEXT NOT NULL,
        PRIMARY KEY (paper_run_id, cohort_id, code)
    """,
    "paper_bar_request": f"""
        paper_run_id TEXT NOT NULL,
        object TEXT NOT NULL,
        session_date TEXT NOT NULL,
        due INTEGER NOT NULL,
        requested_at TEXT NOT NULL,
        result TEXT NOT NULL {_ref('paper_bar_request', 'result')},
        PRIMARY KEY (paper_run_id, object, session_date)
    """,
    "paper_engine_downtime": f"""
        scope TEXT NOT NULL,
        from_scheduled_pass TEXT NOT NULL,
        to_scheduled_pass TEXT NOT NULL,
        cause TEXT NOT NULL {_ref('paper_engine_downtime', 'cause')},
        subcause TEXT NOT NULL,
        detected_at TEXT NOT NULL,
        PRIMARY KEY (scope, from_scheduled_pass)
    """,
    "paper_bar_observation": """
        data_symbol TEXT NOT NULL,
        session_date TEXT NOT NULL,
        bar_timestamp TEXT NOT NULL,
        open REAL NOT NULL,
        high REAL NOT NULL,
        low REAL NOT NULL,
        close REAL NOT NULL,
        volume REAL NOT NULL,
        observed_at TEXT NOT NULL,
        provider TEXT NOT NULL,
        request TEXT NOT NULL,
        scale_doubtful INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (data_symbol, session_date, observed_at)
    """,
    "paper_corporate_action": f"""
        data_symbol TEXT NOT NULL,
        kind TEXT NOT NULL {_ref('paper_corporate_action', 'kind')},
        ex_date TEXT NOT NULL,
        amount REAL NOT NULL,
        ratio REAL NOT NULL,
        currency TEXT NOT NULL,
        observed_at TEXT NOT NULL,
        provider TEXT NOT NULL,
        terminal_kind TEXT NOT NULL DEFAULT '' {_ref('paper_corporate_action', 'terminal_kind')},
        source_url TEXT NOT NULL DEFAULT '',
        source_sha256 TEXT NOT NULL DEFAULT '',
        decision_ref TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (data_symbol, kind, ex_date)
    """,
    "paper_corporate_action_revision": """
        data_symbol TEXT NOT NULL,
        kind TEXT NOT NULL,
        ex_date TEXT NOT NULL,
        amount REAL NOT NULL,
        ratio REAL NOT NULL,
        observed_at TEXT NOT NULL,
        PRIMARY KEY (data_symbol, kind, ex_date, observed_at)
    """,
    "paper_fx_quote": """
        fx_pair TEXT NOT NULL,
        bar_timestamp TEXT NOT NULL,
        session_date TEXT NOT NULL,
        timestamp_available TEXT NOT NULL,
        rate REAL NOT NULL,
        provider TEXT NOT NULL,
        observed_at TEXT NOT NULL,
        PRIMARY KEY (fx_pair, bar_timestamp)
    """,
    "paper_context_observation": """
        series TEXT NOT NULL,
        bar_timestamp TEXT NOT NULL,
        close REAL NOT NULL,
        observed_at TEXT NOT NULL,
        provider TEXT NOT NULL,
        PRIMARY KEY (series, bar_timestamp)
    """,
    "paper_data_alert": f"""
        object TEXT NOT NULL,
        kind TEXT NOT NULL {_ref('paper_data_alert', 'kind')},
        session_date TEXT NOT NULL,
        detected_at TEXT NOT NULL,
        PRIMARY KEY (object, kind, session_date)
    """,
    "paper_signal_evaluation": """
        cohort_id TEXT NOT NULL REFERENCES paper_cohort(cohort_id),
        policy_id TEXT NOT NULL,
        signal_id TEXT NOT NULL,
        instrument_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        data_symbol TEXT NOT NULL,
        market TEXT NOT NULL,
        signal_session_date TEXT NOT NULL,
        bar_timestamp TEXT NOT NULL,
        pass_scheduled_ts TEXT NOT NULL,
        analysis_timestamp TEXT NOT NULL,
        decision_ts TEXT NOT NULL,
        reference_price REAL NOT NULL,
        entry_max REAL,
        stop REAL,
        target1 REAL,
        target2 REAL,
        target3 REAL,
        rr_at_reference REAL,
        risk_fraction REAL,
        score REAL,
        score_model_version TEXT NOT NULL,
        setup_radar TEXT NOT NULL,
        setup_accion TEXT NOT NULL,
        operar INTEGER NOT NULL,
        context_json TEXT NOT NULL,
        data_quality TEXT NOT NULL,
        reasons TEXT NOT NULL,
        max_input_observed_at TEXT NOT NULL,
        source_run_id TEXT NOT NULL,
        source_recommendation_id TEXT NOT NULL,
        paper_run_id TEXT NOT NULL,
        content_sha256 TEXT NOT NULL,
        PRIMARY KEY (cohort_id, signal_id, pass_scheduled_ts),
        UNIQUE (cohort_id, instrument_id, signal_session_date, pass_scheduled_ts)
    """,
    "paper_signal_not_evaluated": f"""
        cohort_id TEXT NOT NULL,
        data_symbol TEXT NOT NULL,
        signal_session_date TEXT NOT NULL,
        entry_session TEXT NOT NULL,
        cause TEXT NOT NULL {_ref('paper_signal_not_evaluated', 'cause')},
        detected_at TEXT NOT NULL,
        PRIMARY KEY (cohort_id, data_symbol, signal_session_date)
    """,
    "paper_open_check": f"""
        policy_id TEXT NOT NULL,
        t025_code_sha TEXT NOT NULL,
        signal_id TEXT NOT NULL,
        instrument_id TEXT NOT NULL,
        signal_session_date TEXT NOT NULL,
        entry_session TEXT NOT NULL,
        binding_pass_ts TEXT NOT NULL,
        open_market REAL NOT NULL,
        entry_effective REAL NOT NULL,
        check_code TEXT NOT NULL {_ref('paper_open_check', 'check_code')},
        requested_weight REAL,
        paper_run_id TEXT NOT NULL,
        content_sha256 TEXT NOT NULL,
        PRIMARY KEY (policy_id, t025_code_sha, signal_id)
    """,
    "paper_ledger": """
        cohort_id TEXT NOT NULL REFERENCES paper_cohort(cohort_id),
        seq INTEGER NOT NULL,
        run_seq INTEGER NOT NULL,
        epoch_no INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        timestamp_utc TEXT NOT NULL,
        signal_id TEXT NOT NULL,
        position_id TEXT NOT NULL,
        row_json TEXT NOT NULL,
        content_sha256 TEXT NOT NULL,
        PRIMARY KEY (cohort_id, seq)
    """,
    "paper_signal_disposition": """
        cohort_id TEXT NOT NULL,
        signal_id TEXT NOT NULL,
        event_ts_utc TEXT NOT NULL,
        disposition TEXT NOT NULL,
        ledger_seq INTEGER NOT NULL,
        PRIMARY KEY (cohort_id, signal_id)
    """,
    "paper_order": """
        cohort_id TEXT NOT NULL,
        signal_id TEXT NOT NULL,
        order_type TEXT NOT NULL,
        ledger_seq INTEGER NOT NULL,
        PRIMARY KEY (cohort_id, signal_id)
    """,
    "paper_entry_decision": """
        cohort_id TEXT NOT NULL,
        signal_id TEXT NOT NULL,
        status TEXT NOT NULL,
        event_ts_utc TEXT NOT NULL,
        ledger_seq INTEGER NOT NULL,
        PRIMARY KEY (cohort_id, signal_id)
    """,
    "paper_position": """
        cohort_id TEXT NOT NULL,
        position_id TEXT NOT NULL,
        signal_id TEXT NOT NULL,
        asset TEXT NOT NULL,
        opened_ts_utc TEXT NOT NULL,
        ledger_seq INTEGER NOT NULL,
        PRIMARY KEY (cohort_id, position_id),
        UNIQUE (cohort_id, signal_id)
    """,
    "paper_position_event": """
        cohort_id TEXT NOT NULL,
        event_seq INTEGER NOT NULL,
        run_seq INTEGER NOT NULL,
        epoch_no INTEGER NOT NULL,
        position_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        event_ts_utc TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        content_sha256 TEXT NOT NULL,
        PRIMARY KEY (cohort_id, event_seq)
    """,
    "paper_equity_snapshot": """
        cohort_id TEXT NOT NULL,
        snapshot_day TEXT NOT NULL,
        run_seq INTEGER NOT NULL,
        epoch_no INTEGER NOT NULL,
        equity_eur REAL NOT NULL,
        cash_eur REAL NOT NULL,
        long_value_eur REAL NOT NULL,
        stale_value_eur REAL NOT NULL,
        n_positions INTEGER NOT NULL,
        exposure_json TEXT NOT NULL,
        content_sha256 TEXT NOT NULL,
        PRIMARY KEY (cohort_id, snapshot_day)
    """,
    "paper_trade_outcome": """
        cohort_id TEXT NOT NULL,
        position_id TEXT NOT NULL,
        run_seq INTEGER NOT NULL,
        epoch_no INTEGER NOT NULL,
        entry_session TEXT NOT NULL,
        exit_session TEXT NOT NULL,
        exit_ts_utc TEXT NOT NULL,
        exit_reason TEXT NOT NULL,
        trade_json TEXT NOT NULL,
        mae_R REAL NOT NULL,
        mfe_R REAL NOT NULL,
        content_sha256 TEXT NOT NULL,
        PRIMARY KEY (cohort_id, position_id)
    """,
    "paper_cohort_progress": """
        cohort_id TEXT NOT NULL,
        run_seq INTEGER NOT NULL,
        paper_run_id TEXT NOT NULL,
        frontier_ts_utc TEXT NOT NULL,
        frontier_key TEXT NOT NULL,
        stop_reason TEXT NOT NULL,
        stalled_on TEXT NOT NULL,
        counters_json TEXT NOT NULL,
        state_sha256 TEXT NOT NULL,
        PRIMARY KEY (cohort_id, run_seq)
    """,
    "paper_seal_nonce": """
        cohort_id TEXT NOT NULL,
        paper_run_id TEXT NOT NULL,
        nonce_hex TEXT NOT NULL,
        PRIMARY KEY (cohort_id, paper_run_id)
    """,
    "paper_seal_commitment": """
        cohort_id TEXT NOT NULL,
        paper_run_id TEXT NOT NULL,
        commitment_sha256 TEXT NOT NULL,
        PRIMARY KEY (cohort_id, paper_run_id)
    """,
    "paper_seal_window": f"""
        window_id TEXT NOT NULL,
        revision INTEGER NOT NULL,
        kind TEXT NOT NULL {_ref('paper_seal_window', 'kind')},
        cohorts_json TEXT NOT NULL,
        sessions_from TEXT NOT NULL,
        sessions_to TEXT NOT NULL,
        opened_at TEXT NOT NULL,
        opened_by_ref TEXT NOT NULL,
        closed_at TEXT NOT NULL DEFAULT '',
        closed_by_ref TEXT NOT NULL DEFAULT '',
        closure TEXT NOT NULL DEFAULT '' {_ref('paper_seal_window', 'closure')},
        sessions_status TEXT NOT NULL DEFAULT '' {_ref('paper_seal_window', 'sessions_status')},
        seal_still_active INTEGER NOT NULL DEFAULT 1,
        evidence_sha256 TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (window_id, revision)
    """,
    "paper_outcome_access": f"""
        access_id TEXT PRIMARY KEY,
        cohort_id TEXT NOT NULL,
        accessed_at TEXT NOT NULL,
        who TEXT NOT NULL,
        purpose TEXT NOT NULL,
        access_kind TEXT NOT NULL {_ref('paper_outcome_access', 'access_kind')},
        query TEXT NOT NULL,
        sessions_json TEXT NOT NULL,
        rows_sha256 TEXT NOT NULL
    """,
}


# Caché del estado del motor: NO es un hecho. Una fila por cohorte, reemplazable, verificada contra el
# ``state_sha256`` (append-only) de ``paper_cohort_progress``; si no cuadra, se descarta y se repite desde cero.
CACHE_TABLES: Dict[str, str] = {
    "paper_engine_state_cache": """
        cohort_id TEXT PRIMARY KEY,
        run_seq INTEGER NOT NULL,
        state_json_zlib BLOB NOT NULL,
        state_sha256 TEXT NOT NULL
    """,
}


def _migration_v1() -> List[str]:
    statements: List[str] = []
    for domain, values in REFERENCE_DOMAINS.items():
        statements.append(f"CREATE TABLE paper_ref_{domain} (value TEXT PRIMARY KEY)")
        statements.extend(f"INSERT INTO paper_ref_{domain}(value) VALUES ('{value}')" for value in values)
    for table, body in {**FACT_TABLES, **CACHE_TABLES}.items():
        statements.append(f"CREATE TABLE {table} ({body})")
    for table in [*FACT_TABLES, *(f"paper_ref_{d}" for d in REFERENCE_DOMAINS)]:
        statements.append(
            f"CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT, 'append-only'); END"
        )
        statements.append(
            f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT, 'append-only'); END"
        )
    return statements


MIGRATIONS: Dict[int, Tuple[bool, str, List[str]]] = {
    1: (True, "esquema inicial de engine_v1", _migration_v1()),
}


class SchemaError(RuntimeError):
    """El esquema de ``paper.db`` no es utilizable por este código."""


def migrate(conn: sqlite3.Connection) -> int:
    """Aplica las migraciones pendientes. Un esquema más nuevo solo se acepta si todas sus migraciones
    posteriores a la de este código están registradas como aditivas (§12, ronda 4)."""

    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current > SCHEMA_VERSION:
        rows = conn.execute(
            "SELECT version, additive FROM paper_schema_migration WHERE version > ?", (SCHEMA_VERSION,)
        ).fetchall()
        versions = {int(v): bool(a) for v, a in rows}
        expected = set(range(SCHEMA_VERSION + 1, current + 1))
        if set(versions) != expected or not all(versions.values()):
            raise SchemaError(f"paper.db en esquema {current}: alguna migración posterior a {SCHEMA_VERSION} no es aditiva")
        return current
    for version in range(current + 1, SCHEMA_VERSION + 1):
        additive, description, statements = MIGRATIONS[version]
        conn.execute("BEGIN IMMEDIATE")
        try:
            for statement in statements:
                conn.execute(statement)
            conn.execute(
                "INSERT INTO paper_schema_migration(version, additive, description) VALUES (?, ?, ?)",
                (version, int(additive), description),
            )
            conn.execute(f"PRAGMA user_version = {version}")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
    return SCHEMA_VERSION
