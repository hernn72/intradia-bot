# T-019 paso 2a-code

SHA pre-registro de P3 (manda): `8b2dddb8fd66423d9550df496d1a2a85abd066b6`
Base de la rama: `main` = `026c96f9b8b7e1b6884eefa96356dc99e9a5d3d5` (solo documentación sobre `8b2dddb`)
SHA del código 2a-code: el del commit que contiene esta carpeta (`git log -1 -- evidence/2026-09-30-T-019-paso2a-code`)
Cosecha: `071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841`

Alcance: implementa exactamente D-50 a D-56. **No** implementa Score v2, **no** ejecuta P3 (no se
ha calculado ni leído ningún desenlace PIT), **no** cambia `config.yaml`, umbrales (70/60,
`calibrated: false`) ni el esquema (v7), y **no** se ha desplegado en la Pi (sigue en
`v0.4.1` = `8b2dddb`). Programó Codex en cuatro vueltas; supervisó y reprodujo Claude Code.

Ficheros de esta carpeta:
- `p3_population_control.py` / `.txt`: control de población contra el pre-registro (llama a la
  implementación, no al censo de 2a-doc) y control cruzado por el event study PIT.
- `06-*.tsv`: listados por motivo y huecos de STOXX, idénticos byte a byte a los de
  `evidence/2026-09-29-T-019-paso2a-doc-inspeccion/`.
- `01-verificaciones.txt`: salidas finales del supervisor (ruff, mypy, pytest, backtest v1 y
  reproducción byte a byte del control).
- `revision-look-ahead-previa.md`: revisión independiente previa a P3 y cierre de sus hallazgos.

Casos temporales (tests en `tests/test_point_in_time_context.py`):
- `test_analysis_timestamp_por_plaza`: las 8 filas de la ficha (XETRA verano/invierno, NYSE
  normal y desfases DST de primavera y otoño, JPX normal y con festivo, HKG Semana Santa).
- `test_vix_tendencia_point_in_time`: las 8 sesiones de VIX/STOXX de la ficha, incluido NYSE
  2026-08-26 → STOXX 2026-08-26 (no el 27) y JPX 2026-08-26 → VIX 2026-08-25.
- `test_paridad_r_ctx_cuatro_caminos_pit`: para esos 8 instantes, `run_analysis` (rama v2),
  `run_backtest`, `run_event_study_on_vintage` y `review_positions` (rama v2) reciben el mismo
  `MarketContext` que `resolve_point_in_time_context`.
- `test_sma200_sin_historia_excluye`, `test_hueco_stoxx_usa_ultimo_cierre_causal`,
  `test_exclusiones_p3_union_sin_doble_conteo`, `test_d54_cierres_extraordinarios_y_huecos_no_forzados`,
  `test_timer_coincide_con_pasadas_d50`, selector de modo y VIX ausente.

Controles contra el pre-registro (todos coinciden):

| | A-02 | cripto | Asia | SMA200 | Asia∩SMA | unión | final | activos | regiones | bloques | huecos STOXX |
|---|---|---|---|---|---|---|---|---|---|---|---|
| swing | 106.363 | 5.112 | 396 | 6.937 | 176 | 12.269 | **94.094** | 90 | 5 | **19** | 1.406 {1: 624, 3: 700, 4: 82} |
| medio | 94.273 | 4.722 | 218 | 0 | 0 | 4.940 | **89.333** | 90 | 5 | **5** | 1.312 {1: 620, 3: 610, 4: 82} |

sha256 swing `4aa12d85eb54d7a01c10a4a3e4cf04e8077c842829235a93b75f7bd19c62011a`, medio
`4d6eaab9b84ff23bade1df86a82e95f46da546917a226dc8438a8e88493020f8`. La intersección Asia∩SMA y
las regiones las comprobó el supervisor desde los listados y `census_p3_population`.

Efectos declarados en v1: `exchange_overrides_hash` pasa de `b17cb2…` a `87e4aa…` por los cinco
cierres de D-54, y cambian los recuentos históricos de huecos de HKG y TAI en la frescura. El
backtest v1 sobre la cosecha no cambia (`49b12c85…`, 866 operaciones).

