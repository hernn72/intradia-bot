# T-001 — CI en GitHub Actions (pytest, ruff, mypy)

Estado: ACEPTADA
Agente: Codex
Línea / fase: C-00 (línea C, ingeniería de producción)
Gate al que contribuye: GATE L0 (requisito 7), GATE PROD (requisito 1)

## Objetivo
Cada push y cada PR ejecutan `pytest -q`, `ruff check .` y `mypy advisor` en
GitHub, y `main` no puede recibir cambios que los rompan.

## Por qué existe
Hoy no existe `.github/` (verificado 2026-09-14). Ninguna release depende de
nada más que de que alguien recuerde ejecutar los tres comandos. Decisión D-11.

## Dependencias previas
Ninguna. Puede hacerse en paralelo con todo.

## Archivos probables
No asumir que sean exactos: verificar primero.
- `.github/workflows/ci.yml` (nuevo)
- `requirements-dev.txt` (ya instala ruff, mypy, types-*)
- `pyproject.toml` (config de pytest/ruff/mypy ya existente; no tocar)
- `README.md` sección «Desarrollo» (añadir el badge y la frase «CI obligatoria»)

## Invariantes que no pueden romperse
INV-06 (no se cambia código de cálculo), INV-13 (los tests que dependen de la
cosecha se saltan si `data/vintages/` no existe: ya lo hacen; comprobar que en
CI se saltan y no fallan).

## Implementación requerida
1. Workflow `ci.yml`, disparo `push` y `pull_request` sobre todas las ramas.
2. Job único `checks` en `ubuntu-latest`, matriz Python `3.12` y `3.13` (el
   portátil usa 3.12, la Pi 3.13; verificado en `pyproject.toml` y
   `docs/pendientes.md`).
3. Pasos: checkout, setup-python con cache de pip, `pip install -r
   requirements-dev.txt`, `ruff check .`, `mypy advisor`, `python -m pytest -q
   --durations=10`.
4. Sin red en tests: ya es así (`tests/conftest.py` usa `FakeProvider`). Añadir
   `env: YF_DISABLE=1` no es necesario; en cambio, añadir un paso que falle si
   algún test intenta abrir un socket **no** se pide en esta tarea (FOLLOW_UP
   si se considera).
5. Timeout del job: 20 minutos.
6. Generar en la ficha el bloque exacto de configuración de branch protection
   (required check: nombre del job) para que el propietario lo active (OA-02).

## Qué NO debe modificarse
Ningún fichero de `advisor/` ni `tests/`. Si un test falla en CI y no en local,
es un hallazgo (FOLLOW_UP o BLOCKER), no se arregla «ajustando» el test.

## Tests unitarios
No aplica: la tarea no añade código Python. Verificación = el workflow en verde.

## Tests de integración
`tests/test_systemd_deploy.py` y `tests/test_capacity_real_vintage.py` deben
aparecer como pasados o saltados en CI, nunca fallidos.

## Verificación contra datos reales
```bash
gh run list --limit 3
gh run view <id> --log | grep -E "passed|skipped|failed|Success: no issues"
```
Comprobar a mano: el número de tests pasados en CI coincide con local (398 en
`e53e385`) ± los saltados por falta de cosecha (3).

## Medición del impacto
- nº activos afectados: 0
- nº señales afectadas: 0
- cambio en resultados relevantes: ninguno; el impacto es que a partir de aquí
  toda rama tiene un resultado de CI visible.

## Criterio de aceptación
- Workflow en verde en las dos versiones de Python sobre la rama de la tarea.
- Duración total < 10 minutos.
- Bloque de branch protection escrito en el handoff.

## Criterio de rechazo
- Se ha excluido algún test para que pase.
- Se ha instalado una versión de dependencia distinta de `requirements*.txt`.

## Evidencia que debe quedar registrada
`evidence/<fecha>-T-001-ci/README.md` con el enlace al run, el número de
tests, la duración por versión de Python y el bloque de branch protection.

## Commit esperado
Rama `ci/github-actions`. Mensaje: `ci: pytest, ruff y mypy en cada push y PR`.

## Actualización documental requerida
`docs/roadmap.md`: fila C-00 → ACEPTADA con SHA. `README.md`: sección
Desarrollo. `docs/decision-log.md`: OA-02 pasa a «pendiente de activar».

