# Revisión independiente final del look-ahead — T-019 / A-03 (GATE P3, requisito 5)

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

Es la **revisión 2** que exige la ficha T-019 («Revisión independiente de look-ahead, en dos
momentos»), hecha al final de P3. La revisión 1, anterior a P3, está en
`evidence/2026-09-30-T-019-paso2a-code/revision-look-ahead-previa.md`.

## Revisor y mandato

- **Revisor:** el agente `revisor` (Claude), lanzado el 2026-10-01. No escribió nada de lo que se
  revisa: el código lo programó Codex (OpenAI), y la documentación y la supervisión las hizo otra
  instancia de Claude.
- **Mandato:** de adversario. Debía intentar demostrar que GATE P3 **no** puede cruzarse, buscando:
  - look-ahead;
  - rupturas de paridad;
  - poblaciones o cortes mal reconstruidos;
  - un veredicto mal aplicado;
  - umbrales fabricados;
  - artefactos alterados.
- **Cómo trabajó:**
  - Solo leyó el repositorio. Sus scripts y salidas están en `revisor/`.
  - **No ejecutó `advisor.main p3`** en ninguna fase.
  - No calculó ningún desenlace por señal. Reconstruyó las poblaciones con
    `build_population(..., with_outcomes=False)`, y además dejó los evaluadores de desenlace
    parcheados para que lanzaran un error si alguien los llamaba.
  - Solo leyó los agregados que #33 ya había publicado.
- **Estado del repositorio:** `git status` salió idéntico al empezar y al terminar.

## Base revisada

| | |
|---|---|
| Rama | `docs/t019-cierre` = `main` = `4ca9a370a02d297c949555a409eb960adfb8d8e8` |
| Pre-registro de P3 | `8b2dddb8fd66423d9550df496d1a2a85abd066b6` |
| `P3_EXECUTOR_SHA` | `87309da148772f834fd49c3f2357692e48ed9273` |
| Evidencia de P3 | `9d4ffb1` |
| Paso 4 | `4ca9a37` |
| Cosecha | `071ddb2b…253841`, que solo vive en el portátil |

`git diff 87309da 4ca9a37 -- advisor config.yaml` está **vacío**: el código que se auditó al ejecutar
es, byte a byte, el que corrió P3.

## Veredicto

**Ningún BLOCKER ni ningún IMPORTANTE. Hay 1 MENOR y 5 OBSERVACIONES.** El requisito 5 de
GATE P3 queda **satisfecho**. Ningún hallazgo altera la ejecución congelada.

---

## Qué se verificó ejecutando

Todos los comandos se lanzaron desde la raíz del repositorio con `.venv/bin/python`.

### 1. Suite

- `ruff check .` → `All checks passed!`
- `mypy advisor` → `Success: no issues found in 71 source files`
- `pytest -q` → **774 passed**, sin fallos ni saltos, en 219,6 s. Con la cosecha presente, el test
  del preflight real **se ejecutó**.
- Pruebas focalizadas (`test_point_in_time_context.py`, `test_p3.py` y
  `test_score_v2_real_vintage.py`): **49 passed**.

### 2. Población reconstruida sin desenlaces (`revisor/a_poblacion_y_pit.py`)

Guardas puestas durante la reconstrucción:
- `event_study._align` lanza un error si se usa dentro del camino PIT;
- `evaluate_managed_event` y `evaluate_potential_event` lanzan un error si alguien los invoca;
- se comprueba que ningún `P3Record` lleva `net_r`.

Resultado de las guardas: `_align` dentro del camino PIT se llamó **0 veces** y los evaluadores de
desenlace **0 veces**.

| | Swing | Medio |
|---|---|---|
| Población de A-02 | 106.363 | 94.273 |
| Cripto | 5.112 | 4.722 |
| Asia no calculable | 396 | 218 |
| SMA200 sin historia | 6.937 | 0 |
| Asia ∩ SMA200 | 176 | 0 |
| Cripto ∩ otros motivos | 0 | 0 |
| Exclusiones (unión) | **12.269** | **4.940** |
| Población final | **94.094** | **89.333** |
| sha256 | `4aa12d85eb54d7a01c10a4a3e4cf04e8077c842829235a93b75f7bd19c62011a` | `4d6eaab9b84ff23bade1df86a82e95f46da546917a226dc8438a8e88493020f8` |
| Activos | 90 | 90 |
| Bloques ocupados | 19 (del 3 al 21) | 5 |
| Bloque más corto | 42 > 40 → válido | 102 ≤ 250 → inválido |
| Huecos intermedios de `^STOXX50E` | 1.406, edades ⊆ {1, 3, 4} | 1.312, edades ⊆ {1, 3, 4} |

