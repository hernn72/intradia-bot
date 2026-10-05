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

### D-42 — 2026-09-21 — El laboratorio rehecho (A-02): con el estimador pre-registrado, ninguna banda es concluyente
T-013 rehace P2.3, P2.4 y P2.5 una sola vez sobre `071ddb2b…`, con la fortaleza
relativa alineada y el estimador pre-registrado de INV-14 al frente. Evidencia
en `evidence/2026-09-21-T-013-laboratorio-rehecho/`.

**El control de la ficha pasa exacto.** La población `pre-d31` (107 activos)
devuelve **121.786 señales**, la cifra publicada en agosto. Sobre la misma
población el total no cambia, así que ni la corrección de fortaleza relativa ni
la geometría de la línea 0 crean o destruyen señales.

**Lo que NO se puede afirmar, y una primera redacción de esta decisión afirmaba
por error.** Se publicó que «solo 194 señales (0,16 %) cambian de banda» y que
«toda la diferencia es de población». **Las dos frases se retiran.** El 194 era
la suma de las diferencias **netas** por banda, que no cuenta migraciones: si N
señales entran en una banda y N salen, el neto es 0 y el movimiento real es 2N.
El mínimo compatible con esos agregados es **97** y el máximo, acotado por las
**10.228** señales de los **diez** pares que cruzan continente en `pre-d31`
(`docs/pendientes.md` §16). De agosto solo se conservan los agregados por banda,
no la salida por señal, así que **la atribución exacta entre población y
corrección de RS no es observable con los artefactos disponibles, y se declara
que no se puede separar** —la ficha lo contempla—. Queda FOLLOW_UP: rehacer
`pre-d31` con la corrección de zona revertida y emparejar por `signal_id`.

No confundir dos universos: los pares que cruzan continente son **diez** en
`pre-d31`, que es donde se compara con agosto; **ocho** sobreviven en la
población vigente de 93, porque `DFEN.DE` y `4GLD.DE` cayeron con D-35.

**Lo que cambia el veredicto, y es el hallazgo de la tarea.** Con la tasa
TARGET_FIRST —el estimador **secundario**— la capacidad global salía `LIMITADA`
con resolución `MEDIUM`. Con el primario que INV-14 declara desde el 2026-09-02
—media por bloque de la expectancy neta en R— sale **`INSUFICIENTE` con
resolución `LOW`**: el intervalo mide 0,231 R frente al umbral de 0,200.
**Ninguna de las cinco bandas es concluyente**, y el IC95 del primario cruza el
cero en todas menos en `<50`, que es la banda más baja del score.

El instrumento existía desde el 2026-09-02, pero solo publicaba **un número
global sin intervalo**; el intervalo que se venía leyendo por banda era el de la
métrica secundaria. Esta tarea construye el primario por banda, por región y por
activo, que es lo que GATE P2 punto 4 exigía.

**De dónde salen 21 y 5 bloques.** No del diseño del bot: de la ventana. El
protocolo pre-registró la capacidad sobre «Histórico útil: 2.430 sesiones» (40
bloques en swing, 8 en medio), y la cosecha congelada que GATE P2 usa tiene
`requested_range: "5y"` — rango efectivo 2021-08-30 → 2026-08-28, unas **1.302
sesiones**, que dan 1302/60 ≈ 21 bloques en swing y 1302/300 ≈ 5 en medio.
**La cosecha congelada que usa GATE P2 tiene aproximadamente la mitad de la
ventana de 2.430 sesiones que el protocolo describía al pre-registrar la
capacidad.** No se amplía la ventana ni se rehace la cosecha —T-013 lo prohíbe—
y la discrepancia queda como FOLLOW_UP.

**MEDIO queda invalidado, no solo con poca resolución (corregido el 2026-09-21
tras la revisión del PR).** El resto de 102 sesiones es un bloque **ocupado** que
no supera `MAX_HOLD_BARS` = 250, así que no puede contener una operación
completa, y P2.5 declara inválida por definición una ventana más corta que
`MAX_HOLD_BARS`. El horizonte se publica como **`INSUFFICIENT` / no concluyente**
con el motivo `bloque temporal parcial 102 sesiones <= MAX_HOLD_BARS 250`. Sus
números se conservan por trazabilidad y quedan marcados **no utilizables para
calibración ni conclusión**. **Swing no está afectado**: su último bloque mide 42
y supera los 40, y su salida es idéntica byte a byte. La guarda vive en
`_classify_capacity`, acumula su motivo con los demás e impide alcanzar `HIGH` o
`MEDIUM` aunque el intervalo salga estrecho. Compara con **`<=`**, igual que la
validación nominal de `_protocol_block_length`: P2.5 exige que el bloque
**supere** `MAX_HOLD_BARS`, así que un bloque real de exactamente 250 sesiones
tampoco vale.

**No se adopta nada y no se ajusta nada.** No se toca `config.yaml`, ni los
pesos, ni la geometría, ni los umbrales. Un resultado NO CONCLUYENTE es el
resultado, y se publica con su resolución, su muestra, su número de bloques y su
intervalo.

**Defecto corregido de paso (SAME_SCOPE).** La tabla de la ablación sustituía el
intervalo, la media y el número de bloques por la palabra «NO CONCLUYENTE».
Mientras casi todo salía concluyente bajo la tasa no se notaba; con el primario
la tabla se quedaba **sin un solo número**, lo que incumple `docs/metodo-trabajo.md`
sección 3. Ahora el veredicto va en su columna y las cifras se publican siempre.

**GATE P2 NO queda cruzado todavía.** Seis de sus siete requisitos están
cumplidos; falta el **6**, la decisión formal sobre el RR, que es del propietario
y queda abierta como **OD-11** con los números nuevos. El gate se cruzará cuando
OD-11 se responda.

### D-43 — 2026-09-21 — OD-11 cerrada: el RR sale del score como dimensión, y GATE P2 queda cruzado
Decisión del propietario, sobre P2.4 rehecho y revisado (D-42).

**Qué se decide.** El ratio beneficio/riesgo **deja de ser una dimensión de
puntuación de `compute_score`**, a partir de P3.

**El alcance de la conclusión, que no se puede ensanchar.** Lo medido es que
**el RR no sirve como dimensión de ordenación del score actual**, tal y como
P2.4 lo midió. **No** se ha concluido, ni se sigue de aquí, que «el RR no
sirve» en general: **sigue siendo una condición de ejecutabilidad y de riesgo**,
y en esa función no se toca nada.

**En qué se apoya.** Sobre la población vigente de 93 activos, cosecha
`071ddb2b…`, swing, 106.363 señales sin pasar por `classify()`:
- la dimensión reparte ~10 de sus 20 puntos a **casi todo el universo** (p10 =
  p90 = 10,000 en cuatro de las cinco bandas);
- el RR **bruto** tiene mediana **1,500 en las cinco bandas**;
- no muestra capacidad discriminante útil entre bandas;
- buena parte del cambio de nota al retirarlo es **normalización matemática**,
  no información añadida: la contribución vale `−0,4167·T + 16,667`, función
  solo de la nota total;
- al retirarlo migran muchas señales (`70-80` pasa de 2.194 a 6.443 y `80+` de
  65 a 1.032), así que **los umbrales actuales no se pueden reutilizar**.

**Lo que NO cambia, y se mantiene intacto:**
- `min_rr` y `entry_max_rr`;
- la invariante de que **nunca** se recomiende una entrada que viole el RR
  mínimo;
- `RR_TOO_LOW` como guarda correspondiente (sigue siendo la guarda de P4 que
  D-29 decidió conservar);
- la geometría de stop, objetivos y entrada, que es P4;
- `min_score_operar` y `min_score_vigilar`, que no se tocan ahora.

**Lo que P3 (A-03) tendrá que hacer:**
1. `score_model_version` **nuevo**;
2. redefinir el score **sin** la dimensión RR;
3. recalibrar los umbrales **por horizonte** con el estimador primario de
   INV-14;
4. **no asumir ninguna equivalencia** entre las bandas del score viejo y las
   del nuevo.

**Aviso que viaja con la decisión.** D-42 dejó medido que, con el estimador
primario, **ninguna banda es concluyente**. Esta decisión **no** se apoya en que
una banda rinda más que otra —eso no está medido con resolución suficiente—,
sino en que la dimensión es **casi constante**, que es un hecho descriptivo
independiente de la resolución.

**GATE P2 queda CRUZADO el 2026-09-21.** Era el séptimo y último requisito: la
decisión formal sobre el RR, salida de P2.4, en el decision log. Con ella,
**T-013 / A-02 pasa a ACEPTADA** y **A-03 (P3) queda desbloqueada**.

### D-44 — 2026-09-25 — Regla 4 de la caché resuelta, y el reajuste de la serie se distingue de la revisión
Decisión del propietario, tomada al implementar T-018. D-41 dejó la regla 4 con
una pregunta abierta a propósito —una barra revisada no se sobrescribe en
silencio, pero no estaba dicho **cuál se usa**— y la ficha prohibía que la
respondiera el implementador.

**Qué se decide (primera pregunta).** Manda la **primera barra validada**. Una
revisión posterior del proveedor queda registrada con valor anterior, valor
nuevo, instante y proveedor, y **no cambia el número que alimenta el análisis**.
El motivo es el efecto secundario que justificaba la tarea: que el histórico del
bot deje de moverse según lo que el proveedor decida devolver esa mañana.

**Hecho técnico que apareció al implementar, y que la pregunta no contemplaba.**
`MarketDataProvider.get_history` usa yfinance con `auto_adjust=True`
(verificado en yfinance 1.7.0), así que **cada ex-dividendo reescribe
legítimamente todas las barras anteriores por un factor común**. Con la regla
literal, la caché habría conservado la base vieja en las barras recientes
mientras el resto de la serie se reajustaba: **dos bases de ajuste en la misma
serie**, con un escalón artificial de en torno al 1 % justo en el borde de la
ventana, que ATR y las medias se comen sin avisar.

**Qué se decide (segunda pregunta).** Se distingue lo que sí es distinguible:
- si **todas** las barras solapadas cambian por un **mismo factor**, es un
  **REAJUSTE** de la serie (dividendo o split) y la caché **adopta la base
  nueva**, reanclándose con lo que el proveedor sirve ahora;
- si **una barra se mueve sola**, es una **REVISION** de esa sesión y sigue
  mandando la primera validada.

Una sola base de ajuste por serie, siempre. Con **una sola** barra solapada no
se puede distinguir un caso del otro, así que no se afirma que sea un reajuste:
se trata como revisión, que es la lectura conservadora.

**Coste declarado del reanclaje, que no se esconde.** Al reanclar se descartan
las barras guardadas en la base vieja, así que **una barra retirada el mismo día
del reajuste se pierde**. No se escala por el factor detectado porque eso
produciría un valor que el bot nunca observó, contra la regla 2 de D-41. La
pasada lo declara en la medición en vez de perderlo en silencio.

### D-45 — 2026-09-26 — GATE P3 requisito 2: medio queda sin calibrar mientras su evidencia sea inválida, y ningún umbral v1 se hereda
Decisión del propietario sobre la propuesta A de T-019.

**Contradicción que resuelve.** GATE P3 exigía calibrar swing y medio por
separado. A-02 (D-42) invalidó medio para calibración y conclusión: su último
bloque ocupado mide 102 sesiones y `MAX_HOLD_BARS` vale 250. Calibrar medio con
esos números contradice P2.5, y conseguir datos válidos exige una cosecha más
larga, que es FU-1 de A-02 y no cabe en A-03.

**Qué se decide:**
1. **Swing** puede calibrarse en P3 con la regla pre-registrada en T-019. Si la
   regla no se cumple, queda `calibrated: false`.
2. **Medio** queda `calibrated: false` sin intentar calibración. P3 publica sus
   números solo por trazabilidad, marcados inválidos.
3. **Intradía** queda `calibrated: false` (no tiene laboratorio: P2 solo cubre
   swing y medio).
4. **No se heredan los umbrales 70/60 de Score v1** en ningún horizonte de
   Score v2, ni por equivalencia de escala ni por equivalencia de percentil.
5. Un horizonte `calibrated: false` **no puede presentarse** como score
   operativamente calibrado en ningún informe, mensaje ni persistencia.
6. Si la ordenación de P3 sale NO CONCLUYENTE, GATE P3 se cruza con esa
   etiqueta, como ya decía `docs/gates.md`, y P4 trabaja sobre `score_signal`
   sin umbrales operativos nuevos.

Reabrir la calibración de medio exige una cosecha nueva cuyo último bloque
ocupado supere `MAX_HOLD_BARS`, con `data_vintage_id` nuevo, y una ficha nueva.
**Se corrige en el mismo commit el requisito 2 de GATE P3** en `docs/gates.md`.

