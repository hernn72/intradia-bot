"""Estado de una ejecución: ``OK`` solo si la cartera se atendió con datos válidos.

Un símbolo sin datos no para la cartera, pero una ejecución sin ningún dato, con
datos caducados o con una posición abierta sin barras no puede quedar como
correcta: nadie vigila esos stops.
"""

from __future__ import annotations

import sqlite3
import zlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, ClassVar, Dict, Optional, Set

import numpy as np
import pandas as pd
import pytest

from advisor.universe.loader import load_universe
from superbot.cli import main
from superbot.config import SuperbotConfig
from superbot.data import MAX_BAR_AGE_DAYS, fresh_symbols, load_series
from superbot.engine import BarSeries

UNIVERSE = Path(__file__).resolve().parent.parent / "universe.yaml"


class Provider:
    fail: ClassVar[Set[str]] = set()
    fail_all = False
    age_days = 3
    age_of: ClassVar[Dict[str, int]] = {}

    def __init__(self, min_interval_seconds: float = 0.0) -> None:
        pass

    def get_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        if self.fail_all or symbol in self.fail:
            raise ValueError(f"No se han recibido datos para el símbolo '{symbol}'")
        age = self.age_of.get(symbol, self.age_days)
        end = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(days=age)
        index = pd.bdate_range(end=end, periods=320, tz="UTC")
        if symbol.endswith("=X"):
            closes = np.full(len(index), 1.1)
        else:
            rng = np.random.default_rng(zlib.crc32(symbol.encode()))
            closes = 50 * np.exp(np.cumsum(rng.normal(0.001, 0.012, len(index))))
        return pd.DataFrame({"Open": closes, "High": closes * 1.01, "Low": closes * 0.99, "Close": closes,
                             "Volume": 1e6}, index=index)


