"""Tests del event study P2.3."""

from __future__ import annotations

import pandas as pd
import pytest

from advisor.analysis.levels import Levels
from advisor.research.event_study import (
    AMBIGUOUS,
    STOP_FIRST,
    TARGET_FIRST,
    EventStudySignal,
    PotentialEvent,
    classify_target_stop_bar,
    evaluate_managed_event,
    evaluate_potential_event,
    event_economics,
    summarize_by_score_band,
)
from advisor.research.observations import SignalObservation, stable_signal_id


def _levels(price: float = 100.0, stop: float = 95.0, target: float = 110.0) -> Levels:
    return Levels(
        price=price,
        entry_ideal_low=price,
        entry_ideal_high=price,
        entry_max=price,
        stop=stop,
        invalidation_level=None,
        invalidation_reason="test",
        stop_basis="test",
        target1=105.0,
        target2=target,
        target3=115.0,
        risk_pp=(price - stop) / price * 100,
        reward_pct=(target / price - 1) * 100,
        rr_ratio=(target - price) / (price - stop),
        extension_atr=None,
        chase=False,
    )


def _observation(score: float = 85.0) -> SignalObservation:
    timestamp = pd.Timestamp("2026-01-01", tz="UTC")
    return SignalObservation(
        signal_id=stable_signal_id("TEST", "swing", timestamp),
        data_vintage_id="vintage",
        asset="TEST",
        horizonte="swing",
        signal_idx=0,
        signal_timestamp=timestamp,
        score_value=score,
        evaluable_max=80.0,
        dimensions=(),
        price=100.0,
        atr=2.5,
        low_lookback=95.0,
        high_lookback=105.0,
        ema_fast=99.0,
    )


def _bar(open_: float, high: float, low: float, close: float) -> pd.Series:
    return pd.Series({"Open": open_, "High": high, "Low": low, "Close": close})


def test_contrato_numerico_p21_con_numeros_cerrados() -> None:
    economics = event_economics(entry_price=100.0, stop=95.0, exit_price=110.0, cost_pct=0.20)

    assert economics.risk_pp == pytest.approx(5.0)
    assert economics.gross_return_pp == pytest.approx(10.0)
    assert economics.gross_r_multiple == pytest.approx(2.0)
    assert economics.net_return_pp == pytest.approx(9.8)
    assert economics.net_r_multiple == pytest.approx(1.96)
    assert economics.gross_return_pp / economics.risk_pp == pytest.approx((110.0 - 100.0) / (100.0 - 95.0))
    assert economics.net_r_multiple == pytest.approx(economics.gross_r_multiple - 0.20 / economics.risk_pp)


def test_signal_id_acepta_timestamp_iso_de_cosecha() -> None:
    assert stable_signal_id("AAPL", "swing", "2021-11-05T04:00:00Z") == "AAPL|swing|2021-11-05T04:00:00Z"


@pytest.mark.parametrize(
    ("bar", "expected_status", "expected_price"),
    [
        (_bar(94.0, 112.0, 93.0, 108.0), STOP_FIRST, 94.0),
        (_bar(111.0, 112.0, 93.0, 108.0), TARGET_FIRST, 111.0),
        (_bar(100.0, 111.0, 94.0, 101.0), AMBIGUOUS, None),
        (_bar(100.0, 109.0, 94.0, 101.0), STOP_FIRST, 95.0),
        (_bar(100.0, 111.0, 96.0, 101.0), TARGET_FIRST, 110.0),
    ],
)
def test_ambiguedad_intrabarra_conserva_estado_y_el_hueco_resuelve(bar, expected_status, expected_price) -> None:
    status, price = classify_target_stop_bar(bar, stop=95.0, target=110.0)

    assert status == expected_status
    if expected_price is None:
        assert pd.isna(price)
    else:
        assert price == pytest.approx(expected_price)


def test_managed_event_no_resuelve_vela_ambigua() -> None:
    df = pd.DataFrame(
        [
            {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0},
            {"Open": 100.0, "High": 111.0, "Low": 94.0, "Close": 102.0},
        ],
        index=pd.date_range("2026-01-01", periods=2, freq="D", tz="UTC"),
    )

    event = evaluate_managed_event(_observation(), df, 0, _levels(), max_hold_bars=1, cost_pct=0.2)

    assert event.exit_status == AMBIGUOUS
    assert event.exit_price is None
    assert event.net_r_multiple is None
    assert event.mae_r == pytest.approx(1.2)
    # La vela abre entre stop y objetivo y toca ambos: su máximo no es un hecho
    # observable, así que solo puede figurar como cota superior.
    assert event.mfe_lower_r == pytest.approx(0.0)
    assert event.mfe_upper_r == pytest.approx(2.2)