## Handoff al siguiente agente
- Estado: ACEPTADA · Commit: `e5ed089` · Rama: `ci/github-actions` (pusheada a origin)
- Verificado: run https://github.com/hernn72/intradia-bot/actions/runs/34824959115 en verde
  en 3.12 y 3.13; 395 pasan + 3 saltados = 398 locales (comprobado a mano); duración 64 s / 82 s.
- Impacto medido: 0 activos / 0 señales.
- Invariantes ejercitadas: INV-13 (los tests de cosecha se saltan en CI, no fallan). No aplican: INV-06.
- Hallazgos: OBSERVATION: la sesión de Codex no puede escribir en `.git` (ver evidencia);
  commit y push los hizo Claude Code.
- Decisiones tomadas / pendientes: ninguna; OA-02 (branch protection) queda listo para activar.
- Qué queda de esta ficha: nada.
- Siguiente ficha y agente recomendado: T-002 (Codex → Opus). Mergear `ci/github-actions`
  junto con `fix/execution-data-quality` en OA-01.
- Trampas para el siguiente: Codex implementa y verifica, pero el commit/push lo hace otro.

Registro original de Codex (antes del commit):
ESTADO: BLOQUEADA

Resumen:
- Rama activa verificada: `ci/github-actions` en `e53e385`.
- Se creó localmente `.github/workflows/ci.yml` con `push` y `pull_request`,
  job `checks`, matriz Python `3.12`/`3.13`, cache de pip, timeout de 20
  minutos, instalación desde `requirements-dev.txt`, `ruff check .`,
  `mypy advisor` y `python -m pytest -q --durations=10`.
- No se pudo commitear ni pushear por bloqueo de permisos al crear
  `.git/index.lock`.
- Al no haber push, no existe run de GitHub Actions para verificar con
  `gh run list` / `gh run view`.

Verificación local:
- Antes (`evidence/2026-09-14-T-001-ci/antes.txt`): 398 passed, `ruff` ok,
  `mypy` ok.
- Después (`evidence/2026-09-14-T-001-ci/despues.txt`): 398 passed, `ruff` ok,
  `mypy` ok.
- Verificado a mano: el número de tests local antes y después coincide
  (398 = 398), sin cambios de comportamiento esperados porque la tarea solo
  añade CI.

Bloqueo:
```text
$ git add .github/workflows/ci.yml && git diff --cached --name-status && git commit -m "ci: pytest, ruff y mypy en cada push y PR"
fatal: Unable to create '/Users/fer/Desktop/Trading bot/intradia-bot/.git/index.lock': Operation not permitted
```

Archivos modificados por Codex:
- `.github/workflows/ci.yml` (nuevo, sin commitear por el bloqueo de git).
- Esta sección de handoff en `docs/tareas/T-001-ci-github-actions.md`
  (sin commitear).
- `evidence/2026-09-14-T-001-ci/README.md`, `antes.txt` y `despues.txt`
  (sin commitear).

Archivos no modificados por Codex:
- No se tocaron `README.md`, `docs/roadmap.md`, `docs/decision-log.md`,
  `advisor/` ni `tests/`.

Impacto:
- nº activos afectados: 0
- nº señales afectadas: 0
- cambio en resultados relevantes: ninguno; el cambio es solo de CI.

Invariantes:
- INV-06: no aplica; no se cambió código de cálculo ni investigación.
- INV-13: ejercitada indirectamente por la suite local completa; CI no pudo
  ejecutarse por falta de commit/push.

Hallazgos:
- BLOCKER: el entorno impide crear `.git/index.lock`, por lo que no se puede
  hacer `git add`, `git commit` ni `git push` desde esta sesión.

Branch protection para OA-02 (pendiente cuando se pueda completar T-001):
```text
Branch: main
Require status checks to pass before merging: enabled
Require branches to be up to date before merging: enabled
Required checks:
- checks (3.12)
- checks (3.13)
Restrict direct pushes: enabled
Restrict force pushes: enabled
```

Siguiente:
- Ejecutar el commit esperado cuando el entorno permita escribir `.git`:
  `ci: pytest, ruff y mypy en cada push y PR`.
- Pushear solo `ci/github-actions` a origin y verificar el run con
  `gh run list --branch ci/github-actions` y `gh run view <run-id>`.
