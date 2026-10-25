import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sazon.model import RecruiterStatus

AGENT = "agent"
BUSY_TIMEOUT_SECONDS = 10

_SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
    candidate_id TEXT PRIMARY KEY,
    state TEXT NOT NULL DEFAULT '{}',
    extracted TEXT NOT NULL DEFAULT '{}',
    summary TEXT,
    outcome TEXT,
    reasons TEXT NOT NULL DEFAULT '[]',
    flags TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    type TEXT NOT NULL,
    detail TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'agent',
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recruiter (
    candidate_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'new',
    assignee TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    author TEXT NOT NULL,
    text TEXT NOT NULL,
    at TEXT NOT NULL
);
"""

# Columns added after the first release; databases created earlier are upgraded in place.
_ADDED_COLUMNS = {
    "candidates": {"reasons": "TEXT NOT NULL DEFAULT '[]'", "flags": "TEXT NOT NULL DEFAULT '[]'",
                   "outcome": "TEXT"},
    "events": {"actor": "TEXT NOT NULL DEFAULT 'agent'"},
}

_CANDIDATE_COLUMNS = ("c.candidate_id, c.state, c.extracted, c.summary, c.outcome, c.reasons, c.flags, "
                      "c.updated_at, COALESCE(r.status, 'new'), r.assignee")


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
    reasons: list
    flags: list
    status: RecruiterStatus
    assignee: str | None


@dataclass(frozen=True)
class Event:
    type: str
    detail: str
    at: datetime
    actor: str = AGENT


@dataclass(frozen=True)
class RecruiterRecord:
    status: RecruiterStatus
    assignee: str | None
    updated_at: datetime | None


@dataclass(frozen=True)
class Note:
    author: str
    text: str
    at: datetime


class Store:
    def __init__(self, path: Path | str):
        self._path = str(path)
        with self._connect() as db:
            db.executescript(_SCHEMA)
            for table, columns in _ADDED_COLUMNS.items():
                existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
                for name, definition in columns.items():
                    if name not in existing:
                        db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self._path, timeout=BUSY_TIMEOUT_SECONDS)
        try:
            with db:
                yield db
        finally:
            db.close()

    # -- written by the agent ------------------------------------------------

    def commit_turn(self, candidate_id: str, now: datetime, state: dict, extracted: dict,
                    outcome: str, events: list[tuple[str, str]],
                    messages: list[tuple[str, str]], reasons: list[str] = (),
                    flags: list[str] = ()) -> None:
        with self._connect() as db:
            db.execute("INSERT OR IGNORE INTO candidates (candidate_id, updated_at) VALUES (?, ?)",
                       (candidate_id, now.isoformat()))
            db.execute(
                "UPDATE candidates SET state = ?, extracted = ?, outcome = ?, reasons = ?, flags = ?, "
                "updated_at = ? WHERE candidate_id = ?",
                (json.dumps(state, ensure_ascii=False), json.dumps(extracted, ensure_ascii=False),
                 outcome, json.dumps(list(reasons)), json.dumps(list(flags)), now.isoformat(),
                 candidate_id))
            db.executemany("INSERT INTO events (candidate_id, type, detail, actor, at) VALUES (?, ?, ?, ?, ?)",
                           [(candidate_id, t, d, AGENT, now.isoformat()) for t, d in events])
            db.executemany("INSERT INTO messages (candidate_id, role, text, at) VALUES (?, ?, ?, ?)",
                           [(candidate_id, r, x, now.isoformat()) for r, x in messages])

    def save_summary(self, candidate_id: str, summary: str) -> None:
        with self._connect() as db:
            db.execute("UPDATE candidates SET summary = ? WHERE candidate_id = ?", (summary, candidate_id))

    # -- written by recruiters (never touched by chat turns) -----------------

    def set_status(self, candidate_id: str, status: RecruiterStatus, recruiter: str, now: datetime) -> None:
        status = RecruiterStatus(status)
        self._recruiter_action(candidate_id, recruiter, now, "recruiter_status", status.value,
                               "INSERT INTO recruiter (candidate_id, status, updated_at) VALUES (?, ?, ?) "
                               "ON CONFLICT(candidate_id) DO UPDATE SET status = excluded.status, "
                               "updated_at = excluded.updated_at",
                               (candidate_id, status.value, now.isoformat()))

    def assign(self, candidate_id: str, assignee: str, recruiter: str, now: datetime) -> None:
        assignee = assignee.strip()
        if not assignee:
            raise ValueError("an assignee name is required")
        self._recruiter_action(candidate_id, recruiter, now, "recruiter_assigned", assignee,
                               "INSERT INTO recruiter (candidate_id, assignee, updated_at) VALUES (?, ?, ?) "
                               "ON CONFLICT(candidate_id) DO UPDATE SET assignee = excluded.assignee, "
                               "updated_at = excluded.updated_at",
                               (candidate_id, assignee, now.isoformat()))

    def add_note(self, candidate_id: str, text: str, author: str, now: datetime) -> None:
        text = text.strip()
        if not text:
            raise ValueError("a note cannot be empty")
        self._recruiter_action(candidate_id, author, now, "recruiter_note", "",
                               "INSERT INTO notes (candidate_id, author, text, at) VALUES (?, ?, ?, ?)",
                               (candidate_id, author.strip(), text, now.isoformat()))

    def _recruiter_action(self, candidate_id: str, recruiter: str, now: datetime, event_type: str,
                          detail: str, sql: str, params: tuple) -> None:
        recruiter = recruiter.strip()
        if not recruiter:
            raise ValueError("the recruiter's name is required")
        with self._connect() as db:
            if db.execute("SELECT 1 FROM candidates WHERE candidate_id = ?", (candidate_id,)).fetchone() is None:
                raise LookupError(f"no candidate {candidate_id}")
            db.execute(sql, params)
            db.execute("INSERT INTO events (candidate_id, type, detail, actor, at) VALUES (?, ?, ?, ?, ?)",
                       (candidate_id, event_type, detail, f"recruiter:{recruiter}", now.isoformat()))

    # -- reads ---------------------------------------------------------------

    def get(self, candidate_id: str) -> Record | None:
        with self._connect() as db:
            row = db.execute(
                f"SELECT {_CANDIDATE_COLUMNS} FROM candidates c LEFT JOIN recruiter r "
                "ON r.candidate_id = c.candidate_id WHERE c.candidate_id = ?", (candidate_id,)).fetchone()
        return _record(row) if row else None

    def list_candidates(self, outcome: str | None = None,
                        status: RecruiterStatus | None = None) -> list[Record]:
        status_value = RecruiterStatus(status).value if status else None
        with self._connect() as db:
            rows = db.execute(
                f"SELECT {_CANDIDATE_COLUMNS} FROM candidates c LEFT JOIN recruiter r "
                "ON r.candidate_id = c.candidate_id "
                "WHERE (? IS NULL OR c.outcome = ?) AND (? IS NULL OR COALESCE(r.status, 'new') = ?) "
                "ORDER BY c.updated_at DESC", (outcome, outcome, status_value, status_value)).fetchall()
        return [_record(r) for r in rows]

    def recruiter(self, candidate_id: str) -> RecruiterRecord:
        with self._connect() as db:
            row = db.execute("SELECT status, assignee, updated_at FROM recruiter WHERE candidate_id = ?",
                             (candidate_id,)).fetchone()
        if row is None:
            return RecruiterRecord(RecruiterStatus.NEW, None, None)
        return RecruiterRecord(RecruiterStatus(row[0]), row[1], datetime.fromisoformat(row[2]))

    def notes(self, candidate_id: str) -> list[Note]:
        with self._connect() as db:
            rows = db.execute("SELECT author, text, at FROM notes WHERE candidate_id = ? ORDER BY id",
                              (candidate_id,)).fetchall()
        return [Note(a, t, datetime.fromisoformat(at)) for a, t, at in rows]

    def events(self, candidate_id: str) -> list[Event]:
        with self._connect() as db:
            rows = db.execute("SELECT type, detail, at, actor FROM events WHERE candidate_id = ? ORDER BY id",
                              (candidate_id,)).fetchall()
        return [Event(t, d, datetime.fromisoformat(a), actor) for t, d, a, actor in rows]

    def messages(self, candidate_id: str) -> list[Message]:
        with self._connect() as db:
            rows = db.execute("SELECT role, text, at FROM messages WHERE candidate_id = ? ORDER BY id",
                              (candidate_id,)).fetchall()
        return [Message(r, t, datetime.fromisoformat(a)) for r, t, a in rows]


def _record(row) -> Record:
    candidate_id, state, extracted, summary, outcome, reasons, flags, updated_at, status, assignee = row
    return Record(candidate_id, json.loads(state), json.loads(extracted), summary, outcome,
                  datetime.fromisoformat(updated_at), json.loads(reasons), json.loads(flags),
                  RecruiterStatus(status), assignee)
