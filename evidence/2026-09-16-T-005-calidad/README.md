# T-005 — calidad del dato por dimensiones y códigos de descarte

- Fecha: 2026-09-16 · Rama `refactor/data-quality-codes` · base `main` `c255e0c`
- Implementación: Codex · Verificación real, medición y correcciones: Claude Code
- Suite final: **483 tests**, `ruff` y `mypy` limpios (60 ficheros)

## Impacto medido, comparando dos pasadas reales seguidas

Para que el mercado no confundiera la comparación, la pasada «antes» se ejecutó
desde un worktree en `c255e0c` minutos después de la pasada «después».

| | Antes (T-004) | Después (T-005) |
|---|---|---|
| OPERAR | 4: `EUNN.DE`, `EXH1.DE`, `EXV1.DE`, `CRWD` | 1: `CRWD` |
| Descartados | 88, motivo en texto libre | 89, repartidos en 4 códigos |
| Códigos | — | `LOW_SCORE` 51 · `MISSING_RECENT_DATA` 22 · `STALE_DATA` 13 · `PARTIAL_BAR` 3 |

Cada activo cae en **un solo** grupo y 51+22+13+3 = 89: se cumple el criterio de
aceptación «cero descartes sin código».

**Activos que pasan de ejecutable a vetado: 3**, los tres ETF europeos, y los
tres por `STALE_DATA`. **De vetado a ejecutable: 0.**

**INV-03 comprobada con datos, no solo leyendo:** `advisor/analysis/scoring.py`
no aparece en el diff y `compute_score` solo recibe snapshot, niveles, contexto
y config. En las dos pasadas seguidas, las notas coinciden exactamente:
`TTE.PA` 70, `ENI.MI` 70, `R6C0.DE` 68 antes y después.

## Cuatro defectos encontrados al verificar, ninguno visible en los tests

Medidos ejecutando `analyze_asset` real sobre activos concretos, no con fixtures.

**1. Se fabricaba una sesión ausente que no existía.** `EXH1.DE` no tiene
ninguna ausencia —las dos tuplas vacías— y recibía `recent_completeness =
CRITICAL` con el motivo «cola de sesiones cerradas no disponible». El retraso
del dato se estaba convirtiendo en una sesión ausente, y con la severidad
máxima, que la ficha reserva para «falta la última sesión». El retraso ya vive
en `freshness`, así que se contaba dos veces.

**2. Las dos dimensiones de completitud estaban intercambiadas.** El hueco de
`SXR8.DE` del 2026-03-06 está fuera de la ventana de veto y salía como
`recent = CRITICAL`, `historical = OK`. Eso rompía D-05: el activo pasó de
`DEGRADADO` sin vetar a `INCOMPLETO` vetado por un hueco de hace 134 sesiones.

**3. `sessions_ago` valía 0 siempre**, lo que inutilizaba la ordenación por
antigüedad y hacía que cualquier ausencia pareciera la última. Ahora usa
`closed_sessions_between` del calendario de la plaza: el hueco de `SXR8.DE`
declara `sessions_ago = 134`.

**4. Doce activos asiáticos quedaban vetados cada día por una barra cerrada.**
`7203.T` y `0700.HK` declaraban «última barra cerrada según cierre regular
15:30 Asia/Tokyo + 20 min» y `may_be_partial = False`, y aun así su
`DataQuality` decía `PARTIAL_BAR`. La causa es estructural: `build_data_quality`
corre **dentro** de `calcular_frescura_serie`, antes de que el analizador
corrija la barra parcial con el cierre real de la plaza, así que la calidad se
construía con el valor viejo.

Se corrigió de raíz y no en el síntoma: el dato de si la barra está cerrada
entra ahora **como parámetro** (`barra_actual_cerrada`) en la función que
construye la calidad, y la corrección a posteriori del analizador desaparece.
Es el mismo patrón que ya había producido el fallo de cripto de esta mañana.

Efecto: `PARTIAL_BAR` baja de 15 activos a 3, y esos 3 son las criptos, que sí
tienen barra parcial por definición. Los doce asiáticos vuelven a evaluarse y
caen por nota.

Verificación de los tests de regresión: el de la barra asiática **falla** con el
defecto reintroducido y pasa sin él.

## La decisión del propietario sobre el dato retrasado

Preguntado explícitamente, el propietario eligió que **un dato con una sesión de
retraso vete la apertura**, que es lo que la ficha especificaba. Queda como
D-21.

Medido después sobre las 21 pasadas guardadas en la Pi, el retraso europeo **no
es permanente: depende de la hora de la pasada**.

| Pasada (UTC) | Europeos con retraso |
|---|---|
| 06:02 y 07:32 | 45–47 de 47 (96–100 %) |
| 13:32 | 18 de 47 (38 %) |
| 20:02 | **0 de 47** |

Y es limpiamente geográfico: 1.197 mediciones de activos no europeos y 63 de
cripto, **cero con retraso**. El lunes 14 no hubo retraso en ninguna pasada,
porque el fin de semana da tiempo a que llegue la barra del viernes.

Con las cuatro pasadas actuales (07:00, 08:30, 14:30 y 21:00 hora local), la
consecuencia es que **las dos de la mañana no podrán recomendar ningún activo
europeo, la de las 14:30 podrá con parte, y la de las 21:00 con todos**. Queda
como decisión operativa pendiente del propietario: aceptar mañanas solo con
valores de EE. UU., o mover las pasadas.

## Consecuencia sobre cripto, que conviene decidir aparte

Las tres criptos tienen barra parcial siempre, porque su sesión 24/7 no cierra
hasta las 00:00 UTC más el margen de liquidación. Con la regla elegida —solo
`FRESH` es ejecutable— **cripto no es recomendable en ninguna de las cuatro
pasadas**. No es un defecto: se deduce de la regla. Pero nadie lo decidió
explícitamente, así que se anota para revisarlo.

## Ambigüedad corregida en la propia ficha

La ficha escribía la regla como `recent_completeness ≤ MEDIUM`, que **permite**
operar con `MEDIUM`, y en la frase siguiente decía que `MEDIUM` veta y que se
conserva D-05. Codex detectó la contradicción al implementar y eligió la lectura
correcta. La fórmula queda reescrita para que no dependa de acertar.
