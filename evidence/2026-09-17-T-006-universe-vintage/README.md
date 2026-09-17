# T-006 universe vintage e identidad

Commit de base: `5de38c2`
Instante de cierre: `2026-09-17T10:50Z`

## Comandos

Línea base antes de editar:

```bash
source .venv/bin/activate && python -m pytest -q && ruff check . && mypy advisor
python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar | tail -3
```

Verificación después:

```bash
source .venv/bin/activate && python -m pytest -q
source .venv/bin/activate && ruff check . && mypy advisor
python -m advisor.main universo --vintage
python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar | tail -3
```

Salidas guardadas:
- `antes.txt`
- `despues.txt`

## Conclusión

El nuevo `universe_vintage_id` canónico es:

```text
2ba5b3f370badc77c10457f71c21f445425366d524905b85a5c4f39a1ea49a5c
```

El id provisional anterior era:

```text
80d05f21abad212757d2f06d9f2dd53032b92a342dba90904b3086ea970d0b59
```

Las pasadas persistidas antes de T-006 conservan el provisional. Las pasadas
nuevas usan el id canónico.

## Método de `added_at`

No se usó `git log -S`; la sección de comprobación del 2026-09-17 lo descarta.
Se cargaron los tres `universe.yaml` relevantes y se compararon conjuntos de
símbolos:

```bash
git show 93009da:universe.yaml
git show e952f71:universe.yaml
git show HEAD:universe.yaml
```

Resultado reproducido:

- `93009da` (`2026-08-27`): 28 símbolos en el esquema antiguo `symbol:`.
- `e952f71` (`2026-08-29`): 126 símbolos con `primary_symbol:`.
- `HEAD`: 126 símbolos.
- Intersección `93009da ∩ HEAD`: 20 instrumentos con `added_at: 2026-08-27`.
- Diferencia `HEAD - 93009da`: 106 instrumentos con `added_at: 2026-08-29`.
- Diferencia `93009da - HEAD`: 8 listings alemanes ausentes tratados como
  instrumentos distintos.

Lista `2026-08-27`:

```text
4GLD.DE ALV.DE ASML.AS BTC-EUR EQQQ.DE ETH-EUR EUNH.DE EUNL.DE IS3N.DE
MBG.DE MC.PA SAP.DE SIE.DE ^GDAXI ^GSPC ^HSI ^N225 ^NDX ^STOXX50E ^VIX
```

Los demás 106 instrumentos actuales llevan `2026-08-29`. En particular,
`AAPL` lleva `2026-08-29`, `ticker_history: []`, e `issuer_id: apple`; no
reclama antigüedad del listing alemán `APC.DE`.

## Comprobación manual

El subcomando imprime:

```text
universe_vintage_id=2ba5b3f370badc77c10457f71c21f445425366d524905b85a5c4f39a1ea49a5c
```

El pie del informe en `despues.txt` termina con:

```text
universo 2ba5b3f3
```

Cálculo comprobado: los 8 primeros caracteres del id canónico son
`2ba5b3f3`; coinciden con el pie del informe.

Además, el payload canónico tiene 107 entradas analizables; el primer
`instrument_id` ordenado es `000660.KS@KSC` y el último es `ZPRR.DE@XETRA`.

## Impacto

- Activos que entran o salen del universo analizable: 0.
- Activos con metadatos nuevos: 126.
- Señales que cambian por score, niveles, frescura, ejecución o benchmark: 0.
- Motivo del único cambio visible en la salida: el pie del manifiesto pasa de
  `universo 80d05f21` a `universo 2ba5b3f3`.

## Hallazgos

- SAME_SCOPE: un test sintético declaraba un ISIN sin fuente; se actualizó el
  fixture para reflejar el nuevo contrato.
- FOLLOW_UP: `graphify-out/` estaba sin seguimiento antes de empezar.
- OBSERVATION: pytest mantiene 3 warnings preexistentes no relacionados con
  T-006.

---

## Verificación independiente del supervisor (Claude Code, 2026-09-17)

La entrega llegó con 500 tests, `ruff` y `mypy` limpios. Eso no basta en este
proyecto, así que se ejercitó el camino real. Todo lo de abajo está medido, no
leído del diff.

### Un defecto en la propia evidencia

