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
                CREATE TABLE IF NOT EXISTS negative_examples (
                    phrase TEXT NOT NULL,
                    action_name TEXT NOT NULL,
                    penalty REAL NOT NULL DEFAULT 0.2,
                    corrections INTEGER NOT NULL DEFAULT 1,
                    last_updated REAL NOT NULL,
                    PRIMARY KEY(phrase, action_name)
                );
                CREATE TABLE IF NOT EXISTS semantic_examples (
                    action_name TEXT NOT NULL,
                    phrase TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY(action_name, phrase)
                );
                CREATE TABLE IF NOT EXISTS pending_learning (
                    id TEXT PRIMARY KEY,
                    phrase TEXT NOT NULL,
                    action_name TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    risk TEXT NOT NULL,
                    undo_id TEXT,
                    created_at REAL NOT NULL
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
                    output_json TEXT NOT NULL DEFAULT '{}',
                    utterance TEXT NOT NULL DEFAULT '',
                    session_id TEXT NOT NULL DEFAULT 'local-session',
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
                CREATE TABLE IF NOT EXISTS routines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    macro_id INTEGER NOT NULL,
                    time_local TEXT NOT NULL,
                    weekdays_json TEXT NOT NULL DEFAULT '[0,1,2,3,4,5,6]',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_fired_date TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
            """)
            undo_columns = {
                row["name"] for row in db.execute("PRAGMA table_info(undo_journal)").fetchall()
            }
            if "output_json" not in undo_columns:
                db.execute("ALTER TABLE undo_journal ADD COLUMN output_json TEXT NOT NULL DEFAULT '{}'")
            if "utterance" not in undo_columns:
                db.execute("ALTER TABLE undo_journal ADD COLUMN utterance TEXT NOT NULL DEFAULT ''")
            if "session_id" not in undo_columns:
                db.execute("ALTER TABLE undo_journal ADD COLUMN session_id TEXT NOT NULL DEFAULT 'local-session'")

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


    def create_routine(
        self, name: str, macro_id: int, time_local: str,
        weekdays: list[int] | None = None,
    ) -> int:
        selected_days = sorted(set(weekdays if weekdays is not None else range(7)))
        if not selected_days or any(day not in range(7) for day in selected_days):
            raise ValueError("Routine weekdays must contain values from 0 through 6.")
        if len(time_local) != 5 or time_local[2] != ":":
            raise ValueError("Routine time must use 24-hour HH:MM format.")
        try:
            hour, minute = (int(part) for part in time_local.split(":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Routine time must use 24-hour HH:MM format.") from exc
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("Routine time must use 24-hour HH:MM format.")
        now = time.time()
        with self.connect() as db:
            cursor = db.execute(
                """INSERT INTO routines(
                       name,macro_id,time_local,weekdays_json,enabled,created_at,updated_at
                   ) VALUES(?,?,?,?,1,?,?)""",
                (name, macro_id, time_local, json.dumps(selected_days), now, now),
            )
            return int(cursor.lastrowid)

    def routines(self, enabled: bool | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM routines"
        params: tuple[Any, ...] = ()
        if enabled is not None:
            query += " WHERE enabled=?"
            params = (int(enabled),)
        query += " ORDER BY time_local,id"
        with self.connect() as db:
            rows = db.execute(query, params).fetchall()
            return [
                {"id": row["id"], "name": row["name"], "macro_id": row["macro_id"],
                 "time_local": row["time_local"],
                 "weekdays": json.loads(row["weekdays_json"]),
                 "enabled": bool(row["enabled"]), "last_fired_date": row["last_fired_date"]}
                for row in rows
            ]

    def due_routines(self, now_local) -> list[dict[str, Any]]:
        date_key = now_local.date().isoformat()
        weekday = now_local.weekday()
        clock = now_local.strftime("%H:%M")
        due = []
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM routines WHERE enabled=1 AND time_local<=? "
                "AND (last_fired_date IS NULL OR last_fired_date<>?) ORDER BY time_local,id",
                (clock, date_key),
            ).fetchall()
            for row in rows:
                weekdays = json.loads(row["weekdays_json"])
                if weekday not in weekdays:
                    continue
                cursor = db.execute(
                    "UPDATE routines SET last_fired_date=?,updated_at=? "
                    "WHERE id=? AND (last_fired_date IS NULL OR last_fired_date<>?)",
                    (date_key, time.time(), row["id"], date_key),
                )
                if cursor.rowcount == 1:
                    due.append({
                        "id": row["id"], "name": row["name"], "macro_id": row["macro_id"],
                        "time_local": row["time_local"],
                    })
        return due

    def set_routine_enabled(self, routine_id: int, enabled: bool) -> bool:
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE routines SET enabled=?,updated_at=? WHERE id=?",
                (int(enabled), time.time(), routine_id),
            )
            return cursor.rowcount == 1

    def delete_routine(self, routine_id: int) -> bool:
        with self.connect() as db:
            cursor = db.execute("DELETE FROM routines WHERE id=?", (routine_id,))
            return cursor.rowcount == 1

    def record_undo(
        self, action_name: str, args: dict[str, Any], before_state: dict[str, Any],
        *, utterance: str = "", session_id: str = "local-session",
    ) -> str:
        undo_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute(
                """INSERT INTO undo_journal(
                       id,action_name,args_json,before_state_json,utterance,session_id,status,created_at
                   ) VALUES(?,?,?,?,?,?,'pending',?)""",
                (undo_id, action_name, json.dumps(args, default=str),
                 json.dumps(before_state, default=str), utterance, session_id, time.time()),
            )
        return undo_id

    def update_undo_output(self, undo_id: str, output: dict[str, Any]) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE undo_journal SET output_json=? WHERE id=?",
                (json.dumps(output, default=str), undo_id),
            )

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

    def remove_entity_target(self, target: str) -> int:
        with self.connect() as db:
            cursor = db.execute("DELETE FROM entities WHERE target=?", (target,))
            return int(cursor.rowcount)

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

    def remove_alias(self, phrase: str) -> None:
        normalized = " ".join(phrase.casefold().split())
        with self.connect() as db:
            db.execute("DELETE FROM aliases WHERE phrase=?", (normalized,))

    def remove_alias_if_implicit(self, phrase: str) -> bool:
        normalized = " ".join(phrase.casefold().split())
        with self.connect() as db:
            cursor = db.execute(
                "DELETE FROM aliases WHERE phrase=? AND explicit=0", (normalized,),
            )
            return cursor.rowcount > 0

    def remove_alias_candidate(self, phrase: str, target: str | None = None) -> int:
        normalized = " ".join(phrase.casefold().split())
        with self.connect() as db:
            if target is None:
                cursor = db.execute("DELETE FROM alias_candidates WHERE phrase=?", (normalized,))
            else:
                cursor = db.execute(
                    "DELETE FROM alias_candidates WHERE phrase=? AND target=?",
                    (normalized, target),
                )
            return int(cursor.rowcount)

    def remove_all_user_learning(self) -> dict[str, int]:
        with self.connect() as db:
            aliases = db.execute("DELETE FROM aliases").rowcount
            candidates = db.execute("DELETE FROM alias_candidates").rowcount
            negatives = db.execute("DELETE FROM negative_examples").rowcount
            examples = db.execute("DELETE FROM semantic_examples").rowcount
            pending = db.execute("DELETE FROM pending_learning").rowcount
            episodes = db.execute("DELETE FROM episodes").rowcount
            macros = db.execute("DELETE FROM macros").rowcount
        return {
            "aliases": int(aliases), "candidates": int(candidates),
            "negative_examples": int(negatives), "semantic_examples": int(examples),
            "pending_learning": int(pending), "episodes": int(episodes),
            "macros": int(macros),
        }

    def queue_learning_signal(
        self, phrase: str, action_name: str, session_id: str,
        risk: str, undo_id: str | None = None,
    ) -> str:
        signal_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute(
                """INSERT INTO pending_learning(id,phrase,action_name,session_id,risk,undo_id,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (signal_id, phrase, action_name, session_id, risk, undo_id, time.time()),
            )
        return signal_id

    def pending_learning_signals(self, older_than: float | None = None) -> list[dict[str, Any]]:
        with self.connect() as db:
            if older_than is None:
                rows = db.execute("SELECT * FROM pending_learning ORDER BY created_at").fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM pending_learning WHERE created_at<=? ORDER BY created_at",
                    (older_than,),
                ).fetchall()
            return [
                {"id": row["id"], "phrase": row["phrase"], "action_name": row["action_name"],
                 "session_id": row["session_id"], "risk": row["risk"],
                 "undo_id": row["undo_id"], "created_at": row["created_at"]}
                for row in rows
            ]

    def discard_pending_learning(
        self, *, signal_id: str | None = None, session_id: str | None = None,
        undo_id: str | None = None, phrase: str | None = None,
    ) -> int:
        clauses, values = [], []
        for column, value in (
            ("id", signal_id), ("session_id", session_id),
            ("undo_id", undo_id), ("phrase", phrase),
        ):
            if value is not None:
                clauses.append(f"{column}=?")
                values.append(value)
        if not clauses:
            raise ValueError("At least one pending-learning selector is required.")
        with self.connect() as db:
            cursor = db.execute(
                "DELETE FROM pending_learning WHERE " + " AND ".join(clauses),
                tuple(values),
            )
            return int(cursor.rowcount)

    def add_semantic_example(
        self, action_name: str, phrase: str, vector: list[float],
    ) -> None:
        with self.connect() as db:
            db.execute(
                """INSERT INTO semantic_examples(action_name,phrase,vector_json,created_at)
                   VALUES(?,?,?,?)
                   ON CONFLICT(action_name,phrase) DO UPDATE SET
                   vector_json=excluded.vector_json,created_at=excluded.created_at""",
                (action_name, phrase, json.dumps(vector), time.time()),
            )

    def semantic_examples(self, action_name: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as db:
            if action_name:
                rows = db.execute(
                    "SELECT * FROM semantic_examples WHERE action_name=? ORDER BY created_at DESC",
                    (action_name,),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM semantic_examples ORDER BY created_at DESC",
                ).fetchall()
            return [
                {"action_name": row["action_name"], "phrase": row["phrase"],
                 "vector": json.loads(row["vector_json"]), "created_at": row["created_at"]}
                for row in rows
            ]

    def remove_semantic_example(self, action_name: str, phrase: str) -> None:
        with self.connect() as db:
            db.execute(
                "DELETE FROM semantic_examples WHERE action_name=? AND phrase=?",
                (action_name, phrase),
            )

    def undo_record(self, undo_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM undo_journal WHERE id=?", (undo_id,)).fetchone()
            if row is None:
                return None
            return {
                "id": row["id"], "action_name": row["action_name"],
                "args": json.loads(row["args_json"]),
                "before_state": json.loads(row["before_state_json"]),
                "output": json.loads(row["output_json"]) if "output_json" in row.keys() else {},
                "utterance": row["utterance"] if "utterance" in row.keys() else "",
                "session_id": row["session_id"] if "session_id" in row.keys() else "local-session",
                "status": row["status"],
            }

    def set_setting(self, key: str, value: Any) -> None:
        with self.connect() as db:
            db.execute(
                """INSERT INTO agent_settings(key,value_json,updated_at) VALUES(?,?,?)
                   ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,
                   updated_at=excluded.updated_at""",
                (key, json.dumps(value, default=str), time.time()),
            )

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.connect() as db:
            row = db.execute("SELECT value_json FROM agent_settings WHERE key=?", (key,)).fetchone()
            return json.loads(row["value_json"]) if row else default

    def record_macro(
        self, shape_hash: str, name: str, plan: dict[str, Any], trigger: str,
        *, approved: bool = False, evidence_count: int = 1,
    ) -> None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM macros WHERE shape_hash=?", (shape_hash,)).fetchone()
            phrases = json.loads(row["trigger_phrases_json"]) if row else []
            successes = int(row["successes"]) if row else 0
            if trigger and trigger not in phrases:
                phrases.append(trigger)
            successes = max(successes, max(0, evidence_count))
            db.execute(
                """INSERT INTO macros(shape_hash,name,plan_json,trigger_phrases_json,successes,approved,updated_at)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(shape_hash) DO UPDATE SET successes=excluded.successes,
                   trigger_phrases_json=excluded.trigger_phrases_json,
                   approved=MAX(macros.approved,excluded.approved),updated_at=excluded.updated_at""",
                (shape_hash, name, json.dumps(plan, default=str), json.dumps(phrases),
                 successes, int(approved), time.time()),
            )

    def macros(self, approved: bool | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM macros"
        params: tuple[Any, ...] = ()
        if approved is not None:
            query += " WHERE approved=?"
            params = (int(approved),)
        query += " ORDER BY successes DESC"
        with self.connect() as db:
            rows = db.execute(query, params).fetchall()
            return [
                {"id": row["id"], "shape_hash": row["shape_hash"], "name": row["name"],
                 "plan": json.loads(row["plan_json"]),
                 "trigger_phrases": json.loads(row["trigger_phrases_json"]),
                 "successes": row["successes"], "approved": bool(row["approved"])}
                for row in rows
            ]

    def approve_macro(self, macro_id: int, approved: bool = True) -> bool:
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE macros SET approved=?,updated_at=? WHERE id=?",
                (int(approved), time.time(), macro_id),
            )
            return cursor.rowcount == 1

    def alias_candidates(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM alias_candidates").fetchall()
            return [
                {"phrase": row["phrase"], "target": row["target"],
                 "successes": row["successes"], "failures": row["failures"],
                 "sessions": json.loads(row["sessions_json"]), "last_updated": row["last_updated"]}
                for row in rows
            ]

    def update_alias_candidate(
        self, phrase: str, target: str, successes: float, failures: float,
        sessions: list[str], updated_at: float | None = None,
    ) -> None:
        with self.connect() as db:
            db.execute(
                """UPDATE alias_candidates SET successes=?,failures=?,sessions_json=?,last_updated=?
                   WHERE phrase=? AND target=?""",
                (successes, failures, json.dumps(sessions), updated_at or time.time(), phrase, target),
            )

    def successful_episodes(self, limit: int = 1000) -> list[dict[str, Any]]: 
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM episodes WHERE outcome='success' ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [
                {"id": row["id"], "utterance": row["utterance"],
                 "plan": json.loads(row["plan_json"]),
                 "layer_path": json.loads(row["layer_path_json"]),
                 "created_at": row["created_at"]}
                for row in rows
            ]

    def approved_macros(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM macros WHERE approved=1 ORDER BY successes DESC"
            ).fetchall()
            return [
                {"shape_hash": row["shape_hash"], "name": row["name"],
                 "plan": json.loads(row["plan_json"]),
                 "trigger_phrases": json.loads(row["trigger_phrases_json"]),
                 "successes": row["successes"]}
                for row in rows
            ]

    def recent_episodes(self, limit: int = 3) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM episodes WHERE outcome='success' ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [
                {"id": row["id"], "utterance": row["utterance"],
                 "plan": json.loads(row["plan_json"]),
                 "layer_path": json.loads(row["layer_path_json"])}
                for row in rows
            ]

    def add_negative_example(
        self, phrase: str, action_name: str, penalty_delta: float = 0.15,
    ) -> None:
        normalized = " ".join(phrase.casefold().split())
        with self.connect() as db:
            row = db.execute(
                "SELECT penalty,corrections FROM negative_examples WHERE phrase=? AND action_name=?",
                (normalized, action_name),
            ).fetchone()
            penalty = min(0.75, (float(row["penalty"]) if row else 0.0) + penalty_delta)
            corrections = (int(row["corrections"]) if row else 0) + 1
            db.execute(
                """INSERT INTO negative_examples(phrase,action_name,penalty,corrections,last_updated)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(phrase,action_name) DO UPDATE SET penalty=excluded.penalty,
                   corrections=excluded.corrections,last_updated=excluded.last_updated""",
                (normalized, action_name, penalty, corrections, time.time()),
            )

    def negative_examples(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM negative_examples ORDER BY last_updated DESC").fetchall()
            return [
                {"phrase": row["phrase"], "action_name": row["action_name"],
                 "penalty": row["penalty"], "corrections": row["corrections"]}
                for row in rows
            ]

    def aliases(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM aliases ORDER BY last_used DESC").fetchall()
            return [
                {"phrase": row["phrase"], "target_type": row["target_type"],
                 "target": row["target"], "scope": json.loads(row["scope_json"]),
                 "confidence": row["confidence"], "explicit": bool(row["explicit"])}
                for row in rows
            ]

    def audit_rows(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [{"id": row["id"], "event_type": row["event_type"],
                     "payload": json.loads(row["payload_json"]), "created_at": row["created_at"]}
                    for row in rows]
