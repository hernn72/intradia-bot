# T-019 paso 2 - Score v2 en codigo, sin activar

- Base: `main` = `b2d4d4f617b9402274448e92b1e6b22dfb3ec9cd` (PR #31 fusionado).
- Pre-registro P3 (manda): `8b2dddb8fd66423d9550df496d1a2a85abd066b6`.
- SHA del código del paso 2: el del commit que contiene esta carpeta (`git log -1 -- evidence/2026-09-30-T-019-paso2`).
- Programó Codex en cuatro vueltas; supervisó, reprodujo y verificó Claude Code. Revisión independiente: `revision-independiente.md` (sin BLOCKER ni IMPORTANTE; cuatro MENOR corregidos). Verificación final del supervisor: `01-verificaciones-supervisor.txt`.
- La Pi no se ha tocado: sigue en `v0.4.1` = `8b2dddb`, esquema v7, Score v1. Score v2 no es activable por configuración hasta que el paso 5 implemente D-60.
- Por qué la confianza no cambia en A-02: la dimensión fundamental falta siempre (una dimensión ausente impide «Alta») y todas las señales tienen historia e indicadores completos, así que la fórmula antigua y la nueva dan «Media». La medición es sobre la cosecha; no se midió sobre una pasada de producción.
- P3 no ejecutado: no expectancy, no quintiles confirmatorios, no candidatos ni calibracion.
- `config.yaml` permanece con `scoring.score_model_version: "1.0"` y thresholds `70/60`, `calibrated: false`.

## Formula implementada

- v1: catalizador 20 + fundamental 20 no disponible + tecnico 20 + beneficio/riesgo 20 + contexto 10 + conviccion 10. Caso base: `51/80 = 63.75`.
- v2: catalizador 20 + tecnico 20 + contexto 10; fundamental sigue no disponible y fuera del denominador; sin beneficio/riesgo ni conviccion. Caso base: `31/50 = 62.0`.
- Normalizacion comun: `100 * points / evaluable_max`, o `0` si `evaluable_max == 0`.

## Diseno

- `compute_score` despacha explicitamente por `model_version`. v1 conserva `levels` y `min_bars`; v2 rechaza `levels` y `min_bars`.
- `Score.model_version` expone la version guardada en `score_model_version`.
- Versiones implementadas: `{"1.0", "2.0"}`. Versiones activables por configuracion: `{"1.0"}`.
- Segunda vuelta P1: `Opportunity.confidence_min_bars` y `build_opportunity(..., confidence_min_bars=...)` son obligatorios; los tests y llamantes pasan el `min_bars` del horizonte.
- Segunda vuelta P2: la config efectiva de investigacion para v2 se construye en `advisor.config.scoring_for_requested_model`, validada por `ScoringConfig` con contexto explicito de investigacion; no usa `model_construct` ni vuelve v2 activable.
- D-59: `model_version="2.0"` deriva contexto `point_in_time`; `legacy_v1` con v2 falla. `MarketContext.source` marca el origen y Score v2 exige `source == "point_in_time"`.
- Cuarta vuelta M1: en PIT, un universo sin series asiaticas produce `excluded_asia_missing` con detalle `sin series asiáticas en el universo`; Score v2 rechaza `asia_change_pct`, `vix_value` o tendencia/SMA nulos aunque el `MarketContext` tenga `source="point_in_time"`.
- Investigacion (`analyzer`, `backtest`, `event_study`, `execution_filter`) acepta `score_model_version` explicito sin cambiar la config activa.
- Bandas v1 (`score_band` / `SCORE_BANDS`) rechazan observaciones con `score_model_version != "1.0"`.
- Cuarta vuelta M2: `run_execution_filter_study` rechaza `score_model_version="2.0"` porque el estudio es de bandas v1; `_band_for_trade` y el informe de backtest tambien rechazan operaciones v2.
- Segunda vuelta P4: `score_label` es una unica funcion compartida por formatter y texto al LLM. Presentacion v2 no usa `Score.grade` ni `conviction_label`; muestra `sin umbral calibrado`.

## Tests discriminantes

- Formula v1 y v2 del caso base: v1 `63.75`, v2 `62.0`, `evaluable_max=50`.
- RR presente fuera de v2 y firma v2 sin `levels`/`min_bars`.
- Version desconocida falla.
- Score v2 con contexto legacy falla (`test_compute_score_v2_rechaza_contexto_legacy`).
- D-59 en `run_analysis`, `run_backtest`, `run_event_study_on_vintage` y `run_execution_filter_study` (`test_d59_v1_legacy_permitido_v2_pit_automatico_y_v2_legacy_falla`).
- Investigacion pide v2 con config activa v1 mediante `scoring_for_requested_model`; produccion con config v1 sigue en v1.
- v2 no contiene `beneficio_riesgo` ni `conviccion`; cambiar ATR, RR/min_rr, frescura o broker no cambia `Score.value`.
- Cuarta vuelta M3: el test de presentacion toma etiquetas reales de `Score.grade` y `conviction_label` (`Convicción media`, `Especulativa`) para asegurar que no se filtran a v2.
- Presentacion v2 no filtra etiquetas cualitativas v1 y dice `sin umbral calibrado`.
- Confianza calculada desde snapshot: barras e indicadores; ATR% fuera.
- Bandas v1 rechazan observaciones v2, tambien al resumir por banda; execution filter e informe de backtest rechazan v2.
- Cuarta vuelta M4: los tests de RR/min_rr, calidad/frescura/broker y ATR/RR ahora pasan por ejecutabilidad/clasificacion real y discriminan cambios observables sin mover `Score.value` v2.
- Tercera vuelta: INV-06 codigo sobre la cosecha `071ddb2b...` para `AAPL`, `SAP.DE` y `SXR8.DE`: `test_inv06_score_v2_coincide_en_analyzer_engine_y_event_study`.
- Tercera vuelta: equivalencia v2 frente a reconstruccion desde v1 con el mismo contexto PIT: `test_score_v2_equivale_a_reconstruccion_desde_observaciones_v1`.
- Cuarta vuelta M1: el universo del test real incluye las cinco series asiaticas de produccion: `^N225`, `^HSI`, `^KS11`, `^TWII`, `510300.SS`.

## Impacto D-46 en confianza

Salida: `confidence_impact.txt`.

```text
# Impacto D-46 en Opportunity.confianza

cosecha=071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841
desenlaces=parcheados_a_None

=== swing ===
senales_A02_v1=106363
matriz antigua -> nueva:
  Alta: Alta=0 Media=0 Baja=0
  Media: Alta=0 Media=106363 Baja=0
  Baja: Alta=0 Media=0 Baja=0
motivos:
  Media->Media sin_cambio: 106363

=== medio ===
senales_A02_v1=94273
matriz antigua -> nueva:
  Alta: Alta=0 Media=0 Baja=0
  Media: Alta=0 Media=94273 Baja=0
  Baja: Alta=0 Media=0 Baja=0
motivos:
  Media->Media sin_cambio: 94273
```

No cambia ninguna etiqueta en A-02: todas las senales v1 ya eran `Media` y siguen `Media`.

## Controles

```text
.venv/bin/python -m ruff check .
All checks passed!
```

```text
.venv/bin/python -m mypy advisor
Success: no issues found in 70 source files
```

```text
.venv/bin/python -m pytest -q
743 passed, 3 warnings in 141.12s (0:02:21)
```

Tercera vuelta aislada:

```text
.venv/bin/python -m pytest -q tests/test_score_v2_real_vintage.py
..                                                                       [100%]
=============================== warnings summary ===============================
tests/test_score_v2_real_vintage.py::test_inv06_score_v2_coincide_en_analyzer_engine_y_event_study
tests/test_score_v2_real_vintage.py::test_inv06_score_v2_coincide_en_analyzer_engine_y_event_study
  /Users/fer/Desktop/Trading bot/intradia-bot/.venv/lib/python3.12/site-packages/exchange_calendars/exchange_calendar_xhkg.py:363: DeprecationWarning: The 'generic' unit for NumPy timedelta is deprecated, and will raise an error in the future. This includes implicit conversion of bare integers (e.g. `+ 1`).Please use a specific unit instead.
    easter_monday = EasterMonday.dates(years[0], years[-1] + 1)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2 passed, 2 warnings in 16.88s
```

Backtest A-02 v1:

```text
49b12c855c2d2681d9ecd0f592248cd03b11cd8428273014238e04f0ddefbc3c  -
866 operaciones | win rate 42% | expectancy R 0,17 | profit factor 1,25 | payoff 1,74 | R mediana -1,03 | R total 145,10 | desv. R 1,67 | P10/P25/P50/P75/P90 -1,17/-1,07/-1,03/1,67/2,13 | 10 velas de media
```

Control de poblacion PIT ejecutado en `/private/tmp/p3-pop-r4.XKHHSo`, sin modificar `evidence/2026-09-30-T-019-paso2a-code/`:

```text
=== swing ===
A-02 población: 106363 | saltados: 0
excluded_crypto: 5112
excluded_asia_missing: 396
excluded_trend_sma_history: 6937
excluidas unión deduplicada: 12269
POBLACION FINAL: 94094 señales | 90 activos
bloques con señales: 19
sha256 población final: 4aa12d85eb54d7a01c10a4a3e4cf04e8077c842829235a93b75f7bd19c62011a
hueco intermedio de ^STOXX50E: 1406 | antigüedad: {1: 624, 3: 700, 4: 82}
control cruzado event_study PIT swing:
  señales: 94094 (OK)
  sha256: 4aa12d85eb54d7a01c10a4a3e4cf04e8077c842829235a93b75f7bd19c62011a (OK)
comparación TSV swing:
  06-excluded_crypto-swing.tsv: OK
  06-excluded_asia_missing-swing.tsv: OK
  06-excluded_trend_sma_history-swing.tsv: OK
  06-stoxx_hueco_intermedio-swing.tsv: OK
=== medio ===
A-02 población: 94273 | saltados: 0
excluded_crypto: 4722
excluded_asia_missing: 218
excluded_trend_sma_history: 0
excluidas unión deduplicada: 4940
POBLACION FINAL: 89333 señales | 90 activos
bloques con señales: 5
sha256 población final: 4d6eaab9b84ff23bade1df86a82e95f46da546917a226dc8438a8e88493020f8
hueco intermedio de ^STOXX50E: 1312 | antigüedad: {1: 620, 3: 610, 4: 82}
control cruzado event_study PIT medio:
  señales: 89333 (OK)
  sha256: 4d6eaab9b84ff23bade1df86a82e95f46da546917a226dc8438a8e88493020f8 (OK)
comparación TSV medio:
  06-excluded_crypto-medio.tsv: OK
  06-excluded_asia_missing-medio.tsv: OK
  06-excluded_trend_sma_history-medio.tsv: OK
  06-stoxx_hueco_intermedio-medio.tsv: OK
```
