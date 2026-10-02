# Revisión adversarial independiente de la ficha T-021 (primera vuelta)

Agente `revisor` (Claude, distinto del autor), en solo lectura, sobre el commit `3e597db` (rama
`docs/a05-p5-preregistro`, base `4eed281`). Mandato: intentar demostrar que el diseño permite
escoger a posteriori el resultado deseado. No evaluó ningún desenlace. Informe transcrito
literalmente.

---

RESULTADO: REQUIERE CAMBIOS

Revisión adversarial en solo lectura de `docs/tareas/T-021-p5-regiones-robustas.md` (rama docs/a05-p5-preregistro, commit 3e597db, base 4eed281). No he modificado nada ni evaluado ningún desenlace: solo he leído código, documentos y evidencia congelada, he hecho álgebra y he ejecutado dos scripts con primitivas (el universo y el JSON del inventario).

Veredicto: hay 1 BLOCKER, que deja decidida de antemano la salida `[]`; 1 IMPORTANTE, sobre la tolerancia de S2 mal descrita; 5 MENOR y 2 OBSERVACIÓN. Fuera de esto, el diseño es sólido. No he encontrado ninguna forma de escoger el resultado después de medir. La rejilla sale solo de la geometría de P4. Ningún vecino es elegible. La multiplicidad está fijada. Las condiciones del centro que ya se conocen están marcadas como «conocida» y no se presentan como evidencia nueva.

---

**[BLOCKER] El LOCRO no puede ser estimable nunca: la salida `[]` queda decidida por el texto**

- **Dónde:** §15, línea 461 («pares ≥ 90 % de 101.251»); §19.2, líneas 542-545 (el LOCRO es estimable si cumple «las condiciones de capacidad de la sección 15»); §26, etiqueta 3 (líneas 719-720); §25.
- **Fallo:** en cualquier ejecución, las tres poblaciones LOCRO tienen menos pares que el 90 % de 101.251 (91.126):
  - sin USA: 101.251 − 44.898 = 56.353 señales (55,7 %);
  - sin EUROPA: 66.629 (65,8 %);
  - sin ASIA: 83.298 (82,3 %).
- **Resultado:** las tres son NO_ESTIMABLES, así que B2 y S2 salen siempre NO_CONCLUYENTE (o FRÁGIL), nunca ROBUSTA. La salida es `[]` sea cual sea el dato.
- **Causa:** la condición 9 de P4 se trasladó a la capacidad de celda con un denominador absoluto. En el código está fijado igual: `MIN_PAIR_FRACTION = 0.90` contra `EXPECTED_P4 = 101_251` (`advisor/research/p4.py:106,123,1535`). En P4 esa condición solo se aplicaba a la población completa, no a estratos (T-020 §22, condiciones 3 y 9).
- **Cómo se cierra:**
  - En §19.2, definir la capacidad del LOCRO con la fracción de pares sobre la población sin la región r. Pre-registrar los tres denominadores (56.353 / 66.629 / 83.298), o quitar la condición de pares del LOCRO y conservar las demás.
  - Llevarlo a OD-P5-8 como alternativa explícita.
  - Añadir al test 6 de §34 un caso que falle con el denominador absoluto.

**[IMPORTANTE] La tolerancia de S2 está mal descrita y falta la característica operativa por candidata**

- **Dónde:** §11.6, líneas 374-375 («B2 admite 2 fallos de 8 (25 %); S2, 1 de 5 (20 %)»); §23.2, línea 630; OD-P5-4 y OD-P5-5 (líneas 941-958).
- **El hecho:** en S2, los semiplanos `s+` y `m2−` tienen un solo vecino cada uno, (2,75; 4,125) y (2,25; 3,375). Por F2/F3, si cualquiera de esos dos no es ACEPTABLE, S2 es FRÁGIL. Su tolerancia real es: los dos tienen que ser ACEPTABLES, y de los otros tres puede fallar como mucho uno.
- **Comparación con B2:** B2 sí tolera dos DÉBIL en cualquier sitio. Con tres vecinos por semiplano, dos fallos no pueden vaciar ninguno; CONTRARIA veta en las dos candidatas por F1.
- **Cifras, con los mismos supuestos de §23.4** (independencia; p = 0,79 en B2 y 0,92 en S2):
  - B2: P(≥ 6 de 8) ≈ 0,78;
  - S2: ≈ 0,92⁵ + 3·0,92⁴·0,08 ≈ 0,83, no el ≈ 0,95 que implicaría «1 de 5 cualquiera».
