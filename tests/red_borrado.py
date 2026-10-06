"""Red de seguridad de borrado para los tests (incidente 2026-10-06, evidence/2026-10-06-incidente-perdida-vintage/).

Solo biblioteca estándar: la usan `tests/conftest.py` (con monkeypatch, restaurable) y
`tests/red_hijos/sitecustomize.py`, que la instala en todo intérprete Python hijo lanzado por un test.

Ningún test puede borrar, mover ni pisar `/`, `$HOME`, la raíz del repo o sus antecesores, ni nada en `data/`,
`evidence/` o `.git/` del repo, ni una base SQLite del repo. Las órdenes externas se inspeccionan por tokens.

Riesgo residual documentado: un programa externo no Python cuya forma de borrar no se reconozca por sus
tokens (p. ej. un binario propio) no pasa por la red. Lo cubren los backups fuera del repositorio.
"""

from __future__ import annotations

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
    for token in argv[1:]:
        if token in {"-c", "-m"} or not token.startswith("-") or token == "-":
            break
        if token.startswith("--"):
            continue
        letras = token[1:]
        malas.extend(f"-{letra}" for letra in letras if letra in {"I", "E", "S"})
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
    tokens = _tokens(args, shell=shell)
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


class PopenGuardado(subprocess.Popen):  # type: ignore[type-arg]
    """`subprocess.Popen` que aplica `asegurar_hijo` a todo lanzamiento."""

    def __init__(self, args: Any, *posicionales: Any, **kwargs: Any) -> None:
        entorno = asegurar_hijo(
            args, shell=bool(kwargs.get("shell")), executable=kwargs.get("executable"), env=kwargs.get("env")
        )
        if entorno is not None:
            kwargs["env"] = entorno
        super().__init__(args, *posicionales, **kwargs)


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

    def guardada(*args: Any, **kwargs: Any) -> Any:
        if corto == "system":
            asegurar_hijo(args[0], shell=True)
            return original(*args, **kwargs)
        i_prog, i_argv, i_env = _FIRMAS_OS[corto]
        argv = list(args[i_argv]) if len(args) > i_argv else []
        programa = args[i_prog] if len(args) > i_prog else None
        orden = [os.fsdecode(programa), *argv[1:]] if programa is not None else argv
        entorno = asegurar_hijo(orden, executable=programa, env=args[i_env] if i_env is not None and len(args) > i_env else None)
        if entorno is not None and i_env is not None:
            args = (*args[:i_env], entorno, *args[i_env + 1 :])
        return original(*args, **kwargs)

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
    setattr_(os, "system", envolver_proceso(os.system, "os.system"))
    for nombre in _FIRMAS_OS:
        if hasattr(os, nombre):
            setattr_(os, nombre, envolver_proceso(getattr(os, nombre), f"os.{nombre}"))
