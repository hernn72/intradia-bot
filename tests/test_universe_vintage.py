"""Vintage point-in-time del universo analizable."""

from __future__ import annotations

import pytest

from advisor.research.event_study import EventStudyResult, replay_managed_population
from advisor.research.population import resolve_research_population
from advisor.research.vintage import VintageLoad
from advisor.universe.loader import load_universe
from advisor.universe.models import Asset, Universe
from advisor.universe.vintage import universe_vintage_id

BASE_VINTAGE = "b11204ead2a392b2832764b234b584dd3f070b9a11a884bd3994d39364e30709"
WITH_THIRD_ASSET = "28534156227fa947f5cb788f360c91d0038834dc82835fc8fef3646ed33d0eed"
WITH_OTHER_BENCHMARK = "717e561a9a2b0cb736c4101c76c9a3ab65ac72d849bcd1a3d5d648b01c13a024"
REAL_UNIVERSE_VINTAGE = "237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19"
D31_VINTAGE = "c8496446d9b04795b8533e25e794c6141a4e73db73c0ef9bf98599b70f952132"
PRE_D31_VINTAGE = "894ce776ff8572b3a9dfc97a724f96789122e0dd2c46eef55045d4968e0b5fb0"
PRE_D31_WITH_VALID_TO_VINTAGE = "d75368d6e2fc3b5d74206abaf357ea7f9d081e5d692841be44921f9c28e36c0e"
D31_SYMBOLS = {"SAN.MC", "UCG.MI", "005930.KS", "1211.HK"}
D35_SYMBOLS = {"LRCX", "JPM", "GE", "RTX", "RHM.DE", "NOVO-B.CO", "9984.T", "000660.KS", "DFEN.DE", "4GLD.DE"}


SIN_DECLARAR = object()


def _asset(
    symbol: str,
    issuer_id: str,
    *,
    name: str | None = None,
    benchmark: object = "^GDAXI",
    notes: str | None = None,
) -> Asset:
    """Construye un activo; con ``benchmark=SIN_DECLARAR`` omite la clave.

    Declarar ``benchmark: null`` y no declarar el campo no son lo mismo:
    `resolve_benchmark_symbol` decide por presencia, no por valor.
    """

    extra = {} if benchmark is SIN_DECLARAR else {"benchmark": benchmark}
    return Asset(
        primary_symbol=symbol,
        primary_market="XETRA",
        primary_currency="EUR",
        name=name or symbol,
        asset_class="stock",
        region="EUROPA",
        economic_currency="EUR",
        timezone="Europe/Berlin",
        trade_republic="unknown",
        isin=None,
        issuer_id=issuer_id,
        instrument_id=f"{symbol}@XETRA",
        added_at="2026-08-27",
        valid_to=None,
        notes=notes,
        **extra,
    )


def _universe(*assets: Asset) -> Universe:
    return Universe(groups={"europa": list(assets)})


def test_vintage_estable_ante_cambios_de_nombre_o_notas() -> None:
    base = _universe(_asset("SAP.DE", "sap"), _asset("ALV.DE", "allianz"))
    renamed = _universe(
        _asset("SAP.DE", "sap"),
        _asset("ALV.DE", "allianz", name="Allianz cambiado", notes="no entra en el hash"),
    )

    assert universe_vintage_id(base) == BASE_VINTAGE
    assert universe_vintage_id(renamed) == BASE_VINTAGE


def test_vintage_cambia_si_entra_o_sale_un_activo() -> None:
    changed = _universe(_asset("SAP.DE", "sap"), _asset("ALV.DE", "allianz"), _asset("SIE.DE", "siemens"))

    assert universe_vintage_id(changed) == WITH_THIRD_ASSET
    assert WITH_THIRD_ASSET != BASE_VINTAGE


def test_vintage_cambia_si_cambia_el_benchmark() -> None:
    changed = _universe(
        _asset("SAP.DE", "sap", benchmark="^STOXX50E"),
        _asset("ALV.DE", "allianz"),
    )

    assert universe_vintage_id(changed) == WITH_OTHER_BENCHMARK
    assert WITH_OTHER_BENCHMARK != BASE_VINTAGE


def test_vintage_distingue_benchmark_declarado_nulo_de_no_declarado() -> None:
    """El caso que de verdad ocurre en `universe.yaml`.

    Solo 2 de los 107 analizables declaran benchmark. Para los otros 105,
    añadir `benchmark: null` cambia su índice comparable efectivo —y con él su
    fortaleza relativa y su puntuación— así que tiene que mover el vintage.
    Sin `benchmark_declared` en el payload, los dos casos colapsaban al mismo
    hash y el cambio quedaba invisible en todos los identificadores.
    """

    no_declarado = _universe(
        _asset("SAP.DE", "sap", benchmark=SIN_DECLARAR),
        _asset("ALV.DE", "allianz", benchmark=SIN_DECLARAR),
    )
    declarado_nulo = _universe(
        _asset("SAP.DE", "sap", benchmark=None),
        _asset("ALV.DE", "allianz", benchmark=SIN_DECLARAR),
    )

    assert universe_vintage_id(no_declarado) != universe_vintage_id(declarado_nulo)


