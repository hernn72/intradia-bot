# T-013 — Rehacer P2.3, P2.4 y P2.5 una sola vez sobre `071ddb2b…` (A-02)

Estado: ACEPTADA
Agente: Opus (ficha) → Codex (implementación) → Opus (revisión) → propietario (OD-11)
Línea / fase: Línea A, A-02
Gate al que contribuye: **GATE P2** (es la tarea que lo cruza)

## Objetivo
Publicar P2.3, P2.4 y P2.5 rehechos **una sola vez** sobre la cosecha congelada
`071ddb2b…`, con la fortaleza relativa alineada, la geometría de la línea 0 y el
estimador pre-registrado como métrica principal, declarando las tres poblaciones
(107, 103, 93), de modo que los siete requisitos de GATE P2 queden satisfechos y
el propietario pueda decidir el RR en el score con números delante.

## Por qué existe
GATE L0 quedó cruzado el 2026-09-18 (D-30) y con él caducó lo que bloqueaba esta
tarea. Lo publicado hoy en `docs/pendientes.md` §11, §14 y §15 no se puede llevar
a GATE P2 tal cual, por cuatro motivos distintos y acumulativos:

1. **El instrumento que sostenía «el score ordena» no existía.** El intervalo de
   ±0,004 por banda no lo producía ningún código y trataba 121.786 señales
   solapadas de 107 activos correlacionados como ensayos independientes. La
   frase se retiró; no se sustituyó por nada.
2. **La fortaleza relativa estaba desalineada por zona horaria** en la cosecha
   (`docs/pendientes.md` §16). Se corrigió el 2026-09-02 en
   `relative_strength` y `relative_strength_series`, pero P2.3, P2.4 y P2.5 se
   midieron **antes** de esa corrección.
3. **La población cambió dos veces el 2026-09-18**: 107 → 103 (D-31) → 93
   (D-35). Todo lo publicado es sobre 107.
4. **La métrica principal nunca encabezó el resultado.** La tabla de §11 lidera
   con `P(objetivo antes de stop)`, que INV-14 declara **secundaria**; la
   primaria —media por bloque de la expectancy neta en R— aparece como una
   columna lateral sin intervalo.

Lo que T-016 sí despejó: la auditoría del 2026-09-18 midió **0 celdas afectadas**
por el centinela `(0.0, 1.0)` en el veredicto de P2.5, así que T-016 ya **no**
bloquea esta ficha (`evidence/2026-09-18-T-016-auditoria/`).

## Qué NO es esta ficha
No es P3. **No se recalibran umbrales**, no se cambian pesos, no se toca
`min_score_operar`, no se elige geometría y no se saca el RR del score. Esta
ficha **mide y publica**; la única decisión que abre es la del propietario sobre
el RR (OD-11), y la toma él, no el implementador. Si un resultado sale NO
CONCLUYENTE, se publica como tal: está prohibido ampliar la ventana, cambiar la
métrica, quitar activos o mover el bloque para que salga (`docs/metodo-trabajo.md`
§3, «…el resultado es NO CONCLUYENTE»).

## Dependencias previas
Todas cumplidas; no queda ninguna por esperar.
- **GATE L0 cruzado** (D-30), `evidence/2026-09-18-L0-cierre/`.
- **T-015 ACEPTADA** (D-34): el backtest ya es reproducible sobre cosecha.
- **T-016 auditada** (2026-09-18): 0 celdas afectadas, deja de bloquear.
- **Pre-registro del estimador del 2026-09-02** (INV-14), en
  `advisor/research/capacity.py::preregistered_estimators`.
- Decisiones que aplican: **D-17** (el RR sigue en el score hasta que esta
  ablación lo decida), **D-18** (se rehace una sola vez), **D-29** (cerrada:
  `RR_TOO_LOW` sigue existiendo como guarda de P4 aunque hoy sea inalcanzable),
  **D-31** y **D-35** (las tres poblaciones).

## Hechos verificados sobre el terreno el 2026-09-21
Comprobados ejecutando, no leídos. Quien implemente puede darlos por ciertos y
debe volver a comprobarlos si algo no cuadra.

- La cosecha existe y está completa: `data/vintages/071ddb2b…/manifest.json`,
  **126 series, 0 fallidas**, `created_at: 2026-08-30T09:41:38Z`. Los **93**
  analizables vigentes tienen serie en ella: faltan 0.
