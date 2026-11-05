"""Registro de decisiones: todo lo evaluado queda escrito y nada de ello decide."""

from __future__ import annotations

import ast
import random
import sqlite3
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import pytest

import superbot.engine as engine_module
from superbot import alerts
from superbot.config import SizingParams, SuperbotConfig
from superbot.decisions import Decision, DecisionRecorder, NullRecorder, recorder_from_env
from superbot.engine import BarSeries, PaperEngine
from superbot.store import SuperbotStore
from tests import test_superbot_run_status as base
from tests.test_superbot_run_status import Provider, held, last_run, portfolio, snapshot
from tests.test_superbot_run_status import run as cli_run

provider = base.provider

START = date(2026, 3, 2)
START_TIME = datetime(2026, 3, 2, 18, 15, tzinfo=timezone.utc)
BUY = {"sma_fast": 95.0, "sma_slow": 90.0, "rsi": 60.0, "atr": 2.0, "trend_break": False}
HOLD = {"sma_fast": 105.0, "sma_slow": 90.0, "rsi": 60.0, "atr": 2.0, "trend_break": False}


class Fx:
    def __init__(self, missing: bool = False) -> None:
        self.missing = missing

    def rate(self, currency: str, on: date) -> Optional[float]:
        return None if self.missing else 1.0


def bar(o: float, h: float, low: float, c: float, ind: dict = HOLD) -> dict:
    return {"Open": o, "High": h, "Low": low, "Close": c, **ind, "Stock Splits": 0.0}


FLAT = bar(100, 101, 99, 100)
SIGNAL = bar(99, 101, 98, 100, BUY)


def series(symbol: str, bars: List[dict], market: str = "XETRA", start: date = START) -> BarSeries:
    index = [start + timedelta(days=i) for i in range(len(bars))]
    return BarSeries(symbol=symbol, name=symbol, currency="EUR", frame=pd.DataFrame(bars, index=index), market=market)


def data(**bars: List[dict]) -> Dict[str, BarSeries]:
    return {f"{symbol}.DE": series(f"{symbol}.DE", rows) for symbol, rows in bars.items()}


def make_store(path: Path, config: Optional[SuperbotConfig] = None) -> SuperbotStore:
    created = SuperbotStore(path / "superbot.db")
    created.initialize(config or SuperbotConfig(initial_capital_eur=10_000.0), START, retrospective=False)
    return created


@pytest.fixture
def store(tmp_path: Path) -> SuperbotStore:
    return make_store(tmp_path)


def process(store: SuperbotStore, frames: Dict[str, BarSeries], recorder: Optional[NullRecorder] = None,
            entries: bool = True, fx: Optional[Fx] = None, days: int = 5):
    engine = PaperEngine(store, DecisionRecorder() if recorder is None else recorder)
    return engine.process(frames, fx or Fx(), store.start_run(), START + timedelta(days=days), allow_entries=entries)


def log(store: SuperbotStore) -> List[dict]:
    rows = store.connect().execute("SELECT * FROM decision_log ORDER BY bar_date, symbol").fetchall()
    return [dict(row) for row in rows]


def reasons(store: SuperbotStore, symbol: str = "SAP.DE") -> List[str]:
    return [row["reason"] for row in log(store) if row["symbol"] == symbol]


def closing(store: SuperbotStore) -> List[dict]:
    return [dict(row) for row in store.connect().execute("SELECT * FROM decision_runs ORDER BY run_id")]


# --- Motivos -----------------------------------------------------------------


def test_senal_aceptada_guarda_fecha_simbolo_decision_y_motivo(store: SuperbotStore) -> None:
    process(store, data(SAP=[SIGNAL]))
    [row] = log(store)
    assert (row["bar_date"], row["symbol"], row["action"]) == (START.isoformat(), "SAP.DE", "BUY")
    assert (row["decision"], row["reason"]) == ("ACEPTADA", "ORDEN_CREADA")
    assert row["detail"]


def test_sin_senal_no_hay_fila(store: SuperbotStore) -> None:
    process(store, data(SAP=[FLAT]))
    assert log(store) == []
    assert closing(store)[0]["status"] == "COMPLETO"


def test_orden_pendiente(store: SuperbotStore) -> None:
    process(store, data(SAP=[SIGNAL]))
    # Sin tipo de cambio la orden sigue pendiente y la señal se repite.
    process(store, data(SAP=[SIGNAL, SIGNAL]), fx=Fx(missing=True))
    assert reasons(store) == ["ORDEN_CREADA", "ORDEN_PENDIENTE"]


