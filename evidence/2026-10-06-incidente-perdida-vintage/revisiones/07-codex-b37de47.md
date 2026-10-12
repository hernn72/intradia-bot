BLOCKER: vacío.

IMPORTANTE:
- [tests/red_borrado.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/tests/red_borrado.py:211): `PopenGuardado` solo mira `shell`, `executable` y `env` en `kwargs`, pero `subprocess.Popen` acepta esos parámetros también por posición. Escenario: `subprocess.Popen(f"{sys.executable} -S -c ...", -1, None, None, None, None, None, True, True)` ejecuta con `shell=True` posicional, pero la guarda lo analiza como `shell=False`; no detecta el intérprete ni `-S`, y el hijo Python puede arrancar sin `sitecustomize`.

- [tests/red_borrado.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/tests/red_borrado.py:240): `envolver_proceso` para `os.spawn*`/`os.exec*` extrae `programa`, `argv` y `env` solo desde `args`, ignorando keywords. En macOS aquí `os.spawnve`/`os.spawnv` aceptan keywords. Escenario: `os.spawnve(os.P_WAIT, file=sys.executable, args=[sys.executable, "-S", "-c", "..."], env={"PATH": ...})` llega a `asegurar_hijo` como orden vacía y sin entorno explícito; no niega `-S` ni inyecta `PYTHONPATH`/`INTRADIA_RED_BORRADO_REPO`.

- [tests/red_borrado.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/tests/red_borrado.py:160): `flags_que_anulan_la_red` corta al primer token no opción, pero algunas opciones de Python consumen argumento y permiten más opciones después. Escenario: `[sys.executable, "-W", "ignore", "-S", "-c", "..."]`; la función ve `-W`, luego `"ignore"` y deja de mirar, por lo que no detecta `-S`. Esto contradice la promesa de negar `-I/-E/-S` en cualquier intérprete Python de la orden.

MENOR: vacío.

OBSERVACIÓN:
- Para los caminos normales añadidos en `b37de47`, el hallazgo anterior sí queda cubierto: `subprocess(..., shell=True)` por keyword, `Popen(executable=...)`, `os.system`, `os.spawnve`/`os.posix_spawn` posicionales y entorno explícito tipo dict reciben la regla única e inyección de entorno.
- Confirmé que `git diff --exit-code 1a697c3 HEAD -- advisor config.yaml universe.yaml exchange_overrides.yaml pyproject.toml requirements.txt` sigue vacío. Git devolvió código 0; solo emitió avisos del sandbox sobre cachés temporales de macOS.
- La fase A sigue sin ruta para registrar, capturar ni abrir desenlaces: `deploy/t024/checkpoint.py` permite solo `git rev-parse`, preflight/identidad, `t024_forward peticion` y `t024_forward congelar` en [_permite](/Users/fer/Desktop/Trading%20bot/intradia-bot/deploy/t024/checkpoint.py:205), y las llamadas reales son `peticion`/`congelar`, no `registrar`/`capturar` ni `ejecutar_mirada`.
- No ejecuté `pytest` ni ningún test. Solo usé lectura, `git diff/show/grep` e introspección de firmas con `python3 -B`; no modifiqué archivos.

Codex session ID: 01a11167-8134-7802-b2d3-6db8062d3473
Resume in Codex: codex resume 01a11167-8134-7802-b2d3-6db8062d3473
