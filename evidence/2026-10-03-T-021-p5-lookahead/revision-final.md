# T-021 / P5 — Revisión independiente de look-ahead del ejecutor: informe final

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

**Esta revisión se hizo ANTES de la ejecución confirmatoria de P5.** En el momento de cerrarla (2026-10-03,
antes de las 09:37 UTC) P5 no se había ejecutado: no existía la marca
`evidence/2026-10-02-T-021-p5/run/EJECUCION_CONFIRMATORIA_P5_INICIADA` ni el directorio `run/`, y no se
había evaluado ningún vecino ni ningún LOCRO. Todos los ataques usaron datos sintéticos, funciones puras y
`tmp_path`; los únicos desenlaces reales leídos fueron los de C0, B2 y S2, para reproducir agregados ya
publicados por P4 en el preflight.

Revisores: Claude (Opus 5.5) y Codex, en revisión cruzada; los hallazgos de cada uno se reprodujeron antes
de aceptarlos.

## Identidad revisada

| | |
|---|---|
| `P5_PREREG_SHA` | `a7c3d238d651b4ea8f48834848c03c0a5a462dfa` (T-021 y D-66; sin cambios) |
| `P5_CODE_CANDIDATE_SHA` | `6c7f9135774f157e82634b6abf82a847d9b99bd9` (commit C: `advisor/research/p5.py`, `tests/test_p5.py`) |
| Evidencia del preflight | `7446602114b26f56cae549d2ec299d7bbc07b459` (commit D: solo `evidence/2026-10-02-T-021-p5/preflight/`) |
| Supersedidos | `eaa7506` (ejecutor) y `c027d56` (su preflight): se conservan en la historia, no son candidatos |
| C → D | ningún cambio ejecutable |

## Antecedente: primera vuelta (sobre `eaa7506` / `c027d56`)

Resultado: **0 BLOCKER, 2 IMPORTANTE → NO AUTORIZAR**.

- **I-1 (IMPORTANTE).** `evaluate_candidate` aceptaba mapas incompletos. Con un vecino omitido (cualquiera
  de los 8 de B2, o cualquiera de los dos críticos iso-RR de S2), una clase desconocida, un LOCRO omitido,
  vacío, con región extra o de otro centro, el veredicto salía ROBUSTA. La ruta real construía las
  estructuras completas y el recuento posterior la protegía, pero la función decisoria no.
- **I-2 (IMPORTANTE).** `centro_p4 = all(p4_conditions.values())` sobre el conjunto que llegara: con un
  mapa vacío o parcial, el centro pasaba.
- **M-1.** `build_confirmatory_token` quedaba fuera del `try`: un fallo tras la marca no dejaba
  `p5-parada.json`.
- **M-2.** La marca se escribía sin creación exclusiva: dos ejecuciones concurrentes podían abrir
  desenlaces.
- **M-3.** `criterio.tsv` de P4 se leía después de la marca y no estaba atado a la huella ni a la marca;
  la evidencia de P4 no tenía hash fijado.
- **M-4.** El hash de política dependía del rol suministrado, no de la celda canónica.
- **M-5.** La guarda comprobaba la celda pero no los niveles: `B2_CELL` con niveles de un vecino se
  evaluaba sin token.
- **M-6.** Los controles de C0 (hash de configuración e identidad con el event study) se calculaban pero
  no podían poner `ok = false`.
- **Observaciones:** symlink de la marca (requiere crear la marca); D-66 §17 dice «2.000 remuestreos»
  para `anchura_ic95`, que P4 calculó con 20.000 (P5 reproduce lo publicado); el orden real de las
  guardas era más estricto que el pedido.
- **NO_ESTIMABLE frente al recuento 71:** caso A. Una celda NO_ESTIMABLE con pares conserva sus 5
  estimaciones y el recuento sigue en 71. Solo una celda con 0 pares (inalcanzable con los 101.251
  niveles válidos congelados) daría STOP.

