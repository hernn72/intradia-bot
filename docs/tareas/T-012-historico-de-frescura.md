# T-012 — Interpretar el histórico de frescura de la Pi (A-01)

Estado: ACEPTADA (2026-09-20) — OD-02 cerrada con su cifra en D-40
Agente: Opus (ficha y lectura) → Codex (agregación) → propietario (OD-02, OD-01)
Línea / fase: Línea A, A-01
Gate al que contribuye: ninguno directamente; **produce la cifra con la que se
deciden OD-02 y, desde D-39, OD-01**

## Objetivo
Convertir las pasadas guardadas en la Pi en tres números que hoy no existen:
cada cuánto falta el dato, **a qué hora** y **a qué activos**. Con ellos, el
propietario decide si paga una segunda fuente para Europa (OD-02), si mueve el
horario de las pasadas (OD-09) y qué hace con cripto (OD-10).

## Por qué existe
Las tres decisiones abiertas se están tomando con intuición y con muestras
pequeñas medidas de pasada:

- OD-02 fija un umbral —«> 2 sesiones perdidas por mes en más de 10 activos»—
  **que nadie ha medido todavía**.
- OD-09 se apoya en 21 pasadas medidas el 2026-09-16 (96–100 % de retraso
  europeo a las 06:02 y 07:32 UTC, 38 % a las 13:32, 0 % a las 20:02). Es la
  dirección correcta, pero son 21 pasadas y dos semanas.
- OD-10 se apoya en el razonamiento de que la sesión 24/7 solo cierra a las
  00:00 UTC, no en el recuento de cuántas veces la barra de cripto llegó
  parcial y a qué hora.

La Pi acumula histórico persistido de frescura **desde el 2026-09-02**
(`frescura-historico`). Esta ficha lo lee y lo publica.

## Pregunta, métrica y criterio — PRE-REGISTRO
Se escribe antes de mirar los datos. Lo que se decida después de verlos se
etiqueta `exploratorio`.

- **Pregunta primaria:** ¿con qué frecuencia el dato que ve el asesor está
  retrasado o ausente, desglosado por plaza y por hora de pasada?
- **Métrica primaria:** para cada par (plaza, hora de pasada), el **porcentaje
  de mediciones con retraso ≥ 1 sesión**, con su intervalo de confianza y su
  denominador. El denominador se publica siempre: un 100 % sobre 4 mediciones
  no es lo mismo que sobre 400.
- **Métricas secundarias:** sesiones ausentes por activo y por mes (la cifra
  del umbral de OD-02); racha máxima de sesiones consecutivas ausentes por
  activo; porcentaje de barras parciales por activo (la cifra de OD-10);
  distribución por día de la semana (la sospecha del lunes); y cuántas
  ausencias coinciden con un `exchange_overrides.yaml` ya registrado —esas no
  son huecos, son cierres reales.
- **Población:** todas las mediciones persistidas en la Pi desde el
  2026-09-02 hasta la fecha de ejecución, los 107 analizables. Se declara el
  número exacto de pasadas y de mediciones.
- **Criterio de decisión de OD-02, fijado antes de medir:** el umbral ya
  propuesto —más de 2 sesiones perdidas por mes en más de 10 activos— se
  evalúa tal cual. Si sale por encima, OD-02 se reabre con la cifra; si sale
  por debajo, se cierra como «no procede por ahora» con la cifra. **Este
  informe no decide**: prepara la decisión.
- **Tratamiento de la incertidumbre:** intervalo binomial por celda. Una
  celda con menos de 30 mediciones se publica como insuficiente y **no** se
  agrega con otra para alcanzar el mínimo.
- **Sesgo conocido que hay que declarar:** el histórico empieza el
  2026-09-02, cubre pocas semanas y **no** incluye ningún periodo de
  vacaciones ni cierres largos. Cualquier tasa mensual extrapolada de aquí es
  provisional y se etiqueta como tal.

## Dependencias previas
Acceso a la Pi (`ssh -i ~/.ssh/id_ed25519_rpi_bot fer@192.168.1.113`). No
depende de GATE L0. Sí conviene hacerla **después** de T-007, porque el
estado de plaza permite separar «no hay barra porque la plaza está cerrada»
de «no hay barra y debería haberla».

## Archivos probables
- `advisor/main.py` — `cmd_frescura_historico`, ya existe: se **amplía** con
  la agregación, no se escribe un comando paralelo.
