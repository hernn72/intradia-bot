"""Identificador canónico del universo point-in-time."""

from __future__ import annotations

import hashlib
import json
from typing import Any, List, Optional

from advisor.universe.models import Universe


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def universe_vintage_payload(
    universe: Universe,
    groups: Optional[List[str]] = None,
) -> list[dict[str, object]]:
    """Lista canónica de analizables que entra en el hash del universo.

    Con ``groups``, la lista es la de **esa** selección: una pasada sobre un
    subconjunto analiza una población distinta y no puede declarar el
    identificador de la lista entera (INV-19). Sin ``groups``, el resultado es
    el de siempre, bit a bit (D-23).
    """

    return [
        {
            "instrument_id": asset.instrument_id,
            "issuer_id": asset.issuer_id,
            "primary_symbol": asset.primary_symbol,
            "primary_market": asset.primary_market,
            "primary_currency": asset.primary_currency,
            "asset_class": asset.asset_class,
            "region": asset.region,
            "added_at": asset.added_at,
            "valid_to": asset.valid_to,
            "benchmark": asset.benchmark,
            # `benchmark: null` declarado y benchmark no declarado son cosas
            # distintas: `resolve_benchmark_symbol` decide por presencia en
            # `model_fields_set`, no por valor. Solo 2 de los 107 analizables
            # declaran benchmark, así que sin esta clave añadir `benchmark: null`
            # a cualquiera de los otros 105 le cambia el índice comparable —y con
            # él su fortaleza relativa y su puntuación— sin mover el vintage.
            "benchmark_declared": "benchmark" in asset.model_fields_set,
        }
        for asset in sorted(universe.analizables(groups), key=lambda item: item.instrument_id or "")
    ]


def universe_vintage_id(universe: Universe, groups: Optional[List[str]] = None) -> str:
    return canonical_hash(universe_vintage_payload(universe, groups))
