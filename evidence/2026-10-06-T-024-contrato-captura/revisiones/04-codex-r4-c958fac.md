**BLOCKER**

- `advisor/research/t024_decision.py:924` / `advisor/research/t024_decision.py:943` + `advisor/research/t024_forward.py:553`: `ejecutar_mirada` sigue confiando en un `VintageLoad` recibido en memoria. `exigir_procedencia` cruza `request`, símbolos, `manifest_file_sha256`, `provider_version` y rango superior, pero no prueba que ese `VintageLoad` venga de `load_vintage()` ni que sus `views.raw` cuadren con los `series_hash` / `corporate_actions_hash` del manifiesto. Además `validar_registro` acepta `data_vintage_id` no-SHA mientras sea `str` (`advisor/research/t024_forward.py:455`).
  
  Escenario: se forja un registro canónico con `data_vintage_id="v1"`, request/context correctos, `failed=[]`, 126 símbolos y `manifest_file_sha256` calculado sobre un manifiesto falso; luego se pasa a `ejecutar_mirada` un `VintageLoad("v1", manifest_falso, by_symbol=...)` con barras arbitrarias antes de `end`. Pasa procedencia y llega a `capturar` en `advisor/research/t024_decision.py:948`, abriendo desenlaces sobre una cosecha no cargada/verificada desde disco.

**IMPORTANTE**

- No encontré hallazgos adicionales en esta categoría.

**MENOR**

- No encontré hallazgos en esta categoría.

**OBSERVACIÓN**

- `tests/test_t024.py:526`-`534` construye precisamente un `VintageLoad` sintético con manifiesto falso y `data_vintage_id` tipo `"v1"`. Eso hace que parte de la suite pase apoyándose en la misma brecha: valida el flujo decisorio sin exigir una cosecha real cargada/verificada.

No ejecuté `pytest` por la restricción indicada; sí hice revisión de diff y comprobaciones sueltas de import/petición con `.venv/bin/python3 -B`.

Codex session ID: 01a11079-7ec5-7d13-a1ed-c455d4ab34f7
Resume in Codex: codex resume 01a11079-7ec5-7d13-a1ed-c455d4ab34f7
