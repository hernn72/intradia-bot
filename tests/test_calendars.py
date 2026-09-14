"""Calendarios de plaza para frescura de datos."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import pytest

from advisor.data.calendars import expected_sessions, missing_sessions
from advisor.data.freshness import calcular_frescura_serie, mercado_para_simbolo
from advisor.universe.models import Asset


def _ohlcv_for_dates(values: list[date]) -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.Timestamp(value, tz="UTC") for value in values])
    return pd.DataFrame(
        {
            "Open": [100.0 + i for i in range(len(values))],
            "High": [101.0 + i for i in range(len(values))],
            "Low": [99.0 + i for i in range(len(values))],
            "Close": [100.0 + i for i in range(len(values))],
            "Volume": [1_000_000.0] * len(values),
        },
        index=index,
    )


def test_xetra_no_espera_sesion_el_24_26_31_dic_ni_viernes_santo_ni_1_mayo() -> None:
    sessions = set(expected_sessions("XETRA", date(2025, 12, 20), date(2026, 9, 10)))

    assert date(2025, 12, 24) not in sessions
    assert date(2025, 12, 26) not in sessions
    assert date(2025, 12, 31) not in sessions
    assert date(2026, 4, 3) not in sessions
    assert date(2026, 4, 6) not in sessions
    assert date(2026, 5, 1) not in sessions
    assert date(2026, 3, 6) in sessions
    assert date(2026, 9, 7) in sessions


def test_nyse_no_espera_labor_day_ni_thanksgiving() -> None:
    sessions = set(expected_sessions("NYSE", date(2025, 11, 20), date(2026, 9, 10)))

    assert date(2026, 9, 7) not in sessions
    assert date(2025, 11, 27) not in sessions
    assert date(2026, 9, 8) in sessions


def test_jpx_espera_sesion_cuando_xetra_cierra() -> None:
    assert date(2026, 4, 6) in set(expected_sessions("JPX", date(2026, 4, 1), date(2026, 4, 10)))


def test_adr_usa_calendario_de_su_ticker() -> None:
    actual = {date(2026, 9, 4), date(2026, 9, 8)}

    assert missing_sessions(actual, "NYSE", date(2026, 9, 4), date(2026, 9, 8)) == ()


def test_etf_xetra_sobre_sp500_usa_calendario_xetra() -> None:
    dates = expected_sessions("XETRA", date(2026, 3, 2), date(2026, 3, 10))
    freshness = calcular_frescura_serie(
        _ohlcv_for_dates(dates),
        datetime(2026, 3, 10, 20, 0, tzinfo=timezone.utc),
        market="XETRA",
        strength_benchmark="^GSPC",
    )

    assert freshness.absent_reference_sessions == ()
    assert freshness.calendar == "XETR"


def test_cripto_sabado_domingo_navidad_son_sesion() -> None:
    sessions = set(expected_sessions("CRYPTO", date(2025, 12, 25), date(2025, 12, 28)))

    assert {date(2025, 12, 25), date(2025, 12, 27), date(2025, 12, 28)} <= sessions


def test_plaza_desconocida_falla_ruidosamente() -> None:
    with pytest.raises(ValueError, match="plaza 'SIN_TABLA' sin calendario declarado"):
        expected_sessions("SIN_TABLA", date(2026, 1, 1), date(2026, 1, 2))


def test_brk_b_no_es_cripto() -> None:
    asset = Asset(
        symbol="BRK-B",
        name="Berkshire Hathaway",
        asset_class="stock",
        region="USA",
        market="NYSE",
        currency="USD",
        timezone="America/New_York",
        trade_republic="unknown",
    )

    assert mercado_para_simbolo(asset, "BRK-B") == "NYSE"


def test_sessions_approx_usa_calendario() -> None:
    history = _ohlcv_for_dates([date(2026, 9, 4)])
    reference = datetime(2026, 9, 8, 7, 0, tzinfo=timezone.utc)

    nyse = calcular_frescura_serie(history, reference, market="NYSE")
    xetra = calcular_frescura_serie(history, reference, market="XETRA")

    assert nyse.sessions_approx == 0
    assert xetra.sessions_approx == 1
