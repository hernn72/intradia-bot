# Revisión final independiente del cierre de P4 (T-020)

**Procedencia.**
- **Quién:** un agente `revisor` (Claude), distinto de quien programó, de la revisión del paso 2 y de
  la revisión de look-ahead. La lanzó la sesión de cierre el 2026-10-02 en modo adversarial y solo
  lectura, con los puntos A–I del propietario.
- **Sobre qué:** HEAD `3d86036` (D-64).
- **El texto:** se copia **literalmente** el informe que devolvió; solo se ha quitado la sangría del
  mecanismo de entrega. Los hallazgos no se borran aunque luego se corrijan. Al final se añade la
  sección «Vuelta de cierre de hallazgos», con la segunda vuelta del mismo revisor.

---

RESULTADO: REQUIERE CAMBIOS

No hay ningún BLOCKER. El resultado mecánico de P4 queda confirmado a partir de los artefactos congelados. Hay dos hallazgos IMPORTANTE y uno MENOR que no cambian el resultado; los dos IMPORTANTE conviene cerrarlos en el commit que cruce el gate. **Veredicto: GATE P4 PUEDE CRUZARSE.**

**Lo que no ejecuté:** no ejecuté `p4` en ninguna fase ni `comparacion-pareada`, y no modifiqué ningún fichero. `git status` muestra solo los dos ficheros sin seguimiento que ya estaban (`graphify-out/` y `ultima_cerrada`). Todo lo recalculado sale de `run/p4-resultado.json`, `run/tablas/*.tsv` y `preflight/p4-preflight.json`.

Dos cosas que conviene saber:
- `pytest tests/test_p4.py`, que estaba autorizado, contiene un test que ejecuta el **preflight real** sobre la cosecha. Lo hace con los evaluadores de desenlaces bloqueados (`_forbid_outcomes`) y con `write=False`, así que no lee desenlaces ni escribe nada.
- Para comprobar `leer_estratos.py` no lo ejecuté tal cual, porque escribe `estratos-congelados.md`. Cargué el módulo, desvié su fichero de salida al scratchpad y comparé el resultado con el publicado.

## Puntos A–I

**A. Integridad de la ejecución: OK**
- **Marca única.** Hay una sola marca, `run/EJECUCION_CONFIRMATORIA_P4_INICIADA`, con `inicio_utc` 05:37:50Z. Es posterior al fin del preflight (05:30:18Z) y al commit c2c52b1 (05:30:38Z), y anterior a los resultados: el JSON tiene `fin_utc` 05:43:52Z y los ficheros tienen esa misma hora de modificación.
- **Identidad en la marca:** `p4_prereg_sha`=48b8847…, `p4_executor_sha_preflight`=3df8230…, `head_sha`=c2c52b1… y `git_dirty`=false.
- **Población y niveles congelados:**
  - los hashes de población y de `signal_ids` son 78024050…3141 y 9faa4a45…629f;
  - los cinco `niveles_sha256` son idénticos a los de `preflight/p4-preflight.json` y a los de `p4-resultado.json` → `preflight.niveles_sha256`;
  - los cortes de terciles [0.019819…, 0.030590…] coinciden;
  - la semilla es 20260830 y la familia es [B2, S1, S2, E1].
- **Integridad de `run/`.** `shasum -c SHA256SUMS-ejecucion.txt` da 12/12 OK, y `SHA256SUMS.txt` del preflight da 7/7 OK. `git diff cfa365d HEAD -- …/run` está vacío.
- **`p4_executor_sha`=c2c52b1 no es un error de resultado.** `run_confirmatory` (`advisor/research/p4.py:1946-1948`) se niega a ejecutar si `git diff --quiet 3df8230 HEAD -- advisor config.yaml universe.yaml exchange_overrides.yaml pyproject.toml requirements.txt` no está vacío. La marca guarda 3df8230 aparte (`p4.py:1984-1985`).
- **Código de salida 0:** ver la observación 1.

