"""Madurez del contrafactual (D-83, D-84): cuántos casos hay y si toca la única evaluación.

Solo cuenta, y solo lee: de cada decisión, si su apertura pasó el gate (``ia_contrafactual_entrada``, un
hecho que se escribe una vez), y el calendario de su plaza. No toca ``ia_contrafactual``, donde están
los desenlaces, así que ningún recuento puede depender de un stop. El criterio está en
``docs/superbot-ia/CRITERIO-CONTRAFACTUAL.md``.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

from advisor.data.calendars import expected_sessions
from advisor.data.sessions import latest_expected_closed_session
from superbot.ia.contrafactual import HORIZONTE_SESIONES
from superbot.ia.politica import PoliticaIA

# Despliegue en la Pi del primer código con el contrafactual y el arreglo del validador (2e26f65).
CORTE = datetime(2026, 11, 24, 9, 55, 3, tzinfo=timezone.utc)
OBJETIVO_POR_GRUPO = 50
MINIMO_POR_GRUPO = 30
FECHA_LIMITE = date(2027, 5, 31)
# El de ``config.yaml``, para quien no carga la configuración (el dashboard).
SETTLEMENT_MINUTES = 20

# Parámetros de la política que no deciden ninguna operación: cambiarlos no rompe la congelación.
_PARAMETROS_AJENOS = frozenset({
    "tope_eur_mes", "cache_horas", "eur_por_usd", "usd_millon_entrada", "usd_millon_salida", "margen_tokens_entrada",
})
_RAIZ = Path(__file__).resolve().parents[2]
_FICHEROS = (
    "config.yaml", "universe.yaml", "exchange_overrides.yaml", "superbot/config.py", "superbot/data.py",
    "superbot/ia/asesores.py", "superbot/ia/cartera.py", "superbot/ia/comite.py", "superbot/ia/datos.py",
    "superbot/ia/paquete.py", "superbot/ia/predicados.py",
)
# La huella de la estrategia en el corte. Una prueba falla si el código se aparta de ella: no se
# actualiza sin cerrar antes la muestra.
HUELLA_CONGELADA = "7fab091759159a889dc50003cfdd5a2cba1ba132b6c67ac90e2d1c703773acb7"


def huella_estrategia(raiz: Path = _RAIZ) -> str:
    """Lo que decide operaciones: configuración, universo, análisis, asesores, cartera y elegibilidad."""

    from superbot.ia import pasada  # en tiempo de ejecución: ``pasada`` importa este módulo

    resumen = hashlib.sha256()
    ficheros = [raiz / f for f in _FICHEROS] + sorted((raiz / "superbot/ia/prompts").glob("*.md"))
    ficheros += sorted(f for f in (raiz / "advisor").rglob("*.py") if "research" not in f.parts)
    for fichero in ficheros:
        resumen.update(fichero.relative_to(raiz).as_posix().encode() + b"\0" + fichero.read_bytes() + b"\0")
    # ``pasada.py`` también tiene observación y avisos: solo cuenta lo que decide.
    for pieza in (pasada.motivo_no_elegible, pasada.elegir_por_plaza, pasada.Motor):
        resumen.update(inspect.getsource(pieza).encode() + b"\0")
    resumen.update(json.dumps(_estrategicos(asdict(PoliticaIA())), sort_keys=True).encode())
    return resumen.hexdigest()


def _estrategicos(parametros: Mapping[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in parametros.items() if k not in _PARAMETROS_AJENOS}


@dataclass(frozen=True)
class GrupoMadurez:
    maduros: int
    madurando: int
    no_ejecutables: int
    sin_entrada: int


@dataclass(frozen=True)
class Madurez:
    aprobadas: GrupoMadurez
    descartadas: GrupoMadurez
    sin_resolver: int
    toca_evaluar: bool
    motivo: Optional[str]
    minimo_alcanzado: bool
    # Lo que cambió de lo vigilado (huella de la estrategia, política, modelo y prompts).
    congelacion_rota: Tuple[str, ...]

    def como_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _hay_tabla(conn: sqlite3.Connection, nombre: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (nombre,)).fetchone() is not None


def _filas(conn: sqlite3.Connection) -> List[Tuple[Any, ...]]:
    con_entrada = _hay_tabla(conn, "ia_contrafactual_entrada")
    return conn.execute(
        "SELECT d.symbol, d.market, d.resolucion, d.target_session, "
        + ("e.ejecutable " if con_entrada else "NULL ")
        + "FROM ia_decision d JOIN ia_pasada p ON p.id = d.pasada_id "
        + ("LEFT JOIN ia_contrafactual_entrada e ON e.decision_id = d.id " if con_entrada else "")
        + "WHERE d.tipo = 'COMPRA' AND p.decision_ts >= ? ORDER BY d.symbol, d.target_session, d.id",
        (CORTE.isoformat(timespec="seconds"),),
    ).fetchall()


def _congelacion_rota(conn: sqlite3.Connection) -> Tuple[str, ...]:
    corte = CORTE.isoformat(timespec="seconds")
    avisos: List[str] = []
    if huella_estrategia() != HUELLA_CONGELADA:
        avisos.append("cambió el código o la configuración de la estrategia")
    if _hay_tabla(conn, "ia_politica_cambio"):
        for anterior, nueva in conn.execute(
            "SELECT anterior, nueva FROM ia_politica_cambio WHERE created_at >= ? ORDER BY id", (corte,)
        ):
            antes, despues = (_estrategicos(json.loads(texto)["params"]) for texto in (anterior, nueva))
            cambiados = sorted(k for k in antes.keys() | despues.keys() if antes.get(k) != despues.get(k))
            if cambiados:
                avisos.append("cambió la política: " + ", ".join(cambiados))
    for asesor, modelos, prompts, esquemas in conn.execute(
        "SELECT asesor, COUNT(DISTINCT model), COUNT(DISTINCT prompt_version), COUNT(DISTINCT schema_version) "
        "FROM ia_llamada WHERE created_at >= ? GROUP BY asesor ORDER BY asesor", (corte,),
    ):
        for cuantos, que in ((modelos, "modelo"), (prompts, "prompt"), (esquemas, "esquema")):
            if cuantos > 1:
                avisos.append(f"cambió el {que} del asesor {asesor}")
    return tuple(avisos)


def contar(conn: sqlite3.Connection, instante: datetime, settlement_minutes: int = SETTLEMENT_MINUTES) -> Madurez:
    """Episodios por grupo, en el orden de las decisiones de cada valor. No escribe nada.

    Un episodio se abre con la primera decisión ejecutable y dura ``HORIZONTE_SESIONES`` sesiones de su
    plaza contando la de entrada; las decisiones del mismo valor dentro de él se ignoran. Una decisión
    cuya apertura aún no se ha visto detiene a su valor; si tras esas sesiones sigue sin verse, no
    hubo entrada y deja paso a la siguiente. Los datos rotos posteriores a la entrada no se miran
    aquí: se descuentan al evaluar.
    """

    cuenta: Dict[Tuple[str, str], int] = {}
    cerradas: Dict[str, Optional[date]] = {}
    detenidos: Set[str] = set()
    fin_episodio: Dict[str, date] = {}
    sin_resolver = 0

    def suma(grupo: str, que: str) -> None:
        cuenta[grupo, que] = cuenta.get((grupo, que), 0) + 1

    for symbol, market, grupo, texto, ejecutable in _filas(conn):
        sesion = date.fromisoformat(texto)
        if symbol in detenidos or (symbol in fin_episodio and sesion <= fin_episodio[symbol]):
            continue
        if ejecutable == 0:
            suma(grupo, "no_ejecutables")
            continue
        if market not in cerradas:
            cerradas[market] = latest_expected_closed_session(market, instante, settlement_minutes=settlement_minutes)
        ultima = cerradas[market]
        sesiones = [] if ultima is None else expected_sessions(market, sesion, ultima)
        maduro = len(sesiones) >= HORIZONTE_SESIONES
        if ejecutable is None:
            if maduro:
                suma(grupo, "sin_entrada")
            else:
                sin_resolver += 1
                detenidos.add(symbol)
            continue
        suma(grupo, "maduros" if maduro else "madurando")
        if maduro:
            fin_episodio[symbol] = sesiones[HORIZONTE_SESIONES - 1]
        else:
            detenidos.add(symbol)  # todo lo posterior cae dentro de un episodio aún abierto

    def grupo_de(resolucion: str) -> GrupoMadurez:
        return GrupoMadurez(*(cuenta.get((resolucion, que), 0) for que in (
            "maduros", "madurando", "no_ejecutables", "sin_entrada",
        )))

    aprobadas, descartadas = grupo_de("COMPRAR"), grupo_de("DESCARTAR")
    menor = min(aprobadas.maduros, descartadas.maduros)
    rota = _congelacion_rota(conn)
    motivo = (
        f"{OBJETIVO_POR_GRUPO} casos maduros en cada grupo" if menor >= OBJETIVO_POR_GRUPO
        else f"fecha límite {FECHA_LIMITE.isoformat()}" if instante.astimezone(timezone.utc).date() >= FECHA_LIMITE
        else None
    )
    # Con la congelación rota la muestra mezcla estrategias: no se ordena evaluarla.
    return Madurez(
        aprobadas, descartadas, sin_resolver, motivo is not None and not rota, motivo, menor >= MINIMO_POR_GRUPO, rota,
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
            f"⚠️ La estrategia ha dejado de estar congelada\n- {detalle}\n"
            "- La muestra del contrafactual queda cerrada y no se pedirá evaluarla (D-83): decide el propietario.",
        ))
    return avisos


__all__ = [
    "CORTE",
    "FECHA_LIMITE",
    "HUELLA_CONGELADA",
    "MINIMO_POR_GRUPO",
    "OBJETIVO_POR_GRUPO",
    "GrupoMadurez",
    "Madurez",
    "contar",
    "huella_estrategia",
    "texto_avisos",
]
