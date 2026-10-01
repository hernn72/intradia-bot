import sys, copy, yaml; sys.path.insert(0, ".")
from advisor.config import load_config, ScoringConfig, scoring_for_requested_model, AdvisorConfig
from advisor.context.point_in_time import resolve_context_mode
from advisor.analysis.market_context import MarketContext
from advisor.analysis.scoring import compute_score
from advisor.run.manifest import config_hash
cfg = load_config("config.yaml")
print("activo:", cfg.scoring.score_model_version, "fundamentals:", cfg.scoring.fundamentals_enabled)
for h in ("swing", "medio", "intradia"):
    t = cfg.scoring.threshold_for(h); print(" ", h, t)
print("config_hash:", config_hash(cfg))
raw = yaml.safe_load(open("config.yaml"))
def attempt(label, mutate):
    d = copy.deepcopy(raw["scoring"]); mutate(d)
    try:
        ScoringConfig.model_validate(d); print("ACEPTADO (!)", label)
    except Exception as e:
        print("rechazado:", label, "->", " | ".join(str(e).splitlines()[1:3])[:220])
def v2_with_7060(d):
    d["score_model_version"] = "2.0"
    for h in d["thresholds"].values(): h["score_model_version"] = "2.0"
attempt("activar 2.0 con 70/60 calibrated:false", v2_with_7060)
def v2_null(d):
    d["score_model_version"] = "2.0"
    for h in d["thresholds"].values():
        h.update(score_model_version="2.0", calibrated=False, min_score_operar=None, min_score_vigilar=None, calibration_ref=None)
attempt("activar 2.0 con umbrales nulos", v2_null)
def v2_cal(d):
    d["score_model_version"] = "2.0"
    for h in d["thresholds"].values():
        h.update(score_model_version="2.0", calibrated=True, min_score_operar=57.6, min_score_vigilar=49.6, calibration_ref="x")
attempt("activar 2.0 con calibrated:true inventado", v2_cal)
inv = scoring_for_requested_model(cfg.scoring, "2.0")
print("investigación v2 desde config 1.0:", inv.score_model_version, {h: (inv.threshold_for(h).calibrated, inv.threshold_for(h).min_score_operar, inv.threshold_for(h).min_score_vigilar) for h in ("swing","medio","intradia")})
print("modo para 2.0 sin explícito:", resolve_context_mode("2.0", None))
try: resolve_context_mode("2.0", "legacy_v1"); print("ACEPTADO (!) v2+legacy")
except ValueError as e: print("rechazado v2+legacy:", e)
