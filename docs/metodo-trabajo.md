# Método de trabajo

Cómo trabaja **cualquier agente** (Opus, Codex, Claude Code, una persona) en
`intradia-bot` desde el 2026-09-14. Es normativo: una entrega que no siga este
método se devuelve, aunque los tests pasen.

Documentos relacionados, cada uno con un papel y sin solaparse:

| Documento | Papel |
|---|---|
| `docs/roadmap.md` | Qué falta, en qué orden, qué depende de qué, qué está bloqueado |
| `docs/metodo-trabajo.md` (este) | Cómo se ejecuta una tarea: ciclo, invariantes, defectos, commits, revisión, ficha |
| `docs/agent-workflow.md` | Quién hace qué (Opus/Codex), prompts operativos, START HERE, cola de tareas |
| `docs/gates.md` | Puertas entre fases: requisitos, métricas, artefactos, qué desbloquean |
| `docs/decision-log.md` | Decisiones tomadas y decisiones que solo el propietario puede tomar |
| `docs/tareas/T-nnn-*.md` | Una ficha por tarea, con el formato de la sección 9 |
| `docs/protocolo-investigacion.md` | Cómo se mide (P2–P7). No se toca sin registrar la modificación como decisión |
| `docs/plan-ejecucion.md` | Especificación detallada de las fases 4–15 de la línea 0 |
| `evidence/` | Evidencia reproducible de cada entrega (sección 7) |

---

## 1. El ciclo, paso a paso

Toda tarea recorre estos once pasos en este orden. Ninguno se salta; si uno no
aplica, la ficha dice por qué.

### 1. Inspeccionar

- Leer `docs/roadmap.md`, este documento, la ficha de la tarea y las decisiones
  de `docs/decision-log.md` que la ficha cite.
- Localizar el código real con búsqueda de símbolos, **no por las rutas de la
  ficha**: `grep -rn "def nombre" advisor tests`. Las rutas de la ficha son
  una pista, no un hecho.
- Comprobar `git status` y `git log --oneline -5`. Si hay cambios sin
  commitear que no son tuyos, no los toques y anótalo en el handoff.

### 2. Reproducir el estado actual

```bash
source .venv/bin/activate
git rev-parse --short HEAD
python -m pytest -q            # ~90 s; anota el número de tests
ruff check .
mypy advisor
```

Si algo falla **antes** de tocar nada, es un BLOCKER (sección 5): se documenta
y se para, salvo que la ficha diga que la tarea consiste en arreglarlo.

### 3. Establecer la línea base

La línea base es la salida real del sistema antes del cambio. Se guarda en
`evidence/<fecha>-<tarea>/` (sección 7). Según la tarea:

| Tarea toca… | Línea base obligatoria |
|---|---|
| Análisis, niveles, ejecución, calidad del dato, informe | `python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar > evidence/.../antes.txt` y conteos: OPERAR/RADAR/DESCARTADOS, calidad OK/INCOMPLETO/DEGRADADO, activos con sesiones ausentes |
| Backtest o simulador | `python -m advisor.main backtest --horizonte swing --period 5y` sobre los grupos que la ficha indique; guardar la tabla de operaciones y expectancy |
| Investigación (P2–P9) | El comando de la fase sobre la cosecha `071ddb2b…` (o la que la ficha fije), con `data_vintage_id` en la salida |
| Persistencia | `sqlite3 intradia.db ".schema"` y conteos por tabla |
| Despliegue / systemd | `python -m advisor.main verificar-systemd` (en la Pi) |
| Solo documentación | No aplica; decirlo |

### 4. Implementar

- Cambio mínimo y coherente. No reescribir módulos si cabe un cambio local.
- Una función, varios llamantes: si producción e investigación necesitan el
  mismo cálculo, viven en el mismo sitio (INV-06).
- No introducir excepciones por ticker ni por fecha para hacer pasar un caso.
- No cambiar fórmulas, umbrales ni pesos fuera del alcance de la ficha. Si el
  cambio obliga a tocarlos, es una decisión: sección 6, caso «contrato».