- `universe.yaml`: 126 activos, **93 analizables**, **14 con `valid_to`** (los 4
  de D-31 y los 10 de D-35) y **19 no analizables sin `valid_to`**, que son los
  activos de contexto. Luego `93 + 14 = 107` y `93 + 10 = 103` exactamente.
- **Las 14 bajas comparten `valid_to: 2026-09-18`.** La decisión que las separa
  (D-31 frente a D-35) vive **solo en el texto libre de `notes`**. Consecuencia
  directa: **una reconstrucción por fecha no puede distinguir 103 de 107**. Ver
  el punto 1 de la implementación.
- **Las dos reconstrucciones reproducen los hashes publicados**, `894ce776…` y
  `c8496446…`, y solo si se anula `valid_to` al reponer el activo. Medido, no
  supuesto; la tabla está en el punto 1.
- De los **10 pares de fortaleza relativa que cruzan continente** (§16), hoy
  **sobreviven 8**: `SXR8.DE`, `EUNL.DE`, `EQQQ.DE`, `VVSM.DE`, `Q8Y0.DE`,
  `ZPRR.DE`, `AZN`, `TSM`. `DFEN.DE` y `4GLD.DE` cayeron con D-35. Es decir, en
  la población de 93 la corrección de RS puede mover como mucho 8 activos, y eso
  acota cuánta diferencia entre el antes y el después puede atribuírsele.
- `universe_vintage_payload` es una **lista blanca de campos** sobre
  `analizables()` únicamente. Añadir un campo a un activo **no analizable** no
  mueve el hash. Eso es lo que hace viable el punto 1 sin tocar INV-19.
- **Hueco real en el instrumento, y es el trabajo de código de esta ficha:**
  `preregistered_estimators` devuelve el primario como **un único número global
  y sin intervalo**; el intervalo por banda que hoy publica `capacity.py`
  (`_block_success_rates` → `_block_mean_interval`) es de la **tasa
  TARGET_FIRST**, o sea del estimador **secundario**. No existe intervalo por
  bloque de la expectancy neta en R por banda, ni desglose por región, ni por
  activo. GATE P2 punto 4 los exige los tres.

## Archivos probables
No asumir que son exactos; verificar con búsqueda de símbolos antes de editar.
- `advisor/research/capacity.py` — `preregistered_estimators`, `_summary`,
  `_block_success_rates`, `_block_mean_interval`, `_classify_capacity`.
- `advisor/research/event_study.py` — `run_event_study_on_vintage`,
  `format_event_study_report`, bandas, MAE/MFE.
- `advisor/research/ablation.py` — P2.4.
- `advisor/universe/models.py` y `advisor/universe/loader.py` — campo nuevo de
  baja y filtro de población de laboratorio.
- `advisor/main.py` — los subcomandos `event-study`, `ablacion-score`,
  `capacidad-estadistica`.
- `universe.yaml` — solo las 14 líneas de baja.

## Invariantes que no pueden romperse
- **INV-06** (una función, varios llamantes): el filtro de población de
  laboratorio no puede crear un segundo camino de cálculo. Los tres subcomandos
  comparten la misma resolución de población.
- **INV-13** (los timestamps crudos de la cosecha no se reserializan): esta
  ficha **lee** `data/vintages/` y no escribe en ella.
- **INV-14** (el primario encabeza; los secundarios se publican con él, nunca
  solos). Es la invariante central de esta ficha.
- **INV-19** (cambiar la lista de analizables produce `universe_vintage_id`
  nuevo y entrada en el decision log). Esta ficha **no cambia la lista vigente**:
  las reconstrucciones son de laboratorio y se declaran como tales.
- **INV-20** (nada se publica como hallazgo sin `experimental_resolution` e
  intervalo).

## Implementación requerida

### 1. Hacer reconstruibles las tres poblaciones
La baja deja de identificarse por texto libre. Se añade a `Asset` un campo
**aditivo y opcional** `baja_decision: Optional[str]` y se rellena en las 14
líneas de baja de `universe.yaml` con `D-31` (`SAN.MC`, `UCG.MI`, `005930.KS`,
`1211.HK`) o `D-35` (los otros diez). `notes` se conserva íntegro.

