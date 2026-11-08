#!/bin/bash
set -euo pipefail

# Igual que ~/superbot-ia-pruebas/bin/con-clave.sh: solo lee la clave de
# Anthropic, nunca el resto de variables de /home/fer/intradia-bot/.env (que
# incluye secretos de otro bot, p. ej. su propio Telegram).
export SUPERBOT_IA_API_KEY="$(sed -n 's/^ANTHROPIC_API_KEY=//p' /home/fer/intradia-bot/.env | tr -d "\"'")"
: "${SUPERBOT_IA_API_KEY:?falta ANTHROPIC_API_KEY en /home/fer/intradia-bot/.env}"

exec /home/fer/superbot-ia-venv/bin/python -B -m superbot.ia --db /home/fer/superbot-ia-forward/datos/superbot_ia.db pasada
