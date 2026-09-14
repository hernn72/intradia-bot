"""Sesiones regulares de mercado y recorte de barras diarias no cerradas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd


@dataclass(frozen=True)
class MarketSession:
    timezone: str
    close_time: Optional[time]
    mic: str

    @property
    def has_close(self) -> bool:
        return self.close_time is not None


@dataclass(frozen=True)
class TrimResult:
    df: pd.DataFrame
    status: str
    removed_last_bar: bool = False


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


def trim_unclosed_bar(
    df: pd.DataFrame,
    *,
    market: str,
    reference: datetime,
    settlement_minutes: int,
    interval: str = "1d",
) -> TrimResult:
    """Descarta la última barra diaria si su sesión regular no está cerrada."""

    session = market_session(market)
    if df.empty or interval != "1d":
        return TrimResult(df=df, status="sin recorte: intervalo no diario o histórico vacío")
    if session.close_time is None:
        return TrimResult(df=df, status="sin sesión de cierre")

    zone = ZoneInfo(session.timezone)
    local_now = reference.astimezone(zone)
    last_session_date = _session_date(df.index[-1], zone)
    close_at = datetime.combine(last_session_date, session.close_time, tzinfo=zone)
    settled_at = close_at + timedelta(minutes=settlement_minutes)
    if local_now < settled_at:
        return TrimResult(
            df=df.iloc[:-1],
            status=(
                f"barra {last_session_date.isoformat()} recortada: cierre regular "
                f"{session.close_time:%H:%M} {session.timezone} + {settlement_minutes} min no alcanzado"
            ),
            removed_last_bar=True,
        )
    return TrimResult(
        df=df,
        status=(
            f"última barra cerrada según cierre regular {session.close_time:%H:%M} "
            f"{session.timezone} + {settlement_minutes} min"
        ),
    )


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
