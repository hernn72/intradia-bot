# Resultado P3

- P3_EXECUTOR_SHA: `87309da148772f834fd49c3f2357692e48ed9273`
- SHA pre-registro: `8b2dddb8fd66423d9550df496d1a2a85abd066b6`
- data_vintage_id: `071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841`
- universe_vintage_id: `237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19`
- config_hash: `89406d28c7b4b6e6c4f032cd63b6868c927af3e926dfb52d430dfa6654d06387`
- ejecución única: inicio `2026-09-30T17:58:03.136526+00:00`, fin `2026-09-30T18:01:28.058824+00:00`, exit code `0`, marca `EJECUCION_CONFIRMATORIA_INICIADA`
- etiqueta de universo: condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)
- contadores: 329/309/638; comprobación contra pre-registro: True

## Swing

Primario global: 0.1549 [0.0569, 0.2558]; bloques 19; n 94069.
Cortes: 28.0 / 39.6 / 49.6 / 57.6; bloques ocupados 19; n población 94094.

### Quintiles

| quintil | n con net_R observable | primario IC95 | capacidad | experimental_resolution | expectancy agrupada | PF |
|---|---|---|---|---|---|---|
| Q1 | 18281 | 0.3430 [0.2374, 0.4445] | INSUFICIENTE | LOW | 0.2841 | 1.4331 |
| Q2 | 18738 | 0.1584 [0.0651, 0.2547] | LIMITADA | MEDIUM | 0.1446 | 1.2457 |
| Q3 | 19404 | 0.0666 [-0.0524, 0.1815] | INSUFICIENTE | LOW | 0.0886 | 1.1505 |
| Q4 | 17199 | 0.0342 [-0.1082, 0.1698] | INSUFICIENTE | LOW | 0.1093 | 1.1894 |
| Q5 | 20447 | 0.0535 [-0.0753, 0.1828] | INSUFICIENTE | LOW | 0.1218 | 1.2128 |

### Delta Q5-Q1

Δ Q5−Q1: -0.2895 [-0.4098, -0.1658]; anchura 0.2440; bloques 19.
Veredicto: NO CONCLUYENTE porque anchura IC95 0.2440 > 0.2; motivo mecánico 0.2440 > 0.2000.

### Contrastes Adyacentes

| contraste | media | IC95 | anchura | bloques |
|---|---|---|---|---|
| Q2−Q1 | -0.1846 | [-0.2579, -0.1052] | 0.1527 | 19 |
| Q3−Q2 | -0.0917 | [-0.1605, -0.0308] | 0.1297 | 19 |
| Q4−Q3 | -0.0324 | [-0.1038, 0.0474] | 0.1512 | 19 |
| Q5−Q4 | 0.0192 | [-0.0461, 0.0965] | 0.1427 | 19 |

## descriptivo, no modifica el veredicto

### Regiones

| región | n | primario IC95 | Δ Q5-Q1 IC95 | bloques Δ |
|---|---|---|---|---|
| ASIA | 16717 | 0.1232 [0.0043, 0.2411] | -0.2761 [-0.4966, -0.0616] | 19 |
| EMERGING_MARKETS | 1068 | 0.2015 [-0.0639, 0.4662] | -1.4664 [-2.0966, -0.7359] | 10 |
| EUROPA | 32096 | 0.1188 [0.0096, 0.2386] | -0.4174 [-0.5901, -0.2552] | 19 |
| GLOBAL | 2459 | 0.2335 [0.0154, 0.4595] | -1.0508 [-1.7646, -0.4148] | 14 |
| USA | 41729 | 0.1897 [0.0618, 0.3129] | -0.3023 [-0.4942, -0.1102] | 19 |

### Activos

Δ calculable en 89 activos; negativos 89; IC entero bajo 0: 83; IC entero sobre 0: 0.

### Intra-Activo

Estimación global intra-activo: -0.7512 [-0.8150, -0.6720]; bloques 19; pares calculables 1512; pares excluidos 178 (TSV: 178); IC entero bajo 0: 81; IC entero sobre 0: 0.

## Calibración Swing

min_score_operar=null; min_score_vigilar=null; calibrated=false.
Familia Bonferroni: m=20; 10 evaluados + 10 VIGILAR no evaluados.

| candidato | percentil | n | capacidad | IC primario Bonf. | IC contraste Bonf. | PF | condiciones que fallan | cumple OPERAR |
|---|---|---|---|---|---|---|---|---|
| 43.6 | 50 | 49056 | INSUFICIENTE | [-0.1415, 0.2280] | [-0.3439, -0.0503] | 1.1842 | c2, c3, c4 | False |
| 49.6 | 60 | 37657 | INSUFICIENTE | [-0.1608, 0.2341] | [-0.3505, -0.0184] | 1.2021 | c2, c3, c4 | False |
| 53.6 | 70 | 28670 | INSUFICIENTE | [-0.1589, 0.2343] | [-0.3268, -0.0124] | 1.1963 | c2, c3, c4 | False |
| 57.6 | 80 | 20452 | INSUFICIENTE | [-0.1441, 0.2443] | [-0.2562, 0.0051] | 1.2128 | c2, c3, c4 | False |
| 63.6 | 90 | 9595 | INSUFICIENTE | [-0.1615, 0.2509] | [-0.3165, 0.0314] | 1.2299 | c2, c3, c4 | False |

