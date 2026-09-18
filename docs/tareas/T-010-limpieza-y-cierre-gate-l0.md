# T-010 — Limpieza final y cierre de GATE L0 (PR 5, fase 15)

Estado: ACEPTADA — GATE L0 CRUZADO (2026-09-18, D-30)
Agente: Opus (ficha) → Codex (limpieza) → Opus (cierre del gate)
Línea / fase: L0 PR 5, fase 15 de `docs/plan-ejecucion.md`
Gate al que contribuye: **GATE L0 — es la ficha que lo cierra**

## Objetivo
Quitar lo que la línea 0 ha dejado por el camino —cálculos duplicados,
caminos muertos, excepciones temporales— y **demostrar, con la evidencia
delante, que los siete requisitos y las seis métricas de GATE L0 se cumplen**.
Si alguno no se cumple, la ficha no lo maquilla: lo declara y el gate no se
cruza.

## Por qué existe
Un gate que se cruza «porque las fichas anteriores están aceptadas» no es un
gate. `docs/gates.md` fija seis métricas contra
`evidence/2026-09-14-L0-baseline/`, y ninguna se ha vuelto a medir desde
entonces con el código completo: se midieron una a una, con el código a medias
de cada entrega. Esta ficha las mide **todas a la vez sobre `main`**, que es la
única medición que responde a la pregunta del gate.

Además, la línea 0 ha durado cinco entregas y ha dejado residuo identificable:
la fase 15 del plan lo enumera, y el roadmap tiene diez hallazgos abiertos sin
ficha que hay que resolver o convertir en ficha, no dejar flotando.

## Dependencias previas
T-007, T-008 y T-009 ACEPTADAS y en `main`. C-00, C-01 y C-02 aceptadas (lo
están). Si alguna no lo está, esta ficha **no empieza**.

## Archivos probables
Todo el árbol: es una ficha de limpieza. Puntos de partida:
- `advisor/analysis/levels.py`, `execution.py`, `sizing.py` — RR y `entry_max`.
- `advisor/data/sessions.py`, `calendars.py` — calendario y benchmark.
- `advisor/report/formatter.py` — restos de la fase 12.
- `advisor/backtest/`, `advisor/research/` — duplicación producción/laboratorio.

## Invariantes que no pueden romperse
Todas. Esta ficha las comprueba una por una; ninguna se relaja para cerrar el
gate.

## Implementación requerida

### 1. La lista de la fase 15, cada punto con su prueba
No basta con marcar la casilla: cada línea lleva **el comando que demuestra
que está hecho**, y su salida va a la evidencia.

- [ ] Ningún cálculo de RR duplicado →
      `grep -rn "target.*-.*entry\|/ (entry" advisor` revisado uno a uno; el
      único cálculo vive en `reward_risk` y todos los llamantes lo usan
      (INV-06).
- [ ] Ningún cálculo antiguo de `entry_max` fuera de `compute_levels`.
- [ ] El benchmark no se usa como calendario en ningún camino (INV-05).
- [ ] Cero excepciones temporales por fecha o por ticker: buscar `2026-09-07`,
      `2026-03-06`, `EXH1`, `AZN`, `TSM`, `005930` en `advisor/` y justificar
      cada aparición (los `exchange_overrides.yaml` **sí** son legítimos:
      llevan fuente obligatoria y son datos, no código).
- [ ] Cero `print()` y cero `TODO`/`FIXME` sin ficha asociada en `advisor/`.
- [ ] Cero código muerto: funciones sin llamante, ramas inalcanzables,
      constantes huérfanas.
- [ ] `mypy advisor` limpio y **sin `type: ignore` nuevos** respecto a la
      línea base; los que había, contados y justificados.
- [ ] `ruff check .` limpio.
- [ ] Suite completa verde, y verde **también en un clon limpio**:
      `git archive HEAD | tar -x -C <dir aparte>` y ejecutarla allí. Una suite
      verde en el portátil no dice nada del CI (lección del 2026-09-17: el
      `manifest.json` de la cosecha hizo fallar tres tests en clon limpio).
- [ ] Informe completo de los 107 sin error, en los dos horizontes.
- [ ] Comparación antes/después con la línea base del gate.

### 2. Los diez hallazgos abiertos del roadmap, resueltos o con ficha
La sección «Hallazgos abiertos» de `docs/roadmap.md` tiene diez entradas sin
ficha. Cada una sale de esta entrega en uno de tres estados, y ninguna se
queda como está:

