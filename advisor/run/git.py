"""Lectura del estado de git: una sola implementación para todo el asesor.

El manifiesto de cada pasada y ``verificar-release`` responden a la misma
pregunta —qué código está corriendo— y deben responderla con el mismo código
(INV-06). Aquí viven los primitivos; la interpretación (¿estamos en un tag?)
vive en ``advisor/deploy/release.py``.

La distinción que sostiene este módulo es la de INV-16: un comando que **falla**
no es lo mismo que un comando que devuelve vacío. ``git status --porcelain``
vacío significa «árbol limpio»; ``git status`` que no se puede ejecutar
significa «no lo sé», y eso se declara, no se convierte en ``False``.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

UNKNOWN_SHA = "unknown"

# Un release es `vX.Y.Z` y nada más. Cualquier otra etiqueta —`release-test`,
# `antes-de-tocar`, la que alguien deje en la Pi— no es una versión publicada:
# el flujo de release de CI solo construye sobre este patrón, así que aceptarla
# aquí permitiría dar por desplegado un tag que nunca pasó la CI.
RELEASE_TAG_PATTERN = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
# Lo mismo en el lenguaje de `git describe --match`, que usa globs, no regex.
RELEASE_TAG_GLOB = "v[0-9]*.[0-9]*.[0-9]*"


@dataclass(frozen=True)
class GitResult:
    """Salida de un comando de git, o el motivo por el que no la hay."""

    output: Optional[str]
    error: Optional[str]

    @property
    def ok(self) -> bool:
        return self.output is not None


@dataclass(frozen=True)
class GitDirty:
    """``True``/``False`` si se pudo comprobar; ``None`` con motivo si no."""

    value: Optional[bool]
    reason: Optional[str] = None


def run_git(args: list[str], repo: str | Path = ".", *, timeout: float = 5.0) -> GitResult:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return GitResult(None, "git no está instalado")
    except subprocess.TimeoutExpired:
        return GitResult(None, f"git {args[0]} superó el tiempo máximo ({timeout:g} s)")
    except OSError as exc:
        return GitResult(None, f"git {args[0]} no se pudo ejecutar: {exc.strerror or exc}")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        reason = detail[0] if detail else f"código de salida {result.returncode}"
        return GitResult(None, f"git {args[0]}: {reason}")
    return GitResult(result.stdout.strip(), None)


def git_sha(repo: str | Path = ".") -> str:
    """SHA de ``HEAD``, o ``unknown`` si no se puede leer."""

    return run_git(["rev-parse", "HEAD"], repo).output or UNKNOWN_SHA


def git_dirty(repo: str | Path = ".") -> GitDirty:
    """¿Hay ficheros con seguimiento modificados?

    Los ficheros sin seguimiento no cuentan: en la Pi `logs/` existe siempre y
    marcaría todas las pasadas como sucias sin que el código difiera del SHA.

    Si ``git status`` no se puede ejecutar, el valor es ``None`` —no ``False``—
    y el motivo viaja con él: un manifiesto que dice «árbol limpio» sin haberlo
    comprobado es peor que uno que dice «no lo sé» (INV-16).
    """

    result = run_git(["status", "--porcelain", "--untracked-files=no"], repo)
    if not result.ok:
        return GitDirty(None, result.error)
    return GitDirty(bool(result.output))


def release_tags_at_head(repo: str | Path = ".") -> List[str]:
    """Tags `vX.Y.Z` que apuntan a ``HEAD``, del más alto al más bajo.

    Se usa ``git tag --points-at`` y no ``git describe --exact-match`` porque
    con varios tags en el mismo commit `describe` elige uno por su cuenta: aquí
    hace falta verlos todos y quedarse con el de versión mayor, que es el que
    representa lo desplegado.
    """

    result = run_git(["tag", "--points-at", "HEAD"], repo)
    if not result.ok or not result.output:
        return []
    tags = [line.strip() for line in result.output.splitlines() if RELEASE_TAG_PATTERN.match(line.strip())]
    return sorted(tags, key=_version_key, reverse=True)


def exact_release_tag(repo: str | Path = ".") -> Optional[str]:
    """Tag de release que apunta exactamente a ``HEAD``, o ``None``."""

    tags = release_tags_at_head(repo)
    return tags[0] if tags else None


def nearest_tag(repo: str | Path = ".") -> Optional[str]:
    """Release alcanzable más reciente desde ``HEAD``, o ``None`` si no hay ninguno."""

    return run_git(
        ["describe", "--tags", "--abbrev=0", f"--match={RELEASE_TAG_GLOB}", "HEAD"], repo
    ).output or None


def _version_key(tag: str) -> Tuple[int, int, int]:
    match = RELEASE_TAG_PATTERN.match(tag)
    assert match is not None  # el llamante ya filtró por el patrón
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def commits_ahead_of(tag: str, repo: str | Path = ".") -> Optional[int]:
    """Commits de ``HEAD`` que no están en ``tag``, o ``None`` si no se puede contar."""

    result = run_git(["rev-list", "--count", f"{tag}..HEAD"], repo)
    if not result.ok or not result.output:
        return None
    try:
        return int(result.output)
    except ValueError:
        return None


def tag_sha(tag: str, repo: str | Path = ".") -> Optional[str]:
    """SHA del commit al que apunta un tag local (``^{commit}`` desreferencia anotados)."""

    return run_git(["rev-list", "-n", "1", tag], repo).output or None


def remote_tag_sha(
    tag: str,
    repo: str | Path = ".",
    *,
    remote: str = "origin",
    timeout: float = 10.0,
) -> GitResult:
    """SHA que el remoto publica para un tag.

    Devuelve el ``GitResult`` entero a propósito: sin red, ``ls-remote`` falla y
    el motivo es la diferencia entre «el tag no existe en origin» y «no he
    podido preguntar», que INV-16 obliga a distinguir.
    """

    result = run_git(["ls-remote", "--tags", remote, f"refs/tags/{tag}"], repo, timeout=timeout)
    if not result.ok:
        return result
    if not result.output:
        return GitResult("", None)
    # `ls-remote` lista `refs/tags/v1` y `refs/tags/v1^{}` para un tag anotado;
    # el segundo es el commit, que es lo que se compara con el SHA local.
    sha = ""
    for line in result.output.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        if parts[1].endswith("^{}"):
            return GitResult(parts[0], None)
        sha = parts[0]
    return GitResult(sha, None)
