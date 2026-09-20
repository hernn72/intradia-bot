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

### D-29 — 2026-09-18 — Qué código emite un precio por encima de la entrada máxima · CERRADA en T-010
El repositorio se contradice desde antes de hoy. `docs/plan-ejecucion.md`, en su
caso de regresión de `EXH1.DE`, pide `RR_TOO_LOW` para `entry 56,63`; la ficha de
T-007, el roadmap y **D-06** piden `ABOVE_MAX_ENTRY`. La causa es que
`entry_max = min(entry_max_tecnica, entry_max_rr)` y el RR manda en 102 de los
107 activos (medido en T-008), así que un precio por encima de la máxima
aplicada incumple también el ratio: las dos condiciones son ciertas a la vez y
solo el orden de las ramas decide la etiqueta. Con cualquiera de los dos órdenes
uno de los códigos queda casi inalcanzable.

En T-008 se revirtió al orden que respeta D-06 (`ABOVE_MAX_ENTRY` primero),
porque `execution_code` se persiste y cambiar su significado a mitad de camino
rompe la reconstrucción que exige GATE PROD.

**Medido en T-009 (2026-09-18), y la respuesta es contundente.** Sobre la
cosecha `071ddb2b…`, de las 1.189 señales perdidas en swing y las 962 en medio:

    ABOVE_MAX_ENTRY   1146/1189  (96,4 %)      926/962  (96,3 %)
    INVALID_STOP        31/1189                 25/962
    INVALID_TARGET      12/1189                 11/962
    RR_TOO_LOW           0/1189                  0/962

`RR_TOO_LOW` es **inalcanzable**: 0 de 2.151. Con `entry_max` definido como la
rotura del RR, ningún precio que respete la máxima puede incumplir el ratio. Los
dos códigos no reparten un espacio: uno está muerto, y cuál de ellos lo esté
depende solo del orden de dos ramas.

**Queda por decidir en T-010**, con estos números delante, entre: (a) mantener
el orden actual, que respeta D-06, y retirar `RR_TOO_LOW` del vocabulario de
ejecución por inalcanzable, documentándolo; o (b) invertir el orden, cumplir la
línea del plan y asumir que el muerto pasa a ser `ABOVE_MAX_ENTRY`, lo que
obliga a un punto de corte declarado porque `execution_code` se persiste.
**Decidido en T-010 (2026-09-18), opción (a).** Se mantiene el orden actual:
`ABOVE_MAX_ENTRY` primero, que es lo que D-06 dice y lo que producción lleva
emitiendo desde PR 1, así que las 4.963 filas persistidas en la Pi conservan su
significado sin punto de corte. `RR_TOO_LOW` **no se borra**: hoy es
inalcanzable por construcción —si `precio ≤ entry_max ≤ entry_max_rr`, el ratio
llega al mínimo— pero deja de serlo en cuanto P4 (A-04) introduzca holgura de
entrada y `entry_max` pueda superar a `entry_max_rr`; es la guarda de ese
escenario, y borrarla hoy sería quitarla justo antes de necesitarla. Se corrige
la línea del caso EXH1 en `docs/plan-ejecucion.md`, que era la fuente anterior a
PR 1, y `test_exh1_regresion_de_la_linea_0` la fija con los cuatro precios.

**Medición T-009, 2026-09-18, sin decisión de política.** Con la cosecha
`071ddb2b…`, horizonte `swing`, la población perdida por ejecución contiene
`ABOVE_MAX_ENTRY=1146`, `RR_TOO_LOW=0`, `INVALID_STOP=31` e
`INVALID_TARGET=12`. En `medio`: `ABOVE_MAX_ENTRY=926`, `RR_TOO_LOW=0`,
`INVALID_STOP=25`, `INVALID_TARGET=11`. Esto describe el orden actual
(`ABOVE_MAX_ENTRY` antes que `RR_TOO_LOW`); no resuelve D-29 ni cambia
`evaluate_trade_at_entry`. La decisión sigue pendiente para P4/A-04.

La misma entrega constata que no se cambia la política de entrada: no hay
holgura nueva, no se mueve `entry_max`, no se toca el score y el
contrafactual se etiqueta como medición, no recomendación.

### D-30 — 2026-09-18 — GATE L0 cruzado
Se cruza con las seis métricas medidas a la vez sobre `main` (`d8cbc37` más la
limpieza de T-010) y los siete requisitos respondidos con evidencia, en
`evidence/2026-09-18-L0-cierre/`. La métrica 6 se midió **en la Pi** (2.460
filas con `run_id` desde la migración, sin solape con las 2.503 anteriores),
porque en el portátil no se guarda nada. Consecuencias: A-02 (T-013) pasa de
bloqueada a pendiente, **con T-016 por delante** porque el veredicto de P2.5
puede llevar un intervalo falso; y el despliegue de la línea 0 en la Pi (OA-04)
deja de tener motivo para esperar: la Pi está en `894fa75`, cuatro entregas por
detrás.

Lo que el gate no afirma: ventaja del sistema (P10), reproducibilidad del
backtest en vivo (T-015), ni que la Pi ejecute esto.

### D-31 — 2026-09-18 — Baja de `SAN.MC`, `UCG.MI`, `005930.KS` y `1211.HK`: no están en Trade Republic
Decisión del propietario. Los cuatro salen del universo analizable porque no se
pueden comprar en el broker: `UCG.MI` y `1211.HK` estaban sin comprobar desde
OA-03 y resultan no disponibles; `SAN.MC` y `005930.KS` eran el caso
`PENDIENTE_ADR` de D-26 —en la app existe el ADR/GDR estadounidense, que es
otro instrumento, no la acción local que el bot analiza— y se resuelve dándolos
de baja en vez de cambiar el símbolo analizado.

