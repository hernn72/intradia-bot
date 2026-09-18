# T-009 — El filtro de ejecución, medido aparte del score (PR 5, fase 14)

Estado: BLOQUEADA
Agente: Opus (ficha) → Codex (implementación del instrumento) → Opus (medición y lectura)
Línea / fase: L0 PR 5, fase 14 de `docs/plan-ejecucion.md`
Gate al que contribuye: GATE L0 (requisito 5)

## Objetivo
Contar, sobre la cosecha congelada, **cuánto cuesta el filtro de ejecución**:
cuántas señales que el score aprueba se pierden porque la apertura siguiente
cotiza por encima de `entry_max`, y qué habría pasado con ellas. Y publicarlo
como dos capas separadas —`setup_score` y `execution filter`— sin mezclar
nunca la segunda dentro de la primera.

## Por qué existe
D-06 midió que con la geometría por defecto `entry_max_rr = price` **exactamente**,
así que toda apertura al alza es `ABOVE_MAX_ENTRY`. El backtest ya aplica esa
disciplina (`advisor/backtest/engine.py`, «la apertura debe ser ejecutable con
el mismo RR, stop y tamaño que se usarían en producción»), pero **nadie ha
contado el precio de esa disciplina**. Hoy no sabemos si el filtro:

- descarta sobre todo señales malas (protege), o
- descarta precisamente las que abrían con fuerza (sesga a la baja), o
- descarta casi todas (y entonces el asesor casi no puede operar y eso es un
  hallazgo de producto, no de código).

El roadmap dice que la tensión de D-06 se resuelve en P4 («holgura de
entrada»), pero **sin esta medición P4 no tiene con qué compararse**. Esta
ficha no decide la política: la instrumenta y la publica.

## Pregunta, métrica y criterio — PRE-REGISTRO
Se escribe **antes** de medir, según `docs/protocolo-investigacion.md`. Si algo
se decide después de ver resultados, se etiqueta `exploratorio` y se dice.

- **Pregunta primaria:** de las señales que `classify_setup` aprueba, ¿qué
  fracción resulta no ejecutable a la apertura siguiente por
  `ABOVE_MAX_ENTRY`, y cuál es la diferencia de expectancy neta en R entre
  las ejecutadas y las descartadas por ese motivo?
- **Métrica primaria:** expectancy neta en **R por bloque temporal** (la misma
  que P2, para poder compararlas), calculada por separado en dos poblaciones:
  `EJECUTADAS` y `PERDIDAS_POR_ENTRADA`. La segunda se valora con una entrada
  contrafactual **declarada**: la apertura real (el precio que el asesor
  rechazó), mismo stop y mismos objetivos, mismo coste.
- **Métricas secundarias:** tasa agrupada de acierto, `P(objetivo antes de
  stop)`, MAE, MFE, payoff, profit factor, mediana y percentiles de R,
  tamaño de muestra; desglosadas por banda de score, región, horizonte y
  código de ejecución.
- **Población:** cosecha `071ddb2b…`, los 107 analizables, horizontes `swing`
  y `medio`, con `universe_vintage_id` y `data_vintage_id` en la salida.
- **Criterio de aceptación del gate:** el gate **no exige ningún valor**. Exige
  que los números estén publicados, con muestra e incertidumbre, y que el
  código de ejecución esté en cada señal. NO CONCLUYENTE es un resultado
  válido y se declara como tal.
- **Tratamiento de la incertidumbre:** bootstrap por bloques, la maquinaria
  que ya existe en `advisor/research/bootstrap.py` y `uncertainty.py`. Si la
  muestra de una celda no llega al mínimo ya declarado (`_MIN_SAMPLE`), la
  celda se publica como insuficiente, **no** se agrega con otra para
  alcanzarlo.

## Dependencias previas
T-007 y T-008 ACEPTADAS. La medición se hace **con el código de la línea 0 ya
cerrado**, no antes: es justo lo que D-18 obliga a no repetir dos veces.

## Archivos probables
No asumir que sean exactos: verificar primero con búsqueda de símbolos.
- `advisor/backtest/engine.py` — `simulate_asset`, el bloque donde
  `execution.executable` decide si la posición se abre. Es el punto donde hoy
  se **pierde** la información: la señal rechazada desaparece sin registro.