**Precisión de la tercera revisión del PR #26 (2026-09-26, antes de fusionar).**
Para que el requisito no tenga escapatorias: swing queda `calibrated: true`
**solo** si la regla pre-registrada produce umbrales válidos, y
`calibrated: false` **también satisface el requisito** cuando la regla no produce
ninguno, siempre que se publiquen el resultado y el motivo. Para Score v2, el
contrato implementado **impide** `calibrated: true` en medio e intradía: cada
`score_model_version` declara en el código qué horizontes puede calibrar (`"2.0"`
→ solo swing; `"1.0"` → ninguno), así que la restricción es parte de la
especificación de la versión y no una revisión humana del YAML (T-019, regla 8
del contrato).

### D-46 — 2026-09-26 — `convicción` sale de Score v2; su contenido de calidad del dato pasa a la confianza, y el ATR% no se conserva escondido
Decisión del propietario sobre la propuesta B de T-019. Se toma por
arquitectura y **antes** de ver P3.

**Por qué.** La dimensión `convicción` (10 puntos) mide cobertura de barras (4),
indicadores disponibles (4) y «estabilidad» por ATR% (2). Los dos primeros son
calidad del dato, que por arquitectura no puntúa (INV-03). El tercero es una
propiedad del activo que nunca se pre-registró como predictor. Ningún documento
normativo fija seis dimensiones.

**Qué se decide:**
1. Score v2 **no** contiene `convicción`.
2. Cobertura de barras e indicadores disponibles siguen existiendo como
   **confianza del análisis** (`Opportunity.confianza`), calculada desde el
   snapshot, **fuera** de `compute_score`, y **no** se convierten en puntos.
3. El ATR% **no** se conserva dentro de ninguna otra dimensión ni de la
   confianza. Estudiar la volatilidad como predictor exige una señal o dimensión
   explícita, pre-registrada y medida por separado.
4. Los 30 puntos retirados (RR 20 + convicción 10) **no se redistribuyen**. Score
   v2 = catalizador 20 + técnico 20 + contexto 10 (fundamental 20 cuando exista,
   que sería otro modelo), normalizado sobre los puntos evaluables: **50**
   habituales.
5. La ablación de P3 **no** reabre esta decisión.
6. **Invariante de composición** (añadida en la tercera revisión del PR #26,
   antes de fusionar): las dimensiones puntuables son **propiedad del
   `score_model_version`**, no de un flag que pueda modificar su composición.
   Con `"1.0"` o `"2.0"`, `fundamentals_enabled: true` es configuración
   inválida; activar fundamentales exige una versión nueva del modelo (T-019,
   regla 9 del contrato). No se crea ahora ninguna versión `"3.0"`.

### D-47 — 2026-09-26 — Transición: producción sigue en Score v1 con sus 70/60 legacy hasta que v2 entre de forma atómica
Decisión del propietario sobre la propuesta C de T-019 (alternativa **C2**).
**Es un estado de transición**, no el destino.

**Pregunta.** Si P3 sale NO CONCLUYENTE y swing queda `calibrated: false`, ¿qué
modelo y qué umbrales usa producción?

**Qué se decide:**
1. Producción sigue en **`score_model_version = "1.0"`**: calcula Score v1 y
   clasifica con sus **cortes legacy 70/60**.
2. Esos 70/60 son de v1 y se declaran `calibrated: false` en todos los
   horizontes desde el primer commit de código (paso 1 de T-019), porque A-02
   midió que ninguna banda v1 es concluyente. **No se presentan nunca como
   calibración de Score v2**, ni en el informe, ni en Telegram, ni en el texto
   al LLM, ni en la persistencia.
3. El RR **sigue puntuando en producción únicamente porque todavía corre v1**.
   No es una excepción a D-43: en cuanto producción pase a v2, el RR deja de
   puntuar.
4. El cambio a v2 en producción es **atómico**: en un mismo commit entran la
   versión nueva (`"2.0"`), el contrato de umbrales con bloques que declaran
   `"2.0"` y un estado de calibración coherente con la evidencia de P3.
5. **No puede existir ninguna pasada de producción que calcule Score v2 y
   clasifique con los 70/60 de v1.** Comparar la etiqueta de versión de los
   umbrales con la del modelo activo **no basta** (se podrían reescribir 70/60
   en un bloque que declare `"2.0"`). Lo impide la **regla 7** del contrato de
   T-019, que el cargador aplica al arrancar: los 70/60 legacy con
   `calibrated: false` solo se admiten con `"1.0"`; en cualquier otra versión,
   `calibrated: false` obliga a umbrales y `calibration_ref` nulos, y
   `calibrated: true` exige umbrales numéricos y una referencia de calibración
   válida.
6. **Trazabilidad en persistencia.** Cada pasada guarda junto a su manifiesto el
   contrato de scoring canónico realmente usado
   (`analysis_run.scoring_contract_json`: versión, `fundamentals_enabled`,
   umbrales, `calibrated` y `calibration_ref` por horizonte); las
   recomendaciones lo alcanzan por `run_id`, y las revisiones de posición también,
   porque `seguimiento` crea manifiesto y `position_review.run_id` entra en la
   migración v7. `config_hash` solo no basta: permite comprobar una
   configuración, no recuperarla. Las filas anteriores a v7 quedan con el
   contrato **no recuperable**, salvo evidencia externa verificable; nunca se
   rellenan con `"1.0"`.

Score v2 vive mientras tanto en el código y en investigación, con la misma
función versionada (INV-06 se cumple en el código, no en la versión activa).

**Alternativas descartadas.** C1 (v2 activo sin umbrales: el asesor dejaría de
emitir COMPRAR) y C3 (v2 con umbrales provisionales elegidos a mano: un corte
nuevo sin medir).

**Por qué no contradice D-43.** D-43 sacó el RR «a partir de P3»; esta decisión
lo lee como a partir de que v2 tenga umbrales con los que clasificar, que es lo
que ya recomendaba OD-11: «retirarlo debe entrar junto con la recalibración de
P3, no antes, o quedan umbrales heredados sobre una escala que ya no existe».

### D-48 — 2026-09-26 — RETIRADA el mismo día, antes de fusionarse: mezclaba tres cuestiones y la primera no estaba aprobada
La primera versión de esta entrada (commit `6572ecb`, rama
`docs/t019-preregistro-p3`, nunca fusionada en `main`) registraba como una sola
decisión cerrada tres cosas distintas: que el componente asiático dejaba de
puntuar en Score v2, que el revisor independiente decidiría la alineación del
VIX y que el seguimiento construiría el contexto como la pasada diaria. **Se
retira** porque:
- la exclusión del componente asiático **no estaba aprobada**: es una
  modificación interna de la dimensión `contexto`, que en la arquitectura
  aprobada de Score v2 permanece;
- que el revisor **eligiera** la alineación del VIX no es válido
  metodológicamente: una regla elegida al revisar no está pre-registrada;
- el seguimiento de posiciones es un requisito técnico de INV-06, no una
  decisión estadística.

No se borra, conforme a la regla de este registro. Su contenido queda dividido
así:
- **Componente asiático** → pregunta de pre-registro **pendiente** en T-019
  (PR-1), a resolver antes de ejecutar P3 y sin mirar su expectancy.
- **Alineación del VIX** → **D-49**.
- **Contexto del seguimiento** → requisito técnico de T-019 (R-CTX), bajo INV-06.

### D-49 — 2026-09-26 — La regla point-in-time del VIX se fija antes de P3; el revisor la verifica, no la elige
Decisión del propietario. Sustituye la parte del VIX de la D-48 retirada.

**Hallazgo que la motiva (H-1 de T-019).** El laboratorio y el backtest usan el
VIX con una vela de retraso (`event_study.py:309`, `backtest/runner.py:210`,
`shift(1)`), y producción el último VIX cerrado a la hora de la pasada
(`market_context.py:159–170`). Mismo `compute_score`, entradas distintas.

**Qué se decide.** La regla point-in-time de alineación del VIX se fija y
documenta antes de ejecutar P3. El revisor independiente no elige la regla:
verifica que la regla pre-registrada no contiene look-ahead y que producción e
investigación usan exactamente la misma implementación.

**Cómo se fija.** Antes del experimento se inspecciona el camino actual de los
dos lados y se define, por escrito en T-019, qué valor del VIX era realmente
conocido en cada `analysis_timestamp`. Si esa inspección deja **varias reglas
plausibles** y ningún contrato previo decide entre ellas, **se eleva al
propietario antes de ejecutar el laboratorio**; ni el implementador ni el
revisor eligen.

**Completada el 2026-09-29 por D-53**, con la regla concreta.

### D-50 — 2026-09-29 — `analysis_timestamp` de una señal histórica: la última pasada programada antes de la apertura de entrada (T-A)
Decisión del propietario tras la parada OWNER_DECISION_REQUIRED de T-019 2a-doc.

**Hallazgo que la motiva.** Producción genera la señal swing **cuatro veces**
por día laborable (07:00, 08:30, 14:30 y 21:00, hora de Londres), y ningún
contrato decía cuál de esas pasadas representa una señal histórica. Había dos
lecturas plausibles:
- **T-A:** la última pasada anterior a la apertura de entrada.
- **T-B:** la primera pasada posterior a que la barra esté disponible.

Las dos dan un VIX y un dato asiático distintos a la misma señal. Evidencia en
`evidence/2026-09-29-T-019-paso2a-doc-inspeccion/`.

**Qué se decide (T-A).**

> `analysis_timestamp` = la última pasada programada de producción
> estrictamente anterior a la apertura de la sesión de entrada `d+1`, siempre
> que la barra de señal `d` ya estuviera cerrada y disponible después de
> `settlement_minutes`.

Finalidad: reproducir el último estado real que el bot podía observar antes de
la apertura que el laboratorio usa como entrada.

**Cómo se resuelve**, derivado del contrato existente:
- Calendario y zona de la plaza (`exchange_calendars` +
  `exchange_overrides.yaml`), con DST histórico, festivos y cierres especiales.
- `settlement_minutes` = 20.
- Pasadas programadas: las del **único horario registrado**,
  `deploy/systemd/intradia-bot.timer` (commit `1f31d2d`), lunes a viernes en
  hora Europe/London.
- La pasada por evento de las 22:30 no cuenta: es condicional y no se puede
  reconstruir.

La fórmula y la tabla por plaza están en T-019, sección «Contexto: paridad y
point-in-time».

### D-51 — 2026-09-29 — Cripto fuera de la población de P3: enmienda del pre-registro condicionado
Decisión del propietario.

**Hallazgo.** En las plazas 24/7, el cierre de la barra diaria `d` (00:00 UTC)
coincide con la apertura de `d+1`. No existe ninguna pasada real entre los dos
instantes, así que la regla de D-50 no tiene solución, y no se inventa un
`analysis_timestamp` que producción nunca ejecutó.

**Qué se decide.**
- Los activos cripto (`BTC-EUR`, `ETH-EUR` y `SOL-EUR`) quedan **fuera de la
  población confirmatoria de P3 y de su trazabilidad de medio**, mientras se
  mantenga la semántica diaria «señal al cierre → entrada en la apertura
  siguiente».
