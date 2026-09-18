# Gates

Una puerta es una condición **objetiva** entre dos bloques de trabajo. Se
cruza cuando todos sus requisitos están en `evidence/` y un revisor
independiente lo ha confirmado. Cruzar una puerta se registra en
`docs/decision-log.md` con fecha, commit y ruta de la evidencia.

Convenciones: «artefacto» = fichero en `evidence/` o en el repositorio;
«test» = nombre en `tests/`; «desbloquea» = qué trabajo puede empezar.

---

## GATE L0 — Correctitud de ejecución y del dato

> **CRUZADO el 2026-09-18** sobre `main` tras T-007, T-008 y T-009 (ficha
> T-010). Las seis métricas medidas juntas y los siete requisitos respondidos
> en `evidence/2026-09-18-L0-cierre/README.md`. Dos precisiones declaradas,
> ninguna excepción: la métrica 4 se apoya en 2 fichas (el informe solo genera
> ficha completa para OPERAR) y la 5 se cumple en el informe con un descarte
> cuyo motivo va en `execution_code`. La casilla 26 del plan (backtest en vivo
> reproducible) queda abierta con ficha T-015. Decisión D-30.


**Cierra** la línea 0 (PR 1–5 de `docs/plan-ejecucion.md`). Mientras no se
cruce, **ninguna** fase de la línea A recalibra nada.

Requisitos:

1. PR 1 mergeado en `main` (hecho en rama: `e929da4`; merge pendiente).
2. PR 2 aceptado: sesiones esperadas desde calendario de plaza (INV-05);
   cripto 24/7; el hueco del 2026-09-07 tiene causa identificada (1 de 3:
   mercado cerrado / proveedor no entregó / pipeline la perdió) con test.
3. PR 3 aceptado: `DataQuality` con dimensiones separadas (frescura,
   completitud reciente, completitud histórica, indicadores, ejecutabilidad) y
   códigos estructurados de descarte.
4. PR 4 aceptado: estado de mercado `PRE_OPEN/OPEN/CLOSED`, «último cierre» en
   vez de «precio actual» (INV-11), reevaluación a precio nuevo, estados de
   broker `AVAILABLE/UNAVAILABLE/UNVERIFIED`, `EXH1.DE` con ISIN
   `DE000A0H08M3` verificado.
5. PR 5 aceptado: informe con score / setup / ejecución / dos entradas máximas
   separadas; las siete invariantes de integración de la fase 13 como tests;
   fase 14 ejecutada (filtro de ejecución medido aparte del score); fase 15
   limpia.
6. Manifiesto de ejecución y migraciones (C-01, C-02) aceptados, porque PR 3 y
   PR 4 añaden columnas y no se añade ninguna sin migración (INV-17).
7. CI en verde en `main` (C-00).

Métricas (comparadas contra `evidence/2026-09-14-L0-baseline/`):

| Métrica | Valor de aceptación |
|---|---|
| Activos con falsos huecos por festivo ajeno (`AZN`, `TSM`, ETFs Xetra sobre `^GSPC`/`^N225`) | 0 |
| Activos `INCOMPLETO` por el 2026-09-07 | explicados uno a uno con la causa identificada |
| `reward_risk(entry_max, target2, stop) < min_rr` en la salida real | 0 casos |
| Fichas con «Precio actual» cuando solo hay cierre | 0 |
| Descartes sin código de motivo | 0 |
| Recomendaciones persistidas sin `run_id` | 0 desde la migración |

Artefactos: `evidence/<fecha>-L0-cierre/` con `antes.txt` (baseline),
`despues.txt`, tabla de activos por motivo, tabla de la fase 14, salida de la
fase 15.

Tests: `tests/test_execution.py` (o el fichero real de la fase 13),
`tests/test_sessions.py`, `tests/test_freshness.py`, migraciones.

Desbloquea: GATE P2 (rehacer P2.3/P2.4) y el despliegue de producción de la
línea 0 en la Pi.

---

## GATE P2 — Laboratorio corregido y congelado

Requisitos:

1. GATE L0 cruzado.
2. Cosecha fijada: `data_vintage_id = 071ddb2b…` (o una nueva si el
   proveedor obliga; entonces se registra por qué y se compara).
3. `universe_vintage_id` calculado y registrado (A-00), con la declaración de
   sesgo de la sección «Universo» de `docs/roadmap.md` copiada en la
   evidencia.
