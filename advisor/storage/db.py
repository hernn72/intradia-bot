"""Persistencia SQLite del asesor.

Tres tablas:

- ``recommendation``: una fila por activo y ejecución. Es el registro
  histórico de lo que el bot recomendó y con qué números, para poder
  auditarlo después.
- ``position``: posiciones abiertas manualmente en Trade Republic, con la
  tesis original. Una vez abierta una posición, el seguimiento se hace contra
  esa tesis y no se vuelve a analizar el activo desde cero.
- ``position_review``: cada revisión de una posición abierta y su veredicto.

Los importes se guardan en euros cuando hay tipo de cambio (``*_eur``) y
siempre también en la divisa nativa, para que un fallo de conversión no
pierda el dato original.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

VERDICTS = ("REFUERZA", "NO CAMBIA", "DEBILITA", "INVALIDA")

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
"""


class AdvisorDB:
    """Acceso a la base de datos del asesor."""

    def __init__(self, path: str | Path = "intradia.db") -> None:
        self.path = str(path)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    # -- Recomendaciones ---------------------------------------------------

    def insert_recommendations(self, rows: Iterable[Dict[str, Any]]) -> int:
        """Guarda las recomendaciones de una ejecución. Devuelve cuántas se insertaron."""

        rows = list(rows)
        if not rows:
            return 0

        columns = [
            "created_at", "symbol", "name", "isin", "trade_republic", "currency", "horizonte",
            "radar", "accion", "score", "evaluable_max", "price", "price_eur", "entry_max",
            "entry_max_eur", "stop", "stop_eur", "target2", "target2_eur", "risk_pct",
            "reward_pct", "rr_ratio", "reasons",
        ]
        placeholders = ", ".join(f":{c}" for c in columns)
        sql = f"INSERT INTO recommendation ({', '.join(columns)}) VALUES ({placeholders})"

        with self._connect() as connection:
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