- **No** salen del universo ni de producción.
- Es una enmienda explícita del pre-registro condicionado (PR #26), anterior
  al SHA de 2a-doc y motivada **solo** por una imposibilidad causal o
  temporal detectada antes de mirar P3. No es una selección por rendimiento.

**Consecuencias recalculadas** sin leer desenlaces:
- De 93 a **90 activos**.
- Señales swing: de 106.363 a 101.251 antes de D-52.
- Señales medio: de 94.273 a 89.551 antes de D-52.
- Comparaciones: de 332/318 a 323/309 por los activos. D-57 las lleva después
  a 329/309.
- Los bloques no cambian, porque la espina ya excluía cripto.

### D-52 — 2026-09-29 — PR-1 respondida: Asia point-in-time con sesiones cerradas, las cinco series y sin imputar
Decisión del propietario (opción 2 de la parada de 2a-doc).

**Hallazgo.** El dato asiático de producción es intradía en las pasadas de la
mañana: `fetch_overview` no recorta la barra abierta. La cosecha solo tiene
cierres diarios, así que PR-1 era el caso B con cualquier
`analysis_timestamp`.

**Qué se decide.**
- **Composición.** Se conservan las cinco series: `^N225`, `^HSI`, `^KS11`,
  `^TWII` y `510300.SS`.
- **Cálculo**, para cada serie y cada `analysis_timestamp`:
  1. con su propio calendario, la última sesión cerrada y con
     `settlement_minutes` superado;
  2. su cierre, y el de la sesión cerrada inmediatamente anterior de esa serie;
  3. la variación porcentual entre los dos.

  `asia_session_change` es la media simple de las cinco variaciones. Nunca se
  usan barras intradía.
- **Un festivo o un cierre de plaza**, aunque dure varios días, **no es un
  dato ausente**.
- **Un hueco del proveedor** es una sesión que el calendario exige y que no
  tiene barra. Ante un hueco no hay forward fill, ni proxy, ni imputación, ni
  cálculo con cuatro series. La observación de P3 es **no calculable por input
  de contexto ausente**: se excluye y se publican su contador y su motivo. La
  composición nunca pasa de cinco a cuatro series.
- **Alcance.** Es la semántica de Score v2, de P3 y de la futura producción
  v2. **Score v1 queda intacto** mientras D-47 lo mantenga activo.

**Aplicación en 2a-doc.**
- Cinco sesiones que `exchange_calendars` da como abiertas fueron cierres
  reales verificados con fuente, **aprobados como festivos por el propietario
  en D-54**: tifón y lluvia negra en XHKG el 2023-09-01 y
  el 2023-09-08; en XTAI, el día sin negociación del 2023-01-18 (calendario
  oficial de la TWSE) y los tifones del 2024-10-31 y el 2026-07-10. Por esta decisión
  son festivos. 2a-code los añade a `exchange_overrides.yaml` antes de P3, y
  la población se congela con ellos.
- Sin fuente quedan tres sesiones, que siguen siendo huecos del proveedor:
  `^KS11` 2022-05-09, `510300.SS` 2025-10-24 y `510300.SS` 2026-08-28.
- Exclusiones: **396 señales swing y 218 de medio**, listadas en
  `06-excluded_asia_missing-*.tsv`.

### D-53 — 2026-09-29 — Regla point-in-time del VIX (completa D-49) y de la tendencia, y una sola función de contexto
Decisión del propietario. Completa D-49 con la regla concreta.

**VIX.**
- Para cada `analysis_timestamp` se usa la última observación diaria de `^VIX`
  cuya sesión `s` esté cerrada y cumpla `available_at(s) <= analysis_timestamp`.
- `available_at(s) = session_close_at("NYSE", s) + settlement_minutes`, con
  el calendario XNYS: zona, DST, festivos de EE. UU. y cierres anticipados.
- Es la misma semántica con la que producción acepta la **barra diaria del
  proveedor** (`trim_unclosed_bar` en `fetch_market_context`).
- No hay `shift(1)` por posición de fila ni alineación por fecha civil.

**Tendencia.**
- El último cierre de `^STOXX50E` disponible en `analysis_timestamp`, con la
  misma regla sobre XETRA.
- La SMA de 200 se calcula solo con observaciones que ya estaban disponibles
  en ese instante.
- Solo cuentan barras cuya fecha de sesión es sesión del calendario de su plaza
  (XNYS o XETR); las demás se ignoran, como `trim_unclosed_bar`.
- **Dato ausente de tendencia en P3:** si la SMA no tiene 200 cierres
  causalmente disponibles, la observación se excluye (**D-55**). Un hueco
  puntual de `^STOXX50E` usa el último cierre causal disponible (**D-56**).

**R-CTX.** Seguimiento, producción v2, backtest y event study llaman a la
**misma función** de contexto point-in-time. Para el mismo `analysis_timestamp`
obtienen el mismo VIX, la misma tendencia y SMA y el mismo dato asiático.

**Contexto de Score v2, congelado.**
- Tendencia 4, VIX 4 y Asia 2: total 10, con los tramos de v1.
- No se redistribuye nada.
- No se añade ninguna señal nueva: ni `^SOX`, ni `^RUT`, ni `^TNX`, ni
  `DX-Y.NYB`, ni `CL=F`, ni `GC=F`.

**Defecto registrado.** `_naive_dates` (`event_study._align`, `runner._align`)
normaliza las fechas en UTC. En la cosecha eso dio:
- en el 78 % de las barras de EE. UU. y el 69 % de las de cripto, una
  tendencia de una sesión posterior a la barra (look-ahead);
- en Europa y Asia, un VIX de dos sesiones atrás.

**A-02 se midió con ese defecto y su evidencia no se modifica**: queda
publicada con esa limitación. P3 usa el camino corregido, que implementa
2a-code.

### D-54 — 2026-09-29 — Cinco cierres extraordinarios son cierres reales de plaza, no huecos del proveedor
Decisión del propietario, antes de P3.

**Qué se decide.** Estas sesiones se tratan como cierres reales o festivos a
efectos de D-52:
- XHKG: 2023-09-01 y 2023-09-08;
- XTAI: 2023-01-18, 2024-10-31 y 2026-07-10.

`exchange_calendars` las da como abiertas y la cosecha no tiene barra en ellas.
Las fuentes están en T-019 y en la evidencia de 2a-doc. **2a-code las
incorpora a `exchange_overrides.yaml`**, con sus fuentes, antes de P3.

### D-55 — 2026-09-29 — Historia insuficiente para la SMA200: la observación se excluye de P3 (`NO_CALCULABLE_CONTEXT_HISTORY`)
Decisión del propietario, antes de P3. **Es una enmienda del pre-registro
condicionado anterior al SHA de 2a-doc**, decidida sin mirar desenlaces.
**Sustituye** la propuesta de 2a-doc de aplicar a esas observaciones la regla v1
de dato ausente (2 de 4).

**Qué se decide.** Si la cosecha no permite reconstruir causalmente, en
`analysis_timestamp`, los 200 cierres de `^STOXX50E` que necesita la SMA, la
observación **se excluye de P3**, con el código conceptual
`NO_CALCULABLE_CONTEXT_HISTORY`, y se publican su contador y su listado.

**Motivo.** No es un dato que producción desconociera: es un límite de
profundidad histórica de la cosecha. No se neutraliza.

**Consecuencias medidas por el censo 06, sin leer desenlaces:**
- 6.937 señales swing excluidas, 176 de ellas también excluidas por Asia; 0 de
  medio.
- La población de P3 en swing ocupa **19 bloques con señales**, frente a los
  21 de A-02. El bloque 2 de la espina lo vacía esta decisión. El bloque 1 ya
  lo había vaciado D-51, porque solo tenía señales cripto
  (`07-ocupacion-de-bloques.txt`, con el desglose por motivo).

### D-56 — 2026-09-29 — Hueco puntual de `^STOXX50E`: último cierre presente y causalmente disponible, sin excluir
Decisión del propietario, antes de P3. Confirma la lectura de D-53.

**Qué se decide.** Si falta la barra de la sesión exigible de `^STOXX50E`, se
usa el **último cierre presente y causalmente disponible** antes de
`analysis_timestamp`, y la observación **no** se excluye.
- Se declara que ese dato puede ser más antiguo que la sesión exigible.
- Se publica el contador: 1.406 señales swing y 1.312 de medio en la
  población de P3, con una antigüedad de 1, 3 o 4 días naturales.

**Distinción con D-55:**
- un hueco intermedio usa la última observación causal disponible;
- la historia inicial insuficiente para la SMA200 excluye la observación.

### D-57 — 2026-09-29 — Familia Bonferroni de P3: `m = 20` fijo
Decisión del propietario, antes de P3. **Es una enmienda del pre-registro
condicionado anterior al SHA de 2a-doc**, decidida sin mirar desenlaces.
**Sustituye `m = 14`**.

**Qué se decide.** La familia inferencial completa, definida antes de mirar P3,
tiene **20** intervalos:
- **10 de OPERAR:** 5 candidatos × 2 contrastes (el primario de `[c, ∞)` y el
  contraste pareado `[c, ∞) − [0, c)`);
- **10 de VIGILAR:** todos los pares posibles `[v, operar)` entre los cinco
  candidatos, `C(5,2) = 10`.

**Parámetros:**
- `confidence = 1 − 0,05/20`, con 20.000 remuestreos y la semilla `20260830`.
- La capacidad sigue aparte, con el instrumento estándar P2.5: IC95 y 2.000
  remuestreos.
- Si varios percentiles colapsan en el mismo score, la selección opera sobre
  los valores distintos y se informa del colapso, pero **m sigue en 20**.
- La regla mecánica de selección de VIGILAR no cambia.

**Contadores resultantes:**
- swing = 1 confirmatoria + 20 de la familia + 308 descriptivas = **329**;
- medio = **309**, sin familia de umbrales;
- total = **638**.

### D-58 — 2026-09-30 — La migración v7 se despliega sola, como `v0.4.1`, antes de 2a-code
Decisión del propietario, **separada del pre-registro de P3**. Enmienda el «no
despliega nada en la Pi» de la ficha T-019 solo para lo que ya está en `main`
(el paso 1). **No modifica el pre-registro de P3**: `8b2dddb` sigue siendo su
SHA, con las mismas reglas, población, exclusiones y familia (D-50 a D-57).
Desplegar ese SHA en producción no ejecuta ni adelanta nada de P3.

**Qué se decide.** Antes de empezar 2a-code, producción pasa al estado de
`main` = `8b2dddb` (el SHA del pre-registro de P3, sin commits añadidos) con el
tag `v0.4.1`. La Pi migra de v6 a v7 y sigue en **Score v1**, con 70/60 legacy y
`calibrated: false`. No se activa v2, no se implementa 2a-code, no se ejecuta P3
y no se aplican en producción las exclusiones de P3 (D-51, D-52, D-55).

**Por qué.** Aislar y validar la migración v7 en producción antes de introducir
los cambios point-in-time: si algo falla después, no se mezcla un fallo de
esquema con uno de contexto.

**Rollback.** Por D-32, `checkout v0.4.0` no es un rollback válido; hay que
restaurar el backup `pre-v7` (esquema v6) verificado.

**Resultado (2026-09-30):** desplegado, verificado y **aceptado por el
propietario**; sin rollback (`evidence/2026-09-30-despliegue-v041/`).
Observaciones que no bloquean: `position_review` sin filas históricas, y
TTE.PA con 32 barras descartadas en el log frente a 30 `REAJUSTE` persistidos,
que queda como **FOLLOW_UP de T-018**, fuera de T-019.

### D-59 — 2026-09-30 — Score v2 exige contexto point-in-time
Decisión del propietario, tomada después de 2a-code (`782e462`) y **antes** de
implementar Score v2. No modifica el pre-registro de P3 (`8b2dddb`): concreta
cómo se aplica D-53/R-CTX al código de Score v2.

**Qué se decide.**
- `model_version = "2.0"` implica contexto **point-in-time obligatoriamente**.
- **Nunca** se puede combinar Score v2 con `legacy_v1`, aunque `config.yaml`
  siga teniendo `"1.0"` activo, como ocurrirá durante P3.
- El modo de contexto depende de la **versión de score pedida para el cálculo**,
  no de `config.scoring.score_model_version`. Pedir `"2.0"` selecciona PIT
  automáticamente.
- Intentar calcular Score v2 con contexto legacy es un **error**, no una
  advertencia.

**Por qué.** En 2a-code el selector deriva el modo de la versión activa de la
configuración. Con `"1.0"` activo, un cálculo de Score v2 que no pidiera PIT
explícitamente atravesaría el camino legacy, con el look-ahead de tendencia que
D-53 corrige. La revisión previa a P3 lo registró como observación.

**Efecto.** Lo implementa el paso 2 de T-019, con un test que demuestre que
Score v2 con contexto legacy falla.

### D-60 — 2026-09-30 — Producción v2 falla cerrada si el contexto point-in-time no es calculable
Decisión del propietario. Queda **fijada ahora** y solo tendrá efecto si algún
día se activa v2 en producción (paso 5 de T-019). Hasta entonces el
comportamiento productivo no cambia: v1 sigue activo.

**Qué se decide.** Si en una pasada de producción v2 el contexto PIT no es
calculable (Asia ausente, SMA200 sin historia, VIX ausente o cualquier otro
motivo no calculable):
- **ningún fallback a legacy**, **ninguna imputación** ni neutralización y
  **ningún score parcial**;
- la pasada v2 **no produce recomendaciones** basadas en ese contexto;
- la pasada **registra claramente el motivo** (el código de no calculable y su
  detalle).

**Por qué.** La regla v1 de dato ausente (la mitad de los puntos) solo sigue en
v1. En v2, un contexto incompleto no se puede presentar como un score completo.

**Efecto.** Hoy `fetch_point_in_time_market_context` lanza `RuntimeError` y
aborta la pasada entera: es código inerte mientras v1 esté activo. Antes del
paso 5 se sustituye por la política de D-60, y la forma exacta de declarar el
motivo en la pasada y en el manifiesto se implementa entonces.

### D-61 — 2026-10-01 — Resultado de P3 y estado de calibración de Score v2
Registro del paso 4 de T-019, autorizado por el propietario. No tiene margen de
decisión: lo fijan la regla pre-registrada de P3 (`8b2dddb`) y D-45, aplicadas
al resultado de la **única** ejecución confirmatoria (`P3_EXECUTOR_SHA` =
`87309da`, evidencia inmutable en `evidence/2026-09-30-T-019-paso3-p3/`).
Resumen generado desde esos artefactos en
`evidence/2026-10-01-T-019-score-v2/resultado-p3.md`.

**Swing (confirmatorio).** P3 produjo Δ Q5−Q1 = **−0,2895 R**, IC95
**[−0,4098, −0,1658]**, anchura **0,2440**, 19 bloques. Por la tabla
pre-registrada, aplicada en su orden, **`veredicto_ordenacion` = NO
CONCLUYENTE**, porque la anchura **0,2440 > 0,20**.

Que el intervalo entero sea negativo **no permite sustituir el veredicto
mecánico** por «ordena al revés» ni por ningún otro juicio confirmatorio. Se
publica, solo como **descripción separada del veredicto**:
- el signo del contraste es negativo;
- las cinco regiones tienen Δ negativo;
- los 89 activos con Δ calculable tienen Δ negativo;
- el intra-activo vale −0,751 R [−0,815, −0,672].

**Calibración de swing.** Los cinco candidatos —43,6 / 49,6 / 53,6 / 57,6 /
63,6— fallan OPERAR. Por tanto swing queda **`calibrated: false`**, con
`min_score_operar: null` y `min_score_vigilar: null`: **no existe franja
operativa v2 calibrada**. Ningún percentil se convierte en umbral.

**Medio.** `calibrated: false`. Su resultado es solo de trazabilidad, con el
veredicto forzado «NO CONCLUYENTE — inválido (bloque parcial 102 ≤ 250)»
(D-42, D-45).

**Intradía.** `calibrated: false`, sin laboratorio y sin umbrales (D-45).

**Producción.** D-47 sigue plenamente vigente:
- producción continúa con Score v1;
- 70/60 pertenecen exclusivamente a `"1.0"`;
- v2 no se activa;
- no hay transición atómica posible, porque P3 no produjo umbrales v2 válidos
  (el paso 5 de la ficha, en su parte de activación, no se hace en A-03).

`config.yaml` no cambia: `"1.0"`, 70/60, `calibrated: false`.

**Consecuencia metodológica.** Un resultado desfavorable o no concluyente **no
impide por sí mismo** cruzar GATE P3: `docs/gates.md` exige una respuesta
cuantificada, no favorable. Pero **D-61 no declara GATE P3 cruzado.** Eso se
decide en el paso 5, después de la revisión independiente final (requisito 5).
Matriz provisional en `evidence/2026-10-01-T-019-score-v2/gate-p3-matriz.md`.

**Nota (2026-10-01, revisión final, hallazgo M-1).** Todas las cifras de esta
decisión están **condicionadas al universo seleccionado en 2026 (sesgo de
supervivencia y selección no corregido)**. Los artefactos de P3 ya llevaban la
etiqueta y aquí faltaba. Añadirla no cambia ningún número.

### D-62 — 2026-10-01 — GATE P3 cruzado con el veredicto NO CONCLUYENTE
Decisión del propietario, tomada en el paso 5 de T-019 después de la revisión
independiente final del look-ahead. Base del cierre: `main` =
`4ca9a370a02d297c949555a409eb960adfb8d8e8`. El commit de cierre es el que
introduce esta decisión: `docs(T-019): cierre de GATE P3 y revisión final`.
_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y
selección no corregido)._

