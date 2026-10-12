# Revisión final independiente de P6 / GATE P6 (solo lectura)

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

- **Fecha:** 2026-10-05, después de la ejecución única de P6 (`0771989`) y con D-70 y el cierre
  redactados, sin commitear.
- **Revisores:** Codex (independiente, solo lectura) y Claude (verificación propia sobre los mismos
  artefactos).
- **Mandato:** intentar demostrar que el cierre es incorrecto o que GATE P6 no puede cruzarse.
- **Restricciones respetadas:** no se ejecutó el simulador ni el CLI de P6 en ninguna fase, ni
  `run_confirmatory`, `_ejecutar_confirmatoria_sellada`, `simulate`, `build_real_market`,
  `build_real_signals` o `load_vintage`. No se modificó `evidence/2026-10-03-T-022-p6/run/` y P6 no se
  volvió a ejecutar. Lo único que se recalculó es aritmética sobre los CSV y el JSON publicados.

## Resultado

**0 BLOCKER · 0 IMPORTANTE · 0 MENOR.**

Una observación de Codex, sin impacto: `revision-final.md`, `hashes-evidencia.txt` y
`final-pytest-ruff-mypy.txt` no existían durante la revisión, como preveía el encargo; se escribieron
después.

## Verificación de Claude (reproducible con lecturas, git y aritmética sobre lo publicado)

| Comprobación | Resultado |
|---|---|
| `git diff --name-only 353876d 0771989` | 31 ficheros, todos en `evidence/2026-10-03-T-022-p6/run/` |
| Commits en `0771989..HEAD` que tocan `run/`, y cambios del árbol en `run/` | 0 y 0 |
| `shasum -a 256 -c SHA256SUMS-ejecucion.txt` | 30/30 OK; cubre los 30 ficheros de `run/` salvo sí mismo |
| sha256(marca) = `token_sha256`; `payload_sha256` de la marca = sha256(`apertura-payload.json`) | sí y sí |
| `p6-parada.json` | no existe |
| Consola | `código de salida: 0` (`consola-confirmatoria.txt`) |
| `P6_PREREG_SHA` ancestro de `353876d` | sí |
| `git diff bc0636d 353876d -- advisor config.yaml universe.yaml exchange_overrides.yaml pyproject.toml requirements.txt` | vacío |
| 7 `system_sha256`, 2 `benchmark_sha256` y la ventana del payload = `preflight/system-hashes.json` | sí |
| Criterio de §16 aplicado de nuevo a B2 y S2 primarias | `[True, True, True, True, False]` en las dos → `NO PASA`, igual a lo publicado |
| `excess_CAGR_pp` = (CAGR política − CAGR benchmark 5 pb) · 100 | B2 −15.767134262530824 y S2 −18.722782521718038, exactos |
| `supervivientes` | `[]` exacto |
| `etiquetas_decisorias` y `supervivientes` | se derivan solo de `*_primaria_5pb` (`advisor/research/p6.py`) |
| Conciliación de las 7 corridas de política (`check_ledger_flows` sobre los ledgers publicados) | el efectivo encadena; efectivo final = V_T = última serie diaria; V_T − V_0 = Σ pnl_neto_EUR = Σ bruto + dividendos − comisiones con \|Δ\| ≤ 1,2e-10 |
| Conciliación del benchmark (5 y 10 pb) | efectivo final = V_T, Δ = 0 |
| Orden cronológico de los 9 ledgers | `timestamp_utc` sin retrocesos y `seq` consecutivo |
| `ENTRY_REJECTED` = INSUFFICIENT_CASH + ABOVE_MAX_ENTRY + INVALID_STOP + INVALID_TARGET (B2) | 7 620 = 7 005 + 531 + 73 + 11 |
| Mapa de sector congelado | ningún `UNKNOWN` |
| `git diff --name-only 353876d HEAD -- advisor config.yaml deploy tests universe.yaml exchange_overrides.yaml` y árbol | vacío y sin cambios |
| `origin/main` | `dac50249d5d047ff27d36fc827954e7a4c850e81`, sin cambios |
| Pi (lectura por SSH, 2026-10-05) | `~/intradia-bot` en `8b2dddb` (v0.4.1), árbol limpio, sin `run/` de P6 |
| Filas R-01 y V-01 de `docs/roadmap.md` | sin cambios |
| Suite local al cerrar (`final-pytest-ruff-mypy.txt`) | ruff y mypy limpios; **1103 passed**, tras la corrección post-run de `tests/test_p6.py` (adenda) |

