# Revisión cruzada de Codex — borrador de T-020 (2026-10-01)

Revisión en solo lectura del primer borrador de `docs/tareas/T-020-p4-geometria.md`, lanzada con `codex-companion task` sin `--write`. Texto literal de su respuesta; las rutas absolutas se han acortado a rutas del repositorio. Los números de línea se refieren al primer borrador.

Revisión en solo lectura completada. No edité ficheros, no hice commits y no ejecuté `comparacion-pareada`, P3, event studies con desenlaces ni replay de población. Tampoco reproduzco cifras de desenlace.

**BLOCKER**
- No veo un blocker técnico insalvable si esta ficha se trata como borrador condicionado. Pero no debería considerarse pre-registro ejecutable todavía: hay ODs abiertas que pueden cambiar rejilla, población, multiplicidad y criterio.

**IMPORTANTE**
- Criterio llamado “pre-registrado” aunque todavía es modificable por OD-P4-9.  
  Ficha: [T-020-p4-geometria.md](<docs/tareas/T-020-p4-geometria.md:466>) y OD: [T-020-p4-geometria.md](<docs/tareas/T-020-p4-geometria.md:692>).  
  Evidencia: la sección 22 fija condiciones 1-9, pero OD-P4-9 permite elegir “tal cual”, desempatar o relajar heterogeneidad. Eso deja grados de libertad que afectan directamente la conclusión.  
  Corrección: no llamarlo criterio pre-registrado hasta cerrar OD-P4-9; tras cerrar, eliminar alternativas no elegidas o moverlas a historial, y congelar el SHA documental.

- Afirmación demasiado fuerte sobre emparejamiento completo por construcción.  
  Ficha: [T-020-p4-geometria.md](<docs/tareas/T-020-p4-geometria.md:275>). Código: [levels.py](<advisor/analysis/levels.py:132>) y [levels.py](<advisor/analysis/levels.py:167>).  
  Evidencia: `compute_levels_from_inputs` devuelve `None` si `atr <= 0`, `stop <= 0`, `stop >= price` o si no pasa RR en `entry_max`. Con S2, por álgebra, `stop = P - 2,5A`, así que no es imposible que alguna señal válida en C0 no lo sea en S2 si `A/P` es extremo. La propia ficha luego prevé contar señales sin niveles, lo que contradice “completo por construcción”.  
  Corrección: cambiar a “se espera emparejamiento alto; el preflight contará pérdidas de niveles por variante” y mantener la condición 9 como guarda.

- La condición `target1 < target2 < target3` está mal especificada como prueba real de niveles.  
  Ficha: [T-020-p4-geometria.md](<docs/tareas/T-020-p4-geometria.md:478>) y test: [T-020-p4-geometria.md](<docs/tareas/T-020-p4-geometria.md:493>). Código: [config.py](<advisor/config.py:100>) y [levels.py](<advisor/analysis/levels.py:174>).  
  Evidencia: el validador solo asegura que los múltiplos configurados son crecientes. El nivel efectivo de `target1` puede ceder ante resistencia; en estas variantes eso lo baja, así que no rompe el orden, pero el test propuesto no prueba el nivel efectivo, solo la config.  
  Corrección: probar explícitamente niveles efectivos tras resistencia/soporte, no solo `LevelsConfig`.

- OD-P4-5 introduce una secundaria económica con apertura siguiente que puede abrir una puerta de interpretación no contada.  
  Ficha: [T-020-p4-geometria.md](<docs/tareas/T-020-p4-geometria.md:628>) y recuento: [T-020-p4-geometria.md](<docs/tareas/T-020-p4-geometria.md:431>).  
  Evidencia: alternativa B recomienda medir resultado económico condicionado a `open_{t+1} <= entry_max`, pero el recuento de multiplicidad solo se rehace si se elige C. Aunque se rotule descriptiva, es desenlace adicional por geometría y muestra seleccionada por ejecutabilidad.  
  Corrección: si se adopta B, contarla explícitamente como análisis de desenlace descriptivo, prohibir que afecte P5/P6, y publicarla separada de la decisión confirmatoria.

- Coherencia incompleta con el protocolo sobre validación temporal.  
  Ficha: [T-020-p4-geometria.md](<docs/tareas/T-020-p4-geometria.md:345>) y OD-P4-10: [T-020-p4-geometria.md](<docs/tareas/T-020-p4-geometria.md:709>). Protocolo: [protocolo-investigacion.md](<docs/protocolo-investigacion.md:537>).  
  Evidencia: el protocolo dice que P4/P5 comparan ya bajo validación temporal; la ficha reconoce que la cosecha está consumida y lo deja a OD-P4-10. Esto es honesto, pero mientras OD-P4-10 no cierre, el pre-registro no satisface el protocolo.  
  Corrección: cerrar OD-P4-10 antes del SHA; si se elige “solo desarrollo”, declarar una desviación formal del protocolo, no solo una OD.

- Recuento 436 condicionado a ODs, pero presentado como “propuesto” y a la vez usado para el gate.  
  Ficha: [T-020-p4-geometria.md](<docs/tareas/T-020-p4-geometria.md:431>) y [T-020-p4-geometria.md](<docs/tareas/T-020-p4-geometria.md:451>).  
  Evidencia: el total depende de OD-P4-1/4/5/7/10/11. La ficha lo admite, pero GATE P4 exige publicar el número total de comparaciones; si las ODs cambian, el número deja de ser el pre-registro.  
  Corrección: tras cerrar ODs, recalcular y convertir la tabla en definitiva; antes, rotularla como “borrador no vinculante”.

**MENOR**
- La sección de revisión independiente se marca como hecha antes de estar rellena.  
  Ficha: [T-020-p4-geometria.md](<docs/tareas/T-020-p4-geometria.md:766>) y [T-020-p4-geometria.md](<docs/tareas/T-020-p4-geometria.md:785>).  
  Evidencia: dice “Se hizo el 2026-10-01” pero la sección está vacía.  
  Corrección: cambiar a “pendiente” hasta incorporar esta revisión, o rellenar hallazgos y fecha exacta.

- Inventario de coste correcto, pero la fuente está repartida y conviene citar también el default de event study.  
  Ficha: [T-020-p4-geometria.md](<docs/tareas/T-020-p4-geometria.md:103>). Código: [event_study.py](<advisor/research/event_study.py:222>) y [p3.py](<advisor/research/p3.py:66>).  
  Corrección: citar ambos defaults: P3 fija `COST_PCT`; `run_event_study_on_vintage` también tiene `cost_pct=0.2`.

**OBSERVACIÓN**
- Exposición previa: B1 está declarada; no encontré evidencia clara de medición previa de B2/S1/S2 con esos puntos exactos. Sí aparecen antecedentes algebraicos/documentales de 4,875 y stop 1,5 como discusión, no como medición confirmatoria.  
  Ficha: [T-020-p4-geometria.md](<docs/tareas/T-020-p4-geometria.md:234>). Referencias previas: [protocolo-investigacion.md](<docs/protocolo-investigacion.md:83>) y [ratio-beneficio-riesgo.md](<docs/ratio-beneficio-riesgo.md:112>).  
  Corrección: precisar “B2/S1/S2 no se han medido como variantes pareadas de P4; sí existen antecedentes algebraicos o cualitativos”.

- La fidelidad del inventario de sección 5 al código es mayormente correcta: soporte E, `target2_structural=false`, entrada de event study al cierre, `AMBIGUOUS` sin `net_R`, `open_{t+1}` en ejecución y defaults coinciden con el código revisado. La parte débil no es el inventario, sino las inferencias posteriores sobre completitud y criterio.

