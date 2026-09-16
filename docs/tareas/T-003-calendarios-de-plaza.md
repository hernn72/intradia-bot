# T-003 — Calendarios de plaza separados del benchmark y cripto 24/7 (PR 2, fases 4 y 6)

Estado: ACEPTADA (2026-09-16, tras revisión independiente y sus correcciones)
Agente: Codex (implementa) → Opus (revisión obligatoria: fechado de sesiones)
Línea / fase: L0 PR 2, fases 4 y 6 de `docs/plan-ejecucion.md`
Gate al que contribuye: GATE L0 (requisito 2)

## Objetivo
Las sesiones esperadas de cada activo salen del calendario de **su plaza**
(festivos incluidos), nunca del benchmark; las tres criptos tienen calendario
24/7; existe una sola taxonomía de plazas en el código.

## Por qué existe
Verificado en `evidence/2026-09-14-L0-baseline/`: `AZN` (NASDAQ) queda
`INCOMPLETO` y **vetada** por seis festivos de EE. UU. que `^STOXX` sí cotiza;
`TSM` igual contra `^TWII`; trece ETF de Xetra aparecen `DEGRADADO` por
festivos alemanes que `^GSPC`/`^N225` no tienen. Además `advisor/data/freshness.py`
(`_mercado_por_sufijo`: `EURONEXT`, `MILAN`, `BME`, `COPENHAGEN`) y
`advisor/data/sessions.py` (`market_for_symbol`: `PAR`, `AMS`, `MIL`, `MCE`,
`CPH`) mantienen **dos taxonomías distintas** de la misma cosa. Decisión D-07.

## Dependencias previas
T-002 aceptada (la columna nueva de la medición de frescura entra por
migración). Decisiones D-07 y D-15.

## Archivos probables
No asumir que sean exactos: verificar primero.
- `advisor/data/sessions.py` (`MARKET_SESSIONS`, `SYMBOL_MARKETS`, `market_for_symbol`, `trim_unclosed_bar`)
- `advisor/data/calendars.py` (nuevo)
- `advisor/data/freshness.py` (`calcular_frescura_serie`, `classify_data_quality`, `DataFreshness`, `_mercado_por_sufijo`, `mercado_para_simbolo`)
- `advisor/analysis/analyzer.py` (`analyze_asset`, `_fetch_benchmark`, llamadas a `calcular_frescura_serie`)
- `advisor/main.py` (`cmd_frescura_datos`, `freshness_row_to_measurement`)
- `advisor/report/formatter.py` (bloque «Sesiones ausentes frente al benchmark»)
- `advisor/research/event_study.py` y `advisor/research/capacity.py` (usan `market_session`; la espina de sesiones de P2.5 **no** cambia en esta tarea)
- `advisor/storage/migrations.py` (v3: columna `calendar TEXT` en `data_freshness_measurement`)
- `universe.yaml` (campos opcionales `exchange_calendar`, `exchange_timezone`; por defecto derivados de `primary_market`)
- `requirements.txt` (`exchange_calendars`)
- `tests/test_sessions.py`, `tests/test_freshness.py`, `tests/test_analyzer.py`, `tests/test_calendars.py` (nuevo)

## Invariantes que no pueden romperse
INV-03, INV-05 (esta tarea la establece), INV-06 (producción e investigación
usan el mismo `calendars.py`), INV-12, INV-13 (no se toca el fechado de la
cosecha ni `timestamps.py`), INV-17.

## Implementación requerida
1. Dependencia `exchange_calendars` en `requirements.txt` con versión fijada.
   **Primer paso de la tarea:** instalarla en un venv Python 3.13 (o en la
   Pi) y anotar el resultado en la ficha; si no instala, BLOCKER y reabrir D-07.
