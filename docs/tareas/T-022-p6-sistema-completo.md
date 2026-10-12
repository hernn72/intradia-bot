# T-022 — P6 Sistema completo de cartera: B2 y S2 como sistemas, con pre-registro (A-06)

Estado: **ACEPTADA — GATE P6 CRUZADO el 2026-10-05 (D-70), con la salida `[]`.** P6 se ejecutó
**una sola vez** el 2026-10-05.

**Identidad.**
- `P6_PREREG_SHA = 03f04a42ea9d2be893e7c4cc09de76bd1c55778b`
- `P6_CODE_SHA = bc0636d4320b38ef5a620fa9ae94cee35df47580`
- `P6_RUN_HEAD_SHA = 353876d39d03f6849847743b9f4e7f791abbed30`
- `P6_RUN_EVIDENCE_SHA = 0771989af851748463aa0e79d4a7dc327066ca5f`

**Resultado (D-70):** **B2 `NO PASA`** y **S2 `NO PASA`**, con supervivientes **`[]`**. Las dos cumplen
las condiciones 1 a 4 de la sección 16 y fallan solo la 5, `excess_CAGR_pp > 0` (B2 −15,7671 pp;
S2 −18,7228 pp).

Cierre y handoff en la sección «Cierre (2026-10-05)», al final. Lo que sigue a continuación es el
pre-registro tal como quedó fijado; no se reescribe.

---

Estado: **PRE-REGISTRO CONGELADO (2026-10-03).** OD-P6-1 a OD-P6-43 CERRADAS en D-69; revisión
final con 0 BLOCKER y 0 IMPORTANTE en las dos revisiones independientes; precisiones de D-69
ratificadas por el propietario. **`P6_PREREG_SHA` = HEAD del commit de congelación** que añade
`evidence/2026-10-03-T-022-p6-prereg-final/` (se identifica en el PR #40; el commit no puede contener su
propio SHA). P6 **no** está implementado ni ejecutado; el sidecar FX, el mapa de sector y `p6.py`
necesitan autorizaciones aparte. Las recomendaciones de esta ficha son ahora **reglas
vinculantes**: el propietario adoptó todas las recomendadas (sección 24). El criterio decisorio está en
la sección 16 y en D-69.

Historial: EN DISEÑO / PRE-REGISTRO desde el 2026-10-03. Desbloqueado por D-68. **P6 no se ha
ejecutado.** No existe `p6.py`. No se ha simulado ninguna cartera ni calculado ninguna métrica de
sistema (equity, CAGR, drawdown, Sharpe, número de operaciones, exposición, dividendos cobrados ni
exceso) de B2, de S2, de C0 ni del buy-and-hold. Lo único calculado sobre la cosecha es un **censo
estructural sin desenlaces** (`evidence/2026-10-03-T-022-p6-diseno/`).

Las OD-P6 se cerraron en D-69. Siguen la revisión final del pre-registro y el `P6_PREREG_SHA`. El
sidecar FX, el mapa de sector y la implementación del simulador y del preflight necesitan
**autorizaciones aparte**.

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._ El
buy-and-hold del mismo universo **mitiga la interpretación**, pero **no corrige** ese sesgo.

---

## 0. Identidad de partida

| | |
|---|---|
| Base | `main = 0c144ba9ad672817bbff80011c61fb62587b0409` (GATE P5 cruzado, D-67/D-68) |
| `data_vintage_id` | `071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841` (precios y acciones corporativas; no se redescarga) |
| `universe_vintage_id` | `237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19` |
| Políticas que entran | B2 y S2, exactamente como en `evidence/2026-10-03-T-021-p5-cierre/politicas-finales.json` |
| Control | C0 = producción (`config.yaml`, Score v1) |
| Producción | `config.yaml` `"1.0"`, C0, Score v1 70/60 legacy, Score v2 inactivo, Pi `v0.4.1` |

## 1. Pregunta

P4 y P5 midieron **eventos**: cada señal es un ensayo independiente, entra al cierre de la señal y se
compara por `signal_id` frente a C0. P6 hace otra pregunta:

> ¿Qué ocurre cuando B2 y S2 funcionan como **sistemas completos** sobre **una única cartera** con
> capital finito, posiciones simultáneas, ocupación, cash, costes, slippage, dividendos, divisas y
> orden cronológico real?

Protocolo (orden de trabajo): «P6 — Backtest completo de las supervivientes, **como sistemas, no
como trades pareados**». Cambiar la geometría cambia la ejecutabilidad, la duración, la ocupación,
el cash, las señales que se admiten después, la exposición y la trayectoria entera. Por eso cada
política se ejecuta como un sistema independiente, sobre su propia cartera, y P6 no usa ningún
emparejamiento por `signal_id`.

## 2. Políticas que entran en P6

Fuente canónica: `evidence/2026-10-03-T-021-p5-cierre/politicas-finales.json`. **No se reconstruyen
y no se cambia su geometría.** El preflight de P6 tendrá que regenerar `policy_payload`,
`canonical_json` y `policy_sha256` y comprobar que coinciden byte a byte.

| | `policy_sha256` | `advisor_config_hash` | stop | objetivos |
|---|---|---|---|---|
| **B2** | `d5d6a533fe846a6ebb5d5c8e313c84f2a5b4e04095d08386e5d903dce73101b9` | `c5d60f44e89a754f34dfc685cda5073af1c0f9dbb04ab3ec14a813d423f81760` | 2,0·ATR | [1,5; 4,875; 5,0] |
| **S2** | `e37ee93363dbbd7c58cae74bba4391ab9ad41dd1f3ed55804a92efb531e44d11` | `8a151b80d91bf73e431ec38e5e21f22268783bbd0a26d5f72e6ef8887aca0dbb` | 2,5·ATR | [1,5; 3,75; 5,0] |
| C0 (control) | `80e21111a88c1eeac94c2ecef6b8bc480a505a045ca90f6a91a0ba6fc4ffd29a` | `89406d28c7b4b6e6c4f032cd63b6868c927af3e926dfb52d430dfa6654d06387` | 2,0·ATR | [1,5; 3,0; 5,0] |

Las tres comparten `target2_structural = false`, `entry_max_atr = 0,75`, `min_rr = 1,5`, regla E,
`support_buffer_atr = 0,25` y `m3_auxiliar = false`. El hash de C0 es el que publicó el preflight de
P5 (`hashes-configuraciones.md`).

**El campo `laboratorio.entrada = cierre_de_la_senal` de esos payloads describe el event study de P4
y P5. No es la regla de ejecución de P6** (sección 7.8). El `policy_sha256` de P5 no se reinterpreta:
el sistema de P6 tiene su propio hash, que lo incluye (sección 18).

**C0 es el control del sistema, nunca candidata.** P6 no puede llevar C0 a P7 como nueva candidata
(OD-P6-29).

## 3. Inventario del código actual (sin ejecutar resultados)

### 3.1 `advisor/backtest/engine.py` (`simulate_asset`)

Lo que hace, leído en el código:
- **Simula activo por activo**: recorre las velas de un solo `df`. No existe una cartera global, ni
  cash compartido, ni arbitraje entre activos.
- **Una posición por activo.** Además, la señal solo se calcula cuando no hay posición
  (`if position is None and j < len(df) - 1`), así que las señales con posición abierta **ni
  siquiera se cuentan**.
- **Señal al cierre de `t`** → orden pendiente → **intento de entrada en `open(t+1)`**, con
  `evaluate_trade_at_entry`, que comprueba en este orden `INVALID_STOP`, `INVALID_TARGET`,
  `ABOVE_MAX_ENTRY`, `RR_TOO_LOW` (RR a `target2` desde la apertura), `POSITION_TOO_SMALL`,
  `DATA_NOT_EXECUTABLE` y el broker (`BROKER_UNAVAILABLE` rechaza; `BROKER_UNVERIFIED` no rechaza).
  `simulate_asset` no pasa `asset` a `evaluate_trade_at_entry`, así que el broker **no** se evalúa en
  la entrada del backtest; `broker_neutral` solo cambia el predicado de la señal
  (`engine.py:395-399`).
- **Salida** (`_check_exit`): un hueco por debajo del stop se cruza a la apertura; un toque intradía
  del stop, al stop; un hueco por encima del objetivo, a la apertura; un toque del objetivo, a
  `target2` (`target3` no interviene). **Si la misma vela toca stop y objetivo, gana el stop.** Por
  tiempo, al cierre de la barra 40. Al final del histórico, al último cierre (`EXIT_FINAL`).
- **Coste:** porcentaje fijo de ida y vuelta restado del retorno (`net_return_pp = gross − cost_pct`).
- **Docstring:** «**Sin deslizamiento**: las salidas se cruzan al precio exacto del stop o del
  objetivo salvo hueco de apertura».
- **No hay** dividendos, divisas, sizing monetario, equity ni orden cronológico entre activos y
  plazas.

### 3.2 Por qué no satisface GATE P6

GATE P6 pide literalmente un «simulador de cartera con capital, posiciones simultáneas, ocupación,
exposición por región/divisa/sector, costes, slippage, dividendos y orden cronológico real». El motor
actual **no** tiene capital, ni posiciones simultáneas entre activos, ni ocupación, ni exposición, ni
slippage, ni dividendos, ni orden cronológico entre plazas. **No es un simulador de cartera** y esta
ficha no lo llama así. P6 necesitará un simulador nuevo (`p6.py`, con autorización aparte) que
**reutilice** la semántica de señal, entrada y salida de `simulate_asset` sin modificar el backtest
productivo.

### 3.3 Sizing existente

- `config.yaml`: `portfolio.capital: null`, `risk_per_trade_pct: 0.5`, `max_position_pct: 10.0`;
  `risk.min_rr_ratio: 1.5`; `risk.risk_free_annual_pct: 2.25`; `base_currency: "EUR"`.
- `advisor/analysis/sizing.py::calculate_position_sizing`:
  - `risk_fraction = (entry − stop)/entry`;
  - `uncapped_position_pct = risk_per_trade_pct / risk_fraction`;
  - `position_pct = min(uncapped, max_position_pct)`;
  - `risk_pct = min(risk_per_trade_pct, position_pct · risk_fraction)`.
- Es un **porcentaje**. Sin capital no hay unidades, ni cash, ni límite de cash.

## 4. Inventario estructural de datos (censo sin desenlaces)

Script y salida: `evidence/2026-10-03-T-022-p6-diseno/censo_p6.py` → `censo-p6.json`. Solo lee
metadatos del universo, columnas de la cosecha, recuentos de acciones corporativas y fechas. Ningún
precio se convierte en retorno.

| # | Pregunta | Respuesta del censo |
|---|---|---|
| 1 | Divisas de cotización | EUR 41, USD 40, JPY 6, HKD 3 (`currency` = `primary_currency` en los 90) |
| 2 | `economic_currency` | USD 43, EUR 26, JPY 7, HKD 3, MULTI 3, GBP 2, INR 2, TWD 2, CNY 1, KRW 1 |
| 3 | Dividendos | Columna `Dividends` en los 90; 64 activos con algún dividendo; 821 eventos |
| 4 | Splits | Columna `Stock Splits`; 17 eventos en 16 activos (6 japoneses, AMZN, AVGO, AZN, CRWD, GOOGL, NFLX, NOW, NVDA, PANW, TSLA) |
| 5 | FX en la cosecha | Solo `EURUSD=X`: 1.300 barras, marcas 2021-08-29 23:00Z → 2026-08-27 23:00Z (23:00/00:00 UTC), `series_hash 5491cddf…` (bloque `fx_series` del censo) |
| 6 | Pares FX necesarios | `EURUSD=X`, `EURJPY=X`, `EURHKD=X`; **9 activos (6 JPY, 3 HKD) sin FX en la cosecha**; 49 activos necesitan FX |
| 7 | Sector | **0/90**: `Asset` no tiene campo `sector` y `universe.yaml` tampoco |
| 8 | Plazas y zonas | NASDAQ 24, NYSE 16, XETRA 28, PAR 6, JPX 6, MCE 3, HKG 3, AMS 2, MIL 2; 8 zonas horarias |
| 9 | Calendarios | `advisor/data/sessions.py` usa `exchange_calendars` por MIC (`session_open`/`session_close` en `market_state`); `MarketSession` solo guarda zona y cierre regular. `exchange_overrides.yaml` añade cierres que el calendario no tiene (D-54, por ejemplo HKG 2023-09-01 y 2023-09-08) |
| 10 | Historia distinta | 88 activos empiezan el 2021-08-30 (fecha de sesión local); **ARM** (2023-09-14) y **Q8Y0.DE** (2024-11-18) entran más tarde |
| 11 | Broker/metadatos en `simulate_asset` | El backtest no pasa `asset` a `evaluate_trade_at_entry`: el broker no se evalúa en la entrada. `broker_neutral` solo cambia el predicado de la señal (D-04: el broker no forma parte de la señal) |
| 12 | Hashes B2/S2 | Reproducibles con `policy_payload`/`canonical_json` (verificado en el cierre de P5) |
| 13 | Campos de ledger | Ninguno existe hoy: el motor solo produce `BacktestTrade` por activo, sin cash ni unidades |
| 14 | Fecha de pago de dividendos | **No existe**: la cosecha solo trae el importe en la fecha ex |
| 15 | Limitaciones de yfinance | `Dividends` por acción en la divisa de cotización y **ajustado por splits posteriores** (coherente con `execution_prices`); FX diario de calidad de agregador, con marca a medianoche de Londres; sin fecha de pago; sin market cap point-in-time; sector solo como foto actual (`info`), no point-in-time; el acceso a `fc.yahoo.com` puede estar bloqueado en la red de casa (Pi-hole) |

Marcas temporales de la cosecha: cada barra diaria está marcada a la **medianoche local de su plaza
expresada en UTC** (AAPL `04:00/05:00Z`, SAP.DE `22:00/23:00Z` del día anterior, 7203.T `15:00Z`,
0700.HK `16:00Z`). La fecha de sesión es la fecha local. **La marca no es la hora de la apertura ni la
del cierre.**

Calentamiento (swing, `min_bars = 120`), calculado solo con fechas de sesión locales: los 88 activos
con historia completa terminan su calentamiento entre el 2022-02-14 (ADYEN.AS) y el **2022-02-25**
(8035.T); ARM el 2024-03-07; Q8Y0.DE el 2025-05-15. Última sesión local: 2026-08-27 en 39 activos
(XETRA, PAR, AMS, MIL…) y 2026-08-28 en 51.

**Contexto de mercado (Score v1), del censo:** la tendencia usa `^STOXX50E` con SMA200 (D-55); el VIX
usa su última observación causal (D-53) y no necesita historia. La SMA200 se completa con la sesión
**2022-06-13**. Con contexto point-in-time, la SMA200 está completa para una señal al cierre del
2022-06-13, así que **no puede haber ninguna entrada OPERAR antes de la apertura del 2022-06-14**. El
censo solo prueba la historia de la SMA200; el resto del contexto (VIX, Asia) se comprueba señal a
señal y sus exclusiones se cuentan.

**Calendario efectivo, del censo** (`exchange_calendars` 4.13.2 + `exchange_overrides.yaml`,
`sha256 87e4aa21…539db`): 0 barras fuera de calendario y **27 sesiones sin barra**, todas en ETF de
Xetra (el 2025-10-24 y, en 12 de ellos, el 2026-03-06). Con el calendario puro serían 33: los 6 casos
de HKG son los cierres de D-54, que están en los overrides.

