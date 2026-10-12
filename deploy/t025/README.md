# T-025 forward en Raspberry Pi — pegamento de despliegue

**SHADOW / PAPER.** Estos ficheros no son el motor: `paper/` y el resto de
`EXECUTOR_PATHS_T025` (`paper/cli.py`) están congelados en el `t025_code_sha` de
la cohorte (`78db33d2f2ab71aaf32a5ca6b6d0aa59f06506b6`, tag `v0.5.0`). El
preflight de `t025_pasada.py` exige `HEAD` igual a ese SHA y el árbol limpio en
esas rutas; si no, la pasada no se ejecuta. Por eso el pegamento vive aquí,
fuera de la identidad, y en la Pi se ejecuta **copiado** en
`~/t025-forward/bin/`, nunca desde el worktree `~/intradia-t025`.

| Fichero | Destino en la Pi | Qué hace |
|---|---|---|
| `t025-pasada.sh` | `~/t025-forward/bin/` | fija la identidad congelada y el entorno, `cd` al worktree y lanza `t025_pasada.py` |
| `t025_pasada.py` | `~/t025-forward/bin/` | preflight de identidad, `paper run` de la última pasada D-50 y Telegram por sesión cuyo texto visible cambió |
| `t025_resumen.py` | `~/t025-forward/bin/` | vista resumida del mensaje para Telegram |
| `systemd/intradia-t025-paper.{service,timer}` | `/etc/systemd/system/` | lun-vie 07:00/08:30/14:30/21:00 Europe/London |

`t025.env` (0600: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `T025_TELEGRAM_SEND`)
no se versiona.

## Telegram

El texto de `python -m paper telegram --session D` (capa de visibilidad) es la
referencia: su sha256 decide si una sesión se reenvía. A Telegram va
`t025_resumen.resumir(texto, sesión)`, que agrupa las señales por estado
(MARKET_PASS, rechazo, pendiente de validar la barra de entrada) y política, sin
niveles por señal y sin añadir ningún dato. Los niveles siguen en `paper.db`
(`python -m paper signals`). Si alguna línea no tiene la forma conocida, o el
resumen falla, se envía el texto original de siempre.

«Pendiente de validar la barra de entrada» sustituye al «pendiente de la
apertura» del texto congelado: la ingesta solo guarda barras cerradas más el
settlement, así que `comprobaciones_de_apertura = 0` en las pasadas del día de
entrada es lo esperado.

## Desplegar

```bash
scp deploy/t025/t025_pasada.py deploy/t025/t025_resumen.py fer@<pi>:~/t025-forward/bin/
ssh fer@<pi> 'sha256sum ~/t025-forward/bin/*'   # contrastar con el commit fusionado
```

No hace falta tocar `~/intradia-t025`, el venv, `paper.db` ni las unidades.