- Regiones, en número de activos: ASIA 16, EUROPA 30, USA 40, GLOBAL 3 y EMERGING_MARKETS 1.
- Los 20 controles de identidad del ejecutor salen OK en los dos horizontes.
- El hash de población lo calculó el revisor por su cuenta, aparte del ejecutor, y coincide.

### 3. Auditoría PIT independiente sobre toda la población (183.427 señales)

El contexto se recalculó **sin** `point_in_time.py`, `session_close_at` ni `expected_sessions`:
- **calendarios:** `exchange_calendars` sin modificar, con los cierres de D-54 escritos a mano;
- **pasadas:** a las 07:00, 08:30, 14:30 y 21:00 hora de Londres, de lunes a viernes, convertidas
  con zoneinfo;
- **VIX y tendencia:** última barra de una sesión válida cuyo cierre más 20 minutos no supera `ts`;
- **SMA200:** media de los últimos 200 cierres causales;
- **Asia:** las sesiones L y P salen del calendario, y se exige que existan las dos barras.

Resultado, en swing y en medio:
- `analysis_timestamp` distintos: **0**.
- Contextos distintos: **0**. Se compararon las sesiones de VIX y de tendencia, el número de
  cierres, los valores de VIX, tendencia, SMA y Asia, y las sesiones asiáticas L/P.
- **Look-ahead** (algún dato usado con `available_at > ts`): **0**.
- Puntos de contexto independientes que no coinciden con la dimensión `contexto` que puntuó: **0**.
- Margen mínimo entre `ts` y el `available_at` del dato más reciente usado: **600 s**.

### 4. Paridad R-CTX con datos reales (`revisor/d_paridad_real.py`)

Muestra: 48 señales de 8 activos (SAP.DE, AIR.PA, ASML.AS, BBVA.MC, AAPL, AZN, 7203.T y 0700.HK).
Cubren las plazas XETRA, PAR, AMS, MCE, NASDAQ, JPX y HKG, entre 2022 y 2026.

Caminos comparados, todos frente a `resolver.resolve(ts)`:
- `run_analysis(..., score_model_version="2.0", now=ts)`, que es el de producción v2;
- `review_positions(..., now=ts)`, el de seguimiento, con el selector forzado a PIT;
- `run_backtest(vintage=…, score_model_version="2.0")`;
- `run_event_study_on_vintage(score_model_version="2.0")`.

Resultado: **48/48 idénticos y 0 fallos**, todos con `source="point_in_time"`.

### 5. Cortes

El revisor usó su propio nearest-rank en aritmética entera, contrastado con
`numpy.percentile(method="inverted_cdf")`.

| | Swing | Medio |
|---|---|---|
| Cortes p20/p40/p60/p80 | 28,0 / 39,6 / 49,6 / 57,6 | 29,6 / 40,0 / 49,6 / 57,6 |
| Valores distintos | 817 | 730 |
| Empates entre cortes | ninguno | ninguno |
| n por quintil (Q1…Q5) | 18.292 / 18.740 / 19.405 / 17.205 / 20.452 | 17.071 / 18.387 / 16.640 / 16.940 / 20.295 |

- **Candidatos de swing:** 43,6 / 49,6 / 53,6 / 57,6 / 63,6, sin colapsos. Las bandas `[c, ∞)`
  tienen 49.056 / 37.657 / 28.670 / 20.452 / 9.595 señales.
- **Ablaciones:** sus cortes coinciden con los publicados.
- **Empates:** las observaciones con un valor igual a un corte **suben de banda**, como manda la
  ficha.
- **Redondeo** (`canonical_score`, 9 decimales): no cambia nada. Los cortes salen iguales, ninguna
  señal cambia de quintil y no hay valores crudos a menos de 1e-9 de un corte
  (`revisor/e_raw_vs_canon.py`).

### 6. Aritmética sobre los artefactos publicados (`revisor/b_aritmetica_artefactos.py`)

Solo usa agregados de #33.
- **Δ del bloque 3:** −0,0482 − 0,6721 = **−0,72033**.
- **Media de los 19 Δ de bloque:** **−0,28946785451648893**, igual que el contraste publicado.
- **IC95:** el de `bootstrap_block_mean_interval` y el de una reimplementación propia coinciden:
  [**−0,4097552592**, **−0,1657789209**]. La anchura es **0,2440 > 0,20** → **NO CONCLUYENTE**.
  Hay 19 bloques, por encima del mínimo de 12.
