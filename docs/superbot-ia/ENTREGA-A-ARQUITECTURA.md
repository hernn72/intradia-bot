# Entrega A: arquitectura del Superbot con IA

Fecha: 2026-11-05. Sustituye como objetivo a `fase-ia/AUDITORIA-Y-DISENO-IA-SUPERBOT.md`, que queda como auditoría. Nada implementado. Sin capital real.

## 0. Objetivo final

**El único producto final es Superbot IA.** iTrade, intradia-bot y el Superbot técnico son proyectos de desarrollo: aportan código, asesores, modelos y gestión de riesgo.

En la Raspberry Pi quedará **un solo sistema**, con análisis cuantitativo, asesores IA, comité, gestión de riesgo, una única cartera paper, dashboard, mensajes de Telegram y servicios propios. El Mac es solo desarrollo y mantenimiento: ninguna operación ordinaria depende de él. T-024 y T-025 se mantienen hasta su cierre formal o una cancelación expresa.

## 1. Conclusiones

1. **La arquitectura es viable reutilizando la mayor parte.** Lo nuevo son el adaptador cuantitativo, los asesores, el comité y el registro.
2. **Un Superbot visible sobre este motor erosiona T-024 y consume sesiones de P7.** El propietario lo acepta con D-81 (sección 3): no se presentará como evidencia ciega, y mientras sea visible no habrá ventana virgen para P7.
3. **Dar voto a la IA cambia reglas escritas del proyecto.** Tu orden lo aprueba, pero debe registrarse como D-81, con las enmiendas explícitas, antes de programar.
4. **El motor cuantitativo no tiene ventaja demostrada.** P2 a P6 no la encontraron: bandas no concluyentes y `NO PASA` en P6 (D-70). Esta arquitectura construye un sistema que decide y se explica, no garantiza que gane.
5. **Es un solo proceso y una sola base nueva.** La cartera antigua se archiva.

## 2. Flujo de decisión

```text
Barras cerradas y fills pendientes (motor de cartera)
        │
        ▼
Análisis cuantitativo (analyze_asset por plaza y sesión, sin intradia.db)
        │ adaptador: barras sin ajustar, contexto point-in-time, available_at
        │ elegibles y posiciones abiertas, con paquete fechado
        ▼
Asesor de oportunidades   COMPRAR / DESCARTAR, prioridad, riesgos
Asesor de riesgo          COMPRAR / DESCARTAR y MANTENER / VENDER, riesgos
        │ JSON con esquema cerrado, fuera de la transacción
        ▼
Comité    resolución estructurada por reglas
        │
        ▼
Motor de riesgo    veto final: capital, exposición, stops, calidad de datos
        │
        ▼
Orden paper para la siguiente apertura → cartera, dashboard, registro
```

**Adaptador cuantitativo.** Superbot **no llama a `run_analysis`**: esa función no admite contexto point-in-time, fija `legacy_v1` con Score v1 y descarga con `get_history`, con barras ajustadas. El adaptador, nuevo en `superbot/`, replica solo su orquestación y llama a `analyze_asset`, que recibe proveedor y contexto como parámetros:

- Pasa un proveedor cuyo `get_history` devuelve `get_raw_history`, con barras sin ajustar.
- Inyecta un `MarketContext` de `PointInTimeContextResolver`, con Score `1.0`. Es la combinación que usa P6, y `resolve_context_mode` la admite.
- Fija `analysis_timestamp` y guarda `observed_at`, `available_at`, fuente y hash por observación.
- Rechaza el paquete si `max(available_at) > decision_ts` o si `context.source` no es `point_in_time`.

`advisor/` no se modifica.

**Elegibilidad.** Parte del análisis cuantitativo, no de las señales antiguas. Un valor es elegible si tiene Score de al menos 60, `broker_state` verificado, calidad de dato operable y no tiene posición ni orden pendiente. Se excluye a propósito la decisión `OPERAR`. El ranking es por plaza y sesión: los 5 primeros de cada pasada, según D-38.

