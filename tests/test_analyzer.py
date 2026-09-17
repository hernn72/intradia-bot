"""Orquestador del análisis, contexto de mercado y seguimiento de posiciones.

Todos los datos vienen de ``FakeProvider``: ningún test toca la red.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import pytest

from advisor.analysis.analyzer import analyze_asset, run_analysis
from advisor.analysis.benchmark import resolve_benchmark_symbol
from advisor.analysis.market_context import build_market_context, fetch_market_context
from advisor.analysis.opportunity import ANALYSIS_ERROR, INSUFFICIENT_HISTORY, INVALID_INDICATORS
from advisor.analysis.overview import IndexQuote, asia_session_change, fetch_overview
from advisor.config import AdvisorConfig, MarketContextConfig
from advisor.data.calendars import expected_sessions
from advisor.data.quality import FreshnessState
from advisor.report.tracking import (
    VERDICT_DEBILITA,
    VERDICT_INVALIDA,
    VERDICT_NO_CAMBIA,
    VERDICT_REFUERZA,
    _verdict,
    review_positions,
)
from advisor.storage.db import AdvisorDB
from advisor.universe.models import Asset
from tests.conftest import FakeProvider, make_ohlcv


def _asset(
    symbol: str,
    region: str,
    market: str,
    asset_class: str = "stock",
    benchmark: str | None = None,
    set_benchmark: bool = False,
) -> Asset:
    extra = {"benchmark": benchmark} if set_benchmark else {}
    return Asset(
        symbol=symbol,
        name=symbol,
        asset_class=asset_class,
        region=region,
        market=market,
        currency="USD",
        timezone="America/New_York",
        trade_republic="yes",
        **extra,
    )


def _cripto() -> Asset:
    """Cripto tal como está declarada en ``universe.yaml``: zona horaria UTC."""

    return Asset(
        symbol="BTC-EUR",
        name="Bitcoin",
        asset_class="crypto",
        region="GLOBAL",
        market="CRYPTO",
        currency="EUR",
        timezone="UTC",
        trade_republic="unknown",
    )


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
            {
                "^STOXX50E": make_ohlcv(n=300, start=5000.0, drift=-1.0),
                "^VIX": make_ohlcv(n=30, start=35.0, drift=0.0),
            }
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


class TestAsiaSignal:
    def _context(self, asia):
        return build_market_context(14.0, 5000.0, 4800.0, MarketContextConfig(), asia_change_pct=asia)

    def test_asia_positiva_suma_y_negativa_resta(self) -> None:
        sin_asia = self._context(None)
        alcista = self._context(1.2)
        bajista = self._context(-2.0)
        assert alcista.points > sin_asia.points > bajista.points

    def test_sin_dato_asiatico_puntua_neutro(self) -> None:
        assert self._context(None).points == self._context(0.0).points

    def test_desplome_asiatico_aparece_en_el_motivo(self) -> None:
        context = self._context(-2.4)
        assert "asiática" in context.reason
        assert "-2,4" in context.reason.replace(".", ",")

    def test_asia_no_convierte_el_contexto_en_hostil_por_si_sola(self) -> None:
        """Asia puntúa, pero el veto de hostilidad sigue siendo VIX + tendencia."""
        assert self._context(-3.0).is_hostile is False

    def test_media_de_la_sesion_asiatica(self) -> None:
        quotes = [
            IndexQuote("^N225", "Nikkei", "ASIA", "JPY", 40000.0, -1.0),
            IndexQuote("^HSI", "Hang Seng", "ASIA", "HKD", 18000.0, -2.0),
            IndexQuote("^GDAXI", "DAX", "EUROPA", "EUR", 20000.0, 5.0),
            IndexQuote("^KS11", "Kospi", "ASIA", "KRW", None, None, "sin datos"),
        ]
        assert asia_session_change(quotes) == -1.5

    def test_sin_indices_asiaticos_devuelve_none(self) -> None:
        assert asia_session_change([]) is None


class TestOverview:
    def test_devuelve_los_indices_de_contexto(self, universe, histories) -> None:
        quotes = fetch_overview(FakeProvider(histories), universe)
        assert [q.symbol for q in quotes] == ["^STOXX50E"]
        assert quotes[0].available is True

    def test_indice_sin_datos_no_rompe(self, universe) -> None:
        quotes = fetch_overview(FakeProvider(), universe)
        assert quotes[0].available is False
        assert quotes[0].error is not None


class TestBenchmarkRegional:
    def test_resuelve_por_region_y_mercado_asiatico(self) -> None:
        config = AdvisorConfig(horizontes={"swing": {"interval": "1d", "period": "1y", "min_bars": 120}})

        assert resolve_benchmark_symbol(_asset("AAPL", "USA", "NASDAQ"), config.report) == "^GSPC"
        assert resolve_benchmark_symbol(_asset("SAP.DE", "EUROPA", "XETRA"), config.report) == "^STOXX"
        assert resolve_benchmark_symbol(_asset("7203.T", "ASIA", "JPX"), config.report) == "^N225"
        assert resolve_benchmark_symbol(_asset("0700.HK", "ASIA", "HKG"), config.report) == "^HSI"

    def test_adrs_asiaticos_no_usan_benchmark_usa_por_cotizar_en_nyse(self) -> None:
        config = AdvisorConfig(horizontes={"swing": {"interval": "1d", "period": "1y", "min_bars": 120}})

        assert resolve_benchmark_symbol(_asset("TSM", "ASIA", "NYSE", benchmark="^TWII", set_benchmark=True), config.report) == "^TWII"
        assert resolve_benchmark_symbol(_asset("INFY", "ASIA", "NYSE", benchmark=None, set_benchmark=True), config.report) is None

    def test_cripto_y_emergentes_quedan_sin_benchmark(self) -> None:
        config = AdvisorConfig(horizontes={"swing": {"interval": "1d", "period": "1y", "min_bars": 120}})

        assert resolve_benchmark_symbol(_asset("BTC-USD", "GLOBAL", "CRYPTO", "crypto"), config.report) is None
        assert resolve_benchmark_symbol(_asset("EM", "EMERGING_MARKETS", "NYSE"), config.report) is None

    def test_benchmark_null_en_activo_es_explicitamente_ninguno(self) -> None:
        config = AdvisorConfig(horizontes={"swing": {"interval": "1d", "period": "1y", "min_bars": 120}})
        asset = Asset(
            symbol="CUSTOM",
            name="Custom",
            asset_class="stock",
            region="USA",
            market="NASDAQ",
            currency="USD",
            timezone="America/New_York",
            benchmark=None,
        )

        assert resolve_benchmark_symbol(asset, config.report) is None


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
        assert result.skipped[0].code == INSUFFICIENT_HISTORY

    def test_un_fallo_no_reconocido_no_se_publica_como_indicadores_invalidos(
        self, config, universe, histories
    ) -> None:
        """INV-16: lo desconocido se declara desconocido.

        El caso por defecto era `INVALID_INDICATORS`, así que un 404 del
        proveedor, un timeout o una plaza sin calendario se publicaban en el
        informe afirmando una causa técnica que nadie había comprobado.
        """

        class ProveedorQueFalla(FakeProvider):
            def get_history(self, symbol, period="1y", interval="1d"):
                if symbol == "AAPL":
                    raise RuntimeError("HTTP Error 404: Not Found")
                return super().get_history(symbol, period=period, interval=interval)

        provider = ProveedorQueFalla(histories, closes={"^VIX": 14.0})
        result = run_analysis(config, universe, provider, horizonte="swing")

        fallido = next(skipped for skipped in result.skipped if skipped.symbol == "AAPL")
        assert fallido.code == ANALYSIS_ERROR
        assert fallido.code != INVALID_INDICATORS
        assert "404" in fallido.reason

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

    def test_cachea_benchmarks_compartidos(self, config, universe, histories) -> None:
        histories["^GSPC"] = make_ohlcv(n=300, start=5000.0, drift=2.0)
        provider = FakeProvider(histories, closes={"^VIX": 14.0})

        run_analysis(config, universe, provider, horizonte="swing")

        assert provider.calls.count("^GSPC") == 1

    def test_benchmark_nunca_define_sesiones(self, config, benign_context) -> None:
        asset = _asset("TSM", "ASIA", "NYSE", benchmark="^TWII", set_benchmark=True)
        nyse_sessions = expected_sessions("NYSE", date(2026, 3, 2), date(2026, 9, 8))
        nyse_dates = pd.DatetimeIndex([pd.Timestamp(value, tz="America/New_York") for value in nyse_sessions])
        history = make_ohlcv(n=len(nyse_dates), start_date="2026-03-02").set_axis(nyse_dates)
        benchmark_dates = nyse_dates.append(
            pd.DatetimeIndex([pd.Timestamp("2026-09-07", tz="America/New_York")])
        ).sort_values()
        benchmark = make_ohlcv(n=len(benchmark_dates), start=5000.0).set_axis(benchmark_dates)
        provider = FakeProvider({"TSM": history, "^TWII": benchmark})

        opportunity = analyze_asset(
            asset,
            config,
            provider,
            benign_context,
            "swing",
            benchmark_close=benchmark["Close"],
            benchmark_symbol="^TWII",
            now=datetime(2026, 9, 8, 21, 0, tzinfo=timezone.utc),
        )

        assert opportunity.data_freshness is not None
        assert opportunity.data_freshness.calendar == "XNYS"
        assert opportunity.data_freshness.absent_reference_sessions == ()

    def test_cripto_declara_la_barra_del_dia_en_curso_como_parcial(self, config, benign_context) -> None:
        """Cripto no cierra: la barra de hoy es parcial hasta UTC 00:00 + settlement."""

        asset = _cripto()
        fechas = pd.date_range(end="2026-09-16", periods=300, freq="D", tz="UTC")
        history = make_ohlcv(n=len(fechas), start=50_000.0).set_axis(fechas)
        provider = FakeProvider({"BTC-EUR": history})

        opportunity = analyze_asset(
            asset,
            config,
            provider,
            benign_context,
            "swing",
            now=datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc),
        )

        assert opportunity.data_freshness is not None
        assert opportunity.data_freshness.calendar == "CRYPTO_24_7"
        assert opportunity.data_freshness.session_close_status == "sin sesión de cierre"
        assert opportunity.data_freshness.may_be_partial_current_session is True

    def test_cripto_no_declara_parcial_una_barra_ya_liquidada(self, config, benign_context) -> None:
        asset = _cripto()
        fechas = pd.date_range(end="2026-09-15", periods=300, freq="D", tz="UTC")
        history = make_ohlcv(n=len(fechas), start=50_000.0).set_axis(fechas)
        provider = FakeProvider({"BTC-EUR": history})

        opportunity = analyze_asset(
            asset,
            config,
            provider,
            benign_context,
            "swing",
            now=datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc),
        )

        assert opportunity.data_freshness is not None
        assert opportunity.data_freshness.may_be_partial_current_session is False


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


class TestBarraParcialYCalidad:
    """La calidad debe usar el cierre real de la plaza, no la fecha de la barra."""

    def _asset_jpx(self) -> Asset:
        return Asset(
            symbol="7203.T",
            name="Toyota",
            asset_class="stock",
            region="ASIA",
            market="JPX",
            currency="JPY",
            timezone="Asia/Tokyo",
            trade_republic="unknown",
        )

    def test_sesion_asiatica_ya_cerrada_no_es_barra_parcial(self, config, benign_context) -> None:
        """Tokio cierra a las 06:00 UTC: a las 11:00 su barra de hoy está cerrada.

        Antes, `DataQuality` se construía dentro de la frescura con el valor sin
        corregir y el analizador lo arreglaba después, así que los doce activos
        asiáticos del universo quedaban PARTIAL_BAR y vetados cada día por una
        sesión que llevaba horas cerrada.
        """

        asset = self._asset_jpx()
        sesiones = expected_sessions("JPX", date(2025, 1, 2), date(2026, 9, 16))
        fechas = pd.DatetimeIndex([pd.Timestamp(v, tz="Asia/Tokyo") for v in sesiones])
        history = make_ohlcv(n=len(fechas), start=3000.0).set_axis(fechas)
        provider = FakeProvider({"7203.T": history})

        opportunity = analyze_asset(
            asset,
            config,
            provider,
            benign_context,
            "swing",
            now=datetime(2026, 9, 16, 11, 0, tzinfo=timezone.utc),
        )

        freshness = opportunity.data_freshness
        assert freshness is not None
        assert freshness.last_bar_date == date(2026, 9, 16)
        assert freshness.session_close_status.startswith("última barra cerrada")
        assert freshness.may_be_partial_current_session is False
        assert opportunity.data_quality is not None
        assert opportunity.data_quality.freshness is FreshnessState.FRESH
        assert opportunity.data_quality.execution_readiness is True

    def test_sesion_cerrada_sigue_siendo_fresca_aunque_falte_un_indicador(self, config, benign_context) -> None:
        """La frescura se rehace cuando falta un indicador, y ahí se perdía el cierre.

        Con menos de 200 barras no hay `sma_long`, el analizador recalcula la
        frescura y esa segunda llamada se había quedado sin el dato del cierre
        de plaza: el activo volvía a registrarse como barra parcial y perdía
        `session_close_status`, aunque Tokio llevara horas cerrado.
        """

        asset = self._asset_jpx()
        sesiones = expected_sessions("JPX", date(2026, 2, 2), date(2026, 9, 16))
        fechas = pd.DatetimeIndex([pd.Timestamp(v, tz="Asia/Tokyo") for v in sesiones])
        history = make_ohlcv(n=len(fechas), start=3000.0).set_axis(fechas)
        provider = FakeProvider({"7203.T": history})

        opportunity = analyze_asset(
            asset,
            config,
            provider,
            benign_context,
            "swing",
            now=datetime(2026, 9, 16, 11, 0, tzinfo=timezone.utc),
        )

        assert opportunity.data_quality is not None
        assert opportunity.data_quality.indicators_missing == ("sma_long",)
        assert opportunity.data_freshness.session_close_status.startswith("última barra cerrada")
        assert opportunity.data_quality.freshness is FreshnessState.FRESH
        assert not any(reason.code == "PARTIAL_BAR" for reason in opportunity.data_quality.reasons)
