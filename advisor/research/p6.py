"""Ejecutor único de P6 (T-022 / A-06): B2 y S2 como sistemas completos de cartera.

La especificación es ``docs/tareas/T-022-p6-sistema-completo.md`` y D-69, con sus precisiones
ratificadas. Este módulo contiene:

- las identidades congeladas (``P6_PREREG_SHA``, ``P6_DATA_ID``, FX, sector, políticas);
- la guarda de desenlaces: ``ConfirmatoryToken`` ligado a la marca exclusiva
  ``EJECUCION_CONFIRMATORIA_P6_INICIADA``; sin token no se cargan precios reales, no se generan
  señales reales y el motor (``p6_sim``) se niega a simular datos reales;
- la carga estructural (FX congelado, mapa sectorial, calendario, ventana) y ``system_sha256``;
- el preflight, que **no abre ningún desenlace** ni carga la cosecha de precios: solo fechas y acciones
  corporativas verificadas y, para la coherencia dividendo/split (T-022 §10.1), ``Close``/``Adj Close``
  en la víspera y la fecha ex de los activos afectados;
- la ejecución confirmatoria única, implementada pero que solo se lanza con autorización expresa.

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._
"""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import os
import secrets
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, FrozenSet, List, Mapping, NoReturn, Optional, Sequence, Tuple, cast
from zoneinfo import ZoneInfo

import pandas as pd

from advisor.analysis.benchmark import resolve_benchmark_symbol
from advisor.analysis.levels import compute_levels
from advisor.analysis.opportunity import ACCION_COMPRAR, RADAR_OPERAR
from advisor.analysis.snapshot import build_snapshot_series, snapshot_from_series
from advisor.backtest.engine import _signal
from advisor.config import AdvisorConfig
from advisor.context.point_in_time import PointInTimeContextResolver, analysis_timestamp_for_signal
from advisor.data.calendars import exchange_calendar, expected_sessions
from advisor.data.freshness import mercado_para_simbolo
from advisor.data.sessions import market_for_symbol, market_session, session_close_at
from advisor.research.observations import stable_signal_id
from advisor.research.p3 import utc_now, write_json
from advisor.research.p4 import _context_resolver, executor_unchanged_since, run_git, tree_dirty
from advisor.research.p6_sim import (
    ORIGIN_REAL,
    AssetSeries,
    FxTable,
    MarketData,
    P6OutcomeGateError,
    Signal,
    SimSpec,
    canonical_json,
    cash_occupancy,
    criterion,
    equity_series,
    excess,
    exposure_metrics,
    ledger_csv,
    path_metrics,
    series_csv,
    simulate,
    simulate_benchmark,
    subperiods,
    survivors,
    trade_metrics,
    trades_csv,
    turnover,
)
from advisor.research.vintage import (
    VintageLoad,
    VintageStructure,
    load_vintage_structure,
)
from advisor.run.git import git_sha
from advisor.run.manifest import config_hash
from advisor.universe.models import Universe

P6_PREREG_SHA = "03f04a42ea9d2be893e7c4cc09de76bd1c55778b"
P6_DATA_ID = "572e09141dbfe0fc9c53a7b529f1abcff46e16027fe9b47d1f3e26330c1e5383"
DATA_VINTAGE_ID = "071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841"
UNIVERSE_VINTAGE_ID = "237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19"
FX_VINTAGE_ID = "10e832ef38daa5d7e81a444bcd3bc99a5e783a382a14a4a14c68e6736dfeac0b"
SECTOR_MAP_SHA256 = "24f45421a582cc79ee16f8436e3e008d252ccafc06f34503961d5dfccea662cd"
ASSET_LIST_SHA256 = "36355796a57e55a68ea16957b7edc6975360fb2085e7fd91841d20e2d7812f50"
EXCHANGE_OVERRIDES_SHA256 = "87e4aa21def5eaf057745cf4b98711c4df694dae2f6cfbf27245823d946539db"
EXCHANGE_CALENDARS_VERSION = "4.13.2"
TZDATA_VERSION = "2026.4"
EXPECTED_CONFIG_HASH = "89406d28c7b4b6e6c4f032cd63b6868c927af3e926dfb52d430dfa6654d06387"

POLICY_HASHES = {
    "B2": ("d5d6a533fe846a6ebb5d5c8e313c84f2a5b4e04095d08386e5d903dce73101b9",
           "c5d60f44e89a754f34dfc685cda5073af1c0f9dbb04ab3ec14a813d423f81760"),
    "S2": ("e37ee93363dbbd7c58cae74bba4391ab9ad41dd1f3ed55804a92efb531e44d11",
           "8a151b80d91bf73e431ec38e5e21f22268783bbd0a26d5f72e6ef8887aca0dbb"),
    "C0": ("80e21111a88c1eeac94c2ecef6b8bc480a505a045ca90f6a91a0ba6fc4ffd29a",
           "89406d28c7b4b6e6c4f032cd63b6868c927af3e926dfb52d430dfa6654d06387"),
}
CANDIDATES = ("B2", "S2")
CONTROL = "C0"

CONFIG_PATH = Path("config.yaml")
DATA_DIR = Path("evidence/2026-10-03-T-022-p6-datos")
CENSUS = Path("evidence/2026-10-03-T-022-p6-diseno/censo-p6.json")
PREFLIGHT_DIR = Path("evidence/2026-10-03-T-022-p6/preflight")
RUN_DIR = Path("evidence/2026-10-03-T-022-p6/run")
RUN_MARKER = "EJECUCION_CONFIRMATORIA_P6_INICIADA"
RUN_PAYLOAD = "apertura-payload.json"
BENCHMARK_POPULATION = "benchmark_pesos_iguales"
DEVELOPMENT_ENV = "INTRADIA_P6_PREFLIGHT_DESARROLLO"

HORIZONTE = "swing"
WARMUP_BARS = 120
TREND_SMA = 200
CAPITAL = 100_000.0
SLIPPAGE_PRIMARY_BPS = 5.0
SLIPPAGE_SENSITIVITY_BPS = 10.0
POPULATION_OPERAR = "OPERAR_score_v1_point_in_time"
POPULATION_ALL_BARS = "todas_las_barras_elegibles"
UNIVERSE_LABEL = "condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)"


class P6PreflightError(RuntimeError):
    """Una identidad del pre-registro no se reproduce: P6 no se ejecuta."""


class P6AlreadyExecutedError(RuntimeError):
    """La ejecución confirmatoria de P6 ya se inició una vez: no se repite."""


# ---------------------------------------------------------------------------
# Guarda de desenlaces: marca exclusiva y token.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfirmatoryToken:
    marker_path: Path
    marker_payload_sha256: str
    nonce: str = ""


# Token vigente: solo existe mientras corre _ejecutar_confirmatoria_sellada, que lo crea tras escribir
# y verificar la marca y lo revoca en un finally (también si falla). No hay registro de tokens emitidos
# ni piezas sueltas (autorización, marca, token) que un llamador pueda encadenar o reutilizar después.
_ACTIVE_TOKEN: Optional[ConfirmatoryToken] = None


def _deny(reason: str) -> NoReturn:
    raise P6OutcomeGateError(f"autorización denegada: {reason}")


def _frozen_identity_mismatches(report: Mapping[str, Any]) -> List[str]:
    """Campos del preflight guardado que no reproducen las identidades congeladas."""

    identity = cast(Mapping[str, Any], report.get("identidad") or {})
    expected = {
        "p6_prereg_sha": P6_PREREG_SHA,
        "p6_data_id": P6_DATA_ID,
        "data_vintage_id": DATA_VINTAGE_ID,
        "universe_vintage_id": UNIVERSE_VINTAGE_ID,
        "fx_vintage_id": FX_VINTAGE_ID,
        "sector_map": SECTOR_MAP_SHA256,
        "prereg_en_historia": True,
        "git_dirty": False,
    }
    wrong = [f"identidad.{key}" for key, value in expected.items() if identity.get(key) != value]
    policies = cast(Mapping[str, Any], report.get("politicas") or {})
    for policy, (policy_hash, cfg_hash) in POLICY_HASHES.items():
        record = cast(Mapping[str, Any], policies.get(policy) or {})
        if record.get("policy_sha256") != policy_hash or record.get("advisor_config_hash") != cfg_hash:
            wrong.append(f"politicas.{policy}")
    if not isinstance(identity.get("p6_executor_sha"), str) or not identity.get("p6_executor_sha"):
        wrong.append("identidad.p6_executor_sha")
    return wrong


