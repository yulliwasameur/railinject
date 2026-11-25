import sys,json,collections
sys.path.insert(0,".")
from railinject.analyze import load
R=load(["runs/campaign/*.jsonl","runs/subset70b/*.jsonl"])
print("keys:",sorted(R[0].keys()))
A={};B={};C={}
for r in R:
    k=(r["policy"],r["item"],r["kind"],r.get("framing"))
    m=r["model"].split("/")[-1]
    sig=json.dumps([(d.get("tool"),d.get("decision"),d.get("args")) for d in r.get("decisions",[])],sort_keys=True,default=str)
    {"Qwen2.5-7B-Instruct":A,"Qwen2.5-32B-Instruct":B,"Hermes-3-Llama-3.1-8B":C}.get(m,{})[k]=(sig,r.get("utility"),r.get("attack_committed"),r.get("violation"),r.get("n_turns",r.get("turns")),r.get("tokens",r.get("usage")))
common=set(A)&set(B)
same=sum(A[k][0]==B[k][0] for k in common); sameo=sum(A[k][1:4]==B[k][1:4] for k in common)
print("7B vs 32B: common",len(common),"identical decision traces",same,"identical outcomes",sameo)
common=set(A)&set(C); print("7B vs Hermes: identical traces",sum(A[k][0]==C[k][0] for k in common),"of",len(common))
k=next(iter(set(A)&set(B))); print(k, A[k][4:], B[k][4:])
