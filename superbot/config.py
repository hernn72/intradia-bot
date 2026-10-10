"""Parámetros de la cartera paper visible.

Los valores por defecto son los de ``trading-bot/config.yaml`` (iTrade Bot)
tras el incidente del 3-8 jul 2026: ATR 3,0, histéresis del 2 % con dos cierres
de confirmación, riesgo 1,25 % por operación, 25 % de techo por posición,
mínimo de 200 EUR, seis huecos y costes de Trade Republic.

La configuración se congela en la base al hacer ``init``: una cartera no cambia
de reglas a mitad de camino sin que quede registrado.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List

STRATEGY_ID = "itrade_trend_v1"


@dataclass(frozen=True)
class StrategyParams:
    sma_fast: int = 50
    sma_slow: int = 200
    rsi_period: int = 14
    rsi_entry_min: float = 45.0
    rsi_entry_max: float = 80.0
    rsi_exit: float = 90.0
    exit_buffer_pct: float = 0.02
    exit_confirm_days: int = 2
    atr_period: int = 14
    atr_multiplier: float = 3.0
    stop_loss_pct: float = 0.05
    # Objetivos en múltiplos de R (R = entrada − stop inicial). iTrade no tiene
    # objetivos: aquí son niveles de referencia que avisan al tocarse, no salidas.
    target1_r: float = 2.0
    target2_r: float = 4.0
    # Ranking de compras simultáneas (``TrendStrategy.score`` de iTrade).
    momentum_lookback_3m: int = 63
    momentum_lookback_6m: int = 126
    momentum_lookback_12m: int = 252
    momentum_vol_lookback: int = 252
    momentum_3m_weight: float = 0.40
    momentum_6m_weight: float = 0.30
    momentum_12m_weight: float = 0.20
    inv_vol_weight: float = 0.10


@dataclass(frozen=True)
class SizingParams:
    max_position_pct: float = 0.25
    max_risk_pct_per_trade: float = 0.0125
    min_position_value_eur: float = 200.0
    max_positions: int = 6
    # Escalonado de iTrade: el capital se despliega en varios días, no de golpe.
    max_new_positions_per_session: int = 3


@dataclass(frozen=True)
class CostParams:
    commission_pct: float = 0.0015
    commission_fixed_eur: float = 1.0
    slippage_pct: float = 0.0005
    spread_pct: float = 0.0005


@dataclass(frozen=True)
class SuperbotConfig:
    initial_capital_eur: float = 10_000.0
    strategy_id: str = STRATEGY_ID
    groups: List[str] = field(default_factory=lambda: ["usa", "europa", "asia", "etfs_etc"])
    history_period: str = "2y"
    settlement_minutes: int = 20
    # Una orden de compra que no encuentra barra en este plazo se cancela: la
    # señal ya no describe el mercado que habría al ejecutarla.
    buy_order_expiry_days: int = 7
    # Eventos de barras más antiguas no se avisan uno a uno (arranque
    # retrospectivo o recuperación tras días sin ejecutar): solo el resumen.
    notify_max_age_days: int = 4
    strategy: StrategyParams = field(default_factory=StrategyParams)
    sizing: SizingParams = field(default_factory=SizingParams)
    costs: CostParams = field(default_factory=CostParams)

    def validate(self) -> None:
        if self.initial_capital_eur <= 0:
            raise ValueError("initial_capital_eur debe ser mayor que 0")
        if not 0 < self.sizing.max_position_pct <= 1:
            raise ValueError("max_position_pct debe estar en (0, 1]")
        if not 0 < self.sizing.max_risk_pct_per_trade <= 1:
            raise ValueError("max_risk_pct_per_trade debe estar en (0, 1]")
        if not 0 < self.strategy.stop_loss_pct < 1:
            raise ValueError("stop_loss_pct debe estar en (0, 1)")
        if self.sizing.max_positions < 1:
            raise ValueError("max_positions debe ser al menos 1")
        if self.strategy.sma_fast >= self.strategy.sma_slow:
            raise ValueError("sma_fast debe ser menor que sma_slow")
        if not self.groups:
            raise ValueError("groups no puede estar vacío")

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> SuperbotConfig:
        raw: Dict[str, Any] = json.loads(text)
        nested = {"strategy": StrategyParams, "sizing": SizingParams, "costs": CostParams}
        kwargs: Dict[str, Any] = {}
        known = {f.name for f in fields(cls)}
        for key, value in raw.items():
            if key not in known:
                raise ValueError(f"clave de configuración desconocida: {key}")
            kwargs[key] = nested[key](**value) if key in nested else value
        config = cls(**kwargs)
        config.validate()
        return config
