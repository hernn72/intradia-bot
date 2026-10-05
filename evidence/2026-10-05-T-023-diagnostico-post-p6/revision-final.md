# T-023 — Revisión final independiente (solo lectura)

> **Exploratorio / post hoc. No cambia D-70, no valida una nueva política y no constituye evidencia
> confirmatoria.**

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

- **Fecha:** 2026-10-05, sobre la rama `research/t023-diagnostico-post-p6` (base `26dea36`), con este
  directorio sin commitear.
- **Revisores:** Codex (independiente, solo lectura) y Claude (verificación propia).
- **Cómo se hizo:** el script lo programó Codex, en dos rondas, a partir de una especificación
  cerrada. Claude verificó su salida, pidió correcciones y redactó los `.md`. Codex hizo la revisión
  final.
- **Mandato:** intentar demostrar que T-023 es incorrecto: re-simulación, inputs distintos de P6,
  fuentes externas, escrituras en `run/`, agregados erróneos, contrafactuales disfrazados, selección
  oportunista, hipótesis sin rotular, D-70 o `[]` alterados, o P7 desbloqueado.

## Resultado

**0 BLOCKER · 0 IMPORTANTE · 0 MENOR · 0 OBSERVACIONES accionables.**

## Verificación de Claude

| Comprobación | Resultado |
|---|---|
| Importaciones del script | solo biblioteca estándar y `yaml`; grep de `advisor`, `simulate`, `run_confirmatory`, `load_vintage`, `data/vintages`, red, reloj y aleatoriedad: 0 coincidencias |
| Escrituras del script | solo los 9 CSV de este directorio, más `fuentes.json` con `--fijar-fuentes` explícito |
| Guarda de hashes | 30 inputs fijados; los 27 de `run/` coinciden con `SHA256SUMS-ejecucion.txt` de P6. Con un hash alterado en una copia de `fuentes.json`, el script aborta con código 1 sin leer nada; restaurado, la salida es idéntica |
| `run/` antes y después | `shasum -c SHA256SUMS-ejecucion.txt` 30/30 OK; `git status -- evidence/2026-10-03-T-022-p6` vacío |
| Determinismo | dos ejecuciones → sha256 del conjunto de CSV `a58baa51…38bd` en ambas |
| Reconstrucción frente a lo publicado | exposición media, cash medio, cash mínimo, posiciones media y máx., `win_rate`, PF, fracción rechazada por cash, capital pedido y disponible, comisiones, slippage, dividendos y FX: iguales a `p6-resultado.json` (el script aborta si no) |
| Identidades contables | Σ P&L por activo = V_T − V_0 (políticas y benchmark); Σ(R_EUR·riesgo_EUR) = Σ pnl_neto_EUR; Σ del aporte anual del log_gap = log_gap final |
| D-70 y documentación | `git diff 26dea36 -- docs/` vacío |
| Alcance | `git status` solo muestra este directorio (más `graphify-out/` y `ultima_cerrada`, del usuario, sin tocar) |
| Suite | antes y después: ruff y mypy limpios, 1103 passed (`pytest-ruff-mypy.txt`) |
| Correcciones de la ronda 2, tras revisar la ronda 1 | `win_rate` alineado con la definición de P6 (`pnl_neto_eur > 0`, validado); unidades explícitas en `brecha-temporal.csv` (pp y log); columnas `frac_*` en lugar de `pct_*`; publicada y reconstruida por separado; nuevos bloques `exceso_anual`, `log_gap`, `riesgo_tamano`, `fraccion_notional` y rechazos por motivo y año |
| Trazabilidad de `hallazgos.md` | se quitaron dos cifras derivadas a mano que no estaban en ningún CSV (un porcentaje del log_gap y un producto riesgo·R) |

## Informe de Codex (literal)

**Veredicto**

APROBADO como revisión final: 0 `BLOCKER` y 0 `IMPORTANTE`. Esto es lo que informó Codex.

No encontró evidencia de re-simulación, contrafactuales prohibidos, hashes débiles, modificación de `run/`, contradicción de D-70/salida `[]`, ni desbloqueo de P7. No editó, creó, borró ni commiteó ficheros.

**Resultado 1-9**

