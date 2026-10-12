# T-019 paso 3 — P3 ejecutado una sola vez (2026-09-30)

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

Resultado **mecánico** del experimento pre-registrado. No incluye interpretación ni el paso 4:
la calibración documental la decide el propietario después de revisar este resultado.

## Identidad

| | |
|---|---|
| Pre-registro de P3 | `8b2dddb8fd66423d9550df496d1a2a85abd066b6` |
| **P3_EXECUTOR_SHA** | `87309da148772f834fd49c3f2357692e48ed9273` (árbol limpio, sin cambios posteriores) |
| `data_vintage_id` | `071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841` |
| `universe_vintage_id` | `237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19` |
| `config_hash` | `89406d28c7b4b6e6c4f032cd63b6868c927af3e926dfb52d430dfa6654d06387` (`config.yaml` en "1.0") |
| Score medido | `"2.0"`, contexto point-in-time (D-59) |
| Coste / semilla | 0,2 / 20260830 |

## Una sola ejecución confirmatoria

- **Comando único:** `.venv/bin/python -m advisor.main p3 --fase confirmatoria` (`consola/comando.txt`).
  Se lanzó desacoplado (`nohup caffeinate -i`) para que ni el reposo del Mac ni un límite de
  tiempo pudieran cortarlo después de la marca.
- **Horas:**
  - lanzamiento 2026-09-30T17:40:54Z (`consola/inicio_utc.txt`);
  - preflight interno de 17:40 a 17:58;
  - marca y análisis desde 17:58:03Z;
  - fin 18:01:28Z (`consola/fin_utc.txt`).
- **Salida:** exit code **0** (`consola/exit_code.txt`), stderr vacío. HEAD al iniciar:
  `87309da…` (`consola/head_al_iniciar.txt`).
- **Garantías de ejecución única:**
  - la marca `run/EJECUCION_CONFIRMATORIA_INICIADA` se escribió antes de calcular desenlaces;
  - el ejecutor se niega a arrancar si la marca existe y escribe solo en la ruta fija `run/`.
- **Comprobaciones posteriores:** se hicieron **leyendo los artefactos de esta ejecución**, sin
  recalcular P3.
- **El preflight interno reprodujo el oficial byte a byte:** `run/preflight-interno/p3-preflight.txt`
  y `preflight/p3-preflight.txt` tienen el mismo sha256 (`3a0f4540…`).
- **Hashes:** `SHA256SUMS-ejecucion.txt` recoge los de todos los artefactos de `run/` y
  `consola/`; `preflight/SHA256SUMS`, los del registro previo.
- **Después de abrir los desenlaces no se cambió ninguna regla, código, percentil, bloque,
  intervalo, población ni selección.**

## Ficheros

- `preflight/` — todo lo generado **antes** de abrir desenlaces:
  - `00-suite.txt`: ruff, mypy y pytest (774) sobre el SHA;
  - `p3-preflight.json`/`.txt`: 40 controles OK;
  - `registro-previo.md`: SHA, población, cortes y candidatos;
  - `revision-previa.md`: dos vueltas de revisión independiente;
  - `SHA256SUMS`.
- `consola/` — stdout y stderr literales, comando, horas y código de salida.
- `run/` — artefactos literales de la única ejecución:
  - `p3-resultado.json`: todo, legible por máquina;
  - `p3-resumen.md`;
  - `tablas/*.tsv`: quintiles, bloque × quintil, contrastes, regiones, activos, intra-activo,
    pares excluidos, ablaciones, candidatos y familia Bonferroni.

## Resultado mecánico — swing (confirmatorio)

**Población y bloques.**
- 94.094 señales, 90 activos, 5 regiones y 19 bloques; hash `4aa12d85…`.
- Horizonte válido: bloque más corto de 42 sesiones > 40.
- El primario usa 94.069 señales con `net_R` observable; las 25 restantes no lo tienen, igual que
  en A-02.

**Primario global:** 0,1549 R, IC95 [0,0569, 0,2558], 19 bloques. Coincide exactamente con el
instrumento de A-02.

**Cortes sin desenlaces.** p20/p40/p60/p80 = 28,0 / 39,6 / 49,6 / 57,6, con 817 valores distintos
y sin empates.

