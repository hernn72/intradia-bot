"""CLI de la cartera paper visible: ``python -m superbot <comando>``.

Comandos:
- ``init``: crea la cartera (capital, fecha de inicio) y congela la configuración.
- ``run``: descarga barras cerradas, ejecuta el ciclo completo y encola avisos.
- ``status``: resumen de cartera en texto.
- ``dashboard``: sirve el dashboard por HTTP o lo escribe a un fichero HTML.
- ``telegram``: envía los avisos pendientes o un mensaje de prueba.
"""

from __future__ import annotations

import argparse
import fcntl
import logging
import os
import sys
from contextlib import contextmanager
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional

from superbot import LABEL, notify
from superbot.config import SuperbotConfig
from superbot.store import SuperbotStore, utcnow_iso

DEFAULT_DB = Path("data/superbot/superbot.db")

logger = logging.getLogger("superbot")


def _db_path(args: argparse.Namespace) -> Path:
    return Path(args.db or os.getenv("SUPERBOT_DB") or DEFAULT_DB)


def cmd_init(args: argparse.Namespace) -> int:
    store = SuperbotStore(_db_path(args))
    config = replace(SuperbotConfig(), initial_capital_eur=args.capital)
    if args.grupos:
        config = replace(config, groups=args.grupos)
    today = datetime.now(timezone.utc).date()
    start = date.fromisoformat(args.start) if args.start else today
    if start > today:
        raise ValueError("la fecha de inicio no puede ser futura")
    store.initialize(config, start, retrospective=start < today)
    print(f"Cartera creada en {store.path}")
    print(f"  {LABEL}")
    print(f"  Estrategia {config.strategy_id} · capital {config.initial_capital_eur:,.2f} EUR · inicio {start}")
    if start < today:
        print("  ARRANQUE RETROSPECTIVO: la primera ejecución simulará las sesiones desde esa fecha.")
    return 0


@contextmanager
def _exclusive(db_path: Path) -> Iterator[bool]:
    """Lock de fichero compartido por ``run`` y ``telegram``: uno a la vez por base."""

    lock_path = db_path.with_name(db_path.name + ".lock")
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(lock_path, "w")  # noqa: SIM115 - se cierra con el with de abajo
    except OSError as exc:
        raise ValueError(f"no se puede crear el lock {lock_path}: {exc}") from exc
    with handle as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True


def cmd_run(args: argparse.Namespace) -> int:
    from advisor.data.market_data import MarketDataProvider
    from advisor.universe.loader import load_universe
    from superbot.data import FxHistory, load_series, select_assets
    from superbot.engine import PaperEngine

    db_path = _db_path(args)
    store = SuperbotStore(db_path)
    config = store.config()
    with _exclusive(db_path) as acquired:
        if not acquired:
            print("Otra ejecución de superbot está en curso; no se hace nada.", file=sys.stderr)
            return 2

        now = datetime.now(timezone.utc)
        live = {p["symbol"] for p in store.open_positions()} | {o["symbol"] for o in store.pending_orders()}
        assets = select_assets(load_universe(args.universe), config, extra_symbols=live)
        provider = MarketDataProvider(min_interval_seconds=args.intervalo)
        run_id = store.start_run()
        try:
            loaded = load_series(assets, provider, config, now)
            fx = FxHistory(provider, {s.currency for s in loaded.series.values()}, config.history_period)
            result = PaperEngine(store).process(loaded.series, fx, run_id, now.date())
            if result.bars:
                with store.transaction() as conn:
                    conn.execute(
                        "INSERT OR IGNORE INTO notifications (key, created_at, kind, text, status) "
                        "VALUES (?, ?, 'RESUMEN', ?, 'PENDING')",
                        (f"summary:{run_id}", utcnow_iso(), notify.summary_text(store)),
                    )
            detail = "; ".join(f"{s}: {e}" for s, e in sorted(loaded.errors.items()))[:4000]
            store.finish_run(run_id, "OK", len(loaded.series), len(loaded.errors), result.bars, detail)
        except BaseException as exc:
            # También Ctrl+C o el SIGTERM de systemd: la cartera ya hizo rollback,
            # pero la ejecución no debe quedar como RUNNING para siempre.
            store.finish_run(run_id, "ERROR", 0, 0, 0, repr(exc)[:4000])
            raise

        print(f"Ejecución {run_id}: {len(loaded.series)} símbolos con datos, {len(loaded.errors)} sin datos, "
              f"{result.bars} barras nuevas en {len(result.dates)} sesiones")
        for line in result.events[-50:]:
            print(f"  {line}")
        if args.telegram:
            counts = notify.flush(store, notify.notifier_from_env())
            print(f"Telegram: {counts}")
    print()
    print(notify.summary_text(store))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    print(notify.summary_text(SuperbotStore(_db_path(args))))
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    from superbot.dashboard import serve, write_html

    db_path = _db_path(args)
    SuperbotStore(db_path).config()  # falla pronto si la cartera no existe
    if args.output:
        write_html(db_path, Path(args.output))
        print(f"Dashboard escrito en {args.output}")
        return 0
    print(f"Dashboard en http://{args.host}:{args.port}/ (Ctrl+C para salir)")
    serve(db_path, host=args.host, port=args.port)
    return 0


