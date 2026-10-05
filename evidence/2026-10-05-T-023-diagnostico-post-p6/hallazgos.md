# T-023 — Hallazgos del diagnóstico post-P6

> **Exploratorio / post hoc. No cambia D-70, no valida una nueva política y no constituye evidencia
> confirmatoria.** P6 sigue cerrado con B2 `NO PASA`, S2 `NO PASA` y salida `[]`.

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

Todas las cifras salen de los CSV de este directorio, generados por `diagnostico_p6.py` a partir de
`evidence/2026-10-03-T-022-p6/run/` (commit `0771989`). No hay ninguna re-simulación. La columna
«Fuente» indica el CSV y la clave. Unidades: «pp» = puntos porcentuales; «frac» = fracción (0,10 = 10 %).

Etiquetas:
- `OBSERVADO`: sale directamente de los artefactos o de una agregación contable determinista suya.
- `COMPATIBLE_CON`: los datos son compatibles con un mecanismo, sin probar causalidad.
- `NO_IDENTIFICABLE`: responder exigiría simular algo que no ocurrió o datos no archivados.

## Comprobaciones de base

- `OBSERVADO`: la reconstrucción diaria desde el ledger reproduce **exactamente** lo publicado por P6.
  En B2, la exposición media es 0,8371, el cash mínimo es 31,35 EUR y las posiciones son 10,48 de
  media y 16 de máximo, iguales a lo publicado; lo mismo ocurre en S2 y C0. También coinciden el
  `win_rate`, el PF, la fracción rechazada por cash, el capital pedido y disponible en los rechazos,
  las comisiones, el slippage, los dividendos y el FX. Σ P&L por activo = V_T − V_0, y
  Σ(R_EUR · riesgo_EUR) = Σ pnl_neto_EUR. Fuentes: `ocupacion-cash.csv` (`*_publicada` /
  `*_reconstruida`), `presion-capital.csv` (`fraccion_publicada`) y `operaciones-por-salida.csv`
  (`riesgo_tamano`).

## A. Dónde se abre la brecha en el tiempo

| | B2 | S2 | C0 | Fuente |
|---|---|---|---|---|
| Exceso 2022 (pp) | −6,86 | −4,23 | −6,33 | `brecha-temporal.csv` `exceso_anual` |
| Exceso 2023 (pp) | −12,09 | −27,94 | −27,86 | ídem |
| Exceso 2024 (pp) | −27,31 | −28,43 | −27,73 | ídem |
| Exceso 2025 (pp) | −23,84 | −19,27 | −30,94 | ídem |
| Exceso 2026 hasta el 27-08 (pp) | **+3,88** | −0,83 | −8,65 | ídem |
| Benchmark por año (pp) | 2022 −0,30; 2023 +43,80; 2024 +50,92; 2025 +31,44; 2026 +19,55 | | | ídem, `r_bench_pp` |
| Brecha logarítmica final ln(V_sis/V_bench) | −0,527 | −0,634 | −0,827 | `log_gap` |
| Aporte 2024 + 2025 a esa brecha | −0,200 y −0,200 | −0,209 y −0,159 | −0,203 y −0,268 | `log_gap_aporte_anual` |
| Meses con exceso > 0 / < 0 (de 51) | 22 / 29 | 21 / 30 | 16 / 35 | `conteo_meses` |
| Gap negativo sin volver a ≥ 0 desde | 2022-07-06 | 2022-10-21 | 2022-10-21 | `inicio_apertura` |
| Peor mes (pp) | 2022-07, −9,43 | 2025-05, −9,68 | 2023-11, −9,66 | `peores_meses` |

1. `OBSERVADO`: la brecha **no se concentra en unos pocos meses**. Es negativa todos los años
   completos de 2022 a 2025 en las tres corridas, y B2 y S2 tienen más meses negativos que positivos
   (29 y 30 de 51). La mayor parte se acumula en 2023–2025, los tres años en que el benchmark ganó
   entre +31 y +51 pp. En B2, 2024 y 2025 aportan −0,200 cada uno a una brecha logarítmica final
   de −0,527.
2. `OBSERVADO`: el único año con exceso positivo es 2026 en B2 (+3,88 pp), con un benchmark de
   +19,55 pp en lo que va de año.
3. `COMPATIBLE_CON`: la brecha crece sobre todo cuando el universo sube con fuerza (2023 y 2024). Es
   compatible con que los sistemas capten una fracción limitada de las subidas amplias del universo;
   no prueba por qué.

