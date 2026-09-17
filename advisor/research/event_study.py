"""Event study P2.3 sobre cosechas congeladas.

Este módulo mide señales potenciales, no operaciones admitidas por la
política. Por eso no usa estado de posición, no llama a ``classify()`` y no
resuelve la ambigüedad OHLC: cuando una vela diaria no permite saber si el
objetivo o el stop fue primero, conserva ese estado como parte del resultado.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import pandas as pd

from advisor.analysis.benchmark import resolve_benchmark_symbol
from advisor.analysis.levels import Levels, compute_levels, compute_levels_from_inputs
from advisor.analysis.market_context import build_market_context
from advisor.analysis.scoring import compute_score
from advisor.analysis.snapshot import SnapshotSeries, build_snapshot_series, snapshot_from_series
from advisor.config import AdvisorConfig, LevelsConfig
from advisor.data.freshness import mercado_para_simbolo
from advisor.data.sessions import market_for_symbol, market_session
from advisor.indicators.technical import sma
from advisor.research.observations import SignalObservation, build_signal_observation
from advisor.research.timestamps import parse_timestamp, timestamp_raw
from advisor.research.vintage import VintageLoad, load_vintage
from advisor.universe.models import Asset, Universe
from advisor.universe.vintage import universe_vintage_id

MAX_HOLD_BARS = {"swing": 40, "medio": 250}

TARGET_FIRST = "TARGET_FIRST"
STOP_FIRST = "STOP_FIRST"
AMBIGUOUS = "AMBIGUOUS"
TIME_EXIT = "TIME"
FINAL_EXIT = "FINAL"

SCORE_BANDS: Tuple[Tuple[str, float, Optional[float]], ...] = (
    ("<50", 0.0, 50.0),
    ("50-60", 50.0, 60.0),
    ("60-70", 60.0, 70.0),
    ("70-80", 70.0, 80.0),
    ("80+", 80.0, None),
)


@dataclass(frozen=True)
class EventEconomics:
    """Contrato numérico P2.1 para una salida observable."""

    risk_pp: float
    gross_return_pp: float
    net_return_pp: float
    gross_r_multiple: float
    net_r_multiple: float


@dataclass(frozen=True)
class ManagedEvent:
    """Resultado administrado: stop, objetivo y duración máxima activos."""

    observation: SignalObservation
    entry_price: float
    stop: float
    target: float
    exit_status: str
    exit_idx: int
    exit_timestamp_raw: str
    exit_timestamp: datetime
    exit_price: Optional[float]
    bars_held: int
    risk_pp: float
    gross_return_pp: Optional[float]
    net_return_pp: Optional[float]
    gross_r_multiple: Optional[float]
    net_r_multiple: Optional[float]
    mae_r: float
    mfe_lower_r: float
    mfe_upper_r: float


@dataclass(frozen=True)
class PotentialEvent:
    """Resultado potencial: stop y horizonte activos, objetivo eliminado."""

    observation: SignalObservation
    entry_price: float
    stop: float
    exit_status: str
    exit_idx: int
    exit_timestamp_raw: str
    exit_timestamp: datetime
    mfe_unbounded_lower_r: float
    mfe_unbounded_upper_r: float


@dataclass(frozen=True)
class EventStudySignal:
    """La misma señal evaluada por las dos familias obligatorias."""

    observation: SignalObservation
    managed: ManagedEvent
    potential: PotentialEvent


@dataclass(frozen=True)
class BandSummary:
    """Intervalo de probabilidad por banda, sin colapsarlo a un punto."""

    label: str
    lower_score: float
    upper_score: Optional[float]
    total: int = 0
    target_first: int = 0
    stop_first: int = 0
    ambiguous: int = 0
    time_exit: int = 0
    final_exit: int = 0
    mean_net_r_multiple: Optional[float] = None
    median_mae_winners_r: Optional[float] = None
    median_mfe_losers_lower_r: Optional[float] = None
    median_mfe_losers_upper_r: Optional[float] = None
    median_mfe_unbounded_lower_r: Optional[float] = None
    median_mfe_unbounded_upper_r: Optional[float] = None

    @property
    def lower(self) -> float:
        return self.target_first / self.total if self.total else 0.0

    @property
    def upper(self) -> float:
        return (self.target_first + self.ambiguous) / self.total if self.total else 0.0


@dataclass(frozen=True)
class EventStudyResult:
    """Resultado completo de una pasada sobre una cosecha verificada."""

    data_vintage_id: str
    horizonte: str
    cost_pct: float
    warmup_bars: int
    max_hold_bars: int
    universe_vintage_id: str = ""
    signals: List[EventStudySignal] = field(default_factory=list)
    evaluated_assets: List[str] = field(default_factory=list)
    asset_bar_counts: Dict[str, int] = field(default_factory=dict)
    session_dates_by_asset: Dict[str, Tuple[date, ...]] = field(default_factory=dict)
    skipped: List[Tuple[str, str]] = field(default_factory=list)

    @property
    def bands(self) -> List[BandSummary]:
        return summarize_by_score_band(self.signals)

    @property
    def status_counts(self) -> Dict[str, int]:
        counts = {TARGET_FIRST: 0, STOP_FIRST: 0, AMBIGUOUS: 0, TIME_EXIT: 0, FINAL_EXIT: 0}
        for signal in self.signals:
            counts[signal.managed.exit_status] = counts.get(signal.managed.exit_status, 0) + 1
        return counts


def event_economics(entry_price: float, stop: float, exit_price: float, cost_pct: float) -> EventEconomics:
    """Calcula P&L en pp y R manteniendo bruto y neto separados."""

    risk = entry_price - stop
    if entry_price <= 0 or risk <= 0:
        raise ValueError("entrada y stop no definen un riesgo largo válido")
    risk_pp = risk / entry_price * 100
    gross_return_pp = (exit_price / entry_price - 1) * 100
    net_return_pp = gross_return_pp - cost_pct
    gross_r_multiple = gross_return_pp / risk_pp
    net_r_multiple = net_return_pp / risk_pp
    return EventEconomics(
        risk_pp=risk_pp,
        gross_return_pp=gross_return_pp,
        net_return_pp=net_return_pp,
        gross_r_multiple=gross_r_multiple,
        net_r_multiple=net_r_multiple,
    )


def classify_target_stop_bar(bar: pd.Series, stop: float, target: float) -> Optional[Tuple[str, float]]:
    """Clasifica una vela sin inventar el orden intradía.

    El hueco de apertura sí ordena el evento: si la apertura ya está fuera de
    los niveles, el primer precio observable de la vela resolvió la salida.
    La ambigüedad solo existe cuando la apertura queda entre stop y objetivo
    y el rango de la vela toca ambos.
    """

    bar_open = float(bar["Open"])
    if bar_open <= stop:
        return STOP_FIRST, bar_open
    if bar_open >= target:
        return TARGET_FIRST, bar_open

    touched_stop = float(bar["Low"]) <= stop
    touched_target = float(bar["High"]) >= target
    if touched_stop and touched_target:
        return AMBIGUOUS, math.nan
    if touched_stop:
        return STOP_FIRST, stop
    if touched_target:
        return TARGET_FIRST, target
    return None


def run_event_study(
    config: AdvisorConfig,
    universe: Universe,
    data_vintage_id: str,
    *,
    horizonte: str = "swing",
    cost_pct: float = 0.2,
    root_dir: str = "data/vintages",
) -> EventStudyResult:
    """Ejecuta P2.3 sobre una cosecha ya congelada y verificada."""

    vintage = load_vintage(data_vintage_id, root_dir=root_dir)
    return run_event_study_on_vintage(config, universe, vintage, horizonte=horizonte, cost_pct=cost_pct)


def run_event_study_on_vintage(
    config: AdvisorConfig,
    universe: Universe,
    vintage: VintageLoad,
    *,
    horizonte: str = "swing",
    cost_pct: float = 0.2,
) -> EventStudyResult:
    """Núcleo con I/O ya resuelto, útil para tests y para la CLI."""

    if horizonte not in MAX_HOLD_BARS:
        raise ValueError(f"el event study solo cubre swing y medio: '{horizonte}'")

    window = config.horizonte(horizonte)
    warmup = window.min_bars
    max_hold = MAX_HOLD_BARS[horizonte]
    result = EventStudyResult(
        data_vintage_id=vintage.data_vintage_id,
        universe_vintage_id=universe_vintage_id(universe),
        horizonte=horizonte,
        cost_pct=cost_pct,
        warmup_bars=warmup,
        max_hold_bars=max_hold,
    )

    vix_close = _frozen_close(vintage, config.market_context.vix_symbol)
    trend_close = _frozen_close(vintage, config.market_context.trend_symbol)
    trend_sma_close = sma(trend_close, config.market_context.trend_sma) if trend_close is not None else None
    benchmark_cache: Dict[str, Optional[pd.Series]] = {}

    for symbol, views in vintage.by_symbol.items():
        asset = universe.get(symbol)
        if asset is None or not asset.analizable:
            continue
        signal_df = views.signal_prices
        execution_df = views.execution_prices
        result.asset_bar_counts[symbol] = len(signal_df)
        result.session_dates_by_asset[symbol] = tuple(
            parse_timestamp(timestamp_raw(timestamp)).astimezone(ZoneInfo(asset.timezone)).date()
            for timestamp in signal_df.index
        )
        if len(signal_df) < warmup + 2 or len(execution_df) != len(signal_df):
            result.skipped.append((symbol, f"histórico insuficiente o vistas desalineadas: {len(signal_df)} velas"))
            continue

        benchmark_symbol = resolve_benchmark_symbol(asset, config.report)
        benchmark_close = None
        if benchmark_symbol is not None:
            if benchmark_symbol not in benchmark_cache:
                benchmark_cache[benchmark_symbol] = _frozen_close(vintage, benchmark_symbol)
            benchmark_close = benchmark_cache[benchmark_symbol]
        try:
            snapshot_series = build_snapshot_series(
                signal_df,
                config.indicators,
                config.levels,
                window.interval,
                benchmark_close,
                asset_timezone=market_session(mercado_para_simbolo(asset, symbol)).timezone,
                benchmark_timezone=(
                    market_session(market_for_symbol(benchmark_symbol)).timezone
                    if benchmark_symbol
                    else None
                ),
            )
        except ValueError as exc:
            result.skipped.append((symbol, str(exc)))
            continue

        vix_aligned = _align(vix_close, signal_df.index) if vix_close is not None else None
        vix_at = _as_optional_list(vix_aligned.shift(1) if vix_aligned is not None else None)
        trend_at = _as_optional_list(_align(trend_close, signal_df.index))
        trend_sma_at = _as_optional_list(_align(trend_sma_close, signal_df.index))

        for j in range(warmup, len(signal_df) - 1):
            signal = _build_event_signal(
                asset,
                snapshot_series,
                j,
                config,
                horizonte,
                warmup,
                vix_at,
                trend_at,
                trend_sma_at,
            )
            if signal is None:
                continue
            levels, observation = signal
            if observation.data_vintage_id != vintage.data_vintage_id:
                observation = _with_vintage_id(observation, vintage.data_vintage_id)

            try:
                managed = evaluate_managed_event(observation, execution_df, j, levels, max_hold, cost_pct)
                potential = evaluate_potential_event(observation, execution_df, j, levels, max_hold)
            except ValueError as exc:
                result.skipped.append((observation.signal_id, str(exc)))
                continue
            result.signals.append(EventStudySignal(observation=observation, managed=managed, potential=potential))

        result.evaluated_assets.append(symbol)

    return result


def replay_managed_population(
    result: EventStudyResult,
    vintage: VintageLoad,
    levels_config: LevelsConfig,
    min_rr_ratio: float,
    *,
    cost_pct: Optional[float] = None,
) -> Dict[str, ManagedEvent]:
    """Reevalúa la población administrada con otros niveles, sin recalcular señales."""

    if result.data_vintage_id != vintage.data_vintage_id:
        raise ValueError(
            f"cosecha distinta: result={result.data_vintage_id} vintage={vintage.data_vintage_id}"
        )
    vintage_universe = vintage.manifest.get("universe_vintage_id")
    if vintage_universe is not None and result.universe_vintage_id != vintage_universe:
        raise ValueError(
            f"universo distinto: result={result.universe_vintage_id} vintage={vintage_universe}"
        )
    replayed: Dict[str, ManagedEvent] = {}
    effective_cost = result.cost_pct if cost_pct is None else cost_pct
    for signal in result.signals:
        obs = signal.observation
        try:
            views = vintage.by_symbol[obs.asset]
        except KeyError:
            raise ValueError(f"{obs.asset}: activo ausente en la cosecha {vintage.data_vintage_id}") from None
        levels = compute_levels_from_inputs(
            price=obs.price,
            atr=obs.atr,
            low_lookback=obs.low_lookback,
            high_lookback=obs.high_lookback,
            ema_fast=obs.ema_fast,
            config=levels_config,
            min_rr_ratio=min_rr_ratio,
        )
        if levels is None:
            raise ValueError(f"{obs.signal_id}: la configuración no produce niveles comparables")
        replayed[obs.signal_id] = evaluate_managed_event(
            obs,
            views.execution_prices,
            obs.signal_idx,
            levels,
            result.max_hold_bars,
            effective_cost,
        )
    return replayed


def evaluate_managed_event(
    observation: SignalObservation,
    df: pd.DataFrame,
    signal_idx: int,
    levels: Levels,
    max_hold_bars: int,
    cost_pct: float,
) -> ManagedEvent:
    """Evalúa stop/objetivo/horizonte desde el cierre de la señal."""

    entry_price = levels.price
    if entry_price <= levels.stop:
        raise ValueError("entrada y stop no definen un riesgo largo válido")
    end = min(len(df) - 1, signal_idx + max_hold_bars)
    if signal_idx >= end:
        raise ValueError("la señal no tiene trayectoria futura evaluable")

    risk = entry_price - levels.stop
    status = FINAL_EXIT if end == len(df) - 1 and end < signal_idx + max_hold_bars else TIME_EXIT
    exit_idx = end
    exit_price: Optional[float] = float(df.iloc[end]["Close"])
    lows: List[float] = []
    max_high = entry_price
    # Máximo de la vela de salida cuando su orden intrabarra es inobservable:
    # se guarda aparte para publicarlo como cota superior, no como hecho.
    unobservable_high: Optional[float] = None

    for i in range(signal_idx + 1, end + 1):
        bar = df.iloc[i]
        lows.append(float(bar["Low"]))
        touch = classify_target_stop_bar(bar, levels.stop, levels.target2)
        if touch is None:
            max_high = max(max_high, float(bar["High"]))
            continue

        status, touched_price = touch
        exit_idx = i
        exit_price = None if math.isnan(touched_price) else touched_price
        # El precio de salida sí es alcanzable; lo que venga después de él en la
        # misma vela no lo es, porque la posición ya está cerrada. Un hueco
        # resuelve el orden y deja el máximo de la vela fuera de alcance; un
        # toque intrabarra no lo resuelve y se conserva como intervalo.
        if exit_price is not None:
            max_high = max(max_high, exit_price)
        if float(bar["Open"]) > levels.stop and float(bar["Open"]) < levels.target2:
            unobservable_high = float(bar["High"])
        break

    mae_r = max(0.0, (entry_price - min(lows)) / risk) if lows else 0.0
    mfe_lower_r = max(0.0, (max_high - entry_price) / risk)
    upper_high = max(max_high, unobservable_high) if unobservable_high is not None else max_high
    mfe_upper_r = max(0.0, (upper_high - entry_price) / risk)
    economics = event_economics(entry_price, levels.stop, exit_price, cost_pct) if exit_price is not None else None

    return ManagedEvent(
        observation=observation,
        entry_price=entry_price,
        stop=levels.stop,
        target=levels.target2,
        exit_status=status,
        exit_idx=exit_idx,
        exit_timestamp_raw=timestamp_raw(df.index[exit_idx]),
        exit_timestamp=parse_timestamp(timestamp_raw(df.index[exit_idx])),
        exit_price=exit_price,
        bars_held=exit_idx - signal_idx,
        risk_pp=event_economics(entry_price, levels.stop, entry_price, 0.0).risk_pp,
        gross_return_pp=economics.gross_return_pp if economics is not None else None,
        net_return_pp=economics.net_return_pp if economics is not None else None,
        gross_r_multiple=economics.gross_r_multiple if economics is not None else None,
        net_r_multiple=economics.net_r_multiple if economics is not None else None,
        mae_r=mae_r,
        mfe_lower_r=mfe_lower_r,
        mfe_upper_r=mfe_upper_r,
    )


def evaluate_potential_event(
    observation: SignalObservation,
    df: pd.DataFrame,
    signal_idx: int,
    levels: Levels,
    max_hold_bars: int,
) -> PotentialEvent:
    """Evalúa el potencial sin objetivo para no truncar el MFE."""

    entry_price = levels.price
    if entry_price <= levels.stop:
        raise ValueError("entrada y stop no definen un riesgo largo válido")
    end = min(len(df) - 1, signal_idx + max_hold_bars)
    if signal_idx >= end:
        raise ValueError("la señal no tiene trayectoria futura evaluable")

    risk = entry_price - levels.stop
    status = FINAL_EXIT if end == len(df) - 1 and end < signal_idx + max_hold_bars else TIME_EXIT
    exit_idx = end
    max_high = entry_price
    # Igual que en el modo administrado: el máximo de la vela en la que salta
    # el stop solo cuenta si pudo ocurrir antes del stop, y eso es
    # inobservable en velas diarias. Un hueco por debajo del stop sí lo
    # resuelve: la posición se cierra en la apertura y el resto de la vela ya
    # no es alcanzable.
    unobservable_high: Optional[float] = None

    for i in range(signal_idx + 1, end + 1):
        bar = df.iloc[i]
        if float(bar["Open"]) <= levels.stop:
            status = STOP_FIRST
            exit_idx = i
            break
        if float(bar["Low"]) <= levels.stop:
            status = STOP_FIRST
            exit_idx = i
            unobservable_high = float(bar["High"])
            break
        max_high = max(max_high, float(bar["High"]))

    upper_high = max(max_high, unobservable_high) if unobservable_high is not None else max_high

    return PotentialEvent(
        observation=observation,
        entry_price=entry_price,
        stop=levels.stop,
        exit_status=status,
        exit_idx=exit_idx,
        exit_timestamp_raw=timestamp_raw(df.index[exit_idx]),
        exit_timestamp=parse_timestamp(timestamp_raw(df.index[exit_idx])),
        mfe_unbounded_lower_r=max(0.0, (max_high - entry_price) / risk),
        mfe_unbounded_upper_r=max(0.0, (upper_high - entry_price) / risk),
    )


def band_of_full_score(signal: EventStudySignal) -> str:
    return score_band(signal.observation.score_value)


def summarize_by_score_band(
    signals: Iterable[EventStudySignal],
    *,
    band_of: Callable[[EventStudySignal], str] = band_of_full_score,
) -> List[BandSummary]:
    """Agrupa por bandas de score y publica intervalos conservando ambiguos."""

    buckets: Dict[str, List[EventStudySignal]] = {label: [] for label, _, _ in SCORE_BANDS}
    for signal in signals:
        label = band_of(signal)
        buckets[label].append(signal)

    summaries: List[BandSummary] = []
    for label, lower, upper in SCORE_BANDS:
        bucket = buckets[label]
        managed = [s.managed for s in bucket]
        target = sum(1 for event in managed if event.exit_status == TARGET_FIRST)
        stop = sum(1 for event in managed if event.exit_status == STOP_FIRST)
        ambiguous = sum(1 for event in managed if event.exit_status == AMBIGUOUS)
        time = sum(1 for event in managed if event.exit_status == TIME_EXIT)
        final = sum(1 for event in managed if event.exit_status == FINAL_EXIT)
        net_r_values = [event.net_r_multiple for event in managed if event.net_r_multiple is not None]
        winners_mae = [event.mae_r for event in managed if event.exit_status == TARGET_FIRST]
        losers_mfe_lower = [event.mfe_lower_r for event in managed if event.exit_status == STOP_FIRST]
        losers_mfe_upper = [event.mfe_upper_r for event in managed if event.exit_status == STOP_FIRST]
        potential_lower = [s.potential.mfe_unbounded_lower_r for s in bucket]
        potential_upper = [s.potential.mfe_unbounded_upper_r for s in bucket]
        summaries.append(
            BandSummary(
                label=label,
                lower_score=lower,
                upper_score=upper,
                total=len(bucket),
                target_first=target,
                stop_first=stop,
                ambiguous=ambiguous,
                time_exit=time,
                final_exit=final,
                mean_net_r_multiple=_mean(net_r_values),
                median_mae_winners_r=_median(winners_mae),
                median_mfe_losers_lower_r=_median(losers_mfe_lower),
                median_mfe_losers_upper_r=_median(losers_mfe_upper),
                median_mfe_unbounded_lower_r=_median(potential_lower),
                median_mfe_unbounded_upper_r=_median(potential_upper),
            )
        )
    return summaries


def format_event_study_report(result: EventStudyResult, estimator_summary: Optional[str] = None) -> str:
    """Informe textual por bandas, manteniendo probabilidades como intervalo."""

    lines = [
        "# Event study P2.3",
        "",
        f"Cosecha: {result.data_vintage_id}",
        f"Universo: {result.universe_vintage_id}",
        f"Horizonte: {result.horizonte} | coste {result.cost_pct:.2f}% | "
        f"warmup {result.warmup_bars} velas | horizonte máximo {result.max_hold_bars} velas",
        f"Activos evaluados: {len(result.evaluated_assets)} | señales evaluadas: {len(result.signals)}",
    ]
    if result.skipped:
        lines.append(f"Saltos registrados: {len(result.skipped)}")
    if estimator_summary is not None:
        lines.extend(["", estimator_summary])
    counts = result.status_counts
    lines.extend(
        [
            "",
            "Estados administrados:",
            f"- {TARGET_FIRST}: {counts.get(TARGET_FIRST, 0)}",
            f"- {STOP_FIRST}: {counts.get(STOP_FIRST, 0)}",
            f"- {AMBIGUOUS}: {counts.get(AMBIGUOUS, 0)}",
            f"- {TIME_EXIT}: {counts.get(TIME_EXIT, 0)}",
            f"- {FINAL_EXIT}: {counts.get(FINAL_EXIT, 0)}",
            "",
            "Banda   n     target stop ambig tiempo final  P(objetivo antes de stop)   net_R medio  "
            "MAE gan.       MFE perd.       MFE sin objetivo",
        ]
    )
    for band in result.bands:
        lines.append(
            f"{band.label:<6} {band.total:>5} {band.target_first:>6} {band.stop_first:>4} "
            f"{band.ambiguous:>5} {band.time_exit:>6} {band.final_exit:>5}  "
            f"[{band.lower:.3f}, {band.upper:.3f}]"
            f"{_fmt_optional(band.mean_net_r_multiple):>13}"
            f"{_fmt_optional(band.median_mae_winners_r):>10}"
            f"  {_fmt_interval(band.median_mfe_losers_lower_r, band.median_mfe_losers_upper_r):>14}"
            f"  {_fmt_interval(band.median_mfe_unbounded_lower_r, band.median_mfe_unbounded_upper_r):>14}"
        )
    return "\n".join(lines)


def _build_event_signal(
    asset: Asset,
    snapshot_series: SnapshotSeries,
    j: int,
    config: AdvisorConfig,
    horizonte: str,
    min_bars: int,
    vix_at: Optional[Sequence[Optional[float]]],
    trend_price_at: Optional[Sequence[Optional[float]]],
    trend_sma_at: Optional[Sequence[Optional[float]]],
) -> Optional[Tuple[Levels, SignalObservation]]:
    try:
        snapshot = snapshot_from_series(asset.symbol, snapshot_series, j)
    except ValueError:
        return None
    levels = compute_levels(snapshot, config.levels, config.risk.min_rr_ratio)
    if levels is None:
        return None
    context = build_market_context(
        vix_at[j] if vix_at is not None else None,
        trend_price_at[j] if trend_price_at is not None else None,
        trend_sma_at[j] if trend_sma_at is not None else None,
        config.market_context,
    )
    score = compute_score(snapshot, levels, context, config.scoring, min_bars)
    observation = build_signal_observation(asset=asset, horizonte=horizonte, signal_idx=j, snapshot=snapshot, score=score)
    primitive_levels = compute_levels_from_inputs(
        price=observation.price,
        atr=observation.atr,
        low_lookback=observation.low_lookback,
        high_lookback=observation.high_lookback,
        ema_fast=observation.ema_fast,
        config=config.levels,
        min_rr_ratio=config.risk.min_rr_ratio,
    )
    if primitive_levels is None:
        return None
    return primitive_levels, observation


def _with_vintage_id(observation: SignalObservation, data_vintage_id: str) -> SignalObservation:
    return SignalObservation(
        signal_id=observation.signal_id,
        data_vintage_id=data_vintage_id,
        asset=observation.asset,
        horizonte=observation.horizonte,
        signal_idx=observation.signal_idx,
        signal_timestamp_raw=observation.signal_timestamp_raw,
        signal_timestamp=observation.signal_timestamp,
        score_value=observation.score_value,
        evaluable_max=observation.evaluable_max,
        dimensions=observation.dimensions,
        price=observation.price,
        atr=observation.atr,
        low_lookback=observation.low_lookback,
        high_lookback=observation.high_lookback,
        ema_fast=observation.ema_fast,
    )


def score_band(score: float) -> str:
    for label, lower, upper in SCORE_BANDS:
        if score >= lower and (upper is None or score < upper):
            return label
    return SCORE_BANDS[0][0]


def _score_band(score: float) -> str:
    return score_band(score)


def _frozen_close(vintage: VintageLoad, symbol: Optional[str]) -> Optional[pd.Series]:
    if symbol is None:
        return None
    views = vintage.by_symbol.get(symbol)
    if views is None:
        return None
    return views.signal_prices["Close"]


def _naive_dates(index: pd.Index) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return idx.normalize()


def _align(series: Optional[pd.Series], index: pd.Index) -> Optional[pd.Series]:
    if series is None or series.empty:
        return None
    s = series.copy()
    s.index = _naive_dates(s.index)
    s = s[~s.index.duplicated(keep="last")]
    target = _naive_dates(index)
    aligned = s.reindex(s.index.union(target)).ffill().reindex(target)
    aligned.index = index
    return aligned


def _as_optional_list(series: Optional[pd.Series]) -> Optional[Sequence[Optional[float]]]:
    if series is None:
        return None
    return [None if pd.isna(v) else float(v) for v in series]


def _mean(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def _median(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _fmt_interval(lower: Optional[float], upper: Optional[float]) -> str:
    """Intervalo de una excursión: el orden intrabarra no se colapsa a un punto."""

    if lower is None or upper is None:
        return "n/d"
    return f"[{lower:.2f}, {upper:.2f}]"


def _fmt_optional(value: Optional[float]) -> str:
    return "N/D" if value is None else f"{value:.2f}"