Es un cambio aditivo de contrato con valor por defecto, previsto aquí, luego
permitido por `docs/metodo-trabajo.md` §3 caso 1. **No entra en
`universe_vintage_payload`** y **no toca ningún activo analizable**, así que
`universe_vintage_id` de los 93 debe seguir siendo
`237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19`: el test que
lo fija tiene que seguir en verde **sin tocarlo**. Si se mueve, algo se hizo mal.

Con eso, los tres subcomandos de investigación aceptan
`--poblacion {vigente,d31,pre-d31}`, con `vigente` por defecto:

    vigente   93 activos   los analizables de hoy
    d31      103 activos   vigente + las 10 bajas con baja_decision = D-35
    pre-d31  107 activos   vigente + las 14 bajas

El filtro es **solo de laboratorio**: no cambia `universe.yaml`, no afecta a
`analizar`, `seguimiento` ni a ninguna pasada de producción, y el informe declara
en cabecera qué población se usó y su `universe_vintage_id` calculado.

**La reconstrucción tiene una trampa, y está medida.** Reponer un activo no es
solo poner `analizable = True`: hay que **anular también su `valid_to`**, porque
`valid_to` sí entra en `universe_vintage_payload`. Comprobado ejecutándolo el
2026-09-21 sobre el `universe.yaml` real:

    pre-d31 (107) con valid_to puesto   d75368d6e2fc3b5d74206abaf357ea7f9d081e5d692841be44921f9c28e36c0e   ← NO corresponde a nada
    pre-d31 (107) con valid_to anulado  894ce776ff8572b3a9dfc97a724f96789122e0dd2c46eef55045d4968e0b5fb0   ← el de 107 del decision log
    d31     (103) con valid_to anulado  c8496446d9b04795b8533e25e794c6141a4e73db73c0ef9bf98599b70f952132   ← el de D-31, exacto
    vigente  (93)                       237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19

Para `d31` se anula `valid_to` **solo a los diez de D-35**; los cuatro de D-31
conservan el suyo, que es el estado real de aquel día. Los tres hashes son
**criterio de aceptación literal**: si una reconstrucción no devuelve el suyo,
está mal hecha y no se publica nada medido con ella.

Aviso para no confundirse: los resultados publicados en **agosto** llevan un
`universe_vintage_id` distinto de `894ce776…`, porque la identidad de 19 activos
cambió después con OA-03 (D-24). Frente a agosto lo comparable es **la lista de
símbolos**, no el hash; frente al decision log, el hash.

### 2. Publicar el estimador primario como manda INV-14
Hoy no se puede. Hace falta:

- **Intervalo por bloque de la expectancy neta en R**, calculado igual que el que
  ya existe para la tasa (media por bloque + intervalo entre bloques), disponible
  **por banda**, además del global. El primario pasa a encabezar la tabla de
  P2.3; `P(objetivo antes de stop)` y la tasa agrupada se publican **debajo**, y
  nunca sin él.
- **Desglose por región y por activo**, que GATE P2 punto 4 exige y hoy no
  existe. `Asset.region` ya está. Por activo basta con la tabla ordenada y el
  número de bloques en que aparece cada uno: sin eso no se puede saber si un
  resultado lo sostiene un puñado de activos.
- **MAE y MFE por banda**, que sí existen (`median_mae_winners_r`,
  `median_mfe_losers_*`, `median_mfe_unbounded_*`): hay que llevarlos a la
  publicación, con la lectura del protocolo escrita al lado —la MAE de una
  salida por stop vale 1,0 R por construcción y no informa; la informativa es la
  MAE de las ganadoras.
- Mantener el **modo potencial sin objetivo** (`MFE_unbounded_R`) separado del
  administrado, porque es el único que permitiría elegir objetivo en P4.

### 3. P2.3 rehecho, con antes y después
Pasada completa sobre `071ddb2b…`, horizonte **swing y medio**, coste 0,20 %,
sobre las tres poblaciones. Se publica el antes (lo de agosto, sobre 107, tal y
como está, sin retocarlo) y el después, y **se declara qué parte de la diferencia
puede venir de cada causa**: población, corrección de RS (como mucho 8 activos) y
cualquier otra. Si no se puede separar, se dice que no se puede separar.

