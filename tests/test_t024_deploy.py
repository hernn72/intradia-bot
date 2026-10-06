from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable

import pytest

from advisor.research import t024_forward as fwd
from advisor.research import vintage as vintage_mod
from tests.test_t024_forward import CODE_SHA, DOWNLOADED, ExactProvider

ROOT = Path(__file__).resolve().parents[1]
CP = "2026-11-03"
FESTIVOS = ["2026-11-02"]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


checkpoint = _load("t024_checkpoint_deploy", "deploy/t024/checkpoint.py")
traer = _load("t024_traer_cosecha", "deploy/t024/traer_cosecha.py")
render_mod = _load("t024_render", "deploy/t024/render.py")


def _calendario_con_sha(tmp_path: Path, code_sha: str) -> Path:
    """Copia del calendario versionado con el T024_CODE_SHA que devuelve el runner de la prueba."""

    datos = json.loads((ROOT / "deploy/t024/calendario-checkpoints.json").read_text(encoding="utf-8"))
    datos["t024_code_sha"] = code_sha
    ruta = tmp_path / "calendario-prueba.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return ruta


def _cfg(tmp_path: Path, *, data_dir: Path | None = None, cal: Path | None = None, code_sha: str = CODE_SHA):
    return checkpoint.Cfg(
        repo=ROOT,
        python="python",
        data_dir=data_dir or (tmp_path / "data"),
        artefactos=tmp_path / "art",
        calendario=cal or _calendario_con_sha(tmp_path, code_sha),
    )


