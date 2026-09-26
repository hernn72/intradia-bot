# T-019 — Score v2 y umbrales por horizonte, con P3 pre-registrado (A-03)

Estado: PENDIENTE — ficha aprobada el 2026-09-26 y commiteada como
**pre-registro de P3**. Decisiones cerradas por el propietario ese mismo día:
A → **D-45**, B → **D-46**, C → **D-47** (alternativa C2), D → **D-48**
(alternativa D1). GATE P3 requisito 2 corregido por D-45. Lista para
implementar desde el paso 1.
Agente: Opus (ficha) → propietario (A–D) → Codex (implementación) → Claude Code
(verificación real y commits) → revisor independiente (look-ahead, obligatorio)
Línea / fase: Línea A, A-03 (P3)
Gate al que contribuye: **GATE P3** (es la tarea que lo cruza)

## Objetivo
Definir Score v2 sin el RR (D-43) y sin `convicción` (D-46), con un
`score_model_version` nuevo, un contrato de umbrales **por horizonte** con estado
`calibrated` ligado a la versión del modelo, y ejecutar P3 **una sola vez** con el
experimento pre-registrado en esta ficha, publicando ordenación, ablación,
sesgo de universo e impacto, de modo que los cinco requisitos de GATE P3 queden
respondidos con evidencia, **salga lo que salga**.

## Por qué existe
- **D-43** (2026-09-21) sacó el RR del score como dimensión de puntuación y
  obligó a P3 a crear un `score_model_version` nuevo, recalibrar por horizonte
  con el primario de INV-14 y no asumir equivalencia entre bandas viejas y
  nuevas. El RR **sigue** siendo condición de ejecutabilidad y de riesgo.
- **D-42 / A-02** dejó medido, con el primario de INV-14, que en swing la
  capacidad es `INSUFICIENTE`/`LOW` y **ninguna banda es concluyente**, y que
  **medio es inválido** para calibración y conclusión (último bloque ocupado de
  102 sesiones frente a `MAX_HOLD_BARS` = 250). Evidencia:
  `evidence/2026-09-21-T-013-laboratorio-rehecho/`.
- GATE P3 exige umbrales «calibrados por horizonte (swing y medio por
  separado)»; con la evidencia de A-02 eso es literalmente imposible para medio.
  Esta ficha propone cómo resolver esa contradicción **sin tocar `gates.md` en
  silencio** (decisión A).

## Qué NO es esta ficha
- No es P4: no se toca la geometría, ni `min_rr`, ni `entry_max_rr`, ni
  `RR_TOO_LOW`, ni la invariante de no recomendar una entrada que viole el RR
  mínimo (INV-01, INV-02).
- No amplía la cosecha, no cambia los bloques (60 swing / 300 medio), no cambia
  el estimador primario y no elige otra métrica para conseguir resolución (FU-1
  de A-02 sigue abierto y **no** se resuelve aquí).
- No despliega nada en la Pi. La Pi queda en `v0.3.0` (`03e1ec3`), esquema v5.
  Cualquier despliegue es una decisión posterior y separada.
- No redefine el score después de ver resultados: la ablación publica, no
  selecciona (sección «P3 — ablación»).

## Dependencias previas
- **GATE P2 cruzado** (D-42, D-43), T-013 ACEPTADA.
- Pre-registro del estimador de bloque del 2026-09-02 (INV-14, D-03).
- `main` en `b658541` (T-018 aceptada; la caché de barras no afecta a la
  cosecha congelada).
- **D-45, D-46, D-47 y D-48** (decisiones A, B, C y D de esta ficha), cerradas
  por el propietario el 2026-09-26 y registradas en `docs/decision-log.md` en el
  mismo commit que esta ficha, junto con la corrección de `docs/gates.md`.

## Hechos verificados sobre el terreno el 2026-09-26
Comprobados sobre `main` = `b658541ee53c9a868ec96c2ad34fc8eefaa204c8`. Antes de
escribir esta ficha el árbol estaba limpio salvo `graphify-out/` y
`ultima_cerrada` (sin seguimiento, no son de esta tarea); después, solo esta
ficha y la fila A-03 de `docs/roadmap.md`. La cosecha `071ddb2b…` está presente en `data/vintages/`.

### Score v1 tal como es hoy (`advisor/analysis/scoring.py`)
`SCORE_MODEL_VERSION = "1.0"`. Seis dimensiones con peso fijo; cada una se
reescala a su peso sobre los componentes con dato (`Dimension.points = weight ·
raw_points / raw_max`); una dimensión sin componentes con dato, o con
`unavailable_reason`, sale del denominador.

| Dimensión | Peso | Componentes (máximo bruto) | Entradas |
|---|---|---|---|
| catalizador | 20 | volumen 8 · hueco 6 · ruptura 6 | `snapshot` |
| fundamental | 20 | ninguno: **siempre no disponible** (no hay proveedor) | `config.fundamentals_enabled` |
| técnico | 20 | cruce EMA 5 · SMA larga 4 · RSI 4 · MACD 4 · fortaleza relativa 3 | `snapshot` |
| beneficio/riesgo | 20 | ratio B/R: 20 / 15 / 10 / 5 / 0 en ≥3 / ≥2 / ≥1,5 / ≥1 / <1 | `levels.rr_ratio` |
| contexto | 10 | «régimen» = `MarketContext.points` (tendencia 4 · VIX 4 · Asia 2) | `context` |
| convicción | 10 | histórico 4·min(1, barras/min_bars) · indicadores 4·presentes/6 · estabilidad ATR% 2/1,5/1/0,5 | `snapshot`, `min_bars` |

- `Score.evaluable_max` = suma de pesos de dimensiones disponibles: **80**
  habitual (fundamental fuera).
- `Score.points` = suma de puntos (0–80 habitual).
- `Score.value` = `100 · points / evaluable_max` (0–100); 0 si `evaluable_max`
  es 0.
- `Score.grade`: ≥90 «Excepcional», ≥80 «Muy atractiva», ≥70 «Interesante»,
  ≥60 «Vigilancia», resto «No operar» — **cortes v1 codificados**.
- Firma: `compute_score(snapshot, levels, context, config: ScoringConfig,
  min_bars)`. `levels` solo lo usa la dimensión RR; `min_bars` solo convicción;
  de `ScoringConfig` solo `fundamentals_enabled`.

### Inventario real de llamantes (búsqueda de símbolos, no rutas de ficha)

**`compute_score`** — tres llamantes de producción/investigación y tests:
- `advisor/analysis/analyzer.py:203` (producción: `analizar`, `seguimiento`,
  `pasada-evento`).
- `advisor/backtest/engine.py:174` (`backtest`, también `--vintage`).
- `advisor/research/event_study.py:649` (event study, capacidad, ablación,
  filtro de ejecución).
- Tests: `tests/test_analysis.py` (385–481), `tests/test_ai.py:28`,
  `tests/test_report.py:59, 595, 863`.
- Tests que leen `score.value` y fijan números v1:
  `tests/test_analysis.py:399, 407, 422, 538, 669, 706, 863, 956`,
  `tests/test_analyzer.py:199, 214` (orden por nota), `tests/test_bar_cache.py:597`.

**`SCORE_MODEL_VERSION` / `score_model_version`**:
- `advisor/run/manifest.py:23, 59, 138` → columna `analysis_run.score_model_version`
  (`advisor/storage/migrations.py:29, 112, 136, 171, 178`; NOT NULL).
- Las recomendaciones **no** llevan versión propia: la heredan por
  `recommendation.run_id → analysis_run`. Las filas anteriores a la migración de
  `run_id` no tienen versión.
- `position_review.score` (`advisor/storage/db.py:104–110, 846`) se persiste
  **sin versión y sin `run_id`** (hallazgo H-2).
