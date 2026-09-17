"""Modelos del universo de activos (``universe.yaml``).

Cada activo lleva los metadatos que la restricción fundamental del asesor
exige comprobar antes de recomendar una compra: nombre, ticker, ISIN,
mercado de datos, divisa y disponibilidad en Trade Republic.

Sobre ``trade_republic``: el asesor NO puede consultar el catálogo de Trade
Republic (no hay API pública), así que ese campo se mantiene a mano. El valor
por defecto es deliberadamente ``unknown``: es preferible que el informe diga
"pendiente de verificación" a que el bot afirme una disponibilidad que nadie
ha comprobado. El ISIN es otro dato distinto: se guarda solo cuando se ha
verificado por una fuente fiable.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, PrivateAttr, field_validator, model_validator

VALID_ASSET_CLASSES = frozenset({
    "stock", "equity_etf", "bond_etf", "commodity_etf", "commodity_etc", "leveraged_etf",
    "index", "volatility_index", "crypto",
})

VALID_REGIONS = frozenset({"ASIA", "EUROPA", "USA", "GLOBAL", "EMERGING_MARKETS"})

VALID_TRADE_REPUBLIC = frozenset({"yes", "no", "unknown"})

VALID_BROKERS = frozenset({"trade_republic"})

VALID_EXECUTION_MODES = frozenset({"best_price", "direct_price", "unknown"})

# Un índice no es un instrumento comprable: sirve de contexto, nunca de
# recomendación de compra.
_CONTEXT_ONLY_CLASSES = frozenset({"index", "volatility_index"})

_NO_ISIN_REQUIRED_CLASSES = frozenset({"crypto", "index", "volatility_index"})

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
    economic_currency: str
    timezone: str
    primary_symbol: str
    primary_market: str
    primary_currency: str
    european_symbol: Optional[str] = None
    european_market: Optional[str] = None
    european_currency: Optional[str] = None
    benchmark: Optional[str] = None
    broker: str = "trade_republic"
    execution_mode: str = "best_price"
    isin: Optional[str] = None
    issuer_id: Optional[str] = None
    instrument_id: Optional[str] = None
    added_at: Optional[date] = None
    valid_to: Optional[date] = None
    delisted_at: Optional[date] = None
    ticker_history: List[str] = Field(default_factory=list)
    isin_verified_at: Optional[date] = None
    isin_source: Optional[str] = None
    trade_republic_checked_at: Optional[date] = None
    requires_isin: Optional[bool] = None
    trade_republic: str = "unknown"
    # Un activo con ``analizable: false`` se carga pero no se analiza: útil
    # para apartar temporalmente un valor sin borrar sus metadatos.
    analizable: bool = True
    notes: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _fill_compatibility_fields(cls, data):
        if not isinstance(data, dict):
            return data

        values = dict(data)
        if "symbol" not in values and "primary_symbol" in values:
            values["symbol"] = values["primary_symbol"]
        if "primary_symbol" not in values and "symbol" in values:
            values["primary_symbol"] = values["symbol"]

        if "market" not in values and "primary_market" in values:
            values["market"] = values["primary_market"]
        if "primary_market" not in values and "market" in values:
            values["primary_market"] = values["market"]

        if "currency" not in values and "primary_currency" in values:
            values["currency"] = values["primary_currency"]
        if "primary_currency" not in values and "currency" in values:
            values["primary_currency"] = values["currency"]

        if "economic_currency" not in values and "currency" in values:
            values["economic_currency"] = values["currency"]
        return values

    @field_validator("symbol", "primary_symbol", "european_symbol")
    @classmethod
    def _validate_symbol(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("symbol no puede estar vacío")
        return cleaned

    @field_validator("benchmark")
    @classmethod
    def _validate_benchmark(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("benchmark no puede estar vacío; usa null para indicar explícitamente sin benchmark")
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

    @field_validator("currency", "economic_currency", "primary_currency", "european_currency")
    @classmethod
    def _validate_currency(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        # "GBp" (peniques) y "GBP" (libras) solo se distinguen por la caja de
        # la última letra y valen 100 veces distinto: el proveedor devuelve
        # 12.114 para una acción de AstraZeneca que cuesta 121,14 libras.
        # Pasar a mayúsculas convertiría peniques en libras sin decir nada y
        # multiplicaría por 100 todos los precios del informe, así que se
        # rechaza aquí, al cargar, en vez de mentir sobre dinero después.
        crudo = value.strip()
        if crudo == "GBp" or crudo.upper() == "GBX":
            raise ValueError(
                f"currency '{value}': ese activo cotiza en peniques, no en libras. "
                "Usa su cotización en EUR (Xetra) o su ADR en USD; con peniques, "
                "todo importe del informe saldría multiplicado por 100"
            )
        cleaned = value.strip().upper()
        if cleaned == "GBP":
            return cleaned
        if cleaned == "MULTI":
            return cleaned
        if len(cleaned) != 3 or not cleaned.isalpha():
            raise ValueError(
                f"currency inválida: '{value}'. Debe ser un código de 3 letras (p. ej. EUR) o MULTI"
            )
        return cleaned

    @field_validator("market", "primary_market", "european_market")
    @classmethod
    def _validate_market(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("market no puede estar vacío")
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

    @field_validator("issuer_id")
    @classmethod
    def _validate_issuer_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip().lower()
        if not cleaned:
            return None
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-_")
        if any(char not in allowed for char in cleaned):
            raise ValueError("issuer_id debe ser un slug en minúsculas")
        return cleaned

    @field_validator("instrument_id")
    @classmethod
    def _validate_instrument_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip().upper()
        if not cleaned:
            return None
        return cleaned

    @field_validator("ticker_history")
    @classmethod
    def _validate_ticker_history(cls, value: List[str]) -> List[str]:
        return [symbol.strip().upper() for symbol in value if symbol.strip()]

    @field_validator("trade_republic")
    @classmethod
    def _validate_trade_republic(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in VALID_TRADE_REPUBLIC:
            raise ValueError(
                f"trade_republic inválido: '{value}'. Permitidos: {sorted(VALID_TRADE_REPUBLIC)}"
            )
        return cleaned

    @field_validator("broker")
    @classmethod
    def _validate_broker(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in VALID_BROKERS:
            raise ValueError(f"broker inválido: '{value}'. Permitidos: {sorted(VALID_BROKERS)}")
        return cleaned

    @field_validator("execution_mode")
    @classmethod
    def _validate_execution_mode(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in VALID_EXECUTION_MODES:
            raise ValueError(
                f"execution_mode inválido: '{value}'. Permitidos: {sorted(VALID_EXECUTION_MODES)}"
            )
        return cleaned

    @model_validator(mode="after")
    def _validate_cross_fields(self) -> Asset:
        # ``symbol`` sigue siendo la identidad canónica de la app: base de
        # datos, posiciones y deduplicación lo usan como clave. En activos con
        # doble símbolo, ``symbol`` equivale a ``primary_symbol``; el ticker
        # europeo es solo una ruta alternativa para leer datos durante la
        # sesión europea o la preapertura de EE. UU.
        if self.symbol != self.primary_symbol:
            raise ValueError(f"{self.symbol}: symbol debe coincidir con primary_symbol")
        if self.market != self.primary_market:
            raise ValueError(f"{self.symbol}: market debe coincidir con primary_market")
        if self.currency != self.primary_currency:
            raise ValueError(f"{self.symbol}: currency debe coincidir con primary_currency")

        european = [self.european_symbol, self.european_market, self.european_currency]
        if any(value is not None for value in european) and not all(value is not None for value in european):
            raise ValueError(
                f"{self.symbol}: european_symbol, european_market y european_currency deben declararse juntos"
            )

        if self.requires_isin is None:
            self.requires_isin = self.asset_class not in _NO_ISIN_REQUIRED_CLASSES
        if self.isin is not None and not self.requires_isin:
            raise ValueError(f"{self.symbol}: un {self.asset_class} no debe llevar ISIN en este universo")

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
        if self.isin is not None and (
            self.isin_verified_at is None or self.isin_source is None or not self.isin_source.strip()
        ):
            raise ValueError(f"{self.symbol}: un ISIN sin fuente no es verificado")
        if self.instrument_id is None:
            self.instrument_id = self.isin if self.isin is not None else f"{self.primary_symbol}@{self.primary_market}"
        return self

    def data_symbol(self, now: Optional[datetime] = None) -> str:
        """Símbolo que debe consultarse al proveedor de datos en este momento."""

        if self.european_symbol is None or now is None:
            return self.symbol

        try:
            berlin_now = now.astimezone(ZoneInfo("Europe/Berlin"))
            new_york_now = now.astimezone(ZoneInfo("America/New_York"))
        except ValueError:
            return self.symbol

        if berlin_now.weekday() >= 5:
            return self.symbol
        if 8 <= berlin_now.hour < 22 and new_york_now.hour < 9:
            return self.european_symbol
        if new_york_now.hour == 9 and new_york_now.minute < 30:
            return self.european_symbol
        return self.symbol

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

    @property
    def isin_label(self) -> str:
        """Texto del ISIN para informes, distinguiendo pendiente de no aplicable."""
        if self.isin is not None:
            return self.isin
        if self.requires_isin:
            return "⚠️ NO REGISTRADO — complétalo en universe.yaml"
        return "No aplica"


class Universe(BaseModel):
    """Universo completo, agrupado por lista."""

    groups: Dict[str, List[Asset]]
    _by_symbol: Dict[str, Asset] = PrivateAttr(default_factory=dict)

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
                if asset.european_symbol is not None:
                    if asset.european_symbol in seen:
                        raise ValueError(
                            f"símbolo duplicado '{asset.european_symbol}': aparece como ticker alternativo de "
                            f"'{asset.symbol}' y en '{seen[asset.european_symbol]}'"
                        )
                    seen[asset.european_symbol] = group_name
        self._by_symbol = {
            symbol: asset
            for asset in self.all_assets()
            for symbol in (asset.symbol, asset.european_symbol)
            if symbol is not None
        }
        return self

    def all_assets(self) -> List[Asset]:
        """Todos los activos del universo, en orden de declaración."""
        return [asset for assets in self.groups.values() for asset in assets]

    def validate_identity_metadata(self) -> None:
        """Exige identidad point-in-time en el universo cargado desde YAML."""

        missing: List[str] = []
        for asset in self.all_assets():
            if asset.issuer_id is None:
                missing.append(f"{asset.symbol}: issuer_id")
            if asset.added_at is None:
                missing.append(f"{asset.symbol}: added_at")
            if asset.instrument_id is None:
                missing.append(f"{asset.symbol}: instrument_id")
        if missing:
            raise ValueError("identidad de universo incompleta: " + ", ".join(missing))

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
        """Busca un activo por símbolo canónico o alternativo, sin distinguir mayúsculas."""
        target = symbol.strip().upper()
        return self._by_symbol.get(target)
