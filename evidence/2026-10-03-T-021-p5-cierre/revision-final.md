# Revisión final independiente de P5 / GATE P5 (solo lectura)

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

- **Fecha:** 2026-10-03, después de la ejecución única de P5 y de D-67 (`7c9e875`).
- **Revisores:** Codex (independiente, solo lectura) y Claude (verificación propia sobre los mismos
  artefactos).
- **Mandato:** intentar demostrar que GATE P5 no puede cruzarse.
- **Restricciones respetadas:** no se ejecutó ningún research, no se recalculó nada desde la cosecha,
  no se modificó `evidence/2026-10-02-T-021-p5/run/` y no se volvió a ejecutar P5. Lo único que se
  regeneró son las configuraciones y los hashes deterministas de las políticas (`policy_payload`,
  `canonical_json`, `advisor_config_hash`), que no usan desenlaces.

## Resultado

**0 BLOCKER · 0 IMPORTANTE · 0 MENOR · 1 OBSERVACIÓN.**

- **OBSERVACIÓN (sin impacto).** `niveles` del preflight de `7446602` tiene 19 entradas: las 3
  ausencias estructurales de S2 llevan `levels_sha256: null`. Sin ellas, los 16 `levels_sha256`
  coinciden exactamente con los de la marca.

## Verificación de Claude (reproducible con lecturas y git)

| Comprobación | Resultado |
|---|---|
| `git diff --name-only 282b1ce 86ddd5b` | 12 ficheros, todos en `evidence/2026-10-02-T-021-p5/run/` |
| Commits en `86ddd5b..HEAD` que tocan `run/` | 0 |
| `git diff --name-only 6c7f913 282b1ce` | solo evidencia (preflight y revisión de look-ahead) |
| `SHA256SUMS-ejecucion.txt` | 11/11 OK |
| sha256(marca) = `token_sha256` = `f50d5ec9…f1c8c` | sí |
| 16 `levels_sha256` de la marca = preflight `7446602` = `p5-resultado.json` | sí |
| `condiciones_p4`, `p4_evidencia_sha256`, LOCRO y `grid_sha256` de la marca = preflight | sí |
| `policy_sha256_centros` de la marca = preflight = `politicas-finales.json` | sí (B2 y S2) |
| `policy_payload` → `canonical_json` → sha256 en `politicas-finales.json` | coinciden (B2 y S2) |
| `policy_sha256` publicado | solo C0 (control), B2 y S2; ningún vecino |
| Regla ACEPTABLE de D-66 aplicada de nuevo a `superficie.tsv` publicada | 13/13 ACEPTABLE, coherente con `clases.tsv` |
| `p5-parada.json` | no existe |
| Consola | `código de salida: 0` archivado literalmente (`consola-confirmatoria.txt`, línea 8) |
| `git diff 6c7f913 HEAD -- advisor config.yaml deploy tests` | vacío |

## Informe de Codex (literal)

**Veredicto:** no he encontrado base para bloquear GATE P5. Intenté tumbarlo por identidad, inmutabilidad, superficie, LOCRO, políticas, D-67 y producción; todo lo comprobado sostiene que puede cruzarse.

**Hallazgos**
- `BLOCKER`: ninguno.
- `IMPORTANTE`: ninguno.
- `MENOR`: ninguno.
- `OBSERVACIÓN`: el preflight de `7446602` contiene 19 entradas en `niveles` si se cuentan también las 3 ausencias estructurales S2 con `levels_sha256: null`; al filtrar esas ausencias, los 16 `levels_sha256` no estructurales coinciden exactamente con la marca. Reproducción: `git show 7446602:.../p5-preflight.json` + comparación contra [EJECUCION_CONFIRMATORIA_P5_INICIADA](</Users/fer/Desktop/Trading bot/intradia-bot/evidence/2026-10-02-T-021-p5/run/EJECUCION_CONFIRMATORIA_P5_INICIADA:30>). Sin impacto.

