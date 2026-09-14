# T-002 — Migraciones SQLite y manifiesto de ejecución

Estado: EN_REVISION
Agente: Codex (implementa) → Opus (revisa persistencia y reconstrucción)
Línea / fase: C-01 y C-02 (línea C)
Gate al que contribuye: GATE L0 (requisito 6), GATE PROD (requisitos 3 y 4)

## Objetivo
Toda pasada que persiste algo queda identificada por un `run_id` con
manifiesto reconstruible, y todo cambio de esquema pasa por una migración con
backup previo y prueba de restauración.

## Por qué existe
`advisor/storage/db.py` crea tablas con `CREATE TABLE IF NOT EXISTS` y no
tiene versión de esquema (verificado 2026-09-14). `recommendation` no guarda
SHA, config, universo ni versión de modelo. PR 2, 3 y 4 van a añadir columnas;
sin esto, se añadirían a mano y sin poder volver atrás. Decisiones D-09, D-10,
D-13, D-19.

## Dependencias previas
T-001 (CI) aceptada, para que la migración llegue a `main` con checks.

## Archivos probables
No asumir que sean exactos: verificar primero.
- `advisor/storage/db.py` (`_SCHEMA`, `_init_schema`, `insert_*`)
- `advisor/storage/migrations.py` (nuevo)
- `advisor/run/manifest.py` (nuevo) o `advisor/storage/manifest.py`
- `advisor/main.py` (`cmd_analizar`, `cmd_pasada_evento`, `_persist`,
  `opportunity_to_row`, `freshness_row_to_measurement`; nuevos subcomandos)
- `advisor/config.py` (hash canónico de la config cargada)
- `advisor/universe/loader.py` (hash canónico del universo; si T-006 no ha
  llegado, calcular sobre la lista de analizables ordenada por símbolo)
- `tests/test_db.py`, `tests/test_migrations.py` (nuevo), `tests/test_manifest.py` (nuevo)
- `deploy/` (backup pre-migración en el arranque de la pasada)

## Invariantes que no pueden romperse
INV-03 (nada de esto toca el score), INV-10 (la narrativa no entra en
columnas numéricas), INV-17, INV-18. Los tests existentes de `tests/test_db.py`
deben seguir pasando sin modificar sus aserciones de datos.

## Implementación requerida

### Migraciones
1. `advisor/storage/migrations.py`: lista ordenada `MIGRATIONS: list[tuple[int, str, Callable]]`
   (versión, descripción, función que recibe la conexión). Versión actual del
   esquema existente = 1 (marcar bases ya creadas: si `user_version == 0` y
   existe `recommendation`, fijar 1 sin tocar nada).
2. `AdvisorDB._init_schema` → aplica el esquema base solo en base nueva y
   luego `apply_migrations(conn)` hasta la última versión.
3. Antes de aplicar cualquier migración con versión > actual sobre un fichero
   existente: copia `intradia.db.bak-<YYYYmmdd-HHMMSS>-pre-v<n>` en el mismo
   directorio, con `sqlite3.Connection.backup()` (no `shutil.copy` sobre una
   base abierta).
4. Subcomando `verificar-backup --ruta <bak>`: abre la copia en modo
   `?mode=ro`, ejecuta `PRAGMA integrity_check`, compara conteos por tabla con
   la base viva y devuelve 0 solo si la copia es íntegra y no tiene menos
   filas que las que tenía la base en el momento del backup (guardar los
   conteos en una tabla `backup_log`).
5. Migración v2 (esta tarea): tabla `analysis_run`, columna `run_id TEXT` en
   `recommendation` y en `data_freshness_measurement` (nullable para filas
   antiguas), índice por `run_id`.

### Manifiesto
6. `RunManifest` (dataclass frozen) con: `run_id` (uuid4), `command`
   (`analizar`, `pasada-evento`, `event-study`, `backtest`, …), `git_sha`,
   `git_dirty` (bool), `config_hash` (SHA-256 del YAML canónico cargado, no del
   fichero), `universe_vintage_id`, `data_vintage_id` (null en vivo),
   `score_model_version` (constante `SCORE_MODEL_VERSION = "1.0"` en
   `advisor/analysis/scoring.py`), `context_model_version` (null hasta línea
   B), `schema_version` (user_version), `analysis_timestamp` (UTC ISO),
   `environment` (`INTRADIA_ENV` o hostname: `laptop`/`pi`/`ci`),
   `python_version`, `provider_versions` (`yfinance.__version__`,
   `pandas.__version__`), `clock_drift_seconds` (null si no se pudo medir).
