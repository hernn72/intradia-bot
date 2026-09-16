"""Acceso a datos de mercado mediante yfinance, con rate limiting básico.

Copia de ``app/data/market_data.py`` del proyecto trading-bot (módulo puro,
sin dependencias del resto de aquel paquete), más ``get_last_close``, que es
lo único que necesita el conversor de divisa.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Tuple

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


class RateLimiter:
    """Garantiza un tiempo mínimo entre llamadas consecutivas (thread-safe)."""

    def __init__(self, min_interval_seconds: float) -> None:
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds debe ser >= 0")
        self.min_interval_seconds = min_interval_seconds
        self._lock = threading.Lock()
        self._last_call: Optional[float] = None

    def wait(self) -> None:
        """Bloquea hasta que haya transcurrido el intervalo mínimo desde la última llamada."""

        with self._lock:
            now = time.monotonic()
            if self._last_call is not None:
                elapsed = now - self._last_call
                remaining = self.min_interval_seconds - elapsed
                if remaining > 0:
                    time.sleep(remaining)
            self._last_call = time.monotonic()


class MarketDataProvider:
    """Obtiene históricos de precios para un símbolo, aplicando rate limiting."""

    def __init__(self, min_interval_seconds: float = 1.0) -> None:
        self._rate_limiter = RateLimiter(min_interval_seconds)

    def get_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        """Descarga el histórico OHLCV de ``symbol``.

        Lanza ``ValueError`` si el símbolo es inválido o no hay datos disponibles.
        """

        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol debe ser una cadena no vacía")

        self._rate_limiter.wait()

        try:
            ticker = yf.Ticker(symbol)
            history = ticker.history(period=period, interval=interval)
        except Exception as exc:  # pragma: no cover - depende de red externa
            logger.error("Error al obtener datos de %s: %s", symbol, exc)
            raise

        if history is None or history.empty:
            raise ValueError(f"No se han recibido datos para el símbolo '{symbol}'")

        history = history.dropna(subset=["Close"])
        if history.empty:
            raise ValueError(f"Datos vacíos tras limpieza para el símbolo '{symbol}'")

        return history

    def get_raw_history(
        self,
        symbol: str,
        period: str = "1y",
        interval: str = "1d",
        *,
        drop_na: bool = True,
    ) -> pd.DataFrame:
        """Descarga OHLCV y acciones corporativas sin ajuste por dividendos.

        yfinance devuelve el OHLC ya ajustado por splits cuando se pide
        ``auto_adjust=False``. Esta ruta conserva ``Adj Close``, dividendos y
        splits para que investigación pueda congelar la cosecha original.
        """

        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol debe ser una cadena no vacía")

        self._rate_limiter.wait()

        try:
            ticker = yf.Ticker(symbol)
            history = ticker.history(period=period, interval=interval, auto_adjust=False, actions=True)
        except Exception as exc:  # pragma: no cover - depende de red externa
            logger.error("Error al obtener datos brutos de %s: %s", symbol, exc)
            raise

        if history is None or history.empty:
            raise ValueError(f"No se han recibido datos para el símbolo '{symbol}'")

        if drop_na:
            history = history.dropna(subset=["Close"])
            if history.empty:
                raise ValueError(f"Datos vacíos tras limpieza para el símbolo '{symbol}'")

        return history

    def get_last_close(
        self, symbol: str, period: str = "5d", interval: str = "1d"
    ) -> Tuple[Optional[float], Optional[pd.Timestamp]]:
        """Último cierre de ``symbol`` y la marca temporal de esa vela.

        Devuelve ``(None, None)`` en caso de error en vez de lanzar: quien lo
        usa (el conversor de divisa) debe poder degradar el informe a la
        divisa nativa en lugar de abortar el análisis entero.
        """

        try:
            history = self.get_history(symbol, period=period, interval=interval)
        except Exception as exc:
            logger.warning("No se pudo obtener el último cierre de %s: %s", symbol, exc)
            return None, None

        close = float(history["Close"].iloc[-1])
        timestamp = history.index[-1]
        return close, timestamp
