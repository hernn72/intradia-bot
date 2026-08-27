"""Seguimiento de posiciones abiertas.

Una vez que una idea entra en cartera deja de analizarse desde cero: lo que
se evalúa es si la información nueva **refuerza, no cambia, debilita o
invalida** la tesis con la que se abrió.

El veredicto es determinista y jerárquico: primero los hechos duros (stop
alcanzado, objetivo alcanzado) y solo después la lectura del sistema sobre el
activo. Los niveles guardados al abrir la posición no se mueven aquí: cambiar
un stop para justificar mantener una posición perdedora es exactamente lo que
este módulo debe impedir.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from advisor.analysis.analyzer import analyze_asset
from advisor.analysis.market_context import fetch_market_context
from advisor.config import AdvisorConfig
from advisor.data.fx import FxConverter
from advisor.data.market_data import MarketDataProvider
from advisor.report.money import MoneyFormatter
from advisor.storage.db import AdvisorDB
from advisor.universe.models import Universe

logger = logging.getLogger(__name__)

VERDICT_REFUERZA = "REFUERZA"
VERDICT_NO_CAMBIA = "NO CAMBIA"
VERDICT_DEBILITA = "DEBILITA"
VERDICT_INVALIDA = "INVALIDA"


@dataclass(frozen=True)
class PositionReview:
    """Revisión de una posición abierta."""

    position_id: int
    symbol: str
    name: str
    currency: str
    opened_at: str
    entry_price: float
    quantity: float
    price: float
    pnl_pct: float
    stop: Optional[float]
    target: Optional[float]
    score: Optional[float]
    verdict: str
    note: str
    thesis: str


def _verdict(
    price: float,
    entry_price: float,
    stop: Optional[float],
    target: Optional[float],
    score: Optional[float],
    config: AdvisorConfig,
) -> tuple:
    """Decide el veredicto y su explicación. Devuelve ``(veredicto, nota)``."""

    if stop is not None and price <= stop:
        return VERDICT_INVALIDA, f"stop alcanzado ({price:.2f} ≤ {stop:.2f}): la tesis ha fallado, procede salir"

    if target is not None and price >= target:
        return VERDICT_REFUERZA, f"objetivo alcanzado ({price:.2f} ≥ {target:.2f}): valorar toma de beneficios"

    if score is None:
        return VERDICT_NO_CAMBIA, "sin datos suficientes para repuntuar el activo; la tesis sigue en pie"

    if score < config.scoring.min_score_vigilar:
        return (
            VERDICT_DEBILITA,
            f"la puntuación ha caído a {score:.0f}, por debajo del mínimo de vigilancia "
            f"({config.scoring.min_score_vigilar:.0f})",
        )

    if score >= config.scoring.min_score_operar and price > entry_price:
        return VERDICT_REFUERZA, f"la puntuación se mantiene en {score:.0f} y la posición va a favor"

    return VERDICT_NO_CAMBIA, f"puntuación {score:.0f}: ni mejora ni deteriora la tesis original"


def review_positions(
    config: AdvisorConfig,
    universe: Universe,
    db: AdvisorDB,
    provider: MarketDataProvider,
    now: Optional[datetime] = None,
) -> List[PositionReview]:
    """Revisa todas las posiciones abiertas y persiste cada veredicto.

    Un activo que ya no esté en el universo, o del que no haya datos, se
    revisa igualmente con la información disponible en vez de omitirse: una
    posición abierta nunca debe desaparecer silenciosamente del seguimiento.
    """

    positions = db.list_open_positions()
    if not positions:
        return []

    timestamp = now or datetime.now(timezone.utc)
    context = fetch_market_context(provider, config.market_context)
    reviews: List[PositionReview] = []

    for row in positions:
        symbol = row["symbol"]
        asset = universe.get(symbol)
        score_value: Optional[float] = None
        price: Optional[float] = None

        if asset is not None:
            try:
                opportunity = analyze_asset(asset, config, provider, context, row["horizonte"])
            except Exception as exc:
                logger.warning("Seguimiento — no se pudo repuntuar %s: %s", symbol, exc)
            else:
                score_value = opportunity.score.value
                price = opportunity.snapshot.price
        else:
            logger.warning("Seguimiento — %s ya no está en el universo; solo se actualiza el precio", symbol)

        if price is None:
            price, _ = provider.get_last_close(symbol)

        if price is None:
            logger.error("Seguimiento — sin precio para %s: se omite la revisión de esta posición", symbol)
            continue

        entry_price = float(row["entry_price"])
        pnl_pct = (price / entry_price - 1) * 100
        verdict, note = _verdict(price, entry_price, row["stop"], row["target"], score_value, config)

        db.insert_review(
            position_id=int(row["id"]),
            price=price,
            pnl_pct=pnl_pct,
            verdict=verdict,
            score=score_value,
            note=note,
            created_at=timestamp,
        )

        reviews.append(
            PositionReview(
                position_id=int(row["id"]),
                symbol=symbol,
                name=row["name"],
                currency=row["currency"],
                opened_at=row["opened_at"],
                entry_price=entry_price,
                quantity=float(row["quantity"]),
                price=price,
                pnl_pct=pnl_pct,
                stop=row["stop"],
                target=row["target"],
                score=score_value,
                verdict=verdict,
                note=note,
                thesis=row["thesis"],
            )
        )

    return reviews


def format_reviews(reviews: List[PositionReview], fx: FxConverter) -> str:
    """Informe de seguimiento de posiciones abiertas."""

    width = 90
    lines: List[str] = ["=" * width, "SEGUIMIENTO DE POSICIONES ABIERTAS", "=" * width, ""]

    if not reviews:
        lines.append("No hay posiciones abiertas registradas.")
        lines.append("")
        lines.append("Registra una con:  python -m advisor.main abrir --symbol XXX --precio 00.00 --cantidad 0 --tesis \"...\"")
        lines.append("=" * width)
        return "\n".join(lines)

    for review in reviews:
        money = MoneyFormatter(fx, review.currency)
        lines.append(f"{review.symbol} — {review.name}")
        lines.append(f"  Abierta: {review.opened_at[:10]}  |  Cantidad: {review.quantity:g}")
        lines.append(f"  Precio medio: {money(review.entry_price)}")
        lines.append(f"  Precio actual: {money(review.price)}")
        lines.append(f"  Rentabilidad: {review.pnl_pct:+.1f}%".replace(".", ","))
        lines.append(f"  Stop: {money(review.stop)}  |  Objetivo: {money(review.target)}")
        lines.append(f"  Puntuación actual: {review.score:.0f}/100" if review.score is not None else "  Puntuación actual: N/D")
        lines.append(f"  Veredicto: **{review.verdict} LA TESIS** — {review.note}")
        lines.append(f"  Tesis original: {review.thesis}")
        lines.append("-" * width)

    lines.append("")
    lines.append("Los niveles mostrados son los que se fijaron al abrir la posición y no se han recalculado.")
    lines.append("=" * width)
    return "\n".join(lines)
