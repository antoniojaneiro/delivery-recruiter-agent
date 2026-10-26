"""D48: call slots and bookings. A mixin of Store; it uses the store's `_connect`."""
import sqlite3
from datetime import datetime

from sazon.store_types import AGENT, Booking, InputError, Slot, stamp as _stamp

_SLOT_SELECT = "SELECT id, country, starts_at, recruiter, candidate_id, cancelled_at FROM slots"
_BOOKING_SELECT = "SELECT id, country, starts_at, recruiter FROM slots"


def _slot(row) -> Slot:
    slot_id, country, starts_at, recruiter, candidate_id, cancelled_at = row
    return Slot(slot_id, country, datetime.fromisoformat(starts_at), recruiter, candidate_id, bool(cancelled_at))


def _booking(row) -> Booking:
    slot_id, country, starts_at, recruiter = row
    return Booking(slot_id, country, datetime.fromisoformat(starts_at), recruiter)


class SlotsMixin:
    calendar = None  # set by Store: None means this client does not book calls

    def _calendar(self):
        if self.calendar is None:
            raise InputError("no_calendar", "this client does not book calls")
        return self.calendar

    # -- call slots (D48) ----------------------------------------------------

    def add_slot(self, country: str, starts_at: datetime, recruiter: str | None, created_by: str,
                 now: datetime) -> int:
        created_by = (created_by or "").strip()
        if not created_by:
            raise InputError("name_required", "the recruiter's name is required")
        calendar = self._calendar()
        if country not in calendar.timezones:
            raise InputError("unknown_country", f"unknown country {country}")
        if not calendar.wall_time_exists(country, starts_at):
            raise InputError("clock_change", "that time does not exist on the day the clocks change")
        if not calendar.has_enough_notice(country, starts_at, now):
            raise InputError("too_soon", "the slot is in the past or too soon")
        with self._connect() as db:
            cursor = db.execute(
                "INSERT INTO slots (country, starts_at, recruiter, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
                (country, starts_at.isoformat(), (recruiter or "").strip() or None, created_by, _stamp(now)))
            return cursor.lastrowid

    def free_slots(self, country: str, now: datetime, limit: int = 3) -> list[Slot]:
        if self.calendar is None:
            return []
        with self._connect() as db:
            rows = db.execute(f"{_SLOT_SELECT} WHERE country = ? AND candidate_id IS NULL AND cancelled_at IS NULL "
                              "ORDER BY starts_at, id", (country,)).fetchall()
        free, seen = [], set()
        for slot in map(_slot, rows):
            if slot.starts_at not in seen and self.calendar.has_enough_notice(slot.country, slot.starts_at, now):
                seen.add(slot.starts_at)  # two recruiters at the same time make one option, not two
                free.append(slot)
        return free[:limit]

    def slots(self, now: datetime, include_past: bool = False, include_cancelled: bool = False) -> list[Slot]:
        if self.calendar is None:
            return []
        with self._connect() as db:
            rows = db.execute(f"{_SLOT_SELECT} ORDER BY starts_at, id").fetchall()
        found = [_slot(r) for r in rows]
        if not include_cancelled:
            found = [s for s in found if not s.cancelled]
        if not include_past:
            found = [s for s in found if self.calendar.has_enough_notice(s.country, s.starts_at, now - self.calendar.min_notice)]
        return found

    def book_slot(self, slot_id: int, candidate_id: str, now: datetime, must_exist: bool = False) -> Booking | None:
        """Books the slot for the candidate, once. Asking again returns the booking they already hold.
        With `must_exist` nothing is booked for a candidate whose record is gone (erased a moment ago)."""
        try:
            return self._book_slot(slot_id, candidate_id, now, must_exist)
        except sqlite3.IntegrityError:  # another process booked for this candidate first
            return self.booking_of(candidate_id)

    def _held_booking(self, db, candidate_id: str):
        return db.execute(f"{_BOOKING_SELECT} WHERE candidate_id = ? AND cancelled_at IS NULL",
                          (candidate_id,)).fetchone()

    def _book_slot(self, slot_id: int, candidate_id: str, now: datetime, must_exist: bool) -> Booking | None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if must_exist and db.execute("SELECT 1 FROM candidates WHERE candidate_id = ?", (candidate_id,)).fetchone() is None:
                return None
            held = self._held_booking(db, candidate_id)
            if held:
                return _booking(held)
            row = db.execute(f"{_BOOKING_SELECT} WHERE id = ? AND candidate_id IS NULL AND cancelled_at IS NULL",
                             (slot_id,)).fetchone()
            if row is None:
                return None
            booking = _booking(row)
            if not self.calendar.has_enough_notice(booking.country, booking.starts_at, now):
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
            raise InputError("name_required", "the recruiter's name is required")
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
