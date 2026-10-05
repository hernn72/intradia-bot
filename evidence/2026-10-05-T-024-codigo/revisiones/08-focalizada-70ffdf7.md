# Revisión Codex (focalizada-70ffdf7) — informe literal

_Solo lectura, sin red y sin datos posteriores al 2026-08-27. Job `task-muvi7r6i-j202nr`._

**Resultado**

BLOCKER: 0  
IMPORTANTE: 0  
MENOR: 0  
OBSERVACIÓN: 1

Veredicto: **APTA**. El diff `65eb32f..HEAD` cumple el mandato.

Confirmaciones:

- El diff solo toca [advisor/research/t024_decision.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:210) y [tests/test_t024.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/tests/test_t024.py:740).
- En `salida_p6`, el único cambio funcional es el booleano `truncada`: STOP/TARGET/TIME ahora devuelven `False`, incluso si ocurren en la última barra; `True` queda solo para `EXIT_FINAL` cuando `i == last`.
- No cambian motivos (`EXIT_STOP`, `EXIT_TARGET`, `EXIT_TIME`, `EXIT_FINAL`), precios de salida, índice `i`, acumulación de dividendos, ni guardas/token.
- `construir_ventanas` sigue propagando exactamente el `truncada` devuelto por `salida_p6` a `calcular_ventana`, sin abrir rutas nuevas de desenlace.
- El test añadido cubre el caso focal: stop en la última barra no truncado, final en la última barra sí truncado.

**Look-ahead / desenlaces**

No veo look-ahead introducido: el cambio no adelanta lecturas ni altera el orden de evaluación de la barra actual. Tampoco abre ninguna ruta pública nueva: `_exigir_token_si_cosecha(...)` queda intacta al inicio de `salida_p6`.

OBSERVACIÓN: no ejecuté tests porque el mandato era solo lectura y sin crear ficheros; `pytest` podría escribir cachés.