def _sources() -> Tuple[AdvisorConfig, Universe]:
    """Configuración y universo canónicos, cargados desde el repositorio (no del llamador)."""

    from advisor.config import load_config
    from advisor.universe.loader import load_universe

    config = load_config(CONFIG_PATH)
    return config, load_universe(config.universe_path)


def _live_preflight(config: AdvisorConfig, universe: Universe) -> Tuple[bool, Dict[str, Any]]:
    """Preflight vivo recalculado con la función canónica, sobre la cosecha estructural."""

    return run_preflight(config, universe, load_structure(), current_identity(config), write=False,
                         determinism=synthetic_determinism())


def _verified_authorization() -> Tuple[AdvisorConfig, Universe, Dict[str, Any], Dict[str, Any]]:
    """Precondiciones de la ejecución confirmatoria, reconstruidas desde las fuentes de verdad.

    No recibe nada del llamador y no emite nada: devolver sin error no autoriza a crear la marca, que
    solo crea _ejecutar_confirmatoria_sellada.
    """

    stored_path = PREFLIGHT_DIR / "p6-preflight.json"
    if not stored_path.is_file():
        _deny(f"no existe el preflight definitivo ({stored_path})")
    try:
        stored = json.loads(stored_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _deny(f"preflight definitivo ilegible: {exc}")
    if not isinstance(stored, dict):
        _deny("preflight definitivo con formato inválido")
    if stored.get("ok") is not True:
        _deny("el preflight definitivo no es correcto (ok != true)")
    if stored.get("definitivo") is not True:
        _deny("el preflight guardado no es definitivo")
    wrong = _frozen_identity_mismatches(stored)
    if wrong:
        _deny(f"el preflight definitivo no reproduce las identidades congeladas: {wrong}")
    if p6_data_id() != P6_DATA_ID:
        _deny("P6_DATA_ID no se reproduce en este entorno")
    if not executor_unchanged_since(str(stored["identidad"]["p6_executor_sha"]), "."):
        _deny("el ejecutor cambió desde el preflight definitivo")
    config, universe = _sources()
    live_ok, live = _live_preflight(config, universe)
    if not (live_ok and live.get("ok") is True and live.get("definitivo") is True):
        _deny("el preflight recalculado no es correcto y definitivo")
    if canonical_json(preflight_fingerprint(live)) != canonical_json(preflight_fingerprint(stored)):
        _deny("el preflight recalculado no coincide con el definitivo guardado")
    if (RUN_DIR / RUN_MARKER).exists():
        raise P6AlreadyExecutedError(f"la ejecución confirmatoria de P6 ya se inició ({RUN_DIR / RUN_MARKER}); no se repite")
    return config, universe, stored, live


def require_token(token: Optional[ConfirmatoryToken]) -> ConfirmatoryToken:
    if token is None:
        raise P6OutcomeGateError("P6: abrir desenlaces exige ConfirmatoryToken")
    if _ACTIVE_TOKEN is None or token != _ACTIVE_TOKEN:
        raise P6OutcomeGateError("ConfirmatoryToken no vigente: solo vale durante la ejecución confirmatoria sellada")
    expected = (RUN_DIR / RUN_MARKER).resolve()
    if token.marker_path.resolve() != expected:
        raise P6OutcomeGateError("ConfirmatoryToken apunta a una marca que no es la de P6")
    if not token.marker_path.is_file():
        raise P6OutcomeGateError("ConfirmatoryToken sin marca en disco")
    if hashlib.sha256(token.marker_path.read_bytes()).hexdigest() != token.marker_payload_sha256:
        raise P6OutcomeGateError("ConfirmatoryToken no coincide con la marca en disco")
    return token


# ---------------------------------------------------------------------------
# Identidades estructurales.
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def asset_list() -> List[str]:
    data = json.loads(CENSUS.read_text(encoding="utf-8"))
    symbols = sorted(row["asset"] for row in data["activos"])
    digest = hashlib.sha256("\n".join(symbols).encode("utf-8")).hexdigest()
    if digest != ASSET_LIST_SHA256:
        raise P6PreflightError(f"asset_list_sha256 {digest} distinto del congelado")
    return symbols


def policy_cells() -> Dict[str, Any]:
    from advisor.research import p5  # local: p6 no reexporta el módulo de P5

    return {"B2": p5.B2_CELL, "S2": p5.S2_CELL, "C0": p5.C0_CELL}


def policy_identities(config: AdvisorConfig) -> Dict[str, Dict[str, str]]:
    from advisor.research import p5

    out = {}
    for policy, cell in policy_cells().items():
        out[policy] = {
            "policy_sha256": p5.policy_sha256(config, cell),
            "advisor_config_hash": p5.advisor_config_hash(config, cell),
        }
    return out


def policy_config(config: AdvisorConfig, policy: str) -> AdvisorConfig:
    cell = policy_cells()[policy]
    return config.model_copy(update={"levels": cell.levels_config(config.levels)})


def load_fx() -> Tuple[FxTable, Dict[str, Any]]:
    manifest = json.loads((DATA_DIR / "fx" / "fx-manifest.json").read_text(encoding="utf-8"))
    sidecar = DATA_DIR / "fx" / "fx-sidecar.csv"
    if manifest.get("fx_vintage_id") != FX_VINTAGE_ID:
        raise P6PreflightError("fx_vintage_id del manifiesto distinto del congelado")
    if sha256_file(sidecar) != manifest["fx_sidecar_csv_sha256"]:
        raise P6PreflightError("fx-sidecar.csv no coincide con su sha256 congelado")
    recomputed = hashlib.sha256(
        canonical_json(
            {
                "fuente_usada": manifest["fuente_usada"],
                "series_fx": manifest["series_fx"],
                "fx_sidecar_csv_sha256": manifest["fx_sidecar_csv_sha256"],
            }
        ).encode("utf-8")
    ).hexdigest()
    if recomputed != FX_VINTAGE_ID:
        raise P6PreflightError("fx_vintage_id no se reproduce desde el manifiesto")
    series: Dict[str, List[Tuple[datetime, float]]] = {}
    with sidecar.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            currency = row["fx_pair"].replace("EUR", "", 1)
            available = datetime.strptime(row["timestamp_available"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            series.setdefault(currency, []).append((available, float(row["rate"])))
    return FxTable(series), {"fuente_usada": manifest["fuente_usada"], "pares": sorted(series)}


def load_sector_map() -> Dict[str, str]:
    document = json.loads((DATA_DIR / "p6-sector-map.json").read_text(encoding="utf-8"))
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != SECTOR_MAP_SHA256:
        raise P6PreflightError("el mapa sectorial no reproduce su sha256 congelado")
    return {entry["asset"]: entry["sector"] for entry in document["instrumentos"]}


def p6_data_id_payload() -> Dict[str, Any]:
    return {
        "market_data_vintage": DATA_VINTAGE_ID,
        "universe_vintage": UNIVERSE_VINTAGE_ID,
        "fx_vintage": FX_VINTAGE_ID,
        "sector_map": SECTOR_MAP_SHA256,
        "calendar": {
            "exchange_calendars": importlib.metadata.version("exchange_calendars"),
            "exchange_overrides_sha256": sha256_file(Path("exchange_overrides.yaml")),
            "tzdata": importlib.metadata.version("tzdata"),
        },
        "asset_list": ASSET_LIST_SHA256,
    }


def p6_data_id() -> str:
    canonical = json.dumps(p6_data_id_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Calendario y ventana (estructurales: solo fechas, nunca precios).
# ---------------------------------------------------------------------------


def _local_dates(index: pd.Index, tz: str) -> List[date]:
    stamps = pd.DatetimeIndex(pd.to_datetime(index, utc=True, format="mixed"))
    return [stamp.date() for stamp in stamps.tz_convert(ZoneInfo(tz))]


def bar_times(market: str, sessions: Sequence[date]) -> Tuple[Tuple[datetime, ...], Tuple[datetime, ...]]:
    """Aperturas y cierres reales en UTC del calendario efectivo para cada fecha de sesión con barra."""

    calendar = cast(Any, exchange_calendar(market))
    opens: List[datetime] = []
    closes: List[datetime] = []
    for day in sessions:
        opened = calendar.session_open(pd.Timestamp(day)).to_pydatetime()
        if opened.tzinfo is None:
            opened = opened.replace(tzinfo=timezone.utc)
        closed = session_close_at(market, day)
        if closed is None:
            raise P6PreflightError(f"{market} {day}: sin cierre de calendario")
        opens.append(opened.astimezone(timezone.utc))
        closes.append(closed.astimezone(timezone.utc))
    return tuple(opens), tuple(closes)


@dataclass(frozen=True)
class Window:
    start: date
    end: date
    warmup_last_initial: date
    sma_complete_session: date
    sessions_without_bar: int
    snapshot_days: int
    periods_per_year: float

    def as_dict(self) -> Dict[str, Any]:
        return {
            "inicio": self.start.isoformat(),
            "fin": self.end.isoformat(),
            "ultimo_calentamiento_de_los_iniciales": self.warmup_last_initial.isoformat(),
            "sesion_que_completa_la_sma200": self.sma_complete_session.isoformat(),
            "sesiones_sin_barra_en_ventana": self.sessions_without_bar,
            "instantaneas": self.snapshot_days,
            "periodos_por_año": self.periods_per_year,
        }


def structure_index(structure: VintageStructure) -> Dict[str, pd.Index]:
    return {symbol: frame.index for symbol, frame in structure.by_symbol.items()}


def vintage_index(vintage: VintageLoad) -> Dict[str, pd.Index]:
    return {symbol: views.execution_prices.index for symbol, views in vintage.by_symbol.items()}


def load_structure() -> VintageStructure:
    return load_vintage_structure(DATA_VINTAGE_ID)


def derive_window(config: AdvisorConfig, universe: Universe, index: Mapping[str, pd.Index]) -> Window:
    """Regla de T-022 §7.9 (D-69 punto 13), solo con fechas de sesión (``index``: timestamps por símbolo)."""

    symbols = asset_list()
    dates: Dict[str, List[date]] = {}
    markets: Dict[str, str] = {}
    for symbol in symbols:
        asset = universe.get(symbol)
        if asset is None:
            raise P6PreflightError(f"{symbol} ausente del universo")
        dates[symbol] = _local_dates(index[symbol], asset.timezone)
        markets[symbol] = mercado_para_simbolo(asset, symbol)
    first = min(days[0] for days in dates.values())
    initial = [symbol for symbol, days in dates.items() if days[0] == first]
    warmup_last = max(dates[symbol][WARMUP_BARS] for symbol in initial)
    trend_symbol = config.market_context.trend_symbol
    trend_market = market_for_symbol(trend_symbol)
    trend_dates = _local_dates(index[trend_symbol], market_session(trend_market).timezone)
    sma_session = trend_dates[TREND_SMA - 1]
    sma_available = session_close_at(trend_market, sma_session)
    if sma_available is None:
        raise P6PreflightError("sin cierre para la sesión que completa la SMA200")
    sma_available = sma_available + timedelta(minutes=config.data_quality.settlement_minutes)
    candidate = max(warmup_last + timedelta(days=1), sma_session + timedelta(days=1))
    all_days = sorted({day for days in dates.values() for day in days})
    start = next(day for day in all_days if day >= candidate)
    # Condición 2 comprobada señal a señal: la última sesión de cada activo antes del inicio tiene
    # su analysis_timestamp después de que la SMA200 esté disponible.
    for symbol in symbols:
        before = [day for day in dates[symbol] if day < start]
        after = [day for day in dates[symbol] if day >= start]
        if not before or not after or symbol not in initial:
            continue
        ts = analysis_timestamp_for_signal(markets[symbol], before[-1], after[0],
                                           settlement_minutes=config.data_quality.settlement_minutes)
        if ts is not None and ts < sma_available:
            raise P6PreflightError(f"{symbol}: la primera señal admitida no tiene la SMA200 causal")
    end = min(days[-1] for days in dates.values())
    missing = 0
    for symbol in symbols:
        # Desde la primera barra del activo: antes de cotizar (ARM, Q8Y0.DE) no hay «sesión sin barra».
        listed_from = max(start, dates[symbol][0])
        window_days = [day for day in dates[symbol] if listed_from <= day <= end]
        expected = expected_sessions(markets[symbol], listed_from, end)
        missing += len(set(expected) - set(window_days))
    snapshot_days = sorted({day for days in dates.values() for day in days if start <= day <= end})
    span = (snapshot_days[-1] - start).days
    ppy = len(snapshot_days) / (span / 365.25)
    return Window(start, end, warmup_last, sma_session, missing, len(snapshot_days), ppy)


# ---------------------------------------------------------------------------
# Identidad del sistema (T-022 §18).
# ---------------------------------------------------------------------------


def system_payload(config: AdvisorConfig, policy: str, population: str, slippage_bps: float, window: Window) -> Dict[str, Any]:
    identities = policy_identities(config)[policy]
    return {
        "esquema": "intradia.p6.system.v1",
        "policy_id": policy,
        "p5_policy_sha256": identities["policy_sha256"],
        "advisor_config_hash": identities["advisor_config_hash"],
        "score_model_version": "1.0",
        "poblacion_de_senales": population,
        "papel": "control_descriptivo" if policy == CONTROL else (
            "decisoria" if population == POPULATION_OPERAR and slippage_bps == SLIPPAGE_PRIMARY_BPS else "descriptiva"
        ),
        "capital_inicial": CAPITAL,
        "base_currency": config.base_currency,
        "risk_per_trade_pct": config.portfolio.risk_per_trade_pct,
        "max_position_pct": config.portfolio.max_position_pct,
        "modo_de_contexto": "point_in_time" if population == POPULATION_OPERAR else "sin_score",
        "predicado_OPERAR": "broker_neutral: setup_radar == OPERAR y setup_accion == COMPRAR",
        "estimador_decisorio": "mean_R_local = media simple de trade_R_local sobre las operaciones cerradas (excepción a INV-14)",
        "regla_analysis_timestamp": {
            "regla": "D-50: última pasada programada antes de la apertura de entrada",
            "pasadas": ["07:00", "08:30", "14:30", "21:00"],
            "dias": "lun-vie",
            "zona": "Europe/London",
            "settlement_minutes": config.data_quality.settlement_minutes,
        },
        "moneda_del_R_decisorio": "local",
        "fuente_fx": "B",
        "unidades": "fraccionarias",
        "base_del_sizing": "equity causal anterior al lote, una vez por lote",
        "regla_de_cash": "rechazar entera (INSUFFICIENT_CASH) si nominal efectivo + comisión > cash",
        "apalancamiento": 0,
        "limites_globales": "ninguno",
        "regla_mismo_activo": "una posición; IGNORED_ALREADY_OPEN contado",
        "semantica_de_entrada": "open de la barra siguiente; INVALID_STOP, INVALID_TARGET, ABOVE_MAX_ENTRY, RR_TOO_LOW, POSITION_TOO_SMALL, INSUFFICIENT_CASH con precio efectivo",
        "semantica_de_salida": "engine._check_exit: hueco stop, stop, hueco objetivo, objetivo; stop gana; tiempo 40 barras; EXIT_FINAL; target3 no sale",
        "cronologia": {
            "calendario": "exchange_calendars + exchange_overrides.yaml + tzdata",
            "fases": ["OPEN_EXIT", "OPEN_ENTRY", "CLOSE_EXIT", "CLOSE_DIVIDEND", "CLOSE_VALUATION", "SIGNAL"],
        },
        "desempate": "sha256(b'intradia.p6.desempate.v1' + signal_id.encode('utf-8')).hexdigest() ascendente",
        "liquidacion": "inmediata al materializar la salida",
        "modelo_de_costes": {"entrada_pct": 0.10, "salida_pct": 0.10, "sobre": "nominal ejecutado"},
        "modelo_de_slippage": {"pb_por_lado": slippage_bps},
        "modelo_de_dividendos": {"derecho": "abierta al cierre previo a la fecha ex", "abono": "cierre de la sesión ex", "fiscalidad": "bruto"},
        "fx": {"fx_vintage_id": FX_VINTAGE_ID, "regla": "último tipo con timestamp_available < τ; 1/rate", "caja": "única en EUR, sin coste FX"},
        "sector_map_sha256": SECTOR_MAP_SHA256,
        "calendario_de_valoracion": "ledger por eventos + instantánea 23:59:59 UTC de cada día con sesión",
        "periodos_por_año": window.periods_per_year,
        "ventana": {"inicio": window.start.isoformat(), "fin": window.end.isoformat()},
        "universo": {"asset_list_sha256": ASSET_LIST_SHA256},
        "contrato_del_benchmark": benchmark_contract(slippage_bps),
        "contrato_de_metricas": "T-022 §15 (rf = 0, MAR = 0, DD sobre la serie diaria con V_0)",
        "criterio_de_supervivencia": "N_closed >= 100; profit_factor_local > 1; mean_R_local > 0; max_drawdown >= -25 %; excess_CAGR_pp > 0",
        "data_vintage_id": DATA_VINTAGE_ID,
        "universe_vintage_id": UNIVERSE_VINTAGE_ID,
        "p6_data_id": P6_DATA_ID,
    }


def benchmark_contract(slippage_bps: float) -> Dict[str, Any]:
    return {
        "esquema": "intradia.p6.benchmark.v1",
        "universo": ASSET_LIST_SHA256,
        "ponderacion": "pesos iguales 1/90, comisión dentro del importe",
        "rebalanceo": "ninguno",
        "tardios": "1/90 en cash hasta la apertura de la barra siguiente a su barra 120",
        "dividendos": "reinvertidos en el mismo activo en la apertura siguiente; comisión dentro del dividendo",
        "costes_pct_por_lado": 0.10,
        "slippage_pb_por_lado": slippage_bps,
        "fx_vintage_id": FX_VINTAGE_ID,
    }


def benchmark_payload(slippage_bps: float, window: Window) -> Dict[str, Any]:
    return {
        "esquema": "intradia.p6.benchmark.v1",
        "contrato": benchmark_contract(slippage_bps),
        "capital_inicial": CAPITAL,
        "ventana": {"inicio": window.start.isoformat(), "fin": window.end.isoformat()},
        "periodos_por_año": window.periods_per_year,
        "p6_data_id": P6_DATA_ID,
    }


def sha256_payload(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


RUNS: Tuple[Tuple[str, str, str, float], ...] = (
    ("B2_primaria_5pb", "B2", POPULATION_OPERAR, SLIPPAGE_PRIMARY_BPS),
    ("B2_sensibilidad_10pb", "B2", POPULATION_OPERAR, SLIPPAGE_SENSITIVITY_BPS),
    ("B2_todas_las_barras_5pb", "B2", POPULATION_ALL_BARS, SLIPPAGE_PRIMARY_BPS),
    ("S2_primaria_5pb", "S2", POPULATION_OPERAR, SLIPPAGE_PRIMARY_BPS),
    ("S2_sensibilidad_10pb", "S2", POPULATION_OPERAR, SLIPPAGE_SENSITIVITY_BPS),
    ("S2_todas_las_barras_5pb", "S2", POPULATION_ALL_BARS, SLIPPAGE_PRIMARY_BPS),
    ("C0_primaria_5pb", "C0", POPULATION_OPERAR, SLIPPAGE_PRIMARY_BPS),
)
BENCHMARK_RUNS = (("benchmark_5pb", SLIPPAGE_PRIMARY_BPS), ("benchmark_10pb", SLIPPAGE_SENSITIVITY_BPS))


def system_hashes(config: AdvisorConfig, window: Window) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    for run_id, policy, population, slippage in RUNS:
        payload = system_payload(config, policy, population, slippage, window)
        out[run_id] = {"system_sha256": sha256_payload(payload), "policy": policy, "poblacion": population,
                       "slippage_pb": str(slippage), "papel": payload["papel"]}
    for run_id, slippage in BENCHMARK_RUNS:
        out[run_id] = {"benchmark_sha256": sha256_payload(benchmark_payload(slippage, window)), "slippage_pb": str(slippage)}
    return out


# ---------------------------------------------------------------------------
# Datos y señales reales: solo con token (abren desenlaces).
# ---------------------------------------------------------------------------


def build_real_market(
    token: ConfirmatoryToken,
    config: AdvisorConfig,
    universe: Universe,
    vintage: VintageLoad,
    window: Window,
    sectors: Mapping[str, str],
    contract: FrozenSet[SimSpec],
) -> MarketData:
    require_token(token)
    if len(contract) != len(RUNS) + len(BENCHMARK_RUNS):
        raise P6OutcomeGateError("P6: los datos reales exigen el contrato completo de corridas pre-registradas")
    assets: Dict[str, AssetSeries] = {}
    for symbol in asset_list():
        asset = universe.get(symbol)
        assert asset is not None
        views = vintage.by_symbol[symbol]
        prices = views.execution_prices
        market = mercado_para_simbolo(asset, symbol)
        sessions = _local_dates(prices.index, asset.timezone)
        opens, closes = bar_times(market, sessions)
        dividends = views.raw["Dividends"].astype(float).reindex(prices.index).fillna(0.0)
        assets[symbol] = AssetSeries(
            symbol=symbol, market=market, currency=asset.primary_currency or asset.currency,
            economic_currency=asset.economic_currency, region=asset.region, sector=sectors[symbol],
            session_dates=tuple(sessions), open_utc=opens, close_utc=closes,
            open=tuple(float(v) for v in prices["Open"]), high=tuple(float(v) for v in prices["High"]),
            low=tuple(float(v) for v in prices["Low"]), close=tuple(float(v) for v in prices["Close"]),
            dividends=tuple(float(v) for v in dividends), eligible_from=WARMUP_BARS + 1,
        )
    return MarketData(assets=assets, window_start=window.start, window_end=window.end, origin=ORIGIN_REAL,
                      contract=contract)


def build_real_signals(
    token: ConfirmatoryToken,
    config: AdvisorConfig,
    universe: Universe,
    vintage: VintageLoad,
    policy: str,
    population: str,
    window: Window,
) -> Tuple[List[Signal], Dict[str, int]]:
    """Señales reales de una política cuya entrada cae en la ventana: abre desenlaces, exige el token."""

    require_token(token)
    if (policy, population) not in {(p, pop) for _run, p, pop, _slip in RUNS}:
        raise P6OutcomeGateError(f"P6: señales reales solo para corridas pre-registradas, no {policy}/{population}")
    from advisor.research.vintage import frozen_close  # local, tras el token: p6 no expone accesores de precios

    cfg = policy_config(config, policy)
    resolver: PointInTimeContextResolver = _context_resolver(config, universe, vintage)
    window_cfg = config.horizonte(HORIZONTE)
    settlement = config.data_quality.settlement_minutes
    signals: List[Signal] = []
    counts: Dict[str, int] = {}

    def bump(name: str) -> None:
        counts[name] = counts.get(name, 0) + 1

    for symbol in asset_list():
        asset = universe.get(symbol)
        assert asset is not None
        signal_df = vintage.by_symbol[symbol].signal_prices
        market = mercado_para_simbolo(asset, symbol)
        sessions = _local_dates(signal_df.index, asset.timezone)
        benchmark_symbol = resolve_benchmark_symbol(asset, config.report)
        benchmark_close = frozen_close(vintage, benchmark_symbol) if benchmark_symbol else None
        series = build_snapshot_series(
            signal_df, cfg.indicators, cfg.levels, window_cfg.interval, benchmark_close,
            asset_timezone=market_session(market).timezone,
            benchmark_timezone=market_session(market_for_symbol(benchmark_symbol)).timezone if benchmark_symbol else None,
        )
        contexts = resolver.contexts_for_index(signal_df.index, signal_market=market) if population == POPULATION_OPERAR else []
        for j in range(WARMUP_BARS, len(signal_df) - 1):
            if not (window.start <= sessions[j + 1] <= window.end):
                continue
            ts = analysis_timestamp_for_signal(market, sessions[j], sessions[j + 1], settlement_minutes=settlement)
            if ts is None:
                bump("excluida_sin_analysis_timestamp")
                continue
            if population == POPULATION_OPERAR:
                resolved = contexts[j]
                if resolved is None or not resolved.calculable:
                    bump("excluida_" + (",".join(resolved.exclusions) if resolved is not None and resolved.exclusions else "NO_CALCULABLE_CONTEXT_HISTORY"))
                    continue
                context = resolved.context
                assert context is not None
                if context.source != "point_in_time":
                    raise P6OutcomeGateError(f"{symbol}: contexto {context.source} en P6 (solo point_in_time)")
                context_at: List[Any] = [None] * len(signal_df)
                context_at[j] = context
                found = _signal(asset, series, j, cfg, HORIZONTE, WARMUP_BARS, None, None, None, context_at, "1.0")
                if found is None:
                    bump("sin_niveles")
                    continue
                if not (found["setup_radar"] == RADAR_OPERAR and found["setup_accion"] == ACCION_COMPRAR):
                    bump("no_operar")
                    continue
                levels = found["levels"]
                signal_id = found["observation"].signal_id
            else:
                try:
                    snapshot = snapshot_from_series(symbol, series, j)
                except ValueError:
                    bump("sin_snapshot")
                    continue
                levels = compute_levels(snapshot, cfg.levels, cfg.risk.min_rr_ratio)
                if levels is None:
                    bump("sin_niveles")
                    continue
                signal_id = stable_signal_id(symbol, HORIZONTE, snapshot.timestamp)
            bump("senales")
            signals.append(Signal(signal_id, symbol, j, ts, levels.stop, levels.target2, levels.entry_max))
    return signals, dict(sorted(counts.items()))


# ---------------------------------------------------------------------------
# Preflight (no abre desenlaces).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class P6Identity:
    head_sha: str
    git_dirty: Optional[bool]
    prereg_in_history: Optional[bool]
    config_hash: str
    score_model_version: str


def prereg_in_history(repo: str | Path = ".") -> Optional[bool]:
    if run_git(["merge-base", "--is-ancestor", P6_PREREG_SHA, "HEAD"], repo).ok:
        return True
    kind = run_git(["cat-file", "-t", P6_PREREG_SHA], repo)
    return False if kind.ok and kind.output == "commit" else None


def current_identity(config: AdvisorConfig, repo: str | Path = ".") -> P6Identity:
    return P6Identity(git_sha(repo), tree_dirty(repo), prereg_in_history(repo), config_hash(config),
                      config.scoring.score_model_version)


def development_mode() -> bool:
    return os.getenv(DEVELOPMENT_ENV) == "1"


def guard_checks(config: AdvisorConfig, universe: Universe, window: Window) -> List[Tuple[str, Any, Any, bool]]:
    """Demuestra que sin token no se abre ningún desenlace (sin abrir ninguno).

    Las funciones reciben una cosecha nula: la guarda tiene que saltar antes de tocarla. Si no
    saltara, el fallo sería otro error y el control queda en rojo.
    """

    checks: List[Tuple[str, Any, Any, bool]] = []
    vintage = cast(Any, None)

    def expect_gate(name: str, call: Callable[[], Any]) -> None:
        try:
            call()
        except P6OutcomeGateError:
            checks.append((name, "P6OutcomeGateError", "P6OutcomeGateError", True))
            return
        except Exception as exc:
            checks.append((name, type(exc).__name__, "P6OutcomeGateError", False))
            return
        checks.append((name, "sin error", "P6OutcomeGateError", False))

    fake = ConfirmatoryToken(RUN_DIR / RUN_MARKER, "0" * 64)
    expect_gate("build_real_market sin token",
                lambda: build_real_market(cast(Any, None), config, universe, vintage, window, {}, frozenset()))
    expect_gate("build_real_signals sin token", lambda: build_real_signals(cast(Any, None), config, universe, vintage, "B2", POPULATION_OPERAR, window))
    expect_gate("build_real_signals con token fabricado", lambda: build_real_signals(fake, config, universe, vintage, "B2", POPULATION_OPERAR, window))
    fx_stub = FxTable({})
    spec = SimSpec("guarda", "0" * 64)

    def empty_real() -> MarketData:
        return MarketData(assets={}, window_start=window.start, window_end=window.end, origin=ORIGIN_REAL,
                          contract=frozenset({spec}))

    expect_gate("simulate con datos reales sin autorización", lambda: simulate(empty_real(), [], fx_stub, spec))
    expect_gate("simulate_benchmark con datos reales sin autorización",
                lambda: simulate_benchmark(empty_real(), fx_stub, spec))
    checks.append(("marca confirmatoria ausente", (RUN_DIR / RUN_MARKER).exists(), False, not (RUN_DIR / RUN_MARKER).exists()))
    return checks


DIVIDEND_SPLIT_ASSETS = 16
SECTION_10_1_COLUMNS = ("Close", "Adj Close")
DIVIDEND_SPLIT_TOLERANCE = 1e-5
# T-022 §10.1: R6C0.DE comprobado (importe × 1,1587 = dividendo en USD); el resto, sospechosos sin verificar.
XETRA_FX_CONTROL = ("R6C0.DE", 1.1587)
XETRA_FX_SUSPECTS = ("BSP.DE", "RRU.DE", "EQQQ.DE", "IQQK.DE", "IQQT.DE")


def _not_round(amount: float, decimals: int) -> bool:
    scaled = amount * 10**decimals
    return abs(scaled - round(scaled)) > 1e-6


def dividend_split_checks() -> Tuple[List[Tuple[str, Any, Any, bool]], Dict[str, Any]]:
    """T-022 §10.1 sobre la cosecha congelada, sin argumentos del llamador.

    Carga ella misma la estructura verificada por hash (fechas, dividendos y splits) y el lector de
    filas con import local: ni las filas ni las columnas que se leen dependen del llamador, y
    ``advisor.research.p6`` no expone ningún lector de precios.
    """

    from advisor.research.vintage import load_price_rows

    return _dividend_split_checks(load_vintage_structure(DATA_VINTAGE_ID), load_price_rows)


def _dividend_split_checks(
    structure: VintageStructure,
    price_rows: Callable[..., pd.DataFrame],
) -> Tuple[List[Tuple[str, Any, Any, bool]], Dict[str, Any]]:
    """Cálculo de T-022 §10.1: coherencia algebraica Dividends/splits y lista Xetra.

    Solo pide a ``price_rows`` ``Close`` y ``Adj Close`` de la víspera y la fecha ex de los activos con
    split y dividendo, filas que calcula aquí a partir de las acciones corporativas.

    Yahoo construye ``Adj Close`` multiplicando, en cada fecha ex ``d``, por ``1 − D(d)/Close(d−1)``.
    Con ``r = Adj Close / Close`` se cumple ``r(d−1)/r(d) = 1 − D(d)/Close(d−1)`` si ``Dividends`` está en
    las mismas unidades (ajustadas por split) que ``Close``; con un dividendo sin ajustar el residuo
    sería del orden del factor de split. Solo se leen la víspera y la fecha ex de esos activos.
    """

    checks: List[Tuple[str, Any, Any, bool]] = []
    symbols = asset_list()
    split_assets = [s for s in symbols if (structure.by_symbol[s]["Stock Splits"] != 0).any()]
    checks.append((f"activos con split ({DIVIDEND_SPLIT_ASSETS})", len(split_assets), DIVIDEND_SPLIT_ASSETS,
                   len(split_assets) == DIVIDEND_SPLIT_ASSETS))
    per_asset: Dict[str, Any] = {}
    violations: List[str] = []
    for symbol in split_assets:
        frame = structure.by_symbol[symbol]
        ex_positions = [i for i, amount in enumerate(frame["Dividends"]) if amount > 0]
        if ex_positions and ex_positions[0] == 0:
            violations.append(f"{symbol} {frame.index[0]}: fecha ex sin víspera en la cosecha")
            ex_positions = ex_positions[1:]
        residuals: List[float] = []
        if ex_positions:
            stamps = sorted({frame.index[i] for i in ex_positions} | {frame.index[i - 1] for i in ex_positions})
            rows = price_rows(structure.data_vintage_id, symbol, stamps, SECTION_10_1_COLUMNS)
            for i in ex_positions:
                eve, ex = rows.loc[frame.index[i - 1]], rows.loc[frame.index[i]]
                lhs = (eve["Adj Close"] / eve["Close"]) / (ex["Adj Close"] / ex["Close"])
                rhs = 1.0 - float(frame["Dividends"].iloc[i]) / eve["Close"]
                residual = abs(float(lhs - rhs))
                residuals.append(residual)
                if not residual <= DIVIDEND_SPLIT_TOLERANCE:
                    violations.append(f"{symbol} {frame.index[i]}: residuo {residual:.3e}")
        last_split = max(i for i, factor in enumerate(frame["Stock Splits"]) if factor != 0)
        per_asset[symbol] = {
            "splits": int((frame["Stock Splits"] != 0).sum()),
            "fechas_ex": len(ex_positions),
            # Solo estas discriminan: tras el último split, ajustado y sin ajustar dan el mismo importe.
            "fechas_ex_previas_a_split": sum(1 for i in ex_positions if i < last_split),
            "residuo_max": float(f"{max(residuals):.3e}") if residuals else None,
        }
    checks.append(("coherencia algebraica Dividends/splits (fechas ex fuera de tolerancia)", len(violations), 0,
                   not violations))

    not_round = []
    for symbol in symbols:
        if not symbol.endswith(".DE"):
            continue
        amounts = [float(v) for v in structure.by_symbol[symbol]["Dividends"] if v > 0]
        if any(_not_round(amount, 4) for amount in amounts):
            not_round.append(symbol)
    control, rate = XETRA_FX_CONTROL
    control_amounts = [float(v) for v in structure.by_symbol[control]["Dividends"] if v > 0]
    # Yahoo redondea el importe convertido: tolerancia de 2·10⁻⁵ sobre el importe en USD a 4 decimales.
    control_ok = bool(control_amounts) and all(abs(a * rate - round(a * rate, 4)) < 2e-5 for a in control_amounts)
    checks.append((f"control {control}: importe × {rate} redondo a 4 decimales", control_ok, True, control_ok))
    checks.append(("lista Xetra contiene el control y los sospechosos de T-022",
                   sorted({control, *XETRA_FX_SUSPECTS} - set(not_round)), [],
                   {control, *XETRA_FX_SUSPECTS} <= set(not_round)))
    section = {
        "tolerancia": DIVIDEND_SPLIT_TOLERANCE,
        "identidad": "r(d-1)/r(d) = 1 - D(d)/Close(d-1), r = Adj Close / Close",
        "nota": ("solo las fechas ex previas al último split de cada activo discriminan un dividendo sin ajustar; "
                 "los activos sin ninguna no aportan comprobación. Close/Adj Close de esas filas no se verifican "
                 "contra series_hash (Adj Close no está en ningún hash); load_vintage los verifica en la confirmatoria."),
        "activos_con_split": per_asset,
        "fuera_de_tolerancia": violations,
        "xetra_importe_no_redondo": not_round,
        "xetra_nota": ("superconjunto: activos .DE con algún dividendo no redondo a 4 decimales, compatible con "
                       "un importe convertido de otra divisa con un único tipo; incluye ETF que reparten en EUR "
                       "con 6 decimales. No se corrige el dato (T-022 §10.1)."),
        "xetra_control": {"simbolo": control, "tipo": rate, "ok": control_ok},
    }
    return checks, section


def synthetic_market() -> Tuple[MarketData, FxTable, List[Signal]]:
    """Fixture sintético fijo para comprobar el determinismo sin abrir ningún desenlace real."""

    days = [date(2024, 1, 1) + timedelta(days=k) for k in range(60) if (date(2024, 1, 1) + timedelta(days=k)).weekday() < 5]
    assets: Dict[str, AssetSeries] = {}
    for n, (symbol, market, currency, hour_open, hour_close, drift) in enumerate((
        ("SYN.DE", "XETRA", "EUR", 7, 15, 0.004), ("SYN", "NYSE", "USD", 14, 21, -0.002), ("SYN.T", "JPX", "JPY", 0, 6, 0.003),
    )):
        closes = [100.0 * (1.0 + drift) ** k + (k % 5) * 0.3 for k in range(len(days))]
        opens = [closes[k - 1] if k else 100.0 for k in range(len(days))]
        assets[symbol] = AssetSeries(
            symbol=symbol, market=market, currency=currency, economic_currency="MULTI" if n == 2 else currency,
            region=("EUROPA", "USA", "ASIA")[n], sector=("Technology", "Energy", "UNKNOWN")[n],
            session_dates=tuple(days),
            open_utc=tuple(datetime.combine(d, time(hour_open, 30), timezone.utc) for d in days),
            close_utc=tuple(datetime.combine(d, time(hour_close, 0), timezone.utc) for d in days),
            open=tuple(opens), high=tuple(max(o, c) * 1.01 for o, c in zip(opens, closes)),
            low=tuple(min(o, c) * 0.99 for o, c in zip(opens, closes)), close=tuple(closes),
            dividends=tuple(0.5 if k == 30 else 0.0 for k in range(len(days))), eligible_from=0,
        )
    fx = FxTable({
        "USD": [(datetime.combine(d, time(15, 0), timezone.utc), 1.10 + 0.001 * k) for k, d in enumerate([days[0] - timedelta(days=3), *days])],
        "JPY": [(datetime.combine(d, time(15, 0), timezone.utc), 160.0) for d in [days[0] - timedelta(days=3), *days]],
    })
    signals = [
        Signal(f"{symbol}|swing|{k}", symbol, k, series.close_utc[k] + timedelta(minutes=30),
               series.close[k] * 0.96, series.close[k] * 1.08, series.close[k] * 1.01)
        for symbol, series in assets.items() for k in range(2, len(days) - 1, 7)
    ]
    return MarketData(assets, days[0], days[-1]), fx, signals


def synthetic_determinism() -> Dict[str, Any]:
    """Dos corridas idénticas producen el mismo ledger, la misma serie y las mismas métricas byte a byte."""

    digests = []
    for _ in range(2):
        market, fx, signals = synthetic_market()
        result = simulate(market, signals, fx, SimSpec("SINTETICO", "1" * 64))
        bench = simulate_benchmark(market, fx, SimSpec("benchmark", "2" * 64))
        series = equity_series(result.v0, result.v0_day, result.snapshots)
        bench_series = equity_series(bench.v0, bench.v0_day, bench.snapshots)
        metrics = {
            "trayectoria": path_metrics(series), "operaciones": trade_metrics(result.trades),
            "benchmark": path_metrics(bench_series),
        }
        digests.append({
            "ledger_sha256": hashlib.sha256(ledger_csv(result.ledger).encode("utf-8")).hexdigest(),
            "serie_sha256": hashlib.sha256(series_csv(series).encode("utf-8")).hexdigest(),
            "metricas_sha256": hashlib.sha256(canonical_json(metrics).encode("utf-8")).hexdigest(),
            "benchmark_ledger_sha256": hashlib.sha256(ledger_csv(bench.ledger).encode("utf-8")).hexdigest(),
            "operaciones": len(result.trades),
        })
    return {"corridas": digests, "identico": digests[0] == digests[1], "datos": "sintéticos (synthetic_market)"}


def run_preflight(
    config: AdvisorConfig,
    universe: Universe,
    structure: VintageStructure,
    ident: P6Identity,
    *,
    development: bool = False,
    write: bool = True,
    out_dir: Path = PREFLIGHT_DIR,
    determinism: Optional[Mapping[str, Any]] = None,
) -> Tuple[bool, Dict[str, Any]]:
    checks: List[Tuple[str, Any, Any, bool]] = []

    def check(name: str, observed: Any, expected: Any) -> None:
        checks.append((name, observed, expected, observed == expected))

    check("P6_PREREG_SHA en la historia", ident.prereg_in_history, True)
    check("config_hash", ident.config_hash, EXPECTED_CONFIG_HASH)
    check("score_model_version", ident.score_model_version, "1.0")
    check("data_vintage_id", structure.data_vintage_id, DATA_VINTAGE_ID)
    check("exchange_calendars", importlib.metadata.version("exchange_calendars"), EXCHANGE_CALENDARS_VERSION)
    check("tzdata", importlib.metadata.version("tzdata"), TZDATA_VERSION)
    check("exchange_overrides_sha256", sha256_file(Path("exchange_overrides.yaml")), EXCHANGE_OVERRIDES_SHA256)
    check("P6_DATA_ID", p6_data_id(), P6_DATA_ID)
    check("asset_list (90)", len(asset_list()), 90)
    identities = policy_identities(config)
    for policy, (policy_hash, cfg_hash) in POLICY_HASHES.items():
        check(f"policy_sha256 {policy}", identities[policy]["policy_sha256"], policy_hash)
        check(f"advisor_config_hash {policy}", identities[policy]["advisor_config_hash"], cfg_hash)
    from advisor.research import p5

    final = json.loads(Path("evidence/2026-10-03-T-021-p5-cierre/politicas-finales.json").read_text(encoding="utf-8"))
    for record in final["politicas"]:
        regenerated = p5.canonical_json(p5.policy_payload(config, policy_cells()[record["id"]]))
        check(f"canonical_json P5 {record['id']} byte a byte", regenerated, record["canonical_json"])
    _fx, fx_meta = load_fx()
    check("FX fuente usada", fx_meta["fuente_usada"], "B")
    check("FX pares", fx_meta["pares"], ["HKD", "JPY", "USD"])
    sectors = load_sector_map()
    check("sector 90/90", sorted(sectors) == asset_list(), True)
    window = derive_window(config, universe, structure_index(structure))
    check("ventana inicio", window.start.isoformat(), "2022-06-14")
    check("ventana fin", window.end.isoformat(), "2026-08-27")
    hashes = system_hashes(config, window)
    check("9 identidades de corrida", len(hashes), 9)
    check("system_sha256 distintos", len({v.get("system_sha256") or v.get("benchmark_sha256") for v in hashes.values()}), 9)
    dividend_checks, dividends_section = dividend_split_checks()
    checks.extend(dividend_checks)
    checks.extend(guard_checks(config, universe, window))
    if determinism is not None:
        check("determinismo sintético byte a byte", determinism.get("identico"), True)
    report: Dict[str, Any] = {
        "fase": "preflight",
        "modo": "DESARROLLO (no es evidencia)" if development else "DEFINITIVO",
        "label": UNIVERSE_LABEL,
        "inicio_utc": utc_now(),
        "new_p6_outcomes_read": False,
        "outcomes_leidos": "ninguno: solo identidades, fechas, calendario, FX y sector congelados",
        "datos_de_mercado_leidos": ("fechas y acciones corporativas verificadas (corporate_actions_hash) de toda la "
                                    "cosecha; los CSV se leen como texto y las columnas de precio solo sirven para descartar "
                                    "filas sin precio; únicamente Close y Adj Close de la víspera y la fecha ex de los "
                                    "activos con split y dividendo se convierten a número (T-022 §10.1); no se "
                                    "construye ninguna vista de precios"),
        "p6_confirmatory_executed": (RUN_DIR / RUN_MARKER).exists(),
        "identidad": {
            "p6_prereg_sha": P6_PREREG_SHA,
            "p6_executor_sha": ident.head_sha,
            "git_dirty": ident.git_dirty,
            "prereg_en_historia": ident.prereg_in_history,
            "p6_data_id": P6_DATA_ID,
            "data_vintage_id": DATA_VINTAGE_ID,
            "universe_vintage_id": UNIVERSE_VINTAGE_ID,
            "fx_vintage_id": FX_VINTAGE_ID,
            "sector_map": SECTOR_MAP_SHA256,
        },
        "politicas": identities,
        "ventana": window.as_dict(),
        "system_hashes": hashes,
        "dividendos_splits": dividends_section,
        "determinismo": dict(determinism) if determinism is not None else None,
        "checks": [{"control": n, "observado": o, "esperado": e, "ok": ok} for n, o, e, ok in checks],
        "fin_utc": utc_now(),
    }
    ok = all(row["ok"] for row in report["checks"])
    report["ok"] = ok
    report["definitivo"] = bool(ok and not development and ident.git_dirty is False and ident.prereg_in_history is True)
    if write and not development:
        if ident.git_dirty is not False:
            raise P6PreflightError("el preflight definitivo solo se escribe con árbol limpio")
        out_dir.mkdir(parents=True, exist_ok=True)
        write_json(out_dir / "p6-preflight.json", report)
        (out_dir / "p6-preflight.txt").write_text(format_preflight(report), encoding="utf-8")
        write_json(out_dir / "system-hashes.json", {"label": UNIVERSE_LABEL, "ventana": window.as_dict(), "hashes": hashes})
    return ok, report


def format_preflight(report: Mapping[str, Any]) -> str:
    lines = [
        "# P6 preflight",
        f"modo: {report['modo']}",
        f"ok: {report.get('ok')}",
        f"definitivo: {report.get('definitivo')}",
        f"ventana: {report['ventana']['inicio']} → {report['ventana']['fin']}",
        f"new_p6_outcomes_read: {report['new_p6_outcomes_read']}",
        f"label: {UNIVERSE_LABEL}",
        "",
    ]
    failed = [row for row in report["checks"] if not row["ok"]]
    lines.append(f"Checks: {len(report['checks']) - len(failed)}/{len(report['checks'])} OK.")
    lines.extend(f"- FALLA {row['control']}: observado={row['observado']} esperado={row['esperado']}" for row in failed)
    return "\n".join(lines) + "\n"


def preflight_fingerprint(report: Mapping[str, Any]) -> Dict[str, Any]:
    return {key: report.get(key) for key in ("politicas", "ventana", "system_hashes", "dividendos_splits",
                                              "determinismo")} | {
        "identidad": {k: v for k, v in cast(Mapping[str, Any], report.get("identidad", {})).items()
                      if k not in ("p6_executor_sha", "git_dirty")},
    }


# ---------------------------------------------------------------------------
# Ejecución confirmatoria única (implementada; solo se lanza con autorización expresa).
# ---------------------------------------------------------------------------


def _run_metrics(result: Any, benchmark_paths: Mapping[float, Mapping[str, Any]], slippage: float, ppy: float) -> Dict[str, Any]:
    series = equity_series(result.v0, result.v0_day, result.snapshots)
    path = path_metrics(series, expected_ppy=ppy)
    trades_m = trade_metrics(result.trades)
    exc = excess(path, benchmark_paths[slippage])
    return {
        "trayectoria": path,
        "operaciones": trades_m,
        "exposicion": exposure_metrics(result.snapshots),
        "turnover": turnover(result.notional_traded_eur, series),
        "costes_eur": result.fees_eur,
        "slippage_eur": result.slippage_eur,
        "dividendos_eur": result.dividends_eur,
        "fx_eur": sum(trade.fx_eur for trade in result.trades),
        "exceso": exc,
        "contadores": result.counters,
        "ocupacion": cash_occupancy(result.counters, result.ledger),
        "subperiodos": subperiods(series, result.trades),
        "criterio": criterion(trades_m, path, exc),
    }


def _preregistered_specs(config: AdvisorConfig, hashes: Mapping[str, Mapping[str, str]]) -> FrozenSet[SimSpec]:
    """Contrato de corridas: los 9 SimSpec de T-022/D-69 (7 corridas + 2 benchmarks), completos.

    Cada entrada fija run_id, policy_id, población, slippage, hash, capital, riesgo, tope por posición,
    comisión, min_rr y tiempo máximo; ``hashes`` solo puede venir del preflight definitivo verificado.
    """

    defaults = SimSpec("", "")
    specs = {
        SimSpec(policy, hashes[run_id]["system_sha256"], capital=CAPITAL, risk_pct=config.portfolio.risk_per_trade_pct,
                max_position_pct=config.portfolio.max_position_pct, fee_rate=defaults.fee_rate, slippage_bps=slippage,
                min_rr=config.risk.min_rr_ratio, max_hold_bars=defaults.max_hold_bars, run_id=run_id, population=population)
        for run_id, policy, population, slippage in RUNS
    }
    specs |= {SimSpec("benchmark", hashes[run_id]["benchmark_sha256"], capital=CAPITAL, fee_rate=defaults.fee_rate,
                      slippage_bps=slippage, run_id=run_id, population=BENCHMARK_POPULATION)
              for run_id, slippage in BENCHMARK_RUNS}
    if len(specs) != len(RUNS) + len(BENCHMARK_RUNS):
        raise P6PreflightError("el contrato de corridas no tiene las 9 identidades distintas")
    return frozenset(specs)


def _spec_guard(allowed: FrozenSet[SimSpec]) -> Callable[[SimSpec], None]:
    """Rechaza cualquier SimSpec que no sea exactamente uno de los pre-registrados."""

    def check(spec: SimSpec) -> None:
        if spec not in allowed:
            raise P6OutcomeGateError(f"P6: SimSpec no pre-registrado ({spec.run_id or spec.policy_id}, {spec.system_sha256[:12]}…)")

    return check


def _ejecutar_confirmatoria_sellada() -> Tuple[int, str]:
    """Único camino que abre desenlaces: apertura y corridas pre-registradas, sin argumentos.

    1. autorización reconstruida desde disco y preflight recalculado (_verified_authorization);
    2. cosecha completa y ventana idéntica a la del preflight (si no, para sin consumir la marca);
    3. payload canónico y contrato de corridas calculados aquí con los hashes del preflight verificado;
    4. payload persistido (temporal, fsync, replace atómico, fsync del directorio) y verificado por hash;
       si falla, no hay marca;
    5. marca en RUN_DIR/RUN_MARKER con O_CREAT|O_EXCL que referencia y hashea ese payload;
    6. token atado a la marca, vigente solo durante esta función;
    7. solo las 9 corridas del contrato: el MarketData real lo lleva dentro y p6_sim lo exige por sí mismo,
       además del token y del guard de esta función.
    """

    config, universe, stored, live = _verified_authorization()
    # La cosecha completa solo se carga aquí, tras verificar preflight, identidades, P6_DATA_ID y ejecutor,
    # y antes de la marca solo para reproducir la ventana. P6 no expone ningún otro cargador de precios.
    from advisor.research.vintage import load_vintage

    vintage = load_vintage(DATA_VINTAGE_ID)
    window = derive_window(config, universe, vintage_index(vintage))
    if window.as_dict() != live["ventana"]:
        raise P6PreflightError("la cosecha completa no reproduce la ventana del preflight; P6 no se ejecuta")
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    if any(RUN_DIR.iterdir()):
        raise P6AlreadyExecutedError(f"{RUN_DIR} no está vacío: P6 no se repite")
    hashes: Dict[str, Dict[str, str]] = stored["system_hashes"]
    payload = {
        "inicio_utc": utc_now(),
        "p6_prereg_sha": P6_PREREG_SHA,
        "p6_code_sha_preflight": stored["identidad"]["p6_executor_sha"],
        "head_sha": git_sha("."),
        "p6_data_id": P6_DATA_ID,
        "ventana": stored["ventana"],
        "system_hashes": {run_id: hashes[run_id]["system_sha256"] for run_id, *_ in RUNS},
        "benchmark_hashes": {run_id: hashes[run_id]["benchmark_sha256"] for run_id, _ in BENCHMARK_RUNS},
        "label": UNIVERSE_LABEL,
    }
    data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    payload_sha256 = hashlib.sha256(data).hexdigest()
    contract = _preregistered_specs(config, hashes)
    specs = {spec.run_id: spec for spec in contract}

    # El payload canónico se persiste y verifica ANTES de la marca: si el proceso cae justo después de
    # crearla, ya está archivado el contrato que consumió la ejecución. Si falla, no hay marca.
    payload_path = RUN_DIR / RUN_PAYLOAD
    tmp_path = RUN_DIR / f".{RUN_PAYLOAD}.tmp"
    try:
        with open(tmp_path, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, payload_path)
        dir_fd = os.open(RUN_DIR, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        if hashlib.sha256(payload_path.read_bytes()).hexdigest() != payload_sha256:
            raise P6PreflightError("el payload de apertura persistido no coincide con el canónico")
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        payload_path.unlink(missing_ok=True)
        raise

    marker = RUN_DIR / RUN_MARKER
    marker_data = (json.dumps({"payload": RUN_PAYLOAD, "payload_sha256": payload_sha256}, ensure_ascii=False,
                              indent=2) + "\n").encode("utf-8")
    try:
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError as exc:
        raise P6AlreadyExecutedError(f"la ejecución confirmatoria de P6 ya se inició ({marker}); no se repite") from exc
    except BaseException:
        payload_path.unlink(missing_ok=True)
        raise
    # Desde aquí la ejecución está consumida; el payload que la abrió ya está en disco y la marca lo hashea.
    written = 0
    global _ACTIVE_TOKEN
    try:
        try:
            while written < len(marker_data):
                written += os.write(fd, marker_data[written:])
            os.fsync(fd)
        finally:
            os.close(fd)
        if marker.read_bytes() != marker_data:
            raise P6OutcomeGateError("la marca escrita no coincide con la referencia al payload canónico")
        token = ConfirmatoryToken(marker, hashlib.sha256(marker_data).hexdigest(), secrets.token_hex(32))
        _ACTIVE_TOKEN = token
        guard = _spec_guard(contract)

        def authorize(spec: SimSpec) -> None:
            require_token(token)
            guard(spec)

        fx, _ = load_fx()
        sectors = load_sector_map()
        market = build_real_market(token, config, universe, vintage, window, sectors, contract)
        bench: Dict[float, Any] = {}
        bench_paths: Dict[float, Dict[str, Any]] = {}
        tables = RUN_DIR / "tablas"
        tables.mkdir(parents=True, exist_ok=True)
        for run_id, slippage in BENCHMARK_RUNS:
            bench[slippage] = simulate_benchmark(market, fx, specs[run_id], authorize=authorize)
            series = equity_series(CAPITAL, window.start, bench[slippage].snapshots)
            bench_paths[slippage] = path_metrics(series, expected_ppy=window.periods_per_year)
            (tables / f"{run_id}-ledger.csv").write_text(ledger_csv(bench[slippage].ledger), encoding="utf-8")
            (tables / f"{run_id}-serie-diaria.csv").write_text(series_csv(series), encoding="utf-8")
        results: Dict[str, Any] = {}
        signal_counts: Dict[str, Any] = {}
        for run_id, policy, population, slippage in RUNS:
            signals, counts = build_real_signals(token, config, universe, vintage, policy, population, window)
            signal_counts[run_id] = counts
            result = simulate(market, signals, fx, specs[run_id], authorize=authorize)
            results[run_id] = _run_metrics(result, bench_paths, slippage, window.periods_per_year)
            (tables / f"{run_id}-ledger.csv").write_text(ledger_csv(result.ledger), encoding="utf-8")
            (tables / f"{run_id}-operaciones.csv").write_text(trades_csv(result.trades), encoding="utf-8")
            (tables / f"{run_id}-serie-diaria.csv").write_text(
                series_csv(equity_series(result.v0, result.v0_day, result.snapshots)), encoding="utf-8")
        labels = {policy: results[f"{policy}_primaria_5pb"]["criterio"]["etiqueta"] for policy in CANDIDATES}
        output = {
            "fase": "confirmatoria",
            "token_sha256": token.marker_payload_sha256,
            "label": UNIVERSE_LABEL,
            "ventana": window.as_dict(),
            "benchmark": {f"{s}pb": bench_paths[s] for s in bench_paths},
            "corridas": results,
            "senales": signal_counts,
            "etiquetas_decisorias": labels,
            "supervivientes": list(survivors(labels)),
            "fin_utc": utc_now(),
        }
        write_json(RUN_DIR / "p6-resultado.json", output)
        summary = "# P6 confirmatoria\n\n" + "".join(f"- {p}: {labels[p]}\n" for p in CANDIDATES) + (
            f"- supervivientes: {', '.join(output['supervivientes']) or 'ninguno'}\n")
        (RUN_DIR / "p6-resumen.md").write_text(summary, encoding="utf-8")
        return 0, summary
    except BaseException as exc:
        write_json(RUN_DIR / "p6-parada.json", {
            "fase": "confirmatoria", "parada": type(exc).__name__, "detalle": str(exc), "fin_utc": utc_now(),
            "marca": {"payload": RUN_PAYLOAD, "payload_sha256": payload_sha256,
                      "bytes_escritos": written, "bytes_esperados": len(marker_data)},
        })
        if not isinstance(exc, Exception):
            raise
        return 2, f"STOP P6 confirmatoria: {type(exc).__name__}: {exc}\n"
    finally:
        _ACTIVE_TOKEN = None


def run_confirmatory(
    config: AdvisorConfig,
    universe: Universe,
    ident: P6Identity,
    out_dir: Path,
) -> Tuple[int, str]:
    """Ejecución confirmatoria única. Devuelve solo código y resumen, nunca el token.

    ``config``, ``universe`` e ``ident`` solo sirven para rechazar pronto un estado imposible; todo lo
    que decide la ejecución lo reconstruye _ejecutar_confirmatoria_sellada desde las fuentes de verdad.
    """

    del config, universe
    if out_dir.resolve() != RUN_DIR.resolve():
        raise P6PreflightError(f"la ejecución confirmatoria solo escribe en {RUN_DIR}")
    if (RUN_DIR / RUN_MARKER).exists():
        raise P6AlreadyExecutedError(f"la ejecución confirmatoria de P6 ya se inició ({RUN_DIR / RUN_MARKER}); no se repite")
    if ident.git_dirty is not False:
        raise P6PreflightError(f"árbol no limpio (git_dirty={ident.git_dirty})")
    if ident.prereg_in_history is not True:
        raise P6PreflightError("P6_PREREG_SHA no está en la historia de HEAD")
    if RUN_DIR.exists() and any(RUN_DIR.iterdir()):
        raise P6AlreadyExecutedError(f"{RUN_DIR} no está vacío: P6 no se repite")
    return _ejecutar_confirmatoria_sellada()
