# El ratio beneficio/riesgo coincide con su propio umbral

**Estado: pendiente de decisión.** Documento de hallazgo, no de cambio. Nada
de lo que aquí se describe se ha modificado, salvo donde se dice lo
contrario.

Medido el 2026-08-27 sobre `config.yaml` por defecto.

## El hecho

```yaml
levels:
  atr_stop_multiple: 2.0
  target_atr_multiples: [1.5, 3.0, 5.0]
risk:
  min_rr_ratio: 1.5
```

El ratio se calcula sobre el objetivo 2, y tanto el stop como ese objetivo
son múltiplos del mismo ATR:

```
reward = 3,0·ATR
risk   = 2,0·ATR
ratio  = 3,0 / 2,0 = 1,5   ← exactamente min_rr_ratio
```

Cuando manda el stop por volatilidad —el caso corriente— el ratio **no
depende del activo**: vale 1,5 siempre. En la ejecución del 2026-08-27 sobre
el grupo `europa`, 5 de 6 activos dieron 1,50 exacto; el único distinto
(MC.PA, 3,37) lo fue porque su stop se apoyó en un soporte cercano.

## Por qué importa

### 1. El veto de ratio casi nunca puede dispararse

`opportunity.classify` descarta si `rr_ratio < min_rr_ratio`. Pero con esta
configuración el ratio no puede bajar de 1,5: si no hay soporte cerca vale
1,5, y si lo hay el stop se acerca, el riesgo baja y el ratio *sube*. Un
filtro pensado para rechazar operaciones con mala relación rentabilidad/riesgo
no llega a rechazar ninguna por ese motivo.

### 2. La dimensión beneficio/riesgo deja de ordenar

Son 20 puntos sobre los 80 evaluables (25% de la nota). Los tramos de
`scoring._beneficio_riesgo` empiezan en 1,5 → 10 puntos ("aceptable"), así
que casi todos los activos sacan exactamente 10 y esos 20 puntos no separan
a unos de otros.

### 3. Convirtió el redondeo en un veredicto

`3,0·ATR / 2,0·ATR` da 1,4999999999999xx en coma flotante para la mayoría de
los precios reales: 25 de 42 combinaciones precio/ATR probadas. Como el valor
cae *clavado* sobre la frontera, el ruido decidía el veredicto, y del lado
severo (`DESCARTAR`, no `VIGILAR`). Con un ratio por defecto de 1,8 o de 1,2
ese ruido no habría cambiado nunca una decisión.

**Esto sí está corregido** (`rr_at_least` en `analysis/levels.py`, con tests
en `tests/test_analysis.py`), pero la causa que lo hizo grave sigue aquí.

### 4. La única franja donde descarta, descarta al revés

Barrido con `precio = 100`, `ATR = 2` (stop por volatilidad en 96,00),
moviendo la posición del soporte:

| soporte |  stop | riesgo | ratio | veredicto |
|--------:|------:|-------:|------:|-----------|
|   90,00 | 96,00 |  4,00% |  1,50 | justo en el mínimo |
|   95,90 | 96,00 |  4,00% |  1,50 | justo en el mínimo |
|   96,10 | 95,60 |  4,40% |  1,36 | **DESCARTA** |
|   96,40 | 95,90 |  4,10% |  1,46 | **DESCARTA** |
|   96,50 | 96,00 |  4,00% |  1,50 | justo en el mínimo |
|   96,60 | 96,10 |  3,90% |  1,54 | pasa |
|   98,00 | 97,50 |  2,50% |  2,40 | pasa |

El stop se apoya en el soporte con una holgura de `0,25·ATR` por debajo.
Cuando el soporte cae en esa ventana estrecha justo por encima del stop por
volatilidad, la holgura lo empuja **más lejos** que el stop por ATR: el
riesgo sube y el ratio baja del mínimo.

Resultado: la única situación en la que el filtro rechaza algo es cuando el
activo tiene un soporte identificable justo ahí — que es información buena.
Y contradice al propio código, cuyo comentario justifica apoyarse en el
soporte porque es «más ajustado y justificado por estructura».

Esto no es una decisión de configuración: es un defecto. Se corrige
impidiendo que el stop por soporte quede más lejos que el de volatilidad.

## La raíz

El stop mira la estructura del mercado; el objetivo que forma el ratio, no:

