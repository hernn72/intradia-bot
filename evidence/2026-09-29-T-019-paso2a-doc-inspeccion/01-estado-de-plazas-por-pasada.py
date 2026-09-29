"""Estado de cada serie de contexto a cada hora de pasada del timer (solo lectura, sin red).

Usa las funciones de calendario del propio repo (advisor.data.sessions) y el
universo vigente. Las horas de los timers son hora local de la Pi (Europe/London).
"""
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from advisor.analysis.overview import context_assets_of
from advisor.config import load_config
from advisor.data.sessions import latest_expected_closed_session, market_for_symbol, market_state, session_close_at
from advisor.universe.loader import load_universe

LONDON = ZoneInfo("Europe/London")
UTC = ZoneInfo("UTC")
cfg = load_config("config.yaml")
settle = cfg.data_quality.settlement_minutes
uni = load_universe(cfg.universe_path)
ctx = context_assets_of(uni)
asia = sorted(a.symbol for a in ctx if a.region == "ASIA")
print("settlement_minutes =", settle)
print("context_assets_of(universe) region ASIA ->", asia)
print("mercado por serie:", {s: market_for_symbol(s) for s in [*asia, "^VIX", cfg.market_context.trend_symbol]})
print("vix_symbol =", cfg.market_context.vix_symbol, "| trend_symbol =", cfg.market_context.trend_symbol)
print()
PASADAS = [time(7, 0), time(8, 30), time(14, 30), time(21, 0), time(22, 30)]
for dia in (date(2026, 9, 29), date(2026, 1, 13)):
    print(f"=== {dia} ({'BST, UTC+1' if dia.month == 9 else 'GMT, UTC+0'}) ===")
    for hora in PASADAS:
        ref = datetime.combine(dia, hora, LONDON)
        print(f"-- pasada {hora:%H:%M} Londres = {ref.astimezone(UTC):%H:%M} UTC")
        for s in [*asia, "^VIX", cfg.market_context.trend_symbol]:
            m = market_for_symbol(s)
            st = market_state(m, ref)
            last = latest_expected_closed_session(m, ref, settlement_minutes=settle)
            close = session_close_at(m, last) if last else None
            print(f"   {s:10s} {m:6s} estado={st:9s} ultima_cerrada_exigible={last} cierre={close.astimezone(UTC):%Y-%m-%d %H:%M}Z" if close else f"   {s} {m} {st} {last}")
    print()
