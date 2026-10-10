"""CLI de superbot de punta a punta con un proveedor falso (sin red)."""

from __future__ import annotations

import sqlite3
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from superbot import LABEL
from superbot.cli import main

UNIVERSE = Path(__file__).resolve().parent.parent / "universe.yaml"


class FakeProvider:
    """Serie alcista con ruido para cada símbolo; tipos de cambio constantes."""

    def __init__(self, min_interval_seconds: float = 0.0) -> None:
        pass

    def get_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        end = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(days=3)
        index = pd.bdate_range(end=end, periods=320, tz="UTC")
        if symbol.endswith("=X"):
            closes = np.full(len(index), 1.1)
        else:
            rng = np.random.default_rng(zlib.crc32(symbol.encode()))
            closes = 50 * np.exp(np.cumsum(rng.normal(0.001, 0.012, len(index))))
        return pd.DataFrame(
            {"Open": closes, "High": closes * 1.01, "Low": closes * 0.99, "Close": closes, "Volume": 1e6},
            index=index,
        )


@pytest.fixture
def fake_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    import advisor.data.market_data as market_data

    monkeypatch.setattr(market_data, "MarketDataProvider", FakeProvider)
    for var in ("SUPERBOT_TELEGRAM_BOT_TOKEN", "SUPERBOT_TELEGRAM_CHAT_ID", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        # Vacías y no borradas: load_dotenv no pisa una variable que ya existe,
        # así que un .env real no puede colar un envío a Telegram desde un test.
        monkeypatch.setenv(var, "")


def test_init_run_status_y_dashboard(tmp_path: Path, fake_provider: None, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "sb" / "superbot.db"
    start = (datetime.now(timezone.utc) - timedelta(days=90)).date().isoformat()
    assert main(["--db", str(db), "init", "--capital", "10000", "--start", start, "--grupos", "europa", "usa"]) == 0
    assert main(["--db", str(db), "run", "--universe", str(UNIVERSE), "--intervalo", "0", "--telegram"]) == 0
    out = capsys.readouterr().out
    assert LABEL in out
    assert "barras nuevas" in out

    conn = sqlite3.connect(db)
    run = conn.execute("SELECT status, symbols_ok FROM runs").fetchone()
    assert run[0] == "OK" and run[1] > 0
    assert conn.execute("SELECT COUNT(*) FROM fills").fetchone()[0] > 0
    assert conn.execute("SELECT COUNT(*) FROM equity_snapshots").fetchone()[0] > 30
    # Sin Telegram configurado el resumen queda SKIPPED, no PENDING para siempre.
    assert conn.execute("SELECT status FROM notifications WHERE kind = 'RESUMEN'").fetchone()[0] == "SKIPPED"
    cash = conn.execute("SELECT 10000 + COALESCE(SUM(cash_delta_eur), 0) FROM fills").fetchone()[0]
    assert cash >= 0

    # Segunda ejecución con los mismos datos: nada nuevo.
    assert main(["--db", str(db), "run", "--universe", str(UNIVERSE), "--intervalo", "0"]) == 0
    assert "0 barras nuevas" in capsys.readouterr().out

    assert main(["--db", str(db), "status"]) == 0
    assert "RESUMEN DE CARTERA" in capsys.readouterr().out

    html = tmp_path / "dash.html"
    assert main(["--db", str(db), "dashboard", "--output", str(html)]) == 0
    assert LABEL in html.read_text(encoding="utf-8")


def test_run_sin_init_falla_con_mensaje(tmp_path: Path, fake_provider: None,
                                        capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--db", str(tmp_path / "superbot.db"), "run", "--universe", str(UNIVERSE)]) == 1
    assert "no está inicializada" in capsys.readouterr().err
    assert not (tmp_path / "superbot.db").exists()


def test_init_rechaza_la_base_de_t025(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--db", str(tmp_path / "paper.db"), "init"]) == 1
    assert not (tmp_path / "paper.db").exists()
