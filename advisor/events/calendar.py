"""Calendario de eventos del asesor: macro curado + resultados del proveedor.

Une las dos únicas fuentes de eventos que hoy son verificables:

- **Macro**: fichero curado (``events.yaml``) con las fechas que publican la
  Fed y el BCE. Núcleo puro, sin red.
- **Resultados**: fechas del proveedor de datos, que sí cambian y no se
  pueden curar a mano para un universo de cien activos.

Ambas se tratan distinto a propósito. Una fecha de banco central está
publicada por la institución y es fiable; una fecha de resultados la estima
el proveedor, a veces mal y a veces caducada, así que se marca como estimada
y se descarta si ya pasó.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Protocol

import yaml

from advisor.events.models import (
    ALCANCE_ACTIVO,
    ALCANCE_GLOBAL,
    TIPO_BANCO_CENTRAL,
    TIPO_RESULTADOS,
    MarketEvent,
)

logger = logging.getLogger(__name__)

# Si al calendario macro le quedan menos días que esto, el bot avisa: un
# calendario agotado no da error, simplemente deja de ver eventos, que es la
# forma más silenciosa de fallar.
_AVISO_COBERTURA_DIAS = 60


def load_macro_events(path: str | Path = "events.yaml") -> List[MarketEvent]:
    """Carga el calendario macro curado y lo valida.

    Lanza ``FileNotFoundError`` si no existe y ``ValueError`` si el contenido
    no tiene la forma esperada: una fecha macro mal escrita debe fallar al
    arrancar, no aparecer como un evento inventado en un informe.
    """

    ruta = Path(path)
    if not ruta.is_file():
        raise FileNotFoundError(f"No se encuentra el calendario de eventos: {ruta}")

    with ruta.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    if not isinstance(raw, dict) or "eventos" not in raw:
        raise ValueError(f"{ruta} debe contener un mapeo con la clave 'eventos'")

    fuentes: Dict[str, str] = raw.get("fuentes") or {}
    eventos: List[MarketEvent] = []
    for i, item in enumerate(raw["eventos"] or []):
        if not isinstance(item, dict):
            raise ValueError(f"{ruta}: el evento {i} no es un mapeo")
        faltan = {"fecha", "institucion", "titulo"} - set(item)
        if faltan:
            raise ValueError(f"{ruta}: al evento {i} le faltan campos {sorted(faltan)}")
        fecha = item["fecha"]
        if not isinstance(fecha, date):
            raise ValueError(f"{ruta}: la fecha del evento {i} no es una fecha válida: {fecha!r}")
        institucion = str(item["institucion"])
        eventos.append(
            MarketEvent(
                fecha=fecha,
                tipo=TIPO_BANCO_CENTRAL,
                alcance=ALCANCE_GLOBAL,
                titulo=str(item["titulo"]),
                fuente=fuentes.get(institucion.lower(), institucion),
                detalle=item.get("detalle"),
                confirmada=True,
            )
        )

    if not eventos:
        raise ValueError(f"{ruta}: el calendario no contiene ningún evento")

    ordenados = sorted(eventos, key=lambda e: e.fecha)
    if [e.fecha for e in ordenados] != [e.fecha for e in eventos]:
        raise ValueError(f"{ruta}: los eventos deben estar ordenados por fecha")

    return eventos


class EarningsSource(Protocol):
    """Fuente de la próxima fecha de resultados de un activo."""

    def next_earnings(self, symbol: str) -> Optional[MarketEvent]:
        ...


class YahooEarningsSource:
    """Próxima fecha de resultados según yfinance.

    Descarta las fechas que ya pasaron: el proveedor devuelve a veces la
    última publicación en vez de la siguiente (LVMH devolvía el 27-jul un mes
    después), y presentar eso como "próximo evento" sería mentir con un dato
    real.
    """

    def __init__(self, hoy: Optional[date] = None) -> None:
        self._hoy = hoy
        self._cache: Dict[str, Optional[MarketEvent]] = {}

    def _fecha_de_hoy(self) -> date:
        return self._hoy or date.today()

    def next_earnings(self, symbol: str) -> Optional[MarketEvent]:
        if symbol in self._cache:
            return self._cache[symbol]

        evento: Optional[MarketEvent] = None
        try:
            import yfinance as yf

            calendario = yf.Ticker(symbol).calendar or {}
            fechas = calendario.get("Earnings Date") or []
            hoy = self._fecha_de_hoy()
            futuras = [f for f in fechas if isinstance(f, date) and f >= hoy]
            if futuras:
                estimacion = calendario.get("Earnings Average")
                evento = MarketEvent(
                    fecha=min(futuras),
                    tipo=TIPO_RESULTADOS,
                    alcance=ALCANCE_ACTIVO,
                    titulo="Publicación de resultados",
                    fuente="yfinance",
                    simbolo=symbol,
                    detalle=None if estimacion is None else f"BPA estimado por el consenso: {estimacion}",
                    # El proveedor no distingue fecha confirmada de estimada.
                    confirmada=False,
                )
        except Exception as exc:  # los ETF e índices no tienen fundamentales
            logger.debug("Sin calendario de resultados para %s: %s", symbol, exc)

        self._cache[symbol] = evento
        return evento


class EventCalendar:
    """Eventos con fecha conocida que afectan a un activo."""

    def __init__(self, macro: List[MarketEvent], earnings: Optional[EarningsSource] = None) -> None:
        self._macro = sorted(macro, key=lambda e: e.fecha)
        self._earnings = earnings

    @classmethod
    def load(cls, path: str | Path = "events.yaml", earnings: Optional[EarningsSource] = None) -> EventCalendar:
        return cls(load_macro_events(path), earnings)

    @property
    def cobertura_hasta(self) -> date:
        """Fecha del último evento macro conocido."""
        return self._macro[-1].fecha

    def avisar_si_se_agota(self, hoy: Optional[date] = None) -> Optional[str]:
        """Aviso si al calendario macro le queda poco recorrido, o ``None``."""
        referencia = hoy or date.today()
        quedan = (self.cobertura_hasta - referencia).days
        if quedan <= _AVISO_COBERTURA_DIAS:
            return (
                f"el calendario macro solo llega al {self.cobertura_hasta.isoformat()} "
                f"({quedan} días): actualiza events.yaml desde las fuentes que declara"
            )
        return None

    def proximos(self, symbol: Optional[str] = None, dias: int = 14, hoy: Optional[date] = None) -> List[MarketEvent]:
        """Eventos entre hoy y ``dias`` días, ordenados por fecha.

        Incluye siempre los de alcance global; los de resultados solo si se
        pide un ``symbol``.
        """

        if dias < 0:
            raise ValueError(f"dias debe ser >= 0, recibido {dias}")

        referencia = hoy or date.today()
        eventos = [e for e in self._macro if 0 <= e.dias_hasta(referencia) <= dias]

        if symbol and self._earnings is not None:
            resultados = self._earnings.next_earnings(symbol)
            if resultados is not None and 0 <= resultados.dias_hasta(referencia) <= dias:
                eventos.append(resultados)

        return sorted(eventos, key=lambda e: e.fecha)
