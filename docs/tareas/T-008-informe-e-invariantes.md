# T-008 — Informe honesto e invariantes de integración (PR 5, fases 12–13)

Estado: PENDIENTE
Agente: Opus (ficha) → Codex (implementación) → Opus (revisión)
Línea / fase: L0 PR 5, fases 12 y 13 de `docs/plan-ejecucion.md`
Gate al que contribuye: GATE L0 (requisito 5)

## Objetivo
La ficha de una oportunidad deja de mezclar cuatro capas en un solo número y
en una sola etiqueta: publica por separado el score técnico, el estado del
setup, el estado de ejecución y la calidad del dato, con **las dos entradas
máximas visibles** —la técnica y la que impone el RR mínimo— y el motivo de
espera cuando lo hay. Y siete invariantes de integración pasan a ser tests que
fallan si alguna capa vuelve a contaminar a otra.

## Por qué existe
La línea 0 ha separado las capas por dentro (PR 1 ejecución, PR 3 calidad,
PR 4 estado de mercado y broker) pero **el informe sigue contándolas como
antes**. Tres consecuencias medibles hoy en `advisor/report/formatter.py`:

1. `entry_max` se imprime como un único número (línea 185 aprox.,
   «Entrada máxima aceptable»), cuando en `compute_levels` es
   `min(entry_max_tecnica, entry_max_rr)`. El usuario no puede saber cuál de
   las dos manda, que es justo lo que D-06 convirtió en la política de
   entrada.
2. `_conclusion` afirma «Principal riesgo del mercado: <reason>» usando
   `result.context.reason`, que es la **explicación del régimen**, no un
   riesgo identificado. Y «Liquidez recomendada: N%» es la resta de tres
   posiciones, no una política de asignación a efectivo: el sistema no tiene
   modelo de liquidez y el informe habla como si lo tuviera.
3. La fase 13 lista siete invariantes que hoy **no** tienen test. Sin ellas,
   cualquier entrega futura puede volver a acoplar score y ejecución sin que
   la suite se entere.

## Dependencias previas
T-005 ACEPTADA (códigos de descarte y `DataQuality` por dimensiones; el
agrupado de descartados por código ya existe en `_group_discarded_by_code`) y
**T-007 ACEPTADA**, porque esta ficha da por hecho que «Último cierre» y el
estado de plaza ya existen: T-008 **no** vuelve a tocar esa línea.
Decisiones que aplica: D-06 (`entry_max` manda), D-04 (`unknown` no degrada),
D-05 (`INCOMPLETO` veta la apertura sin tocar el score).

## Archivos probables
No asumir que sean exactos: verificar primero con búsqueda de símbolos.
- `advisor/report/formatter.py` — `format_opportunity` (ficha), `_conclusion`
  (cierre), `_opportunity_row`/`_opportunity_table` (tabla resumen),
  `_group_discarded_by_code` (ya agrupa; comprobar que cubre los siete grupos
  de la fase 12).
- `advisor/analysis/levels.py` — `compute_levels` calcula `entry_max_tecnica`
  y `entry_max_rr` como **locales** y solo publica el mínimo: hay que
  exponerlos en `Levels`.
- `advisor/analysis/execution.py` — `ExecutionEvaluation` ya trae
  `entry_price`, `rr`, `reason`: la ficha los imprime, no los recalcula.
- `advisor/analysis/market_context.py` — `MarketContext.label` es el régimen
  (`RISK_ON`/`CAUTELA`/`RISK_OFF`) y `.reason` su explicación.
- `tests/test_report.py`, `tests/test_analysis.py`.

## Invariantes que no pueden romperse
INV-03 (calidad, broker y ejecución **no** tocan `score.value`), INV-04 (señal
y ejecutabilidad separadas), INV-11 (no llamar «precio actual» a un cierre),
INV-16 (lo desconocido se declara desconocido), INV-17 (ninguna columna
persistida nueva sin migración: si `entry_max_rr`/`entry_max_tecnica` llegan a
persistirse, migración con `PRAGMA user_version`; si solo se muestran, decirlo
en la ficha).

## Implementación requerida

1. **Las dos entradas máximas, visibles y nombradas.** Añadir a `Levels` los
   campos `entry_max_tecnica` y `entry_max_rr` (hoy locales de
   `compute_levels`), sin cambiar `entry_max`, que sigue siendo su mínimo y
   sigue mandando. La ficha imprime las tres y **dice cuál manda**:

   ```text
   Entrada ideal: 55,76–56,11 €
   Entrada máxima por técnica (ATR): 57,42 €
   Entrada máxima por RR mínimo (1,5): 56,11 €
   Entrada máxima aplicada: 56,11 €  ← manda el RR mínimo
   ```

   `entry_max_rr` puede ser `None` cuando la geometría no admite ningún precio
   con el RR mínimo: entonces se declara así, nunca como un número.

