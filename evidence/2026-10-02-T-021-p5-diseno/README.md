# T-021 (A-05 / P5) — evidencia de la fase de diseño y pre-registro

_condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)_

**P5 no se ha ejecutado.** Ningún fichero de este directorio contiene un desenlace (`net_R`, ΔR, PF,
expectancy ni intervalo) de ningún punto de ninguna superficie.

| Fichero | Qué es |
|---|---|
| `inventario_rejilla_p5.py` | Inventario estructural de la rejilla. Enumera la población de P4 con `p4.build_population` y recalcula solo niveles desde las primitivas en t. Los tres evaluadores de desenlace se sustituyen, antes de importar el resto, por funciones que lanzan un error |
| `inventario-estructural.json` | Salida del script (`outcomes_read: false`). Reproduce 101.251 señales y `population_sha256 = 78024050…` |
| `codex-encargo-diseno.md` | Encargo literal a Codex (solo lectura) para refutar el diseño antes de redactar la ficha |
| `codex-revision-diseno.md` | Respuesta literal de Codex: 1 BLOCKER, 6 IMPORTANTE, 1 MENOR y 1 OBSERVACIÓN. La respuesta a cada hallazgo está en la ficha, sección «Revisión de la ficha» |
| `codex-encargo-ficha.md` | Encargo literal a Codex para revisar la ficha (`3e597db`) contra el código |
| `codex-revision-ficha.md` | Respuesta literal de Codex sobre la ficha: 1 BLOCKER, 3 IMPORTANTE, 1 MENOR y 2 OBSERVACIÓN |
| `revision-independiente-ficha.md` | Informe literal del revisor independiente (primera vuelta, `3e597db`): 1 BLOCKER, 1 IMPORTANTE, 5 MENOR y 2 OBSERVACIÓN |

Reproducir, desde la raíz del repositorio y con la cosecha `071ddb2b…` en `data/vintages/`:

```
PYTHONPATH=. .venv/bin/python evidence/2026-10-02-T-021-p5-diseno/inventario_rejilla_p5.py \
    > /tmp/inventario-estructural.json
```

Escribir la salida fuera del árbol y compararla después, para no ensuciar la evidencia versionada.

sha256:
- `inventario_rejilla_p5.py`: `db62c443496b56a8848731401e4f7756e8e6c29a5972ca73a7a2ab851d2c0eb6`
- `inventario-estructural.json`: `c49598011e39685fc3d0239dd12b13d835c9ee045c5586fc892a0a20145da0e2`
