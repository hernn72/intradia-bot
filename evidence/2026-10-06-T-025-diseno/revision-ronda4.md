# T-025 — Revisión independiente, ronda 4 (2026-10-07)

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

- **Objeto:** el diseño entero de T-025 tras las decisiones del propietario D-75, D-76 y D-77, en
  `ce45c4e` (rama `research/t025-shadow-prereg`), con sus interacciones con P6, T-023, T-024, P6-bis,
  P7, P10, posiciones manuales, `intradia.db`, `paper.db`, la Pi, dashboard y Telegram. Los 24 puntos
  del encargo y la búsqueda de texto heredado contradictorio.
- **Revisores:** Codex (vía `codex:codex-rescue`) y el subagente `revisor`, ambos de solo lectura: sin
  modificar ficheros, sin descargas, sin abrir datos forward.
- **Resultado agregado:** **0 BLOCKER**, 6 IMPORTANTES (4 del `revisor`, 2 de Codex), 11 MENORES,
  7 OBSERVACIONES. Todos verificados contra el repositorio y corregidos en la ficha, el decision log, el
  roadmap, `docs/gates.md`, el runbook de T-024 y `deploy/t024/README.md`, salvo MENOR-8 del `revisor`,
  que exige una decisión del propietario y queda como **OD-T25-10, abierta**.
- **Limitación declarada por el `revisor`:** leyó también los cambios de Codex ya aplicados sin
  commitear, y dice que no cambian ninguno de sus hallazgos.

## Codex (resumen literal de su informe)

Codex advierte que su revisión es corta: los logs muestran lecturas de la ficha, gates, decision log,
roadmap, T-024, PAPER-001, runbook, `deploy/t024/README.md`, `instalar.sh`, `p6_sim.py` y
`t024_decision.py`.

1. **IMPORTANTE** — `deploy/t024/README.md:109` y `docs/tareas/T-024-runbook-checkpoint.md:126` decían
   «Cambiar `T024_CODE_SHA` exige actualizar también este campo», contra D-77 (no cambian ni el sidecar
   ni `t024_code_sha`). Escenario: ante una incompatibilidad, un operador actualiza calendario y sidecar,
   el wrapper queda en verde y se rompe el contrato confirmatorio. **Corregido.**
2. **IMPORTANTE** — Runbook (línea 58) y README (línea 30) presentan el venv compartido como normal, sin
   la condición de D-77. Escenario: T-025 se despliega, cambia el venv y T-024 ejecuta el mismo código Git
   con dependencias distintas sin que `verificar_identidad()` lo detecte. **Corregido.**
3. **MENOR** — El estado del roadmap mezcla 2026-10-06 (`main = 4170bb4`) con D-75/D-77 y `f80ab28`.
   **Corregido.**
4. **MENOR** — «Estado de la cohorte» visible se confunde con el estado sellado de las posiciones.
   **Corregido:** «estado administrativo», nunca de posición.
5. **OBSERVACIÓN** — Las alertas de dato visibles, cruzadas con un `PASS`, permiten sospechar una
   suspensión. Inferencia exógena; **declarada** en D-76.

Recuento de Codex: BLOCKER 0 · IMPORTANTE 2 · MENOR 2 · OBSERVACIÓN 1.

## `revisor` (resumen literal de su informe)

Comprobaciones ejecutadas: `git diff --quiet 1a697c3 {f80ab28,HEAD} -- EXECUTOR_PATHS` vacío en los dos;
`0918cb3` ancestro de `f80ab28`; `requested_weight` cuadra con `p6_sim.py:627-630`; el orden de §7.2 es
el de `_process_entries`.

**Interpretación de §10.2:** correcta y sin OD nueva. La forma por libro choca con puntos sellados
explícitamente (`IGNORED_ALREADY_OPEN` = posición anterior abierta; `FILLED` = ya cerrada;
`INSUFFICIENT_CASH` y unidades/EUR = cash y equity). La lista de D-75 tiene una tensión interna y esa
es la única lectura compatible con las dos listas.

- **IMPORTANTE-1** — La vista ajustada por splits dividía otra vez barras ya ajustadas por
  `get_raw_history` (`market_data.py:109`; P6: `vintage.build_views`, `signal = execution.copy()`):
  calentamiento con un split en el lookback y barras tardías. **Corregido** (§3.3).
- **IMPORTANTE-2** — Cohortes con motores distintos sobre un solo `paper.db`: un `user_version`
  desconocido, venv compartido sin versiones fijadas, lock que hace perder pasadas. **Corregido** (§12,
  §13).
- **IMPORTANTE-3** — Una caída de la Pi de más de 5 (o 20) sesiones convertía datos disponibles en
  sesiones sin barra o en `DATA_LOSS_SUSPENDED`. **Corregido** (§7.2, §8.7); a ratificar por el
  propietario.
- **IMPORTANTE-4** — «Tenía observada la barra `t`» y el retraso europeo de D-21 (45-47 de 47 europeos
  sin la sesión anterior a las 06:02 y 07:32 UTC) desplazaban la vinculante a las 21:00 y el contexto a
  t−1. **Corregido** (§7.1).
