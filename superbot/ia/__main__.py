"""CLI de Superbot IA: ``python -m superbot.ia pasada|decisiones|corpus|dashboard|telegram``.

``pasada`` nunca activa la cartera paper por sí sola (modo ``registro`` siempre, salvo que algo
externo ya la hubiera activado) — eso sigue exigiendo un llamador explícito, conforme a que la
cartera operativa no se activa en producción sin autorización."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import List, Optional

from advisor.config import load_config
from advisor.data.market_data import MarketDataProvider
from advisor.universe.loader import load_universe
from superbot.config import SuperbotConfig
from superbot.data import select_assets
from superbot.ia import telegram as telegram_mod
from superbot.ia.asesores import ClienteAnthropic, ClienteIA
from superbot.ia.cartera import CarteraIA
from superbot.ia.corpus import ejecutar_corpus
from superbot.ia.paquete import EstadoCartera
from superbot.ia.pasada import ejecutar_pasada
from superbot.ia.politica import PoliticaIA
from superbot.ia.registro import RegistroIA

CLAVE_ENV = "SUPERBOT_IA_API_KEY"


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _cliente(politica: PoliticaIA) -> Optional[ClienteIA]:
    clave = os.getenv(CLAVE_ENV, "").strip()
    return ClienteAnthropic(clave, politica) if clave else None


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m superbot.ia")
    parser.add_argument("--db", required=True)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pasada")
    sub.add_parser("decisiones")
    sub.add_parser("corpus").add_argument("--solo", help="casos separados por comas")
    parser_dashboard = sub.add_parser("dashboard")
    parser_dashboard.add_argument("--host", default="127.0.0.1")
    parser_dashboard.add_argument("--port", type=int, default=8766)
    parser_telegram = sub.add_parser("telegram")
    parser_telegram.add_argument("--test", action="store_true", help="envía un mensaje de prueba en vez de vaciar la cola")
    args = parser.parse_args(argv)

    politica = PoliticaIA()
    registro = RegistroIA(args.db, politica)
    if args.cmd == "decisiones":
        for fila in registro.decisiones():
            print(f"{fila['symbol']} {fila['tipo']} {fila['target_session']}: {fila['resolucion']} ({fila['motivo']})")
        return 0
    if args.cmd == "dashboard":
        from superbot.ia.dashboard import serve

        serve(args.db, politica, host=args.host, port=args.port)
        return 0
    if args.cmd == "telegram":
        notifier = telegram_mod.notifier_from_env()
        if args.test:
            ok = notifier.send_message(f"{telegram_mod.HEADER}\n\nMensaje de prueba.")
            print("Enviado" if ok else "No se pudo enviar (¿Telegram configurado?)")
            return 0 if ok else 1
        cartera_ia = CarteraIA(registro.conn)
        contadores = telegram_mod.flush(cartera_ia, notifier)
        print(json.dumps(contadores, ensure_ascii=False))
        return 0
    cliente = _cliente(politica)
    if args.cmd == "corpus":
        if cliente is None:
            print(f"Falta {CLAVE_ENV}", file=sys.stderr)
            return 2
        informe = ejecutar_corpus(cliente, politica, registro, args.solo.split(",") if args.solo else None)
        print(json.dumps(informe, ensure_ascii=False, indent=1))
        return 0 if informe["aprobados"] == informe["casos"] else 1

    config = load_config("config.yaml")
    universe = load_universe(config.universe_path)
    # Reconoce una cartera YA activada (por el dashboard, aparte): esto nunca la activa por sí
    # mismo, solo evita que el CLI ignore para siempre una activación hecha por otro medio.
    cartera_ia = CarteraIA(registro.conn)
    resultado = ejecutar_pasada(
        config=config,
        universe=universe,
        activos=select_assets(universe, SuperbotConfig()),
        proveedor=MarketDataProvider(config.request_min_interval_seconds),
        cliente=cliente,
        registro=registro,
        cartera=EstadoCartera(equity_eur=10_000.0, cash_eur=10_000.0),
        instante=_ahora(),
        reloj=_ahora,
        politica=politica,
        cartera_ia=cartera_ia,
    )
    print(json.dumps({"pasada": resultado.pasada_id, "status": resultado.status, "compras": resultado.compras,
                      "ventas": resultado.ventas, "incidencias": len(resultado.incidencias)}, ensure_ascii=False))
    return 0 if resultado.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
