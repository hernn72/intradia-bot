# T-024 — Edge relativo al drift: ¿la señal elige ventanas mejores que mantener el activo? (D-71)

Estado: **FICHA DE DISEÑO — OD abiertas. No hay pre-registro congelado.** No se ha calculado ninguna
métrica de T-024, ni sobre la cosecha consumida ni sobre datos posteriores al 2026-08-27. No existe
código de T-024.

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

---

## 0. Identidad de partida

| | |
|---|---|
| Base | `main = d86a94e6fcbc86c7dfdb345eaf7959b9d83e91cc` (merge del PR #43, T-023) |
| Decisión | D-71 (opción E de T-023) |
| Hipótesis de origen | H23-04 (`evidence/2026-10-05-T-023-diagnostico-post-p6/hipotesis-candidatas.md`), post hoc |
| P6 | Cerrado y vinculante: B2 `NO PASA`, S2 `NO PASA`, salida `[]` (D-70); P7 BLOQUEADO |
| Cosecha consumida | `071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841` (hasta el 2026-08-27): solo desarrollo |
| Políticas | B2 y S2 tal como están en `evidence/2026-10-03-T-021-p5-cierre/politicas-finales.json`; C0 = producción |
| Producción | `config.yaml` `"1.0"`, C0, Score v1 70/60 legacy, Score v2 inactivo, Pi `v0.4.1` |

## 1. Pregunta

P6 midió edge positivo por operación (mean_R_local de 0,25 en B2 y 0,24 en S2) y, a la vez, carteras muy por
debajo del buy-and-hold del universo (−15,8 y −18,7 pp de CAGR). T-023 mostró que la brecha persiste
incluso con la población de todas las barras y ≈ 95 % de exposición (−9,5 y −5,6 pp). H23-04 propone un
mecanismo: la R positiva mide la operación **contra su propio stop**, no contra lo que el activo rinde
sin seleccionar ventana. D-71 pregunta, antes de tocar la cartera:

> ¿Las ventanas que selecciona la señal aportan rendimiento adicional frente a mantener el mismo activo?

T-024 es una **medición**. No cambia ninguna regla de señal, geometría ni cartera.

## 2. Qué no hace

- No simula otra vez P6 ni ninguna cartera. La unidad es la ventana de cada señal, sin capital finito.
- No cambia B2, S2 ni C0, ni elige geometría, prioridad, sizing, cash, entrada máxima, objetivos,
  stops ni horizonte.
- No inicia P7 ni lo desbloquea, y no activa nada en producción.
- No usa la cosecha consumida para decidir. Sobre ella solo se desarrollan el código, los tests y las
  definiciones, siempre rotulados como desarrollo.

## 3. Notación y contrato de la operación (el de P6, sin cambios)

Para la ventana `i` de la política `p` sobre el activo `a`, en el calendario local de `a`:

- **Entrada:** la señal se analiza al cierre de la sesión `s_i`; la orden entra en la apertura de la
  sesión `e_i = s_i + 1`.
  - Precio bruto `O_{e_i}`; precio efectivo `P_in = O_{e_i}·(1 + σ)`, con `σ = 5 pb` de slippage.
  - Comisión `f = 0,001` sobre el efectivo.
  - Si `O_{e_i}` supera la entrada máxima, o el stop o el objetivo no son válidos, la ventana no se
    abre (`ABOVE_MAX_ENTRY`, `INVALID_STOP`, `INVALID_TARGET`).
- **Salida en la sesión `x_i`:**
  - por gap en la apertura: precio bruto `O_{x_i}` (`_process_open_exit`);
  - por stop o por objetivo dentro de la sesión: precio bruto igual al stop o al `target2`;
  - por tiempo (40 sesiones) o final: precio bruto `C_{x_i}`;
  - en todos los casos, precio efectivo `P_out = Q_out·(1 − σ)`, donde `Q_out` es el precio bruto, y
    comisión `f` (`advisor/research/p6_sim.py:456-463`, `673-703`).
- **Dividendos:** `D_i` = suma de los dividendos brutos por acción a los que da derecho la posición
  según la regla de P6 (derecho fijado en la ex-date mientras se mantiene, abono en el cierre de la
  ex-date, `p6_sim.py:679-681`, `707-718`; D-69).
- **Retorno logarítmico neto de la operación:**

  `ℓ_i = ln( (P_out·(1 − f) + D_i) / (P_in·(1 + f)) )`

- **Retorno logarítmico total diario, cierre a cierre:** `g_{a,t} = ln((C_t + d_t)/C_{t−1})`, con `d_t`
  el dividendo con ex-date `t` y los precios en la misma vista de la cosecha que usa P6 para la ejecución.
- **Splits:** los ajusta la vista de ejecución de la cosecha, igual que en P6.

## 4. Por qué la definición literal es degenerada (y H23-04 también, tal como quedó escrita)

D-71 enuncia, como punto de partida a revisar:

`edge_relativo = retorno_sistema − retorno_pasivo_del_mismo_activo_en_el_mismo_intervalo`

El pasivo del **mismo activo** en el **mismo intervalo** compra al precio bruto de entrada `O_{e_i}` y
valora al precio bruto de salida `Q_out`, en el mismo instante que la operación. Cobra los mismos
dividendos `D_i`, porque mantiene la misma posición en las mismas ex-dates. Su retorno total es:

`π_i = ln( (Q_out + D_i) / O_{e_i} )`

y por tanto:

**D1:** `ℓ_i − π_i = ln( (Q_out·(1−σ)(1−f) + D_i) / (Q_out + D_i) ) − ln( (1+σ)(1+f) )`

Las dos partes son ≤ 0, y la expresión vale 0 solo si `σ = f = 0`. **Para toda operación, D1 depende
solo de los costes y del peso relativo del dividendo; no contiene información sobre el timing.**
Ejemplo sin dividendo: D1 = ln((1−σ)(1−f)) − ln((1+σ)(1+f)) ≈ −0,0030, que es exactamente el coste de
la ida y vuelta.

La redacción de H23-04 en T-023 («frente al mismo activo comprado y mantenido durante el holding
efectivo») tiene el mismo defecto. Su mecanismo, en cambio, sí es informativo: si las ventanas
seleccionadas rinden lo mismo o menos que el **drift** del activo, una R positiva puede convivir con un
exceso negativo frente al buy-and-hold. T-023 queda publicado tal cual (no se reescribe evidencia), y
esta ficha recoge la corrección.

**Hay que comparar la ventana seleccionada con lo que el mismo activo rinde en sesiones no
seleccionadas o medias, es decir, con su drift**, no con la misma ventana. El §5 propone definiciones
concretas y la elección es del propietario (OD-T24-1).

## 5. Definiciones candidatas

`h_i` es la duración comparable de la ventana en sesiones; su convención está en §5.2 (OD-T24-3).
`[T0, T1]` es la ventana de referencia del drift, fijada en §9.

| Id | Exceso por ventana | Qué mide | Propuesta |
|---|---|---|---|
| **D1** | `ℓ_i − π_i` (§4) | Solo costes y dividendo | **Excluida** (se publica como comprobación de que la implementación cuadra) |
| **D2** | `ℓ_i − h_i·μ_a`, con `μ_a` = media de `g_{a,t}` en todas las sesiones de `a` en `[T0, T1]` | **Timing** frente al drift medio del mismo activo (la referencia del buy-and-hold) | **Primaria (recomendada)** |
| **D2o** | `ℓ_i − h_i·μ_a^{fuera}`, con `μ_a^{fuera}` = media de `g_{a,t}` en las sesiones de `[T0, T1]` que **no** cubre ninguna ventana de `(p, a)` | Timing frente a las sesiones no seleccionadas del mismo activo | Secundaria |
| **D2c** | `ℓ_i − h_i·μ_a^{causal}`, con `μ_a^{causal}` = media de `g_{a,t}` en las 250 sesiones anteriores a `s_i` | Timing frente al drift reciente conocido al entrar | Descriptiva |
| **D3** | `ℓ_i − ln(I_r(x_i)/I_r(e_i − 1))`, con `I_r` el índice equiponderado total return, cierre a cierre, de los activos analizables de la región de `a` | Selección más timing frente al universo de su región | Descriptiva |
| **D4** | `ℓ_i − ln((C_{e_i+40} + D)/P_in)`: el mismo activo mantenido desde la misma entrada 40 sesiones | Si la salida corta la subida (H23-01), no el timing | Descriptiva, fuera del criterio |

### 5.1 Por qué D2 es la propuesta, y su sesgo de atenuación

- Es la única que mantiene el «mismo activo» de D-71 sin ser degenerada.
- Responde al mecanismo de H23-04.
- Usa la referencia del benchmark de P6: el buy-and-hold gana el drift completo de cada activo.

Hay una identidad que la conecta con la cartera. `Σ_i ℓ_i` es lo que ganan las ventanas, y
`Σ_i h_i·μ_a` es lo que el activo habría ganado de media en ese mismo número de sesiones. Si D2 ≤ 0, las
ventanas no ganan más que el drift y ninguna asignación lo cambia. Si D2 > 0, la brecha de cartera
tiene que venir de la participación o de la asignación (H23-02 y H23-03).

**Atenuación.** `μ_a` incluye las sesiones de las propias ventanas. Si en `(p, a)` las ventanas cubren
una fracción `φ_a` de las sesiones de `[T0, T1]`, la diferencia media entre sesiones dentro y fuera
queda multiplicada por `(1 − φ_a)` en D2, salvo por costes y por la convención de §5.2. D2 está
**sesgada hacia 0**: es más difícil obtener `POSITIVO` y también `NO POSITIVO`. Por eso se publica `φ_a`
por política y la variante D2o, que no sufre esta atenuación pero tiene menos sesiones de referencia
cuando `φ_a` es alto. La elección entre D2 y D2o como primaria es parte de OD-T24-1.

**Limitación de D2 y D2o:** `μ_a` es ex post sobre `[T0, T1]`, igual que el benchmark. Es legítimo para
evaluar porque no decide ninguna entrada, pero no es implementable en tiempo real. D2c sí es causal,
aunque mide otra cosa: el timing frente al momentum reciente.

### 5.2 Base temporal: `ℓ_i` intradía frente a `μ_a` cierre a cierre (OD-T24-3)

`ℓ_i` va de la **apertura** de `e_i` a la salida en `x_i`, que puede ser en la apertura, dentro de la
sesión o al cierre. `g_{a,t}` va de cierre a cierre. Hay dos convenciones posibles, y se fija una:

- **(a) Sesiones completas, como penalización deliberada:** `h_i = x_i − e_i + 1`. El pasivo
  comparable equivale a cubrir de `C_{e_i−1}` a `C_{x_i}`, de modo que la noche anterior a la entrada y
  el resto de la sesión de salida cuentan como drift aunque la operación no los tenga. Si el drift es
  positivo, esto es conservador contra la señal y sesga D2 hacia abajo en una cuantía del orden de
  `μ_a` por ventana.
- **(b) Descomposición noche y día:** se estiman `μ_a^{noche}` = media de `ln(O_t/C_{t−1})` y
  `μ_a^{día}` = media de `ln((C_t + d_t)/O_t)`. El pasivo comparable es
  `(x_i − e_i)·μ_a^{noche} + (x_i − e_i + 1)·μ_a^{día}`: las noches entre `e_i` y `x_i` y las sesiones
  diurnas de `e_i` a `x_i`, con la de salida contada completa aunque la salida sea intradía. Es más
  exacta, salvo en la sesión de salida.

**Ejemplos sintéticos obligatorios en los tests**, para las dos convenciones y con resultados
calculados a mano:
- entrada en apertura con salida en la misma sesión por stop;
- salida por gap en la apertura de `x_i`;
- salida por objetivo intradía;
- salida por tiempo a las 40 sesiones;
- salida final;
- una ventana con dividendo;
- una ventana con split.

### 5.3 Datos insuficientes, suspensiones y bajas (MENOR de la revisión)

- `μ_a` y `μ_a^{fuera}` se calculan sobre las sesiones con barra válida de `a` dentro de `[T0, T1]`. No
  se imputa ninguna sesión.
- Si `a` tiene menos de **60 sesiones válidas** en `[T0, T1]`, o menos de **20 fuera de ventana** para
  D2o, sus ventanas se excluyen de la métrica correspondiente. Se publican el número de ventanas y de
  activos excluidos. Este criterio solo usa la disponibilidad de barras, no los retornos.
- Si `a` deja de cotizar o se suspende con una ventana abierta, la ventana se cierra con la regla final
  de P6 en su última barra válida. `μ_a` usa solo hasta esa barra.

## 6. Población y ventanas

- **Políticas decisorias:** B2 y S2. **C0** se mide como control descriptivo (OD-T24-2).
- **Señales:** población decisoria de P6, `OPERAR_score_v1_point_in_time`, con broker neutral (D-04),
  `setup_radar = OPERAR`, `setup_accion = COMPRAR` y contexto point-in-time. La generan
  `build_snapshot_series` y la configuración de cada política, sin ningún cambio.
- **Sin capital finito:** no hay `INSUFFICIENT_CASH`. Cada señal ejecutable puede abrir su ventana.
  Esto aísla el timing de la asignación.
- **No solapamiento por activo (solo en la ejecución decisoria sellada):** mientras una ventana de
  `(p, a)` está abierta, otra señal de `(p, a)` no abre ventana. Es la regla `IGNORED_ALREADY_OPEN` de
  P6 aplicada por activo. **Depende de la fecha de salida, que es un desenlace**, así que solo se aplica
  dentro de la ejecución decisoria (§6.3 y §12). Se publican el número de señales ejecutables, el de
  ventanas abiertas y el de señales ignoradas.
- **Elegibilidad temporal:** la sesión de análisis `s_i` es posterior a la última sesión de la cosecha
  consumida en la plaza de `a`, es decir, `s_i > 2026-08-27` en hora local de la plaza. Por tanto
  `e_i ≥ T0(a)`, la primera sesión de `a` posterior al 2026-08-27. Las barras anteriores solo sirven como
  historia de los indicadores (SMA200, ATR, contexto) y para `μ_a^{causal}`, nunca como desenlace.
- **Universo:** el congelado de P6 (`universe_vintage_id 237b0056…`), sin altas ni bajas.

### 6.3 Ceguera durante la acumulación (corrige el BLOCKER de la revisión)

En los checkpoints, el código de captura **no aplica el no solapamiento ni procesa ninguna salida**.
Solo emite conteos que no dependen de ningún precio posterior a la apertura de `e_i`:

- señales OPERAR por política;
- **señales ejecutables** por política: las que pasan las comprobaciones de la apertura de `e_i`
  (entrada máxima, stop y objetivo válidos);
- **pares (activo, semana ISO de `e_i`) distintos con al menos una señal ejecutable**;
- semanas ISO distintas con al menos una señal ejecutable;
- calidad de datos: barras nuevas, revisiones y retrasos.

No emite `ℓ_i`, ningún exceso, ningún motivo ni fecha de salida, ni ningún recuento de ventanas
«abiertas» o «cerradas». La apertura de `e_i` es el precio de entrada, no un desenlace. La guarda se
implementa como en P6: el camino de captura no tiene acceso a barras posteriores a `e_i` para cada
señal, y el camino decisorio se ejecuta una sola vez con marca exclusiva (§12).

## 7. Datos: separación entre desarrollo y decisión, y captura forward

| Uso | Datos | Qué se permite |
|---|---|---|
| Desarrollo | Cosecha `071ddb2b…` (hasta el 2026-08-27) | Código, tests y comprobación de definiciones, con ejemplos rotulados «DESARROLLO — no decide» |
| Decisión | Desenlaces, ventanas, retornos y drift decisorios: solo sesiones ≥ `T0(a)`. Barras anteriores: solo warm-up, indicadores, contexto point-in-time y `μ_a^{causal}` (D2c), sin aportar ningún retorno decisorio | El único cálculo decisorio, en la mirada fijada en §9 |

**Mecanismo de captura (OD-T24-6):**
- **Cosechas forward congeladas** con `freeze_vintage` (la misma función de la cosecha original), en un
  checkpoint fijo el **primer día hábil de cada mes**. Cada cosecha registra su petición exacta:
  símbolos, `start`, `end`, `interval = 1d`, `auto_adjust = False`, `actions = True` y la versión de
  `yfinance`. Tiene su propio `data_vintage_id` y se archiva en `data/vintages/`, más el manifiesto y
  el hash en `evidence/`.
- **Retraso europeo:** cada cosecha deja fuera las sesiones de los últimos 5 días hábiles anteriores al
  checkpoint (datos europeos servidos con retraso; ver los pendientes de frescura). Esas sesiones
  entran en el checkpoint siguiente.
- **Revisiones:** en cada checkpoint se comparan las barras ya vistas en la cosecha anterior y se
  publica cuántas cambian. La ejecución decisoria usa **solo la cosecha decisiva** (§9), sin mezclar
  cosechas.
- **Contraste independiente:** las barras validadas de la Pi (`validated_bar`, con `observed_at`) y
  las recomendaciones C0 que emitió producción (`recommendation`) se usan **solo como contraste
  descriptivo** de integridad. No deciden.

## 8. Costes, dividendos y FX

- **Costes:** los de P6 en ambas patas de la operación. El drift **no** lleva costes: el pasivo que gana
  el drift es el buy-and-hold, que paga una sola ida y vuelta en toda la ventana. Es conservador contra
  la señal. La variante con el coste del pasivo prorrateado es descriptiva (OD-T24-4).
- **Dividendos:** en `ℓ_i` con la regla de derecho de P6 (§3), y en `g_{a,t}` por ex-date, con la misma
  fuente.
- **FX:** la métrica primaria va en **divisa local**. Operación y drift son del mismo activo y la misma
  divisa, así que el FX no interviene. La versión en EUR, con el FX causal disponible en la entrada y en
  la salida (sidecar congelado, como en P6), es descriptiva (OD-T24-5).

## 9. Ventana de referencia, capacidad y calendario de miradas (fijados antes de mirar)

**Ritmo esperado (solo recuentos publicados de P6, sin desenlaces).** En
`evidence/2026-10-05-T-023-diagnostico-post-p6/presion-capital.csv`, las señales que llegaron a la
apertura y fueron ejecutables, ENTRY + INSUFFICIENT_CASH, suman:
- B2: 673 + 7 005 = 7 678;
- S2: 528 + 319 = 847;
- C0: 623 + 241 = 864.

Repartidas en la ventana de P6, del 2022-06-14 al 2026-08-27 (≈ 50,4 meses), dan del orden de **152, 17
y 17 al mes**. Son una aproximación:
- se midieron con cartera, y `IGNORED_ALREADY_OPEN` de cartera (B2 2 284, S2 390, C0 322) descartó
  señales antes de la comprobación de ejecutabilidad;
- en T-024, el no solapamiento por activo descarta otras;
- en 2022 hubo menos señales porque la ventana arrancaba (presion-capital.csv, `por_anio`).

S2 es la política que más tarda en llegar a la capacidad.

**Propuesta (OD-T24-8):**
- **Medida de capacidad, sin desenlaces (§6.3):** `Q_p` = número de pares (activo, semana ISO de
  `e_i`) distintos con al menos una señal ejecutable, y `W_p` = número de semanas ISO distintas con
  alguna señal ejecutable.
- **Umbral por política:** `Q_p ≥ 120` y `W_p ≥ 26`.
- **Mirada 1:** el primer checkpoint mensual en que **B2 y S2** cumplan el umbral. Ese checkpoint fija
  el corte de entradas `C_e`; las señales con `e_i > C_e` no entran.
- **Mirada final** (solo para la política que en la mirada 1 dé `NO CONCLUYENTE`): corte de entradas
  `C_e^{final} = 2027-08-27`. Si en esa fecha alguna política no cumple el umbral, esa política es
  `NO EVALUABLE POR MUESTRA`.
- **Cosecha decisiva y `T1`:** para cada mirada, la cosecha decisiva es la del **primer checkpoint
  mensual posterior en al menos 75 días naturales a `C_e`**. Eso cubre 40 sesiones de cierre, los 5
  días hábiles de retraso y los festivos. `T1(a)` = la última sesión de `a` incluida en esa cosecha. Las
  ventanas que en `T1(a)` sigan abiertas se cierran con la regla final de P6 y se cuentan aparte. El
  diseño hace que deban ser excepcionales.
- **`[T0, T1]` es la referencia del drift en todas las definiciones.** En la mirada final se recalcula
  con su propia cosecha decisiva: el drift de la mirada final incluye las sesiones de la mirada 1. Esto
  se fija ahora y no se elige después.
- **Mínimo en la decisión:** si, tras el no solapamiento, una política tiene menos de **100 ventanas**,
  es `NO EVALUABLE POR MUESTRA` en esa mirada.
- Ni el umbral, ni el corte, ni el límite cambian después de ver resultados. Ninguna mirada intermedia
  emite desenlaces.
- Con el ritmo aproximado de S2, es probable que la mirada 1 llegue entre 7 y 12 meses después de `T0`.
  Si el ritmo real es menor, el límite del 2027-08-27 puede dejar a S2 `NO EVALUABLE POR MUESTRA`. Es un
  riesgo aceptado ex ante, que el propietario puede cambiar ahora, no después (OD-T24-8).

## 10. Métrica primaria, unidad, bloques e intervalo

- **Métrica primaria (por política):** `M_p` = media de `D2_i` sobre las ventanas de la política en la
  mirada (o D2o, según OD-T24-1).
- **Unidad estadística:** la ventana (señal ejecutada).
- **Excepción declarada a INV-14 (OD-T24-7).** INV-14 fija como primaria la media por bloque. Igual que
  D-69 en P6, T-024 propone decidir con la **media por ventana**. El motivo es que la ventana forward da
  unos 7–12 bloques mensuales, demasiado pocos para estimar con la media por bloque. La media por
  bloque mensual de entrada (INV-14) se publica como **descriptiva**: no veta, no rescata y no puede
  invocarse después. Si el propietario prefiere respetar INV-14, la alternativa es la media por bloque
  semanal de entrada como primaria.
- **Dependencia:** las señales se concentran en los mismos días, las ventanas de distintos activos se
  solapan hasta 40 sesiones y los activos se repiten. El intervalo se obtiene con un **bootstrap por
  bloques móviles de 4 semanas ISO de entrada consecutivas**: todas las ventanas de las semanas del
  bloque se remuestrean juntas, con B = 10 000 y semilla fija `20261005`.
- **Secundarias y descriptivas (sin veto):**
  - D2o, D2c, D3 y D4;
  - `φ_a` por política;
  - la media por bloque mensual;
  - el exceso por sesión, `Σ D2_i / Σ h_i`;
  - la versión en EUR;
  - la mediana;
  - el desglose por motivo de salida, región y mes;
  - D1, como comprobación de la implementación.

## 11. Criterio de decisión (por política, B2 y S2 por separado)

Con el intervalo `IC` de `M_p` al nivel corregido (OD-T24-9; propuesta: Bonferroni por 2 políticas
y 2 miradas posibles, lo que da un IC bilateral del 98,75 % en cada mirada):

| Etiqueta | Regla |
|---|---|
| `POSITIVO` | cota inferior del IC > `δ` |
| `NO POSITIVO` | cota superior del IC ≤ `δ` |
| `NO CONCLUYENTE` | el IC contiene `δ` |
| `NO EVALUABLE POR MUESTRA` | no se cumple la capacidad (§9) o hay menos de 100 ventanas tras el no solapamiento |

- Propuesta: `δ = 0` (OD-T24-10).
- En la mirada final, `NO CONCLUYENTE` es definitivo: no hay más miradas.
- C0 se etiqueta de forma descriptiva y no entra en la corrección ni en la interpretación.

## 12. Interpretación (fijada en D-71)

- **`POSITIVO`**: el timing de la señal aporta valor frente al drift del mismo activo. Queda
  justificado estudiar después la arquitectura de cartera, empezando por H23-02 y H23-03, con ficha y
  pre-registro propios.
- **`NO POSITIVO`**: no se optimiza la asignación para rescatarlo. La investigación vuelve a la señal,
  la salida o la arquitectura.
- **`NO CONCLUYENTE`**: se sigue acumulando hasta el límite pre-registrado, sin cambiar las reglas.
- Si B2 y S2 obtienen etiquetas distintas, cada una se interpreta por separado. T-024 no ordena una
  sobre la otra.
- Ningún resultado de T-024 cambia D-70 ni desbloquea P7 por sí mismo.

## 13. Implementación (con autorización aparte, después del pre-registro)

- Un módulo nuevo de investigación, `advisor/research/t024.py`, que no se integra en producción.
  Reutiliza en modo lectura `build_snapshot_series`, la configuración de las políticas y las reglas de
  ejecución y salida de P6. No cambia el código de P6.
- Dos caminos:
  - **captura**: conteos de §6.3. Solo recibe, por señal, las barras hasta la apertura de `e_i`, sin
    salidas ni no solapamiento;
  - **decisión**: única, con marca exclusiva `O_CREAT|O_EXCL`, identidad congelada (`T024_PREREG_SHA`,
    `T024_CODE_SHA`, los `data_vintage_id` forward y el de la cosecha decisiva) y salida en
    `evidence/…/run/`.
- **Tests obligatorios, con datos sintéticos:**
  - D1 coincide con la fórmula cerrada de §4, con y sin dividendo, y con slippage y comisión por
    separado;
  - D2 y D2o valen 0 cuando la ventana rinde exactamente el drift, en las dos convenciones de §5.2;
  - los ejemplos de §5.2, con dividendos y splits;
  - la atenuación `(1 − φ)` en un caso construido;
  - no solapamiento por activo;
  - elegibilidad temporal por plaza y zona horaria;
  - el camino de captura no recibe barras posteriores a `e_i` y no emite nada derivado de salidas;
  - las exclusiones de §5.3;
  - el bootstrap es determinista;
  - el criterio aplica bien el IC y `δ`;
  - la mirada única y la marca exclusiva funcionan.
- **Revisión de look-ahead independiente** antes de la decisión.

## 14. Riesgos y limitaciones

- **Ventana corta:** unos 12 meses de un solo régimen. Un resultado `POSITIVO` o `NO POSITIVO` habla de
  ese periodo y no generaliza sin más.
- **Sesgo de universo:** el universo se seleccionó en 2026. D2 **lo mitiga**, porque compara cada
  activo consigo mismo, pero no lo elimina en D3.
- **Atenuación de D2** cuando `φ_a` es alto (§5.1).
- **Datos:** el proveedor es `yfinance`, con revisiones y retraso europeo; las revisiones se publican y
  no se corrigen a mano.
- **Presupuesto de datos (OD-T24-11):** T-024 consume la ventana `[T0, T1]` de la mirada en que
  decide. Cualquier holdout futuro de GATE P7 para candidatas nuevas tiene que empezar después, o
  declararse ahora como compartido. Hay que decidirlo antes de congelar.
- **Visibilidad previa:** producción emitió señales C0 después del 2026-08-27 y el propietario las ha
  visto en Telegram, pero nadie ha calculado ninguna métrica de T-024 sobre ellas. Se declara.

## 15. OWNER_DECISION_REQUIRED

| OD | Decisión | Opciones | Propuesta |
|---|---|---|---|
| OD-T24-1 | Definición primaria del exceso | D2 (drift medio de `[T0, T1]`, atenuado por `1 − φ`); D2o (drift de las sesiones fuera de ventana); D2c (drift causal de 250 sesiones) | **D2**; D2o, D2c y D3 como descriptivas |
| OD-T24-2 | Políticas | B2 y S2 decisorias, C0 descriptiva; o las tres decisorias | **B2 y S2 decisorias; C0 descriptiva** |
| OD-T24-3 | Base temporal de `h_i` (§5.2) | (a) sesiones completas `x_i − e_i + 1`, penalización deliberada; (b) descomposición noche y día | **(a)**, por simple y conservadora contra la señal; (b) descriptiva |
| OD-T24-4 | Costes del pasivo | Sin costes (conservador); ida y vuelta prorrateada | **Sin costes** en la primaria; la prorrateada, descriptiva |
| OD-T24-5 | Divisa | Local (primaria) con EUR descriptiva; o EUR primaria | **Local** |
| OD-T24-6 | Captura forward | Cosechas mensuales congeladas; la caché de la Pi como fuente | **Cosechas mensuales**; la Pi, solo como contraste |
| OD-T24-7 | Estimador e intervalo | Media por ventana con excepción declarada a INV-14 y bootstrap de bloques de 4 semanas; o media por bloque semanal (respeta INV-14) | **Media por ventana**, con la excepción declarada y la media por bloque mensual como descriptiva |
| OD-T24-8 | Capacidad y límite | `Q_p ≥ 120`, `W_p ≥ 26`, mínimo de 100 ventanas en la decisión, corte final el 2027-08-27; o un límite de 18 meses (2028-02-28) | **Corte final el 2027-08-27** |
| OD-T24-9 | Multiplicidad | Bonferroni (2 políticas × 2 miradas → IC del 98,75 %); IC del 95 % por política sin corregir | **Bonferroni** |
| OD-T24-10 | Margen de relevancia | `δ = 0`; `δ` = coste de ida y vuelta (≈ 0,003) | **`δ = 0`**, con el exceso frente al coste como descriptivo |
| OD-T24-11 | Presupuesto de datos frente a P7 | T-024 consume `[T0, T1]` y P7 empieza después; o se declara compartido | **Consumido por T-024**: cualquier holdout de P7 empieza después de `T1` de la última mirada |
| OD-T24-12 | Población de todas las barras | Excluida; descriptiva | **Descriptiva** (puente, como en P6) |

## 16. Plan

1. El propietario cierra las OD-T24 en una D-nn.
2. Revisión final del pre-registro, con 0 BLOCKER y 0 IMPORTANTE → `T024_PREREG_SHA`.
3. Con autorización: código de captura y tests, sobre desarrollo, y una revisión de look-ahead.
4. Acumulación forward con checkpoints mensuales de solo conteos.
5. Con autorización: la ejecución decisoria única en la mirada 1 y, si toca, la mirada final.

## Revisión adversarial del diseño

**Ronda 1 (Codex, 2026-10-05): 2 BLOCKER y 4 IMPORTANTE, más 1 MENOR.** Correcciones:
- **BLOCKER, D1 sin dividendos:** D1 se reescribe en §4 como el retorno total del mismo intervalo, con
  los mismos dividendos y precios brutos; la fórmula cerrada depende solo de los costes y del dividendo.
- **BLOCKER, captura frente a no solapamiento:** el no solapamiento depende de las salidas, así que
  solo se aplica en la ejecución decisoria. La capacidad se mide con `Q_p` y `W_p`, que no dependen de
  desenlaces (§6.3, §9).
- **IMPORTANTE, `T1` sin cerrar:** `T1` queda fijado por la cosecha decisiva de cada mirada (§9).
- **IMPORTANTE, INV-14:** la excepción queda declarada, con la alternativa como OD (§10, OD-T24-7).
- **IMPORTANTE, ritmos:** el cálculo (ENTRY + INSUFFICIENT_CASH sobre ≈ 50,4 meses) queda explícito,
  con sus límites, y la capacidad se redefine (§9). La cifra del revisor (11–12 al mes en S2) cuenta
  solo las entradas aceptadas con cash, no las ejecutables.
- **IMPORTANTE, base temporal:** las convenciones quedan fijadas, con ejemplos sintéticos obligatorios
  (§5.2).
- **MENOR, datos insuficientes:** reglas en §5.3.
- **Añadido por Claude:** la atenuación `(1 − φ)` de D2 y la variante D2o (§5.1).

**Ronda 2 (Codex, 2026-10-05): 0 BLOCKER y 1 IMPORTANTE.** Todos los hallazgos de la ronda 1 quedan
resueltos. Las cifras de §1 y los ritmos de §9 se comprobaron contra los artefactos publicados.
- **IMPORTANTE, warm-up:** la tabla de §7 decía «barras con sesión ≥ `T0(a)`» para la decisión,
  en contradicción con el warm-up permitido en §6. Se corrige: los desenlaces, retornos y drift
  decisorios usan solo sesiones ≥ `T0(a)`, y las barras anteriores solo sirven para warm-up,
  indicadores, contexto point-in-time y D2c.

**Ronda 3 (Codex, 2026-10-05): 0 BLOCKER, 0 IMPORTANTE y 1 MENOR.**
- El arreglo del warm-up queda resuelto, sin contradicciones con §9, §10 ni §13.
- D-71 refleja la opción E de T-023 sin añadir decisiones.
- El tratamiento de `φ_a` y de D2o es suficiente para decidir OD-T24-1.
- MENOR corregido: D-71 remitía al §3 de la ficha para la degeneración, que está en el §4.
- **Veredicto: apto para que el propietario cierre las OD y se congele el pre-registro.**