**Pasadas.** Se mantienen 18:15 (Europa y Asia) y 22:45 (EE. UU.). Cada decisión tiene clave única `(instrumento, sesión de señal, sesión objetivo, versión de política)`: no hay duplicados entre pasadas. El motor cancela la orden si se creó después de la apertura de su sesión objetivo, y revalida la ejecutabilidad con el precio de apertura.

**Comité.** Conserva del comité de iTrade su formato (votos, razonamiento, invalidación), pero pasa de opinión de mercado posterior a resolución por operación anterior a operar. La consolidación es una regla, no un tercer modelo: es reproducible, auditable y más barata.

| Oportunidad | Riesgo | Resolución de compra |
|---|---|---|
| `COMPRAR` | `COMPRAR` | Aprobada; la prioridad ordena las aprobadas |
| Cualquier otro caso, o fallo | | Descartada |

| Dictámenes de la posición | Resolución |
|---|---|
| `VENDER` con causa de la lista, y predicado verificado en código | Venta en la apertura siguiente |
| `VENDER` sin causa válida o con predicado falso | Mantener; se registra |
| `MANTENER` de ambos, o fallo | Mantener, con su stop |

Basta un `VENDER` válido: el voto del otro asesor se registra pero no bloquea una salida verificada.

**Causas de venta, lista cerrada.** El modelo elige la causa; el código comprueba que es cierta **para esa posición**, con su sesión de señal y el paquete versionado. Citar un dato no basta. Dato ausente o no verificable implica `MANTENER`.

| Causa | Predicado en código, sobre la última sesión cerrada del valor |
|---|---|
| `CIERRE_BAJO_SMA` | `Close < SMA50 × 0,98` |
| `SCORE_BAJO_60` | Score v1 point-in-time del valor menor que 60 |
| `INVALIDACION_CRUZADA` | `Close` bajo el `invalidation_level` guardado al abrir la posición |

**Disparador de revisión.** Una posición recibe dictamen solo si, sobre su última sesión cerrada, se verifica al menos uno de estos predicados. Sin predicado positivo no se llama a la IA y la posición se mantiene. Así, con la misma entrada, las posiciones revisadas son siempre las mismas. La regla no vende sola: decide el asesor, que puede dictaminar `MANTENER` aunque el predicado sea cierto.

Umbrales versionados en la configuración congelada de la cartera. Las causas de mercado y concentración no existen como venta: no identifican qué posición vender y dejarían esa elección al modelo. La concentración se controla como veto de entrada.

Límites: máximo 1 venta IA por pasada; si hay varias válidas, se ejecuta la de peor resultado no realizado, y a igualdad, por símbolo. Sin recompra del valor en 5 sesiones de su plaza. La orden caduca si no se ejecuta en su sesión objetivo. Si el stop o el hueco bajo stop actúan en la misma barra, prevalece la protección y la orden de venta se cancela.

**Autoridad del motor de riesgo.** La IA no tiene campos de precio, stop, tamaño ni capital. El stop final lo fija el motor y solo se endurece. Los niveles se muestran a la IA como referencia; solo `invalidation_level` tiene un uso, el predicado de venta, y no mueve el stop. Una venta libera efectivo y hueco, así que la IA influye indirectamente en compras futuras, y por eso existen el límite de ventas y la espera de recompra. Toda compra pasa los controles del motor.

## 3. Bloqueo de sellado

**Hechos.**

- T-025 §10.1 y §10.3 sellan para B2, S2 y C0 fills, posiciones, salidas, cash, equity y P&L, y cualquier canal lateral.
- D-75 fija la sesión como unidad de consumo «sin usar (política, sesión) como escapatoria». P7 solo podría usar sesiones sin desenlace consultado.
- D-76 aceptó ver información ex ante porque «ningún desenlace» de esas políticas se muestra.
- El Superbot actual usa otra estrategia, y aun así se anotó que su P&L visible «erosiona en parte la ceguera de T-024».

