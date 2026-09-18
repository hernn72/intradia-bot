# T-017 — Higiene del manifiesto y del esquema (cuatro hallazgos, una migración)

Estado: EN_REVISION (2026-09-18) — implementada junto con T-011, una sola migración v4→v5
Agente: Opus (implementación) → Codex (revisión independiente)
Línea / fase: Línea C, C-02 (manifiesto) y C-01 (migraciones)
Gate al que contribuye: GATE PROD (requisito 4: reconstrucción probada a ≥ 30 días)

## Objetivo
Cerrar cuatro hallazgos que llevan abiertos desde la revisión de T-002 y que
comparten dos cosas: todos tocan el manifiesto o el esquema, y **todos exigen
una migración**. Se hacen juntos para migrar una vez.

## Por qué existe
Cada uno por separado parecía pequeño y por eso siguen abiertos. Juntos, dejan
la reconstrucción de una recomendación —lo que GATE PROD exige— sin garantía:

1. **`git_dirty` miente por omisión.** `advisor/run/manifest.py` devuelve
   `False` si `git status` falla o expira. Un manifiesto puede decir «árbol
   limpio» cuando en realidad no pudo comprobarlo. INV-16: lo desconocido se
   declara desconocido, y eso es un `NULL`, que exige migración.
2. **`config_hash` no identifica la configuración lógica.** Incluye `db_path`
   y `universe_path`, así que la misma configuración en el portátil y en la Pi
   da hashes distintos, y la reconstrucción de D-10 no puede decir «misma
   config» comparándolos.
3. **`backup_log` es esquema no versionado.** Se crea fuera de la lista de
   migraciones (`_ensure_backup_log`). Inocuo hoy; contradice INV-17.
4. **`analizar --grupos X` declara el vintage del universo entero**, no el del
   subconjunto analizado. Una pasada sobre `europa` lleva el mismo
   `universe_vintage_id` que una sobre los 107, y son poblaciones distintas.

## Dependencias previas
Ninguna. Conviene hacerla **junto con T-011**, que también añade una columna
al manifiesto (`release_tag`): una sola migración v4→v5 para todo. Si T-011 va
antes, esta ficha se apoya en su migración; si va después, al revés. Lo que no
puede pasar es que haya dos migraciones consecutivas por dos fichas que tocan
la misma tabla.

## Archivos probables
No asumir que sean exactos: verificar primero con búsqueda de símbolos.
- `advisor/run/manifest.py` — `git_dirty`, `config_hash`.
- `advisor/storage/migrations.py` — `MIGRATIONS`; `advisor/storage/db.py` —
  `_ensure_backup_log`, `_init_schema` (que es el punto de entrada real de las
  migraciones; `apply_migrations` se borró en T-010 por huérfana y sin backup).
- `advisor/research/vintage.py` o donde viva `universe_vintage_id`.
- `advisor/main.py` — `cmd_analizar` y `--grupos`.

## Invariantes que no pueden romperse
INV-16 (desconocido ≠ `False`), INV-17 (toda columna nueva, por migración con
backup previo), INV-19 (cualquier cambio en la lista analizada → vintage
distinto), INV-06.

## Implementación requerida

1. **`git_dirty` nullable.** `True`, `False` o `NULL` cuando no se pudo
   comprobar, con el motivo en un campo o log. Migración de la columna.
2. **`config_hash` sin rutas.** Excluir `db_path` y `universe_path` del hash y
   documentarlo en D-10. **Decisión que hay que registrar**: los manifiestos
   anteriores llevan el hash viejo; no se recalculan. Se añade
   `config_hash_version` (o equivalente) para que la reconstrucción sepa con
   qué regla se calculó cada uno.
3. **`backup_log` en la lista de migraciones.** Dejar de crearla aparte. Para
   bases que ya la tienen, la migración es idempotente (`CREATE TABLE IF NOT
   EXISTS`) y lo dice.
