"""Ocupación de los bloques P2.5 por la población de P3 (solo lectura, sin desenlaces).

Reconstruye la espina y el mapa de bloques exactamente como `capacity.py`
(`_temporal_block_lookup`) sobre la población del event study, y cuenta
cuántas señales caen en cada bloque para la población de A-02 y para la de P3
(tras D-51, D-52 y D-55, leída de los listados de exclusión de 06), con el
desglose de las excluidas por combinación de motivos. No calcula
ni lee net_R, salidas, expectancy ni scores.
"""
from __future__ import annotations

import csv
import sys
from collections import Counter

import advisor.research.event_study as es
from advisor.config import load_config
from advisor.data.freshness import mercado_para_simbolo
from advisor.data.sessions import session_date_of
from advisor.research.capacity import PROTOCOL_BLOCK_LENGTH_SESSIONS, _temporal_block_lookup
from advisor.research.vintage import load_vintage
from advisor.universe.loader import load_universe

VID = "071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841"
carpeta = sys.argv[1] if len(sys.argv) > 1 else "."
cfg = load_config("config.yaml")
uni = load_universe(cfg.universe_path)
vintage = load_vintage(VID)
es.evaluate_managed_event = lambda *a, **k: None
es.evaluate_potential_event = lambda *a, **k: None

for horizonte in ("swing", "medio"):
    res = es.run_event_study_on_vintage(cfg, uni, vintage, horizonte=horizonte, population_name="vigente")
    mapa = _temporal_block_lookup(res, PROTOCOL_BLOCK_LENGTH_SESSIONS[horizonte], uni)
    motivos_de = {}
    for motivo in ("excluded_crypto", "excluded_asia_missing", "excluded_trend_sma_history"):
        with open(f"{carpeta}/06-{motivo}-{horizonte}.tsv") as fh:
            for r in csv.DictReader(fh, delimiter="\t"):
                motivos_de.setdefault((r["activo"], r["sesion_senal"]), set()).add(motivo.removeprefix("excluded_"))
    a02 = Counter()
    p3 = Counter()
    por_motivo = Counter()
    for s in res.signals:
        bloque = mapa.block_for(s)
        a02[bloque] += 1
        a = s.observation.asset
        idx = vintage.by_symbol[a].signal_prices.index
        d = session_date_of(idx[s.observation.signal_idx], mercado_para_simbolo(uni.get(a), a)).isoformat()
        motivos = motivos_de.get((a, d))
        if motivos is None:
            p3[bloque] += 1
        else:
            por_motivo[(bloque, " ∩ ".join(sorted(motivos)))] += 1
    n_bloques = max(mapa.session_to_block.values()) + 1
    print(f"\n=== {horizonte} (bloque {PROTOCOL_BLOCK_LENGTH_SESSIONS[horizonte]} sesiones) ===")
    print("bloques en la espina:", n_bloques, "| sesiones del último:", mapa.sessions_in_block(n_bloques - 1))
    print("bloques con señales A-02:", len(a02), "| P3:", len(p3))
    etiquetas = sorted({k for _, k in por_motivo})
    print("bloque | señales A-02 | señales P3 | " + " | ".join(f"excluidas {k}" for k in etiquetas))
    for b in range(n_bloques):
        resto = " | ".join(str(por_motivo.get((b, k), 0)) for k in etiquetas)
        print(f"{b:6d} | {a02.get(b, 0):12d} | {p3.get(b, 0):10d} | {resto}")
