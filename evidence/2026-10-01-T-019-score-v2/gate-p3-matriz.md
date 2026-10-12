# Matriz provisional de GATE P3 (T-019, paso 4, 2026-10-01)

**GATE P3 NO está cruzado.** Esta matriz solo ordena la evidencia. El cruce se decide en el paso 5
de T-019, después de la revisión independiente final del look-ahead (requisito 5), que **no se ha
lanzado** en este paso.

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

| # | Requisito (`docs/gates.md`) | Estado | Evidencia |
|---|---|---|---|
| 1 | Dimensiones y pesos redefinidos con `score_model_version` nuevo; nada se mezcla sin etiqueta | **SATISFECHO** | D-46, D-59; `advisor/analysis/scoring.py` con `"2.0"` y `Score.score_model_version` (paso 2, `5953300`, `evidence/2026-09-30-T-019-paso2/`); `README.md`, sección «La puntuación» |
| 2 | Umbrales por horizonte con estado `calibrated` ligado a la versión | **SATISFECHO** | D-45 y **D-61**. Swing `calibrated: false` **por la regla**: los 5 candidatos fallan OPERAR, así que `min_score_operar` y `min_score_vigilar` son nulos (`resultado-p3.md`; `evidence/2026-09-30-T-019-paso3-p3/run/tablas/swing-candidatos.tsv` y `swing-familia-bonferroni.tsv`). Medio `calibrated: false` **por invalidez** (bloque parcial 102 ≤ 250). Intradía `calibrated: false` **sin laboratorio**. Contrato con las reglas 7 y 8 en `advisor/config.py` (paso 1) |
| 3 | Ordenación bajo el primario, por banda y por bloque, con veredicto | **SATISFECHO** | `evidence/2026-09-30-T-019-paso3-p3/run/p3-resultado.json`, `run/tablas/swing-quintiles.tsv`, `swing-bloque-x-quintil.tsv` y `swing-contrastes.tsv`; swing **NO CONCLUYENTE** (anchura 0,2440 > 0,20); medio con el veredicto forzado por invalidez; `resultado-p3.md`; comprobación a mano en `calculo-manual-delta-bloque.md` |
| 4 | Ablación por dimensión publicada | **SATISFECHO** | `run/tablas/swing-ablaciones.tsv` y `medio-ablaciones.tsv` (tres dimensiones, mismo procedimiento, sin selección); `resultado-p3.md` |
| 5 | Revisión independiente del look-ahead | **PENDIENTE PASO 5** | Revisión 1, previa a P3: `evidence/2026-09-30-T-019-paso2a-code/revision-look-ahead-previa.md`. Revisión 2, final: **pendiente**, en el paso 5 (`revision-look-ahead.md`) |

## Lo que la ficha pide además (criterios de aceptación) y dónde está

| Criterio | Evidencia |
|---|---|
| 6. Ablación y sesgo de universo | `run/tablas/swing-regiones.tsv`, `swing-activos.tsv`, `swing-intra-activo*.tsv` (y los de medio); resumidos en `resultado-p3.md` como descriptivos |
| 7. Impacto | `impacto.md` y `tablas/`; `contexto-h6.md`; `confianza.md` (cosecha del paso 2 y pasada local de producción, generada por `confianza_produccion.py`); clasificación operativa: «no aplica: Score v2 no dispone de umbrales calibrados» |
| Número comprobado a mano (SAP.DE) | `calculo-manual-sap.md` |
| Δ por bloque a mano | `calculo-manual-delta-bloque.md` |
| `hashes-de-tablas.txt` | este directorio |
| `final-pytest-ruff-mypy.txt` | este directorio |
| 9. Revisión de look-ahead en sus dos momentos | la primera está hecha; la segunda, **pendiente del paso 5** |

Nombres de fichero: la ficha preveía `p3-ordenacion-*.txt`, `p3-calibracion-swing.txt`,
`p3-ablacion-*.txt` y `p3-universo-*.txt`. El ejecutor congelado de P3 (`87309da`) publicó ese
mismo contenido en `p3-resultado.json` y `run/tablas/*.tsv`. No se regeneran con otro nombre
porque la evidencia de #33 es inmutable. `resultado-p3.md` los resume y verifica sus hashes.
