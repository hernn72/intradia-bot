# T-003 calendarios de plaza

- Fecha: 2026-09-14
- Rama: `fix/exchange-calendars`
- Python local: 3.12 (`.venv`)
- **Línea base real: `evidence/2026-09-14-L0-baseline/analizar-swing-sin-ia.txt`** (59 `OK` / 30 `INCOMPLETO` / 18 `DEGRADADO`, 43 activos con ausencias). Es la única con la que se compara.
- `pasada-fallida-por-dns.txt` **no es una línea base**: es la pasada que Codex no pudo completar (138 `Could not resolve host`, los 107 activos sin datos). Se conserva como registro del bloqueo, no como material de comparación.
- `pip-install-fallido-por-dns.txt` es igualmente el log del intento fallido. La instalación en Python 3.13 quedó verificada en la Pi el 2026-09-16: `evidence/2026-09-16-T-003-correcciones/pi-python313-exchange-calendars.txt`.
- Estado de lint y tipos de la línea base: `baseline-pytest.txt`, `baseline-ruff.txt`, `baseline-mypy.txt`.

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

## BLOCKER (resuelto el mismo día)

Durante la sesión de Codex el proveedor de datos/Yahoo fue inaccesible por DNS, y tras el reintento único exigido por la ficha no hubo evidencia real para medir impacto ni validar a mano los seis símbolos. **Claude Code ejecutó la pasada real ese mismo día a las 14:01 UTC**; la sección siguiente es esa verificación y el BLOCKER queda cerrado.

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

## Activos que cambian de radar o de acción: 0

Medición que la ficha pedía y que faltaba. Comparadas las dos pasadas:
RADAR idéntico (mismos 10 símbolos y mismas notas), OPERAR idéntico
(`EXH1.DE`, nota 74) y 90 descartados antes y después, con el mismo conjunto de
símbolos. Lo único que cambia es el **motivo**: `AZN` y `TSM` dejan de llevar
«calidad INCOMPLETO». Es lo esperado, porque la entrega no toca el score ni la
clasificación (INV-03): solo corrige qué sesiones se esperan.

## Correcciones posteriores a la revisión independiente

La revisión independiente del 2026-09-16 encontró un BLOCKER y tres defectos de
alcance. Están corregidos y verificados en
`evidence/2026-09-16-T-003-correcciones/`.
