import json
from contextlib import contextmanager
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
    candidate_id TEXT PRIMARY KEY,
    state TEXT NOT NULL DEFAULT '{}',
    extracted TEXT NOT NULL DEFAULT '{}',
    summary TEXT,
    outcome TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    type TEXT NOT NULL,
    detail TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    at TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class Message:
    role: str
    text: str
    at: datetime


@dataclass(frozen=True)
class Record:
    candidate_id: str
    state: dict
    extracted: dict
    summary: str | None
    outcome: str | None
    updated_at: datetime


@dataclass(frozen=True)
class Event:
    type: str
    detail: str
    at: datetime


class Store:
    def __init__(self, path: Path | str):
        self._path = str(path)
        with self._connect() as db:
            db.executescript(_SCHEMA)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self._path)
        try:
            with db:
                yield db
        finally:
            db.close()

    def commit_turn(self, candidate_id: str, now: datetime, state: dict, extracted: dict,
                    outcome: str, events: list[tuple[str, str]],
                    messages: list[tuple[str, str]]) -> None:
        with self._connect() as db:
            db.execute("INSERT OR IGNORE INTO candidates (candidate_id, updated_at) VALUES (?, ?)",
                       (candidate_id, now.isoformat()))
            db.execute(
                "UPDATE candidates SET state = ?, extracted = ?, outcome = ?, updated_at = ? "
                "WHERE candidate_id = ?",
                (json.dumps(state, ensure_ascii=False), json.dumps(extracted, ensure_ascii=False),
                 outcome, now.isoformat(), candidate_id))
            db.executemany("INSERT INTO events (candidate_id, type, detail, at) VALUES (?, ?, ?, ?)",
                           [(candidate_id, t, d, now.isoformat()) for t, d in events])
            db.executemany("INSERT INTO messages (candidate_id, role, text, at) VALUES (?, ?, ?, ?)",
                           [(candidate_id, r, x, now.isoformat()) for r, x in messages])

    def get(self, candidate_id: str) -> Record | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT candidate_id, state, extracted, summary, outcome, updated_at "
                "FROM candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
        return _record(row) if row else None

    def list_candidates(self, outcome: str | None = None) -> list[Record]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT candidate_id, state, extracted, summary, outcome, updated_at "
                "FROM candidates WHERE ? IS NULL OR outcome = ? ORDER BY updated_at DESC",
                (outcome, outcome)).fetchall()
        return [_record(r) for r in rows]

    def save_summary(self, candidate_id: str, summary: str) -> None:
        with self._connect() as db:
            db.execute("UPDATE candidates SET summary = ? WHERE candidate_id = ?", (summary, candidate_id))

    def events(self, candidate_id: str) -> list[Event]:
        with self._connect() as db:
            rows = db.execute("SELECT type, detail, at FROM events WHERE candidate_id = ? ORDER BY id",
                              (candidate_id,)).fetchall()
        return [Event(t, d, datetime.fromisoformat(a)) for t, d, a in rows]

    def messages(self, candidate_id: str) -> list[Message]:
        with self._connect() as db:
            rows = db.execute("SELECT role, text, at FROM messages WHERE candidate_id = ? ORDER BY id",
                              (candidate_id,)).fetchall()
        return [Message(r, t, datetime.fromisoformat(a)) for r, t, a in rows]


def _record(row) -> Record:
    candidate_id, state, extracted, summary, outcome, updated_at = row
    return Record(candidate_id, json.loads(state), json.loads(extracted), summary, outcome,
                  datetime.fromisoformat(updated_at))
