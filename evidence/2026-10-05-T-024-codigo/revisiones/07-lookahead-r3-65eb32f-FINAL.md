# Revisión Codex (lookahead-r3-65eb32f-FINAL) — informe literal

_Solo lectura, sin red y sin datos posteriores al 2026-08-27. Job `task-muvi2cbs-3f1avu`._

**Hallazgos**

MENOR: [advisor/research/t024_decision.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:210) marca `truncada_t1=True` para cualquier salida que caiga en la última barra disponible, no solo para una posición aún abierta cerrada por regla final. El valor se propaga en [línea 327](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:327) y se agrega como `ventanas_truncadas_t1` en [línea 841](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:841).  
Reproducción sintética: una señal con `e_index=1` y `T1` en índice `2`, donde la barra `2` abre por debajo del stop, devuelve `EXIT_STOP` pero también `truncada=True`. No es fuga ni afecta D2/decisión; es un conteo descriptivo sobreincluyente. Los tests actuales validan razón/precio de salida, pero no el booleano `truncada`.

**Sin BLOCKER / Sin IMPORTANTE**

No encuentro look-ahead ni fuga decisoria en la versión actual:

- Generación de señales T024 replica P6: `build_snapshot_series`, `_signal`, contexto PIT y filtros OPERAR/COMPRAR siguen el patrón de P6 en [t024_captura.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_captura.py:232) frente a [p6.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/p6.py:644).
- Captura y reconfirmación no procesan salidas ni no solapamiento; cuentan capacidad con apertura `e_i` y `VistaCiega` bloquea `high/low/close` de `e_i` y todo futuro en [t024_captura.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_captura.py:68).
- La decisión exige reconfirmación antes de crear marca/token; si falla mirada 1 devuelve `REPROPONER` sin abrir desenlaces en [t024_decision.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:886).
- Las funciones de desenlace con barras de cosecha exigen token activo por `origen` en [t024_decision.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:192).
- D2/D2o/D2c, `phi`, D3 y D4 están acotados a `T0/T1` y/o a historia previa según ficha; D3 ya incluye todos los analizables del censo disponibles en cosecha decisiva en [t024_decision.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:803).
- La cosecha decisiva está atada por `data_vintage_id`, registro forward, checkpoint y regla de 75 días en [t024_decision.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:587) y [línea 880](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:880).

No ejecuté tests por el mandato de solo lectura y el sandbox sin escritura; inspeccioné el código y los tests. Tampoco leí `data/frescura-snapshot.db`, no usé red y no calculé D1/D2 ni salidas sobre datos reales.

**Veredicto:** APTA para look-ahead: 0 BLOCKER, 0 IMPORTANTE. Queda 1 MENOR descriptivo.

