# T-020 — P4 Geometría: stop, objetivo y holgura de entrada, con pre-registro (A-04)

Estado: **PRE-REGISTRO — OD cerradas el 2026-10-01 (D-63).** P4 **NO se ha ejecutado**, y no se ha
calculado ningún resultado de ninguna variante: ni expectancy, ni `net_R`, ni PF, ni MAE/MFE, ni ΔR,
ni intervalos, ni heterogeneidad. Las cifras de esta ficha son de cuatro tipos:
- algebraicas, derivadas de las fórmulas de `advisor/analysis/levels.py`;
- el **censo de la población de P4**, calculado sin desenlaces (`evidence/2026-10-01-T-020-censo-p4/`);
- recuentos de primitivas en el instante de la señal, de la revisión de la ficha;
- resultados **anteriores** declarados como exposición previa (sección 7.1).

El primer borrador (`8512b0e`) proponía las OD-P4-1 a OD-P4-13. El propietario las cerró en
**D-63**, y esta versión aplica esas decisiones. Las alternativas no elegidas se conservan como
historial en la sección 27. El candidato a **`P4_PREREG_SHA`** es el HEAD documental que quede
después de la tercera revisión independiente y de sus correcciones (sección «Revisión de la
ficha»).

Agente: Claude (inventario y ficha) → revisión independiente de la ficha → propietario (OD-P4-x)
→ implementación (Codex programa y Claude supervisa) → revisión de look-ahead → una ejecución.
Línea / fase: Línea A, A-04 (P4).
Gate al que contribuye: **GATE P4** (es la tarea que lo cruza).
_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

---

## 1. Objetivo

Comparar un número pequeño de geometrías (stop y objetivo 2) y una política de entrada contra la
vigente:
- **pareadas por `signal_id`**, sobre la misma cosecha congelada;
- con el estimador primario de INV-14 / D-03 (media por bloque del R neto);
- con bootstrap por bloques temporales completos (P2.6);
- **midiendo explícitamente la holgura de entrada que D-06 dejó pendiente**.

**La salida tiene tres partes:**
- el conjunto, quizá vacío, de geometrías **B2, S1 y S2** que cumplen el criterio de la sección 22
  y pasan a P5 como candidatas;
- el resultado propio de **E1** (entrada a la apertura frente a entrada al cierre, bajo C0), que no
  selecciona geometría;
- la publicación **descriptiva** de **B1**, que cierra el pendiente de D-02.

**Si ninguna geometría cumple, la geometría actual permanece**, y ese es un resultado válido. P4
no cambia producción.

## 2. Pregunta causal

Dado el mismo conjunto de señales, con el mismo instante de señal y la misma trayectoria futura,
¿cambiar **solo** la geometría (dónde se pone el stop, dónde el objetivo que cierra la posición y
cuánto puede pagarse de más al entrar sin violar el RR mínimo) cambia el R neto por señal de forma:
- estable en el tiempo;
- no atribuible a un solo régimen o mercado;
- robusta a la ambigüedad intrabarra;
- con su efecto sobre la ejecutabilidad publicado (sección 18)?

El pareado por `signal_id` hace que la única diferencia entre A y B sea la geometría: misma
entrada, misma trayectoria y mismas barras.

Se separan tres preguntas:
- **P4-A, stop.** ¿Cambiar el ancho del stop **bajo la regla E** mejora el R neto? Con stop por
  volatilidad, el objetivo 2 escala para mantener el RR y la holgura; con soporte, la comparabilidad
  se rompe, y por eso se descompone por `stop_basis` (sección 7).
- **P4-B, objetivo.** ¿Cambiar el objetivo 2 mejora la geometría económica y abre holgura de
  entrada? Incluye obligatoriamente el objetivo 2 a 3,5·ATR (D-02).
- **P4-C, entrada.** Tiene dos partes:
  - **E1:** ¿la política de entrada de producción (entrar a la apertura siguiente con veto
    `ABOVE_MAX_ENTRY`) cambia el R neto por señal frente a entrar al cierre, con la geometría C0?
  - **Holgura:** ¿cuánta persecución de precio admite cada geometría manteniendo el RR mínimo? Se
    mide la **holgura efectiva** (`entry_max − price`), no el parámetro nominal `entry_max_atr`
  (sección 18).

## 3. Dependencias

- **GATE P3 cruzado** (D-62). P4 trabaja sobre `score_signal` sin umbrales operativos (D-45.6,
  D-62). En esta ficha, `score_signal` es la **población de señales del event study, sin filtrar
  por ningún score ni por `classify()`** (sección 8).
- **P2.0 a P2.6:** cosecha congelada, primitivas de `SignalObservation`, event study administrado,
  capacidad P2.5 e infraestructura pareada P2.6 (`advisor/research/uncertainty.py` y
  `bootstrap.py`).
- **Decisiones vinculantes:**
  - **D-02:** la opción B, objetivo 2 a 3,5·ATR, quedó pendiente para P4;
  - **D-03 / INV-14:** estimador primario;
  - **D-06:** la holgura de entrada es una dimensión de la geometría;
  - **D-43:** el RR sigue siendo condición de ejecutabilidad;
  - **D-47:** producción en v1 hasta la transición atómica;
  - **D-62 y regla 7 del protocolo:** P3 consumió la cosecha entera, así que ninguna parte de ella
    puede ser holdout de P7. INV-15 añade que el holdout se consulta una sola vez.

## 4. Estado de producción y lo que P4 no cambia

- Producción usa Score v1, 70/60 y `calibrated: false` (D-47). `config.yaml` está en `"1.0"` y la
  Pi en `v0.4.1` = `8b2dddb`.
- P4 **no** cambia `config.yaml`, no despliega y no activa Score v2.
- **No reabre P3:**
  - no recalibra Score v2 ni crea umbrales;
  - no cambia la fórmula del score;
  - no usa el signo negativo de P3 para elegir geometrías;
  - el score no selecciona señales ni variantes.
- La geometría que salga de P4 es **de desarrollo**. Pasa a P5 y P6, y solo P7 (con datos
  posteriores u holdout) puede validarla (INV-15). Ningún resultado de P4 se presenta como
  validación fuera de muestra.

## 5. Inventario: la geometría vigente, tal como la ejecuta el código

Verificado leyendo el código y `config.yaml` en `a15e695`.

### 5.1 Parámetros

| Parámetro | Valor | Fuente |
|---|---|---|
| `levels.atr_stop_multiple` | **2.0** | `config.yaml:52`; por defecto `LevelsConfig` |
| `levels.target_atr_multiples` | **[1.5, 3.0, 5.0]** | `config.yaml:53`. El validador exige 3 valores > 0 estrictamente crecientes |
| `levels.target2_structural` | **false** | por defecto en `advisor/config.py:98`; no aparece en `config.yaml` |
| `levels.entry_max_atr` | **0.75** | `config.yaml:55` |
| `levels.entry_pullback_atr` | 0.5 | `config.yaml:54`; solo afecta a la zona ideal del informe |
| `levels.lookback_bars` | 60 | `config.yaml:51`; ventana de soportes y resistencias |
| `risk.min_rr_ratio` | **1.5** | `config.yaml:85` |
| Holgura del soporte | `_SUPPORT_BUFFER_ATR = 0.25` | constante en `levels.py` |
| Coste | **0,20 %** ida y vuelta | `COST_PCT = 0.2` en `advisor/research/p3.py:66` y por defecto `cost_pct=0.2` en `run_event_study_on_vintage` (`event_study.py:249`); no está en `config.yaml` |
| `MAX_HOLD_BARS` | swing **40**, medio 250 | `advisor/research/event_study.py:36` |

### 5.2 Cálculo (`compute_levels_from_inputs`, `advisor/analysis/levels.py`)

Con el precio `P` (cierre de señal) y `A` = ATR:

```
stop_vol      = P − s·A                                   (s = atr_stop_multiple)
soporte       = low_lookback; si stop_vol < soporte < P:
                  stop_sop = soporte − 0,25·A
stop          = stop_sop si stop_sop > stop_vol, si no stop_vol   (regla E de D-02: el soporte nunca aleja el stop)
target1       = P + m1·A, o la resistencia si P < resistencia < target1
target2       = P + m2·A   (cede ante la resistencia solo si target2_structural)
target3       = P + m3·A
entry_max_tec = P + entry_max_atr·A
entry_max_rr  = (target2 + min_rr·stop) / (1 + min_rr)
entry_max     = min(entry_max_tec, entry_max_rr)
```

`compute_levels_from_inputs` devuelve `None` sin ATR, con un stop ≤ 0 o ≥ `P`, o si el RR en
`entry_max` no alcanza `min_rr`. Con stop por volatilidad y `target2` sin estructura, esto último
no ocurre por construcción.

### 5.3 Lo que de verdad decide el resultado económico

En el event study, `evaluate_managed_event`:
- entra **al cierre de la señal** (`levels.price`);
- sale por stop, por **`target2`** o por tiempo (`MAX_HOLD_BARS`);
- **`target1` y `target3` no intervienen**.

`classify_target_stop_bar` resuelve los huecos de apertura y marca `AMBIGUOUS` cuando la vela abre
entre los niveles y toca los dos. Una salida `AMBIGUOUS` tiene `exit_price = None` y, por tanto,
`net_r_multiple = None`. `event_economics` calcula `gross_R` y `net_R = (retorno − coste) /
riesgo_pp` por separado.

La entrada a la **apertura siguiente** con veto `ABOVE_MAX_ENTRY` si `open > entry_max` es la
semántica de producción (`advisor/analysis/execution.py:72`). En el backtest la aplica la disciplina
`ENTRY_RESPECT_ENTRY_MAX`. **`ENTRY_OPEN_AT_OPEN` abre aunque la apertura sea `ABOVE_MAX_ENTRY`**:
solo rechaza `INVALID_STOP` e `INVALID_TARGET` (`advisor/backtest/engine.py:376-381`). El event
study no usa ninguna de las dos: entra al cierre.

### 5.4 Quién llama a los niveles

| Llamante | Uso |
|---|---|
| `advisor/analysis/analyzer.py:204` | producción, `compute_levels` |
| `advisor/backtest/engine.py:167` | backtest |
| `advisor/research/event_study.py:685` y `:710` | event study; comprueba además que niveles y primitivas coinciden |
| `advisor/research/event_study.py:414` | `replay_managed_population`: **reevalúa otra geometría sin recalcular las señales** |
| `advisor/analysis/execution.py` | `evaluate_trade_at_entry`: `ABOVE_MAX_ENTRY` y `RR_TOO_LOW` |

### 5.5 Primitivas congeladas