- Sin `print()`, sin `TODO` sin ficha asociada, sin código muerto.

### 5. Tests

- Test unitario para cada regla nueva, con **números cerrados** calculados a
  mano en el propio test, no aserciones de signo.
- Test de regresión para cada defecto corregido, nombrado por el caso real
  (`test_exh1_regression_2026_09_14` es el modelo).
- Los fixtures reproducen el universo real: `trade_republic: unknown`, ISIN
  `null` en la mayoría, plazas europeas con su zona horaria. Un fixture
  «cómodo» que no se parece a `universe.yaml` no prueba nada.
- Ejecutar `python -m pytest -q`, `ruff check .`, `mypy advisor`. Los tres
  limpios.

### 6. Ejecutar contra datos reales

Repetir exactamente el comando de la línea base y guardar `despues.txt`.
Después, **comprobar a mano al menos un número**: abrir la salida, elegir un
activo, recalcular con calculadora lo que la tarea cambió y escribir el cálculo
en la ficha. Ejemplo válido:

```text
EXH1.DE: stop 54,71 · target2 58,20 · min_rr 1,5
entry_max_rr = (58,20 + 1,5·54,71) / 2,5 = 56,106 → informe muestra 56,11 ✔
```

Si la tarea necesita la Pi (despliegue, systemd, reloj), la verificación se
hace **en la Pi**, no en el portátil.

### 7. Medir el impacto

Comparar `antes.txt` y `despues.txt` y rellenar en la ficha:

- nº de activos cuyo radar/acción cambia, listados por motivo;
- nº de activos cuya calidad del dato cambia, por motivo;
- para investigación: nº de señales que cambian de población o de bloque;
- cualquier número agregado que se mueva (expectancy, conteos por banda).

Un cambio que «no debería afectar a nadie» y afecta a alguien es un hallazgo:
se explica o se revierte. Un cambio que debería afectar a alguien y no afecta a
nadie, también.

### 8. Revisar invariantes

Recorrer la lista de la sección 2 y marcar en la ficha cuáles ha ejercitado la
tarea y cómo (test, salida real, o «no aplica»).

### 9. Actualizar documentación

- La ficha de la tarea: estado, evidencia, impacto, handoff.
- `docs/roadmap.md`: solo la fila de estado de la fase.
- `docs/decision-log.md`: si se ha tomado una decisión (sección 6).
- `docs/plan-ejecucion.md` o `docs/protocolo-investigacion.md`: solo si el
  contrato que describen ha cambiado, y entonces con fecha y motivo.
- No se actualiza `docs/pendientes.md` ni `docs/cobertura-especificacion.md`:
  son históricos.

### 10. Commit

Ver sección 4. Un commit por entrega coherente, con mensaje causa → efecto, en
la rama de la tarea. Nunca `git push --force`, nunca sobre `main` directamente.

### 11. Handoff

Bloque final de la ficha (sección 9): qué se hizo, qué se verificó, qué queda,
qué hallazgos ajenos aparecieron (clasificados), y qué debe hacer el siguiente
agente. Escrito para alguien que no ha visto la conversación.

---

## 2. Invariantes globales

Se numeran para poder citarlas en fichas, tests y revisiones. Cada una dice
dónde está protegida hoy o qué tarea la protegerá.

