"""Time rules for call slots (D48, D63). A slot is a wall-clock time in its country's own zone, so a
candidate in that country sees exactly the time the recruiter typed and no conversion is needed.
The only conversions are the two rules about when a slot may be booked (D87)."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class SlotCalendar:
    timezones: dict[str, str]  # country code -> time zone name
    country_of: dict[str, str]  # service area -> country code
    book_from_days: int = 1  # the nearest day a candidate can book, counted from the call's country today: 1 is tomorrow
    offer_size: int = 3  # how many free times a qualified candidate is offered
    call_minutes: int = 15  # one call; a recruiter takes one at a time
    horizon_days: int = 28  # the farthest day a candidate can book, and how far ahead recruiters' times are made
    default_days: tuple[int, ...] = (0, 1, 2, 3, 4)  # a recruiter who never changed their week works these weekdays...
    default_start: int = 9 * 60  # ...from this minute of the day...
    default_end: int = 17 * 60  # ...to this one, in their country's clock

    def zone(self, country: str) -> ZoneInfo:
        return ZoneInfo(self.timezones[country])

    def wall_time_exists(self, country: str, wall: datetime) -> bool:
        """False for a time skipped when the clocks spring forward (a time inside the spring-forward gap)."""
        aware = wall.replace(tzinfo=self.zone(country))
        return aware.astimezone(timezone.utc).astimezone(self.zone(country)).replace(tzinfo=None) == wall

    def today(self, country: str, now: datetime) -> date:
        """The calendar day it is in `country`."""
        return self._now(now).astimezone(self.zone(country)).date()

    def candidate_may_book(self, country: str, wall: datetime, now: datetime) -> bool:
        """A candidate books from tomorrow up to `horizon_days` ahead, counted by the country's own calendar day."""
        today = self._now(now).astimezone(self.zone(country)).date()
        return today + timedelta(days=self.book_from_days) <= wall.date() <= today + timedelta(days=self.horizon_days)

    def recruiter_may_book(self, country: str, wall: datetime, now: datetime) -> bool:
        """A recruiter may book any time that has not started; it is also what the calendar lists."""
        return wall.replace(tzinfo=self.zone(country)) >= self._now(now)

    @staticmethod
    def _now(now: datetime) -> datetime:
        """`now` may be aware, or naive meaning this machine's local time."""
        return now if now.tzinfo else now.astimezone()