**Qué se decide.** **GATE P3 queda cruzado.** Sus cinco requisitos están
satisfechos (`evidence/2026-10-01-T-019-cierre/gate-p3-final.md`):
1. **Score v2 versionado** como `"2.0"` (D-46, D-59).
2. **Umbrales por horizonte:** swing, medio e intradía quedan **`calibrated:
   false`** (D-61).
3. **Ordenación publicada:** swing **NO CONCLUYENTE**.
4. **Ablaciones publicadas.**
5. **Revisión independiente del look-ahead hecha:**
   `evidence/2026-10-01-T-019-cierre/revision-look-ahead.md`. Sin BLOCKER ni
   IMPORTANTE; un MENOR (M-1, etiqueta de universo, corregido en D-61) y cinco
   observaciones.

**El resultado con el que se cruza** (D-61, sin reinterpretar):
- **Swing:** Δ Q5−Q1 −0,2895 R [−0,4098, −0,1658], anchura 0,2440 > 0,20 →
  **NO CONCLUYENTE**.
- **Medio:** «NO CONCLUYENTE — inválido (bloque parcial 102 ≤ 250)».
- **Intradía:** sin laboratorio.
- **Umbrales:** no hay ningún umbral v2; `min_score_operar` y
  `min_score_vigilar` son nulos en los tres horizontes.
- **Signo:** el negativo del contraste sigue siendo **descriptivo** y no
  constituye un veredicto distinto. `docs/gates.md` exige una respuesta
  cuantificada, no favorable.

**Producción.**
- Score v2 **no se activa**: P3 no produjo umbrales válidos y la activación
  atómica del paso 5 no es posible.
- Producción sigue en **Score v1** con 70/60 y `calibrated: false` (D-47), y
  `config.yaml` no cambia.
- v2 queda solo como investigación y versionado.
- D-60 sigue registrada para una posible activación futura.
- No hay release ni despliegue; la Pi sigue en `v0.4.1` = `8b2dddb`.

**Efecto.**
- **A-03 queda ACEPTADA** y T-019 cerrada.
- **P4 (A-04) queda desbloqueado**, pero **no se inicia** con esta decisión.
  Trabajará sobre `score_signal` sin umbrales operativos nuevos, como prevén
  `docs/gates.md` y D-45.
- P3 no se repite: cualquier estudio nuevo del score necesita su propia ficha
  y datos posteriores a la cosecha `071ddb2b…`, que P3 consumió entera
  (INV-15).

**Evidencia:**
- `evidence/2026-09-30-T-019-paso3-p3/` (ejecución única, inmutable);
- `evidence/2026-10-01-T-019-score-v2/` (paso 4);
- `evidence/2026-10-01-T-019-cierre/` (revisión final, matriz, suite y hashes).

### D-63 — 2026-10-01 — Pre-registro de P4: población, variantes y criterio
Decisión del propietario. Cierra **OD-P4-1 a OD-P4-13** de la ficha T-020 (A-04). Se toma **antes de
ejecutar P4 y sin abrir ningún desenlace nuevo de P4**. B1 constituye una **exposición previa
conocida y documentada** sobre esta misma cosecha (P2.6, 2026-08-31; ficha, sección 7.1). No se
consultó ningún resultado nuevo de B1 ni ningún resultado de B2, S1, S2 o E1. La ficha
`docs/tareas/T-020-p4-geometria.md` es la especificación; aquí solo se resumen las elecciones.
_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

**Qué se decide.**
1. **B1** (objetivo 2 a 3,5·ATR) queda **solo descriptiva**, con la etiqueta «previamente expuesta
   en esta misma cosecha; no confirmatoria; no elegible para sustituir C0». Ya se midió sobre
   `071ddb2b` en P2.6. Así se cierra el pendiente de D-02 sin fingir evidencia independiente.
   (OD-P4-1 = B)
2. **Población:** la de A-02 swing **sin cripto**, sin las exclusiones de P3 por Asia ni por la
   SMA200, que son requisitos del contexto v2 y no de la geometría.
   - Censo sin desenlaces: **101.251** señales y **90** activos.
   - `p4_population_sha256 = 78024050f7081ad4e1dd5cefaefbfa1a1668ff5b1a2ced8c34e62b6501873141`.
   - Bloques de 60 sesiones: **20** ocupados.
   - Evidencia: `evidence/2026-10-01-T-020-censo-p4/`.
   (OD-P4-2 = C)
3. **S1 y S2** se miden sobre toda la población, como política completa bajo la regla E, con
   `stop_basis` como desglose descriptivo. (OD-P4-3 = A)
4. **B2 = 4,875·ATR** puede ser candidata. No se la llama ciega del todo, porque hay exposición
   previa a B1 en la misma dirección. (OD-P4-4 = A)
5. **Entrada:** una sola comparación confirmatoria, **E1**, solo con C0: entrada al cierre frente a
   entrada a `open(t+1)` con el orden real de `evaluate_trade_at_entry`, y `R = 0` para las no
   ejecutadas. E1 no es una geometría ni candidata a P5, y no altera producción. Para las demás
   geometrías solo se publican la holgura y las categorías de D-06. (OD-P4-5 = C, acotada)
6. **Bloques:** primaria de 60; sensibilidad válida de 120. Las longitudes 40 y 80 (bloque ocupado
   más corto de 22 ≤ 40) son inválidas: se publican y quedan fuera de toda condición. (OD-P4-6 = A)
7. **Familia confirmatoria definitiva, `m = 4`:** B2, S1, S2 y E1. Bonferroni con 0,9875, 20.000
   remuestreos y la semilla 20260830. B1 queda fuera. (OD-P4-7 = A)
8. **Medio** fuera de P4. (OD-P4-8 = A)
9. **Criterio:** el de la sección 22 de la ficha, adaptado. **Solo B2, S1 y S2** pueden pasar a P5.
   Las condiciones 4 (heterogeneidad) y 7 (ejecutabilidad) no vetan. (OD-P4-9 = A)
10. **Robustez temporal interna sobre datos de desarrollo:** media por bloque de ΔR > 0 en los
    bloques 2–11 y en los 12–21. **Desviación formal del protocolo:** el protocolo pedía validación
    temporal en P4 y P5, pero la cosecha ya está consumida y no hay holdout sin consumir. **P4 no
    constituye validación temporal**; la validación independiente sigue en P7, bajo INV-15.
    (OD-P4-10 = B)
11. **Estratos descriptivos:** región, activo, régimen PIT, volatilidad y `stop_basis`. Un contexto
    PIT no calculable (7.157 señales en el censo) **no excluye** una señal de P4: se cuenta aparte y
    no se le inventa régimen. (OD-P4-11 = A)
12. **La heterogeneidad es una bandera obligatoria, no un veto.** Si sale ALTA, se publican y
    discuten los estratos antes de cerrar GATE P4. ALTA por sí sola no aprueba ni veta, y no hay
    calibración sintética. **FOLLOW_UP:** el instrumento de P2.6 trata como independientes sesiones
    que se solapan y puede confundir esa dependencia con heterogeneidad. Hay que revisarlo antes de
    darle función de veto en una fase posterior. (OD-P4-12 = B)
13. **La ejecutabilidad se publica y no veta.** (OD-P4-13 = A)

**Recuento derivado del censo:** 447 comparaciones, de las que 4 son confirmatorias. Es la fórmula
de la sección 20 de la ficha: el ejecutor la reproduce desde sus salidas, y nunca se escribe a
mano.

**Lo que no cambia.**
- P4 no se ha ejecutado, y no se implementa `p4.py` sin una autorización nueva.
- `config.yaml` sigue en `"1.0"`, Score v2 inactivo y la Pi en `v0.4.1`.
- El pre-registro de P4 (`P4_PREREG_SHA`) será el HEAD documental que quede después de la tercera
  revisión independiente de la ficha y de sus correcciones.

### D-64 — 2026-10-02 — Resultado de P4 y candidatas para P5
Registro del resultado congelado de la **ejecución confirmatoria única** de P4 (T-020, A-04). Se
transcribe la salida de `evidence/2026-10-01-T-020-p4/run/` sin recalcular nada.
_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

**Identidad.**
- `P4_PREREG_SHA = 48b884722ef027e99857a4e65f9ab6b11da4758f`
- `P4_CODE_SHA = 3df8230d7806dde4151b56501641a1524a3df9d8`: último commit que modifica el código
  del ejecutor.
- `P4_RUN_HEAD_SHA = c2c52b11c60bb8dfd08d8cb33d5f6f251e9bf2c0`: HEAD desde el que se lanzó la
  ejecución. Respecto a `3df8230` solo añade evidencia de preflight.
- `P4_RUN_EVIDENCE_COMMIT = cfa365da468edd04f0ccf4d5f20b657382078cbd`
- Ejecución el 2026-10-02 a las 05:37:50 UTC, con la marca escrita antes de abrir desenlaces.
  - Completó por la ruta normal: `p4-resultado.json` y `p4-resumen.md` íntegros, y ningún
    `p4-parada.json`.
  - El código de salida 0 no quedó archivado literalmente en la consola; se infiere de esa ruta de
    finalización.
  - P4 no se repite.
- El campo histórico `p4_executor_sha` de los artefactos de ejecución contiene `c2c52b1`, el HEAD
  de ejecución. La marca guarda aparte `p4_executor_sha_preflight = 3df8230`. No es un error de
  resultado y los artefactos no se reescriben.

