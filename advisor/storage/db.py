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
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

from advisor.run.manifest import RunManifest
from advisor.storage.migrations import (
    ANALYSIS_RUN_COLUMNS,
    BACKUP_LOG_STATEMENTS,
    MIGRATIONS,
    run_migration,
    table_exists,
)

VERDICTS = ("REFUERZA", "NO CAMBIA", "DEBILITA", "INVALIDA")

_ANALYSIS_RUN_INSERT = (
    f"INSERT INTO analysis_run ({', '.join(ANALYSIS_RUN_COLUMNS)}) "
    f"VALUES ({', '.join(f':{column}' for column in ANALYSIS_RUN_COLUMNS)})"
)
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
            current = self._mark_or_create_base_schema(connection)
            if existing_file and not table_exists(connection, "backup_log"):
                # Una base anterior a `backup_log` (v2, v3 o v4 sin ella) migra
                # con respaldo previo, y el respaldo necesita dónde anotarse.
                # Es la misma DDL de la migración, no una definición aparte.
                for statement in BACKUP_LOG_STATEMENTS:
                    connection.execute(statement)
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

    def _mark_or_create_base_schema(self, connection: sqlite3.Connection) -> int:
        """Lleva una base sin versionar a la v1, creando el esquema si hace falta.

        `backup_log` forma parte de la v1 porque el respaldo previo a la
        primera migración necesita dónde anotarse. Las bases que ya pasaron de
        ahí la reciben en la migración v5, que es idempotente.
        """

        current = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if current != 0:
            return current
        if not table_exists(connection, "recommendation"):
            connection.executescript(_SCHEMA)
        for statement in BACKUP_LOG_STATEMENTS:
            connection.execute(statement)
        connection.execute("PRAGMA user_version = 1")
        return 1

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
        if not table_exists(connection, "backup_log"):
            # Una base anterior a `backup_log` sigue mereciendo su copia: lo que
            # se pierde es el registro, y `verificar-backup` ya sabe comprobar
            # una copia no registrada por integridad y conteos.
            logger.warning(
                "Backup previo a v%d sin registrar: la base no tiene backup_log (%s)",
                target_version,
                backup_path,
            )
            return backup_path
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
            _add_recommendation_quality_defaults(row)

        columns = [
            "created_at", "symbol", "name", "isin", "trade_republic", "currency", "horizonte",
            "radar", "accion", "score", "evaluable_max", "price", "price_eur", "entry_max",
            "entry_max_eur", "stop", "stop_eur", "target2", "target2_eur", "risk_pct",
            "reward_pct", "rr_ratio", "reasons", "run_id",
            "discard_code", "execution_code", "quality_freshness", "quality_recent",
            "quality_historical", "execution_ready", "quality_period", "quality_interval",
            "warnings",
        ]
        placeholders = ", ".join(f":{c}" for c in columns)
        sql = f"INSERT INTO recommendation ({', '.join(columns)}) VALUES ({placeholders})"

        with self._connect() as connection:
            connection.executemany(sql, rows)
        return len(rows)

    def insert_analysis_run(self, manifest: RunManifest) -> None:
        row = manifest.to_row()
        sql = _ANALYSIS_RUN_INSERT
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
        sql = _ANALYSIS_RUN_INSERT
        connection.execute(sql, row)

    def _insert_recommendations(
        self,
        connection: sqlite3.Connection,
        rows: List[Dict[str, Any]],
    ) -> int:
        if not rows:
            return 0
        for row in rows:
            _add_recommendation_quality_defaults(row)
        columns = [
            "created_at", "symbol", "name", "isin", "trade_republic", "currency", "horizonte",
            "radar", "accion", "score", "evaluable_max", "price", "price_eur", "entry_max",
            "entry_max_eur", "stop", "stop_eur", "target2", "target2_eur", "risk_pct",
            "reward_pct", "rr_ratio", "reasons", "run_id",
            "discard_code", "execution_code", "quality_freshness", "quality_recent",
            "quality_historical", "execution_ready", "quality_period", "quality_interval",
            "warnings",
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
            "measured_at", "symbol", "data_symbol", "market", "benchmark_symbol", "calendar",
            "last_bar_date", "natural_days", "sessions_approx", "may_be_partial_current_session",
            "absent_reference_sessions", "absent_recent_sessions", "reference_sessions_checked",
            "veto_window_sessions", "quality", "error", "run_id",
            "quality_freshness", "quality_recent", "quality_historical", "execution_ready",
            "quality_period", "quality_interval",
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
            "measured_at", "symbol", "data_symbol", "market", "benchmark_symbol", "calendar",
            "last_bar_date", "natural_days", "sessions_approx", "may_be_partial_current_session",
            "absent_reference_sessions", "absent_recent_sessions", "reference_sessions_checked",
            "veto_window_sessions", "quality", "error", "run_id",
            "quality_freshness", "quality_recent", "quality_historical", "execution_ready",
            "quality_period", "quality_interval",
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

    def get_all_freshness_measurements(self) -> List[sqlite3.Row]:
        """Todas las mediciones de frescura persistidas, en orden cronológico.

        Trae el ``git_sha`` y el ``release_tag`` del manifiesto de su pasada
        porque una ventana larga puede cruzar varias versiones de código, y una
        de ellas (D-36 y D-37) cambió qué cuenta como sesión exigible: agregar
        las dos definiciones en una sola tasa mezclaría métricas distintas. Las
        pasadas anteriores a C-02 no tienen manifiesto y llegan con ``NULL``.
        """

        with self._connect() as connection:
            cursor = connection.execute(
                """
                SELECT f.*, a.git_sha AS run_git_sha, a.release_tag AS run_release_tag
                FROM data_freshness_measurement f
                LEFT JOIN analysis_run a ON a.run_id = f.run_id
                ORDER BY f.measured_at ASC, f.symbol ASC, f.id ASC
                """
            )
            return cursor.fetchall()

    def latest_freshness_measured_at(self) -> Optional[str]:
        """Marca temporal de la última pasada de frescura guardada, si hay alguna."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT measured_at FROM data_freshness_measurement ORDER BY measured_at DESC LIMIT 1"
            ).fetchone()
            return None if row is None else row["measured_at"]

    def get_latest_freshness_absences(self) -> List[tuple[str, date]]:
        """Pares símbolo-fecha ausente de la última pasada de frescura guardada."""

        with self._connect() as connection:
            latest = connection.execute(
                "SELECT measured_at FROM data_freshness_measurement ORDER BY measured_at DESC LIMIT 1"
            ).fetchone()
            if latest is None:
                return []
            cursor = connection.execute(
                """
                SELECT symbol, absent_reference_sessions
                FROM data_freshness_measurement
                WHERE measured_at = ?
                ORDER BY symbol
                """,
                (latest["measured_at"],),
            )
            pairs: list[tuple[str, date]] = []
            for row in cursor.fetchall():
                for value in _decode_date_list(row["absent_reference_sessions"]):
                    pairs.append((row["symbol"], value))
            return pairs

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
    for column in (
        "quality_freshness", "quality_recent", "quality_historical",
        "quality_period", "quality_interval",
    ):
        row.setdefault(column, None)
    return {
        **row,
        "calendar": row.get("calendar"),
        "may_be_partial_current_session": int(bool(row.get("may_be_partial_current_session"))),
        "execution_ready": None if row.get("execution_ready") is None else int(bool(row.get("execution_ready"))),
        "absent_reference_sessions": json.dumps(list(absent), ensure_ascii=False),
        "absent_recent_sessions": json.dumps(list(absent_recent), ensure_ascii=False),
    }


def _add_recommendation_quality_defaults(row: Dict[str, Any]) -> None:
    for column in (
        "discard_code", "execution_code", "quality_freshness", "quality_recent",
        "quality_historical", "quality_period", "quality_interval", "warnings",
    ):
        row.setdefault(column, None)
    if "execution_ready" not in row or row["execution_ready"] is None:
        row["execution_ready"] = None
    else:
        row["execution_ready"] = int(bool(row["execution_ready"]))


def _decode_date_list(raw: str) -> tuple[date, ...]:
    """Fechas ausentes persistidas. Un valor corrupto se declara, no se ignora.

    Esta lista define la población que hay que clasificar; descartar en
    silencio una fecha ilegible la haría más pequeña de lo que es.
    """

    if raw is None or raw == "":
        return ()
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"lista de sesiones ausentes ilegible en la base: {raw!r}") from exc
    if not isinstance(values, list):
        raise ValueError(f"lista de sesiones ausentes no es una lista: {values!r}")
    dates: list[date] = []
    for value in values:
        try:
            dates.append(date.fromisoformat(str(value)))
        except ValueError as exc:
            raise ValueError(f"fecha ausente ilegible en la base: {value!r}") from exc
    return tuple(dates)


# Una copia sin esto no puede sustituir a `intradia.db`: un fichero SQLite
# íntegro pero vacío pasa `integrity_check` y no restaura nada. `recommendation`
# existe desde la v1, así que sirve de marca para cualquier esquema al que se
# pueda volver.
TABLAS_ESENCIALES = ("recommendation",)

BACKUP_VALIDO = "VALIDO"
BACKUP_INVALIDO = "INVALIDO"

REGISTRO_EN_LOG = "REGISTRADO"
REGISTRO_COPIA_MANUAL = "NO_REGISTRADO"
REGISTRO_DESCONOCIDO = "DESCONOCIDO"


@dataclass(frozen=True)
class BackupCheck:
    """Qué se sabe de un fichero de copia, punto por punto.

    El veredicto no sustituye a la materia prima: «no registrado» es un dato
    sobre el origen de la copia, no un defecto de la copia. Confundirlos costó
    el 2026-09-18 llamar «inválida» a una copia manual íntegra, que es
    exactamente lo que no puede pasar en un rollback de madrugada.
    """

    path: Path
    exists: bool
    integrity_ok: bool
    schema_version: Optional[int]
    counts: Dict[str, int] = field(default_factory=dict)
    registration: str = REGISTRO_DESCONOCIDO
    logged_counts: Dict[str, int] = field(default_factory=dict)
    live_counts: Optional[Dict[str, int]] = None
    live_reason: Optional[str] = None
    verdict: str = BACKUP_INVALIDO
    reasons: List[str] = field(default_factory=list)

    @property
    def restorable(self) -> bool:
        return self.verdict == BACKUP_VALIDO


def check_backup(db_path: str | Path, backup_path: str | Path) -> BackupCheck:
    """Integridad, esquema y conteos de **cualquier** fichero SQLite.

    El registro en ``backup_log`` se informa aparte porque solo existe para las
    copias que hizo una migración: una copia hecha con ``cp`` nunca estará ahí
    y sigue siendo perfectamente restaurable.
    """

    backup = Path(backup_path)
    if not backup.is_file():
        return BackupCheck(
            path=backup,
            exists=False,
            integrity_ok=False,
            schema_version=None,
            reasons=[f"no existe el fichero {backup}"],
        )

    try:
        with sqlite3.connect(f"file:{backup}?mode=ro", uri=True) as backup_conn:
            integrity = backup_conn.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                detalle = "sin respuesta" if integrity is None else str(integrity[0])
                return BackupCheck(
                    path=backup,
                    exists=True,
                    integrity_ok=False,
                    schema_version=None,
                    reasons=[f"integrity_check: {detalle}"],
                )
            schema_version = int(backup_conn.execute("PRAGMA user_version").fetchone()[0])
            backup_counts = _table_counts(backup_conn)
    except sqlite3.DatabaseError as exc:
        return BackupCheck(
            path=backup,
            exists=True,
            integrity_ok=False,
            schema_version=None,
            reasons=[f"no se puede leer como base SQLite: {exc}"],
        )

    # La base viva se abre en solo lectura: verificar un backup no puede
    # migrar producción ni crear una base vacía si la ruta está mal.
    live_counts: Optional[Dict[str, int]] = None
    live_reason: Optional[str] = None
    logged_rows: List[Any] = []
    try:
        live = AdvisorDB(db_path, readonly=True)
        with live._connect() as live_conn:
            live_counts = _table_counts(live_conn)
            if table_exists(live_conn, "backup_log"):
                logged_rows = live_conn.execute(
                    "SELECT backup_path, table_name, row_count FROM backup_log"
                ).fetchall()
            else:
                live_reason = "la base viva no tiene backup_log"
    except (sqlite3.DatabaseError, FileNotFoundError) as exc:
        live_reason = f"no se puede leer la base viva: {exc}"

    # Las rutas se comparan resueltas: el registro puede ser relativo (config
    # con ``db_path: intradia.db``) y el operador pasar la absoluta, o al revés.
    target = backup.resolve()
    logged = {
        row["table_name"]: int(row["row_count"])
        for row in logged_rows
        if Path(row["backup_path"]).resolve() == target
    }

    reasons: List[str] = []
    verdict = BACKUP_VALIDO

    ausentes = [table for table in TABLAS_ESENCIALES if table not in backup_counts]
    if ausentes:
        verdict = BACKUP_INVALIDO
        reasons.append(
            f"la copia no contiene {', '.join(ausentes)}: no es una base del asesor"
        )

    if logged:
        registration = REGISTRO_EN_LOG
        faltan = {
            table_name: (backup_counts.get(table_name, 0), row_count)
            for table_name, row_count in logged.items()
            if backup_counts.get(table_name, -1) < row_count
        }
        if faltan:
            verdict = BACKUP_INVALIDO
            for table_name, (encontradas, esperadas) in sorted(faltan.items()):
                reasons.append(
                    f"{table_name}: {encontradas} filas en la copia, {esperadas} registradas en backup_log"
                )
        # Más filas de las registradas no impide restaurar, pero significa que el
        # fichero no es exactamente el que anotó la migración: se dice, y quien
        # decide el rollback lo sabe.
        sobran = {
            table_name: (backup_counts[table_name], row_count)
            for table_name, row_count in logged.items()
            if backup_counts.get(table_name, 0) > row_count
        }
        for table_name, (encontradas, esperadas) in sorted(sobran.items()):
            reasons.append(
                f"{table_name}: {encontradas} filas en la copia frente a {esperadas} registradas; "
                "la copia ha cambiado desde que se registró"
            )
    elif live_reason is not None:
        registration = REGISTRO_DESCONOCIDO
        reasons.append(f"no se ha podido consultar el registro de copias ({live_reason})")
    else:
        registration = REGISTRO_COPIA_MANUAL
        reasons.append("no figura en backup_log: copia manual, no la hizo una migración")

    return BackupCheck(
        path=backup,
        exists=True,
        integrity_ok=True,
        schema_version=schema_version,
        counts=backup_counts,
        registration=registration,
        logged_counts=logged,
        live_counts=live_counts,
        live_reason=live_reason,
        verdict=verdict,
        reasons=reasons,
    )


def verify_backup(db_path: str | Path, backup_path: str | Path) -> bool:
    """¿Se puede restaurar esta copia? Resumen booleano de :func:`check_backup`."""

    return check_backup(db_path, backup_path).restorable


def format_backup_check(check: BackupCheck) -> str:
    """Cada punto por separado, en el orden en que lo necesita un rollback."""

    registro = {
        REGISTRO_EN_LOG: "registrado en backup_log",
        REGISTRO_COPIA_MANUAL: "no registrado (copia manual)",
        REGISTRO_DESCONOCIDO: "desconocido",
    }[check.registration]
    lines = [
        f"fichero            {check.path}",
        f"integridad         {'ok' if check.integrity_ok else 'FALLA'}",
        f"esquema            {'desconocido' if check.schema_version is None else f'v{check.schema_version}'}",
        f"registro           {registro}",
    ]
    if check.counts:
        detalle = ", ".join(f"{table}={count}" for table, count in sorted(check.counts.items()))
        lines.append(f"filas en la copia  {detalle}")
    if check.live_counts is not None:
        detalle = ", ".join(f"{table}={count}" for table, count in sorted(check.live_counts.items()))
        lines.append(f"filas en la viva   {detalle}")
    elif check.live_reason:
        lines.append(f"filas en la viva   desconocidas ({check.live_reason})")
    lines.append(f"veredicto          {check.verdict}")
    for reason in check.reasons:
        lines.append(f"  - {reason}")
    return "\n".join(lines)


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