La ambigüedad intrabarra se conserva como estado (`TARGET_FIRST`, `STOP_FIRST`,
`AMBIGUOUS`) y la probabilidad se sigue publicando como intervalo
`[seguros/total, (seguros+ambiguos)/total]`.

### 4. P2.4 rehecho sobre la misma población de señales
Sobre el `EventStudyResult` nuevo, **sin pasar por `classify()`** —esa
dependencia de orden la exige el protocolo: medir la ordenación del RR sobre una
muestra que el propio RR depuró no mide nada—. Se publica: `score` completo,
`score` sin RR, contribución del RR, `risk_pp`, RR bruto y RR neto, y la
migración de señales entre bandas al quitarlo.

Se mantiene el aviso que ya se escribió y que hay que repetir: la tabla sin RR
usa **los mismos cortes** sobre una nota normalizada sobre 60, así que las bandas
**no son comparables una a una**, y recalibrar es P3.

### 5. P2.5 reejecutado sobre el resultado nuevo
Con `experimental_resolution` publicada para cada corte, el número de bloques, su
longitud, la cobertura de regímenes, la censura y la amplitud de los intervalos.
El **gate de censura** se publica: `FINAL_EXIT` es censura administrativa del
experimento, no una salida estratégica, y su tasa va en la tabla. Ojo con el
nombre que usa el protocolo: `_exit_census` vive en `advisor/backtest/report.py`
y es del backtest; en investigación la tasa ya existe como `exit_final_rate`
dentro de `capacity.py::_summary`, y ya alimenta `_classify_capacity`. Aquí solo
falta **publicarla por corte**, no calcularla. El bloque debe superar `MAX_HOLD_BARS` (40 swing, 250 medio); para medio
se publica el número de bloques aunque la resolución salga `LOW`, que es
precisamente el resultado.

### 6. La decisión del RR, que no toma el implementador
P2.4 entrega el material; la decisión es del propietario y se abre como
**OD-11** en `docs/decision-log.md`, con el formato obligatorio (pregunta
exacta, alternativas, consecuencia de cada una, recomendación técnica, trabajo
bloqueado). Lo ya medido en agosto que la alimenta: la dimensión de 20 puntos
reparte 10 a casi todo el mundo, el RR bruto vale 1,500 en la mediana de las
cinco bandas, y la diferencia entre nota con y sin RR vale
`−0,4167·puntos + 16,667`, o sea aritmética de normalización, no información.
Hay que **rehacer esos números** sobre la población nueva antes de abrir OD-11:
si cambian, la pregunta cambia.

### 7. Hashes de las tablas en la evidencia
GATE P2 punto 7. Cada tabla publicada lleva su hash canónico en
`evidence/`, para que se pueda demostrar después que no se retocó.

## Qué NO debe modificarse
`config.yaml` (ni `min_score_operar`, ni `min_rr_ratio`, ni multiplicadores de
ATR), `compute_score`, `compute_levels_from_inputs`, `classify()`, el veto de
D-21, la regla de barra abierta de D-37, `score_model_version`, el contenido de
`data/vintages/`, el orden de ramas de `execution_code` (D-29) y la lista de
analizables vigente. Tampoco se toca producción: ni `analizar`, ni las pasadas
de la Pi, ni el informe de usuario.

Y tampoco **`docs/pendientes.md`**, **`docs/cobertura-especificacion.md`** ni
**`docs/protocolo-investigacion.md`**: los dos primeros son históricos por D-16 y
el tercero está pre-registrado. Ver «Actualización documental requerida».

## Tests unitarios
Con números cerrados escritos en el test.
- `test_poblacion_pre_d31_reconstruye_107_y_d31_reconstruye_103`: sobre
  `universe.yaml` real, `pre-d31` da 107, `d31` da 103 y `vigente` da 93, los
  símbolos de cada diferencia son exactamente los de D-31 y D-35, y los tres
  `universe_vintage_id` valen `894ce776…`, `c8496446…` y `237b0056…`.
- `test_reponer_un_activo_sin_anular_valid_to_no_reproduce_el_hash`: la
  reconstrucción que deja `valid_to` puesto da `d75368d6…` y debe ser rechazada.
  Es el defecto concreto que este test existe para cazar.
