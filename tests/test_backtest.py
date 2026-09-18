"""Motor de backtest: entradas, salidas, políticas y ejecución completa.

Los escenarios se construyen vela a vela sobre una serie plana de precio 100
con rango 99-101: ahí el ATR vale exactamente 2, la entrada máxima queda en
101,5 y el objetivo 2 en 106. El mínimo constante de 99 actúa de soporte,
así que el stop se apoya en él con su holgura: 99 − 0,25·ATR = 98,5. Cada
test mueve una única vela para provocar la salida que quiere comprobar.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import ClassVar, Dict, Optional, Tuple

import pandas as pd
import pytest

from advisor.analysis.levels import compute_levels
from advisor.analysis.opportunity import ACCION_COMPRAR, ACCION_VERIFICAR_BROKER, classify
from advisor.backtest.engine import (
    ACCIONES_OPERABLES,
    ENTRY_OPEN_AT_OPEN,
    EXIT_FINAL,
    EXIT_STOP,
    EXIT_TARGET,
    EXIT_TIME,
    POLICY_OPERAR,
    POLICY_TODAS,
    BacktestTrade,
    ExecutionRejectedSignal,
    simulate_asset,
)
from advisor.backtest.report import format_backtest_report
from advisor.backtest.runner import BacktestResult, run_backtest
from advisor.universe.models import Asset
from tests.conftest import FakeProvider, make_ohlcv
from tests.test_analysis import make_snapshot

WARMUP = 20


def make_flat_df(n: int, overrides: Optional[Dict[int, Tuple[float, float, float, float]]] = None) -> pd.DataFrame:
    """Serie plana (O=C=100, H=101, L=99) con velas concretas sobrescritas."""

    index = pd.date_range("2026-01-01", periods=n, freq="D", tz="UTC")
    rows = []
    for i in range(n):
        o, h, low, c = 100.0, 101.0, 99.0, 100.0
        if overrides and i in overrides:
            o, h, low, c = overrides[i]
        rows.append({"Open": o, "High": h, "Low": low, "Close": c, "Volume": 1_000_000.0})
    return pd.DataFrame(rows, index=index)


def simulate(df: pd.DataFrame, config, asset_eur, policy: str = POLICY_TODAS, **kwargs):
    return simulate_asset(
        asset_eur, df, config, "swing", policy, cost_pct=0.2, min_bars=WARMUP, **kwargs
    )


class TestExits:
    def test_contrato_numerico_de_r_con_numeros_cerrados(self) -> None:
        trade = BacktestTrade(
            symbol="TEST",
            score=70.0,
            radar="OPERAR",
            accion="COMPRAR",
            entry_date=pd.Timestamp("2026-01-01", tz="UTC"),
            exit_date=pd.Timestamp("2026-01-02", tz="UTC"),
            entry_price=100.0,
            exit_price=110.0,
            stop=95.0,
            target=110.0,
            exit_reason=EXIT_TARGET,
            bars_held=1,
            cost_pct=0.20,
        )

        assert trade.risk_pp == pytest.approx(5.0)
        assert trade.gross_return_pp == pytest.approx(10.0)
        assert trade.gross_r_multiple == pytest.approx(2.0)
        assert trade.net_return_pp == pytest.approx(9.8)
        assert trade.net_r_multiple == pytest.approx(1.96)

    @pytest.mark.parametrize(
        ("entry", "stop", "exit_price", "cost_pp"),
        [
            (100.0, 95.0, 110.0, 0.20),
            (50.0, 48.0, 51.0, 0.10),
            (240.0, 232.0, 252.0, 0.35),
            (80.0, 78.8, 78.0, 0.20),
        ],
    )
    def test_identidad_general_de_r_neto(self, entry: float, stop: float, exit_price: float, cost_pp: float) -> None:
        trade = BacktestTrade(
            symbol="TEST",
            score=70.0,
            radar="OPERAR",
            accion="COMPRAR",
            entry_date=pd.Timestamp("2026-01-01", tz="UTC"),
            exit_date=pd.Timestamp("2026-01-02", tz="UTC"),
            entry_price=entry,
            exit_price=exit_price,
            stop=stop,
            target=exit_price,
            exit_reason=EXIT_TARGET,
            bars_held=1,
            cost_pct=cost_pp,
        )

        assert trade.net_r_multiple == pytest.approx(
            trade.gross_r_multiple - cost_pp / trade.risk_pp,
            rel=1e-12,
            abs=1e-12,
        )

    def test_stop_alcanzado_sale_al_precio_del_stop(self, config, asset_eur) -> None:
        df = make_flat_df(24, {22: (100.0, 101.0, 90.0, 91.0)})
        trades = simulate(df, config, asset_eur)

        assert len(trades) == 1
        trade = trades[0]
        assert trade.exit_reason == EXIT_STOP
        assert trade.entry_price == pytest.approx(100.0)
        assert trade.exit_price == pytest.approx(98.5)  # soporte 99 con holgura de 0,25·ATR
        assert trade.gross_r_multiple == pytest.approx(-1.0)

    def test_objetivo_alcanzado_sale_al_objetivo(self, config, asset_eur) -> None:
        df = make_flat_df(24, {22: (100.0, 107.0, 99.0, 106.5)})
        trades = simulate(df, config, asset_eur)

        trade = trades[0]
        assert trade.exit_reason == EXIT_TARGET
        assert trade.exit_price == pytest.approx(106.0)  # objetivo 2 = 100 + 3·ATR
        assert trade.gross_return_pp == pytest.approx(6.0)
        assert trade.net_return_pp == pytest.approx(5.8)  # menos 0,2 pp de coste

    def test_hueco_por_debajo_del_stop_sale_a_la_apertura(self, config, asset_eur) -> None:
        """El stop no puede cruzarse a un precio que nunca existió."""

        df = make_flat_df(24, {22: (92.0, 93.0, 91.0, 92.5)})
        trades = simulate(df, config, asset_eur)

        trade = trades[0]
        assert trade.exit_reason == EXIT_STOP
        assert trade.exit_price == pytest.approx(92.0)
        assert trade.gross_r_multiple < -1.0  # peor que el riesgo planificado: eso mide el hueco

    def test_stop_y_objetivo_en_la_misma_vela_asume_stop(self, config, asset_eur) -> None:
        df = make_flat_df(24, {22: (100.0, 107.0, 95.0, 106.0)})
        trades = simulate(df, config, asset_eur)
        assert trades[0].exit_reason == EXIT_STOP

    def test_salida_por_tiempo_al_agotar_el_horizonte(self, config, asset_eur) -> None:
        df = make_flat_df(WARMUP + 45)  # sin stop ni objetivo: la tesis caduca
        trades = simulate(df, config, asset_eur)

        trade = trades[0]
        assert trade.exit_reason == EXIT_TIME
        assert trade.bars_held == 40  # swing: 2 días a 8 semanas
        assert trade.exit_price == pytest.approx(100.0)

    def test_fin_de_datos_cierra_al_ultimo_precio(self, config, asset_eur) -> None:
        df = make_flat_df(WARMUP + 6)
        trades = simulate(df, config, asset_eur)
        assert trades[0].exit_reason == EXIT_FINAL


class TestEntries:
    def test_apertura_por_encima_de_la_entrada_maxima_no_entra(self, config, asset_eur) -> None:
        """Entrar por encima de entry_max sería perseguir el precio."""

        # La serie acaba justo tras la vela cara: si el precio siguiera ahí,
        # una señal nueva al nivel superior sería legítima, no una persecución.
        df = make_flat_df(WARMUP + 2, {WARMUP + 1: (103.0, 104.0, 102.0, 103.0)})
        trades = simulate(df, config, asset_eur)
        assert trades == []

    def test_senal_rechazada_por_entrada_queda_registrada(self, config, asset_eur) -> None:
        # Señal en WARMUP: precio 100, ATR 2, stop 98,5 y objetivo 106.
        # La entrada máxima por RR coincide con la técnica: 101,5.
        df = make_flat_df(WARMUP + 2, {WARMUP + 1: (103.0, 107.0, 102.0, 106.0)})
        rejected: list[ExecutionRejectedSignal] = []

        trades = simulate(df, config, asset_eur, rejected_signals=rejected)

        assert trades == []
        assert len(rejected) == 1
        lost = rejected[0]
        assert lost.symbol == "SAP.DE"
        assert lost.signal_id == f"SAP.DE|swing|{df.index[WARMUP].isoformat().replace('+00:00', 'Z')}"
        assert lost.signal_date == df.index[WARMUP]
        assert lost.open_date == df.index[WARMUP + 1]
        assert lost.open_price == pytest.approx(103.0)
        assert lost.entry_max == pytest.approx(101.5)
        assert lost.entry_max_tecnica == pytest.approx(101.5)
        assert lost.entry_max_rr == pytest.approx(101.5)
        assert lost.stop == pytest.approx(98.5)
        assert lost.target2 == pytest.approx(106.0)
        assert lost.execution_reason == "ABOVE_MAX_ENTRY"
        assert lost.rr_at_open == pytest.approx((106.0 - 103.0) / (103.0 - 98.5))

    def test_contrafactual_entra_a_la_apertura_real_y_respeta_el_stop(self, config, asset_eur) -> None:
        # Mismos niveles que el test anterior, pero la disciplina contrafactual
        # abre a 103 aunque el filtro real la rechazaría. En la misma vela toca
        # el objetivo 106: R bruto = (106 - 103) / (103 - 98,5) = 2/3.
        df = make_flat_df(WARMUP + 2, {WARMUP + 1: (103.0, 107.0, 102.0, 106.0)})

        trades = simulate(df, config, asset_eur, entry_discipline=ENTRY_OPEN_AT_OPEN)

        assert len(trades) == 1
        trade = trades[0]
        assert trade.entry_price == pytest.approx(103.0)
        assert trade.stop == pytest.approx(98.5)
        assert trade.exit_reason == EXIT_TARGET
        assert trade.exit_price == pytest.approx(106.0)
        assert trade.gross_r_multiple == pytest.approx(2 / 3)
        assert trade.net_r_multiple == pytest.approx(((106.0 / 103.0 - 1) * 100 - 0.2) / ((103.0 - 98.5) / 103.0 * 100))
        assert trade.execution_reason == "ABOVE_MAX_ENTRY"

    def test_el_backtest_por_defecto_no_cambia_ni_una_operacion(self, config, asset_eur) -> None:
        df = make_flat_df(30, {22: (100.0, 107.0, 99.0, 106.5), 26: (100.0, 101.0, 90.0, 91.0)})

        before = simulate(df, config, asset_eur)
        rejected: list[ExecutionRejectedSignal] = []
        after = simulate(df, config, asset_eur, rejected_signals=rejected)

        assert after == before

    def test_el_filtro_de_ejecucion_no_toca_el_score(self, config, asset_eur) -> None:
        df = make_flat_df(WARMUP + 2, {WARMUP + 1: (103.0, 107.0, 102.0, 106.0)})
        rejected: list[ExecutionRejectedSignal] = []
        simulate(df, config, asset_eur, rejected_signals=rejected)

        same_signal = simulate(df, config, asset_eur, entry_discipline=ENTRY_OPEN_AT_OPEN)[0]

        assert rejected[0].score == pytest.approx(same_signal.score)

    def test_apertura_por_debajo_del_stop_no_entra(self, config, asset_eur) -> None:
        overrides = dict.fromkeys(range(WARMUP + 1, WARMUP + 4), (94.0, 95.0, 93.0, 94.0))
        df = make_flat_df(WARMUP + 4, overrides)
        trades = simulate(df, config, asset_eur)
        assert all(t.entry_price > t.stop for t in trades)

    def test_tras_salir_puede_volver_a_entrar(self, config, asset_eur) -> None:
        df = make_flat_df(30, {22: (100.0, 101.0, 90.0, 91.0), 23: (100.0, 101.0, 99.0, 100.0)})
        trades = simulate(df, config, asset_eur)
        assert len(trades) >= 2
        assert trades[0].exit_date < trades[1].entry_date

    def test_una_posicion_por_activo(self, config, asset_eur) -> None:
        """Mientras hay posición abierta no se abre otra: los intervalos no se solapan."""

        df = make_flat_df(60, {30: (100.0, 101.0, 90.0, 91.0), 45: (100.0, 107.0, 99.0, 106.0)})
        trades = simulate(df, config, asset_eur)
        for previous, current in zip(trades, trades[1:]):
            assert previous.exit_date <= current.entry_date


class TestPolicies:
    def test_contexto_hostil_frena_la_politica_real_pero_no_el_censo(self, config, asset_eur) -> None:
        df = make_flat_df(30)
        n = len(df)
        hostil = dict(
            vix_at=[40.0] * n, trend_price_at=[4000.0] * n, trend_sma_at=[4500.0] * n
        )

        censo = simulate(df, config, asset_eur, policy=POLICY_TODAS, **hostil)
        real = simulate(df, config, asset_eur, policy=POLICY_OPERAR, **hostil)

        assert len(censo) >= 1
        assert all(t.accion != ACCION_COMPRAR for t in censo)
        assert real == []

    def test_politica_desconocida(self, config, asset_eur) -> None:
        with pytest.raises(ValueError, match="política"):
            simulate_asset(asset_eur, make_flat_df(25), config, "swing", "mixta", 0.2, min_bars=WARMUP)

    def test_horizonte_sin_backtest(self, config, asset_eur) -> None:
        with pytest.raises(ValueError, match="horizonte"):
            simulate_asset(asset_eur, make_flat_df(25), config, "intradia", POLICY_TODAS, 0.2, min_bars=WARMUP)


class TestRunner:
    @pytest.fixture
    def histories(self) -> dict:
        return {
            "SAP.DE": make_ohlcv(n=300, start=200.0, drift=0.3),
            "AAPL": make_ohlcv(n=300, start=150.0, drift=0.2),
            "^STOXX50E": make_ohlcv(n=400, start=4500.0, drift=1.0),
            "^VIX": make_ohlcv(n=400, start=15.0, drift=0.0),
        }

    def test_ejecuta_las_dos_politicas_y_referencia(self, config, universe, histories) -> None:
        provider = FakeProvider(histories)
        result = run_backtest(config, universe, provider, horizonte="swing", period="2y")

        assert set(result.evaluated) == {"SAP.DE", "AAPL"}
        assert len(result.trades_todas) >= len(result.trades_operar)
        assert "SAP.DE" in result.buy_hold_pct
        # Un backtest sin datos de contexto no debe abortar; con ellos, menos aún.
        assert result.skipped == []

    def test_activo_sin_datos_queda_en_no_evaluados(self, config, universe) -> None:
        provider = FakeProvider({"SAP.DE": make_ohlcv(n=300, start=200.0, drift=0.3)})
        result = run_backtest(config, universe, provider)
        assert result.evaluated == ["SAP.DE"]
        assert any(symbol == "AAPL" for symbol, _ in result.skipped)

    def test_intradia_se_rechaza_con_motivo(self, config, universe) -> None:
        with pytest.raises(ValueError, match="intradía"):
            run_backtest(config, universe, FakeProvider(), horizonte="intradia")

    def test_el_informe_se_genera_y_declara_sus_limites(self, config, universe, histories) -> None:
        result = run_backtest(config, universe, FakeProvider(histories), period="2y")
        report = format_backtest_report(result)
        assert "BACKTEST" in report
        assert "Advertencias" in report
        assert "¿ORDENA LA PUNTUACIÓN?" in report
        assert "no garantizan nada" in report


class TestPoblacionDeOperarYBroker:
    """El estado del broker no puede cambiar la población que mide el laboratorio.

    Regresión de la revisión de T-007: al convertir ``BROKER_UNVERIFIED`` en la
    acción propia ``VERIFICAR_BROKER``, los activos sin verificar salían de
    ``POLICY_OPERAR`` en silencio, que es justo lo que D-04 prohíbe.
    """

    def test_verificar_broker_sigue_entrando_en_la_poblacion_de_operar(self) -> None:
        assert ACCION_COMPRAR in ACCIONES_OPERABLES
        assert ACCION_VERIFICAR_BROKER in ACCIONES_OPERABLES

    def test_misma_senal_misma_poblacion_con_y_sin_broker_verificado(self, config, benign_context) -> None:
        """La misma señal, con el activo verificado y sin verificar, entra igual."""

        class _Score:
            value = 85.0
            missing_dimensions: ClassVar[list] = []
            dimensions: ClassVar[list] = []
            evaluable_max = 80.0

        def _asset(trade_republic: str) -> Asset:
            return Asset(
                symbol="UCG.MI",
                name="UniCredit",
                asset_class="stock",
                region="EUROPA",
                market="MIL",
                currency="EUR",
                timezone="Europe/Rome",
                trade_republic=trade_republic,
                isin=None,
            )

        levels = compute_levels(make_snapshot(), config.levels, config.risk.min_rr_ratio)
        acciones = {}
        for estado in ("yes", "unknown"):
            _, accion, _ = classify(
                _Score(), levels, benign_context, config.scoring, config.risk, _asset(estado)
            )
            acciones[estado] = accion

        assert acciones["yes"] == ACCION_COMPRAR
        assert acciones["unknown"] == ACCION_VERIFICAR_BROKER
        # Lo que no puede cambiar: si una entra en la población medida, la otra también.
        assert all(accion in ACCIONES_OPERABLES for accion in acciones.values())

    def test_laboratorio_broker_neutral_incluye_no_sin_cambiar_default(self, config) -> None:
        asset_no = Asset(
            symbol="LRCX",
            name="Lam Research",
            asset_class="stock",
            region="USA",
            market="NASDAQ",
            currency="USD",
            timezone="America/New_York",
            trade_republic="no",
        )
        df = make_flat_df(24, {22: (100.0, 107.0, 99.0, 106.5)})

        default = simulate(df, config, asset_no, policy=POLICY_OPERAR)
        neutral = simulate(df, config, asset_no, policy=POLICY_OPERAR, broker_neutral=True)

        assert default == []
        assert len(neutral) == 1
        assert neutral[0].accion == "DESCARTAR"

    def test_el_informe_del_backtest_no_esconde_las_operaciones_sin_verificar(self) -> None:
        """Una operación ``VERIFICAR_BROKER`` tiene fila propia en el informe."""

        def _trade(accion: str, symbol: str) -> BacktestTrade:
            return BacktestTrade(
                symbol=symbol,
                score=85.0,
                radar="OPERAR",
                accion=accion,
                entry_date=pd.Timestamp("2026-01-01", tz="UTC"),
                exit_date=pd.Timestamp("2026-01-02", tz="UTC"),
                entry_price=100.0,
                exit_price=110.0,
                stop=95.0,
                target=110.0,
                exit_reason=EXIT_TARGET,
                bars_held=1,
                cost_pct=0.20,
            )

        result = BacktestResult(
            horizonte="swing",
            period="5y",
            cost_pct=0.20,
            warmup_bars=WARMUP,
            trades_operar=[_trade(ACCION_COMPRAR, "SAP.DE")],
            trades_todas=[_trade(ACCION_COMPRAR, "SAP.DE"), _trade(ACCION_VERIFICAR_BROKER, "UCG.MI")],
            evaluated=["SAP.DE", "UCG.MI"],
        )

        informe = format_backtest_report(result)
        assert ACCION_VERIFICAR_BROKER in informe


class TestCosechaCongelada:
    """T-015: el backtest deja de depender del minuto en que se ejecuta."""

    class RawProvider:
        """Proveedor doble por la ruta bruta, la que congela la cosecha."""

        def __init__(self, histories: dict) -> None:
            self.histories = histories

        def get_raw_history(self, symbol: str, period: str = "5y", interval: str = "1d"):
            if symbol not in self.histories:
                raise ValueError(f"sin datos para '{symbol}'")
            return self.histories[symbol].copy()

    @staticmethod
    def _serie(n: int, start: float, drift: float, amplitud: float, periodo: int, fase: float = 0.0):
        """Tendencia con retrocesos: una recta no genera ni una señal.

        `make_ohlcv` sube en línea recta, y con eso el precio nunca vuelve por
        debajo de la entrada máxima: el backtest sale con cero operaciones y un
        test de reproducibilidad sobre cero operaciones no prueba nada.
        """

        index = pd.date_range(start="2026-01-01", periods=n, freq="D", tz="UTC")
        filas = []
        for i in range(n):
            base = start + drift * i + amplitud * math.sin(2 * math.pi * (i + fase) / periodo)
            apertura = base * 0.997
            filas.append({
                "Open": apertura,
                "High": max(apertura, base) * 1.01,
                "Low": min(apertura, base) * 0.99,
                "Close": base,
                "Volume": 1_000_000.0,
                "Dividends": 0.0,
                "Stock Splits": 0.0,
            })
        return pd.DataFrame(filas, index=index)

    @pytest.fixture
    def cosecha(self, tmp_path):
        """Cosecha congelada en disco, con los dos activos y el contexto."""

        from advisor.research.vintage import freeze_vintage

        histories = {
            "SAP.DE": self._serie(400, 200.0, 0.25, 15.0, 30),
            "AAPL": self._serie(400, 150.0, 0.2, 10.0, 30, fase=7),
            "^STOXX50E": self._serie(400, 4500.0, 1.0, 50.0, 60),
            "^VIX": self._serie(400, 15.0, 0.0, 2.0, 35),
        }
        resultado = freeze_vintage(
            list(histories),
            self.RawProvider(histories),
            period="5y",
            interval="1d",
            root_dir=tmp_path,
            downloaded_at=datetime(2026, 8, 30, 9, 41, tzinfo=timezone.utc),
        )
        return resultado.data_vintage_id, tmp_path

    def test_backtest_sobre_cosecha_es_reproducible(self, config, universe, cosecha) -> None:
        """Dos cargas independientes de la misma cosecha dan las mismas operaciones.

        No se comparan totales sino operación por operación y campo por campo:
        dos pasadas pueden sumar lo mismo con operaciones distintas.
        """

        from advisor.research.vintage import load_vintage

        vintage_id, root = cosecha
        primera = run_backtest(
            config, universe, None, horizonte="swing",
            vintage=load_vintage(vintage_id, root_dir=root),
        )
        segunda = run_backtest(
            config, universe, None, horizonte="swing",
            vintage=load_vintage(vintage_id, root_dir=root),
        )

        # Sin operaciones el test no probaría nada. La política real puede quedar
        # vacía con datos sintéticos —el score rara vez llega a COMPRAR—, así que
        # la guarda mira el censo completo; la cobertura de POLICY_OPERAR la da
        # `tests/test_backtest_real_vintage.py` sobre la cosecha de verdad.
        assert primera.trades_todas
        assert len(primera.trades_operar) == len(segunda.trades_operar)
        for a, b in zip(primera.trades_operar, segunda.trades_operar):
            assert a == b
        for a, b in zip(primera.trades_todas, segunda.trades_todas):
            assert a == b
        assert primera.buy_hold_pct == segunda.buy_hold_pct
        assert primera.evaluated == segunda.evaluated

    def test_backtest_con_vintage_declara_el_data_vintage_id(self, config, universe, cosecha) -> None:
        from advisor.research.vintage import load_vintage

        vintage_id, root = cosecha
        result = run_backtest(
            config, universe, None, horizonte="swing",
            vintage=load_vintage(vintage_id, root_dir=root),
        )

        assert result.data_vintage_id == vintage_id
        assert result.reproducible is True
        assert result.data_range is not None and result.data_range[0] < result.data_range[1]
        informe = format_backtest_report(result)
        assert vintage_id[:12] in informe
        assert "resultado reproducible" in informe

    def test_backtest_en_vivo_declara_que_no_es_reproducible(self, config, universe) -> None:
        histories = {
            "SAP.DE": make_ohlcv(n=300, start=200.0, drift=0.3),
            "AAPL": make_ohlcv(n=300, start=150.0, drift=0.2),
            "^STOXX50E": make_ohlcv(n=400, start=4500.0, drift=1.0),
            "^VIX": make_ohlcv(n=400, start=15.0, drift=0.0),
        }
        result = run_backtest(config, universe, FakeProvider(histories), horizonte="swing", period="2y")

        assert result.data_vintage_id is None
        assert result.reproducible is False
        informe = format_backtest_report(result)
        assert "NO es reproducible" in informe
        assert "--vintage" in informe

    def test_las_operaciones_cerradas_no_cambian_al_quitar_el_futuro(self, config, universe, cosecha) -> None:
        """Estabilidad de prefijo: lo ya cerrado no cambia porque después haya más datos.

        Se simula sobre la cosecha entera y sobre la misma cosecha cortada. Toda
        operación **cerrada** antes del corte debe salir idéntica en las dos.

        **Qué caza y qué no, medido inyectando el defecto** (evidencia en
        `evidence/2026-09-18-T-015-backtest-reproducible/inyeccion-de-defectos.txt`):

        - Caza un look-ahead ancho: con la media de tendencia centrada
          (`center=True`, que usa 100 barras futuras) el test falla.
        - **No caza un look-ahead de una barra**: si el VIX se alineara con
          `shift(-1)` en vez de `shift(1)`, este test pasa igual. Es una
          limitación estructural, no un descuido: cualquier corte posterior a la
          barra espiada la deja presente en las dos series. Contra ese caso la
          guarda es el `shift(1)` explícito del runner, y la definitiva será el
          contrato point-in-time de INV-09, que es trabajo de T-014 (B-00).
        """

        from advisor.research.vintage import VintageLoad, build_views, load_vintage

        vintage_id, root = cosecha
        completa = load_vintage(vintage_id, root_dir=root)
        corte = next(iter(completa.by_symbol.values())).raw.index[320]
        truncada = VintageLoad(
            data_vintage_id=completa.data_vintage_id,
            manifest=completa.manifest,
            by_symbol={
                symbol: build_views(views.raw.loc[:corte])
                for symbol, views in completa.by_symbol.items()
            },
        )

        con_futuro = run_backtest(config, universe, None, horizonte="swing", vintage=completa)
        sin_futuro = run_backtest(config, universe, None, horizonte="swing", vintage=truncada)

        cerradas_antes = [t for t in con_futuro.trades_todas if str(t.exit_date) <= str(corte)]
        assert cerradas_antes, "el corte debe dejar operaciones cerradas a la izquierda"
        equivalentes = {(t.symbol, str(t.entry_date)): t for t in sin_futuro.trades_todas}
        for trade in cerradas_antes:
            gemela = equivalentes.get((trade.symbol, str(trade.entry_date)))
            assert gemela is not None, f"{trade.symbol} {trade.entry_date} desaparece al quitar el futuro"
            assert gemela == trade

    def test_una_cosecha_sin_tendencia_lo_dice(self, config, universe, cosecha) -> None:
        """Faltar TODO el contexto no puede parecerse a no faltar nada (INV-16).

        `context_sin_sma` cuenta sesiones sin media. Si la cosecha ni siquiera
        trae el índice de tendencia, ese contador vale 0 —no falta ninguna
        sesión: faltan todas—, y sin un aviso propio el informe diría que no
        pasa nada.
        """

        from advisor.research.vintage import VintageLoad, load_vintage

        vintage_id, root = cosecha
        original = load_vintage(vintage_id, root_dir=root)
        sin_tendencia = VintageLoad(
            data_vintage_id=original.data_vintage_id,
            manifest=original.manifest,
            by_symbol={s: v for s, v in original.by_symbol.items() if s != "^STOXX50E"},
        )

        result = run_backtest(config, universe, None, horizonte="swing", vintage=sin_tendencia)

        assert result.context_sin_tendencia is True
        assert result.context_sin_sma == 0  # no falta "alguna" sesión: falta la serie entera
        assert "AVISO GRAVE" in format_backtest_report(result)

    def test_una_decision_no_puede_depender_de_la_barra_siguiente(self, config, universe, cosecha) -> None:
        """Look-ahead de UNA barra, cazado perturbando el futuro en vez de truncarlo.

        Truncar no sirve: cualquier corte posterior a la barra espiada la deja
        presente en las dos series. Perturbar sí. Se cambia el VIX **solo** en la
        vela en la que una operación entra —cuya decisión se tomó en la vela
        anterior— y esa operación tiene que salir idéntica: con `shift(1)` la
        decisión usa el VIX de dos velas antes y no puede verla.

        Con `shift(-1)` inyectado, este test falla; comprobado en
        `evidence/2026-09-18-T-015-backtest-reproducible/inyeccion-de-defectos.txt`.
        """

        from advisor.research.vintage import VintageLoad, build_views, load_vintage

        vintage_id, root = cosecha
        original = load_vintage(vintage_id, root_dir=root)
        base = run_backtest(config, universe, None, horizonte="swing", vintage=original)
        assert base.trades_todas

        operacion = base.trades_todas[len(base.trades_todas) // 2]
        vix_raw = original.by_symbol["^VIX"].raw
        posicion = list(pd.to_datetime(vix_raw.index)).index(pd.Timestamp(operacion.entry_date))

        perturbado = vix_raw.copy()
        columna = perturbado.columns.get_loc("Close")
        # Un VIX de 80 vuelve el contexto hostil: si la decisión lo viera, cambiaría.
        perturbado.iloc[posicion, columna] = 80.0
        futuro_cambiado = VintageLoad(
            data_vintage_id=original.data_vintage_id,
            manifest=original.manifest,
            by_symbol={
                symbol: (build_views(perturbado) if symbol == "^VIX" else views)
                for symbol, views in original.by_symbol.items()
            },
        )

        con_perturbacion = run_backtest(config, universe, None, horizonte="swing", vintage=futuro_cambiado)
        gemela = next(
            (t for t in con_perturbacion.trades_todas
             if t.symbol == operacion.symbol and t.entry_date == operacion.entry_date),
            None,
        )
        assert gemela is not None, "la operación desaparece al tocar el VIX de su propia vela de entrada"
        assert gemela == operacion

    def test_las_fechas_se_fechan_igual_en_los_dos_modos(self, config, universe, cosecha) -> None:
        """La misma operación tiene que poder compararse entre cosecha y vivo.

        La cosecha guarda sus marcas de tiempo como texto —es lo que hace
        estables los hashes de INV-13—, así que sin convertir el índice
        `entry_date` sería un `str` sobre cosecha y un `Timestamp` en vivo. El
        informe ordena por ese campo.
        """

        from advisor.research.vintage import load_vintage

        vintage_id, root = cosecha
        sobre_cosecha = run_backtest(
            config, universe, None, horizonte="swing",
            vintage=load_vintage(vintage_id, root_dir=root),
        )
        en_vivo = run_backtest(
            config, universe,
            FakeProvider({
                "SAP.DE": self._serie(400, 200.0, 0.25, 15.0, 30),
                "AAPL": self._serie(400, 150.0, 0.2, 10.0, 30, fase=7),
                "^STOXX50E": self._serie(400, 4500.0, 1.0, 50.0, 60),
                "^VIX": self._serie(400, 15.0, 0.0, 2.0, 35),
            }),
            horizonte="swing", period="2y",
        )

        assert sobre_cosecha.trades_todas and en_vivo.trades_todas
        for trade in sobre_cosecha.trades_todas + en_vivo.trades_todas:
            assert isinstance(trade.entry_date, pd.Timestamp)
            assert isinstance(trade.exit_date, pd.Timestamp)

    def test_el_backtest_sin_proveedor_y_sin_cosecha_falla(self, config, universe) -> None:
        with pytest.raises(ValueError, match="proveedor de datos o una cosecha"):
            run_backtest(config, universe, None, horizonte="swing")


class TestBacktestCLI:
    """El comando: cómo se pide una cosecha y qué combinaciones no valen."""

    def test_el_parser_no_impone_periodo_por_defecto(self) -> None:
        """`--period` nace vacío para poder distinguir «no lo pidió» de «pidió 5y»."""

        from advisor.main import build_parser

        args = build_parser().parse_args(["backtest"])
        assert args.period is None
        assert args.vintage is None

    def test_periodo_y_cosecha_juntos_se_rechazan(self, config, universe, capsys) -> None:
        """Recortar una cosecha por periodo devolvería la dependencia del reloj.

        Un periodo es relativo a *ahora*; una cosecha es un rango fijo. Mezclarlos
        volvería a hacer que el resultado dependiera del minuto de la ejecución,
        que es justo lo que esta ficha quita.
        """

        from advisor.main import build_parser, cmd_backtest

        args = build_parser().parse_args(["backtest", "--vintage", "071ddb2b", "--period", "2y"])

        assert cmd_backtest(args, config, universe) == 2
        assert "--period no se puede usar con --vintage" in capsys.readouterr().err
