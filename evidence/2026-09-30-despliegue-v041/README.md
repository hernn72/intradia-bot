# Despliegue de `v0.4.1` en la Pi — 2026-09-30 (T-019 paso 1, migración v6 → v7)

Despliega el estado de `main` que contiene el paso 1 de T-019 (contrato de
umbrales por horizonte y persistencia v7) **sin** el paso 2a-code. Por D-58, la
migración v7 se aísla y se valida en producción antes de introducir el contexto
point-in-time. Producción sigue en **Score v1**, con 70/60 legacy y
`calibrated: false`; no se activa v2 ni se ejecuta P3.

**Estado: ACEPTADO por el propietario el 2026-09-30.** Estado final `EN_TAG`,
timers activos, **rollback no ejecutado**.

    tag         v0.4.1 (anotado)
    SHA         8b2dddb8fd66423d9550df496d1a2a85abd066b6
    anterior    v0.4.0 = 84ea28e3a39a5602302838504e37c60aaf9492de
    esquema     v6 → v7
    release     https://github.com/hernn72/intradia-bot/releases/tag/v0.4.1
                (release.yml en verde: checks 3.12 y 3.13 + publicar release)

`8b2dddb` es también el SHA del pre-registro ejecutable de P3; el tag no añade
ningún commit. Entre `v0.4.0` y `v0.4.1` no cambian `requirements.txt` ni
`deploy/`, así que no se reinstalaron dependencias ni unidades;
`verificar-systemd` lo confirma. La única migración nueva es la v7
(`_migration_v7_scoring_contract_and_review_run`).

## Secuencia (horas UTC)

1. **En el portátil**: `main` = `origin/main` = `8b2dddb…`; CI de `main` en
   verde en 3.12 y 3.13 (run 36583463281). Tag anotado `v0.4.1` sobre ese SHA,
   empujado; `release.yml` (run 36705812825) pasó los checks y publicó el
   release a las 11:01:52, con «SHA del tag: 8b2dddb…» en las notas.
2. **Preflight en la Pi en `v0.4.0`** (11:00): `HEAD` = `84ea28e…`,
   `EN_TAG`, `PRAGMA user_version = 6`, servicios de análisis `inactive`. Solo
   dos entradas sin seguimiento preexistentes (`logs/` e
   `intradia.db.rollback-20260918-144036`), que no ensucian el árbol y no se
   tocaron.
3. **Timers parados** y ninguna pasada en curso (`inactive` los cuatro;
   ningún proceso `advisor.main`).
4. **Backup manual** `intradia.db.bak-manual-20260930-110208`: sha256 idéntico
   al de la base viva en ese momento (`6e58e8c4…`), íntegro, esquema v6, no
   registrado (copia manual), **`VALIDO`**; verificado con el código de
   `v0.4.0` y otra vez con `v0.4.1`.
5. **`git fetch --tags` y `git checkout v0.4.1`**, sin `git pull`. `HEAD` y
   `git rev-list -n 1 v0.4.1` = `8b2dddb…`; `verificar-release` = `v0.4.1` /
   `EN_TAG`; `verificar-systemd` alineado. La base seguía en 6.
6. **Pasada seca** `analizar --horizonte swing --sin-ia --sin-guardar` (11:03):
   código 0, 93 activos, run `b0995877…` no persistido. **No migró**, como era
   de esperar: esquema 6 y sin backup `pre-v7`.
7. **Migración aislada** (11:05:37) con `AdvisorDB(load_config().db_path)`,
   código 0. Comprobaciones, todas correctas:
   - `PRAGMA user_version = 7`;
   - `PRAGMA integrity_check = ok`;
   - `PRAGMA foreign_key_check` sin filas;
   - backup automático `intradia.db.bak-20260930-110539-pre-v7`: íntegro,
     esquema **v6**, registrado en `backup_log` (8 filas, `target_version` 7),
     conteos idénticos a la base en el momento de migrar, **`VALIDO`**;
   - `analysis_run.scoring_contract_json TEXT` presente;
   - `position_review.run_id TEXT` presente, con FK a `analysis_run(run_id)` e
     índice `idx_position_review_run_id`;
   - las **59** `analysis_run` anteriores conservan `scoring_contract_json =
     NULL`; no se rellenaron históricos. `position_review` tiene **0 filas**,
     así que la condición «`run_id` NULL en históricos» se cumple sin datos
     que la pongan a prueba.
