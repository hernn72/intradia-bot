# T-004 — Investigar los huecos 2026-09-07 y 2026-03-06 hasta la causa (PR 2, fase 5)

Estado: PENDIENTE
Agente: Opus (diagnóstico con red) → Codex solo si la causa exige un cambio de código mecánico
Línea / fase: L0 PR 2, fase 5
Gate al que contribuye: GATE L0 (requisito 2)

## Objetivo
Para cada activo con la sesión 2026-09-07 ausente (30 europeos en la línea
base) y para `SXR8.DE`/`EUNL.DE`/… con 2026-03-06 ausente, afirmar **una** de
tres cosas con evidencia: (1) el mercado estaba cerrado; (2) el mercado abrió
y el proveedor no entregó la barra; (3) el proveedor la entregó y el pipeline
la perdió. Y dejar una herramienta que lo responda para cualquier fecha futura.

## Por qué existe
Es la tercera vez que aparece el patrón «índices al día, valores sin la
sesión» (2026-08-28, 2026-09-07). Sin causa, PR 3 no puede decidir si un
hueco reciente es dato ausente o dato perdido, y OD-02 (pagar otra fuente) no
tiene base. `docs/plan-ejecucion.md` fase 5 prohíbe resolverlo con excepciones.

## Dependencias previas
T-003 aceptada (para decir «mercado abierto» con calendario real). Aceptada el
2026-09-16.

## Población exacta que hereda de T-003

Medida sobre la pasada real del 2026-09-14 (`evidence/2026-09-14-T-003-calendarios/`):
44 activos con ausencias, 47 pares activo-fecha.

| Fecha | Activos | Plazas |
|---|---|---|
| 2026-09-07 | 28 | XETR, XPAR, XMIL, XMAD, XAMS, XCSE |
| 2026-03-06 | 14 | XETR |
| 2026-07-17 | 2 | XKRX |
| 2026-06-03 | 2 | XKRX |
| 2026-03-23 | 1 | XCSE |

**Las cuatro ausencias coreanas hay que clasificarlas primero, y puede que no
sean huecos de dato.** `005930.KS` y `000660.KS` son los dos únicos valores
coreanos del universo y a ambos les faltan exactamente las mismas dos fechas,
lo que apunta a cierre de plaza. Medido sobre `exchange_calendars==4.13.2`:
todos los días electorales coreanos pasados son no-sesión (2020-04-15,
2022-03-09, 2022-06-01, 2024-04-10, 2025-06-03) pero **2026-06-03 figura como
sesión**, y esa es la fecha de las elecciones locales de 2026. Los calendarios
públicos de KRX para 2026 listan los mismos 15 cierres que la librería y
ninguno incluye días electorales, que Corea declara como festivo temporal.
`2026-07-17` no tiene explicación candidata.

Si son festivos, no son caso de T-004 sino un límite conocido de la
dependencia, y hay que decidir política de actualización de versión; el efecto
hoy es que dos activos quedan `DEGRADADO` por un hueco inexistente, que es lo
que T-003 y la métrica de GATE L0 prohíben. Resolverlo **contra fuente oficial
de KRX** antes de dar la población por buena.

## Archivos probables
No asumir que sean exactos: verificar primero.
- `advisor/data/market_data.py` (`get_history`, `get_raw_history`)
- `advisor/data/sessions.py` (`trim_unclosed_bar`, `_session_date`)
- `advisor/data/calendars.py` (T-003)
- `advisor/analysis/analyzer.py` (`analyze_asset`: recorte, frescura, snapshot)
- `advisor/main.py` (nuevo subcomando `diagnosticar-barra`)
- `tests/test_sessions.py`, `tests/test_diagnostico_barra.py` (nuevo, sin red)

## Invariantes que no pueden romperse
INV-05, INV-06, INV-13, INV-16 (no se inventa la barra ausente: si el
proveedor no la da, se declara ausente).