**Comprobaciones Clave**
- Identidad íntegra: marca única, `inicio_utc`, prereg/code/head, población, `signal_ids`, grid, semiplanos, LOCRO, P4, seed y recuento están en la marca [líneas 2-137](</Users/fer/Desktop/Trading bot/intradia-bot/evidence/2026-10-02-T-021-p5/run/EJECUCION_CONFIRMATORIA_P5_INICIADA:2>). `sha256(marca)` = `token_sha256` = `f50d5ec...`; `SHA256SUMS-ejecucion.txt` verifica todos los ficheros [líneas 1-11](</Users/fer/Desktop/Trading bot/intradia-bot/evidence/2026-10-02-T-021-p5/run/SHA256SUMS-ejecucion.txt:1>). Consola archiva literalmente `código de salida: 0` [línea 8](</Users/fer/Desktop/Trading bot/intradia-bot/evidence/2026-10-02-T-021-p5/run/consola-confirmatoria.txt:8>).
- Inmutabilidad limpia: `git diff --name-only 282b1ce 86ddd5b` solo lista `evidence/2026-10-02-T-021-p5/run/`; `git diff --name-only 86ddd5b..HEAD -- evidence/2026-10-02-T-021-p5/run` vacío; `git diff --name-only 6c7f913 HEAD -- advisor config.yaml deploy tests` vacío.
- Superficie/criterio: B2 8/8 y S2 5/5 `ACEPTABLE`; regla D-66 aplicada a los valores publicados no produce discrepancias. `criterio.tsv` da `centro_p4=True` y F1-F6 `False` en ambas, por tanto `ROBUSTA`, coherente con [resultado-p5.md líneas 31-57](</Users/fer/Desktop/Trading bot/intradia-bot/evidence/2026-10-03-T-021-p5-cierre/resultado-p5.md:31>).
- LOCRO: 6/6 filas estimables, IC inferior > 0 y mínimos 50718/59967/74969 respetados [líneas 89-100](</Users/fer/Desktop/Trading bot/intradia-bot/evidence/2026-10-03-T-021-p5-cierre/resultado-p5.md:89>).
- Políticas: JSON final contiene exactamente `B2` y `S2`; regeneré en memoria `policy_payload`, `canonical_json`, `advisor_config_hash` y `policy_sha256` con `.venv/bin/python` y coincide. Geometrías y laboratorio son los esperados [B2 líneas 7-41](</Users/fer/Desktop/Trading bot/intradia-bot/evidence/2026-10-03-T-021-p5-cierre/politicas-finales.json:7>), [S2 líneas 44-78](</Users/fer/Desktop/Trading bot/intradia-bot/evidence/2026-10-03-T-021-p5-cierre/politicas-finales.json:44>). Ningún vecino publica `policy_sha256`; solo `diagnostico_sha256` [líneas 5-24](</Users/fer/Desktop/Trading bot/intradia-bot/evidence/2026-10-02-T-021-p5/preflight/hashes-configuraciones.md:5>).
- D-67 coincide con artefactos: LOCRO, concentración, superficies, ausencias S2 y “no ordena B2 sobre S2” están correctamente recogidos [decision-log.md líneas 1497-1543](</Users/fer/Desktop/Trading bot/intradia-bot/docs/decision-log.md:1497>) y [resultado-p5.md líneas 79-121](</Users/fer/Desktop/Trading bot/intradia-bot/evidence/2026-10-03-T-021-p5-cierre/resultado-p5.md:79>).

**Matriz GATE P5**
Literal de [docs/gates.md](</Users/fer/Desktop/Trading bot/intradia-bot/docs/gates.md:232>):

| Requisito | Estado | Evidencia |
|---|---:|---|
| Superficies de parámetros publicadas | SATISFECHO | `superficie.tsv`, transcrita en `resultado-p5.md` |
| Configuraciones descartadas por fragilidad/dependencia listadas con motivo | SATISFECHO | No hay descartes FRÁGIL/DEPENDIENTE; ausencias S2 listadas por RR < 1,5 |
| Conjunto de políticas candidatas <= 5 | SATISFECHO | `[B2, S2]`, 2 políticas |
| Cada política con config completa y hash | SATISFECHO | `politicas-finales.json`, hashes regenerados y coincidentes |

No crucé comandos prohibidos, no recalculé desde cosecha y no edité nada.

