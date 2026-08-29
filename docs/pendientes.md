# Pendientes del asesor

Estado al **29 de agosto de 2026**. P0 y P1 están en `main`; P2.1 y P2.2 están
implementadas y verificadas.

Cada punto dice qué falta, por qué importa y qué hay que decidir antes de
tocarlo. Orden dentro de cada bloque: lo que más cambia el resultado, primero.

## Lo que ya está hecho (para no repetir trabajo)

- Universo de **126 instrumentos** (107 analizables + 19 de contexto), con los
  126 símbolos verificados uno a uno contra el proveedor de datos.
- Modelo de doble símbolo, `economic_currency`, `broker`/`execution_mode`,
  `requires_isin`, clase `commodity_etc` y región `EMERGING_MARKETS`.
- Calendario de eventos (`advisor/events/`): Fed y BCE curados + resultados
  del proveedor, ya visibles en el informe y como riesgo cuando son inminentes.
- Desplegado en la Pi con cuatro pasadas diarias (07:00, 08:30, 14:30 y 21:00,
  hora local de la Pi, UTC+1), de lunes a viernes.
- **P0 — dimensionamiento por riesgo.** El tamaño sale del
  presupuesto de riesgo y de la distancia al stop, no de la convicción:
  `position_pct = risk_per_trade_pct / risk_pp`, con tope `max_position_pct`
  que informa de cuánto sería sin él. `advisor/analysis/sizing.py` es puro y
  adimensional; las acciones y los euros se calculan en la capa de informe,
  que es donde vive `FxConverter`. Sin tipo de cambio para una divisa (KRW,
  CNY) no se inventa un número de acciones. La etiqueta de convicción se
  conserva como información y **no** dimensiona.
- **P1 — benchmark por activo.** La fortaleza relativa ya no
  compara Apple ni Toyota contra el Euro Stoxx 50. Precedencia: campo
  `benchmark` del activo → mercado → región → `benchmark_symbol` global. El
  criterio es exposición económica, no plaza de cotización. Cripto y
  `EMERGING_MARKETS` resuelven a «sin comparable», que excluye el factor del
  reparto en vez de penalizar. TSM usa `^TWII` e INFY `null` por declaración
  explícita en `universe.yaml`.

## En curso

### P2 — Infraestructura de investigación

Ver **`docs/protocolo-investigacion.md`**, que es ahora la especificación que
gobierna cualquier medición futura. Está acordado y **sin implementar**.

El cambio de encuadre importa: hasta ahora se pensaba que el trabajo pendiente
era mejorar la estrategia. Al revisar qué puede concluir el backtest actual
aparecieron varios sesgos que comparten raíz, así que primero hay que
construir un laboratorio fiable. Si el laboratorio mide mal, cada iteración
posterior tendrá más capacidad de encontrar artefactos que de encontrar
ventaja.

Fases: P2.0 congelar datos · P2.1 contrato numérico · P2.2 instrumentación de
señal y vectorización causal · P2.3 event study · P2.4 ablación del score ·
P2.5 capacidad estadística · P2.6 infraestructura de incertidumbre.

**Hechas: P2.1 y P2.2.** Unidades con la unidad en el nombre (`risk_pp`,
`gross_return_pp`, `net_r_multiple`), evaluación económica en R neto,
expectancy / profit factor / payoff / mediana / percentiles / dispersión por
tramo de puntuación, y el redondeo movido del cálculo a la presentación.
`SignalObservation` guarda insumos primitivos y componentes numéricos, nunca
niveles derivados. Los indicadores se calculan una vez sobre la serie completa
y se indexan por barra, con un test de equivalencia contra el camino por
prefijos que cubre cuatro configuraciones de benchmark y un caso negativo de
look-ahead deliberado.

**Siguiente: P2.0**, con la decisión ya tomada — descarga con
`auto_adjust=False` y `actions=True`, tres vistas derivadas y
`data_vintage_id` a dos niveles. Ver el protocolo.

---

## 1. El ratio beneficio/riesgo no mide lo que dice medir

**No tocar hasta P4.** Está medido y documentado, pero cambiarlo ahora sería
cambiar la estrategia sin evidencia.

Tres hechos verificados:

- Con `target2_structural: false` el ratio vale 1,5 por construcción, salvo
  que un soporte cercano acerque el stop, en cuyo caso *sube*. La dimensión de
  20 puntos premia estar cerca del mínimo de 60 sesiones mientras el resto del
  score premia rupturas: dos tesis opuestas sumando a la misma nota.
- El ratio se calcula sobre el precio de señal, pero se admite comprar hasta
  `precio + 0,75·ATR`. A ese precio el ratio real cae a 0,82:1.
- Exigir `RR ≥ 1,5` en el precio real de ejecución da `E ≤ P` exactamente:
  `entry_max_atr` quedaría muerto y solo entrarían pullbacks. Para tolerar
  0,75·ATR conservando 1,5 harían falta objetivos de 4,875·ATR, por encima del
  objetivo 3 actual.

Es decir, corregir el ratio y decidir la geometría son la misma decisión.
Detalle en `docs/ratio-beneficio-riesgo.md` y en el protocolo.

## 2. Pasadas por evento

El asesor ya sabe qué días hay Fed, BCE o resultados de un activo del
universo. Falta que se despierte solo esos días, que es lo que se pidió desde
el principio. Sigue desbloqueado y sin depender de P2.

**Qué hay que decidir:** si la pasada extra es un temporizador fijo adicional
que se autodescarta cuando no hay eventos (simple, robusto), o un temporizador
que se reprograma según el calendario (elegante, más frágil). Recomendación:
lo primero.

**Cuidado con:** el calendario macro de `events.yaml` caduca el **2027-12-16**.
El bot avisa solo cuando quedan menos de 60 días, pero conviene refrescarlo
antes desde las fuentes que el propio fichero declara.

