# T-024 — Edge relativo al drift: ¿la señal elige ventanas mejores que mantener el activo? (D-71)

Estado: **PRE-REGISTRO — OD-T24-1 a OD-T24-12 CERRADAS en D-72 (2026-10-05).** Pendiente: la revisión
adversarial final y la congelación de `T024_PREREG_SHA`. No se ha calculado ninguna métrica de T-024, ni
sobre la cosecha consumida ni sobre datos posteriores al 2026-08-27. No existe código de T-024 (ni
`t024.py` ni la captura). Las recomendaciones de la ficha son ahora **reglas vinculantes** con las
modificaciones de D-72: bootstrap de 10 semanas y guarda de reconfirmación de capacidad.

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

---

## 0. Identidad de partida

| | |
|---|---|
| Base | `main = d86a94e6fcbc86c7dfdb345eaf7959b9d83e91cc` (merge del PR #43, T-023) |
| Decisiones | D-71 (opción E de T-023); D-72 (cierra las OD-T24) |
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

**Qué mide exactamente (precisión de D-72).** La métrica primaria D2 **no** mide el «timing puro de la
señal». Depende de la selección de la señal, la entrada, el stop, el objetivo, la salida temporal y la
duración resultante. La afirmación permitida es:

> D2 evalúa si las ventanas del contrato activo congelado de B2/S2 (selección, ejecución y salida)
> obtienen un retorno neto superior al drift medio del mismo activo durante un número comparable de
> sesiones.

Ningún resultado se atribuye causalmente solo al score o a la señal.

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
solo de los costes y del peso relativo del dividendo; no contiene información sobre las ventanas.**
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

| Id | Exceso por ventana | Qué mide | Papel (D-72) |
|---|---|---|---|
| **D1** | `ℓ_i − π_i` (§4) | Solo costes y dividendo | **Solo comprobación de la implementación** |
| **D2** | `ℓ_i − h_i·μ_a`, con `μ_a` = media de `g_{a,t}` en todas las sesiones de `a` en `[T0, T1]` | Retorno neto de las ventanas del contrato (selección, ejecución y salida) frente al drift medio del mismo activo en un número comparable de sesiones (la referencia del buy-and-hold) | **Primaria** |
| **D2o** | `ℓ_i − h_i·μ_a^{fuera}`, con `μ_a^{fuera}` = media de `g_{a,t}` en las sesiones de `[T0, T1]` que **no** cubre ninguna ventana de `(p, a)` | Lo mismo, frente a las sesiones del mismo activo no cubiertas por ventanas | **Secundaria** |
| **D2c** | `ℓ_i − h_i·μ_a^{causal}`, con `μ_a^{causal}` = media de `g_{a,t}` en las 250 sesiones anteriores a `s_i` | Lo mismo, frente al drift reciente conocido al entrar | Descriptiva |
| **D3** | `ℓ_i − ln(I_r(x_i)/I_r(e_i − 1))`, con `I_r` el índice equiponderado total return, cierre a cierre, de los activos analizables de la región de `a` | Ventanas del contrato frente al universo equiponderado de su región | Descriptiva |
| **D4** | `ℓ_i − ln((C_{e_i+40} + D)/P_in)`: el mismo activo mantenido desde la misma entrada 40 sesiones | Si la salida corta la subida (H23-01) | Descriptiva, fuera del criterio |

### 5.1 Por qué D2 es la primaria (D-72), y su sesgo de atenuación

- Es la única que mantiene el «mismo activo» de D-71 sin ser degenerada.
- Responde al mecanismo de H23-04.
- Usa la referencia del benchmark de P6: el buy-and-hold gana el drift completo de cada activo.

Hay una identidad que la conecta con la cartera. `Σ_i ℓ_i` es lo que ganan las ventanas, y
`Σ_i h_i·μ_a` es lo que el activo habría ganado de media en ese mismo número de sesiones. Si D2 ≤ 0, las
ventanas del contrato no ganan más que el drift y ninguna asignación lo cambia. Si D2 > 0, la brecha de
cartera es compatible con un problema de participación o de asignación (H23-02 y H23-03). Que D2 sea
mayor o menor que 0 no aísla la contribución de la señal frente a la de la ejecución o la salida.

**Atenuación.** `μ_a` incluye las sesiones de las propias ventanas. Si en `(p, a)` las ventanas cubren
una fracción `φ_a` de las sesiones de `[T0, T1]`, la diferencia media entre sesiones dentro y fuera
queda multiplicada por `(1 − φ_a)` en D2, salvo por costes y por la convención de §5.2. D2 está
**sesgada hacia 0**: es más difícil obtener `POSITIVO` y también `NO POSITIVO`. Por eso se publica `φ_a`
por política y la variante D2o (secundaria, D-72), que no sufre esta atenuación pero tiene menos
sesiones de referencia cuando `φ_a` es alto.

**Limitación de D2 y D2o:** `μ_a` es ex post sobre `[T0, T1]`, igual que el benchmark. Es legítimo para
evaluar porque no decide ninguna entrada, pero no es implementable en tiempo real. D2c sí es causal,
aunque mide otra cosa: las ventanas frente al momentum reciente.

### 5.2 Base temporal: `ℓ_i` intradía frente a `μ_a` cierre a cierre (OD-T24-3, cerrada en D-72)

`ℓ_i` va de la **apertura** de `e_i` a la salida en `x_i`, que puede ser en la apertura, dentro de la
sesión o al cierre. `g_{a,t}` va de cierre a cierre. **D-72 fija la convención (a) como primaria**; la (b) se publica como
descriptiva.

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

- **Políticas decisorias:** B2 y S2. **C0** se mide como control descriptivo (OD-T24-2, D-72).
- **Señales:** población decisoria de P6, `OPERAR_score_v1_point_in_time`, con broker neutral (D-04),
  `setup_radar = OPERAR`, `setup_accion = COMPRAR` y contexto point-in-time. La generan
  `build_snapshot_series` y la configuración de cada política, sin ningún cambio.
- **Sin capital finito:** no hay `INSUFFICIENT_CASH`. Cada señal ejecutable puede abrir su ventana.
  Esto separa las ventanas de la asignación de capital.
- **No solapamiento por activo (solo en la ejecución decisoria sellada):** mientras una ventana de
  `(p, a)` está abierta, otra señal de `(p, a)` no abre ventana. Es la regla `IGNORED_ALREADY_OPEN` de
  P6 aplicada por activo. **Depende de la fecha de salida, que es un desenlace**, así que solo se aplica
  dentro de la ejecución decisoria (§6.3 y §13). Se publican el número de señales ejecutables, el de
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
señal, y el camino decisorio se ejecuta una sola vez con marca exclusiva (§13).

## 7. Datos: separación entre desarrollo y decisión, y captura forward

| Uso | Datos | Qué se permite |
|---|---|---|
| Desarrollo | Cosecha `071ddb2b…` (hasta el 2026-08-27) | Código, tests y comprobación de definiciones, con ejemplos rotulados «DESARROLLO — no decide» |
| Decisión | Desenlaces, ventanas, retornos y drift decisorios: solo sesiones ≥ `T0(a)`. Barras anteriores: solo warm-up, indicadores, contexto point-in-time y `μ_a^{causal}` (D2c), sin aportar ningún retorno decisorio | El único cálculo decisorio, en la mirada fijada en §9 |

**Mecanismo de captura (OD-T24-6, D-72):**
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
  la señal. La variante con el coste del pasivo prorrateado es descriptiva (OD-T24-4, D-72).
- **Dividendos:** en `ℓ_i` con la regla de derecho de P6 (§3), y en `g_{a,t}` por ex-date, con la misma
  fuente.
- **FX:** la métrica primaria va en **divisa local**. Operación y drift son del mismo activo y la misma
  divisa, así que el FX no interviene. La versión en EUR, con el FX causal disponible en la entrada y en
  la salida (sidecar congelado, como en P6), es descriptiva (OD-T24-5, D-72).

## 9. Ventana de referencia, capacidad y calendario de miradas (D-72; fijados antes de mirar)

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

**Medida de capacidad, sin desenlaces (§6.3):**
- `Q_p` = número de pares (activo, semana ISO de `e_i`) distintos con al menos una señal ejecutable y
  `e_i ≤ C_e`;
- `W_p` = número de semanas ISO distintas con alguna señal ejecutable y `e_i ≤ C_e`;
- **umbral por política:** `Q_p ≥ 120` y `W_p ≥ 26`.

**Calendario de miradas:**
1. **Propuesta de mirada.** El primer checkpoint mensual en que, con su cosecha forward, **B2 y S2**
   cumplen el umbral **propone** abrir la mirada 1 y fija el corte de entradas `C_e` en ese checkpoint.
   El checkpoint no abre nada.
2. **Cosecha decisiva.** La cosecha decisiva de una mirada es la del **primer checkpoint mensual
   posterior en al menos 75 días naturales a `C_e`**. Eso cubre 40 sesiones de cierre, los 5 días
   hábiles de retraso y los festivos. `T1(a)` = la última sesión de `a` incluida en esa cosecha.
3. **Reconfirmación de capacidad, antes de leer ningún desenlace (guarda de D-72).** La ejecución
   decisoria recalcula primero `Q_p` y `W_p` desde la cosecha decisiva, con `e_i ≤ C_e` y usando solo
   la señal y la apertura de `e_i`:
   - **Mirada 1:** si alguna de las dos políticas no cumple `Q ≥ 120` o `W ≥ 26`, **no se abre ningún
     desenlace, no se crea ni se consume la marca de la mirada y se sigue acumulando**. El siguiente
     checkpoint que vuelva a cumplir el umbral propone de nuevo la mirada 1, con un `C_e` nuevo y
     posterior. Se publica el intento fallido: fecha, `C_e`, `Q_p` y `W_p`.
   - **Mirada final:** una política que no cumpla la capacidad queda `NO EVALUABLE POR MUESTRA`.
4. **Mirada final.** Solo para la política que en la mirada 1 dé `NO CONCLUYENTE`. Su corte de entradas
   es `C_e^{final} = 2027-08-27`, con su propia cosecha decisiva (regla 2) y su propia reconfirmación
   (regla 3).
5. **Si la mirada 1 no llega a abrirse** antes de que el corte propuesto supere el 2027-08-27, la única
   mirada es la del corte 2027-08-27, que cuenta como mirada final para las dos políticas. Se aplica la
   regla 3 en su versión final. El nivel del intervalo no cambia (§11).
6. **Mínimo en la decisión:** una vez reconfirmada la capacidad y aplicado el no solapamiento dentro de
   la ejecución decisoria, una política con menos de **100 ventanas** queda `NO EVALUABLE POR MUESTRA`
   en esa mirada.
7. **`[T0, T1]` es la referencia del drift en todas las definiciones.** En la mirada final se recalcula
   con su propia cosecha decisiva, de modo que el drift de la mirada final incluye las sesiones de la
   mirada 1. Las ventanas que en `T1(a)` sigan abiertas se cierran con la regla final de P6 y se cuentan
   aparte; el diseño hace que deban ser excepcionales.
8. Ni el umbral, ni el corte, ni el límite cambian después de ver resultados. Ningún checkpoint emite
   desenlaces.

Con el ritmo aproximado de S2, es probable que la mirada 1 llegue entre 7 y 12 meses después de `T0`.
Si el ritmo real es menor, el límite del 2027-08-27 puede dejar a S2 `NO EVALUABLE POR MUESTRA`. Es un
riesgo aceptado ex ante (D-72).

## 10. Métrica primaria, unidad, bloques e intervalo (D-72)

- **Métrica primaria (por política y mirada):** `M_p = (Σ_i D2_i) / n_p`, la media de D2 sobre las
  `n_p` ventanas de la política en la mirada.
- **Unidad estadística:** la ventana (señal ejecutada).
- **Excepción explícita a INV-14 (D-72).** INV-14 fija como primaria la media por bloque. Igual que
  D-69 en P6, T-024 decide con la **media por ventana**. El motivo es que la ventana forward da unos
  7–12 bloques mensuales, demasiado pocos para estimar con la media por bloque. La media por bloque
  mensual de entrada (INV-14) se publica como **descriptiva**: no veta, no rescata y no puede invocarse
  después.
- **Intervalo: bootstrap de bloques móviles de 10 semanas ISO de entrada (D-72).**
  - **Secuencia:** las semanas ISO consecutivas desde la de la primera `e_i` hasta la de la última
    `e_i ≤ C_e`, ambas incluidas. Se incluyen también las semanas sin ninguna ventana. Sea `K` su
    número.
  - **Bloques:** los `K − 9` bloques de 10 semanas consecutivas, sin circularidad. Si `K < 10`, la
    política no cumple `W ≥ 26`, así que el caso no se da.
  - **Réplica:** se sortean con reemplazo `⌈K/10⌉` bloques, se concatenan y se trunca a las primeras `K`
    semanas. Todas las ventanas cuyas semanas de entrada caen en las semanas seleccionadas entran juntas,
    con sus repeticiones.
  - **Estadístico de la réplica:** `M_p* = Σ D2_i / n*` sobre las ventanas de la réplica. Una réplica
    sin ventanas se descarta y se sustituye, y se publica el número de sustituciones.
  - `B = 10 000`, generador `numpy.random.default_rng(20261005)` y el mismo esquema para B2 y S2.
  - **IC bilateral del 98,75 % por percentiles:** cuantiles 0,00625 y 0,99375 de las `M_p*`, con el
    método `numpy.quantile(..., method="linear")`.
- **Secundaria (D-72):** D2o, con el mismo intervalo. **Descriptivas y sin veto:**
  - D2c, D3 y D4;
  - la convención (b) de §5.2;
  - el drift con el coste del pasivo prorrateado;
  - `φ_a` por política;
  - la media por bloque mensual;
  - el exceso por sesión, `Σ D2_i / Σ h_i`;
  - la versión en EUR;
  - la mediana;
  - el desglose por motivo de salida, región y mes;
  - la comparación con el coste de ida y vuelta;
  - la población de todas las barras (OD-T24-12);
  - D1, como comprobación de la implementación.

## 11. Criterio de decisión (D-72; por política, B2 y S2 por separado)

Con el IC bilateral del **98,75 %** de `M_p` (Bonferroni: 2 políticas × un máximo de 2 miradas; nivel
fijo aunque solo haya una mirada) y **`δ = 0`**:

| Etiqueta | Regla |
|---|---|
| `POSITIVO` | cota inferior del IC > 0 |
| `NO POSITIVO` | cota superior del IC ≤ 0 |
| `NO CONCLUYENTE` | el IC contiene el 0 (cota inferior ≤ 0 < cota superior) |
| `NO EVALUABLE POR MUESTRA` | no se cumple la capacidad en la mirada final (§9, regla 3) o hay menos de 100 ventanas tras el no solapamiento (§9, regla 6) |

- El retorno de la operación ya incorpora sus costes y el drift primario no. No se exige ningún otro
  margen. La lectura frente al coste de ida y vuelta es descriptiva.
- En la mirada final, `NO CONCLUYENTE` es definitivo: no hay más miradas.
- C0 se etiqueta de forma descriptiva y no entra en la corrección ni en la interpretación.
- D2o y las descriptivas no cambian la etiqueta.

## 12. Interpretación (D-71 con la precisión de D-72)

- **`POSITIVO`**: las ventanas activas bajo el contrato congelado (selección, ejecución y salida)
  muestran edge frente al drift. Esto justifica investigar después la capa de cartera, empezando por
  H23-02 y H23-03, con ficha y pre-registro propios.
- **`NO POSITIVO`**: el conjunto de señal más ejecución y salida no demuestra edge frente al drift. No
  se optimiza la asignación de cartera para rescatarlo; la investigación vuelve a la señal, la salida o
  la arquitectura.
- **`NO CONCLUYENTE`**: se aplica únicamente el calendario de miradas ya fijado (§9).
- **`NO EVALUABLE POR MUESTRA`**: capacidad insuficiente.
- Ningún resultado positivo o negativo se atribuye causalmente solo al score o a la señal.
- Si B2 y S2 obtienen etiquetas distintas, cada una se interpreta por separado. T-024 no ordena una
  sobre la otra.
- Ningún resultado de T-024 cambia D-70 ni desbloquea P7 por sí mismo.

## 13. Implementación (con autorización aparte, después de la congelación)

- Un módulo nuevo de investigación, `advisor/research/t024.py`, que no se integra en producción.
  Reutiliza en modo lectura `build_snapshot_series`, la configuración de las políticas y las reglas de
  ejecución y salida de P6. No cambia el código de P6.
- Tres caminos:
  - **captura**: conteos de §6.3. Solo recibe, por señal, las barras hasta la apertura de `e_i`, sin
    salidas ni no solapamiento;
  - **reconfirmación de capacidad** (§9, regla 3): igual de ciega que la captura, sobre la cosecha
    decisiva. Si falla en la mirada 1, termina sin crear ninguna marca;
  - **decisión**: solo si la reconfirmación pasa. Es única por mirada, con marca exclusiva
    `O_CREAT|O_EXCL` escrita antes de abrir desenlaces, identidad congelada (`T024_PREREG_SHA`,
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
  - el camino de captura y el de reconfirmación no reciben barras posteriores a `e_i` y no emiten nada
    derivado de salidas;
  - una reconfirmación fallida en la mirada 1 no crea marca, no abre desenlaces y deja proponer de
    nuevo; en la mirada final da `NO EVALUABLE POR MUESTRA`;
  - las exclusiones de §5.3;
  - el bootstrap de 10 semanas: secuencia con semanas vacías, `K − 9` bloques, truncado a `K`,
    sustitución de réplicas vacías y determinismo con la semilla;
  - el criterio aplica bien el IC del 98,75 % y `δ = 0`;
  - la mirada única y la marca exclusiva funcionan.
- **Revisión de look-ahead independiente** antes de la decisión.

## 14. Riesgos y limitaciones

- **Ventana corta:** unos 12 meses de un solo régimen. Un resultado `POSITIVO` o `NO POSITIVO` habla de
  ese periodo y no generaliza sin más.
- **Pocos bloques:** con `W` entre 26 y 52 semanas, los bloques de 10 semanas dan de 3 a 5 bloques por
  réplica. El intervalo es más ancho y su cobertura, menos precisa, de modo que sube la probabilidad
  de `NO CONCLUYENTE`. Es el coste aceptado de respetar la dependencia de las ventanas de hasta 40
  sesiones (D-72).
- **Sesgo de universo:** el universo se seleccionó en 2026. D2 **lo mitiga**, porque compara cada
  activo consigo mismo, pero no lo elimina en D3.
- **Atenuación de D2** cuando `φ_a` es alto (§5.1).
- **Datos:** el proveedor es `yfinance`, con revisiones y retraso europeo; las revisiones se publican y
  no se corrigen a mano.
- **Presupuesto de datos (OD-T24-11, D-72):** T-024 consume `[T0, T1]`. Cualquier holdout futuro de
  GATE P7 debe empezar **después del `T1` de la última mirada que use T-024**.
- **Visibilidad previa:** producción emitió señales C0 después del 2026-08-27 y el propietario las ha
  visto en Telegram, pero nadie ha calculado ninguna métrica de T-024 sobre ellas. Se declara.

## 15. Decisiones (OD-T24-1 a OD-T24-12 CERRADAS en D-72)

| OD | Decisión |
|---|---|
| OD-T24-1 | D2 primaria; D2o secundaria; D2c, D3 y D4 descriptivas; D1 solo como comprobación de la implementación |
| OD-T24-2 | B2 y S2 decisorias; C0 descriptiva |
| OD-T24-3 | Convención (a), sesiones completas, primaria; (b) noche y día, descriptiva |
| OD-T24-4 | Drift primario sin costes; coste del pasivo prorrateado, descriptivo |
| OD-T24-5 | Divisa local primaria; EUR descriptivo |
| OD-T24-6 | Cosechas forward mensuales congeladas; la Pi, solo como contraste de integridad |
| OD-T24-7 | Media por ventana, con excepción explícita a INV-14; bootstrap de **bloques móviles de 10 semanas ISO de entrada**, `B = 10 000`, semilla `20261005`; media por bloque mensual descriptiva |
| OD-T24-8 | `Q_p ≥ 120`, `W_p ≥ 26`, mínimo de 100 ventanas tras el no solapamiento, corte final el 2027-08-27, y **reconfirmación de la capacidad en la cosecha decisiva antes de leer desenlaces** (§9) |
| OD-T24-9 | Bonferroni: IC bilateral del 98,75 % por política y mirada |
| OD-T24-10 | `δ = 0`; la comparación con el coste de ida y vuelta es descriptiva |
| OD-T24-11 | T-024 consume `[T0, T1]`; cualquier holdout de P7 empieza después del `T1` de la última mirada |
| OD-T24-12 | Población de todas las barras solo descriptiva |

## 16. Plan

1. ~~El propietario cierra las OD-T24~~ → D-72.
2. Revisión adversarial final del pre-registro completo, con 0 BLOCKER y 0 IMPORTANTE → congelación
   en un commit documental nuevo, cuyo HEAD es `T024_PREREG_SHA`.
3. Con autorización aparte: el código de captura y de reconfirmación, y los tests, sobre desarrollo,
   más una revisión de look-ahead → `T024_CODE_SHA`.
4. Acumulación forward con checkpoints mensuales de solo conteos.
5. Con autorización aparte: la ejecución decisoria única de la mirada 1 y, si toca, la mirada final.

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
