#!/usr/bin/env bash
# Pasada programada de T-025 (v0.5.0, engine_v1). Pegamento de despliegue, fuera del repo.
set -euo pipefail

REPO=/home/fer/intradia-t025
PY=/home/fer/t025-venv/bin/python
export T025_DB=/home/fer/t025-forward/paper.db
export T025_STATE=/home/fer/t025-forward/estado
# Identidad congelada de la cohorte (paper_cohort.t025_code_sha y época de entorno 1).
export T025_CODE_SHA=78db33d2f2ab71aaf32a5ca6b6d0aa59f06506b6
export T025_PYTHON_VERSION=3.13.5
export T025_PACKAGES_SHA256=225904f7327c8af8a1e85c6ddc146bbee763e902553eab5d315e454c788d243b
export T025_REQUIREMENTS_SHA256=9336e876932f686d6e970cc1942ce913acfcf4dd56001dd00c0b0ba1e87ba576
export T025_MAX_LAG_MIN=60

cd "$REPO"
export PYTHONDONTWRITEBYTECODE=1
mkdir -p "$T025_STATE"
exec "$PY" /home/fer/t025-forward/bin/t025_pasada.py
