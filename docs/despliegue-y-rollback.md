# Despliegue por tag y vuelta atrás

Qué corre la Pi, cómo se cambia y cómo se deshace. Escrito para ejecutarlo de
madrugada sin pensar: los comandos son literales.

Complementa a `deploy/systemd/README.md` (qué unidades hay) y a
`docs/metodo-trabajo.md` (cómo se acepta una entrega antes de llegar aquí).

---

## Por qué existe

Hasta el 2026-09-18 el despliegue era `git pull` en la Pi y comprobar a ojo.
Eso ya costó dos cosas medidas: entre el 2026-09-02 y el 2026-09-16 la Pi corrió
**dos entregas por detrás** de `main` sin que ningún comando lo dijera, y la
migración de esquema v2→v3 de producción se hizo sin procedimiento de vuelta
atrás escrito.

Desde T-011 la Pi ejecuta **un tag concreto y verificable**, y volver al
anterior es un procedimiento probado.

## Las tres verificaciones

Se ejecutan **en la Pi**, en este orden, y ninguna sustituye a las otras:

| Comando | Qué responde |
|---|---|
| `verificar-systemd` | ¿las unidades instaladas son las del repo? |
| `verificar-release` | ¿el código en ejecución es el tag que dije? |
| `verificar-backup` | ¿la copia a la que podría volver es restaurable? |

`verificar-release` publica cada punto por separado —SHA de `HEAD`, tag exacto,
árbol limpio, tag en `origin`— y un veredicto:

- **`EN_TAG`**: `HEAD` es el tag, el árbol está limpio y `origin` publica el
  mismo SHA. Es el único caso con código de salida 0.
- **`FUERA_DE_TAG`**: se sabe que no coincide, y dice por qué (commits por
  delante, ficheros modificados, el tag no está en `origin`).
- **`DESCONOCIDO`**: no se ha podido determinar (sin red para preguntar a
  `origin`, sin `git`). No se asume que coincide (INV-16).

## Desplegar un tag

```bash
ssh -i ~/.ssh/id_ed25519_rpi_bot fer@192.168.1.113
cd ~/intradia-bot

# 0. Parar los timers para que ninguna pasada programada coincida con el
#    checkout o la migración, y comprobar que no hay una en curso.
sudo systemctl stop intradia-bot.timer intradia-bot-event.timer
systemctl is-active intradia-bot.service intradia-bot-event.service   # ambos inactive

# 1. Copia manual antes de tocar nada, verificada con el código todavía vigente.
#    La automática solo la hace una migración.
BACKUP="intradia.db.bak-manual-$(date -u +%Y%m%d-%H%M%S)"
cp intradia.db "$BACKUP"
.venv/bin/python -m advisor.main verificar-backup --ruta "$BACKUP"

# 2. Traer el tag y ponerse en él (nunca `git pull`)
git fetch --tags
git checkout vX.Y.Z

# 3. Dependencias y unidades, solo si el tag las cambió
git diff --stat vX.Y.(Z-1) vX.Y.Z -- requirements.txt deploy/
.venv/bin/pip install -r requirements.txt                              # si cambió requirements.txt
sudo bash deploy/install-systemd.sh && sudo systemctl daemon-reload    # si cambió deploy/

# 4. Las tres verificaciones
.venv/bin/python -m advisor.main verificar-systemd
.venv/bin/python -m advisor.main verificar-release
.venv/bin/python -m advisor.main verificar-backup --ruta "$BACKUP"
```

Comprobar a mano que el SHA que imprime `verificar-release` es el mismo que
`git rev-list -n 1 vX.Y.Z`, carácter a carácter, y el mismo que el `git_sha`
del manifiesto de la primera pasada (`manifiesto --run-id <el del pie del
informe>`).

Después vienen **tres pasos distintos, que no se sustituyen entre sí**.

### A. Prueba seca, pre-migración

```bash
.venv/bin/python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar
```

Comprueba que el código del tag analiza correctamente. **No prueba la base ni
aplica migraciones**: con `--sin-guardar`, `cmd_analizar` no crea `AdvisorDB`
(`advisor/main.py`, `db = None if args.sin_guardar else AdvisorDB(...)`), así
que no abre la base, no migra, no hace el backup `pre-vN` y, desde T-018,
tampoco usa la caché persistente de barras. Hasta el 2026-09-26 este documento
decía que la migración se aplicaba aquí; el despliegue de `v0.4.0` demostró que
no (`evidence/2026-09-26-despliegue-v040/`).

### B. Migración aislada (solo si el tag cambia el esquema)

Una migración se aplica en la **primera apertura de la base en escritura**, no
al hacer `checkout`. Se aplica primero **sola**, sin analizar ni persistir
recomendaciones:

```bash
.venv/bin/python -c \
'from advisor.config import load_config; from advisor.storage.db import AdvisorDB; AdvisorDB(load_config().db_path)'
```

Y después, **obligatoriamente**, antes de cualquier pasada persistente:

```bash
# esquema nuevo
.venv/bin/python -c 'import sqlite3; c=sqlite3.connect("intradia.db"); print(c.execute("PRAGMA user_version").fetchone()[0]); c.close()'
# backup automático previo, que la migración crea justo antes de aplicarse
PREVN="$(ls -1t intradia.db.bak-*-pre-vN | head -1)"
.venv/bin/python -m advisor.main verificar-backup --ruta "$PREVN"      # esquema anterior, VALIDO
# integridad
.venv/bin/python -c 'import sqlite3; c=sqlite3.connect("intradia.db"); print(c.execute("PRAGMA integrity_check").fetchone()[0]); c.close()'
```

