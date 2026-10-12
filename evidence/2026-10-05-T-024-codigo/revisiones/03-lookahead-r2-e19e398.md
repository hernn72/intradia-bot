# Revisión Codex (lookahead-r2-e19e398) — informe literal

_Solo lectura, sin red y sin datos posteriores al 2026-08-27. Job `task-muvh5ujh-6tew3d`._

**Hallazgos**

MENOR: D3 no usa todo el universo regional analizable, solo activos que tuvieron alguna señal generada.
En [advisor/research/t024_decision.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:772), `symbols` se deriva de `{signal.asset for signal in signals}`; luego `_descriptivos_d3_d4` construye el índice regional únicamente con `barras_por_activo` en [advisor/research/t024_decision.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:699). Esto no afecta a la métrica primaria ni abre look-ahead, pero D3 queda distinto de la ficha, que pide índice equiponderado total return de los activos analizables de la región.  
Reproducción sintética: región USA con `AAA` y `BBB`, una ventana solo en `AAA`, y `BBB` con retorno fuerte en `[T0,T1]`; el D3 actual excluye `BBB`, por lo que el índice regional y `d3_region` cambian frente al contrato.

OBSERVACIÓN: no he podido ejecutar tests en este sandbox de solo lectura; incluso `git` falla al crear cachés temporales en `/tmp`, y `tests/test_t024.py` usa `tmp_path`. La revisión es estática.

**Verificación De Look-Ahead**

0 BLOCKER y 0 IMPORTANTE observados.

Las correcciones previas están verificadas: `construir_resultado` exige `TokenMirada` en [advisor/research/t024_decision.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:755), y `barras_decision` también queda detrás del token en [advisor/research/t024_decision.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:664). La captura queda ciega: `VistaCiega` solo expone historia hasta `s_i` y `open(e_i)` en [advisor/research/t024_captura.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_captura.py:68), y `capturar` trunca la cosecha a `c_e` antes de generar señales en [advisor/research/t024_captura.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_captura.py:371).

La ejecutabilidad replica P6: las comprobaciones con precio efectivo están en [advisor/research/t024_captura.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_captura.py:108), equivalentes a `p6_sim._process_entries`. La decisión vuelve a aplicar ejecutabilidad antes de abrir ventana en [advisor/research/t024_decision.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:302), y el no solapamiento por `(policy, asset)` se aplica solo en la ruta decisoria en [advisor/research/t024_decision.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:298).

Los desenlaces quedan acotados a la mirada: `c_e` filtra entradas, `t1_por_activo` trunca barras para salida final, y `T0(a)` es la primera sesión posterior al corte consumido. D2/D2o/φ se recalculan por política-activo en [advisor/research/t024_decision.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:378); D2c usa solo retornos previos a `s_i` en [advisor/research/t024_decision.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:342). La reconfirmación fallida de mirada 1 vuelve sin marca ni desenlaces en [advisor/research/t024_decision.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_decision.py:849).

**Veredicto**

APTO para el criterio pedido: 0 BLOCKER, 0 IMPORTANTE. No he demostrado look-ahead ni fuga decisoria en captura, reconfirmación o decisión. Solo queda el MENOR descriptivo de D3.