## Informe de Codex (literal)

**Veredicto**

No he encontrado ningún **BLOCKER**, **IMPORTANTE** ni **MENOR**. No pude demostrar que el cierre sea incorrecto ni que GATE P6 no pueda cruzarse.

Veredicto explícito: **ACEPTABLE: 0 BLOCKER / 0 IMPORTANTE. GATE P6 puede cruzarse con salida `[]`; P7/A-07 queda bloqueado por falta de supervivientes.**

**Hallazgos**

No hay hallazgos.

**Comprobaciones Clave**

Hecho: la ejecución publicada es única. Hay una sola marca `EJECUCION_CONFIRMATORIA_P6_INICIADA`, no existe `p6-parada.json`, la consola publica `código de salida: 0`, y la marca hashea `apertura-payload.json` con `7823fe8d…8a7e`; su SHA256 coincide con `token_sha256`. Ver [marca](</Users/fer/Desktop/Trading bot/intradia-bot/evidence/2026-10-03-T-022-p6/run/EJECUCION_CONFIRMATORIA_P6_INICIADA:1>) y [consola](</Users/fer/Desktop/Trading bot/intradia-bot/evidence/2026-10-03-T-022-p6/run/consola-confirmatoria.txt:1>).

Hecho: los hashes de integridad pasan. `shasum -a 256 -c SHA256SUMS-ejecucion.txt` devolvió OK para todos los ficheros listados; el manifiesto cubre todos los ficheros de `run/` salvo sí mismo.

Hecho: las identidades P6 cuadran. El payload contiene `P6_PREREG_SHA`, `P6_CODE_SHA`, `P6_RUN_HEAD_SHA` y `P6_DATA_ID`; `P6_PREREG_SHA` es ancestro de `353876d`; y `git diff bc0636d 353876d -- advisor config.yaml universe.yaml exchange_overrides.yaml pyproject.toml requirements.txt` salió vacío. Los hashes de sistema/benchmark del payload coinciden con `preflight/system-hashes.json`.

Hecho: el criterio decisorio está aplicado a las primarias. B2 y S2 cumplen `N_closed>=100`, `profit_factor_local>1`, `mean_R_local>0` y `max_drawdown>=-25%`, y fallan solo `excess_CAGR_pp>0`: B2 `-15.767134262530824`, S2 `-18.722782521718038`. Ver [resultado-p6.md](</Users/fer/Desktop/Trading bot/intradia-bot/evidence/2026-10-05-T-022-p6-cierre/resultado-p6.md:26>) y [D-70](</Users/fer/Desktop/Trading bot/intradia-bot/docs/decision-log.md:1841>). `etiquetas_decisorias` y `supervivientes` se derivan solo de `B2_primaria_5pb` y `S2_primaria_5pb` en [advisor/research/p6.py](</Users/fer/Desktop/Trading bot/intradia-bot/advisor/research/p6.py:1235>).

Hecho: la conciliación contable publicada cuadra desde CSV. Para las siete corridas de políticas, el cash encadena fila a fila, `V_T - V_0` coincide con `Σ pnl_neto_eur` con diferencias solo de redondeo flotante, y la última fila de serie diaria coincide con `equity_final`. El exceso CAGR recalculado desde JSON da exactamente B2 `-15.767134262530824` y S2 `-18.722782521718038`.

Hecho: los descriptivos no rescatan candidatos. `resultado-p6.md` dice que solo las dos primeras filas deciden y que C0, sensibilidad 10 pb y puente todas-las-barras son descriptivos, sin veto ni rescate; D-70 repite que no se retoca ninguna candidata. Ver [resultado-p6.md](</Users/fer/Desktop/Trading bot/intradia-bot/evidence/2026-10-05-T-022-p6-cierre/resultado-p6.md:63>) y [decision-log.md](</Users/fer/Desktop/Trading bot/intradia-bot/docs/decision-log.md:1827>).

Hecho: producción permanece intacta. `git diff 353876d HEAD -- advisor config.yaml deploy tests universe.yaml` salió vacío; `origin/main` resuelve a `dac50249d5d047ff27d36fc827954e7a4c850e81`.

Hecho: P7 no recibe política. `docs/gates.md` declara P7 bloqueado por ausencia de supervivientes, y `docs/roadmap.md` marca A-07 como bloqueado, no iniciado y sin candidata. Ver [gates.md](</Users/fer/Desktop/Trading bot/intradia-bot/docs/gates.md:312>) y [roadmap.md](</Users/fer/Desktop/Trading bot/intradia-bot/docs/roadmap.md:219>). R-01 y V-01 no cambian en el diff de roadmap y siguen bloqueados por GATE P7 en [roadmap.md](</Users/fer/Desktop/Trading bot/intradia-bot/docs/roadmap.md:242>).

