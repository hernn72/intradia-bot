"""Pasadas adicionales disparadas por eventos con fecha conocida.

El temporizador es fijo y barato; la inteligencia está aquí. Si hoy no hay
evento, el proceso termina sin enviar nada. Si lo hay, se reserva un ID
determinista antes de generar el informe para que un doble disparo de systemd
o una ejecución manual no duplique Telegram.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, List, Sequence

from advisor.events.calendar import EventCalendar
from advisor.events.models import ALCANCE_ACTIVO, TIPO_RESULTADOS, MarketEvent
from advisor.storage.db import AdvisorDB
from advisor.universe.models import Asset

PASS_KIND_EVENTO = "evento"


@dataclass(frozen=True)
class EventPassDecision:
    """Decisión auditable antes de ejecutar una pasada por evento."""

    today: date
    events: List[MarketEvent]
    claimed_event_ids: List[str]
    duplicate_event_ids: List[str]
    health_alerts: List[str]

    @property
    def should_run(self) -> bool:
        return bool(self.claimed_event_ids)

    @property
    def discard_reason(self) -> str:
        if not self.events:
            return f"sin eventos fechados para {self.today.isoformat()}"
        return "todos los eventos de hoy ya tienen una pasada enviada"


def decide_event_pass(
    calendar: EventCalendar,
    assets: Sequence[Asset],
    db: AdvisorDB,
    *,
    horizonte: str,
    today: date,
) -> EventPassDecision:
    """Consulta eventos de hoy y reserva los que aún no tienen pasada."""

    events = events_for_day(calendar, assets, today)
    rows = [
        {
            "event_id": deterministic_event_pass_id(event, horizonte, PASS_KIND_EVENTO),
            "event_date": event.fecha.isoformat(),
            "event_type": event.tipo,
            "event_scope": event.alcance,
            "symbol": event.simbolo,
            "horizonte": horizonte,
            "pass_kind": PASS_KIND_EVENTO,
            "title": event.titulo,
        }
        for event in events
    ]
    # No se usa un bloqueo distribuido: en producción lo lanza un servicio
    # systemd Type=oneshot desde un timer fijo, así que una misma unidad no se
    # solapa consigo misma. La deduplicación deliberadamente solo considera
    # definitivo el estado SENT; un CLAIMED puede ser un intento muerto antes
    # de Telegram y debe poder reintentarse.
    claimed = db.claim_event_passes(rows)
    all_ids = [str(row["event_id"]) for row in rows]
    return EventPassDecision(
        today=today,
        events=events,
        claimed_event_ids=claimed,
        duplicate_event_ids=[event_id for event_id in all_ids if event_id not in claimed],
        health_alerts=calendar.alarmas_salud(today),
    )


def events_for_day(calendar: EventCalendar, assets: Sequence[Asset], today: date) -> List[MarketEvent]:
    """Eventos macro globales y resultados de activos analizables que caen hoy."""

    events = list(calendar.proximos(dias=0, hoy=today))
    seen = {_event_identity(event) for event in events}
    for asset in assets:
        for event in calendar.proximos(asset.symbol, dias=0, hoy=today):
            if event.tipo != TIPO_RESULTADOS or event.alcance != ALCANCE_ACTIVO:
                continue
            identity = _event_identity(event)
            if identity in seen:
                continue
            seen.add(identity)
            events.append(event)
    return events


def deterministic_event_pass_id(event: MarketEvent, horizonte: str, pass_kind: str) -> str:
    """ID estable: fecha, tipo, alcance, símbolo, horizonte y clase de pasada."""

    symbol = event.simbolo or "-"
    return "|".join([event.fecha.isoformat(), event.tipo, event.alcance, symbol, horizonte, pass_kind])


def format_event_trigger(events: Iterable[MarketEvent]) -> str:
    """Texto que explica por qué existe una pasada extra."""

    lines = ["Pasada por evento: " + "; ".join(_event_label(event) for event in events)]
    return "\n".join(lines)


def _event_label(event: MarketEvent) -> str:
    symbol = f" ({event.simbolo})" if event.simbolo else ""
    detail = f": {event.detalle}" if event.detalle else ""
    return f"{event.fecha.isoformat()} {event.titulo}{symbol} [{event.etiqueta_fuente}]{detail}"


def _event_identity(event: MarketEvent) -> tuple:
    return event.fecha, event.tipo, event.alcance, event.simbolo, event.titulo