- **Δ negativo** en 16 de los 19 bloques.
- **Activos:**
  - primario > 0 en 75;
  - Δ calculable en 89 y negativo en los 89;
  - IC por debajo de 0 en 83 y por encima de 0 en ninguno.
- **Intra-activo:** −0,7512 [−0,8150, −0,6720], con 1.512 pares calculables y 178 excluidos.
- **Contadores:** 329 y 309, y `contadores_coinciden: true`.

### 7. D-59 y producción (`revisor/c_produccion_d59.py`)

- `config.yaml` está en "1.0", con 70/60 y `calibrated: false` en los tres horizontes. Su
  `config_hash` es `89406d28…6387`.
- **Activar "2.0" falla siempre**, con el error «score_model_version no activable en producción:
  2.0». Falla con 70/60, con umbrales nulos y también con un `calibrated: true` inventado.
- **Investigación v2 desde la config "1.0":** `scoring_for_requested_model` devuelve "2.0", y los
  tres horizontes quedan en `(calibrated False, None, None)`.
- **Selector de contexto:** `resolve_context_mode("2.0", None)` devuelve `point_in_time`, y
  `resolve_context_mode("2.0", "legacy_v1")` lanza `ValueError`.

### 8. Integridad de la evidencia

- `shasum -a 256 -c SHA256SUMS-ejecucion.txt`: **30/30 OK**. Coincide exactamente con todos los
  ficheros de `run/` y de `consola/`.
- `preflight/SHA256SUMS`: **8/8 OK**.
- Paso 4, `hashes-de-tablas.txt`: **22/22 OK**.
- `git log 9d4ffb1..HEAD -- evidence/2026-09-30-T-019-paso3-p3 advisor/research/p3.py` está vacío.
- Después de `87309da`, lo único que cambia en `advisor/`, `tests/` o `config.yaml` es la condición
  de salto de un test (`9089bc3`).
- El preflight interno y el oficial dan el mismo `p3-preflight.txt` (`3a0f4540…`).

### 9. Impacto del paso 4

Los percentiles de v2 sobre la población reconstruida coinciden con
`tablas/{swing,medio}-percentiles.tsv`: medias 43,22 / 43,98 y 817 / 730 valores distintos.

### 10. SAP.DE

- Sesión de la señal 2022-06-13 y entrada el 2022-06-14, en el bloque 3.
- Score v2 **4,4**, que cae en **Q1**.
- Contexto 1,2, tanto en el cálculo independiente como en la observación.
- `ts` = 2022-06-14T06:00Z.

## Qué se verificó leyendo el código

- **Temporalidad del contexto.**
  `git diff 782e462 87309da -- advisor/context advisor/research/event_study.py advisor/research/timestamps.py advisor/data advisor/analysis/market_context.py`
  solo añade dos cosas:
  - el campo `MarketContext.source`, que marca el contexto como `point_in_time`;
  - una guarda para una lista asiática vacía.

  La semántica temporal que validó la revisión 1 es la que se ejecutó.
- **Camino v2 de P3.** `run_p3_event_study` fuerza `point_in_time` y "2.0". Si el contexto PIT es
  `None`, la señal se descarta; nunca se cae a legacy.
- **Score v2.** `compute_score` rechaza v2 con un contexto que no sea point-in-time
  (`advisor/analysis/scoring.py:416-417`).
- **Orientación del contraste.**
  - `quintile_of` pone la nota más baja en Q1.
  - `paired_block_contrast("Q5−Q1", high=Q5, low=Q1)` calcula `high_mean − low_mean` por bloque
    (`p3.py:750` y `p3.py:344`).
  - Los primarios por quintil, que no dependen de ese código, apuntan en la misma dirección:
    Q1 0,343 frente a Q5 0,054.
  - El primario global, 0,1549, coincide con A-02.

  **El signo negativo no es un error de orientación.**
- **Veredicto** (`p3.py:359-391`). Las condiciones de NO CONCLUYENTE se evalúan primero, en este
  orden: horizonte inválido, Δ no calculable, menos de 12 bloques, anchura > 0,20 y
  `SCORE_RESOLUTION_INSUFFICIENT`. Después vienen SUFICIENTE, LIMITADA e INSUFICIENTE. Es el orden
  pre-registrado.
- **Calibración** (`p3.py:803-889`):
  - la capacidad P2.5 se calcula aparte del veredicto;
  - Bonferroni con `1 − 0,05/20 = 0,9975` y 20.000 remuestreos;
  - una familia de 20 miembros fijada con una aserción;
  - la meseta OPERAR se recorre de mayor a menor y se corta en el primer fallo;
  - el recorrido VIGILAR es literal;
  - medio lleva el veredicto forzado y no se calibra.