**Cómo se hace la baja, y por qué no se borran las líneas.** Se marcan con
`valid_to: 2026-09-18`, `analizable: false`, `trade_republic: "no"` y nota;
`added_at`, ISIN y el resto de la identidad se conservan. La cosecha congelada
`071ddb2b…` contiene sus 4 series y la base de la Pi tiene 4.963 filas que los
referencian: borrar la definición los dejaría huérfanos y rompería la
reconstrucción. Es para lo que A-00 dejó `valid_to` y `delisted_at` «vacíos
hasta que haga falta».

Consecuencias: **126 activos, 103 analizables** (antes 107). Vintage nuevo
`c8496446d9b04795b8533e25e794c6141a4e73db73c0ef9bf98599b70f952132` (INV-19).
Los resultados publicados hasta hoy —P2.3 con 121.786 señales, T-009, la línea
base de L0— son sobre los 107 y llevan su vintage; A-02 rehará el laboratorio
sobre los 103, y la comparación entre ambos debe declarar la diferencia de
población. Quedan **10 activos** marcados `no` que siguen siendo analizables y
vetados como `BROKER_UNAVAILABLE` (D-26); no se tocan aquí, es otra decisión.

## OWNER_DECISION_REQUIRED

Formato obligatorio para cada una: pregunta exacta, alternativas, consecuencia
de cada una, recomendación técnica, trabajo bloqueado. Mientras no haya
respuesta, la tarea afectada queda `BLOQUEADA_POR_OWNER` y **se hace todo lo
demás**.

### OD-01 — Proveedor de fundamentales y su coste · en prueba desde D-39
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
- **Paso intermedio decidido el 2026-09-20 (D-39):** antes de elegir entre (a),
  (b) y (c) se prueba **EODHD en su plan gratuito** con uno o dos valores
  europeos, para ver si el JSON real trae `filing_date`, estados financieros,
  ISIN, EPS, deuda y FCF. La respuesta a `filing_date` es la que decide entre
  (a) y (b).
- **Bloquea:** P8. No bloquea B0, noticias, sentimiento ni macro.

### OD-02 — Segunda fuente de datos para las plazas europeas · CERRADA en D-40
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
- **Se decide junto con OD-01** (2026-09-20): el mismo plan de pago de EODHD
  podría cubrir la segunda fuente de precios y los fundamentales point-in-time,
  y su EOD europeo ya responde en el plan gratuito (ver D-39). Ninguna de las dos
  se decide hasta tener la cifra de T-012.
- **T-012 ENTREGADA el 2026-09-20: la cifra ya existe, falta que el propietario
  elija una definición.** Sobre 4.143 mediciones y 39 pasadas de la Pi
  (`evidence/2026-09-20-T-012-frescura-historico/`):
  **el retraso es exclusivamente europeo**. A las 06 y 07 UTC, 278/329 y 277/328
  mediciones europeas llegan con retraso ≥ 1 sesión, frente a **0 de 399** de
  NASDAQ, NYSE, JPX, HKG y KSC. A las 13 UTC, 135/327 en Europa y 0/397 fuera. A
  las 20 UTC, **0 en todas partes**.
  La respuesta al umbral —más de 2 sesiones perdidas por mes en más de 10
  activos— **depende de qué sea una «sesión perdida», que el pre-registro no
  definió**: (a) si el hueco debe seguir ausente al final, **0 activos** lo
  superan y el umbral NO se alcanza; (b) si basta con que faltara en alguna
  pasada, 18; (c) contando además los retrasos que luego llegan, 47. La
  diferencia es la conclusión entera: casi todo lo que parece hueco es retraso
  que acaba llegando. **Decisión pendiente: qué lectura vale.**
  Dos avisos que van con la cifra: la ventana cruza **14 versiones de código** y
  solo una pasada usa la regla vigente de D-36/D-37; y son 18 días sin vacaciones
  ni cierres largos, así que toda tasa mensual es provisional.
- **Criterio fijado por el propietario el 2026-09-20 (sigue abierta):** T-012
  debe decir **cuánto falla y cuánto se retrasa `yfinance` en nuestras plazas
  europeas**, y con esa cifra se decide si hace falta una segunda fuente **para
  todo el universo o solo para determinados mercados o tickers**. La alternativa
  (c) «segunda fuente parcial» pasa a ser explícita y es la que hay que medir:
  T-012 tiene que publicar el retraso **por plaza y por símbolo**, no solo un
  agregado. El despliegue de `v0.3.0` da el primer dato con la regla nueva: los
  25 vetos por dato de la pasada del 2026-09-20 son **todos** europeos, 21
  `STALE_DATA` y 4 `MISSING_RECENT_DATA`, y ninguno de otra plaza.
- **Bloquea:** nada hoy.

### OD-03 — Presupuesto de llamadas LLM para contexto · CERRADA en D-38
- **Pregunta:** ¿Cuántas llamadas/mes (o euros/mes) se admiten para relevancia
  de noticias, sentimiento y Context Analyst en shadow?
- **Alternativas:** (a) solo por informe, top 5 (coste actual); (b) por activo
  con noticias nuevas, con tope diario; (c) sin LLM hasta P9.
- **Recomendación técnica:** (b) con tope 50 llamadas/día y filtro previo por
  reglas (símbolo/emisor, deduplicación por `content_hash`, fuente).
- **Bloquea:** B-03 (sentimiento con LLM) y B-06 (Context Analyst). No
  bloquea la captura y almacenamiento de datos. **Desbloqueadas en D-38**, que
  fija un tope en euros en vez de en llamadas.

### OD-08 — Duración de la validación forward (P10)
- **Pregunta:** ¿Cuánto dura P10 con configuración congelada?
- **Alternativas:** 3 meses (≈ 60 sesiones) / 6 meses / 12 meses.
- **Consecuencia:** 3 meses da ~1 bloque de swing por régimen: sirve para
  detectar un fallo grosero, no para confirmar una ventaja pequeña; 6 meses es
  el mínimo para un intervalo útil; 12 cubre más regímenes.
- **Recomendación técnica:** 6 meses; si no hay respuesta al llegar a GATE P7,
  se usa 6 meses.
