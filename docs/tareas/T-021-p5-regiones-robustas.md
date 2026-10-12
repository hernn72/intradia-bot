# T-021 — P5 Regiones robustas de parámetros: B2 y S2, con pre-registro (A-05)

Estado: **ACEPTADA — GATE P5 CRUZADO el 2026-10-03 (D-67 y D-68).** P5 se ejecutó **una sola
vez** el 2026-10-03.

**Identidad.**
- `P5_PREREG_SHA = a7c3d238d651b4ea8f48834848c03c0a5a462dfa`
- `P5_CODE_SHA = 6c7f9135774f157e82634b6abf82a847d9b99bd9`
- `P5_PREFLIGHT_HEAD = 7446602114b26f56cae549d2ec299d7bbc07b459`
- `P5_RUN_HEAD_SHA = 282b1ce991bb4567ff2ad41a28e00c9518662115`
- Evidencia `86ddd5baf8ceabe6e9d3747d645c7c99d719343c`

**Resultado (D-67):** **B2 ROBUSTA** y **S2 ROBUSTA**, con supervivientes **`[B2, S2]`**:
- 13/13 vecinos ACEPTABLES;
- 6/6 LOCRO con IC95 inferior > 0;
- 71/71 comparaciones, 0 confirmatorias nuevas;
- ninguna candidata FRÁGIL, DEPENDIENTE_DE_MERCADO ni NO_CONCLUYENTE.

Cierre y handoff en la sección «Cierre (2026-10-03)», al final. Lo que sigue a continuación es el
pre-registro tal como quedó fijado; no se reescribe.

---

Estado: **PRE-REGISTRO — OD-P5-1 a OD-P5-16 CERRADAS en D-66 (2026-10-02).** P5 **no se ha
ejecutado** y no se ha calculado ningún resultado (`net_R`, ΔR, PF, expectancy ni intervalo) de
ningún punto nuevo de ninguna superficie. Las recomendaciones de la ficha son ahora **reglas
vinculantes**: el propietario adoptó en D-66 todas las recomendadas, con las guardas reforzadas de
OD-P5-16. Las alternativas no elegidas se conservan como historial en la sección 33.

El candidato a **`P5_PREREG_SHA`** es el HEAD documental que quede después de la revisión final del
pre-registro y de sus correcciones, con 0 BLOCKER y 0 IMPORTANTE (sección «Revisión de la ficha»).
La implementación de `p5.py` necesita una autorización nueva.

**Base:** `main = 4eed281ba5f4f611f07de3755a79c0b4005062d8` (GATE P4 cruzado, D-65).

Las cifras de esta ficha son de cuatro tipos:
- **algebraicas**, derivadas de `advisor/analysis/levels.py`;
- **estructurales**, del inventario sin desenlaces de la sección 10.3
  (`evidence/2026-10-02-T-021-p5-diseno/`), que usa solo primitivas del instante de señal;
- **resultados de P4 ya publicados** (D-64), que se citan como exposición previa (sección 5) y nunca
  se recalculan aquí;
- **aproximaciones de diseño**, derivadas solo de los intervalos de P4 ya publicados (sección 23.4).

Agente: Claude (inventario y ficha), con Codex en revisión cruzada del diseño → revisión
independiente adversarial de la ficha → propietario (OD-P5-x) → implementación (Codex programa y
Claude supervisa) → revisión de look-ahead → una ejecución.
Línea / fase: Línea A, A-05 (P5).
Gate al que contribuye: **GATE P5** (es la tarea que lo cruza).
_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

---

## 1. Objetivo

P5 **no busca otra vez el máximo de rendimiento**. P4 ya seleccionó dos candidatas, B2 y S2. P5 debe
decidir, con reglas fijadas antes de medir, si cada una:
- **sobrevive sin cambiar su configuración**, porque está dentro de una región estable del espacio
  de parámetros; o
- **se descarta**, porque es un punto frágil, un pico aislado o depende de un solo mercado, o porque
  la evidencia no basta para decirlo.

**Principio vinculante: P5 prueba la robustez de B2 y S2; no busca sustitutos mejores.**
- Si B2 sobrevive, la política resultante es **B2 exacta**; si S2 sobrevive, **S2 exacta**.
- Ningún punto nuevo de la superficie es elegible para sustituir a B2 o a S2 (sección 27).
- **P5 puede terminar con cero candidatas**, y ese es un resultado válido.

## 2. Pregunta de robustez

> ¿B2 y S2 pertenecen a una región suficientemente estable del espacio (stop, objetivo 2), o son
> puntos frágiles, picos aislados o dependientes de un solo mercado?

Se separa en cinco preguntas, cada una con su instrumento:
- **A. Robustez local:** ¿el efecto del centro frente a C0 persiste cuando el stop y el objetivo 2 se
  perturban un paso de retícula? (secciones 23 y 24)
- **B. Continuidad:** ¿hay una vecindad contigua de puntos aceptables alrededor del centro, o el
  centro está aislado? (sección 23)
- **C. Anchura:** ¿qué fracción mínima de la vecindad se sostiene? (sección 23)
- **D. Magnitud e incertidumbre:** ¿los vecinos mantienen una señal positiva distinguible de cero, y
  no solo un signo? (sección 23)
- **E. Mercado:** ¿la ventaja del centro desaparece si se quita la región que más contribuye?
  (sección 19)

## 3. Dependencias y estado de partida

- **GATE P4 cruzado** (D-65). A-04 / T-020 ACEPTADA. P4 se ejecutó una sola vez y **no se repite**.
  - `P4_PREREG_SHA = 48b884722ef027e99857a4e65f9ab6b11da4758f`
  - `P4_CODE_SHA = 3df8230d7806dde4151b56501641a1524a3df9d8`
  - `P4_RUN_HEAD_SHA = c2c52b11c60bb8dfd08d8cb33d5f6f251e9bf2c0`
  - evidencia `cfa365d` en `evidence/2026-10-01-T-020-p4/run/` (inmutable)
- **P5 recibe de P4 exactamente** (D-64): C0 como control; B2 y S2 como candidatas, **sin
  preferencia entre ellas**. S1 está descartada. B1 es solo descriptiva. E1 fue NO CONCLUYENTE y no
  forma parte de P5.
- **Infraestructura que reutiliza:** la población y los niveles de `advisor/research/p4.py`, la
  réplica de geometrías (`replay_managed_population`), el estimador pareado y el bootstrap de P2.6
  (`advisor/research/uncertainty.py`, `bootstrap.py`) y los umbrales de capacidad de P2.5
  (`advisor/research/capacity.py`).
- **Decisiones vinculantes:** D-03 / INV-14 (estimador primario), D-06 (holgura), D-43 (el RR sigue
  siendo condición de ejecutabilidad), D-47 (producción en v1), D-62 y la regla 7 del protocolo (la
  cosecha está consumida: ninguna parte puede ser holdout), D-63 (heterogeneidad como bandera;
  desviación formal del protocolo sobre validación temporal) e INV-15.

## 4. Producción y lo que P5 no cambia

- Producción sigue con la geometría C0, Score v1, `score_model_version = "1.0"` y Score v2
  inactivo. La Pi sigue en `v0.4.1`.
- P5 **no** toca `config.yaml`, no despliega, no activa B2 ni S2, no toca la Pi y no hace release.
- P5 **no** toca Score v2, **no** usa el score para seleccionar la población ni recalibra 70/60.
- P5 **no adelanta P6** (sección 36): ni sizing, ni asignación de cartera, ni concurrencia, ni divisa
  de cartera, ni drawdown, CAGR, Sharpe o Sortino.

## 5. Exposición previa: B2 y S2 no son puntos ciegos

Esta ficha lo declara antes de medir nada:

1. **B2 y S2 fueron seleccionadas por P4 sobre esta misma cosecha.** Por tanto:
   - P5 es **desarrollo**;
   - las superficies son una **prueba de robustez local posterior a la selección**;
   - **no constituyen confirmación independiente**;
   - P5 no puede convertir un vecino en descubrimiento;
   - la validación independiente en el tiempo sigue siendo P7 / INV-15.
2. **Del centro ya se conoce casi todo lo que se le exige.** P4 publicó, para B2 y S2: la primaria
   con IC de Bonferroni, la sensibilidad de 120 sesiones, las dos mitades temporales, las cotas de
   ambigüedad, el nivel y el PF (D-64); y los estratos por región, régimen, volatilidad, activo y,
   en S2, base del stop (`evidence/2026-10-02-T-020-p4-cierre/`). En particular:
   - **regiones:** ASIA, EUROPA y USA tienen el IC95 entero por encima de 0 en B2 y en S2;
   - **activos:** B2 tiene 75 de 90 activos con ΔR puntual positivo; S2, 73 de 90.

   **Consecuencia:** toda condición de esta ficha que se aplique **solo al centro** está, en buena
   parte, decidida por cifras ya publicadas. Se declara así, como **reverificación no
   informativa**, y no como evidencia nueva (sección 26, columna «conocida»). La información nueva
   de P5 está en **los vecinos** y en el **leave-one-region-out**, que P4 no calculó.
3. **Puntos de la rejilla de P4 ya medidos que caen cerca de las superficies:**
   - **B1** (2,0; 3,5): ΔR +0,0206. Está en el eje de objetivo de B2, por debajo de su superficie
     (la fila más baja de B2 es 4,5) y **fuera** de la retícula de P5.
   - **C0** (2,0; 3,0): ΔR ≡ 0 por definición. Está en la recta iso-RR = 1,5 de S2, **un paso
     diagonal** (Δs = 0,25 y Δm2 = 0,375) por debajo del vecino diagonal inferior de S2 (2,25; 3,375).
   - **S1** (1,5; 2,25): ΔR −0,0411. Está en la misma recta iso-RR, dos pasos más a la izquierda.

   Por tanto, en la recta iso-RR de S2 ya se conoce la secuencia S1 < C0 < S2. El vecino
   (2,25; 3,375) cae **entre C0 y S2** y su ΔR frente a C0 se acerca mecánicamente a cero por
   cercanía al control. La sección 23.3 explica cómo la definición de «aceptable» evita que esa
   cercanía decida el veredicto.
4. **El mapa de la «MFE sin objetivo» de A-02** (stop 2·ATR) informa sobre dónde acaban los
   objetivos lejanos, y por tanto sobre la fila superior de B2. Se declara.
5. **Lo que no se ha mirado nunca:** ningún punto de las superficies distinto de B2 y S2 se ha medido
   como variante pareada sobre esta cosecha. La retícula se construyó **solo** con la geometría de
   P4 (sección 11.1), sin resultados de vecinos.

**Etiqueta obligatoria en toda conclusión futura de P5:** «condicionado al universo seleccionado en
2026 (sesgo de supervivencia y selección no corregido)».

## 6. Población

Se reutiliza **exactamente** la población de P4 (D-63, OD-P4-2 = C). No es una OD.

| | Valor |
|---|---|
| `data_vintage_id` | `071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841` |
| `universe_vintage_id` | `237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19` |
| Señales | **101.251** (swing, A-02 sin cripto) |
| Activos | **90** (USA 40, EUROPA 30, ASIA 16, GLOBAL 3, EMERGING_MARKETS 1) |
| `population_sha256` | `78024050f7081ad4e1dd5cefaefbfa1a1668ff5b1a2ced8c34e62b6501873141` |
| sha256 de los `signal_id` | `9faa4a45beaba3eb8dafabf7990906cd8c89e8e06ae2f25edec7839cd48e629f` |
| Señales por región | USA 44.898, EUROPA 34.622, ASIA 17.953, GLOBAL 2.627, EMERGING_MARKETS 1.151 |

- Sin cripto (D-51). Sin las exclusiones de contexto de P3 (D-52, D-55): las 7.157 señales con
  `NO_CALCULABLE_CONTEXT` siguen dentro.
- **Ningún score ni `classify()` selecciona señales.**
- **P5 es swing.** Medio queda fuera, por los mismos motivos que en P4 (D-63, OD-P4-8 = A): no hay
  capacidad y el dividendo no entra en el P&L del laboratorio.
- El inventario de la sección 10.3 reproduce el tamaño y el hash con la misma ruta que el preflight
  de P4. El preflight de P5 tendrá que reproducirlos; si no, **STOP**.

## 7. Control C0

**C0 = `atr_stop_multiple 2,0`; `target_atr_multiples [1,5; 3,0; 5,0]`; `target2_structural false`;
`entry_max_atr 0,75`; `min_rr 1,5`; regla de soporte E; coste 0,20 %; swing con `MAX_HOLD_BARS` 40.**

C0 es el control y la referencia de todos los ΔR. **No es candidata** y no puede ser salida de P5:
si ninguna candidata sobrevive, la salida es `[]` y C0 sigue en producción, como siempre.

## 8. Candidatas

| Id | `s` | `[m1, m2, m3]` | RR en P (vol.) | Holgura RR (vol.) | Holgura efectiva (vol.) | Recta que la define en P4 |
|---|---|---|---|---|---|---|
| **B2** | 2,0 | [1,5; **4,875**; 5,0] | 2,4375 | 0,75·A | **0,75·A (empate RR/técnica)** | saturación de holgura: `m2 = 1,5·s + 1,875` |
| **S2** | **2,5** | [1,5; **3,75**; 5,0] | 1,50 | 0 | **0** | iso-RR mínimo: `m2 = 1,5·s` |

P4 (D-64), copiado sin recalcular:
- **B2:** ΔR +0,0717; IC Bonferroni 98,75 % [+0,0061; +0,1356]; pares 101.226.
- **S2:** ΔR +0,0348; IC Bonferroni 98,75 % [+0,0076; +0,0597]; pares 101.225.

**Las dos son candidatas sin preferencia.** Que B2 tenga un ΔR mayor no la ordena por delante de S2.

## 9. Parámetros

### 9.1 Movibles (los dos ejes)

- **Eje 1:** `atr_stop_multiple` (`s`).
- **Eje 2:** `target2_atr_multiple` (`m2`, el segundo de `target_atr_multiples`).