4. P2.3 y P2.4 **rehechos una sola vez** con fortaleza relativa alineada y
   con la geometría/ejecución de la línea 0, publicando antes/después:
   expectancy neta en R por bloque (primaria), tasa agrupada y
   `P(objetivo antes de stop)` (secundarias), MAE, MFE, por banda, región y
   activo.
5. P2.5 (capacidad) reejecutado sobre el resultado nuevo, con
   `experimental_resolution` publicada.
6. Decisión formal sobre el RR en el score, salida de P2.4, en el decision log.
7. Hashes de las tablas de resultados registrados en `evidence/`.

Métricas: número de señales, número de bloques, resolución, intervalos por
banda; el gate no exige ningún valor concreto, exige que estén publicados.

Desbloquea: P3.

---

## GATE P3 — Score v2 calibrado

Requisitos:

1. Dimensiones y pesos redefinidos y documentados con `score_model_version`
   nuevo. Ninguna observación posterior se mezcla con la anterior sin etiqueta.
2. Umbrales `min_score_operar` / `min_score_vigilar` calibrados **por
   horizonte** (swing y medio por separado) con el estimador primario
   (INV-14), y `calibrated: false` declarado para intradía.
3. Ordenación medida bajo el estimador primario: publicada como intervalo por
   banda y por bloque, con veredicto `SUFICIENTE / LIMITADA / INSUFICIENTE /
   NO CONCLUYENTE`.
4. Ablación por dimensión (`score_sin_X`) publicada.
5. Revisión independiente del look-ahead (obligatoria).

Métricas de aceptación: **no** se exige que el score ordene. Se exige que la
respuesta sea inequívoca y esté cuantificada. Si es NO CONCLUYENTE, P3 se
cruza igualmente con la etiqueta, y P4 se hace sobre `score_signal` sin
umbrales operativos nuevos.

Desbloquea: P4.

---

## GATE P4 — Geometría

Requisitos:

1. Variantes de stop, objetivo y entrada comparadas **pareadas por
   `signal_id`** con bootstrap por bloques (P2.6), sobre el mismo
   `data_vintage_id`.
2. Cada variante publica ΔR medio, IC por bloque, dispersión y heterogeneidad;
   ninguna se elige por el promedio si la heterogeneidad es alta sin explicar
   en qué régimen/región/volatilidad mejora.
3. **Holgura de entrada** medida (decisión D-06): para cada geometría,
   `entry_max_rr − price` en ATR y fracción de señales que serían
   `ABOVE_MAX_ENTRY` a la apertura siguiente.
4. Número total de comparaciones publicado.

Desbloquea: P5.

---

## GATE P5 — Regiones robustas

Requisitos: superficies de parámetros publicadas; configuraciones descartadas
por fragilidad o dependencia de un solo mercado listadas con motivo; conjunto
de políticas candidatas ≤ 5, cada una con su `config` completa y hash.

Desbloquea: P6.

---

## GATE P6 — Sistema completo

Requisitos: simulador de cartera con capital, posiciones simultáneas,
ocupación, exposición por región/divisa/sector, costes, slippage, dividendos y
orden cronológico real. Métricas publicadas por política candidata: CAGR,
volatilidad, Sharpe, Sortino, max drawdown, Calmar, exposición media,
turnover, profit factor, R total y R por operación, **y** exceso sobre el
buy-and-hold del propio universo en la misma ventana (mitigación del sesgo de
universo, ver roadmap).

Desbloquea: P7.

---

## GATE P7 — La ventaja sobrevive fuera de muestra (en el tiempo)

Requisitos:

1. Ventanas de desarrollo, validación y holdout definidas **antes** de mirar
   (fechas en el decision log), con configuración congelada antes de cada
   ventana.
2. El holdout se consulta una vez (INV-15) y la consulta queda registrada.
3. Resultado publicado con el estimador primario, intervalos y
   `experimental_resolution`.
4. **Etiqueta obligatoria en toda tabla y conclusión:** «fuera de muestra en
   el tiempo, condicionado al universo seleccionado en 2026 (sesgo de
   supervivencia y selección no corregido)». Sin esa etiqueta el gate no se
   cruza.

Si la ventaja no sobrevive: no se ajusta el holdout; se vuelve a
investigación con un `score_model_version` nuevo y una ventana de holdout
nueva y posterior.

Desbloquea: portfolio risk (R-01) y P10.

---

## GATE B0 — Contrato point-in-time

