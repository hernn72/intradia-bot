# T-003 calendarios de plaza

- Fecha: 2026-09-14
- Rama: `fix/exchange-calendars`
- Python local: 3.12 (`.venv`)
- Línea base reutilizada: `antes.txt`, `baseline-pytest.txt`, `baseline-ruff.txt`, `baseline-mypy.txt`.

## Comandos ejecutados

```bash
source .venv/bin/activate
python -m pytest -q
ruff check .
mypy advisor
python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar > evidence/2026-09-14-T-003-calendarios/despues.txt
python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar > evidence/2026-09-14-T-003-calendarios/despues.txt  # reintento único
```

## Resultado

- Tests: 431 passed, 1 warning.
- Ruff: All checks passed.
- Mypy: Success, no issues found in 58 source files.
- Verificación real: **hecha por Claude Code** el 2026-09-14 a las 14:01 UTC (la sesión de Codex no tiene DNS). `despues.txt` es esa pasada: 107 activos, `exit=0`, run `c2a22e5f-2518-487a-a314-5aa4bd81aca5`.

## Comprobación manual posible

No se pudo comprobar contra datos reales `AZN`, `TSM`, `SXR8.DE`, `IQQT.DE`, `SAP.DE` ni `BTC-EUR` porque el proveedor no devolvió históricos. No se inventan resultados.

Sí quedó cubierto sin red por tests con fechas cerradas:
- `XETRA`: no espera 2026-04-06 y sí espera 2026-09-07.
- `NYSE`: no espera 2026-09-07 y sí espera 2026-09-08.
- `CRYPTO`: sábado, domingo y 25 de diciembre son sesiones válidas.
- `test_benchmark_nunca_define_sesiones`: un benchmark con fecha extra no genera ausencias del activo.

## BLOCKER

BLOCKER de aceptación real: proveedor de datos/Yahoo inaccesible por DNS desde esta sesión. Tras el reintento único exigido por la ficha, no hay evidencia real suficiente para medir impacto antes/después ni validar a mano los seis símbolos.

## Verificación real — 2026-09-14 14:01 UTC (Claude Code)

```bash
python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar \
  > evidence/2026-09-14-T-003-calendarios/despues.txt 2>&1
```

Comparada con `evidence/2026-09-14-L0-baseline/analizar-swing-sin-ia.txt`:

| Medida | Antes (benchmark como calendario) | Después (calendario de plaza) |
|---|---|---|
| Calidad `OK` | 59 | **63** |
| Calidad `INCOMPLETO` | 30 | **28** |
| Calidad `DEGRADADO` | 18 | **16** |
| Activos con sesiones ausentes | 43 | 44 |
| Encabezado | «frente al benchmark» | «frente al calendario de su plaza» |
| Sin calendario de referencia | 5 (`IS3N.DE`, 3 criptos, `INFY`) | **0** |

Los seis casos que la línea base dejó anotados, comprobados a mano en `despues.txt`:

| Símbolo | Antes | Después |
|---|---|---|
| `AZN` (NASDAQ vs `^STOXX`) | 6 ausencias, todas festivos de EE. UU., `INCOMPLETO` y vetada | **0 ausencias** |
| `TSM` (NYSE vs `^TWII`) | 5 ausencias, festivos de EE. UU. | **0 ausencias** |
| `SXR8.DE`, `EUNL.DE` (XETRA vs `^GSPC`) | 6 ausencias | **1**: `2026-03-06` en XETR |
| `IQQT.DE` (XETRA vs `^N225`) | 7 ausencias | **1**: `2026-03-06` en XETR |
| `SAP.DE` | `2026-09-07` | `2026-09-07` en XETR (hueco real, se mantiene) |
| `BTC-EUR`, `ETH-EUR`, `SOL-EUR` | «sin calendario de referencia» | calendario `CRYPTO_24_7`, sin ausencias |

Reparto de las ausencias que quedan, todas reales y ya identificadas como
trabajo de T-004:

| Fecha | Activos | Plazas |
|---|---|---|
| 2026-09-07 | 28 | XETR, XPAR, XMIL, XMAD, XAMS, XCSE |
| 2026-03-06 | 14 | XETR |
| 2026-07-17 | 2 | XKRX |
| 2026-06-03 | 2 | XKRX |
| 2026-03-23 | 1 | XCSE |

Es decir: desaparecen todos los falsos huecos por festivo ajeno y quedan
exactamente los dos casos que la línea base predijo (`2026-09-07` y
`2026-03-06`), más tres aislados coreanos y daneses que T-004 debe clasificar
con la misma herramienta.

El `universe_vintage_id` sigue siendo el provisional `80d05f21…` porque T-006
no se ha ejecutado.
