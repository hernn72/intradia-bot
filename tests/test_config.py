"""Validación de la configuración."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from advisor.config import (
    AdvisorConfig,
    EventsConfig,
    HorizonThresholds,
    IndicatorsConfig,
    LevelsConfig,
    PortfolioConfig,
    ScoringConfig,
    load_config,
)

_MINIMO = {"horizontes": {"swing": {"interval": "1d", "period": "1y", "min_bars": 120}}}


def _threshold(version: str = "1.0", operar: float | None = 70, vigilar: float | None = 60) -> dict:
    return {
        "score_model_version": version,
        "calibrated": False,
        "min_score_operar": operar,
        "min_score_vigilar": vigilar,
        "calibration_ref": None,
    }


def _thresholds_all() -> dict:
    return {horizon: _threshold() for horizon in ("intradia", "swing", "medio")}


_SCORING_EXPLICITO = {
    "scoring": {
        "score_model_version": "1.0",
        "thresholds": _thresholds_all(),
    }
}


class TestAdvisorConfig:
    def test_carga_con_valores_por_defecto(self) -> None:
        config = AdvisorConfig(**_MINIMO)
        assert config.base_currency == "EUR"
        assert config.scoring.fundamentals_enabled is False
        assert config.portfolio.risk_per_trade_pct == 0.5
        assert config.report.benchmark_by_region["USA"] == "^GSPC"
        assert config.events.pasada_evento_hora == "22:30"

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

    def test_rechaza_objetivos_repetidos(self) -> None:
        """Dos objetivos en el mismo precio no son "creciente"."""
        with pytest.raises(ValidationError, match="creciente"):
            LevelsConfig(target_atr_multiples=[1.5, 3.0, 3.0])

    def test_rechaza_multiplo_no_positivo(self) -> None:
        with pytest.raises(ValidationError, match="> 0"):
            LevelsConfig(target_atr_multiples=[0.0, 3.0, 5.0])


class TestScoringConfig:
    def test_vigilar_no_puede_superar_operar(self) -> None:
        with pytest.raises(ValidationError, match="min_score_vigilar"):
            HorizonThresholds(
                score_model_version="1.0",
                calibrated=False,
                min_score_operar=60,
                min_score_vigilar=70,
            )

    def test_rechaza_un_umbral_null_y_el_otro_numerico(self) -> None:
        with pytest.raises(ValidationError, match="ambos números o ambos null"):
            HorizonThresholds(
                score_model_version="1.0",
                calibrated=False,
                min_score_operar=None,
                min_score_vigilar=60,
            )

    def test_rechaza_calibration_ref_vacio(self) -> None:
        with pytest.raises(ValidationError, match="calibration_ref no puede estar vacío"):
            HorizonThresholds(
                score_model_version="1.0",
                calibrated=False,
                min_score_operar=70,
                min_score_vigilar=60,
                calibration_ref="  ",
            )

    def test_rechaza_calibrated_true_sin_ref(self) -> None:
        with pytest.raises(ValidationError, match="calibrated: true exige"):
            HorizonThresholds(
                score_model_version="2.0",
                calibrated=True,
                min_score_operar=70,
                min_score_vigilar=60,
                calibration_ref=None,
            )

    def test_rechaza_claves_globales_antiguas(self) -> None:
        with pytest.raises(ValidationError, match="claves antiguas"):
            ScoringConfig(min_score_operar=70)

    def test_v1_acepta_legacy_70_60_no_calibrado(self) -> None:
        config = ScoringConfig()

        assert config.score_model_version == "1.0"
        assert config.threshold_for("swing").calibrated is False
        assert config.threshold_for("swing").min_score_operar == 70

    def test_v1_rechaza_calibrated_true(self) -> None:
        with pytest.raises(ValidationError, match="calibrated no está permitido"):
            ScoringConfig(
                thresholds={
                    "swing": HorizonThresholds(
                        score_model_version="1.0",
                        calibrated=True,
                        min_score_operar=70,
                        min_score_vigilar=60,
                        calibration_ref="D-47 · evidence/x",
                    )
                }
            )

    def test_rechaza_score_model_version_no_implementada(self) -> None:
        with pytest.raises(ValidationError, match=r"score_model_version no implementada: 2\.0"):
            ScoringConfig(score_model_version="2.0", thresholds={h: _threshold("2.0", None, None) for h in _thresholds_all()})

    def test_rechaza_threshold_score_model_version_distinta(self) -> None:
        thresholds = _thresholds_all()
        thresholds["swing"] = _threshold("2.0")
        with pytest.raises(ValidationError, match=r"thresholds\.swing\.score_model_version"):
            ScoringConfig(thresholds=thresholds)

    def test_v1_rechaza_cortes_no_legacy(self) -> None:
        thresholds = _thresholds_all()
        thresholds["swing"] = _threshold(operar=75, vigilar=60)
        with pytest.raises(ValidationError, match="solo admite los cortes legacy 70/60"):
            ScoringConfig(thresholds=thresholds)

    def test_fundamentales_exigen_version_nueva(self) -> None:
        with pytest.raises(ValidationError, match="fundamentals_enabled"):
            ScoringConfig(fundamentals_enabled=True)


class TestPortfolioConfig:
    def test_capital_opcional_y_positivo_si_se_declara(self) -> None:
        assert PortfolioConfig().capital is None
        with pytest.raises(ValidationError, match="capital"):
            PortfolioConfig(capital=0)

    def test_rechaza_porcentajes_incoherentes(self) -> None:
        with pytest.raises(ValidationError, match="risk_per_trade_pct"):
            PortfolioConfig(risk_per_trade_pct=0)
        with pytest.raises(ValidationError, match="max_position_pct"):
            PortfolioConfig(max_position_pct=101)


class TestEventsConfig:
    def test_hora_de_pasada_por_evento_es_configurable(self) -> None:
        assert EventsConfig(pasada_evento_hora="21:45").pasada_evento_hora == "21:45"

    def test_rechaza_hora_de_pasada_invalida(self) -> None:
        with pytest.raises(ValidationError, match="pasada_evento_hora"):
            EventsConfig(pasada_evento_hora="24:00")


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
        path.write_text(yaml.safe_dump({**_MINIMO, **_SCORING_EXPLICITO}), encoding="utf-8")
        assert load_config(path).horizonte("swing").min_bars == 120

    def test_load_config_exige_bloque_scoring_explicito(self, tmp_path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text(yaml.safe_dump(_MINIMO), encoding="utf-8")

        with pytest.raises(ValueError, match=r"scoring\.score_model_version y scoring\.thresholds"):
            load_config(path)

    def test_load_config_exige_score_model_version_explicita(self, tmp_path) -> None:
        path = tmp_path / "config.yaml"
        payload = {
            **_MINIMO,
            "scoring": {
                "thresholds": _SCORING_EXPLICITO["scoring"]["thresholds"],
            },
        }
        path.write_text(yaml.safe_dump(payload), encoding="utf-8")

        with pytest.raises(ValueError, match=r"scoring\.score_model_version"):
            load_config(path)

    def test_load_config_exige_thresholds_explicitos(self, tmp_path) -> None:
        path = tmp_path / "config.yaml"
        payload = {**_MINIMO, "scoring": {"score_model_version": "1.0"}}
        path.write_text(yaml.safe_dump(payload), encoding="utf-8")

        with pytest.raises(ValueError, match=r"scoring\.thresholds"):
            load_config(path)

    def test_load_config_exige_thresholds_para_todos_los_horizontes_validos(self, tmp_path) -> None:
        path = tmp_path / "config.yaml"
        payload = {
            **_MINIMO,
            "scoring": {
                "score_model_version": "1.0",
                "thresholds": {
                    "swing": _threshold(),
                },
            },
        }
        path.write_text(yaml.safe_dump(payload), encoding="utf-8")

        with pytest.raises(ValidationError, match=r"falta scoring\.thresholds para horizontes válidos"):
            load_config(path)

    def test_load_config_acepta_thresholds_para_todos_los_horizontes_validos(self, tmp_path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text(yaml.safe_dump({**_MINIMO, **_SCORING_EXPLICITO}), encoding="utf-8")

        config = load_config(path)

        assert sorted(config.scoring.thresholds) == ["intradia", "medio", "swing"]

    def test_load_config_rechaza_threshold_horizonte_desconocido(self, tmp_path) -> None:
        path = tmp_path / "config.yaml"
        thresholds = _thresholds_all()
        thresholds["semanal"] = _threshold()
        payload = {
            **_MINIMO,
            "scoring": {
                "score_model_version": "1.0",
                "thresholds": thresholds,
            },
        }
        path.write_text(yaml.safe_dump(payload), encoding="utf-8")

        with pytest.raises(ValidationError, match="thresholds contiene horizontes desconocidos"):
            load_config(path)
