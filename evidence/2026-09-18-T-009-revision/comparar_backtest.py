"""Simula una serie fija y escribe las operaciones, para comparar dos codigos."""
import sys, json
import numpy as np, pandas as pd
from advisor.backtest.engine import POLICY_OPERAR, POLICY_TODAS, simulate_asset
from advisor.config import AdvisorConfig
from advisor.universe.models import Asset

rng = np.random.default_rng(20260918)
n = 900
idx = pd.date_range("2022-01-03", periods=n, freq="B")
paso = rng.normal(0.0006, 0.013, n).cumsum()
close = 100 * np.exp(paso)
open_ = np.concatenate([[close[0]], close[:-1] * (1 + rng.normal(0, 0.004, n - 1))])
high = np.maximum(open_, close) * (1 + abs(rng.normal(0, 0.006, n)))
low = np.minimum(open_, close) * (1 - abs(rng.normal(0, 0.006, n)))
df = pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close,
                   "Volume": np.full(n, 3_000_000.0)}, index=idx)

asset = Asset(symbol="SAP.DE", name="SAP", asset_class="stock", region="EUROPA",
              market="XETRA", currency="EUR", timezone="Europe/Berlin",
              trade_republic="yes", isin=None)
config = AdvisorConfig(
    base_currency="EUR",
    horizontes={
        "intradia": {"interval": "15m", "period": "60d", "min_bars": 120},
        "swing": {"interval": "1d", "period": "1y", "min_bars": 120},
        "medio": {"interval": "1d", "period": "2y", "min_bars": 250},
    },
)
salida = {}
for policy in (POLICY_OPERAR, POLICY_TODAS):
    for horizonte in ("swing", "medio"):
        trades = simulate_asset(asset, df, config, horizonte, policy, cost_pct=0.2, min_bars=120)
        salida[f"{policy}-{horizonte}"] = [
            [t.entry_date.isoformat(), round(t.entry_price, 6), round(t.exit_price, 6),
             t.exit_reason, t.accion, round(t.net_r_multiple, 6)] for t in trades
        ]
print(json.dumps(salida, sort_keys=True))
