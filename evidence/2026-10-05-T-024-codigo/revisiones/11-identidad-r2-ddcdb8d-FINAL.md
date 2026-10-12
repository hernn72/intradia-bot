# Revisión Codex (identidad-r2-ddcdb8d-FINAL) — informe literal

_Solo lectura, sin red y sin datos posteriores al 2026-08-27. Job `task-muvpiu9p-1gzjkn`._

**Veredicto: APTO.**  
0 BLOCKER, 0 IMPORTANTE. No he encontrado una vía estructural para abrir desenlaces reales usando otro repo, `cwd`, argumentos, sidecar sin commitear/modificado, formato inválido, SHA inexistente/no ancestro o commit posterior solo de evidencia.

**Hallazgos**
Ninguno.

**Confirmaciones clave**
- La ruta pública queda anclada al repo del módulo importado: `verificar_identidad()` no acepta `repo` y llama a `_verificar_identidad_en(REPO_ROOT)`; `ejecutar_mirada()` llama a `verificar_identidad()` sin override. Ver [t024_decision.py](</Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:607>) y [t024_decision.py](</Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:927>).
- El orden es el exigido: cargar SHA del sidecar, `T024_PREREG_SHA` ancestro, `T024_CODE_SHA` ancestro, `executor_unchanged_since`, árbol limpio, devolver SHA. Ver [t024_decision.py](</Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:616>).
- La marca registra el SHA validado en `T024_CODE_SHA` antes de abrir desenlaces. Ver [t024_decision.py](</Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:940>).
- No queda circularidad: `T024_CODE_LOCK` vive en `evidence/...`, fuera de `EXECUTOR_PATHS`; `executor_unchanged_since(HEAD_de_código, HEAD)` queda verde si el commit posterior solo añade ese sidecar. La prueba real `test_lock_real_sidecar_correcto_y_ejecutor_sin_cambios_pasa` cubre A → commit lock y pasa el lock contra HEAD posterior. Ver [t024_comun.py](</Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_comun.py:10>), [p4.py](</Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/p4.py:142>) y [test_t024.py](</Users/fer/Desktop/Trading bot/intradia-bot/tests/test_t024.py:529>).
- Los tests de lock usan repositorio git temporal y no monkeypatchean `T024_CODE_SHA`; solo sustituyen `T024_PREREG_SHA` para que el repo temporal sea autocontenido. Ver [test_t024.py](</Users/fer/Desktop/Trading bot/intradia-bot/tests/test_t024.py:499>) y [test_t024.py](</Users/fer/Desktop/Trading bot/intradia-bot/tests/test_t024.py:515>).

**Reproducción revisada**
- `git diff 789e4c1 HEAD` muestra solo el anclaje a `REPO_ROOT`, retirada de `repo` en `ejecutar_mirada`, y tests asociados.
- El sidecar `evidence/2026-10-05-T-024-code-lock/T024_CODE_SHA.txt` no existe en `HEAD` ni en copia de trabajo; por diseño, `cargar_t024_code_sha` falla cerrado. Ver [t024_decision.py](</Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:575>).
- No ejecuté `pytest`: el mandato era solo lectura/no crear ficheros, y esos tests crean repositorios temporales.

