"""D93: booking a call by voice has no list or button: the candidate says a day, then a time. Plain code reads both, in Spanish
and English, from what a speech reader writes ("el jueves 5", "a las 3 de la tarde", "10 and a half"). Anything it is not
sure of is None, and the agent asks again."""
from datetime import date

from screener.spoken_when import Wish, nearest_day, nearest_time, read_day, read_time
from tests.support.tables import table

TODAY = date(2026, 10, 29)  # a Thursday


@table("text,expected", [
    ("mañana", date(2026, 10, 30)), ("tomorrow", date(2026, 10, 30)), ("pasado mañana", date(2026, 10, 31)),
    ("the day after tomorrow", date(2026, 10, 31)), ("hoy", TODAY), ("today", TODAY),
    ("el viernes", date(2026, 10, 30)), ("Friday", date(2026, 10, 30)), ("el sábado", date(2026, 10, 31)),
    ("el jueves", date(2026, 11, 5)),                       # today is Thursday: the next one
    ("next Monday", date(2026, 11, 2)), ("el lunes que viene", date(2026, 11, 2)),
    ("el 30", date(2026, 10, 30)), ("el 3", date(2026, 11, 3)), ("the 30th", date(2026, 10, 30)),
    ("30 de octubre", date(2026, 10, 30)), ("3 de noviembre", date(2026, 11, 3)), ("October 30", date(2026, 10, 30)),
    ("November 3rd", date(2026, 11, 3)), ("jueves 5 de noviembre", date(2026, 11, 5)),
    ("el 1 de enero", date(2027, 1, 1)), ("1 of January", date(2027, 1, 1)),
    ("mañana por la mañana", date(2026, 10, 30)),           # "in the morning" is not the day
    ("por la mañana", None), ("no sé", None), ("", None), ("a las 10", None), ("in the afternoon", None),
])
def test_a_day_is_read_from_what_was_said(text, expected):
    assert read_day(text, TODAY) == expected


@table("text,expected", [
    ("a las 10", Wish(10, 0)), ("a las 10:30", Wish(10, 30)), ("10 y media", Wish(10, 30)), ("10 y cuarto", Wish(10, 15)),
    ("las 10 menos cuarto", Wish(9, 45)), ("a las 3", Wish(15, 0)), ("3 pm", Wish(15, 0)), ("3:15 p.m.", Wish(15, 15)),
    ("10 de la mañana", Wish(10, 0)), ("3 de la tarde", Wish(15, 0)), ("10 am", Wish(10, 0)), ("at 2", Wish(14, 0)),
    ("ten thirty", Wish(10, 30)), ("half past nine", Wish(9, 30)), ("quarter past 11", Wish(11, 15)),
    ("las diez", Wish(10, 0)), ("a las doce", Wish(12, 0)), ("noon", Wish(12, 0)), ("mediodía", Wish(12, 0)),
    ("9", Wish(9, 0)), ("16:45", Wish(16, 45)), ("4 in the afternoon", Wish(16, 0)),
    ("por la mañana", Wish(period="morning")), ("en la mañana", Wish(period="morning")),
    ("por la tarde", Wish(period="afternoon")), ("in the afternoon", Wish(period="afternoon")),
    ("in the morning", Wish(period="morning")), ("evening", Wish(period="evening")),
    ("no sé", None), ("", None), ("el jueves", None), ("25:00", None),
])
def test_a_time_is_read_from_what_was_said(text, expected):
    assert read_time(text) == expected


@table("days,wanted,expected", [
    ([date(2026, 10, 30), date(2026, 11, 3)], date(2026, 11, 3), date(2026, 11, 3)),            # that very day
    ([date(2026, 10, 30), date(2026, 11, 3)], date(2026, 11, 2), date(2026, 11, 3)),            # one day off beats four
    ([date(2026, 10, 30), date(2026, 11, 3)], date(2026, 10, 31), date(2026, 10, 30)),          # one day either side: the earlier
    ([date(2026, 10, 30), date(2026, 11, 3)], date(2026, 10, 29), date(2026, 10, 30)),          # today: the first day with times
    ([date(2026, 10, 30), date(2026, 11, 3)], date(2026, 12, 25), date(2026, 11, 3)),           # far beyond: the last day
    ([date(2026, 11, 3)], date(2026, 10, 1), date(2026, 11, 3)),
    ([], date(2026, 11, 3), None),
])
def test_the_closest_day_with_times(days, wanted, expected):
    assert nearest_day(days, wanted) == expected


@table("minutes,wish,expected", [
    ([540, 555, 600, 960], Wish(10, 0), 600),               # exactly that time
    ([540, 555, 615, 960], Wish(10, 0), 615),               # 10:00 is gone: 10:15 is 15 away, 9:15 is 45 away
    ([540, 555, 585, 615], Wish(10, 0), 585),               # 9:45 and 10:15 are equally close: the earlier
    ([540, 555], Wish(15, 0), 555),                         # nothing in the afternoon: the last time
    ([540, 555, 960], Wish(period="morning"), 540),         # a period: its earliest time
    ([540, 555, 960, 975], Wish(period="afternoon"), 960),
    ([540, 555], Wish(period="afternoon"), 555),            # none that afternoon: the closest to it
    ([], Wish(10, 0), None),
])
def test_the_closest_time_of_a_day(minutes, wish, expected):
    assert nearest_time(minutes, wish) == expected