## Implementación requerida
1. Subcomando `diagnosticar-barra --symbol SAP.DE --fecha 2026-09-07`
   que imprime, sin modificar nada:
   `ticker · plaza · MIC · calendario dice sesión sí/no · raw timestamp del
   proveedor (si existe) · tz original · tz convertida · session_date derivada
   · presente tras dropna · presente tras trim · presente en snapshot`.
   Descarga con `get_history` y con `get_raw_history` y con los tres
   `period` (`1mo`, `1y`, `5y`) porque yfinance puede devolver series
   distintas según el rango.
2. Ejecutarlo para los 30 activos del 2026-09-07 y para los ETF con
   2026-03-06, en dos momentos distintos del día (antes y después de la
   apertura europea) y guardar las salidas en `evidence/`.
3. Clasificar cada activo en (1)/(2)/(3). Si alguno cae en (3), localizar la
   línea exacta (`index.date`, `tz_convert`, `normalize`, `resample`,
   `dropna(subset=["Close"])`…) y corregirla con test de regresión; eso es
   SAME_SCOPE.
4. Si todos caen en (2): documentar el comportamiento del proveedor
   (¿reaparece la barra días después? comparar con la cosecha `071ddb2b…`
   para 2026-08-28 si la cosecha llega a esa fecha; si no, con una descarga
   nueva a los 7 días) y dejar en PR 3 la regla: «sesión ausente reciente que
   el calendario esperaba = `MISSING_RECENT_DATA`, severidad por antigüedad».
5. Sin `print()` permanentes: el subcomando usa `logger`/`print` solo en su
   propia salida.

## Qué NO debe modificarse
Ninguna regla de calidad ni de veto (PR 3). Ningún umbral. Nada en
`advisor/research/`.

## Tests unitarios
- `test_diagnostico_deriva_session_date_en_zona_de_plaza`: timestamp
  `2026-09-06T22:00:00Z` con plaza XETRA → `2026-09-07`; con NYSE → `2026-09-06`.
- `test_diagnostico_declara_calendario_cerrado`: NYSE 2026-09-07 → «sesión: no».
- `test_diagnostico_detecta_perdida_en_pipeline`: `FakeProvider` sirve la
  barra y un recorte simulado la elimina → estado «presente en raw, ausente
  tras trim».

## Tests de integración
Si aparece un caso (3): test de regresión con el DataFrame mínimo que lo
reproduce, nombrado `test_regresion_<symbol>_<fecha>`.

## Verificación contra datos reales
```bash
for s in SAP.DE SIE.DE ASML.AS TTE.PA ITX.MC NOVO-B.CO UCG.MI SXR8.DE; do
  python -m advisor.main diagnosticar-barra --symbol $s --fecha 2026-09-07
done
python -m advisor.main diagnosticar-barra --symbol SXR8.DE --fecha 2026-03-06
```
Comprobar a mano: para `SAP.DE`, el calendario XETR dice sesión el
2026-09-07; anotar literalmente qué devuelve el proveedor.

## Medición del impacto
- nº activos por clase (1)/(2)/(3).
- nº activos que cambian de calidad si hubo corrección de pipeline.
- nº señales de la cosecha afectadas: 0 salvo corrección de fechado (entonces medir con `event-study` sobre 3 activos).

## Criterio de aceptación
- Tabla completa activo → clase → evidencia, sin «no se sabe».
- Herramienta en el repositorio con tests.
- Si hubo clase (3): corregida con regresión y CI en verde.
- Revisión independiente si se tocó el fechado.

## Criterio de rechazo
- Una excepción por ticker o por fecha.
- Un activo sin clasificar.
- Conclusión basada en una sola descarga.

## Evidencia que debe quedar registrada
`evidence/<fecha>-T-004-hueco-0907/` con las salidas crudas, la tabla y el
README con la conclusión y el impacto en OD-02.

## Commit esperado
Rama `fix/session-gap-diagnosis`. Mensaje:
`fix(data): herramienta de diagnóstico de barras ausentes y causa del hueco del 2026-09-07`.

## Actualización documental requerida
`docs/roadmap.md`: PR 2 fase 5 → ACEPTADA; sección OD-02 del decision log con
la cifra de recurrencia. `docs/plan-ejecucion.md`: fase 5 con la causa.

## Handoff al siguiente agente
(se rellena al terminar)
