import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sazon import config, slot_time
from sazon.model import RecruiterStatus

AGENT = "agent"
NO_CHECK = object()  # commit_turn without a version check (tests and tools that own the whole record)


class ConflictError(Exception):
    """The candidate's record changed, or was erased, after this copy was loaded."""
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
    version INTEGER NOT NULL DEFAULT 0,
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
CREATE TABLE IF NOT EXISTS slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    country TEXT NOT NULL,
    starts_at TEXT NOT NULL,
    recruiter TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    candidate_id TEXT,
    booked_at TEXT,
    cancelled_at TEXT,
    cancelled_by TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS one_booking_per_candidate
    ON slots(candidate_id) WHERE candidate_id IS NOT NULL AND cancelled_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_candidates_outcome ON candidates(outcome);
CREATE INDEX IF NOT EXISTS idx_events_candidate ON events(candidate_id, id);
CREATE INDEX IF NOT EXISTS idx_messages_candidate ON messages(candidate_id, id);
CREATE INDEX IF NOT EXISTS idx_slots_country_start ON slots(country, starts_at);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    delivered_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_outbox_pending ON outbox(delivered_at, candidate_id);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    changed_by TEXT,
    changed_at TEXT
);
CREATE TABLE IF NOT EXISTS admin_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    author TEXT NOT NULL,
    text TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notes_candidate ON notes(candidate_id, id);
