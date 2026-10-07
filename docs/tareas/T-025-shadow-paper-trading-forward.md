# T-025 — Shadow/Paper Trading Forward diario: B2 y S2 operando en el tiempo, sin dinero real (S-01)

Estado: **PRE-REGISTRO PROPUESTO, OD CERRADAS, SIN CONGELAR.** El propietario cerró OD-T25-1 a
OD-T25-9 (§17, D-75) y OD-12 (D-77) el 2026-10-07, y declaró la visibilidad parcial ex ante de T-024
(D-76). Falta su revisión final del PR y la congelación de `T025_PREREG_SHA`; la implementación
necesita autorización aparte. No hay código, ni tablas, ni paper broker. No se ha descargado ningún
dato forward ni observado ningún desenlace. B2, S2 y C0 no cambian. La Pi no se ha tocado.

Agente: Opus (diseño) → revisión independiente → propietario (OD) → revisión final → congelación.
Línea / fase: S-01 (línea S, velocidad «bot», D-73).
Gate al que contribuye: ninguno formal. **No desbloquea P7**, no es P10 y no valida B2 ni S2.
Prepara la infraestructura que P10 (V-01) y el Superbot (S-03) necesitan.

**Etiqueta obligatoria de toda salida de T-025:**
**«SHADOW / PAPER — estrategia en investigación, no validada para capital real».**

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

---

## 0. Identidad de partida