**B. Código ejecutado: OK**
- `git diff --stat 3df8230 c2c52b1` toca solo los 8 ficheros de `evidence/…/preflight/`.
- `git diff c2c52b1 HEAD -- advisor tests config.yaml deploy` está vacío.
- c2c52b1..HEAD solo añade `run/`, `docs/decision-log.md` y `evidence/2026-10-02-T-020-p4-cierre/`.

**C. Resultado mecánico, recalculado solo desde los artefactos: OK**
- **Condiciones de capacidad (`capacidad.tsv`):**
  - 20 bloques con pares (≥ 12);
  - mínimo de 3.599 pares por bloque (≥ 5);
  - descarte por ambigüedad ≤ 0,000652 (≤ 25 %);
  - `EXIT_FINAL` de C0 0,013975 y de las variantes ≤ 0,018676 (≤ 10 %);
  - anchura del IC95: B2 0,1020, S1 0,0479 y S2 0,0404 (≤ 0,20).
- **Pares sobre 101.251:**
  - B2 101.226 (0,99975), que cuadra con 101.251 − 25;
  - S1 101.185, que cuadra con 101.251 − 10 − 41 − 15;
  - S2 101.225, que cuadra con 101.251 − 21 − 1 − 4.
  - Las sumas de `n` por bloque en `bloques-60.tsv` coinciden con esos pares, y el TSV coincide fila a fila con el JSON.
- **B2 y S2 pasan todas las condiciones que vetan:**

  | Condición | B2 | S2 |
  |---|---|---|
  | 1. Inferior del IC de Bonferroni | 0,00611 | 0,00761 |
  | 2. Bloque 120: ΔR / IC95 inferior | 0,0726 / 0,0238 | 0,0346 / 0,0131 |
  | 5. Cota conservadora | 0,0710 | 0,0343 |
  | 6. Niveles coherentes (preflight) | `incoherentes`=0, `rr_efectivo_bajo_min_rr`=0 | igual |
  | 8. Mitades 2–11 / 12–21 | 0,0693 / 0,0740 | 0,0239 / 0,0456 |
  | 10. Nivel: media `net_R` / PF agrupado | 0,1754 / 1,263 | 0,1388 / 1,243 |

  Recalculé desde las 20 medias por bloque la media primaria, las mitades y la dispersión (desviación típica muestral), y coinciden con el JSON.
- **S1 falla exactamente las condiciones 1, 2, 5 y 8:**
  - condición 1: superior de Bonferroni −0,0096, inferior −0,0708;
  - condición 2: ΔR −0,0407 en el bloque 120;
  - condición 5: cota conservadora −0,0418;
  - condición 8: mitades −0,0326 y −0,0495.
  - Las condiciones 3, 6, 9 y 10 pasan (nivel 0,0633 y PF 1,103).
- **E1:** IC [−0,1078, +0,0120], que contiene el 0, y capacidad OK → NO CONCLUYENTE.
- **B1:** IC95 con 2.000 remuestreos, sin fila de criterio.
- Las condiciones 4 y 7 tienen `veta=False` en `criterio.tsv`.

**D. Multiplicidad: OK**
- En `estimaciones.tsv`, exactamente 4 filas tienen (0,9875; 20.000): las primarias de B2, S1, S2 y E1. Las otras 439 tienen (0,95; 2.000), incluida la primaria de B1.
- La familia es `[B2_vs_C0, S1_vs_C0, S2_vs_C0, E1]`, y B1 figura en `fuera_de_la_familia`.

**E. Población: OK**
- 101.251 señales (106.363 − 5.112 de cripto) de 90 activos.
- `exclusiones_p3_aplicadas=false`; las 7.157 señales `NO_CALCULABLE_CONTEXT` siguen en la población.
- Los hashes coinciden.

