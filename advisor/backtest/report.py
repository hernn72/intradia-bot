"""Informe del backtest: qué habría hecho el asesor y si tuvo ventaja.

Todo el texto se construye con reglas sobre los números medidos; ninguna
conclusión sale de un modelo. Las advertencias metodológicas se imprimen
siempre: un backtest sin sus limitaciones a la vista invita a creerse la
cifra equivocada.
"""

from __future__ import annotations

import statistics
from typing import Dict, List, Optional, Tuple

import numpy as np

from advisor.analysis.opportunity import (
    ACCION_COMPRAR,
    ACCION_DESCARTAR,
    ACCION_ESPERAR,
    ACCION_VERIFICAR_BROKER,
)
from advisor.backtest.engine import ACCIONES_OPERABLES, BacktestTrade
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


def _net_rs(trades: List[BacktestTrade]) -> List[float]:
    return [r for r in (t.net_r_multiple for t in trades) if r is not None]


def _ratio(numerator: float, denominator: float) -> str:
    if denominator == 0:
        return "∞" if numerator > 0 else "N/D"
    return _n(numerator / denominator, 2)


def _percentile(values: List[float], q: float) -> float:
    return float(np.percentile(values, q))


def _evidence_cell(value: Optional[float], n: int, decimals: int = 2, suffix: str = "") -> str:
    if n < _MIN_SAMPLE or value is None:
        return "—"
    return f"{_n(value, decimals)}{suffix}"


def _stats_line(trades: List[BacktestTrade]) -> str:
    if not trades:
        return "sin operaciones"
    rs = _net_rs(trades)
    won = sum(1 for t in trades if t.won)
    mean_r = _mean(rs)
    holds = _mean([float(t.bars_held) for t in trades])
    assert holds is not None
    if len(trades) < _MIN_SAMPLE or not rs:
        return (
            f"{len(trades)} operaciones | muestra insuficiente para evidencia económica | "
            f"{holds:.0f} velas de media"
        )
    winners = [r for r in rs if r > 0]
    losers = [r for r in rs if r < 0]
    total_r = sum(rs)
    median_r = statistics.median(rs)
    std_r = statistics.pstdev(rs) if len(rs) > 1 else 0.0
    gross_profit = sum(winners)
    gross_loss = abs(sum(losers))
    avg_winner = _mean(winners)
    mean_loser = _mean(losers)
    avg_loser = abs(mean_loser) if mean_loser is not None else None
    return (
        f"{len(trades)} operaciones | win rate {won / len(trades) * 100:.0f}% | "
        f"expectancy R {_n(mean_r, 2) if mean_r is not None else 'N/D'} | "
        f"profit factor {_ratio(gross_profit, gross_loss)} | "
        f"payoff {_ratio(avg_winner or 0.0, avg_loser or 0.0)} | "
        f"R mediana {_n(median_r, 2)} | R total {_n(total_r, 2)} | desv. R {_n(std_r, 2)} | "
        f"P10/P25/P50/P75/P90 "
        f"{_n(_percentile(rs, 10), 2)}/{_n(_percentile(rs, 25), 2)}/"
        f"{_n(_percentile(rs, 50), 2)}/{_n(_percentile(rs, 75), 2)}/{_n(_percentile(rs, 90), 2)} | "
        f"{holds:.0f} velas de media"
    )


