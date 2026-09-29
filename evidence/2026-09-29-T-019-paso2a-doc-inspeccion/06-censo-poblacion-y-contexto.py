"""Censo de la población de P3 con las decisiones del propietario del 2026-09-29.

Reproduce la población del event study (la misma que A-02) SIN evaluar ningún
desenlace: `evaluate_managed_event` y `evaluate_potential_event` se sustituyen
por funciones que devuelven None, así que no se calcula ni se lee ningún
precio posterior a la señal, ningún net_R, ninguna salida ni ningún score v2.
De cada señal solo se usan el activo y el índice de la barra de señal.

Para cada señal no cripto calcula el `analysis_timestamp` de D-50 (T-A) y el
contexto exigible en ese instante con los calendarios del repo, más los
cierres reales aprobados en D-54 (que 2a-code añade a exchange_overrides.yaml).

Motivos de exclusión, evaluados sobre cada observación (una observación puede
tener varios; la población final sale de la UNIÓN, sin doble conteo):
  excluded_crypto              D-51  plaza 24/7
  excluded_asia_missing        D-52  hueco del proveedor en una serie asiática (L o P)
  excluded_trend_sma_history   D-55  menos de trend_sma cierres de ^STOXX50E
                                     causalmente disponibles (NO_CALCULABLE_CONTEXT_HISTORY)
No excluye (D-56): hueco intermedio de ^STOXX50E; se usa el último cierre
presente y causalmente disponible, y se publica el contador con su antigüedad.
"""
from __future__ import annotations

import hashlib
import sys
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

import advisor.data.calendars as calmod
import advisor.research.event_study as es
from advisor.analysis.overview import context_assets_of
from advisor.config import load_config
from advisor.data.freshness import mercado_para_simbolo
from advisor.data.sessions import (
    _exchange_calendar,
    latest_expected_closed_session,
    market_for_symbol,
    market_session,
    session_close_at,
    session_date_of,
)
from advisor.research.vintage import load_vintage
from advisor.universe.loader import load_universe

VID = "071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841"
LONDON = ZoneInfo("Europe/London")
CIERRES_VERIFICADOS = {  # D-54: plaza -> cierres reales ausentes del calendario
    "HKG": {"2023-09-01", "2023-09-08"},   # tifón Saola (T8) y lluvia negra: HKEX canceló la sesión completa
    "TAI": {"2023-01-18", "2024-10-31", "2026-07-10"},  # TWSE: sin negociación antes del Año Nuevo Lunar (calendario oficial); tifones Kong-rey y Bavi
}
PASADAS = (time(7, 0), time(8, 30), time(14, 30), time(21, 0))  # deploy/systemd/intradia-bot.timer

cfg = load_config("config.yaml")
uni = load_universe(cfg.universe_path)
vintage = load_vintage(VID)
SETTLE = cfg.data_quality.settlement_minutes
TREND_SMA = cfg.market_context.trend_sma

_expected_original = calmod.expected_sessions


def _expected_con_cierres_aprobados(market, start, end):
    from datetime import date as _d
    extra = {_d.fromisoformat(x) for x in CIERRES_VERIFICADOS.get(market, ())}
    return [s for s in _expected_original(market, start, end) if s not in extra]


calmod.expected_sessions = _expected_con_cierres_aprobados

# 1. Población sin desenlaces.
es.evaluate_managed_event = lambda *a, **k: None
es.evaluate_potential_event = lambda *a, **k: None

def poblacion(horizonte):
    res = es.run_event_study_on_vintage(cfg, uni, vintage, horizonte=horizonte, population_name="vigente")
    return res, [(s.observation.asset, s.observation.signal_idx) for s in res.signals]

