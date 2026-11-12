"""Parámetros de ``superbot_ia_v1``. Se congelan en la base al crearla, como los de la cartera."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Optional

POLICY_ID = "superbot_ia_v1"
SCHEMA_VERSION = "1"

CAUSA_SMA = "CIERRE_BAJO_SMA"
CAUSA_SCORE = "SCORE_BAJO_60"
CAUSA_INVALIDACION = "INVALIDACION_CRUZADA"
CAUSAS = (CAUSA_SMA, CAUSA_SCORE, CAUSA_INVALIDACION)


@dataclass(frozen=True)
class PoliticaIA:
    score_min: float = 60.0
    top_por_plaza: int = 5
    horizonte: str = "swing"
    sma_periodo: int = 50
    sma_holgura: float = 0.02
    score_venta: float = 60.0
    max_ventas_por_pasada: int = 1
    espera_recompra_sesiones: int = 5
    # ``None`` es sin tope: el gasto se sigue reservando y registrando, pero no bloquea llamadas.
    tope_eur_mes: Optional[float] = None
    cache_horas: int = 24
    modelo: str = "claude-opus-5-5"
    max_tokens: int = 4000
    # Margen sobre los bytes del mensaje: esquema y envoltura que la API factura como entrada.
    margen_tokens_entrada: int = 4000
    esfuerzo: str = "medium"
    usd_millon_entrada: float = 4.0
    usd_millon_salida: float = 20.0
    # Un dólar se cuenta como un euro: sobrestima el gasto y no depende de un tipo de cambio.
    eur_por_usd: float = 1.0

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    def coste_eur(self, tokens_entrada: int, tokens_salida: int) -> float:
        usd = tokens_entrada * self.usd_millon_entrada / 1e6 + tokens_salida * self.usd_millon_salida / 1e6
        return usd * self.eur_por_usd

    def coste_maximo_eur(self, tokens_entrada_estimados: int) -> float:
        """Lo que puede costar una llamada como mucho: se reserva antes de hacerla."""

        return self.coste_eur(tokens_entrada_estimados, self.max_tokens)
