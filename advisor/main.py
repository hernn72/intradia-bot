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
from dataclasses import replace
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from advisor.analysis.analyzer import AnalysisResult, indicator_reference_sessions, run_analysis
from advisor.analysis.benchmark import resolve_benchmark_symbol
from advisor.analysis.opportunity import RADAR_OPERAR, Opportunity
from advisor.config import VALID_HORIZONTES, AdvisorConfig, load_config
from advisor.data.bar_diagnostics import (
    diagnose_all_saved_gaps,
    diagnose_bar,
    format_bar_diagnosis,
    format_many_bar_diagnoses,
)
from advisor.data.freshness import (
    MERCADO_DESCONOCIDO,
    FreshnessBucket,
    FreshnessRow,
    agrupar_frescura_por_fecha,
    calcular_frescura_serie,
    mercado_para_simbolo,
)
from advisor.data.fx import FxConverter
from advisor.data.market_data import MarketDataProvider
from advisor.deploy.systemd import DEFAULT_CONFIG_ENV, DEFAULT_SYSTEMD_DIR, find_systemd_drift, write_rendered_units
from advisor.events.calendar import EventCalendar, YahooEarningsSource
from advisor.events.passes import decide_event_pass, format_event_trigger
from advisor.report.formatter import format_report
from advisor.report.money import MoneyFormatter
from advisor.report.tracking import format_reviews, review_positions
from advisor.research.ablation import format_ablation_report, run_ablation
from advisor.research.capacity import (
    assess_capacity,
    format_capacity_report,
    format_preregistered_estimators,
    preregistered_estimators,
)
from advisor.research.event_study import format_event_study_report, run_event_study
from advisor.research.uncertainty import compare_target_geometry, format_paired_comparison
from advisor.research.vintage import freeze_vintage, select_symbols
from advisor.run.manifest import RunManifest, build_run_manifest, format_manifest_footer
from advisor.storage.db import AdvisorDB, verify_backup
from advisor.storage.migrations import LATEST_VERSION
from advisor.telegram.notifier import TelegramNotifier
from advisor.universe.loader import load_universe
from advisor.universe.models import Asset, Universe
from advisor.universe.vintage import universe_vintage_id, universe_vintage_payload

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
    quality = opportunity.data_quality

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
        "warnings": json.dumps(list(opportunity.warnings), ensure_ascii=False),
        "discard_code": opportunity.discard_code,
        "execution_code": opportunity.execution_code,
        "quality_freshness": quality.freshness.value if quality is not None else None,
        "quality_recent": quality.recent_completeness.value if quality is not None else None,
        "quality_historical": quality.historical_completeness.value if quality is not None else None,
        "execution_ready": quality.execution_readiness if quality is not None else None,
        "quality_period": quality.measurement_period if quality is not None else None,
        "quality_interval": quality.measurement_interval if quality is not None else None,
    }


def _persist(result: AnalysisResult, fx: FxConverter, db: AdvisorDB, manifest: RunManifest) -> int:
    created_at = result.generated_at.isoformat()
    rows = [opportunity_to_row(o, fx, created_at) for o in result.opportunities]
    freshness_rows = [freshness_row_to_measurement(row, created_at) for row in result.freshness_rows]
    saved, freshness_saved = db.insert_analysis_result(
        manifest,
        rows,
        freshness_rows,
    )
    logger.info("%d mediciones de frescura guardadas en %s", freshness_saved, db.path)
    return saved


