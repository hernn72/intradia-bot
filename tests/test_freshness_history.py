from __future__ import annotations

from datetime import date, datetime

from advisor.freshness_history import (
    CauseCounts,
    FreshnessHistorySummary,
    RateCell,
    classify_absence_causes,
    format_freshness_history_summary,
    summarize_freshness_history,
)
from advisor.universe.models import Asset, Universe


def _asset(symbol: str, market: str = "XETRA", valid_to: date | None = None) -> Asset:
    return Asset(
        primary_symbol=symbol,
        primary_market=market,
        primary_currency="EUR",
        name=symbol,
        asset_class="stock",
        region="EUROPA",
        economic_currency="EUR",
        timezone="Europe/Berlin",
        trade_republic="unknown",
        isin=None,
        issuer_id=symbol.lower().replace(".", "-"),
        instrument_id=f"{symbol}@{market}",
        added_at=date(2026, 8, 27),
        valid_to=valid_to,
    )


def _universe(*assets: Asset) -> Universe:
    return Universe(groups={"test": list(assets)})


def _row(
    symbol: str = "SAP.DE",
    *,
    measured_at: str = "2026-09-02T07:00:00+00:00",
    market: str = "XETRA",
    sessions_approx: int = 0,
    partial: bool = False,
    absent: str = "[]",
    last_bar_date: str | None = "2026-09-01",
) -> dict[str, object]:
    return {
        "measured_at": measured_at,
        "symbol": symbol,
        "data_symbol": symbol,
        "market": market,
        "last_bar_date": last_bar_date,
        "sessions_approx": sessions_approx,
        "may_be_partial_current_session": int(partial),
        "absent_reference_sessions": absent,
        "quality": "OK",
        "error": None,
    }


def test_resumen_no_agrega_celdas_con_muestra_insuficiente() -> None:
    rows = [
        _row(measured_at=f"2026-09-02T07:{minute:02d}:00+00:00", sessions_approx=1)
        for minute in range(29)
    ]

    summary = summarize_freshness_history(rows, _universe(_asset("SAP.DE")))
    output = format_freshness_history_summary(summary)

    assert "insuficiente (29/29; n=29<30)" in output
    assert "100.0% (29/29)" not in output


def test_ausencia_con_override_no_cuenta_como_hueco() -> None:
    causes, provider_dates, closed_dates, delayed_dates = classify_absence_causes(
        _row(
            symbol="005930.KS",
            market="KSC",
            measured_at="2026-06-04T07:00:00+00:00",
            absent='["2026-06-03"]',
            last_bar_date="2026-06-02",
        ),
        measured_at=datetime.fromisoformat("2026-06-04T07:00:00+00:00"),
    )

    assert causes == CauseCounts(market_closed=1, provider_missing=0, partial_bar=0)
    assert provider_dates == set()
    assert closed_dates == {date(2026, 6, 3)}
    assert delayed_dates == set()


def test_celda_sin_mediciones_se_declara_vacia_y_no_cero() -> None:
    summary = FreshnessHistorySummary(
        total_measurements=0,
        total_passes=0,
        total_symbols=0,
        first_measured_at=None,
        last_measured_at=None,
        market_hour={},
        asset_months=[],
        asset_partials=[],
        weekdays={0: RateCell()},
        causes=CauseCounts(),
        causes_appearances=CauseCounts(),
        od02_assets_over_threshold=0,
        od02_assets_observed=0,
        od02_assets_persistent=0,
        od02_assets_with_persistent_gap=0,
        od02_assets_with_delays=0,
        historical_gaps=[],
        versions=[],
        populations=("107 analizables", "103 analizables", "93 analizables"),
        window_note="Ventana corta.",
    )

    output = format_freshness_history_summary(summary)

    assert "| lunes | n=0 | sin mediciones (n=0) | N/D |" in output
    assert "| lunes | n=0 | 0.0%" not in output


def test_porcentaje_siempre_va_con_denominador() -> None:
    rows = [
        _row(measured_at=f"2026-09-02T07:{minute:02d}:00+00:00", sessions_approx=int(minute < 15))
        for minute in range(30)
    ]

    summary = summarize_freshness_history(rows, _universe(_asset("SAP.DE")))
    output = format_freshness_history_summary(summary)

    assert "50.0% (15/30)" in output


