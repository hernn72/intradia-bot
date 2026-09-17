# Flujo de trabajo de los agentes

Quién hace qué, con qué prompt, y por dónde se empieza. Complementa a
`docs/metodo-trabajo.md` (cómo se ejecuta una tarea) y a `docs/roadmap.md`
(qué se ejecuta y en qué orden).

---

## START HERE

```markdown
# START HERE — actualizado 2026-09-17 (cierre del día; OA-03 casi cerrada)

## Dónde está todo

    main / origin/main / la Pi    894fa75    las tres alineadas, CI verde
    graphify-out/                 sin seguimiento, ignorar

Nada pendiente de commitear. La Pi corre lo mismo que `main`, con esquema v4 y
los timers vivos.

## Lo que entró hoy, de abajo arriba

    572192c  T-005: las 5 correcciones de su 2.ª revisión independiente
    6e7eaa5  despliegue de T-004 y T-005 en la Pi (migración v3→v4 verificada)
    5de38c2  D-22 validada con Codex; resuelto el added_at de los 8 renombrados
    e0bff6b  T-006: identidad de instrumentos y universe_vintage_id canónico
    cc9341f  T-006: las 3 correcciones de su revisión (una era un BLOCKER de CI)
    4f07829  OA-03 primera tanda: 19 ISIN verificados en la app del broker
    3ece8f1  punto de retomada
    5125e90  OA-03 segunda tanda: 52 ISIN y 48 disponibilidades
    54ac004  BTC-EUR sí está disponible (corrección del propietario)
    ae39c6c  punto de retomada
    894fa75  OA-03 tercera tanda: 92 ISIN, 95 disponibles, el universo cubierto

Vintage actual del universo: `894ce776…`. Cambia con cada tanda de OA-03,
y el test `test_universe_real_tiene_107_analizables_y_vintage_conocido` se
actualiza a propósito con cada una.

## Por dónde seguir, en orden

1. **T-007** (PR 4) está **escrita y sin implementar**:
   `docs/tareas/T-007-estado-de-mercado-y-broker.md`. Lleva dentro un defecto
   medido hoy que **no estaba en ningún plan**: `trim_unclosed_bar` compara
   contra el cierre **regular** de la plaza, así que en un día de media sesión
   descarta una barra ya cerrada. No ha mordido nunca —el bot nació en agosto—
   y muerde por primera vez el **2026-11-27** (NYSE y NASDAQ cierran a las
   13:00), luego el 24, 30 y 31 de diciembre con ocho plazas. Hay margen hasta
   finales de noviembre y ni un día más.
   Ojo: la ficha corrige un error propio. NO añadir `open_time` a mano a
   `MARKET_SESSIONS`: `exchange_calendars` ya da apertura y cierre, y sus 14
   cierres coinciden exactamente con los hardcodeados. Copiarlos sería una
   segunda fuente de verdad (INV-06).
2. **OA-03 está prácticamente cerrada.** 92 con ISIN verificado, 95
   disponibles, 10 no disponibles, 3 no aplicable. Solo faltan:
   - `UCG.MI` y `1211.HK`, sin comprobar en la app.
   - `SAN.MC` y `005930.KS`, en **`PENDIENTE_ADR`**: el propietario aportó el
     ISIN del ADR/GDR estadounidense, pero el bot analiza la acción local en
     Madrid y en Seúl. Hay que decidir si se registra el ADR anotando la
     diferencia o se cambia el símbolo analizado. Mismo problema que `TSM` e
     `INFY`. **Decisión pendiente del propietario, no la tome un agente.**
   - Nueve sin ISIN por estar marcados no disponibles, que es coherente.

   Efecto en producción: `EXECUTABLE` pasó de 0 a **51** y `BROKER_UNVERIFIED`
   de 57 a **1**. Lo que frena ahora al asesor es la calidad del dato —28
   `MISSING_RECENT_DATA`, 18 `STALE_DATA`, 3 `PARTIAL_BAR`—, nunca el broker.

3. **T-008..T-010** (PR 5) siguen **sin ficha**; las escribe Opus.

## Decisiones del propietario pendientes

- **OA-02** — branch protection en GitHub, sin hacer. `main` recibió seis
  commits hoy y sigue admitiendo push directo y force-push.
- **OD-09** (horario de las pasadas) y **OD-10** (cripto), abiertas desde ayer.
  Ahora se deciden con datos: con **24 activos ya `EXECUTABLE`**, lo que frena a
  los europeos es `STALE_DATA` y `MISSING_RECENT_DATA`, y a las criptos
  `PARTIAL_BAR`. Ninguna de las dos cosas es el broker. `BTC-EUR` está
  disponible y aun así no es recomendable por su barra 24/7: eso es OD-10 en
  estado puro.

## Dos hallazgos abiertos que no son de ninguna ficha

- `analizar --grupos X` declara el vintage del universo **entero**, no el del
  subconjunto analizado.
- El informe de `capacidad-estadistica` no publica ningún vintage, así que un
  veredicto de GATE no es atribuible a ninguna cosecha.

## Cómo se trabajó hoy, y qué repetir

Las tres capas siguieron encontrando cosas distintas, y **la revisión
independiente encontró defectos en las dos entregas**, incluidos dos errores
míos: afirmé en una evidencia que una guarda empezaría a proteger con la
próxima cosecha cuando el campo no lo escribía nadie, y mi comprobación manual
del benchmark tocó justo el único caso que ya funcionaba. Verificar contra
datos reales no basta si la comprobación se apoya en el mismo punto ciego.

Tres trampas concretas que volverán:
- Revertir un defecto inyectado con `git checkout -- <fichero>` **borra las
  correcciones sin commitear**. Copiar a /tmp y restaurar desde ahí.
- `trade_republic: yes` sin comillas lo lee YAML como booleano y la carga falla.
- Una suite verde en el portátil no dice nada del CI: comprobar con
  `git archive HEAD | tar -x` en un directorio aparte.

**Codex**: disponible otra vez, comprobado al cierre del 2026-09-17. Agota la
cuota con facilidad y la recupera a las ~13:48.
Su sandbox **no puede escribir refs de git**, así que hay que crearle la rama
antes y commitear por él. Y `codex exec` se cuelga esperando stdin si no se
cierra con `< /dev/null`; `--full-auto` no existe en la 0.150.1, se usa
`--sandbox workspace-write -c sandbox_workspace_write.network_access=true`.
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