### 9.2 Fijos

| Parámetro | Valor | Nota |
|---|---|---|
| `target1` (`m1`) | 1,5 | no interviene en ninguna salida simulada |
| `target3` (`m3`) | 5,0 | **excepción solo diagnóstica** en la fila `m2 = 5,25` de B2, según OD-P5-3 (sección 12) |
| `min_rr` | 1,5 | define la frontera de validez de S2 |
| `entry_max_atr` | 0,75 | |
| `target2_structural` | false | |
| Regla de soporte | E (`_SUPPORT_BUFFER_ATR = 0,25`) | |
| `lookback_bars` | 60 | |
| Coste | 0,20 % ida y vuelta | |
| Horizonte | swing, `MAX_HOLD_BARS = 40` | |
| Entrada del laboratorio | al cierre de la señal | como P4; la entrada a la apertura (E1) no forma parte de P5 |

Introducir el score, otra política de entrada, el objetivo estructural, otro RR mínimo, otro coste,
otra regla de soporte o `target1`/`target3` como dimensiones exigiría una OWNER_DECISION nueva. Esta
ficha no lo propone.

## 10. Inventario del espacio paramétrico

### 10.1 Álgebra (stop por volatilidad, sin desenlaces)

Con `P` el cierre de señal, `A` el ATR, `stop = P − s·A` y `target2 = P + m2·A`:

```
RR en P          = m2 / s
holgura RR       = (m2 − 1,5·s) / 2,5          [en ATR]
holgura efectiva = min(0,75, holgura RR)
manda la técnica si  m2 > 1,5·s + 1,875;  empate si  m2 = 1,5·s + 1,875
```

`target1` y `target3` **no intervienen en ningún desenlace** del laboratorio. Verificado en el
código y confirmado por Codex:
- `evaluate_managed_event` sale por stop, por `levels.target2` o por tiempo
  (`advisor/research/event_study.py:542`);
- `evaluate_potential_event` solo usa el stop (`event_study.py:618`);
- la ejecución calcula el RR contra `target2` (`advisor/analysis/execution.py:58`);
- el motor de backtest toma `levels.target2` como objetivo (`advisor/backtest/engine.py:201`) y solo
  guarda `target1`/`target3` en el registro;
- `target3` aparece en el informe, en el texto del agente y en la comprobación de coherencia de P4
  (`target2 < target3`, `advisor/research/p4.py:332`).

### 10.2 Fronteras de validez

| Frontera | Origen | Naturaleza |
|---|---|---|
| `m1 < m2 < m3` | validador de `LevelsConfig` (`advisor/config.py:100`) | **no económica**: `m3` no interviene en ningún desenlace |
| `m2 ≥ 1,5·s` (RR en P ≥ `min_rr`) | INV-01/02 y condición 6 de P4 | **económica**: por debajo, la señal de stop por volatilidad no es ejecutable al precio de señal (`P > entry_max`) |
| `stop > 0` | `compute_levels_from_inputs` | estructural; con ATR/P máximo 0,2654 en la población, solo actúa para `s ≥ 3,77` |

Una celda con `m2 < 1,5·s` **no devuelve `None`**: `compute_levels_from_inputs` devuelve niveles con
`entry_max < P`, que violan la condición 6 en todas las señales de stop por volatilidad y, además, en
las de stop por soporte poco ajustado (sección 10.3: 78.601–81.381 señales incoherentes, más que las
de volatilidad). Por eso esa frontera se detecta por coherencia, no por niveles nulos.

**Las dos candidatas están en un borde:**
- **S2 está exactamente sobre la frontera económica** `m2 = 1,5·s`. Cualquier aumento del stop con
  el objetivo fijo, o cualquier reducción del objetivo con el stop fijo, la cruza.
- **B2 está a 0,125·ATR de la frontera no económica** `m2 < m3 = 5,0`. A cualquier resolución
  razonable del objetivo (≥ 0,125), B2 no tiene ningún vecino superior en objetivo con `m3 = 5,0`.

### 10.3 Inventario estructural sin desenlaces

Script y salida en `evidence/2026-10-02-T-021-p5-diseno/` (`inventario_rejilla_p5.py`,
`inventario-estructural.json`, sha256 `c4959801…`). Enumera la población con `p4.build_population`
(la misma ruta del preflight de P4) con los tres evaluadores de desenlace sustituidos por funciones
que lanzan un error; calcula solo niveles desde las primitivas en t. Resultado:
- población 101.251 y hash `78024050…` reproducidos; `outcomes_read = false`;
- **ninguna celda de la rejilla tiene señales sin niveles** (`none = 0` en todas); ATR/P máximo
  0,2654;
- las tres celdas con `m2 < 1,5·s` violan la condición 6 en todas las señales de stop por volatilidad
  y en parte de las de soporte (78.601 a 81.381 señales);
- ningún vecino es degenerado frente a su centro.

| Celda (`s`; `m2`; `m3`) | Sup. | Validez | Stop por soporte | Stop = centro | Stop y obj. 2 = centro | Stop = C0 | Qué manda (RR / técnica / empate) | RR efectivo mín. |
|---|---|---|---|---|---|---|---|---|
| (1,75; 4,5; 5,0) | B2 | válida | 14.391 | 14.391 | 0 | 14.391 | 0 / 14.391 / 86.860 | 2,571 |
| (1,75; 4,875; 5,0) | B2 | válida | 14.391 | 14.391 | 14.391 | 14.391 | 0 / 101.251 / 0 | 2,786 |
| (1,75; 5,25; 5,625) | B2 | válida (`m3` aux.) | 14.391 | 14.391 | 0 | 14.391 | 0 / 101.251 / 0 | 3,000 |
| (2,0; 4,5; 5,0) | B2 | válida | 17.143 | 101.251 | 0 | 101.251 | 86.860 / 14.391 / 0 | 2,250 |
| **(2,0; 4,875; 5,0) = B2** | B2 | centro | 17.143 | — | — | 101.251 | 0 / 17.143 / 84.108 | 2,4375 |
| (2,0; 5,25; 5,625) | B2 | válida (`m3` aux.) | 17.143 | 101.251 | 0 | 101.251 | 0 / 101.251 / 0 | 2,625 |
| (2,25; 4,5; 5,0) | B2 | válida | 19.869 | 17.149 | 0 | 17.149 | 86.860 / 14.391 / 0 | 2,000 |
| (2,25; 4,875; 5,0) | B2 | válida | 19.869 | 17.149 | 17.149 | 17.149 | 84.102 / 17.143 / 6 | 2,167 |
| (2,25; 5,25; 5,625) | B2 | válida (`m3` aux.) | 19.869 | 17.149 | 0 | 17.149 | 0 / 19.869 / 81.382 | 2,333 |
| (2,25; 3,375; 5,0) | S2 | válida | 19.869 | 19.870 | 0 | 17.149 | 94.603 / 6.648 / 0 | 1,500 |
| (2,25; 3,75; 5,0) | S2 | válida | 19.869 | 19.870 | 19.870 | 17.149 | 92.148 / 9.103 / 0 | 1,667 |
| (2,25; 4,125; 5,0) | S2 | válida | 19.869 | 19.870 | 0 | 17.149 | 89.582 / 11.669 / 0 | 1,833 |
| (2,5; 3,375; 5,0) | S2 | **inválida** (RR < 1,5) | 22.650 | 101.251 | 0 | 17.149 | 81.381 señales incoherentes | 1,350 |
| **(2,5; 3,75; 5,0) = S2** | S2 | centro | 22.650 | — | — | 17.149 | 92.148 / 9.103 / 0 | 1,500 |
| (2,5; 4,125; 5,0) | S2 | válida | 22.650 | 101.251 | 0 | 17.149 | 89.582 / 11.669 / 0 | 1,650 |
| (2,75; 3,375; 5,0) | S2 | **inválida** (RR < 1,5) | 25.418 | 22.650 | 0 | 17.149 | 81.381 señales incoherentes | 1,227 |
| (2,75; 3,75; 5,0) | S2 | **inválida** (RR < 1,5) | 25.418 | 22.650 | 22.650 | 17.149 | 78.601 señales incoherentes | 1,364 |
| (2,75; 4,125; 5,0) | S2 | válida | 25.418 | 22.650 | 0 | 17.149 | 89.582 / 11.669 / 0 | 1,500 |

Lecturas estructurales, sin desenlaces:
- **Fracción degenerada máxima:** los vecinos que solo cambian `s` comparten stop y objetivo 2 con
  el centro en las señales de soporte: el 14,2 % en (1,75; 4,875), el 16,9 % en (2,25; 4,875) y el
  19,6 % en (2,25; 3,75). En esas señales el par vecino–centro es idéntico. Se publica por celda
  (sección 14) y no excluye ninguna señal.
- **El paso de 0,25 en el stop no queda absorbido por la regla de soporte:** respecto a su centro,
  mueve el stop de entre 78.601 y 86.860 señales (del 78 al 86 %; las de stop por volatilidad en los
  dos brazos). Ver la sección 11.2.
- **La diagonal de cada superficie es la recta con la que P4 construyó su centro.** En B2, (1,75;
  4,5), B2 y (2,25; 5,25) están sobre la recta de saturación de la holgura: las tres empatan RR y
  técnica en todas las señales de stop por volatilidad. En S2, (2,25; 3,375), S2 y (2,75; 4,125)
  están sobre la recta iso-RR = 1,5.

## 11. Superficies y rejilla exacta (OD-P5-1, OD-P5-2, OD-P5-5)

### 11.1 Retícula común

- **Paso de stop:** `Δs = 0,25·ATR`.
- **Paso de objetivo 2:** `Δm2 = 0,375·ATR = 1,5·Δs`. Se elige así para que **las rectas iso-RR =
  1,5 pasen por nodos** de la retícula y la familia de S2 sea representable.
- **Origen:** C0 (2,0; 3,0). B2 (2,0; 3,0 + 5·0,375 = 4,875) y S2 (2,0 + 2·0,25; 3,0 + 2·0,375 =
  3,75) caen exactamente en nodos. **Ningún valor de la retícula se eligió mirando un resultado**:
  se deduce de C0, B2, S2 y de la frontera `min_rr`.
- Todos los valores son múltiplos de 1/8: se representan exactamente en binario, sin ambigüedad de
  redondeo en la configuración ni en el hash.

### 11.2 Por qué 0,25 y no 0,5 (respuesta al BLOCKER de Codex)

T-020 §7 justificó que ±0,5·ATR era «el paso simétrico más pequeño alrededor de 2,0 que no se
confunde con el ruido de la holgura del soporte (0,25·A)». Esa justificación servía para **comparar
políticas distinguibles** en P4. P5 hace otra cosa: **perturbar** un punto ya elegido para ver si se
rompe. Esta ficha lo declara así:
- **P5 es una prueba de sensibilidad local a escala inferior a la de P4**, no una rejilla de
  políticas a la misma escala. La escala de P4 (0,5) es la distancia entre candidatas; la de P5
  (0,25) es la mitad, el «ligeramente» de la pregunta A.
- **El argumento de P4 no impide medir a 0,25.** El inventario muestra que un paso de 0,25 mueve el
  stop en el 78–86 % de las señales (las de volatilidad en los dos brazos) y solo coincide con el
  centro en las señales de soporte (14–22 %). La perturbación es real, no ruido de la regla E.
- **0,5 no es viable alrededor de S2:** en la recta iso-RR, el vecino inferior a 0,5 es **C0 mismo**
  (2,0; 3,0), con ΔR ≡ 0 por definición. Un vecino que es el control no informa de nada. Y el
  superior, (3,0; 4,5), queda a un paso de P4 de S2 y a dos de C0. Además, por la regla F1 (sección
  24), un vecino con ΔR ≡ 0 es CONTRARIO: a esa escala **S2 saldría FRÁGIL por construcción**,
  salvo una regla adicional que excluyera C0.
- **0,125 sería ruido:** 0,125·ATR de stop es la mitad de la holgura de soporte y, con el ATR/P
  típico de la población (cortes de terciles 1,98 % y 3,06 %), entre el 0,25 % y el 0,4 % del
  precio, del orden del coste ida y vuelta (0,20 %). Los vecinos
  serían casi idénticos al centro y la robustez quedaría casi garantizada de antemano.

La alternativa de escala de P4 se conserva en OD-P5-2 (B) con su consecuencia.

### 11.3 Superficie de B2 (3×3, centro en el medio)

| `m2` \ `s` | 1,75 | **2,0** | 2,25 |
|---|---|---|---|
| **5,25** (`m3` = 5,625, aux.) | válida | válida | válida |
| **4,875** | válida | **B2** | válida |
| **4,5** | válida | válida | válida |

Con OD-P5-3 = C: **8 vecinos válidos**. Con OD-P5-3 = A: la fila 5,25 es inválida y quedan 5.

### 11.4 Superficie de S2 (3×3, centro en el medio)

| `m2` \ `s` | 2,25 | **2,5** | 2,75 |
|---|---|---|---|
| **4,125** | válida | válida | válida (iso-RR) |
| **3,75** | válida | **S2** | inválida (RR 1,364) |
| **3,375** | válida (iso-RR) | inválida (RR 1,35) | inválida (RR 1,227) |

**5 vecinos válidos y 3 ausencias estructurales**, con cualquier opción de OD-P5-3.

### 11.5 Recuento de puntos

| | Celdas totales | Centros | Vecinos válidos | Inválidos |
|---|---|---|---|---|
| B2 (OD-P5-3 = C) | 9 | 1 | **8** | 0 |
| B2 (OD-P5-3 = A) | 9 | 1 | 5 | 3 (`m2 = 5,25 ≥ m3`) |
| S2 | 9 | 1 | **5** | 3 (RR < 1,5) |
| **Total (D-66, OD-P5-3 = C)** | **18** | **2** | **13** | **3** |

- **Puntos coincidentes entre las dos superficies: ninguno.** Las dos comparten la columna `s =
  2,25`, pero con objetivos distintos ({4,5; 4,875; 5,25} en B2 y {3,375; 3,75; 4,125} en S2).