def freshness_row_to_measurement(row: FreshnessRow, measured_at: str) -> Dict[str, Any]:
    """Convierte una fila de frescura a la forma persistida."""

    freshness = row.freshness
    quality = freshness.data_quality if freshness is not None else None
    return {
        "measured_at": measured_at,
        "symbol": row.symbol,
        "data_symbol": row.data_symbol,
        "market": row.market,
        "calendar": freshness.calendar if freshness is not None else None,
        "benchmark_symbol": freshness.strength_benchmark if freshness is not None else None,
        "last_bar_date": freshness.last_bar_date.isoformat() if freshness is not None else None,
        "natural_days": freshness.natural_days if freshness is not None else None,
        "sessions_approx": freshness.sessions_approx if freshness is not None else None,
        "may_be_partial_current_session": freshness.may_be_partial_current_session if freshness is not None else False,
        "absent_reference_sessions": [
            value.isoformat() for value in freshness.absent_reference_sessions
        ] if freshness is not None else [],
        "absent_recent_sessions": [
            value.isoformat() for value in freshness.absent_recent_sessions
        ] if freshness is not None else [],
        "reference_sessions_checked": freshness.reference_sessions_checked if freshness is not None else 0,
        "veto_window_sessions": freshness.veto_window_sessions if freshness is not None else 0,
        "quality": freshness.quality if freshness is not None else "SIN_DATO",
        "quality_freshness": quality.freshness.value if quality is not None else None,
        "quality_recent": quality.recent_completeness.value if quality is not None else None,
        "quality_historical": quality.historical_completeness.value if quality is not None else None,
        "execution_ready": quality.execution_readiness if quality is not None else None,
        "quality_period": quality.measurement_period if quality is not None else None,
        "quality_interval": quality.measurement_interval if quality is not None else None,
        "error": row.error,
    }


def cmd_analizar(args: argparse.Namespace, config: AdvisorConfig, universe: Universe) -> int:
    db = None if args.sin_guardar else AdvisorDB(config.db_path)
    manifest = build_run_manifest(
        command="analizar",
        config=config,
        universe=universe,
        schema_version=db.schema_version() if db is not None else LATEST_VERSION,
        timestamp=datetime.now(timezone.utc),
    )
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
        # `replace` y no un constructor a mano: reconstruir el resultado campo a
        # campo ya perdió `freshness_rows` en silencio, y con la IA activada
        # —que es como corre la Pi— eso dejaba el histórico de frescura vacío
        # sin que fallara nada.
        result = replace(
            result,
            opportunities=[redactadas.get(o.asset.symbol, o) for o in result.opportunities],
        )

    report = format_report(result, config, fx, _build_calendar(config))
    report = f"{report}\n{format_manifest_footer(manifest)}"
    print(report)

    if not args.sin_guardar:
        assert db is not None
        saved = _persist(result, fx, db, manifest)
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


def cmd_congelar_datos(args: argparse.Namespace, config: AdvisorConfig, universe: Universe) -> int:
    provider = MarketDataProvider(config.request_min_interval_seconds)
    groups: Optional[List[str]] = args.grupos.split(",") if args.grupos else None
    symbols: Optional[List[str]] = args.symbols.split(",") if args.symbols else None
    selected = select_symbols(universe, groups=groups, symbols=symbols)
    result = freeze_vintage(
        selected,
        provider,
        period=args.period,
        interval=args.interval,
        root_dir=args.data_dir,
        universe_vintage=universe_vintage_id(universe),
    )

    print(f"Cosecha congelada: {result.data_vintage_id}")
    print(f"Manifiesto: {result.manifest_path}")
    print(f"Símbolos correctos: {len(result.succeeded)}")
    if result.failed:
        print(f"Símbolos fallidos: {len(result.failed)}")
        for symbol, error in result.failed.items():
            print(f"- {symbol}: {error}")
    return 0


def cmd_frescura_datos(args: argparse.Namespace, config: AdvisorConfig, universe: Universe) -> int:
    provider = MarketDataProvider(config.request_min_interval_seconds)
    groups: Optional[List[str]] = args.grupos.split(",") if args.grupos else None
    assets = _assets_por_grupos(universe, groups)
    reference = datetime.now(timezone.utc)
    rows = medir_frescura_datos(
        assets,
        provider,
        config,
        reference,
        period=args.period,
        interval=args.interval,
    )
    print(format_frescura_datos(rows, reference))
    return 0


def cmd_frescura_historico(args: argparse.Namespace, config: AdvisorConfig, universe: Universe) -> int:
    db = AdvisorDB(config.db_path)
    rows = db.get_recent_freshness_measurements(symbol=args.symbol, limit=args.limit)
    print(format_frescura_historico(rows))
    return 0


