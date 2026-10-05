# Revisión Codex (identidad-r1-789e4c1) — informe literal

_Solo lectura, sin red y sin datos posteriores al 2026-08-27. Job `task-muvn93z3-naaoex`._

**Veredicto: NO PASA.** Encontré **0 BLOCKER, 1 IMPORTANTE, 0 MENOR, 1 OBSERVACIÓN**.

**IMPORTANTE — `repo` permite validar un árbol distinto del código que se está ejecutando.**  
En [advisor/research/t024_decision.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:917), `ejecutar_mirada(..., repo=...)` acepta un repo arbitrario y lo pasa a `verificar_identidad` en la línea 919. Después, `cargar_t024_code_sha` y las comprobaciones git usan ese `cwd=repo` en líneas 582, 608, 610, 612 y 614, pero no hay ninguna comprobación que ate ese repo al árbol desde el que se importó `advisor.research.t024_decision`.

Reproducción conceptual, sin datos reales: importar el módulo desde un checkout B modificado y llamar `ejecutar_mirada(..., repo="/ruta/a/checkout-A-limpio-con-sidecar")`. La identidad valida A, devuelve el SHA de A y la marca registra ese SHA en [t024_decision.py:933](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:933), pero los desenlaces los calcula el código cargado desde B. No es monkeypatch del módulo; es una ruta estructural por argumento.

**OBSERVACIÓN — Este HEAD aún no contiene el sidecar real.**  
La ruta canónica está fijada en [advisor/research/t024_comun.py:13](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_comun.py:13), pero `git show HEAD:evidence/2026-10-05-T-024-code-lock/T024_CODE_SHA.txt` falla con “path ... does not exist in HEAD”. Esto falla cerrado, no abre desenlaces, pero el lock real todavía no puede pasar en este HEAD.

Comprobaciones relevantes:

- Orden exigido: sí. `cargar SHA → PREREG ancestro → CODE_SHA ancestro → executor_unchanged_since(CODE_SHA) → tree_dirty → return SHA` está en [t024_decision.py:607](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:607).
- Marca: sí, registra exactamente el `code_sha` devuelto por `verificar_identidad` en [t024_decision.py:936](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:936).
- Formato del SHA: rechaza corto, ambiguo, mayúsculas, espacios y varias líneas por regex `40 hex minúscula` en [t024_decision.py:569](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:569) y línea 599.
- Sidecar sin commitear/modificado: queda denegado por `git show HEAD:<path>` y comparación byte a byte con copia de trabajo en [t024_decision.py:580](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:580).
- Circularidad: `evidence/` y `tests/` no están en `EXECUTOR_PATHS`; `advisor/` sí, en [p4.py:142](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/p4.py:142). Un commit posterior que solo añada el sidecar en `evidence/` y contenga `789e4c1...` debería dejar `executor_unchanged_since` en verde.
- Tests: los tests temporales sí prueban el mecanismo real sin monkeypatchear el SHA de código y cubren válido, ausente, sin commitear, modificado, inválido, no ancestro, inexistente, ejecutor cambiado y circularidad en [tests/test_t024.py:499](/Users/fer/Desktop/Trading%20bot/intradia-bot/tests/test_t024.py:499). Falta cobertura del caso “repo distinto al código importado”.

No ejecuté `pytest` para respetar el mandato de no crear ficheros.

