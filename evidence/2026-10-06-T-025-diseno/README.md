# T-025 — Diseño y pre-registro propuesto (entrega documental, 2026-10-06)

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

- **Ficha:** `docs/tareas/T-025-shadow-paper-trading-forward.md`.
  **Decisiones:** D-73, D-74, OD-12 y OD-T25-1..9 en `docs/decision-log.md`.
  **Plan de la publicación:** `docs/tareas/PAPER-001-trade-edge-vs-portfolio.md`.
- **Base:** `main = 4170bb4`. La rama `research/t025-shadow-prereg` parte de `0918cb3` (PR #47, sin
  fusionar).
- **Estado:** pre-registro **propuesto, no congelado**. T-025 queda `BLOQUEADA_POR_OWNER` hasta que el
  propietario decida OD-T25-1..9 y OD-12, y después de una revisión final.

**Qué no se hizo**, a propósito:
- no se escribió código ni se crearon tablas;
- no se descargaron datos forward ni se observó ningún desenlace;
- no se ejecutó T-025;
- no se tocaron B2/S2, la Pi, el worktree de T-024, sus `EXECUTOR_PATHS` ni `T024_CODE_SHA`.

**Único cálculo hecho:** el solape de `signal_id` entre B2, S2 y C0 sobre los ledgers **ya
publicados** de P6 (`evidence/2026-10-03-T-022-p6/run/tablas/*_primaria_5pb-ledger.csv`), que son
desarrollo consumido. Resultado: B2 10.577, S2 2.440, C0 2.423; S2 ⊂ B2 y C0 ⊂ S2 ∩ B2.

| Fichero | Contenido |
|---|---|
| `revision-ronda1.md` | Codex y `revisor` sobre `b25f5ba`: 2 BLOCKER (base de precios; «consumido»), IMPORTANTES y MENORES |
| `revision-ronda2.md` | Los mismos revisores sobre `4eeb9a1`: sin BLOCKER; 3 IMPORTANTES nuevos (vista con splits, A-07, visibilidad) |
| La ficha, sección «Revisión independiente del diseño» | La ronda 3 (Codex, sobre `6a75bcf`): 1 IMPORTANTE (los instantes de la señal), corregido |
| `verificacion.txt` | Salida de `pytest -q`, `ruff check .` y `mypy advisor` |

Línea base antes de tocar nada (`0918cb3`): 1430 pasan y 20 se saltan; `ruff` y `mypy` limpios.
