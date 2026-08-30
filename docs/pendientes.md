# Pendientes del asesor

Estado al **30 de agosto de 2026**. P0, P1, P2.0, P2.1 y P2.2 están en `main`
y pusheadas a GitHub (`b732e79`). La rama
`sizing-riesgo-y-benchmark-regional` ya está fusionada en fast-forward.

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
gobierna cualquier medición futura.

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

**Hecha también P2.0.** `advisor/research/vintage.py` congela el material
bruto descargado con `auto_adjust=False` y `actions=True`, deriva las tres
vistas y verifica los hashes al cargar. Verificado contra la red que en ese
modo yfinance **ya devuelve el OHLC ajustado por splits** (NVDA cerró a 120,888
el 2024-06-07, post-split del 10:1) y que `Close` difiere de `Adj Close`, o sea
que el dividendo no está aplicado. Por eso las vistas no reconstruyen nada.

`gap_for_catalyst` existe como dato pero **NO está enchufada al scoring**, a
propósito. Enchufarla cambiaría puntuaciones en vivo y eso se mide antes. Con
AAPL la corrección del hueco vale ~0,09 pp, pero el scoring da 6 puntos si el
hueco es ≥ 2 % y 3 si es ≥ 1 %: una europea que reparte 4 % anual en un solo
pago genera un hueco mecánico de ~2 pp, justo encima del primer umbral. Ahí la
vista no afina, cambia de tramo.

---

## Lo siguiente, por orden

1. ~~Fusionar a `main` y pushear.~~ **Hecho el 2026-08-30.**
2. ~~Lanzar una cosecha real del universo completo.~~ **Hecha el 2026-08-30**,
   con `--period 5y` (el valor por defecto del subcomando, no los 2 años de
   `config.yaml`). Los 126 símbolos entraron, ninguno falló, 18 MB en disco, y
   la relectura verifica los tres hashes —manifiesto, serie y acciones
   corporativas— sin excepción. `data/vintages/` está en `.gitignore`, así que
   la cosecha vive solo en este portátil: para reproducirla en otra máquina hay
   que volver a congelar y comprobar que sale el mismo `data_vintage_id`.

   `data_vintage_id`:
   `071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841`

   Cobertura: mediana de 1255 barras, máximo 1825 (las tres criptos, que cotizan
   también en fin de semana) y mínimo 446 (`Q8Y0.DE`), con `ARM` en 742 y
   `DFEN.DE` en 863 porque son jóvenes. Los asiáticos se quedan en ~1220 barras
   porque yfinance no da 5 años completos de esas plazas. **P2.5 tendrá que
   tratar la profundidad como variable por activo, no como constante.**

3. **Pasadas por evento.** Sigue siendo lo único de toda la lista que mejora el
   bot en producción; el resto del laboratorio no cambia nada de lo que el
   asesor hace hoy. Decisión ya tomada: temporizador fijo autodescartable,
   con IDs deterministas por evento y pasada para evitar duplicados, y dos
   alarmas — `events.yaml` sin ningún evento futuro, y último evento a menos
   de 60 días. El calendario macro caduca el **2027-12-16**.
4. ~~P2.3, el event study.~~ **Hecho el 2026-08-30**, en la rama
   `event-study-p23` (`8a5dd0b`), sin fusionar. `advisor/research/event_study.py`
   más el subcomando `event-study`. 121.786 señales sobre 107 activos.
   Resultados en la sección 11.

5. **Cerrar el flanco estadístico antes de usar las bandas.** P2.5 deja de ser
   una fase futura y pasa a ser un requisito: la banda 80+ tiene 78
   observaciones y no sostiene ninguna conclusión (ver sección 11).
6. Después: P2.4 ablación · P2.6 incertidumbre · P3 score sin RR y
   recalibración por horizonte · P4 geometría · P5 reducción a regiones
   robustas · P6 backtest de sistemas · P7 walk-forward y holdout.

