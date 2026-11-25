"""Lectura por fases y puertas de la evaluación única del contrafactual."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import sqlite3
import subprocess
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import exchange_calendars
import pandas

from advisor.data.calendars import expected_sessions
from advisor.data.sessions import latest_expected_closed_session, session_date_of
from advisor.research.vintage import VintageLoad, load_vintage
from superbot.ia import madurez
from superbot.ia.cartera import evaluar_gate_apertura, evaluar_stop
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
    Caso,
    DatoCompartidoInvalido,
    Observacion,
    SeriePrecios,
    carteras,
    coste_api_por_aprobado,
    estimador,
    exceso_neto,
    fx_de,
    inferencia_posible,
    intervalo_jackknife,
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
# Sesiones de la plaza, contando la de entrada como la 1, que se esperan unas barras antes de resolver (D-88).
SESIONES_DE_ESPERA = 25
HOLGURA_GATE = 1e-4
# Sesiones seguidas de EUNL.DE que se pueden declarar ausentes: más dejaría casos sin mercado que restar.
MAX_HUECO_REFERENCIA = 3
SIN_DATOS = "SIN_DATOS"
EXCLUSION = "EXCLUSION"
FALTA, CONTRADICE = "FALTA", "CONTRADICE"
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
    # Sesiones de su plaza ya cerradas, contando la de entrada como la 1.
    sesiones: int = 0
    fin: Optional[date] = None


@dataclass(frozen=True)
class Determinacion:
    """Qué pasó con un valor que dejó de tener barras: lo declara el propietario antes de abrir (D-88)."""

    decision_id: int
    tipo: str
    justificacion: str
    fuente: str
    sesion_salida: Optional[date] = None
    precio_entrada: float = 0.0
    precio_salida: float = 0.0


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
        return self.motivo is None and all((
            self.autorizacion, self.sin_resultado, self.git_limpio, self.madurez_valida,
        ))


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
    columnas_fase1 = {
        "decision_id", "estado", "final", "resolucion", "target_session", "sesiones", "hasta_session",
    }

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
                salida.append(Episodio(
                    decision_id, symbol, market, grupo, sesion, "sin_entrada", len(sesiones),
                    sesiones[HORIZONTE_SESIONES - 1],
                ))
            else:
                detenidos.add(symbol)
            continue
        categoria = "maduros" if maduro else "madurando"
        salida.append(Episodio(
            decision_id, symbol, market, grupo, sesion, categoria, len(sesiones),
            sesiones[HORIZONTE_SESIONES - 1] if maduro else None,
        ))
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
        estados[0] = True
        _sin_salidas(raiz)
        estados[1] = True
        _git_limpio(raiz)
        estados[2] = True
        cuenta, lista = _puerta_madurez(db, instante)
        estados[3] = True
        estados[4] = min(cuenta.aprobadas.maduros, cuenta.descartadas.maduros) >= madurez.MINIMO_POR_GRUPO
        if cosecha_raiz is not None and estados[4]:  # sin muestra, ``evaluar`` concluye sin mirar la cosecha
            estados[4] = False
            _preparar(db, cosecha_raiz, autorizacion, instante, lista)
            estados[4] = True
        return Puertas(estados[0], estados[1], estados[2], estados[3], estados[4], None)
    except EvaluacionDenegada as exc:
        return Puertas(estados[0], estados[1], estados[2], estados[3], estados[4], str(exc))


def _identidades(raiz: Path, db: Path, cosecha: str, instante: Optional[datetime] = None) -> Dict[str, Any]:
    return {
        "criterio_sha256": _sha(raiz / _CRITERIO), "codigo_sha256": huella_evaluador(raiz),
        "git_sha": _git(raiz, "rev-parse", "HEAD"), "base_sha256": _sha(db), "cosecha": cosecha,
        "instante": (instante or _instante_base(db)).isoformat(), "entorno": _entorno(),
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
    detalle: Optional[Mapping[str, Any]] = None, identidades: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    maduros = {"COMPRAR": cuenta.aprobadas.maduros, "DESCARTAR": cuenta.descartadas.maduros}
    datos: Dict[str, Any] = {
        "veredicto": "INCONCLUSO", "motivo": motivo, "ic": None, "estimador": None,
        "media_grupo": {"COMPRAR": None, "DESCARTAR": None},
        "n": dict(n or maduros), "maduros": maduros,
        "excluidos": excluidos or {"COMPRAR": {}, "DESCARTAR": {}}, "coste_api": None,
        "carteras": None, "secundario": None,
        "identidades": dict(identidades or _identidades(raiz, db, cosecha)), **(detalle or {}),
    }
    _atomico(_salidas(raiz)[0], datos)
    return datos


def _sesiones(market: str, entrada: date, instante: datetime) -> Sequence[date]:
    ultima = latest_expected_closed_session(market, instante, settlement_minutes=madurez.SETTLEMENT_MINUTES)
    return () if ultima is None else expected_sessions(market, entrada, ultima)


def _sesiones_cerradas(market: str, entrada: date, instante: datetime) -> int:
    return len(_sesiones(market, entrada, instante))


def _sin_huecos(market: str, entrada: date, estado: str, hasta: Any, barras: Any) -> bool:
    """Si el desenlace guardado vio una barra por cada sesión de su plaza.

    Producción sigue las barras que le sirve el proveedor: con un hueco, su «sesión 20» es la 21 y un stop de
    la sesión perdida no existe. Sobra o falta una barra y el desenlace no es el del criterio.
    """

    try:
        ultima = date.fromisoformat(str(hasta))
        sesiones, vistas = expected_sessions(market, entrada, ultima), int(barras)
    except (TypeError, ValueError):
        return False
    # Una barra en festivo puede compensar un hueco en el recuento, pero no es una salida.
    return ultima in sesiones and len(sesiones) == vistas and (estado != HORIZONTE or vistas == HORIZONTE_SESIONES)


def _es_sesion(market: str, texto: str) -> bool:
    try:
        dia = date.fromisoformat(texto)
        return dia in expected_sessions(market, dia, dia)
    except ValueError:
        return False


def _barras_de_cosecha(
    vintage: VintageLoad, symbol: str, market: str, sesion: date,
) -> Dict[date, set[Tuple[float, float]]]:
    """Apertura y mínimo de cada sesión oficial, en la escala de la entrada; más de uno si se contradicen."""

    if symbol not in vintage.by_symbol:
        return {}
    vista = vintage.by_symbol[symbol].execution_prices
    serie, escala = _serie(vintage, symbol, market), 1.0
    oficiales = set(serie.fechas)
    for fecha_split, ratio in serie.splits:
        escala *= ratio if fecha_split > sesion else 1.0
    barras: Dict[date, set[Tuple[float, float]]] = {}
    for marca, apertura, minimo, cierre in zip(vista.index, vista["Open"], vista["Low"], vista["Close"]):
        dia = session_date_of(marca, market)
        if dia in oficiales and all(math.isfinite(v) and v > 0 for v in (apertura, minimo, cierre)):
            barras.setdefault(dia, set()).add((float(apertura) * escala, float(minimo) * escala))
    return barras


def _saltos(stop: float, apertura: float, minimo: float) -> set[bool]:
    return {
        evaluar_stop(stop * factor, apertura, minimo).disparado
        for factor in (1 - HOLGURA_GATE, 1.0, 1 + HOLGURA_GATE)
    }


def _contraste(
    vintage: VintageLoad, symbol: str, market: str, sesion: date, estado: str, hasta: date, stop: float,
) -> Optional[str]:
    """Qué dice la cosecha, por las sesiones oficiales, de un estado y una fecha guardados.

    El recuento no ve una barra repetida que compensa un hueco. No calcula rendimientos: usa lo que la fase 1 ya
    conoce. Donde la serie no llega no se concluye nada, y el stop lleva la misma holgura que el gate.
    """

    barras = _barras_de_cosecha(vintage, symbol, market, sesion)
    falta = False
    for dia in expected_sessions(market, sesion, hasta) if barras else ():
        if dia not in barras or len(barras[dia]) > 1:
            falta = falta or min(barras) < dia < max(barras) or dia in barras
            continue
        (apertura, minimo), = barras[dia]
        saltos = _saltos(stop, apertura, minimo)
        if (dia < hasta and False not in saltos) or (dia == hasta and (estado == STOP) not in saltos):
            return CONTRADICE
    return FALTA if falta else None


def _stop_en_cosecha(
    vintage: VintageLoad, symbol: str, market: str, sesion: date, hasta: date, stop: float,
) -> Optional[Tuple[date, float]]:
    """Primera sesión hasta ``hasta`` en la que el stop salta sin duda, y a qué precio."""

    barras = _barras_de_cosecha(vintage, symbol, market, sesion)
    for dia in expected_sessions(market, sesion, hasta) if barras else ():
        for apertura, minimo in barras.get(dia, ()) if len(barras.get(dia, ())) == 1 else ():
            precio = evaluar_stop(stop, apertura, minimo).precio_fill
            if False not in _saltos(stop, apertura, minimo) and precio is not None:
                return dia, precio
    return None


def _fase1(
    db: Path, lista: Sequence[Episodio], determinaciones: Mapping[int, Determinacion], rechazadas: Sequence[int],
    invalidadas: Mapping[int, str], vintage: Optional[VintageLoad] = None,
    cuantitativos: Optional[Mapping[int, Mapping[str, Any]]] = None,
) -> Tuple[List[Episodio], Dict[str, Dict[str, int]], List[int]]:
    """Casos utilizables, excluidos por grupo y los que se resuelven con un resultado económico declarado."""

    exigidos = [e for e in lista if e.categoria in {"maduros", "sin_entrada"}]
    with abrir_fase(db, 1) as conn:
        filas = conn.execute(
            "SELECT c.decision_id,c.estado,c.final,c.resolucion,c.target_session,d.resolucion,d.target_session,"
            "d.target_open,d.market,c.sesiones,c.hasta_session FROM ia_contrafactual c "
            "JOIN ia_decision d ON d.id=c.decision_id JOIN ia_pasada p ON p.id=d.pasada_id "
            "WHERE d.tipo='COMPRA' AND p.decision_ts>=?",
            (madurez.CORTE.isoformat(timespec="seconds"),),
        ).fetchall()
    estados: Dict[int, Tuple[str, int]] = {}
    hastas: Dict[int, str] = {}
    con_huecos: set[int] = set()
    for fila in filas:
        try:
            apertura, sesion = datetime.fromisoformat(str(fila[7])), date.fromisoformat(str(fila[6]))
            if str(fila[3]) != str(fila[5]) or str(fila[4]) != str(fila[6]):
                raise EvaluacionDenegada("decisión y contrafactual no coinciden")
            if apertura.tzinfo is None or apertura.utcoffset() is None:
                raise EvaluacionDenegada("target_open sin zona")
            expected_sessions(str(fila[8]), sesion, sesion)
        except (TypeError, ValueError, KeyError) as exc:
            raise EvaluacionDenegada("decisión de fase 1 ilegible") from exc
        estado, final = str(fila[1]), int(fila[2])
        if estado in {STOP, HORIZONTE} and not _sin_huecos(str(fila[8]), sesion, estado, fila[10], fila[9]):
            con_huecos.add(int(fila[0]))
        estados[int(fila[0])], hastas[int(fila[0])] = (estado, final), str(fila[10])
    excluidos: Dict[str, Dict[str, int]] = {"COMPRAR": {}, "DESCARTAR": {}}
    usables: List[Episodio] = []
    con_exclusion: List[int] = []
    faltan = 0
    for episodio in exigidos:
        # Una apertura que el gate rechaza no abre episodio: ni se espera ni penaliza.
        if episodio.categoria == "sin_entrada" and episodio.decision_id in rechazadas:
            continue
        declarada = determinaciones.get(episodio.decision_id)
        excluida = declarada is not None and declarada.tipo == EXCLUSION
        # Una entrada retirada es falta de datos, y una exclusión declarada la resuelve; una rechazada, no.
        invalida = invalidadas.get(episodio.decision_id) if episodio.categoria == "maduros" else None
        if invalida is not None and not (excluida and invalida == SIN_BARRA_DE_ENTRADA):
            estado = invalidadas[episodio.decision_id]
            excluidos[episodio.grupo][estado] = excluidos[episodio.grupo].get(estado, 0) + 1
            continue
        estado, final = estados.get(episodio.decision_id, (DATOS_INCOMPLETOS, 0))
        # Un stop anterior manda sobre una exclusión aunque falten barras, al bot o a la cosecha: una barra que falta
        # puede esconder un stop, no inventarlo. Un horizonte no se sostiene sin todas.
        stop_manda = excluida and estado == STOP and _es_sesion(episodio.market, hastas[episodio.decision_id])
        if not stop_manda and (invalida is not None or episodio.decision_id in con_huecos):
            estado, final = DATOS_INCOMPLETOS, 0
        if vintage is not None and cuantitativos is not None and estado in {STOP, HORIZONTE}:
            contraste = _contraste(
                vintage, episodio.symbol, episodio.market, episodio.sesion, estado,
                date.fromisoformat(hastas[episodio.decision_id]),
                float(cuantitativos[episodio.decision_id]["niveles"]["stop"]),
            )
            if contraste is not None and not (contraste == FALTA and stop_manda):
                estado, final = DATOS_INCOMPLETOS, 0
        if not final or estado == SIN_BARRA_DE_ENTRADA:
            if episodio.sesiones < SESIONES_DE_ESPERA:
                faltan += 1
                continue
            estado = estado if final else DATOS_INCOMPLETOS
        if episodio.categoria == "sin_entrada":
            if estado == NO_EJECUTABLE:
                continue
            estado = estado if estado in _EXCLUIDOS else DATOS_INCOMPLETOS
        elif estado in {STOP, HORIZONTE}:
            usables.append(episodio)
            continue
        elif estado not in {NO_EJECUTABLE, *_EXCLUIDOS}:
            estado = DATOS_INCOMPLETOS
        # Falta de datos: lo que una exclusión declarada resuelve. Un split o una apertura invalidada, no.
        if estado in {DATOS_INCOMPLETOS, SIN_BARRA_DE_ENTRADA} and excluida:
            usables.append(episodio)
            con_exclusion.append(episodio.decision_id)
            continue
        excluidos[episodio.grupo][estado] = excluidos[episodio.grupo].get(estado, 0) + 1
    if faltan:
        raise EvaluacionDenegada(f"faltan {faltan} casos por completar")
    return usables, excluidos, con_exclusion


def _inconcluso_previo(
    usables: Sequence[Episodio], excluidos: Mapping[str, Mapping[str, int]],
) -> Optional[str]:
    sesiones: Dict[str, List[date]] = {
        grupo: [e.sesion for e in usables if e.grupo == grupo] for grupo in ("COMPRAR", "DESCARTAR")
    }
    for grupo, validas in sesiones.items():
        malos = sum(excluidos[grupo].values())
        if malos * 20 > malos + len(validas):  # más del 5 %
            return "DATOS"
    if any(len(validas) < madurez.MINIMO_POR_GRUPO for validas in sesiones.values()):
        return "MUESTRA"
    return None if inferencia_posible(sesiones["COMPRAR"], sesiones["DESCARTAR"]) else "BLOQUES"


def _cuantitativos(decisiones: Sequence[sqlite3.Row]) -> Dict[int, Mapping[str, Any]]:
    """Datos de decisión: los de una entrada ejecutable tienen que estar completos; los demás, si se puede."""

    salida: Dict[int, Mapping[str, Any]] = {}
    for fila in decisiones:
        try:
            datos = json.loads(fila[4])
            niveles, currency = datos["niveles"], datos["currency"]
            stop, score = float(niveles["stop"]), float(datos["score"])
            if not isinstance(currency, str) or not currency or not (math.isfinite(score) and 0 < stop < math.inf):
                raise ValueError
        except (KeyError, TypeError, ValueError) as exc:
            if fila[5] == 1:
                raise EvaluacionDenegada("cuantitativo ilegible") from exc
            datos = {"niveles": {}}
        salida[int(fila[0])] = datos
    return salida


# Guarda también la vista: mientras esté viva, su identidad no se reutiliza.
_SERIES: Dict[Tuple[int, str, bool], Tuple[Any, SeriePrecios]] = {}


def _serie(vintage: VintageLoad, symbol: str, market: str, *, fx: bool = False) -> SeriePrecios:
    """Precios de la cosecha. Una barra fuera de las sesiones de su plaza no es un precio, la sirva quien la sirva."""

    if symbol not in vintage.by_symbol:
        raise EvaluacionDenegada(f"falta {symbol} en la cosecha")
    vista = vintage.by_symbol[symbol]
    clave = (id(vista), market, fx)
    if clave not in _SERIES:
        _SERIES[clave] = (vista, _leer_serie(vintage, symbol, market, fx))
    return _SERIES[clave][1]


def _leer_serie(vintage: VintageLoad, symbol: str, market: str, fx: bool) -> SeriePrecios:
    barras = vintage.by_symbol[symbol].execution_prices
    fechas = tuple(fecha_fx(m) if fx else session_date_of(m, market) for m in barras.index)
    if any(d is None for d in fechas):
        raise EvaluacionDenegada(f"sesión ilegible en {symbol}")
    crudo = vintage.by_symbol[symbol].raw
    fechas_split = tuple(fecha_fx(m) if fx else session_date_of(m, market) for m in crudo.index)
    splits = tuple((d, float(r)) for d, r in zip(fechas_split, crudo["Stock Splits"]) if d is not None and float(r))
    dias = [d for d in fechas if d is not None]
    oficiales = set(dias) if fx or not dias else set(expected_sessions(market, min(dias), max(dias)))
    filas = [f for f in zip(dias, barras["Open"], barras["Close"]) if f[0] in oficiales]
    return SeriePrecios(
        tuple(d for d, _a, _c in filas), tuple(float(a) for _d, a, _c in filas),
        tuple(float(c) for _d, _a, c in filas), splits,
    )


def _decisiones_compra(db: Path) -> List[sqlite3.Row]:
    with abrir_fase(db, 0) as conn:
        return conn.execute(
            "SELECT d.id,d.symbol,d.market,d.target_session,d.cuantitativo,e.ejecutable "
            "FROM ia_decision d JOIN ia_pasada p ON p.id=d.pasada_id "
            "LEFT JOIN ia_contrafactual_entrada e ON e.decision_id=d.id "
            "WHERE d.tipo='COMPRA' AND p.decision_ts>=? ORDER BY d.id",
            (madurez.CORTE.isoformat(timespec="seconds"),),
        ).fetchall()


def _cubre(vintage: VintageLoad, symbol: str, market: str, sesion: date) -> bool:
    if symbol not in vintage.by_symbol:
        return False
    serie = _serie(vintage, symbol, market)
    return len(set(serie.fechas)) == len(serie.fechas) and any(
        math.isfinite(c) and c > 0 for d, c in zip(serie.fechas, serie.cierres) if d <= sesion
    )


def series_inservibles(vintage: VintageLoad, decisiones: Sequence[sqlite3.Row]) -> List[str]:
    """Valores con entrada ejecutable cuya serie falta, empieza tarde o repite sesiones."""

    primeras: Dict[Tuple[str, str], date] = {}
    for fila in decisiones:
        if fila[5] == 1:
            clave, sesion = (str(fila[1]), str(fila[2])), date.fromisoformat(str(fila[3]))
            primeras[clave] = min(sesion, primeras.get(clave, sesion))
    return sorted({s for (s, market), sesion in primeras.items() if not _cubre(vintage, s, market, sesion)})


def _exigidas(
    decisiones: Sequence[sqlite3.Row], cuantitativos: Mapping[int, Mapping[str, Any]], sin_entrada: Sequence[int],
) -> List[sqlite3.Row]:
    """Decisiones cuya divisa y referencia hacen falta: una exclusión declarada puede dar entrada a quien no la tuvo."""

    return [fila for fila in decisiones if fila[5] == 1 or (
        int(fila[0]) in sin_entrada and "currency" in cuantitativos[int(fila[0])]
    )]


def referencia_de(
    vintage: VintageLoad, exigidas: Sequence[sqlite3.Row], instante: datetime,
) -> Tuple[SeriePrecios, List[date]]:
    """``EUNL.DE`` con solo sesiones y precios válidos, y las sesiones que le faltan desde la primera entrada."""

    if REFERENCIA not in vintage.by_symbol:
        raise EvaluacionDenegada("falta EUNL.DE en la cosecha")
    serie = _serie(vintage, REFERENCIA, "XETRA")
    if len(set(serie.fechas)) != len(serie.fechas):
        raise EvaluacionDenegada("sesiones repetidas de EUNL.DE")
    filas = [f for f in zip(serie.fechas, serie.aperturas, serie.cierres) if all(
        math.isfinite(v) and v > 0 for v in f[1:]
    )]
    valida = SeriePrecios(
        tuple(f[0] for f in filas), tuple(f[1] for f in filas), tuple(f[2] for f in filas), serie.splits,
    )
    if not exigidas:
        return valida, []
    primera = min(date.fromisoformat(str(fila[3])) for fila in exigidas)
    esperadas = expected_sessions("XETRA", primera, instante.astimezone(timezone.utc).date())
    return valida, sorted(set(esperadas) - set(valida.fechas))


def _hueco_mas_largo(huecos: Sequence[date]) -> int:
    largo = seguidas = 0
    for dia in expected_sessions("XETRA", min(huecos), max(huecos)) if huecos else ():
        seguidas = seguidas + 1 if dia in huecos else 0
        largo = max(largo, seguidas)
    return largo


def _comprobar_cosecha(
    cosecha: str, cosecha_raiz: Path, decisiones: Sequence[sqlite3.Row], instante: datetime,
    cuantitativos: Mapping[int, Mapping[str, Any]], series_ausentes: Sequence[str] = (),
    sin_entrada: Sequence[int] = (), referencia_ausente: Sequence[date] = (),
) -> Tuple[VintageLoad, SeriePrecios]:
    try:
        vintage = load_vintage(cosecha, root_dir=cosecha_raiz)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise EvaluacionDenegada("cosecha ilegible o alterada") from exc
    peticion = vintage.manifest.get("request", {})
    inicio_esperado = (madurez.CORTE.date() - timedelta(days=10)).isoformat()
    fecha_instante = instante.astimezone(timezone.utc).date()
    fin_esperado = (fecha_instante + timedelta(days=1)).isoformat()
    if peticion.get("start") != inicio_esperado or peticion.get("end") != fin_esperado or not peticion.get(
        "end_exclusive"
    ):
        raise EvaluacionDenegada("la petición de la cosecha no coincide con el intervalo autorizado")
    ejecutables = _exigidas(decisiones, cuantitativos, sin_entrada)
    referencia, huecos = referencia_de(vintage, ejecutables, instante)
    if set(huecos) - set(referencia_ausente):
        raise EvaluacionDenegada(f"faltan {len(set(huecos) - set(referencia_ausente))} sesiones de EUNL.DE sin declarar")
    if _hueco_mas_largo(huecos) > MAX_HUECO_REFERENCIA:
        raise EvaluacionDenegada(f"EUNL.DE tiene más de {MAX_HUECO_REFERENCIA} sesiones seguidas sin precio")
    if set(referencia_ausente) - set(huecos):
        raise EvaluacionDenegada("referencia_ausente incluye sesiones que sí están")
    inservibles = set(series_inservibles(vintage, decisiones))
    if inservibles - set(series_ausentes):
        raise EvaluacionDenegada("series ausentes, que empiezan tarde o con sesiones repetidas: " + ", ".join(
            sorted(inservibles - set(series_ausentes))
        ))
    if set(series_ausentes) - inservibles:
        raise EvaluacionDenegada("series_ausentes incluye valores que sí tienen datos")
    primer_dia = min((date.fromisoformat(str(f[3])) for f in ejecutables), default=fecha_instante)
    monedas = sorted({str(cuantitativos[int(f[0])]["currency"]) for f in ejecutables} - {"EUR"})
    for moneda in monedas:
        simbolo = f"EUR{moneda}=X"
        if simbolo not in vintage.by_symbol:
            raise EvaluacionDenegada(f"falta {simbolo} en la cosecha")
        serie_fx = _serie(vintage, simbolo, "", fx=True)
        # Dos valores para un mismo día dejarían el cambio al azar del orden; repetir el mismo no afecta.
        if len(set(serie_fx.fechas)) != len(set(zip(serie_fx.fechas, serie_fx.cierres))):
            raise EvaluacionDenegada(f"{simbolo} tiene dos valores para el mismo día")
        for desplazamiento in range((fecha_instante - primer_dia).days + 1):
            dia = primer_dia + timedelta(days=desplazamiento)
            if fx_de(serie_fx.fechas, serie_fx.cierres, dia, moneda) is None:
                raise EvaluacionDenegada(f"falta FX de {moneda} para {dia}")
    return vintage, referencia


def episodios_truncados(
    vintage: VintageLoad, lista: Sequence[Episodio], rechazadas: Sequence[int] = (),
) -> List[Episodio]:
    """Episodios cuyo valor no tiene barras hasta su sesión 20: puede ser el proveedor o una exclusión.

    Incluye los que no tienen entrada vista, salvo si el gate la habría rechazado: la pérdida fue igual de real.
    Solo mira el calendario y precios de mercado, así que no dice nada de sus desenlaces.
    """

    salida = []
    for episodio in lista:
        if episodio.fin is None or episodio.decision_id in rechazadas:
            continue
        ultima = None
        if episodio.symbol in vintage.by_symbol:
            serie = _serie(vintage, episodio.symbol, episodio.market)
            validas = [d for d, c in zip(serie.fechas, serie.cierres) if math.isfinite(c) and c > 0]
            ultima = max(validas, default=None)
        if ultima is None or ultima < episodio.fin:
            salida.append(episodio)
    return salida


def _apertura_original(vintage: VintageLoad, symbol: str, market: str, sesion: date) -> Optional[float]:
    """Apertura de la sesión de entrada en la cosecha, en la escala de entonces."""

    if symbol not in vintage.by_symbol:
        return None
    serie = _serie(vintage, symbol, market)
    if sesion not in serie.fechas:
        return None
    apertura = serie.aperturas[serie.fechas.index(sesion)]
    if not (math.isfinite(apertura) and apertura > 0):
        return None  # una apertura vacía es un dato que falta, no un rechazo del gate
    for fecha_split, ratio in serie.splits:
        apertura *= ratio if fecha_split > sesion else 1.0
    return apertura


def _gate_rechaza(apertura: float, niveles: Mapping[str, Any]) -> bool:
    """Si el gate rechaza esa apertura también con una diezmilésima de holgura a cada lado.

    Sin holgura, el ruido de coma flotante del proveedor o de un split cambiaría la decisión en las aperturas
    pegadas al máximo, que es donde casi siempre está ``entry_max``.
    """

    try:
        minimo = niveles.get("min_rr_ratio")
        return not any(
            evaluar_gate_apertura(
                apertura * factor, float(niveles["stop"]), float(niveles["target2"]), float(niveles["entry_max"]),
                None if minimo is None else float(minimo),
            ).aprobado
            for factor in (1 - HOLGURA_GATE, 1.0, 1 + HOLGURA_GATE)
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return False  # sin niveles legibles no se puede afirmar que la rechazara


def _rechazadas_por_gate(
    vintage: VintageLoad, lista: Sequence[Episodio], cuantitativos: Mapping[int, Mapping[str, Any]],
) -> List[int]:
    """Decisiones sin entrada vista cuya apertura, según la cosecha, el gate habría rechazado."""

    salida = []
    for episodio in lista:
        if episodio.categoria != "sin_entrada":
            continue
        apertura = _apertura_original(vintage, episodio.symbol, episodio.market, episodio.sesion)
        if apertura is not None and _gate_rechaza(apertura, cuantitativos[episodio.decision_id]["niveles"]):
            salida.append(episodio.decision_id)
    return salida


def aperturas_invalidadas(
    vintage: VintageLoad, decisiones: Sequence[sqlite3.Row], cuantitativos: Mapping[int, Mapping[str, Any]],
) -> Dict[int, str]:
    """Entradas que constan como ejecutables y que el proveedor invalidó o retiró después (§9.3).

    Se decide igual para todas con la cosecha. Mirar solo el estado guardado excluiría la que seguía viva
    cuando llegó la revisión y conservaría la que ya había saltado su stop: dependería del resultado.
    """

    salida: Dict[int, str] = {}
    for fila in decisiones:
        decision_id, symbol, market, sesion = int(fila[0]), str(fila[1]), str(fila[2]), date.fromisoformat(str(fila[3]))
        if fila[5] != 1 or symbol not in vintage.by_symbol:
            continue
        apertura = _apertura_original(vintage, symbol, market, sesion)
        if apertura is not None:
            if _gate_rechaza(apertura, cuantitativos[decision_id]["niveles"]):
                salida[decision_id] = NO_EJECUTABLE
            continue
        serie = _serie(vintage, symbol, market)
        fechas = [d for d, c in zip(serie.fechas, serie.cierres) if math.isfinite(c) and c > 0]
        # Sin barras a ambos lados no se distingue una barra retirada de una serie que empieza o acaba ahí.
        if fechas and min(fechas) < sesion < max(fechas):
            salida[decision_id] = SIN_BARRA_DE_ENTRADA
    return salida


def _admite_entrada(
    precio: float, cuantitativo: Mapping[str, Any], episodio: Episodio, lista: Sequence[Episodio],
    declaraciones: Sequence[Mapping[str, Any]],
) -> bool:
    """Si una entrada no vista pasa el gate y no repite un episodio del mismo valor dentro de sus 20 sesiones."""

    niveles = cuantitativo["niveles"]
    for clave in ("stop", "target2", "entry_max"):
        float(niveles[clave])
    if _gate_rechaza(precio, niveles) or not isinstance(cuantitativo["currency"], str):
        return False
    excluidas = {int(dato["decision_id"]) for dato in declaraciones if dato["tipo"] == EXCLUSION}
    return episodio.fin is not None and not any(
        otro.symbol == episodio.symbol and episodio.sesion < otro.sesion <= episodio.fin
        and (otro.categoria in {"maduros", "madurando"} or otro.decision_id in excluidas)
        for otro in lista
    )


def _absorbidas(autorizacion: Mapping[str, Any], lista: Sequence[Episodio]) -> List[int]:
    """Decisiones sin entrada dentro del episodio que abre una exclusión del mismo valor: §4 las ignora."""

    try:
        excluidas = {
            int(dato["decision_id"]) for dato in autorizacion.get("episodios_truncados", []) if dato["tipo"] == EXCLUSION
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise EvaluacionDenegada("episodios_truncados ilegible o inválido") from exc
    abren = [e for e in lista if e.categoria == "sin_entrada" and e.decision_id in excluidas]
    return [
        otro.decision_id for otro in lista if otro.categoria == "sin_entrada" and any(
            e.symbol == otro.symbol and e.fin is not None and e.sesion < otro.sesion <= e.fin for e in abren
        )
    ]


def _determinaciones(
    autorizacion: Mapping[str, Any], vintage: VintageLoad, lista: Sequence[Episodio],
    cuantitativos: Mapping[int, Mapping[str, Any]], instante: datetime, rechazadas: Sequence[int],
) -> Dict[int, Determinacion]:
    truncados = episodios_truncados(vintage, lista, rechazadas)
    absorbidas = _absorbidas(autorizacion, lista)
    hechas: Dict[int, Determinacion] = {}
    try:
        for dato in autorizacion.get("episodios_truncados", []):
            tipo = dato["tipo"]
            justificacion, fuente = str(dato["justificacion"]).strip(), str(dato["fuente"]).strip()
            if tipo not in {SIN_DATOS, EXCLUSION} or not justificacion or not fuente:
                raise ValueError
            decision = int(dato["decision_id"])
            if decision in absorbidas and tipo == SIN_DATOS:
                continue  # ``congelar`` no puede saberlo: la lista aún sin declaraciones la incluye
            d = Determinacion(decision, tipo, justificacion, fuente)
            if tipo == EXCLUSION:
                d = Determinacion(
                    decision, tipo, justificacion, fuente, date.fromisoformat(dato["sesion_salida"]),
                    float(dato["precio_entrada"]), float(dato["precio_salida"]),
                )
                episodio = next(e for e in truncados if e.decision_id == decision)
                stop = float(cuantitativos[decision]["niveles"]["stop"])
                publicada = _apertura_original(vintage, episodio.symbol, episodio.market, episodio.sesion)
                if publicada is not None and not math.isclose(d.precio_entrada, publicada, rel_tol=0.005):
                    raise ValueError
                if episodio.categoria == "sin_entrada" and not _admite_entrada(
                    d.precio_entrada, cuantitativos[decision], episodio, lista, autorizacion["episodios_truncados"],
                ):
                    raise ValueError
                cerradas = _sesiones(episodio.market, episodio.sesion, instante)
                if d.sesion_salida not in cerradas or not (
                    math.isfinite(d.precio_entrada) and d.precio_entrada > stop and math.isfinite(d.precio_salida) and d.precio_salida >= 0
                ):
                    raise ValueError
            if decision in hechas:
                raise ValueError
            hechas[decision] = d
    except (KeyError, TypeError, ValueError, StopIteration) as exc:
        raise EvaluacionDenegada("episodios_truncados ilegible o inválido") from exc
    pendientes = {e.decision_id: e.symbol for e in truncados if e.decision_id not in hechas}
    if pendientes:
        raise EvaluacionDenegada("falta declarar en episodios_truncados: " + ", ".join(
            f"{symbol} (decisión {decision})" for decision, symbol in sorted(pendientes.items())
        ))
    if set(hechas) - {e.decision_id for e in truncados}:
        raise EvaluacionDenegada("episodios_truncados incluye episodios con datos completos")
    return hechas


def _justificadas(autorizacion: Mapping[str, Any], clave: str) -> Dict[str, str]:
    crudo = autorizacion.get(clave, {})
    if not isinstance(crudo, dict) or not all(isinstance(v, str) and v.strip() for v in crudo.values()):
        raise EvaluacionDenegada(f"{clave} debe dar la justificación de cada valor")
    return dict(sorted(crudo.items()))


def _referencia_ausente(autorizacion: Mapping[str, Any]) -> Dict[date, str]:
    try:
        return {date.fromisoformat(k): v for k, v in _justificadas(autorizacion, "referencia_ausente").items()}
    except ValueError as exc:
        raise EvaluacionDenegada("referencia_ausente lleva una fecha ilegible") from exc


def _preparar(
    db: Path, cosecha_raiz: Path, autorizacion: Mapping[str, Any], instante: datetime, lista: Sequence[Episodio],
) -> Tuple[VintageLoad, SeriePrecios, Dict[int, Determinacion], List[int], Dict[int, str], Dict[str, str]]:
    """Todo lo que se comprueba con la cosecha y la fase 0: lo comparten ``puertas`` y ``evaluar``."""

    ausentes = _justificadas(autorizacion, "series_ausentes")
    decisiones = _decisiones_compra(db)
    cuantitativos = _cuantitativos(decisiones)
    vintage, referencia = _comprobar_cosecha(
        str(autorizacion["cosecha"]), cosecha_raiz, decisiones, instante, cuantitativos, list(ausentes),
        [e.decision_id for e in lista if e.categoria == "sin_entrada"], list(_referencia_ausente(autorizacion)),
    )
    rechazadas = _rechazadas_por_gate(vintage, lista, cuantitativos)
    rechazadas += _absorbidas(autorizacion, lista)
    determinaciones = _determinaciones(autorizacion, vintage, lista, cuantitativos, instante, rechazadas)
    return (
        vintage, referencia, determinaciones, rechazadas,
        aperturas_invalidadas(vintage, decisiones, cuantitativos), ausentes,
    )


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
    db: Path, usables: Sequence[Episodio], exclusiones: Mapping[int, Determinacion], instante: datetime,
    invalidadas: Mapping[int, str], vintage: Optional[VintageLoad] = None,
) -> Tuple[List[Caso], List[Caso], Dict[int, float], Optional[str], List[int]]:
    """Casos de la métrica, casos de carteras, R de cada uno, errores solo de carteras y omitidos en ellas."""

    ids = {e.decision_id for e in usables}
    with abrir_fase(db, 2) as conn:
        filas = conn.execute(
            "SELECT d.id,d.symbol,d.market,d.resolucion,d.target_session,d.target_open,d.cuantitativo,"
            "c.estado,c.final,c.entrada,c.salida,c.hasta_session,c.retorno_r,c.sesiones "
            "FROM ia_decision d JOIN ia_pasada p ON p.id=d.pasada_id "
            "LEFT JOIN ia_contrafactual_entrada e ON e.decision_id=d.id "
            "LEFT JOIN ia_contrafactual c ON c.decision_id=d.id "
            "WHERE d.tipo='COMPRA' AND p.decision_ts>=? AND (e.ejecutable=1 OR (e.decision_id IS NULL AND d.id IN "
            f"({','.join(str(int(i)) for i in sorted(exclusiones)) or 'NULL'}))) ORDER BY d.id",
            (madurez.CORTE.isoformat(timespec="seconds"),),
        ).fetchall()
    casos: List[Caso] = []
    candidatas: List[Caso] = []
    retornos_r: Dict[int, float] = {}
    errores_cartera: list[str] = []
    omitidos: List[int] = []
    for f in filas:
        decision_id, estado, final, declarada = int(f[0]), str(f[7]), f[8], exclusiones.get(int(f[0]))
        if decision_id in invalidadas and decision_id not in ids:
            omitidos.append(decision_id)
            continue
        # Lo utilizable lo decidió la fase 1 y no se vuelve a juzgar; lo demás solo puede ir a carteras.
        cerrado = (decision_id in ids and declarada is None) or (
            final == 1 and estado in {STOP, HORIZONTE}
            and _sin_huecos(str(f[2]), date.fromisoformat(str(f[4])), estado, f[11], f[13])
        )
        if cerrado and decision_id not in ids and vintage is not None:
            try:
                stop_visto = float(json.loads(f[6])["niveles"]["stop"])
            except (KeyError, TypeError, ValueError):
                stop_visto = math.nan
            cerrado = _contraste(
                vintage, str(f[1]), str(f[2]), date.fromisoformat(str(f[4])), estado, date.fromisoformat(str(f[11])),
                stop_visto,
            ) is None
        # Pasadas sus 20 sesiones, una posición sin desenlace no está abierta: le faltan datos.
        abierto = final == 0 and estado == ABIERTA and f[9] is not None and _sesiones_cerradas(
            str(f[2]), date.fromisoformat(str(f[4])), instante,
        ) < HORIZONTE_SESIONES
        if not cerrado and declarada is None and not abierto:
            if decision_id in ids:
                raise EvaluacionDenegada("estado final inesperado")
            omitidos.append(decision_id)
            continue
        try:
            cuantitativo = json.loads(f[6])
            stop, score = float(cuantitativo["niveles"]["stop"]), float(cuantitativo["score"])
            salida: Optional[float] = None
            sesion_salida: Optional[date] = None
            if declarada is not None:
                estado, salida, sesion_salida = EXCLUSION, declarada.precio_salida, declarada.sesion_salida
                entrada = declarada.precio_entrada if f[9] is None else float(f[9])
                antes = None if vintage is None or sesion_salida is None else _stop_en_cosecha(
                    vintage, str(f[1]), str(f[2]), date.fromisoformat(str(f[4])), sesion_salida, stop,
                )
                if antes is not None:  # un stop anterior manda, también el que el bot no llegó a ver
                    estado, (sesion_salida, salida) = STOP, antes
            else:
                entrada = float(f[9])
                if cerrado:
                    salida, sesion_salida = float(f[10]), date.fromisoformat(str(f[11]))
            numeros = [entrada, stop, score, *([] if salida is None else [salida])]
            if not all(map(math.isfinite, numeros)) or stop >= entrada:
                raise ValueError("precios inesperados")
            caso = Caso(
                decision_id, str(f[1]), str(f[2]), str(cuantitativo["currency"]), str(f[3]),
                date.fromisoformat(str(f[4])), sesion_salida, entrada, salida, stop, score,
                datetime.fromisoformat(str(f[5])), estado,
            )
        except (KeyError, TypeError, ValueError) as exc:
            if decision_id in ids:
                raise EvaluacionDenegada("caso utilizable ilegible") from exc
            errores_cartera.append(f"decisión {decision_id}: caso de cartera ilegible")
            continue
        candidatas.append(caso)
        if decision_id in ids and salida is not None:
            casos.append(caso)
            if declarada is not None:
                retornos_r[decision_id] = (salida - entrada) / (entrada - stop)
            elif f[12] is not None:
                retornos_r[decision_id] = float(f[12])
    if len(casos) != len(ids):
        raise EvaluacionDenegada("faltan casos utilizables tras la apertura")
    return casos, candidatas, retornos_r, "; ".join(errores_cartera) or None, omitidos


def _euros_api(db: Path) -> Tuple[float, Dict[date, float]]:
    with abrir_fase(db, 0) as conn:
        filas = conn.execute(
            "SELECT l.coste_eur,l.created_at FROM ia_llamada l JOIN ia_paquete p ON p.input_hash=l.input_hash "
            "JOIN ia_pasada x ON x.id=l.pasada_id WHERE p.tipo='COMPRA' AND x.decision_ts>=?",
            (madurez.CORTE.isoformat(timespec="seconds"),),
        ).fetchall()
    por_dia: Dict[date, float] = {}
    for coste, texto in filas:
        try:
            instante, euros = datetime.fromisoformat(texto), float(coste)
        except (TypeError, ValueError) as exc:
            raise EvaluacionDenegada("coste API ilegible") from exc
        if instante.tzinfo is None or instante.utcoffset() is None or not (math.isfinite(euros) and euros >= 0):
            raise EvaluacionDenegada("coste API inválido")
        dia = instante.astimezone(timezone.utc).date()
        por_dia[dia] = por_dia.get(dia, 0.0) + euros
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
    _sin_salidas(raiz)
    _git_limpio(raiz)
    cuenta, lista = _puerta_madurez(db, instante_evaluacion)
    if min(cuenta.aprobadas.maduros, cuenta.descartadas.maduros) < madurez.MINIMO_POR_GRUPO:
        if _sha(db) != str(autorizacion["base_sha256"]):
            raise EvaluacionDenegada("la base cambió antes de escribir el resultado")
        return _resultado_inconcluso(raiz, db, cosecha, "MUESTRA", cuenta)
    ultimo_dia = instante_evaluacion.astimezone(timezone.utc).date()
    vintage, referencia, determinaciones, rechazadas, invalidadas, ausentes = _preparar(
        db, cosecha_raiz, autorizacion, instante_evaluacion, lista,
    )
    usables, excluidos, con_exclusion = _fase1(
        db, lista, determinaciones, rechazadas, invalidadas, vintage, _cuantitativos(_decisiones_compra(db)),
    )
    detalle = {
        "series_ausentes": ausentes,
        "referencia_ausente": {d.isoformat(): v for d, v in _referencia_ausente(autorizacion).items()},
        "episodios_truncados": [asdict(d) for _id, d in sorted(determinaciones.items())],
        "con_resultado_de_exclusion": con_exclusion, "aperturas_invalidadas": invalidadas,
    }
    n = {grupo: sum(e.grupo == grupo for e in usables) for grupo in ("COMPRAR", "DESCARTAR")}
    motivo = _inconcluso_previo(usables, excluidos)
    if motivo is not None:
        if _sha(db) != str(autorizacion["base_sha256"]):
            raise EvaluacionDenegada("la base cambió antes de escribir el resultado")
        return _resultado_inconcluso(raiz, db, cosecha, motivo, cuenta, excluidos, n, detalle)
    euros_api, api_por_dia = _euros_api(db)
    identidades = _identidades(raiz, db, cosecha, instante_evaluacion)
    for clave in ("criterio_sha256", "codigo_sha256", "base_sha256", "instante", "entorno"):
        if autorizacion.get(clave) != identidades[clave]:
            raise EvaluacionDenegada(f"la identidad {clave} cambió antes de abrir")
    _abrir(raiz, identidades, instante_apertura)
    casos, candidatas, retornos_r, error_carteras, omitidos = _leer_casos(
        db, usables, {i: determinaciones[i] for i in con_exclusion}, instante_evaluacion, invalidadas, vintage,
    )
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
    coste_api = coste_api_por_aprobado(euros_api, observaciones["COMPRAR"])
    ic = intervalo_jackknife(observaciones["COMPRAR"], observaciones["DESCARTAR"], coste_api)
    if ic.bajo is None:
        if _sha(db) != str(autorizacion["base_sha256"]):
            raise EvaluacionDenegada("la base cambió después de abrir")
        return _resultado_inconcluso(raiz, db, cosecha, "BLOQUES", cuenta, excluidos, n, detalle, identidades)
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
        # Sin serie solo queda quien la autorización identifica: ausente o con una exclusión declarada.
        candidatas_cartera = [c for c in candidatas if c.symbol not in ausentes and c.symbol in vintage.by_symbol]
        omitidos = sorted({*omitidos, *(
            c.decision_id for c in candidatas if c.symbol not in ausentes and c.symbol not in vintage.by_symbol
        )})
        series = {c.symbol: _serie(vintage, c.symbol, c.market) for c in candidatas_cartera}
        detalle_carteras: Any = {
            k: v.como_dict() for k, v in carteras(
                candidatas_cartera, series, fx, referencia, api_por_dia, ultimo_dia,
            ).items()
        }
    except DatoCompartidoInvalido:
        # El fallo toca un dato de la métrica: no se publica un veredicto a favor ni en contra (D-88).
        if _sha(db) != str(autorizacion["base_sha256"]):
            raise EvaluacionDenegada("la base cambió después de abrir") from None
        return _resultado_inconcluso(
            raiz, db, cosecha, "DATOS_COMPARTIDOS", cuenta, excluidos, n, detalle, identidades,
        )
    except Exception as exc:
        detalle_carteras = {"error": f"{type(exc).__name__}: {exc}"}
    try:
        detalle_secundario: Any = secundario(casos, retornos_r, no_ejecutables)
        detalle_secundario["ventas_ia"] = _ventas_ia(db)
    except Exception as exc:
        detalle_secundario = {"error": f"{type(exc).__name__}: {exc}"}
    datos = {
        "veredicto": veredicto_final, "motivo": None, "ic": [ic.bajo, ic.alto],
        "intervalo": {"metodo": "t con jackknife por bloques", "bloques": ic.bloques, "error_tipico": ic.error_tipico},
        "estimador": estimador(observaciones["COMPRAR"], observaciones["DESCARTAR"], coste_api),
        "media_grupo": medias, "n": {g: len(observaciones[g]) for g in observaciones},
        "maduros": {"COMPRAR": cuenta.aprobadas.maduros, "DESCARTAR": cuenta.descartadas.maduros},
        "excluidos": excluidos,
        "coste_api": {"euros": euros_api, "por_nocional_aprobado": coste_api},
        "carteras": detalle_carteras, "omitidos_en_carteras": omitidos,
        "entradas_de_exclusiones": {c.decision_id: c.entrada for c in casos if c.decision_id in con_exclusion},
        "exclusiones_con_stop_anterior": [
            c.decision_id for c in casos if c.decision_id in con_exclusion and c.estado == STOP
        ],
        "secundario": detalle_secundario, "identidades": identidades, **detalle,
    }
    if _sha(db) != str(autorizacion["base_sha256"]):
        raise EvaluacionDenegada("la base cambió después de abrir")
    _atomico(_salidas(raiz)[0], datos)
    return datos


__all__ = [
    "Episodio", "EvaluacionDenegada", "Puertas", "abrir_fase", "episodios", "evaluar", "huella_evaluador",
    "puertas",
]