Requisitos: `advisor/context/models.py` con `source`, `source_id`, `symbol`
o `issuer_id`, `observed_at`, `published_at`, `available_at`,
`content_hash`, `raw_payload_hash`, `provider`, `provider_schema_version`;
identidad emisor/instrumento/listing definida; test de que ningún dato con
`available_at > analysis_timestamp` puede entrar a un backtest (INV-09);
ficha de proveedor rellena para cada fuente antes de descargar.

Desbloquea: collectors de noticias, sentimiento, fundamentales y macro.

---

## GATE CONTEXT — El contexto aporta valor demostrado

Requisitos: shadow mode acumulado con muestra suficiente (P2.5 aplicado a la
población de contexto); P8 (fundamentales) y P9 (context study) publicados con
la disciplina de P2 (ablación, bootstrap por bloques, heterogeneidad,
holdout); regresiones del LLM en verde (no fabrica catalizadores, no usa
información no suministrada, no confunde ausencia con neutralidad, no altera
números); versionado LLM persistido (provider, model, prompt_version,
input_source_ids).

Solo se integra lo que demuestre mejora fuera de muestra, y solo en la
dirección conservadora (degradar, nunca rescatar).

---

## GATE PROD — Sistema operativo fiable

Requisitos:

1. CI obligatoria en `main` (pytest, ruff, mypy, tests de integración sin
   red) y branch protection activada por el propietario.
2. Release = tag `vX.Y.Z`; la Pi ejecuta solo tags; `verificar-systemd` y
   `verificar-release` (SHA de la Pi = SHA del tag) en verde.
3. Migraciones con `PRAGMA user_version`, backup previo automático y
   **prueba de restauración** ejecutada en la Pi con su copia real.
4. Manifiesto de ejecución en cada pasada (INV-18) y reconstrucción probada:
   dado un `run_id` de hace ≥ 30 días, reproducir la recomendación con el
   mismo SHA, config y universo.
5. Logs rotados; alertas por Telegram cuando una pasada falla, cuando un
   proveedor falla, cuando el reloj deriva más de 60 s, cuando `events.yaml`
   caduca en < 60 días.
6. Timeouts y reintentos declarados por proveedor; degradación limpia probada
   apagando la red a mitad de pasada.
7. Rollback probado: volver al tag anterior y verificar.

---

## GATE RISK — Riesgo de cartera

Requisitos: límites agregados (riesgo diario y semanal, concentración por
sector, región, factor y divisa, correlación entre posiciones abiertas)
implementados como capa **separada** de la señal, medidos en P6 y declarados
en el informe.

---

## GATE P10 — Validación forward superada

Requisitos:

1. Configuración congelada (tag) durante toda la ventana; duración
   predefinida en el decision log (OD-08; por defecto 3 meses naturales de
   pasadas diarias, mínimo 60 sesiones).
2. Por cada señal emitida se registra: `run_id`, datos disponibles
   (`data_vintage`/frescura), precio de referencia, precio ejecutable
   observado a la apertura siguiente, `execution_state`, `context_state`
   (shadow), y el desenlace posterior (stop/objetivo/tiempo, `net_R`, MAE,
   MFE, retorno del benchmark, alfa).
3. Resultado comparado con lo que P7 predijo para esa política, con el
   estimador primario e intervalos; sin tocar ninguna regla a mitad.
4. Es la **única** validación no condicionada al universo 2026, porque las
   señales se generan sin conocer el futuro y sobre el universo vigente.

Desbloquea: release final y paquete de revisión externa.

---

## Paquete para la revisión externa final

Se entrega como un directorio `evidence/final-review/` con:

```text
HEAD_SHA.txt                 # y tag de release
roadmap.md (copia congelada) # con todos los gates marcados y fechados
decision-log.md (copia)      # decisiones metodológicas y de propietario
config.yaml (copia)          # configuración final con hash
universe.yaml (copia)        # universe_vintage_id
data_vintages.md             # ids, hashes, dónde están las cosechas
resultados/P2..P10/          # tablas, intervalos, resoluciones, hashes
walk-forward.md, holdout.md, forward-test.md
test-summary.txt             # pytest -q, ruff, mypy, versión de Python
ci-status.md                 # enlace al último run verde de main
known-limitations.md         # sesgo de universo, proveedor único, intradía…
deuda-tecnica.md             # FOLLOW_UP abiertos
informes-ejemplo/            # 3 informes reales con su run_id
manifests/                   # manifiestos de ejecución de los informes de ejemplo
```

Debe poder revisarse sin reconstruir conversaciones: cada afirmación del
paquete apunta a un fichero del paquete o a un commit.