**B2 frente a C0 (objetivo 2 a 4,875·ATR): PASA A P5.** Cumple todas las condiciones que vetan.
- ΔR = **+0,0717 R**; IC Bonferroni 98,75 % = **[+0,0061, +0,1356]**; pares = **101.226**.
- Sensibilidad 120: ΔR = +0,07264; IC95 inferior = +0,02378.
- Cota conservadora de ambigüedad: ΔR = +0,07099.
- Robustez temporal interna sobre datos de desarrollo: bloques 2–11 = +0,06930; bloques 12–21 =
  +0,07401.
- Nivel: media `net_R` = +0,17540; PF = 1,26344.

**S2 frente a C0 (stop 2,5·ATR, objetivo 3,75·ATR): PASA A P5.** Cumple todas las condiciones que
vetan.
- ΔR = **+0,0348 R**; IC Bonferroni 98,75 % = **[+0,0076, +0,0597]**; pares = **101.225**.
- Sensibilidad 120: ΔR = +0,03459; IC95 inferior = +0,01309.
- Cota conservadora de ambigüedad: ΔR = +0,03430.
- Robustez temporal interna sobre datos de desarrollo: bloques 2–11 = +0,02395; bloques 12–21 =
  +0,04562.
- Nivel: media `net_R` = +0,13876; PF = 1,24259.

**S1 frente a C0 (stop 1,5·ATR, objetivo 2,25·ATR): NO PASA.**
- ΔR = **−0,0411 R**; IC Bonferroni = **[−0,0708, −0,0096]**.
- Falla exactamente las condiciones **1, 2, 5 y 8**.

**E1 (entrada a `open(t+1)` con veto de producción frente a entrada al cierre, bajo C0): NO
CONCLUYENTE.**
- ΔR = **−0,0491 R**; IC Bonferroni = **[−0,1078, +0,0120]**.
- No es una geometría, no es candidata a P5 y no interviene en la decisión sobre B2, S1 y S2.

**B1 (objetivo 2 a 3,5·ATR): solo descriptiva.**
- ΔR = **+0,0206 R**; IC95 = **[+0,0047, +0,0363]**.
- «previamente expuesta en esta misma cosecha; no confirmatoria; no elegible para sustituir C0».
- No pertenece a Bonferroni, no influye en B2 y no pasa a P5.

**Candidatas que salen de P4:**
- **B2**
- **S2**

Las dos pasan a P5, como pre-registró la sección 22 de la ficha («si cumplen varias, todas pasan»).
No se elige una de las dos, y ninguna se declara mejor por tener un ΔR mayor. S1 queda descartada.
C0 sigue como control y referencia. P5 decidirá la robustez de las candidatas.

**Heterogeneidad.** Sale **ALTA en las cinco comparaciones**. Es una bandera, no un veto (D-63).
Los estratos pre-registrados ya calculados se publican y se discuten en
`evidence/2026-10-02-T-020-p4-cierre/resultado-y-heterogeneidad.md`. No se crea ninguna política
por estrato.

**Recuento derivado:** 447 comparaciones (B1 110, B2 110, S1 113, S2 113, E1 1), igual que el
previsto, de las que 4 son confirmatorias.

**Lo que no cambia.**
- B2 y S2 son candidatas de investigación para P5, no una geometría de producción.
- `config.yaml` sigue en `"1.0"`, Score v2 inactivo y la Pi en `v0.4.1`.
- El resultado es de desarrollo, no una validación fuera de muestra (INV-15). La validación
  independiente sigue en P7.

### D-65 — 2026-10-02 — GATE P4 cruzado
Cierre mecánico de GATE P4 con la regla del propietario: los cuatro requisitos de `docs/gates.md`
satisfechos y la revisión final independiente sin ningún BLOCKER ni IMPORTANTE.
_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

- **P4 se ejecutó una sola vez:** el 2026-10-02, desde `P4_RUN_HEAD_SHA = c2c52b1`, con
  `P4_CODE_SHA = 3df8230` y `P4_PREREG_SHA = 48b8847`. La evidencia está congelada en `cfa365d`
  (`evidence/2026-10-01-T-020-p4/run/`, 12/12 SHA256). P4 no se repite.
- **B2 y S2 pasan a P5** como candidatas (D-64). Ninguna se elige sobre la otra.
- **S1 no pasa:** falla las condiciones 1, 2, 5 y 8.
- **E1 sale NO CONCLUYENTE.** No es geometría ni candidata.
- **B1 es solo descriptiva:** «previamente expuesta en esta misma cosecha; no confirmatoria; no
  elegible para sustituir C0».
- **La heterogeneidad ALTA queda explicada y no veta** (D-63). Se explica por la dispersión
  observable por activo, régimen y volatilidad, y por una limitación conocida del instrumento debida
  al solapamiento. No se crea ninguna política por estrato. El FOLLOW_UP del instrumento sigue
  abierto.
- **Revisión final independiente:** tras la vuelta de cierre, 0 BLOCKER, 0 IMPORTANTE, 0 MENOR y 1
  OBSERVACIÓN, que es la verificabilidad del texto archivado de la revisión de look-ahead.
- **GATE P4 CRUZADO.** La matriz está en `evidence/2026-10-02-T-020-p4-cierre/gate-p4-final.md`.
- **A-04 / T-020 queda ACEPTADA.**
- **P5 queda desbloqueado, pero NO iniciado.** La ficha de P5 se escribe con una autorización aparte.

**Lo que no cambia.** No se toca producción:
- B2 y S2 son candidatas de investigación para P5, no una geometría productiva;
- `config.yaml` sigue en `"1.0"` con la geometría C0;
- Score v2 sigue inactivo;
- la Pi sigue en `v0.4.1`;
- no hay release ni despliegue.

El resultado es de desarrollo; la validación independiente sigue en P7 (INV-15).

### D-66 — 2026-10-02 — Pre-registro de P5: superficies, robustez y políticas elegibles
Decisión del propietario. Cierra **OD-P5-1 a OD-P5-16** de la ficha T-021 (A-05). Se toma **antes
de ejecutar P5 y sin ningún desenlace de ningún punto nuevo**: el único cálculo sobre la cosecha es
el inventario estructural sin desenlaces de `evidence/2026-10-02-T-021-p5-diseno/`. La ficha
`docs/tareas/T-021-p5-regiones-robustas.md` es la especificación; aquí se resumen las elecciones, y
las alternativas no elegidas se conservan como historial en la ficha.
_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

**Qué es P5.** P5 prueba la robustez de B2 y S2, las candidatas de P4 (D-64), frente a C0. **Solo
puede quitar candidatas; nunca promociona un vecino. P5 puede terminar en `[]`.** Es desarrollo
sobre una cosecha ya consumida, posterior a la selección de P4, y **no es validación**: la validación
independiente sigue en P7 (INV-15).

**Qué se decide.**
1. **Superficies:** dos 3×3 locales sobre una retícula común (OD-P5-1 = A). El paso es Δstop =
   0,25·ATR y Δtarget2 = 0,375·ATR, fijo (OD-P5-2 = A).
   - **B2:** stop ∈ {1,75; 2,00; 2,25} × target2 ∈ {4,500; 4,875; 5,250}; centro (2,00; 4,875).
   - **S2:** stop ∈ {2,25; 2,50; 2,75} × target2 ∈ {3,375; 3,750; 4,125}; centro (2,50; 3,750).
   - target1 = 1,5, `min_rr` = 1,5, `entry_max_atr` = 0,75, `target2_structural` = false, regla E,
     coste 0,20 % y swing con 40 barras, fijos.
2. **Borde de B2 con `target3`** (OD-P5-3 = C):
   - en las tres celdas con target2 = 5,25, `target3` = 5,625 y `m3_auxiliar` = true, **solo para
     el diagnóstico**;
   - esas celdas no son políticas ni candidatas, nunca pueden salir de P5, y su hash contiene el
     `target3` real de 5,625;
   - B2 conserva `target3` = 5,0 y `m3_auxiliar` = false.
3. **Frontera de RR de S2, truncada:** (2,50; 3,375), (2,75; 3,375) y (2,75; 3,750) son
   `AUSENCIA_ESTRUCTURAL` (RR < 1,5). No se estiman y no entran en ningún denominador.
4. **Vecindad de 8 vecinos geométricos** (OD-P5-5 = A), con semiplanos `s−`, `s+`, `m2−` y `m2+`.
   - **13 vecinos válidos:** 8 de B2 y 5 de S2.
   - **Ningún vecino es elegible como política.**
   - **Asimetría de S2, que no se suaviza después de medir:** sus dos vecinos iso-RR, (2,25; 3,375)
     y (2,75; 4,125), son cada uno el único vecino válido de un semiplano, así que **los dos tienen
     que ser ACEPTABLES**. De los otros tres puede fallar como mucho uno.
5. **Clases de celda** (OD-P5-15 = A, con los umbrales de capacidad de P4):
   - `AUSENCIA_ESTRUCTURAL`;
   - `NO_ESTIMABLE`: falla la capacidad. No es buena ni mala, cuenta en `|NE|` y puede llevar a
     NO_CONCLUYENTE;
   - `ACEPTABLE`: estimable, IC95 inferior de ΔR > 0, cota conservadora puntual > 0, nivel > 0 y
     PF > 1 (OD-P5-4 = A; OD-P5-12 = A);
   - `DÉBIL`: estimable, ΔR puntual > 0, pero no ACEPTABLE;
   - `CONTRARIA`: estimable y ΔR puntual ≤ 0.
6. **Región robusta** (OD-P5-4 = A), con umbrales fijos:
   - ningún vecino CONTRARIO;
   - cada semiplano con vecinos estimables tiene al menos un ACEPTABLE;
   - `|A| / |E| ≥ 0,75`;
   - `|NE| ≤ 1`;
   - ningún semiplano con todos sus vecinos válidos NO_ESTIMABLES;
   - y el centro cumple su propio criterio: las diez condiciones de P4 y la reproducción de P4 de
     OD-P5-16.
7. **Fragilidad:** exactamente F1–F6 de la ficha; no se añade ninguna causa después de medir.
   - **Precedencia de etiqueta:** FRÁGIL > DEPENDIENTE_DE_MERCADO > NO_CONCLUYENTE > ROBUSTA.
   - **Solo ROBUSTA sobrevive.**
8. **Multiplicidad jerárquica** (OD-P5-6 = A):
   - confirmatorias nuevas = **0**; la evidencia confirmatoria de B2 y S2 sigue siendo la de P4;
   - los IC95 de los vecinos y del LOCRO son vetos pre-registrados: pueden quitar una candidata,
     nunca crearla;
   - sin Bonferroni nuevo y sin banda simultánea.
9. **Mercado = región; LOCRO decisorio** (OD-P5-7 = A; OD-P5-8 = A, con la capacidad i):
   - para cada centro se calcula la primaria sin USA, sin EUROPA y sin ASIA; GLOBAL y
     EMERGING_MARKETS se quedan dentro y se publican descriptivamente;
   - cada LOCRO pasa solo si es estimable y su IC95 inferior de ΔR es > 0;
   - **la fracción de pares se calcula sobre su propia población restante:**
     - sin USA: 56.353 señales, mínimo 50.718 pares;
     - sin EUROPA: 66.629 señales, mínimo 59.967 pares;
     - sin ASIA: 83.298 señales, mínimo 74.969 pares;
   - el resto de los umbrales de capacidad, los de P4;
   - **nunca el límite absoluto de 91.126** en el LOCRO, y un test demuestra que esa implementación
     errónea fallaría.
10. **Concentración por activo descriptiva** (OD-P5-9 = A):
    - se publican positivos y negativos, percentiles, la mayor contribución individual y la de los
      5 y los 10 primeros activos;
    - no veta ni rescata, y no se introduce ningún umbral después.
11. **Heterogeneidad no vetante** (OD-P5-10 = A): ALTA no veta. El instrumento se publica y no
    decide; el FOLLOW_UP de autocorrelación y solapamiento sigue fuera de P5.
12. **Temporal** (OD-P5-11 = A):
    - **en el centro, veto** (aunque ya se conoce de P4): las dos mitades > 0, y el bloque de 120
      con ΔR > 0 e IC95 inferior > 0;
    - **en los vecinos**, el bloque de 120 y las mitades son descriptivos y no forman parte de
      ACEPTABLE.
13. **Ambigüedad** (OD-P5-12 = A): para que un vecino sea ACEPTABLE, la cota conservadora puntual
    tiene que ser > 0. La favorable se publica. No se exige ningún IC de la cota.
14. **Salida permitida, exactamente:** `[]`, `[B2]`, `[S2]` o `[B2, S2]` (OD-P5-13 = A). C0 sigue
    siendo control. Un vecino, aunque tenga mejor ΔR, se publica, no se adopta, no recibe hash de
    política candidata y no puede sustituir a B2 ni a S2.
