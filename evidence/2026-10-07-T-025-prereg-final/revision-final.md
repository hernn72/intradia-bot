# T-025 — Revisión final del pre-registro, centrada en OD-T25-12 (2026-10-07)

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

- **Objeto:** coherencia del pre-registro tras D-79 (OD-T25-12, alternativa A: ninguna excepción a GATE
  P7), en `fef0429`, y la confirmación de sus correcciones en `4efcba1`. Ficha T-025, `docs/gates.md`,
  `docs/decision-log.md` (D-78, D-79, OD-T25), `docs/roadmap.md` y PAPER-001.
- **Revisores:** el subagente `revisor` (que ya había hecho la ronda 5) y Codex, ambos de solo lectura,
  sin descargas ni datos forward.
- **Criterio (D-78 §5):** congelar solo con 0 BLOCKER y 0 IMPORTANTE.

## `revisor` sobre `fef0429`: APROBADO

Buscó «reutiliz», «sin haber visto», «OD-T25-12», «abierta», «solo con sesiones futuras» y «requisito 1».
- Ningún texto vigente deja reutilizar la ventana a una candidata congelada después de su primera sesión
  (D-78 y §17 OD-T25-10 conservan «sin haber visto» con la nota «precisado por D-79»; §10.7, T25-12, el
  test de §16, `gates.md` y el roadmap dicen lo mismo).
- GATE P7 no cambia; el requisito 1 sigue intacto.
- La frontera temporal y las reglas de `VIRGEN_REUTILIZABLE` son coherentes con D-78 y D-79.
- Ninguna OD de T-025 figura como abierta en texto vigente.
- **MENOR:** el estado del roadmap repetía la frase y omitía D-79. **Corregido.**
- **OBSERVACIONES:** las tablas históricas decían «OD-T25-12 abierta» (**anotadas**); con 9 plazas,
  «primera sesión» admitía dos lecturas (**precisado**: apertura más temprana, en cualquier plaza, de la
  fecha `sessions_from`).

Recuento: BLOCKER 0 · IMPORTANTE 0 · MENOR 1 · OBSERVACIÓN 2.

## Codex sobre `fef0429`

- **IMPORTANTE:** el historial de la ronda 5 de la ficha seguía diciendo «OD-T25-12, abierta» y «lo único
  que impide congelar es OD-T25-12», lo que podía leerse como una OD abierta. **Corregido** (redactado en
  pasado, «resuelta por D-79»).
- **MENOR:** roadmap (líneas 40 y 301) duplicado y sin D-77. **Corregido.**
- **MENOR:** handoff sin D-79. **Corregido.**
- **MENOR:** PAPER-001 sin D-79. **Corregido.**
- Sin texto operativo que permita la reutilización con una candidata congelada después; sin cambios a
  GATE P7; sin incoherencias en la frontera ni en `VIRGEN_REUTILIZABLE`.

Recuento: BLOCKER 0 · IMPORTANTE 1 · MENOR 3 · OBSERVACIÓN 0.

## Confirmación de Codex sobre `4efcba1`

Los cuatro hallazgos, resueltos; ninguno nuevo. La precisión de la primera sesión con varias plazas es
conservadora y coherente con D-79. Ninguna OD de T-025 presentada como abierta en estado vigente.

**Recuento final: BLOCKER 0 · IMPORTANTE 0 · MENOR 0 · OBSERVACIÓN 0.** Se cumple D-78 §5: el
pre-registro se congela.
