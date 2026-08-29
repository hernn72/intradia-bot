# Cobertura de la especificación

Contraste entre las 27 secciones de la especificación del asesor y lo que
hay construido. Verificado contra el código el 2026-08-27.

Leyenda: **✅** implementado · **◐** parcial · **✗** ausente

## Resumen

| # | Sección | Estado | Nota |
|---|---|:--:|---|
| 1 | Rol y horizontes | ◐ | 3 horizontes (intradía/swing/medio). El «corto plazo 1-10 sesiones» queda absorbido por swing |
| 2 | Restricción Trade Republic | ◐ | ISIN validado con Luhn, `trade_republic: yes/no/unknown`, marca ⚠️ PENDIENTE. **Falta** buscar sustituto (acción equivalente / ETF / empresa con el mismo catalizador) |
| 3 | Listón del 2,25 % libre de riesgo | ✅ | En el horizonte medio, un potencial que no supere `2,25% × risk_free_multiple` baja a VIGILAR (2026-08-27) |
| 4 | Filosofía (calidad > número) | ✅ | «NO OPERAR / MANTENER LIQUIDEZ» y «no perseguir precio» implementados como vetos reales |
| 5 | Análisis secuencial de mercados | ◐ | La sesión asiática ya puntúa en el contexto (2 de 10 puntos) y un desplome aparece en el motivo (2026-08-27). Bonos, divisas y materias primas siguen fuera |
| 6 | Macroeconomía | ✗ | Sin fuente de datos macro ni de calendario |
| 7 | Noticias y catalizadores | ✗ | Sin fuente de noticias |
| 8 | Calendario de resultados | ✗ | No existe |
| 9 | Análisis fundamental | ✗ | Sin fuente. La dimensión se excluye del cómputo y la nota se normaliza sobre 80 |
| 10 | Análisis técnico | ✅ | EMA 20/50, SMA 200, RSI, MACD, ATR, volumen, gaps, soportes/resistencias, fortaleza relativa |
| 11 | Clasificación de oportunidades | ◐ | Los tres tipos existen. Pero §11 exige para intradía un catalizador claro entre cinco (resultados, noticia, gap, volumen, ruptura) y solo se detectan **tres**: los que dejan huella en el precio |
| 12 | Puntuación 0-100 | ◐ | Las 6 dimensiones existen; la fundamental (20 pts) está excluida |
| 13 | Probabilidad y escenarios | ◐ | Los tres escenarios se describen; **sin probabilidades**, por decisión explícita: no se estima lo que no se ha medido |
| 14 | Entrada | ✅ | Precio actual, zona ideal, entrada máxima y veto «ESPERAR PULLBACK» |
| 15 | Objetivos | ✅ | Tres objetivos con potencial porcentual |
| 16 | Stop e invalidación | ✅ | Distingue stop de precio de invalidación de la tesis; basado en estructura y ATR |
| 17 | Ratio beneficio/riesgo | ◐ | Calculado, pero sigue siendo casi una constante. La opción que atacaba la raíz (objetivo 2 estructural) se midió el 2026-08-29 y empeora el resultado: el problema está en la definición de resistencia, no en el ratio. Ver `docs/ratio-beneficio-riesgo.md` |
| 18 | Gestión de cartera | ✗ | Sin concentración sectorial, geográfica, correlación ni exposición a divisa |
| 19 | Dimensionamiento | ✅ | Los tres tramos (5-10 % / 2-5 % / 0,5-2 %), ajustados por volatilidad |
| 20 | Prohibiciones | ✅ | No inventa: lo que no tiene fuente sale como `N/D` |
| 21 | Fuentes | ◐ | Única fuente: yfinance (precio y volumen). Sin Reuters/Bloomberg/FT ni comunicaciones oficiales |
| 22 | Radar de tres listas | ✅ | 🟢 OPERAR / 🟡 VIGILAR / 🔴 DESCARTAR |
| 23 | Formato de la recomendación | ◐ | Completo salvo **«Próximo evento importante»**, que depende de §8 |
| 24 | Resumen diario | ◐ | Faltan bonos, divisas, materias primas, «⚠️ EVENTOS IMPORTANTES HOY», «📅 PRÓXIMOS CATALIZADORES» y «💼 CARTERA» |
| 25 | Seguimiento de posiciones | ✅ | Los cuatro veredictos (REFUERZA / NO CAMBIA / DEBILITA / INVALIDA) contra la tesis original |
| 26 | Búsqueda proactiva | ✗ | Universo fijo de 28 activos escritos a mano; no escanea el mercado |
| 27 | Principio final | ◐ | Ya es verificable: el motor de `advisor/backtest/` midió esperanza positiva y ordenación por nota en tres cortes (2026-08-27). Verificado ≠ garantizado |