- **Configuraciones únicas a evaluar:** 13 vecinos nuevos + 2 centros (reproducción de P4) + C0 =
  **16** con D-66 (habrían sido 13 con OD-P5-3 = A, que no se eligió).
- Ningún punto de la rejilla coincide con B1, S1 ni C0.

### 11.6 Vecindad (OD-P5-5)

**Vecindad de 8** (los 8 nodos que rodean al centro). Con 4 vecinos, los vecinos de la recta que
define cada candidata (las diagonales de la sección 10.3) quedarían fuera, y S2 tendría solo 2
vecinos válidos de 4 —(2,25; 3,75) y (2,5; 4,125)—, sin ninguno en la dirección «stop más ancho».

**Semiplanos.** Para leer la estabilidad por eje, los vecinos válidos de cada centro X se agrupan en
cuatro semiplanos (un vecino diagonal pertenece a dos):

| Semiplano | B2 (OD-P5-3 = C) | S2 |
|---|---|---|
| `s−` (stop más estrecho) | (1,75; 4,5), (1,75; 4,875), (1,75; 5,25) | (2,25; 3,375), (2,25; 3,75), (2,25; 4,125) |
| `s+` (stop más ancho) | (2,25; 4,5), (2,25; 4,875), (2,25; 5,25) | (2,75; 4,125) |
| `m2−` (objetivo más cercano) | (1,75; 4,5), (2,0; 4,5), (2,25; 4,5) | (2,25; 3,375) |
| `m2+` (objetivo más lejano) | (1,75; 5,25), (2,0; 5,25), (2,25; 5,25) | (2,25; 4,125), (2,5; 4,125), (2,75; 4,125) |

**Asimetría declarada (IMPORTANTE de Codex).** En S2, los semiplanos `s+` y `m2−` tienen **un solo
vecino válido**, el de la recta iso-RR, por la frontera económica. Ese vecino decide solo su
semiplano. No es un castigo por vecinos imposibles: las ausencias estructurales no cuentan como
buenas ni como malas. Es la consecuencia de que S2 esté sobre la frontera `min_rr`, y se declara
antes de medir. B2 tiene tres vecinos por semiplano. **La tolerancia efectiva no es la misma**
(corregido tras la revisión independiente, I-1):
- **B2:** admite hasta 2 vecinos DÉBILES en cualquier posición; con tres vecinos por semiplano, dos
  fallos no pueden vaciar ninguno.
- **S2:** sus dos vecinos iso-RR, (2,25; 3,375) y (2,75; 4,125), **tienen que ser ACEPTABLES** (cada
  uno es el único de su semiplano), y de los otros tres puede fallar como mucho uno.
- En las dos, un vecino CONTRARIO veta (F1).

La probabilidad aproximada de cumplir la regla de la meseta, por candidata, está en la sección 23.4.

## 12. Tratamiento de las fronteras (OD-P5-3)

### 12.1 Frontera económica (`min_rr`, afecta a S2): truncar

Las celdas con `m2 < 1,5·s` no son políticas: violan INV-01/02 y la condición 6 de P4. Se publican
como **AUSENCIA_ESTRUCTURAL**, no se estiman y no entran en ningún denominador. No hay alternativa
razonable: ampliar la superficie por debajo de `min_rr` exigiría cambiar `min_rr`, que esta ficha no
mueve (sección 9.2).

### 12.2 Frontera no económica (`m3`, afecta a B2): C restringida (D-66)

- **A — truncar en `m2 < 5,0`.** B2 se queda sin semiplano `m2+`. Entonces la ficha tendría que
  elegir entre dos cosas que la sección 22 de la orden prohíbe: o B2 puede ser ROBUSTA con un lado
  entero sin evaluar, o no puede serlo por culpa de vecinos imposibles. **El inventario demuestra que
  A impide evaluar la robustez de B2 de forma simétrica**: con `Δm2 = 0,375` no cabe ningún vecino
  en (4,875; 5,0), y uno a 0,0625 sería ruido (sección 11.2).
- **B — reparametrizar** por (stop, holgura) o (stop, RR). **No resuelve el borde**: en cualquier
  coordenada, «objetivo más lejano que 4,875 con stop 2,0» necesita `m2 ≥ 5,0`. Además, en la
  coordenada (stop, holgura) el vecino «stop más ancho a igual holgura» de B2 sería (2,25; 5,25), que
  tropieza con el mismo validador.
- **C — `m3` auxiliar solo en celdas diagnósticas.** En la fila `m2 = 5,25` de B2, `m3 = 5,625`
  (el nodo siguiente de la retícula). En todas las demás celdas, `m3 = 5,0`.
  - **B2 conserva su configuración exacta**, con `m3 = 5,0`. Ningún vecino es elegible (sección 27),
    así que ninguna configuración con `m3 ≠ 5,0` puede salir de P5.
  - **`m3` no interviene en ningún desenlace del laboratorio** (sección 10.1). La única diferencia
    de esas tres celdas con una hipotética celda «`m3 = 5,0`» es que el validador las acepta.
  - **Limitación declarada (Codex):** `target3` sí forma parte de la configuración completa (se
    muestra en el informe y en los textos). Por eso C es un **recurso diagnóstico**, no una
    equivalencia de configuración. Las tres celdas llevan la marca `m3_auxiliar = true` en toda
    salida, y su hash incluye `m3 = 5,625` (sección 28).
  - **Test obligatorio** (sección 34): con barras sintéticas, el `ManagedEvent` de una geometría es
    idéntico con `m3 = 5,0` y con `m3 = 5,625` cuando `m2 < 5,0`.

**Decisión (D-66): C restringida para `m3`, y truncar en la frontera `min_rr`.**

## 13. Métrica primaria

Mismo instrumento causal que P4 (INV-14 / D-03, P2.6):

```
ΔR_c,i = net_R_c,i − net_R_C0,i        por el mismo signal_id
```

1. ΔR por señal frente a **C0** (no frente al centro);
2. media de ΔR dentro de cada **bloque completo de 60 sesiones** (todas las señales de todos los
   activos de esa ventana);
3. **estimación = media simple de las medias de bloque**;
4. **IC del 95 %** por bootstrap de bloques completos, 2.000 remuestreos, semilla 20260830
   (sección 16).

Se mide contra C0, y no contra el centro, porque la pregunta de P5 es si **la ventaja sobre el
control** sobrevive a la perturbación. La retención relativa al centro se publica aparte
(`ΔR_c / ΔR_X`, descriptiva, sección 14).

**P5 no escoge celdas por el máximo ΔR.** Ningún ΔR de un vecino cambia la candidata; solo puede
quitarla.

## 14. Secundarias por celda (descriptivas)

Para cada vecino válido, con el mismo estimador. Las que llevan IC cuentan como comparación
(sección 29):
- **con IC95:** sensibilidad de 120 sesiones; cota de ambigüedad conservadora; cota favorable;
  nivel (media por bloque de `net_R` de la celda);
- **puntuales, sin IC (no cuentan):**
  - mitades temporales internas (bloques 2–11 y 12–21);
  - retención `ΔR_c / ΔR_X`;
  - media agrupada de ΔR y PF agrupado de la celda;
  - `P(objetivo antes que stop)` como intervalo `[seguros; seguros + ambiguos]`;
  - tasas de salida por tiempo y `EXIT_FINAL`;
  - bandera de heterogeneidad (sección 21);
  - pares usados y descartes por ambigüedad (solo en C0, solo en la celda, en los dos);
  - fracciones estructurales de la sección 10.3: stop igual al centro, stop y objetivo iguales al
    centro, stop igual a C0, y qué manda en `entry_max`;
  - holgura D-06 de la celda (sin desenlaces, en el preflight).

## 15. Capacidad y clases de celda (OD-P5-15)

Se reutilizan los umbrales de P4 (condiciones 3 y 9, `CapacityThresholds` vigentes). Una celda es
**ESTIMABLE** si en el bloque de 60:
- ≥ 12 bloques con pares (`limited_blocks`);
- ningún bloque con < 5 pares (`min_observations_per_block`);
- descarte por ambigüedad ≤ 25 % (`max_ambiguous_rate`);
- `EXIT_FINAL` ≤ 10 % en C0 y en la celda (`max_exit_final_rate`);
- anchura del IC95 de ΔR ≤ 0,20 (`limited_interval_width`);
- pares ≥ 90 % de las señales de su población: 91.126 de 101.251 en las celdas (y en el LOCRO, el
  90 % de la población sin la región, sección 19.2).

Clases (mutuamente excluyentes):

| Clase | Definición |
|---|---|
| **AUSENCIA_ESTRUCTURAL** | celda inválida por la frontera `min_rr` (o por `m3`, si OD-P5-3 = A). No se estima ni cuenta |
| **NO_ESTIMABLE** | falla alguna condición de capacidad. **No cuenta como vecino malo** ni como bueno |
| **ACEPTABLE** | estimable y, a la vez: IC95 inferior de ΔR > 0; cota conservadora de ambigüedad (puntual) > 0; nivel de la celda (puntual) > 0; PF agrupado de la celda > 1 |
| **DÉBIL** | estimable, ΔR puntual > 0, pero no ACEPTABLE |
| **CONTRARIA** | estimable y ΔR puntual ≤ 0 |

**Población de cada métrica** (Codex, I-2), para que nadie la decida al implementar:
- **ΔR, su IC y CONTRARIA** se evalúan con la primaria (`media_delta_r` de la longitud 60) sobre los
  **pares finales** de `pair_populations`: señales con `net_R` observable en C0 y en la celda.
- **Nivel y PF** de la celda se calculan como en `level_estimate` (`advisor/research/p4.py:1070`):
  sobre **todos los eventos observables de la celda** (excluyendo solo `net_R is None`), no sobre el
  subconjunto pareado. Es la misma definición de la condición 10 de P4.
- **Cota conservadora:** `ambiguity_bound_deltas` (`p4.py:1031`), con la misma población que P4.

## 16. Bloques y bootstrap

Contrato de P4 y P2.6, sin cambios:

| Elemento | Valor |
|---|---|
| Longitud primaria | **60** sesiones: 20 bloques ocupados (2 a 21), bloque más corto 42 |
| Sensibilidad | **120** sesiones: 10 bloques, el más corto 102; descriptiva en los vecinos |
| 40 y 80 | inválidas (bloque más corto 22 ≤ 40). **P5 no las calcula** |
| Unidad | bloque temporal completo con reemplazo |
| Semilla | **20260830** (`seed_ci = seed·1.000.003 + 97`, `seed_het = seed·1.000.003 + 194`) |
| Remuestreos | **2.000**, nivel 0,95, cuantiles |
| Bonferroni | **ninguno nuevo** (sección 22). Los 20.000 remuestreos de P4 solo se usan para reproducir los intervalos de B2 y S2 |
| Mapa de bloques | el de la población completa, también en el leave-one-region-out (los bloques sin pares salen de `n_blocks` y se publican) |

## 17. Robustez temporal interna (OD-P5-11)

P5 **no constituye validación temporal**: la cosecha está consumida (D-62, regla 7). Se mantiene la
desviación formal del protocolo que registró D-63. No se crea ninguna partición nueva.

Decisión (D-66, OD-P5-11 = A):
- **Centro:** las dos mitades (bloques 2–11 y 12–21) con media de ΔR > 0, y la sensibilidad de 120
  con ΔR > 0 y IC95 inferior > 0, **son veto**. Son los valores de P4 (D-64), que el preflight de P5
  reproduce. Ya se sabe que pasan: es reverificación no informativa (sección 5).
- **Vecinos:** la sensibilidad de 120 (con IC95) y las mitades (puntos) se **publican y no vetan**.
  No forman parte de ACEPTABLE.

Nunca se llama «validación» a ninguna de estas divisiones.

## 18. Ambigüedad intrabarra (OD-P5-12)

Contrato de P4 (sección 17 de T-020): `AMBIGUOUS` es un estado y no se resuelve en la primaria. Los
pares con una salida ambigua en cualquiera de los dos brazos salen del par primario, y se publica
cuántos salen solo por C0, solo por la celda o por los dos.

Por celda se calculan las dos cotas envolventes con el mismo estimador:
- **conservadora para la celda:** sus ambiguas salen por stop y las de C0 por objetivo;
- **favorable para la celda:** al revés.

Decisión (D-66, OD-P5-12 = A): **la cota conservadora (puntual) > 0 forma parte de ACEPTABLE**; la favorable se
publica. Ninguna resolución se elige después. En el centro vale la cota de P4, reproducida.

## 19. Mercado, región y leave-one-region-out (OD-P5-7, OD-P5-8)

### 19.1 Qué es «mercado»

**Decisión (D-66, OD-P5-7 = A): la región económica del activo** (`Asset.region`, `advisor/universe/models.py`),
con las regiones núcleo **USA, EUROPA y ASIA** como unidad decisoria.

Motivos:
- es la unidad ya pre-registrada y publicada en P4;
- **la plaza no mide exposición:** de los 16 activos ASIA, 5 cotizan en XETRA y 2 en NYSE; de los 40
  USA, 3 cotizan en XETRA (inventario de la población). Usar la plaza mezclaría la exposición
  económica con el sitio donde se compra;
- el universo no tiene un campo de país;
- **GLOBAL** (3 activos, 2.627 señales) y **EMERGING_MARKETS** (1 activo, 1.151 señales) suman el
  3,7 % de las señales. EMERGING_MARKETS es un solo activo, ya rotulado así en P4 (OD-P4-11, O-3).
  Quitarlas no prueba nada sobre la dependencia de un mercado, y estimarlas por separado no tiene
  potencia.

### 19.2 Leave-one-core-region-out (LOCRO)

Para cada centro X ∈ {B2, S2} y cada región núcleo r ∈ {USA, EUROPA, ASIA}, se recalcula la
primaria de X frente a C0 **sobre la población sin la región r**. GLOBAL y EMERGING_MARKETS se
quedan siempre. Codex señaló que no es un leave-one-out literal sobre las cinco regiones del
repositorio, y por eso se llama **LOCRO** en toda salida.

