# T-019 — Score v2 y umbrales por horizonte, con P3 pre-registrado (A-03)

Estado: EN CURSO. La ficha se aprobó el 2026-09-26 como **pre-registro
condicionado de P3** (PR #26). El paso 1 está hecho (PR #28, `db51d67`). El
**paso 2a-doc está cerrado el 2026-09-29**, con D-50 a D-57: `analysis_timestamp`,
cripto fuera de P3, Asia con sesiones cerradas, VIX y tendencia point-in-time,
cinco cierres reales aprobados, exclusión por historia insuficiente de la
SMA200, huecos de `^STOXX50E` con el último cierre causal y Bonferroni con
`m = 20`.
**El commit de 2a-doc es el pre-registro completo y ejecutable de P3.** P3
sigue sin poder ejecutarse hasta que estén hechos 2a-code y la revisión previa
de look-ahead.
Decisiones cerradas por el propietario: A → **D-45**, B → **D-46**, C →
**D-47** (C2, estado de transición), VIX → **D-49** y **D-53**,
`analysis_timestamp` → **D-50**, cripto → **D-51**, Asia (PR-1) → **D-52**,
cierres extraordinarios → **D-54**, SMA200 → **D-55**, huecos de `^STOXX50E` →
**D-56**, Bonferroni → **D-57**. La **D-48** se retiró el
mismo día, antes de fusionarse (mezclaba tres cuestiones). GATE P3 requisito 2
corregido por D-45 y precisado en la tercera revisión.
Agente: Opus (ficha) → propietario (D-45 a D-47, D-49 a D-57) → Codex (implementación) → Claude Code
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
- No despliega nada en la Pi. Cuando se escribió la ficha, la Pi estaba en
  `v0.3.0` (`03e1ec3`), esquema v5; desde el 2026-09-26 está en `v0.4.0`
  (`84ea28e`), esquema v6.
  Cualquier despliegue es una decisión posterior y separada.
- No redefine el score después de ver resultados: la ablación publica, no
  selecciona (sección «P3 — ablación»).

## Dependencias previas
- **GATE P2 cruzado** (D-42, D-43), T-013 ACEPTADA.
- Pre-registro del estimador de bloque del 2026-09-02 (INV-14, D-03).
- `main` en `b658541` (T-018 aceptada; la caché de barras no afecta a la
  cosecha congelada).
- **D-45, D-46, D-47 y D-49**, cerradas por el propietario el 2026-09-26 y
  registradas en `docs/decision-log.md`, junto con la corrección de
  `docs/gates.md`. D-48 figura como retirada.
- **Antes del paso 3 (P3):** el commit documental 2a-doc (**hecho el
  2026-09-29**: PR-1 respondida, reglas point-in-time del VIX, la tendencia y
  Asia, y `analysis_timestamp` fijados), la implementación 2a-code y la
  revisión previa de look-ahead; ver «Contexto:
  paridad y point-in-time» e «Implementación».

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
   con niveles válidos (`event_study.py:313–338`); el score solo etiqueta.
   **Actualizado en 2a-doc:** A-02 publicó un primario global de swing de
   `+0.064 R`, IC95 `[-0.060, 0.171]`, 21 bloques, `INSUFICIENTE`/`LOW`, sobre
   106.363 señales. Ese valor **ya no es el de P3 por construcción**: la
   población de P3 es de 94.094 señales en **19 bloques con señales**. D-51
   quita cripto, D-52 excluye Asia no calculable y D-55 excluye la historia
   insuficiente de la SMA200. El bloque 1 de la espina lo vacía D-51, porque
   solo tenía señales cripto, y el 2, D-55. Su
   primario global es otra cifra y no debe usarse como control. Lo que sigue
   valiendo es que la población no depende del score.
2. **Con 19 bloques, `SUFICIENTE`/`HIGH` es inalcanzable** en swing, porque
   `CapacityThresholds.sufficient_blocks` = 25. El mejor veredicto posible de
   cualquier fila de swing es `LIMITADA`.
3. **Cualquier subconjunto del score (banda, umbral) tiene como mucho los mismos
   19 bloques y menos señales por bloque**, así que lo esperable es que sus
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
  la de `analizar` y la de `seguimiento`. Se trata en tres piezas separadas:
  PR-1 (componente asiático), D-49 (VIX) y R-CTX (seguimiento), resueltas en
  2a-doc por D-50 a D-57; sección
  «Contexto: paridad y point-in-time».
- **H-2 — `position_review.score` sin versión ni manifiesto. SAME_SCOPE.** Con
  dos modelos coexistiendo, una revisión persistida no dice con qué modelo ni
  con qué umbrales se puntuó; y `seguimiento` persiste sin `run_id`
  (`main.py:772–784`, `db.py:826–848`), contra INV-18. Además `analysis_run`
  solo guarda `config_hash`, que permite **comprobar** una configuración pero no
  **recuperarla**, y `--config` (`main.py:1002`) acepta cualquier ruta sin
  registrarla. Se resuelve con el contrato de persistencia de la migración
  **v7** (sección «Implementación», paso 1).
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

**A, B y C cerradas el 2026-09-26** como **D-45, D-46 y D-47** en
`docs/decision-log.md`, que es el texto que manda. Se conserva abajo el
razonamiento y las alternativas con que se propusieron. **D no se cerró como
una decisión única**: la D-48 que la registraba se retiró antes de fusionarse
porque mezclaba tres cuestiones y una no estaba aprobada; su reparto está en la
sección «Contexto: paridad y point-in-time».

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
- **Aprobada C2 como estado de transición (D-47):** producción sigue en
  `score_model_version = "1.0"` con los 70/60 legacy de v1, que nunca se
  presentan como calibración de v2; el RR sigue puntuando solo porque corre v1;
  el paso a v2 es atómico (versión + contrato de umbrales + estado de
  calibración coherente) y no puede existir una pasada que calcule v2 y
  clasifique con 70/60.
- **Recomendación técnica con que se propuso: C2**, con la etiqueta `calibrated: false` visible
  desde el paso 1. Es la única que no introduce un corte nuevo sin medir y no
  deja el asesor inutilizado. La tercera revisión mostró que comparar la
  etiqueta de versión **no bastaba** para hacer imposible «v2 activo con
  70/60»: lo garantiza la regla 7 del contrato de umbrales.
- **Bloquea:** solo el paso 5 (activación de v2 en producción). No bloquea P3
  ni GATE P3.

### DECISIÓN D — Paridad del contexto · **no se cerró como una decisión: dividida**

Se propuso como una sola decisión (D1: el componente asiático deja de puntuar,
el revisor fija la alineación del VIX y el seguimiento usa el mismo contexto).
Se registró como D-48 y **se retiró** antes de fusionarse: la primera parte no
estaba aprobada, la segunda no es válida metodológicamente y la tercera es un
requisito técnico, no una decisión estadística. Queda dividida en la sección
siguiente.

## Contexto: paridad y point-in-time — CONGELADO en 2a-doc (2026-09-29)

El 2026-09-26 esta sección tenía tres piezas abiertas: PR-1 (el componente
asiático), D-49 (el VIX) y R-CTX (el seguimiento). La inspección de 2a-doc
(`evidence/2026-09-29-T-019-paso2a-doc-inspeccion/`) encontró dos cosas que el
contrato no decidía: qué pasada de producción representa a una señal
histórica, y qué hacer con PR-1. El propietario las resolvió el 2026-09-29
(**D-50 a D-57**). Nada de lo que sigue se eligió mirando la expectancy, los
desenlaces ni los scores.

**Hechos de la inspección que motivan las reglas:**
- Producción genera la señal swing **cuatro veces** por día laborable (H1).
- Su dato asiático es intradía en las pasadas de la mañana, porque
  `fetch_overview` no recorta la barra abierta (H2).
- La cosecha solo tiene cierres diarios (H3).
- Hay plazas cuyo cierre de sesión coincide con la apertura siguiente
  (cripto, H4).
- El laboratorio desalinea el VIX y la tendencia, con look-ahead en EE. UU. y
  cripto (H6).

### `analysis_timestamp` (D-50)

> `analysis_timestamp` de una señal con barra de señal `d` y barra de entrada
> `d+1` (la barra `j+1` de la cosecha, cuya apertura es la entrada del
> laboratorio) = la **última pasada programada** de producción
> **estrictamente anterior** a la apertura de la sesión `d+1` de la plaza del
> activo, siempre que sea **igual o posterior** a `available_at(d)`.

Con fórmula, siendo `P` el conjunto de pasadas programadas:

    available_at(d)     = session_close_at(plaza, d) + settlement_minutes
    apertura(d+1)       = session_open(calendario de la plaza, d+1)
    analysis_timestamp  = max{ p ∈ P : available_at(d) <= p < apertura(d+1) }

- **Pasadas programadas `P`.** Son las del timer versionado
  `deploy/systemd/intradia-bot.timer`, que es el **único horario registrado**
  (una sola versión, commit `1f31d2d` del 2026-08-30): lunes a viernes a las
  07:00, 08:30, 14:30 y 21:00 en hora **Europe/London**, la zona de la Pi.
  Las horas se convierten a UTC con el DST histórico de la base tz, fecha a
  fecha. Los festivos británicos no cuentan, porque el timer se dispara de
  lunes a viernes sin mirar festivos. Como no existe otro horario, este se
  aplica a todo el periodo de la cosecha.
- **La pasada por evento de las 22:30 no forma parte de `P`.** Se
  autodescarta salvo que el calendario de eventos la active, esa condición no
  se puede reconstruir sobre la cosecha y la base de producción no tiene
  ninguna persistida. Es la única lectura implementable de «pasada
  programada».
- **Calendarios.** `session_close_at` y `session_open` salen del calendario de
  la plaza (`exchange_calendars` + `exchange_overrides.yaml`), con sus
  festivos, cierres anticipados y DST. `settlement_minutes` = 20
  (`config.yaml`, `data_quality`).
- **Conjunto vacío.** Si ninguna pasada cae en el intervalo, la observación no
  es calculable y se cuenta. En la cosecha hay **0** casos fuera de cripto.
- **Resultado por plaza.** Es igual en verano y en invierno. **La fórmula
  prevalece sobre la tabla**, que solo describe el caso habitual:

  | plazas | `analysis_timestamp` |
  |---|---|
  | XETRA, PAR, AMS, MCE, MIL | la pasada de las **07:00 de Londres de `d+1`** |
  | NYSE, NASDAQ | la de las **08:30 de Londres de `d+1`**; la de las 14:30 coincide con la apertura o la sigue, así que no cuenta |
  | JPX, HKG | la de las **21:00 de Londres del último día laborable anterior a la apertura de `d+1`**, que coincide con `d` salvo cuando un festivo de la plaza separa `d` y `d+1`: 342 de 6.612 pares de barras consecutivas tras el warmup en JPX y 159 de 3.318 en HKG, por ejemplo Golden Week o Semana Santa en Hong Kong |

### Cripto fuera de P3 (D-51)

En las plazas 24/7, el cierre de la barra diaria `d` (00:00 UTC) **coincide**
con la apertura de `d+1`, así que no existe ninguna pasada entre los dos
instantes. No se inventa un `analysis_timestamp` que producción nunca
ejecutó.

`BTC-EUR`, `ETH-EUR` y `SOL-EUR` quedan **fuera de la población confirmatoria
de P3 y de la trazabilidad de medio**, mientras se mantenga la semántica diaria
«señal al cierre → entrada en la apertura siguiente». **No** salen del
universo ni de producción.

Es una enmienda del pre-registro condicionado anterior al SHA de 2a-doc,
motivada solo por una imposibilidad temporal detectada antes de mirar P3. La
espina de sesiones de los bloques ya se construía sin cripto
(`capacity.py:619`), así que la espina y los bloques no cambian: 22 bloques en
swing, el último de 42 sesiones, y 5 en medio, el último de 102. Cuántos de
ellos tienen señales lo fija el censo tras todas las exclusiones: 19 en swing
y 5 en medio (`07-ocupacion-de-bloques.txt`).

### Componente asiático, con sesiones cerradas (PR-1 → D-52)

**Composición.** Las cinco series, derivadas del universo con la regla de
producción (`context_assets_of` + `region: ASIA`): `^N225`, `^HSI`, `^KS11`,
`^TWII` y `510300.SS`.

**Cálculo, para cada serie y cada `analysis_timestamp`:**
1. `L` = la última sesión de su propia plaza cuyo cierre más
   `settlement_minutes` es ≤ `analysis_timestamp`
   (`latest_expected_closed_session`).
2. `P` = la sesión de su calendario inmediatamente anterior a `L`.
3. `variación = (cierre(L) / cierre(P) − 1) · 100`.

`asia_session_change` es la **media simple de las cinco variaciones**. Nunca se
usan barras intradía.

**Festivo frente a hueco.**
- **Festivo o cierre de plaza**, aunque dure varios días: no es un dato
  ausente. `L` y `P` son las sesiones realmente cerradas de esa plaza.
- **Hueco del proveedor**: el calendario exige `L` o `P` y la cosecha no tiene
  su barra. Entonces no hay forward fill, ni proxy, ni imputación, ni cálculo
  con cuatro series. La observación es **no calculable por input de contexto
  ausente**, se excluye de P3 y se publican su contador y su motivo. La
  composición **nunca** pasa de cinco a cuatro series.

**Cierres reales que el calendario no conoce.** La inspección encontró
sesiones que `exchange_calendars` da como abiertas y que fueron **cierres
reales verificados**. El propietario los **aprobó como festivos en D-54**: no
son huecos del proveedor. **2a-code debe añadirlos a `exchange_overrides.yaml`
antes de P3**, con estas mismas fuentes, y la población de P3 se congela con
ellos incluidos:

| plaza | fecha | motivo | fuente |
|---|---|---|---|
| XHKG | 2023-09-01 | tifón Saola (T8): HKEX canceló la sesión completa | CNBC 2023-09-01; SCMP |
| XHKG | 2023-09-08 | aviso de lluvia negra todo el día: HKEX canceló la sesión | HKEX, comunicado 230908; SCMP |
| XTAI | 2023-01-18 | la TWSE no negoció antes del Año Nuevo Lunar («市場無交易，僅辦理結算交割作業»); `exchange_calendars` la da como abierta | calendario oficial de la TWSE, año 112 |
| XTAI | 2024-10-31 | tifón Kong-rey: la TWSE suspendió la sesión | Bloomberg 2024-10-30/31 |
| XTAI | 2026-07-10 | tifón Bavi: la TWSE suspendió la sesión | Bloomberg 2026-07-10; Reuters vía TradingView |

Las sesiones sin cierre verificado siguen siendo **huecos del proveedor**:

| serie | sesión | nota |
|---|---|---|
| `^KS11` | 2022-05-09 | sin fuente |
| `510300.SS` | 2025-10-24 | sin fuente |
| `510300.SS` | 2026-08-28 | la cosecha se congeló el 2026-08-30 sin esa barra |

**Alcance.** Esta semántica es la de **Score v2, P3 y la futura producción
v2**. **Score v1 queda intacto** mientras D-47 lo mantenga activo: 2a-code no
cambia el comportamiento productivo de v1 antes de la activación atómica de
v2.

### VIX y tendencia (D-49 → D-53)

**VIX.**

> Para cada `analysis_timestamp` se usa la **última observación diaria de
> `^VIX` presente en los datos** cuya sesión `s` cumple
> `available_at(s) <= analysis_timestamp`, con
> `available_at(s) = session_close_at("NYSE", s) + settlement_minutes`.

- **Calendario.** La plaza del VIX se resuelve por símbolo, como en producción
  (`market_for_symbol("^VIX") = "NYSE"`, calendario XNYS con festivos de
  EE. UU., cierres anticipados y DST). El universo declara
  `primary_market: CBOE`, que no tiene sesión en `MARKET_SESSIONS`; la función
  compartida no lo usa.
- **Disponibilidad de la barra del proveedor.** La barra diaria del VIX que
  sirve el proveedor está fechada a la medianoche de Nueva York (`05:00Z` o
  `04:00Z`, `05-materia-prima-cosecha.txt`), así que `session_date_of("NYSE")`
  le asigna su sesión. Producción la acepta con la misma regla
  (`trim_unclosed_bar` en `fetch_market_context`): solo después del cierre
  XNYS más 20 minutos. Esa es la semántica que se congela.
- **Sin forward fill ni imputación.** «Última observación presente» significa
  eso: si el proveedor no tiene la barra de `s`, la última disponible es la
  anterior que exista. No se rellena ni se imputa nada. En la cosecha no
  aparece **ningún** hueco del VIX en los `analysis_timestamp` de P3.
- **Sin `shift(1)` por posición de fila ni alineación por fecha civil.**
- **Barras en días sin sesión.** Solo cuentan las barras cuya fecha de sesión
  es una sesión del calendario de su plaza (XNYS para el VIX, XETR para
  `^STOXX50E`). Las demás se ignoran, como hace `trim_unclosed_bar` con
  `latest_expected_closed_session`. Ejemplo: la cosecha tiene una barra `^VIX`
  del 2026-05-25, Memorial Day, con XNYS cerrado; no se usa. Es la única barra
  de contexto de la cosecha en un día sin sesión.

**Tendencia `^STOXX50E`.** Es la misma regla con la plaza XETRA: el último
cierre presente cuya sesión cumple `available_at <= analysis_timestamp`. La
SMA de 200 se calcula **solo** con los cierres presentes hasta esa misma
sesión.

Dos situaciones distintas, con tratamiento distinto:

- **Hueco puntual de `^STOXX50E` → último cierre causal disponible (D-56).**
  La sesión exigible por XETR no tiene barra del índice (Ascensión, lunes de
  Pentecostés, 1 de agosto, 2 de enero…). Se usa el último cierre presente y
  causalmente disponible antes de `analysis_timestamp`, y la observación
  **no** se excluye.
  - Se declara que ese dato puede ser más antiguo que la sesión exigible.
  - En la población de P3 afecta a **1.406 señales swing y 1.312 de medio**:
    el cierre usado tiene 1, 3 o 4 días naturales más que el exigible.
  - Listado en `06-stoxx_hueco_intermedio-{swing,medio}.tsv`, y P3 publica el
    contador.
- **Historia inicial insuficiente para la SMA200 → exclusión (D-55,
  `NO_CALCULABLE_CONTEXT_HISTORY`).** Si en `analysis_timestamp` no hay 200
  cierres de `^STOXX50E` causalmente disponibles en la cosecha, la
  observación **se excluye de P3**. No se neutraliza con 2 de 4, porque no es
  un dato que producción desconociera: es un límite de profundidad de la
  cosecha.
  - Afecta a **6.937 señales swing**, las del principio de la cosecha; 176 de
    ellas también están excluidas por Asia. En medio, 0.
  - Listado en `06-excluded_trend_sma_history-{swing,medio}.tsv`.

**El defecto del laboratorio, registrado.** `_naive_dates` normaliza las
fechas en UTC (`event_study._align`, `runner._align`). En la cosecha eso dio:
- en las barras de EE. UU. (78 %) y de cripto (69 %), una tendencia de una
  sesión **posterior** a la barra;
- en Europa y Asia, un VIX de dos sesiones atrás.

A-02 se midió con ese defecto. **Su evidencia no se modifica**: queda como
resultado publicado con esa limitación. P3 usa el camino corregido.

### R-CTX — una sola función de contexto

> Producción v2, backtest, event study y seguimiento llaman a **la misma
> función de contexto point-in-time**. Para el mismo `analysis_timestamp`
> obtienen exactamente el mismo VIX, la misma tendencia y SMA, y el mismo dato
> asiático.

`seguimiento` usa como `analysis_timestamp` el instante de su propio
manifiesto, nunca «lo último disponible ahora» calculado aparte.

### `contexto` de Score v2 — composición congelada

| componente | puntos | valor | semántica temporal |
|---|---|---|---|
| tendencia | 4 | `^STOXX50E` > SMA 200 → 4; ≤ → 0 | D-53 |
| VIX | 4 | ≤ 0,6·umbral → 4; < umbral → 2,8; < 1,4·umbral → 1,2; resto → 0 (umbral 25) | D-53 |
| Asia | 2 | ≥ +0,5 % → 2; (−0,5, +0,5) → 1; (−1,5, −0,5] → 0,5; ≤ −1,5 % → 0 | D-52 |
| **total** | **10** | | |

- Los tramos son los de v1 (`MarketContext.points`): no se redistribuye nada.
- No se añade ninguna señal. `^SOX`, `^RUT`, `^TNX`, `DX-Y.NYB`, `CL=F` y
  `GC=F` son FOLLOW_UP con medición propia.
- **Datos ausentes en P3:**
  - SMA200 sin 200 cierres causalmente disponibles: la observación **se
    excluye** (D-55).
  - Asia no calculable: la observación **se excluye** (D-52). No puntúa 1,0.
  - Hueco puntual de `^STOXX50E`: último cierre causal disponible (D-56).
  - VIX: la cosecha no tiene ningún hueco del VIX en los `analysis_timestamp`
    de P3.

  La regla v1 de dato ausente (la mitad de los puntos) solo sigue en v1.

## Score v2 — especificación

Con D-43 (RR fuera) y D-46 (convicción fuera). Contexto congelado en 2a-doc
(D-50 a D-57).

| Dimensión | v1 | v2 | Cambio |
|---|---|---|---|
| catalizador | 20 | **20** | ninguno: mismos componentes y tramos |
| fundamental | 20 | **20** | ninguno: sigue no disponible y fuera del denominador |
| técnico | 20 | **20** | ninguno |
| beneficio/riesgo | 20 | — | **sale** (D-43) |
| contexto | 10 | **10** | mismos puntos y tramos (tendencia 4 + VIX 4 + Asia 2). **Cambia la semántica temporal** de los tres (D-50, D-52, D-53; sección «Contexto: paridad y point-in-time») |
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
- **Invariante de composición (I2 de la tercera revisión).** Las dimensiones
  puntuables son **propiedad del `score_model_version`**, no de un flag que
  pueda modificar su composición. Mientras no exista una versión que incluya
  fundamentales, `score_model_version = "1.0"` o `"2.0"` con
  `fundamentals_enabled: true` es **configuración inválida** (regla 9 del
  contrato). Activar fundamentales exige una versión nueva; esta ficha no la
  crea.
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

## Contrato de umbrales por horizonte (implementado en el paso 1)

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
   desajuste es error. Por sí sola esta regla **no** impide «v2 activo con
   70/60»: bastaría con reescribir 70/60 en un bloque que declare `"2.0"`. Lo
   impide la regla 7.
3. `min_score_operar` y `min_score_vigilar` son los dos números o los dos
   `null`; con números, `vigilar ≤ operar` (la regla actual).
4. `calibrated: true` exige números y `calibration_ref` no nulo.
5. Las claves globales antiguas `scoring.min_score_operar` /
   `scoring.min_score_vigilar` son error con mensaje explícito; no se migran en
   silencio.
6. `scoring.score_model_version` debe ser una versión implementada.
7. **Números y estado de calibración, por versión.**
   - Para `score_model_version == "1.0"` se permite excepcionalmente, durante
     D-47, `calibrated: false` con los 70/60 legacy.
   - Para **cualquier** modelo distinto de `"1.0"`:
     `calibrated: false` ⇒ `min_score_operar = null`, `min_score_vigilar =
     null` y `calibration_ref = null`; `calibrated: true` ⇒ los dos umbrales
     numéricos y una `calibration_ref` válida (formato `D-nn · evidence/<ruta>`,
     con la ruta existente en el repositorio).

   Por tanto es **inválido**, y el cargador lo rechaza al arrancar:

   ```yaml
   score_model_version: "2.0"
   calibrated: false
   min_score_operar: 70
   min_score_vigilar: 60
   ```
8. **Horizontes calibrables, como parte de la especificación de cada versión**
   (no como revisión humana del YAML). Cada `score_model_version` declara en el
   código el conjunto de horizontes que pueden estar `calibrated: true`:
   `"1.0"` → ninguno; `"2.0"` → solo `swing` (D-45). `calibrated: true` en un
   horizonte fuera de ese conjunto es error. Reabrir medio exige la decisión y
   la ficha nuevas que prevé D-45, y con ellas una versión cuya especificación
   lo autorice.
9. **Composición fija por versión** (invariante de composición):
   `fundamentals_enabled: true` con `"1.0"` o `"2.0"` es error. Activar
   fundamentales exige una versión nueva del modelo.

Semántica:
- `classify_setup_detailed` lee los umbrales **de su `horizonte`**; ya lo
  recibe, así que el cambio está contenido (protocolo, regla 5).
- **Umbrales `null`** → ningún score abre OPERAR: radar VIGILAR, acción
  ESPERAR, código nuevo `SCORE_UNCALIBRATED`. Por la regla 7 es el caso de
  todo horizonte v2 `calibrated: false` (medio e intradía siempre; swing si la
  regla de P3 no produce umbral). Como producción solo ejecuta swing, activar v2
  con swing calibrado deja medio e intradía sin OPERAR por score.
- **`calibrated: false` con números** → solo existe en `"1.0"` durante D-47. Se
  clasifica con ellos y **todo** informe, mensaje de Telegram, texto al LLM y
  el contrato persistido de la pasada lo declaran («umbral no calibrado»).
  Nunca se imprime «calibrado» a secas.
- `tracking._verdict` usa los umbrales del horizonte de la posición y, si son
  `null`, solo emite los veredictos por precio (stop / objetivo).
- `config_hash` cambia con el contrato (lo pinea el manifiesto; D-33).

## Implementación requerida — orden obligatorio

Rama `research/a03-score-v2` desde `main` (una vez fusionado el PR #26), con los
pasos en este orden, cada uno en su commit compilable. **El orden es lo que
impide el estado prohibido y lo que garantiza que P3 se ejecuta sobre un
pre-registro cerrado.**

0. pre-registro condicionado — PR #26;
1. contrato de umbrales y persistencia v7, con v1 activo;
2a-doc. cerrar componente asiático y VIX → **SHA final del pre-registro**;
2a-code. implementar el contexto congelado y verificarlo;
2. implementar Score v2 sin activar;
3. ejecutar P3 una sola vez;
4. registrar resultado y calibración;
5. activar v2 solo si D-47 y el resultado lo permiten.

**Paso 0 — Pre-registro condicionado (PR #26). HECHO el 2026-09-26.** D-45,
D-46, D-47 y D-49 registradas (D-48 retirada) en `docs/decision-log.md`,
requisito 2 de GATE P3 corregido en `docs/gates.md` y esta ficha en la rama
`docs/t019-preregistro-p3`, fusionada después por PR. Fija todo el diseño
estadístico de P3, **pero no es el SHA que autoriza a ejecutarlo**: en ese
momento PR-1 y la semántica point-in-time concreta del VIX seguían abiertas.
Se cerraron en 2a-doc (D-50 a D-57).

**Paso 1 — Contrato de umbrales y persistencia v7, con v1 activo y sin cambio de
comportamiento. HECHO el 2026-09-29** en `research/a03-score-v2`; evidencia en
`evidence/2026-09-29-T-019-paso1-contrato-umbrales-v7/`. Además de lo que
sigue, la configuración exige umbrales para los tres horizontes válidos (no
solo los de `horizontes`), porque `abrir` acepta cualquiera.
- `ScoringConfig` con `score_model_version` y `thresholds` por horizonte y las
  nueve reglas de validación; `config.yaml` con v1 70/60 **declarados
  `calibrated: false`** en los tres horizontes.
- `classify_setup_detailed` y `tracking._verdict` leen del horizonte.
- `Score.grade` y `conviction_label` siguen con sus cortes en v1 (son la
  presentación de v1), aisladas para que no sean alcanzables desde v2.
- **Contrato de persistencia** (D-47 exige poder reconstruir qué versión y qué
  umbrales reales produjeron cada decisión; `config_hash` solo no basta):
  - **`analysis_run.scoring_contract_json`**: JSON canónico, con la misma
    serialización determinista que `config_hash`, del contrato de scoring
    realmente usado por la pasada: `score_model_version`,
    `fundamentals_enabled` y, por horizonte, `score_model_version`,
    `calibrated`, `min_score_operar`, `min_score_vigilar` y `calibration_ref`.
    Se escribe **junto al manifiesto**, desde el objeto de configuración cargado
    en esa pasada, y **nunca** se reconstruye desde el `config.yaml` actual. Toda
    pasada desde v7 lo lleva; `analysis_run.score_model_version` debe coincidir
    con el del contrato o la pasada aborta.
  - **`recommendation`**: no se duplica nada. `recommendation.run_id →
    analysis_run` identifica el contrato exacto.
  - **`position_review.run_id`**: columna nueva, nullable, con relación a
    `analysis_run(run_id)`. El comando `seguimiento` **crea su manifiesto** como
    cualquier ejecución que persiste (INV-18) y cada revisión lleva su `run_id`.
    No hace falta una columna suelta `position_review.score_model_version`: la
    versión y los umbrales salen del run.
  - **Filas anteriores a v7**: `run_id = NULL` en `position_review`,
    `scoring_contract_json = NULL` en `analysis_run`; su contrato de umbrales es
    **no recuperable**, salvo evidencia externa verificable (por ejemplo, un
    `config.yaml` en el `git_sha` de la pasada, con `git_dirty = 0` y cuyo hash
    coincida con `config_hash`). **Nunca** se rellena con `"1.0"` ni con nada
    inventado: la fórmula v1 cambió durante 2026 sin cambiar de versión.
- **Migración v7** (`main` ya está en v6 desde T-018,
  `_migration_v6_validated_bar_cache` en `advisor/storage/migrations.py:268`):
  añade `analysis_run.scoring_contract_json` y `position_review.run_id`. Backup
  previo y prueba de restauración (INV-17). Recorridos que el test y la evidencia
  deben cubrir:
  - **base nueva:** se crea en v1 y recorre la cadena hasta la vigente en la
    misma apertura (`db.py:227–243`), así que llega directamente a v7;
  - **base de `main`:** v6 → v7, con su backup `pre-v7`;
  - **la Pi:** estaba en **v5** al escribirse la ficha y desde el 2026-09-26
    está en **v6** (`v0.4.0`); no se toca en A-03;
  - **futuro despliegue que contenga T-018 y P3:** v5 → v6 → v7, cada paso con su
    backup;
  - **rollback de código:** no deshace **ninguna** de las dos migraciones
    (D-32); volver atrás exige restaurar el backup previo a v6 o a v7 y aceptar
    la pérdida de las pasadas guardadas desde entonces.
- Verificación: `backtest --vintage 071ddb2b…` **idéntico byte a byte** al de
  A-02 (866 operaciones; hash normalizado `49b12c85…`), salvo lo que cambie por
  `config_hash`. Informe: solo cambia la etiqueta «no calibrado».
- **Aviso de esquema:** este paso migra a v7. La Pi (v6 desde el 2026-09-26)
  no se toca.

**Paso 2a-doc — Cerrar el contexto point-in-time. Solo documentación, antes de
tocar código. HECHO el 2026-09-29** (D-50 a D-57; evidencia en
`evidence/2026-09-29-T-019-paso2a-doc-inspeccion/`). Una primera inspección se
detuvo en OWNER_DECISION_REQUIRED, el propietario decidió y la inspección se
completó con el censo de la población.
1. Resolver PR-1 por inspección de la materia prima y de la semántica temporal.
2. Si exige decisión del propietario, **detenerse y obtenerla**.
3. Fijar exactamente la regla point-in-time del VIX (D-49).
4. Definir el `analysis_timestamp` histórico de cada señal.
5. Actualizar la composición definitiva de `contexto` en v2 (tabla de la
   especificación).
6. Registrar las decisiones necesarias en `docs/decision-log.md`.
7. Commit **exclusivamente documental**.

**El SHA de este commit es el pre-registro completo y ejecutable de P3.** Toda
evidencia de P3 lo cita. **P3 no se puede ejecutar antes.** 2a-doc completa lo
que el paso 0 dejó abierto: PR-1, VIX, `analysis_timestamp` y composición de
`contexto`. No toca ninguna otra parte del diseño estadístico, **salvo las
enmiendas explícitas del propietario anteriores al SHA de 2a-doc**, decididas
el 2026-09-29 sin mirar desenlaces, expectancy ni scores:
- **D-51:** cripto fuera de la población, por imposibilidad temporal.
- **D-55:** historia insuficiente para la SMA200 → exclusión. Sustituye a la
  regla v1 de dato ausente para ese caso.
- **D-57:** Bonferroni con `m = 20`, que sustituye a `m = 14`.

Ninguna otra parte del diseño cambia.

**Paso 2a-code — Implementar exactamente lo congelado.** (Después del SHA de
2a-doc.)
- Implementar en **una sola función** de contexto point-in-time la regla de
  `analysis_timestamp` (D-50) y las de VIX, tendencia y SMA (D-53) y de Asia
  (D-52). Solo la usa Score v2: v1 no cambia (D-47).
- Sustituir `_align` y `shift(1)` en el laboratorio y el backtest. Es el
  defecto de `_naive_dates` registrado en D-53.
- Añadir a `exchange_overrides.yaml` los cinco cierres aprobados en D-54, con
  sus fuentes.
- Excluir de P3, como unión y publicando contador y listado por motivo:
  - `excluded_crypto` (D-51);
  - `excluded_asia_missing` (D-52);
  - `excluded_trend_sma_history`, con el código `NO_CALCULABLE_CONTEXT_HISTORY`
    (D-55).
- Controles:
  - población de 94.094 señales en swing y 89.333 en medio;
  - sha256 de la lista ordenada «activo, sesión de señal» igual al del censo
    `06`;
  - 19 y 5 bloques con señales.
- Producción, backtest, event study y seguimiento usan la misma semántica
  (R-CTX): `review_positions` construye el contexto con esa función y la misma
  referencia temporal que la pasada.
- Verificar la paridad (tests de integración de INV-06) y medir el impacto
  sobre la cosecha.
- Si la implementación demuestra que la regla congelada es imposible, ambigua o
  necesita cambiarse: **BLOCKER → volver al propietario**. No se adapta la regla
  después de medir.

**Revisión independiente de look-ahead, en dos momentos:**
1. **antes de P3**: verifica 2a-doc y 2a-code (que la regla congelada no
   contiene look-ahead y que los cuatro caminos usan la misma implementación);
   P3 no se ejecuta sin ella;
2. **al final de P3**: revisión completa del gate (GATE P3 requisito 5).

**Paso 2 — Score v2 en el código, sin activar.** (Requiere 2a-code.)
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

**Paso 3 — P3 ejecutado una sola vez** sobre el pre-registro completo del SHA de
2a-doc (sección siguiente), y solo después de la revisión 1 de look-ahead.
Comandos nuevos o extendidos en `advisor/main.py` (`event-study`,
`capacidad-estadistica`, `ablacion-score` con `--score-model 2.0`, o un
`score-v2` que los agrupe; el implementador elige y la ficha lo registra).
Resultado y veredicto publicados en `evidence/`.

**Paso 4 — Registrar resultado y calibración.** Si la regla pre-registrada da
umbrales para swing, se registran como D-nn con su `calibration_ref`. Si no, se
registra que swing queda `calibrated: false`. Medio e intradía,
`calibrated: false` por D-45. **Nada de esto toca aún la configuración activa.**

**Paso 5 — Activación de v2 en producción, solo si D-47 y el resultado lo
permiten, en un solo commit:** `scoring.score_model_version: "2.0"` y los tres
bloques de umbrales `"2.0"` a la vez, válidos por las reglas 7 y 8. Con swing
sin calibrar, este paso **no se hace** en A-03. Sin despliegue: la Pi es
decisión aparte.

## P3 — experimento pre-registrado

Este bloque, junto con la sección «Contexto: paridad y point-in-time», forma el
pre-registro de P3, en **dos niveles**:
- **PR #26 (paso 0) = pre-registro condicionado.** Todo lo escrito aquí queda
  fijo, salvo lo que el paso 2a-doc tiene que completar: PR-1, la regla del VIX,
  el `analysis_timestamp` histórico y la composición definitiva de `contexto`.
  No autoriza a ejecutar P3.
- **Enmiendas del propietario al pre-registro condicionado**, anteriores al
  SHA de 2a-doc y decididas sin mirar desenlaces: **D-51** (cripto fuera de la
  población), **D-55** (exclusión por historia insuficiente de la SMA200) y
  **D-57** (Bonferroni `m = 20`). Son las únicas partes del diseño estadístico
  del paso 0 que cambian en 2a-doc.
- **SHA del paso 2a-doc = pre-registro completo y ejecutable.** Es el que se
  cita en toda la evidencia de P3; P3 no puede ejecutarse antes.

Cualquier cambio posterior a ese SHA es un estudio nuevo con decisión propia.

**Datos e identidad.**
- `data_vintage_id = 071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841`.
- Universo `vigente` (93 analizables), `universe_vintage_id =
  237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19`. **La
  población de P3 son sus 90 activos no cripto** (D-51), en cinco regiones:
  ASIA 16, EUROPA 30, USA 40, GLOBAL 3 y EMERGING_MARKETS 1.
- `score_model_version = "2.0"` (y `"1.0"` solo para el antes/después).
- En la cabecera de cada salida: SHA del paso 2a-doc (pre-registro), SHA del
  código que ejecuta y `config_hash`.
- Etiqueta en toda tabla y conclusión: «condicionado al universo seleccionado
  en 2026 (sesgo de supervivencia y selección no corregido)».

**Horizontes.** Swing es el horizonte **confirmatorio**. Medio se calcula con el
mismo código y se publica **solo por trazabilidad**, con el veredicto forzado
«NO CONCLUYENTE — inválido (bloque parcial 102 ≤ 250)», independiente de sus
números (A-02, D-42). Intradía no tiene laboratorio y no se mide.

**Población de señales.** Parte de la de P2.3: todas las barras elegibles, sin
`classify()`, sin estado de posición, con solapamiento, warmup 120, horizonte
máximo 40 (swing) / 250 (medio), geometría de la línea 0 (`config.levels`
vigente), modo administrado. Sobre ella se aplican **tres motivos de
exclusión**, ninguno por rendimiento. Recuento sin leer desenlaces (censo
`06` de la evidencia de 2a-doc):

| | swing | medio |
|---|---|---|
| población de A-02 (93 activos) | 106.363 | 94.273 |
| − cripto (D-51, 3 activos) | −5.112 | −4.722 |
| − Asia no calculable por hueco del proveedor (D-52) | −396 | −218 |
| − SMA200 sin historia causal suficiente (D-55) | −6.937 | 0 |
| (solapamiento Asia ∩ SMA200, contado una vez) | +176 | 0 |
| exclusiones, unión deduplicada | 12.269 | 4.940 |
| **población de P3 (90 activos)** | **94.094** | **89.333** |
| bloques con señales | 19 | 5 |

El censo `06` calcula la población de P3 como la unión de los motivos, por
observación. No resta cifras. Evidencia:
- **Listados por motivo:** `06-excluded_crypto-*`,
  `06-excluded_asia_missing-*` y `06-excluded_trend_sma_history-*`, uno por
  horizonte.
- **Hash de la población:** sha256 de la lista ordenada «activo, sesión de
  señal», que 2a-code debe reproducir:
  - swing: `4aa12d85eb54d7a01c10a4a3e4cf04e8077c842829235a93b75f7bd19c62011a`
  - medio: `4d6eaab9b84ff23bade1df86a82e95f46da546917a226dc8438a8e88493020f8`
- **Origen de las exclusiones de Asia:** tres sesiones ausentes sin cierre
  verificado, `^KS11` 2022-05-09 y `510300.SS` 2025-10-24 y 2026-08-28.

Cualquier diferencia se explica antes de ejecutar P3.

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

**Bloques.** Longitud 60 sesiones en swing y 300 en medio, sobre la espina de
sesiones de A-02, sin cambios. La espina tiene 22 bloques en swing, el último
de 42 sesiones, y 5 en medio, el último de 102. Tras las exclusiones de 2a-doc,
la población de P3 ocupa **19 bloques en swing** (A-02 ocupaba 21: el bloque 1
lo vacía D-51, porque solo tenía señales cripto, y el 2, D-55) y 5 en medio
(`07-ocupacion-de-bloques.txt`, con el desglose por motivo).

**Bloque parcial.** La regla de A-02 (`_classify_capacity`, `<=`): un horizonte
con un bloque **ocupado** de longitud ≤ `MAX_HOLD_BARS` es inválido. En swing el
último bloque (42 > 40) es válido y entra **tal cual**, sin repesar, fusionar ni
descartar. Un bloque con menos de 5 observaciones en una fila se declara como
motivo, como hoy.

**Método de percentil, fijado literalmente.** Para un percentil `p` sobre los
`n` valores de `Score.value` ordenados de menor a mayor, `x[0] … x[n−1]`:

    cut(p) = x[ceil(p · n) − 1]        (índice cero-based)

Es el método **nearest-rank sobre un valor realmente observado**. No se delega
en el valor por defecto de NumPy ni de pandas. Con `p = k/100` se calcula en
**aritmética entera**, `ceil(k·n/100) = (k·n + 99) // 100`, para que el índice no
dependa del redondeo en coma flotante (en coma flotante, `0,07 · 100` da
`7,000000000000001` y `ceil` devolvería 8 en vez de 7).

**Bandas v2 — quintiles, fijados sin mirar resultados.** Los cortes son
`cut(0,20)`, `cut(0,40)`, `cut(0,60)` y `cut(0,80)` de `Score.value` v2 sobre las
94.094 señales de swing de P3, calculados **solo con la nota** (ningún campo de
desenlace entra en su cálculo; el revisor lo comprueba). Bandas `v2-Q1` …
`v2-Q5`: `Q1 = [mín, c20)`, `Q2 = [c20, c40)`, `Q3 = [c40, c60)`,
`Q4 = [c60, c80)`, `Q5 = [c80, máx]`; una observación exactamente igual a un
corte entra en la banda superior.

**Empates en los cortes.** Si dos cortes consecutivos son iguales: no se
fusionan bandas, no se elige otro método; se declara
**`SCORE_RESOLUTION_INSUFFICIENT`** y el veredicto confirmatorio de ordenación
queda **NO CONCLUYENTE**. Los análisis descriptivos que usan los quintiles se
publican igualmente, marcados con la misma etiqueta.

Se publican siempre: los cuatro percentiles solicitados, sus cuatro valores, el
número de valores distintos de `Score.value` y el `n` de cada banda.
**Motivo de usar quintiles, declarado antes de medir:** las bandas fijas de 10 puntos dejaron en A-02 una banda alta de 65
señales en 15 bloques, que no puede concluir nada; los quintiles garantizan
bandas comparables en tamaño. No se reutilizan los cortes 50/60/70/80 de v1.
Medio usa **sus propios** quintiles, con el mismo método y la misma regla de
empates, sobre su población.

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
(`veredicto_ordenacion` y `capacidad`). Con 19 bloques, SUFICIENTE es
inalcanzable en swing y se dice así en el resultado.

**Se publica siempre, además del veredicto:** el primario con IC95, `n`,
bloques y `experimental_resolution` por quintil; la tabla **por bloque**
(19 × 5: media de `net_R` y `n`); los cuatro contrastes adyacentes (Q2−Q1 …
Q5−Q4) como descriptivos; las secundarias por quintil. La monotonía no entra en
el veredicto: es descriptiva.

**Regla de calibración de umbrales — solo swing, mecánica.**
Candidatos: `cut(0,50)`, `cut(0,60)`, `cut(0,70)`, `cut(0,80)` y `cut(0,90)` de
`Score.value` v2 en swing, con el mismo método nearest-rank y sin desenlace.
**Si dos percentiles producen el mismo score**, ese valor se evalúa **una sola
vez** como candidato y se publica qué percentiles colapsaron en él. Los
candidatos efectivos son los **valores distintos, ordenados**.

**Dos instrumentos, sin mezclarlos:**
- **Capacidad (condición 2 de OPERAR y capacidad de VIGILAR): P2.5 estándar.**
  IC95, 2.000 remuestreos, semilla `20260830` y `CapacityThresholds` vigentes,
  sin modificar el instrumento de INV-14.
- **Intervalos de decisión (condiciones 3 y 4 de OPERAR y cota de VIGILAR):
  familia Bonferroni. `m = 20`, fijo (D-57)**, es decir, la familia
  inferencial completa, definida antes de mirar P3:
  - **10 contrastes de OPERAR:** para cada uno de los 5 candidatos `c`, la
    cota inferior del primario de `[c, ∞)` (condición 3) y la del contraste
    pareado `[c, ∞) − [0, c)` (condición 4);
  - **10 pares potenciales de VIGILAR:** todas las bandas `[v, operar)` con
    `v < operar` entre los 5 candidatos, `C(5,2) = 10`, porque antes de medir
    no se sabe qué candidato será `operar`.

  Nivel `1 − 0,05/20` (= 99,75 %), **20.000** remuestreos y la misma semilla,
  porque 2.000 no estabilizan una cola del 0,125 %.
  - **m permanece en 20** aunque varios percentiles colapsen en el mismo score:
    la selección opera sobre los valores distintos, se informa del colapso, y
    ni el número de candidatos distintos ni el de pares realmente evaluados
    cambian m.
  - La regla mecánica de selección de VIGILAR no cambia. Se implementa con un envoltorio propio de P3 que pasa
  `confidence` y `n_resamples` al bootstrap, sin cambiar los valores por
  defecto del instrumento de INV-14.

La familia Bonferroni **no sustituye** al instrumento estándar de capacidad.

- Un candidato `c` **cumple OPERAR** si: (1) el horizonte es válido; (2) la
  banda `[c, ∞)` tiene capacidad `LIMITADA` o mejor y es concluyente según
  **P2.5 estándar**; (3) la cota inferior del intervalo **Bonferroni** del
  primario de `[c, ∞)` es > 0; (4) la cota inferior del intervalo **Bonferroni**
  del contraste pareado por bloque `[c, ∞) − [0, c)` es > 0 (el umbral separa,
  no solo selecciona una población que ya era positiva); (5) profit factor
  agrupado de `[c, ∞)` > 1 (restricción del protocolo, regla 2).
- **Meseta, no máximo**, sobre los candidatos **distintos, ordenados**:
  `min_score_operar` = el menor candidato `c` tal que **todos** los candidatos
  ≥ `c` cumplen. Si no existe, swing queda `calibrated: false` y no se publica
  ningún número como umbral.
- `min_score_vigilar` solo existe si existe `min_score_operar`. Un candidato
  distinto `v < operar` **cumple VIGILAR** si la banda `[v, operar)` tiene
  capacidad `LIMITADA` o mejor según **P2.5 estándar** y la cota **superior**
  de su intervalo **Bonferroni** es > 0 (no es demostrablemente perdedora). Se
  recorre así, sin margen de interpretación:

  ```text
  distintos = sorted(set(cut(k/100) for k in (50, 60, 70, 80, 90)))
  candidatos_bajo = [c for c in reversed(distintos) if c < operar]   # de mayor a menor
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

**Multiplicidad.** Se cuentan y publican todas las comparaciones. Swing, con la
lista vigente:
- confirmatoria: **1** (Δ Q5−Q1, IC95);
- familia inferencial de umbrales: **20** (10 de OPERAR + 10 pares potenciales
  de VIGILAR), corregida por Bonferroni (D-57);
- descriptivas, sin corrección y **sin** valor inferencial por separado:
  - quintiles: 5;
  - adyacentes: 4;
  - regiones, primario + Δ: 5 × 2 = 10;
  - activos, primario + Δ: 90 × 2 = 180;
  - intra-activo agregado: 1;
  - intra-activo por activo: 90;
  - 3 ablaciones × (5 quintiles + 1 Δ): 18;

  total descriptivas = **308**;
- **total swing = 1 + 20 + 308 = 329**.

Antes de 2a-doc eran 317 descriptivas, 332 en swing y 318 en medio. Las
descriptivas cambian solo por los activos, de 93 a 90 (D-51), y la familia de
umbrales pasa de 14 a 20 (D-57). El censo confirma que las cinco regiones y los
90 activos siguen presentes en los dos horizontes tras todas las exclusiones.

**Medio** no ejecuta la familia de 20 umbrales, porque D-45 prohíbe intentar
calibrarlo; se cuenta por separado todo lo que realmente se calcule por
trazabilidad (con la misma lista, 1 + 308 = **309**: el censo confirma que las
cinco regiones y los 90 activos producen señales en medio). Total =
329 + 309 = **638**.

Se publican **tres contadores calculados por el código**:
`comparaciones_swing`, `comparaciones_medio_trazabilidad` y
`comparaciones_totales`. Ningún total se codifica como verdad: el test los
deriva de las salidas previstas y falla si divergen. Las cifras 329 y 309 de
arriba son la aritmética de la lista vigente, no un valor que el código deba
reproducir a la fuerza; cualquier diferencia se explica antes de publicar.

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
  sus propios quintiles sin desenlace (mismo método nearest-rank y misma regla
  de empates: un colapso de cortes da `SCORE_RESOLUTION_INSUFFICIENT` y
  veredicto NO CONCLUYENTE para esa ablación), primario por quintil, Δ Q5−Q1 y
  su veredicto.
- Se publica, además, la migración de quintil entre el score completo y cada
  ablación.
- **La ablación no selecciona.** No hay regla de selección pre-registrada, así
  que ningún resultado de la ablación cambia Score v2 en esta tarea: si una
  dimensión parece inútil o dañina, se abre una decisión y una ficha posterior
  (o un Score v3).

### P3 — sesgo de universo
- Primario y Δ Q5−Q1 **global**, **por región** (5) y **por activo** (90).
- **Ordenación dentro de cada activo por bloques temporales** (roadmap,
  «Universo»): para cada activo y bloque, `media net_R(Q4∪Q5) − media
  net_R(Q1∪Q2)` con los quintiles globales; primario intra-activo = media por
  bloque de la media entre activos de esas diferencias; IC95 por bootstrap de
  bloques. Q4∪Q5 frente a Q1∪Q2, y no Q5 frente a Q1, porque muchos activos no
  tienen señales en un quintil extremo en cada bloque; se decide aquí, antes de
  medir. Se publica también por activo, como descriptivo.
- **Huecos del intra-activo, pre-registrados:**
  - un par activo-bloque sin señales en `Q4∪Q5` o sin señales en `Q1∪Q2` es
    **no calculable** y se excluye; nunca se sustituye por cero;
  - se publica el número de pares excluidos y su motivo;
  - un bloque que queda con **cero** activos calculables se excluye del
    bootstrap y se publica;
  - `n_blocks` del intervalo es el número de **bloques calculables reales**;
  - si cae por debajo del mínimo aplicable según
    `CapacityThresholds.limited_blocks` (vigente: 12), el resultado es **NO
    CONCLUYENTE**. La regla depende de ese umbral pre-registrado de capacidad;
    12 es su valor vigente, no una constante propia de T-019.
- Todas con la etiqueta de universo condicionado a 2026.

## Qué NO debe modificarse
- `min_rr_ratio`, `compute_levels*`, `entry_max_rr`, `RR_TOO_LOW`,
  `evaluate_trade_at_entry` y la geometría (`config.levels`).
- Los componentes y tramos de catalizador, técnico y contexto, salvo lo que
  fijaron D-52 (Asia) y D-53 (VIX y tendencia).
- `advisor/`, `tests/` y `config.yaml` **mientras el propietario no autorice
  empezar la implementación**.
- El estimador, los bloques, la semilla, `CapacityThresholds`, la cosecha y
  `universe.yaml`.
- La evidencia de A-02.
- La Pi y su esquema (v6 desde el 2026-09-26).

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
- `test_config_v2_no_calibrado_con_numeros_es_invalido` (regla 7): el YAML
  `score_model_version: "2.0"`, `calibrated: false`, 70/60 → `ValidationError`;
  y `"1.0"` con `calibrated: false` y 70/60 → válido.
- `test_config_v2_calibrated_true_solo_en_swing` (regla 8): `"2.0"` con medio o
  intradía `calibrated: true`, aunque traigan números y referencia →
  `ValidationError`; `"1.0"` con cualquier `calibrated: true` →
  `ValidationError`.
- `test_config_fundamentales_exigen_otra_version` (regla 9): `"1.0"` y `"2.0"`
  con `fundamentals_enabled: true` → `ValidationError`.
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
- `test_percentil_nearest_rank_exacto`: valores 1…10 → `cut(0,20)` = x[1] = 2,
  `cut(0,25)` = x[2] = 3, `cut(0,60)` = x[5] = 6; y con 100 observaciones
  1…100, `cut(0,07)` = x[6] = 7, no x[7] = 8 (el índice se calcula en
  aritmética entera).
- `test_quintiles_con_cortes_iguales`: 100 valores cuyos 50 menores valen 10 →
  `c20 = c40` → `SCORE_RESOLUTION_INSUFFICIENT` y veredicto NO CONCLUYENTE, sin
  fusionar bandas; se publican los percentiles, sus valores, el número de
  distintos y el `n` por banda.
- `test_candidatos_p50_igual_p60`: se evalúa un solo candidato para los dos, se
  publica el colapso y m sigue siendo 20.
- `test_candidatos_varios_percentiles_mismo_valor`: p60 = p70 = p80 → tres
  candidatos distintos en total; la meseta opera sobre ellos.
- `test_vigilar_con_candidatos_repetidos`: el recorrido de VIGILAR usa los
  valores distintos, no los percentiles.
- `test_intervalos_capacidad_estandar_y_bonferroni_separados`: la condición 2
  usa IC95 con 2.000 remuestreos; las 3 y 4 y la cota de VIGILAR, nivel
  `1 − 0,05/20` con 20.000;
  los valores por defecto del instrumento de INV-14 no cambian.
- `test_familia_bonferroni_m20`:
  - la familia enumera exactamente 20 intervalos: 5 candidatos × (primario
    `[c, ∞)` + contraste `[c, ∞) − [0, c)`) y los 10 pares `[v, operar)` con
    `v < operar` entre los 5 candidatos;
  - `confidence = 1 − 0,05/20`, 20.000 remuestreos, semilla `20260830`;
  - con p50 = p60 = p70 (colapso), m sigue siendo 20 y se publica el colapso.
- `test_exclusiones_p3_union_sin_doble_conteo`:
  - una observación con Asia no calculable **y** SMA200 sin historia cuenta
    una vez en la unión y aparece en los dos listados;
  - cripto se excluye antes de calcular `analysis_timestamp`.
- `test_sma200_sin_historia_excluye`: con 199 cierres de `^STOXX50E`
  causalmente disponibles, la observación queda
  `NO_CALCULABLE_CONTEXT_HISTORY` y se excluye; con 200, no.
- `test_hueco_stoxx_usa_ultimo_cierre_causal`:
  - si falta la barra de la sesión exigible, se usa el último cierre presente
    con `available_at <= analysis_timestamp`, la observación no se excluye y
    se publica su antigüedad;
  - nunca se usa un cierre posterior a `analysis_timestamp`.
- `test_analysis_timestamp_por_plaza` (D-50). Casos calculados en 2a-doc con
  los calendarios del repo, `settlement_minutes = 20` y el timer de Londres:

  | plaza | `d` | `d+1` | `analysis_timestamp` | qué cubre |
  |---|---|---|---|---|
  | XETRA | 2026-08-26 | 2026-08-27 | 2026-08-27 07:00 BST (06:00Z) | caso normal en verano |
  | XETRA | 2025-03-12 | 2025-03-13 | 2025-03-13 07:00 GMT (07:00Z) | invierno |
  | NYSE | 2026-08-26 | 2026-08-27 | 2026-08-27 08:30 BST (07:30Z) | 14:30 BST coincide con la apertura y no cuenta |
  | NYSE | 2025-03-12 | 2025-03-13 | 2025-03-13 08:30 GMT (08:30Z) | desfase de DST EE. UU./Reino Unido |
  | NYSE | 2025-10-29 | 2025-10-30 | 2025-10-30 08:30 GMT (08:30Z) | desfase de DST de otoño |
  | JPX | 2026-08-26 | 2026-08-27 | 2026-08-26 21:00 BST (20:00Z) | caso normal: pasada del día `d` |
  | JPX | 2022-04-28 | 2022-05-02 | 2022-04-29 21:00 BST (20:00Z) | festivo de la plaza entre `d` y `d+1` |
  | HKG | 2022-04-14 | 2022-04-19 | 2022-04-18 21:00 BST (20:00Z) | Semana Santa en Hong Kong |
- `test_vix_tendencia_point_in_time` (D-53). Sesión de VIX (XNYS) y de
  `^STOXX50E` (XETR) disponible en cada `analysis_timestamp` de la tabla
  anterior:
  - XETRA 2026-08-26 → VIX 2026-08-26 y STOXX 2026-08-26;
  - XETRA 2025-03-12 → VIX 2025-03-12 y STOXX 2025-03-12;
  - NYSE 2026-08-26 → VIX 2026-08-26 y STOXX 2026-08-26, **no** 2026-08-27
    (el look-ahead de `_naive_dates`);
  - NYSE 2025-03-12 → VIX 2025-03-12 y STOXX 2025-03-12;
  - NYSE 2025-10-29 → VIX 2025-10-29 y STOXX 2025-10-29;
  - JPX 2026-08-26 → VIX **2026-08-25**, porque el 26 no estaba disponible a
    las 20:00Z, y STOXX 2026-08-26;
  - JPX 2022-04-28 → VIX 2022-04-28 y STOXX 2022-04-29;
  - HKG 2022-04-14 → VIX 2022-04-14 y STOXX 2022-04-14, por el Viernes Santo
    y el Lunes de Pascua cerrados.

  Además, los cuatro caminos (producción v2, backtest, event study y
  seguimiento) devuelven esos mismos valores para esos instantes.
- `test_intra_activo_excluye_pares_incompletos`: activo-bloque sin Q1∪Q2 se
  excluye (no cuenta como 0) y se publica; bloque sin activos calculables sale
  del bootstrap; por debajo del mínimo aplicable según
  `CapacityThresholds.limited_blocks` (vigente: 12) → NO CONCLUYENTE.
- `test_contadores_de_comparaciones_derivados`: los tres contadores se derivan
  de las salidas previstas; medio no incluye la familia de umbrales.
- `test_veredicto_ordenacion_tabla`: cuatro casos sintéticos con bloques de
  tamaños distintos, uno por fila de la tabla del veredicto, incluido 19 bloques
  con anchura 0,10 → LIMITADA (no SUFICIENTE).
- `test_regla_de_umbral_meseta`: candidatos que cumplen {p60, p80, p90} pero no
  p70 → operar = p80, no p60.
- `test_migracion_v7`: base nueva → v7; base v6 → v7 con backup `pre-v7` y
  restauración; base v5 → v6 → v7. Tras migrar, las filas anteriores tienen
  `position_review.run_id = NULL` y `analysis_run.scoring_contract_json = NULL`,
  sin ningún `"1.0"` inventado.
- `test_analysis_run_guarda_el_contrato_de_scoring`: el JSON persistido es el
  canónico del contrato cargado en la pasada; cambiar después `config.yaml` no
  cambia lo guardado.
- `test_seguimiento_crea_manifiesto_y_run_id`: `seguimiento` inserta su
  `analysis_run` y cada `position_review` lleva ese `run_id`.

## Tests de integración
- **INV-06, código:** para `AAPL`, `SAP.DE` y `SXR8.DE` sobre la cosecha, el
  score v2 de `analyzer`, `backtest/engine` y `event_study` coincide en las
  mismas barras (extensión del test de equivalencia prefijo/vectorizado).
- **INV-06, contenido:** el `MarketContext` que ven los tres caminos para la
  misma barra produce los mismos `points` (falla hoy por H-1; tiene que pasar
  tras el paso 2a-code). Incluye `review_positions` (R-CTX).
- **Equivalencia v2 ↔ ablación:** en los mismos tres activos, `Score.value` v2
  == `100·(points − rr − conviccion)/(evaluable_max − 20 − 10)` reconstruido
  desde las `DimensionObservation` v1 (P2.2), con `assert_allclose` estrecho.
  Como D-52 y D-53 cambian el contexto, la reconstrucción parte de observaciones
  v1 recalculadas con el contexto nuevo, y el test lo refleja.
- **Recomendación persistida:** una pasada con versión activa X deja
  `analysis_run.score_model_version = X` y un `scoring_contract_json` con esa
  misma versión y los umbrales usados; persistir una oportunidad cuyo
  `Score.model_version` ≠ X aborta la transacción. Por `run_id` se reconstruyen
  versión, umbrales y estado `calibrated` de cada recomendación y revisión.
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
- número de señales con contexto imputado (H-6) y el efecto sobre la nota de
  lo que congele el paso 2a-doc (regla del VIX y, en su caso, componente
  asiático), medido en 2a-code;
- cambio de `confianza` en la pasada de producción (paso 2), por motivo;
- **clasificación operativa:** el número de señales cuya clasificación cambia
  **solo** se calcula si swing sale `calibrated: true`, comparando v1 70/60 con
  v2 y sus umbrales calibrados en `backtest --vintage`. Si no hay umbrales
  válidos, la salida dice «no aplica: sin umbrales v2 calibrados» y **no** se
  calcula con 70/60.
- Ninguna mejora de expectancy se atribuye a una dimensión si su intervalo no lo
  permite.

## Criterio de aceptación
1. D-45, D-46, D-47 y D-49 registradas y `gates.md` corregido **antes** del
   primer commit de código; PR-1 respondida, regla del VIX y
   `analysis_timestamp` fijados en el commit documental 2a-doc **antes** de
   ejecutar P3; el SHA de 2a-doc aparece en toda la evidencia.
2. Score v2 implementado como está especificado, con `"2.0"` y v1 intacto.
3. Contrato de umbrales por horizonte con las nueve reglas de validación, y
   contrato de persistencia v7 (`scoring_contract_json`,
   `position_review.run_id`, manifiesto de `seguimiento`).
4. P3 ejecutado **una vez** con el pre-registro, sin desviaciones, o con cada
   desviación declarada como BLOCKER y parada.
5. Veredicto de ordenación publicado con su tabla, por bloque, secundarias,
   `experimental_resolution` y contador de comparaciones.
6. Ablación y sesgo de universo publicados.
7. Impacto medido como arriba.
8. `pytest -q`, `ruff check .` y `mypy advisor` limpios; producción idéntica en
   `backtest --vintage` tras los pasos 1 y 2.
9. Revisión independiente de look-ahead hecha en sus dos momentos (antes de P3,
   sobre 2a-doc y 2a-code; y al final) y sus hallazgos cerrados.
10. Matriz de GATE P3 rellenada con rutas de evidencia.

## Criterio de rechazo
- Cualquier estado del repositorio en el que v2 esté activo y se clasifique con
  70/60 o con cualquier número declarado para `"1.0"`.
- Umbrales v2 con números que no salgan de la regla pre-registrada, o umbrales
  v2 con números y `calibrated: false` (regla 7).
- Medio o intradía `calibrated: true` en v2, o el veredicto de medio derivado de
  sus números.
- P3 ejecutado antes del SHA de 2a-doc o sin la revisión 1 de look-ahead; una
  regla de contexto cambiada después de medir.
- Cortes o bandas elegidos después de ver desenlaces; P3 ejecutado más de una
  vez con reglas distintas.
- Una secundaria publicada sin el primario, o un resultado sin intervalo ni
  `experimental_resolution` (INV-14, INV-20).
- Redefinir Score v2 a partir de la ablación dentro de esta tarea.
- El RR dejando de condicionar la ejecutabilidad, o `min_rr` afectando al score.
- Cualquier despliegue o migración en la Pi.

## Evidencia que debe quedar registrada
`evidence/<fecha>-T-019-score-v2/`:
- `README.md`: SHA de 2a-doc (pre-registro ejecutable), SHA del PR #26
  (pre-registro condicionado), SHA del código, `data_vintage_id`,
  `universe_vintage_id`, `score_model_version`, `config_hash`, comandos exactos,
  veredicto y matriz de GATE P3;
- `produccion-backtest-{MAIN,RAMA}.txt` de los pasos 1 y 2 con su hash
  normalizado;
- `p3-ordenacion-{swing,medio}.txt` (percentiles solicitados, valores de los
  cortes, número de valores distintos, `n` por banda, por bloque, Δ,
  secundarias, veredicto y los tres contadores);
- `p3-calibracion-swing.txt` (los cinco percentiles, los candidatos distintos y
  los colapsos, cada condición con su intervalo y su instrumento, y el
  resultado de la regla);
- `p3-ablacion-{swing,medio}.txt`, `p3-universo-{swing,medio}.txt`;
- `impacto.md` y sus tablas;
- `revision-look-ahead-previa.md` (antes de P3, sobre 2a-doc y 2a-code) y
  `revision-look-ahead.md` (final), del revisor independiente;
- `hashes-de-tablas.txt`;
- `final-pytest-ruff-mypy.txt`.

## Commit esperado
Rama `research/a03-score-v2`. Primeras líneas, una por paso:
- `docs(T-019): pre-registro de P3 y decisiones de Score v2` (PR #26, hecho)
- `feat(scoring): umbrales por horizonte y contrato de scoring persistido (v7), sin cambio de comportamiento`
- `docs(T-019): contexto point-in-time congelado — pre-registro ejecutable de P3` (2a-doc)
- `feat(context): una sola semántica point-in-time del contexto en producción, laboratorio y seguimiento` (2a-code)
- `feat(scoring): Score v2 sin RR ni convicción, sin activar`
- `research(P3): ordenación, ablación y sesgo de universo de Score v2 sobre 071ddb2b`
- `docs(T-019): resultado de P3 y estado de calibración por horizonte`

## Actualización documental requerida
- Paso 0 (hecho): `docs/decision-log.md` (D-45, D-46, D-47, D-49; D-48 retirada), `docs/gates.md` (requisito 2 de
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
adicionales a Asia (IMPORTANTE, ahora en H-1, D-49 y R-CTX), regla de VIGILAR ambigua
(MENOR, ahora en pseudocódigo) y estado del árbol desactualizado (MENOR).

**Segunda y tercera revisión (PR #26).** La segunda (sobre `5a036c1`, revisión
propia y refutación estadística de Codex) dio `CORREGIR_ANTES_DE_FUSIONAR` con
cuatro BLOCKER y siete IMPORTANTE. El propietario aprobó sus resoluciones y este
tercer commit las incorpora: pre-registro condicionado frente a ejecutable
(2a-doc / 2a-code) y revisión de look-ahead en dos momentos (B1); regla 7 del
contrato (B2); método nearest-rank y regla de empates (B3); instrumento
estándar de capacidad separado de la familia Bonferroni (B4); contrato de
persistencia v7 (I1); composición fija por versión (I2); `analysis_timestamp` y
calendario del VIX (I3); cláusulas de PR-1 (I4); contador recalculado a 332 en
swing (I5); huecos del intra-activo (I6); escapatorias del requisito 2 (I7); y
orden de los pasos.

## Matriz de GATE P3

| # | Requisito (texto tras la decisión A) | Evidencia exacta que lo satisface |
|---|---|---|
| 1 | Dimensiones y pesos redefinidos y documentados con `score_model_version` nuevo; nada posterior se mezcla con lo anterior sin etiqueta | D-46 registrada; `advisor/analysis/scoring.py` con `"2.0"` y `Score.model_version`; `test_v2_valor_del_caso_base`, `test_v1_y_v2_tienen_versiones_distintas`, `test_bandas_v1_rechazan_observaciones_v2`, test de recomendación persistida; `README.md` actualizado |
| 2 | Umbrales por horizonte con estado `calibrated` ligado a la versión; swing `calibrated: true` solo si la regla pre-registrada produce umbrales válidos, y `calibrated: false` también válido si no los produce, publicando resultado y motivo; medio `calibrated: false` (D-42, D-45); intradía `calibrated: false` | D-45 registrada y `gates.md` corregido; contrato en `advisor/config.py` con las reglas 7 y 8 y sus tests; `p3-calibracion-swing.txt` con el resultado mecánico de la regla; D-nn del paso 4 con el estado de los tres horizontes |
| 3 | Ordenación bajo el primario, por banda y por bloque, con veredicto SUFICIENTE / LIMITADA / INSUFICIENTE / NO CONCLUYENTE | `p3-ordenacion-swing.txt` (percentiles y cortes nearest-rank, valores distintos, quintiles, IC95, tabla por bloque, Δ Q5−Q1, secundarias, `experimental_resolution`, veredicto, tres contadores de comparaciones); `p3-ordenacion-medio.txt` con veredicto forzado por invalidez |
| 4 | Ablación por dimensión (`score_sin_X`) publicada | `p3-ablacion-{swing,medio}.txt`, tres dimensiones, mismo procedimiento que el completo, sin selección |
| 5 | Revisión independiente del look-ahead | `revision-look-ahead-previa.md` (antes de P3, sobre 2a-doc y 2a-code) y `revision-look-ahead.md` (final), de otro agente, con al menos: que el `analysis_timestamp` y la regla del VIX congelados en 2a-doc (D-49) no contienen look-ahead y que producción, backtest, event study y seguimiento usan la misma implementación —el revisor verifica, no elige—; la respuesta a PR-1; alineación de tendencia y fortaleza relativa; que los quintiles y candidatos no leen desenlace; que la población no depende del score; paridad de contexto producción/laboratorio/seguimiento (H-1, R-CTX); que medio no se usa para nada más que trazabilidad; hallazgos clasificados y cerrados |

## Handoff al siguiente agente
(se rellena al terminar)
