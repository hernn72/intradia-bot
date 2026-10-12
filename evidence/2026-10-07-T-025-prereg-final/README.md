# T-025 — Congelación del pre-registro (2026-10-07)

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

**`T025_PREREG_SHA` = HEAD del commit de congelación que añade esta carpeta** (rama
`research/t025-shadow-prereg`, PR #48; el commit no puede contener su propio SHA). Misma convención que
`T024_PREREG_SHA`.

- **Contenido congelado:** `docs/tareas/T-025-shadow-paper-trading-forward.md` con OD-T25-1..12
  cerradas; D-73 a D-79 en `docs/decision-log.md` (D-75, D-76, D-77, D-78 y D-79 de este PR); las
  ratificaciones de D-78 (visibilidad estricta `MARKET_PASS`/`FILLED` y plazos de 5 y 20 sesiones);
  `docs/gates.md`, `docs/roadmap.md` y PAPER-001 coherentes.
- **Revisión:** rondas 1 a 5 en `evidence/2026-10-06-T-025-diseno/`; la revisión final de OD-T25-12 en
  `revision-final.md` (0 BLOCKER, 0 IMPORTANTE, 0 MENOR).
- **Verificación:** `verificacion.txt` (sobre `4efcba1`, el padre del commit de congelación, que solo
  añade documentación y evidencia): `pytest` 1430 pasan y 20 se saltan, `ruff` y `mypy advisor` limpios,
  diff de `EXECUTOR_PATHS` contra `1a697c3` vacío y `verificar_identidad()` = `1a697c3…`.
- **Enmiendas:** después de este commit, el pre-registro solo cambia mediante una decisión explícita del
  propietario (D-nn) que declare la enmienda.

**Qué no se hizo:** no se escribió código de T-025 ni se ejecutó; no se descargaron datos forward ni se
observó ningún desenlace; no se tocaron la Pi, B2, S2, C0, los `EXECUTOR_PATHS` ni `T024_CODE_SHA`; el PR
#48 no se fusionó.
