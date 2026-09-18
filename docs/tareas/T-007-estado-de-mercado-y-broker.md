# T-007 — Estado de mercado, precio ejecutable y estado de broker (PR 4, fases 9–11)

Estado: EN_REVISION
Agente: Opus (ficha) → Codex (implementación) → Opus (revisión)
Línea / fase: L0 PR 4, fases 9, 10 y 11 de `docs/plan-ejecucion.md`
Gate al que contribuye: GATE L0

## Objetivo
El informe deja de llamar «precio actual» al cierre de la sesión anterior:
declara el estado de la plaza, nombra el precio por lo que es, y la capa de
ejecución sabe reevaluar un setup contra un precio posterior sin recalcular la
señal.

## Por qué existe
Tres defectos distintos que comparten causa —confundir el dato de referencia con
el precio al que se puede operar— y que el plan separó en las fases 9, 10 y 11.

La fase 9 sale de una observación directa: a las 06:37 UTC el informe imprimía
`**Precio actual:** 56,11 €` para `EXH1.DE` cuando Xetra llevaba catorce horas
cerrada y ese número era el cierre del día anterior. La 10 es la consecuencia
operativa: D-06 midió que con la geometría por defecto `entry_max_rr = price`
exactamente, así que **toda apertura al alza es `ABOVE_MAX_ENTRY`** y hoy no hay
forma de volver a evaluar el mismo setup cuando el precio baja dentro del rango.
La 11 cierra el estado de broker, que ya existe en `execution.py` pero no tiene
su metadato en `universe.yaml`.

## Dependencias previas
T-005 ACEPTADA (códigos de descarte y ejecución separados) y T-006 ACEPTADA
(identidad de instrumentos: esta ficha escribe `isin` de `EXH1.DE`, y sin los
campos `isin_verified_at`/`isin_source` de T-006 ese ISIN no podría cargarse).
Decisiones que aplica: D-04 (`unknown` no degrada la señal), D-06 (`entry_max`
manda en la entrada), D-21 (retraso veta la apertura).

## Archivos probables
No asumir que sean exactos: verificar primero con búsqueda de símbolos.
- `advisor/data/sessions.py` — `MARKET_SESSIONS` ya tiene zona horaria y
  `close_time` por plaza; **no existe hora de apertura**, y hace falta para
  distinguir `PRE_OPEN` de `CLOSED`.
- `advisor/analysis/execution.py` — `evaluate_trade_at_entry`, `ABOVE_MAX_ENTRY`,
  `BROKER_UNVERIFIED`, `BROKER_UNAVAILABLE` ya existen: la fase 10 los reutiliza,
  no los reescribe.
- `advisor/report/formatter.py:132` — la línea `**Precio actual:**`.
- `advisor/analysis/opportunity.py:140` — `broker_execution_label`.
- `universe.yaml:200` — `EXH1.DE`, hoy con `isin: null` y `requires_isin: true`.
- `tests/test_sessions.py`, `tests/test_report.py`, `tests/test_analysis.py`.

## Invariantes que no pueden romperse
INV-03 (el estado de mercado y el del broker **no** tocan `score.value`),
INV-04 (señal y ejecutabilidad separadas), INV-16 (lo desconocido se declara
desconocido: `UNVERIFIED` nunca se convierte en `UNAVAILABLE`), INV-05 (la plaza
sale de `primary_market`, nunca del benchmark).

Revisión al entregar:
- INV-03: ejercitada por `test_accion_verificar_broker_con_universo_real`; el
  score queda en 90,0 al pasar a `VERIFICAR_BROKER`. En salida real `AMD`
  conserva score 74 antes/después.
- INV-04: ejercitada por la separación `Señal: OPERAR` /
  `Acción: VERIFICAR_BROKER` en test con `trade_republic="unknown"`.
- INV-16: ejercitada por `test_unverified_no_se_convierte_en_unavailable`; el
  motivo queda `BROKER_UNVERIFIED`, ejecutable, y no se convierte en
  `BROKER_UNAVAILABLE`.
- INV-05: ejercitada indirectamente en `format_opportunity`, que usa
  `mercado_para_simbolo(asset, asset.data_symbol(reference))` y no el benchmark.

## Implementación requerida

