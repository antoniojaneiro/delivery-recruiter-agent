import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from sazon.model import RecruiterStatus
from sazon.store_schema import prepare
from sazon.store_slots import SlotsMixin
from sazon.store_types import (AGENT, NO_CHECK, AdminEntry, Booking, ConflictError, Event, InputError, Message,  # noqa: F401
                               Note, OutboxEntry, Record, RecruiterRecord, Slot)  # noqa: F401

BUSY_TIMEOUT_SECONDS = 10

_CANDIDATE_COLUMNS = ("c.candidate_id, c.state, c.extracted, c.summary, c.outcome, c.reasons, c.flags, "
                      "c.updated_at, COALESCE(r.status, 'new'), r.assignee, "
                      "s.id, s.country, s.starts_at, s.recruiter, c.version")
_CANDIDATE_JOINS = ("FROM candidates c LEFT JOIN recruiter r ON r.candidate_id = c.candidate_id "
                    "LEFT JOIN slots s ON s.candidate_id = c.candidate_id AND s.cancelled_at IS NULL")


class Store(SlotsMixin):
    def __init__(self, path: Path | str, calendar=None):
        self._path = str(path)
        self.calendar = calendar
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(40):  # several processes may open a new or old file at the same moment
            try:
                self._prepare()
                return
            except sqlite3.OperationalError as error:
                if "locked" not in str(error) or attempt == 39:
                    raise
                time.sleep(0.25)

    def _prepare(self) -> None:
        with self._connect() as db:
            prepare(db)

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
            db.execute("BEGIN IMMEDIATE")  # the version is read while holding the write lock, so nobody slips in
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
                log_id = self._log(db, actor, "candidate_erased", f"id_sha256={digest} reason={reason}", now)
        if existed:
            complete = self._checkpoint()
            with self._connect() as db:
                db.execute("UPDATE admin_log SET detail = detail || ? WHERE id = ?",
                           (f" checkpoint={'complete' if complete else 'incomplete'}", log_id))
        else:
            self._checkpoint()
        return existed is not None

    def _checkpoint(self) -> bool:
        """Empties the write-ahead log so erased bytes are not left in it. False if a reader kept it from finishing."""
        raw = sqlite3.connect(self._path, timeout=BUSY_TIMEOUT_SECONDS)
        try:
            busy = raw.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]
        finally:
            raw.close()
        return busy == 0

    # -- written by recruiters (never touched by chat turns) -----------------

    def set_status(self, candidate_id: str, status: RecruiterStatus, recruiter: str, now: datetime) -> None:
        try:
            status = RecruiterStatus(status)
        except ValueError:
            raise InputError("unknown_status", f"unknown status {status}") from None
        self._recruiter_action(candidate_id, recruiter, now, "recruiter_status", status.value,
                               "INSERT INTO recruiter (candidate_id, status, updated_at) VALUES (?, ?, ?) "
                               "ON CONFLICT(candidate_id) DO UPDATE SET status = excluded.status, "
                               "updated_at = excluded.updated_at",
                               (candidate_id, status.value, now.isoformat()))

    def assign(self, candidate_id: str, assignee: str, recruiter: str, now: datetime) -> None:
        assignee = assignee.strip()
        if not assignee:
            raise InputError("assignee_required", "an assignee name is required")
        self._recruiter_action(candidate_id, recruiter, now, "recruiter_assigned", assignee,
                               "INSERT INTO recruiter (candidate_id, assignee, updated_at) VALUES (?, ?, ?) "
                               "ON CONFLICT(candidate_id) DO UPDATE SET assignee = excluded.assignee, "
                               "updated_at = excluded.updated_at",
                               (candidate_id, assignee, now.isoformat()))

    def add_note(self, candidate_id: str, text: str, author: str, now: datetime) -> None:
        text = text.strip()
        if not text:
            raise InputError("note_empty", "a note cannot be empty")
        self._recruiter_action(candidate_id, author, now, "recruiter_note", "",
                               "INSERT INTO notes (candidate_id, author, text, at) VALUES (?, ?, ?, ?)",
                               (candidate_id, author.strip(), text, now.isoformat()))

    def _recruiter_action(self, candidate_id: str, recruiter: str, now: datetime, event_type: str,
                          detail: str, sql: str, params: tuple) -> None:
        recruiter = recruiter.strip()
        if not recruiter:
            raise InputError("name_required", "the recruiter's name is required")
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

    def revision(self) -> int:
        """Moves whenever a candidate, a recruiter's status or assignee, or a slot changes. Reading never moves it."""
        with self._connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key = 'rev'").fetchone()
        return int(row[0]) if row else 0

    def last_activity_of(self, candidate_id: str) -> datetime | None:
        with self._connect() as db:
            row = db.execute("SELECT MAX(at) FROM messages WHERE candidate_id = ?", (candidate_id,)).fetchone()
        return datetime.fromisoformat(row[0]) if row and row[0] else None

    # -- settings and the admin log (D56) --------------------------------------

    def accepting_applications(self) -> bool:
        with self._connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key = 'accepting'").fetchone()
        return row is None or row[0] == "1"

    def set_accepting(self, accepting: bool, recruiter: str, now: datetime) -> None:
        recruiter = (recruiter or "").strip()
        if not recruiter:
            raise InputError("name_required", "the recruiter's name is required")
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
    def _log(db, actor: str, action: str, detail: str, now: datetime) -> int:
        return db.execute("INSERT INTO admin_log (at, actor, action, detail) VALUES (?, ?, ?, ?)",
                          (now.isoformat(), actor, action, detail)).lastrowid

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


def _record(row) -> Record:
    (candidate_id, state, extracted, summary, outcome, reasons, flags, updated_at, status, assignee,
     slot_id, country, starts_at, slot_recruiter, version) = row
    booking = Booking(slot_id, country, datetime.fromisoformat(starts_at), slot_recruiter) if slot_id else None
    return Record(candidate_id, json.loads(state), json.loads(extracted), summary, outcome,
                  datetime.fromisoformat(updated_at), json.loads(reasons), json.loads(flags),
                  RecruiterStatus(status), assignee, booking, version)
