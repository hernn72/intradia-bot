# GATE P3: matriz final (T-019, paso 5, 2026-10-01)

**GATE P3 CRUZADO (D-62), con el veredicto NO CONCLUYENTE.**

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

Antes de cruzarlo se comprobaron los cinco requisitos de `docs/gates.md` uno por uno, después de la
revisión independiente final (`revision-look-ahead.md`), que no encontró ningún BLOCKER ni ningún
IMPORTANTE.

El gate no exige un resultado favorable: «se exige que la respuesta sea inequívoca y esté
cuantificada. Si es NO CONCLUYENTE, P3 se cruza igualmente con la etiqueta».

| # | Requisito | Estado | Evidencia | Comprobado por la revisión final |
|---|---|---|---|---|
| 1 | Dimensiones y pesos redefinidos con `score_model_version` nuevo; nada se mezcla sin etiqueta | **SATISFECHO** | D-46 y D-59; `advisor/analysis/scoring.py` (`"2.0"`, sin cambios desde `5953300`); `evidence/2026-09-30-T-019-paso2/` | "2.0" en `Score` y `SignalObservation`; `score_band` rechaza lo que no sea v1; P3 exige "2.0" en cada registro |
| 2 | Umbrales por horizonte con `calibrated` ligado a la versión | **SATISFECHO** | D-45 y D-61. Swing: `calibrated: false` **por la regla**, porque los cinco candidatos (43,6 / 49,6 / 53,6 / 57,6 / 63,6) fallan las condiciones 2, 3 y 4 de OPERAR (`evidence/2026-09-30-T-019-paso3-p3/run/tablas/swing-candidatos.tsv` y `swing-familia-bonferroni.tsv`). Medio: `false` **por invalidez** (102 ≤ 250). Intradía: `false`, **sin laboratorio**. No hay umbrales v2 | Cortes y candidatos reproducidos sin desenlaces. El cargador rechaza activar "2.0" en cualquier configuración. No hay umbrales fabricados |
| 3 | Ordenación bajo el primario, por banda y por bloque, con veredicto | **SATISFECHO** | `run/p3-resultado.json`; `run/tablas/swing-{quintiles,bloque-x-quintil,contrastes}.tsv`; `evidence/2026-10-01-T-019-score-v2/resultado-p3.md` y `calculo-manual-delta-bloque.md`. Swing: Δ Q5−Q1 −0,2895 R [−0,4098, −0,1658], anchura 0,2440 > 0,20 → **NO CONCLUYENTE**. Medio: veredicto forzado por invalidez | IC95 reproducido; la media de los 19 Δ de bloque es igual al contraste; el veredicto sigue el orden pre-registrado; la orientación del contraste es correcta; el signo negativo es solo descriptivo |
| 4 | Ablación por dimensión publicada | **SATISFECHO** | `run/tablas/{swing,medio}-ablaciones.tsv`; `resultado-p3.md` | Tres ablaciones con cortes propios reproducidos. Son descriptivas y Score v2 no cambió |
| 5 | Revisión independiente del look-ahead | **SATISFECHO** | Revisión 1: `evidence/2026-09-30-T-019-paso2a-code/revision-look-ahead-previa.md`. Revisión 2: `revision-look-ahead.md`, del agente `revisor`, independiente de Codex y del supervisor | 0 casos de look-ahead y 0 diferencias de contexto sobre 183.427 señales; paridad R-CTX 48/48 en los cuatro caminos; hashes de #33 30/30 y 8/8 OK |

## Hallazgos de la revisión final y qué se hizo con cada uno

### M-1 (MENOR): faltaba la etiqueta de universo

- **Corregido** con una nota fechada en D-61. D-62, la fila A-03 del roadmap, el estado de la ficha
  y `docs/gates.md` ya llevan la etiqueta.
- **No se tocó** `evidence/2026-10-01-T-019-score-v2/calculo-manual-delta-bloque.md`. Es evidencia
  del paso 4, ya fusionada, y su sha256 está en `hashes-de-tablas.txt`; si se reescribiera, esa
  verificación de integridad dejaría de cuadrar.
- **Ese fichero queda cubierto por esta matriz.** Sus medias por bloque son de la población de P3 y
  están condicionadas al universo seleccionado en 2026, con el sesgo de supervivencia y de selección
  sin corregir.
- **Ninguna cifra cambia.**

### O-1 a O-5 (observaciones)

No requieren acción para este cierre. O-1 (el seguimiento toma la versión activa) y O-5 (la pasada
v2 aborta si el contexto no es calculable, que es D-60) solo importan si algún día se activa v2. Se
recogen en el handoff de la ficha.

## Lo que el cruce no cambia

- Score v2 **no se activa**. Producción sigue en v1 con 70/60 y `calibrated: false` (D-47), y
  `config.yaml` sigue en `"1.0"`.
- No hay release ni despliegue. La Pi sigue en `v0.4.1` = `8b2dddb`.
- **A-04 (P4) queda desbloqueada, pero no se inicia.** Trabajará sobre `score_signal` sin umbrales
  operativos nuevos.
- P3 no se repitió y no se repetirá.
