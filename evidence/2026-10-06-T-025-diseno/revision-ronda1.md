# T-025 — Revisión independiente, ronda 1 (2026-10-06)

Objeto: `git diff 0918cb3..b25f5ba` (rama `research/t025-shadow-prereg`), entrega solo documental.
Revisores, independientes del autor y en solo lectura:
- **Codex**, vía el plugin `codex:codex-rescue`, con el encargo de desmontar el diseño;
- el **subagente `revisor`** de Claude Code.

Ninguno creó ni modificó ficheros (los dos lo declaran). Cada hallazgo se verificó contra el
repositorio antes de corregirlo. Este documento resume sus informes con sus clasificaciones; las
correcciones están en la ficha, en la sección «Revisión independiente del diseño».

## Codex — veredicto: no aprobaría el pre-registro tal como está

- **BLOCKER:** contradicción en la definición de «consumido».
  - D-73 decía que consumido es lo que «intervino en el diseño o la selección», no lo que T-025 haya
    visto.
  - `gates.md` y la ficha §10 recogían la regla del propietario: «toda observación cuyo desenlace se
    consulte durante T-025 queda consumida».
  - **Verificado:** la rebaja era del autor y contradecía la regla del propietario.
- **IMPORTANTE:**
  - El orden de las comprobaciones de entrada de la ficha no es el de `p6_sim.py:616-636`, que
    comprueba `DATA_NOT_EXECUTABLE` primero. **Verificado.**
  - La ficha decía que lo visible de B2 y S2 es «lo mismo que T-024 §6.3 publica», pero T-024 §6.3
    solo publica conteos. **Verificado.**
  - PAPER-001 usaba «edge» sin desambiguarlo de «ventaja», contra su propia prohibición.
    **Verificado.**
- **MENOR:**
  - §3.8 enumeraba tres de las seis rutas de `EXECUTOR_PATHS`. **Verificado.**
  - Los campos para el dashboard y P10 sobreafirmaban la cobertura (falta `context_state`).
    **Verificado.**
- **OBSERVACIÓN:**
  - Los hashes y las cifras citadas cuadran: `politicas-finales.json`, `system-hashes.json`, D-70 y
    T-023.
  - La separación `paper.db` + `paper/` es correcta, condicionada a no duplicar lógica de `advisor`
    (INV-06).
  - Confirma que cualquier cambio en `EXECUTOR_PATHS` rompe `verificar_identidad()`.
- **Alcance declarado:** no comprobó a fondo idempotencia, concurrencia, dividendos, FX, lote ni
  MAE/MFE. Esos puntos se consideran no confirmados, no limpios.

## `revisor` — RESULTADO: REQUIERE CAMBIOS (1 BLOCKER, 7 IMPORTANTE)

- **B-1 BLOCKER: la fuente de precios tiene otra base de ajuste que P6.**
  - `market_data.py:83` usa `ticker.history()` con `auto_adjust` por defecto (`True`), y
    `bar_cache.py` lo envuelve, reancla en cada dividendo y no guarda dividendos.
  - P6 usa `auto_adjust=False` con los dividendos aparte (`p6.py:599-610`).
  - Consecuencias: el dividendo se cuenta dos veces, los reajustes por dividendo se tratan como split
    y los niveles se calculan sobre otra serie.
  - **Verificado** en `market_data.py:75-95`, `bar_cache.py:60-75` y `915-921`, y `p6.py:595-612`.
- **I-1:** la redefinición de «consumido» (la misma que el BLOCKER de Codex).
- **I-2:** la visibilidad era mayor que la de T-024 §6.3 (el mismo hallazgo que Codex).
- **I-3:** desellar por política permite que B2 revele a S2.
  - **Verificado y medido** en los ledgers de P6: S2 ⊂ B2 y C0 ⊂ B2 ∩ S2 por `signal_id`.
- **I-4:** las comprobaciones de apertura en `paper_entry_decision` delatan `IGNORED_ALREADY_OPEN`
  (`p6_sim.py:582-585`).
- **I-5:** canales laterales en una cohorte sellada: `max_seq`, `frontier_ts_utc`, los bloqueos y
  los recuentos de `DATA_GAP`, entre otros.
- **I-6:** una orden pendiente sobre una barra no validada choca con la regla de frontera.
- **I-7:** los dividendos no se persistían, así que la reconstrucción no era posible.
- **MENOR:**
  - **M-1:** el orden de las comprobaciones (el mismo hallazgo que Codex).
  - **M-2:** «C0 comparte casi toda la población de B2» es falso; C0 es el 23 % de B2. **Verificado.**
  - **M-3:** sobreafirmación de la cobertura de P10.
  - **M-4:** el hash de C0 no está en `politicas-finales.json` sino en `p6.py:95-100`. **Verificado.**
  - **M-5:** una transacción por evento rompe el sizing al reanudar a mitad de lote.
  - **M-6:** claves de idempotencia frágiles.
  - **M-7:** `IGNORED_ALREADY_OPEN` aparecía en dos instantes distintos.
  - **M-8:** `start_ts_utc` es ambiguo con 9 plazas.
  - **M-9:** plantilla del método incompleta.
- **OBSERVACIÓN:**
  - **O-1:** cambios sin commit durante la revisión; eran las correcciones de la ronda de Codex.
  - **O-2:** la evidencia de la entrega estaba vacía.
  - **O-3:** el tag de T-025 saca la Pi de `v0.4.1`.
  - **O-4:** riesgo de dos `signal_id` para la misma sesión.
  - **O-5:** exigir `observed_at < τ` en las entradas de la evaluación.
- **Intentos de refutación sin defecto:**
  - look-ahead del timer (`Persistent=false`, horarios, FX);
  - T-025 y T-024 frente a P7;
  - separación entre real y paper;
  - reglas de salida, desempate, costes y FX regla A frente a P6;
  - doble apertura;
  - migraciones;
  - versionado;
  - todos los hashes y cifras citados.

## Medición hecha para I-3 y M-2

Sobre `evidence/2026-10-03-T-022-p6/run/tablas/{B2,S2,C0}_primaria_5pb-ledger.csv`, contando los
`signal_id` distintos:
- B2 tiene 10.577, S2 2.440 y C0 2.423;
- C0∩B2 = 2.423, C0∩S2 = 2.423 y S2∩B2 = 2.440.

Son evidencia de desarrollo ya consumida y publicada; no se abre ningún dato forward.
