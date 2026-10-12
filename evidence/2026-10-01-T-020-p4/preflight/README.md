# T-020 / A-04, paso 2 — preflight de P4 sin desenlaces

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

- `P4_PREREG_SHA` = `48b884722ef027e99857a4e65f9ab6b11da4758f` (ficha T-020 y D-63).
- `P4_EXECUTOR_CANDIDATE_SHA` = `3df8230d7806dde4151b56501641a1524a3df9d8`. Es el commit del
  ejecutor, sobre el que se generó este preflight con el árbol limpio. Pasará a ser
  `P4_EXECUTOR_SHA` solo si la revisión independiente de look-ahead del paso siguiente queda limpia.
- **P4 no se ha ejecutado.** No existe `../run/` ni la marca `EJECUCION_CONFIRMATORIA_P4_INICIADA`.
  `outcomes_read = false`, `p4_confirmatory_executed = false`.

## Ficheros

| Fichero | Contenido |
|---|---|
| `p4-preflight.json` | Salida legible por máquina (`ok = true`, `definitivo = true`, 54/54 controles) |
| `p4-preflight.txt` | La misma salida en formato humano |
| `consola-preflight.txt` | Salida literal de `python -m advisor.main p4 --fase preflight` |
| `identidad.txt` | SHA, árbol limpio, prereg en la historia, `config.yaml` en `"1.0"` sin cambios y ficheros tocados |
| `suite-ruff-mypy-pytest.txt` | ruff, mypy y la suite (824 passed) |
| `regresion-v1.txt` | Backtest `--vintage` normalizado: 866 operaciones, `49b12c85…` |
| `SHA256SUMS.txt` | Hash de cada artefacto de esta carpeta |

## Qué contiene el preflight

Solo usa primitivas del instante de señal, la apertura de `t+1`, calendarios y el contexto PIT
para estratificar. La enumeración no llama a los evaluadores de desenlace del event study.

- **Población:** A-02 swing 106.363 − cripto 5.112 = **101.251** señales, **90** activos.
  - `p4_population_sha256 = 78024050…3141`, `signal_ids_sha256 = 9faa4a45…629f`.
  - Regiones y régimen PIT iguales al censo. Las 7.157 `NO_CALCULABLE_CONTEXT` permanecen.
- **Bloques:**
  - 60 → 20 ocupados (2–21), mínimo 42: **primaria**;
  - 120 → 10, mínimo 102: **sensibilidad**;
  - 40 y 80 → mínimo 22: **inválidas**.
- **Rejilla, álgebra, niveles reales, holgura D-06, terciles, estratos, familia (m = 4) y
  recuento estructural:** 110 + 110 + 113 + 113 + 1 = **447**, de las que 4 son confirmatorias.
- **Decisiones de implementación que la ficha no fijaba literalmente:** se declaran en
  `p4-preflight.json` → `decisiones_de_implementacion`, antes de abrir ningún desenlace.
- **Congelado para la ejecución confirmatoria:** `niveles_sha256` es la huella de los niveles
  (stop, objetivos y `entry_max`) de cada geometría y señal. La confirmatoria congela la población,
  estos niveles y los cortes **antes** de escribir la marca, los registra en ella y se para si no
  coinciden. Después de la marca no se vuelve a enumerar ni se recalcula ningún nivel.

Este preflight sustituye al generado sobre `d531d1d` (historial en `bf40f0b`). El ejecutor cambió
solo para cumplir el checklist de look-ahead (`3df8230`), sin tocar estimaciones, criterio ni recuento.
