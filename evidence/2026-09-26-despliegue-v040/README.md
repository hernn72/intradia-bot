# Despliegue de `v0.4.0` en la Pi — 2026-09-26 (T-018 / C-09, migración v5 → v6)

Primer despliegue por tag que **migra el esquema** desde que existe el
procedimiento de `docs/despliegue-y-rollback.md`. Entra la caché de barras de
sesión cerrada ya validadas (T-018, D-41, D-44).

    tag         v0.4.0 (anotado)
    SHA         84ea28e3a39a5602302838504e37c60aaf9492de
    anterior    v0.3.0 = 03e1ec37e59e645164ac48779e169fc58a4bcc2b
    esquema     v5 → v6
    release     https://github.com/hernn72/intradia-bot/releases/tag/v0.4.0 (release.yml en verde)

Entre `v0.3.0` y `v0.4.0` no cambian `requirements.txt` ni `deploy/`, así que no
se reinstalaron dependencias ni unidades; `verificar-systemd` lo confirma. La
única migración nueva es la v6 (`_migration_v6_validated_bar_cache`).

## Secuencia

1. **Preflight en `v0.3.0`**: `EN_TAG`, SHA `03e1ec3…`, árbol sin cambios en
   ficheros con seguimiento, `PRAGMA user_version = 5`. Solo había dos entradas
   sin seguimiento preexistentes (`logs/` y
   `intradia.db.rollback-20260918-144036`), que por la regla de
   `advisor/run/git.py` no ensucian el árbol y no se tocaron.
2. **Timers parados** y ninguna pasada en curso (`inactive`).
3. **Backup manual** `intradia.db.bak-manual-20260926-173436`: íntegro, esquema
   v5, no registrado (copia manual), conteos idénticos a la base viva,
   **`VALIDO`**, verificado con el código de `v0.3.0` y otra vez con `v0.4.0`.
4. **`git fetch --tags` y `git checkout v0.4.0`**, sin `git pull`. `HEAD` y
   `git rev-list -n 1 v0.4.0` = `84ea28e…`; `verificar-release` = `v0.4.0` /
   `EN_TAG`; `verificar-systemd` alineado.
5. **Pasada seca** `analizar --horizonte swing --sin-ia --sin-guardar`: código 0,
   93 activos. **No migró**: el esquema seguía en 5 y no había backup `pre-v6`
   (ver «Desviación»).
6. **Migración aislada**, con la aprobación del propietario:
   `AdvisorDB(load_config().db_path)`. Esquema **6**; backup automático
   `intradia.db.bak-20260926-173928-pre-v6`: íntegro, esquema v5, **registrado
   en `backup_log`**, conteos idénticos, **`VALIDO`**. Tablas `validated_bar` y
   `validated_bar_revision` y las columnas `bars_served_from_cache`,
   `bars_pinned_revisions`, `sessions_never_observed` y `bar_cache_status`
   presentes; `PRAGMA integrity_check = ok`.
7. **Primera pasada real** `analizar --horizonte swing`: código 0,
   `run_id = ea08c727-8c1c-4d02-8a08-5d197f5dc33b`, **93 recomendaciones y 93
   mediciones de frescura** persistidas, 2 OPERAR (ARM y R6C0.DE, 71).
   Manifiesto: `release_tag v0.4.0`, `git_sha 84ea28e…`, `git_dirty false`,
   `schema_version 6`, `score_model_version 1.0`, `CLOCK_OK`,
   `config_hash 2356d37d…`, universo `237b0056…`.
8. **Caché**: `validated_bar = 3228`, `validated_bar_revision = 0`.
9. **Timers reactivados** (`active`); próximas pasadas el lunes 2026-09-28 a las
   07:00 y 22:30 BST.

## Desviación del procedimiento, y por qué

El procedimiento decía que la pasada `--sin-ia --sin-guardar` era «donde se
aplica la migración». **Es falso**: `cmd_analizar` hace
`db = None if args.sin_guardar else AdvisorDB(config.db_path)`
(`advisor/main.py:259`), así que con `--sin-guardar` no abre la base, no migra,
no hace el backup `pre-vN` y, desde T-018, tampoco usa la caché
(`advisor/main.py:239–247`). El despliegue se paró con la base intacta, y el
propietario eligió migrar de forma aislada antes de la primera pasada
persistente. `docs/despliegue-y-rollback.md` queda corregido en la misma
entrega que esta evidencia.

## Lo que dice la primera pasada con caché

La caché arrancó vacía, así que no sirvió ninguna barra. Esa pasada midió **16
sesiones exigibles nunca observadas y no entregadas, en 16 activos**, todas la
barra del 2026-09-25 en ETF de XETRA: el retraso europeo ya conocido. Es la cifra
que acumula **OD-02 bis**, que **sigue abierta**: una sola pasada no distingue
un fallo puntual del proveedor de un hueco estructural.

## Ficheros

Los ficheros `01`, `03` y `04` se obtuvieron **después** del despliegue (a las
18:45 hora de la Pi), con comandos de solo lectura: base abierta con
`mode=ro`, y `manifiesto` y `verificar-backup` en el modo de solo lectura de
`AdvisorDB`. Los ficheros `02` y `05` son los logs literales de las dos pasadas,
copiados de `logs/` en la Pi. Los resultados del preflight en `v0.3.0` y de la
migración aislada no tienen fichero propio: se registran en la secuencia de
arriba tal como salieron en la sesión.

| Fichero | Qué contiene |
|---|---|
| `01-verificaciones.txt` | `HEAD`, `git rev-list -n 1 v0.4.0`, `verificar-systemd`, `verificar-release` con código de salida, estado de los timers |
| `02-pasada-seco.txt` | pasada `--sin-ia --sin-guardar`, código 0 (no migra) |
| `03-manifiesto.txt` | `manifiesto --run-id ea08c727-…` |
| `04-base.txt` | `verificar-backup` de las dos copias, esquema, integridad, estructuras v6 y conteos de la caché y del run |
| `05-pasada-real.txt` | primera pasada persistente en `v0.4.0` |

## Rollback, si hiciera falta

Volver a `v0.3.0` **no** deshace la v6 (D-32). Se restaura
`intradia.db.bak-20260926-173928-pre-v6` (v5, verificado) siguiendo
`docs/despliegue-y-rollback.md`, y se pierden las pasadas guardadas desde la
migración (17:39 UTC del 2026-09-26, 18:39 hora de la Pi).