`SignalObservation` guarda, por diseño de P2.2, solo los insumos de la geometría:
`price`, `atr`, `low_lookback`, `high_lookback` y `ema_fast`, más `signal_idx` y
`signal_timestamp`. **No guarda `stop` ni los objetivos.** Con esas primitivas y la serie de
ejecución congelada, toda variante de esta ficha se recalcula sin volver a ejecutar `_signal()`. Es
lo que hace `replay_managed_population`. `ema_slow` y `sma_long` solo fijan la invalidación, que
no interviene en la salida simulada.

### 5.6 La geometría control

**C0 = `atr_stop_multiple 2.0`, `target_atr_multiples [1.5, 3.0, 5.0]`, `target2_structural
false`, `entry_max_atr 0.75`, `min_rr 1.5`, regla de soporte E y coste 0,20 %.** Coincide con lo
esperado; ninguna cifra difiere del repositorio.

## 6. Álgebra de la holgura (D-06), sin desenlaces

Con el stop por volatilidad (`stop = P − s·A`) y `target2 = P + m2·A`:

```
entry_max_rr − P = A · (m2 − min_rr·s) / (1 + min_rr)
RR en P         = m2 / s
```

Con el stop apoyado en un soporte, el riesgo efectivo `s_ef` es menor que `s` y la holgura sube a
`A·(m2 − 1,5·s_ef)/2,5`. Es la única fuente de holgura en el control. La holgura efectiva es
`min(entry_max_atr·A, entry_max_rr − P)`.

En el control: `(3,0 − 1,5·2,0)/2,5 = 0` → `entry_max = P` siempre que mande el stop por
volatilidad (D-06, hallazgo 4 del protocolo). Por eso variar solo `entry_max_atr` no cambia nada
mientras `entry_max_rr` mande, y la pregunta P4-C se resuelve a través de la geometría, no de ese
parámetro.

## 7. Rejilla definitiva (D-63)

Las columnas de RR y holgura valen **con stop por volatilidad** en los dos brazos. Con un stop
apoyado en soporte cambian; ver «La regla de soporte rompe la comparabilidad» más abajo.

| Id | Pregunta | `s` | `[m1, m2, m3]` | RR en P | Holgura RR (vol.) | Holgura efectiva (vol.) |
|---|---|---|---|---|---|---|
| **C0** | control | 2,0 | [1,5, 3,0, 5,0] | 1,50 | 0 | **0** |
| **B1** | P4-B, D-02, **solo descriptiva** | 2,0 | [1,5, **3,5**, 5,0] | 1,75 | 0,20·A | **0,20·A** |
| **B2** | P4-B, hallazgo 4 | 2,0 | [1,5, **4,875**, 5,0] | 2,44 | 0,75·A | **0,75·A** |
| **S1** | P4-A, stop estrecho a igual RR | **1,5** | [1,5, **2,25**, 5,0] | 1,50 | 0 | 0 |
| **S2** | P4-A, stop ancho a igual RR | **2,5** | [1,5, **3,75**, 5,0] | 1,50 | 0 | 0 |

**Papel de cada una (D-63):**
- **Candidatas a P5:** B2, S1 y S2. Son confirmatorias y son las únicas a las que se aplica el
  criterio de la sección 22.
- **B1:** **solo descriptiva**, con la etiqueta «previamente expuesta en esta misma cosecha; no
  confirmatoria; no elegible para sustituir C0» en toda salida. Se publica con el mismo estimador y
  los mismos estratos que las demás, pero no entra en la familia confirmatoria ni en el criterio.
  Así se cierra el pendiente de D-02 sin fingir evidencia independiente.
- **E1** no es una geometría: es la comparación confirmatoria de la entrada bajo C0 (sección
  18.1).

### Justificación de cada punto, sin resultados de P4

- **B1, objetivo 2 a 3,5·ATR.**
  - Lo exige D-02, que lo dejó formalmente pendiente para P4.
  - Algebraicamente es el primer paso que abre holgura: 0,2·A.
  - Ya se midió sobre esta misma cosecha (sección 7.1), así que queda solo descriptiva.
- **B2, objetivo 2 a 4,875·ATR.**
  - Es el **menor** objetivo con el que el RR deja de mandar y la holgura técnica de 0,75·A queda
    entera. Sale de `(m2 − 3)/2,5 = 0,75`, la cifra que el hallazgo 4 del protocolo ya publicó
    («harían falta objetivos de 4,875·ATR»).
  - Marca el extremo de la pregunta P4-C, «toda la persecución técnica admitida», y no se eligió
    por rendimiento.
  - `m3 = 5,0` sigue por encima, así que el validador se cumple.
- **S1 y S2, stop a 1,5 y 2,5·ATR, con el objetivo 2 escalado para mantener RR = 1,5 y holgura 0.**
  - Responden a P4-A, el ancho del stop bajo la regla E (ver el apartado siguiente).
  - No se puede ensanchar el stop con el objetivo fijo: con `s = 2,5` y `m2 = 3,0` el RR en P vale
    1,2, por debajo de `min_rr`, y la invariante INV-01/02 impide recomendar esa entrada. Esa
    geometría no sería una política ejecutable.
  - Escalar `m2 = 1,5·s` deja el RR y la holgura iguales que en el control **cuando el stop es por
    volatilidad en los dos brazos**. No en general: ver el apartado siguiente.
  - `±0,5·A` es el paso simétrico más pequeño alrededor de 2,0 que no se confunde con el ruido de
    la holgura del soporte (0,25·A).

### La regla de soporte rompe la comparabilidad de S1 y S2 (revisión de la ficha, I-1 e I-2)

El stop por soporte (`soporte − 0,25·A`) **no depende de `s`**: se aplica cuando el soporte cae
entre `P − (s − 0,25)·A` y `P`. Eso tiene tres consecuencias, que se ven solo con primitivas del
instante de señal y sin desenlaces:
- **El mismo stop con otro objetivo.** En una parte de las señales, S1 o S2 tienen el **mismo
  stop** que C0. La variante «de stop» solo cambia entonces el objetivo 2 (de 3,0 a 2,25 o a 3,75),
  y el RR en P deja de ser 1,5.
  - El revisor lo contó sobre 101.251 barras de la cosecha, una aproximación a la población: el
    stop es idéntico en el 11,5 % de las barras con S1 y en el 16,9 % con S2.
- **La holgura no es neutra.** El `entry_max` de S1 es **≤** el de C0 en toda señal; el de S2, B1 y
  B2 es **≥**. Con soporte, C0 tiene holgura > 0 y S1 la pierde.
- **Qué responde de verdad P4-A.** La pregunta pasa a ser **«el ancho del stop bajo la regla E»**:
  el efecto de la política, no el del stop aislado. Las salidas se descomponen por pares de
  `stop_basis` (sección 16). D-63 eligió esta lectura (OD-P4-3 = A); la alternativa de aislar el
  stop restringiendo la primaria no se adoptó.

### Descartados antes de medir, con su motivo

- **`target2_structural = true` (opción D).** Medida y descartada en D-02: reduce las operaciones
  un 85 % y su ratio no ordena. No hay razón metodológica nueva para reintroducirla.
- **Bajar `min_rr`.** Lo descartó D-06 como atajo: cambia la política sin medir y rompe la
  invariante del RR mínimo.
- **Stop 3,0·ATR con objetivo 3,0 (opción C).** Ya se vio que rompe el sistema: RR 1,0 y el veto
  lo descarta todo. Es S2 llevado más lejos; S2 cubre la dirección «stop ancho» con RR coherente.
- **Variar solo `entry_max_atr`.** Es inerte en C0, B1, S1 y S2 (sección 6). En B2 el RR deja de
  mandar justo en 0,75, así que mover `entry_max_atr` por debajo de 0,75 solo recortaría holgura.
  No forma una pregunta económica identificable aparte de la geometría. P4-C se mide como holgura
  efectiva de cada variante y con la comparación E1 bajo C0 (sección 18.1).
- **Cualquier rejilla de fuerza bruta.** El protocolo busca meseta, no máximo, y cada punto añadido
  multiplica las comparaciones.

### 7.1 Exposición previa: estas variantes no son ciegas

Esta ficha debe declararlo antes de medir:

1. **B1 ya se midió dos veces.**
   - **El 2026-08-27,** en el backtest antiguo de 21 activos: «mejora leve» con n = 4
     (`docs/ratio-beneficio-riesgo.md`).
   - **El 2026-08-31,** con `comparacion-pareada` (P2.6) sobre **esta misma cosecha `071ddb2b`**,
     con la población, el mapa de bloques y el contexto de entonces: ΔR +0,022, IC por bloque por
     encima de 0 en 40/60/80/120 y **heterogeneidad alta** en las cuatro longitudes. Veredicto
     NO CONCLUYENTE (`docs/pendientes.md` §15).
2. **La dirección «stop ancho sin subir objetivos» (C) también se vio:** rompe el sistema.
3. **S1, S2 y B2 no se han medido nunca como variantes pareadas.** Sí tienen antecedentes, que
   hay que declarar:
   - **B2:** el 4,875 es una cifra algebraica del hallazgo 4 del protocolo.
   - **S1:** la dirección «stop más estrecho» se discutió en `docs/ratio-beneficio-riesgo.md:112`
     (opción C, de 2,0 a 1,5).
   - **Stop ancho:** el incidente de julio del proyecto `trading-bot` (stops en cadena) forma parte
     de la experiencia previa del propietario sobre el ancho del stop.
4. **Ya está publicado sobre esta cosecha el comportamiento de C0:**
   - el event study de A-02, con `P(objetivo antes de stop)` y la mediana de la «MFE sin objetivo»
     por banda, con stop 2·ATR. Esa MFE informa directamente sobre dónde acaban los objetivos de B1
     y B2;
   - P3, con primarios por región y por activo.
5. **B1 informa del sentido de B2.** El punto exacto 4,875 no se ha medido nunca, pero hay
   exposición previa a B1 en la misma dirección. **B2 no se llama ciega del todo** en ninguna
   salida, y una lectura «meseta B1 + B2» solo es ciega a medias. Esa lectura es descriptiva y **no
   interviene en el criterio de B2** (sección 22).

Consecuencia: la conclusión sobre B1 no es ciega, y por eso D-63 la deja **solo descriptiva** (OD-P4-1
= B).

## 8. Población (D-63, OD-P4-2 = C)

- **Cosecha:** `data_vintage_id = 071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841`.
- **Universo:** `universe_vintage_id = 237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19`
  (vigente, 93 analizables).
- **Señales:** la **población de A-02 en swing sin cripto**.
  - Son todas las barras elegibles del event study: sin `classify()`, sin estado de posición, con
    solapamiento, con `warmup` = `min_bars` del horizonte y como máximo 40 barras.
  - Se enumeran con `run_event_study_on_vintage(swing, score_model_version="1.0")`, como A-02,
    con los evaluadores de desenlace sustituidos por funciones que devuelven `None`.
  - El modo de contexto solo cambia el score, que P4 no lee. En ese modo ninguna señal se descarta
    por contexto.
  - **Ningún score selecciona**: ni v1, ni v2, ni sus umbrales.
