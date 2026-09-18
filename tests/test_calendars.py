"""Calendarios de plaza para frescura de datos."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import pytest

import advisor.data.calendars as calendars
from advisor.data.calendars import closed_sessions_between, expected_sessions, load_exchange_overrides, missing_sessions
from advisor.data.freshness import calcular_frescura_serie, mercado_para_simbolo
from advisor.universe.models import Asset


def _ohlcv_for_dates(values: list[date]) -> pd.DataFrame:
    # Marcas **sin zona**, que es como sirve el proveedor el histórico diario en
    # vivo. Con `tz="UTC"` una barra de NYSE a las 00:00Z serían las 20:00 del
    # día anterior en Nueva York y pertenecería a otra sesión: la misma serie no
    # puede valer para dos plazas si lleva zona.
    index = pd.DatetimeIndex([pd.Timestamp(value) for value in values])
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


def test_benchmark_no_es_calendario() -> None:
    history = _ohlcv_for_dates([date(2026, 9, 4), date(2026, 9, 8)])
    freshness = calcular_frescura_serie(
        history,
        datetime(2026, 9, 8, 20, 0, tzinfo=timezone.utc),
        market="NYSE",
        strength_benchmark="^GDAXI",
    )

    assert freshness.calendar == "XNYS"
    assert freshness.strength_benchmark == "^GDAXI"
    assert freshness.absent_reference_sessions == ()


def test_festivo_no_es_sesion_ausente() -> None:
    dates = expected_sessions("XETRA", date(2026, 4, 1), date(2026, 4, 8))
    freshness = calcular_frescura_serie(
        _ohlcv_for_dates(dates),
        datetime(2026, 4, 8, 20, 0, tzinfo=timezone.utc),
        market="XETRA",
        strength_benchmark="^GSPC",
    )

    assert date(2026, 4, 3) not in dates
    assert date(2026, 4, 3) not in freshness.absent_reference_sessions


def test_sesion_de_benchmark_extranjero_no_exige_vela() -> None:
    xetra_dates = expected_sessions("XETRA", date(2026, 4, 2), date(2026, 4, 7))
    freshness = calcular_frescura_serie(
        _ohlcv_for_dates(xetra_dates),
        datetime(2026, 4, 7, 20, 0, tzinfo=timezone.utc),
        market="XETRA",
        strength_benchmark="^GSPC",
    )

    assert date(2026, 4, 6) in expected_sessions("NYSE", date(2026, 4, 6), date(2026, 4, 6))
    assert date(2026, 4, 6) not in xetra_dates
    assert date(2026, 4, 6) not in freshness.absent_reference_sessions


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


def test_xkrx_aplica_cierres_adicionales_declarados() -> None:
    sessions = set(expected_sessions("KSC", date(2026, 6, 1), date(2026, 7, 20)))

    assert date(2026, 6, 3) not in sessions
    assert date(2026, 7, 17) not in sessions
    assert date(2026, 6, 4) in sessions


def test_override_no_afecta_otras_plazas() -> None:
    assert date(2026, 6, 3) in set(expected_sessions("XETRA", date(2026, 6, 1), date(2026, 6, 5)))


def test_override_falta_fuente_falla_ruidosamente(tmp_path) -> None:
    path = tmp_path / "exchange_overrides.yaml"
    path.write_text(
        """
XKRX:
  cierres_adicionales:
    - fecha: 2026-06-03
      motivo: elecciones
      verificado_el: 2026-09-16
  aperturas_forzadas: []
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"falta fuente en XKRX.cierres_adicionales\[1\]"):
        load_exchange_overrides(path)


def test_override_falta_verificado_el_falla_ruidosamente(tmp_path) -> None:
    path = tmp_path / "exchange_overrides.yaml"
    path.write_text(
        """
XKRX:
  cierres_adicionales:
    - fecha: 2026-06-03
      motivo: elecciones
      fuente: https://example.test
  aperturas_forzadas: []
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"falta verificado_el en XKRX.cierres_adicionales\[1\]"):
        load_exchange_overrides(path)


def test_override_mic_desconocido_falla_ruidosamente(tmp_path) -> None:
    path = tmp_path / "exchange_overrides.yaml"
    path.write_text(
        """
NOPE:
  cierres_adicionales: []
  aperturas_forzadas: []
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="MIC desconocido en overrides: NOPE"):
        load_exchange_overrides(path)