# 2. Barras de contexto presentes en la cosecha, por sesión de su plaza.
asia = sorted(a.primary_symbol for a in context_assets_of(uni) if a.region == "ASIA")
ctx_symbols = [*asia, cfg.market_context.vix_symbol, cfg.market_context.trend_symbol]
ctx_market = {s: market_for_symbol(s) for s in ctx_symbols}
present = {}
for s in ctx_symbols:
    raw = vintage.by_symbol[s].signal_prices.index
    present[s] = sorted({session_date_of(t, ctx_market[s]) for t in raw})
present_set = {s: set(v) for s, v in present.items()}

def pasadas_entre(inicio: datetime, fin: datetime):
    d = inicio.astimezone(LONDON).date() - timedelta(days=1)
    ultimo = fin.astimezone(LONDON).date() + timedelta(days=1)
    while d <= ultimo:
        if d.weekday() < 5:
            for h in PASADAS:
                yield datetime.combine(d, h, LONDON).astimezone(timezone.utc)
        d += timedelta(days=1)

def analysis_timestamp(market, d, e):
    """T-A: última pasada programada estrictamente anterior a la apertura de e,
    y no anterior a available_at(d) = cierre(d) + settlement."""
    cal = _exchange_calendar(market_session(market).mic)
    if not cal.is_session(pd.Timestamp(e)):
        return None, "entrada_sin_sesion_en_calendario"
    apertura = cal.session_open(pd.Timestamp(e)).to_pydatetime()
    disponible = session_close_at(market, d) + timedelta(minutes=SETTLE)
    candidatas = [p for p in pasadas_entre(disponible, apertura) if disponible <= p < apertura]
    if not candidatas:
        return None, "sin_pasada_entre_cierre_y_apertura"
    return max(candidatas), None

ctx_cache = {}
TREND = cfg.market_context.trend_symbol


def contexto_en(T):
    """Faltas asiáticas, historia de la SMA y hueco de tendencia en el instante T."""
    if T in ctx_cache:
        return ctx_cache[T]
    faltas_asia = []
    sma = None
    hueco_tendencia = None
    for s in ctx_symbols:
        m = ctx_market[s]
        L = latest_expected_closed_session(m, T, settlement_minutes=SETTLE)
        if L is None:
            raise RuntimeError(f"{s}: última sesión cerrada indeterminada en {T}")
        if s == TREND:
            disponibles = [x for x in present[s] if x <= L]
            sma = len(disponibles)
            if L not in present_set[s]:
                hueco_tendencia = (L, disponibles[-1] if disponibles else None)
            continue
        if s not in asia:
            if L not in present_set[s]:
                raise RuntimeError(f"{s}: hueco en {L}; D-53 no lo contempla en esta cosecha")
            continue
        if L not in present_set[s]:
            faltas_asia.append((s, "falta_ultima_cerrada", L))
            continue
        prev = calmod.expected_sessions(m, L - timedelta(days=45), L - timedelta(days=1))
        if not prev:
            raise RuntimeError(f"{s}: sesión anterior indeterminada antes de {L}")
        if prev[-1] not in present_set[s]:
            faltas_asia.append((s, "falta_anterior_cerrada", prev[-1]))
    ctx_cache[T] = (tuple(faltas_asia), sma, hueco_tendencia)
    return ctx_cache[T]


region_of = {a.primary_symbol: a.region for a in uni.analizables()}
out = []
def p(*a):
    print(*a)
    out.append(" ".join(str(x) for x in a))

salida = sys.argv[1] if len(sys.argv) > 1 else "."


def escribir(nombre, cabecera, filas):
    with open(f"{salida}/{nombre}", "w") as fh:
        fh.write("\t".join(cabecera) + "\n")
        for fila in filas:
            fh.write("\t".join(str(x) for x in fila) + "\n")


