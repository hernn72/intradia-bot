# Cálculo manual de un Delta de bloque

Fuente única: `evidence/2026-09-30-T-019-paso3-p3/run/tablas/swing-bloque-x-quintil.tsv`.
Bloque elegido: 3.

- media Q1: 0.672117
- media Q5: -0.048212
- Delta_bloque = media(Q5) - media(Q1) = -0.048212 - 0.672117 = -0.720330

`paired_block_contrast` calcula por bloque `media(high) - media(low)` solo donde existen ambas medias; su `mean` es la media simple de esos deltas de bloque. La `n` de la TSV no pondera el contraste, solo acompaña al intervalo por bootstrap de bloques.

Comprobación automática: 19 bloques calculables; media simple -0.289467854516; `p3-resultado.json`/`swing-contrastes.tsv` -0.289467854516; diferencia 0.
Media ponderada por Q1_n+Q5_n (no usada por `paired_block_contrast`): -0.274593474181.
