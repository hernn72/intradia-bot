"""Fixtures compartidas: datos sintéticos y objetos de configuración.

Ningún test toca la red. Los precios se generan de forma determinista para
que un fallo sea siempre reproducible.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Callable, Iterator, List, Optional

import pandas as pd
import pytest

from advisor.analysis.market_context import MarketContext
from advisor.config import AdvisorConfig
from advisor.universe.models import Asset, Universe


def make_ohlcv(
    n: int = 300,
    start: float = 100.0,
    drift: float = 0.3,
    volume: float = 1_000_000.0,
    last_volume: Optional[float] = None,
    start_date: str = "2026-01-01",
) -> pd.DataFrame:
    """Serie OHLCV sintética con tendencia lineal y rango intradía constante.

    ``drift`` es el incremento por vela: positivo genera tendencia alcista.
    """

    index = pd.date_range(start=start_date, periods=n, freq="D", tz="UTC")
    closes = [start + drift * i for i in range(n)]
    opens = [c - drift * 0.5 for c in closes]
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    volumes: List[float] = [volume] * n
    if last_volume is not None:
        volumes[-1] = last_volume

    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes},
        index=index,
    )


class FakeProvider:
    """Sustituto de ``MarketDataProvider`` que sirve datos de un diccionario."""

    def __init__(
        self,
        histories: Optional[dict] = None,
        closes: Optional[dict] = None,
        raw_histories: Optional[dict] = None,
    ) -> None:
        self.histories = histories or {}
        self.raw_histories = raw_histories or self.histories
        self.closes = closes or {}
        self.calls: List[str] = []

    def get_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        self.calls.append(symbol)
        if symbol not in self.histories:
            raise ValueError(f"sin datos para '{symbol}'")
        return self.histories[symbol]

    def get_raw_history(
        self,
        symbol: str,
        period: str = "1y",
        interval: str = "1d",
        *,
        drop_na: bool = True,
    ) -> pd.DataFrame:
        self.calls.append(symbol)
        if symbol not in self.raw_histories:
            raise ValueError(f"sin datos crudos para '{symbol}'")
        history = self.raw_histories[symbol]
        if drop_na and "Close" in history.columns:
            return history.dropna(subset=["Close"])
        return history

    def get_last_close(self, symbol: str, period: str = "5d", interval: str = "1d"):
        self.calls.append(symbol)
        if symbol in self.closes:
            return self.closes[symbol], pd.Timestamp("2026-08-27", tz="UTC")
        if symbol in self.histories:
            history = self.histories[symbol]
            return float(history["Close"].iloc[-1]), history.index[-1]
        return None, None


@pytest.fixture
def config() -> AdvisorConfig:
    """Configuración mínima válida, equivalente a la del ``config.yaml`` real."""

    return AdvisorConfig(
        base_currency="EUR",
        horizontes={
            "intradia": {"interval": "15m", "period": "60d", "min_bars": 120},
            "swing": {"interval": "1d", "period": "1y", "min_bars": 120},
            "medio": {"interval": "1d", "period": "2y", "min_bars": 250},
        },
    )


@pytest.fixture
def asset_eur() -> Asset:
    return Asset(
        symbol="SAP.DE",
        name="SAP",
        asset_class="stock",
        region="EUROPA",
        market="XETRA",
        currency="EUR",
        timezone="Europe/Berlin",
        trade_republic="yes",
        isin=None,
    )


@pytest.fixture
def asset_usd() -> Asset:
    return Asset(
        symbol="AAPL",
        name="Apple",
        asset_class="stock",
        region="USA",
        market="NASDAQ",
        currency="USD",
        timezone="America/New_York",
        trade_republic="unknown",
    )


@pytest.fixture
def universe(asset_eur: Asset, asset_usd: Asset) -> Universe:
    context_index = Asset(
        symbol="^STOXX50E",
        name="Euro Stoxx 50",
        asset_class="index",
        region="EUROPA",
        market="EU",
        currency="EUR",
        timezone="Europe/Berlin",
        analizable=False,
    )
    return Universe(groups={"europa": [asset_eur], "usa": [asset_usd], "contexto": [context_index]})


@pytest.fixture
def benign_context() -> MarketContext:
    """Contexto de mercado favorable, para aislar el efecto del activo."""

    return MarketContext(
        vix_value=14.0,
        vix_threshold=25.0,
        trend_price=5000.0,
        trend_sma=4800.0,
        label="RISK_ON",
        reason="tendencia alcista y volatilidad contenida",
    )


@pytest.fixture
def hostile_context() -> MarketContext:
    return MarketContext(
        vix_value=32.0,
        vix_threshold=25.0,
        trend_price=4500.0,
        trend_sma=4800.0,
        label="RISK_OFF",
        reason="VIX 32,0 ≥ 25,0 y tendencia no alcista",
    )


# ---------------------------------------------------------------------------
# Red de seguridad de borrado (incidente 2026-10-06: evidence/2026-10-06-incidente-perdida-vintage/).
# Ningún test puede borrar `/`, `$HOME`, la raíz del repo ni sus antecesores, ni nada en `data/`,
# `evidence/` o `.git/` del repo, ni una base SQLite del repo. Los temporales de pytest quedan fuera.
# ---------------------------------------------------------------------------

REPO_TESTS = Path(__file__).resolve().parents[1]
SUBDIRS_PROTEGIDOS = ("data", "evidence", ".git")
SUFIJOS_SQLITE = (".db", ".sqlite", ".sqlite3")


class BorradoProhibidoEnTests(RuntimeError):
    """Un test intentó borrar datos protegidos del repositorio o del sistema."""


def ruta_prohibida(objetivo: Any, *, repo: Path = REPO_TESTS, home: Optional[Path] = None) -> Optional[str]:
    """Motivo por el que `objetivo` no se puede borrar en tests, o None si se puede."""

    try:
        real = Path(os.path.realpath(os.fspath(objetivo)))
    except TypeError:
        return None
    repo = repo.resolve()
    for protegida in (Path("/"), (home or Path.home()).resolve(), repo):
        if real == protegida or real in protegida.parents:
            return f"{real} es o contiene {protegida}"
    for sub in SUBDIRS_PROTEGIDOS:
        base = repo / sub
        if real == base or base in real.parents:
            return f"{real} está en {base}"
    nombre = real.name.lower()
    if repo in real.parents and any(nombre.endswith(s) or f"{s}." in nombre or f"{s}-" in nombre for s in SUFIJOS_SQLITE):
        return f"{real} es una base SQLite del repo"
    return None


def envolver_borrado(original: Callable[..., Any], nombre: str, *, repo: Path = REPO_TESTS) -> Callable[..., Any]:
    """Envuelve una función de borrado: comprueba la ruta antes de llamar a la original."""

    def guardada(ruta: Any, *args: Any, **kwargs: Any) -> Any:
        # Con dir_fd la ruta es relativa a un descriptor (uso interno de shutil.rmtree, ya comprobado arriba).
        if kwargs.get("dir_fd") is None:
            motivo = ruta_prohibida(ruta, repo=repo)
            if motivo is not None:
                raise BorradoProhibidoEnTests(f"{nombre} denegado en tests: {motivo}")
        return original(ruta, *args, **kwargs)

    for atributo in ("avoids_symlink_attacks",):
        if hasattr(original, atributo):
            setattr(guardada, atributo, getattr(original, atributo))
    return guardada


@pytest.fixture(autouse=True, scope="session")
def _red_de_seguridad_de_borrado() -> Iterator[None]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(shutil, "rmtree", envolver_borrado(shutil.rmtree, "shutil.rmtree"))
        mp.setattr(os, "remove", envolver_borrado(os.remove, "os.remove"))
        mp.setattr(os, "unlink", envolver_borrado(os.unlink, "os.unlink"))
        mp.setattr(os, "rmdir", envolver_borrado(os.rmdir, "os.rmdir"))
        yield
