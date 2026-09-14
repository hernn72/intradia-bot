# Flujo de trabajo de los agentes

Quién hace qué, con qué prompt, y por dónde se empieza. Complementa a
`docs/metodo-trabajo.md` (cómo se ejecuta una tarea) y a `docs/roadmap.md`
(qué se ejecuta y en qué orden).

---

## START HERE

```markdown
# START HERE — actualizado 2026-09-14 (fin de la segunda sesión)

Estado actual:
- `main` sigue en `6d32cf2`. **Nada mergeado todavía**: cuatro ramas en cadena,
  cada una desde la anterior, todas pusheadas y con CI verde:
    fix/execution-data-quality   e53e385  PR 1 (fases 1-3) + docs previas
    ci/github-actions            e5ed089  T-001 CI  · ACEPTADA
    feat/run-manifest-migrations 1c76add  T-002 migraciones + manifiesto · ACEPTADA (revisada y desplegada)
    fix/exchange-calendars       5fb3394  T-003 calendarios de plaza · EN_REVISION
  `feat/universe-vintage` existe en `1c76add` y está vacía (T-006 no llegó a empezar).
- La Pi corre `1c76add` (T-002), base migrada a v2, timers vivos, NTP ok.
  Tiene ya instalada `exchange_calendars==4.13.2` (Python 3.13/ARM, verificada).
- 431 tests, ruff y mypy limpios en `fix/exchange-calendars`.

Primera acción del propietario:
- OA-01: mergear la cadena en `main` (basta con `fix/exchange-calendars`, es lineal)
  cuando T-003 esté aceptada. OA-02: branch protection con `checks (3.12)` y `checks (3.13)`.

Primera tarea ejecutable:
- **Revisión independiente de T-003** (obligatoria: toca fechado de sesiones).
  Los puntos concretos a refutar están al final de
  `docs/tareas/T-003-calendarios-de-plaza.md`, sección «Cierre de la ficha».

Quién debe hacerla:
- Opus (subagente `revisor` con PROMPT_REVIEW), no el autor.

Qué debe devolver:
- Hallazgos clasificados con reproducción y VEREDICTO ACEPTAR/CORREGIR/RECHAZAR.

Criterio para continuar:
- Aceptada T-003 → desplegar en la Pi y verificar allí → **T-004** (Opus: causa
  de los huecos; la población exacta ya está medida: 28 activos con 2026-09-07,
  14 con 2026-03-06, 2+2 en XKRX, 1 en XCSE) → **T-006** (universe vintage) →
  T-005 (calidad y códigos).

Cómo delegar en Codex (aprendido a golpes, ver docs/metodo-trabajo.md):
- No puede escribir en `.git`: crea tú la rama, y el commit y el push los haces tú.
- No tiene DNS: instala tú las dependencias y ejecuta tú las verificaciones
  contra datos reales.
- No escribe fuera del directorio principal del repositorio: **nada de
  worktrees hermanos**; las fichas en paralelo se serializan.
```

---

## 1. Reparto de funciones

### Opus — diseño, método, estadística, diagnóstico

Preferir para: arquitectura y contratos de datos; decisiones metodológicas y
pre-registro; investigación estadística (P2–P9) e interpretación de
resultados; depuración de causa raíz con datos reales (T-004 es el modelo);
revisión conceptual e independiente; documentación técnica que fija reglas.

### Codex — implementación especificada, mecánica, verificación

Preferir para: fichas con contrato ya fijado; refactors locales; tests;
migraciones; CI/CD y automatización; cambios mecánicos multiarchivo;
búsqueda de referencias y eliminación de duplicación; herramientas de línea
de comandos con salida definida.

### Cuándo se encadena Opus → Codex → Opus

Obligatorio cuando la tarea cumple **una** de estas:

- introduce o cambia un contrato de datos (`Levels`, `DataQuality`,
  esquema SQLite, manifiesto, `universe.yaml`);
- toca `advisor/research/`, calendarios, fechado de sesiones, `classify()`,
  `compute_levels*`, `compute_score`;
- tiene consecuencias estadísticas o de look-ahead;
- la ficha dice «Opus diseña».

Entonces: Opus escribe/valida la sección «Implementación requerida» de la
ficha (contrato, invariantes, tests con números), Codex implementa, Opus
revisa con `PROMPT_REVIEW` intentando refutar.