def _compound_pct(trades: List[BacktestTrade]) -> float:
    """Retorno compuesto de encadenar las operaciones (una posición a la vez)."""
    total = 1.0
    for trade in sorted(trades, key=lambda t: t.entry_date):
        total *= 1 + trade.net_return_pp / 100
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
    lines.append(
        f"  {'Tramo':<8} {'n':>5} {'Win':>7} {'Expect.':>9} {'PF':>7} "
        f"{'Payoff':>8} {'Mediana':>9} {'Total R':>9} {'Desv.':>7}"
    )
    bucket_means: Dict[str, Optional[float]] = {}
    bucket_percentiles: Dict[str, Optional[Tuple[float, float, float, float, float]]] = {}
    for label, low, high in _SCORE_BUCKETS:
        subset = [t for t in todas if low <= t.score < high]
        if not subset:
            lines.append(f"  {label:<8} {0:>5} {'—':>7} {'—':>9} {'—':>7} {'—':>8} {'—':>9} {'—':>9} {'—':>7}")
            bucket_means[label] = None
            bucket_percentiles[label] = None
            continue
        rs = _net_rs(subset)
        mean_r = _mean(rs)
        winners = [r for r in rs if r > 0]
        losers = [r for r in rs if r < 0]
        won_pct = sum(1 for t in subset if t.won) / len(subset) * 100 if subset else 0.0
        avg_winner = _mean(winners)
        mean_loser = _mean(losers)
        avg_loser = abs(mean_loser) if mean_loser is not None else None
        enough = len(subset) >= _MIN_SAMPLE and bool(rs)
        lines.append(
            f"  {label:<8} {len(subset):>5} "
            f"{_evidence_cell(won_pct, len(subset), 0, '%'):>7} "
            f"{_evidence_cell(mean_r, len(subset)):>9} "
            f"{_ratio(sum(winners), abs(sum(losers))) if enough else '—':>7} "
            f"{_ratio(avg_winner or 0.0, avg_loser or 0.0) if enough else '—':>8} "
            f"{_evidence_cell(statistics.median(rs) if rs else None, len(subset)):>9} "
            f"{_evidence_cell(sum(rs) if rs else None, len(subset)):>9} "
            f"{_evidence_cell(statistics.pstdev(rs) if len(rs) > 1 else 0.0, len(subset)):>7}"
        )
        bucket_means[label] = mean_r if enough else None
        bucket_percentiles[label] = (
            (
                _percentile(rs, 10),
                _percentile(rs, 25),
                _percentile(rs, 50),
                _percentile(rs, 75),
                _percentile(rs, 90),
            )
            if enough
            else None
        )
    lines.append("")
    lines.append(f"  {'Tramo':<8} {'n':>5} {'P10 R':>8} {'P25 R':>8} {'P50 R':>8} {'P75 R':>8} {'P90 R':>8}")
    for label, low, high in _SCORE_BUCKETS:
        subset = [t for t in todas if low <= t.score < high]
        percentiles = bucket_percentiles[label]
        if percentiles is None:
            lines.append(f"  {label:<8} {len(subset):>5} {'—':>8} {'—':>8} {'—':>8} {'—':>8} {'—':>8}")
        else:
            p10, p25, p50, p75, p90 = percentiles
            lines.append(
                f"  {label:<8} {len(subset):>5} {_n(p10, 2):>8} {_n(p25, 2):>8} "
                f"{_n(p50, 2):>8} {_n(p75, 2):>8} {_n(p90, 2):>8}"
            )
    lines.append("")

    # --- ¿Aportan los vetos? ---
    lines.append("## ¿APORTAN LOS VETOS? (mismas señales, agrupadas por la decisión del asesor)")
    accion_means: Dict[str, Optional[float]] = {}
    for accion in (ACCION_COMPRAR, ACCION_VERIFICAR_BROKER, ACCION_ESPERAR, ACCION_DESCARTAR):
        subset = [t for t in todas if t.accion == accion]
        lines.append(f"  {accion:<10} {_stats_line(subset)}")
        accion_means[accion] = _mean(_net_rs(subset)) if len(subset) >= _MIN_SAMPLE else None
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
        mean_net_r = _mean(_net_rs(operar))
        assert mean_net_r is not None
        signo = "positiva" if mean_net_r > 0 else "negativa"
        muestra = "" if len(operar) >= _MIN_SAMPLE else f" (solo {len(operar)} operaciones: muestra insuficiente)"
        verdicts.append(f"Esperanza media por operación COMPRAR: {_n(mean_net_r, 2)} R — {signo}{muestra}.")

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
                f"La puntuación ordena: los tramos ≥70 rinden de media {_n(alto, 2)} R frente a "
                f"{_n(bajo, 2)} R de los tramos <60."
            )
        else:
            verdicts.append(
                f"La puntuación NO ordena en este periodo: tramos ≥70 en {_n(alto, 2)} R frente a "
                f"{_n(bajo, 2)} R de los tramos <60. La nota no está demostrando ventaja."
            )

    comprar = accion_means.get(ACCION_COMPRAR)
    vetadas = [v for k, v in accion_means.items() if k not in ACCIONES_OPERABLES and v is not None]
    if comprar is not None and vetadas:
        vetada_media = sum(vetadas) / len(vetadas)
        if comprar > vetada_media:
            verdicts.append(
                f"Los vetos aportan: lo que el asesor habría comprado rinde {_n(comprar, 2)} R frente a "
                f"{_n(vetada_media, 2)} R de lo vetado."
            )
        else:
            verdicts.append(
                f"Los vetos NO aportan en este periodo: lo comprado rinde {_n(comprar, 2)} R frente a "
                f"{_n(vetada_media, 2)} R de lo vetado."
            )

    if not verdicts:
        verdicts.append("Muestra insuficiente en todos los cortes: no se puede afirmar nada.")
    return verdicts