- **Arreglada aquí** (si es de una línea y de esta línea de trabajo): el
  `capital:` vacío documentado, la cabecera de
  `docs/protocolo-investigacion.md`, el informe que no dice qué tope de sizing
  manda (si T-008 no lo dejó cerrado).
- **Convertida en ficha** (si es trabajo de verdad): `git_dirty` nullable
  (exige migración), `config_hash` con `db_path`/`universe_path` dentro,
  `backup_log` fuera de la lista de migraciones, los seis índices que no
  alimentan el contexto, `economic_currency` sin usar, el dividendo en
  horizonte medio, `analizar --grupos X` declarando el vintage entero, y
  `capacidad-estadistica` sin vintage (si T-009 no lo cerró).
- **Cerrada como no-problema**, con el motivo escrito.

### 3. Las seis métricas de GATE L0, medidas de nuevo y juntas
Contra `evidence/2026-09-14-L0-baseline/`, con el código de `main` completo:

| Métrica | Valor de aceptación |
|---|---|
| Activos con falsos huecos por festivo ajeno | 0 |
| Activos `INCOMPLETO` por el 2026-09-07 | explicados uno a uno con su causa |
| `reward_risk(entry_max, target2, stop) < min_rr` en la salida real | 0 casos |
| Fichas con «Precio actual» cuando solo hay cierre | 0 |
| Descartes sin código de motivo | 0 |
| Recomendaciones persistidas sin `run_id` | 0 desde la migración |

Cada una con el comando que la produce y su salida. La tercera y la quinta se
miden **sobre los 107 reales**, no sobre fixtures.

### 4. Los siete requisitos del gate, uno a uno
Copiar los siete de `docs/gates.md` y responder cada uno con la evidencia
concreta (commit, comando, salida). El requisito 4 incluye el ISIN de
`EXH1.DE` = `DE000A0H08M3`, ya verificado contra la ficha del emisor el
2026-09-18.

### 5. Los 27 criterios finales del plan de ejecución
`docs/plan-ejecucion.md` termina con una lista de 27 casillas. Se marcan una a
una **con la prueba al lado**, y las que no se cumplan se declaran abiertas con
su motivo. Incluye el caso de regresión obligatorio `EXH1.DE`:

```text
entry 55,76 → ejecutable por RR
entry 56,00 → ejecutable por RR
entry 56,11 → límite
entry 56,63 → NO ejecutable, motivo RR_TOO_LOW
```

### 6. Veredicto del gate
La ficha termina con `GATE L0: CRUZADO` o `GATE L0: NO CRUZADO`, y en el
segundo caso la lista exacta de lo que falta. **Un gate que se cruza con
excepciones no está cruzado.** Si se cruza, se registra la decisión D-nn y se
desbloquea A-02 (T-013) en el roadmap.

## Qué NO debe modificarse
Nada de comportamiento. Esta ficha **no cambia una sola decisión del sistema**:
si la limpieza mueve un número del informe o una operación del backtest, es un
defecto y se investiga antes de continuar. La prueba de que la limpieza está
bien hecha es que la salida es idéntica byte a byte salvo lo que la propia
ficha declare.

## Tests unitarios
- La suite existente al completo, sin excepciones ni `skip` nuevos.
- `test_no_hay_prints_ni_todos_sin_ficha_en_advisor`: test de higiene que
  recorre el árbol. Debe fallar si alguien mete un `print()` mañana.
- `test_exh1_regresion_de_la_linea_0`: los cuatro precios de arriba con sus
  cuatro veredictos, números cerrados.
- `test_la_suite_no_depende_de_ficheros_ignorados`: comprobación de que
  ningún test necesita `data/vintages/` presente para pasar (o, si lo
  necesita, que se salta de forma explícita y declarada).

## Verificación contra datos reales
```bash
.venv/bin/python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar
.venv/bin/python -m advisor.main analizar --horizonte medio --sin-ia --sin-guardar
.venv/bin/python -m advisor.main backtest --horizonte swing --period 5y
.venv/bin/python -m advisor.main frescura-datos
.venv/bin/python -m advisor.main manifiesto --ultima
git archive HEAD | tar -x -C /tmp/clon-limpio && cd /tmp/clon-limpio && python -m pytest -q
```

