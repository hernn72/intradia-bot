# T-024 forward en Raspberry Pi

La Pi es el host 24/7 de la fase A: un timer diario llama al wrapper y el wrapper solo actúa si la fecha
actual en `Atlantic/Canary` es un checkpoint declarado en `calendario-checkpoints.json`. Ese intento
verifica identidad, construye la petición exacta, congela una vez, guarda artefactos y hashes, y termina.

La fase B ocurre en el PC: copiar y verificar la cosecha, versionar evidencia y ejecutar después el
registro y los conteos del runbook de investigación.

## Worktree dedicado

Producción sigue en `/home/fer/intradia-bot` con el tag operativo. La captura forward usa un worktree
separado en `/home/fer/intradia-t024` porque `verificar_identidad()` exige el ejecutor de
`T024_CODE_SHA = 1a697c3fa2ab76ddfcf567c2ef3f5ab56492eaf0`; el release de producción no coincide y no
se toca para esta tarea.

Ejemplo de preparación en la Pi:

```bash
git -C /home/fer/intradia-bot worktree add --detach /home/fer/intradia-t024 1a697c3fa2ab76ddfcf567c2ef3f5ab56492eaf0
```

El intérprete puede ser el venv del bot:

```bash
/home/fer/intradia-bot/.venv/bin/python -m advisor.research.t024_forward peticion --checkpoint 2026-11-03 --festivo 2026-11-02
```

## Configuración

`/etc/intradia-bot/t024.env` no contiene secretos:

```bash
T024_USER=fer
T024_REPO_DIR=/home/fer/intradia-t024
T024_PYTHON=/home/fer/intradia-bot/.venv/bin/python
T024_DATA_DIR=/home/fer/intradia-bot/data/vintages
T024_ARTEFACTOS_DIR=/home/fer/t024-forward
T024_LOG=/home/fer/t024-forward/logs/systemd.log
```

Instalación, no ejecutada por este cambio:

```bash
sudo install -d -m 0755 /etc/intradia-bot
sudo install -m 0644 t024.env /etc/intradia-bot/t024.env
sudo /home/fer/intradia-t024/deploy/t024/instalar.sh
```

El instalador debe correr como root para escribir en systemd, pero las comprobaciones sobre el worktree
se ejecutan como `T024_USER`: limpieza de git, import de `advisor` desde `T024_REPO_DIR/advisor`,
`verificar_identidad()` y render de plantillas con `PYTHONDONTWRITEBYTECODE=1`.

## Operación

Estado local:

```bash
python deploy/t024/checkpoint.py estado --artefactos /home/fer/t024-forward
systemctl status intradia-t024-checkpoint.timer intradia-t024-checkpoint.service
journalctl -u intradia-t024-checkpoint.service
```

Códigos de salida:

| Código | Significado |
|---:|---|
| 0 | Nada que hacer, o checkpoint ya cerrado con `APTA`/`NO_APTA`, o cierre `APTA` |
| 2 | `NO_APTA`; systemd lo ve como fallo de unidad |
| 3 | Falta declarar el checkpoint del mes siguiente durante los últimos 10 días del mes |
| 4 | Se detectó un checkpoint pasado sin artefactos y se marcó `PERDIDO` |
| 5 | Hay `intento.json` sin `estado.json`; queda `INTERRUMPIDO` |
| 6 | Error de preflight o identidad |
| 7 | La petición no coincide con el calendario versionado |
| 8 | Calendario inválido |
| 9 | Error inesperado de congelación |
| 75 | Lock ocupado |

## Calendario

El calendario es operativo y versionado, separado del ejecutor. Para ampliarlo, usa solo una fuente
oficial de festivos laborales de Canarias, cita la fuente en cada entrada y no inventes fechas. Debe
actualizarse antes del día 20 del mes previo; si no, el wrapper avisará en los últimos 10 días naturales
del mes.

## Fase B en el PC

```bash
python deploy/t024/traer_cosecha.py copiar \
  --checkpoint 2026-11-03 \
  --destino-artefactos evidence/T-024-forward/2026-11-03/pi \
  --data-dir data/vintages \
  --pi-artefactos /home/fer/t024-forward \
  --pi-data-dir /home/fer/intradia-bot/data/vintages
```

`copiar` usa `rsync -a` sin `--delete`, exige estado `APTA`, verifica `SHA256SUMS`, manifiesto, petición,
contexto y sidecar de identidad, y solo instala el vintage local si no existe. Si ya existe, exige igualdad
byte a byte. El staging se crea junto a `--data-dir` para que el movimiento final sea atómico dentro del
mismo sistema de ficheros.
