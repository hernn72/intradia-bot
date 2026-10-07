"""Entorno de prueba de T-025: universo de tres plazas reales, proveedor falso determinista, sin red."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

import pandas as pd

from paper.contract import build_contracts
from paper.environment import Environment
from paper.runner import init_cohorts, run_pass
from paper.signals import PolicyEnv
from paper.store import PaperStore
from paper.universe import FX_MARKET, PaperAsset, PaperUniverse, scheduled_passes, sessions

UTC = timezone.utc
START = date(2026, 3, 2)
CODE_SHA = "c" * 40
ENV = Environment("3.12.0", ("pandas==3.0.5", "yfinance==1.7.0"), "r" * 64)

ASSETS = (
    PaperAsset("TSTA.DE", "TSTA.DE", "XETRA", "EUR", "EUR", "EUROPA", "S0", "INST-A"),
    PaperAsset("TSTB", "TSTB", "NASDAQ", "USD", "USD", "USA", "S1", "INST-B"),
    PaperAsset("TSTC.HK", "TSTC.HK", "HKG", "HKD", "HKD", "ASIA", "S2", "INST-C"),
)
UNIVERSE = PaperUniverse(
    assets=ASSETS, context_symbols=("^VIX", "^STOXX50E", "^N225"), asia_symbols=("^N225",), vix_symbol="^VIX",
    trend_symbol="^STOXX50E", settlement_minutes=20,
)
MARKET_TZ = {"XETRA": "Europe/Berlin", "NASDAQ": "America/New_York", "HKG": "Asia/Hong_Kong", "NYSE": "America/New_York",
             "JPX": "Asia/Tokyo", FX_MARKET: "Europe/London"}
SYMBOL_MARKET = {"^VIX": "NYSE", "^STOXX50E": "XETRA", "^N225": "JPX", "EURUSD=X": FX_MARKET, "EURHKD=X": FX_MARKET,
                 **{a.symbol: a.market for a in ASSETS}}


def _frame(symbol: str, seed: int, *, base: float, dividends: Dict[date, float], splits: Dict[date, float]) -> pd.DataFrame:
    market = SYMBOL_MARKET[symbol]
    rng = random.Random(seed)
    days = sessions(market, date(2024, 1, 2), date(2026, 12, 31))
    tz = ZoneInfo(MARKET_TZ[market])
    price = base
    rows = []
    for day in days:
        if day in splits:
            price = price / splits[day]  # desde la apertura de la fecha ex, la escala nueva
        open_ = price * (1 + rng.gauss(0, 0.008))
        close = open_ * (1 + rng.gauss(0.0006, 0.015))
        high = max(open_, close) * (1 + abs(rng.gauss(0, 0.008)))
        low = min(open_, close) * (1 - abs(rng.gauss(0, 0.008)))
        rows.append({"ts": pd.Timestamp(datetime(day.year, day.month, day.day, tzinfo=tz)), "Open": open_, "High": high,
                     "Low": low, "Close": close, "Volume": 1e6, "Dividends": dividends.get(day, 0.0),
                     "Stock Splits": 0.0})
        price = close
    return pd.DataFrame(rows).set_index("ts")


@dataclass
class FakeProvider:
    """``get_raw_history`` determinista. ``hide`` oculta sesiones de un símbolo hasta una fecha de consulta;
    ``down`` hace fallar todo (red caída); ``calls`` registra las peticiones."""

    frames: Dict[str, pd.DataFrame]
    now: Callable[[], datetime]
    hide: Dict[str, Tuple[date, date, Optional[datetime]]] = field(default_factory=dict)
    down: bool = False
    calls: List[Tuple[str, str, str]] = field(default_factory=list)
    splits: Dict[str, Tuple[date, float]] = field(default_factory=dict)

    def get_raw_history(self, symbol: str, period: str = "1y", interval: str = "1d", *, drop_na: bool = True,
                        start: Optional[str] = None, end: Optional[str] = None) -> pd.DataFrame:
        self.calls.append((symbol, str(start), str(end)))
        if self.down:
            raise ConnectionError("red caída")
        frame = self.frames.get(symbol)
        if frame is None:
            raise ValueError(f"No se han recibido datos para el símbolo '{symbol}'")
        assert start is not None and end is not None
        lo, hi = date.fromisoformat(start), date.fromisoformat(end)
        out = frame[[lo <= ts.date() < hi for ts in frame.index]].copy()
        split = self.splits.get(symbol)
        if split is not None and self.now().date() >= split[0]:
            # Como yfinance: una vez ocurrido el split, la serie anterior a la fecha ex llega reajustada.
            ex_date, ratio = split
            before = [ts.date() < ex_date for ts in out.index]
            for column in ("Open", "High", "Low", "Close"):
                out.loc[before, column] = out.loc[before, column] / ratio
            out.loc[[ts.date() == ex_date for ts in out.index], "Stock Splits"] = ratio
        hidden = self.hide.get(symbol)
        if hidden is not None:
            first, last, until = hidden
            if until is None or self.now() < until:
                out = out[[not (first <= ts.date() <= last) for ts in out.index]]
        if out.empty:
            raise ValueError(f"No se han recibido datos para el símbolo '{symbol}'")
        return out


def frames(seed: int = 1, *, dividends: Optional[Dict[str, Dict[date, float]]] = None,
           splits: Optional[Dict[str, Dict[date, float]]] = None) -> Dict[str, pd.DataFrame]:
    dividends = dividends or {}
    splits = splits or {}
    out = {}
    for k, symbol in enumerate(["TSTA.DE", "TSTB", "TSTC.HK", "^VIX", "^STOXX50E", "^N225"]):
        out[symbol] = _frame(symbol, seed + k, base=[50, 120, 80, 18, 5000, 38000][k],
                             dividends=dividends.get(symbol, {}), splits=splits.get(symbol, {}))
    for k, (pair, base) in enumerate((("EURUSD=X", 1.10), ("EURHKD=X", 8.6))):
        out[pair] = _frame(pair, seed + 10 + k, base=base, dividends={}, splits={})
    return out


def fake_evaluator(asset: PaperAsset, info: Any, frame: pd.DataFrame, j: int, env: PolicyEnv, resolver: Any,
                   benchmark: Any, analysis_ts: datetime) -> Dict[str, Any]:
    """Evaluación determinista que no depende de ningún libro: OPERAR algunos días, con niveles del cierre."""

    close = float(frame["Close"].iloc[j])
    day = info.sessions[j]
    operar = int((day.toordinal() + len(asset.symbol)) % 3 == 0)
    stop_pct = {"B2": 0.04, "S2": 0.03, "C0": 0.04}[env.policy_id]
    return {
        "reference_price": close, "entry_max": close * 1.01, "stop": close * (1 - stop_pct), "target1": close * 1.03,
        "target2": close * 1.08, "target3": close * 1.12, "rr_at_reference": 2.0, "risk_fraction": stop_pct,
        "score": 75.0, "setup_radar": "OPERAR" if operar else "VIGILAR", "setup_accion": "COMPRAR" if operar else "ESPERAR",
        "operar": operar, "context_json": "{}", "reasons": "",
    }


ENVS = {p: PolicyEnv(p, None, {}, None, 1.5) for p in ("B2", "S2", "C0")}


@dataclass
class Clock:
    current: datetime

    def __call__(self) -> datetime:
        self.current += timedelta(seconds=1)
        return self.current


def make_store(tmp: Path, name: str = "paper.db", start: date = START) -> PaperStore:
    store = PaperStore.open(tmp / name, create=True)
    contracts = build_contracts(
        start, CODE_SHA, identities={p: {"policy_sha256": p * 32, "advisor_config_hash": p * 32} for p in ("B2", "S2", "C0")},
        system_hashes={"B2": "b" * 64, "S2": "s" * 64, "C0": "0" * 64, "BH": "h" * 64}, asset_list_sha256="a" * 64,
        universe_vintage_id="u" * 64, universe_size=len(ASSETS),
    )
    init_cohorts(store, contracts, ENV, now=datetime(2026, 3, 1, 12, tzinfo=UTC))
    return store


def passes_between(first: date, last: date) -> List[datetime]:
    return scheduled_passes(datetime(first.year, first.month, first.day, tzinfo=UTC),
                            datetime(last.year, last.month, last.day, 23, 59, tzinfo=UTC))


def run_passes(store: PaperStore, provider: FakeProvider, clock: Clock, passes: List[datetime], *, env: Environment = ENV,
               identity_ok: Callable[[str], bool] = lambda _sha: True, skip: Set[datetime] = frozenset()) -> List[Any]:  # type: ignore[assignment]
    reports = []
    for pass_ts in passes:
        if pass_ts in skip:
            continue
        clock.current = max(clock.current, pass_ts + timedelta(minutes=2))
        reports.append(run_pass(store, UNIVERSE, provider, pass_ts=pass_ts, clock=clock, code_sha=CODE_SHA,
                                environment=env, envs=ENVS, identity_ok=identity_ok, evaluator=fake_evaluator,
                                lock_wait_seconds=2.0))
    return reports
