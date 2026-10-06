# Incidente 2026-10-06 — pérdida de la cosecha consumida `071ddb2b…` en el portátil

## Qué pasó

- **Cuándo:** 2026-10-06, hacia las 10:33:55 UTC (11:33 hora local), en el portátil.
- **Dónde:** en la rama `research/t024-contrato-captura` (PR #46), durante una corrección de
  `deploy/t024/traer_cosecha.py` que Codex programaba con permiso de escritura y ejecución.
- **Causa técnica:**
  1. Para marcar un directorio de staging como «ya promovido», el código lo reasignaba a
     `staging = Path()`. En Python, `Path()` es el directorio actual.
  2. El bloque `finally` de esa función hacía `shutil.rmtree` del staging.
  3. Al ejecutar `pytest tests/test_t024_deploy.py` desde la raíz del repositorio, el `rmtree` actuó
     sobre la **raíz del checkout**. Fue borrando entradas hasta topar con `.git`, que en el sandbox de
     Codex era de solo lectura, y ahí se detuvo con error.
- **Detección:** la siguiente suite completa pasó de 1296 tests a 1289 passed y 19 skipped (los que
  necesitan los CSV de la cosecha) y tardó mucho menos. El log del job de Codex
  (`task-muwjf0qu-b5m7rj`, 10:34:12 UTC) describe el borrado y la restauración, pero su informe final
  no lo mencionaba.

## Qué se recuperó

**Git permitió restaurar todo lo versionado.** Codex reescribió desde `HEAD` los ficheros borrados
(10:34:41 UTC) y `git status` volvió a quedar limpio, incluido el `manifest.json` versionado de
`071ddb2b…`.

No se vieron afectados:
- `.git`;
- `.venv`;
- `advisor/`, `docs/` y `evidence/`, incluidos los ficheros sin seguimiento `* 2.md`;
- `graphify-out/`.

## Qué se perdió (sin copia recuperable)

No hay copia en iCloud, ni en Time Machine, ni en la copia de seguridad que se creía disponible. La Pi
solo conserva el `manifest.json` de esa cosecha.

- **Los 126 CSV de la cosecha consumida**
  `071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841`, congelada el 2026-08-30.
  Solo existían en el portátil.
- `intradia.db` del portátil y cuatro copias locales:
  - `intradia.db.bak-20260902-181458`;
  - `intradia.db.bak-20260914-091715-pre-v2`;
  - `intradia.db.bak-20260916-105826-pre-v3`;
  - `intradia.db.bak-20260917-095333-pre-v4`.
- `ultima_cerrada`, un fichero sin seguimiento del propietario.
- Posiblemente `.env`: ahora no existe en el portátil y no consta si existía antes.

**La base de producción de la Pi no se vio afectada.** El 2026-10-06, después del incidente, se
comprobó lo siguiente:
- `/home/fer/intradia-bot` en `v0.4.1`, árbol limpio;
- `intradia.db` y sus 21 copias pasan `PRAGMA quick_check = ok`;
- los timers del bot siguen activos.

## Consecuencias

- **P6 (T-022) y T-023 conservan toda su evidencia publicada:**
  - el manifiesto y sus hashes, `data_vintage_id`, `P6_DATA_ID`, resultados, commits, revisiones y
    decisiones (D-70, D-71, D-72);
  - siguen siendo históricos válidos;
  - **no se reescribe ninguna evidencia histórica**.
- **Lo que se pierde es la reproducibilidad desde cero** de esos cálculos con los CSV originales. El
  manifiesto permite comprobar que una copia es la original, pero no recrearla.
- **T-024 forward no queda bloqueado.** La lista de 126 símbolos se deriva del `manifest.json`, que está
  versionado e intacto, y el hash congelado `c7a896ab…` se sigue verificando. Los tests de desarrollo
  que necesitaban los CSV se omiten (`pytest.skip`), igual que ya ocurría en CI.

## Lo que NO se hará

- No se volverá a descargar de Yahoo para intentar recrear `071ddb2b…`. Una descarga actual tendría
  revisiones y no reproduciría los `series_hash` del manifiesto.
- No se reutilizará ese `data_vintage_id` para datos nuevos.
- No se presentará ninguna descarga posterior como equivalente a la cosecha original.

## Medidas

1. **Backups verificados fuera del repositorio**, en `~/intradia-backups/2026-10-06/`, antes de volver
   a ejecutar tests o a Codex:
   - árbol completo del portátil (sin `.venv` ni cachés);
   - lo no versionado que queda;
   - copia independiente de las bases de la Pi.

   Detalle en `backups.md`.
2. **Guarda fuerte de borrado** (`deploy/t024/borrado_seguro.py`, en el commit siguiente de esta rama). Toda
   limpieza de las herramientas T-024:
   - resuelve la ruta absoluta;
   - rechaza `/`, `$HOME`, la raíz del repositorio, `.`, `..` y cualquier antecesor de esos;
   - rechaza `data/`, `evidence/`, `.git/` y las bases SQLite;
   - solo borra directorios de nombre `.t024-staging-*` situados bajo la base esperada;
   - falla cerrada en cualquier otro caso.

   Además, la red de `tests/red_borrado.py` (instalada por `tests/conftest.py`) impide que un test
   borre, mueva o pise esas rutas:
   - envuelve `shutil.rmtree`, `os.remove`/`unlink`/`rmdir`/`removedirs` y `os.rename`/`replace`,
     resolviendo también las rutas relativas a `dir_fd`;
   - inspecciona las órdenes externas por tokens (`subprocess`, `os.system`, `spawn*`, `exec*`);
   - se propaga a todo intérprete Python hijo mediante `tests/red_hijos/sitecustomize.py`.

   **Riesgo residual:** un programa externo no Python que borre de una forma no reconocible por sus
   tokens. Lo cubren los backups fuera del repositorio.

   Se probó y se descartó dejar `data/` y `evidence/` sin permiso de escritura durante los tests. En este
   portátil el repositorio está en el Escritorio sincronizado con iCloud Drive, e iCloud reescribe los
   permisos de los directorios en segundos: los dejó en `drwx------`, tanto con la protección puesta como
   después. El 2026-10-06 se restauraron a mano los modos originales (`755`, comprobados contra el backup).
   Ningún fichero cambió. Mientras el repositorio siga en una carpeta sincronizada, la protección no
   puede apoyarse en permisos del sistema de ficheros.
3. **Doble copia de toda cosecha forward desde su creación** (también en el commit siguiente).
   - El wrapper de la Pi deja una segunda copia, verificada por hash, fuera del checkout del bot.
   - Dos copias dentro del mismo árbol no cuentan como backup.
