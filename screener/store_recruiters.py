"""D80: the recruiters and their sign-in. A mixin of Store; it uses the store's `_connect`."""
import json
import sqlite3
from datetime import datetime

from screener.recruiters import (LOCK_SECONDS, MAX_FAILURES, MIN_PASSWORD_LENGTH, Recruiter, TooManyAttempts,
                                 hash_password, is_email, normal_email, password_matches, spend_the_same_time)
from screener.store_types import InputError, parse_stamp, stamp


class RecruitersMixin:
    calendar = None

    def _check_new_password(self, password: str) -> None:
        if len(password or "") < MIN_PASSWORD_LENGTH:
            raise InputError("password_short", f"the password needs at least {MIN_PASSWORD_LENGTH} characters")

    def add_recruiter(self, email: str, name: str, country: str, password: str, created_by: str,
                      now: datetime) -> Recruiter:
        email, name = normal_email(email), " ".join((name or "").split())
        if not is_email(email):
            raise InputError("email_invalid", "that is not an email address")
        if not name:
            raise InputError("name_missing", "a name is required")
        if self.calendar is None or country not in self.calendar.timezones:
            raise InputError("unknown_country", f"unknown country {country}")
        self._check_new_password(password)
        salt, digest, params = hash_password(password)
        try:
            with self._connect() as db:
                db.execute("INSERT INTO recruiters (email, name, country, salt, hash, params, created_by, created_at) "
                           "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           (email, name, country, salt.hex(), digest.hex(), json.dumps(params), created_by, stamp(now)))
                self._log(db, created_by, "recruiter_created", f"{email} ({country})", now)
        except sqlite3.IntegrityError:
            raise InputError("exists", f"there is already a recruiter with {email}") from None
        return Recruiter(email, name, country, now)

    def recruiters(self) -> list[Recruiter]:
        with self._connect() as db:
            rows = db.execute("SELECT email, name, country, created_at FROM recruiters ORDER BY email").fetchall()
        return [Recruiter(e, n, c, parse_stamp(at)) for e, n, c, at in rows]

    def get_recruiter(self, email: str) -> Recruiter | None:
        with self._connect() as db:
            row = db.execute("SELECT email, name, country, created_at FROM recruiters WHERE email = ?",
                             (normal_email(email),)).fetchone()
        return Recruiter(row[0], row[1], row[2], parse_stamp(row[3])) if row else None

    def remove_recruiter(self, email: str, removed_by: str, now: datetime) -> bool:
        email = normal_email(email)
        with self._connect() as db:
            gone = db.execute("DELETE FROM recruiters WHERE email = ?", (email,)).rowcount
            if gone:
                self._log(db, removed_by, "recruiter_removed", email, now)
        return bool(gone)

    # -- signing in -------------------------------------------------------------------------------------------------

    def locked(self, key: str, now: datetime) -> bool:
        """True after MAX_FAILURES wrong passwords for `key` in the last LOCK_SECONDS (kept in the database)."""
        with self._connect() as db:
            recent = db.execute("SELECT COUNT(*) FROM login_failures WHERE key = ? AND at > ?",
                                (key, now.timestamp() - LOCK_SECONDS)).fetchone()[0]
        return recent >= MAX_FAILURES

    def note_login(self, key: str, success: bool, now: datetime) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM login_failures WHERE at <= ?", (now.timestamp() - LOCK_SECONDS,))
            if success:
                db.execute("DELETE FROM login_failures WHERE key = ?", (key,))
            else:
                db.execute("INSERT INTO login_failures (key, at) VALUES (?, ?)", (key, now.timestamp()))

    def verify_recruiter(self, email: str, password: str, now: datetime) -> Recruiter | None:
        """The recruiter when the password is right, else None. It does the same work either way. After MAX_FAILURES
        wrong passwords the email is locked for LOCK_SECONDS and TooManyAttempts is raised."""
        key = normal_email(email)
        if self.locked(key, now):
            raise TooManyAttempts(key)
        with self._connect() as db:
            row = db.execute("SELECT name, country, salt, hash, params, created_at FROM recruiters WHERE email = ?",
                             (key,)).fetchone()
        if row is None:
            spend_the_same_time(password)
            self.note_login(key, False, now)
            return None
        name, country, salt, digest, params, created_at = row
        ok = password_matches(password or "", bytes.fromhex(salt), bytes.fromhex(digest), json.loads(params))
        self.note_login(key, ok, now)
        return Recruiter(key, name, country, parse_stamp(created_at)) if ok else None

    def change_password(self, email: str, old: str, new: str, now: datetime) -> None:
        """A recruiter changes their own password; the old one is needed."""
        if self.verify_recruiter(email, old, now) is None:
            raise InputError("wrong_password", "the current password is wrong")
        self._check_new_password(new)
        self._store_password(normal_email(email), new)

    def reset_password(self, email: str, new: str, reset_by: str, now: datetime) -> None:
        """The hiring manager sets a new password for a recruiter who forgot theirs."""
        email = normal_email(email)
        if self.get_recruiter(email) is None:
            raise LookupError(f"no recruiter {email}")
        self._check_new_password(new)
        self._store_password(email, new)
        with self._connect() as db:
            db.execute("DELETE FROM login_failures WHERE key = ?", (email,))
            self._log(db, reset_by, "password_reset", email, now)

    def _store_password(self, email: str, password: str) -> None:
        salt, digest, params = hash_password(password)
        with self._connect() as db:
            db.execute("UPDATE recruiters SET salt = ?, hash = ?, params = ? WHERE email = ?",
                       (salt.hex(), digest.hex(), json.dumps(params), email))
