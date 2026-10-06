"""Wrapper operativo del checkpoint forward T-024."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

ZONA = "Atlantic/Canary"
SCHEMA = "t024-calendario-checkpoints"
SCHEMA_VERSION = 1
START_ESPERADO = "2021-08-30"
N_SIMBOLOS_ESPERADO = 126
SIMBOLOS_FORWARD_SHA256 = "c7a896ab921a27dce3e6ea268187ff03ce77954dd67298ac2b62d7c4017b50b5"
SHA40 = re.compile(r"[0-9a-f]{40}")
SHA64 = re.compile(r"[0-9a-f]{64}")
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
TIMEOUT_SECONDS = 3600

RC_OK = 0
RC_NO_APTA = 2
RC_CALENDARIO_AGOTADO = 3
RC_PERDIDO = 4
RC_INTERRUMPIDO = 5
RC_PREFLIGHT = 6
RC_CALENDARIO = 7
RC_CALENDARIO_INVALIDO = 8
RC_CONGELACION = 9
RC_LOCK = 75

SNIPPET_PREFLIGHT = "import advisor; print(advisor.__file__)"
SNIPPET_IDENTIDAD = "from advisor.research.t024_decision import verificar_identidad; print(verificar_identidad())"
COMANDOS_PERMITIDOS = (
    ("git", "rev-parse", "HEAD"),
    ("python", "-c", SNIPPET_PREFLIGHT),
    ("python", "-c", SNIPPET_IDENTIDAD),
    ("python", "-m", "advisor.research.t024_forward", "peticion"),
    ("python", "-m", "advisor.research.t024_forward", "congelar"),
)


@dataclass(frozen=True)
class Checkpoint:
    checkpoint: date
    festivos: tuple[date, ...]
    requested_end: date
    fuente: str


@dataclass(frozen=True)
class Calendario:
    path: Path
    checkpoints: tuple[Checkpoint, ...]


@dataclass(frozen=True)
class Cfg:
    repo: Path
    python: str
    data_dir: Path | None
    artefactos: Path
    calendario: Path


Runner = Callable[[list[str], Path], tuple[int, str, str]]


def repo_default() -> Path:
    return Path(__file__).resolve().parents[2]


def _fecha_iso(value: object, campo: str) -> date:
    if not isinstance(value, str) or not ISO_DATE.fullmatch(value):
        raise ValueError(f"{campo}: fecha ISO inválida")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError(f"{campo}: fecha ISO no canónica")
    return parsed


def cargar_calendario(path: str | Path) -> Calendario:
    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("calendario: JSON raíz no es objeto")
    requeridas = {"schema", "schema_version", "zona", "regla", "checkpoints"}
    if set(data) != requeridas:
        raise ValueError(f"calendario: claves inválidas {sorted(set(data) ^ requeridas)}")
    if data["schema"] != SCHEMA or data["schema_version"] != SCHEMA_VERSION or data["zona"] != ZONA:
        raise ValueError("calendario: schema, versión o zona inválidos")
    items = data["checkpoints"]
    if not isinstance(items, list) or not items:
        raise ValueError("calendario: checkpoints debe ser lista no vacía")
    out: list[Checkpoint] = []
    previo: date | None = None
    meses: set[tuple[int, int]] = set()
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError("calendario: checkpoint no es objeto")
        claves = {"checkpoint", "festivos", "requested_end", "fuente"}
        if set(raw) != claves:
            raise ValueError(f"calendario: claves de checkpoint inválidas {sorted(set(raw) ^ claves)}")
        cp = _fecha_iso(raw["checkpoint"], "checkpoint")
        requested_end = _fecha_iso(raw["requested_end"], "requested_end")
        festivos_raw = raw["festivos"]
        if not isinstance(festivos_raw, list):
            raise ValueError("calendario: festivos debe ser lista")
        festivos = tuple(_fecha_iso(item, "festivo") for item in festivos_raw)
        if list(festivos) != sorted(festivos) or len(set(festivos)) != len(festivos):
            raise ValueError("calendario: festivos no ordenados o duplicados")
        fuente = raw["fuente"]
        if not isinstance(fuente, str) or not fuente.strip():
            raise ValueError("calendario: fuente vacía")
        if previo is not None and cp <= previo:
            raise ValueError("calendario: checkpoints no crecientes")
        mes = (cp.year, cp.month)
        if mes in meses:
            raise ValueError("calendario: dos checkpoints en el mismo mes")
        meses.add(mes)
        previo = cp
        out.append(Checkpoint(cp, festivos, requested_end, fuente))
    return Calendario(source, tuple(out))


def hoy_canarias() -> date:
    return datetime.now(ZoneInfo(ZONA)).date()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def log(artefactos: Path, mensaje: str) -> None:
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    line = f"{stamp} {mensaje}"
    logs = artefactos / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / "checkpoint.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line)


def _json_write(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _json_write_excl(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n")


def _atomic_text(path: Path, texto: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, path)


def _permite(cmd: Sequence[str], python: str) -> None:
    if len(cmd) == 5 and cmd[0] == "git" and cmd[1] == "-C" and cmd[3:] == ["rev-parse", "HEAD"]:
        return
    if len(cmd) == 3 and cmd[0] == python and cmd[1:] == ["-c", SNIPPET_PREFLIGHT]:
        return
    if len(cmd) == 3 and cmd[0] == python and cmd[1:] == ["-c", SNIPPET_IDENTIDAD]:
        return
    if (
        len(cmd) >= 4
        and cmd[0] == python
        and cmd[1:3] == ["-m", "advisor.research.t024_forward"]
        and cmd[3] in {"peticion", "congelar"}
    ):
        return
    raise AssertionError(f"comando no permitido: {cmd}")


def run(cmd: list[str], cwd: Path, runner: Runner, *, python: str) -> tuple[int, str, str]:
    _permite(cmd, python)
    return runner(cmd, cwd)


def subprocess_runner(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True, timeout=TIMEOUT_SECONDS, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def _cp_dir(artefactos: Path, cp: date) -> Path:
    return artefactos / "checkpoints" / cp.isoformat()


def _estado(path: Path, checkpoint: date, estado: str, **extra: Any) -> None:
    payload = {"checkpoint": checkpoint.isoformat(), "estado": estado, **extra}
    _json_write(path / "estado.json", payload)


def _festivo_args(festivos: Iterable[date]) -> list[str]:
    args: list[str] = []
    for festivo in festivos:
        args.extend(["--festivo", festivo.isoformat()])
    return args


def _calendario_sha(calendario: Path) -> str:
    return sha256_path(calendario)


def _leer_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _preflight_ok(repo: Path, stdout: str) -> bool:
    resolved = Path(stdout.strip()).resolve()
    advisor_root = (repo / "advisor").resolve()
    try:
        resolved.relative_to(advisor_root)
    except ValueError:
        return False
    return True


def _validar_peticion(data: Mapping[str, Any], cp: Checkpoint) -> bool:
    symbols = data.get("symbols")
    if not isinstance(symbols, list) or not all(isinstance(item, str) for item in symbols):
        return False
    symbols_hash = hashlib.sha256("\n".join(symbols).encode("utf-8")).hexdigest()
    return (
        data.get("checkpoint") == cp.checkpoint.isoformat()
        and data.get("start") == START_ESPERADO
        and data.get("end") == cp.requested_end.isoformat()
        and data.get("end_exclusive") is True
        and data.get("interval") == "1d"
        and data.get("auto_adjust") is False
        and data.get("actions") is True
        and data.get("n_symbols") == N_SIMBOLOS_ESPERADO
        and len(symbols) == N_SIMBOLOS_ESPERADO
        and symbols == sorted(symbols)
        and len(set(symbols)) == N_SIMBOLOS_ESPERADO
        and data.get("symbols_sha256") == SIMBOLOS_FORWARD_SHA256
        and symbols_hash == SIMBOLOS_FORWARD_SHA256
        and data.get("festivos") == [dia.isoformat() for dia in cp.festivos]
    )


def _sha_line(path: Path, name: str) -> str:
    return f"{sha256_path(path)}  {name}"


def escribir_sha256s(dir_cp: Path, data_dir: Path, congelacion: Mapping[str, Any]) -> None:
    lines = []
    for name in ("intento.json", "identidad.txt", "peticion.json", "congelacion.json", "congelar.stderr.log", "estado.json"):
        path = dir_cp / name
        if path.is_file():
            lines.append(_sha_line(path, name))
    vintage_id = congelacion.get("data_vintage_id")
    if isinstance(vintage_id, str) and SHA64.fullmatch(vintage_id):
        vintage_dir = data_dir / vintage_id
        if vintage_dir.is_dir():
            for path in sorted(item for item in vintage_dir.rglob("*") if item.is_file()):
                rel = path.relative_to(vintage_dir).as_posix()
                lines.append(_sha_line(path, f"vintage/{vintage_id}/{rel}"))
    _atomic_text(dir_cp / "SHA256SUMS", "\n".join(sorted(lines)) + "\n")


def _rc_final(base: int, aviso_horizonte: bool, perdido_nuevo: bool) -> int:
    if base not in {RC_OK, RC_CALENDARIO_AGOTADO, RC_PERDIDO}:
        return base
    if perdido_nuevo:
        return RC_PERDIDO
    if aviso_horizonte:
        return RC_CALENDARIO_AGOTADO
    return base


def _checkpoint_mes_siguiente(hoy: date, calendario: Calendario) -> bool:
    anio = hoy.year + (1 if hoy.month == 12 else 0)
    mes = 1 if hoy.month == 12 else hoy.month + 1
    return any((cp.checkpoint.year, cp.checkpoint.month) == (anio, mes) for cp in calendario.checkpoints)


def _ultimos_10_dias_mes(hoy: date) -> bool:
    siguiente = date(hoy.year + 1, 1, 1) if hoy.month == 12 else date(hoy.year, hoy.month + 1, 1)
    return (siguiente - hoy).days <= 10


def ejecutar(cfg: Cfg, hoy: date, runner: Runner) -> int:
    calendario = cargar_calendario(cfg.calendario)
    cfg.artefactos.mkdir(parents=True, exist_ok=True)
    lock_path = cfg.artefactos / ".lock"
    with lock_path.open("a", encoding="utf-8") as lock_fh:
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log(cfg.artefactos, "lock ocupado; no se ejecuta nada")
            return RC_LOCK
        perdido_nuevo = False
        for cp in calendario.checkpoints:
            path = _cp_dir(cfg.artefactos, cp.checkpoint)
            if cp.checkpoint < hoy and not path.exists():
                path.mkdir(parents=True, exist_ok=True)
                _estado(path, cp.checkpoint, "PERDIDO", detectado=hoy.isoformat())
                log(cfg.artefactos, f"{cp.checkpoint.isoformat()} marcado como PERDIDO")
                perdido_nuevo = True
        aviso_horizonte = _ultimos_10_dias_mes(hoy) and not _checkpoint_mes_siguiente(hoy, calendario)
        cp_hoy = next((item for item in calendario.checkpoints if item.checkpoint == hoy), None)
        base = RC_OK
        if cp_hoy is None:
            log(cfg.artefactos, "sin checkpoint hoy")
        else:
            base = _ejecutar_checkpoint(cfg, calendario, cp_hoy, hoy, runner)
        if aviso_horizonte:
            log(cfg.artefactos, "CALENDARIO_AGOTADO: falta declarar el checkpoint del mes siguiente")
        return _rc_final(base, aviso_horizonte, perdido_nuevo)


def _ejecutar_checkpoint(cfg: Cfg, calendario: Calendario, cp: Checkpoint, hoy: date, runner: Runner) -> int:
    assert cfg.data_dir is not None
    dir_cp = _cp_dir(cfg.artefactos, cp.checkpoint)
    intento = dir_cp / "intento.json"
    if intento.exists():
        estado_path = dir_cp / "estado.json"
        if estado_path.exists():
            estado = _leer_json(estado_path).get("estado")
            log(cfg.artefactos, f"{cp.checkpoint.isoformat()} ya tiene intento con estado {estado}")
            return RC_OK if estado in {"APTA", "NO_APTA"} else RC_INTERRUMPIDO
        _estado(dir_cp, cp.checkpoint, "INTERRUMPIDO")
        log(cfg.artefactos, f"{cp.checkpoint.isoformat()} tiene intento sin estado final")
        return RC_INTERRUMPIDO
    dir_cp.mkdir(parents=True, exist_ok=True)
    rc, stdout, stderr = run(["git", "-C", str(cfg.repo), "rev-parse", "HEAD"], cfg.repo, runner, python=cfg.python)
    repo_head = stdout.strip() if rc == 0 else ""
    _json_write_excl(
        intento,
        {
            "checkpoint": cp.checkpoint.isoformat(),
            "hoy": hoy.isoformat(),
            "inicio_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "repo": str(cfg.repo),
            "python": cfg.python,
            "calendario_sha256": _calendario_sha(calendario.path),
            "wrapper_sha256": sha256_path(Path(__file__).resolve()),
            "repo_head": repo_head,
        },
    )
    if rc != 0 or not SHA40.fullmatch(repo_head):
        _atomic_text(dir_cp / "git.stderr.log", stderr)
        _estado(dir_cp, cp.checkpoint, "ERROR_PREFLIGHT")
        return RC_PREFLIGHT
    rc, stdout, stderr = run([cfg.python, "-c", SNIPPET_PREFLIGHT], cfg.repo, runner, python=cfg.python)
    if rc != 0 or not _preflight_ok(cfg.repo, stdout):
        _atomic_text(dir_cp / "preflight.stderr.log", stderr)
        _estado(dir_cp, cp.checkpoint, "ERROR_PREFLIGHT")
        return RC_PREFLIGHT
    rc, stdout, stderr = run([cfg.python, "-c", SNIPPET_IDENTIDAD], cfg.repo, runner, python=cfg.python)
    _atomic_text(dir_cp / "identidad.txt", stdout)
    if rc != 0 or not SHA40.fullmatch(stdout.strip()):
        _atomic_text(dir_cp / "identidad.stderr.log", stderr)
        _estado(dir_cp, cp.checkpoint, "ERROR_IDENTIDAD")
        return RC_PREFLIGHT
    peticion_cmd = [
        cfg.python,
        "-m",
        "advisor.research.t024_forward",
        "peticion",
        "--checkpoint",
        cp.checkpoint.isoformat(),
        *_festivo_args(cp.festivos),
    ]
    rc, stdout, stderr = run(peticion_cmd, cfg.repo, runner, python=cfg.python)
    _atomic_text(dir_cp / "peticion.json", stdout)
    if rc != 0:
        _atomic_text(dir_cp / "peticion.stderr.log", stderr)
        _estado(dir_cp, cp.checkpoint, "ERROR_CALENDARIO")
        return RC_CALENDARIO
    try:
        peticion = json.loads(stdout)
    except json.JSONDecodeError:
        peticion = {}
    if not isinstance(peticion, dict) or not _validar_peticion(peticion, cp):
        _estado(dir_cp, cp.checkpoint, "ERROR_CALENDARIO")
        return RC_CALENDARIO
    congelar_cmd = [
        cfg.python,
        "-m",
        "advisor.research.t024_forward",
        "congelar",
        "--checkpoint",
        cp.checkpoint.isoformat(),
        *_festivo_args(cp.festivos),
        "--data-dir",
        str(cfg.data_dir),
    ]
    rc, stdout, stderr = run(congelar_cmd, cfg.repo, runner, python=cfg.python)
    _atomic_text(dir_cp / "congelacion.json", stdout)
    _atomic_text(dir_cp / "congelar.stderr.log", stderr)
    try:
        congelacion = json.loads(stdout)
    except json.JSONDecodeError:
        congelacion = {}
    if not isinstance(congelacion, dict):
        congelacion = {}
    apta = congelacion.get("apta")
    if rc == 0 and apta is True:
        estado = "APTA"
        salida = RC_OK
    elif rc == RC_NO_APTA and apta is False:
        estado = "NO_APTA"
        salida = RC_NO_APTA
    else:
        _estado(dir_cp, cp.checkpoint, "ERROR_CONGELACION", rc_congelar=rc)
        escribir_sha256s(dir_cp, cfg.data_dir, congelacion)
        return RC_CONGELACION
    _estado(
        dir_cp,
        cp.checkpoint,
        estado,
        data_vintage_id=congelacion.get("data_vintage_id"),
        apta=bool(apta),
        rc_congelar=rc,
        motivos=congelacion.get("motivos", []),
        finalizado_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )
    escribir_sha256s(dir_cp, cfg.data_dir, congelacion)
    log(cfg.artefactos, f"{cp.checkpoint.isoformat()} finalizado con estado {estado}")
    return salida


def estado(cfg: Cfg, hoy: date) -> int:
    calendario = cargar_calendario(cfg.calendario)
    checkpoints = []
    for cp in calendario.checkpoints:
        dir_cp = _cp_dir(cfg.artefactos, cp.checkpoint)
        if (dir_cp / "estado.json").exists():
            estado_cp = str(_leer_json(dir_cp / "estado.json").get("estado"))
        elif dir_cp.exists():
            estado_cp = "SIN_ESTADO"
        elif cp.checkpoint < hoy:
            estado_cp = "PERDIDO"
        else:
            estado_cp = "PENDIENTE"
        checkpoints.append({"checkpoint": cp.checkpoint.isoformat(), "estado": estado_cp})
    aviso = _ultimos_10_dias_mes(hoy) and not _checkpoint_mes_siguiente(hoy, calendario)
    print(json.dumps({"zona": ZONA, "hoy": hoy.isoformat(), "calendario_agotado": aviso, "checkpoints": checkpoints}, sort_keys=True, indent=2))
    return RC_OK


def _parse_hoy(value: str | None) -> date:
    return hoy_canarias() if value is None else _fecha_iso(value, "hoy")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python deploy/t024/checkpoint.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("ejecutar", "estado"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--repo", type=Path, default=repo_default())
        cmd.add_argument("--python", default=sys.executable)
        cmd.add_argument("--artefactos", type=Path, required=True)
        cmd.add_argument("--calendario", type=Path)
    sub.choices["estado"].add_argument("--hoy")
    sub.choices["ejecutar"].add_argument("--data-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = args.repo.resolve()
    calendario = args.calendario or (repo / "deploy" / "t024" / "calendario-checkpoints.json")
    cfg = Cfg(repo=repo, python=args.python, data_dir=getattr(args, "data_dir", None), artefactos=args.artefactos, calendario=calendario)
    try:
        if args.cmd == "estado":
            dia = _parse_hoy(args.hoy)
            return estado(cfg, dia)
        return ejecutar(cfg, hoy_canarias(), subprocess_runner)
    except ValueError as exc:
        print(f"CALENDARIO_INVALIDO: {exc}", file=sys.stderr)
        return RC_CALENDARIO_INVALIDO


if __name__ == "__main__":
    raise SystemExit(main())
