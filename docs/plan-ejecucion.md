# Plan de corrección y cierre de la capa de ejecución

**Estado:** en implementación (rama `fix/execution-data-quality`). Fases 1–3 hechas
(`e929da4`); fases 4–15 pendientes con fichas en `docs/tareas/` (T-003, T-004,
T-005 y siguientes). El orden y las dependencias mandan desde `docs/roadmap.md`;
el método desde `docs/metodo-trabajo.md`.

**Notas de la auditoría del 2026-09-14** (ver `docs/decision-log.md`):

- D-15 sustituye la regla «un commit por fase» de este documento: una entrega
  coherente con commits compilables; fases mutuamente dependientes van juntas.
- D-19: C-00 (CI), C-01 (migraciones) y C-02 (manifiesto) van **antes** de PR 3,
  porque PR 3 y PR 4 añaden columnas y estados.
- D-06: con la geometría por defecto, `entry_max_rr` coincide con el cierre de
  señal; la fase 14 debe medir la pérdida por `ABOVE_MAX_ENTRY` a la apertura y
  P4 tratar la holgura de entrada como dimensión de la geometría.
- D-07: las fases 4 y 6 usan `exchange_calendars` (T-003), y unifican las dos
  taxonomías de plazas que hoy conviven en `freshness.py` y `sessions.py`.
- Línea base real de partida: `evidence/2026-09-14-L0-baseline/`.
**Prioridad:** alta
**Objetivo:** conseguir que una señal técnicamente válida solo se convierta en
`OPERAR` cuando los datos, el precio real de entrada, el RR, el dimensionamiento
y la ejecutabilidad sean coherentes.

Línea base antes de tocar nada (2026-09-14, commit `6d32cf2`): 385 tests pasan,
`ruff check .` limpio, `mypy advisor` limpio sobre 53 ficheros.

---

## 0. Reglas de trabajo

Antes de modificar código:

1. Inspeccionar la estructura actual del repositorio.
2. Localizar las implementaciones reales mediante búsqueda de símbolos, no asumir rutas.
3. Identificar como mínimo: `classify()`, cálculo de targets/stops, cálculo de RR,
   cálculo de `entry_max`, position sizing, `report.py`, `universe.yaml`,
   descarga/normalización de datos de `yfinance`, control de última barra cerrada,
   calidad/frescura de datos, comparación contra benchmark y los tests correspondientes.
4. Ejecutar la suite actual antes de cambiar nada.
5. No modificar simultáneamente scoring, datos y reporting en un único commit.
6. Mantener compatibilidad con los resultados/backtests existentes salvo donde este
   plan indique expresamente un cambio.
7. Cada fase debe terminar con tests verdes antes de comenzar la siguiente.

### Decisiones ya tomadas

Mantener `yfinance` con `auto_adjust=False`.

Mantener almacenamiento/control de `Dividends`, `Stock Splits` y `data_vintage_id`.

Mantener `target_atr_multiples = [1.5, 3.0, 5.0]`.

Mantener la identidad:

```text
net_R = gross_R - cost_pp / risk_pp
```

y corregir cualquier representación porcentual sin alterar esta identidad.

### RR y score

No volver a introducir RR como condición para calcular el **score técnico**.

Separar `setup_score` de `execution_valid`. Un activo puede tener `score = 80` y
`execution_valid = false`, con motivo `precio actual hace que RR < 1.5`.

---

# FASE 1 — Corregir RR y precio máximo de entrada

**Prioridad:** P0. Debe hacerse antes que cualquier otra mejora.

## Problema

El informe del 14/09/2026 produjo, para `EXH1.DE`: precio 56,11 €, entrada máxima
56,63 €, target 2 58,20 €, stop 54,71 €, RR informado 1,5:1.

Pero a 56,63 €:

```text
reward = 58.20 - 56.63 = 1.57
risk   = 56.63 - 54.71 = 1.92
RR     = 0.82
```

La operación deja de cumplir el RR mínimo.

## Implementación

