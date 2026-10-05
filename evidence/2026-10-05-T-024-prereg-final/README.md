# T-024 — Congelación del pre-registro (Edge relativo al drift)

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

- **`T024_PREREG_SHA`** = HEAD del commit que añade este directorio. El commit no puede contener su
  propio SHA: se identifica en el PR #44 y en la respuesta al propietario.
- Especificación: `docs/tareas/T-024-edge-relativo-al-drift.md`. Decisiones: D-71 (opción E de T-023)
  y D-72 (cierra OD-T24-1 a OD-T24-12) en `docs/decision-log.md`.
- Revisión: `revision-final.md`. Hubo tres rondas sobre la ficha de diseño y una revisión final del
  pre-registro completo tras D-72, todas de Codex; la final da 0 BLOCKER y 0 IMPORTANTE.

**T-024 no está implementado ni medido.**
- No existen `advisor/research/t024.py` ni el código de captura.
- No se ha congelado ninguna cosecha forward.
- No se ha calculado ningún desenlace ni ninguna métrica de T-024, ni sobre la cosecha consumida
  `071ddb2b…` ni sobre datos posteriores al 2026-08-27.

Siguientes pasos, cada uno con autorización aparte:
1. código de captura y de reconfirmación, y tests sobre desarrollo, más una revisión de look-ahead →
   `T024_CODE_SHA`;
2. acumulación forward con checkpoints mensuales de solo conteos;
3. la ejecución decisoria única de la mirada 1 y, si toca, la mirada final.

P6 sigue vinculante: B2 y S2 `NO PASA`, salida `[]`, P7 BLOQUEADO (D-70). Producción sin cambios: C0,
Score v1 70/60, Score v2 inactivo y Pi `v0.4.1`.
