"""METRICA 1 y 2 de GATE L0 sobre el universo real.

1. Un hueco falso es una ausencia que cae en un dia que NO es sesion de la
   plaza del propio activo. Debe ser 0.
2. Toda ausencia del 2026-09-07 queda atribuida a una causa.
"""
from datetime import date, datetime, timezone

from advisor.analysis.analyzer import run_analysis
from advisor.config import load_config
from advisor.data.calendars import expected_sessions, session_override_kind
from advisor.data.market_data import MarketDataProvider
from advisor.universe.loader import load_universe

config = load_config("config.yaml")
universe = load_universe(config.universe_path)
provider = MarketDataProvider(config.request_min_interval_seconds)
result = run_analysis(config, universe, provider, horizonte="swing")

print(f"instante={datetime.now(timezone.utc).isoformat()}")

falsos, ausencias_totales, por_fecha = [], 0, {}
for o in result.opportunities:
    f = o.data_freshness
    if f is None:
        continue
    mercado = o.asset.market
    for fecha in f.absent_reference_sessions:
        ausencias_totales += 1
        por_fecha.setdefault(fecha, []).append(o.asset.symbol)
        # la plaza estaba abierta ese dia?
        abierta = fecha in set(expected_sessions(mercado, fecha, fecha))
        if not abierta:
            falsos.append((o.asset.symbol, mercado, fecha, session_override_kind(mercado, fecha)))

print(f"ausencias totales={ausencias_totales} en {len(por_fecha)} fechas distintas")
print(f"METRICA 1 -- huecos falsos (plaza cerrada ese dia): {len(falsos)}")
for fila in falsos[:10]:
    print("   ", fila)

clave = date(2026, 9, 7)
afectados = por_fecha.get(clave, [])
print(f"METRICA 2 -- activos con ausencia el 2026-09-07: {len(afectados)}")
for s in afectados:
    o = next(x for x in result.opportunities if x.asset.symbol == s)
    abierta = clave in set(expected_sessions(o.asset.market, clave, clave))
    print(f"    {s:10} plaza={o.asset.market:6} abierta_ese_dia={abierta} calidad_reciente={o.data_quality.recent_completeness.value if o.data_quality else 'N/D'}")