- **Condición obligatoria:** sí, para los centros (es la que materializa el requisito del gate sobre
  la dependencia de un solo mercado).
- **Pasa** si, para las tres r, la población sin r es estimable **y** su IC95 inferior de ΔR es > 0.
- **Capacidad del LOCRO** (corregido tras la revisión independiente, BLOCKER B-1). Las condiciones
  de la sección 15, con la de pares **relativa a la población sin r**. Con el denominador absoluto
  (91.126 de 101.251), ninguna población LOCRO podría ser estimable y la salida `[]` quedaría
  decidida por el texto. Denominadores y umbrales, fijados ahora desde el censo:

  | Población | Señales | Pares mínimos (⌈0,9·n⌉) |
  |---|---|---|
  | sin USA | 56.353 | 50.718 |
  | sin EUROPA | 66.629 | 59.967 |
  | sin ASIA | 83.298 | 74.969 |

- **Contrato operativo** (Codex, I-1): `ids_r = {señales con región ≠ r}`; se filtran **los dos
  brazos** (C0 y X) a `ids_r` antes de `pair_populations`, que exige los mismos `signal_id`;
  `bootstrap_block_delta` recibe la espina completa de la población (`population.spine`). `n_blocks`
  cuenta los bloques con pares, y se publican, contra los 20 bloques ocupados de la población
  completa, los que quedan sin pares.
- **Falla** (DEPENDIENTE_DE_MERCADO) si alguna estimable tiene IC95 inferior ≤ 0.
- **NO_CONCLUYENTE** si alguna no es estimable.
- Se usa el IC95 (no solo el punto), con la misma regla de incertidumbre que ACEPTABLE.
- **Los vecinos no tienen LOCRO.** Solo B2 y S2 pueden ser candidatas, y el gate habla de las
  configuraciones candidatas. Calcularlo en los vecinos añadiría 39 comparaciones sin decidir nada.
- Las estimaciones por región sola de B2 y S2 ya están publicadas en P4 y se citan, sin recalcular.

**Exposición:** los estratos regionales de B2 y S2 en P4 tienen el IC95 entero por encima de 0 en
las tres regiones núcleo, así que el LOCRO del centro es **poco informativo** y probablemente pase.
Se mantiene porque el gate lo exige y porque P4 no lo calculó.

**El LOCRO no es la bandera de heterogeneidad** (observación de Codex): mide si la ventaja
desaparece al quitar una región, no la dispersión entre bloques. ALTA sigue sin vetar.

## 20. Activos y concentración (OD-P5-9)

**Decisión (D-66, OD-P5-9 = A): descriptiva, sin veto.** P4 ya publicó los 90 ΔR por activo de B2 y de S2, así que
cualquier umbral fijado ahora se fijaría conociendo los datos.

Se publica para B2 y S2 (puntos, sin IC; no cuentan):
- número de activos con media agrupada de ΔR > 0 y < 0;
- distribución por activo (p10, p25, p50, p75, p90);
- **mayor contribución individual** = `max_a Σ_{i∈a} ΔR_i / Σ_i ΔR_i` (sobre los pares de la
  primaria);
- **participación de los 5 y de los 10 activos que más contribuyen** en `Σ_i ΔR_i`.

Si `Σ_i ΔR_i ≤ 0`, las participaciones no se definen y se publica así. No se crea ninguna regla a
partir de los activos que salgan.

## 21. Heterogeneidad (OD-P5-10)

**Decisión (D-66, OD-P5-10 = A): no reparar el instrumento dentro de P5.** Se publica la bandera de P2.6
(BAJA / COMPATIBLE CON RUIDO / ALTA / NO ESTIMABLE y τ) para cada celda y para cada LOCRO, **solo
como descriptiva**. **ALTA no veta en P5.** El instrumento remuestrea como independientes sesiones
que comparten hasta 40 barras, y puede marcar ALTA un efecto constante (D-63). El FOLLOW_UP de D-63
sigue **abierto y separado**: la robustez se decide con la superficie, el LOCRO y el tiempo, no con
la bandera.

## 22. Multiplicidad (OD-P5-6)

**Decisión (D-66, OD-P5-6 = A): jerárquica.**
- B2 y S2 **conservan su evidencia confirmatoria de P4** (Bonferroni, `m = 4`). P5 no la repite ni la
  sustituye.
- P5 **no tiene familia confirmatoria nueva: 0 confirmatorias.**
- Los IC95 de vecinos y LOCRO son **sin corregir** y se usan **solo como vetos** («veto sin
  corrección»). Como la supervivencia exige que se cumplan todas las condiciones, un IC95 sin
  corregir solo puede **quitar** candidatas, nunca añadirlas.
- **Ningún vecino se declara política nueva**: no hay ningún descubrimiento que proteger con una
  corrección.

Alternativas:
- **B — corrección de Bonferroni sobre todos los puntos.** En un diseño de vetos, ensanchar los
  intervalos **aumenta** los vetos: protege contra falsos descubrimientos que P5 no puede producir y
  vuelve más probable descartar candidatas reales.
- **C — banda simultánea de la superficie.** Es código y teoría nuevos, sin un beneficio claro para
  una decisión de veto con todas las condiciones obligatorias.

Codex observa (MENOR) que A solo es defendible si P5 se formula como filtro de candidatas ya
confirmadas: así se formula aquí, con la salida `[]` explícitamente válida.

## 23. Definición de región robusta (OD-P5-4)

### 23.1 Algoritmo, para cada centro X ∈ {B2, S2}

Entradas: las clases de la sección 15 de los vecinos válidos de X y los semiplanos de la sección
11.6. Sea `E` el conjunto de vecinos estimables (ACEPTABLE, DÉBIL o CONTRARIA), `A ⊆ E` los
ACEPTABLE y `NE` los NO_ESTIMABLE.

1. **Centro (condición E de la orden):** X cumple su criterio propio. Es decir, las diez condiciones
   de P4 (D-64) y la reproducción de sus filas de P4 en el preflight (OD-P5-16). Si el
   preflight no reproduce, **STOP**: no es un veredicto, es un defecto del ejecutor. Un centro no
   puede sobrevivir porque sus vecinos sean buenos.
2. **Sin cambio de signo:** ningún vecino es CONTRARIO.
3. **Estabilidad por eje:** cada semiplano (`s−`, `s+`, `m2−`, `m2+`) que tiene algún vecino
   estimable tiene **al menos uno ACEPTABLE**.
4. **Anchura de la meseta:** `|A| / |E| ≥ 0,75`.
5. **Capacidad alrededor del centro:** `|NE| ≤ 1`, y **ningún semiplano tiene todos sus vecinos
   válidos NO_ESTIMABLES**.

**Región robusta** = se cumplen 1 a 5.

### 23.2 Por qué esos números

- **Vecindad de 8 y semiplanos:** la continuidad se lee en las cuatro direcciones, y cada candidata
  tiene en su diagonal la recta que la define.
- **0,75 de anchura:** una mayoría clara. B2 admite 2 vecinos no aceptables de 8; S2, 1 de 5, pero
  ese uno no puede ser ninguno de sus dos vecinos iso-RR (sección 11.6). Con
  0,5 se aceptaría media corona caída, que es una cresta y no una meseta. Con 1,0, un solo fallo por
  ruido entre 5 u 8 intervalos sin corregir descartaría la candidata (sección 23.4).
- **`|NE| ≤ 1`:** una celda no estimable no se cuenta como mala, pero dos dejan la meseta sin
  evaluar.

### 23.3 Magnitud: por qué el IC95 > 0 y no «la mitad del centro»

La orden pide evitar que una región sea robusta porque todos los vecinos valen +0,0001. Se
estudiaron dos reglas:
- **«ΔR del vecino ≥ ½·ΔR del centro» (rechazada).** En S2, el vecino (2,25; 3,375) está a medio
  camino entre C0 (ΔR ≡ 0) y S2 en la recta iso-RR (sección 5, punto 3). Si el efecto creciera de
  forma lineal con el stop, ese vecino tendría exactamente la mitad del efecto de S2: la regla
  dependería de la curvatura, y el veredicto de S2 sería una moneda al aire decidida por la
  proximidad al control. Una pendiente suave no es fragilidad.
- **«IC95 inferior > 0» (adoptada en D-66).** Es una regla de signo con incertidumbre. Excluye los
  +0,0001, porque ningún vecino tiene un error típico de ese orden. Es neutral a la distancia al control **bajo un supuesto declarado**: que el efecto y
  su error típico crezcan los dos aproximadamente en proporción a la distancia a C0. En el eje del
  objetivo hay apoyo parcial en P4 (cociente efecto/error ≈ 2,56 en B1 y ≈ 2,77 en B2). En la recta
  iso-RR no hay ningún dato a distancia 0,25: si allí el error creciera como √d, el vecino
  (2,25; 3,375), que decide solo el semiplano `m2−` de S2, tendría menos potencia. Se declara como
  supuesto, no como hecho.

Codex precisa el significado: **ACEPTABLE no significa «no se rompe», sino «mantiene una señal
positiva estadísticamente clara frente a C0»**. Así se rotula en las salidas.

### 23.4 Características operativas (aproximación de diseño, sin datos de vecinos)

Solo con los intervalos de P4 ya publicados (`z95 / z98,75 ≈ 1,960 / 2,498`):
- **error típico** del centro ≈ 0,0259 en B2 y ≈ 0,0104 en S2; **cociente efecto/error** ≈ 2,77 y
  ≈ 3,34;
- **ΔR mínimo** para que un vecino con el mismo error típico tenga IC95 inferior > 0: ≈ **0,051**
  (71 % del efecto de B2) y ≈ **0,020** (59 % del de S2). Codex llega a las mismas cifras;
- si un vecino tuviera **exactamente** el efecto observado del centro y su mismo error típico, la
  probabilidad de que salga ACEPTABLE sería ≈ Φ(2,77 − 1,96) ≈ **0,79** en B2 y ≈ Φ(3,34 − 1,96) ≈
  **0,92** en S2;
- **por candidata** (revisión independiente, I-1), con esas probabilidades y suponiendo vecinos
  independientes, la probabilidad de cumplir la regla de la meseta (condiciones 3 y 4 de la sección
  23.1, sin contar las CONTRARIAS ni la capacidad) es:
  - **B2:** P(≥ 6 ACEPTABLES de 8) ≈ **0,77**;
  - **S2:** P(los dos iso-RR ACEPTABLES y ≥ 2 de los otros 3) = 0,92⁵ + 3·0,92⁴·0,08 ≈ **0,83**.

Advertencias:
- el efecto observado del centro está **inflado por la selección** de P4 (maldición del ganador), así
  que el efecto verdadero de los vecinos será probablemente menor y esas probabilidades son cotas
  optimistas;
- los vecinos están correlacionados entre sí y con el centro;
- **el diseño es exigente con B2 por construcción**, porque su estimación es más ruidosa. Se declara
  y se acepta: P5 puede terminar en `[]`.

Estas cifras no salen de ningún vecino y no se recalibran después.

## 24. Criterio de fragilidad

Una candidata X es **FRÁGIL** si, con el centro reproducido, se da **cualquiera** de estas:

| Código | Condición | Ejemplo de la orden que cubre |
|---|---|---|
| F1 | algún vecino estimable es CONTRARIO (ΔR puntual ≤ 0) | «centro positivo pero vecinos inmediatos cambian de signo» |
| F2 | el semiplano `s−` o el `s+` tiene vecinos estimables y ninguno ACEPTABLE | «desaparece con una pequeña perturbación del stop» |
| F3 | el semiplano `m2−` o el `m2+` tiene vecinos estimables y ninguno ACEPTABLE | «desaparece con una pequeña perturbación del objetivo» |
| F4 | `|A| / |E| < 0,75` | «centro aislado» |
| F5 | alguna mitad temporal del centro con ΔR ≤ 0, o la sensibilidad de 120 del centro con ΔR ≤ 0 o IC95 inferior ≤ 0 | «solo se sostiene en una mitad temporal» (conocida: pasa en P4) |
| F6 | cota conservadora del centro ≤ 0, nivel del centro ≤ 0 o PF del centro ≤ 1 | reverificación de P4 (conocida: pasa) |

- **«Depende de una sola región»** es DEPENDIENTE_DE_MERCADO (sección 25), no FRÁGIL.
- **«Capacidad insuficiente alrededor del centro»** es NO_CONCLUYENTE, no FRÁGIL: una celda sin
  capacidad no es un vecino malo. Ninguna de las dos sobrevive.

## 25. Criterio de dependencia de mercado

X es **DEPENDIENTE_DE_MERCADO** si alguna de las tres poblaciones LOCRO (sin USA, sin EUROPA, sin
ASIA) es estimable y su IC95 inferior de ΔR es ≤ 0 (sección 19.2).

## 26. Criterio mecánico de supervivencia

No hay puntuación ponderada. **Sobrevive solo si se cumplen todas las condiciones que vetan.**

