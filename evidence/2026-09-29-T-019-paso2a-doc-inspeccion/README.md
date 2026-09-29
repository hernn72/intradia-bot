# T-019 paso 2a-doc — contexto point-in-time y población de P3 — 2026-09-29

**Estado: CERRADO.** Hubo una primera inspección, que se detuvo en
OWNER_DECISION_REQUIRED (hechos H1–H6 de abajo). Después el propietario
decidió **D-50 a D-57**, y con eso se hizo el censo de la población (`06`). El
commit que contiene esta carpeta es el **pre-registro completo y ejecutable de
P3**.

    rama        research/a03-score-v2 (base main = db51d67)
    cosecha     071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841
    universo    237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19 (93 analizables)
    score       score_model_version 1.0 activo; v2 aún no existe en código
    no se miró  ningún desenlace, expectancy, precio posterior a la señal ni score

Los guiones `*.py` se ejecutan desde la raíz del repo con
`PYTHONPATH=. .venv/bin/python evidence/…/NN-….py [carpeta de salida]`. Solo
leen calendarios del repo, universo, configuración y cosecha. En `06`,
`evaluate_managed_event` y `evaluate_potential_event` se sustituyen por
funciones que devuelven `None`: la población se reproduce **sin calcular
ningún desenlace**. Aun así sale exacta la de A-02 (106.363 swing y 94.273
medio, 0 saltados), lo que confirma que la población no depende del score ni
del resultado.

| fichero | qué contiene |
|---|---|
| `01-estado-de-plazas-por-pasada.*` | estado de cada serie de contexto a cada hora de pasada, en verano y en invierno |
| `02-pasadas-reales-de-produccion.txt` | horas reales de las pasadas (copia de solo lectura de la base de la Pi) |
| `03-alineacion-laboratorio-muestra.*` | qué VIX y qué tendencia asigna hoy `_align` a barras concretas |
| `04-alineacion-laboratorio-cosecha.*` | el defecto H6 contado sobre toda la cosecha |
| `05-materia-prima-cosecha.txt` | forma e índice de las barras de las series de contexto |
| `06-censo-poblacion-y-contexto.*` | población de P3: `analysis_timestamp` T-A, exclusiones como unión por observación y sha256 de la población final |
| `06-excluded_crypto-{swing,medio}.tsv` | observaciones excluidas por D-51 |
| `06-excluded_asia_missing-{swing,medio}.tsv` | observaciones excluidas por D-52, con serie, motivo y sesión ausente |
| `06-excluded_trend_sma_history-{swing,medio}.tsv` | observaciones excluidas por D-55 (`NO_CALCULABLE_CONTEXT_HISTORY`), con los cierres disponibles |
| `06-stoxx_hueco_intermedio-{swing,medio}.tsv` | observaciones de la población con hueco puntual de `^STOXX50E` (D-56): sesión exigible, sesión usada y antigüedad |
| `07-ocupacion-de-bloques.*` | señales por bloque P2.5, en A-02 y en P3 |

## Hechos comprobados

**H1 — Producción genera la señal swing cuatro veces por día laborable.**
`intradia-bot.timer` programa las pasadas a las 07:00, 08:30, 14:30 y 21:00
en **hora local de la Pi, que es Europe/London**. Las pasadas reales de la
base (`02`) están a las 06:00, 07:30, 13:30 y 20:00 UTC en horario de verano,
11 de cada. La pasada por evento de las 22:30 se autodescarta: no hay ninguna
persistida. Todas las pasadas analizan swing, y ningún contrato dice cuál de
ellas es «la» observación de una señal.

**H2 — La señal asiática de producción es intradía en las pasadas de la mañana.**
`fetch_overview` toma `Close.iloc[-1]` frente a `iloc[-2]` de un histórico de
`1mo`/`1d` **sin `trim_unclosed_bar`** (`overview.py`), y
`asia_session_change` promedia las series `region: ASIA` de
`context_assets_of`, que son `510300.SS`, `^HSI`, `^KS11`, `^N225` y `^TWII`.
Con los calendarios del repo (`01`):