- **Sin las exclusiones de P3.** No se aplican las de Asia no calculable (D-52) ni las de la
  historia de la SMA200 (D-55). Son requisitos del contexto de Score v2, no de la geometría, y P4 no
  usa `build_population` de P3.
- **Cripto fuera (D-51).** En las plazas 24/7 la apertura siguiente coincide con el cierre, así que
  la entrada y la holgura D-06 pierden sentido.

### 8.0 Censo congelado sin desenlaces

Script y salida en `evidence/2026-10-01-T-020-censo-p4/`. El script se para si los recuentos no
coinciden exactamente.

| | Valor |
|---|---|
| A-02 swing | 106.363 |
| − cripto (`BTC-EUR`, `ETH-EUR`, `SOL-EUR`) | −5.112 |
| **Población de P4** | **101.251** señales, **90** activos |
| **`p4_population_sha256`** (activo y sesión de plaza, como en P3) | `78024050f7081ad4e1dd5cefaefbfa1a1668ff5b1a2ced8c34e62b6501873141` |
| sha256 de los `signal_id` ordenados | `9faa4a45beaba3eb8dafabf7990906cd8c89e8e06ae2f25edec7839cd48e629f` |
| Regiones | ASIA 17.953, EUROPA 34.622, USA 44.898, GLOBAL 2.627, EMERGING_MARKETS 1.151 |
| Espina de sesiones | 1.302 sesiones de bolsa (sin cripto) |
| Régimen PIT | RISK_ON 73.719, CAUTELA 12.431, RISK_OFF 7.944, **NO_CALCULABLE_CONTEXT 7.157** (Asia ausente 396, historia de la SMA200 6.937; algunas tienen los dos códigos) |

El preflight de la implementación tendrá que reproducir exactamente el tamaño y los dos hashes. Si
no los reproduce, **STOP**.

### 8.1 `signal_id` y emparejamiento

- `signal_id` = `"{asset}|{horizonte}|{signal_timestamp_raw}"`, el de `SignalObservation`. Es único
  por activo y barra.
- Para cada variante V, `replay_managed_population` recalcula los niveles desde las primitivas del
  mismo `signal_id` y simula sobre la misma serie de ejecución.
- `ΔR_i = net_R_V,i − net_R_C0,i`.
- **Se espera un emparejamiento casi completo, pero no está garantizado.** Por ejemplo, S2 da
  `None` si `ATR/P ≥ 0,4` sin soporte, porque el stop quedaría ≤ 0. La revisión contó 0 casos sobre
  101.251 barras con primitivas. El preflight, sin desenlaces, **cuenta por variante** los
  `signal_id` sin niveles y su motivo; nunca los descarta en silencio, y salen del par. La
  condición 9 de la sección 22 actúa como guarda.
- Los pares que no se pueden calcular por `AMBIGUOUS` se tratan en la sección 17.

## 9. Geometría recalculable

Todas las variantes se derivan de la misma tabla de observaciones y de la misma serie de ejecución.
No se recalcula ningún indicador. `compute_levels_from_inputs` recibe el `LevelsConfig` de la
variante y el mismo `min_rr`. Un test de identidad exige que la réplica de C0 reproduzca
exactamente el `ManagedEvent` original de cada señal (sección 23).

## 10. Métrica primaria

**Media por bloque de ΔR neto** (INV-14 / D-03, P2.6):
1. se calcula `ΔR_i` por `signal_id`;
2. se agrupa por bloque temporal completo (todas las señales de todos los activos de esa ventana);
3. se calcula la media de ΔR dentro de cada bloque;
4. la estimación es la media simple de esas medias de bloque.

El IC sale de un bootstrap sobre **bloques completos**, nunca sobre operaciones sueltas.
Convención: ΔR > 0 significa que la variante gana más R neto que C0 sobre las mismas señales.

## 11. Secundarias (descriptivas; no deciden solas)

Por variante, con el mismo estimador. **Solo el primario de nivel lleva IC** (del 95 %) y cuenta
como comparación. **Todas las demás secundarias son puntuales, sin IC**, y no cuentan:
- primario de nivel (media por bloque de `net_R`), **con IC del 95 %**;
- media agrupada de ΔR;
- `P(objetivo antes que stop)` como intervalo `[seguros, seguros + ambiguos]` (P2.3);
- tasa de salida por tiempo y `EXIT_FINAL`;
- MAE de las ganadoras;
- MFE potencial (`evaluate_potential_event`, que solo depende del stop);
- `gross_R` **solo como diagnóstico geométrico**, nunca en la misma conclusión que `net_R`;
- tasa de acierto, solo como contexto;
- PF agrupado de cada geometría, como contexto. El PF de V es además parte de la condición 10, la
  regla 2 del protocolo.

## 12. Costes

`net_R` con un coste de **0,20 % ida y vuelta**, el valor pre-registrado de P2/P3, verificado en el
código (sección 5.1). Toda conclusión económica es en R neto. `gross_R` se publica aparte, rotulado
como diagnóstico.

## 13. Bloques (D-63, OD-P4-6 = A)

Sobre la espina de 1.302 sesiones de la población de P4, calculado sin desenlaces en el censo:

| Longitud | Bloques en la espina | Bloques ocupados | Bloque ocupado más corto | Válida (P2.5: > 40) | Papel |
|---|---|---|---|---|---|
| 40 | 33 | 30 | 22 | **no** | publicada, marcada inválida; fuera de toda condición |
| **60** | 22 | **20** (del 2 al 21) | 42 | sí | **primaria** |
| 80 | 17 | 16 | 22 | **no** | publicada, marcada inválida; fuera de toda condición |
| 120 | 11 | 10 | 102 | sí | sensibilidad válida |

La primaria **no hereda los 19 bloques de P3**: la población de P4 tiene 20 bloques ocupados con 60
sesiones. Con 120 sesiones hay 10 bloques, por debajo de los 12 de `limited_blocks`. Por eso la
condición 2 lee su signo y su IC, pero la capacidad (condición 3) se exige solo en la primaria.

## 14. Bootstrap (congelado antes de medir)

Contrato P2.6 vigente (`advisor/research/bootstrap.py`), verificado en el código:

| Elemento | Valor |
|---|---|
| Unidad | bloque temporal completo (todos los activos dentro), con reemplazo |
| Semilla | **20260830**; `seed_ci = seed·1.000.003 + 97` y `seed_het = seed·1.000.003 + 194` |
| Remuestreos | **2.000** (`DEFAULT_RESAMPLES`) para los IC del 95 % y la heterogeneidad |
| Nivel del IC | **0,95**, por cuantiles (implementación propia) |
| Ruido para heterogeneidad | 0,90 |
| Confirmatorio (D-63, OD-P4-7 = A) | familia de **`m = 4`** (B2, S1, S2 y E1). Bonferroni con `confidence = 1 − 0,05/4 = 0,9875`, **20.000** remuestreos y la misma semilla 20260830, en la longitud 60. B1 queda fuera de la familia |
| Bloques sin pares | no entran en el bootstrap; se publica cuántos y cuáles (`n_blocks` = bloques con al menos un par) |
| Bloques con < 5 pares | se publican; activan la condición de capacidad de la sección 22 (`min_observations_per_block` = 5) |

Los 20.000 remuestreos se aplican **solo** al intervalo corregido de las cuatro confirmatorias.
Todo lo demás usa el contrato P2.6 (2.000, 95 %).

## 15. Robustez temporal interna sobre datos de desarrollo (D-63, OD-P4-10 = B)

**P4 no constituye validación temporal.** El protocolo original pedía validación temporal en P4 y
P5 («la comparación se hace ya bajo validación temporal»). Pero esta cosecha ya fue consumida (D-62
y regla 7 del protocolo), y no hay ningún holdout sin consumir. **Esta desviación del protocolo
queda declarada formalmente en D-63.** La validación temporal independiente sigue en P7, bajo
INV-15.

Lo que P4 sí hace es una **robustez temporal interna sobre datos de desarrollo**, la condición 8:
- se toman los **20 bloques ocupados** de la primaria (60 sesiones), en orden temporal;
- se parten en dos mitades **pre-registradas**: los 10 primeros (bloques 2 a 11) y los 10 últimos
  (bloques 12 a 21);
- en cada mitad, la media por bloque de ΔR debe ser > 0.

Es un veto de robustez dentro del desarrollo, no una validación, y nunca se llama así en ninguna
salida.

## 16. Heterogeneidad

**Instrumento.** El de P2.6, sin cambios:
- se compara la desviación típica observada de las medias de bloque con el intervalo del 90 % de
  esa misma desviación bajo un efecto verdadero constante, que se estima remuestreando sesiones
  dentro de cada bloque recentrado;
- el resultado es **BAJA / COMPATIBLE CON RUIDO / ALTA**, o NO ESTIMABLE;
- se publica también τ, el exceso de dispersión.

Esto separa la dispersión compatible con ruido de la heterogeneidad real.

**Estratos pre-registrados** (descriptivos), solo para las geometrías B1, B2, S1 y S2, **no para E1**
(sección 18.1):
- **bloque temporal:** las **20 medias** de ΔR, una por bloque ocupado (del 2 al 21). Son
  **puntos sin IC**: un solo bloque no admite el bootstrap de bloques completos. No cuentan como
  comparaciones (sección 20);
- **los demás estratos** (región, activo, régimen, volatilidad y `stop_basis`) llevan cada uno su ΔR
  por bloque y su IC del 95 % (2.000 remuestreos) y cuentan en la sección 20:
- **región:** ASIA, EUROPA, USA, GLOBAL y EMERGING_MARKETS;
- **activo:** los 90, descriptivo;
- **régimen:** la etiqueta point-in-time de `MarketContext` en el `analysis_timestamp` de la señal
  (`RISK_ON` / `CAUTELA` / `RISK_OFF`). Ya está congelada y es causal (D-50, D-53).
  - Solo se estratifican las señales con contexto calculable.
  - Las **7.157** con `NO_CALCULABLE_CONTEXT` (censo) **no se quitan de la primaria ni de ningún
    otro análisis**: se publica su número aparte y no se les inventa ningún régimen;
- **volatilidad:** terciles de `atr/price` en la señal, con cortes nearest-rank sobre la población.
  Solo usan insumos del instante de señal; se fijan en el preflight, sin desenlaces;
- **base del stop, solo para S1 y S2:** el par `stop_basis` (C0, V) — volatilidad/volatilidad,
  soporte/soporte o mixto. Sale de las primitivas en el preflight. Separa la parte de ΔR que
  corresponde al ancho del stop de la que corresponde a un cambio de objetivo con el mismo stop
  (sección 7). En B1 y B2 el stop es idéntico al de C0, así que no aplica.

