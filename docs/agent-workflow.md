# Flujo de trabajo de los agentes

Quién hace qué, con qué prompt, y por dónde se empieza. Complementa a
`docs/metodo-trabajo.md` (cómo se ejecuta una tarea) y a `docs/roadmap.md`
(qué se ejecuta y en qué orden).

---

## START HERE

```markdown
# START HERE — 2026-09-14

Estado actual:
- Rama `fix/execution-data-quality`, HEAD `e53e385`, 3 commits por delante de
  `main` (`6d32cf2`). Árbol limpio salvo `graphify-out/` (sin seguimiento).
- 398 tests, `ruff` y `mypy` limpios (verificado 2026-09-14, Python 3.12).
- PR 1 (fases 1–3 de la línea 0) hecho en rama. PR 2–5 pendientes.
- Laboratorio P2.0–P2.6 implementado, no congelado (GATE P2 abierto).
- La Pi corre `d795127` según `docs/pendientes.md`; NO verificado desde aquí.
- Línea base real capturada en `evidence/2026-09-14-L0-baseline/`.
- Esta documentación (método, gates, decisiones, fichas) está en el árbol de
  trabajo; el propietario decide si la commitea en esta rama antes del merge.

Primera acción del propietario (no de un agente):
- OA-01: mergear `fix/execution-data-quality` en `main` (fast-forward).

Primera tarea ejecutable:
- T-001 — CI en GitHub Actions. Ficha: docs/tareas/T-001-ci-github-actions.md

Quién debe hacerla:
- Codex

Prompt exacto:
- PROMPT_CODEX_TASK (abajo) con `<FICHA> = docs/tareas/T-001-ci-github-actions.md`

Qué debe devolver:
- Rama `ci/github-actions` con el workflow, run de CI en verde en 3.12 y 3.13,
  `evidence/<fecha>-T-001-ci/README.md`, ficha con handoff rellenado y el
  bloque de branch protection para OA-02.

Criterio para continuar:
- CI verde y ficha ACEPTADA → T-002 (Codex→Opus). Después, en paralelo:
  T-003 (Codex→Opus) y T-006 (Codex). Luego T-004 (Opus) y T-005
  (Opus→Codex→Opus). Orden completo en docs/roadmap.md, «Qué hacer ahora».
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
