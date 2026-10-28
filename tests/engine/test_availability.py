"""D82: call times come from recruiters' availability. Each recruiter has a weekly pattern (default: Monday to Friday, 9:00 to
17:00 in their country's clock) with days off; free 15-minute times are made from it for the coming weeks, so the more
recruiters there are, the more people can be offered the same time. Booking gives the call to the least busy recruiter."""
import threading
from datetime import date, datetime, timedelta

import pytest

from sazon.client import SAZON_CALENDAR
from screener.store import InputError, Store

NOW = datetime(2026, 11, 2, 8, 0)  # a Monday
MONDAY = date(2026, 11, 9)
SATURDAY = date(2026, 11, 14)
BOSS = "boss@sazon.test"


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "s.db", calendar=SAZON_CALENDAR)


def hire(store, name, country="ES", password="contraseña-segura-1"):
    return store.add_recruiter(f"{name.lower()}@sazon.test", name, country, password, BOSS, NOW)


def times(store, day, country="ES", now=NOW):
    return [s.starts_at for s in store.free_slots_on(country, day, now.astimezone())]


def clock(*slots):
    return [f"{t:%H:%M}" for t in slots]


# --- the default and the horizon ----------------------------------------------------------------------------------

def test_a_new_recruiter_is_available_monday_to_friday_nine_to_five_in_fifteen_minute_calls(store):
    hire(store, "Ana")
    day = times(store, MONDAY)
    assert clock(*day)[0] == "09:00" and clock(*day)[-1] == "16:45" and len(day) == 32
    assert times(store, SATURDAY) == [] and times(store, SATURDAY + timedelta(days=1)) == []


def test_times_are_made_for_four_weeks_ahead_and_not_beyond(store):
    hire(store, "Ana")
    assert times(store, NOW.date() + timedelta(days=25)) and times(store, NOW.date() + timedelta(days=29)) == []  # Friday the 27th; Tuesday Dec 1st
    assert len(times(store, NOW.date() + timedelta(days=28))) == 32  # Monday Nov 30: the last day a candidate may book


def test_two_recruiters_make_one_option_with_two_calls_of_capacity(store):
    hire(store, "Ana")
    hire(store, "Luis")
    ten = datetime.combine(MONDAY, datetime.min.time()).replace(hour=10)
    assert len(times(store, MONDAY)) == 32 and store.capacity("ES", ten) == 2


def test_a_recruiters_times_are_in_their_countrys_clock_and_never_mix_with_another_countrys(store):
    hire(store, "Ana", "ES")
    hire(store, "Marta", "MX")
    assert len(times(store, MONDAY, "ES")) == 32 and len(times(store, MONDAY, "MX")) == 32
    assert {s.country for s in store.slots(NOW.astimezone(), include_past=True)} == {"ES", "MX"}


def test_a_day_that_has_come_is_added_when_the_clock_moves_on_and_nothing_is_made_twice(store):
    hire(store, "Ana")
    later = NOW + timedelta(days=3)
    store.sync_availability(later.astimezone())
    store.sync_availability(later.astimezone())  # the second pass changes nothing
    rows = store.slots(later.astimezone(), include_past=True)
    assert len(times(store, later.date() + timedelta(days=25), now=later)) == 32
    assert len(rows) == len({(s.country, s.starts_at, s.recruiter) for s in rows})


