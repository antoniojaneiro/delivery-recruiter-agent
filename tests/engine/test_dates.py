"""D94: the two small date calculations the engine used to repeat in several places."""
from datetime import date, time

from screener.dates import minutes_of_day, next_weekday
from tests.support.tables import table

THURSDAY = date(2026, 10, 29)


@table("weekday,expected", [
    (4, date(2026, 10, 30)),   # Friday: tomorrow
    (0, date(2026, 11, 2)),    # Monday: next week
    (3, date(2026, 11, 5)),    # Thursday again: a week on, never today
    (6, date(2026, 11, 1)),
])
def test_the_next_weekday_is_always_after_today(weekday, expected):
    assert next_weekday(THURSDAY, weekday) == expected


@table("moment,minutes", [(time(0, 0), 0), (time(9, 15), 555), (time(23, 59), 1439)])
def test_minutes_of_day_counts_from_midnight(moment, minutes):
    assert minutes_of_day(moment) == minutes