- Test: `tests/test_migrations.py:289, 313, 373`.

**`min_score_operar` / `min_score_vigilar`** (hoy globales en `ScoringConfig`,
`advisor/config.py:105–116`, y en `config.yaml` 70/60):
- `advisor/analysis/opportunity.py:255–265` (`classify_setup_detailed`, que
  alimentan `classify`, `classify_setup` y `build_opportunity`).
- `advisor/report/tracking.py:78–85` (`_verdict` del seguimiento de posiciones).
- Tests: `tests/test_config.py:79–80`, `tests/test_analysis.py:718, 761`,
  `tests/test_report.py:587, 826`.

**`Score.value`**:
- Clasificación: `opportunity.py:253` (umbrales).
- Orden del informe: `analyzer.py:298` (orden por `score.value`, luego RR).
- Persistencia: `advisor/main.py:122–123` (`recommendation.score`,
  `evaluable_max`); `tracking.py:125` → `position_review.score`.
- Investigación: `research/observations.py:71–72` (`SignalObservation.score_value`),
  `research/event_study.py:525` (`score_band`), `research/capacity.py:344`,
  `research/ablation.py:119–157`, `research/execution_filter.py:344`,
  `backtest/engine.py:179` → `backtest/report.py:202, 242` (`_SCORE_BUCKETS`).
- Presentación: `report/formatter.py:278, 311, 593, 706, 777`,
  `ai/agents.py:115`.
- Etiqueta de «convicción» del dimensionamiento: `analysis/sizing.py:38–43`
  (`conviction_label`, ≥80 / ≥70, **cortes v1 codificados**; informativa, no
  dimensiona).

**`Score.grade`**: `report/formatter.py:278, 311`, `ai/agents.py:115`.

**Dimensión `conviccion` leída fuera del score**: `Opportunity.confianza`
(`opportunity.py:151–165`) usa `conviccion.points / weight` para decidir
Alta/Media/Baja, y `report/formatter.py:374` la imprime. Tests que nombran la
dimensión: `tests/test_analysis.py`, `tests/test_ablation.py`.

**`classify()`** (`opportunity.py:177`): llamado desde
`build_opportunity` (`opportunity.py:357`) y `backtest/engine.py:176`
(`POLICY_OPERAR`). `classify_setup` desde `backtest/engine.py:175`. Tests que
llaman a `classify()` directamente: `tests/test_analysis.py:408, 524, 535, 544,
551, 568, 578, 586, 594, 606, 626, 635, 643, 665, 675, 701, 797` y
`tests/test_backtest.py:361`; los que fijan un resultado con 70/60 globales
cambian con el paso 1. El event
study **no** llama a `classify()` (P2.3/P2.4).

**Bandas v1 codificadas en investigación**: `research/event_study.py:42`
`SCORE_BANDS` (<50, 50-60, 60-70, 70-80, 80+), reutilizada por
`execution_filter.py:27, 255, 344` y `capacity.py:741`; `backtest/report.py`
`_SCORE_BUCKETS`; `research/ablation.py:424–427` (cortes 60 y 70 literales).

**Producción ejecuta solo swing**: `deploy/systemd/intradia-bot.service:16`
(`analizar --horizonte swing --telegram`) y `intradia-bot-event.service:16`
(`pasada-evento --horizonte swing`). Medio e intradía solo por CLI manual.

### Hechos que condicionan P3 y que se conocen **antes** de medir
1. **La población del event study no depende del score.** Son todas las barras
   con niveles válidos (`event_study.py:313–338`); el score solo etiqueta. Por
   tanto el primario **global** de swing de P3 será el mismo que publicó A-02:
   `+0.064 R`, IC95 `[-0.060, 0.171]`, anchura 0,231 > 0,200, 21 bloques,
   `INSUFICIENTE`/`LOW`. No es un resultado de P3: es aritmética.
2. **Con 21 bloques, `SUFICIENTE`/`HIGH` es inalcanzable** en swing, porque
   `CapacityThresholds.sufficient_blocks` = 25. El mejor veredicto posible de
   cualquier fila de swing es `LIMITADA`.
3. **Cualquier subconjunto del score (banda, umbral) tiene como mucho los mismos
   21 bloques y menos señales por bloque**, así que lo esperable es que sus
   intervalos sean más anchos que el global. Un contraste **pareado por bloque**
   (alta − baja en el mismo bloque) puede estrecharse, porque el régimen común se
   cancela; por eso el contraste es la medida confirmatoria (sección P3).
4. **Previsión honesta, escrita antes de medir:** lo más probable es que P3 salga
   **NO CONCLUYENTE** y que **ningún** horizonte quede `calibrated: true`. La
   ficha está diseñada para que ese resultado sea válido y cruce GATE P3 con su
   etiqueta, no para evitarlo.
5. **P3 consume la cosecha completa (2021-08-30 → 2026-08-28).** Ninguna parte
   de esa ventana puede servir después como holdout de P7 para los umbrales
   calibrados aquí (INV-15): el holdout tendrá que ser posterior.

### Hallazgos de la inspección (clasificados, `docs/metodo-trabajo.md` §5)
- **H-1 — INV-06: el contexto de producción y el del laboratorio no reciben lo
  mismo. BLOCKER de la calibración, no de la ficha.** Producción pasa
  `asia_change_pct` (`analyzer.py:245–248` → `fetch_market_context`); el event
  study y el backtest llaman a `build_market_context` **sin** ese argumento
  (`event_study.py:643`, `backtest/engine.py:168`), así que en investigación el
  componente Asia vale **siempre 1,0** (el neutro de `MarketContext.points`) y
  en producción varía entre 0 y 2. Misma función, entradas distintas: un umbral
  calibrado en el laboratorio se aplicaría en producción a una nota que puede
  diferir **±2,0 puntos en Score v2** (±1 de 50 evaluables) y ±1,25 en v1. En
  v2 el contexto pesa 10 de 50 (20 %), frente a 10 de 80 en v1.
  **No es la única diferencia de entrada** (señalado por Codex en la revisión
  de la ficha y reproducido): el laboratorio y el backtest usan el **VIX con una
  vela de retraso** (`event_study.py:309`, `backtest/runner.py:210`,
  `shift(1)`), mientras producción usa el último VIX cerrado
  (`market_context.py:159–170`); y el **seguimiento de posiciones** repuntúa con
  un contexto **sin** Asia (`report/tracking.py:109`), distinto del de la
  pasada diaria. Hay por tanto tres versiones del contexto: la del laboratorio,
  la de `analizar` y la de `seguimiento`. Requiere la decisión D.
- **H-2 — `position_review.score` sin versión. SAME_SCOPE.** Con dos modelos
  coexistiendo, una revisión persistida no dice con qué modelo se puntuó.
  Migración v6 (sección «Implementación», paso 1).
- **H-3 — Cortes v1 codificados fuera de `config.yaml`. SAME_SCOPE.**
  `Score.grade` (90/80/70/60) y `conviction_label` (80/70) aplicarían bandas v1
  a una nota v2 sin que nadie lo decidiera. Prohibido por D-43.
- **H-4 — `Opportunity.confianza` depende de la dimensión `conviccion`.
  SAME_SCOPE**, consecuencia directa de la decisión B.
- **H-5 — OBSERVATION.** `confianza` nunca puede ser «Alta» hoy: exige
  `missing_dimensions == 0` y fundamental falta siempre. No se corrige aquí; se
  conserva la regla y se anota.
- **H-6 — OBSERVATION / FOLLOW_UP ya conocido.** El contexto imputa un valor
  neutro cuando falta tendencia, VIX o Asia (`market_context.py:62–77`), con
  regla escrita en el docstring, así que no viola INV-16 en la letra; pero en v2
  su peso relativo sube. Se publica en el impacto cuántas señales de la cosecha
  puntúan contexto con algún componente imputado.
