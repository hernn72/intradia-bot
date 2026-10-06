"""Red de seguridad de borrado para los tests (incidente 2026-10-06, evidence/2026-10-06-incidente-perdida-vintage/).

Solo biblioteca estándar: la usan `tests/conftest.py` (con monkeypatch, restaurable) y
`tests/red_hijos/sitecustomize.py`, que la instala en todo intérprete Python hijo lanzado por un test.

Ningún test puede borrar, mover, pisar ni abrir para escritura `/`, `$HOME`, la raíz del repo o sus
antecesores, ni nada en `data/`, `evidence/` o `.git/` del repo, ni una base SQLite del repo. La lectura sigue
permitida. Las órdenes externas se inspeccionan por tokens.

Riesgos residuales documentados (fuera del modelo accidental/estructural o cubiertos por los backups fuera
del repositorio):
- un programa externo no Python cuya forma de borrar no se reconozca por sus tokens (p. ej. un binario
  propio);
- un intérprete Python lanzado desde una orden de shell de forma ofuscada (variables, `$(which python)`,
  alias): la búsqueda de intérpretes en órdenes de shell es por tokens y separa espacios y puntuación del
  shell, pero no evalúa el shell.
"""

from __future__ import annotations

import inspect
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Optional

REPO_TESTS = Path(__file__).resolve().parents[1]
SUBDIRS_PROTEGIDOS = ("data", "evidence", ".git")
SUFIJOS_SQLITE = (".db", ".sqlite", ".sqlite3")


class BorradoProhibidoEnTests(RuntimeError):
    """Un test intentó borrar datos protegidos del repositorio o del sistema."""


def ruta_prohibida(objetivo: Any, *, repo: Path = REPO_TESTS, home: Optional[Path] = None) -> Optional[str]:
    """Motivo por el que `objetivo` no se puede borrar en tests, o None si se puede."""

    try:
        real = Path(os.path.realpath(os.fspath(objetivo)))
    except TypeError:
        return None
    repo = repo.resolve()
    for protegida in (Path("/"), (home or Path.home()).resolve(), repo):
        if real == protegida or real in protegida.parents:
            return f"{real} es o contiene {protegida}"
    for sub in SUBDIRS_PROTEGIDOS:
        # Literal y resuelta: si `data/` fuera un enlace a otro volumen, el objetivo resuelto cae en el destino.
        for base in {repo / sub, (repo / sub).resolve()}:
            if real == base or base in real.parents:
                return f"{real} está en {base}"
    nombre = real.name.lower()
    raices = {repo, *((repo / sub).resolve() for sub in SUBDIRS_PROTEGIDOS)}
    if any(r in real.parents for r in raices) and any(
        nombre.endswith(s) or f"{s}." in nombre or f"{s}-" in nombre for s in SUFIJOS_SQLITE
    ):
        return f"{real} es una base SQLite del repo"
    return None


def ruta_de_descriptor(fd: int) -> Optional[str]:
    """Ruta real de un descriptor de directorio (macOS: F_GETPATH; Linux: /proc/self/fd)."""

    try:
        import fcntl

        if hasattr(fcntl, "F_GETPATH"):
            crudo = fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024))
            return os.fsdecode(crudo.split(b"\0", 1)[0])
    except OSError:
        return None
    try:
        return os.readlink(f"/proc/self/fd/{fd}")
    except OSError:
        return None


def ruta_efectiva(ruta: Any, dir_fd: Any) -> Any:
    """La ruta que de verdad se toca: relativa a `dir_fd` si lo hay. Sin resolver → falla cerrada."""

    if dir_fd is None:
        return ruta
    base = ruta_de_descriptor(int(dir_fd))
    if base is None:
        raise BorradoProhibidoEnTests(f"no se puede resolver dir_fd={dir_fd}: se deniega")
    return os.path.join(base, os.fsdecode(ruta))


def envolver_borrado(original: Callable[..., Any], nombre: str, *, repo: Path = REPO_TESTS) -> Callable[..., Any]:
    """Envuelve una función de borrado: comprueba la ruta efectiva (también con dir_fd) antes de borrar."""

    def guardada(ruta: Any, *args: Any, **kwargs: Any) -> Any:
        motivo = ruta_prohibida(ruta_efectiva(ruta, kwargs.get("dir_fd")), repo=repo)
        if motivo is not None:
            raise BorradoProhibidoEnTests(f"{nombre} denegado en tests: {motivo}")
        return original(ruta, *args, **kwargs)

    for atributo in ("avoids_symlink_attacks",):
        if hasattr(original, atributo):
            setattr(guardada, atributo, getattr(original, atributo))
    return guardada


