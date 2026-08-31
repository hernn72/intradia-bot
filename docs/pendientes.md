# Pendientes del asesor

Estado al **31 de agosto de 2026**.

En `main` y pusheadas a GitHub (`c415dbc`) están P0, P1, P2.0–P2.3 y P2.5,
además de las pasadas por evento, el despliegue versionado en `deploy/` y el
gate de `mypy`. La Pi corre lo mismo: se desplegó en `1f31d2d`, y `c415dbc`
solo toca documentación.

El **31 de agosto** entró una tanda grande, ya en `main` y **desplegada en la
Pi** (`39aab6c`): la frescura del dato y la detección de sesiones ausentes,
P2.4, P2.6, la corrección del mapa de bloques de P2.5, el error limpio de
`verificar-systemd` y los tests de dimensionamiento con capital sintético.
Verificado en la propia Pi: 366 tests pasan y 2 se saltan (los que necesitan la
cosecha, que allí no está), `verificar-systemd` dice «alineadas», una pasada
real termina con código 0 y los dos timers siguen vivos. Copia de seguridad en
`intradia.db.bak-20260831-081832`.

Con eso, **el laboratorio P2 está completo** (P2.0 a P2.6) y en producción el
informe ya declara la antigüedad del dato y las sesiones que le faltan.

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
- **Frescura del dato** (sin commitear): el informe declara siempre la
  antigüedad de la última barra de cada activo, y el subcomando
  `frescura-datos` reproduce la medición del retraso por plaza. Sección 10.
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

## Lo que falta, por orden

### A. Decisiones que son tuyas, y que bloquean lo demás

1. **Qué hacer con las sesiones ausentes.** Hoy el informe las declara y sigue
   puntuando, que respeta la regla de no degradar *en silencio*. Pero una sesión
   que falta no es un dato viejo: contamina EMA, RSI, ATR, MACD y los retornos, y
   deja la fortaleza relativa restando dos series de calendarios distintos. Las
   opciones son mantener la declaración, marcar la calidad como degradada de
   forma explícita, o un veto configurable. **Cambiar cuándo el bot recomienda no
   es una decisión del bot.** Contexto entero en la sección 10.
2. **Declarar el estimador del bloque antes de tocar P3.** Peso igual por bloque
   o tasa agrupada: la elección decide el signo del resultado y el protocolo
   nunca la fijó. Hay que escribirla **antes** de volver a mirar los números;
   elegirla después es exactamente lo que el documento prohíbe. Sin esto, P3 no
   puede empezar. Sección 11.
3. **Fundamentales: proveedor y coste.** Es la única brecha que cuesta dinero.
   Mientras no esté, la nota se normaliza sobre 80 y el ratio pesa 25 de 100 en
   vez de 20. Sección 3.
4. **Noticias: quién filtra y con qué criterio.** Los datos son gratis; el
   problema medido es la relevancia. Sección 4.
5. **Si se paga otra fuente para las plazas europeas.** Antes era un lujo. Con
   sesiones que sencillamente no existen en la serie, ya no está claro que lo
   sea. Sección 10.

### B. Medir antes de decidir (no cuesta dinero, solo días)

6. **Repetir la medición de sesiones ausentes varios días seguidos.** Lo del
   viernes 28 es **una** observación. Hasta tener varias no se puede afirmar que
   el proveedor se salte sesiones de forma sistemática en Europa. El comando ya
   existe: `frescura-datos`, y el informe lo declara en cada pasada.
7. **El desfase activo/benchmark en la fortaleza relativa.** Medido, sin decidir.
   Declararlo es barato; corregirlo exige alinear las series por sesión, y eso sí
   toca el cálculo.
8. **La barra en curso tratada como cierre.** Las pasadas de las 08:30 y las
   14:30 puntúan sobre la sesión del día sin cerrar. Ahora se declara, pero no
   está resuelto, y arreglarlo de verdad necesita horarios de cierre por plaza
   que no tenemos.

### C. Laboratorio

9. **P3** — sacar el RR del score y recalibrar umbrales por horizonte.
   Bloqueado por el punto 2. P2.4 ya dejó el material: la dimensión del ratio
   reparte 10 de sus 20 puntos a casi todo, así que no ordena, diluye.
10. **P4** geometría · **P5** reducción a regiones robustas · **P6** backtest de
    sistemas · **P7** walk-forward y holdout. P4 hereda de P2.6 una advertencia:
    la opción B mejora en promedio pero con heterogeneidad alta, así que lo
    primero es preguntarse en qué régimen mejora y en cuál no.
