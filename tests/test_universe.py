"""Validación del universo: ISIN, metadatos y reglas de disponibilidad."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

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
        assert asset.region == "EUROPA"
        assert asset.currency == "EUR"

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
