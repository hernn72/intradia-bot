# T-018 — Caché local de barras de sesión cerrada ya validadas (C-09)

Estado: EN_REVISION (implementada el 2026-09-25)
Agente: Opus (ficha e implementación) → Codex (revisión de diseño y supervisión del código) → propietario (OD-02 bis)
Línea / fase: Línea C, C-09
Gate al que contribuye: ninguno directamente; **produce la cifra que decide si
además hace falta una segunda fuente de precios europea**

## Objetivo
Que una barra de sesión cerrada que el bot ya observó y validó **no desaparezca
del análisis porque el proveedor deje de devolverla**, y que quede registrado
cuándo la fuente viva no la estaba sirviendo.

## Por qué existe
D-40 cerró OD-02 con la lectura (c): 47 activos superan el umbral de 2 sesiones
perdidas por mes, frente al umbral de 10 activos. Pero al medir **el mecanismo**
apareció que el fallo dominante no es «el proveedor nunca entregó la barra»,
sino **«la entregó, el bot la vio, y después dejó de devolverla»**. Sobre el dato
crudo de la Pi (`evidence/2026-09-20-T-012-frescura-historico/`), siguiendo
`SAP.DE` pasada a pasada:

    2026-09-14 20:02  ultima barra = 2026-09-14
    2026-09-15 06:02  ultima barra = 2026-09-11   <- desaparecio
    2026-09-15 13:32  ultima barra = 2026-09-14   <- volvio

El patrón se repite todos los días laborables: por la mañana el activo está dos
sesiones atrás, al mediodía una, por la tarde al día. **Pagar una segunda fuente
para reconstruir algo que ya tuvimos sería innecesario** (D-41), así que la caché
va primero y la segunda fuente queda condicionada a lo que esta ficha mida.

Efecto secundario que por sí solo justifica la tarea: hoy **el histórico del bot
cambia retrospectivamente** según lo que el proveedor decida devolver esa mañana.
Eso contamina cualquier medición de investigación que se repita en otro momento.

## Dependencias previas
Ninguna ficha bloquea. D-40 y D-41 en `docs/decision-log.md`. **No** depende de
B-00: la caché no es una fuente externa nueva, es persistencia de lo que ya se
recibió. Si más adelante entra una segunda fuente, **esa sí** pasa por B-00.

## Archivos probables
No asumir que son exactos; verificar con búsqueda de símbolos antes de editar.
- `advisor/data/` — el proveedor (`MarketDataProvider`) y `advisor/data/freshness.py`.
- `advisor/data/sessions.py` — `session_date_of` y la última sesión cerrada exigible.
- `advisor/storage/db.py` y `advisor/storage/migrations.py` — tabla nueva y su migración.
- `advisor/main.py` — el punto donde la pasada obtiene las series.

## Invariantes que no pueden romperse
- **INV-16** (lo desconocido se declara desconocido): si una sesión exigible
  **nunca** se ha observado, sigue siendo `MISSING_RECENT_DATA`. La caché no la
  inventa ni la interpola.
- **INV-06** (una función, varios llamantes): producción e investigación leen las
  series por el mismo camino; no puede haber una ruta con caché y otra sin ella.
- **INV-13** (los timestamps crudos de la cosecha no se reserializan): la caché
  es una capa distinta de `data/vintages/` y no la toca.
- **INV-17** (todo cambio de esquema pasa por migración con backup previo).
- **INV-18** (lo que persiste lleva `run_id` y manifiesto).
- Nueva, a numerar como **INV-21**: *una barra servida desde la caché queda
  marcada como tal en la medición de esa pasada; nunca se presenta como si la
  fuente viva la hubiera devuelto.*

## Implementación requerida

Las cinco reglas son del propietario (D-41) y no se reinterpretan.

1. **Persistir la barra de sesión cerrada ya validada.** Una barra entra en la
   caché cuando su sesión está **cerrada y es exigible** según
   `advisor/data/sessions.py` y ha pasado la validación que ya aplica producción.
   Una vez dentro, **no desaparece porque el proveedor deje de devolverla**.

2. **La caché nunca crea una barra que el bot no haya observado.** No hay
   relleno, ni interpolación, ni arrastre del cierre anterior.

3. **Sesión nueva jamás recibida ⇒ sigue siendo `MISSING_RECENT_DATA`.** Si una
   sesión se vuelve exigible y nunca se ha observado, el veto actúa igual que
   hoy. **Ese es exactamente el caso en el que una segunda fuente aportaría
   algo**, y el que hay que contar (punto 6).

4. **Una barra revisada no se sobrescribe en silencio.** Si el proveedor
   devuelve después una versión distinta de una barra ya guardada, se registra
   como **revisión**, conservando: valor anterior, valor nuevo, instante de la
   revisión y proveedor. Hace falta una decisión explícita sobre cuál se usa
   —no la tome el implementador—: si la ficha llega aquí sin respuesta, se
   escribe como DECISIÓN PENDIENTE y se para.

