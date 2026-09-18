# T-011 + T-017 — release por tag e higiene del manifiesto

Fecha: 2026-09-18
Rama: `feat/release-by-tag-and-manifest-hygiene`, desde `main` en `11efae8`
Agentes: Opus (implementación) → Codex (revisión independiente, solo lectura) → Opus (correcciones)

Las dos fichas van juntas **para migrar una sola vez** la base de producción:
ambas añaden columnas al manifiesto, y dos migraciones consecutivas sobre la
misma tabla son exactamente lo que T-017 prohíbe.

## Qué hay en este directorio

| Fichero | Qué demuestra |
|---|---|
| `suite-despues.txt` | `pytest`, `ruff` y `mypy` tras la entrega |
| `migracion-v4-a-v5.txt` | migración sobre una **copia de la base real** del portátil |
| `migracion-con-manifiestos.txt` | la misma migración con manifiestos de la forma que tiene la Pi: los conserva con su `config_hash` y `config_hash_version = 1` |
| `inyeccion-de-defectos.txt` | cada corrección con su defecto inyectado en una copia del árbol y el test fallando |
| `verificar-release.txt` | el comando nuevo sobre el repositorio real |
| `pasada-rama.txt` / `.log` | pasada real de análisis sobre los 103 analizables |
| `pasada-main.txt` | la misma pasada con el código de `main` (`11efae8`) |
| `comparacion-main-vs-rama.txt` | ninguna recomendación cambia de radar ni de acción |
| `pasada-grupos-europa.txt` / `.log` | pasada con `--grupos europa`: 28 analizables |
| `vintage-por-grupo.txt` | el vintage del grupo (`1d721d98`) es distinto del de los 103 (`c8496446`) |
| `verificar-backup.txt` | el antes y el después sobre los **mismos dos ficheros reales**: la copia manual del 2026-09-02 pasa de «Backup invalido» a `VALIDO` con «no registrado (copia manual)» |

Línea base en `main` (`11efae8`), antes de tocar nada: **550 tests, `ruff` y
`mypy` limpios**. Al cerrar: **574 tests** (24 nuevos), `ruff` y `mypy` limpios.

## Lo que no se puede medir aquí

Tres cosas solo existen en la Pi y quedan para el ensayo de OA-04:

1. El **recuento de manifiestos migrados** en producción (el portátil tiene 0:
   aquí siempre se corre con `--sin-guardar`).
2. Que el **`config_hash` del portátil y el de la Pi coinciden** para la misma
   configuración lógica. Es *la* prueba de T-017 y antes daba distinto por
   construcción.
3. El **rollback probado de verdad** (punto 6 de T-011). Mientras no se ejecute,
   T-011 sigue en EN_REVISION: un rollback escrito no es un rollback.

## La revisión de Codex, y por qué importa

Codex revisó el diff en solo lectura y encontró un BLOCKER real: `verificar-release`
aceptaba **cualquier** tag exacto, no solo `vX.Y.Z`. Con un tag `release-test` en
`HEAD` el comando decía `EN_TAG` y salía con 0, o sea daba por desplegado algo
que el flujo de release de CI nunca construye. La suite estaba verde: ninguno de
los tests probaba un tag que no fuera de release.

Es el mismo patrón que se repitió tres veces el 2026-09-18 con las entregas de
Codex, esta vez en la dirección contraria. Lo que lo cazó no fue ejecutar más
tests, sino preguntar explícitamente por los casos límite del contrato.

Los otros tres hallazgos (copia SQLite vacía dada por válida, copia registrada
que ha cambiado, respaldo previo sin registrar) están corregidos y cada uno
tiene su test de regresión, verificado por inyección.
