# T-006 — `universe_vintage_id` e identidad mínima de instrumentos (A-00)

Estado: PENDIENTE (intento del 2026-09-14 bloqueado por el entorno; ver handoff)
Agente: Codex (mecánico, bien especificado) → Opus (revisión breve del hash canónico)
Línea / fase: A-00 (prerrequisito de GATE P2) y B-01 (identidad para la línea B)
Gate al que contribuye: GATE P2 (requisito 3), GATE B0

## Objetivo
El universo analizable tiene una identidad versionada (`universe_vintage_id`)
que entra en el manifiesto de ejecución y en todo resultado de investigación,
y cada activo lleva los campos mínimos de identidad emisor/instrumento/listing.

## Por qué existe
Los 107 activos se eligieron el 2026-08-27/29 con conocimiento de 2026 y se
miden hacia atrás cinco años (verificado: `git log -- universe.yaml`). Ese
sesgo no se puede corregir gratis, pero sí acotar: hace falta saber
**exactamente** qué universo produjo cada número. Decisiones D-08, D-20.

## Dependencias previas
T-002 (el manifiesto consume el vintage). Puede hacerse en paralelo con T-003.

## Archivos probables
No asumir que sean exactos: verificar primero.
- `advisor/universe/models.py` (`Asset`, `Universe`)
- `advisor/universe/loader.py` (`load_universe`)
- `advisor/universe/vintage.py` (nuevo: `universe_vintage_id(universe) -> str`)
- `universe.yaml` (campos nuevos en los 126 instrumentos)
- `advisor/run/manifest.py` (T-002)
- `advisor/research/event_study.py`, `capacity.py`, `ablation.py`, `uncertainty.py` (los resultados publican el vintage)
- `.gitignore` (excepción `!data/vintages/*/manifest.json`)
- `tests/test_universe.py`, `tests/test_universe_vintage.py` (nuevo)

## Invariantes que no pueden romperse
INV-06, INV-16, INV-19 (esta tarea la establece). La carga del universo
sigue fallando ante un ISIN inválido.

## Implementación requerida
1. Campos nuevos en `Asset`, todos con valor por defecto para no romper la
   carga: `issuer_id: Optional[str]` (slug; obligatorio para `analizable:
   true` — validar), `instrument_id: str` (= ISIN si verificado, si no
   `f"{primary_symbol}@{primary_market}"`), `added_at: date` (obligatorio;
   para los 126 actuales: `2026-08-27` los del commit inicial y `2026-08-29`
   los del commit `e952f71`; obtenerlo con `git log -S` por símbolo y anotar
   el método en la ficha), `valid_to: Optional[date] = None`, `delisted_at:
   Optional[date] = None`, `ticker_history: list[str] = []`,
   `isin_verified_at: Optional[date]`, `isin_source: Optional[str]`,
   `trade_republic_checked_at: Optional[date]`.
2. Validador: `isin` sin `isin_verified_at` → error de carga («un ISIN sin
   fuente no es verificado»). Los 18 ISIN actuales: rellenar
   `isin_source: "universe inicial 2026-08-27"` y `isin_verified_at` con esa
   fecha; **no** inventar fuentes mejores.
3. `universe_vintage_id`: SHA-256 de la serialización canónica (JSON con
   claves ordenadas, sin espacios) de la lista de analizables ordenada por
   `instrument_id`, con los campos `instrument_id, issuer_id, primary_symbol,
   primary_market, primary_currency, asset_class, region, added_at, valid_to,
   benchmark`. Cambiar `name` o `notes` no cambia el vintage; cambiar la lista
   o un benchmark sí.
4. El manifiesto (T-002) y los resultados de `advisor/research/` incluyen
   `universe_vintage_id`. `comparacion-pareada` aborta si difieren, igual que
   con `data_vintage_id` (INV-08 ampliada).
5. Subcomando `universo --vintage` que imprime el id y la lista.
6. `.gitignore`: dejar de ignorar `data/vintages/*/manifest.json` y commitear
   el manifiesto de `071ddb2b…` (87 KB, verificado).

## Qué NO debe modificarse
La lista de analizables (ningún activo entra ni sale en esta tarea), los
benchmarks, `trade_republic` (sigue `unknown`).

## Tests unitarios
- `test_vintage_estable_ante_cambios_de_nombre_o_notas`.
- `test_vintage_cambia_si_entra_o_sale_un_activo`.
- `test_vintage_cambia_si_cambia_el_benchmark`.
- `test_isin_sin_fuente_falla_al_cargar`.
- `test_universe_real_tiene_107_analizables_y_vintage_conocido`: carga
  `universe.yaml` y fija el id en el test (se actualiza a propósito cuando el
  universo cambia, con entrada en el decision log).

