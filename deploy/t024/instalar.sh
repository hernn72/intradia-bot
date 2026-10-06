#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "instalar.sh debe ejecutarse como root" >&2
  exit 1
fi

ENV_FILE=/etc/intradia-bot/t024.env
if [[ ! -r "${ENV_FILE}" ]]; then
  echo "no se puede leer ${ENV_FILE}" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

for name in T024_USER T024_REPO_DIR T024_PYTHON T024_DATA_DIR T024_ARTEFACTOS_DIR T024_LOG; do
  if [[ -z "${!name:-}" ]]; then
    echo "falta ${name} en ${ENV_FILE}" >&2
    exit 1
  fi
done

run_as_user() {
  runuser -u "${T024_USER}" -- "$@"
}

run_in_repo() {
  runuser -u "${T024_USER}" -- bash -c 'cd "$1" && shift && exec "$@"' bash "${T024_REPO_DIR}" "$@"
}

run_as_user git -C "${T024_REPO_DIR}" rev-parse --is-inside-work-tree >/dev/null
if [[ -n "$(run_as_user git -C "${T024_REPO_DIR}" status --porcelain)" ]]; then
  echo "T024_REPO_DIR debe ser un worktree git limpio: ${T024_REPO_DIR}" >&2
  exit 1
fi

advisor_file="$(run_in_repo env PYTHONDONTWRITEBYTECODE=1 "${T024_PYTHON}" -c "import advisor; print(advisor.__file__)" 2>/dev/null)"
case "${advisor_file}" in
  "${T024_REPO_DIR}"/advisor/*) ;;
  *)
    echo "advisor se importa fuera de ${T024_REPO_DIR}/advisor: ${advisor_file}" >&2
    exit 1
    ;;
esac

run_in_repo env PYTHONDONTWRITEBYTECODE=1 "${T024_PYTHON}" -c "from advisor.research.t024_decision import verificar_identidad; print(verificar_identidad())" >/dev/null

install -d -m 0755 -o "${T024_USER}" -g "${T024_USER}" "${T024_ARTEFACTOS_DIR}"
# El wrapper corre como T024_USER y escribe sus propios logs: ningún directorio suyo puede ser de root.
install -d -m 0755 -o "${T024_USER}" -g "${T024_USER}" "${T024_ARTEFACTOS_DIR}/logs"
install -d -m 0755 -o "${T024_USER}" -g "${T024_USER}" "$(dirname "${T024_LOG}")"

tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT
# El render corre como T024_USER: necesita escribir en el temporal.
chown "${T024_USER}" "${tmpdir}"

run_in_repo env PYTHONDONTWRITEBYTECODE=1 "${T024_PYTHON}" - "${T024_REPO_DIR}" "${tmpdir}" <<'PY'
import os
import sys
from pathlib import Path

repo = Path(sys.argv[1])
out = Path(sys.argv[2])
sys.path.insert(0, str(repo))
from deploy.t024.render import render

valores = {name: os.environ[name] for name in (
    "T024_USER",
    "T024_REPO_DIR",
    "T024_PYTHON",
    "T024_DATA_DIR",
    "T024_ARTEFACTOS_DIR",
    "T024_LOG",
)}
src = repo / "deploy" / "t024" / "systemd"
for name in ("intradia-t024-checkpoint.service", "intradia-t024-checkpoint.timer"):
    (out / name).write_text(render((src / name).read_text(encoding="utf-8"), valores), encoding="utf-8")
PY

install -m 0644 "${tmpdir}/intradia-t024-checkpoint.service" /etc/systemd/system/intradia-t024-checkpoint.service
install -m 0644 "${tmpdir}/intradia-t024-checkpoint.timer" /etc/systemd/system/intradia-t024-checkpoint.timer
systemctl daemon-reload
systemctl enable --now intradia-t024-checkpoint.timer
systemctl list-timers intradia-t024-checkpoint.timer