7. Medición del reloj (D-13): intentar en orden `timedatectl show -p
   NTPSynchronized,TimeUSec`, `chronyc tracking`, y una consulta NTP con
   `socket` y timeout 2 s a `pool.ntp.org`; guardar el primer resultado
   válido; nunca fallar la pasada por no poder medir. Si `|drift| > 60`,
   `clock_status = "CLOCK_SUSPECT"` y `logger.error`.
8. `cmd_analizar` y `cmd_pasada_evento` crean el manifiesto **antes** de
   descargar datos, lo persisten al final junto con las filas (misma
   transacción), y lo imprimen al pie del informe en una línea:
   `run <run_id> · <sha>[+dirty] · config <hash8> · universo <vintage8>`.
9. Subcomando `manifiesto --run-id <id>`: imprime el manifiesto y las
   recomendaciones de esa pasada.

## Qué NO debe modificarse
`compute_score`, `classify`, `compute_levels*`, `evaluate_trade_at_entry`, el
formato de las secciones existentes del informe salvo la línea nueva al pie,
`advisor/research/vintage.py` (ya tiene su propio `schema_version: 1`; no
unificar en esta tarea).

## Tests unitarios
- `test_migrations_base_nueva_llega_a_ultima_version`: base en memoria,
  `user_version == 2`, tablas presentes.
- `test_migrations_base_v1_existente_se_marca_y_migra`: crear con el esquema
  antiguo (copiar `_SCHEMA` de `e53e385` en el test), insertar 3
  recomendaciones, migrar, comprobar 3 filas con `run_id IS NULL`.
- `test_backup_antes_de_migrar`: fichero temporal, existe `*.bak-*-pre-v2`,
  `verificar-backup` devuelve 0 y conteos iguales.
- `test_backup_corrupto_falla`: truncar la copia, `verificar-backup` devuelve 1.
- `test_manifest_config_hash_es_canonico`: dos configs con claves en distinto
  orden → mismo hash; una clave cambiada → hash distinto.
- `test_manifest_git_dirty`: con un fichero modificado en un repo temporal →
  `git_dirty is True`.
- `test_clock_drift_no_bloquea`: sin red y sin `timedatectl` → `None`, la
  pasada continúa.

## Tests de integración
- `test_analizar_persiste_run_id_en_todas_las_filas`: `FakeProvider`, base
  temporal, `cmd_analizar` sin IA; todas las filas de `recommendation` y
  `data_freshness_measurement` tienen el mismo `run_id` y existe una fila en
  `analysis_run`.
- Con IA simulada (`enrich_with_narrative` parcheado): mismo resultado. Este es
  el camino que perdió `freshness_rows` en silencio el 2026-09-02; el test
  existe para que no vuelva.

## Verificación contra datos reales
```bash
cp intradia.db /tmp/intradia-antes.db
python -m advisor.main analizar --horizonte swing --sin-ia
ls intradia.db.bak-*-pre-v2
python -m advisor.main verificar-backup --ruta intradia.db.bak-<…>-pre-v2
sqlite3 intradia.db "PRAGMA user_version; SELECT count(*) FROM analysis_run; SELECT run_id, count(*) FROM recommendation GROUP BY run_id ORDER BY 2 DESC LIMIT 3;"
python -m advisor.main manifiesto --run-id <id>
```
Comprobar a mano: `git_sha` del manifiesto == `git rev-parse HEAD`;
`config_hash` cambia si se edita un comentario de `config.yaml`? **No debe
cambiar** (el hash es de la config cargada, no del texto). Verificar ambas.

## Medición del impacto
- nº activos afectados: 0 (la decisión no cambia)
- nº señales afectadas: 0
- cambio en resultados relevantes: `recommendation` gana `run_id`; el informe
  gana una línea.

## Criterio de aceptación
- Todos los tests de arriba en verde, CI en verde.
- En el portátil: la base real migra, la copia se restaura y verifica, la
  pasada real persiste `run_id` en 107 recomendaciones + 107 mediciones.
- Revisión de Opus: reconstrucción probada tomando un `run_id` y recuperando
  SHA + config hash + universe vintage.

## Criterio de rechazo
- Una migración sin backup, o un backup sin prueba de restauración.
- `run_id` nullable en filas nuevas.
- La pasada falla si no hay NTP.

## Evidencia que debe quedar registrada
`evidence/<fecha>-T-002-manifest/README.md` con la salida de los comandos de
verificación y el manifiesto de la pasada real (sin secretos).

## Commit esperado
Rama `feat/run-manifest-migrations`. Mensaje:
`feat(storage): migraciones versionadas con backup verificado y manifiesto de ejecución por pasada`.

## Actualización documental requerida
`docs/roadmap.md`: C-01 y C-02 → ACEPTADA. `README.md`: comandos nuevos
(`verificar-backup`, `manifiesto`). `docs/decision-log.md`: nada nuevo salvo
hallazgos.

