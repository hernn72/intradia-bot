# Pendientes del asesor

Estado al **29 de agosto de 2026**, tras el commit `e952f71`. Cada punto dice
qué falta, por qué importa y qué hay que decidir antes de tocarlo.

Orden dentro de cada bloque: lo que más cambia el resultado, primero.

## Lo que ya está hecho (para no repetir trabajo)

- Universo de **126 instrumentos** (107 analizables + 19 de contexto), con los
  126 símbolos verificados uno a uno contra el proveedor de datos.
- Modelo de doble símbolo, `economic_currency`, `broker`/`execution_mode`,
  `requires_isin`, clase `commodity_etc` y región `EMERGING_MARKETS`.
- Calendario de eventos (`advisor/events/`): Fed y BCE curados + resultados
  del proveedor, ya visibles en el informe y como riesgo cuando son inminentes.
- Desplegado en la Pi con cuatro pasadas diarias (07:00, 08:30, 14:30 y 21:00,
  hora local de la Pi, UTC+1), de lunes a viernes.

---

## 1. Siguiente paso natural: pasadas por evento

El asesor ya sabe qué días hay Fed, BCE o resultados de un activo del
universo. Falta que se despierte solo esos días, que es lo que se pidió desde
el principio.

**Qué hay que decidir:** si la pasada extra es un temporizador fijo adicional
que se autodescarta cuando no hay eventos (simple, robusto), o un temporizador
que se reprograma según el calendario (elegante, más frágil). Recomendación:
lo primero.

**Cuidado con:** el calendario macro de `events.yaml` caduca el **2027-12-16**.
El bot avisa solo cuando quedan menos de 60 días, pero conviene refrescarlo
antes desde las fuentes que el propio fichero declara.

## 2. Noticias (§7)

Disponibles y gratis en yfinance, con titular, medio, fecha y URL, y cubren
también Japón. **El problema medido es la relevancia**: de tres noticias de
NVDA, dos eran relleno de Motley Fool, y una de las de SAP hablaba en realidad
de Accenture.

**Qué hay que decidir:** si el filtro lo hace el agente de Anthropic que ya
está conectado (coste por informe, no por activo) y con qué criterio se
descarta una noticia. Meterlas sin filtrar empeoraría el informe.

## 3. Fundamentales (§9) — la única pieza que cuesta dinero

Sigue sin fuente. Mientras tanto la dimensión se excluye y la nota se
normaliza sobre 80, de modo que **el ratio beneficio/riesgo pesa hasta 25
puntos de 100** en vez de 20. Eso ya tuvo consecuencias medidas: es la razón
de que bajar `min_rr_ratio` no rescatara la opción D.

**Qué hay que decidir:** proveedor y coste. Es la brecha más cara.

## 4. Los eventos todavía no puntúan

Deliberado. Que los eventos mejoran las señales es exactamente el tipo de
afirmación que en este proyecto se mide con el backtest antes de creérsela.

**Antes de tocarlo:** medir en 2y y 5y, y en un grupo fuera de muestra.

## 5. `economic_currency` se guarda pero no se usa

El campo existe en los 126 activos, pero hoy solo se imprime. La motivación
original era usarlo en **stops, volatilidad y correlaciones**: comprar Apple
en euros en Xetra no elimina el riesgo dólar.

**Qué hay que decidir:** si descomponer el ATR en riesgo del activo y riesgo
de divisa merece la pena. No es un cambio de metadatos, es un cambio de
cálculo, y hay que medirlo.

## 6. El doble símbolo está a medias

El modelo soporta `european_symbol`, pero **ningún activo lo declara** y el
análisis siempre usa `primary_symbol`. Falta lo que le daba sentido: elegir
la cotización según la sesión (Xetra por la mañana, Nasdaq por la tarde).

**Cuidado con:** no inventar tickers de Xetra. Hay que verificarlos con datos
reales, uno a uno, como se hizo con los 126.

## 7. ISIN: faltan 89 de 107

Solo hay 18 verificados. **No se pueden rellenar automáticamente**: yfinance
devuelve ISIN falsos que superan el dígito de control Luhn (daba
`AR0725224551`, de Argentina, para ASML, y `CA50244Q1037`, de Canadá, para
LVMH). Un ISIN inventado que valida es peor que ninguno.

**Cómo hacerlo:** Deutsche Börse (`live.deutsche-boerse.com/equity/<empresa>`)
y Euronext (`live.euronext.com/en/product/equities/<ISIN>-<MIC>`) respondieron
bien y son fuentes primarias.

## 8. Disponibilidad en Trade Republic: los 107 están en `unknown`

No hay API pública del catálogo. El informe lo marca con
"⚠️ PENDIENTE DE VERIFICACIÓN", que es el comportamiento correcto, pero
significa que **ninguna recomendación está confirmada como ejecutable**.

## 9. El backtest se calibró con 21 activos, no con 107

Todo lo medido (ordenación de la nota, aportación de los vetos, opciones B, C
y D del ratio) sale de `europa`, `usa_en_xetra` y `etfs_ucits` del universo
viejo. Con 107 activos y grupos nuevos, conviene rehacerlo.

**Pendiente además, de antes:** walk-forward, horizonte `medio` y algún
régimen bajista.

## 10. Cosas menores pero reales

- **`mypy` no se puede ejecutar**: `pyproject.toml` fija
  `python_version = "3.9"` y el mypy instalado exige >=3.10. Hay que decidir
  si el proyecto sube a 3.10+ (la Pi ya va con 3.13) o si el venv baja. Es un
  gate de calidad caído, no un fallo de código.
- **Opción B del ratio** (objetivo 2 a 3,5·ATR): medida, mejora leve, sin
  decidir. Ver `docs/ratio-beneficio-riesgo.md`.
- **`510300.SS` es un ETF, no el índice CSI 300**: se usa como referencia
  porque el índice no trae histórico. Está anotado en el universo.
- **El grupo `contexto` tiene 19 referencias nuevas** (^SOX, ^RUT, ^TWII,
  EURUSD=X, CL=F...) que **todavía no alimentan la puntuación**: el contexto
  sigue puntuando solo con VIX, tendencia europea y sesión asiática.
