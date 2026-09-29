"""Qué VIX y qué tendencia asigna el laboratorio (event_study._align) a cada barra de señal.

Solo lectura, sobre la cosecha congelada. Para cada barra: su sesión local real,
la etiqueta de fecha que le da _naive_dates, y la sesión real del VIX (tras
.shift(1)) y del ^STOXX50E que el laboratorio le asigna.
"""
from zoneinfo import ZoneInfo

import pandas as pd

from advisor.config import load_config
from advisor.data.freshness import mercado_para_simbolo
from advisor.data.sessions import market_for_symbol, market_session
from advisor.research.event_study import _align, _naive_dates
from advisor.research.vintage import frozen_close, load_vintage
from advisor.universe.loader import load_universe

VID = "071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841"
cfg = load_config("config.yaml")
uni = load_universe(cfg.universe_path)
v = load_vintage(VID)

def market(sym):
    if sym.startswith("^"):
        return market_for_symbol(sym)
    a = uni.get(sym)
    return mercado_para_simbolo(a, sym) if a is not None else market_for_symbol(sym)

def sessions(sym):
    """Serie etiqueta_naive -> sesión local real de cada barra del símbolo."""
    close = frozen_close(v, sym)
    utc = pd.DatetimeIndex(close.index)
    zone = ZoneInfo(market_session(market(sym)).timezone)
    real = [t.tz_convert(zone).date() for t in utc]
    return close, pd.Series(real, index=close.index)

MK = {"^VIX": market_for_symbol("^VIX"), "^STOXX50E": market_for_symbol("^STOXX50E")}
vix, vix_real = sessions("^VIX")
trend, trend_real = sessions("^STOXX50E")
print("tipo de indice de la cosecha:", type(vix.index).__name__, "ejemplo:", vix.index[-1])
for sym in ("SAP.DE", "7203.T", "AAPL", "0700.HK", "BTC-EUR"):
    if frozen_close(v, sym) is None:
        print("\n==", sym, "no esta en la cosecha")
        continue
    close, real = sessions(sym)
    idx = close.index[-6:]
    vix_used = _align(vix_real.map(lambda d: pd.Timestamp(d).toordinal()).astype(float).set_axis(vix.index), close.index).shift(1)
    trend_used = _align(trend_real.map(lambda d: pd.Timestamp(d).toordinal()).astype(float).set_axis(trend.index), close.index)
    print(f"\n== {sym} ({market(sym)})")
    print("  sesion real barra | etiqueta _naive_dates | sesion real VIX usado (shift 1) | sesion real ^STOXX50E usado")
    for t in idx:
        lab = _naive_dates(pd.Index([t]))[0].date()
        fv = vix_used.loc[t]
        ft = trend_used.loc[t]
        dv = pd.Timestamp.fromordinal(int(fv)).date() if pd.notna(fv) else None
        dt = pd.Timestamp.fromordinal(int(ft)).date() if pd.notna(ft) else None
        print(f"  {real.loc[t]} | {lab} | {dv} | {dt}")