Crear o centralizar una función pura equivalente a `reward_risk(entry, target, stop)`.

Para largos: `reward = target - entry`, `risk = entry - stop`, `rr = reward / risk`.
Debe proteger `risk <= 0`, `target <= entry`, `NaN` e `inf`.

Calcular el precio máximo de entrada compatible con un RR mínimo:

```python
entry_max_rr = (target + min_rr * stop) / (1 + min_rr)
```

Con `target = 58.20`, `stop = 54.71`, `min_rr = 1.5`, el resultado esperado es
`entry_max_rr ~= 56.11`.

No confundir `entry_max_tecnica` con `entry_max_rr`. Usar:

```python
entry_max = min(entry_max_tecnica, entry_max_rr)
```

Si existen otras restricciones legítimas de precio, incorporarlas explícitamente,
no ocultarlas dentro de una fórmula.

## Invariante obligatoria

```python
reward_risk(entry=entry_max, target=target_2, stop=stop) >= min_rr - tolerance
```

Si no se cumple, hay un bug.

## Tests

`test_reward_risk`, `test_entry_max_rr`, `test_entry_max_never_violates_min_rr`,
`test_entry_above_max_is_not_executable` y el caso de regresión obligatorio
`test_exh1_regression_2026_09_14`:

```text
stop = 54.71 · target = 58.20 · min_rr = 1.5
entry_max ~= 56.11 · 56.63 -> NO ejecutable
```

## Criterio de aceptación

Debe ser imposible producir simultáneamente entrada máxima 56,63 €, RR mínimo 1,5,
target 58,20 € y stop 54,71 €.

**Commit:** `fix(execution): enforce minimum RR in maximum entry price`

---

# FASE 2 — Crear una capa explícita de ejecutabilidad

**Prioridad:** P0

Separar definitivamente «¿es un buen setup?» de «¿se puede comprar ahora?».

## Modelo esperado

Una estructura equivalente a:

```python
ExecutionEvaluation(
    reference_price=..., entry_price=..., entry_max=..., stop=..., targets=...,
    rr=..., risk_pct=..., potential_pct=..., position_size=..., capital_at_risk=...,
    executable=..., reason=...,
)
```

No es obligatorio ese nombre ni una `dataclass`: usar la arquitectura actual si ya
existe una estructura apropiada.

## Evaluación a precio real

Un único punto de entrada lógico equivalente a `evaluate_trade_at_entry(...)` que
recalcule RR, riesgo %, potencial %, distancia al stop, position sizing,
capital at risk, `execution_valid` y `execution_reason`.

No reutilizar valores calculados con el cierre anterior cuando el precio de entrada
haya cambiado.

## Estados

```text
EXECUTABLE · ABOVE_MAX_ENTRY · RR_TOO_LOW · INVALID_STOP · INVALID_TARGET
POSITION_TOO_SMALL · DATA_NOT_EXECUTABLE · BROKER_UNVERIFIED · BROKER_UNAVAILABLE
```

## Regla importante

`classify()` puede seguir diciendo que el setup es técnicamente bueno. No hacer
`if rr < min_rr: score = 0`. Hacer conceptualmente:

```python
setup = classify(...)
execution = evaluate_execution(...)

if setup.valid and execution.executable:
    action = "OPERAR"
elif setup.valid:
    action = "ESPERAR"
```

## Tests

```text
setup bueno + RR bueno -> OPERAR
setup bueno + RR malo  -> ESPERAR / NO_OPERAR
setup malo  + RR bueno -> NO_OPERAR
precio > entry_max     -> NO_CHASE
precio <= entry_max    -> puede ser ejecutable
```

**Commit:** `refactor(execution): separate setup score from trade executability`

---

# FASE 3 — Recalcular position sizing con la entrada efectiva

**Prioridad:** P0

El tamaño de posición no puede permanecer calculado con el precio del snapshot si
finalmente se entra a otro precio.

## Fórmula

