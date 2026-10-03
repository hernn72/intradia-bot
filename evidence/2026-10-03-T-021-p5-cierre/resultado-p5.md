# Resultado congelado de P5 (T-021 / A-05)

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

Transcripción literal de `evidence/2026-10-02-T-021-p5/run/` (commit `86ddd5baf8ceabe6e9d3747d645c7c99d719343c`). **No se recalcula nada**: cada valor es la cadena que escribió la ejecución única. P5 no se repite.

## Identidad

| | |
|---|---|
| `P5_PREREG_SHA` | `a7c3d238d651b4ea8f48834848c03c0a5a462dfa` |
| `P5_CODE_SHA` | `6c7f9135774f157e82634b6abf82a847d9b99bd9` |
| `P5_PREFLIGHT_HEAD` | `7446602114b26f56cae549d2ec299d7bbc07b459` |
| `P5_RUN_HEAD_SHA` | `282b1ce991bb4567ff2ad41a28e00c9518662115` |
| `P5_RUN_EVIDENCE_COMMIT` | `86ddd5baf8ceabe6e9d3747d645c7c99d719343c` |
| Marca `inicio_utc` | `2026-10-03T09:44:05.684666+00:00` |
| sha256 de la marca = `token_sha256` | `f50d5ec9cc7e2c266515778592c4398001ee8588dbcdcc2b4c783bcca87c1f8c` |

Finalización normal: `p5-resultado.json` y `p5-resumen.md` íntegros, sin `p5-parada.json`. La consola archiva literalmente `código de salida: 0` (línea añadida por el envoltorio de lanzamiento con el código que devolvió el proceso).

## Recuento

- Comparaciones previstas: **71** (B2 43 = 8·5 + 3; S2 28 = 5·5 + 3).
- Comparaciones derivadas de las salidas (`recuento.tsv`): **71** (esperadas 71).
- Confirmatorias nuevas: **0**.

## Criterio (`criterio.tsv`)

| Centro | centro_p4 | F1 | F2 | F3 | F4 | F5 | F6 | Etiqueta | Sobrevive |
|---|---|---|---|---|---|---|---|---|---|
| B2 | True | False | False | False | False | False | False | **ROBUSTA** | True |
| S2 | True | False | False | False | False | False | False | **ROBUSTA** | True |

## Clases de los vecinos (`clases.tsv`)

- **B2: 8/8 vecinos ACEPTABLE**; NO_ESTIMABLE 0, DÉBIL 0, CONTRARIA 0.
- **S2: 5/5 vecinos ACEPTABLE**; NO_ESTIMABLE 0, DÉBIL 0, CONTRARIA 0.

## Superficie completa (`superficie.tsv`)

Las tres celdas de B2 con `target2 = 5,25` llevan `target3 = 5,625` y `m3_auxiliar = true`: son **exclusivamente diagnósticas**, no son políticas ni candidatas. Ningún vecino es política (D-66).

