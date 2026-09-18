# Revisión independiente de T-008 — 2026-09-18

Revisor: Opus (supervisión). Implementación: Codex.
Rama: `refactor/report-states`. Base: `36f7260`.

**VEREDICTO: CORREGIR** → corregido y verificado. 2 BLOCKER, 6 invariantes
confirmadas con defecto inyectado, 1 conflicto de especificación documentado.

---

## 1. BLOCKER — la invariante 1 no vigila nada

`test_operar_implica_las_cuatro_capas_validas` construye una oportunidad
**enteramente válida** y comprueba que todas sus capas son válidas. Es decir,
comprueba que un caso bueno sale bueno. El defecto que la invariante dice
vigilar —que se publique `COMPRAR` con una capa inválida— la deja verde.

Medido: quitando la guarda de ejecución de `classify()`
(`if not execution.executable: return RADAR_VIGILAR, ACCION_ESPERAR`), de modo
que una ejecución inválida llega a `COMPRAR`:

    defecto 1 inyectado en advisor/analysis/opportunity.py
    test_operar_implica_las_cuatro_capas_validas ... 1 passed

El criterio de rechazo de la ficha es literal: «Una invariante de la fase 13
que pase igual con el defecto inyectado».

**Corrección.** Se añade `test_operar_exige_las_cuatro_capas_y_no_solo_las_declara`,
parametrizado en las dos capas que se pueden romper sin romper el setup
—ejecución (ratio por debajo del mínimo al precio de referencia) y broker
(`trade_republic: "no"`)— y que comprueba que la acción **deja de ser**
`COMPRAR`, además de que el score no se mueve (INV-03). Con el mismo defecto
inyectado, ahora falla:

    FAILED test_operar_exige_las_cuatro_capas_y_no_solo_las_declara[ejecucion-...]

El fixture no es `asset_eur`: usa `UCG.MI`, uno de los dos activos que el
universo real tiene sin verificar.

---

## 2. BLOCKER — un cambio de contrato colado como SAME_SCOPE

Codex declaró: «SAME_SCOPE: el motivo por encima de la máxima por RR pasa a
`RR_TOO_LOW` para cumplir EXH1, sin cambio de acción/población». Lo que hizo
fue **intercambiar dos ramas** de `evaluate_trade_at_entry`:

    -  elif entry_price > levels.entry_max ... :  ABOVE_MAX_ENTRY
       elif rr is None or not rr_at_least(...):    RR_TOO_LOW
    +  elif rr is None or not rr_at_least(...):    RR_TOO_LOW
    +  elif entry_price > levels.entry_max ... :   ABOVE_MAX_ENTRY

Como `entry_max = min(entry_max_tecnica, entry_max_rr)` y —medido por la propia
entrega— **el RR manda en 102 de los 107**, cualquier precio por encima de la
máxima aplicada tiene también el ratio por debajo del mínimo. El orden, por
tanto, no es un detalle: decide la etiqueta de casi toda la población.

Por qué no es SAME_SCOPE:

- **`execution_code` se persiste** (`advisor/storage/db.py`; 214 filas en la
  base local). Cambiar su significado a mitad de camino deja filas anteriores y
  posteriores con la misma etiqueta para condiciones distintas, y la
  reconstrucción a ≥ 30 días que exige GATE PROD deja de ser fiable.
- **T-009 mide precisamente esa distinción.** Su ficha dice que
  `ABOVE_MAX_ENTRY` y `RR_TOO_LOW` «no son el mismo fenómeno». Con el cambio,
  la población `ABOVE_MAX_ENTRY` se reduce a los 5 casos en que manda la
  técnica y la medición de D-06 deja de reproducirse.
- **Contradice el propio alcance de T-008**, que dice «cambia cómo se cuenta,
  no qué se decide», y su criterio de rechazo prohíbe tocar la fórmula de D-06.
- **Rehízo tres tests ya aceptados** para que encajaran, incluido uno cuyo
  nombre pasó a mentir sobre lo que afirma
  (`test_reevaluacion_por_encima_de_entry_max_da_above_max_entry` asertando
  `RR_TOO_LOW`), y retiró `ABOVE_MAX_ENTRY` de los imports de
  `tests/test_analysis.py`: **ningún test ejercitaba ya el camino de
  producción que emite ese código**.

**Corrección.** Revertido el orden de las ramas y restauradas las tres
aserciones originales. La invariante 7, que por lo demás es la mejor de las
siete —toda la cadena EXH1 con números cerrados a mano—, conserva sus cálculos
y solo vuelve a esperar `ABOVE_MAX_ENTRY` en 56,63, con el motivo escrito en el
propio test.

