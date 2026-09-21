# T-013 (A-02) — el laboratorio rehecho sobre `071ddb2b…`

Fecha: 2026-09-21. Rama `feat/a02-laboratorio-rehecho`, partiendo de `main`
en `d7ddf59`.

Esta carpeta contiene la evidencia de la tarea que cruza **GATE P2**.

## Los siete requisitos de GATE P2, uno a uno

**1. GATE L0 cruzado.** Si, el 2026-09-18 (D-30), evidencia en
`evidence/2026-09-18-L0-cierre/`. No se toca aqui.

**2. Cosecha fijada.** `071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841`,
sin cambiarla. Verificada integra el mismo dia con `load_vintage`: hash de
manifiesto valido, `series_hash` y `corporate_actions_hash` correctos en los 126
activos, 126 series declaradas y 126 en disco, 0 fallidas. Existe ademas una
copia local verificable fuera del repositorio.

**3. `universe_vintage_id` calculado y registrado.** Los tres, y los tres
reproducen exactamente los del decision log:

    vigente  93 activos   237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19
    d31     103 activos   c8496446d9b04795b8533e25e794c6141a4e73db73c0ef9bf98599b70f952132
    pre-d31 107 activos   894ce776ff8572b3a9dfc97a724f96789122e0dd2c46eef55045d4968e0b5fb0

Reponer una baja exige anular tambien su `valid_to`; sin eso sale
`d75368d6…e36c0e`, que no corresponde a nada, y hay un test que lo fija.
El hash vigente **no se ha movido**: su test sigue en verde sin tocarlo.

**4. P2.3 y P2.4 rehechos una sola vez**, con fortaleza relativa alineada y la
geometria de la linea 0, publicando antes y despues: ver `antes.md` y
`despues.md`. El primario —media por bloque de la expectancy neta en R—
encabeza, con intervalo, **por banda, por region y por activo**; las secundarias
se publican con el y nunca solas. MAE y MFE van por banda, con el modo potencial
sin objetivo separado.

**5. P2.5 reejecutado** sobre el resultado nuevo, con `experimental_resolution`
publicada por corte, el numero de bloques, el minimo de observaciones por bloque
y la tasa de censura `EXIT_FINAL`.

**6. Decision formal sobre el RR.** No se toma aqui: se abre **OD-11** en
`docs/decision-log.md` con los numeros nuevos. La ficha prohibe expresamente que
la tome el implementador.

**7. Hashes de las tablas registrados.** En `hashes-de-tablas.txt`.

## Lo que hay que leer primero

`despues.md`. Tres cosas que cambian como se lee todo lo demas:

1. **El control principal pasa exacto**: `pre-d31` devuelve 121.786 señales, la
   cifra de agosto. Solo 194 de ellas (0,16 %) cambian de banda. Toda la
   diferencia con las cifras vigentes es **de poblacion**, no de metodo.
2. **El veredicto global empeora al usar el estimador correcto**: de `LIMITADA`
   / `MEDIUM` con la tasa TARGET_FIRST a **`INSUFICIENTE` / `LOW`** con el
   primario de INV-14. El disenno tenia menos resolucion de la que aparentaba.
3. **Ninguna banda es concluyente**, y el IC95 del primario cruza el cero en
   todas menos en `<50`, que es la banda mas baja del score.

## Ficheros

| Fichero | Que es |
|---|---|
| `antes.md` | copia literal de `docs/pendientes.md` §11, §14 y §15 (no modificados) |
| `despues.md` | el resultado nuevo y la atribucion por causa |
| `baseline-*.txt` | linea base antes de tocar codigo |
| `event-study-{vigente,d31,pre-d31}-{swing,medio}.txt` | P2.3, seis pasadas |
| `ablacion-score-vigente-{swing,medio}.txt` | P2.4 |
| `capacidad-estadistica-vigente-{swing,medio}.txt` | P2.5 |
| `produccion-backtest-RAMA.txt` | prueba de que produccion no se mueve |
| `defectos-inyectados.txt` | los cuatro defectos inyectados y los tests fallando |
| `hashes-de-tablas.txt` | GATE P2 punto 7 |
| `final-pytest-ruff-mypy.txt` | verificacion final |
| `analizar-*.txt` | pasada de produccion (ver limitacion abajo) |

## Produccion no se mueve, y esta probado de forma determinista

Comparar dos pasadas de `analizar` en vivo no prueba nada: los precios se mueven
entre ejecuciones. Se uso la via determinista que dejo T-015: `backtest
--vintage` recorre `classify()` y el score de produccion sobre la cosecha
congelada y es reproducible byte a byte.

Ejecutado en `main` y en la rama, la salida es **identica** salvo la marca de
tiempo del log. Sin ella, las dos dan el mismo SHA-256
`49b12c855c2d2681d9ecd0f592248cd03b11cd8428273014238e04f0ddefbc3c`, con 866
operaciones, que es la cifra que D-34 registro.

## Los cuatro defectos inyectados

Ninguna invariante se acepta sin ver fallar su test. Salida completa en
`defectos-inyectados.txt`:

1. `baja_decision` colado en `universe_vintage_payload` → caen los dos tests de
   hash del universo.
2. Reponer sin anular `valid_to` → el hash de `d31` deja de coincidir.
3. El primario calculado con la tasa TARGET_FIRST en vez de `net_r_multiple` →
   el test da 1.0 donde espera 0.200. **Es exactamente el error historico.**
4. El veredicto NO CONCLUYENTE comiendose el intervalo y los bloques → la fila
   se queda sin intervalo.

## Limitacion declarada

La pasada de `analizar` guardada aqui se ejecuto en un entorno **sin DNS**, asi
que degrada todos los simbolos por fallo de red. **No sirve como comprobacion**
y se conserva solo por trazabilidad. La comprobacion valida de que produccion no
se mueve es la determinista de mas arriba.
