# Protocolo de investigación

**Estado: acordado, sin implementar.** Este documento fija *cómo* se mide,
antes de medir. Se escribe ahora a propósito: un protocolo redactado después
de ver resultados no es un protocolo, es una justificación.

Redactado el 2026-08-29. Los hechos marcados como *verificado* se
comprobaron contra el código en esa fecha; el resto son decisiones de diseño.

## Por qué existe este documento

Hasta ahora el proyecto medía con `advisor/backtest/`, y la conclusión
implícita era que mejorar el bot consistía en mejorar la estrategia. Al
revisar qué puede concluir realmente ese backtest aparecieron varios sesgos
que comparten una raíz: **el motor que ejecuta una estrategia y el motor que
investiga si una idea tiene ventaja no pueden ser el mismo**.

El primero debe ser conservador cuando los datos no permiten saber qué pasó
(ante la duda, asumir lo peor). El segundo debe conservar esa incertidumbre
en vez de resolverla, porque resolverla arbitrariamente introduce un sesgo
que luego se confunde con señal.

De ahí la regla que gobierna todo lo que sigue:

> El motor de ejecución puede ser conservador. El motor de investigación debe
> registrar «no observable con estos datos» en vez de elegir un supuesto.

## Hallazgos que motivan el protocolo

### 1. `trades_todas` no son todas las señales (verificado)

En `advisor/backtest/engine.py`, la generación de señal vive dentro de
`if position is None and j < len(df) - 1`. Bajo `POLICY_TODAS` el motor está
en posición casi siempre, así que **una señal que llega con posición abierta
no se registra en ninguna parte**.

La tabla «¿ORDENA LA PUNTUACIÓN?» de `advisor/backtest/report.py` no mide
todas las señales: mide las que cayeron con el hueco libre. Para una
comprobación global es tolerable. Para recalibrar umbrales por banda no lo
es, porque la ocupación está correlacionada con lo que se quiere medir: una
banda que se dispara en tramos tendenciales queda infra-muestreada justo
después de sus propias operaciones.

### 2. `r_multiple` es bruto y `won` es neto (verificado)

`BacktestTrade.r_multiple` divide por el riesgo sin descontar costes;
`BacktestTrade.won` usa `net_return_pct`, que sí los descuenta. Hoy conviven
en la misma tabla, así que hay operaciones contadas como perdedoras con R
positivo.

El sesgo no es constante. Vale `cost_pct / risk_pp` por operación, o sea que
**es mayor cuanto más ajustado el stop**:

```
coste ida+vuelta 0,20 pp
    stop 4 pp → 0,05 R
    stop 2 pp → 0,10 R
    stop 1 pp → 0,20 R
```

Eso importa porque el sistema ya favorecía los stops ajustados por otra vía
(ver punto 3): el R bruto oculta exactamente la penalización que esos stops
sufren.

### 3. El ratio beneficio/riesgo mezcla dos filosofías (verificado)

Con `target2_structural: false`, `stop = 2·ATR` y `objetivo 2 = 3·ATR`, el
ratio vale 1,5 salvo que un soporte cercano acerque el stop, en cuyo caso
*sube*. Es decir, la dimensión de 20 puntos premia estar cerca del mínimo de
60 sesiones, mientras el resto del score premia rupturas, huecos alcistas y
RSI 50-70. Dos tesis opuestas sumando a la misma nota.

Detalle completo en `docs/ratio-beneficio-riesgo.md`.

### 4. Exigir el ratio en el precio real de ejecución colapsa `entry_max`

Con la geometría actual, imponer `RR(entrada) ≥ 1,5` da:

```
(P + 3A − E) / (E − (P − 2A)) ≥ 1,5   →   2,5·P ≥ 2,5·E   →   E ≤ P
```

Exactamente el precio de señal: `entry_max_atr: 0.75` quedaría muerto y solo
entrarían los pullbacks. Para tolerar 0,75·ATR de persecución conservando
1,5 harían falta objetivos de 4,875·ATR, por encima del objetivo 3 actual.

**Por eso el filtro de RR no se toca todavía.** Corregirlo sin tocar la
geometría no afina un filtro: cambia la política de entrada. Se decide en P4
con medición, no antes.