```python
risk_per_unit    = entry - stop
risk_budget      = portfolio_value * risk_pct
position_by_risk = risk_budget / risk_per_unit
position_by_cap  = (portfolio_value * max_position_pct) / entry
position_size    = min(position_by_risk, position_by_cap)
```

Adaptar a acciones fraccionarias/unidades según la lógica actual del broker.

## Guardar restricción dominante

Añadir un dato equivalente a `position_limit_reason`, con valores
`RISK_BUDGET`, `MAX_POSITION_PCT`, `BROKER_LIMIT`, `MIN_ORDER_SIZE`. Ejemplo:

```text
Tamaño por riesgo: 20,1% · Máximo por posición: 10%
Tamaño final: 10% · Restricción: MAX_POSITION_PCT
```

## Tests

```text
entry cambia -> position_size cambia
stop cambia  -> position_size cambia
risk_per_unit <= 0 -> operación inválida
posición superior al 10% -> limitada al 10%
riesgo máximo -> nunca superado
```

**Commit:** `fix(risk): recalculate position sizing from effective entry`

---

# FASE 4 — Separar calendario de mercado y benchmark

**Prioridad:** P0

## Problema actual

La comprobación de barras ausentes utiliza en determinados activos sesiones del
benchmark. Eso mezcla dos conceptos distintos: `exchange_calendar` y `benchmark`.

## Nueva separación

Cada instrumento debe poder resolver `exchange`, `exchange_calendar`,
`exchange_timezone` y `benchmark`:

```yaml
ticker: SXR8.DE
exchange: XETRA
exchange_calendar: XETRA
exchange_timezone: Europe/Berlin
benchmark: ^GSPC
```

El benchmark sirve para fortaleza relativa, régimen, comparación de rendimiento y
contexto. **Nunca** para decidir si el activo debería tener una vela.

ADR: la existencia de una sesión de `TSM` depende de NYSE, no de si Taiwán estuvo
abierto. ETF: que el S&P 500 cotice un día no implica que el ETF Xetra tenga que
cotizar ese día. Aplicar el mismo principio a `IQQT.DE`, `IQQK.DE`, `EUNL.DE`,
`EUNN.DE`, `QDV5.DE`, `SXR8.DE`, `VVSM.DE`, `ZPRR.DE`, `Q8Y0.DE`, `4GLD.DE`,
`ICGA.DE`, `DFEN.DE` y demás ETFs.

## Sesiones esperadas

```python
expected_sessions = calendar.sessions(start, end)
missing_sessions  = expected_sessions - actual_sessions
```

No `expected_sessions = benchmark.index`.

## Tests de regresión

XETRA vs S&P 500 · XETRA vs Nikkei · ADR NYSE vs mercado de origen · BME ·
Euronext Paris · Euronext Amsterdam · NASDAQ · NYSE · JPX · HKEX · Korea.

**Commit:** `fix(data): validate bars against exchange calendar instead of benchmark`

---

# FASE 5 — Investigar el 07/09/2026

**Prioridad:** P0/P1

No arreglar este caso añadiendo una excepción. Hay que encontrar la causa.

## Síntoma

Numerosos activos europeos aparecen con `falta sesión 2026-09-07`: `SAN.MC`,
`BBVA.MC`, `IBE.MC`, `ITX.MC`, `SAP.DE`, `DBK.DE`, `ASML.AS`, `TTE.PA`, `RHM.DE`,
`AIR.PA`, etc.

## Auditar pipeline

Seguir una barra concreta desde `yfinance` hasta el informe, comprobando: raw
dataframe, timezone original, timezone convertido, fecha normalizada, filtro de
sesiones, detección de barra cerrada, resample, deduplicación, cache, persistencia
y `data_vintage_id`.

Buscar especialmente usos de `index.date`, `tz_localize(...)`, `tz_convert(...)`,
`normalize()`, `floor("D")` y `resample("1D")`.

## Regla de timezone

La fecha de sesión debe determinarse en `exchange_timezone`, no en UTC de forma
indiscriminada:

```python
session_date = timestamp.tz_convert(exchange_timezone).date()
```