Inferencia: GATE P6 puede cruzarse porque el propio gate exige medición completa y reproducible, no resultado favorable; la matriz final mapea los requisitos literales a evidencia publicada en [gate-p6-final.md](</Users/fer/Desktop/Trading bot/intradia-bot/evidence/2026-10-05-T-022-p6-cierre/gate-p6-final.md:19>) y el cierre lo formula igual en [gates.md](</Users/fer/Desktop/Trading bot/intradia-bot/docs/gates.md:270>).

**Observaciones**

`revision-final.md`, `hashes-evidencia.txt` y `final-pytest-ruff-mypy.txt` no existen todavía; lo trato como no hallazgo porque el mandato lo excluye expresamente. `README.md` los lista como ficheros esperados de cierre en [README.md](</Users/fer/Desktop/Trading bot/intradia-bot/evidence/2026-10-05-T-022-p6-cierre/README.md:56>).

Git emitió avisos de `xcrun_db` por el sandbox de solo lectura, pero los comandos devolvieron los códigos útiles esperados.

**Comandos Ejecutados**

- `pwd && git status --short --branch && git rev-parse HEAD && git rev-parse --abbrev-ref HEAD && git log --oneline -5`
- `rg --files ...`
- `git diff --name-only`
- `git diff --name-only 353876d 0771989`
- `git diff --name-only 353876d HEAD -- advisor config.yaml deploy tests universe.yaml`
- `cd evidence/2026-10-03-T-022-p6/run && shasum -a 256 -c SHA256SUMS-ejecucion.txt`
- Varios `python3 -B -c ...` para leer JSON, calcular SHA256, comparar manifiesto, recalcular métricas y conciliar CSV.
- `git log --oneline --name-only 0771989..HEAD -- evidence/2026-10-03-T-022-p6/run`
- `git status --short -- evidence/2026-10-03-T-022-p6/run`
- `git merge-base --is-ancestor ...`
- `git diff --exit-code bc0636d... 353876d... -- advisor config.yaml universe.yaml exchange_overrides.yaml pyproject.toml requirements.txt`
- `git diff --exit-code 353876d... HEAD -- advisor config.yaml deploy tests universe.yaml`
- `git rev-parse origin/main`
- `git diff -- docs/roadmap.md`
- `nl -ba ... | sed ...`
- `rg -n ...` acotados a docs/cierre/p6.py
- `head`/`tail` sobre CSV publicados
- `ls -la evidence/2026-10-05-T-022-p6-cierre`
- `test ! -e evidence/2026-10-03-T-022-p6/run/p6-parada.json`
- `find evidence/2026-10-03-T-022-p6/run -name EJECUCION_CONFIRMATORIA_P6_INICIADA -print | wc -l`

No ejecuté el simulador, `advisor.main p6`, `run_confirmatory`, `_ejecutar_confirmatoria_sellada`, `simulate`, `build_real_market`, `build_real_signals` ni `load_vintage`.

## Adenda (2026-10-05): corrección post-run de `tests/test_p6.py`

La primera pasada de la suite al cerrar dio 1101 passed y 1 failed: `test_preflight_real_sin_cargar_precios`
leía el `RUN_DIR` real y su control «marca confirmatoria ausente» veía la marca de la ejecución única.
Era una dependencia accidental del estado global. Con autorización del propietario:

- ese test usa un `RUN_DIR` temporal vacío (`monkeypatch.setattr(p6, "RUN_DIR", tmp_path / "run")`),
  sigue usando la cosecha real local y sigue prohibiendo `load_vintage` y `build_views`; la marca real no
  se borra, oculta, renombra ni monkeypatchea;
- `test_marca_en_run_dir_consume_p6`, nuevo, sin precios reales y con `tmp_path`: con la marca en
  `RUN_DIR`, el control de `guard_checks` pasa a `observado = True, ok = False` y `run_confirmatory` lanza
  `P6AlreadyExecutedError` sin escribir nada más.

No cambia `advisor/` ni la configuración (`tests/` no está en `EXECUTOR_PATHS`), así que
`P6_CODE_SHA = bc0636d` y `P6_RUN_HEAD_SHA = 353876d` no cambian. `run/` sigue íntegro (30/30 OK). Suite
final: **1103 passed**, ruff y mypy limpios. Los dos tests pasan en local.

