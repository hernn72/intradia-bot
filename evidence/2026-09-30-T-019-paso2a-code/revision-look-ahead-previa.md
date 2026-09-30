# Revisión independiente previa a P3 — 2a-doc y 2a-code (2026-09-30)

Es la **revisión 1 de look-ahead** que exige la ficha T-019 («Revisión independiente de
look-ahead, en dos momentos»): se hace antes de P3 y cubre la regla congelada en 2a-doc
(`8b2dddb`) y su implementación en 2a-code. P3 no se ejecuta sin ella. La revisión 2, al final
de P3, queda pendiente.

- **Revisor:** agente `revisor` (Claude), independiente de quien programó (Codex) y del
  supervisor. Trabajó en solo lectura sobre el árbol sin commitear.
- **Mandato:** intentar demostrar que la implementación es incorrecta. Foco en look-ahead, D-50
  a D-56, la unión de exclusiones, los hashes de población, la paridad de los cuatro caminos,
  que Score v1 no cambie y que no se haya ejecutado P3.
- **Veredicto:** **ningún BLOCKER ni IMPORTANTE.** Dos MENOR y siete OBSERVATION.

## Qué verificó ejecutando

- **D-50, recalculado sin usar el código del módulo.** Usó `exchange_calendars` y la conversión
  de la hora de Londres con la base tz de pandas sobre los **11.336 pares** distintos (plaza, d,
  d+1) de la cosecha, todos los activos no cripto. Resultado: **0 diferencias** de
  `analysis_timestamp` y ningún conjunto vacío. Cubre DST, festivos de la plaza, cierres
  anticipados y el caso p == apertura, que queda excluido porque la desigualdad es estricta.
- **D-53, en los mismos pares.** Las sesiones de VIX y STOXX usadas y el número de cierres
  causales de la SMA coinciden al **100 %** con un filtro independiente «sesión esperada y
  cierre + 20 ≤ ts».
- **D-52, en los mismos pares.** L es siempre la última sesión cerrada causal y P la anterior del
  calendario con overrides. **No hay ningún caso de look-ahead.**
- **Casos concretos:**
  - el 2026-05-26 a las 06:00Z el VIX usa el 2026-05-22: la barra de Memorial Day se ignora;
  - STOXX usa el 22 con antigüedad 3, hueco D-56 sin exclusión;
  - ^HSI y ^TWII saltan los tifones de 2023-09-01, 2023-09-08 y 2024-10-31 sin excluir;
  - `analysis_timestamp_for_signal("HKG", 2023-08-31, 2023-09-01)` devuelve `None`, porque la
    entrada cae en un día cerrado.
- **Tests y análisis estático.** `tests/test_point_in_time_context.py` pasa, la suite completa
  pasa, y `ruff` y `mypy` salen limpios. `git status` quedó sin cambios.
- **Cosecha.** Sus índices son texto UTC con «Z» y el camino PIT los convierte en datetimes con
  zona, así que no reaparece `_naive_dates`.

## Qué verificó leyendo el código

- **Camino legacy de v1 idéntico al de `main`:**
  - en `analyzer.py` y `tracking.py`, la rama v1 es literalmente la llamada de `main`;
  - en `runner`, `event_study` y `execution_filter` se conservan `_align`, `shift(1)` y las
    mismas series;
  - `engine`, con `market_context_at=None`, ejecuta el código anterior;
  - el diff no toca `config.yaml`, los umbrales ni el esquema.
- **Selector.** "1.0" va a legacy y "2.0" a point-in-time; cualquier otra versión falla, y
  `legacy_v1` falla con cualquier versión distinta de "1.0".
- **Paridad R-CTX.** El test **no es tautológico**: recorre `run_analysis`, `run_backtest`,
  `run_event_study_on_vintage` y `review_positions`, y compara el `MarketContext` completo.
- **D-54.** Están las 5 fechas con sus fuentes, y los 3 huecos del proveedor siguen siendo
  sesión.
- **Efecto en v1.** Cambia `exchange_overrides_hash` y los recuentos históricos de huecos de HKG
  y TAI en la frescura. No afecta a los vetos actuales.
- **D-55 frente a D-56.** No se mezclan: solo se excluye con menos de 200 cierres.
- **Unión.** Deduplica por (activo, sesión); cripto se excluye antes de calcular D-50.
- **P3.** No encontró ningún indicio de que se ejecutara ni de que se leyeran desenlaces PIT.

## Hallazgos y cómo quedaron

| # | Clase | Hallazgo | Estado |
|---|---|---|---|
| R1 | MENOR | Con VIX ausente, el camino PIT puntuaba con la regla v1 de la mitad de los puntos, que la ficha reserva a v1 | **Corregido.** `context=None` y `NO_CALCULABLE_CONTEXT_VIX`; no se inventa ninguna exclusión, y el censo lanza `RuntimeError` si aparece. En la cosecha hay 0 casos |
| R2 | MENOR | El backtest PIT tomaba `settlement_minutes` de su parámetro (20 por defecto) y no de la config | **Corregido.** Lo toma de `config.data_quality.settlement_minutes` |
| O3 | OBSERVATION | El backtest v1 en vivo descargaba cinco series asiáticas que no usa | **Corregido.** El camino legacy solo carga VIX y tendencia |
| O1, O2, O4-O7 | OBSERVATION | Descartes PIT sin contador en backtest, event study y filtro; modo por defecto legacy con la config "1.0"; `context_sin_sma` legacy; producción v2 aborta si el contexto no es calculable; faltan tests unitarios explícitos de la barra del VIX en día sin sesión y del festivo asiático (cubiertos por la paridad y por la auditoría); no se ejecutó P3 | Registradas en el README, «Observaciones para el paso 2» |

**R1-R3 corregidos después de la revisión.** El supervisor revisó el delta, repitió la suite
completa (717), `ruff`, `mypy` y el backtest v1 (`49b12c85…`, 866 operaciones), y volvió a
ejecutar el control de población con resultado **byte a byte idéntico**
(`01-verificaciones.txt`). Las correcciones no tocan la regla temporal ni la población; no se
lanzó una segunda revisión completa.

**Límite declarado por el revisor.** Su auditoría comparte con el código `expected_sessions` (el
calendario con overrides) y `exchange_calendars`. Valida que se aplican bien, no los calendarios
en sí.
