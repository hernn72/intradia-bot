# T-003 — Calendarios de plaza separados del benchmark y cripto 24/7 (PR 2, fases 4 y 6)

Estado: PENDIENTE
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
   - `MARKET_TO_MIC = {"XETRA": "XETR", "PAR": "XPAR", "AMS": "XAMS", "MCE": "XMAD", "MIL": "XMIL", "CPH": "XCSE", "NYSE": "XNYS", "NASDAQ": "XNAS", "JPX": "XJPX", "HKG": "XHKG", "KSC": "XKRX", "TAI": "XTAI", "SHH": "XSHG", "LSE": "XLON", "CRYPTO": "CRYPTO_24_7"}`.
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
(se rellena al terminar)