def test_las_tres_causas_son_excluyentes() -> None:
    rows = [
        _row(
            symbol="005930.KS",
            market="KSC",
            measured_at="2026-06-04T07:00:00+00:00",
            absent='["2026-06-03"]',
            partial=True,
            last_bar_date="2026-06-02",
        ),
        _row(
            symbol="SAP.DE",
            market="XETRA",
            measured_at="2026-09-03T07:00:00+00:00",
            absent='["2026-09-02"]',
            partial=True,
            last_bar_date="2026-09-01",
        ),
        _row(
            symbol="ALV.DE",
            market="XETRA",
            measured_at="2026-09-03T07:00:00+00:00",
            partial=True,
            last_bar_date="2026-09-03",
        ),
    ]

    summary = summarize_freshness_history(
        rows,
        _universe(_asset("005930.KS", "KSC"), _asset("SAP.DE"), _asset("ALV.DE")),
    )

    assert summary.causes == CauseCounts(market_closed=1, provider_missing=1, partial_bar=1)
    assert summary.causes.total == 3


def test_una_ausencia_repetida_en_varias_pasadas_cuenta_una_vez() -> None:
    """El defecto que la primera entrega tenia: `absent_reference_sessions` mira

    200 sesiones atras, asi que la misma sesion ausente reaparece en todas las
    pasadas. Sumarla una vez por pasada multiplicaba el hueco por 3 aqui, y por
    39 sobre el historico real de la Pi.
    """
    rows = [
        _row(
            measured_at=f"2026-09-0{day}T07:00:00+00:00",
            absent='["2026-09-04"]',
            last_bar_date="2026-09-03",
        )
        for day in (4, 7, 8)
    ]

    summary = summarize_freshness_history(rows, _universe(_asset("SAP.DE")))
    septiembre = [item for item in summary.asset_months if item.month == "2026-09"]

    assert len(septiembre) == 1
    assert septiembre[0].provider_missing_sessions == 1
    assert septiembre[0].provider_missing_appearances == 3


def test_hueco_anterior_a_la_ventana_no_es_sesion_perdida_de_la_ventana() -> None:
    rows = [
        _row(measured_at="2026-09-03T07:00:00+00:00", absent='["2026-03-06"]', last_bar_date="2026-09-02"),
        _row(measured_at="2026-09-04T07:00:00+00:00", absent='["2026-03-06"]', last_bar_date="2026-09-03"),
    ]

    summary = summarize_freshness_history(rows, _universe(_asset("SAP.DE")))

    assert [gap.symbol for gap in summary.historical_gaps] == ["SAP.DE"]
    assert summary.historical_gaps[0].sessions == 1
    assert all(item.provider_missing_sessions == 0 for item in summary.asset_months)


def test_hueco_que_se_rellena_despues_no_cuenta_como_persistente() -> None:
    rows = [
        _row(measured_at="2026-09-04T07:00:00+00:00", absent='["2026-09-04"]', last_bar_date="2026-09-03"),
        _row(measured_at="2026-09-07T07:00:00+00:00", absent="[]", last_bar_date="2026-09-07"),
    ]

    summary = summarize_freshness_history(rows, _universe(_asset("SAP.DE")))

    assert summary.od02_assets_with_persistent_gap == 0
    assert summary.asset_months[0].provider_missing_sessions == 1


def test_el_resumen_declara_las_versiones_de_codigo() -> None:
    vieja = _row(measured_at="2026-09-03T07:00:00+00:00", last_bar_date="2026-09-02")
    vieja["run_git_sha"] = "a" * 40
    vieja["run_release_tag"] = None
    nueva = _row(measured_at="2026-09-20T16:00:00+00:00", last_bar_date="2026-09-18")
    nueva["run_git_sha"] = "b" * 40
    nueva["run_release_tag"] = "v0.3.0"

    summary = summarize_freshness_history([vieja, nueva], _universe(_asset("SAP.DE")))
    output = format_freshness_history_summary(summary)

    assert len(summary.versions) == 2
    assert "bbbbbbbbbbbb (v0.3.0)" in output
    assert "AVISO: la ventana cruza 2 versiones de codigo" in output


def test_el_porcentaje_declara_cuantas_pasadas_lo_generan() -> None:
    """D-41 / INV-22: 30 filas de una sola pasada son un evento, no 30 observaciones."""
    rows = [
        _row(symbol=f"SYM{index}.DE", measured_at="2026-09-03T06:00:00+00:00", sessions_approx=1)
        for index in range(30)
    ]

    summary = summarize_freshness_history(rows, _universe(*[_asset(f"SYM{i}.DE") for i in range(30)]))
    output = format_freshness_history_summary(summary)

    assert summary.market_hour[("XETRA", 6)].passes == 1
    assert "100.0% (30/30) en 1 pasadas" in output
    assert "NO independiente: 1 pasadas" in output
