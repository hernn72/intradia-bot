"""Revisor final: comprobaciones aritméticas SOLO sobre artefactos agregados
publicados por #33 (no abre desenlaces por señal, no ejecuta P3)."""
import csv, json, math, random, sys
sys.path.insert(0, ".")
from advisor.research.bootstrap import bootstrap_block_mean_interval
T = "evidence/2026-09-30-T-019-paso3-p3/run/tablas/"
def rows(f):
    with open(T + f) as fh:
        lines = [l for l in fh if not l.startswith("#")]
    return list(csv.DictReader(lines, delimiter="\t"))
bq = rows("swing-bloque-x-quintil.tsv")
deltas = [float(r["Q5_mean_net_r"]) - float(r["Q1_mean_net_r"]) for r in bq]
print("bloques", [r["bloque"] for r in bq], "n=", len(deltas))
print("Δ bloque 3 =", deltas[0])
mean = sum(deltas) / len(deltas); print("media Δ (propia) =", repr(mean))
lo, hi = bootstrap_block_mean_interval([(d, 1) for d in deltas], seed=20260830, n_resamples=2000, confidence=0.95)
print("IC95 instrumento INV-14 sobre los 19 Δ publicados:", lo, hi, "anchura", hi - lo)
# reimplementación propia (mismo RNG y cuantiles que el instrumento, escrita aparte)
rng = random.Random(20260830); n = len(deltas); s = []
for _ in range(2000):
    idx = [rng.randrange(n) for _ in range(n)]; s.append(sum(deltas[i] for i in idx) / n)
s.sort(); lo2 = s[math.floor(0.025 * 2000)]; hi2 = s[math.ceil(0.975 * 2000) - 1]
print("IC95 reimplementado:", lo2, hi2)
# signo: Q5 por debajo de Q1 en cuántos bloques
print("bloques con Δ<0:", sum(d < 0 for d in deltas), "de", n)
# veredicto mecánico aplicado a mano en el orden de la tabla
w = hi - lo
print("NO CONCLUYENTE por anchura" if w > 0.20 else "anchura ≤ 0,20", "| bloques≥12:", n >= 12)
# activos
act = rows("swing-activos.tsv")
pos = sum(float(r["primario"]) > 0 for r in act if r["primario"])
calc = [r for r in act if r["delta_q5_q1"]]
print("activos", len(act), "primario>0", pos, "Δ calculable", len(calc), "Δ<0", sum(float(r["delta_q5_q1"]) < 0 for r in calc),
      "IC entero <0", sum(r["delta_ic_upper"] != "" and float(r["delta_ic_upper"]) < 0 for r in calc),
      "IC entero >0", sum(r["delta_ic_lower"] != "" and float(r["delta_ic_lower"]) > 0 for r in calc))
ia = rows("swing-intra-activo.tsv")
print("intra-activo por activo:", len(ia), "media<0:", sum(float(r["mean"]) < 0 for r in ia if r["mean"]))
reg = rows("swing-regiones.tsv"); print("regiones Δ<0:", [(r["grupo"], r["delta_q5_q1"][:7]) for r in reg])
d = json.load(open("evidence/2026-09-30-T-019-paso3-p3/run/p3-resultado.json"))
sw = d["horizontes"]["swing"]
print("intra global:", sw["intra_asset"]["primary"], sw["intra_asset"]["lower"], sw["intra_asset"]["upper"], sw["intra_asset"]["n_blocks"],
      sw["intra_asset"]["pares_calculables"], sw["intra_asset"]["pares_excluidos"], sw["intra_asset"]["bloques_sin_activos_calculables"])
# candidatos: ninguna condición 2/3/4 se cumple
for e in sw["calibration"]["evaluations"]:
    print("cand", e["candidato"], e["condiciones"], e["cumple_operar"])
# contadores derivados a mano de las salidas
def desc(o):
    return (len(o["quintiles"]) + len(o["adjacent_contrasts"]) + len(o["regions"]["primary"]) + len(o["regions"]["delta"])
            + len(o["assets"]["primary"]) + len(o["assets"]["delta"]) + 1 + len(o["intra_asset"]["by_asset"])
            + sum(len(a["quintiles"]) + 1 for a in o["ablations"].values()))
md = d["horizontes"]["medio"]
print("contadores a mano:", 1 + len(sw["calibration"]["bonferroni_family"]) + desc(sw), 1 + desc(md))
print("quintiles: primario Q1..Q5", [round(q["primary"]["mean"], 4) for q in sw["quintiles"]])
print("capacidad Q:", [(q["label"], q["capacidad"].get("verdict"), q["capacidad"].get("conclusive")) for q in sw["quintiles"]])