2. `advisor/data/calendars.py`:
   - `MARKET_TO_MIC = {"XETRA": "XETR", "PAR": "XPAR", "AMS": "XAMS", "MCE": "XMAD", "MIL": "XMIL", "CPH": "XCSE", "NYSE": "XNYS", "NASDAQ": "XNAS", "JPX": "XTKS", "HKG": "XHKG", "KSC": "XKRX", "TAI": "XTAI", "SHH": "XSHG", "LSE": "XLON", "CRYPTO": "CRYPTO_24_7"}`.
   - `class Crypto247Calendar` con `sessions_in_range(start, end)` = todos los
     días naturales; `is_session(d)` siempre `True`.
   - `expected_sessions(market: str, start: date, end: date) -> list[date]`;
     plaza desconocida → `ValueError` con el nombre (nunca UTC ni benchmark).
   - `missing_sessions(actual: set[date], market, start, end) -> tuple[date, ...]`.
   - `market_timezone(market)` delega en `sessions.py`; **una sola tabla** de
     plazas: `MARKET_SESSIONS` se completa con `mic` y desaparece
     `_mercado_por_sufijo` de `freshness.py` (sus llamantes usan
     `market_for_symbol`). Corregir en el mismo paso la trampa documentada: un
     símbolo con guion solo es cripto si termina en `-EUR`/`-USD` **y** su
     `asset_class` es `crypto`; `BRK-B` debe resolver a NYSE por `universe.yaml`,
     y la función de sufijos debe fallar ruidosamente si no puede resolver.
3. `calcular_frescura_serie` recibe `market` (obligatorio) y calcula
   `absent_reference_sessions` / `absent_recent_sessions` contra
   `expected_sessions(market, primera_fecha_ventana, última_fecha_activo)`;
   el parámetro `benchmark_close` desaparece de la firma. `DataFreshness`
   gana `calendar: str` (MIC) y pierde `benchmark_symbol` como referencia de
   calendario (puede conservarse solo para informar qué benchmark usa la
   fortaleza relativa, con otro nombre: `strength_benchmark`).
4. Última barra: `sessions_approx` pasa a contar sesiones **del calendario**
   entre la última barra y la referencia, no días laborables.
5. Cripto: `may_be_partial_current_session` se decide con el cierre UTC
   00:00 + `settlement_minutes`; nunca con un cierre bursátil. Sábado,
   domingo y 25 de diciembre son sesiones válidas.
6. Informe: el bloque pasa a llamarse «Sesiones ausentes frente al calendario
   de su plaza» y muestra el MIC; no imprime más de 5 fechas por activo en el
   informe principal (el resto va al log).
7. Migración v3: `data_freshness_measurement.calendar TEXT`.

## Qué NO debe modificarse
`compute_score`, `classify`, `relative_strength*`, la espina de sesiones de
`advisor/research/capacity.py`, `advisor/research/timestamps.py`, la ventana
de veto (20) y el vocabulario `OK/DEGRADADO/INCOMPLETO` (eso es PR 3).

## Tests unitarios
Todos con fechas cerradas y sin red:
- `test_xetra_no_espera_sesion_el_24_26_31_dic_ni_viernes_santo_ni_1_mayo`: 2025-12-24, 2025-12-26, 2025-12-31, 2026-04-03, 2026-04-06, 2026-05-01 no están en `expected_sessions("XETRA", …)`; 2026-03-06 y 2026-09-07 sí.
- `test_nyse_no_espera_labor_day_ni_thanksgiving`: 2026-09-07 y 2025-11-27 ausentes; 2026-09-08 presente.
- `test_jpx_espera_sesion_cuando_xetra_cierra`: 2026-04-06 presente en JPX.
- `test_adr_usa_calendario_de_su_ticker`: `TSM` con `market=NYSE` no echa en falta 2026-09-07 aunque `^TWII` cotice.
- `test_etf_xetra_sobre_sp500_usa_calendario_xetra`: `SXR8.DE` con barras completas de Xetra → 0 ausentes.
- `test_cripto_sabado_domingo_navidad_son_sesion`.
- `test_plaza_desconocida_falla_ruidosamente`.
- `test_brk_b_no_es_cripto`.
- `test_sessions_approx_usa_calendario`: última barra viernes 2026-09-04, referencia martes 2026-09-08 07:00 UTC, plaza NYSE → 0 sesiones perdidas (el lunes 7 fue festivo); plaza XETRA → 1.

## Tests de integración
- `test_benchmark_nunca_define_sesiones` (fase 13, invariante 3): con
  `FakeProvider` que sirve un benchmark con fechas extra, `analyze_asset` no
  reporta ninguna ausencia. Debe fallar si alguien vuelve a pasar el
  benchmark a la frescura.
- `test_festivo_no_es_missing_session` (invariante 4).
- Tests existentes de `tests/test_freshness.py` que asumían benchmark: se
  reescriben con `market`, conservando los casos numéricos.

