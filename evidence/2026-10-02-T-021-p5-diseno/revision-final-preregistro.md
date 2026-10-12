# Revisión final del pre-registro de P5 (sobre D-66, commit `53b2f48`)

Mismo agente `revisor`, en solo lectura y sin desenlaces. Mandato del propietario: comprobar
únicamente que las decisiones de D-66 se transcribieron fielmente y que no apareció ningún grado de
libertad nuevo. Informe transcrito literalmente; sus hallazgos se corrigieron en el commit
siguiente.

---

RESULTADO: REQUIERE CAMBIOS (solo cambios MENOR de redacción: 0 BLOCKER, 0 IMPORTANTE)

Revisión final de 53b2f48, en solo lectura, sin desenlaces y sin commits. He leído D-66 en `docs/decision-log.md` (desde l.1347), la ficha completa en 53b2f48 y el diff 4feadf0..53b2f48. D-66 recoge fielmente lo que decidió el propietario, y la ficha lo aplica. No aparece ningún grado de libertad nuevo que permita mover el resultado. Quedan 2 MENOR y 2 OBSERVACIÓN, todos de redacción.

Las líneas son de la ficha en 53b2f48, salvo cuando se indica D-66.

## Hallazgos

**[MENOR] §27 sigue dejando abierta la promoción de vecinos (l.786-788)**

- **Qué dice:** «Si el propietario entendiera que el gate exige poder promover puntos de la superficie, sería una OWNER_DECISION previa a medir. Esta ficha recomienda que no.»
- **Por qué sobra:** OD-P5-13 = A ya está cerrada en D-66 (punto 14). El texto sigue planteando como abierta una decisión que lo está.
- **Cómo se cierra:** sustituirlo por «D-66 (OD-P5-13 = A) lo cierra: ningún vecino es elegible; promoverlos exigiría un estudio nuevo».

**[MENOR] «Regiones» significa dos cosas distintas en el preflight**

- **Dónde:** regla 5 de OD-P5-16 (l.1265), test 7 (l.1301-1303) y §29 (l.900).
- **El conflicto:**
  - la regla 5 y el test 7 exigen que, antes de la marca, «fallen explícitamente» las rutas de «las regiones y subpoblaciones»;
  - en cambio, §29 obliga a derivar el 71 antes de los desenlaces «de la estructura (rejilla, validez y regiones)»;
  - y §6 (l.151) y §19.2 piden reproducir en el preflight el censo por región y los denominadores del LOCRO (56.353 / 66.629 / 83.298).
- **Riesgo:** leído al pie de la letra, un test que espera una excepción en «regiones» choca con el censo estructural que el preflight necesita. El implementador tendría que decidir qué significa.
- **Cómo se cierra:** precisar que fallan las **estimaciones** por región o subpoblación (cualquier cálculo con desenlaces), y que el censo estructural por región y los denominadores del LOCRO, que no usan desenlaces, se calculan y se comprueban en el preflight.

**[OBSERVACIÓN] El hash de un vecino solo se distingue del de una candidata por un campo fuera del hash**

- **Dónde:** §28, l.792-801.
- **Qué pasa:** los vecinos se hashean con el mismo esquema `intradia.p5.politica.v1`, y su papel diagnóstico (`procedencia.rol`) queda fuera del hash. La regla «un vecino nunca recibe hash de política candidata» se cumple por el rol y por el test 11 (l.1313-1315), así que no es un defecto.
- **Sugerencia:** para que sea mecánico, publicar el hash de los vecinos con otro nombre de campo y no incluirlo nunca en la lista de políticas candidatas.

**[OBSERVACIÓN] Quedan restos de «recomendación» fuera de §33**

- **Dónde:** el título de §12.2 (l.401, «recomendación C») y §23.3 (l.684, «(recomendada)»).
- **Cómo se cierra:** cambiarlos por «Decisión (D-66)». No cambia ninguna regla.

## Estado de los 12 puntos

| # | Punto | Estado | Evidencia |
|---|---|---|---|
| 1 | `m3_auxiliar` nunca elegible | **CUMPLE** | D-66 punto 2 (l.1384-1389 del log); ficha §12.2, §28 l.797-801 y test 11 l.1313-1315 |
| 2 | Exactamente 13 vecinos válidos | **CUMPLE** | D-66 punto 4; §11.5 (8 + 5); test 1 |
| 3 | Las 3 ausencias de S2 fuera de todo denominador | **CUMPLE** | D-66 punto 3; §12.1 l.397; §15 l.483 |
| 4 | S2 mantiene la tolerancia asimétrica | **CUMPLE** | D-66 punto 4; §11.6 l.386; OD-P5-5 l.1046 |
| 5 | Umbral 0,75 fijo | **CUMPLE** | D-66 punto 6; §23.1 l.658; F4 l.730; §26 l.750 |
| 6 | \|NE\| ≤ 1 | **CUMPLE** | D-66 punto 6; §23.1; OD-P5-4 |
| 7 | LOCRO con denominadores relativos, nunca 91.126 | **CUMPLE** | D-66 punto 9; §15 l.476; §19.2 l.569-576; OD-P5-8; test 6 con el caso del denominador absoluto |
| 8 | 0 confirmatorias nuevas | **CUMPLE** | D-66 puntos 8 y 16; §22 l.626; §29 |
| 9 | Ningún vecino elegible | **CUMPLE** | D-66 puntos 4 y 14; §27; test 11 (queda el resto de texto del MENOR de §27) |
| 10 | El preflight no puede producir LOCRO ni vecinos | **CUMPLE** | D-66 punto 17; reglas 1-6 de OD-P5-16; test 7 (con la precisión del MENOR sobre «regiones») |
| 11 | El 71 se deriva de la estructura, con STOP si no | **CUMPLE** | D-66 punto 16; §29 l.900-902; test 10 |
| 12 | P5 no es validación | **CUMPLE** | D-66, «Qué es P5»; §5 y §17; §32 l.945 |

## Otras comprobaciones

- **Transcripción de D-66:**
  - las 16 OD de la ficha están marcadas «CERRADA (D-66)», con una decisión que coincide con la recomendación de cada una;
  - OD-P5-8 queda como «A con la capacidad i»;
  - en OD-P5-16 están las seis reglas vinculantes (l.1245-1270): lista blanca de geometrías, lista blanca de filas con `primaria_60` como fila de Bonferroni, cadenas `{:.6f}` con STOP y sin tolerancia, C0 por identidad y hash, aislamiento, y que no autoriza repetir P4;
  - el punto 17 de D-66 dice lo mismo.
- **Filas de la lista blanca:** todas existen en los TSV congelados de P4 y están publicadas. El IC95 de la capacidad solo compara la anchura; sus extremos no se archivan.
- **§26:** la condición 1 ya remite a OD-P5-16 (l.749).
- **Sin grados de libertad nuevos:** los tests 7, 8, 10 y 11 solo añaden guardas. La renumeración del 11 al 13 no pierde ningún test.
- **§37:** coherente con el estado.
- **Roadmap:** coherente.

## Veredicto

D-66 y la ficha recogen fielmente las decisiones del propietario, y los 12 puntos se cumplen. No hay ningún BLOCKER ni IMPORTANTE. Con la regla del propietario, el pre-registro puede fijarse como `P5_PREREG_SHA` después de corregir los dos MENOR (§27 y el significado de «regiones» en el preflight). Las dos observaciones son opcionales.