## B. Participación y exposición

| | B2 | S2 | C0 | Fuente |
|---|---|---|---|---|
| Exposición media | 0,8371 | 0,6054 | 0,5313 | `ocupacion-cash.csv` `resumen` |
| Días con exposición ≤ 25 % (al cierre previo) | 77 (63 en 2022) | 219 (112 en 2022) | 273 (120 en 2022) | `bucket_exposicion`, `bucket_exposicion_por_anio` |
| Días con exposición > 90 % | 688 | 217 | 139 | ídem |
| Suma del exceso diario en días ≤ 25 % | −0,247 | −0,442 | −0,509 | `[0,0.25]:suma_exceso` |
| Suma del exceso diario en días > 90 % | **+0,052** | −0,055 | −0,031 | `(0.9,1]:suma_exceso` |
| Retorno diario medio con exposición > 90 %: sistema / benchmark | 0,00061 / 0,00053 | 0,00123 / 0,00149 | 0,00149 / 0,00171 | `(0.9,1]:media_r_sis`, `media_r_bench` |

4. `OBSERVADO`: en B2 los días con más del 90 % invertido suman un exceso diario ligeramente
   **positivo** (+0,052), y los días con menor exposición suman todo el déficit. En S2 y C0 el
   exceso es negativo en todos los tramos, pero el mayor déficit está en los días con 25 % o menos
   invertido (−0,442 en S2 y −0,509 en C0).
5. `OBSERVADO`: los días con poca exposición de B2 se concentran en el arranque de 2022 (63 de 77).
   Los de S2 y C0 se reparten por todos los años: en S2 hay 25, 26, 39 y 18 días ≤ 25 % de 2023 a
   2026.
6. `COMPATIBLE_CON`: una participación baja explica una parte visible de la brecha de S2 y C0, y
   probablemente una parte menor de la de B2. **No es causal**: los días de exposición baja no son
   aleatorios, porque siguen a cierres de posiciones, estados de mercado concretos y el arranque.
   Las sumas de excesos diarios son descriptivas y no se suman exactamente a la brecha compuesta.

## C. Presión de capital

| | B2 | S2 | C0 | Fuente |
|---|---|---|---|---|
| Señales pendientes / entradas | 8 293 / 673 | 2 050 / 528 | 2 101 / 623 | `presion-capital.csv` `evento` |
| `INSUFFICIENT_CASH` | 7 005 | 319 | 241 | `ENTRY_REJECTED` |
| `ABOVE_MAX_ENTRY` | 531 | **1 175** | 1 197 | ídem |
| `IGNORED_ALREADY_OPEN` | 2 284 | 390 | 322 | `SIGNAL_IGNORED` |
| Fracción de ejecutables rechazada por cash | 0,9123 | 0,3766 | 0,2789 | `resumen` |
| Capital pedido / disponible en esos rechazos | 3,45 | 1,88 | 2,42 | `ratio_pedido_disponible` |
| Días con al menos un rechazo por cash | 834 (76,2 % de las instantáneas) | 167 (15,3 %) | 128 (11,7 %) | `dias_rechazo_cash` |
| Rechazos por cash al día (mediana / p90) | 6 / 16 | 0 / 1 | 0 / 1 | `percentil_rechazos_cash_por_dia_con_senal` |
| Rechazos por cash por año (2023–2026) | 2 065; 2 173; 1 636; 954 | 123; 107; 66; 20 | 88; 96; 36; 20 | `por_anio` |

7. `OBSERVADO`: en B2 la saturación de capital es **estructural**: hay rechazos por cash en el
   76 % de los días, durante todos los años, y en un día típico se rechazan 6 entradas ejecutables.
8. `OBSERVADO`: en S2 la saturación por cash es **ocasional** (15 % de los días; mediana de 0
   rechazos al día). Su principal motivo de rechazo es otro: `ABOVE_MAX_ENTRY`, 1 175 de 1 522
   rechazos (77 %), es decir, el precio de apertura ya superaba la entrada máxima permitida.
9. `COMPATIBLE_CON`: en B2, cómo se reparte el capital entre oportunidades simultáneas es una
   dimensión material del sistema. En S2 pesa más la combinación de pocas señales ejecutables y
   cash ocioso que la falta de cash.
