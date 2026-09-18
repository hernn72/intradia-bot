"""Sesiones regulares de mercado y recorte de barras diarias no cerradas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from functools import cache
from typing import Optional
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd


@dataclass(frozen=True)
class MarketSession:
    timezone: str
    close_time: Optional[time]
    mic: str


@dataclass(frozen=True)
class TrimResult:
    df: pd.DataFrame
    status: str
    removed_last_bar: bool = False


MARKET_PRE_OPEN = "PRE_OPEN"
MARKET_OPEN = "OPEN"
MARKET_CLOSED = "CLOSED"

MARKET_SESSIONS = {
    "AMS": MarketSession("Europe/Amsterdam", time(17, 30), "XAMS"),
    "CPH": MarketSession("Europe/Copenhagen", time(17, 0), "XCSE"),
    "CRYPTO": MarketSession("UTC", None, "CRYPTO_24_7"),
    "HKG": MarketSession("Asia/Hong_Kong", time(16, 0), "XHKG"),
    "JPX": MarketSession("Asia/Tokyo", time(15, 30), "XTKS"),
    "KSC": MarketSession("Asia/Seoul", time(15, 30), "XKRX"),
    "LSE": MarketSession("Europe/London", time(16, 30), "XLON"),
    "MCE": MarketSession("Europe/Madrid", time(17, 30), "XMAD"),
    "MIL": MarketSession("Europe/Rome", time(17, 30), "XMIL"),
    "NASDAQ": MarketSession("America/New_York", time(16, 0), "XNAS"),
    "NYSE": MarketSession("America/New_York", time(16, 0), "XNYS"),
    "PAR": MarketSession("Europe/Paris", time(17, 30), "XPAR"),
    "SHH": MarketSession("Asia/Shanghai", time(15, 0), "XSHG"),
    "TAI": MarketSession("Asia/Taipei", time(13, 30), "XTAI"),
    "XETRA": MarketSession("Europe/Berlin", time(17, 30), "XETR"),
}

SYMBOL_MARKETS = {
    "^DJI": "NYSE",
    "^FCHI": "PAR",
    "^FTSE": "LSE",
    "^GDAXI": "XETRA",
    "^GSPC": "NYSE",
    "^HSI": "HKG",
    "^IXIC": "NASDAQ",
    "^KS11": "KSC",
    "^N225": "JPX",
    "^NDX": "NASDAQ",
    "^RUT": "NYSE",
    "^SOX": "NASDAQ",
    "^STOXX": "XETRA",
    "^STOXX50E": "XETRA",
    "^TNX": "NYSE",
    "^TWII": "TAI",
    "^VIX": "NYSE",
    "CL=F": "NYSE",
    "DX-Y.NYB": "NYSE",
    "GC=F": "NYSE",
    "510300.SS": "SHH",
}


def market_session(market: str) -> MarketSession:
    try:
        return MARKET_SESSIONS[market]
    except KeyError:
        raise ValueError(f"plaza '{market}' sin cierre regular declarado") from None


def market_timezone(market: str) -> ZoneInfo:
    return ZoneInfo(market_session(market).timezone)


def market_state(market: str, reference: datetime) -> Optional[str]:
    session = MARKET_SESSIONS.get(market)
    if session is None:
        return None
    if session.mic == "CRYPTO_24_7":
        return MARKET_OPEN

    cal = _exchange_calendar(session.mic)
    local_reference = reference.astimezone(ZoneInfo(session.timezone))
    session_label = pd.Timestamp(local_reference.date())
    if not cal.is_session(session_label):
        return MARKET_CLOSED

    opened_at = cal.session_open(session_label)
    closed_at = cal.session_close(session_label)
    # ``local_reference`` ya es consciente de zona horaria: para un ``reference``
    # sin zona, ``astimezone`` asume la del sistema, que es la misma convención
    # que sigue ``trim_unclosed_bar`` en este módulo.
    reference_utc = pd.Timestamp(local_reference).tz_convert("UTC")
    if reference_utc < opened_at:
        return MARKET_PRE_OPEN
    if reference_utc <= closed_at:
        return MARKET_OPEN
    return MARKET_CLOSED


def market_for_symbol(symbol: str, *, asset_class: Optional[str] = None) -> str:
    cleaned = symbol.upper()
    if cleaned in SYMBOL_MARKETS:
        return SYMBOL_MARKETS[cleaned]
    suffixes = {
        ".AS": "AMS",
        ".CO": "CPH",
        ".DE": "XETRA",
        ".HK": "HKG",
        ".KS": "KSC",
        ".MC": "MCE",
        ".MI": "MIL",
        ".PA": "PAR",
        ".SS": "SHH",
        ".T": "JPX",
    }
    for suffix, market in suffixes.items():
        if cleaned.endswith(suffix):
            return market
    if cleaned.endswith(("-EUR", "-USD")) and asset_class == "crypto":
        return "CRYPTO"
    if cleaned.startswith("^"):
        raise ValueError(f"{symbol}: índice sin plaza declarada en SYMBOL_MARKETS")
    raise ValueError(f"{symbol}: símbolo sin plaza declarada")


CRYPTO_MIC = "CRYPTO_24_7"


def session_date_of(timestamp: object, market: str) -> Optional[date]:
    """A qué sesión de la plaza pertenece una barra.

    Es la **única** forma de fechar una barra en el asesor. Fechar en UTC y
    recortar en la zona de la plaza son dos maneras distintas de responder a la
    misma pregunta, y dan respuestas distintas: una barra de la sesión XETRA del
    18 llega estampada como `2026-09-17T22:00:00Z`, así que en UTC parece del 17.
    Con el veto midiéndose contra la última sesión cerrada exigible, esa
    diferencia de un día veta a un activo que tiene su dato al día (INV-06).

    Devuelve ``None`` si la plaza no está declarada: entonces quien llama decide,
    en vez de que este módulo se invente una zona.
    """

    try:
        zone = ZoneInfo(market_session(market).timezone)
    except ValueError:
        return None
    return _session_date(timestamp, zone)


def session_close_at(market: str, session_date: date) -> Optional[datetime]:
    """Instante en que cierra la sesión de una plaza, o ``None`` si no se sabe.

    Una plaza 24/7 no tiene hora de cierre pero sus barras diarias **sí** se
    cierran: la del día D queda cerrada a las 00:00 UTC del día siguiente. Eso
    es lo que permite tratar cripto con la misma regla que el resto en vez de
    con una excepción (D-37).
    """

    session = market_session(market)
    if session.mic == CRYPTO_MIC:
        return datetime.combine(session_date + timedelta(days=1), time(0, 0), tzinfo=timezone.utc)
    if session.close_time is None:
        return None
    try:
        return _session_close_at(session, session_date).to_pydatetime()
    except Exception:  # calendario no declarado o fecha fuera de rango
        return None


def latest_expected_closed_session(
    market: str,
    reference: datetime,
    *,
    settlement_minutes: int = 0,
    lookback_days: int = 45,
) -> Optional[date]:
    """La última sesión cuyo cierre —más la liquidación— ya ha pasado.

    Es la barra que el proveedor **ya debería** haber publicado. Si falta, el
    dato está retrasado y D-21 veta; cualquier barra posterior sigue abierta, se
    ignora y no veta. La regla es la misma para todas las plazas, incluida una
    24/7: lo único que cambia es a qué hora cierra cada sesión.

    Devuelve ``None`` cuando no se puede determinar —plaza sin calendario
    declarado—, y entonces quien llama declara desconocido en vez de suponer
    (INV-16).

    ``lookback_days`` son 45 y no 15 porque un cierre largo real —una semana
    dorada asiática encadenada con festivos, una suspensión— dejaría la ventana
    sin ninguna sesión y la frescura volvería a la cuenta antigua sin que nadie
    se enterara. Con 45 días no hay cierre de plaza conocido que la agote, y si
    lo hubiera se declara desconocido, que es lo correcto.
    """

    # Import diferido: `calendars` importa este módulo, así que hacerlo arriba
    # cerraría el círculo. Es la misma lista de sesiones que usa todo lo demás,
    # con los overrides de plaza aplicados (INV-06).
    from advisor.data.calendars import expected_sessions

    try:
        session = market_session(market)
    except ValueError:
        # Plaza sin declarar: aquí no se grita, se declara desconocido. Quien
        # necesite gritar es `trim_unclosed_bar`, que sí exige plaza conocida.
        return None
    zone = ZoneInfo(session.timezone)
    hoy = reference.astimezone(zone).date()
    for delta in range(lookback_days + 1):
        candidata = hoy - timedelta(days=delta)
        if session.mic != CRYPTO_MIC and not expected_sessions(market, candidata, candidata):
            continue
        cierre = session_close_at(market, candidata)
        if cierre is None:
            return None
        if cierre + timedelta(minutes=settlement_minutes) <= reference:
            return candidata
    return None


def trim_unclosed_bar(
    df: pd.DataFrame,
    *,
    market: str,
    reference: datetime,
    settlement_minutes: int,
    interval: str = "1d",
) -> TrimResult:
    """Descarta las barras posteriores a la última sesión cerrada exigible.

    Una barra en curso no es un dato: se ignora para indicadores, puntuación,
    señales y backtest. Lo que decide cuál sobra no es «es de hoy», sino si su
    sesión ha cerrado ya —lo que vale igual para XETRA a las 17:30 de Berlín que
    para una plaza 24/7 a las 00:00 UTC (D-37)—.
    """

    session = market_session(market)
    if df.empty or interval != "1d":
        return TrimResult(df=df, status="sin recorte: intervalo no diario o histórico vacío")

    ultima_cerrada = latest_expected_closed_session(
        market, reference, settlement_minutes=settlement_minutes
    )
    if ultima_cerrada is None:
        return TrimResult(df=df, status="sin recorte: no se puede determinar la última sesión cerrada")

    zone = ZoneInfo(session.timezone)
    cierre = session_close_at(market, ultima_cerrada)
    detalle_cierre = ""
    if cierre is not None:
        local = cierre.astimezone(zone)
        detalle_cierre = f"cierre de sesión {local:%H:%M} {session.timezone} + {settlement_minutes} min"

    abiertas = [
        posicion
        for posicion in range(len(df.index))
        if _session_date(df.index[posicion], zone) > ultima_cerrada
    ]
    if abiertas:
        recortado = df.iloc[: abiertas[0]]
        fechas = ", ".join(sorted({_session_date(df.index[p], zone).isoformat() for p in abiertas}))
        return TrimResult(
            df=recortado,
            status=(
                f"barra {fechas} recortada: aún abierta; la última sesión cerrada exigible es "
                f"{ultima_cerrada.isoformat()} ({detalle_cierre})"
            ),
            removed_last_bar=True,
        )
    return TrimResult(
        df=df,
        status=(
            f"última barra cerrada según {detalle_cierre}; "
            f"última sesión cerrada exigible: {ultima_cerrada.isoformat()}"
        ),
    )


@cache
def _exchange_calendar(mic: str):
    return xcals.get_calendar(mic)


def _session_close_at(session: MarketSession, session_date: date) -> pd.Timestamp:
    cal = _exchange_calendar(session.mic)
    session_label = pd.Timestamp(session_date)
    if cal.is_session(session_label):
        return cal.session_close(session_label)
    close_time = session.close_time
    if close_time is None:
        raise ValueError("no hay cierre de sesión para una plaza sin cierre")
    return pd.Timestamp(datetime.combine(session_date, close_time, tzinfo=ZoneInfo(session.timezone))).tz_convert("UTC")


def _session_date(timestamp: object, zone: ZoneInfo) -> date:
    if isinstance(timestamp, pd.Timestamp):
        if timestamp.tzinfo is None:
            return timestamp.date()
        return timestamp.to_pydatetime().astimezone(zone).date()
    if isinstance(timestamp, datetime):
        if timestamp.tzinfo is None:
            return timestamp.date()
        return timestamp.astimezone(zone).date()
    if isinstance(timestamp, str):
        parsed = pd.Timestamp(timestamp)
        if parsed.tzinfo is None:
            return parsed.date()
        return parsed.to_pydatetime().astimezone(zone).date()
    raise TypeError(f"timestamp no soportado para sesión: {timestamp!r}")
