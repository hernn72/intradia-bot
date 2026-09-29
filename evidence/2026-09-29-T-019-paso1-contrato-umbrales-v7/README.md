# T-019 paso 1 — contrato de umbrales por horizonte y migración v7 — 2026-09-29

Paso 1 de `docs/tareas/T-019-score-v2-y-calibracion-por-horizonte.md` (A-03),
autorizado por el propietario el 2026-09-29. **v1 sigue activo y sin cambio de
comportamiento**; lo único visible es la etiqueta «umbral no calibrado».

    rama        research/a03-score-v2 (desde main = b7a9786)
    commit      el que añade esta carpeta
    esquema     v6 → v7 (_migration_v7_scoring_contract_and_review_run)
    modelo      score_model_version 1.0, 70/60 legacy, calibrated: false en los tres horizontes
    vintage     071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841 (solo en el portátil)
    la Pi       no se toca: sigue en v0.4.0, esquema v6

## Qué entra

- `ScoringConfig` con `score_model_version` y `thresholds` por horizonte, y las
  nueve reglas de validación en `load_config`. Además, `load_config` exige que
  el YAML declare de forma explícita `scoring.score_model_version` y
  `scoring.thresholds`, y la configuración exige umbrales para los **tres**
  horizontes válidos, no solo los de `horizontes`: `abrir --horizonte` acepta
  cualquiera y el seguimiento no puede quedarse sin umbral para una posición.
- `classify_setup_detailed` y `tracking._verdict` leen del horizonte; sin
  horizonte, error (no hay caída a `swing`). Las ramas de umbral nulo
  (`SCORE_UNCALIBRATED`; veredicto solo por precio) existen y tienen test,
  aunque v1 no puede alcanzarlas.
- `Score` lleva el `score_model_version` que lo produjo; `Score.grade` y
  `conviction_label` fallan si no es `1.0` (aisladas de v2).
- `analysis_run.scoring_contract_json`: JSON canónico del contrato cargado en
  la pasada. `analysis_run.score_model_version` es el del modelo **ejecutado**
  (`advisor.analysis.scoring.SCORE_MODEL_VERSION`); si no coincide con el del
  contrato, la pasada aborta. `insert_analysis_run` rechaza contratos vacíos,
  mal formados o incompletos.
- `position_review.run_id` (FK nullable a `analysis_run`); `seguimiento` crea
  su manifiesto (INV-18). Filas anteriores a v7: `NULL`, nunca rellenadas.
- Informe, Telegram, texto al LLM e informe de seguimiento declaran «umbral no
  calibrado».

## Verificación

`01-verificaciones.txt`: 703 tests, `ruff`, `mypy` y el backtest de la cosecha,
**idéntico byte a byte a A-02** (866 operaciones, hash normalizado
`49b12c85…`).

`02-migracion-y-pasada-real.txt`: camino real sobre una **copia de solo
lectura** de la base de la Pi (esquema v6, 55 pasadas), con un `config.yaml`
que solo cambia `db_path`. Migración aislada con `AdvisorDB`, `analizar
--sin-ia` real (93 recomendaciones con contrato), `abrir` en `medio` y
`seguimiento` (la revisión lleva el `run_id` del manifiesto de seguimiento).
v7 íntegra, sin violaciones de clave ajena, las 55 pasadas previas sin
contrato, y backup `pre-v7` íntegro en v6 y registrado en `backup_log`. La base
de producción no se escribió.

Recorridos de migración con test (`tests/test_migrations.py`): base nueva
v1→v7 en una apertura, v6→v7 con backup `pre-v7`, v5→v6→v7 con los dos backups.
**El rollback de código no deshace la v7** (D-32): volver atrás exige restaurar
el backup `pre-v7`.

## Revisión

Codex programó; el supervisor revisó y devolvió cinco defectos (etiqueta
ausente en el LLM y en el seguimiento, guarda de versión tautológica, caída
silenciosa a `swing`, umbrales por defecto cargados en silencio). Un revisor
independiente dio cero críticos, cero importantes y cuatro menores
(seguimiento que abortaba con un horizonte sin umbral, reglas sin prueba de
rechazo, guarda de persistencia sin prueba e incompleta, y `grade` /
`conviction_label` sin aislar). Todos corregidos y verificados de nuevo.

Aceptado a propósito: v1 solo admite 70/60; el formato de `calibration_ref`
(`D-nn · evidence/<ruta>`) no se valida hasta que exista "2.0", porque hoy es
inalcanzable; `seguimiento` crea manifiesto aunque no haya posiciones.