- `advisor/storage/` — la tabla que persiste las mediciones; leer su esquema
  real antes de escribir nada (`sqlite3 intradia.db ".schema"`).
- `advisor/data/` — `calcular_frescura_dato` y la clasificación de calidad.
- `exchange_overrides.yaml` — los cierres reales ya registrados, que hay que
  descontar de las ausencias.

## Invariantes que no pueden romperse
INV-05 (la plaza sale de `primary_market`), INV-16 (una celda sin datos se
declara vacía, nunca 0 %), INV-06 (la clasificación de frescura es la misma
que usa producción; no se reimplementa para el informe).

Revisión Codex 2026-09-20:
- INV-05: ejercitada en el resumen por plaza usando la plaza persistida desde
  el universo; no se cambió el contrato de universo.
- INV-16: protegida por
  `tests/test_freshness_history.py::test_celda_sin_mediciones_se_declara_vacia_y_no_cero`.
- INV-06: el resumen consume `sessions_approx`,
  `may_be_partial_current_session` y ausencias ya persistidas por la medición
  de frescura; no reclasifica la calidad del dato.

## Implementación requerida

1. **Traer el histórico de la Pi al portátil sin tocar la base de la Pi.**
   Copia de solo lectura (`scp` del fichero de base o export a CSV desde la
   Pi), registrada en la evidencia con su instante y su tamaño. **No** se
   ejecuta nada que escriba en la base de producción.

2. **Agregación**, como subcomando o argumento de `frescura-historico`:
   `frescura-historico --resumen` que publique, en tablas:
   - (plaza × hora de pasada): mediciones, % con retraso ≥ 1 sesión, IC;
   - (activo × mes): sesiones ausentes, descontando las de
     `exchange_overrides.yaml`, y racha máxima;
   - (activo): % de barras parciales;
   - (día de la semana): % con retraso.

   Todo con denominador visible. Nada de porcentajes sin `n`.

3. **Responder al umbral de OD-02 con una sola línea**, calculada por el
   código y no a ojo: «N activos superan las 2 sesiones perdidas por mes;
   el umbral es 10». Esa línea es el entregable que el propietario lee.

4. **Separar las tres causas**, que hoy se confunden: plaza cerrada (cierre
   real, con override o con calendario) · proveedor que no entregó con la
   plaza abierta · barra parcial por sesión aún en curso. Cada ausencia cae
   en una y solo una.

## Qué NO debe modificarse
Nada de producción: esta ficha **lee**. Si al leer aparece un defecto en cómo
se persiste la frescura, se clasifica (BLOCKER / FOLLOW_UP) y se decide
aparte; no se arregla dentro de una tarea de medición.

## Tests unitarios
- `test_resumen_no_agrega_celdas_con_muestra_insuficiente`.
- `test_ausencia_con_override_no_cuenta_como_hueco`: fecha de KRX del
  2026-06-03, ya registrada como cierre real → no suma al recuento.
- `test_celda_sin_mediciones_se_declara_vacia_y_no_cero` (INV-16).
- `test_porcentaje_siempre_va_con_denominador`.
- `test_las_tres_causas_son_excluyentes`: una ausencia no puede contarse dos
  veces.

## Verificación contra datos reales
```bash
# en la Pi, solo lectura
ssh -i ~/.ssh/id_ed25519_rpi_bot fer@192.168.1.113 \
  "cd ~/intradia-bot && python -m advisor.main frescura-historico --resumen"
# y en el portátil, sobre la copia
.venv/bin/python -m advisor.main frescura-historico --resumen
```
Comprobar a mano: elegir **un** activo europeo y **una** hora de pasada,
contar sus mediciones retrasadas en la base con una consulta SQL directa y
comprobar que coincide con la celda de la tabla, denominador incluido.

## Medición del impacto
Ninguno sobre el comportamiento del bot. El impacto es informativo: OD-02 pasa
de no tener cifra a tenerla, y por D-39 esa misma cifra alimenta OD-01 si se
evalúa ampliar el plan de EODHD. OD-09 y OD-10 ya estaban cerradas por D-36 y
D-37; no se alimentan aquí.

