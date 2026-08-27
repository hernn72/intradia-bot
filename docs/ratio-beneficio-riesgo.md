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

## Sin decidir

B y D siguen abiertas; A pierde sentido tras E (el ratio ya no puede caer
por debajo del umbral con la configuración por defecto).