MOTIVOS = ("excluded_crypto", "excluded_asia_missing", "excluded_trend_sma_history")
for horizonte in ("swing", "medio"):
    res, sig = poblacion(horizonte)
    p(f"\n=== {horizonte} ===")
    p("población de A-02 (todos los activos):", len(sig), "| saltados:", len(res.skipped))
    mk = {a: mercado_para_simbolo(uni.get(a), a) for a in {x for x, _ in sig}}
    filas = {m: [] for m in MOTIVOS}
    huecos_tendencia = []
    motivos_por_obs = []
    final = []
    for a, j in sig:
        m = mk[a]
        idx = vintage.by_symbol[a].signal_prices.index
        d = session_date_of(idx[j], m)
        motivos = set()
        if m == "CRYPTO":
            motivos.add("excluded_crypto")
            filas["excluded_crypto"].append((a, d))
        else:
            e = session_date_of(idx[j + 1], m)
            T, sin_T = analysis_timestamp(m, d, e)
            if T is None:
                raise RuntimeError(f"{a} {d}: {sin_T}")
            faltas, n_sma, hueco = contexto_en(T)
            if faltas:
                motivos.add("excluded_asia_missing")
                filas["excluded_asia_missing"].append(
                    (a, d, T.isoformat(), "; ".join(f"{s}:{w}:{x}" for s, w, x in faltas)))
            if n_sma < TREND_SMA:
                motivos.add("excluded_trend_sma_history")
                filas["excluded_trend_sma_history"].append((a, d, T.isoformat(), n_sma))
            if hueco is not None and not motivos:
                exigible, usada = hueco
                huecos_tendencia.append((a, d, T.isoformat(), exigible, usada, (exigible - usada).days))
        motivos_por_obs.append(frozenset(motivos))
        if not motivos:
            final.append((a, d))
    for motivo in MOTIVOS:
        p(f"{motivo}:", len(filas[motivo]))
    combinaciones = Counter(tuple(sorted(x)) for x in motivos_por_obs if x)
    p("combinaciones de motivos (observaciones):", {" + ".join(k): v for k, v in sorted(combinaciones.items())})
    p("excluidas (unión deduplicada):", sum(combinaciones.values()))
    p("POBLACION FINAL:", len(final), "señales |", len({a for a, _ in final}), "activos")
    reg = Counter(region_of[a] for a, _ in final)
    p("  por region:", dict(sorted(reg.items())), "| regiones:", len(reg))
    p("  activos por region:", dict(sorted(Counter(region_of[a] for a in {a for a, _ in final}).items())))
    edades = Counter(x[5] for x in huecos_tendencia)
    p("hueco intermedio de ^STOXX50E en la población final (último cierre presente, D-56):",
      len(huecos_tendencia), "| antigüedad en días naturales:", dict(sorted(edades.items())))
    faltas_asia = Counter()
    for _a, _d, _T, f in filas["excluded_asia_missing"]:
        for item in f.split("; "):
            faltas_asia[item.split(":", 1)[1]] += 1
    p("faltas asiáticas (serie:motivo:sesión -> observaciones):")
    for k, v in sorted(faltas_asia.items()):
        p("   ", k, "->", v)
    lineas = sorted(f"{a}\t{d}" for a, d in final)
    p("sha256 de la población final (activo<TAB>sesión de señal, ordenado):",
      hashlib.sha256("\n".join(lineas).encode()).hexdigest())
    escribir(f"06-excluded_crypto-{horizonte}.tsv", ("activo", "sesion_senal"), filas["excluded_crypto"])
    escribir(f"06-excluded_asia_missing-{horizonte}.tsv",
             ("activo", "sesion_senal", "analysis_timestamp_utc", "faltas"), filas["excluded_asia_missing"])
    escribir(f"06-excluded_trend_sma_history-{horizonte}.tsv",
             ("activo", "sesion_senal", "analysis_timestamp_utc", "cierres_disponibles"),
             filas["excluded_trend_sma_history"])
    escribir(f"06-stoxx_hueco_intermedio-{horizonte}.tsv",
             ("activo", "sesion_senal", "analysis_timestamp_utc", "sesion_exigible", "sesion_usada", "dias"),
             huecos_tendencia)