## 5. Diferencias materiales entre P4/P5 y P6

1. **Población de señales.** P4 y P5 midieron la geometría sobre **todas las barras elegibles del
   event study** (101.251 señales, sin score y sin `classify()`, D-63). Un sistema que opera «la
   política OPERAR» con Score v1 (70/60, `calibrated: false`) selecciona **otra población**: la que
   pasa el score y los vetos. **Lo que se sabe de la ordenación de Score v1** es lo de A-02
   (P2.3/P2.4 rehechos, D-42): con el estimador primario el veredicto global es `INSUFICIENTE`/`LOW`
   y **ninguna banda es concluyente**. P3 midió **Score v2** (`score_model_version = 2.0`), no v1, y
   salió NO CONCLUYENTE (D-61/D-62). **Esta es la decisión más delicada de P6** y tiene su propia OD
   (OD-P6-37).
   - **El Score v1 incluye el RR** (`scoring.py::_beneficio_riesgo`: 10/15/20 puntos para RR ≥ 1,5 /
     2 / 3). Con stop de volatilidad, el RR es 4,875/2 = 2,44 en B2 (15 puntos), 3,75/2,5 = 1,5 en
     S2 (10) y 3/2 = 1,5 en C0 (10). Con una población OPERAR, **B2 cruza el 70 más a menudo que S2
     y C0 por un efecto mecánico del score**, no por la geometría.
2. **Entrada.** P4/P5 entran al cierre de la señal. P6 entra en `open(t+1)` y vuelve a comprobar
   `entry_max`, RR y tamaño. E1 en P4 (entrada a la apertura con veto frente a entrada al cierre,
   bajo C0) salió NO CONCLUYENTE, ΔR −0,0491 [−0,1078, +0,0120] (D-64). Se cita como contexto; no
   decide nada en P6.
3. **Solapamiento.** P4/P5 admitían señales solapadas del mismo activo. P6, como mucho una posición
   por activo.
4. **Unidad.** P4/P5 miden R por evento; P6, euros de una cartera.
5. **Velas ambiguas.** Los payloads de P5 dicen `"ambiguous": "no_resuelto"` y P4 publicaba cotas. P6
   resuelve la vela que toca stop y objetivo **a stop**, como el motor.
6. **`entry_max`.** Con stop de volatilidad, `entry_max_rr` es exactamente el cierre de la señal en C0
   y S2 (RR = 1,5 justo), pero cierre + 0,75·ATR en B2 (`levels.py`, `entry_max_for_rr`). Con el
   precio efectivo (OD-P6-11 A), solo en C0 y S2 se rechazan las aperturas de la banda
   (cierre/(1+s), cierre].
7. **Tiempo.** La salida por tiempo cuenta 40 barras **desde la entrada**: 41 sesiones desde la señal,
   frente a 40 en P4/P5.

## 6. Prohibiciones de esta fase

Está prohibido:
- crear `p6.py` o modificar el backtest productivo;
- construir curvas de equity de B2, S2, C0 o el benchmark;
- contar operaciones reales, señales OPERAR por política o entradas ejecutables;
- calcular CAGR, drawdown, rendimiento del benchmark, exposición, dividendos cobrados o exceso;
- probar capitales, slippages o umbrales sobre desenlaces;
- elegir el drawdown máximo, la muestra mínima o cualquier umbral mirando resultados.

Está permitido leer código, inspeccionar esquemas, hacer álgebra, contar cobertura estructural sin
resultados de política, diseñar sidecars FX y de sector, usar datos sintéticos y calcular hashes.

## 7. Contrato de simulación

Cada apartado remite a su OD. **Todo lo que dice «se propone» en las secciones 7 a 21 quedó adoptado
tal cual por D-69** y es vinculante; el texto se conserva como se escribió.

### 7.1 Capital (OD-P6-1)
Se propone **100.000 EUR** iniciales por sistema, idénticos para B2, S2, C0 y el buy-and-hold.

### 7.2 Unidades (OD-P6-2)
Se proponen **unidades fraccionarias**. Con fraccionales y sin mínimos por operación, el resultado
relativo es **invariante a la escala del capital**, salvo los redondeos en coma flotante. Con
unidades enteras no lo es.

### 7.3 Base del sizing (OD-P6-3)
Se propone la **equity actual inmediatamente antes de la entrada**:
`equity(τ) = cash(τ) + Σ unidades·último cierre estrictamente anterior a τ·FX causal en τ`, sin
ningún cobro pendiente (con OD-P6-13 C el dividendo entra en cash y en equity solo en el cierre ex).
- Una posición comprada **después** de su último cierre (por ejemplo, en la apertura de Xetra, antes
  de un lote de Nueva York) se valora a su **entrada efectiva** hasta su primer cierre: así la equity
  no recoge un P&L fantasma entre el cierre previo y la compra. La misma regla vale para la identidad
  de la sección 19.
- Se calcula **una vez por lote** de entradas con el mismo `timestamp_utc`, antes de la primera, de
  modo que el orden dentro del lote no cambia el tamaño.
- Las posiciones abiertas en ese mismo instante no cuentan para ese lote.
- Riesgo = 0,5 % de esa equity; posición máxima = 10 % de esa equity.

### 7.4 Cash y apalancamiento (OD-P6-4, OD-P6-5)
- Long only, sin margen, sin apalancamiento y **cash ≥ 0 siempre**.
- `cash_requerido = unidades · entrada_efectiva · FX_entrada + comisión_de_entrada`. El slippage ya va
  dentro de la entrada efectiva.
- Si `cash_requerido > cash`: se propone **rechazar la entrada entera** (`INSUFFICIENT_CASH`). El cash
  se comprueba de forma secuencial dentro del lote, en el orden de OD-P6-6. El tamaño pre-registrado
  no se toca y el coste de oportunidad de la ocupación queda a la vista.
- **Sin límites globales nuevos** (posiciones, riesgo agregado, región, sector, divisa): R-01 está
  después de P7. P6 **mide** la concurrencia y la exposición; no las limita.

### 7.5 Una posición por activo (OD-P6-38)
Como mucho una posición abierta por activo, sin piramidar. Una señal nueva del mismo activo con
posición abierta se registra como `IGNORED_ALREADY_OPEN` y se publica su recuento. No reemplaza stop
ni objetivo, ni aumenta la posición. A diferencia de `simulate_asset`, **la señal se calcula y se
cuenta** aunque haya posición.

### 7.6 Score y señales (OD-P6-37)
- P6 no activa Score v2, no recalibra y no toca los umbrales.
- Cada política usa el scoring heredado por su `advisor_config_hash`: `score_model_version = 1.0`,
  swing OPERAR = 70, VIGILAR = 60, `calibrated: false`.
- **Población (OD-P6-37 = C, D-69):** la primaria y única decisoria es OPERAR con Score v1, con el
  predicado **broker neutral** (D-04): `setup_radar = OPERAR` y `setup_accion = COMPRAR`
  (`engine.py:395-399`, rama `broker_neutral`). El puente descriptivo usa todas las barras elegibles.
- **Contexto de mercado (OD-P6-42):** si la población usa el score, el contexto se calcula con la
  **función point-in-time única** (R-CTX, D-52, D-53, D-56) y `market_context_at`, nunca con el camino
  antiguo (`vix_at`/`trend_*` alineados por fecha civil, que D-53 documenta con look-ahead).
  - **Ojo:** el selector del código, `context_mode_for("1.0")`, devuelve `legacy_v1`. P6 tiene que
    pasar `context_mode="point_in_time"` explícito (`resolve_context_mode` lo admite con 1.0), y un
    test comprueba `MarketContext.source == "point_in_time"` en todas las señales.
- **Marca temporal de la señal:** su `analysis_timestamp` (D-50: la última pasada programada antes de
  la apertura de entrada; pasadas lun–vie a las 07:00, 08:30, 14:30 y 21:00 de Londres). En la
  población sin score se usa la misma regla. Una señal de Xetra queda así hacia las 06:00 UTC del
  día siguiente, no a las 15:30.
- `IGNORED_ALREADY_OPEN` se evalúa con la posición al cierre de `t`.
- **Ningún recuento del preflight reabre una OD.** Si la población cerrada da pocas señales, el
  resultado es el que pre-registra la sección 16.

### 7.7 Universo (OD-P6-39)
Los **90 activos** de P4/P5 (A-02 swing sin cripto; lista con
`asset_list_sha256 = 36355796a57e55a68ea16957b7edc6975360fb2085e7fd91841d20e2d7812f50`). No entra
ningún activo nuevo, ni se excluye ninguno por región, sector o divisa. ARM y Q8Y0.DE entran en el
sistema cuando terminan su calentamiento, con la misma regla que los demás.

### 7.8 Ejecución
- Señal al **cierre** de la sesión `t` del activo, con datos hasta ese cierre inclusive.
- Orden pendiente para la **apertura de la barra siguiente de la serie** del activo (como
  `simulate_asset`), con su hora sacada del calendario efectivo de su fecha de sesión. Si el
  calendario tiene sesiones sin barra, se salta a la siguiente barra y se publica el recuento.
- En esa apertura se vuelven a comprobar stop, objetivo, `entry_max`, RR mínimo a `target2` y
  tamaño, igual que `evaluate_trade_at_entry`, pero con el **precio efectivo** (OD-P6-11 = A).
- **Broker neutral** (D-04): el estado de Trade Republic no rechaza entradas.
- Salidas como en `_check_exit`: hueco al stop → apertura; stop intradía → stop; hueco al objetivo →
  apertura; objetivo intradía → `target2`; los dos en la misma vela → stop; tiempo → cierre de la
  barra 40 desde la entrada (cuenta **barras** de la serie, no sesiones del calendario); final de
  ventana → cierre de la última sesión (`EXIT_FINAL`).
- `target3` no interviene en ninguna salida.

### 7.9 Ventana (OD-P6-21)
Regla propuesta, determinista y solo con fechas:
- **inicio** = la primera fecha `d` en la que se cumplen las dos condiciones:
  1. los 88 activos con historia desde el principio de la cosecha han completado el calentamiento
     swing (barra de índice 120 en fecha local; la última es el 2022-02-25);
  2. (solo si la población decisoria usa el score, OD-P6-37 A o C, con OD-P6-42 A) la SMA200 de
     `^STOXX50E` está causalmente completa (D-55) para una señal al cierre de la última sesión de cada
     activo anterior a `d`. **Solo cuenta la historia de la SMA200**: las exclusiones puntuales de D-52
     (huecos asiáticos) posteriores al inicio se cuentan y se publican, pero **no mueven el inicio**.

  Con el censo, la estimación es el **2022-06-14**:
  - primera señal con la SMA200 completa al cierre del 2022-06-13;
  - ninguna entrada OPERAR antes de la apertura del 2022-06-14.

  El preflight calcula la fecha exacta con la regla, antes de cualquier desenlace, y la escribe en la
  marca. **Pares (fecha de señal, fecha de entrada):** la primera señal admitida es la del cierre de
  la última sesión del activo anterior a `d`, y su entrada es la primera barra del activo en o después
  de `d`.
- **fin** = la última fecha de sesión local común a las 90 series: **2026-08-27**.
- **Bordes:**
  - se admiten señales al cierre de la sesión anterior al inicio, que entran en la primera apertura
    de la ventana, a la vez que el buy-and-hold compra;
  - `V_0` = capital inicial en el instante anterior al primer evento de la fecha de inicio; el
    buy-and-hold compra en la primera apertura de cada activo en o después de `d`, los mismos
    instantes en que el sistema puede entrar;
  - en el fin, todas las posiciones se cierran con `EXIT_FINAL` y esas operaciones cuentan como
    cerradas para N_min, publicadas aparte.

La misma ventana vale para B2, S2, C0, las poblaciones descriptivas y el buy-and-hold. ARM y Q8Y0.DE
no mueven el inicio.

## 8. Cronología global

### 8.1 Marcas temporales reales (OD-P6-7)
Cada evento lleva `timestamp_utc` real:
- **calendario efectivo** = `exchange_calendars` (versión fijada) + `exchange_overrides.yaml`, con su
  hash en `P6_DATA_ID` (OD-P6-41);
- **OPEN** de la sesión `d` del activo = hora de apertura regular de su MIC en `d` en el calendario
  efectivo;
- **CLOSE** = hora de cierre regular de esa sesión (`session_close_at`).

La marca de la barra en la cosecha no se usa como hora. Las sesiones cortas, como medias jornadas y
festivos, salen del calendario de la plaza.

### 8.2 Orden dentro de una sesión de un activo
**En la apertura**, en este orden:
1. los derechos de dividendo con fecha ex `d` ya están determinados por la posición al cierre de la
   sesión anterior;
2. las salidas por hueco (stop u objetivo a la apertura);
3. el cash de esas salidas;
4. las entradas pendientes de esa apertura.

**Durante la sesión:** los toques intradía de stop u objetivo se saben por OHLC, pero no su hora.
**Su cash no se usa antes del cierre de la sesión.**

**En el cierre**, en este orden:
1. las salidas intradía;
2. las salidas por tiempo y la final;
3. el abono de dividendos cuya fecha económica es `d` (OD-P6-13);
4. la valoración;
5. la evaluación de la señal con los datos de la sesión `t`. La señal se **registra** en la fase
   `SIGNAL`, con `timestamp_utc = analysis_timestamp` (sección 7.6), y queda pendiente para la
   apertura de la barra siguiente del activo.

**Entre plazas:** una salida materializada en el cierre de Tokio (06:00 o 06:30 UTC) libera cash
**antes** de la apertura de Nueva York (13:30 o 14:30 UTC) del mismo día, y legítimamente puede
financiarla. Una salida intradía de Nueva York no financia una apertura asiática anterior.

### 8.3 Orden total y empates (OD-P6-6, OD-P6-36)
Orden total:
`(timestamp_utc, fase, clave_de_desempate)`, con
`fase: OPEN_EXIT < OPEN_ENTRY < CLOSE_EXIT < CLOSE_DIVIDEND < CLOSE_VALUATION < SIGNAL`.
Una salida de apertura financia las entradas de esa misma apertura. Una salida de cierre con el mismo
`timestamp_utc` que una apertura de otra plaza **no** la financia: el caso HKG/Europa de abajo.

Los empates reales son frecuentes:
- XETRA, PAR, AMS, MIL y MCE abren y cierran a la misma hora; NYSE y NASDAQ también;
- en invierno, el cierre de HKG (08:00 UTC) coincide con la apertura europea. El orden de fases lo
  resuelve: la salida de HKG está en `CLOSE_EXIT` y la entrada europea en `OPEN_ENTRY`, y como gana
  el `timestamp_utc` igual + la fase, las entradas europeas van antes del cierre de HKG, que es lo
  conservador.

La clave de desempate decide **quién entra** cuando el cash no da para todos, y se fija antes de medir:
- se propone `sha256("intradia.p6.desempate.v1" ‖ signal_id)` en orden ascendente, con bytes exactos
  `sha256(b"intradia.p6.desempate.v1" + signal_id.encode("utf-8")).hexdigest()`, sin separador y
  ordenando la cadena hexadecimal (equivale al orden de bytes): determinista, sin
  relación con el alfabeto ni con el score, y **común a todos los sistemas** (`signal_id` no depende
  de la política). No depende de ningún campo que se pueda redactar después;
- el orden de un `dict`, del YAML o de los ficheros **nunca** decide.