**Consecuencia.** Una cartera visible seleccionada con el mismo Score v1, universo y sesiones muestra resultados parcialmente deducibles para C0, B2 y S2. Más que el Superbot actual. Llamarla `superbot_ia_v1` no lo evita: sería justo la escapatoria que D-75 cerró.

| Opción | Dashboard con resultados | T-024 y T-025 | Coste |
|---|---|---|---|
| **1. Superbot visible, enmienda D-81** | Sí, desde el inicio | Siguen corriendo con su código y metodología | La ceguera de T-024 se debilita, declarado en sus informes. Las sesiones visibles se dan por consumidas para P7 |
| **2. Superbot oculto hasta resolver T-024** | Solo ex ante; cartera sellada | Sin efecto | Sin resultados visibles durante muchos meses. Contradice tu objetivo |
| **3. Selección sin Score v1** | Sí | Efecto menor, como el Superbot actual | Renuncia al motor de intradia-bot, que pides como punto de partida |

**Decisión: opción 1.** No altera el código ni la metodología de T-024 y T-025, pero sí debilita la ceguera de T-024 y gasta sesiones de P7. Es irreversible para esas sesiones.

D-81 enmienda D-38, D-73, D-75, D-76, D-78, D-79 y la línea B, y fija el alcance desde `SIA_T0`, la primera sesión con cartera activa.

**Geometría.** Se mantiene el stop actual del motor: 5 % inicial y `Close − 3·ATR` móvil, solo hacia arriba. Es la protección obligatoria ya probada. Desaparecen las entradas, el ranking y las salidas de `itrade_trend_v1`. Este cambio no resuelve el sellado: solo evita reutilizar la geometría de C0.

## 4. Reutilización

| Función | Componente | Origen | Acción |
|---|---|---|---|
| Análisis e indicadores | `analyze_asset`, `Opportunity`, `Levels`, `Score`, `PointInTimeContextResolver` | intradia-bot | Reutilizar sin cambios, desde el adaptador |
| Calidad de datos, calendarios, FX | `advisor/data`, `superbot/data.py` | intradia-bot | Reutilizar |
| Asesor de oportunidades | Patrón de `advisor/ai/agents.py` y restricciones de `advisor_agent.md` | intradia-bot | Nuevo en `superbot/`, con su propio prompt. Los originales no se editan |
| Asesor de riesgo | `risk_agent.md`, formato de votos | iTrade | Adaptar a una operación |
| Comité | Esquema de `committee_agent.md` y `analyst.py` | iTrade | Adaptar: previo y por operación, consolidado por reglas |
| Órdenes, fills, costes, FX, splits, equity, idempotencia | `superbot/engine.py`, `store.py` | Superbot | Reutilizar |
| Límites de sizing, stop, trailing | `superbot/engine.py`, `strategy.py` | Superbot | Reutilizar |
| Exposición y kill switch | `app/risk/exposure.py`, `kill_switch.py` | iTrade | Reescribir sobre el ledger de Superbot: dependen de `PaperBroker`. Subconjunto paper, no cierra R-01 ni GATE RISK |
| Registro | `superbot/decisions.py`, solo en la rama del PR #58 | Superbot | Componente nuevo; aprovechar del PR su mecánica de completitud |
| Dashboard y alertas | `superbot/dashboard.py`, `alerts.py` | Superbot | Ampliar con decisiones |
| Análisis posterior | `meta_analyst` | iTrade | Adaptar a la Entrega D. Informa, no cambia reglas |

**No se reutiliza:** agentes técnico y macro (repiten al motor; el macro usa memoria del modelo), research, `evaluate` y `momentum_score` como decisores, parsers JSON por regex, y correlación y régimen de iTrade, fuera de esta versión.

**Cambios en el motor:** despachar `_signal`, ranking y salida según `strategy_id`, que hoy no se usa para esto; guardar con la orden los niveles y su versión. Cada base queda ligada a su `strategy_id` congelado y el motor se niega a mezclarlas. La política antigua sigue en el código hasta validar la nueva.

