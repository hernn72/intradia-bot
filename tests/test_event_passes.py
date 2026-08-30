"""Pasadas autodescartables por eventos conocidos."""

from __future__ import annotations

from datetime import date
from typing import Optional

from advisor.events.calendar import EventCalendar
from advisor.events.models import ALCANCE_ACTIVO, ALCANCE_GLOBAL, TIPO_BANCO_CENTRAL, TIPO_RESULTADOS, MarketEvent
from advisor.events.passes import decide_event_pass, deterministic_event_pass_id, events_for_day, format_event_trigger
from advisor.storage.db import AdvisorDB


class EarningsFalsos:
    def __init__(self, fechas: dict[str, Optional[date]]) -> None:
        self.fechas = fechas

    def next_earnings(self, symbol: str) -> Optional[MarketEvent]:
        fecha = self.fechas.get(symbol)
        if fecha is None:
            return None
        return MarketEvent(
            fecha=fecha,
            tipo=TIPO_RESULTADOS,
            alcance=ALCANCE_ACTIVO,
            titulo="Publicación de resultados",
            fuente="proveedor",
            simbolo=symbol,
            confirmada=False,
        )


def _macro(fecha: date) -> MarketEvent:
    return MarketEvent(
        fecha=fecha,
        tipo=TIPO_BANCO_CENTRAL,
        alcance=ALCANCE_GLOBAL,
        titulo="Decisión de tipos del BCE",
        fuente="banco central",
        detalle="reunión de política monetaria",
    )


def test_events_for_day_usa_dias_cero_y_resultados_por_activo(asset_eur, asset_usd) -> None:
    today = date(2026, 9, 10)
    calendar = EventCalendar(
        [_macro(today), _macro(date(2026, 9, 11))],
        EarningsFalsos({asset_usd.symbol: today, asset_eur.symbol: date(2026, 9, 11)}),
    )

    events = events_for_day(calendar, [asset_eur, asset_usd], today)

    assert [event.titulo for event in events] == ["Decisión de tipos del BCE", "Publicación de resultados"]
    assert events[1].simbolo == asset_usd.symbol


def test_eventos_pasados_no_disparan_ni_crean_ids(tmp_path, asset_eur) -> None:
    today = date(2026, 9, 10)
    calendar = EventCalendar([_macro(date(2026, 9, 9))], EarningsFalsos({asset_eur.symbol: date(2026, 9, 9)}))
    db = AdvisorDB(tmp_path / "test.db")

    decision = decide_event_pass(calendar, [asset_eur], db, horizonte="swing", today=today)

    assert decision.should_run is False
    assert decision.events == []
    assert decision.claimed_event_ids == []


def test_intento_fallido_en_claimed_no_silencia_el_evento(tmp_path, asset_eur) -> None:
    today = date(2026, 9, 10)
    calendar = EventCalendar([_macro(today)])
    db = AdvisorDB(tmp_path / "test.db")
    expected_id = deterministic_event_pass_id(_macro(today), "swing", "evento")

    first = decide_event_pass(calendar, [asset_eur], db, horizonte="swing", today=today)
    second = decide_event_pass(calendar, [asset_eur], db, horizonte="swing", today=today)

    assert first.should_run is True
    assert first.claimed_event_ids == [expected_id]
    assert second.should_run is True
    assert second.claimed_event_ids == [expected_id]
    assert db.get_event_pass(expected_id)["status"] == "CLAIMED"


def test_envio_correcto_deduplica_el_siguiente_disparo(tmp_path, asset_eur) -> None:
    today = date(2026, 9, 10)
    calendar = EventCalendar([_macro(today)])
    db = AdvisorDB(tmp_path / "test.db")
    expected_id = deterministic_event_pass_id(_macro(today), "swing", "evento")

    first = decide_event_pass(calendar, [asset_eur], db, horizonte="swing", today=today)
    db.mark_event_passes_sent(first.claimed_event_ids)
    second = decide_event_pass(calendar, [asset_eur], db, horizonte="swing", today=today)

    assert first.should_run is True
    assert second.should_run is False
    assert second.duplicate_event_ids == [expected_id]
    assert db.get_event_pass(expected_id)["status"] == "SENT"


def test_texto_de_disparo_incluye_evento_activo_y_fuente() -> None:
    text = format_event_trigger(
        [
            MarketEvent(
                fecha=date(2026, 9, 10),
                tipo=TIPO_RESULTADOS,
                alcance=ALCANCE_ACTIVO,
                titulo="Publicación de resultados",
                fuente="yfinance",
                simbolo="AAPL",
                confirmada=False,
            )
        ]
    )

    assert "Pasada por evento" in text
    assert "AAPL" in text
    assert "fecha estimada" in text
