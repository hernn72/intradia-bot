"""Estrategia ``itrade_trend_v1`` portada de trading-bot (superbot)."""

from __future__ import annotations

import pandas as pd
import pytest

from superbot.config import StrategyParams, SuperbotConfig
from superbot.strategy import enrich, evaluate, initial_levels, trailed_stop

P = StrategyParams()


def _row(**values: float | bool) -> pd.Series:
    base = {"Close": 100.0, "sma_fast": 95.0, "sma_slow": 90.0, "rsi": 60.0, "atr": 2.0, "trend_break": False}
    base.update(values)
    return pd.Series(base)


def test_compra_con_tendencia_alcista_y_rsi_en_rango() -> None:
    assert evaluate(_row(), P, has_position=False).action == "BUY"
    assert evaluate(_row(rsi=81.0), P, has_position=False).action == "HOLD"
    assert evaluate(_row(rsi=44.0), P, has_position=False).action == "HOLD"
    assert evaluate(_row(sma_fast=101.0), P, has_position=False).action == "HOLD"
    assert evaluate(_row(sma_slow=96.0), P, has_position=False).action == "HOLD"


def test_con_posicion_vende_por_rotura_o_rsi_extremo() -> None:
    assert evaluate(_row(), P, has_position=True).action == "HOLD"
    assert evaluate(_row(trend_break=True), P, has_position=True).action == "SELL"
    assert evaluate(_row(rsi=91.0), P, has_position=True).action == "SELL"


def test_sin_indicadores_no_hay_senal() -> None:
    assert evaluate(_row(sma_slow=float("nan")), P, has_position=False).action == "HOLD"


def test_rotura_exige_dos_cierres_consecutivos_bajo_la_sma_con_buffer() -> None:
    closes = [100.0] * 60 + [97.0, 100.0, 97.0, 97.0]  # SMA50 ≈ 100; umbral 98
    df = pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes})
    out = enrich(df, StrategyParams(sma_slow=55))
    assert list(out["trend_break"].iloc[-4:]) == [False, False, False, True]


def test_niveles_iniciales_y_trailing_que_nunca_baja() -> None:
    stop, t1, t2 = initial_levels(100.0, P)
    assert (stop, t1, t2) == pytest.approx((95.0, 110.0, 120.0))
    assert trailed_stop(95.0, 110.0, 2.0, P) == pytest.approx(104.0)
    assert trailed_stop(104.0, 100.0, 2.0, P) == pytest.approx(104.0)
    assert trailed_stop(95.0, 110.0, None, P) == 95.0


def test_configuracion_ida_y_vuelta_y_validacion() -> None:
    config = SuperbotConfig(initial_capital_eur=5_000.0)
    assert SuperbotConfig.from_json(config.to_json()) == config
    with pytest.raises(ValueError):
        SuperbotConfig.from_json('{"desconocida": 1}')
    with pytest.raises(ValueError):
        SuperbotConfig(initial_capital_eur=0).validate()


def test_fx_antes_del_primer_dato_es_desconocido() -> None:
    from datetime import date

    from superbot.data import FxHistory

    class _Provider:
        def get_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
            index = pd.DatetimeIndex(["2026-03-05", "2026-03-06"], tz="UTC")
            return pd.DataFrame({"Close": [1.25, 1.10]}, index=index)

    fx = FxHistory(_Provider(), {"USD", "EUR"}, "2y")
    assert fx.rate("USD", date(2026, 3, 2)) is None
    assert fx.rate("USD", date(2026, 3, 5)) == pytest.approx(0.8)
    assert fx.rate("USD", date(2026, 3, 9)) == pytest.approx(1 / 1.10)
    assert fx.rate("EUR", date(2020, 1, 1)) == 1.0
