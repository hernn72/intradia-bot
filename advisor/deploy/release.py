"""¿Qué versión del código está corriendo esta máquina?

`verificar-systemd` compara las unidades instaladas con las plantillas del
repo. Este módulo es su equivalente para el **código**: compara lo que hay en
`HEAD` con el tag que se dijo desplegar, y publica cada punto por separado en
vez de un sí/no.

La regla que lo gobierna es INV-16: si no se puede determinar algo —no hay
red para preguntar a `origin`, no se puede ejecutar `git`— se declara
desconocido. Nunca se asume que coincide.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from advisor.run.git import (
    UNKNOWN_SHA,
    GitDirty,
    commits_ahead_of,
    exact_release_tag,
    git_dirty,
    git_sha,
    nearest_tag,
    remote_tag_sha,
    tag_sha,
)

EN_TAG = "EN_TAG"
FUERA_DE_TAG = "FUERA_DE_TAG"
DESCONOCIDO = "DESCONOCIDO"

ORIGIN_COINCIDE = "COINCIDE"
ORIGIN_DIFIERE = "DIFIERE"
ORIGIN_AUSENTE = "AUSENTE"
ORIGIN_DESCONOCIDO = "DESCONOCIDO"


@dataclass(frozen=True)
class ReleaseStatus:
    head_sha: str
    tag: Optional[str]
    nearest_tag: Optional[str]
    commits_ahead: Optional[int]
    dirty: GitDirty
    local_tag_sha: Optional[str]
    origin_state: str
    origin_tag_sha: Optional[str]
    origin_reason: Optional[str]
    verdict: str
    reasons: List[str]

    @property
    def exit_code(self) -> int:
        """0 solo con `EN_TAG` y árbol limpio; cualquier otra cosa es un fallo."""

        return 0 if self.verdict == EN_TAG and self.dirty.value is False else 1


def evaluate_release(
    repo: str | Path = ".",
    *,
    remote: str = "origin",
    check_remote: bool = True,
) -> ReleaseStatus:
    head = git_sha(repo)
    dirty = git_dirty(repo)
    tag = exact_release_tag(repo)

    nearest: Optional[str] = None
    ahead: Optional[int] = None
    if tag is None:
        nearest = nearest_tag(repo)
        if nearest is not None:
            ahead = commits_ahead_of(nearest, repo)

    local_sha = tag_sha(tag, repo) if tag is not None else None

    origin_state = ORIGIN_DESCONOCIDO
    origin_sha: Optional[str] = None
    origin_reason: Optional[str] = None
    if tag is None:
        origin_reason = "HEAD no está en un release: no hay nada que comparar con el remoto"
    elif not check_remote:
        origin_reason = "comprobación del remoto desactivada"
    else:
        result = remote_tag_sha(tag, repo, remote=remote)
        if not result.ok:
            origin_reason = result.error
        elif not result.output:
            origin_state = ORIGIN_AUSENTE
            origin_reason = f"{remote} no publica el tag {tag}"
        else:
            origin_sha = result.output
            origin_state = ORIGIN_COINCIDE if origin_sha == local_sha else ORIGIN_DIFIERE

    reasons: List[str] = []
    verdict = EN_TAG

    if head == UNKNOWN_SHA:
        reasons.append("no se puede leer el SHA de HEAD")
        verdict = DESCONOCIDO
    elif dirty.value is None:
        reasons.append(f"no se puede saber si el árbol está limpio: {dirty.reason}")
        verdict = DESCONOCIDO
    elif tag is None:
        if nearest is None:
            reasons.append("no hay ningún release vX.Y.Z alcanzable desde HEAD")
            verdict = DESCONOCIDO
        else:
            contados = "un número indeterminado de" if ahead is None else str(ahead)
            reasons.append(f"HEAD está {contados} commits por delante de {nearest}")
            verdict = FUERA_DE_TAG
    else:
        if dirty.value:
            # El SHA puede coincidir con el tag y el código en ejecución no: un
            # fichero modificado sin commitear no cambia HEAD.
            reasons.append("el árbol tiene ficheros con seguimiento modificados")
            verdict = FUERA_DE_TAG
        if origin_state == ORIGIN_DIFIERE:
            reasons.append(f"{remote} publica {origin_sha} para {tag} y aquí es {local_sha}")
            verdict = FUERA_DE_TAG
        elif origin_state == ORIGIN_AUSENTE:
            reasons.append(f"el tag {tag} no existe en {remote}")
            verdict = FUERA_DE_TAG
        elif origin_state == ORIGIN_DESCONOCIDO and verdict == EN_TAG:
            reasons.append(f"no se ha podido comprobar {tag} contra {remote}: {origin_reason}")
            verdict = DESCONOCIDO

    return ReleaseStatus(
        head_sha=head,
        tag=tag,
        nearest_tag=nearest,
        commits_ahead=ahead,
        dirty=dirty,
        local_tag_sha=local_sha,
        origin_state=origin_state,
        origin_tag_sha=origin_sha,
        origin_reason=origin_reason,
        verdict=verdict,
        reasons=reasons,
    )


def format_release_status(status: ReleaseStatus) -> str:
    """Cada punto por separado: el veredicto no sustituye a la materia prima."""

    dirty = {True: "sí", False: "no", None: "desconocido"}[status.dirty.value]
    lines = [
        f"HEAD               {status.head_sha}",
        f"tag exacto         {status.tag or 'ninguno'}",
    ]
    if status.tag is None:
        cercano = status.nearest_tag or "ninguno"
        adelanto = "desconocido" if status.commits_ahead is None else str(status.commits_ahead)
        lines.append(f"tag más cercano    {cercano} (HEAD por delante: {adelanto} commits)")
    else:
        lines.append(f"SHA del tag        {status.local_tag_sha or 'desconocido'}")
    lines.append(f"árbol modificado   {dirty}" + (f" ({status.dirty.reason})" if status.dirty.reason else ""))
    origen = f"origin             {status.origin_state}"
    if status.origin_tag_sha:
        origen += f" ({status.origin_tag_sha})"
    elif status.origin_reason:
        origen += f" ({status.origin_reason})"
    lines.append(origen)
    lines.append(f"veredicto          {status.verdict}")
    for reason in status.reasons:
        lines.append(f"  - {reason}")
    return "\n".join(lines)