## Verificación contra datos reales
```bash
python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar > evidence/<fecha>-T-003-calendarios/despues.txt
python -m advisor.main frescura-datos
```
Comprobar a mano, contra `evidence/2026-09-14-L0-baseline/analizar-swing-sin-ia.txt`:
- `AZN`: 0 sesiones ausentes (antes 6) y calidad ≠ `INCOMPLETO` por ese motivo.
- `TSM`: 0 (antes 5).
- `SXR8.DE`: solo puede quedar `2026-03-06` (antes 6); esa fecha pasa a T-004.
- `IQQT.DE`: 0 (antes 7).
- `SAP.DE`: sigue faltando `2026-09-07` (hueco real, causa en T-004).
- `BTC-EUR`: calendario `CRYPTO_24_7`, sin «sin calendario de referencia».

## Medición del impacto
- nº activos cuya calidad cambia, por motivo (esperado: ~13 DEGRADADO → OK
  por festivos ajenos; `AZN` y `TSM` dejan de estar vetadas; los 30 del
  2026-09-07 se mantienen hasta PR 3/T-004).
- nº activos que cambian de radar/acción y por qué.
- nº señales afectadas en investigación: 0 (la espina de P2.5 no cambia; decirlo).

## Criterio de aceptación
- Tests y CI en verde; instalación en 3.13 verificada.
- Las seis comprobaciones a mano de arriba se cumplen.
- Cero activos con ausencias que coincidan con un festivo de su propia plaza.
- Una sola taxonomía de plazas (`grep -rn "EURONEXT\|MILAN\|COPENHAGEN\|BME" advisor` vacío).
- Revisión independiente (Opus) sin hallazgos BLOCKER/SAME_SCOPE abiertos.

## Criterio de rechazo
- Cualquier excepción por ticker o por fecha.
- Un `fallback` silencioso a UTC o al benchmark para una plaza desconocida.
- Cambios en el score o en la ventana de veto.

## Evidencia que debe quedar registrada
`evidence/<fecha>-T-003-calendarios/` con `despues.txt`, `README.md` con la
tabla antes/después por activo y motivo, y la salida de `pip install` en 3.13.

## Commit esperado
Rama `fix/exchange-calendars`. Mensaje:
`fix(data): las sesiones esperadas salen del calendario de plaza, no del benchmark; cripto 24/7`.
(Fases 4 y 6 en un commit si comparten `calendars.py`; si no, dos.)

## Actualización documental requerida
`docs/roadmap.md`: PR 2 fases 4 y 6 → ACEPTADA. `docs/plan-ejecucion.md`:
nota de fecha en las fases 4 y 6. `README.md`: limitación «no se modelan
festivos» se retira.

## Handoff al siguiente agente
Resumen de cambios:
- Añadido `advisor/data/calendars.py` con `exchange_calendars`, MIC por plaza,
  `CRYPTO_24_7`, `expected_sessions`, `missing_sessions` y conteo de sesiones
  cerradas por calendario.
- Unificada la taxonomía en `MARKET_SESSIONS` con `mic`; eliminado el fallback
  silencioso de `_mercado_por_sufijo` en frescura. `BRK-B` no cae como cripto:
  se resuelve por `primary_market` del universo.
- `calcular_frescura_serie` recibe `market` obligatorio y ya no usa el benchmark
  para ausencias. `DataFreshness` añade `calendar` y `strength_benchmark`.
- `sessions_approx` cuenta sesiones del calendario de plaza; cripto usa sesión
  natural 24/7 y cierre lógico UTC 00:00 + `settlement_minutes`.
- Informe y CLI muestran el MIC/calendario de plaza; el informe principal limita
  a 5 fechas ausentes por activo y registra el detalle completo en log.
- Añadida migración v3 `data_freshness_measurement.calendar TEXT` y tests.
- No se editó `universe.yaml`: `exchange_calendar` y `exchange_timezone` se
  derivan en código desde `primary_market`. Los campos opcionales de YAML quedan
  pendientes para una fase posterior.
- No se tocó `requirements.txt`; la dependencia ya estaba fijada.

