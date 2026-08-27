"""Orquestador del análisis, contexto de mercado y seguimiento de posiciones.

Todos los datos vienen de ``FakeProvider``: ningún test toca la red.
"""

from __future__ import annotations

import pytest

from advisor.analysis.analyzer import analyze_asset, run_analysis
from advisor.analysis.market_context import fetch_market_context
from advisor.analysis.overview import fetch_overview
from advisor.config import AdvisorConfig, MarketContextConfig
from advisor.report.tracking import (
    VERDICT_DEBILITA,
    VERDICT_INVALIDA,
    VERDICT_NO_CAMBIA,
    VERDICT_REFUERZA,
    _verdict,
    review_positions,
)
from advisor.storage.db import AdvisorDB
from tests.conftest import FakeProvider, make_ohlcv


@pytest.fixture
def histories() -> dict:
    return {
        "SAP.DE": make_ohlcv(n=300, start=200.0, drift=0.3),
        "AAPL": make_ohlcv(n=300, start=150.0, drift=0.2),
        "^STOXX50E": make_ohlcv(n=300, start=4500.0, drift=1.0),
        "^VIX": make_ohlcv(n=30, start=15.0, drift=0.0),
    }


class TestMarketContext:
    def test_risk_on_con_tendencia_y_vix_bajo(self, histories) -> None:
        provider = FakeProvider(histories, closes={"^VIX": 14.0})
        context = fetch_market_context(provider, MarketContextConfig())
        assert context.label == "RISK_ON"
        assert context.trend_up is True

    def test_risk_off_con_vix_alto_y_tendencia_bajista(self) -> None:
        provider = FakeProvider(
            {"^STOXX50E": make_ohlcv(n=300, start=5000.0, drift=-1.0)}, closes={"^VIX": 35.0}
        )
        context = fetch_market_context(provider, MarketContextConfig())
        assert context.label == "RISK_OFF"
        assert context.is_hostile is True

    def test_sin_datos_queda_indeterminado(self) -> None:
        context = fetch_market_context(FakeProvider(), MarketContextConfig())
        assert context.label == "INDETERMINADO"
        assert context.points == pytest.approx(5.0)  # ambas mitades neutras

    def test_puntuacion_acotada_a_diez(self, histories) -> None:
        provider = FakeProvider(histories, closes={"^VIX": 10.0})
        assert 0 <= fetch_market_context(provider, MarketContextConfig()).points <= 10


class TestOverview:
    def test_devuelve_los_indices_de_contexto(self, universe, histories) -> None:
        quotes = fetch_overview(FakeProvider(histories), universe)
        assert [q.symbol for q in quotes] == ["^STOXX50E"]
        assert quotes[0].available is True

    def test_indice_sin_datos_no_rompe(self, universe) -> None:
        quotes = fetch_overview(FakeProvider(), universe)
        assert quotes[0].available is False
        assert quotes[0].error is not None


class TestAnalyzeAsset:
    def test_analiza_un_activo(self, asset_eur, config, benign_context, histories) -> None:
        provider = FakeProvider(histories)
        opportunity = analyze_asset(asset_eur, config, provider, benign_context, "swing")

        assert opportunity.asset.symbol == "SAP.DE"
        assert opportunity.score.value > 0
        assert opportunity.levels.stop < opportunity.levels.price

    def test_historico_insuficiente_da_un_motivo_legible(self, asset_eur, config, benign_context) -> None:
        provider = FakeProvider({"SAP.DE": make_ohlcv(n=30)})
        with pytest.raises(ValueError, match="histórico insuficiente"):
            analyze_asset(asset_eur, config, provider, benign_context, "swing")


class TestRunAnalysis:
    def test_analiza_el_universo_y_ordena_por_nota(self, config, universe, histories) -> None:
        provider = FakeProvider(histories, closes={"^VIX": 14.0})
        result = run_analysis(config, universe, provider, horizonte="swing")

        assert len(result.opportunities) == 2
        valores = [o.score.value for o in result.opportunities]
        assert valores == sorted(valores, reverse=True)

    def test_un_activo_sin_datos_no_aborta_el_analisis(self, config, universe, histories) -> None:
        del histories["AAPL"]
        provider = FakeProvider(histories, closes={"^VIX": 14.0})
        result = run_analysis(config, universe, provider, horizonte="swing")

        assert [o.asset.symbol for o in result.opportunities] == ["SAP.DE"]
        assert result.skipped[0][0] == "AAPL"

    def test_los_indices_de_contexto_no_generan_oportunidades(self, config, universe, histories) -> None:
        provider = FakeProvider(histories, closes={"^VIX": 14.0})
        result = run_analysis(config, universe, provider, horizonte="swing")
        assert "^STOXX50E" not in [o.asset.symbol for o in result.opportunities]

    def test_filtra_por_grupo(self, config, universe, histories) -> None:
        provider = FakeProvider(histories, closes={"^VIX": 14.0})
        result = run_analysis(config, universe, provider, horizonte="swing", groups=["europa"])
        assert [o.asset.symbol for o in result.opportunities] == ["SAP.DE"]

    def test_universo_sin_activos_analizables(self, config, universe, histories) -> None:
        provider = FakeProvider(histories)
        with pytest.raises(ValueError, match="no hay activos analizables"):
            run_analysis(config, universe, provider, horizonte="swing", groups=["contexto"])