def test_isin_sin_fuente_falla_al_cargar(tmp_path) -> None:
    universe_path = tmp_path / "universe.yaml"
    universe_path.write_text(
        """
groups:
  europa:
    - {primary_symbol: SAP.DE, primary_market: XETRA, primary_currency: EUR,
       name: SAP, asset_class: stock, region: EUROPA, economic_currency: EUR,
       timezone: Europe/Berlin, trade_republic: unknown, isin: DE0007164600,
       requires_isin: true, issuer_id: sap, instrument_id: DE0007164600,
       added_at: 2026-08-27, valid_to: null, delisted_at: null,
       ticker_history: [], trade_republic_checked_at: null}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="ISIN sin fuente"):
        load_universe(universe_path)


def test_universe_real_tiene_93_analizables_y_vintage_conocido() -> None:
    universe = load_universe("universe.yaml")

    assert len(universe.all_assets()) == 126
    # 107 hasta el 2026-09-18; luego cuatro bajas por no estar en Trade Republic
    # (D-31) y diez más el mismo día, los que estaban marcados `no` (D-35).
    assert len(universe.analizables()) == 93
    # Ninguna baja se queda analizable, y ninguna se cuela como contexto.
    assert [a.symbol for a in universe.all_assets() if a.trade_republic == "no" and a.analizable] == []
    assert universe_vintage_id(universe) == REAL_UNIVERSE_VINTAGE


def test_poblacion_pre_d31_reconstruye_107_y_d31_reconstruye_103() -> None:
    universe = load_universe("universe.yaml")
    vigente = resolve_research_population(universe, "vigente")
    d31 = resolve_research_population(universe, "d31")
    pre_d31 = resolve_research_population(universe, "pre-d31")

    assert len(vigente.analizables()) == 93
    assert len(d31.analizables()) == 103
    assert len(pre_d31.analizables()) == 107
    assert {asset.symbol for asset in d31.analizables()} - {asset.symbol for asset in vigente.analizables()} == D35_SYMBOLS
    assert {asset.symbol for asset in pre_d31.analizables()} - {asset.symbol for asset in d31.analizables()} == D31_SYMBOLS
    assert universe_vintage_id(vigente) == REAL_UNIVERSE_VINTAGE
    assert universe_vintage_id(d31) == D31_VINTAGE
    assert universe_vintage_id(pre_d31) == PRE_D31_VINTAGE
    assert all(asset.valid_to is None for asset in d31.analizables() if asset.symbol in D35_SYMBOLS)


def test_reponer_un_activo_sin_anular_valid_to_no_reproduce_el_hash() -> None:
    universe = load_universe("universe.yaml")
    groups = {
        group: [
            asset.model_copy(update={"analizable": True}, deep=True)
            if asset.baja_decision in {"D-31", "D-35"}
            else asset.model_copy(deep=True)
            for asset in assets
        ]
        for group, assets in universe.groups.items()
    }
    defectuoso = Universe(groups=groups)

    assert len(defectuoso.analizables()) == 107
    assert universe_vintage_id(defectuoso) == PRE_D31_WITH_VALID_TO_VINTAGE
    assert universe_vintage_id(defectuoso) != PRE_D31_VINTAGE


def test_campo_baja_no_mueve_el_universe_vintage_id() -> None:
    universe = load_universe("universe.yaml")

    assert {asset.symbol for asset in universe.all_assets() if asset.baja_decision == "D-31"} == D31_SYMBOLS
    assert {asset.symbol for asset in universe.all_assets() if asset.baja_decision == "D-35"} == D35_SYMBOLS
    assert universe_vintage_id(universe) == REAL_UNIVERSE_VINTAGE


def test_comparacion_pareada_aborta_con_universo_distinto() -> None:
    result = EventStudyResult(
        data_vintage_id="data-vintage",
        universe_vintage_id="universo-a",
        horizonte="swing",
        cost_pct=0.2,
        warmup_bars=120,
        max_hold_bars=40,
    )
    vintage = VintageLoad(
        data_vintage_id="data-vintage",
        manifest={"universe_vintage_id": "universo-b"},
        by_symbol={},
    )

    with pytest.raises(ValueError, match="universo distinto"):
        replay_managed_population(result, vintage, _levels_config(), min_rr_ratio=1.5)


def _levels_config():
    from advisor.config import LevelsConfig

    return LevelsConfig()
