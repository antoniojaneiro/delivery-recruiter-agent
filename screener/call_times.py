"""Call times (D48, D79, D80, D82): the recruiters and how they sign in, their weekly hours and days off, the 15-minute times
made from them, and the bookings. One module because one booking needs all of it at once (is the recruiter there, in
that country, free, not already booked) in one atomic step; the candidates and the service's records are other parts of
the store (D88).

Each recruiter has a weekly pattern (the client's default, or their own) and days off. Free times are made from it as rows
of the `slots` table for the coming weeks, so booking, offers, cancelling and the funnel all use the one atomic code, and
capacity grows with every recruiter. A one-off time added by hand is never removed by the pattern."""
import json
import sqlite3
from datetime import date, datetime, time, timedelta

from screener.recruiters import (LOCK_SECONDS, MAX_FAILURES, MIN_PASSWORD_LENGTH, Recruiter, TooManyAttempts,
                                 hash_password, is_email, normal_email, password_matches, spend_the_same_time)
from screener.store_db import Part
from screener.store_types import AGENT, Booking, Call, InputError, Slot, parse_stamp, stamp, stamp as _stamp

_SLOT_SELECT = "SELECT id, country, starts_at, recruiter, candidate_id, cancelled_at FROM slots"
_BOOKING_SELECT = "SELECT id, country, starts_at, recruiter FROM slots"


def _slot(row) -> Slot:
    slot_id, country, starts_at, recruiter, candidate_id, cancelled_at = row
    return Slot(slot_id, country, datetime.fromisoformat(starts_at), recruiter, candidate_id, bool(cancelled_at))


def _booking(row) -> Booking:
    slot_id, country, starts_at, recruiter = row
    return Booking(slot_id, country, datetime.fromisoformat(starts_at), recruiter)


MADE = "availability"  # `created_by` of a row made from a pattern (a hand-added time has a person's name)