## Debug temporal

Crear una herramienta o test capaz de imprimir, para una fecha solicitada: ticker,
raw timestamp, raw timezone, converted timestamp, exchange timezone, derived
`session_date`, expected session y actual session. No dejar `print()` permanentes
en producción.

## Criterio de aceptación

Para cada activo afectado debe poder explicarse una de tres cosas, sin un cuarto
estado ambiguo:

1. el mercado estaba cerrado, luego no falta barra;
2. el mercado estaba abierto y Yahoo no entregó barra;
3. Yahoo entregó barra y nuestro pipeline la perdió.

**Commit:** `fix(data): correct session-date normalization and missing-bar detection`

---

# FASE 6 — Cripto 24/7

**Prioridad:** P1

No considerar `BTC-EUR`, `ETH-EUR` ni `SOL-EUR` como `DEGRADADO` simplemente por no
disponer de calendario bursátil comparable.

Implementar un calendario lógico `CRYPTO_24_7` con sesiones de lunes a domingo,
365/366 días. No utilizar festivos bursátiles, sesiones del benchmark ni cierres de
NYSE/Xetra.

Mantener tratamiento especial de la última barra de cripto, porque no existe cierre
regular comparable al de una bolsa. Definir claramente cuándo una vela `1d` se
considera finalizada, sin mezclarlo con el `regular_close + 20 min` bursátil.

## Tests

```text
sábado -> sesión válida · domingo -> sesión válida
25 diciembre -> sesión válida · benchmark cerrado -> irrelevante
```

**Commit:** `fix(data): add native 24x7 session model for crypto`

---

# FASE 7 — Rediseñar calidad de datos

**Prioridad:** P1

`OK` / `INCOMPLETO` / `DEGRADADO` mezcla hoy distintos tipos de problema. Una barra
antigua ausente puede ensuciar una señal actual perfectamente utilizable.

## Separar dimensiones

```python
DataQuality(
    freshness=..., recent_completeness=..., historical_completeness=...,
    indicator_readiness=..., execution_readiness=...,
)
```

No es obligatorio utilizar exactamente esa clase.

## Severidad temporal

```text
última sesión ausente -> CRITICAL · últimas 5 sesiones -> HIGH
últimas 20 sesiones   -> MEDIUM   · más antiguas       -> WARNING
```

El objetivo es que una anomalía de hace meses no tenga el mismo efecto que no
disponer del cierre de ayer.

## Señal ejecutable

Debe poder quedar `setup_score: 76`, `historical_quality: WARNING`,
`recent_quality: OK`, `execution_ready: true` si la anomalía histórica no afecta a
los indicadores utilizados.

Respetar los requisitos actuales de número de velas (p. ej. 253 velas, 100 %
requerido, 6/6 indicadores). Una anomalía histórica solo debe bloquear si provoca
insuficiencia de historial, indicador inválido, ventana contaminada o frescura
insuficiente.

## Tests

missing última sesión · missing hace 3 · hace 15 · hace 150 · festivo legítimo ·
historial suficiente pese al warning · indicador que sí depende del hueco.

**Commit:** `refactor(data): separate freshness from historical data quality`

---

# FASE 8 — Motivos estructurados de descarte

**Prioridad:** P1

No volver a generar bloques como «91 activos descartados: TSM…, SAN.MC…, GS…,
XOM…» sin poder saber inmediatamente por qué se descartó cada uno.

## Códigos estructurados

```text
LOW_SCORE · LOW_RR · ABOVE_MAX_ENTRY · STALE_DATA · MISSING_RECENT_DATA
INSUFFICIENT_HISTORY · INVALID_INDICATORS · INVALID_TREND · OVEREXTENDED
VOLATILITY_TOO_HIGH · EVENT_RISK · BROKER_UNAVAILABLE · BROKER_UNVERIFIED · NO_ENTRY
```

Distinguir `discard_reason` de `warning`: un warning no debe implicar necesariamente
descarte.

## Salida esperada

