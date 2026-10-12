"""Evaluación de B2, S2 y C0 en vivo y comprobación de apertura por política (ficha §3.5, §5, §7, §10.2).

La población es la de P6 (``OPERAR_score_v1_point_in_time``): Score v1 70/60, broker neutral y contexto
point-in-time. Se llama a las mismas funciones de ``advisor`` que ``p6.build_real_signals``
(``build_snapshot_series``, ``advisor.backtest.engine._signal`` y ``PointInTimeContextResolver``); no se
copia ninguna (INV-06).

Todo lo de este módulo es **independiente de los libros**: la misma evaluación y la misma comprobación de
apertura para cualquier cohorte de la política. ``MARKET_PASS`` es visible durante el embargo; ``FILLED``
no existe aquí (D-78).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence

import pandas as pd

from paper.engine_v1 import market_check, requested_weight
from paper.inputs import Downtime, SeriesInfo, bindings, exec_factor, series_info
from paper.store import PaperStore, canonical, content_sha256
from paper.universe import PaperAsset, PaperUniverse, closed_by, next_session, open_close

HORIZONTE = "swing"
WARMUP_BARS = 120
SCORE_MODEL_VERSION = "1.0"
CHECK_OK = "MARKET_PASS"


@dataclass(frozen=True)
class PolicyEnv:
    """Configuración de una política y modelos de ``advisor`` necesarios para evaluarla."""

    policy_id: str
    config: Any  # AdvisorConfig con los niveles de la celda de P5
    advisor_assets: Mapping[str, Any]  # símbolo → advisor.universe.models.Asset
    market_context: Any
    min_rr: float = 1.5


def policy_envs(policies: Sequence[str]) -> Dict[str, PolicyEnv]:
    from advisor.research import p6

    config, universe = p6._sources()
    assets = {symbol: universe.get(symbol) for symbol in p6.asset_list()}
    return {
        policy: PolicyEnv(policy, p6.policy_config(config, policy), assets, config.market_context, config.risk.min_rr_ratio)
        for policy in policies
    }


def signal_frame(info: SeriesInfo, store: PaperStore, symbol: str, cutoff: datetime) -> pd.DataFrame:
    """Vista de señal: barras vigentes en la escala de todos los splits conocidos al corte (§3.3)."""

    rows = {r["session_date"]: r for r in store.rows(
        "SELECT session_date, volume FROM paper_bar_observation WHERE data_symbol = ? AND observed_at <= ?",
        (symbol, cutoff.isoformat()),
    )}
    known = info.splits
    data = []
    for i, day in enumerate(info.sessions):
        to_signal = 1.0
        for ex_date, ratio, _obs in known:
            if ex_date > day:
                to_signal /= ratio
        factor = info.exec_factor[i] * to_signal
        v = info.view
        data.append({
            "Open": v.open[i] / info.exec_factor[i] * factor, "High": v.high[i] / info.exec_factor[i] * factor,
            "Low": v.low[i] / info.exec_factor[i] * factor, "Close": v.close[i] / info.exec_factor[i] * factor,
            "Volume": float(rows.get(day.isoformat(), {"volume": 0.0})["volume"]),
        })
    index = pd.DatetimeIndex(pd.to_datetime(list(info.bar_timestamps), utc=True))
    return pd.DataFrame(data, index=index)


def close_series(store: PaperStore, symbol: str, cutoff: datetime, *, context: bool) -> Optional[pd.Series]:
    if context:
        rows = store.rows(
            "SELECT bar_timestamp, close FROM paper_context_observation WHERE series = ? AND observed_at <= ? ORDER BY bar_timestamp",
            (symbol, cutoff.isoformat()),
        )
    else:
        from paper.ingest import usable_bars

        first: Dict[str, Any] = {day: bar.row for day, bar in usable_bars(store, symbol, as_of=cutoff.isoformat()).items()}
        rows = [first[k] for k in sorted(first)]
        from paper.inputs import _splits

        splits = _splits(store, symbol, cutoff)
        provider_splits = _splits(store, symbol, cutoff, provider_only=True)
        values = []
        for r in rows:
            day = date.fromisoformat(r["session_date"])
            factor = exec_factor(day, r["observed_at"], provider_splits)
            for ex_date, ratio, _obs in splits:
                if ex_date > day:
                    factor /= ratio
            values.append(float(r["close"]) * factor)
        if not rows:
            return None
        return pd.Series(values, index=pd.DatetimeIndex(pd.to_datetime([r["bar_timestamp"] for r in rows], utc=True)))
    if not rows:
        return None
    return pd.Series([float(r["close"]) for r in rows], index=pd.DatetimeIndex(pd.to_datetime([r["bar_timestamp"] for r in rows], utc=True)))


def context_resolver(store: PaperStore, universe: PaperUniverse, env: PolicyEnv, cutoff: datetime) -> Any:
    from advisor.context.point_in_time import PointInTimeContextResolver

    closes = {}
    for symbol in universe.context_symbols:
        series = close_series(store, symbol, cutoff, context=True)
        if series is not None:
            closes[symbol] = series
    return PointInTimeContextResolver(
        closes, env.market_context, asia_symbols=universe.asia_symbols, settlement_minutes=universe.settlement_minutes
    )


def evaluate(asset: PaperAsset, info: SeriesInfo, frame: pd.DataFrame, j: int, env: PolicyEnv, resolver: Any,
             benchmark: Optional[pd.Series], analysis_ts: datetime) -> Dict[str, Any]:
    """Una evaluación (``paper_signal_evaluation``) de la sesión ``j`` con la configuración de la política."""

    from advisor.analysis.opportunity import ACCION_COMPRAR, RADAR_OPERAR
    from advisor.analysis.snapshot import build_snapshot_series
    from advisor.backtest.engine import _signal
    from advisor.data.sessions import market_for_symbol, market_session

    cfg = env.config
    window = cfg.horizonte(HORIZONTE)
    base: Dict[str, Any] = {
        "reference_price": float(frame["Close"].iloc[j]), "entry_max": None, "stop": None, "target1": None,
        "target2": None, "target3": None, "rr_at_reference": None, "risk_fraction": None, "score": None,
        "setup_radar": "", "setup_accion": "", "operar": 0, "context_json": "{}", "reasons": "",
    }
    resolved = resolver.resolve(analysis_ts)
    if resolved is None or not resolved.calculable or resolved.context is None:
        codes = ",".join((*(resolved.exclusions or ()), *(resolved.no_calculable_codes or ()))) if resolved else ""
        return {**base, "setup_radar": "NO_CALCULABLE_CONTEXT", "reasons": codes or "NO_CALCULABLE_CONTEXT_HISTORY"}
    context = resolved.context
    benchmark_symbol = asset.benchmark_symbol
    try:
        series = build_snapshot_series(
            frame, cfg.indicators, cfg.levels, window.interval, benchmark,
            asset_timezone=market_session(asset.market).timezone,
            benchmark_timezone=market_session(market_for_symbol(benchmark_symbol)).timezone if benchmark_symbol else None,
        )
    except ValueError as exc:
        return {**base, "setup_radar": "SIN_SERIE", "reasons": str(exc)}
    context_at: List[Any] = [None] * len(frame)
    context_at[j] = context
    found = _signal(env.advisor_assets[asset.symbol], series, j, cfg, HORIZONTE, WARMUP_BARS, None, None, None,
                    context_at, SCORE_MODEL_VERSION)
    ctx = {"label": getattr(context, "label", ""), "source": getattr(context, "source", "")}
    if found is None:
        return {**base, "setup_radar": "SIN_NIVELES", "context_json": canonical(ctx)}
    levels = found["levels"]
    operar = int(found["setup_radar"] == RADAR_OPERAR and found["setup_accion"] == ACCION_COMPRAR)
    return {
        **base, "signal_id": found["observation"].signal_id, "entry_max": float(levels.entry_max),
        "stop": float(levels.stop), "target1": float(levels.target1), "target2": float(levels.target2),
        "target3": float(levels.target3), "rr_at_reference": float(levels.rr_ratio),
        "risk_fraction": float(levels.risk_pp) / 100.0, "score": float(found["score"]),
        "setup_radar": str(found["setup_radar"]), "setup_accion": str(found["setup_accion"]), "operar": operar,
        "context_json": canonical(ctx),
    }


def evaluate_pass(store: PaperStore, universe: PaperUniverse, cohorts: Mapping[str, str], envs: Mapping[str, PolicyEnv], *,
                  pass_ts: datetime, now: datetime, start: date, paper_run_id: str, source_run_id: str,
                  evaluator: Any = None) -> List[Dict[str, Any]]:
    """Evaluaciones de esta pasada para cada cohorte de política (``cohorts``: política → cohorte).

    Se evalúa la última sesión ``t`` de la serie vigente y contigua cuya barra estaba disponible en la hora
    programada (``available_at ≤ analysis_timestamp``) y cuya apertura de entrada todavía no llegó. Devuelve
    las filas sin escribirlas: el llamador fija ``decision_ts`` justo antes de confirmar la transacción única
    de evaluaciones y las inserta entonces (D-78, ronda 4).
    """

    evaluator = evaluator or evaluate
    downtime = Downtime(store, now)
    out: List[Dict[str, Any]] = []
    for asset in universe.assets:
        info = series_info(store, asset, start, now, universe.settlement_minutes, downtime)
        if not info.sessions:
            continue
        j = len(info.sessions) - 1
        t = info.sessions[j]
        if t < start - timedelta(days=7) or not closed_by(asset.market, t, pass_ts, universe.settlement_minutes):
            continue
        entry = next_session(asset.market, t)
        if open_close(asset.market, entry)[0] <= now:
            continue
        frame = signal_frame(info, store, asset.data_symbol, now)
        benchmark = close_series(store, asset.benchmark_symbol, now, context=False) if asset.benchmark_symbol else None
        for policy, cohort_id in cohorts.items():
            env = envs[policy]
            resolver = context_resolver(store, universe, env, now)
            result = evaluator(asset, info, frame, j, env, resolver, benchmark, pass_ts)
            from advisor.research.observations import stable_signal_id

            signal_id = result.get("signal_id") or stable_signal_id(asset.symbol, HORIZONTE, pd.Timestamp(info.bar_timestamps[j]))
            row = {
                "cohort_id": cohort_id, "policy_id": policy, "signal_id": signal_id, "instrument_id": asset.instrument_id,
                "symbol": asset.symbol, "data_symbol": asset.data_symbol, "market": asset.market,
                "signal_session_date": t.isoformat(), "bar_timestamp": info.bar_timestamps[j],
                "pass_scheduled_ts": pass_ts.isoformat(), "analysis_timestamp": pass_ts.isoformat(), "decision_ts": "",
                "reference_price": result["reference_price"], "entry_max": result["entry_max"], "stop": result["stop"],
                "target1": result["target1"], "target2": result["target2"], "target3": result["target3"],
                "rr_at_reference": result["rr_at_reference"], "risk_fraction": result["risk_fraction"],
                "score": result["score"], "score_model_version": SCORE_MODEL_VERSION,
                "setup_radar": result["setup_radar"], "setup_accion": result["setup_accion"], "operar": result["operar"],
                "context_json": result["context_json"], "data_quality": "OK", "reasons": result["reasons"],
                "max_input_observed_at": max(info.observed_at) if info.observed_at else "",
                "source_run_id": source_run_id, "source_recommendation_id": "", "paper_run_id": paper_run_id,
            }
            row["content_sha256"] = content_sha256(row, ("paper_run_id", "decision_ts", "max_input_observed_at", "source_run_id"))
            out.append(row)
    return out


def write_evaluations(store: PaperStore, rows: Sequence[Dict[str, Any]], decision_ts: datetime) -> int:
    """Inserta las evaluaciones de una pasada con su ``decision_ts`` (una sola vez: append-only)."""

    written = 0
    for row in rows:
        stamped = {**row, "decision_ts": decision_ts.isoformat()}
        if store.insert_first("paper_signal_evaluation", stamped, ("cohort_id", "signal_id", "pass_scheduled_ts")):
            written += 1
    return written


def open_checks(store: PaperStore, universe: PaperUniverse, cohorts: Mapping[str, str], envs: Mapping[str, PolicyEnv],
                code_sha: str, *, now: datetime, start: date, paper_run_id: str, slippage_bps: float = 5.0) -> int:
    """``paper_open_check`` para toda señal vinculante OPERAR cuya barra de entrada ya está observada,
    haya o no posición en ningún libro (§5, §7.1)."""

    downtime = Downtime(store, now)
    infos = {a.symbol: series_info(store, a, start, now, universe.settlement_minutes, downtime) for a in universe.assets}
    written = 0
    for policy, cohort_id in cohorts.items():
        done = {r["signal_id"] for r in store.rows(
            "SELECT signal_id FROM paper_open_check WHERE policy_id = ? AND t025_code_sha = ?", (policy, code_sha))}
        for b in bindings(store, cohort_id, universe, now):
            # Se escribe una sola vez, cuando la barra de entrada ya está observada; nunca se recalcula el
            # historial (una entrada posterior no reescribe una comprobación ya publicada).
            if not (b.final and b.operar) or b.signal_id in done:
                continue
            info = infos[b.asset]
            if b.signal_session not in info.sessions:
                continue
            j = info.sessions.index(b.signal_session)
            if j + 1 >= len(info.sessions):
                continue
            view = info.view
            i = j + 1
            ratio = view.splits.get(i, 1.0)
            assert b.stop is not None and b.target2 is not None and b.entry_max is not None
            stop, target2, entry_max = b.stop / ratio, b.target2 / ratio, b.entry_max / ratio
            market_open = view.open[i]
            eff = market_open * (1.0 + slippage_bps / 10_000.0)
            code = market_check(market_open, eff, stop, target2, entry_max, envs[policy].min_rr)
            check = CHECK_OK if code == "EXECUTABLE" else code
            row = {
                "policy_id": policy, "t025_code_sha": code_sha, "signal_id": b.signal_id,
                "instrument_id": universe.by_symbol()[b.asset].instrument_id, "signal_session_date": b.signal_session.isoformat(),
                "entry_session": info.sessions[i].isoformat(), "binding_pass_ts": b.pass_ts.isoformat(),
                "open_market": market_open, "entry_effective": eff, "check_code": check,
                "requested_weight": requested_weight(eff, stop) if check == CHECK_OK else None, "paper_run_id": paper_run_id,
            }
            row["content_sha256"] = content_sha256(row, ("paper_run_id",))
            if store.insert("paper_open_check", row, ("policy_id", "t025_code_sha", "signal_id"), compare_exclude=("paper_run_id",)):
                written += 1
    return written


def not_evaluated(store: PaperStore, universe: PaperUniverse, cohorts: Mapping[str, str], *, now: datetime,
                  start: date) -> int:
    """``SIGNAL_NOT_EVALUATED`` de las sesiones cuya apertura de entrada ya pasó sin evaluación vinculante,
    con su causa: ``ENGINE_DOWNTIME`` si la pasada vinculante cayó en una caída, si no
    ``PROVIDER_DATA_MISSING``. Nunca se reconstruye la recomendación (D-78)."""

    from paper.universe import binding_pass

    downtimes = {cohort_id: Downtime(store, now, cohort_id) for cohort_id in cohorts.values()}
    known = {
        cohort_id: {(b.asset, b.signal_session) for b in bindings(store, cohort_id, universe, now)}
        for cohort_id in cohorts.values()
    }
    written = 0
    base = Downtime(store, now)
    for asset in universe.assets:
        info = series_info(store, asset, start, now, universe.settlement_minutes, base)
        for t in info.sessions:
            if t < start:
                continue
            entry = next_session(asset.market, t)
            entry_open = open_close(asset.market, entry)[0]
            if entry_open > now:
                continue
            for cohort_id in cohorts.values():
                if (asset.symbol, t) in known[cohort_id]:
                    continue
                scheduled = binding_pass(asset.market, t, entry, universe.settlement_minutes)
                down = downtimes[cohort_id]
                cause = "ENGINE_DOWNTIME" if scheduled is not None and down.covers(scheduled) else "PROVIDER_DATA_MISSING"
                if store.insert_first(
                    "paper_signal_not_evaluated",
                    {"cohort_id": cohort_id, "data_symbol": asset.data_symbol, "signal_session_date": t.isoformat(),
                     "entry_session": entry.isoformat(), "cause": cause, "detected_at": now.isoformat()},
                    ("cohort_id", "data_symbol", "signal_session_date"),
                ):
                    written += 1
    return written


