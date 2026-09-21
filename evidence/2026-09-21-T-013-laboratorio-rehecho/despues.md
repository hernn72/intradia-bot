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

**Lo que esta tabla permite afirmar, y lo que NO.**

Permite afirmar que sobre la **misma poblacion** el numero total de señales es
identico —121.786 en las dos— y que las diferencias **netas** por banda suman
194 señales.

**No permite afirmar cuantas señales cambian de banda.** Una diferencia neta no
es un recuento de migraciones: si N señales entran en una banda y N salen, el
neto es 0 y el movimiento real es 2N. Con estos agregados:

    minimo compatible          Σ|Δ| / 2 = 97 señales
    maximo acotado          10.228 señales

El maximo sale de que la correccion de fortaleza relativa del 2026-09-02 solo
puede alterar la nota de los **diez** pares que cruzan continente
(`docs/pendientes.md` §16), y esos diez aportan 10.228 de las 121.786 señales de
`pre-d31` (medido sobre la tabla «Primario por activo» de
`event-study-pre-d31-swing.txt`).

**La atribucion exacta entre poblacion y correccion de RS no es observable con
los artefactos disponibles**, porque de agosto solo se conservan los agregados
por banda (`docs/pendientes.md` §11) y no la salida por señal. La ficha
contempla este caso expresamente: si no se puede separar, se dice que no se
puede separar. **Se declara que no se puede separar.**

Lo que si queda establecido es que el **numero total** de señales no cambia
sobre la misma poblacion, asi que ni la correccion de RS ni la geometria de la
linea 0 crean o destruyen señales: como mucho las mueven de banda.

Una medicion que si cerraria el punto, y que queda como FOLLOW_UP: rehacer la
pasada `pre-d31` con la correccion de zona de `relative_strength` revertida y
emparejar por `signal_id`.

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
umbral de 0.200. **La medicion tenia menos resolucion de la que aparentaba**, y
aparentaba mas solo porque se estaba leyendo la metrica secundaria. Cuanto de
ese deficit es de la ventana de la cosecha y cuanto del disenno, ver el punto
siguiente: la ventana lo explica por completo en el numero de bloques.

**Ninguna banda es concluyente.** Las cinco salen NO CONCLUYENTE, cada una con
su motivo publicado: intervalo demasiado ancho en las tres bajas, bloque minimo
de 2 observaciones en `70-80`, y en `80+` las tres cosas a la vez (bloque minimo
1, n=65 < 100, intervalo 0.668).

**De donde salen 21 y 5 bloques: la ventana de la cosecha, no el disenno.**
El protocolo pre-registro la capacidad sobre «Historico util: 2.430 sesiones»,
que da 40 bloques en swing y 8 en medio. La cosecha congelada que GATE P2 usa
tiene `requested_range: "5y"`:

    rango efectivo      2021-08-30 → 2026-08-28
    sesiones            ~1.302
    swing   1302 / 60   = 21 bloques con observaciones (+ un resto de 42 sesiones)
    medio   1302 / 300  = 5 bloques (+ un resto de 102 sesiones)

Es decir, **la cosecha congelada que usa GATE P2 tiene aproximadamente la mitad
de la ventana de 2.430 sesiones que el protocolo describia al pre-registrar la
capacidad**. El deficit de bloques se explica por completo asi.

No se amplia la ventana ni se rehace la cosecha: T-013 lo prohibe expresamente.
La discrepancia entre el documento pre-registrado y la cosecha queda como
FOLLOW_UP, en `follow-ups.md`.

Dentro de esta ventana la limitacion sigue siendo estadistica y ninguna cantidad
de señales la arregla: lo que fija la precision es el numero de bloques.

**Y en MEDIO el resto de 102 sesiones no es solo un bloque corto: lo invalida.**
P2.5 exige que el bloque **supere** `MAX_HOLD_BARS`, que en medio vale 250. Un
bloque de 102 sesiones no puede contener una operacion completa, asi que el
horizonte entero se publica como **`INSUFFICIENT` / no concluyente**, con el
motivo explicito:

    bloque temporal parcial 102 sesiones < MAX_HOLD_BARS 250:
    no utilizable para calibración ni conclusión

Los numeros de medio (`+0.102 R`, IC95 `[-0.053, 0.203]`, 5 bloques) **se
conservan y se publican por trazabilidad**, pero quedan marcados como **no
utilizables para calibracion ni conclusion**. No se amplia la cosecha, no se
elimina el bloque, no se fusiona con otro, no se cambia su peso y no se cambia
la longitud nominal de 300: cualquiera de esas salidas seria tomar ahora, con
los resultados delante, una decision metodologica nueva.

**Swing no esta afectado**: su ultimo bloque mide 42 sesiones y supera los 40 de
`MAX_HOLD_BARS`, aunque por poco. Su salida es identica byte a byte a la
anterior a esta correccion.

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