11. **Rehacer la calibración con los 107 activos.** Todo lo medido
    históricamente sale de 21.

### D. Trabajo manual, sin atajo

12. **89 ISIN de 107**, uno a uno contra Deutsche Börse y Euronext. `yfinance`
    devuelve ISIN falsos que superan el dígito de control.
13. **Disponibilidad real en Trade Republic** de los 107. El tratamiento ya está
    resuelto (señal y ejecutabilidad van separadas); falta el dato, y no hay API.
14. **Doble símbolo**: ningún activo declara `european_symbol`. Hay que verificar
    los tickers de Xetra uno a uno antes de elegir cotización por sesión.

### E. Menores

15. El **calendario macro de `events.yaml` caduca el 2027-12-16**. El bot avisa
    a 60 días, pero conviene refrescarlo antes.
16. **`^SOX`, `^RUT`, `^TNX`, `DX-Y.NYB`, `CL=F` y `GC=F` no alimentan el
    contexto de mercado**, que sigue puntuando solo con VIX, tendencia europea y
    sesión asiática.
17. **`economic_currency` se guarda y no se usa.** Descomponer el ATR en riesgo
    de activo y de divisa es un cambio de cálculo, y hay que medirlo.
18. **Los eventos no puntúan**, a propósito, hasta medir que mejoran las señales.

### La cosecha congelada, para no volver a buscarla

`data_vintage_id`:
`071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841`

126 símbolos a 5 años, 18 MB, los tres hashes verificados al releer. Mediana de
1255 barras, máximo 1825 (las tres criptos, que cotizan también en fin de
semana), mínimo 446 (`Q8Y0.DE`), con `ARM` en 742 y `DFEN.DE` en 863 porque son
jóvenes; los asiáticos se quedan en ~1220 porque `yfinance` no da cinco años de
esas plazas. `data/vintages/` está en `.gitignore`: **la cosecha vive solo en el
portátil**, y reproducirla en otra máquina exige volver a congelar y comprobar
que sale el mismo identificador.

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

## 2. ~~Pasadas por evento~~ — hechas y en producción

Resuelto el 2026-08-30 y desplegado. Temporizador fijo autodescartable a las
22:30, que es el único hueco real del horario: las 21:00 caen en el cierre
americano y por eso no pueden ver los resultados que se publican después. Se
descartó la reprogramación dinámica porque con systemd exigiría dar permisos
sobre systemd a un bot de bolsa. IDs deterministas por evento y pasada, y solo
una pasada efectivamente enviada deduplica: reservar y morir antes de enviar
dejaba el evento silenciado para siempre.

**Trampa aprendida:** probar con `--fecha` futura marca esos eventos como
enviados y silenciaría la pasada real. Cualquier prueba con fecha futura tiene
que borrar después sus filas de `event_pass`.

**Sigue vigente el aviso:** el calendario macro de `events.yaml` caduca el
**2027-12-16**.
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
`unknown` eso inutilizaría el sistema.

**Separación hecha el 2026-08-30** (`1f31d2d`): calidad de la señal y
ejecutabilidad en el broker ya son dos campos distintos del informe —`Señal:` y
`Ejecutabilidad en broker:` en la ficha del activo, `Señal:` y
`Disponibilidad:` en el bloque de acción—, de modo que puede decir «OPERAR,
disponibilidad pendiente» sin afirmar nunca «COMPRAR AHORA EN TRADE REPUBLIC»
antes de verificarlo. La liquidez recomendada se sigue calculando sobre las
mejores ideas **por señal**, y el informe lo declara: condicionarla a
disponibilidad verificada lo dejaba en cero ideas, precisamente porque los 107
están en `unknown`.

**Lo que sigue pendiente es el dato**, no su tratamiento: verificar la
disponibilidad real de los 107, que no tiene fuente automática.

## 10. Los datos europeos: no llegan tarde, les faltan sesiones

**La pregunta que quedaba abierta está resuelta.** La medición del domingo era
una sola muestra en fin de semana y no permitía distinguir un retraso real del
proveedor de un rezago que se pusiera al día el lunes. Ya está repetida en día
de mercado, y el retraso es real.

### Las tres mediciones

| Momento | Xetra y Euronext | EE. UU. |
|---|---|---|
| dom 30, por la mañana | mié 26 (−2 sesiones) | vie 28 |
| dom 30, 17:20 | jue 27 (−1 sesión) | vie 28 |
| lun 31, 06:51 UTC | jue 27 (−1 sesión) | vie 28 |

