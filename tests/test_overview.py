"""El panorama global solo lleva contexto vigente, nunca bajas."""

from __future__ import annotations

from datetime import date

from advisor.analysis.overview import context_assets_of
from advisor.universe.loader import load_universe
from advisor.universe.models import Asset, Universe


def _indice() -> Asset:
    return Asset(
        symbol="^GDAXI", name="DAX", asset_class="index", region="EUROPA",
        market="XETRA", currency="EUR", timezone="Europe/Berlin",
        trade_republic="no", isin=None, analizable=False,
    )


def _baja() -> Asset:
    return Asset(
        symbol="UCG.MI", name="UniCredit", asset_class="stock", region="EUROPA",
        market="MIL", currency="EUR", timezone="Europe/Rome",
        trade_republic="no", isin=None, analizable=False, valid_to=date(2026, 9, 18),
    )


def test_una_baja_no_es_contexto_aunque_no_sea_analizable() -> None:
    universe = Universe(groups={"todo": [_indice(), _baja()]})

    simbolos = [a.symbol for a in context_assets_of(universe)]

    assert simbolos == ["^GDAXI"]


def test_el_universo_real_tiene_19_de_contexto_y_ninguna_baja() -> None:
    universe = load_universe("universe.yaml")

    contexto = context_assets_of(universe)

    assert len(contexto) == 19
    assert {"SAN.MC", "UCG.MI", "005930.KS", "1211.HK"}.isdisjoint({a.symbol for a in contexto})
