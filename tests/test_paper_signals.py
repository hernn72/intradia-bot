"""T-025 — la evaluación en vivo usa la ruta de P6 (``build_snapshot_series`` + ``_signal`` + contexto PIT)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from paper.signals import evaluate, policy_envs
from paper.universe import load_p6_universe
from tests.conftest import make_ohlcv

UTC = timezone.utc


def _closes(symbol: str, start: float, drift: float, first: str, last: str) -> pd.Series:
    """Cierres en las sesiones reales de la plaza del símbolo, estampados como yfinance (medianoche local)."""

    from datetime import date
    from zoneinfo import ZoneInfo

    from advisor.data.sessions import market_for_symbol, market_session
    from paper.universe import sessions

    market = market_for_symbol(symbol)
    tz = ZoneInfo(market_session(market).timezone)
    days = sessions(market, date.fromisoformat(first), date.fromisoformat(last))
    index = pd.DatetimeIndex([pd.Timestamp(datetime(d.year, d.month, d.day, tzinfo=tz)) for d in days])
    return pd.Series([start + drift * i for i in range(len(days))], index=index)


@pytest.mark.parametrize("policy", ["B2", "S2", "C0"])
def test_evaluacion_en_vivo_reproduce_la_ruta_de_p6(policy: str) -> None:
    from advisor.analysis.snapshot import build_snapshot_series
    from advisor.backtest.engine import _signal
    from advisor.context.point_in_time import PointInTimeContextResolver
    from advisor.data.sessions import market_session

    universe = load_p6_universe()
    asset = next(a for a in universe.assets if a.market == "XETRA" and a.benchmark_symbol is None) if any(
        a.market == "XETRA" and a.benchmark_symbol is None for a in universe.assets) else next(
        a for a in universe.assets if a.market == "XETRA")
    env = policy_envs((policy,))[policy]
    frame = make_ohlcv(n=420, start=40.0, drift=0.08, start_date="2024-09-02")
    j = len(frame) - 1
    analysis_ts = frame.index[-1].to_pydatetime().replace(tzinfo=UTC) + timedelta(days=1, hours=6)
    end = analysis_ts.strftime("%Y-%m-%d")
    closes = {s: _closes(s, 20.0 if s == "^VIX" else 1000.0, 0.0 if s == "^VIX" else 1.0, "2024-01-02", end)
              for s in universe.context_symbols}
    # Solo lo disponible en el instante del análisis (cierre de la sesión más liquidación).
    resolver = PointInTimeContextResolver(closes, env.market_context, asia_symbols=universe.asia_symbols,
                                          settlement_minutes=universe.settlement_minutes)
    live = evaluate(asset, None, frame, j, env, resolver, None, analysis_ts)

    resolved = resolver.resolve(analysis_ts)
    assert resolved.calculable, (resolved.exclusions, resolved.no_calculable_codes)
    window = env.config.horizonte("swing")
    series = build_snapshot_series(frame, env.config.indicators, env.config.levels, window.interval, None,
                                   asset_timezone=market_session(asset.market).timezone, benchmark_timezone=None)
    context_at = [None] * len(frame)
    context_at[j] = resolved.context
    found = _signal(env.advisor_assets[asset.symbol], series, j, env.config, "swing", 120, None, None, None, context_at, "1.0")
    assert found is not None
    assert live["stop"] == pytest.approx(found["levels"].stop)
    assert live["target2"] == pytest.approx(found["levels"].target2)
    assert live["entry_max"] == pytest.approx(found["levels"].entry_max)
    assert live["setup_radar"] == found["setup_radar"] and live["score"] == pytest.approx(found["score"])
    assert live["signal_id"] == found["observation"].signal_id


def test_las_tres_politicas_tienen_niveles_distintos_y_hashes_congelados() -> None:
    from paper.contract import frozen_policy_identities

    ids = frozen_policy_identities()
    assert ids["B2"]["policy_sha256"].startswith("d5d6a533") and ids["S2"]["policy_sha256"].startswith("e37ee933")
    envs = policy_envs(("B2", "S2", "C0"))
    assert envs["B2"].config.levels != envs["S2"].config.levels
    _ = datetime.now(UTC)