class CallTimes(Part):
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

    # -- what a recruiter's week is ---------------------------------------------------------------------------------

    def _windows(self, db, email: str) -> list[tuple[int, int, int]]:
        if db.execute("SELECT 1 FROM availability_custom WHERE email = ?", (email,)).fetchone():
            return [tuple(r) for r in db.execute("SELECT weekday, start_min, end_min FROM availability WHERE email = ? "
                                                 "ORDER BY weekday, start_min", (email,))]
        cal = self._calendar()
        return [(day, cal.default_start, cal.default_end) for day in cal.default_days]

    def weekly(self, email: str) -> list[tuple[int, int, int]]:
        """(weekday, start minute, end minute) windows of the week: their own, or the default."""
        with self._connect() as db:
            return self._windows(db, email)

    def is_custom(self, email: str) -> bool:
        with self._connect() as db:
            return db.execute("SELECT 1 FROM availability_custom WHERE email = ?", (email,)).fetchone() is not None

    def days_off(self, email: str) -> list[date]:
        with self._connect() as db:
            return [date.fromisoformat(r[0]) for r in db.execute("SELECT day FROM days_off WHERE email = ? ORDER BY day",
                                                                 (email,))]

    # -- changing it ------------------------------------------------------------------------------------------------

    def _known(self, db, email: str) -> str:
        row = db.execute("SELECT country FROM recruiters WHERE email = ?", (email,)).fetchone()
        if row is None:
            raise LookupError(f"no recruiter {email}")
        return row[0]

    def set_weekly(self, email: str, windows: list[tuple[int, int, int]], by: str, now: datetime) -> list[Call]:
        """The recruiter's own week. Returns the booked calls that no longer fit (they are left in place for someone
        to move or release)."""
        self._calendar()
        for weekday, start, end in windows:
            if not (0 <= weekday <= 6 and 0 <= start < end <= 24 * 60):
                raise InputError("window_invalid", "a window needs a weekday and a start before its end")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            country = self._known(db, email)
            db.execute("DELETE FROM availability WHERE email = ?", (email,))
            db.executemany("INSERT INTO availability (email, weekday, start_min, end_min) VALUES (?, ?, ?, ?)",
                           [(email, *w) for w in windows])
            db.execute("INSERT OR IGNORE INTO availability_custom (email) VALUES (?)", (email,))
            self._log(db, by, "availability_changed", email, now)
            return self._apply(db, email, country, now)

    def reset_weekly(self, email: str, by: str, now: datetime) -> list[Call]:
        self._calendar()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            country = self._known(db, email)
            db.execute("DELETE FROM availability WHERE email = ?", (email,))
            db.execute("DELETE FROM availability_custom WHERE email = ?", (email,))
            self._log(db, by, "availability_reset", email, now)
            return self._apply(db, email, country, now)

    def set_day_off(self, email: str, day: date, off: bool, by: str, now: datetime) -> list[Call]:
        self._calendar()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            country = self._known(db, email)
            if off:
                db.execute("INSERT OR IGNORE INTO days_off (email, day) VALUES (?, ?)", (email, day.isoformat()))
            else:
                db.execute("DELETE FROM days_off WHERE email = ? AND day = ?", (email, day.isoformat()))
            self._log(db, by, "day_off" if off else "day_on", f"{email} {day.isoformat()}", now)
            return self._apply(db, email, country, now)

    def sync_availability(self, now: datetime) -> None:
        """Adds the days that have come into the horizon. Cheap when it was already done today."""
        if self.calendar is None:
            return
        today = (now if now.tzinfo else now.astimezone()).date().isoformat()
        with self._connect() as db:
            done = db.execute("SELECT value FROM settings WHERE key = 'availability_synced'").fetchone()
        if done and done[0] == today:
            return
        yesterday = ((now if now.tzinfo else now.astimezone()).date() - timedelta(days=1)).isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM slots WHERE candidate_id IS NULL AND cancelled_at IS NULL AND created_by = ? AND starts_at < ?",
                       (MADE, yesterday))  # free times that have passed: nobody will ever be offered them
            for email, country in db.execute("SELECT email, country FROM recruiters").fetchall():
                self._apply(db, email, country, now)
            db.execute("INSERT INTO settings (key, value) VALUES ('availability_synced', ?) "
                       "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (today,))

    # -- making the rows --------------------------------------------------------------------------------------------

    def _desired(self, db, email: str, country: str, now: datetime) -> set[datetime]:
        cal = self._calendar()
        local = (now if now.tzinfo else now.astimezone()).astimezone(cal.zone(country)).replace(tzinfo=None)
        off = {r[0] for r in db.execute("SELECT day FROM days_off WHERE email = ?", (email,))}
        windows = self._windows(db, email)
        wanted = set()
        for ahead in range(cal.horizon_days):
            day = local.date() + timedelta(days=ahead)
            if day.isoformat() in off:
                continue
            for weekday, start, end in windows:
                if weekday != day.weekday():
                    continue
                for minute in range(start, end - cal.call_minutes + 1, cal.call_minutes):
                    wall = datetime.combine(day, time()) + timedelta(minutes=minute)
                    if wall > local and cal.wall_time_exists(country, wall):
                        wanted.add(wall)
        return wanted

    def _apply(self, db, email: str, country: str, now: datetime) -> list[Call]:
        """Makes the recruiter's rows match their availability. Free rows made from a pattern that no longer fit are
        removed; a booked one that no longer fits is reported and left."""
        wanted = self._desired(db, email, country, now)
        cal = self._calendar()
        local = (now if now.tzinfo else now.astimezone()).astimezone(cal.zone(country)).replace(tzinfo=None)
        have = {}
        for slot_id, starts_at, candidate_id, created_by in db.execute(
                "SELECT id, starts_at, candidate_id, created_by FROM slots WHERE recruiter = ? AND cancelled_at IS NULL "
                "AND starts_at > ?", (email, local.isoformat())):
            have[datetime.fromisoformat(starts_at)] = (slot_id, candidate_id, created_by)
        db.executemany("INSERT OR IGNORE INTO slots (country, starts_at, recruiter, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
                       [(country, t.isoformat(), email, MADE, stamp(now)) for t in sorted(wanted - have.keys())])
        gone, conflicts = [], []
        for starts_at, (slot_id, candidate_id, created_by) in have.items():
            if starts_at in wanted or created_by != MADE:
                continue
            if candidate_id is None:
                gone.append((slot_id,))
            else:
                conflicts.append(Call(slot_id, candidate_id, country, starts_at, email))
        db.executemany("DELETE FROM slots WHERE id = ?", gone)
        return sorted(conflicts, key=lambda c: c.starts_at)

    # -- reading ----------------------------------------------------------------------------------------------------

    def capacity(self, country: str, starts_at: datetime) -> int:
        """How many recruiters are free at that time: how many candidates can still be given it."""
        with self._connect() as db:
            return db.execute("SELECT COUNT(*) FROM slots WHERE country = ? AND starts_at = ? AND candidate_id IS NULL "
                              "AND cancelled_at IS NULL", (country, starts_at.isoformat())).fetchone()[0]

    def free_days(self, country: str, month: date, now: datetime) -> dict[date, int]:
        """The days of `month` that have a free time, each with how many distinct times: what the picker colours."""
        if self.calendar is None:
            return {}
        self.sync_availability(now)
        first = month.replace(day=1)
        after = (first + timedelta(days=32)).replace(day=1)
        with self._connect() as db:
            rows = db.execute("SELECT starts_at FROM slots WHERE country = ? AND candidate_id IS NULL AND cancelled_at IS NULL "
                              "AND starts_at >= ? AND starts_at < ? GROUP BY starts_at",
                              (country, first.isoformat(), after.isoformat())).fetchall()
        days: dict[date, int] = {}
        for (at,) in rows:
            starts = datetime.fromisoformat(at)
            if self.calendar.candidate_may_book(country, starts, now):
                days[starts.date()] = days.get(starts.date(), 0) + 1
        return dict(sorted(days.items()))

    def slot(self, slot_id: int):
        with self._connect() as db:
            row = db.execute("SELECT id, country, starts_at, recruiter, candidate_id, cancelled_at FROM slots WHERE id = ?",
                             (slot_id,)).fetchone()
        return _slot(row) if row else None

    def future_calls(self, email: str, now: datetime) -> list[Call]:
        """The calls this recruiter has booked from now on."""
        with self._connect() as db:
            rows = db.execute("SELECT id, candidate_id, country, starts_at FROM slots WHERE recruiter = ? AND candidate_id "
                              "IS NOT NULL AND cancelled_at IS NULL ORDER BY starts_at", (email,)).fetchall()
        calendar = self._calendar()
        return [Call(i, c, country, datetime.fromisoformat(at), email) for i, c, country, at in rows
                if calendar.recruiter_may_book(country, datetime.fromisoformat(at), now)]

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
                if self.calendar is not None:
                    self._apply(db, email, country, now)  # their default week is on the calendar from this moment
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
                for table in ("availability", "availability_custom", "days_off"):
                    db.execute(f"DELETE FROM {table} WHERE email = ?", (email,))
                db.execute("DELETE FROM slots WHERE recruiter = ? AND candidate_id IS NULL AND cancelled_at IS NULL", (email,))
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
