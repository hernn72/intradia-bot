# T-017 — Higiene del manifiesto y del esquema (cuatro hallazgos, una migración)

Estado: PENDIENTE
Agente: Codex (implementación) → Opus (revisión)
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

## Handoff al siguiente agente
Pendiente de escribir al terminar.