## Tests de integración
`test_comparacion_pareada_aborta_con_universo_distinto`.

## Verificación contra datos reales
```bash
python -m advisor.main universo --vintage
python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar | tail -3
```
Comprobar a mano: el id impreso al pie del informe coincide con el del
subcomando; editar un `notes` y comprobar que no cambia; revertir.

## Medición del impacto
- nº activos afectados: 0 en decisión; 126 en metadatos.
- nº señales afectadas: 0.
- cambio en resultados relevantes: cada resultado futuro lleva vintage.

## Criterio de aceptación
- 107 analizables con `issuer_id`, `added_at` e `instrument_id`; carga sin errores.
- Vintage estable y testeado; manifiesto de cosecha commiteado.
- CI en verde.

## Criterio de rechazo
- Un ISIN nuevo «encontrado» sin fuente primaria.
- Un `added_at` inventado (debe salir de `git log`).

## Evidencia que debe quedar registrada
`evidence/<fecha>-T-006-universe-vintage/README.md` con el id, el comando
`git log -S` usado y la lista de `added_at` por commit.

## Commit esperado
Rama `feat/universe-vintage`. Mensaje:
`feat(universe): identidad mínima de instrumentos y universe_vintage_id en manifiesto y resultados`.

## Actualización documental requerida
`docs/roadmap.md`: A-00 → ACEPTADA; sección «Universo» con el id.
`docs/decision-log.md`: entrada con el primer vintage registrado.

## Handoff al siguiente agente

### Intento del 2026-09-14 — BLOQUEADA por el entorno, sin trabajo perdido

Se delegó a Codex sobre un git worktree hermano
(`../intradia-bot-t006`, rama `feat/universe-vintage` desde `1c76add`) para
ejecutarla en paralelo con T-003. **La sesión de Codex no puede escribir fuera
del directorio principal del repositorio**: falló antes de la línea base con

```text
mkdir: evidence/2026-09-14-T-006-universe-vintage: Operation not permitted
```

No se modificó ni creó ningún fichero, no se calculó el vintage nuevo y el
worktree quedó limpio. El worktree se retiró; la rama `feat/universe-vintage`
sigue apuntando a `1c76add`.

### Cómo retomarla

1. Desde el repositorio principal: `git checkout feat/universe-vintage`
   (o rehacerla desde el HEAD de `fix/exchange-calendars` una vez esa entrega
   esté aceptada, para no arrastrar un `universe.yaml` desactualizado).
2. Ejecutarla **después** de T-003, no en paralelo: con Codex las fichas
   simultáneas se serializan porque no admite worktrees.
3. Cambios respecto a la ficha original, ya sabidos:
   - T-002 dejó en `advisor/run/manifest.py` un `universe_vintage_id`
     provisional (hash de la lista de símbolos analizables) que hay que
     sustituir por la definición canónica de esta ficha, preferiblemente en
     `advisor/universe/vintage.py` con un import desde el manifiesto.
   - El vintage de las pasadas ya persistidas,
     `80d05f21abad212757d2f06d9f2dd53032b92a342dba90904b3086ea970d0b59`,
     cambia por definición nueva: hay que anotarlo en el decision log y en la
     evidencia, y dejar claro que las pasadas anteriores llevan el provisional.
   - `added_at` sale de `git log --diff-filter=A -S'primary_symbol: <SYM>'
     --format=%ad --date=short -- universe.yaml`; los 126 instrumentos deben
     caer entre `93009da` (2026-08-27) y `e952f71` (2026-08-29).
   - T-003 ya usa `exchange_calendars` y deriva la plaza de `primary_market`;
     si T-003 no llegó a añadir `exchange_calendar`/`exchange_timezone` al
     YAML, esta ficha es un buen sitio para hacerlo junto con el resto de
     campos de identidad.

### Comprobación del entorno del 2026-09-17, antes de encargarla

Lo que sigue está **medido hoy sobre `refactor/data-quality-codes`**, no
supuesto. Sustituye a lo que dice el punto 3 del apartado anterior donde se
contradigan.

**Sigue siendo cierto:** no existe `advisor/universe/vintage.py`; el
provisional vive en `advisor/run/manifest.py:75` y es
`canonical_hash({"analizables": [symbol…]})`; el universo tiene 126
instrumentos y 107 analizables; los 18 ISIN siguen sin fuente; los 126 están
en `trade_republic: unknown`; el vintage provisional sigue valiendo
`80d05f21…` y es el que imprime el pie del informe; `data/vintages/` entero
está ignorado y el `manifest.json` de la cosecha `071ddb2b…` ocupa 88 KB; no
existe subcomando `universo`.

