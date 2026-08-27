"""Indicadores técnicos."""

from __future__ import annotations

import pandas as pd
import pytest

from advisor.indicators.technical import atr, ema, last_atr, macd, relative_strength, rsi, sma
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

    def test_lookback_invalido(self) -> None:
        with pytest.raises(ValueError):
            relative_strength(pd.Series([1.0]), pd.Series([1.0]), 0)