4. **Vintage del subconjunto.** `analizar --grupos X` calcula y declara el
   `universe_vintage_id` de los activos que analiza, y el manifiesto guarda
   además qué grupos se pidieron. Una pasada sin `--grupos` sigue dando el
   vintage de los 107, sin cambio.

## Qué NO debe modificarse
Cómo se calcula el vintage de la lista completa (D-23), la lógica de análisis,
nada del informe.

## Tests unitarios
- `test_git_dirty_es_null_cuando_git_status_falla` (INV-16).
- `test_config_hash_no_cambia_con_las_rutas`: misma config con `db_path`
  distinto → mismo hash.
- `test_manifiestos_antiguos_conservan_su_hash_y_su_version`.
- `test_backup_log_la_crea_la_migracion_y_es_idempotente`.
- `test_grupos_declara_el_vintage_del_subconjunto`: `--grupos europa` ≠
  vintage de los 107, y dos pasadas sobre el mismo grupo → mismo vintage.
- `test_la_migracion_hace_backup_previo`, como en las anteriores.

## Verificación contra datos reales
```bash
.venv/bin/python -m advisor.main analizar --horizonte swing --sin-ia --grupos europa
.venv/bin/python -m advisor.main manifiesto --ultima
.venv/bin/python -m advisor.main verificar-backup <backup pre-migración>
```
Comprobar a mano: que el `config_hash` del portátil coincide con el que
produce la Pi para la misma configuración lógica (es la prueba de la ficha), y
que el vintage del grupo `europa` es distinto del de los 107.

## Medición del impacto
- Ninguno sobre recomendaciones. Confirmarlo con una pasada antes y después.
- Manifiestos afectados en la Pi por la migración: contarlos y declarar que
  conservan sus valores antiguos con su versión.

## Criterio de aceptación
- Los cuatro hallazgos cerrados con test.
- Una sola migración, con backup previo verificado.
- Portátil y Pi dan el mismo `config_hash` para la misma configuración.

## Criterio de rechazo
- Recalcular hashes de manifiestos antiguos.
- Dos migraciones donde cabía una.
- Cualquier cambio de recomendación.

## Evidencia que debe quedar registrada
`evidence/<fecha>-T-017-manifiesto/` con README.md, el backup pre-migración
verificado, la comparación de `config_hash` portátil/Pi, y los dos vintages
(grupo y completo).

## Commit esperado
Rama `fix/manifest-schema-hygiene`. Mensaje:
`fix(manifest): git_dirty nullable, config_hash sin rutas, backup_log migrado y vintage por grupo`

## Actualización documental requerida
`docs/roadmap.md`: fila nueva en la línea C; retirar los cuatro hallazgos de
la sección de abiertos. `docs/decision-log.md`: D-nn con la regla del hash y su
versión. `docs/tareas/T-002-…md`: nota de que estos FOLLOW_UP se cierran aquí.

## Qué se implementó, hallazgo por hallazgo

1. **`git_dirty` nullable.** Los primitivos de git se mudan a
   `advisor/run/git.py`, donde `run_git` distingue «el comando falló» de «la
   salida está vacía» —que es justo lo que se confundía—. `git_dirty` devuelve
   `GitDirty(value, reason)`: `True`, `False` o `None` con el motivo. La columna
   `git_dirty` pasa a aceptar `NULL` y se añade `git_dirty_reason`. El pie del
   informe dice `+dirty?` cuando no se pudo comprobar, en vez de callar.
2. **`config_hash` sin rutas, y versionado.** `db_path` y `universe_path` salen
   del hash. Los manifiestos anteriores **no** se recalculan: la migración los
   marca con `config_hash_version = 1` y los nuevos nacen con `2` (D-33).
