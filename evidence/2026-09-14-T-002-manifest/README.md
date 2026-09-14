# T-002 — migraciones y manifiesto

Instante: 2026-09-14T09:05:33Z a 2026-09-14T10:07:46+01:00.
Commit base: `e5ed089`.
Rama: `feat/run-manifest-migrations`.

## Antes

Comando:

```bash
source .venv/bin/activate
python -m pytest -q
ruff check .
mypy advisor
sqlite3 intradia.db ".schema"
sqlite3 intradia.db "SELECT 'recommendation', count(*) FROM recommendation UNION ALL SELECT 'data_freshness_measurement', count(*) FROM data_freshness_measurement;"
```

Resultado en `antes.txt`:

- 405 tests pasan.
- `ruff check .` limpio.
- `mypy advisor` limpio.
- Esquema sin `user_version` aplicado ni `run_id`.
- Conteos: `recommendation=214`, `data_freshness_measurement=107`.

## Después

Comandos principales:

```bash
source .venv/bin/activate
python -m pytest -q
ruff check .
mypy advisor

cp intradia.db /tmp/intradia-t002.db
cp config.yaml /tmp/intradia-t002-config.yaml
perl -0pi -e 's#db_path:\s*.*#db_path: /tmp/intradia-t002.db#' /tmp/intradia-t002-config.yaml
python -m advisor.main --config /tmp/intradia-t002-config.yaml analizar --horizonte swing --sin-ia
python -m advisor.main --config /tmp/intradia-t002-config.yaml verificar-backup --ruta /tmp/intradia-t002.db.bak-20260914-090533-pre-v2
sqlite3 /tmp/intradia-t002.db "PRAGMA user_version; SELECT count(*) FROM analysis_run;"
python -m advisor.main --config /tmp/intradia-t002-config.yaml manifiesto --run-id e86c54f6-37b8-4307-adf4-f145f5bf9ca3
```

Resultado:

- 405 tests pasan, 1 warning conocido de Pydantic por `db_path=Path` en test.
- `ruff check .` limpio.
- `mypy advisor` limpio.
- Backup previo creado y verificado:
  `/tmp/intradia-t002.db.bak-20260914-090533-pre-v2`.
- `PRAGMA user_version = 2`.
- `analysis_run = 1`.
- Run: `e86c54f6-37b8-4307-adf4-f145f5bf9ca3`.
- `git_sha` del manifiesto:
  `e5ed08928d51b5afd4f3315a9ba747c85207a2e6`, coincide con HEAD.
- `config_hash`:
  `9ac73923c3eea91e9c85da6d12b55bb19e42051c5cebf10aa4de75d54291c3ab`.
- `universe_vintage_id`:
  `80d05f21abad212757d2f06d9f2dd53032b92a342dba90904b3086ea970d0b59`.
- Añadir un comentario a la config temporal no cambió el `config_hash`.

## Conclusión

La migración, el backup verificado y el manifiesto funcionan en copia de la
base real. Las 107 mediciones de frescura nuevas quedaron asociadas al
`run_id`.

Bloqueo de aceptación real: la pasada de datos reales devolvió `No se han
recibido datos` para los 107 activos, así que no generó recomendaciones
nuevas. Por eso no se pudo comprobar el criterio exacto de 107
recomendaciones + 107 mediciones en la pasada real; sí se comprobó en test de
integración con proveedor simulado.

## Verificación real repetida — 2026-09-14 09:15 UTC (`despues-2.txt`)

Sobre una copia nueva `/tmp/intradia-t002b.db` (config `/tmp/intradia-t002b-config.yaml`),
el proveedor ya respondía:

- `analizar --horizonte swing --sin-ia` → 107 recomendaciones y 107 mediciones
  guardadas con `run_id = 07de4ea6-f372-4561-9f0a-e96436c88e76`.
- Backup `/tmp/intradia-t002b.db.bak-20260914-091509-pre-v2` creado y `verificar-backup` → 0.
- `PRAGMA user_version = 2`; `analysis_run = 1`; filas antiguas con `run_id NULL` (214 y 107).
- `manifiesto --run-id 07de4ea6…` → `git_sha e5ed0892…` = `git rev-parse HEAD`;
  `config_hash 8750384a…` (distinto del run anterior porque `db_path` difiere: ver OBSERVATION 7 del revisor).

El BLOCKER declarado por Codex (proveedor sin datos) era transitorio.

## Revisión independiente y correcciones — 2026-09-14

Revisor: subagente `revisor` con `PROMPT_REVIEW`. Veredicto: **CORREGIR**.
Hallazgos confirmados con reproducción y corregidos:

