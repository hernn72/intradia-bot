# Superbot IA — simulaciones de reglas de entrada y salida: pre-registro (D-84 §5)

**SUPERBOT IA — PAPER, NO VALIDADA PARA CAPITAL REAL.**
_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

Escrito el 2026-11-24, **antes de ejecutar ninguna simulación**. Estado: PREPARADO, pendiente de que el
propietario autorice la ejecución. Código: `superbot_lab/`, que producción no importa.

## 1. Qué se pregunta y qué no

¿Alguna regla alternativa de entrada, umbral o salida mejora a la actual en 5 y 2 años, descontando
costes y exposición? Es **desarrollo**: compara reglas sobre datos ya consumidos. No valida ninguna, no
demuestra ventaja del Score (D-70: sin ventaja demostrada) y **no cambia la estrategia activa, congelada
hasta la evaluación del contrafactual**. La IA no se simula: el modelo recuerda el pasado.

## 2. Datos

- Cosecha propia `4506dc5df60bb1f6cbdaf6755e1b60c65c1ed25a1598e8f53f6afdf0e984869c` (yfinance diario, 102 símbolos,
  2020-06-01 a 2026-08-27). Antes del 2021-08-30 solo calienta indicadores.
- El final es el de los datos que los gates declaran consumidos (D-73). **No se usan** los
  resultados sellados del contrafactual, la base de Superbot IA, `paper.db` ni las cosechas de T-024.
- Ventanas: **5 años** (2021-08-30 a 2026-08-27) y **2 años** (2024-08-28 a 2026-08-27). La segunda está
  dentro de la primera: es una comprobación de estabilidad, no una muestra independiente.
- 90 valores: los que el bot puede comprar hoy. Precios sin ajustar por dividendos, que se ignoran.
- Cobertura comprobada sin abrir resultados: 120.732 fichas; 7.344 sesiones sin contexto calculable.

## 3. Motor

Score v1, contexto point-in-time, niveles, gate de apertura, stop, tamaño (0,5 % de riesgo, máximo 10 %) y
predicados de venta reales. 5.000 €; 1 € por orden y 0,10 % por lado; cambio al cierre del día. Se compra
toda candidata elegible (score ≥ umbral, cinco por plaza) que quepa. Se vende cuando un predicado es
cierto: es el máximo que la IA podría vender, y **en el bot real vendería menos**.

Aproximaciones: barras diarias; si un día toca stop y objetivo, cuenta el stop; una orden limitada se
ejecuta si el mínimo llega al precio; el efectivo se reparte por hora de apertura de la plaza y símbolo,
con un orden de aperturas fijo, sin cambio de hora; «cinco por plaza» es por sesión (en el bot, por pasada, puede haber
más); no se aplican el máximo de una venta por pasada, el veto por calidad del dato ni la tolerancia
parcial de Asia en el contexto; el tamaño usa el valor a mercado del cierre anterior. La espera de recompra
de 5 sesiones cuenta desde cualquier cierre, como en el bot.

## 4. Variantes: una cosa cada vez

| Regla | Cambio respecto a la actual |
|---|---|
| `BASE` | Ninguno: precio máximo = cierre, compra ≥ 60, venta < 60, stop fijo |
| `E1_MARGEN_025` | Precio máximo = máximo actual + 0,25 ATR |
| `E2_MARGEN_050` | Precio máximo = máximo actual + 0,50 ATR |
| `E3_LIMITE_DIA` | Orden limitada al precio máximo actual, viva durante la sesión objetivo |
| `H1_60_55` | Vende por debajo de 55 |
| `H2_65_60` | Compra desde 65 |
| `H3_65_55` | Compra desde 65 y vende por debajo de 55 |
| `X1_OBJETIVO` | Vende al tocar `target2` (no el día de entrada) |
| `X2_STOP_MOVIL` | El stop sube a máximo cierre − 2 ATR; nunca baja |
| `X3_20_SESIONES` | Vende tras 20 sesiones |

Todas las entradas conservan un tope de precio. El precio máximo actual coincide casi siempre con
el cierre porque stop = 2 ATR, objetivo = 3 ATR y ratio mínimo = 1,5 (3/2 = 1,5): subirlo obliga a aceptar
un ratio menor (1,22 con `E1`, 1,00 con `E2`). En 564 de 24.574 fichas con score de 60 o más (2,3 %) un
soporte cercano acerca el stop, y el máximo queda por encima del cierre. No se combinan variantes en esta ronda.

## 5. Métrica y decisión

**Métrica:** exceso diario = cambio de valor de la cartera menos lo que habría rendido `EUNL.DE` con la
exposición del cierre anterior. El efectivo no suma ni resta. Se compara cada variante con `BASE` en
los mismos días.

**Incertidumbre:** bloques móviles circulares de 20 sesiones, 10.000 réplicas, semilla 20261124, con
corrección por 9 comparaciones (intervalo del 99,44 %).

| Resultado | Condición |
|---|---|
| `MERECE VALIDACIÓN` | En 5 años el intervalo está entero por encima de cero, en 2 años la diferencia es positiva y la caída máxima de 5 años no empeora más de 2 puntos |
| `DESCARTADA` | En 5 años el intervalo está entero en cero o por debajo |
| `SIN EVIDENCIA` | Cualquier otro caso: se queda la regla actual |

Se publican todas las variantes, con operaciones, rechazos, costes, exposición y caída. Si `BASE` y una
variante pierden contra `EUNL.DE`, se dice: perder menos no es tener ventaja. `MERECE VALIDACIÓN` solo
permite proponer una prueba hacia delante, tras la evaluación del contrafactual y con decisión propia.

## 6. Ejecución

Una vez. `python -m superbot_lab correr` exige el sha256 de este fichero y un árbol de git limpio, usa solo
la cosecha de §2, guarda el SHA del código y escribe en `evidence/superbot-ia/simulaciones-reglas/`, donde
se niega a sobrescribir. Si un fallo obliga a repetir, se corrige, se declara aquí y se repite entera.
