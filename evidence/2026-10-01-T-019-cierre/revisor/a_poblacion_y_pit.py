"""Revisor final T-019: reconstruye la población P3 SIN desenlaces, recalcula
cortes con una implementación propia y audita el contexto PIT con un cálculo
independiente (exchange_calendars crudo + overrides D-54 escritos a mano).
No escribe en el repo. Ejecutar con cwd = raíz del repo."""
from __future__ import annotations
import hashlib, json, math, sys, time as _t
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from unittest.mock import patch

import numpy as np
import pandas as pd
import exchange_calendars as xcals

sys.path.insert(0, ".")
import advisor.research.event_study as es
import advisor.research.p3 as p3
from advisor.config import load_config
from advisor.universe.loader import load_universe
from advisor.research.vintage import load_vintage, frozen_close
from advisor.data.freshness import mercado_para_simbolo
from advisor.data.sessions import session_date_of, MARKET_SESSIONS
from advisor.context.point_in_time import PointInTimeContextResolver, analysis_timestamp_for_signal
from advisor.analysis.overview import context_assets_of

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
log = open(OUT / "a_salida.txt", "w")
def say(*a):
    s = " ".join(str(x) for x in a); print(s); log.write(s + "\n"); log.flush()

cfg = load_config("config.yaml"); universe = load_universe(cfg.universe_path)
vintage = load_vintage(p3.DATA_VINTAGE_ID)
say("config score_model_version activo:", cfg.scoring.score_model_version)

# --- Guardia: el camino PIT de P3 no puede tocar _align/_naive_dates ni desenlaces
state = {"pit": False, "align_in_pit": 0, "outcome_calls": 0}
orig_align = es._align
def guarded_align(*a, **k):
    if state["pit"]:
        state["align_in_pit"] += 1
        raise AssertionError("_align llamado en camino PIT")
    return orig_align(*a, **k)
orig_run = p3.run_p3_event_study
def guarded_run(*a, **k):
    assert k.get("with_outcomes") is False
    state["pit"] = True
    try:
        return orig_run(*a, **k)
    finally:
        state["pit"] = False
def boom(*a, **k):
    state["outcome_calls"] += 1
    raise AssertionError("desenlace calculado")

# ---- auditoría independiente: calendarios crudos + overrides de la ficha
D54 = {"XHKG": {date(2023,9,1), date(2023,9,8)}, "XTAI": {date(2023,1,18), date(2024,10,31), date(2026,7,10)},
       "XKRX": {date(2026,6,3), date(2026,7,17)}}  # XKRX: overrides previos del yaml
CALS = {}
def cal(mic):
    if mic not in CALS:
        CALS[mic] = xcals.get_calendar(mic, start="2019-01-01", end="2026-12-31")
    return CALS[mic]
SESS = {}
def sessions(mic):
    if mic not in SESS:
        c = cal(mic); s = [d.date() for d in c.sessions]
        SESS[mic] = [d for d in s if d not in D54.get(mic, set())]
    return SESS[mic]
CLOSE = {}
def close_at(mic, d):
    k = (mic, d)
    if k not in CLOSE:
        CLOSE[k] = cal(mic).session_close(pd.Timestamp(d)).to_pydatetime()
    return CLOSE[k]
LON = ZoneInfo("Europe/London")
PASSES = (time(7,0), time(8,30), time(14,30), time(21,0))
from functools import lru_cache
@lru_cache(maxsize=None)
def indep_ts(mic, d, d1):
    avail = close_at(mic, d) + timedelta(minutes=20)
    opened = cal(mic).session_open(pd.Timestamp(d1)).to_pydatetime()
    best = None
    day = avail.astimezone(LON).date() - timedelta(days=1)
    while day <= opened.astimezone(LON).date() + timedelta(days=1):
        if day.weekday() < 5:
            for t in PASSES:
                p = datetime.combine(day, t, LON).astimezone(timezone.utc)
                if avail <= p < opened and (best is None or p > best):
                    best = p
        day += timedelta(days=1)
    return best