### Nota de método, por si se pierde

Las tres entregas de esta tanda llegaron con la suite en verde y aun así
tenían defectos reales que solo aparecieron al comprobarlas con datos
auténticos: el sizing mezclaba euros con divisa nativa (3 acciones de Toyota
donde iban 566), el test de equivalencia no pasaba nunca un benchmark y dejaba
pasar una divergencia del 100 % de las barras, y la cosecha congelada no se
podía releer porque el CSV guardaba 12 dígitos y el hash usaba 17. En los tres
casos los tests pasaban porque usaban datos sintéticos «redondos». **Verde no
es verificado**: hay que ejercitar el camino real.

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

## 10. Los datos europeos llegan con retraso frente a los de EE. UU.

Medido el **domingo 2026-08-30**, siendo el viernes 28 la última sesión. Al
agrupar los 126 símbolos de la cosecha por su última barra aparece un escalón
por plaza que no es aleatorio:

| Última barra | Símbolos | Plazas |
|---|---|---|
| vie 28 (al día) | 53 | EE. UU. e índices estadounidenses |
| jue 27 (−1 sesión) | 25 | Japón, Hong Kong, Corea, España, `^FCHI` |
| mié 26 (−2 sesiones) | 45 | **Xetra (31), Euronext, Milán, Copenhague** |
| dom 30 | 3 | cripto, que cotiza en fin de semana |

**No es un artefacto de la cosecha: es el proveedor.** Comprobado pidiendo de
nuevo los datos en vivo, con `period=1mo` y con `period=5y`: `SAP.DE` y
`ASML.AS` terminan el 26 en los cuatro casos, mientras `AAPL` termina el 28 y
`7203.T` el 27. La serie europea no está truncada por la cola, va retrasada
entera.

Por qué importa: el asesor recomienda para ejecutar en **Trade Republic**, o
sea justo las plazas del tramo de −2 sesiones, y hace cuatro pasadas diarias.
Si el retraso también se da entre semana, las señales de los 31 instrumentos
de Xetra se calculan sobre un cierre de hace dos sesiones sin que el informe lo
diga. Es la misma familia de fallo que el precio obsoleto del otro bot.

**Lo que NO está medido, y no hay que darlo por sabido:** esto es *una* medición
hecha en fin de semana. Puede ser un retraso permanente del proveedor o un
rezago de fin de semana que se pone al día el lunes. Antes de tocar nada hay
que **repetir la medición un día de mercado**, comparando la última barra por
plaza a la misma hora.

**Qué hay que decidir, si se confirma:** si el informe declara la antigüedad
del dato por activo (barato, honesto, y encaja con separar señal de
ejecutabilidad del §9) o si se busca otra fuente para las plazas europeas
(caro). No degradar recomendaciones en silencio.

**No afecta a la cosecha ni a P2.3:** al event study le sobran dos sesiones de
cola sobre medianas de 1255 barras.

## 11. Resultados de P2.3 y el flanco que abren

Pasada completa sobre la cosecha `071ddb2b`, horizonte swing, coste 0,20 %:
121.786 señales sobre 107 activos.

| Banda | n | P(objetivo antes de stop) | IC 95 % (muestreo) | net_R medio |
|---|---|---|---|---|
| <50 | 51.268 | 0,402 | [0,398, 0,406] | 0,13 |
| 50-60 | 44.848 | 0,410 | [0,406, 0,415] | 0,09 |
| 60-70 | 23.027 | 0,443 | [0,437, 0,449] | 0,12 |
| 70-80 | 2.565 | 0,477 | [0,458, 0,496] | 0,21 |
| **80+** | **78** | 0,500 | **[0,392, 0,608]** | 0,20 |

**Lo bueno: el score ordena.** La progresión es monótona y los intervalos de
muestreo de las cuatro primeras bandas se separan. Es la primera evidencia
medida de que la puntuación tiene capacidad de ordenación.

