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

# 0. Copia manual antes de tocar nada. La automática solo la hace una migración.
cp intradia.db "intradia.db.bak-manual-$(date -u +%Y%m%d-%H%M%S)"

# 1. Traer el tag y ponerse en él
git fetch --tags
git checkout vX.Y.Z

# 2. Dependencias, por si el tag las cambió
.venv/bin/pip install -r requirements.txt

# 3. Unidades systemd, solo si cambiaron las plantillas
sudo bash deploy/install-systemd.sh
sudo systemctl daemon-reload

# 4. Las tres verificaciones
.venv/bin/python -m advisor.main verificar-systemd
.venv/bin/python -m advisor.main verificar-release
.venv/bin/python -m advisor.main verificar-backup --ruta <la copia del paso 0>

# 5. Una pasada real, supervisada, que es donde se aplica la migración si la hay
.venv/bin/python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar
.venv/bin/python -m advisor.main analizar --horizonte swing   # esta sí persiste

# 6. Timers vivos
systemctl list-timers 'intradia-bot*'
```

Comprobar a mano que el SHA que imprime `verificar-release` es el mismo que
`git rev-list -n 1 vX.Y.Z`, carácter a carácter, y el mismo que el `git_sha`
del manifiesto de la pasada (`manifiesto --run-id <el del pie del informe>`).

**Una migración de esquema se aplica en la primera apertura de la base**, no al
hacer `checkout`. Por eso el paso 5 se hace supervisado y no de madrugada: la
base hace su backup automático `intradia.db.bak-<fecha>-pre-vN` justo antes.

## Volver atrás

```bash
cd ~/intradia-bot
git fetch --tags
git checkout vX.Y.(Z-1)
.venv/bin/pip install -r requirements.txt
sudo bash deploy/install-systemd.sh && sudo systemctl daemon-reload
.venv/bin/python -m advisor.main verificar-systemd
.venv/bin/python -m advisor.main verificar-release
.venv/bin/python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar
```

### Qué pasa con el esquema de la base

**Regla: el rollback de código no deshace migraciones** (D-32). Una migración
v3→v4 no se revierte sola, y el tag anterior no sabe leer el esquema nuevo.

1. Si el tag anterior **entiende el esquema actual** (no hubo migración entre
   los dos tags), no hay nada que hacer: la base se queda como está.
2. Si entre los dos tags **hubo migración**, hay que restaurar el backup previo
   a esa migración:

```bash
sudo systemctl stop intradia-bot.timer intradia-bot-event.timer
ls -la intradia.db.bak-*-pre-v*          # elegir el pre-vN de la migración que se deshace
.venv/bin/python -m advisor.main verificar-backup --ruta intradia.db.bak-<fecha>-pre-vN
cp intradia.db "intradia.db.rollback-$(date -u +%Y%m%d-%H%M%S)"   # la de ahora, por si acaso
cp intradia.db.bak-<fecha>-pre-vN intradia.db
.venv/bin/python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar
sudo systemctl start intradia-bot.timer intradia-bot-event.timer
```

**Lo que se pierde al restaurar son las pasadas guardadas desde la migración.**
Es una pérdida real y se declara: por eso el paso 0 del despliegue copia la base
viva, para poder consultarla después aunque no se use como base de trabajo.

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