## Ablaciones Swing

| ablación | primario por quintil | Δ | IC95 | anchura | veredicto |
|---|---|---|---|---|---|
| catalizador | Q1=0.3443; Q2=0.1658; Q3=0.0447; Q4=0.0293; Q5=-0.0385 | -0.3828 | [-0.6091, -0.1910] | 0.4181 | NO CONCLUYENTE |
| tecnico | Q1=0.3792; Q2=0.1378; Q3=0.1015; Q4=0.0959; Q5=0.0832 | -0.2960 | [-0.4394, -0.1591] | 0.2803 | NO CONCLUYENTE |
| contexto | Q1=0.2896; Q2=0.2001; Q3=0.1277; Q4=0.0616; Q5=0.0464 | -0.2432 | [-0.3729, -0.1247] | 0.2482 | NO CONCLUYENTE |


## Medio

Cifras de trazabilidad, no calibración: primario global 0.1051 [-0.0503, 0.2060]; Δ Q5−Q1 -0.2120 [-0.3046, -0.1359]; anchura 0.1686; bloques 5.
Veredicto forzado: NO CONCLUYENTE — inválido (bloque parcial 102 ≤ 250); motivo: medio solo por trazabilidad (D-45, D-42).
Activos medio con Δ calculable 90; negativos 81; IC entero bajo 0: 43; IC entero sobre 0: 1.

| quintil | n con net_R observable | primario IC95 | capacidad | experimental_resolution | PF |
|---|---|---|---|---|---|
| Q1 | 17059 | 0.2589 [0.0119, 0.4260] | INSUFICIENTE | INSUFFICIENT | 1.3977 |
| Q2 | 18386 | 0.0995 [-0.0221, 0.2166] | INSUFICIENTE | INSUFFICIENT | 1.2729 |
| Q3 | 16639 | 0.0571 [-0.0841, 0.1641] | INSUFICIENTE | INSUFFICIENT | 1.1974 |
| Q4 | 16934 | 0.0705 [-0.0913, 0.1861] | INSUFICIENTE | INSUFFICIENT | 1.2243 |
| Q5 | 20290 | 0.0469 [-0.1230, 0.1567] | INSUFICIENTE | INSUFFICIENT | 1.2281 |

| contraste medio | media | IC95 | anchura | bloques |
|---|---|---|---|---|
| Q5−Q1 | -0.2120 | [-0.3046, -0.1359] | 0.1686 | 5 |
| Q2−Q1 | -0.1594 | [-0.2609, -0.0460] | 0.2149 | 5 |
| Q3−Q2 | -0.0424 | [-0.0999, 0.0201] | 0.1200 | 5 |
| Q4−Q3 | 0.0134 | [-0.0244, 0.0569] | 0.0813 | 5 |
| Q5−Q4 | -0.0235 | [-0.0684, 0.0284] | 0.0968 | 5 |

## Calibración Tres Horizontes

- swing: calibrated=false; `min_score_operar`=null; `min_score_vigilar`=null.
- medio: calibrated=false (D-45; trazabilidad inválida por bloque parcial).
- intradía: calibrated=false (sin laboratorio y sin umbrales, D-45).

## Identidad Y Hashes

Score model version: `2.0`; coste: 0.2; seed: 20260830.
Hashes de artefactos originales verificados contra `SHA256SUMS-ejecucion.txt`:

```text
consola/comando.txt: OK
consola/exit_code.txt: OK
consola/fin_utc.txt: OK
consola/head_al_iniciar.txt: OK
consola/inicio_utc.txt: OK
consola/stderr.txt: OK
consola/stdout.txt: OK
run/EJECUCION_CONFIRMATORIA_INICIADA: OK
run/p3-resultado.json: OK
run/p3-resumen.md: OK
run/preflight-interno/p3-preflight.json: OK
run/preflight-interno/p3-preflight.txt: OK
run/tablas/medio-ablaciones.tsv: OK
run/tablas/medio-activos.tsv: OK
run/tablas/medio-bloque-x-quintil.tsv: OK
run/tablas/medio-contrastes.tsv: OK
run/tablas/medio-intra-activo-pares-excluidos.tsv: OK
run/tablas/medio-intra-activo.tsv: OK
run/tablas/medio-quintiles.tsv: OK
run/tablas/medio-regiones.tsv: OK
run/tablas/swing-ablaciones.tsv: OK
run/tablas/swing-activos.tsv: OK
run/tablas/swing-bloque-x-quintil.tsv: OK
run/tablas/swing-candidatos.tsv: OK
run/tablas/swing-contrastes.tsv: OK
run/tablas/swing-familia-bonferroni.tsv: OK
run/tablas/swing-intra-activo-pares-excluidos.tsv: OK
run/tablas/swing-intra-activo.tsv: OK
run/tablas/swing-quintiles.tsv: OK
run/tablas/swing-regiones.tsv: OK
```