- **Marca de ejecución única** (`p3.py:1251-1282`). El orden es:
  1. la marca no existe, el árbol está limpio y `run/` está vacío;
  2. el preflight se ejecuta sin desenlaces;
  3. se escribe la marca;
  4. solo entonces se llama a `build_population(with_outcomes=True)`.

  Las horas lo confirman: el preflight termina a las 17:58:02.977 y la marca es de las 17:58:03.136.
- **Ablaciones.** `scoring.py` es idéntico en `5953300`, `87309da` y `4ca9a37`. Las ablaciones no
  seleccionan nada.
- **Fortaleza relativa.** Cada benchmark se lee con su sesión `d` ya cerrada antes de `ts`. Ningún
  activo asiático usa un benchmark de EE. UU.
- **Seguimiento.** `review_positions` usa `now` como `analysis_timestamp`, como exige R-CTX.

---

## Resultado, punto por punto

1. **Look-ahead: CORRECTO, verificado EJECUTANDO y LEYENDO.**
   - D-50: 0 diferencias de `ts` sobre las 183.427 señales.
   - D-52 a D-56: 0 diferencias de contexto.
   - Ningún dato tiene `available_at > ts`.
   - El camino v2 llama 0 veces a `_naive_dates`/`_align`.
   - El código ejecutado es el que revisó la revisión 1.
2. **Paridad R-CTX / INV-06: CORRECTO, EJECUTANDO.** Pasa el test sintético del repositorio, y el
   control sobre la cosecha real sale 48/48 idéntico en los cuatro caminos.
3. **D-59: CORRECTO, EJECUTANDO.** v2 implica PIT; v2 con `legacy_v1` falla; la config "1.0" no
   contamina una investigación v2. Además está la guarda estructural de `compute_score`.
4. **Población: CORRECTO, EJECUTANDO.** Se reproducen exactamente todas las cifras.
5. **Cortes: CORRECTO, EJECUTANDO.** Nearest-rank exacto, sin desenlaces, con los empates subiendo
   de banda, sin colapsos y coincidentes con los congelados.
6. **Ejecutor `87309da`: CORRECTO, LEYENDO** y contrastado con los artefactos. Se comprobó:
   - Q5−Q1 pareado por bloque;
   - IC95 estándar, reproducido;
   - orden del veredicto;
   - capacidad P2.5 separada;
   - Bonferroni con m = 20, 0,9975 y 20.000 remuestreos;
   - meseta OPERAR y recorrido VIGILAR;
   - medio forzado;
   - contadores 329/309/638;
   - marca escrita antes de abrir desenlaces.
7. **Resultado: CORRECTO, EJECUTANDO sobre los agregados.**
   - Δ −0,2895 [−0,4098, −0,1658], anchura 0,2440 → NO CONCLUYENTE.
   - El signo solo aparece como descriptivo.
   - Ningún candidato cumple OPERAR: los cinco fallan las condiciones 2, 3 y 4.
   - No se fabricó ningún umbral: los valores 43,6, 57,6 y 63,6 solo aparecen como candidatos que
     fallan.
   - El signo no viene de un error de orientación.
8. **Ablaciones: CORRECTO.** Son descriptivas y `scoring.py` no cambió.
9. **Sesgo de universo: CORRECTO en las salidas de P3, con un defecto documental (M-1).**
10. **Paso 4: CORRECTO**, reproducido en parte.
    - Coinciden los percentiles de v2, el H-6 (0 contextos incompletos), SAP.DE y el Δ del bloque.
    - La clasificación operativa dice «no aplica».
    - Confianza: solo leída, porque la pasada necesita red.
11. **Integridad: CORRECTO, EJECUTANDO.** Los hashes dan 30, 8 y 22 OK, y ningún commit posterior a
    `9d4ffb1` toca la evidencia de P3 ni `p3.py`.
12. **Producción: CORRECTO, EJECUTANDO.**
    - `config.yaml` sigue en "1.0".
    - 70/60 solo se admite con "1.0".
    - v2 no se puede activar.
    - D-47 sigue vigente.
    - D-60 no hace falta mientras v2 no vaya a producción.

---

## Hallazgos

### M-1 · MENOR — Falta la etiqueta de sesgo de universo en conclusiones posteriores a la ejecución

- **Dónde:**
  - `docs/decision-log.md:1074-1119` (D-61);
  - `evidence/2026-10-01-T-019-score-v2/calculo-manual-delta-bloque.md`;
  - el estado tras P3 en la ficha T-019 (líneas 20 y 1598);
  - la fila A-03 de `docs/roadmap.md:215`.