O sea: **no es una constante por plaza, es un rezago que se va rellenando**, y
entre la mañana y la tarde del domingo el proveedor completó una sesión. Lo que
no rellenó, ni el domingo ni antes de abrir el lunes, es el viernes 28 de las
plazas europeas.

Medición completa del lunes 2026-08-31 a las 06:51 UTC, con la última sesión
cerrada siendo el viernes 28:

| Última barra | Símbolos | Plazas |
|---|---|---|
| lun 31 (al día) | 25 | JPX (7), HKG (5), CRYPTO (3), KSC (3), CCY, CMX, NYB, NYM, OSA, SHH, TAI |
| vie 28 (al día) | 57 | NASDAQ (27), NYSE (19), MCE (3), ZRH (2), CBOE, CGI, PAR, SNP, WCB, XETRA |
| jue 27 (−1 sesión) | 44 | **XETRA (31)**, PAR (6), MIL (3), AMS (2), CPH, MCE |

### El hallazgo nuevo: el retraso es por símbolo, no por plaza

Xetra aparece en dos filas a la vez, y eso es lo importante. El único símbolo de
Xetra que sí tiene el viernes es **`^GDAXI`**, el índice. El único de París es
**`^FCHI`**, también índice. Y en Madrid, `IBE.MC`, `SAN.MC` y `BBVA.MC` están al
día mientras `ITX.MC` no.

El patrón es **índices al día, valores retrasados**. Y tiene una consecuencia
analítica que no es cosmética: la fortaleza relativa compara el activo contra su
benchmark, así que hoy compara **un valor sin el viernes contra un índice con el
viernes**. No es ruido aleatorio, es un desfase sistemático de una sesión en un
lado de la resta, justo en las 31 acciones alemanas que son el grueso de lo que
se opera en Trade Republic.

### Lo que se ha hecho

- `advisor/data/freshness.py`: núcleo puro que calcula la antigüedad en días
  naturales y en **sesiones cerradas perdidas**, que no es lo mismo que días
  laborables transcurridos. La sesión en curso no cuenta: el lunes por la mañana
  una acción de EE. UU. con la barra del viernes no ha perdido ningún dato. Las
  sesiones son aproximadas y el propio módulo lo dice, porque no hay calendario
  de festivos.
- El informe **declara la antigüedad siempre**, no solo cuando hay algo que
  comprar. Salió así de ejercitar el camino real: la primera versión ponía la
  línea dentro de la ficha de la oportunidad, y un informe sin oportunidades
  —que es lo que dio el domingo— no decía absolutamente nada sobre el retraso.
  Ahora hay un bloque de frescura en la situación global, y RADAR y DESCARTADOS
  marcan el activo con dato viejo.
- `frescura-datos`: subcomando que reproduce la medición entera en un comando,
  con la hora exacta de la medición y una tabla de dispersión por plaza que
  cuenta cuántos símbolos no coinciden con el escalón mayoritario de la suya.
  Esa tabla es la que delató que el rezago es por símbolo.

**Decisión aplicada, la que ya estaba tomada:** declarar, nunca degradar en
silencio. Ni la puntuación, ni el radar, ni las exclusiones, ni el
dimensionamiento miran la frescura.

### Lo que sigue abierto

- **El desfase activo/benchmark.** Ahora que está medido, hay que decidir qué
  hacer con una fortaleza relativa que resta series con un día de diferencia.
  Declararlo por activo es barato; corregirlo exige alinear las series por
  sesión, y eso sí toca el cálculo.
- **Si se busca otra fuente para las plazas europeas.** Es la opción cara y
  ahora hay con qué compararla: el subcomando mide el retraso de cualquier
  proveedor con el mismo criterio.
- ~~Repetir la medición dentro de la sesión europea.~~ **Hecho el 2026-08-31**,
  ver abajo.

### El giro: no es un retraso, es un HUECO

Siguiendo la medición dentro de la sesión apareció lo que de verdad pasa, y
obliga a corregir todo lo anterior de esta sección.

A las 07:11 UTC, con Xetra abierto desde las 07:00, `SAP.DE`, `SIE.DE`,
`ASML.AS` y `MC.PA` seguían en el jueves 27. A las 07:22 UTC saltaron a la barra
del **lunes 31**. Pero el viernes **no apareció por el camino**. Pidiendo la
serie diaria de un mes:

