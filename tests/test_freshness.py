"""Frescura de datos de mercado."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from advisor.config import AdvisorConfig
from advisor.data.freshness import (
    QUALITY_DEGRADED,
    QUALITY_INCOMPLETE,
    QUALITY_OK,
    agrupar_frescura_por_fecha,
    calcular_frescura_dato,
    calcular_frescura_serie,
)
from advisor.main import format_frescura_datos, format_frescura_historico, medir_frescura_datos
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
        )

        assert freshness.last_bar_date.isoformat() == "2026-08-28"
        assert freshness.natural_days == 0
        assert freshness.sessions_approx == 0
        assert "al día" in freshness.label

    def test_fin_de_semana_no_suma_sesiones(self) -> None:
        freshness = calcular_frescura_dato(
            pd.Timestamp("2026-08-28", tz="UTC"),
            datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc),
        )

        assert freshness.natural_days == 2
        assert freshness.sessions_approx == 0

    def test_sesion_en_curso_no_cuenta_como_perdida(self) -> None:
        freshness = calcular_frescura_dato(
            pd.Timestamp("2026-08-28", tz="UTC"),
            datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc),
        )

        assert freshness.natural_days == 3
        assert freshness.sessions_approx == 0

    def test_salto_de_dos_sesiones_sin_festivos(self) -> None:
        freshness = calcular_frescura_dato(
            pd.Timestamp("2026-08-26", tz="UTC"),
            datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc),
        )

        assert freshness.natural_days == 4
        assert freshness.sessions_approx == 2
        assert "sin festivos" in freshness.label


class TestMedirFrescuraDatos:
    def test_agrupa_por_fecha_y_plaza_con_proveedor_inyectado(self) -> None:
        assets = [
            _asset("SAP.DE", "XETRA"),
            _asset("ASML.AS", "EURONEXT"),
            _asset("AAPL", "NASDAQ", "USA"),
        ]
        provider = FakeProvider(
            histories={
                "SAP.DE": make_ohlcv(n=3, start_date="2026-08-24"),
                "ASML.AS": make_ohlcv(n=3, start_date="2026-08-24"),
                "AAPL": make_ohlcv(n=5, start_date="2026-08-24"),
                "^STOXX": make_ohlcv(n=5, start_date="2026-08-24"),
                "^GSPC": make_ohlcv(n=5, start_date="2026-08-24"),
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

        assert provider.calls == ["SAP.DE", "^STOXX", "ASML.AS", "AAPL", "^GSPC"]
        assert [(bucket.last_bar_date.isoformat(), bucket.symbols_count) for bucket in buckets] == [
            ("2026-08-28", 1),
            ("2026-08-26", 2),
        ]
        viejo = buckets[1]
        assert viejo.freshness.sessions_approx == 2
        assert viejo.markets_label == "EURONEXT, XETRA"

    def test_salida_declara_hora_de_medicion_y_dispersion_por_plaza(self) -> None:
        assets = [
            _asset("AAA.DE", "XETRA"),
            _asset("BBB.DE", "XETRA"),
            _asset("CCC.DE", "XETRA"),
            _asset("DDD.PA", "EURONEXT"),
        ]
        provider = FakeProvider(
            histories={
                "AAA.DE": make_ohlcv(n=1, start_date="2026-08-28"),
                "BBB.DE": make_ohlcv(n=1, start_date="2026-08-28"),
                "CCC.DE": make_ohlcv(n=1, start_date="2026-08-27"),
                "DDD.PA": make_ohlcv(n=1, start_date="2026-08-27"),
                "^STOXX": make_ohlcv(n=1, start_date="2026-08-28"),
            }
        )
        reference = datetime(2026, 8, 30, 17, 20, tzinfo=timezone.utc)

        rows = medir_frescura_datos(assets, provider, _config(), reference)
        salida = format_frescura_datos(rows, reference)

        assert "Medición: 2026-08-30 17:20:00 UTC" in salida
        assert "Dispersión por plaza:" in salida
        assert "| XETRA | vie 28 | 1 / 3 |" in salida
        assert "| EURONEXT | jue 27 | 0 / 1 |" in salida

    def test_detecta_sesion_ausente_intermedia_jueves_lunes_frente_a_benchmark(self) -> None:
        activo = make_ohlcv(n=3, start_date="2026-08-26").drop(pd.Timestamp("2026-08-28", tz="UTC"))
        activo.loc[pd.Timestamp("2026-08-31", tz="UTC")] = activo.iloc[-1]
        activo = activo.sort_index()
        benchmark = make_ohlcv(n=4, start_date="2026-08-26")
        benchmark = benchmark.drop(pd.Timestamp("2026-08-29", tz="UTC"))
        benchmark.loc[pd.Timestamp("2026-08-31", tz="UTC")] = benchmark.iloc[-1]
        benchmark = benchmark.sort_index()

        freshness = calcular_frescura_serie(
            activo,
            datetime(2026, 8, 31, 7, 30, tzinfo=timezone.utc),
            benchmark_close=benchmark["Close"],
            benchmark_symbol="^STOXX50E",
        )

        assert freshness.sessions_approx == 0
        assert freshness.last_bar_date.isoformat() == "2026-08-31"
        assert [value.isoformat() for value in freshness.absent_reference_sessions] == ["2026-08-28"]
        assert freshness.may_be_partial_current_session is True

    def test_frescura_datos_declara_sesiones_ausentes_y_referencia(self) -> None:
        activo = make_ohlcv(n=3, start_date="2026-08-26").drop(pd.Timestamp("2026-08-28", tz="UTC"))
        activo.loc[pd.Timestamp("2026-08-31", tz="UTC")] = activo.iloc[-1]
        benchmark = make_ohlcv(n=3, start_date="2026-08-27").drop(pd.Timestamp("2026-08-29", tz="UTC"))
        benchmark.loc[pd.Timestamp("2026-08-31", tz="UTC")] = benchmark.iloc[-1]
        provider = FakeProvider(histories={"SAP.DE": activo.sort_index(), "^STOXX": benchmark.sort_index()})
        reference = datetime(2026, 8, 31, 7, 30, tzinfo=timezone.utc)

        rows = medir_frescura_datos([_asset("SAP.DE", "XETRA")], provider, _config(), reference)
        salida = format_frescura_datos(rows, reference)

        assert "| Símbolo | Símbolo datos | Plaza | Última barra | Antigüedad | Referencia | Sesiones ausentes |" in salida
        assert "| SAP.DE | SAP.DE | XETRA | 2026-08-31 | hoy; al día; barra de hoy posiblemente parcial | ^STOXX | 2026-08-28 |" in salida

    def test_calidad_incompleto_degradado_ok(self) -> None:
        reference = datetime(2026, 8, 31, 18, 0, tzinfo=timezone.utc)
        activo_incompleto = make_ohlcv(n=4, start_date="2026-08-26").drop(pd.Timestamp("2026-08-28", tz="UTC"))
        activo_incompleto.loc[pd.Timestamp("2026-08-31", tz="UTC")] = activo_incompleto.iloc[-1]
        benchmark = make_ohlcv(n=4, start_date="2026-08-26")
        benchmark.loc[pd.Timestamp("2026-08-31", tz="UTC")] = benchmark.iloc[-1]

        incompleto = calcular_frescura_serie(
            activo_incompleto.sort_index(),
            reference,
            benchmark_close=benchmark["Close"],
            benchmark_symbol="^STOXX",
        )
        degradado = calcular_frescura_serie(make_ohlcv(n=2, start_date="2026-08-26"), reference)
        ok = calcular_frescura_serie(make_ohlcv(n=4, start_date="2026-08-26"), reference, benchmark["Close"], "^STOXX")

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
            }
        ])

        salida = format_frescura_historico(db.get_recent_freshness_measurements())

        assert "| 2026-09-02T08:30:00+00:00 | SAP.DE | SAP.DE | XETRA | 2026-08-31 | al día | ^STOXX | sí | 2026-08-28 |  |" in salida

    def test_hueco_viejo_declara_pero_no_veta(self) -> None:
        """Un hueco fuera de la ventana de veto se declara, no bloquea abrir.

        Medido el 2026-09-02 sobre el universo real: con la ventana larga,
        AZN, TSM y NOVO-B.CO quedaban vetados por sesiones que les faltaban
        hace meses, y ese veto no habría caducado nunca.
        """

        reference = datetime(2026, 8, 31, 18, 0, tzinfo=timezone.utc)
        benchmark = make_ohlcv(n=30, start_date="2026-07-20")
        hueco = pd.Timestamp(benchmark.index[2])
        activo = benchmark.drop(hueco)

        viejo = calcular_frescura_serie(
            activo,
            reference,
            benchmark_close=benchmark["Close"],
            benchmark_symbol="^STOXX",
            recent_reference_sessions=200,
            veto_window_sessions=5,
        )
        reciente = calcular_frescura_serie(
            activo,
            reference,
            benchmark_close=benchmark["Close"],
            benchmark_symbol="^STOXX",
            recent_reference_sessions=200,
            veto_window_sessions=200,
        )

        assert viejo.absent_reference_sessions == (hueco.date(),)
        assert viejo.absent_recent_sessions == ()
        assert viejo.quality == QUALITY_DEGRADED
        assert reciente.quality == QUALITY_INCOMPLETE


class TestPersistenciaEnLaPasadaReal:
    """La IA activada no puede vaciar el histórico de frescura.

    `cmd_analizar` reconstruía el `AnalysisResult` campo a campo tras redactar
    con la IA y se dejaba `freshness_rows` fuera. Los tests pasaban, pero en la
    Pi —que corre con la IA activada— no se guardaba ni una medición.
    """

    def test_guarda_frescura_con_la_ia_activada(self, tmp_path, monkeypatch) -> None:
        import argparse
        from datetime import datetime, timezone as tz

        import advisor.ai.narrator as narrator
        import advisor.main as main
        from advisor.analysis.analyzer import AnalysisResult
        from advisor.config import load_config
        from advisor.data.freshness import FreshnessRow, calcular_frescura_dato
        from advisor.storage.db import AdvisorDB
        from advisor.universe.loader import load_universe

        reference = datetime(2026, 9, 2, 10, 0, tzinfo=tz.utc)
        fila = FreshnessRow(
            symbol="SAP.DE",
            data_symbol="SAP.DE",
            market="XETRA",
            freshness=calcular_frescura_dato(pd.Timestamp("2026-09-01", tz="UTC"), reference),
        )
        resultado = AnalysisResult(
            generated_at=reference,
            horizonte="swing",
            interval="1d",
            context=None,
            opportunities=[],
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

        args = argparse.Namespace(
            grupos=None, horizonte="swing", sin_ia=False, sin_guardar=False, telegram=False
        )
        assert main.cmd_analizar(args, config, load_universe("universe.yaml")) == 0

        guardadas = AdvisorDB(config.db_path).get_recent_freshness_measurements()
        assert [row["symbol"] for row in guardadas] == ["SAP.DE"]
