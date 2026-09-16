"""Migraciones versionadas de la base SQLite del asesor.

Cada migración se aplica dentro de una transacción explícita junto con el
``PRAGMA user_version`` que la marca como hecha: o entra entera o no entra.
Sin eso, un corte entre dos ``ALTER TABLE`` dejaría la base con el esquema a
medias y la versión antigua, y cada apertura posterior volvería a intentar la
migración y fallaría con ``duplicate column``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

Migration = tuple[int, str, Callable[[sqlite3.Connection], None]]


def _migration_v2_runs(conn: sqlite3.Connection) -> None:
    statements = (
        """
        CREATE TABLE IF NOT EXISTS analysis_run (
            run_id                  TEXT PRIMARY KEY,
            command                 TEXT NOT NULL,
            git_sha                 TEXT NOT NULL,
            git_dirty               INTEGER NOT NULL,
            config_hash             TEXT NOT NULL,
            universe_vintage_id     TEXT NOT NULL,
            data_vintage_id         TEXT,
            score_model_version     TEXT NOT NULL,
            context_model_version   TEXT,
            schema_version          INTEGER NOT NULL,
            analysis_timestamp      TEXT NOT NULL,
            environment             TEXT NOT NULL,
            python_version          TEXT NOT NULL,
            provider_versions       TEXT NOT NULL,
            clock_drift_seconds     REAL,
            clock_status            TEXT NOT NULL
        )
        """,
        "ALTER TABLE recommendation ADD COLUMN run_id TEXT",
        "ALTER TABLE data_freshness_measurement ADD COLUMN run_id TEXT",
        "CREATE INDEX IF NOT EXISTS idx_recommendation_run_id ON recommendation(run_id)",
        "CREATE INDEX IF NOT EXISTS idx_data_freshness_run_id ON data_freshness_measurement(run_id)",
    )
    for statement in statements:
        conn.execute(statement)


def _migration_v3_freshness_calendar(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE data_freshness_measurement ADD COLUMN calendar TEXT")


def _migration_v4_data_quality_codes(conn: sqlite3.Connection) -> None:
    statements = (
        "ALTER TABLE recommendation ADD COLUMN discard_code TEXT",
        "ALTER TABLE recommendation ADD COLUMN execution_code TEXT",
        "ALTER TABLE recommendation ADD COLUMN quality_freshness TEXT",
        "ALTER TABLE recommendation ADD COLUMN quality_recent TEXT",
        "ALTER TABLE recommendation ADD COLUMN quality_historical TEXT",
        "ALTER TABLE recommendation ADD COLUMN execution_ready INTEGER",
        "ALTER TABLE recommendation ADD COLUMN quality_period TEXT",
        "ALTER TABLE recommendation ADD COLUMN quality_interval TEXT",
        "ALTER TABLE data_freshness_measurement ADD COLUMN quality_freshness TEXT",
        "ALTER TABLE data_freshness_measurement ADD COLUMN quality_recent TEXT",
        "ALTER TABLE data_freshness_measurement ADD COLUMN quality_historical TEXT",
        "ALTER TABLE data_freshness_measurement ADD COLUMN execution_ready INTEGER",
        "ALTER TABLE data_freshness_measurement ADD COLUMN quality_period TEXT",
        "ALTER TABLE data_freshness_measurement ADD COLUMN quality_interval TEXT",
    )
    for statement in statements:
        conn.execute(statement)


MIGRATIONS: list[Migration] = [
    (2, "analysis_run y run_id en recomendaciones/frescura", _migration_v2_runs),
    (3, "calendar en mediciones de frescura", _migration_v3_freshness_calendar),
    (4, "calidad del dato por dimensiones y códigos estructurados", _migration_v4_data_quality_codes),
]


LATEST_VERSION = MIGRATIONS[-1][0]


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def run_migration(conn: sqlite3.Connection, version: int, migrate: Callable[[sqlite3.Connection], None]) -> None:
    """Aplica una migración y su ``user_version`` como una sola transacción.

    ``executescript`` no sirve aquí: hace commit de lo pendiente y ejecuta en
    autocommit, así que dos ``ALTER TABLE`` no forman una unidad. SQLite sí
    admite DDL transaccional y ``PRAGMA user_version`` se revierte con el
    ``ROLLBACK``.
    """

    if conn.in_transaction:
        conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        migrate(conn)
        conn.execute(f"PRAGMA user_version = {int(version)}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Aplica las migraciones pendientes sobre una conexión abierta."""

    current = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if current == 0 and table_exists(conn, "recommendation"):
        conn.execute("PRAGMA user_version = 1")
        current = 1

    for version, _description, migrate in MIGRATIONS:
        if version <= current:
            continue
        run_migration(conn, version, migrate)
        current = version
