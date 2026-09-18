# T-016 — El centinela `(0.0, 1.0)` deja de publicarse como intervalo

Estado: PENDIENTE
Agente: Codex (implementación) → Opus (revisión)
Línea / fase: Línea A, higiene del laboratorio
Gate al que contribuye: **GATE P2** — debe estar hecho antes de A-02 (T-013)

## Objetivo
Que ninguna salida del laboratorio publique como intervalo de confianza un
valor que significa «no se pudo calcular un intervalo».

## Por qué existe
`advisor/research/bootstrap.py:100`:

```python
if len(values) < 2:
    return 0.0, 1.0
```

Es un centinela: con menos de dos bloques no hay intervalo bootstrap posible.
El problema es que **en unidades de R, `[0.0000, 1.0000]` se lee como un
intervalo perfectamente plausible** —«la expectancy está entre 0 y 1 R»— y es
una afirmación fuerte que nadie ha calculado. Detectado en la revisión de T-009,
donde el tramo `80+` salía así:

    | 80+ | EJECUTADAS | 28 | OK | ... | 0.4391 | [0.0000, 1.0000] | ...

con la fila etiquetada `OK`. En T-009 se corrigió **el consumidor**, no la
raíz. Quedan dos frentes:

1. **La raíz.** La función devuelve un valor que el llamante no puede
   distinguir de un resultado. Debe devolver ausencia (`None`) o un tipo que
   obligue a tratar el caso.
2. **El otro consumidor, que es el grave.** `advisor/research/capacity.py:534`
   llama a la misma función. `capacidad-estadistica` es **el comando que emite
   el veredicto de P2.5**, y GATE P2 depende de él. Si alguna de sus celdas ha
   tenido menos de dos bloques, ese veredicto se apoyó en un intervalo que no
   existe.

## Dependencias previas
Ninguna. **Debe estar antes de A-02 (T-013)**, que reejecuta P2.5.

## Archivos probables
- `advisor/research/bootstrap.py` — `bootstrap_block_mean_interval` y el otro
  centinela de la línea 97 (`return 0.0, 0.0` con lista vacía), que tiene el
  mismo problema con otro disfraz.
- `advisor/research/capacity.py:534` y su formateo de salida.
- `advisor/research/execution_filter.py` — ya corregido en T-009; debe quedar
  consumiendo la nueva forma, sin duplicar la comprobación (INV-06).
- `tests/test_capacity.py:100` compara contra la función directamente: se
  actualiza.

## Invariantes que no pueden romperse
INV-16 (lo desconocido se declara desconocido: la ausencia de intervalo es
ausencia, no `[0, 1]`), INV-06 (la comprobación de «hay bloques suficientes»
vive en un solo sitio).

## Implementación requerida

1. **La función deja de inventar.** `bootstrap_block_mean_interval` devuelve
   `None` —o un tipo explícito— cuando no hay material para un intervalo, en
   los dos casos: lista vacía y menos de dos bloques. Ningún llamante puede
   seguir recibiendo un par de números indistinguible de un resultado.
2. **Todos los consumidores lo declaran.** `capacity.py` y
   `execution_filter.py` imprimen «N/D (menos de 2 bloques)» y marcan el estado
   de la celda, como ya hace `execution_filter` tras T-009.
3. **Auditar hacia atrás, que es la parte que importa.** Reejecutar
   `capacidad-estadistica` sobre la cosecha `071ddb2b…` y **contar cuántas
   celdas caían en el centinela**. Si alguna del veredicto de P2.5 lo hacía, se
   dice en el decision log y se marca ese veredicto como no concluyente hasta
   que A-02 lo rehaga. Este recuento es el entregable principal de la ficha: si
   sale cero, la deuda era teórica; si no sale cero, GATE P2 arrastra un
   resultado inválido.
4. **No cambiar ningún cálculo.** Las celdas con dos o más bloques deben dar
   exactamente el mismo intervalo que hoy, comprobado cifra a cifra.

## Qué NO debe modificarse
El método bootstrap, la longitud de bloque, `_MIN_SAMPLE`, ni ningún umbral del
protocolo de investigación.

## Tests unitarios
- `test_intervalo_sin_bloques_suficientes_es_ausencia_y_no_cero_uno`: con un
  bloque, la función no devuelve `(0.0, 1.0)`.
- `test_intervalo_con_lista_vacia_es_ausencia` (el centinela de la línea 97).
- `test_capacidad_declara_las_celdas_sin_intervalo`.
- `test_las_celdas_con_dos_o_mas_bloques_dan_el_mismo_intervalo_que_antes`, con
  números cerrados tomados de la salida actual.

## Verificación contra datos reales
```bash
.venv/bin/python -m advisor.main capacidad-estadistica --vintage 071ddb2b
.venv/bin/python -m advisor.main filtro-ejecucion --horizonte swing --vintage 071ddb2b
```
Comprobar a mano: que ninguna salida contiene `[0.0000, 1.0000]`, y que una
celda concreta con bloques suficientes conserva su intervalo dígito a dígito.

## Medición del impacto
- Número de celdas afectadas en `capacidad-estadistica`, por tramo.
- Si el veredicto de P2.5 cambia al declararlas, decirlo en el decision log.

## Criterio de aceptación
- Ninguna salida publica el centinela.
- El recuento retrospectivo está hecho y publicado.
- Las celdas con bloques suficientes no cambian.

## Criterio de rechazo
- Sustituir el centinela por otro valor plausible (por ejemplo `[nan, nan]`
  impreso como números).
- Cambiar cualquier intervalo calculable.
- Dar por bueno el veredicto de P2.5 sin haber contado las celdas afectadas.

## Evidencia que debe quedar registrada
`evidence/<fecha>-T-016-centinela-intervalo/` con README.md, la salida de
`capacidad-estadistica` antes y después, el recuento de celdas afectadas y la
comprobación dígito a dígito de una celda no afectada.

## Commit esperado
Rama `fix/interval-sentinel`. Mensaje:
`fix(research): la ausencia de intervalo se declara, en vez de publicarse como [0, 1]`

## Actualización documental requerida
`docs/roadmap.md`: fila nueva en la línea A, marcada como previa a A-02.
`docs/decision-log.md`: D-nn con el recuento retrospectivo y, si procede, la
declaración de que el veredicto de P2.5 no era concluyente.

## Handoff al siguiente agente
Pendiente de escribir al terminar.
