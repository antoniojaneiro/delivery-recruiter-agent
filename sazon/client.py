"""One client's deployment of the screening engine (D63): what it screens for and where it operates."""
from dataclasses import dataclass
from datetime import timedelta

from sazon.slot_calendar import SlotCalendar
from sazon.spec import ScreeningSpec


class ClientError(ValueError):
    """A client that cannot keep its promises. The message lists every problem found."""


@dataclass(frozen=True)
class Client:
    spec: ScreeningSpec
    areas: dict[str, list[str]]  # service area -> nearby places that count as the same area
    calendar: SlotCalendar | None = None  # None: this client does not book calls
    remind_after: timedelta = timedelta(hours=24)  # silence before the one reminder, and again before STALLED

    def __post_init__(self):
        problems = []
        books_calls = self.spec.pack.slots is not None
        if books_calls and self.calendar is None:
            problems.append("the pack has call texts but the client has no calendar, so no call could be offered")
        if self.calendar is not None and not books_calls:
            problems.append("the client has a calendar but the pack has no call texts")
        if self.calendar is not None:
            for area in self.areas:
                if area not in self.calendar.country_of:
                    problems.append(f"service area '{area}' has no country in the calendar")
            for country in dict.fromkeys(self.calendar.country_of.values()):
                if country not in self.calendar.timezones:
                    problems.append(f"country {country} has no time zone")
        if problems:
            raise ClientError("; ".join(problems))