**Prioridad por zona horaria (declarada):** las aperturas asiáticas son las primeras del día UTC y se
quedan con el cash que liberan los cierres de la víspera en EE. UU. Es la cronología real, no un
desempate, y se declara como característica del sistema.

### 8.4 Liquidación (OD-P6-8)
Se propone que el cash de una venta esté **disponible en el mismo `timestamp_utc`** en que se
materializa la salida. La limitación se declara: ignora T+1/T+2 reales, que los datos no permiten
modelar bien en todas las plazas.

## 9. Costes y slippage

### 9.1 Costes (OD-P6-9)
P4/P5 restaban un 0,20 % de ida y vuelta del retorno sobre el precio de entrada.

Se propone un **0,10 % por lado sobre el nominal ejecutado**:
`comision_local = 0,001 · precio_efectivo · unidades` en cada lado, y
`fee_base = comision_local · fx_rate` del evento. El coste
total es `0,001·(E + X)`, frente a `0,002·E` en P4. La diferencia es `0,001·(X − E)` por unidad:
**es idéntico a P4 solo si X = E**. En una salida al objetivo, el coste por lado es un poco mayor que
en P4; en una salida al stop, un poco menor. El 0,20 % total no cambia; lo que se fija es su reparto.
La alternativa (OD-P6-9 B) cobra el 0,20 % del nominal de entrada, que es la equivalencia exacta.

### 9.2 Slippage (OD-P6-10)
Se propone un **primario de 5 pb por lado**, igual para todas las políticas y el benchmark, y una
**sensibilidad descriptiva de 10 pb por lado**, sin veto. Ninguno se calibra sobre resultados.

### 9.3 Precio efectivo (OD-P6-11)
- `entrada_efectiva = precio_de_mercado · (1 + s)`
- `salida_efectiva = precio_de_mercado · (1 − s)`

El precio de mercado es la apertura, el stop, `target2` o el cierre, según la salida.

Se propone evaluar la ejecutabilidad (RR a `target2`, `entry_max` y tamaño) con la **entrada
efectiva**, porque ese es el riesgo realmente asumido. Esto puede rechazar entradas que P4 habría
admitido; queda pre-registrado.

## 10. Dividendos y splits

### 10.1 Semántica (inventario)
- `execution_prices` está ajustado por splits y **no** por dividendos: conserva el hueco ex-dividendo.
  Si P6 no abonara el dividendo, el precio caería en la fecha ex sin el cobro que lo compensa: el
  sistema perdería un ingreso real. P6 tiene que abonarlo.
- **Limitación (revisión final):** en cotizaciones de Xetra cuyo dividendo se declara en otra divisa,
  Yahoo convierte el importe con **un único tipo de cambio** (presumiblemente el de la descarga), no
  con el de cada fecha ex. Comprobado en R6C0.DE (Shell): cada importe × 1,1587 da exactamente el
  dividendo en USD (0,24 … 0,3906). En 2022, con EURUSD ≈ 1,0, el abono queda infravalorado en torno a
  un 14 %. Posiblemente también afecta a BSP.DE, RRU.DE y a ETF como EQQQ.DE, IQQK.DE e IQQT.DE (sin
  verificar). No se corrige el dato: se declara, afecta igual a las políticas y al benchmark, y el
  preflight publica la lista de activos afectados con una comprobación estructural, sin desenlaces.
- `Dividends` (yfinance) es el importe por acción en la fecha ex, en la divisa de cotización y
  ajustado por splits posteriores. Por tanto es coherente con las unidades de `execution_prices`; el
  preflight lo comprueba de forma algebraica en los 16 activos con split.

### 10.2 Derecho (OD-P6-12)
Una posición cobra el dividendo con fecha ex `d` si estaba abierta **al cierre de la sesión anterior
a `d`**:
- una compra en la apertura de `d` **no** lo cobra;
- una venta en la apertura de `d` (hueco) **sí** lo cobra.

### 10.3 Fecha económica y de cash (OD-P6-13)
La cosecha no trae fecha de pago. Se propone abonar el cash **en el cierre de la sesión ex** (C) y
declarar la simplificación. Así el dividendo no puede financiar una apertura del mismo día. La
fecha de pago real suele ser posterior, así que esta regla **adelanta** el cash; el sesgo es pequeño
frente al tamaño de las posiciones y se declara.

### 10.4 Fiscalidad (OD-P6-14)
Se propone dividendo **bruto**, sin retención: no hay información fiscal congelada. Se publica la
limitación.

### 10.5 Splits
No se aplica ningún split manual: la vista ya está ajustada y las unidades se mantienen. Los tests
sintéticos comprueban un split 2:1 y un **contrasplit** (en la ventana hay uno de factor 0,5 en AZN el
2026-02-02, por el cambio de ratio del ADR), la continuidad del valor económico y la coherencia de
stop y objetivo.

## 11. FX (OD-P6-15, OD-P6-16)

- **Problema:** la base es EUR y 49 activos cotizan en USD, JPY o HKD. Sin una política FX no hay
  capital, CAGR, drawdown, cash ni exposición en EUR.
- **Disponibilidad:** solo `EURUSD=X` está en la cosecha. P6 necesita un **vintage auxiliar FX
  congelado antes de cualquier desenlace**, con `EURUSD=X`, `EURJPY=X` y `EURHKD=X`, del mismo
  proveedor y con hash propio. La descarga necesita autorización aparte y red con acceso a Yahoo.
  Si la comprobación de integridad falla, se aplica la **fuente B** (sección 11.1), sin abrir ninguna
  OD nueva (D-69).
- **Regla causal propuesta (A):** para un evento en τ se usa el **cierre de la última barra FX
  completa antes de τ**. Se fija `timestamp_available = marca_de_la_barra + 24 h` (la barra diaria
  de yfinance va marcada al principio del día de Londres). Nunca se usa el FX de un día para un
  evento que ocurrió horas antes de su cierre.
- **Contrato del sidecar:** `fx_pair, bar_timestamp, timestamp_available, rate, series_hash,
  provider, provider_version, downloaded_at`.
- **Sentido del FX:** `EURxxx=X` cotiza unidades de `xxx` por 1 EUR. Se define
  `fx_rate = EUR por unidad de la divisa de cotización = 1 / close(EURxxx=X)`; para EUR, 1. Todas las
  fórmulas multiplican importes en divisa por `fx_rate`.
- **Petición fija de la fuente A:** una sola descarga con yfinance, `interval = "1d"`,
  `start = "2021-08-27"` y `end = "2026-08-29"` explícitos (no `period`), `auto_adjust = False` y
  `actions = True` (la misma política que la cosecha), registrando la versión de yfinance y
  `downloaded_at`. Solo se reintenta una llamada que **termina con excepción** (fallo de red). La
  primera llamada que termina sin excepción se congela tal cual y se comprueba **una sola vez**; una
  respuesta con barras de menos o de más no se reintenta: es un fallo de integridad y lleva a B. **La elección entre A y B depende solo de la comprobación de integridad sobre
  esa petición fija**, sin desenlaces.
- **Comprobación del sidecar (fuente A):** el **tramo común** es el conjunto exacto de las 1.300 marcas
  de `EURUSD=X` de la cosecha. El `EURUSD=X` del sidecar tiene que contener **exactamente esas marcas**
  dentro de ese rango, con la cadena canónica del float **idéntica** barra a barra. Una barra que falte
  o que sobre dentro del rango, o una cadena distinta, es un **fallo**. Si pasa, se usa el sidecar de
  Yahoo para los tres pares. Si falla, no se excluye ningún activo, no se acepta una serie aproximada,
  se documenta el fallo y se aplica la fuente B (sección 11.1) **para los tres pares**. Esta decisión
  se toma y se congela **antes del preflight y sin ningún desenlace**.
- **Conversión:** cada entrada, salida y dividendo se convierte a EUR con el FX causal de su τ. Las
  posiciones abiertas se valoran en cada instantánea con el último FX causal.
- **Equity EUR** = cash EUR + valor de mercado de las posiciones en EUR (con la valoración de la
  sección 7.3). Sin cobros pendientes: con OD-P6-13 = C el dividendo entra en cash en el cierre ex.
### 11.1 Fuente B de respaldo (pre-registrada; solo si falla la integridad de A)

- **Fuente:** los tipos de referencia diarios del euro del **BCE** (euro foreign exchange reference
  rates), para **USD, JPY y HKD**: los tres pares salen del BCE, también el USD.
- **Sentido:** el BCE publica unidades de la divisa por 1 EUR, así que `fx_rate = 1 / rate`.
- **Disponibilidad causal:** se fija `timestamp_available = 17:00 Europe/Berlin` del día de referencia
  (el BCE publica hacia las 16:00 CET; la hora de margen queda fijada). Para un evento en τ se usa el
  último tipo con `timestamp_available < τ`.
- **Días sin tipo** (festivos TARGET): el último tipo causal disponible.
- **Contrato del sidecar:** el mismo que en A, con `provider = ECB` y su `series_hash`. El
  `fx_vintage_id` forma parte de `P6_DATA_ID`.
- Lo que cambia es la fuente, nunca la regla de qué eventos convierte ni cómo entra el FX en las
  métricas.

### 11.2 Caja

- **Cash:** se propone una **única caja en EUR**; cada compra y venta en otra divisa se convierte al
  FX causal sin coste FX adicional, y la limitación se declara (OD-P6-40).
- `economic_currency` **nunca** se usa para convertir precios. El cash y el P&L van siempre en la
  divisa de la serie de ejecución.

## 12. Exposición (OD-P6-17, OD-P6-18, OD-P6-19)

- **Divisa:** se propone publicar **las dos**:
  1. por divisa de cotización y liquidación (`primary_currency`);
  2. por `economic_currency`, con `MULTI` como categoría propia y sin reparto.
- **Sector:** hoy la cobertura es 0/90.
  - Se propone un **mapa congelado de propuesta**, `evidence/…T-022…/p6-sector-map.yaml`, con
    `instrument_id, asset, sector, taxonomy, source, observed_at`.
  - Acciones: sector de una fuente externa verificable, foto actual, **no point-in-time**.
  - ETF y ETC: una categoría propia (`DIVERSIFIED_ETF`, `BOND_ETF`…), sin look-through.
  - Lo que no se pueda clasificar: `UNKNOWN`, publicado y **dentro del denominador**.
  - El sector es **descriptivo**: no decide ninguna entrada ni ningún veto, así que el que no sea
    point-in-time solo afecta a la lectura, y se etiqueta.
- **Región:** USA, EUROPA, ASIA, GLOBAL y EMERGING_MARKETS (`Asset.region`).
- **Métricas de exposición por categoría** (sobre la instantánea diaria):
  - exposición bruta = valor long / equity;
  - cash / equity;
  - para cada región, divisa y sector: media temporal, máximo y p95 (nearest-rank).

## 13. Valoración (OD-P6-20)

Se propone **C**:
- el **ledger por eventos** es la fuente de verdad;
- una **serie diaria** derivada sirve para las métricas, con una instantánea a las **23:59:59 UTC**
  de cada día en que al menos una de las 9 plazas tuvo sesión.

Cada instantánea valora con el último cierre de cada activo **estrictamente anterior** a ella y el
último FX causal. A las 23:59:59 UTC ya cerraron Asia, Europa y Estados Unidos de ese día, y Tokio
todavía no ha abierto el siguiente (00:00 UTC).

`periodos_por_año` se calcula **antes de medir**, solo con el calendario: número de instantáneas de
la ventana dividido por sus años (365,25 días). Queda como constante del contrato.

## 14. Buy-and-hold del propio universo (OD-P6-22 a OD-P6-25)

- **Mismo universo** (los 90 activos), **misma ventana**, misma cosecha, misma regla FX, misma regla
  de dividendos y mismo modelo de costes y slippage. No se usa ningún índice externo como sustituto.
- **Ponderación propuesta:** pesos iguales (no hay capitalizaciones point-in-time congeladas).
  **Sin rebalanceo.**
- **Compra:** en la apertura de la primera sesión de cada activo dentro de la ventana, 1/90 del
  capital inicial por activo. **La comisión va dentro del importe asignado:** `nominal + comisión =
  1/90 del capital` (el nominal es `(capital/90)/1,001`). Lo mismo en cada reinversión: `nominal +
  comisión = dividendo abonado en EUR`. El benchmark también cumple cash ≥ 0.
- **ARM y Q8Y0.DE:** se propone reservar su 1/90 en cash hasta la **apertura de la barra siguiente a
  su barra 120** (2024-03-08 y 2025-05-16 según el censo, o la siguiente barra), que es la primera
  apertura en la que el sistema podría entrar. Es la misma regla de elegibilidad que el sistema.
- **Dividendos propuestos:** **reinvertidos** en el mismo activo en la apertura siguiente al abono,
  con coste y slippage. Es lo más conservador frente a las candidatas: evita que el arrastre del
  cash debilite el benchmark.
- **Final:** liquidación en el cierre de la última sesión de la ventana, con coste y slippage, igual
  que las posiciones abiertas del sistema (`EXIT_FINAL`).

## 15. Métricas: definiciones exactas

Notación:
- `V_t`: equity EUR en la instantánea `t = 0…T`;
- `r_t = V_t / V_{t−1} − 1` (retorno simple);
- `P`: `periodos_por_año` (sección 13);
- `D`: días naturales entre la primera y la última instantánea. La instantánea 0 es `V_0`, tomada en el
  instante anterior al primer evento de la fecha de inicio (sección 7.9).

Todas las métricas se calculan igual para cada política y para el benchmark.

| Métrica | Definición | Casos límite |
|---|---|---|
| Retorno total | `V_T / V_0 − 1` | — |
| **CAGR** | `(V_T / V_0)^(365,25 / D) − 1` | `V_T ≤ 0` → N/D |
| Volatilidad | `std(r_t, ddof=1) · √P` | < 2 retornos → N/D |
| **Sharpe** | `mean(r_t)·P / (std(r_t, ddof=1)·√P)`, con **rf = 0** (OD-P6-26), rotulado «Sharpe (rf = 0)» | std = 0 → N/D |
| **Sortino** | `mean(r_t)·P / (√(mean(min(r_t, 0)²))·√P)`, con MAR = 0; la media de la desviación a la baja va sobre **todos** los periodos | sin retornos negativos → N/D |
| **Max drawdown** | `min_t(V_t / max_{s≤t} V_s − 1)`; se publican magnitud, fecha del pico, fecha del valle, fecha de recuperación (primera `t` > valle con `V_t ≥ pico`, o «sin recuperar») y duración en días naturales de pico a recuperación (o hasta el final) | sin caída → 0 |
| **Calmar** | `CAGR / |max_drawdown|` | DD = 0 → N/D, nunca infinito |
| **Turnover** | `turnover_total = Σ |nominal_EUR de cada compra y venta| / mean_t(V_t)`; `turnover_anual = turnover_total / (D / 365,25)` | — |
| Exposición media | media de `valor_long_t / V_t` sobre las instantáneas | — |
| **Profit factor** | `Σ R⁺ / |Σ R⁻|` sobre las operaciones cerradas, con `trade_R_local` (OD-P6-43); en EUR, `Σ pnl⁺ / |Σ pnl⁻|`, descriptivo | **sin pérdidas y n ≥ N_min → la condición PF > 1 se cumple** y se publica «sin pérdidas»; sin operaciones → N/D y la condición no se cumple |
| **R por operación** | `trade_R_local = pnl_neto_local / riesgo_inicial_local` (decide, OD-P6-43) y `trade_R_EUR = pnl_neto_EUR / riesgo_inicial_EUR` (descriptivo) | riesgo ≤ 0 → la operación no puede existir (la ejecutabilidad lo impide) |
| **R total** | `Σ trade_R` | — |
| R medio / mediano | `mean_R_local = mean(trade_R_local)` sobre las operaciones cerradas (**decide**) / `median(trade_R_local)` | — |
| Media por bloque (INV-14, descriptiva) | media simple, por año natural con al menos una operación cerrada, de la media de `trade_R_local` de las operaciones cerradas en ese año (fecha de salida) | años sin operaciones no cuentan |
| **Expectancy de sistema** | `mean(trade_R_local)` (no la del event study) | — |
| Win rate | fracción de operaciones con `pnl_neto_EUR > 0` | — |
| Exceso | `excess_terminal_pp = 100·(ret_total_pol − ret_total_BH)`; **`excess_CAGR_pp = 100·(CAGR_pol − CAGR_BH)`** (principal, OD-P6-27) | — |

