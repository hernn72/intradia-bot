# T-022 / A-06 — Cierre de P6 y GATE P6

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

**P6 se ejecutó exactamente una vez** (2026-10-05, marca a las 10:11:49 UTC) y no se repite. El
propietario la aceptó como válida y consumida. Este directorio registra su resultado y el cierre del
gate **sin re-simular nada** y sin tocar `evidence/2026-10-03-T-022-p6/run/`, que es inmutable.

## Identidad

| | |
|---|---|
| `P6_PREREG_SHA` | `03f04a42ea9d2be893e7c4cc09de76bd1c55778b` |
| `P6_CODE_SHA` | `bc0636d4320b38ef5a620fa9ae94cee35df47580` |
| `P6_RUN_HEAD_SHA` | `353876d39d03f6849847743b9f4e7f791abbed30` |
| `P6_RUN_EVIDENCE_SHA` | `0771989af851748463aa0e79d4a7dc327066ca5f` |
| `P6_DATA_ID` | `572e09141dbfe0fc9c53a7b529f1abcff46e16027fe9b47d1f3e26330c1e5383` |
| sha256 de `apertura-payload.json` | `7823fe8dc2634a0f4d6271399511d5d0d62b3a5da49c61106be6210a12dc8a7e` |
| sha256 de la marca = `token_sha256` | `7a05c3b80d42765bf8d7e272a7afa4419ab15aaf8611e3e15e2e9d3182a07463` |

## Resultado (D-70)

| | N_closed | PF local | mean_R_local | Max DD | CAGR | excess_CAGR_pp | Etiqueta |
|---|---|---|---|---|---|---|---|
| **B2** | 673 | 1,3995 | 0,2478 | −16,60 % | 18,03 % | −15,77 | **NO PASA** |
| **S2** | 528 | 1,4044 | 0,2383 | −11,23 % | 15,08 % | −18,72 | **NO PASA** |

- **Supervivientes `[]`.**
- En las dos candidatas se cumplen `N_closed >= 100`, `profit_factor_local > 1`, `mean_R_local > 0` y
  `max_drawdown >= -25 %`, y falla **exclusivamente** `excess_CAGR_pp > 0`.
- Benchmark de comprar y mantener del propio universo a pesos iguales (5 pb): CAGR 33,80 %, max DD
  −26,22 %.
- C0, la sensibilidad de 10 pb, el puente de todas las barras, la exposición, el cash y los
  subperiodos son **descriptivos** y no pueden rescatar ni cambiar esta salida.

## Gate (D-70)

GATE P6 **CRUZADO**: todos los requisitos metodológicos y de evidencia están cumplidos, y la revisión
final no deja ningún BLOCKER ni ningún IMPORTANTE. **El gate exige la medición completa y
reproducible, no un resultado favorable.** A-06 / T-022 queda ACEPTADA.

**A-07 / P7 queda BLOQUEADO: P6 no produjo ninguna política superviviente.** Cualquier corrección
futura de la selección de señales, la prioridad, el sizing, el uso del cash, la geometría o el
benchmark es investigación nueva, con ficha y pre-registro propios, y no cambia la etiqueta de P6.

Producción no cambia: `config.yaml` sigue en `"1.0"` con C0, Score v2 sigue inactivo y la Pi en
`v0.4.1`.

## Ficheros

| Fichero | Contenido |
|---|---|
| `resultado-p6.md` | Transcripción de `run/p6-resultado.json`: criterio, benchmark, las nueve corridas completas, señales y contadores |
| `transcribir_resultado.py` | Genera el fichero anterior leyendo solo `p6-resultado.json` (no importa `advisor` ni abre la cosecha) |
| `gate-p6-final.md` | Matriz de los requisitos de GATE P6, más los de método y evidencia |
| `revision-final.md` | Revisión final independiente (Codex, literal) y verificación propia, ambas de solo lectura |
| `hashes-evidencia.txt` | SHA256 de `run/` y de este directorio |
| `final-pytest-ruff-mypy.txt` | ruff, mypy y la suite completa al cerrar |
