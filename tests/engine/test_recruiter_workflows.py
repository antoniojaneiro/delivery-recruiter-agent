"""D88: what a recruiter does that touches several things (leave, change a week or a day off, make a time while booking)
is one call into the engine, not a string of store calls in a page. It can be repeated after a failure part-way, and a
refused booking leaves nothing behind."""
from datetime import date, datetime

import pytest

from sazon import config
from sazon.client import SAZON_CALENDAR
from screener import slot_flow
from screener.store import InputError, Store
from screener.model import RecruiterStatus as S
from tests.support.booking import NOW, NOW_AWARE, hire, qualify
from tests.support.clients import client_for

CLIENT = client_for(config.AREAS)
MONDAY = date(2026, 10, 26)
BOSS = "boss@sazon.test"
ANA = "ana@sazon.test"


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "s.db", calendar=SAZON_CALENDAR)


def book(store, cid, minute=0):
    qualify(store, cid)
    slot = next(s for s in store.free_slots_on("ES", MONDAY, NOW_AWARE) if s.starts_at.minute == minute)
    return store.book_slot(slot.id, cid, NOW_AWARE)


def owners(store):
    return {s.candidate_id: s.recruiter for s in store.slots(NOW_AWARE) if s.candidate_id}


def test_leaving_moves_calls_to_the_others_when_they_are_free_and_releases_the_rest(store):
    hire(store, "Ana", "Luis")
    book(store, "c1")  # one of them has 09:00 ...
    book(store, "c2")  # ... and the other one the second 09:00 call: both are busy then
    leaving = owners(store)["c1"]
    result = slot_flow.remove_recruiter(store, CLIENT, leaving, BOSS, NOW)
    assert (result.moved, result.released) == (0, 1)  # the other recruiter is busy at 09:00, so that call is released
    assert store.get_recruiter(leaving) is None and leaving not in owners(store).values()
    assert store.booking_of("c1") is None and store.booking_of("c2") is not None


def test_a_leaving_recruiters_call_goes_to_a_free_colleague(store):
    hire(store, "Ana", "Luis")
    book(store, "c1")
    leaving = owners(store)["c1"]
    result = slot_flow.remove_recruiter(store, CLIENT, leaving, BOSS, NOW)
    assert (result.moved, result.released) == (1, 0) and owners(store)["c1"] != leaving


def test_leaving_can_be_run_again_after_a_failure_part_way_and_finishes_the_rest(store, monkeypatch):
    hire(store, "Ana")
    book(store, "c1")
    book(store, "c2", 15)
    real = slot_flow.notify_cancelled
    calls = []

    def flaky(*args, **kwargs):
        calls.append(args[2])
        if len(calls) == 1:
            raise RuntimeError("the database was busy")
        return real(*args, **kwargs)

    monkeypatch.setattr(slot_flow, "notify_cancelled", flaky)
    with pytest.raises(RuntimeError):
        slot_flow.remove_recruiter(store, CLIENT, ANA, BOSS, NOW)
    assert store.get_recruiter(ANA) is None  # the account is gone, so nobody can book their times again
    slot_flow.remove_recruiter(store, CLIENT, ANA, BOSS, NOW)  # the same call again finishes what is left
    assert store.booking_of("c1") is None and store.booking_of("c2") is None
    assert store.future_calls(ANA, NOW_AWARE) == []


def test_an_unknown_recruiter_with_no_calls_is_not_found(store):
    with pytest.raises(LookupError):
        slot_flow.remove_recruiter(store, CLIENT, "nobody@sazon.test", BOSS, NOW)


def test_a_day_off_or_a_new_week_deals_with_the_calls_that_no_longer_fit(store):
    hire(store, "Ana", "Luis")
    book(store, "c1")
    leaving = owners(store)["c1"]
    assert slot_flow.set_day_off(store, CLIENT, leaving, MONDAY, True, BOSS, NOW).moved == 1
    assert owners(store)["c1"] != leaving
    other = owners(store)["c1"]
    assert slot_flow.save_week(store, CLIENT, other, [(1, 9 * 60, 17 * 60)], BOSS, NOW).released == 1  # no Monday any more
    assert store.booking_of("c1") is None
    assert slot_flow.reset_week(store, CLIENT, other, BOSS, NOW).released == 0


def test_a_new_time_made_while_booking_is_the_owners_and_booked_for_the_candidate(store):
    hire(store, "Ana")
    qualify(store, "c1")
    done = slot_flow.schedule_new_time(store, CLIENT, "c1", "ES", datetime(2026, 10, 30, 18, 0), ANA, BOSS, NOW)
    assert done.booking.starts_at == datetime(2026, 10, 30, 18, 0) and owners(store)["c1"] == ANA


def test_a_refused_booking_leaves_the_new_time_behind_nowhere(store):
    hire(store, "Ana")
    qualify(store, "c1")
    store.set_status("c1", S.REJECTED, BOSS, NOW)
    before = len(store.slots(NOW_AWARE))
    with pytest.raises(InputError):
        slot_flow.schedule_new_time(store, CLIENT, "c1", "ES", datetime(2026, 10, 30, 18, 0), ANA, BOSS, NOW)
    assert len(store.slots(NOW_AWARE)) == before


def test_a_new_time_nobody_ends_up_using_is_cancelled_again(store):
    hire(store, "Ana", "Luis")
    qualify(store, "c0")
    store.book_slot(store.free_slots_on("ES", date(2026, 10, 30), NOW_AWARE)[0].id, "c0", NOW_AWARE)  # Ana has a call that day
    store.add_slot("ES", datetime(2026, 10, 30, 18, 0), "luis@sazon.test", BOSS, NOW_AWARE)  # Luis is free at 18:00
    qualify(store, "c1")
    slot_flow.schedule_new_time(store, CLIENT, "c1", "ES", datetime(2026, 10, 30, 18, 0), ANA, BOSS, NOW)
    assert owners(store)["c1"] == "luis@sazon.test"  # the least busy recruiter takes it
    ana_new = [s for s in store.slots(NOW_AWARE, include_cancelled=True) if s.recruiter == ANA and s.starts_at.hour == 18]
    assert len(ana_new) == 1 and ana_new[0].cancelled and ana_new[0].candidate_id is None
