"""D87: who may be given a call is decided in the engine, once, and every way to book or to see times asks it: the
recruiter's calendar, the typed number, the picker, the picker's list of times, the reminder job. A candidate the agent
did not qualify, or whose case a recruiter closed (hired, rejected, unreachable), is never booked or offered times."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from sazon import config
from sazon.client import SAZON_CALENDAR
from screener import reminders, slot_flow, turn
from screener.model import RecruiterStatus as S
from screener.service import create_app
from screener.store import InputError, Store
from tests.support.booking import NOW, NOW_AWARE, add_slots, qualify, say
from tests.support.clients import client_for
from tests.support.fakes import ScriptedLLM

CLIENT = client_for(config.AREAS)
CLOSED = (S.HIRED, S.REJECTED, S.UNREACHABLE)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "s.db", calendar=SAZON_CALENDAR)


@pytest.fixture
def slots(store):
    return add_slots(store)


def close(store, status, cid="c1"):
    store.set_status(cid, status, "Ana", NOW)


def test_a_call_can_be_organised_exactly_for_the_states_qualified_and_interview_scheduled():
    from screener.recruiter_rules import can_schedule

    class Shown:
        def __init__(self, stage):
            self.stage = stage
    assert {stage: can_schedule(Shown(stage)) for stage in S} == {
        S.NEW: False, S.CONTACTED: False, S.QUALIFIED: True, S.INTERVIEW_SCHEDULED: True, S.HIRED: False,
        S.REJECTED: False, S.UNREACHABLE: False}


def test_a_recruiter_who_qualifies_someone_the_agent_turned_down_can_organise_their_call(store, slots):
    turn.start(store, CLIENT, "c9", NOW)
    store.commit_turn("c9", NOW, {}, {"name": "Ana Gil", "city": "Madrid"}, "DISQUALIFIED", [], [], reasons=["NO_LICENSE"])
    with pytest.raises(InputError):
        slot_flow.schedule_by_recruiter(store, CLIENT, "c9", slots[0], "Ana", NOW_AWARE)
    store.set_stage("c9", S.QUALIFIED, "Ana", NOW)
    assert slot_flow.schedule_by_recruiter(store, CLIENT, "c9", slots[0], "Ana", NOW_AWARE).booking.slot_id == slots[0]
    assert store.get("c9").stage is S.INTERVIEW_SCHEDULED


def test_only_a_qualified_candidate_nobody_closed_and_with_no_call_may_choose_a_time(store, slots):
    qualify(store, "c1")
    assert slot_flow.may_choose_time(store, CLIENT, "c1")
    for status in CLOSED:
        qualify(store, "c2")
        close(store, status, "c2")
        assert not slot_flow.may_choose_time(store, CLIENT, "c2"), status
        store.erase_candidate("c2", "Ana", NOW, "test")
    say(store, "1")
    assert not slot_flow.may_choose_time(store, CLIENT, "c1")  # now holds a call
    assert not slot_flow.may_choose_time(store, CLIENT, "nobody")
    turn.start(store, CLIENT, "c3", NOW)
    assert not slot_flow.may_choose_time(store, CLIENT, "c3")  # still answering questions


def test_a_recruiter_cannot_book_a_call_for_a_candidate_who_is_not_qualified_or_is_closed(store, slots):
    turn.start(store, CLIENT, "c0", NOW)  # in progress
    with pytest.raises(InputError) as refused:
        slot_flow.schedule_by_recruiter(store, CLIENT, "c0", slots[0], "Ana", NOW_AWARE)
    assert refused.value.code == "not_schedulable"
    for status in CLOSED:
        qualify(store, "c1")
        close(store, status)
        with pytest.raises(InputError) as refused:
            slot_flow.schedule_by_recruiter(store, CLIENT, "c1", slots[0], "Ana", NOW_AWARE)
        assert refused.value.code == "not_schedulable" and store.booking_of("c1") is None, status
        store.erase_candidate("c1", "Ana", NOW, "test")


def test_a_closed_candidate_cannot_book_by_typing_a_number_or_by_the_picker_and_is_not_shown_times_again(store, slots):
    qualify(store)
    close(store, S.REJECTED)
    for message in ("1", "hola", "1"):
        reply, _ = say(store, message)
        assert "1)" not in reply and "encaja" not in reply, message  # no new offer, no "your profile fits"
    assert store.booking_of("c1") is None and not store.get("c1").state.get("slot_offer")
    assert turn.handle_slot(store, CLIENT, "c1", slots[0], NOW) == "" and store.booking_of("c1") is None


def test_the_pickers_list_of_times_is_empty_for_a_candidate_who_may_not_choose(store, slots):
    import hashlib
    http = TestClient(create_app(CLIENT, store, ScriptedLLM(), clock=lambda: NOW))

    def times(cid):
        token = f"token-of-{cid}-" + "x" * 30
        store.set_token(cid, hashlib.sha256(token.encode()).hexdigest())
        return http.get(f"/candidates/{cid}/times", params={"day": "2026-11-03"},
                        headers={"Authorization": f"Bearer {token}"}).json()["times"]

    qualify(store, "c1")
    assert len(times("c1")) == 1
    qualify(store, "c2")
    close(store, S.HIRED, "c2")
    turn.start(store, CLIENT, "c3", NOW)
    assert times("c2") == [] and times("c3") == []


def test_the_reminder_job_does_not_ask_a_closed_candidate_to_pick_a_time(store, slots):
    qualify(store)
    close(store, S.REJECTED)
    assert reminders.run_once(store, CLIENT, datetime(2026, 10, 27, 12, 0)) == []
    assert not store.outbox_pending("c1")