| # | Condición | Instrumento | Efecto | ¿Conocida antes de medir? |
|---|---|---|---|---|
| 1 | El centro mantiene la evidencia favorable de P4 (las diez condiciones de D-64) y reproduce sus filas de P4 según OD-P5-16 | D-64 + preflight | veta (STOP si no reproduce) | sí |
| 2 | Vecindad suficientemente amplia: `|A| / |E| ≥ 0,75` | sección 23 | veta → FRÁGIL (F4) | no |
| 3 | No es un pico aislado: ningún vecino CONTRARIO | sección 23 | veta → FRÁGIL (F1) | no |
| 4 | Estabilidad al variar el stop: `s−` y `s+` con ≥ 1 ACEPTABLE | sección 23 | veta → FRÁGIL (F2) | no |
| 5 | Estabilidad al variar el objetivo 2: `m2−` y `m2+` con ≥ 1 ACEPTABLE | sección 23 | veta → FRÁGIL (F3) | no |
| 6 | Capacidad de los vecinos necesarios: `|NE| ≤ 1` y ningún semiplano entero NO_ESTIMABLE | sección 15 | veta → NO_CONCLUYENTE | no |
| 7 | Robustez temporal interna del centro: mitades > 0 y 120 con IC95 > 0 | sección 17 | veta → FRÁGIL (F5) | sí |
| 8 | Ambigüedad: cota conservadora > 0 en el centro (P4) y en cada vecino ACEPTABLE | sección 18 | veta (en el centro, F6; en los vecinos, a través de ACEPTABLE) | centro sí; vecinos no |
| 9 | No depende de una región: LOCRO pasa | sección 19 | veta → DEPENDIENTE_DE_MERCADO o NO_CONCLUYENTE | casi (sección 19.2) |
| 10 | Concentración por activo | sección 20 | **no veta** (descriptiva) | — |
| 11 | Nivel > 0 y PF > 1: en el centro (P4) y en cada vecino ACEPTABLE | secciones 14 y 15 | veta (en el centro, F6; en los vecinos, a través de ACEPTABLE) | centro sí; vecinos no |
| 12 | Heterogeneidad | sección 21 | **no veta** | — |
| 13 | Ejecutabilidad D-06 (holgura y categorías a la apertura) | sección 14 | **no veta** (descriptiva) | — |

**Etiqueta final de cada candidata**, por orden de precedencia (solo cambia el rótulo, no la
supervivencia):
1. **FRÁGIL** si se da alguna de F1–F6;
2. si no, **DEPENDIENTE_DE_MERCADO** si se da la sección 25;
3. si no, **NO_CONCLUYENTE** si falla la condición 6 o algún LOCRO no es estimable;
4. si no, **ROBUSTA**.

**Solo ROBUSTA sobrevive.** Se publican siempre todas las condiciones de cada candidata, cumplan o
no, aunque la etiqueta ya esté decidida.

## 27. Salida permitida y política de vecinos (OD-P5-13)

- **C0 es el control**, no una candidata.
- **B2 y S2 son las únicas candidatas elegibles.** Si sobreviven, sobreviven con su configuración
  exacta.
- **Los puntos vecinos son diagnósticos de superficie, no candidatos.** Ninguno puede sustituir,
  rescatar ni acompañar a B2 o a S2.
- **Si un vecino sale mejor que el centro:** se publica, no se adopta y la candidata no se mueve. Un
  vecino mejor no hace frágil al centro (solo un vecino no aceptable cuenta en contra), pero tampoco
  lo mejora. Ninguna salida usa la expresión «nuevo óptimo».

**Salida posible, y ninguna otra:** `[]`, `[B2]`, `[S2]`, `[B2, S2]`.

GATE P5 admite hasta 5 políticas. Esta ficha **no** lee ese límite como permiso para promover
vecinos: lo cumple con ≤ 2. D-66 (OD-P5-13 = A) lo cierra: ningún vecino es elegible, y promover
puntos de la superficie exigiría un estudio nuevo con su propia decisión.

## 28. Configuración canónica y hash (OD-P5-14)

Para cada celda (centros, vecinos y C0) el ejecutor genera una configuración completa y
determinista, con su hash, **para trazabilidad**. El papel de cada una va fuera del hash, en
`procedencia.rol`:
- `CONTROL` para C0;
- `CANDIDATA` para B2 y S2;
- `DIAGNOSTICO_SUPERFICIE` para los vecinos, con `m3_auxiliar` explícito.

**Un vecino nunca recibe hash de política candidata** (D-66): su hash identifica la configuración
diagnóstica que se midió, no una política. Solo las candidatas supervivientes se publican como
política candidata, y su configuración es la `config` que exige el gate. El hash de las tres celdas
con `m3_auxiliar` contiene el `target3` real de 5,625.

**Política = dos partes.**
1. **`advisor_config_hash`:** el `config_hash` del proyecto (`advisor/run/manifest.py:80`) sobre el
   `AdvisorConfig` de `config.yaml` con **solo** `levels.atr_stop_multiple` y
   `levels.target_atr_multiples` sustituidos. Cubre el resto de la configuración que define la
   señal y la geometría: indicadores, `lookback_bars`, `entry_max_atr`, `entry_pullback_atr`,
   `target2_structural`, `risk.min_rr_ratio`, etc. Excluye las rutas de máquina, como ya hace
   `config_hash`. **Test:** en C0 debe dar `89406d28c7b4b6e6c4f032cd63b6868c927af3e926dfb52d430dfa6654d06387`
   (el `EXPECTED_CONFIG_HASH` de P4).
2. **Envoltorio de política del laboratorio**, con los campos que no están en `config.yaml` o que
   deciden el comportamiento económico:

```json
{
  "esquema": "intradia.p5.politica.v1",
  "advisor_config_hash": "<sha256>",
  "geometria": {
    "atr_stop_multiple": 2.0,
    "target_atr_multiples": [1.5, 4.875, 5.0],
    "target2_structural": false,
    "entry_max_atr": 0.75,
    "min_rr": 1.5,
    "regla_soporte": "E",
    "support_buffer_atr": 0.25,
    "m3_auxiliar": false
  },
  "laboratorio": {
    "horizonte": "swing",
    "max_hold_bars": 40,
    "coste_pct_ida_vuelta": 0.2,
    "entrada": "cierre_de_la_senal",
    "salidas": ["STOP_FIRST", "TARGET_FIRST", "TIME", "FINAL"],
    "ambiguous": "no_resuelto"
  }
}
```

- **Serialización canónica:** `json.dumps(payload, sort_keys=True, separators=(",", ":"),
  ensure_ascii=False, allow_nan=False)`, codificado en UTF-8. Usa la **misma ordenación y los mismos
  separadores** que `canonical_hash` (`advisor/universe/vintage.py:12`), pero **no es la misma
  función**: `canonical_hash` usa `default=str` y no fija `allow_nan`. P5 define su propia función
  canónica con `allow_nan=False` y sin `default`, de modo que un valor no serializable es un error y
  no una cadena.
- **Etiquetas de salida:** las constantes literales del código (`STOP_FIRST`, `TARGET_FIRST`, `TIME`,
  `FINAL`, `advisor/research/event_study.py:38-42`), no nombres libres.
- **Floats:** como números JSON con la representación más corta de ida y vuelta de Python (`repr`).
  Todos los valores de geometría son múltiplos de 1/8 y exactos en binario; `0.2` y `0.75` son
  deterministas con `repr`. Las listas conservan su orden.
- **`policy_sha256` = sha256 de esa cadena.** El cálculo es idéntico para todas las celdas, pero el
  campo publicado depende del papel, para que la regla sea mecánica: C0 y las candidatas publican
  `policy_sha256`; los vecinos publican el mismo hash con el nombre `diagnostico_sha256`, nunca
  `policy_sha256`, y nunca aparecen en la lista de políticas candidatas.
- **No entran en el hash:** el identificador («B2»), la procedencia (`data_vintage_id`,
  `universe_vintage_id`, `population_sha256`, SHA de P4 y de P5) y los resultados. Se publican al
  lado, en un bloque `procedencia`. Así el hash identifica el comportamiento y no la etiqueta.
- La duplicación de `entry_max_atr`, `min_rr` y `target2_structural` entre `geometria` y
  `advisor_config_hash` es deliberada, por legibilidad. Un test exige que coincidan.
- **No se escribe ninguna configuración productiva.** El ejecutor publica el JSON y su hash en la
  evidencia; `config.yaml` no cambia.

## 29. Número de comparaciones

Convención de P3 y P4: **cada estimación con IC es una comparación**. Se cuenta cada IC calculado,
también si la celda resulta NO_ESTIMABLE (se calcula y luego se clasifica).

| Por vecino válido | Número | Tipo |
|---|---|---|
| Primaria, bloque 60, IC95 | 1 | **decisoria** (veto sin corrección, a través de ACEPTABLE) |
| Sensibilidad 120, IC95 | 1 | descriptiva |
| Cota conservadora | 1 | **decisoria** (a través de ACEPTABLE, punto) |
| Cota favorable | 1 | descriptiva |
| Nivel de la celda, IC95 | 1 | **decisoria** (a través de ACEPTABLE, punto) |
| **Subtotal por vecino** | **5** | |

| Por centro | Número | Tipo |
|---|---|---|
| LOCRO (sin USA, sin EUROPA, sin ASIA), IC95 | 3 | **decisoria** (veto sin corrección) |
| Reproducción de P4 (primaria, Bonferroni, 120, cotas, mitades, nivel) | 0 | son comparaciones de P4, no nuevas |

**Fórmula, que el ejecutor reproduce desde sus salidas:**

```
N = Σ_{X ∈ {B2, S2}} (5 · |V_X| + 3)
```

con `|V_X|` el número de vecinos válidos de X.

| Escenario | `|V_B2|` | `|V_S2|` | **N** |
|---|---|---|---|
| **D-66 (OD-P5-3 = C)** | 8 | 5 | **(40 + 3) + (25 + 3) = 71** |
| OD-P5-3 = A (no elegida) | 5 | 5 | (25 + 3) + (25 + 3) = 56 |

- **Confirmatorias nuevas: 0.** Decisorias: primaria de cada vecino (13), sus cotas conservadoras y
  niveles (que deciden por su punto), y los 6 LOCRO. Todo lo demás es descriptivo.
- **No cuentan, porque no llevan IC:** mitades de los vecinos, retenciones, banderas de
  heterogeneidad, PF, medias agrupadas, `P(objetivo antes que stop)`, tasas de salida, fracciones
  estructurales, holgura D-06 y concentración por activo.
- **Desglose pedido por la orden:** global 13 (primarias); por región 6 (LOCRO); leave-one-region-out
  6 (los mismos); por activo 0 (descriptivo, sin IC); temporal 13 (120 de los vecinos; las mitades
  son puntos); sensibilidad 120 13 (las mismas); ambigüedad 26 (13 × 2); nivel 13.
- **El ejecutor deriva N de la estructura antes de abrir ningún desenlace** (rejilla, validez y
  regiones). Si sale distinto de 71, **STOP** (D-66). El 71 es la comprobación, nunca el sustituto
  del recuento.
- **Si después de abrir desenlaces una celda quedara sin pares** por una razón estructural, el
  número de estimaciones producidas cambia por esa razón. Se publica el recuento derivado con sus
  componentes y el motivo, **nunca** un 71 escrito a mano.
- Con P4 (447), el acumulado sobre la cosecha queda en 518 comparaciones con IC. Se publica.

## 30. Evidencia prevista

- `evidence/2026-10-02-T-021-p5-diseno/` (esta fase): inventario estructural sin desenlaces, encargo
  y revisión de diseño de Codex, revisión adversarial de la ficha.
- `evidence/<fecha>-T-021-p5/preflight/`: identidad del ejecutor, población y hash, rejilla y
  validez, inventario estructural, configuraciones y hashes de todas las celdas, reproducción
  de C0 (identidad) y de B2/S2 (filas de P4) y recuento previsto. **El preflight no archiva
  desenlaces por señal** de C0, B2 ni S2 (ni `net_R` por `signal_id` ni eventos): solo las filas
  agregadas que reproduce. Así nadie puede calcular el LOCRO antes de la marca, ni dentro ni fuera
  del código. Sin desenlaces de ningún punto nuevo.
- `evidence/<fecha>-T-021-p5/run/`: `p5-resultado.json`, `p5-resumen.md`, `tablas/*.tsv`
  (superficie por celda, clases, semiplanos, LOCRO, concentración, criterio condición por
  condición, recuento) y `SHA256SUMS-ejecucion.txt`.
- La etiqueta de universo en toda tabla y conclusión.

## 31. GATE P5, requisito por requisito

| # | Requisito (`docs/gates.md`) | Cómo lo cubre esta ficha |
|---|---|---|
| 1 | Superficies de parámetros publicadas | Secciones 11, 14 y 30: las dos superficies 3×3 con todas sus celdas (válidas, ausencias estructurales y `m3` auxiliar), su ΔR, IC, clase y descriptivas |
| 2 | Configuraciones descartadas por fragilidad o por depender de un solo mercado, listadas con motivo | Secciones 24–26: cada candidata descartada sale con su etiqueta (FRÁGIL, DEPENDIENTE_DE_MERCADO o NO_CONCLUYENTE) y la lista de condiciones (F1–F6, LOCRO, capacidad) que fallan |
| 3 | Conjunto de políticas candidatas ≤ 5 | Sección 27: `[]`, `[B2]`, `[S2]` o `[B2, S2]` |
| 4 | Cada candidata con su `config` completa y hash | Sección 28: `advisor_config_hash` + envoltorio canónico + `policy_sha256` |

## 32. Prohibiciones

En el diseño y en la ejecución:
- calcular cualquier resultado de un punto nuevo antes del `P5_PREREG_SHA` y de la marca de
  ejecución;
- ejecutar P4 otra vez o `comparacion-pareada`;
- añadir, quitar o mover celdas, ejes, pasos, umbrales, semiplanos, regiones o condiciones después de
  ver desenlaces;
- mover B2 o S2, o promover un vecino;
- elegir la resolución intrabarra a posteriori;
- usar el score para seleccionar señales;
- tocar `config.yaml`, desplegar, activar B2/S2 o Score v2, o tocar la Pi;
- adelantar P6 (sizing, cartera, divisa, drawdown, CAGR, Sharpe, Sortino);
- presentar el resultado como validación fuera de muestra;
- ejecutar P5 más de una vez: un cambio posterior es un estudio nuevo, con decisión propia.

## 33. OWNER_DECISION_REQUIRED — todas CERRADAS en D-66 (2026-10-02)

El propietario adoptó en D-66 la recomendación de cada una (OD-P5-8 con la capacidad i y OD-P5-16
con guardas reforzadas). La decisión va al principio de cada OD. Las alternativas y consecuencias
que siguen son el historial de la pregunta tal como se planteó; lo vinculante es D-66 y el cuerpo de
esta ficha.

