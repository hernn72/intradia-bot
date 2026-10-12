**BLOCKER**

- [advisor/research/t024_decision.py:637](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:637): `cargar_registro_forward` acepta registros contaminados con desenlaces. Solo lee `data_vintage_id`, `checkpoint` y `sha256`; ignora `schema`, `schema_version`, `entradas_sha256`, claves extra top-level y claves extra dentro de cada entrada. Luego `ejecutar_mirada` usa ese lector en [advisor/research/t024_decision.py:929](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:929), antes de abrir desenlaces.  
  Escenario: un `registro-forward.json` con `cosechas[0].D2`, `cosechas[0].R`, `mean_R` o cualquier salida post hoc pasa si el `sha256` mínimo está calculado solo sobre `data_vintage_id/checkpoint`, que es exactamente lo que esa función recalcula. El nuevo `t024_forward.validar_registro` sí lo rechaza, pero la ruta decisoria que realmente consume el registro no lo llama.

**IMPORTANTE**

- [advisor/research/t024_forward.py:567](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_forward.py:567): `capturar_checkpoint` ignora `root_dir` al reconstruir la petición: llama `peticion_de_entrada(entrada)` y esa función usa por defecto `simbolos_root="data/vintages"` en [advisor/research/t024_forward.py:473](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_forward.py:473).  
  Escenario: se congela/registra con `--data-dir /ruta/aislada` y luego se captura con ese mismo `--data-dir`; la captura deriva los símbolos desde el manifiesto de `data/vintages/071ddb...`, no desde la raíz indicada. Si esa raíz no existe o contiene otro lock de desarrollo, falla o verifica contra una fuente distinta de la cosecha que está capturando. El test pasa por razón equivocada porque el repo local sí tiene `data/vintages`.

- [advisor/research/t024_decision.py:648](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:648): el lector decisorio solo comprueba ordenación no decreciente, no orden estrictamente creciente ni duplicados.  
  Escenario: dos entradas con el mismo `checkpoint` pasan `cargar_registro_forward`; `t024_forward.validar_registro` lo impediría, pero `ejecutar_mirada` no usa esa validación. Esto abre una divergencia entre “registro canónico” y “registro aceptado por decisión”.

- [advisor/research/t024_forward.py:587](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_forward.py:587): `validar_salida` es una validación superficial de claves, no del contenido.  
  Escenario: si por un bug aguas arriba `rechazos` o `exclusiones` contienen claves tipo `"D2_media=..."`, `"R"`, `"exit_reason"` o valores no enteros, la salida sigue pasando porque solo se valida el conjunto de claves del bloque de política. El test solo cubre claves extra, no fuga dentro de los mapas permitidos.

**MENOR**

- [advisor/data/bar_cache.py:287](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/data/bar_cache.py:287): el wrapper de caché `get_raw_history` no acepta `start/end`.  
  Escenario: si alguien intenta reutilizar `freeze_vintage(..., start=..., end=...)` con un proveedor cacheado, todos los símbolos exactos fallan por `unexpected keyword argument 'start'`. El CLI nuevo usa `MarketDataProvider` directo, así que no rompe el runbook actual, pero la interfaz del proveedor queda partida.

- [tests/test_t024_forward.py:489](/Users/fer/Desktop/Trading%20bot/intradia-bot/tests/test_t024_forward.py:489): el test de compatibilidad del registro solo prueba el caso positivo con el escritor canónico. No prueba que `t024_decision.cargar_registro_forward` rechace claves de desenlace, duplicados o esquema no canónico. Justo ahí está la brecha.

**OBSERVACIÓN**

- No he visto cambios de comportamiento del modo `period` en las llamadas normales: las rutas existentes siguen pasando `period=` explícito, y `MarketDataProvider.get_raw_history` conserva los kwargs de yfinance cuando no hay `start/end`.

- La regla del primer checkpoint parece correcta: con festivo `2026-11-02`, `end_exclusivo(2026-11-03)` devuelve `2026-10-26`; sin ese festivo se rechaza porque el 3 ya no sería primer hábil.

- No pude ejecutar `pytest` por la restricción del sandbox. Sí hice lectura completa del diff relevante y scripts mínimos de solo lectura con `.venv/bin/python` donde el sandbox lo permitió.

Codex session ID: 01a1104f-6027-7602-b044-aecde9950db9
Resume in Codex: codex resume 01a1104f-6027-7602-b044-aecde9950db9
