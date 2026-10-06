**BLOCKER**

No encontré BLOCKER.

**IMPORTANTE**

1. [checkpoint.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/deploy/t024/checkpoint.py:373) no fija en runtime el `T024_CODE_SHA=1a697c3...`; solo exige que `verificar_identidad()` imprima “algún” SHA de 40 hex. El instalador sí compara contra `1a697c3...` una vez ([instalar.sh](/Users/fer/Desktop/Trading%20bot/intradia-bot/deploy/t024/instalar.sh:59)), pero el timer no. Escenario: después de instalar, el worktree limpio se actualiza a un commit que solo cambia el sidecar `T024_CODE_SHA.txt` fuera de `EXECUTOR_PATHS`; `verificar_identidad()` acepta ese SHA si es ancestro y el diff protegido está limpio ([p4.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/p4.py:1667)), y `congelar` lo mete en el manifiesto ([t024_forward.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/advisor/research/t024_forward.py:807)). Resultado: la Pi puede gastar el único intento automático congelando una cosecha con otro `T024_CODE_SHA`; el PC la rechazará después, así que la corrección depende de Fase B y el checkpoint queda perdido.

2. [traer_cosecha.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/deploy/t024/traer_cosecha.py:138) no valida completa la `peticion.json` copiada. Solo compara `end`/`checkpoint` contra `congelacion.json`, y del manifiesto contra `peticion.json` solo compara `start`, `end`, `interval`, `auto_adjust`, `actions`, `symbols`, `symbols_sha256` ([traer_cosecha.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/deploy/t024/traer_cosecha.py:164)). Quedan sin validar campos contractuales del artefacto como `end_exclusive`, `n_symbols` y `festivos`. Escenario: una copia/tampering de Pi trae `peticion.json` con `festivos: []` o `end_exclusive: false`, recalcula `SHA256SUMS`, pero el vintage/manifiesto real sigue correcto; `verificar()` puede devolver OK aunque el artefacto de petición no sea la petición exacta que se pretende versionar. Los tests solo alteran `end` ([tests/test_t024_deploy.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/tests/test_t024_deploy.py:321)), así que pasan por una cobertura demasiado estrecha.

**MENOR**

1. [instalar.sh](/Users/fer/Desktop/Trading%20bot/intradia-bot/deploy/t024/instalar.sh:16) hace `source` de `/etc/intradia-bot/t024.env` como root sin comprobar propietario, permisos ni que no sea symlink. Si ese fichero queda escribible por `fer` o por grupo, reinstalar ejecuta shell arbitrario como root antes de las comprobaciones. No cambia el contrato T-024, pero sí es un fallo operativo de permisos justo en el punto root/usuario.

2. [traer_cosecha.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/deploy/t024/traer_cosecha.py:45) ignora el segundo componente de rutas `vintage/<id>/...` en `SHA256SUMS`: siempre mapea a `vintage_dir / resto` y nunca exige que `<id>` sea `vintage_dir.name`. Escenario: `SHA256SUMS` puede listar `vintage/<otro-id>/manifest.json` con el hash del vintage actual y pasar la verificación de bytes. No parece abrir desenlaces ni aceptar datos distintos, pero rompe la exactitud semántica del manifiesto de hashes.

**OBSERVACIÓN**

El diff protegido pedido sale vacío: `git diff --name-only 1a697c3 HEAD -- advisor config.yaml universe.yaml exchange_overrides.yaml pyproject.toml requirements.txt` no devuelve rutas. El wrapper tampoco contiene rutas automáticas a `registrar`/`capturar`, el lock evita dos ejecuciones simultáneas, y `tree_dirty()` sí miraría un `__pycache__` sin seguimiento bajo `advisor`.

No ejecuté `pytest`, conforme a tu restricción; la revisión fue por lectura del diff y comprobaciones git puntuales en solo lectura.

Codex session ID: 01a110c9-8275-7770-8593-5ba60e37b640
Resume in Codex: codex resume 01a110c9-8275-7770-8593-5ba60e37b640
