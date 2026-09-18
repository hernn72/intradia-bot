# Cierre de GATE L0 — 2026-09-18

Ficha: `docs/tareas/T-010-limpieza-y-cierre-gate-l0.md`. Rama `chore/l0-cleanup`
sobre `main` en `d8cbc37` (T-007, T-008 y T-009 ya fusionadas, CI verde).
Instantes de las pasadas reales: 10:48 y 10:55 UTC. Línea base de comparación:
`antes-baseline-2026-09-14.txt` (copiada de `evidence/2026-09-14-L0-baseline/`).

## VEREDICTO: GATE L0 CRUZADO

Los siete requisitos de `docs/gates.md` se cumplen con evidencia. Las seis
métricas dan su valor de aceptación, medidas **todas a la vez sobre el código
completo**, y dos de ellas llevan una precisión declarada (no una excepción).
De las 27 casillas del plan de ejecución, 26 se cumplen y una queda abierta
con ficha (T-015). Nada de lo que sigue es una excepción al gate: son los
límites de lo medido, dichos.

---

## 1. Las seis métricas, medidas juntas sobre `main`

| # | Métrica | Aceptación | Medido | Dónde y cómo |
|---|---|---|---|---|
| 1 | Activos con falsos huecos por festivo ajeno | 0 | **0** de 37 ausencias en 107 activos | `medir_metricas_1_y_2.py` → `metricas-1-y-2.txt`. Definición operativa: una ausencia es falsa si cae en un día que **no** es sesión de la plaza del propio activo. Las 37 ausencias reales caen en 3 fechas, todas con la plaza abierta |
| 2 | Activos `INCOMPLETO` por el 2026-09-07 | explicados uno a uno | **22**, todos atribuidos | Mismo script. 11 Xetra, 5 París, 3 Madrid, 2 Milán, 1 Ámsterdam; en los 22 la plaza estaba abierta → hueco del proveedor, la causa que T-004 identificó (43 huecos del proveedor con plaza abierta, 0 del pipeline) |
| 3 | `reward_risk(entry_max, target2, stop) < min_rr` en la salida real | 0 casos | **0** en swing y **0** en medio, sobre 107 y 107 | `medir_metricas_3_y_5.py` → `metricas-3-y-5.txt`, usando `run_analysis` (el mismo camino que producción, no una reimplementación) |
| 4 | Fichas con «Precio actual» cuando solo hay cierre | 0 | **0 de 2** | `despues-swing.txt` y `despues-medio.txt`: el informe genera ficha completa solo para las oportunidades OPERAR, una por horizonte (AMD). Cobertura limitada por construcción; lo que da fuerza a la métrica es el test `test_informe_no_llama_precio_actual_al_cierre_anterior`, que falla contra el defecto inyectado (revisión de T-008) |
| 5 | Descartes sin código de motivo | 0 | **0 en el informe**; 1 de 82 sin `discard_code` | En el bloque DESCARTADOS los 82 descartes caen en uno de los siete grupos y `otros: 0`. Precisión: `9984.T` tiene `discard_code` vacío porque su motivo es de broker (`execution_code = BROKER_UNAVAILABLE`), persistido y visible bajo el grupo «broker». Es consecuencia de T-007, que convirtió el broker no disponible en descarte. La métrica habla del informe y se cumple; el campo se declara |
| 6 | Recomendaciones persistidas sin `run_id` desde la migración | 0 | **0** | **Medido en la Pi**, no en el portátil, porque aquí no se guarda nada. 4.963 filas: 2.503 sin `run_id`, de 2026-08-29 a 2026-09-14T07:32; 2.460 con `run_id`, de 2026-09-14T09:38 a hoy 07:32. Sin solape: el corte es la migración |

## 2. Los siete requisitos del gate

| # | Requisito | Evidencia |
|---|---|---|
| 1 | PR 1 mergeado en `main` | `e929da4`, fusionado el 2026-09-16 |
| 2 | PR 2 aceptado: calendarios de plaza, cripto 24/7, causa del hueco con test | T-003 y T-004 aceptadas, en `main` y desplegadas; `exchange_overrides.yaml` con fuente; métricas 1 y 2 |
| 3 | PR 3 aceptado: `DataQuality` por dimensiones y códigos de descarte | T-005 aceptada tras dos revisiones; métrica 5 |
| 4 | PR 4 aceptado: estado de plaza, «último cierre», reevaluación, estados de broker, ISIN `EXH1.DE` | T-007 aceptada (`c314729`), revisión con BLOCKER corregido; ISIN cruzado contra la ficha del emisor; métrica 4 |
| 5 | PR 5 aceptado: informe por capas, siete invariantes como tests, fase 14 ejecutada, fase 15 limpia | T-008 (`6fbeed0`), T-009 (`3ac1fb8`), esta entrega. Las siete invariantes comprobadas con defecto inyectado, no leídas |
| 6 | Manifiesto y migraciones aceptados | T-002 aceptada; métrica 6 sobre la Pi con esquema v4 |
| 7 | CI verde en `main` | run `35334178346` sobre `d8cbc37`, `checks (3.12)` y `checks (3.13)`; branch protection activa (OA-02, comprobada por API con `enforce_admins`) |

