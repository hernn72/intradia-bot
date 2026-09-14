# Roadmap de intradia-bot

Estado al **14 de septiembre de 2026**.

Unifica el plan de trabajo del asesor con el plan de corrección de la capa de
ejecución (`docs/plan-ejecucion.md`) y los pendientes acumulados
(`docs/pendientes.md`). Versión visual publicada como artefacto:
https://claude.ai/code/artifact/90dfc34d-b1fc-4546-ac03-f81e82f9f358

- Rama `fix/execution-data-quality`, commit `e929da4`.
- 398 tests, `ruff` y `mypy` limpios.
- La Pi sigue con `d795127`, del 2 de septiembre: sin el PR 1.
- Laboratorio P2.0–P2.6 implementado, **no congelado**.

---

## Revisión del plan de trabajo

El plan de trabajo se escribió sobre `main` a 2 de septiembre. Su idea central
—dos líneas separadas hasta que ambas estén validadas— se conserva entera. Seis
cosas ya no encajan.

### 1. Rehacer P2.3 ahora haría el trabajo dos veces

«Rehacer P2.3 con la fortaleza relativa corregida» era la primera prioridad.
Pero quedan cuatro entregas del plan de ejecución que cambian el dato sobre el
que P2.3 mide: qué barras existen (calendarios de plaza, el hueco del 07/09,
cripto 24/7), qué activos quedan vetados (rediseño de la calidad del dato) y qué
señales llegan a entrar (la lógica de relleno).

El criterio de cierre del propio plan dice que «P2.3 queda congelado con la
implementación actual y sus hashes de datos». Congelarlo hoy es congelarlo
contra una implementación que va a cambiar. Lo caro no es repetir la pasada
—la cosecha no cambia y rehacerla es barato— sino que las conclusiones
publicadas entre medias alimentarían P3, que es donde no cabe un número mal
medido.

**Cerrar primero la línea de ejecución, rehacer P2.3 y P2.4 una sola vez, y
congelar entonces.**

### 2. Ya no hay un motivo para rehacer P2.3, hay dos

El plan atribuía la contaminación solo a la fortaleza relativa desalineada.
Hay un segundo motivo, independiente y medido el 2026-09-14: estrechar
`entry_max` para que respete el ratio mínimo cambia qué señales entran. Sobre la
cosecha `071ddb2b`, horizonte swing y coste cero, en operaciones OPERAR/TODAS:

| Símbolo | OPERAR | TODAS |
|---|---|---|
| `AAPL` | 7 → 4 | 111 → 104 |
| `MSFT` | 5 → 3 | 118 → 114 |
| `SAP.DE` | 6 → 4 | 103 → 97 |

`POLICY_TODAS` es la población de control del estudio y también se mueve.

### 3. «Sacar el beneficio/riesgo del score» no es lo que hizo el PR 1

Suenan igual y no lo son. El PR 1 le quitó al ratio el poder de **vetar** dentro
de `classify()`. El ratio sigue siendo una **dimensión de la puntuación**, 20 de
100 puntos, en `advisor/analysis/scoring.py:251`. La decisión de sacarlo del
score sigue entera pendiente y debe salir de P2.4, no de que el veto ya no
exista.

### 4. Faltan tres principios que el proyecto ya ha pagado dos veces

Van incorporados abajo, marcados como nuevos. El 2026-09-14 una entrega con 398
tests en verde, `ruff` y `mypy` limpios habría dejado al asesor sin recomendar
nada y al backtest en cero operaciones.

### 5. Falta la decisión sobre las plazas europeas

El plan cubría ISIN, Trade Republic y símbolos europeos, pero no la tercera
decisión que cuesta dinero: si se paga otra fuente de datos para Xetra y
Euronext. No se decide con una observación, y lo que la desbloquea es el
histórico de frescura que la Pi acumula desde el 2 de septiembre.

### 6. Dos casillas ya tienen respuesta

