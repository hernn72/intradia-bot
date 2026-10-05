"""Camino ciego de captura y reconfirmación para T-024."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

import pandas as pd

from advisor.analysis.execution import ABOVE_MAX_ENTRY, DATA_NOT_EXECUTABLE, INVALID_STOP, INVALID_TARGET, RR_TOO_LOW
from advisor.analysis.levels import rr_at_least
from advisor.config import AdvisorConfig
from advisor.research.t024_comun import (
    C_E_FINAL,
    CUTOFF_CONSUMIDA,
    DEV_VINTAGE_ID,
    HORIZONTE,
    MIN_RR,
    Q_MIN,
    SLIP_BPS,
    W_MIN,
    WARMUP_BARS,
    ConteoCaptura,
    SenalT024,
    es_elegible_temporal,
    local_dates,
    semana_iso,
)
from advisor.research.vintage import VintageLoad, VintageViews

EXECUTABLE = "EXECUTABLE"
ASSET_LIST_SHA256 = "36355796a57e55a68ea16957b7edc6975360fb2085e7fd91841d20e2d7812f50"
CENSUS = Path("evidence/2026-10-03-T-022-p6-diseno/censo-p6.json")
T024_CAPTURA_IMPORTED_CALLABLES = (
    "advisor.analysis.benchmark.resolve_benchmark_symbol",
    "advisor.analysis.levels.rr_at_least",
    "advisor.analysis.snapshot.build_snapshot_series",
    "advisor.backtest.engine._signal",
    "advisor.context.point_in_time.analysis_timestamp_for_signal",
    "advisor.data.calendars.market_session",
    "advisor.data.freshness.mercado_para_simbolo",
    "advisor.data.sessions.market_for_symbol",
    "advisor.research.p4._context_resolver",
    "advisor.research.vintage.frozen_close",
)


class T024LookaheadError(RuntimeError):
    """La captura intentó leer información posterior a la apertura de entrada."""


@dataclass(frozen=True)
class BarraCiega:
    session: date
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class VistaCiega:
    """Vista que permite historia hasta `s_i` y solo la apertura de `e_i`."""

    def __init__(self, barras: Sequence[BarraCiega], senal: SenalT024) -> None:
        self._barras = tuple(barras)
        self._senal = senal
        self._e_index = senal.s_index + 1
        if self._e_index >= len(self._barras):
            raise ValueError(f"{senal.signal_id}: sin barra de entrada")
        if self._barras[self._e_index].session != senal.e_session:
            raise ValueError(f"{senal.signal_id}: e_session no coincide con s_index + 1")

    def signal_prices(self) -> tuple[BarraCiega, ...]:
        return self._barras[: self._senal.s_index + 1]

    def open_e(self) -> float:
        return self._barras[self._e_index].open

    def get(self, index: int, field: str) -> float:
        if index < 0 or index >= len(self._barras):
            raise IndexError(index)
        if index > self._e_index or (index == self._e_index and field != "open"):
            raise T024LookaheadError(f"{self._senal.signal_id}: acceso no ciego a {field}[{index}]")
        return float(getattr(self._barras[index], field))


@dataclass(frozen=True)
class ResultadoCaptura:
    conteos: Mapping[str, ConteoCaptura]
    exclusiones: Mapping[str, int]
    rotulo: str = ""


@dataclass(frozen=True)
class ResultadoEjecutabilidad:
    ejecutable: bool
    reason: str
    effective_open: float


def evaluar_ejecutabilidad(senal: SenalT024, apertura: float) -> ResultadoEjecutabilidad:
    """Comprobaciones previas al sizing de P6 sobre una única apertura bruta."""

    eff = apertura * (1.0 + SLIP_BPS / 10_000.0)
    reason = EXECUTABLE
    if not (math.isfinite(apertura) and apertura > 0):
        reason = DATA_NOT_EXECUTABLE
    elif senal.stop >= eff:
        reason = INVALID_STOP
    elif senal.target2 <= eff:
        reason = INVALID_TARGET
    elif eff > senal.entry_max and not math.isclose(eff, senal.entry_max, rel_tol=1e-9):
        reason = ABOVE_MAX_ENTRY
    elif not rr_at_least((senal.target2 - eff) / (eff - senal.stop), MIN_RR):
        reason = RR_TOO_LOW
    return ResultadoEjecutabilidad(reason == EXECUTABLE, reason, eff)


def contar_captura(
    senales: Iterable[SenalT024],
    aperturas: Mapping[str, float],
    *,
    c_e: date = C_E_FINAL,
    barras_actuales: Optional[Mapping[str, Sequence[BarraCiega]]] = None,
    barras_previas: Optional[Mapping[str, Sequence[BarraCiega]]] = None,
) -> dict[str, ConteoCaptura]:
    """Cuenta capacidad sin salidas ni no solapamiento."""

    total: Counter[str] = Counter()
    ejecutables: Counter[str] = Counter()
    rechazos: dict[str, Counter[str]] = defaultdict(Counter)
    pares: dict[str, set[tuple[str, tuple[int, int]]]] = defaultdict(set)
    semanas: dict[str, set[tuple[int, int]]] = defaultdict(set)
    for senal in senales:
        if not es_elegible_temporal(senal.s_session, senal.e_session, c_e):
            continue
        total[senal.policy] += 1
        resultado = evaluar_ejecutabilidad(senal, aperturas[senal.signal_id])
        if resultado.ejecutable:
            ejecutables[senal.policy] += 1
            week = semana_iso(senal.e_session)
            pares[senal.policy].add((senal.asset, week))
            semanas[senal.policy].add(week)
        else:
            rechazos[senal.policy][resultado.reason] += 1
    nuevas, revisadas = calidad_barras(barras_actuales or {}, barras_previas or {})
    policies = set(total) | set(ejecutables) | set(rechazos) | set(pares)
    return {
        policy: ConteoCaptura(
            policy=policy,
            senales_operar=total[policy],
            ejecutables=ejecutables[policy],
            rechazos=dict(sorted(rechazos[policy].items())),
            q_p=len(pares[policy]),
            w_p=len(semanas[policy]),
            barras_nuevas=nuevas,
            barras_revisadas=revisadas,
            cumple=len(pares[policy]) >= Q_MIN and len(semanas[policy]) >= W_MIN,
            exclusiones={},
        )
        for policy in sorted(policies)
    }


def calidad_barras(
    actuales: Mapping[str, Sequence[BarraCiega]], previas: Mapping[str, Sequence[BarraCiega]]
) -> tuple[int, int]:
    nuevas = 0
    revisadas = 0
    for symbol, rows in actuales.items():
        old = {row.session: row for row in previas.get(symbol, ())}
        for row in rows:
            before = old.get(row.session)
            if before is None:
                nuevas += 1
            elif (
                row.open != before.open
                or row.high != before.high
                or row.low != before.low
                or row.close != before.close
                or row.volume != before.volume
            ):
                revisadas += 1
    return nuevas, revisadas


def policy_config(config: AdvisorConfig, policy: str) -> AdvisorConfig:
    from advisor.research import p5

    cells = {"B2": p5.B2_CELL, "S2": p5.S2_CELL, "C0": p5.C0_CELL}
    cell = cells[policy]
    return config.model_copy(update={"levels": cell.levels_config(config.levels)})


def asset_list() -> list[str]:
    data = json.loads(CENSUS.read_text(encoding="utf-8"))
    symbols = sorted(row["asset"] for row in data["activos"])
    digest = hashlib.sha256("\n".join(symbols).encode("utf-8")).hexdigest()
    if digest != ASSET_LIST_SHA256:
        raise RuntimeError(f"asset_list_sha256 {digest} distinto del congelado")
    return symbols


def _truncate_frame_by_local_date(frame: pd.DataFrame, timezone: str, c_e: date) -> pd.DataFrame:
    sessions = local_dates(frame.index, timezone)
    mask = [session <= c_e for session in sessions]
    return frame.loc[mask].copy()


def truncar_vintage(vintage: VintageLoad, universe: Any, c_e: date) -> VintageLoad:
    by_symbol: dict[str, VintageViews] = {}
    for symbol, views in vintage.by_symbol.items():
        asset = universe.get(symbol)
        if asset is None:
            continue
        by_symbol[symbol] = VintageViews(
            raw=_truncate_frame_by_local_date(views.raw, asset.timezone, c_e),
            execution_prices=_truncate_frame_by_local_date(views.execution_prices, asset.timezone, c_e),
            signal_prices=_truncate_frame_by_local_date(views.signal_prices, asset.timezone, c_e),
            gap_for_catalyst=_truncate_frame_by_local_date(views.gap_for_catalyst, asset.timezone, c_e),
        )
    return replace(vintage, by_symbol=by_symbol)


def generar_senales_operar(
    *,
    config: Any,
    universe: Any,
    vintage: Any,
    policy: str,
    c_e: date,
    cutoff_desarrollo: date = CUTOFF_CONSUMIDA,
) -> tuple[list[SenalT024], dict[str, int]]:
    """Genera OPERAR point-in-time replicando el bucle de P6, sin token ni desenlaces.

    # T-024 §6: lectura literal de P6; el corte ficticio solo se expone para desarrollo.
    """

    from advisor.analysis.benchmark import resolve_benchmark_symbol
    from advisor.analysis.opportunity import ACCION_COMPRAR, RADAR_OPERAR
    from advisor.analysis.snapshot import build_snapshot_series
    from advisor.backtest.engine import _signal
    from advisor.context.point_in_time import PointInTimeContextResolver, analysis_timestamp_for_signal
    from advisor.data.calendars import market_session
    from advisor.data.freshness import mercado_para_simbolo
    from advisor.data.sessions import market_for_symbol
    from advisor.research.p4 import _context_resolver
    from advisor.research.vintage import frozen_close

    cfg = policy_config(config, policy)
    resolver: PointInTimeContextResolver = _context_resolver(config, universe, vintage)
    window_cfg = config.horizonte(HORIZONTE)
    settlement = config.data_quality.settlement_minutes
    out: list[SenalT024] = []
    counts: Counter[str] = Counter()
    for symbol in asset_list():
        loaded = vintage.by_symbol.get(symbol)
        if loaded is None:
            counts["excluida_sin_simbolo_en_cosecha"] += 1
            continue
        asset = universe.get(symbol)
        if asset is None:
            continue
        signal_df = loaded.signal_prices
        market = mercado_para_simbolo(asset, symbol)
        sessions = local_dates(signal_df.index, asset.timezone)
        benchmark_symbol = resolve_benchmark_symbol(asset, config.report)
        benchmark_close = frozen_close(vintage, benchmark_symbol) if benchmark_symbol else None
        series = build_snapshot_series(
            signal_df,
            cfg.indicators,
            cfg.levels,
            window_cfg.interval,
            benchmark_close,
            asset_timezone=market_session(market).timezone,
            benchmark_timezone=market_session(market_for_symbol(benchmark_symbol)).timezone if benchmark_symbol else None,
        )
        contexts = resolver.contexts_for_index(signal_df.index, signal_market=market)
        for j in range(WARMUP_BARS, len(signal_df) - 1):
            s_session = sessions[j]
            e_session = sessions[j + 1]
            if not (s_session > cutoff_desarrollo and e_session <= c_e):
                continue
            ts = analysis_timestamp_for_signal(market, s_session, e_session, settlement_minutes=settlement)
            if ts is None:
                counts["excluida_sin_analysis_timestamp"] += 1
                continue
            resolved = contexts[j]
            if resolved is None or not resolved.calculable:
                reason = ",".join(resolved.exclusions) if resolved is not None and resolved.exclusions else "NO_CALCULABLE_CONTEXT_HISTORY"
                counts["excluida_" + reason] += 1
                continue
            context = resolved.context
            if context is None or context.source != "point_in_time":
                raise RuntimeError(f"{symbol}: contexto {getattr(context, 'source', None)} en T-024 (solo point_in_time)")
            context_at: list[Any] = [None] * len(signal_df)
            context_at[j] = context
            found = _signal(asset, series, j, cfg, HORIZONTE, WARMUP_BARS, None, None, None, context_at, "1.0")
            if found is None:
                counts["sin_niveles"] += 1
                continue
            if not (found["setup_radar"] == RADAR_OPERAR and found["setup_accion"] == ACCION_COMPRAR):
                counts["no_operar"] += 1
                continue
            levels = found["levels"]
            signal_id = found["observation"].signal_id
            counts["senales"] += 1
            out.append(
                SenalT024(
                    signal_id=signal_id,
                    policy=policy,
                    asset=symbol,
                    s_index=j,
                    s_session=s_session,
                    e_session=e_session,
                    analysis_ts=ts,
                    stop=levels.stop,
                    target2=levels.target2,
                    entry_max=levels.entry_max,
                )
            )
    return out, dict(sorted(counts.items()))


def _barras_ciegas(vintage: VintageLoad, symbol: str, timezone: str, c_e: date) -> tuple[BarraCiega, ...]:
    views = vintage.by_symbol[symbol]
    sessions = local_dates(views.execution_prices.index, timezone)
    rows = []
    for session, (_, row) in zip(sessions, views.execution_prices.iterrows()):
        if session <= c_e:
            rows.append(
                BarraCiega(
                    session=session,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row.get("Volume", 0.0)),
                )
            )
    return tuple(rows)


def capturar(
    config: AdvisorConfig,
    universe: Any,
    vintage: VintageLoad,
    *,
    c_e: date,
    cutoff: date = CUTOFF_CONSUMIDA,
    desarrollo: bool = False,
    previa: Optional[VintageLoad] = None,
) -> ResultadoCaptura:
    """Ruta pública ciega: señales, apertura por VistaCiega y conteos."""

    if desarrollo:
        rotulo = "DESARROLLO — no decide"
    else:
        if cutoff != CUTOFF_CONSUMIDA:
            raise ValueError("T-024: cutoff ficticio solo permitido con desarrollo=True")
        if vintage.data_vintage_id == DEV_VINTAGE_ID:
            raise ValueError("T-024: la cosecha consumida solo puede usarse en modo DESARROLLO")
        rotulo = ""
    truncated = truncar_vintage(vintage, universe, c_e)
    all_signals: list[SenalT024] = []
    exclusions: Counter[str] = Counter()
    for policy in ("B2", "S2", "C0"):
        signals, counts = generar_senales_operar(config=config, universe=universe, vintage=truncated, policy=policy, c_e=c_e, cutoff_desarrollo=cutoff)
        all_signals.extend(signals)
        exclusions.update({f"{policy}:{key}": value for key, value in counts.items() if key != "senales"})
    aperturas: dict[str, float] = {}
    actuales: dict[str, tuple[BarraCiega, ...]] = {}
    previas: dict[str, tuple[BarraCiega, ...]] = {}
    for signal in all_signals:
        asset = universe.get(signal.asset)
        rows = actuales.setdefault(signal.asset, _barras_ciegas(truncated, signal.asset, asset.timezone, c_e))
        aperturas[signal.signal_id] = VistaCiega(rows, signal).open_e()
    if previa is not None:
        prev_truncated = truncar_vintage(previa, universe, c_e)
        for symbol in actuales:
            asset = universe.get(symbol)
            previas[symbol] = _barras_ciegas(prev_truncated, symbol, asset.timezone, c_e)
    conteos = contar_captura(all_signals, aperturas, c_e=c_e, barras_actuales=actuales, barras_previas=previas)
    conteos = {policy: replace(conteo, exclusiones=dict(sorted(exclusions.items()))) for policy, conteo in conteos.items()}
    return ResultadoCaptura(conteos=conteos, exclusiones=dict(sorted(exclusions.items())), rotulo=rotulo)


def reconfirmar_capacidad(
    config: AdvisorConfig,
    universe: Any,
    vintage: VintageLoad,
    *,
    c_e: date,
) -> Mapping[str, ConteoCaptura]:
    return capturar(config, universe, vintage, c_e=c_e, desarrollo=False).conteos


def verificar_invariante_prefijo(
    senal: SenalT024,
    barras: Sequence[BarraCiega],
    envenenar: Callable[[Sequence[BarraCiega]], Sequence[BarraCiega]],
) -> bool:
    vista = VistaCiega(barras, senal)
    poisoned = VistaCiega(envenenar(barras), senal)
    return (
        vista.signal_prices() == poisoned.signal_prices()
        and evaluar_ejecutabilidad(senal, vista.open_e()) == evaluar_ejecutabilidad(senal, poisoned.open_e())
    )