## 3. Los 27 criterios del plan de ejecución

| # | Criterio | Estado | Prueba |
|---|---|---|---|
| 1 | RR calculado siempre desde el precio efectivo | ✓ | `execution.py`: `reward_risk(entry_price, …)`; invariante 7 |
| 2 | `entry_max` respeta `min_rr` | ✓ | métrica 3 = 0; invariante 2 |
| 3 | El score no depende del filtro duro de RR | ✓ | INV-03: 0 cambios de score en T-007/T-008/T-009. (El RR sigue siendo *dimensión* del score por D-17; eso lo decide A-02, no este gate) |
| 4 | Setup y ejecución son estados distintos | ✓ | `classify_setup` vs `evaluate_trade_at_entry`; ficha por capas de T-008 |
| 5 | Un score alto puede terminar en ESPERAR | ✓ | `test_setup_bueno_con_rr_malo_espera_sin_tocar_score` |
| 6 | Cambiar `entry` recalcula el dimensionamiento | ✓ | invariante 7, cadena EXH1 completa a mano |
| 7 | Riesgo real nunca supera el configurado | ✓ | fase 3; el informe declara «Restricción dominante» |
| 8 | Calendario del activo depende del exchange | ✓ | `calendars.py`, MIC por plaza; métrica 1 |
| 9 | Benchmark no determina sesiones esperadas | ✓ | invariante 3 |
| 10 | ETF usa calendario de su bolsa | ✓ | `EUNN.DE` (Xetra sobre Japón) con calendario `XETR`; métrica 1 |
| 11 | ADR usa calendario donde cotiza el ticker | ✓ | `TSM`, `INFY`, `AZN` sin falsos huecos; métrica 1 |
| 12 | Cripto tiene calendario 24/7 | ✓ | `CRYPTO_24_7`, `test_cripto_siempre_open` |
| 13 | El caso 07/09/2026 tiene causa identificada y test | ✓ | T-004; métrica 2, los 22 atribuidos |
| 14 | Festivos no generan falsos missing sessions | ✓ | invariante 4 (falla con días hábiles en vez de calendario); métrica 1 |
| 15 | Freshness y calidad histórica separadas | ✓ | `DataQuality` con `freshness`, `recent_completeness`, `historical_completeness` |
| 16 | Warning histórico no bloquea automáticamente ejecución | ✓ | `veto_window_sessions`, `execution_readiness` separada (T-005) |
| 17 | Descartes tienen código de motivo | ✓ | métrica 5, con la precisión de `9984.T` |
| 18 | Último cierre no se presenta como precio actual | ✓ | métrica 4; invariante 6 |
| 19 | Gap por encima de `entry_max` produce NO_CHASE | ✓ | `ABOVE_MAX_ENTRY` con motivo «NO_CHASE»; T-009: 96 % de las señales perdidas |
| 20 | Broker UNVERIFIED no se presenta como disponible | ✓ | `VERIFICAR_BROKER` (T-007); `test_unverified_no_se_convierte_en_unavailable` |
| 21 | `EXH1.DE` tiene ISIN `DE000A0H08M3` | ✓ | `universe.yaml`, verificado en la app y cruzado con el emisor |
| 22 | `report.py` sin contradicciones entre RR, stop, target y entrada máxima | ✓ | T-008: dos máximas publicadas y cuál manda; RR al precio evaluado; sin comparar redondeados |
| 23 | Tests unitarios verdes | ✓ | 548 tras esta entrega |
| 24 | Tests de integración verdes | ✓ | misma suite; también en clon limpio: 538 + 3 saltados declarados |
| 25 | Informe completo de 107 activos sin errores | ✓ | hoy, dos horizontes, 107 oportunidades y 0 saltadas cada uno |
| 26 | Event study / backtest continúa siendo reproducible | **ABIERTO** | El laboratorio sobre cosecha sí: `event-study`, `capacidad-estadistica` y `filtro-ejecucion` publican hashes. **El backtest en vivo no**: 891/893/890 operaciones en tres pasadas del mismo commit (revisión de T-009). Ficha **T-015** |
| 27 | `data_vintage_id` continúa funcionando | ✓ | T-006; los tres comandos del laboratorio lo publican |

**La casilla del caso EXH1 a 56,63** decía `RR_TOO_LOW` y ahora dice
`ABOVE_MAX_ENTRY`: **D-29 cerrada** en esta entrega con los datos de T-009
(`RR_TOO_LOW` 0 de 2.151, inalcanzable por construcción). Se corrige la línea
del plan, que era anterior a PR 1 y contradecía D-06, y
`test_exh1_regresion_de_la_linea_0` fija los cuatro precios.

## 4. Lista de la fase 15, con la prueba al lado

