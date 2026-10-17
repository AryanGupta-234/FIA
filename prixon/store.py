from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


def default_store_path() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    return root / "Prixon" / "prixon.sqlite3"


class AgentStore:
    """Small, local SQLite store for world state, goals, episodes and audit records."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else default_store_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    normalized TEXT NOT NULL,
                    target TEXT,
                    source TEXT NOT NULL DEFAULT 'perception',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    last_seen REAL NOT NULL,
                    UNIQUE(kind, normalized, target)
                );
                CREATE INDEX IF NOT EXISTS ix_entities_kind_name ON entities(kind, normalized);
                CREATE TABLE IF NOT EXISTS aliases (
                    phrase TEXT PRIMARY KEY,
                    target_type TEXT NOT NULL,
                    target TEXT NOT NULL,
                    scope_json TEXT NOT NULL DEFAULT '{}',
                    confidence REAL NOT NULL DEFAULT 1.0,
                    explicit INTEGER NOT NULL DEFAULT 0,
                    last_used REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS alias_candidates (
                    phrase TEXT NOT NULL,
                    target TEXT NOT NULL,
                    successes REAL NOT NULL DEFAULT 0,
                    failures REAL NOT NULL DEFAULT 0,
                    sessions_json TEXT NOT NULL DEFAULT '[]',
                    last_updated REAL NOT NULL,
                    PRIMARY KEY(phrase, target)
                );
                CREATE TABLE IF NOT EXISTS episodes (
                    id TEXT PRIMARY KEY,
                    utterance TEXT NOT NULL,
                    layer_path_json TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    feedback TEXT,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS goals (
                    id TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 50,
                    status TEXT NOT NULL DEFAULT 'pending',
                    source TEXT NOT NULL DEFAULT 'user',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_goals_status_priority ON goals(status, priority, created_at);
                CREATE TABLE IF NOT EXISTS undo_journal (
                    id TEXT PRIMARY KEY,
                    action_name TEXT NOT NULL,
                    args_json TEXT NOT NULL,
                    before_state_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at REAL NOT NULL,
                    completed_at REAL
                );
                CREATE TABLE IF NOT EXISTS event_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    processed_at REAL
                );
                CREATE TABLE IF NOT EXISTS macros (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    shape_hash TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    trigger_phrases_json TEXT NOT NULL DEFAULT '[]',
                    successes INTEGER NOT NULL DEFAULT 0,
                    approved INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL
                );
            """)

    def audit(self, event_type: str, payload: dict[str, Any]) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO audit_log(event_type,payload_json,created_at) VALUES(?,?,?)",
                (event_type, json.dumps(payload, ensure_ascii=False, default=str), time.time()),
            )

    def episode(
        self, utterance: str, layer_path: list[str], plan: dict[str, Any],
        outcome: str, feedback: str | None = None,
    ) -> str:
        episode_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute(
                """INSERT INTO episodes(id,utterance,layer_path_json,plan_json,outcome,feedback,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (episode_id, utterance, json.dumps(layer_path), json.dumps(plan),
                 outcome, feedback, time.time()),
            )
        return episode_id

    def enqueue_event(self, event_type: str, payload: dict[str, Any]) -> int:
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO event_queue(event_type,payload_json,created_at) VALUES(?,?,?)",
                (event_type, json.dumps(payload, default=str), time.time()),
            )
            return int(cursor.lastrowid)

    def pending_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM event_queue WHERE processed_at IS NULL ORDER BY id LIMIT ?",
                (limit,),
            ).fetchall()
            return [
                {"id": row["id"], "event_type": row["event_type"],
                 "payload": json.loads(row["payload_json"]), "created_at": row["created_at"]}
                for row in rows
            ]

    def mark_event_processed(self, event_id: int) -> None:
        with self.connect() as db:
            db.execute("UPDATE event_queue SET processed_at=? WHERE id=?", (time.time(), event_id))

    def add_goal(
        self, description: str, priority: int = 50, source: str = "user",
        payload: dict[str, Any] | None = None,
    ) -> str:
        goal_id, now = str(uuid.uuid4()), time.time()
        with self.connect() as db:
            db.execute(
                """INSERT INTO goals(id,description,priority,status,source,payload_json,created_at,updated_at)
                   VALUES(?,?,?,'pending',?,?,?,?)""",
                (goal_id, description, priority, source,
                 json.dumps(payload or {}, default=str), now, now),
            )
        return goal_id

    def goals(self, statuses: tuple[str, ...] = ("pending", "active")) -> list[dict[str, Any]]:
        if not statuses:
            return []
        marks = ",".join("?" for _ in statuses)
        with self.connect() as db:
            rows = db.execute(
                f"SELECT * FROM goals WHERE status IN ({marks}) ORDER BY priority, created_at",
                statuses,
            ).fetchall()
            return [
                {"id": row["id"], "description": row["description"], "priority": row["priority"],
                 "status": row["status"], "source": row["source"],
                 "payload": json.loads(row["payload_json"])}
                for row in rows
            ]

    def set_goal_status(self, goal_id: str, status: str) -> bool:
        if status not in {"pending", "active", "completed", "cancelled", "blocked"}:
            raise ValueError("Unsupported goal status")
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE goals SET status=?,updated_at=? WHERE id=?",
                (status, time.time(), goal_id),
            )
            return cursor.rowcount == 1

    def record_undo(self, action_name: str, args: dict[str, Any], before_state: dict[str, Any]) -> str:
        undo_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute(
                """INSERT INTO undo_journal(id,action_name,args_json,before_state_json,status,created_at)
                   VALUES(?,?,?,?, 'pending', ?)""",
                (undo_id, action_name, json.dumps(args, default=str),
                 json.dumps(before_state, default=str), time.time()),
            )
        return undo_id

    def finish_undo(self, undo_id: str, status: str) -> None:
        if status not in {"undone", "failed", "retained"}:
            raise ValueError("Unsupported undo status")
        with self.connect() as db:
            db.execute(
                "UPDATE undo_journal SET status=?,completed_at=? WHERE id=?",
                (status, time.time(), undo_id),
            )

    def add_entity(
        self, kind: str, name: str, target: str | None, source: str = "perception",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        normalized = " ".join(name.casefold().split())
        now = time.time()
        with self.connect() as db:
            db.execute(
                """INSERT INTO entities(kind,name,normalized,target,source,metadata_json,last_seen)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(kind,normalized,target) DO UPDATE SET
                     name=excluded.name,source=excluded.source,
                     metadata_json=excluded.metadata_json,last_seen=excluded.last_seen""",
                (kind, name, normalized, target, source,
                 json.dumps(metadata or {}, default=str), now),
            )
            row = db.execute(
                "SELECT id FROM entities WHERE kind=? AND normalized=? AND target IS ?",
                (kind, normalized, target),
            ).fetchone()
            return int(row["id"])

    def entity_rows(self, kind: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as db:
            if kind:
                rows = db.execute("SELECT * FROM entities WHERE kind=? ORDER BY last_seen DESC", (kind,))
            else:
                rows = db.execute("SELECT * FROM entities ORDER BY last_seen DESC")
            return [
                {"id": row["id"], "kind": row["kind"], "name": row["name"],
                 "normalized": row["normalized"], "target": row["target"],
                 "source": row["source"], "metadata": json.loads(row["metadata_json"]),
                 "last_seen": row["last_seen"]}
                for row in rows.fetchall()
            ]

    def put_alias(
        self, phrase: str, target_type: str, target: str,
        scope: dict[str, Any] | None = None, confidence: float = 1.0,
        explicit: bool = False,
    ) -> None:
        normalized = " ".join(phrase.casefold().split())
        with self.connect() as db:
            db.execute(
                """INSERT INTO aliases(phrase,target_type,target,scope_json,confidence,explicit,last_used)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(phrase) DO UPDATE SET target_type=excluded.target_type,
                   target=excluded.target,scope_json=excluded.scope_json,
                   confidence=excluded.confidence,explicit=excluded.explicit,last_used=excluded.last_used""",
                (normalized, target_type, target, json.dumps(scope or {}),
                 confidence, int(explicit), time.time()),
            )

    def alias(self, phrase: str) -> dict[str, Any] | None:
        normalized = " ".join(phrase.casefold().split())
        with self.connect() as db:
            row = db.execute("SELECT * FROM aliases WHERE phrase=?", (normalized,)).fetchone()
            if row is None:
                return None
            db.execute("UPDATE aliases SET last_used=? WHERE phrase=?", (time.time(), normalized))
            return {"phrase": row["phrase"], "target_type": row["target_type"],
                    "target": row["target"], "scope": json.loads(row["scope_json"]),
                    "confidence": row["confidence"], "explicit": bool(row["explicit"])}

    def observe_alias(
        self, phrase: str, target: str, success: bool, session_id: str,
    ) -> dict[str, Any]:
        normalized = " ".join(phrase.casefold().split())
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM alias_candidates WHERE phrase=? AND target=?",
                (normalized, target),
            ).fetchone()
            if row is None:
                successes, failures, sessions = 0.0, 0.0, []
            else:
                elapsed_days = max(0.0, (time.time() - row["last_updated"]) / 86400)
                decay = 0.5 ** (elapsed_days / 60.0)
                successes = float(row["successes"]) * decay
                failures = float(row["failures"]) * decay
                sessions = json.loads(row["sessions_json"])
            if success:
                successes += 1
            else:
                failures += 1
            if success and session_id not in sessions:
                sessions.append(session_id)
            db.execute(
                """INSERT INTO alias_candidates(phrase,target,successes,failures,sessions_json,last_updated)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(phrase,target) DO UPDATE SET successes=excluded.successes,
                   failures=excluded.failures,sessions_json=excluded.sessions_json,
                   last_updated=excluded.last_updated""",
                (normalized, target, successes, failures, json.dumps(sessions), time.time()),
            )
            posterior = (successes + 1) / (successes + failures + 2)
            return {"phrase": normalized, "target": target, "successes": successes,
                    "failures": failures, "sessions": sessions, "confidence": posterior}

    def audit_rows(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [{"id": row["id"], "event_type": row["event_type"],
                     "payload": json.loads(row["payload_json"]), "created_at": row["created_at"]}
                    for row in rows]
