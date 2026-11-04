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

# La Pi no trae la herramienta sqlite3: todo pasa por el Python del servicio.
sql() {
  PYTHONDONTWRITEBYTECODE=1 "${PYTHON}" -c 'import sqlite3, sys
conn = sqlite3.connect("file:" + sys.argv[1] + "?mode=ro", uri=True)
for row in conn.execute(sys.argv[2]):
    print("|".join("" if value is None else str(value) for value in row))' "$1" "$2"
}
query() { sql "${DB}" "$1"; }
backup_db() {
  PYTHONDONTWRITEBYTECODE=1 "${PYTHON}" -c 'import sqlite3, sys
source, target = sqlite3.connect(sys.argv[1]), sqlite3.connect(sys.argv[2])
with target:
    source.backup(target)' "$1" "$2"
}

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

write_dropin() {
  mkdir -p "${DROPIN_DIR}"
  printf '[Service]\nSuccessExitStatus=2\nEnvironment=SUPERBOT_ALERTAS=%s\n' "${ALERTAS}" > "${DROPIN}"
  systemctl daemon-reload
}

restore_code() {
  local dir="$1"
  repo checkout -q -f --detach "$(cat "${dir}/sha")" || return 1
  if [[ -s "${dir}/rama" ]]; then repo checkout -q -f "$(cat "${dir}/rama")" || return 1; fi
  [[ "$(repo rev-parse HEAD)" == "$(cat "${dir}/sha")" && -z "$(repo status --porcelain --untracked-files=no)" ]] || return 1
  if [[ -f "${dir}/dropin.conf" ]]; then
    mkdir -p "${DROPIN_DIR}"
    cp "${dir}/dropin.conf" "${DROPIN}"
  else
    rm -f "${DROPIN}"
    rmdir "${DROPIN_DIR}" 2>/dev/null || true
  fi
  systemctl daemon-reload
}

# Con el código a medias el temporizador se queda parado: mejor sin ejecuciones que
# una cartera movida por un árbol mezclado.
restore_or_halt() {
  restore_code "$1" && return 0
  trap - EXIT
  die "no se pudo restaurar ${WORKDIR}; temporizador PARADO, copia en $1"
}

wait_idle() {
  for _ in $(seq 1 1800); do idle && return 0; sleep 1; done
  die "${SERVICE} sigue en marcha"
}

deploy() {
  local sha dir
  check
  repo fetch -q origin
  sha="$(repo rev-parse --verify "$1^{commit}")" || die "no existe $1"
  repo merge-base --is-ancestor "${sha}" origin/main || die "${sha} no está en origin/main"

  if [[ "$(repo rev-parse HEAD)" == "${sha}" ]]; then
    write_dropin
    echo "Código ya en ${sha}: solo cambia la unidad. Avisos: ${ALERTAS}. El punto de reversión no se mueve."
    return
  fi

  systemctl stop "${TIMER}"
  trap 'systemctl start "${TIMER}"' EXIT
  wait_idle

  dir="${BACKUPS}/$(date +%Y%m%d-%H%M%S)"
  mkdir -p "${dir}"
  chmod 700 "${BACKUPS}" "${dir}"
  repo rev-parse HEAD > "${dir}/sha"
  repo symbolic-ref -q --short HEAD > "${dir}/rama" || true
  if [[ -f "${DROPIN}" ]]; then cp "${DROPIN}" "${dir}/dropin.conf"; fi
  backup_db "${DB}" "${dir}/superbot.db"
  [[ "$(sql "${dir}/superbot.db" 'PRAGMA integrity_check')" == ok ]] || die "copia dañada; no se ha cambiado nada"
  sha256sum "${dir}/superbot.db" > "${dir}/SHA256SUMS"
  echo "Copia en ${dir}"

  # git puede salir con 0 y dejar ficheros sin escribir: se comprueba el árbol.
  if ! {
    repo checkout -q --detach "${sha}" &&
    [[ "$(repo rev-parse HEAD)" == "${sha}" && -z "$(repo status --porcelain --untracked-files=no)" ]] &&
    write_dropin &&
    as_user env SUPERBOT_DB="${DB}" bash -c "cd '${WORKDIR}' && '${PYTHON}' -c 'import superbot.engine, superbot.data, advisor.data.market_data' && '${PYTHON}' -m superbot status" > /dev/null
  }; then
    echo "Fallo al desplegar: se restaura el estado anterior." >&2
    restore_or_halt "${dir}"
    exit 1
  fi
  ln -sfn "${dir}" "${BACKUPS}/ultima"
  echo "Desplegado ${sha}. Avisos: ${ALERTAS}. Reversión a $(cut -c1-7 "${dir}/sha")."
}

revert() {
  local dir saved
  dir="$(readlink -f "${BACKUPS}/ultima")"
  [[ -f "${dir}/sha" ]] || die "no hay copia en ${BACKUPS}"
  echo "Copia $(basename "${dir}"): código $(cut -c1-7 "${dir}/sha")"
  systemctl stop "${TIMER}"
  trap 'systemctl start "${TIMER}"' EXIT
  wait_idle
  restore_or_halt "${dir}"
  if [[ "${1:-}" == --con-base ]]; then
    (cd "${dir}" && sha256sum -c SHA256SUMS --quiet) || die "la copia no coincide con su suma"
    saved="${dir}/antes-de-revertir-$(date +%Y%m%d-%H%M%S).db"
    backup_db "${DB}" "${saved}"
    install -o "${RUN_USER:-root}" -m 600 "${dir}/superbot.db" "${DB}"
    echo "Base restaurada. La anterior queda en ${saved}"
  fi
  echo "Revertido a $(repo rev-parse --short HEAD)."
}

case "${1:-}" in
  comprobar) check ;;
  desplegar) [[ -n "${2:-}" ]] || die "falta el sha"; deploy "$2" ;;
  revertir) revert "${2:-}" ;;
  *) die "uso: comprobar | desplegar <sha> | revertir [--con-base]" ;;
esac