**El instrumento puede confundir dependencia con heterogeneidad** (revisión de la ficha, B-1). El
ruido «bajo efecto constante» remuestrea **sesiones como si fueran independientes** dentro de cada
bloque. En swing, las señales de sesiones contiguas comparten hasta 40 barras de trayectoria, así
que su ΔR está autocorrelado y el instrumento infravalora la dispersión esperable. El revisor lo
mostró con datos sintéticos, sin datos reales: con un efecto constante y un factor común con un
solapamiento de 40, dio ALTA en 20 de 20 réplicas; con ruido independiente, COMPATIBLE en 10 de 10.

**Papel en P4 (D-63, OD-P4-12 = B):** la heterogeneidad es una **bandera obligatoria, no un veto**.
- Se publica siempre, para cada comparación, E1 incluida.
- **Si sale ALTA en B1, B2, S1 o S2**, antes de cerrar GATE P4 hay que publicar y discutir los
  estratos pre-registrados: región, régimen, volatilidad, activo y, en S1 y S2, `stop_basis`. Esos
  estratos ya se calculan siempre para las geometrías, así que la ALTA no añade ninguna estimación.
- **En E1 la bandera se publica sin estratos**, aunque salga ALTA. E1 no se elige ni selecciona
  nada, así que el requisito 2 del gate («ninguna se elige por el promedio… sin explicar») no la
  alcanza. Calcular estratos de E1 añadiría comparaciones que D-63 no prevé.
- En P4 no se permite crear una política condicionada por estrato.
- **ALTA por sí sola no aprueba ni veta una variante.**
- No hay calibración sintética que convierta la bandera en veto.
- **FOLLOW_UP:** revisar un instrumento que respete la dependencia por solapamiento antes de darle
  función de veto en una fase posterior. Queda registrado en `docs/roadmap.md` («Hallazgos
  abiertos») y en D-63.

## 17. Ambigüedad OHLC

- Se conserva el contrato de P2.3: `AMBIGUOUS` es un estado, no se resuelve. El modo administrado
  no le asigna `net_R`.
- **Primaria:** pares con `net_R` observable en las dos geometrías (`pair_populations`). Se publica
  cuántas señales salen por ambigüedad solo en C0, solo en V o en las dos (`dropped_only_a`,
  `dropped_only_b`, `dropped_both`).
- **Sesgo conocido.** La tasa de ambigüedad cambia con la geometría: un stop más estrecho o un
  objetivo más cercano tocan los dos niveles más a menudo. Excluir los pares es, por tanto,
  diferencial.
- **Cotas pre-registradas.** Para conservar la incertidumbre se recalcula ΔR con cada `AMBIGUOUS`
  resuelto de las dos maneras extremas, sin elegir:
  - **cota conservadora para V:** las ambiguas de V salen por stop (`exit = stop`) y las de C0 por
    objetivo (`exit = target2`);
  - **cota favorable a V:** al revés.

  Las dos se publican con el mismo estimador. Ninguna resolución intrabarra se elige después.
- **Las cotas no son siempre factibles a la vez** (revisión, M-6). Si una misma vela es ambigua en
  los dos brazos con niveles anidados, la combinación de una cota puede no ser una trayectoria
  posible: por ejemplo, con el mismo stop, «V por stop y C0 por objetivo». Por eso las cotas son
  **envolventes**, no escenarios. Se publica cuántos pares tienen la vela ambigua compartida. En C0
  la tasa publicada es de 25 `AMBIGUOUS` sobre 106.363 (A-02), y las variantes se cuentan en el
  preflight solo como recuento de estados, nunca como `net_R`.
- Si la tasa de descarte supera el 25 % (`max_ambiguous_rate`), la comparación es NO CONCLUYENTE
  por capacidad.

## 18. Holgura de entrada (D-06) y `ABOVE_MAX_ENTRY`

Se mide para **cada** geometría (C0, B1, B2, S1, S2), sobre todas las señales de la población. Es
un requisito explícito de GATE P4.

| Medida | Definición |
|---|---|
| Holgura RR | `entry_max_rr − P`, en precio, en ATR y en % de P |
| Holgura efectiva | `entry_max − P`, en precio, en ATR y en % de P |
| Qué manda | fracción donde manda el RR (`entry_max_rr < entry_max_tec`), la técnica o **empate** (`isclose`, rel 1e-9). En B2 coinciden en 0,75·A exacto con stop por volatilidad: sin el empate, el redondeo decidiría |
| Categoría a la apertura | fracciones en el **mismo orden** que `evaluate_trade_at_entry` (`execution.py:66-72`): `INVALID_STOP` (`open ≤ stop`), `INVALID_TARGET` (`open ≥ target2`), `ABOVE_MAX_ENTRY` (`open > entry_max`, con la tolerancia `isclose` del código) y dentro (el resto) |
| Distancia | `(open_{t+1} − entry_max)/A`: distribución (p10, p25, p50, p75, p90) entre las señales `ABOVE_MAX_ENTRY` |

- `open_{t+1}` es la apertura de la serie de ejecución en la barra siguiente a la señal: el mismo
  precio que usa producción.
- Se publica por región y global.
- Mide ejecutabilidad, no rendimiento. **Se publica y no veta** (D-63, OD-P4-13 = A).
- Para B1, B2, S1 y S2 **no** se calcula ningún resultado económico de entrada: solo esta holgura y
  estas categorías. La única comparación económica de entrada es E1, con C0.

### 18.1 E1 — entrada a la apertura frente a entrada al cierre, bajo C0 (confirmatoria)

E1 es la comparación inferencial de la dimensión entrada, que cumple literalmente el requisito 1
de GATE P4 (D-63, OD-P4-5 = C, acotada). **No es una geometría, no es candidata a P5 y no altera
producción.** Sus niveles son los de C0 en los dos brazos.

**Brazo A, entrada al cierre.**
- Es el `ManagedEvent` de C0 del event study: entra a `P`, el cierre de la señal en `t`, y evalúa
  las barras `t+1 … t+40` contra el stop y el objetivo 2 de C0.
- Se aplica el coste pre-registrado del 0,20 %.

**Brazo B, entrada de producción.**
1. Los niveles son los de C0 calculados en el instante de la señal (`stop`, `target2` y
   `entry_max`), sin recalcular nada en `t+1`.
2. La entrada se intenta a `open_{t+1}`, la apertura de la serie de ejecución en la barra siguiente.
3. Se clasifica en el **orden real** de `evaluate_trade_at_entry` (`execution.py:66-72`):
   - `INVALID_STOP` si `open_{t+1} ≤ stop`;
   - `INVALID_TARGET` si `open_{t+1} ≥ target2`;
   - `ABOVE_MAX_ENTRY` si `open_{t+1} > entry_max`, salvo `isclose(rel 1e-9)`;
   - si no, **ejecutable**.

   `RR_TOO_LOW` es inalcanzable después de esas tres comprobaciones (D-29). `POSITION_TOO_SMALL`,
   la calidad del dato y el broker no se aplican, porque el laboratorio no dimensiona posiciones ni
   tiene esos estados por barra. Se declara así.
4. **No ejecutada:** `R = 0`, con estado `NO_EJECUTADA_<código>`. El `signal_id` se conserva en el
   pareado.
5. **Ejecutada:**
   - entrada a `E = open_{t+1}`; riesgo = `E − stop`;
   - mismas reglas de salida que el modo administrado, sobre las **mismas barras `t+1 … t+40`**,
     que es la misma ventana que el brazo A;
   - en la barra `t+1` la apertura ya es la entrada: se evalúa el resto de la vela contra stop y
     objetivo con `classify_target_stop_bar`. Como la apertura queda entre los dos niveles, no hay
     hueco que resuelva, y una vela que toque los dos es `AMBIGUOUS`;
   - `net_R = ((salida/E − 1)·100 − 0,20) / ((E − stop)/E·100)`, con la misma `event_economics`;
   - `TIME_EXIT` al cierre de `t+40` y `FINAL_EXIT` si la serie se acaba antes.
6. **Ambigüedad:** un `AMBIGUOUS` en cualquiera de los dos brazos sale del par primario, igual que
   en la sección 17. Se publica cuántos pares salen por ese motivo (solo A, solo B o los dos). **En
   E1 no se calculan cotas de ΔR**, porque serían comparaciones nuevas. Una no ejecutada (`R = 0`)
   nunca es ambigua.

**Estimador.** `ΔR_i = R_B,i − R_A,i` por `signal_id`, con la media por bloque de 60 sesiones e IC de
Bonferroni (`m = 4`, 0,9875, 20.000 remuestreos).

**E1 aporta exactamente 1 comparación** al recuento. Se publican además, con la misma ejecución y
sin contarlo como comparaciones:
- la tasa de cada categoría a la apertura;
- la bandera de heterogeneidad de esa misma estimación;
- el recuento de descartes por ambigüedad.

**No se calculan para E1** ni sensibilidad de bloque, ni mitades, ni estratos, ni nivel: añadirían
comparaciones que D-63 no prevé.

**Lectura pre-registrada de E1** (descriptiva, no selecciona nada):
- «la entrada de producción **gana** frente al cierre» si el IC de Bonferroni tiene el límite
  inferior > 0;
- «**pierde**» si tiene el límite superior < 0;
- **NO CONCLUYENTE** en otro caso, o si la condición 3 de capacidad falla en E1.

## 19. Medio

**Medio queda fuera de P4** (D-63, OD-P4-8 = A). Motivos:
- su evidencia es inválida por capacidad: el bloque parcial mide 102 ≤ 250 y solo hay 5 bloques
  (D-42, D-45);
- la comparación pareada de P2.6 rechaza bloques ≤ 250 en medio;
- el dividendo cobrado durante posiciones largas no entra en el P&L del laboratorio (protocolo
  P2.0; nota A-06 del roadmap).

**Limitación que también afecta a swing.** La cosecha está ajustada por splits pero **no por
dividendos**, y la serie de señal es igual a la de ejecución (`vintage.py:39-40` y `:233-236`). El
hueco del día ex-dividendo sí aparece en los precios, pero el dividendo no se abona en ninguna
geometría. Por eso el sesgo depende de la geometría:
- **S1** (stop más estrecho): el hueco del ex-dividendo hace saltar más stops que en C0. El sesgo va
  **en contra** de S1.
- **S2** (stop más ancho): hace saltar menos stops que en C0. El sesgo **favorece** a S2.
- **B2** (objetivo lejano, tenencia más larga): cruza más ex-dividendos sin cobrarlos. El sesgo va
  **en contra** de B2.
- **B1:** el mismo mecanismo que B2, pero más pequeño. En contra.

Se declara como limitación, por variante, y no se corrige en P4.

## 20. Multiplicidad (D-63)

**Familia confirmatoria definitiva, `m = 4`:**
1. B2 frente a C0;
2. S1 frente a C0;
3. S2 frente a C0;
4. E1: entrada de producción frente a entrada al cierre, bajo C0.

