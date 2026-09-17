# T-005 — Calidad del dato por dimensiones y códigos de descarte (PR 3, fases 7 y 8)

Estado: EN_REVISION
Agente: Opus (diseña el contrato, 1 sesión) → Codex (implementa) → Opus (revisa)
Línea / fase: L0 PR 3, fases 7 y 8
Gate al que contribuye: GATE L0 (requisito 3)

## Objetivo
`DataQuality` separa frescura, completitud reciente, completitud histórica,
disponibilidad de indicadores y ejecutabilidad, con severidad por antigüedad;
todo descarte y toda espera llevan un código estructurado y el informe agrupa
por él.

## Por qué existe
`OK/DEGRADADO/INCOMPLETO` mezcla tipos de problema (verificado en
`advisor/data/freshness.py::classify_data_quality`): un hueco de hace 150
sesiones y el cierre de ayer ausente caen en vocabularios que no distinguen
severidad, y el bloque «90 activos descartados: …» no permite saber por qué
cayó cada uno sin leer texto libre. Fases 7 y 8 de `docs/plan-ejecucion.md`.

## Dependencias previas
T-002 (migraciones), T-003 (calendarios), T-004 (causa del hueco). Decisiones
D-05 (la ventana de veto 20 se conserva como valor; su semántica pasa a
«completitud reciente»), D-16.

## Archivos probables
No asumir que sean exactos: verificar primero.
- `advisor/data/freshness.py` → `advisor/data/quality.py` (nuevo; `freshness.py` puede quedar como cálculo de antigüedad)
- `advisor/analysis/execution.py` (`DATA_NOT_EXECUTABLE` pasa a depender de `execution_readiness`)
- `advisor/analysis/opportunity.py` (`classify`, `classify_setup`, `_execution_reasons`; nuevo `discard_code`, `warnings`)
- `advisor/analysis/analyzer.py` (`AnalysisResult.skipped` pasa a llevar código)
- `advisor/report/formatter.py` (bloques RADAR, DESCARTADOS, calidad)
- `advisor/main.py` (`opportunity_to_row`, `freshness_row_to_measurement`)
- `advisor/storage/migrations.py` (v4: columnas `discard_code`, `execution_reason`, `quality_*`)
- `advisor/config.py` (`DataQualityConfig`: severidades por ventana)
- `tests/test_freshness.py`, `tests/test_quality.py` (nuevo), `tests/test_analysis.py`, `tests/test_report.py`

## Invariantes que no pueden romperse
INV-02, INV-03 (ninguna dimensión de calidad toca `score.value`), INV-04,
INV-05, INV-12, INV-16, INV-17.

## Implementación requerida (contrato que Opus fija antes de que Codex empiece)
1. `DataQuality` (frozen):
   `freshness: FreshnessState` (`FRESH | STALE_1 | STALE_2_PLUS | PARTIAL_BAR`),
   `recent_completeness: Severity`, `historical_completeness: Severity`,
   `indicator_readiness: bool` con `indicators_missing: tuple[str, ...]`,
   `execution_readiness: bool`, `reasons: tuple[QualityReason, ...]` donde
   `QualityReason = (code, severity, detail, sessions_ago)`.
   `Severity ∈ {OK, WARNING, MEDIUM, HIGH, CRITICAL}`.
2. Severidad por antigüedad de la sesión ausente más reciente, medida en
   **sesiones del calendario de la plaza**: última → `CRITICAL`; ≤ 5 → `HIGH`;
   ≤ 20 → `MEDIUM`; > 20 → `WARNING`. Los cortes van en `DataQualityConfig`
   con estos valores por defecto.
3. `execution_readiness = freshness == FRESH ∧ recent_completeness ∈ {OK,
   WARNING} ∧ indicator_readiness`. **`MEDIUM` veta**: un hueco entre 6 y 20
   sesiones cae dentro de la ventana de veto de D-05, y `CRITICAL` y `HIGH`
   vetan con más razón. Un `WARNING` histórico nunca veta salvo que provoque
   `indicators_missing` o historial insuficiente.

   > Corregido el 2026-09-16: la versión anterior escribía la fórmula como
   > `recent_completeness ≤ MEDIUM`, que **permitía** operar con `MEDIUM` y
   > contradecía su propia frase siguiente y a D-05. Codex detectó la
   > ambigüedad al implementar y eligió la lectura correcta; la fórmula queda
   > reescrita para que no dependa de elegir bien.
4. Códigos de descarte del setup (`discard_code`): `LOW_SCORE`,
   `INVALID_TREND`, `OVEREXTENDED`, `VOLATILITY_TOO_HIGH`, `EVENT_RISK`,
   `HOSTILE_CONTEXT`, `BELOW_RISK_FREE`, `NO_LEVELS`, `INSUFFICIENT_HISTORY`,
   `INVALID_INDICATORS`. Códigos de ejecución: los de
   `advisor/analysis/execution.py` más `STALE_DATA`, `MISSING_RECENT_DATA`.
   `warning` es una lista aparte y nunca implica descarte.