def test_sin_tipo_de_cambio(store: SuperbotStore) -> None:
    process(store, data(SAP=[SIGNAL]), fx=Fx(missing=True))
    assert reasons(store) == ["SIN_FX"]


def test_no_asequible(tmp_path: Path) -> None:
    store = make_store(tmp_path, SuperbotConfig(initial_capital_eur=100.0))
    process(store, data(SAP=[SIGNAL]))
    assert reasons(store) == ["NO_ASEQUIBLE"]


def test_ranking_y_sin_hueco(tmp_path: Path) -> None:
    config = SuperbotConfig(initial_capital_eur=10_000.0,
                            sizing=replace(SizingParams(), max_positions=2, max_new_positions_per_session=1))
    store = make_store(tmp_path, config)
    process(store, data(AAA=[SIGNAL], BBB=[SIGNAL]))
    assert sorted(r["reason"] for r in log(store)) == ["ORDEN_CREADA", "RANKING"]
    assert sorted(r["rank"] for r in log(store)) == [1, 2]


def test_sin_hueco_cuando_la_cartera_esta_llena(tmp_path: Path) -> None:
    config = SuperbotConfig(initial_capital_eur=10_000.0, sizing=replace(SizingParams(), max_positions=1))
    store = make_store(tmp_path, config)
    process(store, data(AAA=[SIGNAL, FLAT, FLAT], BBB=[FLAT, FLAT, SIGNAL]))
    assert reasons(store, "BBB.DE") == ["SIN_HUECO"]


def test_salio_hoy(store: SuperbotStore) -> None:
    falls_with_signal = bar(100, 101, 80, 100, BUY)
    process(store, data(SAP=[SIGNAL, FLAT, falls_with_signal]))
    assert reasons(store) == ["ORDEN_CREADA", "SALIO_HOY"]


def test_barra_atrasada(store: SuperbotStore) -> None:
    flat = [FLAT] * 6
    process(store, data(AAA=flat, SAP=[FLAT]))
    process(store, data(AAA=flat, SAP=[FLAT, SIGNAL, FLAT, FLAT, FLAT, FLAT]))
    assert reasons(store) == ["BARRA_ATRASADA"]


def test_sin_entradas(store: SuperbotStore) -> None:
    process(store, data(SAP=[SIGNAL, FLAT]))
    bars = [SIGNAL, FLAT, bar(100, 100, 80, 85), bar(85, 101, 84, 100, BUY), bar(100, 101, 99, 100)]
    process(store, data(SAP=bars), entries=False)
    assert reasons(store) == ["ORDEN_CREADA", "SIN_ENTRADAS"]
    assert [c["mode"] for c in closing(store)] == ["NORMAL", "SIN_ENTRADAS"]


# --- Cobertura ---------------------------------------------------------------


def market(seed: int) -> Dict[str, BarSeries]:
    rng = random.Random(seed)
    frames = {}
    for number in range(9):
        price, bars = 100.0, []
        for _ in range(45):
            change = rng.uniform(-0.05, 0.055)
            opened = price
            price *= 1 + change
            indicators = {**(BUY if rng.random() < 0.35 else HOLD), "sma_fast": price * 0.95 if rng.random() < 0.5 else price * 1.05}
            bars.append(bar(opened, max(opened, price) * 1.01, min(opened, price) * 0.98, price, indicators))
        frames[f"S{number}.DE"] = series(f"S{number}.DE", bars)
    return frames