def cmd_telegram(args: argparse.Namespace) -> int:
    notifier = notify.notifier_from_env()
    if not notifier.enabled:
        print("Telegram sin configurar (SUPERBOT_TELEGRAM_BOT_TOKEN/CHAT_ID o TELEGRAM_BOT_TOKEN/CHAT_ID).")
        return 1
    if args.prueba:
        ok = notifier.send_message(f"{notify.HEADER}\nMensaje de prueba.")
        print("enviado" if ok else "fallo al enviar")
        return 0 if ok else 1
    db_path = _db_path(args)
    store = SuperbotStore(db_path)
    store.config()
    with _exclusive(db_path) as acquired:
        if not acquired:
            print("Otra ejecución de superbot está en curso; reintenta luego.", file=sys.stderr)
            return 2
        counts = notify.flush(store, notifier)
    print(f"Telegram: {counts}")
    return 0 if counts["FAILED"] == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m superbot", description=f"Superbot paper visible — {LABEL}")
    parser.add_argument("--db", help=f"ruta de la base (por defecto $SUPERBOT_DB o {DEFAULT_DB})")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="crear la cartera")
    p_init.add_argument("--capital", type=float, default=SuperbotConfig().initial_capital_eur)
    p_init.add_argument("--start", help="fecha de inicio YYYY-MM-DD (por defecto hoy)")
    p_init.add_argument("--grupos", nargs="+", help="grupos del universo (por defecto usa europa asia etfs_etc)")
    p_init.set_defaults(func=cmd_init)

    p_run = sub.add_parser("run", help="ejecutar el ciclo completo")
    p_run.add_argument("--universe", default="universe.yaml")
    p_run.add_argument("--intervalo", type=float, default=0.5, help="segundos mínimos entre descargas")
    p_run.add_argument("--telegram", action="store_true", help="enviar los avisos al terminar")
    p_run.set_defaults(func=cmd_run)

    p_status = sub.add_parser("status", help="resumen de cartera")
    p_status.set_defaults(func=cmd_status)

    p_dash = sub.add_parser("dashboard", help="dashboard HTML")
    p_dash.add_argument("--host", default="127.0.0.1")
    p_dash.add_argument("--port", type=int, default=8765)
    p_dash.add_argument("--output", help="escribir el HTML a un fichero en vez de servirlo")
    p_dash.set_defaults(func=cmd_dashboard)

    p_tg = sub.add_parser("telegram", help="enviar avisos pendientes")
    p_tg.add_argument("--prueba", action="store_true", help="enviar solo un mensaje de prueba")
    p_tg.set_defaults(func=cmd_telegram)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
