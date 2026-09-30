"""Transactional trial checkpoints bound to immutable campaign configuration."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.eval.call_gate import ResumeBlockedError, canonical


class Checkpoint:
    def __init__(self, path: Path, identity: dict):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS identity (id INTEGER PRIMARY KEY, value TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS results (id TEXT PRIMARY KEY, result TEXT)")
        self.db.execute("INSERT OR IGNORE INTO identity VALUES (1, ?)", (canonical(identity),))
        self.db.commit()
        if self.db.execute("SELECT value FROM identity").fetchone()[0] != canonical(identity):
            self.db.close()
            raise ResumeBlockedError("Checkpoint configuration or source changed")

    def get(self, record_id: str):
        row = self.db.execute("SELECT result FROM results WHERE id=?", (record_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def save(self, record: dict):
        with self.db:
            self.db.execute("INSERT INTO results VALUES (?, ?)",
                            (record["record_id"], canonical(record)))

    def close(self):
        self.db.close()