«Nunca recomendar con `INCOMPLETO`» está implementado desde el 2 de septiembre,
con veto configurable y sin tocar `score.value`. «La Raspberry Pi ejecuta
exactamente la versión registrada en GitHub» es hoy falso.

---

## Principios que no se rompen

Reglas de arquitectura, no buenas intenciones: cualquier entrega que las
incumpla se devuelve.

- **La decisión es determinista.** El LLM no calcula indicadores, niveles,
  stops, objetivos ni tamaño, y no puede alterar `score.value`.
- **Todo dato tiene instante.** `available_at <= analysis_timestamp`. Si no
  puede demostrarse, no sirve para un backtest point-in-time.
- **Una sola función de cálculo.** Investigación y producción comparten
  implementación. La fortaleza relativa ya se rompió por aquí una vez.
- **Toda señal nueva se mide antes de producción,** y `NO CONCLUYENTE` sigue
  siendo un resultado válido.
- **Nada se optimiza a posteriori en silencio.** Si una regla se ajusta después
  de mirar el resultado, queda documentada como exploratoria.
- **Señal, ejecutabilidad y calidad del dato van separadas.** Tres conceptos,
  tres estados. El PR 1 estuvo a punto de fusionar los dos primeros.
- **Lo desconocido se declara desconocido.** Nunca se inventa un dato ni se
  afirma una disponibilidad no comprobada.
- **(nuevo) Verde no es verificado.** La pregunta después de una entrega no es
  «¿pasan los tests?», sino «¿qué número de la salida real puedo comprobar a
  mano?».
- **(nuevo) Un cambio que decide cuándo se recomienda se mide por a quién le
  cae.** No basta con comprobar que la regla se aplica: hay que contar a cuántos
  activos afecta y por qué motivo.
- **(nuevo) Un fixture que no reproduce el universo real no prueba nada.** Los
  107 activos están en `unknown`; el fixture de tests usaba `yes`, y por eso la
  suite no vio nada.

---

## Línea 0 — Cerrar la capa de ejecución y el dato

Va delante de todo. Mientras el calendario salga del benchmark y la calidad del
dato mezcle problemas de hace meses con los de ayer, cualquier medición del
modelo se hace sobre arena. Detalle completo en `docs/plan-ejecucion.md`.

| PR | Fases | Qué cierra | Estado |
|---|---|---|---|
| 1 | 1–3 | Corrección de la ejecución | hecho (`e929da4`) |
| 2 | 4–6 | Calendarios de mercado | siguiente |
| 3 | 7–8 | Calidad del dato | |
| 4 | 9–11 | Estado real de ejecución | |
| 5 | 12–15 | Informe y regresión | |

**PR 2 — calendarios.** Cada instrumento resuelve `exchange_calendar` y
`exchange_timezone` aparte de su `benchmark`; investigar el hueco del 07/09/2026
en las europeas hasta poder decir si el mercado estaba cerrado, si Yahoo no
entregó la barra o si la perdimos nosotros, sin cuarto estado ambiguo y sin
excepciones por ticker; calendario nativo 24/7 para las tres criptos.

**PR 3 — calidad del dato.** Separar frescura, completitud reciente,
completitud histórica y disponibilidad de indicadores, con severidad por
antigüedad. Códigos estructurados de descarte, distinguiendo aviso de veto.

**PR 4 — estado real de ejecución.** El informe deja de llamar «precio actual»
al cierre de la víspera; reevaluación tras la apertura sin perseguir precio;
metadatos de instrumento y estado de broker, con el ISIN `DE000A0H08M3` de
`EXH1.DE`.

**PR 5 — informe y regresión.** El informe muestra por separado score, estado
del setup, estado de ejecución y los dos precios máximos de entrada. Siete
invariantes de integración. La fase 14 valida el filtro de ejecución aparte del
score y es la puerta a la línea A.

