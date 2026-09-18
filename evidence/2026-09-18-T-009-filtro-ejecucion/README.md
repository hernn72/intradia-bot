# T-009 — Filtro de ejecución medido

## Comandos

```bash
source .venv/bin/activate
python -m pytest -q
ruff check .
mypy advisor
python -m advisor.main backtest --horizonte swing --period 5y
python -m advisor.main filtro-ejecucion --horizonte swing --vintage 071ddb2b
python -m advisor.main filtro-ejecucion --horizonte medio --vintage 071ddb2b
```

Commit medido: `6fbeed03a2f87a1e3a4c3a59d7822250a2804a33`.

Instantes:
- Línea base: `UTC 2026-09-18T09:07:16Z`.
- Verificación posterior: `UTC 2026-09-18T09:54:43Z`.

## Conclusión

Estado: **BLOQUEADA**.

El instrumento de medición queda implementado y la medición congelada queda
publicada. No se decide política de entrada: no se cambia `entry_max`, no se
añade holgura, no se toca el score y D-29 queda pendiente.

El bloqueo está en el criterio de aceptación del backtest live por defecto:
`antes.txt` y `despues.txt` no coinciden cifra a cifra, y una repetición
posterior inmediata tampoco coincide con `despues.txt`. Por tanto no se puede
certificar “cambio cero” contra esa evidencia viva.

## Resultados congelados

Swing:
- Ejecutadas: 994.
- Perdidas por entrada/ejecución: 1189.
- Contrafactuales simulables: 879.
- Motivos: `ABOVE_MAX_ENTRY` 1146/1189, `INVALID_STOP` 31/1189,
  `INVALID_TARGET` 12/1189, `RR_TOO_LOW` 0/1189.

Medio:
- Ejecutadas: 792.
- Perdidas por entrada/ejecución: 962.
- Contrafactuales simulables: 716.
- Motivos: `ABOVE_MAX_ENTRY` 926/962, `INVALID_STOP` 25/962,
  `INVALID_TARGET` 11/962, `RR_TOO_LOW` 0/962.

Broker neutral (`trade_republic="no"`):
- Swing: entran 85 señales de laboratorio que antes salían por broker.
- Medio: entran 74 señales de laboratorio que antes salían por broker.

## Hashes

Ver `hashes_tablas.txt`:

```text
56be50a2c4bcb6e72aa53d5ef2f8419adf2944a07bf25d710bb7e5a24e3af248  tabla_banda_poblacion_swing.md
32fc5e9aa5ccc1956f9e5dc10dd70d3bd3cdb791c3eb6eacb2e9058773e837b9  desglose_motivo_swing.md
c8a429cc3e374d312c0b520b6c9ca8606f911af1477fda1a52c71346b8db3a71  tabla_banda_poblacion_medio.md
30d04b2ecf5fdc5b5555f8dbaf42eefb1984e3f5637faf06f83cfd479d4cb79e  desglose_motivo_medio.md
```

## Verificación manual

Señal: `AAPL|swing|2023-12-13T05:00:00Z`.

```text
cierre_senal=197.960007
apertura_siguiente=198.020004
stop=192.234290
target2=206.548582
entry_max_tecnica=200.107150
entry_max_rr=(206.548582 + 1.5 * 192.234290) / (1 + 1.5) = 197.960007
entry_max=min(200.107150, 197.960007) = 197.960007
apertura_siguiente 198.020004 > entry_max 197.960007
rr_apertura=1.474075
```

## Backtest por defecto

Comparación exigida contra `antes.txt`:
- `antes.txt`: 891 operaciones, expectancy 0,21 R.
- `despues.txt`: 893 operaciones, expectancy 0,20 R.
- `backtest_repetido_post.txt`: 890 operaciones, expectancy 0,20 R.

Clasificación: **BLOCKER** de aceptación, no SAME_SCOPE. No se modifica la
política del backtest para forzar coincidencia.

## Pre-registro copiado antes de medir

## Pregunta, métrica y criterio — PRE-REGISTRO
Se escribe **antes** de medir, según `docs/protocolo-investigacion.md`. Si algo
se decide después de ver resultados, se etiqueta `exploratorio` y se dice.

- **Pregunta primaria:** de las señales que `classify_setup` aprueba, ¿qué
  fracción resulta no ejecutable a la apertura siguiente por
  `ABOVE_MAX_ENTRY`, y cuál es la diferencia de expectancy neta en R entre
  las ejecutadas y las descartadas por ese motivo?
- **Métrica primaria:** expectancy neta en **R por bloque temporal** (la misma
  que P2, para poder compararlas), calculada por separado en dos poblaciones:
  `EJECUTADAS` y `PERDIDAS_POR_ENTRADA`. La segunda se valora con una entrada
  contrafactual **declarada**: la apertura real (el precio que el asesor
  rechazó), mismo stop y mismos objetivos, mismo coste.
- **Métricas secundarias:** tasa agrupada de acierto, `P(objetivo antes de
  stop)`, MAE, MFE, payoff, profit factor, mediana y percentiles de R,
  tamaño de muestra; desglosadas por banda de score, región, horizonte y
  código de ejecución.
- **Población:** cosecha `071ddb2b…`, los 107 analizables, horizontes `swing`
  y `medio`, con `universe_vintage_id` y `data_vintage_id` en la salida.
- **Criterio de aceptación del gate:** el gate **no exige ningún valor**. Exige
  que los números estén publicados, con muestra e incertidumbre, y que el
  código de ejecución esté en cada señal. NO CONCLUYENTE es un resultado
  válido y se declara como tal.
- **Tratamiento de la incertidumbre:** bootstrap por bloques, la maquinaria
  que ya existe en `advisor/research/bootstrap.py` y `uncertainty.py`. Si la
  muestra de una celda no llega al mínimo ya declarado (`_MIN_SAMPLE`), la
  celda se publica como insuficiente, **no** se agrega con otra para
  alcanzarlo.
