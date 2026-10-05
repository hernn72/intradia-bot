"""Camino decisorio sintético de T-024."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import subprocess
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping, Optional, Protocol, Sequence

import numpy as np

from advisor.config import AdvisorConfig
from advisor.research import t024_comun as comun
from advisor.research.p4 import executor_unchanged_since, tree_dirty
from advisor.research.t024_captura import capturar, evaluar_ejecutabilidad
from advisor.research.t024_comun import (
    BLOCK_WEEKS,
    C_E_FINAL,
    CUTOFF_CONSUMIDA,
    DIAS_COSECHA_DECISIVA,
    FEE,
    MAX_HOLD,
    MIN_SESIONES_DRIFT,
    MIN_SESIONES_FUERA,
    N_MIN,
    Q_HI,
    Q_LO,
    SEED,
    SLIP_BPS,
    B,
    ConteoCaptura,
    SenalT024,
    semana_iso,
)
from advisor.research.vintage import VintageLoad

EXIT_STOP = "stop"
EXIT_TARGET = "objetivo"
EXIT_TIME = "tiempo"
EXIT_FINAL = "final"
POSITIVO = "POSITIVO"
NO_POSITIVO = "NO POSITIVO"
NO_CONCLUYENTE = "NO CONCLUYENTE"
NO_EVALUABLE = "NO EVALUABLE POR MUESTRA"
REPROPONER = "REPROPONER"
ORIGEN_SINTETICO = "sintetico"
UTC = timezone.utc


class T024DecisionError(RuntimeError):
    """La ejecución decisoria violaría una guarda pre-registrada."""


@dataclass(frozen=True)
class BarraDecision:
    session: date
    open: float
    high: float
    low: float
    close: float
    dividend: float = 0.0
    # «sintetico» para tests y desarrollo; «cosecha:<data_vintage_id>» solo lo pone `barras_decision`, tras el token.
    origen: str = ORIGEN_SINTETICO


@dataclass(frozen=True)
class TokenMirada:
    marca: Path
    marca_sha256: str
    nonce: str


_TOKEN_ACTIVO: Optional[TokenMirada] = None


@dataclass
class _D3D4Bucket:
    d3: list[float]
    d4: list[float]
    d4_truncadas: int = 0


@dataclass(frozen=True)
class VentanaT024:
    senal: SenalT024
    e_index: int
    x_index: int
    exit_reason: str
    exit_price: float
    dividend: float
    l_i: float
    pi_i: float
    h_i: int
    d1: float
    d2: Optional[float]
    d2o: Optional[float]
    d2c: Optional[float]
    d2_b: Optional[float]
    d2_coste_prorrateado: Optional[float]
    phi_a: float
    truncada_t1: bool = False
    origen: str = ORIGEN_SINTETICO


@dataclass(frozen=True)
class BootstrapResult:
    mean: float
    ci_low: float
    ci_high: float
    substitutions: int
    draws: tuple[float, ...]


@dataclass(frozen=True)
class ResultadoPolitica:
    policy: str
    etiqueta: str
    n: int
    media: Optional[float]
    ci: Optional[tuple[float, float]]
    sustituciones: int = 0
    ventanas_excluidas: int = 0
    activos_excluidos: int = 0


@dataclass(frozen=True)
class RegistroForward:
    cosechas: tuple[tuple[str, date], ...]
    sha256: str


@dataclass(frozen=True)
class ResultadoDecision:
    politicas: Mapping[str, ResultadoPolitica]
    descriptivas: Mapping[str, object]
    phi_medio: Mapping[str, float]
    ignoradas_no_solapamiento: int
    ventanas_truncadas_t1: int
    eur: Optional[Mapping[str, object]]

    def serializable(self) -> Mapping[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ResultadoVentanas:
    ventanas: tuple[VentanaT024, ...]
    ignoradas_no_solapamiento: int
    ventanas_excluidas_d2: int
    activos_excluidos_d2: int
    ventanas_excluidas_d2o: int
    activos_excluidos_d2o: int
    rechazos_ejecutabilidad: Mapping[str, int]


class FxCausal(Protocol):
    def rate(self, currency: str, at: datetime) -> float: ...


class ActivoT024(Protocol):
    timezone: str


class UniversoT024(Protocol):
    def get(self, symbol: str) -> ActivoT024: ...


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _crear_token_mirada(marca: Path) -> TokenMirada:
    return TokenMirada(marca=marca, marca_sha256=_sha256_path(marca), nonce=secrets.token_hex(32))


def _exigir_token(token: TokenMirada | None) -> None:
    if token is None:
        raise T024DecisionError("T-024: token de mirada ausente")
    if token != _TOKEN_ACTIVO:
        raise T024DecisionError("T-024: token de mirada no activo")
    if _sha256_path(token.marca) != token.marca_sha256:
        raise T024DecisionError("T-024: marca de mirada modificada")


def _exigir_token_si_cosecha(origenes: Iterable[str]) -> None:
    """Las funciones de desenlace son libres con datos sintéticos; con barras de una cosecha exigen el token.

    Modelo de amenaza (T-024 §13): impide abrir desenlaces reales por accidente o fuera de `ejecutar_mirada`;
    no pretende impedir que alguien reconstruya a mano barras «sintéticas» desde una cosecha para saltárselo.
    """

    if any(origen != ORIGEN_SINTETICO for origen in origenes):
        _exigir_token(_TOKEN_ACTIVO)


def d1_cerrada(open_entry: float, exit_price: float, dividend: float, *, fee: float = FEE, slip_bps: float = SLIP_BPS) -> float:
    sigma = slip_bps / 10_000.0
    return math.log((exit_price * (1.0 - sigma) * (1.0 - fee) + dividend) / (exit_price + dividend)) - math.log(
        (1.0 + sigma) * (1.0 + fee)
    )


def salida_p6(senal: SenalT024, barras: Sequence[BarraDecision]) -> tuple[int, str, float, float, bool]:
    _exigir_token_si_cosecha(row.origen for row in barras)
    e = senal.s_index + 1
    if e >= len(barras):
        raise ValueError(f"{senal.signal_id}: sin entrada")
    last = len(barras) - 1
    dividend = 0.0
    for i in range(e, len(barras)):
        row = barras[i]
        if i > e and row.dividend > 0:
            dividend += row.dividend
        if i > e:
            if row.open <= senal.stop:
                return i, EXIT_STOP, row.open, dividend, False
            if row.open >= senal.target2 and row.low > senal.stop:
                return i, EXIT_TARGET, row.open, dividend, False
        if row.low <= senal.stop:
            return i, EXIT_STOP, senal.stop, dividend, False
        if row.high >= senal.target2:
            return i, EXIT_TARGET, senal.target2, dividend, False
        if i - e >= MAX_HOLD:
            return i, EXIT_TIME, row.close, dividend, False
        if i == last:
            # T-024 §9 regla 7: solo la ventana aún abierta en T1, cerrada por la regla final, cuenta como truncada.
            return i, EXIT_FINAL, row.close, dividend, True
    raise AssertionError("salida inalcanzable")


def retorno_log_operacion(open_entry: float, exit_price: float, dividend: float) -> float:
    sigma = SLIP_BPS / 10_000.0
    p_in = open_entry * (1.0 + sigma)
    p_out = exit_price * (1.0 - sigma)
    return math.log((p_out * (1.0 - FEE) + dividend) / (p_in * (1.0 + FEE)))


def retorno_pasivo_mismo_intervalo(open_entry: float, exit_price: float, dividend: float) -> float:
    return math.log((exit_price + dividend) / open_entry)


def coste_roundtrip() -> float:
    sigma = SLIP_BPS / 10_000.0
    return math.log((1.0 + sigma) * (1.0 + FEE)) - math.log((1.0 - sigma) * (1.0 - FEE))


def retornos_cierre(barras: Sequence[BarraDecision]) -> list[Optional[float]]:
    _exigir_token_si_cosecha(row.origen for row in barras)
    out: list[Optional[float]] = [None]
    for prev, row in zip(barras, barras[1:]):
        out.append(math.log((row.close + row.dividend) / prev.close))
    return out


def drift_noche_dia(barras: Sequence[BarraDecision]) -> tuple[float, float]:
    _exigir_token_si_cosecha(row.origen for row in barras)
    noches: list[float] = []
    dias: list[float] = []
    for prev, row in zip(barras, barras[1:]):
        noches.append(math.log(row.open / prev.close))
        dias.append(math.log((row.close + row.dividend) / row.open))
    return sum(noches) / len(noches), sum(dias) / len(dias)


def media(values: Iterable[float]) -> Optional[float]:
    data = list(values)
    if not data:
        return None
    return sum(data) / len(data)


def _present(values: Iterable[Optional[float]]) -> list[float]:
    return [value for value in values if value is not None]


def t0_activo(barras: Sequence[BarraDecision]) -> date:
    for row in barras:
        if row.session > CUTOFF_CONSUMIDA:
            return row.session
    raise ValueError("activo sin sesión posterior al corte consumido")


def _truncate_barras(barras: Sequence[BarraDecision], t1: date) -> tuple[BarraDecision, ...]:
    return tuple(row for row in barras if row.session <= t1)


def construir_ventanas(
    senales: Sequence[SenalT024],
    barras_por_activo: Mapping[str, Sequence[BarraDecision]],
    *,
    c_e: date,
    t1_por_activo: Optional[Mapping[str, date]] = None,
    no_solapar: bool = True,
) -> ResultadoVentanas:
    _exigir_token_si_cosecha(row.origen for rows in barras_por_activo.values() for row in rows)
    abiertas_hasta: dict[tuple[str, str], int] = {}
    ignoradas = 0
    rechazos: Counter[str] = Counter()
    ventanas: list[VentanaT024] = []
    for senal in sorted(senales, key=lambda s: (s.analysis_ts, s.signal_id)):
        if not comun.es_elegible_temporal(senal.s_session, senal.e_session, c_e):
            continue
        t1_asset = t1_por_activo.get(senal.asset) if t1_por_activo is not None else None
        full_bars = barras_por_activo[senal.asset]
        t1_asset = t1_asset or full_bars[-1].session
        barras = _truncate_barras(full_bars, t1_asset)
        t0 = t0_activo(barras)
        e = senal.s_index + 1
        if e >= len(barras) or barras[e].session > c_e:
            continue
        key = (senal.policy, senal.asset)
        if no_solapar and abiertas_hasta.get(key, -1) >= e:
            ignoradas += 1
            continue
        ejecutabilidad = evaluar_ejecutabilidad(senal, barras[e].open)
        if not ejecutabilidad.ejecutable:
            rechazos[ejecutabilidad.reason] += 1
            continue
        x, reason, exit_price, dividend, truncada = salida_p6(senal, barras)
        abiertas_hasta[key] = x
        ventanas.append(calcular_ventana(senal, barras, x, reason, exit_price, dividend, t0=t0, t1=t1_asset, truncada_t1=truncada))
    return recalcular_por_politica_activo(
        ventanas,
        barras_por_activo,
        t1_por_activo=t1_por_activo,
        ignoradas=ignoradas,
        rechazos_ejecutabilidad=dict(sorted(rechazos.items())),
    )


def calcular_ventana(
    senal: SenalT024,
    barras: Sequence[BarraDecision],
    x: int,
    reason: str,
    exit_price: float,
    dividend: float,
    *,
    t0: date,
    t1: date,
    truncada_t1: bool,
) -> VentanaT024:
    _exigir_token_si_cosecha(row.origen for row in barras)
    e = senal.s_index + 1
    open_entry = barras[e].open
    l_i = retorno_log_operacion(open_entry, exit_price, dividend)
    pi_i = retorno_pasivo_mismo_intervalo(open_entry, exit_price, dividend)
    h_i = x - e + 1
    valid_indices = [i for i, row in enumerate(barras) if t0 <= row.session <= t1]
    returns = retornos_cierre(barras)
    valid_returns = _present(returns[i] for i in valid_indices)
    mu = media(valid_returns)
    covered = set(range(e, x + 1))
    outside_returns = _present(returns[i] for i in valid_indices if i not in covered)
    mu_out = media(outside_returns)
    causal = _present(returns[i] for i in range(max(1, senal.s_index - 249), senal.s_index + 1))
    mu_causal = media(causal)
    phi = len(covered & set(valid_indices)) / len(valid_indices) if valid_indices else 0.0
    if len(valid_returns) < MIN_SESIONES_DRIFT:
        d2 = None
        d2_b = None
        d2_cost = None
    else:
        assert mu is not None
        d2 = l_i - h_i * mu
        mu_noche, mu_dia = drift_noche_dia([row for row in barras if t0 <= row.session <= t1])
        d2_b = l_i - ((x - e) * mu_noche + (x - e + 1) * mu_dia)
        d2_cost = l_i - (h_i * mu - (coste_roundtrip() * h_i / max(len(valid_returns), 1)))
    d2o = None if len(outside_returns) < MIN_SESIONES_FUERA or mu_out is None else l_i - h_i * mu_out
    d2c = None if mu_causal is None else l_i - h_i * mu_causal
    return VentanaT024(
        senal=senal,
        e_index=e,
        x_index=x,
        exit_reason=reason,
        exit_price=exit_price,
        dividend=dividend,
        l_i=l_i,
        pi_i=pi_i,
        h_i=h_i,
        d1=l_i - pi_i,
        d2=d2,
        d2o=d2o,
        d2c=d2c,
        d2_b=d2_b,
        d2_coste_prorrateado=d2_cost,
        phi_a=phi,
        truncada_t1=truncada_t1,
        origen=barras[e].origen,
    )


def recalcular_por_politica_activo(
    ventanas: Sequence[VentanaT024],
    barras_por_activo: Mapping[str, Sequence[BarraDecision]],
    *,
    t1_por_activo: Optional[Mapping[str, date]] = None,
    ignoradas: int = 0,
    rechazos_ejecutabilidad: Optional[Mapping[str, int]] = None,
) -> ResultadoVentanas:
    _exigir_token_si_cosecha([*(v.origen for v in ventanas), *(row.origen for rows in barras_por_activo.values() for row in rows)])
    grouped: dict[tuple[str, str], list[VentanaT024]] = {}
    for ventana in ventanas:
        grouped.setdefault((ventana.senal.policy, ventana.senal.asset), []).append(ventana)
    final: list[VentanaT024] = []
    excl_d2_windows = excl_d2_assets = excl_d2o_windows = excl_d2o_assets = 0
    for (policy, asset), group in grouped.items():
        _ = policy
        rows_all = barras_por_activo[asset]
        t1 = t1_por_activo.get(asset) if t1_por_activo is not None else rows_all[-1].session
        rows = _truncate_barras(rows_all, t1 or rows_all[-1].session)
        t0 = t0_activo(rows)
        valid_indices = [i for i, row in enumerate(rows) if t0 <= row.session <= (t1 or rows[-1].session)]
        returns = retornos_cierre(rows)
        valid_returns = _present(returns[i] for i in valid_indices)
        covered: set[int] = set()
        for window in group:
            covered.update(range(window.e_index, window.x_index + 1))
        outside_returns = _present(returns[i] for i in valid_indices if i not in covered)
        phi = len(covered & set(valid_indices)) / len(valid_indices) if valid_indices else 0.0
        mu = media(valid_returns)
        mu_out = media(outside_returns)
        d2_ok = len(valid_returns) >= MIN_SESIONES_DRIFT and mu is not None
        d2o_ok = len(outside_returns) >= MIN_SESIONES_FUERA and mu_out is not None
        if not d2_ok:
            excl_d2_assets += 1
            excl_d2_windows += len(group)
        if not d2o_ok:
            excl_d2o_assets += 1
            excl_d2o_windows += len(group)
        mu_value = float(mu) if mu is not None else 0.0
        mu_out_value = float(mu_out) if mu_out is not None else 0.0
        for window in group:
            d2 = None if not d2_ok else window.l_i - window.h_i * mu_value
            d2o = None if not d2o_ok else window.l_i - window.h_i * mu_out_value
            d2_cost = None if not d2_ok else window.l_i - (window.h_i * mu_value - coste_roundtrip() * window.h_i / len(valid_returns))
            final.append(replace(window, d2=d2, d2o=d2o, d2_coste_prorrateado=d2_cost, phi_a=phi))
    return ResultadoVentanas(
        ventanas=tuple(sorted(final, key=lambda w: (w.senal.analysis_ts, w.senal.signal_id))),
        ignoradas_no_solapamiento=ignoradas,
        ventanas_excluidas_d2=excl_d2_windows,
        activos_excluidos_d2=excl_d2_assets,
        ventanas_excluidas_d2o=excl_d2o_windows,
        activos_excluidos_d2o=excl_d2o_assets,
        rechazos_ejecutabilidad=dict(rechazos_ejecutabilidad or {}),
    )


def indice_equiponderado_region(series_por_activo: Mapping[str, Sequence[BarraDecision]]) -> dict[date, float]:
    _exigir_token_si_cosecha(row.origen for rows in series_por_activo.values() for row in rows)
    by_date: dict[date, list[float]] = {}
    all_dates = sorted({row.session for rows in series_por_activo.values() for row in rows})
    for rows in series_por_activo.values():
        returns = retornos_cierre(rows)
        for i, row in enumerate(rows):
            value = returns[i]
            if value is not None:
                by_date.setdefault(row.session, []).append(value)
    index: dict[date, float] = {}
    value = 1.0
    for session in all_dates:
        if session in by_date:
            value *= math.exp(sum(by_date[session]) / len(by_date[session]))
        index[session] = value
    return index


def d3_region(ventana: VentanaT024, barras: Sequence[BarraDecision], indice: Mapping[date, float]) -> float:
    _exigir_token_si_cosecha([ventana.origen, *(row.origen for row in barras)])
    return ventana.l_i - math.log(indice[barras[ventana.x_index].session] / indice[barras[ventana.e_index - 1].session])


def d4_40_sesiones(ventana: VentanaT024, barras: Sequence[BarraDecision], *, t1: Optional[date] = None) -> tuple[float, bool]:
    _exigir_token_si_cosecha([ventana.origen, *(row.origen for row in barras)])
    e = ventana.e_index
    usable = _truncate_barras(barras, t1) if t1 is not None else tuple(barras)
    j = min(e + MAX_HOLD, len(usable) - 1)
    dividend = sum(row.dividend for row in barras[e + 1 : j + 1])
    pin = barras[e].open * (1.0 + SLIP_BPS / 10_000.0)
    return ventana.l_i - math.log((usable[j].close + dividend) / pin), j != e + MAX_HOLD


def retorno_eur(l_i: float, currency: str, entry_at: datetime, exit_at: datetime, fx: FxCausal) -> float:
    return l_i + math.log(fx.rate(currency, exit_at) / fx.rate(currency, entry_at))


def bootstrap_semanal(
    valores: Sequence[tuple[date, float]],
    *,
    b: int = B,
    seed: int = SEED,
) -> BootstrapResult:
    if not valores:
        raise ValueError("sin ventanas")
    by_week: dict[tuple[int, int], list[float]] = {}
    for day, value in valores:
        by_week.setdefault(semana_iso(day), []).append(value)
    weeks = semanas_consecutivas(min(by_week), max(by_week))
    k = len(weeks)
    blocks = [weeks[i : i + BLOCK_WEEKS] for i in range(k - BLOCK_WEEKS + 1)]
    rng = np.random.default_rng(seed)
    draws: list[float] = []
    substitutions = 0
    while len(draws) < b:
        selected: list[tuple[int, int]] = []
        for _ in range(math.ceil(k / BLOCK_WEEKS)):
            selected.extend(blocks[int(rng.integers(0, len(blocks)))])
        sample_weeks = selected[:k]
        sample = [v for week in sample_weeks for v in by_week.get(week, [])]
        if not sample:
            substitutions += 1
            continue
        draws.append(sum(sample) / len(sample))
    arr = np.array(draws, dtype=float)
    ci_low, ci_high = np.quantile(arr, [Q_LO, Q_HI], method="linear")
    return BootstrapResult(sum(v for _, v in valores) / len(valores), float(ci_low), float(ci_high), substitutions, tuple(draws))


def semanas_consecutivas(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    current = date.fromisocalendar(start[0], start[1], 1)
    last = date.fromisocalendar(end[0], end[1], 1)
    out: list[tuple[int, int]] = []
    while current <= last:
        out.append(semana_iso(current))
        current += timedelta(days=7)
    return out


def etiquetar(ci_low: float, ci_high: float, *, n: int, capacidad: bool = True) -> str:
    if not capacidad or n < N_MIN:
        return NO_EVALUABLE
    if ci_low > 0.0:
        return POSITIVO
    if ci_high <= 0.0:
        return NO_POSITIVO
    return NO_CONCLUYENTE


def decidir_politica(
    policy: str,
    ventanas: Sequence[VentanaT024] | ResultadoVentanas,
    *,
    capacidad: bool = True,
) -> ResultadoPolitica:
    if isinstance(ventanas, ResultadoVentanas):
        excl_w = ventanas.ventanas_excluidas_d2
        excl_a = ventanas.activos_excluidos_d2
        window_seq = ventanas.ventanas
    else:
        excl_w = 0
        excl_a = 0
        window_seq = tuple(ventanas)
    _exigir_token_si_cosecha(v.origen for v in window_seq)
    valores = [(v.senal.e_session, v.d2) for v in window_seq if v.senal.policy == policy and v.d2 is not None]
    if not capacidad or len(valores) < N_MIN:
        return ResultadoPolitica(policy, NO_EVALUABLE, len(valores), None, None, ventanas_excluidas=excl_w, activos_excluidos=excl_a)
    boot = bootstrap_semanal([(d, float(v)) for d, v in valores])
    return ResultadoPolitica(policy, etiquetar(boot.ci_low, boot.ci_high, n=len(valores), capacidad=capacidad), len(valores), boot.mean, (boot.ci_low, boot.ci_high), boot.substitutions, excl_w, excl_a)


_SHA_GIT = re.compile(r"[0-9a-f]{40}\n?")
# Raíz del repositorio desde el que se importó este módulo: la identidad se valida sobre el código que de verdad
# se ejecuta, nunca sobre un repositorio elegido por el llamante.
REPO_ROOT = Path(__file__).resolve().parents[2]


def cargar_t024_code_sha(repo: str | Path = ".") -> str:
    """`T024_CODE_SHA` desde el sidecar canónico versionado en HEAD; sin override ni otra ruta.

    Se lee con `git show HEAD:<sidecar>`: un fichero sin commitear no cuenta. La copia de trabajo tiene que
    coincidir byte a byte con la de HEAD. El contenido es exactamente un SHA de 40 caracteres hexadecimales en
    minúscula, con un único salto de línea final opcional.
    """

    try:
        shown = subprocess.run(
            ["git", "show", f"HEAD:{comun.T024_CODE_LOCK}"], cwd=repo, check=False, capture_output=True, timeout=5.0
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise T024DecisionError(f"no se pudo leer el sidecar de T024_CODE_SHA: {exc}") from exc
    if shown.returncode != 0:
        raise T024DecisionError(f"sidecar de T024_CODE_SHA ausente o no versionado en HEAD ({comun.T024_CODE_LOCK})")
    contenido = shown.stdout
    try:
        trabajo = (Path(repo) / comun.T024_CODE_LOCK).read_bytes()
    except OSError as exc:
        raise T024DecisionError("sidecar de T024_CODE_SHA ausente en la copia de trabajo") from exc
    if trabajo != contenido:
        raise T024DecisionError("el sidecar de T024_CODE_SHA de la copia de trabajo no coincide con HEAD")
    try:
        texto = contenido.decode("ascii")
    except UnicodeDecodeError as exc:
        raise T024DecisionError("sidecar de T024_CODE_SHA con formato inválido") from exc
    if not _SHA_GIT.fullmatch(texto):
        raise T024DecisionError("sidecar de T024_CODE_SHA con formato inválido (40 hex en minúscula)")
    return texto.rstrip("\n")


def verificar_identidad() -> str:
    """Identidad congelada del código importado (`REPO_ROOT`); devuelve el `T024_CODE_SHA` validado."""

    return _verificar_identidad_en(REPO_ROOT)


def _verificar_identidad_en(repo: Path) -> str:
    """Comprobaciones de identidad sobre `repo`. Privada: la ruta pública solo la usa con `REPO_ROOT`."""

    code_sha = cargar_t024_code_sha(repo)
    if _git(["merge-base", "--is-ancestor", comun.T024_PREREG_SHA, "HEAD"], repo) is not True:
        raise T024DecisionError("T024_PREREG_SHA no es ancestro de HEAD")
    if _git(["merge-base", "--is-ancestor", code_sha, "HEAD"], repo) is not True:
        raise T024DecisionError("T024_CODE_SHA no es ancestro de HEAD")
    if not executor_unchanged_since(code_sha, repo):
        raise T024DecisionError("ejecutor cambiado desde T024_CODE_SHA")
    dirty = tree_dirty(repo)
    if dirty is not False:
        raise T024DecisionError("árbol de ejecutor no limpio")
    return code_sha


def _git(args: Sequence[str], repo: str | Path) -> Optional[bool]:
    try:
        return subprocess.run(["git", *args], cwd=repo, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    except OSError:
        return None



def cargar_registro_forward(path: Path, cosecha_decisiva: str) -> RegistroForward:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = tuple((str(item["data_vintage_id"]), date.fromisoformat(str(item["checkpoint"]))) for item in data["cosechas"])
    encoded = json.dumps(
        {"cosechas": [{"data_vintage_id": vintage_id, "checkpoint": checkpoint.isoformat()} for vintage_id, checkpoint in entries]},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    if digest != data.get("sha256"):
        raise T024DecisionError("hash del registro forward no cuadra")
    if tuple(sorted(entries, key=lambda item: item[1])) != entries:
        raise T024DecisionError("registro forward no ordenado")
    if cosecha_decisiva not in {vintage_id for vintage_id, _checkpoint in entries}:
        raise T024DecisionError("cosecha decisiva ausente del registro forward")
    return RegistroForward(entries, digest)


def checkpoint_de(registro: RegistroForward, cosecha_decisiva: str) -> date:
    for vintage_id, checkpoint in registro.cosechas:
        if vintage_id == cosecha_decisiva:
            return checkpoint
    raise T024DecisionError("cosecha decisiva ausente del registro forward")


def exigir_regla_75_dias(c_e: date, checkpoint: date) -> None:
    if checkpoint < c_e + timedelta(days=DIAS_COSECHA_DECISIVA):
        raise T024DecisionError("cosecha decisiva antes de c_e + 75 días")


def exigir_calendario_registro(registro: RegistroForward, c_e: date, cosecha_decisiva: str) -> None:
    """T-024 §9: `c_e` es un checkpoint del registro y la decisiva es la primera a 75 días o más de él."""

    checkpoints = [checkpoint for _vid, checkpoint in registro.cosechas]
    if c_e != C_E_FINAL and c_e not in checkpoints:
        raise T024DecisionError("c_e no es un checkpoint del registro forward")
    limite = c_e + timedelta(days=DIAS_COSECHA_DECISIVA)
    primera = next((vid for vid, checkpoint in registro.cosechas if checkpoint >= limite), None)
    if primera != cosecha_decisiva:
        raise T024DecisionError("la cosecha decisiva no es el primer checkpoint a 75 días o más de c_e")


def crear_marca_exclusiva(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(payload)


def _registro_miradas_path(evidence_dir: Path) -> Path:
    return evidence_dir / "miradas-t024.json"


def _leer_miradas(evidence_dir: Path) -> dict[str, object]:
    path = _registro_miradas_path(evidence_dir)
    if not path.exists():
        return {"consumidas": {}, "mirada_1_estados": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise T024DecisionError("registro de miradas inválido")
    return data


def _guardar_miradas(evidence_dir: Path, data: Mapping[str, object]) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    _registro_miradas_path(evidence_dir).write_text(json.dumps(data, sort_keys=True, indent=2), encoding="utf-8")


def politicas_para_mirada(*, mirada: str, c_e: date, evidence_dir: Path) -> tuple[str, ...]:
    if mirada not in {"mirada_1", "mirada_final"}:
        raise T024DecisionError("mirada no permitida")
    if (evidence_dir / f"{mirada}.t024.consumida").exists():
        raise T024DecisionError(f"{mirada} ya tiene marca")
    registro = _leer_miradas(evidence_dir)
    consumidas = registro.get("consumidas", {})
    if isinstance(consumidas, Mapping) and mirada in consumidas:
        raise T024DecisionError(f"{mirada} ya consumida")
    if mirada == "mirada_1":
        if c_e >= C_E_FINAL:
            raise T024DecisionError("mirada_1 exige c_e < C_E_FINAL")
        return comun.POLITICAS_DECISORIAS
    if c_e != C_E_FINAL:
        raise T024DecisionError("mirada_final exige c_e == C_E_FINAL")
    estados = registro.get("mirada_1_estados", {})
    marca_m1 = (evidence_dir / "mirada_1.t024.consumida").exists()
    if not isinstance(consumidas, Mapping) or "mirada_1" not in consumidas:
        if marca_m1:
            # T-024 §9: la mirada 1 se consumió al crear su marca; sin estados registrados no hay pendientes
            # conocidos y la final no puede reabrir B2 y S2 como si la mirada 1 no hubiera existido.
            raise T024DecisionError("mirada_1 con marca pero sin estados registrados: final denegada")
        return comun.POLITICAS_DECISORIAS
    if not isinstance(estados, Mapping):
        raise T024DecisionError("registro de estados inválido")
    pendientes = tuple(policy for policy in comun.POLITICAS_DECISORIAS if estados.get(policy) == NO_CONCLUYENTE)
    if not pendientes:
        raise T024DecisionError("mirada_final sin políticas pendientes")
    return pendientes


def validar_mirada(*, mirada: str, c_e: date, evidence_dir: Path) -> None:
    politicas_para_mirada(mirada=mirada, c_e=c_e, evidence_dir=evidence_dir)


def barras_decision(token: TokenMirada | None, cosecha: VintageLoad, universe: UniversoT024, symbol: str) -> tuple[BarraDecision, ...]:
    _exigir_token(token)
    asset = universe.get(symbol)
    views = cosecha.by_symbol[symbol]
    sessions = comun.local_dates(views.execution_prices.index, asset.timezone)
    dividends = views.raw["Dividends"].astype(float).reindex(views.execution_prices.index).fillna(0.0)
    rows: list[BarraDecision] = []
    for session, (_, row), dividend in zip(sessions, views.execution_prices.iterrows(), dividends):
        rows.append(
            BarraDecision(
                session=session,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                dividend=float(dividend),
                origen=f"cosecha:{cosecha.data_vintage_id}",
            )
        )
    return tuple(rows)


def _region_de(universe: UniversoT024, symbol: str) -> str:
    asset = universe.get(symbol)
    region = getattr(asset, "region", None)
    if region is None:
        raise T024DecisionError(f"{symbol}: activo sin región para D3")
    return str(region)


def _descriptivos_d3_d4(
    ventanas: Sequence[VentanaT024],
    barras_por_activo: Mapping[str, Sequence[BarraDecision]],
    universe: UniversoT024,
    t1_por_activo: Mapping[str, date],
) -> Mapping[str, object]:
    regiones: dict[str, dict[str, Sequence[BarraDecision]]] = defaultdict(dict)
    for symbol, rows in barras_por_activo.items():
        regiones[_region_de(universe, symbol)][symbol] = _truncate_barras(rows, t1_por_activo[symbol])
    indices = {region: indice_equiponderado_region(series) for region, series in regiones.items()}
    d3_values: list[float] = []
    d4_values: list[float] = []
    d4_truncadas = 0
    por_politica: dict[str, _D3D4Bucket] = {}
    for ventana in ventanas:
        symbol = ventana.senal.asset
        rows = barras_por_activo[symbol]
        region = _region_de(universe, symbol)
        d3 = d3_region(ventana, rows, indices[region])
        d4, truncada = d4_40_sesiones(ventana, rows, t1=t1_por_activo[symbol])
        d3_values.append(d3)
        d4_values.append(d4)
        d4_truncadas += int(truncada)
        bucket = por_politica.setdefault(ventana.senal.policy, _D3D4Bucket([], []))
        bucket.d3.append(d3)
        bucket.d4.append(d4)
        bucket.d4_truncadas += int(truncada)
    return {
        "d3_media": media(d3_values),
        "d3_n": len(d3_values),
        "d4_media": media(d4_values),
        "d4_n": len(d4_values),
        "d4_truncadas": d4_truncadas,
        "por_politica": {
            policy: {
                "d3_media": media(values.d3),
                "d3_n": len(values.d3),
                "d4_media": media(values.d4),
                "d4_n": len(values.d4),
                "d4_truncadas": values.d4_truncadas,
            }
            for policy, values in sorted(por_politica.items())
        },
    }


def _fx_eur_descriptivo(
    ventanas: Sequence[VentanaT024],
    barras_por_activo: Mapping[str, Sequence[BarraDecision]],
    fx: Optional[FxCausal],
) -> Optional[Mapping[str, object]]:
    if fx is None:
        return {"motivo": "FX forward no congelado"}
    values: list[float] = []
    for ventana in ventanas:
        rows = barras_por_activo[ventana.senal.asset]
        entry_at = datetime.combine(rows[ventana.e_index].session, time(0), UTC)
        exit_at = datetime.combine(rows[ventana.x_index].session, time(0), UTC)
        values.append(retorno_eur(ventana.l_i, "EUR", entry_at, exit_at, fx))
    return {"media_l_i_eur": media(values), "n": len(values)}


def construir_resultado(
    token: TokenMirada | None,
    config: AdvisorConfig,
    universe: UniversoT024,
    cosecha_decisiva: VintageLoad,
    *,
    c_e: date,
    policies: Sequence[str],
    fx: Optional[FxCausal] = None,
) -> ResultadoDecision:
    _exigir_token(token)
    from advisor.research import t024_captura as captura

    signals: list[SenalT024] = []
    for policy in tuple(policies) + comun.POLITICAS_DESCRIPTIVAS:
        generated, _counts = captura.generar_senales_operar(config=config, universe=universe, vintage=cosecha_decisiva, policy=policy, c_e=c_e)
        signals.extend(generated)
    symbols = sorted({signal.asset for signal in signals})
    barras_por_activo = {symbol: barras_decision(token, cosecha_decisiva, universe, symbol) for symbol in symbols}
    t1_por_activo = {symbol: rows[-1].session for symbol, rows in barras_por_activo.items() if rows}
    ventanas = construir_ventanas(signals, barras_por_activo, c_e=c_e, t1_por_activo=t1_por_activo)
    # T-024 §5 (D3): el índice de región usa todos los activos analizables con barras en la cosecha decisiva,
    # no solo los que tuvieron señal.
    region_symbols = sorted(set(symbols) | {s for s in captura.asset_list() if s in cosecha_decisiva.by_symbol})
    barras_region = {
        symbol: barras_por_activo.get(symbol) or barras_decision(token, cosecha_decisiva, universe, symbol)
        for symbol in region_symbols
    }
    t1_region = {symbol: rows[-1].session for symbol, rows in barras_region.items() if rows}
    politicas = {policy: decidir_politica(policy, ventanas) for policy in policies}
    phi_medio = {
        policy: float(media(v.phi_a for v in ventanas.ventanas if v.senal.policy == policy) or 0.0)
        for policy in tuple(policies) + comun.POLITICAS_DESCRIPTIVAS
    }
    d3_d4 = _descriptivos_d3_d4(ventanas.ventanas, barras_region, universe, t1_region)
    descriptivas: dict[str, object] = {
        "C0": decidir_politica("C0", ventanas, capacidad=True),
        "d2_media_por_politica": {
            policy: media(v.d2 for v in ventanas.ventanas if v.senal.policy == policy and v.d2 is not None)
            for policy in tuple(policies) + comun.POLITICAS_DESCRIPTIVAS
        },
        "d2o_media": media(v.d2o for v in ventanas.ventanas if v.d2o is not None),
        "d2c_media": media(v.d2c for v in ventanas.ventanas if v.d2c is not None),
        "d1_media": media(v.d1 for v in ventanas.ventanas),
        "d3_media": d3_d4["d3_media"],
        "d3_n": d3_d4["d3_n"],
        "d4_media": d3_d4["d4_media"],
        "d4_n": d3_d4["d4_n"],
        "d4_truncadas": d3_d4["d4_truncadas"],
        "d3_d4_por_politica": d3_d4["por_politica"],
        "convencion_b_media": media(v.d2_b for v in ventanas.ventanas if v.d2_b is not None),
        "coste_prorrateado_media": media(v.d2_coste_prorrateado for v in ventanas.ventanas if v.d2_coste_prorrateado is not None),
        "rechazos_ejecutabilidad": ventanas.rechazos_ejecutabilidad,
    }
    return ResultadoDecision(
        politicas=politicas,
        descriptivas=descriptivas,
        phi_medio=phi_medio,
        ignoradas_no_solapamiento=ventanas.ignoradas_no_solapamiento,
        ventanas_truncadas_t1=sum(1 for ventana in ventanas.ventanas if ventana.truncada_t1),
        eur=_fx_eur_descriptivo(ventanas.ventanas, barras_por_activo, fx),
    )


def _registrar_consumo(
    evidence_dir: Path,
    mirada: str,
    c_e: date,
    policies: Sequence[str],
    resultado: ResultadoDecision | Mapping[str, ResultadoPolitica],
) -> None:
    reg = _leer_miradas(evidence_dir)
    raw_consumidas = reg.get("consumidas", {})
    consumidas: dict[str, object] = dict(raw_consumidas) if isinstance(raw_consumidas, Mapping) else {}
    consumidas[mirada] = {"c_e": c_e.isoformat(), "policies": list(policies)}
    reg["consumidas"] = consumidas
    if mirada == "mirada_1":
        if isinstance(resultado, ResultadoDecision):
            reg["mirada_1_estados"] = {policy: resultado.politicas[policy].etiqueta for policy in policies}
        else:
            reg["mirada_1_estados"] = {policy: resultado[policy].etiqueta for policy in resultado if policy in policies}
    _guardar_miradas(evidence_dir, reg)


def ejecutar_mirada(
    *,
    mirada: str,
    c_e: date,
    config: AdvisorConfig,
    universe: UniversoT024,
    cosecha_decisiva: VintageLoad,
    cosecha_decisiva_id: str,
    registro_forward_path: Path,
    evidence_dir: Path,
) -> ResultadoDecision | Mapping[str, ResultadoPolitica] | str:
    code_sha = verificar_identidad()
    policies = politicas_para_mirada(mirada=mirada, c_e=c_e, evidence_dir=evidence_dir)
    registro_forward = cargar_registro_forward(registro_forward_path, cosecha_decisiva_id)
    if cosecha_decisiva.data_vintage_id != cosecha_decisiva_id:
        raise T024DecisionError("la cosecha recibida no es la cosecha decisiva declarada")
    checkpoint = checkpoint_de(registro_forward, cosecha_decisiva_id)
    exigir_regla_75_dias(c_e, checkpoint)
    exigir_calendario_registro(registro_forward, c_e, cosecha_decisiva_id)
    captura = capturar(config, universe, cosecha_decisiva, c_e=c_e, desarrollo=False)
    conteos: Mapping[str, ConteoCaptura] = captura.conteos
    evaluables = tuple(p for p in policies if conteos.get(p) is not None and conteos[p].cumple)
    if mirada == "mirada_1" and evaluables != tuple(policies):
        return REPROPONER
    marca = evidence_dir / f"{mirada}.t024.consumida"
    payload = json.dumps(
        {
            "T024_PREREG_SHA": comun.T024_PREREG_SHA,
            "T024_CODE_SHA": code_sha,
            "registro_forward_sha256": registro_forward.sha256,
            "mirada": mirada,
            "c_e": c_e.isoformat(),
            "checkpoint": checkpoint.isoformat(),
            "cosecha_decisiva": cosecha_decisiva_id,
        },
        sort_keys=True,
        indent=2,
    )
    crear_marca_exclusiva(marca, payload)
    # T-024 §9 regla 3: en la mirada final, la política sin capacidad queda NO EVALUABLE y las demás se evalúan.
    sin_capacidad = {p: ResultadoPolitica(p, NO_EVALUABLE, 0, None, None) for p in policies if p not in evaluables}
    if not evaluables:
        _registrar_consumo(evidence_dir, mirada, c_e, policies, sin_capacidad)
        return sin_capacidad
    token = _crear_token_mirada(marca)
    global _TOKEN_ACTIVO
    _TOKEN_ACTIVO = token
    try:
        resultado_decision = construir_resultado(token, config, universe, cosecha_decisiva, c_e=c_e, policies=evaluables)
    finally:
        _TOKEN_ACTIVO = None
    if sin_capacidad:
        resultado_decision = replace(resultado_decision, politicas={**resultado_decision.politicas, **sin_capacidad})
    _registrar_consumo(evidence_dir, mirada, c_e, policies, resultado_decision)
    return resultado_decision


def siguiente_mirada(estados_m1: Optional[Mapping[str, str]], corte_propuesto: date) -> tuple[str, tuple[str, ...]]:
    if estados_m1 is None and corte_propuesto > C_E_FINAL:
        return "mirada_final", comun.POLITICAS_DECISORIAS
    if estados_m1 is None:
        return "mirada_1", comun.POLITICAS_DECISORIAS
    pendientes = tuple(p for p, estado in estados_m1.items() if estado == NO_CONCLUYENTE)
    return "mirada_final", pendientes
