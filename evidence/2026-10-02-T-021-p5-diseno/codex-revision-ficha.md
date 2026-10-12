**BLOCKER**

- `docs/tareas/T-021-p5-regiones-robustas.md:1076-1079` exige reproducir “C0/B2/S2” contra `run/tablas/*.tsv`, incluyendo punto, Bonferroni, 120, cotas, mitades, nivel y PF. Pero P4 no publica C0 como salida comparable: `p4-resultado.json` tiene C0 en preflight/niveles/hash (`evidence/.../p4-resultado.json:114`, `:336`, `:428`), mientras `salidas` empieza en B1 (`:435`) y los TSV de `nivel.tsv`/`estimaciones.tsv` son solo variantes.  
  **Cambio:** separar “C0 reproduce niveles/hash/identidad de control” de “B2/S2 reproducen salidas P4”; o indicar explícitamente una fuente JSON y campos exactos para C0.

**IMPORTANTE**

- LOCRO es implementable, pero la ficha deja una decisión oculta: `pair_populations` solo acepta mapas con los mismos `signal_id` (`advisor/research/uncertainty.py:75-87`), así que hay que filtrar C0 y X a la misma subpoblación “sin región r” antes de emparejar. `bootstrap_block_delta` acepta `session_spine` completa (`advisor/research/bootstrap.py:105-126`), pero `n_blocks` cuenta solo bloques con pares (`:131-154`). La ficha dice “mapa de bloques completo” y “bloques sin pares salen de n_blocks” (`docs/...T-021...md:486`), compatible, pero insuficientemente operativo.  
  **Cambio:** añadir pseudocontrato: `subset_ids = señales con region != r`, `subset_control = control[id]`, `subset_variant = variant[id]`, `spine = population.spine`; publicar bloques ocupados sin pares contra los bloques de la población completa.

- `docs/...T-021...md:469-471` mezcla criterios de ACEPTABLE/CONTRARIA sin fijar claramente la población de cada métrica cuando hay descartes ambiguos distintos. En código, ΔR usa pares no ambiguos de ambos brazos (`pair_populations`, `advisor/research/uncertainty.py:95-124`), pero `level_estimate`/PF usan todos los `net_R` observables de la celda, no el subconjunto pareado (`advisor/research/p4.py:1070-1099`, `:1328`).  
  **Cambio:** declarar: “CONTRARIA se evalúa con `primaria_60.media_delta_r` sobre pares finales; nivel/PF se calculan sobre todos los eventos observables de la celda, excluyendo solo `net_R is None`”.

- La igualdad “a la precisión del TSV” es factible pero debe quedar definida como comparación a 6 decimales: `_cell` redondea todos los `float` con `"{value:.6f}"` (`advisor/research/p4.py:2128-2133`). Los TSV tienen cabeceras/comentarios y columnas distintas por tabla (`estimaciones.tsv` 16 columnas, `nivel.tsv` 7, etc.).  
  **Cambio:** especificar parser: ignorar líneas `#`, comparar columnas concretas por clave `(comparacion, estimacion, estrato)` y valores formateados con la misma `_cell`, no floats crudos.

**MENOR**

- Hash: la propuesta es mayormente reproducible. `config_hash` usa `model_dump(mode="json")`, elimina rutas y llama a `canonical_hash` (`advisor/run/manifest.py:80-91`); `canonical_hash` usa `sort_keys=True` y separadores canónicos (`advisor/universe/vintage.py:12-14`). La ficha añade `allow_nan=False` para el envoltorio (`docs/...T-021...md:783-785`), pero eso no coincide literalmente con `canonical_hash`, que usa `default=str` y no fija `allow_nan`.  
  **Cambio:** decir “misma ordenación/separadores que `canonical_hash`, no la misma función”, o crear una función canónica P5 con `allow_nan=False`.

**OBSERVACIÓN**

- Los hallazgos anteriores de diseño están sustancialmente cerrados: escala 0,25 redefinida como sensibilidad local (`docs/...:297-317`), IC95>0 rotulado como señal clara (`:635-650`), asimetría S2 declarada (`:370-375`), `m3` auxiliar marcado (`:397-406`), degeneración por soporte publicada (`:271-275`) y LOCRO renombrado (`:533-538`).  
- `ambiguity_bound_deltas`, `level_estimate` y `block_estimate` existen y dan la materia prima requerida (`advisor/research/p4.py:966-983`, `:1031-1047`, `:1070-1099`). Bonferroni con 20.000 es determinista por semilla derivada (`advisor/research/p4.py:81-86`, `advisor/research/bootstrap.py:157-160`).

Codex session ID: 01a0fc1d-5db0-79f2-8b74-492ff5097196
Resume in Codex: codex resume 01a0fc1d-5db0-79f2-8b74-492ff5097196
