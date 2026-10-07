# T-024 — Creación de la línea `t024/forward` y traslado del worktree de la Pi (D-77), 2026-10-07

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

Ejecuta el procedimiento de D-77. No cambia el pre-registro ni el código de T-024, ni ningún
`EXECUTOR_PATH`. No descarga datos, no congela ninguna cosecha, no registra, no captura conteos y no
ejecuta ninguna mirada.

## Git

- PR #48 `MERGED` con merge normal: `main = b21e7cc66337f617b6a2fb9c26a2d9b663209a83`, padres `f80ab28`
  (main anterior) y `c6fdc42` (`T025_PREREG_SHA`). El árbol de `b21e7cc` es idéntico al de `c6fdc42`.
- Sobre `origin/main`: `git diff --quiet 1a697c3 origin/main -- <EXECUTOR_PATHS>` → exit 0;
  `verificar_identidad()` → `1a697c3fa2ab76ddfcf567c2ef3f5ab56492eaf0` (en un worktree desacoplado).
- **`t024/forward` creada en el remoto en `b21e7cc`** (el merge de #48, no `1a697c3`), sin force-push.
  `git diff --quiet 1a697c3 origin/t024/forward -- <EXECUTOR_PATHS>` → exit 0.
- **Protección:** `main` está protegida (sin force-push ni borrado, CI 3.12/3.13 requerida, PR,
  `enforce_admins`) por un ruleset con `include: refs/heads/main`. `t024/forward` **no** está protegida.
  No se cambió ninguna regla del repositorio: queda como acción del propietario.

## Entorno de Python propio para T-024 (D-77, paso 7)

- Antes: la unidad usaba `/home/fer/intradia-bot/.venv/bin/python` (venv del bot; Python 3.13.5 de
  `/usr/bin/python3.13`; 49 distribuciones).
- **Nuevo venv dedicado: `/home/fer/t024-venv`**, fuera de los dos checkouts, creado con el mismo
  `/usr/bin/python3.13 -m venv` e instalando con `pip install --no-deps --only-binary=:all:` exactamente
  la lista congelada del venv del bot (`t024-venv.freeze-origen.txt`, sha256 `f942f27a…`), incluida
  `pip==26.2.1`. Ningún paquete se actualizó ni cambió de versión; el venv del bot no se tocó.
- **Evidencia de reproducción:**
  - `pip freeze --all` de los dos venvs: idénticos;
  - comparación de los `RECORD` de las 49 distribuciones (7.187 entradas con hash): **todos los ficheros
    de biblioteca son idénticos byte a byte**; las únicas 17 diferencias son scripts de `bin/` cuyo
    shebang contiene la ruta del propio venv;
  - los ficheros instalados del venv nuevo cuadran todos con su `RECORD` (0 discrepancias);
  - versiones relevantes: Python 3.13.5, `yfinance` 1.7.0, `pandas` 3.0.5, `numpy` 2.5.2,
    `exchange_calendars` 4.13.2;
  - `verificar_identidad()` con el venv nuevo → `1a697c3…`.

## Traslado del worktree `/home/fer/intradia-t024`

Tras la ejecución diaria de las 12:00 (hoy no era checkpoint: «sin checkpoint hoy», exit 0) y fuera de
su ventana:
1. instantánea «antes» (`t024-snapshot-antes-20261007.txt`);
2. `systemctl stop intradia-t024-checkpoint.timer` (solo el timer de T-024; ninguna ejecución activa);
3. worktree limpio, incluidos no versionados; `git fetch origin` en el repositorio compartido (actualiza
   referencias; no toca el árbol ni el HEAD del checkout habitual);
4. `git switch -c t024/forward --track origin/t024/forward` en el worktree: `4170bb4` → `b21e7cc`, sin
   borrar ni recrear nada;
5. diff de `EXECUTOR_PATHS` contra `1a697c3` vacío y `verificar_identidad()` = `1a697c3…` con los dos
   intérpretes;
6. copia `/etc/intradia-bot/t024.env.bak-20261007` y cambio de una sola línea:
   `T024_PYTHON=/home/fer/t024-venv/bin/python`;
7. `sudo bash deploy/t024/instalar.sh` desde el worktree (vuelve a comprobar el árbol limpio, el diff, el
   import de `advisor` y la identidad; reinstala la unidad y hace `enable --now` del timer).

## Verificación posterior

- Worktree: rama `t024/forward`, HEAD `b21e7cc`, upstream `origin/t024/forward`, `git status` limpio
  (solo un `.pyc` ignorado por `.gitignore` en `deploy/t024/__pycache__`, fuera de los `EXECUTOR_PATHS`).
- Checkout habitual `/home/fer/intradia-bot`: sin cambios, `8b2dddb` (`v0.4.1`), los mismos dos no
  versionados de antes; timers del bot sin tocar.
- systemd: `ExecStart=/home/fer/t024-venv/bin/python deploy/t024/checkpoint.py ejecutar --data-dir
  /home/fer/intradia-bot/data/vintages --artefactos /home/fer/t024-forward`,
  `WorkingDirectory=/home/fer/intradia-t024`, `User=fer`, `OnCalendar=*-*-* 12:00:00 Atlantic/Canary`;
  timer `enabled`/`active`, próximo disparo jueves 2026-10-08 12:00 BST.
- `checkpoint.py estado`: checkpoint `2026-11-03` `PENDIENTE`, calendario no agotado.
- **Prueba sin descarga por la unidad real** (`systemctl start intradia-t024-checkpoint.service`):
  `Result=success`, exit 0, log «sin checkpoint hoy».
- Antes/después (`t024-snapshot-*.txt`): solo cambian los dos logs (una línea más) y el HEAD del
  worktree. `data/vintages/` idéntico (solo el `manifest.json` de `071ddb2b…`, mismo hash); ninguna
  cosecha, ninguna segunda copia, ningún registro ni conteo.

## Copias externas

- PC, `~/intradia-backups/2026-10-06/` (fuera del repositorio): árbol completo y no versionado del
  portátil (`SHA256SUMS` OK) y las copias de `intradia.db` de la Pi (21 de `SHA256SUMS-pi-original` y la
  `copia-api-20261006`, todas OK). La más reciente es del 2026-10-06; `intradia.db` de la Pi ha seguido
  creciendo desde entonces.
- Pi: las copias `intradia.db.bak-*` viven dentro del checkout habitual, que no se modificó, pero no son
  externas.
- Segunda copia de T-024: todavía no existe ninguna cosecha forward (primer checkpoint 2026-11-03), así
  que no hay nada que copiar; los artefactos viven en `/home/fer/t024-forward`, fuera del worktree.