```python
target1 = price + m1 * atr
if resistance is not None and price < resistance < target1:
    target1 = resistance          # ← el objetivo 1 sí cede ante una resistencia real
target2 = price + m2 * atr        # ← el objetivo 2 nunca
...
reward_pct = (target2 / price - 1) * 100   # y el ratio se calcula sobre él
```

Por eso el ratio solo varía cuando varía el stop. Retocar los múltiplos mueve
la constante de sitio, pero no la convierte en una medida informativa: para
eso el objetivo 2 tendría que salir de estructura, como ya hace el objetivo 1.

## Opciones, con su contrapartida

| Opción | Efecto | Contrapartida |
|---|---|---|
| **A.** Bajar `min_rr_ratio` (p. ej. a 1,3) | El umbral deja de coincidir; el filtro pasa a ser un suelo real | No toca la geometría: el ratio sigue siendo casi constante |
| **B.** Subir el objetivo 2 (3,0 → 3,5) | Ratio por defecto 1,75, con holgura | **Choca con un principio del README**: «los objetivos se calculan antes que el ratio para que el ratio no pueda *fabricarse* moviendo un objetivo hasta que cuadre». Subir el objetivo mejora el ratio en el papel sin mejorar la operación |
| **C.** Bajar `atr_stop_multiple` (2,0 → 1,5) | Ratio 2,0, y el riesgo baja de verdad | Stops más estrechos = más barridos por ruido. Es el error del incidente de julio en `trading-bot`, donde la solución fue **subir** el ATR a 3,0 |
| **D.** Que el objetivo 2 ceda ante una resistencia real | El ratio pasaría a medir algo del activo | Cambio de diseño, no de parámetro. Rebaja el ratio cuando hay techo cerca, que es justo lo que debería hacer |
| **E.** Impedir que el stop por soporte quede más lejos que el de volatilidad | Elimina la franja del punto 4 | Ninguna: corrige una contradicción del código consigo mismo |

**E** es independiente de las demás y no compite con ellas. **B** y **C**
tienen contrapartidas concretas ya documentadas en este proyecto o en su
hermano. **D** es la única que ataca la raíz.

## Actualización 2026-08-27: medido con el backtest

Con el motor de `advisor/backtest/` (grupo `europa`, swing, 2y y 5y):

- **E aplicada**: el stop por soporte ya no puede quedar más lejos que el de
  volatilidad (`compute_levels`), con test que fija el caso de la tabla.
  Consecuencia estructural: con la config por defecto el ratio ya no puede
  bajar de 1,5, así que el veto de ratio solo puede dispararse si se cambian
  los múltiplos.
- **B medida** (objetivo 2 a 3,5·ATR): mejora leve (esperanza por operación
  0,35% → 0,92% con n=4; tramo ≥70 de 1,38% → 1,57%). Insuficiente para
  decidir; queda abierta.
- **C medida** (stop 3,0·ATR): **rompe el sistema tal cual** — con objetivo 2
  en 3,0·ATR el ratio pasa a 1,0 y el veto de ratio descarta todo (1 sola
  operación en 5 años). Solo tendría sentido subiendo los objetivos a la vez.
- **D** sigue sin medir: exige cambiar el cálculo, no la configuración.

El hallazgo operativo más importante salió de esta medición y está aparte:
el veto de *no perseguir precio* era lo que dejaba al asesor sin operar, y
se degradó a advertencia (ver `advisor/analysis/opportunity.py` y el README).

## Actualización 2026-08-29: D medida y descartada

D era la única opción que atacaba la raíz, así que se implementó detrás del
interruptor `levels.target2_structural` (por defecto `false`) para poder
medirla contra el control sobre exactamente los mismos datos. El control
reprodujo los números ya publicados (europa 2y: 20 operaciones, +0,42%/op;
europa 5y: 75 y +0,34%/op), así que la comparación es limpia.

Compuesto medio por activo, política real, coste 0,2% ida y vuelta:

| Corte | Control | Con D | Operaciones |
|---|---|---|---|
| europa 2y | **+1,9%** | −0,7% | 20 → 2 |
| europa 5y | **+2,7%** | −1,4% | 75 → 10 |
| usa_en_xetra 5y *(fuera de muestra)* | **+45,3%** | +2,6% | 143 → 21 |
| etfs_ucits 5y *(fuera de muestra)* | +0,8% | **+2,7%** | 83 → 13 |

