# T-019 paso 4 — resultado de P3, calibración e impacto de Score v2 (2026-10-01)

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

Paso autorizado por el propietario. Es documentación y evidencia: no toca `advisor/`, `tests/`,
`config.yaml` ni `deploy/`. **P3 no se repitió**: sus resultados se leen de los artefactos
inmutables de `evidence/2026-09-30-T-019-paso3-p3/` (PR #33), cuyos hashes se verifican aquí.
Decisión registrada: **D-61**. **GATE P3 no se declara cruzado**: eso queda para el paso 5, tras la
revisión independiente final del look-ahead, que tampoco se lanzó en este paso.

## Identidad

| | |
|---|---|
| Base | `main` = `9089bc386319c0e94a0dcd94cb7c36f717f38177` |
| Pre-registro de P3 (2a-doc) | `8b2dddb8fd66423d9550df496d1a2a85abd066b6` |
| Pre-registro condicionado (PR #26) | ficha T-019, paso 0 |
| `P3_EXECUTOR_SHA` | `87309da148772f834fd49c3f2357692e48ed9273` |
| `data_vintage_id` | `071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841` |
| `universe_vintage_id` | `237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19` |
| `config_hash` | `89406d28c7b4b6e6c4f032cd63b6868c927af3e926dfb52d430dfa6654d06387` (`"1.0"`, 70/60, `calibrated: false`) |

## Comandos

```text
.venv/bin/python evidence/2026-10-01-T-019-score-v2/paso4_generar.py      # impacto, H-6, SAP.DE, Δ de bloque, resultado-p3, hashes
.venv/bin/python evidence/2026-10-01-T-019-score-v2/confianza_produccion.py   # confianza: cosecha + pasada local de producción (necesita red)
```

`impacto.py` es un atajo que llama a `paso4_generar.main`. Ningún script ejecuta P3. Los
evaluadores de desenlace (`evaluate_managed_event` y `evaluate_potential_event`) están parcheados a
`None` en toda reconstrucción, y la población sale de `build_population(..., with_outcomes=False)`,
que es el camino del preflight, comprobada por tamaño y hash (swing 94.094, `4aa12d85…`; medio
89.333, `4d6eaab9…`). El único contacto con desenlaces es la **lectura** de medias agregadas ya
publicadas en las tablas congeladas de #33, para `resultado-p3.md` y el Δ de bloque.

## Ficheros

| Fichero | Contenido |
|---|---|
| `resultado-p3.md` | Resultado de P3 generado desde `p3-resultado.json` y las TSV congeladas, con hashes verificados |
| `impacto.md`, `tablas/` | Impacto v1 → v2 con contexto PIT en las cuatro escalas, para swing y medio (medio marcado inválido) |
| `contexto-h6.md` | Contexto imputado (0) frente a excluido, y hueco de STOXX aparte |
| `confianza.md` | Confianza de D-46: cosecha del paso 2 y pasada local de producción |
| `calculo-manual-sap.md` | Señal SAP.DE recalculada a mano, con su quintil según los cortes congelados |
| `calculo-manual-delta-bloque.md` | Δ del bloque 3 a mano, y los 19 bloques frente al contraste |
| `gate-p3-matriz.md` | Matriz provisional de GATE P3 (requisito 5 pendiente del paso 5) |
| `hashes-de-tablas.txt` | Verificación de los hashes de #33 y sha256 de todo lo producido aquí |
| `final-pytest-ruff-mypy.txt` | Salida literal de la suite |

## Resultado (D-61)

- **Swing:** Δ Q5−Q1 −0,2895 R, IC95 [−0,4098, −0,1658], anchura 0,2440, 19 bloques → **NO
  CONCLUYENTE**, porque 0,2440 > 0,20. El signo negativo se publica como descriptivo y no cambia
  el veredicto. Los cinco candidatos fallan OPERAR, así que el horizonte queda **`calibrated:
  false`**, con `min_score_operar` y `min_score_vigilar` nulos.
- **Medio:** «NO CONCLUYENTE — inválido (bloque parcial 102 ≤ 250)», `calibrated: false`.
- **Intradía:** sin laboratorio, `calibrated: false`.
- **Producción:** sin cambios. Sigue Score v1 con 70/60 (D-47) y v2 no se activa.
- **Clasificación operativa:** no aplica, porque Score v2 no dispone de umbrales calibrados.

## Cómo se hizo

Codex programó `paso4_generar.py` en dos vueltas y revisó la documentación sin encontrar ningún
BLOCKER ni ningún IMPORTANTE; su único MENOR ya está resuelto. Claude supervisó, escribió D-61, los
documentos y `confianza_produccion.py`, y reprodujo de forma independiente:
- la media de los 19 Δ de bloque, −0,289467854516;
- la cuenta de SAP.DE;
- los cortes y el `n` por quintil de v2 frente a P3.

La pasada de confianza la ejecutó Claude porque el sandbox de Codex no resuelve DNS. Una
regeneración completa de `paso4_generar.py` reprodujo todas las salidas byte a byte.
