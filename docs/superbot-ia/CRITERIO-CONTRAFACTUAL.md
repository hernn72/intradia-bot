# Superbot IA — criterio del contrafactual, escrito antes de leerlo (D-83)

**SUPERBOT IA — PAPER, NO VALIDADA PARA CAPITAL REAL.**
_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

Escrito el 2026-11-24 y **ratificado por el propietario ese mismo día (D-84)**, con los resultados
sellados y sin ningún caso posterior al corte. No se cambia hasta la evaluación.

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
desplegar (hecho). La estrategia queda congelada en la ventana: scores, umbrales, stops, precio máximo de
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

## 4. Métrica primaria: ¿elige bien?

**Episodio** (unidad de análisis): la primera decisión **ejecutable** de un valor, sea cual sea su
resolución; su grupo es esa resolución y no cambia por lo que se decida después. Las decisiones
posteriores del mismo valor hasta 20 sesiones de su plaza después de esa entrada se ignoran; el
siguiente episodio empieza después. Una no ejecutable en la apertura no abre episodio: se cuenta.

**Exceso neto** = retorno del valor menos retorno de `EUNL.DE` en el mismo tramo, en EUR:
- Valor: precio por el cambio de cierre diario de yfinance (`fx_en_sesion`, el de la cartera) de la
  sesión de entrada y de la de salida; si falta, el último de los 5 días naturales anteriores. Unidades:
  la regla de tamaño (0,5 % de riesgo, máximo 10 %) con 5.000 € fijos. Se **restan** 0,10 % del importe
  por lado y 1 € por orden, en EUR, entre el nocional de entrada.
- `EUNL.DE`: de la primera apertura de Xetra en la sesión de entrada o después, al último cierre de
  Xetra en la de salida o antes; 0,10 % por lado. Si no queda ningún tramo, 0.
- Precios sin dividendos en ambos grupos: perjudica algo a los valores frente al fondo, igual en los dos.

**Estimador:** media de los aprobados menos media de los descartados. A los aprobados se les resta el
coste de API: euros de todas las llamadas de compra de la ventana, válidas o no, entre la suma de los
nocionales de los aprobados.

**Incertidumbre:** intervalo percentil del 95 % por remuestreo con reemplazo de bloques (10.000 réplicas,
semilla 20261124). Bloques consecutivos de 4 semanas ISO desde el lunes de la semana del corte, según
la sesión de entrada; el último puede quedar incompleto y los vacíos no cuentan. Se remuestrean los
mismos bloques para los dos grupos. Una réplica sin algún grupo se descarta; si son más del 5 %, el
resultado es `INCONCLUSO`.

## 4 bis. Contraste económico: carteras con las mismas restricciones

Dos carteras simuladas de 5.000 € desde el corte hasta la evaluación, con las mismas candidatas, gate,
stop, salida, tamaños y costes: una compra todo (**sin IA**), la otra solo lo aprobado (**con IA**,
restando además el gasto de API de compra). Las candidatas de la misma sesión se atienden por apertura y
luego por score descendente y símbolo; si no cabe en el efectivo, no se compra, y no se repite un valor ya
en cartera. Cada día se resta al resultado lo que habría rendido `EUNL.DE` con **la misma exposición
del cierre anterior**, así que el efectivo no suma ni resta. Se publica el exceso acumulado de las dos.

Es una sola trayectoria, sin inferencia: **se publica siempre junto al resultado y no decide**. Si
contradice a la métrica principal, se dice.

## 5. Cuándo se evalúa: una sola vez

Un episodio **maduro** lleva 20 sesiones de su plaza desde la entrada, haya saltado o no el stop: así la
muestra no se llena de stops recientes ni depende de resultados. Se evalúa:
- con **50 episodios maduros en cada grupo**, o
- el **2027-05-31**, lo que ocurra antes.

Con menos de 30 maduros en algún grupo en esa fecha: `INCONCLUSO`. El aviso lo da
`superbot/ia/madurez.py`, que solo cuenta: no lee precios, retornos ni si saltó un stop.

`SIN_BARRA_DE_ENTRADA`, `SPLIT_POSTERIOR` y `DATOS_INCOMPLETOS` se excluyen y se cuentan por grupo. Si
superan el 5 % de un grupo, los datos no valen para concluir y el resultado es `INCONCLUSO`.

## 6. Qué se concluye

Demostrar que la IA no aporta y no tener pruebas de que aporte son cosas distintas. Decide solo el
intervalo del 95 % del efecto neto de la selección (§4):

| Resultado | Condición | Qué se hace |
|---|---|---|
| `LA IA APORTA` | Todo el intervalo por encima de cero | Se conservan los asesores y sigue la validación |
| `LA IA NO APORTA` | Todo el intervalo en cero o por debajo | Se desactivan los asesores de compra (§6 bis) |
| `INCONCLUSO` | El intervalo incluye valores positivos y negativos, menos de 30 maduros en algún grupo, o datos no válidos (§4 y §5) | No se desactivan los asesores por este resultado |

Junto al resultado se publican el exceso neto medio de cada grupo y el contraste de §4 bis. `LA IA APORTA`
no basta para capital real: la fase 4 del plan sigue exigiendo batir a `EUNL.DE`. Tras la evaluación no
se amplía la muestra ni se repite sin una decisión nueva escrita antes de mirar más.

Con 50 por grupo y una dispersión del orden del 7 % por episodio (supuesto, no medido), el error
típico ronda 1,4 puntos: solo se detectan con fiabilidad diferencias de unos 4. El propietario acepta
expresamente que el resultado pueda ser `INCONCLUSO`. No se sabe si se alcanzarán 50 por grupo.

## 6 bis. Qué significa desactivar los asesores de compra

- Dejan de influir en las compras nuevas; pueden seguir ejecutándose en modo observación.
- Se conservan todos los registros para comparar después.
- Siguen la gestión de posiciones, los stops y los controles de riesgo.
- No se apaga el sistema ni se tocan los asesores de venta, que exigen su propia evaluación.
- Es un cambio controlado y reversible, documentado, que abre una fase de evaluación nueva sin alterar los
  resultados de esta.

## 7. Secundario (no decide)

- Ventas de la IA: venta real frente a mantener hasta stop o sesión 20 (descriptivo; no evalúa a esos asesores).
- Retorno en R, proporción en positivo, stops y no ejecutables por grupo.

## 8. Registro

| Fecha | Qué |
|---|---|
| 2026-11-24 | Criterio escrito con los resultados sellados |
| 2026-11-24 | **Corte:** la Pi ejecuta `2e26f65` desde las 09:55:03 UTC; entran las decisiones fechadas desde entonces |
| 2026-11-24 | Criterio ratificado por el propietario (D-84): solo decide el intervalo, las carteras son contraste y `LA IA NO APORTA` se separa de `INCONCLUSO`. Programa de madurez escrito |
