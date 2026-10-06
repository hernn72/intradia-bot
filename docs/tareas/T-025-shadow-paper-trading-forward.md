# T-025 — Shadow/Paper Trading Forward diario: B2 y S2 operando en el tiempo, sin dinero real (S-01)

Estado: **EN DISEÑO — PRE-REGISTRO PROPUESTO, NO CONGELADO.** Queda **BLOQUEADA_POR_OWNER** en las
decisiones OD-T25-1 a OD-T25-8 (§17) y en OD-12 (`docs/decision-log.md`). No hay código, ni tablas,
ni paper broker. No se ha descargado ningún dato forward ni observado ningún desenlace. B2 y S2 no
cambian. La Pi no se ha tocado.

Agente: Opus (diseño) → revisión independiente → propietario (OD) → congelación.
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
| Base | `main = 4170bb4bc0434436e16aced39bfd907fedebaea0` (merge del PR #46). La rama parte de `0918cb3` (PR #47, estado del roadmap, sin fusionar), que solo cambia `docs/roadmap.md` |
| Decisiones | D-70 (P6 `[]`), D-71 y D-72 (T-024), **D-73** (reorientación y sellado de T-025), **D-74** (apertura de T-025) |
| Políticas | `evidence/2026-10-03-T-021-p5-cierre/politicas-finales.json` (`sha256 fa027058…9fd9f6b`; esquema `intradia.p5.politicas_finales.v1`; `p5_prereg_sha a7c3d238…`) |
| B2 | `policy_sha256 d5d6a533fe846a6ebb5d5c8e313c84f2a5b4e04095d08386e5d903dce73101b9`; `advisor_config_hash c5d60f44e89a754f34dfc685cda5073af1c0f9dbb04ab3ec14a813d423f81760`; sistema P6 primario `system_sha256 010977688a180cc63d22111f2dcb520c937ba39bb63fbb88082c30a061724026` |
| S2 | `policy_sha256 e37ee93363dbbd7c58cae74bba4391ab9ad41dd1f3ed55804a92efb531e44d11`; `advisor_config_hash 8a151b80d91bf73e431ec38e5e21f22268783bbd0a26d5f72e6ef8887aca0dbb`; `system_sha256 824a1dff2d1bf1e6d89b842b9606887cec5eed28f3b76448f947dfbb28d39a69` |
| C0 (control) | `policy_sha256 80e21111a88c1eeac94c2ecef6b8bc480a505a045ca90f6a91a0ba6fc4ffd29a`; `advisor_config_hash 89406d28c7b4b6e6c4f032cd63b6868c927af3e926dfb52d430dfa6654d06387`; `system_sha256 18956fb61823c4cfbf625b1581ef15f6048a1096134d50c00404f76b12fd99e8` |
| Contrato del sistema | El de P6 (`docs/tareas/T-022-p6-sistema-completo.md` §7–§19, D-69), `P6_PREREG_SHA 03f04a42…`, `P6_CODE_SHA bc0636d4…`; hashes en `evidence/2026-10-03-T-022-p6/preflight/system-hashes.json` |
| Universo | El de P6: 90 activos, `asset_list_sha256 36355796a57e55a68ea16957b7edc6975360fb2085e7fd91841d20e2d7812f50`, `universe_vintage_id 237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19` |
| T-024 | `T024_PREREG_SHA dfcca0ef3428df916089480a0ca574f47e550c24`, `T024_CODE_SHA 1a697c3fa2ab76ddfcf567c2ef3f5ab56492eaf0`. `EXECUTOR_PATHS` de `main` idénticos a `1a697c3` (comprobado con `git diff --quiet` el 2026-10-06) |
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
- No toca T-024: ni su pre-registro, ni su código, ni sus `EXECUTOR_PATHS`, ni el worktree de la Pi,
  ni sus cosechas, ni sus conteos.
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

### 3.3 Caché de barras validadas (C-09): fuente de precios

`validated_bar` y `validated_bar_revision` (migración v6, `advisor/data/bar_cache.py`, D-41 y D-44):
- guardan cada barra de sesión cerrada tal como se observó por primera vez, con `observed_at`,
  `provider` y `run_id`;
- ante una revisión aislada, **manda la primera validada**;
- un `REAJUSTE` (split o reajuste de la serie) reancla la caché con un `factor`.

Es la base natural de T-025: las fills y las salidas se resuelven sobre barras de sesión cerrada ya
validadas. **Riesgo:** el reanclaje cambia la escala de barras ya guardadas, y un stop guardado en la
escala vieja daría una salida falsa. Por eso T-025 copia a su propio almacén las barras que usa y
trata los reajustes como un evento explícito (§8.6).

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

**Consecuencia:** cualquier commit en `main` que toque `advisor/`, `config.yaml` o `universe.yaml`
deja de servir para operar T-024. Afecta a T-025, a P6-bis, a C-04 y a C-05 por igual. **Esta entrega
no toca ningún `EXECUTOR_PATHS`.** Antes de fusionar la primera implementación que los toque, el
propietario tiene que decidir OD-12 (`docs/decision-log.md`).

### 3.9 Qué falta

No hay en el repositorio: libro paper, orden paper, fill, posición paper, ledger de cash de cartera
en vivo, instantáneas de equity en vivo, desenlaces forward, sellado, registro de consumo ni
benchmark forward. Todo eso es persistencia nueva (§5).

## 4. Decisión arquitectónica: separar lo real de lo paper (propuesta para OD-T25-1)

**Propuesta: una base SQLite propia y un código fuera de `advisor/`.**

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
2. **Identidad de T-024 intacta.** Un paquete fuera de `advisor/` y sin tocar `config.yaml` deja los
   `EXECUTOR_PATHS` de `main` idénticos a `1a697c3`. T-024 se puede seguir operando desde `main`
   mientras ninguna otra tarea los toque (OD-12).
3. **Sin migración de la base de la Pi.** `intradia.db` sigue en v7: no hay migración irreversible
   (D-32) ni copia previa que coordinar.
4. **Reconstrucción.** `paper.db` contiene todo lo que T-025 usó: barras, FX, señales y decisiones.
   Una operación se reconstruye sin depender de que la caché de `intradia.db` no se haya reanclado.

Costes declarados:
- **INV-06** (una función, varios llamantes): `paper/` llama a `build_snapshot_series`, a la
  configuración de las políticas y a los niveles de `advisor` y **no los copia**. Si necesita algo que
  `advisor` no expone, eso es un cambio en `EXECUTOR_PATHS` y espera a OD-12.
- La CI tiene que ejecutar también `mypy paper` y los tests de `paper/`. Se cambia
  `.github/workflows/ci.yml`, que no está en los `EXECUTOR_PATHS`.
- No hay claves foráneas entre bases. `source_run_id` y `source_recommendation_id` son referencias
  verificadas por el código (existencia y hash de la fila), no restricciones de SQLite.

Alternativa B (tablas `paper_*` en `intradia.db`, migración v8 y código en `advisor/`): la separación
se haría solo por nombre de tabla, obligaría a migrar la base de la Pi y rompería la identidad de
T-024 en `main` desde el primer commit. Solo es razonable si OD-12 abre antes la línea dedicada de
T-024.

## 5. Contrato de persistencia (para la tarea de implementación; nada se crea ahora)

Reglas generales:
- **Append-only:** ninguna fila de hechos se actualiza ni se borra. Unos triggers `BEFORE UPDATE` y
  `BEFORE DELETE` con `RAISE(ABORT)` lo garantizan en las tablas de hechos. Lo derivado (estado
  actual, vistas) se reconstruye desde los hechos.
- Toda fila de hechos lleva `cohort_id`, `paper_run_id`, `computed_at` (hora de reloj en que se
  escribió) y, si es un evento económico, `event_ts_utc` (el instante τ que representa) y `phase`.
- Los precios se guardan en divisa local y en EUR (`*_local`, `*_eur`), con el FX y su
  `fx_timestamp_available`.
- Los booleanos y los estados son textos de lista cerrada con `CHECK`.

| Tabla | Una fila por | Campos mínimos | Unicidad / idempotencia |
|---|---|---|---|
| `paper_cohort` | libro (B2, S2, C0, BH) y versión | `cohort_id`, `book_kind = 'PAPER'` (CHECK), `policy_id`, `policy_sha256`, `advisor_config_hash`, `p6_system_sha256` de referencia, `t025_system_sha256` (§13), `engine_version`, `t025_prereg_sha`, `t025_code_sha`, `release_tag`, `capital_inicial_eur`, `base_currency`, `asset_list_sha256`, `universe_vintage_id`, `start_session_rule`, `start_ts_utc`, `sealed_until_rule`, `label`, `created_at` | `cohort_id` = sha256 canónico de su contrato |
| `paper_run` | ejecución de T-025 | `paper_run_id`, `source_run_id` (pasada de `intradia.db`), manifiesto completo (como `RunManifest`), `paper_schema_version`, `engine_version`, `started_at`, `finished_at`, `status`, `frontier_ts_utc` por cohorte, `inputs_sha256` | `paper_run_id` |
| `paper_bar_observation` | barra de sesión cerrada usada | `data_symbol`, `market`, `session_date`, `bar_timestamp` crudo (INV-13), OHLCV, `observed_at`, `provider`, `source` (`validated_bar` o descarga), `validated_bar_id`, `scale_anchor` | `(data_symbol, session_date, observed_at)`; la vigente para una sesión es la primera observada |
| `paper_bar_adjustment` | reajuste de escala detectado | `data_symbol`, `kind` (`SPLIT`/`REAJUSTE`), `factor`, `effective_session`, `detected_at`, `evidence` | `(data_symbol, effective_session, kind)` |
| `paper_fx_quote` | barra FX usada | `fx_pair`, `bar_timestamp`, `timestamp_available` (= marca + 24 h), `rate`, `provider`, `observed_at` | `(fx_pair, bar_timestamp)`; manda la primera observada |
| `paper_context_observation` | dato de contexto usado | serie (`^VIX`, `^STOXX50E`, Asia), marca, valor, `observed_at`, `source = point_in_time` | `(serie, marca)` |
| `paper_signal_evaluation` | (cohorte, activo, sesión `t`, pasada) | `signal_id` (`stable_signal_id`), `instrument_id`, `symbol`, `data_symbol`, `market`, `signal_session_date`, `pass_scheduled_ts`, `analysis_timestamp`, `bar_t_observation_id`, `reference_price` (cierre de `t`), `entry_max`, `stop`, `target1`, `target2`, `target3`, `rr_at_reference`, `risk_fraction`, `score`, `score_model_version`, `setup_radar`, `setup_accion`, `operar` (sí/no), `context_snapshot_json`, `data_quality` y frescura, `reasons`, `source_recommendation_id` (solo enlace) | `(cohort_id, signal_id, pass_scheduled_ts)` |
| `paper_order` | señal vinculante (§7.1) | `order_id`, `cohort_id`, `signal_id`, `binding_evaluation_id`, `target_session` (primera sesión de calendario > `t`), `order_type = OPEN_NEXT_BAR_WITH_MAX` | `(cohort_id, signal_id)` |
| `paper_entry_decision` | intento de entrada (fill o rechazo) | `order_id`, `event_ts_utc` (apertura), `lot_id`, `tiebreak_key`, `bar_observation_id`, `open_market`, `entry_effective`, `checks_json` (stop, objetivo, `entry_max`, RR, tamaño), `status` (`FILLED` o el código de rechazo de P6 §17), `equity_before_eur`, `cash_before_eur`, `open_positions_json` (ids y hash), `requested_units`, `requested_cash_eur`, `units`, `notional_eur`, `fee_eur`, `slippage_eur`, `fx_rate`, `fx_timestamp_available`, `risk_local`, `risk_eur` | `order_id` (una decisión por orden) |
| `paper_position` | posición abierta (hecho de apertura) | `position_id`, `cohort_id`, `instrument_id`, `signal_id`, `entry_decision_id`, `units`, `entry_effective`, `stop`, `target2`, `max_hold_bars = 40`, `opened_ts_utc`, `scale_anchor` | `(cohort_id, signal_id)`; además, a lo sumo una abierta por `(cohort_id, instrument_id)` (§12) |
| `paper_position_event` | hecho sobre una posición | `seq`, `position_id`, `event_type` (`OPEN`, `MARK`, `SPLIT_ADJUST`, `DIVIDEND_ENTITLED`, `DIVIDEND_CREDIT`, `DATA_GAP`, `EXIT`), `event_ts_utc`, `phase`, `session_date`, `market_price`, `effective_price`, `units_before`, `units_after`, `reason`, `late` (sí/no), `input_ids` | `(position_id, event_type, session_date)` |
| `paper_ledger` | movimiento de caja | las columnas de `p6_sim.LEDGER_COLUMNS` más `cohort_id` y `paper_run_id` | `(cohort_id, seq)`; `seq` estrictamente creciente con `(event_ts_utc, phase, clave)` |
| `paper_equity_snapshot` | (cohorte, día) a las 23:59:59 UTC (P6 §13) | `equity_eur`, `cash_eur`, `long_value_eur`, `n_positions`, exposición por región, divisa y sector, `fx_set_hash` | `(cohort_id, snapshot_day)` |
| `paper_trade_outcome` | posición cerrada | `exit_ts_utc`, `exit_reason`, `exit_market`, `exit_effective`, `pnl_gross_local`, `pnl_gross_eur`, `pnl_net_local`, `pnl_net_eur`, `fees_eur`, `slippage_eur`, `dividends_eur`, `fx_pnl_eur`, `risk_initial_local`, `risk_initial_eur`, `net_R_local`, `net_R_eur`, `mae_R`, `mfe_R`, `duration_bars`, `duration_sessions`, `duration_days`, `exposure_eur_days`, `benchmark_return` (cohorte BH, §11) | `position_id` |
| `paper_seal_commitment` | (cohorte sellada, ejecución) | `cohort_id`, `paper_run_id`, `max_seq`, `sealed_rows_sha256` | `(cohort_id, paper_run_id)` |
| `paper_outcome_access` | lectura de desenlaces | `cohort_id`, `accessed_at`, `who`, `purpose`, `query`, `rows_sha256` | append-only; es el registro de consumo (§10) |

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
  sus hashes de §0, y la implementación los regenera desde `politicas-finales.json` y aborta si no
  coinciden byte a byte, como hizo el preflight de P6.
- **Libros independientes (propuesta para OD-T25-3):** cada política es un sistema con su propia
  cartera, su cash y su equity, como en P6 §1. B2 y S2 no compiten por el cash ni se bloquean entre
  sí. Pueden tener a la vez el mismo activo, cada una en su libro.
- **Capital (propuesta para OD-T25-2):** **100.000 EUR** por cohorte, iguales para B2, S2, C0 y BH.
  Es coherente con el diseño existente:
  - P6 usó 100.000 EUR (OD-P6-1);
  - con unidades **fraccionarias** y sin mínimos por operación (OD-P6-2), el resultado relativo es
    invariante a la escala del capital;
  - el capital vive en `paper_cohort`, no en `config.yaml`, cuyo `portfolio.capital: null` no se toca
    porque está en los `EXECUTOR_PATHS`.

  Limitación: Trade Republic no ofrece fraccionales en todos los instrumentos. Se declara; P6 tenía la
  misma.
- **Universo:** los 90 de P6 (`asset_list_sha256 36355796…`), sin altas ni bajas. Si un activo sale
  del universo vivo de la Pi, sigue en T-025 mientras haya barras (§8.7).
- **Inicio:** todas las cohortes arrancan planas (sin posiciones heredadas) con un `start_ts_utc`
  fijado en `paper_cohort` **antes** de la primera señal: la apertura de la primera sesión de calendario
  posterior al despliegue del tag congelado. BH compra en esa misma apertura (P6 §14).

## 7. Entrada

### 7.1 Señal emitida y señal vinculante

- La **evaluación** de `(cohorte, activo, sesión t)` es el predicado de la población P6
  (`OPERAR_score_v1_point_in_time`, broker neutral, contexto point-in-time) calculado con las barras de
  sesión cerrada **hasta `t` inclusive**, en una ejecución de T-025 asociada a una pasada programada.
  Se guarda como `paper_signal_evaluation`, aunque el resultado sea «no OPERAR».
- Cada pasada vuelve a evaluar las sesiones `t` cuya apertura siguiente todavía no ha llegado. Cada
  evaluación es una fila nueva e inmutable.
- **Señal vinculante (D-50):** la evaluación de la **última pasada programada cuya hora es anterior a
  la apertura de la sesión de entrada** y que tenía validada la barra `t`. Si dice OPERAR, crea la
  `paper_order`. La elección es determinista y solo usa marcas anteriores a la apertura.
- **Ninguna señal se crea después de la apertura.** Si no hubo ninguna pasada con la barra `t` antes de
  la apertura (la Pi caída, el proveedor sin la barra), el caso se cuenta como `SIGNAL_NOT_EVALUATED`
  y no hay orden. No se rellena hacia atrás.
- `signal_id = stable_signal_id(symbol, "swing", bar_timestamp_t)`: el mismo para las tres políticas,
  como en P6.

### 7.2 Sesión y precio de entrada

- La orden apunta a la **apertura de la barra siguiente de la serie del activo** (P6 §7.8), con la
  hora sacada del calendario efectivo: `exchange_calendars` 4.13.2 más `exchange_overrides.yaml`.
  Festivos y mercado cerrado no son sesión y no ejecutan nada.
- `entrada_efectiva = open · (1 + 0,0005)`. En esa apertura se comprueban, en el orden de
  `evaluate_trade_at_entry` y con el precio efectivo (OD-P6-11 A): `INVALID_STOP` (incluye una
  apertura por debajo del stop), `INVALID_TARGET`, `ABOVE_MAX_ENTRY` (entrada efectiva > `entry_max`,
  también cuando la causa es un hueco al alza), `RR_TOO_LOW` (RR a `target2` < 1,5),
  `POSITION_TOO_SMALL`, `DATA_NOT_EXECUTABLE` y después `INSUFFICIENT_CASH`. El broker es neutral.
- **Caducidad:** la orden vale **solo** para esa barra. Se consume en su apertura con un fill o un
  rechazo, y no se arrastra a ninguna otra sesión.
- **Barra de entrada ausente (propuesta para OD-T25-5):** si la barra de la sesión `s` no se valida en
  ninguna pasada hasta el cierre de la **5.ª sesión hábil** posterior a `s` (el margen del retraso
  europeo de T-024 §7), `s` se declara sin barra y la orden pasa a la siguiente barra de la serie, como
  en P6, que salta y cuenta esas sesiones. Si la barra de `s` aparece después, se registra como
  observación tardía y no reescribe nada.
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
   libro es `IGNORED_ALREADY_OPEN`. Se guarda, pero no reemplaza el stop ni el objetivo ni piramida
   (OD-P6-38). La posición se evalúa al cierre de `t`.
5. **Dividendos:** hay derecho si la posición estaba abierta al cierre de la víspera de la fecha ex; el
   abono se hace al cierre de la sesión ex, bruto (OD-P6-12, 13 y 14).
   - **En vivo (propuesta para OD-T25-6):** un dividendo que se conoce más tarde se abona al cierre de
     la primera sesión que se procesa después de conocerlo, marcado `late`. **Nunca se reescribe** el
     cash anterior, porque ya decidió tamaños.
6. **Splits y reajustes:** P6 operaba sobre una vista ya ajustada; en vivo la escala cambia a mitad de
   una posición.
   - Ante un split o un `REAJUSTE` con factor `f` registrado en `paper_bar_adjustment`, se ejecuta un
     evento `SPLIT_ADJUST` en la apertura de la sesión efectiva, antes de `OPEN_EXIT`:
     `unidades · f`, y la entrada, el stop y los objetivos `/ f`. El valor económico y el cash no
     cambian.
   - Si una barra nueva no casa con el `scale_anchor` de una posición y no hay ningún reajuste
     registrado, la posición queda en `DATA_GAP` (`SCALE_MISMATCH`) y **no se procesa** hasta que una
     revisión documentada lo resuelva. Nunca se adivina el factor.
7. **Datos ausentes y deslistados (propuesta para OD-T25-7):**
   - mientras falte la barra de un activo con posición, el libro no procesa eventos posteriores a esa
     sesión, hasta el límite de §7.2;
   - pasado el límite, la sesión se declara sin barra y el libro sigue;
   - si un activo no tiene ninguna barra validada durante **20 sesiones hábiles** de su calendario, se
     cierra con `EXIT_DATA_LOSS` al último cierre validado, sin slippage adicional, y la operación se
     publica aparte.
8. **FX:** la regla A de P6 (OD-P6-16) sobre `paper_fx_quote`. Si para un evento no hay ningún tipo
   causal, el evento espera. Nunca se inventa un tipo (INV-16). Hay una sola caja en EUR (P6 §11.2).

**Adaptaciones en vivo frente a P6, todas declaradas:** la señal vinculante por pasada (§7.1),
`SIGNAL_NOT_EVALUATED`, la barra ausente y su límite, los dividendos tardíos, `SPLIT_ADJUST`,
`SCALE_MISMATCH` y `EXIT_DATA_LOSS`. Fuera de esto, cualquier diferencia de comportamiento con P6 es un
defecto.

## 9. Costes y riesgo (P6, sin cambios)

- 0,10 % por lado sobre el nominal ejecutado (OD-P6-9 A); slippage primario de 5 pb por lado
  (OD-P6-10). La sensibilidad de 10 pb, si se publica, se calcula al publicar, reprocesando el mismo
  flujo de eventos, y es descriptiva.
- Riesgo del 0,5 % de la equity causal por operación y posición máxima del 10 % de esa equity.
- Long only, sin margen ni apalancamiento, cash ≥ 0 siempre. Sin cash suficiente, **rechazo
  completo** (`INSUFFICIENT_CASH`), sin reducir el tamaño.
- Sin límites globales nuevos: R-01 va después de P7.
- **Nada de esto cambia sin una decisión del propietario.**

## 10. Sellado, visibilidad y contaminación

**Por qué.** T-024 prohíbe mirar desenlaces de B2 y S2 posteriores al 2026-08-27 antes de su mirada
(D-72; ficha §6.3 y §9: «ningún checkpoint emite desenlaces», ni ventanas abiertas o cerradas).
T-025 opera las mismas políticas en las mismas sesiones. D-73 §2 lo resolvió: **los desenlaces de B2
y S2 quedan sellados hasta que T-024 emite su resultado para esa política** (`POSITIVO`,
`NO POSITIVO` o `NO EVALUABLE POR MUESTRA` en una mirada, o el veredicto final).

**Qué es visible de una cohorte sellada.** Solo lo que no depende de ningún precio posterior a la
apertura de entrada, que es lo mismo que T-024 §6.3 publica en sus conteos:
- las evaluaciones y señales OPERAR, con activo, `entry_max`, stop, objetivos, RR y riesgo
  porcentual;
- si la apertura pasa las comprobaciones que solo dependen de ella: `INVALID_STOP`, `INVALID_TARGET`,
  `ABOVE_MAX_ENTRY` y `RR_TOO_LOW`.

**Qué queda sellado** (todo lo que depende de equity, cash o salidas):
- `FILLED`, `POSITION_TOO_SMALL`, `INSUFFICIENT_CASH` e `IGNORED_ALREADY_OPEN`;
- unidades e importes;
- posiciones abiertas y cerradas, salidas, P&L, R, MAE, MFE y duraciones;
- equity, cash y exposición.

**Mecanismo (ciego procedimental, declarado):**
- La cohorte sellada se calcula en vivo, igual que las demás, para ejercitar el motor.
- Cada ejecución escribe `paper_seal_commitment` con el sha256 de todas sus filas selladas. Ese hash
  sí es visible, así que al desellar se puede comprobar que nada se reescribió.
- **Toda lectura** de `paper.db` pasa por una única capa de visibilidad. Informe, Telegram, dashboard
  y CLI solo usan la vista visible. Un test cerrado comprueba que ningún camino de presentación lee
  las tablas selladas de una cohorte sellada.
- **Limitación:** quien tenga la base (el usuario de la Pi) podría leerla. El ciego es procedimental,
  como el de la fase B de T-024, y se declara.

**C0 (propuesta para OD-T25-4, que reabre en parte D-73 §2 con un dato nuevo).** D-73 dejó C0 visible
porque en T-024 es descriptiva. Pero C0 comparte con B2 el stop de 2,0·ATR (§0) y casi toda la
población de señales; difieren el objetivo y el RR del score. **Un P&L visible de C0 revela en gran
parte cuándo se para B2.** Se propone sellar también C0 mientras T-024 no se resuelva, y dejar
visible solo la cohorte BH, que no depende de ninguna señal.

**Contaminación (regla vinculante, D-73 §3 y este encargo):**

> Toda observación cuyo desenlace se consulte durante T-025 queda consumida para investigación y no
> podrá utilizarse posteriormente como holdout virgen de P7.

- **Registro de consumo:** cada lectura de desenlaces, ya sea de una cohorte visible o de una
  desellada, deja una fila en `paper_outcome_access` (quién, cuándo, para qué, qué filas, su hash).
  Así lo consumido es un hecho registrado, no una memoria.
- **Frontera de P7:** P7 empieza después de la congelación de su candidata **y** del `T1` de la
  última mirada de T-024 (OD-T24-11). Solo usa sesiones cuyos desenlaces no hayan intervenido en el
  diseño ni en la selección de la candidata.
- **P6-bis** no lee `paper.db`. Solo usa sesiones hasta el 2026-08-27 (D-73 §6).
- **T-024 y T-025 no se alimentan entre sí:** las poblaciones y los datos son distintos (cosechas
  mensuales frente a pasadas en vivo) y sus objetivos también (medición frente a registro operativo).
  Una comparación entre los dos solo es descriptiva, después de desellar, y no cambia nada de ninguno.

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
- **Transacción por paso:** cada evento económico se escribe en una transacción con sus filas de
  ledger, posición y evento. Si la ejecución se corta, o entra entero o no entra.
- **Repetir una pasada no duplica nada:**
  - las claves únicas de §5 hacen que reprocesar las mismas entradas sea un no-op;
  - si una clave choca con un **contenido distinto**, la ejecución para con
    `ERROR_DIVERGENCIA` y no escribe;
  - una pasada repetida no puede abrir otra vez la misma posición: `(cohort_id, signal_id)` es único
    en `paper_order`, `paper_entry_decision` y `paper_position`.
- **Una abierta por activo y libro:** el motor lo garantiza, y una comprobación al final de cada
  transacción (posiciones con `OPEN` y sin `EXIT` por `(cohort_id, instrument_id)` ≤ 1) aborta la
  transacción si se viola.
- **Frontera por cohorte:** cada cohorte avanza en orden total `(event_ts_utc, phase, clave)`. No se
  escribe un evento con τ anterior a la frontera ya escrita de esa cohorte. Lo que llega tarde se
  aplica en la frontera, marcado `late` (§8.5).
- **Identidades contables** de P6 §19 en cada evento y al final de cada ejecución, con tolerancia de
  1e-6 EUR: `equity = cash + Σ valor`, `cash ≥ 0` y el flujo V_T − V_0. Si una falla, la ejecución
  aborta.
- **Reconstrucción:** con `paper_run_id`, SHA, `t025_system_sha256` y las observaciones guardadas,
  reprocesar desde cero tiene que dar el mismo ledger byte a byte. Se prueba en los tests y en una
  verificación periódica.

## 13. Versionado y modificación

- B2, S2 y C0 quedan **congeladas** durante todo el shadow. Cambiar una política crea una
  `policy_version` nueva, y con ella una cohorte nueva.
- El paper broker se versiona por `engine_version` y por tag. **`t025_system_sha256`** es el hash
  canónico de un envoltorio `intradia.t025.system.v1` con: el `p6_system_sha256` de referencia, cada
  adaptación de §8, `engine_version`, la regla de señal vinculante, los límites de datos ausentes, el
  sellado y el capital.
- **Un cambio que puede alterar desenlaces** (motor, reglas, datos, calendario) crea una **cohorte
  nueva**. Una cohorte nunca cambia de motor. La vieja sigue con su motor congelado, que vive en un
  módulo inmutable `paper/engine_vN`, hasta que el propietario la cierre: entonces cierra sus
  posiciones con `EXIT_COHORT_CLOSED` en la apertura siguiente (propuesta para OD-T25-8).
- **Nunca se mezclan cohortes sin etiqueta** en una métrica ni en el dashboard.
- **Nunca se reescribe** una observación anterior. Una corrección de un defecto de implementación es
  una cohorte nueva más una nota en la ficha, y la cohorte defectuosa se conserva.

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
- `late`, `DATA_GAP`, `SCALE_MISMATCH` y `EXIT_DATA_LOSS`.

En una cohorte sellada, solo lo visible de §10 hasta desellar. **Ninguna de estas métricas se usa
para tocar B2, S2, C0 ni el motor durante la captura.** Las métricas no tienen intervalo ni veredicto:
son descriptivas (INV-20).

**Campos para el dashboard (S-02, S-03):**
- capital inicial, equity, cash, posiciones abiertas y cerradas;
- rentabilidad, drawdown, benchmark y exceso;
- recomendaciones de hoy por política y rechazos con su motivo;
- etiqueta y cohorte.

Todos salen de §5. En las cohortes selladas, solo su parte visible.

## 15. Invariantes

- **INV-02, INV-06, INV-07, INV-13, INV-15, INV-16 e INV-18:** se ejercitan con los tests de §16.
- Específicas de T-025:
  - **T25-1:** ninguna fila de hechos se actualiza ni se borra;
  - **T25-2:** ninguna decisión usa una entrada con marca ≥ τ, salvo la apertura de su barra;
  - **T25-3:** como mucho una posición abierta por `(cohorte, activo)`;
  - **T25-4:** ningún camino de presentación lee lo sellado de una cohorte sellada;
  - **T25-5:** ninguna consulta de `intradia.db` devuelve una fila paper, y `paper/` nunca abre
    `intradia.db` para escribir;
  - **T25-6:** el motor reproduce `p6_sim` (test de equivalencia);
  - **T25-7:** los `EXECUTOR_PATHS` no cambian mientras no se decida OD-12.

## 16. Implementación requerida (tarea siguiente, con autorización aparte)

Nada de esto se hace en esta entrega.

1. Cerrar las OD-T25 y OD-12, hacer la revisión final y congelar `T025_PREREG_SHA`.
2. `paper/`: almacén y migraciones de `paper.db`, motor incremental `engine_v1`, capa de visibilidad,
   CLI y mensaje de Telegram.
3. **Tests obligatorios, con datos sintéticos:**
   - equivalencia con `p6_sim.simulate`, ledger fila a fila, incluido un lote con cash escaso y
     desempate;
   - una pasada repetida no duplica; una divergencia aborta;
   - dos ejecuciones concurrentes: la segunda sale sin escribir;
   - `IGNORED_ALREADY_OPEN` con la posición abierta;
   - stop y objetivo en la misma barra → stop;
   - hueco al alza → `ABOVE_MAX_ENTRY`;
   - festivo y media sesión;
   - barra de entrada ausente y su límite (§7.2);
   - dividendo tardío sin reescritura;
   - split 2:1 y contrasplit con posición abierta; `SCALE_MISMATCH` sin reajuste;
   - `EXIT_DATA_LOSS`;
   - FX ausente → el evento espera;
   - los triggers impiden `UPDATE` y `DELETE`;
   - la capa de visibilidad no deja ver lo sellado (lista cerrada de columnas);
   - `paper/` se niega a abrir una base sin su `application_id`;
   - `seguimiento`, `posiciones` y `cerrar` no ven ninguna fila paper;
   - reconstrucción byte a byte.
4. **Revisión independiente** de look-ahead y de idempotencia antes de desplegar.
5. Despliegue en la Pi como tag, con unidad systemd propia tras cada pasada programada.

## 17. Decisiones del propietario (OD-T25) — todas ABIERTAS

Formato de `docs/decision-log.md`. Mientras sigan abiertas, T-025 está en `BLOQUEADA_POR_OWNER` para
congelar.

### OD-T25-1 — Arquitectura de persistencia y código
- **Pregunta:** ¿dónde viven los datos y el código paper?
- **Alternativas:** (A) `paper.db` aparte y paquete `paper/` fuera de los `EXECUTOR_PATHS` (§4);
  (B) tablas `paper_*` en `intradia.db` (migración v8) y código en `advisor/`.
- **Consecuencia:** (A) separación por construcción, sin migrar la base de la Pi y sin romper la
  identidad de T-024, a cambio de una CI algo más amplia y referencias entre bases sin claves
  foráneas. (B) separación por nombre de tabla, migración irreversible en la Pi y T-024 inoperable
  desde `main` desde el primer commit.
- **Recomendación técnica:** A.
- **Bloquea:** la implementación.

### OD-T25-2 — Capital inicial
- **Alternativas:** (A) 100.000 EUR por cohorte, como P6; (B) un capital realista para Trade Republic
  (por ejemplo 10.000 EUR) con las mismas reglas; (C) otro.
- **Consecuencia:** con unidades fraccionarias, el resultado relativo es el mismo en A y B. B hace los
  importes del dashboard más parecidos a la realidad, pero rompe la comparación directa en euros con
  P6.
- **Recomendación técnica:** A.

### OD-T25-3 — Libros de B2 y S2
- **Alternativas:** (A) libros independientes, como P6, con coexistencia en el mismo activo y sin
  prioridad entre políticas; (B) un libro común con una regla de prioridad entre B2 y S2 (por ejemplo,
  el desempate de P6 sobre `policy‖signal_id`).
- **Consecuencia:** A es fiel a P6 y no introduce ninguna regla nueva. B es una política de cartera
  nueva, sin medir, y pertenece a P6-bis (bloque B), no a T-025.
- **Recomendación técnica:** A.

### OD-T25-4 — Visibilidad de C0 mientras T-024 no se resuelve (reabre en parte D-73 §2)
- **Dato nuevo:** C0 comparte con B2 el stop de 2,0·ATR y casi toda la población de señales. Su P&L
  visible revela en gran parte las salidas por stop de B2 (§10).
- **Alternativas:** (A) sellar C0 como B2 y S2, con solo BH visible; (B) C0 visible, declarando en
  T-024 una pérdida parcial de ceguera; (C) C0 visible solo de forma agregada y mensual.
- **Consecuencia:** A protege el único resultado forward limpio (T-024), pero deja el dashboard sin
  P&L de ninguna política durante 7 a 13 meses (la mirada 1 o el corte final de T-024). B da
  visibilidad inmediata, pero el resultado de T-024 para B2 queda con la ceguera rota. C sigue
  revelando la tendencia.
- **Recomendación técnica:** A.

### OD-T25-5 — Barra de entrada ausente
- **Alternativas:** (A) esperar hasta el cierre de la 5.ª sesión hábil y después aplicar el salto de
  P6 (§7.2); (B) rechazar `DATA_NOT_EXECUTABLE` en cuanto la barra falte en la primera pasada posterior
  a la apertura.
- **Consecuencia:** A es fiel a P6 y tolera el retraso europeo medido (T-012), a cambio de que el libro
  espere unos días. B rechaza entradas que P6 habría hecho.
- **Recomendación técnica:** A.

### OD-T25-6 — Dividendos conocidos tarde
- **Alternativas:** (A) abono al cierre de la primera sesión procesada después de conocerlo, marcado
  `late`, sin reescribir; (B) reescribir el cash desde la fecha ex.
- **Consecuencia:** B viola T25-1 y cambia retroactivamente tamaños ya decididos.
- **Recomendación técnica:** A.

### OD-T25-7 — Activo sin datos de forma prolongada
- **Alternativas:** (A) `EXIT_DATA_LOSS` al último cierre validado tras 20 sesiones hábiles sin barra;
  (B) mantener la posición abierta indefinidamente y avisar.
- **Consecuencia:** B puede dejar capital bloqueado para siempre e impedir las identidades del final de
  una cohorte.
- **Recomendación técnica:** A.

### OD-T25-8 — Cohortes y versiones del motor
- **Alternativas:** (A) un motor nuevo abre una cohorte nueva y la vieja sigue con su motor congelado
  hasta que el propietario la cierra (`EXIT_COHORT_CLOSED` en la apertura siguiente); (B) la cohorte
  vieja se cierra automáticamente al desplegar un motor nuevo.
- **Consecuencia:** A conserva la continuidad del registro y multiplica las cohortes; B corta series
  cada vez que se corrige algo.
- **Recomendación técnica:** A.

## 18. Riesgos y limitaciones

- **Ciego procedimental** (§10): no es criptográfico.
- **Meses sin P&L visible** si se aprueba OD-T25-4 A: el bot «funciona», pero el propietario no ve
  cómo le va hasta que T-024 se resuelve.
- **Datos de `yfinance`:** retraso europeo, revisiones y reajustes. Se mitigan con la caché, la
  primera observación vinculante y los eventos explícitos de §8, pero no desaparecen.
- **Fraccionales y liquidación inmediata:** las mismas simplificaciones que en P6.
- **La Pi** es un único dispositivo, en desarrollo/integración, y una caída hace perder señales
  (`SIGNAL_NOT_EVALUATED`). C-06 (backups) es prioridad alta antes de acumular meses de registro.
- **Interacción con T-024** (§3.8): depende de OD-12.
- Universo condicionado a 2026; T-025 no lo corrige.

## Criterio de aceptación (de esta entrega documental)

- La ficha recorre todos los apartados del encargo (§1–§17) y no queda ninguna regla sin fijar ni sin
  marcar como OD.
- Ninguna OD se da por cerrada sin una decisión del propietario.
- El roadmap, el decision log y `docs/gates.md` son coherentes con esta ficha.
- La revisión independiente queda sin BLOCKER ni IMPORTANTE abiertos.
- `pytest`, `ruff` y `mypy` dan lo mismo que la línea base, y no cambia ningún fichero de los
  `EXECUTOR_PATHS`.

## Criterio de rechazo

Cualquiera de estos: una regla de P6 cambiada sin OD; una lectura de desenlaces de B2 o S2 permitida
antes de desellar; una ruta por la que una fila paper pueda aparecer como posición real; un cambio en
los `EXECUTOR_PATHS`; código funcional en esta entrega.

## Evidencia que debe quedar registrada

- Esta entrega: la ficha, el roadmap, el decision log, `docs/gates.md` y la revisión, en
  `evidence/2026-10-06-T-025-diseno/`, con la salida de `pytest`, `ruff` y `mypy`.
- Implementación: `evidence/<fecha>-T-025-codigo/` con los tests, la equivalencia y la revisión.
- Registro forward: `paper.db` fuera del repositorio, con su ruta, su tamaño y su hash periódicos en
  `evidence/T-025-forward/`, y los compromisos de sellado.

## Commit esperado

Rama `research/t025-shadow-prereg`: `docs(T-025): diseño y pre-registro propuesto del shadow/paper
trading forward`, más commits separados para el roadmap y las decisiones.

## Actualización documental requerida

`docs/roadmap.md` (S-01, Línea S, mapa y orden), `docs/decision-log.md` (D-73, D-74, OD-12 y el
enlace a las OD-T25) y `docs/gates.md` (nota en GATE P7 y en GATE P10).

## Handoff al siguiente agente

- **Estado:** diseño y pre-registro propuesto; BLOQUEADA_POR_OWNER en OD-T25-1 a OD-T25-8 y OD-12.
- **Verificado:**
  - inventario del código citado en §3, leído el 2026-10-06;
  - igualdad de los `EXECUTOR_PATHS` de `main` con `1a697c3`;
  - hashes de §0 leídos de `politicas-finales.json` y de `system-hashes.json`;
  - línea base de §0.
- **Pendiente:** las decisiones del propietario, la revisión final, la congelación y, con autorización
  aparte, la implementación (§16).
- **Hallazgos:**
  - **BLOCKER futuro, no de esta entrega:** la interacción con la identidad de T-024 (§3.8). Antes de
    cualquier cambio en los `EXECUTOR_PATHS` de `main`, hay que decidir OD-12.
  - **OBSERVATION:** el texto anterior del roadmap atribuía a S2 una exposición media de 0,5313, que es
    la de C0; la de S2 es 0,6054 (T-023, `hallazgos.md` §B). Corregido en esta entrega.

## Revisión independiente del diseño

(Se rellena tras la revisión.)
