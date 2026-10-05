# T-023 — Hipótesis candidatas (post hoc)

> **Exploratorio / post hoc. No cambia D-70, no valida una nueva política y no constituye evidencia
> confirmatoria.** Ninguna hipótesis es un resultado. No se recomienda ninguna, no se elige ganadora y
> no se implementa ninguna. Cada una nace de mirar los desenlaces de P6, así que cualquier estudio
> que la pruebe necesita ficha y pre-registro propios y **no cambia la etiqueta de P6**.

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

**Restricción común sobre los datos.** La cosecha `071ddb2b…` (2022-06-14 → 2026-08-27) ya se usó
para desarrollar P3–P6. Cualquier hipótesis de esta lista que se estudie sobre esa misma ventana es,
como mucho, **desarrollo**. Falsarla de verdad exige datos que no hayan intervenido en su
formulación: una ventana posterior al 2026-08-27 o el holdout que fije GATE P7, con las fechas en el
decision log antes de mirar (INV-15).

Las referencias «(A-1)», «(C-7)», etc. remiten a la sección y al número de `hallazgos.md`.

---

## H23-01 — La salida por objetivo retiene una fracción pequeña de las subidas amplias del universo

- **Observación que la motiva:**
  - la brecha se abre sobre todo en 2023–2024, con el benchmark en +43,8 y +50,9 pp (A-1, A-3);
  - el P&L depende de las salidas por objetivo, cerradas a unos 2 R tras unas 16 sesiones (D-11,
    D-14);
  - B2 y S2 operaron los 10 mejores activos del benchmark y de ellos sale el 41 % y el 32 % de su
    P&L, pero en tramos cortos (E-16, E-17);
  - con todas las barras y un 95 % de exposición, la brecha sigue siendo de −9,5 y −5,6 pp (I-25).
- **Mecanismo propuesto:** un objetivo fijo en múltiplos de ATR y el horizonte de 40 sesiones cortan
  la cola derecha de las operaciones. En mercados con tendencia amplia, el comprar y mantener retiene
  esa cola y el sistema no.
- **Por qué es post hoc:** surge al comparar la trayectoria de P6 con el benchmark después de ver
  el resultado.
- **Qué implicaría estudiar:** reglas de salida (objetivo, horizonte máximo, salida dinámica), es
  decir, la geometría.
- **Datos necesarios:** precios OHLCV de una ventana no usada en P3–P6 y la misma población de señales
  point-in-time.
- **Simulación nueva necesaria:** sí. Un sistema completo de cartera con reglas de salida alternativas
  fijadas de antemano, frente al buy-and-hold de la misma ventana.
- **Estudio mínimo pre-registrado capaz de falsarla:** fijar ex ante un número pequeño de reglas de
  salida (por ejemplo, ≤ 3) y medir la fracción de la subida de cada activo retenida durante las
  operaciones y el exceso sobre el buy-and-hold, con criterio y ventana fijados en el decision log
  antes de mirar.
- **Riesgo de sobreajuste:** alto. Se elegiría la regla de salida que mejor reproduzca una subida ya
  observada (2023–2024), y el espacio de reglas de salida es grande.
- **Qué la descartaría:** que, en datos nuevos y con salidas sin objetivo fijo, la fracción retenida
  de la subida y el exceso sobre el benchmark no mejoren, o que la brecha siga igual con exposición
  casi completa.

## H23-02 — Bajo capital finito, la asignación entre señales simultáneas es material en B2

- **Observación que la motiva:**
  - B2 rechaza por cash el 91,2 % de sus entradas ejecutables;
  - hay rechazos en el 76 % de los días y todos los años, con una mediana de 6 al día;
  - el capital pedido es 3,45 veces el disponible (C-7).
- **Mecanismo propuesto:** cuando hay más señales que capital, qué entradas se toman (hoy, por orden
  de desempate pre-registrado) determina el resultado de la cartera tanto como el edge medio de la
  población de señales.
- **Por qué es post hoc:** se formula tras ver el contador `INSUFFICIENT_CASH` y la presión de capital
  de P6.
- **Qué implicaría estudiar:** reglas de prioridad o asignación (por ejemplo, por puntuación,
  diversificación o riesgo), sin cambiar la población de señales ni la geometría.
- **Datos necesarios:** ventana no usada y los desenlaces de **todas** las señales ejecutables, también
  las que hoy se rechazan. Ese dato no existe en los artefactos (C-10, pregunta 11).
- **Simulación nueva necesaria:** sí. La cartera con cada regla de asignación, y el desenlace de las
  señales rechazadas.
- **Estudio mínimo pre-registrado capaz de falsarla:** fijar ex ante dos o tres reglas de asignación,
  más el desempate actual como control, y medir la dispersión del resultado de cartera entre reglas
  frente a la dispersión entre órdenes de desempate aleatorios con la misma regla. Si la regla no
  supera esa dispersión de referencia, se descarta.
- **Riesgo de sobreajuste:** medio–alto. Con 7 005 rechazos hay muchos órdenes posibles, y elegir el
  que mejor sale sobre datos vistos es selección oportunista.
- **Qué la descartaría:** que en datos nuevos el resultado de cartera apenas cambie entre reglas de
  asignación (dentro de la variación por desempate aleatorio), o que ninguna regla reduzca la brecha
  con el benchmark.

## H23-03 — En S2, la baja participación (cash ocioso) pesa más que la saturación de cash

