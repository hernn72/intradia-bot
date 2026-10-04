# T-022 / A-06 — Preflight definitivo de P6

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

**P6 no se ha ejecutado.** No existe `../run/` ni la marca `EJECUCION_CONFIRMATORIA_P6_INICIADA`, no se
ha emitido ningún token y `new_p6_outcomes_read = false`. El preflight no cuenta señales OPERAR reales,
no simula ninguna cartera sobre la cosecha y no calcula ninguna métrica real.

**Lectura mínima de la cosecha** (decisión del propietario, 2026-10-04, tras la revisión de b66db49): el
preflight no llama a `load_vintage` ni construye vistas de precios. Lee las fechas y las acciones
corporativas de los 126 CSV, verificadas contra `corporate_actions_hash`. Los precios se leen como texto
y solo para descartar filas sin precio. Únicamente `Close`/`Adj Close` de la víspera y la fecha ex de los
activos con split y dividendo se convierten a número, para T-022 §10.1.

## Identidad

| | |
|---|---|
| `P6_PREREG_SHA` | `03f04a42ea9d2be893e7c4cc09de76bd1c55778b` (en la historia de HEAD) |
| `P6_DATA_ID` | `572e09141dbfe0fc9c53a7b529f1abcff46e16027fe9b47d1f3e26330c1e5383` (reproducido) |
| Ejecutor | `6ef1aa951f571e83067b12334318d64bdc5378e0` (candidato a `P6_CODE_SHA`): `advisor/research/p6.py`, `advisor/research/p6_sim.py`, `advisor/research/vintage.py` (lector estructural), CLI `p6` y `tests/test_p6.py` |
| Cosecha / universo | `071ddb2b…` / `237b0056…` |
| FX | `fx_vintage_id 10e832ef…` (fuente B, BCE), verificado contra su manifiesto y su sha256 |
| Sector | `24f45421…`, 90/90 |

## Lo que comprueba (35/35 OK)

- **Identidad:** P6_PREREG_SHA en la historia, `config_hash` de producción, Score v1 (`"1.0"`),
  `data_vintage_id`, `exchange_calendars` 4.13.2, tzdata 2026.4, `exchange_overrides.yaml`,
  `P6_DATA_ID` y los 90 activos. `tzdata==2026.4` queda fijado en `requirements.txt` (CI instalaba 2026.5).
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
- **Dividendos y splits, T-022 §10.1** (`dividendos-splits.json`):
  - Hay 16 activos con split. Se comprueba la identidad `r(d−1)/r(d) = 1 − D(d)/Close(d−1)`, con
    `r = Adj Close / Close`, en todas sus fechas ex, con tolerancia 1e-5. Ninguna queda fuera; el
    residuo máximo es 2,6e-7.
  - Solo discriminan un dividendo sin ajustar las fechas ex anteriores al último split: 55, repartidas
    en 6501.T, 6758.T, 6857.T, 7011.T, 8035.T, AVGO, AZN y NVDA. Los otros 8 activos no aportan
    comprobación porque no tienen dividendos o los tienen todos después del split.
  - Lista Xetra: superconjunto declarado de los `.DE` con algún dividendo no redondo a 4 decimales:
    BSP, EQQQ, EXH1, EXSA, EXV1, IQQK, IQQT, R6C0 y RRU. Incluye ETF que reparten en EUR con 6
    decimales. Control positivo: R6C0.DE × 1,1587 da importes redondos. Contiene todos los sospechosos
    de T-022. El dato no se corrige.
  - Los `Close`/`Adj Close` leídos no se verifican contra `series_hash` (`Adj Close` no está en ningún
    hash); `load_vintage` verifica la serie completa en la confirmatoria.
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
| `dividendos-splits.json` | Sección §10.1 del informe: identidad por activo y lista Xetra |
| `identidad.txt` | SHAs, árbol limpio, marca y `run/` inexistentes, sin `P6_RUN_HEAD_SHA` |
| `SHA256SUMS.txt` | Hash de cada fichero |

## Siguiente

Revisión adversarial independiente del ejecutor y de este preflight. Después, `P6_CODE_SHA` y, solo
con una autorización expresa del propietario, la única `p6 --fase confirmatoria`.