Cada una se estima en la longitud 60 con un IC de Bonferroni (0,9875, 20.000 remuestreos). B1 no
pertenece a la familia.

**Recuento** (convención de P3: cada estimación con IC es una comparación). Las piezas se derivan
del censo, sin desenlaces: 5 regiones, 3 regímenes calculables y 90 activos.

| Por geometría (B1, B2, S1 y S2, frente a C0) | Número | Tipo |
|---|---|---|
| Primaria, bloque 60 | 1 | **confirmatoria** en B2, S1 y S2 (IC de Bonferroni); en B1 es **descriptiva, con IC del 95 %** (2.000 remuestreos), nunca de Bonferroni |
| Bloques 40 y 80 (inválidos, publicados) y 120 | 3 | descriptiva; el 120 es veto sin corrección (condición 2) |
| Cotas de ambigüedad | 2 | descriptiva; la conservadora es veto sin corrección (condición 5) |
| Regiones (censo: 5) | 5 | descriptiva |
| Regímenes PIT calculables (censo: RISK_ON, CAUTELA, RISK_OFF) | 3 | descriptiva; `NO_CALCULABLE_CONTEXT` se cuenta, no se estima |
| Terciles de volatilidad | 3 | descriptiva |
| Mitades temporales | 2 | descriptiva; veto sin corrección (condición 8) |
| Nivel de V (media por bloque de `net_R` de V, con IC) | 1 | descriptiva; veto sin corrección (condición 10) |
| Activos (censo: 90) | 90 | descriptiva |
| **Subtotal por geometría** | **110** | |
| Base del stop, solo S1 y S2 (3 pares de `stop_basis`) | +3 | descriptiva |

| Total | |
|---|---|
| Geometrías: 2 × 110 (B1, B2) + 2 × 113 (S1, S2) | **446** |
| E1 (sección 18.1) | **+1** |
| **Total** | **447 comparaciones, de las que 4 son confirmatorias** |

- **Fórmula, que el ejecutor reproduce desde sus propias salidas** (test 11): la suma, para cada
  geometría g de {B1, B2, S1, S2}, de `(1 + 3 + 2 + R_g + K_g + 3 + 2 + 1 + A_g)`, más
  `3 × [g ∈ {S1, S2}]`, más 1 por E1. `R_g`, `K_g` y `A_g` son las regiones, los regímenes
  calculables y los activos con pares **en esa geometría**.
  - Con el censo, `R_g = 5`, `K_g = 3` y `A_g = 90` en las cuatro geometrías: 4 × 110 + 2 × 3 + 1 =
    **447**.
  - Si en la ejecución un estrato quedara sin pares en alguna geometría (por ejemplo, un activo
    cuyas señales sean todas ambiguas en un brazo), el número cambia por esa razón estructural. Se
    publica el recuento derivado, con sus componentes por geometría y el motivo de la diferencia,
    **nunca** un 447 escrito a mano.
- **No cuentan como comparaciones**, porque no tienen IC:
  - las medidas de holgura de la sección 18 y las tasas de categoría de E1;
  - las 20 medias por bloque (sección 16);
  - las secundarias puntuales de la sección 11.

  Si alguna recibiera un IC, sería una comparación nueva que este pre-registro no autoriza.
- Las condiciones que usan comparaciones descriptivas como veto se rotulan **«veto sin
  corrección»**. Como el criterio exige que se cumplan todas, solo pueden quitar candidatas.

## 21. Hipótesis por familia

| Familia | H0 | H1 | Confirmatorias |
|---|---|---|---|
| P4-A (stop) | ΔR(S_k) = 0 | ΔR(S_k) ≠ 0 | S1, S2 |
| P4-B (objetivo) | ΔR(B2) = 0 | ΔR(B2) ≠ 0 | B2. B1 es solo descriptiva, sin hipótesis confirmatoria |
| P4-C (entrada) | ΔR(E1) = 0 | ΔR(E1) ≠ 0 | E1 (sección 18.1). La holgura de cada geometría es descriptiva (sección 18) |

## 22. Criterio para que una geometría sustituya al control (D-63, OD-P4-9 = A)

**Solo B2, S1 y S2 pueden cumplir este criterio.** No se aplica a B1 (descriptiva) ni a E1 (no es
una geometría). Ningún resultado de B1 ni de E1 interviene en ninguna condición de B2, S1 o S2.

«Sustituir» significa **pasar a P5 como candidata en lugar de C0**; producción no cambia hasta P7.
Una geometría G ∈ {B2, S1, S2} cumple **solo si se dan todas** las condiciones con efecto. Si
ninguna cumple, C0 permanece.

| # | Condición | Efecto | Instrumento |
|---|---|---|---|
| 1 | El IC de Bonferroni (`m = 4`) de ΔR neto en el bloque 60 tiene el **límite inferior > 0** | veta | sección 14 |
| 2 | **Estabilidad de longitud:** en 120, la única sensibilidad válida, ΔR puntual > 0 y límite inferior del IC del 95 % > 0. Las longitudes 40 y 80 se publican y no cuentan | veta (sin corrección) | sección 13 |
| 3 | **Capacidad P2.5**, en el bloque 60: ≥ 12 bloques con pares; ningún bloque con < 5 pares; descarte por ambigüedad ≤ 25 %; `EXIT_FINAL` ≤ 10 % en C0 y en G; anchura del IC del 95 % de ΔR ≤ 0,20 (`limited_interval_width`, como en P3) | veta | `CapacityThresholds` vigentes |
| 4 | **Heterogeneidad:** se publica siempre. Si es ALTA, se publican y discuten los estratos pre-registrados (región, régimen, volatilidad, activo y, en S1/S2, `stop_basis`). No se crea ninguna política por estrato | **no veta ni aprueba** | sección 16 |
| 5 | **Ambigüedad:** con la cota conservadora para G, ΔR puntual > 0 | veta (sin corrección) | sección 17 |
| 6 | **Coherencia del RR** sobre los **niveles efectivos** (tras soporte y resistencia), en toda señal: RR en P ≥ `min_rr`; `target1 ≤ target2 < target3`; `stop < P ≤ entry_max` | veta | preflight sin desenlaces y test 2 |
| 7 | **Ejecutabilidad:** se publica la holgura y la fracción de cada categoría a la apertura de G frente a C0. El álgebra ya fija el orden de `entry_max` (S1 ≤ C0 ≤ S2, B2) | **no veta** | sección 18 |
| 8 | **Robustez temporal interna sobre datos de desarrollo:** media por bloque de ΔR > 0 en los bloques 2–11 y en los 12–21 (sección 15) | veta (sin corrección) | sección 15 |
| 9 | **Pares:** los pares usados de G son ≥ 90 % de las 101.251 señales | veta | sección 8.1 |
| 10 | **Nivel de G** (regla 2 del protocolo, como P3): primario de nivel de G > 0 (media por bloque del `net_R` de G) y PF agrupado de G > 1. El drawdown no aplica hasta P6 | veta (sin corrección) | sección 11 |

- **Si cumplen varias** (de B2, S1 y S2), todas pasan a P5 como candidatas, cuyo gate admite hasta
  5. P4 no elige un máximo.
- **B1** se publica junto a B2 como contexto descriptivo, con su etiqueta. Su resultado no cambia el
  de B2.
- **E1** se publica con su lectura propia (sección 18.1). No hace pasar ni impide pasar ninguna
  geometría.
- **El signo negativo de P3 no interviene en nada.**

## 23. Tests obligatorios (antes de ejecutar)

1. **Álgebra:** para cada variante, con niveles sintéticos (P = 100, A = 2, sin soporte),
   `entry_max_rr − P`, `entry_max` y el RR en P coinciden con la tabla de la sección 7.
2. **Validez de las variantes sobre niveles efectivos**, y no solo sobre `LevelsConfig`:
   - `LevelsConfig` acepta las cinco geometrías;
   - con primitivas sintéticas (sin soporte, con soporte que acerca el stop, con resistencia por
     debajo de `target1` y con `ATR/P` extremo), los niveles devueltos cumplen la condición 6;
   - S2 devuelve `None` donde el álgebra lo predice;
   - el preflight repite la comprobación sobre toda la población, solo con primitivas.
3. **Réplica de C0 idéntica:** `replay_managed_population` con C0 reproduce exactamente el
   `ManagedEvent` del event study, en estado, salida y `net_R`, sobre una muestra real de la cosecha.
4. **Emparejamiento:** mismos `signal_id` en todas las variantes; un `signal_id` sin niveles se
   cuenta y se publica, y nunca hace caer la ejecución en silencio.
5. **Cotas de ambigüedad:** con velas sintéticas `AMBIGUOUS`, cada cota sale con la salida esperada
   (stop u objetivo) y el `net_R` correcto.
6. **Holgura D-06:** con aperturas sintéticas bajo el stop, sobre `target2`, por encima de
   `entry_max`, igual a él y por debajo, la categoría coincide con `evaluate_trade_at_entry` en orden
   y en tolerancia. «Qué manda» declara empate con `isclose` (B2).
7. **Sin desenlaces en el preflight:** con los evaluadores parcheados para lanzar un error, el
   preflight completo (población, hash, terciles, cortes, recuentos y álgebra) termina.
8. **Población:** el censo del preflight reproduce exactamente:
   - 106.363 señales de A-02 y 5.112 de cripto;
   - **101.251** señales de **90** activos;
   - `p4_population_sha256 = 78024050…3141` y el sha256 de los `signal_id`, `9faa4a45…629f`.

   No usa `build_population` de P3 ni sus exclusiones (Asia, SMA200). Las señales con
   `NO_CALCULABLE_CONTEXT` siguen en la población. Si algo no cuadra, el preflight se para.
9. **Bootstrap y bloques:**
   - semilla, remuestreos y niveles fijados; Bonferroni con `m = 4` (0,9875, 20.000);
   - bloques ocupados y bloque más corto iguales al censo: 60 → 20 bloques, 42; 120 → 10, 102; 40 y
     80 → 22, inválidas;
   - 40 y 80 quedan fuera de la condición 2;
   - las mitades de la condición 8 son exactamente los bloques 2–11 y 12–21.
10. **E1 (sección 18.1):**
    - con barras sintéticas, la clasificación de `open_{t+1}` sigue el orden y la tolerancia de
      `evaluate_trade_at_entry`;
    - una no ejecutada da `R = 0` y conserva su `signal_id`;
    - una ejecutada usa `E = open_{t+1}`, el mismo stop y `target2`, las mismas barras `t+1 … t+40`
      y `net_R` con el coste del 0,20 %;
    - una vela de entrada que toca los dos niveles es `AMBIGUOUS`;
    - el brazo A coincide exactamente con el `ManagedEvent` de C0;
    - E1 produce exactamente 1 estimación con IC, también cuando su bandera de heterogeneidad sale
      ALTA (0 estratos y 0 cotas).
