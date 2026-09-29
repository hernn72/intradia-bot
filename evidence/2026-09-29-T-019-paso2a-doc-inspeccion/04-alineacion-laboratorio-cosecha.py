"""Recuento sobre toda la cosecha: sesión real de VIX y ^STOXX50E que el
laboratorio (event_study._align) asigna a cada barra de señal, frente a la
sesión real de la barra. Solo lectura. No mira desenlaces ni scores."""
from collections import Counter, defaultdict
from zoneinfo import ZoneInfo

import pandas as pd

from advisor.config import load_config
from advisor.data.freshness import mercado_para_simbolo
from advisor.data.sessions import market_for_symbol, market_session
from advisor.research.event_study import _align
from advisor.research.vintage import frozen_close, load_vintage
from advisor.universe.loader import load_universe

VID = "071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841"
cfg = load_config("config.yaml")
uni = load_universe(cfg.universe_path)
v = load_vintage(VID)

def real_ordinals(sym, mkt):
    close = frozen_close(v, sym)
    zone = ZoneInfo(market_session(mkt).timezone)
    return pd.Series([float(pd.DatetimeIndex([t])[0].tz_convert(zone).toordinal()) for t in close.index], index=close.index)

vix_o = real_ordinals("^VIX", market_for_symbol("^VIX"))
tr_o = real_ordinals("^STOXX50E", market_for_symbol("^STOXX50E"))
trend_ahead = Counter()
total = Counter()
vix_lag = defaultdict(Counter)
for a in uni.analizables():
    sym = a.primary_symbol
    if frozen_close(v, sym) is None:
        continue
    mkt = mercado_para_simbolo(a, sym)
    bar = real_ordinals(sym, mkt)
    vix_used = _align(vix_o, bar.index).shift(1)
    tr_used = _align(tr_o, bar.index)
    for t in bar.index:
        total[mkt] += 1
        if pd.notna(tr_used.loc[t]) and tr_used.loc[t] > bar.loc[t]:
            trend_ahead[mkt] += 1
        if pd.notna(vix_used.loc[t]):
            # retraso del VIX en sesiones reales del VIX
            lag = int(((vix_o > vix_used.loc[t]) & (vix_o <= bar.loc[t])).sum())
            vix_lag[mkt][lag] += 1
print("mercado | barras | tendencia de una sesion POSTERIOR a la barra | retraso del VIX en sesiones VIX (0 = misma fecha que la barra)")
for m in sorted(total):
    print(f"{m:7s} | {total[m]:6d} | {trend_ahead[m]:6d} ({trend_ahead[m]/total[m]:.0%}) | {dict(sorted(vix_lag[m].items()))}")