@pytest.fixture(autouse=True)
def provider(monkeypatch: pytest.MonkeyPatch) -> type[Provider]:
    import advisor.data.market_data as market_data

    monkeypatch.setattr(Provider, "fail", set())
    monkeypatch.setattr(Provider, "fail_all", False)
    monkeypatch.setattr(Provider, "age_days", 3)
    monkeypatch.setattr(Provider, "age_of", {})
    monkeypatch.setattr(market_data, "MarketDataProvider", Provider)
    for var in ("SUPERBOT_TELEGRAM_BOT_TOKEN", "SUPERBOT_TELEGRAM_CHAT_ID", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.setenv(var, "")
    return Provider


def init(db: Path, *groups: str, days: int = 0) -> None:
    args = ["--db", str(db), "init"]
    if days:
        args += ["--start", (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()]
    assert main([*args, "--grupos", *groups]) == 0


def run(db: Path, *extra: str, universe: Path = UNIVERSE) -> int:
    return main(["--db", str(db), "run", "--universe", str(universe), "--intervalo", "0", *extra])


def last_run(db: Path) -> sqlite3.Row:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn.execute("SELECT * FROM runs ORDER BY id DESC").fetchone()


def snapshot(db: Path) -> dict:
    conn = sqlite3.connect(db)
    return {t: conn.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()
            for t in ("positions", "orders", "signals", "fills", "equity_snapshots", "symbol_state", "notifications")}


def held(db: Path) -> Optional[str]:
    row = sqlite3.connect(db).execute("SELECT symbol FROM positions WHERE status = 'OPEN' ORDER BY id").fetchone()
    return None if row is None else row[0]


def portfolio(tmp_path: Path) -> Path:
    db = tmp_path / "superbot.db"
    init(db, "europa", "usa", days=90)
    assert run(db) == 0
    assert held(db) is not None
    return db


def test_sin_ningun_dato_la_ejecucion_falla_y_no_toca_la_cartera(
    tmp_path: Path, provider: type[Provider], capsys: pytest.CaptureFixture[str]
) -> None:
    db = portfolio(tmp_path)
    before = snapshot(db)
    provider.fail_all = True
    assert run(db) == 1
    row = last_run(db)
    assert row["status"] == "ERROR"
    assert row["symbols_ok"] == 0 and row["symbols_err"] > 0 and row["bars"] == 0
    assert "sin datos válidos" in row["detail"]
    assert "sin datos válidos" in capsys.readouterr().err
    assert snapshot(db) == before


def test_primera_ejecucion_sin_datos_tambien_falla(tmp_path: Path, provider: type[Provider]) -> None:
    db = tmp_path / "superbot.db"
    init(db, "europa")
    provider.fail_all = True
    assert run(db) == 1
    assert last_run(db)["status"] == "ERROR"


def test_datos_caducados_en_todo_el_universo_no_son_una_ejecucion_correcta(
    tmp_path: Path, provider: type[Provider]
) -> None:
    db = portfolio(tmp_path)
    before = snapshot(db)
    provider.age_days = MAX_BAR_AGE_DAYS + 5
    assert run(db) == 1
    row = last_run(db)
    assert row["status"] == "ERROR" and "caducad" in row["detail"]
    assert snapshot(db) == before


def test_posicion_abierta_sin_datos_se_marca_y_el_resto_se_procesa(
    tmp_path: Path, provider: type[Provider], capsys: pytest.CaptureFixture[str]
) -> None:
    db = portfolio(tmp_path)
    symbol = held(db)
    provider.fail = {symbol}
    assert run(db) == 1
    row = last_run(db)
    assert row["status"] == "ERROR" and row["symbols_ok"] > 0
    assert symbol in row["detail"] and "sin vigilar" in row["detail"]
    assert symbol in capsys.readouterr().err
    assert held(db) == symbol


def test_posicion_con_barras_caducadas_tambien_queda_sin_vigilar(tmp_path: Path, provider: type[Provider]) -> None:
    db = portfolio(tmp_path)
    symbol = held(db)
    provider.age_of = {symbol: MAX_BAR_AGE_DAYS + 5}
    assert run(db) == 1
    assert symbol in last_run(db)["detail"]


def test_posicion_fuera_del_universo_no_desaparece_en_silencio(tmp_path: Path) -> None:
    db = portfolio(tmp_path)
    symbol = held(db)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE positions SET symbol = 'RETIRADO.XX' WHERE symbol = ?", (symbol,))
    conn.commit()
    conn.close()
    assert run(db) == 1
    assert "RETIRADO.XX" in last_run(db)["detail"]


def test_sin_tipo_de_cambio_para_una_divisa_en_uso_no_es_correcta(tmp_path: Path, provider: type[Provider]) -> None:
    db = tmp_path / "superbot.db"
    init(db, "usa", days=30)
    provider.fail = {"EURUSD=X"}
    assert run(db) == 1
    row = last_run(db)
    assert row["status"] == "ERROR" and "USD" in row["detail"]


def test_simbolo_sin_datos_y_sin_posicion_sigue_siendo_correcta(tmp_path: Path, provider: type[Provider]) -> None:
    db = portfolio(tmp_path)
    conn = sqlite3.connect(db)
    busy = {r[0] for r in conn.execute("SELECT symbol FROM positions WHERE status = 'OPEN' "
                                       "UNION SELECT symbol FROM orders WHERE status = 'PENDING'")}
    conn.close()
    provider.fail = {s for s in ("SAP.DE", "SIE.DE", "ASML.AS", "MSFT", "AAPL") if s not in busy}
    assert provider.fail
    assert run(db) == 0
    row = last_run(db)
    assert row["status"] == "OK" and row["symbols_err"] == len(provider.fail)
    assert next(iter(sorted(provider.fail))) in row["detail"]


def test_sin_barras_nuevas_sigue_siendo_correcta(tmp_path: Path) -> None:
    db = portfolio(tmp_path)
    before = snapshot(db)
    assert run(db) == 0
    assert last_run(db)["status"] == "OK" and last_run(db)["bars"] == 0
    assert snapshot(db) == before


@pytest.mark.parametrize("age,code", [(MAX_BAR_AGE_DAYS - 1, 0), (MAX_BAR_AGE_DAYS + 4, 1)])
def test_limite_de_antiguedad(tmp_path: Path, provider: type[Provider], age: int, code: int) -> None:
    # bdate_range retrocede al viernes en fin de semana: el margen evita un test que dependa del día.
    db = tmp_path / "superbot.db"
    init(db, "europa")
    provider.age_days = age - 2 if code == 0 else age
    assert run(db) == code


def test_vigencia_de_una_barra_cubre_el_cierre_mas_largo_de_una_plaza() -> None:
    today = date(2026, 2, 26)
    frames = {
        name: BarSeries(symbol=name, name=name, currency="CNY", market="XSHG",
                        frame=pd.DataFrame({"Close": [1.0]}, index=[today - timedelta(days=age)]))
        for name, age in (("hoy", 0), ("ano-nuevo-lunar", 9), ("limite", 10), ("caducada", 11))
    }
    assert fresh_symbols(frames, today) == {"hoy", "ano-nuevo-lunar", "limite"}


def test_el_aviso_de_operaciones_sale_aunque_quede_una_posicion_sin_datos(
    tmp_path: Path, provider: type[Provider], capsys: pytest.CaptureFixture[str]
) -> None:
    db = portfolio(tmp_path)
    provider.fail = {held(db)}
    assert run(db, "--telegram") == 1
    assert "Telegram:" in capsys.readouterr().out


def test_una_excepcion_del_motor_sigue_quedando_como_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from superbot import engine

    db = portfolio(tmp_path)
    boom: Callable[..., None] = lambda *a, **k: (_ for _ in ()).throw(ValueError("fallo del motor"))  # noqa: E731
    monkeypatch.setattr(engine.PaperEngine, "process", boom)
    assert run(db) == 1
    row = last_run(db)
    assert row["status"] == "ERROR" and "fallo del motor" in row["detail"]


def test_ejecucion_sin_datos_reintenta_los_avisos_pendientes(
    tmp_path: Path, provider: type[Provider], monkeypatch: pytest.MonkeyPatch
) -> None:
    from superbot import notify

    db = portfolio(tmp_path)
    called = []
    monkeypatch.setattr(notify, "flush", lambda store, notifier: called.append(True) or {"SENT": 0})
    provider.fail_all = True
    assert run(db) == 1
    assert called == []                    # sin --telegram no se envía nada
    assert run(db, "--telegram") == 1
    assert called == [True]
    assert last_run(db)["status"] == "ERROR"


def test_tipo_de_cambio_vacio_cuenta_como_ausente(tmp_path: Path, provider: type[Provider],
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "superbot.db"
    init(db, "usa", days=30)
    original = Provider.get_history

    def without_closes(self: Provider, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        frame = original(self, symbol, period, interval)
        return frame.assign(Close=0.0) if symbol.endswith("=X") else frame

    monkeypatch.setattr(Provider, "get_history", without_closes)
    assert run(db) == 1
    assert "USD" in last_run(db)["detail"]


def test_load_series_conserva_el_split_de_la_barra_recortada() -> None:
    now = datetime(2026, 6, 10, 15, 0, tzinfo=timezone.utc)      # NYSE abierta
    index = pd.bdate_range(end="2026-06-10", periods=320, tz="America/New_York")
    closes = np.linspace(50, 80, len(index))
    raw = pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes,
                        "Stock Splits": 0.0}, index=index)
    raw.iloc[-1, raw.columns.get_loc("Stock Splits")] = 4.0

    class One:
        def get_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
            return raw

    asset = next(a for a in load_universe(UNIVERSE).analizables(["usa"]) if a.symbol == "AAPL")
    bars = load_series([asset], One(), SuperbotConfig(), now).series["AAPL"]
    assert bars.frame.index[-1] < date(2026, 6, 10)
    assert bars.unclosed_split == 4.0