y comprobar en SQLite las **estructuras que crea esa migración** (tablas y
columnas; la ficha de la tarea las enumera). Si algo falla aquí, **no** se hace
la pasada persistente: se sigue «Volver atrás».

Por qué se migra aislado y no dentro de la primera pasada:

- **separa** un fallo de migración de un fallo de análisis o de persistencia;
- permite **validar el backup previo y el esquema nuevo antes** de guardar la
  primera pasada sobre él;
- hace el rollback **determinista**: si la migración falla o no convence, la base
  aún no contiene ninguna pasada nueva y restaurar el `pre-vN` no pierde nada.

### C. Pasada real

```bash
.venv/bin/python -m advisor.main analizar --horizonte swing
.venv/bin/python -m advisor.main manifiesto --run-id <el del pie del informe>
```

Ya usa la base migrada y persiste resultados. Comprobar en el manifiesto
`release_tag`, `git_sha`, `git_dirty` y `schema_version`.

### D. Reactivar los timers

```bash
sudo systemctl start intradia-bot.timer intradia-bot-event.timer
systemctl list-timers 'intradia-bot*'
.venv/bin/python -m advisor.main verificar-systemd
.venv/bin/python -m advisor.main verificar-release
```

## Volver atrás

### Sin migración entre los dos tags

```bash
cd ~/intradia-bot
sudo systemctl stop intradia-bot.timer intradia-bot-event.timer
git fetch --tags
git checkout vX.Y.(Z-1)
.venv/bin/pip install -r requirements.txt
sudo bash deploy/install-systemd.sh && sudo systemctl daemon-reload
.venv/bin/python -m advisor.main verificar-systemd
.venv/bin/python -m advisor.main verificar-release
.venv/bin/python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar
sudo systemctl start intradia-bot.timer intradia-bot-event.timer
```

### Con migración entre los dos tags

**Regla: el rollback de código no deshace migraciones** (D-32). Un checkout del
tag anterior **no** revierte la base, y el tag anterior no sabe leer el esquema
nuevo. Hay que restaurar un backup del esquema anterior, verificado. Ejemplo
literal para volver de `v0.4.0` (esquema v6) a `v0.3.0` (esquema v5):

```bash
cd ~/intradia-bot
# 1. parar los timers
sudo systemctl stop intradia-bot.timer intradia-bot-event.timer
# 2. conservar la base v6 tal como está, por si hay que consultarla después
cp intradia.db "intradia.db.rollback-v6-$(date -u +%Y%m%d-%H%M%S)"
# 3. volver al código anterior
git checkout v0.3.0
# 4. restaurar un backup v5 verificado; preferentemente el automático pre-v6
PREV6="$(ls -1t intradia.db.bak-*-pre-v6 | head -1)"
.venv/bin/python -m advisor.main verificar-backup --ruta "$PREV6"      # esquema v5, VALIDO
cp "$PREV6" intradia.db
# 5. comprobar el esquema
.venv/bin/python -c 'import sqlite3; c=sqlite3.connect("intradia.db"); print(c.execute("PRAGMA user_version").fetchone()[0]); c.close()'   # 5
.venv/bin/python -m advisor.main verificar-release                      # v0.3.0, EN_TAG
# 6. pasada seca
.venv/bin/python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar
# 7. reactivar los timers
sudo systemctl start intradia-bot.timer intradia-bot-event.timer
```

**Lo que se pierde al restaurar son las pasadas guardadas desde la migración.**
Es una pérdida real y se declara: por eso el paso 1 del despliegue copia la base
viva y el paso 2 del rollback conserva la migrada, para poder consultarlas
después aunque no se usen como base de trabajo. Con la migración aislada (paso
B), si el rollback se decide antes de la primera pasada real, no se pierde nada.

### Cómo leer `verificar-backup`

Desde T-011 el comando distingue tres cosas que antes se confundían:

- **integridad y esquema**: si el fichero es una base SQLite restaurable;
- **registro**: `registrado en backup_log` (lo hizo una migración) o
  `no registrado (copia manual)`;
- **veredicto**: `VALIDO` / `INVALIDO`.

Una copia hecha con `cp` **nunca** figura en `backup_log` y es perfectamente
restaurable. El 2026-09-18, en pleno despliegue, el comando antiguo la llamó
«Backup inválido» porque solo validaba contra el registro: en un rollback de
madrugada ese mensaje lleva a descartar la copia buena. `INVALIDO` queda ahora
reservado a lo que de verdad no se puede restaurar.

## Cuando algo no cuadra

| Síntoma | Qué significa | Qué hacer |
|---|---|---|
| `verificar-release` dice `FUERA_DE_TAG` con commits por delante | alguien hizo `git pull` en vez de `checkout` de un tag | `git checkout vX.Y.Z` y repetir |
| `FUERA_DE_TAG` por árbol modificado | hay ediciones sin commitear en la Pi | `git status`, decidir si son basura o trabajo; **no** borrarlas sin mirarlas |
| `FUERA_DE_TAG` porque el tag no está en `origin` | el tag es local, no se empujó | empujarlo desde el portátil y repetir |
| `DESCONOCIDO` por `ls-remote` | no hay red | reintentar con red; si no la hay, se despliega igual pero **se anota** que el punto de `origin` quedó sin comprobar |
| `verificar-systemd` señala desfase | las unidades instaladas no son las del repo | `sudo bash deploy/install-systemd.sh && sudo systemctl daemon-reload` |
| Tras la pasada `--sin-guardar` el esquema sigue en la versión anterior y no hay backup `pre-vN` | es lo esperado: esa pasada no abre la base | aplicar la migración aislada (paso B) y verificarla antes de la pasada real |