- `test_campo_baja_no_mueve_el_universe_vintage_id`: tras añadir
  `baja_decision`, `universe_vintage_id(universe)` sigue siendo
  `237b0056…`. Debe **fallar** si el campo se cuela en
  `universe_vintage_payload`; comprobarlo inyectándolo.
- `test_intervalo_primario_por_banda_se_calcula_sobre_bloques`: serie sintética
  con dos bloques de expectancy neta conocida (p. ej. +0,50 R y −0,10 R) ⇒ el
  primario de esa banda vale +0,200 y el intervalo **no** es el de la tasa
  TARGET_FIRST. Verificar que el test falla si se le pasa el estimador de tasa.
- `test_el_informe_nunca_publica_el_secundario_sin_el_primario` (INV-14): un
  informe construido sin primario no se formatea, lanza.
- `test_desglose_por_region_suma_la_poblacion`: la suma de las n por región
  iguala la n global, sin activo huérfano.
- `test_tasa_de_censura_exit_final_se_publica_por_corte`.

## Tests de integración
- Event study completo sobre una cosecha de prueba con **tres activos**
  (`AAPL`, `SAP.DE`, `SXR8.DE`, los que `docs/metodo-trabajo.md` §3 fija para
  esto), en las tres poblaciones, comprobando que `vigente` ⊂ `d31` ⊂ `pre-d31`
  en número de señales y que ninguna señal cambia de valor entre poblaciones
  —solo aparecen o desaparecen—. Si una señal **cambia de valor**, hay
  contaminación entre activos y es un defecto, no un resultado.
- `ablacion-score` y `capacidad-estadistica` sobre el mismo `EventStudyResult`,
  comprobando que ninguno de los dos vuelve a recorrer la cosecha.
- Una pasada de producción (`analizar --sin-ia --sin-guardar`) **antes y
  después** del cambio: salida idéntica. Esta ficha no puede mover producción.

## Verificación contra datos reales
```bash
V=071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841

# P2.3, las tres poblaciones y los dos horizontes
for P in vigente d31 pre-d31; do
  for H in swing medio; do
    .venv/bin/python -m advisor.main event-study "$V" --horizonte "$H" --poblacion "$P"
  done
done

# P2.4 y P2.5 sobre la población vigente
.venv/bin/python -m advisor.main ablacion-score        "$V" --horizonte swing --poblacion vigente
.venv/bin/python -m advisor.main ablacion-score        "$V" --horizonte medio --poblacion vigente
.venv/bin/python -m advisor.main capacidad-estadistica "$V" --horizonte swing --poblacion vigente
.venv/bin/python -m advisor.main capacidad-estadistica "$V" --horizonte medio --poblacion vigente

# la población vigente no se ha movido
.venv/bin/python -m advisor.main universo

# producción intacta
.venv/bin/python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar
```
**Los cuatro números que hay que comprobar a mano**, no solo leer:
1. `pre-d31` sobre swing debe devolver **121.786 señales** si nada más cambió.
   Si no las devuelve, la diferencia es de la corrección de RS y de la geometría
   de la línea 0, y hay que cuantificarla activo por activo antes de publicar
   nada. Es el control principal de toda la ficha.
2. Los tres `universe_vintage_id` de la tabla de arriba, los tres exactos:
   `237b0056…`, `c8496446…` y `894ce776…`.
3. La diferencia `pre-d31 − vigente` en número de activos con señal debe ser
   **14 como máximo**, y los símbolos, exactamente los de D-31 y D-35.
4. Coger **un** activo de los 8 pares que cruzan continente (`SXR8.DE` contra
   `^GSPC` es el caso de §16) y verificar que su número de sesiones comunes es
   el alineado (1.235, no 982), tal y como se midió el 2026-09-02.

**Ejecutar todos los comandos de la lista, no solo el principal.** La lección de
T-003 es esa: `analizar` iba bien y `frescura-datos` moría con código 1.

## Medición del impacto
- Nº de señales por población y horizonte, y la diferencia atribuida a cada
  causa (población, RS, geometría), o la declaración de que no se puede separar.
- Nº de activos con señal por población, y los símbolos de la diferencia.
- Nº de bloques y `experimental_resolution` por corte, en las tres poblaciones.
- Cambio del primario (media por bloque de expectancy neta en R) global y por
  banda, antes y después, con su intervalo.