### OD-P5-1 — Forma de la superficie · **CERRADA (D-66): A**

**Decisión del propietario:** dos superficies locales de 3×3 sobre una retícula común. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** ¿qué forma tienen las superficies de P5?
- **Alternativas:**
  - **A.** Dos superficies locales de 3×3, una por candidata, sobre una retícula común (sección 11).
  - **B.** Una superficie rectangular común que cubra B2 y S2 (`s` de 1,75 a 2,75 y `m2` de 3,375 a
    5,25: 5 × 6 = 30 celdas, 3 inválidas por `min_rr`, 25 vecinos válidos además de los dos centros,
    muchos lejos de los dos).
  - **C.** Solo cortes por ejes (cruces de 5 puntos), sin diagonales.
- **Consecuencias:** A mide solo lo local y deja las diagonales que definen cada candidata. B
  multiplica las comparaciones (25 vecinos × 5 = 125, más LOCRO) y convierte P5 en una búsqueda. C pierde
  la recta iso-RR de S2 y la de saturación de B2.
- **Recomendación:** **A.**
- **Bloquea:** la rejilla y el recuento.

### OD-P5-2 — Valores exactos de los ejes y resolución · **CERRADA (D-66): A**

**Decisión del propietario:** Δstop = 0,25·ATR y Δtarget2 = 0,375·ATR; B2: stop {1,75; 2,00; 2,25} × target2 {4,500; 4,875; 5,250}; S2: stop {2,25; 2,50; 2,75} × target2 {3,375; 3,750; 4,125}. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** ¿qué pasos y qué valores?
- **Alternativas:**
  - **A.** `Δs = 0,25`, `Δm2 = 0,375`; B2: `s` ∈ {1,75; 2,0; 2,25}, `m2` ∈ {4,5; 4,875; 5,25}; S2:
    `s` ∈ {2,25; 2,5; 2,75}, `m2` ∈ {3,375; 3,75; 4,125}.
  - **B.** Escala de P4: `Δs = 0,5`, `Δm2 = 0,75`.
  - **C.** A, más un segundo anillo en el eje que P4 varió (3×5).
- **Consecuencias:**
  - **A:** perturbación de un ~10 % alrededor de cada centro, que mueve el stop del 78–86 % de las
    señales (sección 11.2). Contradice la frase de T-020 §7 solo si P5 se leyera como rejilla de
    políticas: esta ficha la declara prueba de sensibilidad local a escala inferior.
  - **B:** el vecino inferior de S2 en la recta iso-RR es C0 (ΔR ≡ 0), que es CONTRARIO por
    definición: **S2 saldría FRÁGIL por construcción** (F1), salvo añadir una regla que excluya C0
    de la vecindad. El superior, (3,0; 4,5), queda a un paso de P4 de S2. La vecindad de S2 deja de
    ser local y deja de ser independiente del control.
  - **C:** añade anchura, pero en S2 el segundo anillo choca con la frontera (`s = 3,0` exige `m2 ≥
    4,5`) y vuelve a la asimetría (la columna `s = 3,0` es entera inválida); añade 9 vecinos válidos (+45
    comparaciones).
- **Recomendación:** **A.**
- **Bloquea:** la rejilla, el recuento y el test de retícula.

### OD-P5-3 — Borde de B2 con `target3` · **CERRADA (D-66): C**

**Decisión del propietario:** `target3` = 5,625 y `m3_auxiliar` = true solo en las tres celdas diagnósticas con target2 = 5,25; nunca políticas ni candidatas; B2 conserva `target3` = 5,0. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** ¿cómo se trata la frontera `m2 < m3 = 5,0`?
- **Alternativas:** A (truncar), B (reparametrizar) o C (`m3` auxiliar = 5,625 solo en la fila
  diagnóstica `m2 = 5,25`). Detalle en la sección 12.2.
- **Consecuencias:** A deja a B2 sin semiplano `m2+` y obliga a elegir entre «robusta con un lado sin
  evaluar» y «no robusta por vecinos imposibles». B no resuelve el borde. C da 8 vecinos sin tocar
  la configuración de B2, porque `m3` no interviene en ningún desenlace; a cambio, las tres celdas
  llevan una configuración no equivalente en `target3` (solo informe), rotulada `m3_auxiliar`.
- **Recomendación:** **C**, restringida a esas tres celdas. Es contraria a la preferencia inicial
  del propietario (A), porque el inventario demuestra que A impide la evaluación simétrica.
- **Bloquea:** la rejilla de B2, el recuento (71 o 56) y el test de inercia de `m3`.

### OD-P5-4 — Definición algorítmica de región robusta · **CERRADA (D-66): A**

**Decisión del propietario:** ACEPTABLE = estimable, IC95 inferior de ΔR > 0, cota conservadora puntual > 0, nivel > 0 y PF > 1; región robusta = ningún CONTRARIO, ≥ 1 ACEPTABLE en cada semiplano con estimables, `|A|/|E| ≥ 0,75`, `|NE| ≤ 1` y ningún semiplano entero NO_ESTIMABLE. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** ¿qué hace ACEPTABLE a un vecino y qué hace robusta a una región?
- **Alternativas:**
  - **A.** La de las secciones 15 y 23: ACEPTABLE = IC95 inferior > 0, cota conservadora > 0, nivel >
    0 y PF > 1; robusta = sin CONTRARIAS, cada semiplano con ≥ 1 ACEPTABLE, `|A|/|E| ≥ 0,75` y
    `|NE| ≤ 1`.
  - **B.** A, añadiendo `ΔR ≥ ½·ΔR_centro`.
  - **C.** Solo el signo puntual (ACEPTABLE = ΔR > 0, cota conservadora > 0, nivel > 0 y PF > 1).
  - **Umbrales de la meseta, elegibles por separado** dentro de A:
    - anchura `|A|/|E|`: **0,75 (recomendado)**, 0,5 o 1,0;
    - no estimables: **`|NE| ≤ 1` (recomendado)** o `|NE| = 0`;
    - semiplanos: **≥ 1 ACEPTABLE en cada uno (recomendado)** o sin condición de semiplano.
- **Consecuencias:**
  - **A:** exigente. Un vecino con el mismo efecto que el centro sale ACEPTABLE con probabilidad
    ≈ 0,79 en B2 y ≈ 0,92 en S2, y la candidata cumple la regla de la meseta con ≈ 0,77 (B2) y ≈ 0,83
    (S2) (sección 23.4), menos con la maldición del ganador.
    Neutral a la distancia a C0 solo bajo el supuesto de la sección 23.3.
  - **B:** casi redundante con A en la mayoría de vecinos (el IC95 ya exige el 59–71 % del efecto),
    pero decide por curvatura en el vecino de S2 que está entre C0 y S2 (sección 23.3).
  - **C:** laxa: no distingue +0,0001 de un efecto real si el signo puntual es positivo, que es lo
    que la orden pide evitar.
  - **Umbrales:**
    - anchura 0,5: admite media corona caída (una cresta);
    - anchura 1,0: un solo fallo por ruido descarta, y la probabilidad por candidata cae a ≈ 0,15
      (B2: 0,79⁸) y ≈ 0,66 (S2: 0,92⁵);
    - `|NE| = 0`: una sola celda sin capacidad deja la candidata NO_CONCLUYENTE;
    - sin semiplanos: una dirección entera podría caer sin vetar.
- **Recomendación:** **A**, con 0,75, `|NE| ≤ 1` y semiplanos.
- **Bloquea:** las secciones 15, 23, 24 y 26 y el test del criterio.

### OD-P5-5 — Vecindad · **CERRADA (D-66): A**

**Decisión del propietario:** 8 vecinos geométricos; las ausencias estructurales no cuentan; S2 mantiene su tolerancia asimétrica (sus dos vecinos iso-RR tienen que ser ACEPTABLES). El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** ¿4 u 8 vecinos? ¿Cómo se tratan los bordes y los puntos inválidos?
- **Alternativas:** **A.** 8 vecinos; las ausencias estructurales no cuentan; semiplanos de la sección
  11.6. **B.** 4 vecinos ortogonales. **C.** 8 vecinos, contando las ausencias como fallos.
- **Consecuencias:** A no cuenta las ausencias, pero deja a S2 con dos semiplanos de un solo vecino:
  sus dos vecinos iso-RR tienen que ser ACEPTABLES (tolerancia efectiva de la sección 11.6). B deja a
  S2 con 2 vecinos y sin la dirección «stop más ancho», y quita las rectas que definen las dos
  candidatas. C castiga a S2 por estar sobre `min_rr`, y a B2 si OD-P5-3 = A.
- **Recomendación:** **A.**
- **Bloquea:** la sección 23.

### OD-P5-6 — Multiplicidad · **CERRADA (D-66): A**

**Decisión del propietario:** jerárquica; 0 confirmatorias nuevas; IC95 de vecinos y LOCRO como vetos; sin Bonferroni nuevo ni banda simultánea. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** ¿cómo se trata la multiplicidad de los vecinos?
- **Alternativas:** **A.** Jerárquica, con 0 confirmatorias nuevas y vetos sin corrección. **B.**
  Bonferroni sobre todos los puntos. **C.** Banda simultánea.
- **Consecuencias:** A conserva la evidencia confirmatoria de P4 y usa los IC95 sin corregir solo como
  vetos: solo pueden quitar candidatas, y P5 no produce ningún descubrimiento que proteger. B ensancha
  los intervalos y aumenta los vetos sin proteger contra nada que P5 pueda producir. C es teoría y
  código nuevos (sección 22).
- **Recomendación:** **A.**
- **Bloquea:** las secciones 16 y 22 y el recuento.

### OD-P5-7 — Qué es «mercado» · **CERRADA (D-66): A**

**Decisión del propietario:** región; USA, EUROPA y ASIA decisorias; GLOBAL y EMERGING_MARKETS dentro y descriptivas. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** ¿qué unidad decide la dependencia de un solo mercado?
- **Alternativas:** **A.** Región, con USA, EUROPA y ASIA decisorias y GLOBAL/EM descriptivas.
  **B.** Plaza / exchange. **C.** País.
- **Consecuencias:** A usa la unidad de P4. B mezcla la exposición con el sitio de cotización (7 de
  los 16 ASIA y 3 de los 40 USA cotizan en XETRA o NYSE) y deja plazas con muy pocos activos. C no
  existe en el universo.
- **Recomendación:** **A.**
- **Bloquea:** la sección 19.

### OD-P5-8 — Leave-one-region-out · **CERRADA (D-66): A con la capacidad i**

**Decisión del propietario:** LOCRO decisorio sobre los centros; pasa si es estimable y su IC95 inferior > 0; pares relativos a la población restante (50.718 / 59.967 / 74.969); nunca 91.126. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** ¿es obligatorio y cuándo pasa?
- **Alternativas:**
  - **A.** LOCRO sobre los centros, obligatorio: pasa si las tres poblaciones son estimables y tienen
    el IC95 inferior > 0.
  - **B.** Lo mismo, con el punto > 0 en lugar del IC95.
  - **C.** Solo descriptivo, con la dependencia leída en las estimaciones por región de P4.
  - **Capacidad del LOCRO**, elegible por separado:
    - **i (recomendada):** la condición de pares relativa a la población sin r (umbrales de la
      sección 19.2);
    - **ii:** la condición absoluta de las celdas (91.126 de 101.251);
    - **iii:** sin condición de pares, conservando las demás.
- **Consecuencias:** A usa la misma regla de incertidumbre que los vecinos. Con la capacidad ii,
  ningún LOCRO es estimable (56.353 / 66.629 / 83.298 < 91.126) y la salida `[]` queda decidida por el
  texto. iii no detecta un emparejamiento roto dentro de la subpoblación. B es más laxa. C deja el
  requisito del gate sobre cifras ya publicadas y sin instrumento nuevo. En A, B y C, el resultado
  del centro está en buena parte anticipado por P4 (sección 19.2).
- **Recomendación:** **A, con la capacidad i.**
- **Bloquea:** las secciones 19 y 25 y el recuento (+6).

### OD-P5-9 — Concentración por activo · **CERRADA (D-66): A**

**Decisión del propietario:** concentración por activo descriptiva; no veta ni rescata. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** ¿descriptiva o veto?
- **Alternativas:** **A.** Descriptiva. **B.** Veto si los 5 activos que más contribuyen superan el
  50 % de `Σ ΔR`. **C.** Veto si un solo activo supera el 25 %.
- **Consecuencias:** A publica la concentración sin que pueda quitar ni salvar candidatas; una
  ventaja concentrada en pocos activos queda a la vista para P6, pero no veta aquí. B y C fijarían el
  umbral conociendo los 90 ΔR por activo de B2 y S2 publicados en P4.
- **Recomendación:** **A.**
- **Bloquea:** la sección 20.

### OD-P5-10 — Heterogeneidad · **CERRADA (D-66): A**

**Decisión del propietario:** ALTA no veta; el FOLLOW_UP del instrumento sigue fuera de P5. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** ¿qué hace P5 con el FOLLOW_UP del instrumento de heterogeneidad?
- **Alternativas:** **A.** No repararlo en P5: bandera descriptiva y ALTA no veta. **B.** Reparar
  primero el instrumento y bloquear P5. **C.** Instrumento nuevo dentro de P5.
- **Consecuencias:** A decide con la superficie, el LOCRO y el tiempo. B retrasa P5 por una
  herramienta que no se usaría como veto. C mezcla el desarrollo de un instrumento con la decisión
  que debería tomar.
- **Recomendación:** **A.**
- **Bloquea:** la sección 21.

### OD-P5-11 — Robustez temporal · **CERRADA (D-66): A**

**Decisión del propietario:** veto en el centro (mitades > 0; 120 con ΔR > 0 e IC95 inferior > 0); descriptiva en los vecinos. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** ¿qué veta la dimensión temporal?
- **Alternativas:** **A.** Veto en el centro (mitades y 120, ya conocidos de P4); en los vecinos,
  descriptiva. **B.** A, y además las dos mitades del vecino > 0 (puntos) como parte de ACEPTABLE.
  **C.** Solo informa, también en el centro.