15. **Configuración y hash** (OD-P5-14 = A):
    - `advisor_config_hash` sobre el `AdvisorConfig` completo con solo la geometría sustituida; en
      C0 tiene que dar `89406d28c7b4b6e6c4f032cd63b6868c927af3e926dfb52d430dfa6654d06387`;
    - envoltorio canónico `intradia.p5.politica.v1` serializado con `json.dumps(payload,
      sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)` en UTF-8;
    - `policy_sha256` (los vecinos publican el mismo cálculo como `diagnostico_sha256`, nunca como
      `policy_sha256`);
    - las salidas son las constantes del código: `STOP_FIRST`, `TARGET_FIRST`, `TIME` y `FINAL`.
16. **Recuento:** 5 comparaciones con IC por vecino y 3 LOCRO por centro: (8·5 + 3) + (5·5 + 3) =
    **71**, con **0 confirmatorias nuevas**.
    - El ejecutor deriva el 71 de la estructura antes de abrir ningún desenlace; si sale otro
      número, **STOP**. El 71 nunca sustituye al recuento derivado.
    - Acumulado descriptivo de comparaciones con IC sobre la cosecha: P4 447 + P5 71 = **518**.
17. **Reproducción de P4 antes de la marca, con guardas reforzadas** (OD-P5-16 = A):
    - **solo** se evalúan C0, B2 y S2; intentar evaluar cualquier otra geometría lanza un error;
    - **solo** se reproducen estimaciones ya publicadas. Para X ∈ {B2, S2}, las filas de
      `estimaciones.tsv`: `(X, primaria_60, "")` —que **es la de Bonferroni**, 0,9875 y 20.000
      remuestreos—, `(X, bloque_120, "")`, `(X, cota_conservadora, "")`,
      `(X, cota_favorable, "")`, `(X, mitades, bloques_2_11)` y `(X, mitades, bloques_12_21)`;
      además, la fila X de `nivel.tsv` y de `capacidad.tsv`, y las filas X de
      `emparejamiento.tsv`;
    - del IC95 de 2.000 remuestreos usado para la capacidad solo se reproduce y compara la
      `anchura_ic95`; sus extremos no se archivan;
    - se comparan cadenas con la representación de P4 (`float` → `"{:.6f}"`). Si algo diverge,
      **STOP**, sin actualizar el valor esperado ni introducir ninguna tolerancia;
    - C0 se verifica por identidad semántica con el event study y por su `advisor_config_hash`;
    - **aislamiento:** no se escriben eventos ni `net_R` por `signal_id`, y la API del preflight no
      los devuelve; la función de reproducción devuelve solo el agregado autorizado;
    - **antes de la marca fallan explícitamente**, con tests que lo comprueban, las
      **estimaciones** (todo cálculo con desenlaces) del LOCRO, de regiones y subpoblaciones, de
      estratos, de concentración por activo nueva, de los vecinos y cualquier estimación nueva de
      P5. El censo estructural por región, los denominadores del LOCRO y el recuento estructural no
      usan desenlaces y sí se calculan en el preflight;
    - la evidencia del preflight solo contiene agregados ya publicados y controles estructurales;
    - **esto no autoriza repetir P4** ni ejecutar `p4 --fase confirmatoria`.

**Lo que no cambia.**
- P5 **no** se ha ejecutado, y `p5.py` no se implementa sin una autorización nueva.
- `config.yaml` sigue en `"1.0"` con C0, Score v2 inactivo y la Pi en `v0.4.1`.
- El `P5_PREREG_SHA` será el HEAD documental que quede después de la revisión final del
  pre-registro y de sus correcciones, con 0 BLOCKER y 0 IMPORTANTE.

### D-67 — 2026-10-03 — Resultado de P5: B2 y S2 robustas
Registro del resultado congelado de la **ejecución confirmatoria única** de P5 (T-021, A-05). Se
transcribe la salida de `evidence/2026-10-02-T-021-p5/run/` sin recalcular nada; el detalle completo
está en `evidence/2026-10-03-T-021-p5-cierre/resultado-p5.md`.
_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

**Identidad.**
- `P5_PREREG_SHA = a7c3d238d651b4ea8f48834848c03c0a5a462dfa`
- `P5_CODE_SHA = 6c7f9135774f157e82634b6abf82a847d9b99bd9`
- `P5_PREFLIGHT_HEAD = 7446602114b26f56cae549d2ec299d7bbc07b459`
- `P5_RUN_HEAD_SHA = 282b1ce991bb4567ff2ad41a28e00c9518662115`: archiva la revisión final de
  look-ahead, previa a la ejecución. Respecto a `6c7f913` solo añade evidencia.
- `P5_RUN_EVIDENCE_COMMIT = 86ddd5baf8ceabe6e9d3747d645c7c99d719343c`
- Marca escrita antes de abrir desenlaces, con `inicio_utc = 2026-10-03T09:44:05.684666+00:00` y
  sha256 `f50d5ec9cc7e2c266515778592c4398001ee8588dbcdcc2b4c783bcca87c1f8c`, igual al
  `token_sha256` del resultado.
- Completó por la ruta normal: `p5-resultado.json` y `p5-resumen.md` íntegros y ningún
  `p5-parada.json`. La consola archiva `código de salida: 0`.
- **P5 se ejecutó exactamente una vez y no se repite.**

**Recuento:** comparaciones previstas **71**, derivadas de las salidas **71**, confirmatorias nuevas
**0**.

**B2 (stop 2,0·ATR, objetivo 2 a 4,875·ATR): ROBUSTA.**
- `centro_p4 = True`; F1, F2, F3, F4, F5 y F6 = False.
- 8 vecinos válidos: **8 ACEPTABLES**, 0 NO_ESTIMABLES.
- LOCRO: sin USA, 56.329 pares, ΔR 0,067950, IC95 [0,015507, 0,122806]; sin EUROPA, 66.626 pares,
  ΔR 0,077285, IC95 [0,012695, 0,139081]; sin ASIA, 83.275 pares, ΔR 0,070625, IC95 [0,021085,
  0,119686]. Los tres son estimables y tienen IC95 inferior > 0.

**S2 (stop 2,5·ATR, objetivo 2 a 3,75·ATR): ROBUSTA.**
- `centro_p4 = True`; F1, F2, F3, F4, F5 y F6 = False.
- 5 vecinos válidos: **5 ACEPTABLES**, 0 NO_ESTIMABLES. Los dos vecinos iso-RR críticos,
  (2,25; 3,375) y (2,75; 4,125), son ACEPTABLES.
- LOCRO: sin USA, 56.328 pares, ΔR 0,038843, IC95 [0,017103, 0,059156]; sin EUROPA, 66.626 pares,
  ΔR 0,032699, IC95 [0,004929, 0,058428]; sin ASIA, 83.274 pares, ΔR 0,033781, IC95 [0,014273,
  0,052136]. Los tres son estimables y tienen IC95 inferior > 0.

**Superficies.** Se publican completas, sin recalcular (`superficie.tsv`). B2 tiene 8/8 vecinos
ACEPTABLES y S2 5/5. Las tres celdas de B2 con `target2 = 5,25` (`target3 = 5,625`,
`m3_auxiliar = true`) son solo diagnósticas. Ningún vecino es política ni recibe `policy_sha256`.

**Ausencias estructurales de S2:** (2,50; 3,375), (2,75; 3,375) y (2,75; 3,750), por RR < 1,5.
Quedaron fijadas en D-66, no se estimaron y no son descartes por rendimiento.

**Concentración por activo** (descriptiva: no veta, no aprueba y no se crea ningún umbral):
- B2: 75 activos positivos y 15 negativos; mayor 5,2492 %, top 5 18,7986 %, top 10 32,9982 %.
- S2: 74 activos positivos y 16 negativos; mayor 3,6788 %, top 5 17,9082 %, top 10 33,3776 %.

**Descartes:**
- Candidatas heredadas de P4 descartadas por FRÁGIL: ninguna.
- Descartadas por DEPENDIENTE_DE_MERCADO: ninguna.
- NO_CONCLUYENTE: ninguna.

Los 13 vecinos son diagnósticos, no candidatas.

**Supervivientes: exactamente `[B2, S2]`.** P5 solo prueba robustez: no ordena una sobre la otra y
no dice que una sea mejor.

**Configuraciones completas:** `evidence/2026-10-03-T-021-p5-cierre/politicas-finales.json`,
generado con `policy_payload` y `canonical_json`. El `policy_sha256` se regenera desde el
`canonical_json`.
- B2: `advisor_config_hash = c5d60f44e89a754f34dfc685cda5073af1c0f9dbb04ab3ec14a813d423f81760`,
  `policy_sha256 = d5d6a533fe846a6ebb5d5c8e313c84f2a5b4e04095d08386e5d903dce73101b9`.
- S2: `advisor_config_hash = 8a151b80d91bf73e431ec38e5e21f22268783bbd0a26d5f72e6ef8887aca0dbb`,
  `policy_sha256 = e37ee93363dbbd7c58cae74bba4391ab9ad41dd1f3ed55804a92efb531e44d11`.

**Lo que no cambia.**
- B2 y S2 son políticas candidatas de investigación. **Ninguna se activa.**
- `config.yaml` sigue en `"1.0"` con C0, Score v2 sigue inactivo y la Pi sigue en `v0.4.1`.
- El resultado es de desarrollo sobre una cosecha ya consumida, no una validación (INV-15). La
  validación independiente sigue en P7.

### D-68 — 2026-10-03 — GATE P5 cruzado
Cierre mecánico de GATE P5 con la regla del propietario: los cuatro requisitos de `docs/gates.md`
satisfechos y la revisión final independiente sin ningún BLOCKER ni IMPORTANTE.
_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

- **P5 se ejecutó exactamente una vez:** el 2026-10-03, desde `P5_RUN_HEAD_SHA = 282b1ce`, con
  `P5_CODE_SHA = 6c7f913`, `P5_PREREG_SHA = a7c3d23` y la marca a las 09:44:05 UTC. La evidencia está
  congelada en `86ddd5b` (`evidence/2026-10-02-T-021-p5/run/`, 11/11 SHA256), y ningún commit
  posterior la toca. P5 no se repite.
- **71/71 comparaciones**, de ellas 0 confirmatorias nuevas.
- **B2: ROBUSTA.** **S2: ROBUSTA.** `centro_p4 = True` y F1–F6 = False en las dos (D-67).
- **13/13 vecinos ACEPTABLES:** 8/8 de B2 y 5/5 de S2, incluidos los dos iso-RR críticos de S2.
- **6/6 LOCRO decisorios superados:** todos estimables y con IC95 inferior > 0.
- **Supervivientes: `[B2, S2]`.** Ninguna se ordena sobre la otra.
- **Configuraciones completas y hashes** en `evidence/2026-10-03-T-021-p5-cierre/politicas-finales.json`:
  - B2: `advisor_config_hash c5d60f44…1760`, `policy_sha256 d5d6a533…01b9`;
  - S2: `advisor_config_hash 8a151b80…0dbb`, `policy_sha256 e37ee933…4d11`.
  Se regeneraron desde `canonical_json` y coinciden con la marca y con el preflight.
- **Ninguna candidata descartada** por fragilidad, por dependencia de mercado ni por resultado no
  concluyente. Las 3 ausencias de S2 son estructurales (RR < 1,5, D-66), no descartes por resultado.
- **Revisión final independiente:** 0 BLOCKER, 0 IMPORTANTE, 0 MENOR y 1 OBSERVACIÓN sin impacto
  (`evidence/2026-10-03-T-021-p5-cierre/revision-final.md`).
- **GATE P5 CRUZADO.** La matriz está en `evidence/2026-10-03-T-021-p5-cierre/gate-p5-final.md`.
- **A-05 / T-021 queda ACEPTADA.**
- **P6 queda desbloqueado, pero NO iniciado.** Su ficha se escribe con una autorización aparte.

**Lo que no cambia.** No se toca producción:
- B2 y S2 son políticas candidatas de investigación y **ninguna se activa**;
- `config.yaml` sigue en `"1.0"` con la geometría C0;
- Score v2 sigue inactivo;
- la Pi sigue en `v0.4.1`;
- no hay release ni despliegue.

El resultado es de desarrollo sobre una cosecha ya consumida; la validación independiente sigue en
P7 (INV-15).

### D-69 — 2026-10-03 — P6: decisiones de diseño cerradas
Decisión del propietario. Cierra **OD-P6-1 a OD-P6-43** de la ficha T-022 (A-06). Se toma **antes de
implementar P6 y sin ningún desenlace de sistema**. Lo único calculado sobre la cosecha es el censo
estructural sin desenlaces de `evidence/2026-10-03-T-022-p6-diseno/`. La ficha
`docs/tareas/T-022-p6-sistema-completo.md` es la especificación; aquí se resumen las elecciones, y las
alternativas no elegidas se conservan como historial en la ficha.
_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

