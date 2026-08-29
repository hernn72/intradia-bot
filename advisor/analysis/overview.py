"""Panorama de mercados por región: cierre y variación de los índices de
contexto declarados en el universo (``analizable: false``).

Alimenta la sección "situación global" del informe diario. No genera
recomendaciones: un índice no se compra.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from advisor.data.market_data import MarketDataProvider
from advisor.universe.models import Asset, Universe

logger = logging.getLogger(__name__)

REGION_ORDER = ("ASIA", "EMERGING_MARKETS", "EUROPA", "USA", "GLOBAL")


def asia_session_change(quotes: List[IndexQuote]) -> Optional[float]:
    """Variación media (%) de los índices asiáticos del panorama.

    Asia cierra antes de que Europa abra: su media es la primera lectura del
    tono del día y alimenta la señal de contexto. ``None`` si ningún índice
    asiático tiene dato, para que el contexto puntúe esa parte como neutra.
    """

    changes = [q.change_pct for q in quotes if q.region == "ASIA" and q.change_pct is not None]
    if not changes:
        return None
    return sum(changes) / len(changes)


@dataclass(frozen=True)
class IndexQuote:
    """Última cotización conocida de un índice de contexto."""

    symbol: str
    name: str
    region: str
    currency: str
    price: Optional[float]
    change_pct: Optional[float]
    error: Optional[str] = None

    @property
    def available(self) -> bool:
        return self.price is not None


def fetch_overview(provider: MarketDataProvider, universe: Universe) -> List[IndexQuote]:
    """Descarga los índices de contexto del universo, en orden por región.

    Nunca lanza: un índice que falle aparece con ``error`` y el informe lo
    muestra como no disponible.
    """

    context_assets: List[Asset] = [a for a in universe.all_assets() if not a.analizable]
    if not context_assets:
        return []

    ordered = sorted(
        context_assets,
        key=lambda a: (REGION_ORDER.index(a.region) if a.region in REGION_ORDER else len(REGION_ORDER), a.symbol),
    )

    quotes: List[IndexQuote] = []
    for asset in ordered:
        try:
            history = provider.get_history(asset.symbol, period="1mo", interval="1d")
        except Exception as exc:
            logger.warning("Panorama — sin datos de %s: %s", asset.symbol, exc)
            quotes.append(
                IndexQuote(asset.symbol, asset.name, asset.region, asset.currency, None, None, str(exc))
            )
            continue

        close = history["Close"]
        price = float(close.iloc[-1])
        change_pct = None
        if len(close) >= 2:
            previous = float(close.iloc[-2])
            if previous > 0:
                change_pct = (price / previous - 1) * 100

        quotes.append(IndexQuote(asset.symbol, asset.name, asset.region, asset.currency, price, change_pct))

    return quotes
