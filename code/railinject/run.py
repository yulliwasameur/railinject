"""Campaign runner. One line of JSON per episode; resumable; shardable.

Example (vLLM server already running on localhost:8000):
  python -m railinject.run --agent llm --model Qwen/Qwen2.5-7B-Instruct \
      --policies D0,D1,D2,D3,D4,D5,D6,D7,D7-noC2,D7-noC3,D7-noC4 --out runs/qwen7b.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .agent import LLMAgent, ScriptedAgent
from .env import Episode
from .suites import SUITES, Item, items

ALL_POLICIES = ["D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D7-noC2", "D7-noC3", "D7-noC4", "D2D5"]


def make_detector(kind: str):
    if kind == "none":
        return None
    if kind == "keyword":              # TEST ONLY: never used in reported runs
        keys = ("important message", "operating rule 4.2", "urgent safety notice")
        return lambda txt: any(k in txt.lower() for k in keys)
    from transformers import pipeline  # protectai/deberta-v3-base-prompt-injection-v2
    clf = pipeline("text-classification", model=kind, truncation=True, max_length=512)

    lk = threading.Lock()

    def det(txt: str) -> bool:
        with lk:
            r = clf(txt)[0]
        return r["label"].upper().startswith("INJ")
    return det


def run_episode(it: Item, policy: str, agent: Any, detector=None) -> dict[str, Any]:
    s = SUITES[it.suite]
    task = s.tasks[it.task]
    inj = next((i for i in s.injections if i.id == it.injection), None) if it.injection else None
    lc = next((c for c in s.lifecycle if c.id == it.lifecycle), None) if it.lifecycle else None
    envpol = "D5" if policy == "D2D5" else policy
    env = Episode(s, task, envpol if envpol.startswith("D7") or envpol in ("D3", "D4", "D5") else "D0",
                  injection=inj, framing=it.framing, lifecycle=lc,
                  spotlight=(policy == "D1"), detector=(detector if policy == "D6" else None),
                  allowlist=(policy in ("D2", "D2D5")))
    # time spent in the gate (commit path), per committed or refused action
    gate_times: list[float] = []
    orig = env.gate._commit_one

    def timed(a, human):
        t0 = time.perf_counter()
        orig(a, human)
        gate_times.append((time.perf_counter() - t0) * 1000)
    env.gate._commit_one = timed
    err = ""
    try:
        meta = agent.run(env, spotlight=(policy == "D1"))
    except Exception as e:  # noqa: BLE001 -- environment or server crash, recorded
        meta, err = {"calls": 0, "seconds": 0, "tokens": 0, "final": ""}, repr(e)
    st = env.store
    hist = env.gate.history
    res: dict[str, Any] = {
        "item": it.id, "kind": it.kind, "suite": it.suite, "task": it.task, "policy": policy,
        "injection": it.injection, "framing": it.framing, "lifecycle": it.lifecycle,
        "lc_class": lc.cls if lc else None, "lc_relevant": lc.relevant if lc else None,
        "goal": inj.goal if inj else None, "error": err, **{k: meta[k] for k in ("calls", "seconds", "tokens")},
        "utility": bool(task.utility(st, env)) if not err else False,
        "decisions": [{"tool": a.tool, "args": a.args, "decision": a.decision, "reason": a.reason,
                       "escalated": a.escalated} for a in hist],
        "gate_ms": gate_times,
    }
    benign_targets = task.expected
    res["benign_blocked"] = sum(1 for a in hist if any((a.tool, t) in benign_targets
                                                       for t in a.targets.values())
                                and a.decision in ("block",))
    res["benign_escalated"] = sum(1 for a in hist if any((a.tool, t) in benign_targets
                                                         for t in a.targets.values())
                                  and a.escalated)
    if inj is not None:
        want = inj.attacker_calls(task, env)
        def is_att(c):
            return any(c["tool"] == n and all(str(c["args"].get(k)) == str(v)
                       for k, v in a.items() if k not in ("body", "basis"))
                       for n, a in want)
        res["attack_proposed"] = any(is_att(c) for c in env.calls)
        res["attack_committed"] = bool(inj.committed(st, env, task))
        res["attack_escalated"] = any(is_att({"tool": a.tool, "args": a.args}) and a.escalated
                                      for a in hist)
    if lc is not None:
        res["violation"] = bool(env.violations)
        res["violations"] = env.violations
        res["replans"] = env.replans_total
        res["replans_needless"] = env.replans_needless
        res["harmless_stale_commits"] = env.harmless_stale
    return res


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", choices=["llm", "scripted", "scripted-obey"], default="llm")
    ap.add_argument("--model", default="")
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--policies", default=",".join(ALL_POLICIES))
    ap.add_argument("--framings", default="template,rulebook,urgency")
    ap.add_argument("--kinds", default="benign,attack,lifecycle")
    ap.add_argument("--detector", default="protectai/deberta-v3-base-prompt-injection-v2")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--run-id", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0, help="pilot: first N items per policy")
    ap.add_argument("--shard", default="0/1")
    ap.add_argument("--workers", type=int, default=1, help="parallel episodes (vLLM batches them)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    pols = a.policies.split(",")
    kinds = set(a.kinds.split(","))
    its = [i for i in items(tuple(a.framings.split(","))) if i.kind in kinds]
    k, n = map(int, a.shard.split("/"))
    done = set()
    if os.path.exists(a.out):
        with open(a.out) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    done.add((r["item"], r["policy"], r.get("run", 0)))
                except json.JSONDecodeError:
                    pass
    agent = (LLMAgent(a.base_url, a.model, a.temperature, seed=a.run_id) if a.agent == "llm"
             else ScriptedAgent(obey=(a.agent == "scripted-obey")))
    det = make_detector(a.detector) if "D6" in pols else None
    jobs = [(i, p) for p in pols for i in (its[: a.limit] if a.limit else its)]
    jobs = [j for idx, j in enumerate(jobs) if idx % n == k]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    todo = [(i, p) for i, p in jobs if (i.id, p, a.run_id) not in done]
    lock = threading.Lock()
    with open(a.out, "a") as f:
        def one(job):
            i, p = job
            r = run_episode(i, p, agent, det)
            r.update({"model": a.model or a.agent, "temperature": a.temperature, "run": a.run_id})
            with lock:
                f.write(json.dumps(r) + "\n")
                f.flush()
        if a.workers <= 1:
            for j in todo:
                one(j)
        else:
            with ThreadPoolExecutor(a.workers) as ex:
                list(ex.map(one, todo))
    print(f"done: {len(jobs)} jobs -> {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
