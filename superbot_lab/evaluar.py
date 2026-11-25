"""CLI de la evaluación final: ``python -m superbot_lab.evaluar``."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence

from advisor.config import load_config
from advisor.data.market_data import MarketDataProvider
from advisor.research.vintage import freeze_vintage, load_vintage
from superbot.ia import madurez
from superbot.ia.medicion import REFERENCIA
from superbot_lab import evaluacion


def congelar(
    db: Path, cosecha_raiz: Path, *, raiz: Path = evaluacion._RAIZ,
    reloj: Optional[Callable[[], datetime]] = None,
    proveedor: Optional[Any] = None,
) -> Dict[str, Any]:
    db, raiz = db.resolve(), raiz.resolve()
    if Path.cwd().resolve() != raiz:
        raise evaluacion.EvaluacionDenegada("el directorio de trabajo no es la raíz autorizada")
    evaluacion._wal_limpio(db)
    ahora = evaluacion._ahora(reloj)
    instante = evaluacion._instante_base(db)
    if ahora.astimezone(timezone.utc).date() <= instante.astimezone(timezone.utc).date():
        raise evaluacion.EvaluacionDenegada("aún no están completas las barras del día del instante")
    evaluacion._sin_salidas(raiz)
    evaluacion._git_limpio(raiz)
    _cuenta, lista = evaluacion._puerta_madurez(db, instante)
    decisiones = evaluacion._decisiones_compra(db)
    cuantitativos = evaluacion._cuantitativos(decisiones)
    # Los que no tienen entrada vista también: con su serie se sabe si el gate la habría rechazado.
    sin_entrada = [e.decision_id for e in lista if e.categoria == "sin_entrada"]
    simbolos = {REFERENCIA}
    pares_fx: set[str] = set()
    for fila in decisiones:
        if fila[5] != 1 and int(fila[0]) not in sin_entrada:
            continue
        simbolos.add(str(fila[1]))
        moneda = str(cuantitativos[int(fila[0])].get("currency", "EUR"))
        if moneda != "EUR":
            par = f"EUR{moneda}=X"
            simbolos.add(par)
            pares_fx.add(par)
    config = load_config(raiz / "config.yaml")
    cliente = proveedor or MarketDataProvider(config.request_min_interval_seconds)
    resultado = freeze_vintage(
        sorted(simbolos), cliente, interval="1d", start=(madurez.CORTE.date() - timedelta(days=10)).isoformat(),
        end=(instante.astimezone(timezone.utc).date() + timedelta(days=1)).isoformat(),
        root_dir=cosecha_raiz, downloaded_at=ahora,
        request_context={"uso": "evaluación final contrafactual Superbot IA"},
    )
    salida: Dict[str, Any] = {
        "cosecha": resultado.data_vintage_id, "instante": instante.isoformat(),
        "base_sha256": evaluacion._sha(db), "failed": resultado.failed,
    }
    criticos = ({REFERENCIA} | pares_fx) & set(resultado.failed)
    if criticos:
        detalle = ", ".join(f"{s}: {m}" for s, m in sorted(resultado.failed.items()))
        raise evaluacion.EvaluacionDenegada("failed: " + detalle)
    vintage = load_vintage(resultado.data_vintage_id, root_dir=cosecha_raiz)
    salida["series_ausentes"] = evaluacion.series_inservibles(vintage, decisiones)
    evaluacion._comprobar_cosecha(
        resultado.data_vintage_id, cosecha_raiz, decisiones, instante, cuantitativos, salida["series_ausentes"],
        sin_entrada,
    )
    salida["aperturas_invalidadas"] = evaluacion.aperturas_invalidadas(vintage, decisiones, cuantitativos)
    # Lo que la autorización tendrá que justificar: solo calendario y precios de mercado.
    salida["episodios_truncados"] = [
        {"decision_id": e.decision_id, "symbol": e.symbol, "sesion_entrada": e.sesion.isoformat(),
         "sesion_20": None if e.fin is None else e.fin.isoformat()}
        for e in evaluacion.episodios_truncados(
            vintage, lista, evaluacion._rechazadas_por_gate(vintage, lista, cuantitativos),
        )
    ]
    return salida


def identidades(db: Path, *, raiz: Path = evaluacion._RAIZ) -> Dict[str, Any]:
    db, raiz = db.resolve(), raiz.resolve()
    evaluacion._wal_limpio(db)
    instante = evaluacion._instante_base(db)
    return {
        "criterio_sha256": evaluacion._sha(raiz / evaluacion._CRITERIO),
        "codigo_sha256": evaluacion.huella_evaluador(raiz),
        "base_sha256": evaluacion._sha(db), "instante": instante.isoformat(),
        "entorno": evaluacion._entorno(),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m superbot_lab.evaluar")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--cosecha-raiz", required=True, type=Path)
    sub = parser.add_subparsers(dest="orden", required=True)
    for nombre in ("puertas", "congelar", "identidades", "evaluar"):
        sub.add_parser(nombre)
    args = parser.parse_args(argv)
    try:
        if args.orden == "puertas":
            estado = evaluacion.puertas(args.db, cosecha_raiz=args.cosecha_raiz)
            print(json.dumps({**estado.__dict__, "permitida": estado.permitida}, ensure_ascii=False, default=str))
            return 0 if estado.permitida else 2
        if args.orden == "congelar":
            congelada = congelar(args.db, args.cosecha_raiz)
            if congelada["series_ausentes"]:
                print("series_ausentes: " + ", ".join(congelada["series_ausentes"]), file=sys.stderr)
            print(json.dumps(congelada, ensure_ascii=False))
            return 0
        if args.orden == "identidades":
            print(json.dumps(identidades(args.db), ensure_ascii=False, sort_keys=True))
            return 0
        resultado = evaluacion.evaluar(args.db, args.cosecha_raiz)
        print(json.dumps({"veredicto": resultado["veredicto"], "motivo": resultado["motivo"]}, ensure_ascii=False))
        return 0
    except (
        evaluacion.EvaluacionDenegada, OSError, ValueError, sqlite3.Error,
        TypeError, AttributeError, KeyError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