## Correcciones (commit C, sin cambio de metodología)

- **I-1:** `validate_candidate_inputs` exige que `set(neighbor_classes)` sea exactamente el conjunto de
  vecinos válidos del centro, con clases ∈ {ACEPTABLE, DÉBIL, CONTRARIA, NO_ESTIMABLE}. El LOCRO tiene que
  ser exactamente USA, EUROPA y ASIA, con `centro`, `sin_region`, `denominador` y `pares_minimos`
  canónicos. Se elimina el atajo de `locro_row`: `estimable := capacidad.ok` (booleano) e
  `ic_inferior := estimacion.ic_inferior`, que tiene que ser finito. Cualquier otra forma da error, nunca
  un veredicto.
- **I-2:** `set(p4_conditions) == EXPECTED_P4_VETO_CONDITIONS` = {P4_1, P4_2, P4_3, P4_5, P4_6, P4_8,
  P4_9, P4_10}, con valores booleanos; `centro_p4` exige `is True` en las ocho.
- **M-3:** `criterio.tsv` se valida en el preflight: condiciones 1–10 una vez cada una, las 8 de veto con
  `veta=True` y la 4 y la 7 con `veta=False` y `cumple=N/D`. Se congela en
  `p4_reproduccion.condiciones_p4`, en la huella y en la marca. La confirmatoria no lo vuelve a leer.
  `P4_EVIDENCE_SHA256` fija los cinco TSV de P4, `p4-preflight.json` y el inventario de diseño, y se
  verifica sobre los mismos bytes que se parsean.
- **M-5:** la guarda exige la celda canónica de `GRID` y que los niveles tengan su `levels_sha256`: los
  publicados por P4 antes de la marca, y los fijados por la marca después. La marca no puede cambiar los
  de C0, B2 ni S2. `estimate_neighbor` exige la guarda creada desde la marca.
- **M-4:** `canonical_cell`; `policy_sha256` solo para C0, B2 y S2 canónicos, `diagnostico_sha256` solo
  para vecinos canónicos, las ausencias sin hash, y cualquier celda incoherente da error. Los 16 hashes
  publicados son idénticos a los de `c027d56`.
- **M-6:** controles del preflight `C0 advisor_config_hash_ok`, `C0 niveles_event_study_diferencias = 0`
  y `C0 sin_niveles = 0`.
- **M-1 / M-2:** la marca se crea con `os.open(O_CREAT|O_EXCL)`; si ya existe, `P5AlreadyExecutedError`
  sin tocarla y sin parada. `run/` vacío se vuelve a comprobar justo antes. Desde la creación, todo va
  dentro de `try/except BaseException`: escribir la marca, construir el token, verificar niveles y
  desenlaces. Cualquier fallo escribe `p5-parada.json`, la marca permanece y P5 no se repite.
- **Celda sin pares:** documentada. Si alguna de las 71 estimaciones no pudiera existir, la ejecución se
  detiene y conserva la marca, sin inventar un resultado. D-66 no se modifica.

## Revisión final (sobre `6c7f913` / `7446602`)

**Resultado: 0 BLOCKER · 0 IMPORTANTE · 0 MENOR.**