2. **Bloque de estados en cabecera de ficha**, con las cuatro capas
   separadas y en este orden:

   ```text
   Score: 74/100 (B)
   Setup: VÁLIDO | INVÁLIDO  (+ motivo)
   Ejecución: EJECUTABLE | ESPERAR  (+ código: ABOVE_MAX_ENTRY, RR_TOO_LOW…)
   Dato: OK | INCOMPLETO | DEGRADADO  (+ código)
   Broker: AVAILABLE | UNAVAILABLE | UNVERIFIED
   ```

   Los valores salen de `opportunity.score`, `setup_radar`/`setup_accion`,
   `execution.executable`/`execution.reason`, `data_quality` y
   `asset.availability_label`. **Ninguno se recalcula en el formateador**: si
   un dato no está, se imprime desconocido (INV-16).

3. **RR al precio evaluado, no solo al de referencia.** Imprimir
   `RR a <precio evaluado>: 1,49` usando `execution.rr`, y el motivo de espera
   cuando `execution.executable` es falso, con la frase operativa de la fase
   12: «No perseguir precio. Si cotiza > <entry_max> €, la operación deja de
   cumplir el RR mínimo configurado». La precisión interna es la del cálculo:
   **no** comparar los números ya redondeados, que produce falsos
   incumplimientos (un RR de 1,495 no puede imprimirse «1,5» y a la vez
   declararse insuficiente).

4. **Régimen, dicho como régimen.** En `_conclusion`, sustituir
   «Principal riesgo del mercado: <reason>» por
   `Régimen: <label> — <reason>`. No inventar un riesgo principal: el sistema
   no lo calcula.

5. **Liquidez, dicha como exposición.** Sustituir «Liquidez recomendada: N%»
   por `Capital asignado a señales actuales: X% · Capital no asignado: Y%`,
   con la misma aritmética de hoy (suma de las tres mejores por señal en su
   dimensionamiento máximo) y una frase que diga que **no** es una política de
   asignación a efectivo. Añadir la aclaración del hallazgo abierto del
   roadmap: cuando manda `max_position_pct` en vez de `risk_per_trade_pct`, el
   riesgo efectivo es menor que el configurado; el informe debe decir cuál de
   los dos topes ha mandado (`sizing` ya guarda la restricción dominante desde
   la fase 3).

6. **Calidad: resumen arriba, detalle fuera del informe principal.** La ficha
   imprime el resumen (frescura reciente + calidad histórica + código). El
   listado largo de fechas ausentes deja de salir en la ficha: se conserva en
   el informe de diagnóstico (`frescura-datos`) y en la base. Límite duro: la
   ficha no imprime más de **una** línea de fechas por dimensión; el resto se
   cuenta («y 12 sesiones más»). `_dates_label_limited` ya existe: usarlo.

7. **Descartados agrupados por los siete grupos de la fase 12**: score
   insuficiente · RR/ejecución · datos · tendencia · sobreextensión · broker ·
   otros. `_group_discarded_by_code` ya agrupa por código: mapear los códigos
   reales a esos siete grupos, y que «otros» esté **vacío** en la pasada real
   o el mapeo está incompleto. Declarar el recuento por grupo en la evidencia.

## Las siete invariantes de integración (fase 13)
Cada una es un test, con el nombre entre paréntesis, y **cada una debe fallar
contra el código actual o contra un defecto inyectado a propósito**; si pasa
igual sin el cambio, no prueba nada y hay que rehacerla:

1. `action == OPERAR` implica `setup_valid` y `execution_valid` y
   `rr >= min_rr` y `entry <= entry_max` y, si la política lo exige,
   `broker_status == AVAILABLE`
   (`test_operar_implica_las_cuatro_capas_validas`).
2. `entry_max` nunca produce un RR inferior al configurado
   (`test_entry_max_nunca_incumple_min_rr`), sobre los 107 del universo real.
3. El benchmark nunca proporciona el calendario de `missing_sessions`
   (`test_benchmark_no_es_calendario`) — INV-05.
4. Un festivo de la plaza no aparece como sesión ausente
   (`test_festivo_no_es_sesion_ausente`).
5. Una sesión de un benchmark extranjero no obliga a que el activo local tenga
   vela (`test_sesion_de_benchmark_extranjero_no_exige_vela`): el caso real son
   los ETF alemanes sobre índices de EE. UU., más `AZN` y `TSM`.