## Handoff al siguiente agente
- Estado: ACEPTADA (2026-09-14) · Rama: `feat/run-manifest-migrations` · Commits: ver evidencia
- Revisión independiente (subagente `revisor`, veredicto CORREGIR) y correcciones aplicadas por Claude Code:
  1. Migración atómica: `run_migration` con `BEGIN IMMEDIATE`/`COMMIT`/`ROLLBACK`, sentencias una a una (antes `executescript` dejaba `run_id` puesto y `user_version` 1 tras un corte; reproducido). Test `test_migracion_que_falla_a_mitad_no_deja_esquema_a_medias`.
  2. `verificar-backup` y `manifiesto` abren la base en `mode=ro` (`AdvisorDB(readonly=True)`): ya no migran producción ni crean bases vacías. El revisor había migrado sin querer el `intradia.db` real del portátil con el comando antiguo (sin pérdida; backup `intradia.db.bak-20260914-091715-pre-v2`). Tests `test_verify_backup_no_escribe_en_la_base_viva`, `test_readonly_no_crea_ni_migra`.
  3. Rutas de backup resueltas al registrar y al comparar: ruta absoluta y relativa verifican igual. Test `test_verify_backup_acepta_ruta_relativa_y_absoluta`.
  4. Reloj: `timedatectl timesync-status` (`Offset: -572us` verificado en la Pi), `chronyc`, SNTP por **UDP** (antes TCP: nunca medía y costaba 6 s por pasada y por test). Medido tras el cambio: deriva −0,13 s en 0,07 s. Tests en `tests/test_manifest.py`; el test de integración parchea la medición para no salir a la red.
  5. Tests añadidos: `run_id` obligatorio (None, vacío, ausente) en las dos APIs; segunda apertura idempotente; conteos del backup iguales a `backup_log`; backup con menos filas falla.
- Verificación real repetida (`evidence/2026-09-14-T-002-manifest/despues-2.txt`): 107 recomendaciones + 107 mediciones con el mismo `run_id`, backup pre-v2 creado y verificado, `user_version` 2, `manifiesto --run-id` devuelve el SHA de HEAD. El BLOCKER del proveedor era transitorio.
- FOLLOW_UP registrados en `docs/roadmap.md` (hallazgos abiertos): `git_dirty` falso ante fallo de git; `config_hash` incluye rutas; `backup_log` fuera de migraciones.
- Decisiones: D-09 y D-13 precisadas en el decision log. Ninguna pendiente del propietario.
- Siguiente: desplegar en la Pi (migración de la base real con 2.503 recomendaciones y 1.177 mediciones) y verificar allí; después T-003 (calendarios) y T-006 (universe vintage) en paralelo.
- Trampas para el siguiente: Codex no puede escribir en `.git`; `verificar-backup` con el comando antiguo migraba la base; `timedatectl show -p TimeUSec` no es una referencia externa.

Registro original de Codex (antes de la revisión):
Codex implementó migraciones SQLite versionadas y manifiesto de ejecución.

Cambios principales:
- `advisor/storage/migrations.py`: `MIGRATIONS` v2 con `analysis_run`,
  `run_id` nullable en `recommendation` y `data_freshness_measurement`, e
  índices por `run_id`.
- `advisor/storage/db.py`: inicialización con `PRAGMA user_version`, marcado
  de bases v1 existentes, backup previo con `sqlite3.Connection.backup()`,
  `backup_log`, verificación de backup y persistencia transaccional de
  `analysis_run` + recomendaciones + frescura.
- `advisor/run/manifest.py`: `RunManifest` frozen, hash canónico de config,
  vintage provisional de universo por símbolos analizables, SHA/dirty,
  versiones de proveedor y medición tolerante de reloj.
- `advisor/main.py`: `analizar` y `pasada-evento` crean manifiesto antes de
  descargar datos, añaden la línea `run ...` al pie del informe, y nuevos
  subcomandos `verificar-backup` y `manifiesto`.
- `advisor/analysis/scoring.py`: `SCORE_MODEL_VERSION = "1.0"`.
- Tests nuevos: `tests/test_migrations.py`, `tests/test_manifest.py`; test de
  integración de frescura ampliado para comprobar `run_id` común y
  `analysis_run`.

Verificación:
- Línea base antes del cambio en
  `evidence/2026-09-14-T-002-manifest/antes.txt`: 405 tests, ruff y mypy
  limpios; esquema v1 sin `run_id`; `recommendation=214`,
  `data_freshness_measurement=107`.
- Después del cambio: `python -m pytest -q` → 405 passed, 1 warning de
  serialización Pydantic en un test que ya usa `Path` para `db_path`;
  `ruff check .` ok; `mypy advisor` ok.
