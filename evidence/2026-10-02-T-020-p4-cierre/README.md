# T-020 / A-04 — cierre de P4 (GATE P4 cruzado, D-65)

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

**Identidad.**

| | SHA |
|---|---|
| `P4_PREREG_SHA` | `48b884722ef027e99857a4e65f9ab6b11da4758f` |
| `P4_CODE_SHA` | `3df8230d7806dde4151b56501641a1524a3df9d8` (último commit que modifica el código del ejecutor) |
| `P4_RUN_HEAD_SHA` | `c2c52b11c60bb8dfd08d8cb33d5f6f251e9bf2c0` (HEAD desde el que se lanzó la ejecución) |
| Evidencia de la ejecución | `cfa365da468edd04f0ccf4d5f20b657382078cbd` (`../2026-10-01-T-020-p4/run/`, inmutable) |
| D-64 (resultado) | `3d860360b13f34a463b7adb5d15d971773b6a908` |
| Correcciones de la revisión final | `72c3cef6355c8beec050078cc295ca9aed74186a` |

**El campo `p4_executor_sha` de la ejecución no es un error.** En los artefactos de ejecución
contiene el HEAD desde el que se lanzó (`c2c52b1`). La marca conserva aparte
`p4_executor_sha_preflight = 3df8230`, el último commit que modifica el código del ejecutor. Entre
los dos solo cambia evidencia de preflight. No es un error de resultado, y los artefactos no se
reescriben.

## Ficheros

| Fichero | Contenido |
|---|---|
| `resultado-y-heterogeneidad.md` | Resultado (D-64) y discusión de los estratos pre-registrados de B2, S2, S1 y B1 |
| `estratos-congelados.md` | Copia literal de todos los estratos de `run/tablas/estimaciones.tsv`, incluidos los 90 activos |
| `leer_estratos.py` | Lector puro del TSV que genera el fichero anterior. No calcula ninguna estimación |
| `revision-look-ahead.md` | Revisión de look-ahead previa a la ejecución, archivada después |
| `revision-final.md` | Revisión final independiente y su vuelta de cierre: 0 BLOCKER, 0 IMPORTANTE |
| `gate-p4-final.md` | Matriz de los cuatro requisitos de GATE P4 |
| `final-pytest-ruff-mypy.txt` | ruff, mypy y la suite con la cosecha: 825 passed, 0 skipped |
| `hashes-evidencia.txt` | Verificación de los 12 SHA256 de `run/` y hashes de esta carpeta |

## Qué no se hizo
- No se repitió P4.
- No se recalculó ninguna variante ni se creó ningún análisis nuevo.
- No se modificó `run/`.
- No se tocó producción: `config.yaml` sigue en `"1.0"`, Score v2 inactivo, la Pi en `v0.4.1`, y
  no hubo ni release ni despliegue.