**Qué es P6.** P6 ejecuta B2 y S2, las políticas candidatas de P5 (D-67/D-68), como **sistemas
completos** sobre una cartera con capital finito. No usa operaciones pareadas. C0 es un control
descriptivo. Es desarrollo sobre una cosecha ya consumida, **no validación**: la validación
independiente sigue en P7 (INV-15).

**Decisiones:**

| OD | Decisión | OD | Decisión |
|---|---|---|---|
| 1 Capital | A | 23 Activos tardíos del benchmark | B |
| 2 Unidades | A | 24 Dividendos del benchmark | B |
| 3 Base del sizing | A | 25 Costes del benchmark | A |
| 4 Cash insuficiente | A | 26 Sharpe y risk-free | A |
| 5 Límites globales | A | 27 Exceso principal | A |
| 6 Orden de entradas simultáneas | D | 28 ¿Veta el exceso? | A |
| 7 Cronología intradía | A | 29 C0 | A |
| 8 Liquidación | A | 30 Muestra mínima | A |
| 9 Costes | A | 31 Drawdown máximo | C |
| 10 Slippage | D | 32 Sharpe, Sortino y Calmar | A |
| 11 Precio de ejecutabilidad | A | 33 Incertidumbre | A + C |
| 12 Derecho al dividendo | A | 34 Salida | A |
| 13 Fecha del dividendo | C | 35 Hash de sistema | A |
| 14 Fiscalidad | A | 36 Empates | A |
| 15 Fuente FX | A (con B de respaldo) | 37 Población de señales | **C** |
| 16 Regla causal FX | A | 38 Mismo activo | A |
| 17 Exposición por divisa | C | 39 Universo | A |
| 18 Sector | A para acciones + categorías de C para ETF/ETC | 40 Caja en divisas | A |
| 19 UNKNOWN y ETF/ETC | A | 41 Calendario | A |
| 20 Valoración | C | 42 Contexto | A |
| 21 Ventana | A | 43 Moneda del R decisorio | A |
| 22 Buy-and-hold | A | | |

**Semántica vinculante.**

1. **Capital, unidades y sizing (OD-P6-1/2/3).**
   - 100.000 EUR iniciales y unidades fraccionarias.
   - Sizing sobre la equity causal inmediatamente anterior al lote de entrada.
   - `risk_per_trade_pct = 0,5 %` y `max_position_pct = 10 %` sin cambio; no se optimizan en P6.
2. **Cash (OD-P6-4/5).**
   - Long only, sin margen, sin apalancamiento y cash nunca negativo.
   - Si la posición calculada no cabe con la comisión incluida → `INSUFFICIENT_CASH`, rechazada
     entera. No se reduce el tamaño ni se prorratea.
   - Sin límites globales de posiciones, riesgo, región, sector o divisa: son de R-01, después de P7.
3. **Desempate (OD-P6-6).** Entradas con el mismo `timestamp_utc`, en orden ascendente de
   `sha256("intradia.p6.desempate.v1" ‖ signal_id)`. La misma regla para B2, S2 y C0. Ni score ni
   alfabeto.
4. **Cronología (OD-P6-7/8/36/41).**
   - Causal y global, con timestamps reales de mercado.
   - Calendario = `exchange_calendars` + `exchange_overrides.yaml` + versión de tzdata, todo en
     `P6_DATA_ID`.
   - Fases en empate: `OPEN_EXIT < OPEN_ENTRY < CLOSE_EXIT < CLOSE_DIVIDEND < CLOSE_VALUATION <
     SIGNAL`.
   - Una salida por hueco libera el cash en la apertura; una salida intradía, solo en el cierre.
   - Entre plazas manda el tiempo UTC real.
   - El cash de una venta está disponible desde que se materializa la salida; no se modela T+1/T+2.
5. **Costes (OD-P6-9).** 0,10 % sobre el nominal de entrada y 0,10 % sobre el de salida. No es
   algebraicamente idéntico al 0,20 % fijo de P4 salvo cuando salida = entrada.
6. **Slippage (OD-P6-10).** Primario de 5 pb por lado; sensibilidad de 10 pb por lado, **solo
   descriptiva**: no veta, no rescata y no cambia los supervivientes.
7. **Ejecutabilidad (OD-P6-11).** El RR, `entry_max`, el riesgo y el sizing se evalúan con el **precio
   efectivo después del slippage**.
8. **Dividendos (OD-P6-12/13/14).**
   - Cobra la posición abierta al cierre de la sesión anterior a la fecha ex. Una compra en la fecha ex
     no cobra; una venta en su apertura de una posición que venía abierta sí cobra.
   - Sin fecha de pago: el dividendo entra en cash al **cierre de la sesión ex**.
   - Bruto, sin retención.
   - La misma regla para las políticas y el benchmark.
9. **FX (OD-P6-15/16).**
   - Más adelante, con autorización aparte, se crea un sidecar congelado de `EURUSD=X`, `EURJPY=X` y
     `EURHKD=X` desde Yahoo/yfinance.
   - **Integridad obligatoria:** el `EURUSD=X` del sidecar tiene que reproducir exactamente la cadena
     canónica de la cosecha. Si falla, no se excluye ningún activo, no se acepta una serie aproximada,
     se documenta el fallo y se usa como fuente FX la **alternativa B** pre-registrada (tipos de
     referencia diarios oficiales).
   - Regla causal: para un evento en τ, el cierre de la última barra FX **completa y disponible antes
     de τ**, nunca el cierre futuro del mismo día.
   - `fx_rate_to_EUR = 1 / close(EURXXX=X)`.
   - En este commit no se descarga nada.
10. **Exposición por divisa (OD-P6-17).** Se publican dos: la divisa de cotización y liquidación y la
    `economic_currency`. `MULTI` es una categoría propia. Sin look-through.
11. **Sector (OD-P6-18/19).**
    - Acciones: sector externo verificable, congelado con `instrument_id`, `sector`, `taxonomy`,
      `source` y `observed_at`.
    - ETF y ETC: categorías estructurales por tipo, sin look-through.
    - `UNKNOWN` es válida, queda en el denominador y se publica.
    - El sector es **solo descriptivo**: nunca decide una entrada, un veto ni la supervivencia.
    - Todavía no se obtienen estos datos.
12. **Valoración (OD-P6-20).** El ledger por eventos es la fuente de verdad. Más adelante se genera una
    serie diaria de equity a las 23:59:59 UTC de cada día con al menos una sesión. `periodos_por_año`
    sale del calendario antes de cualquier desenlace.
13. **Ventana (OD-P6-21).** Regla A.
    - Con OD-P6-37 = C y OD-P6-42 = A, el inicio exige el calentamiento estructural de los 88 activos
      iniciales y la SMA200 de `^STOXX50E` causalmente completa.
    - Fecha estimada: **2022-06-14**. El preflight deriva y fija la fecha exacta de forma mecánica.
    - Fin: **2026-08-27**, la última sesión común.
    - Las exclusiones puntuales posteriores por contexto asiático no mueven el inicio.
14. **Benchmark (OD-P6-22/23/24/25).**
    - Pesos iguales sobre los 90 activos, sin rebalanceo.
    - ARM y Q8Y0.DE: su 1/90 queda en cash hasta la apertura de la barra siguiente a su barra 120.
    - Dividendos reinvertidos en el mismo activo en la apertura siguiente al abono.
    - Paga los mismos costes, slippage, FX y reglas de dividendos que las políticas, incluidas la
      compra inicial, las reinversiones y la liquidación final.
15. **Sharpe y Sortino (OD-P6-26).** Sharpe con **rf = 0** y Sortino con **MAR = 0**, rotulados así.
    No se aplica hacia atrás el 2,25 % actual.
16. **Exceso (OD-P6-27/28).** Principal: `excess_CAGR_pp = 100·(CAGR_policy − CAGR_buy_hold)`;
    también se publica `excess_terminal_pp`. Para sobrevivir es **obligatorio**
    `excess_CAGR_pp > 0`. No hay otro umbral de exceso.
17. **C0 (OD-P6-29).** Solo control descriptivo. Nunca veta ni rescata a B2 o S2, nunca pasa a P7 y
    nunca vuelve a ser candidata.
18. **Muestra (OD-P6-30).** `N_closed ≥ 100`. Por debajo, **`NO EVALUABLE POR MUESTRA`**, y no pasa a
    P7. Se publican las operaciones por año y los años con operaciones, sin otro veto. El recuento
    nunca reabre esta OD.
19. **Drawdown (OD-P6-31).** `max_drawdown ≥ −25 %`; uno peor veta. El umbral no se cambia después de
    ver resultados.
20. **Métricas descriptivas (OD-P6-32).** Sharpe, Sortino y Calmar son **solo descriptivos**: no vetan
    ni rescatan.
21. **Incertidumbre (OD-P6-33).** Ni bootstrap ni IC de trayectoria. Se publican las métricas de
    trayectoria completas, los resultados por año natural y por primera y segunda mitad de la ventana,
    rotulados «**robustez temporal interna sobre datos de desarrollo**». Solo descriptivo: no es
    validación y no veta.
22. **Salida (OD-P6-34).** Exactamente `[]`, `[B2]`, `[S2]` o `[B2, S2]`. Si las dos pasan, las dos
    van a P7. No se elige la mejor ni se crea una combinación de B2 y S2.
23. **Identidad (OD-P6-35).** Más adelante se crean `intradia.p6.system.v1`, con un `system_sha256`
    que identifica todas las decisiones económicas y de contexto de T-022, y el `P6_DATA_ID`
    compuesto. Los dos existen y quedan congelados antes de la ejecución.
24. **Población (OD-P6-37 = C, especialmente vinculante).**
    - **Primaria y única decisoria:** OPERAR con Score v1 y el contexto point-in-time de OD-P6-42.
    - **Puente descriptivo hacia P4/P5:** una corrida con **todas las barras elegibles**. No veta, no
      rescata, no elige y no modifica el resultado de P6.
    - Cada corrida tiene su propio `system_sha256`.
    - Se declara expresamente, sin ocultar la diferencia de población:
      - P4/P5 midieron todas las barras, no OPERAR;
      - el Score v1 no tiene ordenación demostrada (A-02, D-42);
      - P3 estudió el Score v2, no el v1;
      - el RR forma parte del Score v1: con el stop de volatilidad, B2 recibe mecánicamente 15 puntos
        de RR, frente a 10 en S2 y C0.
25. **Mismo activo (OD-P6-38).** Una señal nueva de un activo con posición abierta →
    `IGNORED_ALREADY_OPEN`, contada y publicada. Sin piramidar y sin modificar el stop ni los
    objetivos.
26. **Universo (OD-P6-39).** Exactamente los 90 activos de P4/P5. ARM y Q8Y0.DE entran en su
    elegibilidad: la apertura de la barra siguiente a su barra 120. No se elimina ningún activo por FX,
    sector, región o conveniencia.
27. **Caja (OD-P6-40).** Una sola caja en EUR. Cada flujo en otra divisa se convierte con el FX causal,
    sin coste FX adicional porque no hay un coste congelado defendible. La limitación se declara.
28. **Contexto (OD-P6-42).**
    - Obligatorio `context_mode = "point_in_time"`, con la función R-CTX de D-52/D-53/D-56 y el
      `analysis_timestamp` de D-50.
    - `NO_CALCULABLE_CONTEXT_HISTORY` o la falta del contexto exigido excluye la señal, y se cuenta.
    - No se usa `legacy_v1` ni se neutraliza para fabricar un contexto ausente.
    - Replica el contrato causal del laboratorio y de P3, y **no es idéntico al contexto v1 activo hoy
      en producción**.
29. **R decisorio (OD-P6-43).**
    - El PF y el R que deciden el gate son `trade_R_local`, `profit_factor_local` y `mean_R_local`, en
      la divisa de cotización y sin efecto FX. El R y el PF en EUR son **solo descriptivos**.
    - El efecto FX entra íntegro en la equity en EUR, el retorno, el CAGR, el drawdown y el exceso
      frente al benchmark.

**Criterio decisorio de P6.** B2 o S2 pasan P6 solo si se cumplen **a la vez**:

```text
N_closed >= 100
profit_factor_local > 1
mean_R_local > 0
max_drawdown >= -25 %
excess_CAGR_pp > 0
```

Sharpe, Sortino, Calmar, las sensibilidades, C0, los subperiodos y el puente de todas las barras son
descriptivos. No hay ranking entre B2 y S2.

**Lo que no cambia.**
- P6 **no se ha ejecutado**: no existe `p6.py`, no se ha descargado el FX ni el sector y no se ha
  calculado ninguna señal OPERAR ni ningún desenlace.
