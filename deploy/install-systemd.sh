#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Ejecuta este script con sudo." >&2
  exit 1
fi

CONFIG_ENV="${CONFIG_ENV:-/etc/intradia-bot/systemd.env}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"

if [[ ! -f "${CONFIG_ENV}" ]]; then
  echo "No existe ${CONFIG_ENV}. Consulta deploy/systemd/README.md." >&2
  exit 1
fi

set -a
source "${CONFIG_ENV}"
set +a

: "${INTRADIA_BOT_USER:?falta INTRADIA_BOT_USER en ${CONFIG_ENV}}"
: "${INTRADIA_BOT_DIR:?falta INTRADIA_BOT_DIR en ${CONFIG_ENV}}"
: "${INTRADIA_BOT_PYTHON:?falta INTRADIA_BOT_PYTHON en ${CONFIG_ENV}}"
: "${INTRADIA_BOT_ENV_FILE:?falta INTRADIA_BOT_ENV_FILE en ${CONFIG_ENV}}"
: "${INTRADIA_BOT_ANALIZAR_LOG:?falta INTRADIA_BOT_ANALIZAR_LOG en ${CONFIG_ENV}}"
: "${INTRADIA_BOT_EVENT_LOG:?falta INTRADIA_BOT_EVENT_LOG en ${CONFIG_ENV}}"

cd "${INTRADIA_BOT_DIR}"

EVENT_TIME="$("${INTRADIA_BOT_PYTHON}" - <<'PY'
from advisor.config import load_config

print(load_config("config.yaml").events.pasada_evento_hora)
PY
)"

"${INTRADIA_BOT_PYTHON}" -m advisor.main render-systemd \
  --config-env "${CONFIG_ENV}" \
  --output-dir "${SYSTEMD_DIR}" \
  --event-time "${EVENT_TIME}"

systemctl daemon-reload
systemctl enable --now intradia-bot.timer
systemctl enable --now intradia-bot-event.timer
systemctl list-timers intradia-bot.timer intradia-bot-event.timer --no-pager
