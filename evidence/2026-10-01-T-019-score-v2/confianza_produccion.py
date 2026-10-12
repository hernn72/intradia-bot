"""Cambio de `Opportunity.confianza` (D-46) en una pasada local de producción, sin persistir.

Recorre el camino de `analizar --sin-guardar --sin-ia` en proceso, sin Telegram ni base de datos,
y compara sobre los mismos snapshots la confianza antigua (ratio de la dimensión convicción de v1)
con la nueva de D-46 (cobertura de barras + indicadores presentes), que es la que calcula hoy
`Opportunity.confianza`.
"""

from __future__ import annotations

import hashlib
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from advisor.analysis.analyzer import run_analysis  # noqa: E402
from advisor.config import load_config  # noqa: E402
from advisor.main import _build_data_provider  # noqa: E402
from advisor.run.manifest import config_hash  # noqa: E402
from advisor.universe.loader import load_universe  # noqa: E402

OUT = Path(__file__).resolve().parent
PASO2 = ROOT / "evidence/2026-09-30-T-019-paso2/confidence_impact.txt"
LABELS = ("Alta", "Media", "Baja")
ORDER = {"Baja": 0, "Media": 1, "Alta": 2}


def _label(ratio: float, missing: int) -> str:
    if missing == 0 and ratio >= 0.8:
        return "Alta"
    if missing <= 1 and ratio >= 0.6:
        return "Media"
    return "Baja"


def _old(opportunity: Any) -> Tuple[str, float]:
    conviccion = next(d for d in opportunity.score.dimensions if d.name == "conviccion")
    ratio = conviccion.points / conviccion.weight
    return _label(ratio, len(opportunity.score.missing_dimensions)), ratio


def _new_components(opportunity: Any) -> Tuple[float, int]:
    min_bars = opportunity.confidence_min_bars
    coverage = min(1.0, opportunity.snapshot.bars / min_bars) if min_bars > 0 else 1.0
    snap = opportunity.snapshot
    present = sum(
        1 for value in (snap.ema_fast, snap.ema_slow, snap.sma_long, snap.rsi, snap.atr, snap.macd_hist) if value is not None
    )
    return coverage, present


def main() -> None:
    cfg = load_config("config.yaml")
    universe = load_universe(cfg.universe_path)
    reference = datetime.now(timezone.utc)
    lines: List[str] = [
        "# Confianza (D-46): cosecha y pasada local de producción",
        "",
        "## Cosecha congelada (paso 2, sin rehacer)",
        "",
        f"`{PASO2.relative_to(ROOT)}`, sha256 `{hashlib.sha256(PASO2.read_bytes()).hexdigest()}`.",
        "Método: event study v1 sin desenlaces sobre la población A-02; fórmula antigua frente a D-46.",
        "",
        "```text",
        PASO2.read_text(encoding="utf-8").strip(),
        "```",
        "",
        "## Pasada local de producción",
        "",
        f"- `timestamp_utc` de referencia: `{reference.isoformat()}`",
        f"- `config_hash`: `{config_hash(cfg)}` (`score_model_version` activa: `{cfg.scoring.score_model_version}`)",
        "- Camino: `run_analysis` en proceso, equivalente a `analizar --sin-guardar --sin-ia`; sin Telegram,",
        "  sin base de datos (la caché de barras no actúa), sin Pi, sin cambiar configuración.",
        "- Producción ejecuta solo swing; medio se añade como comprobación del mismo camino.",
        "- Antigua: ratio de la dimensión convicción de Score v1 (barras, indicadores y volatilidad).",
        "  Nueva (D-46, `Opportunity.confianza`): cobertura de barras e indicadores presentes, sin ATR.",
        "  En ambas, la dimensión fundamental ausente cuenta como dimensión que falta.",
        "",
    ]
    for horizonte in ("swing", "medio"):
        provider = _build_data_provider(cfg, universe, None, reference=reference)
        result = run_analysis(cfg, universe, provider, horizonte=horizonte, groups=None, now=reference)
        matrix: Counter[Tuple[str, str]] = Counter()
        reasons: Counter[str] = Counter()
        missing_dims: Counter[Tuple[str, ...]] = Counter()
        coverage_full = 0
        indicators: Counter[int] = Counter()
        changes: List[str] = []
        for opp in result.opportunities:
            old, old_ratio = _old(opp)
            new = opp.confianza
            coverage, present = _new_components(opp)
            matrix[(old, new)] += 1
            missing_dims[tuple(opp.score.missing_dimensions)] += 1
            coverage_full += coverage >= 1.0
            indicators[present] += 1
            if old == new:
                reasons["sin cambio"] += 1
                continue
            causes = []
            if coverage < 1.0:
                causes.append(f"cobertura de barras {coverage:.3f}")
            if present < 6:
                causes.append(f"indicadores presentes {present}/6")
            if not causes:
                causes.append("la convicción antigua penalizaba la volatilidad (ATR), que D-46 retira")
            reason = "; ".join(causes)
            reasons[f"{old}→{new}: {reason}"] += 1
            changes.append(f"| {opp.asset.symbol} | {old} ({old_ratio:.3f}) | {new} | {reason} |")
        lines += [
            f"### {horizonte}",
            "",
            f"Oportunidades evaluadas: {len(result.opportunities)}; activos omitidos por la pasada: {len(result.skipped)}.",
            "",
            "| antigua \\ nueva | " + " | ".join(LABELS) + " |",
            "|---|---|---|---|",
        ]
        for old in LABELS:
            lines.append(f"| {old} | " + " | ".join(str(matrix[(old, new)]) for new in LABELS) + " |")
        total_changes = sum(n for (old, new), n in matrix.items() if old != new)
        lines += [
            "",
            f"**Cambios: {total_changes}.**",
            "",
            "Motivos:",
            *[f"- {reason}: {n}" for reason, n in sorted(reasons.items())],
            "",
            "Componentes sobre los mismos snapshots:",
            "- dimensiones que faltan: "
            + "; ".join(f"{', '.join(dims) or 'ninguna'} = {n}" for dims, n in sorted(missing_dims.items())),
            f"- cobertura de barras completa: {coverage_full} de {len(result.opportunities)}",
            "- indicadores presentes: " + ", ".join(f"{k}/6 = {n}" for k, n in sorted(indicators.items())),
            "",
        ]
        if changes:
            lines += ["| activo | antigua (ratio) | nueva | motivo |", "|---|---|---|---|", *changes, ""]
    output = "\n".join(lines) + "\n"
    (OUT / "confianza.md").write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