- **Por qué importa:** la frase de §11.6 es la que el propietario usa para cerrar OD-P5-5 («tolerancia parecida»), y no describe la regla escrita.
- **Cómo se cierra:** corregir §11.6 y §23.2 con la tolerancia efectiva, y añadir en §23.4 y en las consecuencias de OD-P5-4/5 la probabilidad aproximada de ROBUSTA por candidata, no solo por celda.

**[MENOR] La alternativa B de OD-P5-2 (escala de P4) omite que hace FRÁGIL a S2 por construcción, y cuenta mal los pasos**

- **Dónde:** §11.2, líneas 309-311; OD-P5-2 B, líneas 910-911.
- **Qué omite:** con Δs = 0,5, el vecino iso-RR inferior de S2 es C0, con ΔR ≡ 0. Según §15 eso es CONTRARIA, y por F1 S2 sale FRÁGIL automáticamente. La ficha solo dice «no informa de nada»; la consecuencia real es un veredicto fijado de antemano, salvo una regla adicional que excluya C0.
- **Qué está mal contado:** «(3,0; 4,5) queda a dos pasos de P4 de S2» es falso. Está a un paso (0,5); a dos pasos está de C0.
- **Cómo se cierra:** escribir esa consecuencia en OD-P5-2 B y corregir la cuenta de pasos.

**[MENOR] Varias OD no cumplen el formato exigido y falta alguna OD**

- **Dónde:** OD-P5-9 (línea 1002), OD-P5-13 (línea 1045) y OD-P5-6 (línea 967).
- **Formato:** el formato exige la consecuencia de cada alternativa.
  - OD-P5-9 y OD-P5-13 no dan la consecuencia de la alternativa A, que es la recomendada.
  - OD-P5-6 la da solo por remisión a §22.
- **Umbrales sin alternativas:** OD-P5-4 ofrece alternativas para la definición de ACEPTABLE, pero no para los números de la meseta (0,75, |NE| ≤ 1, «≥ 1 ACEPTABLE por semiplano»). §23.2 discute 0,5 y 1,0, pero el propietario no puede elegirlos.
- **OD que falta:** no hay ninguna OD sobre la capacidad del LOCRO (ver el BLOCKER).
- **Cómo se cierra:** completar las consecuencias, añadir alternativas numéricas en OD-P5-4 y abrir una OD (o una alternativa en OD-P5-8) para la capacidad del LOCRO.

**[MENOR] El preflight da acceso a los desenlaces por señal de B2 y S2 antes de la marca de ejecución**

- **Dónde:** OD-P5-16 (líneas 1074-1087) y test 7 (línea 1114).
- **Fallo:** el test 7 solo restringe geometrías. Con los desenlaces de C0, B2 y S2 en memoria durante el preflight, el LOCRO de los centros (una estimación nueva y decisoria) puede calcularse antes de la marca.
- **Cómo se cierra:** exigir que el preflight no calcule ninguna estimación sobre subpoblaciones (LOCRO ni estratos), y que la ruta del LOCRO se niegue a ejecutarse sin la marca, con un test.

**[MENOR] La cifra del stop movido no coincide entre OD-P5-2 y §11.2**

- **Dónde:** OD-P5-2 A, línea 908 («80–86 %»), frente a §11.2, línea 307 («78–86 %»).
- **Dato:** el mínimo es 78.601 / 101.251 = 77,6 %.
- **Cómo se cierra:** unificar en 78–86 %.

**[MENOR] Pequeñas imprecisiones de texto**

- **§5.3, líneas 110-111:** C0 queda a «un paso de stop a la izquierda» de (2,25; 3,375). En realidad es un paso diagonal (Δs = 0,25 y Δm2 = 0,375), no un paso solo de stop.
- **§10.2, líneas 228-229, y §10.3, línea 247:** las celdas con `m2 < 1,5·s` violan la condición 6 «en las señales de stop por volatilidad». El JSON muestra más incoherencias que señales de volatilidad: 81.381 frente a 78.601 en (2,5; 3,375), 81.381 frente a 75.833 en (2,75; 3,375) y 78.601 frente a 75.833 en (2,75; 3,75). También fallan señales con stop por soporte poco ajustado.
- **Cómo se cierra:** corregir las dos frases.

**[OBSERVACIÓN] La «neutralidad a la distancia» de §23.3 es un supuesto sin verificar en la recta iso-RR**

- **Dónde:** §23.3, líneas 644-647.
- **Lo que hay:** en el eje del objetivo, B1 y B2 de P4 la apoyan. El cociente efecto/error es ≈ 2,56 en B1 (IC95 [0,0047; 0,0363]) y ≈ 2,77 en B2, y el error crece casi linealmente con la distancia.
- **Lo que no hay:** ningún dato en el eje iso-RR a distancia 0,25. Ahí el mecanismo es sobre todo de cambios discretos stop/objetivo, en los que el error podría crecer como √d. Si fuera así, la celda (2,25; 3,375), que decide sola el semiplano `m2−` de S2, tendría menos potencia.
- **Cómo se cierra:** rebajar «aproximadamente neutral» a supuesto declarado y citar la evidencia de B1/B2 como apoyo parcial.