def test_two_processes_syncing_at_the_same_moment_make_no_duplicates(store):
    hire(store, "Ana")
    later = (NOW + timedelta(days=2)).astimezone()
    threads = [threading.Thread(target=store.sync_availability, args=(later,)) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    rows = store.slots(later, include_past=True)
    assert len(rows) == len({(s.country, s.starts_at) for s in rows})


def test_a_time_inside_the_spring_forward_gap_is_not_made(store):
    hire(store, "Ana")
    sunday = date(2027, 3, 28)  # clocks go 02:00 to 03:00 in Spain
    store.set_weekly("ana@sazon.test", [(6, 60, 300)], BOSS, datetime(2027, 3, 20, 8, 0))
    found = clock(*times(store, sunday, now=datetime(2027, 3, 20, 8, 0)))
    assert "01:45" in found and "03:00" in found and not [t for t in found if t.startswith("02:")]


# --- changing availability --------------------------------------------------------------------------------------------

def test_a_recruiter_who_changes_their_week_gets_exactly_those_hours(store):
    hire(store, "Ana")
    conflicts = store.set_weekly("ana@sazon.test", [(1, 14 * 60, 16 * 60)], BOSS, NOW)
    assert conflicts == [] and store.is_custom("ana@sazon.test")
    assert clock(*times(store, MONDAY)) == [] and clock(*times(store, MONDAY + timedelta(days=1)))[:1] == ["14:00"]
    assert len(times(store, MONDAY + timedelta(days=1))) == 8


def test_going_back_to_the_default_restores_monday_to_friday(store):
    hire(store, "Ana")
    store.set_weekly("ana@sazon.test", [], BOSS, NOW)
    assert times(store, MONDAY) == []
    store.reset_weekly("ana@sazon.test", BOSS, NOW)
    assert not store.is_custom("ana@sazon.test") and len(times(store, MONDAY)) == 32


def test_a_day_off_removes_that_days_times_and_taking_it_back_restores_them(store):
    hire(store, "Ana")
    store.set_day_off("ana@sazon.test", MONDAY, True, BOSS, NOW)
    assert times(store, MONDAY) == [] and store.days_off("ana@sazon.test") == [MONDAY]
    store.set_day_off("ana@sazon.test", MONDAY, False, BOSS, NOW)
    assert len(times(store, MONDAY)) == 32 and store.days_off("ana@sazon.test") == []


def test_a_one_off_extra_time_is_added_for_a_recruiter_on_a_day_they_do_not_work(store):
    hire(store, "Ana")
    slot_id = store.add_slot("ES", datetime.combine(SATURDAY, datetime.min.time()).replace(hour=10), "ana@sazon.test",
                             BOSS, NOW.astimezone())
    assert [s.starts_at.hour for s in store.free_slots_on("ES", SATURDAY, NOW.astimezone())] == [10] and slot_id


def test_a_change_that_removes_a_booked_time_reports_the_call_and_leaves_it_alone(store):
    hire(store, "Ana")
    store.commit_turn("c1", NOW, {}, {"name": "Juan Pérez", "city": "Madrid"}, "QUALIFIED", [], [])
    first = store.free_slots_on("ES", MONDAY, NOW.astimezone())[4]
    booking = store.book_slot(first.id, "c1", NOW.astimezone())
    conflicts = store.set_day_off("ana@sazon.test", MONDAY, True, BOSS, NOW)
    assert [(c.candidate_id, c.starts_at) for c in conflicts] == [("c1", booking.starts_at)]
    assert store.booking_of("c1") is not None  # not touched until someone resolves it


def test_a_recruiter_who_leaves_loses_their_free_times_and_their_booked_calls_are_reported(store):
    hire(store, "Ana")
    hire(store, "Luis")
    store.commit_turn("c1", NOW, {}, {"name": "Juan Pérez", "city": "Madrid"}, "QUALIFIED", [], [])
    ana_slot = next(s for s in store.free_slots_on("ES", MONDAY, NOW.astimezone()))
    store.book_slot(ana_slot.id, "c1", NOW.astimezone())
    owner = next(s.recruiter for s in store.slots(NOW.astimezone()) if s.candidate_id == "c1")
    calls = store.future_calls(owner, NOW.astimezone())
    assert [c.candidate_id for c in calls] == ["c1"]
    other = "luis@sazon.test" if owner == "ana@sazon.test" else "ana@sazon.test"
    store.remove_recruiter(owner, BOSS, NOW)
    assert store.get_recruiter(owner) is None and len(times(store, MONDAY)) == 32  # the other one still covers every time
    assert store.capacity("ES", ana_slot.starts_at) == 1 and other


def test_a_day_off_with_a_wrong_recruiter_or_no_calendar_is_refused(store, tmp_path):
    with pytest.raises(LookupError):
        store.set_day_off("nobody@sazon.test", MONDAY, True, BOSS, NOW)
    bare = Store(tmp_path / "bare.db")
    with pytest.raises(InputError):
        bare.set_weekly("x@y.test", [], BOSS, NOW)


# --- booking: the least busy recruiter gets the call ----------------------------------------------------------------------

def candidates(store, count):
    for n in range(count):
        store.commit_turn(f"c{n}", NOW, {}, {"name": f"Persona {n}", "city": "Madrid"}, "QUALIFIED", [], [])


def owner_of(store, candidate):
    return next(s.recruiter for s in store.slots(NOW.astimezone()) if s.candidate_id == candidate)


def test_the_call_goes_to_the_recruiter_with_fewer_calls_that_day_and_then_alphabetically(store):
    hire(store, "Ana")
    hire(store, "Luis")
    candidates(store, 4)
    ten = next(s for s in store.free_slots_on("ES", MONDAY, NOW.astimezone()) if s.starts_at.hour == 10 and s.starts_at.minute == 0)
    nine = next(s for s in store.free_slots_on("ES", MONDAY, NOW.astimezone()) if s.starts_at.hour == 9 and s.starts_at.minute == 0)
    store.book_slot(nine.id, "c0", NOW.astimezone())
    assert owner_of(store, "c0") == "ana@sazon.test"  # nobody had calls: alphabetical
    store.book_slot(ten.id, "c1", NOW.astimezone())
    assert owner_of(store, "c1") == "luis@sazon.test"  # Ana already has one that day
    store.book_slot(ten.id, "c2", NOW.astimezone())
    assert owner_of(store, "c2") == "ana@sazon.test" and store.capacity("ES", ten.starts_at) == 0


def test_a_time_with_no_capacity_left_is_no_longer_offered_and_booking_it_fails(store):
    hire(store, "Ana")
    candidates(store, 2)
    ten = next(s for s in store.free_slots_on("ES", MONDAY, NOW.astimezone()) if s.starts_at.hour == 10 and s.starts_at.minute == 0)
    assert store.book_slot(ten.id, "c0", NOW.astimezone()) is not None
    assert ten.starts_at not in times(store, MONDAY) and store.book_slot(ten.id, "c1", NOW.astimezone()) is None


def test_the_row_offered_may_be_taken_by_another_candidate_and_a_free_recruiter_at_that_time_serves_the_next(store):
    hire(store, "Ana")
    hire(store, "Luis")
    candidates(store, 2)
    ten = next(s for s in store.free_slots_on("ES", MONDAY, NOW.astimezone()) if s.starts_at.hour == 10 and s.starts_at.minute == 0)
    assert store.book_slot(ten.id, "c0", NOW.astimezone()) and store.book_slot(ten.id, "c1", NOW.astimezone())
    assert {owner_of(store, "c0"), owner_of(store, "c1")} == {"ana@sazon.test", "luis@sazon.test"}


# --- what the calendar page reads ---------------------------------------------------------------------------------------

def test_the_calendar_reads_only_the_booked_calls_of_a_week_and_never_every_free_time(store):
    hire(store, "Ana")
    hire(store, "Luis")
    candidates(store, 2)
    first = store.free_slots_on("ES", MONDAY, NOW.astimezone())[0]
    store.book_slot(first.id, "c0", NOW.astimezone())
    store.book_slot(first.id, "c1", NOW.astimezone())
    week = store.booked_slots("ES", MONDAY, MONDAY + timedelta(days=7))
    assert sorted(s.candidate_id for s in week) == ["c0", "c1"] and {s.recruiter for s in week} == {"ana@sazon.test", "luis@sazon.test"}
    assert store.booked_slots("MX", MONDAY, MONDAY + timedelta(days=7)) == []
    assert store.booked_slots("ES", MONDAY + timedelta(days=7), MONDAY + timedelta(days=14)) == []


def test_the_list_holds_booked_calls_and_hand_made_times_not_the_thousands_made_from_availability(store):
    hire(store, "Ana")
    candidates(store, 1)
    store.add_slot("ES", datetime.combine(SATURDAY, datetime.min.time()).replace(hour=10), "ana@sazon.test", BOSS, NOW.astimezone())
    store.book_slot(store.free_slots_on("ES", MONDAY, NOW.astimezone())[0].id, "c0", NOW.astimezone())
    listed = store.listed_slots(NOW.astimezone())
    assert len(store.slots(NOW.astimezone())) > 500 and len(listed) == 2


def test_free_times_that_have_passed_are_cleaned_up_each_day_and_offers_never_look_at_the_past(store):
    hire(store, "Ana")
    later = NOW + timedelta(days=30)
    store.sync_availability(later.astimezone())
    free = [s for s in store.slots(later.astimezone(), include_past=True) if s.candidate_id is None]
    assert free and min(s.starts_at for s in free) >= datetime.combine(later.date() - timedelta(days=1), datetime.min.time())
    assert store.free_slots("ES", later.astimezone(), 3)[0].starts_at > later  # the first offer is in the future
    assert len(store.slots(later.astimezone(), include_past=True)) < 2000  # not a month of old rows kept forever


def test_a_time_added_by_hand_for_a_recruiter_must_be_in_that_recruiters_own_country(store):
    hire(store, "Ana", "ES")
    when = datetime.combine(SATURDAY, datetime.min.time()).replace(hour=10)
    with pytest.raises(InputError) as refused:
        store.add_slot("MX", when, "ana@sazon.test", BOSS, NOW.astimezone())
    assert refused.value.code == "wrong_country"
    assert store.add_slot("ES", when, "ana@sazon.test", BOSS, NOW.astimezone()) > 0


def test_the_list_can_be_limited_to_one_country_and_one_week_in_the_database(store):
    hire(store, "Ana", "ES")
    hire(store, "Marta", "MX")
    candidates(store, 3)
    for cid, country, day in (("c0", "ES", MONDAY), ("c1", "ES", MONDAY + timedelta(days=7)), ("c2", "MX", MONDAY)):
        store.book_slot(store.free_slots_on(country, day, NOW.astimezone())[0].id, cid, NOW.astimezone())
    week = lambda country, first: [s.candidate_id for s in store.listed_slots(NOW.astimezone(), country, first, first + timedelta(days=7))]
    assert week("ES", MONDAY) == ["c0"] and week("ES", MONDAY + timedelta(days=7)) == ["c1"] and week("MX", MONDAY) == ["c2"]
    assert sorted(s.candidate_id for s in store.listed_slots(NOW.astimezone())) == ["c0", "c1", "c2"]