- **Orientación del propietario, 2026-09-20 (sigue abierta hasta GATE P7):** no
  fijarla solo por calendario, sino **por tiempo y por número de señales
  cerradas a la vez**. Punto de partida: **mínimo 8 semanas y al menos 100
  señales cerradas**; si al cumplirse las 8 semanas no se han alcanzado las 100,
  se continúa hasta alcanzarlas. 12 semanas se considera mejor para una
  validación sólida.
- **Consecuencia medida sobre el backtest (2026-09-20), que conviene tener
  delante al cerrarla:** la cosecha `071ddb2b…` da **866 operaciones en 5 años**
  sobre el universo de entonces, es decir ~3,3 señales cerradas por semana, y
  ~2,9 al reescalar a los 93 analizables de hoy. Con ese ritmo, **100 señales
  cerradas piden entre 30 y 35 semanas**: el que manda es el número de señales,
  no las 8 ni las 12 semanas, y P10 duraría del orden de siete u ocho meses. La
  cifra es la tasa del backtest sobre la cosecha, no la de producción, así que
  se recalcula con el ritmo real antes de fijar el número.
- **Condición metodológica:** la regla de parada se fija **antes** de empezar y
  se para en el primer instante en que se cumplen las dos condiciones. Parar
  «cuando la cifra se ve bien» invalida P10, que es justo la prueba que no está
  condicionada.
- **Bloquea:** solo la fecha de fin de P10.

---

### OD-09 — Horario de las pasadas, ahora que el dato retrasado veta · CERRADA en D-36
- **Pregunta:** ¿se aceptan mañanas solo con valores de EE. UU., o se mueven las pasadas?
- **Alternativas:** dejarlo como está (07:00, 08:30, 14:30, 21:00 local) / mover
  las dos de la mañana a después de que el proveedor publique el cierre europeo /
  declarar explícitamente que las de la mañana son para EE. UU. y Asia.
- **Consecuencia:** con D-21, las dos pasadas de la mañana no podrán recomendar
  ningún activo europeo. Medido, no supuesto.
- **Bloquea:** nada técnico; cambia qué recomienda el bot y cuándo.

### OD-10 — Cripto con la regla de D-21 · CERRADA en D-37
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

