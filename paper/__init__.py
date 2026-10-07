"""T-025 — Shadow/Paper Trading Forward (S-01).

Paquete separado de ``advisor/`` por construcción (D-75, OD-T25-1): base propia ``paper.db`` con su
``application_id``, esquema y migraciones propios y comandos propios. Ningún comando de posiciones manuales
lee ``paper.db`` y nada de este paquete escribe en ``intradia.db``.

Pre-registro congelado: ``T025_PREREG_SHA = c6fdc421afb0c1fbba5780ae533e7d97681f4c06``
(``docs/tareas/T-025-shadow-paper-trading-forward.md``).

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._
"""

LABEL = "SHADOW / PAPER — estrategia en investigación, no validada para capital real"
T025_PREREG_SHA = "c6fdc421afb0c1fbba5780ae533e7d97681f4c06"
ENGINE_VERSION = "engine_v1"
