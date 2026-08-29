"""Resolución del índice comparable para fortaleza relativa."""

from __future__ import annotations

from typing import Optional

from advisor.config import ReportConfig
from advisor.universe.models import Asset


def resolve_benchmark_symbol(asset: Asset, config: ReportConfig) -> Optional[str]:
    """Devuelve el benchmark del activo, o ``None`` si se declaró sin comparable."""

    if "benchmark" in asset.model_fields_set:
        return asset.benchmark

    if asset.asset_class == "crypto":
        return None

    # La exposición económica manda sobre la plaza: ADRs asiáticos como TSM o
    # INFY cotizan en NYSE, pero no deben compararse contra el S&P 500.
    if asset.region == "ASIA" and asset.primary_market in config.benchmark_by_market:
        return config.benchmark_by_market[asset.primary_market]

    if asset.region in config.benchmark_by_region:
        return config.benchmark_by_region[asset.region]

    if asset.primary_market in config.benchmark_by_market:
        return config.benchmark_by_market[asset.primary_market]

    return config.benchmark_symbol