**Pendiente menor del PR 1.** Las fases 1 a 3 fueron a un solo commit en vez de
tres: son mutuamente dependientes —la capa de ejecución necesita la firma nueva
del dimensionamiento— y dividirlas dejaría commits intermedios que no compilan.

---

## Línea A — Modelo cuantitativo

Arranca cuando la línea 0 cierre. Antes, no.

### Cerrar P2 (bloqueada)

Rehacer P2.3 y P2.4 sobre la cosecha congelada, con la misma población y las
mismas reglas de observación, comparando contra lo antiguo: expectancy neta en
R, `P(target antes de stop)`, MAE, MFE, distribución por score, por región y por
activo. De P2.4 sale la decisión formal sobre si el beneficio/riesgo desaparece
del score: demostrada, no intuida.

### P3 — Score v2

Redefinir dimensiones y recalcular pesos, sin heredar los actuales. Normalizar
bien cuando falte una dimensión. Pregunta abierta: si `convicción`, que hoy mide
sobre todo cobertura del dato, debe salir del número y convertirse en
`score_signal` + `confidence`.

Calibrar umbrales por horizonte —swing y medio por separado, no 70/60 para
todo— con el estimador pre-registrado: media por bloque de la expectancy neta en
R, publicando siempre tasa agrupada y `P(objetivo antes de stop)`.

Desde aquí toda señal registra `score_model_version`. Nunca se mezclan
observaciones de reglas distintas sin etiquetar.

### P4 — Geometría

Stop: ATR, soporte, mixto, volatilidad adaptativa. Objetivos: de 1,5 a 3,5 ATR,
estructura e híbridos. Entrada: apertura siguiente, zona ideal, pullback,
entrada máxima. Ninguna variante se elige por su resultado agregado sin estudiar
heterogeneidad por mercado, región, volatilidad, régimen y score. P2.6 dejó el
aviso: la opción B mejora en promedio con dispersión alta.

Hereda del PR 1 la separación entre señal válida y precio aceptable, así que la
usa en vez de inventarla.

### P5 — Regiones robustas

Superficies de parámetros buscando mesetas, no picos. Descartar configuraciones
frágiles y las que dependen demasiado de un mercado concreto. La salida es un
conjunto pequeño de políticas candidatas.

### P6 — Sistema completo

Simulación del asesor como sistema: capital, posiciones simultáneas, ocupación,
riesgo agregado, exposición por región, divisa y sector, costes y slippage,
dividendos, cash y orden cronológico real de señales.

Métricas: CAGR, volatilidad, Sharpe, Sortino, max drawdown, Calmar, exposición
media, turnover, profit factor, R total y R por operación.

### P7 — Walk-forward y holdout

Desarrollo, validación y holdout final, con el holdout sin consultar durante la
calibración. Configuración congelada antes de cada ventana, con versión de
modelo y vintage de datos registrados. Si la ventaja no sobrevive fuera de
muestra, no se arregla el holdout: se vuelve a investigación.

### Recalibrar con los 107

Todo lo medido históricamente sale de 21 activos.

---

## Línea B — Contexto externo

Puede empezar ya: capturar y almacenar no toca ninguna decisión, así que no
contamina la validación de la línea A.

### El contrato point-in-time

Antes de descargar una sola noticia. `advisor/context/models.py` define la
procedencia de toda observación externa: `source`, `source_id`, `symbol`,
`observed_at`, `published_at`, `available_at`, `content_hash`,
`raw_payload_hash`, `provider`, y cuando aplique periodo fiscal, divisa y
revisión. Sin `available_at <= analysis_timestamp` demostrable, el dato no entra
en un backtest.

Estructura propuesta: `advisor/context/` con `models.py`, `collector.py`,
`provenance.py`, `news.py`, `sentiment.py`, `fundamentals.py` y `macro.py`. No
se instala TradingAgents como dependencia.

### Noticias

Collector propio: descarga por activo y macro, normalización de fechas,
deduplicación, asociación de símbolos y hash del contenido. El LLM no busca
noticias: recibe las ya obtenidas y devuelve `relevance`, `direction`,
`event_type`, `materiality` y `confidence`. No se convierten todavía en puntos
del score.

