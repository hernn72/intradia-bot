"""Ejecutor único de P4 (T-020 / A-04): geometría de stop, objetivo y entrada.

Implementa literalmente el pre-registro `48b8847` (ficha T-020 y D-63). Nada de
lo que sigue es un parámetro: población, rejilla, bloques, semilla,
remuestreos, familia confirmatoria, coste, estratos y criterio están fijados
aquí o en los instrumentos P2.5/P2.6 que se reutilizan sin cambios.

Dos fases, separadas por una frontera que no se cruza dos veces:

- ``preflight``: reproduce la población, los hashes, los bloques, el álgebra,
  los niveles de cada geometría, la holgura D-06 a ``open(t+1)``, los estratos y
  el recuento estructural de comparaciones **sin abrir ningún desenlace**: la
  enumeración no llama a los evaluadores del event study. Se puede repetir.
- ``confirmatoria``: una sola ejecución sobre un árbol limpio y el preflight
  definitivo. Deja una marca antes de abrir desenlaces y se niega a arrancar si
  la marca o una salida previa ya existen.

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y
selección no corregido)._
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, cast

import pandas as pd

import advisor.research.event_study as event_study
from advisor.analysis.execution import ABOVE_MAX_ENTRY, EXECUTABLE, INVALID_STOP, INVALID_TARGET, RR_TOO_LOW
from advisor.analysis.levels import _SUPPORT_BUFFER_ATR, Levels, compute_levels_from_inputs, reward_risk, rr_at_least
from advisor.analysis.overview import context_assets_of
from advisor.config import AdvisorConfig, LevelsConfig
from advisor.context.point_in_time import PointInTimeContextResolver, analysis_timestamp_for_signal
from advisor.data.freshness import mercado_para_simbolo
from advisor.data.sessions import session_date_of
from advisor.research.bootstrap import (
    BlockBootstrapResult,
    PairedDelta,
    bootstrap_block_delta,
    bootstrap_block_mean_interval,
)
from advisor.research.capacity import DEFAULT_THRESHOLDS, CapacityThresholds, TemporalBlockMap, _temporal_block_lookup
from advisor.research.event_study import (
    AMBIGUOUS,
    FINAL_EXIT,
    STOP_FIRST,
    TARGET_FIRST,
    TIME_EXIT,
    EventStudyResult,
    EventStudySignal,
    ManagedEvent,
    PotentialEvent,
)
from advisor.research.observations import SignalObservation
from advisor.research.p3 import _finite, _json_default, nearest_rank_cut, utc_now, write_json
from advisor.research.uncertainty import pair_populations
from advisor.research.vintage import VintageLoad, frozen_close
from advisor.run.git import git_dirty, git_sha, run_git
from advisor.run.manifest import config_hash
from advisor.universe.models import Universe

# ---------------------------------------------------------------------------
# Identidad del pre-registro (T-020, D-63). No son parámetros.
# ---------------------------------------------------------------------------

P4_PREREG_SHA = "48b884722ef027e99857a4e65f9ab6b11da4758f"
DATA_VINTAGE_ID = "071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841"
UNIVERSE_VINTAGE_ID = "237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19"
P4_POPULATION_SHA256 = "78024050f7081ad4e1dd5cefaefbfa1a1668ff5b1a2ced8c34e62b6501873141"
P4_SIGNAL_IDS_SHA256 = "9faa4a45beaba3eb8dafabf7990906cd8c89e8e06ae2f25edec7839cd48e629f"
COST_PCT = 0.2
SEED = 20260830
STANDARD_RESAMPLES = 2000
STANDARD_CONFIDENCE = 0.95
BONFERRONI_M = 4
BONFERRONI_CONFIDENCE = 0.9875
BONFERRONI_RESAMPLES = 20_000

UNIVERSE_LABEL = "condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)"
B1_LABEL = "previamente expuesta en esta misma cosecha; no confirmatoria; no elegible para sustituir C0"
HALVES_LABEL = "robustez temporal interna sobre datos de desarrollo"
E1_LABEL = "E1: entrada a open(t+1) con veto de producción frente a entrada al cierre, bajo C0; no es geometría ni candidata a P5"

HORIZONTE = "swing"
MAX_HOLD_BARS = 40
# A-02 enumeró con el selector de v1: el modo de contexto solo cambia el score,
# que P4 no lee; con él ninguna señal se descarta por contexto (ficha §8).
ENUMERATION_SCORE_MODEL = "1.0"
ACTIVE_SCORE_MODEL_VERSION = "1.0"
# `config_hash` de `config.yaml` vigente (el mismo que fijó P3): la geometría C0
# sale de aquí, así que un `--config` distinto no puede pasar el preflight.
EXPECTED_CONFIG_HASH = "89406d28c7b4b6e6c4f032cd63b6868c927af3e926dfb52d430dfa6654d06387"

# Censo congelado sin desenlaces (evidence/2026-10-01-T-020-censo-p4/).
EXPECTED_A02 = 106_363
EXPECTED_CRYPTO = 5_112
EXPECTED_P4 = 101_251
EXPECTED_ASSETS = 90
EXPECTED_CRYPTO_ASSETS = ("BTC-EUR", "ETH-EUR", "SOL-EUR")
EXPECTED_REGIONS = {"ASIA": 17_953, "EMERGING_MARKETS": 1_151, "EUROPA": 34_622, "GLOBAL": 2_627, "USA": 44_898}
NO_CALCULABLE_CONTEXT = "NO_CALCULABLE_CONTEXT"
CALCULABLE_REGIMES = ("RISK_ON", "CAUTELA", "RISK_OFF")
EXPECTED_REGIMES = {"CAUTELA": 12_431, NO_CALCULABLE_CONTEXT: 7_157, "RISK_OFF": 7_944, "RISK_ON": 73_719}
EXPECTED_SPINE_SESSIONS = 1_302

BLOCK_LENGTHS = (40, 60, 80, 120)
PRIMARY_BLOCK_LENGTH = 60
SENSITIVITY_BLOCK_LENGTH = 120
INVALID_BLOCK_LENGTHS = (40, 80)
# longitud → (bloques ocupados, bloque ocupado más corto en sesiones)
EXPECTED_BLOCKS = {40: (30, 22), 60: (20, 42), 80: (16, 22), 120: (10, 102)}
FIRST_HALF_BLOCKS = tuple(range(2, 12))
SECOND_HALF_BLOCKS = tuple(range(12, 22))
MIN_PAIR_FRACTION = 0.90
AMBIGUITY_BOUNDS = ("conservadora", "favorable")
TERCILE_LABELS = ("T1", "T2", "T3")
DISTRIBUTION_PERCENTILES = (10, 25, 50, 75, 90)
ISCLOSE_REL_TOL = 1e-9

# Recuento esperado del pre-registro (sección 20): el ejecutor lo deriva de sus
# propias salidas previstas y se para si no coincide; nunca lo usa en su lugar.
EXPECTED_COMPARISONS = 447
EXPECTED_CONFIRMATORY = 4

PREFLIGHT_DIR = Path("evidence/2026-10-01-T-020-p4/preflight")
CONFIRMATORY_OUTPUT_DIR = Path("evidence/2026-10-01-T-020-p4/run")
RUN_MARKER = "EJECUCION_CONFIRMATORIA_P4_INICIADA"
# Modo explícito para iterar antes del commit del ejecutor: calcula e imprime el
# preflight con el árbol sucio, pero no escribe evidencia ni cuenta como definitivo.
DEVELOPMENT_ENV = "INTRADIA_P4_PREFLIGHT_DESARROLLO"
# Lo que decide los desenlaces: entre el ejecutor del preflight definitivo y el
# HEAD de la ejecución confirmatoria no puede cambiar nada de esto.
EXECUTOR_PATHS = ("advisor", "config.yaml", "universe.yaml", "exchange_overrides.yaml", "pyproject.toml", "requirements.txt")


class P4PreflightError(RuntimeError):
    """Una identidad del pre-registro no se reproduce: P4 no se ejecuta."""


class P4AlreadyExecutedError(RuntimeError):
    """La ejecución confirmatoria ya se inició una vez: no se repite."""


# ---------------------------------------------------------------------------
# Rejilla (D-63). Objetos de investigación, no configuración de producción.
# ---------------------------------------------------------------------------

ROLE_CONTROL = "CONTROL"
ROLE_DESCRIPTIVE = "DESCRIPTIVA"
ROLE_CANDIDATE = "CANDIDATA"


@dataclass(frozen=True)
class Geometry:
    gid: str
    atr_stop_multiple: float
    target_atr_multiples: Tuple[float, float, float]
    role: str
    confirmatory: bool
    eligible_for_p5: bool
    bonferroni: bool
    label: Optional[str] = None
    target2_structural: bool = False
    entry_max_atr: float = 0.75
    min_rr: float = 1.5

    def levels_config(self, base: LevelsConfig) -> LevelsConfig:
        """La configuración de niveles de producción con solo la geometría cambiada."""

        return LevelsConfig(
            **{
                **base.model_dump(),
                "atr_stop_multiple": self.atr_stop_multiple,
                "target_atr_multiples": list(self.target_atr_multiples),
                "target2_structural": self.target2_structural,
                "entry_max_atr": self.entry_max_atr,
            }
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.gid,
            "atr_stop_multiple": self.atr_stop_multiple,
            "target_atr_multiples": list(self.target_atr_multiples),
            "target2_structural": self.target2_structural,
            "entry_max_atr": self.entry_max_atr,
            "min_rr": self.min_rr,
            "regla_soporte": "E (el soporte nunca aleja el stop)",
            "rol": self.role,
            "confirmatory": self.confirmatory,
            "eligible_for_p5": self.eligible_for_p5,
            "bonferroni": self.bonferroni,
            "etiqueta": self.label,
        }


C0 = Geometry("C0", 2.0, (1.5, 3.0, 5.0), ROLE_CONTROL, confirmatory=False, eligible_for_p5=False, bonferroni=False)
B1 = Geometry(
    "B1", 2.0, (1.5, 3.5, 5.0), ROLE_DESCRIPTIVE, confirmatory=False, eligible_for_p5=False, bonferroni=False, label=B1_LABEL
)
B2 = Geometry("B2", 2.0, (1.5, 4.875, 5.0), ROLE_CANDIDATE, confirmatory=True, eligible_for_p5=True, bonferroni=True)
S1 = Geometry("S1", 1.5, (1.5, 2.25, 5.0), ROLE_CANDIDATE, confirmatory=True, eligible_for_p5=True, bonferroni=True)
S2 = Geometry("S2", 2.5, (1.5, 3.75, 5.0), ROLE_CANDIDATE, confirmatory=True, eligible_for_p5=True, bonferroni=True)
GEOMETRIES: Tuple[Geometry, ...] = (C0, B1, B2, S1, S2)
VARIANTS: Tuple[Geometry, ...] = (B1, B2, S1, S2)
GEOMETRY_BY_ID: Dict[str, Geometry] = {g.gid: g for g in GEOMETRIES}
CANDIDATE_IDS: Tuple[str, ...] = ("B2", "S1", "S2")
STOP_BASIS_GEOMETRIES: Tuple[str, ...] = ("S1", "S2")
E1_ID = "E1"
CONFIRMATORY_FAMILY: Tuple[str, ...] = ("B2_vs_C0", "S1_vs_C0", "S2_vs_C0", "E1")

BASIS_VOLATILITY = "VOLATILIDAD"
BASIS_SUPPORT = "SOPORTE"
STOP_BASIS_PAIRS = ("VOL/VOL", "SOP/SOP", "MIXTO")
BINDING_RR = "RR"
BINDING_TECHNICAL = "TECNICO"
BINDING_TIE = "EMPATE"
OPEN_CATEGORIES = (INVALID_STOP, INVALID_TARGET, ABOVE_MAX_ENTRY, RR_TOO_LOW, EXECUTABLE)
NOT_EXECUTED_PREFIX = "NO_EJECUTADA_"


def comparison_id(gid: str) -> str:
    return E1_ID if gid == E1_ID else f"{gid}_vs_C0"


# ---------------------------------------------------------------------------
# Álgebra de la holgura (§6) y niveles efectivos (§22, condición 6).
# ---------------------------------------------------------------------------


def algebra(geometry: Geometry) -> Dict[str, float]:
    """RR en P y holguras con stop por volatilidad, en ATR (fórmulas de §6)."""

    s = geometry.atr_stop_multiple
    m2 = geometry.target_atr_multiples[1]
    slack_rr = (m2 - geometry.min_rr * s) / (1 + geometry.min_rr)
    return {
        "rr_en_p": m2 / s,
        "holgura_rr_atr": slack_rr,
        "holgura_efectiva_atr": min(geometry.entry_max_atr, slack_rr),
    }


def synthetic_algebra(geometry: Geometry, base: LevelsConfig, price: float = 100.0, atr: float = 2.0) -> Dict[str, float]:
    """Las mismas magnitudes medidas con `compute_levels_from_inputs` (P=100, A=2, sin soporte)."""

    levels = compute_levels_from_inputs(
        price=price,
        atr=atr,
        low_lookback=None,
        high_lookback=None,
        ema_fast=None,
        config=geometry.levels_config(base),
        min_rr_ratio=geometry.min_rr,
    )
    if levels is None or levels.entry_max_rr is None:
        raise P4PreflightError(f"{geometry.gid}: sin niveles con primitivas sintéticas")
    return {
        "rr_en_p": levels.rr_ratio,
        "holgura_rr_atr": (levels.entry_max_rr - price) / atr,
        "holgura_efectiva_atr": (levels.entry_max - price) / atr,
    }


def geometry_levels(observation: SignalObservation, geometry: Geometry, base: LevelsConfig) -> Optional[Levels]:
    """Los niveles de la geometría desde las primitivas en t, como `replay_managed_population`."""

    return _levels_with(observation, geometry.levels_config(base), geometry.min_rr)


def _levels_with(observation: SignalObservation, config: LevelsConfig, min_rr: float) -> Optional[Levels]:
    return compute_levels_from_inputs(
        price=observation.price,
        atr=observation.atr,
        low_lookback=observation.low_lookback,
        high_lookback=observation.high_lookback,
        ema_fast=observation.ema_fast,
        config=config,
        min_rr_ratio=min_rr,
    )


def levels_none_reason(observation: SignalObservation, geometry: Geometry) -> str:
    """Motivo, solo con primitivas, por el que `compute_levels_from_inputs` devolvió None."""

    atr = observation.atr
    price = observation.price
    if atr is None or atr <= 0:
        return "SIN_ATR"
    volatility_stop = price - geometry.atr_stop_multiple * atr
    stop = volatility_stop
    support = observation.low_lookback
    if support is not None and volatility_stop < support < price:
        support_stop = support - _SUPPORT_BUFFER_ATR * atr
        if support_stop > volatility_stop:
            stop = support_stop
    if stop <= 0 or stop >= price:
        return "STOP_FUERA_DE_RANGO"
    return "RR_EN_ENTRY_MAX"


def stop_basis_of(levels: Levels) -> str:
    return BASIS_SUPPORT if levels.stop_basis.startswith("soporte") else BASIS_VOLATILITY


def stop_basis_pair(control: Levels, variant: Levels) -> str:
    pair = (stop_basis_of(control), stop_basis_of(variant))
    if pair == (BASIS_VOLATILITY, BASIS_VOLATILITY):
        return "VOL/VOL"
    if pair == (BASIS_SUPPORT, BASIS_SUPPORT):
        return "SOP/SOP"
    return "MIXTO"


def coherence_violations(levels: Levels, min_rr: float) -> List[str]:
    """Condición 6 sobre niveles efectivos: RR en P, orden de objetivos y stop < P ≤ entry_max."""

    violations: List[str] = []
    if not rr_at_least(levels.rr_ratio, min_rr):
        violations.append("RR_EN_P_BAJO_MIN_RR")
    if not levels.target1 <= levels.target2:
        violations.append("TARGET1_SOBRE_TARGET2")
    if not levels.target2 < levels.target3:
        violations.append("TARGET2_NO_BAJO_TARGET3")
    if not levels.stop < levels.price:
        violations.append("STOP_NO_BAJO_P")
    if not (levels.price <= levels.entry_max or math.isclose(levels.price, levels.entry_max, rel_tol=ISCLOSE_REL_TOL)):
        violations.append("P_SOBRE_ENTRY_MAX")
    return violations


def binding_limit(levels: Levels) -> str:
    """Qué límite fija `entry_max`; el empate se declara con `isclose` (B2 lo roza por construcción)."""

    technical = levels.entry_max_tecnica
    rr_limit = levels.entry_max_rr
    if technical is None or rr_limit is None:
        raise ValueError("niveles sin entry_max_tecnica / entry_max_rr")
    if math.isclose(technical, rr_limit, rel_tol=ISCLOSE_REL_TOL):
        return BINDING_TIE
    return BINDING_RR if rr_limit < technical else BINDING_TECHNICAL


def classify_open_entry(levels: Levels, entry_price: float, min_rr: float) -> str:
    """Categoría a un precio de entrada en el orden y la tolerancia de `evaluate_trade_at_entry`.

    Sin sizing, broker ni calidad del dato: el laboratorio no dimensiona posiciones
    ni tiene esos estados por barra (ficha §18.1, paso 3).
    """

    risk_pct = (entry_price - levels.stop) / entry_price * 100 if entry_price > 0 else 0.0
    if levels.stop >= entry_price or risk_pct <= 0:
        return INVALID_STOP
    if levels.target2 <= entry_price:
        return INVALID_TARGET
    if entry_price > levels.entry_max and not math.isclose(entry_price, levels.entry_max, rel_tol=ISCLOSE_REL_TOL):
        return ABOVE_MAX_ENTRY
    rr = reward_risk(entry_price, levels.target2, levels.stop)
    if rr is None or not rr_at_least(rr, min_rr):
        return RR_TOO_LOW
    return EXECUTABLE


# ---------------------------------------------------------------------------
# Población P4: A-02 swing sin cripto, sin desenlaces (§8, D-63 punto 2).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ObservationOnly:
    observation: SignalObservation


def _as_block_signal(observation: SignalObservation) -> EventStudySignal:
    # `TemporalBlockMap` solo lee `.observation` de la señal: no hace falta ningún
    # desenlace para situarla en la espina de sesiones.
    return cast(EventStudySignal, _ObservationOnly(observation))


@dataclass(frozen=True)
class P4Signal:
    """Una señal de P4 con lo que se sabe en t (y la apertura de t+1)."""

    observation: SignalObservation
    region: str
    plaza_session: date
    spine_session: date
    blocks: Mapping[int, int]
    regime: str
    next_open: float

    @property
    def signal_id(self) -> str:
        return self.observation.signal_id

    @property
    def asset(self) -> str:
        return self.observation.asset

    @property
    def atr_ratio(self) -> float:
        atr = self.observation.atr
        if atr is None:
            raise ValueError(f"{self.signal_id}: señal sin ATR")
        return atr / self.observation.price


@dataclass
class P4Population:
    signals: List[P4Signal]
    meta: EventStudyResult
    lookups: Dict[int, TemporalBlockMap]
    a02: int
    crypto_excluded: int
    crypto_assets: Tuple[str, ...]
    population_sha256: str
    signal_ids_sha256: str
    regions: Dict[str, int]
    regimes: Dict[str, int]
    no_calculable_codes: Dict[str, int]
    blocks: Dict[int, Dict[str, Any]]
    enumerated_levels: Dict[str, Levels]
    checks: List[Tuple[str, Any, Any, bool]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(passed for *_, passed in self.checks)

    @property
    def spine(self) -> Tuple[date, ...]:
        return self.lookups[PRIMARY_BLOCK_LENGTH].session_spine


def build_population(config: AdvisorConfig, universe: Universe, vintage: VintageLoad) -> P4Population:
    """Enumera la población sin llamar a ningún evaluador de desenlace."""

    meta_all, enumerated = event_study.enumerate_event_signals_on_vintage(
        config,
        universe,
        vintage,
        horizonte=HORIZONTE,
        cost_pct=COST_PCT,
        score_model_version=ENUMERATION_SCORE_MODEL,
    )
    crypto = {symbol for symbol in meta_all.evaluated_assets if _asset(universe, symbol).asset_class == "crypto"}
    kept = [item for item in enumerated if item.observation.asset not in crypto]
    meta = EventStudyResult(
        data_vintage_id=meta_all.data_vintage_id,
        horizonte=meta_all.horizonte,
        cost_pct=meta_all.cost_pct,
        warmup_bars=meta_all.warmup_bars,
        max_hold_bars=meta_all.max_hold_bars,
        universe_vintage_id=meta_all.universe_vintage_id,
        population_name="P4_A02_sin_cripto",
        signals=[],
        evaluated_assets=[symbol for symbol in meta_all.evaluated_assets if symbol not in crypto],
        asset_bar_counts={k: v for k, v in meta_all.asset_bar_counts.items() if k not in crypto},
        session_dates_by_asset={k: v for k, v in meta_all.session_dates_by_asset.items() if k not in crypto},
        skipped=list(meta_all.skipped),
    )
    lookups = {length: _temporal_block_lookup(meta, length, universe) for length in BLOCK_LENGTHS}
    resolver = _context_resolver(config, universe, vintage)

    signals: List[P4Signal] = []
    keys: List[Tuple[str, date]] = []
    regimes: Counter[str] = Counter()
    no_calc: Counter[str] = Counter()
    for item in kept:
        obs = item.observation
        asset = _asset(universe, obs.asset)
        views = vintage.by_symbol[asset.primary_symbol]
        market = mercado_para_simbolo(asset, asset.primary_symbol)
        session = session_date_of(views.signal_prices.index[obs.signal_idx], market)
        if session is None:
            raise P4PreflightError(f"{asset.symbol}: señal sin sesión de plaza")
        keys.append((asset.symbol, session))
        regime, codes = _regime(resolver, views.signal_prices.index, obs.signal_idx, market, config)
        regimes[regime] += 1
        for code in codes:
            no_calc[code] += 1
        block_signal = _as_block_signal(obs)
        signals.append(
            P4Signal(
                observation=obs,
                region=asset.region,
                plaza_session=session,
                spine_session=lookups[PRIMARY_BLOCK_LENGTH].effective_session_date(block_signal),
                blocks={length: lookup.block_for(block_signal) for length, lookup in lookups.items()},
                regime=regime,
                next_open=_next_open(vintage, obs),
            )
        )

    population_sha256 = hashlib.sha256("\n".join(sorted(f"{s}\t{d}" for s, d in keys)).encode()).hexdigest()
    signal_ids_sha256 = hashlib.sha256("\n".join(sorted(s.signal_id for s in signals)).encode()).hexdigest()
    population = P4Population(
        signals=signals,
        meta=meta,
        lookups=lookups,
        a02=len(enumerated),
        crypto_excluded=len(enumerated) - len(kept),
        crypto_assets=tuple(sorted(crypto)),
        population_sha256=population_sha256,
        signal_ids_sha256=signal_ids_sha256,
        regions=dict(sorted(Counter(s.region for s in signals).items())),
        regimes=dict(sorted(regimes.items())),
        no_calculable_codes=dict(sorted(no_calc.items())),
        blocks={length: _block_summary(signals, lookups[length]) for length in BLOCK_LENGTHS},
        enumerated_levels={item.observation.signal_id: item.levels for item in kept},
    )
    population.checks = _population_checks(population, keys)
    return population


def _asset(universe: Universe, symbol: str) -> Any:
    asset = universe.get(symbol)
    if asset is None:
        raise P4PreflightError(f"{symbol}: activo ausente del universo")
    return asset


def _next_open(vintage: VintageLoad, observation: SignalObservation) -> float:
    # Solo la apertura de t+1: ni el máximo, ni el mínimo, ni el cierre de esa vela.
    return float(vintage.by_symbol[observation.asset].execution_prices["Open"].iloc[observation.signal_idx + 1])


def _context_resolver(config: AdvisorConfig, universe: Universe, vintage: VintageLoad) -> PointInTimeContextResolver:
    asia_symbols = tuple(sorted(a.primary_symbol for a in context_assets_of(universe) if a.region == "ASIA"))
    symbols = (config.market_context.vix_symbol, config.market_context.trend_symbol, *asia_symbols)
    closes = {s: c for s in symbols if (c := frozen_close(vintage, s)) is not None}
    return PointInTimeContextResolver(
        closes, config.market_context, asia_symbols=asia_symbols, settlement_minutes=config.data_quality.settlement_minutes
    )


def _regime(
    resolver: PointInTimeContextResolver,
    index: pd.Index,
    signal_idx: int,
    market: str,
    config: AdvisorConfig,
) -> Tuple[str, Tuple[str, ...]]:
    """Régimen PIT en el `analysis_timestamp` de la señal, solo para estratificar."""

    session = session_date_of(index[signal_idx], market)
    entry = session_date_of(index[signal_idx + 1], market)
    if session is None or entry is None:
        return NO_CALCULABLE_CONTEXT, ("SIN_SESION_DE_PLAZA",)
    ts = analysis_timestamp_for_signal(market, session, entry, settlement_minutes=config.data_quality.settlement_minutes)
    if ts is None:
        return NO_CALCULABLE_CONTEXT, ("SIN_ANALYSIS_TIMESTAMP",)
    resolved = resolver.resolve(ts)
    if resolved.calculable:
        assert resolved.context is not None
        return resolved.context.label, ()
    return NO_CALCULABLE_CONTEXT, tuple(resolved.exclusions or resolved.no_calculable_codes or ("SIN_CODIGO",))


def _block_summary(signals: Sequence[P4Signal], lookup: TemporalBlockMap) -> Dict[str, Any]:
    occupied = Counter(signal.blocks[lookup.block_length] for signal in signals)
    if not occupied:
        return {"bloques_ocupados": 0, "bloque_ocupado_mas_corto": None, "valida_P2_5": False}
    shortest = min(lookup.sessions_in_block(block) for block in occupied)
    return {
        "espina_sesiones": len(lookup.session_spine),
        "bloques_espina": len(set(lookup.session_to_block.values())),
        "bloques_ocupados": len(occupied),
        "primer_y_ultimo_ocupado": [min(occupied), max(occupied)],
        "bloque_ocupado_mas_corto": shortest,
        "valida_P2_5": shortest > MAX_HOLD_BARS,
        "senales_min_por_bloque": min(occupied.values()),
        "papel": block_role(lookup.block_length),
    }


def block_role(length: int) -> str:
    if length == PRIMARY_BLOCK_LENGTH:
        return "PRIMARIA"
    if length == SENSITIVITY_BLOCK_LENGTH:
        return "SENSIBILIDAD (condición 2)"
    return "INVÁLIDA (bloque ocupado más corto ≤ 40): publicada, fuera de toda condición"


def _population_checks(population: P4Population, keys: Sequence[Tuple[str, date]]) -> List[Tuple[str, Any, Any, bool]]:
    checks: List[Tuple[str, Any, Any, bool]] = []

    def check(name: str, observed: Any, wanted: Any) -> None:
        checks.append((name, observed, wanted, observed == wanted))

    check("A-02 swing", population.a02, EXPECTED_A02)
    check("cripto excluido", population.crypto_excluded, EXPECTED_CRYPTO)
    check("activos cripto", list(population.crypto_assets), list(EXPECTED_CRYPTO_ASSETS))
    check("población P4", len(population.signals), EXPECTED_P4)
    check("activos", len({s.asset for s in population.signals}), EXPECTED_ASSETS)
    check("(activo, sesión) únicos", len(set(keys)), len(keys))
    check("p4_population_sha256", population.population_sha256, P4_POPULATION_SHA256)
    check("signal_ids_sha256", population.signal_ids_sha256, P4_SIGNAL_IDS_SHA256)
    check("regiones", population.regions, dict(sorted(EXPECTED_REGIONS.items())))
    check("régimen PIT", population.regimes, dict(sorted(EXPECTED_REGIMES.items())))
    check("espina de sesiones", len(population.spine), EXPECTED_SPINE_SESSIONS)
    for length, (occupied, shortest) in EXPECTED_BLOCKS.items():
        summary = population.blocks[length]
        check(f"bloques {length}: ocupados", summary["bloques_ocupados"], occupied)
        check(f"bloques {length}: más corto", summary["bloque_ocupado_mas_corto"], shortest)
        check(f"bloques {length}: válida P2.5", summary["valida_P2_5"], length not in INVALID_BLOCK_LENGTHS)
    primary_blocks = sorted({s.blocks[PRIMARY_BLOCK_LENGTH] for s in population.signals})
    check("bloques 60 = mitades 2–11 ∪ 12–21", primary_blocks, sorted(FIRST_HALF_BLOCKS + SECOND_HALF_BLOCKS))
    check("data_vintage_id", population.meta.data_vintage_id, DATA_VINTAGE_ID)
    check("universe_vintage_id", population.meta.universe_vintage_id, UNIVERSE_VINTAGE_ID)
    return checks


# ---------------------------------------------------------------------------
# Niveles reales, holgura D-06 y estratos: todo en t (y open(t+1)).
# ---------------------------------------------------------------------------


def levels_by_geometry(population: P4Population, base: LevelsConfig) -> Dict[str, Dict[str, Optional[Levels]]]:
    # Una sola `LevelsConfig` por geometría: construir medio millón de modelos pydantic
    # dispara el recolector de basura y, con muchos objetos vivos, el tiempo se dispara.
    out: Dict[str, Dict[str, Optional[Levels]]] = {}
    for geometry in GEOMETRIES:
        config = geometry.levels_config(base)
        out[geometry.gid] = {s.signal_id: _levels_with(s.observation, config, geometry.min_rr) for s in population.signals}
    return out


def distribution(values: Sequence[float]) -> Dict[str, Any]:
    """Resumen puntual nearest-rank, sin intervalo (no es una comparación)."""

    if not values:
        return {"n": 0}
    ordered = sorted(values)
    out: Dict[str, Any] = {"n": len(ordered), "media": sum(ordered) / len(ordered), "min": ordered[0], "max": ordered[-1]}
    for k in DISTRIBUTION_PERCENTILES:
        out[f"p{k}"] = nearest_rank_cut(ordered, k)
    return out


def levels_census(
    population: P4Population,
    geometry: Geometry,
    levels: Mapping[str, Optional[Levels]],
    control: Mapping[str, Optional[Levels]],
) -> Dict[str, Any]:
    none_reasons: Counter[str] = Counter()
    basis: Counter[str] = Counter()
    pairs: Counter[str] = Counter()
    violations: Counter[str] = Counter()
    incoherent = 0
    rr_values: List[float] = []
    order_vs_c0: Counter[str] = Counter()
    for signal in population.signals:
        current = levels[signal.signal_id]
        if current is None:
            none_reasons[levels_none_reason(signal.observation, geometry)] += 1
            continue
        basis[stop_basis_of(current)] += 1
        rr_values.append(current.rr_ratio)
        found = coherence_violations(current, geometry.min_rr)
        if found:
            incoherent += 1
            violations.update(found)
        reference = control[signal.signal_id]
        if reference is None:
            raise P4PreflightError(f"{signal.signal_id}: C0 sin niveles en la población")
        if geometry.gid in STOP_BASIS_GEOMETRIES:
            pairs[stop_basis_pair(reference, current)] += 1
        if math.isclose(current.entry_max, reference.entry_max, rel_tol=ISCLOSE_REL_TOL):
            order_vs_c0["igual"] += 1
        elif current.entry_max < reference.entry_max:
            order_vs_c0["menor"] += 1
        else:
            order_vs_c0["mayor"] += 1
    valid = len(population.signals) - sum(none_reasons.values())
    return {
        "senales": len(population.signals),
        "validos": valid,
        "none": sum(none_reasons.values()),
        "none_por_motivo": dict(sorted(none_reasons.items())),
        "stop_basis": dict(sorted(basis.items())),
        "stop_basis_pares_c0_variante": {pair: pairs.get(pair, 0) for pair in STOP_BASIS_PAIRS}
        if geometry.gid in STOP_BASIS_GEOMETRIES
        else None,
        "rr_efectivo_en_p": distribution(rr_values),
        "rr_efectivo_bajo_min_rr": sum(1 for value in rr_values if not rr_at_least(value, geometry.min_rr)),
        "incoherentes": incoherent,
        "incoherencias_por_tipo": dict(sorted(violations.items())),
        "coherentes": incoherent == 0,
        "entry_max_frente_a_c0": dict(sorted(order_vs_c0.items())),
    }


def _slack_rows(signal: P4Signal, levels: Levels) -> Dict[str, float]:
    atr = signal.observation.atr
    assert atr is not None and levels.entry_max_rr is not None
    price = levels.price
    rr_slack = levels.entry_max_rr - price
    effective = levels.entry_max - price
    return {
        "rr_precio": rr_slack,
        "rr_atr": rr_slack / atr,
        "rr_pct": rr_slack / price * 100,
        "efectiva_precio": effective,
        "efectiva_atr": effective / atr,
        "efectiva_pct": effective / price * 100,
    }


def entry_slack(
    population: P4Population,
    geometry: Geometry,
    levels: Mapping[str, Optional[Levels]],
) -> Dict[str, Any]:
    """Holgura D-06 y categorías a `open(t+1)`, global y por región (§18). Sin desenlaces."""

    groups: Dict[str, List[Tuple[P4Signal, Levels]]] = {"GLOBAL": []}
    for signal in population.signals:
        current = levels[signal.signal_id]
        if current is None:
            continue
        groups["GLOBAL"].append((signal, current))
        groups.setdefault(f"region:{signal.region}", []).append((signal, current))

    out: Dict[str, Any] = {}
    for name in ["GLOBAL", *sorted(key for key in groups if key != "GLOBAL")]:
        rows = groups[name]
        slacks: Dict[str, List[float]] = {}
        binding: Counter[str] = Counter()
        categories: Counter[str] = Counter()
        distances: List[float] = []
        for signal, current in rows:
            for key, value in _slack_rows(signal, current).items():
                slacks.setdefault(key, []).append(value)
            binding[binding_limit(current)] += 1
            category = classify_open_entry(current, signal.next_open, geometry.min_rr)
            categories[category] += 1
            if category == ABOVE_MAX_ENTRY:
                atr = signal.observation.atr
                assert atr is not None
                distances.append((signal.next_open - current.entry_max) / atr)
        n = len(rows)
        out[name] = {
            "n": n,
            "holgura": {key: distribution(values) for key, values in slacks.items()},
            "manda": {key: binding.get(key, 0) for key in (BINDING_RR, BINDING_TECHNICAL, BINDING_TIE)},
            "manda_fraccion": {key: (binding.get(key, 0) / n if n else None) for key in (BINDING_RR, BINDING_TECHNICAL, BINDING_TIE)},
            "categoria_open_t1": {key: categories.get(key, 0) for key in OPEN_CATEGORIES},
            "categoria_open_t1_fraccion": {key: (categories.get(key, 0) / n if n else None) for key in OPEN_CATEGORIES},
            "distancia_above_max_entry_atr": {
                f"p{k}": nearest_rank_cut(sorted(distances), k) for k in DISTRIBUTION_PERCENTILES
            }
            if distances
            else None,
        }
    return out


def tercile_index(k: int, n: int) -> int:
    """Índice cero-based de `cut(k/3)` nearest-rank en aritmética entera: ⌈k·n/3⌉ − 1."""

    if n <= 0:
        raise ValueError("nearest-rank necesita al menos un valor")
    if k not in (1, 2):
        raise ValueError(f"tercil fuera de rango: {k}")
    return (k * n + 2) // 3 - 1


def tercile_cuts(values: Sequence[float]) -> Tuple[float, float]:
    ordered = sorted(values)
    return ordered[tercile_index(1, len(ordered))], ordered[tercile_index(2, len(ordered))]


def tercile_of(value: float, cuts: Sequence[float]) -> str:
    """T1=[mín,c1) … T3=[c2,máx]; un valor igual a un corte sube de tercil (regla de P3)."""

    for index, cut in enumerate(cuts):
        if value < cut:
            return TERCILE_LABELS[index]
    return TERCILE_LABELS[-1]


def strata_of(
    signal: P4Signal,
    cuts: Sequence[float],
    stop_basis: Optional[str],
) -> Dict[str, Optional[str]]:
    """Claves de estrato pre-registradas (§16). El régimen no calculable no se estima."""

    return {
        "regiones": signal.region,
        "regimenes": signal.regime if signal.regime in CALCULABLE_REGIMES else None,
        "terciles": tercile_of(signal.atr_ratio, cuts),
        "activos": signal.asset,
        "stop_basis": stop_basis,
    }


STRATUM_KINDS = ("regiones", "regimenes", "terciles", "activos", "stop_basis")


def geometry_strata(
    population: P4Population,
    geometry: Geometry,
    levels: Mapping[str, Optional[Levels]],
    control: Mapping[str, Optional[Levels]],
    cuts: Sequence[float],
) -> Dict[str, Dict[str, int]]:
    """Señales por estrato entre las que tienen niveles en C0 y en la variante (pares posibles)."""

    counts: Dict[str, Counter[str]] = {kind: Counter() for kind in STRATUM_KINDS}
    no_calc = 0
    for signal in population.signals:
        current = levels[signal.signal_id]
        reference = control[signal.signal_id]
        if current is None or reference is None:
            continue
        basis = stop_basis_pair(reference, current) if geometry.gid in STOP_BASIS_GEOMETRIES else None
        for kind, key in strata_of(signal, cuts, basis).items():
            if key is not None:
                counts[kind][key] += 1
        if signal.regime == NO_CALCULABLE_CONTEXT:
            no_calc += 1
    out = {kind: dict(sorted(counter.items())) for kind, counter in counts.items()}
    out["no_calculable_context_contado"] = {NO_CALCULABLE_CONTEXT: no_calc}
    return out


# ---------------------------------------------------------------------------
# Recuento de comparaciones (§20): fórmula única, derivada de las estimaciones.
# ---------------------------------------------------------------------------


def comparison_components(
    gid: str,
    *,
    regions: int,
    regimes: int,
    terciles: int,
    assets: int,
    stop_basis: int,
) -> Dict[str, int]:
    if gid == E1_ID:
        return {"primaria_60": 1}
    components = {
        "primaria_60": 1,
        "otras_longitudes": len(BLOCK_LENGTHS) - 1,
        "cotas_ambiguedad": len(AMBIGUITY_BOUNDS),
        "regiones": regions,
        "regimenes": regimes,
        "terciles": terciles,
        "mitades": 2,
        "nivel": 1,
        "activos": assets,
    }
    if gid in STOP_BASIS_GEOMETRIES:
        components["stop_basis"] = stop_basis
    return components


def planned_comparisons(strata: Mapping[str, Mapping[str, Mapping[str, int]]]) -> Dict[str, Any]:
    """Recuento estructural previsto desde los estratos con pares posibles (preflight)."""

    per_geometry: Dict[str, Dict[str, int]] = {}
    for geometry in VARIANTS:
        current = strata[geometry.gid]
        per_geometry[geometry.gid] = comparison_components(
            geometry.gid,
            regions=len(current["regiones"]),
            regimes=len(current["regimenes"]),
            terciles=len(current["terciles"]),
            assets=len(current["activos"]),
            stop_basis=len(current["stop_basis"]),
        )
    per_geometry[E1_ID] = comparison_components(E1_ID, regions=0, regimes=0, terciles=0, assets=0, stop_basis=0)
    return _comparison_totals(per_geometry, confirmatory=len(CONFIRMATORY_FAMILY))


def _comparison_totals(per_geometry: Mapping[str, Mapping[str, int]], *, confirmatory: int) -> Dict[str, Any]:
    subtotals = {gid: sum(components.values()) for gid, components in per_geometry.items()}
    return {
        "componentes": {gid: dict(components) for gid, components in per_geometry.items()},
        "subtotales": subtotals,
        "total": sum(subtotals.values()),
        "confirmatorias": confirmatory,
    }


def derived_comparisons(outputs: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """Recuento real: cuenta las estimaciones con IC que aparecen en las salidas."""

    per_geometry: Dict[str, Dict[str, int]] = {}
    confirmatory = 0
    for gid in (*(g.gid for g in VARIANTS), E1_ID):
        estimates = outputs[gid]["estimaciones"]
        components: Dict[str, int] = {}
        for key, value in estimates.items():
            items = [value] if _is_estimate(value) else list(value.values())
            with_interval = [item for item in items if _is_estimate(item) and item["ic_inferior"] is not None]
            components[key] = len(with_interval)
            confirmatory += sum(1 for item in with_interval if item.get("confirmatoria"))
        per_geometry[gid] = components
    return _comparison_totals(per_geometry, confirmatory=confirmatory)


def _is_estimate(value: Any) -> bool:
    return isinstance(value, Mapping) and "ic_inferior" in value


# ---------------------------------------------------------------------------
# E1 (§18.1): entrada a open(t+1) con veto de producción frente al cierre.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class E1Outcome:
    signal_id: str
    entry_category: str
    status: str
    net_r: Optional[float]
    entry_price: float
    managed: Optional[ManagedEvent]


def simulate_e1_open_entry(
    observation: SignalObservation,
    execution_df: pd.DataFrame,
    levels: Levels,
    *,
    max_hold_bars: int,
    cost_pct: float,
    min_rr: float,
) -> E1Outcome:
    """Brazo B: niveles C0 congelados en t, entrada a `open(t+1)` si producción la admite.

    La vela t+1 es también la de entrada: con la apertura ya entre stop y objetivo,
    `evaluate_managed_event` la clasifica entera con el contrato intrabarra (si toca
    los dos niveles es AMBIGUOUS) y sigue con las mismas barras t+1 … t+40 del brazo A.
    """

    signal_idx = observation.signal_idx
    entry = float(execution_df["Open"].iloc[signal_idx + 1])
    category = classify_open_entry(levels, entry, min_rr)
    if category != EXECUTABLE:
        return E1Outcome(observation.signal_id, category, f"{NOT_EXECUTED_PREFIX}{category}", 0.0, entry, None)
    managed = event_study.evaluate_managed_event(
        observation, execution_df, signal_idx, replace(levels, price=entry), max_hold_bars, cost_pct
    )
    return E1Outcome(observation.signal_id, EXECUTABLE, managed.exit_status, managed.net_r_multiple, entry, managed)


# ---------------------------------------------------------------------------
# Estimación (ejecución confirmatoria; testable con desenlaces sintéticos).
# ---------------------------------------------------------------------------


def block_estimate(
    deltas: Sequence[PairedDelta],
    spine: Sequence[date],
    *,
    block_length: int,
    confidence: float,
    n_resamples: int,
) -> Optional[BlockBootstrapResult]:
    if not deltas:
        return None
    return bootstrap_block_delta(
        deltas,
        block_length=block_length,
        seed=SEED,
        n_resamples=n_resamples,
        confidence=confidence,
        session_spine=spine,
    )


def estimate_dict(
    result: BlockBootstrapResult,
    *,
    role: str,
    confirmatory: bool = False,
    valid: bool = True,
    label: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "papel": role,
        "confirmatoria": confirmatory,
        "longitud_valida": valid,
        "etiqueta": label,
        "block_length": result.block_length,
        "n_pares": result.n_pairs,
        "n_bloques": result.n_blocks,
        "min_pares_bloque": min((block.n for block in result.blocks), default=0),
        "media_delta_r": result.mean_delta_r,
        "media_agrupada_delta_r": result.pooled_mean_delta_r,
        "ic_inferior": result.ci_lower,
        "ic_superior": result.ci_upper,
        "ic_nivel": result.ci_level,
        "remuestreos": result.n_resamples,
        "semilla": result.seed,
        "heterogeneidad": result.heterogeneity,
        "dispersion_observada": result.observed_dispersion,
        "ruido_inferior": result.noise_lower,
        "ruido_superior": result.noise_upper,
        "ruido_mediana": result.noise_median,
        "tau": result.tau_excess_dispersion,
        "exceedance": result.exceedance_fraction,
    }


def _resolved_net_r(event: ManagedEvent, side: str) -> float:
    """`net_R` observable, o el de la cota: AMBIGUOUS resuelto a stop o a target2."""

    if event.exit_status != AMBIGUOUS:
        if event.net_r_multiple is None:
            raise ValueError(f"{event.observation.signal_id}: {event.exit_status} sin net_R")
        return event.net_r_multiple
    exit_price = event.stop if side == "stop" else event.target
    return event_study.event_economics(event.entry_price, event.stop, exit_price, COST_PCT).net_r_multiple


def ambiguity_bound_deltas(
    control: Mapping[str, ManagedEvent],
    variant: Mapping[str, ManagedEvent],
    signal_by_id: Mapping[str, P4Signal],
    bound: str,
) -> List[PairedDelta]:
    """Envolventes de §17: la conservadora para V manda las ambiguas de V a stop y las de C0 a objetivo."""

    if bound not in AMBIGUITY_BOUNDS:
        raise ValueError(f"cota desconocida: {bound}")
    variant_side, control_side = ("stop", "target") if bound == "conservadora" else ("target", "stop")
    deltas: List[PairedDelta] = []
    for signal_id, event in variant.items():
        net_v = _resolved_net_r(event, variant_side)
        net_c = _resolved_net_r(control[signal_id], control_side)
        deltas.append(_delta(signal_by_id[signal_id], net_c, net_v))
    return deltas


def _delta(signal: P4Signal, net_a: float, net_b: float) -> PairedDelta:
    return PairedDelta(
        signal_id=signal.signal_id,
        asset=signal.asset,
        session=signal.spine_session,
        net_r_a=net_a,
        net_r_b=net_b,
        delta_r=net_b - net_a,
    )


def profit_factor(values: Iterable[float]) -> Optional[float]:
    observed = list(values)
    gains = sum(value for value in observed if value > 0)
    losses = sum(value for value in observed if value < 0)
    if losses == 0:
        return math.inf if gains > 0 else None
    return gains / abs(losses)


def level_estimate(events: Iterable[ManagedEvent], signal_by_id: Mapping[str, P4Signal]) -> Dict[str, Any]:
    """Primario de nivel de una geometría: media por bloque de 60 de su `net_R`, con IC95."""

    buckets: Dict[int, List[float]] = {}
    values: List[float] = []
    for event in events:
        if event.net_r_multiple is None:
            continue
        values.append(event.net_r_multiple)
        block = signal_by_id[event.observation.signal_id].blocks[PRIMARY_BLOCK_LENGTH]
        buckets.setdefault(block, []).append(event.net_r_multiple)
    block_values = [(sum(items) / len(items), len(items)) for _, items in sorted(buckets.items())]
    lower: Optional[float] = None
    upper: Optional[float] = None
    if len(block_values) >= 2:
        lower, upper = bootstrap_block_mean_interval(
            block_values, seed=SEED, n_resamples=STANDARD_RESAMPLES, confidence=STANDARD_CONFIDENCE
        )
    return {
        "papel": "nivel de la geometría (condición 10)",
        "confirmatoria": False,
        "n": len(values),
        "n_bloques": len(block_values),
        "media_net_r": (sum(mean for mean, _ in block_values) / len(block_values)) if block_values else None,
        "ic_inferior": lower,
        "ic_superior": upper,
        "ic_nivel": STANDARD_CONFIDENCE,
        "remuestreos": STANDARD_RESAMPLES,
        "profit_factor_agrupado": profit_factor(values),
    }


def secondaries(events: Sequence[ManagedEvent], potentials: Sequence[PotentialEvent]) -> Dict[str, Any]:
    """Secundarias puntuales de §11, sin IC (no cuentan como comparaciones)."""

    total = len(events)
    statuses = Counter(event.exit_status for event in events)
    target = statuses.get(TARGET_FIRST, 0)
    ambiguous = statuses.get(AMBIGUOUS, 0)
    net = [event.net_r_multiple for event in events if event.net_r_multiple is not None]
    gross = [event.gross_r_multiple for event in events if event.gross_r_multiple is not None]
    winners_mae = [event.mae_r for event in events if event.exit_status == TARGET_FIRST]
    return {
        "n": total,
        "estados": {key: statuses.get(key, 0) for key in (TARGET_FIRST, STOP_FIRST, AMBIGUOUS, TIME_EXIT, FINAL_EXIT)},
        "p_objetivo_antes_que_stop": [target / total, (target + ambiguous) / total] if total else None,
        "tasa_salida_tiempo": statuses.get(TIME_EXIT, 0) / total if total else None,
        "tasa_exit_final": statuses.get(FINAL_EXIT, 0) / total if total else None,
        "tasa_ambiguas": ambiguous / total if total else None,
        "mediana_mae_ganadoras_r": statistics.median(winners_mae) if winners_mae else None,
        "mediana_mfe_potencial_r": [
            statistics.median(p.mfe_unbounded_lower_r for p in potentials),
            statistics.median(p.mfe_unbounded_upper_r for p in potentials),
        ]
        if potentials
        else None,
        "gross_r_medio_diagnostico": (sum(gross) / len(gross)) if gross else None,
        "tasa_acierto_contexto": (sum(1 for value in net if value > 0) / len(net)) if net else None,
        "media_agrupada_net_r": (sum(net) / len(net)) if net else None,
        "profit_factor_agrupado": profit_factor(net),
    }


def capacity_check(
    primary: Optional[BlockBootstrapResult],
    width95: Optional[float],
    *,
    dropped_rate: float,
    exit_final_control: float,
    exit_final_variant: float,
    thresholds: CapacityThresholds = DEFAULT_THRESHOLDS,
) -> Dict[str, Any]:
    """Condición 3 con los `CapacityThresholds` vigentes, en el bloque primario."""

    reasons: List[str] = []
    n_blocks = primary.n_blocks if primary is not None else 0
    min_block = min((block.n for block in primary.blocks), default=0) if primary is not None else 0
    if n_blocks < thresholds.limited_blocks:
        reasons.append(f"bloques con pares {n_blocks} < {thresholds.limited_blocks}")
    if min_block < thresholds.min_observations_per_block:
        reasons.append(f"bloque con {min_block} pares < {thresholds.min_observations_per_block}")
    if dropped_rate > thresholds.max_ambiguous_rate:
        reasons.append(f"descarte por ambigüedad {dropped_rate:.4f} > {thresholds.max_ambiguous_rate}")
    if exit_final_control > thresholds.max_exit_final_rate:
        reasons.append(f"EXIT_FINAL control {exit_final_control:.4f} > {thresholds.max_exit_final_rate}")
    if exit_final_variant > thresholds.max_exit_final_rate:
        reasons.append(f"EXIT_FINAL variante {exit_final_variant:.4f} > {thresholds.max_exit_final_rate}")
    if width95 is None or width95 > thresholds.limited_interval_width:
        reasons.append(f"anchura IC95 {width95} > {thresholds.limited_interval_width}")
    return {
        "ok": not reasons,
        "motivos": reasons,
        "bloques_con_pares": n_blocks,
        "min_pares_bloque": min_block,
        "tasa_descarte_ambiguedad": dropped_rate,
        "exit_final_control": exit_final_control,
        "exit_final_variante": exit_final_variant,
        "anchura_ic95": width95,
        "nota": "la anchura IC95 sale de la misma estimación primaria (mismos remuestreos y semilla); no cuenta aparte",
    }


def _primary_estimates(
    deltas: Sequence[PairedDelta],
    spine: Sequence[date],
    *,
    confirmatory: bool,
) -> Tuple[Optional[BlockBootstrapResult], Optional[float], Optional[BlockBootstrapResult]]:
    """Primaria en 60, anchura IC95 de capacidad y heterogeneidad, todo de la misma estimación.

    - El IC de Bonferroni usa 20.000 remuestreos (§14).
    - `bootstrap_block_delta` sortea el IC con una semilla derivada solo de `SEED`:
      con el mismo número de remuestreos, el IC95 de capacidad sale de las mismas
      medias remuestreadas que el IC de Bonferroni.
    - La heterogeneidad sigue el contrato P2.6 (2.000 remuestreos, §14): los 20.000
      se aplican solo al intervalo corregido.
    """

    resamples = BONFERRONI_RESAMPLES if confirmatory else STANDARD_RESAMPLES
    confidence = BONFERRONI_CONFIDENCE if confirmatory else STANDARD_CONFIDENCE
    primary = block_estimate(deltas, spine, block_length=PRIMARY_BLOCK_LENGTH, confidence=confidence, n_resamples=resamples)
    if primary is None:
        return None, None, None
    if not confirmatory:
        return primary, primary.ci_upper - primary.ci_lower, primary
    same = block_estimate(deltas, spine, block_length=PRIMARY_BLOCK_LENGTH, confidence=STANDARD_CONFIDENCE, n_resamples=resamples)
    standard = block_estimate(
        deltas, spine, block_length=PRIMARY_BLOCK_LENGTH, confidence=STANDARD_CONFIDENCE, n_resamples=STANDARD_RESAMPLES
    )
    assert same is not None and standard is not None
    return primary, same.ci_upper - same.ci_lower, standard


def _with_heterogeneity(estimate: Dict[str, Any], standard: BlockBootstrapResult) -> Dict[str, Any]:
    return {
        **estimate,
        "heterogeneidad": standard.heterogeneity,
        "dispersion_observada": standard.observed_dispersion,
        "ruido_inferior": standard.noise_lower,
        "ruido_superior": standard.noise_upper,
        "ruido_mediana": standard.noise_median,
        "tau": standard.tau_excess_dispersion,
        "exceedance": standard.exceedance_fraction,
        "heterogeneidad_remuestreos": standard.n_resamples,
    }


def _blocks_without_pairs(population: P4Population, primary: Optional[BlockBootstrapResult]) -> List[int]:
    occupied = {s.blocks[PRIMARY_BLOCK_LENGTH] for s in population.signals}
    with_pairs = {block.block_index for block in primary.blocks} if primary is not None else set()
    return sorted(occupied - with_pairs)


def _exit_final_rate(events: Iterable[ManagedEvent]) -> float:
    values = list(events)
    return sum(1 for event in values if event.exit_status == FINAL_EXIT) / len(values) if values else 0.0


def analyze_variant(
    geometry: Geometry,
    population: P4Population,
    control: Mapping[str, ManagedEvent],
    variant_events: Mapping[str, ManagedEvent],
    without_levels: Sequence[str],
    potentials: Mapping[str, PotentialEvent],
    control_potentials: Mapping[str, PotentialEvent],
    cuts: Sequence[float],
    control_levels: Mapping[str, Optional[Levels]],
    variant_levels: Mapping[str, Optional[Levels]],
) -> Dict[str, Any]:
    """B1, B2, S1 o S2 frente a C0, emparejadas por `signal_id`, con todo lo pre-registrado."""

    if geometry.gid not in {g.gid for g in VARIANTS}:
        raise ValueError(f"{geometry.gid} no es una variante de P4")
    signal_by_id = {s.signal_id: s for s in population.signals}
    if set(variant_events) | set(without_levels) != set(signal_by_id) or set(variant_events) & set(without_levels):
        raise ValueError(f"{geometry.gid}: la réplica no cubre exactamente la población")
    spine = population.spine

    subset_control = {signal_id: control[signal_id] for signal_id in variant_events}
    paired = pair_populations(subset_control, variant_events)
    deltas = [
        _delta(signal_by_id[d.signal_id], d.net_r_a, d.net_r_b) for d in paired.deltas
    ]
    deltas.sort(key=lambda item: (item.session, item.asset, item.signal_id))

    confirmatory = geometry.confirmatory
    primary, width95, standard = _primary_estimates(deltas, spine, confirmatory=confirmatory)
    estimates: Dict[str, Any] = {}
    missing: List[str] = []
    if primary is not None and standard is not None:
        estimates["primaria_60"] = _with_heterogeneity(
            estimate_dict(
                primary,
                role="primaria confirmatoria (Bonferroni m=4)" if confirmatory else "primaria descriptiva (IC95)",
                confirmatory=confirmatory,
                label=geometry.label,
            ),
            standard,
        )
    else:
        missing.append("primaria_60: sin pares")

    for length in BLOCK_LENGTHS:
        if length == PRIMARY_BLOCK_LENGTH:
            continue
        result = block_estimate(deltas, spine, block_length=length, confidence=STANDARD_CONFIDENCE, n_resamples=STANDARD_RESAMPLES)
        if result is None:
            missing.append(f"bloque_{length}: sin pares")
            continue
        estimates[f"bloque_{length}"] = estimate_dict(
            result, role=block_role(length), valid=length not in INVALID_BLOCK_LENGTHS, label=geometry.label
        )

    for bound in AMBIGUITY_BOUNDS:
        bound_deltas = ambiguity_bound_deltas(control, variant_events, signal_by_id, bound)
        result = block_estimate(
            bound_deltas, spine, block_length=PRIMARY_BLOCK_LENGTH, confidence=STANDARD_CONFIDENCE, n_resamples=STANDARD_RESAMPLES
        )
        if result is None:
            missing.append(f"cota_{bound}: sin pares")
            continue
        estimates[f"cota_{bound}"] = estimate_dict(result, role=f"envolvente {bound} de ambigüedad (§17)", label=geometry.label)

    by_stratum: Dict[str, Dict[str, List[PairedDelta]]] = {kind: {} for kind in STRATUM_KINDS}
    no_calc_pairs = 0
    for delta in deltas:
        signal = signal_by_id[delta.signal_id]
        reference = control_levels[delta.signal_id]
        current = variant_levels[delta.signal_id]
        assert reference is not None and current is not None
        basis = stop_basis_pair(reference, current) if geometry.gid in STOP_BASIS_GEOMETRIES else None
        for kind, key in strata_of(signal, cuts, basis).items():
            if key is not None:
                by_stratum[kind].setdefault(key, []).append(delta)
        if signal.regime == NO_CALCULABLE_CONTEXT:
            no_calc_pairs += 1
    for kind in STRATUM_KINDS:
        if kind == "stop_basis" and geometry.gid not in STOP_BASIS_GEOMETRIES:
            continue
        estimates[kind] = {}
        for key, items in sorted(by_stratum[kind].items()):
            result = block_estimate(
                items, spine, block_length=PRIMARY_BLOCK_LENGTH, confidence=STANDARD_CONFIDENCE, n_resamples=STANDARD_RESAMPLES
            )
            assert result is not None
            estimates[kind][key] = estimate_dict(result, role=f"estrato descriptivo ({kind})", label=geometry.label)

    halves: Dict[str, Any] = {}
    for name, blocks in (("bloques_2_11", FIRST_HALF_BLOCKS), ("bloques_12_21", SECOND_HALF_BLOCKS)):
        items = [d for d in deltas if signal_by_id[d.signal_id].blocks[PRIMARY_BLOCK_LENGTH] in blocks]
        result = block_estimate(items, spine, block_length=PRIMARY_BLOCK_LENGTH, confidence=STANDARD_CONFIDENCE, n_resamples=STANDARD_RESAMPLES)
        if result is None:
            missing.append(f"mitad {name}: sin pares")
            continue
        halves[name] = estimate_dict(result, role=HALVES_LABEL, label=geometry.label)
    estimates["mitades"] = halves

    estimates["nivel"] = level_estimate(variant_events.values(), signal_by_id)

    shared_candle = sum(
        1
        for signal_id, event in variant_events.items()
        if event.exit_status == AMBIGUOUS
        and control[signal_id].exit_status == AMBIGUOUS
        and control[signal_id].exit_idx == event.exit_idx
    )
    both_ambiguous = sum(
        1
        for signal_id, event in variant_events.items()
        if event.exit_status == AMBIGUOUS and control[signal_id].exit_status == AMBIGUOUS
    )
    exit_final_control = _exit_final_rate(control.values())
    exit_final_variant = _exit_final_rate(variant_events.values())
    return {
        "geometria": geometry.as_dict(),
        "comparacion": comparison_id(geometry.gid),
        "etiqueta": geometry.label,
        "emparejamiento": {
            "senales_poblacion": len(signal_by_id),
            "sin_niveles": len(without_levels),
            "con_niveles": len(variant_events),
            "dropped_only_c0": paired.dropped_only_a,
            "dropped_only_variant": paired.dropped_only_b,
            "dropped_both": paired.dropped_both,
            "pares_finales": len(deltas),
            "bloques_60_sin_pares": _blocks_without_pairs(population, primary),
            "fraccion_pares": len(deltas) / len(signal_by_id) if signal_by_id else 0.0,
            "tasa_descarte_ambiguedad": paired.dropped_rate,
            "pares_no_calculable_context": no_calc_pairs,
            "ambiguas_en_los_dos_brazos": both_ambiguous,
            "vela_ambigua_compartida": shared_candle,
        },
        "estimaciones": estimates,
        "sin_estimacion": missing,
        "medias_por_bloque_60": [
            {"bloque": block.block_index, "n": block.n, "media_delta_r": block.mean_delta_r}
            for block in (primary.blocks if primary is not None else ())
        ],
        "capacidad": capacity_check(
            primary,
            width95,
            dropped_rate=paired.dropped_rate,
            exit_final_control=exit_final_control,
            exit_final_variant=exit_final_variant,
        ),
        "secundarias": {
            "variante": secondaries(list(variant_events.values()), [potentials[s] for s in variant_events]),
            "c0_mismas_senales": secondaries(
                [control[s] for s in variant_events], [control_potentials[s] for s in variant_events]
            ),
            "media_agrupada_delta_r": primary.pooled_mean_delta_r if primary is not None else None,
        },
    }


def analyze_e1(
    population: P4Population,
    control: Mapping[str, ManagedEvent],
    outcomes: Mapping[str, E1Outcome],
) -> Dict[str, Any]:
    """Una sola estimación (bloque 60, Bonferroni); sin estratos, cotas, mitades, sensibilidad ni nivel."""

    signal_by_id = {s.signal_id: s for s in population.signals}
    if set(outcomes) != set(signal_by_id) or set(control) != set(signal_by_id):
        raise ValueError("E1: los brazos no cubren exactamente la población")
    deltas: List[PairedDelta] = []
    only_a = only_b = both = 0
    for signal_id in sorted(signal_by_id):
        net_a = control[signal_id].net_r_multiple
        net_b = outcomes[signal_id].net_r
        if net_a is None and net_b is None:
            both += 1
        elif net_a is None:
            only_a += 1
        elif net_b is None:
            only_b += 1
        else:
            deltas.append(_delta(signal_by_id[signal_id], net_a, net_b))
    deltas.sort(key=lambda item: (item.session, item.asset, item.signal_id))
    total = len(signal_by_id)
    dropped_rate = (only_a + only_b + both) / total if total else 0.0
    primary, width95, standard = _primary_estimates(deltas, population.spine, confirmatory=True)
    categories = Counter(outcome.entry_category for outcome in outcomes.values())
    statuses = Counter(outcome.status for outcome in outcomes.values())
    exit_final_b = statuses.get(FINAL_EXIT, 0) / total if total else 0.0
    capacity = capacity_check(
        primary,
        width95,
        dropped_rate=dropped_rate,
        exit_final_control=_exit_final_rate(control.values()),
        exit_final_variant=exit_final_b,
    )
    estimates: Dict[str, Any] = {}
    if primary is not None and standard is not None:
        estimates["primaria_60"] = _with_heterogeneity(
            estimate_dict(primary, role="primaria confirmatoria (Bonferroni m=4)", confirmatory=True, label=E1_LABEL),
            standard,
        )
    return {
        "comparacion": E1_ID,
        "etiqueta": E1_LABEL,
        "eligible_for_p5": False,
        "confirmatory": True,
        "categorias_open_t1": {key: categories.get(key, 0) for key in OPEN_CATEGORIES},
        "estados_brazo_b": dict(sorted(statuses.items())),
        "emparejamiento": {
            "senales_poblacion": total,
            "dropped_only_a": only_a,
            "dropped_only_b": only_b,
            "dropped_both": both,
            "pares_finales": len(deltas),
            "bloques_60_sin_pares": _blocks_without_pairs(population, primary),
            "tasa_descarte_ambiguedad": dropped_rate,
        },
        "estimaciones": estimates,
        "capacidad": capacity,
        "lectura": e1_reading(primary, capacity["ok"]),
    }


E1_WINS = "GANA"
E1_LOSES = "PIERDE"
E1_INCONCLUSIVE = "NO CONCLUYENTE"


def e1_reading(primary: Optional[BlockBootstrapResult], capacity_ok: bool) -> str:
    """Lectura mecánica pre-registrada de E1: no selecciona nada."""

    if primary is None or not capacity_ok:
        return E1_INCONCLUSIVE
    if primary.ci_lower > 0:
        return E1_WINS
    if primary.ci_upper < 0:
        return E1_LOSES
    return E1_INCONCLUSIVE


# ---------------------------------------------------------------------------
# Criterio mecánico (§22): solo B2, S1 y S2.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateEvidence:
    geometry_id: str
    bonferroni_lower: Optional[float]
    sensitivity_120_mean: Optional[float]
    sensitivity_120_lower: Optional[float]
    capacity_ok: bool
    capacity_reasons: Tuple[str, ...]
    heterogeneity: str
    conservative_bound_mean: Optional[float]
    levels_coherent: bool
    executability: Mapping[str, Any]
    first_half_mean: Optional[float]
    second_half_mean: Optional[float]
    pairs: int
    population: int
    level_mean: Optional[float]
    level_profit_factor: Optional[float]


@dataclass(frozen=True)
class ConditionResult:
    number: int
    name: str
    vetoes: bool
    passed: Optional[bool]
    detail: str


@dataclass(frozen=True)
class CandidateVerdict:
    geometry_id: str
    passes: bool
    conditions: Tuple[ConditionResult, ...]


def _positive(value: Optional[float]) -> bool:
    return value is not None and value > 0


def evaluate_candidate(evidence: CandidateEvidence) -> CandidateVerdict:
    """Las diez condiciones de §22. La 4 (heterogeneidad) y la 7 (ejecutabilidad) se publican y no se leen."""

    if evidence.geometry_id not in CANDIDATE_IDS:
        raise ValueError(f"{evidence.geometry_id} no puede evaluarse como candidata: solo {CANDIDATE_IDS}")
    pair_fraction = evidence.pairs / evidence.population if evidence.population else 0.0
    pf = evidence.level_profit_factor
    conditions = (
        ConditionResult(1, "IC Bonferroni (m=4) en 60: inferior > 0", True, _positive(evidence.bonferroni_lower),
                        f"inferior={evidence.bonferroni_lower}"),
        ConditionResult(2, "Bloque 120: ΔR > 0 e IC95 inferior > 0 (veto sin corrección)", True,
                        _positive(evidence.sensitivity_120_mean) and _positive(evidence.sensitivity_120_lower),
                        f"media={evidence.sensitivity_120_mean}; inferior={evidence.sensitivity_120_lower}"),
        ConditionResult(3, "Capacidad P2.5 en 60", True, evidence.capacity_ok, "; ".join(evidence.capacity_reasons) or "ok"),
        ConditionResult(4, "Heterogeneidad: se publica, no veta ni aprueba", False, None, "publicada aparte"),
        ConditionResult(5, "Cota conservadora de ambigüedad: ΔR > 0 (veto sin corrección)", True,
                        _positive(evidence.conservative_bound_mean), f"media={evidence.conservative_bound_mean}"),
        ConditionResult(6, "RR y niveles efectivos coherentes en toda señal", True, evidence.levels_coherent, ""),
        ConditionResult(7, "Ejecutabilidad: se publica, no veta", False, None, "publicada aparte"),
        ConditionResult(8, f"{HALVES_LABEL}: ΔR > 0 en bloques 2–11 y 12–21 (veto sin corrección)", True,
                        _positive(evidence.first_half_mean) and _positive(evidence.second_half_mean),
                        f"2–11={evidence.first_half_mean}; 12–21={evidence.second_half_mean}"),
        ConditionResult(9, f"Pares ≥ {MIN_PAIR_FRACTION:.0%} de {EXPECTED_P4}", True,
                        pair_fraction >= MIN_PAIR_FRACTION, f"pares={evidence.pairs}; fracción={pair_fraction:.4f}"),
        ConditionResult(10, "Nivel de la geometría: primario > 0 y PF agrupado > 1 (veto sin corrección)", True,
                        _positive(evidence.level_mean) and pf is not None and pf > 1,
                        f"media={evidence.level_mean}; PF={pf}"),
    )
    passes = all(bool(condition.passed) for condition in conditions if condition.vetoes)
    return CandidateVerdict(geometry_id=evidence.geometry_id, passes=passes, conditions=conditions)


def candidates_for_p5(verdicts: Sequence[CandidateVerdict]) -> Tuple[str, ...]:
    """Todas las que cumplen pasan a P5; ninguna → C0 permanece. No se elige un máximo."""

    for verdict in verdicts:
        if verdict.geometry_id not in CANDIDATE_IDS:
            raise ValueError(f"{verdict.geometry_id} no puede ser candidata a P5")
    return tuple(verdict.geometry_id for verdict in verdicts if verdict.passes)


def candidate_evidence(
    gid: str,
    output: Mapping[str, Any],
    levels_census_row: Mapping[str, Any],
    executability: Mapping[str, Any],
) -> CandidateEvidence:
    if gid not in CANDIDATE_IDS:
        raise ValueError(f"{gid} no puede evaluarse como candidata")
    estimates = output["estimaciones"]
    primary = estimates.get("primaria_60") or {}
    sensitivity = estimates.get(f"bloque_{SENSITIVITY_BLOCK_LENGTH}") or {}
    conservative = estimates.get("cota_conservadora") or {}
    halves = estimates.get("mitades") or {}
    level = estimates.get("nivel") or {}
    pairing = output["emparejamiento"]
    return CandidateEvidence(
        geometry_id=gid,
        bonferroni_lower=primary.get("ic_inferior"),
        sensitivity_120_mean=sensitivity.get("media_delta_r"),
        sensitivity_120_lower=sensitivity.get("ic_inferior"),
        capacity_ok=bool(output["capacidad"]["ok"]),
        capacity_reasons=tuple(output["capacidad"]["motivos"]),
        heterogeneity=str(primary.get("heterogeneidad")),
        conservative_bound_mean=conservative.get("media_delta_r"),
        levels_coherent=bool(levels_census_row["coherentes"]),
        executability=executability,
        first_half_mean=(halves.get("bloques_2_11") or {}).get("media_delta_r"),
        second_half_mean=(halves.get("bloques_12_21") or {}).get("media_delta_r"),
        pairs=int(pairing["pares_finales"]),
        population=EXPECTED_P4,
        level_mean=level.get("media_net_r"),
        level_profit_factor=level.get("profit_factor_agrupado"),
    )


def verdict_dict(verdict: CandidateVerdict) -> Dict[str, Any]:
    return {
        "geometria": verdict.geometry_id,
        "pasa_a_p5": verdict.passes,
        "condiciones": [
            {"n": c.number, "condicion": c.name, "veta": c.vetoes, "cumple": c.passed, "detalle": c.detail}
            for c in verdict.conditions
        ],
    }


# ---------------------------------------------------------------------------
# Identidad del árbol.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class P4Identity:
    executor_sha: str
    git_dirty: Optional[bool]
    prereg_in_history: Optional[bool]
    config_hash: str
    score_model_version: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "p4_prereg_sha": P4_PREREG_SHA,
            "p4_executor_sha": self.executor_sha,
            "git_dirty": self.git_dirty,
            "prereg_en_historia": self.prereg_in_history,
            "data_vintage_id": DATA_VINTAGE_ID,
            "universe_vintage_id": UNIVERSE_VINTAGE_ID,
            "config_hash": self.config_hash,
            "config_score_model_version": self.score_model_version,
            "cost_pct": COST_PCT,
            "seed": SEED,
            "standard": {"confidence": STANDARD_CONFIDENCE, "resamples": STANDARD_RESAMPLES},
            "bonferroni": {"m": BONFERRONI_M, "confidence": BONFERRONI_CONFIDENCE, "resamples": BONFERRONI_RESAMPLES},
            "label": UNIVERSE_LABEL,
        }


def current_identity(config: AdvisorConfig, repo: str | Path = ".") -> P4Identity:
    return P4Identity(
        executor_sha=git_sha(repo),
        git_dirty=tree_dirty(repo),
        prereg_in_history=prereg_in_history(repo),
        config_hash=config_hash(config),
        score_model_version=config.scoring.score_model_version,
    )


def tree_dirty(repo: str | Path = ".") -> Optional[bool]:
    """Ficheros con seguimiento modificados, o cualquier fichero sin seguimiento en el ejecutor.

    `git_dirty` ignora los ficheros sin seguimiento a propósito (en la Pi `logs/`
    existe siempre), pero aquí un `p4.py` sin commitear daría un «árbol limpio» con
    un SHA que no contiene el código que se ejecuta.
    """

    tracked = git_dirty(repo).value
    untracked = run_git(["status", "--porcelain", "--untracked-files=all", "--", *EXECUTOR_PATHS], repo)
    if tracked is None or not untracked.ok:
        return None
    return tracked or bool(untracked.output)


def prereg_in_history(repo: str | Path = ".") -> Optional[bool]:
    """¿`P4_PREREG_SHA` es antecesor de HEAD? None si no se puede saber."""

    if run_git(["merge-base", "--is-ancestor", P4_PREREG_SHA, "HEAD"], repo).ok:
        return True
    kind = run_git(["cat-file", "-t", P4_PREREG_SHA], repo)
    if kind.ok and kind.output == "commit":
        return False
    return None


def executor_unchanged_since(sha: str, repo: str | Path = ".") -> bool:
    """¿Nada de lo que decide desenlaces cambió entre `sha` y HEAD?"""

    return run_git(["diff", "--quiet", sha, "HEAD", "--", *EXECUTOR_PATHS], repo).ok


def tree_checks(config: AdvisorConfig, ident: P4Identity) -> List[Tuple[str, Any, Any, bool]]:
    checks: List[Tuple[str, Any, Any, bool]] = []

    def check(name: str, observed: Any, wanted: Any) -> None:
        checks.append((name, observed, wanted, observed == wanted))

    check("config.yaml score_model_version", config.scoring.score_model_version, ACTIVE_SCORE_MODEL_VERSION)
    check("config_hash", ident.config_hash, EXPECTED_CONFIG_HASH)
    check("P4_PREREG_SHA en la historia", ident.prereg_in_history, True)
    check("C0 = niveles de producción", C0.levels_config(config.levels) == config.levels, True)
    check("min_rr = risk.min_rr_ratio", C0.min_rr, config.risk.min_rr_ratio)
    return checks


# ---------------------------------------------------------------------------
# Preflight.
# ---------------------------------------------------------------------------


def _checks_dicts(checks: Iterable[Tuple[str, Any, Any, bool]]) -> List[Dict[str, Any]]:
    return [{"control": n, "observado": o, "esperado": w, "ok": p} for n, o, w, p in checks]


def compute_preflight_sections(
    population: P4Population, base: LevelsConfig
) -> Tuple[Dict[str, Any], List[Tuple[str, Any, Any, bool]], Dict[str, Dict[str, Optional[Levels]]]]:
    """Álgebra, niveles, holgura D-06, estratos y recuento: solo primitivas en t y `open(t+1)`.

    Devuelve también los niveles de cada geometría: son los que la ejecución
    confirmatoria congela antes de la marca y evalúa sin volver a calcularlos.
    """

    checks: List[Tuple[str, Any, Any, bool]] = []

    def check(name: str, observed: Any, wanted: Any) -> None:
        checks.append((name, observed, wanted, observed == wanted))

    levels = levels_by_geometry(population, base)
    control = levels[C0.gid]
    mismatched = sum(1 for s in population.signals if control[s.signal_id] != population.enumerated_levels[s.signal_id])
    check("C0 recalculado = niveles de la enumeración", mismatched, 0)

    algebra_rows: Dict[str, Any] = {}
    for geometry in GEOMETRIES:
        formula = algebra(geometry)
        measured = synthetic_algebra(geometry, base)
        algebra_rows[geometry.gid] = {"formula": formula, "niveles_sinteticos_P100_A2": measured}
        for key, value in formula.items():
            check(f"álgebra {geometry.gid} {key}", math.isclose(measured[key], value, rel_tol=1e-9, abs_tol=1e-12), True)

    census = {g.gid: levels_census(population, g, levels[g.gid], control) for g in GEOMETRIES}
    check("C0 sin niveles None", census[C0.gid]["none"], 0)
    check("C0 coherente", census[C0.gid]["coherentes"], True)

    slack = {g.gid: entry_slack(population, g, levels[g.gid]) for g in GEOMETRIES}
    check("RR_TOO_LOW inalcanzable en C0", slack[C0.gid]["GLOBAL"]["categoria_open_t1"][RR_TOO_LOW], 0)

    cuts = tercile_cuts([s.atr_ratio for s in population.signals])
    terciles = Counter(tercile_of(s.atr_ratio, cuts) for s in population.signals)
    strata = {g.gid: geometry_strata(population, g, levels[g.gid], control, cuts) for g in VARIANTS}
    comparisons = planned_comparisons(strata)
    check("recuento estructural de comparaciones", comparisons["total"], EXPECTED_COMPARISONS)
    check("confirmatorias", comparisons["confirmatorias"], EXPECTED_CONFIRMATORY)
    check("familia confirmatoria", list(CONFIRMATORY_FAMILY), ["B2_vs_C0", "S1_vs_C0", "S2_vs_C0", "E1"])
    check("BONFERRONI_M = len(familia)", BONFERRONI_M, len(CONFIRMATORY_FAMILY))

    sections: Dict[str, Any] = {
        "rejilla": {g.gid: g.as_dict() for g in GEOMETRIES},
        "algebra": algebra_rows,
        "niveles": census,
        "holgura_d06": slack,
        "volatilidad": {
            "metodo": "nearest-rank, cut(k/3) = x[⌈k·n/3⌉−1]; un valor igual a un corte sube de tercil",
            "cortes_atr_sobre_precio": list(cuts),
            "n_por_tercil": {label: terciles.get(label, 0) for label in TERCILE_LABELS},
        },
        "estratos": strata,
        "familia_confirmatoria": {
            "miembros": list(CONFIRMATORY_FAMILY),
            "m": BONFERRONI_M,
            "confidence": BONFERRONI_CONFIDENCE,
            "remuestreos": BONFERRONI_RESAMPLES,
            "fuera_de_la_familia": {"B1": B1_LABEL},
        },
        "e1": {
            "definicion": E1_LABEL,
            "categorias_open_t1_c0": slack[C0.gid]["GLOBAL"]["categoria_open_t1"],
            "estimaciones_previstas": 1,
        },
        "recuento": comparisons,
        "bloques_mitades": {"primera": list(FIRST_HALF_BLOCKS), "segunda": list(SECOND_HALF_BLOCKS), "rotulo": HALVES_LABEL},
        "decisiones_de_implementacion": IMPLEMENTATION_DECISIONS,
        "niveles_sha256": {gid: levels_sha256(values) for gid, values in levels.items()},
    }
    return sections, checks, levels


def levels_sha256(levels: Mapping[str, Optional[Levels]]) -> str:
    """Huella de los niveles de una geometría: stop, objetivos y entry_max de cada señal."""

    lines = []
    for signal_id in sorted(levels):
        current = levels[signal_id]
        if current is None:
            lines.append(f"{signal_id}\tNone")
        else:
            lines.append(
                f"{signal_id}\t{current.stop!r}\t{current.target1!r}\t{current.target2!r}\t"
                f"{current.target3!r}\t{current.entry_max!r}"
            )
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


IMPLEMENTATION_DECISIONS: Tuple[str, ...] = (
    "Terciles de ATR/P: nearest-rank cut(k/3) = x[⌈k·n/3⌉−1]; un valor igual a un corte sube de tercil (regla de P3).",
    "Tasa de descarte por ambigüedad (condición 3): descartes / señales con niveles en la variante "
    "(en E1, / población); el emparejamiento por niveles se publica aparte.",
    "EXIT_FINAL del brazo B de E1: sobre toda la población, incluidas las no ejecutadas (R = 0).",
    "Nivel de la geometría (condición 10): media por bloque de 60 y PF agrupado sobre todos sus net_R observables, como en P3.",
    "Heterogeneidad publicada: contrato P2.6 (2.000 remuestreos) sobre los mismos pares de la primaria, también en "
    "B2/S1/S2/E1; los 20.000 solo para el IC de Bonferroni y la anchura IC95 de capacidad.",
    "Anchura IC95 de capacidad en B2/S1/S2/E1: cuantiles 2,5/97,5 de las mismas 20.000 medias remuestreadas del IC de Bonferroni.",
    "Pares (condición 9): pares con net_R observable en C0 y en G sobre 101.251.",
    "Población, niveles de las cinco geometrías y cortes de terciles se congelan sin desenlaces antes de la marca "
    "(sus hashes van en la marca); tras ella solo se evalúan con evaluate_managed_event / evaluate_potential_event, "
    "las mismas primitivas del event study y de replay_managed_population, sin volver a enumerar ni recalcular niveles.",
    "Brazo A de E1 y control de toda comparación: el ManagedEvent de C0 con los niveles de la enumeración del event "
    "study (control del preflight: 0 diferencias). La identidad réplica = event study (test 3 de la ficha) se cumple "
    "por construcción; en este paso no se calcula ningún net_R sobre la cosecha.",
)


def preflight_fingerprint(report: Mapping[str, Any]) -> Dict[str, Any]:
    """Lo que la ejecución confirmatoria exige idéntico entre el preflight guardado y el suyo."""

    population = report.get("poblacion", {})
    return {
        "poblacion": population,
        "bloques": report.get("bloques"),
        "volatilidad": report.get("volatilidad"),
        "niveles": report.get("niveles"),
        "recuento": report.get("recuento"),
        "rejilla": report.get("rejilla"),
        "niveles_sha256": report.get("niveles_sha256"),
    }


@dataclass
class FrozenRun:
    """Lo que se fija sin desenlaces y la ejecución confirmatoria ya no puede cambiar."""

    population: P4Population
    levels: Dict[str, Dict[str, Optional[Levels]]]
    cuts: Tuple[float, float]


def run_preflight(
    config: AdvisorConfig,
    universe: Universe,
    vintage: VintageLoad,
    ident: P4Identity,
    *,
    development: bool = False,
    write: bool = True,
    out_dir: Path = PREFLIGHT_DIR,
) -> Tuple[bool, Dict[str, Any]]:
    """Preflight sin desenlaces. Se para (ok=False) si la población no reproduce el censo."""

    ok, report, _ = _preflight(config, universe, vintage, ident, development=development)
    if write and not development:
        if (CONFIRMATORY_OUTPUT_DIR / RUN_MARKER).exists():
            raise P4AlreadyExecutedError("P4 ya se ejecutó: el preflight que la autorizó no se reescribe")
        out_dir.mkdir(parents=True, exist_ok=True)
        write_json(out_dir / "p4-preflight.json", report)
        (out_dir / "p4-preflight.txt").write_text(format_preflight(report), encoding="utf-8")
    return ok, report


def _preflight(
    config: AdvisorConfig,
    universe: Universe,
    vintage: VintageLoad,
    ident: P4Identity,
    *,
    development: bool = False,
) -> Tuple[bool, Dict[str, Any], Optional[FrozenRun]]:
    started = utc_now()
    population = build_population(config, universe, vintage)
    tree = tree_checks(config, ident)
    report: Dict[str, Any] = {
        "fase": "preflight",
        "modo": "DESARROLLO (no es evidencia)" if development else "DEFINITIVO",
        "identidad": ident.as_dict(),
        "inicio_utc": started,
        "outcomes_read": False,
        "p4_confirmatory_executed": (CONFIRMATORY_OUTPUT_DIR / RUN_MARKER).exists(),
        "poblacion": {
            "a02_swing": population.a02,
            "cripto_excluido": population.crypto_excluded,
            "cripto_activos": list(population.crypto_assets),
            "p4": len(population.signals),
            "activos": len({s.asset for s in population.signals}),
            "p4_population_sha256": population.population_sha256,
            "signal_ids_sha256": population.signal_ids_sha256,
            "regiones": population.regions,
            "exclusiones_p3_aplicadas": False,
        },
        "bloques": {str(length): summary for length, summary in population.blocks.items()},
        "contexto_pit": {
            "regimen": population.regimes,
            "no_calculable_por_codigo": population.no_calculable_codes,
            "nota": "NO_CALCULABLE_CONTEXT permanece en la primaria; no se le inventa régimen",
        },
        "label": UNIVERSE_LABEL,
    }
    checks = list(population.checks) + tree
    frozen: Optional[FrozenRun] = None
    if population.ok:
        sections, section_checks, levels = compute_preflight_sections(population, config.levels)
        report.update(sections)
        checks += section_checks
        cuts = sections["volatilidad"]["cortes_atr_sobre_precio"]
        frozen = FrozenRun(population=population, levels=levels, cuts=(cuts[0], cuts[1]))
    else:
        report["abortado"] = "la población no reproduce el censo congelado: STOP → OWNER_DECISION_REQUIRED"
    report["checks"] = _checks_dicts(checks)
    ok = all(passed for *_, passed in checks)
    report["ok"] = ok
    report["definitivo"] = bool(ok and not development and ident.git_dirty is False and ident.prereg_in_history is True)
    report["fin_utc"] = utc_now()
    return ok, report, frozen


# ---------------------------------------------------------------------------
# Ejecución confirmatoria única.
# ---------------------------------------------------------------------------


def _load_stored_preflight(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise P4PreflightError(f"falta el preflight definitivo en {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not (data.get("ok") is True and data.get("definitivo") is True):
        raise P4PreflightError(f"{path} no es un preflight definitivo y correcto")
    return cast(Dict[str, Any], data)


def _normalized(value: Any) -> Any:
    return json.loads(json.dumps(_finite(value), default=_json_default, sort_keys=True))


def run_confirmatory(
    config: AdvisorConfig,
    universe: Universe,
    vintage: VintageLoad,
    ident: P4Identity,
    out_dir: Path,
) -> Tuple[int, str]:
    """La única ejecución de P4. Devuelve el código de salida y el texto que imprime la CLI."""

    if out_dir.resolve() != CONFIRMATORY_OUTPUT_DIR.resolve():
        raise P4PreflightError(f"la ejecución confirmatoria solo escribe en {CONFIRMATORY_OUTPUT_DIR}")
    marker = out_dir / RUN_MARKER
    if marker.exists():
        raise P4AlreadyExecutedError(f"la ejecución confirmatoria ya se inició ({marker}); P4 no se repite")
    if ident.git_dirty is not False:
        raise P4PreflightError(f"el árbol no está limpio o no se pudo comprobar (git_dirty={ident.git_dirty})")
    if ident.prereg_in_history is not True:
        raise P4PreflightError(f"P4_PREREG_SHA {P4_PREREG_SHA} no está en la historia de HEAD")
    if out_dir.exists() and any(out_dir.iterdir()):
        raise P4AlreadyExecutedError(f"{out_dir} no está vacío: P4 no se repite ni se sobrescribe")

    stored = _load_stored_preflight(PREFLIGHT_DIR / "p4-preflight.json")
    executor = str(stored["identidad"]["p4_executor_sha"])
    if not executor_unchanged_since(executor, "."):
        raise P4PreflightError(f"el ejecutor cambió desde el preflight definitivo ({executor}): P4 no se ejecuta")

    ok, preflight, frozen = _preflight(config, universe, vintage, ident)
    if not ok or frozen is None:
        return 2, format_preflight(preflight) + "PREFLIGHT FALLIDO: P4 NO SE EJECUTA.\n"
    if _normalized(preflight_fingerprint(preflight)) != _normalized(preflight_fingerprint(stored)):
        return 2, "STOP: el preflight interno no coincide con el preflight definitivo guardado. P4 NO SE EJECUTA.\n"

    out_dir.mkdir(parents=True, exist_ok=True)
    started = utc_now()
    marker.write_text(
        json.dumps(marker_payload(started, ident, executor, preflight), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    # A partir de aquí se abren desenlaces: P4 ya no se puede repetir. La población,
    # los niveles y los cortes son los congelados arriba; ya no se recalculan.
    code, result = execute_with_outcomes(vintage, ident, preflight, frozen)
    if code != 0:
        write_json(out_dir / "p4-parada.json", result)
        return code, "STOP → OWNER_DECISION_REQUIRED: " + str(result.get("motivo")) + "\n"
    result["inicio_utc"] = started
    result["fin_utc"] = utc_now()
    write_json(out_dir / "p4-resultado.json", result)
    write_tables(out_dir / "tablas", result)
    summary = format_result(result)
    (out_dir / "p4-resumen.md").write_text(summary, encoding="utf-8")
    return 0, summary


def marker_payload(started: str, ident: P4Identity, executor: str, preflight: Mapping[str, Any]) -> Dict[str, Any]:
    """La marca de ejecución única: identidad completa de lo que se va a medir, escrita antes de medirlo."""

    population = preflight["poblacion"]
    return {
        "inicio_utc": started,
        "p4_prereg_sha": P4_PREREG_SHA,
        "p4_executor_sha_preflight": executor,
        "head_sha": ident.executor_sha,
        "identidad": ident.as_dict(),
        "p4_population_sha256": population["p4_population_sha256"],
        "signal_ids_sha256": population["signal_ids_sha256"],
        "senales": population["p4"],
        "niveles_sha256": preflight["niveles_sha256"],
        "cortes_terciles": preflight["volatilidad"]["cortes_atr_sobre_precio"],
        "familia_confirmatoria": list(CONFIRMATORY_FAMILY),
        "seed": SEED,
        "label": UNIVERSE_LABEL,
    }


def evaluate_frozen(
    population: P4Population,
    vintage: VintageLoad,
    levels: Mapping[str, Optional[Levels]],
) -> Tuple[Dict[str, ManagedEvent], Dict[str, PotentialEvent], Tuple[str, ...]]:
    """Desenlaces administrado y potencial de unos niveles ya congelados, sin recalcularlos.

    Es la misma evaluación que hacen el event study y `replay_managed_population`
    (`evaluate_managed_event` y `evaluate_potential_event` desde el cierre de t,
    con `MAX_HOLD_BARS` y el coste pre-registrado); solo cambia que los niveles
    llegan fijados desde antes de la marca.
    """

    managed: Dict[str, ManagedEvent] = {}
    potential: Dict[str, PotentialEvent] = {}
    without_levels: List[str] = []
    for signal in population.signals:
        current = levels[signal.signal_id]
        if current is None:
            without_levels.append(signal.signal_id)
            continue
        obs = signal.observation
        df = vintage.by_symbol[obs.asset].execution_prices
        managed[signal.signal_id] = event_study.evaluate_managed_event(obs, df, obs.signal_idx, current, MAX_HOLD_BARS, COST_PCT)
        potential[signal.signal_id] = event_study.evaluate_potential_event(obs, df, obs.signal_idx, current, MAX_HOLD_BARS)
    return managed, potential, tuple(without_levels)


def execute_with_outcomes(
    vintage: VintageLoad,
    ident: P4Identity,
    preflight: Mapping[str, Any],
    frozen: FrozenRun,
) -> Tuple[int, Dict[str, Any]]:
    """Abre desenlaces y analiza. Solo la llama `run_confirmatory`, después de la marca.

    No recibe configuración ni universo: la población, los niveles y los cortes
    son los congelados sin desenlaces, y aquí no se vuelven a construir.
    """

    population = frozen.population
    levels = frozen.levels
    cuts = frozen.cuts
    stop = {"identidad": ident.as_dict(), "label": UNIVERSE_LABEL}
    for gid, values in levels.items():
        if levels_sha256(values) != preflight["niveles_sha256"][gid]:
            return 3, {**stop, "motivo": f"los niveles congelados de {gid} no coinciden con el preflight"}

    # Brazo A de E1 y control de todas las comparaciones: el ManagedEvent de C0. Sus niveles
    # son los de la enumeración del event study (control del preflight con 0 diferencias).
    control, control_potentials, c0_missing = evaluate_frozen(population, vintage, levels[C0.gid])
    if c0_missing:
        return 3, {**stop, "motivo": f"C0 sin niveles en {len(c0_missing)} señales"}
    enumerated = population.enumerated_levels
    if any(levels[C0.gid][sid] != enumerated[sid] for sid in control):
        return 3, {**stop, "motivo": "los niveles de C0 no son los de la enumeración del event study"}

    outputs: Dict[str, Any] = {}
    for geometry in VARIANTS:
        events, potentials, without_levels = evaluate_frozen(population, vintage, levels[geometry.gid])
        outputs[geometry.gid] = analyze_variant(
            geometry,
            population,
            control,
            events,
            without_levels,
            potentials,
            control_potentials,
            cuts,
            levels[C0.gid],
            levels[geometry.gid],
        )

    e1_outcomes: Dict[str, E1Outcome] = {}
    for signal in population.signals:
        obs = signal.observation
        current = levels[C0.gid][signal.signal_id]
        assert current is not None
        e1_outcomes[signal.signal_id] = simulate_e1_open_entry(
            obs,
            vintage.by_symbol[obs.asset].execution_prices,
            current,
            max_hold_bars=MAX_HOLD_BARS,
            cost_pct=COST_PCT,
            min_rr=C0.min_rr,
        )
    outputs[E1_ID] = analyze_e1(population, control, e1_outcomes)
    return 0, assemble_result(ident, preflight, outputs)


def assemble_result(ident: P4Identity, preflight: Mapping[str, Any], outputs: Mapping[str, Any]) -> Dict[str, Any]:
    """Criterio, lecturas y recuento derivado a partir de las salidas ya calculadas."""

    verdicts = [
        evaluate_candidate(
            candidate_evidence(
                gid,
                outputs[gid],
                preflight["niveles"][gid],
                preflight["holgura_d06"][gid]["GLOBAL"]["categoria_open_t1_fraccion"],
            )
        )
        for gid in CANDIDATE_IDS
    ]
    passing = candidates_for_p5(verdicts)
    derived = derived_comparisons(outputs)
    planned = preflight["recuento"]
    return {
        "fase": "confirmatoria",
        "identidad": ident.as_dict(),
        "outcomes_read": True,
        "preflight": preflight_fingerprint(preflight),
        "salidas": outputs,
        "criterio": [verdict_dict(v) for v in verdicts],
        "candidatas_p5": list(passing),
        "conclusion": "C0 permanece" if not passing else f"pasan a P5: {', '.join(passing)}",
        "b1": {"etiqueta": B1_LABEL, "en_familia": False, "candidata": False},
        "e1": {"lectura": outputs[E1_ID]["lectura"], "candidata": False},
        "recuento_derivado": derived,
        "recuento_previsto": planned,
        "recuento_coincide": derived["total"] == planned["total"],
        "label": UNIVERSE_LABEL,
    }


# ---------------------------------------------------------------------------
# Tablas TSV y resúmenes legibles.
# ---------------------------------------------------------------------------


def _cell(value: Any) -> str:
    if value is None:
        return "N/D"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _tsv(path: Path, header: Sequence[str], rows: Iterable[Sequence[Any]], ident: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# p4_prereg_sha={ident['p4_prereg_sha']} p4_executor_sha={ident['p4_executor_sha']} "
        f"data_vintage_id={ident['data_vintage_id']} universe_vintage_id={ident['universe_vintage_id']} "
        f"config_hash={ident['config_hash']} cost_pct={ident['cost_pct']} seed={ident['seed']}",
        f"# {UNIVERSE_LABEL}",
        "\t".join(header),
    ]
    lines.extend("\t".join(_cell(value) for value in row) for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


ESTIMATE_COLUMNS = (
    "papel", "n_pares", "n_bloques", "min_pares_bloque", "media_delta_r", "media_agrupada_delta_r",
    "ic_inferior", "ic_superior", "ic_nivel", "remuestreos", "heterogeneidad", "tau", "exceedance",
)


def _estimate_rows(gid: str, estimates: Mapping[str, Any]) -> List[List[Any]]:
    rows: List[List[Any]] = []
    for key, value in estimates.items():
        if _is_estimate(value) and "media_delta_r" in value:
            rows.append([gid, key, "", *[value.get(c) for c in ESTIMATE_COLUMNS]])
        elif not _is_estimate(value):
            for sub, item in value.items():
                if _is_estimate(item):
                    rows.append([gid, key, sub, *[item.get(c) for c in ESTIMATE_COLUMNS]])
    return rows


def write_tables(directory: Path, result: Mapping[str, Any]) -> None:
    ident = result["identidad"]
    outputs = result["salidas"]
    rows: List[List[Any]] = []
    for gid in (*(g.gid for g in VARIANTS), E1_ID):
        rows.extend(_estimate_rows(gid, outputs[gid]["estimaciones"]))
    _tsv(directory / "estimaciones.tsv", ("comparacion", "estimacion", "estrato", *ESTIMATE_COLUMNS), rows, ident)
    _tsv(
        directory / "nivel.tsv",
        ("geometria", "n", "n_bloques", "media_net_r", "ic_inferior", "ic_superior", "profit_factor_agrupado"),
        [
            [gid, *[outputs[gid]["estimaciones"]["nivel"].get(c) for c in ("n", "n_bloques", "media_net_r", "ic_inferior", "ic_superior", "profit_factor_agrupado")]]
            for gid in (g.gid for g in VARIANTS)
        ],
        ident,
    )
    _tsv(
        directory / "bloques-60.tsv",
        ("geometria", "bloque", "n", "media_delta_r"),
        [[gid, b["bloque"], b["n"], b["media_delta_r"]] for gid in (g.gid for g in VARIANTS) for b in outputs[gid]["medias_por_bloque_60"]],
        ident,
    )
    _tsv(
        directory / "emparejamiento.tsv",
        ("comparacion", "clave", "valor"),
        [[gid, k, v] for gid in (*(g.gid for g in VARIANTS), E1_ID) for k, v in outputs[gid]["emparejamiento"].items()],
        ident,
    )
    _tsv(
        directory / "capacidad.tsv",
        ("comparacion", "ok", "motivos", "bloques_con_pares", "min_pares_bloque", "tasa_descarte", "exit_final_c", "exit_final_v", "anchura_ic95"),
        [
            [gid, c["ok"], "; ".join(c["motivos"]), c["bloques_con_pares"], c["min_pares_bloque"], c["tasa_descarte_ambiguedad"],
             c["exit_final_control"], c["exit_final_variante"], c["anchura_ic95"]]
            for gid in (*(g.gid for g in VARIANTS), E1_ID)
            for c in (outputs[gid]["capacidad"],)
        ],
        ident,
    )
    _tsv(
        directory / "criterio.tsv",
        ("geometria", "condicion", "texto", "veta", "cumple", "detalle"),
        [[v["geometria"], c["n"], c["condicion"], c["veta"], c["cumple"], c["detalle"]] for v in result["criterio"] for c in v["condiciones"]],
        ident,
    )
    _tsv(
        directory / "e1-categorias.tsv",
        ("categoria", "n"),
        list(outputs[E1_ID]["categorias_open_t1"].items()),
        ident,
    )
    _tsv(
        directory / "recuento.tsv",
        ("comparacion", "componente", "derivado", "previsto"),
        [
            [gid, key, value, result["recuento_previsto"]["componentes"].get(gid, {}).get(key)]
            for gid, components in result["recuento_derivado"]["componentes"].items()
            for key, value in components.items()
        ],
        ident,
    )


def _f(value: Any, digits: int = 4) -> str:
    if value is None:
        return "N/D"
    if isinstance(value, float):
        if math.isinf(value):
            return "inf"
        return f"{value:.{digits}f}"
    return str(value)


def format_preflight(report: Mapping[str, Any]) -> str:
    ident = report["identidad"]
    population = report["poblacion"]
    lines = [
        f"# P4 — preflight sin desenlaces ({report['modo']})",
        "",
        f"_{UNIVERSE_LABEL}_",
        "",
        f"P4_PREREG_SHA={ident['p4_prereg_sha']}",
        f"P4_EXECUTOR_SHA={ident['p4_executor_sha']} (git_dirty={ident['git_dirty']}; prereg en historia={ident['prereg_en_historia']})",
        f"data_vintage_id={ident['data_vintage_id']}",
        f"universe_vintage_id={ident['universe_vintage_id']}",
        f"config_hash={ident['config_hash']}; config score_model_version={ident['config_score_model_version']}",
        f"coste={ident['cost_pct']}%; semilla={ident['seed']}; estándar {ident['standard']}; Bonferroni {ident['bonferroni']}",
        f"outcomes_read={report['outcomes_read']}; p4_confirmatory_executed={report['p4_confirmatory_executed']}",
        "",
        "## Población (A-02 swing sin cripto; sin exclusiones de P3)",
        f"A-02 swing {population['a02_swing']} − cripto {population['cripto_excluido']} {population['cripto_activos']} "
        f"= {population['p4']} señales, {population['activos']} activos",
        f"p4_population_sha256={population['p4_population_sha256']}",
        f"signal_ids_sha256={population['signal_ids_sha256']}",
        f"regiones={population['regiones']}",
        f"régimen PIT (solo estratos)={report['contexto_pit']['regimen']}; códigos={report['contexto_pit']['no_calculable_por_codigo']}",
        "",
        "## Bloques",
    ]
    for length, summary in report["bloques"].items():
        lines.append(
            f"{length:>4}: ocupados {summary['bloques_ocupados']} {summary.get('primer_y_ultimo_ocupado')}, "
            f"más corto {summary['bloque_ocupado_mas_corto']}, válida={summary['valida_P2_5']} → {summary.get('papel')}"
        )
    if "rejilla" in report:
        lines.extend(["", "## Rejilla y álgebra (stop por volatilidad)"])
        for gid, row in report["rejilla"].items():
            alg = report["algebra"][gid]["formula"]
            lines.append(
                f"{gid}: s={row['atr_stop_multiple']} m={row['target_atr_multiples']} rol={row['rol']} "
                f"confirmatory={row['confirmatory']} eligible_for_p5={row['eligible_for_p5']} bonferroni={row['bonferroni']} | "
                f"RR en P {_f(alg['rr_en_p'])}, holgura RR {_f(alg['holgura_rr_atr'])}·A, efectiva {_f(alg['holgura_efectiva_atr'])}·A"
                + (f" | «{row['etiqueta']}»" if row["etiqueta"] else "")
            )
        lines.extend(["", "## Niveles reales (sin desenlaces)"])
        for gid, row in report["niveles"].items():
            lines.append(
                f"{gid}: válidos {row['validos']}, None {row['none']} {row['none_por_motivo']}, stop_basis {row['stop_basis']}, "
                f"pares stop_basis {row['stop_basis_pares_c0_variante']}, RR<min {row['rr_efectivo_bajo_min_rr']}, "
                f"incoherentes {row['incoherentes']} {row['incoherencias_por_tipo']}, entry_max vs C0 {row['entry_max_frente_a_c0']}"
            )
        lines.extend(["", "## Holgura D-06 y categorías a open(t+1) (global; sin IC, no son comparaciones)"])
        for gid, groups in report["holgura_d06"].items():
            g = groups["GLOBAL"]
            lines.append(
                f"{gid}: holgura RR p50 {_f(g['holgura']['rr_atr'].get('p50'))}·A ({_f(g['holgura']['rr_pct'].get('p50'))} %), "
                f"efectiva p50 {_f(g['holgura']['efectiva_atr'].get('p50'))}·A; manda {g['manda']}; "
                f"open(t+1) {g['categoria_open_t1']}; distancia ABOVE_MAX_ENTRY {g['distancia_above_max_entry_atr']}"
            )
        vol = report["volatilidad"]
        lines.extend(
            [
                "",
                "## Estratos",
                f"terciles ATR/P: cortes {vol['cortes_atr_sobre_precio']} ({vol['metodo']}); n {vol['n_por_tercil']}",
            ]
        )
        for gid, strata in report["estratos"].items():
            lines.append(
                f"{gid}: regiones {len(strata['regiones'])}, regímenes {strata['regimenes']}, terciles {strata['terciles']}, "
                f"activos {len(strata['activos'])}, stop_basis {strata['stop_basis']}, {strata['no_calculable_context_contado']}"
            )
        family = report["familia_confirmatoria"]
        count = report["recuento"]
        lines.extend(
            [
                "",
                f"## Familia confirmatoria: {family['miembros']} (m={family['m']}, {family['confidence']}, {family['remuestreos']} remuestreos); "
                f"fuera: {family['fuera_de_la_familia']}",
                f"## Recuento estructural: {count['subtotales']} → total {count['total']}, confirmatorias {count['confirmatorias']}",
                f"Mitades: {report['bloques_mitades']}",
            ]
        )
    failed = [c for c in report["checks"] if not c["ok"]]
    lines.extend(["", f"## Controles: {len(report['checks']) - len(failed)}/{len(report['checks'])} correctos"])
    for check in failed:
        lines.append(f"FALLA {check['control']}: observado {check['observado']} ≠ esperado {check['esperado']}")
    if "abortado" in report:
        lines.append(f"ABORTADO: {report['abortado']}")
    lines.append(f"ok={report['ok']}; definitivo={report.get('definitivo')}")
    return "\n".join(lines) + "\n"


def format_result(result: Mapping[str, Any]) -> str:
    outputs = result["salidas"]
    lines = [
        "# P4 — resultado de la ejecución confirmatoria única",
        "",
        f"_{UNIVERSE_LABEL}_",
        "",
        f"P4_PREREG_SHA={result['identidad']['p4_prereg_sha']}; P4_EXECUTOR_SHA={result['identidad']['p4_executor_sha']}",
        "",
        "## Comparaciones",
    ]
    for gid in (*(g.gid for g in VARIANTS), E1_ID):
        out = outputs[gid]
        primary = out["estimaciones"].get("primaria_60")
        if primary is None:
            lines.append(f"{comparison_id(gid)}: sin estimación primaria")
            continue
        lines.append(
            f"{comparison_id(gid)}: ΔR {_f(primary['media_delta_r'])} [{_f(primary['ic_inferior'])}, {_f(primary['ic_superior'])}] "
            f"(IC {primary['ic_nivel']}, {primary['remuestreos']} remuestreos); pares {out['emparejamiento']['pares_finales']}; "
            f"heterogeneidad {primary['heterogeneidad']} (bandera, no veta); capacidad {out['capacidad']['ok']}"
            + (f" — «{out['etiqueta']}»" if out.get("etiqueta") else "")
        )
    lines.extend(["", "## Criterio (solo B2, S1, S2)"])
    for verdict in result["criterio"]:
        failed = [c["n"] for c in verdict["condiciones"] if c["veta"] and not c["cumple"]]
        lines.append(f"{verdict['geometria']}: {'PASA a P5' if verdict['pasa_a_p5'] else 'no pasa'}; condiciones que fallan {failed}")
    lines.extend(
        [
            "",
            f"**{result['conclusion']}**",
            f"E1: {result['e1']['lectura']} (no es candidata)",
            f"B1: {B1_LABEL}",
            f"Recuento derivado: {result['recuento_derivado']['total']} (previsto {result['recuento_previsto']['total']}); "
            f"confirmatorias {result['recuento_derivado']['confirmatorias']}",
        ]
    )
    return "\n".join(lines) + "\n"


def development_mode() -> bool:
    return os.environ.get(DEVELOPMENT_ENV) == "1"
