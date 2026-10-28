"""D48: call slots. The slots table is the single source of truth for a booking."""
from datetime import datetime, timezone

import pytest

from tests.support.tables import table

from sazon.client import SAZON_CALENDAR
from sazon import config
from screener.call_times import CallTimes
from screener.store import Store

# An aware "now" keeps these tests independent of the machine's time zone.
NOW = datetime(2026, 10, 26, 8, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 11, 20, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "sazon.db", calendar=SAZON_CALENDAR)


def add(store, country="ES", when=datetime(2026, 11, 3, 10, 0), recruiter="Ana"):
    return store.add_slot(country, when, recruiter, "Ana", NOW)


def starts(slots):
    return [s.starts_at for s in slots]


def test_every_service_area_belongs_to_a_country_with_a_known_time_zone():
    from zoneinfo import ZoneInfo
    for city in config.AREAS:
        assert SAZON_CALENDAR.country_of[city] in SAZON_CALENDAR.timezones
    for zone in SAZON_CALENDAR.timezones.values():
        ZoneInfo(zone)


def test_a_new_slot_is_free_and_listed_in_time_order(store):
    add(store, when=datetime(2026, 11, 5, 9, 0))
    add(store, when=datetime(2026, 11, 3, 10, 0))
    free = store.free_slots("ES", NOW)
    assert starts(free) == [datetime(2026, 11, 3, 10, 0), datetime(2026, 11, 5, 9, 0)]
    assert free[0].recruiter == "Ana" and free[0].country == "ES" and free[0].candidate_id is None


def test_only_slots_of_the_candidates_country_are_offered(store):
    add(store, "ES")
    add(store, "MX", datetime(2026, 11, 4, 9, 0))
    assert [s.country for s in store.free_slots("MX", NOW)] == ["MX"]
    assert [s.country for s in store.free_slots("ES", NOW)] == ["ES"]


def test_the_number_offered_is_limited(store):
    for day in range(3, 9):
        add(store, when=datetime(2026, 11, day, 10, 0))
    assert len(store.free_slots("ES", NOW, limit=3)) == 3


@table("country,when", [
    ("ES", datetime(2026, 10, 1, 10, 0)),            # in the past
    ("ES", datetime(2026, 10, 26, 8, 59)),           # a minute ago: 09:00 Madrid is 08:00 UTC
    ("XX", datetime(2026, 11, 3, 10, 0)),            # unknown country
    ("ES", datetime(2027, 3, 28, 2, 30)),            # does not exist: Spain springs forward 02:00 -> 03:00
])
def test_impossible_or_past_slots_are_refused(store, country, when):
    with pytest.raises(ValueError):
        store.add_slot(country, when, "Ana", "Ana", NOW)
    assert store.free_slots("ES", NOW) == [] and store.free_slots("MX", NOW) == []


def test_a_wall_time_that_exists_in_one_country_may_not_exist_in_the_other(store):
    assert add(store, "MX", datetime(2027, 3, 28, 2, 30))  # Mexico has no clock change


def test_a_time_that_has_not_started_may_be_added_today_by_the_clock_of_its_own_country(store):
    # 09:30 Mexico City is 15:30 UTC: after NOW (08:00 UTC); 09:30 Madrid on the same day is 08:30 UTC, also after it.
    assert add(store, "MX", datetime(2026, 10, 26, 9, 30), "Marta") and add(store, "ES", datetime(2026, 10, 26, 9, 30))
    later = datetime(2026, 10, 26, 8, 45, tzinfo=timezone.utc)  # 09:45 in Madrid, 02:45 in Mexico City
    with pytest.raises(ValueError):
        store.add_slot("ES", datetime(2026, 10, 26, 9, 30), "Luis", "Ana", later)
    assert store.add_slot("MX", datetime(2026, 10, 26, 9, 30), "Pepe", "Ana", later)


def test_candidates_are_offered_times_from_tomorrow_to_four_weeks_and_a_recruiter_may_still_book_today(store):
    today, tomorrow, last, too_far = (add(store, when=datetime(2026, *day, 10, 0), recruiter=f"r{n}")
                                      for n, day in enumerate([(10, 26), (10, 27), (11, 23), (11, 24)]))
    for cid in ("c1", "c2"):
        store.commit_turn(cid, datetime(2026, 10, 26, 9, 0), {}, {}, "QUALIFIED", [], [])
    assert starts(store.free_slots("ES", NOW, limit=10)) == [datetime(2026, 10, 27, 10, 0), datetime(2026, 11, 23, 10, 0)]
    assert store.book_slot(today, "c1", NOW) is None and store.book_slot(too_far, "c1", NOW) is None
    assert store.move_booking("c1", today, "Ana", NOW)[0].slot_id == today  # a recruiter can book it
    assert store.book_slot(last, "c2", NOW).slot_id == last


def test_a_slot_needs_a_creator(store):
    with pytest.raises(ValueError):
        store.add_slot("ES", datetime(2026, 11, 3, 10, 0), None, "  ", NOW)


