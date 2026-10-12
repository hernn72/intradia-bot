Veredicto final global sobre `adbd482`: **0 BLOCKER / 0 IMPORTANTE / 1 MENOR / 1 OBSERVACIÓN**.

**BLOCKER**
Vacío.

**IMPORTANTE**
Vacío.

**MENOR**
[deploy/t024/instalar.sh:115](/Users/fer/Desktop/Trading%20bot/intradia-bot/deploy/t024/instalar.sh:115) + [deploy/t024/systemd/intradia-t024-checkpoint.service:13](/Users/fer/Desktop/Trading%20bot/intradia-bot/deploy/t024/systemd/intradia-t024-checkpoint.service:13): el instalador valida que `T024_ARTEFACTOS_DIR`, la segunda copia y `T024_DATA_DIR` queden fuera del checkout/data-dir, pero no valida `T024_LOG`. Escenario: un `.env` accidentalmente pone `T024_LOG=/home/fer/intradia-t024/logs/systemd.log`; el instalador lo acepta, crea el directorio como `T024_USER`, y systemd append-escribe stdout/stderr dentro del worktree. No abre desenlaces ni cambia el contrato, pero sí permite escritura operativa fuera de artefactos y deja el worktree sucio.

**OBSERVACIÓN**
Confirmado: `T024_CODE_SHA=1a697c3fa2ab76ddfcf567c2ef3f5ab56492eaf0` sigue válido. El comando solicitado equivalente a `git diff --quiet 1a697c3 HEAD -- advisor config.yaml universe.yaml exchange_overrides.yaml pyproject.toml requirements.txt` devolvió `0`, y el sidecar coincide con el calendario.

No ejecuté pytest ni comandos de escritura. Solo lectura; los comandos `git` emitieron avisos de xcrun por el sandbox, pero devolvieron la información necesaria.

Codex session ID: 01a11190-7252-7a60-bb7d-0cf0aeca78df
Resume in Codex: codex resume 01a11190-7252-7a60-bb7d-0cf0aeca78df