6. El informe no dice «Precio actual» cuando solo hay último cierre
   (`test_informe_no_dice_precio_actual_con_plaza_cerrada`) — INV-11; T-007 lo
   implementa, T-008 lo blinda.
7. Cambiar `entry` recalcula RR, `risk_pct`, `potential_pct`, tamaño de
   posición, capital en riesgo y estado de ejecución
   (`test_cambiar_entry_recalcula_toda_la_cadena`), con **números cerrados
   calculados a mano** sobre el caso `EXH1.DE` del plan: referencia 56,11,
   stop 54,71, target2 58,20, `min_rr` 1,5 → `entry_max_rr` 56,11;
   55,76 ejecutable · 56,00 ejecutable · 56,11 límite · 56,63 `RR_TOO_LOW`.

## Qué NO debe modificarse
`advisor/analysis/scoring.py` (ni pesos ni umbrales), la geometría de stop y
objetivo, la fórmula de `entry_max` de D-06, la clasificación de `classify()`,
los umbrales de calidad de T-005, y el estado de plaza/broker de T-007: esta
ficha **presenta** lo que otras capas ya calculan.

## Tests unitarios
Además de las siete invariantes:
- `test_ficha_publica_las_dos_entradas_maximas_y_cual_manda`: con
  `entry_max_tecnica` 57,42 y `entry_max_rr` 56,11, la ficha contiene ambos y
  declara que manda el RR.
- `test_entry_max_rr_none_se_declara_desconocido` (INV-16).
- `test_regimen_se_nombra_regimen_y_no_riesgo_principal`.
- `test_liquidez_se_nombra_capital_no_asignado`.
- `test_sizing_declara_el_tope_dominante`: caso `risk_per_trade_pct: 0.5` con
  `max_position_pct: 10` → el informe dice que manda el tope de posición.
- `test_ficha_no_imprime_mas_de_una_linea_de_fechas_por_dimension`.
- `test_descartados_no_caen_en_otros_con_el_universo_real`.

## Verificación contra datos reales
```bash
.venv/bin/python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar
.venv/bin/python -m advisor.main analizar --horizonte medio --sin-ia --sin-guardar
```
Comprobar a mano: tomar el activo con mejor score de la pasada, recalcular su
RR al precio evaluado con calculadora —`(target2 − entry) / (entry − stop)`— y
comprobar que coincide con el número impreso hasta el segundo decimal, y que
la entrada máxima aplicada es efectivamente el mínimo de las dos publicadas.

## Medición del impacto
- nº activos cuya **acción** cambia: debe ser **0**. Esta ficha cambia cómo se
  cuenta, no qué se decide. Si alguno cambia, es un defecto o una decisión.
- nº activos cuya ficha cambia de texto: previsiblemente los 107; declararlo.
- recuento de descartados por cada uno de los siete grupos, antes y después.
- diferencia de `entry_max_tecnica` vs `entry_max_rr`: en cuántos de los 107
  manda cada uno. Es el número que da sentido a D-06 y no está medido.

## Criterio de aceptación
- Las cuatro capas aparecen separadas en la ficha, con su código cuando lo hay.
- Las dos entradas máximas están publicadas y se declara cuál manda.
- Las siete invariantes de la fase 13 son tests y cada una falla contra un
  defecto inyectado.
- Ningún activo cambia de acción respecto a la línea base.
- `pytest`, `ruff`, `mypy` limpios; CI en verde.

## Criterio de rechazo
- Cualquier recálculo de score, RR, niveles o calidad dentro de
  `formatter.py`: el formateador presenta, no calcula.
- Una invariante de la fase 13 que pase igual con el defecto inyectado.
- Comparar números ya redondeados para decidir si se cumple el RR.
- Un grupo «otros» no vacío en la pasada real sin explicación.

## Evidencia que debe quedar registrada
`evidence/<fecha>-T-008-informe/` con README.md (comando, commit, instante,
conclusión), `antes.txt`, `despues.txt`, la ficha completa de un mismo activo
antes y después, la tabla de acciones antes/después (que debe ser idéntica), el
recuento por los siete grupos de descarte y el recuento de cuál de las dos
entradas máximas manda en cada uno de los 107.

## Commit esperado
Rama `refactor/report-states`. Mensaje:
`refactor(report): separar score, setup, ejecucion y dato, y publicar las dos entradas maximas`

## Actualización documental requerida
`docs/roadmap.md`: fila de PR 5 (fases 12–13) a EN_REVISION y luego ACEPTADA.
`docs/decision-log.md`: entrada D-nn si el mapeo de códigos a los siete grupos
obliga a decidir dónde cae alguno.

## Handoff al siguiente agente
Pendiente de escribir al terminar.
