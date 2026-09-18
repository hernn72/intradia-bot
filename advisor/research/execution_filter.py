"""Medición del filtro de ejecución separado del score."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from advisor.analysis.benchmark import resolve_benchmark_symbol
from advisor.backtest.engine import (
    ENTRY_OPEN_AT_OPEN,
    POLICY_OPERAR,
    BacktestTrade,
    ExecutionRejectedSignal,
    simulate_asset,
)
from advisor.backtest.report import _MIN_SAMPLE
from advisor.config import AdvisorConfig
from advisor.indicators.technical import sma
from advisor.research.bootstrap import (
    DEFAULT_RESAMPLES,
    DEFAULT_SEED,
    bootstrap_block_mean_interval,
    session_block_lookup,
)
from advisor.research.event_study import SCORE_BANDS
from advisor.research.vintage import VintageLoad, load_vintage
from advisor.run.manifest import config_hash, git_sha
from advisor.universe.models import Universe
from advisor.universe.vintage import universe_vintage_id

BLOCK_LENGTH = {"swing": 60, "medio": 300}
MAX_HOLD_BARS = {"swing": 40, "medio": 250}

POP_ALL_SCORE = "TODAS_SCORE"
POP_EXECUTED = "EJECUTADAS"
POP_LOST_ENTRY = "PERDIDAS_POR_ENTRADA"


@dataclass(frozen=True)
class PopulationStats:
    population: str
    band: str
    n: int
    sufficient: bool
    wins: int
    target_exits: int
    stop_exits: int
    mean_net_r: Optional[float]
    block_mean_net_r: Optional[float]
    ci_low: Optional[float]
    ci_high: Optional[float]
    median_net_r: Optional[float]
    p10_net_r: Optional[float]
    p90_net_r: Optional[float]
    profit_factor: Optional[float]
    payoff: Optional[float]


@dataclass(frozen=True)
class ExecutionFilterResult:
    data_vintage_id: str
    universe_vintage_id: str
    git_sha: str
    config_hash: str
    horizonte: str
    cost_pct: float
    evaluated_assets: Tuple[str, ...]
    skipped: Tuple[Tuple[str, str], ...]
    executed: Tuple[BacktestTrade, ...]
    lost: Tuple[ExecutionRejectedSignal, ...]
    counterfactual_lost: Tuple[BacktestTrade, ...]
    broker_neutral_delta_by_asset: Dict[str, Tuple[int, int]]
    table: Tuple[PopulationStats, ...] = field(default_factory=tuple)

    @property
    def reason_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for signal in self.lost:
            counts[signal.execution_reason] = counts.get(signal.execution_reason, 0) + 1
        return dict(sorted(counts.items()))


def run_execution_filter_study(
    config: AdvisorConfig,
    universe: Universe,
    data_vintage_id: str,
    *,
    horizonte: str = "swing",
    cost_pct: float = 0.2,
    root_dir: str = "data/vintages",
) -> ExecutionFilterResult:
    """Mide la disciplina real y el contrafactual sobre una cosecha congelada."""

    if horizonte not in MAX_HOLD_BARS:
        raise ValueError(f"filtro-ejecucion solo cubre swing y medio: '{horizonte}'")
    vintage = load_vintage(_resolve_vintage_id(data_vintage_id, root_dir), root_dir=root_dir)
    window = config.horizonte(horizonte)
    vix_close = _frozen_close(vintage, config.market_context.vix_symbol)
    trend_close = _frozen_close(vintage, config.market_context.trend_symbol)
    trend_sma_close = sma(trend_close, config.market_context.trend_sma) if trend_close is not None else None
    benchmark_cache: Dict[str, Optional[object]] = {}

    executed: List[BacktestTrade] = []
    lost: List[ExecutionRejectedSignal] = []
    counterfactual_lost: List[BacktestTrade] = []
    evaluated: List[str] = []
    skipped: List[Tuple[str, str]] = []
    broker_delta: Dict[str, Tuple[int, int]] = {}

    for symbol, views in vintage.by_symbol.items():
        asset = universe.get(symbol)
        if asset is None or not asset.analizable:
            continue
        df = views.signal_prices
        if len(df) < window.min_bars + 2:
            skipped.append((symbol, f"histórico insuficiente: {len(df)} velas"))
            continue
        benchmark_symbol = resolve_benchmark_symbol(asset, config.report)
        benchmark_close = None
        if benchmark_symbol is not None:
            if benchmark_symbol not in benchmark_cache:
                benchmark_cache[benchmark_symbol] = _frozen_close(vintage, benchmark_symbol)
            cached = benchmark_cache[benchmark_symbol]
            benchmark_close = cached if cached is not None else None
        vix_aligned = _align(vix_close, df.index) if vix_close is not None else None
        vix_at = _as_optional_list(vix_aligned.shift(1) if vix_aligned is not None else None)
        trend_at = _as_optional_list(_align(trend_close, df.index))
        trend_sma_at = _as_optional_list(_align(trend_sma_close, df.index))

        strict_rejected: List[ExecutionRejectedSignal] = []
        strict = simulate_asset(
            asset,
            df,
            config,
            horizonte,
            POLICY_OPERAR,
            cost_pct,
            benchmark_close=benchmark_close,
            vix_at=vix_at,
            trend_price_at=trend_at,
            trend_sma_at=trend_sma_at,
            broker_neutral=False,
        )
        neutral_rejected: List[ExecutionRejectedSignal] = []
        neutral = simulate_asset(
            asset,
            df,
            config,
            horizonte,
            POLICY_OPERAR,
            cost_pct,
            benchmark_close=benchmark_close,
            vix_at=vix_at,
            trend_price_at=trend_at,
            trend_sma_at=trend_sma_at,
            rejected_signals=neutral_rejected,
            broker_neutral=True,
        )
        lost_ids = {item.signal_id for item in neutral_rejected}
        counterfactual = simulate_asset(
            asset,
            df,
            config,
            horizonte,
            POLICY_OPERAR,
            cost_pct,
            benchmark_close=benchmark_close,
            vix_at=vix_at,
            trend_price_at=trend_at,
            trend_sma_at=trend_sma_at,
            entry_discipline=ENTRY_OPEN_AT_OPEN,
            broker_neutral=True,
        )
        executed.extend(neutral)
        lost.extend(neutral_rejected)
        counterfactual_lost.extend(trade for trade in counterfactual if trade.signal_id in lost_ids)
        if asset.trade_republic == "no":
            broker_delta[symbol] = (len(strict), len(neutral))
        evaluated.append(symbol)
        if strict_rejected:
            raise AssertionError("strict_rejected solo existe para conservar el tipo")

    result = ExecutionFilterResult(
        data_vintage_id=vintage.data_vintage_id,
        universe_vintage_id=universe_vintage_id(universe),
        git_sha=git_sha(),
        config_hash=config_hash(config),
        horizonte=horizonte,
        cost_pct=cost_pct,
        evaluated_assets=tuple(evaluated),
        skipped=tuple(skipped),
        executed=tuple(executed),
        lost=tuple(lost),
        counterfactual_lost=tuple(counterfactual_lost),
        broker_neutral_delta_by_asset=broker_delta,
    )
    return ExecutionFilterResult(**{**result.__dict__, "table": tuple(_build_table(result))})


def format_execution_filter_report(result: ExecutionFilterResult) -> str:
    lines = [
        "# Filtro de ejecución",
        "",
        f"data_vintage_id={result.data_vintage_id}",
        f"universe_vintage_id={result.universe_vintage_id}",
        f"git_sha={result.git_sha}",
        f"config_hash={result.config_hash}",
        f"horizonte={result.horizonte} coste={result.cost_pct:.2f}%",
        f"activos_evaluados={len(result.evaluated_assets)} señales_ejecutadas={len(result.executed)} "
        f"perdidas_por_entrada={len(result.lost)} contrafactuales={len(result.counterfactual_lost)}",
        "",
        "## Tabla por banda y población",
        "| banda | población | n | estado | win | objetivo | stop | expectancy_pool_R | expectancy_bloque_R | IC95_bloque | mediana_R | p10_R | p90_R | PF | payoff |",
        "|---|---|---:|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|",
    ]
    for row in result.table:
        lines.append(_format_stats_row(row))
    lines.extend(["", "## Desglose por motivo", "| motivo | n | porcentaje |", "|---|---:|---:|"])
    total_lost = len(result.lost)
    for reason, n in result.reason_counts.items():
        pct = f"{n / total_lost * 100:.2f}%" if total_lost else "N/D"
        lines.append(f"| {reason} | {n} | {pct} ({n}/{total_lost}) |")
    if not result.reason_counts:
        lines.append("| sin perdidas | 0 | N/D |")
    lines.extend(["", "## Broker neutral: activos trade_republic=no", "| activo | estricto | broker_neutral | entra/sale |", "|---|---:|---:|---|"])
    for symbol, (strict, neutral) in sorted(result.broker_neutral_delta_by_asset.items()):
        lines.append(f"| {symbol} | {strict} | {neutral} | {neutral - strict:+d} |")
    if not result.broker_neutral_delta_by_asset:
        lines.append("| ninguno | 0 | 0 | 0 |")
    lines.extend(["", "## D-29"])
    lines.append(
        f"ABOVE_MAX_ENTRY={result.reason_counts.get('ABOVE_MAX_ENTRY', 0)}; "
        f"RR_TOO_LOW={result.reason_counts.get('RR_TOO_LOW', 0)}. No se cambia el orden de evaluación."
    )
    if result.skipped:
        lines.extend(["", "## Saltos"])
        for symbol, reason in result.skipped:
            lines.append(f"- {symbol}: {reason}")
    return "\n".join(lines)


def _build_table(result: ExecutionFilterResult) -> List[PopulationStats]:
    executed_by_id = {trade.signal_id: trade for trade in result.executed}
    counter_by_id = {trade.signal_id: trade for trade in result.counterfactual_lost}
    all_rows: List[tuple[str, str, BacktestTrade]] = []
    all_rows.extend((POP_EXECUTED, _band_for_trade(trade), trade) for trade in result.executed)
    all_rows.extend((POP_LOST_ENTRY, _band_for_lost(lost), counter_by_id[lost.signal_id]) for lost in result.lost if lost.signal_id in counter_by_id)
    all_rows.extend((POP_ALL_SCORE, _band_for_trade(trade), trade) for trade in result.executed)
    all_rows.extend((POP_ALL_SCORE, _band_for_lost(lost), counter_by_id[lost.signal_id]) for lost in result.lost if lost.signal_id in counter_by_id)
    del executed_by_id

    stats: List[PopulationStats] = []
    for band, _, _ in SCORE_BANDS:
        for population in (POP_ALL_SCORE, POP_EXECUTED, POP_LOST_ENTRY):
            trades = [trade for pop, label, trade in all_rows if pop == population and label == band]
            stats.append(_population_stats(population, band, trades, result.horizonte))
    return stats


def _population_stats(population: str, band: str, trades: Sequence[BacktestTrade], horizonte: str) -> PopulationStats:
    rs = [r for r in (trade.net_r_multiple for trade in trades) if r is not None]
    sufficient = len(trades) >= _MIN_SAMPLE and bool(rs)
    block_mean = ci_low = ci_high = None
    if sufficient:
        block_mean, ci_low, ci_high = _block_expectancy(trades, horizonte)
    winners = [r for r in rs if r > 0]
    losers = [r for r in rs if r < 0]
    avg_winner = sum(winners) / len(winners) if winners else None
    avg_loser = abs(sum(losers) / len(losers)) if losers else None
    return PopulationStats(
        population=population,
        band=band,
        n=len(trades),
        sufficient=sufficient,
        wins=sum(1 for trade in trades if trade.won),
        target_exits=sum(1 for trade in trades if trade.exit_reason == "objetivo"),
        stop_exits=sum(1 for trade in trades if trade.exit_reason == "stop"),
        mean_net_r=sum(rs) / len(rs) if sufficient else None,
        block_mean_net_r=block_mean,
        ci_low=ci_low,
        ci_high=ci_high,
        median_net_r=statistics.median(rs) if sufficient else None,
        p10_net_r=_percentile(rs, 10) if sufficient else None,
        p90_net_r=_percentile(rs, 90) if sufficient else None,
        profit_factor=(sum(winners) / abs(sum(losers))) if sufficient and losers else None,
        payoff=(avg_winner / avg_loser) if sufficient and avg_winner is not None and avg_loser not in (None, 0.0) else None,
    )


def _block_expectancy(
    trades: Sequence[BacktestTrade], horizonte: str
) -> Tuple[float, Optional[float], Optional[float]]:
    sessions = sorted({_trade_session(trade) for trade in trades})
    lookup = session_block_lookup(sessions, BLOCK_LENGTH[horizonte])
    by_block: Dict[int, List[float]] = {}
    for trade in trades:
        r = trade.net_r_multiple
        if r is not None:
            by_block.setdefault(lookup[_trade_session(trade)], []).append(r)
    block_values = [(sum(values) / len(values), len(values)) for values in by_block.values() if values]
    mean = sum(value for value, _ in block_values) / len(block_values) if block_values else 0.0
    # Con menos de dos bloques no hay intervalo que calcular:
    # ``bootstrap_block_mean_interval`` devuelve el centinela (0.0, 1.0), que en
    # unidades de R se lee como un intervalo plausible y no lo es. Se declara
    # no calculable en vez de publicarlo.
    if len(block_values) < 2:
        return mean, None, None
    low, high = bootstrap_block_mean_interval(block_values, seed=DEFAULT_SEED, n_resamples=DEFAULT_RESAMPLES)
    return mean, low, high


def _trade_session(trade: BacktestTrade) -> date:
    import pandas as pd

    return pd.Timestamp(trade.entry_date).date()


def _format_stats_row(row: PopulationStats) -> str:
    if not row.sufficient:
        state = f"INSUFICIENTE (<{_MIN_SAMPLE})"
        return (
            f"| {row.band} | {row.population} | {row.n} | {state} | {row.wins}/{row.n} | "
            f"{row.target_exits}/{row.n} | {row.stop_exits}/{row.n} |  |  |  |  |  |  |  |  |"
        )
    assert row.mean_net_r is not None and row.block_mean_net_r is not None
    if row.ci_low is None or row.ci_high is None:
        intervalo = "N/D (menos de 2 bloques)"
        state = "SIN INTERVALO"
    else:
        intervalo = f"[{_fmt(row.ci_low)}, {_fmt(row.ci_high)}]"
        state = "OK"
    return (
        f"| {row.band} | {row.population} | {row.n} | {state} | {row.wins}/{row.n} | "
        f"{row.target_exits}/{row.n} | {row.stop_exits}/{row.n} | {_fmt(row.mean_net_r)} | "
        f"{_fmt(row.block_mean_net_r)} | {intervalo} | "
        f"{_fmt(row.median_net_r)} | {_fmt(row.p10_net_r)} | {_fmt(row.p90_net_r)} | "
        f"{_fmt(row.profit_factor)} | {_fmt(row.payoff)} |"
    )


def _band_for_trade(trade: BacktestTrade) -> str:
    for label, low, high in SCORE_BANDS:
        if trade.score >= low and (high is None or trade.score < high):
            return label
    return SCORE_BANDS[0][0]


def _band_for_lost(signal: ExecutionRejectedSignal) -> str:
    return signal.score_band


def _percentile(values: Sequence[float], q: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * q / 100
    lower = int(k)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = k - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _fmt(value: Optional[float]) -> str:
    return "" if value is None else f"{value:.4f}"


def _resolve_vintage_id(value: str, root_dir: str) -> str:
    root = Path(root_dir)
    if (root / value / "manifest.json").is_file():
        return value
    matches = [path.name for path in root.iterdir() if path.is_dir() and path.name.startswith(value)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise FileNotFoundError(f"No existe la cosecha {value!r} en {root_dir}")
    raise ValueError(f"Prefijo de cosecha ambiguo {value!r}: {matches}")


def _frozen_close(vintage: VintageLoad, symbol: Optional[str]):
    if symbol is None:
        return None
    views = vintage.by_symbol.get(symbol)
    if views is None:
        return None
    return views.signal_prices["Close"]


def _align(series, index):
    if series is None or series.empty:
        return None
    s = series.copy()
    s.index = _naive_dates(s.index)
    s = s[~s.index.duplicated(keep="last")]
    target = _naive_dates(index)
    aligned = s.reindex(s.index.union(target)).ffill().reindex(target)
    aligned.index = index
    return aligned


def _naive_dates(index) -> object:
    import pandas as pd

    idx = pd.DatetimeIndex(index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return idx.normalize()


def _as_optional_list(series) -> Optional[List[Optional[float]]]:
    if series is None:
        return None
    import pandas as pd

    return [None if pd.isna(value) else float(value) for value in series]