5. **Trazabilidad obligatoria.** Cuando una pasada usa la barra local porque la
   API «retrocedió», la medición de frescura de esa pasada debe decirlo, con un
   campo propio. No basta con que el análisis salga bien: tiene que quedar
   escrito que la fuente viva no estaba sirviendo ese dato.

6. **La cifra que decide la segunda fuente.** Publicar, por pasada y acumulada,
   el recuento de:

       sesión exigible  +  nunca observada antes  +  el proveedor principal no la entrega

   Es el **valor marginal real** de una segunda fuente. Va en el informe y
   persistida, para poder acumularla varias semanas.

## Qué NO debe modificarse
El score, la geometría, los umbrales, `classify()`, el veto de D-21 y la regla
de barra abierta de D-37. Esta ficha cambia **de dónde sale una barra**, no qué
se hace con ella. Tampoco se toca `data/vintages/` ni el modo `--vintage` del
backtest: la cosecha congelada seguirá siendo la fuente reproducible.

## Tests unitarios
Con números cerrados escritos en el test.
- `test_barra_validada_sobrevive_a_que_el_proveedor_deje_de_servirla`: serie con
  sesiones 09-11 y 09-14; segunda llamada devuelve solo hasta 09-11; el análisis
  sigue viendo 09-14 y la fila queda marcada como servida por caché.
- `test_la_cache_no_inventa_una_sesion_nunca_observada`: sesión 09-15 exigible y
  jamás recibida ⇒ `MISSING_RECENT_DATA`, y la caché no la fabrica.
- `test_revision_de_barra_no_sobrescribe_en_silencio`: cierre 100,0 guardado y
  luego 100,5; quedan las dos, con instante y proveedor.
- `test_una_barra_servida_por_cache_se_declara_en_la_medicion` (INV-21).
- `test_contador_de_valor_marginal_solo_cuenta_lo_nunca_observado`: una sesión
  que sí se había visto antes **no** suma al contador del punto 6.

## Tests de integración
- Pasada completa con un proveedor de prueba que «retrocede» entre dos llamadas:
  las recomendaciones no cambian y la medición declara el uso de caché.
- Migración de esquema con backup previo y restauración probada (INV-17).

## Verificación contra datos reales
```bash
# en el portátil, sobre la copia de la Pi
.venv/bin/python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar
# y en la Pi, tras desplegar el tag: comparar una pasada de las 06 UTC con una de las 20 UTC
```
Comprobar a mano: elegir **un** activo europeo y una mañana concreta, ver que la
barra que la API no devuelve a las 06 UTC está en la caché con el instante en que
se observó la tarde anterior, y que la fila de frescura lo declara.

## Medición del impacto
- Nº de activos que pasan de vetados a evaluables en las pasadas de mañana, por
  motivo (`STALE_DATA` frente a `MISSING_RECENT_DATA`).
- Nº de señales que aparecen o desaparecen por ese cambio.
- El contador del punto 6 en la primera pasada, que es la línea base de la
  decisión sobre la segunda fuente.

## Criterio de aceptación
- Las cinco reglas implementadas y cada una con su test.
- El contador de valor marginal publicado y persistido.
- Migración con backup previo y restauración probada.
- `pytest`, `ruff`, `mypy` limpios; impacto medido y escrito.
- Ninguna barra servida desde caché sin declararlo.

## Criterio de rechazo
- Rellenar, interpolar o arrastrar una barra nunca observada.
- Sobrescribir una barra revisada sin registrar la anterior.
- Usar la caché en producción y no en investigación, o al revés (INV-06).
- Tomar por el propietario la decisión de qué versión vale tras una revisión.
- Cambiar el veto de D-21 o cualquier umbral.

## Evidencia que debe quedar registrada
`evidence/<fecha>-T-018-cache-de-barras/` con README.md, la migración y su
backup, el caso real del activo europeo comprobado a mano, el antes y el después
de una pasada de mañana, y el valor inicial del contador del punto 6.

## Commit esperado
Rama `feat/validated-bar-cache`. Mensaje:
`feat(datos): persistir barras de sesion cerrada ya validadas y declarar cuando la fuente viva no las sirve`

## Actualización documental requerida
`docs/roadmap.md`: fila C-09 a EN_REVISION y luego ACEPTADA.
`docs/metodo-trabajo.md`: añadir **INV-21** a la tabla de invariantes.
`docs/decision-log.md`: OD-02 bis queda abierta a la espera del contador; se
cierra cuando haya varias semanas de datos.

## Cómo quedó implementada (2026-09-25)

**La regla 4 la decidió el propietario, y con ella apareció un hecho que la
pregunta no contemplaba.** Todo está en **D-44**: manda la primera barra
validada, y —porque `get_history` usa yfinance con `auto_adjust=True`, así que
cada ex-dividendo reescribe la serie por un factor común— se distingue el
**REAJUSTE** de la serie, que la caché adopta reanclándose, de la **REVISION**
de una barra, donde sigue mandando la primera validada. Una sola base de ajuste
por serie, siempre.