D reduce las operaciones un 85% en los cuatro cortes. La esperanza por
operación mejora en `etfs_ucits` y aguanta en `usa_en_xetra`, pero con tan
pocas señales el dinero compuesto se hunde: en el corte fuera de muestra más
poblado, de +45,3% a +2,6%.

**A ya no rescata a D, y el motivo importa.** Bajar `min_rr_ratio` a 1,3 o a
1,0 deja el número de operaciones *exactamente igual* (2, 10 y 21). Aflojar
el veto no devuelve ninguna señal porque el ratio no solo veta: alimenta los
20 puntos brutos de la dimensión `beneficio_riesgo` y, con los fundamentales
excluidos, la nota se normaliza sobre 80, así que valen hasta **25 puntos de
100**. Al recortar el objetivo 2, el tramo de ratio baja de 10/20 a 5/20 o a
0/20 y la puntuación se hunde por debajo de `min_score_operar`. No es una ley
—una señal con el resto de dimensiones muy altas puede sobrevivir— pero en
los cuatro cortes medidos no sobrevivió ninguna. El veto se puede aflojar; la
nota, no, sin rehacer los pesos. D+B (objetivo 2 a 3,5·ATR) recupera algo de
esperanza por operación pero no el número de señales.

### Por qué falla: la resistencia no es un obstáculo, es el destino

Diagnóstico sobre todas las velas con niveles válidos (6.936 en europa 5y,
9.232 en usa_en_xetra 5y):

- D muerde en el **46-48%** de las velas: la resistencia queda por debajo del
  objetivo 2 casi la mitad del tiempo.
- Cuando muerde, el recorrido hasta la resistencia tiene mediana **2,6-2,8%**
  frente a un riesgo mediano de **4,2-4,8%**. Un objetivo que está a la mitad
  de distancia que el stop no puede dar un ratio aceptable.
- La proporción de velas con ratio ≥1,5 cae del 60-62% al 35-36%.

La causa es la definición de resistencia: `high_lookback` es el **máximo de
las últimas 60 velas incluyendo la actual** (`advisor/analysis/snapshot.py`),
así que está por encima del precio casi siempre y, en un activo fuerte, muy
cerca. No es mirar el futuro —el backtest evalúa al cierre de esa vela— pero
sí basta una mecha superior de la propia vela que genera la señal para
convertirse en el "primer obstáculo" que recorta el objetivo. Anclar ahí el
objetivo que forma el ratio equivale a exigir que el activo esté lejos de su
propio máximo reciente.

Y ese requisito va al revés de lo que hace el mercado. Etiquetando cada señal
con el ratio que habría tenido bajo D, pero dejando las salidas del control
(objetivos intactos), el ratio de D **no ordena nada** — si acaso, invierte:

| Ratio bajo D | europa 5y | usa_en_xetra 5y |
|---|---|---|
| < 0,5 | +0,77% (n=112) | **+1,78%** (n=172) |
| 0,5-1,0 | **+1,14%** (n=45) | +0,17% (n=61) |
| 1,0-1,5 | −0,05% (n=144) | −0,04% (n=213) |
| ≥ 1,5 | +0,51% (n=308) | +0,22% (n=432) |

El tramo que D castiga más —precio pegado a su máximo de 60 sesiones— es el
que mejor rinde. En este universo esa cercanía es una ruptura en marcha, no
un techo. D no está mal calibrada: parte de una premisa que los datos no
sostienen.

## Sin decidir

Solo queda **B** (objetivo 2 a 3,5·ATR), con la mejora leve ya medida el
2026-08-27 y confirmada como leve aquí. A pierde sentido tras E, C rompe el
sistema y D queda descartada por medición.

El código de D se conserva tras `levels.target2_structural` (con test) para
que el hallazgo sea reproducible en una línea de configuración. No está en
`config.yaml`: activarlo empeora el resultado en tres de los cuatro cortes.

Lo que sigue abierto no es el ratio, sino la definición de resistencia: un
nivel estructural que no sea "el máximo reciente, incluida la vela de hoy"
—por ejemplo un máximo pivote ya superado y confirmado— podría hacer que la
idea de D signifique lo que pretendía. Eso es un cambio de `snapshot`, no de
`levels`, y no se ha medido.
