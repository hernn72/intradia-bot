# D-21 reimplementado: la última barra cerrada exigible

Fecha: 2026-09-18
Rama: `feat/d21-barra-cerrada-exigible`, desde `main` en `3d0e611`
Decisiones que cierra: **OD-09 → D-36** y **OD-10 → D-37**

La regla, tal como la fijó el propietario:

> `latest_expected_closed_bar` = última barra cuyo cierre ≤ `analysis_timestamp`.
> Solo hay veto si falta esa barra. Cualquier barra posterior todavía abierta se
> ignora para indicadores, scoring, señales y backtest, pero no veta. Genérica
> para cualquier calendario, sin parche para cripto.

## Qué cambia respecto a lo que había

La frontera dejaba de ser el cierre de la plaza y era **«hoy»**:
`sessions_approx` salía de `closed_sessions_between(última barra, hoy)`, que
**excluye el día de referencia**. Consecuencia: una sesión que cerraba hoy nunca
contaba como exigible, por tarde que fuera.

Y cripto no entraba en el recorte: `trim_unclosed_bar` devolvía «sin sesión de
cierre» porque la plaza no tiene hora de cierre. La barra en curso se quedaba
dentro de la serie —los indicadores se calculaban con una vela a medias— y
`PARTIAL_BAR` le quitaba la ejecutabilidad. **Cripto no era recomendable nunca**:
no existe un instante en que su barra del día esté cerrada y siga siendo la
última.

Lo que lo hace genérico: una plaza 24/7 no tiene hora de cierre, pero **sus
barras diarias sí cierran**. La del día D cierra a las 00:00 UTC de D+1.

## Medición sobre el universo real

`main` (`3d0e611`) y la rama, ejecutadas **a la vez** a las 16:20 UTC sobre los
93 analizables (`01-antes-main.txt` y `02-despues.txt`):

| | antes | después |
|---|---|---|
| Calidad | `INCOMPLETO=41, OK=52` | `INCOMPLETO=41, DEGRADADO=9, OK=43` |
| Barra parcial declarada | `SOL-EUR`, `BTC-EUR`, `ETH-EUR` | ninguno |
| Última barra de cripto | 2026-09-18 (en curso) | 2026-09-17 (cerrada) |

**Los 9 nuevos DEGRADADO son los 6 japoneses y los 3 de Hong Kong**, todos con
`sessions_approx=1` y `execution_readiness=False`:

```
6501.T  6758.T  8035.T  6857.T  7203.T  7011.T  0700.HK  9988.HK  1810.HK
```

Su sesión del 18/09 cerró hace horas —Tokio a las 06:30 UTC, Hong Kong a las
08:00— y el proveedor no la ha publicado. **Comprobado contra el dato crudo**,
no deducido:

```
7203.T   últimas fechas: 2026-09-15, 2026-09-16, 2026-09-17
0700.HK  últimas fechas: 2026-09-15, 2026-09-16, 2026-09-17
SAP.DE   últimas fechas: 2026-09-15, 2026-09-16, 2026-09-18
AAPL     últimas fechas: 2026-09-16, 2026-09-17, 2026-09-18
```

Es un veto correcto: el dato que ya debería estar, no está. Antes pasaba
inadvertido porque la sesión de hoy no se contaba.

## El caso de las 21:00 con EE. UU.

Lo pidió el propietario expresamente. A las **21:00 BST (20:00 UTC)** Nueva York
cierra en ese mismo instante, así que su sesión de hoy **todavía no es exigible**
y no puede vetar; con la liquidación de 20 minutos pasa a serlo a las 20:20 UTC.
Es decir, la pasada de las 21:00 no veta a EE. UU. por la sesión que acaba de
cerrar. Fijado en
`tests/test_sessions.py::test_la_sesion_estadounidense_de_hoy_es_exigible_pasado_su_cierre`.

## Qué queda igual, a propósito

Si no se puede determinar la frontera —plaza sin calendario declarado— **no se
recorta y no se supone que el dato está al día**: se declara desconocido
(INV-16). El veto residual por `PARTIAL_BAR` sobrevive solo para ese caso, y hoy
no alcanza a ningún activo analizable.

`trim_unclosed_bar` sigue fallando ruidosamente con una plaza sin declarar; lo
que devuelve «no se sabe» es `latest_expected_closed_session`, que es quien
tiene que poder decirlo.

## La revisión de Codex encontró un BLOCKER, y era gordo

`trim_unclosed_bar` fechaba las barras en la zona de la plaza y la frescura las
fechaba **en UTC**. Dos formas de responder a la misma pregunta, con respuestas
distintas: una barra de la sesión XETRA del 18 llega estampada
`2026-09-17T22:00:00Z`, así que en UTC parece del 17. Con el veto midiéndose
ahora contra la última sesión cerrada exigible, ese día de diferencia **vetaba a
un activo que tenía su dato al día**. Reproducido antes de tocar nada:

```
recorta? False   (correcto: su sesión ya cerró)
last_bar_date  : 2026-09-17     <- mal fechada
exigible       : 2026-09-18
sessions_approx: 1              <- veto falso
```

**Y al medirlo salió que no era un caso raro, sino la norma.** En la cosecha
real, `SAP.DE` tiene **252 barras selladas en domingo UTC** y ninguna en viernes,
y `7203.T` 225: imposible si la fecha UTC fuera la de la sesión, y exactamente lo
que produce sellar a medianoche local. El fechado en UTC desplazaba un día
**todas** las barras europeas y asiáticas; lo que pasaba es que la regla vieja
—que excluía el día de referencia— lo tapaba.

Corregido con una sola función, `session_date_of(timestamp, market)`, que es
ahora la única forma de fechar una barra en el asesor (INV-06). Con test
integrado «recorta + frescura» para XETRA, JPX y HKG, y una guarda sobre el
universo real: la zona declarada de cada activo coincide con la de su plaza en
los 93.

Los otros hallazgos, también atendidos: el retroceso de `latest_expected_closed_session`
pasa de 15 a 45 días para que un cierre largo no devuelva «no se sabe» y caiga en
silencio a la semántica antigua; y se retiró un `monkeypatch` sin usar.

**Tras la corrección, la medición sobre el universo real no cambia**
(`03-despues-tras-revision.txt`): `DEGRADADO=9, INCOMPLETO=41, OK=43`. Era de
esperar —el proveedor sirve el diario en vivo **sin zona**, así que ahí no había
desplazamiento—, y confirma que los 9 vetos asiáticos son retraso real y no un
artefacto del fechado.
