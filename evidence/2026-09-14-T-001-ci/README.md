# Evidencia T-001 — CI en GitHub Actions

Fecha: 2026-09-14
Rama: `ci/github-actions`
Commit base: `e53e385`
Estado final: ACEPTADA. Commit `e5ed089` (hecho por Claude Code tras el bloqueo de
permisos de la sesión de Codex), push a `origin/ci/github-actions`, run en verde.

## Qué se implementó localmente

Se creó `.github/workflows/ci.yml` con:

- `push` y `pull_request` en todas las ramas.
- Job único `checks` en `ubuntu-latest`.
- Matriz Python `3.12` y `3.13`.
- `timeout-minutes: 20`.
- `actions/checkout@v4`.
- `actions/setup-python@v5` con cache de pip y `requirements-dev.txt`.
- `python -m pip install -r requirements-dev.txt`.
- `ruff check .`.
- `mypy advisor`.
- `python -m pytest -q --durations=10`.

## Línea base antes

Comando:

```bash
{ date -u '+%Y-%m-%dT%H:%M:%SZ'; git rev-parse --short HEAD; source .venv/bin/activate && python -m pytest -q && ruff check . && mypy advisor; } > evidence/2026-09-14-T-001-ci/antes.txt 2>&1
```

Resultado en `antes.txt`:

```text
2026-09-14T08:45:47Z
e53e385
398 passed in 85.46s (0:01:25)
All checks passed!
Success: no issues found in 54 source files
```

## Verificación local después

Comando:

```bash
{ date -u '+%Y-%m-%dT%H:%M:%SZ'; git rev-parse --short HEAD; source .venv/bin/activate && python -m pytest -q && ruff check . && mypy advisor; } > evidence/2026-09-14-T-001-ci/despues.txt 2>&1
```

Resultado en `despues.txt`:

```text
2026-09-14T08:47:28Z
e53e385
398 passed in 88.58s (0:01:28)
All checks passed!
Success: no issues found in 54 source files
```

## Bloqueo en git

Comando ejecutado:

```bash
git add .github/workflows/ci.yml && git diff --cached --name-status && git commit -m "ci: pytest, ruff y mypy en cada push y PR"
```

Error literal:

```text
fatal: Unable to create '/Users/fer/Desktop/Trading bot/intradia-bot/.git/index.lock': Operation not permitted
```

Por este bloqueo no se pudo crear el commit, no se pudo hacer push a
`origin/ci/github-actions` y no hay ejecución de GitHub Actions para verificar
con `gh run list` / `gh run view`.

## Estado del workflow en GitHub

- Run id: 34824959115
- URL: https://github.com/hernn72/intradia-bot/actions/runs/34824959115
- Resultado: success en los dos jobs.
- Tests en CI: 395 pasan, 3 saltados (los que necesitan la cosecha `data/vintages/`, ausente en CI) = 398 locales. `ruff` «All checks passed!», `mypy` «no issues found in 54 source files».
- Duración por versión de Python: 3.12 → 64 s (08:52:47Z–08:53:51Z, pytest 28 s); 3.13 → 82 s (08:52:46Z–08:54:08Z, pytest 41 s).
- Comprobado a mano: 395 + 3 = 398, igual que `antes.txt` y `despues.txt`.

## Branch protection para OA-02

El workflow ya aparece en GitHub; el propietario puede activarlo (OA-02):

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

## Impacto

- Activos afectados: 0.
- Señales afectadas: 0.
- Resultados relevantes: ninguno; el cambio es solo de CI.

## Hallazgos

- OBSERVATION: la sesión de Codex no puede crear `.git/index.lock`
  («Operation not permitted»), así que Codex implementa y verifica pero no
  commitea ni pushea; el commit y el push los hace Claude Code o el
  propietario. Tenerlo en cuenta en las fichas siguientes.
