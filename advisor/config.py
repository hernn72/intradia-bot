"""Carga y validación de ``config.yaml`` (pydantic).

Punto único de entrada de configuración del asesor: ``load_config`` devuelve
un ``AdvisorConfig`` ya validado. Cualquier valor incoherente falla aquí, al
arrancar, y no a mitad de un análisis.

Los secretos (tokens de Telegram, clave de Anthropic) NUNCA se leen de este
archivo: solo de variables de entorno / ``.env``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

VALID_HORIZONTES = ("intradia", "swing", "medio")

# Divisas para las que existe un par ``EUR<CCY>=X`` en yfinance y por tanto
# se puede convertir el precio a euros. Ampliar aquí al añadir mercados.
SUPPORTED_CURRENCIES = frozenset({"EUR", "USD", "GBP", "CHF", "JPY", "HKD", "SEK", "DKK", "NOK"})


def _default_benchmark_by_region() -> Dict[str, Optional[str]]:
    return {
        "USA": "^GSPC",
        "EUROPA": "^STOXX",
        "ASIA": "^N225",
        "GLOBAL": "^GSPC",
        "EMERGING_MARKETS": None,
    }


def _default_benchmark_by_market() -> Dict[str, Optional[str]]:
    return {
        "JPX": "^N225",
        "OSA": "^N225",
        "HKG": "^HSI",
        "KSC": "^KS11",
        "TAI": "^TWII",
        "SHH": "510300.SS",
        "SNP": "510300.SS",
    }


class HorizonteConfig(BaseModel):
    """Ventana de datos de un horizonte de análisis."""

    interval: str
    period: str
    min_bars: int = Field(..., gt=0)


class IndicatorsConfig(BaseModel):
    ema_fast: int = Field(20, gt=0)
    ema_slow: int = Field(50, gt=0)
    sma_long: int = Field(200, gt=0)
    rsi_period: int = Field(14, gt=1)
    atr_period: int = Field(14, gt=0)
    macd_fast: int = Field(12, gt=0)
    macd_slow: int = Field(26, gt=0)
    macd_signal: int = Field(9, gt=0)
    volume_lookback: int = Field(20, gt=0)

    @model_validator(mode="after")
    def _validate_periods(self) -> IndicatorsConfig:
        if self.ema_fast >= self.ema_slow:
            raise ValueError(f"ema_fast ({self.ema_fast}) debe ser menor que ema_slow ({self.ema_slow})")
        if self.macd_fast >= self.macd_slow:
            raise ValueError(f"macd_fast ({self.macd_fast}) debe ser menor que macd_slow ({self.macd_slow})")
        return self


class LevelsConfig(BaseModel):
    lookback_bars: int = Field(60, gt=1)
    atr_stop_multiple: float = Field(2.0, gt=0)
    target_atr_multiples: List[float] = Field(default_factory=lambda: [1.5, 3.0, 5.0])
    entry_pullback_atr: float = Field(0.5, ge=0)
    entry_max_atr: float = Field(0.75, ge=0)
    # ¿El objetivo 2 —el que forma el ratio beneficio/riesgo— cede ante una
    # resistencia real, como ya hace el objetivo 1? Con esto en false el
    # ratio es casi una constante (stop y objetivo 2 son múltiplos del mismo
    # ATR); con true mide la distancia hasta el primer obstáculo estructural.
    # Ver docs/ratio-beneficio-riesgo.md.
    target2_structural: bool = False

    @field_validator("target_atr_multiples")
    @classmethod
    def _validate_targets(cls, value: List[float]) -> List[float]:
        if len(value) != 3:
            raise ValueError(f"target_atr_multiples debe tener exactamente 3 valores (objetivos 1-3), recibidos: {len(value)}")
        if any(v <= 0 for v in value):
            raise ValueError("todos los múltiplos de target_atr_multiples deben ser > 0")
        # Estrictamente creciente: dos objetivos iguales no son un error
        # inofensivo, dejan una configuración con dos niveles que son el
        # mismo precio y un objetivo 3 que nunca aporta información nueva.
        if any(b <= a for a, b in zip(value, value[1:])):
            raise ValueError(f"target_atr_multiples debe ser creciente (objetivo 1 < 2 < 3), recibido: {value}")
        return value


class ScoringConfig(BaseModel):
    min_score_operar: float = Field(70.0, ge=0, le=100)
    min_score_vigilar: float = Field(60.0, ge=0, le=100)
    fundamentals_enabled: bool = False

    @model_validator(mode="after")
    def _validate_thresholds(self) -> ScoringConfig:
        if self.min_score_vigilar > self.min_score_operar:
            raise ValueError(
                f"min_score_vigilar ({self.min_score_vigilar}) no puede superar "
                f"min_score_operar ({self.min_score_operar})"
            )
        return self


class RiskConfig(BaseModel):
    min_rr_ratio: float = Field(1.5, gt=0)
    risk_free_annual_pct: float = Field(2.25, ge=0)
    # Holgura exigida sobre la alternativa sin riesgo en el horizonte medio:
    # el potencial hasta el objetivo 2 debe ser al menos este múltiplo del
    # 2,25% anual para que asumir riesgo de mercado durante meses compense.
    risk_free_multiple: float = Field(2.0, gt=0)


class PortfolioConfig(BaseModel):
    capital: Optional[float] = Field(None, gt=0)
    risk_per_trade_pct: float = Field(0.5, gt=0, le=100)
    max_position_pct: float = Field(10.0, gt=0, le=100)


class MarketContextConfig(BaseModel):
    vix_symbol: str = "^VIX"
    vix_threshold: float = Field(25.0, gt=0)
    trend_symbol: str = "^STOXX50E"
    trend_sma: int = Field(200, gt=0)


class DataQualityConfig(BaseModel):
    settlement_minutes: int = Field(20, ge=0)
    veto_incomplete_open: bool = True
    veto_window_sessions: int = Field(20, gt=0)
    critical_latest_sessions: int = Field(0, ge=0)
    high_after_sessions: int = Field(5, ge=0)
    medium_after_sessions: int = Field(20, ge=0)

    @model_validator(mode="after")
    def _validate_severity_cuts(self) -> DataQualityConfig:
        if not self.critical_latest_sessions <= self.high_after_sessions <= self.medium_after_sessions:
            raise ValueError(
                "los cortes de severidad deben ir en orden: critical_latest_sessions "
                f"({self.critical_latest_sessions}) <= high_after_sessions ({self.high_after_sessions}) "
                f"<= medium_after_sessions ({self.medium_after_sessions})"
            )
        # El corte MEDIUM y la ventana de veto son el mismo concepto visto dos
        # veces. Si divergen, las ausencias entre ambos valores entran en la
        # ventana pero reciben WARNING y dejan de vetar, es decir, parte de la
        # ventana de veto deja de vetar sin que nadie lo diga.
        if self.medium_after_sessions != self.veto_window_sessions:
            raise ValueError(
                "medium_after_sessions y veto_window_sessions deben coincidir: son la misma ventana. "
                f"Recibidos {self.medium_after_sessions} y {self.veto_window_sessions}"
            )
        return self


class BarCacheConfig(BaseModel):
    """Caché local de barras de sesión cerrada ya validadas (C-09, D-41).

    ``window_sessions`` es la ventana en la que la caché actúa. No es la ventana
    de los indicadores a propósito: el fallo medido es que el proveedor retira
    por la mañana una barra reciente que ya había servido, así que persistir y
    reinyectar las últimas sesiones basta. Cuanto más larga sea la ventana, más
    barras quedan expuestas a un reajuste por dividendo, que obliga a reanclar.

    ``readjustment_tolerance`` es la holgura relativa con la que dos barras se
    consideran la misma. Por debajo de ella, la diferencia es redondeo del
    proveedor; por encima, o todas las barras solapadas cambian por un mismo
    factor —reajuste por dividendo o split— o una cambia sola, que es una
    revisión de la sesión.
    """

    enabled: bool = True
    window_sessions: int = Field(30, gt=0)
    readjustment_tolerance: float = Field(1e-4, gt=0)


class ReportConfig(BaseModel):
    top_n: int = Field(5, gt=0)
    benchmark_symbol: str = "^STOXX50E"
    benchmark_by_region: Dict[str, Optional[str]] = Field(default_factory=_default_benchmark_by_region)
    benchmark_by_market: Dict[str, Optional[str]] = Field(default_factory=_default_benchmark_by_market)


class EventsConfig(BaseModel):
    """Calendario de eventos con fecha conocida (resultados y banco central)."""

    enabled: bool = True
    path: str = "events.yaml"
    pasada_evento_hora: str = "22:30"
    # Ventana que se mira hacia delante al redactar una recomendación.
    ventana_dias: int = Field(30, gt=0)
    # Por debajo de estos días, unos resultados dejan de ser un dato de
    # contexto y pasan a ser un riesgo: el precio se moverá por la
    # publicación, no por la configuración técnica que motivó la entrada.
    aviso_resultados_dias: int = Field(7, gt=0)

    @field_validator("pasada_evento_hora")
    @classmethod
    def _validate_pasada_evento_hora(cls, value: str) -> str:
        cleaned = value.strip()
        parts = cleaned.split(":")
        if len(parts) != 2 or not all(part.isdigit() and len(part) == 2 for part in parts):
            raise ValueError("pasada_evento_hora debe tener formato HH:MM")
        hour, minute = (int(part) for part in parts)
        if hour > 23 or minute > 59:
            raise ValueError("pasada_evento_hora debe ser una hora válida en formato HH:MM")
        return cleaned

    @model_validator(mode="after")
    def _validate_ventana(self) -> EventsConfig:
        if self.aviso_resultados_dias > self.ventana_dias:
            raise ValueError(
                f"aviso_resultados_dias ({self.aviso_resultados_dias}) no puede superar "
                f"ventana_dias ({self.ventana_dias}): el aviso nunca se dispararía"
            )
        return self


class AiConfig(BaseModel):
    enabled: bool = False
    model: str = "claude-sonnet-5"
    max_opportunities: int = Field(5, gt=0)


class AdvisorConfig(BaseModel):
    """Configuración completa del asesor."""

    base_currency: str = "EUR"
    universe_path: str = "universe.yaml"
    db_path: str = "intradia.db"
    request_min_interval_seconds: float = Field(1.0, ge=0)
    horizontes: Dict[str, HorizonteConfig]
    indicators: IndicatorsConfig = Field(default_factory=IndicatorsConfig)
    levels: LevelsConfig = Field(default_factory=LevelsConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    portfolio: PortfolioConfig = Field(default_factory=PortfolioConfig)
    market_context: MarketContextConfig = Field(default_factory=MarketContextConfig)
    data_quality: DataQualityConfig = Field(default_factory=DataQualityConfig)
    bar_cache: BarCacheConfig = Field(default_factory=BarCacheConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)
    ai: AiConfig = Field(default_factory=AiConfig)
    events: EventsConfig = Field(default_factory=EventsConfig)

    @field_validator("base_currency")
    @classmethod
    def _validate_base_currency(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if cleaned not in SUPPORTED_CURRENCIES:
            raise ValueError(f"base_currency no soportada: '{value}'. Permitidas: {sorted(SUPPORTED_CURRENCIES)}")
        return cleaned

    @field_validator("horizontes")
    @classmethod
    def _validate_horizontes(cls, value: Dict[str, HorizonteConfig]) -> Dict[str, HorizonteConfig]:
        if not value:
            raise ValueError("horizontes no puede estar vacío")
        unknown = set(value) - set(VALID_HORIZONTES)
        if unknown:
            raise ValueError(f"horizontes desconocidos: {sorted(unknown)}. Permitidos: {list(VALID_HORIZONTES)}")
        return value

    def horizonte(self, name: str) -> HorizonteConfig:
        """Devuelve la ventana de datos de ``name``. Lanza ``ValueError`` si no está configurado."""
        try:
            return self.horizontes[name]
        except KeyError:
            raise ValueError(
                f"horizonte '{name}' no configurado en config.yaml. Disponibles: {sorted(self.horizontes)}"
            ) from None


def load_config(path: str | Path = "config.yaml") -> AdvisorConfig:
    """Carga y valida ``config.yaml``.

    Lanza ``FileNotFoundError`` si el archivo no existe y ``ValueError`` si el
    contenido no es un mapeo YAML válido o no supera la validación.
    """

    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"No se encuentra el archivo de configuración: {config_path}")

    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    if not isinstance(raw, dict):
        raise ValueError(f"{config_path} debe contener un mapeo YAML en la raíz")

    return AdvisorConfig(**raw)
