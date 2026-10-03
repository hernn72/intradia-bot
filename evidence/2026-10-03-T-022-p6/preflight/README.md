# T-022 / A-06 — Preflight definitivo de P6

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

**P6 no se ha ejecutado.** No existe `../run/` ni la marca `EJECUCION_CONFIRMATORIA_P6_INICIADA`, no se
ha emitido ningún token y `new_p6_outcomes_read = false`. El preflight no cuenta señales OPERAR reales,
no simula ninguna cartera sobre la cosecha y no calcula ninguna métrica real.

## Identidad

| | |
|---|---|
| `P6_PREREG_SHA` | `03f04a42ea9d2be893e7c4cc09de76bd1c55778b` (en la historia de HEAD) |
| `P6_DATA_ID` | `572e09141dbfe0fc9c53a7b529f1abcff46e16027fe9b47d1f3e26330c1e5383` (reproducido) |
| Ejecutor | `d4f213b866006069708f24c056c5a6a542d2685c` (candidato a `P6_CODE_SHA`): `advisor/research/p6.py`, `advisor/research/p6_sim.py`, CLI `p6` y `tests/test_p6.py` |
| Cosecha / universo | `071ddb2b…` / `237b0056…` |
| FX | `fx_vintage_id 10e832ef…` (fuente B, BCE), verificado contra su manifiesto y su sha256 |
| Sector | `24f45421…`, 90/90 |

## Lo que comprueba (31/31 OK)

- **Identidad:** P6_PREREG_SHA en la historia, `config_hash` de producción, Score v1 (`"1.0"`),
  `data_vintage_id`, `exchange_calendars` 4.13.2, tzdata 2026.4, `exchange_overrides.yaml`,
  `P6_DATA_ID` y los 90 activos.
- **Políticas:** `policy_sha256` y `advisor_config_hash` de B2, S2 y C0, regenerados, y el
  `canonical_json` de P5 de B2 y S2 idéntico byte a byte a `politicas-finales.json`.
- **Datos auxiliares:** FX (fuente B; pares HKD, JPY, USD) y mapa sectorial congelados.
- **Ventana estructural** (solo fechas): **2022-06-14 → 2026-08-27**.
  - El último calentamiento de los 88 activos iniciales es el 2022-02-25.
  - La SMA200 de `^STOXX50E` se completa en la sesión del 2022-06-13.
  - 27 sesiones sin barra, contadas desde la primera barra de cada activo.
  - 1.095 instantáneas y `periodos_por_año = 260,5529…`.
- **Identidades de las 9 corridas** (`system-hashes.json`), calculadas sin ningún desenlace:
  - B2 y S2 primaria (5 pb), sensibilidad (10 pb) y todas las barras (5 pb);
  - C0 primaria;
  - benchmark a 5 pb y a 10 pb.
- **Guardas** (`guardas-outcome.txt`): sin token no se cargan precios reales ni se generan señales; un
  token fabricado no vale; el motor rechaza datos reales sin autorización; la marca no existe.
- **Determinismo** (`determinismo.txt`): el fixture sintético da el mismo ledger, la misma serie diaria,
  las mismas métricas y el mismo ledger del benchmark, byte a byte.

## Ficheros

| Fichero | Contenido |
|---|---|
| `p6-preflight.json` / `.txt` | Informe completo y resumen |
| `consola-preflight.txt` | Salida literal de `python -m advisor.main p6 --fase preflight` y su código de salida |
| `system-hashes.json` | `system_sha256` de las 7 corridas y `benchmark_sha256` de los 2 benchmarks, con la ventana |
| `tests-48.md` | Los 48 tests de T-022 §20, con su test pytest y su estado (48/48 PASSED) |
| `suite-ruff-mypy-pytest.txt` | ruff, mypy y la suite completa sobre el ejecutor |
| `determinismo.txt` | Hashes de dos corridas sintéticas idénticas |
| `guardas-outcome.txt` | Guardas de desenlace comprobadas |
| `identidad.txt` | SHAs, árbol limpio, marca y `run/` inexistentes, sin `P6_RUN_HEAD_SHA` |
| `SHA256SUMS.txt` | Hash de cada fichero |

## Siguiente

Revisión adversarial independiente del ejecutor y de este preflight. Después, `P6_CODE_SHA` y, solo
con una autorización expresa del propietario, la única `p6 --fase confirmatoria`.
