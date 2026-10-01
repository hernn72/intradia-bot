# Revisión adversarial independiente del borrador de T-020 (P4, geometría) — 2026-10-01

- **Revisor:** el agente `revisor` (Claude), distinto del autor de la ficha.
- **Modo:** solo lectura. **No calculó ningún desenlace de ninguna variante**: ni `net_R`, ni ΔR, ni
  PF, ni MAE/MFE, ni intervalos. No ejecutó `comparacion-pareada`, `p3` ni `replay`.
- **Base:** `main` = `a15e695`, con la ficha sin commitear. Los números de sección se refieren al
  primer borrador.
- Este texto reproduce su informe. La respuesta a cada hallazgo está en la sección «Revisión de la
  ficha» de `docs/tareas/T-020-p4-geometria.md`.

**Resultado: REQUIERE CAMBIOS.** 1 BLOCKER, 5 IMPORTANTE, 9 MENOR y 4 OBSERVACIÓN. El inventario y
el álgebra son correctos. Los defectos están en el criterio:
- dos condiciones quedaban decididas antes de medir, una por un artefacto del instrumento y otra por
  álgebra;
- S1 y S2 no aíslan el stop;
- el bloque de 80 tiene el mismo problema que la ficha detectó en el de 40.

## Qué verificó y cómo

**Ejecutado, sin desenlaces.** Los scripts quedaron en el scratchpad de la sesión.
- **Espina de sesiones** (fechas de la cosecha, sin cripto): **1.302 sesiones**. El último bloque
  mide 22 con longitud 40, 42 con 60 (coincide con el «bloque más corto 42» del preflight de P3), 22
  con 80 y 102 con 120.
- **Primitivas de 101.251 barras**, una aproximación a la población de P3: solo `price`, `atr`,
  `low_lookback` y `high_lookback` del instante de señal, con `compute_levels_from_inputs` para cada
  variante. No lee ninguna barra posterior.
- **Álgebra** con niveles sintéticos: P = 100 / 37,13 / 1234,567 y A = 2, con y sin soporte en 97.
- **`bootstrap_block_delta`** con datos sintéticos de efecto constante.
- **Tests:** `pytest tests/test_uncertainty.py tests/test_event_study.py tests/test_capacity.py
  tests/test_analysis.py` → **142 passed**.

**Leído.**
- **Código:** `levels.py`, `config.py`, `config.yaml`, `event_study.py`, `execution.py`,
  `uncertainty.py`, `bootstrap.py`, `capacity.py`, `p3.py`, `vintage.py` y `backtest/engine.py`.
- **Documentos:** `docs/gates.md`, `docs/protocolo-investigacion.md`, `docs/decision-log.md` (D-02,
  D-03, D-06, D-43, D-62), `docs/metodo-trabajo.md` (INV-01 a INV-19),
  `docs/ratio-beneficio-riesgo.md`, `docs/pendientes.md` §15 y el criterio de P3 en T-019.
- **Evidencia publicada:** el preflight de P3 y el event study de A-02, solo los recuentos de
  estados de C0.

**Confirmado correcto.**
- Los parámetros y las líneas de las tablas 5.1 y 5.4.
- Las fórmulas de 5.2 y la regla E.
- La tabla de la sección 7: RR en P; holgura B1 = 0,2·A, B2 = 0,75·A, y 0 en C0, S1 y S2 con stop
  por volatilidad.
- Las semillas (+97 y +194) y `DEFAULT_RESAMPLES` = 2000.
- El recuento de entonces: 109 por variante y 436 en total.
- El hash y el tamaño de la población de P3.
- La descripción del bloque 40 en `_comparison_verdict` y `_stable_intervals`.
- Las cinco geometrías producen niveles en las 101.251 barras (0 `None`).
- La serie de señal y la de ejecución tienen **la misma escala** (`vintage.py:39-40` y `:233-236`),
  así que comparar `open_{t+1}` con `entry_max` es coherente.

## BLOCKER

### B-1. La condición 4 («heterogeneidad no ALTA») sale casi decidida por el instrumento

- **El problema.** `_constant_effect_noise` (`bootstrap.py:237-260`) remuestrea **sesiones como si
  fueran independientes** dentro de cada bloque. En swing, las señales de sesiones contiguas
  comparten hasta 40 barras de trayectoria, así que su ΔR está autocorrelado. El instrumento
  infravalora la dispersión esperable y etiqueta ALTA aunque el efecto sea constante.
- **Ensayo sintético:** 1.140 sesiones con 60 señales cada una; ΔR = 0,02 constante, más un factor
  común (la media móvil de 40 choques) y ruido individual.
  - Con `block_length = 60` sale **ALTA en 20 de 20** réplicas. Por ejemplo, una dispersión de 0,0194
    frente a un ruido esperado de [0,0040, 0,0072].
  - Con ruido independiente, el control da COMPATIBLE en 10 de 10.
  - Es coherente con el ALTA de B1 en `pendientes.md` §15.
- **Consecuencias:**
  - el «C0 permanece» queda medio decidido de antemano;
  - OD-P4-1 se apoyaba en el ALTA ya observado en B1, que es una regla diseñada sabiendo un
    resultado.
- **Corrección propuesta.** Una OD que elija entre dos opciones:
  - (a) que ALTA sea una bandera que exige la explicación por estrato del gate, en lugar de un veto;
  - (b) un test de calibración: con efecto constante y solapamiento de 40, ≤ ~10 % de ALTA; si no lo
    pasa, la condición 4 es solo descriptiva.

  Cambiar el modelo de ruido es una decisión aparte.

## IMPORTANTES

### I-1. La condición 7 (ejecutabilidad) queda decidida por el álgebra

