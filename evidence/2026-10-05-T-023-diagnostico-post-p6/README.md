# T-023 — Diagnóstico post-P6: por qué el edge por operación no supera al buy-and-hold

> **Exploratorio / post hoc. No cambia D-70, no valida una nueva política y no constituye evidencia
> confirmatoria.**

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

## Qué es

Un post mortem **descriptivo** de P6 hecho solo con artefactos ya publicados. P6 sigue cerrado y
consumido (D-70): B2 `NO PASA`, S2 `NO PASA` y salida `[]`. GATE P6 está cruzado y P7 sigue
**BLOQUEADO**. T-023 no es una fase confirmatoria, no rescata candidatas, no crea políticas ni
umbrales, y no tiene gate que cruzar: prepara una decisión posterior del propietario (D-71).

**Pregunta:** dónde se abre, contable y temporalmente, la brecha entre el edge positivo por operación
de B2/S2 y el rendimiento mucho mayor del comprar y mantener del mismo universo, y qué mecanismos
observables son compatibles con ella.

## Identidades

| | |
|---|---|
| Base (`main`) | `26dea364f32866d135f938f128aba541d20b6469` |
| `P6_PREREG_SHA` | `03f04a42ea9d2be893e7c4cc09de76bd1c55778b` |
| `P6_CODE_SHA` | `bc0636d4320b38ef5a620fa9ae94cee35df47580` |
| `P6_RUN_HEAD_SHA` | `353876d39d03f6849847743b9f4e7f791abbed30` |
| `P6_RUN_EVIDENCE_SHA` | `0771989af851748463aa0e79d4a7dc327066ca5f` |

## Método

- `diagnostico_p6.py` lee **solo** los inputs que fija `fuentes.json`: el resultado, los ledgers, las
  operaciones y las series de las 7 corridas y del benchmark de `evidence/2026-10-03-T-022-p6/run/`,
  el mapa de sectores congelado y `universe.yaml`. Antes de leer nada comprueba el sha256 de cada input
  y el manifiesto `SHA256SUMS-ejecucion.txt` de P6, y aborta si algo no coincide.
  `--fijar-fuentes` es solo para fijar ese fichero una vez.
- No importa `advisor`, no simula, no carga cosechas, no usa red, ni reloj, ni aleatoriedad, y no
  escribe fuera de este directorio. Dos ejecuciones producen los mismos bytes.
- Solo suma, agrupa y reconcilia lo que ya está en los ficheros. La exposición y las posiciones diarias
  se reconstruyen desde el ledger, porque la instantánea de P6 es a las 23:59:59 UTC tras todos los
  eventos del día, y **reproducen exactamente** las medias publicadas por P6. El script aborta si no
  coinciden.
- Ningún número es contrafactual. Lo que exigiría simular se marca `NO_IDENTIFICABLE`.

Uso, desde la raíz del repositorio: `python evidence/2026-10-05-T-023-diagnostico-post-p6/diagnostico_p6.py`

## Ficheros

| Fichero | Contenido |
|---|---|
| `diagnostico_p6.py` | Script determinista de diagnóstico |
| `fuentes.json` | SHA del repositorio e identidades de P6, y sha256 de los 30 inputs |
| `trayectorias.csv` | Índices diarios (base 100) de B2, S2, C0 y el benchmark |
| `brecha-temporal.csv` | Brecha diaria, por año y por mitad; brecha logarítmica y su aporte anual; exceso mensual; mejores y peores meses; hitos; alrededor de los drawdowns |
| `ocupacion-cash.csv` | Exposición, cash y posiciones (publicados y reconstruidos); tramos de exposición cruzados con retornos; tramos por año |
| `presion-capital.csv` | Eventos y rechazos por motivo; presión de cash; serie anual y mensual; días con rechazo |
| `operaciones-por-salida.csv` | Anatomía del edge: distribución de R, motivo de salida, año, riesgo y tamaño por operación |
| `contribucion-por-activo.csv` | P&L por activo de las políticas y el benchmark; concentración; captura de los mejores activos del benchmark |
| `contribucion-region-sector-divisa.csv` | P&L, notional y exposición por región, sector y divisa de cotización |
| `costes-fx-dividendos.csv` | Comisiones, slippage, dividendos y FX en EUR y como fracción del capital, del beneficio y de la brecha |
| `comparativa-primaria-todas-barras.csv` | Primaria frente a todas las barras (descriptivo), con C0 y benchmark de referencia; rotación anual |
| `hallazgos.md` | Hallazgos clasificados `OBSERVADO` / `COMPATIBLE_CON` / `NO_IDENTIFICABLE` y respuestas a las 12 preguntas |
| `hipotesis-candidatas.md` | H23-01 a H23-05, post hoc y falsables con un estudio nuevo |
| `OWNER_DECISION_REQUIRED.md` | Opciones para una D-71 aparte |
| `revision-final.md` | Revisión independiente (Codex) y verificación propia |
| `pytest-ruff-mypy.txt` | Suite, ruff y mypy antes y después |
| `SHA256SUMS.txt` | sha256 de los ficheros de este directorio |

## Lo que no cambia

P6, D-70 y su salida `[]`; Score v1 y v2; C0, B2 y S2; `config.yaml` y `universe.yaml`; producción y
la Pi; P7, R-01 y P10. `evidence/2026-10-03-T-022-p6/run/` queda intacto byte a byte.
