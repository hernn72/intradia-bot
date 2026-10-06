"""Instala la red de borrado de los tests en todo intérprete Python hijo lanzado durante la sesión.

Solo actúa si `INTRADIA_RED_BORRADO_REPO` está definida (la define `tests/conftest.py`). Si el módulo de la red
no se puede importar, el hijo falla cerrado en vez de ejecutarse sin red.
"""

import os
import sys

_repo = os.environ.get("INTRADIA_RED_BORRADO_REPO")
if _repo:
    if _repo not in sys.path:
        sys.path.insert(0, _repo)
    try:
        from tests import red_borrado as _red
    except Exception as exc:  # pragma: no cover - fallo cerrado
        raise SystemExit(f"red de borrado de tests no disponible en el proceso hijo: {exc}") from exc
    _red.instalar(setattr)
