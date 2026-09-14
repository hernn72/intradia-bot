"""Formato del informe y conversión a euros."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from advisor.analysis.analyzer import AnalysisResult
from advisor.analysis.levels import Levels, compute_levels
from advisor.analysis.opportunity import build_opportunity
from advisor.analysis.overview import IndexQuote
from advisor.analysis.scoring import compute_score
from advisor.analysis.sizing import calculate_position_sizing
from advisor.config import AdvisorConfig, LevelsConfig, PortfolioConfig, RiskConfig, ScoringConfig
from advisor.data.freshness import DataFreshness
from advisor.data.fx import FxConverter
from advisor.events.models import (
    ALCANCE_ACTIVO,
    ALCANCE_GLOBAL,
    TIPO_BANCO_CENTRAL,
    TIPO_RESULTADOS,
    MarketEvent,
)
from advisor.report.formatter import format_opportunity, format_overview, format_report
from advisor.report.money import MoneyFormatter, format_eur
from tests.conftest import FakeProvider
from tests.test_analysis import make_snapshot

REPORT_REFERENCE = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def fx() -> FxConverter:
    """Conversor con EURUSD = 1,25, para que las cuentas salgan redondas."""
    return FxConverter(FakeProvider(closes={"EURUSD=X": 1.25}), "EUR")


@pytest.fixture
def fx_sin_datos() -> FxConverter:
    return FxConverter(FakeProvider(), "EUR")


def _opportunity(asset, context, horizonte: str = "swing", portfolio: PortfolioConfig | None = None, **snapshot_kwargs):
    portfolio = portfolio or PortfolioConfig()
    data_freshness = snapshot_kwargs.pop("data_freshness", None)
    snapshot = make_snapshot(**snapshot_kwargs)
    levels = compute_levels(snapshot, LevelsConfig(), RiskConfig().min_rr_ratio)
    score = compute_score(snapshot, levels, context, ScoringConfig(), 250)
    return build_opportunity(
        asset=asset, horizonte=horizonte, snapshot=snapshot, levels=levels,
        score=score, context=context, scoring=ScoringConfig(), risk=RiskConfig(), portfolio=portfolio,
        data_freshness=data_freshness,
    )


class TestFormatoDeImportes:
    def test_formato_espanol(self) -> None:
        assert format_eur(1234.5) == "1.234,50 €"
        assert format_eur(None) == "N/D"

    def test_activo_en_euros_no_se_convierte(self, fx: FxConverter) -> None:
        money = MoneyFormatter(fx, "EUR")
        assert money(240.5) == "240,50 €"
        assert money.needs_conversion is False

    def test_activo_en_dolares_muestra_nativo_y_aproximado(self, fx: FxConverter) -> None:
        money = MoneyFormatter(fx, "USD")
        resultado = money(100.0)
        assert "100,00 USD" in resultado
        assert "≈ 80,00 €" in resultado

    def test_sin_tipo_de_cambio_no_se_inventa_conversion(self, fx_sin_datos: FxConverter) -> None:
        money = MoneyFormatter(fx_sin_datos, "USD")
        resultado = money(100.0)
        assert "100,00 USD" in resultado
        assert "no disponible" in resultado
        assert "€" not in resultado

    def test_valor_en_euros_para_persistencia(self, fx: FxConverter) -> None:
        assert MoneyFormatter(fx, "USD").eur_value(100.0) == pytest.approx(80.0)
        assert MoneyFormatter(fx, "EUR").eur_value(100.0) == pytest.approx(100.0)
        assert MoneyFormatter(fx, "USD").eur_value(None) is None

    def test_valor_desde_euros_a_divisa_nativa(self, fx: FxConverter) -> None:
        assert fx.from_base(80.0, "USD") == pytest.approx(100.0)
        assert fx.from_base(100.0, "EUR") == pytest.approx(100.0)
        assert fx.from_base(None, "USD") is None

    def test_columna_compacta_prefiere_euros(self, fx: FxConverter) -> None:
        assert MoneyFormatter(fx, "USD").compact(100.0) == "80,00 €"

    def test_el_tipo_se_descarga_una_sola_vez(self) -> None:
        """Un informe debe usar un único tipo de cambio de principio a fin."""
        provider = FakeProvider(closes={"EURUSD=X": 1.25})
        fx = FxConverter(provider, "EUR")
        money = MoneyFormatter(fx, "USD")

        money(1.0)
        money(2.0)
        money(3.0)

        assert provider.calls.count("EURUSD=X") == 1
        assert fx.rate("USD") == pytest.approx(0.8)


class TestFormatOverview:
    def test_agrupa_por_region(self) -> None:
        quotes = [
            IndexQuote("^N225", "Nikkei 225", "ASIA", "JPY", 39000.0, 0.8),
            IndexQuote("^GDAXI", "DAX", "EUROPA", "EUR", 18000.0, -0.4),
        ]
        salida = format_overview(quotes)
        assert "Asia:" in salida and "Europa:" in salida
        assert salida.index("Asia:") < salida.index("Europa:")

    def test_indice_sin_datos_se_declara(self) -> None:
        quotes = [IndexQuote("^HSI", "Hang Seng", "ASIA", "HKD", None, None, "sin datos")]
        assert "no disponibles" in format_overview(quotes)

    def test_sin_indices_configurados(self) -> None:
        assert "Sin índices" in format_overview([])


class TestFormatOpportunity:
    def test_ficha_incluye_los_campos_obligatorios(self, asset_eur, benign_context, fx: FxConverter) -> None:
        ficha = format_opportunity(_opportunity(asset_eur, benign_context), fx, REPORT_REFERENCE)

        for campo in [
            "**Ticker:**", "**ISIN:**", "**Mercado de datos:**", "**Divisa de cotización:**",
            "**Exposición económica:**", "**Broker / ejecución:**", "**Disponible en Trade Republic:**",
            "**Precio actual:**", "**Tipo de operación:**", "**Señal:**", "**Ejecutabilidad en broker:**",
            "**Puntuación:**",
            "### Tesis", "### Catalizador", "### Entrada", "### Stop / invalidación",
            "### Objetivos", "### Potencial", "### Riesgo", "### Ratio beneficio/riesgo",
            "### Horizonte temporal", "### Confianza", "### Qué podría salir mal", "### Acción",
        ]:
            assert campo in ficha, f"falta {campo}"

    def test_precios_de_un_activo_en_euros_llevan_simbolo(self, asset_eur, benign_context, fx: FxConverter) -> None:
        ficha = format_opportunity(_opportunity(asset_eur, benign_context), fx, REPORT_REFERENCE)
        assert "€" in ficha

    def test_precios_en_dolares_muestran_equivalente_en_euros(self, asset_usd, benign_context, fx: FxConverter) -> None:
        ficha = format_opportunity(_opportunity(asset_usd, benign_context), fx, REPORT_REFERENCE)
        assert "USD" in ficha
        assert "≈" in ficha and "€" in ficha

    def test_isin_ausente_se_marca(self, asset_eur, benign_context, fx: FxConverter) -> None:
        ficha = format_opportunity(_opportunity(asset_eur, benign_context), fx, REPORT_REFERENCE)
        assert "NO REGISTRADO" in ficha

    def test_disponibilidad_unknown_separa_senal_y_ejecutabilidad(self, asset_usd, benign_context, fx: FxConverter) -> None:
        ficha = format_opportunity(_opportunity(asset_usd, benign_context), fx, REPORT_REFERENCE)

        assert "**Señal:** 🟢 OPERAR" in ficha
        assert "**Ejecutabilidad en broker:** ❓ pendiente de verificación" in ficha
        assert "### Acción\n**COMPRAR**" in ficha
        assert "**Disponibilidad:** ❓ pendiente de verificación" in ficha

    def test_declara_frescura_y_avisa_si_la_barra_es_vieja(
        self,
        asset_eur,
        benign_context,
        fx: FxConverter,
    ) -> None:
        opportunity = _opportunity(asset_eur, benign_context, timestamp=pd.Timestamp("2026-08-26", tz="UTC"))

        ficha = format_opportunity(
            opportunity,
            fx,
            REPORT_REFERENCE,
        )

        assert "**Datos de mercado:** DEGRADADO; última barra 2026-08-26" in ficha
        assert "hace 4 días naturales; 2 sesiones" in ficha
        assert "Dato retrasado" in ficha

    def test_avisa_con_una_sesion_cerrada_perdida(
        self,
        asset_eur,
        benign_context,
        fx: FxConverter,
    ) -> None:
        opportunity = _opportunity(asset_eur, benign_context, timestamp=pd.Timestamp("2026-08-27", tz="UTC"))

        ficha = format_opportunity(
            opportunity,
            fx,
            REPORT_REFERENCE,
        )

        assert "1 sesión" in ficha
        assert "Dato retrasado" in ficha

    def test_isin_no_aplicable_no_se_marca_como_pendiente(self, benign_context, fx: FxConverter) -> None:
        from advisor.universe.models import Asset

        asset = Asset(
            symbol="BTC-EUR",
            name="Bitcoin",
            asset_class="crypto",
            region="GLOBAL",
            market="CRYPTO",
            currency="EUR",
            economic_currency="BTC",
            timezone="UTC",
        )
        ficha = format_opportunity(_opportunity(asset, benign_context), fx, REPORT_REFERENCE)

        assert "**ISIN:** No aplica" in ficha
        assert "NO REGISTRADO" not in ficha

    def test_disponibilidad_sin_verificar_sale_advertida(self, asset_usd, benign_context, fx: FxConverter) -> None:
        ficha = format_opportunity(_opportunity(asset_usd, benign_context), fx, REPORT_REFERENCE)
        assert "PENDIENTE DE VERIFICACIÓN" in ficha

    def test_dimension_excluida_aparece_en_el_desglose(self, asset_eur, benign_context, fx: FxConverter) -> None:
        ficha = format_opportunity(_opportunity(asset_eur, benign_context), fx, REPORT_REFERENCE)
        assert "fundamental: excluida" in ficha
        assert "puntos evaluables" in ficha

    def test_sin_ia_no_se_inventan_probabilidades(self, asset_eur, benign_context, fx: FxConverter) -> None:
        ficha = format_opportunity(_opportunity(asset_eur, benign_context), fx, REPORT_REFERENCE)
        assert "no estima probabilidades" in ficha

    def test_tipo_de_operacion_sigue_al_horizonte(self, asset_eur, benign_context, fx: FxConverter) -> None:
        assert "Intradía" in format_opportunity(_opportunity(asset_eur, benign_context, "intradia"), fx, REPORT_REFERENCE)
        assert "Medio plazo" in format_opportunity(_opportunity(asset_eur, benign_context, "medio"), fx, REPORT_REFERENCE)

    def test_dimensionamiento_eur_y_usd_equivale_tras_convertir(self, asset_eur, asset_usd, benign_context) -> None:
        portfolio = PortfolioConfig(capital=100_000.0, risk_per_trade_pct=0.5, max_position_pct=10.0)
        fx = FxConverter(FakeProvider(closes={"EURUSD=X": 1.25}), "EUR")

        ficha_eur = format_opportunity(
            _opportunity(asset_eur, benign_context, portfolio=portfolio),
            fx,
            REPORT_REFERENCE,
            portfolio=portfolio,
        )
        ficha_usd = format_opportunity(
            _opportunity(asset_usd, benign_context, portfolio=portfolio),
            fx,
            REPORT_REFERENCE,
            portfolio=portfolio,
        )

        assert "100 acciones; posición 10.000,00 €" in ficha_eur
        assert "125 acciones; posición 12.500,00 USD (≈ 10.000,00 €)" in ficha_usd

    @pytest.mark.parametrize(
        ("capital", "expected_shares", "expected_position"),
        [
            (10_000.0, 10, "1.000,00 €"),
            (50_000.0, 50, "5.000,00 €"),
            (100_000.0, 100, "10.000,00 €"),
        ],
    )
    def test_dimensionamiento_con_capital_sintetico_y_activo_en_euros(
        self,
        asset_eur,
        benign_context,
        fx: FxConverter,
        capital: float,
        expected_shares: int,
        expected_position: str,
    ) -> None:
        portfolio = PortfolioConfig(capital=capital, risk_per_trade_pct=0.5, max_position_pct=10.0)

        ficha = format_opportunity(
            _opportunity(asset_eur, benign_context, portfolio=portfolio),
            fx,
            REPORT_REFERENCE,
            portfolio=portfolio,
        )

        assert f"{expected_shares} acciones; posición {expected_position}" in ficha

    @pytest.mark.parametrize(
        ("capital", "expected_shares", "expected_native"),
        [
            (10_000.0, 12, "1.200,00 USD"),
            (50_000.0, 62, "6.200,00 USD"),
            (100_000.0, 125, "12.500,00 USD"),
        ],
    )
    def test_dimensionamiento_con_capital_sintetico_y_divisa_no_euro(
        self,
        asset_usd,
        benign_context,
        capital: float,
        expected_shares: int,
        expected_native: str,
    ) -> None:
        portfolio = PortfolioConfig(capital=capital, risk_per_trade_pct=0.5, max_position_pct=10.0)
        fx = FxConverter(FakeProvider(closes={"EURUSD=X": 1.25}), "EUR")

        ficha = format_opportunity(
            _opportunity(asset_usd, benign_context, portfolio=portfolio),
            fx,
            REPORT_REFERENCE,
            portfolio=portfolio,
        )

        assert f"{expected_shares} acciones; posición {expected_native}" in ficha
        assert "tope máximo por posición (10%)" in ficha

    def test_dimensionamiento_redondea_acciones_hacia_abajo(self, asset_usd, benign_context) -> None:
        portfolio = PortfolioConfig(capital=10_400.0, risk_per_trade_pct=0.5, max_position_pct=10.0)
        fx = FxConverter(FakeProvider(closes={"EURUSD=X": 1.25}), "EUR")

        ficha = format_opportunity(
            _opportunity(asset_usd, benign_context, portfolio=portfolio),
            fx,
            REPORT_REFERENCE,
            portfolio=portfolio,
        )

        assert "13 acciones; posición 1.300,00 USD" in ficha
        assert "14 acciones" not in ficha

    def test_dimensionamiento_jpy_convierte_capital_a_yenes(self, benign_context) -> None:
        from advisor.universe.models import Asset

        asset = Asset(
            symbol="7203.T",
            name="Toyota",
            asset_class="stock",
            region="ASIA",
            market="JPX",
            currency="JPY",
            timezone="Asia/Tokyo",
        )
        capital = 100_000.0
        max_position_pct = 10.0
        precio_jpy = 3054.0
        eurjpy = 173.0
        expected_shares = int((capital * max_position_pct / 100 * eurjpy) // precio_jpy)
        expected_position_jpy = expected_shares * precio_jpy
        assert expected_shares == 566
        portfolio = PortfolioConfig(capital=capital, risk_per_trade_pct=0.5, max_position_pct=max_position_pct)
        fx = FxConverter(FakeProvider(closes={"EURJPY=X": eurjpy}), "EUR")
        opportunity = _opportunity(
            asset,
            benign_context,
            portfolio=portfolio,
            price=precio_jpy,
            atr=76.35,
            ema_fast=3015.825,
            ema_slow=2900.0,
            sma_long=2750.0,
            low_lookback=1.0,
            high_lookback=3084.54,
        )

        ficha = format_opportunity(opportunity, fx, REPORT_REFERENCE, portfolio=portfolio)

        assert f"{expected_shares} acciones; posición {expected_position_jpy:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") in ficha
        assert "3 acciones" not in ficha

    def test_dimensionamiento_sin_tipo_de_cambio_no_inventa_acciones(self, benign_context) -> None:
        from advisor.universe.models import Asset

        asset = Asset(
            symbol="005930.KS",
            name="Samsung",
            asset_class="stock",
            region="ASIA",
            market="KSC",
            currency="KRW",
            timezone="Asia/Seoul",
        )
        portfolio = PortfolioConfig(capital=100_000.0, risk_per_trade_pct=0.5, max_position_pct=10.0)
        ficha = format_opportunity(
            _opportunity(asset, benign_context, portfolio=portfolio),
            FxConverter(FakeProvider(), "EUR"),
            REPORT_REFERENCE,
            portfolio=portfolio,
        )

        assert "no hay tipo de cambio para KRW" in ficha
        assert "no se calcula un número de acciones" in ficha
        assert "acciones; posición" not in ficha

    def test_capital_que_no_alcanza_para_una_accion_se_declara(self, asset_eur, benign_context, fx: FxConverter) -> None:
        portfolio = PortfolioConfig(capital=50.0, risk_per_trade_pct=0.5, max_position_pct=10.0)
        ficha = format_opportunity(
            _opportunity(asset_eur, benign_context, portfolio=portfolio),
            fx,
            REPORT_REFERENCE,
            portfolio=portfolio,
        )

        assert "no alcanza para comprar una acción" in ficha

    def test_stop_invalido_deja_el_dimensionamiento_a_cero(self) -> None:
        levels = Levels(
            price=100.0,
            entry_ideal_low=100.0,
            entry_ideal_high=100.0,
            entry_max=100.0,
            stop=100.0,
            invalidation_level=None,
            invalidation_reason="test",
            stop_basis="test",
            target1=103.0,
            target2=106.0,
            target3=110.0,
            risk_pp=0.0,
            reward_pct=6.0,
            rr_ratio=0.0,
            extension_atr=None,
            chase=False,
        )

        sizing = calculate_position_sizing(levels, PortfolioConfig(capital=100_000.0), "test")

        assert sizing.position_pct == 0.0
        assert sizing.risk_pct == 0.0
        assert sizing.capped_by == "riesgo no calculable"


class TestFormatReport:
    def _result(self, opportunities, context) -> AnalysisResult:
        return AnalysisResult(
            generated_at=datetime(2026, 8, 27, 9, 30, tzinfo=timezone.utc),
            horizonte="swing",
            interval="1d",
            context=context,
            opportunities=opportunities,
            overview=[IndexQuote("^GDAXI", "DAX", "EUROPA", "EUR", 18000.0, 0.5)],
        )

    def test_informe_completo(self, asset_eur, benign_context, fx: FxConverter) -> None:
        config = AdvisorConfig(horizontes={"swing": {"interval": "1d", "period": "1y", "min_bars": 120}})
        informe = format_report(self._result([_opportunity(asset_eur, benign_context)], benign_context), config, fx)

        for seccion in ["🌍 SITUACIÓN GLOBAL", "🔥 OPORTUNIDADES DETECTADAS", "👀 RADAR", "🎯 CONCLUSIÓN"]:
            assert seccion in informe
        assert "no es asesoramiento financiero" in informe.lower()

    def test_sin_oportunidades_recomienda_liquidez(self, benign_context, fx: FxConverter) -> None:
        config = AdvisorConfig(horizontes={"swing": {"interval": "1d", "period": "1y", "min_bars": 120}})
        informe = format_report(self._result([], benign_context), config, fx)
        assert "NO OPERAR / MANTENER LIQUIDEZ" in informe

    def test_informe_declara_frescura_sin_operar(
        self,
        asset_eur,
        asset_usd,
        benign_context,
        hostile_context,
        fx: FxConverter,
    ) -> None:
        config = AdvisorConfig(horizontes={"swing": {"interval": "1d", "period": "1y", "min_bars": 120}})
        no_disponible = asset_usd.model_copy(update={"trade_republic": "no"})
        radar_viejo = _opportunity(
            asset_eur,
            hostile_context,
            timestamp=pd.Timestamp("2026-08-25", tz="UTC"),
        )
        descartado_al_dia = _opportunity(
            no_disponible,
            benign_context,
            timestamp=pd.Timestamp("2026-08-27", tz="UTC"),
        )

        informe = format_report(
            self._result([radar_viejo, descartado_al_dia], hostile_context),
            config,
            fx,
        )

        assert "Ninguna oportunidad cumple hoy los criterios de entrada." in informe
        assert "**Frescura de datos:** 2 activos analizados con snapshot." in informe
        assert "0 sesiones cerradas perdidas: 1 activo; última barra 2026-08-27 (NASDAQ)." in informe
        assert "⚠️ 1 sesión cerrada perdida: 1 activo; última barra 2026-08-25 (XETRA)." in informe
        assert "SAP.DE (SAP) — score" in informe
        assert "⚠️ dato 2026-08-25 (1s)" in informe
        assert "AAPL (Apple) — score" in informe
        assert "no disponible en Trade Republic" in informe
        assert "## SAP" not in informe

    def test_informe_declara_sesion_ausente_intermedia_y_marca_compacta(
        self,
        asset_eur,
        hostile_context,
        fx: FxConverter,
    ) -> None:
        config = AdvisorConfig(horizontes={"swing": {"interval": "1d", "period": "1y", "min_bars": 120}})
        freshness = DataFreshness(
            last_bar_date=date(2026, 8, 31),
            natural_days=0,
            sessions_approx=0,
            label="hoy; al día",
            may_be_partial_current_session=True,
            calendar="XETR",
            strength_benchmark="^STOXX50E",
            absent_reference_sessions=(date(2026, 8, 28),),
            reference_sessions_checked=3,
        )
        opportunity = _opportunity(
            asset_eur,
            hostile_context,
            timestamp=pd.Timestamp("2026-08-31", tz="UTC"),
            data_freshness=freshness,
        )

        informe = format_report(self._result([opportunity], hostile_context), config, fx)

        assert "0 sesiones cerradas perdidas: 1 activo; última barra 2026-08-31 (XETRA)." in informe
        assert "Sesiones ausentes frente al calendario de su plaza: 1 activo." in informe
        assert "SAP.DE: faltan 2026-08-28 en XETR." in informe
        assert "⚠️ Barra potencialmente parcial: última barra fechada hoy, puede no ser cierre de sesión." in informe
        assert "  - SAP.DE" in informe
        assert "⚠️ falta sesión 2026-08-28" in informe

    def test_conclusion_dimensiona_ideas_aunque_todas_tengan_disponibilidad_unknown(
        self,
        asset_eur,
        asset_usd,
        benign_context,
        fx: FxConverter,
    ) -> None:
        """El caso real actual no debe degradar la señal por falta de catálogo del broker."""

        config = AdvisorConfig(horizontes={"swing": {"interval": "1d", "period": "1y", "min_bars": 120}})
        unknown_eur = asset_eur.model_copy(update={"trade_republic": "unknown"})
        unknown_usd = asset_usd.model_copy(update={"trade_republic": "unknown"})

        informe = format_report(
            self._result(
                [_opportunity(unknown_eur, benign_context), _opportunity(unknown_usd, benign_context)],
                benign_context,
            ),
            config,
            fx,
        )

        assert "suma de las 0 mejores ideas" not in informe
        assert "suma de las 2 mejores ideas por señal" in informe
        assert "La disponibilidad del broker se informa aparte" in informe

    def test_nota_del_tipo_de_cambio_solo_si_se_usa(self, asset_eur, asset_usd, benign_context, fx: FxConverter) -> None:
        config = AdvisorConfig(horizontes={"swing": {"interval": "1d", "period": "1y", "min_bars": 120}})

        solo_eur = format_report(self._result([_opportunity(asset_eur, benign_context)], benign_context), config, fx)
        assert "Conversión a euros aproximada" not in solo_eur

        con_usd = format_report(self._result([_opportunity(asset_usd, benign_context)], benign_context), config, fx)
        assert "Conversión a euros aproximada" in con_usd

    def test_activos_no_analizados_se_declaran(self, benign_context, fx: FxConverter) -> None:
        config = AdvisorConfig(horizontes={"swing": {"interval": "1d", "period": "1y", "min_bars": 120}})
        result = AnalysisResult(
            generated_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
            horizonte="swing", interval="1d", context=benign_context,
            skipped=[("XYZ.DE", "histórico insuficiente: 30 velas")],
        )
        informe = format_report(result, config, fx)
        assert "XYZ.DE" in informe and "histórico insuficiente" in informe


class TestEventosEnLaFicha:
    """El §23 pide 'Próximo evento importante', y unos resultados inminentes
    son un riesgo con fecha, no una opinión de la IA."""

    def _evento(self, dias: int, tipo: str = TIPO_RESULTADOS, titulo: str = "Publicación de resultados"):
        base = make_snapshot().timestamp.date()
        return MarketEvent(
            fecha=base + timedelta(days=dias),
            tipo=tipo,
            alcance=ALCANCE_ACTIVO if tipo == TIPO_RESULTADOS else ALCANCE_GLOBAL,
            titulo=titulo,
            fuente="fuente de prueba",
            confirmada=tipo != TIPO_RESULTADOS,
        )

    def test_sin_calendario_lo_dice_en_vez_de_callar(self, asset_eur, benign_context, fx: FxConverter) -> None:
        ficha = format_opportunity(_opportunity(asset_eur, benign_context), fx, REPORT_REFERENCE)
        assert "### Próximo evento importante" in ficha
        assert "Ninguno con fecha conocida" in ficha

    def test_lista_el_evento_con_su_fuente(self, asset_eur, benign_context, fx: FxConverter) -> None:
        ficha = format_opportunity(
            _opportunity(asset_eur, benign_context), fx, REPORT_REFERENCE, [self._evento(20)]
        )
        assert "en 20 días" in ficha
        assert "fuente de prueba" in ficha

    def test_resultados_inminentes_son_un_riesgo(self, asset_eur, benign_context, fx: FxConverter) -> None:
        ficha = format_opportunity(_opportunity(asset_eur, benign_context), fx, REPORT_REFERENCE, [self._evento(3)])
        assert "apuesta binaria" not in ficha  # el texto no promete, describe
        assert "Publica resultados dentro de 3 días" in ficha

    def test_resultados_lejanos_no_generan_riesgo(self, asset_eur, benign_context, fx: FxConverter) -> None:
        ficha = format_opportunity(_opportunity(asset_eur, benign_context), fx, REPORT_REFERENCE, [self._evento(25)])
        assert "Publica resultados" not in ficha.split("### Qué podría salir mal")[1]

    def test_banco_central_inminente_avisa(self, asset_eur, benign_context, fx: FxConverter) -> None:
        evento = self._evento(2, TIPO_BANCO_CENTRAL, "Decisión de tipos de la Fed")
        ficha = format_opportunity(_opportunity(asset_eur, benign_context), fx, REPORT_REFERENCE, [evento])
        assert "mueve todo el mercado" in ficha
