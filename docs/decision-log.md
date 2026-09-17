# Registro de decisiones

Formato: `D-nn` decisiones tomadas (por quién, fecha, alternativas, qué evita,
reversibilidad). `OD-nn` decisiones que **solo el propietario** puede tomar.
`OA-nn` acciones manuales que solo el propietario puede ejecutar (no son
decisiones, son trabajo sin atajo).

Una decisión se añade **antes** de implementarla o de medir. Nunca se borra:
si se revierte, se añade otra que la cita.

---

## Decisiones tomadas

### D-01 — 2026-08-29 — Cosecha en bruto con `auto_adjust=False` y tres vistas
Congelar OHLCV bruto + dividendos + splits; derivar `execution_prices`,
`signal_prices` y `gap_for_catalyst`. Evita comparar reconstrucciones
distintas del mismo histórico. Detalle: `docs/protocolo-investigacion.md` P2.0.

### D-02 — 2026-08-27 / 2026-08-29 — Ratio beneficio/riesgo: E aplicada, D descartada, B pendiente
E (el soporte nunca aleja el stop) aplicada con test. D (objetivo 2
estructural) medida y descartada: reduce operaciones un 85 % y su ratio no
ordena. B (objetivo 2 a 3,5·ATR) queda para P4. Detalle:
`docs/ratio-beneficio-riesgo.md`.

### D-03 — 2026-09-02 — Estimador primario pre-registrado
Media por bloque de la expectancy neta en R. Tasa agrupada y `P(objetivo
antes de stop)` son secundarias y se publican siempre junto a la primaria.
INV-14.

### D-04 — 2026-08-30 — `trade_republic: unknown` no degrada la señal
Con 107/107 en `unknown`, degradar inutilizaría el sistema. Se separa señal
de ejecutabilidad en broker. INV-04.

### D-05 — 2026-09-02 — `INCOMPLETO` veta la apertura sin tocar el score
Ventana de veto 20 sesiones (meseta medida: 5, 10 y 20 dan el mismo
resultado). `DEGRADADO` se declara y no veta. INV-03.

### D-06 — 2026-09-14 — El RR mínimo manda en la entrada máxima, y eso cambia la política de entrada
**Hecho:** PR 1 (`e929da4`) fija `entry_max = min(price + entry_max_atr·ATR,
entry_max_rr)` con `entry_max_rr = (target2 + min_rr·stop) / (1 + min_rr)`.
Con la geometría por defecto (stop 2·ATR, objetivo 2 a 3·ATR, `min_rr` 1,5)
`entry_max_rr = price` **exactamente**, así que `entry_max_atr: 0.75` deja de
intervenir salvo cuando un soporte acerca el stop. Verificado en la salida
real del 2026-09-14 (`EXH1.DE`: precio 56,11, entrada máxima 56,11).

**Consecuencia que el protocolo ya había previsto (hallazgo 4) y había
aplazado a P4:** en producción y en el backtest (`POLICY_OPERAR` y
`POLICY_TODAS`, que entran a la apertura siguiente) solo se admiten entradas a
un precio ≤ cierre de señal. Toda apertura al alza es `ABOVE_MAX_ENTRY`. Medido
sobre la cosecha: `AAPL` OPERAR 7 → 4, `MSFT` 5 → 3, `SAP.DE` 6 → 4.

**Decisión:** se mantiene, porque la invariante «nunca recomendar una entrada
que viole el RR mínimo» es no negociable y una entrada máxima que no la cumpla
es un número falso. Lo que cambia es dónde se resuelve la tensión: **P4 debe
tratar la holgura de entrada como una dimensión de la geometría** (por
ejemplo, objetivo 2 a 3,5·ATR da `entry_max_rr = price + 0,2·ATR`), y la fase
14 debe medir cuántas señales se pierden por `ABOVE_MAX_ENTRY` a la apertura.
El event study (P2.3) no se ve afectado: entra al cierre de señal.

