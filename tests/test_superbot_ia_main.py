"""CLI de Superbot IA: el subcomando ``pasada`` debe reconocer una cartera ya activada.

Hallazgo de Codex sobre la integración completa de la Entrega C: ``main()`` llamaba a
``ejecutar_pasada()`` sin pasarle ``cartera_ia``, así que ``_ejecutar()`` calculaba ``activa =
False`` sin importar lo que dijera la base de datos — ninguna pasada real desde cron/systemd en
la Raspberry Pi habría procesado nunca una orden, un stop, la caja ni una notificación, pese a
que el propio módulo declara en su docstring "modo registro salvo que algo externo ya la hubiera
activado". Esta prueba fija exactamente ese contrato de cableado, sin pasar por mercado real.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pytest

from superbot.ia import __main__ as cli
from superbot.ia.cartera import CarteraIA
from superbot.ia.pasada import ResultadoPasada
from superbot.ia.registro import RegistroIA
from tests.test_superbot_ia import POLITICA


def test_pasada_le_pasa_una_carteraia_de_la_misma_base_a_ejecutar_pasada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "ia.db"
    capturado: Dict[str, Any] = {}

    def _ejecutar_pasada_falso(**kwargs: Any) -> ResultadoPasada:
        capturado.update(kwargs)
        return ResultadoPasada(pasada_id=1, status="OK")

    monkeypatch.setattr(cli, "ejecutar_pasada", _ejecutar_pasada_falso)

    assert cli.main(["--db", str(db), "pasada"]) == 0

    cartera_ia = capturado.get("cartera_ia")
    assert isinstance(cartera_ia, CarteraIA)
    # La misma conexión/base que el ``RegistroIA`` del resto de la pasada, nunca una paralela.
    assert cartera_ia.conn is capturado["registro"].conn


def test_pasada_reconoce_una_cartera_ya_activada_por_el_dashboard_sin_activarla_ella_misma(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "ia.db"
    reg = RegistroIA(db, POLITICA)
    CarteraIA(reg.conn).activar(datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc), 10_000.0)
    reg.close()

    capturado: Dict[str, Any] = {}

    def _ejecutar_pasada_falso(**kwargs: Any) -> ResultadoPasada:
        capturado.update(kwargs)
        return ResultadoPasada(pasada_id=1, status="OK")

    monkeypatch.setattr(cli, "ejecutar_pasada", _ejecutar_pasada_falso)

    assert cli.main(["--db", str(db), "pasada"]) == 0

    cartera_ia = capturado["cartera_ia"]
    assert cartera_ia.activa() is True  # reconocida, no reactivada por el propio comando


def test_pasada_con_la_cartera_inactiva_sigue_en_modo_registro(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "ia.db"
    capturado: Dict[str, Any] = {}

    def _ejecutar_pasada_falso(**kwargs: Any) -> ResultadoPasada:
        capturado.update(kwargs)
        return ResultadoPasada(pasada_id=1, status="OK")

    monkeypatch.setattr(cli, "ejecutar_pasada", _ejecutar_pasada_falso)

    assert cli.main(["--db", str(db), "pasada"]) == 0

    assert capturado["cartera_ia"].activa() is False