- No existe todavía `P6_PREREG_SHA`: será el HEAD documental que quede tras la revisión final del
  pre-registro y sus correcciones, con 0 BLOCKER y 0 IMPORTANTE.
- La implementación, el sidecar FX y el mapa de sector necesitan autorizaciones aparte.
- Producción no cambia: `config.yaml` en `"1.0"` con C0, Score v1 70/60, Score v2 inactivo y la Pi en
  `v0.4.1`.

**Precisiones de la revisión final del pre-registro** (2026-10-03). **Especificación derivada de la
revisión, **ratificada expresamente por el propietario el 2026-10-03, antes de congelar** el
pre-registro (las cinco precisiones, una a una: `mean_R_local` decide y la media por bloques es
descriptiva; fuente B del BCE con 17:00 Europe/Berlin, último tipo causal y `1/tipo`; petición fija de
Yahoo y fallo de A ante cualquier barra que falte, sobre o cambie de las 1.300 de `EURUSD=X`; comisión
dentro del 1/90 y de cada reinversión; población OPERAR `broker_neutral`).** `P6_PREREG_SHA` es el
HEAD del commit de congelación que registra esta ratificación. No cambian ninguna letra
de D-69. Añaden parámetros que el texto no fijaba (17:00 Europe/Berlin para la fuente B, la comisión
dentro del importe del benchmark, el predicado broker neutral, la petición fija de la fuente A) y
nombran la consecuencia de usar `mean_R_local` frente a INV-14. Se añadieron para cerrar ambigüedades
que permitirían reinterpretar después:
- **INV-14:** el criterio decide con `mean_R_local`, la media de las operaciones cerradas, como fija este
  D-69. Es una **excepción declarada** al estimador primario de INV-14/D-03, que se definió para eventos.
  La media por bloque (por año natural) se publica como descriptiva y no veta ni rescata (T-022 §16).
- **Fuente B de FX:** tipos de referencia del BCE para USD, JPY y HKD, con `timestamp_available` a las
  17:00 Europe/Berlin del día de referencia, el último tipo causal en los festivos TARGET y
  `fx_rate = 1/rate` (T-022 §11.1). Fallo de integridad de A = cualquier barra que falte o sobre, o
  cualquier cadena distinta, en las 1.300 marcas de `EURUSD=X` de la cosecha, sobre una **petición fija**
  (`start = 2021-08-27`, `end = 2026-08-29`, `interval = 1d`, `auto_adjust = False`,
  `actions = True`, versión registrada). El paso a B no abre OD.
- **RR en el score:** los 15 puntos de B2 frente a 10 en S2 y C0 valen **con el stop de volatilidad**;
  con la regla E, un stop de soporte más ajustado puede dar más puntos a cualquiera.
- **Predicado OPERAR:** broker neutral (D-04), `setup_radar = OPERAR` y `setup_accion = COMPRAR`.
- **Benchmark:** la comisión va dentro del importe asignado (1/90, o el dividendo reinvertido).
- **Dividendos de Xetra en otra divisa:** Yahoo los convierte a un tipo constante (comprobado en
  R6C0.DE); limitación declarada que afecta igual a las políticas y al benchmark.
- **Correcciones posteriores de métricas:** solo de errores de implementación; un cambio de
  definición exige una D-nn y nunca cambia la salida.

### D-70 — 2026-10-05 — Resultado de P6 y GATE P6 cruzado: salida `[]`
Decisión del propietario. Registra el resultado de la **ejecución confirmatoria única** de P6 (T-022,
A-06), que acepta como válida y consumida, y cierra GATE P6. Se transcribe la salida de
`evidence/2026-10-03-T-022-p6/run/` sin recalcular nada; el detalle está en
`evidence/2026-10-05-T-022-p6-cierre/resultado-p6.md`.
_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

**Identidad.**
- `P6_PREREG_SHA = 03f04a42ea9d2be893e7c4cc09de76bd1c55778b`
- `P6_CODE_SHA = bc0636d4320b38ef5a620fa9ae94cee35df47580`
- `P6_RUN_HEAD_SHA = 353876d39d03f6849847743b9f4e7f791abbed30`: archiva el preflight definitivo sobre
  `bc0636d`; respecto a `bc0636d` solo añade evidencia.
- `P6_RUN_EVIDENCE_SHA = 0771989af851748463aa0e79d4a7dc327066ca5f`
- `P6_DATA_ID = 572e09141dbfe0fc9c53a7b529f1abcff46e16027fe9b47d1f3e26330c1e5383`
- Marca creada el 2026-10-05 a las 10:11:49 UTC, antes de abrir ningún desenlace. Hashea
  `apertura-payload.json` (`7823fe8dc2634a0f4d6271399511d5d0d62b3a5da49c61106be6210a12dc8a7e`), y su
  sha256 (`7a05c3b80d42765bf8d7e272a7afa4419ab15aaf8611e3e15e2e9d3182a07463`) es el `token_sha256` del
  resultado.
- Completó por la ruta normal: `p6-resultado.json` y `p6-resumen.md` íntegros, ningún `p6-parada.json`
  y `código de salida: 0` en la consola.

**Decisiones.**
1. **P6 se ejecutó exactamente una vez** y no se repite.
2. **B2 recibe `NO PASA`** y **S2 recibe `NO PASA`**.
3. **Salida de P6 = `[]`.**
4. **La causa formal es exclusivamente `excess_CAGR_pp <= 0`.** Las dos cumplen `N_closed >= 100`,
   `profit_factor_local > 1`, `mean_R_local > 0` y `max_drawdown >= -25 %`; solo falla la quinta
   condición de T-022 §16.
5. **No se reinterpretan** la sensibilidad de 10 pb, el puente de todas las barras, C0, la
   exposición, el cash, los subperiodos ni ningún diagnóstico de ocupación. Son descriptivos (T-022
   §16) y no pueden rescatar ni cambiar la salida.
6. **No se retoca ninguna candidata** usando estos resultados.
7. **Producción continúa exactamente igual:** `config.yaml` en `"1.0"` con C0, Score v1 70/60, Score v2
   inactivo y la Pi en `v0.4.1`. No hay release ni despliegue.
8. **GATE P6 se cruza** porque todos sus requisitos metodológicos y de evidencia están cumplidos
   (`evidence/2026-10-05-T-022-p6-cierre/gate-p6-final.md`). El gate exige la medición completa y
   reproducible, no un resultado favorable.
9. **P7 queda sin candidata admisible**, y por tanto **A-07 permanece BLOQUEADO**.
10. **Cualquier intento futuro** de corregir la selección de señales, la prioridad, el sizing, la
    utilización del cash, la geometría o el benchmark constituye **investigación nueva**, con ficha y
    pre-registro nuevos, y **no cambia la etiqueta original de P6**.

**Valores vinculantes (corridas primarias a 5 pb).**

| | N_closed | PF local | mean_R_local | Max DD | CAGR | excess_CAGR_pp | Etiqueta |
|---|---|---|---|---|---|---|---|
| B2 | 673 | 1,3995145381 | 0,2477734148 | −16,5959 % | 18,0349 % | −15,7671 | **NO PASA** |
| S2 | 528 | 1,4043635462 | 0,2383023780 | −11,2259 % | 15,0793 % | −18,7228 | **NO PASA** |

Benchmark de comprar y mantener del propio universo, a pesos iguales y 5 pb: CAGR 33,8021 %, max DD
−26,2249 %.

**Descriptivo, sin efecto en la salida:**
- C0: N 623, PF 1,2468, mean_R 0,1637, max DD −11,1428 %, CAGR 9,8883 %, exceso −23,9138 pp;
- sensibilidad de 10 pb: B2 −15,3041 pp y S2 −20,0919 pp de exceso;
- puente de todas las barras: B2 −9,5165 pp y S2 −5,5714 pp de exceso.

**Conciliación contable:** cuadra en las 9 corridas (efectivo encadenado fila a fila y
V_T − V_0 = Σ pnl_neto_EUR = Σ bruto + dividendos − comisiones).

**Revisión final independiente:** 0 BLOCKER, 0 IMPORTANTE y 0 MENOR (`evidence/2026-10-05-T-022-p6-cierre/revision-final.md`).

**A-06 / T-022 queda ACEPTADA — GATE P6 CRUZADO.** El resultado es de desarrollo sobre una cosecha ya
consumida (INV-15); el buy-and-hold del mismo universo mitiga la interpretación, pero no corrige el sesgo
de universo.

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

### OD-02 bis — ¿Hace falta además una segunda fuente de precios? · ABIERTA desde el 2026-09-25
- **Por qué existe:** D-40 cerró OD-02 con la lectura (c) y D-41 puso la caché
  primero, porque el fallo dominante era que el proveedor **retiraba una barra
  que ya había servido**. Eso lo resuelve T-018 sin pagar nada. Lo que queda por
  medir es el resto: las sesiones que **nadie ha visto nunca**.
- **Pregunta:** ¿se contrata una segunda fuente de precios europea, sabiendo que
  la caché ya cubre las barras retiradas?
- **La cifra que la decide** la produce T-018 y se publica en cada informe y en
  `frescura-historico`: `sesión exigible + nunca observada antes + no entregada`,
  contada **una vez por activo y sesión** (deduplicada, como exige D-40).
- **Estado:** la caché ya está implementada y la cifra ya se persiste. **No se
  decide hasta tener varias semanas de datos de la Pi**: una sola pasada no
  distingue un fallo puntual del proveedor de un hueco estructural.
- **Bloquea:** nada. La ficha de proveedor (B-00) solo se activa si la respuesta
  es sí.
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

### OD-11 — ¿Sale el RR del score? · **CERRADA el 2026-09-21 en D-43**
- **Pregunta:** el ratio beneficio/riesgo pesa 20 de 100 puntos en
  `compute_score`. A la vista de la ablación rehecha, ¿se mantiene como
  dimensión, se retira del score, o se sustituye por otra formulación?
- **Lo que se ha medido** (T-013, población vigente de 93 activos, cosecha
  `071ddb2b…`, horizonte swing, 106.363 señales, cero descartes, sin pasar por
  `classify()`):

      Banda   n       mediana RR puntos  mediana contrib.  RR bruto  RR neto
      <50     45.574        10,000            +2,500        1,500    1,472
      50-60   38.828        10,000            −1,583        1,500    1,461
      60-70   19.702        10,000            −4,167        1,500    1,454
      70-80    2.194        10,000            −7,292        1,500    1,458
      80+         65        10,000           −10,333        1,500    1,463

  La dimensión reparte **10 de sus 20 puntos a casi todo el mundo** y el RR
  bruto vale **1,500 en la mediana de las cinco bandas**. La contribución cae
  monótonamente de +2,500 a −10,333: es **aritmética de normalización, no
  información sobre el activo**. El hallazgo de agosto se reproduce entero sobre
  la población nueva, así que no era un artefacto de los 107.
  Al quitarlo, `70-80` pasa de 2.194 a 6.443 señales y `80+` de 65 a 1.032.
- **Alternativas:** (a) retirar el RR del score y recalibrar los umbrales en P3
  sobre la nota normalizada sobre 60; (b) mantenerlo como está; (c) mantener la
  dimensión pero redefinirla para que discrimine —hoy no puede, porque con
  `target2_structural: false` el ratio vale 1,5 salvo que un soporte cercano
  acerque el stop—.
- **Consecuencia:** (a) el score cambia de escala y **todos** los umbrales
  quedan sin calibrar hasta P3; obliga a `score_model_version` nuevo y las
  recomendaciones persistidas dejan de ser comparables sin etiqueta. (b) se
  sigue diluyendo la nota hacia el centro y `80+` sigue siendo una banda de 65
  señales que no calibra nada. (c) es trabajo de P4, no de P3, porque toca la
  geometría.
- **Recomendación técnica:** (a), pero **no ahora**: retirarlo es un cambio de
  escala del score y debe entrar junto con la recalibración de P3, no antes, o
  quedan umbrales heredados sobre una escala que ya no existe. Lo que sí
  conviene decidir ya es **si P3 arranca con el RR dentro o fuera**, porque eso
  cambia lo que P3 calibra.
- **Aviso que condiciona la lectura:** con el estimador primario de INV-14
  **ninguna banda es concluyente** (ver GATE P2). Esta decisión no puede
  apoyarse en que una banda rinda más que otra, porque eso no se ha medido con
  resolución suficiente. Lo que sí está medido, y con firmeza, es que la
  dimensión **es casi constante**, y eso no depende de la resolución.
- **Bloquea:** A-03 (P3, score v2). No bloquea nada más.
- **Respuesta del propietario, 2026-09-21:** el RR **sale del score como
  dimensión de puntuación**. Registrada en **D-43**, que es el texto que manda.

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
