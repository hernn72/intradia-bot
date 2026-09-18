"""Higiene de la línea 0, fase 15: lo que no puede volver a entrar en ``advisor/``.

Cada test es una casilla de la lista de la fase 15 convertida en guarda, para
que la limpieza no dure hasta el siguiente commit.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from advisor.analysis.execution import ABOVE_MAX_ENTRY, EXECUTABLE, evaluate_trade_at_entry
from advisor.analysis.levels import Levels, entry_max_for_rr
from advisor.config import PortfolioConfig, RiskConfig

RAIZ = Path(__file__).resolve().parent.parent / "advisor"
FICHEROS = sorted(RAIZ.rglob("*.py"))

# Una CLI imprime: ``main.py`` es su salida. En cualquier otro módulo un
# ``print`` es depuración olvidada.
FICHEROS_QUE_IMPRIMEN = {RAIZ / "main.py"}


def _llamadas_a_print(ruta: Path) -> list[int]:
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    return [
        nodo.lineno
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name) and nodo.func.id == "print"
    ]


def test_no_hay_prints_fuera_de_la_cli() -> None:
    culpables = {
        str(ruta.relative_to(RAIZ.parent)): lineas
        for ruta in FICHEROS
        if ruta not in FICHEROS_QUE_IMPRIMEN and (lineas := _llamadas_a_print(ruta))
    }
    assert culpables == {}, f"print() fuera de la CLI: {culpables}"


def test_no_hay_todos_sin_ficha_en_advisor() -> None:
    # Un TODO vale si nombra la ficha que lo recoge: ``TODO(T-015)``.
    patron = re.compile(r"\b(TODO|FIXME)\b(?!\(T-\d{3}\))")
    culpables = {
        str(ruta.relative_to(RAIZ.parent)): [
            n for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1) if patron.search(linea)
        ]
        for ruta in FICHEROS
    }
    culpables = {k: v for k, v in culpables.items() if v}
    assert culpables == {}, f"TODO/FIXME sin ficha: {culpables}"


def test_no_hay_type_ignore_en_advisor() -> None:
    culpables = [
        str(ruta.relative_to(RAIZ.parent))
        for ruta in FICHEROS
        if "type: ignore" in ruta.read_text(encoding="utf-8")
    ]
    assert culpables == [], f"type: ignore reaparece en {culpables}"


# --- Caso de regresión obligatorio de la línea 0: EXH1.DE -------------------
#
# Referencia 56,11 · stop 54,71 · target2 58,20 · min_rr 1,5.
# entry_max_rr = (58,20 + 1,5 · 54,71) / 2,5 = 140,265 / 2,5 = 56,106.
# Como la máxima técnica no interviene aquí, entry_max = 56,106 ≈ 56,11.


def _levels_exh1() -> Levels:
    # Los mismos niveles que usa la invariante 7 en tests/test_analysis.py.
    return Levels(
        price=56.11,
        entry_ideal_low=55.00,
        entry_ideal_high=56.11,
        entry_max=56.106,
        stop=54.71,
        invalidation_level=54.71,
        invalidation_reason="stop técnico",
        stop_basis="manual test",
        target1=57.20,
        target2=58.20,
        target3=59.10,
        risk_pp=2.4951,
        reward_pct=3.7248,
        rr_ratio=1.4929,
        extension_atr=None,
        chase=False,
        entry_max_tecnica=57.42,
        entry_max_rr=56.106,
        min_rr_ratio=1.5,
    )


@pytest.mark.parametrize(
    ("entry", "ejecutable", "motivo"),
    [
        (55.76, True, EXECUTABLE),
        (56.00, True, EXECUTABLE),
        (56.106, True, EXECUTABLE),
        (56.63, False, ABOVE_MAX_ENTRY),
    ],
)
def test_exh1_regresion_de_la_linea_0(entry: float, ejecutable: bool, motivo: str) -> None:
    levels = _levels_exh1()
    assert entry_max_for_rr(58.20, 54.71, 1.5) == pytest.approx(56.106)
    assert levels.entry_max == pytest.approx(56.106, abs=1e-3)

    execution = evaluate_trade_at_entry(
        levels=levels,
        entry_price=entry,
        risk=RiskConfig(),
        portfolio=PortfolioConfig(),
        label="test",
    )

    assert execution.executable is ejecutable
    assert execution.reason == motivo