## 5. Registro y datos

- **Sin registro completo no hay decisión de IA.** Si no se puede guardar, no se crea la orden: ni compra ni venta discrecional.
- **Las salidas de protección nunca dependen de la IA ni del registro.** Stop y hueco bajo stop escriben su fill, posición y efectivo de forma atómica, como hoy; esa contabilidad es la fuente de verdad. El registro enriquecido va en un savepoint aparte: si falla, se revierte solo ese savepoint, la operación se confirma, y `REGISTRO_INCOMPLETO` se guarda en `runs.detail`, que no depende del componente fallido.
- Por decisión: fecha, paquete con `as_of` y fuente de cada dato, análisis cuantitativo, dictámenes, resolución, veto de riesgo, decisión aplicada, y enlace a orden y resultado posterior.
- Por llamada: campos de D-12, respuesta cruda y validada, tokens, coste, `request_id`.
- **Datos admitidos:** cuantitativos del motor, cartera y contexto de mercado con fecha verificable. Nada del conocimiento propio del modelo. Noticias y fundamentales no entran: no hay fuente verificada, y `trader-news` sigue fuera.
- El paquete se rechaza si algún dato es posterior a la decisión. El motor cancela toda orden creada después de la apertura de su sesión objetivo.
- Superbot usa clave de API propia y tope de 5 €/mes por mes UTC. Las llamadas son en serie, bajo el bloqueo del proceso. Antes de cada una se reserva en la base su coste máximo; si no cabe, no se llama. Tras la respuesta se concilia con el coste real. Sin presupuesto no hay decisiones nuevas de IA; las protecciones siguen. No se instrumenta el asesor, que no debe alterarse: el total frente a los 10 €/mes de D-38 se revisa en la consola de la API. Caché persistente de 24 horas por `input_hash`. D-81 enmienda D-38.

## 6. Modos

| Modo | Efecto |
|---|---|
| `registro` | Evalúa compras y las registra; no crea órdenes, ni cartera, ni resultados |
| `activo` | Las decisiones crean órdenes paper |

El cambio de modo es manual y queda registrado. `registro` no valida ventas reales, porque no hay posiciones: el camino de venta se valida con un replay de posiciones sintéticas en la Entrega C, sin cartera visible, sin P&L y sin consumo de sesiones.

**Reversión de la política nueva.**

- **Disparador:** descuadre contable, fallo de seguridad o sellado, o decisión del propietario. La parada es inmediata; cualquier otro paso exige su autorización.
- **Efecto:** `superbot-ia-paper.timer` deshabilitado y servicio inactivo, en menos de 15 minutos. La cartera nueva se archiva tal cual: posiciones y órdenes se conservan sin liquidar, como la antigua.
- **Sin mezclas:** no se aplica otra política sobre esa base. La cartera antigua **no se reanuda**: reactivarla recuperaría sesiones pasadas, y eso está excluido.
- **Volver a operar** es un arranque nuevo con base nueva, tras corregir la causa.

## 7. Entregas

Un solo frente, una rama, y ninguna funcionalidad fuera de esta tabla.