Alternativas descartadas: bajar `min_rr` (cambia la política sin medir);
dejar `entry_max` técnico y mostrar un RR que no se cumple (número falso).
Reversible: sí, vía P4.

### D-07 — 2026-09-14 — Calendarios de plaza con la librería `exchange_calendars`
Las sesiones esperadas salen de un calendario de plaza real (festivos y
medias sesiones), no de una tabla manual ni del benchmark. Se añade la
dependencia `exchange_calendars` (pura Python, sin red, mantenida; códigos
MIC: XETR, XPAR, XAMS, XMAD, XMIL, XCSE, XNYS, XNAS, XTKS, XHKG, XKRX). Para
cripto se define un calendario propio 24/7 en el repositorio. Motivo: mantener
festivos de 12 plazas a mano es exactamente la fuente de falsos huecos que se
quiere eliminar. Riesgo: instalación en la Pi (Python 3.13, ARM); T-002 lo
verifica y, si falla, es BLOCKER y se reabre esta decisión. Reversible: sí.

### D-08 — 2026-09-14 — Universo point-in-time: acotar el sesgo, no fingir que no existe
Se introduce `universe_vintage_id` (hash canónico de la lista de analizables
con sus `added_at`) y la etiqueta obligatoria de sesgo en P6/P7 (ver
`docs/roadmap.md`, sección «Universo»). No se construye un universo histórico
completo: no hay fuente gratuita de constituyentes históricos ni de
exclusiones, y fabricarlo a mano introduciría otro sesgo. P10 es la
validación no condicionada. Revisión: si en el futuro aparece una fuente de
constituyentes históricos, se abre A-08 (universo histórico) y P7 se repite.

### D-09 — 2026-09-14 — Migraciones SQLite con `PRAGMA user_version`
Lista ordenada de migraciones en `advisor/storage/migrations.py`; backup
`intradia.db.bak-<fecha>-pre-v<n>` antes de aplicar; comando `verificar-backup`
que abre la copia en solo lectura, pasa `PRAGMA integrity_check` y compara sus
conteos con los registrados en `backup_log` en el momento del backup (no
restaura a un fichero temporal: T-002 lo implementó así y es equivalente para
lo que se quiere probar). Ninguna columna nueva sin migración (INV-17). Se
elige `user_version` frente a una tabla de versiones por simplicidad y porque
SQLite lo soporta de forma atómica. **Precisión 2026-09-14 (revisión de
T-002):** cada migración y su `user_version` van en una transacción explícita
(`BEGIN IMMEDIATE` … `COMMIT`), nunca con `executescript`; y los comandos de
consulta (`verificar-backup`, `manifiesto`) abren la base en `mode=ro` y no
migran ni crean nada.

### D-10 — 2026-09-14 — Manifiesto de ejecución obligatorio
Tabla `analysis_run` con `run_id` (UUID4), `git_sha`, `git_dirty`,
`config_hash`, `universe_vintage_id`, `data_vintage_id` (null en vivo),
`score_model_version`, `context_model_version`, `schema_version`,
`analysis_timestamp`, `environment` (`laptop`/`pi`/`ci`), `python_version`,
`provider_versions`, `clock_drift_seconds`. Toda fila de `recommendation`,
`data_freshness_measurement` y futuras tablas de contexto lleva `run_id`.
INV-18. Reconstrucción: `git checkout <sha>` + config con ese hash + universo
con ese vintage reproduce la decisión salvo por los datos del proveedor, cuya
identidad queda en la frescura persistida.

### D-11 — 2026-09-14 — CI, releases y despliegue por tag
GitHub Actions ejecuta `pytest -q`, `ruff check .`, `mypy advisor` en cada
push y PR. `main` protegida (OA-02). Release = tag `vX.Y.Z` con changelog. La
Pi despliega solo tags y `verificar-release` compara su SHA con el tag.
Rollback = checkout del tag anterior + `verificar-systemd`.