| quintil | n | primario (IC95) | capacidad | experimental_resolution | expectancy agrupada | PF |
|---|---|---|---|---|---|---|
| Q1 | 18.292 | 0,3430 [0,2374, 0,4445] | INSUFICIENTE (anchura 0,207) | LOW | 0,2841 | 1,433 |
| Q2 | 18.740 | 0,1584 [0,0651, 0,2547] | LIMITADA, concluyente | MEDIUM | 0,1446 | 1,246 |
| Q3 | 19.405 | 0,0666 [−0,0524, 0,1815] | INSUFICIENTE (0,234) | LOW | 0,0886 | 1,151 |
| Q4 | 17.205 | 0,0342 [−0,1082, 0,1698] | INSUFICIENTE (0,278) | LOW | 0,1093 | 1,189 |
| Q5 | 20.452 | 0,0535 [−0,0753, 0,1828] | INSUFICIENTE (0,258) | LOW | 0,1218 | 1,213 |

**Confirmatorio: Δ Q5−Q1 = −0,2895 R**, IC95 [−0,4098, −0,1658], anchura **0,2440**, 19 bloques
con Δ y ningún bloque excluido.

**`veredicto_ordenacion`: NO CONCLUYENTE**, porque la anchura del IC95 es 0,2440 > 0,20. Así lo
exige la tabla pre-registrada, que se aplica en su orden. Se publica el signo: el Δ es negativo en
todo el intervalo (Q5 por debajo de Q1). SUFICIENTE era inalcanzable con 19 bloques.

**Contrastes adyacentes (descriptivos):**
- Q2−Q1: −0,1846 [−0,2579, −0,1052];
- Q3−Q2: −0,0917 [−0,1605, −0,0308];
- Q4−Q3: −0,0324 [−0,1038, 0,0474];
- Q5−Q4: 0,0192 [−0,0461, 0,0965].

**Secundarias por quintil:** en `tablas/swing-quintiles.tsv`. Q1 frente a Q5:

| | Q1 | Q5 |
|---|---|---|
| TF/(TF+SF) | 0,427 | 0,468 |
| P(objetivo antes de stop) | [0,409, 0,409] | [0,445, 0,445] |
| Mediana MAE de ganadoras | 0,323 | 0,307 |
| Mediana MFE sin objetivo | [1,402, 1,444] | [1,210, 1,213] |
| EXIT_FINAL | 0,65 % | 1,67 % |
| Ambigüedad | 0,06 % | 0,02 % |

**Calibración** (Bonferroni m = 20, confianza 0,9975, 20.000 remuestreos).
- Candidatos p50/p60/p70/p80/p90 = 43,6 / 49,6 / 53,6 / 57,6 / 63,6, sin colapsos.
- Evaluación de cada candidato:

| c | n | capacidad [c,∞) | Bonf. primario | Bonf. contraste | PF | cumple |
|---|---|---|---|---|---|---|
| 43,6 | 49.056 | INSUFICIENTE (anchura 0,250) | [−0,1415, 0,2280] | [−0,3439, −0,0503] | 1,184 | no (2, 3, 4) |
| 49,6 | 37.657 | INSUFICIENTE (0,271) | [−0,1608, 0,2341] | [−0,3505, −0,0184] | 1,202 | no (2, 3, 4) |
| 53,6 | 28.670 | INSUFICIENTE (0,265) | [−0,1589, 0,2343] | [−0,3268, −0,0124] | 1,196 | no (2, 3, 4) |
| 57,6 | 20.452 | INSUFICIENTE (0,258) | [−0,1441, 0,2443] | [−0,2562, 0,0051] | 1,213 | no (2, 3, 4) |
| 63,6 | 9.595 | INSUFICIENTE (0,268) | [−0,1615, 0,2509] | [−0,3165, 0,0314] | 1,230 | no (2, 3, 4) |

- **`min_score_operar`: ninguno.** No hay meseta y **swing queda `calibrated: false`**: no se
  publica ningún número como umbral.
- **VIGILAR:** no se calcula, porque no existe OPERAR.
- **Familia Bonferroni:** 20 miembros (`tablas/swing-familia-bonferroni.tsv`). Los 10 de OPERAR
  están evaluados; los 10 pares VIGILAR figuran como «no evaluado: no existe min_score_operar».
  m = 20.

