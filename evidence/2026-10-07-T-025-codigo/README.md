# T-025 — Implementación v1 del paper broker (2026-10-07)

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

Implementa el pre-registro congelado `T025_PREREG_SHA = c6fdc421afb0c1fbba5780ae533e7d97681f4c06` (D-75 a D-79).
**No desplegado; sin cohorte forward real; ningún desenlace forward observado.** Rama `feat/t025-paper-engine-v1`,
PR #50, revisado sobre `ffbc800a5875f3fb72c4f6b3dbd7831ebdcc43d7`.

## Verificación

- `pytest -q`: 1498 passed, 20 skipped (línea base 1430/20 + 68 tests de T-025).
- `ruff check .`, `mypy advisor` (79 ficheros) y `mypy paper` (17 ficheros): limpios. La CI ejecuta `mypy paper`.
- `git diff --quiet 1a697c3 HEAD -- <EXECUTOR_PATHS>`: vacío (este PR no toca `advisor/` ni la configuración).
- Equivalencia del motor con `p6_sim.simulate` y `simulate_benchmark`: ledger, operaciones e instantáneas
  idénticos bit a bit en tres configuraciones (incluida una con cash escaso y desempate), avanzando por tramos.

## Criterios técnicos tomados (reversibles; ninguno cambia B2/S2/C0, reglas económicas, consumo, T-024 ni causalidad)

- Una transacción por avance de cohorte (más estricta que una por lote τ).
- Estado del motor en JSON canónico (sin `pickle`), en una caché verificada contra el `state_sha256`
  append-only de cada ejecución; si no cuadra, se reconstruye repitiendo la secuencia registrada.
- `run_seq` reservado al empezar (`paper_run_start`); corte de decisión registrado antes de los libros
  (`paper_run_decision`); una pasada ya completada no se repite.
- El límite de cada ejecución es la hora programada de su pasada (exclusiva) y una señal se entrega al motor
  solo cuando es la vinculante definitiva (D-50).
- Listas cerradas con tablas de referencia; migraciones aditivas; fallo cerrado ante valores desconocidos.

## Revisión independiente

- Codex: 2 BLOCKER, 4 IMPORTANTES, 1 MENOR. Corregidos todos salvo un BLOCKER **no aceptado**: «evaluar con
  observaciones posteriores a la hora programada es look-ahead». El pre-registro §7.1 (ronda 3) lo permite
  expresamente (`observed_at ≤ decision_ts` y `available_at ≤ analysis_timestamp`); el `revisor` coincide.
- `revisor`: 2 BLOCKER, 8 IMPORTANTES, 10 MENORES en la primera pasada; dos confirmaciones posteriores.
  **Resultado final: 0 BLOCKER, 0 IMPORTANTE.**
- **Split nunca publicado (antes MENOR abierto):** resuelto según §8.6 en `4d9ff37`/`083fa89` (bloqueo hasta un
  `SPLIT` observado) y, para el hueco real indistinguible, por **D-80** (abajo).
- Observaciones abiertas: `data_quality` fijo y sin ids de entrada en la evaluación; `policy_cohorts`
  indexado por política (una sola versión del motor en v1); `eligible_for_p7` no comprueba la frontera
  ordinaria de P7; la serie de benchmark no se filtra por `available_at` (igual que P6).

## D-80 — `REAL_GAP_CONFIRMED / NO_SPLIT` (2026-10-08)

Cierra el último IMPORTANTE del PR. Enmienda explícita de §8.6 registrada en `docs/decision-log.md` (D-80).

- Por defecto, sin cambios: cambio de escala ambiguo sin `SPLIT` → `SCALE_MISMATCH` → bloqueo →
  `DATA_LOSS_SUSPENDED` → `NO_EVALUABLE_DATA_LOSS`. Sin heurística.
- `paper_scale_resolution` (append-only, clave activo + sesión) y `register_real_gap` / `python -m paper
  real-gap-confirmed`: exige el `SCALE_MISMATCH` de esa sesión exacta, fuente, sha256 (hex) de la evidencia
  y `D-<n>`; nunca se infiere.
- Con la resolución, las barras bloqueadas son utilizables desde su `observed_at` (`usable_bars`), en
  ingesta, señales y motor. Las ya declaradas ausentes se recorren en la frontera (`CatchupBar`), en dos
  fases como el motor normal: en su apertura (split, dividendo, hueco) y en su cierre (toque intradía,
  tiempo), `late` y `late_processing` en ledger y eventos de posición; sin reescribir decisiones.
- Tests: `test_hueco_real_ambiguo_sin_resolucion_sigue_bloqueado_y_acaba_no_evaluable`,
  `test_real_gap_confirmed_libera_y_procesa_causalmente_las_barras_bloqueadas` (antes y después de la
  declaración), `test_split_real_no_publicado_no_se_libera_como_hueco_sin_resolucion_explicita` (incluye CLI y
  append-only) y, en el motor, frontera detenida por otro activo, toque intradía al cierre, split y dividendo
  con fecha ex en el catch-up.
- Revisión focalizada (`revisor`, tres pasadas): 1.ª 1 IMPORTANTE (catch-up por delante de la frontera) y
  3 MENORES; 2.ª 1 IMPORTANTE (mínimo y cierre usados en la apertura); todos corregidos. 3.ª: APROBADO,
  **0 BLOCKER, 0 IMPORTANTE** (observación: el dividendo del catch-up se abona en la apertura, no al cierre).
- Verificación: `pytest -q` 1511 passed, 20 skipped; `ruff check .`, `mypy advisor` y `mypy paper` limpios;
  EXECUTOR_PATHS de T-024 idénticos a `1a697c3`.