3. **`backup_log` en la lista de migraciones.** La DDL vive en
   `advisor/storage/migrations.py` (`BACKUP_LOG_STATEMENTS`), la aplica el
   esquema base para bases nuevas y la migración v5 para las que ya existían,
   idempotente. `_ensure_backup_log` desaparece: ya no se crea esquema en cada
   apertura.
4. **Vintage del subconjunto.** `universe_vintage_id(universe, groups)` y
   `build_run_manifest(..., groups=...)`. `analizar --grupos europa` declara el
   vintage de esos activos y guarda los grupos pedidos en el manifiesto. Sin
   `--grupos` el identificador es idéntico al publicado (D-23), comprobado
   contra la constante real `c8496446…`.

## Invariantes ejercitadas

- **INV-16**: `test_git_dirty_es_null_cuando_git_status_falla`, verificada
  inyectando el defecto (`evidence/.../inyeccion-de-defectos.txt`, bloque D).
- **INV-17**: migración v5 con backup previo, probada sobre una copia de la base
  real (`evidence/.../migracion-v4-a-v5.txt`) y sobre una copia con manifiestos
  de la forma que tiene la Pi (`migracion-con-manifiestos.txt`).
- **INV-19**: `test_grupos_declara_el_vintage_del_subconjunto` —`europa` da un
  identificador distinto del de los 103, y dos pasadas sobre el mismo grupo dan
  el mismo—, con la guarda de D-23 en `test_el_vintage_sin_grupos_no_cambia`.
- **INV-06**: una sola implementación de los primitivos de git, compartida por
  el manifiesto y `verificar-release`.

## Medición del impacto

- **Recomendaciones: ninguna.** El diff no toca `advisor/analysis` ni
  `advisor/report`. Confirmado con una pasada real sobre los 103 analizables.
- **Manifiestos afectados por la migración:** en el portátil, 0 (aquí siempre se
  corre con `--sin-guardar`). En la Pi hay que contarlos al desplegar; la
  migración se probó con filas sintéticas de la forma v4 y las conservó todas
  con su `config_hash` y `config_hash_version = 1`.
- **Vintage:** sin `--grupos`, `c8496446…`, el mismo de D-31. Con
  `--grupos europa`, 28 analizables y un identificador propio.

## Desviación respecto a la ficha

La ficha propone verificar con `manifiesto --ultima`; ese flag **no existe**
—`manifiesto` exige `--run-id`— y añadirlo queda fuera del alcance. Se verifica
con el `run` que imprime el pie del informe. Queda como FOLLOW_UP menor.

## Handoff al siguiente agente

La ficha está completa salvo por lo que solo se puede medir en producción: el
recuento de manifiestos migrados en la Pi y la prueba de que el `config_hash`
del portátil y el de la Pi coinciden para la misma configuración lógica. Las dos
cosas se hacen en el mismo ensayo de OA-04 que cierra T-011, y por eso las dos
fichas se aceptan juntas.

**FOLLOW_UP que deja a la vista esta ficha, y que NO se toca aquí.**
`congelar-datos --grupos X` (o `--symbols`) tiene el mismo defecto que se acaba
de corregir en `analizar`: el manifiesto de la cosecha declara el
`universe_vintage_id` del universo entero (`advisor/main.py:293`), congele lo que
congele. No se corrige junto con esto porque `replay_managed_population`
compara ese campo contra el vintage calculado sobre el universo completo
(`advisor/research/event_study.py:347`): cambiarlo invalidaría la comprobación
de INV-08 para las cosechas ya congeladas, incluida `071ddb2b…`. Es una decisión
—recongelar o versionar la regla—, no un arreglo, y necesita ficha propia.

Para esa comprobación: ejecutar en ambas máquinas
`.venv/bin/python -c "from advisor.config import load_config;
from advisor.run.manifest import config_hash; print(config_hash(load_config('config.yaml')))"`
y comparar. Antes de esta ficha daban distinto **por construcción**, así que es
la prueba de que el cambio hizo lo que decía.