def cmd_diagnosticar_barra(args: argparse.Namespace, config: AdvisorConfig, universe: Universe) -> int:
    provider = MarketDataProvider(config.request_min_interval_seconds)
    if args.todos_los_huecos:
        try:
            db = AdvisorDB(config.db_path, readonly=True)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        diagnoses = diagnose_all_saved_gaps(db=db, universe=universe, provider=provider, config=config)
        print(format_many_bar_diagnoses(diagnoses, measured_at=db.latest_freshness_measured_at()))
        return 0

    if not args.symbol or not args.fecha:
        raise ValueError("diagnosticar-barra requiere --symbol y --fecha, o --todos-los-huecos")
    asset = universe.get(args.symbol)
    if asset is None:
        raise ValueError(f"'{args.symbol}' no esta en el universo")
    diagnosis = diagnose_bar(asset, _parse_date(args.fecha), provider=provider, config=config)
    print(format_bar_diagnosis(diagnosis))
    return 0


def medir_frescura_datos(
    assets: List[Asset],
    provider: MarketDataProvider,
    config: AdvisorConfig,
    reference: datetime,
    period: str = "1mo",
    interval: str = "1d",
) -> List[FreshnessRow]:
    """Pide barras del activo y devuelve filas agrupables de frescura."""

    rows: List[FreshnessRow] = []
    for asset in assets:
        data_symbol = asset.data_symbol(reference)
        # El universo incluye los 19 activos de contexto, cuyas plazas (CBOE,
        # SNP, NYM, CCY...) no tienen calendario declarado. Un fallo de plaza
        # o de proveedor degrada ese activo, nunca la medición entera.
        market = MERCADO_DESCONOCIDO
        try:
            market = mercado_para_simbolo(asset, data_symbol)
            history = provider.get_history(data_symbol, period=period, interval=interval)
            benchmark_symbol = resolve_benchmark_symbol(asset, config.report)
            freshness = calcular_frescura_serie(
                history,
                reference,
                market=market,
                strength_benchmark=benchmark_symbol,
                recent_reference_sessions=indicator_reference_sessions(config),
                veto_window_sessions=config.data_quality.veto_window_sessions,
                asset_timezone=asset.timezone,
                settlement_minutes=config.data_quality.settlement_minutes,
                measurement_period=period,
                measurement_interval=interval,
                critical_latest_sessions=config.data_quality.critical_latest_sessions,
                high_after_sessions=config.data_quality.high_after_sessions,
                medium_after_sessions=config.data_quality.medium_after_sessions,
            )
            # Este camino mide el dato **crudo** del proveedor y no recorta la
            # barra no cerrada, que es justo lo que el comando existe para ver.
            # El analizador sí la recorta, así que su `DataQuality` y el que
            # saldría de aquí responden a preguntas distintas: publicarlo desde
            # este camino afirmaba un veredicto de ejecución que esta medición
            # no puede sostener, y para el mismo activo e instante decía
            # PARTIAL_BAR / no ejecutable donde el asesor decía FRESH /
            # ejecutable. Si `frescura-datos` debe recortar es una decisión
            # metodológica, no de implementación: queda como D-22 (propuesta).
            freshness = replace(freshness, data_quality=None)
        except Exception as exc:
            rows.append(FreshnessRow(asset.symbol, data_symbol, market, None, str(exc)))
            continue
        rows.append(
            FreshnessRow(
                symbol=asset.symbol,
                data_symbol=data_symbol,
                market=market,
                freshness=freshness,
            )
        )
    return rows


def _assets_por_grupos(universe: Universe, groups: Optional[List[str]]) -> List[Asset]:
    if groups is None:
        return universe.all_assets()
    unknown = [group for group in groups if group not in universe.groups]
    if unknown:
        raise ValueError(f"grupos desconocidos: {unknown}. Disponibles: {sorted(universe.groups)}")
    return [asset for group in groups for asset in universe.groups[group]]


def _parse_date(value: Optional[str]) -> date:
    if value is None:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"fecha inválida: {value!r}. Usa YYYY-MM-DD") from None