Ficheros a commitear:
- `advisor/data/calendars.py`
- `advisor/data/sessions.py`
- `advisor/data/freshness.py`
- `advisor/analysis/analyzer.py`
- `advisor/main.py`
- `advisor/report/formatter.py`
- `advisor/storage/db.py`
- `advisor/storage/migrations.py`
- `tests/test_calendars.py`
- `tests/test_freshness.py`
- `tests/test_analyzer.py`
- `tests/test_analysis.py`
- `tests/test_report.py`
- `tests/test_db.py`
- `tests/test_migrations.py`
- `docs/tareas/T-003-calendarios-de-plaza.md`
- `docs/roadmap.md`
- `docs/plan-ejecucion.md`
- `evidence/2026-09-14-T-003-calendarios/README.md`
- `evidence/2026-09-14-T-003-calendarios/antes.txt`
- `evidence/2026-09-14-T-003-calendarios/baseline-mypy.txt`
- `evidence/2026-09-14-T-003-calendarios/baseline-pytest.txt`
- `evidence/2026-09-14-T-003-calendarios/baseline-ruff.txt`
- `evidence/2026-09-14-T-003-calendarios/despues.txt`
- `evidence/2026-09-14-T-003-calendarios/pip-install-exchange-calendars.txt`

Mensaje de commit propuesto:
`fix(data): las sesiones esperadas salen del calendario de plaza, no del benchmark; cripto 24/7`

Verificación:
- `python -m pytest -q`: 431 passed, 1 warning.
- `ruff check .`: All checks passed.
- `mypy advisor`: Success, no issues found in 58 source files.
- `python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar`:
  la sesión de Codex no tiene DNS y quedó bloqueada; **Claude Code la ejecutó
  el 2026-09-14 a las 14:01 UTC** con `exit=0` sobre los 107 activos. El
  BLOCKER de aceptación real queda resuelto; `despues.txt` es esa pasada.

Verificado a mano:
- No verificable contra datos reales por bloqueo del proveedor. No se inventan
  resultados para `AZN`, `TSM`, `SXR8.DE`, `IQQT.DE`, `SAP.DE` ni `BTC-EUR`.
- Verificación manual sin red cubierta en tests: XETRA no espera 2026-04-06 y
  sí espera 2026-09-07; NYSE no espera 2026-09-07 y sí espera 2026-09-08;
  cripto acepta sábado, domingo y Navidad como sesiones; un benchmark con fecha
  extra no produce ausencias del activo.

Impacto:
- No medible contra datos reales por fallo del proveedor. Impacto esperado por
  contrato: falsos huecos por festivos ajenos desaparecen; la espina de P2.5 no
  cambia; señales de investigación afectadas: 0 en esta entrega.

Hallazgos:
- BLOCKER: aceptación real bloqueada por DNS/proveedor de datos tras un
  reintento.
- OBSERVATION: el árbol tenía cambios previos no atribuibles a esta ejecución
  en `docs/decision-log.md`, `docs/tareas/T-006-universe-vintage-e-identidad.md`,
  `requirements.txt`, `graphify-out/` y evidencia base; no se revirtieron.

Decisiones pendientes:
- Ninguna para implementar código. Pendiente operativo: repetir verificación
  real cuando el proveedor/DNS responda.

Siguiente:
- Reintentar aceptación real y después revisión independiente Opus centrada en
  fechado de sesiones, zonas horarias, ausencia de benchmark como calendario,
  migración v3 atómica y cripto 24/7.


---

## Cierre de la ficha por Claude Code — 2026-09-14

El único BLOCKER que dejó Codex era su falta de DNS, no un defecto del código.
Ejecutada la verificación real desde Claude Code, el resultado es el que la
línea base predijo:

- `AZN` y `TSM` pasan de 6 y 5 ausencias (festivos de EE. UU. que su benchmark
  extranjero sí cotizaba) a **0**; dejan de estar vetadas por un hueco que no
  existía.
- Los ETF de Xetra contra `^GSPC`/`^N225` pasan de 6-7 ausencias a **1**
  (`2026-03-06`), que es justo el caso que la línea base dejó anotado para
  T-004.
- Las tres criptos dejan de aparecer como «sin calendario de referencia».
- Calidad del dato: `OK` 59 → 63, `INCOMPLETO` 30 → 28, `DEGRADADO` 18 → 16.

Tabla completa y comandos en `evidence/2026-09-14-T-003-calendarios/README.md`.

**Pendiente antes de aceptar** (siguiente sesión):

1. **Revisión independiente obligatoria** (la ficha la exige: toca fechado de
   sesiones). Puntos que el revisor debe intentar romper, además de los
   habituales:
   - `market_for_symbol` ahora exige `asset_class="crypto"` para resolver
     `-EUR`/`-USD`: comprobar que ningún llamante se queda sin plaza en
     silencio y que `BRK-B` no cae en `CRYPTO`.
   - `closed_sessions_between` y el cierre lógico 24/7 de cripto
     (UTC 00:00 + `settlement_minutes`).
   - Que la espina de sesiones de `advisor/research/capacity.py` no haya
     cambiado (la ficha lo prohíbe) y que P2.3/P2.4 no se muevan.
   - La migración v3 con el patrón atómico y su backup.
