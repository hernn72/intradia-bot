# Revisión Codex (lookahead-r1-3da05e7) — informe literal

_Solo lectura, sin red y sin datos posteriores al 2026-08-27. Job `task-muvg27j5-6m3efs`._

**Hallazgos**

**IMPORTANTE**: `construir_ventanas` abre ventanas para todas las señales elegibles temporalmente, pero no vuelve a aplicar el filtro de ejecutabilidad de P6 en la apertura de `e_i`. En [t024_decision.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:238), el flujo pasa de `es_elegible_temporal` a `salida_p6` sin comprobar `DATA_NOT_EXECUTABLE`, `INVALID_STOP`, `INVALID_TARGET`, `ABOVE_MAX_ENTRY` ni `RR_TOO_LOW`. En P6, esas señales se rechazan antes de abrir posición en [p6_sim.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/p6_sim.py:616).

Reproducción sintética: una señal con `entry_max=99` y apertura de entrada `100` sería `ABOVE_MAX_ENTRY` por [t024_captura.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_captura.py:108), pero `dec.construir_ventanas([senal], {"AAA": rows}, c_e=...)` produciría una `VentanaT024` y calcularía salida/D2. Esto no es look-ahead, pero rompe el contrato “salidas idénticas a `p6_sim`” y puede contaminar no solapamiento, `ℓ_i`, D2/D2o/D2c y la etiqueta decisoria.

**OBSERVACIÓN**: los tests no cubren esa integración. [tests/test_t024.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/tests/test_t024.py:294) prueba motivos de ejecutabilidad de forma aislada, y [tests/test_t024.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/tests/test_t024.py:307) compara salidas contra `p6_sim` solo con entradas ejecutables. Por tanto, una fuga de “señal no ejecutable entra en decisión” pasaría.

**Resultado Del Mandato**

No he demostrado look-ahead directo en captura/reconfirmación: el truncado a `c_e`, la vista ciega de apertura de `e_i`, el `analysis_timestamp` point-in-time y la generación equivalente a P6 están bien encaminados en las líneas revisadas. Pero sí hay una desviación material del contrato P6 en el camino decisorio.

**Veredicto explícito**: **NO APTO para cierre** bajo el criterio pedido, porque hay **0 BLOCKER pero 1 IMPORTANTE**. No ejecuté tests ni leí datos reales; la revisión fue solo lectura, sin red y sin abrir `data/frescura-snapshot.db`.

