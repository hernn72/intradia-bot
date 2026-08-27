"""Modelos del universo de activos (``universe.yaml``).

Cada activo lleva los metadatos que la restricción fundamental del asesor
exige comprobar antes de recomendar una compra: nombre, ticker, ISIN,
mercado, divisa y disponibilidad en Trade Republic.

Sobre ``trade_republic`` e ``isin``: el asesor NO puede consultar el catálogo
de Trade Republic (no hay API pública), así que ambos campos se mantienen a
mano. El valor por defecto es deliberadamente ``unknown`` / ``None``: es
preferible que el informe diga "pendiente de verificación" a que el bot
afirme una disponibilidad que nadie ha comprobado.
"""

from __future__ import annotations

from typing import Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, field_validator, model_validator

VALID_ASSET_CLASSES = frozenset({
    "stock", "equity_etf", "bond_etf", "commodity_etf", "leveraged_etf",
    "index", "volatility_index", "crypto",
})

VALID_REGIONS = frozenset({"ASIA", "EUROPA", "USA", "GLOBAL"})

VALID_TRADE_REPUBLIC = frozenset({"yes", "no", "unknown"})

# Un índice no es un instrumento comprable: sirve de contexto, nunca de
# recomendación de compra.
_CONTEXT_ONLY_CLASSES = frozenset({"index", "volatility_index"})

_ISIN_LENGTH = 12


def isin_check_digit(isin_body: str) -> int:
    """Dígito de control de un ISIN (Luhn mod-10 sobre el cuerpo de 11 caracteres).

    Cada letra se expande a su posición alfabética + 9 (A=10 ... Z=35) antes
    de aplicar Luhn sobre la cadena de dígitos resultante.
    """

    digits = ""
    for char in isin_body.upper():
        if char.isdigit():
            digits += char
        elif char.isalpha():
            digits += str(ord(char) - ord("A") + 10)
        else:
            raise ValueError(f"carácter inválido en ISIN: '{char}'")

    total = 0
    # Luhn se aplica de derecha a izquierda, duplicando posiciones impares.
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 0:
            value *= 2
            if value > 9:
                value -= 9
        total += value

    return (10 - total % 10) % 10


def validate_isin(isin: str) -> str:
    """Valida formato y dígito de control de un ISIN. Devuelve el ISIN normalizado.

    Lanza ``ValueError`` si el formato o el checksum no son correctos: sirve
    para que una errata al teclear un ISIN falle al cargar el universo y no
    acabe en una recomendación.
    """

    cleaned = isin.strip().upper().replace(" ", "")
    if len(cleaned) != _ISIN_LENGTH:
        raise ValueError(f"ISIN inválido '{isin}': debe tener {_ISIN_LENGTH} caracteres, tiene {len(cleaned)}")
    if not cleaned[:2].isalpha():
        raise ValueError(f"ISIN inválido '{isin}': los 2 primeros caracteres deben ser el código de país (letras)")
    if not cleaned[2:].isalnum():
        raise ValueError(f"ISIN inválido '{isin}': los caracteres 3-12 deben ser alfanuméricos")
    if not cleaned[-1].isdigit():
        raise ValueError(f"ISIN inválido '{isin}': el último carácter debe ser el dígito de control")

    expected = isin_check_digit(cleaned[:-1])
    if int(cleaned[-1]) != expected:
        raise ValueError(f"ISIN inválido '{isin}': dígito de control incorrecto (esperado {expected})")

    return cleaned


