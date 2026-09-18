"""Reproducibilidad del backtest contra la cosecha real, si está disponible.

El test sintético de `tests/test_backtest.py` no llega a la política real: con
series inventadas el score rara vez alcanza COMPRAR, así que `POLICY_OPERAR`
queda vacía y esa mitad del contrato no se prueba. Aquí sí, sobre la cosecha de
verdad, acotado al grupo `cripto` para que la suite no se alargue.

Los CSV de la cosecha están en `.gitignore` y solo viven en el portátil; en un
clon limpio este módulo se salta entero.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from advisor.backtest.runner import run_backtest
from advisor.config import load_config
from advisor.research.vintage import load_vintage
from advisor.universe.loader import load_universe

VINTAGE_ID = "071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841"
GRUPO = ["cripto"]


def _cosecha_disponible() -> bool:
    # El `manifest.json` sí se commitea desde T-006, así que comprobar el
    # directorio no basta: hace falta un CSV real.
    return (Path("data/vintages") / VINTAGE_ID / "BTC-EUR.csv").is_file()


def test_dos_pasadas_sobre_la_cosecha_dan_las_mismas_operaciones() -> None:
    """Operación por operación y campo por campo, incluida la política real.

    Es el criterio de aceptación de T-015. Comparar totales no valdría: dos
    pasadas pueden sumar el mismo número de operaciones siendo distintas.
    """

    if not _cosecha_disponible():
        pytest.skip("data/vintages no está disponible")

    config = load_config("config.yaml")
    universe = load_universe(config.universe_path)

    primera = run_backtest(
        config, universe, None, horizonte="swing", groups=GRUPO,
        vintage=load_vintage(VINTAGE_ID),
    )
    segunda = run_backtest(
        config, universe, None, horizonte="swing", groups=GRUPO,
        vintage=load_vintage(VINTAGE_ID),
    )

    assert primera.trades_operar, "sin operaciones de la política real el test no probaría nada"
    assert primera.trades_operar == segunda.trades_operar
    assert primera.trades_todas == segunda.trades_todas
    assert primera.buy_hold_pct == segunda.buy_hold_pct
    assert primera.evaluated == segunda.evaluated
    assert primera.data_vintage_id == VINTAGE_ID
    assert primera.data_range == segunda.data_range