def envolver_renombrado(original: Callable[..., Any], nombre: str, *, repo: Path = REPO_TESTS) -> Callable[..., Any]:
    """`os.rename`/`os.replace`: mover algo protegido equivale a borrarlo; pisarlo, también."""

    def guardada(origen: Any, destino: Any, *args: Any, **kwargs: Any) -> Any:
        for ruta, fd in ((origen, kwargs.get("src_dir_fd")), (destino, kwargs.get("dst_dir_fd"))):
            motivo = ruta_prohibida(ruta_efectiva(ruta, fd), repo=repo)
            if motivo is not None:
                raise BorradoProhibidoEnTests(f"{nombre} denegado en tests: {motivo}")
        return original(origen, destino, *args, **kwargs)

    return guardada


ORDENES_BORRADO = {"rm", "rmdir", "unlink", "shred", "srm", "trash", "mv"}
_PALABRA_BORRADO = re.compile(r"(^|[\s;&|(`'\"/])(rm|rmdir|unlink|shred|srm|trash|mv)(\s|$|[;&|)`'\"])")
# git que descarta trabajo o ficheros: clean, reset --hard, checkout --, restore, stash, rm.
_GIT_DESTRUCTIVO = re.compile(r"\bgit\b.*\s(clean|restore|stash|rm)(\s|$)|\bgit\b.*\sreset\s.*--hard|\bgit\b.*\scheckout\s.*--(\s|$)")


def orden_de_borrado(args: Any, *, shell: bool = False) -> Optional[str]:
    """Motivo si una orden externa puede borrar; None si no. Mira todos los tokens, no solo el primero.

    Es una lista negra y por tanto incompleta. Los intérpretes Python hijos llevan la red completa
    (`tests/red_hijos/sitecustomize.py`); para otros programas externos queda el riesgo residual del
    docstring del módulo.
    """

    unico = isinstance(args, (str, bytes, os.PathLike))
    tokens = [os.fsdecode(args)] if unico else [os.fsdecode(a) for a in args]
    texto = " ".join(tokens)
    nombres = {os.path.basename(t) for t in tokens}
    if nombres & ORDENES_BORRADO or _PALABRA_BORRADO.search(texto):
        return f"orden con borrado: {texto!r}"
    palabras = [t.rstrip(";&|)") for t in texto.split()]
    if "-delete" in palabras or any(p.startswith("--delete") or p.startswith("--remove-source-files") for p in palabras):
        return f"find -delete / rsync --delete: {texto!r}"
    if _GIT_DESTRUCTIVO.search(texto):
        return f"git destructivo: {texto!r}"
    return None


VARIABLES_RED = ("PYTHONPATH", "INTRADIA_RED_BORRADO_REPO")


def es_python(programa: str) -> bool:
    """¿Es un intérprete Python? Por nombre (python, python3.12, pythonw, pypy3…) o por ser el de la sesión."""

    nombre = os.path.basename(programa).lower()
    if re.fullmatch(r"(python|pythonw|pypy)(\d+(\.\d+)*)?(\.exe)?", nombre):
        return True
    try:
        return os.path.realpath(programa) == os.path.realpath(sys.executable)
    except (TypeError, ValueError):
        return False


def flags_que_anulan_la_red(argv: list[str]) -> list[str]:
    """Banderas de un intérprete Python que harían ignorar `PYTHONPATH`/`sitecustomize` (-I, -E, -S)."""

    malas: list[str] = []
    indice = 1
    while indice < len(argv):
        token = argv[indice]
        if not token.startswith("-") or token == "-" or token.startswith("--"):
            if token.startswith("--") and token != "--":
                # La única opción larga de CPython con argumento separado.
                indice += 2 if token == "--check-hash-based-pycs" else 1
                continue
            break  # script, `-` (stdin) o `--`: fin de las opciones del intérprete
        letras = token[1:]
        for posicion, letra in enumerate(letras):
            if letra in {"c", "m"}:
                return malas  # lo que sigue es código o módulo, no opciones
            if letra in {"W", "X"}:
                # El resto del token es su argumento; si no queda nada, lo es el token siguiente.
                if posicion == len(letras) - 1:
                    indice += 1
                break
            if letra in {"I", "E", "S"}:
                malas.append(f"-{letra}")
        indice += 1
    return malas