| Casilla | Prueba | Resultado |
|---|---|---|
| Cálculo de RR duplicado | `grep -rn reward_risk advisor` | un solo cálculo, `levels.py:41`, tres llamantes |
| Cálculos antiguos de `entry_max` | `grep -rn entry_max advisor/analysis` | solo `compute_levels_from_inputs` |
| Benchmark usado como calendario | `grep -rn benchmark advisor/data/calendars.py advisor/data/freshness.py` | `strength_benchmark` viaja como metadato, nunca entra en el calendario |
| Excepciones temporales por fecha o ticker | `grep -rnE "2026-09-07\|2026-03-06\|EXH1\|AZN\|TSM\|005930" advisor` | **cero** en código; los cierres de KRX viven en `exchange_overrides.yaml` con fuente |
| `print()` / debug | `test_no_hay_prints_fuera_de_la_cli` | solo `main.py`, que es la CLI |
| `TODO` / `FIXME` sin ficha | `test_no_hay_todos_sin_ficha_en_advisor` | cero |
| `type: ignore` | `test_no_hay_type_ignore_en_advisor` | cero, igual que en la línea base |
| Código muerto | análisis AST de 515 funciones contra `advisor/` y `tests/` | **tres huérfanas, borradas** (abajo) |
| `ruff check .` | | limpio, `evidence/` incluido |
| `mypy advisor` | | limpio, 62 ficheros |
| Suite completa | | 548 pasan |
| Suite en clon limpio | `git archive HEAD \| tar -x` | 538 pasan, 3 saltan declarando que falta la cosecha |
| Informe completo | dos horizontes | 107/107 sin error |
| Comparación antes/después | | 0 cambios de acción respecto a la pasada de T-008 |

**Las tres huérfanas.** `apply_migrations` (`storage/migrations.py`) era la
función que la ficha de T-002 nombraba como punto de entrada, pero `db.py`
acabó duplicando el bucle y añadiendo el backup previo: la huérfana **migraba
sin backup** y conservaba el nombre y el docstring que invitan a llamarla. No
era un defecto vivo; era una trampa cargada. `executable_in_broker`
(`opportunity.py`) repetía la regla de broker que vive en `execution.py`;
`has_close` (`sessions.py`) repetía un `is None`. Ninguna se usaba en ningún
fichero del repositorio. Suite, ruff y mypy limpios tras borrarlas.

## 5. Los hallazgos abiertos del roadmap, uno a uno

Trece en total (los once de la sección del roadmap y los dos del START HERE).
Ninguno se queda como estaba:

| Hallazgo | Salida |
|---|---|
| `events.yaml` caduca el 2027-12-16 | **Ficha**: C-04 (por escribir), que lo convierte en alerta |
| Seis índices no alimentan el contexto | **Nota** en A-03 (P3): medir antes de enchufar; no es defecto |
| `economic_currency` sin usar | **Nota** en A-04 (P4): descomponer el ATR es cambio de cálculo, se mide allí |
| Los eventos no puntúan; `YahooEarningsSource` no es point-in-time | **Ficha**: T-014 (B-00), que es justo el contrato PIT |
| Dividendo en horizonte medio fuera del P&L | **Nota** en A-06 (P6): prerrequisito antes de interpretar `medio` |
| `capital:` vacío a propósito | **Cerrado**: documentado en `config.yaml` líneas 75-77 |
| El informe no dice qué tope de sizing manda | **Cerrado por T-008**: «Restricción dominante: manda el presupuesto de riesgo» |
| `git_dirty` devuelve `False` si `git status` falla | **Ficha**: T-017 (exige migración) |
| `config_hash` incluye `db_path` y `universe_path` | **Ficha**: T-017 (afecta a la reconstrucción de D-10) |
| `backup_log` fuera de la lista de migraciones | **Ficha**: T-017 |
| Cabecera del protocolo «acordado, sin implementar» | **Cerrado por T-009** |
| `analizar --grupos X` declara el vintage entero | **Ficha**: T-017 |
| `capacidad-estadistica` sin vintage | **Cerrado por T-009** |

Resumen: 4 cerrados, 3 notas en fases de la línea A, 6 con ficha (C-04, T-014
y cuatro en la nueva T-017). Suma 13.

## 6. Lo que este gate NO dice

- **No dice que el sistema tenga ventaja.** Eso es P10, y la sección «Universo»
  del roadmap sigue vinculando.
- **No dice que la Pi ejecute esto.** La Pi está en `894fa75`, cuatro entregas
  por detrás. Desplegar es OA-04, del propietario, y ahora ya no hay motivo para
  esperar.
- **No dice que el backtest en vivo sea reproducible** (casilla 26, T-015).
- Y hoy ha dejado tres hallazgos nuevos con ficha —T-015, T-016, T-017— que no
  bloquean este gate pero **sí condicionan el siguiente**: T-016 va antes de
  A-02 porque el veredicto de P2.5 puede llevar un intervalo falso.

## Verificación final

    python -m pytest -q          548 pasan
    ruff check .                 limpio (evidence/ incluido)
    mypy advisor                 limpio, 62 ficheros
    clon limpio                  538 pasan, 3 saltados declarados
    analizar swing / medio       107/107, 0 cambios de acción
