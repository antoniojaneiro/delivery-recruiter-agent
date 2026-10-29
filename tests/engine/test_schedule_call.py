"""D79: a recruiter books or moves a qualified candidate's call from the calendar. One atomic step in the store (free the
old time, book the new one, one audit line by the recruiter), then the candidate's chat is told in a fixed text and their
open offer of times is closed, so the chat and the reminder job do not ask them to pick one again."""
import threading
from datetime import datetime, timedelta

import pytest

from sazon.areas import AREAS
from sazon.pack import SLOTS
from screener import recruiter_calls, reminders, turn
from screener.phrasing import slot_label
from screener.store import InputError, Store
from tests.support.booking import ES_SLOTS, MX_SLOT, NOW, NOW_AWARE, add_slots, qualify, say
from tests.support.clients import client_for

CLIENT = client_for(AREAS)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "s.db", calendar=CLIENT.calendar)


def schedule(store, cid, slot, recruiter="Ana", now=NOW_AWARE, country=None):
    return store.move_booking(cid, slot, recruiter, now, country=country)


# --- the store: one atomic step ---------------------------------------------------------------------------------

def test_a_recruiter_books_a_free_time_for_a_candidate_and_it_is_logged_as_theirs(store):
    slots = add_slots(store)
    qualify(store)
    booking, before = schedule(store, "c1", slots[1])
    assert before is None and booking.starts_at == ES_SLOTS[1] and store.booking_of("c1").slot_id == slots[1]
    event = [e for e in store.events("c1") if e.type == "slot_booked"][-1]
    assert event.actor == "recruiter:Ana"


def test_moving_a_booking_frees_the_old_time_without_cancelling_it_and_logs_one_line(store):
    slots = add_slots(store)
    qualify(store)
    schedule(store, "c1", slots[0])
    booking, before = schedule(store, "c1", slots[2])
    assert before.slot_id == slots[0] and booking.slot_id == slots[2] == store.booking_of("c1").slot_id
    assert slots[0] in [s.id for s in store.free_slots("ES", NOW)]  # free again, not cancelled
    moved = [e for e in store.events("c1") if e.type == "slot_moved"]
    assert len(moved) == 1 and moved[0].actor == "recruiter:Ana"
    assert not [e for e in store.events("c1") if e.type == "slot_cancelled"]


def test_scheduling_the_time_a_candidate_already_has_changes_nothing(store):
    slots = add_slots(store)
    qualify(store)
    schedule(store, "c1", slots[0])
    events = len(store.events("c1"))
    booking, before = schedule(store, "c1", slots[0])
    assert booking.slot_id == before.slot_id == slots[0] and len(store.events("c1")) == events


def test_a_time_someone_else_holds_is_refused_and_the_candidates_own_call_stays(store):
    slots = add_slots(store)
    qualify(store, "c1")
    qualify(store, "c2")
    schedule(store, "c2", slots[1])
    schedule(store, "c1", slots[0])
    with pytest.raises(InputError) as refused:
        schedule(store, "c1", slots[1])
    assert refused.value.code == "slot_unavailable" and store.booking_of("c1").slot_id == slots[0]


def test_a_time_in_another_country_is_refused_when_the_candidates_country_is_given(store):
    add_slots(store)
    mexico = add_slots(store, "MX", [MX_SLOT])
    qualify(store)
    with pytest.raises(InputError) as refused:
        schedule(store, "c1", mexico[0], country="ES")
    assert refused.value.code == "wrong_country" and store.booking_of("c1") is None


def test_a_recruiter_may_book_a_time_later_today_but_not_one_that_has_started(store):
    slots = add_slots(store)
    qualify(store)
    with pytest.raises(InputError) as refused:
        schedule(store, "c1", slots[0], now=datetime(2026, 11, 3, 10, 1).astimezone())
    assert refused.value.code == "in_the_past" and store.booking_of("c1") is None
    assert schedule(store, "c1", slots[0], now=datetime(2026, 11, 3, 9, 0).astimezone())[0].slot_id == slots[0]


def test_the_recruiters_name_is_required_and_an_unknown_candidate_is_not_found(store):
    slots = add_slots(store)
    qualify(store)
    with pytest.raises(InputError) as refused:
        schedule(store, "c1", slots[0], recruiter=" ")
    assert refused.value.code == "name_required"
    with pytest.raises(LookupError):
        schedule(store, "nobody", slots[0])


def test_two_recruiters_booking_the_same_time_for_two_candidates_at_once_give_it_to_one(store):
    slots = add_slots(store)
    qualify(store, "c1")
    qualify(store, "c2")
    results = []

    def go(cid):
        try:
            schedule(store, cid, slots[0])
            results.append("booked")
        except InputError as error:
            results.append(error.code)

    threads = [threading.Thread(target=go, args=(cid,)) for cid in ("c1", "c2")]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == ["booked", "slot_unavailable"]