| pasada (Londres) | verano (UTC) | abiertas en ese instante | invierno (UTC) | abiertas en ese instante |
|---|---|---|---|---|
| 07:00 | 06:00 | 510300.SS, ^HSI, ^KS11, ^N225 | 07:00 | 510300.SS, ^HSI |
| 08:30 | 07:30 | ^HSI | 08:30 | ninguna |
| 14:30 | 13:30 | ninguna | 14:30 | ninguna |
| 21:00 | 20:00 | ninguna (sesión del día cerrada) | 21:00 | ninguna |

**H3 — La cosecha solo tiene barras diarias.** Las cinco series están, con
índice en la medianoche local de la sesión expresada en UTC (`05`). No existe
el valor intradía que ve una pasada con la plaza abierta.

**H4 — El universo es multiplaza.** Hay 93 analizables: 28 en XETRA, 24 en
NASDAQ, 16 en NYSE, 6 en PAR, 6 en JPX, 3 en MCE, 3 en HKG, 3 en CRYPTO, 2 en
AMS y 2 en MIL. La pasada que sigue al cierre de la barra de señal, o la que
precede a la apertura de entrada, **depende de la plaza**. Para CRYPTO, el
cierre de la barra `d` (00:00 UTC) coincide con la apertura de `d+1`, así que
ninguna pasada programada cae entre las dos.

**H5 — VIX en producción.** `fetch_market_context` usa `trim_unclosed_bar` con
`market_for_symbol("^VIX") = "NYSE"` (XNYS, cierre 16:00 ET) y
`settlement_minutes = 20`. En la práctica, admite la sesión del VIX a partir de
las 16:20 ET. El cálculo oficial del VIX termina a las **16:15 ET** (Cboe), así
que esa regla nunca admite un VIX abierto, pero solo porque el margen de
asentamiento es de 15 minutos o más. El universo declara `^VIX` con
`primary_market: CBOE`, que no existe en `MARKET_SESSIONS`; producción no lo
usa porque resuelve la plaza por símbolo.

**H6 — El laboratorio desalinea el VIX y la tendencia.** `event_study._align`
y `runner._align` normalizan con `_naive_dates`, que quita la zona **en UTC**.
Una barra europea o asiática, cuya medianoche local cae el día anterior en UTC,
queda etiquetada un día antes, mientras que el VIX (05:00Z) conserva su fecha.
Recuento sobre toda la cosecha (`04`; muestra en `03`):

| plazas | tendencia `^STOXX50E` de una sesión **posterior** a la barra | VIX asignado |
|---|---|---|
| NASDAQ / NYSE | **78 %** de las barras (look-ahead) | sesión anterior, como pretende `shift(1)` |
| CRYPTO | **69 %** (look-ahead) | sesión anterior, o la misma fecha en fin de semana |
| XETRA, PAR, AMS, MCE, MIL, JPX, HKG | 0 % | casi siempre **dos** sesiones atrás, no una |

El laboratorio no pasa ningún dato asiático a `build_market_context`, y
`MarketContext.points` puntúa entonces Asia con el neutro 1,0. Eso es una
imputación, no una reconstrucción. La ficha ya lo decía, y aquí queda
confirmado.

## Decisiones del propietario (2026-09-29)

- **D-50:** `analysis_timestamp` es T-A, la última pasada programada
  estrictamente anterior a la apertura de entrada `d+1`.
- **D-51:** cripto sale de P3.
- **D-52:** Asia se calcula con sesiones cerradas, las cinco series y sin
  imputar; un hueco del proveedor excluye la observación.
- **D-53:** VIX y tendencia son point-in-time, con una sola función de
  contexto; el defecto H6 queda registrado y la evidencia de A-02 no se toca.
- **D-54:** cinco cierres reales de plaza cuentan como festivos.
- **D-55:** si falta historia para la SMA200, la observación se excluye
  (`NO_CALCULABLE_CONTEXT_HISTORY`).
