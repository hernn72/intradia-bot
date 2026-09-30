"""Censo de población P3 sin leer desenlaces."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Mapping
from unittest.mock import patch

import advisor.research.event_study as event_study
from advisor.analysis.overview import context_assets_of
from advisor.config import AdvisorConfig
from advisor.context.point_in_time import (
    EXCLUDED_ASIA_MISSING,
    EXCLUDED_CRYPTO,
    EXCLUDED_TREND_SMA_HISTORY,
    NO_CALCULABLE_CONTEXT_VIX,
    PointInTimeContextResolver,
    analysis_timestamp_for_signal,
)
from advisor.data.freshness import mercado_para_simbolo
from advisor.data.sessions import CRYPTO_MIC, market_session, session_date_of
from advisor.research.capacity import _protocol_block_length, _temporal_block_lookup
from advisor.research.event_study import EventStudySignal
from advisor.research.vintage import VintageLoad, frozen_close
from advisor.universe.models import Universe


@dataclass(frozen=True)
class P3PopulationControl:
    horizonte: str
    a02_population: int
    rows_by_reason: Mapping[str, tuple[tuple[object, ...], ...]]
    final_population: tuple[tuple[str, date], ...]
    stoxx_gap_rows: tuple[tuple[object, ...], ...]
    blocks_with_signals: int
    skipped: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def union_excluded(self) -> int:
        excluded = {
            (str(row[0]), row[1])
            for rows in self.rows_by_reason.values()
            for row in rows
        }
        return len(excluded)

    @property
    def final_sha256(self) -> str:
        lines = sorted(f"{asset}\t{session}" for asset, session in self.final_population)
        return hashlib.sha256("\n".join(lines).encode()).hexdigest()

    @property
    def stoxx_gap_ages(self) -> Mapping[int, int]:
        return dict(sorted(Counter(row[5] for row in self.stoxx_gap_rows if isinstance(row[5], int)).items()))


def census_p3_population(
    config: AdvisorConfig,
    universe: Universe,
    vintage: VintageLoad,
    *,
    horizonte: str,
    population_name: str = "vigente",
) -> P3PopulationControl:
    """Reconstruye la población A-02 y aplica D-51/D-52/D-55 como unión."""

    with (
        patch.object(event_study, "evaluate_managed_event", _no_outcome),
        patch.object(event_study, "evaluate_potential_event", _no_outcome),
    ):
        result = event_study.run_event_study_on_vintage(
            config,
            universe,
            vintage,
            horizonte=horizonte,
            population_name=population_name,
            context_mode="legacy_v1",
        )

    asia_symbols = tuple(
        sorted(asset.primary_symbol for asset in context_assets_of(universe) if asset.region == "ASIA")
    )
    context_symbols = (config.market_context.vix_symbol, config.market_context.trend_symbol, *asia_symbols)
    closes = {
        symbol: close
        for symbol in context_symbols
        if (close := frozen_close(vintage, symbol)) is not None
    }
    reasons: dict[str, list[tuple[object, ...]]] = {
        EXCLUDED_CRYPTO: [],
        EXCLUDED_ASIA_MISSING: [],
        EXCLUDED_TREND_SMA_HISTORY: [],
    }
    final: list[tuple[str, date]] = []
    stoxx_gaps: list[tuple[object, ...]] = []
    final_signals: list[EventStudySignal] = []
    context_resolver = PointInTimeContextResolver(
        closes,
        config.market_context,
        asia_symbols=asia_symbols,
        settlement_minutes=config.data_quality.settlement_minutes,
    )

    for signal in result.signals:
        asset = universe.get(signal.observation.asset)
        if asset is None:
            continue
        views = vintage.by_symbol[asset.primary_symbol]
        market = mercado_para_simbolo(asset, asset.primary_symbol)
        signal_idx = signal.observation.signal_idx
        signal_session = session_date_of(views.signal_prices.index[signal_idx], market)
        if signal_session is None:
            continue
        excluded: set[str] = set()
        if market_session(market).mic == CRYPTO_MIC:
            excluded.add(EXCLUDED_CRYPTO)
            reasons[EXCLUDED_CRYPTO].append((asset.symbol, signal_session))
        else:
            entry_session = session_date_of(views.signal_prices.index[signal_idx + 1], market)
            if entry_session is None:
                continue
            analysis_timestamp = analysis_timestamp_for_signal(
                market,
                signal_session,
                entry_session,
                settlement_minutes=config.data_quality.settlement_minutes,
            )
            if analysis_timestamp is None:
                raise RuntimeError(f"{asset.symbol} {signal_session}: sin analysis_timestamp D-50")
            context = context_resolver.resolve(analysis_timestamp)
            if NO_CALCULABLE_CONTEXT_VIX in context.no_calculable_codes:
                raise RuntimeError(f"{asset.symbol} {signal_session}: {NO_CALCULABLE_CONTEXT_VIX}")
            if EXCLUDED_ASIA_MISSING in context.exclusions:
                excluded.add(EXCLUDED_ASIA_MISSING)
                reasons[EXCLUDED_ASIA_MISSING].append(
                    (
                        asset.symbol,
                        signal_session,
                        analysis_timestamp.isoformat(),
                        "; ".join(f"{m.symbol}:{m.missing}:{m.session}" for m in context.asia_missing),
                    )
                )
            if EXCLUDED_TREND_SMA_HISTORY in context.exclusions:
                excluded.add(EXCLUDED_TREND_SMA_HISTORY)
                reasons[EXCLUDED_TREND_SMA_HISTORY].append(
                    (asset.symbol, signal_session, analysis_timestamp.isoformat(), context.trend_sma_count)
                )
            if context.stoxx_age_days is not None and context.stoxx_age_days > 0 and not excluded:
                stoxx_gaps.append(
                    (
                        asset.symbol,
                        signal_session,
                        analysis_timestamp.isoformat(),
                        context.trend_expected_session,
                        context.trend_used_session,
                        context.stoxx_age_days,
                    )
                )
        if not excluded:
            final.append((asset.symbol, signal_session))
            final_signals.append(signal)

    block_length = _protocol_block_length(horizonte, event_study.MAX_HOLD_BARS[horizonte])
    block_lookup = _temporal_block_lookup(result, block_length, universe)
    blocks = len({block_lookup.block_for(signal) for signal in final_signals})
    return P3PopulationControl(
        horizonte=horizonte,
        a02_population=len(result.signals),
        rows_by_reason={key: tuple(value) for key, value in reasons.items()},
        final_population=tuple(final),
        stoxx_gap_rows=tuple(stoxx_gaps),
        blocks_with_signals=blocks,
        skipped=tuple(result.skipped),
    )


def _no_outcome(*args: object, **kwargs: object) -> None:
    return None
