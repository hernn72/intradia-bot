**BLOCKER**

1. [advisor/research/vintage.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/vintage.py:119) sigue rechazando barras anteriores a `start` durante la propia congelación exacta.
   Escenario: la cosecha consumida ya muestra `EURUSD=X` con primera barra `2021-08-29T23:00:00Z` para el `start` contractual `2021-08-30` (`data/vintages/.../EURUSD%3DX.csv`). `_require_inside_range()` en [vintage.py:407](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/vintage.py:407) compara `pd.Timestamp(ts).date()` contra `start`, marca `2021-08-29` como fuera de rango y mete EURUSD=X en `failed`. Resultado: la primera cosecha real T-024 queda parcial/no apta aunque la nota de diseño dice explícitamente que el límite inferior no debe revalidarse.

2. [advisor/research/t024_decision.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:941) permite que `ejecutar_mirada` abra la ruta decisoria con una cosecha parcial si el registro fue forjado de forma canónica.
   `capturar_checkpoint` sí reproduce `entrada_registro()` antes de capturar ([t024_forward.py:652](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_forward.py:652)), pero `ejecutar_mirada` solo llama a `exigir_procedencia()`. Esa función únicamente comprueba `T024_CODE_SHA`, `data_vintage_id/manifest_hash`, `request.context`, `start/end` y límite superior ([t024_forward.py:551](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_forward.py:551)); no comprueba `manifest["failed"]`, que los 126 assets estén presentes, `symbols`, `symbols_sha256`, `universe_vintage_id`, `provider`, `provider_version` ni `manifest_file_sha256`.
   Escenario concreto: `freeze_vintage` deja una cosecha con 125 assets y `failed=[EURUSD=X]`; se escribe manualmente un registro canónico con esa `data_vintage_id`, hashes recalculados y campos de entrada aparentemente válidos. `cargar_registro_forward()` lo acepta y `ejecutar_mirada()` puede llegar a `capturar()` sobre una cosecha incompleta.

**IMPORTANTE**

1. [advisor/research/t024_forward.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_forward.py:457) valida `manifest_file_sha256` solo por formato, no contra el fichero real, y `provider_version` solo como string no vacío.
   En `ejecutar_mirada`, esto no se repara después: `exigir_procedencia()` no cruza esos campos con el manifiesto cargado. Un registro con `manifest_file_sha256="f"*64` y `provider_version="9.9"` pasa si se recalcula `entradas_sha256`, aunque no describa la cosecha real. Esto rompe la corrección de ronda 2 para la mirada decisoria.

**MENOR**

1. [tests/test_t024_forward.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/tests/test_t024_forward.py:272) codifica como esperado que una barra anterior a `start` falle en `freeze_vintage`.
   Eso contradice el diseño actual de ronda 3 y deja sin test el caso real `EURUSD=X` con `2021-08-29T23:00:00Z`.

2. [tests/test_t024_forward.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/tests/test_t024_forward.py:1011) solo prueba `manifest_file_sha256` inválido por formato y `provider_version` vacío.
   Falta el caso adversarial importante: valores bien formados pero falsos, especialmente en `ejecutar_mirada`.

**OBSERVACIÓN**

No he visto regresión evidente en el modo `period` ni en `load_vintage` para cosechas existentes: el manifiesto schema 1 sigue sin `request`, y el test fija el id/hash legacy. Tampoco he ejecutado `pytest`, conforme a la restricción; la revisión fue por lectura y comandos sueltos de inspección.

Codex session ID: 01a1106e-2e63-7ac1-bf1a-2fe207251de0
Resume in Codex: codex resume 01a1106e-2e63-7ac1-bf1a-2fe207251de0
