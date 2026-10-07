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
- **MENOR abierto, pendiente de decisión del propietario:** un split que el proveedor no publique nunca. Solo
  la barra del salto queda dudosa (para no esconder un hueco real, que es indistinguible); a las 5 sesiones se
  declara ausente y las barras siguientes, en la escala nueva, darían una salida con pérdida ficticia. §8.6
  trataría como ausentes todas las barras en otra escala; el código prioriza no esconder pérdidas reales. Si el
  propietario lo acepta, una D-nn lo declara; si no, se cambia el detector.
- Observaciones abiertas: `data_quality` fijo y sin ids de entrada en la evaluación; `policy_cohorts`
  indexado por política (una sola versión del motor en v1); `eligible_for_p7` no comprueba la frontera
  ordinaria de P7; la serie de benchmark no se filtra por `available_at` (igual que P6).
