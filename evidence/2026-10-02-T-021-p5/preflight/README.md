# T-021 / A-05, paso 2 — preflight definitivo de P5

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

- `P5_PREREG_SHA` = `a7c3d238d651b4ea8f48834848c03c0a5a462dfa` (ficha T-021 y D-66). No cambia.
- `P5_CODE_CANDIDATE_SHA` = `6c7f9135774f157e82634b6abf82a847d9b99bd9` (commit C). Es el ejecutor
  (`advisor/research/p5.py`, CLI `p5` y `tests/test_p5.py`) tras corregir la revisión independiente de
  look-ahead (I-1, I-2, M-1 a M-6), y es el commit sobre el que se generó este preflight con el árbol
  limpio.
- **Supersede** al candidato anterior `eaa7506` y a su evidencia `c027d56`, que se conservan en la
  historia de Git pero ya no son candidatos de ejecución. Las correcciones son de integridad del
  ejecutor: la metodología de D-66 no cambia, y los hashes de política, de diagnóstico, de rejilla y
  de niveles son idénticos a los de `c027d56`.
- **P5 no se ha ejecutado.** No existe `../run/` ni la marca `EJECUCION_CONFIRMATORIA_P5_INICIADA`.
  `new_p5_outcomes_read = false`; `p5_confirmatory_executed = false`. No se ha evaluado ningún vecino
  ni ningún LOCRO.

## Qué desenlaces se leyeron

Solo los de **C0, B2 y S2**, y solo para reproducir agregados que P4 ya publicó (OD-P5-16 y D-66). El
JSON lo declara en `outcomes_leidos = "solo C0/B2/S2, solo estimaciones ya publicadas en P4"`; el
resultado de la comparación está en `p4_reproduccion.p4_published_results_reproduced = true`.

- La guarda (`OutcomeGate`) solo autoriza, antes de la marca, esas tres geometrías, y además exige la
  celda canónica de la rejilla y que los niveles recibidos tengan el `levels_sha256` publicado por P4
  para esa celda. Toda estimación nueva (vecinos, LOCRO, regiones, concentración) exige un
  `ConfirmatoryToken` que solo es válido si la marca existe en su ruta y su sha256 coincide; tras la
  marca, cada vecino tiene que traer el `levels_sha256` que fija la marca.
- El JSON no contiene ningún evento, `net_R` ni `signal_id` por señal.

## Resultado

- `ok = true`, `definitivo = true`: **94/94 controles** (eran 61; los nuevos están en
  `controles.md`).
- **Población:** 101.251 señales, 90 activos, `population_sha256 = 78024050…3141`,
  `signal_ids_sha256 = 9faa4a45…629f`.
- **Reproducción de P4:** **162/162 cadenas iguales** en la lista blanca de B2 y S2. La fila
  `primaria_60` es la de Bonferroni (0,9875; 20.000). C0: `advisor_config_hash_ok`, 0 diferencias de
  niveles con el event study y 0 señales sin niveles, ahora como controles explícitos.
- **Condiciones de P4 congeladas antes de la marca:** las ocho de veto (1, 2, 3, 5, 6, 8, 9, 10),
  cumplidas en B2 y S2, con 4 y 7 descriptivas (`veta=False`, `cumple=N/D`). Están en
  `p4_reproduccion.condiciones_p4`, en la huella del preflight y en la marca; la confirmatoria ya no
  relee `criterio.tsv`.
- **Evidencia de P4 fijada por sha256** (`p4_evidencia_sha256`): `criterio.tsv`,
  `estimaciones.tsv`, `nivel.tsv`, `capacidad.tsv`, `emparejamiento.tsv`, `p4-preflight.json` y el
  inventario estructural de diseño. Se verifica sobre los mismos bytes que se leen.
- **Rejilla:** 2 centros, 13 vecinos (8 de B2 y 5 de S2), 3 ausencias de S2 por RR < 1,5,
  `m3_auxiliar` solo en las tres celdas de B2 con `target2 = 5,25`. Los 16 `levels_sha256` de las
  celdas válidas son distintos entre sí.
- **Hashes:** `policy_sha256` solo en C0, B2 y S2 canónicos; los 13 vecinos publican
  `diagnostico_sha256`; una celda no canónica lanza error.
- **LOCRO estructural:** sin USA 56.353 (mínimo 50.718 pares), sin EUROPA 66.629 (59.967), sin ASIA
  83.298 (74.969).
- **Recuento estructural:** B2 43 + S2 28 = **71**; confirmatorias nuevas **0**; acumulado con P4, 518.

## Recuento tras los desenlaces y celdas sin pares

Una celda NO_ESTIMABLE con pares conserva sus cinco estimaciones y el recuento derivado sigue en 71
(test `test_caso_a_no_estimable_con_pares_conserva_71`). Si en una celda no se pudiera formar
**ningún** par, no existiría su primaria y el recuento no daría 71: la ejecución se detiene con
`p5-parada.json`, **conserva la marca** y no inventa un resultado. Es inalcanzable en la práctica: los
13 vecinos tienen 101.251 niveles válidos, congelados y atados a la marca. No se modifica D-66 por ese
caso.

## Ficheros

| Fichero | Contenido |
|---|---|
| `p5-preflight.json` | Salida legible por máquina (`ok = true`, `definitivo = true`, 94/94 controles) |
| `p5-preflight.txt` | Resumen en formato humano |
| `consola-preflight.txt` | Salida literal de `python -m advisor.main p5 --fase preflight` y su código de salida |
| `controles.md` | Los 94 controles y los sha256 de la evidencia de P4 |
| `identidad.txt` | SHA, árbol limpio, pre-registro en la historia, `config.yaml` en `"1.0"` sin cambios, ficheros tocados, sin marca ni `run/` |
| `suite-ruff-mypy-pytest.txt` | ruff, mypy y la suite completa sobre `6c7f913` |
| `regresion-v1.txt` | Backtest `--vintage` normalizado: 866 operaciones, `49b12c85…` (igual que antes) |
| `reproduccion-p4.md` | Las 162 comparaciones de cadenas contra P4 y las condiciones congeladas |
| `hashes-configuraciones.md` | `advisor_config_hash`, `policy_sha256` / `diagnostico_sha256` por celda |
| `rejilla-semiplanos.md` | Rejilla con roles, ausencias, `m3_auxiliar`, `levels_sha256`, semiplanos y LOCRO estructural |
| `recuento.md` | Recuento estructural de comparaciones |
| `SHA256SUMS.txt` | Hash de cada artefacto de esta carpeta |

## Siguiente paso

Nueva vuelta de la revisión independiente de look-ahead sobre `6c7f913` y este preflight. Solo
después, y con una autorización nueva del propietario, la única `p5 --fase confirmatoria`.
