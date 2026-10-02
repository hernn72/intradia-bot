# P4 — resultado congelado y discusión de la heterogeneidad

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

- `P4_PREREG_SHA = 48b884722ef027e99857a4e65f9ab6b11da4758f`
- `P4_CODE_SHA = 3df8230d7806dde4151b56501641a1524a3df9d8`
- `P4_RUN_HEAD_SHA = c2c52b11c60bb8dfd08d8cb33d5f6f251e9bf2c0`
- `P4_RUN_EVIDENCE_COMMIT = cfa365da468edd04f0ccf4d5f20b657382078cbd`

**Fuente única de las cifras:** `evidence/2026-10-01-T-020-p4/run/`. Los estratos salen de
`run/tablas/estimaciones.tsv` y se copian literalmente con `leer_estratos.py`, un lector puro que no
calcula ninguna estimación. Las tablas completas, incluidos los 90 activos de cada geometría, están
en `estratos-congelados.md`.

**Ningún valor es nuevo:**
- no se ha vuelto a ejecutar P4;
- no se ha recalculado ninguna variante;
- no se ha añadido ningún intervalo;
- no aparece ningún estrato que no estuviera pre-registrado.

Todas las filas de estratos son **descriptivas**: IC95, 2.000 remuestreos y bloque de 60 sesiones.
No hay significación múltiple por estrato. Las cifras de seis decimales son las celdas literales del
TSV; en el texto se redondean a cinco.

## 1. Resultado

El resultado es el registrado en **D-64**:

| Comparación | ΔR | Intervalo | Resultado |
|---|---|---|---|
| B2 vs C0 | +0,0717 | Bonferroni 98,75 % [+0,0061, +0,1356] | **PASA A P5** |
| S2 vs C0 | +0,0348 | Bonferroni 98,75 % [+0,0076, +0,0597] | **PASA A P5** |
| S1 vs C0 | −0,0411 | Bonferroni [−0,0708, −0,0096] | NO PASA (falla 1, 2, 5 y 8) |
| E1 | −0,0491 | Bonferroni [−0,1078, +0,0120] | NO CONCLUYENTE (no es geometría ni candidata) |
| B1 vs C0 | +0,0206 | IC95 [+0,0047, +0,0363] | solo descriptiva |

B1 lleva la etiqueta «previamente expuesta en esta misma cosecha; no confirmatoria; no elegible para
sustituir C0».

**Candidatas para P5: B2 y S2.** Pasan las dos, sin elegir entre ellas ni ordenarlas por ΔR.

## 2. B2 — estratos

### Región

| Región | ΔR | IC95 |
|---|---|---|
| ASIA | +0,07665 | [+0,00400, +0,15173] |
| EMERGING_MARKETS | +0,02235 | [−0,14738, +0,19344] |
| EUROPA | +0,06019 | [+0,00641, +0,12199] |
| GLOBAL | +0,11104 | [−0,00841, +0,23521] |
| USA | +0,07622 | [+0,01481, +0,13599] |

- El signo puntual es positivo en las cinco regiones, así que el efecto no parece depender de una
  sola.
- ASIA, EUROPA y USA tienen el IC95 entero por encima de 0.
- EMERGING_MARKETS y GLOBAL son imprecisos. EMERGING_MARKETS es además prácticamente un solo activo,
  limitación ya pre-registrada (OD-P4-11, O-3).
- Son estimaciones descriptivas: no se afirma significación múltiple por región.

### Régimen point-in-time

| Régimen | ΔR | IC95 | Bloques con pares |
|---|---|---|---|
| CAUTELA | −0,00294 | [−0,10195, +0,08934] | 13 |
| RISK_OFF | +0,24479 | [+0,15879, +0,33072] | 7 |
| RISK_ON | +0,08495 | [+0,02730, +0,13908] | 17 |

- El efecto no es uniforme por régimen. CAUTELA no muestra ninguna ventaja detectable.
- El efecto observado se concentra sobre todo en RISK_OFF y aparece también en RISK_ON. Esto
  explica parte de la heterogeneidad.
- RISK_OFF descansa en solo 7 bloques con pares. Su magnitud debe leerse con esa limitación.
- **No se crea ninguna política «solo RISK_OFF/RISK_ON»:** sería post hoc.
- NO_CALCULABLE_CONTEXT se contó y permanece en la primaria, sin régimen estimado.

### Volatilidad (terciles de ATR/P, cortes fijados en el preflight)

| Tercil | ΔR | IC95 |
|---|---|---|
| T1 | +0,04676 | [−0,00932, +0,10357] |
| T2 | +0,07133 | [+0,00864, +0,13333] |
| T3 | +0,10311 | [+0,04624, +0,16160] |

- El signo es positivo en los tres terciles, y la magnitud crece con ATR/precio.
- T1 es el menos preciso: su IC95 incluye el 0.
- No se crea ningún umbral de volatilidad.