- **Consecuencias:** A mantiene ACEPTABLE simple. B añade rigor temporal a la meseta, pero también
  más vetos sin corrección (y, por coherencia con P4, contaría 26 comparaciones más). C contradice
  la condición 8 de P4 heredada.
- **Recomendación:** **A.**
- **Bloquea:** las secciones 17 y 26.

### OD-P5-12 — Ambigüedad · **CERRADA (D-66): A**

**Decisión del propietario:** cota conservadora puntual > 0 como parte de ACEPTABLE; la favorable se publica; sin IC de la cota. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** ¿qué se exige a cada celda?
- **Alternativas:** **A.** Cota conservadora (puntual) > 0 como parte de ACEPTABLE; la favorable se
  publica. **B.** Solo publicar. **C.** IC95 inferior de la cota conservadora > 0.
- **Consecuencias:** A hereda la condición 5 de P4. B deja que la exclusión diferencial de las
  ambiguas favorezca a una celda. C es más exigente que lo que se pidió a las candidatas en P4.
- **Recomendación:** **A.**
- **Bloquea:** la sección 18.

### OD-P5-13 — Políticas elegibles · **CERRADA (D-66): A**

**Decisión del propietario:** salida ⊆ {B2, S2}; ningún vecino elegible. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** ¿solo B2 y S2 pueden sobrevivir?
- **Alternativas:** **A.** Sí: salida ⊆ {B2, S2}; ningún vecino es elegible. **B.** Permitir promover
  vecinos hasta 5 políticas.
- **Consecuencias:** A hace que P5 solo pueda quitar candidatas heredadas: si un vecino es mejor, se
  publica y no se adopta, y la salida `[]` es posible. B convierte P5 en una segunda optimización
  sobre la misma cosecha.
- **Recomendación:** **A.**
- **Bloquea:** la sección 27 y el test del criterio.

### OD-P5-14 — Configuración canónica y hash · **CERRADA (D-66): A**

**Decisión del propietario:** `advisor_config_hash` + envoltorio `intradia.p5.politica.v1` + `policy_sha256`, con las constantes de salida del código. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** ¿qué campos forman la política y cómo se serializa?
- **Alternativas:**
  - **A.** `advisor_config_hash` del proyecto sobre `AdvisorConfig` con la geometría sustituida, más
    el envoltorio de laboratorio en JSON canónico (sección 28).
  - **B.** Solo el envoltorio, sin `advisor_config_hash`.
  - **C.** Solo `advisor_config_hash`.
- **Consecuencias:** B no cubre los parámetros que definen la señal. C no cubre el coste, el
  horizonte, la entrada al cierre ni la regla de soporte, que no están en `config.yaml`.
- **Recomendación:** **A.**
- **Bloquea:** la sección 28 y el test de hash.

### OD-P5-15 — Capacidad de celda · **CERRADA (D-66): A**

**Decisión del propietario:** umbrales de capacidad de P4; clases AUSENCIA_ESTRUCTURAL / NO_ESTIMABLE / ACEPTABLE / DÉBIL / CONTRARIA. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** ¿qué hace interpretable una celda?
- **Alternativas:** **A.** Los umbrales de P4 (condiciones 3 y 9), con las clases NO_ESTIMABLE /
  ACEPTABLE / DÉBIL / CONTRARIA. **B.** A sin el límite de anchura del IC95. **C.** Umbrales nuevos.
- **Consecuencias:** A es coherente con P4. B deja entrar celdas imprecisas en la meseta. C abre un
  grado de libertad sin motivo.
- **Recomendación:** **A.**
- **Bloquea:** la sección 15.

### OD-P5-16 — Reproducción de P4 antes de la ejecución · **CERRADA (D-66): A, con guardas reforzadas**

**Decisión del propietario:** reproducción de P4 antes de la marca solo de C0, B2 y S2 y solo de estimaciones ya publicadas, con las reglas de la sección 33 (OD-P5-16, «Reglas vinculantes»). El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** ¿dónde y contra qué se comprueba que el ejecutor de P5 mide lo mismo que el de P4?
- **Qué se puede reproducir** (corregido tras la revisión de Codex, BLOCKER): P4 **no publica C0
  como salida**. `p4-resultado.json` → `salidas` contiene B1, B2, S1, S2 y E1, y `nivel.tsv` /
  `estimaciones.tsv` solo tienen variantes. Por eso:
  - **C0** se reproduce por **identidad**: la réplica de C0 reproduce exactamente el `ManagedEvent`
    del event study en estado, salida y `net_R` (el test 3 de P4), y su `advisor_config_hash` es
    `89406d28…6387`;
  - **B2 y S2** reproducen sus filas de P4 en `run/tablas/`, con X ∈ {`B2`, `S2`} (el valor literal de
    la columna `comparacion`):
    - `estimaciones.tsv`, por la clave `(comparacion, estimacion, estrato)` exacta:
      - `(X, primaria_60, "")`: es la fila de Bonferroni (`ic_nivel` 0,987500 y 20.000 remuestreos);
        **no existe una primaria al 95 % aparte**;
      - `(X, bloque_120, "")`, `(X, cota_conservadora, "")` y `(X, cota_favorable, "")`;
      - `(X, mitades, bloques_2_11)` y `(X, mitades, bloques_12_21)`;
      - columnas comparadas: `n_pares`, `n_bloques`, `min_pares_bloque`, `media_delta_r`,
        `media_agrupada_delta_r`, `ic_inferior`, `ic_superior`, `ic_nivel` y `remuestreos`;
    - `nivel.tsv`, fila X: todas sus columnas;
    - `capacidad.tsv`, fila X: todas sus columnas. **Del IC95 de 2.000 remuestreos de la primaria
      solo se compara y se archiva la anchura** (`anchura_ic95`), que es lo que P4 publicó; sus
      extremos no se publican y no intervienen en nada;
    - `emparejamiento.tsv`, filas de X: todas sus claves.
  - **Regla de comparación:** se ignoran las líneas que empiezan por `#`; se comparan las columnas
    nombradas; cada valor de P5 se formatea con la misma `_cell` de P4 (`advisor/research/p4.py:2128`,
    `float` → `"{:.6f}"`) y se exige **igualdad de cadenas**, no de floats crudos. El Bonferroni de
    20.000 remuestreos es determinista con la semilla derivada.
- **Alternativas:**
  - **A.** En el **preflight**, antes de la marca: el ejecutor evalúa desenlaces **solo** de C0, B2 y
    S2 (ya publicados en D-64) y **solo** para las estimaciones que P4 ya publicó. **No calcula
    ninguna estimación nueva**: ni LOCRO, ni estratos, ni subpoblaciones (revisión independiente,
    MENOR). La ruta del LOCRO se niega a ejecutarse sin la marca. Cualquier otra geometría hace que
    el evaluador lance un error.
  - **B.** En la ejecución, después de la marca.
  - **C.** No reproducir: copiar los valores de P4.
- **Consecuencias:** A detecta un defecto del ejecutor antes de consumir la ejecución única, sin
  abrir ningún desenlace nuevo ni ninguna estimación nueva; tener en memoria los desenlaces por señal
  de B2 y S2 ya publicados no permite calcular el LOCRO, porque esa ruta exige la marca. B gasta la
  ejecución si hay un defecto. C no comprueba que el código de P5 mida lo mismo que el de P4.
- **Recomendación:** **A**, declarando en el preflight `outcomes_read = "solo C0/B2/S2, solo
  estimaciones ya publicadas en P4"`.
- **Bloquea:** el preflight y los tests 6, 7 y 8.

**Reglas vinculantes del preflight de reproducción (D-66):**
1. **Lista blanca de geometrías:** antes de la marca solo se evalúan C0, B2 y S2. Intentar evaluar
   un vecino, o cualquier otra geometría, lanza un error.
2. **Lista blanca de estimaciones**, solo las ya publicadas. Para X ∈ {`B2`, `S2`}:
   - en `estimaciones.tsv`: `(X, primaria_60, "")`, `(X, bloque_120, "")`,
     `(X, cota_conservadora, "")`, `(X, cota_favorable, "")`, `(X, mitades, bloques_2_11)` y
     `(X, mitades, bloques_12_21)`. La fila `primaria_60` **es la de Bonferroni** (`ic_nivel` =
     0,9875, `remuestreos` = 20.000); no existe otra fila de primaria al 95 %;
   - la fila X de `nivel.tsv` y de `capacidad.tsv`, y las filas X de `emparejamiento.tsv`;
   - del IC95 de 2.000 remuestreos usado para la capacidad, solo se reproduce y compara
     `anchura_ic95`. Sus extremos no se archivan.
3. **Comparación:** cadenas con la representación de P4 (`float` → `"{:.6f}"`) sobre las columnas
   pre-registradas. Si algo diverge, **STOP**, sin actualizar el valor esperado ni introducir
   ninguna tolerancia.
4. **C0:** identidad semántica con el event study y `advisor_config_hash` =
   `89406d28c7b4b6e6c4f032cd63b6868c927af3e926dfb52d430dfa6654d06387`.
5. **Aislamiento:**
   - no se escriben eventos ni `net_R` por `signal_id`;
   - la API del preflight no los devuelve: la función de reproducción devuelve solo el agregado
     autorizado;
   - antes de la marca fallan explícitamente las **estimaciones** (todo cálculo que use desenlaces)
     del LOCRO, de regiones y subpoblaciones, de estratos, de concentración por activo nueva, de los
     vecinos y cualquier estimación nueva de P5, con tests que intentan llamar cada ruta y esperan la
     excepción;
   - **no** fallan, porque no usan desenlaces: el censo estructural por región, los denominadores del
     LOCRO (56.353 / 66.629 / 83.298) y sus mínimos de pares, la rejilla, la validez de las celdas y
     el recuento estructural de la sección 29. Se calculan y se comprueban en el preflight;
   - la evidencia del preflight solo contiene agregados ya publicados y controles estructurales.
6. **No autoriza repetir P4** ni ejecutar `p4 --fase confirmatoria`.

## 34. Plan de implementación (requiere autorización aparte)

1. **Paso 1 — pre-registro.** Esta ficha, con las OD-P5 cerradas en D-66 y la revisión final
   aplicada. El HEAD documental que quede con 0 BLOCKER y 0 IMPORTANTE es el **`P5_PREREG_SHA`**.
2. **Paso 2 — ejecutor y preflight, con una autorización nueva.** Codex programa y Claude supervisa
   `advisor/research/p5.py` y un comando `p5 --fase preflight|confirmatoria`. Reutiliza
   `p4.build_population`, `geometry_levels`, la réplica de geometrías, `pair_populations`,
   `bootstrap_block_delta`, `capacity_check` y `ambiguity_bound_deltas`. Añade la retícula, la
   validez, las clases, los semiplanos, el LOCRO, la concentración, el criterio, el recuento derivado,
   la configuración canónica con su hash y la marca de ejecución única.
3. **Tests obligatorios** (antes de ejecutar):
   1. **Retícula:** los 18 puntos, su validez (13 vecinos válidos y 3 ausencias con la
      recomendación), sin coincidencias entre superficies, y B2/S2/C0 en nodos.
   2. **Inercia de `m3`:** con barras sintéticas, el `ManagedEvent` es idéntico con `m3 = 5,0` y con
      `m3 = 5,625` cuando `m2 < 5,0`; las celdas con `m3` auxiliar llevan la marca.
   3. **Coherencia sobre niveles efectivos** (condición 6) en todas las celdas válidas, y violación
      en las tres ausencias, solo con primitivas.
   4. **Clases y semiplanos:** con resultados sintéticos, cada clase y cada semiplano salen como en
      las secciones 11.6, 15 y 23.
   5. **Criterio:** casos sintéticos de ROBUSTA, de cada F1–F6, de DEPENDIENTE_DE_MERCADO y de
      NO_CONCLUYENTE; un vecino mejor que el centro no cambia la candidata; un vecino nunca aparece
      en la salida; la salida solo puede ser `[]`, `[B2]`, `[S2]` o `[B2, S2]`; ALTA, la
      concentración y la ejecutabilidad no cambian el veredicto.
   6. **LOCRO:** quita exactamente las señales de la región **de los dos brazos**, conserva GLOBAL y
      EM, usa la espina de la población completa y aplica los umbrales de pares relativos (50.718 /
      59.967 / 74.969). Incluye un caso que falla con el denominador absoluto: una subpoblación
      sintética sana que, con 91.126, saldría NO_ESTIMABLE. La ruta del LOCRO se niega sin la marca de
      ejecución.
   7. **Sin desenlaces ni estimaciones nuevas en el preflight** (D-66, OD-P5-16):
      - el evaluador lanza un error para cualquier geometría distinta de C0, B2 y S2;
      - un test por ruta intenta calcular, antes de la marca, una estimación (con desenlaces) del
        LOCRO, de regiones y subpoblaciones, de estratos, de concentración por activo, de los vecinos
        o cualquier estimación nueva de P5, y espera la excepción;
      - otro test comprueba que el censo estructural por región, los denominadores del LOCRO y el
        recuento estructural sí se calculan en el preflight, sin desenlaces;
      - la API del preflight no devuelve eventos ni `net_R` por `signal_id`, y la evidencia del
        preflight no los contiene.
   8. **Reproducción de P4:** C0 por identidad (`ManagedEvent` y hash); B2 y S2, igualdad de cadenas
      con `_cell` contra las filas y columnas de la lista blanca de OD-P5-16. Una divergencia
      inyectada produce STOP, sin tolerancia y sin reescribir el valor esperado.
   9. **Hash:** `advisor_config_hash` de C0 = `89406d28…6387`; serialización canónica estable; los
      campos duplicados coinciden.
   10. **Recuento:** derivado de la estructura antes de abrir desenlaces (STOP si no da 71) y de las
       salidas después, con la fórmula de la sección 29.
   11. **Vecinos nunca elegibles:** ninguna celda con `rol = DIAGNOSTICO_SUPERFICIE` (en particular,
       ninguna con `m3_auxiliar = true`) puede aparecer en la salida ni recibir hash de política
       candidata.
   12. **Ejecución única:** la marca se escribe antes de abrir los desenlaces nuevos y el ejecutor se
       niega si ya existe.
   13. **Producción intacta:** `config.yaml`, el backtest `--vintage` normalizado y la suite, iguales.