**Decisión pendiente:** quién filtra y con qué criterio. Los datos son gratis;
el problema medido es la relevancia.

### Sentimiento

Datos primero, LLM después. Guardar número de mensajes, bullish/bearish cuando
exista, engagement, fuente, timestamps y hash. La salida lleva banda, score,
confianza, tamaño de muestra y divergencia entre fuentes. Nunca entra
directamente en el score cuantitativo.

### Fundamentales y P8

La ampliación más delicada y la única brecha que no se cierra con trabajo.
Elegir proveedor por cobertura, histórico, point-in-time, Europa y coste —no
porque encaje con `yfinance`—, guardar magnitudes primarias con su fecha de
publicación y derivar los ratios en Python, nunca en el LLM.

Los 20 puntos no se activan solos: primero **P8 — Fundamentals Study**
determina qué métricas aportan información, con qué pesos, en qué horizonte y en
qué sectores. Mientras tanto la nota se normaliza sobre 80 y el ratio pesa 25 de
100 en vez de 20.

### Macro

Conservar el calendario Fed/BCE actual y ampliar con datos observables: tipos,
IPC, PCE subyacente, paro, curva, EUR/USD, petróleo, oro, DXY. FRED cubre parte
de EE.UU.; para Europa, BCE y Eurostat. Guardar vintage y revisión: muchos datos
macro cambian después de publicarse.

### Context Analyst

Un solo agente bien restringido, sin comité de agentes. Cinco preguntas
obligatorias: qué evidencia apoya la operación, qué la contradice, qué riesgo no
captura el modelo, si hay catalizador y si hay evento próximo. Salida
estructurada y validada con Pydantic.

### Shadow mode

El contexto no modifica ninguna operación. Se guardan `quant_decision` y
`context_shadow_decision` en paralelo, y la recomendación real sigue siendo la
cuantitativa.

Persistencia en SQLite: `context_observation`, `news_item`,
`sentiment_snapshot`, `fundamental_snapshot`, `macro_snapshot` y
`context_assessment`, relacionadas con `analysis_run_id`, `signal_id`, `symbol`
y `analysis_timestamp`.

### P9 — Context Study

Con muestra suficiente: quant solo frente a quant más noticias, sentimiento,
fundamentales, macro y combinaciones, con la misma disciplina que P2 —ablación,
block bootstrap, intervalos, regiones, heterogeneidad y holdout—. La pregunta no
es si parece útil, sino si mejora la expectancy fuera de muestra.

### Integración y Score v3

Solo si P9 demuestra valor, y de forma conservadora: el contexto puede degradar
una señal (`OPERAR → VIGILAR`) pero no rescatarla (`DESCARTAR → OPERAR`). La IA
no salva una señal cuantitativamente mala.

Score v3 no tiene por qué ser un único 0–100: puede ser más informativo y menos
falsamente preciso presentar score cuantitativo, sesgo fundamental, sentimiento,
riesgo de evento y confianza del dato por separado.

---

## En paralelo a todo lo anterior

- **89 ISIN de 107,** uno a uno contra fuente oficial, guardando procedencia y
  fecha de verificación. `yfinance` devuelve ISIN falsos que superan el dígito de
  control: un ISIN plausible no es un ISIN verificado.
- **Disponibilidad real en Trade Republic de los 107.** Hoy todos en `unknown` y
  no hay API. Guardar fecha de comprobación, instrumento exacto y mercado de
  ejecución cuando sea verificable. No modifica la señal, solo la
  ejecutabilidad.
- **Símbolos europeos.** Ningún activo declara `european_symbol`. Verificar
  ticker, plaza, divisa, liquidez y correspondencia con el activo.
