"""Pegamento de despliegue de T-025 (``deploy/t025``): resumen de Telegram y caída al texto original.

Las muestras salen del ``paper.telegram.shadow_message`` congelado en 78db33d:
``muestra-2026-10-09.txt`` es el mensaje real enviado el 2026-10-12 y
``muestra-mixta.txt`` se generó con ese mismo código y señales simuladas.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy" / "t025"
FIXTURES = ROOT / "tests" / "fixtures" / "t025_telegram"
FROZEN_CODE_SHA = "78db33d2f2ab71aaf32a5ca6b6d0aa59f06506b6"


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


resumen = _load("t025_resumen_deploy", "deploy/t025/t025_resumen.py")
LABEL_LINE, SEAL_LINE, resumir = resumen.LABEL_LINE, resumen.SEAL_LINE, resumen.resumir
PENDING_LABEL = resumen.PENDING_LABEL


def _cli_text(name: str) -> str:
    """El texto tal como lo imprime ``paper telegram`` (sin la línea de sesión del pegamento)."""

    lines = (FIXTURES / name).read_text(encoding="utf-8").rstrip("\n").split("\n")
    if lines[-1].startswith("Sesión de señal "):
        lines = lines[:-1]
    return "\n".join(lines)


def _symbols(text: str) -> set:
    return set(re.findall(r"^\S+ · (\S+) · sesión", text, flags=re.M))


def test_mensaje_real_de_24_lineas_queda_en_pocas() -> None:
    text = _cli_text("muestra-2026-10-09.txt")
    assert len(text.split("\n")) == 26
    out = resumir(text, "2026-10-09")

    lines = out.split("\n")
    assert lines[0] == LABEL_LINE
    assert lines[-1] == SEAL_LINE
    assert len(lines) <= 10
    assert "Sesión de señal 2026-10-09 · 24 señales OPERAR" in out
    assert "B2-P6 (18): 6857.T, AMAT, EUNL.DE" in out
    assert "C0-P6 (3): PLTR, SAP.DE, SXR8.DE" in out
    assert "S2-P6 (3): PLTR, SAP.DE, SXR8.DE" in out


def test_no_pierde_ninguna_senal() -> None:
    for name, session in (("muestra-2026-10-09.txt", "2026-10-09"), ("muestra-mixta.txt", "2026-10-09")):
        text = _cli_text(name)
        out = resumir(text, session)
        for symbol in _symbols(text):
            assert symbol in out, (name, symbol)


def test_no_anade_datos_que_no_esten_en_el_original() -> None:
    text = _cli_text("muestra-mixta.txt")
    out = resumir(text, "2026-10-09")
    # Fuera de los recuentos «(n)» y «n señales», cada número del resumen está en el original.
    sin_recuentos = re.sub(r"\(\d+\)|\d+ señales?", "", out)
    numbers_in = set(re.findall(r"\d+(?:[.-]\d+)*", text))
    for number in re.findall(r"\d+(?:[.-]\d+)*", sin_recuentos):
        assert number in numbers_in, number


def test_separa_market_pass_rechazos_y_pendientes() -> None:
    out = resumir(_cli_text("muestra-mixta.txt"), "2026-10-09")

    assert "6 señales OPERAR" in out
    market_pass = out.split("✅ MARKET_PASS\n", 1)[1].split("\n\n", 1)[0]
    assert market_pass.split("\n") == [
        "C0-P6 (1): SAP.DE a 190.10 (8.9 %)",
        "S2-P6 (1): SAP.DE a 190.10 (8.9 %)",
    ]
    rejected = out.split("❌ Rechazo de mercado\n", 1)[1].split("\n\n", 1)[0]
    assert rejected == "S2-P6 (1): PLTR (GAP_ABOVE_ENTRY_MAX)"
    pending = out.split(f"{PENDING_LABEL}\n", 1)[1].split("\n\n", 1)[0]
    assert pending.split("\n") == ["B2-P6 (2): TSLA, V", "C0-P6 (1): PLTR"]
    # Ni niveles por señal ni importes: solo lo agrupado.
    assert "entrada máx" not in out and "stop" not in out


def test_sin_senales_devuelve_el_original() -> None:
    text = f"{LABEL_LINE}\nSin señales OPERAR de B2-P6, S2-P6 ni C0-P6."
    assert resumir(text, "2026-10-12") == f"{text}\nSesión de señal 2026-10-12"


def test_linea_desconocida_devuelve_el_original_sin_tocar() -> None:
    text = _cli_text("muestra-mixta.txt")
    lines = text.split("\n")
    lines.insert(2, "B2-P6 · V · sesión 2026-10-09: formato nuevo que no se reconoce")
    raro = "\n".join(lines)
    assert resumir(raro, "2026-10-09") == f"{raro}\nSesión de señal 2026-10-09"


def test_estado_desconocido_o_sesion_ajena_devuelve_el_original() -> None:
    text = _cli_text("muestra-mixta.txt")
    otro_estado = text.replace("→ pendiente de la apertura", "→ algo nuevo", 1)
    assert resumir(otro_estado, "2026-10-09").startswith(otro_estado)
    assert resumir(text, "2026-10-12") == f"{text}\nSesión de señal 2026-10-12"


def test_sin_etiqueta_o_sin_pie_devuelve_el_original() -> None:
    text = _cli_text("muestra-mixta.txt")
    sin_pie = text.rsplit("\n", 1)[0]
    assert resumir(sin_pie, "2026-10-09") == f"{sin_pie}\nSesión de señal 2026-10-09"
    sin_etiqueta = text.split("\n", 1)[1]
    assert resumir(sin_etiqueta, "2026-10-09") == f"{sin_etiqueta}\nSesión de señal 2026-10-09"


def test_si_el_resumen_falla_el_pegamento_envia_el_texto_completo(monkeypatch, tmp_path) -> None:
    import types

    monkeypatch.setenv("T025_DB", str(tmp_path / "paper.db"))
    monkeypatch.setenv("T025_STATE", str(tmp_path))
    # En la Pi, t025_resumen.py está junto a t025_pasada.py en bin/.
    monkeypatch.syspath_prepend(str(DEPLOY))
    monkeypatch.delitem(sys.modules, "t025_resumen", raising=False)
    pasada = _load("t025_pasada_deploy", "deploy/t025/t025_pasada.py")
    text = _cli_text("muestra-mixta.txt")

    assert pasada.message(text, "2026-10-09") == resumir(text, "2026-10-09")

    roto = types.ModuleType("t025_resumen")

    def resumir_roto(text: str, session: str) -> str:
        raise RuntimeError("roto")

    roto.resumir = resumir_roto  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "t025_resumen", roto)
    assert pasada.message(text, "2026-10-09") == f"{text}\nSesión de señal 2026-10-09"


def test_pendientes_se_nombran_por_la_barra_de_entrada() -> None:
    out = resumir(_cli_text("muestra-2026-10-09.txt"), "2026-10-09")
    assert PENDING_LABEL == "⏳ Pendientes de validar la barra de entrada"
    assert PENDING_LABEL in out
    assert "apertura" not in out


def test_el_pegamento_queda_fuera_de_la_identidad_congelada() -> None:
    from paper.cli import DEPENDENCY_PATHS, EXECUTOR_PATHS_T025

    rel = DEPLOY.relative_to(ROOT).as_posix()
    for path in (*EXECUTOR_PATHS_T025, *DEPENDENCY_PATHS):
        assert not rel.startswith(path.rstrip("/") + "/") and rel != path, path


def test_las_muestras_salen_del_formato_congelado() -> None:
    """Las expresiones del resumen describen ``paper/telegram.py`` tal como está en el SHA de la cohorte."""

    current = hashlib.sha256((ROOT / "paper" / "telegram.py").read_bytes()).hexdigest()
    # sha256 de `git show {FROZEN_CODE_SHA}:paper/telegram.py`.
    assert current == "f219609bc37ae3b1ad7f5743c20c75ce152e87c09cfb0a6ef84374cd634aa15f", "paper/telegram.py cambió: revisar t025_resumen y la identidad de la cohorte"
