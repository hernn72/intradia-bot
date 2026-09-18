# Revisión independiente de T-009 — 2026-09-18

Revisor: Opus (supervisión). Implementación: Codex.
Rama: `feat/execution-filter-study`. Base: `6fbeed0`.

**VEREDICTO: CORREGIR** → corregido. 1 defecto de publicación, 1 bloqueo
levantado con una prueba que la entrega no podía producir, 2 hallazgos que
salen con ficha propia. La entrega llegó declarada **BLOQUEADA** por su autor,
y ese juicio era correcto: lo que estaba mal era el criterio, no la entrega.

---

## 1. El bloqueo era correcto y el criterio era mío

Codex se negó a certificar «el backtest por defecto no cambia ni una
operación» porque `antes.txt` y `despues.txt` no coincidían. Hizo bien en no
maquillarlo. Pero la causa no es su cambio: **el backtest en vivo no es
reproducible**. Tres ejecuciones, el mismo commit `6fbeed0`:

| Ejecución | Código | Hora | Operaciones | COMPRAR | ESPERAR | DESCARTAR |
|---|---|---|---:|---:|---:|---:|
| `antes.txt` | antes del cambio | 10:08 | 891 | 474 | 2310 | 7570 |
| `despues.txt` | después | 10:56 | 893 | 478 | 2298 | 7567 |
| `backtest_repetido_post.txt` | **el mismo de la anterior** | 11:00 | 890 | 474 | 2306 | 7569 |

Dos pasadas del **mismo código**, separadas por cuatro minutos, difieren en 3
operaciones. La diferencia atribuible al cambio (+2) es menor que el ruido
(−3): la comparación no tiene ningún poder discriminante. El criterio que
escribí en la ficha —«Confirmarlo ejecutándolo»— **era inverificable por
construcción**, porque `backtest --period 5y` descarga datos en vivo. Error de
la ficha, no de la entrega.

**La prueba que sí responde a la pregunta.** Se ejecuta el mismo código de
`main` y el del árbol sobre una serie sintética determinista (semilla fija, 900
velas), en los dos horizontes y las dos políticas, y se comparan las
operaciones una a una:

    git worktree add /tmp/intradia-main main
    # mismo script, mismo venv, PYTHONPATH a cada arbol
    diff /tmp/backtest-main.json /tmp/backtest-t009.json
    → IDENTICO byte a byte   (10.948 bytes, 134 operaciones)

    operaciones por poblacion: todas-swing 69 · todas-medio 65 · operar-* 0

**Cero cambios en el backtest por defecto, demostrado.** Salvedad honesta: la
población `operar` sale vacía en esa serie —ninguna señal llega a `COMPRAR`—,
así que la prueba cubre 134 operaciones de la población `todas` y no ejercita
la ruta `POLICY_OPERAR`. Es, aun así, la única prueba determinista disponible
hoy, y es infinitamente mejor que comparar dos descargas distintas.

Se levanta el bloqueo y **se corrige el criterio de la ficha**.

---

## 2. Defecto corregido — se publicaba un centinela como si fuera un intervalo

El tramo `80+` salía así:

    | 80+ | EJECUTADAS | 28 | OK | ... | 0.4391 | [0.0000, 1.0000] | ...

`[0.0000, 1.0000]` no es un intervalo calculado: es el **centinela** que
`bootstrap_block_mean_interval` devuelve cuando hay menos de dos bloques
(`advisor/research/bootstrap.py:100`, `if len(values) < 2: return 0.0, 1.0`).
En unidades de R se lee como «la expectancy está entre 0 y 1 R», que es una
afirmación fuerte y falsa; y la fila iba etiquetada `OK`.

Contradice el pre-registro de la propia ficha —una celda sin muestra se declara
insuficiente, no se publica— y el principio del roadmap de que NO CONCLUYENTE
es un resultado válido que hay que decir.

**Corrección.** `_block_expectancy` devuelve `None` cuando hay menos de dos
bloques, y la fila imprime `SIN INTERVALO` y `N/D (menos de 2 bloques)`.
Regenerada la medición y rehechos los hashes. Test de regresión
`test_una_celda_con_un_solo_bloque_no_publica_intervalo`, que falla contra el
código sin corregir:

    FAILED tests/test_execution_filter.py::test_una_celda_con_un_solo_bloque_no_publica_intervalo

Tras la corrección, el tramo 80+ dice lo que hay:

    | 80+ | EJECUTADAS | 28 | SIN INTERVALO | ... | 0.4391 | N/D (menos de 2 bloques) | ...

---

## 3. Lo que la medición dice, que es el objeto de la ficha

Sobre la cosecha `071ddb2b…`, horizonte swing (el de medio va en la misma
dirección):