4. **Paso 3 — revisión de look-ahead previa**, por un agente independiente, sobre el código y el
   preflight.
5. **Paso 4 — una única ejecución** sobre el SHA congelado del ejecutor.
6. **Paso 5 — registro del resultado (D-nn), revisión final y decisión sobre GATE P5.** Regla del
   propietario: el gate se cruza solo con 0 BLOCKER y 0 IMPORTANTE.

## 35. Plan de revisión independiente

- **Diseño:** Codex, en solo lectura, antes de redactar (`evidence/2026-10-02-T-021-p5-diseno/
  codex-revision-diseno.md`; respuesta a cada hallazgo en «Revisión de la ficha»).
- **Ficha:** revisor independiente adversarial, en solo lectura, con el mandato de demostrar que el
  diseño permite escoger el resultado a posteriori.
- **Código:** revisión de look-ahead antes de ejecutar.
- **Resultado:** revisión final antes de cruzar GATE P5.

## 36. Handoff a P6

P5 solo decide si B2 y/o S2 pasan como políticas candidatas. **P6** las probará como **sistemas
completos**: capital, posiciones simultáneas, ocupación, exposición por región, divisa y sector,
costes, slippage, dividendos, orden cronológico real, métricas de cartera y exceso sobre el
buy-and-hold del mismo universo.

Pasa a P6 como FOLLOW_UP / HANDOFF, sin mezclarse con P5:
- `economic_currency` se guarda y no se usa (roadmap, «Hallazgos abiertos»);
- `RR_TOO_LOW` vuelve a ser alcanzable con holgura de entrada (B2 tiene 0,75·A);
- **el dividendo no entra en el P&L del laboratorio**, y el sesgo depende de la geometría (T-020
  §19): favorece a los stops más anchos (S2 y los vecinos con `s` mayor) y perjudica a los objetivos
  lejanos (B2 y la fila `m2 = 5,25`). P5 lo hereda como limitación y no lo corrige;
- la entrada real es a la apertura con veto (E1 fue NO CONCLUYENTE); P5 mide al cierre, como P4.

## 37. Handoff al siguiente agente

- **Estado:** pre-registro con las OD-P5 cerradas en D-66. P5 **no** se ha ejecutado y no se ha
  calculado ningún resultado de ningún vecino. El único cálculo sobre la cosecha es el inventario
  estructural sin desenlaces de la sección 10.3.
- **Siguiente:** fijar el `P5_PREREG_SHA` (el HEAD documental tras la revisión final del
  pre-registro, con 0 BLOCKER y 0 IMPORTANTE) y, **con una autorización nueva**, el paso 2.
- **Prohibido sin esa autorización:** implementar `p5.py`; evaluar desenlaces de cualquier celda;
  ejecutar P4 o `comparacion-pareada`.

## Revisión de la ficha

### Revisión de diseño de Codex (antes de redactar)

Encargo y respuesta literales en `evidence/2026-10-02-T-021-p5-diseno/`. Solo lectura, sin
desenlaces: **1 BLOCKER, 6 IMPORTANTE, 1 MENOR y 1 OBSERVACIÓN.**

- **BLOCKER — el paso de 0,25 contradice T-020 §7.** Se redefine P5 como prueba de sensibilidad
  local a escala inferior a la de P4, con evidencia estructural de que la perturbación no queda
  absorbida por la regla de soporte, y la escala de P4 queda como alternativa B de OD-P5-2 con su
  degeneración (sección 11.2).
- **IMPORTANTE — IC95 > 0 por vecino es exigente.** Se adopta su significado («mantiene una señal
  positiva clara»), se publican las características operativas y se descarta la regla de la mitad
  del centro, por curvatura (secciones 23.3 y 23.4).
- **IMPORTANTE — asimetría entre B2 y S2 en los semiplanos.** Se declara y se explica por la
  frontera `min_rr` (sección 11.6).
- **IMPORTANTE — `target3` es inerte en los desenlaces, pero no en la configuración completa.** C
  queda como recurso diagnóstico rotulado `m3_auxiliar`, nunca como equivalencia (sección 12.2).
- **IMPORTANTE — degeneración parcial por la regla de soporte.** Se midió sin desenlaces: como
  mucho, el 19,6 %; se publica por celda (secciones 10.3 y 14).
- **IMPORTANTE — el LOCRO no es un leave-one-out literal.** Se rebautiza LOCRO y se justifica
  (sección 19.2).
- **MENOR — «0 confirmatorias» solo si P5 es filtro.** Formulado así (sección 22).
- **OBSERVACIÓN — separar el LOCRO de la bandera ALTA.** Hecho (sección 19.2).

### Revisión adversarial independiente de la ficha (primera vuelta)

Agente `revisor` nuevo, en solo lectura y sin desenlaces, sobre `3e597db`. Mandato: demostrar que el
diseño permite escoger el resultado a posteriori. Informe literal en
`evidence/2026-10-02-T-021-p5-diseno/revision-independiente-ficha.md`: **1 BLOCKER, 1 IMPORTANTE, 5
MENOR y 2 OBSERVACIÓN.** No encontró ninguna forma de escoger el resultado después de medir.
Comprobó correctos el inventario (las 18 filas contra el JSON), el álgebra, la inercia de `target3`,
el recuento (71 / 56 / 518), las aproximaciones de la sección 23.4, las cifras de P4 y de la sección
19.1, el hash y los bloques. También comprobó que la ficha cubre los 38 puntos pedidos.

- **BLOCKER B-1 — el LOCRO nunca podía ser estimable** (pares ≥ 90 % de 101.251 en poblaciones de
  56.353, 66.629 y 83.298 señales): la salida `[]` quedaba decidida por el texto. **Corregido:**
  - la condición de pares del LOCRO es relativa a la población sin la región, con los tres umbrales
    fijados desde el censo (sección 19.2);
  - la capacidad del LOCRO es elegible en OD-P5-8 (i/ii/iii), con la consecuencia de ii escrita;
  - el test 6 incluye un caso que falla con el denominador absoluto.
- **IMPORTANTE I-1 — la tolerancia de S2 estaba mal descrita.** **Corregido:** la tolerancia efectiva
  está en las secciones 11.6 y 23.2 (los dos vecinos iso-RR de S2 tienen que ser ACEPTABLES); la
  probabilidad por candidata (≈ 0,77 en B2 y ≈ 0,83 en S2) está en la sección 23.4 y en OD-P5-4 y
  OD-P5-5.
- **MENOR.**
  - OD-P5-2 B: añadido que S2 saldría FRÁGIL por construcción a la escala de P4; corregida la cuenta
    de pasos (sección 11.2).
  - Formato de las OD: consecuencias de A en OD-P5-6, OD-P5-9 y OD-P5-13; umbrales de la meseta
    elegibles en OD-P5-4; capacidad del LOCRO en OD-P5-8.
  - Preflight: no calcula ninguna estimación nueva, la ruta del LOCRO exige la marca, y el test 7 lo
    comprueba (OD-P5-16).
  - 80–86 % → 78–86 %.
  - Paso diagonal de C0 (sección 5) e incoherencias que incluyen señales de soporte (secciones 10.2 y
    10.3).
- **OBSERVACIÓN.** La neutralidad a la distancia queda como supuesto declarado, con el apoyo parcial
  de B1/B2 (sección 23.3). Las etiquetas de salida del envoltorio son ahora las constantes del código
  (sección 28).

### Segunda revisión de Codex, sobre la ficha (`3e597db`)

Encargo y respuesta literales en `evidence/2026-10-02-T-021-p5-diseno/codex-encargo-ficha.md` y
`codex-revision-ficha.md`. Solo lectura: **1 BLOCKER, 3 IMPORTANTE, 1 MENOR y 2 OBSERVACIÓN**. Las
cuatro afirmaciones sobre código y evidencia se comprobaron antes de corregir: `salidas` de P4 sin
C0; `_cell` a 6 decimales; `level_estimate` sobre todos los eventos observables; `pair_populations`
con los mismos `signal_id`. Codex confirma también que sus hallazgos de diseño están cerrados.

- **BLOCKER — P4 no publica C0 como salida reproducible.** **Corregido** en OD-P5-16 y el test 8: C0
  se reproduce por identidad (`ManagedEvent` y hash), y B2/S2 por sus filas nombradas.
- **IMPORTANTE.**
  - Contrato operativo del LOCRO (filtrar los dos brazos, espina completa): sección 19.2.
  - Población de cada métrica (ΔR sobre pares finales; nivel y PF sobre todos los eventos
    observables de la celda): sección 15.
  - Regla de comparación de la reproducción (sin líneas `#`, columnas nombradas, igualdad de cadenas
    con `_cell`): OD-P5-16.
- **MENOR — la serialización no es literalmente `canonical_hash`.** **Corregido:** P5 define su
  propia función canónica con `allow_nan=False` y sin `default` (sección 28).
- **OBSERVACIÓN.** Sin acción: confirman que la infraestructura existe y que el Bonferroni es
  determinista.

### Segunda vuelta del revisor independiente (`c53f882`)

El mismo agente `revisor`, en solo lectura y sin desenlaces. **Los nueve hallazgos de la primera
vuelta, CERRADOS**; **0 BLOCKER y 0 IMPORTANTE** nuevos. Comprobó:
- los umbrales del LOCRO (⌈0,9·n⌉);
- las probabilidades por candidata (0,774 / 0,831) y las de la anchura 1,0 (0,152 / 0,659);
- que OD-P5-16 no permite calcular nada decisorio que P4 no publicara;
- que los cambios de Codex reproducen el comportamiento del código de P4 sin decisiones ocultas;
- la coherencia entre las secciones 15, 19.2, 23, 24, 26, 29 y 33.

Dejó 1 MENOR y 3 OBSERVACIÓN, todos de redacción y corregidos después:
- **MENOR:** la fila `primaria_60` de P4 **es** la de Bonferroni. OD-P5-16 nombra ahora las claves y
  columnas exactas.
- **N-1:** la condición 1 de la sección 26 remite a OD-P5-16 en lugar de decir «exactamente».
- **N-2:** del IC95 de los centros solo se compara la anchura; el preflight no archiva desenlaces por
  señal (sección 30).
- **N-3:** la recomendación de OD-P5-8 es «A, con la capacidad i»; «en A, B y C».

Con la regla del propietario (0 BLOCKER y 0 IMPORTANTE), la ficha queda lista para cerrar las OD-P5.

### Revisión final del pre-registro (sobre la versión con D-66, `53b2f48`)

El mismo agente `revisor`, en solo lectura y sin desenlaces, con el mandato de comprobar solo que D-66
se transcribió fielmente y que no aparece ningún grado de libertad nuevo. Informe literal en
`evidence/2026-10-02-T-021-p5-diseno/revision-final-preregistro.md`.

**0 BLOCKER, 0 IMPORTANTE, 2 MENOR y 2 OBSERVACIÓN.** Los 12 puntos pedidos por el propietario
CUMPLEN:
1. `m3_auxiliar` nunca es elegible;
2. hay exactamente 13 vecinos válidos;
3. las 3 ausencias de S2 no entran en ningún denominador;
4. S2 mantiene su tolerancia asimétrica;
5. el umbral 0,75 es fijo;
6. `|NE| ≤ 1`;
7. el LOCRO usa denominadores relativos;
8. 0 confirmatorias nuevas;
9. ningún vecino es elegible;
10. el preflight no puede producir LOCRO ni vecinos;
11. las 71 comparaciones se derivan de la estructura, con STOP si no;
12. P5 no es validación.

Corregido después, sin cambiar ninguna regla:
- **MENOR:** la sección 27 ya no plantea como abierta la promoción de vecinos (OD-P5-13 está cerrada).
- **MENOR:** «regiones» en el preflight significa **estimaciones** por región. El censo estructural
  por región, los denominadores del LOCRO y el recuento estructural, que no usan desenlaces, sí se
  calculan en el preflight (OD-P5-16, regla 5; test 7). La misma precisión se aplica al punto 17 de
  D-66.
- **OBSERVACIÓN:** los vecinos publican su hash como `diagnostico_sha256`, nunca como
  `policy_sha256` (sección 28).
- **OBSERVACIÓN:** quitados los restos de «recomendación» fuera de la sección 33.


## Cierre (2026-10-03)

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

- **Ejecución única:** marca a las 09:44:05 UTC, recuento derivado 71, `p5-parada.json` inexistente,
  y `código de salida: 0` archivado en la consola. P5 no se repite.
- **Resultado y superficies completas:** `evidence/2026-10-03-T-021-p5-cierre/resultado-p5.md`
  (transcripción literal de `run/`, sin recalcular) y D-67.
- **Políticas candidatas:** `[B2, S2]`, con `config` completa y `policy_sha256` en
  `evidence/2026-10-03-T-021-p5-cierre/politicas-finales.json`. P5 no ordena una sobre la otra.
- **Revisión final independiente:** 0 BLOCKER, 0 IMPORTANTE, 0 MENOR y 1 OBSERVACIÓN sin impacto
  (`revision-final.md`). GATE P5 cruzado (D-68, `gate-p5-final.md`).
- **Handoff a P6:** P6 (sistema completo con exceso sobre el buy-and-hold del universo) recibe B2 y
  S2 como políticas candidatas de investigación. Está desbloqueado, pero **no iniciado**: su ficha
  necesita una autorización aparte. Producción no cambia: ninguna de las dos se activa,
  `config.yaml` sigue en `"1.0"` con C0, Score v2 sigue inactivo y la Pi en `v0.4.1`. El resultado es
  de desarrollo; la validación independiente sigue en P7 (INV-15).