**F. Heterogeneidad: OK, salvo el hallazgo MENOR**
- La bandera ALTA no veta.
- Las filas de estratos son exactamente las pre-registradas, ni más ni menos:
  - B1 y B2: 5 regiones, 3 regímenes, 3 terciles y 90 activos;
  - S1 y S2: lo mismo más 3 de `stop_basis`;
  - E1: solo la primaria.
- Las 443 filas de `estimaciones.tsv` más las 4 de `nivel.tsv` suman 447.
- Todas las cifras de `resultado-y-heterogeneidad.md` coinciden con el TSV. Los conteos son B2 75/15/20/0, S2 73/17/17/0 y S1 76 negativos, 15 con el IC95 entero por debajo de 0 y 0 con el IC95 entero por encima.
- `leer_estratos.py` regenerado en el scratchpad da un resultado **idéntico** a `estratos-congelados.md`.
- No se crea ninguna política condicionada por estrato.

**G. Requisito 3 del gate (holgura D-06): OK**
- `preflight/p4-preflight.json` → `holgura_d06` incluye C0, B1, B2, S1 y S2, en global y por región.
- Para cada geometría da:
  - `rr_*`, la holgura RR (`entry_max_rr − P`) en precio, ATR y %;
  - `efectiva_*`, la holgura efectiva, en las mismas unidades;
  - `manda`;
  - `categoria_open_t1`, con fracciones y la distancia `ABOVE_MAX_ENTRY` en ATR.
- Fracción `ABOVE_MAX_ENTRY` a la apertura de t+1: C0 46.744, B1 26.552, B2 4.680, S1 48.949 y S2 44.156.

**H. Comparaciones: OK**
- `recuento_derivado`: B1 110, B2 110, S1 113, S2 113 y E1 1, total 447, de las que 4 son confirmatorias.
- `recuento_coincide=true`.

**I. Producción: OK**
- `config.yaml` tiene el mismo sha256 que en 48b8847 (f230467e…).
- `score_model_version: "1.0"` en las líneas 58, 61, 67 y 73.
- `git diff 48b8847 HEAD -- config.yaml deploy` está vacío.
- `git tag --contains 48b8847` está vacío; los tags existentes van de v0.1.0 a v0.4.1.

## Hallazgos

**[IMPORTANTE] La suite de P4 falla en HEAD después de la ejecución**
- **Ubicación:** `tests/test_p4.py:396`.
- **Escenario de fallo:** cualquier ejecución de la suite después de cfa365d.
- **Resultado incorrecto:** `1 failed, 49 passed`. Falla `test_preflight_real_reproduce_poblacion_bloques_y_recuento_sin_desenlaces` con `assert (False is False and True is False)`.
- **Causa:** `p4_confirmatory_executed` es `(CONFIRMATORY_OUTPUT_DIR / RUN_MARKER).exists()` (`p4.py:1868`). La marca ya existe, así que el test no puede volver a pasar nunca. El test 14 de la ficha («la suite, igual») queda incumplido en HEAD, y no hay ningún `final-pytest-ruff-mypy.txt` posterior que lo declare. ruff y mypy están limpios.
- **Corrección recomendada:** asertar `outcomes_read is False` y que `p4_confirmatory_executed` sea igual a `marker.exists()`. `tests/` no está en `EXECUTOR_PATHS`, así que el cambio no altera el código ejecutado. Después, archivar la salida de la suite completa.

**[IMPORTANTE] Falta en el repositorio la evidencia de la revisión de look-ahead (paso 3) y de la verificación final**
- **Ubicación:** la ficha la exige en `docs/tareas/T-020-p4-geometria.md:795` (§24) y `:1144` (§28, paso 3).
- **Resultado incorrecto:** no existen `revision-look-ahead.md` ni `final-pytest-ruff-mypy.txt` para T-020 (`git ls-files | grep -i look-ahead` solo encuentra los de T-019). La única constancia de que la revisión quedó «LIMPIA» está en el mensaje del commit cfa365d. Además, `preflight/README.md:8` condiciona que 3df8230 pase a ser el ejecutor a esa revisión.
- **Impacto:** no invalida el resultado, pero un requisito de proceso pre-registrado no se puede auditar.
- **Corrección recomendada:** archivar el informe de la revisión de look-ahead que hubo entre c2c52b1 y la marca, y la suite final, en `evidence/2026-10-02-T-020-p4-cierre/`.

