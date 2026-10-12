Eres revisor en SOLO LECTURA del repo intradia-bot, rama docs/a05-p5-preregistro, commit 3e597db. NO modifiques ningún fichero. NO ejecutes nada que lea desenlaces (evaluate_managed_event, evaluate_potential_event, classify_target_stop_bar, net_R) ni P4 ni comparacion-pareada.

Revisa docs/tareas/T-021-p5-regiones-robustas.md (borrador de pre-registro de P5) contra el código (advisor/research/p4.py, advisor/analysis/levels.py, advisor/config.py, advisor/run/manifest.py, advisor/universe/vintage.py, advisor/research/capacity.py, advisor/research/bootstrap.py, advisor/research/uncertainty.py) y contra T-020, D-63..D-65 y docs/gates.md. Ya revisaste el diseño previo (evidence/2026-10-02-T-021-p5-diseno/codex-revision-diseno.md): comprueba si la ficha cierra de verdad tus hallazgos anteriores.

Comprueba especialmente que todo lo que la ficha propone sea IMPLEMENTABLE con la infraestructura existente sin decisiones ocultas:
1) LOCRO con el mapa de bloques de la población completa: ¿bootstrap_block_delta / pair_populations admiten una subpoblación sin cambiar la espina? ¿Qué pasa con bloques sin pares?
2) Las cotas de ambigüedad, el nivel con IC y la sensibilidad de 120 por celda: ¿existen funciones en p4.py que lo den tal cual (ambiguity_bound_deltas, level_estimate, block_estimate)?
3) Hash: ¿config_hash de un AdvisorConfig con levels sustituido es reproducible (model_dump mode json, floats)? ¿Coincide la convención con canonical_hash? ¿Hay algún campo de AdvisorConfig que no sea determinista?
4) La reproducción en preflight de C0/B2/S2 contra evidence/2026-10-01-T-020-p4/run/tablas/*.tsv: ¿qué columnas y precisión tiene el TSV? ¿Es factible la «igualdad exacta a la precisión del TSV»? ¿El Bonferroni de 20.000 remuestreos es determinista con la semilla?
5) ¿La regla «ACEPTABLE requiere nivel > 0 y PF > 1» y «CONTRARIA si ΔR ≤ 0» está bien definida cuando una celda tiene pares descartados por ambigüedad distintos de los del centro?
6) Cualquier ambigüedad que obligue a quien implemente a decidir metodología.
Clasifica BLOCKER / IMPORTANTE / MENOR / OBSERVACIÓN, cita fichero:línea y propone el cambio concreto. Español, conciso.