def test_override_con_mic_duplicado_falla_ruidosamente(tmp_path) -> None:
    path = tmp_path / "exchange_overrides.yaml"
    path.write_text(
        """
XKRX:
  cierres_adicionales:
    - fecha: 2026-06-03
      motivo: cierre
      fuente: https://example.test/cierre
      verificado_el: 2026-09-16
  aperturas_forzadas: []
XKRX:
  cierres_adicionales:
    - fecha: 2026-07-17
      motivo: cierre
      fuente: https://example.test/cierre-2
      verificado_el: 2026-09-16
  aperturas_forzadas: []
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"clave duplicada.*XKRX"):
        load_exchange_overrides(path)


def test_override_con_clave_duplicada_en_entrada_falla_ruidosamente(tmp_path) -> None:
    path = tmp_path / "exchange_overrides.yaml"
    path.write_text(
        """
XKRX:
  cierres_adicionales:
    - fecha: 2026-06-03
      fecha: 2026-07-17
      motivo: cierre
      fuente: https://example.test/cierre
      verificado_el: 2026-09-16
  aperturas_forzadas: []
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"clave duplicada.*fecha"):
        load_exchange_overrides(path)


@pytest.mark.parametrize("raw_fecha", ["20260603", "06/03/2026"])
def test_override_fecha_no_iso_falla_ruidosamente(tmp_path, raw_fecha: str) -> None:
    path = tmp_path / "exchange_overrides.yaml"
    path.write_text(
        f"""
XKRX:
  cierres_adicionales:
    - fecha: {raw_fecha}
      motivo: cierre
      fuente: https://example.test/cierre
      verificado_el: 2026-09-16
  aperturas_forzadas: []
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"fecha no es una fecha ISO valida"):
        load_exchange_overrides(path)


def test_override_verificado_el_no_iso_falla_ruidosamente(tmp_path) -> None:
    path = tmp_path / "exchange_overrides.yaml"
    path.write_text(
        """
XKRX:
  cierres_adicionales:
    - fecha: 2026-06-03
      motivo: cierre
      fuente: https://example.test/cierre
      verificado_el: 09/16/2026
  aperturas_forzadas: []
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"verificado_el no es una fecha ISO valida"):
        load_exchange_overrides(path)


def test_override_fecha_en_dos_listas_falla_ruidosamente(tmp_path) -> None:
    path = tmp_path / "exchange_overrides.yaml"
    path.write_text(
        """
XKRX:
  cierres_adicionales:
    - fecha: 2026-06-03
      motivo: cierre
      fuente: https://example.test/cierre
      verificado_el: 2026-09-16
  aperturas_forzadas:
    - fecha: 2026-06-03
      motivo: apertura
      fuente: https://example.test/apertura
      verificado_el: 2026-09-16
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="XKRX tiene fechas en ambas listas: 2026-06-03"):
        load_exchange_overrides(path)


def test_aperturas_forzadas_aniade_sesion(monkeypatch, tmp_path) -> None:
    path = tmp_path / "exchange_overrides.yaml"
    path.write_text(
        """
XETR:
  cierres_adicionales: []
  aperturas_forzadas:
    - fecha: 2026-04-04
      motivo: prueba de apertura extraordinaria
      fuente: https://example.test/apertura
      verificado_el: 2026-09-16
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(calendars, "EXCHANGE_OVERRIDES_PATH", path)
    calendars._load_exchange_overrides.cache_clear()

    assert date(2026, 4, 4) in set(expected_sessions("XETRA", date(2026, 4, 3), date(2026, 4, 6)))


def test_missing_sessions_y_closed_sessions_respetan_override() -> None:
    actual = {date(2026, 6, 2), date(2026, 6, 4)}

    assert missing_sessions(actual, "KSC", date(2026, 6, 2), date(2026, 6, 4)) == ()
    assert closed_sessions_between(date(2026, 6, 2), date(2026, 6, 4), "KSC") == 0


def test_fichero_de_correcciones_ausente_falla_ruidosamente(monkeypatch, tmp_path) -> None:
    """Su ausencia no puede significar «sin correcciones»: devolvería los huecos falsos."""

    monkeypatch.setattr(calendars, "EXCHANGE_OVERRIDES_PATH", tmp_path / "no-existe.yaml")
    calendars._load_exchange_overrides.cache_clear()

    with pytest.raises(FileNotFoundError, match="correcciones de calendario"):
        expected_sessions("KSC", date(2026, 6, 1), date(2026, 6, 10))


@pytest.mark.parametrize("content", ["", "# conflicto resuelto dejando solo comentarios\n"])
def test_fichero_de_correcciones_vacio_falla_ruidosamente(tmp_path, content: str) -> None:
    path = tmp_path / "exchange_overrides.yaml"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="fichero de correcciones vacio"):
        load_exchange_overrides(path)