### Cuándo basta un solo agente

- Codex solo: la ficha ya tiene contrato cerrado y la tarea no entra en la
  lista de arriba (T-001, T-002 salvo la revisión final, T-006).
- Opus solo: diagnóstico, investigación, documentación, decisiones (T-004,
  A-01, A-02…). Si del diagnóstico sale un cambio mecánico grande, lo
  delega a Codex con una ficha nueva.

### Claude Code

Puede actuar como Opus o como Codex según el prompt que reciba; usa el
subagente `revisor` para la revisión independiente y sigue exactamente los
mismos prompts.

---

## 2. Prohibición de decisiones silenciosas

Ningún agente inventa una decisión de producto o de investigación. Si la
ficha, el decision log y el protocolo no la resuelven:

1. Comprobar si es **técnica reversible** (sección 6 de `docs/metodo-trabajo.md`):
   entonces se decide, se anota en la ficha y, si afecta a más tareas, en el
   decision log con `D-nn`.
2. Si es **metodológica**: se propone en el decision log como `D-nn
   (propuesta)` con alternativas, y se pide revisión independiente antes de
   medir.
3. Si es **de propietario**: se escribe en `docs/decision-log.md` con este
   formato y la tarea pasa a `BLOQUEADA_POR_OWNER`, **haciendo todo lo demás**:

```markdown
### OD-nn — <título>
- **Pregunta:** <pregunta exacta, cerrada>
- **Alternativas:** (a) … (b) … (c) …
- **Consecuencia:** (a) … (b) … (c) …
- **Recomendación técnica:** <una>, y qué se hace si no hay respuesta en N días
- **Bloquea:** <tareas/gates>
```

---

## 3. Prompts operativos

Copiar literalmente. Sustituir solo lo que va entre `<>`.

### PROMPT_OPUS_TASK

```text
Eres Opus trabajando en el repositorio `intradia-bot` (hernn72/intradia-bot).
Tu tarea es la ficha <FICHA>. No hagas nada que la ficha no pida.

Antes de tocar código, lee en este orden y no te saltes ninguno:
1. docs/roadmap.md (estado, orden, dependencias, sección «Universo»)
2. docs/metodo-trabajo.md (ciclo de 11 pasos, invariantes INV-xx, política de
   defectos, commits, revisión, definición de terminado)
3. docs/decision-log.md (decisiones D-xx que la ficha cite; OD/OA abiertas)
4. docs/gates.md (el gate al que contribuye la ficha)
5. la ficha completa
6. docs/protocolo-investigacion.md si la ficha toca advisor/research/

Reglas que no se negocian:
- El código es la fuente de verdad sobre lo que hace el sistema. No asumas
  rutas: localiza símbolos con grep antes de editar.
- Ejecuta la línea base ANTES de cambiar nada (paso 3 del método) y guárdala
  en evidence/<fecha>-<tarea>/. Si la línea base falla, es BLOCKER: para y
  documenta.
- No alteres reglas, umbrales, pesos ni contratos fuera del alcance de la
  ficha. Si el trabajo lo exige, es una decisión: sección 6 del método.
- Lo desconocido se declara desconocido (INV-16). Nunca unknown→no, None→0.
- Toda regla nueva lleva test con números cerrados calculados a mano.
- Después de los tests, ejecuta el sistema contra datos reales, comprueba a
  mano al menos un número y escríbelo en la ficha.
- Mide el impacto: activos y señales afectados por motivo, antes/después.
- Clasifica todo hallazgo ajeno: BLOCKER / SAME_SCOPE / FOLLOW_UP / OBSERVATION.
- Decisiones que solo el propietario puede tomar: formato OD-nn en el decision
  log, tarea BLOQUEADA_POR_OWNER, y haces todo lo demás.
- No commitees en main; rama nueva desde main con el nombre de la ficha.
- No uses la palabra «verificado» para algo que solo has leído.

Entrega:
1. Ficha actualizada: estado, evidencia, impacto, invariantes marcadas,
   hallazgos clasificados, handoff.
2. evidence/<fecha>-<tarea>/README.md con comandos, commit, instante y
   conclusión; salidas antes/después.
3. Commit(s) en la rama indicada por la ficha, mensaje causa→efecto.
4. Fila de estado en docs/roadmap.md y entradas del decision log si procede.
5. Si la ficha exige revisión independiente: deja el diff y la ficha listos y
   escribe en el handoff «PENDIENTE DE REVISIÓN: <qué debe intentar refutar>».

Termina con el bloque:
ESTADO: <ACEPTADA|EN_REVISION|BLOQUEADA_POR_OWNER|RECHAZADA>
VERIFICADO A MANO: <el número y el cálculo>
IMPACTO: <activos/señales por motivo>
HALLAZGOS: <lista clasificada o "ninguno">
SIGUIENTE: <ficha siguiente y agente>
```

