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
from typing import Callable, Dict, Iterable, List, Sequence, Tuple
from zoneinfo import ZoneInfo

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

MARKET_TIMEZONES = {
    "AMS": "Europe/Amsterdam",
    "CPH": "Europe/Copenhagen",
    "CRYPTO": "UTC",
    "HKG": "Asia/Hong_Kong",
    "JPX": "Asia/Tokyo",
    "KSC": "Asia/Seoul",
    "MCE": "Europe/Madrid",
    "MIL": "Europe/Rome",
    "NASDAQ": "America/New_York",
    "NYSE": "America/New_York",
    "PAR": "Europe/Paris",
    "XETRA": "Europe/Berlin",
}


@dataclass(frozen=True)
class CapacitySummary:
    """Materia prima y veredicto de capacidad de una población."""

    label: str
    nominal_n: int
    n_by_band: Dict[str, int]
    n_blocks: int
    block_length: int
    interval_lower: float
    interval_upper: float
    interval_width: float
    min_block_observations: int
    mean_block_observations: float
    exit_final_rate: float
    ambiguous_rate: float
    resolution: str
    conclusive: bool
    verdict: str
    reasons: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CapacityComparison:
    """Capacidad de una comparación concreta entre bandas."""

    label: str
    left: CapacitySummary
    right: CapacitySummary
    interval_left: Tuple[float, float]
    interval_right: Tuple[float, float]
    interval_width: float
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
        band_of=band_of,
    )
    band_summaries = [
        _summary(
            label,
            [signal for signal in result.signals if band_of(signal) == label],
            block_length=block_length,
            block_lookup=block_lookup,
            thresholds=thresholds,
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
    )


def format_capacity_report(report: CapacityReport) -> str:
    """Informe textual del gate: veredicto y materia prima inseparables."""

    lines = [
        report.horizonte,
        f"Capacidad global: {report.global_summary.verdict}",
        _format_summary(report.global_summary),
        "",
        "Bandas de score:",
    ]
    for summary in report.bands:
        lines.append(f"Score {summary.label}: {summary.verdict}")
        lines.append(_format_summary(summary))
    if report.comparisons:
        lines.append("")
        lines.append("Comparaciones:")
        for comparison in report.comparisons:
            lines.append(f"{comparison.label}: {comparison.verdict}")
            lines.append(
                "  intervalos="
                f"{_fmt_interval(comparison.interval_left)} vs {_fmt_interval(comparison.interval_right)}; "
                f"anchura_max={comparison.interval_width:.3f}; resolution={comparison.resolution}; "
                f"conclusive={comparison.conclusive}; reasons={list(comparison.reasons)}"
            )
    if any(summary.label == "80+" and not summary.conclusive for summary in report.bands):
        lines.append("")
        lines.append("Conclusión: no se permite calibrar un threshold apoyándose en 80+.")
    return "\n".join(lines)


def _summary(
    label: str,
    signals: Sequence[EventStudySignal],
    *,
    block_length: int,
    block_lookup: TemporalBlockMap,
    thresholds: CapacityThresholds,
    band_of: Callable[[EventStudySignal], str] = band_of_full_score,
) -> CapacitySummary:
    nominal_n = len(signals)
    n_by_band = {band: 0 for band, _, _ in SCORE_BANDS}
    for signal in signals:
        n_by_band[band_of(signal)] += 1

    n_blocks = _temporal_blocks(signals, block_lookup)
    block_rates = _block_success_rates(signals, block_lookup)
    interval = _block_mean_interval(block_rates)
    interval_width = interval[1] - interval[0]
    block_sizes = [total for _, total in block_rates]
    min_block_observations = min(block_sizes) if block_sizes else 0
    mean_block_observations = sum(block_sizes) / len(block_sizes) if block_sizes else 0.0
    exit_final_rate = _rate(sum(1 for signal in signals if signal.managed.exit_status == FINAL_EXIT), nominal_n)
    ambiguous_rate = _rate(sum(1 for signal in signals if signal.managed.exit_status == AMBIGUOUS), nominal_n)
    resolution, verdict, conclusive, reasons = _classify_capacity(
        nominal_n=nominal_n,
        n_blocks=n_blocks,
        interval_width=interval_width,
        exit_final_rate=exit_final_rate,
        ambiguous_rate=ambiguous_rate,
        thresholds=thresholds,
        min_block_observations=min_block_observations,
    )
    return CapacitySummary(
        label=label,
        nominal_n=nominal_n,
        n_by_band=n_by_band,
        n_blocks=n_blocks,
        block_length=block_length,
        interval_lower=interval[0],
        interval_upper=interval[1],
        interval_width=interval_width,
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
    interval_left = (left.interval_lower, left.interval_upper)
    interval_right = (right.interval_lower, right.interval_upper)
    overlap = interval_left[0] <= interval_right[1] and interval_right[0] <= interval_left[1]
    interval_width = max(left.interval_width, right.interval_width)
    reasons: List[str] = []
    if not left.conclusive:
        reasons.append(f"{left.label} no concluyente")
    if not right.conclusive:
        reasons.append(f"{right.label} no concluyente")
    if overlap:
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


def _classify_capacity(
    *,
    nominal_n: int,
    n_blocks: int,
    interval_width: float,
    exit_final_rate: float,
    ambiguous_rate: float,
    thresholds: CapacityThresholds,
    min_block_observations: int,
) -> Tuple[str, str, bool, List[str]]:
    reasons: List[str] = []
    if nominal_n == 0:
        return RESOLUTION_INSUFFICIENT, INSUFICIENTE, False, ["sin observaciones"]
    if exit_final_rate > thresholds.max_exit_final_rate:
        reasons.append(f"censura EXIT_FINAL {exit_final_rate:.1%} > {thresholds.max_exit_final_rate:.1%}")
    if ambiguous_rate > thresholds.max_ambiguous_rate:
        reasons.append(f"ambigüedad {ambiguous_rate:.1%} > {thresholds.max_ambiguous_rate:.1%}")
    if min_block_observations < thresholds.min_observations_per_block:
        reasons.append(
            f"bloque mínimo {min_block_observations} < {thresholds.min_observations_per_block} observaciones"
        )

    if (
        n_blocks >= thresholds.sufficient_blocks
        and nominal_n >= thresholds.sufficient_n
        and interval_width <= thresholds.sufficient_interval_width
        and not reasons
    ):
        return RESOLUTION_HIGH, SUFICIENTE, True, []
    if (
        n_blocks >= thresholds.limited_blocks
        and nominal_n >= thresholds.limited_n
        and interval_width <= thresholds.limited_interval_width
    ):
        return RESOLUTION_MEDIUM, LIMITADA, not reasons, reasons

    if n_blocks < thresholds.limited_blocks:
        reasons.append(f"bloques {n_blocks} < {thresholds.limited_blocks}")
    if nominal_n < thresholds.limited_n:
        reasons.append(f"n {nominal_n} < {thresholds.limited_n}")
    if interval_width > thresholds.limited_interval_width:
        reasons.append(f"intervalo {interval_width:.3f} > {thresholds.limited_interval_width:.3f}")
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


def _market_zone(asset: Asset) -> ZoneInfo:
    market = asset.primary_market
    try:
        timezone_name = MARKET_TIMEZONES[market]
    except KeyError:
        raise ValueError(f"{asset.symbol}: plaza '{market}' sin zona horaria en MARKET_TIMEZONES") from None
    return ZoneInfo(timezone_name)


def _temporal_blocks(signals: Sequence[EventStudySignal], block_lookup: TemporalBlockMap) -> int:
    return len({block_lookup.block_for(signal) for signal in signals})


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
    return (
        f"  n={summary.nominal_n}; n_by_band={summary.n_by_band}; n_blocks={summary.n_blocks}; "
        f"block_length={summary.block_length}; interval=[{summary.interval_lower:.3f}, {summary.interval_upper:.3f}]; "
        f"interval_width={summary.interval_width:.3f}; block_n_min={summary.min_block_observations}; "
        f"block_n_mean={summary.mean_block_observations:.1f}; "
        f"EXIT_FINAL={summary.exit_final_rate:.3f}; AMBIGUOUS={summary.ambiguous_rate:.3f}; "
        f"resolution={summary.resolution}; conclusive={summary.conclusive}; reasons={list(summary.reasons)}"
    )


def _fmt_interval(interval: Tuple[float, float]) -> str:
    return f"[{interval[0]:.3f}, {interval[1]:.3f}]"