class TestVerdict:
    def _config(self) -> AdvisorConfig:
        return AdvisorConfig(horizontes={"swing": {"interval": "1d", "period": "1y", "min_bars": 120}})

    def test_stop_alcanzado_invalida(self) -> None:
        verdict, nota = _verdict(90.0, 100.0, stop=92.0, target=120.0, score=85.0, config=self._config())
        assert verdict == VERDICT_INVALIDA
        assert "stop alcanzado" in nota

    def test_el_stop_manda_sobre_la_puntuacion(self) -> None:
        """Una nota alta no puede justificar mantener una posición con el stop roto."""
        verdict, _ = _verdict(90.0, 100.0, stop=92.0, target=120.0, score=99.0, config=self._config())
        assert verdict == VERDICT_INVALIDA

    def test_objetivo_alcanzado_refuerza(self) -> None:
        verdict, nota = _verdict(125.0, 100.0, stop=92.0, target=120.0, score=50.0, config=self._config())
        assert verdict == VERDICT_REFUERZA
        assert "objetivo alcanzado" in nota

    def test_nota_baja_debilita(self) -> None:
        verdict, _ = _verdict(105.0, 100.0, stop=92.0, target=120.0, score=45.0, config=self._config())
        assert verdict == VERDICT_DEBILITA

    def test_nota_alta_y_posicion_a_favor_refuerza(self) -> None:
        verdict, _ = _verdict(105.0, 100.0, stop=92.0, target=120.0, score=75.0, config=self._config())
        assert verdict == VERDICT_REFUERZA

    def test_sin_puntuacion_no_cambia(self) -> None:
        verdict, nota = _verdict(105.0, 100.0, stop=92.0, target=120.0, score=None, config=self._config())
        assert verdict == VERDICT_NO_CAMBIA
        assert "sin datos suficientes" in nota

    def test_posicion_en_perdidas_sin_romper_stop_no_cambia(self) -> None:
        verdict, _ = _verdict(96.0, 100.0, stop=92.0, target=120.0, score=75.0, config=self._config())
        assert verdict == VERDICT_NO_CAMBIA


class TestReviewPositions:
    def test_sin_posiciones_devuelve_lista_vacia(self, config, universe, tmp_path, histories) -> None:
        db = AdvisorDB(tmp_path / "test.db")
        assert review_positions(config, universe, db, FakeProvider(histories)) == []

    def test_revisa_y_persiste(self, config, universe, tmp_path, histories) -> None:
        db = AdvisorDB(tmp_path / "test.db")
        position_id = db.open_position(
            symbol="SAP.DE", name="SAP", entry_price=200.0, currency="EUR", quantity=4,
            thesis="Ruptura con volumen", horizonte="swing", target=400.0, stop=180.0,
        )
        provider = FakeProvider(histories, closes={"^VIX": 14.0})

        reviews = review_positions(config, universe, db, provider)

        assert len(reviews) == 1
        assert reviews[0].symbol == "SAP.DE"
        assert reviews[0].pnl_pct > 0  # la serie sintética es alcista
        assert len(db.get_reviews(position_id)) == 1

    def test_activo_fuera_del_universo_sigue_revisandose(self, config, universe, tmp_path, histories) -> None:
        db = AdvisorDB(tmp_path / "test.db")
        db.open_position(
            symbol="ZZZ.DE", name="Antiguo", entry_price=100.0, currency="EUR", quantity=1,
            thesis="tesis heredada", horizonte="swing",
        )
        provider = FakeProvider({**histories, "ZZZ.DE": make_ohlcv(n=50, start=110.0)}, closes={"^VIX": 14.0})

        reviews = review_positions(config, universe, db, provider)

        assert len(reviews) == 1
        assert reviews[0].symbol == "ZZZ.DE"
        assert reviews[0].score is None  # no se puede repuntuar, pero no desaparece