| Celda | s | m2 | m3 | m3_aux | Clase | ΔR | IC95 | Pares | Cap. | Bloque 120 [IC95] | Cota cons. | Cota fav. | Nivel [IC95] | PF | Mitades 2–11 / 12–21 | Retención | Heterog. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B2_s1p75_m24p500 | 1.750000 | 4.500000 | 5.000000 | False | ACEPTABLE | 0.055407 | [0.006247, 0.106308] | 101225 | True | 0.056837 [0.010570, 0.096620] | 0.054715 | 0.055497 | 0.159177 [0.011619, 0.310812] | 1.228213 | 0.054400 / 0.056414 | 0.773238 | ALTA |
| B2_s1p75_m24p875 | 1.750000 | 4.875000 | 5.000000 | False | ACEPTABLE | 0.071647 | [0.013096, 0.131251] | 101225 | True | 0.073098 [0.018925, 0.120248] | 0.070950 | 0.071629 | 0.175373 [0.020487, 0.337208] | 1.248485 | 0.071716 / 0.071579 | 0.999883 | ALTA |
| B2_s1p75_m25p250 | 1.750000 | 5.250000 | 5.625000 | True | ACEPTABLE | 0.085237 | [0.018049, 0.153724] | 101226 | True | 0.086872 [0.022535, 0.142878] | 0.084560 | 0.085202 | 0.188968 [0.024312, 0.357389] | 1.265439 | 0.085956 / 0.084518 | 1.189539 | ALTA |
| B2_s2p00_m24p500 | 2.000000 | 4.500000 | 5.000000 | False | ACEPTABLE | 0.056319 | [0.014073, 0.098484] | 101226 | True | 0.057304 [0.015854, 0.091349] | 0.055657 | 0.056394 | 0.160103 [0.016703, 0.305851] | 1.243379 | 0.052631 / 0.060007 | 0.785968 | ALTA |
| B2_s2p00_m25p250 | 2.000000 | 5.250000 | 5.625000 | True | ACEPTABLE | 0.084357 | [0.025383, 0.144489] | 101226 | True | 0.085505 [0.026587, 0.134122] | 0.083683 | 0.084326 | 0.188091 [0.028052, 0.349195] | 1.280080 | 0.083076 / 0.085638 | 1.177260 | ALTA |
| B2_s2p25_m24p500 | 2.250000 | 4.500000 | 5.000000 | False | ACEPTABLE | 0.058378 | [0.019221, 0.095923] | 101226 | True | 0.058910 [0.018609, 0.092498] | 0.057864 | 0.058535 | 0.162280 [0.019392, 0.303252] | 1.260512 | 0.050288 / 0.066467 | 0.814696 | ALTA |
| B2_s2p25_m24p875 | 2.250000 | 4.875000 | 5.000000 | False | ACEPTABLE | 0.072781 | [0.025567, 0.119609] | 101226 | True | 0.073290 [0.025801, 0.113826] | 0.072262 | 0.072905 | 0.176670 [0.028822, 0.326404] | 1.280123 | 0.066206 / 0.079356 | 1.015706 | ALTA |
| B2_s2p25_m25p250 | 2.250000 | 5.250000 | 5.625000 | True | ACEPTABLE | 0.085070 | [0.030102, 0.140433] | 101226 | True | 0.085731 [0.029401, 0.133252] | 0.084552 | 0.085194 | 0.188960 [0.034255, 0.346333] | 1.297078 | 0.079707 / 0.090433 | 1.187206 | ALTA |
| S2_s2p25_m23p375 | 2.250000 | 3.375000 | 5.000000 | False | ACEPTABLE | 0.018522 | [0.006736, 0.029434] | 101224 | True | 0.018371 [0.004847, 0.030761] | 0.018022 | 0.019057 | 0.122605 [0.002189, 0.235141] | 1.209021 | 0.011086 / 0.025958 | 0.532453 | ALTA |
| S2_s2p25_m23p750 | 2.250000 | 3.750000 | 5.000000 | False | ACEPTABLE | 0.032868 | [0.011319, 0.053189] | 101225 | True | 0.032941 [0.010276, 0.052785] | 0.032347 | 0.033174 | 0.136829 [0.008273, 0.259927] | 1.227317 | 0.024017 / 0.041720 | 0.944874 | ALTA |
| S2_s2p25_m24p125 | 2.250000 | 4.125000 | 5.000000 | False | ACEPTABLE | 0.045143 | [0.014159, 0.074347] | 101226 | True | 0.045499 [0.011963, 0.073318] | 0.044626 | 0.045352 | 0.149060 [0.011882, 0.279304] | 1.242825 | 0.036242 / 0.054045 | 1.297743 | ALTA |
| S2_s2p50_m24p125 | 2.500000 | 4.125000 | 5.000000 | False | ACEPTABLE | 0.046280 | [0.017593, 0.072948] | 101226 | True | 0.046341 [0.015782, 0.071967] | 0.045803 | 0.046527 | 0.150237 [0.017443, 0.279096] | 1.257476 | 0.035850 / 0.056710 | 1.330413 | ALTA |
| S2_s2p75_m24p125 | 2.750000 | 4.125000 | 5.000000 | False | ACEPTABLE | 0.047204 | [0.020428, 0.073025] | 101226 | True | 0.047034 [0.018088, 0.071348] | 0.046745 | 0.047467 | 0.151179 [0.022852, 0.275643] | 1.271782 | 0.036227 / 0.058181 | 1.356991 | ALTA |

Todas las columnas, tal cual (incluidos los IC de las dos cotas, fracción de pares y tasa de descarte):

