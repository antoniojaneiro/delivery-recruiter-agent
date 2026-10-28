"""What the calendar page needs, as plain code (D79): the week a day belongs to and the call times that fall in it."""
from datetime import date, timedelta

from screener.store import Slot


def week_start(day: date) -> date:
    """The Monday of the week `day` is in."""
    return day - timedelta(days=day.weekday())


def week_slots(slots: list[Slot], start: date, country: str) -> dict[date, list[Slot]]:
    """The seven days from `start`, each with that country's call times in clock order. A call time's clock is its
    country's own (D8), so two countries are never mixed in one grid."""
    week = {start + timedelta(days=n): [] for n in range(7)}
    for found in slots:
        if found.country == country and found.starts_at.date() in week:
            week[found.starts_at.date()].append(found)
    for found in week.values():
        found.sort(key=lambda s: (s.starts_at, s.id))
    return week
