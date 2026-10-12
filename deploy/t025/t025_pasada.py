"""Pasada programada de T-025: identidad previa, ``paper run`` y Telegram desde la vista visible.

Solo usa el CLI de ``paper`` (capa de visibilidad). La hora de la pasada sale de
``paper.universe.scheduled_passes`` (D-50): la última programada <= ahora, nunca más antigua que
T025_MAX_LAG_MIN (no se ejecutan pasadas retroactivas).
"""
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PY = sys.executable
# El script vive fuera del repo: el código de paper/advisor se importa del worktree (cwd).
sys.path.insert(0, os.getcwd())
DB = os.environ["T025_DB"]
STATE = Path(os.environ["T025_STATE"])
SEND = os.environ.get("T025_TELEGRAM_SEND", "0") == "1"


def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).isoformat()} {msg}", flush=True)


def cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, "-m", "paper", "--db", DB, *args], capture_output=True, text=True)


def payload(stdout: str):
    from paper import LABEL

    label, _, body = stdout.partition("\n")
    if label != LABEL:
        raise ValueError(f"salida sin la etiqueta SHADOW / PAPER: {label[:80]!r}")
    return json.loads(body)


def preflight() -> None:
    from paper.cli import code_identity_ok, git_head
    from paper.environment import current_environment

    head = git_head()
    env = current_environment()
    problems = []
    if head != os.environ["T025_CODE_SHA"]:
        problems.append(f"HEAD {head} != t025_code_sha")
    if not code_identity_ok(os.environ["T025_CODE_SHA"]):
        problems.append("code_identity_ok = False (diff o árbol sucio en rutas económicas)")
    if env.python_version != os.environ["T025_PYTHON_VERSION"]:
        problems.append(f"python {env.python_version} distinto de la época 1")
    if env.packages_sha256 != os.environ["T025_PACKAGES_SHA256"]:
        problems.append(f"packages_sha256 {env.packages_sha256} distinto de la época 1")
    if env.requirements_sha256 != os.environ["T025_REQUIREMENTS_SHA256"]:
        problems.append(f"requirements_sha256 {env.requirements_sha256} distinto de la época 1")
    if problems:
        # No se ejecuta: el runner grabaría la pasada como OK (issue #51) y ya no se podría repetir. La siguiente
        # pasada válida registra esta como ENGINE_DOWNTIME (SIN_EJECUCION), como cualquier unidad fallida.
        log("IDENTIDAD/ENTORNO NO COINCIDEN, pasada NO ejecutada: " + "; ".join(problems))
        raise SystemExit(10)


def pass_ts() -> datetime:
    from paper.universe import scheduled_passes

    lag = timedelta(minutes=int(os.environ["T025_MAX_LAG_MIN"]))
    now = datetime.now(timezone.utc)
    passes = [p for p in scheduled_passes(now - lag, now) if p <= now]
    if not passes:
        log(f"sin pasada programada en los últimos {lag}: no se ejecuta")
        raise SystemExit(11)
    return passes[-1]


def message(text: str, session: str) -> str:
    """Vista resumida para Telegram; ante cualquier fallo del resumen, el texto completo de siempre."""

    try:
        from t025_resumen import resumir  # junto a este script en bin/

        return resumir(text, session)
    except Exception as exc:
        log(f"telegram {session}: resumen no disponible ({exc!r}), se envía el texto completo")
        return f"{text}\nSesión de señal {session}"


def telegram() -> int:
    since = (datetime.now(timezone.utc).date() - timedelta(days=21)).isoformat()
    res = cli("signals", "--since", since)
    if res.returncode != 0:
        log(f"signals falló rc={res.returncode}: {res.stderr.strip()[-500:]}")
        return 3
    sessions = sorted({s["signal_session_date"] for s in payload(res.stdout)})
    failures = 0
    for session in sessions:
        msg = cli("telegram", "--session", session)
        if msg.returncode != 0:
            log(f"telegram {session} falló rc={msg.returncode}")
            failures += 1
            continue
        text = msg.stdout.rstrip("\n")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        last = STATE / f"telegram-{'' if SEND else 'dry-'}{session}.sha256"
        previous = last.read_text().strip() if last.exists() else None
        has_signals = "Sin señales OPERAR" not in text
        if previous == digest:
            continue
        if previous is None and not has_signals:
            last.write_text(digest)  # sin OPERAR y nunca enviado: no se manda ruido
            continue
        # El digest va sobre el texto del CLI (lo que cambia la vista visible); a Telegram va el resumen.
        full = message(text, session)
        print(full, flush=True)
        if not SEND:
            last.write_text(digest)
            log(f"telegram {session}: NO enviado (T025_TELEGRAM_SEND=0)")
            continue
        from paper.telegram import send

        if send(full):
            last.write_text(digest)
            log(f"telegram {session}: enviado")
        else:
            log(f"telegram {session}: el envío falló")
            failures += 1
    return 3 if failures else 0


def main() -> int:
    preflight()
    ts = pass_ts()
    log(f"pasada programada {ts.isoformat()}")
    res = cli("run", "--pass-ts", ts.isoformat())
    sys.stdout.write(res.stdout)
    sys.stderr.write(res.stderr)
    try:
        status = payload(res.stdout)["status"]
    except Exception:
        status = "?"
    log(f"run rc={res.returncode} status={status}")
    if res.returncode != 0 and status != "ALREADY_DONE":
        return res.returncode or 1
    return telegram()


if __name__ == "__main__":
    sys.exit(main())
