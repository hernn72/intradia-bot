# T-015 — El backtest deja de depender del minuto en que se ejecuta

Estado: PENDIENTE
Agente: Opus (ficha) → Codex (implementación) → Opus (revisión)
Línea / fase: Línea C (ingeniería) con efecto directo sobre la línea A
Gate al que contribuye: GATE P2 (requisito 2: cosecha fijada) y GATE PROD
(requisito 4: reconstrucción probada)

## Objetivo
Que `backtest` produzca el mismo resultado dos veces seguidas. Hoy no lo hace,
y eso invalida cualquier cifra que se compare contra otra pasada.

## Por qué existe
Medido en la revisión de T-009, tres ejecuciones sobre el **mismo commit**
`6fbeed0`, la misma configuración y el mismo universo:

| Ejecución | Hora | Operaciones | COMPRAR | ESPERAR | DESCARTAR |
|---|---|---:|---:|---:|---:|
| línea base | 10:08 | 891 | 474 | 2310 | 7570 |
| tras el cambio | 10:56 | 893 | 478 | 2298 | 7567 |
| **repetición del anterior** | 11:00 | 890 | 474 | 2306 | 7569 |

Las dos últimas son **el mismo código con cuatro minutos de diferencia** y
difieren en 3 operaciones. Consecuencias, por orden de gravedad:

1. **Ningún criterio de aceptación puede apoyarse en comparar dos pasadas de
   backtest.** En T-009 hubo que sustituirlo por una comparación determinista
   sobre datos sintéticos, que no cubre la política `POLICY_OPERAR`.
2. **La línea base de la línea 0** (`evidence/2026-09-14-L0-baseline/`) y
   cualquier cifra publicada con `backtest --period Ny` no son reproducibles.
   No están mal: son irrepetibles, que a efectos de auditoría es peor.
3. GATE PROD exige reconstruir una recomendación de hace ≥ 30 días. Con el
   backtest actual esa reconstrucción no puede verificarse.

La causa es estructural, no un fallo: `cmd_backtest` descarga datos en vivo con
un periodo relativo a *ahora*. El proveedor revisa barras, la última vela se
mueve dentro de la sesión, y `trim_unclosed_bar` depende de la hora de la
pasada. El laboratorio tiene cosecha congelada (`data/vintages/071ddb2b…`)
justo para no depender de eso; el comando de backtest no la usa.

## Dependencias previas
Ninguna. Puede hacerse en paralelo con T-010. **Debe estar antes de A-02**
(T-013), porque A-02 rehace P2.3/P2.4/P2.5 y va a querer comparar poblaciones.

## Archivos probables
No asumir que sean exactos: verificar primero con búsqueda de símbolos.
- `advisor/main.py` — `cmd_backtest` y su parser.
- `advisor/backtest/runner.py` — `run_backtest`, donde se piden los datos.
- `advisor/research/vintage.py` y `advisor/research/execution_filter.py` — ahí
  ya está resuelto cargar una cosecha congelada: **se reutiliza ese camino**,
  no se escribe otro (INV-06).
- `advisor/run/manifest.py` — `data_vintage_id` ya viaja en el manifiesto.

## Invariantes que no pueden romperse
INV-06 (una sola forma de cargar una cosecha), INV-16 (si no se declara
vintage, se dice qué datos se usaron, no se finge determinismo),
point-in-time (la cosecha no puede contener barras posteriores a la señal).

## Implementación requerida

1. **`backtest --vintage <id>`**, que ejecuta la simulación sobre la cosecha
   congelada en vez de descargar. Es el modo que se usa para cualquier cifra
   publicable.
2. **La salida declara siempre con qué datos se hizo**: `data_vintage_id` real
   cuando hay cosecha, y un aviso explícito cuando son datos en vivo:
   «datos en vivo: este resultado **no** es reproducible». Sin vintage no se
   finge determinismo (INV-16).
3. **Test de reproducibilidad**: dos ejecuciones seguidas sobre la misma
   cosecha producen operaciones idénticas, comparadas una a una —fecha de
   entrada, precio, salida, motivo, R—, no solo el total.
4. **No cambiar el modo en vivo.** Sigue existiendo y sigue siendo el que usa
   quien quiere una foto rápida de hoy. Lo que cambia es que ahora lo dice.
5. **Medir la magnitud del problema y publicarla**: ejecutar el backtest en
   vivo tres veces seguidas y publicar la dispersión de operaciones y
   expectancy. Es el número que justifica la ficha y no existe fuera de la
   revisión de T-009.

## Qué NO debe modificarse
La lógica de simulación, la geometría, el score, las políticas. Esta ficha
cambia **de dónde salen los datos**, nunca qué se hace con ellos: las cifras
sobre la misma cosecha deben coincidir con las de hoy.

## Tests unitarios
- `test_backtest_sobre_cosecha_es_reproducible`: dos ejecuciones, operaciones
  idénticas campo a campo.
- `test_backtest_en_vivo_declara_que_no_es_reproducible`.
- `test_backtest_con_vintage_declara_el_data_vintage_id`.
- `test_la_cosecha_no_contiene_barras_posteriores_a_la_senal` (point-in-time).

## Verificación contra datos reales
```bash
.venv/bin/python -m advisor.main backtest --horizonte swing --vintage 071ddb2b > a.txt
.venv/bin/python -m advisor.main backtest --horizonte swing --vintage 071ddb2b > b.txt
diff a.txt b.txt   # debe ser vacío salvo el instante
```
Comprobar a mano: que el número de operaciones y la expectancy coinciden
exactamente, y que una tercera ejecución también.

## Medición del impacto
- Dispersión del modo en vivo en tres ejecuciones seguidas (el número que
  justifica la ficha).
- Diferencia entre el resultado sobre cosecha y el último resultado en vivo,
  declarada y explicada. **No tienen por qué coincidir**: la cosecha es de una
  fecha y el vivo es de hoy.

## Criterio de aceptación
- Dos ejecuciones sobre la misma cosecha son idénticas operación a operación.
- El modo en vivo declara que no es reproducible.
- La lógica de simulación no cambia.

## Criterio de rechazo
- Un segundo camino para cargar cosechas (INV-06).
- Presentar el modo en vivo como reproducible.
- Cualquier cambio en las operaciones sobre los mismos datos.

## Evidencia que debe quedar registrada
`evidence/<fecha>-T-015-backtest-reproducible/` con README.md, las tres
ejecuciones en vivo con su dispersión, las dos sobre cosecha con su `diff`
vacío, y la comparación declarada entre cosecha y vivo.

## Commit esperado
Rama `feat/reproducible-backtest`. Mensaje:
`feat(backtest): simular sobre cosecha congelada y declarar cuando los datos son en vivo`

## Actualización documental requerida
`docs/roadmap.md`: fila nueva en la línea C.
`docs/decision-log.md`: D-nn con la constatación de que las cifras de backtest
anteriores a esta ficha no son reproducibles, y qué se hace con la línea base
de la línea 0 (rehacerla sobre cosecha o etiquetarla como no reproducible).

## Handoff al siguiente agente
Pendiente de escribir al terminar.
