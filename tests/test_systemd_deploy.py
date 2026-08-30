"""Plantillas systemd versionadas y comprobación de desfase."""

from __future__ import annotations

from pathlib import Path

from advisor.deploy.systemd import UNIT_NAMES, find_systemd_drift, write_rendered_units


def _env_file(tmp_path: Path) -> Path:
    path = tmp_path / "systemd.env"
    path.write_text(
        "\n".join(
            [
                "INTRADIA_BOT_USER=fer",
                "INTRADIA_BOT_DIR=/home/fer/intradia-bot",
                "INTRADIA_BOT_PYTHON=/home/fer/intradia-bot/.venv/bin/python",
                "INTRADIA_BOT_ENV_FILE=/home/fer/intradia-bot/.env",
                "INTRADIA_BOT_ANALIZAR_LOG=/home/fer/intradia-bot/logs/analizar.log",
                "INTRADIA_BOT_EVENT_LOG=/home/fer/intradia-bot/logs/pasada-evento.log",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_render_systemd_sustituye_rutas_sin_clavarlas_en_las_plantillas(tmp_path) -> None:
    env = _env_file(tmp_path)
    output = tmp_path / "installed"

    write_rendered_units(output_dir=output, config_env=env, event_time="22:30")

    service = (output / "intradia-bot.service").read_text(encoding="utf-8")
    assert "User=fer" in service
    assert "WorkingDirectory=/home/fer/intradia-bot" in service
    assert "StandardOutput=append:/home/fer/intradia-bot/logs/analizar.log" in service
    assert "StandardError=append:/home/fer/intradia-bot/logs/analizar.log" in service
    assert "@INTRADIA_BOT_USER@" not in service
    event_service = (output / "intradia-bot-event.service").read_text(encoding="utf-8")
    assert "StandardOutput=append:/home/fer/intradia-bot/logs/pasada-evento.log" in event_service
    assert "StandardOutput=append:/home/fer/intradia-bot/logs/analizar.log" not in event_service
    assert "OnCalendar=Mon..Fri 22:30" in (output / "intradia-bot-event.timer").read_text(encoding="utf-8")


def test_check_systemd_drift_ignora_placeholders_resueltos_y_detecta_diferencias(tmp_path) -> None:
    env = _env_file(tmp_path)
    installed = tmp_path / "installed"
    write_rendered_units(output_dir=installed, config_env=env, event_time="22:30")

    assert find_systemd_drift(config_env=env, installed_dir=installed, event_time="22:30") == []

    timer_path = installed / "intradia-bot.timer"
    timer_path.write_text(
        timer_path.read_text(encoding="utf-8").replace("OnCalendar=Mon..Fri 14:30", "OnCalendar=Mon..Fri 14:45"),
        encoding="utf-8",
    )

    assert find_systemd_drift(config_env=env, installed_dir=installed, event_time="22:30") == [
        "intradia-bot.timer: difiere de la plantilla resuelta"
    ]


def test_todas_las_unidades_esperadas_estan_versionadas() -> None:
    for name in UNIT_NAMES:
        assert (Path("deploy/systemd") / name).is_file()