### OA-02 — Activar branch protection en GitHub para `main` · HECHA el 2026-09-18
Comprobado por API: `checks (3.12)` y `checks (3.13)` obligatorios con `strict`, `enforce_admins` activo, force-push y borrado bloqueados, PR obligatorio. Desde entonces todo entra por PR (#1 T-008, #2 T-009). El CI cazó el primer error el mismo día (un script de evidencia sin lint), que es para lo que estaba.
Required checks: el workflow de C-00. Prohibir push directo y force-push.
T-001 hecho (`e5ed089`): checks requeridos `checks (3.12)` y `checks (3.13)`; bloque completo en `evidence/2026-09-14-T-001-ci/README.md`. Pendiente de activar por el propietario.

### OA-03 — Verificar 89 ISIN y la disponibilidad en Trade Republic de los 107
Trabajo manual con fuente primaria (Deutsche Börse, Euronext, la app del
broker). Guardar `isin_verified_at`, `isin_source`, `trade_republic_checked_at`
en `universe.yaml` (campos que añade A-00). No modifica la señal.

### OA-04 — Desplegar en la Pi cada tag aceptado y ejecutar la verificación en la Pi
Hecha el 2026-09-16 para `a8a70e2` (evidencia en `evidence/2026-09-16-despliegue-pi/`).
Queda como acción recurrente para las siguientes entregas.

**Al 2026-09-18 el despliegue ya es por tag y el rollback está probado**
(evidencia en `evidence/2026-09-18-OA-04-ensayo-release/`). La Pi corre
**`v0.2.0` = `785daf4`**, esquema v5, con `verificar-release` dando `EN_TAG` y
código 0. El ensayo completo —desplegar, migrar v4→v5 con la base real,
restaurar el backup previo, volver a `v0.1.0`, ejecutar una pasada con el código
viejo y regresar— se hizo con los timers parados y con red de seguridad en cada
paso. El procedimiento vive en `docs/despliegue-y-rollback.md` y sustituye a la
receta manual de arriba.

**Al 2026-09-20 la Pi corre `v0.3.0` = `03e1ec3`**, esquema v5 sin migración
(entre los dos tags no hay ninguna), `verificar-release` en `EN_TAG` con código
0 y el manifiesto persistido llevando `release_tag v0.3.0`. Es el primer
despliegue que aplica el procedimiento sin ensayo previo, y se pudo porque el
salto no toca el esquema. Evidencia en `evidence/2026-09-20-despliegue-v030/`,
incluida la primera medición de a quién veta D-21 en producción: 68
`EXECUTABLE`, 21 `STALE_DATA` y 4 `MISSING_RECENT_DATA`, los 25 europeos.

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

### D-27 — 2026-09-18 — `BROKER_UNVERIFIED` pasa a accion propia, no a compra
La disponibilidad del broker sigue separada de la senal (D-04), pero el informe
deja de presentar un `unknown` como `COMPRAR`: si el setup y la ejecucion son
validos y el broker esta sin verificar, la accion publicada es
`VERIFICAR_BROKER`. Si el broker esta marcado como no disponible, la accion no
es operar.

Consecuencia medida en T-007 con el universo vigente: ya no hay 107 `unknown`;
hay 95 `yes`, 10 `no` y 2 `unknown`. En la pasada real del 2026-09-18 ningun
`unknown` alcanzo setup operativo, asi que no aparecio `VERIFICAR_BROKER` en el
informe real; `9984.T`, que estaba en `no`, paso de radar con
`BROKER_UNAVAILABLE` a descartado por `BROKER_UNAVAILABLE`. El score no cambia.

**Corregido en la revision independiente (2026-09-18):** la accion nueva salia
de la poblacion de `POLICY_OPERAR` del backtest, porque `engine.py` filtraba por
`accion == ACCION_COMPRAR`. Eso hacia depender la poblacion que mide el
laboratorio de un metadato de broker que cambia con cada tanda de OA-03, en
contra de D-04 y de INV-04, y ademas hacia que esas operaciones desaparecieran
sin rastro del informe del backtest. Se introduce `ACCIONES_OPERABLES`
(`COMPRAR` + `VERIFICAR_BROKER`) en `advisor/backtest/engine.py`, se anade la
fila propia en `advisor/backtest/report.py` y se deja de contar
`VERIFICAR_BROKER` como veto. Medido: misma senal (score 85, mismos niveles,
mismo contexto) entra en la poblacion con `yes` y, antes de la correccion, no
entraba con `unknown`. Afecta hoy a `UCG.MI` y `1211.HK`, los dos unicos
analizables sin verificar.

**Hallazgo abierto que esto deja a la vista (FOLLOW_UP, va a T-009):** los 10
activos marcados `no` en el broker siguen fuera de la poblacion de
`POLICY_OPERAR`, y eso **ya ocurria antes de T-007** (PR 1). La poblacion del
laboratorio no deberia depender del broker en ningun caso; se decide y se
corrige al medir el filtro de ejecucion aparte del score.

### D-28 — 2026-09-18 — El recorte diario usa el cierre de la sesion concreta
`trim_unclosed_bar` deja de comparar contra el cierre regular hardcodeado y usa
`exchange_calendars.session_close(sesion)` para la sesion concreta. Esto evita
recortar barras ya cerradas en medias sesiones sin duplicar horarios de apertura
o cierre en `MARKET_SESSIONS`.

Consecuencia medida con `exchange_calendars==4.13.2` entre 2025-11-01 y
2026-12-31: XETRA tiene 2 cierres a las 14:00, NYSE 4 cierres a las 13:00 y PAR
4 cierres a las 14:05. La primera fecha futura que muerde al bot es
2026-11-27 para NYSE/NASDAQ.

### D-32 — 2026-09-18 — El rollback de código no deshace migraciones
Una migración de esquema no se revierte sola, y un tag anterior no sabe leer un
esquema posterior. La regla, escrita antes de necesitarla: **volver a un tag
anterior no toca la base**. Si entre los dos tags hubo migración, se restaura el
backup previo a esa migración —`intradia.db.bak-<fecha>-pre-vN`, que la propia
migración crea— y se acepta explícitamente la pérdida de las pasadas guardadas
desde entonces. El procedimiento literal está en `docs/despliegue-y-rollback.md`.

Consecuencia para `verificar-backup`: si la copia que sostiene el rollback puede
ser una copia manual, el comando no puede llamarla «inválida» solo porque no
esté en `backup_log`. Desde T-011 informa por separado integridad, esquema,
conteos y registro, y reserva `INVALIDO` para lo que de verdad no se puede
restaurar. El caso que lo motivó ocurrió el 2026-09-18: una copia `cp` íntegra,
con `integrity_check = ok`, esquema 4 y los mismos recuentos que la base viva,
salía como «Backup inválido» en pleno despliegue.

### D-33 — 2026-09-18 — `config_hash` identifica la configuración lógica, y se versiona
`config_hash` incluía `db_path` y `universe_path`, así que la misma
configuración en el portátil y en la Pi daba hashes distintos y la
reconstrucción de D-10 no podía decir «misma config» comparándolos. Las dos
claves salen del hash: describen dónde está cada fichero, no qué decide el
asesor.

**Los manifiestos anteriores no se recalculan.** Su hash se calculó con las
rutas dentro y recalcularlo sería inventar un dato que nadie midió. Para que la
reconstrucción sepa con qué regla se calculó cada uno, el manifiesto guarda
`config_hash_version`: las filas que ya existían quedan en `1` (la migración v5
las marca así) y las nuevas nacen con `2`. Comparar dos manifiestos exige
comparar también su versión: dos hashes de versiones distintas no son
comparables aunque coincidieran por azar.

Alcanza también a los informes de investigación: `filtro-ejecucion` imprime
`config_hash` en su cabecera, así que los publicados hasta hoy —T-009 entre
ellos— llevan el hash de la regla 1. No se recalculan por el mismo motivo; al
compararlos con uno nuevo hay que declarar que son de reglas distintas.

**Corrección medida el 2026-09-18, el mismo día, en el ensayo de OA-04.** El
motivo que daba T-017 —«la misma configuración en el portátil y en la Pi da
hashes distintos»— **no era cierto en este despliegue**: las dos máquinas dan
`271d46b2` con la regla 1 y `1294c526` con la regla 2, porque las dos usan las
mismas rutas relativas (`intradia.db`, `universe.yaml`) y la cadena que entra en
el hash es idéntica. La decisión se mantiene por la otra mitad del argumento —la
identidad de una configuración no puede depender de dónde están los ficheros, y
en cuanto aparece una ruta absoluta, como la que introduce el propio
procedimiento de rollback, los hashes se separarían—, pero conviene no repetir
el motivo falso: ese criterio de aceptación ya se cumplía antes del cambio.

### D-34 — 2026-09-18 — Las cifras de backtest en vivo no son reproducibles, y lo que se hace con las publicadas
Medido tres veces seguidas sobre el mismo commit, el mismo universo y la misma
configuración, con minutos de diferencia: **869, 862 y 867 operaciones**, y R
total de 149,19 a 157,10 (un 5 % de diferencia entre dos pasadas que solo se
distinguen en la hora). La causa es estructural: el periodo es relativo a
*ahora*, el proveedor revisa barras y la última vela se mueve dentro de la
sesión. Tres pasadas sobre la cosecha congelada `071ddb2b…` dan 866 y son el
mismo fichero byte a byte.

**Decisión.** Cualquier cifra de backtest que se publique, se compare o sostenga
un criterio de aceptación se produce con `backtest --vintage <id>`. El modo en
vivo sigue existiendo para mirar el día de hoy y **declara en su cabecera que no
es reproducible**; no se le permite fingir determinismo (INV-16).

**Qué pasa con lo ya publicado.** Las cifras anteriores a esta ficha se hicieron
en vivo: la línea base de la línea 0 (`evidence/2026-09-14-L0-baseline/`) y las
tablas de T-007 a T-009 entre ellas. **No se rehacen ahora y no se borran**; se
etiquetan como no reproducibles allí donde se citen. Rehacerlas sobre la cosecha
es trabajo de A-02 (T-013), que ya va a repetir P2.3, P2.4 y P2.5 una sola vez
sobre `071ddb2b…`, y no tiene sentido hacerlo dos veces. Lo que **sí** cambia
desde hoy: ninguna comparación nueva puede apoyarse en dos pasadas en vivo.

**Tres consecuencias medidas que hay que declarar al comparar cosecha y vivo**,
y que el informe imprime antes de cualquier cifra:

1. Las fechas: la cosecha acaba el 2026-08-30 y el vivo, hoy.
2. La cosecha se congeló con 5 años para todos los símbolos, así que no lleva el
   histórico previo que el modo en vivo descarga para la media de tendencia: las
   primeras 199 sesiones del índice corren sin ese contexto.
3. **Los precios no son los mismos números.** `get_history` (vivo) llama a
   `ticker.history(...)` sin `auto_adjust`, que en yfinance 1.7.0 devuelve
   precios **ajustados** por dividendo; la cosecha se congeló con
   `get_raw_history(..., auto_adjust=False, actions=True)`, que conserva el
   material **bruto**. En la cosecha real `SAP.DE` acumula 5 dividendos que suman
   11,55 y `AAPL` 20 que suman 4,90: para esos activos el `Close` difiere entre
   modos y con él ATR, niveles y salidas. Lo encontró la revisión independiente
   de Codex; sin declararlo, alguien leería la diferencia 866 vs 862-869 como
   una discrepancia del sistema en vez de como dos mediciones distintas.

No se unifica el ajuste: cambiar el modo en vivo está fuera del alcance de la
ficha, y reajustar la cosecha rompería sus hashes (INV-13) y la convención
pre-registrada de P2, que trabaja con material bruto y trata el dividendo aparte
en `gap_for_catalyst`. Lo que se hace es **declararlo en cada informe**.

### D-35 — 2026-09-18 — Baja de los diez activos marcados `no` en el broker
Decisión del propietario, y cierre de lo que D-31 dejó abierto a propósito.
Aquel día se dieron de baja cuatro activos por no estar en Trade Republic y
quedaron **diez más en la misma situación** —verificados como `no` en OA-03—
que seguían siendo analizables y vetados como `BROKER_UNAVAILABLE`. Era la misma
situación con decisión distinta; hoy se toma: salen del universo analizable.

Los diez: `LRCX`, `JPM`, `GE`, `RTX`, `RHM.DE`, `NOVO-B.CO`, `9984.T`,
`000660.KS`, `DFEN.DE` y `4GLD.DE`.

**Se hace como D-31 y por el mismo motivo**: `valid_to: 2026-09-18`,
`analizable: false` y nota, **sin borrar las líneas**. Las cosechas congeladas
contienen sus series y la base de la Pi tiene filas que los referencian; borrar
la definición los dejaría huérfanos y rompería la reconstrucción. Y `valid_to`
es obligatorio junto a `analizable: false`: sin él, `context_assets_of` los
tomaría por índices de contexto y aparecerían en «Situación global»,
descargándose en cada pasada. Comprobado: los activos de contexto siguen siendo
19 y ninguno de los diez está entre ellos.

Consecuencias: **126 activos, 93 analizables** (antes 103). Vintage nuevo
`237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19` (INV-19).
Ya no queda **ningún** activo analizable con `trade_republic: "no"`, así que el
motivo de descarte `BROKER_UNAVAILABLE` deja de aplicarse a nadie en producción;
se conserva en el código como guarda, igual que `RR_TOO_LOW` tras D-29.

**Efecto sobre lo medido, que hay que declarar al comparar.** Todo lo publicado
hasta hoy es sobre 107 o sobre 103: P2.3 con sus 121.786 señales, T-007 a T-009,
la línea base de la línea 0 y el backtest de T-015 (866 operaciones sobre los
103). A-02 rehará el laboratorio sobre la población vigente y **la comparación
con lo anterior debe declarar las tres poblaciones**, no solo dos.

### D-36 — 2026-09-18 — OD-09 cerrada: los horarios se mantienen y D-21 actúa por activo
Decisión del propietario. **Las pasadas siguen siendo 07:00, 08:30, 14:30 y
21:00 locales.** No se redefinen las de la mañana como «solo EE. UU. y Asia», ni
se veta a Europa por la hora: eso sería un veto por reloj, no por dato.

La regla es por activo y sobre disponibilidad real: **veta solo si la última
barra que ya debería estar cerrada todavía no está**. A las 07:00 la sesión
europea de ayer ya cerró y su barra es exigible; si el proveedor aún no la ha
publicado, ese activo queda vetado esa pasada, y **si en el futuro la entrega
antes, vuelve a ser elegible sin tocar nada**, porque no hay ninguna regla
horaria que lo impida.

**Lo que esto cambia de verdad**, y es lo que no se veía antes: la frontera deja
de ser «hoy». `sessions_approx` se calculaba con `closed_sessions_between(última
barra, hoy)`, que **excluye el día de referencia**, así que una sesión que
cerraba hoy nunca se contaba como exigible. Medido el 2026-09-18 a las 16:20
UTC sobre el universo real, corriendo `main` y la rama a la vez: la calidad pasa
de `INCOMPLETO=41, OK=52` a `DEGRADADO=9, INCOMPLETO=41, OK=43`. **Los 9 nuevos
son los 6 japoneses y los 3 de Hong Kong**: su sesión cerró hace horas y el
proveedor no la ha publicado. Comprobado contra el dato crudo —`7203.T` y
`0700.HK` van por el 17/09 mientras `SAP.DE` y `AAPL` ya tienen el 18/09—, así
que es un veto correcto, no un falso positivo.

**El caso de las 21:00 con EE. UU., que el propietario pidió comprobar.** A las
21:00 BST (20:00 UTC) Nueva York cierra **en ese mismo instante**, así que su
sesión de hoy todavía no es exigible y no puede vetar; con la liquidación de 20
minutos, pasa a serlo a las 20:20 UTC. En horario de invierno ocurre lo mismo
desplazado. Fijado en
`tests/test_sessions.py::test_la_sesion_estadounidense_de_hoy_es_exigible_pasado_su_cierre`.

### D-37 — 2026-09-18 — OD-10 cerrada: una barra abierta se ignora, no veta
Decisión del propietario. Una barra parcial o en curso **no es un dato
retrasado**: es un dato que todavía no existe. Se ignora para indicadores,
puntuación, señales y backtest, y **no genera veto**.

Regla, genérica para cualquier calendario y sin excepción para cripto:

- falta una barra que ya debería estar cerrada → dato retrasado y **veto**;
- existe una barra todavía abierta → **se recorta** y no veta.

Lo que hacía falta para que fuera genérica: una plaza 24/7 no tiene hora de
cierre, pero **sus barras diarias sí cierran**. La del día D queda cerrada a las
00:00 UTC del día siguiente. Con eso, cripto se trata exactamente igual que
XETRA; lo único que cambia entre plazas es a qué hora cierra cada sesión.

**Por qué importaba.** `trim_unclosed_bar` devolvía «sin sesión de cierre» para
cripto y dejaba la barra en curso dentro de la serie, así que los indicadores se
calculaban con una vela a medias; y `may_be_partial_current_session` la marcaba
`PARTIAL_BAR`, que quita `execution_readiness`. El resultado es que **cripto no
era recomendable nunca**: no existe ningún instante en que su barra del día esté
cerrada y siga siendo la última. Medido hoy: los tres pasan de la lista de
«barra potencialmente parcial» a evaluarse por su nota.

**Qué queda igual.** Si no se puede determinar la frontera —plaza sin calendario
declarado— no se recorta y no se supone que el dato está al día: se declara
desconocido (INV-16). El veto residual por `PARTIAL_BAR` sobrevive solo para ese
caso, y hoy no alcanza a ningún analizable.

### D-38 — 2026-09-20 — OD-03 cerrada: 10 €/mes, con caché y solo sobre candidatos

Decisión del propietario. El presupuesto de LLM para contexto se fija **en euros
y no en llamadas**: **máximo 10 €/mes al principio**, con **caché** y con las
llamadas restringidas al **contexto de los candidatos que ya han pasado los
filtros cuantitativos**. Queda excluido explícitamente pasar el LLM por el
universo entero.

**Por qué en euros.** La recomendación técnica anterior proponía un tope de 50
llamadas/día, que no acota el gasto: el coste depende del tamaño del prompt y
del modelo, y una llamada con el contexto entero de un activo no vale lo mismo
que una de relevancia. Un tope en euros es el que el propietario puede vigilar.

**Qué ya se cumple y qué no.** La narrativa de producción **ya** llama solo a
las oportunidades `OPERAR` del top 5 (`advisor/main.py`, `max_opportunities: 5`
en `config.yaml`), así que la parte de «no indiscriminadamente» está hecha desde
antes de esta decisión. **No existen** hoy ni la caché ni la contabilidad del
gasto: nada mide cuánto se lleva gastado en el mes ni corta al llegar al tope.
Eso es trabajo nuevo, y es lo que esta decisión encarga.

**La decisión se reduce a dos reglas operativas**, y una tercera que ya regía:

1. **Tope de gasto: 10 €/mes** al principio, contado en euros y no en llamadas.
   Hace falta un **contador de gasto mensual persistido** y una degradación
   limpia al llegar al tope: sin contexto y declarado, nunca un contexto
   inventado ni un silencio que parezca ausencia de noticias. El tope cubre
   también la narrativa del informe, que ya existe y gasta.
2. **Caché: 24 horas por activo.** El contexto LLM de un activo se reutiliza
   durante 24 h **salvo que cambie materialmente la entrada con la que se
   generó**. La clave es el `input_hash` que C-05 ya exige persistir: si el hash
   cambia, la caché no vale aunque no hayan pasado las 24 h; si no cambia, no se
   vuelve a pagar dentro de la ventana. Queda por definir, al implementarlo, qué
   entra en ese hash —conjunto de noticias, fundamentales, precio de
   referencia—, que es lo que decide qué significa «materialmente».
3. **Selección: ya está como debe estar** y no cambia. El LLM se pide solo para
   las **5 mejores señales de `OPERAR`** (`max_opportunities: 5`), nunca para el
   universo. Se escribe aquí para que quede fijado como regla, no como detalle
   de configuración que alguien pueda subir sin darse cuenta.

**Y el filtro previo sigue siendo por reglas, no por LLM**: símbolo o emisor,
deduplicación por `content_hash` y fuente, antes de gastar una llamada.

**Lo que esta decisión no dice.** No fija el modelo ni el número de llamadas: si
10 €/mes dan de sí o no, se mide cuando B-02 tenga volumen real de noticias, y
entonces se revisa el número, no la regla.

### D-39 — 2026-09-20 — OD-01: se prueba EODHD en su plan gratuito antes de pagar

Decisión del propietario. No se contrata todavía ningún proveedor de
fundamentales: primero se usa el **plan gratuito de EODHD** para una sola cosa,
**probar la integración antes de pagar**. Crear la cuenta gratuita, obtener la
API key y comprobar con **uno o dos valores europeos** si el JSON trae
exactamente los campos que hacen falta: `filing_date`, estados financieros,
ISIN, EPS, deuda y flujo de caja libre.

**Qué decide esta prueba y qué no.** No decide OD-01, la deja medida: dice si el
proveedor sirve, y solo entonces tiene sentido discutir el precio. Lo que
responde es la pregunta que ninguna página de marketing contesta: si el JSON
real, para un valor europeo concreto, trae fecha de publicación por línea y no
solo el periodo fiscal.

**El campo que manda es `filing_date`.** Sin fecha de publicación por magnitud
no hay point-in-time, y sin point-in-time los fundamentales **no pueden entrar
en un backtest** (principio del roadmap, GATE B0). Un proveedor que dé el resto
impecable y no dé `filing_date` cae en la alternativa (b) de OD-01: solo
producción, con etiqueta, y P8 imposible. Por eso la prueba se declara **contra
el dato crudo**, guardando el JSON tal cual, no contra el resumen de la
documentación.

**Qué hace falta que no se puede hacer aquí.** La cuenta y la API key son
trabajo del propietario: alta con su correo y aceptación de condiciones. La
clave va en `.env`, nunca en el repositorio ni en la evidencia; el sondeo se
guarda con la clave recortada.

**Ejecutado el mismo día. Dos respuestas, y no dicen lo mismo**
(`evidence/2026-09-20-OD-01-eodhd-free/`):

1. **El plan gratuito no sirve para fundamentales**, ni europeos ni de EE. UU.:
   `HTTP 403 — Only EOD data allowed for free users` en los tres símbolos. Que
   el EOD de `SAP.XETRA` sí responda con la misma clave es lo que convierte eso
   en una conclusión sobre **el plan** y no sobre el proveedor ni sobre la plaza.
2. **El esquema sí es point-in-time**, visto sobre el JSON real que sirve el
   token público `demo` para `AAPL.US`: **`filing_date` aparece 594 veces, una
   por línea de cada estado financiero**, separada del cierre del periodo
   (`2026-06-30` cierra, `2026-07-31` publica). Están también ISIN, los tres
   estados con 164 periodos trimestrales, EPS fechado en `Earnings.History` con
   `reportDate`, y flujo de caja libre. **No hay `totalDebt`**: hay `netDebt`,
   `shortTermDebt` y `longTermDebt`, y la deuda total se deriva en Python, que
   es lo que el roadmap ya exige para los ratios.

**Consecuencia para OD-01.** La objeción de forma desaparece: EODHD **puede**
dar point-in-time, cosa que `yfinance` no. Lo que el sondeo **no** demuestra, y
no se va a suponer, es que `filing_date` venga **relleno para un europeo**: todo
lo comprobado es `AAPL.US`, porque `demo` devuelve 403 para `SAP.XETRA`. Cerrar
OD-01 pide un mes del plan de pago más barato con fundamentales, dos o tres
europeos del universo, y mirar tres cosas: `filing_date` relleno en los tres
estados, porcentaje de campos nulos, y qué ocurre con una magnitud revisada. Eso
es gasto y lo decide el propietario.

**Cuándo se decide ese gasto: después de T-012** (propietario, 2026-09-20). No
se amplía el plan de EODHD hasta tener la cifra de retraso europeo, y el motivo
no es solo el orden: **el mismo pago puede estar respondiendo a dos preguntas
distintas**. OD-02 pregunta si hace falta una segunda fuente para las plazas
europeas, y el sondeo de hoy ya midió, de paso, que **el EOD europeo de EODHD sí
funciona incluso en el plan gratuito** (`SAP.XETRA`, HTTP 200). Si T-012
demuestra retraso o huecos recurrentes, un solo plan de pago podría cubrir a la
vez la segunda fuente de precios (OD-02) y los fundamentales point-in-time
(OD-01); si no lo demuestra, el único motivo para pagar es P8 y la decisión es
más pequeña. **Hay que comprobar en su catálogo que un mismo plan cubra los dos
usos antes de contarlos como uno**, y la comparación de precio se hace entonces
contra ese plan, no contra el más barato con fundamentales.

**Consecuencia operativa:** OD-01 y OD-02 dejan de decidirse por separado y
pasan a evaluarse juntas cuando T-012 publique el retraso por plaza y por
símbolo.

**Límite del plan gratuito, a comprobar en la propia prueba.** EODHD limita las
llamadas diarias y restringe parte del catálogo según el plan: si un campo falta,
hay que distinguir **«el proveedor no lo da»** de **«este plan no lo da»**, que
son dos conclusiones distintas y llevan a decisiones opuestas. La evidencia debe
decir cuál de las dos es.

**No se integra nada todavía.** El sondeo no toca `advisor/`: B-00 exige la
ficha de proveedor antes de que ninguna fuente externa entre en el sistema, y
esta prueba es precisamente el material con el que se escribe esa ficha.

### D-40 — 2026-09-20 — OD-02 cerrada: segunda fuente solo para Europa, y como respaldo

Decisión del propietario, tomada sobre las cifras de T-012.

**Primero, la definición que faltaba.** El pre-registro fijó el umbral pero no
qué es una «sesión perdida», y de eso dependía la respuesta. Queda definida así:

> **Sesión perdida (OD-02)** = sesión **ya cerrada y exigible** que no está
> disponible cuando una pasada de producción necesita evaluarla, **aunque el dato
> llegue después**. Cada par activo–sesión cuenta **una sola vez**.

Incluye `MISSING_RECENT_DATA` y los retrasos que provocan `STALE_DATA`. Excluye
sesiones abiertas, barras parciales, cierres reales de plaza y los duplicados
entre pasadas. Es la lectura (c) de T-012.

**Por qué esa y no la (a).** OD-02 no mide la integridad del archivo histórico,
mide si el proveedor impide decidir cuando toca. Si la barra llega a las 20:00
pero a las 07:00, 08:30 y 14:30 el activo queda vetado, esa oportunidad ya se
perdió. La lectura (a) —«si acabó llegando no cuenta»— responde a otra pregunta.

**Con esa definición: 47 activos superan las 2 sesiones perdidas por mes, frente
al umbral pre-registrado de 10. OD-02 se activa: sí hace falta segunda fuente.**

**Con dos límites que son parte de la decisión:**

1. **Solo para Europa, y como respaldo.** T-012 midió 278/329 mediciones
   europeas retrasadas a las 06 UTC frente a **0/399** fuera de Europa, y 0 a las
   20 UTC. No hay ninguna evidencia que justifique pagar una segunda fuente para
   EE. UU. ni Asia.
2. **Los 47 no son una tasa fiable todavía.** La ventana cruza 14 versiones de
   código. Sirven para cruzar el umbral y decidir arquitectura; la magnitud
   estable habrá que volver a medirla con la regla vigente.

La primera pasada de producción con `v0.3.0` apunta igual: 25 vetados, todos
europeos, así que la conclusión no depende solo del histórico mezclado.

**El efecto fin de semana, descartado antes de cerrar.** El propietario pidió
separar laborables de fin de semana a las 06 UTC antes de decidir. Medido: **no
hay ninguna pasada de fin de semana a las 06 UTC**. Las siete son jueves,
viernes, lunes, martes, miércoles, jueves y viernes. El desglose por día:

| Día | 06 UTC | 07 UTC | 13 UTC | 20 UTC |
|---|---|---|---|---|
| lunes | 0/47 | 0/47 | 0/47 | 0/47 |
| martes | 47/47 | 47/47 | 18/47 | 0/47 |
| miércoles | 47/47 | 46/46 | 18/47 | 0/94 |
| jueves | 92/94 | 92/94 | 36/94 | 0/94 |
| viernes | 92/94 | 92/94 | 63/92 | 0/45 |

**El lunes no es una excepción, es la confirmación del mecanismo:** ese día la
sesión exigible es la del viernes, cuya barra ya estaba consolidada. La única
pasada de domingo del histórico es la de hoy, a las 16 UTC, y no entra en esas
cifras.

**Y el mecanismo, verificado sobre el dato crudo, es peor que un retraso: la
barra aparece y desaparece.** Siguiendo `SAP.DE` pasada a pasada: el 2026-09-14
a las 20:02 la última barra es la del 14; a las 06:02 del 15 vuelve a ser la del
11; a las 13:32 del 15 reaparece la del 14. El patrón se repite todos los días:
por la mañana el activo está **dos sesiones atrás**, al mediodía una, y por la
tarde al día. No es solo que el proveedor publique tarde: **retira una barra que
ya había servido**.

**Consecuencia que hay que evaluar al diseñar la solución, y que esta decisión
no cierra:** el bot **ya vio** esa barra la tarde anterior. Una caché local de
barras consolidadas resolvería las pasadas de la mañana sin proveedor nuevo, y es
más barata que una suscripción. No sustituye a la segunda fuente para un hueco
real —cuando la barra no existe en ninguna parte—, pero cubre el caso que domina
estas cifras. Se decide al escribir la ficha, con las dos opciones sobre la mesa.

**Aviso estadístico que acompaña a cualquier cita de estos porcentajes:** cada
celda de 47 mediciones europeas sale de **una sola pasada**, así que son 47
activos afectados por un mismo evento del proveedor, no 47 observaciones
independientes. La muestra efectiva son las 7 pasadas de mañana, no las 329
mediciones, y los intervalos publicados son por tanto demasiado estrechos.

**Qué se desbloquea:** escribir la ficha de la segunda fuente europea, que entra
por B-00 como cualquier proveedor externo (ficha de proveedor obligatoria antes
de integrar nada). Y, junto con D-39, evaluar si un mismo plan de EODHD cubre
los dos usos: fundamentales point-in-time (OD-01) y EOD europeo de respaldo
(OD-02). El sondeo de hoy ya midió que su EOD europeo responde incluso en el
plan gratuito.

### D-41 — 2026-09-20 — C-09: la caché va primero; la segunda fuente queda condicionada

Decisión del propietario, tomada sobre el mecanismo que destapó D-40.

**El razonamiento, que es el que manda:** el fallo dominante no es «el proveedor
nunca entregó la barra», sino **«la entregó, el bot la vio, y después dejó de
devolverla temporalmente»**. Pagar otra fuente para reconstruir algo que ya
tuvimos sería innecesario. Así que C-09 se implementa como **caché local
primero**, y la segunda fuente pasa a ser **respaldo condicionado** a una cifra
que hoy no existe.

**Las cinco reglas de la caché**, que la ficha T-018 no puede reinterpretar:

1. Una barra de sesión cerrada y **ya validada** se persiste localmente y **no
   desaparece porque el proveedor deje de devolverla**.
2. La caché **nunca crea** una barra que el bot no haya observado.
3. Si una sesión nueva **todavía no se ha recibido nunca** cuando resulta
   exigible, sigue siendo `MISSING_RECENT_DATA`. **Ahí sí** puede entrar una
   segunda fuente.
4. Si el proveedor devuelve después una versión distinta de una barra ya
   guardada, **no se sobrescribe en silencio**: se registra como revisión,
   conservando valor anterior, valor nuevo, instante y proveedor.
5. Producción puede usar la barra local validada cuando la API «retrocede», pero
   **debe dejar trazabilidad** de que la fuente viva no la estaba sirviendo en
   esa pasada.

**Lo que esto arregla además, y no es menor:** hoy **el histórico del bot cambia
retrospectivamente** según lo que `yfinance` decida devolver esa mañana. Con la
caché, una medición de investigación repetida en otro momento deja de depender
de eso.

**El criterio para decidir después si además se compra EODHD como segunda fuente
de precios**, fijado antes de medir: una vez implantada la caché, contar durante
varias semanas cuántas veces ocurre

> sesión exigible **+** nunca observada previamente **+** el proveedor principal
> no la entrega.

Esa es la cifra que mide el **valor marginal** de una segunda fuente. **Si sale
cercana a cero, EODHD se queda solo para fundamentales** (OD-01). Si sigue siendo
material, se justifica también pagar precios europeos. Queda como **OD-02 bis**,
abierta.

**Y una corrección de método que el propietario impone sobre las cifras de
T-012:** las 329 mediciones europeas de una franja **no son 329 experimentos
independientes**. En términos del comportamiento del proveedor hay unos **7
eventos matinales**, cada uno afectando a la vez a decenas de símbolos. Los
intervalos binomiales por activo **no se usan para afirmar una precisión que no
tenemos**. El resumen se corrige para publicar el número de pasadas de cada celda
y marcar el intervalo como no independiente.
