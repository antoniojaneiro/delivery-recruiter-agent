"""D87: the two rules about time, in one place. A candidate books from tomorrow up to four weeks ahead, by the clock of the
call's own country; a recruiter may book any time that has not started. Each rule is the only place its answer comes from."""
from datetime import datetime, timedelta, timezone

from screener.slot_calendar import SlotCalendar
from tests.support.tables import table

CAL = SlotCalendar(timezones={"ES": "Europe/Madrid", "MX": "America/Mexico_City"}, country_of={})
# 04:00 UTC on 27 Oct: already the 27th in Madrid (05:00), still the evening of the 26th in Mexico City (22:00).
NOW = datetime(2026, 10, 27, 4, 0, tzinfo=timezone.utc)


@table("country,wall,allowed", [
    ("ES", datetime(2026, 10, 27, 18, 0), False),   # today in Spain
    ("ES", datetime(2026, 10, 28, 9, 0), True),     # tomorrow in Spain
    ("MX", datetime(2026, 10, 27, 9, 0), True),     # tomorrow in Mexico: its today is still the 26th
    ("MX", datetime(2026, 10, 26, 23, 0), False),   # today in Mexico
    ("ES", datetime(2026, 10, 26, 9, 0), False),    # the past
    ("ES", datetime(2026, 11, 24, 23, 45), True),   # the last day: 28 days from Spain's today
    ("ES", datetime(2026, 11, 25, 9, 0), False),    # one day too far
    ("MX", datetime(2026, 11, 23, 9, 0), True),     # Mexico's today is the 26th, so its last day is a day earlier
    ("MX", datetime(2026, 11, 24, 9, 0), False),
])
def test_a_candidate_books_from_tomorrow_up_to_four_weeks_by_the_calls_own_clock(country, wall, allowed):
    assert CAL.candidate_may_book(country, wall, NOW) is allowed


@table("country,wall,allowed", [
    ("ES", datetime(2026, 10, 27, 5, 1), True),     # a minute from now, today
    ("ES", datetime(2026, 10, 27, 5, 0), True),     # right now
    ("ES", datetime(2026, 10, 27, 4, 59), False),   # a minute ago
    ("MX", datetime(2026, 10, 26, 22, 30), True),
    ("MX", datetime(2026, 10, 26, 21, 59), False),
])
def test_a_recruiter_may_book_any_time_that_has_not_started(country, wall, allowed):
    assert CAL.recruiter_may_book(country, wall, NOW) is allowed


def test_a_naive_now_means_this_machines_clock_like_every_other_store_call():
    local = datetime(2026, 10, 25, 10, 0)
    tomorrow = (local + timedelta(days=1)).replace(hour=9)
    assert CAL.candidate_may_book("ES", tomorrow, local) and CAL.recruiter_may_book("ES", tomorrow, local)


def test_a_client_can_move_the_first_day_candidates_may_book():
    two_days = SlotCalendar(timezones={"GB": "Europe/London"}, country_of={}, book_from_days=2)
    now = datetime(2026, 10, 26, 9, 0, tzinfo=timezone.utc)
    assert not two_days.candidate_may_book("GB", datetime(2026, 10, 27, 12, 0), now)
    assert two_days.candidate_may_book("GB", datetime(2026, 10, 28, 12, 0), now)
