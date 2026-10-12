"""Acceso a ``paper.db``: apertura segura, lock, escritura idempotente (ficha §4, §5, §12).

Nada de este módulo abre ``intradia.db``: una base sin el ``application_id`` de T-025 se rechaza, y un
fichero llamado ``intradia.db`` se rechaza aunque esté vacío.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence

from paper.schema import APPLICATION_ID, REFERENCE_DOMAINS, SchemaError, migrate

FORBIDDEN_NAMES = ("intradia.db",)
DEFAULT_LOCK_WAIT_SECONDS = 1200.0


class DivergenceError(RuntimeError):
    """``ERROR_DIVERGENCIA``: una clave ya escrita con un contenido económico distinto (§12)."""


class LockTimeout(RuntimeError):
    """Otra ejecución tiene el lock de ``paper.db`` más allá de la espera acotada."""


class NotAPaperDatabase(RuntimeError):
    """La base no lleva el ``application_id`` de T-025."""


class UnknownReferenceValue(RuntimeError):
    """Un valor de lista cerrada escrito por una versión más nueva: este motor falla cerrado."""


def canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False, default=str)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_sha256(row: Mapping[str, Any], exclude: Sequence[str] = ()) -> str:
    """Hash del contenido económico, sin metadatos de ejecución (§5)."""

    return sha256_text(canonical({k: v for k, v in row.items() if k not in exclude and k != "content_sha256"}))


@dataclass
class PaperStore:
    path: Path
    conn: sqlite3.Connection
    schema_version: int

    @classmethod
    def open(cls, path: Path | str, *, create: bool = False) -> PaperStore:
        target = Path(path)
        if target.name in FORBIDDEN_NAMES:
            raise NotAPaperDatabase(f"{target}: T-025 nunca abre intradia.db (D-75, separación por construcción)")
        exists = target.exists() and target.stat().st_size > 0
        if not exists and not create:
            raise FileNotFoundError(f"{target}: paper.db no existe (crearla con `python -m paper init`)")
        conn = sqlite3.connect(str(target), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        if exists:
            app_id = conn.execute("PRAGMA application_id").fetchone()[0]
            if app_id != APPLICATION_ID:
                conn.close()
                raise NotAPaperDatabase(f"{target}: application_id {app_id:#x} no es el de T-025 ({APPLICATION_ID:#x})")
        else:
            conn.execute(f"PRAGMA application_id = {APPLICATION_ID}")
            conn.execute("PRAGMA journal_mode = WAL")
        try:
            version = migrate(conn)
        except SchemaError:
            conn.close()
            raise
        return cls(target, conn, version)

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------------ concurrencia

    @contextmanager
    def lock(self, wait_seconds: float = DEFAULT_LOCK_WAIT_SECONDS, poll: float = 0.5) -> Iterator[None]:
        """Un solo escritor: ``flock`` exclusivo con espera acotada (§12, ronda 4)."""

        lock_path = self.path.with_name(self.path.name + ".lock")
        fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
        deadline = time.monotonic() + wait_seconds
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError as exc:
                    if time.monotonic() >= deadline:
                        raise LockTimeout(f"{lock_path}: lock ocupado más de {wait_seconds:.0f} s") from exc
                    time.sleep(poll)
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        else:
            self.conn.execute("COMMIT")

    # ------------------------------------------------------------------ escritura idempotente

    def insert(self, table: str, row: Mapping[str, Any], key: Sequence[str], *,
               compare_exclude: Sequence[str] = ()) -> bool:
        """Inserta una fila de hechos. Si la clave ya existe con el mismo contenido económico, no hace nada;
        con un contenido distinto, ``DivergenceError`` y no escribe (§12). Devuelve si insertó."""

        where = " AND ".join(f"{column} = ?" for column in key)
        existing = self.conn.execute(f"SELECT * FROM {table} WHERE {where}", [row[c] for c in key]).fetchone()
        if existing is not None:
            columns = list(existing.keys())  # sqlite3.Row no admite `in` sobre sus claves
            old = {k: existing[k] for k in columns if k in row and k not in compare_exclude}
            new = {k: row[k] for k in old}
            if canonical(old) != canonical(new):
                raise DivergenceError(f"{table} {[row[c] for c in key]}: contenido distinto del ya escrito")
            return False
        columns = list(row)
        placeholders = ", ".join("?" for _ in columns)
        self.conn.execute(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})", [row[c] for c in columns])
        return True

    def insert_first(self, table: str, row: Mapping[str, Any], key: Sequence[str]) -> bool:
        """Observaciones: manda la primera; una posterior con la misma clave no cambia nada."""

        where = " AND ".join(f"{column} = ?" for column in key)
        if self.conn.execute(f"SELECT 1 FROM {table} WHERE {where}", [row[c] for c in key]).fetchone():
            return False
        columns = list(row)
        self.conn.execute(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})", [row[c] for c in columns]
        )
        return True

    def rows(self, sql: str, params: Sequence[Any] = ()) -> List[sqlite3.Row]:
        return list(self.conn.execute(sql, list(params)).fetchall())

    def one(self, sql: str, params: Sequence[Any] = ()) -> Optional[sqlite3.Row]:
        return self.conn.execute(sql, list(params)).fetchone()

    # ------------------------------------------------------------------ listas cerradas

    def check_reference(self, domain: str, value: str) -> str:
        if value not in REFERENCE_DOMAINS[domain]:
            raise UnknownReferenceValue(f"{domain}: valor {value!r} desconocido para este motor (falla cerrado)")
        return value

    def next_run_seq(self) -> int:
        row = self.one("SELECT COALESCE(MAX(run_seq), 0) AS m FROM paper_run")
        assert row is not None
        return int(row["m"]) + 1

    def table_counts(self) -> Dict[str, int]:
        names = [r["name"] for r in self.rows("SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'paper_%'")]
        return {name: int(self.one(f"SELECT COUNT(*) AS n FROM {name}")["n"]) for name in names}  # type: ignore[index]