5. `Opportunity` gana `discard_code: Optional[str]`, `execution_code: str`,
   `warnings: tuple[str, ...]`, `data_quality: DataQuality`; `decision_reasons`
   se conserva para el texto.
6. Informe: DESCARTADOS agrupados por código con conteo; RADAR muestra
   código; el detalle de fechas antiguas va al log/JSON, no al informe.
7. Persistencia (migración v4): `discard_code`, `execution_code`,
   `quality_freshness`, `quality_recent`, `quality_historical`,
   `execution_ready`.

## Qué NO debe modificarse
`compute_score`, `compute_levels*`, umbrales de score, ventana 20, `evaluate_trade_at_entry` salvo el origen de `DATA_NOT_EXECUTABLE`.

## Tests unitarios
Con calendario XETRA y referencia 2026-09-14 07:00 UTC:
- ausente 2026-09-11 (última) → `CRITICAL`, `execution_ready False`.
- ausente hace 3 sesiones → `HIGH`, no ejecutable.
- ausente hace 15 → `MEDIUM`, no ejecutable (D-05).
- ausente hace 150 → `WARNING`, `execution_ready True`, `score` intacto.
- festivo de la plaza → no es ausencia.
- historial suficiente con `WARNING` → ejecutable.
- `sma_long` no calculable por el hueco → `indicator_readiness False`.
- `discard_code` para score 64 con umbral 70 → `LOW_SCORE`, `threshold` en detalle.

## Tests de integración
- `test_operar_implica_execution_ready` (fase 13, invariante 1 ampliada).
- `test_warning_historico_no_cambia_radar` con fixture realista (`unknown`, ISIN null).
- `test_informe_agrupa_descartes_por_codigo`: 90 activos sintéticos → cada uno en exactamente un grupo.

## Verificación contra datos reales
```bash
python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar > evidence/<fecha>-T-005-calidad/despues.txt
```
Comprobar a mano: `NOVO-B.CO` (ausencias 2026-03/04/05/06 y 09-07): la más
reciente decide la severidad; recalcular cuántas sesiones XCSE hay entre esa
fecha y la referencia y comprobar el tramo. Un activo con solo huecos > 20
sesiones debe aparecer `WARNING` y ejecutable.

## Medición del impacto
- Tabla activos por `discard_code` / `execution_code` antes (texto libre) y después.
- nº activos que pasan de vetado a ejecutable y por qué (esperado: solo los
  de huecos > 20 sesiones que además estaban vetados por otro motivo → 0 si
  D-05 ya lo evitaba; comprobar).
- nº señales de investigación afectadas: 0 (declararlo).

## Criterio de aceptación
- Cero descartes sin código en la salida real; cada activo en un solo grupo.
- Tests y CI en verde; migración con backup verificado.
- Revisión de Opus: INV-03 comprobada leyendo `compute_score` y sus llamantes.

## Criterio de rechazo
- Cualquier código que altere `score.value`.
- Un `WARNING` que vete.
- Texto libre como único motivo.

## Evidencia que debe quedar registrada
`evidence/<fecha>-T-005-calidad/` con `despues.txt`, tabla por código y README.

## Commit esperado
Rama `refactor/data-quality-codes`. Mensajes:
`refactor(data): calidad del dato por dimensiones con severidad por antigüedad` y
`refactor(signals): códigos estructurados de descarte y de ejecución` (dos commits si compilan por separado; uno si no).

## Actualización documental requerida
`docs/roadmap.md`: PR 3 → ACEPTADA. `README.md`: vocabulario de calidad y códigos. `docs/plan-ejecucion.md`: fases 7 y 8 con fecha.

## Handoff al siguiente agente
Codex implementó la capa estructurada el 2026-09-16 en la rama
`refactor/data-quality-codes`, sin commit ni push por límite de sesión.

Hecho:
- `DataQuality`/`Severity`/`FreshnessState`/`QualityReason` en
  `advisor/data/quality.py`, con severidad por sesiones de plaza y
  `execution_readiness` que veta `MEDIUM`, `HIGH`, `CRITICAL`, stale/partial
  e indicadores ausentes.
- La causa de huecos vivos reutiliza el vocabulario de
  `advisor/data/bar_diagnostics.py` (`proveedor no la entrega`) y declara en
  código el hallazgo de T-004.
- `DataFreshness` lleva `data_quality`, indicadores ausentes y ventana medida
  (`measurement_period`, `measurement_interval`).
- `Opportunity` añade `discard_code`, `execution_code`, `warnings` y
  `data_quality`; la extensión de precio pasa a `warnings` y no descarta.
- `DATA_NOT_EXECUTABLE` nace de `data_quality.execution_readiness`.
- Informe: RADAR muestra código; DESCARTADOS agrupa por código.
- Persistencia v4: códigos/calidad/ejecutabilidad y ventana persistida en
  recomendaciones y mediciones de frescura.

