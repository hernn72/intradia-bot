# T-007 acciones antes/despues

| Medida en salida real | Antes | Despues | Motivo |
|---|---:|---:|---|
| Fichas impresas con `COMPRAR` | 1 (`AMD`) | 1 (`AMD`) | `AMD` esta verificado en broker (`trade_republic: yes`) |
| Fichas impresas con `VERIFICAR_BROKER` | 0 | 0 | Los 2 `unknown` reales no alcanzaron setup operativo en esta pasada |
| Activos `BROKER_UNAVAILABLE` en radar | 1 (`9984.T`) | 0 | La accion de broker no disponible pasa a no operar |
| Activos `BROKER_UNAVAILABLE` en descartados | 0 | 1 (`9984.T`) | Nueva cadena de accion de broker |
| Etiquetas `Precio actual` en fichas | 1 | 0 | NASDAQ estaba `PRE_OPEN` |
| Etiquetas `Ultimo cierre` en fichas | 0 | 1 | NASDAQ estaba `PRE_OPEN` |
| Calidad OK / INCOMPLETO / DEGRADADO | 57 / 31 / 19 | 60 / 28 / 19 | Drift de datos reales entre pasadas: cripto actualizo barra durante la verificacion |

Universo real al ejecutar la tarea: 107 analizables; `trade_republic`: 95 `yes`, 10 `no`, 2 `unknown`.
