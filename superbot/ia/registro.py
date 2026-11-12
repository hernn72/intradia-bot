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
_ESQUEMA_POLITICA_CAMBIO = """
CREATE TABLE IF NOT EXISTS ia_politica_cambio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anterior TEXT NOT NULL,
    nueva TEXT NOT NULL,
    motivo TEXT NOT NULL,
    created_at TEXT NOT NULL
)
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


def _politica_json(politica: PoliticaIA) -> str:
    return json.dumps({"id": POLICY_ID, "params": json.loads(politica.to_json())}, sort_keys=True)


def _candado(path: Path) -> Path:
    return path.with_name(path.name + ".lock")


def migrar_politica(path: str | Path, politica: PoliticaIA, motivo: str) -> Optional[Dict[str, Any]]:
    """Cambia los parámetros congelados de una base ya creada, dejando constancia del cambio.

    Es el único camino para que una base siga abriéndose tras cambiar ``PoliticaIA``: abrirla
    sin migrar sigue fallando con ``PoliticaDistinta``. Devuelve los parámetros que cambian, o
    ``None`` si la base ya estaba al día. No cambia de política (``POLICY_ID``) ni crea la base.
    """

    ruta = check_db_path(Path(path))
    if not motivo.strip():
        raise ValueError("falta el motivo del cambio de política")
    if not ruta.exists():
        raise FileNotFoundError(ruta)
    nueva = _politica_json(politica)
    with open(_candado(ruta), "w") as candado:
        try:
            fcntl.flock(candado, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("hay una pasada en curso: la política no se cambia a mitad") from None
        conn = sqlite3.connect(ruta, timeout=30, isolation_level=None)
        try:
            # Nada se crea antes de saber que la base es de Superbot IA: un ``--db`` equivocado
            # se rechaza sin dejarle ni una tabla.
            es_propia = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'ia_meta'"
            ).fetchone()
            if es_propia is None:
                raise PoliticaDistinta(f"{ruta} no es una base de Superbot IA")
            conn.execute("BEGIN IMMEDIATE")
            try:
                guardada = conn.execute("SELECT value FROM ia_meta WHERE key = 'politica'").fetchone()
                if guardada is None:
                    raise PoliticaDistinta(f"{ruta} no tiene política congelada: no es una base de Superbot IA")
                anterior = json.loads(guardada[0])
                if anterior.get("id") != POLICY_ID:
                    raise PoliticaDistinta(f"{ruta} pertenece a la política {anterior.get('id')!r}")
                if guardada[0] == nueva:
                    conn.execute("ROLLBACK")
                    return None
                conn.execute(_ESQUEMA_POLITICA_CAMBIO)
                conn.execute(
                    "INSERT INTO ia_politica_cambio (anterior, nueva, motivo, created_at) VALUES (?, ?, ?, ?)",
                    (guardada[0], nueva, motivo.strip(), ahora_iso()),
                )
                conn.execute("UPDATE ia_meta SET value = ? WHERE key = 'politica'", (nueva,))
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
        finally:
            conn.close()
    antes, despues = anterior["params"], json.loads(nueva)["params"]
    return {
        clave: {"antes": antes.get(clave), "despues": despues.get(clave)}
        for clave in sorted(set(antes) | set(despues))
        if antes.get(clave) != despues.get(clave) or (clave in antes) != (clave in despues)
    }


class RegistroIA:
    def __init__(self, path: str | Path, politica: PoliticaIA) -> None:
        self.path = check_db_path(Path(path))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.politica = politica
        self.conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(_ESQUEMA)
        self.conn.execute(_ESQUEMA_POLITICA_CAMBIO)
        self._migrar()
        self._congelar()

    def _migrar(self) -> None:
        columnas = {fila[1] for fila in self.conn.execute("PRAGMA table_info(ia_llamada)")}
        if "segundos" not in columnas:
            self.conn.execute("ALTER TABLE ia_llamada ADD COLUMN segundos REAL")

    def _congelar(self) -> None:
        guardada = self.conn.execute("SELECT value FROM ia_meta WHERE key = 'politica'").fetchone()
        actual = _politica_json(self.politica)
        if guardada is None:
            self.conn.execute("INSERT INTO ia_meta (key, value) VALUES ('politica', ?)", (actual,))
        elif guardada[0] != actual:
            raise PoliticaDistinta(
                f"{self.path} se creó con otra política o parámetros; un cambio deliberado se aplica con "
                "`python -m superbot.ia --db ... migrar-politica --motivo ...`"
            )

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def exclusivo(self) -> Iterator[bool]:
        """Una pasada cada vez: dos procesos no pueden gastar ni decidir a la vez."""

        with open(_candado(self.path), "w") as candado:
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
            tope = self.politica.tope_eur_mes
            if tope is not None and fila[0] + fila[1] + importe > tope:
                raise PresupuestoAgotado(f"{mes}: {fila[1]:.4f} EUR gastados, tope {tope}")
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

    def marcar_aplicadas_sin_efecto(self, pasada_id: int, resoluciones: tuple[str, ...]) -> None:
        """``DESCARTAR``/``MANTENER`` no crean ningún efecto durable: marcarlas aplicadas es su único rastro.

        Una posición que el stop obligatorio ya cerró no pasa por aquí: no
        llega a generar una decisión de tipo ``POSICION`` esta pasada (ver
        ``superbot.ia.cartera``), así que no hay nada que marcar para ella.
        Comprueba por sí misma que ``pasada_id`` es de modo ``'activo'``:
        ninguna decisión de una pasada ``'registro'`` (incluidas las 1.862 ya
        existentes de la Entrega B) debe poder marcarse aplicada, ni siquiera
        por un uso indebido de este método con un ``pasada_id`` antiguo.
        """

        marcador = ", ".join("?" for _ in resoluciones)
        self.conn.execute(
            f"UPDATE ia_decision SET aplicada = 1 WHERE pasada_id = ? AND resolucion IN ({marcador}) "
            "AND pasada_id IN (SELECT id FROM ia_pasada WHERE modo = 'activo')",
            (pasada_id, *resoluciones),
        )

    def marcar_aplicada(self, decision_id: int) -> None:
        """Una decisión concreta ya produjo su efecto durable (p. ej. una orden ``ENTRY`` pendiente).

        Misma defensa que ``marcar_aplicadas_sin_efecto``: solo si su pasada es de modo ``'activo'``.
        """

        self.conn.execute(
            "UPDATE ia_decision SET aplicada = 1 WHERE id = ? "
            "AND pasada_id IN (SELECT id FROM ia_pasada WHERE modo = 'activo')",
            (decision_id,),
        )

    def decisiones(self, pasada_id: Optional[int] = None) -> List[Mapping[str, Any]]:
        consulta = "SELECT * FROM ia_decision"
        parametros: tuple[Any, ...] = ()
        if pasada_id is not None:
            consulta += " WHERE pasada_id = ?"
            parametros = (pasada_id,)
        return [dict(fila) for fila in self.conn.execute(consulta + " ORDER BY id", parametros)]

    def decisiones_recientes(self, limite: int = 200) -> List[Mapping[str, Any]]:
        """Como ``decisiones()`` pero acotada en SQL (dashboard): nunca carga todo el histórico
        para mostrar solo las últimas. Más reciente primero."""

        return [
            dict(f) for f in self.conn.execute(
                "SELECT * FROM ia_decision ORDER BY decision_ts DESC, id DESC LIMIT ?", (limite,)
            )
        ]

    def llamadas(self, pasada_id: int) -> List[Mapping[str, Any]]:
        return [dict(f) for f in self.conn.execute("SELECT * FROM ia_llamada WHERE pasada_id = ? ORDER BY id", (pasada_id,))]

    def pasadas(self, limite: int = 50) -> List[Mapping[str, Any]]:
        """Las últimas pasadas (estado operativo y errores), más reciente primero (dashboard)."""

        return [
            dict(f) for f in self.conn.execute(
                "SELECT * FROM ia_pasada ORDER BY started_at DESC, id DESC LIMIT ?", (limite,)
            )
        ]

    def gasto_desde(self, desde: str) -> float:
        """Coste real de las llamadas hechas desde ``desde`` (ISO UTC), p. ej. la activación de la cartera."""

        fila = self.conn.execute(
            "SELECT COALESCE(SUM(coste_eur), 0) FROM ia_llamada WHERE created_at >= ?", (desde,)
        ).fetchone()
        return float(fila[0])

    def gasto_total(self) -> float:
        """Coste real acumulado (todos los meses), sin contar lo meramente reservado."""

        fila = self.conn.execute("SELECT COALESCE(SUM(gastado_eur), 0) FROM ia_gasto").fetchone()
        return float(fila[0])


def ventana_cache(ahora: datetime, politica: PoliticaIA) -> datetime:
    return ahora - timedelta(hours=politica.cache_horas)


__all__ = [
    "SCHEMA_VERSION",
    "LlamadaGuardada",
    "PoliticaDistinta",
    "PresupuestoAgotado",
    "RegistroIA",
    "migrar_politica",
    "ventana_cache",
]