Verificado localmente:
- Antes de tocar: `python -m pytest -q` → 469 passed; `ruff check .` limpio;
  `mypy advisor` limpio.
- Después: `python -m pytest -q` → 478 passed, 3 warnings conocidas;
  `ruff check .` limpio; `mypy advisor` limpio.
- No se ejecutó verificación real contra proveedor por el límite explícito de
  esta sesión: sin DNS/no red.

Invariantes revisadas:
- INV-03: no se modificó `compute_score`; calidad/ejecución se calculan fuera
  y solo afectan `execution_readiness`, `discard_code`, `execution_code` y
  salida.
- INV-04: se conserva `trade_republic="unknown"` como `BROKER_UNVERIFIED`.
- INV-06: la causa de hueco reutiliza `bar_diagnostics`; no se creó
  taxonomía paralela.
- INV-17: v4 usa `run_migration` con DDL y `PRAGMA user_version` en la misma
  transacción; `AdvisorDB` mantiene backup previo verificado.

Pendiente para Claude Code/Opus:
- Ejecutar contra datos reales:
  `python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar > evidence/2026-09-16-T-005-calidad/despues.txt`
- Medir tabla por `discard_code`/`execution_code`, revisar NOVO-B.CO a mano y
  completar impacto real.
- Revisión independiente obligatoria por cambios en `classify()` y migración.

Ambigüedad registrada:
- El contrato dice `recent_completeness ≤ MEDIUM`, pero también dice
  explícitamente que `MEDIUM` veta y que se conserva D-05. La implementación
  eligió la segunda lectura: solo `OK` y `WARNING` pasan completitud reciente.
- `discard_code` nombra códigos de setup, pero la ficha exige código para toda
  espera; por eso `LOW_SCORE` se guarda también cuando el setup queda en
  `VIGILAR/ESPERAR` por estar bajo `min_score_operar`.

## Segunda revisión independiente — 2026-09-17 — CORREGIR, corregido

La primera revisión dio CORREGIR y sus siete defectos se arreglaron en
`98039b4`. La segunda revisó **esas correcciones** y encontró cuatro hallazgos
de alcance, los cuatro reproducidos y corregidos el mismo día:

1. **La deduplicación de la frescura quedó a medias.** `98039b4` decía haber
   eliminado el segundo camino y solo lo había hecho dentro de `analyze_asset`:
   `medir_frescura_datos` seguía construyendo `DataQuality` sin el cierre de
   plaza y sin las ventanas de configuración, de modo que el mismo activo en el
   mismo instante salía `FRESH`/ejecutable por un camino y `PARTIAL_BAR`/no
   ejecutable por el otro. Corregido pasando las ventanas de config y dejando
   `data_quality` en `None` en ese camino, que mide el dato crudo y no puede
   sostener un veredicto de ejecución. Ver D-22 (propuesta).
2. **El aviso de precio extendido seguía perdido, y además dejó de guardarse.**
   `format_opportunity` solo se genera para las OPERAR, así que el bloque RADAR
   nunca lo imprimía; y al sacarlo de `decision_reasons` salió de lo único que
   la fila persistía, con lo que desapareció de la base de datos **también para
   las OPERAR**. Corregido: se imprime en RADAR y viaja en una columna
   `warnings` propia, añadida a la migración v4 —que todavía no está en `main`,
   así que no hace falta una v5.
3. **`_skip_code` atribuía una causa que nadie había comprobado.** Un 404 del
   proveedor, un timeout o una plaza sin calendario se publicaban como
   `INVALID_INDICATORS`. Corregido con `ANALYSIS_ERROR` para el fallo no
   reconocido, que es lo que exige INV-16.
4. **Faltaban tests que la ficha pedía.** Añadidos el de severidad `CRITICAL`
   —que no tenía ninguno pese a ser la máxima— y uno del bloque DESCARTADOS que
   llega al código por `build_opportunity` en vez de fijarlo con `replace`. El
   que existía pasaba en verde con el defecto reintroducido; el nuevo falla.

### Consecuencia sobre el objetivo 6, que conviene dejar escrita

«DESCARTADOS agrupados por código con conteo» queda **degenerado a un solo
grupo** y no es un fallo: `RADAR_DESCARTAR` solo se alcanza por nota, así que
todo descarte es `LOW_SCORE` mientras el clasificador de setup no tenga más
ramas. Los códigos `INVALID_TREND`, `OVEREXTENDED`, `VOLATILITY_TOO_HIGH` y
`EVENT_RISK` están declarados y **nadie los asigna nunca**. El `or "SIN_CODIGO"`
de `formatter.py` es inalcanzable en producción. Si se quiere que el bloque
vuelva a discriminar, hay que darle ramas al clasificador del setup, no
devolverle el código de calidad.