```text
NVDA
  setup: descartado · reason: LOW_SCORE · score: 64 · threshold: 70

EXH1.DE
  setup: válido · execution: esperar · reason: ABOVE_MAX_ENTRY
```

Los candidatos próximos al umbral deben continuar apareciendo en radar aunque no
sean ejecutables.

**Commit:** `refactor(signals): add structured rejection and execution reasons`

---

# FASE 9 — Precio de cierre vs precio ejecutable

**Prioridad:** P1

Un informe generado antes de la apertura no debe denominar «precio actual» al cierre
anterior.

Determinar el estado de mercado `PRE_OPEN` / `OPEN` / `CLOSED` según
`exchange_calendar` y `exchange_timezone`, y mostrar:

```text
Último cierre: 56,11 € · Sesión: 2026-09-11 · Mercado: PRE_OPEN
```

Cuando haya nueva barra/precio utilizable:

```python
if market_price > entry_max:
    executable = False
    reason = "ABOVE_MAX_ENTRY"
```

No perseguir precio. Regla: setup válido ≠ orden válida a cualquier precio.

**Commit:** `feat(execution): distinguish reference close from executable market price`

---

# FASE 10 — Revisión después de apertura

**Prioridad:** P2

Preparar la arquitectura para ejecutar una segunda evaluación cuando Europa/EE.UU.
ya estén abiertos. No es necesario implementar un broker en tiempo real en esta fase,
pero sí debe ser posible volver a pasar nuevo precio, mismo setup y mismo
stop/targets (o setup recalculado) por la capa de ejecución.

```text
06:37 UTC  EXH1.DE · setup_score 74 · último cierre 56,11 · entry_max 56,11 · CANDIDATO
apertura 56,70 -> execution_valid false · reason ABOVE_MAX_ENTRY · action NO_CHASE
precio  55,95 -> RR > 1,5 · execution_valid true · action OPERAR
```

**Commit:** `feat(execution): support post-open trade reevaluation`

---

# FASE 11 — Broker e identificación de instrumentos

**Prioridad:** P2

Completar en `universe.yaml`, adaptando las claves al esquema real existente:

```yaml
ticker: EXH1.DE
name: iShares STOXX Europe 600 Oil & Gas UCITS ETF (DE)
isin: DE000A0H08M3
exchange: XETRA
currency: EUR
```

Separar broker de señal con estados `AVAILABLE` / `UNAVAILABLE` / `UNVERIFIED`.
No convertir `UNVERIFIED` en `UNAVAILABLE`.

```python
if not setup_valid:                  action = "NO_OPERAR"
elif not execution_valid:            action = "ESPERAR"
elif broker_status == "UNAVAILABLE": action = "NO_OPERAR"
elif broker_status == "UNVERIFIED":  action = "VERIFICAR_BROKER"
else:                                action = "OPERAR"
```

**Commit:** `feat(universe): complete instrument metadata and broker execution state`

---

# FASE 12 — Corregir el informe

**Prioridad:** P2

Modificar `report.py` o los módulos reales que generen estas secciones.

## Oportunidad

Mostrar por separado: score técnico, estado del setup, estado de ejecución, último
cierre, precio evaluado, entrada ideal, entrada máxima por RR, entrada máxima
definitiva, RR al precio evaluado, target, stop y motivo de espera si existe.

```text
EXH1.DE — score 74/100

Setup: 🟢 VÁLIDO
Ejecución: 🟡 ESPERAR

Último cierre: 56,11 €
Entrada ideal: 55,76–56,11 €
Entrada máxima: 56,11 €
Stop: 54,71 €
Objetivo principal: 58,20 €
RR a 56,11 €: 1,49 ≈ 1,5

No perseguir precio.
Si cotiza > 56,11 €, la operación deja de cumplir el RR mínimo configurado.
```

Usar la precisión interna suficiente para evitar que el redondeo visual genere falsos
incumplimientos.

## Liquidez

