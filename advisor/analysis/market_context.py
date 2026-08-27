"""Contexto de mercado: volatilidad implícita (VIX) y tendencia del índice de
referencia.

Adaptación del filtro de régimen de ``app/market/regime.py`` (trading-bot) a
las necesidades del asesor: allí el régimen escalaba la exposición del bot;
aquí solo puntúa el entorno en el que se plantea una operación y advierte
cuando el contexto es hostil.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from advisor.config import MarketContextConfig
from advisor.data.market_data import MarketDataProvider
from advisor.indicators.technical import sma

logger = logging.getLogger(__name__)

# Puntos de la dimensión "contexto de mercado" del sistema de puntuación.
CONTEXT_MAX_POINTS = 10.0


@dataclass(frozen=True)
class MarketContext:
    """Estado del mercado en el momento del análisis."""

    vix_value: Optional[float]
    vix_threshold: float
    trend_price: Optional[float]
    trend_sma: Optional[float]
    label: str
    reason: str
    # Variación media de la sesión de los índices asiáticos de contexto, en %.
    # Asia cierra antes de que abra Europa: su sesión es la señal más
    # temprana disponible sobre el tono del día (§5 de la especificación).
    asia_change_pct: Optional[float] = None

    @property
    def trend_up(self) -> Optional[bool]:
        """``True``/``False`` si hay datos de tendencia; ``None`` si no los hay."""
        if self.trend_price is None or self.trend_sma is None:
            return None
        return self.trend_price > self.trend_sma

    @property
    def points(self) -> float:
        """Puntuación 0-10 del entorno de mercado.

        Reparte 4 puntos por tendencia del índice de referencia, 4 por nivel
        de volatilidad implícita y 2 por el tono de la sesión asiática, que
        cierra antes de que Europa abra. Cuando falta un dato, esa parte se
        puntúa de forma neutra (la mitad) en vez de castigar al activo por
        una carencia que no es suya.
        """

        trend = self.trend_up
        trend_points = 2.0 if trend is None else (4.0 if trend else 0.0)

        if self.vix_value is None:
            vix_points = 2.0
        elif self.vix_value >= self.vix_threshold * 1.4:
            vix_points = 0.0
        elif self.vix_value >= self.vix_threshold:
            vix_points = 1.2
        elif self.vix_value <= self.vix_threshold * 0.6:
            vix_points = 4.0
        else:
            vix_points = 2.8

        asia = self.asia_change_pct
        if asia is None:
            asia_points = 1.0
        elif asia <= -1.5:
            asia_points = 0.0
        elif asia <= -0.5:
            asia_points = 0.5
        elif asia >= 0.5:
            asia_points = 2.0
        else:
            asia_points = 1.0

        return round(trend_points + vix_points + asia_points, 1)

    @property
    def is_hostile(self) -> bool:
        """Contexto claramente adverso: VIX por encima del umbral y tendencia bajista."""
        vix_high = self.vix_value is not None and self.vix_value >= self.vix_threshold
        trend = self.trend_up
        return vix_high and trend is False


def build_market_context(
    vix_value: Optional[float],
    trend_price: Optional[float],
    trend_sma: Optional[float],
    config: MarketContextConfig,
    asia_change_pct: Optional[float] = None,
) -> MarketContext:
    """Clasifica el contexto a partir de valores ya conocidos.

    Núcleo puro, sin I/O: lo usan tanto el análisis en vivo (con los últimos
    datos descargados) como el backtest (con los valores de cada fecha
    histórica), para que ambos apliquen exactamente el mismo criterio.
    """

    if vix_value is None and trend_price is None:
        return MarketContext(
            vix_value=None, vix_threshold=config.vix_threshold,
            trend_price=None, trend_sma=None,
            label="INDETERMINADO",
            reason="sin datos de volatilidad ni de tendencia del índice de referencia",
            asia_change_pct=asia_change_pct,
        )

    vix_high = vix_value is not None and vix_value >= config.vix_threshold
    trend_up = trend_price is not None and trend_sma is not None and trend_price > trend_sma

    if vix_high and not trend_up:
        label, reason = "RISK_OFF", f"VIX {vix_value:.1f} ≥ {config.vix_threshold:.1f} y tendencia no alcista"
    elif vix_high:
        label, reason = "CAUTELA", f"VIX {vix_value:.1f} ≥ {config.vix_threshold:.1f} pese a la tendencia alcista"
    elif trend_up:
        label, reason = "RISK_ON", "tendencia alcista del índice de referencia y volatilidad contenida"
    else:
        label, reason = "CAUTELA", "volatilidad contenida pero sin tendencia alcista confirmada"

    if asia_change_pct is not None and asia_change_pct <= -1.5:
        reason += f"; sesión asiática claramente negativa ({asia_change_pct:+.1f}%)"

    return MarketContext(
        vix_value=vix_value,
        vix_threshold=config.vix_threshold,
        trend_price=trend_price,
        trend_sma=trend_sma,
        label=label,
        reason=reason,
        asia_change_pct=asia_change_pct,
    )


def fetch_market_context(
    provider: MarketDataProvider,
    config: MarketContextConfig,
    asia_change_pct: Optional[float] = None,
) -> MarketContext:
    """Descarga VIX e índice de referencia y clasifica el contexto.

    Nunca lanza: si algún dato no está disponible, queda en ``None`` y el
    informe lo refleja como "N/D" en vez de abortar el análisis.
    """

    vix_value, _ = provider.get_last_close(config.vix_symbol)

    trend_price: Optional[float] = None
    trend_sma: Optional[float] = None
    try:
        history = provider.get_history(config.trend_symbol, period="2y", interval="1d")
    except Exception as exc:
        logger.warning("Contexto de mercado — sin datos de %s: %s", config.trend_symbol, exc)
    else:
        close = history["Close"]
        trend_price = float(close.iloc[-1])
        if len(close) >= config.trend_sma:
            last_sma = sma(close, config.trend_sma).iloc[-1]
            trend_sma = float(last_sma) if last_sma == last_sma else None  # NaN-safe

    return build_market_context(vix_value, trend_price, trend_sma, config, asia_change_pct)
