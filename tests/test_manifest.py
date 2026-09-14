"""Manifiesto de ejecución."""

from __future__ import annotations

import subprocess

import pytest

from advisor.config import load_config
from advisor.run import manifest
from advisor.run.manifest import config_hash, git_dirty, measure_clock_drift_seconds


def test_manifest_config_hash_es_canonico(tmp_path) -> None:
    first = tmp_path / "a.yaml"
    second = tmp_path / "b.yaml"
    changed = tmp_path / "c.yaml"
    first.write_text(
        """
base_currency: EUR
horizontes:
  swing:
    interval: 1d
    period: 1y
    min_bars: 120
request_min_interval_seconds: 1.0
""",
        encoding="utf-8",
    )
    second.write_text(
        """
request_min_interval_seconds: 1.0
horizontes:
  swing:
    min_bars: 120
    period: 1y
    interval: 1d
base_currency: EUR
""",
        encoding="utf-8",
    )
    changed.write_text(first.read_text(encoding="utf-8").replace("120", "121"), encoding="utf-8")

    assert config_hash(load_config(first)) == config_hash(load_config(second))
    assert config_hash(load_config(first)) != config_hash(load_config(changed))


def test_manifest_git_dirty(tmp_path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("uno\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True, capture_output=True)
    tracked.write_text("dos\n", encoding="utf-8")

    assert git_dirty(tmp_path) is True


def test_manifest_git_dirty_ignora_ficheros_sin_seguimiento(tmp_path) -> None:
    """`logs/` en la Pi no convierte cada pasada en `+dirty`."""

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True, capture_output=True)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("uno\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "analizar.log").write_text("x", encoding="utf-8")

    assert git_dirty(tmp_path) is False


def test_clock_drift_no_bloquea(monkeypatch) -> None:
    def fail_run(*_args, **_kwargs):
        raise FileNotFoundError("sin herramienta")

    def fail_socket(*_args, **_kwargs):
        raise OSError("sin red")

    monkeypatch.setattr(manifest.subprocess, "run", fail_run)
    monkeypatch.setattr(manifest.socket, "getaddrinfo", fail_socket)

    assert measure_clock_drift_seconds() is None


def test_offset_de_timesync_status_se_parsea_en_segundos() -> None:
    """Salida real de la Pi el 2026-09-14: `Offset: -572us`."""

    assert manifest._parse_offset("-572us") == pytest.approx(-0.000572)
    assert manifest._parse_offset("+1.5ms") == pytest.approx(0.0015)
    assert manifest._parse_offset("2s") == pytest.approx(2.0)
    assert manifest._parse_offset("Mon 2026-09-14 10:29:24 BST") is None


def test_timedatectl_usa_timesync_status(monkeypatch) -> None:
    class Result:
        returncode = 0
        stdout = (
            "       Server: 195.95.153.43 (2.debian.pool.ntp.org)\n"
            "       Offset: -572us\n"
            "        Delay: 29.094ms\n"
        )

    def fake_run(args, **_kwargs):
        assert args[:2] == ["timedatectl", "timesync-status"]
        return Result()

    monkeypatch.setattr(manifest.subprocess, "run", fake_run)

    assert measure_clock_drift_seconds() == pytest.approx(-0.000572)


def test_sonda_ntp_es_udp_y_no_sale_a_la_red_en_tests(monkeypatch) -> None:
    calls = []

    def fake_getaddrinfo(host, port, family, kind):
        calls.append((host, port, family, kind))
        raise OSError("sin DNS en tests")

    monkeypatch.setattr(manifest.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(OSError):
        manifest._drift_from_ntp()
    assert calls == [("pool.ntp.org", 123, manifest.socket.AF_INET, manifest.socket.SOCK_DGRAM)]