### D-12 — 2026-09-14 — Versionado de toda salida LLM persistida
`provider`, `model`, `model_version` (si la API lo devuelve), `prompt_version`
(SHA-256 del fichero de prompt), `input_hash` (SHA-256 del mensaje de usuario),
`input_source_ids`, `analysis_timestamp`, `run_id`, salida estructurada
validada. La narrativa se guarda en su tabla, nunca en columnas numéricas
(INV-10).

### D-13 — 2026-09-14 — Reloj
UTC en todo cálculo y persistencia; zona de la plaza solo para fechar
sesiones; zona local solo para presentar y programar timers. Cada pasada mide
la deriva del reloj y la guarda en el manifiesto; deriva > 60 s marca la
pasada como `CLOCK_SUSPECT`. **Precisión 2026-09-14 (revisión de T-002):** la
medición usa, en orden, `timedatectl timesync-status` (línea `Offset`, que en
la Pi da p. ej. `-572us`; `timedatectl show -p TimeUSec` no sirve porque
devuelve el reloj local en formato humano), `chronyc tracking` y una sonda
SNTP **por UDP** con timeout de 2 s contra una sola dirección. Hoy la deriva
sospechosa solo se registra con `logger.error`; el aviso por Telegram queda
en C-04.

### D-14 — 2026-09-14 — La evidencia vive en `evidence/`
Convención de `docs/metodo-trabajo.md` sección 7. Los manifiestos de cosecha
se commitean; los CSV no.

### D-15 — 2026-09-14 — Commits por entrega coherente
Sustituye «un commit por fase» de `docs/plan-ejecucion.md`. Detalle en
`docs/metodo-trabajo.md` sección 4.

### D-16 — 2026-09-14 — `docs/pendientes.md` y `docs/cobertura-especificacion.md` pasan a históricos
Conservan mediciones y razonamientos que no se repiten en otro sitio, pero no
se actualizan ni se usan como fuente de estado. El estado vive en
`docs/roadmap.md`.

### D-17 — 2026-09-14 — El RR sigue en el score hasta que P2.4 rehecho lo decida
PR 1 le quitó al ratio el veto dentro de `classify()`; sigue pesando 20/100
en `compute_score`. Sacarlo ahora sería recalibrar sobre arena (línea 0
abierta). Se decide en GATE P2 con la ablación rehecha.

### D-18 — 2026-09-14 — P2.3 y P2.4 se rehacen una sola vez, después de GATE L0
Dos motivos independientes obligan a rehacerlos (fortaleza relativa alineada
y línea 0). Hacerlo dos veces alimentaría P3 con números intermedios.

### D-19 — 2026-09-14 — Orden de la línea C respecto a la línea 0
CI (C-00), migraciones (C-01) y manifiesto (C-02) van **antes** de PR 3,
porque PR 3 y PR 4 añaden columnas y estados que deben nacer versionados.
Coste: dos tareas de Codex de un día; beneficio: no migrar dos veces.

### D-20 — 2026-09-14 — Identidad de instrumentos: modelo mínimo en `universe.yaml`
`issuer_id` (slug estable, p. ej. `apple`, `ishares`), `instrument_id`
(= ISIN cuando se verifique; hasta entonces `symbol@market`), `listing` = el
par `symbol`/`market` actual, `added_at`, `valid_to` (null), `delisted_at`
(null), `ticker_history` (lista vacía). No se crean cuatro tablas
(Issuer/Instrument/Listing/BrokerInstrument): con 107 activos y un broker es
sobreingeniería; el YAML con esos campos y un validador cubre la separación
noticia → emisor / operación → listing. Se revisa si entra un segundo broker o
un universo dinámico.

---

### D-21 — 2026-09-16 — Un dato con una sesión de retraso veta la apertura
Decidido por el propietario, preguntado con la consecuencia medida delante.
Solo `freshness == FRESH` permite recomendar abrir; `STALE_1`, `STALE_2_PLUS` y
`PARTIAL_BAR` vetan. No toca el score (INV-03): el activo se analiza y se
puntúa igual, solo deja de ser ejecutable.