1. **Estado de plaza, derivado del calendario y no hardcodeado.**
   `market_state(market, reference) -> PRE_OPEN | OPEN | CLOSED`, en
   `advisor/data/sessions.py`, junto a `market_session`.

   **No añadas `open_time` a `MARKET_SESSIONS`.** Medido el 2026-09-17:
   `exchange_calendars` ya da apertura y cierre por MIC, y sus 14 cierres
   coinciden **exactamente** con los `close_time` hardcodeados de hoy. Copiar
   los horarios de apertura crearía una segunda fuente de verdad para un dato
   que la librería ya mantiene, que es justo lo que se rechazó en T-006 para
   `exchange_calendar`/`exchange_timezone` en el YAML (INV-06).

   Usa `cal.session_open(sesion)` y `cal.session_close(sesion)` para **la sesión
   concreta**, no el horario regular. Cripto (`CRYPTO_24_7`, sin calendario en
   la librería) es siempre `OPEN` y se resuelve antes de consultar. Una plaza
   sin calendario declarado devuelve `None`, no un estado inventado.

2. **Defecto que esto corrige, medido y no supuesto: el cierre anticipado.**
   `trim_unclosed_bar` compara contra el `close_time` **regular**, así que en los
   días de media sesión descarta una barra que ya está cerrada. Contados con
   `exchange_calendars==4.13.2` entre 2025-11-01 y 2026-12-31:

   ```
   XETRA  cierre regular 17:30 → 2 sesiones cierran a las 14:00 (30/12/2025 y 30/12/2026)
   NYSE   cierre regular 16:00 → 4 sesiones cierran a las 13:00 (Acción de Gracias y Nochebuena)
   PAR    cierre regular 17:30 → 4 sesiones cierran a las 14:05 (Nochebuena y Nochevieja)
   ```

   Consecuencia operativa concreta: el 24/12/2026 NYSE cierra a las 13:00 y el
   código espera hasta las 16:20; la pasada de las 21:00 hora de Londres son las
   15:00 en Nueva York, así que **recorta una barra cerrada** y el activo se
   analiza con una sesión menos sin que nada lo declare. `trim_unclosed_bar`
   debe tomar el cierre de la sesión concreta. Añadir un test con esas fechas
   reales.

   **Cuándo muerde, que es lo que decide la prioridad.** El bot nació en agosto
   de 2026, así que este defecto **todavía no ha afectado a ninguna pasada**. La
   primera fecha en que lo hará es el **2026-11-27** (Acción de Gracias: NYSE y
   NASDAQ cierran a las 13:00), y luego el 24, el 30 y el 31 de diciembre, que
   afectan a ocho plazas entre las dos fechas:

   ```
   2026-11-27  NASDAQ, NYSE          cierran 13:00 (el código espera 16:00)
   2026-12-24  AMS, HKG, LSE, MCE, NASDAQ, NYSE, PAR
   2026-12-30  XETRA                 cierra 14:00 (el código espera 17:30)
   2026-12-31  AMS, HKG, LSE, MCE, PAR
   ```

   Es decir: hay margen hasta finales de noviembre, pero **no debe pasar de
   ahí**, porque en Nochebuena afectaría a la mitad del universo a la vez.
3. **El informe nombra el precio por lo que es.** Sustituir `**Precio actual:**`
   por `**Último cierre:** <precio> · Sesión: <fecha> · Mercado: <estado>` cuando
   el estado sea `PRE_OPEN` o `CLOSED`, y conservar «precio actual» solo con la
   plaza `OPEN`. El valor numérico no cambia: cambia cómo se nombra.
4. **Reevaluación contra un precio posterior.** `evaluate_trade_at_entry` ya
   acepta `entry_price`; añadir el camino que la llama con un precio distinto
   del de la señal, sin recalcular `score` ni `levels`, y devolver
   `execution_valid` con su `reason`. Un `market_price > entry_max` da
   `ABOVE_MAX_ENTRY`; uno dentro del rango con RR suficiente vuelve a ser
   ejecutable. **No** implementar broker en tiempo real ni una segunda pasada
   automática: esta ficha deja la capa lista, no la programa.