Sustituir «Liquidez recomendada: 90%» por «Capital asignado a señales actuales: 10% ·
Capital no asignado: 90%», salvo que exista realmente un modelo explícito de
asignación estratégica a efectivo.

## Régimen

Sustituir «Principal riesgo del mercado: tendencia alcista y volatilidad contenida»
por «Régimen: RISK_ON — tendencia alcista y volatilidad contenida». No inventar un
riesgo principal si el sistema no dispone de datos suficientes para determinarlo.

## Calidad

Resumen con frescura reciente y calidad histórica (`OK` / `WARNING` / `DEGRADED`).
No imprimir docenas de fechas antiguas en el informe principal: mover el detalle
completo a log, JSON o informe de diagnóstico según la arquitectura actual.

## Descartados

Agrupar por: score insuficiente · RR/ejecución · datos · tendencia · sobreextensión ·
broker · otros.

**Commit:** `refactor(report): expose setup, execution and data-quality states clearly`

---

# FASE 13 — Tests de integración del informe

**Prioridad:** P1 antes de considerar terminado el arreglo.

1. Si `action == OPERAR`, entonces `setup_valid`, `execution_valid`,
   `rr >= min_rr`, `entry <= entry_max` y, si la política lo exige,
   `broker_status == AVAILABLE`.
2. `entry_max` nunca puede producir un RR inferior al configurado.
3. El benchmark nunca puede proporcionar el calendario usado para `missing_sessions`.
4. Un festivo del mercado no puede aparecer como `missing session`.
5. Una sesión de un benchmark extranjero no obliga a que el activo cotizado
   localmente tenga vela.
6. El informe no debe decir «Precio actual» cuando solo dispone de último cierre.
7. Cambiar `entry` debe provocar el recálculo de RR, `risk_pct`, `potential_pct`,
   position size, capital at risk y estado de ejecución.

**Commit:** `test: add execution and market-calendar regression invariants`

---

# FASE 14 — Backtest y event study

Una vez corregida la lógica productiva, comprobar que los cambios no contaminan
P2/P3. La rama/event study existente utiliza un universo amplio y más de 100.000
señales: no regenerar conclusiones mezclando código antiguo y nuevo.

Revisar especialmente `BacktestTrade`, `classify()`, RR, targets, score buckets,
`_MIN_SAMPLE`, `_SCORE_BUCKETS`, MAE/MFE, costes y `net_R`.

El nuevo filtro de ejecutabilidad por RR debe estudiarse **por separado** del score.
No modificar retrospectivamente el score histórico para convertir el RR en condición
de puntuación: analizar `setup_score` + `execution filter` como dos capas.

Mantener/obtener expectancy, profit factor, payoff ratio, win rate, mediana R,
percentiles R, MAE, MFE y tamaño de muestra, por score bucket, mercado, setup,
horizonte y estado de ejecución.

**Commit:** `test(backtest): validate execution filters independently from setup score`

---

# FASE 15 — Limpieza final

```text
[ ] eliminar código duplicado de RR
[ ] eliminar cálculos antiguos de entry_max
[ ] eliminar uso del benchmark como calendario
[ ] eliminar excepciones temporales del 07/09
[ ] eliminar prints/debug
[ ] comprobar type hints
[ ] comprobar lint
[ ] ejecutar tests
[ ] ejecutar informe completo
[ ] comparar salida antes/después
```

---

# Orden de PR

- **PR 1 — Execution correctness:** fases 1, 2 y 3. Garantizar matemáticamente que
  ninguna operación pueda marcarse como ejecutable si el precio real destruye el RR
  mínimo.
- **PR 2 — Market calendars:** fases 4, 5 y 6. Eliminar falsos `missing_sessions` y
  separar calendario de cotización y benchmark económico.
- **PR 3 — Data quality:** fases 7 y 8. Diferenciar problemas históricos, recientes
  y bloqueantes.
- **PR 4 — Real execution state:** fases 9, 10 y 11. Pasar de «setup encontrado» a
  «operación realmente ejecutable».