11. **Recuento de comparaciones:** derivado de las salidas con la fórmula de la sección 20 y
    publicado con sus componentes (R, K y A).
12. **Criterio:** sobre resultados sintéticos, la función que evalúa las condiciones da el
    resultado esperado:
    - incluido el caso «ninguna cumple → C0 permanece»;
    - **solo admite B2, S1 y S2**: con B1 o E1 favorables, lo rechaza;
    - una ALTA no cambia el veredicto (condición 4) y la ejecutabilidad tampoco (condición 7).
13. **Ejecución única:** la marca de ejecución se escribe antes de abrir los desenlaces, y el
    ejecutor se niega si ya existe (como en P3).
14. **Producción intacta:** `config.yaml`, el backtest `--vintage` normalizado
    (`49b12c85…`/866) y la suite, iguales.

## 24. Evidencia prevista

En `evidence/<fecha>-T-020-p4/`:
- `preflight/`: registro previo con el SHA del ejecutor, la población y su hash, el álgebra, los
  terciles y el recuento de comparaciones. Todo antes de abrir los desenlaces.
- `run/`: `p4-resultado.json`, `p4-resumen.md` y `tablas/*.tsv`:
  - ΔR por variante y longitud;
  - E1: categorías a la apertura, ΔR e IC, y su lectura;
  - bloques;
  - estratos;
  - cotas de ambigüedad;
  - holgura D-06;
  - `ABOVE_MAX_ENTRY`;
  - secundarias;
  - criterio condición por condición.
- `consola/`, `SHA256SUMS-ejecucion.txt`, `revision-look-ahead.md` y `final-pytest-ruff-mypy.txt`.
- Etiqueta de universo en toda tabla y conclusión.

## 25. GATE P4, requisito por requisito

| # | Requisito (`docs/gates.md`) | Cómo lo cubre esta ficha |
|---|---|---|
| 1 | Variantes de stop, objetivo y entrada comparadas pareadas por `signal_id`, con bootstrap por bloques (P2.6), sobre el mismo `data_vintage_id` | Secciones 7, 8, 10 y 14. **Stop:** S1, S2. **Objetivo:** B2 (y B1, descriptiva). **Entrada:** E1, pareada por `signal_id` con `R = 0` para las no ejecutadas (sección 18.1). Cumple el requisito literalmente |
| 2 | ΔR medio, IC por bloque, dispersión y heterogeneidad; ninguna se elige por el promedio con heterogeneidad alta sin explicarla | Secciones 10, 14 y 16. La heterogeneidad es una bandera obligatoria: si es ALTA, se publican y discuten los estratos pre-registrados antes de cerrar el gate (condición 4) |
| 3 | Holgura de entrada (D-06): `entry_max_rr − price` en ATR y fracción `ABOVE_MAX_ENTRY` a la apertura siguiente, por geometría | Sección 18 |
| 4 | Número total de comparaciones publicado | Sección 20; se recuenta desde las salidas (test 11) |

## 26. Prohibiciones

En el diseño y en la ejecución:
- calcular cualquier resultado de una variante antes del SHA del pre-registro y de la marca de
  ejecución;
- añadir, quitar o mover variantes, estratos, longitudes, umbrales o condiciones después de ver
  desenlaces;
- elegir la resolución intrabarra a posteriori;
- usar el score para seleccionar señales o variantes;
- reabrir P3;
- usar 70/60 o cualquier umbral sobre v2;
- tocar `config.yaml`, desplegar o activar v2;
- presentar el resultado como validación fuera de muestra;
- ejecutar P4 más de una vez con reglas distintas: un cambio posterior es un estudio nuevo con
  decisión propia.

## 27. OWNER_DECISION_REQUIRED — todas CERRADAS en D-63 (2026-10-01)

Se conservan como historial, con la decisión del propietario al principio de cada una. Las
recomendaciones y alternativas que siguen son las del primer borrador (`8512b0e`). Lo vinculante es
D-63 y el cuerpo de esta ficha.

### OD-P4-1 — Exposición previa de B1 (objetivo 2 a 3,5·ATR) · **CERRADA (D-63): B**

**Decisión del propietario:** B1 solo descriptiva, con la etiqueta «previamente expuesta en esta misma cosecha; no confirmatoria; no elegible para sustituir C0». El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** B1 ya se midió sobre esta misma cosecha (P2.6, 2026-08-31: ΔR +0,022, heterogeneidad
  alta, NO CONCLUYENTE). ¿Cómo entra en P4?
- **Alternativas:**
  - **A.** Confirmatoria, como las demás, con la exposición previa declarada en toda salida («no
    ciega»).
  - **B.** Solo descriptiva en P4, sin capacidad de sustituir a C0 hasta tener datos nuevos.
  - **C.** Fuera de P4.
- **Consecuencias:**
  - A cumple D-02, pero una conclusión favorable sobre B1 pesa menos que sobre las variantes ciegas,
    y además informa del sentido de B2 (sección 7.1);
  - B es la más limpia, pero deja D-02 sin resolver en P4;
  - C incumple D-02.
- **Recomendación:** **A**, porque D-02 la exige y la etiqueta «no ciega» impide presentarla como
  hallazgo ciego. **No** se apoya en que la heterogeneidad ya observada impida sustituir: eso sería
  diseñar el criterio sabiendo un resultado (revisión, B-1), y el papel de la heterogeneidad lo
  decide OD-P4-12 sin mirar a B1.
- **Bloquea:** la rejilla final y el recuento.

### OD-P4-2 — Población · **CERRADA (D-63): C**

**Decisión del propietario:** población de A-02 swing sin cripto: 101.251 señales, 90 activos, hash `78024050…`, sin las exclusiones de P3. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** ¿qué población de señales usa P4?
- **Alternativas:**
  - **A.** La de P3: 90 activos, 94.094 señales, hash `4aa12d85…`, 19 bloques.
  - **B.** La de A-02: 93 activos, 106.363 señales, con cripto y con las señales que P3 excluyó por
    Asia o por la historia de la SMA200.
  - **C.** La de A-02 sin cripto.
- **Consecuencias:**
  - A mantiene la identidad con D-62 y con los bloques de P3; sus exclusiones no tienen motivo
    geométrico, pero tampoco dependen del score ni del desenlace;
  - B da más señales, pero incluye cripto, donde la apertura siguiente coincide con el cierre y la
    holgura D-06 pierde sentido (D-51);
  - C está en medio y necesita un hash nuevo.
- **Recomendación:** **A.**
- **Bloquea:** el preflight y el test 8.

### OD-P4-3 — Rejilla de stops (P4-A) · **CERRADA (D-63): A**

**Decisión del propietario:** S1 y S2 sobre toda la población, con la política completa bajo la regla E; `stop_basis` como desglose descriptivo. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** ¿qué variantes de stop se comparan y sobre qué señales?
- **Alternativas:**
  - **A.** S1 (1,5·ATR, objetivo 2,25) y S2 (2,5·ATR, objetivo 3,75) sobre toda la población.
    Responde a «el ancho del stop **bajo la regla E**», con descomposición descriptiva por par de
    `stop_basis`.
  - **B.** Stop estrecho con el objetivo fijo (1,5·ATR, objetivo 3,0: RR 2,0 y holgura 0,3·A), sin
    stop ancho.
  - **C.** Ninguna variante de stop en P4.
  - **D.** S1 y S2, con la primaria de S restringida a las señales con stop por volatilidad en los
    dos brazos. Ese subconjunto sale de las primitivas en el preflight, sin desenlaces.
- **Consecuencias:**
  - **A** mide el efecto de la política tal como se ejecutaría. En las señales con soporte (en torno
    al 11–17 %, según la aproximación del revisor) mezcla un cambio de objetivo con el mismo stop, y
    el `entry_max` de S1 queda ≤ que el de C0 (sección 7). Cuesta 2 comparaciones confirmatorias.
  - **B** mezcla el stop con el RR y la holgura, así que su ΔR no se puede atribuir al stop.
  - **C** deja el requisito 1 del gate («variantes de stop») sin cubrir.
  - **D** aísla el ancho del stop de verdad, pero la población de S deja de ser la de B. Las
    familias A y B ya no comparten denominador, y hay que publicar el tamaño del subconjunto.
- **Recomendación:** **A**, porque la pregunta operativa es la política con la regla E, y se
  publica D como estrato descriptivo, no como primaria.
- **Bloquea:** la rejilla final y el recuento.

### OD-P4-4 — Rejilla de objetivos (P4-B) · **CERRADA (D-63): A**

**Decisión del propietario:** B1 y B2 = 4,875; B1 descriptiva y B2 candidata, sin llamarla ciega del todo. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** ¿qué variantes de objetivo 2 se comparan, además de la obligatoria B1 = 3,5?
- **Alternativas:**
  - **A.** B1 y B2 = 4,875 (el menor objetivo con la holgura técnica de 0,75·A entera).
  - **B.** Solo B1.
  - **C.** B1 y un punto redondo (4,0, holgura 0,4·A).
- **Consecuencias:**
  - A cubre los dos extremos con justificación algebraica y permite leer una meseta;
  - B no permite distinguir un punto aislado de una tendencia;
  - C es arbitraria sin una razón previa.
- **Recomendación:** **A.**
- **Bloquea:** la rejilla final y el recuento.

### OD-P4-5 — Entrada (P4-C) y `entry_max_atr` · **CERRADA (D-63): C, acotada**

**Decisión del propietario:** una sola comparación confirmatoria de entrada, E1, solo con C0 (sección 18.1); sin comparaciones económicas de entrada para las otras geometrías. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** ¿cómo se trata la entrada? `entry_max_atr` no se varía por separado, porque es inerte
  donde manda el RR (sección 6).
- **Alternativas:**
  - **A.** Solo holgura efectiva y categorías a la apertura por geometría (sección 18), descriptivas.
  - **B.** A, más una secundaria económica descriptiva. Para cada geometría, la media por bloque del
    `net_R` entrando a `open_{t+1}` en las señales de la categoría «dentro», con IC por bloques, con
    el mismo stop y objetivo y desde la barra `t+1`. Se rotula **«condicionada a la ejecución:
    muestra seleccionada por la apertura»**, cuenta +5 comparaciones y **no interviene en el
    criterio** de P4, P5 ni P6.
  - **C.** Comparación pareada confirmatoria de la entrada, con la misma geometría (C0) y dos brazos:
    entrada al cierre de la señal frente a entrada a `open_{t+1}` con veto `ABOVE_MAX_ENTRY`, con
    `R = 0` para las no ejecutadas. Se haría también para las geometrías de B si se quiere ver la
    holgura en valor.
