# PAPER-001 — From Trade-Level Edge to Portfolio-Level Underperformance (P-01)

Estado: **PENDIENTE — ficha y plan.** No hay manuscrito. No se recalcula, re-simula ni descarga nada.
Agente: Opus (redacción) → revisión independiente → propietario.
Línea / fase: P-01 (línea P, velocidad «publicación», D-73).
Gate al que contribuye: ninguno. Documenta resultados ya cerrados; no cambia ninguno.

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

## Objetivo

Un manuscrito (preprint v1) que explique, solo con evidencia ya publicada en el repositorio, por qué B2
y S2 muestran **edge por operación** (definido abajo) y robustez local en P4/P5 y, aun así, no lo
convierten en alfa de cartera en P6.

**Vocabulario fijado.** «Edge por operación» significa exactamente: `mean_R_local > 0` y
`profit_factor > 1` medidos en desarrollo sobre la cosecha consumida, condicionados al universo 2026.
**No** significa «ventaja demostrada»: P6 da a las dos `NO PASA` (D-70), con la causa formal
`excess_CAGR_pp ≤ 0`, y P7 no se ha hecho. El texto nunca usa «ventaja» ni «el sistema funciona» para B2
o S2.

## Pregunta

> ¿Por qué una estrategia con expectancy positiva, profit factor > 1 y robustez local puede no generar
> alfa de cartera?

## Evidencia y su estatus (vinculante en todo el texto)

| Estatus | Fuente | Qué aporta |
|---|---|---|
| **Confirmatorio** | P2 (A-02, D-42/D-43), P3 (T-019, D-61/D-62: NO CONCLUYENTE), P4 (T-020, D-64/D-65), P5 (T-021, D-67/D-68: B2 y S2 ROBUSTAS), **P6 (T-022, D-70)** | Cada fase con su pre-registro, su ejecución única y su gate. P6: B2 PF 1,3995, mean_R_local 0,2478, max DD −16,60 %, CAGR 18,03 %, exceso −15,77 pp; S2 PF 1,4044, mean_R_local 0,2383, max DD −11,23 %, CAGR 15,08 %, exceso −18,72 pp; benchmark CAGR 33,80 %, max DD −26,22 % (D-70) |
| **Post hoc** | T-023 (`evidence/2026-10-05-T-023-diagnostico-post-p6/`) | Dónde se abre la brecha (2023–2025), participación (exposición media B2 0,8371, S2 0,6054, C0 0,5313), saturación de cash de B2, rechazos `ABOVE_MAX_ENTRY` de S2, puente de todas las barras. Etiquetas `OBSERVADO` / `COMPATIBLE_CON` / `NO_IDENTIFICABLE`, que el paper conserva |
| **Prospectivo, sin resultado** | T-024 (D-71/D-72, D-76), T-025 (D-73/D-74, D-75, D-78, D-79) | Solo el diseño y el calendario. Ningún número. La v1 dice explícitamente que no hay resultado forward. T-024 se describe como **diseño confirmatorio pre-registrado con visibilidad parcial ex ante del propietario, declarada antes de observar desenlaces** (D-76) |

Ninguna cifra post hoc se presenta como confirmatoria, y ninguna afirmación causal sale de T-023.

## Limitación obligatoria: pérdida de los CSV de la cosecha

Los **126 CSV** de la cosecha `071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841` se
perdieron en el portátil el 2026-10-06, **después** de P6 y T-023
(`evidence/2026-10-06-incidente-perdida-vintage/`). Permanecen los commits, el manifiesto versionado con
sus hashes, los outputs, los ledgers publicados y la evidencia de cada fase. Por tanto:

- las cifras publicadas siguen siendo trazables a sus artefactos y hashes;
- **el cálculo ya no se puede reproducir desde los datos de entrada originales**;
- **no se reconstruye ni se vuelve a descargar ese vintage fingiendo que es el original.** Una descarga
  nueva tendría otro `data_vintage_id` (revisiones de `yfinance`) y, si se usara para algo, se
  identificaría como tal.

El apéndice de reproducibilidad lo declara en su primera línea.

## Plan del manuscrito

1. **Introducción:** edge por operación frente a alfa de cartera; por qué importa para sistemas
   minoristas con capital finito.
2. **Datos y universo:** 90 activos, ventana de P6, sesgos de supervivencia y selección (roadmap,
   sección «Universo»), coste y slippage.
3. **Metodología:** laboratorio pre-registrado P2–P6, ejecución única por fase, gates; P6 como sistema
   completo (T-022 §7–§19).
4. **Resultados confirmatorios:** P4/P5 (edge y robustez local) y P6 (cartera frente a buy-and-hold).
5. **Diagnóstico post hoc (T-023):** brecha temporal, participación, presión de cash, puente de todas
   las barras, con sus etiquetas.
6. **Discusión:** mecanismos compatibles (R medido contra el propio stop frente al drift del activo;
   ocupación; asignación), qué no se puede identificar, y por qué T-024 y P6-bis son las preguntas
   siguientes.
7. **Limitaciones:** universo 2026; una sola ventana y un régimen alcista fuerte del benchmark; pérdida
   de los CSV; `yfinance`; dividendos con tipo de cambio constante en Xetra; fraccionales y liquidación
   inmediata.
8. **Trabajo prospectivo:** T-024 y T-025, sin resultados en la v1.
9. **Apéndice de reproducibilidad:** SHAs (`P*_PREREG_SHA`, `P*_CODE_SHA`, `P6_RUN_HEAD_SHA`,
   `P6_RUN_EVIDENCE_SHA`), `P6_DATA_ID`, `system_sha256`, hashes de ficheros de `evidence/`, y la
   declaración de la pérdida.

**Tablas:** resultados P6 (D-70); P4/P5 por política; T-023 por año y por tramo de exposición.
**Figuras:** solo a partir de los CSV y ledgers ya publicados en `evidence/`; cada figura nombra su
fichero de origen y su hash.

## Qué NO debe hacerse

- Recalcular, re-simular o volver a descargar nada.
- Presentar T-023 como confirmatorio o T-024/T-025 con cualquier cifra.
- Afirmar que B2 o S2 tienen ventaja, o que «el sistema funciona».
- Omitir la etiqueta de universo o la pérdida de los CSV.

## Criterio de aceptación de la v1

Cada número del texto enlaza a un fichero de `evidence/` y coincide con él; el estatus de cada
resultado es el de la tabla de arriba; la limitación de los CSV figura en limitaciones y en el apéndice;
revisión independiente sin BLOCKER ni IMPORTANTE.

## Dependencias previas

GATE P6 (D-70) y T-023 cerrados. No depende de T-024 ni de T-025.

## Archivos probables

`docs/papers/PAPER-001/`; solo lectura de `docs/` y `evidence/`.

## Invariantes que no pueden romperse

INV-15 (no se consulta ningún holdout), INV-16 e INV-20 (ningún número sin su estatus), y la etiqueta
de universo en todas las tablas.

## Tests, verificación contra datos reales e impacto

No aplica: no hay código, ni descarga, ni cambio de comportamiento. La verificación es la tabla de
trazabilidad número → fichero de `evidence/` → hash.

## Entregable y ubicación

`docs/papers/PAPER-001/` (manuscrito en Markdown y figuras generadas desde `evidence/`), con un PR propio.
**v2/final (P-02):** incorpora T-024, T-025, P7 y P10 cuando existan.

## Handoff

Ficha creada el 2026-10-06 dentro del PR de T-025. Siguiente paso, con autorización: redactar el
esqueleto del manuscrito y la tabla de trazabilidad número → fichero.
