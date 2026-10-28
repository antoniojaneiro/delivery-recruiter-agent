"""D82: call times from recruiters' availability. A mixin of Store; it uses the store's `_connect`.

Each recruiter has a weekly pattern (the client's default, or their own) and days off. Free 15-minute times are made from
it as rows of the `slots` table for the coming weeks, so booking, offers, cancelling and the funnel all use the one atomic
code that already exists, and capacity grows with every recruiter. A one-off time added by hand is never removed here."""
from datetime import date, datetime, time, timedelta

from screener.store_types import AGENT, Call, InputError, stamp

def _slot_from(row):
    from screener.store_slots import _slot
    return _slot(row)


MADE = "availability"  # `created_by` of a row made from a pattern (a hand-added time has a person's name)


class AvailabilityMixin:
    calendar = None

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
        return _slot_from(row) if row else None

    def future_calls(self, email: str, now: datetime) -> list[Call]:
        """The calls this recruiter has booked from now on."""
        with self._connect() as db:
            rows = db.execute("SELECT id, candidate_id, country, starts_at FROM slots WHERE recruiter = ? AND candidate_id "
                              "IS NOT NULL AND cancelled_at IS NULL ORDER BY starts_at", (email,)).fetchall()
        calendar = self._calendar()
        return [Call(i, c, country, datetime.fromisoformat(at), email) for i, c, country, at in rows
                if calendar.recruiter_may_book(country, datetime.fromisoformat(at), now)]
