# Revisión final independiente del pre-registro de P6 (T-022)

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

**Realizada antes de implementar o ejecutar P6.** Durante toda la revisión no existía `p6.py`, no se
descargó FX ni sector, no se contó ninguna señal OPERAR y no se calculó ningún resultado de sistema.
Los revisores trabajaron en solo lectura, sin SSH.

- Base: `0c144ba` (GATE P5 cruzado).
- Inicio de la revisión: `861d8208028e194d53a8e6b1f5d9a0402e6e5f1c` (OD cerradas en D-69).
- Revisores:
  - **Codex**, en hilos nuevos, independiente de las revisiones de diseño;
  - un agente **`revisor`** que no había participado en las revisiones anteriores.
- Mandato: demostrar que el pre-registro **no** puede congelarse. Se atacaron la selección
  retrospectiva, el look-ahead, la fabricación de cash, la contabilidad, los dividendos, el FX, el
  benchmark, el criterio, `system_sha256`, `P6_DATA_ID`, la matriz de GATE P6, la ausencia de
  desenlaces y la producción.

## Resultado por vuelta

| Vuelta | HEAD | Codex | `revisor` | Correcciones |
|---|---|---|---|---|
| 1 | `861d820` | 0 B, 0 I, 2 M, 1 O | 0 B, **2 I**, 4 M, 5 O | `aef5c6b` |
| 2 | `aef5c6b` | se cortó (límite de uso del servicio); avanzó 2 M | 0 B, 0 I, 2 M, 1 O | `f657f18` |
| 3 | `f657f18` | se cortó (límite de uso del servicio) | 0 B, 0 I, 1 M, 1 O | `00ce356` |
| 4 | `00ce356` | **0 B, 0 I, 0 M**; 1 O de proceso (ratificación) | **APROBADO: 0 B, 0 I, 0 M, 0 O** | — |

Los dos IMPORTANTE de la vuelta 1 se corrigieron solo en la documentación, sin cambiar ninguna letra
de D-69:
1. **INV-14.** El criterio decidía con `mean_R_local` sin declarar la diferencia con la media por
   bloque de INV-14/D-03. Ahora hay una excepción declarada: decide `mean_R_local`, y la media por
   bloque por año natural es descriptiva.
2. **Fuente FX B.** El respaldo era contradictorio y no ejecutable. Ahora la sección 11.1 lo
   especifica entero: BCE, 17:00 Europe/Berlin, festivos TARGET, `1/tipo`, contrato y hash; se define
   el fallo de integridad y la petición fija de A.

El detalle de cada hallazgo y su corrección está en `docs/tareas/T-022-p6-sistema-completo.md`, sección
«Revisión final del pre-registro (tras D-69)».

## Comprobaciones finales (las dos revisiones de la vuelta 4)

- **OD:** las 43 están CERRADAS y coinciden con D-69, también las sensibles (6 = D, 10 = D, 13 = C,
  15 = A con B de respaldo, 17 = C, 18 = A + C, 20 = C, 23 = B, 24 = B, 31 = C, 33 = A + C, 37 = C,
  42 = A, 43 = A).
- **OD-37:** la primaria y única decisoria es OPERAR con Score v1, `context_mode = "point_in_time"` y
  predicado `broker_neutral`. El puente de todas las barras no veta, no rescata, no selecciona y no
  cambia el resultado. Siguen declarados, sin suavizar:
  - P4/P5 midieron todas las barras;
  - el Score v1 no tiene ordenación demostrada;
  - P3 midió el v2;
  - el RR forma parte del v1 (15 frente a 10 puntos con el stop de volatilidad).
- **OD-42:** `legacy_v1` prohibido; el contexto no es idéntico al de producción, y se declara.
- **OD-43:** deciden el R y el PF locales; el FX entra en la equity, el retorno, el CAGR, el drawdown y
  el exceso.
- **Cronología:** fases `OPEN_EXIT < OPEN_ENTRY < CLOSE_EXIT < CLOSE_DIVIDEND < CLOSE_VALUATION <
  SIGNAL`, sin cash fabricado y con desempate SHA común. Calendario = `exchange_calendars` +
  `exchange_overrides.yaml` + tzdata.