- **H-7 — Las bandas v1 están codificadas en cinco sitios de investigación**
  (ver inventario). SAME_SCOPE: v2 no puede usarlas.

## Decisiones que esta ficha necesita antes de código

**Cerradas el 2026-09-26.** El propietario aprobó A, B, C2 y D1, registradas
como **D-45, D-46, D-47 y D-48** en `docs/decision-log.md`, que es el texto que
manda. Se conserva abajo el razonamiento y las alternativas con que se
propusieron.

### DECISIÓN A — Medio frente a GATE P3 (metodológica, cambia un gate) · **D-45**

**Contradicción literal.** GATE P3 requisito 2 exige umbrales «calibrados por
horizonte (swing y medio por separado) con el estimador primario (INV-14)».
D-42 declara los números de medio «no utilizables para calibración ni
conclusión». Cumplir la letra del gate obligaría a calibrar con datos
declarados inválidos, o a ampliar la cosecha dentro de A-03, que también está
prohibido.

**Texto aprobado (D-45):**

> **D-45 — GATE P3 requisito 2: medio queda sin calibrar mientras su evidencia
> sea inválida, y ningún umbral v1 se hereda.**
> GATE P3 exigía calibrar swing y medio por separado. A-02 (D-42) invalidó medio
> para calibración y conclusión: su último bloque ocupado mide 102 sesiones y
> `MAX_HOLD_BARS` vale 250. Calibrar medio con esos números contradice P2.5, y
> conseguir datos válidos exige una cosecha más larga, que es FU-1 y no cabe en
> A-03. Se decide:
> 1. **Swing** puede calibrarse en P3 con la regla pre-registrada en T-019. Si
>    la regla no se cumple, queda `calibrated: false`.
> 2. **Medio** queda `calibrated: false` sin intentar calibración. P3 publica
>    sus números solo por trazabilidad, marcados inválidos.
> 3. **Intradía** queda `calibrated: false` (sin laboratorio: P2 solo cubre
>    swing y medio).
> 4. **No se heredan los umbrales 70/60 de Score v1** en ningún horizonte de
>    Score v2, ni por equivalencia de escala ni por equivalencia de percentil.
> 5. Un horizonte `calibrated: false` **no puede presentarse** como score
>    operativamente calibrado en ningún informe, mensaje ni persistencia.
> 6. Si la ordenación de P3 sale NO CONCLUYENTE, GATE P3 se cruza con esa
>    etiqueta, como ya dice `docs/gates.md`, y P4 trabaja sobre `score_signal`
>    sin umbrales operativos nuevos.
> Reabrir la calibración de medio exige una cosecha nueva cuyo último bloque
> ocupado supere `MAX_HOLD_BARS`, con `data_vintage_id` nuevo, y una ficha nueva.

**Requisito 2 de GATE P3 corregido** (aplicado a `docs/gates.md` en el mismo
commit que registra la decisión):

> 2. Umbrales `min_score_operar` / `min_score_vigilar` declarados **por
>    horizonte** (swing, medio e intradía por separado), cada uno con estado
>    `calibrated` explícito y ligado al `score_model_version` al que pertenecen.
>    Un horizonte solo puede quedar `calibrated: true` si sus umbrales salen de
>    la regla pre-registrada en la ficha de P3, aplicada con el estimador
>    primario (INV-14) sobre datos que P2.5 no declare inválidos para ese
>    horizonte. Medio queda `calibrated: false` mientras su evidencia sea
>    inválida (D-42) y, en ese caso, el requisito se cumple publicando el motivo;
>    intradía queda `calibrated: false`. Ningún umbral de un `score_model_version`
>    se reutiliza en otro. (Corregido el 2026-09-26 por D-45: el texto anterior
>    exigía calibrar medio, lo que D-42 hizo imposible con la cosecha vigente.)

### DECISIÓN B — `convicción` sale del score numérico (metodológica, cambia un contrato) · **D-46**

**Por qué se decide aquí y sin mirar P3.** Dos de sus tres componentes miden
**calidad y disponibilidad del dato** —cobertura de barras e indicadores
presentes—, no el setup; y el proyecto separa explícitamente score y calidad del
dato (INV-03: el score no depende de la calidad del dato). El tercero, la
«estabilidad» por ATR%, sí es una propiedad del activo, pero nunca se
pre-registró como predictor y va escondido bajo un nombre que no lo describe.
El argumento es de arquitectura, no de rendimiento, así que se decide antes de
medir. **No he encontrado ninguna razón contractual que lo impida**: ningún
documento normativo fija seis dimensiones (solo `README.md:137` las describe,
y se actualiza con la implementación); el único acoplamiento es
`Opportunity.confianza` (H-4), que se resuelve moviendo el cálculo a donde
pertenece.

**Texto aprobado (D-46):**

> **D-46 — `convicción` sale de Score v2; su contenido de calidad del dato pasa a
> la confianza, y el ATR% no se conserva escondido.**
> La dimensión `convicción` (10 puntos) mide cobertura de barras (4),
> indicadores disponibles (4) y «estabilidad» por ATR% (2). Los dos primeros
> son calidad del dato, que por arquitectura no puntúa (INV-03). Se decide:
> 1. Score v2 **no** contiene `convicción`.
> 2. Cobertura de barras e indicadores disponibles siguen existiendo como
>    **confianza del análisis** (`Opportunity.confianza`), calculada desde el
>    snapshot, **fuera** de `compute_score`, y **no** se convierten en puntos.
> 3. El ATR% **no** se conserva dentro de ninguna otra dimensión ni de la
>    confianza. Si se quiere estudiar la volatilidad como predictor, se abre como
>    señal o dimensión explícita, pre-registrada y medida por separado.
> 4. Los 30 puntos retirados (RR 20 + convicción 10) **no se redistribuyen**:
>    no se suben pesos para volver a sumar 100. El score se normaliza sobre los
>    puntos evaluables, como ya hacía.
> 5. La decisión se toma por arquitectura y **antes** de ver P3; la ablación de
>    P3 no la reabre.

### DECISIÓN C — Qué hace producción mientras Score v2 no tenga umbrales calibrados (propietario) · **C2, D-47**

Es de propietario porque cambia lo que el asesor recomienda.

- **Pregunta:** si P3 sale NO CONCLUYENTE y swing queda `calibrated: false`,
  ¿qué modelo y qué umbrales usa producción?
- **Alternativas:**
  - **(C1) v2 activo sin umbrales.** El score v2 se muestra como señal
    ordenable, pero ningún horizonte puede llegar a OPERAR por score:
    `SCORE_UNCALIBRATED`, radar VIGILAR / ESPERAR. El asesor deja de emitir
    COMPRAR hasta que haya calibración.
  - **(C2) v1 sigue activo en producción hasta que v2 tenga umbrales
    calibrados.** Score v1 y sus 70/60 siguen siendo coherentes entre sí (misma
    escala), pero se declaran `calibrated: false`, porque A-02 midió que
    ninguna banda v1 es concluyente. v2 vive en el código y en investigación
    (misma función, versionada: INV-06 se cumple en el código, no en la versión
    activa). El RR sigue puntuando en producción hasta entonces, contra el
    espíritu de D-43 aunque no contra su letra («a partir de P3»).
  - **(C3) v2 activo con umbrales provisionales elegidos por el propietario**,
    declarados `calibrated: false` en todas partes. Prohibido derivarlos de
    70/60 o de percentiles v1 (sería la conversión automática de bandas que
    D-43 prohíbe); tendría que ser una elección explícita con su motivo.
- **Consecuencias:** C1 es la más honesta y deja el producto sin compras; C2
  mantiene el producto como está con la etiqueta correcta; C3 mantiene compras
  con un corte que nadie ha medido, igual que hoy pero en otra escala.
