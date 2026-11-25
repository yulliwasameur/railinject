"""Versioned railway state store and delegation authority, in ONE SQLite database.

Design choices (they match the paper):
* every object has a version that increases at each change (C2 freshness);
* grants, epochs, revoked grants and used request identifiers (nonces) live in
  the same database, so authority and state are checked in the same
  serialisable transaction (BEGIN IMMEDIATE);
* every decision of the gate is logged.
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS objects (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL, version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS grants (
  id TEXT PRIMARY KEY, principal TEXT, parent TEXT, epoch INTEGER, scope TEXT,
  not_after REAL, signature TEXT);
CREATE TABLE IF NOT EXISTS epochs (principal TEXT PRIMARY KEY, epoch INTEGER);
CREATE TABLE IF NOT EXISTS revoked (grant_id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS nonces (nonce TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS log (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, kind TEXT, payload TEXT);
"""


class Store:
    """Thin wrapper over SQLite. One store per episode (in memory)."""

    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path, isolation_level=None)  # autocommit; we manage txns
        self.db.executescript(SCHEMA)

    # ------------------------------------------------------------ objects
    def put(self, oid: str, kind: str, data: dict[str, Any]) -> int:
        row = self.db.execute("SELECT version FROM objects WHERE id=?", (oid,)).fetchone()
        v = 1 if row is None else row[0] + 1
        self.db.execute(
            "INSERT OR REPLACE INTO objects(id, kind, data, version) VALUES (?,?,?,?)",
            (oid, kind, json.dumps(data, sort_keys=True), v),
        )
        return v

    def update(self, oid: str, **changes: Any) -> int:
        obj = self.get(oid)
        if obj is None:
            raise KeyError(oid)
        data = dict(obj["data"])
        data.update(changes)
        return self.put(oid, obj["kind"], data)

    def get(self, oid: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT kind, data, version FROM objects WHERE id=?", (oid,)).fetchone()
        if row is None:
            return None
        return {"id": oid, "kind": row[0], "data": json.loads(row[1]), "version": row[2]}

    def version(self, oid: str) -> int | None:
        row = self.db.execute("SELECT version FROM objects WHERE id=?", (oid,)).fetchone()
        return None if row is None else row[0]

    def all(self, kind: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT id, data, version FROM objects WHERE kind=? ORDER BY id", (kind,)
        ).fetchall()
        return [{"id": r[0], "kind": kind, "data": json.loads(r[1]), "version": r[2]} for r in rows]

    def snapshot(self) -> dict[str, dict[str, Any]]:
        rows = self.db.execute("SELECT id, kind, data, version FROM objects").fetchall()
        return {r[0]: {"kind": r[1], "data": json.loads(r[2]), "version": r[3]} for r in rows}

    # ---------------------------------------------------------- authority
    def add_grant(self, g: dict[str, Any]) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO grants VALUES (?,?,?,?,?,?,?)",
            (g["id"], g["principal"], g.get("parent"), g["epoch"], json.dumps(g["scope"]),
             g.get("not_after", 1e18), g.get("signature", "")),
        )
        if self.epoch(g["principal"]) is None:
            self.db.execute("INSERT INTO epochs VALUES (?,?)", (g["principal"], g["epoch"]))

    def grant(self, gid: str) -> dict[str, Any] | None:
        r = self.db.execute("SELECT * FROM grants WHERE id=?", (gid,)).fetchone()
        if r is None:
            return None
        return {"id": r[0], "principal": r[1], "parent": r[2], "epoch": r[3],
                "scope": json.loads(r[4]), "not_after": r[5], "signature": r[6]}

    def epoch(self, principal: str) -> int | None:
        r = self.db.execute("SELECT epoch FROM epochs WHERE principal=?", (principal,)).fetchone()
        return None if r is None else r[0]

    def bump_epoch(self, principal: str) -> None:
        self.db.execute("UPDATE epochs SET epoch = epoch + 1 WHERE principal=?", (principal,))

    def revoke(self, gid: str) -> None:
        self.db.execute("INSERT OR IGNORE INTO revoked VALUES (?)", (gid,))

    def is_revoked(self, gid: str) -> bool:
        return self.db.execute("SELECT 1 FROM revoked WHERE grant_id=?", (gid,)).fetchone() is not None

    def nonce_used(self, nonce: str) -> bool:
        return self.db.execute("SELECT 1 FROM nonces WHERE nonce=?", (nonce,)).fetchone() is not None

    def use_nonce(self, nonce: str) -> None:
        self.db.execute("INSERT INTO nonces VALUES (?)", (nonce,))

    # -------------------------------------------------------------- misc
    def log(self, kind: str, payload: dict[str, Any]) -> None:
        self.db.execute("INSERT INTO log(ts, kind, payload) VALUES (?,?,?)",
                        (time.time(), kind, json.dumps(payload, sort_keys=True, default=str)))

    def logs(self, kind: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT kind, payload FROM log" + (" WHERE kind=?" if kind else "") + " ORDER BY seq"
        rows = self.db.execute(q, (kind,) if kind else ()).fetchall()
        return [{"kind": r[0], **json.loads(r[1])} for r in rows]

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Serialisable transaction: BEGIN IMMEDIATE takes the write lock at once,
        so no other writer can change state or authority until COMMIT."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
