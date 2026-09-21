"""Gate P2.5 de capacidad estadística."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

import advisor.research.capacity as capacity
from advisor.research.capacity import INSUFICIENTE, assess_capacity, format_capacity_report
from advisor.research.event_study import AMBIGUOUS, STOP_FIRST, TARGET_FIRST, EventStudyResult, band_of_full_score
from advisor.research.timestamps import parse_timestamp
from advisor.universe.models import Asset, Universe
from tests.test_event_study import _signal


def test_banda_80_no_calibra_threshold_con_pocas_observaciones() -> None:
    signals = [
        _with_day(_signal(score=85.0, status="TARGET_FIRST" if i < 40 else "STOP_FIRST"), i)
        for i in range(78)
    ]
    result = _result(signals)

    report = assess_capacity(result, universe=_universe())
    by_label = {summary.label: summary for summary in report.bands}

    assert by_label["80+"].verdict == INSUFICIENTE
    assert by_label["80+"].nominal_n == 78
    assert by_label["80+"].n_blocks == 2
    assert by_label["80+"].block_length == 60
    assert by_label["80+"].interval_width > 0
    assert by_label["80+"].conclusive is False
    assert "no se permite calibrar un threshold apoyándose en 80+" in format_capacity_report(report)


def test_capacidad_distingue_global_banda_y_comparacion() -> None:
    signals = []
    for i in range(180):
        signal = _with_day(_signal(score=55.0, status="TARGET_FIRST"), i)
        object.__setattr__(signal.observation, "signal_idx", i)
        signals.append(signal)
    for i in range(180):
        signal = _with_day(_signal(score=85.0, status="STOP_FIRST"), i)
        object.__setattr__(signal.observation, "signal_idx", i)
        signals.append(signal)

    result = _result(signals)

    report = assess_capacity(result, universe=_universe())
    by_label = {summary.label: summary for summary in report.bands}

    assert report.global_summary.verdict == INSUFICIENTE
    assert by_label["50-60"].nominal_n == 180
    assert by_label["80+"].nominal_n == 180
    assert report.comparisons[0].label == "50-60 vs 80+"
    assert report.comparisons[0].conclusive is False


def test_bloques_son_temporales_y_no_activo_por_tiempo() -> None:
    signals = []
    for day in range(80):
        for asset in ("A", "B", "C"):
            signal = _with_day(_signal(score=55.0, status="TARGET_FIRST"), day)
            object.__setattr__(signal.observation, "asset", asset)
            signals.append(signal)

    result = _result(signals)

    report = assess_capacity(result, universe=_universe("A", "B", "C"))

    assert report.global_summary.nominal_n == 240
    assert report.global_summary.n_blocks == 2


def test_assess_capacity_por_defecto_no_cambia() -> None:
    signals = [_with_day(_signal(score=55.0 if i < 120 else 85.0, status="TARGET_FIRST"), i) for i in range(240)]
    result = _result(signals)

    assert assess_capacity(result, universe=_universe()) == assess_capacity(
        result,
        universe=_universe(),
        band_of=band_of_full_score,
    )


def test_gate_cuenta_ambiguous_como_cota_inferior_no_como_resultado_resuelto() -> None:
    signals = [
        _signal(score=55.0, status=TARGET_FIRST),
        _signal(score=55.0, status=AMBIGUOUS),
        _signal(score=55.0, status=STOP_FIRST),
    ]

    assert capacity._target_first(signals) == 1
    assert "cota inferior" in capacity._target_first.__doc__


def test_intervalo_de_capacidad_delega_en_bootstrap_p26() -> None:
    block_rates = [(0.2, 10), (0.4, 10), (0.8, 10), (0.6, 10)]

    assert capacity._block_mean_interval(block_rates) == capacity.bootstrap_block_mean_interval(
        block_rates,
        seed=capacity.DEFAULT_SEED,
        n_resamples=capacity.DEFAULT_RESAMPLES,
        confidence=0.95,
    )


def test_capacidad_publica_estimador_primario_y_secundarios() -> None:
    signals = [
        _with_day(_signal(score=55.0, status=TARGET_FIRST), 0),
        _with_day(_signal(score=55.0, status=capacity.STOP_FIRST), 1),
        _with_day(_signal(score=55.0, status=capacity.AMBIGUOUS), 2),
    ]
    report = assess_capacity(_result(signals), universe=_universe())
    salida = format_capacity_report(report)

    assert "Estimadores pre-registrados 2026-09-02" in salida
    assert "Primario: media por bloque de expectancy neta en R" in salida
    assert "Secundarios: tasa agrupada expectancy neta en R" in salida
    assert "P(objetivo antes de stop)" in salida


def test_intervalo_primario_por_banda_se_calcula_sobre_bloques() -> None:
    """El primario es la media SIMPLE entre bloques, no la media agrupada.

    Los bloques llevan a proposito tamanos distintos —tres señales frente a
    una—, porque con bloques del mismo tamano las dos medias coinciden y el
    test no distinguiria el estimador pre-registrado de su sustituto:

        media por bloque  = (0,50 + (-0,10)) / 2               = 0,200
        media agrupada    = (0,50 + 0,50 + 0,50 - 0,10) / 4    = 0,350
    """

    signals = [
        _with_net_r(_with_day(_signal(score=55.0, status=TARGET_FIRST), day), 0.50)
        for day in (0, 1, 2)
    ]
    signals.append(_with_net_r(_with_day(_signal(score=55.0, status=TARGET_FIRST), 61), -0.10))
    result = _result(signals)
    result = replace(
        result,
        session_dates_by_asset={"TEST": tuple(_session_date(day) for day in range(62))},
    )
    report = assess_capacity(result, universe=_universe())
    band = {summary.label: summary for summary in report.bands}["50-60"]

    assert band.n_blocks == 2
    assert band.primary_expectancy_net_r == pytest.approx(0.200)
    # La media agrupada valdria 0,350: si alguien sustituye el estimador, aqui salta.
    assert band.primary_expectancy_net_r != pytest.approx(0.350)
    # Y tampoco puede ser la tasa TARGET_FIRST, que con estas señales vale 1,0.
    assert band.secondary_target_first_interval_lower == pytest.approx(1.0)
    assert band.primary_interval_lower != pytest.approx(band.secondary_target_first_interval_lower)


def test_un_bloque_temporal_parcial_invalida_la_capacidad_del_horizonte() -> None:
    """P2.5: el bloque debe SUPERAR `MAX_HOLD_BARS`, y sobre la ventana REAL.

    El ultimo bloque de la espina es el resto de la division y puede quedarse
    corto. Los dos casos que fija el protocolo, con numeros cerrados:

        swing  ultimo bloque  42 sesiones > MAX_HOLD_BARS  40  -> NO invalida
        medio  ultimo bloque 102 sesiones < MAX_HOLD_BARS 250  -> INSUFFICIENT
    """

    # SWING: espina de 60 + 42 sesiones, señales en los dos bloques.
    signals = [
        _with_net_r(_with_day(_signal(score=55.0, status=TARGET_FIRST), day), 0.20)
        for day in (0, 1, 61, 62)
    ]
    swing = replace(
        _result(signals),
        session_dates_by_asset={"TEST": tuple(_session_date(day) for day in range(102))},
    )
    resumen_swing = assess_capacity(swing, universe=_universe()).global_summary

    assert resumen_swing.resolution != capacity.RESOLUTION_INSUFFICIENT
    assert not any("bloque temporal parcial" in motivo for motivo in resumen_swing.reasons)

    # MEDIO: bloque nominal 300, MAX_HOLD_BARS 250, espina de 300 + 102.
    # Las señales tienen que CAER en el bloque parcial: un bloque vacio no
    # alimenta la media por bloque y por tanto no puede invalidarla.
    signals_medio = [
        _with_net_r(_with_day(_signal(score=55.0, status=TARGET_FIRST), day), 0.20)
        for day in (0, 1, 300, 301)
    ]
    medio = replace(
        _result(signals_medio),
        horizonte="medio",
        max_hold_bars=250,
        session_dates_by_asset={"TEST": tuple(_session_date(day) for day in range(402))},
    )
    resumen_medio = assess_capacity(medio, universe=_universe()).global_summary

    assert resumen_medio.resolution == capacity.RESOLUTION_INSUFFICIENT
    assert resumen_medio.conclusive is False
    assert any(
        "bloque temporal parcial 102 sesiones < MAX_HOLD_BARS 250" in motivo
        for motivo in resumen_medio.reasons
    ), resumen_medio.reasons
    # La materia prima se conserva; lo que se niega es su uso para concluir.
    assert resumen_medio.nominal_n == 4
    assert resumen_medio.primary_expectancy_net_r == pytest.approx(0.20)


def test_el_informe_nunca_publica_el_secundario_sin_el_primario() -> None:
    report = assess_capacity(_result([_with_day(_signal(score=55.0, status=TARGET_FIRST), 0)]), universe=_universe())
    roto = replace(report, estimators=None)

    with pytest.raises(ValueError, match="INV-14"):
        format_capacity_report(roto)


def test_desglose_por_region_suma_la_poblacion() -> None:
    signals = []
    for asset, day in (("A", 0), ("B", 1), ("C", 61)):
        signal = _with_day(_signal(score=55.0, status=TARGET_FIRST), day)
        object.__setattr__(signal.observation, "asset", asset)
        signals.append(signal)
    report = assess_capacity(_result(signals), universe=_universe("A", "B", "C", regions=("USA", "EUROPA", "USA")))

    rows = report.estimators.primary_by_region
    assert report.estimators is not None
    assert sum(row.n for row in rows) == report.estimators.n_observable
    assert {row.label: row.n for row in rows} == {"EUROPA": 1, "USA": 2}


def test_tasa_de_censura_exit_final_se_publica_por_corte() -> None:
    signals = [_with_day(_signal(score=55.0, status=TARGET_FIRST), 0)]
    signal = signals[0]
    censored = replace(signal.managed, exit_status=capacity.FINAL_EXIT, net_r_multiple=0.0)
    signals.append(replace(_with_day(_signal(score=85.0, status=TARGET_FIRST), 1), managed=censored))

    salida = format_capacity_report(assess_capacity(_result(signals), universe=_universe()))

    assert "Score 50-60" in salida
    assert "Score 80+" in salida
    assert "EXIT_FINAL=0.000" in salida
    assert "EXIT_FINAL=1.000" in salida


def test_plaza_sin_zona_falla_ruidosamente() -> None:
    signal = _with_day(_signal(score=55.0, status=TARGET_FIRST), 0)
    universe = _universe(market="SIN_TABLA")
    result = _result([signal])

    with pytest.raises(ValueError, match="plaza 'SIN_TABLA' sin cierre regular declarado"):
        assess_capacity(result, universe=universe)


def _with_day(signal, day: int):
    timestamp = parse_timestamp("2026-01-05T00:00:00Z") + timedelta(days=_business_day_offset(day))
    raw = timestamp.isoformat().replace("+00:00", "Z")
    object.__setattr__(signal.observation, "signal_timestamp", timestamp)
    object.__setattr__(signal.observation, "signal_timestamp_raw", raw)
    return signal


def _session_date(day: int) -> date:
    return (parse_timestamp("2026-01-05T00:00:00Z") + timedelta(days=_business_day_offset(day))).date()


def _with_net_r(signal, value: float):
    return replace(signal, managed=replace(signal.managed, net_r_multiple=value))


def _business_day_offset(index: int) -> int:
    day = date(2026, 1, 5)
    offset = 0
    seen = 0
    while seen < index:
        offset += 1
        if (day + timedelta(days=offset)).weekday() < 5:
            seen += 1
    return offset


def _result(signals) -> EventStudyResult:
    assets = sorted({signal.observation.asset for signal in signals})
    session_dates_by_asset = {
        asset: tuple(
            sorted({
                signal.observation.signal_timestamp.date()
                for signal in signals
                if signal.observation.asset == asset
            })
        )
        for asset in assets
    }
    return EventStudyResult(
        data_vintage_id="vintage",
        horizonte="swing",
        cost_pct=0.2,
        warmup_bars=120,
        max_hold_bars=40,
        signals=list(signals),
        evaluated_assets=assets,
        asset_bar_counts=dict.fromkeys(assets, 1255),
        session_dates_by_asset=session_dates_by_asset,
    )


def _universe(*symbols: str, market: str = "XETRA", regions: tuple[str, ...] | None = None) -> Universe:
    if not symbols:
        symbols = ("TEST",)
    if regions is None:
        regions = tuple("EUROPA" for _ in symbols)
    assets = [
        Asset(
            primary_symbol=symbol,
            primary_market=market,
            primary_currency="EUR",
            name=symbol,
            asset_class="stock",
            region=region,
            economic_currency="EUR",
            timezone="Europe/Berlin",
            isin=None,
            requires_isin=True,
        )
        for symbol, region in zip(symbols, regions)
    ]
    return Universe(groups={"test": assets})
