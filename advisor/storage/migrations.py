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
        # Las advertencias no descartan, así que no viajan en `reasons`. Al
        # sacarlas de ahí dejaron de persistirse: el aviso de precio extendido
        # se guardaba antes dentro de los motivos y desapareció de la base.
        "ALTER TABLE recommendation ADD COLUMN warnings TEXT",
        "ALTER TABLE data_freshness_measurement ADD COLUMN quality_freshness TEXT",
        "ALTER TABLE data_freshness_measurement ADD COLUMN quality_recent TEXT",
        "ALTER TABLE data_freshness_measurement ADD COLUMN quality_historical TEXT",
        "ALTER TABLE data_freshness_measurement ADD COLUMN execution_ready INTEGER",
        "ALTER TABLE data_freshness_measurement ADD COLUMN quality_period TEXT",
        "ALTER TABLE data_freshness_measurement ADD COLUMN quality_interval TEXT",
    )
    for statement in statements:
        conn.execute(statement)


# `backup_log` era la única tabla que se creaba fuera de esta lista, en cada
# apertura de la base (`_ensure_backup_log`). Inocuo mientras nadie la cambiara,
# pero contradecía INV-17: el esquema es lo que dicen las migraciones, no lo que
# ejecute un método de conveniencia. Ahora la DDL vive aquí, la usan el esquema
# base (bases nuevas) y la migración v5 (bases que ya existían), y es idempotente
# en las dos.
BACKUP_LOG_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS backup_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        backup_path     TEXT NOT NULL,
        created_at      TEXT NOT NULL,
        target_version  INTEGER NOT NULL,
        table_name      TEXT NOT NULL,
        row_count       INTEGER NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_backup_log_path ON backup_log(backup_path, table_name)",
)


# Columnas del manifiesto, en el orden en que las escribe la migración v5.
ANALYSIS_RUN_COLUMNS: tuple[str, ...] = (
    "run_id",
    "command",
    "git_sha",
    "git_dirty",
    "git_dirty_reason",
    "release_tag",
    "config_hash",
    "config_hash_version",
    "universe_vintage_id",
    "groups",
    "data_vintage_id",
    "score_model_version",
    "context_model_version",
    "schema_version",
    "analysis_timestamp",
    "environment",
    "python_version",
    "provider_versions",
    "clock_drift_seconds",
    "clock_status",
)

_ANALYSIS_RUN_V5 = """
CREATE TABLE analysis_run_v5 (
    run_id                  TEXT PRIMARY KEY,
    command                 TEXT NOT NULL,
    git_sha                 TEXT NOT NULL,
    git_dirty               INTEGER,
    git_dirty_reason        TEXT,
    release_tag             TEXT,
    config_hash             TEXT NOT NULL,
    config_hash_version     INTEGER NOT NULL DEFAULT 1,
    universe_vintage_id     TEXT NOT NULL,
    groups                  TEXT,
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
"""


def _migration_v5_manifest_hygiene(conn: sqlite3.Connection) -> None:
    """Higiene del manifiesto: `git_dirty` nullable, tag, versión del hash y grupos.

    `git_dirty` nace `NOT NULL`, y SQLite no sabe aflojar una restricción de
    columna: hay que reconstruir la tabla. Se hace con la receta oficial —tabla
    nueva, copia, borrado, renombrado— dentro de la transacción de la migración,
    así que o entra entera o no entra.

    Las filas que ya existen conservan su `config_hash` y se marcan con
    `config_hash_version = 1`: ese hash se calculó con las rutas dentro y
    recalcularlo sería inventarse un dato que nadie midió (D-33).
    """

    for statement in BACKUP_LOG_STATEMENTS:
        conn.execute(statement)

    conn.execute(_ANALYSIS_RUN_V5)
    conn.execute(
        """
        INSERT INTO analysis_run_v5 (
            run_id, command, git_sha, git_dirty, git_dirty_reason, release_tag,
            config_hash, config_hash_version, universe_vintage_id, groups,
            data_vintage_id, score_model_version, context_model_version, schema_version,
            analysis_timestamp, environment, python_version, provider_versions,
            clock_drift_seconds, clock_status
        )
        SELECT
            run_id, command, git_sha, git_dirty, NULL, NULL,
            config_hash, 1, universe_vintage_id, NULL,
            data_vintage_id, score_model_version, context_model_version, schema_version,
            analysis_timestamp, environment, python_version, provider_versions,
            clock_drift_seconds, clock_status
        FROM analysis_run
        """
    )
    conn.execute("DROP TABLE analysis_run")
    conn.execute("ALTER TABLE analysis_run_v5 RENAME TO analysis_run")


MIGRATIONS: list[Migration] = [
    (2, "analysis_run y run_id en recomendaciones/frescura", _migration_v2_runs),
    (3, "calendar en mediciones de frescura", _migration_v3_freshness_calendar),
    (4, "calidad del dato por dimensiones y códigos estructurados", _migration_v4_data_quality_codes),
    (5, "manifiesto: git_dirty nullable, release_tag, version del hash, grupos y backup_log versionada", _migration_v5_manifest_hygiene),
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
