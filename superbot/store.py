"""Persistencia SQLite de la cartera paper visible (``superbot.db``).

Base propia: no comparte fichero ni esquema con ``intradia.db`` (asesor) ni con
``paper.db`` (T-025), y se niega a abrir una ruta con esos nombres.

El cash no se guarda como saldo: se deriva sumando ``cash_delta_eur`` de los
fills, de modo que no hay un número que pueda divergir del libro de operaciones.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from superbot.config import SuperbotConfig

SCHEMA_VERSION = 1
FORBIDDEN_DB_NAMES = {"paper.db", "intradia.db"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS symbol_state (
    symbol        TEXT PRIMARY KEY,
    last_bar_date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT NOT NULL CHECK (status IN ('RUNNING', 'OK', 'ERROR')),
    symbols_ok  INTEGER,
    symbols_err INTEGER,
    bars        INTEGER,
    detail      TEXT
);
CREATE TABLE IF NOT EXISTS signals (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id    INTEGER NOT NULL REFERENCES runs(id),
    symbol    TEXT NOT NULL,
    bar_date  TEXT NOT NULL,
    action    TEXT NOT NULL CHECK (action IN ('BUY', 'SELL')),
    close     REAL NOT NULL,
    sma_fast  REAL,
    sma_slow  REAL,
    rsi       REAL,
    atr       REAL,
    momentum  REAL,
    reason    TEXT NOT NULL,
    UNIQUE (symbol, bar_date, action)
);
CREATE TABLE IF NOT EXISTS orders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id   INTEGER NOT NULL UNIQUE REFERENCES signals(id),
    symbol      TEXT NOT NULL,
    side        TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    status      TEXT NOT NULL CHECK (status IN ('PENDING', 'FILLED', 'REJECTED', 'CANCELLED')),
    signal_date TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    resolved_date TEXT,
    detail      TEXT
);
CREATE TABLE IF NOT EXISTS positions (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol             TEXT NOT NULL,
    name               TEXT,
    currency           TEXT NOT NULL,
    status             TEXT NOT NULL CHECK (status IN ('OPEN', 'CLOSED')),
    quantity           REAL NOT NULL CHECK (quantity > 0),
    entry_order_id     INTEGER NOT NULL UNIQUE REFERENCES orders(id),
    entry_date         TEXT NOT NULL,
    entry_price_native REAL NOT NULL,
    entry_fx           REAL NOT NULL,
    cost_eur           REAL NOT NULL,
    initial_stop       REAL NOT NULL,
    stop               REAL NOT NULL,
    target1            REAL NOT NULL,
    target2            REAL NOT NULL,
    t1_hit_date        TEXT,
    t2_hit_date        TEXT,
    last_date          TEXT NOT NULL,
    last_close         REAL NOT NULL,
    last_fx            REAL NOT NULL,
    exit_date          TEXT,
    exit_price_native  REAL,
    exit_fx            REAL,
    exit_reason        TEXT,
    proceeds_eur       REAL,
    pnl_eur            REAL,
    pnl_pct            REAL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_open_position_per_symbol
    ON positions(symbol) WHERE status = 'OPEN';
CREATE TABLE IF NOT EXISTS fills (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id    INTEGER NOT NULL REFERENCES positions(id),
    order_id       INTEGER REFERENCES orders(id),
    symbol         TEXT NOT NULL,
    side           TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    kind           TEXT NOT NULL CHECK (kind IN ('ENTRY', 'SIGNAL_EXIT', 'STOP', 'GAP_STOP')),
    bar_date       TEXT NOT NULL,
    currency       TEXT NOT NULL,
    price_native   REAL NOT NULL,
    fx_rate        REAL NOT NULL,
    quantity       REAL NOT NULL,
    notional_eur   REAL NOT NULL,
    commission_eur REAL NOT NULL,
    cash_delta_eur REAL NOT NULL,
    UNIQUE (position_id, side)
);
CREATE TABLE IF NOT EXISTS equity_snapshots (
    date           TEXT PRIMARY KEY,
    cash_eur       REAL NOT NULL,
    invested_eur   REAL NOT NULL,
    equity_eur     REAL NOT NULL,
    open_positions INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    key        TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    kind       TEXT NOT NULL,
    text       TEXT NOT NULL,
    status     TEXT NOT NULL CHECK (status IN ('PENDING', 'SENT', 'SKIPPED', 'FAILED')),
    sent_at    TEXT
);
"""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def check_db_path(path: Path) -> Path:
    if path.name.lower() in FORBIDDEN_DB_NAMES:
        raise ValueError(f"{path.name} pertenece al asesor o a T-025: superbot usa su propia base")
    return path


