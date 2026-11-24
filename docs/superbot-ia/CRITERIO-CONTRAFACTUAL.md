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
entran en el contraste. Los episodios se forman solo con decisiones posteriores al corte.

**Corte:** entran solo las decisiones de las pasadas ejecutadas con un código que ya contenga el
contrafactual y el arreglo del validador (`ia_pasada.code_sha`). El primer SHA válido se anota en §8 al
desplegar. La estrategia queda congelada en la ventana: scores, umbrales, stops, precio máximo de
entrada, tamaños, prompts y modelo. Un cambio en cualquiera de ellos cierra la muestra y abre otra.

## 3. Qué se compara

Las candidatas que llegaron al comité son las mismas oportunidades para todos. El sistema **sin IA** las
compra todas; el sistema **con IA** solo las que resuelve `COMPRAR`. La IA aporta si lo que aprueba
rinde más que lo que descarta, con las mismas reglas para ambos grupos:

| Regla | Aprobadas y descartadas |
|---|---|
| Entrada | Apertura de la sesión objetivo, con el mismo gate |
| Stop | El congelado al decidir |
| Salida | Stop o cierre de la sesión 20 |

Comparar grupos, y no «invertir o no invertir», evita premiar a la IA por quedarse en efectivo. Las
ventas de la IA se dejan fuera para aislar el filtro de entrada; se miden aparte.

Limitaciones: un valor ya en cartera, pendiente o en espera de recompra no llega al comité; una
candidata sin dictamen válido no tiene decisión. El resultado real de las compras ejecutadas sigue
visible en la cartera, así que el grupo aprobado no es del todo ciego.

## 4. Métrica primaria

**Episodio** (unidad de análisis): la primera decisión **ejecutable** de un valor, sea cual sea su
resolución; su grupo es esa resolución y no cambia por lo que se decida después. Las decisiones
posteriores del mismo valor hasta 20 sesiones de su plaza después de esa entrada se ignoran; el
siguiente episodio empieza después. Una no ejecutable en la apertura no abre episodio: se cuenta.

**Exceso neto** = retorno del valor menos retorno de `EUNL.DE` en el mismo tramo, en EUR:
- Valor: cambio de la sesión de entrada y de la de salida (si falta, el último de los 5 días
  anteriores). Se **restan** 0,10 % por lado y 1 € por orden, sobre el nocional que la regla de tamaño
  daría con 5.000 €.
- `EUNL.DE`: de la primera apertura de Xetra en la sesión de entrada o después, al último cierre de
  Xetra en la de salida o antes; 0,10 % por lado. Si no queda ningún tramo, 0.
- Precios sin dividendos en ambos grupos: perjudica algo a los valores frente al fondo, igual en los dos.

**Estimador:** media de los aprobados menos media de los descartados. A los aprobados se les resta el
coste de API: euros de todas las llamadas de compra de la ventana, válidas o no, entre la suma de los
nocionales de los aprobados.

**Incertidumbre:** intervalo del 95 % por remuestreo de bloques de 4 semanas naturales de la sesión de
entrada (10.000 réplicas, semilla 20261124).

## 5. Cuándo se lee: una sola vez

Un episodio **maduro** lleva 20 sesiones de su plaza desde la entrada, haya saltado o no el stop: así la
muestra no se llena de stops recientes ni depende de resultados. Se lee:
- con **50 episodios maduros en cada grupo**, o
- el **2027-05-31**, lo que ocurra antes.

Con menos de 30 maduros en algún grupo en esa fecha: `INCONCLUSO`. El aviso de que toca leer lo da un
programa que solo cuenta maduros por grupo, sin retornos (pendiente de escribir, antes de ratificar).

`SIN_BARRA_DE_ENTRADA`, `SPLIT_POSTERIOR` y `DATOS_INCOMPLETOS` se excluyen y se cuentan por grupo. Si
superan el 5 % de un grupo, el resultado es `INCONCLUSO`.

## 6. Qué se concluye

| Resultado | Condición |
|---|---|
| `LA IA APORTA` | Límite inferior del intervalo > 0, **y** exceso neto medio de los aprobados > 0 |
| `LA IA NO APORTA` | Límite superior del intervalo < 0 |
| `INCONCLUSO` | Cualquier otro caso |

`LA IA APORTA` no basta para capital real: la fase 4 del plan sigue exigiendo batir a `EUNL.DE`.
Con `LA IA NO APORTA` se propone apagar los asesores de compra. Con `INCONCLUSO` no se amplía la
muestra sin una decisión nueva escrita antes de mirar más.

Con 50 por grupo y una dispersión del orden del 7 % por episodio (supuesto, no medido), el error
típico ronda 1,4 puntos: solo se detectan con fiabilidad diferencias de unos 4. Una ventaja pequeña
saldrá casi siempre `INCONCLUSO`. No se sabe si se alcanzarán 50 por grupo en el plazo.

## 7. Secundario (no decide)

- Cartera simulada con IA contra sin IA, con 5.000 €, el mismo límite de efectivo y tamaños, frente a `EUNL.DE`
  con la misma exposición diaria que cada una.
- Ventas de la IA: venta real frente a mantener hasta stop o sesión 20.
- Retorno en R, proporción en positivo, stops y no ejecutables por grupo.

## 8. Registro

| Fecha | Qué |
|---|---|
| 2026-11-24 | Criterio escrito con los resultados sellados. Números de §5 y §6 pendientes de ratificar |
