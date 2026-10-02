# Revisión independiente de look-ahead del ejecutor de P4 (T-020, paso 3)

> Revisión realizada antes de la ejecución confirmatoria de P4 y archivada posteriormente durante el
> cierre. No estaba versionada en el momento de la ejecución.

**Procedencia.**
- **Quién:** un agente `revisor` (Claude), distinto de quien programó el ejecutor y de la revisión
  anterior del paso 2. La lanzó la sesión de implementación el 2026-10-02, con el checklist cerrado
  del propietario, en solo lectura y con la ejecución confirmatoria prohibida.
- **Sobre qué:** HEAD `c2c52b1` (ejecutor `3df8230`).
- **Cuándo terminó:** antes de las 05:37:50 UTC, hora en que se lanzó la ejecución confirmatoria
  única con la autorización condicional del propietario («si el resultado es limpio queda
  autorizado…»).
- **El texto:** se copia **literalmente** el informe que el agente devolvió a la sesión. Se conservó
  íntegro en la conversación de esa sesión y no se ha reconstruido ni editado; solo se ha quitado la
  sangría que añade el mecanismo de entrega.
- **Evidencia contemporánea que la acompaña:**
  - el mensaje del commit `cfa365d` («revisión de look-ahead LIMPIA»);
  - la marca `run/EJECUCION_CONFIRMATORIA_P4_INICIADA`, con `p4_executor_sha_preflight = 3df8230` y
    `head_sha = c2c52b1`;
  - `git diff 3df8230 c2c52b1`, que solo toca evidencia de preflight.

---

RESULTADO: APROBADO (veredicto global: LIMPIA)

No encontré ninguna ruta por la que el ejecutor lea desenlaces antes de la marca, ni ninguna que cambie geometrías, población, semilla o familia, o que recalcule niveles después de la marca. No hay BLOCKER ni IMPORTANTE. Hay un hallazgo MENOR y varias observaciones.

**No ejecuté nada prohibido.** No lancé `p4 --fase confirmatoria`. Tampoco llamé a `run_confirmatory`, `execute_with_outcomes`, `evaluate_frozen`, `analyze_variant` ni `analyze_e1` sobre la cosecha real, ni a `comparacion-pareada`. No miré ningún net_R, ΔR, PF ni intervalo. No modifiqué ficheros y `evidence/2026-10-01-T-020-p4/run/` sigue sin existir (`ls` solo muestra `preflight`; `git status` solo muestra `graphify-out/` y `ultima_cerrada`, que ya estaban).

## Comprobaciones ejecutadas
- `.venv/bin/python -m pytest -q tests/test_p4.py`: 50 pasan. Aviso: este fichero incluye `test_regresion_backtest_v1`, que lanza el backtest v1 sobre la cosecha real. Es el backtest de producción, no las geometrías de P4, y su salida no la miré.
- ruff sobre p4.py, event_study.py, main.py y test_p4.py: sin errores. mypy sobre p4.py y event_study.py: sin errores.
- Preflight en desarrollo (`INTRADIA_P4_PREFLIGHT_DESARROLLO=1 … p4 --fase preflight`): 54/54 controles, ok=True. Comparado con el `p4-preflight.txt` guardado, solo cambian P4_EXECUTOR_SHA (c2c52b1 frente a 3df8230) y definitivo (False frente a True).
- Una llamada a `p4._preflight(..., development=True)` desde Python, con `evaluate_managed_event`, `evaluate_potential_event`, `event_economics`, `classify_target_stop_bar`, `execute_with_outcomes`, `simulate_e1_open_entry`, `evaluate_frozen` y los bootstraps sustituidos por funciones que lanzan excepción. Ninguna se disparó. La huella normalizada coincide con el JSON guardado (True True).
- `git diff --quiet 3df8230 HEAD -- <EXECUTOR_PATHS>`: sin cambios. El JSON guardado tiene ok=True, definitivo=True, executor=3df8230, git_dirty=False, outcomes_read=False y las cinco claves de niveles_sha256.

