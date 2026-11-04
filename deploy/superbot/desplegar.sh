#!/usr/bin/env bash
# Despliegue de Superbot en la Pi, con copia previa y reversión.
#
#   sudo deploy/superbot/desplegar.sh comprobar          solo lectura
#   sudo deploy/superbot/desplegar.sh desplegar <sha>    copia, código, unidad, temporizador
#   sudo deploy/superbot/desplegar.sh revertir           vuelve al estado de la última copia
#   sudo deploy/superbot/desplegar.sh revertir --con-base   además restaura superbot.db
#
# Lee rutas y usuario de la unidad instalada. No toca T-024, T-025 ni el entorno.
set -euo pipefail

SERVICE=superbot-paper.service
TIMER=superbot-paper.timer
DROPIN_DIR="/etc/systemd/system/${SERVICE}.d"
DROPIN="${DROPIN_DIR}/10-operativos.conf"
BACKUPS="${SUPERBOT_BACKUPS:-/var/backups/superbot}"
ALERTAS="${SUPERBOT_ALERTAS_MODO:-seco}"

die() { echo "ERROR: $*" >&2; exit 1; }
[[ "${EUID}" -eq 0 ]] || die "ejecuta con sudo"

prop() { systemctl show "${SERVICE}" -p "$1" --value; }
WORKDIR="$(prop WorkingDirectory)"
RUN_USER="$(prop User)"
DB="$(prop Environment | tr ' ' '\n' | sed -n 's/^SUPERBOT_DB=//p')"
PYTHON="$(prop ExecStart | sed -n 's/.*argv\[\]=\([^ ]*\).*/\1/p')"
[[ -n "${WORKDIR}" && -n "${DB}" && -n "${PYTHON}" ]] || die "no se pueden leer las rutas de ${SERVICE}"
[[ "${WORKDIR}" != *t024* && "${WORKDIR}" != *t025* ]] || die "${WORKDIR} parece de T-024 o T-025"

as_user() { sudo -u "${RUN_USER:-root}" -H "$@"; }
repo() { as_user git -c safe.directory="${WORKDIR}" -C "${WORKDIR}" "$@"; }
query() { sqlite3 "file:${DB}?mode=ro" "$1"; }

idle() {
  local state
  state="$(systemctl is-active "${SERVICE}" || true)"
  [[ "${state}" != activating && "${state}" != active ]]
}

check() {
  echo "Código:   ${WORKDIR} @ $(repo rev-parse --short HEAD)"
  echo "Base:     ${DB}"
  echo "Temporizador: $(systemctl is-active "${TIMER}" || true) · servicio: $(systemctl is-active "${SERVICE}" || true)"
  [[ -f "${DB}" ]] || die "no existe la base"
  [[ -z "$(repo status --porcelain --untracked-files=no)" ]] || die "árbol con cambios en ${WORKDIR}"
  [[ "$(query 'PRAGMA integrity_check')" == ok ]] || die "integridad de la base"
  echo "Disco libre: $(df -h "$(dirname "${DB}")" | awk 'NR==2 {print $4}')"
  echo "Cartera:  $(query "SELECT COUNT(*) FROM positions WHERE status = 'OPEN'") posiciones abiertas, $(query "SELECT COUNT(*) FROM orders WHERE status = 'PENDING'") órdenes pendientes"
  echo "Ejecuciones por estado: $(query "SELECT status || '=' || COUNT(*) FROM runs GROUP BY status" | paste -sd' ' -)"
  echo "Sin cerrar: $(query "SELECT COUNT(*) FROM runs WHERE status = 'RUNNING'")"
  echo "Cobertura histórica (símbolos con datos / total, peor caso):"
  query "SELECT MIN(1.0 * symbols_ok / (symbols_ok + symbols_err)), SUM(1.0 * symbols_ok / (symbols_ok + symbols_err) < 0.9), COUNT(*) FROM runs WHERE symbols_ok + symbols_err > 0" \
    | awk -F'|' '{printf "  mínimo %.3f · por debajo del 90 %%: %d de %d\n", $1, $2, $3}'
  echo "Posiciones con unidades reescaladas: $(query "SELECT COUNT(*) FROM positions p JOIN fills f ON f.position_id = p.id AND f.side = 'BUY' WHERE p.quantity <> f.quantity")"
}

