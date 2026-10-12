"""Fase de datos de una ejecución de T-025 (ficha §3.3, §5, §7.2, §8.7; D-78).

Toda petición se hace aquí, antes de procesar ningún libro, y con un conjunto fijo para todo el universo
(activos, benchmarks, contexto y FX), así que ni el conjunto ni su momento dependen de un libro.

- Primero el **conjunto testigo** (``^VIX`` y ``EURUSD=X``). Si falla o viene vacío, toda la ejecución es
  ``FETCH_FAILURE``: con ``yfinance`` una respuesta vacía no se distingue de un fallo de red, y eso es una
  caída del motor, no una ausencia del proveedor (no avanza ningún plazo).
- Con el testigo correcto, cada objeto se pide con una ventana que abarca sesiones ya guardadas. Una sesión
  pendiente que no llega es ``PROVIDER_DATA_MISSING``; un error de transporte de ese objeto, ``FETCH_FAILURE``.
- Precios de ``get_raw_history`` (``auto_adjust=False``, ``actions=True``): la base de P6. Nunca la caché
  ``validated_bar`` (§3.3). Manda la primera observación de cada sesión.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Protocol, Sequence, Set, Tuple

import pandas as pd

from paper.store import PaperStore
from paper.universe import FX_MARKET, PaperUniverse, closed_by, sessions

WITNESS = ("^VIX", "EURUSD=X")
WARMUP_DAYS = 760
OVERLAP_DAYS = 21
RESCALE_THRESHOLD = 0.2  # un cambio de escala real; las revisiones menores de un cierre no lo son
SPLIT_LIKE = (2.0, 3.0, 4.0, 5.0, 10.0, 1.5, 1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 10, 2 / 3)
SPLIT_LIKE_TOLERANCE = 0.01
PROVIDER = "yfinance:get_raw_history:auto_adjust=False"


class Provider(Protocol):
    def get_raw_history(self, symbol: str, period: str = "1y", interval: str = "1d", *, drop_na: bool = True,
                        start: Optional[str] = None, end: Optional[str] = None) -> pd.DataFrame: ...


class EmptyResponse(ValueError):
    pass


@dataclass
class IngestReport:
    fetch_failure: bool = False
    witness_error: str = ""
    obtained: int = 0
    missing: int = 0
    failures: List[str] = field(default_factory=list)
    alerts: int = 0


def _iso(value: datetime) -> str:
    return value.astimezone().isoformat() if value.tzinfo is None else value.isoformat()


def _session_of(timestamp: pd.Timestamp, market: str) -> date:
    if market == FX_MARKET:
        return pd.Timestamp(timestamp).tz_convert("Europe/London").date()
    from advisor.data.sessions import session_date_of

    day = session_date_of(timestamp, market)
    if day is None:
        raise ValueError(f"{market}: plaza sin sesión declarada")
    return day


def _vigente(store: PaperStore, symbol: str, as_of: str) -> Dict[str, Any]:
    return {day: bar.row for day, bar in usable_bars(store, symbol, as_of=as_of).items()}


@dataclass(frozen=True)
class UsableBar:
    row: Any
    available_at: str  # desde cuándo puede usarse: ``observed_at``, o la resolución D-80 que la liberó
    released: bool = False


def usable_bars(store: PaperStore, symbol: str, *, as_of: str) -> Dict[str, UsableBar]:
    """Primera barra utilizable de cada sesión hasta ``as_of``: las coherentes (``scale_doubtful = 0``) y las
    bloqueadas por un ``SCALE_MISMATCH`` que el propietario liberó como hueco real (D-80).

    Una barra dudosa de la sesión ``d`` se libera si la última alerta de escala en o antes de ``d`` tiene una
    resolución ``REAL_GAP_CONFIRMED`` y no queda ningún bloqueo anterior sin resolver. Solo es utilizable desde
    la resolución (nunca antes): su precio es real, pero se supo que lo era al registrarla.
    """

    out: Dict[str, UsableBar] = {}
    for row in store.rows(
        "SELECT * FROM paper_bar_observation WHERE data_symbol = ? AND scale_doubtful = 0 AND observed_at <= ? "
        "ORDER BY session_date, observed_at", (symbol, as_of),
    ):
        if row["session_date"] not in out:
            out[row["session_date"]] = UsableBar(row, row["observed_at"])
    resolutions = {r["session_date"]: r["observed_at"] for r in store.rows(
        "SELECT session_date, observed_at FROM paper_scale_resolution WHERE data_symbol = ? "
        "AND resolution = 'REAL_GAP_CONFIRMED' AND observed_at <= ?", (symbol, as_of))}
    if not resolutions:
        return out
    alerts = sorted(r["session_date"] for r in store.rows(
        "SELECT session_date FROM paper_data_alert WHERE object = ? AND kind = 'SCALE_CHANGE_UNEXPLAINED' AND detected_at <= ?",
        (symbol, as_of)))
    blocked = unresolved_scale_mismatch(store, symbol, as_of=as_of)
    for row in store.rows(
        "SELECT * FROM paper_bar_observation WHERE data_symbol = ? AND scale_doubtful = 1 AND observed_at <= ? "
        "ORDER BY session_date, observed_at", (symbol, as_of),
    ):
        day = row["session_date"]
        if blocked is not None and day >= blocked.isoformat():
            continue
        governing = [a for a in alerts if a <= day]
        if not governing or governing[-1] not in resolutions:
            continue
        available = max(row["observed_at"], resolutions[governing[-1]])
        current = out.get(day)
        if current is None or available < current.available_at:
            out[day] = UsableBar(row, available, released=True)
    return out


def fetch(provider: Provider, symbol: str, start: date, end: date) -> pd.DataFrame:
    try:
        frame = provider.get_raw_history(symbol, interval="1d", start=start.isoformat(), end=end.isoformat())
    except ValueError as exc:
        if "No se han recibido datos" in str(exc) or "vacíos" in str(exc):
            raise EmptyResponse(str(exc)) from exc
        raise
    if frame is None or frame.empty:
        raise EmptyResponse(f"{symbol}: respuesta vacía")
    return frame


class Ingestor:
    """Ejecuta la fase de datos dentro de la transacción del llamador."""

    def __init__(self, store: PaperStore, universe: PaperUniverse, provider: Provider, *, now: datetime,
                 paper_run_id: str, start: date) -> None:
        self.store = store
        self.universe = universe
        self.provider = provider
        self.now = now
        self.observed_at = now.isoformat()
        self.run_id = paper_run_id
        self.start = start
        self.report = IngestReport()

    def run(self) -> IngestReport:
        today = self.now.date()
        for symbol in WITNESS:
            try:
                fetch(self.provider, symbol, today - timedelta(days=OVERLAP_DAYS), today + timedelta(days=1))
            except Exception as exc:
                self.report.fetch_failure = True
                self.report.witness_error = f"{symbol}: {type(exc).__name__}: {exc}"
                self._alert("WITNESS", "FETCH_FAILURE", today)
                return self.report
        for asset in self.universe.assets:
            self._object(asset.data_symbol, asset.market, asset.currency, kind="bar")
        for symbol in self.universe.benchmark_symbols():
            self._object(symbol, self.universe.market_of(symbol), "", kind="bar")
        for symbol in self.universe.context_symbols:
            self._object(symbol, self.universe.market_of(symbol), "", kind="context")
        for pair in self.universe.fx_pairs():
            self._object(pair, FX_MARKET, "", kind="fx")
        return self.report

    # ------------------------------------------------------------------ objetos

    def _known_sessions(self, symbol: str, kind: str) -> Set[str]:
        if kind == "bar":
            return set(_vigente(self.store, symbol, self.observed_at))
        if kind == "context":
            return {r["bar_timestamp"] for r in self.store.rows("SELECT bar_timestamp FROM paper_context_observation WHERE series = ?", (symbol,))}
        return {r["session_date"] for r in self.store.rows("SELECT session_date FROM paper_fx_quote WHERE fx_pair = ?", (symbol,))}

    def _pending_sessions(self, symbol: str, market: str, known: Set[str]) -> List[date]:
        """Sesiones exigibles (cerradas y liquidadas) desde el inicio de la cohorte sin barra vigente."""

        out = []
        for day in sessions(market, self.start, self.now.date()):
            if closed_by(market, day, self.now, self.universe.settlement_minutes) and day.isoformat() not in known:
                out.append(day)
        return out

    def _object(self, symbol: str, market: str, currency: str, *, kind: str) -> None:
        stored = self._known_sessions(symbol, kind) if kind != "context" else set()
        if kind == "bar" or kind == "fx":
            known_days = stored
        else:
            known_days = {
                _session_of(pd.Timestamp(ts), market).isoformat()
                for ts in self._known_sessions(symbol, "context")
            } if market != FX_MARKET else set()
        pending = self._pending_sessions(symbol, market, known_days)
        if known_days:
            first = max(date.fromisoformat(min(known_days)), date.fromisoformat(max(known_days)) - timedelta(days=OVERLAP_DAYS))
        else:
            first = self.start - timedelta(days=WARMUP_DAYS)
        if pending:
            first = min(first, pending[0] - timedelta(days=OVERLAP_DAYS))
        try:
            frame = fetch(self.provider, symbol, first, self.now.date() + timedelta(days=1))
        except EmptyResponse:
            self._requests(symbol, pending, set(), "PROVIDER_DATA_MISSING")
            return
        except Exception as exc:
            self.report.failures.append(f"{symbol}: {type(exc).__name__}")
            self._requests(symbol, pending, set(), "FETCH_FAILURE")
            return
        received = self._store_frame(symbol, market, currency, frame, kind=kind)
        self._requests(symbol, pending, received, "PROVIDER_DATA_MISSING")

    def _requests(self, symbol: str, pending: Sequence[date], received: Set[str], missing_result: str) -> None:
        for day in pending:
            result = "OBTAINED" if day.isoformat() in received else missing_result
            self.store.insert_first(
                "paper_bar_request",
                {"paper_run_id": self.run_id, "object": symbol, "session_date": day.isoformat(), "due": 1,
                 "requested_at": self.observed_at, "result": result},
                ("paper_run_id", "object", "session_date"),
            )
            if result == "OBTAINED":
                self.report.obtained += 1
            elif result == "PROVIDER_DATA_MISSING":
                self.report.missing += 1
                self._alert(symbol, "BAR_MISSING", day)

    def _store_frame(self, symbol: str, market: str, currency: str, frame: pd.DataFrame, *, kind: str) -> Set[str]:
        received: Set[str] = set()
        rows: List[Tuple[date, pd.Timestamp, Any]] = []
        actions: List[Tuple[date, Any]] = []
        for ts, bar in frame.iterrows():
            stamp = pd.Timestamp(ts)
            if stamp.tzinfo is None:
                stamp = stamp.tz_localize("UTC")
            day = _session_of(stamp, market)
            if market != FX_MARKET and day not in sessions(market, day, day):
                # Fila en un día que no es sesión de la plaza: se descarta y se avisa a nivel de dato.
                self._alert(symbol, "NON_SESSION_ROW", day)
                continue
            actions.append((day, bar))
            if not closed_by(market, day, self.now, self.universe.settlement_minutes):
                continue  # barra no cerrada: nunca se guarda (sus acciones corporativas sí se conocen ya)
            rows.append((day, stamp, bar))
        if kind == "context":
            for day, stamp, bar in rows:
                close = float(bar["Close"])
                if math.isfinite(close):
                    self.store.insert_first(
                        "paper_context_observation",
                        {"series": symbol, "bar_timestamp": stamp.isoformat(), "close": close,
                         "observed_at": self.observed_at, "provider": PROVIDER},
                        ("series", "bar_timestamp"),
                    )
                    received.add(day.isoformat())
            return received
        if kind == "fx":
            for day, stamp, bar in rows:
                rate = float(bar["Close"])
                if math.isfinite(rate) and rate > 0:
                    self.store.insert_first(
                        "paper_fx_quote",
                        {"fx_pair": symbol, "bar_timestamp": stamp.isoformat(), "session_date": day.isoformat(),
                         "timestamp_available": (stamp + pd.Timedelta(hours=24)).isoformat(), "rate": rate,
                         "provider": PROVIDER, "observed_at": self.observed_at},
                        ("fx_pair", "bar_timestamp"),
                    )
                    received.add(day.isoformat())
            return received
        vigente = _vigente(self.store, symbol, self.observed_at)
        for day, bar in actions:
            for column, action_kind in (("Dividends", "DIVIDEND"), ("Stock Splits", "SPLIT")):
                value = float(bar.get(column, 0.0) or 0.0)
                if value > 0 and math.isfinite(value):
                    self._corporate_action(symbol, action_kind, day, value, currency)
        self._scale_doubtful(symbol, rows, vigente, actions)
        blocked_from = unresolved_scale_mismatch(self.store, symbol, as_of=self.observed_at)
        for day, stamp, bar in rows:
            values = [float(bar[c]) for c in ("Open", "High", "Low", "Close")]
            if not all(math.isfinite(v) for v in values) or day.isoformat() in vigente:
                continue
            # §8.6: desde la primera barra en otra escala sin split observado, ninguna barra posterior entra
            # (cuenta como dato ausente) hasta que llega el split del proveedor o uno manual con D-nn.
            doubtful = blocked_from is not None and day >= blocked_from
            any_row = self.store.one(
                "SELECT 1 FROM paper_bar_observation WHERE data_symbol = ? AND session_date = ?", (symbol, day.isoformat()))
            if doubtful and any_row is not None:
                continue  # una sola fila dudosa por sesión; una observación coherente posterior sí entra
            self.store.conn.execute(
                "INSERT INTO paper_bar_observation (data_symbol, session_date, bar_timestamp, open, high, low, close, volume, "
                "observed_at, provider, request, scale_doubtful) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (symbol, day.isoformat(), stamp.isoformat(), *values, float(bar.get("Volume", 0.0) or 0.0),
                 self.observed_at, PROVIDER, "start/end", int(doubtful)),
            )
            if not doubtful:
                received.add(day.isoformat())
        return received

    def _scale_doubtful(self, symbol: str, rows: Sequence[Tuple[date, pd.Timestamp, Any]], vigente: Dict[str, Any],
                        actions: Sequence[Tuple[date, Any]] = ()) -> Optional[date]:
        """Registra un cambio de escala sin split observado (``SCALE_MISMATCH``, §3.3, §8.6) y devuelve su
        primera sesión, o ``None``. Nunca se adivina el factor.

        1. **Solape.** Cada barra ya guardada se compara con la nueva multiplicada por los splits con fecha ex
           posterior que la guardada todavía no reflejaba. Un cambio de escala real (más del 20 %) en la mayoría
           del solape que ningún split explica: la escala de la respuesta no es la guardada.
        2. **Salto de split no publicado.** Entre barras consecutivas de la misma respuesta, una apertura que
           salta en un factor de split (±1 %) sin un split observado en esa sesión.

        El bloqueo vive en ``paper_data_alert`` y se resuelve solo con un ``SPLIT`` (:func:`unresolved_scale_mismatch`).
        Una revisión menor de un cierre no es un cambio de escala (manda la primera observación).
        """

        from paper.inputs import _splits

        rows_known = self.store.rows(
            "SELECT ex_date FROM paper_corporate_action WHERE data_symbol = ? AND kind = 'SPLIT' AND observed_at <= ?",
            (symbol, self.observed_at))
        # Solo el proveedor reajusta su propio histórico (un split manual, desde que el proveedor lo confirma).
        known = _splits(self.store, symbol, datetime.fromisoformat(self.observed_at), provider_only=True)
        new_splits = [(day, float(bar.get("Stock Splits", 0.0) or 0.0)) for day, bar in actions
                      if float(bar.get("Stock Splits", 0.0) or 0.0) > 0]
        split_days = {date.fromisoformat(r["ex_date"]) for r in rows_known} | {d for d, _r in new_splits}
        overlap = 0
        rescaled = 0
        for day, _stamp, bar in rows:
            old = vigente.get(day.isoformat())
            close = float(bar["Close"])
            if old is None or not (close > 0 and math.isfinite(close)):
                continue
            expected = 1.0
            for ex_date, ratio, observed in known:
                if ex_date > day and observed > old["observed_at"]:
                    expected *= ratio
            overlap += 1
            if abs(float(old["close"]) / close / expected - 1.0) > RESCALE_THRESHOLD:
                rescaled += 1
        new_days = [day for day, _s, _b in rows if day.isoformat() not in vigente]
        if overlap and rescaled * 2 >= overlap and new_days:
            self._alert(symbol, "SCALE_CHANGE_UNEXPLAINED", min(new_days))
            return min(new_days)
        previous: Optional[float] = None
        for day, _stamp, bar in rows:
            close, opening = float(bar["Close"]), float(bar["Open"])
            if previous is not None and previous > 0 and opening > 0 and day.isoformat() not in vigente:
                jump = opening / previous
                if day not in split_days and any(abs(jump / f - 1.0) <= SPLIT_LIKE_TOLERANCE for f in SPLIT_LIKE):
                    self._alert(symbol, "SCALE_CHANGE_UNEXPLAINED", day)
                    return day
            previous = close
        return None

    def _corporate_action(self, symbol: str, kind: str, day: date, value: float, currency: str) -> None:
        row = {"data_symbol": symbol, "kind": kind, "ex_date": day.isoformat(),
               "amount": value if kind == "DIVIDEND" else 0.0, "ratio": value if kind == "SPLIT" else 0.0,
               "currency": currency, "observed_at": self.observed_at, "provider": PROVIDER}
        if not self.store.insert_first("paper_corporate_action", row, ("data_symbol", "kind", "ex_date")):
            first = self.store.one(
                "SELECT amount, ratio FROM paper_corporate_action WHERE data_symbol = ? AND kind = ? AND ex_date = ?",
                (symbol, kind, day.isoformat()),
            )
            assert first is not None
            manual = self.store.one(
                "SELECT 1 FROM paper_corporate_action WHERE data_symbol = ? AND kind = ? AND ex_date = ? AND provider = 'manual'",
                (symbol, kind, day.isoformat()),
            )
            # Una revisión distinta, o la confirmación del proveedor de un split manual (desde entonces su serie
            # ya viene reajustada), se registran sin cambiar la primera observación.
            if manual is not None and kind == "SPLIT" and abs(float(first["ratio"]) - value) > 1e-9:
                self._alert(symbol, "SCALE_CHANGE_UNEXPLAINED", day)  # el proveedor no confirma el ratio manual
            if manual is not None or (float(first["amount"]), float(first["ratio"])) != (row["amount"], row["ratio"]):
                self.store.insert_first(
                    "paper_corporate_action_revision",
                    {"data_symbol": symbol, "kind": kind, "ex_date": day.isoformat(), "amount": row["amount"],
                     "ratio": row["ratio"], "observed_at": self.observed_at},
                    ("data_symbol", "kind", "ex_date", "observed_at"),
                )

    def _alert(self, obj: str, kind: str, day: date) -> None:
        if self.store.insert_first(
            "paper_data_alert", {"object": obj, "kind": kind, "session_date": day.isoformat(), "detected_at": self.observed_at},
            ("object", "kind", "session_date"),
        ):
            self.report.alerts += 1


def unresolved_scale_mismatch(store: PaperStore, symbol: str, *, as_of: str) -> Optional[date]:
    """Primera sesión de un ``SCALE_MISMATCH`` sin resolver del activo, o ``None`` (§8.6).

    Un cambio de escala detectado en la sesión ``d`` queda resuelto solo con una resolución manual
    ``REAL_GAP_CONFIRMED`` de esa sesión exacta (D-80), o con un ``SPLIT`` observado
    (del proveedor, o manual con fuente oficial verificable y D-nn) con fecha ex posterior a la última sesión
    vigente anterior a ``d`` (la del solape puede detectarse antes de su fecha ex, si faltan sesiones). Mientras
    no lo esté, ninguna barra de ``d`` en adelante entra en la serie.
    """

    splits = [date.fromisoformat(r["ex_date"]) for r in store.rows(
        "SELECT ex_date FROM paper_corporate_action WHERE data_symbol = ? AND kind = 'SPLIT' AND observed_at <= ?",
        (symbol, as_of))]
    gaps = {r["session_date"] for r in store.rows(
        "SELECT session_date FROM paper_scale_resolution WHERE data_symbol = ? AND resolution = 'REAL_GAP_CONFIRMED' "
        "AND observed_at <= ?", (symbol, as_of))}
    unresolved: List[date] = []
    for row in store.rows(
        "SELECT session_date FROM paper_data_alert WHERE object = ? AND kind = 'SCALE_CHANGE_UNEXPLAINED' AND detected_at <= ?",
        (symbol, as_of),
    ):
        if row["session_date"] in gaps:
            continue  # D-80: hueco real confirmado por el propietario para esa sesión exacta
        day = date.fromisoformat(row["session_date"])
        before = store.one(
            "SELECT MAX(session_date) AS m FROM paper_bar_observation WHERE data_symbol = ? AND scale_doubtful = 0 "
            "AND session_date < ? AND observed_at <= ?", (symbol, day.isoformat(), as_of),
        )
        previous = date.fromisoformat(before["m"]) if before is not None and before["m"] else date.min
        if not any(previous < ex for ex in splits):
            unresolved.append(day)
    return min(unresolved) if unresolved else None


def register_manual_split(store: PaperStore, symbol: str, *, ex_date: date, ratio: float, currency: str,
                          source_url: str, source_sha256: str, decision_ref: str, now: datetime) -> bool:
    """Split manual con fuente oficial verificable y D-nn (§8.6): resuelve un ``SCALE_MISMATCH`` sin reescribir
    nada; se aplica causalmente desde que se registra (``late`` si la frontera ya pasó la fecha ex)."""

    if not (ratio > 0 and math.isfinite(ratio)) or not source_url or not source_sha256 or not decision_ref:
        raise ValueError("un split manual exige ratio, fuente oficial, su sha256 y una D-nn")
    return store.insert_first("paper_corporate_action", {
        "data_symbol": symbol, "kind": "SPLIT", "ex_date": ex_date.isoformat(), "amount": 0.0, "ratio": ratio,
        "currency": currency, "observed_at": now.isoformat(), "provider": "manual", "terminal_kind": "",
        "source_url": source_url, "source_sha256": source_sha256, "decision_ref": decision_ref,
    }, ("data_symbol", "kind", "ex_date"))


def register_real_gap(store: PaperStore, symbol: str, *, session_date: date, source_url: str, evidence_sha256: str,
                      decision_ref: str, now: datetime) -> bool:
    """``REAL_GAP_CONFIRMED / NO_SPLIT`` (D-80): el propietario confirma que el salto de escala de esa sesión es un
    hueco real de precio y no un split. Libera el ``SCALE_MISMATCH`` de esa sesión exacta; nunca se infiere.

    Exige que exista el ``SCALE_MISMATCH`` de esa sesión, una fuente verificable, el sha256 de la evidencia y la
    D-nn. Append-only: no se puede retirar ni cambiar.
    """

    if (not source_url.strip() or re.fullmatch(r"[0-9a-f]{64}", evidence_sha256) is None
            or re.fullmatch(r"D-\d+", decision_ref) is None):
        raise ValueError("REAL_GAP_CONFIRMED exige fuente verificable, sha256 de la evidencia y D-nn (D-80)")
    if store.one("SELECT 1 FROM paper_data_alert WHERE object = ? AND kind = 'SCALE_CHANGE_UNEXPLAINED' AND session_date = ?",
                 (symbol, session_date.isoformat())) is None:
        raise ValueError(f"{symbol} {session_date}: no hay SCALE_MISMATCH en esa sesión exacta")
    return store.insert_first("paper_scale_resolution", {
        "data_symbol": symbol, "session_date": session_date.isoformat(), "resolution": "REAL_GAP_CONFIRMED",
        "source_url": source_url, "evidence_sha256": evidence_sha256, "decision_ref": decision_ref,
        "observed_at": now.isoformat(),
    }, ("data_symbol", "session_date"))
