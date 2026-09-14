"""Manifiesto reconstruible de cada pasada persistida."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import socket
import struct
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import yfinance as yf

from advisor.analysis.scoring import SCORE_MODEL_VERSION
from advisor.config import AdvisorConfig
from advisor.universe.models import Universe

logger = logging.getLogger(__name__)

CLOCK_OK = "CLOCK_OK"
CLOCK_UNKNOWN = "CLOCK_UNKNOWN"
CLOCK_SUSPECT = "CLOCK_SUSPECT"


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    command: str
    git_sha: str
    git_dirty: bool
    config_hash: str
    universe_vintage_id: str
    data_vintage_id: Optional[str]
    score_model_version: str
    context_model_version: Optional[str]
    schema_version: int
    analysis_timestamp: str
    environment: str
    python_version: str
    provider_versions: dict[str, str]
    clock_drift_seconds: Optional[float]
    clock_status: str

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["git_dirty"] = int(self.git_dirty)
        row["provider_versions"] = json.dumps(self.provider_versions, sort_keys=True)
        return row


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def config_hash(config: AdvisorConfig) -> str:
    return canonical_hash(config.model_dump(mode="json"))


def universe_vintage_id(universe: Universe) -> str:
    symbols = sorted(asset.symbol for asset in universe.analizables())
    return canonical_hash({"analizables": symbols})


def git_sha(repo: str | Path = ".") -> str:
    return _git(["rev-parse", "HEAD"], repo) or "unknown"


def git_dirty(repo: str | Path = ".") -> bool:
    return bool(_git(["status", "--porcelain"], repo))


def build_run_manifest(
    *,
    command: str,
    config: AdvisorConfig,
    universe: Universe,
    schema_version: int,
    timestamp: datetime,
) -> RunManifest:
    drift = measure_clock_drift_seconds()
    status = CLOCK_UNKNOWN if drift is None else CLOCK_OK
    if drift is not None and abs(drift) > 60:
        status = CLOCK_SUSPECT
        logger.error("Deriva de reloj sospechosa: %.3f s", drift)

    return RunManifest(
        run_id=str(uuid.uuid4()),
        command=command,
        git_sha=git_sha(),
        git_dirty=git_dirty(),
        config_hash=config_hash(config),
        universe_vintage_id=universe_vintage_id(universe),
        data_vintage_id=None,
        score_model_version=SCORE_MODEL_VERSION,
        context_model_version=None,
        schema_version=schema_version,
        analysis_timestamp=timestamp.astimezone(timezone.utc).isoformat(),
        environment=_environment(),
        python_version=platform.python_version(),
        provider_versions={"yfinance": yf.__version__, "pandas": pd.__version__},
        clock_drift_seconds=drift,
        clock_status=status,
    )


def measure_clock_drift_seconds() -> Optional[float]:
    for probe in (_drift_from_timedatectl, _drift_from_chronyc, _drift_from_ntp):
        try:
            drift = probe()
        except Exception as exc:
            logger.debug("Medición de reloj fallida con %s: %s", probe.__name__, exc)
            continue
        if drift is not None:
            return drift
    return None


def _git(args: list[str], repo: str | Path) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _environment() -> str:
    explicit = os.getenv("INTRADIA_ENV")
    if explicit:
        return explicit
    hostname = socket.gethostname().lower()
    if os.getenv("CI"):
        return "ci"
    if "raspberry" in hostname or hostname.startswith("pi"):
        return "pi"
    return "laptop"


def _drift_from_timedatectl() -> Optional[float]:
    """Desfase que reporta systemd-timesyncd (``Offset: -572us``).

    ``timedatectl show -p TimeUSec`` no sirve: devuelve el reloj local en
    formato humano, y compararlo consigo mismo daría siempre cero. El desfase
    real contra el servidor NTP está en ``timesync-status``.
    """

    result = subprocess.run(
        ["timedatectl", "timesync-status"],
        check=False,
        capture_output=True,
        text=True,
        timeout=2,
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        key, _, value = line.partition(":")
        if key.strip() == "Offset":
            return _parse_offset(value.strip())
    return None


_OFFSET_UNITS = {"ns": 1e-9, "us": 1e-6, "ms": 1e-3, "s": 1.0, "min": 60.0, "h": 3600.0}


def _parse_offset(value: str) -> Optional[float]:
    """``-572us`` → ``-0.000572``; ``+1.2ms`` → ``0.0012``. ``None`` si no se entiende."""

    text = value.strip().replace("µs", "us")
    for unit in sorted(_OFFSET_UNITS, key=len, reverse=True):
        if text.endswith(unit):
            number = text[: -len(unit)].strip()
            try:
                return float(number) * _OFFSET_UNITS[unit]
            except ValueError:
                return None
    return None


def _drift_from_chronyc() -> Optional[float]:
    result = subprocess.run(
        ["chronyc", "tracking"],
        check=False,
        capture_output=True,
        text=True,
        timeout=2,
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if not line.startswith("System time"):
            continue
        parts = line.split()
        if len(parts) < 4:
            return None
        drift = float(parts[3])
        return -drift if "slow" in line else drift
    return None


def _drift_from_ntp(server: str = "pool.ntp.org", timeout: float = 2.0) -> Optional[float]:
    """Sonda SNTP por UDP contra una sola dirección.

    NTP solo atiende en UDP/123: una conexión TCP nunca se establece y, con
    las cuatro direcciones que resuelve el pool, costaba ~6 s por pasada sin
    medir nada.
    """

    packet = b"\x1b" + 47 * b"\0"
    epoch_delta = 2_208_988_800
    address = socket.getaddrinfo(server, 123, socket.AF_INET, socket.SOCK_DGRAM)[0][4]
    sent_at = datetime.now(timezone.utc).timestamp()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(packet, address)
        data, _ = sock.recvfrom(48)
    received_at = datetime.now(timezone.utc).timestamp()
    if len(data) < 48:
        return None
    seconds, fraction = struct.unpack("!II", data[40:48])
    remote = seconds - epoch_delta + fraction / 2**32
    local_midpoint = (sent_at + received_at) / 2
    return local_midpoint - remote


def format_manifest_footer(manifest: RunManifest) -> str:
    dirty = "+dirty" if manifest.git_dirty else ""
    return (
        f"run {manifest.run_id} · {manifest.git_sha[:12]}{dirty} · "
        f"config {manifest.config_hash[:8]} · universo {manifest.universe_vintage_id[:8]}"
    )
