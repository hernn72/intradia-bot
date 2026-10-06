"""Única puerta de borrado de las herramientas T-024: solo directorios de staging propios.

El 2026-10-06 un `staging = Path()` hizo que un `shutil.rmtree` de limpieza actuara sobre la raíz del
checkout y se perdieran datos no versionados irrecuperables (evidence/2026-10-06-incidente-perdida-vintage/).
Por eso nada en deploy/t024 llama a `shutil.rmtree` directamente: todo borrado pasa por `borrar_staging`,
que niega por defecto y solo acepta un directorio `.t024-staging-*` que sea hijo directo de la base esperada.
"""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

PREFIJO_STAGING = ".t024-staging-"
REPO = Path(__file__).resolve().parents[2]
SUFIJOS_SQLITE = (".db", ".sqlite", ".sqlite3")


class BorradoDenegado(RuntimeError):
    """La ruta no es un staging T-024 válido: no se borra nada."""


def _protegidas() -> tuple[Path, ...]:
    candidatas = [Path("/"), Path.home(), REPO, Path.cwd()]
    return tuple(dict.fromkeys(p.resolve() for p in candidatas))


def _es_sqlite(nombre: str) -> bool:
    bajo = nombre.lower()
    return any(bajo.endswith(s) or f"{s}." in bajo or f"{s}-" in bajo for s in SUFIJOS_SQLITE)


def validar_staging(ruta: str | os.PathLike[str], *, base: str | os.PathLike[str]) -> Path:
    """Devuelve la ruta absoluta si es un staging borrable; si no, `BorradoDenegado`.

    Exige, en este orden:
    - nombre literal con el prefijo (rechaza `Path()`, `.`, `..` y vacíos antes de resolver);
    - que exista como directorio real, no enlace;
    - que sea hijo directo de `base`;
    - que no sea ni contenga ninguna ruta protegida (`/`, `$HOME`, raíz del repo, cwd);
    - que no contenga `.git` ni bases SQLite.
    """

    crudo = os.fspath(ruta)
    nombre = Path(crudo).name
    if crudo.strip() in {"", ".", ".."} or nombre in {"", ".", ".."}:
        raise BorradoDenegado(f"ruta de staging vacía o relativa al directorio actual: {crudo!r}")
    if not nombre.startswith(PREFIJO_STAGING) or len(nombre) == len(PREFIJO_STAGING):
        raise BorradoDenegado(f"{crudo!r} no es un staging {PREFIJO_STAGING}*")
    sin_resolver = Path(crudo).absolute()
    if sin_resolver.is_symlink():
        raise BorradoDenegado(f"{crudo!r} es un enlace simbólico")
    try:
        absoluta = sin_resolver.resolve(strict=True)
        base_abs = Path(base).resolve(strict=True)
    except OSError as exc:
        raise BorradoDenegado(f"staging o base inexistente: {exc}") from exc
    if not absoluta.is_dir():
        raise BorradoDenegado(f"{absoluta} no es un directorio")
    if absoluta.parent != base_abs or absoluta.name != nombre:
        raise BorradoDenegado(f"{absoluta} no es hijo directo de la base {base_abs}")
    for protegida in _protegidas():
        if absoluta == protegida or absoluta in protegida.parents:
            raise BorradoDenegado(f"{absoluta} es o contiene una ruta protegida ({protegida})")
    for raiz, dirs, ficheros in os.walk(absoluta, followlinks=False):
        if ".git" in dirs or ".git" in ficheros:
            raise BorradoDenegado(f"{raiz} contiene .git")
        sqlite = [f for f in ficheros if _es_sqlite(f)]
        if sqlite:
            raise BorradoDenegado(f"{raiz} contiene bases SQLite: {sqlite[:3]}")
    return absoluta


def borrar_staging(ruta: str | os.PathLike[str], *, base: str | os.PathLike[str]) -> None:
    """Borra un staging T-024 validado. Cualquier duda: `BorradoDenegado` y no se toca nada.

    Para estrechar la ventana entre validar y borrar, el staging se renombra antes a una lápida
    `.t024-staging-borrando-*` en la misma base (renombrado atómico a un nombre nuevo), se revalida la
    lápida y solo entonces se borra, y solo con un `rmtree` resistente a enlaces simbólicos.
    """

    if not getattr(shutil.rmtree, "avoids_symlink_attacks", False):
        raise BorradoDenegado("shutil.rmtree no es resistente a enlaces simbólicos en esta plataforma")
    origen = validar_staging(ruta, base=base)
    lapida = origen.parent / nombre_staging(f"borrando-{uuid.uuid4().hex}")
    os.rename(origen, lapida)
    shutil.rmtree(validar_staging(lapida, base=base))


def promover_sin_pisar(staging: str | os.PathLike[str], destino: str | os.PathLike[str]) -> None:
    """Materializa el contenido de `staging` en `destino` sin sobrescribir nunca nada.

    `destino` se crea con `mkdir` exclusivo (falla si ya existe, aunque esté vacío) y cada fichero se enlaza
    con `os.link`, que también falla si el nombre existe. Exige ficheros regulares, sin enlaces simbólicos, en
    el mismo sistema de ficheros. El staging sigue existiendo: lo borra después quien lo creó, vía la guarda.
    """

    origen = Path(staging)
    final = Path(destino)
    relativos: list[Path] = []
    for raiz, dirs, ficheros in os.walk(origen, followlinks=False):
        for nombre in [*dirs, *ficheros]:
            ruta = Path(raiz) / nombre
            if ruta.is_symlink():
                raise BorradoDenegado(f"{ruta} es un enlace simbólico: no se promueve")
        relativos.extend((Path(raiz) / f).relative_to(origen) for f in ficheros)
    os.mkdir(final)
    for rel in sorted(relativos):
        (final / rel).parent.mkdir(parents=True, exist_ok=True)
        os.link(origen / rel, final / rel)


def nombre_staging(etiqueta: str) -> str:
    """Nombre canónico de staging; la etiqueta no puede introducir separadores de ruta."""

    if not etiqueta or "/" in etiqueta or os.sep in etiqueta or etiqueta in {".", ".."}:
        raise BorradoDenegado(f"etiqueta de staging inválida: {etiqueta!r}")
    return f"{PREFIJO_STAGING}{etiqueta}"
