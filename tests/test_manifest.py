"""Manifiesto de ejecución."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone

import pytest

from advisor.config import load_config
from advisor.run import manifest
from advisor.run.manifest import (
    build_run_manifest,
    config_hash,
    file_content_hash,
    git_dirty,
    measure_clock_drift_seconds,
)
from advisor.universe.loader import load_universe
from advisor.universe.vintage import universe_vintage_id, universe_vintage_payload
from tests.test_universe_vintage import REAL_UNIVERSE_VINTAGE


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


def test_manifest_registra_hash_de_exchange_overrides(monkeypatch, tmp_path) -> None:
    overrides = tmp_path / "exchange_overrides.yaml"
    overrides.write_text("XKRX:\n  cierres_adicionales: []\n  aperturas_forzadas: []\n", encoding="utf-8")
    monkeypatch.setattr(manifest, "EXCHANGE_OVERRIDES_PATH", overrides)
    monkeypatch.setattr(manifest, "measure_clock_drift_seconds", lambda: None)
    config = load_config("config.yaml")

    run = build_run_manifest(
        command="analizar",
        config=config,
        universe=load_universe("universe.yaml"),
        schema_version=1,
        timestamp=datetime(2026, 9, 16, tzinfo=timezone.utc),
    )

    assert run.provider_versions["exchange_overrides_hash"] == file_content_hash(overrides)


def test_manifest_git_dirty(tmp_path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("uno\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True, capture_output=True)
    tracked.write_text("dos\n", encoding="utf-8")

    assert git_dirty(tmp_path).value is True


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

    assert git_dirty(tmp_path).value is False


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


def test_git_dirty_es_null_cuando_git_status_falla(tmp_path) -> None:
    """Un `git status` que no se puede ejecutar no significa «árbol limpio» (INV-16)."""

    sin_repo = tmp_path / "no-es-un-repo"
    sin_repo.mkdir()

    estado = git_dirty(sin_repo)

    assert estado.value is None
    assert estado.reason is not None and "git status" in estado.reason


def test_config_hash_no_cambia_con_las_rutas(tmp_path) -> None:
    """El portátil y la Pi tienen la misma configuración lógica con rutas distintas."""

    portatil = tmp_path / "portatil.yaml"
    pi = tmp_path / "pi.yaml"
    otra_config = tmp_path / "otra.yaml"
    comun = """
base_currency: EUR
horizontes:
  swing:
    interval: 1d
    period: 1y
    min_bars: 120
request_min_interval_seconds: 1.0
"""
    portatil.write_text(
        comun + "db_path: intradia.db\nuniverse_path: universe.yaml\n",
        encoding="utf-8",
    )
    pi.write_text(
        comun + "db_path: /home/fer/intradia-bot/intradia.db\nuniverse_path: /home/fer/intradia-bot/universe.yaml\n",
        encoding="utf-8",
    )
    otra_config.write_text(
        comun.replace("min_bars: 120", "min_bars: 121") + "db_path: intradia.db\n",
        encoding="utf-8",
    )

    assert config_hash(load_config(portatil)) == config_hash(load_config(pi))
    # Y sigue distinguiendo lo que sí decide: un umbral distinto es otra config.
    assert config_hash(load_config(portatil)) != config_hash(load_config(otra_config))


def test_grupos_declara_el_vintage_del_subconjunto(monkeypatch) -> None:
    """Una pasada sobre `europa` no puede declarar el universo entero (INV-19)."""

    monkeypatch.setattr(manifest, "measure_clock_drift_seconds", lambda: None)
    config = load_config("config.yaml")
    universe = load_universe("universe.yaml")

    def construir(groups):
        return build_run_manifest(
            command="analizar",
            config=config,
            universe=universe,
            schema_version=5,
            timestamp=datetime(2026, 9, 18, tzinfo=timezone.utc),
            groups=groups,
        )

    completo = construir(None)
    europa = construir(["europa"])
    europa_otra_vez = construir(["europa"])

    assert europa.universe_vintage_id != completo.universe_vintage_id
    assert europa.universe_vintage_id == europa_otra_vez.universe_vintage_id
    assert europa.groups == ("europa",)
    assert completo.groups is None
    # El vintage del subconjunto es el de sus activos, no un hash nuevo inventado:
    # coincide con el que da la lista filtrada por su cuenta.
    assert europa.universe_vintage_id == universe_vintage_id(universe, ["europa"])
    assert len(universe.analizables(["europa"])) < len(universe.analizables())


def test_el_vintage_sin_grupos_no_cambia() -> None:
    """Guarda de D-23: la lista completa sigue dando el identificador publicado.

    Comparado contra la constante real de D-31, no contra la propia función: un
    test que se compara consigo mismo pasaría aunque el hash hubiera cambiado.
    """

    universe = load_universe("universe.yaml")

    assert universe_vintage_id(universe) == REAL_UNIVERSE_VINTAGE
    assert universe_vintage_id(universe, None) == REAL_UNIVERSE_VINTAGE
    assert universe_vintage_payload(universe) == universe_vintage_payload(universe, None)