def _fake_runner(
    tmp_path: Path,
    *,
    apta: bool = True,
    bad_identity: bool = False,
    peticion_edit: Callable[[dict[str, object]], None] | None = None,
    bad_preflight: bool = False,
    congelar_rc: int | None = None,
):
    calls: list[list[str]] = []
    vintage_id = "a" * 64
    vintage_dir = tmp_path / "data" / vintage_id
    vintage_dir.mkdir(parents=True, exist_ok=True)
    (vintage_dir / "manifest.json").write_text("{}\n", encoding="utf-8")
    (vintage_dir / "AAPL.csv").write_text("x\n", encoding="utf-8")

    def runner(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
        calls.append(cmd)
        if cmd[:2] == ["git", "-C"]:
            return 0, "b718917000000000000000000000000000000000\n", ""
        if cmd[1:] == ["-c", checkpoint.SNIPPET_PREFLIGHT]:
            path = "/tmp/other/advisor/__init__.py" if bad_preflight else str(ROOT / "advisor" / "__init__.py")
            return 0, path + "\n", ""
        if cmd[1:] == ["-c", checkpoint.SNIPPET_IDENTIDAD]:
            return (1, "no\n", "boom") if bad_identity else (0, CODE_SHA + "\n", "")
        if cmd[3] == "peticion":
            payload = fwd.peticion_checkpoint(date.fromisoformat(CP), tuple(date.fromisoformat(f) for f in FESTIVOS)).serializable()
            if peticion_edit is not None:
                peticion_edit(payload)
            return 0, json.dumps(payload), ""
        if cmd[3] == "congelar":
            peticion = fwd.peticion_checkpoint(date.fromisoformat(CP), tuple(date.fromisoformat(f) for f in FESTIVOS))
            payload = {
                "peticion": peticion.serializable(),
                "data_vintage_id": vintage_id,
                "apta": apta,
                "motivos": [] if apta else ["parcial"],
                "succeeded": 126 if apta else 125,
                "failed": {} if apta else {"AAPL": "x"},
            }
            return (congelar_rc if congelar_rc is not None else (0 if apta else 2)), json.dumps(payload), "stderr congelar\n"
        raise AssertionError(cmd)

    return runner, calls, vintage_id


def test_calendario_versionado_valida_y_coincide_con_forward() -> None:
    cal = checkpoint.cargar_calendario(ROOT / "deploy/t024/calendario-checkpoints.json")
    assert cal.checkpoints[0].checkpoint == date(2026, 11, 3)
    assert cal.checkpoints[0].festivos == (date(2026, 11, 2),)
    assert cal.checkpoints[0].requested_end == date(2026, 10, 26)
    assert fwd.end_exclusivo(cal.checkpoints[0].checkpoint, cal.checkpoints[0].festivos) == cal.checkpoints[0].requested_end


def test_wrapper_constante_simbolos_coincide_con_forward() -> None:
    assert checkpoint.SIMBOLOS_FORWARD_SHA256 == fwd.SIMBOLOS_FORWARD_SHA256


@pytest.mark.parametrize(
    "edit",
    [
        lambda d: d.update({"zona": "Europe/London"}),
        lambda d: d["checkpoints"].append({**d["checkpoints"][0], "checkpoint": "2026-11-04"}),
        lambda d: d["checkpoints"].insert(0, {**d["checkpoints"][0], "checkpoint": "2026-12-01", "requested_end": "2026-11-24"}),
        lambda d: d["checkpoints"][0].update({"extra": 1}),
        lambda d: d["checkpoints"][0].update({"festivos": ["2026-11-02", "2026-11-02"]}),
        lambda d: d["checkpoints"][0].update({"fuente": ""}),
    ],
)
def test_calendarios_invalidos_fallan(tmp_path: Path, edit: Any) -> None:
    data = json.loads((ROOT / "deploy/t024/calendario-checkpoints.json").read_text())
    edit(data)
    path = tmp_path / "cal.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        checkpoint.cargar_calendario(path)


def test_wrapper_sin_checkpoint_no_ejecuta_comandos(tmp_path: Path) -> None:
    runner, calls, _vid = _fake_runner(tmp_path)
    assert checkpoint.ejecutar(_cfg(tmp_path), date(2026, 10, 6), runner) == 0
    assert calls == []


def test_wrapper_checkpoint_apta_y_segunda_ejecucion_no_repite(tmp_path: Path) -> None:
    runner, calls, vid = _fake_runner(tmp_path)
    cfg = _cfg(tmp_path)
    assert checkpoint.ejecutar(cfg, date(2026, 11, 3), runner) == 0
    def kind(cmd: list[str]) -> list[str]:
        if cmd[0] == "git":
            return ["git", "rev-parse"]
        if cmd[1] == "-c":
            return cmd[:3]
        return cmd[:4]

    assert [kind(cmd) for cmd in calls] == [
        ["git", "rev-parse"],
        ["python", "-c", checkpoint.SNIPPET_PREFLIGHT],
        ["python", "-c", checkpoint.SNIPPET_IDENTIDAD],
        ["python", "-m", "advisor.research.t024_forward", "peticion"],
        ["python", "-m", "advisor.research.t024_forward", "congelar"],
    ]
    estado = json.loads((cfg.artefactos / "checkpoints" / CP / "estado.json").read_text())
    assert estado["estado"] == "APTA" and estado["data_vintage_id"] == vid
    intento = json.loads((cfg.artefactos / "checkpoints" / CP / "intento.json").read_text())
    assert intento["calendario_sha256"] and intento["wrapper_sha256"]
    sums = (cfg.artefactos / "checkpoints" / CP / "SHA256SUMS").read_text()
    assert f"vintage/{vid}/manifest.json" in sums and f"vintage/{vid}/AAPL.csv" in sums
    assert "congelar.stderr.log" in sums
    assert "estado.json" in sums
    calls.clear()
    assert checkpoint.ejecutar(cfg, date(2026, 11, 3), runner) == 0
    assert calls == []


def test_wrapper_no_apta_no_reintenta(tmp_path: Path) -> None:
    runner, calls, _vid = _fake_runner(tmp_path, apta=False)
    cfg = _cfg(tmp_path)
    assert checkpoint.ejecutar(cfg, date(2026, 11, 3), runner) == 2
    assert json.loads((cfg.artefactos / "checkpoints" / CP / "estado.json").read_text())["estado"] == "NO_APTA"
    calls.clear()
    assert checkpoint.ejecutar(cfg, date(2026, 11, 3), runner) == 0
    assert calls == []


def test_wrapper_fallos_cortan_antes_de_congelar(tmp_path: Path) -> None:
    runner, calls, _vid = _fake_runner(tmp_path, bad_identity=True)
    assert checkpoint.ejecutar(_cfg(tmp_path), date(2026, 11, 3), runner) == 6
    assert not any(cmd[3:4] == ["peticion"] or cmd[3:4] == ["congelar"] for cmd in calls)
    runner, calls, _vid = _fake_runner(tmp_path / "b", peticion_edit=lambda data: data.update({"end": "2026-10-27"}))
    assert checkpoint.ejecutar(_cfg(tmp_path / "b"), date(2026, 11, 3), runner) == 7
    assert not any(cmd[3:4] == ["congelar"] for cmd in calls)
    runner, calls, _vid = _fake_runner(tmp_path / "c", bad_preflight=True)
    assert checkpoint.ejecutar(_cfg(tmp_path / "c"), date(2026, 11, 3), runner) == 6
    assert not any(cmd[3:4] == ["congelar"] for cmd in calls)


@pytest.mark.parametrize(
    "edit",
    [
        lambda data: data.update({"interval": "1wk"}),
        lambda data: data.update({"auto_adjust": True}),
        lambda data: data.update({"actions": False}),
        lambda data: data.update({"end_exclusive": False}),
        lambda data: data["symbols"].__setitem__(0, "ZZZZ"),
        lambda data: data.update({"symbols_sha256": "0" * 64}),
        lambda data: data.update({"n_symbols": 125}),
        lambda data: data.update({"start": "2021-08-31"}),
        lambda data: data.update({"end": "2026-10-27"}),
        lambda data: data.update({"festivos": []}),
    ],
)
def test_wrapper_peticion_alterada_da_error_calendario_sin_congelar(
    tmp_path: Path, edit: Callable[[dict[str, object]], None]
) -> None:
    runner, calls, _vid = _fake_runner(tmp_path, peticion_edit=edit)
    assert checkpoint.ejecutar(_cfg(tmp_path), date(2026, 11, 3), runner) == 7
    assert not any(cmd[3:4] == ["congelar"] for cmd in calls)


def test_intento_sin_estado_lock_perdido_y_horizonte(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _cfg(tmp_path)
    cp_dir = cfg.artefactos / "checkpoints" / CP
    cp_dir.mkdir(parents=True)
    (cp_dir / "intento.json").write_text("{}\n")
    runner, calls, _vid = _fake_runner(tmp_path)
    assert checkpoint.ejecutar(cfg, date(2026, 11, 3), runner) == 5
    assert calls == []
    assert json.loads((cp_dir / "estado.json").read_text())["estado"] == "INTERRUMPIDO"

    def busy(*_args: Any, **_kwargs: Any) -> None:
        raise BlockingIOError

    with monkeypatch.context() as m:
        m.setattr(checkpoint.fcntl, "flock", busy)
        assert checkpoint.ejecutar(_cfg(tmp_path / "lock"), date(2026, 11, 3), runner) == 75

    runner, calls, _vid = _fake_runner(tmp_path / "lost")
    assert checkpoint.ejecutar(_cfg(tmp_path / "lost"), date(2026, 11, 4), runner) == 4
    assert calls == []

    runner, calls, _vid = _fake_runner(tmp_path / "horizon")
    cfg_horizon = _cfg(tmp_path / "horizon")
    done = cfg_horizon.artefactos / "checkpoints" / CP
    done.mkdir(parents=True)
    (done / "estado.json").write_text(json.dumps({"checkpoint": CP, "estado": "APTA"}), encoding="utf-8")
    assert checkpoint.ejecutar(cfg_horizon, date(2026, 11, 21), runner) == 3
    assert calls == []


def test_estado_imprime_pendiente(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert checkpoint.estado(_cfg(tmp_path), date(2026, 10, 6)) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["checkpoints"][0]["estado"] == "PENDIENTE"


def test_estado_muestra_sin_estado_si_hay_directorio_sin_estado_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg = _cfg(tmp_path)
    (cfg.artefactos / "checkpoints" / CP).mkdir(parents=True)
    assert checkpoint.estado(cfg, date(2026, 11, 3)) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["checkpoints"][0]["estado"] == "SIN_ESTADO"


def test_parser_ejecutar_rechaza_hoy() -> None:
    with pytest.raises(SystemExit):
        checkpoint.build_parser().parse_args(["ejecutar", "--artefactos", "x", "--data-dir", "y", "--hoy", CP])


def test_error_congelacion_escribe_hashes_y_no_reintenta(tmp_path: Path) -> None:
    runner, calls, vid = _fake_runner(tmp_path, apta=False, congelar_rc=1)
    cfg = _cfg(tmp_path)
    assert checkpoint.ejecutar(cfg, date(2026, 11, 3), runner) == 9
    cp_dir = cfg.artefactos / "checkpoints" / CP
    estado = json.loads((cp_dir / "estado.json").read_text())
    assert estado["estado"] == "ERROR_CONGELACION"
    sums = (cp_dir / "SHA256SUMS").read_text()
    assert "congelar.stderr.log" in sums
    assert "estado.json" in sums
    assert f"vintage/{vid}/manifest.json" in sums
    calls.clear()
    assert checkpoint.ejecutar(cfg, date(2026, 11, 3), runner) == 5
    assert calls == []


def test_wrapper_no_contiene_rutas_automaticas_prohibidas(tmp_path: Path) -> None:
    text = (ROOT / "deploy/t024/checkpoint.py").read_text(encoding="utf-8")
    ast.parse(text)
    for pattern in ("registrar", "capturar", "ejecutar_mirada", "construir_resultado", r"\bd[12]_"):
        assert re.search(pattern, text) is None
    runner, calls, _vid = _fake_runner(tmp_path)
    checkpoint.ejecutar(_cfg(tmp_path), date(2026, 11, 3), runner)
    joined = "\n".join(" ".join(cmd) for cmd in calls)
    assert "registrar" not in joined and "capturar" not in joined


def test_runner_realista_y_verificador_detecta_tampering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vintage_mod, "_provider_version", lambda: "0.0-test")

    cfg, vid = _run_realistic_checkpoint(tmp_path, code_sha=CODE_SHA)
    artefactos = cfg.artefactos / "checkpoints" / CP
    ok, informe = traer.verificar(checkpoint=CP, artefactos=artefactos, vintage_dir=tmp_path / "data" / vid, code_sha_esperado=CODE_SHA)
    assert ok, informe
    extra = tmp_path / "data" / vid / "extra.txt"
    extra.write_text("extra\n", encoding="utf-8")
    ok, _informe = traer.verificar(checkpoint=CP, artefactos=artefactos, vintage_dir=tmp_path / "data" / vid, code_sha_esperado=CODE_SHA)
    assert not ok
    extra.unlink()
    artefacto_extra = artefactos / "extra.txt"
    artefacto_extra.write_text("extra\n", encoding="utf-8")
    ok, _informe = traer.verificar(checkpoint=CP, artefactos=artefactos, vintage_dir=tmp_path / "data" / vid, code_sha_esperado=CODE_SHA)
    assert not ok
    artefacto_extra.unlink()
    estado = artefactos / "estado.json"
    estado_original = estado.read_text(encoding="utf-8")
    estado.write_text(estado_original.replace('"APTA"', '"NO_APTA"', 1), encoding="utf-8")
    ok, _informe = traer.verificar(checkpoint=CP, artefactos=artefactos, vintage_dir=tmp_path / "data" / vid, code_sha_esperado=CODE_SHA)
    assert not ok
    estado.write_text(estado_original, encoding="utf-8")
    identidad = artefactos / "identidad.txt"
    original_identidad = identidad.read_text(encoding="utf-8")
    identidad.write_text("c" * 40 + "\n", encoding="utf-8")
    ok, _informe = traer.verificar(checkpoint=CP, artefactos=artefactos, vintage_dir=tmp_path / "data" / vid, code_sha_esperado=CODE_SHA)
    assert not ok
    identidad.write_text(original_identidad, encoding="utf-8")
    csv = tmp_path / "data" / vid / "AAPL.csv"
    csv.write_text(csv.read_text().replace("100", "101", 1), encoding="utf-8")
    ok, _informe = traer.verificar(checkpoint=CP, artefactos=artefactos, vintage_dir=tmp_path / "data" / vid, code_sha_esperado=CODE_SHA)
    assert not ok
    csv.write_text(csv.read_text().replace("101", "100", 1), encoding="utf-8")
    peticion = artefactos / "peticion.json"
    peticion.write_text(peticion.read_text().replace("2026-10-26", "2026-10-27", 1), encoding="utf-8")
    ok, _informe = traer.verificar(checkpoint=CP, artefactos=artefactos, vintage_dir=tmp_path / "data" / vid, code_sha_esperado=CODE_SHA)
    assert not ok
    peticion.write_text(peticion.read_text().replace("2026-10-27", "2026-10-26", 1), encoding="utf-8")
    ok, _informe = traer.verificar(checkpoint=CP, artefactos=artefactos, vintage_dir=tmp_path / "data" / vid, code_sha_esperado="c" * 40)
    assert not ok


def _run_realistic_checkpoint(tmp_path: Path, *, code_sha: str):
    def runner(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
        if cmd[:2] == ["git", "-C"]:
            return 0, "b718917000000000000000000000000000000000\n", ""
        if cmd[1:] == ["-c", checkpoint.SNIPPET_PREFLIGHT]:
            return 0, str(ROOT / "advisor" / "__init__.py") + "\n", ""
        if cmd[1:] == ["-c", checkpoint.SNIPPET_IDENTIDAD]:
            return 0, code_sha + "\n", ""
        if cmd[3] == "peticion":
            payload = fwd.peticion_checkpoint(date.fromisoformat(CP), tuple(date.fromisoformat(f) for f in FESTIVOS)).serializable()
            return 0, json.dumps(payload, sort_keys=True), ""
        if cmd[3] == "congelar":
            peticion = fwd.peticion_checkpoint(date.fromisoformat(CP), tuple(date.fromisoformat(f) for f in FESTIVOS))
            cosecha = fwd.congelar_checkpoint(
                peticion,
                ExactProvider(),
                root_dir=tmp_path / "data",
                universe_vintage=fwd.UNIVERSE_VINTAGE_ID,
                t024_code_sha=code_sha,
                hoy=date.fromisoformat(CP),
                downloaded_at=DOWNLOADED,
            )
            return 0, json.dumps(cosecha.serializable(), sort_keys=True), ""
        raise AssertionError(cmd)

    cfg = _cfg(tmp_path, code_sha=code_sha)
    assert checkpoint.ejecutar(cfg, date(2026, 11, 3), runner) == 0
    estado = json.loads((cfg.artefactos / "checkpoints" / CP / "estado.json").read_text())
    vid = estado["data_vintage_id"]
    return cfg, vid


def _copytree_contents(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def _local_rsync_runner(calls: list[list[str]]) -> traer.Runner:
    def runner(cmd: list[str]) -> None:
        calls.append(cmd)
        src = cmd[-2]
        dst = Path(cmd[-1])
        assert ":" in src
        src_path = Path(src.split(":", 1)[1].rstrip("/"))
        _copytree_contents(src_path, dst)

    return runner


def _copiar_args(tmp_path: Path, *, data_dir: Path) -> argparse.Namespace:
    return argparse.Namespace(
        pi="fer@pi",
        ssh_key=None,
        checkpoint=CP,
        destino_artefactos=tmp_path / "pc" / "pi",
        data_dir=data_dir,
        pi_artefactos=str(tmp_path / "pi" / "artefactos"),
        pi_data_dir=str(tmp_path / "pi" / "data"),
    )


def _preparar_pi_desde_captura(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[argparse.Namespace, str, list[list[str]]]:
    monkeypatch.setattr(vintage_mod, "_provider_version", lambda: "0.0-test")
    sidecar_sha = (ROOT / traer.CODE_SHA_SIDECAR).read_text(encoding="utf-8").strip()
    cfg, vid = _run_realistic_checkpoint(tmp_path / "run", code_sha=sidecar_sha)
    args = _copiar_args(tmp_path, data_dir=tmp_path / "pc" / "data" / "vintages")
    pi_cp = Path(args.pi_artefactos) / "checkpoints" / CP
    pi_vintage = Path(args.pi_data_dir) / vid
    shutil.copytree(cfg.artefactos / "checkpoints" / CP, pi_cp)
    shutil.copytree(tmp_path / "run" / "data" / vid, pi_vintage)
    calls: list[list[str]] = []
    return args, vid, calls


def test_copiar_materializa_vintage_y_destino_existente_identico_no_toca(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    args, vid, calls = _preparar_pi_desde_captura(tmp_path, monkeypatch)
    assert traer.copiar(args, runner=_local_rsync_runner(calls)) == 0
    final = args.data_dir / vid
    assert traer._dirs_byte_iguales(Path(args.pi_data_dir) / vid, final)
    manifest_mtime = (final / "manifest.json").stat().st_mtime_ns
    assert traer.copiar(args, runner=_local_rsync_runner(calls)) == 0
    assert (final / "manifest.json").stat().st_mtime_ns == manifest_mtime


def test_copiar_destino_existente_distinto_falla_aunque_mismo_tamano_y_mtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    args, vid, calls = _preparar_pi_desde_captura(tmp_path, monkeypatch)
    assert traer.copiar(args, runner=_local_rsync_runner(calls)) == 0
    final_csv = args.data_dir / vid / "AAPL.csv"
    original = final_csv.read_bytes()
    final_csv.write_bytes(original.replace(b"100", b"101", 1))
    src_stat = (Path(args.pi_data_dir) / vid / "AAPL.csv").stat()
    os.utime(final_csv, ns=(src_stat.st_atime_ns, src_stat.st_mtime_ns))
    with pytest.raises(SystemExit):
        traer.copiar(args, runner=_local_rsync_runner(calls))


def test_copiar_verificacion_fallida_no_crea_destinos_ni_deja_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, vid, calls = _preparar_pi_desde_captura(tmp_path, monkeypatch)
    (Path(args.pi_artefactos) / "checkpoints" / CP / "extra.txt").write_text("extra\n", encoding="utf-8")
    assert traer.copiar(args, runner=_local_rsync_runner(calls)) == 1
    assert not args.destino_artefactos.exists()
    assert not (args.data_dir / vid).exists()
    assert not list(args.destino_artefactos.parent.glob(".t024-staging-*"))
    assert not list(args.data_dir.parent.glob(".t024-staging-*"))


def test_copiar_estado_no_apta_no_copia_vintage(tmp_path: Path) -> None:
    args = _copiar_args(tmp_path, data_dir=tmp_path / "pc" / "data" / "vintages")
    pi_cp = Path(args.pi_artefactos) / "checkpoints" / CP
    pi_cp.mkdir(parents=True)
    vid = "a" * 64
    (pi_cp / "estado.json").write_text(json.dumps({"checkpoint": CP, "estado": "NO_APTA", "data_vintage_id": vid}), encoding="utf-8")
    calls: list[list[str]] = []
    with pytest.raises(SystemExit):
        traer.copiar(args, runner=_local_rsync_runner(calls))
    assert len(calls) == 1
    assert not (args.data_dir / vid).exists()


def test_systemd_templates_render_installer_y_sin_palabras_prohibidas(tmp_path: Path) -> None:
    valores = {
        "T024_USER": "fer",
        "T024_REPO_DIR": "/home/fer/intradia-t024",
        "T024_PYTHON": "/home/fer/intradia-bot/.venv/bin/python",
        "T024_DATA_DIR": "/home/fer/intradia-bot/data/vintages",
        "T024_ARTEFACTOS_DIR": "/home/fer/t024-forward",
        "T024_LOG": "/home/fer/t024-forward/logs/systemd.log",
    }
    service_t = (ROOT / "deploy/t024/systemd/intradia-t024-checkpoint.service").read_text()
    timer_t = (ROOT / "deploy/t024/systemd/intradia-t024-checkpoint.timer").read_text()
    service = render_mod.render(service_t, valores)
    timer = render_mod.render(timer_t, valores)
    assert "Type=oneshot" in service
    assert "User=fer" in service
    assert "WorkingDirectory=/home/fer/intradia-t024" in service
    assert "deploy/t024/checkpoint.py ejecutar" in service
    assert "EnvironmentFile" not in service
    assert "TZ=Atlantic/Canary" not in service
    assert "StandardOutput=append:/home/fer/t024-forward/logs/systemd.log" in service
    assert "OnCalendar=*-*-* 12:00:00 Atlantic/Canary" in timer
    assert "Persistent=true" in timer
    with pytest.raises(ValueError):
        render_mod.render("@T024_USER@ @T024_MISSING@", {"T024_USER": "fer"})
    for text in (service_t, timer_t, (ROOT / "deploy/t024/instalar.sh").read_text()):
        assert "registrar" not in text and "capturar" not in text
    instalar = (ROOT / "deploy/t024/instalar.sh").read_text()
    assert 'id -gn "${T024_USER}"' in instalar
    assert "deploy/t024/checkpoint.py" in instalar
    assert "git -C \"${T024_REPO_DIR}\" diff --quiet \"${T024_CODE_SHA}\" HEAD" in instalar
    result = subprocess.run(["bash", "-n", str(ROOT / "deploy/t024/instalar.sh")], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# Segunda copia de cada cosecha, fuera del checkout (regla posterior al incidente 2026-10-06)
# ---------------------------------------------------------------------------


def test_apta_deja_segunda_copia_identica_fuera_del_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vintage_mod, "_provider_version", lambda: "0.0-test")
    cfg, vid = _run_realistic_checkpoint(tmp_path, code_sha=CODE_SHA)
    estado = json.loads((cfg.artefactos / "checkpoints" / CP / "estado.json").read_text())
    copia = cfg.artefactos / "copias" / "vintages" / vid
    assert estado["estado"] == "APTA"
    assert estado["segunda_copia"] == {"ruta": str(copia), "verificada": True, "ficheros": 127}
    original = tmp_path / "data" / vid
    assert sorted(p.name for p in copia.iterdir()) == sorted(p.name for p in original.iterdir())
    for fichero in original.iterdir():
        assert (copia / fichero.name).read_bytes() == fichero.read_bytes()
    assert not [p for p in copia.parent.iterdir() if p.name.startswith(".t024-staging-")]


def test_segunda_copia_dentro_del_repo_o_del_data_dir_se_niega(tmp_path: Path) -> None:
    origen = tmp_path / "data" / ("a" * 64)
    origen.mkdir(parents=True)
    (origen / "manifest.json").write_text("{}\n", encoding="utf-8")
    prohibida_repo = ROOT / "data" / "no-se-crea-nunca"
    for copia_dir in (prohibida_repo, tmp_path / "data" / "copias", tmp_path):
        with pytest.raises(ValueError):
            checkpoint.segunda_copia(tmp_path / "data", copia_dir, "a" * 64, repo=ROOT)
    assert not prohibida_repo.exists()


def test_segunda_copia_existente_distinta_da_error_copia_sin_tocarla(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner, _calls, vid = _fake_runner(tmp_path)
    cfg = _cfg(tmp_path)
    previa = cfg.copia() / vid
    previa.mkdir(parents=True)
    (previa / "manifest.json").write_text("otra cosa\n", encoding="utf-8")
    assert checkpoint.ejecutar(cfg, date(2026, 11, 3), runner) == checkpoint.RC_COPIA
    estado = json.loads((cfg.artefactos / "checkpoints" / CP / "estado.json").read_text())
    assert estado["estado"] == "ERROR_COPIA" and estado["segunda_copia"]["verificada"] is False
    assert (previa / "manifest.json").read_text(encoding="utf-8") == "otra cosa\n"
    calls: list[list[str]] = []
    assert checkpoint.ejecutar(cfg, date(2026, 11, 3), lambda c, w: calls.append(c) or (0, "", "")) == checkpoint.RC_INTERRUMPIDO
    assert calls == []


def test_no_apta_tambien_deja_segunda_copia(tmp_path: Path) -> None:
    runner, _calls, vid = _fake_runner(tmp_path, apta=False)
    cfg = _cfg(tmp_path)
    assert checkpoint.ejecutar(cfg, date(2026, 11, 3), runner) == 2
    estado = json.loads((cfg.artefactos / "checkpoints" / CP / "estado.json").read_text())
    assert estado["estado"] == "NO_APTA" and estado["segunda_copia"]["verificada"] is True
    assert (cfg.copia() / vid / "AAPL.csv").read_text() == "x\n"



def _origen_minimo(tmp_path: Path) -> tuple[Path, str]:
    vid = "b" * 64
    origen = tmp_path / "data" / vid
    origen.mkdir(parents=True)
    (origen / "manifest.json").write_text("{}\n", encoding="utf-8")
    (origen / "AAPL.csv").write_text("1\n", encoding="utf-8")
    return tmp_path / "data", vid


def test_segunda_copia_por_enlace_hacia_el_repo_se_niega_sin_crear_nada(tmp_path: Path) -> None:
    data_dir, vid = _origen_minimo(tmp_path)
    repo_falso = tmp_path / "repo"
    repo_falso.mkdir()
    enlace = tmp_path / "enlace-al-repo"
    enlace.symlink_to(repo_falso)
    with pytest.raises(ValueError):
        checkpoint.segunda_copia(data_dir, enlace / "copias" / "vintages", vid, repo=repo_falso)
    assert list(repo_falso.iterdir()) == []


def test_segunda_copia_previa_como_enlace_o_mismo_inodo_no_cuenta(tmp_path: Path) -> None:
    data_dir, vid = _origen_minimo(tmp_path)
    copias = tmp_path / "copias"
    copias.mkdir()
    (copias / vid).symlink_to(data_dir / vid)
    with pytest.raises(ValueError):
        checkpoint.segunda_copia(data_dir, copias, vid, repo=ROOT)
    copias2 = tmp_path / "copias2"
    (copias2 / vid).mkdir(parents=True)
    for fichero in (data_dir / vid).iterdir():
        os.link(fichero, copias2 / vid / fichero.name)
    with pytest.raises(ValueError, match="inodo"):
        checkpoint.segunda_copia(data_dir, copias2, vid, repo=ROOT)


def test_segunda_copia_nueva_tiene_inodos_propios(tmp_path: Path) -> None:
    data_dir, vid = _origen_minimo(tmp_path)
    resultado = checkpoint.segunda_copia(data_dir, tmp_path / "copias", vid, repo=ROOT)
    assert resultado["verificada"] is True and resultado["ficheros"] == 2
    for fichero in (data_dir / vid).iterdir():
        copia = tmp_path / "copias" / vid / fichero.name
        assert copia.read_bytes() == fichero.read_bytes()
        assert os.stat(copia).st_ino != os.stat(fichero).st_ino
    assert sorted(p.name for p in (tmp_path / "copias").iterdir()) == [vid]


def test_copiar_reverifica_lo_promovido_y_retira_si_cambio_el_staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    args, vid, calls = _preparar_pi_desde_captura(tmp_path, monkeypatch)
    promover_real = traer.borrado_seguro.promover_sin_pisar

    def promover_tras_manipular(staging: Path, destino: Path) -> None:
        # Cambio en staging después de la primera verificación y antes de promover.
        csv = Path(staging) / "AAPL.csv"
        if csv.exists():
            csv.write_bytes(csv.read_bytes().replace(b"100", b"109", 1))
        promover_real(staging, destino)

    monkeypatch.setattr(traer.borrado_seguro, "promover_sin_pisar", promover_tras_manipular)
    assert traer.copiar(args, runner=_local_rsync_runner(calls)) == 1
    assert not (args.data_dir / vid).exists()
    assert not args.destino_artefactos.exists()
    assert not list(args.data_dir.glob(".t024-staging-*")) and not list(args.data_dir.parent.glob(".t024-staging-*"))



# ---------------------------------------------------------------------------
# Ronda 2 de Codex (sobre ac975eb), tratada tras el incidente
# ---------------------------------------------------------------------------


def test_calendario_versionado_declara_el_sha_del_sidecar() -> None:
    cal = checkpoint.cargar_calendario(ROOT / "deploy/t024/calendario-checkpoints.json")
    assert cal.code_sha == (ROOT / traer.CODE_SHA_SIDECAR).read_text(encoding="utf-8").strip()
    assert cal.code_sha == "1a697c3fa2ab76ddfcf567c2ef3f5ab56492eaf0"


@pytest.mark.parametrize("valor", ["", "1A697C3FA2AB76DDFCF567C2EF3F5AB56492EAF0", "1a697c3", None])
def test_calendario_con_sha_invalido_falla(tmp_path: Path, valor: Any) -> None:
    datos = json.loads((ROOT / "deploy/t024/calendario-checkpoints.json").read_text(encoding="utf-8"))
    datos["t024_code_sha"] = valor
    ruta = tmp_path / "cal.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(ValueError):
        checkpoint.cargar_calendario(ruta)


def test_identidad_distinta_del_calendario_no_gasta_el_intento_en_congelar(tmp_path: Path) -> None:
    runner, calls, _vid = _fake_runner(tmp_path)
    cfg = _cfg(tmp_path, code_sha="c" * 40)
    assert checkpoint.ejecutar(cfg, date(2026, 11, 3), runner) == checkpoint.RC_PREFLIGHT
    assert not any(len(cmd) > 3 and cmd[3] in {"peticion", "congelar"} for cmd in calls)
    estado = json.loads((cfg.artefactos / "checkpoints" / CP / "estado.json").read_text())
    assert estado["estado"] == "ERROR_IDENTIDAD" and estado["esperado"] == "c" * 40 and estado["obtenido"] == CODE_SHA


@pytest.mark.parametrize(
    "campo,valor",
    [("festivos", []), ("end_exclusive", False), ("n_symbols", 125), ("start", "2021-08-31"), ("interval", "1wk")],
)
def test_verificar_exige_la_peticion_completa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, campo: str, valor: Any) -> None:
    monkeypatch.setattr(vintage_mod, "_provider_version", lambda: "0.0-test")
    cfg, vid = _run_realistic_checkpoint(tmp_path, code_sha=CODE_SHA)
    artefactos = cfg.artefactos / "checkpoints" / CP
    peticion = artefactos / "peticion.json"
    datos = json.loads(peticion.read_text(encoding="utf-8"))
    datos[campo] = valor
    peticion.write_text(json.dumps(datos, sort_keys=True), encoding="utf-8")
    # Se recalcula SHA256SUMS como haría quien manipulara la copia: la comprobación tiene que ser de contenido.
    sums = artefactos / "SHA256SUMS"
    lineas = [
        f"{checkpoint.sha256_path(peticion)}  peticion.json" if linea.endswith("  peticion.json") else linea
        for linea in sums.read_text(encoding="utf-8").splitlines()
    ]
    sums.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    ok, informe = traer.verificar(checkpoint=CP, artefactos=artefactos, vintage_dir=tmp_path / "data" / vid, code_sha_esperado=CODE_SHA)
    assert not ok and any(campo in e or "símbolos" in e for e in informe["errores"]), informe


def test_verificar_exige_que_sha256sums_nombre_el_vintage_verificado(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vintage_mod, "_provider_version", lambda: "0.0-test")
    cfg, vid = _run_realistic_checkpoint(tmp_path, code_sha=CODE_SHA)
    artefactos = cfg.artefactos / "checkpoints" / CP
    sums = artefactos / "SHA256SUMS"
    sums.write_text(sums.read_text(encoding="utf-8").replace(f"vintage/{vid}/", f"vintage/{'f' * 64}/"), encoding="utf-8")
    ok, informe = traer.verificar(checkpoint=CP, artefactos=artefactos, vintage_dir=tmp_path / "data" / vid, code_sha_esperado=CODE_SHA)
    assert not ok and any("otro vintage" in e for e in informe["errores"]), informe


def test_instalador_lee_el_sha_del_calendario_y_valida_el_env() -> None:
    instalar = (ROOT / "deploy/t024/instalar.sh").read_text(encoding="utf-8")
    assert "1a697c3" not in instalar
    assert "calendario-checkpoints.json" in instalar and '["t024_code_sha"]' in instalar
    assert '-L "${ENV_FILE}"' in instalar and "-perm /022" in instalar and "stat -c '%u'" in instalar



# ---------------------------------------------------------------------------
# Verificación global de Codex (sobre 75aff57)
# ---------------------------------------------------------------------------


def test_verificar_fija_la_lista_de_simbolos_del_contrato(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vintage_mod, "_provider_version", lambda: "0.0-test")
    cfg, vid = _run_realistic_checkpoint(tmp_path, code_sha=CODE_SHA)
    artefactos = cfg.artefactos / "checkpoints" / CP
    peticion = artefactos / "peticion.json"
    datos = json.loads(peticion.read_text(encoding="utf-8"))
    otros = sorted(f"X{i:03d}" for i in range(126))
    datos["symbols"] = otros
    datos["symbols_sha256"] = hashlib.sha256("\n".join(otros).encode()).hexdigest()  # autoconsistente
    peticion.write_text(json.dumps(datos, sort_keys=True), encoding="utf-8")
    ok, informe = traer.verificar(checkpoint=CP, artefactos=artefactos, vintage_dir=tmp_path / "data" / vid, code_sha_esperado=CODE_SHA)
    assert not ok and any("lista congelada" in e for e in informe["errores"]), informe


def test_checkpoint_pasado_con_directorio_sin_intento_queda_perdido(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg = _cfg(tmp_path)
    (cfg.artefactos / "checkpoints" / CP).mkdir(parents=True)  # caída justo tras crear el directorio
    calls: list[list[str]] = []
    assert checkpoint.ejecutar(cfg, date(2026, 11, 4), lambda c, w: calls.append(c) or (0, "", "")) == checkpoint.RC_PERDIDO
    assert calls == []
    assert json.loads((cfg.artefactos / "checkpoints" / CP / "estado.json").read_text())["estado"] == "PERDIDO"


def test_checkpoint_pasado_con_intento_sin_estado_queda_interrumpido(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg = _cfg(tmp_path)
    cp_dir = cfg.artefactos / "checkpoints" / CP
    cp_dir.mkdir(parents=True)
    (cp_dir / "intento.json").write_text("{}\n", encoding="utf-8")
    assert checkpoint.estado(cfg, date(2026, 11, 4)) == 0
    assert json.loads(capsys.readouterr().out)["checkpoints"][0]["estado"] == "INTERRUMPIDO"
    calls: list[list[str]] = []
    checkpoint.ejecutar(cfg, date(2026, 11, 4), lambda c, w: calls.append(c) or (0, "", ""))
    assert calls == []
    assert json.loads((cp_dir / "estado.json").read_text())["estado"] == "INTERRUMPIDO"