def cmd_pasada_evento(args: argparse.Namespace, config: AdvisorConfig, universe: Universe) -> int:
    if not config.events.enabled:
        logger.info("Pasada por evento autodescartada: calendario de eventos desactivado")
        return 0

    today = _parse_date(args.fecha)
    calendar = EventCalendar.load(config.events.path, YahooEarningsSource(today))
    db = AdvisorDB(config.db_path)
    decision = decide_event_pass(
        calendar,
        universe.analizables(),
        db,
        horizonte=args.horizonte,
        today=today,
    )

    for alerta in decision.health_alerts:
        logger.warning("Salud del calendario: %s", alerta)

    if not decision.should_run:
        logger.info("Pasada por evento autodescartada: %s", decision.discard_reason)
        return 0

    provider = MarketDataProvider(config.request_min_interval_seconds)
    fx = FxConverter(provider, config.base_currency)
    manifest = build_run_manifest(
        command="pasada-evento",
        config=config,
        universe=universe,
        schema_version=db.schema_version(),
        timestamp=datetime.now(timezone.utc),
    )
    result = run_analysis(config, universe, provider, horizonte=args.horizonte)

    if config.ai.enabled and not args.sin_ia:
        from advisor.ai.narrator import enrich_with_narrative

        a_redactar = result.by_radar(RADAR_OPERAR)[: config.report.top_n]
        redactadas = {o.asset.symbol: o for o in enrich_with_narrative(a_redactar, config.ai)}
        # `replace` y no un constructor a mano: reconstruir el resultado campo a
        # campo ya perdió `freshness_rows` en silencio, y con la IA activada
        # —que es como corre la Pi— eso dejaba el histórico de frescura vacío
        # sin que fallara nada.
        result = replace(
            result,
            opportunities=[redactadas.get(o.asset.symbol, o) for o in result.opportunities],
        )

    prefix = format_event_trigger(decision.events)
    if decision.health_alerts:
        prefix += "\nAlarmas de calendario: " + "; ".join(decision.health_alerts)
    report = prefix + "\n\n" + format_report(result, config, fx, calendar)
    report = f"{report}\n{format_manifest_footer(manifest)}"
    print(report)

    saved = _persist(result, fx, db, manifest)
    logger.info("%d recomendaciones guardadas en %s", saved, config.db_path)

    notifier = _build_notifier()
    if notifier.send_long_message(report):
        logger.info("Informe de evento enviado por Telegram")
        db.mark_event_passes_sent(decision.claimed_event_ids)
    else:
        logger.warning("El informe de evento no se pudo enviar por Telegram")

    return 0


def cmd_event_study(args: argparse.Namespace, config: AdvisorConfig, universe: Universe) -> int:
    result = run_event_study(
        config,
        universe,
        args.data_vintage_id,
        horizonte=args.horizonte,
        cost_pct=args.coste_pct,
        root_dir=args.data_dir,
    )
    print(format_event_study_report(result, format_preregistered_estimators(preregistered_estimators(result, universe=universe))))
    return 0


def cmd_verificar_backup(args: argparse.Namespace, config: AdvisorConfig, universe: Universe) -> int:
    del universe
    ok = verify_backup(config.db_path, args.ruta)
    if ok:
        print(f"Backup verificado: {args.ruta}")
        return 0
    print(f"Backup inválido: {args.ruta}", file=sys.stderr)
    return 1


def cmd_manifiesto(args: argparse.Namespace, config: AdvisorConfig, universe: Universe) -> int:
    del universe
    try:
        db = AdvisorDB(config.db_path, readonly=True)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    run = db.get_analysis_run(args.run_id)
    if run is None:
        print(f"No existe run_id: {args.run_id}", file=sys.stderr)
        return 1
    payload = dict(run)
    provider_versions = payload.get("provider_versions")
    if isinstance(provider_versions, str):
        payload["provider_versions"] = json.loads(provider_versions)
    payload["git_dirty"] = bool(payload["git_dirty"])
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    print("\nRecomendaciones:")
    for row in db.get_recommendations_for_run(args.run_id):
        print(f"- {row['symbol']} · {row['radar']} · {row['accion']} · score {row['score']:.2f}")
    return 0