**`antes.txt` y `despues.txt` no contienen el informe**, solo su pie: la captura
mezcló `stderr` con las últimas líneas de `stdout`, así que quedaron los logs de
recorte de barra y el manifiesto, pero no los bloques OPERAR / RADAR /
DESCARTADOS. Con esos dos ficheros **el impacto no se puede medir**, que es
justo para lo que existen. Se añade
`informe-despues-completo.txt`, capturado aparte.

### «0 señales» comprobado donde es comprobable

Comparar dos pasadas en vivo no sirve para sostenerlo: entre la línea base de
las 09:06 y la de las 11:0x la sesión europea estaba abierta y el reparto se
mueve solo. De hecho se movió —`ALV.DE`, `IBE.MC` y `RACE.MI` salen de
descartados, `R6C0.DE` entra— y es rotación de mercado en el borde del umbral:
`R6C0.DE` puntuaba 67 a las 09:06 y `IFX.DE` puntúa 67 ahora, el mismo hueco del
radar ocupado por otro activo.

La comprobación válida es sobre **datos congelados**, que son deterministas:

```
python -m advisor.main event-study 071ddb2b… --horizonte swing   → código 0
Activos evaluados: 107 | señales evaluadas: 121786
estimador primario: media por bloque de expectancy neta en R +0.073 (bloques=21, longitud=60)
```

Son exactamente los números anteriores a T-006. Guardado en
`event-study-swing.txt`. **Esa es la prueba de que la identidad no toca la
señal**, y la sostiene además el diff: no aparecen `analyzer.py`, `scoring.py`,
`levels.py`, `opportunity.py`, `execution.py`, `freshness.py` ni `quality.py`.

### Comprobado a mano, contra el universo real

- `universo --vintage` imprime `2ba5b3f3…` y el pie del informe de una pasada
  nueva termina en `universo 2ba5b3f3`. Coinciden.
- **Añadir un `notes` no cambia el vintage**; cambiar un `benchmark` sí
  (`^TWII` → `^N225` lo mueve a `1815b2fb…`), y al revertir vuelve a
  `2ba5b3f3…`. `universe.yaml` quedó byte a byte intacto tras las pruebas.
- 126 instrumentos, **107 analizables**, los 126 siguen en
  `trade_republic: unknown`, los 18 ISIN conservan sus 18 `isin_source`, y
  `ticker_history` está vacío en los 126, como manda la decisión de los ocho
  renombrados.
- Los tres validadores nuevos fallan de verdad sobre el YAML real, no solo con
  fixtures: ISIN sin fuente → «un ISIN sin fuente no es verificado»; `added_at`
  nulo e `issuer_id` nulo → «identidad de universo incompleta».
- `.gitignore`: `git add -n data/` propone **un solo fichero**, el
  `manifest.json` de la cosecha. Los 126 CSV siguen ignorados.
- Se ejecutaron además `frescura-historico`, `seguimiento`, `posiciones` y
  `event-study`, todos con código 0. `verificar-systemd` falla en el portátil
  por no existir `/etc/intradia-bot/systemd.env`, que solo vive en la Pi, donde
  sí se verificó hoy.

### Dos consecuencias que conviene dejar escritas

1. **Verificar un ISIN cambiará el `universe_vintage_id`.** `instrument_id` es
   el ISIN cuando existe y `SYMBOL@MARKET` cuando no, así que cada activo que
   OA-03 verifique moverá su `instrument_id` y con él el hash del universo. Es
   coherente con el diseño —la identidad cambia, el vintage cambia— pero
   significa que el trabajo manual de los 89 ISIN **irá invalidando la
   comparabilidad** de los resultados anteriores, y eso hay que planificarlo,
   no descubrirlo.
2. **La guarda de INV-08 ampliada no protegía nada** (corregido después, ver
   abajo). El aborto por «universo distinto» solo actúa si el manifiesto de la
   cosecha trae `universe_vintage_id`, y el de `071ddb2b…` no lo tiene.

Además, `issuer_id` se exige a los **126**, no solo a los 107 analizables como
decía la ficha. Es más estricto de lo pedido, funciona —los 19 de contexto lo
tienen— y deja el universo entero con identidad; se anota porque es un contrato
más fuerte que el especificado.


---

## Revisión independiente y correcciones (2026-09-17, tarde)