- `advisor/backtest/report.py`, `advisor/backtest/runner.py` — agregación y
  salida por política (`POLICY_OPERAR`, `POLICY_TODAS`).
- `advisor/research/event_study.py` — `EventStudySignal`, `BandSummary`,
  `summarize_by_score_band`, `_MIN_SAMPLE`: el vocabulario de bandas ya existe
  y **se reutiliza**, no se duplica (INV-06).
- `advisor/research/bootstrap.py`, `uncertainty.py`.
- `advisor/main.py` — `cmd_backtest`, `cmd_event_study`.

## Invariantes que no pueden romperse
INV-03 (el filtro de ejecución **no** entra en `score.value`, ni siquiera
retrospectivamente: prohibido recalcular el score histórico para meter el RR
dentro), INV-04, INV-06 (un solo cálculo de RR, niveles y ejecución entre
producción e investigación), INV-05, y el point-in-time: la entrada
contrafactual usa la apertura de la barra siguiente, nunca un precio posterior.

## Implementación requerida

1. **Registrar la señal rechazada en vez de tirarla.** En `simulate_asset`,
   cuando `execution.executable` es falso, hoy la señal se descarta en
   silencio (`pending = None`). Debe emitirse un registro con: `signal_id`,
   activo, fecha de señal, fecha de apertura, score, banda, `entry_max`,
   `entry_max_tecnica`, `entry_max_rr`, apertura real, `execution.reason`
   (`ABOVE_MAX_ENTRY`, `RR_TOO_LOW`, `POSITION_TOO_SMALL`…) y los niveles.
   **Sin cambiar qué opera el backtest**: la simulación sigue exactamente
   igual, solo deja de perder información.

2. **Población contrafactual.** Simular esas mismas señales con la entrada a
   la apertura real —el precio rechazado—, mismo stop, mismos objetivos,
   mismos costes y el mismo `_check_exit`. Es la única forma de responder «qué
   habría pasado». **Debe reutilizar `simulate_asset`**, no una copia: si
   hace falta, se parametriza la disciplina de entrada
   (`entry_discipline: "respetar_entry_max" | "abrir_a_la_apertura"`), con el
   valor por defecto igual al de hoy, y la política existente intacta.

3. **Salida por las dos capas, nunca mezcladas.** Una tabla por banda de score
   con tres columnas de población: `TODAS las señales del score` ·
   `EJECUTADAS` · `PERDIDAS_POR_ENTRADA`, y sus métricas. Publicar también el
   desglose por `execution.reason`, porque `ABOVE_MAX_ENTRY` y `RR_TOO_LOW`
   no son el mismo fenómeno.

4. **Un comando reproducible**, en la línea de los que ya existen
   (`event-study`, `capacidad-estadistica`, `ablacion-score`):
   `filtro-ejecucion --horizonte <swing|medio> --vintage <id>`. Su salida lleva
   `data_vintage_id`, `universe_vintage_id`, `git_sha` y `config_hash`, como
   el resto del laboratorio. **Arreglar de paso el hallazgo abierto del
   roadmap**: el informe de `capacidad-estadistica` no publica vintage; este
   comando nace publicándolo, y si el arreglo de `capacidad-estadistica` cabe
   en una línea, es SAME_SCOPE; si no, FOLLOW_UP con ficha.

5. **La población del laboratorio deja de depender del broker.** Hallazgo
   heredado, confirmado en la revisión de T-007 el 2026-09-18: los 10 activos
   marcados `no` en Trade Republic quedan fuera de `POLICY_OPERAR` desde PR 1,
   porque su estado de broker llega hasta `classify()` y cambia la acción. Eso
   hace que la población medida dependa de un metadato que se mueve con cada
   tanda de OA-03. T-007 corrigió el caso `unknown` (`ACCIONES_OPERABLES`);
   **aquí se cierra el caso `no`**: la población del laboratorio se decide con
   setup + ejecución, y el broker se mide como capa aparte, que es exactamente
   lo que esta ficha construye. Declarar en la evidencia cuántas señales entran
   y salen por este cambio, por activo.

6. **Lo que esta ficha NO hace, y conviene escribirlo:** no cambia
   `entry_max`, no introduce holgura de entrada, no propone una política nueva
   y no toca el score. La decisión que salga de aquí es de P4 (A-04) y se
   registrará entonces.

