# GATE P4 — matriz final de requisitos

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

- `P4_PREREG_SHA = 48b884722ef027e99857a4e65f9ab6b11da4758f`
- `P4_CODE_SHA = 3df8230d7806dde4151b56501641a1524a3df9d8`
- `P4_RUN_HEAD_SHA = c2c52b11c60bb8dfd08d8cb33d5f6f251e9bf2c0`
- `P4_RUN_EVIDENCE_COMMIT = cfa365da468edd04f0ccf4d5f20b657382078cbd`
- Resultado registrado en D-64. Revisión final, tras su vuelta de cierre (`revision-final.md`):
  **0 BLOCKER, 0 IMPORTANTE, 0 MENOR y 1 OBSERVACIÓN**.

Los requisitos se citan literalmente de `docs/gates.md`.

| # | Requisito | Estado | Evidencia |
|---|---|---|---|
| 1 | Variantes de stop, objetivo y entrada comparadas **pareadas por `signal_id`** con bootstrap por bloques (P2.6), sobre el mismo `data_vintage_id`. | **SATISFECHO** | Ver el detalle 1 |
| 2 | Cada variante publica ΔR medio, IC por bloque, dispersión y heterogeneidad; ninguna se elige por el promedio si la heterogeneidad es alta sin explicar en qué régimen, región o volatilidad mejora. | **SATISFECHO** | Ver el detalle 2 |
| 3 | **Holgura de entrada** medida (D-06): para cada geometría, `entry_max_rr − price` en ATR y fracción de señales que serían `ABOVE_MAX_ENTRY` a la apertura siguiente. | **SATISFECHO** | Ver el detalle 3 |
| 4 | Número total de comparaciones publicado. | **SATISFECHO** | Ver el detalle 4 |

## Detalle de cada requisito

### 1. Variantes pareadas con bootstrap por bloques

- **Stop:** S1 y S2. **Objetivo:** B2 y B1 (esta solo descriptiva). **Entrada:** E1, con `R = 0`
  para las no ejecutadas y el mismo `signal_id`.
- Todas se emparejan con C0 por `signal_id` sobre la misma cosecha `071ddb2b…` y la misma población
  de 101.251 señales (`78024050…`).
- Pares: B2 101.226, S1 101.185, S2 101.225, E1 101.226 y B1 101.226. Ningún `signal_id` queda sin
  contador ni motivo (`run/tablas/emparejamiento.tsv`).
- Bootstrap P2.6 por bloques completos de 60 sesiones:
  - Bonferroni con 0,9875 y 20.000 remuestreos en B2, S1, S2 y E1;
  - IC95 con 2.000 remuestreos en todo lo demás.
- Revisión final, puntos C y D.

### 2. ΔR, IC, dispersión y heterogeneidad publicados

- Las cinco comparaciones publican ΔR, IC, dispersión, τ y la bandera de heterogeneidad
  (`run/tablas/estimaciones.tsv`).
- La bandera sale **ALTA en las cinco** y se explica en `resultado-y-heterogeneidad.md`:
  - **B2 y S2:** el signo es positivo en las cinco regiones y en los tres terciles; CAUTELA queda
    neutro; el efecto es mayor por señal en RISK_OFF y positivo en RISK_ON; en S2, `stop_basis`; hay
    dispersión por activo, sin ningún activo con el IC95 entero negativo.
  - **B1 y S1:** también discutidas.
  - **Limitación conocida del instrumento:** puede confundir el solapamiento con heterogeneidad
    (D-63).
- No se elige nada «por el promedio»: B2 y S2 pasan por el criterio pre-registrado, en el que la
  heterogeneidad no veta (D-63), y no se crea ninguna política por estrato.

### 3. Holgura de entrada (D-06)

`preflight/p4-preflight.json` → `holgura_d06`, para C0, B1, B2, S1 y S2, global y por región:
- `entry_max_rr − P` y holgura efectiva, en precio, ATR y %;
- qué límite manda;
- categorías a `open(t+1)`;
- distancia de `ABOVE_MAX_ENTRY` en ATR.

`ABOVE_MAX_ENTRY` a `open(t+1)`: C0 46.744, B1 26.552, B2 4.680, S1 48.949 y S2 44.156, de 101.251
señales. Revisión final, punto G.

### 4. Número total de comparaciones

- **447** comparaciones: B1 110, B2 110, S1 113, S2 113 y E1 1.
- **4** confirmatorias.
- El recuento derivado de las salidas coincide con el previsto en el preflight
  (`run/tablas/recuento.tsv`, `recuento_coincide = true`).

## Decisión mecánica

- **Requisitos:** los cuatro, SATISFECHOS.
- **Revisión final:** 0 BLOCKER y 0 IMPORTANTE.
- **Conclusión: GATE P4 CRUZADO (D-65).**
  - Pasan a P5 las candidatas **B2 y S2**.
  - S1 queda descartada.
  - E1 sale NO CONCLUYENTE.
  - B1 es solo descriptiva.
- **Lo que no cambia:** producción. B2 y S2 son candidatas de investigación para P5.