**La cifra, corregida por el supervisor.** La primera entrega decía «50 activos
superan las 2 sesiones perdidas por mes» y era un artefacto: no deduplicaba, y
la misma sesión ausente reaparece en las 39 pasadas porque
`absent_reference_sessions` mira 200 sesiones atrás. Deduplicando, y según qué
se llame «sesión perdida» —que el pre-registro no fijó—:

| Lectura | Activos por encima | ¿Umbral de 10? |
|---|---:|---|
| (a) el hueco sigue ausente en la última pasada del activo | **0** (9 con algún hueco) | **NO** |
| (b) faltó en alguna pasada, aunque llegara después | 18 | sí |
| (c) lo anterior más las que solo llegaban con retraso | 47 | sí |

Elegir la lectura es del propietario. Con cualquiera de las tres, lo que el
informe sí afirma es que **el retraso es exclusivamente europeo**: 278 de 329
mediciones europeas retrasadas a las 06 UTC frente a **0 de 399** del resto del
mundo, y 0 de 327 en Europa a las 20 UTC.

Verificado contra la copia de la Pi:
- 4.143 mediciones, 39 pasadas, 107 símbolos.
- Ventana: 2026-09-02T17:24:51.715970+00:00 a
  2026-09-20T16:11:02.874968+00:00.
- Poblaciones declaradas: 107 analizables hasta el 2026-09-18 antes de D-31,
  103 tras D-31 y 93 tras D-35.
- Sesgo declarado en el informe: 18 días, sin vacaciones ni cierres largos; toda
  tasa mensual extrapolada va etiquetada como provisional.

## Criterio de aceptación
- Las cuatro tablas publicadas, con denominadores e intervalos.
- La línea de respuesta al umbral de OD-02, calculada por el código.
- Las tres causas separadas y excluyentes.
- El sesgo de ventana corta declarado en el informe, no solo en la ficha.
- `pytest`, `ruff`, `mypy` limpios.

## Criterio de rechazo
- Un porcentaje sin denominador.
- Agregar celdas pequeñas para alcanzar una muestra.
- Extrapolar una tasa mensual desde tres semanas sin etiquetarla provisional.
- Escribir en la base de la Pi.
- Tomar por el propietario cualquiera de las tres decisiones.

## Evidencia que debe quedar registrada
`evidence/<fecha>-T-012-frescura-historico/` con README.md, el pre-registro
copiado, el instante y tamaño de la copia traída de la Pi, las cuatro tablas,
la consulta SQL de la comprobación manual y su resultado.

Registrado en `evidence/2026-09-20-T-012-frescura-historico/`:
README.md, `antes.txt`, `despues.txt`, `validacion.txt`, las cuatro tablas,
`pre-registro.md`, `comprobacion-manual.sql` y
`comprobacion-manual-resultado.txt`.

## Commit esperado
Rama `feat/freshness-history-summary`. Mensaje:
`feat(frescura): resumen del historico persistido con denominadores y causas separadas`

## Actualización documental requerida
`docs/roadmap.md`: fila A-01 a EN_REVISION y luego ACEPTADA.
`docs/decision-log.md`: OD-02, OD-09 y OD-10 actualizadas **con la cifra**, y
marcadas explícitamente como «listas para decidir, pendientes del
propietario». Ninguna se cierra aquí.

Corrección aplicada el 2026-09-20: OD-09 y OD-10 ya estaban cerradas (D-36 y
D-37). No se actualizó `docs/decision-log.md` porque esta tarea no toma ni
cierra decisiones de propietario; la cifra queda en evidencia y alimenta OD-02
y OD-01 según D-39.

## Handoff al siguiente agente
Estado: EN_REVISION.

Hecho:
- Añadido `frescura-historico --resumen --db <ruta>` sobre el comando existente.
- La ruta `--db` se abre con `AdvisorDB(..., readonly=True)`, que usa URI SQLite
  `mode=ro` internamente.
- Publicadas las cuatro tablas con denominadores e IC cuando `n >= 30`; celdas
  sin mediciones salen como vacías y celdas con `n < 30` como insuficientes.
- Separadas causas excluyentes: plaza cerrada por calendario/override,
  proveedor con plaza abierta y barra parcial en curso.
- Por activo se declara `possible_passes`; si `valid_to` existe se usa, si no se
  deriva de la ventana observada en el histórico.

Verificado:
- Línea base antes de cambios: 595 pasan, ruff OK, mypy OK.
- Validación final: 600 pasan, ruff OK, mypy OK.
- Comando real:
  `.venv/bin/python -m advisor.main frescura-historico --resumen --db data/frescura-snapshot.db`.
