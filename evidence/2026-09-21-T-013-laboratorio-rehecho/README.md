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

**3. `universe_vintage_id` calculado y registrado, con la declaración de sesgo
copiada.** La declaración de sesgo está en
`declaracion-de-sesgo-del-universo.md`, copia literal de la sección «Universo:
sesgo de supervivencia y de selección» de `docs/roadmap.md`, que **no se ha
modificado**. Los tres identificadores reproducen exactamente los del decision
log:

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

**6. Decision formal sobre el RR.** **CUMPLIDO.** Se abrio como **OD-11** con
los numeros nuevos y la cerro el propietario el 2026-09-21 en **D-43**: el RR
sale del score como dimension de puntuacion y **sigue siendo condicion de
ejecutabilidad y de riesgo**. La conclusion se limita a su funcion como
dimension del score medida en P2.4, no se ensancha a «el RR no sirve».

**Con este requisito, GATE P2 queda CRUZADO el 2026-09-21.**

**7. Hashes de las tablas registrados.** En `hashes-de-tablas.txt`.

## Lo que hay que leer primero

`despues.md`. Tres cosas que cambian como se lee todo lo demas:

1. **El control principal pasa exacto**: `pre-d31` devuelve 121.786 señales, la
   cifra de agosto, sobre la misma poblacion. Pero **la atribucion entre
   poblacion y correccion de RS no es observable**: de agosto solo quedan los
   agregados por banda, no la salida por señal. Las diferencias netas suman 194
   señales, lo que acota las migraciones reales en **[97, 10.228]**. Se declara
   que no se puede separar.
2. **El veredicto global empeora al usar el estimador correcto**: de `LIMITADA`
   / `MEDIUM` con la tasa TARGET_FIRST a **`INSUFICIENTE` / `LOW`** con el
   primario de INV-14. La medicion tenia menos resolucion de la que aparentaba,
   y el numero de bloques lo explica la **ventana de la cosecha**: 5 anos,
   ~1.302 sesiones, frente a las 2.430 que el protocolo pre-registro.
3. **Ninguna banda es concluyente**, y el IC95 del primario cruza el cero en
   todas menos en `<50`, que es la banda mas baja del score.

## Ficheros

| Fichero | Que es |
|---|---|
| `antes.md` | copia literal de `docs/pendientes.md` §11, §14 y §15 (no modificados) |
| `declaracion-de-sesgo-del-universo.md` | GATE P2 requisito 3, copia literal del roadmap |
| `follow-ups.md` | los nueve FOLLOW_UP abiertos, no corregidos aquí |
| `produccion-backtest-MAIN.txt` | la misma pasada sobre `main`, para comparar |
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

Las dos salidas estan comprometidas aqui: `produccion-backtest-MAIN.txt` y
`produccion-backtest-RAMA.txt`. Son **identicas** salvo la marca de tiempo del
log, y las dos declaran **866 operaciones**, la cifra que D-34 registro.

**Comando exacto de normalizacion y verificacion**, para que un tercero pueda
repetirlo:

    sed 's/^[0-9-]* [0-9:]* //' produccion-backtest-MAIN.txt | shasum -a 256
    sed 's/^[0-9-]* [0-9:]* //' produccion-backtest-RAMA.txt | shasum -a 256

Los dos devuelven:

    49b12c855c2d2681d9ecd0f592248cd03b11cd8428273014238e04f0ddefbc3c

El `sed` quita el prefijo `AAAA-MM-DD HH:MM:SS ` de la linea de log, que es lo
unico que difiere entre las dos ejecuciones. Sin normalizar, cada fichero tiene
su propio hash y ambos estan en `hashes-de-tablas.txt`.

Como se generaron: `git stash` de los cambios para dejar el arbol en `main`,
pasada, `git stash pop`, pasada. Un tercero puede reproducirlo extrayendo
`main` y `HEAD` a dos arboles limpios con `git archive`.

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
