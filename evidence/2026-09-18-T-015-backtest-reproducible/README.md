# T-015 — el backtest deja de depender del minuto en que se ejecuta

Fecha: 2026-09-18
Rama: `feat/reproducible-backtest`, desde `main` en `8790a49`
Cosecha usada: `071ddb2b…` (congelada el 2026-08-30, 126 símbolos, 2021-08-29 → 2026-08-30)

## La cifra que justifica la ficha, medida hoy

Tres ejecuciones seguidas de `backtest --horizonte swing`, **el mismo commit, el
mismo universo, la misma configuración**, separadas por minutos:

| | operaciones | expectancy R | R total | profit factor |
|---|---:|---:|---:|---:|
| vivo-1 | 869 | 0,17 | 149,19 | 1,26 |
| vivo-2 | 862 | 0,18 | 157,10 | 1,28 |
| vivo-3 | 867 | 0,18 | 153,92 | 1,27 |
| **dispersión** | **7** | | **7,91** | |

Y las mismas tres sobre la cosecha congelada:

| | operaciones | expectancy R | R total |
|---|---:|---:|---:|
| cosecha-a | 866 | 0,17 | 145,10 |
| cosecha-b | 866 | 0,17 | 145,10 |
| cosecha-c | 866 | 0,17 | 145,10 |
| **dispersión** | **0** | | **0** |

Las tres del modo cosecha son **el mismo fichero byte a byte**
(`b6027a69d74e0f5b0c60d76a7cd0597c`). Detalle en `dispersion.txt`.

La R total en vivo se mueve un 5 % entre dos ejecuciones que solo se
diferencian en la hora. Cualquier criterio de aceptación que compare dos
pasadas de backtest en vivo está comparando ruido.

## Qué hay aquí

| Fichero | Qué demuestra |
|---|---|
| `dispersion.txt` | la tabla de arriba, generada de las salidas reales |
| `cosecha-a/b/c.txt` | tres ejecuciones sobre la cosecha, idénticas (md5 `79b21916…`) |
| `vivo-1/2/3.txt` | tres ejecuciones en vivo, distintas |
| `inyeccion-de-defectos.txt` | qué caza cada test y **qué no**, inyectando el defecto |
| `suite-despues.txt` | `pytest`, `ruff`, `mypy` |

Línea base en `main` (`8790a49`): 576 tests, `ruff` y `mypy` limpios. Al cerrar: **587 tests** (11 nuevos), limpios.

## Cosecha y vivo no coinciden, y no tienen por qué

866 sobre cosecha frente a 862-869 en vivo. Hay **tres** motivos, y el tercero
lo encontró la revisión de Codex:

1. **Fechas distintas**: la cosecha va hasta el 2026-08-30 y el vivo hasta la
   sesión de hoy.
2. **Contexto más corto**: la cosecha se congeló con 5 años para todos los
   símbolos, así que no lleva el histórico previo que el modo en vivo descarga
   para la media de tendencia (10 años). Sus primeras 199 sesiones del índice
   corren sin ese contexto, y el informe lo dice.
3. **Precios ajustados frente a brutos**, que es el motivo más estructural.
   `get_history` (vivo) llama a `ticker.history(...)` sin `auto_adjust`, que en
   yfinance 1.7.0 significa precios **ajustados** por dividendo;
   `get_raw_history` —con la que se congeló la cosecha— usa
   `auto_adjust=False, actions=True` y conserva el material **bruto**. Medido en
   la cosecha real: `SAP.DE` tiene 5 dividendos que suman 11,55 y `AAPL` 20 que
   suman 4,90, así que para esos activos el `Close` no es el mismo número en los
   dos modos, y con él cambian ATR, niveles y salidas.

El informe declara los tres. Lo que importa no es que coincidan, sino que una se
puede repetir y la otra no.

## Qué caza cada test, y qué no

Medido inyectando el defecto, no razonado:

| Defecto inyectado | Test | ¿lo caza? |
|---|---|---|
| El informe deja de avisar de que el modo en vivo no es reproducible | declaración | **sí** |
| Media de tendencia centrada (`center=True`: 100 barras futuras) | truncamiento | **sí** |
| VIX con `shift(-1)`: look-ahead de **una** barra | truncamiento | **no** |
| VIX con `shift(-1)`: look-ahead de **una** barra | **perturbación** | **sí** |
| El informe deja de distinguir «falta toda la tendencia» de «no falta nada» | tendencia ausente | **sí** |
| Alineado con `bfill` | truncamiento | no aplica: en el fixture todas las series comparten índice diario, así que `bfill` y `ffill` dan lo mismo |

**El truncamiento no puede ver un look-ahead de una barra**: cualquier corte
posterior a la barra espiada la deja presente en las dos series. Por eso ese test
se llama `test_las_operaciones_cerradas_no_cambian_al_quitar_el_futuro` y no
«point-in-time».

**La perturbación sí lo ve, y fue idea de la revisión de Codex.** En vez de
cortar el futuro se **cambia** una sola vela: se pone el VIX a 80 exactamente en
la vela en la que una operación entra —cuya decisión se tomó en la anterior— y se
exige que esa operación salga idéntica. Con `shift(1)` la decisión mira el VIX de
dos velas antes y no puede verla; con `shift(-1)` la ve y el test falla. Es
`test_una_decision_no_puede_depender_de_la_barra_siguiente`.

## Consecuencia para lo ya publicado

Las cifras de backtest publicadas antes de esta ficha —la línea base de la línea
0 en `evidence/2026-09-14-L0-baseline/` entre ellas— se hicieron en vivo y **no
son reproducibles**. No están mal: son irrepetibles, que para auditar es peor.
Qué se hace con ellas está en D-34.