### PROMPT_CODEX_TASK

```text
Eres Codex trabajando en el repositorio `intradia-bot` (hernn72/intradia-bot).
Tu tarea es la ficha <FICHA>. Implementa exactamente lo que la sección
«Implementación requerida» especifica; no rediseñes.

Lee antes, en este orden: docs/roadmap.md (solo «Estado» y «Qué hacer
ahora»), docs/metodo-trabajo.md entero, la ficha entera, y las decisiones
D-xx que la ficha cite en docs/decision-log.md.

Reglas que no se negocian:
- No asumas rutas ni nombres: grep -rn "def <símbolo>" advisor tests antes de
  editar. Si la ficha nombra un fichero que no existe, dilo y localiza el real.
- Ejecuta la línea base antes de cambiar nada:
    source .venv/bin/activate && python -m pytest -q && ruff check . && mypy advisor
  y el comando de datos reales que la ficha indique; guarda la salida en
  evidence/<fecha>-<tarea>/antes.txt. Si algo falla antes de tocar nada,
  BLOCKER: para y documenta.
- Cambio mínimo. No toques funciones, umbrales, pesos ni ficheros listados en
  «Qué NO debe modificarse». No añadas excepciones por ticker ni por fecha.
- Una función, varios llamantes: no dupliques cálculo entre producción e
  investigación (INV-06).
- Todo test nuevo con números cerrados calculados a mano y escritos en el
  test. Los fixtures se parecen a universe.yaml (trade_republic: unknown,
  isin null, plazas europeas con zona horaria).
- Sin print(), sin TODO sin ficha, sin código muerto, sin dependencias nuevas
  salvo las que la ficha autoriza.
- Después de pytest/ruff/mypy en verde, ejecuta el comando de datos reales de
  la ficha, guarda despues.txt y comprueba a mano el número que la ficha pide.
- Mide el impacto comparando antes.txt y despues.txt: activos y señales que
  cambian, por motivo.
- Hallazgos ajenos: clasifícalos (BLOCKER / SAME_SCOPE / FOLLOW_UP /
  OBSERVATION) y no los arregles salvo SAME_SCOPE.
- Si necesitas una decisión que la ficha no resuelve, NO la tomes: escríbela
  en el handoff como «DECISIÓN PENDIENTE» con alternativas y para.
- Rama nueva desde main con el nombre que da la ficha; commits compilables;
  nunca sobre main; nunca force-push.

Entrega:
1. Código + tests en la rama; pytest -q, ruff check ., mypy advisor limpios;
   CI en verde si existe.
2. evidence/<fecha>-<tarea>/ con README.md (comando, commit, instante,
   conclusión), antes.txt, despues.txt.
3. Ficha con: estado EN_REVISION (o ACEPTADA si la ficha no exige revisión),
   invariantes marcadas, impacto, hallazgos, handoff.
4. Fila de estado en docs/roadmap.md.

Termina con el bloque:
ESTADO: <EN_REVISION|ACEPTADA|BLOQUEADA|RECHAZADA>
TESTS: <n pasan / n saltados> · RUFF: <ok> · MYPY: <ok>
VERIFICADO A MANO: <número y cálculo>
IMPACTO: <activos/señales por motivo>
HALLAZGOS: <lista clasificada o "ninguno">
DECISIONES PENDIENTES: <lista o "ninguna">
SIGUIENTE: <revisor o ficha siguiente>
```

### PROMPT_REVIEW