- **PR 5 — Reporting + regression:** fases 12, 13, 14 y 15.

Los commits van en el orden de las fases. **Regla vigente (D-15):** un commit por
entrega coherente y compilable; fases mutuamente dependientes van juntas; no
agrupar los 14 puntos en un único commit.

---

# Criterios finales de aceptación

```text
[ ] RR calculado siempre desde el precio efectivo.
[ ] entry_max respeta min_rr.
[ ] El score técnico no depende del filtro duro de RR.
[ ] Setup y ejecución son estados distintos.
[ ] Un score alto puede terminar en ESPERAR.
[ ] Cambiar entry recalcula el dimensionamiento.
[ ] Riesgo real nunca supera el configurado.
[ ] Calendario del activo depende del exchange.
[ ] Benchmark no determina sesiones esperadas.
[ ] ETF usa calendario de su bolsa.
[ ] ADR usa calendario donde cotiza el ticker.
[ ] Cripto tiene calendario 24/7.
[ ] El caso 07/09/2026 tiene causa identificada y test.
[ ] Festivos no generan falsos missing sessions.
[ ] Freshness y calidad histórica están separadas.
[ ] Warning histórico no bloquea automáticamente ejecución.
[ ] Descartes tienen código de motivo.
[ ] Último cierre no se presenta como precio actual.
[ ] Gap por encima de entry_max produce NO_CHASE.
[ ] Broker UNVERIFIED no se presenta como disponible.
[ ] EXH1.DE tiene ISIN DE000A0H08M3.
[ ] report.py no presenta contradicciones entre RR, stop, target y entrada máxima.
[ ] Tests unitarios verdes.
[ ] Tests de integración verdes.
[ ] Informe completo de 107 activos se genera sin errores.
[ ] Event study/backtest continúa siendo reproducible.
[ ] data_vintage_id continúa funcionando.
```

---

# Caso de regresión obligatorio: EXH1.DE

```yaml
ticker: EXH1.DE
reference_price: 56.11
stop: 54.71
target_2: 58.20
min_rr: 1.5
```

Resultado aproximado esperado: `entry_max_rr: 56.11`.

```text
entry 55.76 -> ejecutable por RR
entry 56.00 -> ejecutable por RR
entry 56.11 -> límite
entry 56.63 -> NO ejecutable, motivo RR_TOO_LOW
```

---

# Instrucción de trabajo incremental

Antes de cada fase: localizar el código existente; explicar brevemente dónde está
implementada la lógica actual; identificar los tests existentes afectados; realizar
el cambio mínimo necesario; añadir/regenerar tests; ejecutar la suite; no continuar
si hay regresiones no explicadas.

No reescribir módulos completos si el cambio puede realizarse de forma localizada.
No modificar fórmulas, thresholds o comportamiento no relacionados para hacer pasar
tests. No esconder errores de datos mediante excepciones específicas para tickers o
fechas. No convertir el benchmark en proxy del calendario. No cambiar el significado
del score para resolver problemas de ejecución.

Cuando exista discrepancia entre score, RR, entry, stop, target y position sizing, la
salida debe favorecer la seguridad (`NO_OPERAR` / `ESPERAR`) y registrar el motivo.

---

# Definición de terminado

El asesor habrá completado esta etapa cuando pueda responder de forma inequívoca y
matemáticamente consistente a estas cuatro preguntas para cada activo:

1. ¿Es técnicamente interesante? → `setup_score`
2. ¿Son fiables y suficientemente recientes los datos? → `data_quality` / `execution_readiness`
3. ¿Es rentable asumir el riesgo al precio al que realmente puedo entrar? → evaluación de ejecución / RR
4. ¿Puedo ejecutarlo realmente en el broker y con qué tamaño? → estado de broker / position sizing

Solo cuando las cuatro capas sean compatibles: `ACTION = OPERAR`. Hasta entonces,
`RADAR`, `ESPERAR`, `NO_CHASE`, `VERIFICAR_BROKER` o `NO_OPERAR` según corresponda.