**[OBSERVACIÓN] Las etiquetas de salida del envoltorio no coinciden con el código**

- **Dónde:** §28, línea 777.
- **Fallo:** `"salidas": ["STOP","TARGET2","TIME_EXIT","FINAL_EXIT"]` no son las constantes del código (`STOP_FIRST`, `TARGET_FIRST`, `TIME`, `FINAL`, en `advisor/research/event_study.py:38-42`). Como entran en el `policy_sha256`, conviene fijar si son literales libres o las del código.

---

**Comprobado y correcto**

- **Inventario:** las 18 filas de la tabla de §10.3 coinciden con `inventario-estructural.json`: soporte, stop = centro, stop y objetivo 2 = centro, stop = C0, qué manda, RR mínimo e incoherencias. El sha256 del JSON es `c4959801…0e2`. La población (101.251) y el hash `78024050…` se reproducen.
- **Fracciones degeneradas:** 14,2 / 16,9 / 19,6 %. El stop movido va de 78.601 a 86.860 señales. ATR/P máximo 0,2654, y 1/0,2654 = 3,77.
- **Álgebra:** RR = m2/s; holgura = (m2 − 1,5s)/2,5, igual que `entry_max_for_rr` en `levels.py:53-60`. Umbral técnico m2 = 1,5s + 1,875. B2 = 2,4375 / 0,75 (empate); S2 = 1,5 / 0. Las dos diagonales son las rectas de saturación y de iso-RR. La tolerancia `isclose` hace válidas las celdas iso-RR (`p4.py:323-338`).
- **target3:** es cierto que no interviene en ningún desenlace.
  - `evaluate_managed_event` solo usa stop y `target2`, incluida la ambigüedad (`event_study.py:542-610`).
  - `evaluate_potential_event` solo usa el stop.
  - `classify_open_entry` usa `target2` (`p4.py:352-369`).
  - `target3` solo aparece en la coherencia (`p4.py:332`), en el informe, en los textos y en la tupla `targets` (`execution.py:93`).
  - El validador estricto está en `config.py:100-110`.
- **Recuento:** 5·8 + 3 + 5·5 + 3 = 71; con OD-P5-3 = A, 56. El desglose suma 13 + 6 + 13 + 26 + 13 = 71, y con P4 el acumulado es 447 + 71 = 518. Configuraciones únicas: 16 (13 con A). La alternativa B de OD-P5-1 tiene 30 celdas, 3 inválidas y 25 vecinos; la C de OD-P5-2 añade 9 vecinos (+45).
- **§23.4:** errores típicos 0,0259 / 0,0104; cocientes 2,77 / 3,34; ΔR mínimo 0,051 (71 %) / 0,020 (59 %); Φ ≈ 0,79 / 0,92.
- **Cifras de P4:** todas las de D-64 coinciden. Los estratos de región de B2 y S2 tienen el IC95 entero por encima de 0 en ASIA, EUROPA y USA, y hay 75/90 y 73/90 activos con ΔR positivo (`estratos-congelados.md`).
- **§19.1:** 90 activos (USA 40, EUROPA 30, ASIA 16, GLOBAL 3, EM 1). En ASIA, 5 cotizan en XETRA y 2 en NYSE; en USA, 3 en XETRA. Señales por región: suman 101.251, y GLOBAL más EM son el 3,7 %.
- **Hash:** `EXPECTED_CONFIG_HASH = 89406d28…` (`p4.py:101`); `config_hash` (`manifest.py:80`) y `canonical_hash` (`vintage.py:12`) están descritos correctamente.
- **Bloques y semilla:** 20 bloques (2-21), el más corto de 42; 120 válido; mitades 2-11 y 12-21, igual que en P4.
- **Lo que no admite elección posterior:**
  - salida limitada a ⊆ {B2, S2};
  - prohibición de mover celdas, umbrales o regiones;
  - sin particiones temporales nuevas;
  - activos y heterogeneidad sin veto, con la exposición declarada;
  - P5 declarado como desarrollo, no validación;
  - sin adelantar P6.
- **Cobertura:** la ficha cubre los 38 puntos pedidos por el propietario, y cada OD tiene pregunta, alternativas, recomendación y qué bloquea, salvo las carencias de formato señaladas arriba.

**Limitaciones de la revisión:** no he ejecutado pytest. No he comprobado si `p4-resultado.json` contiene datos por señal; por su estructura, parece que no permite reconstruir el LOCRO.
