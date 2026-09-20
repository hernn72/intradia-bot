# Flujo de trabajo de los agentes

Quién hace qué, con qué prompt, y por dónde se empieza. Complementa a
`docs/metodo-trabajo.md` (cómo se ejecuta una tarea) y a `docs/roadmap.md`
(qué se ejecuta y en qué orden).

---

## START HERE

```markdown
# START HERE — actualizado 2026-09-20 (cierre de jornada)

## Dónde está todo

    main / origin/main    este commit    CI verde
    la Pi                 v0.3.0 = 03e1ec3    esquema v5    EN_TAG  ← AL DÍA
    graphify-out/         sin seguimiento, ignorar

## Lo primero de mañana: T-013 (A-02), y una pregunta al propietario

**T-012 está ACEPTADA y OD-02 quedó cerrada el mismo día en D-40:** el
propietario eligió la lectura (c) —sesión cerrada y exigible que no está cuando
una pasada la necesita, aunque llegue después, contada una vez por activo y
sesión—, así que 47 activos cruzan el umbral de 10 y **sí hace falta respaldo,
solo para Europa**. Eso abre **C-09**, sin ficha todavía.

**La ficha de C-09 ya está escrita: `docs/tareas/T-018-cache-de-barras-validadas.md`**,
con las cinco reglas del propietario (D-41). El orden quedó decidido: **caché
local primero, segunda fuente condicionada**, porque el proveedor **retira por la
noche una barra que ya había servido** —`SAP.DE` el 14 a las 20:02 tiene la barra
del 14; a las 06:02 del 15 vuelve a la del 11; al mediodía reaparece— y el bot ya
vio ese dato la tarde anterior. T-018 produce además la cifra que decide si
encima se compra EODHD para precios: `sesión exigible + nunca observada + no
entregada`.

**Las dos van en paralelo y no se estorban:** T-013 es laboratorio y T-018 es
producción. Si hay que elegir una, T-013, porque es la que abre GATE P2.

**Lo siguiente que no depende de nadie es T-013 (A-02)**: rehacer P2.3, P2.4 y
P2.5 sobre la cosecha `071ddb2b…` → GATE P2. **La ficha no está escrita**; es lo
primero que hay que hacer. Tres avisos que ya se saben: la población pasa de 107
a 103 y a 93 (hay que declarar las tres), el backtest ya es reproducible con
`--vintage` (T-015) y D-29 quedó cerrada.

**Lo que T-012 dejó medido y cambia cómo se lee todo lo demás:** el retraso del
proveedor es **exclusivamente europeo** —278/329 mediciones europeas retrasadas a
las 06 UTC frente a **0/399** del resto del mundo, y 0 en todas partes a las 20
UTC—, y **la mayoría de los «huecos» son retrasos que acaban llegando**: al final
de la ventana solo quedan 9 activos con un hueco cada uno.

**Trampa nueva, para cualquier medición sobre el histórico de la Pi:** la ventana
cruza **14 versiones de código** y 1.177 mediciones no tienen manifiesto. Solo
una pasada usa la regla vigente de D-36/D-37. Agregar todo en una sola tasa
mezcla definiciones distintas de la métrica. `frescura-historico --resumen` ya lo
declara solo.

## Lo de ayer: el despliegue de v0.3.0

El despliegue ya no está pendiente. **`v0.3.0` se etiquetó y se desplegó el
2026-09-20**, con release publicado por CI y las tres verificaciones en verde en
la Pi; evidencia en `evidence/2026-09-20-despliegue-v030/`. No hubo migración:
entre `v0.2.0` y `v0.3.0` el esquema sigue en v5, así que un rollback sería solo
de código.

**La primera medición de D-21 en producción ya está hecha**, y es la que faltaba:
sobre 93 analizables, **68 `EXECUTABLE`, 21 `STALE_DATA` y 4
`MISSING_RECENT_DATA`**, y los 25 vetados son **todos europeos**. Japón y Hong
Kong no quedaron vetados en esa pasada, al contrario que el 18: era domingo y no
había sesión que reclamar. Lo que sigue sin medirse es el reparto **en cada una
de las cuatro pasadas diarias**, que necesita días de mercado y es material de
T-012.

El propietario autorizó desplegar sin preguntar cada vez: **la Pi está en fase de
pruebas y lo que recomiende es parte del desarrollo**.

**Cómo se opera desde T-011: la Pi no corre `main`, corre un tag.** Desde T-011, `main` puede ir por delante sin que eso signifique que
producción está desactualizada: lo que responde a «qué corre la Pi» es
`verificar-release`, que debe decir `EN_TAG` con código 0. Si dice
`FUERA_DE_TAG`, alguien hizo `git pull` donde tocaba `git checkout <tag>`.

Desplegar y volver atrás están escritos, con comandos literales, en
**`docs/despliegue-y-rollback.md`**. La regla que no se puede olvidar: **el
rollback de código no deshace migraciones** (D-32); si entre los dos tags hubo
una, se restaura el backup previo y se acepta lo que se pierde, contándolo antes.

Desde OA-02 **todo entra por PR**: rama → push → PR → dos checks →
`gh pr merge --rebase`. El push directo a `main` está bloqueado también para el
propietario, y `enforce_admins` está activo. Un tag `vX.Y.Z` empujado dispara
`release.yml`, que corre los mismos checks y publica el release.

## Lo que entró el 2026-09-18, de abajo arriba

    c314729  T-007 estado de plaza, precio ejecutable y broker
    36f7260  fichas T-008..T-012
    6fbeed0  T-008 informe por capas y las siete invariantes
    3ac1fb8  T-009 filtro de ejecución medido aparte del score
    d8cbc37  arreglo de lint en evidencia (lo cazó el CI)
    bde784d  T-010 limpieza y cierre de GATE L0
    7356db8  SHA real en el punto de retomada
    c2ff1d7  baja de SAN.MC, UCG.MI, 005930.KS y 1211.HK (D-31)
    6902d3d  despliegue en la Pi (OA-04)
    14fa732  auditoría del centinela: T-016 deja de bloquear A-02
    11efae8  punto de retomada  ·  etiquetado después como v0.1.0
    ba034d4  T-011 + T-017 en una sola migración v4→v5
    785daf4  corrección: un tag anotado daba FUERA_DE_TAG  ·  v0.2.0
    fe684e9  T-015: backtest reproducible sobre cosecha (D-34)
    3d0e611  D-35: baja de los diez marcados `no` → 93 analizables
    042b9de  D-36 y D-37: el veto se mide contra la última barra cerrada exigible

**GATE L0 CRUZADO** (D-30), evidencia en `evidence/2026-09-18-L0-cierre/`.
**Universo: 126 activos, 93 analizables** tras D-31 y D-35, vintage `237b0056…`.

**T-011 y T-017 ACEPTADAS**, con el ensayo de OA-04 hecho sobre la base real:
`evidence/2026-09-18-OA-04-ensayo-release/`. La Pi migró a esquema v5
conservando sus 25 manifiestos con `config_hash_version = 1`, y el rollback se
ejecutó de verdad (restaurar backup → `v0.1.0` → pasada real → volver a
`v0.2.0`).

## Por dónde seguir, en orden

**0.** ~~Etiquetar `v0.3.0` y desplegar~~ **HECHO** el 2026-09-20 (arriba).

0b. ~~**T-012** histórico de frescura~~ **ACEPTADA** (2026-09-20). OD-02 cerrada
   en D-40; abre **C-09**, el respaldo del EOD europeo, sin ficha.
1. ~~**T-015** backtest sobre cosecha congelada~~ **HECHA** (D-34): 866
   operaciones idénticas byte a byte frente a 869/862/867 en vivo el mismo día. Conviene **antes** de A-02 si
   A-02 va a comparar poblaciones, porque hoy el backtest en vivo da 891, 893 y
   890 operaciones en tres pasadas del mismo commit.
2. ~~**T-012**~~ **HECHA** (2026-09-20). La cifra de OD-02. Ya **no** decide
   OD-09 ni OD-10 —cerradas en D-36 y D-37—, pero sigue diciendo con qué
   frecuencia llega tarde cada plaza, que es lo que ahora determina el veto.
3. **T-013 (A-02)** → GATE P2. **Desbloqueada.** Dos avisos: la población pasa
   de 107 a 103 (D-31) y la comparación con lo publicado debe declararlo; y
   D-29 quedó cerrada, así que `RR_TOO_LOW` sigue existiendo como guarda de P4
   aunque hoy sea inalcanzable.
4. **T-016** higiene del centinela, sin urgencia: la auditoría midió 0 celdas
   afectadas en el veredicto de P2.5.
5. **T-014 (B-00)** contrato point-in-time, y **C-04** alertas, cuando toque.

## Decisiones del propietario pendientes

- ~~**OD-09** (horario de las pasadas) y **OD-10** (cripto)~~ **cerradas el
  2026-09-18** sin esperar a T-012, en D-36 y D-37: los horarios se mantienen,
  D-21 actúa por activo contra la última barra cerrada exigible, y una barra
  abierta se ignora en vez de vetar. T-012 sigue siendo útil para saber **con
  qué frecuencia** llega tarde cada plaza, pero ya no bloquea nada.
- ~~**OD-03** (presupuesto LLM)~~ **cerrada el 2026-09-20** en D-38: **10 €/mes**
  al principio, con caché y llamadas solo sobre los candidatos que ya pasaron los
  filtros cuantitativos. Desbloquea B-03 y B-06. Ojo a lo que **no** existe hoy:
  ni caché ni contador de gasto; la parte de «no indiscriminadamente» sí estaba
  hecha ya, porque la narrativa solo se pide para el top 5 de `OPERAR`.
- **OD-01** (proveedor de fundamentales), abierta **con un paso decidido**
  (D-39): se prueba **EODHD en su plan gratuito** con uno o dos valores europeos
  antes de pagar nada, y lo que decide entre (a) y (b) es si el JSON trae
  `filing_date`. **Sondeo ejecutado el 2026-09-20**
  (`evidence/2026-09-20-OD-01-eodhd-free/`): el plan gratuito **no** da
  fundamentales —403 en europeos y en EE. UU., mientras el EOD europeo sí
  responde con la misma clave, así que el límite es del plan—, pero el token
  público `demo` dejó ver el JSON real de `AAPL.US` y **`filing_date` está, por
  línea, en los tres estados financieros**. Falta lo único que decide: que venga
  **relleno para un europeo**, que pide un mes de plan de pago. **Ese gasto
  espera a T-012** (propietario, 2026-09-20): el EOD europeo de EODHD ya
  responde en el plan gratuito, así que un mismo plan podría cubrir OD-01 y
  OD-02 a la vez. Las dos se evalúan juntas con la cifra de T-012 delante.
- ~~**OD-02** (segunda fuente europea)~~ **cerrada el 2026-09-20** en D-40: hace
  falta respaldo y **solo para Europa**. Los 47 activos cruzan el umbral pero
  **no son una tasa fiable**: la ventana cruza 14 versiones de código y cada
  celda de 47 mediciones sale de **una sola pasada**, así que son 47 activos
  afectados por un mismo evento, no 47 observaciones independientes.
- **OD-08** (duración de P10), abierta con orientación: parar por tiempo **y**
  por señales cerradas (≥ 8 semanas y ≥ 100). Medido sobre la cosecha, 100
  señales cerradas piden 30-35 semanas: manda el número, no el calendario.
- ~~Los 10 activos marcados `no` en el broker~~ **decidido el 2026-09-18**:
  dados de baja (D-35). El universo analizable queda en **93** y ya no hay
  ningún analizable con `trade_republic: "no"`.

## Cuatro cifras de hoy que cambian cómo se piensa el asesor

- **El RR mínimo manda en 102 de los 107** (T-008): `entry_max_atr` interviene
  en menos del 5 % del universo.
- **El filtro de ejecución rechaza más de la mitad de lo que el score aprueba**;
  lo ejecutado rinde 0,21 R por bloque y lo rechazado 0,12 R, con intervalos
  solapados (T-009). Compatible con que proteja, no prueba de que proteja.
- **`RR_TOO_LOW` es inalcanzable: 0 de 2.151** señales perdidas (D-29).
- En producción, **`BROKER_UNVERIFIED` pasó de 57 a 0 y `EXECUTABLE` de 0 a 49**
  tras OA-03 y la baja.

## Codex también sirve para lo contrario: desmentir, no implementar

El 2026-09-18 por la tarde se invirtieron los papeles —Opus implementa, Codex
revisa en solo lectura— y funcionó mejor que las tres entregas de la mañana. En
T-011 encontró un BLOCKER que la suite verde no veía (`verificar-release`
aceptaba cualquier tag, no solo `vX.Y.Z`) y tres defectos más; y **supervisando
el plan de despliegue antes de ejecutarlo** evitó un paso que era teatro: correr
el código viejo contra la base ya migrada demuestra compatibilidad accidental,
no rollback.

Cómo se le pasa: exportar el diff a un fichero, decirle que **no escriba nada**
—hay un supervisor en el mismo árbol— y pedirle casos límite concretos, no una
opinión general.

## Cómo se le encarga una ficha a Codex (contexto operativo, no lo reinventes)

Al `PROMPT_CODEX_TASK` hay que añadirle siempre este bloque, o se pierde media
entrega:

- **Crearle la rama antes.** Su sandbox **no escribe refs de git**: nada de
  `git checkout`, `git branch` ni `git commit`. Deja el árbol sucio y el
  supervisor commitea por él.
- `codex exec --sandbox workspace-write -c sandbox_workspace_write.network_access=true "$(cat prompt)" < /dev/null`
  — sin `< /dev/null` se cuelga esperando stdin; `--full-auto` no existe en la 0.150.1.
- Decirle el venv (`.venv/bin/python`), el directorio de evidencia ya creado, y
  qué ficheros **no** debe tocar porque el supervisor trabaja en paralelo.
- **Agota la cuota a media tarea** (el 2026-09-18, a las ~11:00; volvió a las
  13:34) y deja la entrega a medias pero utilizable: se termina a mano si está
  bien especificada.

## Cómo se trabajó hoy, y qué repetir

Tres entregas de Codex, tres revisiones independientes, **las tres CORREGIR**, y
en las tres el defecto era algo que la suite verde no veía:

- **T-007**: la acción nueva `VERIFICAR_BROKER` sacaba activos de la población
  de `POLICY_OPERAR` del backtest en silencio, y los borraba de su informe.
- **T-008**: una invariante vacua —construía un caso bueno y comprobaba que era
  bueno— y un cambio de contrato colado como SAME_SCOPE, que además rehízo tres
  tests ya aceptados.
- **T-009**: un centinela `(0.0, 1.0)` publicado como intervalo de confianza. Y
  el propio Codex **bloqueó con razón**: el criterio de aceptación era
  inverificable porque el backtest en vivo no es reproducible.

Reglas que salieron de hoy, ya incorporadas a los prompts:

- **SAME_SCOPE significa dentro del alcance de la ficha, no «me venía bien».**
  Si cambia un contrato, un código persistido o una decisión registrada, no lo es.
- **Una invariante se comprueba inyectando el defecto y ejecutando**, con la
  salida guardada. «Revisé que la aserción toca el campo» se devuelve.
- **Una implicación se prueba por el lado que tiene dientes**: no que un caso
  bueno salga bueno, sino que al romper una capa la acción deja de ser COMPRAR.
- **Verifica lo que vas a commitear**, no lo que había antes de añadir el último
  fichero: `ruff check .` cubre `evidence/`, y el CI cazó un script sin lint.
- **Revertir un defecto inyectado con `git checkout -- <fichero>` borra las
  correcciones sin commitear.** Copiar a /tmp y restaurar desde ahí.
- **Antes de medir algo caro, comprueba si la pregunta ya tiene respuesta**: la
  auditoría de T-016 costó dos comandos y quitó una dependencia del camino
  crítico.

## Trampas de operación

- **La métrica de `run_id` solo se mide en la Pi**: en el portátil se corre
  siempre con `--sin-guardar`.
- **La Pi no tiene el CLI `sqlite3`**: consultar con
  `.venv/bin/python -c "import sqlite3..."`.
- **`analizable: false` sin `valid_to` convierte un activo en contexto** y lo
  mete en «Situación global». Una baja lleva `valid_to`; `context_assets_of` lo
  excluye.
- **`capacidad-estadistica` exige el vintage completo como posicional**;
  `filtro-ejecucion` acepta el prefijo con `--vintage`. Se unifica en T-016.
- **Desplegar antes del timer de las 14:30 BST**, para que la primera pasada con
  código nuevo sea supervisada y no automática.
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