def _tokens(args: Any, *, shell: bool) -> list[str]:
    if isinstance(args, (str, bytes, os.PathLike)):
        texto = os.fsdecode(args)
        if not shell:
            return [texto]
        try:
            return shlex.split(texto, posix=True)
        except ValueError:
            return texto.split()
    return [os.fsdecode(a) for a in args]


_METACARACTERES = re.compile(r"[;&|()`<>\n]+|\$\(")


def _expandir(tokens: list[str], profundidad: int = 4) -> list[str]:
    """Trocea con shlex los tokens que contienen órdenes (p. ej. el argumento de `bash -c "..."`).

    Cada token con espacios se sustituye por su troceado, recursivamente y con profundidad acotada; así
    un `python -S` anidado en una orden de shell queda a la vista como tokens propios.
    """

    if profundidad == 0:
        return tokens
    salida: list[str] = []
    for token in tokens:
        if any(c.isspace() for c in token):
            try:
                partes = shlex.split(token, posix=True)
            except ValueError:
                partes = token.split()
            salida.extend(_expandir(partes, profundidad - 1))
        else:
            # `true;python` o `(python`: la puntuación del shell separa órdenes aunque no haya espacios.
            salida.extend(p for p in _METACARACTERES.split(token) if p)
    return salida


def asegurar_hijo(args: Any, *, shell: bool = False, executable: Any = None, env: Any = None) -> Any:
    """Única regla para todo lanzamiento de procesos desde los tests.

    1. Niega órdenes de borrado reconocibles.
    2. Si en la orden aparece un intérprete Python (como programa, en `executable=` o dentro de una orden de
       shell), niega -I/-E/-S, que le harían ignorar la red.
    3. Devuelve el entorno a usar: si `env` es explícito, con las variables de la red añadidas, porque un
       entorno explícito no las hereda; si es None, el heredado ya las lleva.
    """

    motivo = orden_de_borrado(args, shell=shell)
    if motivo is not None:
        raise BorradoProhibidoEnTests(f"lanzamiento denegado en tests: {motivo}")
    tokens = _expandir(_tokens(args, shell=shell))
    candidatos = [i for i, t in enumerate(tokens) if es_python(t)]
    if executable is not None and es_python(os.fsdecode(executable)) and 0 not in candidatos:
        candidatos.insert(0, 0)
    for indice in candidatos:
        malas = flags_que_anulan_la_red(tokens[indice:])
        if malas:
            raise BorradoProhibidoEnTests(f"intérprete Python hijo con {malas}: ignoraría la red de borrado")
    if env is None:
        return None
    return {**env, **{v: os.environ[v] for v in VARIABLES_RED if v in os.environ}}


_FIRMA_POPEN = inspect.signature(subprocess.Popen.__init__)


class PopenGuardado(subprocess.Popen):  # type: ignore[type-arg]
    """`subprocess.Popen` que aplica `asegurar_hijo` a todo lanzamiento.

    Los argumentos se enlazan con la firma real de `Popen`, de modo que `shell`, `executable` y `env` cuentan
    igual pasados por nombre que por posición.
    """

    def __init__(self, *posicionales: Any, **kwargs: Any) -> None:
        enlazados = _FIRMA_POPEN.bind(self, *posicionales, **kwargs)
        a = enlazados.arguments
        entorno = asegurar_hijo(a["args"], shell=bool(a.get("shell", False)), executable=a.get("executable"), env=a.get("env"))
        if entorno is not None:
            a["env"] = entorno
        super().__init__(*enlazados.args[1:], **enlazados.kwargs)


# Posición de (programa, argv, env) en cada función de os; None si no tiene ese argumento.
_FIRMAS_OS: dict[str, tuple[int, int, Optional[int]]] = {
    "spawnv": (1, 2, None),
    "spawnve": (1, 2, 3),
    "spawnvp": (1, 2, None),
    "spawnvpe": (1, 2, 3),
    "posix_spawn": (0, 1, 2),
    "posix_spawnp": (0, 1, 2),
    "execv": (0, 1, None),
    "execve": (0, 1, 2),
    "execvp": (0, 1, None),
    "execvpe": (0, 1, 2),
}


