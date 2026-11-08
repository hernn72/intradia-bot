"""Paquete de una decisión: los datos fechados que reciben los asesores.

El paquete es la frontera causal. Lo que no esté aquí no existe para el modelo, y
ningún dato puede estar disponible después del instante de la decisión.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Mapping, Optional, Tuple

from superbot.ia.politica import POLICY_ID

COMPRA = "COMPRA"
POSICION = "POSICION"


class PaqueteInvalido(ValueError):
    """El paquete incumple el contrato causal: no se llama al modelo."""


@dataclass(frozen=True)
class Observacion:
    fuente: str
    symbol: str
    session: str
    available_at: datetime
    observed_at: datetime
    hash: str


@dataclass(frozen=True)
class PosicionIA:
    """Posición abierta, con lo guardado al abrirla para poder auditar sus causas de venta."""

    symbol: str
    entry_date: date
    signal_session: date
    decision_apertura: str
    entry_price: float
    stop: float
    invalidation_level: Optional[float]
    pnl_pct: float
    exposicion_pct: float
    # Identificador real en ``ia_posicion`` (fase 3): permite que una decisión VENDER cree una
    # salida pendiente ligada a ESTA posición concreta, no a su símbolo (dos posiciones sucesivas
    # del mismo símbolo no deben confundirse). ``None`` fuera de la cartera real (corpus, pruebas
    # que no pasan por CarteraIA).
    id: Optional[int] = None


@dataclass(frozen=True)
class EstadoCartera:
    equity_eur: float
    cash_eur: float
    posiciones: Tuple[PosicionIA, ...] = ()
    ordenes_pendientes: Tuple[str, ...] = ()
    ventas_ia: Mapping[str, date] = field(default_factory=dict)

    def resumen(self) -> Dict[str, Any]:
        return {
            "equity_eur": round(self.equity_eur, 2),
            "efectivo_pct": round(100 * self.cash_eur / self.equity_eur, 2) if self.equity_eur > 0 else None,
            "posiciones": [
                {"valor": p.symbol, "exposicion_pct": round(p.exposicion_pct, 2), "resultado_pct": round(p.pnl_pct, 2)}
                for p in self.posiciones
            ],
        }


def canonico(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class Paquete:
    tipo: str
    symbol: str
    market: str
    signal_session: date
    target_session: date
    target_open: datetime
    decision_ts: datetime
    datos: Mapping[str, Any]
    observaciones: Tuple[Observacion, ...]

    @property
    def clave(self) -> str:
        return f"{self.symbol}|{self.signal_session}|{self.target_session}|{POLICY_ID}"

    @property
    def mensaje(self) -> str:
        return json.dumps(self.datos, sort_keys=True, ensure_ascii=False, indent=1, default=str)

    @property
    def input_hash(self) -> str:
        """Solo depende de lo que ve el modelo: el reloj de la pasada no invalida la caché."""

        return hashlib.sha256(canonico(self.datos).encode("utf-8")).hexdigest()

    @property
    def input_source_ids(self) -> Tuple[str, ...]:
        return tuple(sorted(f"{o.fuente}:{o.symbol}:{o.session}:{o.hash}" for o in self.observaciones))


def validar_causal(paquete: Paquete) -> None:
    """Rechaza mecánicamente lo que incumple D-81. Falla antes de gastar una llamada."""

    if paquete.decision_ts.tzinfo is None or paquete.target_open.tzinfo is None:
        raise PaqueteInvalido("instantes sin zona horaria")
    if not paquete.observaciones:
        raise PaqueteInvalido("paquete sin observaciones")
    tardia = max(o.available_at for o in paquete.observaciones)
    if tardia > paquete.decision_ts:
        raise PaqueteInvalido(f"dato disponible en {tardia.isoformat()}, posterior a la decisión")
    observada = max(o.observed_at for o in paquete.observaciones)
    if observada > paquete.decision_ts:
        raise PaqueteInvalido(f"dato observado en {observada.isoformat()}, posterior a la decisión")
    if paquete.decision_ts >= paquete.target_open:
        raise PaqueteInvalido("decisión posterior a la apertura de su sesión objetivo")
    if paquete.datos.get("contexto", {}).get("fuente") != "point_in_time":
        raise PaqueteInvalido("contexto que no es point_in_time")