- **La causa.** Con la regla de soporte, el `entry_max` de S1 es ≤ que el de C0 en toda señal, y el
  de B1, B2 y S2 es ≥.
- **Sobre primitivas reales:**
  - S1 tiene un `entry_max` menor en 17.143 barras y mayor en 0;
  - S2, mayor en 18.368;
  - B1 y B2, mayor en 96.969.
- **Sintético con soporte en 97:** C0 da 100,3 y S1 da 100,0.
- **Consecuencia:** S1 no puede cumplir la condición 7, y las demás la cumplen siempre.
- **Corrección propuesta:** quitarla, redefinirla con un margen o sacar S1 de las confirmatorias, y
  corregir «RR y holgura iguales que C0».

### I-2. S1 y S2 no aíslan el ancho del stop

- **La causa.** El stop por soporte no depende de `s` (`levels.py:150-165`).
- **Sobre primitivas reales:**
  - el stop se apoya en el soporte en el 16,9 % de las barras con C0, el 11,5 % con S1 y el 22,4 % con
    S2;
  - el stop es **idéntico al de C0** en el 11,5 % de las barras con S1 y en el 16,9 % con S2. Ahí la
    variante solo cambia el objetivo 2, y el RR en P deja de ser 1,5.
- **Corrección propuesta:**
  - un estrato descriptivo por par de `stop_basis`;
  - redefinir P4-A como «ancho del stop bajo la regla E», o restringir la primaria de S a las señales
    con stop por volatilidad en los dos brazos.

### I-3. El bloque de 80 también tiene un bloque final parcial inválido según P2.5

- **Los números.** 1302 mod 80 = 22, que es ≤ 40, y el último bloque está ocupado.
- **Las reglas:**
  - P2.5 dice que una ventana más corta que `MAX_HOLD_BARS` es inválida;
  - P3 aplica `horizon_valid = shortest > max_hold` (`p3.py:597-607`);
  - el bootstrap pondera igual ese bloque de 22 sesiones que uno completo.
- **Corrección propuesta:** ampliar OD-P4-6 a todas las longitudes, con una regla para el resto
  final, y publicar el bloque más corto de cada longitud.

### I-4. El criterio omitía la regla 2 del protocolo, que P3 sí aplicó

- **Qué faltaba.** La regla 2 del protocolo fija de antemano: muestra mínima, PF > 1, drawdown máximo
  y expectancy > 0.
- **Consecuencia.** Una variante con ΔR > 0 pero expectancy negativa pasaría a P5.
- **Corrección propuesta:** una condición de nivel (primario de V > 0 y PF agrupado > 1), con el
  drawdown declarado no aplicable, como en P3.

### I-5. El requisito 1 de GATE P4 en cuanto a la entrada

- **El hueco.** El event study entra al cierre (`event_study.py:447`), así que con OD-P4-5 A o B
  ninguna comparación pareada mide la entrada.
- **Corrección propuesta:** decir que A o B solo cumplen con una lectura aceptada por el propietario,
  o hacer una comparación pareada de entrada: cierre frente a `open_{t+1}` con veto y R = 0.

## MENORES

- **M-1. Categorías.** `evaluate_trade_at_entry` clasifica en este orden: `INVALID_STOP`,
  `INVALID_TARGET`, `ABOVE_MAX_ENTRY` y ejecutable (`execution.py:66-72`). La sección 18 y el test 6
  no lo seguían.
- **M-2. Backtest.** `ENTRY_OPEN_AT_OPEN` abre aunque haya `ABOVE_MAX_ENTRY` (`engine.py:376-381`);
  el veto lo aplica `ENTRY_RESPECT_ENTRY_MAX`.
- **M-3. Dividendos.** La sección 19 decía «serie ajustada», pero la cosecha **no** ajusta por
  dividendos y las dos series coinciden. El hueco del ex-dividendo está en los datos; el dividendo no
  se cobra. Hay que decir en qué sentido va el sesgo.
- **M-4. Exposición previa incompleta.** Faltaban:
  - el comportamiento de C0 ya publicado (event study de A-02 y MFE por banda; P3 por región y
    activo);
  - las creencias previas sobre el stop (`ratio-beneficio-riesgo.md:112`; incidente de julio);
  - que B1 informa de B2.
- **M-5. Empate en B2.** «Qué manda» lo decide el redondeo en B2 (19.020 barras): hay que declarar
  empate con `isclose`.
- **M-6. Cotas de ambigüedad.** No siempre son conjuntamente factibles con niveles anidados. Es
  irrelevante en la práctica (C0: 25 de 106.363), pero hay que declararlo.
- **M-7. Redacción.** Ambigüedades en las condiciones 2 (≥ 0 o > 0), 8 (qué bloques y qué
  estimador) y 3 (anchura de P2.5).
- **M-8. Secundaria sin definir.** La secundaria económica de OD-P4-5 B no tenía estimador y no
  figuraba en el recuento.
- **M-9. Estado y referencias.** La sección 29 decía «se hizo» con el apartado vacío, e INV-15 es
  «el holdout se consulta una vez» (`metodo-trabajo.md:164`), no «cosecha consumida».

## OBSERVACIONES

- **O-1.** Las condiciones 2, 5 y 8 usan comparaciones descriptivas como veto. No inflan los falsos
  positivos, pero conviene rotularlas «veto sin corrección».
- **O-2.** S2 da `None` si `ATR/P ≥ 0,4` sin soporte. Empíricamente, 0 casos.
- **O-3.** EMERGING_MARKETS son 1.068 señales, casi de un solo activo.
- **O-4.** Los 30 puntos están presentes y las alternativas de las OD no están sesgadas. Las OD que
  faltaban son las de B-1, I-1, I-2, I-3 e I-4.
