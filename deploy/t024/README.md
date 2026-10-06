# T-024 forward en Raspberry Pi

La Pi es el host 24/7 de la fase A: un timer diario llama al wrapper y el wrapper solo actúa si la fecha
actual en `Atlantic/Canary` es un checkpoint declarado en `calendario-checkpoints.json`. Ese intento
verifica identidad, construye la petición exacta, congela una vez, guarda artefactos y hashes, y termina.

La fase B ocurre en el PC: copiar y verificar la cosecha, versionar evidencia y ejecutar después el
registro y los conteos del runbook de investigación.

## Worktree dedicado

Producción sigue en `/home/fer/intradia-bot` con el tag operativo. La captura forward usa un worktree
separado en `/home/fer/intradia-t024`. Ese worktree no puede crearse directamente en
`T024_CODE_SHA = 1a697c3fa2ab76ddfcf567c2ef3f5ab56492eaf0`, porque ese commit no contiene `deploy/t024`;
debe apuntar al commit de `main` posterior a fusionar el PR #46, o a un descendiente.

Ejemplo de preparación en la Pi:

```bash
git -C /home/fer/intradia-bot fetch origin
git -C /home/fer/intradia-bot worktree add --detach /home/fer/intradia-t024 <SHA de main tras fusionar #46>
git -C /home/fer/intradia-t024 diff --quiet 1a697c3fa2ab76ddfcf567c2ef3f5ab56492eaf0 HEAD -- advisor config.yaml universe.yaml exchange_overrides.yaml pyproject.toml requirements.txt
test -f /home/fer/intradia-t024/deploy/t024/checkpoint.py
```

La comprobación de `diff --quiet` debe salir 0: permite añadir el despliegue T-024 sin cambiar el código
metodológico congelado. Después, `verificar_identidad()` debe devolver exactamente
`1a697c3fa2ab76ddfcf567c2ef3f5ab56492eaf0`.

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
se ejecutan como `T024_USER`: limpieza de git, existencia de `deploy/t024/checkpoint.py`, diff nulo contra
`T024_CODE_SHA` en las rutas protegidas, import de `advisor` desde `T024_REPO_DIR/advisor`,
`verificar_identidad()` exacto y render de plantillas con `PYTHONDONTWRITEBYTECODE=1`.

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

## Segunda copia y borrado seguro

- Cada cosecha que congela el wrapper, apta o no, se copia a `--copia-dir`, por defecto
  `<artefactos>/copias/vintages/`. Esa ruta queda fuera del checkout del bot y del `--data-dir`.
- La copia pasa por un staging, se verifica por SHA256 fichero a fichero y solo entonces se promueve sin
  pisar nada. La ruta se comprueba ya resuelta (enlaces incluidos) antes y después de crearla. No acepta
  enlaces simbólicos, y la copia tiene que tener inodos propios: un enlace duro al original no cuenta.
- Una copia previa distinta no se toca: el estado pasa a `ERROR_COPIA` (salida 10).
- Ningún script de `deploy/t024/` borra directamente: solo
  `borrado_seguro.borrar_staging(ruta, base=...)`. Esa función solo acepta directorios
  `.t024-staging-*`, hijos directos de `base`, sin `.git` ni SQLite. Rechaza `/`, `$HOME`, la raíz del
  repositorio, el directorio actual y sus antecesores.

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
contexto y sidecar de identidad en staging, y solo promueve artefactos y vintage cuando todo cuadra. Si el
destino ya existe, exige igualdad byte a byte del árbol completo y no lo toca.

La promoción no pisa nada (`borrado_seguro.promover_sin_pisar`):
- el destino se crea con `mkdir` exclusivo;
- cada fichero se enlaza con `os.link`, que falla si el nombre existe.

Los staging viven junto a los destinos finales, en el mismo sistema de ficheros, y solo se borran por la
guarda (renombrado a una lápida `.t024-staging-borrando-*` y `rmtree` resistente a enlaces). Si algo
falla, el destino final queda intacto.
