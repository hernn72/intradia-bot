# FOLLOW_UP abiertos por T-013, NO corregidos dentro de la ficha

Clasificados segun `docs/metodo-trabajo.md` seccion 5. Ninguno bloquea GATE P2 y
ninguno se arregla aqui: mezclarlos con T-013 seria ampliar su alcance.

## FU-1 — La ventana de la cosecha es la mitad de la pre-registrada

`docs/protocolo-investigacion.md` P2.5 pre-registra «Historico util: 2.430
sesiones» → 40 bloques en swing, 8 en medio. La cosecha `071ddb2b…` tiene
`requested_range: "5y"`: rango efectivo 2021-08-30 → 2026-08-28, ~1.302
sesiones, que dan 21 y 5 bloques.

Es la discrepancia entre un documento pre-registrado y el artefacto real, que
`docs/metodo-trabajo.md` seccion 3 obliga a registrar citando ambos. **No se
resuelve en T-013**: rehacer la cosecha seria «ampliar la ventana», que la ficha
prohibe expresamente.

Que hay que decidir mas adelante, y no lo decide el implementador: si se congela
una cosecha de 10 anos y se rehace el laboratorio sobre ella (con un
`data_vintage_id` nuevo y declarando que los resultados anteriores no se
mezclan), o si se corrige el protocolo para que la ventana pre-registrada sea la
que de verdad se usa. Son decisiones distintas con consecuencias distintas.

## FU-2 — El ultimo bloque de cada horizonte es mas corto que `MAX_HOLD_BARS` · **RESUELTO el 2026-09-21**

`advisor/research/capacity.py::_protocol_block_length` validaba la longitud
**nominal** del bloque, no la del ultimo bloque real. Con 1.302 sesiones:

    swing   [60 x 21, 42]     ultimo bloque  42 > MAX_HOLD_BARS  40  (lo supera, aunque por poco)
    medio   [300 x 4, 102]    ultimo bloque 102 < MAX_HOLD_BARS 250  (no puede contener una operacion completa)

El protocolo dice que una ventana mas corta que `MAX_HOLD_BARS` es invalida por
definicion para ese horizonte. Como el primario es media **simple** entre
bloques, ese bloque parcial aportaba **1/5** del `+0.102 R` publicado para medio.

**Resuelto con la salida conservadora, que no toma ninguna decision nueva sobre
como tratar bloques parciales.** `TemporalBlockMap.sessions_in_block` calcula la
longitud real de cada bloque y `_classify_capacity` invalida el horizonte
—`INSUFFICIENT`, no concluyente— en cuanto un bloque **ocupado** tiene menos
sesiones que `MAX_HOLD_BARS`, con el motivo explicito
`bloque temporal parcial 102 sesiones <= MAX_HOLD_BARS 250`. La materia prima
numerica se conserva y se publica por trazabilidad, pero queda marcada como no
utilizable para calibracion ni conclusion.

No se amplio la cosecha, no se elimino el bloque, no se fusiono con otro, no se
cambio su peso y no se cambio la longitud nominal de 300. Swing no se mueve:
su ultimo bloque mide 42 y supera los 40 de `MAX_HOLD_BARS`.

**La comparacion es `<=`, no `<`.** P2.5 exige que el bloque **supere**
`MAX_HOLD_BARS`, asi que la igualdad tampoco vale, y es el mismo criterio que
usa la validacion NOMINAL de `_protocol_block_length`
(`block_length <= max_hold_bars`). Si las dos divergieran, un bloque real de
exactamente 250 sesiones pasaria mientras uno nominal de 250 se rechaza. El test
fija los tres limites —`42 > 40` valido, `250 == 250` invalido, `102 < 250`
invalido— para que no vuelvan a separarse.

## FU-3 — La atribucion poblacion / correccion de RS no es observable

De agosto solo se conservan los agregados por banda, no la salida por señal, asi
que el numero de señales que cambian de banda esta acotado en [97, 10.228] y no
es observable. Medicion que lo cerraria: rehacer `pre-d31` con la correccion de
zona de `relative_strength` / `relative_strength_series` revertida y emparejar
por `signal_id`. Es un estudio nuevo, pre-registrable.

## FU-4 — `format_event_study_report` no protege INV-14

`advisor/research/event_study.py::format_event_study_report` acepta
`estimator_summary=None` y entonces genera un informe cuya tabla encabeza con
`P(objetivo antes de stop)`, que es la metrica **secundaria**, sin primario
alguno. La guarda que la ficha pide solo se implemento en
`format_capacity_report`. **Ningun artefacto publicado esta afectado**:
`advisor/main.py` siempre pasa el primario. Corregir haciendo el parametro
obligatorio o lanzando `ValueError("INV-14: …")`, con su test.

## FU-5 — Una banda sin señales observables publica `+0.000` como primario

`advisor/research/capacity.py:615`, `mean=_mean_float(means) or 0.0`. «0,000 R de
expectancy» y «sin observaciones» son afirmaciones distintas, y de eso va
INV-20. Ninguna tabla publicada esta afectada: las cinco bandas tienen señales
en los dos horizontes y las tres poblaciones.

## FU-6 — `CapacitySummary` enmascara `None` como `0.0`

`advisor/research/capacity.py:96-106`: las propiedades de compatibilidad
`interval_lower` / `interval_upper` / `interval_width` devuelven `0.0` cuando el
valor es `None`. `0.0` es el valor de **maxima** precision y pasaria cualquier
umbral de `_classify_capacity`. Hoy no las usa nadie en `advisor/`, solo un
test. Borrarlas o hacerlas `Optional`.

## FU-7 — `preregistered_estimators` ignora el `band_of` del informe

`advisor/research/capacity.py:331` calcula `primary_by_band` siempre con
`score_band(...)` del score completo, mientras `assess_capacity` acepta un
`band_of` arbitrario y `advisor/research/ablation.py` lo usa con
`band_of_ablated`. Para `capacity_ablated` el bloque de estimadores describiria
las bandas del score completo. Hoy es inocuo porque `format_ablation_report`
nunca imprime `capacity_ablated.estimators`.

## FU-8 — `research_population_header` es codigo muerto

`advisor/research/population.py:28`: definida y nunca llamada; la cabecera se
construye en linea en cada informe. Borrarla o usarla.

## FU-9 — La declaracion de sesgo del roadmap cita un vintage caducado

`docs/roadmap.md` seccion «Universo» dice que el vintage vigente es
`c8496446…` (103 analizables, D-31). Desde D-35 el vigente es `237b0056…` (93).
La copia en `declaracion-de-sesgo-del-universo.md` es **literal a proposito** y
conserva el error; corregir el roadmap queda fuera de T-013, que no puede
editar esa declaracion.

## Ya corregidos dentro de T-013 (SAME_SCOPE, no son FOLLOW_UP)

- La tabla de la ablacion sustituia intervalo, media y bloques por «NO
  CONCLUYENTE», incumpliendo `docs/metodo-trabajo.md` seccion 3.
- `test_intervalo_primario_por_banda_se_calcula_sobre_bloques` usaba bloques del
  mismo tamano y no distinguia la media por bloque de la media agrupada. Lo
  detecto la revision independiente con una mutacion que sobrevivia los 613
  tests. Corregido con bloques de tamanos distintos y defecto inyectado.
- Faltaba el test de integracion de las tres poblaciones que la ficha exige en
  su seccion «Tests de integracion». Anadido:
  `tests/test_population_real_vintage.py`.
- **FU-2 (bloque temporal parcial)** se reclasifico a BLOCKER en la revision del
  PR y quedo resuelto dentro de T-013; el detalle esta arriba.