- **Contabilidad:** identidad sin residuo, sin dobles conteos y con cash ≥ 0.
- **Dividendos y FX:** según D-69 y sus precisiones.
- **Benchmark:** 90 activos con pesos iguales, sin rebalanceo y con las mismas reglas; ARM y Q8Y0.DE
  con su 1/90 en cash hasta ser elegibles; comisión dentro del importe.
- **Criterio único y simultáneo:** `N_closed ≥ 100`, `profit_factor_local > 1`, `mean_R_local > 0`,
  `max_drawdown ≥ −25 %` y `excess_CAGR_pp > 0`. Todo lo demás es descriptivo.
- **Identidad:** `system_sha256` cubre todas las decisiones capaces de cambiar el resultado, incluidos
  el predicado, el estimador y la fuente FX; `P6_DATA_ID` está completo.
- **Matriz de GATE P6:** completa.
- **Ningún desenlace:** de `0c144ba` a HEAD solo hay documentación y el censo estructural.
- **Producción:** diff vacío en `advisor/`, `tests/`, `config.yaml`, `deploy/` y `universe.yaml`;
  `config.yaml` en `"1.0"`. El estado de la Pi (`v0.4.1`) sale de la evidencia archivada, sin SSH.

## Ratificación del propietario

El 2026-10-03, después de la vuelta 4 y antes de congelar, el propietario ratificó expresamente las
cinco «Precisiones de la revisión final» de D-69:
1. `mean_R_local` decide y la media por bloques es descriptiva.
2. Fuente B: BCE para USD, JPY y HKD, con 17:00 Europe/Berlin, último tipo causal en festivos y
   `1/tipo`.
3. Petición fija de Yahoo (`start = 2021-08-27`, `end = 2026-08-29`, `interval = 1d`,
   `auto_adjust = False`, `actions = True`); cualquier barra que falte, sobre o cambie de las 1.300 de
   `EURUSD=X` hace fallar A y se usa B.
4. Comisión del benchmark dentro del 1/90 y dentro de cada reinversión.
5. Población OPERAR `broker_neutral` (`setup_radar = OPERAR` y `setup_accion = COMPRAR`).

## Informe de Codex, vuelta 4 (literal)

**Veredicto**

No encuentro base para bloquear el congelado documental: **0 BLOCKER, 0 IMPORTANTE, 0 MENOR nuevos**.

**OBSERVACIÓN-A, condición de proceso:** el `P6_PREREG_SHA` todavía no puede fijarse hasta que el propietario ratifique expresamente las “Precisiones de la revisión final” de D-69. Está correctamente documentado en [T-022](</Users/fer/Desktop/Trading bot/intradia-bot/docs/tareas/T-022-p6-sistema-completo.md:834>) y [D-69](</Users/fer/Desktop/Trading bot/intradia-bot/docs/decision-log.md:1770>). Corrección documental propuesta: ninguna; solo cumplirlo antes del freeze.

**Cierres Solicitados**

Vuelta 1: todos **CERRADOS**. En particular, INV-14/`mean_R_local`, respaldo FX B, limitación de dividendos Xetra, comisión benchmark, sección 23.6, restos pre-D69, RR “con stop de volatilidad”, parecido a producción, predicado OPERAR, bytes de desempate, `V_0`/D y nota del censo están corregidos o acotados en [T-022](</Users/fer/Desktop/Trading bot/intradia-bot/docs/tareas/T-022-p6-sistema-completo.md:1936>).

Vuelta 2: todos **CERRADOS**. Frase 23.6, estimador del hash, petición fija de fuente A y rótulo/ratificación de precisiones de D-69 están corregidos en [T-022](</Users/fer/Desktop/Trading bot/intradia-bot/docs/tareas/T-022-p6-sistema-completo.md:1951>).

Vuelta 3: **MENOR-C CERRADO** y **OBSERVACIÓN-B CERRADA**. La ratificación previa al `P6_PREREG_SHA` queda exigida y los reintentos FX quedan limitados a excepción; la primera llamada sin excepción se congela y se comprueba una vez en [T-022](</Users/fer/Desktop/Trading bot/intradia-bot/docs/tareas/T-022-p6-sistema-completo.md:1971>) y [T-022 FX](</Users/fer/Desktop/Trading bot/intradia-bot/docs/tareas/T-022-p6-sistema-completo.md:475>).