def ledger(store: SuperbotStore) -> dict:
    conn = store.connect()
    tables = ("positions", "fills", "signals", "symbol_state", "equity_snapshots", "notifications")
    out = {t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY 1")] for t in tables}
    out["orders"] = [tuple(r)[:6] + tuple(r)[7:] for r in conn.execute("SELECT * FROM orders ORDER BY 1")]
    out["notifications"] = [tuple(r)[1:2] + tuple(r)[3:6] for r in conn.execute("SELECT * FROM notifications ORDER BY 1")]
    out["cash"] = store.cash_eur()
    return out


class Broken(DecisionRecorder):
    """Falla en cada anotación y en cada escritura."""

    def record(self, decision) -> None:  # type: ignore[no-untyped-def]
        super().record(lambda: 1 / 0)

    def flush(self, conn: sqlite3.Connection, run_id: int, entries: bool) -> Optional[str]:
        conn.execute("DROP TABLE IF EXISTS decision_runs")
        return super().flush(conn, run_id, entries)


@pytest.mark.parametrize("seed", range(6))
def test_la_cartera_es_identica_con_registro_sin_registro_y_con_registro_roto(tmp_path: Path, seed: int) -> None:
    results = {}
    for name, recorder in (("sin", NullRecorder()), ("con", DecisionRecorder()), ("roto", Broken())):
        folder = tmp_path / name
        store = make_store(folder)
        frames = market(seed)
        for end in (20, 21, 33, 45):
            part = {s: series(s, b.frame.iloc[:end].to_dict("records")) for s, b in frames.items()}
            process(store, part, recorder=recorder, entries=end != 21, days=end)
        results[name] = ledger(store)
    assert results["sin"]["fills"], "escenario vacío"
    assert results["con"] == results["sin"]
    assert results["roto"] == results["sin"]


@pytest.mark.parametrize("seed", range(4))
def test_se_registra_el_100_por_cien_de_las_senales_de_compra(store: SuperbotStore, seed: int,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    seen = []
    original = engine_module.evaluate

    def spy(row, params, has_position):  # type: ignore[no-untyped-def]
        signal = original(row, params, has_position)
        if signal.action == "BUY":
            seen.append(row.name)
        return signal

    monkeypatch.setattr(engine_module, "evaluate", spy)
    process(store, market(seed), days=45)
    rows = log(store)
    assert len(rows) == len(seen) > 0
    conn = store.connect()
    created = conn.execute("SELECT COUNT(*) FROM orders WHERE side = 'BUY'").fetchone()[0]
    assert sum(r["decision"] == "ACEPTADA" for r in rows) == created
    assert closing(store)[0]["expected"] == closing(store)[0]["written"] == len(rows)


def test_repetir_la_ejecucion_no_duplica(store: SuperbotStore) -> None:
    frames = data(SAP=[SIGNAL, FLAT])
    process(store, frames)
    process(store, frames)
    assert len(log(store)) == 1


def test_split_sin_decidir_no_deja_filas_del_intento_revertido(store: SuperbotStore) -> None:
    pre = [bar(99, 101, 98, 100, BUY), bar(100, 104, 99, 103)]
    process(store, data(SAP=pre))
    jump = {**bar(70, 71, 69, 70), "Stock Splits": 2.0}
    other = [FLAT, SIGNAL, FLAT]
    result = process(store, data(SAP=[*pre, jump], ALV=other))
    assert result.held == ["SAP.DE"]
    assert reasons(store, "ALV.DE") == []
    assert closing(store)[-1]["mode"] == "SIN_ENTRADAS"


# --- Fallos ------------------------------------------------------------------


def test_fallo_al_escribir_conserva_operaciones_y_declara_la_perdida(store: SuperbotStore) -> None:
    conn = store.connect()
    conn.execute("DROP TABLE decision_log")
    conn.commit()
    result = process(store, data(SAP=[SIGNAL, FLAT]))
    assert len(store.fills()) == 1
    assert "perdido" in (result.trace_lost or "")
    [closed] = closing(store)
    assert (closed["status"], closed["written"], closed["expected"]) == ("INCOMPLETO", 0, 1)


def test_sin_tabla_de_cierre_tampoco_se_para(store: SuperbotStore) -> None:
    conn = store.connect()
    conn.execute("DROP TABLE decision_runs")
    conn.commit()
    result = process(store, data(SAP=[SIGNAL, FLAT]))
    assert len(store.fills()) == 1
    assert result.trace_lost
    assert store.connect().execute("SELECT COUNT(*) FROM decision_log").fetchone()[0] == 0


def test_fila_duplicada_deshace_solo_el_registro(store: SuperbotStore) -> None:
    conn = store.connect()
    run = store.start_run()
    conn.execute("INSERT INTO decision_log (run_id, bar_date, symbol, action, decision, reason) "
                 "VALUES (?, ?, 'SAP.DE', 'BUY', 'DESCARTADA', 'RANKING')", (run, START.isoformat()))
    conn.commit()
    result = process(store, data(SAP=[SIGNAL, FLAT]))
    assert len(store.fills()) == 1
    assert result.trace_lost
    assert len(log(store)) == 1


def test_anotacion_fallida_se_cuenta_como_perdida(store: SuperbotStore) -> None:
    recorder = DecisionRecorder()
    recorder.record(lambda: 1 / 0)  # type: ignore[arg-type, return-value]
    recorder.flush(store.connect(), store.start_run(), True)
    [closed] = closing(store)
    assert (closed["status"], closed["expected"], closed["written"]) == ("INCOMPLETO", 1, 0)


# --- Aislamiento -------------------------------------------------------------


def test_el_motor_nunca_lee_el_registro() -> None:
    source = Path(engine_module.__file__).read_text(encoding="utf-8")
    texts = [node.value for node in ast.walk(ast.parse(source))
             if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    assert not any("decision_log" in text or "decision_runs" in text for text in texts)


def test_apagado_por_defecto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPERBOT_REGISTRO", raising=False)
    assert type(recorder_from_env()) is NullRecorder
    monkeypatch.setenv("SUPERBOT_REGISTRO", "1")
    assert type(recorder_from_env()) is DecisionRecorder


def test_cli_apagado_no_escribe_nada(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPERBOT_REGISTRO", raising=False)
    db = portfolio(tmp_path)
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM decision_log").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM decision_runs").fetchone()[0] == 0


def test_cli_activado_y_resumen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                capsys: pytest.CaptureFixture[str]) -> None:
    from superbot.cli import main

    monkeypatch.setenv("SUPERBOT_REGISTRO", "1")
    db = portfolio(tmp_path)
    capsys.readouterr()
    assert main(["--db", str(db), "decisiones"]) == 0
    out = capsys.readouterr().out
    assert "ORDEN_CREADA" in out and "Tamaño de la base" in out
    assert "sin cierre del registro: 0" in out


def test_cli_perdida_declarada_sin_cambiar_el_estado(tmp_path: Path, provider: type[Provider],
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPERBOT_REGISTRO", "1")
    monkeypatch.setenv("SUPERBOT_ALERTAS", "seco")
    db = portfolio(tmp_path)
    assert held(db)
    conn = sqlite3.connect(db)
    conn.execute("DROP TABLE decision_log")
    conn.commit()
    conn.close()
    # La tabla se recrea al abrir: el fallo se fuerza en la escritura.
    monkeypatch.setattr(DecisionRecorder, "_rows", [object()], raising=False)
    original = DecisionRecorder.reset

    def poisoned(self) -> None:  # type: ignore[no-untyped-def]
        original(self)
        self._rows.append(object())

    monkeypatch.setattr(DecisionRecorder, "reset", poisoned)
    provider.age_days = 1
    before = snapshot(db)["fills"]
    assert cli_run(db) == 0
    row = last_run(db)
    assert row["status"] == "OK"
    assert "perdido" in row["detail"]
    assert snapshot(db)["fills"] == before or len(snapshot(db)["fills"]) >= len(before)
    state = SuperbotStore(db).get_meta(alerts.STATE_KEY) or ""
    assert "REGISTRO_INCOMPLETO" in state


class DiskFull(DecisionRecorder):
    """Base sin páginas libres al escribir: SQLite revierte la transacción entera."""

    def flush(self, conn: sqlite3.Connection, run_id: int, entries: bool) -> Optional[str]:
        self._rows.extend(Decision(START, f"X{i}", "RANKING", "x" * 200) for i in range(3000))
        pages = conn.execute("PRAGMA page_count").fetchone()[0]
        conn.execute(f"PRAGMA max_page_count = {pages}")
        return super().flush(conn, run_id, entries)


def test_disco_lleno_no_da_por_buena_una_ejecucion_revertida(store: SuperbotStore) -> None:
    with pytest.raises(sqlite3.Error):
        process(store, data(SAP=[SIGNAL, FLAT]), recorder=DiskFull())
    conn = store.connect()
    conn.execute("PRAGMA max_page_count = 1073741823")
    for table in ("fills", "positions", "symbol_state", "notifications", "decision_runs", "decision_log"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
    process(store, data(SAP=[SIGNAL, FLAT]))
    assert len(store.fills()) == 1


def test_una_sola_perdida_avisa_porque_no_se_recupera() -> None:
    sent: List[str] = []
    alerts.advance({}, START_TIME, {"REGISTRO_INCOMPLETO": "x"}, lambda text: sent.append(text) or True)
    assert len(sent) == 1 and "Entradas bloqueadas" not in sent[0]
