"""Registro de las señales de compra: qué se evaluó, qué se decidió y por qué.

Solo observa. El motor anota valores ya calculados en una lista en memoria y nunca
lee estas tablas. Al terminar, las filas se escriben dentro de la transacción de la
cartera, tras un ``SAVEPOINT``: operaciones y registro se confirman juntos, y un
fallo del registro deshace solo el registro. Entonces se declara la pérdida en
``decision_runs``; sin fila de cierre, una ejecución tampoco cuenta como registrada.
La excepción es que SQLite pierda la transacción completa: nada quedó confirmado y
el error sube, como cualquier otro fallo de la cartera.

Nada de lo que ocurra aquí puede llegar al motor: cada entrada captura sus errores.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)

ACCEPTED = "ACEPTADA"
DISCARDED = "DESCARTADA"

ORDER_CREATED = "ORDEN_CREADA"
NO_SLOT = "SIN_HUECO"
RANKING = "RANKING"
NOT_AFFORDABLE = "NO_ASEQUIBLE"
NO_FX = "SIN_FX"
STALE_BAR = "BARRA_ATRASADA"
EXITED_TODAY = "SALIO_HOY"
ORDER_PENDING = "ORDEN_PENDIENTE"
DUPLICATE = "DUPLICADA"
NO_ENTRIES = "SIN_ENTRADAS"

# Base a partir de la cual ``decisiones`` avisa de que conviene decidir qué conservar.
SIZE_WARNING_MB = 256


@dataclass(frozen=True)
class Decision:
    session: date
    symbol: str
    reason: str
    detail: str = ""
    momentum: Optional[float] = None
    rank: Optional[int] = None
    slots: Optional[int] = None


class NullRecorder:
    """Registro apagado: el motor funciona igual sin él."""

    def reset(self) -> None:
        pass

    def record(self, decision: Callable[[], Optional[Decision]]) -> None:
        pass

    def flush(self, conn: sqlite3.Connection, run_id: int, entries: bool) -> Optional[str]:
        return None


class DecisionRecorder(NullRecorder):
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._rows: List[Decision] = []
        self._lost = 0

    def record(self, decision: Callable[[], Optional[Decision]]) -> None:
        """``decision`` se evalúa aquí dentro para que un fallo suyo tampoco llegue al motor."""

        try:
            row = decision()
            if row is not None:
                self._rows.append(row)
        except Exception as exc:
            self._lost += 1
            logger.warning("Decisión sin registrar: %s", type(exc).__name__)

    def flush(self, conn: sqlite3.Connection, run_id: int, entries: bool) -> Optional[str]:
        """Escribe lo anotado. Devuelve la pérdida de trazabilidad, si la hubo."""

        expected = len(self._rows) + self._lost
        mode = "NORMAL" if entries else "SIN_ENTRADAS"
        lost = None
        try:
            conn.execute("SAVEPOINT registro")
            try:
                conn.executemany(
                    "INSERT INTO decision_log (run_id, bar_date, symbol, action, decision, reason, detail, "
                    "momentum, rank, slots) VALUES (?, ?, ?, 'BUY', ?, ?, ?, ?, ?, ?)",
                    [_values(run_id, row) for row in self._rows],
                )
                status = "INCOMPLETO" if self._lost else "COMPLETO"
                conn.execute(
                    "INSERT INTO decision_runs (run_id, mode, expected, written, status) VALUES (?, ?, ?, ?, ?)",
                    (run_id, mode, expected, len(self._rows), status),
                )
                conn.execute("RELEASE registro")
                if self._lost:
                    lost = f"{self._lost} de {expected} decisiones sin registrar"
            except Exception:
                conn.execute("ROLLBACK TO registro")
                conn.execute("RELEASE registro")
                raise
        except Exception as exc:
            # Disco lleno o error de E/S: SQLite ya revirtió la transacción entera, con la
            # cartera dentro. No es un fallo del registro: el motor debe enterarse.
            if not conn.in_transaction:
                raise
            lost = f"registro de decisiones perdido: {expected} sin guardar ({type(exc).__name__})"
            logger.warning(lost)
            _declare_loss(conn, run_id, mode, expected)
        return lost


def _values(run_id: int, row: Decision) -> Tuple[object, ...]:
    decision = ACCEPTED if row.reason == ORDER_CREATED else DISCARDED
    return (run_id, row.session.isoformat(), row.symbol, decision, row.reason, row.detail,
            row.momentum, row.rank, row.slots)


def _declare_loss(conn: sqlite3.Connection, run_id: int, mode: str, expected: int) -> None:
    try:
        conn.execute("SAVEPOINT cierre")
        try:
            conn.execute(
                "INSERT INTO decision_runs (run_id, mode, expected, written, status) "
                "VALUES (?, ?, ?, 0, 'INCOMPLETO')",
                (run_id, mode, expected),
            )
            conn.execute("RELEASE cierre")
        except Exception:
            conn.execute("ROLLBACK TO cierre")
            conn.execute("RELEASE cierre")
            raise
    except Exception as exc:
        logger.warning("Sin cierre del registro: %s", type(exc).__name__)


def recorder_from_env() -> NullRecorder:
    return DecisionRecorder() if os.getenv("SUPERBOT_REGISTRO", "").strip() == "1" else NullRecorder()