**Corrección 1 — el método de `added_at` de la ficha no funciona.** Falla de
tres maneras distintas, las tres reproducidas:

1. `--diff-filter=A` combinado con `-S` no devuelve **nada** para ningún
   símbolo: el filtro se aplica a si el fichero se añadió en ese commit, no a
   la cadena buscada, así que solo sobrevive el commit inicial y en él la
   cadena no existe todavía.
2. Sin ese filtro, `-S'primary_symbol: <SYM>,'` atribuye 122 de 126 activos a
   `e952f71` y no encuentra los otros 4 (`IS3N.DE`, `VVSM.DE`, `4GLD.DE`,
   `510300.SS`), que están escritos en formato de bloque y no llevan la coma.
3. Buscando el símbolo suelto aparecen falsos positivos por subcadena: `GS`
   dentro de `^GSPC`, `^STOXX` dentro de `^STOXX50E`, y `V` dentro de
   cualquier cosa.

La causa de fondo: **`universe.yaml` solo lo tocan tres commits**, y el del
27/08 usaba otro esquema. `93009da` (2026-08-27) tiene **28 entradas con la
clave `symbol:`**; `e952f71` (2026-08-29) reescribe el fichero entero a 126
entradas con `primary_symbol:`. Por eso cualquier `git log -S` sobre
`primary_symbol:` fecha el 29/08 incluso a los activos que ya existían el 27.

**Método que sí vale, y su resultado ya calculado:** cargar el YAML de cada
una de las tres versiones (`git show <commit>:universe.yaml`), extraer el
conjunto de símbolos de cada una y comparar conjuntos. Da:

    added_at = 2026-08-27 -> 20 activos
    added_at = 2026-08-29 -> 106 activos

Los 20 del 27/08 son: `4GLD.DE ALV.DE ASML.AS BTC-EUR EQQQ.DE ETH-EUR
EUNH.DE EUNL.DE IS3N.DE MBG.DE MC.PA SAP.DE SIE.DE ^GDAXI ^GSPC ^HSI ^N225
^NDX ^STOXX50E ^VIX`. Codex debe **reproducir** este reparto con su propio
script y contrastarlo contra estos números, no copiarlos.

**DECISIÓN PENDIENTE (metodológica, no la resuelve Codex): los ocho
renombrados.** Ocho símbolos del 27/08 no están hoy, porque el universo
inicial usaba el listado alemán y `e952f71` pasó al primario:

    4AB.DE  ABEA.DE  AMZ.DE  APC.DE  FB2A.DE  MSF.DE  NVD.DE  TL0.DE

Si `AAPL` es la continuación de `APC.DE`, su `added_at` es 2026-08-27 y
`ticker_history` debe recogerlo; si es un listing distinto del mismo emisor
—que es lo que dice el propio diseño de la ficha, donde `instrument_id` es
`primary_symbol@primary_market` y solo `issuer_id` los une—, su `added_at` es
2026-08-29 y `ticker_history` queda vacío. La elección cambia qué universo
declara cada resultado y cuánta antigüedad se le puede reclamar.

**Resuelta el 2026-09-17 con revisión independiente (Codex): son listings
distintos.** `added_at: 2026-08-29` para el símbolo primario, `ticker_history`
vacío, y la única unión con el alemán es `issuer_id`. El argumento que la cierra
no es de estilo: pasar de `APC.DE` a `AAPL` cambia mercado, calendario, divisa,
fuente de barras, huecos y ejecutabilidad, así que para el backtest y para la
frescura **no es un renombrado**. `ticker_history` queda reservado para la
continuidad del mismo listing bajo otro ticker.

**Consecuencia que hay que respetar al publicar resultados:** se puede afirmar
que el emisor Apple estaba considerado desde el 2026-08-27, pero la serie
`AAPL` sobre su mercado primario entra en el universo medido el 2026-08-29, y
ningún resultado sobre `AAPL` puede reclamar la antigüedad del 27. El sesgo que
esto introduce es conservador, que es el lado correcto para un campo cuyo
propósito es acotar el sesgo de selección.

**Corrección 2 — no añadir `exchange_calendar` ni `exchange_timezone` al
YAML.** La sugerencia del apartado anterior ya no aplica: T-003 y T-004
dejaron la plaza resuelta en código, en `MARKET_SESSIONS` de
`advisor/data/sessions.py` (zona horaria, hora de cierre y MIC por mercado) y
`MARKET_TO_MIC` en `advisor/data/calendars.py`, más
`exchange_overrides.yaml` para los cierres que `exchange_calendars` no
codifica. Duplicar eso en `universe.yaml` crearía una segunda fuente de verdad
para el mismo dato y rompería INV-06. Queda fuera de alcance.