5. **Estado de broker en el informe.** La cadena de acción queda:
   setup inválido → `NO_OPERAR`; ejecución inválida → `ESPERAR`; broker
   `UNAVAILABLE` → `NO_OPERAR`; broker `UNVERIFIED` → `VERIFICAR_BROKER`; resto
   → `OPERAR`. Hoy `UNVERIFIED` produce `COMPRAR` con una nota al lado, y el
   plan pide que sea una acción propia. **Ojo:** los 107 analizables están en
   `unknown`, así que este cambio convierte *todas* las recomendaciones actuales
   en `VERIFICAR_BROKER`. Medir el efecto sobre el informe antes de darlo por
   bueno y declararlo en la evidencia.
6. **ISIN de `EXH1.DE`:** `DE000A0H08M3`, con `isin_source` y
   `isin_verified_at` obligatorios por T-006. **Verificar contra Deutsche Börse
   antes de escribirlo**; si no se puede confirmar con fuente primaria, dejarlo
   en `null` y decirlo. Un ISIN que valida el dígito de control pero es falso es
   peor que ninguno (§8 de `docs/pendientes.md`).

## Qué NO debe modificarse
`advisor/analysis/scoring.py` (ni pesos ni umbrales), la geometría de stop y
objetivo, `entry_max` y su fórmula de D-06, el resto de `trade_republic` de los
otros 106 activos, y la lista de analizables.

## Tests unitarios
- `test_market_state_pre_open_open_y_closed_en_xetra`: con `2026-09-17` y las
  08:00, 12:00 y 19:00 de `Europe/Berlin` → `PRE_OPEN`, `OPEN`, `CLOSED`.
- `test_media_sesion_no_recorta_una_barra_ya_cerrada`: NYSE el `2026-12-24`, que
  cierra a las 13:00; a las 15:00 de Nueva York la barra del día **no** se
  recorta. Falla contra el código actual, que espera a las 16:20.
- `test_media_sesion_en_xetra_el_30_de_diciembre`: cierre a las 14:00, misma
  comprobación.
- `test_market_state_en_fin_de_semana_es_closed`: sábado `2026-09-19` 12:00.
- `test_cripto_siempre_open`.
- `test_plaza_sin_horario_declarado_no_inventa_estado`: devuelve `None`.
- `test_reevaluacion_por_encima_de_entry_max_da_above_max_entry`: `entry_max`
  56,11, precio 56,70 → no ejecutable, `ABOVE_MAX_ENTRY`.
- `test_reevaluacion_dentro_del_rango_vuelve_a_ser_ejecutable`: mismo setup,
  precio 55,95 → ejecutable, RR ≥ 1,5 calculado a mano en el test.
- `test_unverified_no_se_convierte_en_unavailable` (INV-16).

## Tests de integración
- `test_informe_no_llama_precio_actual_al_cierre_anterior`: informe con la plaza
  `CLOSED` → contiene «Último cierre» y **no** contiene «Precio actual».
- `test_accion_verificar_broker_con_universo_real`: fixture con
  `trade_republic="unknown"` —como los 107 reales, no como `asset_eur`— y
  comprobación de que la acción es `VERIFICAR_BROKER` y el score no cambia
  (INV-03).

## Verificación contra datos reales
```bash
.venv/bin/python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar
.venv/bin/python -m advisor.main frescura-datos --grupos europa
```
Comprobar a mano: con la pasada lanzada antes de las 09:00 hora de Berlín, los
activos de Xetra declaran `PRE_OPEN` y su precio aparece como último cierre con
la fecha de la sesión anterior; y que el número no ha cambiado respecto a la
pasada anterior, solo su etiqueta.

## Medición del impacto
- nº activos afectados: previsiblemente los 107 cambian de acción a
  `VERIFICAR_BROKER`; contar y declarar.
- nº señales afectadas: 0 en puntuación (INV-03).
- cambio en resultados relevantes: ninguno en el backtest, que no pasa por el
  informe. Confirmarlo ejecutándolo.

Resultado medido el 2026-09-18:
- Universo real vigente: 107 analizables; `trade_republic`: 95 `yes`, 10 `no`,
  2 `unknown`. La previsión de 107 `unknown` ya no aplica tras OA-03/D-26.
- Acciones en la salida real: `AMD` sigue `COMPRAR` porque está verificado en
  broker; no aparece `VERIFICAR_BROKER` porque los 2 `unknown` reales no
  alcanzan setup operativo en esta pasada.
