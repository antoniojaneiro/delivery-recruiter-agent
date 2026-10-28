"""D48: call slots and bookings. A mixin of Store; it uses the store's `_connect`."""
import sqlite3
from datetime import date, datetime, timedelta

from screener.store_types import AGENT, Booking, InputError, Slot, stamp as _stamp

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
        owner = self.get_recruiter(recruiter) if recruiter else None
        if owner is not None and owner.country != country:
            raise InputError("wrong_country", "a recruiter takes calls in their own country only")
        if not calendar.wall_time_exists(country, starts_at):
            raise InputError("clock_change", "that time does not exist on the day the clocks change")
        if not calendar.recruiter_may_book(country, starts_at, now):
            raise InputError("in_the_past", "the time has already started")
        with self._connect() as db:
            cursor = db.execute(
                "INSERT INTO slots (country, starts_at, recruiter, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
                (country, starts_at.isoformat(), (recruiter or "").strip() or None, created_by, _stamp(now)))
            return cursor.lastrowid

    def _may_take(self, as_recruiter: bool):
        """The rule for who is looking: a recruiter may take a time that has not started, a candidate only from tomorrow."""
        return self.calendar.recruiter_may_book if as_recruiter else self.calendar.candidate_may_book

    def free_slots(self, country: str, now: datetime, limit: int = 3, as_recruiter: bool = False) -> list[Slot]:
        """The next free times, one per start time (two recruiters at the same time are one option), as a candidate
        would be offered them, or as a recruiter may book them."""
        if self.calendar is None:
            return []
        self.sync_availability(now)
        here = (now if now.tzinfo else now.astimezone()).astimezone(self.calendar.zone(country)).replace(tzinfo=None)
        free, floor, may_take = [], here.isoformat(), self._may_take(as_recruiter)  # never look at times that have passed
        while len(free) < limit:
            with self._connect() as db:
                rows = db.execute("SELECT MIN(id), country, starts_at, recruiter, NULL, 0 FROM slots WHERE country = ? AND "
                                  "candidate_id IS NULL AND cancelled_at IS NULL AND starts_at > ? GROUP BY starts_at "
                                  "ORDER BY starts_at LIMIT ?", (country, floor, limit + 20)).fetchall()
            if not rows:
                break
            free += [s for s in map(_slot, rows) if may_take(s.country, s.starts_at, now)]
            floor = rows[-1][2]
        return free[:limit]

    def booked_slots(self, country: str, first: date, before: date) -> list[Slot]:
        """The booked calls of one country from `first` up to (not including) `before`: the calendar grid."""
        with self._connect() as db:
            rows = db.execute(f"{_SLOT_SELECT} WHERE country = ? AND candidate_id IS NOT NULL AND cancelled_at IS NULL "
                              "AND starts_at >= ? AND starts_at < ? ORDER BY starts_at, id",
                              (country, first.isoformat(), before.isoformat())).fetchall()
        return [_slot(r) for r in rows]

    def listed_slots(self, now: datetime, country: str | None = None, first: date | None = None,
                     before: date | None = None) -> list[Slot]:
        """What a person lists and cancels: the calls booked from now on and the times added by hand, optionally of one
        country and of the days from `first` up to `before`, cut in the database so the page never loads them all. Not
        the many free times made from recruiters' availability, which they change by changing the availability."""
        if self.calendar is None:
            return []
        where, args = "", []
        if country is not None:
            where += " AND country = ?"
            args.append(country)
        if first is not None:
            where += " AND starts_at >= ?"
            args.append(first.isoformat())
        if before is not None:
            where += " AND starts_at < ?"
            args.append(before.isoformat())
        with self._connect() as db:
            rows = db.execute(f"{_SLOT_SELECT} WHERE cancelled_at IS NULL AND (candidate_id IS NOT NULL OR "
                              f"created_by != 'availability'){where} ORDER BY starts_at, id", args).fetchall()
        return [s for s in map(_slot, rows) if self.calendar.recruiter_may_book(s.country, s.starts_at, now)]

    def free_slots_on(self, country: str, day: date, now: datetime, as_recruiter: bool = False) -> list[Slot]:
        """Every free time of one day, one per start time: what the picker shows once a day is chosen."""
        if self.calendar is None:
            return []
        self.sync_availability(now)
        start = datetime.combine(day, datetime.min.time())
        with self._connect() as db:
            rows = db.execute("SELECT MIN(id), country, starts_at, recruiter, NULL, 0 FROM slots WHERE country = ? AND "
                              "candidate_id IS NULL AND cancelled_at IS NULL AND starts_at >= ? AND starts_at < ? "
                              "GROUP BY starts_at ORDER BY starts_at",
                              (country, start.isoformat(), (start + timedelta(days=1)).isoformat())).fetchall()
        return [s for s in map(_slot, rows) if self._may_take(as_recruiter)(s.country, s.starts_at, now)]

    def slots(self, now: datetime, include_past: bool = False, include_cancelled: bool = False) -> list[Slot]:
        if self.calendar is None:
            return []
        with self._connect() as db:
            rows = db.execute(f"{_SLOT_SELECT} ORDER BY starts_at, id").fetchall()
        found = [_slot(r) for r in rows]
        if not include_cancelled:
            found = [s for s in found if not s.cancelled]
        if not include_past:
            found = [s for s in found if self.calendar.recruiter_may_book(s.country, s.starts_at, now)]
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
            row = db.execute(f"{_BOOKING_SELECT} WHERE id = ? AND cancelled_at IS NULL", (slot_id,)).fetchone()
            if row is None:
                return None
            booking = _booking(row)
            if not self.calendar.candidate_may_book(booking.country, booking.starts_at, now):
                return None
            slot_id = self._least_busy(db, booking.country, booking.starts_at)
            if slot_id is None:
                return None  # nobody is free at that time any more
            row = db.execute(f"{_BOOKING_SELECT} WHERE id = ?", (slot_id,)).fetchone()
            booking = _booking(row)
            updated = db.execute("UPDATE slots SET candidate_id = ?, booked_at = ? "
                                 "WHERE id = ? AND candidate_id IS NULL AND cancelled_at IS NULL",
                                 (candidate_id, _stamp(now), slot_id)).rowcount
            if updated == 0:
                return None
            db.execute("INSERT INTO events (candidate_id, type, detail, actor, at) VALUES (?, ?, ?, ?, ?)",
                       (candidate_id, "slot_booked", f"{booking.country} {booking.starts_at.isoformat()}",
                        AGENT, _stamp(now)))
            return booking

    def move_booking(self, candidate_id: str, slot_id: int, recruiter: str, now: datetime,
                     country: str | None = None) -> tuple[Booking, Booking | None]:
        """A recruiter books a time for a candidate, or moves the one they hold, in one step: the old time is freed (not
        cancelled), the new one booked and one audit line written by the recruiter. Returns the new booking and the
        one it replaced. Refused (InputError): no name, a time that is not free, in the wrong country, or already started."""
        calendar = self._calendar()
        recruiter = (recruiter or "").strip()
        if not recruiter:
            raise InputError("name_required", "the recruiter's name is required")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM candidates WHERE candidate_id = ?", (candidate_id,)).fetchone() is None:
                raise LookupError(f"no candidate {candidate_id}")
            held_row = self._held_booking(db, candidate_id)
            held = _booking(held_row) if held_row else None
            row = db.execute(f"{_BOOKING_SELECT} WHERE id = ? AND (candidate_id IS NULL OR candidate_id = ?) "
                             "AND cancelled_at IS NULL", (slot_id, candidate_id)).fetchone()
            if row is None:
                raise InputError("slot_unavailable", "that time is taken, cancelled or does not exist")
            booking = _booking(row)
            if held and held.slot_id == booking.slot_id:
                return booking, held  # already theirs: nothing changes
            if country is not None and booking.country != country:
                raise InputError("wrong_country", "that time is in another country than the candidate's")
            slot_id = self._least_busy(db, booking.country, booking.starts_at) or slot_id  # the least busy recruiter then
            booking = _booking(db.execute(f"{_BOOKING_SELECT} WHERE id = ?", (slot_id,)).fetchone())
            if not calendar.recruiter_may_book(booking.country, booking.starts_at, now):
                raise InputError("in_the_past", "the time has already started")
            if held:
                db.execute("UPDATE slots SET candidate_id = NULL, booked_at = NULL WHERE id = ?", (held.slot_id,))
            db.execute("UPDATE slots SET candidate_id = ?, booked_at = ? WHERE id = ? AND candidate_id IS NULL",
                       (candidate_id, _stamp(now), slot_id))
            detail = f"{booking.country} {booking.starts_at.isoformat()}"
            if held:
                detail += f" (was {held.country} {held.starts_at.isoformat()})"
            db.execute("INSERT INTO events (candidate_id, type, detail, actor, at) VALUES (?, ?, ?, ?, ?)",
                       (candidate_id, "slot_moved" if held else "slot_booked", detail, f"recruiter:{recruiter}",
                        _stamp(now)))
            return booking, held

    @staticmethod
    def _least_busy(db, country: str, starts_at: datetime) -> int | None:
        """Of the recruiters free at this time, the one with the fewest calls that day, then by email. The row offered
        stands in for its time: a candidate who picks it is given whoever is free then, even when that row was taken."""
        free = db.execute("SELECT id, recruiter FROM slots WHERE country = ? AND starts_at = ? AND candidate_id IS NULL "
                          "AND cancelled_at IS NULL", (country, starts_at.isoformat())).fetchall()
        if len(free) < 2:
            return free[0][0] if free else None
        day = starts_at.date().isoformat()

        def load(entry) -> tuple:
            calls = db.execute("SELECT COUNT(*) FROM slots WHERE recruiter = ? AND candidate_id IS NOT NULL AND cancelled_at "
                               "IS NULL AND substr(starts_at, 1, 10) = ?", (entry[1], day)).fetchone()[0]
            return calls, entry[1] or "", entry[0]
        return min(free, key=load)[0]

    def booking_of(self, candidate_id: str) -> Booking | None:
        with self._connect() as db:
            row = db.execute(f"{_BOOKING_SELECT} WHERE candidate_id = ? AND cancelled_at IS NULL",
                             (candidate_id,)).fetchone()
        return _booking(row) if row else None

    def reassign_call(self, slot_id: int, now: datetime) -> Booking | None:
        """The recruiter of a booked call can no longer take it: another recruiter free at the same time takes it over
        (the least busy), the candidate keeps their time. None when nobody else is free then."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT country, starts_at, candidate_id FROM slots WHERE id = ? AND cancelled_at IS NULL "
                             "AND candidate_id IS NOT NULL", (slot_id,)).fetchone()
            if row is None:
                return None
            country, starts_at, candidate_id = row
            new_id = self._least_busy(db, country, datetime.fromisoformat(starts_at))
            if new_id is None:
                return None
            db.execute("UPDATE slots SET candidate_id = NULL, booked_at = NULL, cancelled_at = ?, cancelled_by = ? WHERE id = ?",
                       (_stamp(now), "availability", slot_id))
            db.execute("UPDATE slots SET candidate_id = ?, booked_at = ? WHERE id = ?", (candidate_id, _stamp(now), new_id))
            db.execute("INSERT INTO events (candidate_id, type, detail, actor, at) VALUES (?, ?, ?, ?, ?)",
                       (candidate_id, "slot_reassigned", f"{country} {starts_at}", AGENT, _stamp(now)))
            return _booking(db.execute(f"{_BOOKING_SELECT} WHERE id = ?", (new_id,)).fetchone())

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