```
SAP.DE      ... 2026-08-26, 2026-08-27, 2026-08-31
SIE.DE      ... 2026-08-26, 2026-08-27, 2026-08-31
ASML.AS     ... 2026-08-26, 2026-08-27, 2026-08-31
MC.PA       ... 2026-08-26, 2026-08-27, 2026-08-31
ITX.MC      ... 2026-08-26, 2026-08-27, 2026-08-31
NOVO-B.CO   ... 2026-08-26, 2026-08-27, 2026-08-31

^GDAXI      ... 2026-08-26, 2026-08-27, 2026-08-28, 2026-08-31
^STOXX50E   ... 2026-08-26, 2026-08-27, 2026-08-28, 2026-08-31
IBE.MC      ... 2026-08-26, 2026-08-27, 2026-08-28, 2026-08-31
AAPL        ... 2026-08-26, 2026-08-27, 2026-08-28
```

El viernes 28 fue sesión normal en las cinco plazas. **Los índices la tienen y
los valores no.** Para esos valores la sesión no llega tarde: **no existe**, y la
serie sigue con la barra del lunes, que además es la sesión **en curso**, no un
cierre.

Eso cambia el diagnóstico y empeora las consecuencias:

1. **Los indicadores se calculan sobre una serie a la que le falta una sesión
   real.** EMA, RSI, ATR, MACD y los retornos a 20, 60 y 120 velas se computan
   saltándose el viernes, sin que nada lo diga. No es un dato viejo que se pueda
   declarar y seguir: es una observación ausente en medio del cálculo.
2. **La fortaleza relativa resta dos series de calendarios distintos**, porque el
   benchmark sí tiene el viernes. Ya no es una hipótesis: está medido.
3. **El asesor trata como cierre una barra sin cerrar.** Las pasadas de las 08:30
   y las 14:30 puntúan sobre la sesión en curso.

### El instrumento medía el fallo equivocado

La primera versión de la frescura miraba la antigüedad de la **última** barra.
Con el hueco, la última barra es la de hoy, así que el informe desplegado en la
Pi llegó a imprimir «0 sesiones cerradas perdidas: 30 activos» **justo cuando a
26 de esos 30 les faltaba el viernes**. Estaba afirmando que el dato era perfecto
en el peor momento posible.

Corregido: además de la antigüedad, ahora se detectan las **sesiones ausentes**
comparando la serie del activo contra el calendario de su **benchmark**, que es
la referencia que el propio activo ya usa para la fortaleza relativa y que por
tanto no cuesta descargas nuevas. Los activos sin comparable —cripto y
`EMERGING_MARKETS`— se declaran como «sin calendario de referencia» en vez de
inventarse uno. Y si la última barra es de hoy se declara **barra potencialmente
parcial**, sin fingir más precisión de la que hay: no tenemos horarios de cierre
por plaza.

Verificado contra la red el 2026-08-31: el informe señala los **26 activos**
europeos a los que les falta el 28, nombrando la sesión y el benchmark.

### Lo que esto deja abierto, y es más gordo que antes

- **Declarar ya no es obviamente suficiente.** La regla del proyecto es no
  degradar **en silencio**, y declarar en voz alta y seguir puntuando la respeta.
  Pero un hueco no es un dato viejo: contamina el cálculo, no solo su
  antigüedad. Queda como decisión del dueño del proyecto, no del bot.
- **¿Es de todos los lunes o de este?** Una sola observación. Hay que repetirla
  varios días antes de concluir si el proveedor se salta sesiones de forma
  sistemática en las plazas europeas.
- Con esto sobre la mesa, **buscar otra fuente para las plazas europeas** deja de
  ser una opción cara y se acerca a ser necesaria.

**No afecta a la cosecha ni a P2.3:** al event study le sobran una o dos
sesiones de cola sobre medianas de 1255 barras.

## 11. P2.3 y P2.5: la frase «el score ordena» se queda sin instrumento

Esta sección decía que el score ordena. **Hay que retirarlo**, y el motivo no es
que se haya medido lo contrario: es que el instrumento en el que se apoyaba no
existía.

### Lo que P2.3 midió, que sigue siendo cierto

Pasada completa sobre la cosecha `071ddb2b`, horizonte swing, coste 0,20 %:
121.786 señales sobre 107 activos. Proporción agrupada de tocar objetivo antes
que stop, por banda:

| Banda | n | P(objetivo antes de stop) | net_R medio |
|---|---|---|---|
| <50 | 51.268 | 0,402 | 0,13 |
| 50-60 | 44.848 | 0,410 | 0,09 |
| 60-70 | 23.027 | 0,443 | 0,12 |
| 70-80 | 2.565 | 0,477 | 0,21 |
| 80+ | 78 | 0,500 | 0,20 |