**Lo que hay que mirar antes de creerse la banda alta:** 80+ tiene 78
observaciones de 121.786, el 0,06 %. Su intervalo de muestreo mide 0,217 de
ancho y se solapa con el de 50-60. No sostiene ninguna conclusión.

### La regla de decisión del protocolo se queda corta

El protocolo dice: «Si el intervalo de la banda 80+ no se solapa con el de la
50-60, la conclusión es sólida». Aplicada literalmente daría por sólida la
banda 80+, porque ese intervalo es el de **ambigüedad intrabarra** y ha salido
degenerado: `[0,500, 0,500]`. Pero el intervalo que importa aquí es el de
**muestreo**, y ese sí se solapa.

Son dos incertidumbres distintas y el protocolo solo instrumentó una. **La
regla no se cambia a posteriori** —eso es justo lo que el documento prohíbe—,
pero P2.5 deja de ser opcional: sin capacidad estadística, las bandas altas no
pueden calibrar nada en P3.

### La ambigüedad intrabarra resultó ser irrelevante, y está medido

27 velas ambiguas de 121.786, el 0,02 %. No es un fallo de detección: con
stop a 2·ATR y objetivo 2 a 3·ATR, una vela necesita abarcar **5·ATR** para
tocar ambos niveles.

El hallazgo 6 del protocolo suponía que la ambigüedad penalizaría más a la
banda 80+ que a la 50-60 y contaminaría la monotonicidad. **A esta geometría
no ocurre.** La advertencia sigue siendo válida como principio: si P4 acerca
el objetivo, la fracción ambigua subirá y habrá que volver a mirarla. Por eso
el estado se conserva aunque hoy no mueva nada.

### Riesgo abierto: los timestamps de la cosecha son cadenas, no `Timestamp`

`read_raw_csv` conserva el índice como texto a propósito, para que el hash sea
estable. La consecuencia es que `SignalObservation.signal_timestamp` y
`ManagedEvent.exit_timestamp` están **anotados como `pd.Timestamp` y contienen
`str`**. Hoy no rompe nada —`_align()` reconvierte a fechas y restaura el
índice, y está verificado que el benchmark llega a las seis dimensiones—, pero
cualquier aritmética de fechas en P2.5 o P4 fallará o, peor, ordenará
lexicográficamente sin avisar. `mypy` no lo habría dejado pasar, y `mypy` es
justo el gate caído.

## 12. Desplegado en la Pi el 2026-08-30

La Pi pasó de `e952f71` a `1f31d2d`, ocho commits. Hasta ese día producción
corría **sin P0 ni P1**: dimensionaba por convicción y comparaba todo contra el
Euro Stoxx 50.

Verificado en la propia Pi, no en local: suite completa con Python 3.13
(313 pasan, 1 saltado porque `data/vintages/` no existe allí), unidades
instaladas conservando las cuatro horas, `TimeoutStartSec=1800`,
`Persistent=false` y las directivas de log, `verificar-systemd` diciendo
«alineadas», pasada por evento autodescartándose en domingo y disparando con
la fecha del BCE, y una pasada completa de análisis con código 0 y 107
recomendaciones guardadas.

Copias de seguridad: `intradia.db.bak-20260830-125315` y las unidades
originales en `/root/*.bak`.

**Trampa aprendida:** probar la pasada por evento con `--fecha 2026-09-10`
marcó los tres eventos de ese día como `SENT`, lo que habría silenciado la
pasada real del BCE. Se limpió la tabla. Cualquier prueba con fecha futura
tiene que borrar después sus filas de `event_pass`.

### Pendiente menor de esto

`verificar-systemd` lanza un traceback de `PermissionError` en vez de un error
limpio cuando no puede leer el fichero de entorno. Se resolvió el caso real
poniéndolo en `0644` (no tiene secretos), pero el mensaje sigue siendo feo.

## 13. Cosas menores pero reales

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