2. **Despliegue en la Pi** tras aceptar, con `exchange_calendars==4.13.2` ya
   instalada allí (verificada el 2026-09-14 en Python 3.13/ARM: las 14 plazas
   cargan).
3. **T-004** hereda el resultado: 28 activos con `2026-09-07`, 14 con
   `2026-03-06`, 2 con `2026-07-17` y 2 con `2026-06-03` (XKRX), 1 con
   `2026-03-23` (XCSE). Son la población exacta a clasificar.

---

## Revisión independiente y cierre — 2026-09-16

Revisión hecha por el subagente `revisor` con `PROMPT_REVIEW`, sobre el diff
`1c76add..5fb3394`. **Veredicto: CORREGIR**, con un BLOCKER y tres defectos de
alcance. Los cuatro están corregidos y verificados; evidencia completa en
`evidence/2026-09-16-T-003-correcciones/README.md`.

| # | Hallazgo | Corrección |
|---|---|---|
| BLOCKER | `frescura-datos` sin `--grupos` mide los 126 activos; las once plazas de contexto sin calendario lanzaban `ValueError` fuera del `try` y tumbaban el comando (exit 1, cero filas) | `advisor/main.py`: plaza y frescura dentro del `try`; la fila se degrada, la medición no |
| SAME_SCOPE | El requisito 5 (cierre lógico 24/7 de cripto) no llegaba al informe: `analyzer.py` pisaba `may_be_partial_current_session` a `False` cuando `trim.status == "sin sesión de cierre"`, que solo ocurre en `CRYPTO` | Eliminada esa rama de la condición |
| SAME_SCOPE | El manifiesto no registraba la versión de `exchange_calendars`, que desde esta ficha decide calidad y veto (INV-18) | Añadida a `provider_versions` |
| SAME_SCOPE | `calcular_frescura_dato(..., market="XETRA")`: fallback silencioso de plaza, prohibido por el criterio de rechazo | `market` obligatorio |

Lo que la revisión intentó romper y no se rompió: INV-05 (el benchmark ya no
puede definir sesiones y el test lo demuestra fallando con el código antiguo),
INV-03 (ningún score cambia), INV-06 (la espina de P2.5 no se movió y
`advisor/research/` no importa `calendars.py`), INV-13, la migración v3 (DDL y
`PRAGMA user_version` en una sola transacción, con backup previo), ausencia de
look-ahead, y el fallo ruidoso de plaza desconocida.

Correcciones documentales aplicadas:

- `antes.txt` **no era una línea base**: era la pasada fallida por DNS (138
  `Could not resolve host`). Renombrada a `pasada-fallida-por-dns.txt`, y el
  README apunta ahora a la línea base real, `evidence/2026-09-14-L0-baseline/`.
- `pip-install-exchange-calendars.txt` era el log del intento fallido.
  Renombrado a `pip-install-fallido-por-dns.txt`; la instalación en Python 3.13
  queda verificada en la Pi (`pi-python313-exchange-calendars.txt`).
- Añadida la medición que faltaba: **activos que cambian de radar o de acción,
  0**, recalculada de forma independiente.

Tests de regresión añadidos (los tres fallan contra el código sin corregir):

- `tests/test_freshness.py::TestUniversoRealCompleto` (dos tests): el universo
  real completo, con sus 19 activos de contexto, sin fixtures cómodos.
- `tests/test_analyzer.py::TestRunAnalysis::test_cripto_declara_la_barra_del_dia_en_curso_como_parcial`
  y su contrario con la barra ya liquidada.

Verificación final: 435 tests, `ruff` y `mypy` limpios, `frescura-datos` y
`analizar` con código 0 contra datos reales.

**Queda abierto y pasa a T-004:** las dos ausencias coreanas `2026-06-03` y
`2026-07-17`. Hay indicio fuerte de que son festivos de su propia plaza que la
librería no codifica —todos los días electorales coreanos pasados son no-sesión
y el 3 de junio de 2026 son las elecciones locales—, pero no está probado
contra fuente oficial. Si lo son, dos activos quedan `DEGRADADO` por un hueco
que no existe, que es lo que el criterio de aceptación prohíbe.
