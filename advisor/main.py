"""CLI del asesor de inversión.

    python -m advisor.main analizar --horizonte swing
    python -m advisor.main seguimiento
    python -m advisor.main abrir --symbol SAP.DE --precio 240.50 --cantidad 4 --tesis "..."
    python -m advisor.main cerrar --symbol SAP.DE --precio 255.00 --motivo "objetivo 2 alcanzado"
    python -m advisor.main posiciones

Este bot **no ejecuta órdenes**: produce recomendaciones para ejecutar a mano
en Trade Republic, y registra lo que decidas para poder seguirlo después.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

from advisor.analysis.analyzer import AnalysisResult, run_analysis
from advisor.analysis.opportunity import RADAR_OPERAR, Opportunity
from advisor.config import VALID_HORIZONTES, AdvisorConfig, load_config
from advisor.data.fx import FxConverter
from advisor.data.market_data import MarketDataProvider
from advisor.events.calendar import EventCalendar, YahooEarningsSource
from advisor.report.formatter import format_report
from advisor.report.money import MoneyFormatter
from advisor.report.tracking import format_reviews, review_positions
from advisor.storage.db import AdvisorDB
from advisor.telegram.notifier import TelegramNotifier
from advisor.universe.loader import load_universe
from advisor.universe.models import Universe

logger = logging.getLogger(__name__)


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # yfinance es muy ruidoso en INFO.
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def _load_env() -> None:
    """Carga ``.env`` si ``python-dotenv`` está disponible."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def _build_notifier() -> TelegramNotifier:
    return TelegramNotifier(
        bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        chat_id=os.getenv("TELEGRAM_CHAT_ID"),
    )


def opportunity_to_row(opportunity: Opportunity, fx: FxConverter, created_at: str) -> Dict[str, Any]:
    """Convierte una oportunidad en la fila que persiste ``AdvisorDB``."""

    money = MoneyFormatter(fx, opportunity.asset.currency)
    levels = opportunity.levels
    asset = opportunity.asset

    return {
        "created_at": created_at,
        "symbol": asset.symbol,
        "name": asset.name,
        "isin": asset.isin,
        "trade_republic": asset.trade_republic,
        "currency": asset.currency,
        "horizonte": opportunity.horizonte,
        "radar": opportunity.radar,
        "accion": opportunity.accion,
        "score": opportunity.score.value,
        "evaluable_max": opportunity.score.evaluable_max,
        "price": levels.price,
        "price_eur": money.eur_value(levels.price),
        "entry_max": levels.entry_max,
        "entry_max_eur": money.eur_value(levels.entry_max),
        "stop": levels.stop,
        "stop_eur": money.eur_value(levels.stop),
        "target2": levels.target2,
        "target2_eur": money.eur_value(levels.target2),
        "risk_pct": levels.risk_pp,
        "reward_pct": levels.reward_pct,
        "rr_ratio": levels.rr_ratio,
        "reasons": json.dumps(opportunity.decision_reasons, ensure_ascii=False),
    }


def _persist(result: AnalysisResult, fx: FxConverter, db: AdvisorDB) -> int:
    created_at = result.generated_at.isoformat()
    rows = [opportunity_to_row(o, fx, created_at) for o in result.opportunities]
    return db.insert_recommendations(rows)


def cmd_analizar(args: argparse.Namespace, config: AdvisorConfig, universe: Universe) -> int:
    provider = MarketDataProvider(config.request_min_interval_seconds)
    fx = FxConverter(provider, config.base_currency)

    groups: Optional[List[str]] = args.grupos.split(",") if args.grupos else None
    result = run_analysis(config, universe, provider, horizonte=args.horizonte, groups=groups)

    if config.ai.enabled and not args.sin_ia:
        from advisor.ai.narrator import enrich_with_narrative

        # Solo se enriquecen las que el informe desarrolla, que son las de
        # OPERAR dentro del top_n: el resto aparece como una línea de radar o
        # como un símbolo en la lista de descartados, sin narrativa. Redactar
        # la de un activo descartado cuesta una llamada al modelo que nadie
        # llega a leer.
        a_redactar = result.by_radar(RADAR_OPERAR)[: config.report.top_n]
        redactadas = {o.asset.symbol: o for o in enrich_with_narrative(a_redactar, config.ai)}
        result = AnalysisResult(
            generated_at=result.generated_at,
            horizonte=result.horizonte,
            interval=result.interval,
            context=result.context,
            opportunities=[redactadas.get(o.asset.symbol, o) for o in result.opportunities],
            skipped=result.skipped,
            overview=result.overview,
        )

    report = format_report(result, config, fx, _build_calendar(config))
    print(report)

    if not args.sin_guardar:
        db = AdvisorDB(config.db_path)
        saved = _persist(result, fx, db)
        logger.info("%d recomendaciones guardadas en %s", saved, config.db_path)

    if args.telegram:
        notifier = _build_notifier()
        if notifier.send_long_message(report):
            logger.info("Informe enviado por Telegram")
        else:
            logger.warning("El informe no se pudo enviar por Telegram")

    return 0


