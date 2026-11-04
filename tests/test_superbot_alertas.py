"""Avisos operativos: una vez por episodio, sin tocar la cartera ni la salida."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Set, Tuple

import pytest

from superbot import alerts
from superbot.store import SuperbotStore
from tests import test_superbot_run_status as base
from tests.test_superbot_run_status import Provider, held, last_run, portfolio, run, snapshot

provider = base.provider

START = datetime(2026, 11, 2, 18, 15, tzinfo=timezone.utc)
RUNS = [START + timedelta(days=d, hours=h) for d in range(10) for h in (0, 4)]
PROBLEM = {"COBERTURA": "70 de 90", "SIN_VIGILAR": "AAPL", "PARADA": "sin datos"}


def replay(sequence: List[Tuple[datetime, Set[str]]], reachable: bool = True) -> List[str]:
    state: Dict = {}
    sent: List[str] = []

    def send(text: str) -> bool:
        if reachable:
            sent.append(text)
        return reachable

    for now, causes in sequence:
        state = alerts.advance(state, now, {c: PROBLEM[c] for c in causes}, send)
    return sent


def test_fallo_aislado_de_cobertura_no_avisa() -> None:
    assert replay([(now, {"COBERTURA"} if i == 3 else set()) for i, now in enumerate(RUNS)]) == []


def test_cobertura_seguida_avisa_una_vez_y_se_recupera() -> None:
    sent = replay([(now, {"COBERTURA"} if i in (3, 4) else set()) for i, now in enumerate(RUNS)])
    assert len(sent) == 2
    assert "Cobertura insuficiente" in sent[0] and "Recuperado" in sent[1]


@pytest.mark.parametrize("cause", ["SIN_VIGILAR", "PARADA"])
def test_lo_que_protege_la_cartera_avisa_a_la_primera(cause: str) -> None:
    assert len(replay([(RUNS[0], {cause})])) == 1


def test_diez_dias_de_fallo_no_son_veinte_mensajes() -> None:
    sent = replay([(now, {"SIN_VIGILAR"}) for now in RUNS])
    assert len(sent) == 4
    assert sum("Sigue" in text for text in sent) == 3


def test_fallo_intermitente_no_cierra_el_episodio() -> None:
    assert len(replay([(now, {"SIN_VIGILAR"} if i % 2 == 0 else set()) for i, now in enumerate(RUNS)])) == 4


def test_telegram_caido_reintenta_sin_acumular() -> None:
    state: Dict = {}
    state = alerts.advance(state, RUNS[0], {"SIN_VIGILAR": "AAPL"}, lambda _: False)
    state = alerts.advance(state, RUNS[1], {"SIN_VIGILAR": "AAPL"}, lambda _: False)
    sent: List[str] = []
    alerts.advance(state, RUNS[2], {"SIN_VIGILAR": "AAPL"}, lambda text: sent.append(text) or True)
    assert len(sent) == 1


def test_recuperado_sin_enviar_se_reintenta() -> None:
    state = alerts.advance({}, RUNS[0], {"PARADA": "x"}, lambda _: True)
    for now in RUNS[1:3]:
        state = alerts.advance(state, now, {}, lambda _: False)
    assert "PARADA" in state
    assert alerts.advance(state, RUNS[3], {}, lambda _: True) == {}


def test_una_ejecucion_parada_no_recupera_otra_causa() -> None:
    sequence = [(RUNS[0], {"SIN_VIGILAR"}), (RUNS[1], {"PARADA"}), (RUNS[2], {"PARADA"})]
    assert not any("Recuperado" in text for text in replay(sequence))


def test_fallo_de_envio_no_deja_el_token_en_el_log(caplog: pytest.LogCaptureFixture,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    import requests

    from advisor.telegram.notifier import TelegramNotifier

    def down(url: str, **kwargs: object) -> None:
        raise requests.ConnectionError(f"Max retries exceeded with url: {url}")

    monkeypatch.setattr(requests, "post", down)
    assert TelegramNotifier(bot_token="123:SECRETO", chat_id="1").send_message("x") is False
    assert "SECRETO" not in caplog.text


@pytest.fixture
def telegram(monkeypatch: pytest.MonkeyPatch) -> List[str]:
    sent: List[str] = []

    class Fake:
        def __init__(self, bot_token, chat_id) -> None:  # type: ignore[no-untyped-def]
            assert (bot_token, chat_id) == ("token-avisos", "chat-avisos")

        def send_message(self, text: str) -> bool:
            sent.append(text)
            return True

    monkeypatch.setattr(alerts, "TelegramNotifier", Fake)
    monkeypatch.setenv("SUPERBOT_ALERTAS_BOT_TOKEN", "token-avisos")
    monkeypatch.setenv("SUPERBOT_ALERTAS_CHAT_ID", "chat-avisos")
    return sent


def test_apagados_no_envian_ni_escriben(tmp_path: Path, provider: type[Provider], telegram: List[str],
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPERBOT_ALERTAS", raising=False)
    db = portfolio(tmp_path)
    provider.fail_all = True
    assert run(db) == 1
    assert telegram == []
    assert sqlite3.connect(db).execute("SELECT 1 FROM meta WHERE key = ?", (alerts.STATE_KEY,)).fetchone() is None


def test_modo_seco_no_envia_pero_lleva_el_episodio(tmp_path: Path, provider: type[Provider], telegram: List[str],
                                                   monkeypatch: pytest.MonkeyPatch,
                                                   capsys: pytest.CaptureFixture[str]) -> None:
    db = portfolio(tmp_path)
    monkeypatch.setenv("SUPERBOT_ALERTAS", "seco")
    provider.fail_all = True
    assert run(db) == 1
    assert telegram == []
    assert "modo seco" in capsys.readouterr().out
    assert "PARADA" in json.loads(SuperbotStore(db).get_meta(alerts.STATE_KEY) or "{}")


def test_error_real_llega_con_sus_credenciales(tmp_path: Path, provider: type[Provider], telegram: List[str],
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    db = portfolio(tmp_path)
    monkeypatch.setenv("SUPERBOT_ALERTAS", "1")
    provider.fail = {held(db)}
    assert run(db) == 1
    assert len(telegram) == 1 and held(db) in telegram[0] and "token-avisos" not in telegram[0]


def test_ejecucion_sana_no_avisa(tmp_path: Path, telegram: List[str], monkeypatch: pytest.MonkeyPatch) -> None:
    db = portfolio(tmp_path)
    monkeypatch.setenv("SUPERBOT_ALERTAS", "1")
    assert run(db) == 0
    assert telegram == []


def test_fallo_de_los_avisos_no_cambia_la_ejecucion(tmp_path: Path, provider: type[Provider],
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("telegram")

    monkeypatch.setattr(alerts, "advance", broken)
    monkeypatch.setenv("SUPERBOT_ALERTAS", "1")
    db = portfolio(tmp_path)
    assert run(db) == 0
    assert last_run(db)["status"] == "OK"
    provider.fail_all = True
    assert run(db) == 1


def test_los_avisos_no_cambian_la_cartera(tmp_path: Path, provider: type[Provider],
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    def scenario(name: str, mode: str) -> dict:
        monkeypatch.setenv("SUPERBOT_ALERTAS", mode)
        monkeypatch.setattr(provider, "age_days", 3)
        folder = tmp_path / name
        folder.mkdir()
        db = portfolio(folder)
        monkeypatch.setattr(provider, "age_days", 1)
        run(db)
        return {k: [tuple(r)[1:] for r in v] for k, v in snapshot(db).items() if k != "notifications"}

    plain, dry = scenario("apagados", ""), scenario("seco", "seco")
    for rows in (plain, dry):
        for table in ("orders", "signals"):
            rows[table] = [tuple(v for v in r if not (isinstance(v, str) and "T" in v and ":" in v)) for r in rows[table]]
    assert plain == dry