def test_booking_takes_the_slot_out_of_the_free_list_and_is_recorded(store):
    slot_id = add(store)
    booking = store.book_slot(slot_id, "c1", NOW)
    assert (booking.slot_id, booking.country, booking.starts_at) == (slot_id, "ES", datetime(2026, 11, 3, 10, 0))
    assert store.free_slots("ES", NOW) == []
    assert store.booking_of("c1").slot_id == slot_id
    event = [e for e in store.events("c1") if e.type == "slot_booked"][0]
    assert event.actor == "agent" and "2026-11-03T10:00" in event.detail


def test_a_slot_taken_by_someone_else_cannot_be_booked(store):
    slot_id = add(store)
    store.book_slot(slot_id, "c1", NOW)
    assert store.book_slot(slot_id, "c2", NOW) is None
    assert store.booking_of("c2") is None


def test_a_candidate_never_holds_two_bookings_and_retrying_is_harmless(store):
    first, second = add(store), add(store, when=datetime(2026, 11, 4, 10, 0))
    booked = store.book_slot(first, "c1", NOW)
    again = store.book_slot(first, "c1", NOW)
    other = store.book_slot(second, "c1", NOW)
    assert booked.slot_id == again.slot_id == other.slot_id == first
    assert [s.starts_at for s in store.free_slots("ES", NOW)] == [datetime(2026, 11, 4, 10, 0)]
    assert len([e for e in store.events("c1") if e.type == "slot_booked"]) == 1


def test_a_slot_on_the_same_day_cannot_be_booked_by_a_candidate(store):
    slot_id = add(store)
    assert store.book_slot(slot_id, "c1", datetime(2026, 11, 3, 8, 30, tzinfo=timezone.utc)) is None
    assert store.free_slots("ES", datetime(2026, 11, 3, 8, 30, tzinfo=timezone.utc)) == []


def test_cancelling_a_free_slot_removes_it_and_it_cannot_be_booked(store):
    slot_id = add(store)
    assert store.cancel_slot(slot_id, "Ana", NOW) is None
    assert store.free_slots("ES", NOW) == [] and store.book_slot(slot_id, "c1", NOW) is None


def test_cancelling_a_booked_slot_frees_the_candidate_and_logs_it(store):
    slot_id = add(store)
    store.book_slot(slot_id, "c1", NOW)
    assert store.cancel_slot(slot_id, "Ana", NOW) == "c1"
    assert store.booking_of("c1") is None
    event = [e for e in store.events("c1") if e.type == "slot_cancelled"][0]
    assert event.actor == "recruiter:Ana"
    again = add(store, when=datetime(2026, 11, 4, 10, 0))
    assert store.book_slot(again, "c1", NOW).slot_id == again


def test_the_slot_list_shows_who_booked_each_slot(store):
    booked, free = add(store), add(store, when=datetime(2026, 11, 4, 10, 0))
    store.book_slot(booked, "c1", NOW)
    listed = {s.id: s for s in store.slots(NOW)}
    assert listed[booked].candidate_id == "c1" and listed[free].candidate_id is None


def test_the_slot_list_hides_past_and_cancelled_slots_unless_asked(store):
    old = add(store)
    cancelled = add(store, when=datetime(2026, 11, 4, 10, 0))
    store.cancel_slot(cancelled, "Ana", NOW)
    assert [s.id for s in store.slots(NOW)] == [old]
    assert [s.id for s in store.slots(LATER)] == []
    assert {s.id for s in store.slots(LATER, include_past=True)} == {old}
    assert {s.id for s in store.slots(NOW, include_cancelled=True)} == {old, cancelled}


def test_a_candidates_record_carries_their_live_booking(store):
    store.commit_turn("c1", NOW, {}, {}, "QUALIFIED", [], [])
    slot_id = add(store)
    assert store.get("c1").booking is None
    store.book_slot(slot_id, "c1", NOW)
    assert store.get("c1").booking.slot_id == slot_id
    assert [r.booking.slot_id for r in store.list_candidates()] == [slot_id]
    store.cancel_slot(slot_id, "Ana", NOW)
    assert store.get("c1").booking is None


def test_two_slots_at_the_same_time_count_as_one_option_but_both_stay_bookable(store):
    first, second = add(store), add(store, recruiter="Luis")
    assert [s.id for s in store.free_slots("ES", NOW)] == [first]
    store.book_slot(first, "c1", NOW)
    assert [s.id for s in store.free_slots("ES", NOW)] == [second]


def test_a_booking_race_for_the_same_candidate_returns_the_existing_booking_instead_of_failing(store, monkeypatch):
    first, second = add(store), add(store, when=datetime(2026, 11, 4, 10, 0))
    held = store.book_slot(first, "c1", NOW)
    # Another process booked for c1 between our check and our update: our check sees nothing.
    monkeypatch.setattr(CallTimes, "_held_booking", lambda self, db, candidate_id: None)
    again = store.book_slot(second, "c1", NOW)
    assert again.slot_id == held.slot_id and store.booking_of("c1").slot_id == held.slot_id