**Regiones** (primario | Δ Q5−Q1):

| Región | Primario (IC95) | Δ Q5−Q1 (IC95) | Bloques del Δ |
|---|---|---|---|
| ASIA | 0,1232 [0,0043, 0,2411] | −0,2761 [−0,4966, −0,0616] | 19 |
| EMERGING_MARKETS | 0,2015 [−0,0639, 0,4662] | −1,4664 [−2,0966, −0,7359] | 10 |
| EUROPA | 0,1188 [0,0096, 0,2386] | −0,4174 [−0,5901, −0,2552] | 19 |
| GLOBAL | 0,2335 [0,0154, 0,4595] | −1,0508 [−1,7646, −0,4148] | 14 |
| USA | 0,1897 [0,0618, 0,3129] | −0,3023 [−0,4942, −0,1102] | 19 |

**Activos (90):**
- primario > 0 en 75;
- Δ Q5−Q1 calculable en 89, negativo en los 89; su IC95 queda entero por debajo de 0 en 83 y en
  ninguno por encima (`tablas/swing-activos.tsv`).

**Intra-activo** (media(Q4∪Q5) − media(Q1∪Q2) por activo y bloque, con quintiles globales):
- **−0,7512 R**, IC95 [−0,8150, −0,6720], 19 bloques, estado CALCULADO;
- 1.512 pares calculables y 178 excluidos (`tablas/swing-intra-activo-pares-excluidos.tsv`),
  ningún bloque sin activos;
- media negativa en los 90 activos.

**Ablaciones** (descriptivas; no seleccionan ni cambian Score v2):

| Sin | Primario por quintil Q1…Q5 | Δ Q5−Q1 (IC95) | Anchura | Veredicto |
|---|---|---|---|---|
| catalizador | 0,344 / 0,166 / 0,045 / 0,029 / −0,039 | −0,3828 [−0,6091, −0,1910] | 0,418 | NO CONCLUYENTE |
| técnico | 0,379 / 0,138 / 0,102 / 0,096 / 0,083 | −0,2960 [−0,4394, −0,1591] | 0,280 | NO CONCLUYENTE |
| contexto | 0,290 / 0,200 / 0,128 / 0,062 / 0,046 | −0,2432 [−0,3729, −0,1247] | 0,248 | NO CONCLUYENTE |

Las tres tienen cortes propios sin empates. La migración de quintiles está en `p3-resultado.json`.

## Medio (solo trazabilidad) — NO CONCLUYENTE — inválido (bloque parcial 102 ≤ 250)

- **Población:** 89.333 señales y 5 bloques; hash `4d6eaab9…`.
- **Cortes:** 29,6 / 40,0 / 49,6 / 57,6.
- **Primario global:** 0,1051 R [−0,0503, 0,2060].
- **Δ Q5−Q1:** −0,2120 R [−0,3046, −0,1359], anchura 0,169, 5 bloques.
- **Veredicto:** forzado por el pre-registro, independiente de las cifras.
- **Capacidad:** INSUFICIENTE en todos los quintiles (bloque parcial y 5 < 12 bloques).
- **Intra-activo:** −0,3692 R [−0,4842, −0,3020], 5 bloques, NO CONCLUYENTE.
- **Ablaciones:** Δ −0,3746 sin catalizador, −0,2389 sin técnico y −0,1101 sin contexto, todas
  con el veredicto forzado.
- **Sin calibración ni familia Bonferroni** (D-45).

## Contadores (derivados de las salidas)

`comparaciones_swing` = **329**, `comparaciones_medio_trazabilidad` = **309** y
`comparaciones_totales` = **638**. Coinciden con el pre-registro.

## Lo que este paso no hace

- No cambia `config.yaml`, que sigue en "1.0", 70/60 y `calibrated: false`.
- No activa Score v2 ni escribe umbrales en producción.
- No despliega: la Pi sigue en `v0.4.1` = `8b2dddb`.
- No implementa D-60 ni crea un Score v3.
- No modifica la fórmula tras ver los resultados.
- No hace el paso 4.
