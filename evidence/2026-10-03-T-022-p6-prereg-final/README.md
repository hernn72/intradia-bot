# T-022 / A-06 — Congelación del pre-registro de P6

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

- **`P6_PREREG_SHA`** = HEAD del commit que añade este directorio. El commit no puede contener su propio
  SHA: se identifica en el PR #40 y en la respuesta al propietario.
- Especificación: `docs/tareas/T-022-p6-sistema-completo.md`. Decisiones: D-69 en
  `docs/decision-log.md`, con las «Precisiones de la revisión final» ratificadas por el propietario.
- Censo estructural sin desenlaces: `evidence/2026-10-03-T-022-p6-diseno/`.
- Revisión final: `revision-final.md`. Dos revisores independientes; 0 BLOCKER y 0 IMPORTANTE en la
  vuelta 4.

**P6 no está implementado ni ejecutado.** No existe `p6.py`, no se ha descargado FX ni sector y no se
ha calculado ningún desenlace. Siguientes pasos, cada uno con autorización aparte:
1. sidecar FX con la petición fija y mapa de sector → `P6_DATA_ID`;
2. `p6.py`, tests y preflight, más una revisión de look-ahead;
3. la única ejecución confirmatoria.

Producción sin cambios: C0, Score v1 70/60, Score v2 inactivo y Pi `v0.4.1`.
