"""Formato de importes del informe, siempre legibles en euros.

Regla única: **todo precio que aparezca en una recomendación —entrada, stop,
objetivos— tiene que poder leerse en euros**, porque la orden se ejecuta a
mano en Trade Republic y es en euros como se decide cuánto comprar.

Dos casos:

- El activo ya cotiza en euros: se muestra el importe y punto.
- El activo cotiza en otra divisa: se muestra el importe nativo y, entre
  paréntesis, su equivalente aproximado en euros. Nunca se sustituye el
  precio nativo por el convertido, porque el precio al que se cruzará la
  orden es el nativo.

Si no hay tipo de cambio, se dice: no se inventa una conversión.
"""

from __future__ import annotations

from typing import Optional

from advisor.data.fx import FxConverter


def format_amount(value: Optional[float], currency: str, decimals: int = 2) -> str:
    """Formatea un importe con separadores españoles: ``1.234,56 EUR``."""

    if value is None:
        return "N/D"
    formatted = f"{value:,.{decimals}f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return f"{formatted} {currency}"


def format_eur(value: Optional[float], decimals: int = 2) -> str:
    """Formatea un importe en euros: ``1.234,56 €``."""

    if value is None:
        return "N/D"
    formatted = f"{value:,.{decimals}f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return f"{formatted} €"


class MoneyFormatter:
    """Formatea los importes de un activo concreto en su divisa y en euros."""

    def __init__(self, fx: FxConverter, currency: str) -> None:
        self._fx = fx
        self.currency = currency.strip().upper()
        self.needs_conversion = fx.needs_conversion(self.currency)

    def __call__(self, value: Optional[float], decimals: int = 2) -> str:
        """Importe listo para el informe."""

        if value is None:
            return "N/D"

        if not self.needs_conversion:
            return format_eur(value, decimals)

        native = format_amount(value, self.currency, decimals)
        converted = self._fx.to_base(value, self.currency)
        if converted is None:
            return f"{native} (conversión a {self._fx.base_currency} no disponible)"
        return f"{native} (≈ {format_eur(converted, decimals)})"

    def eur_value(self, value: Optional[float]) -> Optional[float]:
        """Valor en euros, o ``None`` si no hay tipo de cambio. Para tablas y persistencia."""

        if value is None:
            return None
        if not self.needs_conversion:
            return value
        return self._fx.to_base(value, self.currency)

    def compact(self, value: Optional[float], decimals: int = 2) -> str:
        """Versión corta para tablas: solo el importe en euros cuando se puede."""

        eur = self.eur_value(value)
        if eur is not None:
            return format_eur(eur, decimals)
        return format_amount(value, self.currency, decimals)