## Medición del impacto
- Cambios de acción respecto a la pasada anterior: **0**. Es el criterio.
- Líneas eliminadas por la limpieza, por categoría.
- Hallazgos abiertos: cuántos arreglados, cuántos convertidos en ficha,
  cuántos cerrados como no-problema. La suma debe ser 10.

## Criterio de aceptación
- Las seis métricas del gate cumplen su valor de aceptación, medidas juntas.
- Los siete requisitos respondidos con evidencia.
- Los 27 criterios del plan marcados o declarados abiertos con motivo.
- La suite pasa también en clon limpio.
- Ningún cambio de comportamiento.

## Criterio de rechazo
- Cruzar el gate «con excepciones».
- Marcar una casilla sin el comando que la demuestra.
- Un hallazgo abierto que siga abierto sin ficha y sin motivo.
- Cualquier cambio de salida no declarado.

## Evidencia que debe quedar registrada
`evidence/<fecha>-L0-cierre/` —el nombre que `docs/gates.md` exige— con
README.md, `antes.txt` (la línea base del 2026-09-14), `despues.txt`, la tabla
de activos por motivo, la tabla de la fase 14, la salida de la fase 15, las
seis métricas con su comando, los siete requisitos respondidos y el veredicto.

## Commit esperado
Rama `chore/l0-cleanup`. Mensaje:
`chore(l0): limpieza final y cierre de GATE L0 con las seis metricas medidas juntas`

## Actualización documental requerida
`docs/roadmap.md`: PR 5 (fase 15) a ACEPTADA, GATE L0 marcado, y la línea A
desbloqueada (A-02 pasa de `BLOQUEADO(GATE L0, A-00)` a `PENDIENTE`).
`docs/gates.md`: GATE L0 con fecha, commit y veredicto.
`docs/decision-log.md`: D-nn con el veredicto del gate.
`docs/agent-workflow.md`: START HERE reescrito con el punto de retomada.

## Handoff al siguiente agente
- Estado: ACEPTADA, GATE L0 CRUZADO · Rama: `chore/l0-cleanup` · Evidencia: `evidence/2026-09-18-L0-cierre/`
- Verificado (comando + número comprobado a mano): las seis métricas en el README, cada una con su script o su consulta. A mano: la métrica 6 se comprobó en la Pi mirando el corte de fechas (última fila sin `run_id` 2026-09-14T07:32, primera con él 09:38 del mismo día); la 1 recorriendo las 37 ausencias contra `expected_sessions` de la plaza de cada activo.
- Impacto medido: 0 cambios de acción; tres funciones huérfanas borradas sin efecto en la suite (548 pasan) ni en el informe.
- Invariantes ejercitadas: INV-03, INV-05, INV-06, INV-16, INV-17 (todas por las métricas y los tests de higiene). No aplican: ninguna se relajó.
- Hallazgos: BLOCKER: ninguno · SAME_SCOPE (arreglados): `apply_migrations` migraba sin backup, borrada; casilla EXH1 del plan anterior a PR 1, corregida con D-29 · FOLLOW_UP (fichas): T-015 backtest no reproducible, T-016 centinela `[0,1]` en `capacity.py`, T-017 higiene del manifiesto · OBSERVATION: la métrica 4 solo tiene 2 fichas por pasada; `ruff check .` cubre `evidence/`, así que los scripts que se dejen ahí deben pasar lint (el CI lo cazó hoy).
- Decisiones tomadas (D-nn) / pendientes (OD-nn): D-29 cerrada (opción a), D-30 gate cruzado. Pendientes del propietario: OA-04 desplegar la línea 0 en la Pi (está en `894fa75`, cuatro entregas por detrás); OD-09/OD-10 esperan la cifra de T-012.
- Qué queda de esta ficha: nada.
- Siguiente ficha y agente recomendado: **T-016** (Codex → Opus) antes de A-02, porque el veredicto de P2.5 puede llevar un intervalo falso. En paralelo T-011 + T-017 con una sola migración, y T-012 para dar cifra a OD-09/OD-10.
- Trampas para el siguiente: la métrica 6 no se puede medir en el portátil (aquí no se guarda nada); el backtest en vivo no sirve como criterio de aceptación de nada (T-015); `git archive HEAD | tar -x` es la única forma de saber lo que verá el CI.
