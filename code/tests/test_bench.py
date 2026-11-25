"""Tests of the benchmark and the gate with scripted agents (no LLM).
They check the design, not any model: run with  python -m pytest -q tests"""
import collections

from railinject.run import run_episode
from railinject.agent import ScriptedAgent
from railinject.suites import items, test_set_hash

IT = items()
DET = lambda txt: False  # noqa: E731


def _run(kind, pol, obey=False):
    return [run_episode(i, pol, ScriptedAgent(obey), DET) for i in IT if i.kind == kind]


def test_sizes():
    c = collections.Counter(i.kind for i in IT)
    assert c == {"benign": 44, "attack": 528, "lifecycle": 60}
    assert len(test_set_hash()) == 64


def test_benign_utility_full_under_every_defence():
    for p in ["D0", "D3", "D4", "D5", "D7", "D7-noC2", "D7-noC3", "D7-noC4"]:
        rs = _run("benign", p)
        assert all(r["utility"] and not r["error"] for r in rs), p


def test_gate_stops_rule_breaking_attacks_but_not_within_rule_ones():
    rs = _run("attack", "D7", obey=True)
    for r in rs:
        if r["goal"] in ("G1", "G2", "G4", "G5a"):
            assert not r["attack_committed"], r["item"]
    g5b = [r for r in rs if r["goal"] == "G5b"]
    assert sum(r["attack_committed"] for r in g5b) > 0     # residual risk is real


def test_no_defence_lets_attacks_through():
    rs = _run("attack", "D0", obey=True)
    assert sum(r["attack_committed"] for r in rs) / len(rs) > 0.8


def test_lifecycle_classes():
    def viol(p, cls):
        rs = [r for r in _run("lifecycle", p) if r["lc_class"] == cls
              and (cls != "stale" or r["lc_relevant"])]
        return sum(r["violation"] for r in rs)
    assert all(viol("D7", c) == 0 for c in ("authority", "unsafe", "stale", "concurrent"))
    assert viol("D5", "unsafe") == 0 and viol("D5", "stale") > 0 and viol("D5", "concurrent") > 0
    assert viol("D4", "authority") > 0
    assert viol("D7-noC2", "stale") > 0


def test_replay_needs_the_nonce():
    rs = [r for r in _run("lifecycle", "D5") if r["item"].endswith(("rep-0",))]
    assert any(r["violation"] for r in rs)
    rs = [r for r in _run("lifecycle", "D7") if r["item"].endswith(("rep-0",))]
    assert not any(r["violation"] for r in rs)