Eso es un **hecho descriptivo de esta cosecha** y no lo discute nadie. La
progresión de la probabilidad es monótona. Conviene fijarse en que la columna de
`net_R`, que el protocolo declara la métrica **primaria**, nunca lo fue.

### El instrumento que no existía

La versión anterior de esta sección publicaba además un intervalo de confianza
del 95 % por banda, de anchura ±0,004, y concluía que las bandas se separaban.
Ese intervalo **no lo produce ningún código del repositorio**, no tiene test, y
trata 121.786 señales solapadas de 107 activos correlacionados como si fueran
ensayos independientes. Es exactamente la unidad de independencia que el
protocolo declara incorrecta en P2.6. Su anchura no mide nada y no debe volver a
citarse.

Con eso, la frase «el score ordena» se queda sin respaldo. **No es lo mismo que
haber medido que no ordena**, y confundir las dos cosas sería el mismo error de
sobrelectura en dirección contraria.

### Al ejecutar el gate aparecieron dos defectos en su propio mapa de bloques

Marco, porque importa: esto **no es cambiar las reglas después de ver los
resultados**, que es lo que el protocolo prohíbe. Es lo contrario. El código se
había desviado de lo que el documento escribió antes de medir, y se le ha
devuelto a la regla escrita. El antes y el después se publican los dos.

- **Las señales europeas caían en el bloque del día anterior.** Los bloques se
  construían con `signal_timestamp.date()` sobre un `datetime` en UTC, pero las
  barras diarias vienen selladas a la medianoche local de la plaza expresada en
  UTC. Verificado en la cosecha: la primera barra de `SAP.DE` es
  `2021-08-29T22:00:00Z`, que es la sesión del **lunes 30** en Berlín, mientras
  la de `AAPL` es `2021-08-30T04:00:00Z`. Resultado: fechas de sábado y domingo
  en un calendario de renta variable, y señales europeas y estadounidenses de la
  misma sesión en bloques distintos. Rompe justo lo que P2.6 exige, que el
  bloque contenga **todos los activos** de esa ventana.
- **La longitud del bloque no estaba en sesiones.** Se contaba sobre el conjunto
  de fechas distintas presentes, inflado por la cripto, que cotiza en fin de
  semana. Un bloque nominal de 40 eran unas 27 a 34 sesiones de bolsa: **más
  corto que el periodo de tenencia** `MAX_HOLD_BARS` = 40, cuando el protocolo
  exige que lo supere y escribe 60 sesiones para swing y 300 para medio.
- **El gate resolvía una ambigüedad que tiene prohibido resolver:** contaba
  `AMBIGUOUS` como fallo. Ahora publica la cota inferior y deja la ambigüedad en
  el denominador, coherente con el `lower`/`upper` del event study.

Corregido: la fecha de sesión se deriva con `zoneinfo` y una tabla explícita de
plazas que **falla ruidosamente** si aparece una sin declarar; la espina de
sesiones se construye con los activos no cripto y la cripto se engancha a la
última sesión bursátil sin crear sesiones nuevas; y la longitud sale de la tabla
del protocolo, validada contra `MAX_HOLD_BARS`.

Efecto medido de la corrección: **1.702** señales cambian de bloque solo por la
fecha de sesión, **236** fechas de fin de semana desaparecen del calendario de
renta variable, y **116.866 de 121.786** cambian de bloque al sumar la longitud
correcta.

### El veredicto de P2.5 con el mapa arreglado

| Banda | n | bloques | Intervalo por bloque | Veredicto |
|---|---|---|---|---|
| GLOBAL | 121.786 | 21 | [0,345, 0,444] | LIMITADA |
| <50 | 51.268 | 21 | [0,362, 0,456] | LIMITADA |
| 50-60 | 44.848 | 21 | [0,312, 0,427] | LIMITADA |
| 60-70 | 23.027 | 20 | [0,347, 0,467] | LIMITADA |
| 70-80 | 2.565 | 20 | [0,305, 0,473] | **no concluyente** (bloque mínimo 2) |
| 80+ | 78 | 16 | [0,409, 0,620] | **INSUFICIENTE** |

Bloque de 60 sesiones, 2.000 remuestreos. Antes de corregir el mapa salían 43
bloques y casi todo SUFICIENTE con resolución HIGH: **aquella suficiencia era un
artefacto de bloques demasiado cortos y mal fechados**. Con la unidad que el
protocolo declara, la resolución del diseño es MEDIUM y **los intervalos de las
tres bandas bajas se solapan casi por completo**.