- Cambio de acción/radar atribuible al código: `9984.T` pasa de radar con
  `BROKER_UNAVAILABLE` a descartado por `BROKER_UNAVAILABLE` (broker `no` ya no
  queda como espera ejecutable).
- Señales afectadas en puntuación: 0. `AMD` conserva score 74; el test de
  broker conserva score 90,0.
- Etiqueta de precio: `AMD` cambia de `Precio actual: 545,09 USD` a
  `Último cierre: 545,09 USD · Sesión: 2026-09-17 · Mercado: PRE_OPEN`; el
  número nativo no cambia.
- Calidad agregada: OK 57 → 60, INCOMPLETO 31 → 28, DEGRADADO 19 → 19 por
  drift de datos reales entre pasadas (cripto actualizó barra durante la
  verificación), no por cambio de scoring.
- Backtest: ejecutado `advisor.main backtest --horizonte swing --period 5y`;
  sigue generando resultados y no pasa por el formatter del informe.

## Criterio de aceptación
- `market_state` con las 15 plazas declaradas y fuente de cada horario.
- El informe no contiene «Precio actual» con la plaza cerrada.
- La reevaluación devuelve `ABOVE_MAX_ENTRY` y ejecutable según el precio, sin
  tocar el score.
- `pytest`, `ruff`, `mypy` limpios; CI en verde.

## Criterio de rechazo
- Horarios de apertura o cierre copiados a mano en `MARKET_SESSIONS` en vez de
  derivados de `exchange_calendars` (segunda fuente de verdad, INV-06).
- `UNVERIFIED` tratado como `UNAVAILABLE` en cualquier camino.
- El ISIN de `EXH1.DE` escrito sin confirmación de fuente primaria.
- Cualquier cambio en `scoring.py`.

## Evidencia que debe quedar registrada
`evidence/<fecha>-T-007-estado-de-mercado/` con README.md (comando, commit,
instante, conclusión), `antes.txt`, `despues.txt`, la tabla de acciones antes y
después, y el recuento de sesiones con cierre anticipado por plaza que justifica
el cambio de `trim_unclosed_bar`.

Evidencia registrada en `evidence/2026-09-18-T-007-estado-de-mercado/`:
`README.md`, `antes.txt`, `despues.txt`, `acciones.md`, `backtest.txt`.

## Commit esperado
Rama `feat/market-state-and-broker`. Mensaje:
`feat(execution): estado de plaza, precio ejecutable y estado de broker en el informe`

## Actualización documental requerida
`docs/roadmap.md`: fila de PR 4 a EN_REVISION y luego ACEPTADA.
`docs/decision-log.md`: entrada D-nn con la consecuencia de que los 107 pasen a
`VERIFICAR_BROKER`, y otra con el cambio de cierre regular a cierre de la sesión
concreta en `trim_unclosed_bar`.

Actualizado:
- `docs/roadmap.md`: PR 4 a `EN_REVISION`.
- `docs/decision-log.md`: D-27 (`BROKER_UNVERIFIED` pasa a acción propia) y
  D-28 (`trim_unclosed_bar` usa cierre de la sesión concreta).

## Handoff al siguiente agente
Estado: ACEPTADA tras revisión independiente.

Implementado:
- `market_state(market, reference)` en `advisor/data/sessions.py`, con cripto
  siempre `OPEN`, plazas sin calendario como `None` y Xetra/NASDAQ/etc. vía
  `exchange_calendars`.
- `trim_unclosed_bar` usa `session_close(sesion)` de la sesión concreta; tests
  cubren NYSE 2026-12-24 13:00 y XETRA 2026-12-30 14:00.
- El informe etiqueta `Precio actual` solo si la plaza está `OPEN`; con
  `PRE_OPEN`/`CLOSED` imprime `Último cierre`, sesión y estado.
- Añadido `reevaluate_execution_at_price(...)` para reevaluar entrada contra un
  precio posterior sin recalcular score ni niveles.
- `BROKER_UNVERIFIED` produce acción `VERIFICAR_BROKER`; `BROKER_UNAVAILABLE`
  deja de quedar como espera ejecutable.

Verificado:
- Baseline antes de editar: 502 tests, `ruff`, `mypy` limpios; salida real
  guardada en `antes.txt`.