def cmd_universo(args: argparse.Namespace, config: AdvisorConfig, universe: Universe) -> int:
    if args.vintage:
        print(format_universe_vintage(universe))
        return 0
    print(f"Activos: {len(universe.all_assets())}; analizables: {len(universe.analizables())}")
    return 0


def format_universe_vintage(universe: Universe) -> str:
    lines = [
        f"universe_vintage_id={universe_vintage_id(universe)}",
        "instrument_id | issuer_id | primary_symbol | primary_market | added_at | benchmark",
    ]
    for item in universe_vintage_payload(universe):
        lines.append(
            f"{item['instrument_id']} | {item['issuer_id']} | {item['primary_symbol']} | "
            f"{item['primary_market']} | {item['added_at']} | {item['benchmark'] or 'null'}"
        )
    return "\n".join(lines)


def cmd_capacidad_estadistica(args: argparse.Namespace, config: AdvisorConfig, universe: Universe) -> int:
    result = run_event_study(
        config,
        universe,
        args.data_vintage_id,
        horizonte=args.horizonte,
        cost_pct=args.coste_pct,
        root_dir=args.data_dir,
    )
    print(format_capacity_report(assess_capacity(result, universe=universe)))
    return 0


def cmd_ablacion_score(args: argparse.Namespace, config: AdvisorConfig, universe: Universe) -> int:
    result = run_event_study(
        config,
        universe,
        args.data_vintage_id,
        horizonte=args.horizonte,
        cost_pct=args.coste_pct,
        root_dir=args.data_dir,
    )
    print(format_ablation_report(run_ablation(result, universe=universe)))
    return 0


def cmd_comparacion_pareada(args: argparse.Namespace, config: AdvisorConfig, universe: Universe) -> int:
    comparison = compare_target_geometry(
        config,
        universe,
        args.data_vintage_id,
        horizonte=args.horizonte,
        cost_pct=args.coste_pct,
        root_dir=args.data_dir,
        target_multiples_b=_parse_float_list(args.multiplos_b),
        block_lengths=_parse_int_list(args.longitudes_bloque),
        seed=args.semilla,
        n_resamples=args.remuestreos,
        mode=args.modo,
    )
    print(format_paired_comparison(comparison))
    return 0


def cmd_render_systemd(args: argparse.Namespace, config: AdvisorConfig, universe: Universe) -> int:
    event_time = args.event_time or config.events.pasada_evento_hora
    write_rendered_units(output_dir=args.output_dir, config_env=args.config_env, event_time=event_time)
    return 0


def cmd_verificar_systemd(args: argparse.Namespace, config: AdvisorConfig, universe: Universe) -> int:
    event_time = args.event_time or config.events.pasada_evento_hora
    drift = find_systemd_drift(
        config_env=args.config_env,
        installed_dir=args.installed_dir,
        event_time=event_time,
    )
    if not drift:
        print("Unidades systemd alineadas con las plantillas versionadas.")
        return 0
    print("Desfase detectado en unidades systemd:")
    for item in drift:
        print(f"- {item}")
    return 1


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


_DIA_SEMANA = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def format_frescura_datos(rows: List[FreshnessRow], measured_at: Optional[datetime] = None) -> str:
    buckets = agrupar_frescura_por_fecha(rows)
    lines: List[str] = []
    if measured_at is not None:
        lines.append(f"Medición: {measured_at:%Y-%m-%d %H:%M:%S %Z}")
        lines.append("")

    lines.extend(["| Última barra | Símbolos | Plazas |", "|---|---|---|"])
    for bucket in buckets:
        lines.append(_freshness_bucket_row(bucket))

    dispersion = _market_dispersion_rows(rows)
    if dispersion:
        lines.append("")
        lines.append("Dispersión por plaza:")
        lines.append("| Plaza | Escalón mayoritario | No coinciden |")
        lines.append("|---|---|---|")
        for market, majority_date, mismatch_count, total_count in dispersion:
            lines.append(f"| {market} | {_fecha_corta(majority_date)} | {mismatch_count} / {total_count} |")

    lines.append("")
    lines.append("Detalle por símbolo:")
    lines.append("| Símbolo | Símbolo datos | Plaza | Última barra | Antigüedad | Calendario | Sesiones ausentes |")
    lines.append("|---|---|---|---|---|---|---|")
    for row in rows:
        lines.append(_freshness_detail_row(row))

    failed = [row for row in rows if row.error is not None]
    if failed:
        lines.append("")
        lines.append("Símbolos sin datos:")
        for row in failed:
            lines.append(f"- {row.symbol} ({row.data_symbol}, {row.market}): {row.error}")
    return "\n".join(lines)


