**BLOCKER**

- [advisor/research/t024_forward.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_forward.py:282): `verificar_cosecha_forward()` no comprueba que las filas reales de los CSV estén dentro de `[requested_start, requested_end)`. Esa validación solo ocurre durante `freeze_vintage()` en [advisor/research/vintage.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/vintage.py:119), pero `registrar` acepta un `data_vintage_id` ya existente y solo verifica hashes/manifest con `load_vintage()`. Escenario: una cosecha autoconsistente con `request.end = 2026-10-26`, pero CSV con barras 2026-10-26..2026-10-30 y hashes recalculados, pasa `entrada_registro()` y puede entrar al registro. Luego `capturar_checkpoint()` usa `c_e = checkpoint` en [t024_forward.py:607](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_forward.py:607), y `capturar()` acepta señales con `e_session <= c_e` en [t024_captura.py:286](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_captura.py:286), así que los días explícitamente excluidos pueden afectar conteos.

- [advisor/research/t024_decision.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:934): `ejecutar_mirada()` verifica la identidad actual, pero `cargar_registro_forward()` descarta los campos completos del registro y devuelve solo `(data_vintage_id, checkpoint)` en [t024_decision.py:646](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:646). No se exige que la entrada registrada tenga `T024_CODE_SHA == code_sha` antes de abrir desenlaces en [t024_decision.py:971](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:971). `capturar_checkpoint()` sí lo hace en [t024_forward.py:602](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_forward.py:602), pero la ruta decisoria final no. Escenario: registro canónico con entrada de una cosecha congelada bajo otro `T024_CODE_SHA` de 40 hex; `validar_registro()` lo acepta y la mirada puede consumir marca y abrir resultados bajo otra identidad.

**IMPORTANTE**

- [advisor/research/t024_forward.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_forward.py:438): `_validar_entrada()` no valida contenido de varios campos que declara canónicos: `n_symbols`, `provider`, `provider_version` y `manifest_file_sha256`. Un registro con `symbols_sha256` correcto pero `n_symbols = 0`, `provider = "evil"` o `manifest_file_sha256 = "x"` puede pasar si se recalcula `entradas_sha256`. `capturar_checkpoint()` lo detecta al reproducir `entrada_registro()`, pero `cargar_registro_forward()`/`ejecutar_mirada()` no reproducen la entrada contra disco, así que el lector decisorio no está aceptando “solo el registro canónico completo” en sentido semántico.

**MENOR**

- No pude ejecutar scripts de reproducción con los módulos reales: el sandbox no tiene `pandas` para `python3`, y `pytest` estaba fuera de alcance según el encargo. La revisión queda basada en inspección estática con líneas.

**OBSERVACIÓN**

- Las correcciones de ronda 2 van en la dirección correcta: `capturar_checkpoint()` exige `verificar_identidad()`, reproduce la entrada registrada contra la cosecha, y la salida se valida por claves y contenido. El hueco principal es que esas garantías fuertes no se trasladan a `ejecutar_mirada()` y que la aptitud de una cosecha registrada no revalida el rango temporal de los datos cargados.

Codex session ID: 01a11060-bf17-7810-8454-a93792ddf98b
Resume in Codex: codex resume 01a11060-bf17-7810-8454-a93792ddf98b