### 15.1 P&L económico y riesgo de una operación
En divisa de cotización (local):
- `riesgo_inicial_local = (entrada_efectiva − stop) · unidades`. Se usa el stop **sin** slippage: es
  el riesgo planificado con el que se dimensionó la posición.
- `pnl_bruto_local = unidades · (salida_efectiva − entrada_efectiva)`; el slippage ya va dentro de los
  precios efectivos.
- `pnl_neto_local = pnl_bruto_local − comisiones_local + dividendos_local_atribuidos`.

En EUR (con `fx_rate` = EUR por unidad local, sección 11):
- `riesgo_inicial_EUR = riesgo_inicial_local · fx_entrada`;
- `pnl_bruto_EUR = unidades · (salida_efectiva · fx_salida − entrada_efectiva · fx_entrada)`;
- `pnl_neto_EUR = pnl_bruto_EUR − Σ comisión_i · fx_i + Σ dividendo_j · fx_j`;
- desglose publicado: `slippage_EUR = unidades · |mercado − efectivo| · fx` en la entrada y en la
  salida; `fx_EUR = unidades · salida_efectiva · (fx_salida − fx_entrada)`.

`trade_R_local` es comparable con P4/P5 y no depende de la tendencia del euro: con una fracción de
riesgo de ~4 %, un 1 % de EURUSD durante la operación vale ~0,25 R. Por eso decide el R local
(OD-P6-43) y el R en EUR se publica.

## 16. Criterio de supervivencia (OD-P6-28, OD-P6-30 a OD-P6-34)

Se propone que una política **pase a P7** si y solo si, sobre su sistema primario (población
primaria de OD-P6-37, slippage primario):
1. operaciones cerradas (incluidas las `EXIT_FINAL`) ≥ **N_min** (OD-P6-30; se propone 100);
2. `profit_factor` en R local > 1 (sin pérdidas cuenta como cumplida, sección 15);
3. `mean(trade_R_local) > 0`;
4. `max_drawdown ≥ −DD_max`, en EUR (OD-P6-31; se propone 25 %);
5. `excess_CAGR_pp > 0`, en EUR (OD-P6-28, A).

**Excepción declarada a INV-14 (D-03).** INV-14 fija como estimador primario «de P3 en adelante» la
media por bloque de la expectancy neta en R de **eventos**. En P6 la unidad no es el evento sino la
**operación de un sistema**: dependiente de la trayectoria, con muchas menos operaciones y sin la
estructura de bloques del event study. D-69 decide literalmente con `mean_R_local` (media de las
operaciones cerradas), y esa es la **única** lectura decisoria. La media por bloque de INV-14 se
publica como **descriptiva** (sección 15, por año natural), nunca veta ni rescata, y no se puede
invocar después para reinterpretar el criterio.

**Etiquetas, fijadas ex ante:**
- `PASA`: cumple las cinco condiciones;
- `NO EVALUABLE POR MUESTRA`: incumple la 1, se publica igual el resto y no pasa;
- `NO PASA`: cumple la 1 e incumple alguna de las demás.

Ningún recuento del preflight ni del resultado reabre una OD.

Lo que se propone **descriptivo, sin veto**:
- Sharpe, Sortino, Calmar, volatilidad y turnover (OD-P6-32);
- la sensibilidad de slippage de 10 pb;
- los resultados por año y por mitades, rotulados «**robustez temporal interna sobre datos de
  desarrollo**», nunca validación (OD-P6-33);
- C0 y las diferencias frente a C0 (OD-P6-29);
- la exposición y la concurrencia.

**Incertidumbre (OD-P6-33):** se propone publicar solo las métricas de trayectoria, sin IC, más los
subperiodos descriptivos (por año natural y por mitades de la ventana). No se remuestrean operaciones
independientes. P7 aporta la validación temporal independiente.

**Salida permitida (OD-P6-34):** exactamente `[]`, `[B2]`, `[S2]` o `[B2, S2]`. P6 no crea B3 ni
S3, no mezcla B2 con S2, no pondera entre ellas y no declara que una sea mejor. Si las dos pasan, las
dos van a P7.

## 17. Salidas obligatorias de P6 (por B2 y S2; C0 y el benchmark como referencia)

- **Rendimiento:** equity inicial y final, retorno total y CAGR.
- **Riesgo:** volatilidad, max DD con sus fechas y duración, Sharpe (rf = 0), Sortino (MAR = 0) y
  Calmar.
- **Operaciones:** n, win rate, PF, R medio y mediano, R total, holding medio (en sesiones), costes
  EUR, slippage EUR, dividendos EUR y P&L FX EUR.
- **Cartera:**
  - posiciones simultáneas media y máxima;
  - porcentaje de instantáneas con 0, 1, …, N posiciones;
  - cash medio y mínimo;
  - exposición bruta;
  - exposición por región, divisa de cotización, divisa económica y sector;
  - turnover;
  - capital pedido frente a capital disponible.
- **Ejecución:**
  - señales;
  - entradas;
  - rechazos por motivo: `ABOVE_MAX_ENTRY`, `RR_TOO_LOW`, `INVALID_STOP`, `INVALID_TARGET`,
    `POSITION_TOO_SMALL`, `INSUFFICIENT_CASH`, `IGNORED_ALREADY_OPEN`, `DATA_NOT_EXECUTABLE` y
    otros;
  - fracción de señales ejecutables rechazadas por cash.
- **Benchmark:** retorno, CAGR, exceso total y exceso de CAGR.
- **Criterio:** cada condición de la sección 16 con su valor, la etiqueta y la salida.

## 18. Identidad del sistema (OD-P6-35)

`system_sha256` = sha256 del `canonical_json` (mismo serializador que P5) de un envoltorio
`intradia.p6.system.v1` con:

`p5_policy_sha256`, `advisor_config_hash`, `score_model_version`, `poblacion_de_senales`
(OD-P6-37), `capital_inicial`, `base_currency`, `risk_per_trade_pct`, `max_position_pct`,
`modo_de_contexto` (OD-P6-42), `predicado_OPERAR` (broker neutral, sección 7.6), `estimador_decisorio` (`mean_R_local` = media simple de `trade_R_local` sobre las operaciones cerradas,
excepción a INV-14 declarada en la sección 16), `regla_analysis_timestamp` (D-50: pasadas 07:00,
08:30, 14:30 y 21:00
lun–vie, zona Europe/London, `settlement_minutes`), `moneda_del_R_decisorio` (OD-P6-43),
`fuente_fx` (A o la B de la sección 11.1, según la integridad), `unidades` (fraccional/entera),
`base_del_sizing`, `regla_de_cash` (rechazar, reducir o prorratear; con comisión),
`apalancamiento = 0`, `limites_globales`, `regla_mismo_activo`, `semantica_de_entrada`
(`open_t+1`, comprobaciones, precio efectivo), `semantica_de_salida`, `cronologia` (fuente del
calendario, orden de fases), `desempate`, `liquidacion`, `modelo_de_costes`, `modelo_de_slippage`,
`modelo_de_dividendos` (derecho, fecha económica, fiscalidad), `fx` (`fx_vintage_id`, regla causal,
caja), `sector_map_sha256`, `calendario_de_valoracion`, `periodos_por_año`, `ventana`
(inicio, fin), `universo` (`asset_list_sha256`), `contrato_del_benchmark`, `contrato_de_metricas`,
`criterio_de_supervivencia`, `data_vintage_id`, `universe_vintage_id` y `p6_data_id`. La clave de desempate **no** depende de `system_sha256` (sección 8.3).

`P6_DATA_ID = sha256(canonical_json({market_data_vintage: 071ddb2b…, universe_vintage: 237b0056…,
fx_vintage: …, sector_map: …, calendar: {exchange_calendars: versión, exchange_overrides_sha256: …,
tzdata: versión}, asset_list: 36355796…}))`.

**Corridas pre-registradas**, cada una con su hash:

| Sistema | Población | Slippage | Papel |
|---|---|---|---|
| B2, S2 | primaria (OD-P6-37) | 5 pb | **decide** |
| B2, S2 | primaria | 10 pb | sensibilidad descriptiva |
| B2, S2 | descriptiva: todas las barras (OD-P6-37 = C) | 5 pb | puente con P4/P5 **bajo la ventana de P6** (no es una réplica de P4/P5), descriptivo |
| C0 | primaria | 5 pb | control descriptivo |
| Buy-and-hold | — | 5 pb | benchmark del criterio |
| Buy-and-hold | — | 10 pb | benchmark de la sensibilidad |

El exceso de la sensibilidad se mide contra el buy-and-hold con el mismo slippage.

Cada sistema (B2, S2 y C0) tiene su `system_sha256` **antes** de ejecutar, publicado en el preflight y
en la marca. El benchmark tiene su `benchmark_sha256`, con el mismo contrato.

## 19. Ledger e identidades contables

**Ledger determinista** (una fila por evento), con estos campos:
- identificación: `seq`, `timestamp_utc`, `fase`, `system_sha256`, `policy_id`, `event_type`,
  `market`, `asset`, `session_date`, `signal_id`, `position_id`;
- cash y unidades: `cash_before`, `cash_after`, `units_before`, `units_after`;
- precios: `market_price`, `effective_price`, `currency`;
- FX: `fx_pair`, `fx_rate`, `fx_timestamp_available`;
- importes en EUR: `notional_base`, `fee_base`, `slippage_base`, `dividend_base`,
  `receivable_after` (siempre 0 con OD-P6-13 C), `realized_pnl_base`;
- `equity_after` y `reason`.

**Ninguna métrica existe solo en memoria:** todas se reconstruyen desde el ledger y la serie diaria
publicados.

**Identidades que el simulador comprueba en cada evento y al final**, con tolerancia absoluta de
1e-6 EUR:
- `equity = cash + Σ valor_de_mercado_EUR` (con la valoración de la sección 7.3, sin cobros
  pendientes);
- `cash ≥ 0` siempre;
- `V_T − V_0 = Σ pnl_bruto_EUR (cerradas) + pnl_no_realizado_bruto_EUR + Σ dividendos_EUR −
  Σ comisiones_EUR`, con el `pnl_bruto` de la sección 15.1 (precio efectivo y FX, sin comisiones ni
  dividendos). Equivalente: `V_T − V_0 = Σ pnl_neto_EUR + pnl_no_realizado_bruto_EUR`. Con el cierre
  `EXIT_FINAL`, el no realizado es 0. El slippage y el FX se publican como desglose dentro de
  `pnl_bruto`; no hay partida residual.

## 20. Tests obligatorios (con datos sintéticos, antes de ejecutar)

1. una operación simple sin costes;
2. sizing por riesgo;
3. tope del 10 %;
4. cash insuficiente → `INSUFFICIENT_CASH`;
5. dos entradas simultáneas;
6. orden determinista por `sha256(b"intradia.p6.desempate.v1" + signal_id.encode("utf-8")).hexdigest()`
   ascendente, sin alfabeto;
7. stop por hueco;
8. stop y objetivo en la misma vela → stop;
9. una salida intradía no financia una entrada anterior a su cierre;
10. una salida en Asia libera cash para una apertura posterior en Estados Unidos;
11. dividendo ex;
12. compra en la fecha ex sin dividendo;
13. venta en la apertura ex con derecho;
14. split 2:1;
15. FX constante;
16. FX que se mueve sin que se mueva el activo;
17. exposición por divisa de cotización frente a `economic_currency` (incluido `MULTI`);
18. turnover;
19. max DD con fechas;
20. Sharpe y Sortino;
21. benchmark con pesos iguales;
22. dividendo del benchmark reinvertido;
23. conciliación del ledger;
24. `system_sha256` de B2 y S2;
25. C0 como control;
26. el mismo resultado repetido byte a byte.

Y además:

27. `IGNORED_ALREADY_OPEN` contado;
28. FX con `timestamp_available` posterior al evento → no se usa;
29. instantánea a las 23:59:59 UTC sin cierres futuros;
30. activo tardío (ARM) que entra al terminar su calentamiento;
31. dividendo en un activo con split (escala coherente);
32. ejecutabilidad con precio efectivo que rechaza una entrada que el precio observado admitiría;
33. coste 0,10 % + 0,10 % = coste de P4 cuando X = E;
34. cash nunca negativo bajo entradas simultáneas;
35. el `policy_sha256` de P5 se regenera dentro del preflight;
36. contrasplit (factor 0,5);
37. cash insuficiente solo por la comisión;
38. PF sin pérdidas con n ≥ N_min;
39. sesión del calendario sin barra (entrada en la barra siguiente);
40. contexto point-in-time: `available_at ≤ analysis_timestamp` para VIX, tendencia, Asia y la serie
    de fortaleza relativa;
41. clave de desempate común a B2, S2 y C0 e independiente del `system_sha256`;
42. R local frente a R en EUR con FX que se mueve (el veto usa el local);
43. sentido del FX (`EURUSD=X` = 1,10 → 1 USD = 0,909 EUR);
44. sizing una vez por lote: el orden del lote no cambia el tamaño;
45. una posición comprada después de su último cierre se valora a su entrada efectiva hasta su primer
    cierre (sin P&L fantasma en el sizing);
46. `MarketContext.source == "point_in_time"` en todas las señales con score (nunca `legacy_v1`);
47. una salida de cierre con el mismo instante que una apertura de otra plaza no financia esa entrada;
48. cadena causal por plaza: `cierre de la sesión t disponible ≤ analysis_timestamp < apertura de la
    barra de entrada`, para todas las plazas y con cambios de horario.

## 21. GATE P6: requisito por requisito (evidencia futura)

| Requisito literal | Dónde se probará |
|---|---|
| simulador de cartera **con capital** | contrato 7.1 a 7.4; ledger (`cash_before/after`, `equity_after`); tests 1–4, 34, 37, 44 y 45 |
| **posiciones simultáneas** | serie de posiciones abiertas por instantánea; tests 5 y 6 |
| **ocupación** | distribución de 0…N posiciones, cash/equity, `INSUFFICIENT_CASH` (sección 17) |
| exposición por **región** | sección 12, desde `Asset.region` |
| exposición por **divisa** | sección 12: cotización y económica (test 17) |
| exposición por **sector** | sección 12, con `p6-sector-map.yaml` congelado y hasheado; `UNKNOWN` publicado |
| **costes** | sección 9.1; `fee_base` por evento; tests 33 y 37 |
| **slippage** | sección 9.2; `slippage_base`; sensibilidad de 10 pb |
| **dividendos** | sección 10; `dividend_base`; tests 11–13, 22 y 31 |
| **orden cronológico real** | sección 8; `timestamp_utc` y orden total; calendario efectivo con 27 sesiones sin barra publicadas; tests 9, 10, 28, 29, 39, 40, 41, 46, 47 y 48 |
| métricas CAGR, volatilidad, Sharpe, Sortino, max DD, Calmar, exposición media, turnover, PF, R total y R por operación | sección 15, en `metricas.json` y en el ledger y la serie diaria publicados; tests 18–20, 38, 42 y 43 |
| **exceso sobre el buy-and-hold** del propio universo en la misma ventana | sección 14; `excess_CAGR_pp` y `excess_terminal_pp` |