| ID | Invariante | Protección |
|---|---|---|
| INV-01 | `reward_risk(entry_max, target2, stop) >= min_rr − 1e-9` para todo `Levels` | `tests/test_analysis.py::test_entry_max_never_violates_min_rr` |
| INV-02 | `accion == COMPRAR` ⇒ setup válido ∧ `execution.executable` ∧ `rr_at_least(rr(entry), min_rr)` ∧ `entry <= entry_max` | `classify()` en `advisor/analysis/opportunity.py`; test de integración en fase 13 |
| INV-03 | `score.value` no depende de frescura, calidad del dato, broker ni ejecución | `compute_score` no recibe esos objetos; comprobar en revisión |
| INV-04 | `trade_republic: unknown` produce `BROKER_UNVERIFIED`, nunca `BROKER_UNAVAILABLE`, y no baja el radar | `tests/test_analysis.py` (PR 1); fixture con `unknown` |
| INV-05 | El benchmark nunca define las sesiones esperadas de un activo | **Pendiente** — T-002 (fase 4) |
| INV-06 | Producción e investigación comparten `compute_levels_from_inputs`, `compute_score`, `relative_strength[_series]`, `build_snapshot_series`, calendarios y transformaciones | Test de equivalencia prefijo/vectorizado en `tests/test_backtest.py`; revisión |
| INV-07 | `net_R = gross_R − cost_pct / risk_pp`, exacto | `tests/test_research.py` (P2.1) |
| INV-08 | Toda comparación pareada exige `data_vintage_id` idéntico o aborta | `replay_managed_population` en `advisor/research/event_study.py` |
| INV-09 | Todo dato externo usado en backtest cumple `available_at <= analysis_timestamp` | **Pendiente** — B0 (`advisor/context/models.py`) |
| INV-10 | El LLM no altera ningún número; la narrativa se guarda aparte de los campos calculados | `advisor/ai/narrator.py` degrada; persistencia pendiente en C-05 |
| INV-11 | El informe no llama «precio actual» a un cierre anterior | **Pendiente** — fase 9 |
| INV-12 | Una entrega que cambia cuándo se recomienda incluye el conteo de activos afectados por motivo | Regla de método (paso 7); el revisor la exige |
| INV-13 | Los timestamps crudos de la cosecha nunca se reserializan (hashes estables) | `tests/test_timestamps.py` |
| INV-14 | Estimador primario: media por bloque de la expectancy neta en R; las secundarias se publican siempre junto a él, nunca solas | Protocolo, pre-registro 2026-09-02; `advisor/research/capacity.py` |
| INV-15 | El holdout se consulta una vez | Protocolo; registro obligatorio en `evidence/` de cada consulta |
| INV-16 | Lo desconocido se declara desconocido: nunca `unknown → no`, `None → 0`, ausencia → neutro sin regla escrita | Revisión; `N/D` en el informe |
| INV-17 | Todo cambio de esquema SQLite pasa por una migración con backup previo y prueba de restauración | **Pendiente** — T-004 |
| INV-18 | Toda ejecución que persiste algo lleva `run_id` y manifiesto (git SHA, config hash, universe vintage, versiones) | **Pendiente** — T-004 |
| INV-19 | Cualquier cambio en la lista de activos analizables produce un `universe_vintage_id` nuevo y una entrada en el decision log | **Pendiente** — A-00 |
| INV-20 | Un resultado de investigación sin `experimental_resolution` y sin intervalo no se publica como hallazgo | `advisor/research/capacity.py`; revisión |
| INV-21 | Una barra servida desde la caché local se declara como tal en la medición de esa pasada; nunca se presenta como si la fuente viva la hubiera devuelto | **Pendiente** — T-018 (C-09) |
| INV-22 | Un porcentaje cuyas observaciones no son independientes se publica con el número de eventos que lo generan, no solo con el número de filas | `advisor/freshness_history.py`; D-41 |

---

## 3. Qué hacer cuando…

### …los tests y la realidad discrepan

La realidad manda. Si la suite está verde y la salida real es incorrecta, el
defecto es de la suite además de del código: añadir el caso real como test de
regresión **antes** de arreglar el código, ver que falla, arreglar, ver que pasa.

### …la documentación y el código discrepan

El código es la fuente de verdad sobre lo que **hace** el sistema; los
documentos son la fuente de verdad sobre lo que **debe** hacer. Si el código
hace algo distinto de lo que dice el protocolo o el plan:

1. Si el documento fija una regla pre-registrada (protocolo) y el código se
   desvió: corregir el código y publicar antes/después (así se hizo con el mapa
   de bloques de P2.5).