Consecuencia medida sobre las 21 pasadas guardadas en la Pi: el retraso europeo
depende de la hora. A las 06:02 y 07:32 UTC lo tienen 45-47 de 47 europeos; a
las 13:32, 18 de 47; a las 20:02, ninguno. Los activos no europeos no lo tienen
nunca (1.197 mediciones, cero). Es decir, con las cuatro pasadas actuales las
dos de la mañana no podrán recomendar europeos. Ver OD-09.

Consecuencia sobre cripto: su barra 24/7 es parcial hasta las 00:00 UTC más el
margen de liquidación, así que cripto no es recomendable en ninguna de las
cuatro pasadas. Se deduce de la regla y nadie lo decidió aparte. Ver OD-10.

### D-22 (propuesta) — 2026-09-17 — Qué mide `frescura-datos`: el dato crudo o el que ve el asesor
Metodológica, pendiente de revisión independiente. Sale de la segunda revisión
de T-005, que encontró los dos caminos contestando distinto sobre el mismo
activo e instante: `7203.T` con Tokio ya cerrado salía `FRESH` / ejecutable por
`analizar` y `PARTIAL_BAR` / no ejecutable por `frescura-datos`.

La causa no es un descuido de parámetros, es una diferencia real: `analizar`
recorta la barra no cerrada con `trim_unclosed_bar` antes de juzgar, y
`frescura-datos` no la recorta porque existe para ver qué sirve el proveedor.

- **(a) Que `frescura-datos` recorte también.** Los dos caminos coinciden, pero
  cambia la serie histórica de retrasos ya medida: para cripto, cuya barra de
  hoy siempre está sin cerrar, pasaría a medirse la de ayer y aparecería un
  retraso de una sesión donde D-21 registró cero. Reescribiría la base de OD-10.
- **(b) Que no recorte y no publique calidad de ejecución.** Es lo aplicado
  ahora: la medición cruda se conserva entera —fecha, antigüedad, ausencias— y
  `data_quality` queda en `None` declarado, en vez de afirmar un veredicto de
  ejecución que esta medición no puede sostener.

**Aplicado (b)** por ser lo que no invalida ninguna medición publicada. Si se
prefiere (a), hay que rehacer las conclusiones de retraso de D-21 y OD-10 con
la serie recortada, no solo cambiar el código.

**Validada por revisión independiente (Codex, 2026-09-17).** Coincide en la
clasificación como metodológica —«cambia qué mide `frescura-datos`»— y en
mantener (b), con dos añadidos que se recogen aquí:

- **Formularlo como contrato, no como omisión.** `frescura-datos` mide *dato
  bruto del proveedor*, no ejecutabilidad del asesor, y eso debe leerse en la
  salida del comando, no solo en este registro. El riesgo real no es el código:
  es que alguien vuelva a interpretar la lectura cruda como «lo que el bot
  puede operar».
- **La tercera vía no sustituye a (b), la extiende.** En vez de elegir una de
  las dos lecturas, publicar ambas con nombres distintos —`raw_freshness` para
  la barra servida por el proveedor y `advisor_effective_freshness` para la que
  ve `analizar` tras `trim_unclosed_bar`—. Queda como trabajo futuro, no como
  requisito para cerrar esta.

**Criterio de cierre acordado:** ningún campo con el mismo nombre puede
significar cosas distintas en dos comandos. Para llegar ahí hay que medir las
divergencias `raw` contra `effective` por plaza y pasada, con cripto contado
aparte, el impacto sobre los vetos de D-21, y los casos frontera: Tokio ya
cerrado, Europa antes y después de la publicación de la barra, y cripto 24/7.

### D-23 — 2026-09-17 — Primer `universe_vintage_id` canónico
Se registra como primer vintage canónico del universo analizable:
`b160c4c2b4c9827f63876bb876b9c66a0cc1db564b877c021ecb93a5fa64089c`.
Sustituye al identificador provisional de T-002
`80d05f21abad212757d2f06d9f2dd53032b92a342dba90904b3086ea970d0b59`,
que era solo `canonical_hash({"analizables": [symbol…]})`.

