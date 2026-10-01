# Impacto v1 PIT -> v2

- condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido).
- Todas las escalas usan contexto `point_in_time`; no se usa contexto legacy.
- Desenlaces parcheados a `None`; población con `build_population(..., with_outcomes=False)`.
- Un valor de una escala no equivale a la misma cifra de otra escala.
- Los desplazamientos son del score, no rendimiento; no atribuyen mejora de expectancy a ninguna dimensión.

## swing

n=94094; population_sha256=`4aa12d85eb54d7a01c10a4a3e4cf04e8077c842829235a93b75f7bd19c62011a`.

### Distribución

| escala | p1 | p5 | p10 | p25 | p50 | p75 | p90 | p95 | p99 | media | distintos |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v1 PIT: catalizador + técnico + RR + contexto + convicción; fundamental ausente; sobre 80 | 31.5 | 37.2 | 40.9 | 46.6 | 52.9 | 59.8 | 64.4 | 67.2 | 72.9 | 52.85 | 961 |
| v1 PIT sin RR; sobre 60 | 22.0 | 29.7 | 33.0 | 43.0 | 53.0 | 63.0 | 69.2 | 73.0 | 80.5 | 52.37 | 940 |
| v1 PIT sin convicción; sobre 70 | 22.6 | 28.3 | 32.6 | 39.7 | 46.9 | 54.0 | 59.7 | 62.6 | 69.7 | 46.38 | 839 |
| v2 PIT: catalizador + técnico + contexto; sobre 50 | 6.4 | 16.4 | 20.0 | 32.0 | 43.6 | 55.6 | 63.6 | 67.6 | 77.6 | 43.22 | 817 |

Histograma en `tablas/swing-histograma-5.tsv`.

### Desplazamientos

| comparación | media | mediana | p5 | p25 | p75 | p95 | min | max | % sube | % baja | % igual |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B - A | -0.48 | +0.75 | -15.00 | -2.00 | +3.25 | +5.75 | -21.04 | +12.50 | 56.79 | 42.64 | 0.56 |
| C - A | -6.47 | -6.46 | -8.62 | -7.36 | -5.57 | -4.41 | -10.50 | -1.20 | 0.00 | 100.00 | 0.00 |
| D - A | -9.63 | -8.50 | -27.15 | -13.15 | -4.12 | +0.50 | -36.88 | +12.50 | 5.95 | 94.03 | 0.02 |

### n por quintil

| escala | cortes p20/p40/p60/p80 | Q1 | Q2 | Q3 | Q4 | Q5 |
|---|---|---|---|---|---|---|
| v1 PIT: catalizador + técnico + RR + contexto + convicción; fundamental ausente; sobre 80 | 45.2 / 50.4 / 56.0 / 61.0 | 18681 | 18496 | 19244 | 17922 | 19751 |
| v1 PIT sin RR; sobre 60 | 40.0 / 48.8 / 57.2 / 64.7 | 18814 | 17762 | 19301 | 18825 | 19392 |
| v1 PIT sin convicción; sobre 70 | 37.6 / 43.7 / 49.7 / 55.4 | 18503 | 19109 | 17526 | 18098 | 20858 |
| v2 PIT: catalizador + técnico + contexto; sobre 50 | 28.0 / 39.6 / 49.6 / 57.6 | 18292 | 18740 | 19405 | 17205 | 20452 |

### migración entre tramos de escala; no son bandas operativas equivalentes

| A \ D | [0,10) | [10,20) | [20,30) | [30,40) | [40,50) | [50,60) | [60,70) | [70,80) | [80,90) | [90,100] | total |
|---|---|---|---|---|---|---|---|---|---|---|---|
| [20,30) | 475 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 476 |
| [30,40) | 771 | 4047 | 2685 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 7503 |
| [40,50) | 675 | 3207 | 7166 | 16804 | 490 | 0 | 0 | 0 | 0 | 0 | 28342 |
| [50,60) | 0 | 0 | 1832 | 1325 | 19293 | 12968 | 0 | 0 | 0 | 0 | 35418 |
| [60,70) | 0 | 0 | 0 | 156 | 214 | 8031 | 10609 | 919 | 0 | 0 | 19929 |
| [70,80) | 0 | 0 | 0 | 0 | 0 | 16 | 8 | 1814 | 509 | 0 | 2347 |
| [80,90) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 32 | 47 | 79 |

### Región

| región | n | mediana D-A | p25 | p75 |
|---|---|---|---|---|
| ASIA | 16719 | -8.6 | -13.8 | -4.0 |
| EMERGING_MARKETS | 1068 | -6.9 | -11.7 | -2.4 |
| EUROPA | 32118 | -8.5 | -13.0 | -4.1 |
| GLOBAL | 2459 | -6.2 | -10.9 | -2.6 |
| USA | 41730 | -8.6 | -13.3 | -4.1 |

### Activo