Módulos principales:
- `advisor/context/point_in_time.py`: semántica D-50..D-56 para contexto PIT.
- `advisor/research/p3_population.py`: controles de población P3 sin desenlaces.
- `advisor/analysis/analyzer.py` y `advisor/report/tracking.py`: selección de contexto por versión; `1.0` conserva legacy y `2.0` queda conectado a PIT sin activarse.
- `advisor/backtest/runner.py`, `advisor/research/event_study.py`, `advisor/research/execution_filter.py`: selector `context_mode_for(score_model_version)` por defecto y guarda contra `legacy_v1` con versiones distintas de `1.0`.

Diseño:
- `ContextMode`: `1.0 -> legacy_v1`, `2.0 -> point_in_time`; cualquier otra versión falla.
- `point_in_time` explícito se permite en laboratorio con la config actual para P3, pero `legacy_v1` no puede usarse con score distinto de `1.0`.
- `PointInTimeContextResolver` pre-sesiona VIX, STOXX y Asia una vez, y cachea por `analysis_timestamp`.
- Producción v2 y seguimiento v2 usan `fetch_point_in_time_market_context`; seguimiento v1 vuelve a `fetch_market_context(provider, config.market_context)`.
- Tests cubren paridad R-CTX entre producción v2, pieza de backtest, pieza de event study y construcción de seguimiento para los casos temporales preregistrados.
- R1 corregido: VIX ausente en PIT deja `context=None`, `calculable=False` y `NO_CALCULABLE_CONTEXT_VIX` en `no_calculable_codes`; no crea una exclusión nueva ni aplica la regla v1 de mitad de puntos.
- R2 corregido: el backtest en modo `point_in_time` construye el resolver con `config.data_quality.settlement_minutes`, igual que producción, seguimiento, event study y filtro de ejecución.
- R3 corregido: el camino `legacy_v1` de backtest/event study/filtro carga solo VIX y tendencia; las cinco series asiáticas se leen únicamente en `point_in_time`.

Ejecución:

```bash
.venv/bin/python evidence/2026-09-30-T-019-paso2a-code/p3_population_control.py
```

Resultados:
- `p3_population_control.txt`: swing 94.094, sha `4aa12d85eb54d7a01c10a4a3e4cf04e8077c842829235a93b75f7bd19c62011a`; medio 89.333, sha `4d6eaab9b84ff23bade1df86a82e95f46da546917a226dc8438a8e88493020f8`.
- Control cruzado H4: `run_event_study_on_vintage(..., context_mode="point_in_time")` con desenlaces parcheados a `None` devuelve los mismos conteos y hashes que el censo.
- `01-verificaciones.txt`: salida literal de pytest, ruff, mypy y backtest v1; hash normalizado `49b12c855c2d2681d9ecd0f592248cd03b11cd8428273014238e04f0ddefbc3c`, 866 operaciones.

## Observaciones para el paso 2

- `fetch_point_in_time_market_context` lanza `RuntimeError` si el contexto es no calculable (Asia ausente o SMA200 sin historia). La conducta de producción v2 ante contexto no calculable no está pre-registrada; queda inerte mientras v1 esté activo y se decide antes de activar v2 (paso 5).
- Con la config activa (`"1.0"`), omitir `context_mode` en event study/backtest da el camino legacy. P3 debe pedir `point_in_time` explícitamente; el paso 2 debe ligar el cálculo de Score v2 al contexto PIT para que no pueda combinarse con el legacy.
- Backtest, event study y filtro descartan señales sin contexto PIT calculable dentro de sus listas por barra; P3 publica las cifras oficiales desde el censo, no desde esos contadores internos.
- `context_sin_sma` del informe de backtest sigue midiendo el camino legacy.
- `census_p3_population` fuerza `legacy_v1` para reconstruir la población A-02; fallaría con una config activa `"2.0"` por la guarda de modo.
- Si algún día aparece VIX ausente en PIT, R1 queda como `OWNER_DECISION_REQUIRED`: el censo P3 lanza `RuntimeError` ante `NO_CALCULABLE_CONTEXT_VIX`.