| Entrega | Contenido | Criterios de aceptación |
|---|---|---|
| **A. Arquitectura** | Este documento, plan de la Pi, D-81 | Decisiones de la sección 8 tomadas; revisión de Codex sin críticos ni importantes de seguridad, sellado, reproducibilidad o ejecución; D-81 fusionada en el repositorio |
| **B. Asesores y comité** | Adaptador causal, paquete, 2 asesores, comité, predicados de venta, registro. Sin tocar la cartera ni `advisor/` | Pruebas verdes. Corpus congelado de 20 casos (no inventa, no usa datos ausentes, no altera cifras) con 20 de 20. 100 % de esas respuestas validan el esquema. Matriz de fallos: en compra acaba sin compra, en venta acaba en `MANTENER`. Cada causa probada verdadera, falsa y con dato ausente. 0 paquetes con `available_at` posterior y 100 % con `context.source = point_in_time`. Una pasada real por plaza registrada completa. Coste por pasada medido; reserva y cambio de mes probados |
| **C. Cartera y dashboard** | Política en el motor, base nueva, exposición y kill switch como subconjunto paper, dashboard con decisiones, replay de ventas | Con `itrade_trend_v1`, iguales en valor `fills`, `orders`, `positions`, `signals` y `equity_snapshots`, en orden canónico y sin `id`, `created_at` ni `run_id`. 10 sesiones simuladas sin descuadre. 0 duplicados por clave. 0 órdenes tras la apertura objetivo. Cada orden enlaza con su decisión. Replay sintético de las 3 causas y sus fallos. Probados: precedencia del stop, límite de 1 venta, espera de recompra, caducidad, `REGISTRO_INCOMPLETO`, IA sin efecto en stop y tamaño, negativa a mezclar políticas, y reversión desde un estado con posición abierta y orden pendiente. Revisión de Codex sin críticos abiertos |
| **D. Verificación y despliegue** | Despliegue, modo `registro`, activación, seguimiento y análisis posterior | En `registro`: al menos 5 sesiones y 30 decisiones de compra, de todas las plazas con candidatos, 100 % válidas, registradas y antes de la apertura; 0 duplicados; coste bajo el tope. `SIA_T0` registrado al activar, con autorización. 20 sesiones en `activo` con informe frente a `EUNL.DE`, y cada venta IA con predicado verificado. Primer análisis posterior sin cambio automático de reglas |

**Criterio final de aceptación.** La Entrega D no se cierra hasta demostrar en la Pi:

| Requisito | Prueba |
|---|---|
| Funciona de forma autónoma | Temporizadores propios; 20 sesiones sin intervención ni el Mac |
| Los asesores intervienen de verdad | Decisiones registradas que cambian órdenes y ventas reales en paper |
| Compra y vende en paper según decisiones y riesgo | Cada orden enlaza con su decisión y su control |
| Conserva efectivo, posiciones, operaciones y rentabilidad | Efectivo igual a capital más fills, sin descuadre |
| Envía los mensajes de Telegram | Mensajes reales recibidos para compra, venta, stop y fallo |
| El dashboard permite seguir toda la actividad | Operaciones, decisiones, dictámenes y resultados visibles |
| Se recupera de reinicios y errores | Reinicio de la Pi y fallos de API y de datos, sin pérdida ni duplicados |
| No depende de servicios de los bots anteriores | Funciona con esos servicios parados; clave y configuración propias |
| No quedan otros bots en producción | Asesor y iTrade retirados tras validar; T-024 y T-025 aparte |

## 8. Decisiones del propietario (2026-11-05)

| # | Decisión | Resultado |
|---|---|---|
| 1 | Sellado | Opción 1, con D-81 (`D-81-borrador.md`). No se abren desenlaces de T-025 |
| 2 | IA vinculante en paper | Autorizada. Comité determinista y trazable |
| 3 | Stop | 5 % inicial y 3·ATR, solo endurece |
| 4 | Registro | Sin registro completo no hay compra ni decisión discrecional. Las salidas de protección no dependen de la IA |
| 5 | Modelo | `claude-opus-5-5` si el tope de gasto lo permite |

## 9. Revisión de Codex

Primera revisión: 4 críticos, 8 importantes y 3 menores; se aceptaron 14. El nº 15 pedía verificar el estado de la Pi, que se leyó el 2026-11-05.

Segunda revisión: no aprobada. Dos críticos seguían abiertos (adaptador causal y verificación de ventas), la reversión incompleta, un crítico nuevo (ventas imposibles en `registro`) y 8 hallazgos más. Todos incorporados aquí y en D-81.

Tercera revisión: los 13 hallazgos anteriores, resueltos. Un hallazgo nuevo (disparador de revisión sin definir), corregido en la sección 2.