Veredicto **CORREGIR**: un BLOCKER y dos defectos de alcance, los tres
reproducidos antes de tocar nada y corregidos. Lo que sigue incluye **un error
del supervisor**, no solo de la implementación.

### BLOCKER — commitear el `manifest.json` ponía el CI en rojo

Tres tests deciden saltarse comprobando que exista el **directorio** de la
cosecha. Mientras `data/vintages/` entero estaba ignorado, en un clon limpio no
existía y los tests se saltaban. Al commitear el `manifest.json`, el directorio
**sí existe** en el clon —con un único fichero dentro—, la guarda deja de
saltar y `load_vintage` muere al abrir el primer CSV, que sigue ignorado.

Reproducido sin tocar el repo, exportando el commit como lo haría
`actions/checkout`:

```
git archive e0bff6b | tar -x -C <tmp> && pytest -q   → 3 failed, 497 passed
```

En el portátil la suite pasaba (500 ✓) porque ahí los 126 CSV existen. Es
exactamente el patrón «una suite verde no basta» del propio proyecto, y habría
salido en el primer push.

Corregido: la guarda mira `AAPL.csv`, que es lo que el test necesita de verdad.
Verificado del mismo modo: **499 pasan, 3 saltados** en el árbol exportado.

### Un error del supervisor, no de Codex

La versión anterior de este documento decía que la guarda de INV-08 ampliada
«empieza a proteger con la primera cosecha congelada después de T-006». **Era
falso.** `freeze_vintage` construye el manifiesto con cuatro claves y
`universe_vintage_id` no es ninguna de ellas, así que ninguna cosecha futura lo
habría llevado tampoco: el `.get()` devolvía `None` siempre y el aborto no
saltaba jamás. El único test que lo cubría fabricaba a mano un manifiesto con
una clave que el pipeline real no produce nunca, de modo que pasaba en verde
con la guarda muerta.

Corregido de raíz: `freeze_vintage` recibe el universo y lo escribe **dentro
del cuerpo que se hashea**, porque el universo forma parte de la identidad de
la cosecha. Consecuencia asumida y anotada: las cosechas congeladas a partir de
ahora tendrán un `data_vintage_id` distinto del que tendrían con el esquema
anterior; la cosecha `071ddb2b…` se sigue leyendo igual, porque `load_vintage`
recalcula el hash sobre el cuerpo que encuentra. El test nuevo congela de
verdad, recarga y comprueba que el aborto salta.

### El punto ciego del benchmark, que mi comprobación manual no vio

El payload hasheaba `asset.benchmark`, su **valor**. Pero
`resolve_benchmark_symbol` decide por **presencia** del campo, no por valor, y
solo 2 de los 107 analizables lo declaran. Consecuencia medida:

```
SAP.DE benchmark efectivo antes de declarar nada : ^STOXX
SAP.DE tras añadirle `benchmark: null`           : None
vintage antes y después                          : idéntico
```

Cambiar el índice comparable de un activo le cambia la fortaleza relativa y con
ella la puntuación, y el identificador que existe para pinear el universo no se
enteraba. Mi comprobación manual de esta mañana (`^TWII` → `^N225`) tocó
justamente uno de los dos activos que sí declaran benchmark, el único caso que
ya funcionaba; y el test del fixture ponía `^GDAXI` en todos, un valor que
ningún analizable real declara. Dos comprobaciones que se apoyaban en el mismo
punto ciego.

Corregido añadiendo `benchmark_declared` al payload, con un test del caso real
—activo sin override al que se le añade `benchmark: null`—. **El vintage
canónico cambia** a `b160c4c2b4c9827f63876bb876b9c66a0cc1db564b877c021ecb93a5fa64089c`;
D-23, la constante `REAL_UNIVERSE_VINTAGE` y este documento quedan actualizados.

### Estado tras las correcciones

502 tests en el árbol de trabajo, 499 y 3 saltados en un clon limpio, `ruff` y
`mypy` limpios.

### Queda abierto, sin corregir a propósito

Dos observaciones del revisor que no son de esta ficha y se anotan para después:
`analizar --grupos X` declara el vintage del universo **entero** y no el del
subconjunto analizado, y el informe de `capacidad-estadistica` no publica
ningún vintage, así que un veredicto de GATE no es atribuible a ninguna
cosecha. Ninguna de las dos las introduce T-006.