Ningún requisito queda como «se añadirá luego». Sector y FX dependen de sidecars que se congelan antes
del preflight (OD-P6-15 y OD-P6-18).

## 22. Producción

P6 no activa nada. No se tocan `config.yaml`, el score, `deploy/` ni la Pi. Producción sigue en C0,
Score v1 70/60 legacy y Pi `v0.4.1`. No hay release ni despliegue.

## 23. Plan después de cerrar las OD

1. El propietario cierra las OD-P6 en una D-nn.
2. Revisión final del pre-registro con 0 BLOCKER y 0 IMPORTANTE **y ratificación expresa del
   propietario de las «Precisiones de la revisión final» de D-69**, registrada antes de congelar →
   `P6_PREREG_SHA`.
3. Con autorización: congelar el sidecar FX y el mapa de sector (sin desenlaces) → `P6_DATA_ID`.
4. Con otra autorización: `p6.py`, los tests y el preflight (sin desenlaces de sistema), y después
   una revisión de look-ahead. Identidades: `P6_CODE_SHA` (último commit del ejecutor) y
   `P6_RUN_HEAD_SHA` (HEAD de la ejecución), como en P4 y P5.
5. Con autorización: la **única** ejecución confirmatoria, con una marca de creación exclusiva escrita
   antes de abrir ningún desenlace de sistema. P6 no se repite: si se para después de la marca, queda
   la parada y no se arregla ni se relanza.
6. Solo se pueden corregir **errores de implementación** frente a las definiciones de las secciones 15
   y 16, recalculando **desde el ledger publicado**. Cualquier cambio de **definición** de una métrica
   exige una D-nn, se rotula como post hoc y **nunca cambia la etiqueta ni la salida** de P6. Las
   correcciones se recalculan sin volver a simular. Cualquier re-simulación exige una D-nn nueva.

---

## 24. OWNER_DECISION_REQUIRED — todas CERRADAS en D-69 (2026-10-03)

El propietario cerró las 43 OD en D-69, todas con la alternativa recomendada (OD-P6-15 con la B como
respaldo si el `EURUSD=X` del sidecar no reproduce la cosecha; OD-P6-18 con A para acciones y las
categorías de C para ETF/ETC). Debajo de cada título está la decisión vinculante; las alternativas y
consecuencias se conservan como historial.

### OD-P6-1 — Capital inicial · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** 100.000 EUR iniciales por sistema y para el benchmark. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Con qué capital inicial EUR arranca cada sistema y el benchmark?

Alternativas:
A. 100.000 EUR.
B. 10.000 EUR.
C. 1.000.000 EUR (escala normalizada).

Consecuencias:
- A: intuitivo y con efectos discretos pequeños; con fraccionales, el resultado relativo no depende
  del capital.
- B: más cerca de una cartera particular; con unidades enteras los redondeos y el mínimo por
  operación pesan, y P6 deja de ser invariante a la escala.
- C: igual que A con fraccionales; menos intuitivo.

Recomendación técnica: A. Con OD-P6-2 = A, la elección no altera ninguna métrica relativa. Su coste
metodológico es nulo siempre que se fije antes de medir.

Qué bloquea: sizing, cash, ledger y `system_sha256`.

### OD-P6-2 — Unidades fraccionarias o enteras · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** Unidades fraccionarias. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Se permiten unidades fraccionarias?

Alternativas:
A. Fraccionarias.
B. Enteras con `floor`.
C. Las dos: una primaria y otra de sensibilidad.

Consecuencias:
- A: la cartera prueba la política, no las restricciones de un broker o un capital concretos; es
  invariante a la escala.
- B: introduce `POSITION_TOO_SMALL` y dependencia del capital; en acciones japonesas o de precio
  alto puede rechazar entradas por un motivo ajeno a la política.
- C: dos sistemas por política y otro grado de libertad para leer.

Recomendación técnica: A, declarando la limitación (Trade Republic permite fracciones en muchos
valores, pero no en todos).

Qué bloquea: sizing y tests 2–4.

### OD-P6-3 — Base del sizing · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** Sizing sobre la equity causal inmediatamente anterior al lote de entrada; `risk_per_trade_pct = 0,5 %` y `max_position_pct = 10 %` sin cambio y sin optimizar en P6. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Sobre qué se calculan el 0,5 % de riesgo y el 10 % máximo?

Alternativas:
A. Equity actual inmediatamente antes de la entrada (precios y FX causales).
B. Capital inicial fijo.
C. Cash disponible.

Consecuencias:
- A: capitalización compuesta real; el tamaño crece y decrece con la equity.
- B: tamaño constante en EUR; el CAGR deja de reflejar la reinversión.
- C: con la cartera cargada el tamaño se encoge, lo que mezcla sizing con ocupación y no es la regla
  de producción.

Recomendación técnica: A, y además se conservan `risk_per_trade_pct = 0,5` y `max_position_pct = 10`
de `config.yaml`. Cambiarlos convertiría P6 en otra optimización.

Qué bloquea: sizing y `system_sha256`.

### OD-P6-4 — Cash insuficiente · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** Si la posición no cabe con la comisión incluida → `INSUFFICIENT_CASH`, rechazada entera; ni reducir ni prorratear. Long only, sin margen ni apalancamiento, cash nunca negativo. El texto que sigue es el historial de la pregunta tal como se planteó.

Si una entrada ejecutable no cabe en el cash, ¿qué se hace?

Alternativas:
A. Rechazarla entera (`INSUFFICIENT_CASH`).
B. Reducir el tamaño al cash restante.
C. Prorratear el cash entre las entradas simultáneas.

Consecuencias:
- A: el tamaño pre-registrado no se toca y la ocupación se ve en la tasa de rechazo; con la cartera
  llena se pierden entradas enteras.
- B: entra más a menudo, pero con un riesgo inferior al 0,5 %, y el R de esa operación deja de ser
  comparable.
- C: depende del conjunto de entradas simultáneas; es complejo de auditar.

Recomendación técnica: A.

Qué bloquea: contrato de ejecución y tests 4–6.

### OD-P6-5 — Límites globales · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** Sin límites globales de posiciones, riesgo, región, sector o divisa (son de R-01, después de P7). El texto que sigue es el historial de la pregunta tal como se planteó.

¿Impone P6 algún límite global (posiciones, riesgo agregado, región, sector, divisa)?

Alternativas:
A. Ninguno: solo 0,5 % por operación, 10 % por posición y cash finito; la concurrencia y la
   exposición se miden.
B. Un máximo de posiciones o de riesgo agregado.
C. Límites por región, sector o divisa.

Consecuencias:
- A: P6 mide el sistema tal como está configurado; la exposición puede llegar a ~100 % invertido.
- B y C: introducen parámetros no validados antes de R-01, que va después de P7, y son nuevos grados
  de libertad.

Recomendación técnica: A.

Qué bloquea: contrato de cartera.

### OD-P6-6 — Orden de entradas simultáneas · **CERRADA (D-69): D**

**Decisión del propietario (vinculante):** `sha256("intradia.p6.desempate.v1" ‖ signal_id)` ascendente, la misma regla para B2, S2 y C0; ni score ni alfabeto. El texto que sigue es el historial de la pregunta tal como se planteó.

Cuando varias entradas coinciden en el mismo `timestamp_utc`, ¿en qué orden se intentan?

Alternativas:
A. Score descendente y después `signal_id`.
B. `signal_id` o símbolo en orden lexicográfico.
C. Prorrateo de cash.
D. `sha256("intradia.p6.desempate.v1" ‖ signal_id)` ascendente (pseudoaleatorio determinista y común a
   todos los sistemas).

Consecuencias:
- A: usa una ordenación del Score v1 que no está validada (A-02, D-42: ninguna banda concluyente) y
  que además premia el RR de la geometría.
- B: neutral respecto al score, pero el **alfabeto** decide el P&L cuando el cash escasea, de forma
  sistemática (por ejemplo, los símbolos numéricos japoneses irían primero).
- C: ver OD-P6-4 C.
- D: neutral respecto al score y al alfabeto, determinista y reproducible. Es el mismo orden en B2,
  S2 y C0, así que el sorteo no introduce ruido independiente entre sistemas (los conjuntos de señales
  que compiten por el cash sí difieren). No depende de ningún campo
  que se pueda redactar después: no hay palanca de re-sorteo.

Recomendación técnica: D. Su coste es que el orden es arbitrario, aunque declarado y no
manipulable después.

Qué bloquea: cronología y test 6.

### OD-P6-7 — Cronología intradía y reutilización de cash · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** Una salida por hueco libera el cash en la apertura; una salida intradía, solo en el cierre; entre plazas manda el tiempo UTC real. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Cuándo está disponible el cash de una salida?

Alternativas:
A. Salidas por hueco: en la apertura, antes de las entradas de esa apertura. Salidas intradía: en el
   cierre de la sesión. Entre plazas manda el `timestamp_utc` real.
B. Todo en el cierre de la sesión, incluidas las salidas por hueco.
C. En la apertura para todo.

Consecuencias:
- A: no usa cash cuya hora es desconocida; deja que una salida en Asia financie Estados Unidos.
- B: más conservador; pierde la liquidez de los huecos conocida en la apertura.
- C: look-ahead, porque usa a las 09:30 el cash de una salida intradía que aún no ha ocurrido.

Recomendación técnica: A, con aperturas y cierres de `exchange_calendars`.

Qué bloquea: cronología y tests 9 y 10.

### OD-P6-8 — Liquidación · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** El cash está disponible desde que se materializa la salida; no se modela T+1/T+2 (limitación declarada). El texto que sigue es el historial de la pregunta tal como se planteó.

¿Cuándo está disponible el cash de una venta?

Alternativas:
A. En el mismo instante en que se materializa la salida.
B. T+1.
C. T+2 u otra regla histórica por plaza.

Consecuencias:
- A: simple y auditable; algo optimista frente a la realidad.
- B y C: más realistas, pero necesitan calendarios de liquidación por plaza y periodo que no están
  congelados, y añaden complejidad sin datos que la sostengan.

Recomendación técnica: A, declarando la limitación.

Qué bloquea: cash.

### OD-P6-9 — Costes · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** 0,10 % sobre el nominal de entrada y 0,10 % sobre el de salida; no es algebraicamente idéntico al 0,20 % fijo de P4 salvo cuando salida = entrada. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Cómo se traduce el 0,20 % de ida y vuelta de P4 a flujos de cash?

Alternativas:
A. 0,10 % por lado sobre el nominal ejecutado.
B. 0,20 % del nominal de entrada, cobrado en la entrada.
C. 0,20 % del nominal de entrada, repartido por mitades entre entrada y salida.

Consecuencias:
- A: realista; el coste total es `0,001·(E + X)`, que coincide con P4 solo si X = E.
- B: equivalencia exacta con P4; adelanta todo el coste.
- C: exacto en total, pero el coste de salida no depende del precio de salida.

Recomendación técnica: A. El 0,20 % total no cambia; la diferencia algebraica con P4 se declara.

Qué bloquea: ledger y test 33.

### OD-P6-10 — Slippage · **CERRADA (D-69): D**

**Decisión del propietario (vinculante):** Primario de 5 pb por lado; sensibilidad de 10 pb por lado solo descriptiva: no veta, no rescata y no cambia los supervivientes. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Qué slippage se usa?

Alternativas:
A. 5 pb por lado, fijo.
B. 10 pb por lado, fijo.
C. Dependiente de ATR o liquidez.
D. Primario de 5 pb por lado y sensibilidad de 10 pb por lado.

Consecuencias:
- A: simple, pero sin ninguna lectura de la sensibilidad.
- B: más conservador y con más rechazos por precio efectivo.
- C: necesita un modelo de liquidez que no está congelado, y es más fácil de calibrar a posteriori.
- D: decide el primario; la sensibilidad se publica.

Recomendación técnica: D, con la sensibilidad **descriptiva, sin veto**, y el mismo modelo para
todas las políticas y el benchmark. Coste metodológico: si la sensibilidad cambiara el veredicto, no
lo cambia. La alternativa D′ hace que la sensibilidad también vete.

Qué bloquea: ejecución y `system_sha256`.

### OD-P6-11 — Ejecutabilidad con precio efectivo o con precio observado · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** El RR, `entry_max`, el riesgo y el sizing se evalúan con el precio efectivo después del slippage. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Con qué precio se evalúan el RR, `entry_max` y el tamaño en la apertura?

Alternativas:
A. Con la entrada efectiva (con slippage).
B. Con el precio observado (la apertura), como `simulate_asset`.

Consecuencias:
- A: mide el riesgo realmente asumido; puede rechazar entradas límite que P4 y producción admitirían.
- B: igual que el motor y el asesor; el riesgo real es mayor que el pre-registrado.

Recomendación técnica: A.

Qué bloquea: ejecución y test 32.

### OD-P6-12 — Derecho al dividendo · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** Cobra la posición abierta al cierre de la sesión anterior a la fecha ex; una compra en la fecha ex no cobra; una venta en su apertura de una posición que venía abierta sí cobra. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Qué posición cobra un dividendo con fecha ex `d`?

Alternativas:
A. La que estaba abierta al cierre de la sesión anterior a `d`.
B. La que está abierta al cierre de `d`.
C. La que está abierta en algún momento de `d`.

Consecuencias:
- A: es la regla económica real; cobra aunque se venda en la apertura de `d`, y una compra en `d` no
  cobra.
- B: da dividendos a quien compra en la fecha ex y se los quita a quien vende en ella; es incorrecta.
- C: ambigua.

Recomendación técnica: A.

Qué bloquea: dividendos y tests 11–13.

### OD-P6-13 — Fecha económica y de cash del dividendo · **CERRADA (D-69): C**

**Decisión del propietario (vinculante):** Sin fecha de pago, el dividendo entra en cash al cierre de la sesión ex. La misma regla para las políticas y el benchmark. El texto que sigue es el historial de la pregunta tal como se planteó.

Sin fecha de pago en la cosecha, ¿cuándo se abona el dividendo?

Alternativas:
A. Cash en la apertura de la fecha ex.
B. Cobro pendiente dentro de la equity en la fecha ex, y cash después de un desfase fijo inventado.
C. Cash en el cierre de la sesión ex, con la simplificación declarada.

Consecuencias:
- A: el dividendo podría financiar entradas en la misma apertura; adelanta el cash más que C.
- B: más realista en el tiempo, pero el desfase es inventado y no se puede verificar.
- C: no financia aperturas del mismo día; adelanta el cash frente al pago real (sesgo pequeño y
  declarado).

Recomendación técnica: C.

Qué bloquea: dividendos y cash.

### OD-P6-14 — Fiscalidad de los dividendos · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** Dividendo bruto, sin retención. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Se aplica retención?

Alternativas:
A. Bruto, sin retención.
B. Retención uniforme.
C. Retención por país.

