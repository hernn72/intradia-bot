# GATE P6 — Sistema completo: matriz final

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

Texto literal de `docs/gates.md`:

> Requisitos: simulador de cartera con capital, posiciones simultáneas, ocupación, exposición por
> región/divisa/sector, costes, slippage, dividendos y orden cronológico real. Métricas publicadas por
> política candidata: CAGR, volatilidad, Sharpe, Sortino, max drawdown, Calmar, exposición media,
> turnover, profit factor, R total y R por operación, **y** exceso sobre el buy-and-hold del propio
> universo en la misma ventana (mitigación del sesgo de universo, ver roadmap).

**El gate no exige un resultado favorable.** Exige que la medición esté completa, publicada y sea
reproducible. Que B2 y S2 reciban `NO PASA` es el resultado de esa medición, no un requisito incumplido.

Todas las rutas son relativas a `evidence/2026-10-03-T-022-p6/run/` (commit `0771989`), salvo que se
diga otra cosa. Las métricas están en `p6-resultado.json` → `corridas.<id>`.

| # | Requisito literal | Estado | Evidencia |
|---|---|---|---|
| 1 | simulador de cartera **con capital** | **SATISFECHO** | Capital 100 000 EUR por sistema. Cada fila del ledger publica `cash_before`, `cash_after` y `equity_after` (`tablas/*-ledger.csv`). El efectivo encadena fila a fila y V_T − V_0 = Σ pnl_neto_EUR en las 9 corridas (`revision-final.md`). |
| 2 | **posiciones simultáneas** | **SATISFECHO** | `exposicion.posiciones_media`, `posiciones_max` y `distribucion_posiciones`. B2: 10,48 de media y 16 de máximo; S2: 7,42 y 15. |
| 3 | **ocupación** | **SATISFECHO** | `exposicion.distribucion_posiciones` (0…N), `cash_medio`, `cash_minimo_eur`, `contadores.INSUFFICIENT_CASH` y el bloque `ocupacion` (capital pedido frente a disponible). |
| 4 | exposición por **región / divisa / sector** | **SATISFECHO** | `exposicion.por_region`, `por_divisa_cotizacion`, `por_divisa_economica` y `por_sector` (media, máx. y p95). El sector sale del mapa congelado `evidence/2026-10-03-T-022-p6-datos/p6-sector-map.yaml`, que no tiene ningún `UNKNOWN`. |
| 5 | **costes** | **SATISFECHO** | `fee_base` por evento en el ledger; `costes_eur` por corrida (B2 15 976,31; S2 11 399,19). |
| 6 | **slippage** | **SATISFECHO** | `slippage_base` por evento; `slippage_eur` por corrida; la sensibilidad de 10 pb se publica como descriptiva (`B2_sensibilidad_10pb`, `S2_sensibilidad_10pb`, `benchmark_10pb`). |
| 7 | **dividendos** | **SATISFECHO** | Eventos `DIVIDEND` / `BH_DIVIDEND` con `dividend_base`; `dividendos_eur` y `contadores.dividendos_abonados` (B2 83, S2 72). |
| 8 | **orden cronológico real** | **SATISFECHO** | `timestamp_utc` no decrece y `seq` es consecutivo en los 9 ledgers (0 retrocesos y 0 saltos, `revision-final.md`). Calendario efectivo con 1 095 instantáneas y 27 sesiones sin barra publicadas en `ventana`. |
| 9 | métricas por política candidata: CAGR, volatilidad, Sharpe, Sortino, max drawdown, Calmar | **SATISFECHO** | `trayectoria.cagr`, `volatilidad`, `sharpe_rf0`, `sortino_mar0`, `max_drawdown` (con pico, valle, recuperación y duración) y `calmar`, para B2 y S2 (y C0 y benchmark como referencia). |
| 10 | exposición media, turnover | **SATISFECHO** | `exposicion.exposicion_media` (B2 0,8371; S2 0,6054) y `turnover.turnover_total` / `turnover_anual`. |
| 11 | profit factor, R total y R por operación | **SATISFECHO** | `operaciones.profit_factor_local`, `R_total_local` y `mean_R_local` (más mediana, versiones en EUR y win rate); operaciones una a una en `tablas/*-operaciones.csv` con `trade_R_local` y `trade_R_eur`. |
| 12 | **exceso sobre el buy-and-hold** del propio universo en la misma ventana | **SATISFECHO** | Benchmark de pesos iguales del universo a 5 y 10 pb (`benchmark`, `tablas/benchmark_*`), misma ventana 2022-06-14 → 2026-08-27; `exceso.excess_CAGR_pp` y `excess_terminal_pp` por corrida. |

**Requisitos de método y de evidencia** (ficha T-022, §23, y D-69):

| Requisito | Estado | Evidencia |
|---|---|---|
| Pre-registro congelado antes de implementar | **SATISFECHO** | `P6_PREREG_SHA = 03f04a4`, en la historia de `353876d` |
| Ejecutor fijado y sin cambios hasta la ejecución | **SATISFECHO** | `P6_CODE_SHA = bc0636d`; `git diff bc0636d 353876d -- advisor config.yaml universe.yaml exchange_overrides.yaml pyproject.toml requirements.txt` vacío |
| Preflight definitivo correcto con datos congelados | **SATISFECHO** | `../preflight/p6-preflight.json` (`ok`, `definitivo`), `P6_DATA_ID = 572e0914…5383`, recalculado y comparado dentro de la ejecución antes de la marca |
| Ejecución única con marca exclusiva previa a los desenlaces | **SATISFECHO** | `EJECUCION_CONFIRMATORIA_P6_INICIADA` (10:11:49 UTC), que hashea `apertura-payload.json` (`7823fe8d…8a7e`); sha256 de la marca = `token_sha256`; sin `p6-parada.json`; consola con `código de salida: 0` |
| Evidencia íntegra e inmutable | **SATISFECHO** | `SHA256SUMS-ejecucion.txt` 30/30 OK; ningún commit posterior a `0771989` toca `run/` |
| Criterio aplicado tal como se pre-registró | **SATISFECHO** | §16: las cinco condiciones, con su valor, por candidata; etiquetas `NO PASA` y salida `[]`, dentro de las cuatro permitidas |
| Revisión final independiente sin BLOCKER ni IMPORTANTE | **SATISFECHO** | `revision-final.md` |

**Veredicto: GATE P6 CRUZADO (D-70)**, con salida **`[]`**: B2 `NO PASA` y S2 `NO PASA`.

GATE P6 «desbloquea P7» en el sentido de que la fase previa queda cerrada, pero **P7 no recibe
ninguna política**. A-07 / P7 queda **BLOQUEADO: P6 no produjo ninguna política superviviente**.
