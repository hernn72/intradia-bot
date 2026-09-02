"""Indicadores técnicos."""

from __future__ import annotations

import pandas as pd
import pytest

from advisor.indicators.technical import atr, ema, last_atr, macd, relative_strength, relative_strength_series, rsi, sma
from tests.conftest import make_ohlcv


class TestSmaEma:
    def test_sma_no_produce_valor_antes_de_completar_la_ventana(self) -> None:
        result = sma(pd.Series([1.0, 2.0, 3.0, 4.0]), 3)
        assert result.iloc[:2].isna().all()
        assert result.iloc[2] == pytest.approx(2.0)

    def test_ema_requiere_la_ventana_completa(self) -> None:
        result = ema(pd.Series([1.0, 2.0, 3.0, 4.0]), 3)
        assert result.iloc[:2].isna().all()
        assert not pd.isna(result.iloc[2])

    def test_ema_reacciona_mas_rapido_que_sma(self) -> None:
        # Serie plana con un salto final: la EMA debe quedar por encima de la SMA.
        values = pd.Series([10.0] * 20 + [20.0])
        assert ema(values, 10).iloc[-1] > sma(values, 10).iloc[-1]

    def test_ventana_no_positiva(self) -> None:
        with pytest.raises(ValueError):
            sma(pd.Series([1.0]), 0)
        with pytest.raises(ValueError):
            ema(pd.Series([1.0]), 0)

    def test_serie_vacia(self) -> None:
        with pytest.raises(ValueError):
            sma(pd.Series(dtype=float), 3)


class TestRsi:
    def test_serie_solo_alcista_da_100(self) -> None:
        values = pd.Series([float(i) for i in range(1, 30)])
        assert rsi(values, 14).iloc[-1] == pytest.approx(100.0)

    def test_serie_plana_da_50(self) -> None:
        values = pd.Series([10.0] * 30)
        assert rsi(values, 14).iloc[-1] == pytest.approx(50.0)

    def test_periodo_invalido(self) -> None:
        with pytest.raises(ValueError):
            rsi(pd.Series([1.0, 2.0]), 0)


class TestAtr:
    def test_atr_positivo_en_serie_con_rango(self) -> None:
        df = make_ohlcv(n=60)
        assert last_atr(df, 14) > 0

    def test_devuelve_none_sin_columnas_ohlc(self) -> None:
        df = pd.DataFrame({"Close": [1.0, 2.0, 3.0]})
        assert last_atr(df, 2) is None

    def test_exige_columnas_completas(self) -> None:
        with pytest.raises(ValueError, match="High"):
            atr(pd.DataFrame({"Close": [1.0, 2.0]}), 2)

    def test_dataframe_vacio(self) -> None:
        with pytest.raises(ValueError, match="vacío"):
            atr(pd.DataFrame(), 2)


class TestMacd:
    def test_histograma_positivo_en_tendencia_alcista(self) -> None:
        close = make_ohlcv(n=120, drift=0.5)["Close"]
        _, _, hist = macd(close, 12, 26, 9)
        assert hist.iloc[-1] > 0

    def test_histograma_negativo_en_tendencia_bajista(self) -> None:
        close = make_ohlcv(n=120, start=200.0, drift=-0.5)["Close"]
        _, _, hist = macd(close, 12, 26, 9)
        assert hist.iloc[-1] < 0

    def test_rechaza_rapida_mayor_que_lenta(self) -> None:
        with pytest.raises(ValueError, match="menor"):
            macd(pd.Series([1.0, 2.0]), 26, 12, 9)


class TestRelativeStrength:
    def test_positiva_cuando_el_activo_bate_al_indice(self) -> None:
        activo = make_ohlcv(n=60, drift=1.0)["Close"]
        indice = make_ohlcv(n=60, drift=0.1)["Close"]
        assert relative_strength(activo, indice, 20) > 0

    def test_negativa_cuando_el_activo_va_por_detras(self) -> None:
        activo = make_ohlcv(n=60, drift=0.1)["Close"]
        indice = make_ohlcv(n=60, drift=1.0)["Close"]
        assert relative_strength(activo, indice, 20) < 0

    def test_none_si_falta_historico(self) -> None:
        corta = pd.Series([1.0, 2.0, 3.0])
        larga = make_ohlcv(n=60)["Close"]
        assert relative_strength(corta, larga, 20) is None
        assert relative_strength(larga, corta, 20) is None

    def test_usa_interseccion_de_sesiones_comunes(self) -> None:
        asset_index = pd.date_range("2026-01-01", periods=25, freq="D", tz="UTC")
        benchmark_index = asset_index.delete([3, 7]).append(pd.DatetimeIndex([pd.Timestamp("2026-02-10", tz="UTC")]))
        activo = pd.Series(range(100, 125), index=asset_index, dtype=float)
        indice = pd.Series(range(200, 200 + len(benchmark_index)), index=benchmark_index, dtype=float)

        common = activo.index.normalize().intersection(indice.index.normalize())
        expected_asset = (activo.loc[common[-1]] / activo.loc[common[-21]] - 1) * 100
        expected_bench = (indice.loc[common[-1]] / indice.loc[common[-21]] - 1) * 100

        assert relative_strength(activo, indice, 20) == pytest.approx(expected_asset - expected_bench)
        series = relative_strength_series(activo, indice, 20)
        assert series.loc[asset_index[3]] != series.loc[asset_index[3]]
        assert series.dropna().iloc[-1] == pytest.approx(expected_asset - expected_bench)

    def test_lookback_invalido(self) -> None:
        with pytest.raises(ValueError):
            relative_strength(pd.Series([1.0]), pd.Series([1.0]), 0)


def test_fortaleza_relativa_alinea_por_zona_en_la_cosecha_real() -> None:
    """Un ETF alemán sobre el S&P no puede compararse contra el índice de la víspera.

    La cosecha sella cada barra a la medianoche local de su plaza expresada en
    UTC: una sesión de Fráncfort viaja como `…T22:00:00Z` del día anterior y una
    de Nueva York como `…T04:00:00Z` del mismo día. Sin declarar la zona, la
    intersección empareja sesiones desplazadas un día.
    """

    from pathlib import Path

    import pytest

    from advisor.indicators.technical import _session_index

    VINTAGE_ID = "071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841"
    vintage_dir = Path("data/vintages") / VINTAGE_ID
    if not vintage_dir.is_dir():
        pytest.skip(f"cosecha real no disponible: {vintage_dir}")

    activo = pd.read_csv(vintage_dir / "SXR8.DE.csv", index_col=0)
    indice = pd.read_csv(vintage_dir / "%5EGSPC.csv", index_col=0)

    sin_zona = _session_index(pd.Index(activo.index)).intersection(_session_index(pd.Index(indice.index)))
    con_zona = _session_index(pd.Index(activo.index), "Europe/Berlin").intersection(
        _session_index(pd.Index(indice.index), "America/New_York")
    )

    assert len(sin_zona) < len(con_zona)
    assert len(con_zona) > 1200