TZ = {"^VIX": ("XNYS", "America/New_York"), "^STOXX50E": ("XETR", "Europe/Berlin"),
      "^N225": ("XTKS", "Asia/Tokyo"), "^HSI": ("XHKG", "Asia/Hong_Kong"), "^KS11": ("XKRX", "Asia/Seoul"),
      "^TWII": ("XTAI", "Asia/Taipei"), "510300.SS": ("XSHG", "Asia/Shanghai")}
asia_symbols = tuple(sorted(a.primary_symbol for a in context_assets_of(universe) if a.region == "ASIA"))
say("asia_symbols", asia_symbols)
raw = {}
for sym in ("^VIX", "^STOXX50E", *asia_symbols):
    s = frozen_close(vintage, sym)
    mic, tz = TZ[sym]
    valid = set(sessions(mic))
    pts = {}
    for ts_, v in s.items():
        if pd.isna(v): continue
        d = pd.Timestamp(ts_).tz_convert(tz).date() if pd.Timestamp(ts_).tzinfo else pd.Timestamp(ts_).date()
        if d in valid:
            pts[d] = float(v)
    ds = sorted(pts)
    raw[sym] = (mic, ds, [pts[d] for d in ds], [close_at(mic, d) + timedelta(minutes=20) for d in ds])
import bisect
@lru_cache(maxsize=None)
def indep_ctx(ts):
    out = {}
    mic, ds, vs, av = raw["^VIX"]; i = bisect.bisect_right(av, ts)
    out["vix_session"] = ds[i-1] if i else None; out["vix"] = vs[i-1] if i else None
    out["vix_avail"] = av[i-1] if i else None
    mic, ds, vs, av = raw["^STOXX50E"]; i = bisect.bisect_right(av, ts)
    out["trend_session"] = ds[i-1] if i else None; out["trend"] = vs[i-1] if i else None
    out["trend_avail"] = av[i-1] if i else None
    out["trend_count"] = i
    out["sma"] = float(np.mean(vs[i-200:i])) if i >= 200 else None
    changes = []; missing = False; used = {}
    for sym in asia_symbols:
        mic, ds, vs, av = raw[sym]
        sess = sessions(mic)
        closed = [d for d in sess if close_at(mic, d) + timedelta(minutes=20) <= ts and d > (ts.date() - timedelta(days=60))]
        L = closed[-1]; P = sess[sess.index(L) - 1]
        dmap = dict(zip(ds, vs))
        used[sym] = (L, P, close_at(mic, L) + timedelta(minutes=20))
        if L not in dmap or P not in dmap:
            missing = True; continue
        changes.append((dmap[L] / dmap[P] - 1) * 100)
    out["asia_missing"] = missing
    out["asia"] = None if missing else sum(changes) / len(changes)
    out["asia_used"] = used
    return out

def vix_points(v, thr=25.0):
    if v <= 0.6 * thr: return 4.0
    if v < thr: return 2.8
    if v < 1.4 * thr: return 1.2
    return 0.0
def asia_points(a):
    if a >= 0.5: return 2.0
    if a > -0.5: return 1.0
    if a > -1.5: return 0.5
    return 0.0

