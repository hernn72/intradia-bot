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
Hasta que C-03 automatice el despliegue por tag, el propietario ejecuta en la
Pi: `git fetch && git checkout <tag> && pip install -r requirements.txt &&
python -m pytest -q && python -m advisor.main verificar-systemd`.