10. `NO_IDENTIFICABLE`: el rendimiento que habrían tenido las 7 005 entradas de B2 rechazadas por
    cash, o las 1 175 de S2 rechazadas por `ABOVE_MAX_ENTRY`. Saberlo exige una simulación nueva.

## D. Anatomía del edge ejecutado

| | B2 | S2 | C0 | Fuente |
|---|---|---|---|---|
| N / win rate (EUR) | 673 / 0,4205 | 528 / 0,4602 | 623 / 0,4189 | `operaciones-por-salida.csv` `resumen` |
| R local: media / mediana | 0,248 / −1,010 | 0,238 / −0,803 | 0,164 / −1,031 | ídem |
| R local p10 / p90 | −1,18 / 2,42 | −1,19 / 2,07 | −1,18 / 2,11 | ídem |
| Salidas por objetivo: N, R medio, P&L EUR | 214, 2,41, +304 164 | 208, 1,96, +227 225 | 239, 2,07, +215 215 | `exit_reason` |
| Salidas por stop: N, R medio, P&L EUR | 359, −1,14, −229 798 | 272, −1,13, −159 087 | 357, −1,15, −174 012 | ídem |
| Salidas por tiempo: N, R medio, P&L EUR | 88, 0,65, +27 890 | 40, 0,53, +10 573 | 19, 0,70, +5 823 | ídem |
| Holding medio (sesiones) | 16,5 | 14,9 | 10,0 | ídem |
| Riesgo por operación / equity previa (media) | 0,41 % | 0,42 % | 0,37 % | `riesgo_tamano` |
| Notional de entrada / equity previa (media) | 8,1 % | 8,2 % | 9,1 % | ídem |
| R medio por año de salida, 2022 → 2026 | −0,73; 0,40; 0,25; 0,12; 0,39 | −0,64; 0,24; 0,24; 0,24; 0,31 | — | `anio_salida` |

11. `OBSERVADO`: el edge es asimétrico. La mediana de R es negativa (cerca de −1, el stop) y el
    resultado depende de las salidas por objetivo, que se cierran a una media de unos 2 R en B2
    (2,41) y S2 (1,96).
12. `OBSERVADO`: identidad contable, P&L = Σ R_EUR · riesgo_EUR. Cada operación arriesga de media un
    0,41 % de la equity en B2 y un 0,42 % en S2, sobre un notional de alrededor del 8 %. Ese riesgo
    por operación, multiplicado por la R media (0,248 y 0,238), es lo que cada operación cerrada
    aporta de media a la equity.
13. `OBSERVADO`: el edge por operación es positivo todos los años salvo 2022 en B2 y en S2. No
    depende de un único año, pero en B2 varía bastante (de 0,12 a 0,40).
14. `COMPATIBLE_CON`: con salidas por objetivo a unos 2 R tras unas 16 sesiones, una ganancia por
    posición limitada es compatible con quedarse por debajo de un universo que sube un 44–51 % al
    año. El benchmark mantiene sus posiciones durante toda la ventana, sin objetivos ni stops.

## E. Concentración del rendimiento por activo

| | B2 | S2 | Benchmark | Fuente |
|---|---|---|---|---|
| Fracción del P&L en el top 5 / top 10 | 0,446 / 0,707 | 0,334 / 0,588 | 0,351 / 0,502 | `contribucion-por-activo.csv` `resumen` |
| Activos con contribución > 0 / < 0 | 53 / 35 | 56 / 32 | 85 / 5 | ídem |
| Top 5 del benchmark | — | — | PLTR +22 796; RRU.DE +18 536; MU +14 899; 6857.T +14 625; NVDA +13 342 EUR | ídem |
| De los 10 mejores activos del benchmark: operados | 10 de 10 | 10 de 10 | — | `top10_benchmark` |
| Su fracción del notional de entrada del sistema (peso inicial del benchmark: 0,085) | 0,137 | 0,130 | — | `fraccion_notional`, `peso_inicial_benchmark` |
| Su fracción del P&L del sistema | 0,407 | 0,323 | — | `fraccion_pnl` |

15. `OBSERVADO`: el benchmark debe la mitad de su P&L a 10 de 90 activos (0,502), pero gana dinero en
    85 de 90. Su rendimiento es amplio, aunque los mayores ganadores pesan mucho.
16. `OBSERVADO`: B2 y S2 **sí operaron** los 10 mejores activos del benchmark. Les asignaron más
    notional de entrada que su peso inicial en el benchmark (0,137 y 0,130 frente a 0,085), y de ellos
    sale el 41 % y el 32 % de su P&L.