def format_frescura_historico(rows) -> str:
    """Tabla legible del histórico acumulado de frescura."""

    lines = [
        "| Medición | Símbolo | Datos | Plaza | Última barra | Antigüedad | Calendario | Parcial | Sesiones ausentes | Error |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        absent = _decode_absent_sessions(row["absent_reference_sessions"])
        if row["error"]:
            age = "error"
        elif row["sessions_approx"] is None:
            age = "N/D"
        else:
            age = _sesiones_label(row["sessions_approx"])
        lines.append(
            f"| {row['measured_at']} | {row['symbol']} | {row['data_symbol']} | {row['market']} | "
            f"{row['last_bar_date'] or 'N/D'} | {age} | {row['calendar'] or 'sin calendario'} | "
            f"{'sí' if row['may_be_partial_current_session'] else 'no'} | "
            f"{', '.join(absent) if absent else 'sin sesiones ausentes'} | {row['error'] or ''} |"
        )
    if not rows:
        lines.append("| N/D | N/D | N/D | N/D | N/D | N/D | N/D | N/D | N/D | sin mediciones |")
    return "\n".join(lines)


def _decode_absent_sessions(raw: str) -> List[str]:
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(values, list):
        return []
    return [str(value) for value in values]


def _market_dispersion_rows(rows: List[FreshnessRow]) -> List[tuple[str, date, int, int]]:
    counts_by_market: Dict[str, Dict[date, int]] = {}
    for row in rows:
        if row.freshness is None:
            continue
        market_counts = counts_by_market.setdefault(row.market, {})
        last_bar_date = row.freshness.last_bar_date
        market_counts[last_bar_date] = market_counts.get(last_bar_date, 0) + 1

    result: List[tuple[str, date, int, int]] = []
    for market, date_counts in counts_by_market.items():
        majority_date, majority_count = max(date_counts.items(), key=lambda item: (item[1], item[0]))
        total_count = sum(date_counts.values())
        result.append((market, majority_date, total_count - majority_count, total_count))
    return sorted(result, key=lambda item: item[0])


def _freshness_bucket_row(bucket: FreshnessBucket) -> str:
    freshness = bucket.freshness
    return (
        f"| {_fecha_corta(bucket.last_bar_date)} ({_sesiones_label(freshness.sessions_approx)}) "
        f"| {bucket.symbols_count} | {bucket.markets_label} |"
    )


def _freshness_detail_row(row: FreshnessRow) -> str:
    if row.freshness is None:
        return f"| {row.symbol} | {row.data_symbol} | {row.market} | N/D | error | N/D | N/D |"
    freshness = row.freshness
    partial = "; barra de hoy posiblemente parcial" if freshness.may_be_partial_current_session else ""
    return (
        f"| {row.symbol} | {row.data_symbol} | {row.market} | "
        f"{freshness.last_bar_date.isoformat()} | {freshness.label}{partial} | "
        f"{freshness.calendar} | {_absent_sessions_label(freshness)} |"
    )


def _absent_sessions_label(freshness) -> str:
    if not freshness.calendar:
        return "sin calendario de referencia"
    if not freshness.absent_reference_sessions:
        return "sin sesiones ausentes recientes"
    return ", ".join(value.isoformat() for value in freshness.absent_reference_sessions)


def _fecha_corta(value: date) -> str:
    return f"{_DIA_SEMANA[value.weekday()]} {value.day:02d}"


def _sesiones_label(sessions_approx: int) -> str:
    if sessions_approx == 0:
        return "al día"
    if sessions_approx == 1:
        return "−1 sesión"
    return f"−{sessions_approx} sesiones"


def _parse_float_list(value: str) -> List[float]:
    try:
        return [float(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError:
        raise ValueError(f"lista de floats inválida: {value}") from None


def _parse_int_list(value: str) -> List[int]:
    try:
        return [int(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError:
        raise ValueError(f"lista de enteros inválida: {value}") from None


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

    congelar = sub.add_parser("congelar-datos", help="descarga y congela una cosecha de datos para investigación")
    congelar.add_argument("--grupos", help="grupos del universo separados por comas (por defecto, todos)")
    congelar.add_argument("--symbols", help="símbolos del universo separados por comas; tiene prioridad sobre --grupos")
    congelar.add_argument("--period", default="5y", help="rango solicitado a yfinance (1y, 5y, max...)")
    congelar.add_argument("--interval", default="1d", help="intervalo solicitado a yfinance (1d, 1wk...)")
    congelar.add_argument("--data-dir", default="data/vintages", help="directorio raíz de cosechas versionadas")
    congelar.set_defaults(func=cmd_congelar_datos)

    frescura = sub.add_parser("frescura-datos", help="mide el retraso de la última barra por plaza")
    frescura.add_argument("--grupos", help="grupos del universo separados por comas (por defecto, todos)")
    frescura.add_argument("--period", default="1mo", help="rango solicitado al proveedor (por defecto, 1mo)")
    frescura.add_argument("--interval", default="1d", help="intervalo solicitado al proveedor (por defecto, 1d)")
    frescura.set_defaults(func=cmd_frescura_datos)

    frescura_hist = sub.add_parser("frescura-historico", help="consulta el histórico persistido de frescura")
    frescura_hist.add_argument("--symbol", help="filtrar por símbolo")
    frescura_hist.add_argument("--limit", type=int, default=50, help="número máximo de filas")
    frescura_hist.set_defaults(func=cmd_frescura_historico)

    diagnosticar = sub.add_parser("diagnosticar-barra", help="diagnostica una barra ausente sin persistir nada")
    diagnosticar.add_argument("--symbol", help="símbolo del universo")
    diagnosticar.add_argument("--fecha", help="fecha de sesión YYYY-MM-DD")
    diagnosticar.add_argument(
        "--todos-los-huecos",
        action="store_true",
        help="diagnostica los huecos de la última pasada guardada",
    )
    diagnosticar.set_defaults(func=cmd_diagnosticar_barra)

    verificar_backup_parser = sub.add_parser("verificar-backup", help="verifica integridad y conteos de un backup SQLite")
    verificar_backup_parser.add_argument("--ruta", required=True, help="ruta del fichero .bak a verificar")
    verificar_backup_parser.set_defaults(func=cmd_verificar_backup)

    manifiesto = sub.add_parser("manifiesto", help="muestra el manifiesto y recomendaciones de una pasada")
    manifiesto.add_argument("--run-id", required=True, dest="run_id")
    manifiesto.set_defaults(func=cmd_manifiesto)

    universo_parser = sub.add_parser("universo", help="muestra metadatos del universo")
    universo_parser.add_argument("--vintage", action="store_true", help="imprime el universe_vintage_id y su lista")
    universo_parser.set_defaults(func=cmd_universo)

    event_study = sub.add_parser("event-study", help="mide señales potenciales sobre una cosecha congelada")
    event_study.add_argument("data_vintage_id", help="identificador de la cosecha congelada")
    event_study.add_argument("--horizonte", choices=["swing", "medio"], default="swing")
    event_study.add_argument("--coste-pct", type=float, default=0.2, dest="coste_pct",
                             help="coste de ida y vuelta en %%")
    event_study.add_argument("--data-dir", default="data/vintages", help="directorio raíz de cosechas versionadas")
    event_study.set_defaults(func=cmd_event_study)

    capacidad = sub.add_parser("capacidad-estadistica", help="evalúa el gate P2.5 sobre una cosecha congelada")
    capacidad.add_argument("data_vintage_id", help="identificador de la cosecha congelada")
    capacidad.add_argument("--horizonte", choices=["swing", "medio"], default="swing")
    capacidad.add_argument("--coste-pct", type=float, default=0.2, dest="coste_pct",
                           help="coste de ida y vuelta en %%")
    capacidad.add_argument("--data-dir", default="data/vintages", help="directorio raíz de cosechas versionadas")
    capacidad.set_defaults(func=cmd_capacidad_estadistica)

    ablacion = sub.add_parser("ablacion-score", help="diagnostica y ablaciona el RR dentro del score")
    ablacion.add_argument("data_vintage_id", help="identificador de la cosecha congelada")
    ablacion.add_argument("--horizonte", choices=["swing", "medio"], default="swing")
    ablacion.add_argument("--coste-pct", type=float, default=0.2, dest="coste_pct",
                          help="coste de ida y vuelta en %%")
    ablacion.add_argument("--data-dir", default="data/vintages", help="directorio raíz de cosechas versionadas")
    ablacion.set_defaults(func=cmd_ablacion_score)

    comparacion = sub.add_parser("comparacion-pareada", help="mide P2.6 con bootstrap por bloques pareados")
    comparacion.add_argument("data_vintage_id", help="identificador de la cosecha congelada")
    comparacion.add_argument("--horizonte", choices=["swing", "medio"], default="swing")
    comparacion.add_argument("--coste-pct", type=float, default=0.2, dest="coste_pct",
                             help="coste de ida y vuelta en %%")
    comparacion.add_argument("--data-dir", default="data/vintages", help="directorio raíz de cosechas versionadas")
    comparacion.add_argument("--multiplos-b", default="1.5,3.5,5.0",
                             help="target_atr_multiples de B separados por comas")
    comparacion.add_argument("--longitudes-bloque", default="40,60,80,120",
                             help="longitudes de bloque separadas por comas")
    comparacion.add_argument("--semilla", type=int, default=20260830, help="semilla entera reproducible")
    comparacion.add_argument("--remuestreos", type=int, default=2000, help="número de remuestreos bootstrap")
    comparacion.add_argument("--modo", choices=["replica", "completo"], default="replica")
    comparacion.set_defaults(func=cmd_comparacion_pareada)

    pasada_evento = sub.add_parser("pasada-evento", help="ejecuta una pasada extra solo si hoy hay eventos")
    pasada_evento.add_argument("--horizonte", choices=["swing", "medio"], default="swing")
    pasada_evento.add_argument("--fecha", help="fecha local YYYY-MM-DD; por defecto, la fecha local del proceso")
    pasada_evento.add_argument("--sin-ia", action="store_true", help="omitir la capa narrativa del agente IA")
    pasada_evento.set_defaults(func=cmd_pasada_evento)

    render_systemd = sub.add_parser("render-systemd", help="renderiza plantillas systemd con rutas locales")
    render_systemd.add_argument("--config-env", default=DEFAULT_CONFIG_ENV, help="EnvironmentFile externo de despliegue")
    render_systemd.add_argument("--output-dir", required=True, help="directorio donde escribir las unidades renderizadas")
    render_systemd.add_argument("--event-time", help="hora HH:MM de la pasada por evento; por defecto, config.yaml")
    render_systemd.set_defaults(func=cmd_render_systemd)

    verificar_systemd = sub.add_parser("verificar-systemd", help="compara systemd instalado contra plantillas resueltas")
    verificar_systemd.add_argument("--config-env", default=DEFAULT_CONFIG_ENV, help="EnvironmentFile externo de despliegue")
    verificar_systemd.add_argument("--installed-dir", default=DEFAULT_SYSTEMD_DIR, help="directorio systemd instalado")
    verificar_systemd.add_argument("--event-time", help="hora HH:MM de la pasada por evento; por defecto, config.yaml")
    verificar_systemd.set_defaults(func=cmd_verificar_systemd)

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
