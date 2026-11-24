# Superbot IA — simulaciones de reglas: resultado (D-86)

**SUPERBOT IA — PAPER, NO VALIDADA PARA CAPITAL REAL.**
_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

Ejecutadas **una sola vez** el 2026-11-24 (14:47 UTC) con el pre-registro `SIMULACIONES-REGLAS.md` sin cambios
y la autorización D-85 ya comiteada. Datos: `resultado.json`, `tablas.md` y `manifiesto.json` en
`evidence/superbot-ia/simulaciones-reglas/`.

## 1. Veredicto, aplicando la regla fijada antes

| Regla | 5 años: diferencia e intervalo 99,44 % (EUR) | 2 años: diferencia (EUR) | Caída máx. 5 a (BASE −100,0 %) | Veredicto |
|---|---|---|---|---|
| `E1_MARGEN_025` | +75 [−724, +928] | +36 | −100,0 % | SIN EVIDENCIA |
| `E2_MARGEN_050` | +182 [−895, +1.294] | −93 | −100,0 % | SIN EVIDENCIA |
| `E3_LIMITE_DIA` | +234 [−797, +1.337] | +74 | −100,0 % | SIN EVIDENCIA |
| `H1_60_55` | +2.629 [+95, +4.997] | +2.013 | −33,7 % | **MERECE VALIDACIÓN** |
| `H2_65_60` | +1.436 [−10, +2.905] | +1.165 | −65,5 % | SIN EVIDENCIA |
| `H3_65_55` | +3.922 [+1.132, +6.663] | +2.596 | −24,0 % | **MERECE VALIDACIÓN** |
| `X1_OBJETIVO` | +15 [−853, +867] | −509 | −100,0 % | SIN EVIDENCIA |
| `X2_STOP_MOVIL` | −51 [−642, +467] | −123 | −100,0 % | SIN EVIDENCIA |
| `X3_20_SESIONES` | +11 [−164, +158] | +54 | −100,0 % | SIN EVIDENCIA |

`MERECE VALIDACIÓN`: `H1_60_55` y `H3_65_55`. `SIN EVIDENCIA`: las otras siete. `DESCARTADA`: ninguna. **No se
implanta nada**: son candidatas a una validación independiente, con decisión propia.

## 2. Todas pierden contra `EUNL.DE`

El exceso de **todas** las reglas, también las dos candidatas, es negativo en las dos ventanas: H3, −1.328 EUR
en 5 años y −231 en 2; H1, −2.620 y −813. Perder menos no es tener ventaja. Solo H3 en 2 años acaba por
encima de los 5.000 EUR (5.212), y aun así por debajo de la referencia.

## 3. Por qué hay que leerlo con cautela

- **La regla actual simulada se arruina en 5 años** (patrimonio −1 EUR; 2.296 operaciones; 5.577 EUR de
  costes sobre 5.000 de capital). También E1, E2, E3, X1, X2 y X3. Contra una base arruinada, **E y X no
  se pueden distinguir en 5 años**: todas acaban en el mismo suelo. Su `SIN EVIDENCIA` no dice que den igual.
- **La base no es el bot real.** Vende siempre que un predicado es cierto; en el bot la IA decide y vende
  como mucho una por pasada. El pre-registro lo declaraba. Es razonable pensar que esa venta mecánica aumenta
  la rotación y favorece a las reglas que venden menos, pero **no se ha medido** cuánto. Lo medido vale solo
  para esta versión mecánica.
- **La mayor parte de la mejora es gastar menos.** Diferencia de costes sobre la diferencia total, 5 y 2
  años: H1, 77 % y 76 %; H3, 73 % y 75 %. Es aritmética descriptiva, sin intervalo.
- El euro fijo por orden pesa más cuanto menor es la posición, y la cartera que cae opera posiciones cada vez
  más pequeñas: la ruina se acelera. Con otro capital o con otra tarifa el resultado sería distinto.
- El simulador no pone suelo al patrimonio: una venta diminuta puede costar más de lo que ingresa. Mayor
  patrimonio final negativo, −1,75 EUR: explica el rebase del 100 % de caída (la tabla redondea), no la ruina.
  No se ha recalculado con suelo.
- H1 supera el umbral por poco (límite inferior +95 EUR). H2 se queda fuera por −10: no se relaja.
- Las variantes H comparten umbrales y no son pruebas independientes. La ventana de 2 años está dentro de la
  de 5. Con 9 variantes sobre los mismos datos, elegir la mejor (H3) la favorece; el 99,44 % corrige las
  nueve comparaciones, no el sesgo de selección del tamaño del efecto.

## 4. Qué se comprobó sin volver a ejecutar

Lectura del simulador buscando un fallo que explicase la ruina: no se encontró; revisión cruzada de Codex, con
la misma conclusión y los veredictos y cifras confirmados. Entradas (`comprobacion-entradas.txt`): 90 valores en EUR,
USD, JPY y HKD, sin precios no positivos ni huecos OHLC, y con saltos diarios de divisa de hasta el 3,8 %; la cosecha cargó con
sus hashes y la copia externa es idéntica. Al final de la prueba la Pi seguía en `f2d5922`, sin tocar. **No se
repitió la ejecución**, así que el determinismo se apoya en las pruebas del motor y en la semilla fija.

## 5. Qué sigue, si el propietario lo decide

La estrategia activa, los 5.000 EUR y el contrafactual siguen intactos hasta su evaluación. Una validación de
H1/H3 exige escribir antes su pre-registro, con datos no consumidos y, si cabe, con la venta de la IA tal
como opera el bot.