90 activos; mediana D-A por activo: mín -12.0, p25 -9.4, mediana -8.3, p75 -7.0, máx -4.9.
Tabla completa: `tablas/swing-activos-D-menos-A.tsv`.

## medio: NO CONCLUYENTE — inválido (bloque parcial 102 ≤ 250)

n=89333; population_sha256=`4d6eaab9b84ff23bade1df86a82e95f46da546917a226dc8438a8e88493020f8`.

### Distribución

| escala | p1 | p5 | p10 | p25 | p50 | p75 | p90 | p95 | p99 | media | distintos |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v1 PIT: catalizador + técnico + RR + contexto + convicción; fundamental ausente; sobre 80 | 32.2 | 37.8 | 41.6 | 47.2 | 53.5 | 59.8 | 64.8 | 67.2 | 73.1 | 53.31 | 794 |
| v1 PIT sin RR; sobre 60 | 22.8 | 30.5 | 33.8 | 44.2 | 53.8 | 63.0 | 69.7 | 73.0 | 80.8 | 53.02 | 774 |
| v1 PIT sin convicción; sobre 70 | 23.1 | 29.0 | 33.6 | 39.7 | 47.1 | 54.3 | 59.7 | 62.9 | 69.7 | 46.90 | 750 |
| v2 PIT: catalizador + técnico + contexto; sobre 50 | 8.4 | 17.0 | 21.6 | 33.6 | 45.0 | 55.6 | 63.6 | 67.6 | 77.6 | 43.98 | 730 |

Histograma en `tablas/medio-histograma-5.tsv`.

### Desplazamientos

| comparación | media | mediana | p5 | p25 | p75 | p95 | min | max | % sube | % baja | % igual |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B - A | -0.29 | +0.96 | -14.67 | -1.75 | +3.25 | +5.75 | -21.04 | +12.50 | 58.66 | 40.75 | 0.59 |
| C - A | -6.41 | -6.38 | -8.57 | -7.32 | -5.54 | -4.38 | -10.41 | -1.20 | 0.00 | 100.00 | 0.00 |
| D - A | -9.32 | -7.90 | -26.73 | -12.52 | -3.90 | +0.50 | -36.88 | +12.50 | 6.20 | 93.78 | 0.02 |

### n por quintil

| escala | cortes p20/p40/p60/p80 | Q1 | Q2 | Q3 | Q4 | Q5 |
|---|---|---|---|---|---|---|
| v1 PIT: catalizador + técnico + RR + contexto + convicción; fundamental ausente; sobre 80 | 46.0 / 51.0 / 56.0 / 61.0 | 17353 | 17914 | 16783 | 17673 | 19610 |
| v1 PIT sin RR; sobre 60 | 41.3 / 49.7 / 58.0 / 64.7 | 17748 | 16677 | 18809 | 16847 | 19252 |
| v1 PIT sin convicción; sobre 70 | 38.3 / 44.0 / 49.9 / 55.4 | 16350 | 17691 | 19558 | 15034 | 20700 |
| v2 PIT: catalizador + técnico + contexto; sobre 50 | 29.6 / 40.0 / 49.6 / 57.6 | 17071 | 18387 | 16640 | 16940 | 20295 |

### migración entre tramos de escala; no son bandas operativas equivalentes

| A \ D | [0,10) | [10,20) | [20,30) | [30,40) | [40,50) | [50,60) | [60,70) | [70,80) | [80,90) | [90,100] | total |
|---|---|---|---|---|---|---|---|---|---|---|---|
| [20,30) | 382 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 382 |
| [30,40) | 564 | 3451 | 2154 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 6169 |
| [40,50) | 498 | 2968 | 6332 | 15853 | 451 | 0 | 0 | 0 | 0 | 0 | 26102 |
| [50,60) | 0 | 0 | 1789 | 1311 | 18616 | 12773 | 0 | 0 | 0 | 0 | 34489 |
| [60,70) | 0 | 0 | 0 | 156 | 213 | 7978 | 10526 | 909 | 0 | 0 | 19782 |
| [70,80) | 0 | 0 | 0 | 0 | 0 | 16 | 8 | 1804 | 504 | 0 | 2332 |
| [80,90) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 31 | 46 | 77 |

### Región

| región | n | mediana D-A | p25 | p75 |
|---|---|---|---|---|
| ASIA | 15839 | -8.0 | -13.1 | -3.6 |
| EMERGING_MARKETS | 1019 | -6.3 | -11.3 | -2.4 |
| EUROPA | 30661 | -7.9 | -12.4 | -3.9 |
| GLOBAL | 2233 | -6.0 | -10.8 | -2.6 |
| USA | 39581 | -8.0 | -12.8 | -4.1 |

### Activo

90 activos; mediana D-A por activo: mín -11.8, p25 -9.4, mediana -7.9, p75 -6.6, máx -4.9.
Tabla completa: `tablas/medio-activos-D-menos-A.tsv`.

## Clasificación operativa

no aplica: Score v2 no dispone de umbrales calibrados