### Qué se puede afirmar y qué no

Dos lecturas independientes del resultado, hechas por separado y sin verse,
llegaron a la misma conclusión: **indeterminado**.

- Se puede afirmar que la banda **80+ no calibra nada**: 78 señales, el 0,06 %,
  presentes en 16 de 21 bloques, con bloques de 4,9 observaciones de media.
- Se puede afirmar que la banda **70-80 tampoco es concluyente**, y eso importa
  más de lo que parece: `min_score_operar` vale **70** en `config.yaml`, o sea
  que el umbral de producción cae justo en el borde de la primera banda sin
  capacidad.
- **No** se puede afirmar que el score ordene, porque el instrumento que lo
  decía no existía.
- **No** se puede afirmar que no ordene: con la unidad correcta el diseño
  simplemente no tiene resolución para el tamaño de efecto en juego (los saltos
  entre bandas valen 0,008 a 0,075 y el suelo de resolución ronda 0,10).
- **No** se puede afirmar que el gate haya refutado P2.3. El gate no es un test
  de ordenación; su única comparación por defecto es 50-60 contra 80+.

Una de las dos lecturas calculó además, con scripts propios fuera del
repositorio, que la ponderación decide el signo: con la tasa agrupada más
bootstrap de bloques la mitad alta sí separa, y con peso igual por bloque no
separa ninguna. **Eso no está en el repositorio, no tiene test y no se ha
verificado**, así que queda anotado como hipótesis para P2.6, no como resultado.
Lo que sí deja claro es que **la ponderación del bloque nunca se declaró en el
protocolo**, y elegirla ahora, a la vista de los resultados, sería justo lo que
el documento prohíbe.

### Consecuencia para P3

P3 estaba definido como «sacar el RR del score, comprobar ordenación y
recalibrar umbrales por horizonte». Tal cual, **no puede empezar**:

1. No puede heredar «el score ordena» como premisa, porque entonces
   «comprobar» se convierte en «confirmar».
2. Antes de volver a mirar hay que **declarar el estimador**: peso igual por
   bloque o tasa agrupada. Fijarlo después de ver los resultados invalida la
   medición.
3. La recalibración de umbrales está bloqueada **por encima de 70**, no solo en
   80+. Lo único con capacidad es la frontera baja, y ahí no hay separación.


### La ambigüedad intrabarra resultó ser irrelevante, y está medido

27 velas ambiguas de 121.786, el 0,02 %. No es un fallo de detección: con
stop a 2·ATR y objetivo 2 a 3·ATR, una vela necesita abarcar **5·ATR** para
tocar ambos niveles.

El hallazgo 6 del protocolo suponía que la ambigüedad penalizaría más a la
banda 80+ que a la 50-60 y contaminaría la monotonicidad. **A esta geometría
no ocurre.** La advertencia sigue siendo válida como principio: si P4 acerca
el objetivo, la fracción ambigua subirá y habrá que volver a mirarla. Por eso
el estado se conserva aunque hoy no mueva nada.

### ~~Riesgo abierto: los timestamps son cadenas~~ — cerrado el 2026-08-30

`read_raw_csv` conserva el índice como texto a propósito, para que el hash sea
estable. El defecto era que `SignalObservation.signal_timestamp` y
`ManagedEvent.exit_timestamp` estaban anotados como `pd.Timestamp` y contenían
`str`: no rompía nada entonces, pero cualquier aritmética de fechas en P2.5 o
P4 habría fallado o, peor, ordenado lexicográficamente sin avisar.

Resuelto en `1f31d2d` separando los dos papeles en `advisor/research/timestamps.py`:
`*_timestamp_raw` guarda el texto congelado, que es formato de archivo y entra
en los hashes, y `*_timestamp` guarda el `datetime` timezone-aware para
cálculo. El texto **nunca se reserializa**: `+00:00` y `Z` significan el mismo
instante pero son bytes distintos, y sustituir uno por otro rompería los 126
hashes de la cosecha. Lo cubre, en `tests/test_timestamps.py`, el test
`test_cosecha_real_mantiene_hashes_y_bytes_tras_parsear_y_serializar_salidas`,
que compara byte a byte contra la cosecha real y se salta si no está presente.

## 12. Despliegues en la Pi

**El 2026-08-31** la Pi pasó a `39aab6c` con la tanda de frescura, sesiones
ausentes, P2.4, P2.6 y el mapa de bloques. Verificado allí: 366 pasan y 2 se
saltan, `verificar-systemd` alineado, pasada real con código 0, timers vivos.
Copia en `intradia.db.bak-20260831-081832`.

