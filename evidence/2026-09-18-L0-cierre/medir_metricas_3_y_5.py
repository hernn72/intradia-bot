"""Mide sobre el universo real las metricas 1, 3 y 5 de GATE L0.

Usa el mismo camino que produccion (run_analysis), no una reimplementacion.
"""
from datetime import datetime, timezone

from advisor.analysis.analyzer import run_analysis
from advisor.analysis.levels import reward_risk, rr_at_least
from advisor.config import load_config
from advisor.data.market_data import MarketDataProvider
from advisor.universe.loader import load_universe

config = load_config("config.yaml")
universe = load_universe(config.universe_path)
provider = MarketDataProvider(config.request_min_interval_seconds)

print(f"instante={datetime.now(timezone.utc).isoformat()}")
print(f"min_rr={config.risk.min_rr_ratio}")

for horizonte in ("swing", "medio"):
    result = run_analysis(config, universe, provider, horizonte=horizonte)
    min_rr = config.risk.min_rr_ratio

    # --- METRICA 3: rr al entry_max nunca por debajo del minimo
    incumplen = []
    for o in result.opportunities:
        rr = reward_risk(o.levels.entry_max, o.levels.target2, o.levels.stop)
        if rr is None or not rr_at_least(rr, min_rr):
            incumplen.append((o.asset.symbol, o.levels.entry_max, o.levels.target2, o.levels.stop, rr))

    # --- METRICA 5: descartes sin codigo de motivo
    descartados = [o for o in result.opportunities if o.radar == "DESCARTAR"]
    sin_codigo = [o.asset.symbol for o in descartados if not o.discard_code]

    print(f"\n== {horizonte} ==")
    print(f"oportunidades={len(result.opportunities)} saltadas={len(result.skipped)}")
    print(f"METRICA 3 rr(entry_max) < min_rr: {len(incumplen)} casos {incumplen[:5]}")
    print(f"METRICA 5 descartes sin codigo: {len(sin_codigo)} de {len(descartados)} {sin_codigo[:5]}")
