# Revisiones de la respuesta al incidente y del despliegue T-024 en la Pi (PR #46)

| Fichero | Rango | Resultado |
|---|---|---|
| 01-codex-ee256e6 | b718917..ee256e6 | 1 BLOCKER, 3 IMPORTANTE, 2 MENOR: corregidos en ac975eb |
| 02-codex-ac975eb | b718917..ac975eb | 0 BLOCKER, 2 IMPORTANTE, 2 MENOR: no se leyó en su momento por el incidente; corregidos en 75aff57 |
| 03-codex-703c581 | b718917..703c581 | 2 BLOCKER, 3 IMPORTANTE, 2 MENOR: corregidos en 740d7e3 |
| 04-codex-740d7e3 | b718917..740d7e3 | 0 BLOCKER, 3 IMPORTANTE, 2 MENOR: corregidos en 6a0af43 |
| 05-codex-6a0af43 | b718917..6a0af43 | 1 BLOCKER, 2 IMPORTANTE: corregidos en 8c5ba1f |
| 00-codex-8c5ba1f-cortada-por-limite-de-uso | b718917..8c5ba1f | sin veredicto (límite de uso de Codex) |
| 00-revisor-claude-8c5ba1f | b718917..8c5ba1f | 0 BLOCKER, 0 IMPORTANTE, 4 MENOR: corregidos en 10f2702 |
| 06-codex-10f2702 | b718917..10f2702 | 0 BLOCKER, 1 IMPORTANTE, 1 MENOR: corregidos en b37de47 |
| 07-codex-b37de47 | b718917..b37de47 | 0 BLOCKER, 3 IMPORTANTE: corregidos en 4964869 |
| 08-codex-4964869 | b718917..4964869 | 0 BLOCKER, 1 IMPORTANTE: corregido en d9892c5 |
| 09-codex-d9892c5 | b718917..d9892c5 | 0 BLOCKER, 2 IMPORTANTE: corregidos en 5866152 |
| 10-codex-5866152 | b718917..5866152 | 0 BLOCKER, 1 IMPORTANTE: corregido en 6238fc9 |
| 11-codex-6238fc9 | b718917..6238fc9 | APTO en borrado: 0 / 0 / 0 |
| 12-codex-global-75aff57 | b718917..75aff57 | global: 0 BLOCKER, 2 IMPORTANTE: corregidos en 155b66a |
| 13-codex-global-155b66a | b718917..155b66a | global: 0 BLOCKER, 1 IMPORTANTE, 1 MENOR: corregidos en ab88fe2 |
| 14-codex-global-ab88fe2 | b718917..ab88fe2 | global: 0 BLOCKER, 0 IMPORTANTE, 1 MENOR: corregido en adbd482 |
| 15-codex-global-adbd482 | b718917..adbd482 | global: 0 BLOCKER, 0 IMPORTANTE, 1 MENOR: corregido en 25382ad |
| **16-codex-global-25382ad-FINAL** | **b718917..25382ad** | **APTO global: 0 BLOCKER / 0 IMPORTANTE / 0 MENOR** |

Las rondas 06–11 trataron la red de tests (`tests/red_borrado.py`); la guarda de producción
(`deploy/t024/borrado_seguro.py`) quedó sin hallazgos desde 05. Las rondas 12–16 son globales sobre todo el
rango del PR: despliegue en la Pi, identidad, contrato y borrado.
