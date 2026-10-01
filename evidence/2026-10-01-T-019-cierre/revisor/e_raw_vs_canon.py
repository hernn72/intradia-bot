import sys; sys.path.insert(0, ".")
import advisor.research.p3 as p3
from advisor.config import load_config
from advisor.universe.loader import load_universe
from advisor.research.vintage import load_vintage
cfg = load_config("config.yaml"); u = load_universe(cfg.universe_path); v = load_vintage(p3.DATA_VINTAGE_ID)
for h in ("swing", "medio"):
    res = p3.run_p3_event_study(cfg, u, v, h, with_outcomes=False)
    raw = [s.observation.score_value for s in res.signals]
    can = [p3.canonical_score(x) for x in raw]
    cr = p3.quintile_cuts(raw).values; cc = p3.quintile_cuts(can).values
    diff = sum(p3.quintile_of(r, cr) != p3.quintile_of(c, cc) for r, c in zip(raw, can))
    near = sum(1 for r in raw for c in cc if r != c and abs(r - c) < 1e-9)
    print(h, "cortes crudos", cr, "canónicos", cc, "señales que cambian de quintil crudo vs canónico:", diff, "valores crudos a <1e-9 de un corte sin ser iguales:", near)