def nr(sorted_vals, k):  # implementación propia nearest-rank, entera
    n = len(sorted_vals); idx = -(-k * n // 100) - 1
    return sorted_vals[idx]

summary = {}
for h in ("swing", "medio"):
    t0 = _t.time()
    with patch.object(es, "_align", guarded_align), patch.object(p3, "run_p3_event_study", guarded_run), \
         patch.object(es, "evaluate_managed_event", boom), patch.object(es, "evaluate_potential_event", boom):
        # build_population parchea internamente los desenlaces a None; nuestro boom se sustituye
        pop = p3.build_population(cfg, universe, vintage, h, with_outcomes=False)
    say(f"[{h}] build_population {(_t.time()-t0):.0f}s align_en_PIT={state['align_in_pit']} outcome_calls={state['outcome_calls']}")
    recs = pop.records
    assert all(r.net_r is None and r.signal is None for r in recs)
    say(f"[{h}] checks del ejecutor:", all(ok for *_, ok in pop.checks))
    for name, obs, want, ok in pop.checks:
        say(f"    {'OK ' if ok else 'FALLA'} {name}: {obs} (esperado {want})")
    c = pop.census; rows = c.rows_by_reason
    asia = {(str(r[0]), r[1]) for r in rows["excluded_asia_missing"]}
    sma = {(str(r[0]), r[1]) for r in rows["excluded_trend_sma_history"]}
    cry = {(str(r[0]), r[1]) for r in rows["excluded_crypto"]}
    say(f"[{h}] A02={c.a02_population} cripto={len(rows['excluded_crypto'])} asia={len(rows['excluded_asia_missing'])} "
        f"sma={len(rows['excluded_trend_sma_history'])} asia∩sma={len(asia & sma)} cripto∩otros={len(cry & (asia|sma))} "
        f"union={len(asia|sma|cry)} final={len(c.final_population)} A02-union={c.a02_population-len(asia|sma|cry)}")
    # hash propio
    keys = []
    region_assets = defaultdict(set)
    dump = []
    ts_mismatch = 0; ctx_mismatch = 0; lookahead = 0; pts_mismatch = 0; checked = 0
    resolver = PointInTimeContextResolver({s: frozen_close(vintage, s) for s in ("^VIX", "^STOXX50E", *asia_symbols)},
                                          cfg.market_context, asia_symbols=asia_symbols,
                                          settlement_minutes=cfg.data_quality.settlement_minutes)
    examples = []
    max_ts_minus_used = None
    for r in recs:
        # localizar la señal: necesitamos sesión e índice; reconstruimos desde result
        pass
    # usar result.signals (mismo orden que records)
    for sig, r in zip(pop.result.signals, recs):
        a = universe.get(sig.observation.asset)
        views = vintage.by_symbol[a.primary_symbol]
        market = mercado_para_simbolo(a, a.primary_symbol)
        mic = MARKET_SESSIONS[market].mic
        j = sig.observation.signal_idx
        d = session_date_of(views.signal_prices.index[j], market)
        d1 = session_date_of(views.signal_prices.index[j + 1], market)
        keys.append((a.symbol, d)); region_assets[a.region].add(a.symbol)
        ts_mod = analysis_timestamp_for_signal(market, d, d1, settlement_minutes=20)
        ts_ind = indep_ts(mic, d, d1)
        if ts_mod != ts_ind: ts_mismatch += 1
        res = resolver.resolve(ts_mod)
        ind = indep_ctx(ts_mod)
        ctx = res.context
        checked += 1
        # look-ahead: todo dato usado disponible <= ts
        used_avail = [ind["vix_avail"], ind["trend_avail"]] + [u[2] for u in ind["asia_used"].values()]
        if any(x is None or x > ts_mod for x in used_avail): lookahead += 1
        gap = min((ts_mod - x).total_seconds() for x in used_avail)
        max_ts_minus_used = gap if max_ts_minus_used is None else min(max_ts_minus_used, gap)
        ok = (ctx is not None and res.vix_session == ind["vix_session"] and res.trend_used_session == ind["trend_session"]
              and res.trend_sma_count == ind["trend_count"] and abs(ctx.vix_value - ind["vix"]) < 1e-12
              and abs(ctx.trend_price - ind["trend"]) < 1e-9 and ind["sma"] is not None and abs(ctx.trend_sma - ind["sma"]) < 1e-6
              and not ind["asia_missing"] and abs(ctx.asia_change_pct - ind["asia"]) < 1e-9
              and all(res.asia_sessions[s] == (ind["asia_used"][s][0], ind["asia_used"][s][1]) for s in asia_symbols))
        if not ok:
            ctx_mismatch += 1
            if len(examples) < 5: examples.append((a.symbol, d, ts_mod, res.vix_session, ind["vix_session"], res.trend_used_session, ind["trend_session"]))
        # puntos del contexto independientes vs dimensión contexto de la observación
        trend_pts = 4.0 if ind["trend"] > ind["sma"] else 0.0
        exp_pts = trend_pts + vix_points(ind["vix"]) + asia_points(ind["asia"])
        dims = {dm.name: dm for dm in sig.observation.dimensions}
        if abs(dims["contexto"].points - exp_pts) > 1e-9: pts_mismatch += 1
        dump.append((a.symbol, d.isoformat(), d1.isoformat(), market, r.block, repr(r.score),
                     repr(r.ablated_scores["catalizador"]), repr(r.ablated_scores["tecnico"]), repr(r.ablated_scores["contexto"]),
                     ts_mod.isoformat(), repr(exp_pts), repr(dims["contexto"].points), str(sig.observation.evaluable_max)))
    say(f"[{h}] auditoría PIT sobre {checked} señales: ts distinto={ts_mismatch} contexto distinto={ctx_mismatch} "
        f"look-ahead={lookahead} puntos contexto distintos={pts_mismatch} margen mínimo ts−available_at={max_ts_minus_used}s")
    if examples: say("   ejemplos:", examples)
    sha = hashlib.sha256("\n".join(sorted(f"{s}\t{d}" for s, d in keys)).encode()).hexdigest()
    say(f"[{h}] n={len(recs)} sha={sha} activos={len({k[0] for k in keys})} regiones=" +
        str({k: len(v) for k, v in sorted(region_assets.items())}))
    blocks = Counter(r.block for r in recs)
    say(f"[{h}] bloques ocupados={len(blocks)} {dict(sorted(blocks.items()))} horizon_valid={pop.horizon_valid} "
        f"bloque_más_corto={pop.shortest_block_sessions} max_hold={pop.result.max_hold_bars}")
    scores = sorted(r.score for r in recs)
    own_q = [nr(scores, k) for k in (20, 40, 60, 80)]
    np_q = [float(np.percentile(np.array(scores), k, method="inverted_cdf")) for k in (20, 40, 60, 80)]
    exe = p3.quintile_cuts(scores)
    say(f"[{h}] cortes propios={own_q} numpy inverted_cdf={np_q} ejecutor={list(exe.values)} distintos={len(set(scores))} "
        f"n_por_q={exe.n_by_quintile} empates={exe.tied_pairs}")
    # comprobación de que el ruido float no cambia nada: scores crudos sin canonicalizar
    raw_scores = sorted(s.observation.score_value for s in pop.result.signals)
    say(f"[{h}] cortes con scores crudos sin redondear={[nr(raw_scores, k) for k in (20,40,60,80)]} distintos crudos={len(set(raw_scores))}")
    # n por banda con mi propia regla: score igual a corte sube
    def band(s, cuts):
        return sum(1 for c_ in cuts if s >= c_) + 1
    own_n = Counter(band(s, own_q) for s in scores)
    say(f"[{h}] n por banda (propio)={dict(sorted(own_n.items()))}")
    # ¿cuántas observaciones caen exactamente en cada corte?
    say(f"[{h}] observaciones exactamente en cada corte={[sum(1 for s in scores if s == c_) for c_ in own_q]}")
    if h == "swing":
        cand = [nr(scores, k) for k in (50, 60, 70, 80, 90)]
        say(f"[{h}] candidatos propios={cand} ejecutor={list(p3.candidate_set(scores).values)} "
            f"n[c,∞)={[sum(1 for s in scores if s >= c_) for c_ in cand]}")
    for name in ("catalizador", "tecnico", "contexto"):
        ab = sorted(r.ablated_scores[name] for r in recs)
        say(f"[{h}] ablación sin {name}: cortes propios={[nr(ab, k) for k in (20,40,60,80)]} distintos={len(set(ab))}")
    with open(OUT / f"poblacion-{h}.tsv", "w") as f:
        f.write("activo\tsesion\tsesion_entrada\tplaza\tbloque\tscore\tsin_catalizador\tsin_tecnico\tsin_contexto\tanalysis_timestamp\tpuntos_contexto_indep\tpuntos_contexto_obs\tevaluable_max\n")
        for row in dump: f.write("\t".join(str(x) for x in row) + "\n")
    summary[h] = {"n": len(recs), "sha": sha}
say("FIN", json.dumps(summary))
