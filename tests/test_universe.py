"""Validación del universo: ISIN, metadatos y reglas de disponibilidad."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from advisor.analysis.benchmark import resolve_benchmark_symbol
from advisor.config import ReportConfig
from advisor.universe.loader import load_universe
from advisor.universe.models import Asset, Universe, isin_check_digit, validate_isin


def _asset(**overrides) -> dict:
    base = dict(
        symbol="sap.de",
        name="SAP",
        asset_class="stock",
        region="europa",
        market="XETRA",
        currency="eur",
        timezone="Europe/Berlin",
    )
    base.update(overrides)
    return base


class TestIsin:
    @pytest.mark.parametrize(
        "isin",
        [
            "US0378331005",  # Apple
            "DE0007164600",  # SAP
            "NL0010273215",  # ASML
            "IE00B4L5Y983",  # iShares Core MSCI World
        ],
    )
    def test_acepta_isin_con_checksum_correcto(self, isin: str) -> None:
        assert validate_isin(isin) == isin

    def test_normaliza_minusculas_y_espacios(self) -> None:
        assert validate_isin(" us0378331005 ") == "US0378331005"

    def test_rechaza_digito_de_control_incorrecto(self) -> None:
        with pytest.raises(ValueError, match="dígito de control"):
            validate_isin("US0378331006")

    def test_rechaza_longitud_incorrecta(self) -> None:
        with pytest.raises(ValueError, match="12 caracteres"):
            validate_isin("US037833100")

    def test_rechaza_pais_no_alfabetico(self) -> None:
        with pytest.raises(ValueError, match="código de país"):
            validate_isin("120378331005")

    def test_check_digit_es_consistente_con_el_isin_completo(self) -> None:
        assert isin_check_digit("US037833100") == 5


class TestAsset:
    def test_normaliza_simbolo_region_y_divisa(self) -> None:
        asset = Asset(**_asset())
        assert asset.symbol == "SAP.DE"
        assert asset.primary_symbol == "SAP.DE"
        assert asset.market == "XETRA"
        assert asset.primary_market == "XETRA"
        assert asset.region == "EUROPA"
        assert asset.currency == "EUR"
        assert asset.primary_currency == "EUR"
        assert asset.economic_currency == "EUR"

    def test_acepta_esquema_primary_sin_campos_compatibles(self) -> None:
        asset = Asset(
            primary_symbol="NVDA",
            primary_market="NASDAQ",
            primary_currency="USD",
            name="Nvidia",
            asset_class="stock",
            region="USA",
            economic_currency="USD",
            timezone="America/New_York",
        )

        assert asset.symbol == "NVDA"
        assert asset.market == "NASDAQ"
        assert asset.currency == "USD"
        assert asset.broker == "trade_republic"
        assert asset.execution_mode == "best_price"

    def test_isin_vacio_se_guarda_como_none(self) -> None:
        assert Asset(**_asset(isin="")).isin is None
        assert Asset(**_asset(isin=None)).isin is None

    def test_isin_invalido_falla_al_cargar(self) -> None:
        with pytest.raises(ValidationError):
            Asset(**_asset(isin="DE0007164601"))

    def test_timezone_invalida_falla(self) -> None:
        with pytest.raises(ValidationError):
            Asset(**_asset(timezone="Europe/Atlantis"))

    def test_trade_republic_por_defecto_es_desconocido(self) -> None:
        asset = Asset(**_asset())
        assert asset.trade_republic == "unknown"
        assert asset.availability_label == "⚠️ PENDIENTE DE VERIFICACIÓN"

    def test_disponibilidad_sin_verificar_no_impide_recomendar(self) -> None:
        """La restricción prohíbe AFIRMAR disponibilidad, no analizar el activo."""
        assert Asset(**_asset(trade_republic="unknown")).is_recommendable is True

    def test_no_disponible_excluye_de_recomendacion(self) -> None:
        asset = Asset(**_asset(trade_republic="no"))
        assert asset.is_recommendable is False
        assert asset.availability_label == "No"

    def test_indice_debe_ser_no_analizable(self) -> None:
        with pytest.raises(ValidationError, match="analizable"):
            Asset(**_asset(symbol="^GDAXI", asset_class="index"))

    def test_indice_no_puede_marcarse_como_comprable(self) -> None:
        with pytest.raises(ValidationError, match="no es comprable"):
            Asset(**_asset(symbol="^GDAXI", asset_class="index", analizable=False, trade_republic="yes"))

    def test_indice_valido_no_es_recomendable(self) -> None:
        asset = Asset(**_asset(symbol="^GDAXI", asset_class="index", analizable=False))
        assert asset.is_recommendable is False

    def test_requires_isin_se_deduce_por_clase(self) -> None:
        assert Asset(**_asset(asset_class="stock")).requires_isin is True
        assert Asset(**_asset(symbol="BTC-EUR", asset_class="crypto")).requires_isin is False
        assert Asset(**_asset(symbol="^GSPC", asset_class="index", analizable=False)).requires_isin is False

    def test_isin_no_aplica_en_cripto_e_indices(self) -> None:
        crypto = Asset(**_asset(symbol="BTC-EUR", asset_class="crypto", isin=None))
        index = Asset(**_asset(symbol="^GSPC", asset_class="index", analizable=False, isin=None))

        assert crypto.isin_label == "No aplica"
        assert index.isin_label == "No aplica"

    def test_rechaza_isin_en_clase_sin_isin(self) -> None:
        with pytest.raises(ValidationError, match="no debe llevar ISIN"):
            Asset(**_asset(symbol="BTC-EUR", asset_class="crypto", isin="US0378331005"))

    def test_acepta_commodity_etc_y_region_emergentes(self) -> None:
        etc = Asset(
            **_asset(
                symbol="4GLD.DE",
                name="Xetra-Gold",
                asset_class="commodity_etc",
                region="GLOBAL",
                isin="DE000A0S9GB0",
                economic_currency="XAU",
            )
        )
        emergentes = Asset(**_asset(symbol="IS3N.DE", asset_class="equity_etf", region="EMERGING_MARKETS"))

        assert etc.asset_class == "commodity_etc"
        assert emergentes.region == "EMERGING_MARKETS"

    def test_ticker_europeo_debe_declararse_completo(self) -> None:
        with pytest.raises(ValidationError, match="deben declararse juntos"):
            Asset(**_asset(european_symbol="NVD.DE"))

    def test_data_symbol_usa_ticker_europeo_en_premarket_de_eeuu(self) -> None:
        asset = Asset(
            **_asset(
                symbol="NVDA",
                market="NASDAQ",
                currency="USD",
                timezone="America/New_York",
                european_symbol="NVD.DE",
                european_market="XETRA",
                european_currency="EUR",
            )
        )

        assert asset.data_symbol(datetime.fromisoformat("2026-08-28T10:00:00+02:00")) == "NVD.DE"
        assert asset.data_symbol(datetime.fromisoformat("2026-08-28T16:00:00+02:00")) == "NVDA"


class TestDivisaEnPeniques:
    """Los peniques no pueden entrar en el universo.

    Es la trampa más cara del fichero: "GBp" y "GBP" solo se distinguen por
    la caja de una letra, y el proveedor devuelve peniques para las acciones
    de Londres. Si el validador los normalizase a mayúsculas, AstraZeneca a
    12.114 peniques (121,14 libras) se mostraría como 12.114 libras.
    """

    def test_rechaza_peniques(self) -> None:
        with pytest.raises(ValidationError, match="peniques"):
            Asset(**_asset(currency="GBp"))

    def test_rechaza_el_codigo_gbx(self) -> None:
        with pytest.raises(ValidationError, match="peniques"):
            Asset(**_asset(currency="GBX"))

    def test_las_libras_de_verdad_siguen_valiendo(self) -> None:
        assert Asset(**_asset(currency="GBP")).currency == "GBP"


class TestUniverse:
    def test_rechaza_simbolos_duplicados_entre_grupos(self) -> None:
        with pytest.raises(ValidationError, match="duplicado"):
            Universe(groups={"a": [Asset(**_asset())], "b": [Asset(**_asset())]})

    def test_rechaza_grupo_vacio(self) -> None:
        with pytest.raises(ValidationError):
            Universe(groups={"a": []})

    def test_analizables_excluye_contexto(self, universe: Universe) -> None:
        symbols = [a.symbol for a in universe.analizables()]
        assert "^STOXX50E" not in symbols
        assert {"SAP.DE", "AAPL"} == set(symbols)

    def test_analizables_filtra_por_grupo(self, universe: Universe) -> None:
        assert [a.symbol for a in universe.analizables(["europa"])] == ["SAP.DE"]

    def test_grupo_desconocido_falla_en_vez_de_devolver_lista_corta(self, universe: Universe) -> None:
        with pytest.raises(ValueError, match="grupos desconocidos"):
            universe.analizables(["no_existe"])

    def test_get_ignora_mayusculas(self, universe: Universe) -> None:
        assert universe.get("sap.de") is not None
        assert universe.get("NO_EXISTE") is None

    def test_get_acepta_simbolo_europeo_alternativo(self) -> None:
        asset = Asset(
            **_asset(
                symbol="NVDA",
                market="NASDAQ",
                currency="USD",
                timezone="America/New_York",
                european_symbol="NVD.DE",
                european_market="XETRA",
                european_currency="EUR",
            )
        )
        universe = Universe(groups={"usa": [asset]})

        assert universe.get("nvd.de") is asset
        assert universe.get("nvd.de").symbol == "NVDA"

    def test_universo_real_tiene_recuento_y_correcciones_nuevas(self) -> None:
        universe = load_universe("universe.yaml")

        assert len(universe.all_assets()) == 126
        assert len(universe.analizables()) == 107
        assert universe.get("IS3N.DE").region == "EMERGING_MARKETS"
        assert universe.get("4GLD.DE").asset_class == "commodity_etc"
        assert universe.get("BTC-EUR").requires_isin is False
        assert resolve_benchmark_symbol(universe.get("TSM"), ReportConfig()) == "^TWII"
        assert resolve_benchmark_symbol(universe.get("INFY"), ReportConfig()) is None

    def test_ningun_activo_cotiza_en_peniques(self) -> None:
        """Las de Londres se sustituyeron por sus cotizaciones en euros o su
        ADR: el proveedor las devuelve en peniques y el informe las mostraría
        multiplicadas por 100 (docs y validador de `currency`)."""

        universe = load_universe("universe.yaml")
        assert [a.symbol for a in universe.all_assets() if a.symbol.endswith(".L")] == []
        for simbolo, divisa in (("RRU.DE", "EUR"), ("BSP.DE", "EUR"), ("R6C0.DE", "EUR"), ("AZN", "USD")):
            assert universe.get(simbolo).currency == divisa

    def test_los_simbolos_sin_datos_se_sustituyeron_por_los_verificados(self) -> None:
        """VWSM.DE no existe en el proveedor y el índice 000300.SS solo trae
        una vela; ambos se cambiaron por tickers con histórico comprobado."""

        universe = load_universe("universe.yaml")
        assert universe.get("VWSM.DE") is None
        assert universe.get("000300.SS") is None
        assert universe.get("VVSM.DE").analizable is True
        assert universe.get("510300.SS").analizable is False
