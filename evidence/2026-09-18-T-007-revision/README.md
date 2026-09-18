# Revisión independiente de T-007 — 2026-09-18

Revisor: Opus (supervisión). Implementación: Codex.
Rama: `feat/market-state-and-broker`. Base: `3e677c3`.

**VEREDICTO: CORREGIR** → corregido y verificado. 1 BLOCKER, 1 defecto menor,
1 hallazgo heredado, 2 afirmaciones comprobadas.

---

## 1. BLOCKER — la acción nueva sacaba activos de la población del backtest

**Qué pasaba.** T-007 convierte `BROKER_UNVERIFIED` en la acción propia
`VERIFICAR_BROKER`. Pero `advisor/backtest/engine.py` construye la población de
`POLICY_OPERAR` filtrando `signal["accion"] == ACCION_COMPRAR`. Antes de T-007,
un activo sin verificar producía `COMPRAR` y entraba; después producía
`VERIFICAR_BROKER` y dejaba de entrar, **sin que nada lo declarase**.

Además, `advisor/backtest/report.py` agrupaba por
`(COMPRAR, ESPERAR, DESCARTAR)`: una operación `VERIFICAR_BROKER` no aparecía en
ninguna fila del informe, y la media de «lo vetado» la habría contado como veto.

**Por qué es BLOCKER y no una observación.** Hace que la población que mide el
laboratorio dependa de un metadato de broker que **cambia con cada tanda de
OA-03** —y con él, el `universe_vintage_id`—. Contradice D-04 («`unknown` no
degrada la señal») e INV-04 (señal y ejecutabilidad separadas), y contamina
A-02 / GATE P2, que va a rehacer P2.3 y P2.4 sobre esta población.

Es el mismo patrón del 2026-09-17, a menor escala: entonces fueron 107 activos
y cero operaciones; aquí son 2 activos y nadie lo habría notado.

**Reproducción (medida, no razonada).** Misma señal —score 85, mismos niveles,
mismo contexto benigno—, cambiando solo `trade_republic`:

    trade_republic=yes      radar=OPERAR    accion=COMPRAR           entra_en_POLICY_OPERAR=True
    trade_republic=unknown  radar=OPERAR    accion=VERIFICAR_BROKER  entra_en_POLICY_OPERAR=False
    trade_republic=no       radar=DESCARTAR accion=DESCARTAR         entra_en_POLICY_OPERAR=False

**Alcance real hoy:** 2 de los 107 analizables, `UCG.MI` y `1211.HK` — los dos
que faltan por comprobar en la app. Contados sobre `universe.yaml`: 95 `yes`,
10 `no`, 2 sin campo.

**Corrección.** `ACCIONES_OPERABLES = (ACCION_COMPRAR, ACCION_VERIFICAR_BROKER)`
en `engine.py`, fila propia en `report.py` y `VERIFICAR_BROKER` fuera del
cómputo de vetos. Tres tests de regresión en
`tests/test_backtest.py::TestPoblacionDeOperarYBroker`.

**Los tres fallan contra el código sin corregir**, comprobado reinyectando el
defecto y restaurando desde copia en `/tmp` (nunca con `git checkout --`, que
habría borrado las correcciones sin commitear):

    FAILED test_verificar_broker_sigue_entrando_en_la_poblacion_de_operar
    FAILED test_misma_senal_misma_poblacion_con_y_sin_broker_verificado
    FAILED test_el_informe_del_backtest_no_esconde_las_operaciones_sin_verificar

---

## 2. Defecto menor — `market_state` reventaba con un `datetime` sin zona

`market_state` hacía `pd.Timestamp(reference).tz_convert("UTC")`, que lanza
`TypeError` si `reference` no tiene zona horaria, mientras que
`trim_unclosed_bar` —en el mismo módulo— tolera ese caso vía `astimezone`.

    market_state naive       -> CRASH: TypeError Cannot convert tz-naive Timestamp
    trim_unclosed_bar naive  -> OK

En producción no muerde hoy: todos los llamantes pasan
`datetime.now(timezone.utc)`. Pero `market_state` se llama desde
`_price_reference_line`, dentro de la generación de cada ficha: un `TypeError`
ahí **mata el informe entero** en vez de degradar. Corregido usando
`local_reference`, que es la convención que ya sigue el módulo. Test:
`test_market_state_acepta_un_reference_sin_zona_horaria`, atado al contrato
(uno de los tres estados) y no a la zona horaria de la máquina, que en el CI
no es la misma que en el portátil.

---

## 3. FOLLOW_UP heredado — el broker ya contaminaba el laboratorio antes de T-007

Los 10 activos marcados `no` quedan fuera de `POLICY_OPERAR` desde PR 1, no
desde T-007. La población del laboratorio no debería depender del broker en
ningún caso. **No se corrige aquí** —sería rediseñar el laboratorio dentro de
una ficha que no lo pide—: se incorpora como requisito explícito de T-009, que
es justo la ficha que mide el filtro de ejecución aparte del score.

---

## 4. Dos afirmaciones de la entrega, comprobadas

**«La calidad cambió 57/31/19 → 60/28/19 por drift de datos reales.»**
Comprobado de forma determinista en vez de repetir pasadas: si el cambio fuera
del código, tendría que venir de `trim_unclosed_bar`. Comparando el cierre
viejo (hardcodeado) con el nuevo (calendario) el 2026-09-17 en las 15 plazas:

    plazas con cierre distinto el 2026-09-17: 0

Luego el cambio de calidad no puede venir del código. La atribución a drift se
sostiene.

**El ISIN de `EXH1.DE`.** Ya estaba escrito desde OA-03 (`DE000A0H08M3`,
verificado por el propietario en la app). Cruzado además contra la ficha del
emisor (BlackRock/iShares): iShares STOXX Europe 600 Oil & Gas UCITS ETF (DE),
ticker EXH1, domicilio Alemania. Coinciden nombre, plaza y país del prefijo.
Requisito 4 de GATE L0 cubierto.

---

## 5. Lo que la evidencia de Codex prueba menos de lo que parece

La pasada real solo generó **una** ficha de oportunidad. La métrica de GATE L0
«0 fichas con "Precio actual" cuando solo hay cierre» se apoya, en esta
evidencia, en esa única ficha:

    antes.txt:   "Precio actual" 1   ·  "Último cierre" 0
    despues.txt: "Precio actual" 0   ·  "Último cierre" 1

No es un defecto de la entrega —el cambio es correcto y hay tests—, pero la
métrica del gate necesita una pasada con más fichas. Se traslada a T-010, que
es la ficha que mide las seis métricas juntas.

---

## Verificación final tras las correcciones

    python -m pytest -q     517 pasan
    ruff check .            limpio
    mypy advisor            limpio, 61 ficheros

Línea base de referencia, en `3e677c3`: 502 tests. Entrega de Codex: 513.
Con los 4 tests de regresión de esta revisión: 517.
