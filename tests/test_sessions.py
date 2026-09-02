"""Recorte de barras diarias no cerradas por plaza."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from advisor.data.sessions import trim_unclosed_bar
from tests.conftest import make_ohlcv


def _daily_with_last(timestamp: str) -> pd.DataFrame:
    df = make_ohlcv(n=3, start_date="2026-09-01")
    return df.set_axis(
        pd.DatetimeIndex([
            pd.Timestamp("2026-08-30T22:00:00Z"),
            pd.Timestamp("2026-08-31T22:00:00Z"),
            pd.Timestamp(timestamp),
        ])
    )


def test_europa_recorta_antes_de_cierre_mas_margen() -> None:
    df = _daily_with_last("2026-09-01T22:00:00Z")
    reference = datetime(2026, 9, 2, 15, 0, tzinfo=timezone.utc)

    result = trim_unclosed_bar(df, market="XETRA", reference=reference, settlement_minutes=20)

    assert result.removed_last_bar is True
    assert len(result.df) == 2
    assert "recortada" in result.status


def test_eeuu_recorta_antes_de_cierre_mas_margen() -> None:
    df = _daily_with_last("2026-09-02T04:00:00Z")
    reference = datetime(2026, 9, 2, 18, 30, tzinfo=timezone.utc)

    result = trim_unclosed_bar(df, market="NASDAQ", reference=reference, settlement_minutes=20)

    assert result.removed_last_bar is True
    assert len(result.df) == 2


def test_asia_no_recorta_si_el_cierre_mas_margen_ya_paso() -> None:
    df = _daily_with_last("2026-09-01T15:00:00Z")
    reference = datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc)

    result = trim_unclosed_bar(df, market="JPX", reference=reference, settlement_minutes=20)

    assert result.removed_last_bar is False
    assert len(result.df) == 3
    assert "última barra cerrada" in result.status


def test_cripto_no_recorta_y_declara_sin_sesion_de_cierre() -> None:
    df = _daily_with_last("2026-09-02T00:00:00Z")
    reference = datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc)

    result = trim_unclosed_bar(df, market="CRYPTO", reference=reference, settlement_minutes=20)

    assert result.removed_last_bar is False
    assert result.df is df
    assert result.status == "sin sesión de cierre"


def test_plaza_sin_declarar_falla_ruidosamente() -> None:
    with pytest.raises(ValueError, match="plaza 'SIN_TABLA' sin cierre regular declarado"):
        trim_unclosed_bar(make_ohlcv(n=3), market="SIN_TABLA", reference=datetime.now(timezone.utc), settlement_minutes=20)