- **Consecuencias:**
  - **A** cumple el requisito 3 del gate. El requisito 1 (variantes de entrada «comparadas pareadas»)
    solo queda cubierto con una lectura que el propietario acepta y registra: que en P4 la entrada
    es una propiedad de cada geometría.
  - **B** añade información económica de la holgura sin poder decidir, por el sesgo de selección.
    Para el requisito 1, lo mismo que A.
  - **C** cubre literalmente el requisito 1 y mide el valor por señal de la política de apertura.
    Añade 1 o más confirmatorias (cambia `m` de OD-P4-7) y redefine qué es «la misma señal» en el
    par.
- **Recomendación:** **B**, aceptando y registrando la lectura del requisito 1. C es preferible si
  el propietario quiere cerrar el requisito sin interpretación; en ese caso `m` pasa a 5.
  *(Historial: D-63 eligió C acotada y, a la vez, sacó B1 de la familia, así que `m` queda en 4:
  B2, S1, S2 y E1.)*
- **Bloquea:** la sección 18, el recuento y OD-P4-7.

### OD-P4-6 — Longitudes de bloque inválidas según P2.5 (40 y 80) · **CERRADA (D-63): A**

**Decisión del propietario:** 40 y 80 inválidas y fuera de toda condición; primaria 60, sensibilidad válida 120. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** P2.5 exige que el bloque supere el periodo de tenencia (40). Con la espina de 1.302
  sesiones, el bloque más corto de la longitud 40 mide 22, y el de la 80 también 22. Las longitudes
  60 (42) y 120 (102) son válidas. El código actual cuenta todas en el veredicto. ¿Qué regla se
  aplica?
- **Alternativas:**
  - **A.** Una longitud cuyo bloque ocupado más corto sea ≤ 40 es inválida, igual que en P3
    (`horizon_valid`). Se publica marcada y no cuenta en ninguna condición. Con esta espina, 40 y 80
    quedan inválidas y la sensibilidad válida es solo 120.
  - **B.** Fusionar el resto final con el bloque anterior en todas las longitudes. Todas quedan
    válidas, salvo el 40 por definición.
  - **C.** Contar todas, como hace hoy `_comparison_verdict`.
- **Consecuencias:**
  - **A** es coherente con P2.5 y con P3, pero la estabilidad descansa en una sola longitud (120,
    con unos 10–11 bloques, por debajo de 12) y en la primaria.
  - **B** conserva más sensibilidad, pero introduce una regla de bloques que P2.5 y P3 no usaron, y
    cambia `session_block_lookup`.
  - **C** deja que longitudes inválidas vetan o aprueben.
- **Recomendación:** **A.**
- **Bloquea:** la sección 13, la condición 2 y el test 9.

### OD-P4-7 — Corrección por multiplicidad · **CERRADA (D-63): A**

**Decisión del propietario:** Bonferroni con familia definitiva `m = 4` (B2, S1, S2, E1): 0,9875 y 20.000 remuestreos; B1 fuera. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** ¿se corrigen las 4 comparaciones confirmatorias?
- **Alternativas:**
  - **A.** Bonferroni con `m = 4`: nivel 0,9875 y 20.000 remuestreos.
  - **B.** Sin corrección, porque cada familia es una pregunta distinta.
  - **C.** Holm.
- **Nota:** `m` es el número de confirmatorias que resulte de las demás OD: 4 con las
  recomendaciones; 5 si OD-P4-5 = C; 3 si OD-P4-13 = C.
- **Consecuencias:**
  - A es conservadora, simple y coherente con P3 (D-57);
  - B infla la probabilidad de un falso positivo entre 4;
  - C es algo más potente, pero añade orden y dependencia entre resultados.
- **Recomendación:** **A.**
- **Bloquea:** la sección 14, la condición 1 y el test 9.

### OD-P4-8 — Alcance de medio · **CERRADA (D-63): A**

**Decisión del propietario:** medio fuera de P4. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** ¿medio entra en P4?
- **Alternativas:**
  - **A.** Fuera.
  - **B.** Trazabilidad, con un veredicto forzado inválido.
  - **C.** Confirmatorio.
- **Consecuencias:**
  - A es simple y evita el problema del dividendo;
  - B cuesta tiempo de cálculo y comparaciones sin poder decidir nada;
  - C contradice D-42 y D-45.
- **Recomendación:** **A**, que coincide con el criterio por defecto del propietario. Se registra
  como propuesta metodológica, no como resultado.
- **Bloquea:** el alcance del ejecutor.

### OD-P4-9 — Criterio de aceptación · **CERRADA (D-63): A, adaptada**

**Decisión del propietario:** solo B2, S1 y S2 pueden cumplir el criterio; las condiciones 4 y 7 no vetan. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** ¿se adoptan las condiciones 1 a 10 de la sección 22, con «varias cumplen → todas
  pasan a P5» y «ninguna → C0 permanece»?
- **Alternativas:**
  - **A.** Sí, tal cual (con la 4 y la 7 según OD-P4-12 y OD-P4-13).
  - **B.** Sí, pero eligiendo una sola si cumplen varias (por ejemplo, la de menor cambio respecto a
    C0).
  - **C.** Sin la condición 10 (nivel de V). Una variante pasaría solo por ΔR > 0 aunque las dos
    geometrías pierdan.
- **Consecuencias:**
  - **A** se ajusta a GATE P5 (≤ 5 candidatas), no busca máximos y respeta la regla 2 del
    protocolo, como P3.
  - **B** introduce una regla de desempate que P5 ya cubre.
  - **C** contradice la regla 2 del protocolo.
- **Recomendación:** **A.**
- **Bloquea:** la sección 22 y el test 12.

### OD-P4-10 — Validación temporal dentro de P4 · **CERRADA (D-63): B**

**Decisión del propietario:** **robustez temporal interna sobre datos de desarrollo**, nunca validación; desviación formal del protocolo registrada. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** el protocolo pide que P4 compare «ya bajo validación temporal», pero la cosecha está
  consumida. ¿Cómo se cumple?
- **Alternativas:**
  - **A.** Solo desarrollo, registrado como **desviación formal del protocolo**. La validación queda
    para P7 con datos posteriores.
  - **B.** A, más la condición 8: media por bloque de ΔR > 0 en cada mitad de los bloques ocupados
    de la primaria, en orden temporal; con un número impar, el central va a la segunda.
  - **C.** Un walk-forward dentro de P4.
- **Consecuencias:**
  - **A** es honesta, pero no hace nada contra la selección retrospectiva.
  - **B** añade estabilidad temporal sin datos nuevos, con 2 comparaciones por variante. Sigue
    siendo una desviación formal, solo que mitigada.
  - **C**, con 19 bloques, deja ventanas sin capacidad.
- **Recomendación:** **B**, registrando la desviación del protocolo en la decisión que cierre esta
  OD.
- **Bloquea:** la condición 8 y el recuento.

### OD-P4-11 — Estratos de heterogeneidad · **CERRADA (D-63): A**

**Decisión del propietario:** estratos descriptivos; las señales con contexto PIT no calculable se quedan en la primaria y se cuentan aparte. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** ¿se adoptan los estratos de la sección 16 (región, régimen PIT, terciles de
  `atr/price`, activo y base del stop en S1/S2) como explicación pre-registrada de la
  heterogeneidad? El veto lo decide OD-P4-12.
- **Alternativas:**
  - **A.** Sí, todos descriptivos; P4 no adopta políticas por estrato y el material pasa a P5.
  - **B.** Solo región y activo.
  - **C.** Permitir ya en P4 una sustitución condicionada al estrato.
- **Consecuencias:**
  - **A** cumple el requisito 2 del gate («explicar en qué régimen, región o volatilidad mejora»).
  - **B** pierde la explicación por régimen y volatilidad que pide el gate.
  - **C** multiplica las políticas y las comparaciones.
- **Nota:** EMERGING_MARKETS es prácticamente un solo activo: 1.068 señales en la población de P3 y
  **1.151 en la de P4** (censo). Revisión, O-3. Su
  fila es casi un estrato por activo y se rotula así.
- **Recomendación:** **A.**
- **Bloquea:** la sección 16.

### OD-P4-12 — Papel de la heterogeneidad (calibración del instrumento) · **CERRADA (D-63): B**

**Decisión del propietario:** la heterogeneidad es una bandera obligatoria, no un veto; sin calibración sintética; FOLLOW_UP del instrumento. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** el instrumento de P2.6 trata como independientes las sesiones dentro de cada bloque.
  Con un solapamiento de 40 barras, en sintético etiqueta ALTA un efecto constante (20 de 20
  réplicas, sección 16). ¿Qué papel tiene la heterogeneidad en el criterio?
- **Alternativas:**
  - **A.** Veto automático: ALTA impide sustituir, como en el primer borrador.
  - **B.** Bandera: ALTA no veta, pero obliga a publicar la explicación por estrato (región,
    régimen, volatilidad y base del stop) que pide el gate. P4 no adopta políticas por estrato; el
    material pasa a P5.
  - **C.** Calibrar antes de medir con el test 10, con el modelo y el umbral fijados aquí, que no
    se pueden ajustar al implementar:
    - **estructura:** 19 bloques de 60 sesiones (1.140 sesiones) y 60 señales por sesión;
    - **efecto:** ΔR constante de 0,02;
    - **factor común por sesión:** la media móvil de los 40 últimos choques i.i.d. N(0, σ_c), que
      reproduce el solapamiento de 40 barras;
    - **ruido individual:** i.i.d. N(0, 1,0);
    - **escenarios:** σ_c ∈ {0,05, 0,10, 0,20};
    - **réplicas:** 200 por escenario, con la semilla 20260830 (stream de réplica `r` = semilla +
      `r`);
    - **instrumento:** `bootstrap_block_delta` con `block_length = 60`, 2.000 remuestreos y
      `noise_level = 0,90`.

    **Umbral exacto:** la fracción de ALTA debe ser **≤ 0,10 en los tres escenarios**. Si se cumple,
    se aplica A; si falla en cualquiera, se aplica B.
  - **D.** Sustituir el modelo de ruido por uno que respete el solapamiento. Es un cambio del
    instrumento P2.6 y necesita su propia decisión y su propia revisión, fuera de P4.
- **Consecuencias:**
  - **A**, con el instrumento sin calibrar, deja «C0 permanece» decidido en buena parte antes de
    medir.
  - **B** cumple el texto del gate («sin explicar»), pero renuncia a usar la dispersión como veto.
  - **C** decide con un criterio fijado antes de ver datos reales; la evidencia sintética del
    revisor anticipa que acabará en B.
  - **D** es la solución de fondo, pero no cabe en P4 sin retrasarlo.
- **Recomendación:** **C**, y abrir D como tarea aparte para P5.
- **Bloquea:** la condición 4 y el test 10.

### OD-P4-13 — Papel de la ejecutabilidad en el criterio · **CERRADA (D-63): A**

**Decisión del propietario:** la ejecutabilidad se publica y no veta. El texto que sigue es el historial de la pregunta tal como se planteó.

