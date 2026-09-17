"""Carga de ``universe.yaml`` hacia el modelo ``Universe``."""

from __future__ import annotations

from pathlib import Path

import yaml

from advisor.universe.models import Universe


def load_universe(path: str | Path = "universe.yaml") -> Universe:
    """Carga y valida el universo de activos.

    Lanza ``FileNotFoundError`` si el archivo no existe y ``ValueError`` si la
    estructura no es la esperada o algún activo no supera la validación
    (ISIN con checksum incorrecto, divisa inválida, símbolo duplicado...).
    """

    universe_path = Path(path)
    if not universe_path.is_file():
        raise FileNotFoundError(f"No se encuentra el archivo de universo: {universe_path}")

    with universe_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    if not isinstance(raw, dict):
        raise ValueError(f"{universe_path} debe contener un mapeo YAML en la raíz")
    if "groups" not in raw:
        raise ValueError(f"{universe_path} debe contener una clave 'groups' en la raíz")

    universe = Universe(**raw)
    universe.validate_identity_metadata()
    return universe