## Checklist
**1. El preflight no lee desenlaces: OK.**
- El único precio posterior a t que lee el preflight es la apertura de t+1, en `p4.py:533` (`_next_open`), que usan `entry_slack` y `classify_open_entry`.
- `_regime` (`p4.py:554-555`) solo usa la marca temporal del índice t+1, no precios.
- El contexto PIT se resuelve en `analysis_timestamp`.
- Los indicadores de `build_snapshot_series` son causales: rolling hacia atrás, `shift(1)` y expanding.
- Los evaluadores solo aparecen en `simulate_e1_open_entry` (`p4.py:955`) y en `evaluate_frozen` (`p4.py:2021-2022`), y a ambos solo se llega desde `execute_with_outcomes`, que solo invoca `run_confirmatory:1964`, después de la marca.

**2. Cambios en `event_study.py`: OK.**
- `run_event_study_on_vintage` (líneas 256-267) consume el generador `_iter_event_observations`. Las salidas por señal se siguen añadiendo en el mismo orden que antes, porque el generador queda suspendido en el `yield`. `evaluated_assets` se añade igual al terminar cada activo. `warmup` y `max_hold` valen lo mismo.
- `enumerate_event_signals_on_vintage` (278-303) no llama a ningún evaluador.
- Diferencia irrelevante: `replay_managed_population` ahora lanza el ValueError después de recorrer todas las señales, no en la primera sin niveles. El mensaje es idéntico (`missing[0]`). Su único llamante, `uncertainty.py:161`, no lo captura.

**3. La confirmatoria no puede cambiar el experimento: OK, con la salvedad MENOR de abajo.**
- a) Geometrías: constantes en `p4.py:206-219`.
- b) Población: la congela `FrozenRun` (`p4.py:1895`), cuyo hash se compara con el guardado (`p4.py:1953`).
- c) Semilla: `SEED` constante (`p4.py:81`).
- d) Familia: constante y comprobada (`p4.py:1736-1737`).
- e) Niveles: `execute_with_outcomes` usa los congelados y vuelve a comprobar `levels_sha256` (`p4.py:2042-2044`).
- CLI: solo existe `--fase` (`main.py:1180`).
- Variable de desarrollo: solo se lee en la rama de preflight (`main.py:750`). `run_confirmatory` llama a `_preflight` con `development=False`.
- Ruta de salida: fija y comprobada con `resolve()` (`p4.py:1933`).
- Preflight guardado: de él solo se usa el SHA del ejecutor, para el `git diff`. Todo lo demás se recalcula y debe coincidir con la huella.
- `--config` global: `EXPECTED_CONFIG_HASH` lo bloquea vía `tree_checks` (`p4.py:1680`), con la excepción descrita en el hallazgo MENOR.

**4. Marca y guardas de arranque: OK.**
- La marca se escribe en `p4.py:1958-1961`, antes de `execute_with_outcomes` (1964).
- `marker_payload` (1977-1995) incluye el SHA del ejecutor del preflight, el SHA de HEAD, `P4_PREREG_SHA`, los hashes de población y de signal_ids, niveles_sha256, los cortes de terciles, la familia y la semilla.
- La confirmatoria se niega si:
  - ya existe la marca (1936);
  - la salida no está vacía (1942);
  - el árbol está sucio o no se puede comprobar (1938). `tree_dirty` cubre ficheros con seguimiento modificados en todo el repo y ficheros sin seguimiento dentro de EXECUTOR_PATHS (1641-1653);
  - el ejecutor cambió desde el preflight definitivo (1947);
  - el preflight interno no coincide con el guardado, niveles_sha256 incluido (1953).
- El preflight definitivo no se reescribe si la marca ya existe (1843).

**5. Tests: cubren 1-4, con algunos puntos flojos (sin efecto en la corrección).**
- No son vacuos:
  - `test_preflight_real_…` y `test_preflight_no_lee_desenlaces`: recorren el preflight real con los evaluadores prohibidos.
  - `test_marca_confirmatoria_antes_de_abrir_desenlaces`: un espía comprueba que la marca existe antes de abrir desenlaces y revisa su contenido.
  - `test_tras_la_marca_no_se_reconstruye…`: prohíbe reconstruir la población y recalcular niveles después de la marca.
  - `test_un_ejecutor_sin_seguimiento_ensucia_el_arbol`: usa un repo git real.
  - `test_segunda_confirmatoria_se_niega_y_ruta_fija` y `test_enumeracion_sin_evaluadores_equivale_al_event_study`.