## Qué NO debe modificarse
`advisor/analysis/scoring.py`, la geometría de niveles, la fórmula de D-06,
`classify()`, el comportamiento por defecto del backtest actual (las cifras de
`POLICY_OPERAR` y `POLICY_TODAS` de hoy deben salir **idénticas** después del
cambio), y `docs/protocolo-investigacion.md` sin registrar la modificación
como decisión.

## Tests unitarios
- `test_senal_rechazada_por_entrada_queda_registrada`: serie sintética donde
  la apertura siguiente supera `entry_max` → 0 operaciones y **1** registro
  de pérdida con motivo `ABOVE_MAX_ENTRY`, con los números cerrados a mano.
- `test_contrafactual_entra_a_la_apertura_real_y_respeta_el_stop`: misma serie,
  disciplina `abrir_a_la_apertura` → 1 operación con entrada igual a la
  apertura, R calculado a mano en el test.
- `test_el_backtest_por_defecto_no_cambia_ni_una_operacion`: la simulación con
  los parámetros de hoy produce exactamente las mismas operaciones que antes
  (regresión sobre un caso fijo).
- `test_el_filtro_de_ejecucion_no_toca_el_score` (INV-03): el score de las
  señales perdidas es el mismo que el de la población total.
- `test_celda_con_muestra_insuficiente_se_declara_insuficiente`: no se agrega
  con otra para alcanzar el mínimo.
- `test_la_salida_declara_los_dos_vintages`.

## Verificación contra datos reales
```bash
.venv/bin/python -m advisor.main filtro-ejecucion --horizonte swing --vintage 071ddb2b
.venv/bin/python -m advisor.main filtro-ejecucion --horizonte medio  --vintage 071ddb2b
.venv/bin/python -m advisor.main backtest --horizonte swing --period 5y
```
Comprobar a mano: elegir **una** señal concreta de la tabla de
`PERDIDAS_POR_ENTRADA`, abrir la cosecha, leer el cierre de la barra de señal
y la apertura de la siguiente, recalcular `entry_max` y confirmar que la
apertura la supera; y que el backtest con parámetros de hoy da las mismas
operaciones y la misma expectancy que `antes.txt`, cifra a cifra.

## Medición del impacto
- nº de señales que el score aprueba, por banda y horizonte.
- nº y **porcentaje** perdidas por `ABOVE_MAX_ENTRY`, y por cada otro motivo.
- expectancy neta en R por bloque de `EJECUTADAS` vs `PERDIDAS_POR_ENTRADA`,
  con su intervalo.
- cuántas de las perdidas habrían terminado en objetivo y cuántas en stop.
- cambio en las cifras del backtest actual: **debe ser cero**, y se demuestra
  de forma **determinista** —misma serie fija, mismo código antes y después—,
  **no** comparando dos ejecuciones de `backtest --period Ny`. Corrección de la
  propia ficha, hecha en la revisión del 2026-09-18: el backtest en vivo
  descarga datos y no es reproducible ni consigo mismo (tres pasadas del mismo
  commit dan 891, 893 y 890 operaciones), así que ese criterio era
  inverificable por construcción. Ver T-015.

## Criterio de aceptación
- El comando existe, es reproducible y publica los dos vintages.
- Las dos capas se publican separadas y por banda de score.
- El backtest por defecto no cambia ni una operación.
- Las celdas con muestra insuficiente se declaran, no se agregan.
- `pytest`, `ruff`, `mypy` limpios; CI en verde.

## Criterio de rechazo
- Cualquier cambio del score histórico para incorporar el RR (INV-03).
- Una copia de `simulate_asset` para el contrafactual (INV-06).
- Conclusiones de política («hay que ampliar `entry_max`») dentro de esta
  ficha: eso es P4 y se decide con el gate correspondiente.
- Interpretar una diferencia sin publicar su incertidumbre y su muestra.

## Evidencia que debe quedar registrada
`evidence/<fecha>-T-009-filtro-ejecucion/` con README.md (comando, commit,
instante, conclusión y **el pre-registro copiado tal cual**), `antes.txt`,
`despues.txt`, la tabla por banda y población, el desglose por motivo, el
hash de las tablas de resultados y la señal concreta comprobada a mano.

## Commit esperado
Rama `feat/execution-filter-study`. Mensaje:
`feat(research): medir el filtro de ejecucion aparte del score, con poblacion contrafactual`

