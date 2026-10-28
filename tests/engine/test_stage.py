"""D92: the "Estado" a recruiter sees is one word per candidate. The system moves it by itself (Contacted while the
conversation goes, Qualified when the agent qualifies, Interview scheduled when the candidate books a call, Rejected when
the agent turns them down); what a recruiter decided (Hired, Rejected, or any other state) wins over it."""
from screener.model import Outcome, RecruiterStatus as S, stage_of
from tests.support.tables import table

NEW = S.NEW


@table("outcome,status,booked,expected", [
    # what the system shows when no recruiter decided anything
    (Outcome.IN_PROGRESS, NEW, False, S.CONTACTED),
    (None, NEW, False, S.CONTACTED),
    (Outcome.STALLED, NEW, False, S.CONTACTED),      # not finished: the Agent column says why
    (Outcome.BLOCKED, NEW, False, S.CONTACTED),
    (Outcome.WITHDRAWN, NEW, False, S.CONTACTED),
    (Outcome.QUALIFIED, NEW, False, S.QUALIFIED),
    (Outcome.QUALIFIED, NEW, True, S.INTERVIEW_SCHEDULED),   # booking moves it forward ...
    (Outcome.DISQUALIFIED, NEW, False, S.REJECTED),
    (Outcome.ENDED_OFF_TOPIC, NEW, False, S.REJECTED),
    # a recruiter's decision wins, whatever the agent said
    (Outcome.QUALIFIED, S.HIRED, True, S.HIRED),
    (Outcome.QUALIFIED, S.REJECTED, True, S.REJECTED),
    (Outcome.QUALIFIED, S.UNREACHABLE, False, S.REJECTED),   # the old state is shown as Rejected
    (Outcome.DISQUALIFIED, S.QUALIFIED, False, S.QUALIFIED),  # a human overruled the agent
    (Outcome.DISQUALIFIED, S.QUALIFIED, True, S.INTERVIEW_SCHEDULED),  # ... and a recruiter's Qualified moves on too
    (Outcome.IN_PROGRESS, S.QUALIFIED, False, S.QUALIFIED),
    (Outcome.QUALIFIED, S.CONTACTED, False, S.CONTACTED),
    (Outcome.QUALIFIED, S.INTERVIEW_SCHEDULED, False, S.INTERVIEW_SCHEDULED),
])
def test_what_estado_shows_is_the_recruiters_decision_or_else_what_the_system_derives(outcome, status, booked, expected):
    assert stage_of(outcome, status, booked) is expected


# --- on a saved candidate -----------------------------------------------------------------------------------------

import pytest

from sazon.client import SAZON_CALENDAR
from screener.store import Store
from tests.support.booking import NOW, NOW_AWARE, hire, qualify, say


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "s.db", calendar=SAZON_CALENDAR)
    hire(s, "Ana")
    return s


def shown(store, cid="c1"):
    return store.get(cid).stage


def test_the_stage_moves_forward_when_a_call_is_booked_and_back_when_it_is_released(store):
    qualify(store)
    assert shown(store) is S.QUALIFIED and store.get("c1").assignee is None
    say(store, "1")
    assert shown(store) is S.INTERVIEW_SCHEDULED and store.get("c1").assignee == "ana@sazon.test"  # assigned by booking
    store.cancel_slot(store.booking_of("c1").slot_id, "Ana", NOW_AWARE)
    assert shown(store) is S.QUALIFIED and store.get("c1").assignee is None


def test_choosing_the_state_the_system_shows_leaves_it_automatic_so_it_keeps_moving(store):
    qualify(store)
    store.set_stage("c1", S.QUALIFIED, "ana@sazon.test", NOW)  # what it already shows: nothing is stored
    assert store.get("c1").status is S.NEW
    say(store, "1")
    assert shown(store) is S.INTERVIEW_SCHEDULED


def test_a_state_a_recruiter_chooses_stays_whatever_happens_after(store):
    qualify(store)
    store.set_stage("c1", S.HIRED, "ana@sazon.test", NOW)
    say(store, "1")
    assert shown(store) is S.HIRED and store.get("c1").status is S.HIRED
    store.set_stage("c1", S.REJECTED, "ana@sazon.test", NOW)
    assert shown(store) is S.REJECTED
