"""Write path: proposal queue + commit-time gate (RailGate) and the baselines.

An agent never writes. A write tool call creates a PendingAction in a queue
(the *proposal*). The harness commits the queue later (the *commit*), possibly
after a lifecycle event. Each defence is a Policy that decides what is checked
at proposal time and at commit time, and whether the commit is atomic.
"""
from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import (Ed25519PrivateKey,
                                                              Ed25519PublicKey)

from .store import Store

# ----------------------------------------------------------------- grants
_KEY = Ed25519PrivateKey.generate()
PUB: Ed25519PublicKey = _KEY.public_key()


def _canon(g: dict[str, Any]) -> bytes:
    body = {k: g[k] for k in ("id", "principal", "parent", "epoch", "scope", "not_after")}
    return json.dumps(body, sort_keys=True).encode()


def issue_grant(store: Store, principal: str, scope: dict[str, Any], parent: str | None = None,
                not_after: float = 1e18) -> dict[str, Any]:
    epoch = store.epoch(principal)
    g = {"id": "g-" + uuid.uuid4().hex[:8], "principal": principal, "parent": parent,
         "epoch": 0 if epoch is None else epoch, "scope": scope, "not_after": not_after}
    g["signature"] = base64.b64encode(_KEY.sign(_canon(g))).decode()
    store.add_grant(g)
    return g


def verify_grant(g: dict[str, Any]) -> bool:
    try:
        PUB.verify(base64.b64decode(g["signature"]), _canon(g))
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- actions
@dataclass
class PendingAction:
    tool: str
    args: dict[str, Any]
    grant_id: str
    rho: dict[str, int]                 # read set: object id -> version seen
    targets: dict[str, str]             # argument name -> target object id / recipient
    provenance: dict[str, str]          # argument name -> "trusted" | "untrusted"
    nonce: str = field(default_factory=lambda: uuid.uuid4().hex)
    proposed_at: float = 0.0
    decision: str = "pending"          # commit | block | replan | escalate | pending
    reason: str = ""
    checked_at_proposal: bool = False
    escalated: bool = False


@dataclass
class Policy:
    name: str
    at_proposal: tuple[str, ...] = ()   # subset of C1, C4 checked when proposed
    at_commit: tuple[str, ...] = ()     # subset of C1, C2, C3, C4, N(nonce) checked at commit
    atomic: bool = False                # check and write in one serialisable transaction


POLICIES: dict[str, Policy] = {
    "D0": Policy("D0"),
    "D1": Policy("D1"),                 # spotlighting: prompt-level only
    "D2": Policy("D2"),                 # static allowlist: enforced by the tool layer
    "D3": Policy("D3", at_commit=("C1",)),
    "D4": Policy("D4", at_proposal=("C1", "C4")),
    "D5": Policy("D5", at_commit=("C1", "C4")),
    "D6": Policy("D6"),                 # detector on tool outputs
    "D7": Policy("D7", at_commit=("N", "C1", "C2", "C3", "C4"), atomic=True),
    "D7-noC2": Policy("D7-noC2", at_commit=("N", "C1", "C3", "C4"), atomic=True),
    "D7-noC3": Policy("D7-noC3", at_commit=("N", "C1", "C2", "C4"), atomic=True),
    "D7-noC4": Policy("D7-noC4", at_commit=("N", "C1", "C2", "C3"), atomic=True),
}