- **Recomendación técnica: C2**, con la etiqueta `calibrated: false` visible
  desde el paso 1. Es la única que no introduce un corte nuevo sin medir y no
  deja el asesor inutilizado; y la regla estructural del paso 1 (los umbrales
  declaran su `score_model_version` y el cargador rechaza un desajuste) hace
  **imposible** el estado prohibido «v2 activo con 70/60».
- **Bloquea:** solo el paso 5 (activación de v2 en producción). No bloquea P3
  ni GATE P3.

### DECISIÓN D — Paridad del contexto entre laboratorio y producción (metodológica, H-1) · **D1, D-48**

- **Pregunta:** ¿cómo se eliminan las divergencias de H-1 (Asia, desfase del
  VIX y contexto del seguimiento) antes de calibrar?
- **Alternativas:**
  - **(D1) En Score v2, Asia no puntúa.** El componente sale del cálculo de
    `MarketContext.points` para v2 y la dimensión contexto se reescala sobre
    tendencia + VIX (máximo bruto 8 → peso 10), igual en producción e
    investigación. El dato asiático sigue en el informe como contexto
    descriptivo. Coherente con B: lo que no se puede medir en el laboratorio no
    puntúa.
  - **(D2) Reconstruir Asia en el laboratorio** con los índices asiáticos de la
    cosecha y la misma alineación temporal que producción. Exige demostrar que
    el dato de la sesión asiática posterior al cierre de la barra de señal no es
    look-ahead para la entrada simulada, que P2.3 fija en la apertura
    siguiente. Es trabajo de laboratorio nuevo y con riesgo propio.
  - **(D3) Dejarlo y declararlo.** Los umbrales calibrados tendrían ±2 puntos de
    holgura desconocida en producción.
- **Desfase del VIX, en cualquiera de las tres alternativas:** hay que decidir
  cuál de los dos alineamientos es el correcto **para la hora de la pasada** y
  aplicar el mismo en los dos caminos. El `shift(1)` del laboratorio es la
  opción conservadora contra look-ahead (el VIX cierra a las 22:15 CET, después
  de las plazas europeas); en producción, a las 06 UTC, el último VIX cerrado es
  el de la víspera, que para una barra europea de la víspera es simultáneo.
  Recomendación: que el revisor de look-ahead (GATE P3 requisito 5) fije cuál
  es la alineación sin mirar hacia delante en cada plaza, y que el paso 2 la
  aplique igual en los dos caminos; si difiere de la actual del laboratorio,
  el cambio se mide antes/después en P3 y se declara.
- **Seguimiento:** `review_positions` debe construir el contexto igual que la
  pasada diaria (paso 2), o sus veredictos por umbral compararán una nota que
  no es la de producción.
- **Recomendación técnica: D1** para Asia. Es la única que devuelve INV-06 a su
  sentido pleno sin ampliar el laboratorio. Cambia el contenido de la dimensión
  contexto, y por eso **no** lo decide el implementador: si se aprueba, forma
  parte de la definición de Score v2 y la sección siguiente se lee con
  «contexto = tendencia 4 + VIX 4, reescalado a 10».
- **Bloquea:** el paso 2 (implementar v2) y todo lo posterior.

## Score v2 — especificación

Con D-46 (convicción fuera) y D-48 (componente asiático fuera de v2).

| Dimensión | v1 | v2 | Cambio |
|---|---|---|---|
| catalizador | 20 | **20** | ninguno: mismos componentes y tramos |
| fundamental | 20 | **20** | ninguno: sigue no disponible y fuera del denominador |
| técnico | 20 | **20** | ninguno |
| beneficio/riesgo | 20 | — | **sale** (D-43) |
| contexto | 10 | **10** | el componente asiático no puntúa (D-48): tendencia 4 + VIX 4, máximo bruto 8 reescalado a 10 |
| convicción | 10 | — | **sale** (D-46) |

- **`score_model_version = "2.0"`.** v1 conserva `"1.0"` y su código, porque
  hace falta para reproducir los resultados publicados y para el antes/después.
- **Pesos**: los de la tabla. No se redistribuye nada.
- **Normalización**: la de v1, sin cambios:
  `Score.points` = Σ puntos de dimensiones disponibles;
  `Score.evaluable_max` = Σ pesos de dimensiones disponibles;
  `Score.value = 100 · points / evaluable_max` (0 si `evaluable_max` = 0).
- **`evaluable_max` habitual = 50** (catalizador 20 + técnico 20 + contexto 10).
  Si catalizador queda sin ningún componente con dato, 30; si llegara a haber
  fundamentales, 70 — y **eso sería un modelo nuevo** (`"3.0"`), no una
  variación de v2, porque cambia la escala.
- **Dimensiones no disponibles**: misma regla que v1. Un componente sin dato
  (`points is None`) sale del reparto de su dimensión; una dimensión sin ningún
  componente con dato, o con `unavailable_reason`, sale del denominador. El
  informe declara siempre `evaluable_max` y las dimensiones ausentes.
- **Relación entre magnitudes**: `Score.value` es la única magnitud comparable
  **dentro** de una versión; `Score.points` solo tiene sentido junto a su
  `evaluable_max`. Entre versiones **no** hay magnitud comparable.
- **Firma**: `compute_score(snapshot, context, config, *, model_version)`.
  v2 no recibe `levels` ni `min_bars`: la garantía de que el RR no entra en v2
  es **estructural** (no puede leerlo), igual que INV-03 hoy. v1 conserva la
  firma que necesita detrás del mismo punto de entrada. `Score` gana el campo
  `model_version`, para que ninguna persistencia tenga que adivinarlo.
- **Presentación**: `Score.grade` y `conviction_label` dejan de tener cortes
  propios en v2. Su etiqueta sale de los umbrales del horizonte (sección
  siguiente); si el horizonte no tiene umbrales, «sin umbral calibrado». Las
  etiquetas «Excepcional» / «Muy atractiva» no tienen base medida y no se
  portan a v2.
- **Histórico v1**: una recomendación, revisión o señal v1 **nunca** se compara
  directamente con una v2. Toda tabla o consulta que mezcle filas de las dos
  exige el `score_model_version` de cada una y las separa.

## Contrato de umbrales por horizonte (diseño; sin implementar)

```yaml
scoring:
  fundamentals_enabled: false
  score_model_version: "1.0"        # modelo ACTIVO en producción (C2: 1.0 hasta el paso 5)
  thresholds:
    swing:
      score_model_version: "1.0"    # a qué modelo pertenecen estos números
      calibrated: false
      min_score_operar: 70
      min_score_vigilar: 60
      calibration_ref: null         # "D-nn · evidence/<ruta>" cuando calibrated: true
    medio:
      score_model_version: "1.0"
      calibrated: false
      min_score_operar: 70
      min_score_vigilar: 60
      calibration_ref: null
    intradia:
      score_model_version: "1.0"
      calibrated: false
      min_score_operar: 70
      min_score_vigilar: 60
      calibration_ref: null
```

Reglas de validación en `load_config` (fallan al arrancar, no a mitad de pasada):
1. Cada horizonte de `horizontes` tiene su entrada en `thresholds`. **No** hay
   valor global ni caída a otro horizonte.
2. `thresholds.<h>.score_model_version` == `scoring.score_model_version`. Un
   desajuste es error. Esto hace **imposible** el estado «v2 activo con 70/60
   de v1»: para activar v2 hay que escribir umbrales que declaren `"2.0"`.
3. `min_score_operar` y `min_score_vigilar` son los dos números o los dos
   `null`; con números, `vigilar ≤ operar` (la regla actual).
4. `calibrated: true` exige números y `calibration_ref` no nulo.
5. Las claves globales antiguas `scoring.min_score_operar` /
   `scoring.min_score_vigilar` son error con mensaje explícito; no se migran en
   silencio.
