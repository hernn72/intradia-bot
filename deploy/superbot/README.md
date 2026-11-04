# Superbot — paper visible

**PAPER OPERACIONAL / NO VALIDADA PARA CAPITAL REAL.** Separado de T-024 y
T-025: base propia (`superbot.db`), paquete `superbot/` que no importa `paper/`
ni `advisor.research`, y ninguna política B2/S2/C0.

Plantillas systemd. Los `@VARIABLES@` se sustituyen al instalar. Para actualizar una
instalación existente, `desplegar.sh`.

| Unidad | Qué hace |
|---|---|
| `superbot-paper.timer` → `superbot-paper.service` | `python -m superbot run --telegram` lun-vie 18:15 y 22:45 (Madrid) |
| `superbot-dashboard.service` | dashboard en `127.0.0.1:8765` |

La ruta de la base va en `SUPERBOT_DB` y debe quedar fuera de los worktrees y
directorios de T-024 y T-025.

## Actualizar en la Pi

```bash
sudo deploy/superbot/desplegar.sh comprobar           # solo lectura
sudo deploy/superbot/desplegar.sh desplegar <sha>     # el sha debe estar en origin/main
sudo deploy/superbot/desplegar.sh revertir            # código y unidad anteriores
sudo deploy/superbot/desplegar.sh revertir --con-base # además restaura superbot.db
```

`desplegar` para el temporizador, espera a que no haya ejecución, copia la base en
`/var/backups/superbot/<fecha>/` y comprueba la copia antes de cambiar nada. Si algo
falla, restaura el código. `SuccessExitStatus=2` y el modo de avisos van en un
drop-in, así que revertir no toca la unidad instalada.

Los avisos arrancan en `seco`. Para enviarlos, añade `SUPERBOT_ALERTAS_BOT_TOKEN` y
`SUPERBOT_ALERTAS_CHAT_ID` al fichero de entorno y repite con
`SUPERBOT_ALERTAS_MODO=1` y el mismo sha: solo cambia la unidad y el punto de
reversión no se mueve. Si no se puede restaurar el código, el temporizador se
queda parado a propósito.

No hay migración de esquema: la versión anterior puede leer la base que deja esta,
así que `revertir` sin `--con-base` conserva las ejecuciones hechas entretanto.
