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
# Se carga como root: tiene que ser un fichero real de root y no escribible por grupo ni otros.
if [[ -L "${ENV_FILE}" || "$(stat -c '%u' "${ENV_FILE}")" != "0" ]] || [[ -n "$(find "${ENV_FILE}" -perm /022)" ]]; then
  echo "${ENV_FILE} debe ser un fichero de root, no enlace, sin escritura de grupo ni otros (0644)" >&2
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
if [[ ! -f "${T024_REPO_DIR}/deploy/t024/checkpoint.py" ]]; then
  echo "T024_REPO_DIR no contiene deploy/t024/checkpoint.py: ${T024_REPO_DIR}" >&2
  exit 1
fi
# El T024_CODE_SHA esperado sale del calendario operativo versionado (la misma fuente que usa el wrapper).
T024_CODE_SHA="$(run_in_repo env PYTHONDONTWRITEBYTECODE=1 "${T024_PYTHON}" -c 'import json; print(json.load(open("deploy/t024/calendario-checkpoints.json", encoding="utf-8"))["t024_code_sha"])')"
if [[ ! "${T024_CODE_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "t024_code_sha del calendario inválido: ${T024_CODE_SHA}" >&2
  exit 1
fi

if ! run_as_user git -C "${T024_REPO_DIR}" diff --quiet "${T024_CODE_SHA}" HEAD -- advisor config.yaml universe.yaml exchange_overrides.yaml pyproject.toml requirements.txt; then
  echo "el contrato de código T-024 difiere de ${T024_CODE_SHA} en rutas protegidas" >&2
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

identidad="$(run_in_repo env PYTHONDONTWRITEBYTECODE=1 "${T024_PYTHON}" -c "from advisor.research.t024_decision import verificar_identidad; print(verificar_identidad())")"
if [[ "${identidad}" != "${T024_CODE_SHA}" ]]; then
  echo "verificar_identidad() devolvió ${identidad}, esperado ${T024_CODE_SHA}" >&2
  exit 1
fi

t024_group="$(id -gn "${T024_USER}")"

# Artefactos, segunda copia (por defecto <artefactos>/copias/vintages) y data-dir fuera del worktree que ejecuta.
repo_real="$(realpath -m "${T024_REPO_DIR}")"
for ruta in "${T024_ARTEFACTOS_DIR}" "${T024_ARTEFACTOS_DIR}/copias/vintages" "${T024_DATA_DIR}"; do
  real="$(realpath -m "${ruta}")"
  case "${real}/" in
    "${repo_real}/"*)
      echo "${ruta} resuelve dentro del worktree ${repo_real}: no se instala" >&2
      exit 1
      ;;
  esac
  case "${repo_real}/" in
    "${real}/"*)
      echo "${ruta} contiene el worktree ${repo_real}: no se instala" >&2
      exit 1
      ;;
  esac
done
install -d -m 0755 -o "${T024_USER}" -g "${t024_group}" "${T024_ARTEFACTOS_DIR}"
# El wrapper corre como T024_USER y escribe sus propios logs: ningún directorio suyo puede ser de root.
install -d -m 0755 -o "${T024_USER}" -g "${t024_group}" "${T024_ARTEFACTOS_DIR}/logs"
install -d -m 0755 -o "${T024_USER}" -g "${t024_group}" "$(dirname "${T024_LOG}")"

tmpdir="$(mktemp -d -t t024-staging-XXXXXX)"
borrar_tmpdir() {
  # Solo el temporal propio: ruta no vacía, absoluta y con el prefijo de staging.
  case "${tmpdir:-}" in
    /*/t024-staging-*) rm -rf -- "${tmpdir:?}" ;;
    *) echo "no se borra ${tmpdir:-<vacío>}: no es un staging t024" >&2 ;;
  esac
}
trap borrar_tmpdir EXIT
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