def _build_calendar(config: AdvisorConfig) -> Optional[EventCalendar]:
    """Calendario de eventos, o ``None`` si está desactivado o no se puede leer.

    Un calendario que no carga no debe impedir que salga el informe: los
    eventos enriquecen la recomendación, no la sostienen. Pero el fallo se
    registra, porque quedarse sin eventos en silencio es indistinguible de no
    tener ninguno.
    """

    if not config.events.enabled:
        return None
    try:
        calendar = EventCalendar.load(config.events.path, YahooEarningsSource())
    except (FileNotFoundError, ValueError) as exc:
        logger.warning("Calendario de eventos no disponible (%s): el informe saldrá sin eventos", exc)
        return None

    aviso = calendar.avisar_si_se_agota()
    if aviso:
        logger.warning("Calendario de eventos: %s", aviso)
    return calendar


def cmd_backtest(args: argparse.Namespace, config: AdvisorConfig, universe: Universe) -> int:
    from advisor.backtest.report import format_backtest_report
    from advisor.backtest.runner import run_backtest

    provider = MarketDataProvider(config.request_min_interval_seconds)
    groups: Optional[List[str]] = args.grupos.split(",") if args.grupos else None
    result = run_backtest(
        config, universe, provider,
        horizonte=args.horizonte, groups=groups,
        period=args.period, cost_pct=args.coste_pct,
    )
    print(format_backtest_report(result))
    return 0


def cmd_seguimiento(args: argparse.Namespace, config: AdvisorConfig, universe: Universe) -> int:
    provider = MarketDataProvider(config.request_min_interval_seconds)
    fx = FxConverter(provider, config.base_currency)
    db = AdvisorDB(config.db_path)

    reviews = review_positions(config, universe, db, provider)
    report = format_reviews(reviews, fx)
    print(report)

    if args.telegram:
        _build_notifier().send_long_message(report)

    return 0


def cmd_abrir(args: argparse.Namespace, config: AdvisorConfig, universe: Universe) -> int:
    asset = universe.get(args.symbol)
    if asset is None:
        print(f"'{args.symbol}' no está en el universo. Añádelo a {config.universe_path} antes de seguirlo.")
        return 1

    provider = MarketDataProvider(config.request_min_interval_seconds)
    fx = FxConverter(provider, config.base_currency)
    money = MoneyFormatter(fx, asset.currency)
    invested_native = args.precio * args.cantidad

    db = AdvisorDB(config.db_path)
    try:
        position_id = db.open_position(
            symbol=asset.symbol,
            name=asset.name,
            entry_price=args.precio,
            currency=asset.currency,
            quantity=args.cantidad,
            invested_eur=money.eur_value(invested_native),
            thesis=args.tesis,
            horizonte=args.horizonte,
            target=args.objetivo,
            stop=args.stop,
            catalyst=args.catalizador,
        )
    except ValueError as exc:
        print(f"No se pudo registrar la posición: {exc}")
        return 1

    print(f"Posición #{position_id} registrada: {asset.symbol} × {args.cantidad:g} a {money(args.precio)}")
    print(f"Invertido: {money(invested_native)}")
    if asset.trade_republic != "yes":
        print("⚠️ La disponibilidad de este activo en Trade Republic no está verificada en universe.yaml.")
    return 0


