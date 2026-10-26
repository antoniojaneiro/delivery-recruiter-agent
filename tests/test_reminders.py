"""D58: the 24-hour reminder job. Called with a given time, so no real waiting is needed."""
from datetime import datetime, timedelta

import pytest

from sazon.sazon_spec import SAZON
from sazon.sazon_client import SAZON_CLIENT
from sazon import reminders, session, turn
from sazon.phrasing import Directive, Kind, phrase
from sazon.store import ConflictError, Store
from tests.fakes import ScriptedLLM
from tests.test_turn_slots import add_slots, qualify

T0 = datetime(2026, 10, 25, 10, 0)
HOUR = timedelta(hours=1)
REMINDER_TEXT = phrase(None, SAZON, Directive(Kind.REMINDER), "es")


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "s.db")


def in_progress(store, cid="c1"):
    turn.start(store, SAZON_CLIENT, cid, T0)
    turn.handle_message(ScriptedLLM(), store, SAZON_CLIENT, cid, "sí", T0)


def outcome(store, cid="c1"):
    return store.get(cid).outcome


def kinds(actions):
    return [(a.candidate_id, a.kind) for a in actions]


def test_nothing_happens_before_24_hours_of_silence(store):
    in_progress(store)
    assert reminders.run_once(store, SAZON_CLIENT, T0 + 23 * HOUR) == []
    assert store.outbox_pending() == []


def test_after_24_hours_one_reminder_is_queued_and_the_chat_stays_open(store):
    in_progress(store)
    assert kinds(reminders.run_once(store, SAZON_CLIENT, T0 + 24 * HOUR)) == [("c1", "reminder")]
    [entry] = store.outbox_pending()
    assert entry.candidate_id == "c1" and entry.text == REMINDER_TEXT
    assert outcome(store) == "IN_PROGRESS"
    assert store.messages("c1")[-1].text == REMINDER_TEXT
    assert "reminder_sent" in [e.type for e in store.events("c1")]


def test_running_again_straight_away_does_nothing_more(store):
    in_progress(store)
    reminders.run_once(store, SAZON_CLIENT, T0 + 24 * HOUR)
    assert reminders.run_once(store, SAZON_CLIENT, T0 + 24 * HOUR) == []
    assert reminders.run_once(store, SAZON_CLIENT, T0 + 30 * HOUR) == []
    assert len(store.outbox_pending()) == 1


def test_24_hours_after_the_reminder_with_no_reply_the_candidate_is_stalled(store):
    in_progress(store)
    reminders.run_once(store, SAZON_CLIENT, T0 + 24 * HOUR)
    assert reminders.run_once(store, SAZON_CLIENT, T0 + 47 * HOUR) == []
    assert kinds(reminders.run_once(store, SAZON_CLIENT, T0 + 48 * HOUR)) == [("c1", "stalled")]
    assert outcome(store) == "STALLED" and len(store.outbox_pending()) == 1
    assert reminders.run_once(store, SAZON_CLIENT, T0 + 100 * HOUR) == []


def test_a_reply_after_the_reminder_restarts_the_clock(store):
    in_progress(store)
    reminders.run_once(store, SAZON_CLIENT, T0 + 24 * HOUR)
    turn.handle_message(ScriptedLLM([{"name": "Juan Pérez"}]), store, SAZON_CLIENT, "c1", "Juan Pérez", T0 + 30 * HOUR)
    assert reminders.run_once(store, SAZON_CLIENT, T0 + 53 * HOUR) == []
    assert kinds(reminders.run_once(store, SAZON_CLIENT, T0 + 54 * HOUR)) == [("c1", "reminder")]
    assert len(store.outbox_pending()) == 2  # a second silence gets its own single reminder


def test_a_stalled_candidate_can_come_back_by_writing(store):
    in_progress(store)
    reminders.run_once(store, SAZON_CLIENT, T0 + 24 * HOUR)
    reminders.run_once(store, SAZON_CLIENT, T0 + 48 * HOUR)
    turn.handle_message(ScriptedLLM([{"name": "Juan Pérez"}]), store, SAZON_CLIENT, "c1", "Juan Pérez", T0 + 60 * HOUR)
    assert outcome(store) == "IN_PROGRESS"


def test_a_blocked_candidate_is_reminded_too(store):
    in_progress(store)
    for _ in range(6):
        turn.handle_message(ScriptedLLM([{"name": "Juan"}]), store, SAZON_CLIENT, "c1", "Juan", T0)
    assert outcome(store) == "BLOCKED"
    assert kinds(reminders.run_once(store, SAZON_CLIENT, T0 + 24 * HOUR)) == [("c1", "reminder")]


@pytest.mark.parametrize("prepare", [
    lambda s: (in_progress(s), turn.handle_message(ScriptedLLM(), s, SAZON_CLIENT, "c1", "me retiro", T0)),
    lambda s: (turn.start(s, SAZON_CLIENT, "c1", T0), turn.handle_message(ScriptedLLM(), s, SAZON_CLIENT, "c1", "no gracias", T0)),
])
def test_candidates_who_left_are_never_nagged(store, prepare):
    prepare(store)
    assert reminders.run_once(store, SAZON_CLIENT, T0 + 100 * HOUR) == []


