"""Gate P2.5 de capacidad estadística antes de calibrar umbrales.

El objetivo no es descubrir cortes de producción, sino impedir que una banda
con poca profundidad parezca concluyente por tener muchas señales solapadas.
El intervalo se estima con bootstrap P2.6 sobre medias por bloque temporal:
cada bloque contiene todos los activos y produce una proporción, evitando
tratar señales solapadas como ensayos independientes.
Los cortes siguientes son parámetros provisionales de ingeniería: no son
verdad estadística ni sustituyen un diseño formal de inferencia.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from advisor.data.sessions import market_timezone
from advisor.research.bootstrap import (
    DEFAULT_RESAMPLES,
    DEFAULT_SEED,
    bootstrap_block_mean_interval,
    session_block_lookup,
)
from advisor.research.event_study import (
    AMBIGUOUS,
    FINAL_EXIT,
    SCORE_BANDS,
    STOP_FIRST,
    TARGET_FIRST,
    EventStudyResult,
    EventStudySignal,
    band_of_full_score,
    score_band,
)
from advisor.universe.models import Asset, Universe

RESOLUTION_HIGH = "HIGH"
RESOLUTION_MEDIUM = "MEDIUM"
RESOLUTION_LOW = "LOW"
RESOLUTION_INSUFFICIENT = "INSUFFICIENT"

SUFICIENTE = "SUFICIENTE"
LIMITADA = "LIMITADA"
INSUFICIENTE = "INSUFICIENTE"


@dataclass(frozen=True)
class CapacityThresholds:
    """Parámetros provisionales, centralizados para no convertirlos en dogma."""

    sufficient_blocks: int = 25
    limited_blocks: int = 12
    sufficient_n: int = 300
    limited_n: int = 100
    sufficient_interval_width: float = 0.12
    limited_interval_width: float = 0.20
    max_exit_final_rate: float = 0.10
    max_ambiguous_rate: float = 0.25
    min_observations_per_block: int = 5


DEFAULT_THRESHOLDS = CapacityThresholds()

PROTOCOL_BLOCK_LENGTH_SESSIONS = {
    "swing": 60,
    "medio": 300,
}

@dataclass(frozen=True)
class CapacitySummary:
    """Materia prima y veredicto de capacidad de una población."""

    label: str
    nominal_n: int
    n_by_band: Dict[str, int]
    n_blocks: int
    block_length: int
    primary_expectancy_net_r: float
    primary_interval_lower: Optional[float]
    primary_interval_upper: Optional[float]
    primary_interval_width: Optional[float]
    secondary_target_first_interval_lower: float
    secondary_target_first_interval_upper: float
    secondary_target_first_interval_width: float
    min_block_observations: int
    mean_block_observations: float
    exit_final_rate: float
    ambiguous_rate: float
    resolution: str
    conclusive: bool
    verdict: str
    reasons: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def interval_lower(self) -> float:
        return self.primary_interval_lower if self.primary_interval_lower is not None else 0.0

    @property
    def interval_upper(self) -> float:
        return self.primary_interval_upper if self.primary_interval_upper is not None else 0.0

    @property
    def interval_width(self) -> float:
        return self.primary_interval_width if self.primary_interval_width is not None else 0.0


@dataclass(frozen=True)
class CapacityComparison:
    """Capacidad de una comparación concreta entre bandas."""

    label: str
    left: CapacitySummary
    right: CapacitySummary
    interval_left: Tuple[Optional[float], Optional[float]]
    interval_right: Tuple[Optional[float], Optional[float]]
    interval_width: Optional[float]
    resolution: str
    conclusive: bool
    verdict: str
    reasons: Tuple[str, ...]


@dataclass(frozen=True)
class CapacityReport:
    """Resultado completo del gate P2.5 para un horizonte."""

    horizonte: str
    global_summary: CapacitySummary
    bands: List[CapacitySummary]
    comparisons: List[CapacityComparison]
    estimators: Optional[PreregisteredEstimatorSummary] = None


@dataclass(frozen=True)
class PrimaryEstimatorRow:
    label: str
    n: int
    n_blocks: int
    mean: float
    interval_lower: Optional[float]
    interval_upper: Optional[float]

    @property
    def has_interval(self) -> bool:
        return self.interval_lower is not None and self.interval_upper is not None


@dataclass(frozen=True)
class PreregisteredEstimatorSummary:
    """Estimadores fijados el 2026-09-02 antes de volver a mirar resultados."""

    block_length: int
    n_blocks: int
    n_observable: int
    primary_block_expectancy_net_r: float
    secondary_pooled_expectancy_net_r: float
    secondary_pooled_target_first_rate: float
    secondary_target_first_lower: float
    secondary_target_first_upper: float
    primary_interval_lower: Optional[float] = None
    primary_interval_upper: Optional[float] = None
    primary_by_band: List[PrimaryEstimatorRow] = field(default_factory=list)
    primary_by_region: List[PrimaryEstimatorRow] = field(default_factory=list)
    primary_by_asset: List[PrimaryEstimatorRow] = field(default_factory=list)


@dataclass(frozen=True)
class TemporalBlockMap:
    """Mapa P2.5: bloques de sesiones de bolsa, no de fechas UTC observadas.

    La espina se construye con sesiones de activos no cripto. Las señales de
    cripto se asignan a la última sesión de esa espina que no sea posterior a
    su fecha civil UTC; pueden participar en un bloque, pero no crear sesiones
    ni bloques para los demás activos.
    """

    block_length: int
    session_spine: Tuple[date, ...]
    session_to_block: Dict[date, int]
    assets: Dict[str, Asset]

    def session_date(self, signal: EventStudySignal) -> date:
        asset = self._asset(signal)
        zone = _market_zone(asset)
        return signal.observation.signal_timestamp.astimezone(zone).date()

    def effective_session_date(self, signal: EventStudySignal) -> date:
        session = self.session_date(signal)
        asset = self._asset(signal)
        if asset.asset_class == "crypto":
            spine_index = bisect_right(self.session_spine, session) - 1
            if spine_index < 0:
                raise ValueError(
                    f"{asset.symbol}: señal cripto {session.isoformat()} anterior a la primera sesión de bolsa"
                )
            return self.session_spine[spine_index]
        return session

    def sessions_in_block(self, block: int) -> int:
        """Sesiones de bolsa REALES de un bloque.

        No tienen por que ser `block_length`: el ultimo bloque de la espina es
        el resto de la division y puede quedarse corto. P2.5 exige que el bloque
        supere `MAX_HOLD_BARS`, y esa exigencia es sobre la ventana real, no
        sobre la nominal.
        """

        return sum(1 for assigned in self.session_to_block.values() if assigned == block)

    def block_for(self, signal: EventStudySignal) -> int:
        session = self.effective_session_date(signal)
        asset = self._asset(signal)
        try:
            return self.session_to_block[session]
        except KeyError:
            raise ValueError(
                f"{asset.symbol}: fecha de sesión {session.isoformat()} no existe en la espina de bolsa"
            ) from None

    def _asset(self, signal: EventStudySignal) -> Asset:
        symbol = signal.observation.asset
        try:
            return self.assets[symbol]
        except KeyError:
            raise ValueError(f"{symbol}: activo sin metadatos de universo para calcular bloques temporales") from None


def assess_capacity(
    result: EventStudyResult,
    *,
    universe: Universe,
    thresholds: CapacityThresholds = DEFAULT_THRESHOLDS,
    comparisons: Sequence[Tuple[str, str]] = (("50-60", "80+"),),
    band_of: Callable[[EventStudySignal], str] = band_of_full_score,
) -> CapacityReport:
    """Evalúa capacidad global, por banda y por comparación concreta."""

    block_length = _protocol_block_length(result.horizonte, result.max_hold_bars)
    block_lookup = _temporal_block_lookup(result, block_length, universe)
    global_summary = _summary(
        "GLOBAL",
        result.signals,
        block_length=block_length,
        block_lookup=block_lookup,
        thresholds=thresholds,
        max_hold_bars=result.max_hold_bars,
        band_of=band_of,
    )
    band_summaries = [
        _summary(
            label,
            [signal for signal in result.signals if band_of(signal) == label],
            block_length=block_length,
            block_lookup=block_lookup,
            thresholds=thresholds,
            max_hold_bars=result.max_hold_bars,
            band_of=band_of,
        )
        for label, _, _ in SCORE_BANDS
    ]
    by_label = {summary.label: summary for summary in band_summaries}
    capacity_comparisons = [
        _comparison(by_label[left], by_label[right], thresholds=thresholds)
        for left, right in comparisons
        if left in by_label and right in by_label
    ]
    return CapacityReport(
        horizonte=result.horizonte.upper(),
        global_summary=global_summary,
        bands=band_summaries,
        comparisons=capacity_comparisons,
        estimators=preregistered_estimators(result, universe=universe, block_lookup=block_lookup),
    )


def format_capacity_report(report: CapacityReport) -> str:
    """Informe textual del gate: veredicto y materia prima inseparables."""

    if report.estimators is None:
        raise ValueError("INV-14: no se publica capacidad sin estimador primario")
    lines = [
        report.horizonte,
        f"Capacidad global: {report.global_summary.verdict}",
        _format_summary(report.global_summary),
    ]
    lines.extend(["", format_preregistered_estimators(report.estimators)])
    lines.extend(["", "Bandas de score:"])
    for summary in report.bands:
        lines.append(f"Score {summary.label}: {summary.verdict}")
        lines.append(_format_summary(summary))
    if report.comparisons:
        lines.append("")
        lines.append("Comparaciones:")
        for comparison in report.comparisons:
            lines.append(f"{comparison.label}: {comparison.verdict}")
            width = "N/D" if comparison.interval_width is None else f"{comparison.interval_width:.3f}"
            lines.append(
                "  intervalos primarios="
                f"{_fmt_optional_interval(*comparison.interval_left)} vs "
                f"{_fmt_optional_interval(*comparison.interval_right)}; "
                f"anchura_max={width}; resolution={comparison.resolution}; "
                f"conclusive={comparison.conclusive}; reasons={list(comparison.reasons)}"
            )
    if any(summary.label == "80+" and not summary.conclusive for summary in report.bands):
        lines.append("")
        lines.append("Conclusión: no se permite calibrar un threshold apoyándose en 80+.")
    return "\n".join(lines)


def preregistered_estimators(
    result: EventStudyResult,
    *,
    universe: Universe,
    block_lookup: Optional[TemporalBlockMap] = None,
) -> PreregisteredEstimatorSummary:
    """Calcula el paquete de estimadores pre-registrado el 2026-09-02."""

    block_length = _protocol_block_length(result.horizonte, result.max_hold_bars)
    lookup = block_lookup or _temporal_block_lookup(result, block_length, universe)
    primary_global = _primary_expectancy_row("GLOBAL", result.signals, lookup)
    pooled_values = [
        signal.managed.net_r_multiple
        for signal in result.signals
        if signal.managed.net_r_multiple is not None
    ]
    total = len(result.signals)
    target_first = sum(1 for signal in result.signals if signal.managed.exit_status == TARGET_FIRST)
    ambiguous = sum(1 for signal in result.signals if signal.managed.exit_status == AMBIGUOUS)
    resolved = sum(
        1
        for signal in result.signals
        if signal.managed.exit_status in {TARGET_FIRST, STOP_FIRST}
    )
    return PreregisteredEstimatorSummary(
        block_length=block_length,
        n_blocks=primary_global.n_blocks,
        n_observable=len(pooled_values),
        primary_block_expectancy_net_r=primary_global.mean,
        primary_interval_lower=primary_global.interval_lower,
        primary_interval_upper=primary_global.interval_upper,
        primary_by_band=[
            _primary_expectancy_row(label, [signal for signal in result.signals if score_band(signal.observation.score_value) == label], lookup)
            for label, _, _ in SCORE_BANDS
        ],
        primary_by_region=_primary_rows_by_region(result.signals, lookup),
        primary_by_asset=_primary_rows_by_asset(result.signals, lookup),
        secondary_pooled_expectancy_net_r=_mean_float(pooled_values) or 0.0,
        secondary_pooled_target_first_rate=target_first / resolved if resolved else 0.0,
        secondary_target_first_lower=target_first / total if total else 0.0,
        secondary_target_first_upper=(target_first + ambiguous) / total if total else 0.0,
    )


def format_preregistered_estimators(summary: PreregisteredEstimatorSummary) -> str:
    """Texto común: primario y secundarios juntos, nunca separados."""

    lines = [
        "Estimadores pre-registrados 2026-09-02:",
        "Primario: media por bloque de expectancy neta en R "
        f"{summary.primary_block_expectancy_net_r:+.3f}; "
        f"IC95={_fmt_optional_interval(summary.primary_interval_lower, summary.primary_interval_upper)}; "
        f"bloques={summary.n_blocks}; longitud={summary.block_length} sesiones.",
        "Primario por banda:",
        _format_primary_rows(summary.primary_by_band),
        "Primario por región:",
        _format_primary_rows(summary.primary_by_region),
        "Primario por activo:",
        _format_primary_rows(summary.primary_by_asset),
        "Secundarios: "
        f"tasa agrupada expectancy neta en R {summary.secondary_pooled_expectancy_net_r:+.3f}; "
        f"tasa agrupada TARGET_FIRST/(TARGET_FIRST+STOP_FIRST) {summary.secondary_pooled_target_first_rate:.3f}; "
        f"P(objetivo antes de stop) [{summary.secondary_target_first_lower:.3f}, {summary.secondary_target_first_upper:.3f}].",
    ]
    return "\n".join(lines)


def _summary(
    label: str,
    signals: Sequence[EventStudySignal],
    *,
    block_length: int,
    block_lookup: TemporalBlockMap,
    thresholds: CapacityThresholds,
    max_hold_bars: int,
    band_of: Callable[[EventStudySignal], str] = band_of_full_score,
) -> CapacitySummary:
    nominal_n = len(signals)
    n_by_band = {band: 0 for band, _, _ in SCORE_BANDS}
    for signal in signals:
        n_by_band[band_of(signal)] += 1

    n_blocks = _temporal_blocks(signals, block_lookup)
    primary = _primary_expectancy_row(label, signals, block_lookup)
    block_rates = _block_success_rates(signals, block_lookup)
    secondary_interval = _block_mean_interval(block_rates)
    secondary_interval_width = secondary_interval[1] - secondary_interval[0]
    primary_width = (
        primary.interval_upper - primary.interval_lower
        if primary.interval_lower is not None and primary.interval_upper is not None
        else None
    )
    block_sizes = [total for _, total in block_rates]
    min_block_observations = min(block_sizes) if block_sizes else 0
    mean_block_observations = sum(block_sizes) / len(block_sizes) if block_sizes else 0.0
    exit_final_rate = _rate(sum(1 for signal in signals if signal.managed.exit_status == FINAL_EXIT), nominal_n)
    ambiguous_rate = _rate(sum(1 for signal in signals if signal.managed.exit_status == AMBIGUOUS), nominal_n)
    resolution, verdict, conclusive, reasons = _classify_capacity(
        nominal_n=nominal_n,
        n_blocks=n_blocks,
        interval_width=primary_width,
        exit_final_rate=exit_final_rate,
        ambiguous_rate=ambiguous_rate,
        thresholds=thresholds,
        min_block_observations=min_block_observations,
        min_block_sessions=_shortest_occupied_block(signals, block_lookup),
        max_hold_bars=max_hold_bars,
    )
    return CapacitySummary(
        label=label,
        nominal_n=nominal_n,
        n_by_band=n_by_band,
        n_blocks=n_blocks,
        block_length=block_length,
        primary_expectancy_net_r=primary.mean,
        primary_interval_lower=primary.interval_lower,
        primary_interval_upper=primary.interval_upper,
        primary_interval_width=primary_width,
        secondary_target_first_interval_lower=secondary_interval[0],
        secondary_target_first_interval_upper=secondary_interval[1],
        secondary_target_first_interval_width=secondary_interval_width,
        min_block_observations=min_block_observations,
        mean_block_observations=mean_block_observations,
        exit_final_rate=exit_final_rate,
        ambiguous_rate=ambiguous_rate,
        resolution=resolution,
        conclusive=conclusive,
        verdict=verdict,
        reasons=tuple(reasons),
    )


def _comparison(
    left: CapacitySummary,
    right: CapacitySummary,
    *,
    thresholds: CapacityThresholds,
) -> CapacityComparison:
    interval_left = (left.primary_interval_lower, left.primary_interval_upper)
    interval_right = (right.primary_interval_lower, right.primary_interval_upper)
    overlap = _intervals_overlap(interval_left, interval_right)
    widths = [
        value
        for value in (left.primary_interval_width, right.primary_interval_width)
        if value is not None
    ]
    interval_width = max(widths) if widths else None
    reasons: List[str] = []
    if not left.conclusive:
        reasons.append(f"{left.label} no concluyente")
    if not right.conclusive:
        reasons.append(f"{right.label} no concluyente")
    if interval_width is None:
        reasons.append("intervalo primario no publicable")
    elif overlap:
        reasons.append("los intervalos se solapan")
    resolution = max((left.resolution, right.resolution), key=_resolution_rank)
    conclusive = left.conclusive and right.conclusive and not overlap
    verdict = SUFICIENTE if conclusive else INSUFICIENTE
    return CapacityComparison(
        label=f"{left.label} vs {right.label}",
        left=left,
        right=right,
        interval_left=interval_left,
        interval_right=interval_right,
        interval_width=interval_width,
        resolution=resolution,
        conclusive=conclusive,
        verdict=verdict,
        reasons=tuple(reasons),
    )


def _shortest_occupied_block(
    signals: Sequence[EventStudySignal],
    block_lookup: TemporalBlockMap,
) -> Optional[int]:
    """Sesiones reales del bloque MAS CORTO de los que alimentan el estimador.

    Solo cuentan los bloques ocupados: un bloque sin señales no entra en la
    media por bloque y por tanto no puede invalidarla.
    """

    ocupados = {block_lookup.block_for(signal) for signal in signals}
    if not ocupados:
        return None
    return min(block_lookup.sessions_in_block(block) for block in ocupados)


def _classify_capacity(
    *,
    nominal_n: int,
    n_blocks: int,
    interval_width: Optional[float],
    exit_final_rate: float,
    ambiguous_rate: float,
    thresholds: CapacityThresholds,
    min_block_observations: int,
    min_block_sessions: Optional[int] = None,
    max_hold_bars: Optional[int] = None,
) -> Tuple[str, str, bool, List[str]]:
    reasons: List[str] = []
    if nominal_n == 0:
        return RESOLUTION_INSUFFICIENT, INSUFICIENTE, False, ["sin observaciones"]
    # P2.5: el bloque debe SUPERAR `MAX_HOLD_BARS`, y la exigencia es sobre la
    # ventana REAL. El ultimo bloque de la espina es el resto de la division y
    # puede quedarse corto: entonces no cabe una operacion completa y el
    # horizonte queda invalidado. El motivo se ACUMULA con los demas en vez de
    # sustituirlos —los otros siguen siendo ciertos y se publican— pero impide
    # cualquier veredicto distinto de INSUFFICIENT, tambien si el intervalo
    # sale estrecho. La materia prima numerica se conserva; lo que se niega es
    # su uso para calibrar o concluir.
    bloque_parcial = (
        min_block_sessions is not None
        and max_hold_bars is not None
        # `<=`, no `<`: P2.5 exige que el bloque SUPERE `MAX_HOLD_BARS`, asi que
        # la igualdad tampoco vale. Es el mismo criterio que la validacion
        # NOMINAL de `_protocol_block_length`, y tiene que seguir siendolo: si
        # las dos divergen, un bloque real de exactamente 250 sesiones pasaria
        # aqui mientras uno nominal de 250 se rechaza alli.
        and min_block_sessions <= max_hold_bars
    )
    if bloque_parcial:
        reasons.append(
            f"bloque temporal parcial {min_block_sessions} sesiones <= MAX_HOLD_BARS "
            f"{max_hold_bars}: no utilizable para calibración ni conclusión"
        )
    if exit_final_rate > thresholds.max_exit_final_rate:
        reasons.append(f"censura EXIT_FINAL {exit_final_rate:.1%} > {thresholds.max_exit_final_rate:.1%}")
    if ambiguous_rate > thresholds.max_ambiguous_rate:
        reasons.append(f"ambigüedad {ambiguous_rate:.1%} > {thresholds.max_ambiguous_rate:.1%}")
    if min_block_observations < thresholds.min_observations_per_block:
        reasons.append(
            f"bloque mínimo {min_block_observations} < {thresholds.min_observations_per_block} observaciones"
        )

    if (
        not bloque_parcial
        and n_blocks >= thresholds.sufficient_blocks
        and nominal_n >= thresholds.sufficient_n
        and interval_width is not None
        and interval_width <= thresholds.sufficient_interval_width
        and not reasons
    ):
        return RESOLUTION_HIGH, SUFICIENTE, True, []
    if (
        not bloque_parcial
        and n_blocks >= thresholds.limited_blocks
        and nominal_n >= thresholds.limited_n
        and interval_width is not None
        and interval_width <= thresholds.limited_interval_width
    ):
        return RESOLUTION_MEDIUM, LIMITADA, not reasons, reasons

    if n_blocks < thresholds.limited_blocks:
        reasons.append(f"bloques {n_blocks} < {thresholds.limited_blocks}")
    if nominal_n < thresholds.limited_n:
        reasons.append(f"n {nominal_n} < {thresholds.limited_n}")
    if interval_width is None:
        reasons.append("intervalo primario no publicable")
    elif interval_width > thresholds.limited_interval_width:
        reasons.append(f"intervalo {interval_width:.3f} > {thresholds.limited_interval_width:.3f}")
    if bloque_parcial:
        return RESOLUTION_INSUFFICIENT, INSUFICIENTE, False, reasons
    return RESOLUTION_LOW, INSUFICIENTE, False, reasons


def _protocol_block_length(horizonte: str, max_hold_bars: int) -> int:
    key = horizonte.lower()
    try:
        block_length = PROTOCOL_BLOCK_LENGTH_SESSIONS[key]
    except KeyError:
        raise ValueError(f"P2.5 no define longitud de bloque para horizonte '{horizonte}'") from None
    if block_length <= max_hold_bars:
        raise ValueError(
            f"bloque P2.5 inválido para {key}: {block_length} sesiones <= MAX_HOLD_BARS {max_hold_bars}"
        )
    return block_length


def _temporal_block_lookup(result: EventStudyResult, block_length: int, universe: Universe) -> TemporalBlockMap:
    assets = _assets_for_result(result, universe)
    spine = _equity_session_spine(result, assets)
    session_to_block = session_block_lookup(spine, block_length)
    return TemporalBlockMap(
        block_length=block_length,
        session_spine=spine,
        session_to_block=session_to_block,
        assets=assets,
    )


def _assets_for_result(result: EventStudyResult, universe: Universe) -> Dict[str, Asset]:
    assets: Dict[str, Asset] = {}
    symbols = {
        *result.session_dates_by_asset.keys(),
        *(signal.observation.asset for signal in result.signals),
    }
    for symbol in symbols:
        asset = universe.get(symbol)
        if asset is None:
            raise ValueError(f"{symbol}: activo sin metadatos de universo para calcular bloques temporales")
        _market_zone(asset)
        assets[symbol] = asset
    return assets


def _equity_session_spine(result: EventStudyResult, assets: Dict[str, Asset]) -> Tuple[date, ...]:
    dates = {
        session_date
        for symbol, asset in assets.items()
        if asset.asset_class != "crypto"
        for session_date in result.session_dates_by_asset.get(symbol, ())
    }
    if not dates:
        raise ValueError("P2.5 necesita al menos un activo no cripto para construir la espina de sesiones")
    weekend_dates = sorted(day for day in dates if day.weekday() >= 5)
    if weekend_dates:
        sample = ", ".join(day.isoformat() for day in weekend_dates[:5])
        raise ValueError(f"la espina de sesiones de bolsa contiene fines de semana: {sample}")
    return tuple(sorted(dates))


def _market_zone(asset: Asset):
    try:
        return market_timezone(asset.primary_market)
    except ValueError:
        raise ValueError(f"{asset.symbol}: plaza '{asset.primary_market}' sin cierre regular declarado") from None


def _temporal_blocks(signals: Sequence[EventStudySignal], block_lookup: TemporalBlockMap) -> int:
    return len({block_lookup.block_for(signal) for signal in signals})


def _primary_expectancy_row(
    label: str,
    signals: Sequence[EventStudySignal],
    block_lookup: TemporalBlockMap,
) -> PrimaryEstimatorRow:
    buckets: Dict[int, List[float]] = {}
    for signal in signals:
        value = signal.managed.net_r_multiple
        if value is None:
            continue
        buckets.setdefault(block_lookup.block_for(signal), []).append(value)
    block_values = [
        (mean, len(values))
        for _, values in sorted(buckets.items())
        if (mean := _mean_float(values)) is not None
    ]
    means = [value for value, _ in block_values]
    if len(block_values) < 2:
        interval: Tuple[Optional[float], Optional[float]] = (None, None)
    else:
        interval = bootstrap_block_mean_interval(
            block_values,
            seed=DEFAULT_SEED,
            n_resamples=DEFAULT_RESAMPLES,
            confidence=0.95,
        )
    return PrimaryEstimatorRow(
        label=label,
        n=sum(weight for _, weight in block_values),
        n_blocks=len(block_values),
        mean=_mean_float(means) or 0.0,
        interval_lower=interval[0],
        interval_upper=interval[1],
    )


def _primary_rows_by_region(signals: Sequence[EventStudySignal], block_lookup: TemporalBlockMap) -> List[PrimaryEstimatorRow]:
    buckets: Dict[str, List[EventStudySignal]] = {}
    for signal in signals:
        region = block_lookup._asset(signal).region
        buckets.setdefault(region, []).append(signal)
    return [_primary_expectancy_row(region, buckets[region], block_lookup) for region in sorted(buckets)]


def _primary_rows_by_asset(signals: Sequence[EventStudySignal], block_lookup: TemporalBlockMap) -> List[PrimaryEstimatorRow]:
    buckets: Dict[str, List[EventStudySignal]] = {}
    for signal in signals:
        buckets.setdefault(signal.observation.asset, []).append(signal)
    return [_primary_expectancy_row(symbol, buckets[symbol], block_lookup) for symbol in sorted(buckets)]


def _block_success_rates(signals: Sequence[EventStudySignal], block_lookup: TemporalBlockMap) -> List[Tuple[float, int]]:
    buckets: Dict[int, List[EventStudySignal]] = {}
    for signal in signals:
        block = block_lookup.block_for(signal)
        buckets.setdefault(block, []).append(signal)
    return [
        (_rate(_target_first(bucket), len(bucket)), len(bucket))
        for _, bucket in sorted(buckets.items())
    ]


def _block_mean_interval(block_rates: Sequence[Tuple[float, int]]) -> Tuple[float, float]:
    """Intervalo bootstrap P2.6 sobre medias por bloque completo."""

    return bootstrap_block_mean_interval(
        block_rates,
        seed=DEFAULT_SEED,
        n_resamples=DEFAULT_RESAMPLES,
        confidence=0.95,
    )


def _target_first(signals: Iterable[EventStudySignal]) -> int:
    """Cuenta solo éxitos observables y deja AMBIGUOUS fuera del numerador.

    El denominador conserva las señales ambiguas, por lo que la tasa usada por
    el gate es la cota inferior publicada por el event study. Es una decisión
    explícita y conservadora para capacidad, no una resolución intrabarra ni
    un colapso silencioso del intervalo lower/upper a un punto estimado.
    """

    return sum(1 for signal in signals if signal.managed.exit_status == "TARGET_FIRST")


def _rate(count: int, total: int) -> float:
    return count / total if total else 0.0


def _mean_float(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def _score_band(score: float) -> str:
    return score_band(score)


def _resolution_rank(value: str) -> int:
    return {
        RESOLUTION_HIGH: 0,
        RESOLUTION_MEDIUM: 1,
        RESOLUTION_LOW: 2,
        RESOLUTION_INSUFFICIENT: 3,
    }[value]


def _format_summary(summary: CapacitySummary) -> str:
    primary_width = "N/D" if summary.primary_interval_width is None else f"{summary.primary_interval_width:.3f}"
    return (
        f"  n={summary.nominal_n}; n_by_band={summary.n_by_band}; n_blocks={summary.n_blocks}; "
        f"block_length={summary.block_length}; primary_expectancy_R={summary.primary_expectancy_net_r:+.3f}; "
        f"primary_interval={_fmt_optional_interval(summary.primary_interval_lower, summary.primary_interval_upper)}; "
        f"primary_interval_width={primary_width}; "
        f"secondary_TARGET_FIRST_interval=[{summary.secondary_target_first_interval_lower:.3f}, "
        f"{summary.secondary_target_first_interval_upper:.3f}]; "
        f"block_n_min={summary.min_block_observations}; "
        f"block_n_mean={summary.mean_block_observations:.1f}; "
        f"EXIT_FINAL={summary.exit_final_rate:.3f}; AMBIGUOUS={summary.ambiguous_rate:.3f}; "
        f"resolution={summary.resolution}; conclusive={summary.conclusive}; reasons={list(summary.reasons)}"
    )


def _intervals_overlap(
    left: Tuple[Optional[float], Optional[float]],
    right: Tuple[Optional[float], Optional[float]],
) -> bool:
    if left[0] is None or left[1] is None or right[0] is None or right[1] is None:
        return True
    return left[0] <= right[1] and right[0] <= left[1]


def _format_primary_rows(rows: Sequence[PrimaryEstimatorRow]) -> str:
    lines = ["label                 n  bloques  media_R   IC95"]
    for row in rows:
        lines.append(
            f"{row.label:<18} {row.n:>6} {row.n_blocks:>8} {row.mean:>+8.3f}   "
            f"{_fmt_optional_interval(row.interval_lower, row.interval_upper)}"
        )
    return "\n".join(lines)


def _fmt_optional_interval(lower: Optional[float], upper: Optional[float]) -> str:
    if lower is None or upper is None:
        return "sin intervalo (<2 bloques)"
    return f"[{lower:.3f}, {upper:.3f}]"