2. Si el documento describe un estado («X está hecho») que no es cierto:
   corregir el documento en la misma entrega y anotarlo en el handoff.
3. Si no está claro cuál de los dos tiene razón: FOLLOW_UP con ambos citados;
   no elegir en silencio.

### …el resultado es NO CONCLUYENTE

Es un resultado válido y se publica como tal, con `experimental_resolution`,
tamaño de muestra, número de bloques e intervalo. **No** se hace nada de esto:
ampliar la ventana hasta que salga, cambiar la métrica, quitar activos, mover
el bloque. Si alguna de esas cosas parece razonable, se propone como estudio
nuevo, pre-registrado, en el decision log.

### …aparece un defecto ajeno a la tarea

Clasificar según la sección 5 y actuar en consecuencia. Nunca arreglarlo «ya
que estamos» sin clasificar.

### …un cambio afecta a la población de P2/P3

Cualquier cambio en `compute_levels_from_inputs`, `compute_score`,
`relative_strength`, calendarios, `build_snapshot_series` o el recorte de
barras cambia lo que P2.3/P2.4 miden. Obligatorio:

1. Decirlo en la ficha con el nombre de la función.
2. Medir cuántas señales de la cosecha `071ddb2b…` cambian de valor, población
   o bloque (`event-study` antes/después sobre tres activos como mínimo:
   `AAPL`, `SAP.DE`, `SXR8.DE`).
3. Registrar que P2.3/P2.4 quedan pendientes de rehacer (ya lo están hasta
   GATE P2), o si ya estaban congelados, abrir una decisión: se recongela con
   nuevo `score_model_version` o se descarta el cambio.

### …hay que modificar un contrato de datos

Contratos: `Levels`, `ExecutionEvaluation`, `PositionSizing`,
`SignalObservation`, `DataFreshness`, el manifiesto de cosecha, el esquema
SQLite, `universe.yaml`, `config.yaml`, la salida JSON del LLM.

1. Cambio **aditivo** (campo nuevo con valor por defecto): permitido dentro de
   la tarea si la ficha lo prevé; migración si toca SQLite (INV-17).
2. Cambio **de significado** (una unidad, un nombre, un valor por defecto):
   decisión en el decision log antes de implementarlo, con la lista de
   llamantes afectados y el test de unidades actualizado.
3. Cambio que **rompe** una cosecha o un resultado publicado: nuevo
   `schema_version` en el manifiesto y `score_model_version`/`data_vintage_id`
   nuevos; el resultado antiguo no se borra, se etiqueta.

### …un proveedor externo cambia

- `yfinance` cambia de comportamiento (columnas, ajuste, zona horaria): test
  contra la cosecha congelada (`tests/test_capacity_real_vintage.py`,
  `tests/test_timestamps.py`) y comparación de una descarga nueva contra el
  hash antiguo del mismo rango. Si el hash cambia para el mismo rango
  histórico, es un hallazgo de revisión retroactiva del proveedor y se
  documenta antes de seguir.
- Cualquier proveedor nuevo entra por la ficha de proveedor de
  `docs/roadmap.md` (línea B, contrato de proveedor): fuente, licencia,
  retención, rate limit, retry, backoff, timeout, versión de esquema, payload
  crudo, normalización, idempotencia, fallback y degradación. Sin esa ficha no
  se escribe el collector.

---

## 4. Política de commits y ramas

- **Una rama por entrega coherente**, creada desde `main`:
  `fix/…`, `feat/…`, `research/…`, `docs/…`, `ci/…`. Un PR de la línea 0 es una
  entrega; una fase de investigación es una entrega.
- **Commits pequeños pero compilables.** Cada commit pasa `pytest`, `ruff` y
  `mypy`. Si dos fases son mutuamente dependientes (la capa de ejecución
  necesita la firma nueva del dimensionamiento), van en **un** commit: no se
  parten por estética. Esto corrige la regla «un commit por fase» de
  `docs/plan-ejecucion.md`.