1. **PASA.** [diagnostico_p6.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/evidence/2026-10-05-T-023-diagnostico-post-p6/diagnostico_p6.py:3) importa solo librerías estándar y `yaml`; no importa `advisor`, no llama simuladores, red, reloj ni aleatoriedad. Las únicas escrituras localizadas son `fuentes.json` con `--fijar-fuentes` y los 9 CSV bajo `OUT`, que apunta al propio directorio T-023.
2. **PASA.** [fuentes.json](/Users/fer/Desktop/Trading%20bot/intradia-bot/evidence/2026-10-05-T-023-diagnostico-post-p6/fuentes.json:7) fija 30 inputs. Recalculó sha256: 0 discrepancias; 27 inputs de `run/` coinciden con `SHA256SUMS-ejecucion.txt`. La lógica aborta si falta `fuentes.json`, si cambia la lista, si cambia un hash o si no valida el manifiesto de P6; `--fijar-fuentes` solo actúa con flag explícito.
3. **PASA.** `shasum -a 256 -c SHA256SUMS-ejecucion.txt` en `evidence/2026-10-03-T-022-p6/run` dio `OK` en todas las entradas. `git status --porcelain -- evidence/2026-10-03-T-022-p6` salió vacío.
4. **PASA.** Recalculó independientemente en memoria: exposición/cash/posiciones, win_rate, PF, exceso anual, log_gap, contribución benchmark `Σ = V_T - V_0`, costes/slippage/dividendos/FX y captura top10. Resultado: 0 discrepancias contra `p6-resultado.json` en los chequeos con valor publicado.
5. **PASA.** Barrido textual de CSV y `.md`: no encontró contrafactuales disfrazados. Las menciones a "habría", "sin costes" u "otra prioridad" aparecen marcadas como `NO_IDENTIFICABLE` o como hipótesis/estudio futuro, no como resultado.
6. **PASA.** Muestreó más de 20 cifras de las tablas A-J y todas trazan a CSV generado. Ejemplos: exceso B2 2022 `-6.8581`, S2 2023 `-27.9369`, log gap C0 `-0.82748`, exposición B2 `0.837094`, S2 días <=25% `219`, B2 señales pendientes `8293`, S2 `ABOVE_MAX_ENTRY` `1175`, B2 comisiones `15976.31`, S2 todas barras CAGR `0.282307`, C0 CAGR `0.098883`.
7. **PASA.** Hay 5 hipótesis H23-01..H23-05; cada una cita observaciones de `hallazgos.md`, declara carácter post hoc, incluye estudio mínimo falsable y no se presenta como ganadora ni recomendada.
8. **PASA.** `git diff 26dea36 -- docs/` salió vacío. Los `.md` mantienen P6 cerrado, B2/S2 `NO PASA`, salida `[]` y P7 `BLOQUEADO`.
9. **PASA CON ALCANCE.** `git status --porcelain` muestra solo `?? evidence/2026-10-05-T-023-diagnostico-post-p6/`, `?? graphify-out/` y `?? ultima_cerrada`; estos dos últimos estaban explícitamente fuera de alcance. No vio cambios fuera del directorio T-023 dentro del alcance revisado.

**Hallazgos**

- `BLOCKER`: ninguno.
- `IMPORTANTE`: ninguno.
- `MENOR`: ninguno.
- `OBSERVACIÓN`: ninguna accionable. Nota operativa: algunos comandos `git` emitieron warnings por no poder crear caché temporal de `xcrun` bajo el sandbox, pero devolvieron salida útil.

**Comandos Ejecutados**

```bash
git status --porcelain
find evidence/2026-10-05-T-023-diagnostico-post-p6 -maxdepth 1 -type f -print | sort
git diff --name-only 26dea364f32866d135f938f128aba541d20b6469 -- docs
cd evidence/2026-10-03-T-022-p6/run && shasum -a 256 -c SHA256SUMS-ejecucion.txt
nl -ba evidence/2026-10-05-T-023-diagnostico-post-p6/{diagnostico_p6.py,fuentes.json,hallazgos.md,hipotesis-candidatas.md,OWNER_DECISION_REQUIRED.md,README.md}
rg ... evidence/2026-10-05-T-023-diagnostico-post-p6
git status --porcelain -- evidence/2026-10-03-T-022-p6
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -c '...'  # hashes fuentes/manifiesto
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -c '...'  # recalculo independiente agregados
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -c '...'  # trazabilidad de cifras A-J
```

Nota: Codex no ejecutó `diagnostico_p6.py` dentro de su sandbox. Hizo revisión estática y recálculo
independiente en memoria, como permitía el mandato. La ejecución real, dos veces y byte a byte, la hizo
Claude (tabla anterior y `pytest-ruff-mypy.txt`).
