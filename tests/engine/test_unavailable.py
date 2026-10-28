"""D84: a recruiter who becomes unavailable (a day off, a new week, leaving) while holding booked calls. Each call goes to
another recruiter free at the same time, if there is one, and the candidate hears nothing. If there is none, the call is
released, the candidate is told in a fixed text and their free times come back so they can pick again."""
from datetime import date, datetime

import pytest

from sazon import config
from sazon.client import SAZON_CALENDAR
from screener import reminders, slot_flow
from screener.store import Store
from tests.support.booking import NOW, NOW_AWARE, qualify, say
from tests.support.clients import client_for

CLIENT = client_for(config.AREAS)
MONDAY = date(2026, 10, 26)
BOSS = "boss@sazon.test"


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "s.db", calendar=SAZON_CALENDAR)


def hire(store, *names):
    for name in names:
        store.add_recruiter(f"{name.lower()}@sazon.test", name, "ES", "contraseña-segura-1", BOSS, NOW)


def book_nine(store, cid="c1"):
    qualify(store, cid)
    first = store.free_slots_on("ES", MONDAY, NOW_AWARE)[0]
    return store.book_slot(first.id, cid, NOW_AWARE)


def owner(store, cid):
    return next(s.recruiter for s in store.slots(NOW_AWARE) if s.candidate_id == cid)


def test_a_call_goes_to_another_recruiter_free_at_the_same_time_and_the_candidate_hears_nothing(store):
    hire(store, "Ana", "Luis")
    held = book_nine(store)
    leaving = owner(store, "c1")
    conflicts = store.set_day_off(leaving, MONDAY, True, BOSS, NOW)
    result = slot_flow.resolve_calls(store, CLIENT, conflicts, BOSS, NOW)
    assert (result.moved, result.released) == (1, 0)
    assert store.booking_of("c1").starts_at == held.starts_at and owner(store, "c1") != leaving
    assert store.outbox_pending("c1") == []


def test_with_nobody_else_free_the_call_is_released_the_candidate_is_told_and_the_times_come_back(store):
    hire(store, "Ana")
    book_nine(store)
    conflicts = store.set_day_off("ana@sazon.test", MONDAY, True, BOSS, NOW)
    result = slot_flow.resolve_calls(store, CLIENT, conflicts, BOSS, NOW)
    assert (result.moved, result.released) == (0, 1) and store.booking_of("c1") is None
    told = store.outbox_pending("c1")[0].text
    assert "ya no está disponible" in told and "1) mar 27 oct, 09:00" in told and "48" not in told
    reply, _ = say(store, "1")  # the offer is open again: a number books
    assert "queda reservada" in reply and store.booking_of("c1").starts_at == datetime(2026, 10, 27, 9, 0)


def test_with_no_other_time_at_all_they_are_told_to_write_again_to_book(store):
    hire(store, "Ana")
    book_nine(store)
    store.set_weekly("ana@sazon.test", [(0, 9 * 60, 9 * 60 + 15)], BOSS, NOW)  # one slot a week, then nothing
    conflicts = store.set_weekly("ana@sazon.test", [], BOSS, NOW)
    slot_flow.resolve_calls(store, CLIENT, conflicts, BOSS, NOW)
    told = store.outbox_pending("c1")[-1].text
    assert "ya no está disponible" in told and "1)" not in told and "escríbenos" in told


def test_a_recruiter_who_leaves_has_each_future_call_moved_or_released(store):
    hire(store, "Ana", "Luis")
    book_nine(store, "c1")
    book_nine(store, "c2")  # the other recruiter has the second 09:00 call
    leaving = owner(store, "c1")
    calls = store.future_calls(leaving, NOW_AWARE)
    store.remove_recruiter(leaving, BOSS, NOW)
    result = slot_flow.resolve_calls(store, CLIENT, calls, BOSS, NOW)
    assert result.moved + result.released == 1
    assert store.booking_of("c1") is None or owner(store, "c1") != leaving


def test_a_call_whose_candidate_was_erased_meanwhile_is_just_released(store):
    hire(store, "Ana")
    book_nine(store)
    conflicts = store.set_day_off("ana@sazon.test", MONDAY, True, BOSS, NOW)
    store.erase_candidate("c1", "recruiter:x", NOW, "request")
    result = slot_flow.resolve_calls(store, CLIENT, conflicts, BOSS, NOW)
    assert result.released == 1 and store.outbox_pending("c1") == []


def test_the_reminder_job_does_not_nag_a_candidate_whose_call_was_moved(store):
    hire(store, "Ana", "Luis")
    book_nine(store)
    slot_flow.resolve_calls(store, CLIENT, store.set_day_off(owner(store, "c1"), MONDAY, True, BOSS, NOW), BOSS, NOW)
    assert reminders.run_once(store, CLIENT, datetime(2026, 10, 27, 12, 0)) == []