6. `scoring.score_model_version` debe ser una versión implementada.

Semántica:
- `classify_setup_detailed` lee los umbrales **de su `horizonte`**; ya lo
  recibe, así que el cambio está contenido (protocolo, regla 5).
- **Umbrales `null`** → ningún score abre OPERAR: radar VIGILAR, acción
  ESPERAR, código nuevo `SCORE_UNCALIBRATED`. Solo se da en v2 bajo C1.
- **`calibrated: false` con números** → se clasifica con ellos y **todo**
  informe, mensaje de Telegram, texto al LLM y fila persistida lo declara
  («umbral no calibrado»). Nunca se imprime «calibrado» a secas.
- `tracking._verdict` usa los umbrales del horizonte de la posición y, si son
  `null`, solo emite los veredictos por precio (stop / objetivo).
- `config_hash` cambia con el contrato (lo pinea el manifiesto; D-33).

## Implementación requerida — orden obligatorio

Rama única `research/a03-score-v2` desde `main`, cinco pasos, cada uno en su
commit compilable. **El orden es lo que impide el estado prohibido.**

**Paso 0 — Documental (antes de código). HECHO el 2026-09-26.** D-45 a D-48
registradas en `docs/decision-log.md`, requisito 2 de GATE P3 corregido en
`docs/gates.md` y esta ficha commiteada tal como quedó aprobada, en la rama
`docs/t019-preregistro-p3`: ese commit es el pre-registro, y su SHA se cita en
toda la evidencia de P3. La implementación parte de esa rama, o de `main` una
vez fusionada.

**Paso 1 — Contrato de umbrales, con v1 activo y sin cambio de comportamiento.**
- `ScoringConfig` con `score_model_version` y `thresholds` por horizonte;
  `config.yaml` con v1 70/60 **declarados `calibrated: false`** en los tres.
- `classify_setup_detailed` y `tracking._verdict` leen del horizonte.
- `Score.grade` y `conviction_label` siguen con sus cortes en v1 (son la
  presentación de v1), aisladas para que no sean alcanzables desde v2.
- Migración **v6**: `position_review.score_model_version TEXT` (nullable; las
  filas anteriores quedan `NULL` = «anterior a v6, sin versión por fila»; **no**
  se rellena con «1.0», porque la fórmula v1 cambió durante 2026 sin cambiar de
  versión). Backup previo y prueba de restauración (INV-17).
- Verificación: `backtest --vintage 071ddb2b…` **idéntico byte a byte** al de
  A-02 (866 operaciones; hash normalizado `49b12c85…`), salvo lo que cambie por
  `config_hash`. Informe: solo cambia la etiqueta «no calibrado».
- **Aviso de esquema:** este paso migra a v6. La Pi sigue en v5 y no se toca.

**Paso 2 — Score v2 en el código, sin activar.** (Requiere D.)
- `compute_score(..., model_version)` con v1 y v2; `Score.model_version`.
- `Opportunity.confianza` pasa a calcularse desde el snapshot, no desde la
  dimensión: `ratio = (4·min(1, barras/min_bars) + 4·presentes/6) / 8`, mismos
  cortes (Alta ≥ 0,8 con 0 dimensiones ausentes; Media ≥ 0,6 con ≤ 1; si no,
  Baja). Aplica a v1 y v2; su efecto se mide (impacto).
- Los tres llamantes (`analyzer`, `backtest/engine`, `event_study`) pasan la
  versión **activa de la configuración**; investigación puede pedir otra
  versión explícitamente para el antes/después.
- Las bandas v1 de investigación (H-7) quedan etiquetadas `v1` y rechazan
  observaciones de otra versión.
- Producción **no cambia**: `scoring.score_model_version` sigue en `"1.0"`.

**Paso 3 — P3 ejecutado una sola vez** sobre el pre-registro del paso 0
(sección siguiente). Comandos nuevos o extendidos en `advisor/main.py`
(`event-study`, `capacidad-estadistica`, `ablacion-score` con
`--score-model 2.0`, o un `score-v2` que los agrupe; el implementador elige y la
ficha lo registra). Resultado y veredicto publicados en `evidence/`.

**Paso 4 — Registrar la calibración.** Si la regla pre-registrada da umbrales
para swing, se registran como D-nn con su `calibration_ref`. Si no, se registra
que swing queda `calibrated: false`. Medio e intradía, `calibrated: false` por
A. **Nada de esto toca aún la configuración activa.**

**Paso 5 — Activación de v2 en producción, en un solo commit** (según C):
`scoring.score_model_version: "2.0"` y los tres bloques de umbrales `"2.0"` a
la vez. Con C2 y swing sin calibrar, este paso **no se hace** en A-03. Sin
despliegue: la Pi es decisión aparte.

Revisión independiente de look-ahead tras el paso 3 (GATE P3 requisito 5) y
revisión del conjunto antes de aceptar.

## P3 — experimento pre-registrado

Este bloque es el pre-registro. Se congela con el commit del paso 0; cualquier
cambio posterior es un estudio nuevo con decisión propia.

**Datos e identidad.**
- `data_vintage_id = 071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841`.
- Población `vigente`, 93 activos, `universe_vintage_id =
  237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19`.
- `score_model_version = "2.0"` (y `"1.0"` solo para el antes/después).
- `config_hash` del paso 2 y SHA del commit, en la cabecera de cada salida.
- Etiqueta en toda tabla y conclusión: «condicionado al universo seleccionado
  en 2026 (sesgo de supervivencia y selección no corregido)».

**Horizontes.** Swing es el horizonte **confirmatorio**. Medio se calcula con el
mismo código y se publica **solo por trazabilidad**, con el veredicto forzado
«NO CONCLUYENTE — inválido (bloque parcial 102 ≤ 250)», independiente de sus
números (A-02, D-42). Intradía no tiene laboratorio y no se mide.

**Población de señales.** La de P2.3: todas las barras elegibles, sin
`classify()`, sin estado de posición, con solapamiento, warmup 120, horizonte
máximo 40 (swing) / 250 (medio), geometría de la línea 0 (`config.levels`
vigente), modo administrado. Es la misma población de A-02: 106.363 señales en
swing.

**Coste.** 0,20 % ida y vuelta (`cost_pct = 0.2`), `net_R = gross_R − cost_pct
/ risk_pp` (INV-07).

**Estimador primario (INV-14).** Media simple por bloque de la expectancy neta
en R; bootstrap por bloques completos con `bootstrap_block_mean_interval`,
semilla `20260830`, **2.000** remuestreos, IC95. Es el instrumento de A-02 sin
cambios.

**Secundarias, siempre junto al primario y nunca solas.** Expectancy neta en R
agrupada; tasa `TARGET_FIRST/(TARGET_FIRST+STOP_FIRST)`; `P(objetivo antes de
stop)` como intervalo [seguros, seguros+ambiguos]; profit factor agrupado; MAE
de ganadoras y MFE sin objetivo; censura `EXIT_FINAL`; ambigüedad.

**Bloques.** Longitud 60 sesiones en swing (21 bloques; el último de 42) y 300
en medio (5; el último de 102), sobre la espina de sesiones de A-02. Sin
cambios.

**Bloque parcial.** La regla de A-02 (`_classify_capacity`, `<=`): un horizonte
con un bloque **ocupado** de longitud ≤ `MAX_HOLD_BARS` es inválido. En swing el
último bloque (42 > 40) es válido y entra **tal cual**, sin repesar, fusionar ni
descartar. Un bloque con menos de 5 observaciones en una fila se declara como
motivo, como hoy.