17. `COMPATIBLE_CON`: el problema no parece ser que los sistemas se perdieran los activos ganadores,
    sino cuánto de su subida retuvieron. Entran y salen en tramos de unas 16 sesiones, mientras que
    el benchmark mantiene durante toda la ventana. El notional de entrada mide rotación, no tiempo
    invertido.
18. `NO_IDENTIFICABLE`: cuánto habría aportado mantener esos activos más tiempo.

## F. Región, sector y divisa

| | B2: P&L (frac) / exposición media | S2: P&L (frac) / exposición media | Benchmark: P&L (frac) / nº activos | Fuente |
|---|---|---|---|---|
| USA | 0,386 / 0,243 | 0,433 / 0,212 | 0,522 / 40 | `contribucion-region-sector-divisa.csv` |
| EUROPA | 0,288 / 0,364 | 0,436 / 0,225 | 0,304 / 30 | ídem |
| ASIA | 0,318 / 0,188 | 0,144 / 0,134 | 0,148 / 16 | ídem |
| GLOBAL | −0,023 / 0,033 | 0,021 / 0,022 | 0,022 / 3 | ídem |
| EMERGING_MARKETS | 0,031 / 0,010 | −0,034 / 0,012 | 0,003 / 1 | ídem |

19. `OBSERVADO`: el 52 % del P&L del benchmark viene de USA. B2 tuvo de media un 24 % de la equity
    en USA y un 36 % en Europa; S2, un 21 % en USA.
20. `COMPATIBLE_CON`: la composición regional que generan las señales difiere de la región donde el
    universo más ganó. La exposición regional es consecuencia de las señales y no una decisión
    aparte, así que esto no aísla ningún mecanismo. El sector es una foto actual, igual que en P6.

## G. Costes, slippage, dividendos y FX

| | B2 | S2 | C0 | Benchmark 5 pb | Fuente |
|---|---|---|---|---|---|
| Comisiones EUR (frac de \|brecha\|) | 15 976 (0,115) | 11 399 (0,071) | 14 125 (0,074) | 450 | `costes-fx-dividendos.csv` |
| Slippage EUR (frac de \|brecha\|) | 7 988 (0,057) | 5 700 (0,036) | 7 062 (0,037) | 55 | ídem |
| Dividendos EUR | 10 196 | 5 612 | 5 629 | 9 924 | ídem |
| FX EUR (frac de \|brecha\|) | −8 859 (−0,064) | −3 006 (−0,019) | −2 778 (−0,015) | NO_IDENTIFICABLE | ídem |
| Brecha final contra el benchmark, EUR | −139 256 | −159 549 | −191 367 | — | ídem |

21. `OBSERVADO`: por separado, cada componente es **pequeño frente a la brecha**. En B2, las
    comisiones equivalen al 11,5 % de la brecha, el slippage al 5,7 % y la pérdida por FX al 6,4 %.
    En S2 son menores todavía. Los dividendos cobrados por B2 (10 196 EUR) son del mismo orden que
    los del benchmark (9 924).
22. `OBSERVADO`: el FX es material solo en B2 (−8 859 EUR, el 8,8 % de su beneficio neto). Es
    pequeño en S2 y C0.
23. `NO_IDENTIFICABLE`: el efecto FX del benchmark, porque su ledger no lo separa, y cualquier
    «CAGR sin costes». La comparación es solo de magnitudes contables; no es un contrafactual.

## H. Rotación y duración

24. `OBSERVADO`: B2 rota mucho y está casi siempre invertido, con un turnover anual de 27,1, entre
    151 y 175 entradas al año de 2023 a 2025, una exposición del 84 % y un holding de 16,5 sesiones.
    S2 rota menos (turnover de 21,3), con un holding de 14,9 sesiones, y pasa mucho tiempo en cash
    (exposición del 61 %). C0 tiene el holding más corto (10,0 sesiones) y la menor exposición
    (53 %). Fuentes: `comparativa-primaria-todas-barras.csv` y `operaciones-por-salida.csv`.

## I. Puente de todas las barras (descriptivo)

| | B2 primaria | B2 todas las barras | S2 primaria | S2 todas las barras | Fuente |
|---|---|---|---|---|---|
| Exposición media | 0,837 | 0,955 | 0,605 | 0,951 | `comparativa-primaria-todas-barras.csv` |
| CAGR | 18,03 % | 24,29 % | 15,08 % | 28,23 % | ídem |
| excess_CAGR_pp | −15,77 | −9,52 | −18,72 | −5,57 | ídem |
| Fracción rechazada por cash | 0,912 | 0,988 | 0,377 | 0,975 | ídem |