class SuperbotStore:
    def __init__(self, path: str | Path) -> None:
        self.path = check_db_path(Path(path))
        self._conn: Optional[sqlite3.Connection] = None

    # --- conexión -----------------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(_SCHEMA)
            self._conn = conn
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise

    def _rows(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        return [dict(row) for row in self.connect().execute(sql, params).fetchall()]

    # --- meta ---------------------------------------------------------------

    def is_initialized(self) -> bool:
        return self.get_meta("config") is not None

    def initialize(self, config: SuperbotConfig, start: date, retrospective: bool) -> None:
        config.validate()
        if self.is_initialized():
            raise ValueError(f"{self.path} ya tiene una cartera; usa otra ruta para empezar de cero")
        with self.transaction() as conn:
            for key, value in {
                "schema_version": str(SCHEMA_VERSION),
                "config": config.to_json(),
                "start_date": start.isoformat(),
                "retrospective": "1" if retrospective else "0",
                "created_at": utcnow_iso(),
            }.items():
                conn.execute("INSERT INTO meta (key, value) VALUES (?, ?)", (key, value))

    def get_meta(self, key: str) -> Optional[str]:
        row = self.connect().execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row[0])

    def config(self) -> SuperbotConfig:
        if self._conn is None and not self.path.exists():
            raise ValueError(f"{self.path} no está inicializada: ejecuta `python -m superbot init`")
        raw = self.get_meta("config")
        if raw is None:
            raise ValueError(f"{self.path} no está inicializada: ejecuta `python -m superbot init`")
        return SuperbotConfig.from_json(raw)

    def start_date(self) -> date:
        raw = self.get_meta("start_date")
        if raw is None:
            raise ValueError("cartera sin fecha de inicio")
        return date.fromisoformat(raw)

    # --- estado por símbolo -------------------------------------------------

    def last_bar_dates(self) -> Dict[str, date]:
        return {
            row["symbol"]: date.fromisoformat(row["last_bar_date"])
            for row in self._rows("SELECT symbol, last_bar_date FROM symbol_state")
        }

    # --- runs ---------------------------------------------------------------

    def start_run(self) -> int:
        with self.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO runs (started_at, status) VALUES (?, 'RUNNING')", (utcnow_iso(),)
            )
            return int(cursor.lastrowid or 0)

    def finish_run(self, run_id: int, status: str, symbols_ok: int, symbols_err: int, bars: int, detail: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE runs SET finished_at = ?, status = ?, symbols_ok = ?, symbols_err = ?, bars = ?, detail = ? "
                "WHERE id = ?",
                (utcnow_iso(), status, symbols_ok, symbols_err, bars, detail, run_id),
            )

    # --- consultas para informes y dashboard --------------------------------

    def cash_eur(self) -> float:
        initial = self.config().initial_capital_eur
        row = self.connect().execute("SELECT COALESCE(SUM(cash_delta_eur), 0) FROM fills").fetchone()
        return initial + float(row[0])

    def open_positions(self) -> List[Dict[str, Any]]:
        return self._rows("SELECT * FROM positions WHERE status = 'OPEN' ORDER BY entry_date, id")

    def closed_positions(self) -> List[Dict[str, Any]]:
        return self._rows("SELECT * FROM positions WHERE status = 'CLOSED' ORDER BY exit_date, id")

    def pending_orders(self) -> List[Dict[str, Any]]:
        return self._rows("SELECT * FROM orders WHERE status = 'PENDING' ORDER BY signal_date, id")

    def orders(self, limit: int = 200) -> List[Dict[str, Any]]:
        return self._rows("SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,))

    def fills(self) -> List[Dict[str, Any]]:
        return self._rows("SELECT * FROM fills ORDER BY bar_date, id")

    def equity_curve(self) -> List[Dict[str, Any]]:
        return self._rows("SELECT * FROM equity_snapshots ORDER BY date")

    def runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self._rows("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))

    def pending_notifications(self) -> List[Dict[str, Any]]:
        return self._rows("SELECT * FROM notifications WHERE status IN ('PENDING', 'FAILED') ORDER BY id")

    def mark_notification(self, notification_id: int, status: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE notifications SET status = ?, sent_at = ? WHERE id = ?",
                (status, utcnow_iso(), notification_id),
            )
