import sys,json
sys.path.insert(0,".")
from railinject.analyze import load, strict_ok, life_viol
R=load(["runs/variance/*.jsonl"],any_temp=True)
from collections import defaultdict
g=defaultdict(list)
for r in R: g[(r["model"].split("/")[-1],r["policy"],r.get("run"),r["kind"])].append(r)
out={}
for k,v in sorted(g.items(),key=str):
    f=strict_ok if k[3]=="benign" else life_viol
    out[str(k)]=(round(sum(bool(f(r)) for r in v)/len(v),3),len(v))
print(json.dumps(out,indent=0))