def envolver_proceso(original: Callable[..., Any], nombre: str) -> Callable[..., Any]:
    """`os.system`, `os.spawn*`, `os.posix_spawn*` y `os.exec*`: la misma regla que `subprocess`."""

    corto = nombre.removeprefix("os.")
    try:
        firma: Optional[inspect.Signature] = inspect.signature(original)
    except (TypeError, ValueError):
        firma = None  # p. ej. posix_spawn: path, argv y env son solo posicionales

    def guardada(*args: Any, **kwargs: Any) -> Any:
        if corto == "system":
            orden_sistema = args[0] if args else kwargs.get("command")
            asegurar_hijo(orden_sistema, shell=True)
            return original(*args, **kwargs)
        i_prog, i_argv, i_env = _FIRMAS_OS[corto]
        if firma is not None:
            # Enlace con la firma real: posición o nombre, da igual.
            enlazados = firma.bind(*args, **kwargs)
            nombres = list(firma.parameters)
            valores = [enlazados.arguments.get(n) for n in nombres]
        else:
            enlazados = None
            nombres = []
            valores = list(args)
        programa = valores[i_prog] if len(valores) > i_prog else None
        argv = list(valores[i_argv]) if len(valores) > i_argv and valores[i_argv] is not None else []
        env_actual = valores[i_env] if i_env is not None and len(valores) > i_env else None
        orden = [os.fsdecode(programa), *argv[1:]] if programa is not None else argv
        entorno = asegurar_hijo(orden, executable=programa, env=env_actual)
        if entorno is not None and i_env is not None:
            if enlazados is not None:
                enlazados.arguments[nombres[i_env]] = entorno
                return original(*enlazados.args, **enlazados.kwargs)
            args = (*args[:i_env], entorno, *args[i_env + 1 :])
        return original(*args, **kwargs)

    return guardada


_FLAGS_ESCRITURA = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND


def _comprobar_escritura(ruta: Any, nombre: str, dir_fd: Any = None) -> None:
    if isinstance(ruta, int):
        return  # descriptor ya abierto: se comprobó al abrirlo
    motivo = ruta_prohibida(ruta_efectiva(ruta, dir_fd))
    if motivo is not None:
        raise BorradoProhibidoEnTests(f"{nombre} en escritura denegado en tests: {motivo}")


def envolver_open(original: Callable[..., Any], nombre: str) -> Callable[..., Any]:
    """`open`/`io.open`: escribir (w, a, x, +) sobre una ruta protegida equivale a pisarla."""

    def guardada(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if any(c in mode for c in "wax+"):
            _comprobar_escritura(file, nombre)
        return original(file, mode, *args, **kwargs)

    return guardada


def envolver_os_open(original: Callable[..., Any]) -> Callable[..., Any]:
    def guardada(path: Any, flags: int, *args: Any, **kwargs: Any) -> Any:
        if flags & _FLAGS_ESCRITURA:
            _comprobar_escritura(path, "os.open", kwargs.get("dir_fd"))
        return original(path, flags, *args, **kwargs)

    return guardada


def envolver_truncate(original: Callable[..., Any]) -> Callable[..., Any]:
    def guardada(path: Any, *args: Any, **kwargs: Any) -> Any:
        _comprobar_escritura(path, "os.truncate")
        return original(path, *args, **kwargs)

    return guardada


def instalar(setattr_: Callable[[Any, str, Any], None]) -> None:
    """Envuelve todas las vías de borrado conocidas usando `setattr_` (monkeypatch o setattr directo)."""

    import shutil

    setattr_(shutil, "rmtree", envolver_borrado(shutil.rmtree, "shutil.rmtree"))
    setattr_(os, "remove", envolver_borrado(os.remove, "os.remove"))
    setattr_(os, "unlink", envolver_borrado(os.unlink, "os.unlink"))
    setattr_(os, "rmdir", envolver_borrado(os.rmdir, "os.rmdir"))
    setattr_(os, "removedirs", envolver_borrado(os.removedirs, "os.removedirs"))
    setattr_(os, "rename", envolver_renombrado(os.rename, "os.rename"))
    setattr_(os, "replace", envolver_renombrado(os.replace, "os.replace"))
    setattr_(subprocess, "Popen", PopenGuardado)
    import builtins
    import io

    abrir = envolver_open(io.open, "open")
    setattr_(builtins, "open", abrir)
    setattr_(io, "open", abrir)
    setattr_(os, "open", envolver_os_open(os.open))
    setattr_(os, "truncate", envolver_truncate(os.truncate))
    setattr_(os, "system", envolver_proceso(os.system, "os.system"))
    for nombre in _FIRMAS_OS:
        if hasattr(os, nombre):
            setattr_(os, nombre, envolver_proceso(getattr(os, nombre), f"os.{nombre}"))