"""

# Columns added after the first release; databases created earlier are upgraded in place.
_ADDED_COLUMNS = {
    "candidates": {"reasons": "TEXT NOT NULL DEFAULT '[]'", "flags": "TEXT NOT NULL DEFAULT '[]'",
                   "outcome": "TEXT", "version": "INTEGER NOT NULL DEFAULT 0"},
    "events": {"actor": "TEXT NOT NULL DEFAULT 'agent'"},
}

_CANDIDATE_COLUMNS = ("c.candidate_id, c.state, c.extracted, c.summary, c.outcome, c.reasons, c.flags, "
                      "c.updated_at, COALESCE(r.status, 'new'), r.assignee, "
                      "s.id, s.country, s.starts_at, s.recruiter, c.version")
_CANDIDATE_JOINS = ("FROM candidates c LEFT JOIN recruiter r ON r.candidate_id = c.candidate_id "
                    "LEFT JOIN slots s ON s.candidate_id = c.candidate_id AND s.cancelled_at IS NULL")


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
    booking: "Booking | None" = None
    version: int = 0


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
class Slot:
    id: int
    country: str
    starts_at: datetime  # wall-clock time in the country's own zone
    recruiter: str | None
    candidate_id: str | None
    cancelled: bool


@dataclass(frozen=True)
class Booking:
    slot_id: int
    country: str
    starts_at: datetime
    recruiter: str | None


@dataclass(frozen=True)
class OutboxEntry:
    id: int
    candidate_id: str
    text: str
    created_at: datetime


@dataclass(frozen=True)
class AdminEntry:
    at: datetime
    actor: str
    action: str
    detail: str


@dataclass(frozen=True)
class Note:
    author: str
    text: str
    at: datetime


class Store:
    def __init__(self, path: Path | str):
        self._path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")  # readers (the dashboard) do not block the chat's writes
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
                    flags: list[str] = (), summary: str | None = None,
                    expected_version: object = NO_CHECK, outbox: list[str] = ()) -> int:
        """Saves one turn atomically. With `expected_version` (the version this copy was loaded at, or None for a
        candidate that did not exist) the save is refused with ConflictError if the record changed or vanished."""
        with self._connect() as db:
            row = db.execute("SELECT version FROM candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
            if expected_version is not NO_CHECK:
                if (expected_version is None and row is not None) or (
                        expected_version is not None and (row is None or row[0] != expected_version)):
                    raise ConflictError(candidate_id)
            db.execute("INSERT OR IGNORE INTO candidates (candidate_id, updated_at) VALUES (?, ?)",
                       (candidate_id, now.isoformat()))
            db.execute(
                "UPDATE candidates SET state = ?, extracted = ?, outcome = ?, reasons = ?, flags = ?, "
                "summary = COALESCE(?, summary), version = version + 1, updated_at = ? WHERE candidate_id = ?",
                (json.dumps(state, ensure_ascii=False), json.dumps(extracted, ensure_ascii=False),
                 outcome, json.dumps(list(reasons)), json.dumps(list(flags)), summary, now.isoformat(),
                 candidate_id))
            db.executemany("INSERT INTO events (candidate_id, type, detail, actor, at) VALUES (?, ?, ?, ?, ?)",
                           [(candidate_id, t, d, AGENT, now.isoformat()) for t, d in events])
            db.executemany("INSERT INTO messages (candidate_id, role, text, at) VALUES (?, ?, ?, ?)",
                           [(candidate_id, r, x, now.isoformat()) for r, x in messages])
            db.executemany("INSERT INTO outbox (candidate_id, text, created_at) VALUES (?, ?, ?)",
                           [(candidate_id, text, now.isoformat()) for text in outbox])
            return db.execute("SELECT version FROM candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()[0]

    def erase_candidate(self, candidate_id: str, actor: str, now: datetime, reason: str) -> bool:
        """Removes everything about a candidate and keeps only an anonymous line saying who erased which
        (hashed) id and why (D53). The bytes are overwritten and the write-ahead log is truncated, because a
        plain DELETE would leave the data in free pages and in the log."""
        with self._connect() as db:
            db.execute("PRAGMA secure_delete = ON")
            existed = db.execute("SELECT 1 FROM candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
            for table in ("candidates", "events", "messages", "notes", "recruiter", "outbox"):
                db.execute(f"DELETE FROM {table} WHERE candidate_id = ?", (candidate_id,))
            db.execute("UPDATE slots SET candidate_id = NULL, booked_at = NULL WHERE candidate_id = ?", (candidate_id,))
            if existed:
                digest = hashlib.sha256(candidate_id.encode("utf-8")).hexdigest()[:12]
                self._log(db, actor, "candidate_erased", f"id_sha256={digest} reason={reason}", now)
        raw = sqlite3.connect(self._path, timeout=BUSY_TIMEOUT_SECONDS)
        try:
            raw.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            raw.close()
        return existed is not None

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

    # -- messages waiting to be delivered by a real channel (D58) ---------------

    def outbox_pending(self, candidate_id: str | None = None) -> list[OutboxEntry]:
        with self._connect() as db:
            rows = db.execute("SELECT id, candidate_id, text, created_at FROM outbox WHERE delivered_at IS NULL "
                              "AND (? IS NULL OR candidate_id = ?) ORDER BY id", (candidate_id, candidate_id)).fetchall()
        return [OutboxEntry(i, c, t, datetime.fromisoformat(at)) for i, c, t, at in rows]

    def mark_delivered(self, entry_id: int, now: datetime) -> None:
        with self._connect() as db:
            db.execute("UPDATE outbox SET delivered_at = ? WHERE id = ?", (now.isoformat(), entry_id))

    def last_activity(self) -> dict[str, datetime]:
        """When each candidate last wrote or was written to in the chat (the chat writes naive local times)."""
        with self._connect() as db:
            rows = db.execute("SELECT candidate_id, MAX(at) FROM messages GROUP BY candidate_id").fetchall()
        return {cid: datetime.fromisoformat(at) for cid, at in rows}

    # -- settings and the admin log (D56) --------------------------------------

    def accepting_applications(self) -> bool:
        with self._connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key = 'accepting'").fetchone()
        return row is None or row[0] == "1"

    def set_accepting(self, accepting: bool, recruiter: str, now: datetime) -> None:
        recruiter = (recruiter or "").strip()
        if not recruiter:
            raise ValueError("the recruiter's name is required")
        with self._connect() as db:
            db.execute("INSERT INTO settings (key, value, changed_by, changed_at) VALUES ('accepting', ?, ?, ?) "
                       "ON CONFLICT(key) DO UPDATE SET value = excluded.value, changed_by = excluded.changed_by, "
                       "changed_at = excluded.changed_at", ("1" if accepting else "0", recruiter, now.isoformat()))
            self._log(db, f"recruiter:{recruiter}", "applications_opened" if accepting else "applications_closed", "", now)

    def admin_log(self) -> list[AdminEntry]:
        with self._connect() as db:
            rows = db.execute("SELECT at, actor, action, detail FROM admin_log ORDER BY id").fetchall()
        return [AdminEntry(datetime.fromisoformat(at), actor, action, detail) for at, actor, action, detail in rows]

    @staticmethod
    def _log(db, actor: str, action: str, detail: str, now: datetime) -> None:
        db.execute("INSERT INTO admin_log (at, actor, action, detail) VALUES (?, ?, ?, ?)",
                   (now.isoformat(), actor, action, detail))

    # -- call slots (D48) ----------------------------------------------------

    def add_slot(self, country: str, starts_at: datetime, recruiter: str | None, created_by: str,
                 now: datetime) -> int:
        created_by = (created_by or "").strip()
        if not created_by:
            raise ValueError("the recruiter's name is required")
        if country not in config.COUNTRY_TZ:
            raise ValueError(f"unknown country {country}")
        if not slot_time.wall_time_exists(country, starts_at):
            raise ValueError("that time does not exist on the day the clocks change")
        if not slot_time.has_enough_notice(country, starts_at, now):
            raise ValueError("the slot is in the past or too soon")
        with self._connect() as db:
            cursor = db.execute(
                "INSERT INTO slots (country, starts_at, recruiter, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
                (country, starts_at.isoformat(), (recruiter or "").strip() or None, created_by, _stamp(now)))
            return cursor.lastrowid

    def free_slots(self, country: str, now: datetime, limit: int = 3) -> list[Slot]:
        with self._connect() as db:
            rows = db.execute(f"{_SLOT_SELECT} WHERE country = ? AND candidate_id IS NULL AND cancelled_at IS NULL "
                              "ORDER BY starts_at, id", (country,)).fetchall()
        free, seen = [], set()
        for slot in map(_slot, rows):
            if slot.starts_at not in seen and slot_time.has_enough_notice(slot.country, slot.starts_at, now):
                seen.add(slot.starts_at)  # two recruiters at the same time make one option, not two
                free.append(slot)
        return free[:limit]

    def slots(self, now: datetime, include_past: bool = False, include_cancelled: bool = False) -> list[Slot]:
        with self._connect() as db:
            rows = db.execute(f"{_SLOT_SELECT} ORDER BY starts_at, id").fetchall()
        found = [_slot(r) for r in rows]
        if not include_cancelled:
            found = [s for s in found if not s.cancelled]
        if not include_past:
            found = [s for s in found if slot_time.has_enough_notice(s.country, s.starts_at, now - slot_time.MIN_NOTICE)]
        return found

    def book_slot(self, slot_id: int, candidate_id: str, now: datetime) -> Booking | None:
        """Books the slot for the candidate, once. Asking again returns the booking they already hold."""
        try:
            return self._book_slot(slot_id, candidate_id, now)
        except sqlite3.IntegrityError:  # another process booked for this candidate first
            return self.booking_of(candidate_id)

    def _held_booking(self, db, candidate_id: str):
        return db.execute(f"{_BOOKING_SELECT} WHERE candidate_id = ? AND cancelled_at IS NULL",
                          (candidate_id,)).fetchone()

    def _book_slot(self, slot_id: int, candidate_id: str, now: datetime) -> Booking | None:
        with self._connect() as db:
            held = self._held_booking(db, candidate_id)
            if held:
                return _booking(held)
            row = db.execute(f"{_BOOKING_SELECT} WHERE id = ? AND candidate_id IS NULL AND cancelled_at IS NULL",
                             (slot_id,)).fetchone()
            if row is None:
                return None
            booking = _booking(row)
            if not slot_time.has_enough_notice(booking.country, booking.starts_at, now):
                return None
            updated = db.execute("UPDATE slots SET candidate_id = ?, booked_at = ? "
                                 "WHERE id = ? AND candidate_id IS NULL AND cancelled_at IS NULL",
                                 (candidate_id, _stamp(now), slot_id)).rowcount
            if updated == 0:
                return None
            db.execute("INSERT INTO events (candidate_id, type, detail, actor, at) VALUES (?, ?, ?, ?, ?)",
                       (candidate_id, "slot_booked", f"{booking.country} {booking.starts_at.isoformat()}",
                        AGENT, _stamp(now)))
            return booking

    def booking_of(self, candidate_id: str) -> Booking | None:
        with self._connect() as db:
            row = db.execute(f"{_BOOKING_SELECT} WHERE candidate_id = ? AND cancelled_at IS NULL",
                             (candidate_id,)).fetchone()
        return _booking(row) if row else None

    def cancel_slot(self, slot_id: int, recruiter: str, now: datetime) -> str | None:
        """Cancels a slot. Returns the candidate who had booked it, if any, who must be told."""
        recruiter = (recruiter or "").strip()
        if not recruiter:
            raise ValueError("the recruiter's name is required")
        with self._connect() as db:
            row = db.execute("SELECT candidate_id, cancelled_at, starts_at, country FROM slots WHERE id = ?",
                             (slot_id,)).fetchone()
            if row is None:
                raise LookupError(f"no slot {slot_id}")
            candidate_id, cancelled_at, starts_at, country = row
            if cancelled_at:
                return None
            db.execute("UPDATE slots SET cancelled_at = ?, cancelled_by = ? WHERE id = ?",
                       (_stamp(now), recruiter, slot_id))
            if candidate_id:
                db.execute("INSERT INTO events (candidate_id, type, detail, actor, at) VALUES (?, ?, ?, ?, ?)",
                           (candidate_id, "slot_cancelled", f"{country} {starts_at}",
                            f"recruiter:{recruiter}", _stamp(now)))
            return candidate_id

    # -- reads ---------------------------------------------------------------

    def get(self, candidate_id: str) -> Record | None:
        with self._connect() as db:
            row = db.execute(
                f"SELECT {_CANDIDATE_COLUMNS} {_CANDIDATE_JOINS} WHERE c.candidate_id = ?",
                (candidate_id,)).fetchone()
        return _record(row) if row else None

    def list_candidates(self, outcome: str | None = None,
                        status: RecruiterStatus | None = None) -> list[Record]:
        status_value = RecruiterStatus(status).value if status else None
        with self._connect() as db:
            rows = db.execute(
                f"SELECT {_CANDIDATE_COLUMNS} {_CANDIDATE_JOINS} "
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


_SLOT_SELECT = "SELECT id, country, starts_at, recruiter, candidate_id, cancelled_at FROM slots"
_BOOKING_SELECT = "SELECT id, country, starts_at, recruiter FROM slots"


def _stamp(now: datetime) -> str:
    return now.isoformat()


def _slot(row) -> Slot:
    slot_id, country, starts_at, recruiter, candidate_id, cancelled_at = row
    return Slot(slot_id, country, datetime.fromisoformat(starts_at), recruiter, candidate_id, bool(cancelled_at))


def _booking(row) -> Booking:
    slot_id, country, starts_at, recruiter = row
    return Booking(slot_id, country, datetime.fromisoformat(starts_at), recruiter)


def _record(row) -> Record:
    (candidate_id, state, extracted, summary, outcome, reasons, flags, updated_at, status, assignee,
     slot_id, country, starts_at, slot_recruiter, version) = row
    booking = Booking(slot_id, country, datetime.fromisoformat(starts_at), slot_recruiter) if slot_id else None
    return Record(candidate_id, json.loads(state), json.loads(extracted), summary, outcome,
                  datetime.fromisoformat(updated_at), json.loads(reasons), json.loads(flags),
                  RecruiterStatus(status), assignee, booking, version)