| # | Hallazgo | Corrección | Test |
|---|---|---|---|
| 1 | Migración no atómica (`executescript`): un corte entre los dos `ALTER TABLE` dejaba `run_id` puesto y `user_version` 1; cada reapertura fallaba con `duplicate column` y creaba otro backup | `run_migration`: `BEGIN IMMEDIATE`, sentencias una a una, `PRAGMA user_version`, `COMMIT`; `ROLLBACK` si falla | `test_migracion_que_falla_a_mitad_no_deja_esquema_a_medias` |
| 2 | `verificar-backup` y `manifiesto` instanciaban `AdvisorDB` y migraban la base viva (el revisor migró el `intradia.db` real; sin pérdida, backup `intradia.db.bak-20260914-091715-pre-v2`); con ruta inexistente creaban una base vacía | `AdvisorDB(readonly=True)` abre `mode=ro`, no crea ni migra; `FileNotFoundError` si no existe | `test_verify_backup_no_escribe_en_la_base_viva`, `test_readonly_no_crea_ni_migra` |
| 3 | `backup_log.backup_path` relativo y comparación por cadena: ruta absoluta → «Backup inválido» sobre un backup íntegro | Rutas resueltas al registrar y al comparar | `test_verify_backup_acepta_ruta_relativa_y_absoluta` |
| 4 | Sonda NTP por TCP (NTP es UDP): nunca medía, 6 s por pasada y por test; `timedatectl show -p TimeUSec` da el reloj local en formato humano (`Mon 2026-09-14 10:29:24 BST`, verificado en la Pi) | `timedatectl timesync-status` → `Offset` (Pi: `-572us`), `chronyc tracking`, SNTP UDP a una dirección; test de integración parchea la medición | `test_offset_de_timesync_status_se_parsea_en_segundos`, `test_timedatectl_usa_timesync_status`, `test_sonda_ntp_es_udp_y_no_sale_a_la_red_en_tests` |
| 5 | Tests ausentes | `run_id` obligatorio (None/vacío/ausente) en ambas APIs; segunda apertura idempotente; conteos del backup; backup con menos filas | `tests/test_db.py::TestRunIdObligatorio`, `test_segunda_apertura_es_idempotente`, `test_backup_conserva_los_conteos_registrados`, `test_backup_con_menos_filas_que_el_registro_falla` |

Verificación tras las correcciones (portátil):

```text
verificar-backup --ruta /tmp/intradia-t002b.db.bak-20260914-091509-pre-v2   → 0 (ruta absoluta)
manifiesto --run-id 07de4ea6-…                                              → manifiesto completo, sin backups nuevos (sigue habiendo 1)
manifiesto --run-id no-existe                                               → 1
measure_clock_drift_seconds()                                               → -0.129 s en 0.07 s (antes: None en 6.06 s)
```

FOLLOW_UP / OBSERVATION del revisor no corregidos aquí (en `docs/roadmap.md`, hallazgos abiertos):
`git_dirty` falso ante fallo de git (exige columna nullable → migración); `config_hash`
incluye `db_path`/`universe_path`; `backup_log` se crea fuera de `MIGRATIONS`;
D-09 y D-13 precisadas en el decision log.

## Despliegue y verificación en la Pi — 2026-09-14 09:36–09:39 UTC

`fer@Raspberry4` (192.168.1.113), Python 3.13.5. Antes: `main` `6d32cf2`, base `user_version` 0
con 2.503 recomendaciones y 1.177 mediciones (11 pasadas desde el 2 de septiembre). Copia manual
previa: `intradia.db.bak-manual-pre-t002`.

```text
git checkout feat/run-manifest-migrations   → 7d450ad
pip install -r requirements.txt             → sin cambios
verificar-systemd                           → «Unidades systemd alineadas con las plantillas versionadas.»
pytest -q                                   → 417 passed, 3 skipped (150 s)
analizar --horizonte swing --sin-ia         → exit 0; 107 recomendaciones + 107 mediciones
backup automático                           → intradia.db.bak-20260914-093629-pre-v2 (1.093.632 bytes)
verificar-backup (relativa y absoluta)      → 0 y 0
PRAGMA user_version = 2 · integrity_check = ok · analysis_run = 1
recommendation: 2.610 (2.503 sin run_id + 107 con run_id e777e161-…)
data_freshness_measurement: 1.284 (1.177 sin run_id + 107 con run_id)
manifiesto: git_sha 7d450ad9…, environment pi, clock_status CLOCK_OK, drift −0,000572 s
            (coincide con `timedatectl timesync-status` Offset −572us), config_hash d359c8d3…
            (= hash del config.yaml commiteado)
```

Hallazgo al desplegar: el manifiesto salió `+dirty` porque `logs/` no tiene seguimiento en la
Pi. Corregido en el commit siguiente: `git_dirty` ignora ficheros sin seguimiento
(`--untracked-files=no`), con test. Los timers siguen vivos; la siguiente pasada programada
(14:30 BST) es la primera de producción con manifiesto.