Consecuencias:
- A: no inventa datos fiscales; sobreestima lo que cobraría un inversor real.
- B: arbitrario.
- C: necesita tablas fiscales congeladas que no existen.

Recomendación técnica: A, publicando la limitación. El benchmark recibe el mismo trato.

Qué bloquea: dividendos.

### OD-P6-15 — Fuente y vintage FX · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** Sidecar congelado de `EURUSD=X`, `EURJPY=X` y `EURHKD=X` (Yahoo/yfinance), creado más adelante con autorización aparte. El `EURUSD=X` tiene que reproducir exactamente la cadena canónica de la cosecha. Si falla: no se excluye ningún activo, no se acepta una serie aproximada, se documenta el fallo y se usa la alternativa B como fuente FX. El texto que sigue es el historial de la pregunta tal como se planteó.

¿De dónde salen `EURJPY` y `EURHKD`, que faltan, y cómo se congelan?

Alternativas:
A. Sidecar FX congelado de yfinance (`EURUSD=X`, `EURJPY=X`, `EURHKD=X`) con hash propio y
   comprobación de que `EURUSD=X` coincide con la cosecha.
B. Otra fuente (BCE, tipos de referencia diarios), especificada por completo en la sección 11.1.
C. Excluir los 9 activos en JPY y HKD.

Consecuencias:
- A: el mismo proveedor que los precios; con calidad de agregador; necesita red con acceso a Yahoo y
  una autorización de descarga.
- B: oficial y trazable, pero publica a las 16:00 CET y a otra hora, así que la regla causal cambia.
- C: cambia el universo, y con él el benchmark. Es una exclusión de conveniencia.

Recomendación técnica: A, y B solo si A no reproduce el `EURUSD=X` de la cosecha.

Qué bloquea: FX, `P6_DATA_ID` y todo el preflight.

### OD-P6-16 — Regla causal FX · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** Para un evento en τ, el cierre de la última barra FX completa y disponible antes de τ, nunca el cierre futuro del mismo día; `fx_rate_to_EUR = 1 / close(EURXXX=X)`. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Qué tipo FX se usa en un evento en τ?

Alternativas:
A. El cierre de la última barra FX completa antes de τ (`timestamp_available = marca + 24 h`).
B. FX intradía.
C. El FX del mismo día de sesión.

Consecuencias:
- A: causal y reproducible; se rezaga hasta un día.
- B: no hay datos intradía congelados.
- C: look-ahead para eventos anteriores al cierre FX.

Recomendación técnica: A.

Qué bloquea: FX y test 28.

### OD-P6-17 — Exposición por divisa · **CERRADA (D-69): C**

**Decisión del propietario (vinculante):** Se publican las dos: divisa de cotización y liquidación y `economic_currency`; `MULTI` como categoría propia; sin look-through. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Qué significa «exposición por divisa» en GATE P6?

Alternativas:
A. Solo la divisa de cotización y liquidación.
B. Solo `economic_currency`.
C. Las dos, con `MULTI` como categoría propia y sin repartir.

Consecuencias:
- A: es la exposición monetaria del cash y del P&L, pero no la económica (un ADR o un valor británico
  en Xetra).
- B: es la económica, pero deja el riesgo de conversión fuera.
- C: más información, sin inventar look-through.

Recomendación técnica: C.

Qué bloquea: salidas y test 17.

### OD-P6-18 — Fuente y taxonomía de sector · **CERRADA (D-69): A para acciones + categorías de C para ETF/ETC**

**Decisión del propietario (vinculante):** Acciones: sector externo verificable, congelado con `instrument_id`, `sector`, `taxonomy`, `source` y `observed_at`. ETF y ETC: categorías estructurales por tipo, sin look-through. Solo descriptivo. Todavía no se obtienen los datos. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Cómo se obtiene el sector de los 90 activos?

Alternativas:
A. Sector GICS o similar de una fuente externa verificable (por ejemplo `info["sector"]` de
   yfinance), como foto congelada.
B. Una taxonomía manual congelada y revisada.
C. Una clasificación mínima: sector para las acciones y categorías para los ETF, bonos y
   commodities, con MULTI/UNKNOWN.

Consecuencias:
- A: verificable, pero no point-in-time.
- B: auditable, pero subjetiva.
- C: robusta, pero gruesa.

Recomendación técnica: A para las acciones, más las categorías de C para los ETF y ETC, congelado en
`p6-sector-map.yaml` con `source` y `observed_at`. Es solo descriptivo, nunca decide.

Qué bloquea: el requisito de sector de GATE P6 y `P6_DATA_ID`.

### OD-P6-19 — UNKNOWN y ETF/ETC en el sector · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** `UNKNOWN` es una categoría válida, queda en el denominador y se publica. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Cómo se tratan los instrumentos sin sector?

Alternativas:
A. Categoría propia `UNKNOWN`, publicada y dentro del denominador.
B. Excluirlos del cálculo de exposición sectorial.
C. Repartirlos con look-through de sus componentes.

Consecuencias:
- A: transparente.
- B: infla la exposición del resto.
- C: necesita composiciones point-in-time que no existen.

Recomendación técnica: A; los ETF y ETC sin look-through, con su categoría.

Qué bloquea: la exposición por sector.

### OD-P6-20 — Calendario de valoración · **CERRADA (D-69): C**

**Decisión del propietario (vinculante):** El ledger por eventos es la fuente de verdad, más una serie diaria a las 23:59:59 UTC de cada día con al menos una sesión; `periodos_por_año` sale del calendario antes de cualquier desenlace. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Cómo se construye la curva de equity?

Alternativas:
A. Instantánea diaria global a una hora UTC fija.
B. Equity en cada evento.
C. Ledger por eventos, que es la fuente de verdad, más una serie diaria derivada a las 23:59:59 UTC
   de cada día con al menos una sesión.

Consecuencias:
- A: sencilla, pero el ledger no queda como fuente.
- B: la frecuencia es irregular y las métricas anualizadas quedan mal definidas.
- C: auditable y con métricas bien definidas.

Recomendación técnica: C, con `periodos_por_año` calculado antes de medir, solo desde el calendario.

Qué bloquea: métricas y test 29.

### OD-P6-21 — Ventana exacta de P6 · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** Inicio: calentamiento de los 88 activos iniciales y SMA200 de `^STOXX50E` causalmente completa (estimación 2022-06-14; el preflight fija la fecha exacta de forma mecánica). Fin: 2026-08-27. Las exclusiones asiáticas puntuales posteriores no mueven el inicio. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Qué inicio y qué fin?

Alternativas:
A. Inicio: la primera fecha con el calentamiento completo de los 88 activos con historia desde el
   principio **y**, solo si OD-P6-37 es A o C con OD-P6-42 A, la SMA200 de `^STOXX50E` causalmente
   completa (estimación 2022-06-14); si no, solo el calentamiento. Fin: la última sesión común
   (2026-08-27).
B. Inicio: solo el calentamiento (2022-02-25).
C. Inicio: la primera sesión de la cosecha (2021-08-30).
D. Una ventana en la que los 90 activos ya tienen historia (desde 2025-05-15).

Consecuencias:
- A: ni el sistema ni el benchmark arrancan con meses en los que la población OPERAR no puede existir.
  Se pierden ~3,5 meses de la caída de 2022.
- B: entre el 2022-02-25 y el 2022-06-13 no puede haber ninguna señal OPERAR con contexto causal. El
  benchmark estaría invertido al 100 % y el sistema al 0 % justo en la caída de 2022, lo que sesga de
  forma estructural el exceso y el drawdown.
- C: lo mismo que B, más largo.
- D: apenas 15 meses, con muy poca muestra.

Recomendación técnica: A. La regla sale de fechas, no de resultados, y el preflight escribe la fecha
exacta en la marca.

Qué bloquea: todas las métricas.

### OD-P6-22 — Construcción del buy-and-hold · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** Pesos iguales sobre los 90 activos, sin rebalanceo. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Qué ponderación y qué rebalanceo?

Alternativas:
A. Pesos iguales, sin rebalanceo.
B. Por capitalización.
C. Pesos iguales con rebalanceo periódico.

Consecuencias:
- A: no necesita datos nuevos y es buy-and-hold literal.
- B: no hay capitalizaciones point-in-time congeladas.
- C: ya no es buy-and-hold y añade costes y otro parámetro.

Recomendación técnica: A, con el mismo FX, dividendos, costes y slippage.

Qué bloquea: el benchmark y el exceso.

### OD-P6-23 — Activos sin precio al inicio del benchmark · **CERRADA (D-69): B**

**Decisión del propietario (vinculante):** El 1/90 de ARM y de Q8Y0.DE queda en cash hasta la apertura de la barra siguiente a su barra 120. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Qué hace el benchmark con ARM y Q8Y0.DE?

Alternativas:
A. Benchmark solo con los activos que tienen precio al inicio (88).
B. Reservar su 1/90 en cash hasta la apertura de la barra siguiente a su barra 120, la primera en la
   que el sistema podría entrar.
C. Un inicio común posterior para todos.

Consecuencias:
- A: el benchmark tiene un universo distinto al del sistema.
- B: el mismo universo y la misma elegibilidad; hay algo de arrastre de cash (2/90 del capital
  durante meses o años).
- C: ver OD-P6-21 D.

Recomendación técnica: B.

Qué bloquea: el benchmark.

### OD-P6-24 — Dividendos del benchmark · **CERRADA (D-69): B**

**Decisión del propietario (vinculante):** Los dividendos del benchmark se reinvierten en el mismo activo en la apertura siguiente al abono. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Qué se hace con los dividendos que cobra el benchmark?

Alternativas:
A. Se acumulan como cash, sin reinvertir.
B. Se reinvierten en el mismo activo en la apertura siguiente al abono.
C. Se reparten en todo el benchmark.

Consecuencias:
- A: hay arrastre de cash, que debilita el benchmark y favorece a las candidatas.
- B: rentabilidad total clásica; genera pequeñas compras con coste.
- C: es un rebalanceo encubierto.

Recomendación técnica: B, por ser lo más conservador frente a las candidatas.

Qué bloquea: el benchmark.

### OD-P6-25 — Costes y slippage del benchmark · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** El benchmark paga los mismos costes, slippage, FX y reglas de dividendos que las políticas, incluidas la compra inicial, las reinversiones y la liquidación final. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Paga el benchmark costes y slippage?

Alternativas:
A. Sí, el mismo modelo en la compra inicial, las reinversiones y la liquidación final.
B. Solo en la compra inicial.
C. No.

Consecuencias:
- A: la comparación económica es justa.
- B: el benchmark sale algo favorecido al no pagar la salida.
- C: el benchmark sale favorecido sin justificación.

Recomendación técnica: A.

Qué bloquea: el benchmark.

### OD-P6-26 — Sharpe y risk-free · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** Sharpe con rf = 0 y Sortino con MAR = 0, rotulados; no se aplica hacia atrás el 2,25 % actual. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Qué tipo libre de riesgo usan el Sharpe y el Sortino?

Alternativas:
A. rf = 0, rotulado así.
B. 2,25 % constante (`config.risk.risk_free_annual_pct`).
C. Una serie histórica point-in-time congelada.

Consecuencias:
- A: transparente y el mismo para todas las políticas; no es un Sharpe en exceso de la caja.
- B: aplica un valor actual hacia atrás, cuando los tipos en EUR fueron negativos o nulos hasta 2022.
- C: necesita otra fuente congelada.

Recomendación técnica: A. Como Sharpe y Sortino son descriptivos (OD-P6-32), el rf no decide nada.

Qué bloquea: métricas.

### OD-P6-27 — Exceso principal · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** `excess_CAGR_pp = 100·(CAGR_policy − CAGR_buy_hold)` principal; también se publica `excess_terminal_pp`. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Cuál es el exceso principal?

Alternativas:
A. `excess_CAGR_pp = 100·(CAGR_pol − CAGR_BH)`.
B. `excess_terminal_pp` (diferencia de retornos totales).
C. Otro, como el exceso ajustado por riesgo.

Consecuencias:
- A: anualizado y comparable entre periodos.
- B: equivalente en signo con la misma ventana y el mismo capital, pero no anualizado.
- C: introduce otro estimador.

Recomendación técnica: A como principal y B publicado. Un `excess_R` no tiene sentido para un
benchmark sin stop.

Qué bloquea: el criterio.

### OD-P6-28 — ¿Veta el exceso? · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** `excess_CAGR_pp > 0` obligatorio para sobrevivir; no hay otro umbral de exceso. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Es `excess_CAGR_pp > 0` condición para pasar a P7?

Alternativas:
A. Sí.
B. Solo se publica; P7 decide.
C. Otro umbral.

Consecuencias:
- A: no se gasta el holdout independiente en una política que no supera a su propio universo en
  desarrollo. Es estricto con políticas de menor exposición, que pueden quedar por debajo de un
  buy-and-hold invertido al 100 % en un mercado alcista.
- B: lleva a P7 sistemas sin ventaja económica demostrada.
- C: es un parámetro nuevo.

Recomendación técnica: A. El coste es el sesgo contra los sistemas con cash parado, y se declara.

Qué bloquea: el criterio y la salida.

### OD-P6-29 — C0 como control · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** C0 es solo control descriptivo: nunca veta ni rescata a B2 o S2, nunca pasa a P7 ni vuelve a ser candidata. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Se simula C0?

Alternativas:
A. Sí, como control descriptivo; se publican sus métricas y las diferencias, sin veto.
B. No; solo B2, S2 y el benchmark.
C. Sí, y además veta (B2 y S2 no pueden empeorar materialmente a C0).

Consecuencias:
- A: comprueba si la ventaja de los eventos sobrevive a la ocupación y al capital, sin convertir C0
  en candidata.
- B: menos información.
- C: añade un umbral de «materialmente» y otro grado de libertad.

Recomendación técnica: A. C0 nunca puede pasar a P7.

Qué bloquea: salidas.

### OD-P6-30 — Muestra mínima · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** `N_closed ≥ 100`; por debajo, `NO EVALUABLE POR MUESTRA`, y no pasa a P7. Se publican las operaciones por año y los años con operaciones, sin otro veto. El recuento nunca reabre esta OD. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Cuántas operaciones cerradas hacen falta como mínimo?

Alternativas:
A. ≥ 100.
B. ≥ 200.
C. Un umbral por años con operaciones (por ejemplo, ≥ 20 por año en cada año).

Consecuencias:
- A: moderado. Ojo: el número de señales OPERAR v1 por política no se ha contado a propósito; si la
  población es OPERAR (OD-P6-37 A), puede quedar por debajo y la política no pasaría por falta de
  muestra.
- B: más exigente.
- C: protege frente a la concentración temporal; es otro parámetro.

Recomendación técnica: A, publicando además las operaciones por año y los años con operaciones. El
umbral se fija **antes** del recuento de señales del preflight. Por debajo, la etiqueta es `NO
EVALUABLE POR MUESTRA` (sección 16), distinta de `NO PASA`, y ninguna de las dos lleva a P7. Un
recuento bajo no reabre ni esta OD ni OD-P6-37.

Qué bloquea: el criterio.

### OD-P6-31 — Drawdown máximo permitido · **CERRADA (D-69): C**

**Decisión del propietario (vinculante):** `max_drawdown ≥ −25 %`; uno peor veta. El umbral no se cambia después de ver resultados. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Qué drawdown veta?

Alternativas:
A. 15 %.
B. 20 %.
C. 25 %.
D. 30 %.
E. Relativo: el DD de la política no puede ser peor que el del buy-and-hold.

