# T-018 — caché local de barras de sesión cerrada ya validadas (C-09)

- Instante de cierre: `2026-09-25T11:40Z`. Rama `feat/validated-bar-cache`.
- Suite: **660 tests pasan** (615 en `main` + 45 nuevos en `tests/test_bar_cache.py`),
  `ruff check .` limpio, `mypy advisor` limpio (67 ficheros), Python 3.12.13.
- Decisiones del propietario tomadas en esta sesión: **D-44** (regla 4 de la caché
  y la distinción entre reajuste de la serie y revisión de una barra).
- **No se escribió en la base de producción.** Todo lo real se hizo sobre una
  copia del `intradia.db` del portátil, en un directorio temporal, con un
  `config.yaml` que solo cambia `db_path`.

## La migración v5 → v6 sobre una base real, con respaldo previo

La copia estaba en esquema **v4**, así que al abrirla se aplicaron v5 y v6, cada
una con su respaldo previo registrado en `backup_log` (INV-17):

| Respaldo | Bytes | SHA-256 (32 primeros) |
|---|---:|---|
| `intradia.db.bak-20260925-111449-pre-v5` | 180.224 | `7228a5fce40120046886ad7503808756` |
| `intradia.db.bak-20260925-111449-pre-v6` | 188.416 | `83f66a04779816b7e0aadf7280746961` |

Las 107 mediciones de frescura que ya había se conservaron. La v6 añade
`validated_bar`, `validated_bar_revision` y cuatro columnas a
`data_freshness_measurement`: `bars_served_from_cache`, `bars_pinned_revisions`,
`sessions_never_observed` y `bar_cache_status`.

## Las dos pasadas reales

`pasada-de-verificacion.py` es el guion exacto que se ejecutó, y
`pasadas-reales.txt` su salida literal. La segunda pasada envuelve al **proveedor
real** para que oculte la última sesión cerrada de los símbolos `.DE`, que es
exactamente lo que hace yfinance a las 06 UTC con las plazas europeas (D-40).
Todo lo demás —series, universo de 93, calendarios, análisis— es real.

| | pasada normal | retirando la última sesión europea |
|---|---:|---:|
| Barras validadas guardadas | **3.328** | 0 (ya estaban) |
| Sesiones retiradas al proveedor | 0 | **12** |
| Símbolos servidos por la caché | 0 | **12** |
| Barras servidas por la caché | 0 | **12** |
| Retiradas que la caché **no** restauró | — | **0** |
| Barras servidas que nadie había retirado | 0 | **0** |
| Revisiones fijadas · reanclajes · fallos | 0 · 0 · 0 | 0 · 0 · 0 |

**Doce retiradas, doce restauradas, ni una de más.** Es la comprobación que pedía
la ficha, y el «ni una de más» importa tanto como el resto: una versión anterior
servía 74 barras en 19 símbolos con solo 12 retiradas, porque alargaba hacia atrás
ventanas que el llamante había pedido cortas (`^VIX` se pide con `period="5d"` y
recibía 19 barras guardadas por la llamada de `2y` del mismo símbolo).

Solo 12 de los ~25 europeos tenían la barra del 2026-09-24 que retirar: al resto
ya le faltaba, y eso es justo lo que cuenta el apartado siguiente.

## La cifra que decide OD-02 bis, y cómo NO leerla

Sesiones exigibles **nunca observadas y no entregadas**, en la pasada del
`2026-09-25T11:31Z` sobre 93 analizables:

- **33 sesiones en 33 activos analizados.** Es la cifra que se persiste y se
  acumula, y la que contesta a OD-02 bis.
- **15 sesiones más en símbolos de contexto y benchmarks**, que no tienen fila de
  frescura y por eso se publican aparte: si se sumaran, el número del informe no
  cuadraría con el acumulado que sale de la base.

Contrastadas por SQL directo contra la métrica que ya existía, las 33 se parten en
dos grupos que significan cosas distintas:

- **17 son huecos interiores** que `absent_reference_sessions` ya declaraba, todas
  del `2026-09-22`. Que las dos métricas coincidan es la comprobación de que el
  contador nuevo no se ha inventado una población.