- **Observación que la motiva:**
  - S2 tiene una exposición media del 60,5 % y 219 días con 25 % o menos invertido, repartidos por
    todos los años (B-5);
  - el mayor déficit diario se acumula en esos días, con un exceso de −0,442 (B-4);
  - su principal motivo de rechazo es `ABOVE_MAX_ENTRY`, 1 175 de 1 522 (C-8);
  - los rechazos por cash son ocasionales (15 % de los días).
- **Mecanismo propuesto:** con pocas señales ejecutables y la regla de entrada máxima, el sistema
  pasa gran parte del tiempo con capital sin invertir mientras el universo sube. La brecha procede
  más del capital ocioso que de la calidad de las operaciones.
- **Por qué es post hoc:** surge del cruce de exposición y exceso diario, que se hizo tras ver P6.
- **Qué implicaría estudiar:** el tratamiento del capital ocioso (por ejemplo, una cartera de reserva
  definida ex ante) o la tolerancia de entrada máxima. Son conceptos de cartera o ejecución, no de
  señal.
- **Datos necesarios:** ventana no usada y precios de las señales rechazadas por `ABOVE_MAX_ENTRY`, que
  no están en los artefactos.
- **Simulación nueva necesaria:** sí.
- **Estudio mínimo pre-registrado capaz de falsarla:** fijar ex ante una única política de capital
  ocioso y medir si la brecha en días de baja exposición desaparece sin empeorar el drawdown más allá
  de un límite fijado de antemano. Comparar contra S2 sin cambios en la misma ventana nueva.
- **Riesgo de sobreajuste:** medio. Una cartera de reserva parecida al benchmark reduciría la brecha
  por construcción. El estudio tiene que separar «parecerse al benchmark» de «aportar edge», por
  ejemplo midiendo el exceso solo de la parte activa.
- **Qué la descartaría:** que en datos nuevos la brecha de S2 no se concentre en los días de baja
  exposición, o que la parte activa siga por debajo del benchmark con independencia del capital
  ocioso.

## H23-04 — El rendimiento por euro y día invertido de las operaciones es inferior al del universo

- **Observación que la motiva:**
  - en B2, con más del 90 % invertido, el retorno diario medio es parecido al del benchmark (0,00061
    frente a 0,00053), pero no lo supera de forma sostenida (B-4);
  - el riesgo por operación es del 0,41–0,42 % de la equity, sobre un notional del 8 %, con una R
    media de 0,24–0,25 (D-12);
  - C0, B2 y S2 quedan todos por debajo del benchmark, incluso con todas las barras (I-25, J-27).
- **Mecanismo propuesto:** el edge positivo de la señal mide la operación contra su propio stop (en
  R), no contra el rendimiento de mantener el mismo activo ese mismo tiempo. Si las ventanas
  seleccionadas rinden lo mismo o menos que el drift del universo, una R positiva puede convivir con
  un exceso negativo.
- **Por qué es post hoc:** surge al ver a la vez R > 0 y `excess_CAGR_pp` < 0 en P6.
- **Qué implicaría estudiar:** una métrica de edge relativa al drift (el retorno de la operación menos
  el retorno del mismo activo o del universo en la misma ventana). Es un concepto de medición, no un
  parámetro.
- **Datos necesarios:** precios del activo y del universo en cada ventana de operación. En la cosecha
  consumida solo servirían como desarrollo; para falsarla hace falta una ventana nueva.
- **Simulación nueva necesaria:** no necesariamente una cartera nueva, pero sí leer precios fuera de
  los artefactos de P6, cosa que T-023 no hace.
- **Estudio mínimo pre-registrado capaz de falsarla:** sobre las señales de una ventana nueva, medir
  ex ante el exceso por operación frente al mismo activo comprado y mantenido durante el holding
  efectivo. Si su media es ≤ 0 con el estimador fijado, la señal no aporta timing sobre el drift.
- **Riesgo de sobreajuste:** bajo en la medición; alto si se usa luego para retocar señales.
- **Qué la descartaría:** que, en datos nuevos, el exceso por operación frente al drift sea claramente
  positivo y aun así la cartera quede por debajo del benchmark. En ese caso la brecha sería de
  cartera (H23-02 o H23-03), no de señal.

## H23-05 — El FX y la composición regional restan, pero de forma secundaria

- **Observación que la motiva:**
  - el FX de B2 es de −8 859 EUR (6,4 % de la brecha) (G-22);
  - el benchmark gana el 52 % en USA, mientras que B2 tuvo un 24 % de exposición a USA y un 36 % a
    Europa (F-19).
- **Mecanismo propuesto:** la composición regional y de divisas que generan las señales se aleja de
  la que más rindió en la ventana, y el FX convierte parte del P&L local en pérdida en EUR.
- **Por qué es post hoc:** surge de agregar la exposición y el P&L por región tras ver el resultado.
- **Qué implicaría estudiar:** límites o neutralización por región o divisa (cobertura FX, presupuesto
  por región).
- **Datos necesarios:** ventana no usada y FX congelado de esa ventana.
- **Simulación nueva necesaria:** sí.
- **Estudio mínimo pre-registrado capaz de falsarla:** fijar ex ante una única restricción regional o
  de cobertura y medir si cambia el exceso más allá de la variación entre ventanas.
- **Riesgo de sobreajuste:** alto. La región ganadora de 2023–2025 (USA) puede no repetirse, y ajustar
  pesos regionales a una ventana vista es *market timing* encubierto.
- **Qué la descartaría:** que en datos nuevos el FX y la composición regional expliquen una fracción
  pequeña de la brecha, como ya ocurre aquí por magnitud (cada componente es < 12 % de la brecha).
