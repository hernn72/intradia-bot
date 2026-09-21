"""Reconstrucción de poblaciones históricas solo para laboratorio P2."""

from __future__ import annotations

from typing import Literal

from advisor.universe.models import Asset, Universe
from advisor.universe.vintage import universe_vintage_id

ResearchPopulationName = Literal["vigente", "d31", "pre-d31"]


def resolve_research_population(universe: Universe, population: ResearchPopulationName) -> Universe:
    """Devuelve una copia del universo para la población de laboratorio pedida.

    Reponer una baja anula ``valid_to`` porque ese campo entra en el hash del
    universo analizable. La función nunca muta el universo recibido.
    """

    if population not in {"vigente", "d31", "pre-d31"}:
        raise ValueError(f"población de laboratorio desconocida: {population}")
    groups: dict[str, list[Asset]] = {}
    for group, assets in universe.groups.items():
        groups[group] = [_asset_for_population(asset, population) for asset in assets]
    return Universe(groups=groups)


def research_population_header(universe: Universe, population: ResearchPopulationName) -> str:
    return (
        f"Población: {population} | activos analizables {len(universe.analizables())} | "
        f"universe_vintage_id {universe_vintage_id(universe)}"
    )


def _asset_for_population(asset: Asset, population: ResearchPopulationName) -> Asset:
    if population == "vigente":
        return asset.model_copy(deep=True)
    if population == "pre-d31" and asset.baja_decision in {"D-31", "D-35"}:
        return asset.model_copy(update={"analizable": True, "valid_to": None}, deep=True)
    if population == "d31" and asset.baja_decision == "D-35":
        return asset.model_copy(update={"analizable": True, "valid_to": None}, deep=True)
    return asset.model_copy(deep=True)