Consecuencias:
- A y B: estrictos para una cartera long-only; la ventana incluye 2022.
- C: tolerable para un inversor particular con riesgo de 0,5 % por operación.
- D: laxo.
- E: depende del mercado, no tiene unidad fija, y un benchmark muy malo lo vuelve permisivo.

Recomendación técnica: C (25 %), razonado a priori: 50 R seguidos perdidos al 0,5 % sin recuperar.
No se ha mirado ningún resultado.

Qué bloquea: el criterio.

### OD-P6-32 — Sharpe, Sortino y Calmar: ¿descriptivos o vetos? · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** Sharpe, Sortino y Calmar son solo descriptivos: no vetan ni rescatan. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Deciden Sharpe, Sortino o Calmar si una política pasa a P7?

Alternativas:
A. Descriptivos.
B. Vetos con umbrales.
C. Solo Calmar como veto.

Consecuencias:
- A: no hay umbrales arbitrarios.
- B: cinco umbrales nuevos y otros tantos grados de libertad.
- C: es redundante con el DD y el exceso.

Recomendación técnica: A.

Qué bloquea: el criterio.

### OD-P6-33 — Incertidumbre y subperiodos · **CERRADA (D-69): A + C**

**Decisión del propietario (vinculante):** Ni bootstrap ni IC de trayectoria. Se publican las métricas de trayectoria, los resultados por año natural y por primera y segunda mitad, rotulados «robustez temporal interna sobre datos de desarrollo»: solo descriptivo, no es validación y no veta. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Qué incertidumbre y qué robustez temporal se publican, y vetan?

Alternativas:
A. Solo métricas de trayectoria, sin IC.
B. Bootstrap por bloques que reconstruye el sistema entero.
C. Subperiodos descriptivos (año natural y mitades de la ventana).
D. Subperiodos como veto (por ejemplo, `mean_R > 0` en las dos mitades).

Consecuencias:
- A: honesto con la dependencia de la trayectoria.
- B: metodológicamente delicado (la cartera depende del orden) y muy caro.
- C: informa sin decidir.
- D: añade vetos de desarrollo que P7 ya cubre mejor.

Recomendación técnica: A + C, rotulado «robustez temporal interna sobre datos de desarrollo». Nunca
validación.

Qué bloquea: salidas y criterio.

### OD-P6-34 — Salida a P7 · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** Solo `[]`, `[B2]`, `[S2]` o `[B2, S2]`; si las dos pasan, las dos van a P7; no se elige la mejor ni se crea una combinación. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Qué conjunto puede salir?

Alternativas:
A. Exactamente `[]`, `[B2]`, `[S2]` o `[B2, S2]`; si las dos pasan, van las dos.
B. Solo la «mejor» de las dos.
C. Una combinación de B2 y S2.

Consecuencias:
- A: no se elige sobre datos de desarrollo y se mantiene la filosofía de P5.
- B: es selección a posteriori.
- C: crea una política nueva no validada.

Recomendación técnica: A.

Qué bloquea: la salida.

### OD-P6-35 — Hash canónico de sistema · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** `intradia.p6.system.v1` con `system_sha256` de todas las decisiones económicas y de contexto, y `P6_DATA_ID` compuesto, congelados antes de la ejecución. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Qué identifica a un sistema P6?

Alternativas:
A. `system_sha256` sobre `intradia.p6.system.v1` con todos los campos de la sección 18, y
   `P6_DATA_ID` compuesto.
B. Solo `policy_sha256` + `data_vintage_id`.
C. Un hash del código.

Consecuencias:
- A: cada decisión económica queda en el hash.
- B: no identifica capital, costes, FX ni ningún otro elemento del sistema.
- C: no es estable frente a refactorizaciones y no describe la economía.

Recomendación técnica: A, publicado antes de ejecutar.

Qué bloquea: el preflight.

### OD-P6-36 — Política ante empates de timestamp · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** Fases en empate: `OPEN_EXIT < OPEN_ENTRY < CLOSE_EXIT < CLOSE_DIVIDEND < CLOSE_VALUATION < SIGNAL`. El texto que sigue es el historial de la pregunta tal como se planteó.

Además del orden de entradas (OD-P6-6), ¿cómo se ordenan los demás eventos con el mismo
`timestamp_utc`?

Alternativas:
A. Por fases (`OPEN_EXIT < OPEN_ENTRY < CLOSE_EXIT < CLOSE_DIVIDEND < CLOSE_VALUATION < SIGNAL`);
   dentro de cada fase, salidas y dividendos por (`market`, `asset`) y entradas según OD-P6-6.
B. Por plaza y después por fase.
C. Todo por `signal_id`.

Consecuencias:
- A: las salidas **de apertura** liberan cash antes de las entradas de esa misma apertura; una salida
  de cierre empatada con una apertura de otra plaza no la financia, que es lo conservador. El orden de
  las salidas no cambia el cash final.
- B: una plaza podría consumir cash antes de que otra lo libere en el mismo instante.
- C: mezcla las fases.

Recomendación técnica: A.

Qué bloquea: cronología.

### OD-P6-37 — Población de señales del sistema · **CERRADA (D-69): C**

**Decisión del propietario (vinculante):** Primaria y única decisoria: OPERAR con Score v1 y el contexto point-in-time de OD-P6-42. Puente descriptivo hacia P4/P5: una corrida de todas las barras elegibles que no veta, no rescata, no elige y no modifica el resultado. Cada una con su `system_sha256`. Se declara: P4/P5 midieron todas las barras; el Score v1 no tiene ordenación demostrada; P3 estudió el v2; el RR forma parte del v1 (B2 15 puntos frente a 10 en S2 y C0). El texto que sigue es el historial de la pregunta tal como se planteó.

¿Qué señales puede intentar operar el sistema, y cuál decide?

Alternativas:
A. Solo la población **OPERAR con Score v1**, con el predicado del código:
   `accion ∈ {COMPRAR, VERIFICAR_BROKER}` o, con `broker_neutral`, `setup_radar = OPERAR` y
   `setup_accion = COMPRAR` (`engine.py:395-399`), con contexto point-in-time (OD-P6-42). Es **lo más
   cercano a producción sin look-ahead** (ver OD-P6-42: no es idéntico al asesor en vivo).
B. **Todas las barras elegibles** del event study (la población de P4/P5), con una posición por activo
   y cash finito: el sistema sobre el que se midió la geometría.
C. A como **primaria y única decisoria**, y B como **descriptiva**, con su propio `system_sha256`, que
   nunca veta ni rescata.
D. Una población **común**, la OPERAR de C0, operada con la geometría de cada política: aísla la
   geometría del efecto del RR en el score.

Consecuencias:
- A:
  - lo más cercano a producción sin look-ahead (OD-P6-42 declara las diferencias);
  - **no** es la población sobre la que P4/P5 demostraron que B2 y S2 mejoran a C0;
  - usa un Score v1 cuya ordenación no es concluyente (A-02, D-42; P3 midió v2, no v1);
  - **el RR forma parte del Score v1**: B2 (RR 2,44, 15 puntos) cruza el 70 más a menudo que S2 y
    C0 (RR 1,5, 10 puntos), así que su población es distinta y más grande por un efecto mecánico del
    score, y la comparación con C0 y entre B2 y S2 mezcla los dos efectos;
  - la muestra puede quedar escasa (OD-P6-30).
- B: coherente con la evidencia de P4/P5. Como sistema, opera la primera señal de cada activo libre,
  lo que es casi entrar siempre; no es el sistema de producción y no usa el score.
- C: el veredicto lo da lo más cercano a producción sin look-ahead, y el puente a P4/P5 queda a la
  vista sin decidir.
  Son dos corridas por política, ambas con hash y pre-registradas.
- D: separa limpiamente la geometría del score, pero no es un sistema que nadie fuera a operar: el
  score se calcularía con niveles de C0 y la operación con los de B2 o S2.

Recomendación técnica: **C**. Es la única que conserva como decisorio lo más cercano a producción sin
look-ahead y deja publicado el puente con lo que P4/P5 midieron, con el efecto del RR declarado. **Es la decisión con
más consecuencias de P6.**
- Se cierra antes de contar ninguna señal.
- La descriptiva nunca cambia el veredicto.
- Ningún recuento del preflight (por ejemplo, pocas señales OPERAR) reabre esta OD.

Qué bloquea: todo el contrato, `system_sha256`, la ventana y la muestra.

### OD-P6-38 — Señales con posición abierta en el mismo activo · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** `IGNORED_ALREADY_OPEN`, contado y publicado; sin piramidar y sin modificar el stop ni los objetivos. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Qué se hace con una señal nueva de un activo con posición abierta?

Alternativas:
A. Ignorarla, contarla y publicarla (`IGNORED_ALREADY_OPEN`).
B. Piramidar.
C. Sustituir el stop o el objetivo por los de la nueva señal.

Consecuencias:
- A: es la regla del motor y del asesor, y queda medida.
- B y C: cambian la política.

Recomendación técnica: A.

Qué bloquea: ejecución y test 27.

### OD-P6-39 — Universo y activos tardíos en el sistema · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** Exactamente los 90 activos de P4/P5; ARM y Q8Y0.DE desde la apertura de la barra siguiente a su barra 120; no se elimina ningún activo por FX, sector, región o conveniencia. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Qué universo opera el sistema y cuándo entran ARM y Q8Y0.DE?

Alternativas:
A. Los 90 activos de P4/P5; ARM y Q8Y0.DE desde la apertura de la barra siguiente a su barra 120
   (2024-03-08 y 2025-05-16, o la barra siguiente).
B. Solo los 88 con historia completa.
C. Añadir o quitar activos por FX, sector o región.

Consecuencias:
- A: el mismo universo que P4/P5 y que el benchmark.
- B: excluye por una razón de calendario.
- C: es una exclusión de conveniencia.

Recomendación técnica: A.

Qué bloquea: el universo y el benchmark.

### OD-P6-40 — Caja en divisas · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** Una sola caja en EUR; cada flujo se convierte con el FX causal, sin coste FX adicional (limitación declarada). El texto que sigue es el historial de la pregunta tal como se planteó.

¿Hay una sola caja en EUR o una caja por divisa?

Alternativas:
A. Una sola caja en EUR; cada operación se convierte al FX causal sin coste FX.
B. Cajas por divisa, con conversiones explícitas y su coste.
C. Una caja en EUR con un coste FX por conversión (por ejemplo, x pb).

Consecuencias:
- A: simple; ignora el coste de cambio real.
- B: realista, pero necesita reglas de conversión y de saldo y añade complejidad.
- C: necesita un parámetro de coste FX no congelado.

Recomendación técnica: A, declarando la limitación. No hay datos de coste FX congelados y el mismo
trato se aplica al benchmark.

Qué bloquea: FX y ledger.

### OD-P6-41 — Fuente de las horas de apertura y cierre · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** Calendario = `exchange_calendars` + `exchange_overrides.yaml` + versión de tzdata, en `P6_DATA_ID`. El texto que sigue es el historial de la pregunta tal como se planteó.

¿De dónde salen las horas de apertura y de cierre por sesión?

Alternativas:
A. `exchange_calendars`, la misma librería que ya usa `sessions.py`, **más `exchange_overrides.yaml`**
   (los cierres de D-54 que el calendario no tiene), con la versión de la librería, el hash de los
   overrides y la versión de tzdata en `P6_DATA_ID`.
B. Las horas regulares fijas de `MarketSession`, con una apertura que hay que añadir.
C. La marca de la cosecha.

Consecuencias:
- A: incluye medias sesiones, cambios de horario y los cierres extraordinarios ya decididos. Un
  cambio en los overrides cambia `P6_DATA_ID`.
- B: ignora las medias sesiones.
- C: la marca es la medianoche local, no una hora de mercado.

Recomendación técnica: A.

Qué bloquea: cronología.

### OD-P6-42 — Contexto de mercado del Score v1 en P6 · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** `context_mode = "point_in_time"` obligatorio (R-CTX, D-52/D-53/D-56, `analysis_timestamp` de D-50). Una señal sin contexto exigido (`NO_CALCULABLE_CONTEXT_HISTORY` o equivalente) se excluye y se cuenta. Ni `legacy_v1` ni neutralización. No es idéntico al contexto v1 de producción. El texto que sigue es el historial de la pregunta tal como se planteó.

¿Cómo se calcula el contexto (VIX, tendencia de `^STOXX50E` con SMA200, Asia) del Score v1 en las
poblaciones que usan el score?

Alternativas:
A. La función point-in-time única (R-CTX: D-52, D-53, D-56) vía `market_context_at`, con la señal
   fechada en su `analysis_timestamp` (D-50). `NO_CALCULABLE_CONTEXT_HISTORY` y la falta de dato
   asiático **excluyen** la señal, como en D-55 y D-52, y se publican los recuentos.
B. La misma función point-in-time, pero sustituyendo el contexto no calculable por la regla v1 de dato
   ausente (componente neutral).
C. El camino antiguo de A-02 (`vix_at`/`trend_*` alineados por fecha civil).

Consecuencias:
- A: causal; con la ventana de OD-P6-21 A casi no hay exclusiones por SMA200. **Replica el contexto
  de P3, no el de producción**: producción usa v1 con `legacy_v1` y datos asiáticos intradía, y no
  aplica las exclusiones D-52 y D-55 (D-58). Excluir por un hueco asiático es una regla de laboratorio.
  El sistema primario no es, por tanto, idéntico al asesor en vivo, y se declara.
- B: causal, pero la señal se puntúa con una neutralidad que no se ha validado.
- C: **look-ahead documentado** (D-53: tendencia de una sesión posterior en el 78 % de las barras de EE.
  UU.; contexto europeo posterior para las señales asiáticas). Inaceptable para P6.

Recomendación técnica: A, con `context_mode="point_in_time"` explícito y los tests 40 y 46. El coste
es la diferencia con producción que se acaba de declarar. **Solo en el tratamiento del contexto no
calculable** (excluir frente a neutralizar), la alternativa sin look-ahead que se parece
más a producción es B.

Qué bloquea: la población primaria, la ventana y `system_sha256`.

### OD-P6-43 — Moneda del R decisorio · **CERRADA (D-69): A**

**Decisión del propietario (vinculante):** Deciden `trade_R_local`, `profit_factor_local` y `mean_R_local`, en divisa de cotización y sin FX. El R y el PF en EUR son solo descriptivos. El FX entra íntegro en la equity, el retorno, el CAGR, el drawdown y el exceso. El texto que sigue es el historial de la pregunta tal como se planteó.

¿El profit factor y `mean(trade_R)` que vetan se miden en la divisa de cotización o en EUR?

Alternativas:
A. En divisa de cotización (`trade_R_local`); el R y el PF en EUR se publican como descriptivos.
B. En EUR (`trade_R_EUR`), con el FX dentro.
C. Las dos tienen que cumplirse.

Consecuencias:
- A: mide la política, comparable con P4/P5; la tendencia del euro entre 2022 y 2026 no decide un
  veto de operaciones. El efecto FX sigue entrando en la equity, el CAGR, el drawdown y el exceso, que
  son en EUR.
- B: un 1 % de EURUSD durante una operación vale ~0,25 R. Ruido del orden de las ventajas de P4/P5
  decidiría el veto.
- C: añade el riesgo de B.

Recomendación técnica: A.

Qué bloquea: el criterio, las métricas y `system_sha256`.

---

## Revisión de la ficha

### Primera vuelta (borrador completo, sin commit)

