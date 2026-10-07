# T-025 — Revisión independiente, ronda 2 (2026-10-06)

Objeto: `git diff b25f5ba..4eeb9a1` (las correcciones de la ronda 1). Los mismos revisores, en solo
lectura: Codex y el subagente `revisor`. Ninguno modificó ficheros. Cada hallazgo se verificó contra el
repositorio antes de corregirlo.

## Codex — no congelaría todavía; ningún BLOCKER nuevo

- **IMPORTANTE:**
  - `docs/roadmap.md` (A-07) conservaba la versión débil de «consumido».
  - La visibilidad por señal de B2 y S2 selladas (niveles y `paper_open_check` por activo) excede lo
    que T-024 §6.3 y su runbook publican, que son conteos agregados; solo estaba declarada.
- **MENOR:** la lista de campos del dashboard estaba incompleta.
- **Resueltos de la ronda 1:** el orden de comprobaciones, «edge» en PAPER-001, `EXECUTOR_PATHS`, la
  base de precios (`get_raw_history` frente a `p6.py:599-610` y `vintage.py:370-379`) e
  `IGNORED_ALREADY_OPEN` en la fase `SIGNAL`.
- **Alcance declarado:** no comprobó OD-T25-9, idempotencia, look-ahead, dividendos ni FX en esta
  ronda.

## `revisor` — REQUIERE CAMBIOS; ningún BLOCKER

- **Ronda 1:** B-1, I-1..I-7, M-1..M-9 y O-3..O-5 resueltos de verdad. O-2 seguía sin resolver.
- **N-1 IMPORTANTE:** tras un split, la serie de señal mezclaría dos escalas: la primera observación
  vigente choca con el reajuste hacia atrás de `yfinance`. Variante: un dividendo tardío tras
  `SPLIT_ADJUST` se abonaría `r` veces.
- **MENOR:**
  - **N-2:** la base del contexto point-in-time no estaba fijada. **Verificado:**
    `fetch_point_in_time_market_context` usa `get_history`, mientras que P6 usó
    `PointInTimeContextResolver` sobre cierres sin ajuste (`p4.py:536-542`).
  - **N-3:** `paper_outcome_access` no guardaba las sesiones consultadas.
  - **N-4:** OD-T25-4 infravaloraba la fuga hacia S2.
  - **N-5:** §18 citaba la caché.
  - **N-6:** faltaba la salida de pytest, ruff y mypy.
  - **N-7:** las entradas de una reevaluación no estaban acotadas a su pasada.
- **OBSERVACIÓN:**
  - OD-T25-9 no contradice la regla del propietario.
  - Bajo la opción A, consultar BH también consume la sesión.
  - Falta qué pasa si T-024 no se resuelve.
  - La frontera y el límite de 5 sesiones son coherentes.
- **Refutaciones sin defecto:**
  - la base de precios frente a P6;
  - `paper_open_check` frente a la ceguera;
  - el desellado conjunto (C0 ⊂ S2 ⊂ B2, verificado);
  - la transacción por lote;
  - `content_sha256`;
  - la coherencia entre documentos;
  - `EXECUTOR_PATHS` idénticos a `1a697c3`.

Las correcciones están en la tabla «Ronda 2» de la ficha.