**Recuento:** 10 ✅ · 12 ◐ · 5 ✗ *(actualizado 2026-08-27; original: 9 · 11 · 7)*

## Las tres brechas

Lo ausente no está repartido al azar: se concentra en tres huecos que
explican la distancia entre lo construido y lo pedido.

### Brecha 1 — Asia se mira pero no se usa — **CERRADA (2026-08-27)**

La media de la sesión asiática (`asia_session_change`) entra ahora en
`MarketContext`: 2 de los 10 puntos de contexto (4 tendencia + 4 VIX + 2
Asia), con neutralidad cuando falta el dato y mención en el motivo cuando la
sesión cae más de un 1,5%. No convierte el contexto en hostil por sí sola:
el veto sigue siendo VIX + tendencia, que es lo que el backtest midió como
aportación positiva.

### Brecha 2 — El bot ve el qué, no el porqué

Secciones 6, 7, 8, 9 y 26. El bot detecta la **huella** de un catalizador en
el precio (volumen anormal, hueco, ruptura) pero nunca su **causa**. No sabe
si un hueco del +4 % es por unos resultados, por una adquisición o por ruido.

Esto tiene una consecuencia que la especificación señala como decisiva. §26
pide responder a tres preguntas ante un acontecimiento, «la tercera es la más
importante»:

> ¿Todavía existe una oportunidad negociable o el mercado ya la ha descontado?

El bot **no puede responderla**, porque no sabe qué ha ocurrido. Solo ve que
el precio se movió. Y §4 advierte justamente contra confundir una noticia
positiva con una oportunidad de compra.

Cerrar esta brecha exige una fuente de datos nueva (noticias, resultados,
calendario macro, fundamentales) y es, con diferencia, el mayor trabajo.

### Brecha 3 — Nada demuestra que gane dinero — **CERRADA en su núcleo (2026-08-27)**

El motor de `advisor/backtest/` reproduce las señales del asesor sobre el
pasado sin mirar el futuro y mide tres cosas: la política real, la
ordenación por tramos de nota y la aportación de los vetos. Primeros
resultados (swing, coste 0,2% ida y vuelta):

| Corte | Política real | ¿Ordena la nota? (≥70 vs <60) |
|---|---|---|
| europa 2y | 20 ops, +0,42%/op | +2,71% vs +0,36% |
| europa 5y | 75 ops, +0,34%/op | +1,51% vs +0,43% |
| usa_en_xetra 5y *(fuera de muestra)* | 143 ops, +1,87%/op, 52% aciertos | +1,70% vs +0,05%, monótona en los 5 tramos |

Dos matices que el informe imprime siempre: comprar y mantener rindió más en
este mercado alcista (el asesor solo está en mercado ~10-16 velas por
operación), y resultados pasados no garantizan nada. Queda pendiente el
walk-forward y medir el horizonte `medio`.

## Qué es decisión y qué es defecto

**Defectos** — ambos corregidos el 2026-08-27:

- ~~`risk_free_annual_pct` declarado y nunca leído (§3)~~ → veto de
  horizonte medio.
- ~~El buffer del stop por soporte~~ → `compute_levels` ya no permite que el
  soporte aleje el stop.

**Decisiones pendientes** (requieren elegir rumbo, coste y fuente de datos):

- Cerrar la brecha 2: qué fuente de noticias/fundamentales, con qué coste.
- Ampliar el backtest: walk-forward, horizonte `medio`, más grupos y
  regímenes bajistas.
- Bonos, divisas y materias primas del resumen diario (§24).
