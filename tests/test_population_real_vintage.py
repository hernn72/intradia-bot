"""Integración de las tres poblaciones de laboratorio sobre la cosecha real.

T-013 lo exige: `vigente` ⊂ `d31` ⊂ `pre-d31` en número de señales, y **ninguna
señal puede cambiar de valor** entre poblaciones. Si una señal común cambia,
hay contaminación entre activos y eso es un defecto, no un resultado.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from advisor.config import load_config
from advisor.research.event_study import run_event_study_on_vintage
from advisor.research.population import resolve_research_population
from advisor.research.vintage import load_vintage
from advisor.universe.loader import load_universe

VINTAGE_ID = "071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841"

# Los tres que `docs/metodo-trabajo.md` seccion 3 fija para esto, mas una baja
# de D-35 y otra de D-31: sin ellas las tres poblaciones darian el mismo
# conjunto y la prueba de inclusion no probaria nada.
ANALIZABLES = ("AAPL", "SAP.DE", "SXR8.DE")
BAJA_D35 = "4GLD.DE"
BAJA_D31 = "SAN.MC"
CONTEXTO = ("^GSPC", "^STOXX", "^STOXX50E", "^VIX")


def _subconjunto(vintage, config):
    simbolos = set(ANALIZABLES) | {BAJA_D35, BAJA_D31} | set(CONTEXTO)
    return replace(
        vintage,
        by_symbol={s: v for s, v in vintage.by_symbol.items() if s in simbolos},
    )


def _ids(result) -> set[str]:
    return {signal.observation.signal_id for signal in result.signals}


def _por_id(result) -> dict[str, object]:
    return {signal.observation.signal_id: signal for signal in result.signals}


def test_las_tres_poblaciones_se_anidan_y_ninguna_senal_cambia_de_valor() -> None:
    vintage_dir = Path("data/vintages") / VINTAGE_ID
    if not (vintage_dir / "AAPL.csv").is_file():
        pytest.skip("data/vintages no está disponible")

    config = load_config("config.yaml")
    universe = load_universe(config.universe_path)
    vintage = _subconjunto(load_vintage(VINTAGE_ID), config)

    resultados = {
        nombre: run_event_study_on_vintage(
            config,
            resolve_research_population(universe, nombre),
            vintage,
            horizonte="swing",
        )
        for nombre in ("vigente", "d31", "pre-d31")
    }

    vigente, d31, pre_d31 = (_ids(resultados[n]) for n in ("vigente", "d31", "pre-d31"))

    # Inclusion estricta: cada poblacion historica solo puede ANADIR señales.
    assert vigente < d31 < pre_d31
    assert {r.observation.asset for r in resultados["vigente"].signals} == set(ANALIZABLES)
    assert {r.observation.asset for r in resultados["d31"].signals} == set(ANALIZABLES) | {BAJA_D35}
    assert {r.observation.asset for r in resultados["pre-d31"].signals} == set(ANALIZABLES) | {BAJA_D35, BAJA_D31}

    # Y lo que de verdad importa: una señal comun vale EXACTAMENTE lo mismo en
    # las tres. Reponer un activo no puede mover la nota de otro.
    base = _por_id(resultados["vigente"])
    for nombre in ("d31", "pre-d31"):
        otros = _por_id(resultados[nombre])
        for signal_id, señal in base.items():
            assert otros[signal_id] == señal, f"{signal_id} cambia de valor en {nombre}"
