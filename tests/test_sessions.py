"""Recorte de barras diarias no cerradas por plaza."""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from advisor.data.sessions import (
    MARKET_CLOSED,
    MARKET_OPEN,
    MARKET_PRE_OPEN,
    latest_expected_closed_session,
    market_state,
    trim_unclosed_bar,
)
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


def test_cripto_recorta_la_barra_del_dia_en_curso() -> None:
    """Una plaza 24/7 no tiene hora de cierre, pero sus barras diarias sí cierran.

    Antes de D-37 esto devolvía «sin sesión de cierre» y dejaba la barra en
    curso dentro de la serie: los indicadores se calculaban con una vela a
    medias y la cripto quedaba vetada para siempre como `PARTIAL_BAR`. La barra
    del día D cierra a las 00:00 UTC del día siguiente, así que a las 08:00 del
    día 2 la última cerrada exigible es la del día 1.
    """

    df = _daily_with_last("2026-09-02T00:00:00Z")
    reference = datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc)

    result = trim_unclosed_bar(df, market="CRYPTO", reference=reference, settlement_minutes=20)

    assert result.removed_last_bar is True
    assert len(result.df) == len(df) - 1
    assert "2026-09-01" in result.status


def test_cripto_no_recorta_una_barra_ya_cerrada() -> None:
    """A las 00:30 UTC del día 2, la barra del día 1 ya cerró y se queda."""

    df = _daily_with_last("2026-09-01T00:00:00Z")
    reference = datetime(2026, 9, 2, 0, 30, tzinfo=timezone.utc)

    result = trim_unclosed_bar(df, market="CRYPTO", reference=reference, settlement_minutes=20)

    assert result.removed_last_bar is False
    assert len(result.df) == len(df)


def test_la_ultima_sesion_cerrada_exigible_depende_de_la_plaza_y_de_la_hora() -> None:
    """La frontera no es «hoy»: es el cierre de cada plaza (D-36).

    A las 07:00 de Londres la sesión europea de ayer ya cerró —su barra es
    exigible— y la estadounidense de hoy ni siquiera ha abierto.
    """

    manana = datetime(2026, 9, 18, 6, 0, tzinfo=timezone.utc)  # 07:00 BST

    assert latest_expected_closed_session("XETRA", manana, settlement_minutes=20) == date(2026, 9, 17)
    assert latest_expected_closed_session("NYSE", manana, settlement_minutes=20) == date(2026, 9, 17)
    assert latest_expected_closed_session("CRYPTO", manana, settlement_minutes=20) == date(2026, 9, 17)
    # Tokio cierra a las 15:30 JST, que son las 06:30 UTC: a las 06:00 la sesión
    # de hoy sigue abierta, y a las 07:00 ya es exigible.
    assert latest_expected_closed_session("JPX", manana, settlement_minutes=20) == date(2026, 9, 17)
    despues_de_tokio = datetime(2026, 9, 18, 7, 0, tzinfo=timezone.utc)
    assert latest_expected_closed_session("JPX", despues_de_tokio, settlement_minutes=20) == date(2026, 9, 18)

    # Por la tarde, Europa ya ha cerrado hoy; Nueva York no.
    tarde = datetime(2026, 9, 18, 16, 0, tzinfo=timezone.utc)  # 17:00 BST
    assert latest_expected_closed_session("XETRA", tarde, settlement_minutes=20) == date(2026, 9, 18)
    assert latest_expected_closed_session("NYSE", tarde, settlement_minutes=20) == date(2026, 9, 17)


def test_la_sesion_estadounidense_de_hoy_es_exigible_pasado_su_cierre() -> None:
    """El caso que pidió comprobar el propietario: la pasada de las 21:00.

    A las 21:00 BST (20:00 UTC) Nueva York está cerrando justo en ese instante,
    así que su sesión de hoy **todavía no** es exigible. Media hora después sí,
    y a partir de ahí que falte la barra de hoy es un dato retrasado.
    """

    cierre_justo = datetime(2026, 9, 18, 20, 0, tzinfo=timezone.utc)
    assert latest_expected_closed_session("NYSE", cierre_justo, settlement_minutes=20) == date(2026, 9, 17)

    media_hora_despues = datetime(2026, 9, 18, 20, 30, tzinfo=timezone.utc)
    assert latest_expected_closed_session("NYSE", media_hora_despues, settlement_minutes=20) == date(2026, 9, 18)


def test_una_plaza_sin_calendario_no_supone_que_esta_al_dia() -> None:
    """INV-16: si no se puede determinar la frontera, se dice, no se inventa."""

    assert latest_expected_closed_session("CBOE", datetime(2026, 9, 18, 16, 0, tzinfo=timezone.utc)) is None


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