def test_apertura_forzada_de_un_dia_que_ya_es_sesion_falla_ruidosamente(monkeypatch, tmp_path) -> None:
    """Una entrada que no corrige nada es un error de declaración, no un no-op."""

    path = tmp_path / "exchange_overrides.yaml"
    path.write_text(
        """
XETR:
  cierres_adicionales: []
  aperturas_forzadas:
    - fecha: 2026-06-04
      motivo: jueves normal, el calendario ya lo da por sesión
      fuente: https://example.test/error
      verificado_el: 2026-09-16
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(calendars, "EXCHANGE_OVERRIDES_PATH", path)
    calendars._load_exchange_overrides.cache_clear()

    with pytest.raises(ValueError, match="ya la considera sesión"):
        expected_sessions("XETRA", date(2026, 6, 1), date(2026, 6, 10))


def test_apertura_forzada_fuera_del_rango_del_calendario_falla_ruidosamente(monkeypatch, tmp_path) -> None:
    path = tmp_path / "exchange_overrides.yaml"
    path.write_text(
        """
XETR:
  cierres_adicionales: []
  aperturas_forzadas:
    - fecha: 1985-01-02
      motivo: anterior a la primera sesión del calendario
      fuente: https://example.test/fuera-de-rango
      verificado_el: 2026-09-16
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(calendars, "EXCHANGE_OVERRIDES_PATH", path)
    calendars._load_exchange_overrides.cache_clear()

    with pytest.raises(ValueError, match="fuera del rango del calendario"):
        expected_sessions("XETRA", date(2026, 6, 1), date(2026, 6, 10))


def test_cierre_adicional_en_dia_no_sesion_falla_ruidosamente(tmp_path) -> None:
    path = tmp_path / "exchange_overrides.yaml"
    path.write_text(
        """
XETR:
  cierres_adicionales:
    - fecha: 2026-06-06
      motivo: sabado
      fuente: https://example.test/sabado
      verificado_el: 2026-09-16
  aperturas_forzadas: []
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="XETR declara un cierre adicional el 2026-06-06"):
        load_exchange_overrides(path)


def test_cierre_adicional_fuera_del_rango_del_calendario_falla_ruidosamente(tmp_path) -> None:
    path = tmp_path / "exchange_overrides.yaml"
    path.write_text(
        """
XETR:
  cierres_adicionales:
    - fecha: 1850-01-02
      motivo: demasiado antigua
      fuente: https://example.test/antigua
      verificado_el: 2026-09-16
  aperturas_forzadas: []
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="fuera del rango del calendario"):
        load_exchange_overrides(path)


def test_override_de_crypto_no_revienta_con_invalid_calendar_name(tmp_path) -> None:
    path = tmp_path / "exchange_overrides.yaml"
    path.write_text(
        """
CRYPTO_24_7:
  cierres_adicionales: []
  aperturas_forzadas:
    - fecha: 2026-06-03
      motivo: prueba
      fuente: https://example.test/crypto
      verificado_el: 2026-09-16
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"CRYPTO_24_7.*apertura forzada"):
        load_exchange_overrides(path)
