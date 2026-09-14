"""Persistencia SQLite del asesor.

Tablas:

- ``recommendation``: una fila por activo y ejecución. Es el registro
  histórico de lo que el bot recomendó y con qué números, para poder
  auditarlo después.
- ``position``: posiciones abiertas manualmente en Trade Republic, con la
  tesis original. Una vez abierta una posición, el seguimiento se hace contra
  esa tesis y no se vuelve a analizar el activo desde cero.
- ``position_review``: cada revisión de una posición abierta y su veredicto.
- ``event_pass``: deduplicación de pasadas despertadas por eventos conocidos.
- ``data_freshness_measurement``: frescura y sesiones ausentes por pasada.

Los importes se guardan en euros cuando hay tipo de cambio (``*_eur``) y
siempre también en la divisa nativa, para que un fallo de conversión no
pierda el dato original.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

from advisor.run.manifest import RunManifest
from advisor.storage.migrations import MIGRATIONS, run_migration, table_exists

VERDICTS = ("REFUERZA", "NO CAMBIA", "DEBILITA", "INVALIDA")
logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS recommendation (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    name            TEXT NOT NULL,
    isin            TEXT,
    trade_republic  TEXT NOT NULL,
    currency        TEXT NOT NULL,
    horizonte       TEXT NOT NULL,
    radar           TEXT NOT NULL,
    accion          TEXT NOT NULL,
    score           REAL NOT NULL,
    evaluable_max   REAL NOT NULL,
    price           REAL NOT NULL,
    price_eur       REAL,
    entry_max       REAL NOT NULL,
    entry_max_eur   REAL,
    stop            REAL NOT NULL,
    stop_eur        REAL,
    target2         REAL NOT NULL,
    target2_eur     REAL,
    risk_pct        REAL NOT NULL,
    reward_pct      REAL NOT NULL,
    rr_ratio        REAL NOT NULL,
    reasons         TEXT
);

CREATE INDEX IF NOT EXISTS idx_recommendation_symbol ON recommendation(symbol, created_at);

CREATE TABLE IF NOT EXISTS position (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT NOT NULL,
    name            TEXT NOT NULL,
    opened_at       TEXT NOT NULL,
    entry_price     REAL NOT NULL,
    currency        TEXT NOT NULL,
    quantity        REAL NOT NULL,
    invested_eur    REAL,
    thesis          TEXT NOT NULL,
    target          REAL,
    stop            REAL,
    horizonte       TEXT NOT NULL,
    catalyst        TEXT,
    status          TEXT NOT NULL DEFAULT 'OPEN',
    closed_at       TEXT,
    exit_price      REAL,
    close_reason    TEXT
);

CREATE INDEX IF NOT EXISTS idx_position_status ON position(status, symbol);

CREATE TABLE IF NOT EXISTS position_review (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id     INTEGER NOT NULL REFERENCES position(id),
    created_at      TEXT NOT NULL,
    price           REAL NOT NULL,
    pnl_pct         REAL NOT NULL,
    score           REAL,
    verdict         TEXT NOT NULL,
    note            TEXT,
    UNIQUE(position_id, created_at)
);

CREATE TABLE IF NOT EXISTS event_pass (
    event_id        TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL,
    event_date      TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    event_scope     TEXT NOT NULL,
    symbol          TEXT,
    horizonte       TEXT NOT NULL,
    pass_kind       TEXT NOT NULL,
    title           TEXT NOT NULL,
    status          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_event_pass_date ON event_pass(event_date, pass_kind);

CREATE TABLE IF NOT EXISTS data_freshness_measurement (
    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    measured_at                     TEXT NOT NULL,
    symbol                          TEXT NOT NULL,
    data_symbol                     TEXT NOT NULL,
    market                          TEXT NOT NULL,
    benchmark_symbol                TEXT,
    last_bar_date                   TEXT,
    natural_days                    INTEGER,
    sessions_approx                INTEGER,
    may_be_partial_current_session  INTEGER NOT NULL,
    absent_reference_sessions       TEXT NOT NULL,
    absent_recent_sessions          TEXT NOT NULL,
    reference_sessions_checked      INTEGER NOT NULL,
    veto_window_sessions            INTEGER NOT NULL,
    quality                         TEXT NOT NULL,
    error                           TEXT
);

CREATE INDEX IF NOT EXISTS idx_data_freshness_symbol
ON data_freshness_measurement(symbol, measured_at);
"""