La definición canónica vive en `advisor/universe/vintage.py`: SHA-256 del JSON
canónico de los 107 analizables ordenados por `instrument_id`, con
`instrument_id`, `issuer_id`, `primary_symbol`, `primary_market`,
`primary_currency`, `asset_class`, `region`, `added_at`, `valid_to`,
`benchmark` y `benchmark_declared`. Las pasadas ya persistidas conservan el id
provisional; las pasadas nuevas usan el id canónico.

`benchmark_declared` no sobra. `resolve_benchmark_symbol` decide por presencia
del campo, no por su valor, y solo 2 de los 107 analizables lo declaran: sin
esa clave, añadir `benchmark: null` a cualquiera de los otros 105 le cambiaba
el índice comparable —y con él su fortaleza relativa y su puntuación— dejando
el vintage idéntico. Medido sobre `SAP.DE`, cuyo benchmark efectivo pasa de
`^STOXX` a `None` sin mover el hash. Lo encontró la revisión independiente.

Una cosecha congelada registra desde ahora el universo con el que se congeló,
dentro del cuerpo que se hashea. Antes la comprobación existía en
`replay_managed_population` pero `freeze_vintage` no escribía el campo, así que
no saltaba nunca. Consecuencia asumida: las cosechas nuevas tienen un
`data_vintage_id` distinto del que tendrían con el esquema anterior; la cosecha
`071ddb2b…` se sigue leyendo igual.

### D-24 — 2026-09-17 — OA-03, primera tanda: 19 ISIN desde la app del broker
El propietario comprobó en la app de Trade Republic los 18 activos que el bot
ha llegado a recomendar COMPRAR alguna vez —medido sobre las 15 pasadas
guardadas en la Pi, no elegidos a ojo— y aportó el ISIN que muestra la ficha de
cada instrumento. Quedan registrados con
`isin_source: "app de Trade Republic, ficha del instrumento, comprobado por el
propietario"` e `isin_verified_at: 2026-09-17`.

**Por qué esa fuente vale, y por qué es mejor que la web del emisor para este
uso concreto:** identifica el instrumento que el propietario va a comprar de
verdad. La web del emisor dice qué ISIN tiene un fondo; la app dice cuál de
ellos vende el broker, que es la pregunta que importa para ejecutar. Los 18
pasan el dígito de control y su prefijo de país concuerda con la plaza.

Tres de ellos —`IS3N.DE`, `ALV.DE` y `NVDA`— ya tenían ISIN declarado del
universo inicial y **coinciden exactamente**, lo que sube la confianza en los
otros 15 heredados aunque sigan sin fuente primaria. `EXH1.DE` coincide además
con el ISIN que aparece en la ruta del KIID publicado por iShares, obtenido de
forma independiente: doble verificación.

`MRVL` queda pendiente a propósito, porque el propietario no pudo confirmarlo.
`BTC-EUR` se marca `trade_republic: "no"` tras comprobarlo, con la consecuencia
asumida de que deja de ser recomendable (`BROKER_UNAVAILABLE`) pese a haber
llegado a OPERAR dos veces. Las tres criptos pasan a `requires_isin: false`,
que es como el modelo expresa que el ISIN no aplica.

`MRVL` se resolvió después, en la misma sesión: el propietario confirmó que
corresponde a Marvell Technology, Inc. y que está disponible, con ISIN
`US5738741041`. Con él, **los 19 activos de prioridad 1 quedan cerrados**.
El aviso que lo desbloqueó: la empresa cambió de domicilio en 2021, de
*Marvell Technology Group Ltd.* (Bermudas, ISIN `BM…`) a *Marvell Technology,
Inc.* (Delaware, ISIN `US…`), y por eso convivían dos identificadores.