class Gate:
    """Runs the checks of a policy. Suite-specific parts are injected:
    `invariants(store, action) -> list[str]` returns violated invariant names,
    `apply(store, action) -> None` performs the write,
    `escalable(inv_names) -> bool` says whether a human may decide,
    `human(action) -> bool` is the simulated human reviewer."""

    def __init__(self, store: Store, policy: Policy,
                 invariants: Callable[[Store, PendingAction], list[str]],
                 apply: Callable[[Store, PendingAction], None],
                 escalable: Callable[[list[str]], bool],
                 directory: set[str]):
        self.store, self.policy = store, policy
        self.invariants, self.apply, self.escalable = invariants, apply, escalable
        self.directory = directory
        self.queue: list[PendingAction] = []
        self.history: list[PendingAction] = []
        self.hook_between: Callable[[], None] | None = None  # concurrency hook

    # ------------------------------------------------------------- checks
    def _c1(self, a: PendingAction) -> str:
        g = self.store.grant(a.grant_id)
        if g is None or not verify_grant(g):
            return "unknown or forged grant"
        gid: str | None = g["id"]
        while gid:                                    # grant and its ancestors
            if self.store.is_revoked(gid):
                return f"grant {gid} revoked"
            gg = self.store.grant(gid)
            gid = gg["parent"] if gg else None
        if g["epoch"] != self.store.epoch(g["principal"]):
            return "principal epoch changed"
        scope = g["scope"]
        if a.tool not in scope.get("tools", []):
            return f"tool {a.tool} outside scope"
        for name, tgt in a.targets.items():
            if name == "recipient":
                continue
            if not _in_scope(self.store, tgt, scope):
                return f"target {tgt} outside scope"
        return ""

    def _c2(self, a: PendingAction) -> str:
        for oid, v in a.rho.items():
            cur = self.store.version(oid)
            if cur != v:
                return f"{oid} changed (v{v} -> v{cur})"
        return ""

    def _c3(self, a: PendingAction) -> tuple[str, str]:
        rec = a.args.get("recipient")
        if rec is not None and rec not in self.directory:
            return "block", f"recipient {rec} outside directory"
        bad = [n for n, p in a.provenance.items() if p == "untrusted" and n in a.targets]
        if bad:
            return "escalate", f"untrusted target(s): {', '.join(bad)}"
        return "", ""

    def _c4(self, a: PendingAction) -> list[str]:
        return self.invariants(self.store, a)

    def _nonce(self, a: PendingAction) -> str:
        return "request replayed" if self.store.nonce_used(a.nonce) else ""

    def _run(self, a: PendingAction, checks: tuple[str, ...],
             human: Callable[[PendingAction], bool] | None = None) -> tuple[str, str]:
        """Runs the checks in order. An escalation asks the (simulated) human; if
        the human approves, the remaining checks still run."""
        note = ""
        if "N" in checks and (r := self._nonce(a)):
            return "block", r
        if "C1" in checks and (r := self._c1(a)):
            return "block", r
        if "C2" in checks and (r := self._c2(a)):
            return "replan", r
        if "C3" in checks:
            d, r = self._c3(a)
            if d == "block":
                return d, r
            if d == "escalate":
                if human is None or not human(a):
                    return "escalate", r
                note = r + " (approved by human); "
        if "C4" in checks and (inv := self._c4(a)):
            r = "invariant " + ",".join(inv)
            if self.escalable(inv) and human is not None and human(a):
                return "commit", note + r + " (approved by human)"
            return ("escalate" if self.escalable(inv) else "block"), note + r
        return "commit", note

    # ----------------------------------------------------------- interface
    def propose(self, a: PendingAction) -> str:
        """Called by write tools. Returns a short message for the agent."""
        if self.policy.at_proposal:
            d, r = self._run(a, self.policy.at_proposal)
            a.checked_at_proposal = True
            if d != "commit":
                a.decision, a.reason = d, r
                self.history.append(a)
                self.store.log("decision", {"tool": a.tool, "decision": d, "reason": r,
                                            "stage": "proposal"})
                return f"Refused at proposal: {r}"
        self.queue.append(a)
        return f"Request {a.nonce[:8]} queued for execution."

    def resubmit(self, a: PendingAction) -> None:
        """Replay of an earlier request with the same nonce (lifecycle class)."""
        clone = PendingAction(a.tool, dict(a.args), a.grant_id, dict(a.rho), dict(a.targets),
                              dict(a.provenance), nonce=a.nonce)
        self.queue.append(clone)

    def commit_all(self, human: Callable[[PendingAction], bool]) -> list[PendingAction]:
        done = []
        while self.queue:
            a = self.queue.pop(0)
            self._commit_one(a, human)
            self.history.append(a)
            done.append(a)
        return done

    def _commit_one(self, a: PendingAction, human: Callable[[PendingAction], bool]) -> None:
        checks = self.policy.at_commit
        if self.policy.atomic:
            # the concurrency hook can only fire before the transaction: no gap exists
            if self.hook_between:
                self.hook_between()
                self.hook_between = None
            with self.store.transaction():
                d, r = self._run(a, checks, human)
                if d == "commit":
                    self.apply(self.store, a)
                    self.store.use_nonce(a.nonce)
        else:
            d, r = self._run(a, checks, human) if checks else ("commit", "")
            if self.hook_between:                      # gap between check and write
                self.hook_between()
                self.hook_between = None
            if d == "commit":
                self.apply(self.store, a)
                if not self.store.nonce_used(a.nonce):
                    self.store.use_nonce(a.nonce)
        a.decision, a.reason = d, r
        a.escalated = "human" in r or d == "escalate"
        self.store.log("decision", {"tool": a.tool, "args": a.args, "decision": d, "reason": r,
                                    "stage": "commit"})


def _in_scope(store: Store, tgt: str, scope: dict[str, Any]) -> bool:
    """Scope = a set of assets/sections. An object is in scope if it is one of
    them or refers to one of them."""
    allowed = set(scope.get("assets", []))
    if tgt in allowed:
        return True
    obj = store.get(tgt)
    if obj is None:
        return True          # creation of a new object: checked by invariants
    d = obj["data"]
    return any(d.get(k) in allowed for k in ("vehicle", "section", "asset"))