```tsv
# condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)
celda	centro	s	m2	m3	m3_auxiliar	rol	clase	delta_r	ic95_inferior	ic95_superior	pares	capacidad_ok	capacidad_motivos	bloque_120_media	bloque_120_ic95_inferior	bloque_120_ic95_superior	cota_conservadora_media	cota_conservadora_ic95_inferior	cota_conservadora_ic95_superior	cota_favorable_media	cota_favorable_ic95_inferior	cota_favorable_ic95_superior	nivel_media	nivel_ic95_inferior	nivel_ic95_superior	pf	mitad_2_11_media	mitad_12_21_media	retencion_delta_r_centro	heterogeneidad	fraccion_pares	tasa_descarte
B2_s1p75_m24p500	B2	1.750000	4.500000	5.000000	False	DIAGNOSTIC_NEIGHBOR	ACEPTABLE	0.055407	0.006247	0.106308	101225	True		0.056837	0.010570	0.096620	0.054715	0.005948	0.104926	0.055497	0.006291	0.106288	0.159177	0.011619	0.310812	1.228213	0.054400	0.056414	0.773238	ALTA	0.999743	0.000257
B2_s1p75_m24p875	B2	1.750000	4.875000	5.000000	False	DIAGNOSTIC_NEIGHBOR	ACEPTABLE	0.071647	0.013096	0.131251	101225	True		0.073098	0.018925	0.120248	0.070950	0.012464	0.130582	0.071629	0.013099	0.131243	0.175373	0.020487	0.337208	1.248485	0.071716	0.071579	0.999883	ALTA	0.999743	0.000257
B2_s1p75_m25p250	B2	1.750000	5.250000	5.625000	True	DIAGNOSTIC_NEIGHBOR	ACEPTABLE	0.085237	0.018049	0.153724	101226	True		0.086872	0.022535	0.142878	0.084560	0.017562	0.153004	0.085202	0.018073	0.153645	0.188968	0.024312	0.357389	1.265439	0.085956	0.084518	1.189539	ALTA	0.999753	0.000247
B2_s2p00_m24p500	B2	2.000000	4.500000	5.000000	False	DIAGNOSTIC_NEIGHBOR	ACEPTABLE	0.056319	0.014073	0.098484	101226	True		0.057304	0.015854	0.091349	0.055657	0.013402	0.097479	0.056394	0.014188	0.098514	0.160103	0.016703	0.305851	1.243379	0.052631	0.060007	0.785968	ALTA	0.999753	0.000247
B2_s2p00_m25p250	B2	2.000000	5.250000	5.625000	True	DIAGNOSTIC_NEIGHBOR	ACEPTABLE	0.084357	0.025383	0.144489	101226	True		0.085505	0.026587	0.134122	0.083683	0.024788	0.143715	0.084326	0.025373	0.144418	0.188091	0.028052	0.349195	1.280080	0.083076	0.085638	1.177260	ALTA	0.999753	0.000247
B2_s2p25_m24p500	B2	2.250000	4.500000	5.000000	False	DIAGNOSTIC_NEIGHBOR	ACEPTABLE	0.058378	0.019221	0.095923	101226	True		0.058910	0.018609	0.092498	0.057864	0.018708	0.095496	0.058535	0.019253	0.096092	0.162280	0.019392	0.303252	1.260512	0.050288	0.066467	0.814696	ALTA	0.999753	0.000247
B2_s2p25_m24p875	B2	2.250000	4.875000	5.000000	False	DIAGNOSTIC_NEIGHBOR	ACEPTABLE	0.072781	0.025567	0.119609	101226	True		0.073290	0.025801	0.113826	0.072262	0.025134	0.118923	0.072905	0.025630	0.119722	0.176670	0.028822	0.326404	1.280123	0.066206	0.079356	1.015706	ALTA	0.999753	0.000247
B2_s2p25_m25p250	B2	2.250000	5.250000	5.625000	True	DIAGNOSTIC_NEIGHBOR	ACEPTABLE	0.085070	0.030102	0.140433	101226	True		0.085731	0.029401	0.133252	0.084552	0.029684	0.139936	0.085194	0.030152	0.140793	0.188960	0.034255	0.346333	1.297078	0.079707	0.090433	1.187206	ALTA	0.999753	0.000247
S2_s2p25_m23p375	S2	2.250000	3.375000	5.000000	False	DIAGNOSTIC_NEIGHBOR	ACEPTABLE	0.018522	0.006736	0.029434	101224	True		0.018371	0.004847	0.030761	0.018022	0.006134	0.029039	0.019057	0.007463	0.029996	0.122605	0.002189	0.235141	1.209021	0.011086	0.025958	0.532453	ALTA	0.999733	0.000267
S2_s2p25_m23p750	S2	2.250000	3.750000	5.000000	False	DIAGNOSTIC_NEIGHBOR	ACEPTABLE	0.032868	0.011319	0.053189	101225	True		0.032941	0.010276	0.052785	0.032347	0.010714	0.052617	0.033174	0.011608	0.053551	0.136829	0.008273	0.259927	1.227317	0.024017	0.041720	0.944874	ALTA	0.999743	0.000257
S2_s2p25_m24p125	S2	2.250000	4.125000	5.000000	False	DIAGNOSTIC_NEIGHBOR	ACEPTABLE	0.045143	0.014159	0.074347	101226	True		0.045499	0.011963	0.073318	0.044626	0.013452	0.073763	0.045352	0.014336	0.074507	0.149060	0.011882	0.279304	1.242825	0.036242	0.054045	1.297743	ALTA	0.999753	0.000247
S2_s2p50_m24p125	S2	2.500000	4.125000	5.000000	False	DIAGNOSTIC_NEIGHBOR	ACEPTABLE	0.046280	0.017593	0.072948	101226	True		0.046341	0.015782	0.071967	0.045803	0.016922	0.072484	0.046527	0.017875	0.073155	0.150237	0.017443	0.279096	1.257476	0.035850	0.056710	1.330413	ALTA	0.999753	0.000247
S2_s2p75_m24p125	S2	2.750000	4.125000	5.000000	False	DIAGNOSTIC_NEIGHBOR	ACEPTABLE	0.047204	0.020428	0.073025	101226	True		0.047034	0.018088	0.071348	0.046745	0.019980	0.072572	0.047467	0.020778	0.073161	0.151179	0.022852	0.275643	1.271782	0.036227	0.058181	1.356991	ALTA	0.999753	0.000247
```

