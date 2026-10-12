"""Revisor final: paridad R-CTX/INV-06 sobre la cosecha REAL, sin desenlaces.
Para una muestra de señales de varias plazas compara el MarketContext que
obtienen producción v2 (run_analysis con score "2.0"), seguimiento
(review_positions con el selector forzado a PIT, porque v2 no es activable),
backtest (run_backtest con vintage y score "2.0") y event study (score "2.0")."""
import random, sys
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, ".")
import pandas as pd
import advisor.research.event_study as es
import advisor.backtest.runner as br
import advisor.analysis.analyzer as an
import advisor.report.tracking as tr
from advisor.config import load_config
from advisor.universe.loader import load_universe
from advisor.universe.models import Universe
from advisor.research.vintage import load_vintage, frozen_close
from advisor.research.p3 import DATA_VINTAGE_ID
from advisor.analysis.overview import context_assets_of
from advisor.context.point_in_time import PointInTimeContextResolver, analysis_timestamp_for_signal
from advisor.data.freshness import mercado_para_simbolo
from advisor.data.sessions import session_date_of

cfg = load_config("config.yaml"); uni = load_universe(cfg.universe_path); vin = load_vintage(DATA_VINTAGE_ID)
ctx_assets = list(context_assets_of(uni))
asia = tuple(sorted(a.primary_symbol for a in ctx_assets if a.region == "ASIA"))
closes = {s: frozen_close(vin, s) for s in (cfg.market_context.vix_symbol, cfg.market_context.trend_symbol, *asia)}
resolver = PointInTimeContextResolver(closes, cfg.market_context, asia_symbols=asia, settlement_minutes=cfg.data_quality.settlement_minutes)

class FakeProvider:
    def get_history(self, symbol, period="2y", interval="1d", **kw):
        v = vin.by_symbol.get(symbol)
        if v is None: raise RuntimeError(f"sin {symbol}")
        return v.signal_prices.copy()
    def __getattr__(self, name):
        raise AttributeError(name)

class FakeDB:
    def __init__(self, a): self.a = a
    def list_open_positions(self):
        return [{"id": 1, "symbol": self.a.symbol, "name": self.a.name, "currency": self.a.currency, "opened_at": "2020-01-01T00:00:00Z",
                 "entry_price": 100.0, "quantity": 1.0, "stop": 90.0, "target": 150.0, "horizonte": "swing", "thesis": "x"}]
    def insert_review(self, **kw): return None

SAMPLE = ["SAP.DE", "AIR.PA", "ASML.AS", "BBVA.MC", "AAPL", "IBM", "7203.T", "0700.HK", "AZN"]
assets = [a for a in uni.analizables(None) if a.symbol in SAMPLE]
rng = random.Random(7)
total = 0; fails = []
for asset in assets:
    sub = Universe(groups={"activos": [asset], "contexto_rev": [a for a in ctx_assets if a.symbol != asset.symbol]})
    assert tuple(sorted(a.primary_symbol for a in context_assets_of(sub) if a.region == "ASIA")) == asia
    market = mercado_para_simbolo(asset, asset.primary_symbol)
    idx = vin.by_symbol[asset.primary_symbol].signal_prices.index
    # event study
    ev = {}
    orig = es._build_event_signal
    def cap(*a, **k):
        ev.setdefault("list", a[9]); return None
    with patch.object(es, "_build_event_signal", cap), patch.object(es, "evaluate_managed_event", lambda *a, **k: None), \
         patch.object(es, "evaluate_potential_event", lambda *a, **k: None):
        es.run_event_study_on_vintage(cfg, sub, vin, horizonte="swing", score_model_version="2.0")
    # backtest
    bt = {}
    def sim(*a, **k):
        bt.setdefault("list", k["market_context_at"]); return []
    with patch.object(br, "simulate_asset", sim):
        br.run_backtest(cfg, sub, None, horizonte="swing", vintage=vin, score_model_version="2.0")
    assert len(ev["list"]) == len(idx) == len(bt["list"]), (len(ev["list"]), len(idx), len(bt["list"]))
    js = rng.sample(range(260, len(idx) - 1), 6)
    for j in js:
        d = session_date_of(idx[j], market); d1 = session_date_of(idx[j + 1], market)
        ts = analysis_timestamp_for_signal(market, d, d1, settlement_minutes=20)
        exp = resolver.resolve(ts).context
        prod = []
        def pa(*a, **k):
            prod.append(a[3]); raise RuntimeError("capturado")
        with patch.object(an, "analyze_asset", pa), patch.object(an, "fetch_overview", lambda *a, **k: []):
            an.run_analysis(cfg, sub, FakeProvider(), horizonte="swing", score_model_version="2.0", now=ts)
        trk = []
        def ta(*a, **k):
            trk.append(a[3]); return SimpleNamespace(score=SimpleNamespace(value=50.0), snapshot=SimpleNamespace(price=110.0))
        with patch.object(tr, "context_mode_for", lambda v: "point_in_time"), patch.object(tr, "analyze_asset", ta):
            try:
                tr.review_positions(cfg, sub, FakeDB(asset), FakeProvider(), "rev", now=ts)
            except Exception as exc:
                trk.append(f"error {exc}")
        paths = {"evento": ev["list"][j], "backtest": bt["list"][j], "produccion": prod[0] if prod else None, "seguimiento": trk[0] if trk else None}
        total += 1
        bad = {k: v for k, v in paths.items() if v != exp}
        if bad or exp is None:
            fails.append((asset.symbol, d, ts, exp, bad))
        else:
            print(f"OK {asset.symbol:8s} señal {d} ts {ts.isoformat()} VIX={exp.vix_value:.2f} tend={exp.trend_price:.1f}/{exp.trend_sma:.1f} asia={exp.asia_change_pct:+.3f} pts={exp.points} source={exp.source}")
print(f"comparaciones={total} fallos={len(fails)}")
for f in fails: print("FALLO", f)