**Piezas:**
- `advisor/data/bar_cache.py`: `CachedBarProvider` envuelve al proveedor y solo
  actúa en series diarias. `get_raw_history` pasa intacto: alimenta la cosecha
  congelada, que debe seguir siendo lo que el proveedor sirvió (INV-13).
- Esquema **v6**: `validated_bar` (UNIQUE por símbolo y sesión, `INSERT OR IGNORE`
  para que nadie sobrescriba la primera validada), `validated_bar_revision` y
  cuatro columnas en `data_freshness_measurement`
  (`bars_served_from_cache`, `bars_pinned_revisions`, `sessions_never_observed`,
  `bar_cache_status`).
- Todo se escribe en la transacción de `insert_analysis_result`, al final de la
  pasada, para que lo persistido lleve el `run_id` de un manifiesto que existe
  (INV-18). El reanclaje **borra antes de insertar**.
- Cableado en `cmd_analizar`, `cmd_pasada_evento` y el `backtest` **vivo** —este
  con la base en solo lectura—, porque no puede haber una ruta con caché y otra
  sin ella (INV-06). `--sin-guardar` no escribe nada.
- La cifra de la regla 6 se publica por pasada en el informe y **acumulada y
  deduplicada por par activo-sesión** en `frescura-historico` (D-40).

**Precedencia de plaza, que no es trivial.** Un activo del universo se fecha con
su plaza declarada, pero un índice o un benchmark se fecha con `SYMBOL_MARKETS`,
que es lo que usa producción para recortarlo: el universo declara `^STOXX50E` en
`ZRH`, sin cierre regular, y producción lo recorta con XETRA. La precedencia es
símbolo explícito → declaración del universo → sufijo → `None`, y con `None` la
caché no actúa y lo declara (INV-16).

**Quince defectos, en tres vueltas de revisión cruzada con Codex, todos medidos
antes de corregirlos** y cada uno con su test, con el valor de antes escrito
dentro. La lista completa está en
`evidence/2026-09-25-T-018-cache-de-barras/README.md`. Lo que hay que saber si
alguien vuelve a tocar esta capa son dos patrones:

- **Los defectos no estaban en la lógica de la caché, sino donde la caché toca
  insumos del análisis.** El índice de una barra reinyectada degradaba a `object`
  y `relative_strength` devolvía `None` en silencio; una barra con volumen
  desconocido hacía que `build_snapshot` tomara el volumen de la sesión anterior
  como si fuera el de esa barra. Al meter una capa en medio del camino de los
  datos hay que comprobar **qué lee aguas abajo**, no solo que la capa haga lo suyo.
- **Cada corrección defensiva tendía a comerse un caso que las reglas de D-41 sí
  quieren cubrir**, y de ahí que hubiera tres vueltas y no una: las correcciones
  de la vuelta 1 abrieron los hallazgos de la 2, y las de la 2 los de la 3. Dos
  ejemplos del mismo par: exigir **unanimidad** para detectar el reajuste dejaba al
  análisis en la base anterior a un split, y exigir **mayoría absoluta** también
  —la regla buena es un solo grupo dominante, sin empate—; y acotar la reposición
  a la primera barra viva evitaba alargar ventanas cortas pero dejaba de reponer la
  primera barra del rango cuando era justo la retirada. **Cada guarda del módulo
  lleva su contraprueba al lado en los tests**, y conviene que siga siendo así.

**Dos costes declarados, que no se esconden:**
- una barra retirada el mismo día de un reajuste **se pierde**, porque escalarla
  por el factor produciría un valor que el bot nunca observó (regla 2);
- el límite de reposición es **el periodo que pidió el llamante**, y en el borde
  de un periodo corto puede entrar **una** sesión que el proveedor no habría
  servido esa vez. Medido: 3 sesiones en 3 índices de contexto sobre 12 retiradas.
  Es una barra real de esa plaza y el efecto está acotado por el propio periodo.
  Entre equivocarse por una sesión de más y perder una barra ya validada, la regla
  1 marca la dirección.

## Handoff al siguiente agente
**Queda vivo para el propietario:** OD-02 bis, que **no se decide hoy**. La cifra
—`sesión exigible + nunca observada + no entregada`— ya se publica y se persiste,
pero una sola pasada no distingue un fallo puntual del proveedor de un hueco
estructural. Hay que dejar que la Pi acumule varias semanas y leerla con
`frescura-historico`.

**Lo que la primera pasada real midió** (2026-09-25, copia de la base del
portátil, 93 activos): 3.193 barras guardadas, 0 revisiones, y 33 sesiones
exigibles nunca observadas en 33 activos analizados —17 son huecos interiores que
la frescura ya declaraba y 16 son cola del día anterior en ETF alemanes—. Es la
línea base de OD-02 bis, no la respuesta.
