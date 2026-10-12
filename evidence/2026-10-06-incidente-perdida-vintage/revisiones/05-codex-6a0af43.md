**BLOCKER**

- [tests/conftest.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/tests/conftest.py:277): la red de subprocess solo inspecciona `argv[0]` o cadenas shell simples. Un test puede saltársela con wrappers que ejecutan `rm` como argumento, por ejemplo `subprocess.run(["/usr/bin/env", "rm", "-rf", str(ROOT / "evidence")])` o `find ... -exec rm ...`. No lo detecta como borrado, y al ejecutarse fuera de Python tampoco pasan por los wrappers de `os.unlink`/`shutil.rmtree`.

**IMPORTANTE**

- [tests/conftest.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/tests/conftest.py:308): la fixture no envuelve `os.system`/`os.spawn*`/`os.posix_spawn*`. Escenario concreto: `os.system(f"rm -rf {ROOT / 'evidence'}")` ejecutaría un shell externo sin pasar por `_PopenGuardado` ni por los wrappers de `os.remove`, pudiendo borrar rutas protegidas del repo.

- [deploy/t024/traer_cosecha.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/deploy/t024/traer_cosecha.py:266): `copiar()` verifica el staging antes de promover, pero no re-verifica el destino ya promovido. Si algo local modifica `staging` entre `verificar(...)` y `promover_sin_pisar(...)`, se puede materializar una cosecha/artefactos distintos de los verificados. No veo borrado fuera de staging por esta vía, pero sí un hueco de integridad de staging.

**MENOR**

- Vacía.

**OBSERVACIÓN**

- Las correcciones de ronda 3 para `dir_fd`/`src_dir_fd`/`dst_dir_fd` están presentes: [tests/conftest.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/tests/conftest.py:235) resuelve el descriptor con `F_GETPATH` o `/proc/self/fd` y falla cerrado si no puede.
- `promover_sin_pisar` ya es todo-o-nada para el destino final: crea con `os.mkdir` exclusivo y, si falla a mitad, renombra el destino recién creado a staging y lo borra vía guarda ([deploy/t024/borrado_seguro.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/deploy/t024/borrado_seguro.py:110)).
- La segunda copia queda fuera de `repo` y `data_dir`, se verifica después de crearla, no pisa copias previas, rechaza enlaces y comprueba inodos distintos ([deploy/t024/checkpoint.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/deploy/t024/checkpoint.py:338)).
- Fase A sigue limitada a `peticion`/`congelar`; no vi rutas de `registrar`/`capturar` en el wrapper operativo.
- `git diff 1a697c3 HEAD -- advisor config.yaml universe.yaml exchange_overrides.yaml pyproject.toml requirements.txt` salió vacío (`exit=0`).
- No ejecuté `pytest`, como pediste.

Codex session ID: 01a110ec-4cb2-79f3-a18d-fc845cfef825
Resume in Codex: codex resume 01a110ec-4cb2-79f3-a18d-fc845cfef825