### Activos

- Son 90 activos: **75 con ΔR puntual positivo** y 15 negativo.
- **20** tienen el IC95 entero por encima de 0 y **ninguno** entero por debajo.
- Hay una dispersión importante entre activos.
- La tabla completa de los 90 está en `estratos-congelados.md` (§ B2 › activos), sin seleccionar
  ejemplos.

## 3. S2 — estratos

### Región

| Región | ΔR | IC95 |
|---|---|---|
| ASIA | +0,03983 | [+0,00370, +0,07614] |
| EMERGING_MARKETS | +0,00973 | [−0,08251, +0,09428] |
| EUROPA | +0,03834 | [+0,01504, +0,06100] |
| GLOBAL | +0,03428 | [−0,03244, +0,10424] |
| USA | +0,02969 | [+0,00202, +0,05520] |

- Las cinco estimaciones puntuales son positivas, así que el efecto no parece depender de una sola
  región.
- ASIA, EUROPA y USA tienen el IC95 entero por encima de 0. EMERGING_MARKETS y GLOBAL son
  imprecisos.

### Régimen point-in-time

| Régimen | ΔR | IC95 | Bloques con pares |
|---|---|---|---|
| CAUTELA | +0,00148 | [−0,05394, +0,05479] | 13 |
| RISK_OFF | +0,08760 | [+0,05845, +0,11518] | 7 |
| RISK_ON | +0,04132 | [+0,01906, +0,06184] | 17 |

- CAUTELA queda prácticamente neutro. El efecto positivo aparece sobre todo en RISK_OFF, sobre 7
  bloques, y también en RISK_ON.
- No se crea ninguna política por régimen.

### Volatilidad

| Tercil | ΔR | IC95 |
|---|---|---|
| T1 | +0,02960 | [+0,00485, +0,05163] |
| T2 | +0,03158 | [+0,00442, +0,05787] |
| T3 | +0,04493 | [+0,02067, +0,06675] |

Los tres terciles tienen signo positivo y el IC95 entero por encima de 0.

### Base del stop (par C0/S2)

| Par | ΔR | IC95 |
|---|---|---|
| MIXTO | +0,01512 | [−0,01447, +0,04470] |
| SOP/SOP | +0,04916 | [+0,01537, +0,07997] |
| VOL/VOL | +0,03153 | [+0,00753, +0,05346] |

- El efecto aparece tanto cuando los dos stops son por volatilidad como cuando los dos se apoyan en
  soporte. El subconjunto mixto es menos claro.
- Esto ayuda a explicar la heterogeneidad, pero no autoriza ninguna política condicionada por
  `stop_basis`.

### Activos

- Son 90 activos: **73 con ΔR puntual positivo** y 17 negativo.
- **17** tienen el IC95 entero por encima de 0 y **ninguno** entero por debajo.
- La tabla completa está en `estratos-congelados.md` (§ S2 › activos).

## 4. S1 como contraste descriptivo

No es un análisis nuevo, sino la lectura de los mismos estratos ya calculados. El deterioro de S1 es
amplio:
- **Región:** ASIA, EUROPA y USA son negativas, con el IC95 entero por debajo de 0.
- **Volatilidad:** los tres terciles son negativos, con el IC95 entero por debajo de 0.
- **Régimen:** RISK_OFF y RISK_ON son negativos.
- **Activos:** 76 de 90 tienen ΔR puntual negativo; 15 tienen el IC95 entero por debajo de 0 y
  ninguno entero por encima.

Esto refuerza la explicación del resultado ya decidido, pero **no añade ninguna condición nueva**.

## 5. Qué significa la heterogeneidad ALTA

**Evidencia observada.** Los efectos varían entre regímenes (CAUTELA neutro, RISK_OFF y RISK_ON
positivos en B2 y S2), entre activos (dispersión amplia, sin ningún activo con el IC95 entero
negativo en B2 ni en S2), con la volatilidad (la magnitud crece con ATR/precio), algo entre regiones
y, en S2, con la base del stop.

**Limitación del instrumento.** D-63 ya registra que el instrumento de P2.6 trata como independientes
sesiones que se solapan hasta 40 barras, y que por eso puede confundir esa dependencia con
heterogeneidad. En sintético, marcó ALTA con un efecto constante. **No se intenta cuantificar ahora
qué parte de la ALTA es heterogeneidad real y qué parte es artefacto.**

**Conclusión.** La bandera ALTA queda explicada por una combinación observable de dispersión por
activo, régimen y volatilidad, y por una limitación conocida del instrumento debida al solapamiento.
D-63 pre-registró que esta bandera no veta P4. No se crean políticas por estrato.

**FOLLOW_UP abierto:** revisar un instrumento de heterogeneidad que respete la dependencia por
solapamiento antes de darle función de veto en una fase posterior (D-63, `docs/roadmap.md`).