class AdvisorDB:
    """Acceso a la base de datos del asesor."""

    def __init__(self, path: str | Path = "intradia.db", *, readonly: bool = False) -> None:
        """Abre (o crea) la base y aplica migraciones pendientes.

        Con ``readonly=True`` la base se abre con ``mode=ro`` y **no** se crea,
        migra ni respalda nada: es el modo de los comandos de consulta
        (``manifiesto``, ``verificar-backup``), que no deben cambiar el esquema
        de producción ni fabricar una base vacía si la ruta está mal.
        """

        self.path = str(path)
        self.readonly = readonly
        self._memory_connection: Optional[sqlite3.Connection] = None
        if readonly:
            if self.path != ":memory:" and not Path(self.path).is_file():
                raise FileNotFoundError(f"base de datos no encontrada: {self.path}")
            return
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if self.path == ":memory:":
            if self._memory_connection is None:
                self._memory_connection = sqlite3.connect(self.path)
                self._memory_connection.row_factory = sqlite3.Row
            connection = self._memory_connection
            close = False
        elif self.readonly:
            connection = sqlite3.connect(f"file:{Path(self.path).resolve()}?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            close = True
        else:
            connection = sqlite3.connect(self.path)
            connection.row_factory = sqlite3.Row
            close = True
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            if close:
                connection.close()

    def _init_schema(self) -> None:
        with self._connect() as connection:
            existing_file = self._is_existing_file()
            self._ensure_backup_log(connection)
            current = self._mark_or_create_base_schema(connection)
            for version, description, migrate in MIGRATIONS:
                if version <= current:
                    continue
                if existing_file:
                    self._backup_before_migration(connection, version, description)
                run_migration(connection, version, migrate)
                current = version

    def _is_existing_file(self) -> bool:
        if self.path == ":memory:" or self.path.startswith("file:"):
            return False
        path = Path(self.path)
        return path.exists() and path.stat().st_size > 0

    def _ensure_backup_log(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS backup_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                backup_path     TEXT NOT NULL,
                created_at      TEXT NOT NULL,
                target_version  INTEGER NOT NULL,
                table_name      TEXT NOT NULL,
                row_count       INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_backup_log_path ON backup_log(backup_path, table_name)"
        )

    def _mark_or_create_base_schema(self, connection: sqlite3.Connection) -> int:
        current = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if current == 0 and table_exists(connection, "recommendation"):
            connection.execute("PRAGMA user_version = 1")
            return 1
        if current == 0:
            connection.executescript(_SCHEMA)
            connection.execute("PRAGMA user_version = 1")
            return 1
        return current

    def _backup_before_migration(
        self,
        connection: sqlite3.Connection,
        target_version: int,
        description: str,
    ) -> Path:
        source = Path(self.path)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup_path = source.with_name(f"{source.name}.bak-{timestamp}-pre-v{target_version}").resolve()
        counts = _table_counts(connection)
        if connection.in_transaction:
            connection.commit()
        backup = sqlite3.connect(backup_path)
        try:
            connection.backup(backup)
        finally:
            backup.close()
        created_at = datetime.now(timezone.utc).isoformat()
        connection.executemany(
            """
            INSERT INTO backup_log (backup_path, created_at, target_version, table_name, row_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (str(backup_path), created_at, target_version, table_name, count)
                for table_name, count in counts.items()
            ],
        )
        logger.info("Backup previo a migración v%d (%s): %s", target_version, description, backup_path)
        return backup_path

    def schema_version(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("PRAGMA user_version").fetchone()[0])

    # -- Recomendaciones ---------------------------------------------------

    def insert_recommendations(self, rows: Iterable[Dict[str, Any]]) -> int:
        """Guarda las recomendaciones de una ejecución. Devuelve cuántas se insertaron."""

        rows = [dict(row) for row in rows]
        if not rows:
            return 0
        for row in rows:
            if not row.get("run_id"):
                raise ValueError("run_id es obligatorio para recomendaciones nuevas")

        columns = [
            "created_at", "symbol", "name", "isin", "trade_republic", "currency", "horizonte",
            "radar", "accion", "score", "evaluable_max", "price", "price_eur", "entry_max",
            "entry_max_eur", "stop", "stop_eur", "target2", "target2_eur", "risk_pct",
            "reward_pct", "rr_ratio", "reasons", "run_id",
        ]
        placeholders = ", ".join(f":{c}" for c in columns)
        sql = f"INSERT INTO recommendation ({', '.join(columns)}) VALUES ({placeholders})"

        with self._connect() as connection:
            connection.executemany(sql, rows)
        return len(rows)

    def insert_analysis_run(self, manifest: RunManifest) -> None:
        row = manifest.to_row()
        columns = [
            "run_id", "command", "git_sha", "git_dirty", "config_hash", "universe_vintage_id",
            "data_vintage_id", "score_model_version", "context_model_version", "schema_version",
            "analysis_timestamp", "environment", "python_version", "provider_versions",
            "clock_drift_seconds", "clock_status",
        ]
        placeholders = ", ".join(f":{column}" for column in columns)
        sql = f"INSERT INTO analysis_run ({', '.join(columns)}) VALUES ({placeholders})"
        with self._connect() as connection:
            connection.execute(sql, row)

    def insert_analysis_result(
        self,
        manifest: RunManifest,
        recommendation_rows: Iterable[Dict[str, Any]],
        freshness_rows: Iterable[Dict[str, Any]],
    ) -> tuple[int, int]:
        recommendations = [dict(row, run_id=manifest.run_id) for row in recommendation_rows]
        freshness = [
            freshness_measurement_to_row(dict(row, run_id=manifest.run_id))
            for row in freshness_rows
        ]
        with self._connect() as connection:
            self._insert_analysis_run(connection, manifest)
            recommendation_count = self._insert_recommendations(connection, recommendations)
            freshness_count = self._insert_freshness_measurements(connection, freshness)
        return recommendation_count, freshness_count

    def _insert_analysis_run(self, connection: sqlite3.Connection, manifest: RunManifest) -> None:
        row = manifest.to_row()
        columns = [
            "run_id", "command", "git_sha", "git_dirty", "config_hash", "universe_vintage_id",
            "data_vintage_id", "score_model_version", "context_model_version", "schema_version",
            "analysis_timestamp", "environment", "python_version", "provider_versions",
            "clock_drift_seconds", "clock_status",
        ]
        placeholders = ", ".join(f":{column}" for column in columns)
        sql = f"INSERT INTO analysis_run ({', '.join(columns)}) VALUES ({placeholders})"
        connection.execute(sql, row)

    def _insert_recommendations(
        self,
        connection: sqlite3.Connection,
        rows: List[Dict[str, Any]],
    ) -> int:
        if not rows:
            return 0
        columns = [
            "created_at", "symbol", "name", "isin", "trade_republic", "currency", "horizonte",
            "radar", "accion", "score", "evaluable_max", "price", "price_eur", "entry_max",
            "entry_max_eur", "stop", "stop_eur", "target2", "target2_eur", "risk_pct",
            "reward_pct", "rr_ratio", "reasons", "run_id",
        ]
        placeholders = ", ".join(f":{c}" for c in columns)
        sql = f"INSERT INTO recommendation ({', '.join(columns)}) VALUES ({placeholders})"
        connection.executemany(sql, rows)
        return len(rows)

    def get_recent_recommendations(self, symbol: Optional[str] = None, limit: int = 50) -> List[sqlite3.Row]:
        """Últimas recomendaciones, opcionalmente filtradas por símbolo."""

        with self._connect() as connection:
            if symbol:
                cursor = connection.execute(
                    "SELECT * FROM recommendation WHERE symbol = ? ORDER BY created_at DESC, id DESC LIMIT ?",
                    (symbol.upper(), limit),
                )
            else:
                cursor = connection.execute(
                    "SELECT * FROM recommendation ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)
                )
            return cursor.fetchall()

    # -- Frescura de datos ------------------------------------------------

    def insert_freshness_measurements(self, rows: Iterable[Dict[str, Any]]) -> int:
        """Guarda mediciones de frescura de una pasada."""

        rows = [freshness_measurement_to_row(row) for row in rows]
        if not rows:
            return 0
        for row in rows:
            if not row.get("run_id"):
                raise ValueError("run_id es obligatorio para mediciones de frescura nuevas")

        columns = [
            "measured_at", "symbol", "data_symbol", "market", "benchmark_symbol",
            "last_bar_date", "natural_days", "sessions_approx", "may_be_partial_current_session",
            "absent_reference_sessions", "absent_recent_sessions", "reference_sessions_checked",
            "veto_window_sessions", "quality", "error", "run_id",
        ]
        placeholders = ", ".join(f":{column}" for column in columns)
        sql = f"INSERT INTO data_freshness_measurement ({', '.join(columns)}) VALUES ({placeholders})"

        with self._connect() as connection:
            connection.executemany(sql, rows)
        return len(rows)

    def _insert_freshness_measurements(
        self,
        connection: sqlite3.Connection,
        rows: List[Dict[str, Any]],
    ) -> int:
        if not rows:
            return 0
        columns = [
            "measured_at", "symbol", "data_symbol", "market", "benchmark_symbol",
            "last_bar_date", "natural_days", "sessions_approx", "may_be_partial_current_session",
            "absent_reference_sessions", "absent_recent_sessions", "reference_sessions_checked",
            "veto_window_sessions", "quality", "error", "run_id",
        ]
        placeholders = ", ".join(f":{column}" for column in columns)
        sql = f"INSERT INTO data_freshness_measurement ({', '.join(columns)}) VALUES ({placeholders})"
        connection.executemany(sql, rows)
        return len(rows)

    def get_recent_freshness_measurements(
        self,
        symbol: Optional[str] = None,
        limit: int = 50,
    ) -> List[sqlite3.Row]:
        """Últimas mediciones de frescura, opcionalmente filtradas por símbolo."""

        with self._connect() as connection:
            if symbol:
                cursor = connection.execute(
                    """
                    SELECT * FROM data_freshness_measurement
                    WHERE symbol = ?
                    ORDER BY measured_at DESC, id DESC
                    LIMIT ?
                    """,
                    (symbol.strip().upper(), limit),
                )
            else:
                cursor = connection.execute(
                    """
                    SELECT * FROM data_freshness_measurement
                    ORDER BY measured_at DESC, id DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            return cursor.fetchall()

    def get_analysis_run(self, run_id: str) -> Optional[sqlite3.Row]:
        with self._connect() as connection:
            cursor = connection.execute("SELECT * FROM analysis_run WHERE run_id = ?", (run_id,))
            return cursor.fetchone()

    def get_recommendations_for_run(self, run_id: str) -> List[sqlite3.Row]:
        with self._connect() as connection:
            cursor = connection.execute(
                "SELECT * FROM recommendation WHERE run_id = ? ORDER BY id",
                (run_id,),
            )
            return cursor.fetchall()

    # -- Pasadas por evento ---------------------------------------------------

    def claim_event_passes(self, rows: Iterable[Dict[str, Any]]) -> List[str]:
        """Registra intentos reintentables y devuelve los que aún no se enviaron."""

        claimed: List[str] = []
        timestamp = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            for row in rows:
                event_id = row["event_id"]
                existing = connection.execute(
                    "SELECT status FROM event_pass WHERE event_id = ?",
                    (event_id,),
                ).fetchone()
                if existing is not None and existing["status"] == "SENT":
                    continue
                connection.execute(
                    """
                    INSERT OR REPLACE INTO event_pass (
                        event_id, created_at, event_date, event_type, event_scope,
                        symbol, horizonte, pass_kind, title, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'CLAIMED')
                    """,
                    (
                        event_id,
                        timestamp,
                        row["event_date"],
                        row["event_type"],
                        row["event_scope"],
                        row.get("symbol"),
                        row["horizonte"],
                        row["pass_kind"],
                        row["title"],
                    ),
                )
                claimed.append(event_id)
        return claimed

    def mark_event_passes_sent(self, event_ids: Iterable[str]) -> None:
        """Marca como completadas las pasadas reservadas por ID determinista."""

        ids = list(event_ids)
        if not ids:
            return
        with self._connect() as connection:
            connection.executemany(
                "UPDATE event_pass SET status = 'SENT' WHERE event_id = ?",
                [(event_id,) for event_id in ids],
            )

    def get_event_pass(self, event_id: str) -> Optional[sqlite3.Row]:
        with self._connect() as connection:
            cursor = connection.execute("SELECT * FROM event_pass WHERE event_id = ?", (event_id,))
            return cursor.fetchone()

    # -- Posiciones --------------------------------------------------------

    def open_position(
        self,
        *,
        symbol: str,
        name: str,
        entry_price: float,
        currency: str,
        quantity: float,
        thesis: str,
        horizonte: str,
        invested_eur: Optional[float] = None,
        target: Optional[float] = None,
        stop: Optional[float] = None,
        catalyst: Optional[str] = None,
        opened_at: Optional[datetime] = None,
    ) -> int:
        """Registra una posición abierta manualmente. Devuelve su ``id``.

        Lanza ``ValueError`` si ya existe una posición abierta para el mismo
        símbolo: el seguimiento de una tesis asume una posición por activo.
        """

        if entry_price <= 0:
            raise ValueError(f"entry_price debe ser > 0, recibido: {entry_price}")
        if quantity <= 0:
            raise ValueError(f"quantity debe ser > 0, recibido: {quantity}")
        if not thesis.strip():
            raise ValueError("thesis no puede estar vacía: sin tesis no hay nada que seguir")

        symbol = symbol.strip().upper()
        if self.get_open_position(symbol) is not None:
            raise ValueError(f"ya existe una posición abierta en {symbol}; ciérrala antes de abrir otra")

        timestamp = (opened_at or datetime.now(timezone.utc)).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO position (
                    symbol, name, opened_at, entry_price, currency, quantity, invested_eur,
                    thesis, target, stop, horizonte, catalyst, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')
                """,
                (
                    symbol, name, timestamp, entry_price, currency.upper(), quantity, invested_eur,
                    thesis.strip(), target, stop, horizonte, catalyst,
                ),
            )
            position_id = cursor.lastrowid
            if position_id is None:
                raise RuntimeError(f"{symbol}: SQLite no devolvió identificador al registrar la posición")
            return position_id

    def get_open_position(self, symbol: str) -> Optional[sqlite3.Row]:
        with self._connect() as connection:
            cursor = connection.execute(
                "SELECT * FROM position WHERE symbol = ? AND status = 'OPEN'", (symbol.strip().upper(),)
            )
            return cursor.fetchone()

    def list_open_positions(self) -> List[sqlite3.Row]:
        with self._connect() as connection:
            cursor = connection.execute("SELECT * FROM position WHERE status = 'OPEN' ORDER BY opened_at")
            return cursor.fetchall()

    def close_position(
        self,
        symbol: str,
        exit_price: float,
        reason: str,
        closed_at: Optional[datetime] = None,
    ) -> None:
        """Cierra la posición abierta de ``symbol``."""

        if exit_price <= 0:
            raise ValueError(f"exit_price debe ser > 0, recibido: {exit_price}")

        symbol = symbol.strip().upper()
        if self.get_open_position(symbol) is None:
            raise ValueError(f"no hay ninguna posición abierta en {symbol}")

        timestamp = (closed_at or datetime.now(timezone.utc)).isoformat()
        with self._connect() as connection:
            connection.execute(
                "UPDATE position SET status = 'CLOSED', closed_at = ?, exit_price = ?, close_reason = ? "
                "WHERE symbol = ? AND status = 'OPEN'",
                (timestamp, exit_price, reason, symbol),
            )

    # -- Revisiones --------------------------------------------------------

    def insert_review(
        self,
        *,
        position_id: int,
        price: float,
        pnl_pct: float,
        verdict: str,
        score: Optional[float] = None,
        note: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> None:
        """Registra la revisión de una posición abierta."""

        if verdict not in VERDICTS:
            raise ValueError(f"verdict inválido: '{verdict}'. Permitidos: {list(VERDICTS)}")

        timestamp = (created_at or datetime.now(timezone.utc)).isoformat()
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO position_review "
                "(position_id, created_at, price, pnl_pct, score, verdict, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (position_id, timestamp, price, pnl_pct, score, verdict, note),
            )

    def get_reviews(self, position_id: int, limit: int = 20) -> List[sqlite3.Row]:
        with self._connect() as connection:
            cursor = connection.execute(
                "SELECT * FROM position_review WHERE position_id = ? ORDER BY created_at DESC LIMIT ?",
                (position_id, limit),
            )
            return cursor.fetchall()


def freshness_measurement_to_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Convierte una medición de frescura a tipos persistibles en SQLite."""

    absent = row.get("absent_reference_sessions") or ()
    absent_recent = row.get("absent_recent_sessions") or ()
    return {
        **row,
        "may_be_partial_current_session": int(bool(row.get("may_be_partial_current_session"))),
        "absent_reference_sessions": json.dumps(list(absent), ensure_ascii=False),
        "absent_recent_sessions": json.dumps(list(absent_recent), ensure_ascii=False),
    }


def verify_backup(db_path: str | Path, backup_path: str | Path) -> bool:
    """Comprueba integridad y conteos registrados para un backup."""

    backup = Path(backup_path)
    if not backup.is_file():
        return False
    try:
        with sqlite3.connect(f"file:{backup}?mode=ro", uri=True) as backup_conn:
            integrity = backup_conn.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                return False
            backup_counts = _table_counts(backup_conn)
    except sqlite3.DatabaseError:
        return False

    # La base viva se abre en solo lectura: verificar un backup no puede
    # migrar producción ni crear una base vacía si la ruta está mal.
    try:
        live = AdvisorDB(db_path, readonly=True)
        with live._connect() as live_conn:
            if not table_exists(live_conn, "backup_log"):
                return False
            logged_rows = live_conn.execute(
                "SELECT backup_path, table_name, row_count FROM backup_log"
            ).fetchall()
    except (sqlite3.DatabaseError, FileNotFoundError):
        return False

    # Las rutas se comparan resueltas: el registro puede ser relativo (config
    # con ``db_path: intradia.db``) y el operador pasar la absoluta, o al revés.
    target = backup.resolve()
    expected = {
        row["table_name"]: int(row["row_count"])
        for row in logged_rows
        if Path(row["backup_path"]).resolve() == target
    }
    if not expected:
        return False
    return all(backup_counts.get(table_name, -1) >= row_count for table_name, row_count in expected.items())


def _table_counts(connection: sqlite3.Connection) -> dict[str, int]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
          AND name != 'backup_log'
        ORDER BY name
        """
    ).fetchall()
    counts: dict[str, int] = {}
    for row in rows:
        table_name = row["name"] if isinstance(row, sqlite3.Row) else row[0]
        quoted = table_name.replace('"', '""')
        counts[table_name] = int(connection.execute(f'SELECT count(*) FROM "{quoted}"').fetchone()[0])
    return counts
