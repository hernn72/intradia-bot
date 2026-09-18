# Flujo de trabajo de los agentes

Quién hace qué, con qué prompt, y por dónde se empieza. Complementa a
`docs/metodo-trabajo.md` (cómo se ejecuta una tarea) y a `docs/roadmap.md`
(qué se ejecuta y en qué orden).

---

## START HERE

```markdown
# START HERE — actualizado 2026-09-18 (GATE L0 cruzado)

## Dónde está todo

    main / origin/main    bde784d    CI verde, branch protection activa (OA-02 HECHA)
    la Pi                 c2ff1d7                  AL DÍA (desplegada 2026-09-18 12:30 BST, OA-04 hecha)
    graphify-out/         sin seguimiento, ignorar

Desde OA-02 **todo entra por PR**: push de la rama → PR → dos checks → merge
con rebase. El push directo a `main` está bloqueado también para el propietario.

## Lo que entró hoy, de abajo arriba

    c314729  T-007 estado de plaza, precio ejecutable y broker (+ revisión: BLOCKER en la población del backtest)
    36f7260  fichas T-008..T-012
    6fbeed0  T-008 informe por capas y siete invariantes (+ revisión: invariante 1 vacua, cambio de contrato revertido)
    3ac1fb8  T-009 filtro de ejecución medido (+ revisión: centinela [0,1] publicado como intervalo)
    d8cbc37  arreglo de lint en evidencia (el CI lo cazó)
    bde784d  T-010 limpieza y cierre de GATE L0

**GATE L0 CRUZADO** (D-30). Evidencia en `evidence/2026-09-18-L0-cierre/`.

## Por dónde seguir, en orden

1. ~~OA-04~~ **hecha**: la Pi corre `c2ff1d7`, evidencia en `evidence/2026-09-18-despliegue-pi/`.
2. **T-013 (A-02)** → GATE P2. **Desbloqueada**: la auditoría de T-016
   (2026-09-18) midió **0 celdas afectadas** por el centinela en el veredicto de
   P2.5, así que no arrastra nada inválido. Ojo al cambio de población: 107 → 103
   por D-31, y la comparación con lo ya publicado debe declararlo.
3. **T-011 + T-017** juntas (Codex → Opus), una sola migración v4→v5:
   release por tag y rollback probado, más `git_dirty` nullable,
   `config_hash` sin rutas, `backup_log` migrado y vintage por grupo.
4. **T-012** (Codex → Opus → propietario): la cifra de OD-02/OD-09/OD-10.
5. **T-015**: backtest sobre cosecha congelada. Conviene antes de A-02 si va a
   comparar poblaciones.
6. **T-016**: higiene del centinela, ya sin urgencia.

## Decisiones del propietario pendientes

- **OD-09** y **OD-10** — esperan la cifra de T-012.
- ~~`SAN.MC`, `005930.KS`, `UCG.MI`, `1211.HK`~~ — **resuelto (D-31)**: baja por no estar en el broker. Universo: 103 analizables, vintage `c8496446…`.

## Tres cifras de hoy que cambian cómo se piensa el asesor

- **El RR mínimo manda en 102 de los 107** (T-008): `entry_max_atr` interviene en menos del 5 %.
- **El filtro de ejecución rechaza más de la mitad de lo que el score aprueba**, y lo ejecutado rinde 0,21 R frente a 0,12 de lo rechazado, con intervalos solapados (T-009).
- **`RR_TOO_LOW` es inalcanzable: 0 de 2.151** (T-009, D-29). Se conserva como guarda para P4.

## Cómo se trabajó hoy, y qué repetir

Tres entregas de Codex, tres revisiones independientes, **las tres CORREGIR**, y
en cada una el defecto fue del mismo tipo: algo que la suite verde no veía.

- T-007: la acción nueva sacaba activos de la población del backtest en silencio.
- T-008: una invariante vacua (un caso bueno sale bueno) y un cambio de contrato
  colado como SAME_SCOPE.
- T-009: un centinela publicado como intervalo. Y el propio Codex bloqueó con
  razón: el backtest en vivo no es reproducible.

Reglas que salieron de hoy, ya en los prompts:
- **SAME_SCOPE significa dentro del alcance de la ficha, no «me venía bien».**
  Si cambia un contrato, un código persistido o una decisión registrada, no lo es.
- **Una invariante se comprueba inyectando el defecto y ejecutando**, con la
  salida guardada. «Revisé que la aserción toca el campo» se devuelve.
- **Verifica lo que vas a commitear, no lo que había antes de añadir el último
  fichero.** `ruff check .` cubre `evidence/`; el CI cazó un script sin lint.
- **La métrica 6 solo se mide en la Pi.** Aquí no se guarda nada.
- **Codex** agota la cuota a media tarea (hoy a las ~11:00, vuelve a las 13:34)
  y deja el árbol sin commitear; lo que deja se puede terminar a mano si está
  bien especificado. Su sandbox no escribe refs: crearle la rama antes.
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
| T-007 Estado de mercado, precio ejecutable y broker | Codex → Opus | T-005, T-006 | GATE L0 (4) |
| T-008 Informe honesto e invariantes de integración | Codex → Opus | T-007 | GATE L0 (5) |
| T-009 Filtro de ejecución medido aparte del score | Codex → Opus | T-008 | GATE L0 (5) |
| T-010 Limpieza final y cierre de GATE L0 | Codex → Opus | T-009 | **GATE L0** |
| T-011 Release por tag, `verificar-release` y rollback | Codex → Opus → propietario | T-001 | GATE PROD (2, 7) |
| T-012 Histórico de frescura de la Pi | Codex → Opus → propietario | acceso a la Pi | OD-02, OD-09, OD-10 |

Escritas el 2026-09-18: T-008, T-009, T-010, T-011 y T-012. Quedan por escribir
T-013 (A-02, rehacer P2.3/P2.4/P2.5 → GATE P2) y T-014 (B-00, contrato
point-in-time y ficha de proveedor), más las de la línea C que salgan de T-010
(C-04 alertas y timeouts, C-05 narrativa LLM versionada, C-06 backup programado).
