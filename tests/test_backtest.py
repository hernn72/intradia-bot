"""Motor de backtest: entradas, salidas, políticas y ejecución completa.

Los escenarios se construyen vela a vela sobre una serie plana de precio 100
con rango 99-101: ahí el ATR vale exactamente 2, la entrada máxima queda en
101,5 y el objetivo 2 en 106. El mínimo constante de 99 actúa de soporte,
así que el stop se apoya en él con su holgura: 99 − 0,25·ATR = 98,5. Cada
test mueve una única vela para provocar la salida que quiere comprobar.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import pandas as pd
import pytest

from advisor.analysis.opportunity import ACCION_COMPRAR
from advisor.backtest.engine import (
    EXIT_FINAL,
    EXIT_STOP,
    EXIT_TARGET,
    EXIT_TIME,
    POLICY_OPERAR,
    POLICY_TODAS,
    simulate_asset,
)
from advisor.backtest.report import format_backtest_report
from advisor.backtest.runner import run_backtest
from tests.conftest import FakeProvider, make_ohlcv

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
    def test_stop_alcanzado_sale_al_precio_del_stop(self, config, asset_eur) -> None:
        df = make_flat_df(24, {22: (100.0, 101.0, 90.0, 91.0)})
        trades = simulate(df, config, asset_eur)

        assert len(trades) == 1
        trade = trades[0]
        assert trade.exit_reason == EXIT_STOP
        assert trade.entry_price == pytest.approx(100.0)
        assert trade.exit_price == pytest.approx(98.5)  # soporte 99 con holgura de 0,25·ATR
        assert trade.r_multiple == pytest.approx(-1.0)

    def test_objetivo_alcanzado_sale_al_objetivo(self, config, asset_eur) -> None:
        df = make_flat_df(24, {22: (100.0, 107.0, 99.0, 106.5)})
        trades = simulate(df, config, asset_eur)

        trade = trades[0]
        assert trade.exit_reason == EXIT_TARGET
        assert trade.exit_price == pytest.approx(106.0)  # objetivo 2 = 100 + 3·ATR
        assert trade.gross_return_pct == pytest.approx(6.0)
        assert trade.net_return_pct == pytest.approx(5.8)  # menos 0,2% de coste

    def test_hueco_por_debajo_del_stop_sale_a_la_apertura(self, config, asset_eur) -> None:
        """El stop no puede cruzarse a un precio que nunca existió."""

        df = make_flat_df(24, {22: (92.0, 93.0, 91.0, 92.5)})
        trades = simulate(df, config, asset_eur)

        trade = trades[0]
        assert trade.exit_reason == EXIT_STOP
        assert trade.exit_price == pytest.approx(92.0)
        assert trade.r_multiple < -1.0  # peor que el riesgo planificado: eso mide el hueco

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
