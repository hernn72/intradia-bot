"""Recorte de barras diarias no cerradas por plaza."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from advisor.data.sessions import MARKET_CLOSED, MARKET_OPEN, MARKET_PRE_OPEN, market_state, trim_unclosed_bar
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


def test_market_state_pre_open_open_y_closed_en_xetra() -> None:
    zone = ZoneInfo("Europe/Berlin")

    assert market_state("XETRA", datetime(2026, 9, 17, 8, 0, tzinfo=zone)) == MARKET_PRE_OPEN
    assert market_state("XETRA", datetime(2026, 9, 17, 12, 0, tzinfo=zone)) == MARKET_OPEN
    assert market_state("XETRA", datetime(2026, 9, 17, 19, 0, tzinfo=zone)) == MARKET_CLOSED


def test_media_sesion_no_recorta_una_barra_ya_cerrada() -> None:
    df = _daily_with_last("2026-12-24T05:00:00Z")
    reference = datetime(2026, 12, 24, 15, 0, tzinfo=ZoneInfo("America/New_York"))

    result = trim_unclosed_bar(df, market="NYSE", reference=reference, settlement_minutes=20)

    assert result.removed_last_bar is False
    assert len(result.df) == 3
    assert "cierre de sesión 13:00 America/New_York + 20 min" in result.status


def test_media_sesion_en_xetra_el_30_de_diciembre() -> None:
    df = _daily_with_last("2026-12-29T23:00:00Z")
    reference = datetime(2026, 12, 30, 15, 0, tzinfo=ZoneInfo("Europe/Berlin"))

    result = trim_unclosed_bar(df, market="XETRA", reference=reference, settlement_minutes=20)

    assert result.removed_last_bar is False
    assert len(result.df) == 3
    assert "cierre de sesión 14:00 Europe/Berlin + 20 min" in result.status


def test_market_state_en_fin_de_semana_es_closed() -> None:
    reference = datetime(2026, 9, 19, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))

    assert market_state("XETRA", reference) == MARKET_CLOSED


def test_cripto_siempre_open() -> None:
    reference = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)

    assert market_state("CRYPTO", reference) == MARKET_OPEN


def test_plaza_sin_horario_declarado_no_inventa_estado() -> None:
    reference = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)

    assert market_state("SIN_TABLA", reference) is None


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


def test_market_state_acepta_un_reference_sin_zona_horaria() -> None:
    """Regresión de la revisión de T-007.

    ``trim_unclosed_bar`` tolera un ``datetime`` sin zona desde siempre; si
    ``market_state`` no lo tolera, una llamada desde el informe rompe la
    generación entera en vez de degradar.
    """

    naive = datetime(2026, 9, 18, 12, 0)

    # El estado concreto depende de la zona horaria del sistema, igual que en
    # ``trim_unclosed_bar``; lo que el contrato garantiza es que no revienta y
    # que devuelve uno de los tres estados declarados.
    assert market_state("XETRA", naive) in (MARKET_PRE_OPEN, MARKET_OPEN, MARKET_CLOSED)