- **MENOR-1** — La aplicación de la cláusula de canales laterales estaba escrita dentro de la decisión.
  **Corregido.**
- **MENOR-2** — `decision_ts` = fin de toda la ejecución; `TimeoutStartSec=1800` es de
  `intradia-bot.service`. **Corregido.**
- **MENOR-3** — T25-2 frente a `p6_sim.py:685`. **Corregido** (excepción declarada).
- **MENOR-4** — MAE/MFE a través de un split. **Corregido.**
- **MENOR-5** — Clave de `paper_open_check` sin motor. **Corregido.**
- **MENOR-6** — `SCALE_MISMATCH` sin resolución. **Corregido.**
- **MENOR-7** — Cierre ordinario y `CLOSED` como canal lateral. **Corregido.**
- **MENOR-8** — Ventana de P7 fijada y nunca consultada. **Exige decisión del propietario: OD-T25-10.**
- **MENOR-9** — Despliegue en el checkout habitual. **Corregido.**
- **O-1** barra provisional congelada (declarada); **O-2** OD-12 (a) frente a D-77 (anotado); **O-3**
  tabla de la ronda 2 (anotada); **O-4** dos «C0» en Telegram (nombres `-P6`); **O-5** texto heredado sin
  contradicciones vigentes; **O-6** sin defecto: ventana P7 futura siempre reservable, sizing y lotes sin
  look-ahead, idempotencia, FX, dividendo y split en la misma base, sin caché C-09, `T024_CODE_SHA`
  intacto.

Recuento del `revisor`: BLOCKER 0 · IMPORTANTE 4 · MENOR 9 · OBSERVACIÓN 6.

## Ronda 4b — confirmación sobre `264f845`

**Codex:** sus 2 IMPORTANTES y 2 MENORES, resueltos (cita `deploy/t024/README.md:115`, runbook `:132`,
README `:30`, runbook `:68`, roadmap `:23` y `:36`, ficha `:620` y `:893`). Sin BLOCKER ni IMPORTANTE
nuevo en §3.3, §7.1, §7.2/§8.7, §8.6, §12, §13, §15 y §10.7, ni look-ahead ni canal lateral nuevo;
contrasta `_process_entries` y `OPEN_EXIT` con `p6_sim.py`. MENOR nuevo: §5 (`paper_signal_evaluation`) y
el test de §16 seguían diciendo «fin de la ejecución original» para `decision_ts` (**corregido**).
Recuento: BLOCKER 0 · IMPORTANTE 0 · MENOR 2 (ese y OD-T25-10) · OBSERVACIÓN 0.

**`revisor`:** los 4 IMPORTANTES y los 8 MENORES corregibles de la ronda 4, resueltos; MENOR-8 pasa a
OD-T25-10. Nuevos:
- **IMPORTANTE N-1** — si una dependencia obliga a cambiar el venv de una cohorte viva, queda en
  `IDENTITY_MISMATCH` permanente, sin procesar stops, sin llegar a `DATA_LOSS_SUSPENDED` y sin poder
  cerrarse. **Exige decisión del propietario** (amplía OD-T25-8): **OD-T25-11, abierta**.
- **IMPORTANTE N-2** — una migración no aditiva (probable con `CHECK`) crea un segundo fichero, y el
  sellado y el consumo eran por fichero: una `P7_WINDOW` no sellaría las cohortes del otro. **Corregido**
  (tablas de referencia; registro único para todos los `paper*.db`; test).
- **MENOR N-3** `CLOSED` deducible (**corregido**); **N-4** apertura ex como sustituto del reajuste
  (**corregido**); **N-5** frescura sobre la descarga y texto de `decision_ts` (**corregido**); **N-6**
  estado de la ficha frente a OD-T25-10 (**corregido**; si la congelación espera, lo decide el
  propietario).
- **Observaciones:** test N/N+k en la CI de N+k y caída larga contada de golpe (**redactadas**).

Recuento del `revisor` sobre `264f845`: BLOCKER 0 · IMPORTANTE 2 · MENOR 4 · OBSERVACIÓN 2.

## Ronda 4c — confirmación final del `revisor` sobre `9bb84d3`

**APROBADO.** N-2 a N-6 resueltos (§5, §12, §13, §3.3, §7.1, estado de la ficha). OD-T25-11 recoge N-1
correctamente; su provisional C no fabrica salidas, no hace correr plazos, su `IDENTITY_MISMATCH` es igual
para todos los libros y no bloquea cohortes nuevas. Ningún BLOCKER ni IMPORTANTE nuevo. Observación: el
test N/N+k debe incluir un valor de referencia desconocido y N debe fallar cerrado (**incorporado**).

**Recuento final de defectos abiertos: BLOCKER 0 · IMPORTANTE 0 · MENOR 0 · OBSERVACIÓN 0** (la única,
incorporada). Decisiones pendientes del propietario: OD-T25-10, OD-T25-11, si la congelación espera a
ambas, ratificar §10.2 y ratificar los plazos de §8.7.
