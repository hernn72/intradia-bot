Veredicto final global sobre `b718917..155b66a` / PR #46: **0 BLOCKER / 1 IMPORTANTE / 1 MENOR / observaciones abajo**.

**BLOCKER**
Vacía.

**IMPORTANTE**
[deploy/t024/instalar.sh](/Users/fer/Desktop/Trading%20bot/intradia-bot/deploy/t024/instalar.sh:25): el instalador solo exige que `T024_ARTEFACTOS_DIR`, `T024_DATA_DIR` y `T024_LOG` existan como variables, y luego crea directorios/logs sin validar que los artefactos queden fuera del checkout ni que la segunda copia por defecto sea viable.

Escenario concreto: si `/etc/intradia-bot/t024.env` pone `T024_ARTEFACTOS_DIR=/home/fer/intradia-t024/art` o un symlink que resuelve dentro del worktree dedicado, `instalar.sh` lo acepta. La unidad se instala sin `--copia-dir` ([service](/Users/fer/Desktop/Trading%20bot/intradia-bot/deploy/t024/systemd/intradia-t024-checkpoint.service:15)), así que el wrapper usa por defecto `<artefactos>/copias/vintages` ([checkpoint.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/deploy/t024/checkpoint.py:97)). La congelación ya se habrá hecho cuando `segunda_copia()` detecte que esa copia cae dentro del repo y pase a `ERROR_COPIA` ([checkpoint.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/deploy/t024/checkpoint.py:545)). Resultado: se gasta el único intento automático, se escriben artefactos dentro del checkout y no queda la segunda copia verificada fuera del checkout. No abre desenlaces, pero sí rompe la garantía operacional de Fase A.

**MENOR**
[deploy/t024/README.md](/Users/fer/Desktop/Trading%20bot/intradia-bot/deploy/t024/README.md:72): la tabla de códigos de salida omite el código `10` (`RC_COPIA` / `ERROR_COPIA`), aunque el texto posterior sí menciona “salida 10”. Es un desajuste documental para operación/alertas, no de ejecución.

**OBSERVACIÓN**
La corrección de `155b66a` cubre los dos hallazgos previos: `verificar` fija `SIMBOLOS_FORWARD_SHA256` y exige lista ordenada/única; un checkpoint pasado sin `estado.json` queda `PERDIDO` sin `intento.json` o `INTERRUMPIDO` con `intento.json`, también en `estado`.

Verifiqué además que `git diff 1a697c3 HEAD -- advisor config.yaml universe.yaml exchange_overrides.yaml pyproject.toml requirements.txt` no lista cambios. No ejecuté `pytest` ni comandos que escriban en el repo.

Codex session ID: 01a11186-c551-7031-bee4-26abe767c2a6
Resume in Codex: codex resume 01a11186-c551-7031-bee4-26abe767c2a6
