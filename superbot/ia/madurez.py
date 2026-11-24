"""Madurez del contrafactual (D-83, D-84): cuántos casos hay y si toca la única evaluación.

Solo cuenta. Nunca lee precios, retornos ni si una operación tocó el stop: la consulta a
``ia_contrafactual`` funde en SQL todos los estados posteriores a la entrada en uno solo, y la
madurez sale del calendario de la plaza, no de lo que hizo el precio. El criterio está en
``docs/superbot-ia/CRITERIO-CONTRAFACTUAL.md``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from advisor.data.calendars import expected_sessions
from advisor.data.sessions import latest_expected_closed_session
from superbot.ia.contrafactual import (
    DATOS_INCOMPLETOS,
    HORIZONTE_SESIONES,
    NO_EJECUTABLE,
    SIN_BARRA_DE_ENTRADA,
    SPLIT_POSTERIOR,
    asegurar_esquema,
)

# Despliegue en la Pi del primer código con el contrafactual y el arreglo del validador (2e26f65).
CORTE = datetime(2026, 11, 24, 9, 55, 3, tzinfo=timezone.utc)
OBJETIVO_POR_GRUPO = 50
MINIMO_POR_GRUPO = 30
FECHA_LIMITE = date(2027, 5, 31)
# El de ``config.yaml``, para quien no carga la configuración (el dashboard).
SETTLEMENT_MINUTES = 20

_ABIERTO = "CON_ENTRADA"
_SIN_RESOLVER = "SIN_RESOLVER"


@dataclass(frozen=True)
class GrupoMadurez:
    maduros: int
    madurando: int
    excluidos: int
    no_ejecutables: int


@dataclass(frozen=True)
class Madurez:
    aprobadas: GrupoMadurez
    descartadas: GrupoMadurez
    sin_resolver: int
    toca_evaluar: bool
    motivo: Optional[str]
    minimo_alcanzado: bool
    # Lo que cambió dentro de la ventana y cierra la muestra; vacío si la estrategia sigue congelada.
    congelacion_rota: Tuple[str, ...]

    def como_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _filas(conn: sqlite3.Connection) -> List[Tuple[Any, ...]]:
    return conn.execute(
        "SELECT d.symbol, d.market, d.resolucion, d.target_session, "
        # Los estados posteriores a la entrada se funden aquí: este programa no puede distinguirlos.
        "  CASE WHEN c.decision_id IS NULL THEN ? "
        "       WHEN c.estado = ? THEN c.estado "
        "       WHEN c.estado IN (?, ?, ?) THEN CASE WHEN c.final = 1 THEN c.estado ELSE ? END "
        "       WHEN c.entrada IS NULL THEN ? ELSE ? END, "
        "  c.entrada IS NOT NULL "
        "FROM ia_decision d JOIN ia_pasada p ON p.id = d.pasada_id LEFT JOIN ia_contrafactual c ON c.decision_id = d.id "
        "WHERE d.tipo = 'COMPRA' AND p.decision_ts >= ? ORDER BY d.symbol, d.target_session, d.id",
        (
            _SIN_RESOLVER, NO_EJECUTABLE, SIN_BARRA_DE_ENTRADA, SPLIT_POSTERIOR, DATOS_INCOMPLETOS, _SIN_RESOLVER,
            _SIN_RESOLVER, _ABIERTO, CORTE.isoformat(timespec="seconds"),
        ),
    ).fetchall()


def _congelacion_rota(conn: sqlite3.Connection) -> Tuple[str, ...]:
    corte = CORTE.isoformat(timespec="seconds")
    avisos: List[str] = []
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'ia_politica_cambio'"
    ).fetchone() and conn.execute("SELECT 1 FROM ia_politica_cambio WHERE created_at >= ?", (corte,)).fetchone():
        avisos.append("cambió la política")
    for asesor, modelos, prompts, esquemas in conn.execute(
        "SELECT asesor, COUNT(DISTINCT model), COUNT(DISTINCT prompt_version), COUNT(DISTINCT schema_version) "
        "FROM ia_llamada WHERE created_at >= ? GROUP BY asesor ORDER BY asesor", (corte,),
    ):
        if modelos > 1:
            avisos.append(f"cambió el modelo del asesor {asesor}")
        if prompts > 1:
            avisos.append(f"cambió el prompt del asesor {asesor}")
        if esquemas > 1:
            avisos.append(f"cambió el esquema del asesor {asesor}")
    return tuple(avisos)


def contar(conn: sqlite3.Connection, instante: datetime, settlement_minutes: int = SETTLEMENT_MINUTES) -> Madurez:
    """Episodios por grupo, en el orden de las decisiones de cada valor.

    Un episodio se abre con la primera decisión ejecutable y dura ``HORIZONTE_SESIONES`` sesiones de
    su plaza, haya saltado o no el stop; las decisiones del mismo valor dentro de él se ignoran. Una
    decisión aún sin resolver detiene a su valor: lo que venga detrás podría no abrir episodio.
    """

    asegurar_esquema(conn)
    cuenta: Dict[Tuple[str, str], int] = {}

    def suma(grupo: str, que: str) -> None:
        cuenta[grupo, que] = cuenta.get((grupo, que), 0) + 1

    cerradas: Dict[str, Optional[date]] = {}
    detenidos: Set[str] = set()
    fin_episodio: Dict[str, Optional[date]] = {}
    sin_resolver = 0
    for symbol, market, grupo, texto, estado, con_entrada in _filas(conn):
        sesion = date.fromisoformat(texto)
        if symbol in detenidos:
            continue
        if symbol in fin_episodio:
            fin = fin_episodio[symbol]
            if fin is None or sesion <= fin:
                continue
        if estado == _SIN_RESOLVER:
            sin_resolver += 1
            detenidos.add(symbol)
            continue
        if estado == NO_EJECUTABLE:
            suma(grupo, "no_ejecutables")
            continue
        if not con_entrada:
            suma(grupo, "excluidos")
            continue
        if market not in cerradas:
            cerradas[market] = latest_expected_closed_session(market, instante, settlement_minutes=settlement_minutes)
        ultima = cerradas[market]
        sesiones = [] if ultima is None else expected_sessions(market, sesion, ultima)
        maduro = len(sesiones) >= HORIZONTE_SESIONES
        # Sin madurar no se sabe dónde acaba el episodio, pero ninguna decisión posterior puede quedar fuera de él.
        fin_episodio[symbol] = sesiones[HORIZONTE_SESIONES - 1] if maduro else None
        suma(grupo, "madurando" if not maduro else "maduros" if estado == _ABIERTO else "excluidos")

    def grupo_de(resolucion: str) -> GrupoMadurez:
        return GrupoMadurez(*(cuenta.get((resolucion, que), 0) for que in (
            "maduros", "madurando", "excluidos", "no_ejecutables",
        )))

    aprobadas, descartadas = grupo_de("COMPRAR"), grupo_de("DESCARTAR")
    menor = min(aprobadas.maduros, descartadas.maduros)
    motivo = (
        f"{OBJETIVO_POR_GRUPO} casos maduros en cada grupo" if menor >= OBJETIVO_POR_GRUPO
        else f"fecha límite {FECHA_LIMITE.isoformat()}" if instante.astimezone(timezone.utc).date() >= FECHA_LIMITE
        else None
    )
    return Madurez(
        aprobadas, descartadas, sin_resolver, motivo is not None, motivo, menor >= MINIMO_POR_GRUPO,
        _congelacion_rota(conn),
    )


def texto_avisos(madurez: Madurez) -> List[Tuple[str, str]]:
    """``(clave, texto)`` de los avisos que correspondan; la clave hace que cada uno salga una sola vez."""

    avisos: List[Tuple[str, str]] = []
    if madurez.toca_evaluar:
        suficiente = "" if madurez.minimo_alcanzado else (
            f"\n- Algún grupo no llega a {MINIMO_POR_GRUPO}: el resultado es INCONCLUSO sin mirar rendimientos."
        )
        avisos.append((
            "madurez:evaluar",
            f"🔔 Toca la única evaluación del contrafactual\n- Motivo: {madurez.motivo}\n"
            f"- Casos maduros: {madurez.aprobadas.maduros} aprobados y {madurez.descartadas.maduros} descartados{suficiente}",
        ))
    if madurez.congelacion_rota:
        detalle = "; ".join(madurez.congelacion_rota)
        avisos.append((
            f"madurez:congelacion:{detalle}",
            f"⚠️ La estrategia ha dejado de estar congelada\n- {detalle}\n- La muestra del contrafactual queda cerrada (D-83).",
        ))
    return avisos


__all__ = [
    "CORTE",
    "FECHA_LIMITE",
    "MINIMO_POR_GRUPO",
    "OBJETIVO_POR_GRUPO",
    "GrupoMadurez",
    "Madurez",
    "contar",
    "texto_avisos",
]