- **Mensaje** = causa y resultado, en la primera línea. Ejemplo:
  `fix(data): las sesiones esperadas salen del calendario de plaza, no del benchmark`.
  El cuerpo lista qué cambia para el usuario y cuántos activos afecta.
- **No mezclar** documentación metodológica con cambios de comportamiento
  salvo que sean inseparables (una decisión que el propio commit aplica).
- **No** hacer `git reset --hard`, `git clean`, `git push --force`, ni commits
  sobre `main`. Merge a `main` solo por PR y solo cuando la ficha dice
  «aceptada».
- Los ficheros de `evidence/` se commitean con la entrega que los produce.

---

## 5. Política de defectos encontrados

Todo hallazgo que no forma parte de la ficha se clasifica **antes** de tocar
código:

| Clase | Definición | Acción |
|---|---|---|
| **BLOCKER** | Impide que la tarea produzca resultados válidos (la línea base falla, un dato de entrada es falso, un contrato previo está roto) | Parar. Escribir el hallazgo en la ficha con reproducción. Si el arreglo es evidente y pequeño, proponerlo; no aplicarlo sin decir que se sale del alcance |
| **SAME_SCOPE** | Misma causa raíz y mismo contrato que la tarea | Arreglar dentro de la tarea, con su test, y listarlo en el handoff |
| **FOLLOW_UP** | Real, independiente, no bloquea | Crear ficha `docs/tareas/T-nnn-*.md` con reproducción y clase; enlazarla en `docs/roadmap.md` (sección «Hallazgos abiertos») |
| **OBSERVATION** | Rareza, mejora posible, duda; no requiere acción ahora | Una línea en el handoff |

Regla de oro: **una tarea no crece por lo que descubre**. Si más de dos
hallazgos son SAME_SCOPE, probablemente la ficha estaba mal delimitada: decirlo.

---

## 6. Decisiones

Hay tres clases y solo una la toma el agente.

| Clase | Quién | Dónde queda |
|---|---|---|
| **Técnica reversible** con un valor por defecto claro (nombre de un campo, orden de dos pasos, una tolerancia numérica, una dependencia pura y mantenida) | El agente | Ficha de la tarea y, si afecta a más de una tarea, `docs/decision-log.md` con ID `D-nn` |
| **Metodológica** (qué se mide, con qué población, qué estimador, qué cambia un contrato) | Opus propone en el decision log **antes** de medir; el revisor independiente la valida | `docs/decision-log.md`, con fecha, alternativas y qué evita |
| **De propietario** (coste, proveedor de pago, riesgo asumido, apetito de capital, duración de la validación forward, activar reglas de GitHub) | Solo el propietario | `docs/decision-log.md`, sección `OWNER_DECISION_REQUIRED`, con el formato de `docs/agent-workflow.md` |

Prohibido: tomar una decisión de propietario por defecto «para no bloquear».
Permitido: hacer todo lo que no dependa de ella y dejar la tarea en
`BLOQUEADA_POR_OWNER` con el trabajo restante identificado.

---

## 7. Evidencia

Todo hallazgo relevante acaba en el repositorio o en un artefacto
identificable desde el repositorio. Convención:

```text
evidence/<YYYY-MM-DD>-<T-nnn o fase>-<slug>/
    README.md        # qué se midió, comando exacto, commit, instante, conclusión
    antes.txt        # salida real antes (si aplica)
    despues.txt      # salida real después
    *.json / *.csv   # tablas numéricas que sustentan la conclusión
```

Reglas:

- Cada fichero ≤ 1 MB. Lo que no cabe (cosechas, bases de datos) se queda
  fuera del repositorio y el README registra ruta, tamaño y **hash SHA-256**.
- El README nombra el commit (`git rev-parse --short HEAD`) y, para
  investigación, el `data_vintage_id`, el `universe_vintage_id` y el
  `score_model_version` cuando existan.