- **16 son cola del día anterior** (`last_bar_date = 2026-09-23`,
  `sessions_approx = 1`) en ETF alemanes. No aparecían en
  `absent_reference_sessions` porque esa métrica solo mira sesiones interiores; la
  cola la cubría `sessions_approx`. Son exactamente las que vetan hoy.

**Una sola pasada no decide nada.** No distingue un fallo puntual del proveedor de
un hueco estructural, y las mediciones de una misma pasada **no son
independientes**: un fallo del proveedor afecta a decenas de símbolos a la vez, así
que estas 33 son ~1 evento, no 33 observaciones (INV-22). La cifra hay que leerla
acumulada y deduplicada por par activo-sesión, con `frescura-historico`, tras
varias semanas en la Pi.

## Los nueve defectos que cazó la revisión cruzada

Codex revisó el diseño antes de escribir el módulo y supervisó el código después,
en dos vueltas. **Ninguno de los nueve se detectó leyendo el código: todos se
midieron ejecutándolos**, y cada uno tiene ahora un test con el valor de antes
escrito dentro.

Del diseño, antes de escribir:

1. el `backtest` **vivo** se habría quedado sin caché, rompiendo INV-06;
2. el acumulado habría contado el mismo par activo-sesión una vez por pasada (el
   defecto que D-40 ya obligó a corregir en las ausencias);
3. la plaza de los índices: el universo declara `^STOXX50E` en `ZRH`, sin cierre
   regular, mientras producción lo recorta con XETRA.

Del código, primera vuelta:

4. el índice de una barra reinyectada degradaba a `object` y **`relative_strength`
   devolvía `None` en silencio** —medido: `None` frente a `6.111461203602397`—,
   justo en los activos que la caché rescata;
5. una barra con volumen desconocido metía un `NaN` y `build_snapshot` tomaba el
   volumen de la sesión anterior como si fuera el de esa barra;
6. una revisión que solo tocaba el volumen no se registraba, y el análisis
   consumía el volumen nuevo;
7. **el más grave:** exigir unanimidad para detectar el reajuste hacía que un split
   con una revisión puntual el mismo día **no** reanclara, y el análisis veía la
   base anterior al split: **168,5 donde el proveedor ya servía 85,09**.

Del código, segunda vuelta (los dos primeros los **abrieron** las correcciones de
la primera, que es para lo que hay una segunda):

8. la regla de mayoría aceptaba un **empate** como mayoría y reanclaba al factor
   que llegaba antes en el tiempo: elegir la escala de una serie por sorteo;
9. intersecar `sessions_never_observed` entre dos peticiones del mismo símbolo con
   periodos distintos **dejaba el contador de OD-02 bis en cero**, porque la
   petición corta empieza después de la sesión que la larga sí había detectado.
   Ahora se **resta lo entregado**, que es lo que dice la regla 6.

Y uno menor, condicional: una marca guardada releída en otra zona puede retroceder
de sesión con el cambio de horario. Ahora se valida que vuelva a fechar en su
propia sesión y, si no, **no se reinyecta y se declara**.

Dos más los encontró contrastar la pasada real por SQL, no leer código: el informe
publicaba 48 sesiones cuando solo 33 se persisten (mezclaba activos con índices), y
`_record` sobrescribía lo declarado cuando un símbolo se pide dos veces con
periodos distintos, con lo que podía perder una declaración de barra servida
(INV-21).

## Lo que esta entrega NO hace

- **No decide OD-02 bis.** Produce su cifra.
- **No toca** el score, la geometría, los umbrales, `classify()`, el veto de D-21
  ni la regla de barra abierta de D-37. Verificado en la revisión leyendo el
  código, no la descripción.
- **No toca** `data/vintages/` ni el modo `--vintage`: `get_raw_history` pasa
  intacto, así que la cosecha congelada sigue siendo lo que el proveedor sirvió
  (INV-13).
- **No escala una barra** por el factor de un reajuste. Coste declarado: una barra
  retirada el mismo día de un reajuste se pierde, porque escalarla produciría un
  valor que el bot nunca observó (regla 2 de D-41).