```text
Eres el revisor independiente de la ficha <FICHA> en `intradia-bot`. Tu
trabajo es intentar demostrar que la entrega es incorrecta, no confirmarla.

Lee: la ficha completa (incluido el handoff), docs/metodo-trabajo.md
(secciones 2, 5 y 8), las decisiones D-xx citadas, el diff (`git diff
main...<rama>`) y evidence/<fecha>-<tarea>/.

Haz, como mínimo:
1. Reproducir la línea base y la salida «después» con los comandos de la
   ficha. Si no puedes reproducir un número de la evidencia, es un hallazgo.
2. Recalcular a mano un número distinto del que el autor comprobó.
3. Para cada invariante marcada en la ficha, buscar un caso que la rompa
   (fixture con unknown/None/festivo/fin de semana/zona horaria/guion).
4. Buscar look-ahead: shift(-1), rolling centrado, uso de datos posteriores a
   la barra, benchmark como calendario, fechas normalizadas en UTC.
5. Buscar duplicación entre producción e investigación del mismo cálculo.
6. Comprobar que el score no cambia por calidad, broker ni ejecución (INV-03).
7. Comprobar que ningún fixture usa valores «cómodos» que el universo real no tiene.
8. Comprobar que la medición de impacto es completa (todos los activos que
   cambian tienen motivo).

Devuelve SOLO hallazgos clasificados (BLOCKER / SAME_SCOPE / FOLLOW_UP /
OBSERVATION), cada uno con reproducción exacta (comando, fixture o cálculo).
Si no encuentras ninguno, di qué intentaste y por qué falló cada intento.
Termina con: VEREDICTO: <ACEPTAR|CORREGIR|RECHAZAR> y, si CORREGIR, la lista
mínima de correcciones para aceptar.
```

---

## 4. Handoff

Al terminar, el agente rellena la sección «Handoff al siguiente agente» de la
ficha con exactamente estos apartados:

```markdown
## Handoff al siguiente agente
- Estado: <…>  ·  Commit: <sha>  ·  Rama: <…>
- Verificado (comando + número comprobado a mano):
- Impacto medido:
- Invariantes ejercitadas: INV-.. (test/salida) · No aplican: INV-..
- Hallazgos: BLOCKER: … · SAME_SCOPE (arreglados): … · FOLLOW_UP (fichas creadas): … · OBSERVATION: …
- Decisiones tomadas (D-nn) / pendientes (OD-nn):
- Qué queda de esta ficha (si algo):
- Siguiente ficha y agente recomendado:
- Trampas para el siguiente: <lo que te costó descubrir>
```

---

## 5. Cola de tareas

Fichas completas en `docs/tareas/`. Orden y paralelismo en
`docs/roadmap.md`, sección «Qué hacer ahora».

| Ficha | Agente | Depende de | Contribuye a |
|---|---|---|---|
| T-001 CI en GitHub Actions | Codex | — | GATE L0 (7), GATE PROD (1) |
| T-002 Migraciones y manifiesto | Codex → Opus | T-001 | GATE L0 (6), GATE PROD (3, 4) |
| T-003 Calendarios de plaza y cripto 24/7 | Codex → Opus | T-002 | GATE L0 (2) |
| T-004 Investigar huecos 2026-09-07 y 2026-03-06 | Opus | T-003 | GATE L0 (2), OD-02 |
| T-005 Calidad del dato por dimensiones y códigos | Opus → Codex → Opus | T-002, T-003, T-004 | GATE L0 (3) |
| T-006 `universe_vintage_id` e identidad | Codex → Opus | T-002 | GATE P2 (3), GATE B0 |

Siguientes fichas por escribir (las escribe Opus al llegar, con la plantilla):
T-007 PR 4 fases 9–11 (estado de mercado, reevaluación, broker e ISIN de
`EXH1.DE`); T-008 PR 5 fases 12–13 (informe e invariantes de integración);
T-009 fase 14 (filtro de ejecución medido aparte del score, incluida la
pérdida por `ABOVE_MAX_ENTRY` a la apertura, decisión D-06); T-010 fase 15 +
cierre de GATE L0; T-011 C-03 despliegue por tag y rollback; T-012 A-01
histórico de frescura de la Pi; T-013 A-02 rehacer P2.3/P2.4/P2.5 → GATE P2;
T-014 B-00 contrato point-in-time y ficha de proveedor.