- **Pregunta:** el orden de `entry_max` frente a C0 lo fija el álgebra (S1 ≤ C0 ≤ S2, B1, B2). Un
  veto «`ABOVE_MAX_ENTRY` de V ≤ C0» queda decidido antes de medir: S1 no podría cumplirlo y las
  otras siempre lo cumplirían. ¿Qué hace el criterio con la ejecutabilidad?
- **Alternativas:**
  - **A.** Solo publicarla, sin vetar (condición 7 del borrador revisado).
  - **B.** Un veto con margen, por ejemplo que `ABOVE_MAX_ENTRY` de V no supere al de C0 en más de 5
    puntos, declarando que la pérdida de holgura de S1 es parte de su diseño.
  - **C.** Sacar S1 de las confirmatorias (`m` baja a 3) y mantener el veto para las demás.
- **Consecuencias:**
  - **A** cumple el requisito 3 del gate (medir) sin un veto trivial.
  - **B** introduce un margen arbitrario.
  - **C** reduce P4-A a un solo stop.
- **Recomendación:** **A.**
- **Bloquea:** la condición 7.

## 28. Plan de implementación (requiere autorización aparte)

1. **Paso 1 — pre-registro.** Esta ficha, con D-63 y la tercera revisión aplicada. El HEAD
   documental que quede después de esa revisión y de sus correcciones es **`P4_PREREG_SHA`**.
2. **Paso 2 — código, sin desenlaces, con una autorización nueva.** Codex programa y Claude
   supervisa `advisor/research/p4.py` y un comando `p4` con `--fase preflight|confirmatoria`.
   - **Reutiliza:**
     - el censo de `evidence/2026-10-01-T-020-censo-p4/censo_p4.py`, como referencia de la
       población (**no** `build_population` de P3);
     - `replay_managed_population`, ampliado para contar en lugar de lanzar un error cuando una
       variante no produce niveles;
     - `pair_populations` y `bootstrap_block_delta`.
   - **Añade:**
     - la simulación de E1 (sección 18.1);
     - las cotas de ambigüedad;
     - la holgura D-06 con `open_{t+1}`;
     - los estratos (con `NO_CALCULABLE_CONTEXT` contado aparte);
     - el criterio, solo para B2, S1 y S2;
     - el recuento derivado;
     - la marca de ejecución única.
   - Lleva los tests de la sección 23. **No ejecuta P4.**
3. **Paso 3 — revisión de look-ahead previa**, por un agente independiente, sobre el código y el
   preflight.
4. **Paso 4 — una única ejecución confirmatoria** sobre el SHA congelado del ejecutor.
5. **Paso 5 — registro del resultado (D-nn), revisión final y decisión sobre GATE P4.**

## 29. Plan de revisión independiente

- **Ficha:** dos vueltas sobre el borrador (2026-10-01) y una tercera sobre la versión con D-63. Ver
  «Revisión de la ficha».
- **Código:** revisión de look-ahead y de ausencia de desenlaces antes de ejecutar.
- **Resultado:** revisión final antes de cruzar GATE P4.

Cada una la hace un agente distinto de quien programó y de quien escribió.

## 30. Handoff al siguiente agente

- **Estado:** pre-registro con las OD cerradas (D-63). P4 **no** se ha ejecutado y no se calculó
  ningún resultado de ninguna variante.
- **Siguiente:** fijar `P4_PREREG_SHA` (el HEAD documental tras la tercera revisión) y, **con una
  autorización nueva del propietario**, el paso 2.
- **Prohibido sin esa autorización:**
  - implementar `p4.py`;
  - ejecutar `comparacion-pareada`, que mide B1 contra C0 sobre la cosecha, sobre ninguna variante;
  - mirar resultados de B1, B2, S1, S2 o E1.
- **No olvidar:**
  - la población es la de A-02 sin cripto (101.251, `78024050…`), **no** la de P3;
  - B1 es solo descriptiva;
  - la heterogeneidad no veta;
  - las mitades son «robustez temporal interna», no validación.

## Revisión de la ficha

Dos revisiones adversariales del primer borrador, el 2026-10-01, las dos en **solo lectura y sin
medir ninguna variante**. Los informes completos están en
`evidence/2026-10-01-T-020-revision-ficha/`.

- **Revisor independiente** (agente `revisor`, Claude, distinto del autor): **1 BLOCKER, 5
  IMPORTANTE, 9 MENOR y 4 OBSERVACIÓN.** Confirmó correctos el inventario, el álgebra, las semillas,
  el recuento de entonces, el hash de la población y que las dos series de la cosecha tienen la
  misma escala.
- **Codex** (revisión cruzada): **0 BLOCKER, 6 IMPORTANTE, 2 MENOR y 2 OBSERVACIÓN.**

### Qué se hizo con cada hallazgo

**BLOCKER.**
- **B-1 (revisor).** El instrumento de heterogeneidad, al tratar como independientes sesiones que
  se solapan, etiqueta ALTA un efecto constante, y eso dejaba la condición 4 decidida antes de
  medir.
  - Se documenta en la sección 16.
  - La condición 4 depende ahora de **OD-P4-12** (calibración con el test 10, o bandera en lugar de
    veto).
  - OD-P4-1 deja de apoyarse en la heterogeneidad ya vista en B1.

**IMPORTANTE.**
- **I-1 (revisor).** El veto de ejecutabilidad quedaba fijado por el álgebra. La condición 7 pasa a
  ser descriptiva y su papel lo decide OD-P4-13. Se corrige la frase «RR y holgura iguales» en la
  sección 7 y en OD-P4-3.
- **I-2 (revisor).** S1 y S2 no aíslan el stop por la regla de soporte.
  - Nuevo apartado en la sección 7.
  - P4-A se redefine como «ancho del stop bajo la regla E».
  - Se añade el estrato de `stop_basis`.
  - OD-P4-3 incluye la alternativa D (aislarlo).
- **I-3 (revisor).** El bloque de 80 sesiones también tiene un bloque final de 22. OD-P4-6 se
  amplía a todas las longitudes; las secciones 13 y 22 y el test 9 se ajustan.
- **I-4 (revisor).** Faltaba la regla 2 del protocolo. Se añade la condición 10 (nivel de V > 0 y PF
  > 1, el drawdown no aplica), como en P3.
- **I-5 (revisor).** El requisito 1 de GATE P4 en cuanto a la entrada. La sección 25 y OD-P4-5
  dicen ahora que con A o B solo se cumple con una lectura que el propietario acepte; C lo cumple
  literalmente.
- **Codex.**
  - El criterio y el recuento pasan a rotularse **propuesta, vinculante al cerrar las OD**.
  - El emparejamiento ya no se da por completo «por construcción»: el preflight cuenta las señales
    sin niveles.
  - La coherencia de niveles se comprueba sobre los **niveles efectivos** (condición 6 y test 2).
  - La secundaria de OD-P4-5 B queda definida y contada (+5).
  - OD-P4-10 A pasa a ser una desviación formal del protocolo.
  - El recuento queda rotulado como borrador.

**MENOR.**
- **M-1.** Categorías a la apertura en el orden de `execution.py`.
- **M-2.** Corregida la semántica del backtest (sección 5.3).
- **M-3.** Sección 19 corregida: la cosecha no está ajustada por dividendos, y se dice en qué
  sentido va el sesgo.
- **M-4.** Exposición previa completada (sección 7.1).
- **M-5.** Empate con `isclose` en «qué manda».
- **M-6.** Las cotas se declaran envolventes y se cuentan las velas ambiguas compartidas.
- **M-7.** Redacción de las condiciones 2, 3 y 8 precisada.
- **M-8.** La secundaria de OD-P4-5 queda definida.
- **M-9.** Corregidas la referencia a INV-15 y esta misma sección.
- **Codex.** Coste citado en las dos fuentes; sección 29.

**OBSERVACIÓN.**
- **O-1.** Las condiciones que usan comparaciones descriptivas se rotulan «veto sin corrección».
- **O-2.** S2 devuelve `None` si `ATR/P ≥ 0,4` (sección 8.1).
- **O-3.** EMERGING_MARKETS es casi un solo activo (OD-P4-11).
- **O-4 y las de Codex.** Sin acción: confirman el inventario y que B2, S1 y S2 no se midieron como
  variantes pareadas.

**Segunda vuelta del revisor sobre la versión corregida.** 14 hallazgos CERRADOS, 3 PARCIALES y 2
ABIERTOS, más 2 defectos nuevos, ninguno BLOCKER ni IMPORTANTE. Todos quedan corregidos:
- **P-1:** restos de «resto comparable» y «sin empeorar la ejecutabilidad» en las secciones 2 y 7;
- **P-2:** el sentido del sesgo del dividendo, ahora por variante (S2 queda favorecida);
- **M-9:** la referencia a INV-15 en la sección 15;
- **N-1:** la calibración de OD-P4-12 C tenía parámetros y umbral abiertos; ahora el modelo, los
  escenarios, las réplicas, la semilla y el umbral (≤ 0,10 en los tres) están fijados;
- **N-2:** la sección 25 remitía al test 10 en lugar del 11.

El revisor confirmó que el recuento de 451 está bien sumado.

**Tercera revisión, sobre la versión con D-63 (`4de6beb`).** La hizo un agente `revisor` nuevo,
solo leyendo y sin desenlaces: **0 BLOCKER, 2 IMPORTANTE, 2 MENOR y 3 OBSERVACIÓN**. Los diez
puntos que pidió el propietario salieron OK:
- B1 no puede entrar en el criterio;
- la población no hereda las exclusiones de P3;
- E1 está definida;
- `m = 4`;
- la heterogeneidad no veta;
- las mitades no se llaman validación;
- las señales sin contexto PIT se quedan;
- el recuento es derivable;
- no se leyó ningún desenlace;
- no hay cambios fuera de alcance.

Lo corregido después:
- **I-1:** la obligación de publicar estratos con ALTA es solo para las geometrías. E1 publica la
  bandera sin estratos (sección 16; test 10).
- **I-2:** las 20 medias por bloque son puntos sin IC y no cuentan (secciones 16 y 20).
- **M-1:** 19 → 20 bloques.
- **M-2:** solo el primario de nivel lleva IC entre las secundarias; la primaria de B1 lleva un IC
  del 95 %, no de Bonferroni (secciones 11 y 20).
- **O-1:** la lectura «meseta B1 + B2» no interviene en el criterio (7.1).
- **O-2:** notas de historial aclaradas (OD-P4-5, OD-P4-11).
- **O-3:** fórmula del recuento como suma por geometría.

Restos del borrador que siguen en la sección «Revisión de la ficha» (por ejemplo, «451») son
historial de las vueltas anteriores. Lo vinculante es D-63 y el cuerpo de la ficha.

**Pendiente (antes de esta tercera revisión).** Una tercera revisión breve, después de que el propietario cierre las OD y antes del
SHA del pre-registro, para comprobar que la versión definitiva no reintroduce grados de libertad.