| | |
|---|---|
| Base | `main = f80ab2876f7a7cc2e001b285e66fa061c0d7a8dc` (merge normal del PR #47, 2026-10-07, que solo cambió `docs/roadmap.md`). La rama nació de `0918cb3`, la cabeza del PR #47, que es ancestro de ese merge |
| Decisiones | D-70 (P6 `[]`), D-71 y D-72 (T-024), **D-73** (reorientación y sellado de T-025), **D-74** (apertura de T-025), **D-75** (cierre de OD-T25-1..9), **D-76** (visibilidad parcial ex ante de T-024), **D-77** (OD-12: línea `t024/forward`) |
| Políticas | `evidence/2026-10-03-T-021-p5-cierre/politicas-finales.json` (`sha256 fa027058…9fd9f6b`; esquema `intradia.p5.politicas_finales.v1`; `p5_prereg_sha a7c3d238…`) |
| B2 | `policy_sha256 d5d6a533fe846a6ebb5d5c8e313c84f2a5b4e04095d08386e5d903dce73101b9`; `advisor_config_hash c5d60f44e89a754f34dfc685cda5073af1c0f9dbb04ab3ec14a813d423f81760`; sistema P6 primario `system_sha256 010977688a180cc63d22111f2dcb520c937ba39bb63fbb88082c30a061724026` |
| S2 | `policy_sha256 e37ee93363dbbd7c58cae74bba4391ab9ad41dd1f3ed55804a92efb531e44d11`; `advisor_config_hash 8a151b80d91bf73e431ec38e5e21f22268783bbd0a26d5f72e6ef8887aca0dbb`; `system_sha256 824a1dff2d1bf1e6d89b842b9606887cec5eed28f3b76448f947dfbb28d39a69` |
| C0 (control) | `policy_sha256 80e21111a88c1eeac94c2ecef6b8bc480a505a045ca90f6a91a0ba6fc4ffd29a`; `advisor_config_hash 89406d28c7b4b6e6c4f032cd63b6868c927af3e926dfb52d430dfa6654d06387`; `system_sha256 18956fb61823c4cfbf625b1581ef15f6048a1096134d50c00404f76b12fd99e8` |
| Contrato del sistema | El de P6 (`docs/tareas/T-022-p6-sistema-completo.md` §7–§19, D-69), `P6_PREREG_SHA 03f04a42…`, `P6_CODE_SHA bc0636d4…`; hashes en `evidence/2026-10-03-T-022-p6/preflight/system-hashes.json` |
| Universo | El de P6: 90 activos, `asset_list_sha256 36355796a57e55a68ea16957b7edc6975360fb2085e7fd91841d20e2d7812f50`, `universe_vintage_id 237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19` |
| T-024 | `T024_PREREG_SHA dfcca0ef3428df916089480a0ca574f47e550c24`, `T024_CODE_SHA 1a697c3fa2ab76ddfcf567c2ef3f5ab56492eaf0`. `EXECUTOR_PATHS` de `main` (`f80ab28`) idénticos a `1a697c3` (comprobado con `git diff --quiet` el 2026-10-07). Desde D-77 T-024 vive en su propia línea `t024/forward` (§3.8) |
| Pi | **Entorno de desarrollo/integración, no producción** (D-74). Tag `v0.4.1 = 8b2dddb`, esquema v7, C0 con Score v1 70/60. Worktree de T-024 aparte (`/home/fer/intradia-t024`) |
| Línea base | `pytest -q`: 1430 pasan y 20 se saltan; `ruff check .` y `mypy advisor` limpios (79 ficheros). Ejecutado el 2026-10-06 sobre `0918cb3` |

## 1. Propósito

Que B2 y S2 generen **operaciones paper forward reales en el tiempo**, una vez al día, con reglas
congeladas antes de conocer ningún desenlace:

`análisis diario → recomendación → orden simulada → ejecución simulada → cartera paper → seguimiento → cierre → resultado`

T-025 hace funcionar el bot como el sistema futuro, pero sin dinero real. Su producto es un
**registro auditable**. No es una medición confirmatoria.

## 2. Qué no hace

- No demuestra alfa ni ventaja. No tiene criterio de aceptación estadístico ni veredicto `PASA`.
- No modifica P6 ni lo reinterpreta: B2 `NO PASA`, S2 `NO PASA`, salida `[]` (D-70).
- **No desbloquea P7** ni aparece como sustituto de P7, y tampoco T-024 lo es. P7 solo recibe una
  candidata de P6-bis (A-11) que haya pasado la evaluación de cartera previa (D-73).
- No es P10: P10 exige la política, la cartera y el riesgo finales con un tag congelado (GATE P10).
  T-025 construye el registro que P10 usará.
- No cambia B2, S2 ni C0, ni su geometría, score, umbrales, sizing o costes.
- No toca T-024: ni su pre-registro, ni su código, ni sus `EXECUTOR_PATHS`, ni la línea
  `t024/forward`, ni el worktree de la Pi, ni sus cosechas, ni sus conteos. Sí cambia lo que el
  propietario ve durante T-024: la información ex ante de B2, S2 y C0 (§10, D-76).
- No reutiliza la tabla `position` ni el seguimiento manual (§4).
- No mueve dinero real ni envía órdenes a ningún broker.

## 3. Inventario: qué existe y qué falta

Leído en el código el 2026-10-06; cada afirmación cita su fuente.

### 3.1 `position` y `position_review` (posiciones manuales): no se reutilizan

`advisor/storage/db.py` (`_SCHEMA`, `open_position`, `close_position`, `list_open_positions`):
- `position` registra **posiciones abiertas a mano en Trade Republic**, con una tesis en texto libre.
  No tiene `run_id`, política, cohorte, hash de política, señal de origen, unidades por riesgo, cash ni
  equity.
- **Es mutable:** `close_position` hace `UPDATE … SET status='CLOSED', exit_price…` sobre la misma
  fila. Un paper broker que reescribe la fila de apertura no deja una historia auditable.
- **Una sola posición abierta por símbolo en toda la base** (`get_open_position(symbol)` y el
  `ValueError` de `open_position`). B2 y S2 pueden tener a la vez el mismo activo en libros
  distintos, y además convivirían con la posición real del propietario.
- `list_open_positions` alimenta `seguimiento` (`advisor/report/tracking.py:116`), que revisa cada
  posición contra su tesis y la envía por **Telegram** como cartera real. Una fila paper aparecería
  ahí como si fuera dinero del propietario.
- `position_review.run_id` existe desde la migración v7, pero solo para las revisiones manuales.

Conclusión: extender `position` exigiría añadir una columna de tipo de libro, cambiar la unicidad, las
consultas de `seguimiento`, `posiciones`, `abrir` y `cerrar` y la semántica de cierre. Cualquier
consulta antigua o futura que olvidara el filtro mezclaría paper y real. **La separación se hace por
construcción, no por filtro** (§4).

### 3.2 `recommendation` y `analysis_run`: se enlazan, no se amplían

- `recommendation` guarda por pasada y activo: `run_id`, `created_at`, `symbol`, `isin`,
  `trade_republic`, `currency`, `horizonte`, `radar`, `accion`, `score`, `price`, `entry_max`, `stop`,
  `target2`, `risk_pct`, `reward_pct`, `rr_ratio`, `reasons`, `discard_code`, `execution_code`,
  calidad del dato por dimensiones, `execution_ready` y `warnings`.
- Son filas de **C0 con el contexto `legacy_v1`** (`context_mode_for("1.0")`) y el predicado con
  broker. **No** son señales de B2 ni de S2, no llevan `target1` ni `target3`, ni la política, el
  `policy_sha256`, el `instrument_id` o el contexto point-in-time.
- `analysis_run` (manifiesto, `advisor/run/manifest.py::RunManifest`) ya tiene `run_id`, `git_sha`,
  `git_dirty`, `release_tag`, `config_hash` y su versión, `universe_vintage_id`, `groups`,
  `data_vintage_id`, `score_model_version`, `scoring_contract_json`, `context_model_version`,
  `schema_version`, `analysis_timestamp`, `environment`, `python_version`, `provider_versions` y el
  estado del reloj.
- **Uso en T-025:** cada señal paper apunta al `run_id` de la pasada cuyos datos usó
  (`source_run_id`). Si existe una fila `recommendation` del mismo `run_id` y activo, se guarda su `id`
  como enlace **descriptivo**: nunca decide nada.

### 3.3 Base de precios: la caché C-09 **no** sirve como fuente (corregido en la revisión)

Hay dos caminos de precios, y **tienen bases de ajuste distintas**:
- **Informe de la Pi y caché C-09.**
  - `MarketDataProvider.get_history` (`advisor/data/market_data.py:83`) llama a
    `ticker.history(period, interval)` con el `auto_adjust` por defecto de `yfinance` (`True`), así
    que el OHLC está ajustado **por dividendos y splits**.
  - `CachedBarProvider.get_history` (`advisor/data/bar_cache.py:267`) envuelve ese camino. Reancla la
    caché en cada reajuste de la serie, «dividendo o split» (`bar_cache.py:69`), y no guarda dividendos
    ni splits (`bar_cache.py:915-921`).
- **P6 y T-024.**
  - `execution_prices` = `signal_prices` con `auto_adjust=False`: el OHLC está ajustado **solo por
    splits** y conserva el hueco ex-dividendo.
  - El dividendo se abona aparte desde `raw["Dividends"]` (`advisor/research/p6.py:599-610`; T-022
    §10.1).
  - T-024 exige `auto_adjust=False` y `actions=True` en su petición.
  - El camino vivo equivalente es `MarketDataProvider.get_raw_history`.

**Regla de T-025:**
- Señales, niveles, entradas, salidas y valoración usan **la misma base que P6**: OHLC de
  `get_raw_history` (`auto_adjust=False`, `actions=True`), con `Dividends` y `Stock Splits`.
- T-025 lo guarda en su propio almacén (§5) con la primera observación como vigente.
- **Vista de señal ajustada por splits (ronda 2).** `yfinance` reajusta hacia atrás la serie cruda
  cuando hay un split (`market_data.py:109-110`), mientras que las barras guardadas no se reescriben.
  Si se usaran tal cual, la serie mezclaría dos escalas: SMA200 partida, ATR disparado y niveles
  falsos. Por eso la serie que recibe `build_snapshot_series` es una **vista derivada**, sin reescribir
  ninguna fila: cada barra vigente se divide por el producto de los ratios de los `SPLIT` observados
  con fecha ex posterior a su sesión. Es la misma vista ajustada por todos los splits conocidos con la
  que P6 calculaba (`signal_prices`, T-022 §10.5). Las fills y salidas usan las barras de la escala
  vigente en su sesión, coherentes con las unidades tras `SPLIT_ADJUST` (§8.6).
- **Contexto point-in-time en la misma base.** El contexto (VIX, `^STOXX50E` y Asia) se calcula con
  `PointInTimeContextResolver` sobre cierres de `get_raw_history` guardados en
  `paper_context_observation`, como P6 (`p4.py:536-542`). **Nunca** con
  `fetch_point_in_time_market_context`, que descarga con `get_history`, ajustado por dividendos
  (`advisor/context/point_in_time.py:171-189`): la variación asiática cambiaría en las fechas ex, y con
  ella el score.
- La caché `validated_bar` de `intradia.db` **no** se usa como fuente. Mezclarla contaría el dividendo
  dos veces (dentro de la serie ajustada y como abono) y convertiría cada reanclaje por dividendo en un
  falso split.
- Consecuencia declarada: los niveles de T-025 no coinciden con los del informe de C0 de la Pi, que
  usa la serie ajustada por dividendos. El enlace con `recommendation` es solo descriptivo (§3.2).
- Si algún día hace falta otra fuente, eso es una OD nueva.

### 3.4 Simulador de P6: misma semántica, pero no se puede llamar en vivo

`advisor/research/p6_sim.py` es el motor puro de P6: ledger por eventos, fases
`OPEN_EXIT < OPEN_ENTRY < CLOSE_EXIT < CLOSE_DIVIDEND < CLOSE_VALUATION < SIGNAL`, desempate
`tiebreak_key`, sizing sobre equity causal, identidades contables y métricas (`path_metrics`,
`trade_metrics`, `exposure_metrics`).
- Es **por lotes** (`simulate`): recibe toda la serie de una vez. T-025 es **incremental**: procesa los
  eventos según llegan las barras.
- **Se niega a abrir datos reales** sin el token confirmatorio de P6 (`_require_live_confirmatory`,
  `P6OutcomeGateError`).
- Por eso T-025 necesita un motor incremental propio que reproduzca la semántica de P6. Su prueba de
  fidelidad es un **test de equivalencia**: el flujo de eventos de T-025, rehecho sobre datos
  sintéticos con `p6_sim.simulate`, tiene que dar el mismo ledger fila a fila (§14).

### 3.5 Sizing, señal y contexto

- `advisor/analysis/sizing.py::calculate_position_sizing` da porcentajes. El sizing monetario de P6
  (unidades sobre la equity causal) está en `p6_sim`.
- La población de P6 es `OPERAR_score_v1_point_in_time`: Score v1 70/60 `calibrated: false`, broker
  neutral (D-04) y contexto **point-in-time** explícito (`resolve_context_mode("1.0",
  "point_in_time")`). El camino del informe usa `legacy_v1`. T-025 tiene que usar el contexto de P6,
  no el del informe.
- `signal_id` = `advisor/research/observations.py::stable_signal_id(asset, "swing", timestamp)`, el
  mismo identificador común a todas las políticas que usa el desempate de P6.

### 3.6 FX

`advisor/data/fx.py::FxConverter` es **solo de presentación** (lo dice su docstring): toma el último
cierre del par y no sirve para contabilidad. T-025 necesita su propio registro FX causal, con la regla
A de P6 (OD-P6-16): el último cierre de `EURxxx=X` con `timestamp_available = marca + 24 h < τ` y
`fx_rate = 1 / rate`.

### 3.7 Pasadas en la Pi

`deploy/systemd/intradia-bot.timer`: `analizar --horizonte swing --telegram` de lunes a viernes a las
07:00, 08:30, 14:30 y 21:00 (hora de la Pi, que en Canarias coincide con la de Londres; D-50 las fija
en Europe/London). Hay además una pasada por evento a las 22:30. Desde ella no se escribe nada paper.

### 3.8 Interacción con la identidad de T-024 (crítica)

`advisor/research/p4.py::EXECUTOR_PATHS = ("advisor", "config.yaml", "universe.yaml",
"exchange_overrides.yaml", "pyproject.toml", "requirements.txt")`.
`t024_decision.verificar_identidad()` exige `git diff --quiet 1a697c3 HEAD -- EXECUTOR_PATHS` y un
árbol limpio. La fase B de T-024 en el PC (`t024_forward registrar` y `capturar`) la llama, y la fase A
de la Pi la exige antes de descargar.

**Consecuencia:** cualquier commit que toque cualquiera de las seis rutas (`advisor/`, `config.yaml`,
`universe.yaml`, `exchange_overrides.yaml`, `pyproject.toml` o `requirements.txt`) deja de servir para
operar T-024. **Esta entrega no toca ningún `EXECUTOR_PATHS`.**

**OD-12 cerrada (D-77): T-024 tiene una línea Git dedicada y congelada, `t024/forward`.**
- `main` queda libre para evolucionar (T-025, P6-bis, C-04, C-05…) y **no** está obligado a seguir
  siendo compatible con T-024.
- T-024 se opera solo desde `t024/forward`, que conserva vacío
  `git diff --quiet 1a697c3 HEAD -- <EXECUTOR_PATHS>`. El contrato, el procedimiento de creación y el
  plan del calendario de diciembre están en D-77.
- **Orden obligatorio:** la línea se crea (en GitHub, desde el último commit compatible) **antes** de
  fusionar en `main` el primer cambio en los `EXECUTOR_PATHS`. Así el «último commit compatible» queda
  fijado sin ambigüedad.
- T-025 sigue fuera de `advisor/` por la arquitectura (OD-T25-1), no por T-024. Si alguna vez necesita
  que `advisor` exponga algo nuevo, ese cambio puede ir a `main` una vez creada `t024/forward`, siempre
  que no cambie B2, S2 ni C0 (sus `policy_sha256`, `advisor_config_hash` y `system_sha256` de §0 se
  regeneran byte a byte) y que abra una cohorte nueva si cambia el motor de una existente (§13).

### 3.9 Qué falta

No hay en el repositorio: libro paper, orden paper, fill, posición paper, ledger de cash de cartera
en vivo, instantáneas de equity en vivo, desenlaces forward, sellado, registro de consumo ni
benchmark forward. Todo eso es persistencia nueva (§5).

## 4. Decisión arquitectónica: separar lo real de lo paper (OD-T25-1, cerrada en D-75)

**Decisión del propietario: arquitectura separada.** Una base SQLite propia y un código fuera de
`advisor/`. La separación entre posiciones reales/manuales y paper es **por construcción, no por
filtros**. No se reutilizan `position` ni `position_review`.

| | Real/manual (hoy) | Shadow/paper (T-025) |
|---|---|---|
| Base | `intradia.db` (`AdvisorDB`, esquema v7) | **`paper.db`, fichero aparte**, con sus propias migraciones y su `PRAGMA user_version` |
| Marca del fichero | — | `PRAGMA application_id` propio; el código paper se niega a abrir una base sin esa marca, y por tanto nunca abre `intradia.db` |
| Código | `advisor/` | **paquete `paper/` en la raíz**, fuera de los `EXECUTOR_PATHS`. Solo **lee** `advisor` a través de funciones públicas y no lo modifica |
| Comandos | `abrir`, `cerrar`, `posiciones`, `seguimiento` | comandos propios (`python -m paper …`). Ninguno de los actuales lee `paper.db` |
| Telegram | informe y seguimiento reales | mensaje propio, con la etiqueta SHADOW/PAPER en la primera línea |
| Semántica | mutable, una posición por símbolo | append-only, una posición por **(cohorte, activo)** |

Por qué:
1. **Separación por construcción.** Ninguna consulta existente sobre `position` puede devolver una
   fila paper, porque esas filas no están en la misma base. Un olvido de filtro no las mezcla.
2. **Sin tocar el ejecutor de B2, S2 y C0.** Un paquete fuera de `advisor/` y sin tocar
   `config.yaml` no puede cambiar las políticas por accidente. (La identidad de T-024 ya no depende de
   esto: vive en `t024/forward`, D-77.)
3. **Sin migración de la base de la Pi.** `intradia.db` sigue en v7: no hay migración irreversible
   (D-32) ni copia previa que coordinar.
4. **Reconstrucción.** `paper.db` contiene todo lo que T-025 usó: barras en la base de P6, acciones
   corporativas, FX, contexto, señales y decisiones. Una operación se reconstruye sin leer
   `intradia.db`.

Costes declarados:
- **INV-06** (una función, varios llamantes): `paper/` llama a `build_snapshot_series`, a la
  configuración de las políticas y a los niveles de `advisor` y **no los copia**. Si necesita algo que
  `advisor` no expone, se cambia `advisor` en `main` con las condiciones de §3.8.
- **El motor de una cohorte incluye el `advisor` que importa.** Como `main` puede cambiar `advisor/`
  (D-77), congelar solo `paper/engine_vN` no basta: la identidad de una cohorte es un commit completo
  (§13).
- La CI tiene que ejecutar también `mypy paper` y los tests de `paper/`. Se cambia
  `.github/workflows/ci.yml`, que no está en los `EXECUTOR_PATHS`.
- No hay claves foráneas entre bases. `source_run_id` y `source_recommendation_id` son referencias
  verificadas por el código (existencia y hash de la fila), no restricciones de SQLite.

Alternativa B (tablas `paper_*` en `intradia.db`, migración v8 y código en `advisor/`): **descartada
por el propietario** (D-75). La separación sería solo por nombre de tabla y obligaría a migrar la base
de la Pi.

## 5. Contrato de persistencia (para la tarea de implementación; nada se crea ahora)

Reglas generales:
- **Append-only:** ninguna fila de hechos se actualiza ni se borra. Unos triggers `BEFORE UPDATE` y
  `BEFORE DELETE` con `RAISE(ABORT)` lo garantizan en las tablas de hechos. Lo derivado (estado
  actual, vistas) se reconstruye desde los hechos.
- Toda fila de hechos lleva `cohort_id`, `paper_run_id`, `computed_at` (hora de reloj en que se
  escribió) y, si es un evento económico, `event_ts_utc` (el instante τ que representa) y `phase`.
- **Contenido económico frente a metadatos:** cada fila tiene un `content_sha256` calculado **solo**
  sobre sus campos económicos, sin `paper_run_id`, `computed_at` ni `observed_at` de la ejecución. La
  idempotencia (§12) compara ese hash, no la fila entera.
- Los precios se guardan en divisa local y en EUR (`*_local`, `*_eur`), con el FX y su
  `fx_timestamp_available`.
- Los booleanos y los estados son textos de lista cerrada con `CHECK`.

| Tabla | Una fila por | Campos mínimos | Unicidad / idempotencia |
|---|---|---|---|
| `paper_cohort` | libro (B2, S2, C0, BH) y versión | `cohort_id`, `book_kind = 'PAPER'` (CHECK), `policy_id`, `policy_sha256`, `advisor_config_hash`, `p6_system_sha256` de referencia, `t025_system_sha256` (§13), `engine_version`, `t025_prereg_sha`, `t025_code_sha` (commit completo que la ejecuta, §13), `release_tag`, `capital_inicial_eur` (= 100.000, D-75), `base_currency`, `asset_list_sha256`, `universe_vintage_id`, `start_session_rule`, `start_ts_utc`, `seal_rule` (embargo T-024 y ventanas P7, §10), `label`, `created_at` | `cohort_id` = sha256 canónico de su contrato |
| `paper_cohort_event` | cambio de estado de una cohorte | `cohort_id`, `state` (`ACTIVE`, `CLOSING`, `CLOSED`, `ABORTED_INVALID_ENGINE`), `event_ts_utc`, `reason`, `decision_ref` (D-nn) | `(cohort_id, state)`. El estado vigente es el último; un `ABORTED_INVALID_ENGINE` es terminal (§13). Visible |
| `paper_run` | ejecución de T-025 | `paper_run_id`, `source_run_id` (pasada de `intradia.db`), manifiesto completo (como `RunManifest`), `paper_schema_version`, `engine_version`, `started_at`, `finished_at`, `status` (lista cerrada y genérica: `OK`, `ERROR`, `IDENTITY_MISMATCH`, `LOCKED`), `inputs_sha256` | `paper_run_id`. El diagnóstico detallado de un error que dependa de un libro va a `paper_run_diagnostic`, sellada (§10) |
| `paper_run_diagnostic` | detalle de un fallo o una espera de un libro | `paper_run_id`, `cohort_id`, `code` (`ERROR_DIVERGENCIA`, identidad contable, FX ausente para un evento…), `detail_json` | `(paper_run_id, cohort_id, code)`. **Sellada** en una cohorte sellada |
| `paper_cohort_progress` | (cohorte, ejecución) | `frontier_ts_utc`, `stalled_on` (activos que bloquean la frontera), recuentos de `late`, `DATA_GAP`, `SCALE_MISMATCH` y `DATA_LOSS_SUSPENDED` | `(cohort_id, paper_run_id)`. **Sellada** en una cohorte sellada: la frontera y los bloqueos delatan qué posiciones hay |
| `paper_data_alert` | aviso operativo **a nivel de dato**, nunca de libro | `data_symbol` o `fx_pair` o serie de contexto, `kind` (`BAR_MISSING`, `ENTRY_BAR_DECLARED_MISSING`, `NO_DATA_20_SESSIONS`, `DATA_RESUMED`, `FX_MISSING`, `SCALE_CHANGE_UNEXPLAINED`, `LATE_BAR`, `LATE_DIVIDEND`), `session_date`, `detected_at` | `(objeto, kind, session_date)`. Se calcula para **todo** el universo, haya o no posición u orden, así que no delata ningún libro. Visible (§10) |
| `paper_bar_observation` | barra de sesión cerrada usada | `data_symbol`, `market`, `session_date`, `bar_timestamp` crudo (INV-13), OHLCV de `get_raw_history` (`auto_adjust=False`), `observed_at`, `provider`, `provider_version`, `request` (`start`/`end` o `period`), `scale_anchor` | `(data_symbol, session_date, observed_at)`; la vigente para una sesión es la primera observada |
| `paper_corporate_action` | dividendo, split o evento terminal observado | `data_symbol`, `kind` (`DIVIDEND`/`SPLIT`/`TERMINAL`), `ex_date` (o fecha efectiva), `amount` (dividendo por acción, en la divisa de cotización y en la base de la serie; o precio de liquidación por acción de un `TERMINAL`) o `ratio` (split), `currency`, `observed_at`, `provider`; para `TERMINAL`, además `terminal_kind` (`DELISTING_CASH`, `LIQUIDATION`, `CASH_MERGER`), `source_url`, `source_sha256` y `decision_ref` (§8.7) | `(data_symbol, kind, ex_date)`; manda la primera observación, y una distinta posterior se registra en `paper_corporate_action_revision` sin cambiar nada. Es un hecho **del activo**, no de un libro: visible |
| `paper_bar_rescale` | cambio de escala detectado en la serie | `data_symbol`, `factor`, `effective_session`, `explained_by` (`SPLIT` con su id, o `UNEXPLAINED`), `detected_at` | `(data_symbol, effective_session)` |
| `paper_fx_quote` | barra FX usada | `fx_pair`, `bar_timestamp`, `timestamp_available` (= marca + 24 h), `rate`, `provider`, `observed_at` | `(fx_pair, bar_timestamp)`; manda la primera observada |
| `paper_context_observation` | cierre de contexto usado | serie (`^VIX`, `^STOXX50E`, Asia), marca, cierre de `get_raw_history` (`auto_adjust=False`), `observed_at`, `provider` | `(serie, marca)`; manda la primera observada |
| `paper_signal_evaluation` | (cohorte, activo, sesión `t`, pasada) | `signal_id` (`stable_signal_id`), `instrument_id`, `symbol`, `data_symbol`, `market`, `signal_session_date`, `pass_scheduled_ts`, `analysis_timestamp`, `bar_t_observation_id`, `reference_price` (cierre de `t`), `entry_max`, `stop`, `target1`, `target2`, `target3`, `rr_at_reference`, `risk_fraction`, `score`, `score_model_version`, `setup_radar`, `setup_accion`, `operar` (sí/no), `context_snapshot_json`, `data_quality` y frescura, `reasons`, `input_observation_ids`, `analysis_timestamp` (hora programada, PIT), `decision_ts` (fin de la ejecución original, < apertura), `max_input_observed_at` (≤ `decision_ts`; ver §7.1), `source_recommendation_id` (solo enlace) | `(cohort_id, signal_id, pass_scheduled_ts)` y `(cohort_id, instrument_id, signal_session_date, pass_scheduled_ts)` |
| `paper_open_check` | señal vinculante OPERAR, **por política y sin depender del libro** | `policy_id`, `signal_id`, `instrument_id`, `signal_session_date`, `entry_session`, `bar_observation_id`, `open_market`, `entry_effective`, `check` (`PASS` o `DATA_NOT_EXECUTABLE`/`INVALID_STOP`/`INVALID_TARGET`/`ABOVE_MAX_ENTRY`/`RR_TOO_LOW`), `requested_weight` (tamaño solicitado como fracción de la equity: `min(0,005 · entry_effective / (entry_effective − stop), 0,10)`, que no depende de la equity ni del FX; solo con `PASS`) | `(policy_id, signal_id)`. Se calcula para toda señal vinculante OPERAR, haya o no posición, como los «ejecutables» de T-024 §6.3. Es la **única** fuente visible de una cohorte embargada sobre la apertura (§10) |
| `paper_signal_disposition` | señal vinculante OPERAR en un libro, en la fase `SIGNAL` (cierre de `t`, P6 §7.6) | `cohort_id`, `signal_id`, `event_ts_utc` (= `analysis_timestamp`), `disposition` (`ORDER` o `IGNORED_ALREADY_OPEN`), `open_position_id` si se ignora | `(cohort_id, signal_id)` |
| `paper_order` | disposición `ORDER` | `order_id`, `cohort_id`, `signal_id`, `binding_evaluation_id`, `target_session` (primera sesión de calendario > `t`), `order_type = OPEN_NEXT_BAR_WITH_MAX` | `(cohort_id, signal_id)`. Como en P6, no hay orden para una señal ignorada |
| `paper_entry_decision` | intento de entrada (fill o rechazo) | `order_id`, `event_ts_utc` (apertura), `lot_id`, `lot_equity_eur` (equity del lote, fijada antes de su primera entrada), `tiebreak_key`, `bar_observation_id`, `open_market`, `entry_effective`, `checks_json` (stop, objetivo, `entry_max`, RR, tamaño), `status` (`FILLED` o el código de rechazo de P6 §17), `equity_before_eur`, `cash_before_eur`, `open_positions_json` (ids y hash), `requested_units`, `requested_cash_eur`, `units`, `notional_eur`, `fee_eur`, `slippage_eur`, `fx_rate`, `fx_timestamp_available`, `risk_local`, `risk_eur` | `order_id` (una decisión por orden) |
| `paper_position` | posición abierta (hecho de apertura) | `position_id`, `cohort_id`, `instrument_id`, `signal_id`, `entry_decision_id`, `units`, `entry_effective`, `stop`, `target2`, `max_hold_bars = 40`, `opened_ts_utc`, `scale_anchor` | `(cohort_id, signal_id)`; además, a lo sumo una abierta por `(cohort_id, instrument_id)` (§12) |
| `paper_position_event` | hecho sobre una posición | `seq`, `position_id`, `event_type` (`OPEN`, `MARK`, `SPLIT_ADJUST`, `DIVIDEND_ENTITLED`, `DIVIDEND_CREDIT`, `DATA_GAP`, `DATA_LOSS_SUSPENDED`, `DATA_RESUMED`, `EXIT`, `NO_EVALUABLE_DATA_LOSS`), `event_ts_utc`, `phase`, `session_date`, `market_price`, `effective_price`, `units_before`, `units_after`, `reason`, `late` (sí/no), `input_ids` | `(position_id, event_type, session_date, source_id)`, donde `source_id` es la observación que lo origina (por ejemplo, el id de `paper_corporate_action`), así que un dividendo tardío y uno normal en la misma sesión no chocan |
| `paper_ledger` | movimiento de caja | las columnas de `p6_sim.LEDGER_COLUMNS` más `cohort_id` y `paper_run_id` | `(cohort_id, seq)`; `seq` estrictamente creciente con `(event_ts_utc, phase, clave)` |
| `paper_equity_snapshot` | (cohorte, día) a las 23:59:59 UTC (P6 §13) | `equity_eur`, `cash_eur`, `long_value_eur`, `n_positions`, exposición por región, divisa y sector, `fx_set_hash` | `(cohort_id, snapshot_day)` |
| `paper_trade_outcome` | posición cerrada con una salida real del contrato (`STOP`, `TARGET`, `TIME`, `EXIT_COHORT_CLOSED`, `EXIT_CORPORATE_ACTION`; nunca una salida sintética, §8.7) | `exit_ts_utc`, `exit_reason`, `exit_market`, `exit_effective`, `pnl_gross_local`, `pnl_gross_eur`, `pnl_net_local`, `pnl_net_eur`, `fees_eur`, `slippage_eur`, `dividends_eur`, `fx_pnl_eur`, `risk_initial_local`, `risk_initial_eur`, `net_R_local`, `net_R_eur`, `mae_R`, `mfe_R`, `duration_bars`, `duration_sessions`, `duration_days`, `exposure_eur_days`, `benchmark_return` (cohorte BH, §11) | `position_id` |
| `paper_seal_commitment` | (cohorte sellada, ejecución) | `cohort_id`, `paper_run_id`, `commitment_sha256 = sha256(nonce ‖ filas selladas canónicas)`, con un `nonce` aleatorio de 32 bytes por ejecución guardado en `paper_seal_nonce` (sellada). Sin `max_seq` ni recuentos | `(cohort_id, paper_run_id)`. Solo el compromiso es visible: como lleva un nonce nuevo, cambia en cada ejecución aunque no haya filas nuevas, y no delata una frontera parada ni cuántos eventos hubo. Al desellar se publican los nonces y se comprueba cada compromiso |
| `paper_seal_window` | regla de sellado vigente | `window_id`, `kind` (`EMBARGO_T024` o `P7_WINDOW`), `cohorts` (todas, en `P7_WINDOW`), `sessions_from`, `sessions_to` (abierto en el embargo hasta su fin), `opened_at`, `opened_by_ref` (D-nn), `closed_at`, `closed_by_ref` | `window_id`; append-only (el cierre es una fila nueva). Visible |
| `paper_outcome_access` | lectura de desenlaces | `cohort_id`, `accessed_at`, `who`, `purpose`, `access_kind` (`NORMAL`, solo fuera de toda ventana sellada; `SEAL_BREAK_AUDIT`, la vía extraordinaria de §10; `P7_HOLDOUT_QUERY`, la consulta única de P7), `query`, `rows_sha256` y **las sesiones consultadas** (`sessions_json`: las fechas de sesión por plaza de todas las barras que entran en los valores leídos, §10) | append-only; es el registro de consumo (§10), y de él sale mecánicamente qué sesiones quedan consumidas |

**Relación con `recommendation`:** `paper_signal_evaluation.source_recommendation_id` es la fila de
C0 del informe con el mismo `run_id` y activo, si existe. Es descriptiva, porque el contexto y el
predicado de broker difieren (§3.2).

**Relación con `run_id`:** cada fila apunta a su `paper_run_id`, y `paper_run.source_run_id` apunta a
la `analysis_run` de la pasada cuyos datos se usaron. Con esos dos identificadores, el SHA, el
`t025_system_sha256` y las observaciones guardadas se reconstruye cualquier operación (§16).

**MAE y MFE** (definición nueva, declarada): sobre las barras desde la de entrada hasta la de salida,
ambas incluidas:
- `mae_R = (min(low) − entrada_efectiva) · unidades / riesgo_inicial_local`;
- `mfe_R = (max(high) − entrada_efectiva) · unidades / riesgo_inicial_local`.

En la barra de entrada solo cuentan los precios desde la apertura, que con datos diarios es la barra
entera: se declara como cota.

## 6. Políticas, libros y capital

- **Decisorias para el registro:** B2 y S2. **Control descriptivo:** C0. **Benchmark:** BH, el
  buy-and-hold a pesos iguales del universo (P6 §14). Ninguna se recalibra. Cada cohorte apunta a
  sus hashes de §0. La implementación los regenera y aborta si no coinciden byte a byte, como hizo el
  preflight de P6: B2 y S2 desde `politicas-finales.json`, y C0 desde la tabla congelada de
  `advisor/research/p6.py` (líneas 95-100), porque `politicas-finales.json` solo contiene B2 y S2.
- **Libros independientes (OD-T25-3, cerrada en D-75):** B2 y S2 operan como libros independientes,
  como en P6 §1. Cada libro tiene sus propios 100.000 EUR iniciales, su cash, su equity, sus
  posiciones, su ledger, sus costes y sus resultados. Una operación de B2 no consume capital de S2 ni
  al revés, y pueden tener a la vez el mismo activo, cada una en su libro. C0 es también un control
  separado, con su propio libro, y BH el suyo.
- **Capital (OD-T25-2, cerrada en D-75):** **100.000 EUR** iniciales por cohorte y libro, iguales para
  B2, S2, C0 y BH, para mantener la comparabilidad directa con P6. El capital de B2 y el de S2 no se
  comparten. Es coherente con el diseño existente:
  - P6 usó 100.000 EUR (OD-P6-1);
  - con unidades **fraccionarias** y sin mínimos por operación (OD-P6-2), el resultado relativo es
    invariante a la escala del capital;
  - el capital vive en `paper_cohort`, no en `config.yaml`, cuyo `portfolio.capital: null` no se toca
    porque está en los `EXECUTOR_PATHS`.

  Limitación: Trade Republic no ofrece fraccionales en todos los instrumentos. Se declara; P6 tenía la
  misma.
- **Universo:** los 90 de P6 (`asset_list_sha256 36355796…`), sin altas ni bajas. Si un activo sale
  del universo vivo de la Pi, sigue en T-025 mientras haya barras (§8.7).
- **Inicio (regla de P6 §7.9 y §14):** todas las cohortes arrancan planas, sin posiciones heredadas.
  Antes de la primera señal se fija en `paper_cohort` una **fecha de inicio `d`**: el primer día hábil
  posterior al despliegue del tag congelado.
  - Se admiten las señales al cierre de la última sesión de cada activo anterior a `d`, que entran en
    la primera apertura de ese activo en o después de `d`.
  - BH compra cada activo en **su propia** primera apertura en o después de `d`. `V_0` es el capital
    en el instante anterior al primer evento de `d`.

## 7. Entrada

### 7.1 Señal emitida y señal vinculante

- La **evaluación** de `(cohorte, activo, sesión t)` es el predicado de la población P6
  (`OPERAR_score_v1_point_in_time`, broker neutral, contexto point-in-time) calculado con las barras de
  sesión cerrada **hasta `t` inclusive**, en una ejecución de T-025 asociada a una pasada programada.
  Se guarda como `paper_signal_evaluation`, aunque el resultado sea «no OPERAR».
- Cada pasada vuelve a evaluar las sesiones `t` cuya apertura siguiente todavía no ha llegado. Cada
  evaluación es una fila nueva e inmutable.
- **Dos instantes distintos (ronda 3):**
  - **`analysis_timestamp`** = la hora **programada** de la pasada (D-50). Es la referencia
    point-in-time con la que el contexto y la frescura filtran por `available_at` (marca de la barra
    más liquidación), exactamente como en P6 (`analysis_timestamp_for_signal`,
    `advisor/context/point_in_time.py:230`). También ordena la fase `SIGNAL`.
  - **`decision_ts`** = el **fin de la ejecución original** de la pasada. En vivo, la pasada descarga
    sus datos durante su ejecución, así que toda observación tiene `observed_at` posterior a la hora
    programada. Exigir `observed_at ≤ analysis_timestamp` dejaría sin entradas a toda evaluación.
- **Reglas de las entradas:** toda observación usada por la evaluación cumple
  `observed_at ≤ decision_ts` (`max_input_observed_at`) y `available_at ≤ analysis_timestamp` (la
  regla PIT de P6). Además, `decision_ts` es estrictamente anterior a la apertura de la sesión de
  entrada. Repetir la evaluación más tarde no puede incorporar observaciones posteriores a su
  `decision_ts` original. No basta con la hora de escritura de la fila.
- **Señal vinculante (D-50):** la evaluación de la **última pasada programada cuya hora es anterior a
  la apertura de la sesión de entrada**, cuya ejecución terminó antes de esa apertura y que tenía
  observada la barra `t`. La elección es determinista. Una pasada que todavía corre al llegar la
  apertura no es vinculante (lo impide `TimeoutStartSec=1800`, que deja 30 minutos antes de la
  apertura más temprana tras cada pasada; se comprueba por señal).
- **Reejecución de una pasada fallida:** si la ejecución original de una pasada programada falla, una
  reejecución de esa misma pasada que termine antes de la apertura la sustituye, con su propio fin como
  `decision_ts`. Una reejecución que termina después de la apertura no es vinculante. La reejecución de
  una pasada que **sí** terminó no cambia su `decision_ts` (§12).
- Si la vinculante dice OPERAR:
  1. se escribe `paper_open_check` para cada política, sin mirar ningún libro (§10);
  2. en cada libro se escribe `paper_signal_disposition` en la fase `SIGNAL`: `IGNORED_ALREADY_OPEN` si
     el libro tiene posición abierta en el activo al cierre de `t` (P6 §7.6, `p6_sim.py:582-585`), y
     si no, `ORDER` y su `paper_order`.
- **Ninguna señal se crea después de la apertura.** Si no hubo ninguna pasada con la barra `t` antes de
  la apertura (la Pi caída, el proveedor sin la barra), el caso se cuenta como `SIGNAL_NOT_EVALUATED`
  y no hay orden. No se rellena hacia atrás.
- `signal_id = stable_signal_id(symbol, "swing", bar_timestamp_t)`: el mismo para las tres políticas,
  como en P6.

### 7.2 Sesión y precio de entrada

- La orden apunta a la **apertura de la barra siguiente de la serie del activo** (P6 §7.8), con la
  hora sacada del calendario efectivo: `exchange_calendars` 4.13.2 más `exchange_overrides.yaml`.
  Festivos y mercado cerrado no son sesión y no ejecutan nada.
- `entrada_efectiva = open · (1 + 0,0005)`. En esa apertura se comprueban, **en el orden exacto de
  `p6_sim._process_entries`** (`advisor/research/p6_sim.py:615-636`) y con el precio efectivo
  (OD-P6-11 A):
  1. `DATA_NOT_EXECUTABLE` (apertura no finita o ≤ 0);
  2. `INVALID_STOP` (`stop ≥ entrada efectiva`, incluido un hueco por debajo del stop);
  3. `INVALID_TARGET` (`target2 ≤ entrada efectiva`);
  4. `ABOVE_MAX_ENTRY` (entrada efectiva > `entry_max`, con la tolerancia relativa de 1e-9 de P6,
     también cuando la causa es un hueco al alza);
  5. `RR_TOO_LOW` (RR a `target2` < 1,5 con `rr_at_least`);
  6. `POSITION_TOO_SMALL`;
  7. `INSUFFICIENT_CASH` (nominal más comisión > cash).

  El broker es neutral. **No** es el orden de `simulate_asset` que describe T-022 §3.1: manda el
  simulador de P6, y el test de equivalencia lo comprueba.
- **Caducidad:** la orden vale **solo** para esa barra. Se consume en su apertura con un fill o un
  rechazo, y no se arrastra a ninguna otra sesión.
- **Barra de entrada ausente (OD-T25-5, cerrada en D-75, alternativa A):** si la barra de la sesión
  `s` no se valida en ninguna pasada hasta el cierre de la **5.ª sesión hábil** posterior a `s` (el
  margen del retraso europeo de T-024 §7), `s` se declara sin barra y se aplica la misma semántica de
  salto de P6: la orden pasa a la siguiente barra de la serie, que salta y cuenta esas sesiones.
  - El hecho se registra explícitamente: `ENTRY_BAR_DECLARED_MISSING` en `paper_data_alert`, a nivel de
    activo y sesión (visible, porque se escribe para todo activo del universo sin barra, haya o no
    orden), y en el libro, sellado, qué orden afectó.
  - Una barra de `s` que aparezca después se registra como tardía (`LATE_BAR`) y **jamás** reescribe
    una decisión.
  - El salto es mecánico, sin ninguna elección: que la decisión se escriba días después no le da
    información posterior, porque usa la apertura de la barra siguiente y la equity y el cash
    anteriores a ella.
- **Instante «ex ante»:** el sizing, la equity y el cash de la decisión son los del instante τ de la
  apertura con información estrictamente anterior a τ (P6 §7.3). La fila se escribe cuando la barra de
  apertura ya está validada, así que `computed_at > τ` siempre. Por eso cada decisión guarda los ids
  de todas sus entradas, y un test comprueba que ninguna tiene una marca ≥ τ salvo la apertura de la
  propia barra, que es el precio de la orden y no un desenlace.

### 7.3 Lote y desempate

Las entradas con el mismo τ forman un lote. Su equity se calcula una vez, antes de la primera entrada
(P6 §7.3). Se intentan en orden ascendente de
`sha256(b"intradia.p6.desempate.v1" + signal_id.encode("utf-8")).hexdigest()` (OD-P6-6 D), y el cash
se comprueba entrada a entrada en ese orden.

## 8. Salidas y eventos de posición (contrato de P6 §7.8–§11, con las adaptaciones en vivo declaradas)

1. **Stop y objetivo:**
   - hueco por debajo del stop → salida a la apertura;
   - toque intradía del stop → al stop;
   - hueco por encima de `target2` → a la apertura;
   - toque intradía de `target2` → a `target2`;
   - **stop y objetivo en la misma barra → gana el stop**.

   Salida efectiva = precio de mercado · (1 − 0,0005). `target3` no interviene. `target1` se guarda,
   pero no sale nada en él.
2. **Tiempo:** al cierre de la barra 40 contada desde la de entrada, en barras de la serie.
3. **Fases y cronología:** las de P6 §8.2–§8.4. Una salida a la apertura financia las entradas de esa
   apertura. El cash de una salida intradía no se usa antes del cierre. La liquidación es inmediata
   (OD-P6-8).
4. **Una posición por activo y libro:** una señal OPERAR sobre un activo con posición abierta en ese
   libro es `IGNORED_ALREADY_OPEN`, que se decide en la fase `SIGNAL` (cierre de `t`) y no en la
   apertura. Se guarda en `paper_signal_disposition`, no crea orden, no reemplaza el stop ni el
   objetivo y no piramida (OD-P6-38).
5. **Dividendos:** salen de `paper_corporate_action` (`Dividends` de `get_raw_history`, por acción, en
   la divisa de cotización y en la misma base de splits que la serie, como en P6 §10.1). Hay derecho si
   la posición estaba abierta al cierre de la víspera de la fecha ex; el abono se hace al cierre de la
   sesión ex, bruto (OD-P6-12, 13 y 14). **Un dividendo nunca reescala una posición:** la serie no
   está ajustada por dividendos (§3.3).
   - **En vivo (OD-T25-6, cerrada en D-75, alternativa A):** un dividendo que se conoce más tarde se
     registra cuando se conoce, se abona causalmente al cierre de la primera sesión procesada después
     de conocerlo y queda marcado `late`. **Nunca reescribe** balances, tamaños ni decisiones
     anteriores.
   - Si la posición ya se cerró, el abono tardío es un `DIVIDEND_CREDIT` `late` enlazado a ella: no la
     reabre ni modifica su fila de `paper_trade_outcome`. Las métricas por operación suman los abonos
     tardíos enlazados en una vista derivada.
   - **Misma base:** el derecho se calcula con las unidades vigentes en la víspera de la fecha ex, y el
     importe se expresa en esa misma base. Si entre la fecha ex y el abono hay un `SPLIT_ADJUST`, el
     importe por acción se convierte con su ratio, para que el abono total no cambie.
6. **Splits:** P6 operaba sobre una cosecha cerrada, ya ajustada por los splits de toda la ventana. En
   vivo, `yfinance` reajusta hacia atrás la serie cuando ocurre un split, a mitad de una posición.
   - **Solo un `SPLIT` observado** (`Stock Splits` en `paper_corporate_action`) con ratio `r` reescala
     una posición. Se ejecuta un evento `SPLIT_ADJUST` en la apertura de la sesión ex, antes de
     `OPEN_EXIT`: `unidades · r`, y la entrada, el stop y los objetivos `/ r`. El valor económico y el
     cash no cambian.
   - Las barras ya guardadas no se reescriben. A partir de la sesión ex, las barras nuevas se leen en la
     escala nueva, y `paper_bar_rescale` registra el factor con `explained_by = SPLIT`.
   - Si las barras nuevas cambian de escala frente al `scale_anchor` de una posición **sin un split
     observado** que lo explique, la posición queda en `DATA_GAP` (`SCALE_MISMATCH`) y no se procesa
     hasta una revisión documentada. Nunca se adivina el factor, y un dividendo nunca se interpreta como
     split.
7. **Datos ausentes, `DATA_LOSS` y eventos terminales (OD-T25-7, modificada y cerrada en D-75):**
   - mientras falte la barra de un activo **con posición o con orden pendiente** en el libro, el libro
     no procesa eventos posteriores a esa sesión, hasta el límite de §7.2. Así una entrada no queda
     nunca detrás de la frontera (§12);
   - pasado el límite, la sesión se declara sin barra y el libro sigue, como P6: la posición conserva
     su última valoración (`mark_price` = último cierre validado, la semántica de
     `p6_sim.CLOSE_VALUATION`) y las barras ausentes no cuentan para las 40 del tiempo máximo;
   - **`DATA_LOSS / SUSPENDED`:** tras **20 sesiones hábiles consecutivas** del calendario del activo
     sin datos suficientes, la posición pasa al estado operativo `DATA_LOSS_SUSPENDED`
     (`paper_position_event`), y **no se fabrica una venta**:
     - no hay `exit_price` sintético ni P&L ficticio, y el último cierre conocido **nunca** se usa como
       si fuera ejecutable 20 sesiones después;
     - el capital queda bloqueado: la posición sigue en el libro, sus unidades no vuelven al cash y
       la valoración sigue siendo el último cierre validado, marcada `STALE` en
       `paper_equity_snapshot` y publicada aparte de la parte evaluable;
     - se genera la alerta operativa `NO_DATA_20_SESSIONS` en `paper_data_alert`, **a nivel de
       activo** y para todo activo del universo en esa situación, haya o no posición, así que no delata
       ningún libro; el caso queda identificado en el libro (sellado mientras rija el embargo, §10);
   - **si vuelven datos válidos**, el procesamiento causal se reanuda desde la primera barra realmente
     observada después de la frontera (`DATA_RESUMED`), con las reglas normales: un hueco por debajo
     del stop sale a la apertura de esa barra. **El periodo perdido no se reescribe:** una barra de una
     sesión ya declarada sin barra se guarda como tardía y no se procesa;
   - **si la cohorte termina** (`CLOSING`, §13) sin que vuelvan datos suficientes, la operación queda
     `NO_EVALUABLE_DATA_LOSS`: se informa por separado, sin `paper_trade_outcome`, sin resultado
     inventado y fuera de toda métrica por operación;
   - **salida real verificable (regla específica, no el fallback de 20 sesiones):** solo un
     `TERMINAL` de `paper_corporate_action` con `terminal_kind` `DELISTING_CASH`, `LIQUIDATION` o
     `CASH_MERGER`, con precio de liquidación por acción, divisa y fecha efectiva, y una fuente oficial
     verificable (aviso de la bolsa o del emisor) cuyo hash se guarda. Lo registra una D-nn **a nivel
     de activo**, sin mirar ningún libro, y el motor lo aplica como `EXIT_CORPORATE_ACTION` a las
     posiciones que haya: al precio de liquidación, con la comisión de P6 (0,10 %, conservadora) y sin
     slippage, porque el precio es fijo; en la fecha
     efectiva si está en la frontera o después, y si no, en la frontera marcado `late` (nunca
     reescribe). Un canje por acciones u otro evento sin precio de liquidación verificable no tiene
     regla: la posición sigue en `DATA_LOSS_SUSPENDED` y, si la cohorte termina, queda
     `NO_EVALUABLE_DATA_LOSS`.
8. **FX:** la regla A de P6 (OD-P6-16) sobre `paper_fx_quote`. Si para un evento no hay ningún tipo
   causal, el evento espera. Nunca se inventa un tipo (INV-16). Hay una sola caja en EUR (P6 §11.2).

**Adaptaciones en vivo frente a P6, todas declaradas:** la señal vinculante por pasada (§7.1) y su
reejecución, `SIGNAL_NOT_EVALUATED`, la barra ausente y su límite, los dividendos tardíos,
`SPLIT_ADJUST` solo por split observado, `SCALE_MISMATCH`, `DATA_LOSS_SUSPENDED` y
`NO_EVALUABLE_DATA_LOSS`, `EXIT_CORPORATE_ACTION`, `EXIT_COHORT_CLOSED` y `ABORTED_INVALID_ENGINE`
(§13). P6 cerraba toda posición dentro de su ventana cerrada; T-025 no tiene final fijo. Fuera de esto,
cualquier diferencia de comportamiento con P6 es un defecto.

## 9. Costes y riesgo (P6, sin cambios)

- 0,10 % por lado sobre el nominal ejecutado (OD-P6-9 A); slippage primario de 5 pb por lado
  (OD-P6-10). La sensibilidad de 10 pb, si se publica, se calcula al publicar, reprocesando el mismo
  flujo de eventos, y es descriptiva.
- Riesgo del 0,5 % de la equity causal por operación y posición máxima del 10 % de esa equity.
- Long only, sin margen ni apalancamiento, cash ≥ 0 siempre. Sin cash suficiente, **rechazo
  completo** (`INSUFFICIENT_CASH`), sin reducir el tamaño.
- Sin límites globales nuevos: R-01 va después de P7.
- **Nada de esto cambia sin una decisión del propietario.**

## 10. Embargo, visibilidad, sellado y consumo

**Por qué.** T-024 prohíbe mirar desenlaces de B2 y S2 posteriores al 2026-08-27 antes de su mirada
(D-72; ficha §6.3 y §9: «ningún checkpoint emite desenlaces», ni ventanas abiertas o cerradas).
T-025 opera las mismas políticas en las mismas sesiones. D-73 §2 lo resolvió: **los desenlaces de B2
y S2 quedan sellados hasta que T-024 se resuelve**. OD-T25-4 (D-75) fija qué se ve mientras tanto.

### 10.1 Embargo de T-024 (OD-T25-4, cerrada en D-75)

- **Cohortes embargadas:** B2, S2 y **C0**. C0 queda sellado en desenlaces y P&L durante el mismo
  embargo, porque en P6 sus 2.423 señales son también de B2 y de S2 (el 23 % de las de B2 y el 99 % de
  las de S2) y comparte con B2 el stop de 2,0·ATR: no puede servir de vía lateral. Esto sustituye la
  regla provisional de D-73 §2 («C0 visible»). En vivo, el solape se mide y se publica al desellar.
- **BH** no depende de ninguna señal ni de ningún libro de política y queda visible, sujeto a las
  ventanas de P7 (§10.7). Consultarlo consume sesiones como cualquier otra cohorte (§10.6).
- **Duración y desellado conjunto:** el embargo dura hasta que T-024 tiene un resultado (`POSITIVO`,
  `NO POSITIVO` o `NO EVALUABLE POR MUESTRA`) **para B2 y para S2 a la vez**. Entonces se desellan B2,
  S2 y C0 juntos. Medido sobre los ledgers publicados de P6
  (`evidence/2026-10-03-T-022-p6/run/tablas/*_primaria_5pb-ledger.csv`, `signal_id` distintos): B2 tiene
  10.577 señales, S2 2.440 y C0 2.423; **todas las de S2 están entre las de B2**, y todas las de C0
  entre las de B2 y entre las de S2. Desellar una política antes que otra revelaría la otra, así que
  **no hay desellado por política** mientras exista solape.
- Si T-024 no llega a resolverse (se abandona o se rompe su identidad), el embargo sigue hasta que una
  D-nn del propietario declare T-024 terminado sin resultado.
- El desellado y el fin del embargo son filas de `paper_seal_window` con su D-nn.

### 10.2 Visible durante el embargo: información ex ante (lista cerrada)

Para B2, S2 y C0, por señal:
1. de `paper_signal_evaluation`: fecha y hora de la señal (`analysis_timestamp`, `decision_ts`),
   `signal_id`, activo, política, sesión `t`, pasada, `operar`, `reference_price`, `entry_max`, stop,
   objetivos, RR, `risk_fraction`, score, contexto y calidad del dato;
2. de `paper_open_check` (la **ejecución simulada de entrada**, por política y sin libro): sesión de
   entrada, apertura, **precio de entrada efectivo** cuando la apertura la permite (`PASS`), los
   **rechazos de entrada de mercado con su motivo** (`DATA_NOT_EXECUTABLE`, `INVALID_STOP`,
   `INVALID_TARGET`, `ABOVE_MAX_ENTRY`, `RR_TOO_LOW`) y el **tamaño solicitado** como fracción de la
   equity (`requested_weight`).

Además, sin depender de ningún libro: `paper_data_alert`, `paper_corporate_action`,
`paper_cohort_event`, `paper_seal_window`, el `status` genérico de `paper_run` y `commitment_sha256`.
Los conteos que se publiquen salen solo de estas filas (señales OPERAR, comprobaciones de apertura por
código, pares (activo, semana ISO) y semanas ISO, como T-024 §6.3).

Así se responde a **«¿qué habría comprado hoy el bot?»**: qué activo, con qué niveles, si la apertura
permitía la entrada, a qué precio y con qué fracción de la equity.

**Cómo se aplica la lista del propietario sin abrir canales laterales (ronda 4).** D-75 permite ver
«tamaño solicitado», «ejecución simulada de entrada», «precio de entrada si se ejecutó» y «rechazos de
entrada y su motivo», y sella «cualquier otro canal lateral identificado por la revisión». La forma
**por libro** de esos campos es un canal lateral, así que se muestra su forma **por política**:
- el tamaño en unidades o en EUR revela la equity, porque
  `unidades · (entrada − stop) · fx = 0,005 · equity` y el tope es el 10 % de la equity. La fracción
  `requested_weight` no depende de la equity ni del FX;
- `FILLED`, `IGNORED_ALREADY_OPEN`, `INSUFFICIENT_CASH` y `POSITION_TOO_SMALL` dependen del estado del
  libro: un `IGNORED_ALREADY_OPEN` dice que una posición anterior **sigue abierta** (no tocó ni stop ni
  objetivo), y un `INSUFFICIENT_CASH` o un `FILLED` delatan el cash. Por eso «se ejecutó» se muestra como
  la comprobación de apertura `PASS` con su precio efectivo, que es la misma para todo libro.

### 10.3 Sellado durante el embargo

Para B2, S2 y C0 no se muestra, mientras dure el embargo:
- si una posición sigue abierta o está cerrada, su estado posterior y `DATA_LOSS_SUSPENDED`;
- timestamp, motivo y precio de salida; stop u objetivo alcanzado;
- P&L, `net_R`, MAE, MFE y duración final;
- cash, equity y exposición derivados de desenlaces, y unidades o importes de cualquier orden o posición;
- PF, win rate, drawdown, CAGR, exceso de CAGR y cualquier métrica agregada que revele resultados;
- el progreso y la frontera de la cohorte, y cualquier recuento de eventos de libro;
- cualquier otro canal lateral identificado por la revisión.

En tablas: nada de `paper_signal_disposition`, `paper_order`, `paper_entry_decision`,
`paper_position`, `paper_position_event`, `paper_ledger`, `paper_equity_snapshot`,
`paper_trade_outcome`, `paper_cohort_progress`, `paper_run_diagnostic` ni `paper_seal_nonce`; ni sus
recuentos, ni los `late`, `DATA_GAP`, `SCALE_MISMATCH`, `DATA_LOSS_SUSPENDED` o
`NO_EVALUABLE_DATA_LOSS` de un libro.

**Canales laterales cerrados por construcción:**
- **Alertas operativas a nivel de dato, nunca de libro.** Un aviso «falta la barra de X», «sin FX
  para Y» o «X lleva 20 sesiones sin datos» se calcula para todo el universo, haya o no posición u orden
  (`paper_data_alert`). El operador arregla el dato sin saber qué libros dependen de él. El detalle «el
  libro B2 espera a X» es `paper_run_diagnostic`, sellado.
- **Estado de ejecución genérico.** `paper_run.status` es `OK`, `ERROR`, `IDENTITY_MISMATCH` o `LOCKED`,
  sin detalle de libro.
- **Compromiso con nonce.** `commitment_sha256` cambia en cada ejecución aunque la frontera no avance
  (§5), así que no delata paradas ni volumen.
- **Tamaño de `paper.db`.** No se publica mientras rija un sellado: crece con los eventos de posición y
  delataría la exposición. La evidencia periódica guarda solo el hash del fichero (§«Evidencia»).
- **Acciones corporativas terminales** se registran a nivel de activo, sin mirar ningún libro (§8.7).
- **Duración de las ejecuciones:** no se publica por cohorte.

**Destinatarios del sellado:** el propietario, el dashboard, la CLI normal, Telegram, Claude, Codex y
cualquier agente de análisis. El motor sí calcula y persiste todo lo necesario para mantener una
cartera causal.

### 10.4 Mecanismo, vía extraordinaria y límite

- La cohorte embargada se calcula en vivo, igual que las demás. Cada ejecución escribe su
  `paper_seal_commitment`; al desellar se publican los nonces y se comprueba que nada se reescribió.
- **Toda lectura** de `paper.db` pasa por una única capa de visibilidad, que aplica `paper_seal_window`.
  Informe, Telegram, dashboard, API, exportaciones y CLI normal solo usan la vista visible.
- **Vía extraordinaria (solo contrato; no se implementa ahora):** únicamente para recuperación o
  auditoría técnica. Exige invocación explícita con motivo, escribe **antes** de devolver nada una fila
  `paper_outcome_access` con `access_kind = SEAL_BREAK_AUDIT`, las sesiones cubiertas y el hash de lo
  devuelto, y cuenta como **ruptura del sellado**: consume esas sesiones (§10.6) y se registra en una
  D-nn. Si afecta a B2, S2 o C0 durante el embargo, la D-nn declara también la pérdida de ceguera
  correspondiente en T-024.
- **Limitación:** el sellado es procedimental, no criptográfico. Quien tenga el fichero (el usuario de
  la Pi) puede leerlo. Se declara, como el ciego de la fase B de T-024.

### 10.5 Contrato de tests del sellado (obligatorio en la implementación)

La implementación tiene que incluir tests que demuestren que, con un embargo o una ventana P7 activos
y datos sintéticos con posiciones abiertas, cerradas, `DATA_LOSS_SUSPENDED` y rechazos de libro:
- ninguna consulta normal de la capa de visibilidad devuelve desenlaces;
- ninguna API devuelve desenlaces;
- ningún comando CLI devuelve desenlaces;
- el mensaje de Telegram no los contiene;
- el dashboard no los recibe;
- las exportaciones normales no los incluyen;
- ninguna métrica agregada se calcula sobre filas selladas;
- las fronteras, los contadores, los estados, las alertas, `paper_run.status` y el compromiso no
  funcionan como canales laterales: dos libros sintéticos con desenlaces distintos y las mismas señales
  producen **exactamente la misma salida visible**, byte a byte;
- la vía extraordinaria escribe su `paper_outcome_access` antes de devolver filas, y sin esa escritura
  no devuelve nada.

### 10.6 Consumo (OD-T25-9, cerrada en D-75: unidad = sesión)

> Toda observación cuyo desenlace se consulte durante T-025 queda consumida para investigación y no
> podrá utilizarse posteriormente como holdout virgen de P7. (D-74 §3)

- **La unidad es la sesión.** Si se consulta un desenlace de **cualquier** política o cohorte T-025
  (BH incluida) que corresponda a una sesión, esa sesión queda consumida para investigación. No se usa
  `(política, sesión)`: las poblaciones están solapadas (§10.1) y una candidata de P6-bis que conserve
  la señal B2/S2 compartirá su población.
- **Sesiones que cubre un valor:** todas aquellas cuyas barras entran en él. Una operación cubre desde
  su sesión de entrada hasta la de salida; una equity, un cash, un drawdown o cualquier métrica
  acumulada cubre todas las sesiones de la cohorte hasta su fecha.
- **Registro:** cada lectura de desenlaces deja una fila en `paper_outcome_access` con sus sesiones, y
  de ahí sale mecánicamente qué sesiones quedan consumidas. Lo consumido es un hecho registrado, no una
  memoria.
- Ver información ex ante (§10.2) no consume sesiones, pero se declara (D-76, §10.7).

### 10.7 Ventana futura de P7 (OD-T25-9, cerrada en D-75: alternativa C)

- **Frontera de P7:** P7 empieza después de la congelación de su candidata **y** del `T1` de la
  última mirada de T-024 (OD-T24-11), y solo usa sesiones sin desenlace consultado en T-025 y que no
  hayan intervenido en T-024 ni en P6-bis.
- Cuando exista una candidata válida, **antes de comenzar P7 se fija su ventana**, solo con sesiones
  futuras (la primera, posterior a la fecha en que se registra). Así nunca puede estar consumida, y
  `paper_outcome_access` lo demuestra. Como T-025 nunca consume una sesión antes de que ocurra, siempre
  se puede reservar una ventana futura: T-025 no puede dejar a P7 sin holdout.
- **Desde que se fija**, una fila `paper_seal_window` (`P7_WINDOW`) sella **todas** las cohortes T-025
  (B2, S2, C0, BH y cualquier versión) para las sesiones de esa ventana. Durante ese periodo T-025
  sigue funcionando y registrando, pero ningún desenlace de esas sesiones se consulta, aparece en el
  dashboard, la CLI o Telegram, ni es accesible a ningún agente.
- **Lo acumulado también:** una equity, un cash, un drawdown, una métrica o una operación que cubra
  alguna sesión de la ventana (§10.6) queda sellado aunque se consulte después de que la ventana
  termine, hasta la consulta única de P7. Si no, la equity del día siguiente revelaría el P&L agregado
  de la ventana.
- La información ex ante sigue visible como durante el embargo. **El pre-registro de P7 tiene que
  declarar esa exposición**, como D-76 lo hace para T-024.
- Después de la consulta única del holdout (INV-15) se registra formalmente su consumo:
  `paper_outcome_access` con `access_kind = P7_HOLDOUT_QUERY`, el cierre de la ventana en
  `paper_seal_window` y una D-nn.
- El embargo de T-024 y una ventana de P7 pueden coincidir: un valor solo es visible si **ningún**
  sellado activo lo cubre.

### 10.8 Otras fronteras

- **P6-bis** no lee `paper.db`. Solo usa sesiones hasta el 2026-08-27 (D-73 §6).
- **T-024 y T-025 no se alimentan entre sí:** las poblaciones y los datos son distintos (cosechas
  mensuales frente a pasadas en vivo) y sus objetivos también (medición frente a registro operativo).
  Una comparación entre los dos solo es descriptiva, después de desellar, y no cambia nada de ninguno.
- **Ceguera de T-024 (D-76):** T-024 conserva intactos su pre-registro, su código, sus métricas, sus
  criterios, su calendario de miradas, su ejecución automática, D2 y sus reglas de decisión. Pero la
  ceguera humana deja de ser absoluta: el propietario ve las señales ex ante de B2 y S2 y, con precios
  públicos, podría intentar deducir resultados a mano. **T-024 conserva su diseño confirmatorio
  pre-registrado, con visibilidad parcial ex ante del propietario declarada antes de observar
  desenlaces.** Su pre-registro no se modifica.

## 11. Benchmark

La cohorte BH aplica el contrato de P6 §14 desde `start_ts_utc`:
- 1/90 del capital por activo, con la comisión dentro del importe;
- dividendos reinvertidos en la apertura siguiente;
- sin rebalanceo;
- mismas reglas de FX, costes y slippage.

`benchmark_return` de una operación es `V_BH(salida) / V_BH(entrada) − 1`, con las equity de BH
valoradas en los mismos τ. `excess` frente a BH se calcula como en P6 §15.

## 12. Idempotencia, concurrencia y reconstrucción

- **Un solo escritor:** un `flock` exclusivo sobre `paper.db.lock` durante toda la ejecución. Una
  segunda ejecución concurrente sale con un código propio, sin escribir nada.
- **Transacción por instante τ (lote):** todos los eventos de una cohorte con el mismo `event_ts_utc`
  y la misma fase (un lote de entradas, las salidas de una apertura) se escriben en **una**
  transacción, con sus filas de ledger, posición y evento. Si la ejecución se corta, el lote entra
  entero o no entra, y al reanudarse el sizing del lote vuelve a salir de la equity anterior al lote
  (`lot_equity_eur`), no de una equity que ya incluya parte del lote.
- **Repetir una pasada no duplica nada:**
  - las claves únicas de §5 hacen que reprocesar las mismas entradas sea un no-op;
  - si una clave choca con un **contenido económico distinto** (`content_sha256` de §5, que excluye
    `paper_run_id`, `computed_at` y los `observed_at` de la ejecución), la ejecución para con
    `ERROR_DIVERGENCIA` y no escribe;
  - una pasada repetida no puede abrir otra vez la misma posición: `(cohort_id, signal_id)` es único
    en `paper_order`, `paper_entry_decision` y `paper_position`.
- **Una abierta por activo y libro:** el motor lo garantiza, y una comprobación al final de cada
  transacción (posiciones con `OPEN` y sin `EXIT` por `(cohort_id, instrument_id)` ≤ 1) aborta la
  transacción si se viola.
- **Frontera por cohorte:** cada cohorte avanza en orden total `(event_ts_utc, phase, clave)`, y solo
  hasta el menor τ para el que estén observadas las barras de **todo activo con posición abierta o con
  orden pendiente** en ese libro, y el FX causal que haga falta (§8.7, §8.8). Así ninguna entrada ni
  salida queda nunca detrás de la frontera. No se escribe un evento con τ anterior a la frontera ya
  escrita. Solo un dividendo conocido tarde (§8.5) y un `EXIT_CORPORATE_ACTION` registrado tarde
  (§8.7) se aplican en la frontera, marcados `late`.
- **Identidades contables** de P6 §19 en cada evento y al final de cada ejecución, con tolerancia de
  1e-6 EUR: `equity = cash + Σ valor`, `cash ≥ 0` y el flujo V_T − V_0. Si una falla, la ejecución
  aborta.
- **Reconstrucción:** con `paper_run_id`, SHA, `t025_system_sha256` y las observaciones guardadas,
  reprocesar desde cero con el mismo `t025_code_sha` tiene que dar el mismo ledger byte a byte. Se
  prueba en los tests y en una verificación periódica. En una cohorte sellada solo es visible si
  coincide o no; el detalle de una discrepancia es `paper_run_diagnostic`, sellado.

## 13. Versionado, cohortes y modificación (OD-T25-8, cerrada en D-75)

- B2, S2 y C0 quedan **congeladas** durante todo el shadow. Cambiar una política crea una
  `policy_version` nueva, y con ella una cohorte nueva.
- El paper broker se versiona por `engine_version` y por tag. **`t025_system_sha256`** es el hash
  canónico de un envoltorio `intradia.t025.system.v1` con: el `p6_system_sha256` de referencia, cada
  adaptación de §8, `engine_version`, la regla de señal vinculante, los límites de datos ausentes, el
  sellado y el capital.
- **Identidad de una cohorte = un commit completo.** El motor de una cohorte es `paper/` **más** el
  `advisor` que importa y su configuración (§4), y `main` puede cambiar `advisor/` (D-77). Por eso cada
  cohorte guarda `t025_code_sha`, y cada ejecución comprueba, como `verificar_identidad()` de T-024,
  `git diff --quiet <t025_code_sha> HEAD -- paper advisor config.yaml universe.yaml
  exchange_overrides.yaml pyproject.toml requirements.txt`, un árbol limpio en esas rutas y la
  regeneración de los hashes de §0. Si no se cumple, esa cohorte **no se procesa** en esa ejecución
  (`IDENTITY_MISMATCH`, genérico): nunca corre con otro código.
- **Una versión nueva del motor crea una cohorte nueva** (alternativa A). La cohorte antigua **continúa
  bajo su motor y su contrato congelados**: en la Pi, cada `t025_code_sha` activo corre en su propio
  worktree desacoplado, como T-024. No se migra en silencio y nunca se mezclan resultados de cohortes.
  Mientras una cohorte no se puede procesar (por ejemplo, porque falta su worktree), pierde sus señales
  como `SIGNAL_NOT_EVALUATED`, y eso se declara.
- **Cierre ordinario:** el propietario puede cerrar una cohorte (`CLOSING` en `paper_cohort_event`).
  Sus posiciones salen con `EXIT_COHORT_CLOSED` en la apertura siguiente de cada activo; una posición
  en `DATA_LOSS_SUSPENDED` queda `NO_EVALUABLE_DATA_LOSS` (§8.7). Después, `CLOSED`.
- **Defecto crítico (precisión del propietario):** si se descubre un defecto que invalida materialmente
  la ejecución de una cohorte, esa cohorte **no sigue ejecutándose como si nada**:
  - se congela y se declara `ABORTED_INVALID_ENGINE` en `paper_cohort_event`, con la causa
    documentada en una D-nn;
  - no se procesa ningún evento más, no se fabrican salidas y su historia **nunca se corrige
    retrospectivamente**; se conserva entera para auditoría;
  - sus desenlaces no entran en ninguna métrica ni comparación, salvo como auditoría del defecto;
  - una versión corregida abre una **cohorte nueva**, que arranca plana según §6.
  - Si el defecto se descubre en una cohorte embargada, el diagnóstico tiene que salir de tests, datos
    sintéticos o información visible. Si exige leer filas selladas, eso es la vía extraordinaria de
    §10.4: ruptura del sellado registrada, con consumo de sesiones.
- **Nunca se mezclan cohortes sin etiqueta** en una métrica ni en el dashboard.
- **Nunca se reescribe** una observación anterior.

## 14. Métricas y publicación

Definiciones exactas de P6 §15 (`p6_sim.path_metrics`, `trade_metrics` y `exposure_metrics`), por
cohorte. Se publican:
- señales evaluadas, OPERAR, vinculantes y `SIGNAL_NOT_EVALUATED`;
- ejecutables a la apertura;
- rechazos por motivo, en especial `ABOVE_MAX_ENTRY`, `INSUFFICIENT_CASH` e
  `IGNORED_ALREADY_OPEN`;
- operaciones abiertas y cerradas;
- exposición media, utilización del cash y turnover;
- PF, mean_R (local y EUR), win rate y max drawdown;
- CAGR (solo con ≥ 1 año de serie; antes N/D);
- benchmark y exceso frente a BH;
- MAE, MFE y duraciones;
- `late`, `DATA_GAP`, `SCALE_MISMATCH`, `DATA_LOSS_SUSPENDED` y, aparte y fuera de las métricas por
  operación, las `NO_EVALUABLE_DATA_LOSS`;
- el capital bloqueado en `DATA_LOSS_SUSPENDED` (valoración `STALE`), separado de la equity evaluable;
- el estado de cada cohorte (`ACTIVE`, `CLOSING`, `CLOSED`, `ABORTED_INVALID_ENGINE`).

Mientras un sellado cubra una cohorte o unas sesiones (embargo de T-024 o ventana de P7, §10), solo
se publica la lista cerrada de §10.2 y los conteos que salen de ella; ningún otro recuento. **Ninguna de
estas métricas se usa para tocar B2, S2, C0 ni el motor durante la captura.** Las métricas no tienen intervalo ni veredicto:
son descriptivas (INV-20).

**Dashboard futuro (S-02, S-03; no se implementa ahora).** Mientras el embargo esté activo, tiene
**dos zonas conceptuales**, y la segunda no recibe ningún dato de las cohortes embargadas, ni siquiera
recuentos:

| Zona | B2, S2 y C0 durante el embargo | Fuente |
|---|---|---|
| **Información visible ex ante** | señales de hoy por política; niveles (`entry_max`, stop, objetivos, RR); tamaño solicitado como fracción de la equity; ejecución simulada de entrada por política (`PASS` con su precio efectivo, o rechazo de mercado); razones y motivos; alertas de dato; estado de la cohorte | §10.2 |
| **Información sellada** | un rótulo fijo «sellado hasta que T-024 se resuelva (D-73, D-75)», sin cifras: ni estado posterior, ni salidas, ni P&L, ni equity, ni cash derivado, ni métricas | §10.3 |

BH se muestra entero en la primera zona, salvo lo que cubra una ventana de P7. Al desellar, la segunda
zona muestra, por cohorte:
- capital inicial, equity, cash, posiciones abiertas y cerradas, capital bloqueado;
- rentabilidad, drawdown, benchmark y exceso;
- la ejecución por libro (`FILLED`, `IGNORED_ALREADY_OPEN`, `INSUFFICIENT_CASH`…);
- por operación cerrada: `net_R` (local y EUR), MAE, MFE, duración, costes, dividendos, FX y
  `benchmark_return`;
- etiqueta y cohorte.

Cada consulta de la segunda zona deja su fila en `paper_outcome_access` (§10.6). Durante una ventana de
P7, las sesiones de la ventana y todo lo acumulado sobre ellas vuelven a la zona sellada (§10.7).

Los campos salen de §5. Frente al registro por señal de GATE P10, hay tres diferencias:
- **`context_state`** (shadow de contexto) falta: llega con la línea B (B-07);
- **el desenlace es por posición abierta**: una señal rechazada o ignorada guarda su motivo, pero no
  tiene desenlace en T-025;
- **el «alfa»** de P10 se lee como exceso frente a BH (§11), y P10 tendrá que fijar su definición.

`execution_state`, `net_R`, MAE, MFE y el benchmark están en §5.

## 15. Invariantes

- **INV-02, INV-06, INV-07, INV-13, INV-15, INV-16 e INV-18:** se ejercitan con los tests de §16.
- Específicas de T-025:
  - **T25-1:** ninguna fila de hechos se actualiza ni se borra;
  - **T25-2:** ninguna decisión usa una entrada con marca ≥ τ, salvo la apertura de su barra. Para la
    señal, τ es `decision_ts` (fin de la ejecución, anterior a la apertura) y además rige
    `available_at ≤ analysis_timestamp` (§7.1);
  - **T25-3:** como mucho una posición abierta por `(cohorte, activo)`;
  - **T25-4:** ningún camino de presentación lee lo sellado mientras un sellado lo cubra, y la salida
    visible no depende de los desenlaces (§10.5);
  - **T25-5:** ninguna consulta de `intradia.db` devuelve una fila paper, y `paper/` nunca abre
    `intradia.db` para escribir;
  - **T25-6:** el motor reproduce `p6_sim` (test de equivalencia);
  - **T25-7:** una cohorte solo se procesa con su `t025_code_sha` (§13); T-025 nunca toca
    `t024/forward` ni sus `EXECUTOR_PATHS` (D-77);
  - **T25-8:** no existe ninguna salida sintética: toda fila de `paper_trade_outcome` es una salida
    real del contrato (§8.7);
  - **T25-9:** toda lectura de desenlaces deja antes su fila en `paper_outcome_access` con sus
    sesiones (§10.6).

## 16. Implementación requerida (tarea siguiente, con autorización aparte)

Nada de esto se hace en esta entrega.

1. Revisión final del propietario de este PR y congelación de `T025_PREREG_SHA` (las OD-T25 y OD-12
   ya están cerradas: D-75, D-76, D-77).
2. `paper/`: almacén y migraciones de `paper.db`, motor incremental `engine_v1`, capa de visibilidad,
   CLI y mensaje de Telegram.
3. **Tests obligatorios, con datos sintéticos:**
   - equivalencia con `p6_sim.simulate`, ledger fila a fila, incluido un lote con cash escaso y
     desempate;
   - una pasada repetida no duplica; una divergencia aborta;
   - dos ejecuciones concurrentes: la segunda sale sin escribir;
   - `IGNORED_ALREADY_OPEN` decidido en la fase `SIGNAL`, sin orden;
   - un split 2:1 con ~200 barras previas: la vista de señal no mezcla escalas (SMA200 y ATR
     continuos);
   - un dividendo observado antes de un split y abonado tarde después de `SPLIT_ADJUST` se abona con
     las unidades y el importe en la misma base (no `r` veces de más);
   - el contexto sale de `PointInTimeContextResolver` sobre cierres guardados sin ajuste por
     dividendos;
   - repetir la ejecución de una pasada después de otra posterior da las mismas entradas (acotadas a
     `observed_at` ≤ fin de la ejecución original);
   - `paper_open_check` se escribe para toda señal vinculante OPERAR, haya o no posición;
   - una orden pendiente sobre una barra aún no observada detiene la frontera;
   - un lote cortado a mitad se reanuda con el mismo sizing que una pasada limpia;
   - un dividendo no reescala ninguna posición; solo un `SPLIT` observado lo hace;
   - el camino de precios es `get_raw_history` (`auto_adjust=False`) y nunca `validated_bar`;
   - stop y objetivo en la misma barra → stop;
   - hueco al alza → `ABOVE_MAX_ENTRY`;
   - festivo y media sesión;
   - barra de entrada ausente y su límite (§7.2);
   - dividendo tardío sin reescritura;
   - split 2:1 y contrasplit con posición abierta; `SCALE_MISMATCH` sin reajuste;
   - `DATA_LOSS_SUSPENDED` tras 20 sesiones: sin salida, sin P&L, cash sin cambios, valoración
     `STALE`; reanudación con `DATA_RESUMED` desde la primera barra real, con hueco bajo el stop a la
     apertura; una barra tardía del periodo perdido no se procesa;
   - cohorte cerrada con una posición suspendida → `NO_EVALUABLE_DATA_LOSS`, sin `paper_trade_outcome`;
   - `EXIT_CORPORATE_ACTION` solo con un `TERMINAL` verificable, en fecha o `late`;
   - `ABORTED_INVALID_ENGINE` congela la cohorte: ningún evento posterior, ninguna salida;
   - una cohorte no se procesa si su `t025_code_sha` no coincide (`IDENTITY_MISMATCH`);
   - FX ausente → el evento espera;
   - los triggers impiden `UPDATE` y `DELETE`;
   - la capa de visibilidad no deja ver lo sellado (lista cerrada de columnas) y cumple el contrato de
     §10.5 completo, incluida la igualdad byte a byte de la salida visible de dos libros con distintos
     desenlaces;
   - una ventana `P7_WINDOW` sella también lo acumulado después de ella hasta la consulta de P7;
   - el compromiso de sellado cambia en cada ejecución aunque no haya filas selladas nuevas;
   - `paper/` se niega a abrir una base sin su `application_id`;
   - `seguimiento`, `posiciones` y `cerrar` no ven ninguna fila paper;
   - reconstrucción byte a byte.
4. **Revisión independiente** de look-ahead y de idempotencia antes de desplegar.
5. Despliegue en la Pi como tag, en el checkout habitual (`/home/fer/intradia-bot`) y con unidad
   systemd propia tras cada pasada programada. **Nunca** en el worktree de T-024 ni en
   `t024/forward`. Si el tag cambia `requirements.txt` o el venv del bot, antes T-024 tiene que tener
   su propio venv (D-77, paso 7).
   **Consecuencia declarada:** ese tag saca el analizador de la Pi de `v0.4.1` (`8b2dddb` no tiene
   `advisor/context/point_in_time.py`, y `scoring.py` y `main.py` cambian). T-024 §7 usa las
   recomendaciones de C0 de la Pi solo como contraste descriptivo, y ese contraste queda etiquetado por
   versión. Antes de desplegar se registra en una D-nn.

## 17. Decisiones del propietario (OD-T25) — todas CERRADAS el 2026-10-07 (D-75)

Formato de `docs/decision-log.md`. Se conservan la pregunta y las alternativas que se presentaron; manda
la decisión. Ya no bloquean la congelación: falta la revisión final del propietario.

### OD-T25-1 — Arquitectura de persistencia y código · CERRADA (D-75)
- **Pregunta:** ¿dónde viven los datos y el código paper?
- **Alternativas presentadas:** (A) `paper.db` aparte y paquete `paper/` fuera de los
  `EXECUTOR_PATHS` (§4); (B) tablas `paper_*` en `intradia.db` (migración v8) y código en `advisor/`.
- **Decisión del propietario: A, arquitectura separada.** `paper.db` independiente de `intradia.db`;
  `PRAGMA application_id` propio; esquema y migraciones propios; paquete raíz `paper/`, separado de
  `advisor/`; comandos propios; ningún comando existente de posiciones manuales lee `paper.db`. La
  separación entre real/manual y paper es **por construcción, no por filtros**. No se reutilizan
  `position` ni `position_review`.

### OD-T25-2 — Capital inicial · CERRADA (D-75)
- **Alternativas presentadas:** (A) 100.000 EUR por cohorte, como P6; (B) un capital realista para
  Trade Republic (por ejemplo 10.000 EUR); (C) otro.
- **Decisión del propietario: A.** **100.000 EUR** de capital inicial por cohorte y libro, para mantener
  la comparabilidad directa con P6. El capital de B2 y el de S2 no se comparten.

### OD-T25-3 — Libros de B2 y S2 · CERRADA (D-75)
- **Alternativas presentadas:** (A) libros independientes, como P6; (B) un libro común con una regla de
  prioridad entre B2 y S2.
- **Decisión del propietario: A.** B2 y S2 operan como libros independientes, como en P6. Cada uno tiene
  sus propios 100.000 EUR iniciales, cash, equity, posiciones, ledger, costes y resultados. Una
  operación de B2 no consume capital de S2 ni al revés. C0 es también un control separado.

### OD-T25-4 — Visibilidad durante el embargo de T-024 · CERRADA (D-75), con D-76
- **Alternativas presentadas:** (A) sellar C0 como B2 y S2; (B) C0 visible; (C) C0 visible solo
  agregado y mensual; y para B2 y S2, (D) la señal con sus niveles y su comprobación de apertura o (E)
  solo los conteos de T-024 §6.3. La recomendación técnica era A + E.
- **Decisión del propietario (cambia la recomendación): visibilidad ex ante, desenlaces sellados.**
  T-025 tiene que ser útil como bot desde el principio. Durante el embargo de T-024 **sí** se ve la
  información ex ante de las recomendaciones de B2 y S2, y **no** sus desenlaces:
  - **visible:** fecha y hora de la señal, activo, política, `entry_max`, stop, objetivos, RR, tamaño
    solicitado, ejecución simulada de entrada, precio de entrada si se ejecutó, rechazos de entrada y
    su motivo;
  - **sellado:** si después la posición sigue abierta o cerrada, timestamp y motivo de salida, stop u
    objetivo alcanzado, precio de salida, P&L, `net_R`, MAE, MFE, duración final, cash y equity
    derivados de desenlaces, PF, win rate, drawdown, CAGR, exceso de CAGR, cualquier métrica agregada
    que revele resultados, el progreso o la frontera que permita inferirlos y **cualquier otro canal
    lateral identificado por la revisión**;
  - el motor calcula internamente todo lo necesario para una cartera causal; los desenlaces se
    persisten, sellados para el propietario, el dashboard, la CLI normal, Telegram, Claude, Codex y
    cualquier agente de análisis;
  - **C0:** dado su solapamiento con B2 y S2, también queda sellado en desenlaces y P&L durante el mismo
    embargo; su información ex ante puede almacenarse y verse. No se usa como vía lateral;
  - **naturaleza de la ceguera:** T-024 conserva intactos pre-registro, código, métricas, criterios,
    calendario de miradas, ejecución automática, D2 y reglas de decisión, pero la ceguera humana deja
    de ser absoluta. **T-024 conserva su diseño confirmatorio pre-registrado, con visibilidad parcial ex
    ante del propietario declarada antes de observar desenlaces.** No se modifica retrospectivamente su
    pre-registro; la exposición se registra en **D-76** antes de ejecutar T-025.
- **Aplicación (ronda 4):** «tamaño solicitado» y «ejecución simulada» se muestran en su forma por
  política (fracción de la equity; comprobación de apertura), porque su forma por libro es un canal
  lateral hacia la equity y el estado de las posiciones (§10.2).

### OD-T25-5 — Barra de entrada ausente · CERRADA (D-75)
- **Alternativas presentadas:** (A) esperar hasta el cierre de la 5.ª sesión hábil y aplicar el salto de
  P6; (B) rechazar en cuanto falte.
- **Decisión del propietario: A.** Se espera hasta el cierre de la 5.ª sesión hábil posterior; si la
  barra sigue sin aparecer, se aplica la misma semántica de salto de P6; el hecho se registra
  explícitamente; una barra aparecida después se registra como tardía y jamás reescribe decisiones
  (§7.2).

### OD-T25-6 — Dividendos conocidos tarde · CERRADA (D-75)
- **Alternativas presentadas:** (A) abono causal posterior marcado `late`; (B) reescribir el cash desde
  la fecha ex.
- **Decisión del propietario: A.** Un dividendo conocido tarde se registra cuando se conoce, se abona
  causalmente en la primera sesión procesada posterior, queda marcado `late` y no reescribe balances,
  tamaños ni decisiones anteriores (§8.5).

### OD-T25-7 — Activo sin datos de forma prolongada · CERRADA (D-75), modificada por el propietario
- **Alternativas presentadas:** (A) `EXIT_DATA_LOSS` al último cierre validado tras 20 sesiones; (B)
  mantener la posición abierta indefinidamente y avisar.
- **Decisión del propietario: ninguna de las dos tal cual. No se fabrica una venta.** Tras 20 sesiones
  hábiles consecutivas sin datos suficientes, la posición pasa a `DATA_LOSS / SUSPENDED`: sin
  `exit_price` sintético, sin P&L ficticio, sin usar el último cierre como ejecutable; el capital queda
  bloqueado; se genera una alerta operativa y el caso queda identificado. Si vuelven datos válidos, se
  reanuda el procesamiento causal desde información realmente observada, sin reescribir el periodo
  perdido. Si la cohorte termina sin datos suficientes, la operación queda `NO_EVALUABLE_DATA_LOSS`,
  se informa por separado y no se inventa un resultado. Una salida real verificable (delisting,
  liquidación, corporate action con precio de liquidación verificable) se trata con una regla
  específica y documentada, no con el fallback de 20 sesiones (§8.7).

### OD-T25-8 — Cohortes y versiones del motor · CERRADA (D-75)
- **Alternativas presentadas:** (A) un motor nuevo abre una cohorte nueva y la vieja sigue con su motor
  congelado; (B) la vieja se cierra al desplegar un motor nuevo.
- **Decisión del propietario: A, con una precisión.** Una versión nueva del motor crea una cohorte
  nueva; la antigua continúa bajo su motor y su contrato congelados; no se migra en silencio ni se
  mezclan resultados. **Excepción:** un defecto crítico que invalide materialmente la ejecución de una
  cohorte la congela y la declara `ABORTED_INVALID_ENGINE`, con la causa documentada; su historia nunca
  se corrige retrospectivamente, y una versión corregida abre una cohorte nueva (§13).

### OD-T25-9 — Alcance del consumo y ventana de P7 · CERRADA (D-75)
- **Alternativas presentadas:** unidad de consumo (A) la sesión o (B) `(política, sesión)`; ventana de
  P7 (C) sellada en todas las cohortes o (D) sin medidas.
- **Decisión del propietario: A + C.** La unidad conservadora es la **sesión**: consultar un desenlace
  de cualquier política o cohorte de T-025 en una sesión la consume, sin usar `(política, sesión)` como
  escapatoria. Cuando exista una candidata válida para P7, su ventana se fija antes de empezar, y desde
  ese momento **todas** las cohortes T-025 quedan selladas para esas sesiones: T-025 sigue funcionando
  y registrando, pero esos desenlaces no se consultan ni aparecen en el dashboard, la CLI o Telegram,
  ni son accesibles a agentes. Tras la consulta única del holdout de P7 se registra formalmente su
  consumo (§10.6, §10.7).

## 18. Riesgos y limitaciones

- **Sellado procedimental** (§10.4): no es criptográfico.
- **Meses sin P&L de B2, S2 ni C0** (D-75): el propietario ve qué compraría el bot cada día, pero no
  cómo le va hasta que T-024 se resuelve (7 a 13 meses, o más). Solo BH tiene P&L visible.
- **Ceguera parcial de T-024** (D-76): con las señales ex ante y precios públicos se pueden deducir
  resultados a mano. T-024 no tiene pasos discrecionales que dependan de desenlaces, pero sí decisiones
  humanas residuales (qué hacer con un checkpoint `NO_APTA` o `ERROR_*`, abandonar T-024); se toman con
  esa exposición declarada.
- **`DATA_LOSS` puede bloquear capital** hasta el final de una cohorte (D-75): el capital bloqueado se
  publica aparte y la operación puede quedar `NO_EVALUABLE_DATA_LOSS`.
- **Cohortes antiguas y su worktree** (§13): mantener varias cohortes vivas exige un worktree por
  `t025_code_sha` en la Pi; sin él, la cohorte pierde señales.
- **Datos de `yfinance`:** retraso europeo, revisiones y reajustes. Se mitigan con el almacén propio,
  la primera observación vigente, la vista de señal ajustada por splits y los eventos explícitos de §8,
  pero no desaparecen.
- **Fraccionales y liquidación inmediata:** las mismas simplificaciones que en P6.
- **La Pi** es un único dispositivo, en desarrollo/integración, y una caída hace perder señales
  (`SIGNAL_NOT_EVALUATED`). C-06 (backups) es prioridad alta antes de acumular meses de registro.
- **Interacción con T-024** (§3.8): resuelta con `t024/forward` (D-77), que exige disciplina: crearla
  antes del primer cambio en los `EXECUTOR_PATHS` de `main`, no fusionar nunca en ella esos cambios y
  darle a T-024 su propio venv antes de que el venv del bot cambie.
- **Versión de la Pi:** desplegar T-025 saca el analizador de `v0.4.1` (§16.5).
- **Desellado conjunto** (§10.1): si S2 llega a la mirada final, B2 (y C0) siguen sellados aunque B2
  ya tenga resultado; el P&L puede tardar hasta el final de T-024.
- **Ventana de P7** (§10.7): mientras esté sellada, y hasta su consulta única, el dashboard vuelve a
  no tener P&L de ninguna cohorte para esas sesiones ni para lo acumulado sobre ellas.
- Universo condicionado a 2026; T-025 no lo corrige.

## Verificación contra datos reales

**No aplica en esta entrega:** es documental, y el encargo prohíbe descargar datos forward u observar
desenlaces. Lo que sí se verificó contra el repositorio está en el handoff. En la implementación, antes
de desplegar:
- una ejecución sin red y otra con red sobre `paper.db` vacía, sin libros activos (solo evaluaciones),
  con un número comprobado a mano: los niveles de una señal recalculados desde las barras guardadas;
- la comprobación de que la base de precios es la de P6 (`auto_adjust=False`), comparando una barra
  guardada con la misma sesión de `get_raw_history`.

## Medición del impacto

**No aplica en esta entrega:** no cambia el código, las recomendaciones ni ninguna población. En la
implementación:
- `intradia.db`, el informe y `seguimiento` no cambian (0 activos afectados, comprobado por conteos
  antes y después);
- el único efecto es el despliegue de un tag nuevo en la Pi (§16.5), que se mide como cualquier
  release.

## Criterio de aceptación (de esta entrega documental)

- La ficha recorre todos los apartados del encargo (§1–§17) y no queda ninguna regla sin fijar ni sin
  marcar como OD.
- Ninguna OD se da por cerrada sin una decisión del propietario. Las OD-T25-1..9 y OD-12 se cierran
  con su decisión literal (D-75, D-77), y la ficha no conserva texto incompatible con ellas.
- El roadmap, el decision log y `docs/gates.md` son coherentes con esta ficha.
- La revisión independiente queda sin BLOCKER ni IMPORTANTE abiertos.
- `pytest`, `ruff` y `mypy` dan lo mismo que la línea base, y no cambia ningún fichero de los
  `EXECUTOR_PATHS`.

## Criterio de rechazo

Cualquiera de estos: una regla de P6 cambiada sin OD; una lectura de desenlaces de B2, S2 o C0
permitida durante el embargo, o de cualquier cohorte en una ventana de P7, salvo por la vía
extraordinaria registrada; un canal lateral visible hacia esos desenlaces; una salida sintética; una
ruta por la que una fila paper pueda aparecer como posición real; un cambio en los `EXECUTOR_PATHS`;
código funcional en esta entrega.

## Evidencia que debe quedar registrada

- Esta entrega: la ficha, el roadmap, el decision log, `docs/gates.md` y la revisión, en
  `evidence/2026-10-06-T-025-diseno/`, con la salida de `pytest`, `ruff` y `mypy`.
- Implementación: `evidence/<fecha>-T-025-codigo/` con los tests, la equivalencia y la revisión.
- Registro forward: `paper.db` fuera del repositorio, con su ruta y su hash periódicos en
  `evidence/T-025-forward/`, y los compromisos de sellado. **Su tamaño no se publica mientras rija un
  sellado** (§10.3).

## Commit esperado

Rama `research/t025-shadow-prereg`: `docs(T-025): diseño y pre-registro propuesto del shadow/paper
trading forward`, más commits separados para el roadmap y las decisiones.

## Actualización documental requerida

`docs/roadmap.md` (S-01, S-02, Línea S, presupuesto de datos, orden y fechas de T-024),
`docs/decision-log.md` (D-73 a D-77, OD-12 y las OD-T25 cerradas), `docs/gates.md` (GATE P7 y GATE
P10) y la ficha de PAPER-001 (visibilidad parcial de T-024).

## Handoff al siguiente agente

- **Estado:** pre-registro propuesto con OD-T25-1..9 y OD-12 cerradas (D-75, D-77) y la visibilidad
  parcial de T-024 declarada (D-76). Sin congelar: espera la revisión final del propietario del PR #48.
- **Verificado:**
  - inventario del código citado en §3, leído el 2026-10-06; la semántica de valoración de P6
    (`mark_price` al último cierre) y el tamaño de `p6_sim._process_entries`, el 2026-10-07;
  - igualdad de los `EXECUTOR_PATHS` de `main` (`f80ab28`) y de la cabeza de la rama con `1a697c3`, y
    `verificar_identidad()`;
  - que el informe diario de la Pi ya muestra niveles ex ante de C0 (`advisor/report/formatter.py`),
    declarado en D-76;
  - hashes de §0 leídos de `politicas-finales.json` y de `system-hashes.json`;
  - línea base de §0.
- **Pendiente:** la revisión final del propietario, la congelación de `T025_PREREG_SHA`, la creación de
  `t024/forward` (D-77, antes del primer cambio en los `EXECUTOR_PATHS` de `main` y antes del
  2026-11-21) y, con autorización aparte, la implementación (§16).
- **Hallazgos:**
  - **FOLLOW_UP:** el informe de la Pi y la caché C-09 trabajan sobre OHLC ajustado por dividendos, y
    P6 y T-024 sobre OHLC sin ese ajuste (§3.3). No es un defecto de T-025, pero cualquier comparación
    entre el informe de C0 y los resultados del laboratorio tiene que tenerlo en cuenta.
  - **FOLLOW_UP:** T-024 usa hoy el venv del bot en la Pi; su identidad no cubre las versiones
    instaladas. Antes de cualquier despliegue que cambie ese venv, T-024 necesita su propio venv (D-77).
  - **OBSERVATION:** el texto anterior del roadmap atribuía a S2 una exposición media de 0,5313, que es
    la de C0; la de S2 es 0,6054 (T-023, `hallazgos.md` §B). Corregido en la entrega anterior.

## Revisión independiente del diseño

**Ronda 1 (2026-10-06, sobre `b25f5ba`).** Dos revisores independientes y de solo lectura: Codex y el
subagente `revisor`. Detalle en `evidence/2026-10-06-T-025-diseno/revision-ronda1.md`. Cada hallazgo
se verificó contra el repositorio antes de corregirlo.

| Hallazgo | Clase | Corrección |
|---|---|---|
| La fuente de precios (caché C-09, OHLC ajustado por dividendos) no es la base de P6: el dividendo se contaba dos veces y los reajustes por dividendo se trataban como splits | **BLOCKER** (revisor) | §3.3: precios de `get_raw_history` (`auto_adjust=False`) en un almacén propio; solo un `SPLIT` observado reescala; `paper_corporate_action` (§5, §8.5, §8.6) |
| D-73 §3 rebajaba la regla de «consumido» del propietario | **BLOCKER** (Codex) / IMPORTANTE (revisor) | Se aplica la regla literal (D-74 §3); la unidad de consumo y la ventana de P7 pasan a OD-T25-9 (§10) |
| El orden de comprobaciones de entrada no era el de `p6_sim` | IMPORTANTE (Codex) / MENOR (revisor) | §7.2 sigue `p6_sim.py:615-636` |
| «Lo visible es lo mismo que T-024 §6.3» era falso | IMPORTANTE (los dos) | §10 lo declara como límite del ciego y OD-T25-4 pregunta entre la opción D y la E |
| El desellado por política deja que B2 revele a S2 | IMPORTANTE (revisor) | Desellado conjunto, medido: S2 ⊂ B2 en P6 (§10, D-73 §2) |
| Las comprobaciones de apertura delataban `IGNORED_ALREADY_OPEN` | IMPORTANTE (revisor) | `paper_open_check` por política y sin libro (§5, §7.1, §10) |
| Canales laterales: `max_seq`, frontera, bloqueos y recuentos | IMPORTANTE (revisor) | Lista cerrada de lo visible (§10); `paper_cohort_progress` sellada; el compromiso solo lleva el hash |
| Una orden pendiente podía quedar detrás de la frontera | IMPORTANTE (revisor) | La frontera espera también a los activos con orden pendiente (§8.7, §12) |
| Los dividendos no se persistían | IMPORTANTE (revisor) | `paper_corporate_action` (§5) |
| PAPER-001: «edge» frente a «ventaja» | IMPORTANTE (Codex) | Vocabulario fijado en la ficha de PAPER-001 |
| `EXECUTOR_PATHS` incompletos en §3.8 | MENOR | Las seis rutas |
| El dashboard y P10 «salen todos de §5» | MENOR (los dos) | Tres diferencias declaradas (§14, `gates.md`) |
| «C0 comparte casi toda la población» no cuadraba | MENOR (revisor) | Medido en los ledgers de P6 y corregido (§10, OD-T25-4) |
| El hash de C0 no está en `politicas-finales.json` | MENOR | Sale de `p6.py:95-100` (§6) |
| Una transacción por evento rompía el sizing al reanudar | MENOR | Una transacción por lote τ con `lot_equity_eur` (§12) |
| Claves de idempotencia frágiles | MENOR | `source_id` en los eventos y `content_sha256` sin metadatos (§5, §12) |
| `IGNORED_ALREADY_OPEN` en dos instantes distintos | MENOR | Fase `SIGNAL`, sin orden (§7.1, §8.4) |
| `start_ts_utc` ambiguo con 9 plazas | MENOR | Fecha `d` y primera apertura de cada activo (§6) |
| Plantilla del método incompleta | MENOR | Estado de la lista cerrada; secciones de verificación e impacto «No aplica» con motivo |
| La evidencia de la entrega estaba vacía; el tag saca la Pi de `v0.4.1`; podían salir dos `signal_id` para una sesión; `observed_at < τ` | OBSERVACIÓN | Evidencia de la revisión añadida en la ronda 1 y la de verificación en la ronda 2; §16.5 y §18; unicidad `(cohort, instrument, session)`; `max_input_observed_at` |

**Ronda 2 (2026-10-06, sobre `4eeb9a1`).** Los mismos dos revisores. Detalle en
`evidence/2026-10-06-T-025-diseno/revision-ronda2.md`. **Los dos confirman resueltos el BLOCKER y
los IMPORTANTES de la ronda 1, sin BLOCKER nuevo.** Hallazgos nuevos, verificados y corregidos:

| Hallazgo | Clase | Corrección |
|---|---|---|
| A-07 del roadmap conservaba la versión débil de «consumido» | IMPORTANTE (Codex) | Regla literal y ventana sellada (OD-T25-9) |
| La visibilidad por señal de B2 y S2 (niveles y comprobación de apertura) excede T-024 §6.3 y el runbook | IMPORTANTE (Codex) | **La opción por defecto pasa a ser E** (solo conteos agregados de T-024); D queda como elección del propietario en OD-T25-4 (§10) |
| Tras un split, la serie de señal mezcla dos escalas; un dividendo tardío tras un split se abonaba `r` veces | IMPORTANTE (revisor) | Vista de señal derivada, ajustada por los splits observados, sin reescribir filas (§3.3); derecho e importe en la misma base (§8.5); tests |
| El contexto point-in-time por la función pública usaría cierres ajustados por dividendos | MENOR (revisor) | `PointInTimeContextResolver` sobre cierres crudos guardados, como P6 (§3.3, §5) |
| `paper_outcome_access` sin las sesiones consultadas | MENOR (revisor) | `sessions_json` (§5) |
| OD-T25-4 infravaloraba la fuga hacia S2 | MENOR (revisor) | Cifras del 99 % y el 23 % |
| §18 citaba la caché como mitigación | MENOR (revisor) | Retirado |
| Faltaba la salida de pytest, ruff y mypy en la evidencia | MENOR (revisor) | `evidence/2026-10-06-T-025-diseno/verificacion.txt` |
| Repetir una pasada podía usar observaciones de pasadas posteriores | MENOR (revisor) | Entradas acotadas al fin de la ejecución original (§5, §7.1) |
| La lista del dashboard estaba incompleta | MENOR (Codex) | Completada (§14) |
| Unidad de consumo pendiente; BH; T-024 que no se resuelva | OBSERVACIÓN (revisor) | Declarados en OD-T25-9, `gates.md` y OD-T25-4 |

Las correcciones de la ronda 2 pasaron una ronda 3 (abajo). Lo que queda abierto son decisiones del
propietario (OD-T25-1..9, OD-12). Una revisión final del pre-registro completo, tras esas decisiones, es
condición para congelar.

**Ronda 3 (Codex, 2026-10-06, sobre `6a75bcf`): 0 BLOCKER, 1 IMPORTANTE, 0 MENOR.** Los dos
IMPORTANTES de la ronda 2 quedan resueltos, y la vista de señal ajustada por splits, el dividendo
tardío tras split, el contexto con `PointInTimeContextResolver` y las sesiones en
`paper_outcome_access` están bien planteados.
- **IMPORTANTE:** acotar las entradas al fin de la ejecución dejaba entrar observaciones posteriores al
  `analysis_timestamp` programado. **Corrección:** §7.1 separa `analysis_timestamp`, referencia PIT de
  `available_at` como en P6, de `decision_ts` (fin de la ejecución, anterior a la apertura), que acota
  `observed_at`. La alternativa del revisor (`observed_at ≤ analysis_timestamp`) no es viable en vivo,
  porque la pasada descarga después de su hora programada. T25-2 se reescribe con los dos instantes.
- **Sin revisar en una ronda 4:** esta última corrección. La revisión final del pre-registro completo,
  tras las decisiones del propietario, la cubrirá.