| Población | n | expectancy por bloque | IC95 |
|---|---:|---:|---|
| TODAS_SCORE (banda 70-80) | 1812 | 0,1550 R | [0,0080, 0,3062] |
| EJECUTADAS | 966 | 0,2111 R | [0,0414, 0,4002] |
| PERDIDAS_POR_ENTRADA | 846 | 0,1221 R | [−0,0008, 0,2309] |

Lectura honesta: **el filtro de ejecución parece proteger, no solo costar**. Lo
ejecutado rinde más que lo rechazado (0,21 vs 0,12 R) y lo rechazado no se
distingue de cero. Pero los intervalos se solapan de sobra, así que lo que se
puede afirmar es «compatible con que el filtro ayude», no «el filtro ayuda».

Un detalle que explica el mecanismo: las señales perdidas **aciertan más veces**
(472 de 846, 56 %) y ganan menos por acierto (payoff 1,01 frente a 1,77). Es
exactamente lo que produce perseguir un hueco al alza: entras más caro, y tu R
se comprime. Ese es el argumento económico a favor de la disciplina de D-06, y
hasta hoy no estaba medido.

**Coste del filtro, en volumen:** 1.189 señales perdidas frente a 994
ejecutadas en swing; 962 frente a 792 en medio. El filtro rechaza **más de la
mitad** de lo que el score aprueba.

---

## 4. D-29 queda respondida con datos, y la respuesta es contundente

De las 1.189 señales perdidas en swing y las 962 en medio:

    ABOVE_MAX_ENTRY   1146/1189  (96,4 %)      926/962  (96,3 %)
    INVALID_STOP        31/1189                 25/962
    INVALID_TARGET      12/1189                 11/962
    RR_TOO_LOW           0/1189                  0/962

**`RR_TOO_LOW` es inalcanzable: 0 de 2.151 señales.** Confirma lo que la
revisión de T-008 sospechaba por lectura del código: con `entry_max` definido
como la rotura del RR, ningún precio que respete la máxima puede incumplir el
ratio. Los dos códigos no reparten un espacio: uno de ellos está muerto.

Esto es lo que D-29 necesitaba para decidirse, y ahora puede decidirse: o
`ABOVE_MAX_ENTRY` absorbe el caso —como está hoy, y como dice D-06— y
`RR_TOO_LOW` se retira del vocabulario de ejecución por inalcanzable, o se
invierte el orden y el muerto es el otro. **Sigue siendo decisión, no defecto**,
y no se toma en una revisión: se lleva a T-010 con estos números delante.

---

## 5. Dos hallazgos que salen con ficha propia

**T-015 — el backtest en vivo no es reproducible.** Medido arriba: tres
ejecuciones del mismo commit, tres resultados. Afecta a cualquier cifra
publicada con `backtest --period Ny`, incluida la línea base de la línea 0 en
`evidence/2026-09-14-L0-baseline/`. El laboratorio tiene cosecha congelada
justo para esto; el comando de backtest no la usa.

**T-016 — el centinela `(0.0, 1.0)` también lo consume `capacity.py`.**
`advisor/research/capacity.py:534` llama a la misma función. Es decir, el gate
de capacidad estadística de P2.5 **puede estar publicando ese mismo intervalo
falso**, y GATE P2 depende de él. Aquí se corrige el consumidor de T-009; la
raíz y el otro consumidor necesitan su propia entrega, **antes de A-02**.

---

## 6. Lo que la entrega hace bien

- **INV-06 respetada de verdad**: el contrafactual reutiliza `simulate_asset`
  con `entry_discipline=ENTRY_OPEN_AT_OPEN`; no hay copia del motor.
- **El defecto inyectado esta vez es una ejecución real**, no una afirmación:
  `defecto_inyectado_registro_rechazo.txt` contiene la salida de pytest
  fallando contra el código sin el cambio. Es la corrección del reproche que se
  le hizo en T-008, aplicada en la entrega siguiente.
- **El pre-registro está copiado tal cual** en la evidencia, antes de medir.
- **No decidió D-29** pese a tener los números que la resuelven, porque la
  ficha se lo prohibía. Eso es exactamente lo que se le pidió.
- **Punto 5 cumplido y medido**: la población broker-neutral suma 85 señales en
  swing y 74 en medio, las que el estado `no` del broker sacaba del laboratorio.
- Arregló de paso el vintage ausente de `capacidad-estadistica` y la cabecera
  de `docs/protocolo-investigacion.md`, dos hallazgos abiertos del roadmap.

---

## Verificación final tras las correcciones

    python -m pytest -q     541 pasan
    ruff check .            limpio
    mypy advisor            limpio, 62 ficheros
    filtro-ejecucion swing y medio regenerados, hashes rehechos