class Asset(BaseModel):
    """Un activo analizable del universo."""

    symbol: str
    name: str
    asset_class: str
    region: str
    market: str
    currency: str
    timezone: str
    isin: Optional[str] = None
    trade_republic: str = "unknown"
    # Un activo con ``analizable: false`` se carga pero no se analiza: útil
    # para apartar temporalmente un valor sin borrar sus metadatos.
    analizable: bool = True
    notes: Optional[str] = None

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("symbol no puede estar vacío")
        return cleaned

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name no puede estar vacío")
        return value.strip()

    @field_validator("asset_class")
    @classmethod
    def _validate_asset_class(cls, value: str) -> str:
        if value not in VALID_ASSET_CLASSES:
            raise ValueError(f"asset_class inválido: '{value}'. Permitidos: {sorted(VALID_ASSET_CLASSES)}")
        return value

    @field_validator("region")
    @classmethod
    def _validate_region(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if cleaned not in VALID_REGIONS:
            raise ValueError(f"region inválida: '{value}'. Permitidas: {sorted(VALID_REGIONS)}")
        return cleaned

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if len(cleaned) != 3 or not cleaned.isalpha():
            raise ValueError(f"currency inválida: '{value}'. Debe ser un código ISO 4217 de 3 letras (p. ej. EUR)")
        return cleaned

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise ValueError(
                f"timezone inválido: '{value}'. Debe ser una zona IANA (p. ej. 'Europe/Berlin')"
            ) from None
        return value

    @field_validator("isin")
    @classmethod
    def _validate_isin(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None
        return validate_isin(value)

    @field_validator("trade_republic")
    @classmethod
    def _validate_trade_republic(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in VALID_TRADE_REPUBLIC:
            raise ValueError(
                f"trade_republic inválido: '{value}'. Permitidos: {sorted(VALID_TRADE_REPUBLIC)}"
            )
        return cleaned

    @model_validator(mode="after")
    def _validate_cross_fields(self) -> Asset:
        if self.asset_class in _CONTEXT_ONLY_CLASSES:
            if self.trade_republic == "yes":
                raise ValueError(
                    f"{self.symbol}: un {self.asset_class} no es comprable, "
                    f"trade_republic no puede ser 'yes'"
                )
            if self.analizable:
                raise ValueError(
                    f"{self.symbol}: un {self.asset_class} solo sirve de contexto, "
                    f"debe llevar analizable: false"
                )
        return self

    @property
    def is_recommendable(self) -> bool:
        """``True`` si el activo puede aparecer como recomendación de compra.

        Un ``trade_republic`` sin verificar ('unknown') no lo descarta: lo que
        la restricción fundamental prohíbe es AFIRMAR una disponibilidad no
        comprobada, no analizar el activo. Esos casos se recomiendan con la
        advertencia de ``availability_label``. Solo un 'no' explícito excluye.
        """
        return (
            self.analizable
            and self.trade_republic != "no"
            and self.asset_class not in _CONTEXT_ONLY_CLASSES
        )

    @property
    def availability_label(self) -> str:
        """Texto de disponibilidad en Trade Republic, tal y como debe salir en el informe."""
        if self.trade_republic == "yes":
            return "Sí"
        if self.trade_republic == "no":
            return "No"
        return "⚠️ PENDIENTE DE VERIFICACIÓN"


class Universe(BaseModel):
    """Universo completo, agrupado por lista."""

    groups: Dict[str, List[Asset]]

    @field_validator("groups")
    @classmethod
    def _validate_groups(cls, value: Dict[str, List[Asset]]) -> Dict[str, List[Asset]]:
        if not value:
            raise ValueError("el universo no puede estar vacío")
        for group_name, assets in value.items():
            if not assets:
                raise ValueError(f"el grupo '{group_name}' no tiene activos")
        return value

    @model_validator(mode="after")
    def _validate_unique_symbols(self) -> Universe:
        seen: Dict[str, str] = {}
        for group_name, assets in self.groups.items():
            for asset in assets:
                if asset.symbol in seen:
                    raise ValueError(
                        f"símbolo duplicado '{asset.symbol}': aparece en '{seen[asset.symbol]}' y en '{group_name}'"
                    )
                seen[asset.symbol] = group_name
        return self

    def all_assets(self) -> List[Asset]:
        """Todos los activos del universo, en orden de declaración."""
        return [asset for assets in self.groups.values() for asset in assets]

    def analizables(self, groups: Optional[List[str]] = None) -> List[Asset]:
        """Activos que deben analizarse, opcionalmente filtrados por grupo.

        Lanza ``ValueError`` si alguno de los grupos pedidos no existe: un
        nombre mal escrito debe fallar, no devolver silenciosamente una lista
        más corta de lo esperado.
        """
        if groups is None:
            selected = self.all_assets()
        else:
            unknown = [g for g in groups if g not in self.groups]
            if unknown:
                raise ValueError(f"grupos desconocidos: {unknown}. Disponibles: {sorted(self.groups)}")
            selected = [asset for g in groups for asset in self.groups[g]]
        return [asset for asset in selected if asset.analizable]

    def get(self, symbol: str) -> Optional[Asset]:
        """Busca un activo por símbolo (sin distinguir mayúsculas)."""
        target = symbol.strip().upper()
        for asset in self.all_assets():
            if asset.symbol == target:
                return asset
        return None