**[MENOR] La discusión de los estratos no cubre B1 ni el `stop_basis` de S1**
- **Ubicación:** `evidence/2026-10-02-T-020-p4-cierre/resultado-y-heterogeneidad.md`, §2–§4.
- **Escenario:** la ficha (§16, `T-020…md:494`) exige publicar *y discutir* los estratos si la bandera sale ALTA en B1, B2, S1 o S2.
- **Resultado incorrecto:** B1 sale ALTA. Sus tablas están en `estratos-congelados.md`, pero no hay ninguna discusión. En S1 no se menciona `stop_basis`.
- **Impacto:** ninguno sobre el criterio, porque ni B1 ni S1 se eligen; es solo cumplimiento literal.
- **Corrección recomendada:** añadir dos o tres frases descriptivas.

**[OBSERVACIÓN 1] El código de salida 0 no consta literalmente**
- D-64 afirma «salida 0», pero `consola-confirmatoria.txt` no lo registra: tiene una cabecera escrita a mano y el resumen.
- Se deduce de forma sólida por tres vías:
  - el resumen solo se imprime tras `return 0` (`p4.py:1965-1974`);
  - no existe `p4-parada.json`;
  - `p4-resumen.md` es idéntico a la consola salvo la cabecera.

**[OBSERVACIÓN 2] «Se concentra sobre todo en RISK_OFF» puede leerse como una exageración**
- **Ubicación:** `resultado-y-heterogeneidad.md:70` y `:121`.
- Es cierto por señal, pero no por contribución al total:
  - B2: RISK_OFF ≈ 0,245 × 7.944 ≈ 1.945, frente a RISK_ON ≈ 0,085 × 73.702 ≈ 6.261;
  - S2: unos 696 frente a 3.045.
- **Sugerencia:** «es mayor por señal en RISK_OFF». No excede lo pre-registrado.

## Comprobaciones ejecutadas
- `git` diff, log, show y tag.
- `shasum -c` de los dos manifiestos.
- Recálculo tabular desde el JSON y los TSV (criterio, capacidad, emparejamiento, mitades, recuento y estratos).
- `pytest -q tests/test_p4.py`: 49 passed, 1 failed (el hallazgo IMPORTANTE de arriba).
- `ruff check advisor tests`: limpio.
- `mypy advisor`: limpio, 72 ficheros.

## Limitaciones
- No ejecuté la suite completa (824 tests) porque solo estaba autorizado `test_p4.py`.
- No puedo verificar el contenido de la revisión de look-ahead: no está archivada.

## Veredicto
**GATE P4 PUEDE CRUZARSE.** No hay ningún BLOCKER: los requisitos 1–4 del gate están cubiertos y el resultado (B2 y S2 pasan a P5; S1 falla 1/2/5/8; E1 NO CONCLUYENTE; B1 descriptiva) sale de forma fiel de los artefactos íntegros. Recomiendo resolver los dos hallazgos IMPORTANTE, el test con estado y el archivo de la revisión de look-ahead y de la suite final, en el mismo commit que declare el cruce.

---

> Nota del cierre: por la regla mecánica del propietario (cruzar solo con 0 BLOCKER y 0 IMPORTANTE),
> GATE P4 **no** se cruzó con este informe. Se declaró OWNER_DECISION_REQUIRED, y el propietario
> autorizó corregir los dos IMPORTANTE y los MENOR y pedir una segunda vuelta al mismo revisor.

## Vuelta de cierre de hallazgos

_(pendiente: se añade con el resultado literal de la segunda vuelta del mismo revisor)_
