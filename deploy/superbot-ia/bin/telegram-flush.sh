#!/bin/bash
set -euo pipefail

exec /home/fer/superbot-ia-venv/bin/python -B -m superbot.ia --db /home/fer/superbot-ia-forward/datos/superbot_ia.db telegram