- **Evidencia:** la ficha (`T-019…md:995-996`) exige la etiqueta «en toda tabla y conclusión».
  D-61 publica el Δ, el signo por región y por activo y el intra-activo sin llevarla.
- **Por qué no altera la ejecución congelada:** todos los artefactos de #33 llevan la etiqueta. El
  defecto está solo en cómo se presentan en documentos posteriores.
- **¿Bloquea GATE P3?** **No.**

### O-1 · OBSERVACIÓN — El seguimiento toma el modo de contexto de la versión activa

- **Dónde:** `advisor/report/tracking.py:121`.
- **Qué pasa:** el modo sale de la versión activa de la config, no de la versión pedida.
- **Por qué no es un defecto hoy:** v2 no es activable. Hay que tenerlo presente si algún día se
  activa.
- **¿Bloquea?** No.

### O-2 · OBSERVACIÓN — `canonical_score` redondea a 9 decimales y el pre-registro no lo fija

- **Dónde:** `advisor/research/p3.py:135-139`.
- **Comprobación:** ejecutado con y sin redondeo, el efecto es nulo.
- **¿Bloquea?** No.

### O-3 · OBSERVACIÓN — El test de paridad del repositorio usa datos sintéticos

- **Dónde:** `tests/test_point_in_time_context.py:589-742`.
- **Cubierto por:** el control de 48 casos con la cosecha real y la auditoría completa.
- **¿Bloquea?** No.

### O-4 · OBSERVACIÓN — La revisión 1 se hizo sobre el árbol sin commitear

- **Qué pasa:** se hizo antes de `782e462`.
- **Por qué no importa:** esta auditoría corre sobre `87309da`, el código que se ejecutó.
- **¿Bloquea?** No.

### O-5 · OBSERVACIÓN — Contexto PIT no calculable en una pasada de producción v2

- **Dónde:** `advisor/context/point_in_time.py:196-198`.
- **Qué pasa:** hoy, si el contexto no es calculable, aborta la pasada entera.
- **Por qué no importa ahora:** D-60 ya lo registra, y solo entra en juego si se activa v2.
- **¿Bloquea?** No.

---

## Dictamen sobre GATE P3

| # | Requisito | Dictamen | Base |
|---|---|---|---|
| 1 | `score_model_version` nuevo; nada se mezcla sin etiqueta | **SATISFECHO** | "2.0" en `Score` y `SignalObservation`; `score_band` rechaza lo que no sea 1.0; `_record` exige "2.0" |
| 2 | Umbrales por horizonte con `calibrated` | **SATISFECHO** | Swing `false` por la regla, con los 5 candidatos fallando (verificado); medio por invalidez; intradía sin laboratorio. El contrato impide activar v2 |
| 3 | Ordenación con veredicto | **SATISFECHO** | Quintiles, tabla 19×5, contrastes y Δ reproducidos; NO CONCLUYENTE aplicado mecánicamente |
| 4 | Ablación publicada | **SATISFECHO** | Tres ablaciones reproducidas, descriptivas, y Score v2 sin cambios |
| 5 | Revisión independiente del look-ahead | **SATISFECHO** con esta revisión | 0 look-ahead y 0 diferencias de contexto sobre 183.427 señales; paridad 48/48; ningún BLOCKER ni IMPORTANTE |

**No hay ningún motivo para no cruzar GATE P3 con la etiqueta NO CONCLUYENTE.** Conviene corregir
el MENOR M-1, pero no condiciona el cruce.

## Límites

- La pasada local de producción de `confianza.md` necesita red: se verificó solo leyendo.
- Los calendarios se validan con `exchange_calendars` y con las fuentes de D-54, no contra las
  fuentes oficiales de cada plaza.
- No se calculó ningún desenlace por señal. La corrección de `net_R` se apoya en que coincide con el
  instrumento de A-02.

## Scripts y salidas

Están en `revisor/`:
- `a_poblacion_y_pit.py` → `a_salida.txt` y `a_stdout.txt`;
- `b_aritmetica_artefactos.py` → `b_salida.txt`;
- `c_produccion_d59.py` → `c_salida.txt`;
- `d_paridad_real.py` → `d_salida.txt`;
- `e_raw_vs_canon.py` → `e_salida.txt`;
- `paso4-sums.txt`.

Las TSV por señal (`poblacion-{swing,medio}.tsv`, unos 19 MB entre las dos y sin desenlaces) no se
versionan. Sus sha256 están en `hashes-evidencia.txt`.