- **D-56:** un hueco puntual de `^STOXX50E` usa el último cierre causal
  disponible y no excluye.
- **D-57:** la familia Bonferroni tiene `m = 20`.

Texto completo en `docs/decision-log.md`. Reglas en T-019, sección
«Contexto: paridad y point-in-time».

## Censo (06 y 07)

La población se calcula como la **unión** de los motivos, observación por
observación; no se restan cifras.

| | swing | medio |
|---|---|---|
| población de A-02 (93 activos) | 106.363 | 94.273 |
| `excluded_crypto` (D-51) | 5.112 | 4.722 |
| `excluded_asia_missing` (D-52) | 396 | 218 |
| `excluded_trend_sma_history` (D-55) | 6.937 | 0 |
| de ellas, Asia ∩ SMA200 | 176 | 0 |
| **exclusiones, unión deduplicada** | **12.269** | **4.940** |
| **población de P3 (90 activos, 5 regiones)** | **94.094** | **89.333** |
| bloques con señales (A-02 → P3) | 21 → 19 | 5 → 5 |
| hueco puntual de `^STOXX50E` en la población (D-56; 1, 3 o 4 días) | 1.406 | 1.312 |
| hueco de VIX | 0 | 0 |

- Ninguna observación no cripto se queda sin pasada entre
  `available_at(d)` y la apertura de `d+1`.
- **Por región en swing:**

  | ASIA | EUROPA | USA | GLOBAL | EMERGING_MARKETS |
  |---|---|---|---|---|
  | 16.719 | 32.118 | 41.730 | 2.459 | 1.068 |
- **sha256 de la población**, sobre la lista ordenada «activo, sesión de
  señal»:
  - swing: `4aa12d85eb54d7a01c10a4a3e4cf04e8077c842829235a93b75f7bd19c62011a`
  - medio: `4d6eaab9b84ff23bade1df86a82e95f46da546917a226dc8438a8e88493020f8`
- **Bloques.** La espina no cambia: 22 bloques en swing, el último de 42
  sesiones, y 5 en medio, el último de 102. En swing, el bloque 1 lo vacía D-51,
  porque solo tenía señales cripto, y el 2, D-55. El desglose por motivo está en
  `07`.

**Fuentes de los cierres verificados:**
- XHKG 2023-09-01, tifón Saola: [CNBC](https://www.cnbc.com/2023/09/01/asia-markets-set-to-fall-as-traders-await-chinese-factory-reading.html).
- XHKG 2023-09-08, lluvia negra: [HKEX](https://www.hkex.com.hk/News/Market-Communications/2023/230908news?sc_lang=en) y [SCMP](https://www.scmp.com/business/markets/article/3233800/hong-kong-halts-stock-derivative-trading-black-rainstorm-warning-imposes-second-weather-disruption).
- XTAI 2024-10-31, tifón Kong-rey: [Bloomberg](https://www.bloomberg.com/news/articles/2024-10-31/taiwan-braces-for-super-typhoon-kong-rey-after-shutting-exchange).
- XTAI 2026-07-10, tifón Bavi: [Bloomberg](https://www.bloomberg.com/news/articles/2026-07-10/taiwan-suspends-stock-trading-and-shuts-schools-as-typhoon-nears) y [Reuters vía TradingView](https://www.tradingview.com/news/reuters.com,2026:newsml_L1N43B0EB:0-taiwan-s-financial-markets-to-close-on-friday-due-to-typhoon-bavi/).
- XTAI 2023-01-18, sin negociación antes del Año Nuevo Lunar: [calendario oficial de la TWSE, año 112](https://www.twse.com.tw/rwd/zh/holidaySchedule/holidaySchedule?date=20230101&response=json) («市場無交易，僅辦理結算交割作業»). Los calendarios de terceros como [calendarlabs](https://www.calendarlabs.com/twse-market-holidays-2023/) no lo recogen.
- Hora oficial del VIX, 9:30–16:15 ET:
  [Cboe](https://www.cboe.com/tradable_products/vix/faqs).