def test_intervalo_por_banda_usa_seguros_y_ambiguos_sin_colapsar() -> None:
    signals = [
        _signal(score=55.0, status=TARGET_FIRST),
        _signal(score=55.0, status=AMBIGUOUS),
        _signal(score=55.0, status=STOP_FIRST),
        _signal(score=85.0, status=TARGET_FIRST),
        _signal(score=85.0, status=TARGET_FIRST),
        _signal(score=85.0, status=STOP_FIRST),
    ]

    by_label = {band.label: band for band in summarize_by_score_band(signals)}

    assert by_label["50-60"].total == 3
    assert by_label["50-60"].lower == pytest.approx(1 / 3)
    assert by_label["50-60"].upper == pytest.approx(2 / 3)
    assert by_label["80+"].total == 3
    assert by_label["80+"].lower == pytest.approx(2 / 3)
    assert by_label["80+"].upper == pytest.approx(2 / 3)
    assert all(band.lower <= band.upper for band in by_label.values())


def _signal(score: float, status: str) -> EventStudySignal:
    obs = _observation(score)
    managed = evaluate_managed_event(
        obs,
        _df_for_status(status),
        0,
        _levels(),
        max_hold_bars=1,
        cost_pct=0.2,
    )
    potential = PotentialEvent(
        observation=obs,
        entry_price=100.0,
        stop=95.0,
        exit_status=STOP_FIRST,
        exit_idx=1,
        exit_timestamp=managed.exit_timestamp,
        mfe_unbounded_lower_r=managed.mfe_lower_r,
        mfe_unbounded_upper_r=managed.mfe_upper_r,
    )
    return EventStudySignal(observation=obs, managed=managed, potential=potential)


def _df_for_status(status: str) -> pd.DataFrame:
    future = {
        TARGET_FIRST: {"Open": 100.0, "High": 110.0, "Low": 96.0, "Close": 109.0},
        STOP_FIRST: {"Open": 100.0, "High": 104.0, "Low": 95.0, "Close": 96.0},
        AMBIGUOUS: {"Open": 100.0, "High": 111.0, "Low": 94.0, "Close": 102.0},
    }[status]
    return pd.DataFrame(
        [
            {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0},
            future,
        ],
        index=pd.date_range("2026-01-01", periods=2, freq="D", tz="UTC"),
    )


def _df_potencial(segunda: dict) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0},
            segunda,
        ],
        index=pd.date_range("2026-01-01", periods=2, freq="D", tz="UTC"),
    )


def test_potencial_con_hueco_bajo_el_stop_no_cuenta_el_maximo_de_esa_vela() -> None:
    """Un hueco resuelve el orden: se sale en la apertura y el resto no existe.

    Es el caso que más engaña, porque la vela puede subir mucho después de
    haber cruzado el stop a la baja, y ese recorrido es inalcanzable.
    """

    df = _df_potencial({"Open": 94.0, "High": 130.0, "Low": 93.0, "Close": 129.0})

    event = evaluate_potential_event(_observation(), df, 0, _levels(), max_hold_bars=5)

    assert event.exit_status == STOP_FIRST
    assert event.mfe_unbounded_lower_r == pytest.approx(0.0)
    assert event.mfe_unbounded_upper_r == pytest.approx(0.0)


def test_potencial_con_stop_intrabarra_publica_intervalo() -> None:
    """Si la vela abre por encima del stop y luego lo toca, el orden es
    inobservable: el máximo se publica como cota superior, no como hecho."""

    df = _df_potencial({"Open": 100.0, "High": 130.0, "Low": 94.0, "Close": 96.0})

    event = evaluate_potential_event(_observation(), df, 0, _levels(), max_hold_bars=5)

    assert event.exit_status == STOP_FIRST
    assert event.mfe_unbounded_lower_r == pytest.approx(0.0)
    assert event.mfe_unbounded_upper_r == pytest.approx(6.0)


def test_potencial_sin_stop_no_trunca_el_recorrido() -> None:
    """Sin objetivo y sin stop tocado, el MFE es el recorrido completo y el
    intervalo se cierra: no hay ninguna ambigüedad que conservar."""

    df = _df_potencial({"Open": 100.0, "High": 130.0, "Low": 99.0, "Close": 129.0})

    event = evaluate_potential_event(_observation(), df, 0, _levels(), max_hold_bars=5)

    assert event.exit_status != STOP_FIRST
    assert event.mfe_unbounded_lower_r == pytest.approx(6.0)
    assert event.mfe_unbounded_upper_r == pytest.approx(6.0)


def test_administrado_con_hueco_sobre_el_objetivo_acota_el_mfe_a_la_apertura() -> None:
    """Salida por hueco al alza: lo alcanzable es la apertura, no el máximo."""

    df = _df_potencial({"Open": 115.0, "High": 140.0, "Low": 114.0, "Close": 139.0})

    event = evaluate_managed_event(_observation(), df, 0, _levels(), max_hold_bars=5, cost_pct=0.2)

    assert event.exit_status == TARGET_FIRST
    assert event.exit_price == pytest.approx(115.0)
    assert event.mfe_lower_r == pytest.approx(3.0)
    assert event.mfe_upper_r == pytest.approx(3.0)