def test_final_closes_get_no_reminders(store):
    in_progress(store)
    turn.handle_message(ScriptedLLM([{"has_license": False}]), store, SAZON_CLIENT, "c1", "no tengo licencia", T0)
    turn.handle_message(ScriptedLLM([{"confirms_rejection": True}]), store, SAZON_CLIENT, "c1", "sí", T0)
    assert outcome(store) == "DISQUALIFIED"
    assert reminders.run_once(store, SAZON_CLIENT, T0 + 100 * HOUR) == []


def test_someone_who_never_answered_the_consent_question_is_not_contacted_again(store):
    turn.start(store, SAZON_CLIENT, "c1", T0)  # the disclosure was sent; they have agreed to nothing
    assert reminders.run_once(store, SAZON_CLIENT, T0 + 100 * HOUR) == []
    assert store.outbox_pending() == []


# --- qualified candidates who ignore the slot offer (the D48 gap) -------------------------------------------------------

def test_a_qualified_candidate_who_ignores_the_offer_is_reminded_with_the_same_slots(store):
    add_slots(store)
    qualify(store)
    assert kinds(reminders.run_once(store, SAZON_CLIENT, T0 + 24 * HOUR)) == [("c1", "reminder")]
    [entry] = store.outbox_pending()
    assert "Te recuerdo las horas disponibles" in entry.text and "1)" in entry.text and "ninguna" in entry.text
    assert outcome(store) == "QUALIFIED"
    reply = turn.handle_message(ScriptedLLM(), store, SAZON_CLIENT, "c1", "1", T0 + 25 * HOUR)
    assert "queda reservada" in reply


def test_if_they_still_do_not_answer_the_offer_ends_and_the_48_hour_promise_is_sent(store):
    add_slots(store)
    qualify(store)
    reminders.run_once(store, SAZON_CLIENT, T0 + 24 * HOUR)
    assert kinds(reminders.run_once(store, SAZON_CLIENT, T0 + 48 * HOUR)) == [("c1", "gave_up_offer")]
    last = store.outbox_pending()[-1]
    assert "48 horas" in last.text and "1)" not in last.text
    assert outcome(store) == "QUALIFIED" and store.booking_of("c1") is None
    assert reminders.run_once(store, SAZON_CLIENT, T0 + 100 * HOUR) == []


def test_a_qualified_candidate_with_a_booking_or_no_offer_is_left_alone(store):
    add_slots(store)
    qualify(store)
    turn.handle_message(ScriptedLLM(), store, SAZON_CLIENT, "c1", "1", T0)
    assert reminders.run_once(store, SAZON_CLIENT, T0 + 100 * HOUR) == []


# --- safety ----------------------------------------------------------------------------------------------------------

def test_a_candidate_whose_record_changed_meanwhile_is_skipped_and_the_others_still_get_theirs(store, monkeypatch):
    in_progress(store, "c1")
    in_progress(store, "c2")
    real_commit = session.commit

    def commit(store_, cid, screening, now, **kwargs):
        if cid == "c1":
            raise ConflictError(cid)
        return real_commit(store_, cid, screening, now, **kwargs)

    monkeypatch.setattr(reminders.session, "commit", commit)
    assert kinds(reminders.run_once(store, SAZON_CLIENT, T0 + 24 * HOUR)) == [("c2", "reminder")]
    assert [e.candidate_id for e in store.outbox_pending()] == ["c2"]


def test_while_applications_are_closed_nobody_is_reminded(store):
    in_progress(store)
    store.set_accepting(False, "Ana", T0.astimezone())
    assert reminders.run_once(store, SAZON_CLIENT, T0 + 100 * HOUR) == []
    assert store.outbox_pending() == []


def test_the_job_ignores_the_aware_timestamps_that_dashboard_actions_write(store):
    in_progress(store)
    store.set_status("c1", "contacted", "Ana", T0.astimezone() + 30 * HOUR)  # a dashboard action, much later
    assert kinds(reminders.run_once(store, SAZON_CLIENT, T0 + 24 * HOUR)) == [("c1", "reminder")]


# --- the outbox -----------------------------------------------------------------------------------------------------------

def test_queued_messages_are_listed_in_order_and_disappear_once_delivered(store):
    in_progress(store, "c1")
    in_progress(store, "c2")
    reminders.run_once(store, SAZON_CLIENT, T0 + 24 * HOUR)
    pending = store.outbox_pending()
    assert [e.candidate_id for e in pending] == ["c1", "c2"]
    assert [e.candidate_id for e in store.outbox_pending("c2")] == ["c2"]
    store.mark_delivered(pending[0].id, T0)
    assert [e.candidate_id for e in store.outbox_pending()] == ["c2"]


def test_erasing_a_candidate_removes_their_queued_messages_too(store):
    in_progress(store)
    reminders.run_once(store, SAZON_CLIENT, T0 + 24 * HOUR)
    store.erase_candidate("c1", "recruiter:Ana", T0, "request")
    assert store.outbox_pending() == []


def test_the_command_runs_once_and_says_what_it_did(store, tmp_path, monkeypatch, capsys):
    in_progress(store)
    monkeypatch.setenv("SAZON_DB", str(tmp_path / "s.db"))
    reminders.main(["--now", (T0 + 24 * HOUR).isoformat()])
    out = capsys.readouterr().out
    assert "c1" in out and "reminder" in out
