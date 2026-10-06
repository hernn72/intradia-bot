**BLOCKER**

- [deploy/t024/README.md](</Users/fer/Desktop/Trading bot/intradia-bot/deploy/t024/README.md:20>) / [README.md:47](</Users/fer/Desktop/Trading bot/intradia-bot/deploy/t024/README.md:47>): la preparación de la Pi crea el worktree en `1a697c3...`, pero `deploy/t024/*` se añade recién en `ee256e6`. Siguiendo el runbook, `sudo /home/fer/intradia-t024/deploy/t024/instalar.sh` no existe y la unidad tampoco podría ejecutar `deploy/t024/checkpoint.py`. El worktree operativo debe estar en `ee256e6` o descendiente, con `git diff 1a697c3 HEAD -- advisor config.yaml universe.yaml exchange_overrides.yaml pyproject.toml requirements.txt` vacío.

**IMPORTANTE**

- [deploy/t024/traer_cosecha.py](</Users/fer/Desktop/Trading bot/intradia-bot/deploy/t024/traer_cosecha.py:203>): los artefactos de la Pi se copian directamente al destino final, sin staging ni promoción atómica. Si `rsync` se corta o la verificación posterior falla, queda evidencia parcial/no verificada en `--destino-artefactos`, lista para confundirse con material bueno.

- [deploy/t024/traer_cosecha.py](</Users/fer/Desktop/Trading bot/intradia-bot/deploy/t024/traer_cosecha.py:67>): la verificación no comprueba igualdad byte a byte completa del árbol de artefactos; solo hashes listados en `SHA256SUMS` y el vintage. Además `estado.json` no entra en `SHA256SUMS` porque el wrapper genera hashes antes de escribirlo en [checkpoint.py:418](</Users/fer/Desktop/Trading bot/intradia-bot/deploy/t024/checkpoint.py:418>). Escenario: un destino con ficheros extra o `estado.json` alterado puede pasar y contaminar la evidencia versionada.

- [deploy/t024/checkpoint.py](</Users/fer/Desktop/Trading bot/intradia-bot/deploy/t024/checkpoint.py:240>): `_validar_peticion` no valida la petición exacta completa: faltan `interval`, `auto_adjust`, `actions`, `symbols`, `symbols_sha256` y `end_exclusive`. De hecho el test fake acepta `symbols=["A"] * 126` y `symbols_sha256="s"` en [tests/test_t024_deploy.py:85](</Users/fer/Desktop/Trading bot/intradia-bot/tests/test_t024_deploy.py:85>). El `congelar` real está protegido por `t024_forward`, pero el wrapper puede guardar y aceptar como “peticion.json” algo que no cumple el contrato completo.

**MENOR**

- [deploy/t024/instalar.sh](</Users/fer/Desktop/Trading bot/intradia-bot/deploy/t024/instalar.sh:52>): usa `-g "${T024_USER}"`. En una Pi normal `fer:fer` existe, pero no es garantizado; si el grupo primario no se llama igual que el usuario, la instalación falla aunque el usuario sea válido.

- [tests/test_t024_deploy.py](</Users/fer/Desktop/Trading bot/intradia-bot/tests/test_t024_deploy.py:268>): el test de “rutas prohibidas” solo escanea `checkpoint.py` y comandos observados. No detecta validación incompleta de petición ni contaminación por artefactos extra; pasa por razones demasiado superficiales.

**OBSERVACIÓN**

- No veo cambios en el ejecutor congelado: `git diff 1a697c3 HEAD -- advisor config.yaml universe.yaml exchange_overrides.yaml pyproject.toml requirements.txt` sale vacío. Eso mantiene viable `T024_CODE_SHA=1a697c3` si el worktree de la Pi está en `ee256e6` o descendiente limpio.

- No ejecuté `pytest`, como pediste/anticipaste; la revisión fue por lectura, `git diff` y contrastes puntuales en modo solo lectura.

Codex session ID: 01a110ba-07df-7f51-aa8e-5c9c7bd5c45d
Resume in Codex: codex resume 01a110ba-07df-7f51-aa8e-5c9c7bd5c45d