def cmd_cerrar(args: argparse.Namespace, config: AdvisorConfig, universe: Universe) -> int:
    db = AdvisorDB(config.db_path)
    try:
        db.close_position(args.symbol, args.precio, args.motivo)
    except ValueError as exc:
        print(f"No se pudo cerrar la posición: {exc}")
        return 1
    print(f"Posición en {args.symbol.upper()} cerrada a {args.precio:g} — {args.motivo}")
    return 0


def cmd_posiciones(args: argparse.Namespace, config: AdvisorConfig, universe: Universe) -> int:
    db = AdvisorDB(config.db_path)
    positions = db.list_open_positions()
    if not positions:
        print("No hay posiciones abiertas.")
        return 0

    print(f"{'Símbolo':<12} {'Cantidad':>10} {'Precio medio':>16} {'Abierta':>12}  Tesis")
    for row in positions:
        print(
            f"{row['symbol']:<12} {row['quantity']:>10g} "
            f"{row['entry_price']:>12.2f} {row['currency']:<3} {row['opened_at'][:10]:>12}  {row['thesis'][:40]}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="advisor",
        description="Asesor de inversión: detecta, puntúa y explica oportunidades para Trade Republic.",
    )
    parser.add_argument("--config", default="config.yaml", help="ruta de config.yaml")
    parser.add_argument("-v", "--verbose", action="store_true", help="log detallado")

    sub = parser.add_subparsers(dest="comando", required=True)

    analizar = sub.add_parser("analizar", help="analiza el universo y genera el informe")
    analizar.add_argument("--horizonte", choices=VALID_HORIZONTES, default="swing")
    analizar.add_argument("--grupos", help="grupos del universo separados por comas (por defecto, todos)")
    analizar.add_argument("--telegram", action="store_true", help="enviar el informe por Telegram")
    analizar.add_argument("--sin-ia", action="store_true", help="omitir la capa narrativa del agente IA")
    analizar.add_argument("--sin-guardar", action="store_true", help="no persistir las recomendaciones")
    analizar.set_defaults(func=cmd_analizar)

    backtest = sub.add_parser("backtest", help="simula las señales del asesor sobre el pasado y mide si tienen ventaja")
    backtest.add_argument("--horizonte", choices=["swing", "medio"], default="swing")
    backtest.add_argument("--grupos", help="grupos del universo separados por comas (por defecto, todos)")
    backtest.add_argument("--period", default="5y", help="histórico a simular (2y, 5y...); validar siempre en más de uno")
    backtest.add_argument("--coste-pct", type=float, default=0.2, dest="coste_pct",
                          help="coste de ida y vuelta en %% (Trade Republic: ~1 EUR por orden)")
    backtest.set_defaults(func=cmd_backtest)

    seguimiento = sub.add_parser("seguimiento", help="revisa las posiciones abiertas contra su tesis")
    seguimiento.add_argument("--telegram", action="store_true", help="enviar el informe por Telegram")
    seguimiento.set_defaults(func=cmd_seguimiento)

    abrir = sub.add_parser("abrir", help="registra una posición abierta manualmente en Trade Republic")
    abrir.add_argument("--symbol", required=True)
    abrir.add_argument("--precio", required=True, type=float, help="precio medio de compra, en la divisa del activo")
    abrir.add_argument("--cantidad", required=True, type=float)
    abrir.add_argument("--tesis", required=True, help="por qué se abre la posición")
    abrir.add_argument("--horizonte", choices=VALID_HORIZONTES, default="swing")
    abrir.add_argument("--objetivo", type=float, help="objetivo de precio")
    abrir.add_argument("--stop", type=float, help="stop de precio")
    abrir.add_argument("--catalizador", help="catalizador esperado")
    abrir.set_defaults(func=cmd_abrir)

    cerrar = sub.add_parser("cerrar", help="cierra una posición registrada")
    cerrar.add_argument("--symbol", required=True)
    cerrar.add_argument("--precio", required=True, type=float)
    cerrar.add_argument("--motivo", required=True)
    cerrar.set_defaults(func=cmd_cerrar)

    posiciones = sub.add_parser("posiciones", help="lista las posiciones abiertas")
    posiciones.set_defaults(func=cmd_posiciones)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    _configure_logging(args.verbose)
    _load_env()

    try:
        config = load_config(args.config)
        universe = load_universe(config.universe_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        return 2

    try:
        return args.func(args, config, universe)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
