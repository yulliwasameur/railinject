"""Suite registry and benchmark items (benign tasks, attack pairs, lifecycle cases)."""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from . import s1_depot, s2_network


class Suite:
    def __init__(self, mod: ModuleType):
        self.mod = mod
        self.name = mod.SUITE
        self.tools = mod.TOOLS
        self.directory = mod.DIRECTORY
        self.free_text_fields = mod.FREE_TEXT
        self.build_state = mod.build_state
        self.invariants = mod.invariants
        self.escalable = mod.escalable
        self.linked = mod.linked
        self.user_tasks = mod.user_tasks()
        self.tasks = {t.id: t for t in self.user_tasks}
        self.injections = mod.injection_tasks()
        self.applicable = mod.applicable
        self.lifecycle = mod.lifecycle_cases(self.tasks)

    def relevant_change(self, env: Any, oid: str) -> bool:
        lc = env.lifecycle
        return not (lc is not None and lc.cls == "stale" and not lc.relevant)


SUITES = {"S1": Suite(s1_depot), "S2": Suite(s2_network)}
GOAL_GROUPS = [("G1", "G2"), ("G4",), ("G5a",), ("G5b",)]


@dataclass
class Item:
    id: str
    kind: str                 # benign | attack | lifecycle
    suite: str
    task: str
    injection: str | None = None
    framing: str | None = None
    lifecycle: str | None = None


def pairs(suite: Suite, seed: int = 2027) -> list[tuple[str, str]]:
    """Each test user task is paired with four applicable injection tasks, one per
    goal group when possible (fixed, stratified draw)."""
    rng = random.Random(seed)
    out = []
    for t in suite.user_tasks:
        if t.dev:
            continue
        chosen = []
        for grp in GOAL_GROUPS:
            cands = [i for i in suite.injections if i.goal in grp and suite.applicable(i, t)]
            if cands:
                chosen.append(rng.choice(cands).id)
        rest = [i.id for i in suite.injections if suite.applicable(i, t) and i.id not in chosen]
        while len(chosen) < 4 and rest:
            chosen.append(rest.pop(rng.randrange(len(rest))))
        out += [(t.id, c) for c in chosen[:4]]
    return out


def items(framings: tuple[str, ...] = ("template", "rulebook", "urgency"),
          include_dev: bool = False) -> list[Item]:
    out: list[Item] = []
    for sname, s in SUITES.items():
        for t in s.user_tasks:
            if t.dev and not include_dev:
                continue
            out.append(Item(f"{t.id}|benign", "benign", sname, t.id))
        for tid, iid in pairs(s):
            for f in framings:
                out.append(Item(f"{tid}|{iid}|{f}", "attack", sname, tid, iid, f))
        for lc in s.lifecycle:
            out.append(Item(f"{lc.id}", "lifecycle", sname, lc.task.id, lifecycle=lc.id))
    return out


def test_set_hash() -> str:
    """SHA-256 of the frozen test set (task prompts, pairs, lifecycle cases),
    to be pasted in the pre-registration before the gate is configured."""
    blob = []
    for sname, s in SUITES.items():
        for t in s.user_tasks:
            blob.append([sname, t.id, t.prompt, t.dev, sorted(t.links), list(t.injection_slot)])
        blob.append(pairs(s))
        blob.append([[lc.id, lc.cls, lc.task.id, lc.kind, lc.relevant, lc.wait_text]
                     for lc in s.lifecycle])
    return hashlib.sha256(json.dumps(blob, sort_keys=True).encode()).hexdigest()