### 5. Los precios están ajustados retroactivamente (verificado)

`advisor/data/market_data.py` llama a `ticker.history(...)` sin pasar
`auto_adjust`. En yfinance 1.7.0 el valor por defecto es `True`, así que
Open, High, Low y Close vienen **ajustados por splits y por dividendos**.

Dos consecuencias:

- La serie histórica de un activo se reescribe cada vez que paga dividendo,
  no solo cuando hay split. Con 38 europeas y 41 estadounidenses en el
  universo, eso es trimestral para casi todo. Un join entre dos campañas
  separadas por un mes compara dos reconstrucciones distintas de la misma
  historia.
- En la serie ajustada **el hueco del día ex-dividendo desaparece**. En la
  realidad el precio abre bajando el importe del dividendo y un stop ceñido
  puede saltar; en los datos, no. El ajuste subestima la tasa de stops, y lo
  hace más cuanto más estrecho el stop y más alta la rentabilidad por
  dividendo: justo las variantes que la comparación de geometrías va a
  evaluar.

Lo que **no** se ve afectado: todo lo que sea ratio (`atr_pct`, `risk_pp`,
`gross_R`, `net_R`, MAE/MFE en R) es invariante a un ajuste multiplicativo.

La consecuencia de diseño es que **una sola serie no sirve para las dos
cosas**, y de ahí la separación de P2.0 entre serie de señal y serie de
ejecución.

### 6. La ambigüedad intrabarra sesga las bandas de score

`P(+kR antes de −1R)` no es observable en velas diarias cuando una misma vela
toca los dos niveles. El motor de ejecución asume stop, que es la elección
correcta *para ejecutar*.

Para investigar no lo es. La fracción de velas ambiguas crece con el rango de
la vela, y las bandas altas de score están definidas en buena parte por
volumen anormal, hueco y ruptura — es decir, por velas de rango grande. El
supuesto «primero el stop» penaliza más a la banda 80+ que a la 50-60. Si la
monotonicidad sale plana, no se sabría si es que el score no ordena o si es
el convenio de desempate.

No hay forma de resolverlo con datos diarios. Sí de no esconderlo: ver P2.3.

### 7. El coste por barra hace cara la fuerza bruta (medido)

`_signal()` recalcula todos los indicadores sobre `df.iloc[:j+1]` en cada
barra: es cuadrático. Medido el 2026-08-29 sobre una serie sintética:

```
1,11 ms por barra con prefijo ~500
→ ~10-15 min por pasada completa (2.500 barras × 107 activos)
```

Tolerable una vez; prohibitivo repetido por cada celda de una rejilla de
parámetros. De ahí la decisión de P2.2: guardar los *insumos* de los niveles,
no los niveles.

## Los dos motores

| | Simulación de cartera | Event study |
|---|---|---|
| Unidad | operación admitida por la política | señal potencial por barra |
| Ocupación | una posición por activo | sin estado de posición |
| Solapamiento | no | sí |
| Sirve para | retorno, drawdown, capital, nº de operaciones, viabilidad real | calibración del score, bandas, excursiones, geometría |
| Ambigüedad OHLC | se resuelve conservadora (stop primero) | se conserva como estado propio |
| Comparaciones | sistemas completos, no pareadas | pareadas por `signal_id` |

No se intenta que `POLICY_TODAS` haga las dos cosas. Son experimentos
distintos y el código debe reflejarlo.

Hay además una razón dura para no emparejar en el simulador de cartera:
cambiar el stop cambia `levels.rr_ratio`, que alimenta el veto de RR de
`classify()` y la condición de admisión `pending["stop"] < bar_open`. Dos
geometrías con stop distinto **no generan el mismo conjunto de señales**, y
la divergencia se propaga: una operación distinta al principio altera la
ocupación y por tanto qué señales posteriores llegan siquiera a evaluarse.

## Protocolo

### P2.0 — Congelar los datos, no la vista ajustada

Congelar únicamente la descarga que devuelve yfinance resolvería
reproducibilidad, pero no fidelidad de ejecución. Se congela el **material
bruto** y las vistas se derivan de forma determinista.

Se descarga con `auto_adjust=False` y se conserva:

```
OHLCV en bruto
Dividends
Stock Splits
downloaded_at
provider + versión
series_hash
```

De ahí se derivan dos series, y la distinción es la que arregla el hallazgo 5:

- **Serie de ejecución** — ajustada por splits pero **no** por dividendos.
  Determina si una apertura, un stop o un objetivo se habrían tocado
  realmente. Así no aparece un desplome falso del 50 % por un split 2:1, pero
  sí permanece el hueco económico del día ex-dividendo, que en la realidad
  puede activar un stop ceñido.
- **Serie de señal** — la que alimenta indicadores y scoring. Si conviene que
  sea la misma o una serie de retorno total es una decisión separada, que se
  estudia con datos y **no se hereda del valor por defecto de yfinance**.

Cada observación queda identificada por dos claves:

```
signal_id       = asset + horizonte + timestamp     (el evento económico)
data_vintage_id = la reconstrucción histórica usada
```

`data_vintage_id` registra al menos: `downloaded_at`, `provider` y versión,
`symbol`, `interval`, `start`/`end`, la política de ajuste aplicada a cada
vista, y un `series_hash`. El hash se calcula sobre una representación
canónica de las columnas realmente usadas (timestamp, open, high, low, close,
volume), ordenada y con serialización determinista — no sobre un CSV
arbitrario.

**Una comparación pareada exige `data_vintage_id` idéntico, o aborta.** Sin
esa comprobación, un join puede funcionar técnicamente mientras compara dos
historias distintas del mismo activo.

**Pendiente anotado, no resuelto en P2**: si una posición de horizonte medio
atraviesa una fecha ex-dividendo, el P&L económico debería incluir el
dividendo cobrado. No hace falta resolverlo para construir el laboratorio,
pero sí antes de interpretar rentabilidades de medio plazo, o se estaría
midiendo el hueco a la baja sin el ingreso que lo compensa.

### P2.1 — Contrato numérico

Unidades explícitas en el nombre. Nada de `risk_pct` con dos significados:
hoy `Levels.risk_pct` está en puntos porcentuales y es fácil escribir una
fracción con el mismo nombre.

| Campo | Unidad | Neto/bruto | Semántica |
|---|---|---|---|
| `gross_return_pp` | pp | bruto | retorno de precio |
| `net_return_pp` | pp | neto | después de costes |
| `risk_pp` | pp | — | riesgo inicial, `(entrada − stop) / entrada × 100` |
| `gross_r_multiple` | R | bruto | `gross_return_pp / risk_pp` |
| `net_r_multiple` | R | neto | `net_return_pp / risk_pp` |
| `mae_r` | R | precio | excursión adversa; positivo = adverso |
| `mfe_r` | R | precio | excursión favorable; positivo = favorable |

Identidades que deben cumplirse exactamente, con test:

```
gross_return_pp / risk_pp = (salida − entrada) / (entrada − stop)
net_R = gross_R − cost_pct / risk_pp
```

Test de unidades con números cerrados, no aserciones de signo:

```
entrada 100, stop 95, salida 110, cost_pct 0,20
    risk_pp          == 5,0
    gross_return_pp  == 10,0
    gross_R          == 2,0
    net_return_pp    == 9,8
    net_R            == 1,96
```

Toda evaluación económica —`won`, expectancy, payoff, profit factor, mediana,
percentiles— se construye sobre **R neto**. `gross_R` se conserva para
estudiar geometría de precios aislada, pero los dos nunca se mezclan en una
misma conclusión.

`Dimension.points` deja de redondear: el `round(..., 2)` pertenece a la
presentación. Una ablación cerca de un corte (69,98 frente a 70,02) no puede
depender de acumulación de redondeos.

```
float completo → cálculo
round          → informe y Telegram
```

### P2.2 — Instrumentación de la señal: solo primitivas

`SignalObservation` es ligero y numérico. Sin objetos `Score`, y sobre todo
**sin los `Component.detail`**: son texto formateado inútil para investigar y,
con ~107 activos × ~2.500 barras ≈ 270.000 observaciones, son el grueso de la
memoria.

Guarda:

```
signal_id, data_vintage_id
asset, horizonte, signal_idx, signal_timestamp
score_value, evaluable_max
por dimensión: points (sin redondear), max, available
insumos de niveles: price, atr, low_lookback, high_lookback, ema_fast
```

**No guarda `stop`, `target1`, `target2`, `target3` ni `rr_ratio`.** Esos son
resultados de una política concreta, y P4 existe precisamente para cambiar esa
política: tomarlos como fuente de verdad congelaría dentro del dataset la
geometría que se quiere poner a prueba.

`signal_idx` y `signal_timestamp` permiten que cada variante consulte la
trayectoria futura dentro del histórico ya congelado, en vez de duplicar esa
trayectoria dentro de cada observación.

La descomposición por dimensión permite reconstruir cualquier ablación sin
re-simular:

```
Score          = points / evaluable_max × 100
Score_sin_X    = (points − points_X) / (evaluable_max − max_X) × 100
```

`Dimension.points` deja de redondear (ver P2.1): dos decimales prematuros son
ruido artificial justo donde más molesta, en las observaciones próximas a un
umbral.

#### Vectorización causal: entra aquí, no como optimización posterior

`_signal()` recalcula hoy todos los indicadores sobre `df.iloc[:j+1]` en cada
barra. Es trabajo repetido sin beneficio metodológico, porque **todos los
indicadores del proyecto son causales**: `atr` usa `shift(1)` y `rolling`;
`sma` y `rsi` usan `rolling`; `ema` y `macd` usan `ewm(adjust=False)`, cuya
recursión depende solo de valores anteriores. Calcularlos vectorizados sobre
la serie completa e indexar por fecha da los mismos valores.

```
serie completa congelada
        ↓
ATR, RSI, EMA, MACD, rolling highs/lows, volumen…   (una vez)
        ↓
indexar por fecha → SignalObservation
```

**Test de equivalencia, obligatorio antes de retirar el camino por prefijos.**
Para una muestra de barras se compara el valor vectorizado con el recalculado
sobre el prefijo:

- magnitudes en coma flotante: `assert_allclose` con tolerancia muy estrecha,
  no igualdad binaria;
- decisiones discretas —`available` de cada componente, clasificaciones de
  indicador, banderas—: igualdad exacta.

Lo que el test garantiza, y esta es su única razón de existir: **calcular el
futuro no altera el valor en t**. Si alguien introduce más adelante un
`shift(-1)`, un `rolling` centrado o cualquier otra forma de look-ahead, este
test tiene que romperse.

#### Consecuencia sobre el coste de P4

Con esta arquitectura la rejilla **no vuelve a ejecutar `_signal()`**. Se
construye una única tabla versionada de ~270.000 observaciones, y cada
variante es aritmética elemental sobre ella:

```
levels = compute_levels_from_inputs(
    obs,
    atr_stop_multiple=...,
    target_atr_multiples=...,
    target2_structural=...,
)
```

más la simulación sobre la trayectoria futura ya congelada. El coste caro
—indicadores, rolling, EMA, RSI, MACD, score— se paga **una vez por data
vintage** en lugar de una vez por celda. Es la diferencia entre los 10-15
minutos del hallazgo 7 repetidos treinta veces y pagados una sola.

Beneficio secundario, y no menor: todas las variantes consumen literalmente
las mismas características de entrada, así que una diferencia entre ellas no
puede venir de haber recalculado los indicadores de otra manera.

### P2.3 — Event study

Sobre **todas las barras elegibles**, no sobre las admitidas por `classify()`.
Sin estado de posición, con solapamiento permitido.

Produce dos familias de resultados:

- **Administrado**: respeta stop, objetivo y duración máxima. Responde cuánto
  retroceden las ganadoras y cuánto avanzan las perdedoras antes de fallar.
  La parte informativa es la MAE de las ganadoras: la MAE de una salida por
  stop vale 1,0 R por construcción y no dice nada.
- **Potencial (sin objetivo)**: mantiene stop y horizonte, elimina el
  objetivo, y registra `MFE_unbounded_R`. Es el único modo que permite elegir
  un objetivo, porque con objetivo activo la MFE está truncada por el propio
  objetivo que se quería evaluar.

La ambigüedad intrabarra se conserva como estado, no se resuelve:

```
TARGET_FIRST | STOP_FIRST | AMBIGUOUS
```

Un hueco de apertura **no** es ambiguo: si la vela abre por debajo del stop o
por encima del objetivo, está resuelto. Solo es ambigua la vela cuya apertura
queda entre ambos y que toca los dos niveles.

Las probabilidades se publican como intervalo, nunca como número:

```
lower = seguros / total
upper = (seguros + ambiguos) / total
```

Si el intervalo de la banda 80+ no se solapa con el de la 50-60, la
conclusión es sólida. Si se solapa, no la hay. Una banda con mucha ambigüedad
es en sí misma un resultado: los datos diarios no tienen resolución para
juzgar ese setup.

### P2.4 — Diagnóstico y ablación del score actual

Sobre la misma población de señales del event study, y solo ahí: `score`
completo, `score` sin RR, contribución del RR, `risk_pp`, RR bruto y RR neto.

El orden importa y es una dependencia, no una preferencia. Si la ablación se
hiciera sobre operaciones venidas de `classify()`, la población ya habría
pasado por el veto de RR, y se estaría midiendo la capacidad de ordenación
del RR sobre una muestra que el propio RR depuró.

### P2.5 — Capacidad estadística, antes de cualquier rejilla

La precisión la fija el número de **bloques** independientes, no el de
operaciones. Antes de decidir qué probar, se calcula por horizonte:

```
SWING
  Histórico útil:  2.430 sesiones
  Bloque:             60 sesiones
  Bloques:            40
  Resolución:      razonable

MEDIO
  Histórico útil:  2.430 sesiones
  Bloque:            300 sesiones
  Bloques:             8
  Resolución:      insuficiente para comparación fina
```

El bloque debe superar el periodo de tenencia (`MAX_HOLD_BARS`: 40 en swing,
250 en medio). Para medio eso deja del orden de ocho bloques en diez años, y
ninguna cantidad de operaciones lo arregla. Tener 20.000 operaciones y creer
que `n = 20.000` cuando la información independiente se parece a `n ≈ 8` es
el error que este gate existe para evitar.

Se publica un `experimental_resolution` en `{HIGH, MEDIUM, LOW,
INSUFFICIENT}` calculado a partir del número de bloques, su longitud, la
cobertura de regímenes, la censura y la amplitud de los intervalos. Para
medio puede acabar siendo `LOW` aunque haya miles de señales: la limitación
es estadística, no computacional.

Gate de censura, con `_exit_census` que ya existe: `EXIT_FINAL` no es una
salida estratégica, es censura administrativa del experimento. Una ventana
con demasiada queda marcada como no concluyente. Y una ventana más corta que
`MAX_HOLD_BARS` es inválida por definición para ese horizonte.

Si la capacidad es insuficiente, la salida correcta del informe es
**NO CONCLUYENTE**, no un Sharpe con apariencia científica.

### P2.6 — Infraestructura de incertidumbre

La unidad de remuestreo es el **bloque temporal completo, con todos los
activos dentro**. Nunca operaciones sueltas: 107 activos con betas altas
ganan y pierden a la vez, así que un mes alcista genera cientos de
operaciones que son, en la práctica, una sola observación de régimen.
Remuestrear operaciones fingiría que AAPL, NVDA, AMD y META el 12 de marzo
son cuatro datos independientes.

Al entrar un bloque, entra entero: se preserva la correlación transversal, el
régimen, la volatilidad común, la agrupación de señales y la autocorrelación
local.

Para comparaciones pareadas, se bootstrapea `ΔR` **por bloques**, no por
señal:

```
ΔR_i = R_B,i − R_A,i        para cada signal_id
bloque = todos los ΔR de todos los activos en esa ventana temporal
```

El pareado controla la correlación entre A y B; el bootstrap de bloques
controla la dependencia de tiempo y mercado.

La longitud del bloque se explora (40, 60, 80, 120 sesiones en swing) y se
comprueba la sensibilidad del resultado a esa elección.

**Heterogeneidad frente a ruido.** «Prefiero esta política porque es más
estable» no es defendible mirando cuatro números por subperiodo: con pocos
bloques por ventana, una tabla puede parecer errática solo por muestreo. Se
compara la dispersión observada con la que cabría esperar bajo un efecto
verdadero constante, estimada con el mismo bootstrap:

```
Dispersión observada: 0,08R   esperada por ruido: 0,06-0,11R  → compatible
Dispersión observada: 0,31R   esperada por ruido: 0,05-0,12R  → régimen
```

Se reportan tres cosas, sin fórmula secreta que decida por nosotros:

| Política | ΔR medio | IC bloque | Heterogeneidad |
|---|---|---|---|
| A | +0,09 | +0,02 / +0,16 | compatible con ruido |
| B | +0,14 | −0,04 / +0,31 | alta |
| C | +0,04 | +0,01 / +0,07 | baja |

Y se prefiere el intervalo y la heterogeneidad al p-valor: `Δ = +0,08 R,
IC [−0,01, +0,17]` dice más que `p = 0,047`.

## Orden de trabajo

| Fase | Qué |
|---|---|
| P2.0-P2.6 | Todo lo anterior: laboratorio |
| P3 | Sacar el RR del score, comprobar ordenación, recalibrar umbrales por horizonte |
| P4 | Geometría: comparaciones pareadas en event study con bootstrap de bloques |
| P5 | Reducir a las regiones robustas de parámetros |
| P6 | Backtest completo de las supervivientes, como sistemas, no como trades pareados |
| P7 | Walk-forward y holdout |

P4 y P5 no seleccionan sobre todo el histórico para después validar: eso
reintroduciría selección retrospectiva. La comparación se hace ya bajo
validación temporal.

## Reglas del protocolo, fijadas de antemano

1. **Métrica primaria**: expectancy neta en R. Se declara antes de mirar.
2. **Restricciones**: muestra mínima, profit factor > 1, drawdown máximo,
   expectancy > 0. Las secundarias (drawdown, estabilidad entre ventanas,
   número de operaciones, dispersión) solo desempatan.
3. **Se busca meseta, no máximo.** `2,5R → 0,05 · 3,0R → 0,31 · 3,5R → −0,04`
   es un pico de sobreajuste, no un hallazgo.
4. **Se cuenta y se publica el número total de comparaciones realizadas.** El
   walk-forward controla la selección temporal, no la multiplicidad.
5. **Umbrales por horizonte.** `min_score_operar` y `min_score_vigilar` son
   hoy un único valor global, pero `simulate_asset` solo admite swing y medio.
   Un corte calibrado en swing aplicado a intradía es una extrapolación, y
   debe declararse con `calibrated: false` para que el informe no presente un
   84/100 de intradía con el mismo peso epistemológico que uno de swing.
   `classify()` ya recibe `horizonte`, así que el cambio está contenido.
6. **Swing y medio se calibran por separado.** Que ambos sean backtesteables
   no implica que compartan distribución.
7. **El holdout se mira una vez.** No se usa para elegir parámetros,
   desempatar, fijar umbrales, quitar un indicador ni cambiar objetivos. Si
   sale mal, la conclusión es que el modelo no generaliza — no se vuelve a
   desarrollo, se ajusta algo y se consulta otra vez el mismo holdout.

## Lo que este protocolo no arregla

- **Sesgo de supervivencia**: el universo son 107 activos elegidos en 2026 y
  medidos hacia atrás. Ninguna partición temporal lo corrige.
- **Intradía**: `simulate_asset` solo admite swing y medio, y el histórico de
  15 minutos de yfinance llega a 60 días. Todo lo medido aquí es swing y
  medio; intradía sigue siendo radar, no estrategia validada.
- **Fundamentales**: la dimensión sigue excluida y la nota se normaliza sobre
  los puntos evaluables. Si además sale el RR, el score real se calcularía
  sobre 60 puntos de 100, lo que refuerza la necesidad de recalibrar los
  umbrales en vez de heredarlos.
- **Acciones corporativas**: se conservan dividendos y splits, pero no
  fusiones, escisiones, cambios de ticker ni exclusiones de cotización. Un
  activo que hoy existe puede tener un histórico que en su día perteneció a
  otra cosa.
- **Proveedor único**: todo depende de yfinance, sin segunda fuente con la
  que contrastar. Un error sistemático del proveedor sería indistinguible de
  un hallazgo.