- Nº de señales que migran de banda al quitar el RR, sobre la población nueva.
- Tasa de `EXIT_FINAL` por corte.

## Criterio de aceptación
- Los **siete requisitos de GATE P2** (`docs/gates.md`) satisfechos y cada uno
  señalado con el artefacto que lo cumple.
- El estimador **primario encabeza** todas las tablas, con intervalo por bloque,
  por banda, por región y por activo; los secundarios aparecen siempre con él.
- Las **tres poblaciones** publicadas y la comparación con lo de agosto
  declarando cuál es cuál (D-35).
- `universe_vintage_id` de los 93 **sin moverse**, con el test existente en
  verde sin haberlo tocado.
- Producción idéntica antes y después.
- **OD-11 abierta** con el formato obligatorio y con los números nuevos, no con
  los de agosto.
- Hashes de las tablas registrados en `evidence/`.
- `pytest`, `ruff` y `mypy` limpios.

## Criterio de rechazo
- Publicar un intervalo que ningún código del repositorio produzca. Es el
  defecto original y su repetición invalida la entrega entera.
- Publicar un secundario sin el primario (INV-14), o un resultado sin
  `experimental_resolution` ni intervalo (INV-20).
- Tocar umbrales, pesos, geometría o `classify()`; o decidir el RR sin el
  propietario.
- Ampliar la ventana, cambiar la métrica, quitar activos o mover la longitud de
  bloque porque un resultado salga NO CONCLUYENTE.
- Que el filtro de población cree un segundo camino de cálculo (INV-06), o que
  se filtre a producción.
- Que `universe_vintage_id` de los 93 cambie.
- Dar por buena una invariante nueva sin haber inyectado el defecto y visto
  fallar el test, con la salida guardada.

## Evidencia que debe quedar registrada
`evidence/<fecha>-T-013-laboratorio-rehecho/` con:
- `README.md` que recorra los siete puntos de GATE P2 uno a uno.
- Salida literal de los doce comandos de arriba.
- `antes.md` (las tablas de `docs/pendientes.md` §11, §14 y §15 copiadas tal
  cual) y `despues.md`.
- Tabla de atribución de la diferencia por causa.
- Los hashes canónicos de cada tabla publicada.
- La salida del test de invariante **fallando** contra el código sin corregir.

## Commit esperado
Rama `feat/a02-laboratorio-rehecho`. Mensaje:
`feat(investigacion): rehacer P2.3, P2.4 y P2.5 sobre la cosecha con el estimador primario por banda`

Recordatorio de OA-02: **todo entra por PR**, también lo de una línea. El push
directo a `main` está bloqueado, `enforce_admins` incluido.

## Actualización documental requerida
- `docs/roadmap.md`: fila **A-02** a EN_REVISION y luego ACEPTADA; fila **A-09**
  (T-016) sin cambios.
- `docs/gates.md`: GATE P2 marcado como cruzado, con la fecha y la evidencia.
- `docs/decision-log.md`: **D-42** con el veredicto del laboratorio rehecho y el
  cruce de GATE P2; **OD-11** abierta con la pregunta del RR.
- `docs/agent-workflow.md`: nuevo punto de retomada, apuntando al resultado
  vigente.

**`docs/pendientes.md` NO se toca.** `docs/metodo-trabajo.md` paso 9 lo dice
expresamente: «No se actualiza `docs/pendientes.md` ni
`docs/cobertura-especificacion.md`: son históricos», y **D-16** es la decisión
que los declaró así. §11, §14 y §15 se quedan **intactas**, con sus cifras sobre
107 y anteriores a la corrección de RS. No se editan, no se anotan y no se les
añade un aviso.

El antes/después no vive ahí, vive en la evidencia: las tablas históricas se
**copian** a `evidence/<fecha>-T-013-laboratorio-rehecho/antes.md` y el resultado
nuevo se publica en `despues.md`, en el mismo directorio. Quien quiera saber cuál
es el resultado vigente lo encuentra por los documentos de **estado** —`roadmap`,
`gates`, `decision-log` y `agent-workflow`—, que sí se actualizan y sí apuntan a
la evidencia. `pendientes.md` es el registro de lo que se pensaba entonces, y por
eso se lee pero no se reescribe.