## Actualización documental requerida
`docs/roadmap.md`: fila de PR 5 (fase 14) a EN_REVISION y luego ACEPTADA.
`docs/decision-log.md`: entrada D-nn con el resultado publicado y la
constatación explícita de que **no** se cambia la política de entrada aquí.
`docs/protocolo-investigacion.md`: corregir de paso la cabecera que sigue
diciendo «acordado, sin implementar» (hallazgo abierto del roadmap), ya que
esta entrega toca `advisor/research/`.

## Handoff al siguiente agente
Implementación Codex 2026-09-18:

- `simulate_asset` conserva su comportamiento por defecto y añade
  instrumentación opcional de señales rechazadas (`ExecutionRejectedSignal`) y
  `entry_discipline="abrir_a_la_apertura"` para el contrafactual. No se copió
  el motor: el contrafactual reutiliza el mismo bucle y `_check_exit`.
- `filtro-ejecucion --horizonte <swing|medio> --vintage <id>` publica
  `data_vintage_id`, `universe_vintage_id`, `git_sha`, `config_hash`, tabla por
  banda/población, desglose por motivo y población broker-neutral para los
  activos `trade_republic="no"`.
- `capacidad-estadistica` imprime también cosecha y universo.
- `docs/protocolo-investigacion.md` deja de decir que P2 está sin implementar.

Evidencia:

- Directorio: `evidence/2026-09-18-T-009-filtro-ejecucion/`.
- Pre-registro copiado antes de medir en `README.md`.
- Línea base previa: `antes.txt` con 533 tests, `ruff`, `mypy` y backtest live.
- Verificación posterior: `despues.txt` con 540 tests, `ruff`, `mypy` y
  backtest live.
- Medición congelada: `filtro_swing.txt`, `filtro_medio.txt`,
  `tabla_banda_poblacion_swing.md`, `tabla_banda_poblacion_medio.md`,
  `desglose_motivo_swing.md`, `desglose_motivo_medio.md`,
  `hashes_tablas.txt`.
- Defecto inyectado: `defecto_inyectado_registro_rechazo.txt` demuestra que el
  test de registro falla si la señal rechazada vuelve a perderse.
- Verificación manual: `AAPL|swing|2023-12-13T05:00:00Z`, cierre 197,960007,
  apertura 198,020004, `entry_max=min(200,107150, 197,960007)=197,960007`;
  la apertura supera `entry_max` y el RR a la apertura cae a 1,474075.

Medición publicada:

- Swing: 994 ejecutadas, 1189 perdidas por ejecución, 879 contrafactuales
  simulables. Motivos perdidos: `ABOVE_MAX_ENTRY` 1146/1189, `INVALID_STOP`
  31/1189, `INVALID_TARGET` 12/1189, `RR_TOO_LOW` 0/1189.
- Medio: 792 ejecutadas, 962 perdidas por ejecución, 716 contrafactuales
  simulables. Motivos perdidos: `ABOVE_MAX_ENTRY` 926/962, `INVALID_STOP`
  25/962, `INVALID_TARGET` 11/962, `RR_TOO_LOW` 0/962.
- Broker neutral, `trade_republic="no"`: swing añade 85 señales de laboratorio
  (por activo: 14, 11, 16, 11, 10, 4, 9, 6, 4, 10); medio añade 74 señales
  (14, 3, 16, 3, 8, 3, 9, 6, 4, 8).

Invariantes ejercitadas:

- INV-03: `test_el_filtro_de_ejecucion_no_toca_el_score`.
- INV-04: `test_laboratorio_broker_neutral_incluye_no_sin_cambiar_default`.
- INV-06: el contrafactual usa `simulate_asset`; no hay copia del motor.
- Muestra mínima: `test_celda_con_muestra_insuficiente_se_declara_insuficiente`.
- Vintages en salida: `test_la_salida_declara_los_dos_vintages`.

Bloqueo:

- El criterio “backtest por defecto no cambia ni una operación contra
  `antes.txt`” no queda satisfecho en la evidencia live. `antes.txt` mide 891
  operaciones y expectancy 0,21 R; `despues.txt` mide 893 y 0,20 R. Una
  repetición posterior inmediata (`backtest_repetido_post.txt`) vuelve a mover
  cifras (890 operaciones), por lo que el comando live no es estable en esta
  ventana. El código por defecto queda cubierto por regresión sintética, pero
  la aceptación pedía comparación cifra a cifra contra `antes.txt`: queda
  BLOQUEADA hasta repetir esa comparación sobre entrada congelada o estabilizar
  el proveedor/ventana.