- Comprobación manual: XETRA 06 UTC = 186 retrasadas / 217 mediciones por SQL
  directo, igual que el informe.

Impacto:
- OD-02 ya tiene cifra calculada por código: 50 activos superan las 2 sesiones
  perdidas por mes; el umbral es 10.
- Por D-39, esa cifra también informa si un eventual pago de EODHD cubre precios
  europeos y fundamentales point-in-time.

Hallazgos:
- OBSERVATION: `graphify-out/` ya estaba sin seguimiento al empezar y no se tocó.
- OBSERVATION: las ausencias históricas guardadas incluyen festivos de calendario
  base además de overrides; el resumen las clasifica como plaza cerrada y no como
  hueco de proveedor.

Decisiones pendientes:
- Propietario: OD-02, decidir con la cifra publicada si procede segunda fuente y
  si sería global, por plaza o por ticker.
- Propietario: OD-01, decidir junto con OD-02 si se amplía el plan de EODHD y si
  un mismo plan cubre precios EOD y fundamentales point-in-time.

Siguiente paso: revisión independiente de T-012; si se acepta, propietario decide
OD-02/OD-01 con la evidencia.

## Revisión del supervisor — 2026-09-20

**Veredicto: CORREGIR, corregido.** La entrega de Codex llegó con 600 tests en
verde, `ruff` y `mypy` limpios, y el defecto estaba en la única línea que el
propietario iba a leer.

- **BLOCKER — no deduplicaba las ausencias.** Sumaba `provider_missing` una vez
  por pasada, así que un hueco contaba 39 veces, y extrapolaba a «por mes»
  fechas de marzo vistas desde septiembre. Corregido: las ausencias se acumulan
  como conjuntos de fechas, cada una se atribuye al mes **de su sesión**, y las
  anteriores a la ventana se publican en su propia tabla. Test de regresión:
  `test_una_ausencia_repetida_en_varias_pasadas_cuenta_una_vez`, que falla
  contra el código sin corregir.
- **SAME_SCOPE — «sesión perdida» no estaba definida.** Se publican las tres
  lecturas en vez de elegir una, porque elegirla es decisión del propietario.
- **FUERA DE FICHA, añadido por el supervisor — la ventana cruza 14 versiones de
  código**, y solo una pasada usa la regla vigente de D-36 y D-37. Agregar 18
  días en una sola tasa mezclaba dos definiciones de la métrica primaria. El
  resumen lo declara en una tabla y con un aviso; `get_all_freshness_measurements`
  trae ahora `git_sha` y `release_tag` del manifiesto.
- **OBSERVATION** — 1.177 mediciones (11 pasadas) son anteriores a C-02 y no
  tienen manifiesto: de esas no se puede saber con qué código se tomaron.

Verificado a mano y sin usar el código del resumen: XETRA 06 UTC = 186/217, y
las tres lecturas de OD-02 recalculadas por SQL directo antes de escribir el
arreglo.

## Handoff al siguiente agente

La ficha queda EN_REVISION a la espera del propietario, que tiene que elegir
qué lectura de «sesión perdida» vale para OD-02. Lo siguiente en la cola no
depende de esto: **T-013 (A-02)**.

Si alguien retoma T-012: `--resumen` no está en la Pi todavía, porque produccion
corre el tag `v0.3.0` y el comando entró después; llegará con el próximo
release. La copia de la Pi se rehace con el API de backup de SQLite, nunca
copiando el fichero vivo.

## Cierre — 2026-09-20

**ACEPTADA.** El propietario eligió la lectura (c) y cerró OD-02 en D-40: hace
falta respaldo del EOD europeo, solo para Europa. Antes de cerrar pidió descartar
el efecto fin de semana, y se descartó midiendo: **no hay ninguna pasada de fin
de semana a las 06 UTC**, las siete son laborables, y el patrón se repite martes,
miércoles, jueves y viernes entre el 97,9 % y el 100 %.

El lunes (0 %) no es una excepción sino la confirmación: ese día la sesión
exigible es la del viernes, ya consolidada. Y el mecanismo real, verificado
siguiendo `SAP.DE` pasada a pasada, es que **el proveedor retira por la noche una
barra que ya había servido**. Todo en D-40.