restore_code() {
  local dir="$1"
  repo checkout -q --detach "$(cat "${dir}/sha")"
  if [[ -s "${dir}/rama" ]]; then repo checkout -q "$(cat "${dir}/rama")"; fi
  rm -f "${DROPIN}"
  rmdir "${DROPIN_DIR}" 2>/dev/null || true
  systemctl daemon-reload
}

wait_idle() {
  for _ in $(seq 1 1800); do idle && return 0; sleep 1; done
  die "${SERVICE} sigue en marcha"
}

deploy() {
  local sha="$1" dir
  check
  repo fetch -q origin
  repo cat-file -e "${sha}^{commit}" || die "no existe ${sha}"
  repo merge-base --is-ancestor "${sha}" origin/main || die "${sha} no está en origin/main"

  systemctl stop "${TIMER}"
  trap 'systemctl start "${TIMER}"' EXIT
  wait_idle

  dir="${BACKUPS}/$(date +%Y%m%d-%H%M%S)"
  mkdir -p "${dir}"
  chmod 700 "${BACKUPS}" "${dir}"
  repo rev-parse HEAD > "${dir}/sha"
  repo symbolic-ref -q --short HEAD > "${dir}/rama" || true
  sqlite3 "${DB}" ".backup '${dir}/superbot.db'"
  [[ "$(sqlite3 "${dir}/superbot.db" 'PRAGMA integrity_check')" == ok ]] || die "copia dañada; no se ha cambiado nada"
  sha256sum "${dir}/superbot.db" > "${dir}/SHA256SUMS"
  ln -sfn "${dir}" "${BACKUPS}/ultima"
  echo "Copia en ${dir}"

  if ! {
    repo checkout -q --detach "${sha}" &&
    mkdir -p "${DROPIN_DIR}" &&
    printf '[Service]\nSuccessExitStatus=2\nEnvironment=SUPERBOT_ALERTAS=%s\n' "${ALERTAS}" > "${DROPIN}" &&
    systemctl daemon-reload &&
    as_user env SUPERBOT_DB="${DB}" bash -c "cd '${WORKDIR}' && '${PYTHON}' -m superbot status" > /dev/null
  }; then
    echo "Fallo al desplegar: se restaura el código anterior." >&2
    restore_code "${dir}"
    exit 1
  fi
  echo "Desplegado ${sha}. Avisos: ${ALERTAS}."
}

revert() {
  local dir
  dir="$(readlink -f "${BACKUPS}/ultima")"
  [[ -f "${dir}/sha" ]] || die "no hay copia en ${BACKUPS}"
  systemctl stop "${TIMER}"
  trap 'systemctl start "${TIMER}"' EXIT
  wait_idle
  restore_code "${dir}"
  if [[ "${1:-}" == --con-base ]]; then
    (cd "${dir}" && sha256sum -c SHA256SUMS --quiet) || die "la copia no coincide con su suma"
    sqlite3 "${DB}" ".backup '${dir}/superbot-antes-de-revertir.db'"
    install -o "${RUN_USER:-root}" -m 600 "${dir}/superbot.db" "${DB}"
    echo "Base restaurada. La anterior queda en ${dir}/superbot-antes-de-revertir.db"
  fi
  echo "Revertido a $(repo rev-parse --short HEAD)."
}

case "${1:-}" in
  comprobar) check ;;
  desplegar) [[ -n "${2:-}" ]] || die "falta el sha"; deploy "$2" ;;
  revertir) revert "${2:-}" ;;
  *) die "uso: comprobar | desplegar <sha> | revertir [--con-base]" ;;
esac
