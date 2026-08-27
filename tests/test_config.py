"""Validación de la configuración."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from advisor.config import AdvisorConfig, IndicatorsConfig, LevelsConfig, ScoringConfig, load_config

_MINIMO = {"horizontes": {"swing": {"interval": "1d", "period": "1y", "min_bars": 120}}}


class TestAdvisorConfig:
    def test_carga_con_valores_por_defecto(self) -> None:
        config = AdvisorConfig(**_MINIMO)
        assert config.base_currency == "EUR"
        assert config.scoring.fundamentals_enabled is False

    def test_rechaza_divisa_base_no_soportada(self) -> None:
        with pytest.raises(ValidationError, match="base_currency"):
            AdvisorConfig(base_currency="XYZ", **_MINIMO)

    def test_rechaza_horizonte_desconocido(self) -> None:
        with pytest.raises(ValidationError, match="horizontes desconocidos"):
            AdvisorConfig(horizontes={"semanal": {"interval": "1d", "period": "1y", "min_bars": 10}})

    def test_horizonte_no_configurado_da_error_explicativo(self) -> None:
        config = AdvisorConfig(**_MINIMO)
        with pytest.raises(ValueError, match="no configurado"):
            config.horizonte("intradia")

    def test_horizonte_devuelve_la_ventana(self) -> None:
        assert AdvisorConfig(**_MINIMO).horizonte("swing").interval == "1d"


class TestIndicatorsConfig:
    def test_rechaza_ema_rapida_mayor_que_lenta(self) -> None:
        with pytest.raises(ValidationError, match="ema_fast"):
            IndicatorsConfig(ema_fast=50, ema_slow=20)

    def test_rechaza_macd_incoherente(self) -> None:
        with pytest.raises(ValidationError, match="macd_fast"):
            IndicatorsConfig(macd_fast=26, macd_slow=12)


class TestLevelsConfig:
    def test_exige_tres_objetivos(self) -> None:
        with pytest.raises(ValidationError, match="exactamente 3"):
            LevelsConfig(target_atr_multiples=[1.5, 3.0])

    def test_exige_objetivos_crecientes(self) -> None:
        with pytest.raises(ValidationError, match="creciente"):
            LevelsConfig(target_atr_multiples=[3.0, 1.5, 5.0])

    def test_rechaza_multiplo_no_positivo(self) -> None:
        with pytest.raises(ValidationError, match="> 0"):
            LevelsConfig(target_atr_multiples=[0.0, 3.0, 5.0])


class TestScoringConfig:
    def test_vigilar_no_puede_superar_operar(self) -> None:
        with pytest.raises(ValidationError, match="min_score_vigilar"):
            ScoringConfig(min_score_operar=60, min_score_vigilar=70)


class TestLoadConfig:
    def test_archivo_inexistente(self, tmp_path) -> None:
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "no_existe.yaml")

    def test_yaml_que_no_es_mapeo(self, tmp_path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text("- uno\n- dos\n", encoding="utf-8")
        with pytest.raises(ValueError, match="mapeo YAML"):
            load_config(path)

    def test_carga_un_archivo_real(self, tmp_path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text(yaml.safe_dump(_MINIMO), encoding="utf-8")
        assert load_config(path).horizonte("swing").min_bars == 120
