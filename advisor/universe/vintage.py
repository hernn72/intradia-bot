"""Identificador canónico del universo point-in-time."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from advisor.universe.models import Universe


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def universe_vintage_payload(universe: Universe) -> list[dict[str, object]]:
    """Lista canónica de analizables que entra en el hash del universo."""

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
        }
        for asset in sorted(universe.analizables(), key=lambda item: item.instrument_id or "")
    ]


def universe_vintage_id(universe: Universe) -> str:
    return canonical_hash(universe_vintage_payload(universe))