**Bandas v2 — quintiles, fijados sin mirar resultados.** Los cortes son los
percentiles 20, 40, 60 y 80 de `Score.value` v2 sobre las 106.363 señales de
swing, calculados **solo con la nota** (ningún campo de desenlace entra en su
cálculo; el revisor lo comprueba). Bandas `v2-Q1` … `v2-Q5`, intervalos
cerrados por abajo; una señal empatada en un corte va a la banda superior. Se
publican los cortes y el `n` realizado de cada banda. **Motivo, declarado antes
de medir:** las bandas fijas de 10 puntos dejaron en A-02 una banda alta de 65
señales en 15 bloques, que no puede concluir nada; los quintiles garantizan
bandas comparables en tamaño. No se reutilizan los cortes 50/60/70/80 de v1.
Medio usa **sus propios** quintiles, calculados igual sobre su población.

**Medida confirmatoria de ordenación.** Contraste pareado por bloque
`Δ = Q5 − Q1`: en cada bloque con señales en ambas bandas, media de `net_R` de
Q5 menos media de Q1; primario = media simple de esos Δ por bloque; IC95 por
bootstrap de bloques con el mismo instrumento. Los bloques sin una de las dos
bandas se excluyen y se cuentan.

**Veredicto de ordenación** — calculado mecánicamente, en este orden:

| Veredicto | Condición (todas) |
|---|---|
| **NO CONCLUYENTE** | el horizonte es inválido (bloque parcial), **o** Δ no es calculable, **o** bloques con Δ < 12, **o** anchura del IC95 de Δ > 0,20 R |
| **SUFICIENTE** | no es NO CONCLUYENTE; bloques con Δ ≥ 25; anchura ≤ 0,12 R; cota inferior del IC95 > 0 |
| **LIMITADA** | no es NO CONCLUYENTE; anchura ≤ 0,20 R; cota inferior del IC95 > 0 |
| **INSUFICIENTE** | no es NO CONCLUYENTE y la cota inferior del IC95 ≤ 0: con resolución suficiente para ver un efecto del orden de 0,2 R, el score **no** ordena (o lo hace al revés; se publica el signo) |

Los números 12, 25, 0,12 y 0,20 son los de `CapacityThresholds` vigentes, **no**
se ajustan para P3. En este veredicto «INSUFICIENTE» significa «ordenación
insuficiente medida con resolución», distinto de la etiqueta de **capacidad**
`INSUFICIENTE` de A-02; las salidas imprimen los dos con nombres distintos
(`veredicto_ordenacion` y `capacidad`). Con 21 bloques, SUFICIENTE es
inalcanzable en swing y se dice así en el resultado.

**Se publica siempre, además del veredicto:** el primario con IC95, `n`,
bloques y `experimental_resolution` por quintil; la tabla **por bloque**
(21 × 5: media de `net_R` y `n`); los cuatro contrastes adyacentes (Q2−Q1 …
Q5−Q4) como descriptivos; las secundarias por quintil. La monotonía no entra en
el veredicto: es descriptiva.

**Regla de calibración de umbrales — solo swing, mecánica.**
Candidatos: los percentiles 50, 60, 70, 80 y 90 de `Score.value` v2 en swing,
calculados sin desenlace como los quintiles. Familia de intervalos para
umbrales: **m = 14** (5 candidatos × 2 condiciones de OPERAR + hasta 4 de
VIGILAR); cada intervalo al nivel Bonferroni `1 − 0,05/14` (≈ 99,64 %), con
**20.000** remuestreos y la misma semilla, porque 2.000 no estabilizan una cola
del 0,18 %.
- Un candidato `c` **cumple OPERAR** si: (1) el horizonte es válido; (2) la
  banda `[c, ∞)` tiene capacidad `LIMITADA` o mejor y es concluyente;
  (3) la cota inferior del intervalo Bonferroni del primario de `[c, ∞)` es
  > 0; (4) la cota inferior del intervalo Bonferroni del contraste pareado por
  bloque `[c, ∞) − [0, c)` es > 0 (el umbral separa, no solo selecciona una
  población que ya era positiva); (5) profit factor agrupado de `[c, ∞)` > 1
  (restricción del protocolo, regla 2).
- **Meseta, no máximo:** `min_score_operar` = el menor candidato `c` tal que
  **todos** los candidatos ≥ `c` cumplen. Si no existe, swing queda
  `calibrated: false` y no se publica ningún número como umbral.
- `min_score_vigilar` solo existe si existe `min_score_operar`. Un candidato
  `v < operar` **cumple VIGILAR** si la banda `[v, operar)` tiene capacidad
  `LIMITADA` o mejor y la cota **superior** de su intervalo Bonferroni es > 0
  (no es demostrablemente perdedora). Se recorre así, sin margen de
  interpretación:

  ```text
  candidatos_bajo = [c for c in (p90, p80, p70, p60, p50) if c < operar]   # de mayor a menor
  vigilar = operar
  for v in candidatos_bajo:
      if cumple_vigilar(v, operar):
          vigilar = v          # sigue bajando
      else:
          break                # el primer fallo corta: no se salta un candidato
  ```

  Cada `[v, operar)` se evalúa contra el `operar` ya fijado, no contra el `v`
  anterior. Si el primero falla, `vigilar = operar` y la franja VIGILAR por
  score queda vacía.
- Drawdown máximo (regla 2 del protocolo): no aplicable a un event study sin
  cartera; se evalúa en P6. Se declara.

**Multiplicidad.** Se cuentan y publican todas las comparaciones de swing:
- confirmatoria: **1** (Δ Q5−Q1, IC95);
- familia de umbrales: **14**, corregida por Bonferroni;
- descriptivas, sin corrección y **sin** valor inferencial por separado:
  5 quintiles + 4 adyacentes + 5 regiones × (primario + Δ) + 93 activos +
  1 intra-activo agregado + 93 intra-activo por activo + 3 ablaciones × (5
  quintiles + 1 Δ) = **224**;
- total swing: **239**. Medio repite el conjunto por trazabilidad y no se
  interpreta. La salida imprime el contador calculado por el código, y si no
  coincide con 239 el implementador explica la diferencia antes de publicar.

**Criterio de NO CONCLUYENTE, dicho sin fórmula.** Es NO CONCLUYENTE todo lo
que la tabla del veredicto clasifique así. Lo que está **prohibido** ante ese
resultado: ampliar la cosecha, cambiar la longitud de bloque, cambiar de
quintiles a otros cortes, cambiar el nivel de confianza, quitar activos o
regiones, usar las secundarias como veredicto, o repetir P3 con otra regla.
Cualquiera de esas cosas es un estudio nuevo, con decisión propia y
`score_model_version` o `data_vintage_id` declarados.

### P3 — ablación por dimensión (GATE P3 requisito 4)
- `score_sin_X` para X ∈ {catalizador, técnico, contexto}, reconstruido desde
  las observaciones por dimensión (P2.2):
  `score_sin_X = 100 · (points − points_X) / (evaluable_max − max_X)`; con
  evaluable 50: sin catalizador y sin técnico sobre 30, sin contexto sobre 40.
- Cada `score_sin_X` se evalúa con **el mismo** procedimiento que el completo:
  sus propios quintiles sin desenlace, primario por quintil, Δ Q5−Q1 y su
  veredicto.
- Se publica, además, la migración de quintil entre el score completo y cada
  ablación.
- **La ablación no selecciona.** No hay regla de selección pre-registrada, así
  que ningún resultado de la ablación cambia Score v2 en esta tarea: si una
  dimensión parece inútil o dañina, se abre una decisión y una ficha posterior
  (o un Score v3).

