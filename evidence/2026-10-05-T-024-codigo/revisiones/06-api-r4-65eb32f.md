# Revisión Codex (api-r4-65eb32f-FINAL) — informe literal

_Solo lectura, sin red y sin datos posteriores al 2026-08-27. Job `task-muvhqsd7-tjusq8`._

Veredicto explícito: **APTO dentro del modelo de amenaza declarado: 0 BLOCKER, 0 IMPORTANTE.**

No he encontrado una ruta estructural para obtener desenlaces de una cosecha sin pasar por `ejecutar_mirada` con identidad, registro forward, calendario, reconfirmación ciega, marca exclusiva y token activo.

**Comprobaciones clave**

- `TokenMirada`: exige token presente, igualdad con `_TOKEN_ACTIVO` y hash vigente de la marca en [t024_decision.py:183](/Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:183). El token se activa solo alrededor de `construir_resultado` y se revoca en `finally` en [t024_decision.py:911](/Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:911).
- Barras de cosecha: `barras_decision` exige token y marca `origen="cosecha:<id>"` en [t024_decision.py:690](/Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:690).
- Funciones puras de desenlace: `salida_p6`, `retornos_cierre`, `drift_noche_dia`, `construir_ventanas`, `calcular_ventana`, `recalcular_por_politica_activo`, D3/D4 y `decidir_politica` llaman la guarda de origen en [t024_decision.py:210](/Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:210), [t024_decision.py:253](/Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:253), [t024_decision.py:293](/Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:293), [t024_decision.py:337](/Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:337), [t024_decision.py:455](/Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:455), [t024_decision.py:474](/Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:474), [t024_decision.py:479](/Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:479) y [t024_decision.py:545](/Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:545).
- Identidad y cosecha: `ejecutar_mirada` valida identidad antes de nada, exige registro forward, ata `cosecha_decisiva.data_vintage_id` al id declarado, aplica regla 75 días y calendario antes de `capturar` y antes de crear marca en [t024_decision.py:878](/Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:878).
- Reconfirmación ciega: `capturar(..., desarrollo=False)` bloquea cutoff ficticio y cosecha consumida, y solo usa `VistaCiega.open_e()` para capacidad; no procesa salidas ni no solapamiento en [t024_captura.py:351](/Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_captura.py:351).
- Máximo dos miradas/regla 5/marca sin registro: solo se aceptan `mirada_1` y `mirada_final`; marca existente deniega; final con marca de mirada 1 pero sin estados deniega en [t024_decision.py:655](/Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:655).

**Observaciones**

- `T024_CODE_SHA` está en `None` en [t024_comun.py:11](/Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_comun.py:11), así que la decisión real falla cerrada ahora mismo por [t024_decision.py:567](/Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/t024_decision.py:567). No es vulnerabilidad; es bloqueo deliberado hasta fijar el commit de código.
- No pude ejecutar tests: `pytest` no está instalado (`python3 -m pytest` devuelve `No module named pytest`). Revisión hecha por lectura estática; no leí `data/frescura-snapshot.db`, no usé red y no calculé D1/D2 sobre datos reales.