### Revisión focalizada de Codex (literal)

**Veredicto**

0 BLOCKER y 0 IMPORTANTE observados. La corrección queda aceptable en revisión estática e integridad, con una salvedad: no pude ejecutar los dos tests por el sandbox de solo lectura, porque `pytest` no encontró ningún directorio temporal escribible antes de recolectar tests.

**Hallazgos**

OBSERVACIÓN: verificación dinámica no ejecutada por entorno, no por fallo del cambio.
Reproducción: `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_p6.py -k 'preflight_real_sin_cargar_precios or marca_en_run_dir_consume_p6'` falla antes de recolectar con `FileNotFoundError: No usable temporary directory found ...`. Esto impide confirmar en runtime los dos tests permitidos en este sandbox.

**Comprobaciones**

En /Users/fer/Desktop/Trading bot/intradia-bot/tests/test_p6.py:818, el test sigue saltando solo si falta `data/vintages/<P6_DATA_VINTAGE_ID>/AAPL.csv`. En tests/test_p6.py:825, siguen prohibidos `vintage.load_vintage` y `vintage.build_views` con el mismo `forbidden`.

Lo único nuevo aislado en `test_preflight_real_sin_cargar_precios` es `p6.RUN_DIR` hacia `tmp_path / "run"` en tests/test_p6.py:827. No observé monkeypatch de `RUN_MARKER` ni de la marca histórica en ese test.

`guard_checks` lee `RUN_DIR` en tiempo de llamada: usa `RUN_DIR / RUN_MARKER` dentro de la función en advisor/research/p6.py:752 y advisor/research/p6.py:767. Por tanto, el monkeypatch del global del módulo es efectivo para el preflight.

La guarda de P6 consumido sigue cubierta: el test nuevo escribe solo en `tmp_path / "run"` y comprueba `guard_checks` y `run_confirmatory` en tests/test_p6.py:841. También siguen presentes coberturas existentes en tests/test_p6.py:638, :1026, :1084 y :1108.

`git status --porcelain -- evidence/2026-10-03-T-022-p6/run` no devolvió entradas. `shasum -a 256 -c SHA256SUMS-ejecucion.txt` en esa carpeta devolvió todos los ficheros `OK`, incluida `EJECUCION_CONFIRMATORIA_P6_INICIADA`.

`git diff --name-only` lista solo `tests/test_p6.py`. `git diff bc0636d HEAD -- advisor config.yaml universe.yaml exchange_overrides.yaml pyproject.toml requirements.txt` no mostró diff. `EXECUTOR_PATHS` en advisor/research/p4.py:142 no incluye `tests/`. Inferencia: este cambio no altera el ejecutor ni el `P6_CODE_SHA` indicado.

**Comandos ejecutados**

- `git status --porcelain -- tests/test_p6.py evidence/2026-10-03-T-022-p6/run evidence/2026-10-05-T-022-p6-cierre advisor config.yaml universe.yaml exchange_overrides.yaml pyproject.toml requirements.txt`
- `git diff -- tests/test_p6.py`
- `rg -n "RUN_DIR|RUN_MARKER|guard_checks|def guard_checks|run_confirmatory|P6AlreadyExecutedError|EXECUTOR_PATHS|test_preflight_real_sin_cargar_precios|test_marca_en_run_dir_consume_p6|test_confirmatoria_rechaza_marca_existente|test_s13_marca_existente|test_s18|test_s19|test_s20" advisor tests/test_p6.py`
- `git diff --name-only`
- `sed -n ...` y `nl -ba ...` sobre `advisor/research/p6.py`, `advisor/research/p4.py` y `tests/test_p6.py`
- `git diff bc0636d HEAD -- advisor config.yaml universe.yaml exchange_overrides.yaml pyproject.toml requirements.txt`
- `git status --porcelain -- evidence/2026-10-03-T-022-p6/run`
- `shasum -a 256 -c SHA256SUMS-ejecucion.txt` (en evidence/2026-10-03-T-022-p6/run)
- `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_p6.py -k 'preflight_real_sin_cargar_precios or marca_en_run_dir_consume_p6'` (falló por falta de directorio temporal, ver observación)
- `git rev-parse --abbrev-ref HEAD`
- `git rev-parse --short=7 HEAD`
- `git status --porcelain -- evidence/2026-10-05-T-022-p6-cierre`

La observación de Codex queda cubierta fuera de su sandbox: los dos tests pasan en local (`2 passed`) y
dentro de la suite completa (1103 passed).
