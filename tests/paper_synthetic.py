"""Mercado sintético determinista para los tests de T-025 (sin red, sin datos reales)."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from advisor.research.p6_sim import AssetSeries, FxTable, MarketData, Signal
from paper.engine_v1 import AssetMeta, AssetView, EngineView

# Tres «plazas» con horarios UTC distintos para que los eventos se intercalen.
MARKETS = {
    "XASI": (time(1, 0), time(7, 0), "JPY"),
    "XEUR": (time(8, 0), time(16, 30), "EUR"),
    "XUSA": (time(14, 30), time(21, 0), "USD"),
}


@dataclass(frozen=True)
class Synthetic:
    market: MarketData
    fx: FxTable
    fx_points: Mapping[str, Sequence[Tuple[datetime, float]]]
    signals: List[Signal]
    days: Tuple[date, ...]


def _weekdays(start: date, n: int) -> List[date]:
    out: List[date] = []
    day = start
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day)
        day += timedelta(days=1)
    return out


def build(seed: int = 7, n_assets: int = 12, n_days: int = 150, signal_share: float = 0.12,
          dividend_share: float = 0.02, holiday_share: float = 0.03) -> Synthetic:
    rng = random.Random(seed)
    days = _weekdays(date(2026, 1, 5), n_days)
    assets: Dict[str, AssetSeries] = {}
    signals: List[Signal] = []
    markets = sorted(MARKETS)
    for k in range(n_assets):
        market = markets[k % len(markets)]
        opening, closing, currency = MARKETS[market]
        symbol = f"A{k:02d}.{market}"
        sessions = [d for d in days if rng.random() > holiday_share]
        price = rng.uniform(20, 200)
        o: List[float] = []
        h: List[float] = []
        lo: List[float] = []
        c: List[float] = []
        div: List[float] = []
        for _ in sessions:
            gap = rng.gauss(0, 0.012) + (rng.choice([-0.06, 0.06]) if rng.random() < 0.03 else 0.0)
            open_ = price * (1 + gap)
            close = open_ * (1 + rng.gauss(0.001, 0.02))
            high = max(open_, close) * (1 + abs(rng.gauss(0, 0.012)))
            low = min(open_, close) * (1 - abs(rng.gauss(0, 0.012)))
            o.append(open_)
            h.append(high)
            lo.append(low)
            c.append(close)
            div.append(round(close * 0.01, 4) if rng.random() < dividend_share else 0.0)
            price = close
        opens = tuple(datetime.combine(d, opening, timezone.utc) for d in sessions)
        closes = tuple(datetime.combine(d, closing, timezone.utc) for d in sessions)
        assets[symbol] = AssetSeries(
            symbol=symbol, market=market, currency=currency, economic_currency=currency, region=market,
            sector=f"S{k % 4}", session_dates=tuple(sessions), open_utc=opens, close_utc=closes, open=tuple(o),
            high=tuple(h), low=tuple(lo), close=tuple(c), dividends=tuple(div),
        )
        # Señales solo en la primera parte: todas se cierran por tiempo antes del final (sin salida «final»).
        for j in range(5, len(sessions) - 50):
            if rng.random() < signal_share:
                ref = c[j]
                stop = ref * (1 - rng.uniform(0.02, 0.06))
                target = ref * (1 + rng.uniform(0.05, 0.12))
                entry_max = ref * (1 + rng.uniform(0.0, 0.02))
                analysis_ts = closes[j] + timedelta(minutes=30)
                if j + 1 < len(sessions) and analysis_ts >= opens[j + 1]:
                    continue
                signals.append(Signal(f"{symbol}|swing|{sessions[j].isoformat()}", symbol, j, analysis_ts, stop, target, entry_max))
    fx_points: Dict[str, List[Tuple[datetime, float]]] = {}
    for currency, base in (("USD", 1.10), ("JPY", 160.0)):
        rate = base
        points: List[Tuple[datetime, float]] = []
        for d in [days[0] - timedelta(days=3), *days]:
            rate *= 1 + rng.gauss(0, 0.004)
            points.append((datetime.combine(d, time(0, 0), timezone.utc) + timedelta(hours=24), rate))
        fx_points[currency] = points
    market_data = MarketData(assets=assets, window_start=days[0], window_end=days[-1])
    return Synthetic(market_data, FxTable(fx_points), fx_points, signals, tuple(days))


def meta_of(series: AssetSeries) -> AssetMeta:
    return AssetMeta(series.symbol, series.market, series.currency, series.economic_currency, series.region, series.sector)


def view_at(syn: Synthetic, cut: datetime, *, start: Optional[date] = None, closing_at: Optional[datetime] = None,
            hide: Mapping[str, datetime] | None = None, late_before: Optional[datetime] = None,
            fx_horizon: Optional[datetime] = None) -> EngineView:
    """Vista causal en ``cut``: barras ya cerradas, señales ya emitidas. ``hide`` retrasa la llegada de las
    barras de un activo (sus barras con cierre ≥ esa marca aún no se observaron)."""

    hide = hide or {}
    assets: Dict[str, AssetView] = {}
    for symbol, s in syn.market.assets.items():
        seen_until = min(cut, hide.get(symbol, cut))
        n = sum(1 for close in s.close_utc if close <= seen_until)
        horizon = s.open_utc[n] if n < len(s.session_dates) else None
        dividends = {i: s.dividends[i] for i in range(n) if s.dividends[i] > 0}
        assets[symbol] = AssetView(
            meta=meta_of(s), session_dates=s.session_dates[:n], open_utc=s.open_utc[:n], close_utc=s.close_utc[:n],
            open=s.open[:n], high=s.high[:n], low=s.low[:n], close=s.close[:n], dividends=dividends, horizon=horizon,
        )
    # Una señal vinculante siempre tiene observada su barra t (ficha §7.1).
    signals = tuple(sig for sig in syn.signals
                    if sig.analysis_ts <= cut and sig.bar_index < len(assets[sig.asset].session_dates))
    days = tuple(sorted({d for s in syn.market.assets.values() for d in s.session_dates}))
    return EngineView(
        assets=assets, fx=syn.fx, signals=signals, start=start or syn.days[0], snapshot_days=days, limit=cut,
        closing_at=closing_at, late_before=late_before, fx_horizon=fx_horizon,
    )
