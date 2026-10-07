"""CLI mínima de T-025: ``python -m paper <comando>`` (ficha §4, §16).

Ningún comando lee ``intradia.db`` ni las tablas selladas directamente: todo pasa por ``paper.visibility``.
Las salidas llevan la etiqueta SHADOW / PAPER.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence

from paper import LABEL

EXECUTOR_PATHS_T025 = ("paper", "advisor", "config.yaml", "universe.yaml", "exchange_overrides.yaml")
DEPENDENCY_PATHS = ("pyproject.toml", "requirements.txt")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _print(payload: object) -> None:
    print(LABEL)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def git_head(repo: Path = Path(".")) -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def code_identity_ok(t025_code_sha: str, repo: Path = Path(".")) -> bool:
    """El código económico de la cohorte es el de su ``t025_code_sha`` y el árbol está limpio (§13)."""

    diff = subprocess.run(["git", "diff", "--quiet", t025_code_sha, "HEAD", "--", *EXECUTOR_PATHS_T025], cwd=repo, check=False)
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--", *EXECUTOR_PATHS_T025],
                           cwd=repo, check=False, capture_output=True, text=True)
    return diff.returncode == 0 and dirty.returncode == 0 and not dirty.stdout.strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m paper", description=LABEL)
    parser.add_argument("--db", type=Path, required=True, help="ruta de paper.db (nunca intradia.db)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    init = sub.add_parser("init", help="crea paper.db, las cohortes B2/S2/C0/BH y el embargo de T-024")
    init.add_argument("--start", type=date.fromisoformat, required=True, help="fecha de inicio d de las cohortes")
    run = sub.add_parser("run", help="una ejecución asociada a una pasada programada")
    run.add_argument("--pass-ts", type=datetime.fromisoformat, required=True)
    run.add_argument("--source-run-id", default="")
    sub.add_parser("status", help="estado visible: cohortes, ejecuciones, alertas, épocas, sellados")
    signals = sub.add_parser("signals", help="señales ex ante con MARKET_PASS o rechazo de mercado")
    signals.add_argument("--since", default=None)
    telegram = sub.add_parser("telegram", help="mensaje shadow (por defecto solo lo imprime)")
    telegram.add_argument("--session", default=None)
    telegram.add_argument("--send", action="store_true")
    sub.add_parser("audit", help="reconstrucción completa; solo informa si coincide")
    outcomes = sub.add_parser("outcomes", help="desenlaces por la vía normal (falla si hay un sellado)")
    outcomes.add_argument("--cohort", required=True)
    outcomes.add_argument("--who", required=True)
    outcomes.add_argument("--purpose", required=True)
    breaker = sub.add_parser("seal-break", help="vía extraordinaria: ruptura del sellado registrada")
    breaker.add_argument("--cohort", required=True)
    breaker.add_argument("--who", required=True)
    breaker.add_argument("--purpose", required=True)
    breaker.add_argument("--i-understand-this-breaks-the-seal", dest="confirm", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    from paper.store import PaperStore

    if args.cmd == "init":
        from paper.contract import build_contracts
        from paper.environment import current_environment
        from paper.runner import init_cohorts

        store = PaperStore.open(args.db, create=True)
        ids = init_cohorts(store, build_contracts(args.start, git_head()), current_environment(), now=_now())
        _print({"cohortes": ids})
        return 0
    store = PaperStore.open(args.db)
    if args.cmd == "run":
        from advisor.data.market_data import MarketDataProvider
        from paper.environment import current_environment
        from paper.ingest import Provider
        from paper.runner import run_pass
        from paper.signals import policy_envs
        from paper.universe import load_p6_universe

        provider: Provider = MarketDataProvider()
        pass_ts = args.pass_ts if args.pass_ts.tzinfo else args.pass_ts.replace(tzinfo=timezone.utc)
        report = run_pass(store, load_p6_universe(), provider, pass_ts=pass_ts, clock=_now, code_sha=git_head(),
                          environment=current_environment(), envs=policy_envs(("B2", "S2", "C0")),
                          identity_ok=code_identity_ok, source_run_id=args.source_run_id)
        _print({"run_seq": report.run_seq, "status": report.status, "evaluaciones": report.evaluations,
                "comprobaciones_de_apertura": report.open_checks})
        return 0 if report.status == "OK" else 2
    if args.cmd == "status":
        from paper.visibility import visible_status

        _print(visible_status(store))
        return 0
    if args.cmd == "signals":
        from paper.visibility import visible_signals

        _print(visible_signals(store, since=args.since))
        return 0
    if args.cmd == "telegram":
        from paper.telegram import send, shadow_message

        text = shadow_message(store, session=args.session)
        print(text)
        if args.send:
            return 0 if send(text) else 3
        return 0
    if args.cmd == "audit":
        from paper.audit import replay
        from paper.universe import load_p6_universe
        from paper.visibility import is_sealed

        universe = load_p6_universe()
        results: List[dict] = []
        for row in store.rows("SELECT cohort_id, policy_id FROM paper_cohort ORDER BY policy_id"):
            replayed = replay(store, universe, row["cohort_id"])
            item = {"cohort": row["policy_id"], "coincide": replayed.match}
            if not is_sealed(store, row["cohort_id"]):
                item["detalle"] = replayed.as_dict()
            results.append(item)
        _print(results)
        return 0 if all(r["coincide"] for r in results) else 4
    if args.cmd == "outcomes":
        from paper.visibility import SealedError, read_outcomes

        try:
            _print(read_outcomes(store, args.cohort, who=args.who, purpose=args.purpose, now=_now()))
        except SealedError as exc:
            print(f"{LABEL}\nSELLADO: {exc}", file=sys.stderr)
            return 5
        return 0
    if args.cmd == "seal-break":
        from paper.visibility import SealedError, seal_break

        try:
            _print(seal_break(store, args.cohort, who=args.who, purpose=args.purpose, now=_now(), confirm=args.confirm))
        except SealedError as exc:
            print(f"{LABEL}\n{exc}", file=sys.stderr)
            return 5
        return 0
    return 1