**Correcto Verificado**

Las 43 OD están cerradas; el conteo da 43 encabezados `CERRADA (D-69)`, y las decisiones sensibles coinciden con D-69: OD-6=D, 10=D, 13=C, 15=A con B fallback, 17=C, 18=A+C, 20=C, 23=B, 24=B, 31=C, 33=A+C, 37=C, 42=A, 43=A. Ver [T-022 OD](</Users/fer/Desktop/Trading bot/intradia-bot/docs/tareas/T-022-p6-sistema-completo.md:859>) y [D-69](</Users/fer/Desktop/Trading bot/intradia-bot/docs/decision-log.md:1598>).

OD-P6-37 queda inequívoca: primaria decisoria OPERAR + Score v1 + `point_in_time`; todas las barras son puente descriptivo y no vetan/rescatan. También declara P4/P5 todas-las-barras, P3 v2, v1 no concluyente y RR en v1. Ver [T-022](</Users/fer/Desktop/Trading bot/intradia-bot/docs/tareas/T-022-p6-sistema-completo.md:1643>).

No veo puerta de selección retrospectiva en criterio, slippage, muestra, C0, subperiodos, puente, R/PF EUR ni B2/S2. El criterio único es simultáneo: `N_closed >= 100`, `PF_local > 1`, `mean_R_local > 0`, `DD >= -25%`, `excess_CAGR_pp > 0`; lo demás descriptivo. Ver [T-022 §16](</Users/fer/Desktop/Trading bot/intradia-bot/docs/tareas/T-022-p6-sistema-completo.md:616>).

La cadena anti-look-ahead está especificada: `analysis_timestamp`, contexto PIT, señal, cierre, apertura siguiente, precio efectivo y ejecutabilidad; `legacy_v1` queda prohibido para P6. Código revisado: `context_mode_for("1.0")` devuelve legacy por defecto, pero `resolve_context_mode` admite override, como exige la ficha. Ver [T-022](</Users/fer/Desktop/Trading bot/intradia-bot/docs/tareas/T-022-p6-sistema-completo.md:251>) y [point_in_time.py](</Users/fer/Desktop/Trading bot/intradia-bot/advisor/context/point_in_time.py:152>).

Cronología, dividendos, FX, benchmark, contabilidad y hash están cubiertos: fases `OPEN_EXIT < OPEN_ENTRY < CLOSE_EXIT < CLOSE_DIVIDEND < CLOSE_VALUATION < SIGNAL`, cash sin fabricar, dividendos ex-date, FX causal con `1/rate`, benchmark 90 equal-weight sin rebalanceo, ledger con identidad sin residuo, `system_sha256` y `P6_DATA_ID` con decisiones/data relevantes. Ver [cronología](</Users/fer/Desktop/Trading bot/intradia-bot/docs/tareas/T-022-p6-sistema-completo.md:323>), [FX](</Users/fer/Desktop/Trading bot/intradia-bot/docs/tareas/T-022-p6-sistema-completo.md:457>), [benchmark](</Users/fer/Desktop/Trading bot/intradia-bot/docs/tareas/T-022-p6-sistema-completo.md:547>), [ledger](</Users/fer/Desktop/Trading bot/intradia-bot/docs/tareas/T-022-p6-sistema-completo.md:723>) y [hash](</Users/fer/Desktop/Trading bot/intradia-bot/docs/tareas/T-022-p6-sistema-completo.md:682>).

Diff desde `0c144ba..HEAD`: solo docs/evidencia P6; nada en `advisor/`, `tests/`, `config.yaml`, `deploy/`, `universe.yaml`. `config.yaml` sigue con Score v1 `"1.0"` y umbrales 70/60. No existe `p6.py`.

**No Comprobado**

No hice SSH ni verificación real de la Pi; solo contrasté contra docs/evidencia archivada. No ejecuté P6, no descargué FX/sectores, no recalculé hashes ni regeneré el censo. Hubo warnings de `git` por caché temporal bloqueada en sandbox, pero los comandos devolvieron la información necesaria.