# --- the flow: the candidate is told, the open offer closes ----------------------------------------------------------

def test_the_candidate_is_told_in_a_fixed_text_in_their_chat_language(store):
    slots = add_slots(store)
    qualify(store)
    done = recruiter_calls.schedule_by_recruiter(store, CLIENT, "c1", slots[1], "Ana", NOW)
    booking = done.booking
    label = slot_label(booking.starts_at, "es")
    queued = [e.text for e in store.outbox_pending("c1")]
    assert queued == [SLOTS.scheduled["es"].format(label=label)] and [m.text for m in store.messages("c1")][-1] == queued[0]


def test_an_english_speaking_candidate_is_told_in_english(store):
    slots = add_slots(store)
    qualify(store, english=True)
    booking = recruiter_calls.schedule_by_recruiter(store, CLIENT, "c1", slots[1], "Ana", NOW).booking
    assert store.outbox_pending("c1")[0].text == SLOTS.scheduled["en"].format(label=slot_label(booking.starts_at, "en"))


def test_a_moved_call_is_told_as_moved(store):
    slots = add_slots(store)
    qualify(store)
    recruiter_calls.schedule_by_recruiter(store, CLIENT, "c1", slots[0], "Ana", NOW)
    moved = recruiter_calls.schedule_by_recruiter(store, CLIENT, "c1", slots[2], "Ana", NOW)
    booking = moved.booking
    assert moved.before is not None
    assert store.outbox_pending("c1")[-1].text == SLOTS.moved["es"].format(label=slot_label(booking.starts_at, "es"))


def test_a_time_that_is_gone_tells_the_candidate_nothing(store):
    slots = add_slots(store)
    qualify(store, "c1")
    qualify(store, "c2")
    recruiter_calls.schedule_by_recruiter(store, CLIENT, "c2", slots[0], "Ana", NOW)
    with pytest.raises(InputError):
        recruiter_calls.schedule_by_recruiter(store, CLIENT, "c1", slots[0], "Ana", NOW)
    assert store.outbox_pending("c1") == []


def test_the_candidates_open_offer_is_closed_so_a_late_reply_gets_the_booked_time_not_a_new_list(store):
    slots = add_slots(store)
    qualify(store)  # the chat has offered three times and waits for a number
    assert store.get("c1").state.get("slot_offer")
    recruiter_calls.schedule_by_recruiter(store, CLIENT, "c1", slots[2], "Ana", NOW)
    reply, _ = say(store, "2")
    assert slot_label(ES_SLOTS[2], "es") in reply and store.booking_of("c1").slot_id == slots[2]


def test_the_reminder_job_does_not_ask_a_booked_candidate_to_pick_a_time(store):
    slots = add_slots(store)
    qualify(store)
    recruiter_calls.schedule_by_recruiter(store, CLIENT, "c1", slots[2], "Ana", NOW)
    sent_before = len(store.outbox_pending("c1"))
    reminders.run_once(store, CLIENT, NOW + timedelta(hours=26))
    assert len(store.outbox_pending("c1")) == sent_before


def test_a_booking_that_cannot_be_told_to_the_candidate_is_kept_and_says_so(store, monkeypatch):
    from screener.store import ConflictError
    slots = add_slots(store)
    qualify(store)

    def lost(*args, **kwargs):
        raise ConflictError("c1")

    monkeypatch.setattr(recruiter_calls.conversation, "run", lost)
    done = recruiter_calls.schedule_by_recruiter(store, CLIENT, "c1", slots[0], "Ana", NOW)  # no crash
    assert done.told is False and store.booking_of("c1").slot_id == slots[0] and store.outbox_pending("c1") == []


def test_a_told_booking_says_so(store):
    slots = add_slots(store)
    qualify(store)
    assert recruiter_calls.schedule_by_recruiter(store, CLIENT, "c1", slots[0], "Ana", NOW).told is True


def test_a_client_that_books_no_calls_refuses_cleanly(tmp_path):
    from tests.support.toy_spec import TOY_CLIENT
    toy_store = Store(tmp_path / "toy.db")
    toy_store.commit_turn("t1", NOW, {"consent": True}, {"name": "Ann Lee"}, "QUALIFIED", [], [])
    with pytest.raises(InputError) as refused:
        toy_store.move_booking("t1", 1, "Ana", NOW_AWARE)
    assert refused.value.code == "no_calendar"
    with pytest.raises(InputError) as refused:
        recruiter_calls.schedule_by_recruiter(toy_store, TOY_CLIENT, "t1", 1, "Ana", NOW)
    assert refused.value.code == "no_calendar"