- Verificación real se hizo sobre copia, no sobre `intradia.db`:
  `/tmp/intradia-t002.db` con config temporal `/tmp/intradia-t002-config.yaml`.
  La migración creó y verificó
  `/tmp/intradia-t002.db.bak-20260914-090533-pre-v2`; `PRAGMA user_version=2`;
  `analysis_run=1`; `data_freshness_measurement` con `run_id` nuevo = 107.
- Run verificado:
  `e86c54f6-37b8-4307-adf4-f145f5bf9ca3`, `git_sha`
  `e5ed08928d51b5afd4f3315a9ba747c85207a2e6`, `git_dirty=true`,
  `config_hash=9ac73923c3eea91e9c85da6d12b55bb19e42051c5cebf10aa4de75d54291c3ab`,
  `universe_vintage_id=80d05f21abad212757d2f06d9f2dd53032b92a342dba90904b3086ea970d0b59`,
  `clock_status=CLOCK_UNKNOWN`.
- Comprobación manual: `git_sha` del manifiesto coincide con
  `git rev-parse HEAD`; añadir un comentario a la config temporal no cambió
  el `config_hash` (`True` en `despues.txt`).

Impacto:
- Activos afectados: 0 por reglas de decisión; no se tocaron `compute_score`,
  `classify`, `compute_levels*` ni `evaluate_trade_at_entry`.
- Señales afectadas: 0 por reglas de decisión.
- Persistencia: filas nuevas de frescura llevan `run_id`; en la verificación
  real no hubo recomendaciones nuevas porque el proveedor devolvió sin datos
  para todos los símbolos.
- Informe: gana una línea al pie con `run_id`, SHA, config hash y universo.

Invariantes revisadas:
- INV-03: no aplica a cálculo; `compute_score` no se modificó.
- INV-10: no se persiste narrativa ni se mezcla con columnas numéricas.
- INV-17: ejercitada con migración v1→v2, backup previo y
  `verificar-backup`.
- INV-18: ejercitada en test de integración y en copia real para
  `analysis_run` + 107 mediciones de frescura con `run_id`.

Hallazgos clasificados:
- BLOCKER de aceptación real: durante la pasada sobre `/tmp/intradia-t002.db`,
  yfinance/proveedor devolvió `No se han recibido datos` para los 107 activos,
  por lo que se persistieron 0 recomendaciones nuevas en vez de las 107
  exigidas por el criterio de aceptación. La base migró, el backup verificó y
  las 107 mediciones de frescura sí quedaron con `run_id`. No parece causado
  por la migración, pero impide declarar aceptada la ficha.
- OBSERVATION: al redirigir stdout y stderr al mismo `despues.txt`, el log de
  persistencia puede aparecer pegado a la línea de manifiesto; en terminal
  normal stdout/stderr van separados.

PENDIENTE DE REVISIÓN:
- Opus debe intentar refutar que no hay migración sin backup, que las filas
  nuevas persistidas por pasadas reales siempre llevan `run_id`, que
  `backup_log` compara contra los conteos correctos y que la reconstrucción
  por `run_id` recupera SHA + config hash + universe vintage.
- Repetir la verificación real cuando el proveedor devuelva datos para
  confirmar las 107 recomendaciones + 107 mediciones exigidas por la ficha.

Commit/handoff para Claude Code:
- No se ejecutó `git add`, `git commit` ni `git push` por la limitación de
  escritura en `.git` indicada por el propietario.
- Ficheros de esta tarea que hay que commitear:
  `advisor/analysis/scoring.py`,
  `advisor/main.py`,
  `advisor/run/__init__.py`,
  `advisor/run/manifest.py`,
  `advisor/storage/db.py`,
  `advisor/storage/migrations.py`,
  `tests/test_freshness.py`,
  `tests/test_manifest.py`,
  `tests/test_migrations.py`,
  `README.md`,
  `docs/roadmap.md`,
  `docs/tareas/T-002-migraciones-y-manifiesto.md`,
  `evidence/2026-09-14-T-002-manifest/README.md`,
  `evidence/2026-09-14-T-002-manifest/antes.txt`,
  `evidence/2026-09-14-T-002-manifest/despues.txt`.
- Nota de staging: `README.md` y `docs/roadmap.md` ya tenían cambios sin
  commitear antes de T-002; para no mezclar documentación del propietario,
  usar staging por hunks y quedarse solo con los comandos nuevos del README y
  las dos filas C-01/C-02 del roadmap.
- Mensaje propuesto:
  `feat(storage): migraciones versionadas con backup verificado y manifiesto de ejecución por pasada`.
