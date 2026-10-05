# Revisión Codex (api-r6-ddcdb8d-FINAL) — informe literal

_Solo lectura, sin red y sin datos posteriores al 2026-08-27. Job `task-muvpiuhk-hu2dsc`._

**Hallazgos**

BLOCKER: 0  
IMPORTANTE: 0  
MENOR: 0

OBSERVACIÓN, sin acción: [t024_decision.py](</Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:575>) mantiene pública `cargar_t024_code_sha(repo)`, que acepta un repo y devuelve el SHA del sidecar. Reproducción: el test [tests/test_t024.py](</Users/fer/Desktop/Trading bot/intradia-bot/tests/test_t024.py:529>) crea un repo temporal y [tests/test_t024.py](</Users/fer/Desktop/Trading bot/intradia-bot/tests/test_t024.py:532>) llama a esa función. No lo clasifico como MENOR porque no valida identidad completa, no abre desenlaces, no permite inyectar `code_sha` en `ejecutar_mirada`, y la ruta pública decisoria sigue sin `repo` ni `code_sha`.

**Veredicto**

PASA para API y guardas bajo el modelo de amenaza indicado: 0 BLOCKER y 0 IMPORTANTE.

Confirmado por lectura del diff `70ffdf7..HEAD`: solo toca identidad en [t024_comun.py](</Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_comun.py:10>) y [t024_decision.py](</Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:569>), más tests/evidencia. No toca `t024_captura.py` ni cambia rutas de cálculo de salidas salvo el encadenado de identidad.

`ejecutar_mirada` deniega antes de cualquier desenlace si falla la identidad: la primera instrucción efectiva es `code_sha = verificar_identidad()` en [t024_decision.py](</Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:927>). Como el sidecar no existe en `HEAD` ni en copia de trabajo, `cargar_t024_code_sha` falla cerrado antes de registro forward, captura, marca, token o lectura de barras.

Las guardas estructurales siguen activas: `TokenMirada` y hash de marca en [t024_decision.py](</Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:184>), origen de cosecha en [t024_decision.py](</Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:193>), calendario/máximo dos miradas en [t024_decision.py](</Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:705>), registro forward y primera cosecha a 75 días en [t024_decision.py](</Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:637>) y [t024_decision.py](</Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:667>), reconfirmación antes de marca en [t024_decision.py](</Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:935>), marca exclusiva antes del token en [t024_decision.py](</Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:954>), y revocación del token en `finally` en [t024_decision.py](</Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:963>).

Cobertura inspeccionada: los tests nuevos cubren sidecar real ausente/no versionado/modificado/formato inválido/no ancestro, repo importado vs `cwd`, ausencia de `repo`/`code_sha` en la API decisoria, token, origen de cosecha, reconfirmación fallida sin marca/desenlace, calendario, registro forward, capacidad por política y máximo dos miradas. No ejecuté pytest por el mandato de solo lectura: varios tests crean repos temporales, marcas y ficheros.

