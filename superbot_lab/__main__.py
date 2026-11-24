"""CLI del laboratorio: ``python -m superbot_lab congelar|comprobar|correr``.

``comprobar`` prepara los datos y solo informa de coberturas. ``correr`` abre desenlaces: exige el
sha256 del pre-registro y un árbol de git limpio, usa solo la cosecha fijada, escribe siempre en el
mismo sitio y no se repite.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from advisor.config import load_config
from advisor.data.market_data import MarketDataProvider
from advisor.research.vintage import load_vintage
from advisor.universe.loader import load_universe
from superbot.ia.medicion import REFERENCIA
from superbot_lab import datos_lab
from superbot_lab.simulador import BASE, CAPITAL_EUR, VARIANTES, Resultado, intervalo_diferencia, simular

COSECHA = "4506dc5df60bb1f6cbdaf6755e1b60c65c1ed25a1598e8f53f6afdf0e984869c"
RESULTADO = Path("evidence/superbot-ia/simulaciones-reglas/resultado.json")
PREREGISTRO = Path("docs/superbot-ia/SIMULACIONES-REGLAS.md")
NIVEL = 1.0 - 0.05 / len(VARIANTES)


def _git(*argumentos: str) -> str:
    return subprocess.run(["git", *argumentos], capture_output=True, text=True, check=True).stdout.strip()


def _resumen(r: Resultado) -> Dict[str, Any]:
    return {
        "equity_final": r.equity[-1], "exceso_eur": sum(r.exceso), "caida_maxima": r.caida_maxima(),
        "exposicion_media": sum(r.exposicion) / len(r.exposicion) / CAPITAL_EUR, "operaciones": len(r.operaciones),
        "positivas": sum(o.pnl_eur > 0 for o in r.operaciones), "candidatas": r.candidatas, "rechazadas": r.rechazadas,
        "costes_eur": r.costes_eur, "abiertas": r.abiertas,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m superbot_lab")
    parser.add_argument("--raiz", default="data/vintages-lab")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("congelar")
    sub.add_parser("comprobar")
    sub.add_parser("correr").add_argument("--prereg-sha256", required=True)
    args = parser.parse_args(argv)

    config = load_config("config.yaml")
    universe = load_universe(config.universe_path)
    if args.cmd == "congelar":
        hecho = datos_lab.congelar(config, universe, MarketDataProvider(config.request_min_interval_seconds), Path(args.raiz))
        print(json.dumps({"cosecha": hecho.data_vintage_id, "bien": len(hecho.succeeded), "mal": hecho.failed}))
        return 0
    if args.cmd == "correr":
        real = hashlib.sha256(PREREGISTRO.read_bytes()).hexdigest()
        if args.prereg_sha256 != real:
            print("El pre-registro no es el autorizado", file=sys.stderr)
            return 2
        if RESULTADO.exists():
            print("Ya hay un resultado: no se repite", file=sys.stderr)
            return 2
        if _git("status", "--porcelain", "--untracked-files=no"):
            print("Hay cambios sin comitear: el resultado no se podría atribuir a un código", file=sys.stderr)
            return 2
    vintage = load_vintage(COSECHA, root_dir=args.raiz)
    series, fichas, fx, informe = datos_lab.preparar(vintage, config, universe)
    if args.cmd == "comprobar":
        print(json.dumps(informe, ensure_ascii=False, indent=1))
        return 0
    referencia = datos_lab.cierres(vintage, REFERENCIA)
    salida: Dict[str, Any] = {
        "cosecha": COSECHA, "prereg_sha256": args.prereg_sha256, "code_sha": _git("rev-parse", "HEAD"), "nivel": NIVEL,
        "datos": informe,
    }
    for nombre, inicio in (("5a", datos_lab.INICIO_5A), ("2a", datos_lab.INICIO_2A)):
        base = simular(series, fichas, fx, referencia, BASE, inicio, datos_lab.FIN)
        bloque: Dict[str, Any] = {BASE.nombre: _resumen(base)}
        for regla in VARIANTES:
            r = simular(series, fichas, fx, referencia, regla, inicio, datos_lab.FIN)
            total, bajo, alto = intervalo_diferencia(r.exceso, base.exceso, nivel=NIVEL)
            bloque[regla.nombre] = {**_resumen(r), "diferencia_eur": total, "ic": [bajo, alto]}
        salida[nombre] = bloque
    RESULTADO.parent.mkdir(parents=True, exist_ok=True)
    RESULTADO.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    print(RESULTADO)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