Tampoco se toca `docs/protocolo-investigacion.md`: es un documento pre-registrado
y corregir en él la referencia a `_exit_census` sería una entrega aparte y
explícita. La aclaración del punto 5 de esta ficha ya evita que el implementador
siga la referencia equivocada, así que no bloquea nada.

## Riesgo operativo que conviene no ignorar
La cosecha `071ddb2b…` está en `.gitignore` y **solo vive en el portátil**. Es la
única fuente reproducible de GATE P2 y de todo lo que venga después: si se pierde
ese directorio, el gate no se puede rehacer, porque una cosecha nueva no
devolvería las mismas series. Copiarla fuera del portátil antes de empezar no es
parte de esta ficha, pero sí es la decisión más barata de la semana.

## Handoff al siguiente agente

**Estado: ACEPTADA** el 2026-09-21. Implementada y revisada en
`feat/a02-laboratorio-rehecho`. **No fusionada, sin PR**, a la espera de que el
propietario revise el cierre. **GATE P2 CRUZADO** (D-42 y D-43).

**Verificado:** 614 tests, `ruff` y `mypy` limpios. Pasó **revisión
independiente** el 2026-09-21 (`CORREGIR_ANTES_DE_OD11`); sus cinco hallazgos
SAME_SCOPE están corregidos y los nueve FOLLOW_UP registrados en
`evidence/.../follow-ups.md`. Los tres
`universe_vintage_id` reproducen los del decision log. `pre-d31` devuelve las
121.786 señales de agosto, exactas. Producción probada intacta de forma
determinista con `backtest --vintage` (mismo SHA-256, 866 operaciones). Los
cuatro defectos inyectados hacen fallar su test, con la salida guardada.

**Resultado:** con el estimador primario de INV-14 el veredicto global pasa de
`LIMITADA`/`MEDIUM` a `INSUFICIENTE`/`LOW`; ninguna banda es concluyente; el
IC95 cruza el cero en todas menos `<50`. Medio da 5 bloques, no los 8 previstos.
No se ajustó nada para mejorarlo.

**OD-11 cerrada** el 2026-09-21 en **D-43**: el RR sale del score como dimensión
de puntuación y sigue siendo condición de ejecutabilidad y de riesgo. Con eso se
cumple el séptimo requisito y **GATE P2 queda cruzado**; **A-03 (P3) queda
desbloqueada**, con su ficha por escribir.

**Hallazgos clasificados:**
- SAME_SCOPE, corregido: la tabla de la ablación sustituía intervalo, media y
  bloques por «NO CONCLUYENTE», incumpliendo `docs/metodo-trabajo.md` §3. Era
  anterior a esta tarea; el cambio de estimador lo dejó al descubierto porque
  la tabla entera se quedaba sin números.
- SAME_SCOPE, corregido tras la revisión: el test del estimador primario usaba
  bloques del **mismo tamaño**, donde la media por bloque y la media agrupada
  coinciden, así que no protegía nada. Una mutación a media agrupada sobrevivía
  los 613 tests. Corregido con bloques de tamaños distintos (0,200 frente a
  0,350) y defecto inyectado.
- SAME_SCOPE, corregido tras la revisión: se afirmaba que «194 señales (0,16 %)
  cambian de banda» y que «toda la diferencia es de población». Era una suma de
  diferencias **netas**, que no cuenta migraciones. Retirado de los cuatro
  sitios; la atribución se declara **no observable** con los artefactos de
  agosto, acotada en [97, 10.228].
- SAME_SCOPE, corregido tras la revisión: faltaba la declaración de sesgo que
  exige el requisito 3 de GATE P2, y faltaba el test de integración de las tres
  poblaciones que esta misma ficha pide.
- OBSERVATION: `_primary_rows_by_region` accede a `block_lookup._asset(...)`,
  un método privado desde fuera de su clase. Funciona y `ruff` lo acepta; queda
  anotado por higiene, no se tocó.
- OBSERVATION: la `n` del primario es menor que la `n` de la banda porque las
  señales `AMBIGUOUS` no tienen `net_r_multiple`. Está declarado en `despues.md`.

**Siguiente paso:** revisión independiente y, en paralelo, responder OD-11.
