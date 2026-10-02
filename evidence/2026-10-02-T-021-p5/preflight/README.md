# T-021 / A-05, paso 2 — preflight definitivo de P5

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

- `P5_PREREG_SHA` = `a7c3d238d651b4ea8f48834848c03c0a5a462dfa` (ficha T-021 y D-66).
- `P5_CODE_CANDIDATE_SHA` = `eaa7506b69dbeec1fbc796e99273764e5bd523e4`. Es el commit del ejecutor
  (`advisor/research/p5.py`, CLI `p5` y `tests/test_p5.py`), sobre el que se generó este preflight con
  el árbol limpio. Pasará a ser `P5_CODE_SHA` solo si la revisión independiente de look-ahead del paso
  siguiente queda limpia.
- **P5 no se ha ejecutado.** No existe `../run/` ni la marca `EJECUCION_CONFIRMATORIA_P5_INICIADA`.
  `new_p5_outcomes_read = false`; `p5_confirmatory_executed = false`. No se ha evaluado ningún vecino
  ni ningún LOCRO.

## Qué desenlaces se leyeron

Solo los de **C0, B2 y S2**, y solo para reproducir agregados que P4 ya publicó (OD-P5-16 y D-66). El
JSON lo declara en `outcomes_leidos = "solo C0/B2/S2, solo estimaciones ya publicadas en P4"`; el
resultado de la comparación está en `p4_reproduccion.p4_published_results_reproduced = true`.

- La guarda (`OutcomeGate`) solo autoriza, antes de la marca, esas tres geometrías, comparando la
  geometría exacta y no el nombre. Toda estimación nueva (vecinos, LOCRO, regiones, concentración)
  exige un `ConfirmatoryToken` que solo es válido si la marca existe en su ruta y su sha256 coincide.
- El JSON no contiene ningún evento, `net_R` ni `signal_id` por señal.

## Resultado

- `ok = true`, `definitivo = true`: **61/61 controles**.
- **Población:** 101.251 señales, 90 activos, `population_sha256 = 78024050…3141`,
  `signal_ids_sha256 = 9faa4a45…629f`, regiones iguales al censo. Bloques: 60 → 20 ocupados (más corto
  42); 120 → 10 (102).
- **Reproducción de P4:** **162/162 cadenas iguales** en las filas y columnas de la lista blanca de
  B2 y S2 (`estimaciones.tsv`, `nivel.tsv`, `capacidad.tsv`, `emparejamiento.tsv`). La fila
  `primaria_60` es la de Bonferroni (0,9875; 20.000). De la capacidad solo se compara `anchura_ic95`.
  C0: `advisor_config_hash = 89406d28…6387`, 0 diferencias de niveles con la enumeración del event
  study y 0 señales sin niveles.
- **Rejilla:** 2 centros, 13 vecinos (8 de B2 y 5 de S2), 3 ausencias de S2 por RR < 1,5, `m3_auxiliar`
  solo en las tres celdas de B2 con `target2 = 5,25`. El inventario estructural de las 19 celdas
  coincide con el de diseño (`evidence/2026-10-02-T-021-p5-diseno/inventario-estructural.json`) y los
  `levels_sha256` de C0, B2 y S2 coinciden con los del preflight de P4.
- **Hashes:** `policy_sha256` solo en C0, B2 y S2; los 13 vecinos publican `diagnostico_sha256`.
- **LOCRO estructural:** sin USA 56.353 (mínimo 50.718 pares), sin EUROPA 66.629 (59.967), sin ASIA
  83.298 (74.969).
- **Recuento estructural:** B2 43 + S2 28 = **71**; confirmatorias nuevas **0**; acumulado con P4, 518.

## Ficheros

| Fichero | Contenido |
|---|---|
| `p5-preflight.json` | Salida legible por máquina (`ok = true`, `definitivo = true`, 61/61 controles) |
| `p5-preflight.txt` | Resumen en formato humano |
| `consola-preflight.txt` | Salida literal de `python -m advisor.main p5 --fase preflight` y su código de salida |
| `identidad.txt` | SHA, árbol limpio, pre-registro en la historia, `config.yaml` en `"1.0"` sin cambios, ficheros tocados, sin marca ni `run/` |
| `suite-ruff-mypy-pytest.txt` | ruff, mypy y la suite completa sobre `eaa7506` |
| `regresion-v1.txt` | Backtest `--vintage` normalizado: 866 operaciones, `49b12c85…` (igual que antes) |
| `reproduccion-p4.md` | Las 162 comparaciones de cadenas contra P4, una por fila |
| `hashes-configuraciones.md` | `advisor_config_hash`, `policy_sha256` / `diagnostico_sha256` por celda |
| `rejilla-semiplanos.md` | Rejilla con roles, ausencias, `m3_auxiliar`, semiplanos y LOCRO estructural |
| `recuento.md` | Recuento estructural de comparaciones |
| `SHA256SUMS.txt` | Hash de cada artefacto de esta carpeta |

## Siguiente paso

Revisión independiente de look-ahead del ejecutor (`eaa7506`) y de este preflight. Solo después, y con
una autorización nueva del propietario, la única `p5 --fase confirmatoria`.
