# despues.md — el laboratorio rehecho (A-02, 2026-09-21)

Cosecha `071ddb2b…253841`. Coste 0,20 %. Bloque 60 sesiones en swing, 300 en
medio, como fija el protocolo. Bootstrap con semilla 20260830 y 2.000
remuestreos.

## 1. Las tres poblaciones y sus hashes

| Poblacion | activos | `universe_vintage_id` | señales swing | señales medio |
|---|---|---|---|---|
| `vigente` | 93 | `237b0056…565d19` | 106.363 | 94.273 |
| `d31` | 103 | `c8496446…f952132` | 117.275 | 103.885 |
| `pre-d31` | 107 | `894ce776…8e0b5fb0` | **121.786** | 107.876 |

Los tres hashes son los publicados en el decision log y se reproducen exactos.

## 2. El control principal de la ficha: PASA EXACTO

La ficha exigia que `pre-d31` sobre swing devolviera **121.786 señales**, la
cifra de agosto, y si no, cuantificar la diferencia activo por activo.
Devuelve **121.786 exactas**.

Eso permite separar las causas, que era el objetivo:

| Banda | agosto (107) | hoy `pre-d31` (107) | Δ |
|---|---|---|---|
| <50 | 51.268 | 51.172 | −96 |
| 50-60 | 44.848 | 44.929 | +81 |
| 60-70 | 23.027 | 23.030 | +3 |
| 70-80 | 2.565 | 2.578 | +13 |
| 80+ | 78 | 77 | −1 |
| **total** | **121.786** | **121.786** | **0** |

**Atribucion medida.** Sobre la misma poblacion, el numero de señales no cambia
y solo **194 de 121.786 (0,16 %)** se mueven de banda. Esa es la huella completa
de la correccion de fortaleza relativa del 2026-09-02, coherente con que solo 8
de los 107 activos cruzan continente. La geometria de la linea 0 no mueve nada.
Por tanto **toda la diferencia entre lo publicado en agosto y las cifras
vigentes es de poblacion**, no de metodo.

## 3. P2.3 con el estimador primario de INV-14 al frente

Poblacion vigente, swing. El primario es la media por bloque de la expectancy
neta en R; la tasa agrupada y `P(objetivo antes de stop)` quedan como
secundarias y nunca se publican solas.

Global: **+0.064 R**, IC95 **[-0.060, 0.171]**, 21 bloques de 60 sesiones.

| Banda | n | bloques | primario (R) | IC95 |
|---|---|---|---|---|
| <50 | 45.561 | 21 | +0.150 | [0.016, 0.263] |
| 50-60 | 38.824 | 21 | −0.026 | [−0.188, 0.114] |
| 60-70 | 19.695 | 20 | +0.006 | [−0.138, 0.153] |
| 70-80 | 2.193 | 20 | −0.015 | [−0.223, 0.193] |
| 80+ | 65 | 15 | +0.233 | [−0.080, 0.588] |

Por region (swing, vigente):

| Region | n | bloques | primario (R) | IC95 |
|---|---|---|---|---|
| ASIA | 17.951 | 20 | +0.089 | [−0.042, 0.214] |
| EMERGING_MARKETS | 1.151 | 20 | +0.098 | [−0.154, 0.340] |
| EUROPA | 34.600 | 20 | +0.070 | [−0.040, 0.190] |
| GLOBAL | 7.739 | 21 | +0.061 | [−0.100, 0.220] |
| USA | 44.897 | 20 | +0.134 | [0.004, 0.257] |

El desglose por activo esta completo en
`capacidad-estadistica-vigente-swing.txt`.

Nota de denominador: la n del primario es menor que la n de la banda porque las
señales `AMBIGUOUS` no tienen `net_r_multiple` y quedan fuera del numerador.
La diferencia es exactamente el recuento de ambiguas (13 en `<50`, 4 en `50-60`,
7 en `60-70`, 1 en `70-80`, 0 en `80+`).

## 4. Lo que el primario dice, y lo que no

**El intervalo del primario cruza el cero en todas las bandas menos `<50`.** La
banda `<50` es la unica cuyo IC95 excluye el cero, y es la banda **mas baja** del
score: no es un resultado que sostenga que el score ordena, mas bien lo
contrario, pero con esta anchura de intervalo tampoco sostiene que ordene al
reves.

**El veredicto global cambia respecto a la linea base.** Con el estimador
secundario (tasa TARGET_FIRST) la capacidad global salia `LIMITADA` con
resolucion `MEDIUM`. Con el primario que INV-14 declara, sale **`INSUFICIENTE`
con resolucion `LOW`**, porque el intervalo mide 0.231 R de ancho frente al
umbral de 0.200. **El disenno tiene menos resolucion de la que aparentaba**, y
aparentaba mas solo porque se estaba mirando la metrica secundaria.

**Ninguna banda es concluyente.** Las cinco salen NO CONCLUYENTE, cada una con
su motivo publicado: intervalo demasiado ancho en las tres bajas, bloque minimo
de 2 observaciones en `70-80`, y en `80+` las tres cosas a la vez (bloque minimo
1, n=65 < 100, intervalo 0.668).

**Medio es peor de lo que el protocolo preveia.** El protocolo escribio «del
orden de ocho bloques en diez anos»; la medicion da **5 bloques** de 300
sesiones. La limitacion es estadistica y ninguna cantidad de señales la arregla.

Esto es el resultado. No se ha ampliado la ventana, ni cambiado el estimador, ni
movido la longitud de bloque, ni quitado activos.

## 5. P2.4 — la ablacion del RR sobre la poblacion nueva

Sobre el mismo `EventStudyResult`, sin pasar por `classify()`: 106.363 señales
entran enteras, **0 descartes**.

| Banda | n | mediana RR puntos | p10 | p90 | mediana contrib. | mediana RR bruto | mediana RR neto |
|---|---|---|---|---|---|---|---|
| <50 | 45.574 | 10.000 | 10.000 | 15.000 | +2.500 | 1.500 | 1.472 |
| 50-60 | 38.828 | 10.000 | 10.000 | 10.000 | −1.583 | 1.500 | 1.461 |
| 60-70 | 19.702 | 10.000 | 10.000 | 10.000 | −4.167 | 1.500 | 1.454 |
| 70-80 | 2.194 | 10.000 | 10.000 | 10.000 | −7.292 | 1.500 | 1.458 |
| 80+ | 65 | 10.000 | 10.000 | 10.000 | −10.333 | 1.500 | 1.463 |

**El hallazgo de agosto se reproduce entero sobre la poblacion nueva.** La
dimension que pesa 20 puntos de 100 reparte 10 a casi todo el mundo, el RR bruto
vale 1.500 en la mediana de las cinco bandas, y la contribucion va de +2.500 en
la banda baja a −10.333 en la alta: aritmetica de normalizacion, no informacion
sobre el activo.

Migracion al quitarlo (tabla C completa en el fichero): `70-80` pasa de 2.194 a
6.443 señales y `80+` de 65 a 1.032, casi dieciseis veces mas.

**Aviso que hay que leer entero:** la tabla sin RR usa **los mismos cortes** de
banda sobre una nota normalizada sobre 60 puntos, asi que las bandas **no son
comparables una a una**. Recalibrar los umbrales es P3 y aqui no se ha hecho.

**P2.4 mide y no decide.** La decision sobre el RR queda abierta como **OD-11**
para el propietario.

## 6. Censura

`EXIT_FINAL` se publica por corte. En swing vigente: 1,3 % global, entre 0,00 %
(`80+`) y 1,65 % (`60-70`). No hay ningun corte con censura alta.
