"""Frescura de datos de mercado."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from advisor.analysis.analyzer import indicator_reference_sessions
from advisor.config import AdvisorConfig
from advisor.data.calendars import expected_sessions
from advisor.data.freshness import (
    MERCADO_DESCONOCIDO,
    QUALITY_DEGRADED,
    QUALITY_INCOMPLETE,
    QUALITY_OK,
    agrupar_frescura_por_fecha,
    calcular_frescura_dato,
    calcular_frescura_serie,
)
from advisor.main import format_frescura_datos, format_frescura_historico, medir_frescura_datos
from advisor.universe.loader import load_universe
from advisor.universe.models import Asset
from tests.conftest import FakeProvider, make_ohlcv


def _asset(symbol: str, market: str, region: str = "EUROPA") -> Asset:
    return Asset(
        symbol=symbol,
        name=symbol,
        asset_class="stock",
        region=region,
        market=market,
        currency="EUR",
        timezone="Europe/Berlin",
        trade_republic="yes",
    )


def _config() -> AdvisorConfig:
    return AdvisorConfig(horizontes={"swing": {"interval": "1d", "period": "1y", "min_bars": 120}})


class TestCalcularFrescuraDato:
    def test_mismo_dia(self) -> None:
        freshness = calcular_frescura_dato(
            pd.Timestamp("2026-08-28T18:00:00Z"),
            datetime(2026, 8, 28, 20, 0, tzinfo=timezone.utc),
            market="XETRA",
        )

        assert freshness.last_bar_date.isoformat() == "2026-08-28"
        assert freshness.natural_days == 0
        assert freshness.sessions_approx == 0
        assert "al día" in freshness.label

    def test_fin_de_semana_no_suma_sesiones(self) -> None:
        freshness = calcular_frescura_dato(
            pd.Timestamp("2026-08-28", tz="UTC"),
            datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc),
            market="XETRA",
        )

        assert freshness.natural_days == 2
        assert freshness.sessions_approx == 0

    def test_sesion_en_curso_no_cuenta_como_perdida(self) -> None:
        freshness = calcular_frescura_dato(
            pd.Timestamp("2026-08-28", tz="UTC"),
            datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc),
            market="XETRA",
        )

        assert freshness.natural_days == 3
        assert freshness.sessions_approx == 0

    def test_salto_de_dos_sesiones_sin_festivos(self) -> None:
        freshness = calcular_frescura_dato(
            pd.Timestamp("2026-08-26", tz="UTC"),
            datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc),
            market="XETRA",
        )

        assert freshness.natural_days == 4
        assert freshness.sessions_approx == 2
        assert "2 sesiones" in freshness.label


class TestMedirFrescuraDatos:
    def test_agrupa_por_fecha_y_plaza_con_proveedor_inyectado(self) -> None:
        assets = [
            _asset("SAP.DE", "XETRA"),
            _asset("ASML.AS", "AMS"),
            _asset("AAPL", "NASDAQ", "USA"),
        ]
        provider = FakeProvider(
            histories={
                "SAP.DE": make_ohlcv(n=3, start_date="2026-08-24"),
                "ASML.AS": make_ohlcv(n=3, start_date="2026-08-24"),
                "AAPL": make_ohlcv(n=5, start_date="2026-08-24"),
            }
        )

        rows = medir_frescura_datos(
            assets,
            provider,
            _config(),
            datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc),
            period="1mo",
            interval="1d",
        )
        buckets = agrupar_frescura_por_fecha(rows)

        assert provider.calls == ["SAP.DE", "ASML.AS", "AAPL"]
        assert [(bucket.last_bar_date.isoformat(), bucket.symbols_count) for bucket in buckets] == [
            ("2026-08-28", 1),
            ("2026-08-26", 2),
        ]
        viejo = buckets[1]
        assert viejo.freshness.sessions_approx == 2
        assert viejo.markets_label == "AMS, XETRA"

    def test_no_publica_calidad_de_ejecucion_porque_mide_el_dato_crudo(self) -> None:
        """Los dos caminos respondían distinto sobre el mismo activo e instante.

        `analizar` recorta la barra no cerrada antes de juzgar la calidad y
        este comando no la recorta, a propósito: existe para ver lo que sirve
        el proveedor. Publicar aquí un `DataQuality` afirmaba un veredicto de
        ejecución que esta medición no puede sostener, y para un activo con la
        sesión ya cerrada decía PARTIAL_BAR / no ejecutable donde el asesor
        decía FRESH / ejecutable.
        """

        asset = _asset("7203.T", "JPX", region="ASIA")
        provider = FakeProvider(histories={"7203.T": make_ohlcv(n=30, start_date="2026-08-03")})
        # Tokio cierra a las 15:30 locales, o sea 06:30 UTC: a las 11:00 UTC la
        # última barra es de una sesión ya cerrada, no una barra parcial.
        reference = datetime(2026, 9, 1, 11, 0, tzinfo=timezone.utc)

        rows = medir_frescura_datos([asset], provider, _config(), reference)

        assert len(rows) == 1
        freshness = rows[0].freshness
        assert freshness is not None
        # La medición cruda sigue entera: fecha, antigüedad y ausencias.
        assert freshness.last_bar_date.isoformat() == "2026-09-01"
        # El veredicto de ejecución, no: se declara ausente en vez de fingirlo.
        assert freshness.data_quality is None

    def test_usa_las_ventanas_de_configuracion_y_no_los_valores_por_defecto(self) -> None:
        """Ignoraba `veto_window_sessions` y la ventana de indicadores, así que
        medía con 10/10 mientras producción usaba 20 y la ventana larga."""

        asset = _asset("SAP.DE", "XETRA")
        provider = FakeProvider(histories={"SAP.DE": make_ohlcv(n=30, start_date="2026-08-03")})
        config = _config()
        reference = datetime(2026, 9, 11, 11, 0, tzinfo=timezone.utc)

        freshness = medir_frescura_datos([asset], provider, config, reference)[0].freshness

        assert freshness is not None
        assert freshness.veto_window_sessions == config.data_quality.veto_window_sessions == 20
        # La ventana larga se acota al histórico disponible (30 barras), pero
        # ya no es el 10 por defecto que este camino usaba sin querer.
        assert 10 < freshness.reference_sessions_checked <= indicator_reference_sessions(config)

    def test_salida_declara_hora_de_medicion_y_dispersion_por_plaza(self) -> None:
        assets = [
            _asset("AAA.DE", "XETRA"),
            _asset("BBB.DE", "XETRA"),
            _asset("CCC.DE", "XETRA"),
            _asset("DDD.PA", "PAR"),
        ]
        provider = FakeProvider(
            histories={
                "AAA.DE": make_ohlcv(n=1, start_date="2026-08-28"),
                "BBB.DE": make_ohlcv(n=1, start_date="2026-08-28"),
                "CCC.DE": make_ohlcv(n=1, start_date="2026-08-27"),
                "DDD.PA": make_ohlcv(n=1, start_date="2026-08-27"),
            }
        )
        reference = datetime(2026, 8, 30, 17, 20, tzinfo=timezone.utc)

        rows = medir_frescura_datos(assets, provider, _config(), reference)
        salida = format_frescura_datos(rows, reference)

        assert "Medición: 2026-08-30 17:20:00 UTC" in salida
        assert "Dispersión por plaza:" in salida
        assert "| XETRA | vie 28 | 1 / 3 |" in salida
        assert "| PAR | jue 27 | 0 / 1 |" in salida

    def test_detecta_sesion_ausente_intermedia_jueves_lunes_frente_a_calendario(self) -> None:
        activo = make_ohlcv(n=3, start_date="2026-08-26").drop(pd.Timestamp("2026-08-28", tz="UTC"))
        activo.loc[pd.Timestamp("2026-08-31", tz="UTC")] = activo.iloc[-1]
        activo = activo.sort_index()

        freshness = calcular_frescura_serie(
            activo,
            datetime(2026, 8, 31, 7, 30, tzinfo=timezone.utc),
            market="XETRA",
            strength_benchmark="^STOXX50E",
        )

        assert freshness.sessions_approx == 0
        assert freshness.last_bar_date.isoformat() == "2026-08-31"
        assert [value.isoformat() for value in freshness.absent_reference_sessions] == ["2026-08-28"]
        assert freshness.may_be_partial_current_session is True

    def test_frescura_datos_declara_sesiones_ausentes_y_referencia(self) -> None:
        activo = make_ohlcv(n=3, start_date="2026-08-26").drop(pd.Timestamp("2026-08-28", tz="UTC"))
        activo.loc[pd.Timestamp("2026-08-31", tz="UTC")] = activo.iloc[-1]
        provider = FakeProvider(histories={"SAP.DE": activo.sort_index()})
        reference = datetime(2026, 8, 31, 7, 30, tzinfo=timezone.utc)

        rows = medir_frescura_datos([_asset("SAP.DE", "XETRA")], provider, _config(), reference)
        salida = format_frescura_datos(rows, reference)

        assert "| Símbolo | Símbolo datos | Plaza | Última barra | Antigüedad | Calendario | Sesiones ausentes |" in salida
        assert "| SAP.DE | SAP.DE | XETRA | 2026-08-31 | hoy; al día; barra de hoy posiblemente parcial | XETR | 2026-08-28 |" in salida

    def test_calidad_incompleto_degradado_ok(self) -> None:
        reference = datetime(2026, 9, 1, 7, 0, tzinfo=timezone.utc)
        activo_incompleto = make_ohlcv(n=4, start_date="2026-08-26").drop(pd.Timestamp("2026-08-28", tz="UTC"))
        activo_incompleto.loc[pd.Timestamp("2026-08-31", tz="UTC")] = activo_incompleto.iloc[-1]

        incompleto = calcular_frescura_serie(
            activo_incompleto.sort_index(),
            reference,
            market="XETRA",
            strength_benchmark="^STOXX",
        )
        degradado = calcular_frescura_serie(make_ohlcv(n=2, start_date="2026-08-26"), reference, market="XETRA")
        ok_history = make_ohlcv(n=4, start_date="2026-08-26")
        ok_history.loc[pd.Timestamp("2026-08-31", tz="UTC")] = ok_history.iloc[-1]
        ok = calcular_frescura_serie(ok_history.sort_index(), reference, market="XETRA", strength_benchmark="^STOXX")

        assert incompleto.quality == QUALITY_INCOMPLETE
        assert "INCOMPLETO" in incompleto.quality_reasons[0]
        assert degradado.quality == QUALITY_DEGRADED
        assert ok.quality == QUALITY_OK

    def test_formatea_historico_persistido(self, tmp_path) -> None:
        from advisor.storage.db import AdvisorDB

        db = AdvisorDB(tmp_path / "freshness.db")
        db.insert_freshness_measurements([
            {
                "measured_at": "2026-09-02T08:30:00+00:00",
                "symbol": "SAP.DE",
                "data_symbol": "SAP.DE",
                "market": "XETRA",
                "calendar": "XETR",
                "benchmark_symbol": "^STOXX",
                "last_bar_date": "2026-08-31",
                "natural_days": 0,
                "sessions_approx": 0,
                "may_be_partial_current_session": True,
                "absent_reference_sessions": ["2026-08-28"],
                "absent_recent_sessions": ["2026-08-28"],
                "reference_sessions_checked": 10,
                "veto_window_sessions": 20,
                "quality": "INCOMPLETO",
                "error": None,
                "run_id": "test-run",
            }
        ])

        salida = format_frescura_historico(db.get_recent_freshness_measurements())

        assert "| 2026-09-02T08:30:00+00:00 | SAP.DE | SAP.DE | XETRA | 2026-08-31 | al día | XETR | sí | 2026-08-28 |  |" in salida

    def test_hueco_viejo_declara_pero_no_veta(self) -> None:
        """Un hueco fuera de la ventana de veto se declara, no bloquea abrir.

        Medido el 2026-09-02 sobre el universo real: con la ventana larga,
        AZN, TSM y NOVO-B.CO quedaban vetados por sesiones que les faltaban
        hace meses, y ese veto no habría caducado nunca.
        """

        reference = datetime(2026, 9, 1, 7, 0, tzinfo=timezone.utc)
        sessions = expected_sessions("XETRA", date(2026, 1, 2), date(2026, 8, 31))
        benchmark = make_ohlcv(n=len(sessions), start_date="2026-01-02")
        benchmark.index = pd.DatetimeIndex([pd.Timestamp(value, tz="UTC") for value in sessions])
        hueco = pd.Timestamp("2026-02-10", tz="UTC")
        activo = benchmark.drop(hueco)

        viejo = calcular_frescura_serie(
            activo,
            reference,
            market="XETRA",
            strength_benchmark="^STOXX",
            recent_reference_sessions=200,
            veto_window_sessions=5,
        )
        reciente = calcular_frescura_serie(
            activo,
            reference,
            market="XETRA",
            strength_benchmark="^STOXX",
            recent_reference_sessions=200,
            veto_window_sessions=200,
        )

        assert viejo.absent_reference_sessions == (hueco.date(),)
        assert viejo.absent_recent_sessions == ()
        assert viejo.quality == QUALITY_DEGRADED
        assert viejo.data_quality is not None
        assert viejo.data_quality.execution_readiness is True
        assert reciente.quality == QUALITY_DEGRADED
        assert reciente.data_quality is not None
        assert reciente.data_quality.execution_readiness is True


class TestPersistenciaEnLaPasadaReal:
    """La IA activada no puede vaciar el histórico de frescura.

    `cmd_analizar` reconstruía el `AnalysisResult` campo a campo tras redactar
    con la IA y se dejaba `freshness_rows` fuera. Los tests pasaban, pero en la
    Pi —que corre con la IA activada— no se guardaba ni una medición.
    """

    def test_guarda_frescura_con_la_ia_activada(self, tmp_path, monkeypatch) -> None:
        import argparse
        from datetime import datetime
        from datetime import timezone as tz

        import advisor.ai.narrator as narrator
        import advisor.main as main
        from advisor.analysis.analyzer import AnalysisResult
        from advisor.analysis.execution import ExecutionEvaluation
        from advisor.analysis.levels import Levels
        from advisor.analysis.market_context import MarketContext
        from advisor.analysis.opportunity import Opportunity
        from advisor.analysis.scoring import Component, Dimension, Score
        from advisor.analysis.sizing import PositionSizing
        from advisor.analysis.snapshot import TechnicalSnapshot
        from advisor.config import load_config
        from advisor.data.freshness import FreshnessRow, calcular_frescura_dato
        from advisor.storage.db import AdvisorDB
        from advisor.universe.loader import load_universe
        from advisor.universe.models import Asset

        reference = datetime(2026, 9, 2, 10, 0, tzinfo=tz.utc)
        asset = Asset(
            symbol="SAP.DE",
            name="SAP",
            asset_class="stock",
            region="EUROPA",
            market="XETRA",
            currency="EUR",
            economic_currency="EUR",
            timezone="Europe/Berlin",
            primary_symbol="SAP.DE",
            primary_market="XETRA",
            primary_currency="EUR",
            isin=None,
            trade_republic="unknown",
        )
        levels = Levels(
            price=240.0,
            entry_ideal_low=238.0,
            entry_ideal_high=240.0,
            entry_max=243.0,
            stop=232.0,
            invalidation_level=None,
            invalidation_reason="",
            stop_basis="2 ATR",
            target1=246.0,
            target2=252.0,
            target3=260.0,
            risk_pp=3.3,
            reward_pct=5.0,
            rr_ratio=1.5,
            extension_atr=None,
            chase=False,
        )
        score = Score([Dimension("tecnico", 100.0, [Component("manual", 78.0, 100.0)])])
        sizing = PositionSizing("Convicción media", 0.5, 10.0, 15.0)
        opportunity = Opportunity(
            asset=asset,
            horizonte="swing",
            snapshot=TechnicalSnapshot(
                symbol="SAP.DE",
                timestamp=pd.Timestamp(reference),
                interval="1d",
                bars=220,
                price=240.0,
                ema_fast=241.0,
                ema_slow=238.0,
                sma_long=230.0,
                rsi=55.0,
                atr=4.0,
                macd=1.0,
                macd_signal=0.5,
                macd_hist=0.5,
                volume=1_000_000,
                volume_avg=900_000,
                volume_ratio=1.1,
                gap_pct=None,
                high_lookback=245.0,
                low_lookback=225.0,
                return_short=1.0,
                return_medium=3.0,
                return_long=8.0,
                volatility_pct=2.0,
                relative_strength=1.2,
            ),
            levels=levels,
            score=score,
            context=MarketContext(None, 25.0, None, None, "INDETERMINADO", "sin datos"),
            setup_radar="OPERAR",
            setup_accion="COMPRAR",
            setup_reasons=[],
            radar="OPERAR",
            accion="COMPRAR",
            decision_reasons=[],
            sizing=sizing,
            execution=ExecutionEvaluation(
                reference_price=240.0,
                entry_price=240.0,
                entry_max=243.0,
                stop=232.0,
                targets=(246.0, 252.0, 260.0),
                rr=1.5,
                risk_pct=3.3,
                potential_pct=5.0,
                position_size=sizing,
                capital_at_risk=None,
                executable=True,
                reason="BROKER_UNVERIFIED",
            ),
        )
        fila = FreshnessRow(
            symbol="SAP.DE",
            data_symbol="SAP.DE",
            market="XETRA",
            freshness=calcular_frescura_dato(pd.Timestamp("2026-09-01", tz="UTC"), reference, "XETRA"),
        )
        resultado = AnalysisResult(
            generated_at=reference,
            horizonte="swing",
            interval="1d",
            context=opportunity.context,
            opportunities=[opportunity],
            skipped=[],
            overview=[],
            freshness_rows=[fila],
        )

        config = load_config("config.yaml").model_copy(update={"db_path": tmp_path / "pasada.db"})
        assert config.ai.enabled, "el test cubre justo el camino con IA"

        monkeypatch.setattr(main, "run_analysis", lambda *a, **k: resultado)
        monkeypatch.setattr(main, "format_report", lambda *a, **k: "")
        monkeypatch.setattr(main, "_build_calendar", lambda *a, **k: None)
        monkeypatch.setattr(narrator, "enrich_with_narrative", lambda opportunities, _config: opportunities)
        # La medición del reloj sale a la red (NTP) cuando no hay timedatectl:
        # los tests no deben salir a la red ni pagar el timeout.
        import advisor.run.manifest as manifest

        monkeypatch.setattr(manifest, "measure_clock_drift_seconds", lambda: None)

        args = argparse.Namespace(
            grupos=None, horizonte="swing", sin_ia=False, sin_guardar=False, telegram=False
        )
        assert main.cmd_analizar(args, config, load_universe("universe.yaml")) == 0

        guardadas = AdvisorDB(config.db_path).get_recent_freshness_measurements()
        assert [row["symbol"] for row in guardadas] == ["SAP.DE"]
        recomendaciones = AdvisorDB(config.db_path).get_recent_recommendations()
        assert [row["symbol"] for row in recomendaciones] == ["SAP.DE"]
        run_ids = {row["run_id"] for row in [*guardadas, *recomendaciones]}
        assert len(run_ids) == 1
        run_id = run_ids.pop()
        assert run_id is not None
        assert AdvisorDB(config.db_path).get_analysis_run(run_id)["command"] == "analizar"


class TestUniversoRealCompleto:
    """El comando por defecto mide los 126 activos, no solo los analizables."""

    def test_activo_de_contexto_sin_calendario_degrada_su_fila_no_la_medicion(self) -> None:
        universe = load_universe(Path("universe.yaml"))
        assets = universe.all_assets()
        reference = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
        provider = FakeProvider(
            histories={
                asset.data_symbol(reference): make_ohlcv(n=3, start_date="2026-08-26") for asset in assets
            }
        )

        rows = medir_frescura_datos(assets, provider, _config(), reference)

        assert len(rows) == len(assets)
        fallidas = {row.symbol: row.error for row in rows if row.error is not None}
        # Las 11 plazas de los activos de contexto (CBOE, SNP, NYM, CCY...) no
        # tienen calendario declarado: se declaran una a una y sin calendario.
        assert "^VIX" in fallidas and "sin calendario declarado" in fallidas["^VIX"]
        assert all(row.freshness is not None for row in rows if row.symbol not in fallidas)
        assert {row.market for row in rows if row.error is not None} != {MERCADO_DESCONOCIDO}
        # Los 107 analizables sí se miden.
        analizables = {asset.symbol for asset in universe.analizables()}
        assert analizables.isdisjoint(fallidas)

    def test_la_salida_se_imprime_con_filas_fallidas(self) -> None:
        universe = load_universe(Path("universe.yaml"))
        assets = universe.all_assets()
        reference = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
        provider = FakeProvider(
            histories={
                asset.data_symbol(reference): make_ohlcv(n=3, start_date="2026-08-26") for asset in assets
            }
        )

        salida = format_frescura_datos(medir_frescura_datos(assets, provider, _config(), reference), reference)

        assert "Símbolos sin datos:" in salida
        assert "sin calendario declarado" in salida
