"""Pasada real de verificacion de T-018.

Uso: pasada.py [retirar]

Sin argumento: pasada real normal, que guarda las barras validadas.
Con `retirar`: la misma pasada real, envolviendo al proveedor de verdad para que
oculte la ultima sesion cerrada de los simbolos `.DE`, que es exactamente lo que
hace yfinance a las 06 UTC con las plazas europeas. Todo lo demas es real.
"""
import json
import sys
from datetime import datetime, timezone

from advisor.analysis.analyzer import run_analysis
from advisor.config import load_config
from advisor.data.bar_cache import CachedBarProvider, build_market_resolver
from advisor.data.fx import FxConverter
from advisor.data.market_data import MarketDataProvider
from advisor.data.sessions import _session_date, latest_expected_closed_session, market_timezone
from advisor.main import _persist
from advisor.run.manifest import build_run_manifest
from advisor.storage.db import AdvisorDB
from advisor.universe.loader import load_universe

S = "/private/tmp/claude-501/-Users-fer-Desktop-Trading-bot/486830be-d9ad-46eb-a521-250f465e74d9/scratchpad/t018"
RETIRAR = len(sys.argv) > 1 and sys.argv[1] == "retirar"

config = load_config(f"{S}/config.yaml")
universe = load_universe(config.universe_path)
reference = datetime.now(timezone.utc)


class ProveedorQueRetira(MarketDataProvider):
    def __init__(self, interval_seconds: float) -> None:
        super().__init__(interval_seconds)
        self.retiradas: dict[str, str] = {}

    def get_history(self, symbol, period="1y", interval="1d"):
        df = super().get_history(symbol, period=period, interval=interval)
        if not RETIRAR or not symbol.endswith(".DE") or interval != "1d":
            return df
        ultima = latest_expected_closed_session("XETRA", reference, settlement_minutes=20)
        zona = market_timezone("XETRA")
        posiciones = [p for p in range(len(df.index)) if _session_date(df.index[p], zona) == ultima]
        if not posiciones:
            return df
        self.retiradas[symbol] = ultima.isoformat()
        return df.drop(df.index[posiciones])


db = AdvisorDB(config.db_path)
crudo = ProveedorQueRetira(config.request_min_interval_seconds)
provider = CachedBarProvider(
    crudo,
    store=db,
    resolve_market=build_market_resolver(universe),
    reference=reference,
    settlement_minutes=config.data_quality.settlement_minutes,
    window_sessions=config.bar_cache.window_sessions,
    readjustment_tolerance=config.bar_cache.readjustment_tolerance,
)
manifest = build_run_manifest(
    command="analizar",
    config=config,
    universe=universe,
    schema_version=db.schema_version(),
    timestamp=reference,
)
result = run_analysis(config, universe, provider, horizonte="swing", now=reference)
_persist(result, FxConverter(provider, config.base_currency), db, manifest)

cache = result.bar_cache
servidos = {u.data_symbol: [d.isoformat() for d in u.served_from_cache] for u in cache.served_symbols}
etiqueta = "retirando la ultima sesion europea" if RETIRAR else "normal"
print(f"--- pasada {etiqueta} ({reference.isoformat()}) ---")
print("barras guardadas en esta pasada  :", len(cache.bars_to_store))
print("sesiones retiradas al proveedor  :", len(crudo.retiradas))
print("simbolos servidos por la cache   :", len(servidos))
print("barras servidas por la cache     :", cache.served_bars_count)
print("revisiones fijadas               :", len(cache.pinned_symbols))
print("reanclajes                       :", len(cache.reanchored))
print("fallos de cache                  :", len(cache.failed))
analizados = {row.data_symbol for row in result.freshness_rows}
nunca_analizados = sum(
    len(u.sessions_never_observed) for u in cache.never_observed_symbols if u.data_symbol in analizados
)
nunca_contexto = sum(
    len(u.sessions_never_observed)
    for u in cache.never_observed_symbols
    if u.data_symbol not in analizados
)
print("nunca observadas, analizados     :", nunca_analizados)
print("nunca observadas, contexto       :", nunca_contexto)
faltan = sorted(set(crudo.retiradas) - set(servidos))
print("retiradas que la cache NO restauro:", len(faltan), faltan[:8])
sobran = sorted(set(servidos) - set(crudo.retiradas))
print("servidas que nadie retiro         :", len(sobran), sobran[:8])
sufijo = "retirada" if RETIRAR else "normal"
with open(f"{S}/resumen-{sufijo}.json", "w") as fh:
    json.dump(
        {
            "instante": reference.isoformat(),
            "retiradas": crudo.retiradas,
            "servidos": servidos,
            "no_restauradas": faltan,
            "servidas_no_retiradas": sobran,
            "nunca_observadas_analizados": nunca_analizados,
            "nunca_observadas_contexto": nunca_contexto,
        },
        fh,
        indent=2,
        ensure_ascii=False,
    )