El vintage del universo pasa a
`23afb7bb49c1c7ae8d33207227d1ece459e45417792c5eb6c5c730324903051b`, porque 19
activos cambian de `instrument_id` (de `SYMBOL@MARKET` al ISIN). Está previsto:
cada tanda de OA-03 lo moverá otra vez, y el test
`test_universe_real_tiene_107_analizables_y_vintage_conocido` se actualiza a
propósito con cada una, que es para lo que existe.

### D-25 — 2026-09-17 — OA-03, segunda tanda: 52 ISIN y 48 disponibilidades
El propietario amplió el inventario a mano y aportó 33 ISIN más y la
disponibilidad de 48 activos. **Cuatro filas no se aplicaron tal cual**, y las
cuatro son el motivo por el que la validación no puede quedarse en el dígito de
control:

- `ENI.MI` traía `JP3164630000`, un ISIN **japonés válido** para una empresa
  italiana. Corregido por el propietario a `IT0003132476`.
- `PLTR` traía `2026-09-17`: una fecha, por una columna desplazada al pegar.
  Corregido a `US69608A1088`.
- `BBVA` no existe como símbolo; era la fila de `BBVA.MC` con el sufijo perdido
  al editar. Se identificó sin inferir nada: misma plaza `MCE`, mismo nombre, y
  ninguna fila `BBVA.MC` en la tabla.
- `SOL-EUR` traía `US42328V8761`, válido pero con prefijo `US`: no es la
  criptomoneda sino un producto cotizado sobre ella, que es **otro
  instrumento** que el que el bot mide contra `SOL-EUR`. No se aplicó.

**La regla que sale de aquí:** el dígito de control no detecta un ISIN correcto
de otra cosa. Hay que cruzar además el país del ISIN con la plaza del activo,
que es lo que cazó `ENI.MI` y `SOL-EUR`.

La incoherencia de las criptos se preguntó y se resolvió el mismo día:
`BTC-EUR` **sí está disponible**, y lo que traía la tabla era un desliz. Queda
en `yes` junto con `SOL-EUR`; `ETH-EUR` sigue sin comprobar. Los dos únicos no
disponibles confirmados son `9984.T` (SoftBank Group) y `4GLD.DE` (Xetra-Gold).

Consecuencia: `BTC-EUR` vuelve a ser ejecutable por broker, pero **sigue
vetado por `PARTIAL_BAR`**, porque su sesión 24/7 no cierra hasta las 00:00
UTC. Eso es OD-10, no el broker.

Nota de diseño confirmada de paso: cambiar `trade_republic` **no mueve el
vintage**, y es correcto. El vintage identifica el universo que se analiza, no
lo que el broker vende.

Estado tras la tanda: **52 con ISIN verificado, 52 pendientes, 3 no aplicable**;
45 disponibles, 3 no disponibles, 59 sin comprobar. Los 19 de prioridad 1 —los
que el bot ha llegado a recomendar COMPRAR— están cerrados. Vintage:
`9d0a4c6ff32d604d5829d3b74620a94d28b6a9af5b16bfa9c89d4e7fa7caae54`.

**Trampa de formato, anotada porque volverá a aparecer:** escribir
`trade_republic: yes` sin comillas hace que YAML lo lea como el booleano `True`
y la carga falla. Los valores `yes` y `no` van siempre entrecomillados.

---

`added_at` se obtuvo comparando los conjuntos de símbolos de
`git show 93009da:universe.yaml`, `git show e952f71:universe.yaml` y `HEAD`:
20 instrumentos con `2026-08-27` y 106 con `2026-08-29`. Los ocho listings
alemanes del universo inicial que pasaron a primarios actuales son
instrumentos distintos del mismo emisor; no son `ticker_history`.

---

## OWNER_DECISION_REQUIRED

Formato obligatorio para cada una: pregunta exacta, alternativas, consecuencia
de cada una, recomendación técnica, trabajo bloqueado. Mientras no haya
respuesta, la tarea afectada queda `BLOQUEADA_POR_OWNER` y **se hace todo lo
demás**.