- **Interpretar el histórico de frescura de la Pi.** Cuatro pasadas diarias de
  lunes a viernes desde el 2 de septiembre. Es la evidencia de recurrencia que
  decide si se paga otra fuente para Xetra y Euronext. **Sin verificar** que las
  filas estén ahí: la base local solo tiene las 107 de aquel día.
- **Desplegar el PR 1 en la Pi.** La verificación en la propia Pi es parte del
  despliegue, no un extra: es donde aparecieron tres de los últimos defectos.

---

## Menores, pero reales

- El **calendario macro de `events.yaml` caduca el 2027-12-16**. El bot avisa a
  60 días, pero conviene refrescarlo antes.
- **`^SOX`, `^RUT`, `^TNX`, `DX-Y.NYB`, `CL=F` y `GC=F` no alimentan el
  contexto**, que sigue puntuando solo con VIX, tendencia europea y sesión
  asiática.
- **`economic_currency` se guarda y no se usa.** Descomponer el ATR en riesgo de
  activo y de divisa es un cambio de cálculo, y hay que medirlo.
- **`market_for_symbol` clasifica como cripto cualquier símbolo con guion.** Hoy
  no rompe nada porque la plaza sale del universo, pero `BRK-B` caería en
  `CRYPTO` en cuanto alguien la use para un activo.
- **Los eventos no puntúan,** a propósito, hasta medir que mejoran las señales.
- **Memoria de resultados:** guardar por recomendación el desenlace, `net_R`,
  MAE, MFE, retorno del benchmark y alfa. El aprendizaje sale de la estadística;
  la reflexión del LLM, si existe, es secundaria.

---

## Qué hacer ahora, en este orden

1. **PR 2 — calendarios de mercado.** Incluye la investigación del hueco del
   07/09 hasta tener causa identificada y test, sin excepciones por ticker ni
   por fecha.
2. **PR 3 — calidad del dato,** separando frescura de completitud histórica y
   dando código de motivo a cada descarte.
3. **PR 4 y PR 5 — estado real de ejecución, informe e invariantes.** Con la
   fase 14 se cierra la línea 0 y el dato deja de moverse.
4. **Rehacer P2.3 y P2.4 una sola vez, y congelar P2** con sus hashes.
5. **P3 y Score v2,** con la decisión sobre el beneficio/riesgo ya tomada en
   P2.4 y los umbrales calibrados por horizonte.
6. **En paralelo desde hoy:** `advisor/context/models.py` y el contrato
   point-in-time, y empezar a almacenar noticias aunque todavía no afecten a
   ninguna decisión.
7. **P4 → P5 → P6 → P7,** en ese orden y sin saltarse la heterogeneidad.
8. **Sentimiento,** y resolver el proveedor de fundamentales para arrancar P8.
9. **Context Study (P9) antes de integrar nada** de la línea B en producción.
10. **Riesgo de cartera,** cuando el sistema individual esté validado:
    correlación entre posiciones, concentración por sector, geografía, factor y
    divisa, y máximos de riesgo diario y semanal.

---

## Definición de terminado

Se cumple cuando todo lo siguiente es cierto a la vez.

- **El modelo.** P2 corregido y congelado; Score v2 definido en P3; geometría
  validada en P4; parámetros robustos en P5; sistema probado en P6; resultado
  confirmado con walk-forward y holdout en P7.
- **El dato.** Calidad protegida en producción; noticias, sentimiento y macro
  almacenados point-in-time; fundamentales con proveedor fiable; universo
  operativo verificado.
- **El contexto.** Context Layer en shadow mode; valor medido en P9; solo entran
  en producción las variables que demuestren ventaja.
- **La auditoría.** Cada recomendación es auditable y cada señal reconstruible;
  ningún LLM altera cálculos en silencio; producción sigue funcionando aunque
  falle la IA.
- **La operación.** Riesgo de cartera controlado; tests, `ruff` y `mypy`
  limpios; sin diferencias entre la Pi y GitHub; backups, migraciones, logs
  rotados, alertas, timeouts y degradación limpia si cae un proveedor.