25. `OBSERVADO`: aplicada a toda la población, con exposiciones del 95 %, la misma geometría
    **sigue por debajo del benchmark** (−9,52 y −5,57 pp).
26. `COMPATIBLE_CON`: la brecha no aparece solo por el filtro OPERAR ni solo por una participación
    baja. Con una participación casi completa también existe, aunque es menor. Esto no es una
    réplica de P4/P5, no decide nada y no rescata a ninguna candidata.

## J. C0 como referencia

27. `OBSERVADO`: B2 y S2 mejoran a C0 en R medio (0,25 y 0,24 frente a 0,16), PF (1,40 y 1,40
    frente a 1,25), CAGR (18,0 % y 15,1 % frente a 9,9 %) y exceso (−15,8 y −18,7 pp frente a
    −23,9). C0 **también** queda por debajo del benchmark todos los años completos y tiene más meses
    negativos (35 de 51). No superar el benchmark no es propio de las geometrías de P4/P5: también le
    ocurre a la geometría de producción.

## Respuestas a las preguntas de T-023 §7

| # | Pregunta | Etiqueta | Respuesta |
|---|---|---|---|
| 1 | ¿Brecha concentrada o persistente? | `OBSERVADO` | Persistente: negativa en todos los años completos 2022–2025 y en la mayoría de los meses. Se acumula sobre todo en 2023–2025, con el universo subiendo fuerte (A). |
| 2 | ¿La baja exposición explica una parte visible? | `COMPATIBLE_CON` | Sí en S2 y C0; menor en B2, cuyo déficit cae fuera de los días con más del 90 % invertido (B). No es causal. |
| 3 | ¿B2 sufre saturación de cash estructural? | `OBSERVADO` | Sí: rechazos en el 76 % de los días y todos los años; 91 % de las ejecutables rechazadas (C). |
| 4 | ¿S2: saturación de cash o menor participación? | `OBSERVADO` + `COMPATIBLE_CON` | Sobre todo menor participación: exposición del 61 % y 219 días ≤ 25 %. Su principal rechazo es `ABOVE_MAX_ENTRY` (77 %); el cash es ocasional (B, C). |
| 5 | ¿Costes y slippage bastan por sí solos? | `OBSERVADO` | No: cada componente queda por debajo del 12 % de la brecha (G). |
| 6 | ¿FX material? | `OBSERVADO` | En B2, moderado (−8 859 EUR, el 6,4 % de la brecha); en S2 y C0, pequeño. En el benchmark no es identificable (G). |
| 7 | ¿El benchmark depende de pocos activos? | `OBSERVADO` | En parte: el top 10 da el 50 % de su P&L, pero 85 de 90 activos son positivos (E). |
| 8 | ¿B2 y S2 capturan esos activos y periodos? | `OBSERVADO` + `COMPATIBLE_CON` | Operan los 10 mejores, con más notional que su peso en el benchmark, pero en tramos cortos; retienen una fracción limitada de la subida (E, D). |
| 9 | ¿Edge concentrado en años, mercados, activos o salidas? | `OBSERVADO` | Por salida: lo aportan los objetivos (~2 R). Por años: positivo en 2023–2026. Por activos: B2 concentrado (top 10 = 71 % del P&L). Por región: B2 reparte entre USA, Asia y Europa; S2, entre USA y Europa (D, E, F). |
| 10 | ¿Todas las barras sigue por debajo? | `OBSERVADO` | Sí: −9,52 y −5,57 pp con un 95 % de exposición (I). |
| 11 | ¿Se puede evaluar si otra prioridad de señales habría mejorado B2? | `NO_IDENTIFICABLE` | No. Los artefactos no contienen el desenlace de las entradas rechazadas, y fabricarlo exige una simulación nueva. |
| 12 | ¿Qué mecanismos justifican investigar y cuáles no? | `COMPATIBLE_CON` | Merecen hipótesis: retención de la subida y salidas (D, E, I), asignación bajo capital finito en B2 (C), participación y cash ocioso en S2 (B, C) y el edge por euro invertido (D). Los costes y el FX no justifican por sí solos una línea propia (G). Ver `hipotesis-candidatas.md`. |