### OD-01 — Proveedor de fundamentales y su coste
- **Pregunta:** ¿Se contrata un proveedor de fundamentales point-in-time (con
  fecha de publicación y revisiones) y con qué presupuesto mensual?
- **Alternativas:** (a) proveedor de pago con point-in-time (p. ej. datos con
  `filing_date`); (b) `yfinance` fundamentals (sin fecha de publicación
  fiable: no sirve para backtest, solo para producción con etiqueta); (c) no
  hacer fundamentales.
- **Consecuencia:** (a) habilita P8 y la dimensión de 20 puntos con medición;
  (b) habilita solo shadow en producción, P8 imposible; (c) el score queda
  normalizado sobre 80 para siempre y el ratio pesa 25 %.
- **Recomendación técnica:** (b) ahora para acumular en shadow con etiqueta
  «no point-in-time»; decidir (a) cuando P9 tenga muestra y se sepa si el
  contexto aporta algo.
- **Bloquea:** P8. No bloquea B0, noticias, sentimiento ni macro.

### OD-02 — Segunda fuente de datos para las plazas europeas
- **Pregunta:** ¿Se paga otra fuente para Xetra/Euronext si el histórico de
  frescura demuestra huecos recurrentes?
- **Alternativas:** (a) sí, si la recurrencia supera un umbral; (b) no, se
  vive con `INCOMPLETO` y el veto.
- **Consecuencia:** (a) coste mensual, más código de proveedor (ficha de
  proveedor obligatoria); (b) los lunes con hueco no se opera Europa.
- **Recomendación técnica:** no decidir aún. La tarea A-01 (interpretar el
  histórico de frescura de la Pi, que acumula desde el 2 de septiembre)
  produce la cifra de recurrencia; decidir con ella. Umbral propuesto para
  reabrir: > 2 sesiones perdidas por mes en más de 10 activos.
- **Bloquea:** nada hoy.

### OD-03 — Presupuesto de llamadas LLM para contexto
- **Pregunta:** ¿Cuántas llamadas/mes (o euros/mes) se admiten para relevancia
  de noticias, sentimiento y Context Analyst en shadow?
- **Alternativas:** (a) solo por informe, top 5 (coste actual); (b) por activo
  con noticias nuevas, con tope diario; (c) sin LLM hasta P9.
- **Recomendación técnica:** (b) con tope 50 llamadas/día y filtro previo por
  reglas (símbolo/emisor, deduplicación por `content_hash`, fuente).
- **Bloquea:** B-03 (sentimiento con LLM) y B-06 (Context Analyst). No
  bloquea la captura y almacenamiento de datos.

### OD-08 — Duración de la validación forward (P10)
- **Pregunta:** ¿Cuánto dura P10 con configuración congelada?
- **Alternativas:** 3 meses (≈ 60 sesiones) / 6 meses / 12 meses.
- **Consecuencia:** 3 meses da ~1 bloque de swing por régimen: sirve para
  detectar un fallo grosero, no para confirmar una ventaja pequeña; 6 meses es
  el mínimo para un intervalo útil; 12 cubre más regímenes.
- **Recomendación técnica:** 6 meses; si no hay respuesta al llegar a GATE P7,
  se usa 6 meses.
- **Bloquea:** solo la fecha de fin de P10.

---

### OD-09 — Horario de las pasadas, ahora que el dato retrasado veta
- **Pregunta:** ¿se aceptan mañanas solo con valores de EE. UU., o se mueven las pasadas?
- **Alternativas:** dejarlo como está (07:00, 08:30, 14:30, 21:00 local) / mover
  las dos de la mañana a después de que el proveedor publique el cierre europeo /
  declarar explícitamente que las de la mañana son para EE. UU. y Asia.
- **Consecuencia:** con D-21, las dos pasadas de la mañana no podrán recomendar
  ningún activo europeo. Medido, no supuesto.
- **Bloquea:** nada técnico; cambia qué recomienda el bot y cuándo.

