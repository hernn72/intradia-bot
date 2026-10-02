# Revisión adversarial independiente de la ficha T-021 (segunda vuelta)

Mismo agente `revisor`, en solo lectura y sin desenlaces, sobre el commit `c53f882`. Informe
transcrito literalmente. Sus hallazgos se corrigieron en el commit siguiente.

---

RESULTADO: REQUIERE CAMBIOS (solo cambios MENOR: 0 BLOCKER, 0 IMPORTANTE)

Segunda vuelta sobre c53f882, en solo lectura, sin desenlaces y sin commits. He leído el diff 3e597db..c53f882, la ficha nueva y `codex-revision-ficha.md`, y los he contrastado con el código (`uncertainty.py:75-124`, `p4.py:1031-1099` y `2128-2133`, `bootstrap.py:105-160`) y con los TSV congelados de P4. Los nueve hallazgos de la primera vuelta quedan cerrados y no hay ningún BLOCKER ni IMPORTANTE nuevo. Quedan 1 MENOR y 3 OBSERVACIÓN, que se cierran con cambios de texto. Con la regla del propietario (0 BLOCKER y 0 IMPORTANTE), la ficha puede ir a cierre de OD.

Las líneas son de la ficha en c53f882.

## Estado de los hallazgos de la primera vuelta

| Hallazgo | Estado | Dónde |
|---|---|---|
| B-1, LOCRO nunca estimable | **CERRADO** | §15 l.471-472; §19.2 l.563-578 (umbrales y contrato operativo); OD-P5-8 l.1056-1063 (i/ii/iii, con la consecuencia de ii); test 6 l.1204-1208 (caso que falla con el denominador absoluto) |
| I-1, tolerancia de S2 y probabilidad por candidata | **CERRADO** | §11.6 l.378-386; §23.2 l.664-665; §23.4 l.700-705; OD-P5-4 l.997-998; OD-P5-5 l.1018-1021 |
| MENOR, OD-P5-2 B (FRÁGIL por construcción; cuenta de pasos) | **CERRADO** | §11.2 l.312-315; OD-P5-2 l.959-962 |
| MENOR, formato de las OD y OD que faltaba | **CERRADO** | OD-P5-6 l.1030-1033; OD-P5-9 l.1074-1076; OD-P5-13 l.1118-1120; umbrales de la meseta en OD-P5-4 l.991-994 y 1007-1012; capacidad del LOCRO en OD-P5-8 |
| MENOR, preflight con desenlaces por señal | **CERRADO** (queda una observación, abajo) | OD-P5-16 l.1166-1181; test 7 l.1209-1211 |
| MENOR, 80–86 % → 78–86 % | **CERRADO** | l.956 |
| MENOR, imprecisiones de texto | **CERRADO** | §5.3 l.110-111 (paso diagonal); §10.2 l.228-231 y §10.3 l.248-249 (incoherencias también en señales de soporte) |
| OBS, neutralidad a la distancia | **CERRADO** | §23.3 l.680-686 (supuesto declarado, con el apoyo de B1/B2) |
| OBS, etiquetas de salida | **CERRADO** | §28 l.821 y 833-834 (constantes de `event_study.py:38-42`) |

## Comprobaciones pedidas

- **Umbrales del LOCRO:** son correctos.
  - ⌈0,9 × 56.353⌉ = ⌈50.717,7⌉ = 50.718;
  - ⌈0,9 × 66.629⌉ = 59.967;
  - ⌈0,9 × 83.298⌉ = 74.969;
  - en las celdas, ⌈0,9 × 101.251⌉ = 91.126, que coincide con `pair_fraction ≥ 0,90` de P4.
- **Probabilidades por candidata:** son correctas.
  - B2: P(Bin(8; 0,79) ≥ 6) = 0,7745 ≈ 0,77.
  - S2: 0,92⁵ + 3·0,92⁴·0,08 = 0,831 ≈ 0,83. Con los p sin redondear (0,7898 y 0,9157) salen 0,774 y 0,822; la diferencia es despreciable.
  - Anchura 1,0: 0,79⁸ = 0,152 ≈ 0,15 y 0,92⁵ = 0,659 ≈ 0,66.
- **OD-P5-16 no permite calcular nada nuevo de valor decisorio.** Las filas que nombra existen y están publicadas para B2 y S2:
  - en `estimaciones.tsv`: `primaria_60` (0,9875, 20.000), `bloque_120`, `cota_conservadora`, `cota_favorable` y `mitades`;
  - más `nivel.tsv`, `capacidad.tsv` y `emparejamiento.tsv`.
  - La ficha prohíbe LOCRO, estratos y subpoblaciones, y exige la marca para la ruta del LOCRO.
  - El único residuo está en la Observación N-2.