Antes, el **2026-08-30**, la Pi pasó de `e952f71` a `1f31d2d`, ocho commits. Hasta ese día producción
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

### ~~Pendiente menor de esto~~ — arreglado el 2026-08-31 (sin commitear)

`verificar-systemd` lanzaba un traceback de `PermissionError` cuando no podía
leer el fichero de entorno. Ahora `load_env_file` convierte cualquier `OSError`
de lectura en un `ValueError` con la ruta, la causa y qué hacer, que es el tipo
que `main()` ya captura para devolver código 1 con un mensaje limpio. Cubierto
con un fichero en `chmod 000` —que se salta solo si los tests corren como root,
donde los permisos no aplican— y con el fichero inexistente.

## 13. Cosas menores pero reales

- ~~**`mypy` no se puede ejecutar**~~ — **gate levantado el 2026-08-30**
  (`1f31d2d`). `pyproject.toml` fija ahora `python_version = "3.12"`, alineado
  con el 3.13 de la Pi, en vez del 3.9 que el mypy instalado rechazaba. Llevaba
  caído desde el principio, y es el gate que habría cazado el defecto de tipos
  de los timestamps de la cosecha.
- **`capital:` sigue vacío en `config.yaml`**, a propósito: sin cifra el
  informe muestra solo porcentajes, que es el comportamiento deseado hasta que
  se configure expresamente. ~~Falta añadir tests del sizing con capital
  sintético.~~ **Hechos el 2026-08-31** (sin commitear): capital 10.000, 50.000
  y 100.000, con un activo en euros, uno en yenes con tipo de cambio —donde el
  test comprueba las 566 acciones contra un cálculo hecho a mano, para que el
  defecto histórico de las 3 acciones de Toyota no pueda volver sin ponerse
  rojo—, uno en divisa sin tipo de cambio, donde no se inventa un número de
  acciones, y el tope `max_position_pct`.
- **La tabla `MARKET_TIMEZONES` del gate solo cubre las plazas de los activos
  analizables** (comprobado: hoy no falta ninguna). Si se añade un analizable en
  una plaza nueva —`ZRH` ya está en el universo como contexto—, el gate falla
  ruidosamente nombrándola. Es deliberado: el recurso silencioso a UTC es
  justamente el defecto que se acaba de corregir.
- **Diagnóstico equivocado, anotado para no repetirlo:** se atribuyó la lentitud
  del gate a que `block_for` escaneaba la espina en lineal. Se corrigió —había
  además un diccionario que se construía y se tiraba— pero medido, el comando
  solo mejoró 0,5 s de 64. El tiempo se lo lleva el event study, no el mapa de
  bloques.
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

## 14. P2.4 — la ablación del score, hecha el 2026-08-31

`advisor/research/ablation.py` y el subcomando `ablacion-score`. Núcleo puro
sobre un `EventStudyResult` ya calculado: no vuelve a recorrer la cosecha, no
llama a `compute_score`, y sobre todo **no pasa por `classify()`**, que es donde
vive el veto `min_rr_ratio: 1.5`. Esa dependencia de orden la exige el
protocolo: medir la capacidad de ordenación del RR sobre una muestra que el
propio RR ya depuró no mide nada. Las 121.786 señales entran enteras, cero
descartes.

La nota sin RR se reconstruye de las dimensiones ya guardadas en
`SignalObservation`, con denominador `evaluable_max` menos el peso de la
dimensión, o sea 80 − 20 = **60**.

### El hallazgo: el ratio beneficio/riesgo es prácticamente constante

| Banda | mediana puntos RR | p10 | p90 | mediana RR bruto | mediana RR neto |
|---|---|---|---|---|---|
| <50 | 10,000 | 10,000 | 15,000 | 1,500 | 1,472 |
| 50-60 | 10,000 | 10,000 | 10,000 | 1,500 | 1,461 |
| 60-70 | 10,000 | 10,000 | 10,000 | 1,500 | 1,455 |
| 70-80 | 10,000 | 10,000 | 10,000 | 1,500 | 1,458 |
| 80+ | 10,000 | 10,000 | 10,000 | 1,500 | 1,462 |

La dimensión que pesa **20 puntos de 100 reparte 10 a casi todo el mundo**, y el
ratio bruto vale 1,5 en la mediana de las cinco bandas. Es la confirmación
medida, sobre 121.786 señales, de lo que la sección 1 decía por construcción:
con `target2_structural: false` el ratio vale 1,5 salvo que un soporte cercano
acerque el stop.

