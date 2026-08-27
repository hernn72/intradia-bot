"""Conversión de precios a la divisa base (euros), solo para presentación.

Este módulo existe por un motivo muy concreto: las recomendaciones se ejecutan
a mano en Trade Republic, en euros, así que la entrada, el stop y los objetivos
tienen que leerse en euros aunque el activo cotice en otra divisa.

Alcance deliberadamente limitado:

- Convierte **importes que se muestran**, nunca contabilidad ni cálculos. Los
  porcentajes (potencial, riesgo, ratio B/R) son invariantes a la divisa y no
  pasan por aquí.
- El valor convertido es **aproximado** y se etiqueta como tal: usa el cierre
  diario del par, no el tipo exacto que aplicará el bróker en el momento de
  ejecutar.
- Si el tipo de cambio no se puede obtener, ``to_base`` devuelve ``None`` y el
  informe muestra la divisa nativa con una advertencia. Nunca se inventa un
  tipo de cambio.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

import pandas as pd

from advisor.data.market_data import MarketDataProvider

logger = logging.getLogger(__name__)


class FxConverter:
    """Convierte importes a ``base_currency`` usando pares ``EUR<CCY>=X`` de yfinance.

    Cachea el tipo de cambio de cada divisa durante la vida del objeto (una
    ejecución del asesor): un informe debe usar un único tipo de cambio de
    principio a fin, y no tiene sentido descargar el mismo par una vez por
    activo.
    """

    def __init__(self, provider: MarketDataProvider, base_currency: str = "EUR") -> None:
        self._provider = provider
        self.base_currency = base_currency.strip().upper()
        self._rates: Dict[str, Optional[float]] = {self.base_currency: 1.0}
        self._as_of: Optional[pd.Timestamp] = None

    @property
    def as_of(self) -> Optional[pd.Timestamp]:
        """Marca temporal de la vela usada para el último tipo de cambio descargado."""
        return self._as_of

    def rate(self, currency: str) -> Optional[float]:
        """Unidades de ``base_currency`` por 1 unidad de ``currency``.

        Devuelve ``None`` si el par no está disponible. El resultado se cachea,
        incluido el fallo: si el par no se pudo descargar, no se reintenta en
        la misma ejecución.
        """

        ccy = currency.strip().upper()
        if ccy in self._rates:
            return self._rates[ccy]

        pair = f"{self.base_currency}{ccy}=X"
        close, timestamp = self._provider.get_last_close(pair)

        if close is None or close <= 0:
            logger.warning(
                "Tipo de cambio no disponible para %s (par %s): los importes se mostrarán en %s",
                ccy, pair, ccy,
            )
            self._rates[ccy] = None
            return None

        # El par EURUSD cotiza USD por 1 EUR; queremos EUR por 1 USD.
        converted = 1.0 / close
        self._rates[ccy] = converted
        if timestamp is not None and (self._as_of is None or timestamp > self._as_of):
            self._as_of = timestamp
        return converted

    def to_base(self, amount: Optional[float], currency: str) -> Optional[float]:
        """Convierte ``amount`` desde ``currency`` a la divisa base.

        Devuelve ``None`` si ``amount`` es ``None`` o si no hay tipo de cambio.
        """

        if amount is None:
            return None
        rate = self.rate(currency)
        if rate is None:
            return None
        return amount * rate

    def needs_conversion(self, currency: str) -> bool:
        """``True`` si ``currency`` no es la divisa base."""
        return currency.strip().upper() != self.base_currency
