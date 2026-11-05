"""Registro auditable de ``superbot_ia_v1``, en su propia base.

Guarda cada llamada y cada decisión con lo necesario para reconstruirlas (D-12,
D-81), y lleva el presupuesto. Sin registro completo una decisión no vale.
"""

from __future__ import annotations

import fcntl
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional

from superbot.ia.paquete import Paquete
from superbot.ia.politica import POLICY_ID, SCHEMA_VERSION, PoliticaIA
from superbot.store import check_db_path

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS ia_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ia_pasada (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    decision_ts TEXT NOT NULL,
    modo TEXT NOT NULL CHECK (modo IN ('registro', 'activo')),
    code_sha TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('EN_CURSO', 'OK', 'ERROR')),
    detail TEXT
);
CREATE TABLE IF NOT EXISTS ia_paquete (
    input_hash TEXT PRIMARY KEY,
    tipo TEXT NOT NULL,
    symbol TEXT NOT NULL,
    contenido TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ia_llamada (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pasada_id INTEGER NOT NULL REFERENCES ia_pasada(id),
    asesor TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT,
    model_version TEXT,
    prompt_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    input_hash TEXT NOT NULL REFERENCES ia_paquete(input_hash),
    input_source_ids TEXT NOT NULL,
    observaciones TEXT NOT NULL,
    analysis_timestamp TEXT NOT NULL,
    estado TEXT NOT NULL,
    respuesta_cruda TEXT,
    salida_validada TEXT,
    stop_reason TEXT,
    request_id TEXT,
    tokens_entrada INTEGER,
    tokens_salida INTEGER,
    coste_eur REAL NOT NULL DEFAULT 0,
    segundos REAL,
    desde_cache INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ia_llamada_cache ON ia_llamada (input_hash, asesor, prompt_version, estado);
CREATE TABLE IF NOT EXISTS ia_decision (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clave TEXT NOT NULL UNIQUE,
    pasada_id INTEGER NOT NULL REFERENCES ia_pasada(id),
    policy TEXT NOT NULL,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('COMPRA', 'POSICION')),
    signal_session TEXT NOT NULL,
    target_session TEXT NOT NULL,
    target_open TEXT NOT NULL,
    decision_ts TEXT NOT NULL,
    input_hash TEXT NOT NULL REFERENCES ia_paquete(input_hash),
    cuantitativo TEXT NOT NULL,
    votos TEXT NOT NULL,
    predicados TEXT,
    resolucion TEXT NOT NULL,
    motivo TEXT NOT NULL,
    prioridad TEXT,
    causa TEXT,
    aplicada INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ia_gasto (
    mes TEXT PRIMARY KEY,
    reservado_eur REAL NOT NULL DEFAULT 0,
    gastado_eur REAL NOT NULL DEFAULT 0
);
"""


def ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PresupuestoAgotado(RuntimeError):
    pass


class PoliticaDistinta(RuntimeError):
    """La base pertenece a otra política o a otros parámetros: no se mezclan."""


@dataclass(frozen=True)
class LlamadaGuardada:
    respuesta_cruda: str
    salida: Dict[str, Any]


class RegistroIA:
    def __init__(self, path: str | Path, politica: PoliticaIA) -> None:
        self.path = check_db_path(Path(path))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.politica = politica
        self.conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(_ESQUEMA)
        self._migrar()
        self._congelar()

    def _migrar(self) -> None:
        columnas = {fila[1] for fila in self.conn.execute("PRAGMA table_info(ia_llamada)")}
        if "segundos" not in columnas:
            self.conn.execute("ALTER TABLE ia_llamada ADD COLUMN segundos REAL")

    def _congelar(self) -> None:
        guardada = self.conn.execute("SELECT value FROM ia_meta WHERE key = 'politica'").fetchone()
        actual = json.dumps({"id": POLICY_ID, "params": json.loads(self.politica.to_json())}, sort_keys=True)
        if guardada is None:
            self.conn.execute("INSERT INTO ia_meta (key, value) VALUES ('politica', ?)", (actual,))
        elif guardada[0] != actual:
            raise PoliticaDistinta(f"{self.path} se creó con otra política o parámetros")

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def exclusivo(self) -> Iterator[bool]:
        """Una pasada cada vez: dos procesos no pueden gastar ni decidir a la vez."""

        with open(self.path.with_name(self.path.name + ".lock"), "w") as candado:
            try:
                fcntl.flock(candado, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
            yield True

    @contextmanager
    def _transaccion(self) -> Iterator[sqlite3.Connection]:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")

    # --- pasadas ---------------------------------------------------------------

    def abrir_pasada(self, decision_ts: datetime, modo: str, code_sha: str) -> int:
        cursor = self.conn.execute(
            "INSERT INTO ia_pasada (started_at, decision_ts, modo, code_sha, status) VALUES (?, ?, ?, ?, 'EN_CURSO')",
            (ahora_iso(), decision_ts.isoformat(), modo, code_sha),
        )
        return int(cursor.lastrowid or 0)

    def fechar_decision(self, pasada_id: int, decision_ts: datetime) -> None:
        self.conn.execute("UPDATE ia_pasada SET decision_ts = ? WHERE id = ?", (decision_ts.isoformat(), pasada_id))

    def cerrar_pasada(self, pasada_id: int, status: str, detail: str = "") -> None:
        self.conn.execute(
            "UPDATE ia_pasada SET finished_at = ?, status = ?, detail = ? WHERE id = ?",
            (ahora_iso(), status, detail[:4000], pasada_id),
        )

    # --- presupuesto -----------------------------------------------------------

    def reservar(self, mes: str, importe: float) -> None:
        """Reserva el coste máximo antes de llamar: si no cabe, la llamada no se hace."""

        with self._transaccion() as conn:
            conn.execute("INSERT OR IGNORE INTO ia_gasto (mes) VALUES (?)", (mes,))
            fila = conn.execute("SELECT reservado_eur, gastado_eur FROM ia_gasto WHERE mes = ?", (mes,)).fetchone()
            if fila[0] + fila[1] + importe > self.politica.tope_eur_mes:
                raise PresupuestoAgotado(f"{mes}: {fila[1]:.4f} EUR gastados, tope {self.politica.tope_eur_mes}")
            conn.execute("UPDATE ia_gasto SET reservado_eur = reservado_eur + ? WHERE mes = ?", (importe, mes))

    def conciliar(self, mes: str, reservado: float, real: float) -> None:
        self.conn.execute(
            "UPDATE ia_gasto SET reservado_eur = MAX(reservado_eur - ?, 0), gastado_eur = gastado_eur + ? WHERE mes = ?",
            (reservado, real, mes),
        )

    def gasto(self, mes: str) -> float:
        fila = self.conn.execute("SELECT gastado_eur FROM ia_gasto WHERE mes = ?", (mes,)).fetchone()
        return float(fila[0]) if fila else 0.0

    # --- paquetes, llamadas y decisiones ---------------------------------------

    def guardar_paquete(self, paquete: Paquete) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO ia_paquete (input_hash, tipo, symbol, contenido) VALUES (?, ?, ?, ?)",
            (paquete.input_hash, paquete.tipo, paquete.symbol, paquete.mensaje),
        )

    def cache(self, input_hash: str, asesor: str, prompt_version: str, desde: datetime) -> Optional[LlamadaGuardada]:
        fila = self.conn.execute(
            "SELECT respuesta_cruda, salida_validada FROM ia_llamada WHERE input_hash = ? AND asesor = ? "
            "AND prompt_version = ? AND model = ? AND estado = 'OK' AND desde_cache = 0 AND created_at >= ? "
            "ORDER BY id DESC LIMIT 1",
            (input_hash, asesor, prompt_version, self.politica.modelo, desde.isoformat(timespec="seconds")),
        ).fetchone()
        if fila is None:
            return None
        return LlamadaGuardada(fila[0], json.loads(fila[1]))

    def guardar_llamada(self, **campos: Any) -> int:
        campos.setdefault("created_at", ahora_iso())
        columnas = ", ".join(campos)
        huecos = ", ".join("?" for _ in campos)
        cursor = self.conn.execute(f"INSERT INTO ia_llamada ({columnas}) VALUES ({huecos})", tuple(campos.values()))
        return int(cursor.lastrowid or 0)

    def ya_decidida(self, clave: str) -> bool:
        return self.conn.execute("SELECT 1 FROM ia_decision WHERE clave = ?", (clave,)).fetchone() is not None

    def guardar_decision(self, **campos: Any) -> int:
        campos.setdefault("created_at", ahora_iso())
        campos["policy"] = POLICY_ID
        columnas = ", ".join(campos)
        huecos = ", ".join("?" for _ in campos)
        with self._transaccion() as conn:
            cursor = conn.execute(f"INSERT INTO ia_decision ({columnas}) VALUES ({huecos})", tuple(campos.values()))
        return int(cursor.lastrowid or 0)

    def decisiones(self, pasada_id: Optional[int] = None) -> List[Mapping[str, Any]]:
        consulta = "SELECT * FROM ia_decision"
        parametros: tuple[Any, ...] = ()
        if pasada_id is not None:
            consulta += " WHERE pasada_id = ?"
            parametros = (pasada_id,)
        return [dict(fila) for fila in self.conn.execute(consulta + " ORDER BY id", parametros)]

    def llamadas(self, pasada_id: int) -> List[Mapping[str, Any]]:
        return [dict(f) for f in self.conn.execute("SELECT * FROM ia_llamada WHERE pasada_id = ? ORDER BY id", (pasada_id,))]


def ventana_cache(ahora: datetime, politica: PoliticaIA) -> datetime:
    return ahora - timedelta(hours=politica.cache_horas)


__all__ = ["SCHEMA_VERSION", "LlamadaGuardada", "PoliticaDistinta", "PresupuestoAgotado", "RegistroIA", "ventana_cache"]