### P3 — sesgo de universo
- Primario y Δ Q5−Q1 **global**, **por región** (5) y **por activo** (93).
- **Ordenación dentro de cada activo por bloques temporales** (roadmap,
  «Universo»): para cada activo y bloque, `media net_R(Q4∪Q5) − media
  net_R(Q1∪Q2)` con los quintiles globales; primario intra-activo = media por
  bloque de la media entre activos de esas diferencias; IC95 por bootstrap de
  bloques. Q4∪Q5 frente a Q1∪Q2, y no Q5 frente a Q1, porque muchos activos no
  tienen señales en un quintil extremo en cada bloque; se decide aquí, antes de
  medir. Se publica también por activo, como descriptivo.
- Todas con la etiqueta de universo condicionado a 2026.

## Qué NO debe modificarse
- `min_rr_ratio`, `compute_levels*`, `entry_max_rr`, `RR_TOO_LOW`,
  `evaluate_trade_at_entry` y la geometría (`config.levels`).
- Los componentes y tramos de catalizador, técnico y contexto (salvo lo que
  diga la decisión D).
- El estimador, los bloques, la semilla, `CapacityThresholds`, la cosecha y
  `universe.yaml`.
- La evidencia de A-02.
- La Pi y su esquema (v5).

## Tests unitarios
Números cerrados, calculados a mano en el propio test.

Caso base (fundamental no disponible): catalizador volumen 5/8, hueco 1/6,
ruptura 3/6 → 9/20 → **9,0**; técnico 5 + 4 + 4 + 0 + 2 = 15/20 → **15,0**;
contexto **7,0**; RR 10; convicción 4 + 4 + 2 = **10,0**.
- v1: `points` = 9 + 15 + 10 + 7 + 10 = 51; `evaluable_max` = 80; `value` =
  **63,75**.
- v2: `points` = 9 + 15 + 7 = 31; `evaluable_max` = 50; `value` = **62,0**.

Tests:
- `test_v2_valor_del_caso_base` → 62,0, `evaluable_max` 50, `model_version`
  "2.0".
- `test_v2_el_rr_no_cambia_el_score`: el mismo snapshot con niveles de RR 3,2
  (20 puntos en v1) y 1,2 (5 puntos en v1) → v2 = 62,0 en los dos; y la firma
  de v2 no acepta `levels`.
- `test_min_rr_cambia_ejecutabilidad_y_no_el_score`: stop 54,71, objetivo 2
  58,20, precio 56,00. Con `min_rr` 1,5: `entry_max_rr` = (58,20 + 1,5·54,71)
  / 2,5 = 56,106 → ejecutable. Con `min_rr` 2,0: (58,20 + 2·54,71) / 3 =
  55,873 → `ABOVE_MAX_ENTRY`. `Score.value` v2 = 62,0 en los dos.
- `test_calidad_frescura_broker_no_cambian_el_score`: la misma oportunidad con
  calidad OK / DEGRADADO / INCOMPLETO y `trade_republic` yes / no / unknown →
  `score.value` 62,0 en las nueve; cambian solo acción y motivos.
- `test_v1_y_v2_tienen_versiones_distintas`: "1.0" ≠ "2.0", las dos
  registradas, y `compute_score` con una versión desconocida lanza.
- `test_confianza_sin_dimension_conviccion`: 250 barras, `min_bars` 250,
  6/6 indicadores → ratio 1,0; con 1 dimensión ausente → «Media» (H-5: nunca
  «Alta» mientras falte fundamental); 150/250 barras y 4/6 → (2,4 + 2,667)/8 =
  0,633 → «Media»; 100/250 y 3/6 → (1,6 + 2,0)/8 = 0,45 → «Baja».
- `test_config_rechaza_umbrales_de_otra_version`: activo "2.0" con swing
  declarando "1.0" → `ValidationError`.
- `test_config_rechaza_horizonte_sin_umbrales` y
  `test_config_rechaza_claves_globales_antiguas`.
- `test_config_calibrated_true_exige_numeros_y_referencia`.
- `test_umbrales_de_un_horizonte_no_se_usan_en_otro`: swing 70/60, medio
  80/75 (ambos `calibrated: false`), score 72 → swing OPERAR, medio VIGILAR con
  motivo que cita 80.
- `test_umbrales_null_dan_score_uncalibrated`: score 95 en un horizonte sin
  números → VIGILAR / ESPERAR / `SCORE_UNCALIBRATED`.
- `test_no_calibrado_nunca_se_presenta_como_calibrado`: informe, Telegram y
  texto al LLM de un horizonte `calibrated: false` contienen «no calibrado» y
  ninguna etiqueta v1 («Excepcional», «Muy atractiva», «Alta convicción»).
- `test_bandas_v1_rechazan_observaciones_v2` (`score_band`, `_SCORE_BUCKETS`,
  `execution_filter`, `ablation`).
- `test_quintiles_no_leen_desenlace`: los cortes calculados sobre observaciones
  con `managed` alterado son idénticos.
- `test_veredicto_ordenacion_tabla`: cuatro casos sintéticos con bloques de
  tamaños distintos, uno por fila de la tabla del veredicto, incluido 21 bloques
  con anchura 0,10 → LIMITADA (no SUFICIENTE).
- `test_regla_de_umbral_meseta`: candidatos que cumplen {p60, p80, p90} pero no
  p70 → operar = p80, no p60.
- `test_migracion_v6_position_review` con backup y restauración.

## Tests de integración
- **INV-06, código:** para `AAPL`, `SAP.DE` y `SXR8.DE` sobre la cosecha, el
  score v2 de `analyzer`, `backtest/engine` y `event_study` coincide en las
  mismas barras (extensión del test de equivalencia prefijo/vectorizado).
- **INV-06, contenido:** el `MarketContext` que ven los tres caminos para la
  misma barra produce los mismos `points` (falla hoy por H-1; pasa con D1 o D2).
- **Equivalencia v2 ↔ ablación:** en los mismos tres activos, `Score.value` v2
  == `100·(points − rr − conviccion)/(evaluable_max − 20 − 10)` reconstruido
  desde las `DimensionObservation` v1 (P2.2), con `assert_allclose` estrecho.
  Con D1 la reconstrucción añade el ajuste de contexto y el test lo refleja.
- **Recomendación persistida:** una pasada con versión activa X deja
  `analysis_run.score_model_version = X`, y persistir una oportunidad cuyo
  `Score.model_version` ≠ X aborta la transacción.
- **Producción no se mueve en los pasos 1 y 2:** `backtest --vintage` idéntico
  al de A-02.

## Verificación contra datos reales
- Pasos 1 y 2: `python -m advisor.main backtest --horizonte swing --vintage
  071ddb2b` en `main` y en la rama; comparar con el `sed` de A-02; el hash
  normalizado debe ser `49b12c855c2d2681d9ecd0f592248cd03b11cd8428273014238e04f0ddefbc3c`
  o explicar cada diferencia.
- Paso 3: los comandos de P3 sobre `071ddb2b…`, `--poblacion vigente`, swing y
  medio, con salida completa en `evidence/`.
- **Número comprobado a mano, obligatorio:** elegir una señal de `SAP.DE` en la
  salida, leer sus `DimensionObservation` v1 y recalcular con calculadora su v2
  (`100·(cat + tec + ctx)/50`) y su quintil. Escribir el cálculo en esta ficha.
- Recalcular a mano un Δ por bloque (un bloque, Q5 y Q1) desde la tabla por
  bloque.

## Medición del impacto
Antes/después sobre la cosecha congelada, swing y medio (medio marcado
inválido), sin llamar equivalentes a bandas de escalas distintas:
- distribución completa de `Score.value` en v1, v1 sin RR (sobre 60), v1 sin
  convicción (sobre 70) y v2 (sobre 50): percentiles 1, 5, 10, 25, 50, 75, 90,
  95 y 99, e histograma en tramos de 5;
- `n` por quintil de cada escala y matriz de migración entre **tramos de
  escala** de 10 puntos v1 → v2, rotulados como tramos, no como bandas
  equivalentes;
