"""Render mínimo de plantillas T-024 sin dependencias externas."""

from __future__ import annotations

import re

_MARKER = re.compile(r"@T024_[A-Z0-9_]+@")


def render(texto: str, valores: dict[str, str]) -> str:
    """Sustituye marcadores @T024_...@ y falla si falta alguno."""

    def reemplazo(match: re.Match[str]) -> str:
        clave = match.group(0)[1:-1]
        if clave not in valores:
            raise ValueError(f"falta valor para {match.group(0)}")
        return valores[clave]

    salida = _MARKER.sub(reemplazo, texto)
    pendiente = sorted(set(_MARKER.findall(salida)))
    if pendiente:
        raise ValueError(f"quedan marcadores sin resolver: {pendiente}")
    return salida
