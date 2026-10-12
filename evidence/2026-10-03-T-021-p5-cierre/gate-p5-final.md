# GATE P5 — Regiones robustas: matriz final

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

Texto literal de `docs/gates.md`:

> Requisitos: superficies de parámetros publicadas; configuraciones descartadas por fragilidad o
> dependencia de un solo mercado listadas con motivo; conjunto de políticas candidatas ≤ 5, cada una
> con su `config` completa y hash.

| # | Requisito literal | Estado | Evidencia |
|---|---|---|---|
| 1 | superficies de parámetros publicadas | **SATISFECHO** | `evidence/2026-10-02-T-021-p5/run/tablas/superficie.tsv` (13 vecinos) y `clases.tsv`, transcritas completas en `resultado-p5.md`, junto con la rejilla y las ausencias (`../2026-10-02-T-021-p5/preflight/rejilla-semiplanos.md`). B2 8/8 y S2 5/5 ACEPTABLE. Las celdas centrales B2 y S2 son las de P4, reproducidas 162/162 en el preflight. |
| 2 | configuraciones descartadas por fragilidad o dependencia de un solo mercado listadas con motivo | **SATISFECHO** | `resultado-p5.md`, sección «Descartes», y D-67: candidatas descartadas por FRÁGIL, ninguna (F1–F6 = False en B2 y S2); por DEPENDIENTE_DE_MERCADO, ninguna (6/6 LOCRO estimables con IC95 inferior > 0); NO_CONCLUYENTE, ninguna. Las 3 ausencias de S2 se listan aparte como `AUSENCIA_ESTRUCTURAL` por RR < 1,5, fijadas en D-66: no son descartes por resultado. Los 13 vecinos son diagnósticos, no candidatas. |
| 3 | conjunto de políticas candidatas ≤ 5 | **SATISFECHO** | `[B2, S2]`, n = 2 (`p5-resultado.json` → `survivors`; `criterio.tsv`). |
| 4 | cada una con su `config` completa y hash | **SATISFECHO** | `politicas-finales.json`: por política, `id`, `advisor_config_hash`, `policy_payload` completo, `canonical_json` y `policy_sha256` regenerado desde él. B2 `c5d60f44…1760` / `d5d6a533…01b9`; S2 `8a151b80…0dbb` / `e37ee933…4d11`. Coinciden con la marca y con el preflight. |

**Revisión final independiente:** 0 BLOCKER, 0 IMPORTANTE, 0 MENOR, 1 OBSERVACIÓN sin impacto
(`revision-final.md`).

**Veredicto: GATE P5 CRUZADO (D-68).** Desbloquea P6, que no se inicia.