## Ausencias estructurales (S2)

| Celda | s | m2 | Motivo |
|---|---|---|---|
| S2_s2p50_m23p375 | 2,50 | 3,375 | `AUSENCIA_ESTRUCTURAL`: RR < 1,5 |
| S2_s2p75_m23p375 | 2,75 | 3,375 | `AUSENCIA_ESTRUCTURAL`: RR < 1,5 |
| S2_s2p75_m23p750 | 2,75 | 3,750 | `AUSENCIA_ESTRUCTURAL`: RR < 1,5 |

Fijadas en D-66 antes de medir. **No se estimaron**, no entran en ningún denominador y **no son celdas descartadas por rendimiento** ni tienen relación con FRÁGIL.

## LOCRO (`locro.tsv`)

| Centro | Sin región | Denominador | Pares | Mínimo | Estimable | ΔR | IC95 |
|---|---|---|---|---|---|---|---|
| B2 | USA | 56353 | 56329 | 50718 | True | 0.067950 | [0.015507, 0.122806] |
| B2 | EUROPA | 66629 | 66626 | 59967 | True | 0.077285 | [0.012695, 0.139081] |
| B2 | ASIA | 83298 | 83275 | 74969 | True | 0.070625 | [0.021085, 0.119686] |
| S2 | USA | 56353 | 56328 | 50718 | True | 0.038843 | [0.017103, 0.059156] |
| S2 | EUROPA | 66629 | 66626 | 59967 | True | 0.032699 | [0.004929, 0.058428] |
| S2 | ASIA | 83298 | 83274 | 74969 | True | 0.033781 | [0.014273, 0.052136] |

Conclusión mecánica: los seis son estimables y los seis tienen IC95 inferior > 0. Ni B2 ni S2 quedan DEPENDIENTE_DE_MERCADO; ningún LOCRO deja una candidata NO_CONCLUYENTE. No se añaden regiones ni otros leave-one-out.

## Concentración por activo (`concentracion.tsv`, descriptiva)

No veta ni aprueba; no se crea ningún umbral.

| Centro | Activos + | Activos − | p10 | p25 | p50 | p75 | p90 | Mayor | Top 5 | Top 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| B2 | 75 | 15 | -0.046660 | 0.015451 | 0.066295 | 0.141210 | 0.187399 | 0.052492 (5.2492 %) | 0.187986 (18.7986 %) | 0.329982 (32.9982 %) |
| S2 | 74 | 16 | -0.019240 | 0.008270 | 0.034630 | 0.061187 | 0.088688 | 0.036788 (3.6788 %) | 0.179082 (17.9082 %) | 0.333776 (33.3776 %) |

## Supervivientes

**`[B2, S2]`**, las dos con la etiqueta ROBUSTA. P5 solo prueba robustez: no ordena una sobre la otra ni dice que una sea mejor.

## Descartes

- Candidatas heredadas de P4 descartadas por FRÁGIL: **ninguna**.
- Candidatas heredadas de P4 descartadas por DEPENDIENTE_DE_MERCADO: **ninguna**.
- Candidatas NO_CONCLUYENTE: **ninguna**.
- Los 13 vecinos son diagnósticos, no candidatas: no se descartan ni se adoptan.
- Aparte, 3 `AUSENCIA_ESTRUCTURAL` en S2 por RR < 1,5 (arriba).