- Puntos flojos (OBSERVACIÓN):
  - `test_la_confirmatoria_no_admite_parametros…` (`tests/test_p4.py:1229-1236`) es casi vacuo: solo busca el texto `"SEED ="` en el código fuente.
  - El test de huella distinta (1002-1019) solo varía `poblacion`; ninguno varía solo `niveles_sha256` en `run_confirmatory`. El camino es la misma igualdad de dicts, que verifiqué a mano.
  - `OUTCOME_PATHS` (tests:67-84) prohíbe funciones, no lecturas directas de High/Low/Close. Esto queda cubierto por la revisión del código, no por el test.

## Hallazgos

[MENOR] `--config` puede cambiar `universe_path` sin alterar `EXPECTED_CONFIG_HASH`

Ubicación: `advisor/run/manifest.py:39` (`_CONFIG_HASH_EXCLUDED_KEYS = ("db_path", "universe_path")`), `advisor/main.py:1261-1262`, `advisor/research/p4.py:1805-1817` y `p4.py:1977-1995`

Escenario de fallo: se ejecuta `python -m advisor.main --config /fuera/c.yaml p4 --fase confirmatoria`, con un c.yaml idéntico al del repo salvo `universe_path: /fuera/u.yaml`. Los dos ficheros están fuera del repo, así que `tree_dirty` no los ve, y config_hash no cambia.

Resultado incorrecto: el universo se valida solo con `universe_vintage_id`. Su contenido (`advisor/universe/vintage.py:30-47`) no incluye `timezone`, y la zona horaria decide `session_dates_by_asset`, es decir, la espina de sesiones y la asignación de cada señal a un bloque. La asignación por señal (bloques 40/60/80/120, spine_session y régimen) no entra en la huella ni en la marca; solo se fijan resúmenes (1302 sesiones, bloques ocupados, bloque más corto, recuentos de régimen).

Causa: config_hash excluye a propósito las rutas, y la huella fija agregados en lugar de la asignación de cada señal.

Evidencia: código citado. No lo he reproducido, y en la práctica los controles agregados casi con seguridad detectarían un cambio real de zona horaria, por eso es MENOR. Exige además una acción deliberada fuera del repo.

Corrección recomendada (cualquiera de las dos, local):
- en la confirmatoria, exigir que `Path(config.universe_path).resolve()` sea el `universe.yaml` del repo y que `--config` sea el `config.yaml` del repo; o
- añadir a la huella y a la marca un `asignacion_sha256` sobre (signal_id, bloques por longitud, spine_session, región, régimen).

## Observaciones (no son defectos)
- **La marca solo protege esta copia del repo.** Es un fichero en disco: un clon o worktree distinto, o borrar `run/` antes de hacer commit, permitiría una segunda ejecución sin rastro. Conviene hacer commit de `run/` justo después de ejecutar.
- **Una excepción después de la marca la deja sin `p4-parada.json`.** P4 quedaría bloqueado sin salida. Es coherente con "una sola vez", pero conviene saberlo antes de lanzar.
- **El estado actual es apto para la ejecución.** HEAD c2c52b1 no cambia nada de EXECUTOR_PATHS respecto a 3df8230, y el preflight interno reproduce la huella guardada.

## Limitaciones
- No ejecuté la suite completa: podría contener comparaciones pareadas sobre la cosecha real.
- No revisé a fondo `evaluate_managed_event` ni el bootstrap: son anteriores a este cambio y quedan fuera del checklist de look-ahead.

Ficheros examinados (todos bajo /Users/fer/Desktop/Trading bot/intradia-bot/):
- `advisor/research/p4.py`
- `advisor/research/event_study.py`
- `advisor/main.py`
- `advisor/run/git.py`
- `advisor/run/manifest.py`
- `advisor/universe/vintage.py`
- `advisor/research/vintage.py`
- `advisor/research/capacity.py`
- `tests/test_p4.py`
- `evidence/2026-10-01-T-020-p4/preflight/p4-preflight.json`

---

## Qué se hizo con el MENOR y las observaciones (nota del cierre, no forma parte del informe)
- **MENOR (`--config` externo):** no se corrigió, para no cambiar el ejecutor ya revisado. La
  ejecución se lanzó **sin** `--config`, con el `config.yaml` y el `universe.yaml` del repo
  (`universe_path: "universe.yaml"`), así que el escenario no se dio.
- **Observación 1:** `run/` se commiteó justo después de ejecutar (`cfa365d`).
- **Observación 2:** no se produjo ninguna excepción. La ejecución terminó por la ruta normal, sin
  `p4-parada.json`.