- Posterior: 513 tests, `ruff check .`, `mypy advisor` limpios.
- Salida real guardada en `despues.txt`; backtest de control en `backtest.txt`.
- Comprobación manual: `AMD` mantiene 545,09 USD y cambia solo etiqueta
  `Precio actual` → `Último cierre · Mercado: PRE_OPEN`; cálculo de RR de
  reevaluación escrito en `README.md`.

Pendiente:
- No se escribió el ISIN de `EXH1.DE` en `universe.yaml`; lo verifica el
  supervisor contra fuente primaria en paralelo, según el contexto operativo de
  la sesión.
- Revisión independiente obligatoria por tocar calendarios y clasificación.

Hallazgos clasificados:
- OBSERVATION: la ficha esperaba 107 `unknown`, pero el universo vigente tras
  OA-03/D-26 tiene 95 `yes`, 10 `no` y 2 `unknown`; por eso la salida real no
  convierte 107 recomendaciones a `VERIFICAR_BROKER`.
- OBSERVATION: la pasada posterior se ejecutó a las 09:51 de Berlín, no antes
  de las 09:00; la comprobación real de estado de mercado fue `AMD`/NASDAQ
  `PRE_OPEN`, y Xetra `PRE_OPEN` queda cubierto por test unitario.
- OBSERVATION: los conteos de calidad cambiaron 57/31/19 → 60/28/19 por drift
  de datos reales entre pasadas (cripto actualizó barra), no por la lógica de
  esta tarea.

Siguiente paso: revisor independiente debe revisar especialmente
`advisor/data/sessions.py`, `advisor/analysis/opportunity.py` y
`advisor/report/formatter.py`, y el supervisor debe cerrar el punto del ISIN de
`EXH1.DE`.


---

## Revisión independiente — 2026-09-18 — VEREDICTO: CORREGIR → corregido

Evidencia completa en `evidence/2026-09-18-T-007-revision/README.md`.

**BLOCKER (corregido).** `VERIFICAR_BROKER` sacaba a los activos sin verificar
de la población de `POLICY_OPERAR` del backtest, porque `engine.py` filtraba por
`accion == ACCION_COMPRAR`, y además esas operaciones desaparecían del informe
del backtest sin dejar rastro. Contradice D-04 e INV-04, y contamina la
población que A-02 va a medir en GATE P2. Medido con la misma señal cambiando
solo `trade_republic`: `yes` → entra, `unknown` → no entraba. Corregido con
`ACCIONES_OPERABLES` en `advisor/backtest/engine.py`, fila propia en
`advisor/backtest/report.py` y `VERIFICAR_BROKER` fuera del cómputo de vetos.
Tres tests de regresión que fallan contra el código sin corregir.

**Defecto menor (corregido).** `market_state` lanzaba `TypeError` con un
`datetime` sin zona horaria, mientras `trim_unclosed_bar` —mismo módulo— lo
tolera. Hoy no muerde porque todos los llamantes pasan `datetime.now(timezone.utc)`,
pero se llama dentro de la generación de cada ficha: un fallo ahí mata el
informe entero. Corregido con la convención que ya usaba el módulo.

**FOLLOW_UP heredado (no se corrige aquí).** Los 10 activos marcados `no` en el
broker quedan fuera de `POLICY_OPERAR` **desde PR 1**, no desde esta ficha.
Incorporado como requisito 5 de T-009, que es la ficha que separa el filtro de
ejecución del score.

**Dos afirmaciones comprobadas, no aceptadas por fe.** El cambio de calidad
57/31/19 → 60/28/19 sí es drift: comparando el cierre viejo con el nuevo el
2026-09-17, **0 de las 15 plazas** tienen cierre distinto, luego el código no
pudo moverlo. Y el ISIN de `EXH1.DE` (`DE000A0H08M3`) queda cerrado: ya estaba
escrito desde OA-03 y se cruzó contra la ficha del emisor (nombre, plaza y país
del prefijo coinciden).

**Aviso para T-010.** La pasada real generó **una sola** ficha de oportunidad,
así que la métrica de GATE L0 «0 fichas con Precio actual» se apoya aquí en un
único caso. Debe medirse con una pasada con más fichas.

**Verificación final:** 517 tests, `ruff` y `mypy` limpios.
