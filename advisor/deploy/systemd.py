"""Render y comprobación de desfase de unidades systemd.

Las unidades versionadas son plantillas: contienen las decisiones operativas,
pero no rutas ni usuario de una máquina concreta. Para comparar producción
contra el repo se renderiza la plantilla con el mismo fichero externo que usa
la instalación y se compara el resultado.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

UNIT_NAMES = (
    "intradia-bot.service",
    "intradia-bot.timer",
    "intradia-bot-event.service",
    "intradia-bot-event.timer",
)

DEFAULT_CONFIG_ENV = "/etc/intradia-bot/systemd.env"
DEFAULT_SYSTEMD_DIR = "/etc/systemd/system"
DEFAULT_TEMPLATE_DIR = "deploy/systemd"


def load_env_file(path: str | Path) -> Dict[str, str]:
    """Lee asignaciones KEY=VALUE sencillas, sin ejecutar código shell."""

    env_path = Path(path)
    values: Dict[str, str] = {}
    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError as exc:
        reason = exc.strerror or str(exc)
        raise ValueError(
            f"{env_path}: no se puede leer el fichero de entorno ({reason}). "
            "Comprueba que existe y que el usuario que ejecuta verificar-systemd "
            "tiene permiso de lectura; ajusta la ruta o los permisos (0644 si procede)."
        ) from exc

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"{env_path}: línea inválida: {raw_line!r}")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if not key:
            raise ValueError(f"{env_path}: variable sin nombre")
        values[key] = value
    return values


def render_units(
    *,
    config_env: str | Path = DEFAULT_CONFIG_ENV,
    template_dir: str | Path = DEFAULT_TEMPLATE_DIR,
    event_time: Optional[str] = None,
) -> Dict[str, str]:
    """Renderiza las plantillas versionadas con rutas externas."""

    values = load_env_file(config_env)
    required = (
        "INTRADIA_BOT_USER",
        "INTRADIA_BOT_DIR",
        "INTRADIA_BOT_PYTHON",
        "INTRADIA_BOT_ENV_FILE",
        "INTRADIA_BOT_ANALIZAR_LOG",
        "INTRADIA_BOT_EVENT_LOG",
    )
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise ValueError(f"{config_env}: faltan variables {missing}")

    rendered: Dict[str, str] = {}
    base = Path(template_dir)
    for name in UNIT_NAMES:
        text = (base / name).read_text(encoding="utf-8")
        for key, value in values.items():
            text = text.replace(f"@{key}@", value)
        if name == "intradia-bot-event.timer" and event_time is not None:
            text = _replace_event_time(text, event_time)
        rendered[name] = _normalize_unit(text)
    return rendered


def write_rendered_units(
    *,
    output_dir: str | Path,
    config_env: str | Path = DEFAULT_CONFIG_ENV,
    template_dir: str | Path = DEFAULT_TEMPLATE_DIR,
    event_time: Optional[str] = None,
) -> None:
    """Escribe unidades renderizadas de forma idempotente."""

    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    for name, text in render_units(config_env=config_env, template_dir=template_dir, event_time=event_time).items():
        (target / name).write_text(text + "\n", encoding="utf-8")


def find_systemd_drift(
    *,
    config_env: str | Path = DEFAULT_CONFIG_ENV,
    template_dir: str | Path = DEFAULT_TEMPLATE_DIR,
    installed_dir: str | Path = DEFAULT_SYSTEMD_DIR,
    event_time: Optional[str] = None,
) -> List[str]:
    """Devuelve diferencias reales entre unidades instaladas y plantillas resueltas."""

    expected = render_units(config_env=config_env, template_dir=template_dir, event_time=event_time)
    installed = Path(installed_dir)
    drift: List[str] = []
    for name, expected_text in expected.items():
        path = installed / name
        if not path.is_file():
            drift.append(f"{name}: no instalada")
            continue
        actual = _normalize_unit(path.read_text(encoding="utf-8"))
        if actual != expected_text:
            drift.append(f"{name}: difiere de la plantilla resuelta")
    return drift


def _replace_event_time(text: str, event_time: str) -> str:
    prefix = "OnCalendar=Mon..Fri "
    lines = []
    for line in text.splitlines():
        if line.startswith(prefix):
            lines.append(prefix + event_time)
        else:
            lines.append(line)
    return "\n".join(lines)


def _normalize_unit(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").splitlines()).rstrip()