| Hallazgo | Estado | Evidencia |
|---|---|---|
| I-1 | **CERRADO** | Se omitió cada uno de los 8 vecinos de B2 y los 2 críticos de S2; también mapa vacío, parcial, vecino extra, clase `XYZ`/`None`/vacía, LOCRO sin cada región, vacío, con región extra, de otro centro, con denominador o mínimo equivocados, atajo `estimable`, `nan`/`inf`/booleano. Todos dan `ValueError`; con el atajo, `capacidad.ok=False` manda (NO_CONCLUYENTE). |
| I-2 | **CERRADO** | Condiciones vacías, una sola, siete, nueve, con `P4_4`, o con un valor no booleano: `ValueError`. Cada una de las 8 en False da FRÁGIL. |
| M-1 | **CERRADO** | Un fallo del token tras la marca deja la marca y `p5-parada.json`, no abre ningún vecino, y la repetición se rechaza. Una interrupción deja la parada y se relanza. |
| M-2 | **CERRADO** | Solo una creación exclusiva gana. Si otra ejecución crea la marca durante el preflight, `P5AlreadyExecutedError`, la marca ajena intacta, sin parada y sin vecinos. Con dos ejecuciones simultáneas, solo una abre desenlaces. |
| M-3 | **CERRADO** | Las seis formas de alterar `criterio.tsv` dan error. Una evidencia de P4 modificada no se lee (sha256). `_center_evidence` no lee `criterio.tsv`. Las condiciones y los hashes están en la huella y en la marca. |
| M-4 | **CERRADO** | Geometría de vecino con rol CENTER, B2 con rol NEIGHBOR, vecino con id `B2` y celda inventada dan error. `policy_sha256` sobre un vecino da error. |
| M-5 | **CERRADO** | B2, S2 y C0 con niveles ajenos, una señal alterada y 4 celdas disfrazadas dan `P5OutcomeGateError`. Tras la marca, los hashes de C0, B2 y S2 no son sustituibles. |
| M-6 | **CERRADO** | Los tres controles de C0 forman parte de los 94 del preflight. |

Ataques repetidos expresamente:

1. omisión de vecinos → error;
2. omisión LOCRO → error;
3. condiciones P4 parciales → error;
4. B2/S2 con niveles ajenos → error;
5. dos ejecuciones simultáneas → solo una abre desenlaces;
6. evidencia de P4 modificada entre el preflight y la ejecución → error de sha256 antes de usarla;
7. fallo del token tras la marca → parada, marca conservada y sin repetición.

Codex, en la vuelta final y en solo lectura sobre `7446602`: «No he podido reabrir el look-ahead. 0
BLOCKER, 0 IMPORTANTE, 0 MENOR». Confirmó además que C→D no cambia código ejecutable y que la metodología
de D-66 no cambió.

## Verificación

- **Preflight definitivo sobre `6c7f913`:** `ok = true`, `definitivo = true`, **94/94 controles**,
  101.251 señales, 90 activos, 13 vecinos, 3 ausencias, 71 comparaciones, 0 confirmatorias, **P4
  reproducido 162/162 cadenas**, `new_p5_outcomes_read = false`, sin datos por señal en el JSON.
  `SHA256SUMS.txt` válido.
- `ruff check .` y `mypy advisor` (73 ficheros) sin errores.
- `pytest -q`: **967 passed** (eran 903).
- Regresión v1: `49b12c85…`, 866 operaciones.
- CI verde en Python 3.12 y 3.13 sobre `7446602`.
- La metodología de D-66 no cambia: rejilla, 13 vecinos, 3 ausencias, 75 %, NE ≤ 1, F1–F6, LOCRO y
  mínimos 50.718 / 59.967 / 74.969, 71, semilla 20260830, 2.000 remuestreos, IC95, 0 confirmatorias,
  `m3` auxiliar, ACEPTABLE/ROBUSTA, salida ⊆ {[], [B2], [S2], [B2, S2]}.
- Producción: `config.yaml` en `"1.0"`, Score v2 inactivo, Pi en `v0.4.1` = `8b2dddb` (comprobado por
  SSH en solo lectura).

## Conclusión

**EJECUTOR APTO PARA DECISIÓN DEL PROPIETARIO.** La revisión no autoriza por sí misma la ejecución; la
única `python -m advisor.main p5 --fase confirmatoria` la autoriza el propietario aparte, sobre el HEAD que
archiva este informe (`P5_RUN_HEAD_SHA`), con `P5_CODE_CANDIDATE_SHA = 6c7f913`.
