# Superbot IA — criterio del contrafactual, escrito antes de leerlo (D-83)

**SUPERBOT IA — PAPER, NO VALIDADA PARA CAPITAL REAL.**
_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

Escrito el 2026-11-24. **Estado de los números de §5 y §6: PROPUESTOS, pendientes de que el
propietario los ratifique. Hasta entonces, y después hasta la lectura de §5, los resultados están
sellados.**

## 1. Pregunta

Con las mismas oportunidades y las mismas restricciones, ¿el filtro de compra de los asesores IA
mejora al mismo sistema sin IA, una vez descontados los costes y el movimiento del mercado?

No mide si el Score tiene ventaja, ni si conviene otra entrada, otro umbral u otro stop.

## 2. Lo que ya se ha visto (no se puede deshacer)

- El 2026-11-12 se leyeron resultados parciales de las decisiones registradas hasta ese día (−0,61 %
  las aprobadas y +0,96 % las descartadas, con 1 o 2 sesiones de vida).
- El 2026-11-24 se revisó el resultado real de las cinco posiciones cerradas y de la abierta.

Por eso **las decisiones anteriores al corte son muestra exploratoria**: se conservan íntegras y no
entran en el contraste.

**Corte:** entran solo las decisiones de las pasadas ejecutadas con un código que ya contenga el
contrafactual y el arreglo del validador (`ia_pasada.code_sha`). El primer SHA válido se anota en §8 al
desplegar. La estrategia queda congelada en la ventana: scores, umbrales, stops, precio máximo de
entrada, tamaños, prompts y modelo. Un cambio en cualquiera de ellos cierra la muestra y abre otra.

## 3. Los dos brazos

| | A: con IA | B: sin IA |
|---|---|---|
| Candidatas | Las que el comité resolvió `COMPRAR` | Todas las que llegaron al comité (`COMPRAR` y `DESCARTAR`) |
| Entrada | Apertura de la sesión objetivo, con el mismo gate | Igual |
| Stop | El congelado al decidir | Igual |
| Salida | Stop o cierre de la sesión 20 | Igual |

Las ventas de la IA se dejan fuera **en los dos brazos** para aislar el filtro de entrada; se miden
aparte, como análisis secundario. Las no ejecutables en la apertura se cuentan y no puntúan.

Limitaciones conocidas: un valor que ya está en cartera, pendiente o en espera de recompra no llega al
comité, así que tampoco está en B; y una candidata sin dictamen válido de la IA no tiene decisión.

## 4. Métrica primaria

Por operación: **exceso neto** = retorno de la operación menos el retorno de `EUNL.DE` en las mismas
sesiones (de la apertura de entrada al cierre de salida; si salta el stop, hasta el cierre de esa
sesión), ambos en EUR y con 0,10 % de deslizamiento por lado. Al activo se le suma 1 € por orden sobre
el nocional que le habría dado la regla de tamaño con 5.000 €. Como cada euro invertido se compara con
el mismo euro en el índice los mismos días, **tener efectivo no da ni quita puntos**.

Unidad de análisis: el **episodio**. Decisiones del mismo valor cuya sesión objetivo cae a menos de 20
sesiones de la primera del episodio, cuentan una sola vez: en A, la primera aprobada ejecutable; en el
grupo descartado, la primera ejecutable de un episodio sin ninguna aprobada.

**Estimador:** media del exceso neto de los episodios aprobados menos media de los descartados. El
coste real de API de las llamadas de compra se reparte entre los episodios aprobados y se resta.

**Incertidumbre:** intervalo del 95 % por remuestreo de bloques de semanas naturales de la sesión
objetivo (10.000 réplicas, semilla 20261124).

## 5. Cuándo se lee: una sola vez

- Al llegar a **50 episodios cerrados en cada grupo**, o
- el **2027-05-31**, lo que ocurra antes.

Si en esa fecha algún grupo tiene menos de 30 episodios cerrados, el resultado es `INCONCLUSO`.
El recuento de episodios cerrados lo hace un programa que solo devuelve sí/no; nadie mira retornos.

## 6. Qué se concluye

| Resultado | Condición |
|---|---|
| `LA IA APORTA` | Límite inferior del intervalo > 0, **y** exceso neto medio de los aprobados > 0 |
| `LA IA NO APORTA` | Límite superior del intervalo < 0, o estimador ≤ 0 con 50 episodios o más por grupo |
| `INCONCLUSO` | Cualquier otro caso |

`LA IA APORTA` no basta para capital real: la fase 4 del plan sigue exigiendo batir a `EUNL.DE`.
Con `LA IA NO APORTA` se apagan los asesores de compra y se conserva el sistema sin IA.
Con `INCONCLUSO` no se amplía la muestra sin una decisión nueva escrita antes de mirar más.

Con 50 por grupo y una dispersión del orden del 7 % por operación (supuesto, no medido), solo se
detectan con fiabilidad diferencias de unos 4 puntos: una ventaja pequeña saldrá `INCONCLUSO`.

## 7. Secundario (no decide)

- Cartera simulada A contra B con 5.000 €, el mismo límite de efectivo y tamaños, frente a `EUNL.DE`
  con la misma exposición diaria que cada una.
- Ventas de la IA: venta real frente a mantener hasta stop o sesión 20.
- Retorno en R, proporción en positivo, stops y no ejecutables por grupo.

## 8. Registro

| Fecha | Qué |
|---|---|
| 2026-11-24 | Criterio escrito con los resultados sellados. Números de §5 y §6 pendientes de ratificar |
