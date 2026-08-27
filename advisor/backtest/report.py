"""Informe del backtest: qué habría hecho el asesor y si tuvo ventaja.

Todo el texto se construye con reglas sobre los números medidos; ninguna
conclusión sale de un modelo. Las advertencias metodológicas se imprimen
siempre: un backtest sin sus limitaciones a la vista invita a creerse la
cifra equivocada.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from advisor.analysis.opportunity import ACCION_COMPRAR, ACCION_DESCARTAR, ACCION_ESPERAR
from advisor.backtest.engine import BacktestTrade
from advisor.backtest.runner import BacktestResult

_LINE = "=" * 90
_THIN = "-" * 90

# Tramos de puntuación del sistema (§12): sirven para comprobar si la nota
# ordena los resultados o si es indiferente.
_SCORE_BUCKETS: List[Tuple[str, float, float]] = [
    ("< 50", 0.0, 50.0),
    ("50-59", 50.0, 60.0),
    ("60-69", 60.0, 70.0),
    ("70-79", 70.0, 80.0),
    ("≥ 80", 80.0, 101.0),
]

# Mínimo de operaciones para que una media merezca imprimirse como evidencia.
_MIN_SAMPLE = 10


def _n(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}".replace(".", ",")


def _mean(values: List[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def _stats_line(trades: List[BacktestTrade]) -> str:
    if not trades:
        return "sin operaciones"
    nets = [t.net_return_pct for t in trades]
    rs = [r for r in (t.r_multiple for t in trades) if r is not None]
    won = sum(1 for t in trades if t.won)
    mean_net = _mean(nets)
    mean_r = _mean(rs)
    holds = _mean([float(t.bars_held) for t in trades])
    assert mean_net is not None
    return (
        f"{len(trades)} operaciones | ganadoras {won / len(trades) * 100:.0f}% | "
        f"media {_n(mean_net, 2)}% | R medio {_n(mean_r, 2) if mean_r is not None else 'N/D'} | "
        f"{holds:.0f} velas de media"
    )


def _compound_pct(trades: List[BacktestTrade]) -> float:
    """Retorno compuesto de encadenar las operaciones (una posición a la vez)."""
    total = 1.0
    for trade in sorted(trades, key=lambda t: t.entry_date):
        total *= 1 + trade.net_return_pct / 100
    return (total - 1) * 100


def _exit_census(trades: List[BacktestTrade]) -> str:
    reasons: Dict[str, int] = {}
    for t in trades:
        reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
    return ", ".join(f"{k} {v}" for k, v in sorted(reasons.items(), key=lambda kv: -kv[1]))


def format_backtest_report(result: BacktestResult) -> str:
    lines: List[str] = [
        _LINE,
        f"BACKTEST — horizonte {result.horizonte} | periodo {result.period} | velas 1d | "
        f"{len(result.evaluated)} activos | coste {_n(result.cost_pct, 2)}% ida y vuelta",
        _LINE,
        "",
        "Advertencias: una posición por activo (las señales con posición abierta se pierden);",
        "sin deslizamiento; con stop y objetivo en la misma vela se asume stop (caso peor);",
        "sin señal asiática histórica (esa parte del contexto puntúa neutra);",
        "los niveles se fijan al entrar y no se recalculan, como indica el asesor.",
        "",
    ]

    # --- La política real: solo lo que el asesor habría marcado COMPRAR ---
    lines.append("## POLÍTICA REAL (solo señales COMPRAR)")
    operar = result.trades_operar
    lines.append(f"  {_stats_line(operar)}")
    if operar:
        lines.append(f"  Salidas: {_exit_census(operar)}")
        lines.append("")
        lines.append(f"  {'Activo':<12} {'n':>4} {'Compuesto':>12} {'Comprar y mantener':>20}")
        for symbol in result.evaluated:
            own = [t for t in operar if t.symbol == symbol]
            bh = result.buy_hold_pct.get(symbol)
            bh_txt = f"{_n(bh, 1)}%" if bh is not None else "N/D"
            comp = f"{_n(_compound_pct(own), 1)}%" if own else "—"
            lines.append(f"  {symbol:<12} {len(own):>4} {comp:>12} {bh_txt:>20}")
    lines.append("")

    # --- ¿Ordena la puntuación? ---
    todas = result.trades_todas
    lines.append("## ¿ORDENA LA PUNTUACIÓN? (todas las señales, sin filtros)")
    lines.append(f"  {'Tramo':<8} {'n':>5} {'Ganadoras':>10} {'Media neta':>11} {'R medio':>8}")
    bucket_means: Dict[str, Optional[float]] = {}
    for label, low, high in _SCORE_BUCKETS:
        subset = [t for t in todas if low <= t.score < high]
        if not subset:
            lines.append(f"  {label:<8} {0:>5} {'—':>10} {'—':>11} {'—':>8}")
            bucket_means[label] = None
            continue
        nets = [t.net_return_pct for t in subset]
        rs = [r for r in (t.r_multiple for t in subset) if r is not None]
        mean_net = _mean(nets)
        mean_r = _mean(rs)
        assert mean_net is not None
        won_pct = sum(1 for t in subset if t.won) / len(subset) * 100
        lines.append(
            f"  {label:<8} {len(subset):>5} {won_pct:>9.0f}% {_n(mean_net, 2):>10}% "
            f"{_n(mean_r, 2) if mean_r is not None else 'N/D':>8}"
        )
        bucket_means[label] = mean_net if len(subset) >= _MIN_SAMPLE else None
    lines.append("")

    # --- ¿Aportan los vetos? ---
    lines.append("## ¿APORTAN LOS VETOS? (mismas señales, agrupadas por la decisión del asesor)")
    accion_means: Dict[str, Optional[float]] = {}
    for accion in (ACCION_COMPRAR, ACCION_ESPERAR, ACCION_DESCARTAR):
        subset = [t for t in todas if t.accion == accion]
        lines.append(f"  {accion:<10} {_stats_line(subset)}")
        nets = [t.net_return_pct for t in subset]
        accion_means[accion] = _mean(nets) if len(subset) >= _MIN_SAMPLE else None
    lines.append("")

    if result.skipped:
        lines.append("## NO EVALUADOS")
        for symbol, reason in result.skipped:
            lines.append(f"  - {symbol}: {reason}")
        lines.append("")

    # --- Conclusión por reglas ---
    lines.append("## LECTURA (reglas sobre lo medido, sin IA)")
    for verdict in _verdicts(result, bucket_means, accion_means):
        lines.append(f"  - {verdict}")
    lines.append(_THIN)
    lines.append(
        "Resultados pasados sobre este grupo y periodo: no garantizan nada y con pocas "
        "operaciones el azar pesa más que el criterio."
    )
    lines.append(_LINE)
    return "\n".join(lines)


def _verdicts(
    result: BacktestResult,
    bucket_means: Dict[str, Optional[float]],
    accion_means: Dict[str, Optional[float]],
) -> List[str]:
    verdicts: List[str] = []
    operar = result.trades_operar

    if not operar:
        verdicts.append(
            "La política real no habría abierto ninguna operación en este periodo: "
            "no hay nada que medir sobre ella."
        )
    else:
        mean_net = _mean([t.net_return_pct for t in operar])
        assert mean_net is not None
        signo = "positiva" if mean_net > 0 else "negativa"
        muestra = "" if len(operar) >= _MIN_SAMPLE else f" (solo {len(operar)} operaciones: muestra insuficiente)"
        verdicts.append(f"Esperanza media por operación COMPRAR: {_n(mean_net, 2)}% — {signo}{muestra}.")

        bh_values = [v for v in result.buy_hold_pct.values() if v is not None]
        comps = [_compound_pct([t for t in operar if t.symbol == s]) for s in result.evaluated]
        if bh_values and comps:
            mean_bh = _mean(bh_values)
            mean_comp = _mean(comps)
            assert mean_bh is not None and mean_comp is not None
            rel = "por encima de" if mean_comp > mean_bh else "por debajo de"
            verdicts.append(
                f"Compuesto medio por activo {_n(mean_comp, 1)}% frente a {_n(mean_bh, 1)}% de comprar y "
                f"mantener: la política queda {rel} la referencia en este periodo."
            )

    alto = bucket_means.get("70-79") if bucket_means.get("70-79") is not None else bucket_means.get("≥ 80")
    bajos = [v for k, v in bucket_means.items() if k in ("< 50", "50-59") and v is not None]
    if alto is not None and bajos:
        bajo = sum(bajos) / len(bajos)
        if alto > bajo:
            verdicts.append(
                f"La puntuación ordena: los tramos ≥70 rinden de media {_n(alto, 2)}% frente a "
                f"{_n(bajo, 2)}% de los tramos <60."
            )
        else:
            verdicts.append(
                f"La puntuación NO ordena en este periodo: tramos ≥70 en {_n(alto, 2)}% frente a "
                f"{_n(bajo, 2)}% de los tramos <60. La nota no está demostrando ventaja."
            )

    comprar = accion_means.get(ACCION_COMPRAR)
    vetadas = [v for k, v in accion_means.items() if k != ACCION_COMPRAR and v is not None]
    if comprar is not None and vetadas:
        vetada_media = sum(vetadas) / len(vetadas)
        if comprar > vetada_media:
            verdicts.append(
                f"Los vetos aportan: lo que el asesor habría comprado rinde {_n(comprar, 2)}% frente a "
                f"{_n(vetada_media, 2)}% de lo vetado."
            )
        else:
            verdicts.append(
                f"Los vetos NO aportan en este periodo: lo comprado rinde {_n(comprar, 2)}% frente a "
                f"{_n(vetada_media, 2)}% de lo vetado."
            )

    if not verdicts:
        verdicts.append("Muestra insuficiente en todos los cortes: no se puede afirmar nada.")
    return verdicts