## 3. Fundamentales (§9) — la única pieza que cuesta dinero

Sigue sin fuente. Mientras tanto la dimensión se excluye y la nota se
normaliza sobre 80, de modo que **el ratio beneficio/riesgo pesa hasta 25
puntos de 100** en vez de 20. Y si P3 saca además el RR del score, la nota
real se calcularía sobre 60 puntos evaluables de 100, lo que obliga a
recalibrar los umbrales en vez de heredarlos.

**Qué hay que decidir:** proveedor y coste. Es la brecha más cara.

## 4. Noticias (§7)

Disponibles y gratis en yfinance, con titular, medio, fecha y URL, y cubren
también Japón. **El problema medido es la relevancia**: de tres noticias de
NVDA, dos eran relleno de Motley Fool, y una de las de SAP hablaba en realidad
de Accenture.

**Qué hay que decidir:** si el filtro lo hace el agente de Anthropic que ya
está conectado (coste por informe, no por activo) y con qué criterio se
descarta una noticia. Meterlas sin filtrar empeoraría el informe.

## 5. Los eventos todavía no puntúan

Deliberado. Que los eventos mejoran las señales es exactamente el tipo de
afirmación que en este proyecto se mide antes de creérsela — y ahora, además,
con el protocolo de investigación por delante.

## 6. `economic_currency` se guarda pero no se usa

El campo existe en los 126 activos, pero hoy solo se imprime. La motivación
original era usarlo en **stops, volatilidad y correlaciones**: comprar Apple
en euros en Xetra no elimina el riesgo dólar.

**Qué hay que decidir:** si descomponer el ATR en riesgo del activo y riesgo
de divisa merece la pena. No es un cambio de metadatos, es un cambio de
cálculo, y hay que medirlo.

## 7. El doble símbolo está a medias

El modelo soporta `european_symbol`, pero **ningún activo lo declara** y el
análisis siempre usa `primary_symbol`. Falta lo que le daba sentido: elegir
la cotización según la sesión (Xetra por la mañana, Nasdaq por la tarde).

**Cuidado con:** no inventar tickers de Xetra. Hay que verificarlos con datos
reales, uno a uno, como se hizo con los 126.

## 8. ISIN: faltan 89 de 107

Solo hay 18 verificados. **No se pueden rellenar automáticamente**: yfinance
devuelve ISIN falsos que superan el dígito de control Luhn (daba
`AR0725224551`, de Argentina, para ASML, y `CA50244Q1037`, de Canadá, para
LVMH). Un ISIN inventado que valida es peor que ninguno.

**Cómo hacerlo:** Deutsche Börse (`live.deutsche-boerse.com/equity/<empresa>`)
y Euronext (`live.euronext.com/en/product/equities/<ISIN>-<MIC>`) respondieron
bien y son fuentes primarias.

## 9. Disponibilidad en Trade Republic: los 107 están en `unknown`

No hay API pública del catálogo. El informe lo marca con
"⚠️ PENDIENTE DE VERIFICACIÓN", que es el comportamiento correcto, pero
significa que **ninguna recomendación está confirmada como ejecutable**.

**Decisión tomada:** *no* degradar `unknown` a VIGILAR. Con 107 de 107 en
`unknown` eso inutilizaría el sistema. Lo correcto es separar dos conceptos
que hoy se mezclan —calidad de la señal y ejecutabilidad en el broker— para
que el informe pueda decir «🟢 OPERAR, disponibilidad ❓ pendiente» sin
afirmar nunca «COMPRAR AHORA EN TRADE REPUBLIC» antes de verificarlo.

## 10. Cosas menores pero reales

- **`mypy` no se puede ejecutar**: `pyproject.toml` fija
  `python_version = "3.9"` y el mypy instalado exige >=3.10. Hay que decidir
  si el proyecto sube a 3.10+ (la Pi ya va con 3.13) o si el venv baja. Es un
  gate de calidad caído, no un fallo de código.
- **`capital:` sigue vacío en `config.yaml`**, a propósito: sin cifra el
  informe muestra solo porcentajes, que es el comportamiento deseado hasta que
  se configure expresamente. Falta añadir tests del sizing con capital
  sintético (10.000 / 50.000 / 100.000) en vez de poner una cifra ficticia en
  producción para ejercitarlo.
- **Resuelto en P2.2**: `_signal()` ya no recalcula los indicadores sobre
  `df.iloc[:j+1]` en cada barra. El camino por prefijos se conserva como
  `_signal_prefix()` porque es la referencia contra la que se comprueba la
  causalidad; no lo borres.
- **`510300.SS` es un ETF, no el índice CSI 300**: se usa como referencia
  porque el índice no trae histórico. Está anotado en el universo. No se
  autocompara consigo mismo porque es `analizable: false`.
- **El grupo `contexto` tiene 19 referencias** (^SOX, ^RUT, ^TWII,
  EURUSD=X, CL=F...) de las que solo algunas se usan como benchmark tras P1.
  El **contexto de mercado** sigue puntuando solo con VIX, tendencia europea y
  sesión asiática: ^SOX, ^RUT, ^TNX, DX-Y.NYB, CL=F y GC=F no alimentan
  todavía la puntuación.
- **Opción B del ratio** (objetivo 2 a 3,5·ATR): medida, mejora leve, sin
  decidir. Absorbida por P4. Ver `docs/ratio-beneficio-riesgo.md`.
- **El backtest se calibró con 21 activos, no con 107**: todo lo medido sale
  de `europa`, `usa_en_xetra` y `etfs_ucits` del universo viejo. Rehacerlo
  forma parte de P2 y siguientes, ya bajo el protocolo.
