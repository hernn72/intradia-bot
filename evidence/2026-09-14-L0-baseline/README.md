# Línea base de la línea 0 — 2026-09-14

Captura de referencia **antes** de PR 2 (calendarios). Cualquier entrega de la
línea 0 se mide contra estos números.

| Campo | Valor |
|---|---|
| Commit | `e53e385` (rama `fix/execution-data-quality`, 3 por delante de `main` `6d32cf2`) |
| Comando | `python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar` |
| Instante | 2026-09-14 08:12 UTC (lunes, antes de la apertura europea) |
| Tests | 398 pasan (`pytest -q`, 87 s); `ruff check .` limpio; `mypy advisor` limpio, 54 ficheros |
| Salida completa | `analizar-swing-sin-ia.txt` |

## Cifras que sirven de referencia

| Medida | Valor |
|---|---|
| Activos analizados | 107 |
| Calidad `OK` / `INCOMPLETO` / `DEGRADADO` | 59 / 30 / 18 |
| Activos con sesiones ausentes frente al benchmark | 43 |
| Sin calendario de referencia | 5 (`IS3N.DE`, `ETH-EUR`, `BTC-EUR`, `SOL-EUR`, `INFY`) |
| OPERAR / RADAR / DESCARTADOS | 1 / 10 / 90 |
| Única OPERAR | `EXH1.DE` score 74, precio 56,11, entrada máx. 56,11, objetivo 2 58,20, stop 54,71 |

## Lo que esta salida demuestra (comprobado a mano)

1. **`entry_max == último cierre` para `EXH1.DE`.** Con stop por volatilidad
   (`2·ATR`) y objetivo 2 a `3·ATR`, `entry_max_rr = (T + 1,5·S) / 2,5 = P`
   exactamente. `entry_max_atr: 0.75` no interviene. Ver decisión D-06.
2. **Falsos huecos por usar el benchmark como calendario.** Ejemplos
   verificables en el texto:
   - `AZN` (NASDAQ) contra `^STOXX`: «faltan» 2025-11-27 (Acción de Gracias),
     2026-01-19 (MLK), 2026-02-16 (Presidents), 2026-06-19 (Juneteenth),
     2026-07-03 y 2026-09-07 (Labor Day). Todos festivos de EE. UU. Resultado:
     `INCOMPLETO` y **vetada** sin que le falte ninguna sesión propia.
   - `TSM` (NYSE) contra `^TWII`: mismo patrón (2025-11-27, 01-19, 05-25, 07-03, 09-07).
   - `IQQT.DE`, `EUNN.DE`, `IQQK.DE`, `QDV5.DE`, `ICGA.DE` (XETRA) contra
     `^N225`: 2025-12-24/25/26, 2026-03-06, 04-03, 04-06, 05-01. Xetra cierra
     el 24, 25, 26 y 31 de diciembre, Viernes Santo, Lunes de Pascua y 1 de mayo.
   - `SXR8.DE`, `EUNL.DE`, `EQQQ.DE`, `ZPRR.DE`, `VVSM.DE`, `Q8Y0.DE`,
     `4GLD.DE`, `DFEN.DE` (XETRA) contra `^GSPC`: 2025-12-24, 12-26, 12-31,
     2026-03-06, 04-06, 05-01. Solo **2026-03-06** no es festivo de Xetra:
     queda para la investigación de la fase 5.
3. **El hueco real del 2026-09-07** afecta a las plazas europeas (XETRA, PAR,
   AMS, MCE, MIL, CPH): 30 activos `INCOMPLETO`. El 7 de septiembre de 2026
   fue sesión normal en Europa y festivo en EE. UU. (Labor Day). Que
   `^STOXX` tenga la barra y `SAP.DE` no, repite el patrón del 2026-08-28.
4. **El informe llama «Precio actual» al cierre del 2026-09-11** en la ficha de
   `EXH1.DE` mientras declara «última barra 2026-09-11». Fase 9 pendiente.
5. **«Liquidez recomendada: 90%»** sigue en la conclusión. Fase 12 pendiente.

## Cómo reproducir

```bash
source .venv/bin/activate
python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar > salida.txt
grep -c "calidad INCOMPLETO" salida.txt
```

La salida no es determinista día a día (depende del proveedor): compara
estructura y conteos por motivo, no bytes.