Una dimensión casi constante no ordena nada; lo que hace es **diluir**. Y se
puede escribir exacto: si la dimensión da 10 de 20 puntos, la diferencia entre
la nota con RR y la nota sin RR vale `−0,4167·puntos + 16,667`, que se anula
justo en la nota 50. Por eso la columna de contribución del informe sale
positiva en la banda baja (+2,42) y cada vez más negativa al subir (−1,58,
−4,17, −7,30, −10,33): **no es información sobre el activo, es aritmética de
normalización**. El RR está comprimiendo todas las notas hacia el centro.

### Qué pasa al quitarlo

| Banda | n con RR | n sin RR |
|---|---|---|
| <50 | 51.268 | 55.520 |
| 50-60 | 44.848 | 30.260 |
| 60-70 | 23.027 | 27.190 |
| 70-80 | 2.565 | **7.608** |
| 80+ | 78 | **1.208** |

La banda 80+ pasa de 78 señales a 1.208, quince veces más, y la 70-80 casi se
triplica. Migran 6.192 señales de 60-70 a 70-80 y 1.130 de 70-80 a 80+. Y la
banda 70-80 sin RR **pasa a ser medible**: intervalo [0,367, 0,483] con
`net_R` medio **0,150**, el más alto de la tabla.

Aviso que hay que leer entero: la tabla sin RR usa **los mismos cortes** de
banda sobre una nota normalizada sobre 60 puntos, así que no son bandas
comparables una a una. Recalibrar los umbrales es P3 y aquí no se ha hecho.
Todas las bandas siguen en LIMITADA con el mapa de bloques corregido, y 50-60
sin RR sale no concluyente.

**P2.4 mide y no decide.** Lo que entrega es el material que P3 necesitaba: hay
razón medida para sacar el RR del score, y hay que recalibrar los umbrales
después, no heredarlos.

## 15. P2.6 — infraestructura de incertidumbre, hecha el 2026-08-31

`advisor/research/bootstrap.py` y `advisor/research/uncertainty.py`, más el
subcomando `comparacion-pareada`. La unidad de remuestreo es el **bloque
temporal completo con todos los activos dentro**, reutilizando la espina de
sesiones corregida de P2.5 (no hay un segundo mapa de bloques, que era la
tentación evidente y habría hecho que los dos módulos dijeran cosas distintas de
los mismos datos). El pareado es por `signal_id`. Los cuantiles están
implementados a mano para que el número no dependa de la versión de una
librería, y la semilla es fija y está testeada.

El gate P2.5 ahora delega su intervalo en este bootstrap en vez de usar la
aproximación normal que él mismo declaraba provisional. Eso movió los intervalos
publicados en el tercer decimal —el global de [0,346, 0,449] a [0,345, 0,444]—
**sin cambiar ningún veredicto**.

### La demostración: la «opción B» del ratio, por fin medida

Comparación pareada de la geometría actual (objetivo 2 a 3,0·ATR) contra la
opción B (3,5·ATR), sobre las mismas señales, sin tocar `config.yaml`:

| Bloque | n bloques | ΔR medio | IC por bloque | Dispersión | Esperada por ruido | Heterogeneidad |
|---|---|---|---|---|---|---|
| 40 | 31 | +0,022 | [+0,005, +0,038] | 0,048 | [0,008, 0,013] | alta |
| 60 | 21 | +0,022 | [+0,006, +0,037] | 0,038 | [0,007, 0,013] | alta |
| 80 | 16 | +0,021 | [+0,003, +0,040] | 0,040 | [0,005, 0,011] | alta |
| 120 | 11 | +0,020 | [+0,005, +0,035] | 0,027 | [0,005, 0,013] | alta |

**Veredicto del comando: NO CONCLUYENTE**, porque alguna longitud baja de 12
bloques. Y aunque el intervalo excluya el cero en las cuatro longitudes, la
heterogeneidad sale **alta** en todas: la dispersión observada entre bloques es
tres o cuatro veces la que cabría esperar bajo un efecto verdadero constante. Es
decir, el +0,022 R **no es un efecto estable, es un promedio de regímenes que se
comportan distinto**. Justo el caso que el protocolo describe cuando dice que se
prefiere el intervalo y la heterogeneidad al p-valor.

**No se adopta nada.** `config.yaml` no se toca, la geometría no se cambia y la
opción B no queda elegida. Elegir geometría es P4, y con esta heterogeneidad lo
primero que P4 tendrá que preguntarse es en qué régimen mejora y en cuál no.