### OD-10 — Cripto con la regla de D-21
- **Pregunta:** ¿cripto deja de ser recomendable, o su barra parcial no veta?
- **Consecuencia:** tal como queda D-21, las tres criptos no son recomendables
  en ninguna pasada, porque su sesión 24/7 solo cierra a las 00:00 UTC.
- **Bloquea:** nada; hoy cripto no ha generado ninguna señal OPERAR.

---

## OWNER_ACTION_REQUIRED

### OA-01 — Mergear la cadena en `main` · HECHA el 2026-09-16
Las cuatro ramas encadenadas (PR 1, T-001, T-002, T-003 con sus correcciones)
se fusionaron en fast-forward: `main` pasa de `6d32cf2` a `74c4ce4`, 10
commits, pusheado. Verificado sobre `main` antes de subir: 435 tests, `ruff` y
`mypy` limpios.

### OA-02 — Activar branch protection en GitHub para `main`
Required checks: el workflow de C-00. Prohibir push directo y force-push.
T-001 hecho (`e5ed089`): checks requeridos `checks (3.12)` y `checks (3.13)`; bloque completo en `evidence/2026-09-14-T-001-ci/README.md`. Pendiente de activar por el propietario.

### OA-03 — Verificar 89 ISIN y la disponibilidad en Trade Republic de los 107
Trabajo manual con fuente primaria (Deutsche Börse, Euronext, la app del
broker). Guardar `isin_verified_at`, `isin_source`, `trade_republic_checked_at`
en `universe.yaml` (campos que añade A-00). No modifica la señal.

### OA-04 — Desplegar en la Pi cada tag aceptado y ejecutar la verificación en la Pi
Hecha el 2026-09-16 para `a8a70e2` (evidencia en `evidence/2026-09-16-despliegue-pi/`).
Queda como acción recurrente para las siguientes entregas.
Hasta que C-03 automatice el despliegue por tag, el propietario ejecuta en la
Pi: `git fetch && git checkout <tag> && pip install -r requirements.txt &&
python -m pytest -q && python -m advisor.main verificar-systemd`.

### D-26 — 2026-09-17 — OA-03, tercera tanda: el universo queda cubierto
El propietario completó la tabla. Se aplican **40 ISIN más y 57 cambios de
disponibilidad**: quedan **92 activos con ISIN**, 95 disponibles, 10 no
disponibles y solo 2 sin comprobar (`UCG.MI` y `1211.HK`). Ninguno de los 92
discrepa de los ya registrados y ningún ISIN se repite en dos activos.

**Dos filas quedan PENDIENTES a propósito, y no son erratas:**
`SAN.MC` traía `US05964H1059` y `005930.KS` traía `US7960508882`. Los dos son
ISIN estadounidenses válidos, pero corresponden al **ADR/GDR**, no a la acción
local que el bot analiza en Madrid y en Seúl. Es el mismo caso que `TSM` e
`INFY`, invertido: aquí el bot mide la acción original y el broker ofrece el
recibo de depósito, que es **otro instrumento** —otra plaza, otra divisa, otro
horario y otra liquidez—. Decisión del propietario: dejarlos pendientes hasta
resolver si se registra el ADR anotando la diferencia o se cambia el símbolo
analizado. Estado `PENDIENTE_ADR` en el inventario.

De los 12 activos sin ISIN, **10 es porque están marcados no disponibles**
(`LRCX`, `JPM`, `GE`, `RTX`, `RHM.DE`, `NOVO-B.CO`, `9984.T`, `000660.KS`,
`DFEN.DE`, `4GLD.DE`), lo cual es coherente: no tiene sentido registrar el
identificador de algo que no se puede comprar.

Caso que ilustra que ISIN y disponibilidad son preguntas distintas: `DFEN.DE`
tenía su ISIN verificado contra el KID de VanEck por la mañana y resultó **no
disponible** en el broker. El identificador era correcto y aun así no sirve.

Vintage: `894ce776ff8572b3a9dfc97a724f96789122e0dd2c46eef55045d4968e0b5fb0`.