Dos revisores independientes y en solo lectura (Codex y el agente `revisor`), sin simular nada y sin
convertir precios en retornos. Mandato: demostrar que el diseño permite elegir B2/S2 después de mirar,
usa información futura o fabrica cash.
- **Codex:** 3 BLOCKER, 4 IMPORTANTE, 1 MENOR.
- **`revisor`:** 1 BLOCKER, 7 IMPORTANTE, 9 MENOR, 7 OBSERVACIÓN.

Varios hallazgos coinciden. Los dos más graves se comprobaron en el código antes de corregir.

| Hallazgo | Corrección |
|---|---|
| **B** Población decisoria abierta y reabrible tras contar (OD-P6-37) | OD-P6-37 reescrita: una sola primaria decisoria, la descriptiva con su hash y sin veto ni rescate; ningún recuento reabre una OD (secciones 7.6 y 16) |
| **B** Score v1 con contexto `legacy_v1` no point-in-time (`point_in_time.py:152`, `runner.py:245`) y señal fechada en el cierre | OD-P6-42 nueva: R-CTX point-in-time, señal en `analysis_timestamp` (D-50); test 40 |
| **B** Con contexto causal no hay entradas OPERAR antes del 2022-06-14 (SMA200 de `^STOXX50E`): el benchmark invertido y el sistema en cash en la caída de 2022 | Regla de la ventana con el contexto calculable (sección 7.9, OD-P6-21 A); el preflight fija la fecha |
| **B/I** `exchange_overrides.yaml` fuera de `P6_DATA_ID`; 33 sesiones sin barra sin regla | Calendario efectivo = `exchange_calendars` + overrides + tzdata en `P6_DATA_ID`; entrada en la barra siguiente; el tiempo cuenta barras; recuento publicado |
| **I** P3 atribuido a Score v1 (P3 midió v2) | Sección 5 y OD-P6-37 corregidas; v1 = A-02/D-42 sin banda concluyente |
| **I** El RR forma parte del Score v1 (B2 15 puntos, S2/C0 10) | Declarado en la sección 5 y en OD-P6-37; alternativa D (población común) |
| **I** R y PF en EUR con FX deciden vetos | OD-P6-43 nueva: el veto usa el R local; el R en EUR es descriptivo |
| **I** Clave de desempate dependiente de `system_sha256` (palanca de re-sorteo y sin números aleatorios comunes) | Clave `sha256("intradia.p6.desempate.v1" ‖ signal_id)`, común; las correcciones de métricas se recalculan desde el ledger y re-simular exige una D-nn |
| **I** Cash sin la comisión | `cash_requerido` incluye la comisión; test 37 |
| **I** Cobros pendientes en la equity de sizing | Eliminados: el dividendo entra en el cierre ex; sizing una vez por lote (test 44) |
| **I** PF sin pérdidas sin regla | Convención ex ante en la sección 15; test 38 |
| **I** Falta de muestra indistinguible y reabrible | Etiqueta `NO EVALUABLE POR MUESTRA`; ninguna OD se reabre |
| **I** Identidad contable con costes y dividendos contados dos veces | `pnl_bruto_EUR` definido; identidad reescrita (sección 19) |
| **I** Fechas del censo en UTC | `censo_p6.py` publica la marca UTC y la fecha de sesión local por separado, más el calentamiento |
| **M** Sentido del FX | `fx_rate = 1/close(EURxxx=X)`; test 43 |
| **M** Bordes de la ventana, `V_0`, `EXIT_FINAL` en N_min | Sección 7.9 |
| **M** Cash y equity en entradas simultáneas | Secciones 7.3 y 7.4 |
| **M** Dato falso de la última sesión | Corregido: 39 activos el 2026-08-27 y 51 el 2026-08-28 |
| **M** Diferencias con P4/P5 omitidas (ambigüedad, banda de `entry_max`, 41 sesiones) | Sección 5, puntos 5 a 7 |
| **M** Solo split 2:1 | Contrasplit añadido (AZN 0,5), test 36 |
| **M** Corridas no enumeradas; sensibilidad sin su benchmark | Tabla de corridas en la sección 18 |
| **M** Sidecar FX sin tolerancia | Igualdad exacta de la cadena canónica |
| **M** Sin mecánica de ejecución única | Sección 23: `P6_CODE_SHA`, `P6_RUN_HEAD_SHA`, marca exclusiva, sin repetición |
| **M/O** OD-P6-32 sin pregunta; descripción del broker y de `sessions.py` imprecisa; «castiga dos veces»; empates HKG/Europa; prioridad asiática | Corregidos o declarados |

Lo que los revisores verificaron como correcto se mantiene: orden de `evaluate_trade_at_entry`,
`_check_exit`, la señal solo sin posición, el sizing, la cosecha, el FX disponible, las fechas de
calentamiento, las horas UTC de `exchange_calendars` 4.13.2 y la coherencia de `Dividends` con los
splits (NVDA, AVGO, 7203.T, AZN).

### Segunda vuelta

- **Codex:** cierra sus hallazgos previos y encuentra 2 BLOCKER de coherencia (el test 6 con la clave
  antigua; el borde de inicio frente a la «primera señal») y 4 IMPORTANTE (OD-P6-36 sobreafirmaba;
  la comisión sin definir; la regla D-50 fuera del hash; los tests nuevos sin mapear en la matriz,
  más el FX del censo), además de 2 MENOR.
- **`revisor`:** 0 BLOCKER y 0 IMPORTANTE; 8 MENOR (MEN-N1 a N5 y los restos R1 a R3) y 6
  OBSERVACIÓN.

Todos corregidos:
- test 6 con la clave común;
- ventana con pares (señal, entrada), condición de contexto condicionada a OD-P6-37/42 y el VIX fuera
  de la condición de historia;
- fase `SIGNAL` con `analysis_timestamp`;
- valoración a la entrada efectiva hasta el primer cierre (test 45);
- `context_mode="point_in_time"` explícito (test 46);
- OD-P6-42 A ya no dice que replica producción;
- comisión definida;
- regla D-50 en `system_sha256`;
- matriz con los tests;
- `receivable_after` = 0;
- puente rotulado;
- OD-P6-6, OD-P6-23 y OD-P6-36 corregidas;
- el buy-and-hold compra ARM y Q8Y0.DE en la barra siguiente a la 120.

El censo reproduce ahora el bloque FX, la fecha de la SMA200 de `^STOXX50E` y las sesiones sin barra
del calendario efectivo (27).

### Tercera vuelta

- **Codex:** cierra los 8 hallazgos de la segunda vuelta; 0 BLOCKER, 2 IMPORTANTE, 2 MENOR.
  - La «primera señal posible» se atribuía al censo, que solo prueba la SMA200.
  - Faltaba un test de la cadena causal señal → entrada.
- **`revisor`:** cierra 12 de 14; 0 BLOCKER, 0 IMPORTANTE, 2 MENOR y 1 OBSERVACIÓN.
  - OD-P6-37 seguía llamando a la población A «el sistema que se usaría».
  - Un hueco asiático puntual podía mover el inicio.
  - OD-P6-21 A no estaba condicionada.

Todos corregidos:
- la condición de la ventana se limita a la historia de la SMA200 (D-55), y las exclusiones D-52
  posteriores se cuentan sin mover el inicio;
- la frase dice ahora «ninguna entrada OPERAR antes del 2022-06-14»;
- test 48 (cadena causal por plaza);
- OD-P6-37, OD-P6-39 y OD-P6-21 A alineadas.

### Cuarta vuelta (confirmación)

Codex confirma CERRADOS los hallazgos de la tercera vuelta y no encuentra ningún BLOCKER ni ningún
IMPORTANTE nuevo. El `revisor` ya había dejado 0 BLOCKER y 0 IMPORTANTE en la tercera; sus MENOR y su
observación están corregidos arriba.

**Estado del borrador al cerrar la cuarta vuelta (histórico): 0 BLOCKER, 0 IMPORTANTE.** En esa vuelta las
OD-P6-1 a OD-P6-43 aún estaban abiertas; **se cerraron después en D-69**. Texto original: seguían abiertas para el
propietario. Después de cerrarlas: revisión final del pre-registro → `P6_PREREG_SHA`.

## Revisión final del pre-registro (tras D-69)

### Vuelta 1 (sobre `861d820`)

Dos revisores nuevos e independientes, en solo lectura, sin desenlaces y sin SSH: Codex en un hilo
nuevo y un agente `revisor` que no había participado en las vueltas anteriores.

- **Codex:** 0 BLOCKER, 0 IMPORTANTE, 2 MENOR y 1 OBSERVACIÓN.
- **`revisor`:** 0 BLOCKER, **2 IMPORTANTE**, 4 MENOR y 5 OBSERVACIÓN.

| Hallazgo | Corrección (documental, sin cambiar ninguna elección de D-69) |
|---|---|
| **I** El criterio decide con `mean_R_local` agrupado sin declarar la diferencia con INV-14/D-03 (media por bloque), lo que abre una reinterpretación | Excepción a INV-14 declarada en la sección 16 y en D-69: decide `mean_R_local` como fija D-69; la media por bloque por año natural es descriptiva. El estimador entra en `system_sha256` |
| **I** El respaldo FX se contradecía («STOP y OD» frente a «alternativa B») y B no era ejecutable | Sección 11 alineada con D-69; nueva sección 11.1 con B completa (BCE para los tres pares, `timestamp_available` 17:00 Europe/Berlin, festivos TARGET, `1/rate`, contrato y hash); fallo de integridad definido (marca que falte o sobre, o cadena distinta, en las 1.300 marcas); `fuente_fx` en el hash |
| **M** Dividendos de Xetra en otra divisa convertidos por Yahoo a un tipo constante (R6C0.DE, × 1,1587) | Comprobado leyendo solo la columna `Dividends`; limitación declarada en la sección 10.1 y lista de afectados en el preflight |
| **M** Comisión del benchmark dentro o fuera del 1/90 | Dentro: `nominal + comisión = importe asignado`; cash ≥ 0 también en el benchmark |
| **M** Sección 23.6 dejaba redefinir métricas desde el ledger | Solo errores de implementación; un cambio de definición exige una D-nn y nunca cambia la salida |
| **M** Restos anteriores a D-69 («siguen abiertas», «si se cierra así», «si OD-P6-37 C», cobros pendientes en la equity) | Redactados en firme; la línea histórica queda marcada como tal |
| **O** RR del score generalizado de más en D-69 | «con el stop de volatilidad» añadido |
| **O** Qué se parece más a producción (OD-P6-42 frente a OD-P6-37) | Acotado al tratamiento del contexto no calculable |
| **O** Predicado OPERAR sin fijar | Broker neutral (D-04), en la sección 7.6 y en el hash |
| **O** Bytes de la clave de desempate | Fórmula literal en la sección 8.3 y en el test 6 |
| **O** `V_0` frente a `D`; fortaleza relativa en el test 40 | Precisados |
| **O** (Codex) La nota del censo decía «primera señal OPERAR posible» | Cambiada a «SMA200 de tendencia completa; VIX y Asia señal a señal»; censo regenerado (solo cambia esa nota) |

### Vuelta 2 (sobre `aef5c6b`)

- **`revisor`:** cierra sus 11 hallazgos de la vuelta 1. Deja 0 BLOCKER, 0 IMPORTANTE, 2 MENOR nuevos
  y 1 OBSERVACIÓN:
  - **MENOR-A:** frase rota en la sección 23.6;
  - **MENOR-B:** parámetros de la descarga de A sin fijar; un `period="5y"` posterior fallaría la
    integridad y forzaría B;
  - **OBSERVACIÓN-A:** las precisiones añadidas a D-69 son especificación nueva dentro de una
    decisión del propietario y conviene su ratificación expresa.
- **Codex:** la tarea se cortó antes de terminar. En su avance había señalado la frase de la sección
  23.6 y la expresión «`mean_R_local` agrupado» del hash.

Corregido:
- sección 23.6 con la frase literal completa;
- el hash dice «media simple de `trade_R_local` sobre las operaciones cerradas»;
- petición fija de la fuente A (`start`/`end` explícitos, mismas opciones que la cosecha, versión
  registrada; la elección A/B solo depende de la comprobación sobre esa petición);
- el párrafo de D-69 queda rotulado como especificación derivada de la revisión, **pendiente de
  ratificación expresa del propietario**.

### Vuelta 3 (sobre `f657f18`)

- **`revisor`:** cierra los cuatro hallazgos de la vuelta 2. Deja 0 BLOCKER, 0 IMPORTANTE y:
  - **MENOR-C:** `P6_PREREG_SHA` no estaba condicionado a la ratificación de las precisiones de D-69;
  - **OBSERVACIÓN-B:** «primera respuesta completa» de la descarga, ambigua.
- **Codex:** su vuelta se cortó por el límite de uso de su servicio; se relanza sobre el HEAD
  corregido.

Corregido:
- la sección 23 y D-69 exigen la ratificación expresa del propietario antes de `P6_PREREG_SHA`;
- reintentos solo ante excepción; la primera llamada sin excepción se congela y se comprueba una vez.

### Vuelta 4 (sobre `00ce356`)

- **`revisor`:** APROBADO. 0 BLOCKER, 0 IMPORTANTE, 0 MENOR y 0 OBSERVACIÓN. MENOR-C y OBSERVACIÓN-B
  cerrados; el diff `f657f18..00ce356` no introduce nada más.
- **Codex** (hilo nuevo, primera vuelta completa tras sus dos cortes): 0 BLOCKER, 0 IMPORTANTE y 0
  MENOR. Cierra todos los hallazgos de las vueltas 1 a 3. Su única observación es de proceso: la
  ratificación previa al `P6_PREREG_SHA`.

### Ratificación y congelación

El propietario ratificó expresamente las cinco «Precisiones de la revisión final» de D-69 el
2026-10-03. Con eso y las dos revisiones en 0 BLOCKER y 0 IMPORTANTE, el pre-registro queda congelado
en el commit que añade `evidence/2026-10-03-T-022-p6-prereg-final/`, cuyo HEAD es `P6_PREREG_SHA`.


## Cierre (2026-10-05)

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

- **Ejecución única:** marca a las 10:11:49 UTC, que hashea `apertura-payload.json`
  (`7823fe8d…8a7e`). No hay `p6-parada.json` y la consola archiva `código de salida: 0`. P6 no se
  repite.
- **Resultado:** `evidence/2026-10-05-T-022-p6-cierre/resultado-p6.md` (transcripción de `run/`, sin
  recalcular) y D-70. B2 `NO PASA` y S2 `NO PASA`, con salida `[]`. La causa formal es exclusivamente
  `excess_CAGR_pp <= 0`.
- **Descriptivo, sin efecto en la salida:** C0, la sensibilidad de 10 pb, el puente de todas las
  barras, la exposición, el cash y los subperiodos.
- **Revisión final independiente** sin ningún BLOCKER ni ningún IMPORTANTE (`revision-final.md`).
  GATE P6 cruzado (D-70, `gate-p6-final.md`).
- **Handoff a P7: ninguno.** P7 no recibe ninguna política y A-07 sigue **BLOQUEADO**. Cualquier
  corrección de la selección de señales, la prioridad, el sizing, el uso del cash, la geometría o el
  benchmark es investigación nueva, con ficha y pre-registro propios, y no cambia la etiqueta de P6.
- **Producción no cambia:** `config.yaml` sigue en `"1.0"` con C0, Score v2 sigue inactivo y la Pi en
  `v0.4.1`.