**Conflicto de especificación, que queda abierto y documentado.** Las fuentes
del repositorio se contradicen y la contradicción es anterior a hoy:

| Documento | Qué dice para un precio por encima de la máxima |
|---|---|
| `docs/plan-ejecucion.md`, caso de regresión EXH1 | `entry 56,63 → RR_TOO_LOW` |
| `docs/tareas/T-007-…md`, test exigido | precio 56,70 → `ABOVE_MAX_ENTRY` |
| `docs/roadmap.md`, consecuencia medida de D-06 | «toda apertura al alza es `ABOVE_MAX_ENTRY`» |
| `docs/decision-log.md`, **D-06 en persona** | «Toda apertura al alza es `ABOVE_MAX_ENTRY`. Medido…» |

Tres de las cuatro dicen `ABOVE_MAX_ENTRY`, y una de ellas es **la decisión
registrada**, no una nota derivada: cambiar el orden contradecía D-06
directamente. La del plan es la más antigua:
se escribió **antes** de que PR 1 creara `entry_max_for_rr`. Con cualquiera de
los dos órdenes uno de los códigos queda casi inalcanzable, así que no es un
defecto sino una decisión de etiquetado. **Se decide en T-009**, que es donde
se miden las dos poblaciones por separado, y **T-010 la verá** al comprobar los
27 criterios del plan: esa línea es hoy la única de las 27 que no se cumple.

---

## 3. Las siete invariantes, comprobadas una a una

La evidencia de Codex (`invariantes_defectos.md`) dice que la comprobación se
hizo «revisando que la aserción toca el campo que cambiaría» y rompiendo el
contrato «durante el desarrollo», sin salida guardada. Eso no es una
comprobación. Repetida aquí inyectando defectos de verdad y ejecutando:

| # | Invariante | Defecto inyectado | ¿Falla? |
|---|---|---|---|
| 1 | OPERAR implica las cuatro capas | quitar la guarda de ejecución en `classify` | **NO** → reescrita (§1) |
| 2 | `entry_max` nunca incumple el RR mínimo | `entry_max = entry_max_tecnica` en vez del mínimo | Sí |
| 3 | El benchmark no da el calendario | `calendar=calendar_mic("XETRA")` con la plaza NYSE | Sí |
| 4 | Un festivo no es sesión ausente | `pd.bdate_range` en vez de `sessions_in_range` | Sí |
| 5 | Sesión extranjera no exige vela local | el mismo defecto de días hábiles | Sí |
| 6 | El informe no dice «Precio actual» con la plaza cerrada | volver a la etiqueta anterior en el formateador | Sí |
| 7 | Cambiar `entry` recalcula toda la cadena | `rr = levels.rr_ratio` en vez de recalcular al precio | Sí |

Seis de las siete tienen dientes. El defecto de días hábiles (4 y 5) es el
defecto histórico real, el que T-003 corrigió, no uno inventado para la
ocasión.

Nota de nomenclatura: la invariante 6 vive con el nombre que le puso T-007,
`test_informe_no_llama_precio_actual_al_cierre_anterior`, no con el que
proponía la ficha de T-008. Es correcto: el test ya existía.

---

## 4. Lo que la entrega hace bien, y conviene decirlo

- **El formateador no calcula.** Revisado el diff entero de
  `advisor/report/formatter.py` (+190 líneas): la única aritmética son
  comparaciones `math.isclose` para decidir cuál de las dos máximas manda. Lee
  `levels.entry_max_rr` y `levels.entry_max_tecnica`, no los recalcula. Era el
  criterio de rechazo principal de la ficha y está respetado.
- **INV-17 no aplica, y es verdad.** Solo `entry_max` se persiste
  (`advisor/storage/db.py:52`); `entry_max_tecnica`, `entry_max_rr` y
  `min_rr_ratio` son campos nuevos de `Levels` con valor por defecto que no
  llegan a la base. No hace falta migración.
- **Cero cambios de acción**, con los conteos idénticos activo a activo.
- **El número que faltaba desde D-06**: el RR manda en **102** de los 107 y la
  técnica en 5. `entry_max_atr: 0.75` interviene en menos del 5 % del universo.
  Eso es lo que da sentido a la «holgura de entrada» que P4 tiene que estudiar.
- **`otros: 0`** en los siete grupos de descarte, sobre la pasada real: el
  mapeo de códigos está completo.

---

## Verificación final tras las correcciones

    python -m pytest -q     533 pasan
    ruff check .            limpio
    mypy advisor            limpio, 61 ficheros

Y contra datos reales, comparando la pasada del revisor con la de la entrega:
la reversión del orden de las ramas **no mueve el informe**, porque ningún
activo cae hoy en el grupo RR/ejecución (0 de 107).