- **Los cambios de Codex no introducen decisiones ocultas.** Cada cambio coincide con lo que ya hace el código de P4:
  - ΔR y CONTRARIA sobre los pares finales de `pair_populations`, que excluye los `net_R` nulos de cualquiera de los dos brazos;
  - nivel y PF sobre todos los eventos observables (`level_estimate`; `nivel.tsv` de S2 tiene n = 101.246, no los pares);
  - cota sobre toda la variante (`ambiguity_bound_deltas`; n = 101.251 en el TSV);
  - LOCRO con los dos brazos filtrados, porque `pair_populations` exige los mismos `signal_id`, y con la espina completa (`session_spine`), donde `n_blocks` cuenta solo los bloques con pares;
  - igualdad de cadenas con `_cell` a 6 decimales, que es el formato de los TSV;
  - función canónica propia con `allow_nan=False`;
  - C0 por identidad: es el test 3 de T-020, «Réplica de C0 idéntica».
- **Coherencia entre §15, 19.2, 23, 24, 26, 29 y 33:**
  - la capacidad de §15 remite a §19.2, que fija los umbrales relativos;
  - §23.1 (1), §17 y §18 hablan de reproducción de filas;
  - F1-F6 y la precedencia de §26 (FRÁGIL > DEPENDIENTE > NO_CONCLUYENTE) no cambian;
  - §29 no cambia (71 / 56; los denominadores no alteran el recuento);
  - OD-P5-4, 5 y 8 son coherentes con §11.6, §19.2 y §23.4.
  - Las únicas fricciones son de redacción y están abajo.

## Hallazgos nuevos

**[MENOR] OD-P5-16 cuenta como dos filas lo que en P4 es una sola**

- **Dónde:** OD-P5-16 l.1157-1158 («primaria 60, Bonferroni, 120…»), test 8 l.1212-1214 y §29 l.864.
- **El hecho:** en `estimaciones.tsv` de P4, la fila `primaria_60` de B2 y S2 **es** la de Bonferroni (`ic_nivel` 0,987500, 20.000 remuestreos). No existe una fila Bonferroni aparte ni una primaria al 95 %.
- **Riesgo:** un ejecutor que busque «primaria 60» y «Bonferroni» como claves distintas no encontrará la segunda, o comparará un IC95 con el de 98,75 %. El resultado sería un STOP falso del preflight o una comparación mal definida.
- **Cómo se cierra:** escribir las claves exactas que se comparan:
  - `(X, primaria_60, "")` con el IC de 0,9875;
  - `(X, bloque_120, "")`;
  - `(X, cota_conservadora, "")` y `(X, cota_favorable, "")`;
  - `(X, mitades, bloques_2_11)` y `(X, mitades, bloques_12_21)`;
  - y las columnas que se comparan en cada una.

**[OBSERVACIÓN N-1] «Se reproduce exactamente» en §26 frente a la igualdad de cadenas de OD-P5-16**

- **Dónde:** §26, condición 1, l.745.
- **Qué pasa:** dice «se reproduce exactamente». OD-P5-16 define la reproducción como igualdad de cadenas `_cell` a 6 decimales, y para C0 como identidad.
- **Cómo se cierra:** cambiarlo por «reproduce sus filas de P4 según OD-P5-16».

**[OBSERVACIÓN N-2] La anchura del IC95 de los centros da un dato que P4 no publicó, sin valor decisorio**

- **Qué pasa:** para reproducir `capacidad.tsv` (`anchura_ic95` = 0,101970 en B2 y 0,040415 en S2) hay que calcular el IC95 de 2.000 remuestreos de la primaria de B2 y S2. P4 solo publicó su anchura, no sus extremos.
- **Por qué no es decisorio:** ninguna condición de P5 usa ese IC en los centros, que se rigen por el de Bonferroni.
- **Cómo se cierra:** basta añadir a OD-P5-16 que de ese IC solo se compara y archiva la anchura.
- **Relacionado:** conviene que §30 diga también que la evidencia del preflight **no archiva desenlaces por señal** de B2 y S2. Así nadie, ni siquiera fuera del código, podrá calcular el LOCRO antes de la marca.

**[OBSERVACIÓN N-3] OD-P5-8 no recoge la sub-elección de capacidad en la recomendación**

- **Dónde:** OD-P5-8, l.1066-1067.
- **Qué pasa:** la recomendación dice solo «**A.**»; la sub-elección «i (recomendada)» está únicamente en las alternativas. Además, «En las tres…» es ambiguo ahora que hay A/B/C e i/ii/iii.
- **Cómo se cierra:** escribir «Recomendación: A con capacidad i» y «en A, B y C».

## Veredicto

B-1 e I-1 quedan cerrados, igual que los cinco MENOR y las dos OBSERVACIÓN. Los cambios de Codex no introducen decisiones ocultas: todos reproducen el comportamiento del código de P4. No he encontrado ninguna vía nueva para escoger el resultado después de medir ni para fijarlo de antemano. Lo que queda es un MENOR de redacción en OD-P5-16 y tres observaciones; recomiendo corregirlos antes de fijar el `P5_PREREG_SHA`, pero no bloquean el cierre de las OD.

**Limitaciones:** no he ejecutado pytest ni ningún código de desenlaces. Las probabilidades se han recalculado con Python estándar a partir de los IC publicados.