8. **Primera pasada real** `analizar --horizonte swing` (11:06–11:08): código 0,
   `run_id = 693c7e1d-a086-4d62-a3b0-b97abb4fa304`, **93 recomendaciones y 93
   mediciones de frescura**. Manifiesto: `release_tag v0.4.1`,
   `git_sha 8b2dddb…`, `git_dirty false`, `schema_version 7`,
   `score_model_version "1.0"`, `CLOCK_OK`, `config_hash 89406d28…`,
   universo `237b0056…` (el mismo que en `v0.4.0`).
   `scoring_contract_json` presente: `score_model_version "1.0"`,
   `fundamentals_enabled false` y, en los tres horizontes, 70/60 con
   `calibrated false` y `calibration_ref null`. Coherente con lo que se
   decidió: 3 OPERAR a 71,6; 28 VIGILAR entre 60,4 y 68,5; 62 DESCARTAR entre
   36,6 y 59,1.
9. **Timers reactivados** (`active`); `verificar-systemd` alineado y
   `verificar-release` `EN_TAG`. Próximas pasadas: 14:30 BST (swing) y
   22:30 BST (evento) del mismo día.

No se aplican las exclusiones de P3 (D-51, D-52, D-55): pertenecen al
laboratorio v2 y a 2a-code, no a producción v1. La pasada analiza los mismos 93
activos que la primera de `v0.4.0` (`ea08c727…`, 93 recomendaciones).

## Observaciones

Ninguna bloquea la aceptación de `v0.4.1`.

- **OBSERVATION — `position_review` sin filas reales históricas.** La tabla
  tiene 0 filas, así que la condición «`run_id` NULL en las revisiones
  anteriores a v7» se cumple sin datos que la pongan a prueba en producción. El
  contrato está cubierto por los tests del paso 1.
- **Revisiones de la caché en la pasada real: 147** (`validated_bar_revision`
  pasa de 579 a 726). Son comportamiento de T-018 (D-44), no de la v7: **117
  `REVISION` no aplicadas**, de las que 112 solo cambian el volumen (en 22 de
  ellas la barra guardada tenía volumen 0) y las 5 restantes (MC.PA, AIR.PA,
  SAF.PA ×2, RACE.MI) conservan el cierre y cambian apertura, máximo o mínimo;
  y **30 `REAJUSTE` aplicados en TTE.PA**.
- **OBSERVATION / FOLLOW_UP de T-018 — TTE.PA, 32 frente a 30.** El log de la
  pasada real dice «Caché reanclada en TTE.PA: 32 barras descartadas por
  reajuste de la serie» y `validated_bar_revision` registra **30** filas
  `REAJUSTE` de ese símbolo en el run `693c7e1d…`. La diferencia de 2 **no se
  ha investigado**: pertenece a la caché de T-018, no a T-019, y queda **fuera
  del alcance de este cierre**. No afecta a la migración v7 ni al manifiesto.
- Los nombres de columna de `analysis_run` (sin `started_at`),
  `recommendation` (`accion`) y `backup_log` (`backup_path`,
  `target_version`) obligaron a repetir alguna consulta de lectura; ninguna
  escribió en la base.

## Ficheros

Los ficheros `01`, `03` y `04` se obtuvieron **después** del despliegue (sobre
las 11:15 UTC), con comandos de solo lectura: base abierta con `mode=ro` y
`manifiesto` y `verificar-backup` en el modo de solo lectura de `AdvisorDB`.
Por eso los conteos de «filas en la viva» de `04` ya incluyen la pasada real.
Los ficheros `02` y `05` son los logs literales de las dos pasadas, copiados de
`logs/deploy-v041-*.log` en la Pi. El preflight en `v0.4.0` y la migración
aislada no tienen fichero propio: se registran en la secuencia de arriba tal
como salieron en la sesión.

| Fichero | Qué contiene |
|---|---|
| `01-verificaciones.txt` | `HEAD`, `git rev-list -n 1 v0.4.1`, tipo del tag, `verificar-systemd`, `verificar-release` con código de salida, estado y lista de los timers |
| `02-pasada-seco.txt` | pasada `--sin-ia --sin-guardar`, código 0 (no migra) |
| `03-manifiesto.txt` | `manifiesto --run-id 693c7e1d-…` |
| `04-base.txt` | `verificar-backup` de las dos copias, sha256, esquema, integridad, FK, estructuras v7, NULL en históricos, `backup_log`, conteos del run y desglose de las revisiones de la caché |
| `05-pasada-real.txt` | primera pasada persistente en `v0.4.1` |

## Rollback

**No se ejecutó.** Procedimiento, si hiciera falta:

Volver a `v0.4.0` **no** deshace la v7 (D-32): un `checkout` de `v0.4.0` no es
un rollback válido. Hay que parar los timers, conservar una copia de la base
v7, hacer `checkout v0.4.0`, restaurar `intradia.db.bak-20260930-110539-pre-v7`
(v6, verificado), verificarlo, hacer la pasada seca y reactivar los timers,
siguiendo `docs/despliegue-y-rollback.md`. Se pierden las pasadas guardadas
desde la migración (11:05 UTC del 2026-09-30).
