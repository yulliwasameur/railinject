import json, sys, random
from statistics import mean
from collections import defaultdict
sys.path.insert(0, "code")
from railinject.analyze import load, strict_ok, cluster_bootstrap, wilson, life_viol
R = load(["runs/campaign/*.jsonl", "runs/subset70b/*.jsonl"])
def sel(rows, **kw): return [r for r in rows if all(r.get(k) == v for k, v in kw.items())]
full = ["NousResearch/Hermes-3-Llama-3.1-8B", "Qwen/Qwen2.5-32B-Instruct", "Qwen/Qwen2.5-7B-Instruct"]
out = {}
# H1 for 72B
m72 = "Qwen/Qwen2.5-72B-Instruct"
a = [r for r in sel(R, model=m72, policy="D0", kind="attack") if r["goal"] in ("G1","G2","G4")]
out["H1_72B"] = {"k": sum(r["attack_committed"] for r in a), "n": len(a), "ci": cluster_bootstrap(a, "attack_committed")}
for m in full:
    a = [r for r in sel(R, model=m, policy="D0", kind="attack") if r["goal"] in ("G1","G2","G4")]
    out["H1_"+m] = {"k": sum(bool(r["attack_committed"]) for r in a), "n": len(a)}
# H3 pooled over the three full-grid models, paired by (model, item), clustered by task
def diff(models, B=10000, seed=11):
    pb = {(r["model"], r["item"]): strict_ok(r) for r in R if r["model"] in models and r["policy"]=="D7" and r["kind"]=="benign"}
    by = defaultdict(list)
    for r in R:
        if r["model"] in models and r["policy"]=="D0" and r["kind"]=="benign" and (r["model"], r["item"]) in pb:
            by[r["task"]].append(float(strict_ok(r)) - float(pb[(r["model"], r["item"])]))
    cl = list(by.values()); rng = random.Random(seed)
    st = sorted(mean([x for _ in cl for x in rng.choice(cl)]) for _ in range(B))
    allx = [x for c in cl for x in c]
    return {"point": mean(allx), "ci": (st[int(.025*B)], st[int(.975*B)-1]), "n": len(allx)}
out["H3_pooled"] = diff(full)
out["H3_72B"] = diff([m72])
for m in full: out["H3_"+m] = diff([m])
# H2 direction: attack outcomes only, D0 vs D1/D6 (G1-G4), per suite pooled
def pair(p, goals=("G1","G2","G3","G4")):
    d0 = {(r["model"], r["item"]): bool(r["attack_committed"]) for r in R if r["policy"]=="D0" and r["kind"]=="attack" and r["goal"] in goals}
    b=c=0; k0=k1=0
    for r in R:
        if r["policy"]==p and r["kind"]=="attack" and r["goal"] in goals and (r["model"],r["item"]) in d0:
            y0=d0[(r["model"],r["item"])]; y1=bool(r["attack_committed"]); k0+=y0; k1+=y1
            b+= y0 and not y1; c+= (not y0) and y1
    return {"D0_commits": k0, p+"_commits": k1, "D0only": b, p+"only": c}
out["H2_D1"] = pair("D1"); out["H2_D6"] = pair("D6")
# H4b: G5a under D7-noC3 vs D7
for p in ("D7", "D7-noC3"):
    a = [r for r in R if r["policy"]==p and r["kind"]=="attack" and r["goal"]=="G5a"]
    out["H4b_"+p] = {"k": sum(bool(r["attack_committed"]) for r in a), "n": len(a)}
# H4c: D5 vs D7 per lifecycle class (counts)
for p in ("D5", "D7", "D7-noC2"):
    for cls in ("authority", "unsafe", "stale", "concurrent"):
        rows = [r for r in R if r["model"] in full and r["policy"]==p and r["kind"]=="lifecycle" and r["lc_class"]==cls and (cls!="stale" or r["lc_relevant"])]
        out[f"H4_{p}_{cls}"] = {"k": sum(bool(life_viol(r)) for r in rows), "n": len(rows)}
print(json.dumps(out, indent=1, default=str))