- Los manifiestos de cosecha (`data/vintages/<id>/manifest.json`, ~90 KB) se
  commitean: son la identidad de la cosecha. Los CSV no. (Tarea A-00 quita la
  regla de `.gitignore` que hoy los excluye.)
- Un número que solo existe en una conversación no existe.

---

## 8. Revisión entre agentes

Para cambios importantes (comportamiento en varios ficheros, lógica de negocio,
persistencia, calendarios, cualquier cosa estadística o con posible
look-ahead):

```text
autor → revisor independiente → correcciones → gate
```

El revisor **intenta romperlo**, no confirmarlo. Recibe: la ficha, el diff, la
evidencia, y las invariantes marcadas. Devuelve hallazgos clasificados
(sección 5) con reproducción. Un «LGTM» sin al menos un intento de refutación
documentado no cuenta como revisión.

Revisión **obligatoria e independiente** (otro agente, no el autor con otro
prompt) para: cualquier cambio en `advisor/research/`, cualquier cambio en
calendarios o fechado de sesiones, cualquier cambio en `classify()`,
`compute_levels*`, `compute_score`, y cualquier migración de SQLite.

Trivial (una línea evidente, texto de informe, documentación sin decisiones):
sin revisión, pero con evidencia.

El revisor en Claude Code es el subagente `revisor`; en Codex, una sesión
nueva con el prompt `PROMPT_REVIEW` de `docs/agent-workflow.md`.

---

## 9. Ficha de tarea (plantilla obligatoria)

Copiar a `docs/tareas/T-nnn-<slug>.md`. Todas las secciones son obligatorias;
si una no aplica se escribe «No aplica: <motivo>».

```markdown
# T-nnn — <título>

Estado: PENDIENTE | EN_CURSO | EN_REVISION | ACEPTADA | RECHAZADA | BLOQUEADA_POR_OWNER
Agente: Opus | Codex | Opus→Codex→Opus
Línea / fase: <L0 PR2 fase 4, A P3, B0, C-02…>
Gate al que contribuye: <GATE L0 …>

## Objetivo
Una frase verificable.

## Por qué existe
El defecto, la medición o la decisión que la motiva, con enlace a evidencia.

## Dependencias previas
Fichas o gates que deben estar ACEPTADAS. Decisiones del decision log que aplica.

## Archivos probables
No asumir que sean exactos: verificar primero con búsqueda de símbolos.

## Invariantes que no pueden romperse
IDs de la sección 2 de docs/metodo-trabajo.md, y las específicas de la tarea.

## Implementación requerida
Pasos concretos. Contratos nuevos con sus campos y tipos.

## Qué NO debe modificarse
Explícito: funciones, umbrales, ficheros.

## Tests unitarios
Nombre y caso numérico cerrado de cada test.

## Tests de integración
Qué invariante prueban y con qué fixture.

## Verificación contra datos reales
Comando exacto y qué número comprobar a mano.

## Medición del impacto
- nº activos afectados (por motivo)
- nº señales afectadas (por motivo)
- cambio en resultados relevantes

## Criterio de aceptación
Condiciones objetivas, todas necesarias.

## Criterio de rechazo
Qué la devuelve aunque lo demás esté bien.

## Evidencia que debe quedar registrada
Ruta en evidence/ y contenido mínimo.

## Commit esperado
Rama y primera línea del mensaje.

## Actualización documental requerida
Qué fila del roadmap, qué decisión, qué contrato.

## Handoff al siguiente agente
(se rellena al terminar) Estado, verificado, pendiente, hallazgos clasificados, siguiente paso.
```

---

## 10. Definición de terminado de una tarea

Una tarea está terminada solo cuando **todo** esto es cierto:

```text
[ ] código correcto y mínimo
[ ] tests unitarios y de integración en verde (pytest -q)
[ ] ruff check . y mypy advisor limpios
[ ] caso real verificado a mano y escrito en la ficha
[ ] impacto medido (activos/señales afectados por motivo)
[ ] invariantes revisadas y marcadas
[ ] documentación actualizada (ficha, roadmap, decision log si procede)
[ ] evidencia en evidence/ con commit y comando
[ ] commit identificable en una rama desde main
[ ] sin prints, sin TODO huérfano, sin fixtures irreales
[ ] hallazgos ajenos clasificados
[ ] handoff escrito
[ ] revisión independiente hecha si la sección 8 la exige
```

«Compila» y «los tests pasan» son dos de trece casillas.

---

## 11. Límites de la sesión de Codex

Comprobados el 2026-09-14, cada uno a costa de una ejecución de ficha. No los
anuncia: se presentan como BLOCKER de la tarea.

| Límite | Síntoma | Cómo se compensa |
|---|---|---|
| No escribe en `.git` | `Unable to create '.git/index.lock': Operation not permitted` | La rama se crea antes desde Claude Code; Codex deja el árbol listo y **lista en el handoff los ficheros a commitear**; el commit y el push los hace Claude Code |
| No tiene DNS | `Failed to resolve 'pypi.org'`; el proveedor de datos no responde | Las dependencias se instalan antes; la verificación contra datos reales la ejecuta Claude Code y se anota quién la hizo |
| No escribe fuera del directorio principal del repositorio | En un worktree hermano falla hasta `mkdir` | **Nada de worktrees**: las fichas en paralelo se serializan, o las hace Claude Code |

Git en solo lectura (`status`, `diff`, `log`, `rev-parse`) sí funciona, así que
Codex puede establecer su línea base y medir su propio diff.

Consecuencia sobre la sección 8: cuando Codex es el autor, el ciclo real es
**Codex implementa → Claude Code verifica contra datos reales y commitea →
revisor independiente**. La verificación real no es opcional por delegarla:
es el paso que descubrió los defectos de las tres últimas entregas.

---

## 12. Ficha de proveedor externo (obligatoria antes de escribir un collector)

Copiar a la ficha de la tarea que introduce la fuente (B-02, B-03, B-04,
B-05, o una segunda fuente de precios si OD-02 lo decide). Sin esta ficha
rellena y revisada, no se descarga nada.

```markdown
## Proveedor: <nombre>
- source / endpoint:
- licencia y uso permitido (personal, no redistribución…):
- retención permitida del payload crudo (sí/no/plazo):
- rate limit declarado y el que aplicamos (peticiones/min):
- timeout por petición (s) y reintentos (n, backoff exponencial base/máx):
- schema_version del proveedor y cómo se detecta un cambio:
- raw_payload: se guarda entero (hash SHA-256) / solo campos (lista):
- normalización (campos de salida, unidades, zona horaria, divisa):
- idempotencia (clave natural: source_id + published_at + content_hash):
- fallback si falla (otra fuente / nada / dato anterior con etiqueta):
- degradación: qué hace el informe si el proveedor no responde:
- point-in-time: cómo se obtiene `available_at` y por qué es fiable:
- coste (€/mes o llamadas/mes) y quién lo aprueba (OD-nn):
```

Estados que todo dato externo debe poder expresar, **distintos entre sí** y
persistidos como tal (nunca `None` a secas):

| Estado | Significado | Ejemplo |
|---|---|---|
| `NO_DATA` | La fuente respondió y no hay dato para ese emisor/instrumento | Sin noticias hoy |
| `PROVIDER_ERROR` | La fuente no respondió, dio error o un esquema desconocido | HTTP 5xx, timeout, 404 de fundamentales |
| `NOT_APPLICABLE` | El dato no tiene sentido para ese instrumento | PER de un ETF de oro |
| `NOT_YET_PUBLISHED` | El dato existe pero `available_at > analysis_timestamp` | Resultados anunciados para mañana |
| `STALE` | El dato existe pero supera la antigüedad máxima declarada | Fundamentales de hace 18 meses |

Un `PROVIDER_ERROR` nunca se convierte en `NO_DATA`, y ninguno de los cinco
entra en el score cuantitativo (INV-16, INV-09).