Hallazgos:

- BLOCKER: la verificación live del backtest por defecto no permite certificar
  cambio cero contra `antes.txt`; no se corrige aquí porque implicaría cambiar
  el procedimiento de aceptación o congelar la entrada del backtest.
- OBSERVATION: con el orden actual de `evaluate_trade_at_entry`, D-29 mide
  `ABOVE_MAX_ENTRY` 1146 (swing) / 926 (medio) y `RR_TOO_LOW` 0 / 0 en las
  señales perdidas. No se decide la etiqueta.

Decisiones pendientes:

- DECISIÓN PENDIENTE D-29: mantener `ABOVE_MAX_ENTRY` como etiqueta prioritaria
  cuando `entry_price > entry_max`, o cambiar a `RR_TOO_LOW` cuando el
  incumplimiento de `entry_max` viene del límite por RR. La medición de T-009
  solo aporta poblaciones; no decide.
Resumen de verificación final:

- `python -m pytest -q`: 540 passed.
- `ruff check .`: limpio.
- `mypy advisor`: limpio.


---

## Revisión independiente — 2026-09-18 — VEREDICTO: CORREGIR → corregido

Evidencia completa en `evidence/2026-09-18-T-009-revision/README.md`.

**El bloqueo era correcto y el criterio era mío.** Codex se negó a certificar
«cero cambios en el backtest» porque las pasadas no coincidían, e hizo bien en
no maquillarlo. La causa no era su cambio: `backtest --period 5y` descarga
datos en vivo y **no es reproducible ni consigo mismo** —tres pasadas del mismo
commit dan 891, 893 y 890 operaciones, y el ruido (−3) es mayor que el efecto
atribuido al cambio (+2)—. El criterio que escribí era inverificable por
construcción. Sustituido por una comparación determinista: el código de `main` y
el del árbol sobre una serie sintética con semilla fija, dos horizontes y dos
políticas, **idénticos byte a byte** (134 operaciones). Salvedad declarada: esa
serie no produce señales `COMPRAR`, así que la ruta `POLICY_OPERAR` no queda
ejercitada.

**Defecto corregido: se publicaba un centinela como intervalo.** El tramo `80+`
salía con `IC95 [0.0000, 1.0000]` y estado `OK`. Eso no es un intervalo: es lo
que `bootstrap_block_mean_interval` devuelve con menos de dos bloques, y en
unidades de R se lee como una afirmación fuerte y falsa. Ahora dice
`SIN INTERVALO` y `N/D (menos de 2 bloques)`. Medición regenerada y hashes
rehechos. Test de regresión que falla contra el código sin corregir.

**D-29 queda respondida con datos:** `RR_TOO_LOW` es **0 de 2.151** señales
perdidas, y `ABOVE_MAX_ENTRY` el 96 %. Uno de los dos códigos está muerto. La
decisión se toma en T-010 con estos números delante; la revisión no la toma.

**Dos hallazgos con ficha propia:** T-015 (el backtest en vivo no es
reproducible, y eso afecta a la línea base de la línea 0) y T-016 (el centinela
también lo consume `capacity.py`, que es quien emite el veredicto de P2.5, del
que depende GATE P2).

**Lo que la entrega hace bien:** INV-06 respetada —el contrafactual reutiliza
`simulate_asset`, no lo copia—; el defecto inyectado es esta vez una ejecución
real guardada, corrigiendo el reproche de T-008; el pre-registro está copiado
antes de medir; y no decidió D-29 pese a tener los números, porque la ficha se
lo prohibía.

**Y el resultado de fondo, que es para lo que existía la ficha:** en la banda
70-80, lo ejecutado rinde 0,2111 R por bloque [0,0414, 0,4002] y lo rechazado
0,1221 R [−0,0008, 0,2309]. El filtro **parece proteger**, con intervalos que se
solapan: compatible con que ayude, no prueba de que ayude. Las señales
rechazadas aciertan más veces (56 %) y ganan menos por acierto (payoff 1,01
frente a 1,77), que es exactamente lo que produce perseguir un hueco al alza.