- lo mismo por región y la mediana del desplazamiento por activo;
- efecto de retirar solo el RR, solo convicción y los dos, por separado;
- número de señales con contexto imputado (H-6) y, con D1, el efecto de retirar
  Asia;
- cambio de `confianza` en la pasada de producción (paso 2), por motivo;
- **clasificación operativa:** el número de señales cuya clasificación cambia
  **solo** se calcula si swing sale `calibrated: true`, comparando v1 70/60 con
  v2 y sus umbrales calibrados en `backtest --vintage`. Si no hay umbrales
  válidos, la salida dice «no aplica: sin umbrales v2 calibrados» y **no** se
  calcula con 70/60.
- Ninguna mejora de expectancy se atribuye a una dimensión si su intervalo no lo
  permite.

## Criterio de aceptación
1. Decisiones A–D registradas y `gates.md` corregido **antes** del primer
   commit de código; el SHA del pre-registro aparece en la evidencia.
2. Score v2 implementado como está especificado, con `"2.0"` y v1 intacto.
3. Contrato de umbrales por horizonte con las seis reglas de validación.
4. P3 ejecutado **una vez** con el pre-registro, sin desviaciones, o con cada
   desviación declarada como BLOCKER y parada.
5. Veredicto de ordenación publicado con su tabla, por bloque, secundarias,
   `experimental_resolution` y contador de comparaciones.
6. Ablación y sesgo de universo publicados.
7. Impacto medido como arriba.
8. `pytest -q`, `ruff check .` y `mypy advisor` limpios; producción idéntica en
   `backtest --vintage` tras los pasos 1 y 2.
9. Revisión independiente de look-ahead hecha y sus hallazgos cerrados.
10. Matriz de GATE P3 rellenada con rutas de evidencia.

## Criterio de rechazo
- Cualquier estado del repositorio en el que v2 esté activo y se clasifique con
  70/60 o con cualquier número declarado para `"1.0"`.
- Umbrales v2 con números que no salgan de la regla pre-registrada (o, bajo C3,
  de una decisión explícita del propietario).
- Medio `calibrated: true`, o su veredicto derivado de sus números.
- Cortes o bandas elegidos después de ver desenlaces; P3 ejecutado más de una
  vez con reglas distintas.
- Una secundaria publicada sin el primario, o un resultado sin intervalo ni
  `experimental_resolution` (INV-14, INV-20).
- Redefinir Score v2 a partir de la ablación dentro de esta tarea.
- El RR dejando de condicionar la ejecutabilidad, o `min_rr` afectando al score.
- Cualquier despliegue o migración en la Pi.

## Evidencia que debe quedar registrada
`evidence/<fecha>-T-019-score-v2/`:
- `README.md`: SHA del pre-registro y del código, `data_vintage_id`,
  `universe_vintage_id`, `score_model_version`, `config_hash`, comandos exactos,
  veredicto y matriz de GATE P3;
- `produccion-backtest-{MAIN,RAMA}.txt` de los pasos 1 y 2 con su hash
  normalizado;
- `p3-ordenacion-{swing,medio}.txt` (quintiles, cortes, por bloque, Δ,
  secundarias, veredicto, contador);
- `p3-calibracion-swing.txt` (los cinco candidatos, cada condición con su
  intervalo, y el resultado de la regla);
- `p3-ablacion-{swing,medio}.txt`, `p3-universo-{swing,medio}.txt`;
- `impacto.md` y sus tablas;
- `revision-look-ahead.md` del revisor independiente;
- `hashes-de-tablas.txt`;
- `final-pytest-ruff-mypy.txt`.

## Commit esperado
Rama `research/a03-score-v2`. Primeras líneas, una por paso:
- `docs(T-019): pre-registro de P3 y decisiones de Score v2`
- `feat(scoring): umbrales por horizonte ligados al score_model_version, sin cambio de comportamiento`
- `feat(scoring): Score v2 sin RR ni convicción, sin activar`
- `research(P3): ordenación, ablación y sesgo de universo de Score v2 sobre 071ddb2b`
- `docs(T-019): resultado de P3 y estado de calibración por horizonte`

## Actualización documental requerida
- Paso 0 (hecho): `docs/decision-log.md` (D-45 a D-48), `docs/gates.md` (requisito 2 de
  GATE P3, texto de A).
- Al cerrar: fila A-03 de `docs/roadmap.md`; GATE P3 en `docs/gates.md` y
  `docs/decision-log.md` si se cruza; `README.md` (tabla de dimensiones);
  `docs/protocolo-investigacion.md` solo si el contrato que describe cambia
  (nota: su frase «el score real se calcularía sobre 60 puntos» queda superada
  por B y se corrige con fecha).
- Hallazgos abiertos del roadmap: H-1 si D no lo resuelve; H-5 y H-6.

## Revisión de la ficha (2026-09-26)
Codex la revisó en modo solo lectura intentando refutarla. **Sin BLOCKER.**
Confirmó contra el código: la descripción de Score v1, que la población del
event study no depende del score (y por tanto el primario global de swing de P3
será el de A-02), los números de los tests (63,75 / 62,0; 56,106 / 55,873 con
`ABOVE_MAX_ENTRY` por el orden de `execution.py:71–74`; 0,633 / 0,45), el
recuento de 239 comparaciones y que ningún paso deja v2 activo con 70/60.
Cuatro hallazgos, reproducidos y ya incorporados: inventario incompleto en tests
(IMPORTANTE), desfase del VIX y contexto del seguimiento como divergencias
adicionales a Asia (IMPORTANTE, ahora en H-1 y D), regla de VIGILAR ambigua
(MENOR, ahora en pseudocódigo) y estado del árbol desactualizado (MENOR).

## Matriz de GATE P3

| # | Requisito (texto tras la decisión A) | Evidencia exacta que lo satisface |
|---|---|---|
| 1 | Dimensiones y pesos redefinidos y documentados con `score_model_version` nuevo; nada posterior se mezcla con lo anterior sin etiqueta | D-46 registrada; `advisor/analysis/scoring.py` con `"2.0"` y `Score.model_version`; `test_v2_valor_del_caso_base`, `test_v1_y_v2_tienen_versiones_distintas`, `test_bandas_v1_rechazan_observaciones_v2`, test de recomendación persistida; `README.md` actualizado |
| 2 | Umbrales por horizonte con estado `calibrated` ligado a la versión; swing con la regla pre-registrada; medio `calibrated: false` con motivo (D-42); intradía `calibrated: false` | D-45 registrada y `gates.md` corregido; contrato en `advisor/config.py` y sus tests; `p3-calibracion-swing.txt` con el resultado mecánico de la regla; D-nn del paso 4 con el estado de los tres horizontes |
| 3 | Ordenación bajo el primario, por banda y por bloque, con veredicto SUFICIENTE / LIMITADA / INSUFICIENTE / NO CONCLUYENTE | `p3-ordenacion-swing.txt` (quintiles, IC95, tabla por bloque, Δ Q5−Q1, secundarias, `experimental_resolution`, veredicto, contador de comparaciones); `p3-ordenacion-medio.txt` con veredicto forzado por invalidez |
| 4 | Ablación por dimensión (`score_sin_X`) publicada | `p3-ablacion-{swing,medio}.txt`, tres dimensiones, mismo procedimiento que el completo, sin selección |
| 5 | Revisión independiente del look-ahead | `revision-look-ahead.md` de otro agente, con al menos: alineación temporal de VIX (`shift(1)`), tendencia y fortaleza relativa; que los quintiles y candidatos no leen desenlace; que la población no depende del score; paridad de contexto producción/laboratorio (H-1); que medio no se usa para nada más que trazabilidad; hallazgos clasificados y cerrados |

## Handoff al siguiente agente
(se rellena al terminar)
