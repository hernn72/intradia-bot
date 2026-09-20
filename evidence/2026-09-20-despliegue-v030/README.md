# Despliegue de `v0.3.0` en la Pi — 2026-09-20 (OA-04)

Primer despliegue por tag desde que el procedimiento existe, hecho sin ensayo
previo porque entre `v0.2.0` y `v0.3.0` **no hay migración de esquema**: la base
sigue en v5 y el rollback sería solo de código.

    tag         v0.3.0
    SHA         03e1ec37e59e645164ac48779e169fc58a4bcc2b
    anterior    v0.2.0 = 785daf4
    base        esquema v5, sin migración
    copia       intradia.db.bak-manual-20260920-160526

## Qué entra

Tres entregas que la Pi no tenía, una de ellas cambia a quién recomienda el bot:

- `fe684e9` T-015 (C-07, D-34): `backtest --vintage` reproducible.
- `3d0e611` D-35: baja de los diez marcados `no` en el broker → 93 analizables,
  vintage `237b0056…`.
- `042b9de` D-36 y D-37: D-21 se mide por activo contra la última barra cerrada
  exigible; una barra abierta se ignora en vez de vetar.

## Verificado

Los ficheros son la salida literal de los comandos en la Pi.

| Fichero | Qué contiene |
|---|---|
| `01-verificaciones.txt` | `git rev-parse HEAD`, `git rev-list -n 1 v0.3.0` y las tres verificaciones con su código de salida |
| `02-pasada-seco.txt` | pasada `--sin-ia --sin-guardar`, código 0 |
| `03-manifiesto.txt` | manifiesto de la pasada real, leído de la base |
| `04-base.txt` | consultas a `intradia.db`: esquema, filas de la run, reparto de `execution_code` |
| `05-pasada-real.txt` | pasada que persiste, con IA, código 0 |

- **`verificar-release`: `EN_TAG`, código 0.** `HEAD`, SHA del tag y `origin`
  coinciden, árbol limpio.
- **`verificar-systemd`: alineadas, código 0.** No hizo falta reinstalar
  unidades: entre los dos tags no cambió ninguna plantilla de `deploy/` ni
  `requirements.txt`; lo único versionado que cambia es `universe.yaml`.
- **`verificar-backup`: `VALIDO`, código 0**, declarado «copia manual, no la hizo
  una migración», que es lo correcto para un `cp`.
- **Pasada real con código 0**, 93 mediciones de frescura y 93 recomendaciones
  guardadas, `run_id` `8609b81b-30d1-4a95-b43f-59c7d7bfb257`.
- **Comprobado sobre la base, no sobre el informe:** el manifiesto persistido
  lleva `release_tag v0.3.0`, `git_sha 03e1ec37…` —el mismo que
  `git rev-list -n 1 v0.3.0`, carácter a carácter—, `git_dirty false`,
  `schema_version 5`, `config_hash_version 2`, `universe_vintage_id 237b0056…`
  y `clock_status CLOCK_OK` con 0,001 s de deriva.
- Timers vivos: `intradia-bot.timer` el lunes a las 07:00 BST,
  `intradia-bot-event.timer` a las 22:30.

## Lo que solo se puede medir aquí: a quién veta ahora D-21

Es la razón por la que este despliegue importa. En la pasada real
(2026-09-20 16:08 UTC, domingo), sobre 93 analizables:

    EXECUTABLE            68
    STALE_DATA            21
    MISSING_RECENT_DATA    4

Los **25 vetados son todos europeos**, ninguno de otra plaza:

- `STALE_DATA` (21): AIR.PA, ALV.DE, ASML.AS, BBVA.MC, BSP.DE, DBK.DE, DTE.DE,
  ENI.MI, IBE.MC, IFX.DE, MBG.DE, MC.PA, MUV2.DE, OR.PA, R6C0.DE, RRU.DE,
  SAF.PA, SAP.DE, SIE.DE, SU.PA, TTE.PA — su última barra es del 2026-09-16 y
  la última sesión cerrada exigible es la del 18.
- `MISSING_RECENT_DATA` (4): ADYEN.AS, ENR.DE, ITX.MC, RACE.MI.

**Japón y Hong Kong no quedan vetados en esta pasada**, al contrario que en la
medición del 2026-09-18 a las 16:20 UTC. No se contradicen: aquel día era
jueves y su sesión del día ya estaba cerrada y todavía sin publicar; hoy es
domingo y no hay sesión que reclamar.

**Lo que esta evidencia NO contiene:** el reparto por cada una de las cuatro
pasadas diarias. Hoy es domingo y solo hay una pasada supervisada. Esa cifra la
dan los timers durante la semana y es material de T-012.
