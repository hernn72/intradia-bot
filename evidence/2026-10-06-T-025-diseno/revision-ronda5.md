# T-025 — Revisión independiente final, ronda 5 (2026-10-07)

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

- **Objeto:** el estado completo del pre-registro tras D-78 (OD-T25-10 y OD-T25-11 cerradas,
  visibilidad y plazos ratificados), en `6d57afa`. Por D-78 §5, `T025_PREREG_SHA` solo se congela si
  esta revisión termina con 0 BLOCKER y 0 IMPORTANTE.
- **Revisores:** Codex y un subagente `revisor` nuevo, sin contexto de las rondas anteriores; ambos de
  solo lectura, sin descargas ni datos forward.
- **Resultado:** **no se congela.** El `revisor` encontró 5 IMPORTANTES: cuatro se corrigen dentro de
  D-78 y uno exige una decisión nueva del propietario, que queda como **OD-T25-12, abierta**.

## Codex

BLOCKER 0 · IMPORTANTE 0 · MENOR 2 · OBSERVACIÓN 0. Advierte que es una única pasada de lectura que no
repasó explícitamente cada canal lateral de la lista.
1. **MENOR** — `docs/roadmap.md` (líneas 26, 40 y 301) seguía con el estado anterior a D-78.
   **Corregido.**
2. **MENOR** — PAPER-001 (línea 33) citaba T-025 sin D-78. **Corregido.**

## `revisor`

Leyó la ficha entera, el diff `dbeb67f..6d57afa`, D-78, GATE P7 y la ronda 4, y contrastó
`p6_sim.py:595-660` y `market_data.py:96-140`. Sin defecto en: `MARKET_PASS` frente a `FILLED`,
`requested_weight` (`p6_sim.py:626-633`), la ventana abandonada y su sellado, `t024/forward` y el estado
de los demás documentos.

- **I-1 IMPORTANTE** — un fallo de red, DNS o librería (o `yfinance` roto) produce la misma respuesta
  vacía y el mismo `ValueError` que una barra ausente (`market_data.py:132-135`), y contaría como
  `PROVIDER_DATA_MISSING` para los 90 activos, contra D-78. **Corregido** (`FETCH_FAILURE`).
- **I-2 IMPORTANTE** — «una caída larga se cuenta de golpe» (§8.7) alcanzaba los plazos de 5 y 20 al
  volver de una caída de 25 sesiones, contra D-78. **Corregido.**
- **I-3 IMPORTANTE** — `paper_environment_epoch.first_event_ts_utc` y el instante visible de
  `ENGINE_UNRUNNABLE` «desde el último evento válido» delataban la frontera, y con `paper_data_alert` la
  posición. **Corregido.**
- **I-4 IMPORTANTE** — la comprobación de interpretación exigía identidad de datos: un split o una barra
  provisional durante la investigación daría `FAIL` y `ENGINE_UNRUNNABLE`. **Corregido** (criterio de
  interpretación fijado antes).
- **I-5 IMPORTANTE** — reutilizar una ventana de P7 abandonada con una candidata congelada después choca
  con GATE P7 (requisito 1 y frontera de sesiones futuras); «sin haber visto» solo se demuestra con
  `paper_outcome_access`. **Exige decisión del propietario: OD-T25-12, abierta.**
- **M-1** hashes deterministas visibles (**corregido**, compromisos con nonce); **M-2** causas de
  `SIGNAL_NOT_EVALUATED` (**corregido**); **M-3** `DATA_NOT_EXECUTABLE` frente a la espera
  (**corregido**); **M-4** órdenes pendientes en `ENGINE_UNRUNNABLE` (**corregido**); **M-5** texto sin
  D-78 (**corregido**); **M-6** `paper_bar_request` como canal de tiempos (**corregido**).
- **O-1** bit `PASS`/`FAIL` dependiente del libro (**declarado**); **O-2** el replay repite la secuencia
  de `paper_run` (**escrito**).

Recuento del `revisor` sobre `6d57afa`: BLOCKER 0 · IMPORTANTE 5 · MENOR 6 · OBSERVACIÓN 2.
