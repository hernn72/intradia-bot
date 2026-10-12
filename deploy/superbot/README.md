# Superbot — paper visible

**PAPER OPERACIONAL / NO VALIDADA PARA CAPITAL REAL.** Separado de T-024 y
T-025: base propia (`superbot.db`), paquete `superbot/` que no importa `paper/`
ni `advisor.research`, y ninguna política B2/S2/C0.

Plantillas systemd **sin instalar**. Los `@VARIABLES@` se sustituyen al
desplegar; el despliegue en la Pi espera a la revisión del PR.

| Unidad | Qué hace |
|---|---|
| `superbot-paper.timer` → `superbot-paper.service` | `python -m superbot run --telegram` lun-vie 18:15 y 22:45 (Madrid) |
| `superbot-dashboard.service` | dashboard en `127.0.0.1:8765` |

La ruta de la base va en `SUPERBOT_DB` y debe quedar fuera de los worktrees y
directorios de T-024 y T-025.
