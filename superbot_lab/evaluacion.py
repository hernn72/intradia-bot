"""Lectura por fases y puertas de la evaluación única del contrafactual."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import exchange_calendars
import pandas

from advisor.data.calendars import expected_sessions
from advisor.data.sessions import latest_expected_closed_session, session_date_of
from advisor.research.vintage import VintageLoad, load_vintage
from superbot.ia import madurez
from superbot.ia.contrafactual import (
    ABIERTA,
    DATOS_INCOMPLETOS,
    HORIZONTE,
    HORIZONTE_SESIONES,
    NO_EJECUTABLE,
    SIN_BARRA_DE_ENTRADA,
    SPLIT_POSTERIOR,
    STOP,
)
from superbot.ia.medicion import REFERENCIA
from superbot_lab.datos_lab import fecha_fx
from superbot_lab.evaluador import (
    SEMILLA,
    Caso,
    Observacion,
    SeriePrecios,
    carteras,
    coste_api_por_aprobado,
    estimador,
    exceso_neto,
    fx_de,
    intervalo_bloques,
    secundario,
    veredicto,
)

_RAIZ = Path(__file__).resolve().parents[1]
_EVALUADOR = (
    "superbot_lab/evaluador.py", "superbot_lab/evaluacion.py", "superbot_lab/evaluar.py",
    "superbot_lab/datos_lab.py", "superbot/ia/contrafactual.py", "superbot/ia/madurez.py",
    "superbot/ia/medicion.py", "superbot/ia/cartera.py", "superbot/ia/registro.py",
    "advisor/research/vintage.py", "advisor/data/calendars.py", "advisor/data/sessions.py",
    "exchange_overrides.yaml",
)
_AUTORIZACION = Path("docs/superbot-ia/AUTORIZACION-EVALUACION.json")
_CRITERIO = Path("docs/superbot-ia/CRITERIO-CONTRAFACTUAL.md")
_SALIDA = Path("evidence/superbot-ia/contrafactual")
_EXCLUIDOS = frozenset({SIN_BARRA_DE_ENTRADA, SPLIT_POSTERIOR, DATOS_INCOMPLETOS})
_TABLAS_FASE0 = frozenset({
    "ia_meta", "ia_pasada", "ia_paquete", "ia_llamada", "ia_decision",
    "ia_contrafactual_entrada", "ia_politica_cambio", "sqlite_master",
})
_TABLAS_FASE2 = frozenset({"ia_contrafactual", "ia_posicion", "ia_orden"})


class EvaluacionDenegada(RuntimeError):
    pass


@dataclass(frozen=True)
class Episodio:
    decision_id: int
    symbol: str
    market: str
    grupo: str
    sesion: date
    categoria: str


@dataclass(frozen=True)
class Puertas:
    autorizacion: bool
    sin_resultado: bool
    git_limpio: bool
    madurez_valida: bool
    muestra_minima: bool
    motivo: Optional[str]

    @property
    def permitida(self) -> bool:
        return all((self.autorizacion, self.sin_resultado, self.git_limpio, self.madurez_valida))


def _sha(path: Path) -> str:
    resumen = hashlib.sha256()
    with path.open("rb") as fichero:
        for bloque in iter(lambda: fichero.read(1024 * 1024), b""):
            resumen.update(bloque)
    return resumen.hexdigest()


def huella_evaluador(raiz: Path = _RAIZ) -> str:
    resumen = hashlib.sha256()
    for nombre in _EVALUADOR:
        ruta = raiz / nombre
        resumen.update(nombre.encode() + b"\0" + ruta.read_bytes() + b"\0")
    return resumen.hexdigest()


def _git(raiz: Path, *argumentos: str, comprobar: bool = True) -> str:
    proceso = subprocess.run(
        ["git", "-C", str(raiz), *argumentos], capture_output=True, text=True, check=False,
    )
    if comprobar and proceso.returncode:
        raise EvaluacionDenegada("no se pudo comprobar git")
    return proceso.stdout.strip()


def _autor(fase: int) -> Callable[[int, Optional[str], Optional[str], Optional[str], Optional[str]], int]:
    columnas_fase1 = {"decision_id", "estado", "final", "resolucion", "target_session"}

    def autorizar(
        accion: int, tabla: Optional[str], columna: Optional[str], _base: Optional[str], _disparador: Optional[str],
    ) -> int:
        nombre = tabla or ""
        if accion == sqlite3.SQLITE_ATTACH:
            return sqlite3.SQLITE_DENY
        if accion == sqlite3.SQLITE_READ:
            permitidas = _TABLAS_FASE0 | (_TABLAS_FASE2 if fase == 2 else frozenset())
            if fase == 1:
                permitidas |= {"ia_contrafactual"}
            if nombre not in permitidas:
                return sqlite3.SQLITE_DENY
            if fase == 1 and nombre == "ia_contrafactual" and (columna or "") not in columnas_fase1:
                return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    return autorizar


def abrir_fase(db: Path, fase: int) -> sqlite3.Connection:
    uri = db.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.set_authorizer(_autor(fase))
    return conn


def _salidas(raiz: Path) -> Tuple[Path, Path]:
    return raiz / _SALIDA / "resultado.json", raiz / _SALIDA / "apertura.json"


def _ahora(reloj: Optional[Callable[[], datetime]]) -> datetime:
    valor = reloj() if reloj is not None else datetime.now(timezone.utc)
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise EvaluacionDenegada("el reloj debe tener zona horaria")
    return valor


def _instante_base(db: Path) -> datetime:
    db = db.resolve()
    with abrir_fase(db, 0) as conn:
        fila = conn.execute("SELECT decision_ts,status FROM ia_pasada ORDER BY id DESC LIMIT 1").fetchone()
    if fila is None or str(fila[1]) != "OK":
        raise EvaluacionDenegada("la última pasada no está OK")
    try:
        instante = datetime.fromisoformat(str(fila[0]))
    except ValueError as exc:
        raise EvaluacionDenegada("instante de la última pasada ilegible") from exc
    if instante.tzinfo is None or instante.utcoffset() is None:
        raise EvaluacionDenegada("instante de la última pasada sin zona")
    return instante


def _entorno() -> Dict[str, str]:
    return {
        "python": platform.python_version(), "pandas": pandas.__version__,
        "exchange_calendars": exchange_calendars.__version__,
    }


def _wal_limpio(db: Path) -> None:
    wal = Path(str(db.resolve()) + "-wal")
    if wal.is_file() and wal.stat().st_size:
        raise EvaluacionDenegada("la base tiene un WAL no vacío")


def _git_head_bytes(raiz: Path, ruta: Path) -> bytes:
    proceso = subprocess.run(
        ["git", "-C", str(raiz), "show", f"HEAD:{ruta.as_posix()}"], capture_output=True, check=False,
    )
    if proceso.returncode:
        raise EvaluacionDenegada(f"{ruta.name} no está comiteado")
    return proceso.stdout


def _autorizacion(
    raiz: Path, cosecha: Optional[str], db: Optional[Path] = None,
    reloj: Optional[Callable[[], datetime]] = None,
) -> Mapping[str, Any]:
    raiz = raiz.resolve()
    if Path.cwd().resolve() != raiz:
        raise EvaluacionDenegada("el directorio de trabajo no es la raíz autorizada")
    ruta = raiz / _AUTORIZACION
    if not ruta.is_file():
        raise EvaluacionDenegada("falta la autorización")
    if ruta.read_bytes() != _git_head_bytes(raiz, _AUTORIZACION):
        raise EvaluacionDenegada("la autorización no es idéntica a HEAD")
    criterio = raiz / _CRITERIO
    if criterio.read_bytes() != _git_head_bytes(raiz, _CRITERIO):
        raise EvaluacionDenegada("el criterio no es idéntico a HEAD")
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluacionDenegada("autorización ilegible") from exc
    esperados: Dict[str, Any] = {
        "criterio_sha256": _sha(criterio), "codigo_sha256": huella_evaluador(raiz), "autoriza": True,
        "entorno": _entorno(),
    }
    if db is not None:
        db = db.resolve()
        _wal_limpio(db)
        if not db.is_file():
            raise EvaluacionDenegada("no existe la base autorizada")
        esperados["base_sha256"] = _sha(db)
    if any(datos.get(clave) != valor for clave, valor in esperados.items()) or (
        cosecha is not None and datos.get("cosecha") != cosecha
    ) or not isinstance(datos.get("cosecha"), str) or not datos["cosecha"]:
        raise EvaluacionDenegada("la autorización no coincide")
    try:
        instante = datetime.fromisoformat(str(datos["instante"]))
    except (KeyError, ValueError) as exc:
        raise EvaluacionDenegada("instante autorizado ilegible") from exc
    if instante.tzinfo is None or instante.utcoffset() is None:
        raise EvaluacionDenegada("instante autorizado sin zona horaria")
    if db is not None and instante != _instante_base(db):
        raise EvaluacionDenegada("el instante autorizado no coincide con la base")
    hoy_utc = _ahora(reloj).astimezone(timezone.utc).date()
    if hoy_utc <= instante.astimezone(timezone.utc).date():
        raise EvaluacionDenegada("aún no están completas las barras del día del instante")
    return datos


def _sin_salidas(raiz: Path) -> None:
    resultado, apertura = _salidas(raiz)
    if resultado.exists() or apertura.exists():
        raise EvaluacionDenegada("la evaluación ya fue abierta o realizada")


def _git_limpio(raiz: Path) -> None:
    if _git(raiz, "status", "--porcelain", "--untracked-files=no"):
        raise EvaluacionDenegada("el árbol de git no está limpio")


def _filas_episodios(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    con_entrada = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ia_contrafactual_entrada'"
    ).fetchone() is not None
    return conn.execute(
        "SELECT d.id, d.symbol, d.market, d.resolucion, d.target_session, "
        + ("e.ejecutable " if con_entrada else "NULL ")
        + "FROM ia_decision d JOIN ia_pasada p ON p.id=d.pasada_id "
        + ("LEFT JOIN ia_contrafactual_entrada e ON e.decision_id=d.id " if con_entrada else "")
        + "WHERE d.tipo='COMPRA' AND p.decision_ts>=? ORDER BY d.symbol,d.target_session,d.id",
        (madurez.CORTE.isoformat(timespec="seconds"),),
    ).fetchall()


def episodios(conn: sqlite3.Connection, instante: datetime) -> List[Episodio]:
    cerradas: Dict[str, Optional[date]] = {}
    detenidos: set[str] = set()
    fin_episodio: Dict[str, date] = {}
    salida: List[Episodio] = []
    for fila in _filas_episodios(conn):
        decision_id, symbol, market, grupo, texto, ejecutable = tuple(fila)
        if grupo not in {"COMPRAR", "DESCARTAR"}:
            raise EvaluacionDenegada("resolución de compra inesperada")
        sesion = date.fromisoformat(texto)
        if symbol in detenidos or (symbol in fin_episodio and sesion <= fin_episodio[symbol]):
            continue
        if ejecutable == 0:
            salida.append(Episodio(decision_id, symbol, market, grupo, sesion, "no_ejecutables"))
            continue
        if market not in cerradas:
            cerradas[market] = latest_expected_closed_session(market, instante, settlement_minutes=madurez.SETTLEMENT_MINUTES)
        ultima = cerradas[market]
        sesiones = [] if ultima is None else expected_sessions(market, sesion, ultima)
        maduro = len(sesiones) >= HORIZONTE_SESIONES
        if ejecutable is None:
            if maduro:
                salida.append(Episodio(decision_id, symbol, market, grupo, sesion, "sin_entrada"))
            else:
                detenidos.add(symbol)
            continue
        categoria = "maduros" if maduro else "madurando"
        salida.append(Episodio(decision_id, symbol, market, grupo, sesion, categoria))
        if maduro:
            fin_episodio[symbol] = sesiones[HORIZONTE_SESIONES - 1]
        else:
            detenidos.add(symbol)
    return salida


def _validar_equivalencia(lista: Sequence[Episodio], cuenta: madurez.Madurez) -> None:
    for grupo, esperado in (("COMPRAR", cuenta.aprobadas), ("DESCARTAR", cuenta.descartadas)):
        reales = tuple(sum(e.grupo == grupo and e.categoria == categoria for e in lista) for categoria in (
            "maduros", "madurando", "no_ejecutables", "sin_entrada",
        ))
        if reales != (esperado.maduros, esperado.madurando, esperado.no_ejecutables, esperado.sin_entrada):
            raise EvaluacionDenegada("los episodios no coinciden con madurez.contar")


def _puerta_madurez(db: Path, instante: datetime) -> Tuple[madurez.Madurez, List[Episodio]]:
    with abrir_fase(db, 0) as conn:
        cuenta = madurez.contar(conn, instante)
        lista = episodios(conn, instante)
    _validar_equivalencia(lista, cuenta)
    if cuenta.congelacion_rota:
        raise EvaluacionDenegada("la congelación está rota")
    if not cuenta.toca_evaluar:
        raise EvaluacionDenegada("todavía no toca evaluar")
    return cuenta, lista


def puertas(
    db: Path, *, cosecha: Optional[str] = None, raiz: Path = _RAIZ,
    reloj: Optional[Callable[[], datetime]] = None, cosecha_raiz: Optional[Path] = None,
) -> Puertas:
    db, raiz = db.resolve(), raiz.resolve()
    estados = [False] * 5
    try:
        autorizacion = _autorizacion(raiz, cosecha, db, reloj)
        instante = datetime.fromisoformat(str(autorizacion["instante"]))
        if cosecha_raiz is not None:
            try:
                load_vintage(str(autorizacion["cosecha"]), root_dir=cosecha_raiz)
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                raise EvaluacionDenegada("la cosecha autorizada no existe o cambió") from exc
        estados[0] = True
        _sin_salidas(raiz)
        estados[1] = True
        _git_limpio(raiz)
        estados[2] = True
        cuenta, _lista = _puerta_madurez(db, instante)
        estados[3] = True
        estados[4] = min(cuenta.aprobadas.maduros, cuenta.descartadas.maduros) >= madurez.MINIMO_POR_GRUPO
        return Puertas(estados[0], estados[1], estados[2], estados[3], estados[4], None)
    except EvaluacionDenegada as exc:
        return Puertas(estados[0], estados[1], estados[2], estados[3], estados[4], str(exc))


def _identidades(raiz: Path, db: Path, cosecha: str, instante: Optional[datetime] = None) -> Dict[str, Any]:
    return {
        "criterio_sha256": _sha(raiz / _CRITERIO), "codigo_sha256": huella_evaluador(raiz),
        "git_sha": _git(raiz, "rev-parse", "HEAD"), "base_sha256": _sha(db), "cosecha": cosecha,
        "instante": (instante or _instante_base(db)).isoformat(), "entorno": _entorno(), "semilla": SEMILLA,
    }


def _atomico(ruta: Path, datos: Mapping[str, Any]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + ".tmp")
    contenido = json.dumps(datos, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n"
    with temporal.open("w", encoding="utf-8") as fichero:
        fichero.write(contenido)
        fichero.flush()
        os.fsync(fichero.fileno())
    os.replace(temporal, ruta)
    descriptor = os.open(ruta.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _resultado_inconcluso(
    raiz: Path, db: Path, cosecha: str, motivo: str, cuenta: madurez.Madurez,
    excluidos: Optional[Mapping[str, Mapping[str, int]]] = None,
    n: Optional[Mapping[str, int]] = None,
    series_ausentes: Sequence[str] = (),
) -> Dict[str, Any]:
    maduros = {"COMPRAR": cuenta.aprobadas.maduros, "DESCARTAR": cuenta.descartadas.maduros}
    datos: Dict[str, Any] = {
        "veredicto": "INCONCLUSO", "motivo": motivo, "ic": None, "estimador": None,
        "media_grupo": {"COMPRAR": None, "DESCARTAR": None},
        "n": dict(n or maduros), "maduros": maduros,
        "excluidos": excluidos or {"COMPRAR": {}, "DESCARTAR": {}}, "coste_api": None,
        "carteras": None, "series_ausentes": list(series_ausentes),
        "secundario": None, "identidades": _identidades(raiz, db, cosecha),
    }
    _atomico(_salidas(raiz)[0], datos)
    return datos


def _fase1(db: Path, lista: Sequence[Episodio]) -> Tuple[List[Episodio], Dict[str, Dict[str, int]]]:
    exigidos = [e for e in lista if e.categoria in {"maduros", "sin_entrada"}]
    with abrir_fase(db, 1) as conn:
        filas = {int(f["decision_id"]): (str(f["estado"]), int(f["final"])) for f in conn.execute(
            "SELECT c.decision_id,c.estado,c.final FROM ia_contrafactual c "
            "JOIN ia_decision d ON d.id=c.decision_id JOIN ia_pasada p ON p.id=d.pasada_id "
            "WHERE d.tipo='COMPRA' AND p.decision_ts>=?",
            (madurez.CORTE.isoformat(timespec="seconds"),),
        )}
        decisiones = conn.execute(
            "SELECT c.decision_id,c.resolucion,c.target_session,d.resolucion,d.target_session,d.target_open,d.market "
            "FROM ia_contrafactual c JOIN ia_decision d ON d.id=c.decision_id "
            "JOIN ia_pasada p ON p.id=d.pasada_id WHERE d.tipo='COMPRA' AND p.decision_ts>=?",
            (madurez.CORTE.isoformat(timespec="seconds"),),
        ).fetchall()
        for fila in decisiones:
            try:
                apertura = datetime.fromisoformat(str(fila[5]))
                sesion = date.fromisoformat(str(fila[4]))
                if str(fila[1]) != str(fila[3]) or str(fila[2]) != str(fila[4]):
                    raise EvaluacionDenegada("decisión y contrafactual no coinciden")
                if apertura.tzinfo is None or apertura.utcoffset() is None:
                    raise EvaluacionDenegada("target_open sin zona")
                expected_sessions(str(fila[6]), sesion, sesion)
            except (TypeError, ValueError, KeyError) as exc:
                raise EvaluacionDenegada("decisión de fase 1 ilegible") from exc
    faltan = sum(e.decision_id not in filas or filas[e.decision_id][1] != 1 for e in exigidos)
    if faltan:
        raise EvaluacionDenegada(f"faltan {faltan} casos por completar")
    excluidos: Dict[str, Dict[str, int]] = {"COMPRAR": {}, "DESCARTAR": {}}
    usables: List[Episodio] = []
    for episodio in exigidos:
        estado = filas[episodio.decision_id][0]
        if episodio.categoria == "sin_entrada" and estado in {STOP, HORIZONTE, ABIERTA}:
            raise EvaluacionDenegada("contradicción en un caso sin entrada")
        if episodio.categoria == "maduros" and estado not in {STOP, HORIZONTE, NO_EJECUTABLE, *_EXCLUIDOS}:
            raise EvaluacionDenegada("estado final inesperado")
        excluir = episodio.categoria == "sin_entrada" or estado in _EXCLUIDOS or estado == NO_EJECUTABLE
        if excluir:
            excluidos[episodio.grupo][estado] = excluidos[episodio.grupo].get(estado, 0) + 1
        elif episodio.categoria == "maduros":
            usables.append(episodio)
    return usables, excluidos


def _inconcluso_previo(
    lista: Sequence[Episodio], usables: Sequence[Episodio], excluidos: Mapping[str, Mapping[str, int]],
) -> Optional[str]:
    for grupo in ("COMPRAR", "DESCARTAR"):
        denominador = sum(e.grupo == grupo and e.categoria in {"maduros", "sin_entrada"} for e in lista)
        malos = sum(excluidos[grupo].values())
        if denominador and malos / denominador > 0.05:
            return "DATOS"
    if any(sum(e.grupo == grupo for e in usables) < madurez.MINIMO_POR_GRUPO for grupo in ("COMPRAR", "DESCARTAR")):
        return "MUESTRA"
    ficticios = {
        grupo: [Observacion(e.sesion, 0.0, 1.0) for e in usables if e.grupo == grupo]
        for grupo in ("COMPRAR", "DESCARTAR")
    }
    ic = intervalo_bloques(ficticios["COMPRAR"], ficticios["DESCARTAR"], 0.0)
    return "BLOQUES" if ic.bajo is None else None


def _cuantitativos(db: Path, ids: Sequence[int]) -> Dict[int, Mapping[str, Any]]:
    if not ids:
        return {}
    marcas = ",".join("?" for _ in ids)
    with abrir_fase(db, 1) as conn:
        filas = conn.execute(f"SELECT id,cuantitativo FROM ia_decision WHERE id IN ({marcas})", tuple(ids)).fetchall()
    try:
        salida = {int(f[0]): json.loads(f[1]) for f in filas}
        for datos in salida.values():
            niveles = datos["niveles"]
            currency = datos["currency"]
            score = datos["score"]
            stop = niveles["stop"]
            if not isinstance(currency, str) or not currency or not all(
                math.isfinite(float(valor)) for valor in (score, stop)
            ):
                raise ValueError
        if len(salida) != len(set(ids)):
            raise ValueError
        return salida
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise EvaluacionDenegada("cuantitativo ilegible") from exc


def _serie(vintage: VintageLoad, symbol: str, market: str, *, fx: bool = False) -> SeriePrecios:
    if symbol not in vintage.by_symbol:
        raise EvaluacionDenegada(f"falta {symbol} en la cosecha")
    barras = vintage.by_symbol[symbol].execution_prices
    fechas = tuple(fecha_fx(m) if fx else session_date_of(m, market) for m in barras.index)
    if any(d is None for d in fechas):
        raise EvaluacionDenegada(f"sesión ilegible en {symbol}")
    crudo = vintage.by_symbol[symbol].raw
    fechas_split = tuple(fecha_fx(m) if fx else session_date_of(m, market) for m in crudo.index)
    splits = tuple((d, float(r)) for d, r in zip(fechas_split, crudo["Stock Splits"]) if d is not None and float(r))
    return SeriePrecios(
        tuple(d for d in fechas if d is not None), tuple(float(v) for v in barras["Open"]),
        tuple(float(v) for v in barras["Close"]), splits,
    )


def _decisiones_compra(db: Path) -> List[sqlite3.Row]:
    with abrir_fase(db, 1) as conn:
        return conn.execute(
            "SELECT d.id,d.symbol,d.market,d.target_session,d.cuantitativo,e.ejecutable "
            "FROM ia_decision d JOIN ia_pasada p ON p.id=d.pasada_id "
            "LEFT JOIN ia_contrafactual_entrada e ON e.decision_id=d.id "
            "WHERE d.tipo='COMPRA' AND p.decision_ts>=? ORDER BY d.id",
            (madurez.CORTE.isoformat(timespec="seconds"),),
        ).fetchall()


def _comprobar_cosecha(
    cosecha: str, cosecha_raiz: Path, decisiones: Sequence[sqlite3.Row], instante: datetime,
    cuantitativos: Mapping[int, Mapping[str, Any]], series_ausentes: Sequence[str] = (),
    usables: Sequence[int] = (),
) -> Tuple[VintageLoad, SeriePrecios, date]:
    try:
        vintage = load_vintage(cosecha, root_dir=cosecha_raiz)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise EvaluacionDenegada("cosecha ilegible o alterada") from exc
    if REFERENCIA not in vintage.by_symbol:
        raise EvaluacionDenegada("falta EUNL.DE en la cosecha")
    peticion = vintage.manifest.get("request", {})
    inicio_esperado = (madurez.CORTE.date() - timedelta(days=10)).isoformat()
    fecha_instante = instante.astimezone(timezone.utc).date()
    fin_esperado = (fecha_instante + timedelta(days=1)).isoformat()
    if peticion.get("start") != inicio_esperado or peticion.get("end") != fin_esperado or not peticion.get(
        "end_exclusive"
    ):
        raise EvaluacionDenegada("la petición de la cosecha no coincide con el intervalo autorizado")
    referencia = _serie(vintage, REFERENCIA, "XETRA")
    sesiones_fin = expected_sessions("XETRA", fecha_instante - timedelta(days=14), fecha_instante)
    if not sesiones_fin:
        raise EvaluacionDenegada("no hay sesión XETRA para el fin")
    fin_xetra = sesiones_fin[-1]
    ejecutables = [fila for fila in decisiones if fila[5] == 1]
    permitidas = set(series_ausentes)
    faltantes = {str(fila[1]) for fila in ejecutables if str(fila[1]) not in vintage.by_symbol}
    inesperadas = faltantes - permitidas
    if inesperadas:
        raise EvaluacionDenegada("faltan series exigidas: " + ", ".join(sorted(inesperadas)))
    if ejecutables:
        primera = min(date.fromisoformat(str(fila[3])) for fila in ejecutables)
        ultimas = []
        ids_usables = set(usables)
        for fila in ejecutables:
            if int(fila[0]) not in ids_usables:
                continue
            sesion = date.fromisoformat(str(fila[3]))
            plaza = expected_sessions(str(fila[2]), sesion, sesion + timedelta(days=90))
            if len(plaza) < HORIZONTE_SESIONES:
                raise EvaluacionDenegada("calendario insuficiente para el horizonte")
            ultimas.append(plaza[HORIZONTE_SESIONES - 1])
        cobertura_fin = max([fin_xetra, *ultimas])
        esperadas = set(expected_sessions("XETRA", primera, cobertura_fin))
        indices_ref = {d: i for i, d in enumerate(referencia.fechas)}
        faltan = esperadas - set(indices_ref)
        if faltan:
            raise EvaluacionDenegada(f"faltan {len(faltan)} sesiones de EUNL.DE")
        for dia in esperadas:
            indice = indices_ref[dia]
            if not all(
                math.isfinite(valor) and valor > 0
                for valor in (referencia.aperturas[indice], referencia.cierres[indice])
            ):
                raise EvaluacionDenegada("precio inválido de EUNL.DE")
    series_comprobadas: set[str] = set()
    for fila in ejecutables:
        _decision_id, symbol, market, texto, _crudo, _ejecutable = tuple(fila)
        sesion = date.fromisoformat(str(texto))
        sesiones = expected_sessions(str(market), sesion, sesion + timedelta(days=90))
        if len(sesiones) < HORIZONTE_SESIONES:
            raise EvaluacionDenegada("calendario insuficiente para el horizonte")
        if str(symbol) not in faltantes and str(symbol) not in series_comprobadas:
            serie_valor = _serie(vintage, str(symbol), str(market))
            if not any(
                math.isfinite(float(c)) and float(c) > 0
                for d, c in zip(serie_valor.fechas, serie_valor.cierres) if d <= sesion
            ):
                raise EvaluacionDenegada(f"la serie de {symbol} empieza después de su entrada")
            series_comprobadas.add(str(symbol))
    primer_dia = min((date.fromisoformat(str(f[3])) for f in ejecutables), default=fecha_instante)
    monedas = sorted({str(cuantitativos[int(f[0])]["currency"]) for f in ejecutables} - {"EUR"})
    for moneda in monedas:
        simbolo = f"EUR{moneda}=X"
        if simbolo not in vintage.by_symbol:
            raise EvaluacionDenegada(f"falta {simbolo} en la cosecha")
        serie_fx = _serie(vintage, simbolo, "", fx=True)
        for desplazamiento in range((cobertura_fin - primer_dia).days + 1):
            dia = primer_dia + timedelta(days=desplazamiento)
            if fx_de(serie_fx.fechas, serie_fx.cierres, dia, moneda) is None:
                raise EvaluacionDenegada(f"falta FX de {moneda} para {dia}")
    return vintage, referencia, fecha_instante


def _abrir(raiz: Path, identidades: Mapping[str, Any], instante: datetime) -> None:
    ruta = _salidas(raiz)[1]
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = {"instante": instante.isoformat(), **identidades}
    contenido = (json.dumps(datos, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    descriptor = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as fichero:
        fichero.write(contenido)
        fichero.flush()
        os.fsync(fichero.fileno())
    descriptor_directorio = os.open(ruta.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor_directorio)
    finally:
        os.close(descriptor_directorio)


def _leer_casos(
    db: Path, usables: Sequence[Episodio],
) -> Tuple[List[Caso], List[Caso], Dict[int, float], Optional[str]]:
    ids = {e.decision_id for e in usables}
    with abrir_fase(db, 2) as conn:
        filas = conn.execute(
            "SELECT c.decision_id,c.symbol,c.resolucion,c.target_session,c.estado,c.entrada,c.salida,c.hasta_session,"
            "c.retorno_r,d.market,d.target_open,d.cuantitativo,d.resolucion,c.final,e.ejecutable "
            "FROM ia_contrafactual c JOIN ia_decision d ON d.id=c.decision_id "
            "JOIN ia_pasada p ON p.id=d.pasada_id "
            "JOIN ia_contrafactual_entrada e ON e.decision_id=d.id "
            "WHERE d.tipo='COMPRA' AND p.decision_ts>=? AND e.ejecutable=1",
            (madurez.CORTE.isoformat(timespec="seconds"),),
        ).fetchall()
    casos: List[Caso] = []
    candidatas: List[Caso] = []
    retornos_r: Dict[int, float] = {}
    errores_cartera: list[str] = []
    for f in filas:
        decision_id = int(f[0])
        if str(f[2]) != str(f[12]):
            mensaje = "resolución distinta entre decisión y contrafactual"
            if decision_id in ids:
                raise EvaluacionDenegada(mensaje)
            errores_cartera.append(f"decisión {decision_id}: {mensaje}")
            continue
        estado, final = str(f[4]), int(f[13])
        if str(f[4]) in _EXCLUIDOS or estado == NO_EJECUTABLE:
            continue
        cerrado = final == 1 and estado in {STOP, HORIZONTE}
        abierto = final == 0 and estado == ABIERTA and f[5] is not None
        if not cerrado and not abierto:
            if decision_id in ids:
                raise EvaluacionDenegada("estado final inesperado")
            errores_cartera.append(f"decisión {decision_id}: estado final inesperado")
            continue
        try:
            cuantitativo = json.loads(f[11])
            niveles = cuantitativo["niveles"]
            entrada, stop = float(f[5]), float(niveles["stop"])
            salida = float(f[6]) if cerrado else None
            score = float(cuantitativo["score"])
            currency = str(cuantitativo["currency"])
            sesion_salida = date.fromisoformat(str(f[7])) if cerrado else None
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            if decision_id in ids:
                raise EvaluacionDenegada("caso utilizable ilegible") from exc
            errores_cartera.append(f"decisión {decision_id}: caso de cartera ilegible")
            continue
        numeros = (entrada, stop, score) if salida is None else (entrada, salida, stop, score)
        if not all(map(math.isfinite, numeros)) or stop >= entrada:
            if decision_id in ids:
                raise EvaluacionDenegada("estado final o precios inesperados")
            errores_cartera.append(f"decisión {decision_id}: estado final o precios inesperados")
            continue
        caso = Caso(
            decision_id, str(f[1]), str(f[9]), currency, str(f[12]), date.fromisoformat(str(f[3])),
            sesion_salida, entrada, salida, stop, score, datetime.fromisoformat(str(f[10])), estado,
        )
        candidatas.append(caso)
        if decision_id in ids and cerrado:
            casos.append(caso)
        if decision_id in ids and f[8] is not None:
            retornos_r[decision_id] = float(f[8])
    if len(casos) != len(ids):
        raise EvaluacionDenegada("faltan casos utilizables tras la apertura")
    error = "; ".join(errores_cartera) or None
    return casos, candidatas, retornos_r, error


def _euros_api(db: Path) -> Tuple[float, Dict[date, float]]:
    with abrir_fase(db, 2) as conn:
        filas = conn.execute(
            "SELECT l.coste_eur,l.created_at FROM ia_llamada l JOIN ia_paquete p ON p.input_hash=l.input_hash "
            "JOIN ia_pasada x ON x.id=l.pasada_id WHERE p.tipo='COMPRA' AND x.decision_ts>=?",
            (madurez.CORTE.isoformat(timespec="seconds"),),
        ).fetchall()
    por_dia: Dict[date, float] = {}
    for coste, texto in filas:
        instante = datetime.fromisoformat(texto)
        if instante.tzinfo is None or instante.utcoffset() is None:
            raise EvaluacionDenegada("fecha de coste API sin zona")
        dia = instante.astimezone(timezone.utc).date()
        por_dia[dia] = por_dia.get(dia, 0.0) + float(coste)
    return sum(por_dia.values()), por_dia


def _ventas_ia(db: Path) -> Dict[str, Any]:
    with abrir_fase(db, 2) as conn:
        tablas = {str(f[0]) for f in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"ia_posicion", "ia_orden"}.issubset(tablas):
            return {"n": 0, "retorno_real_pct_medio": None, "retorno_mantener_pct_medio": None}
        filas = conn.execute(
            "SELECT DISTINCT p.id,p.entry_price,p.exit_price,c.retorno_pct "
            "FROM ia_posicion p JOIN ia_orden o ON o.position_id=p.id "
            "JOIN ia_decision d ON d.id=p.decision_apertura_id "
            "JOIN ia_pasada x ON x.id=d.pasada_id "
            "JOIN ia_contrafactual c ON c.decision_id=d.id "
            "WHERE p.estado='CERRADA' AND o.proposito='EXIT_IA' AND o.estado='EJECUTADA' "
            "AND x.decision_ts>=? AND c.final=1 AND c.estado IN (?,?)",
            (madurez.CORTE.isoformat(timespec="seconds"), STOP, HORIZONTE),
        ).fetchall()
    try:
        reales = [(float(f[2]) / float(f[1]) - 1.0) * 100.0 for f in filas]
        mantener = [float(f[3]) for f in filas]
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise EvaluacionDenegada("venta de IA ilegible") from exc
    return {
        "n": len(filas),
        "retorno_real_pct_medio": None if not reales else sum(reales) / len(reales),
        "retorno_mantener_pct_medio": None if not mantener else sum(mantener) / len(mantener),
    }


def evaluar(
    db: Path, cosecha_raiz: Path, *, raiz: Path = _RAIZ,
    reloj: Optional[Callable[[], datetime]] = None,
) -> Dict[str, Any]:
    db, raiz = db.resolve(), raiz.resolve()
    instante_apertura = _ahora(reloj)
    autorizacion = _autorizacion(raiz, None, db, lambda: instante_apertura)
    instante_evaluacion = datetime.fromisoformat(str(autorizacion["instante"]))
    cosecha = str(autorizacion["cosecha"])
    series_ausentes_crudo = autorizacion.get("series_ausentes", [])
    if not isinstance(series_ausentes_crudo, list) or not all(isinstance(s, str) for s in series_ausentes_crudo):
        raise EvaluacionDenegada("series_ausentes ilegible")
    series_ausentes = sorted(set(series_ausentes_crudo))
    _sin_salidas(raiz)
    _git_limpio(raiz)
    cuenta, lista = _puerta_madurez(db, instante_evaluacion)
    if min(cuenta.aprobadas.maduros, cuenta.descartadas.maduros) < madurez.MINIMO_POR_GRUPO:
        if _sha(db) != str(autorizacion["base_sha256"]):
            raise EvaluacionDenegada("la base cambió antes de escribir el resultado")
        return _resultado_inconcluso(raiz, db, cosecha, "MUESTRA", cuenta, series_ausentes=series_ausentes)
    usables, excluidos = _fase1(db, lista)
    motivo = _inconcluso_previo(lista, usables, excluidos)
    if motivo is not None:
        n = {grupo: sum(e.grupo == grupo for e in usables) for grupo in ("COMPRAR", "DESCARTAR")}
        if _sha(db) != str(autorizacion["base_sha256"]):
            raise EvaluacionDenegada("la base cambió antes de escribir el resultado")
        return _resultado_inconcluso(raiz, db, cosecha, motivo, cuenta, excluidos, n, series_ausentes)
    decisiones = _decisiones_compra(db)
    ejecutables = {int(f[0]): f[5] for f in decisiones}
    if any(ejecutables.get(e.decision_id) != 1 for e in usables):
        raise EvaluacionDenegada("caso utilizable sin entrada ejecutable")
    cuantitativos = _cuantitativos(db, [int(f[0]) for f in decisiones])
    vintage, referencia, fin = _comprobar_cosecha(
        cosecha, cosecha_raiz, decisiones, instante_evaluacion, cuantitativos, series_ausentes,
        [e.decision_id for e in usables],
    )
    identidades = _identidades(raiz, db, cosecha, instante_evaluacion)
    for clave in ("criterio_sha256", "codigo_sha256", "base_sha256", "instante", "entorno"):
        if autorizacion.get(clave) != identidades[clave]:
            raise EvaluacionDenegada(f"la identidad {clave} cambió antes de abrir")
    _abrir(raiz, identidades, instante_apertura)
    casos, candidatas, retornos_r, error_carteras = _leer_casos(db, usables)
    monedas = sorted({c.currency for c in candidatas if c.currency != "EUR"})
    series_fx = {moneda: _serie(vintage, f"EUR{moneda}=X", "", fx=True) for moneda in monedas}
    fx = {moneda: (serie.fechas, serie.cierres) for moneda, serie in series_fx.items()}
    observaciones: Dict[str, List[Observacion]] = {"COMPRAR": [], "DESCARTAR": []}
    for caso in casos:
        if caso.sesion_salida is None:
            raise EvaluacionDenegada("caso métrico sin salida")
        fechas, valores = fx.get(caso.currency, ((), ()))
        fx_entrada = fx_de(fechas, valores, caso.sesion_entrada, caso.currency)
        fx_salida = fx_de(fechas, valores, caso.sesion_salida, caso.currency)
        if fx_entrada is None or fx_salida is None:
            raise EvaluacionDenegada(f"falta FX de {caso.currency} para el caso {caso.decision_id}")
        exceso, nocional = exceso_neto(caso, fx_entrada, fx_salida, referencia)
        observaciones[caso.grupo].append(Observacion(caso.sesion_entrada, exceso, nocional))
    euros_api, api_por_dia = _euros_api(db)
    coste_api = coste_api_por_aprobado(euros_api, observaciones["COMPRAR"])
    ic = intervalo_bloques(observaciones["COMPRAR"], observaciones["DESCARTAR"], coste_api)
    medias = {
        "COMPRAR": sum(o.exceso - coste_api for o in observaciones["COMPRAR"]) / len(observaciones["COMPRAR"]),
        "DESCARTAR": sum(o.exceso for o in observaciones["DESCARTAR"]) / len(observaciones["DESCARTAR"]),
    }
    no_ejecutables = {
        grupo: sum(e.grupo == grupo and e.categoria == "no_ejecutables" for e in lista)
        for grupo in ("COMPRAR", "DESCARTAR")
    }
    veredicto_final = veredicto(ic)
    try:
        if error_carteras is not None:
            raise ValueError(error_carteras)
        candidatas_cartera = [c for c in candidatas if c.symbol not in series_ausentes]
        series = {c.symbol: _serie(vintage, c.symbol, c.market) for c in candidatas_cartera}
        detalle_carteras: Any = {
            k: v.como_dict() for k, v in carteras(
                candidatas_cartera, series, fx, referencia, api_por_dia, fin,
            ).items()
        }
    except Exception as exc:
        detalle_carteras = {"error": f"{type(exc).__name__}: {exc}"}
    try:
        detalle_secundario: Any = secundario(casos, retornos_r, no_ejecutables)
        detalle_secundario["ventas_ia"] = _ventas_ia(db)
    except Exception as exc:
        detalle_secundario = {"error": f"{type(exc).__name__}: {exc}"}
    datos = {
        "veredicto": veredicto_final, "motivo": None if ic.bajo is not None else "BLOQUES",
        "ic": None if ic.bajo is None else [ic.bajo, ic.alto],
        "estimador": estimador(observaciones["COMPRAR"], observaciones["DESCARTAR"], coste_api),
        "media_grupo": medias, "n": {g: len(observaciones[g]) for g in observaciones},
        "maduros": {"COMPRAR": cuenta.aprobadas.maduros, "DESCARTAR": cuenta.descartadas.maduros},
        "excluidos": excluidos,
        "coste_api": {"euros": euros_api, "por_nocional_aprobado": coste_api},
        "carteras": detalle_carteras, "series_ausentes": series_ausentes,
        "secundario": detalle_secundario, "identidades": identidades,
    }
    if _sha(db) != str(autorizacion["base_sha256"]):
        raise EvaluacionDenegada("la base cambió después de abrir")
    _atomico(_salidas(raiz)[0], datos)
    return datos


__all__ = [
    "Episodio", "EvaluacionDenegada", "Puertas", "abrir_fase", "episodios", "evaluar", "huella_evaluador",
    "puertas",
]
