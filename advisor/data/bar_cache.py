"""Caché local de barras de sesión cerrada ya validadas (C-09, T-018, D-41).

El proveedor **retira** por la mañana barras EOD europeas que ya había servido
la tarde anterior: `SAP.DE` el 14 a las 20:02 tiene la barra del 14, a las 06:02
del 15 vuelve a la del 11, y al mediodía reaparece. El bot ya vio ese dato, así
que no hace falta pagar una segunda fuente para reconstruirlo: basta con no
perderlo (D-41).

Esta capa cambia **de dónde sale una barra**, no qué se hace con ella. No toca
el score, la geometría, los umbrales, `classify()`, el veto de D-21 ni la regla
de barra abierta de D-37.

Las cinco reglas del propietario, y dónde vive cada una:

1. Persistir la barra de sesión cerrada y exigible ya validada → `_bars_to_store`.
2. La caché nunca crea una barra no observada → solo se reinyecta lo guardado,
   y un reajuste se reancla con lo que el proveedor sirve, sin aritmética.
3. Sesión exigible jamás recibida sigue siendo `MISSING_RECENT_DATA` → la caché
   no rellena ese hueco; lo cuenta (`sessions_never_observed`).
4. Una barra revisada no se sobrescribe en silencio → `validated_bar_revision`,
   y manda la primera validada (decisión del propietario).
5. Trazabilidad → `SymbolCacheUsage` viaja a la medición de frescura (INV-21).

Y la sexta, que es la que decide si además se compra una segunda fuente de
precios: el recuento de `sesión exigible + nunca observada + no entregada`.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

import pandas as pd

from advisor.data.calendars import expected_sessions
from advisor.data.freshness import mercado_para_simbolo
from advisor.data.sessions import (
    SYMBOL_MARKETS,
    _session_date,
    latest_expected_closed_session,
    market_for_symbol,
    market_timezone,
)
from advisor.universe.models import Universe

logger = logging.getLogger(__name__)

BAR_COLUMNS: Tuple[str, ...] = ("Open", "High", "Low", "Close", "Volume")

KIND_REVISION = "REVISION"
KIND_READJUSTMENT = "REAJUSTE"

STATUS_DISABLED = "SIN_CACHE"
"""La caché no actuó: desactivada, intervalo no diario o plaza sin declarar."""

STATUS_LIVE = "FUENTE_VIVA"
"""La fuente viva sirvió todo lo exigible que la caché conocía."""

STATUS_SERVED = "SERVIDA_POR_CACHE"
"""Al menos una barra la devolvió la caché porque la fuente viva la retiró."""

STATUS_PINNED = "REVISION_FIJADA"
"""El proveedor revisó una barra y sigue mandando la primera validada."""

STATUS_REANCHORED = "REANCLADA"
"""Reajuste de la serie (dividendo o split): la caché adoptó la base nueva."""

STATUS_ERROR = "CACHE_NO_APLICADA"
"""La caché falló en esta pasada. Se declara; la serie viva sigue su camino."""

MARKET_UNKNOWN = "desconocida"


class BarSeriesProvider(Protocol):
    """Lo que la caché necesita de un proveedor de series."""

    def get_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        ...


@dataclass(frozen=True)
class StoredBar:
    """Una barra tal como se observó, con su marca temporal original.

    La marca se conserva sin reserializar el valor: reinyectar tiene que
    reproducir el índice que sirvió el proveedor, porque fechar la barra en su
    plaza es lo que decide si el dato está al día (D-36).
    """

    session_date: date
    bar_timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float]
    observed_at: str

    @property
    def values(self) -> Tuple[float, float, float, float]:
        return (self.open, self.high, self.low, self.close)


@dataclass(frozen=True)
class SymbolCacheUsage:
    """Lo que la caché hizo con un símbolo en esta pasada.

    Es lo que la medición de frescura declara (INV-21). ``status`` resume, y las
    listas dan el detalle; cuando concurren varios hechos el resumen se queda
    con el más grave en este orden: reanclaje, servida por caché, revisión
    fijada, fuente viva.
    """

    data_symbol: str
    market: str
    status: str
    served_from_cache: Tuple[date, ...] = ()
    pinned_revisions: Tuple[date, ...] = ()
    sessions_never_observed: Tuple[date, ...] = ()
    readjustment_factor: Optional[float] = None
    detail: str = ""


@dataclass
class BarCacheReport:
    """Lo que la caché hizo en una pasada, y lo que queda por persistir."""

    enabled: bool
    window_sessions: int
    usage: Dict[str, SymbolCacheUsage] = field(default_factory=dict)
    bars_to_store: List[Dict[str, Any]] = field(default_factory=list)
    revisions_to_store: List[Dict[str, Any]] = field(default_factory=list)
    reanchored_symbols: List[str] = field(default_factory=list)

    @property
    def served_symbols(self) -> Tuple[SymbolCacheUsage, ...]:
        return tuple(
            usage for usage in self.usage.values() if usage.served_from_cache
        )

    @property
    def pinned_symbols(self) -> Tuple[SymbolCacheUsage, ...]:
        return tuple(usage for usage in self.usage.values() if usage.pinned_revisions)

    @property
    def reanchored(self) -> Tuple[SymbolCacheUsage, ...]:
        return tuple(
            usage for usage in self.usage.values() if usage.status == STATUS_REANCHORED
        )

    @property
    def failed(self) -> Tuple[SymbolCacheUsage, ...]:
        return tuple(usage for usage in self.usage.values() if usage.status == STATUS_ERROR)

    @property
    def served_bars_count(self) -> int:
        return sum(len(usage.served_from_cache) for usage in self.usage.values())

    @property
    def never_observed_count(self) -> int:
        """El contador que decide si hace falta una segunda fuente (regla 6).

        Cuenta sesiones, no activos: es el número de barras que una segunda
        fuente tendría que aportar para que el veto no actuara.
        """

        return sum(len(usage.sessions_never_observed) for usage in self.usage.values())

    @property
    def never_observed_symbols(self) -> Tuple[SymbolCacheUsage, ...]:
        return tuple(
            usage for usage in self.usage.values() if usage.sessions_never_observed
        )


class BarCacheStore(Protocol):
    """La parte de ``AdvisorDB`` que la caché usa. Solo lee aquí."""

    def get_validated_bars(self, data_symbol: str, since: Optional[date] = None) -> List[Any]:
        ...


def build_market_resolver(universe: Universe) -> Callable[[str], Optional[str]]:
    """Plaza de cada símbolo que una pasada puede pedir, o ``None``.

    Cada símbolo tiene que fecharse en la misma plaza en la que lo fecha quien
    consume esa serie, o la caché guardaría con una frontera de sesión distinta
    de la que usa el recorte (INV-06). Y resulta que producción no usa una sola
    función: un activo del universo se fecha con su plaza declarada
    (``mercado_para_simbolo``, en el analizador), mientras que un índice de
    contexto o un benchmark se fecha con ``market_for_symbol`` —``SYMBOL_MARKETS``—
    tanto al recortarlo como al medir su contexto. La diferencia no es teórica:
    el universo declara `^STOXX50E` en `ZRH`, que no tiene cierre regular
    declarado, y producción lo recorta con el calendario de XETRA.

    De ahí la precedencia: plaza explícita del símbolo, luego la declarada en el
    universo, y solo después el sufijo. Lo que no se pueda resolver devuelve
    ``None``: la caché no actúa y lo declara, en vez de suponer una plaza (INV-16).
    """

    declared: Dict[str, str] = {}
    for asset in universe.all_assets():
        for symbol in {asset.primary_symbol, asset.european_symbol}:
            if not symbol:
                continue
            try:
                declared[symbol] = mercado_para_simbolo(asset, symbol)
            except ValueError:
                continue

    def resolve(symbol: str) -> Optional[str]:
        explicit = SYMBOL_MARKETS.get(symbol.upper())
        if explicit is not None:
            return explicit
        if symbol in declared:
            return declared[symbol]
        try:
            return market_for_symbol(symbol)
        except ValueError:
            return None

    return resolve


class CachedBarProvider:
    """Proveedor que no deja caer una barra cerrada que ya había servido.

    Envuelve al proveedor real y solo interviene en series diarias. ``get_raw_history``
    pasa de largo a propósito: alimenta la cosecha congelada de investigación, que
    tiene que seguir siendo exactamente lo que el proveedor sirvió (INV-13).
    """

    def __init__(
        self,
        provider: Any,
        *,
        store: Optional[BarCacheStore],
        resolve_market: Callable[[str], Optional[str]],
        reference: datetime,
        settlement_minutes: int,
        window_sessions: int,
        readjustment_tolerance: float,
        provider_name: str = "yfinance",
        enabled: bool = True,
    ) -> None:
        self._provider = provider
        self._store = store
        self._resolve_market = resolve_market
        self._reference = reference
        self._settlement_minutes = settlement_minutes
        self._window_sessions = window_sessions
        self._tolerance = readjustment_tolerance
        self._provider_name = provider_name
        self._enabled = enabled and store is not None
        self.report = BarCacheReport(enabled=self._enabled, window_sessions=window_sessions)
        # Sesiones que la fuente viva **sí** entregó en esta pasada, por símbolo.
        # No es una declaración, es contabilidad: hace falta para que el contador
        # de la regla 6 no dependa de con qué periodo se pidió el símbolo.
        self._delivered: Dict[str, set] = {}

    # -- Interfaz de proveedor ------------------------------------------------

    def get_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        live = self._provider.get_history(symbol, period=period, interval=interval)
        if not self._enabled or interval != "1d":
            return live
        try:
            return self._merge(symbol, live)
        except Exception as exc:  # la caché no puede tumbar una pasada
            # Se declara en vez de degradar en silencio: una medición que no
            # dice nada es indistinguible de una caché que no tenía trabajo.
            logger.warning("Caché de barras no aplicada a %s: %s", symbol, exc)
            self._record(
                SymbolCacheUsage(
                    data_symbol=symbol,
                    market=MARKET_UNKNOWN,
                    status=STATUS_ERROR,
                    detail=str(exc),
                )
            )
            return live

    def get_raw_history(
        self,
        symbol: str,
        period: str = "1y",
        interval: str = "1d",
        *,
        drop_na: bool = True,
    ) -> pd.DataFrame:
        return self._provider.get_raw_history(symbol, period=period, interval=interval, drop_na=drop_na)

    def get_last_close(
        self, symbol: str, period: str = "5d", interval: str = "1d"
    ) -> Tuple[Optional[float], Optional[pd.Timestamp]]:
        return self._provider.get_last_close(symbol, period=period, interval=interval)

    def bar_cache_report(self) -> BarCacheReport:
        return self.report

    # -- Mezcla ---------------------------------------------------------------

    def _merge(self, symbol: str, live: pd.DataFrame) -> pd.DataFrame:
        market = self._resolve_market(symbol)
        if market is None:
            self._record(
                SymbolCacheUsage(
                    data_symbol=symbol,
                    market=MARKET_UNKNOWN,
                    status=STATUS_DISABLED,
                    detail="símbolo sin plaza declarada: la caché no actúa",
                )
            )
            return live

        ultima_cerrada = latest_expected_closed_session(
            market, self._reference, settlement_minutes=self._settlement_minutes
        )
        if ultima_cerrada is None:
            self._record(
                SymbolCacheUsage(
                    data_symbol=symbol,
                    market=market,
                    status=STATUS_DISABLED,
                    detail="sin última sesión cerrada exigible: la caché no actúa",
                )
            )
            return live

        zone = market_timezone(market)
        window = self._window(market, ultima_cerrada)
        if not window:
            self._record(
                SymbolCacheUsage(
                    data_symbol=symbol,
                    market=market,
                    status=STATUS_DISABLED,
                    detail="ventana de caché sin sesiones exigibles",
                )
            )
            return live

        window_start = window[0]
        live_bars = self._live_bars(live, zone, ultima_cerrada)
        stored = {bar.session_date: bar for bar in self._load(symbol, window_start)}

        self._delivered.setdefault(symbol, set()).update(live_bars)

        readjustment = self._detect_readjustment(live_bars, stored)
        if readjustment is not None:
            return self._reanchor(
                symbol=symbol,
                market=market,
                live=live,
                live_bars=live_bars,
                stored=stored,
                factor=readjustment,
                window=window,
            )

        pinned: List[date] = []
        revisions: List[Dict[str, Any]] = []
        for session, (label, values) in live_bars.items():
            bar = stored.get(session)
            if bar is None or _same_bar(bar, values, self._tolerance):
                continue
            # Una barra que se mueve sola es una revisión de esa sesión, no un
            # reajuste de la serie: manda la primera validada y la nueva queda
            # registrada (D-41, regla 4).
            revisions.append(
                _revision_row(
                    data_symbol=symbol,
                    market=market,
                    bar=bar,
                    values=values,
                    kind=KIND_REVISION,
                    factor=None,
                    applied=False,
                    observed_at=self._observed_at(),
                    provider=self._provider_name,
                )
            )
            pinned.append(session)
            live_bars[session] = (label, (*bar.values, bar.volume))

        # La caché repone lo que el proveedor retiró; no alarga hacia atrás una
        # ventana que el llamante pidió corta. Medido en una pasada real: el
        # contexto pide `^VIX` con `period="5d"` y la caché le estaba inyectando
        # 19 barras de sesiones anteriores, guardadas por otra llamada del mismo
        # símbolo con `2y`. Eran barras reales, pero nadie las había pedido, y
        # además inflaban la cifra de barras rescatadas que se publica.
        primera_viva = min(live_bars) if live_bars else None
        candidatas = [
            session
            for session in sorted(stored)
            if session not in live_bars
            and window_start <= session <= ultima_cerrada
            and primera_viva is not None
            and session >= primera_viva
        ]
        marcas: Dict[date, Any] = {}
        for session in candidatas:
            marca = _index_like(live.index, [stored[session].bar_timestamp])[0]
            if _session_date(marca, zone) != session:
                # La marca guardada, releída en la zona de la serie viva, no
                # vuelve a caer en su propia sesión: con el cambio de horario una
                # marca de medianoche puede retroceder un día. Reinyectarla
                # movería la barra de sesión, así que no se reinyecta y se declara.
                logger.warning(
                    "%s %s: la marca guardada %s no vuelve a fechar en su sesión; no se reinyecta",
                    symbol,
                    session,
                    stored[session].bar_timestamp,
                )
                continue
            marcas[session] = marca
        served = sorted(marcas)

        merged = live
        if pinned or served:
            merged = _rebuild(live, zone, stored, pinned, marcas)

        never_observed = self._never_observed(
            window=window,
            live_bars=live_bars,
            stored=stored,
        )

        self._queue_new_bars(
            symbol=symbol,
            market=market,
            live_bars=live_bars,
            stored=stored,
            window_start=window_start,
            has_volume="Volume" in live.columns,
        )
        self.report.revisions_to_store.extend(revisions)
        self._record(
            SymbolCacheUsage(
                data_symbol=symbol,
                market=market,
                status=_status(served, pinned),
                served_from_cache=tuple(served),
                pinned_revisions=tuple(sorted(pinned)),
                sessions_never_observed=tuple(never_observed),
            )
        )
        return merged

    def _reanchor(
        self,
        *,
        symbol: str,
        market: str,
        live: pd.DataFrame,
        live_bars: Dict[date, Tuple[Any, Tuple[float, float, float, float, Optional[float]]]],
        stored: Dict[date, StoredBar],
        factor: float,
        window: List[date],
    ) -> pd.DataFrame:
        """Adopta la base de ajuste nueva y tira lo guardado en la vieja.

        Un dividendo o un split reescriben toda la serie anterior por un mismo
        factor. Conservar barras en la base vieja mezclaría dos escalas en la
        misma serie y metería un escalón artificial en ATR y en las medias, así
        que la caché se reancla con lo que el proveedor sirve **ahora**, que es
        una observación y no un número calculado (regla 2).

        El coste queda declarado: una barra retirada el mismo día del reajuste
        se pierde, porque escalarla produciría un valor que el bot no observó.
        """

        observed_at = self._observed_at()
        revisadas: List[date] = []
        for session in sorted(set(live_bars) & set(stored)):
            bar = stored[session]
            _, values = live_bars[session]
            propio = _bar_factor(bar, values, self._tolerance)
            # Una barra que no comparte la escala de la serie es una revisión, no
            # parte del reajuste. Se adopta igual (`applied`) porque conservarla
            # en la base vieja es justamente lo que el reanclaje viene a evitar,
            # y queda distinguida en la tabla y declarada en la medición.
            es_reajuste = propio is not None and abs(propio - factor) <= self._tolerance
            if not es_reajuste:
                revisadas.append(session)
            self.report.revisions_to_store.append(
                _revision_row(
                    data_symbol=symbol,
                    market=market,
                    bar=bar,
                    values=values,
                    kind=KIND_READJUSTMENT if es_reajuste else KIND_REVISION,
                    factor=factor if es_reajuste else propio,
                    applied=True,
                    observed_at=observed_at,
                    provider=self._provider_name,
                )
            )
        if symbol not in self.report.reanchored_symbols:
            self.report.reanchored_symbols.append(symbol)

        perdidas = tuple(session for session in sorted(stored) if session not in live_bars)
        never_observed = self._never_observed(window=window, live_bars=live_bars, stored={})
        self._queue_new_bars(
            symbol=symbol,
            market=market,
            live_bars=live_bars,
            stored={},
            window_start=window[0],
            has_volume="Volume" in live.columns,
        )
        detalle = f"reajuste de la serie por factor {factor:.6f}: la caché adopta la base nueva"
        if revisadas:
            detalle += (
                "; barras que no comparten esa escala y se adoptan como revisión: "
                + ", ".join(value.isoformat() for value in revisadas)
            )
        if perdidas:
            detalle += (
                "; se pierden por el reanclaje barras que la fuente viva no sirve: "
                + ", ".join(value.isoformat() for value in perdidas)
            )
        self._record(
            SymbolCacheUsage(
                data_symbol=symbol,
                market=market,
                status=STATUS_REANCHORED,
                sessions_never_observed=tuple(never_observed),
                readjustment_factor=factor,
                detail=detalle,
            )
        )
        return live

    def _detect_readjustment(
        self,
        live_bars: Dict[date, Tuple[Any, Tuple[float, float, float, float, Optional[float]]]],
        stored: Dict[date, StoredBar],
    ) -> Optional[float]:
        """Factor que comparte la **mayoría** de las barras solapadas, o ``None``.

        Exigir unanimidad era un defecto medido: un split con una revisión
        puntual el mismo día rompía la unanimidad, no se reanclaba, y entonces la
        serie que veía el análisis era **la base entera anterior al split** —168,5
        donde el proveedor ya servía 85,09—. Un solo dato revisado no puede
        decidir sobre la escala de toda la serie, así que el factor sale de la
        mayoría y las barras que no lo comparten se tratan como revisiones dentro
        de la base nueva.

        Con una sola barra solapada no se puede distinguir un reajuste de la
        serie de una revisión de esa sesión, así que no se afirma que sea un
        reajuste: se trata como revisión, que es la lectura conservadora —manda
        la primera validada— y queda registrada igual.
        """

        factores = [
            factor
            for factor in (
                _bar_factor(stored[session], live_bars[session][1], self._tolerance)
                for session in sorted(set(live_bars) & set(stored))
            )
            if factor is not None
        ]
        if len(factores) < 2:
            return None
        # El candidato es el factor que más barras comparten, y tiene que ser
        # **mayoría estricta**: un empate no es una escala de la serie. Con dos
        # barras a 0,5 y dos a 0,8, aceptar el empate reanclaba a 0,5 solo porque
        # llegaba antes en el tiempo, que es elegir la escala por sorteo.
        candidato, coincidencias = max(
            (
                (valor, sum(1 for otro in factores if abs(otro - valor) <= self._tolerance))
                for valor in factores
            ),
            key=lambda par: par[1],
        )
        if coincidencias < 2 or coincidencias * 2 <= len(factores):
            return None
        if abs(candidato - 1.0) <= self._tolerance:
            return None
        return candidato

    def _never_observed(
        self,
        *,
        window: List[date],
        live_bars: Dict[date, Any],
        stored: Dict[date, StoredBar],
    ) -> List[date]:
        """Sesiones exigibles de la ventana que nadie ha visto nunca (regla 6).

        No cuenta las sesiones anteriores a la primera barra conocida del
        símbolo: antes de esa fecha no hay nada que el proveedor debiera haber
        entregado para este activo, y contarlas convertiría una cotización
        reciente en un argumento para pagar otra fuente.
        """

        conocidas = set(live_bars) | set(stored)
        if not conocidas:
            return []
        primera = min(conocidas)
        return [
            session
            for session in window
            if session >= primera and session not in conocidas
        ]

    def _queue_new_bars(
        self,
        *,
        symbol: str,
        market: str,
        live_bars: Dict[date, Tuple[Any, Tuple[float, float, float, float, Optional[float]]]],
        stored: Dict[date, StoredBar],
        window_start: date,
        has_volume: bool = True,
    ) -> None:
        observed_at = self._observed_at()
        for session in sorted(live_bars):
            if session < window_start or session in stored:
                continue
            label, values = live_bars[session]
            open_, high, low, close, volume = values
            if any(_is_nan(value) for value in (open_, high, low, close)):
                # Una barra con un hueco en OHLC no está validada: guardarla
                # dejaría un NULL en una columna obligatoria y, peor, daría por
                # observada una sesión que no lo está (regla 3).
                logger.info("%s %s: barra con OHLC incompleto, no entra en la caché", symbol, session)
                continue
            if has_volume and (volume is None or _is_nan(volume)):
                # Reinyectar esta barra metería un `NaN` en una columna de volumen
                # que sí existe, y `build_snapshot` descarta los nulos antes de
                # leer el último volumen: el análisis usaría el volumen de la
                # sesión anterior como si fuera el de esta. Medido.
                logger.info("%s %s: barra sin volumen conocido, no entra en la caché", symbol, session)
                continue
            self.report.bars_to_store.append(
                {
                    "data_symbol": symbol,
                    "market": market,
                    "session_date": session.isoformat(),
                    "bar_timestamp": _timestamp_text(label),
                    "open": float(open_),
                    "high": float(high),
                    "low": float(low),
                    "close": float(close),
                    "volume": None if volume is None or _is_nan(volume) else float(volume),
                    "observed_at": observed_at,
                    "provider": self._provider_name,
                }
            )

    # -- Utilidades -----------------------------------------------------------

    def _window(self, market: str, ultima_cerrada: date) -> List[date]:
        # Se piden bastantes más días naturales que sesiones para que un cierre
        # largo de plaza no deje la ventana corta sin avisar.
        desde = ultima_cerrada - timedelta(days=max(self._window_sessions * 3, 45))
        sesiones = expected_sessions(market, desde, ultima_cerrada)
        return sesiones[-self._window_sessions :]

    def _live_bars(
        self,
        live: pd.DataFrame,
        zone: Any,
        ultima_cerrada: date,
    ) -> Dict[date, Tuple[Any, Tuple[float, float, float, float, Optional[float]]]]:
        """Barras vivas de sesión cerrada y exigible, fechadas en su plaza.

        Las posteriores a la última sesión cerrada exigible están en curso: no
        entran en la caché ni cuentan como observadas (D-37).
        """

        bars: Dict[date, Tuple[Any, Tuple[float, float, float, float, Optional[float]]]] = {}
        if live.empty:
            return bars
        missing = [column for column in ("Open", "High", "Low", "Close") if column not in live.columns]
        if missing:
            raise ValueError(f"serie sin columnas {missing}: la caché no puede guardar la barra")
        for position in range(len(live.index)):
            label = live.index[position]
            session = _session_date(label, zone)
            if session > ultima_cerrada:
                continue
            row = live.iloc[position]
            values = (
                float(row["Open"]),
                float(row["High"]),
                float(row["Low"]),
                float(row["Close"]),
                float(row["Volume"]) if "Volume" in live.columns and not _is_nan(row["Volume"]) else None,
            )
            bars[session] = (label, values)
        return bars

    def _load(self, symbol: str, since: date) -> List[StoredBar]:
        if self._store is None:
            return []
        bars: List[StoredBar] = []
        for row in self._store.get_validated_bars(symbol, since):
            bars.append(
                StoredBar(
                    session_date=date.fromisoformat(row["session_date"]),
                    bar_timestamp=row["bar_timestamp"],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=None if row["volume"] is None else float(row["volume"]),
                    observed_at=row["observed_at"],
                )
            )
        return bars

    def _observed_at(self) -> str:
        return self._reference.astimezone(timezone.utc).isoformat()

    def _record(self, usage: SymbolCacheUsage) -> None:
        """Acumula lo declarado por símbolo, sin perder nada de una llamada anterior.

        Un mismo símbolo se pide varias veces en una pasada con periodos
        distintos: `^STOXX50E` entra como tendencia del contexto con `2y`, como
        benchmark con la ventana del horizonte y como panorama con `1mo`.
        Sobrescribir dejaría el informe con lo que dijera la última llamada, así
        que una barra servida desde la caché en la primera podría desaparecer de
        la declaración (INV-21).

        Las barras servidas y las revisiones fijadas se **unen**: ocurrieron. Las
        sesiones nunca observadas se **intersecan**: si cualquier llamada de esta
        pasada entregó la sesión, el proveedor la entrega, y no cuenta como
        valor marginal de una segunda fuente.
        """

        entregadas = self._delivered.get(usage.data_symbol, set())
        anterior = self.report.usage.get(usage.data_symbol)
        if anterior is None:
            self.report.usage[usage.data_symbol] = replace(
                usage,
                sessions_never_observed=tuple(
                    sorted(set(usage.sessions_never_observed) - entregadas)
                ),
            )
            return
        servidas = tuple(sorted(set(anterior.served_from_cache) | set(usage.served_from_cache)))
        fijadas = tuple(sorted(set(anterior.pinned_revisions) | set(usage.pinned_revisions)))
        # Se **resta lo entregado**, no se intersecan los dos conjuntos. Intersecar
        # borraba el contador: la petición larga veía una sesión exigible que nadie
        # ha servido nunca, y la petición corta del mismo símbolo empieza después
        # de esa fecha, así que su conjunto salía vacío y la intersección dejaba el
        # contador de OD-02 bis en cero. Lo que quita una sesión de la cuenta es que
        # alguna petición de esta pasada la haya entregado, no que otra no pudiera
        # llegar a verla.
        nunca = tuple(
            sorted(
                (set(anterior.sessions_never_observed) | set(usage.sessions_never_observed))
                - entregadas
            )
        )
        detalles = [value for value in (anterior.detail, usage.detail) if value]
        self.report.usage[usage.data_symbol] = SymbolCacheUsage(
            data_symbol=usage.data_symbol,
            market=usage.market if usage.market != MARKET_UNKNOWN else anterior.market,
            status=_worst_status(anterior.status, usage.status, servidas, fijadas),
            served_from_cache=servidas,
            pinned_revisions=fijadas,
            sessions_never_observed=nunca,
            readjustment_factor=usage.readjustment_factor or anterior.readjustment_factor,
            detail="; ".join(dict.fromkeys(detalles)),
        )


def _status(served: List[date], pinned: List[date]) -> str:
    if served:
        return STATUS_SERVED
    if pinned:
        return STATUS_PINNED
    return STATUS_LIVE


_STATUS_PRECEDENCE = (
    STATUS_ERROR,
    STATUS_REANCHORED,
    STATUS_SERVED,
    STATUS_PINNED,
    STATUS_LIVE,
    STATUS_DISABLED,
)


def _worst_status(
    anterior: str,
    nuevo: str,
    served: Tuple[date, ...],
    pinned: Tuple[date, ...],
) -> str:
    """El estado que más hay que contar de las dos llamadas.

    Un fallo o un reanclaje pesan más que una barra servida, y una barra servida
    más que «la fuente viva sirvió todo»: el resumen tiene que apuntar a lo que
    obliga a mirar. Si una de las dos llamadas sirvió una barra, el estado no
    puede quedarse en `SIN_CACHE` aunque la otra no actuara.
    """

    for status in _STATUS_PRECEDENCE:
        if status in (anterior, nuevo):
            if status in (STATUS_LIVE, STATUS_DISABLED):
                return _status(list(served), list(pinned)) if (served or pinned) else status
            return status
    return nuevo


def _bar_factor(
    bar: StoredBar,
    values: Tuple[float, float, float, float, Optional[float]],
    tolerance: float,
) -> Optional[float]:
    """Factor de escala de una barra, si OHLC han cambiado todos por el mismo.

    Devuelve ``None`` cuando la barra no tiene una escala única —un cierre que
    se mueve y una apertura que no—, porque entonces no es un reajuste de escala
    sino una revisión de esa sesión.
    """

    factores: List[float] = []
    for previous, current in zip(bar.values, values[:4]):
        if current is None or _is_nan(current) or previous == 0:
            return None
        factores.append(float(current) / float(previous))
    primero = factores[0]
    if any(abs(valor - primero) > tolerance for valor in factores[1:]):
        return None
    return primero


def _same_bar(
    bar: StoredBar,
    values: Tuple[float, float, float, float, Optional[float]],
    tolerance: float,
) -> bool:
    """Si la barra servida es la misma que la guardada, incluido el volumen.

    El volumen entra en la comparación porque una revisión que solo lo toca
    seguía siendo una revisión no registrada: el análisis consumía el volumen
    nuevo —y el volumen alimenta el catalizador— mientras la tabla guardaba otro
    y nadie lo declaraba.
    """

    for previous, current in zip(bar.values, values[:4]):
        if current is None or _is_nan(current):
            return False
        if previous == 0:
            if float(current) != 0:
                return False
            continue
        if abs(float(current) / float(previous) - 1.0) > tolerance:
            return False
    previous_volume = bar.volume
    current_volume = values[4]
    if previous_volume is None or current_volume is None or _is_nan(current_volume):
        # Un volumen desconocido en cualquiera de los dos lados no puede afirmar
        # que la barra cambió ni que siguió igual: se decide por OHLC (INV-16).
        return True
    if previous_volume == 0:
        return float(current_volume) == 0
    return abs(float(current_volume) / float(previous_volume) - 1.0) <= tolerance


def _rebuild(
    live: pd.DataFrame,
    zone: Any,
    stored: Dict[date, StoredBar],
    pinned: List[date],
    served: Dict[date, Any],
) -> pd.DataFrame:
    """Serie devuelta al análisis: lo vivo, con lo guardado donde manda.

    Las columnas que la caché no guarda —dividendos, splits— quedan como
    desconocidas en una barra reinyectada en vez de como cero: afirmar que no
    hubo dividendo ese día sería inventarse un dato (INV-16).
    """

    merged = live.copy()
    fijadas = set(pinned)
    if fijadas:
        for position in range(len(merged.index)):
            session = _session_date(merged.index[position], zone)
            if session not in fijadas:
                continue
            bar = stored[session]
            for column, value in zip(
                ("Open", "High", "Low", "Close", "Volume"),
                (bar.open, bar.high, bar.low, bar.close, bar.volume),
            ):
                if column in merged.columns and value is not None:
                    merged.iloc[position, merged.columns.get_loc(column)] = value

    if served:
        filas = []
        for session in sorted(served):
            bar = stored[session]
            fila: Dict[str, float] = dict.fromkeys(merged.columns, math.nan)
            for column, value in zip(
                ("Open", "High", "Low", "Close", "Volume"),
                (bar.open, bar.high, bar.low, bar.close, bar.volume),
            ):
                if column in merged.columns:
                    fila[column] = math.nan if value is None else value
            filas.append(fila)
        # Las marcas las decide y valida quien las eligió: aquí no se vuelven a
        # convertir, para que no puedan divergir de las que se declararon.
        reinyectadas = pd.DataFrame(
            filas, index=pd.DatetimeIndex([served[session] for session in sorted(served)])
        )
        merged = pd.concat([merged, reinyectadas]).sort_index()
        if not isinstance(merged.index, pd.DatetimeIndex):
            # Defensa explícita, no adorno: una sola marca con zona distinta
            # degrada el índice a `object`, y entonces `relative_strength`
            # devuelve `None` en silencio —la caché mataría el factor justo en
            # los activos que rescata—. Medido antes de esta guarda.
            raise ValueError(
                "la reinyección degradó el índice de la serie: "
                f"{merged.index.dtype} en vez de un DatetimeIndex"
            )

    return merged


def _index_like(reference: pd.Index, timestamps: List[str]) -> pd.DatetimeIndex:
    """Índice para las barras reinyectadas, en la misma escala que la serie viva.

    Las marcas se guardan tal como llegaron —ISO con su desfase—, así que
    releerlas produce una zona de desfase fijo (`UTC+02:00`) que no es la misma
    que `Europe/Berlin`. Concatenar dos índices con zonas distintas degrada el
    resultado a `object`, y ahí se pierde la alineación por sesiones.
    """

    valores = [pd.Timestamp(value) for value in timestamps]
    zona = getattr(reference, "tz", None)
    if zona is not None:
        valores = [
            valor.tz_localize(zona) if valor.tzinfo is None else valor.tz_convert(zona)
            for valor in valores
        ]
    else:
        valores = [
            valor.tz_localize(None) if valor.tzinfo is not None else valor for valor in valores
        ]
    return pd.DatetimeIndex(valores)


def _revision_row(
    *,
    data_symbol: str,
    market: str,
    bar: StoredBar,
    values: Tuple[float, float, float, float, Optional[float]],
    kind: str,
    factor: Optional[float],
    applied: bool,
    observed_at: str,
    provider: str,
) -> Dict[str, Any]:
    open_, high, low, close, volume = values
    return {
        "data_symbol": data_symbol,
        "market": market,
        "session_date": bar.session_date.isoformat(),
        "kind": kind,
        "previous_open": bar.open,
        "previous_high": bar.high,
        "previous_low": bar.low,
        "previous_close": bar.close,
        "previous_volume": bar.volume,
        "previous_observed_at": bar.observed_at,
        "new_open": float(open_),
        "new_high": float(high),
        "new_low": float(low),
        "new_close": float(close),
        "new_volume": None if volume is None or _is_nan(volume) else float(volume),
        "factor": factor,
        "observed_at": observed_at,
        "provider": provider,
        "applied": int(applied),
    }


def _timestamp_text(label: Any) -> str:
    if isinstance(label, pd.Timestamp):
        return label.isoformat()
    return str(label)


def _is_nan(value: Any) -> bool:
    try:
        return bool(math.isnan(float(value)))
    except (TypeError, ValueError):
        return False
