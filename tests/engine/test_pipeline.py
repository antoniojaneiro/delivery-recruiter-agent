"""D78: where a candidate is in the whole process (the agent's screening, then the recruiter's steps), and whether they are
still in it. Pure code over a saved screening, a status and the recruiter's history; the screens only draw it."""
from datetime import date

import pytest

from tests.support.tables import table

from sazon.client import SAZON_CLIENT
from sazon.spec import SAZON
from screener.model import Language, RecruiterStatus
from screener.pipeline import Mark, StepState, mark_of, path_of
from screener.screening import Screening

TODAY = date(2026, 10, 25)
AREAS = SAZON_CLIENT.areas
S = RecruiterStatus
ES = Language.ES
LABELS = {"started": "Conversación iniciada", "consent": "Consentimiento", "qualified": "Cualificado",
          "booked": "Entrevista programada", "hired": "Contratado"}
ANSWERS = {"name": "Juan Pérez", "experience": (2, ["glovo"]), "availability": ["full_time"], "schedule": "morning",
           "start_date": date(2026, 11, 1), "city": "Madrid", "license": True}


def screening(*fields, consent=True):
    s = Screening(AREAS, SAZON)
    s.record_consent(consent)
    for field in fields:
        s.submit(field, ANSWERS[field], TODAY)
    return s


def path(s, outcome="IN_PROGRESS", status=S.NEW, reasons=(), booked=False, history=(), calls=True):
    return path_of(s, outcome=outcome, status=status, reasons=list(reasons), booked=booked, history=history,
                   with_calls=calls, spec=SAZON, language=ES, labels=LABELS)


def states(p):
    return {step.key: step.state for step in p.steps}


@table("outcome,status,expected", [
    ("IN_PROGRESS", S.NEW, Mark.IN_PROCESS),
    (None, S.NEW, Mark.IN_PROCESS),
    ("QUALIFIED", S.NEW, Mark.IN_PROCESS),
    ("STALLED", S.NEW, Mark.PAUSED),
    ("BLOCKED", S.NEW, Mark.PAUSED),
    ("DISQUALIFIED", S.NEW, Mark.OUT),
    ("ENDED_OFF_TOPIC", S.NEW, Mark.OUT),
    ("WITHDRAWN", S.NEW, Mark.OUT),
    ("QUALIFIED", S.CONTACTED, Mark.IN_PROCESS),
    ("QUALIFIED", S.INTERVIEW_SCHEDULED, Mark.IN_PROCESS),
    ("QUALIFIED", S.QUALIFIED, Mark.IN_PROCESS),
    ("DISQUALIFIED", S.QUALIFIED, Mark.IN_PROCESS),   # a recruiter qualified someone the agent turned down
    ("QUALIFIED", S.HIRED, Mark.HIRED),
    ("QUALIFIED", S.REJECTED, Mark.OUT),
    ("QUALIFIED", S.UNREACHABLE, Mark.OUT),
    ("DISQUALIFIED", S.CONTACTED, Mark.IN_PROCESS),   # a recruiter overruled the agent
    ("DISQUALIFIED", S.HIRED, Mark.HIRED),
    ("STALLED", S.REJECTED, Mark.OUT),
    ("STALLED", S.INTERVIEW_SCHEDULED, Mark.IN_PROCESS),
])
def test_the_recruiter_status_overrules_the_agents_outcome_and_new_leaves_it_to_the_agent(outcome, status, expected):
    assert mark_of(outcome, status) == expected


def test_a_candidate_who_just_agreed_is_at_the_first_question_and_the_rest_is_left():
    p = path(screening())
    assert p.mark == Mark.IN_PROCESS
    s = states(p)
    assert s["started"] == s["consent"] == StepState.DONE
    assert s["name"] == StepState.CURRENT
    assert all(s[k] == StepState.LEFT for k in ("experience", "city", "license", "qualified", "booked", "hired"))


def test_answers_given_out_of_order_are_done_and_the_current_step_is_the_first_unanswered():
    p = path(screening("license", "city"))
    s = states(p)
    assert s["license"] == s["city"] == StepState.DONE and s["name"] == StepState.CURRENT
    assert s["experience"] == StepState.LEFT


def test_a_candidate_the_agent_rejected_stopped_at_the_answer_that_rejected_them():
    p = path(screening("name", "experience", "availability", "schedule", "start_date", "city"), outcome="DISQUALIFIED",
             reasons=["NO_LICENSE"])
    assert p.mark == Mark.OUT
    s = states(p)
    assert s["license"] == StepState.STOPPED
    assert s["qualified"] == s["booked"] == s["hired"] == StepState.LEFT
    assert p.why and "licen" in p.why[0].lower()


def test_a_candidate_who_declined_consent_stopped_at_consent():
    p = path(screening(consent=False), outcome="DISQUALIFIED", reasons=["NO_CONSENT"])
    assert p.mark == Mark.OUT and states(p)["consent"] == StepState.STOPPED and states(p)["name"] == StepState.LEFT


def test_a_stalled_candidate_is_paused_at_the_question_they_did_not_answer():
    p = path(screening("name", "experience"), outcome="STALLED")
    assert p.mark == Mark.PAUSED and states(p)["availability"] == StepState.CURRENT


def test_a_qualified_candidate_waits_at_the_call():
    p = path(screening(*ANSWERS), outcome="QUALIFIED")
    s = states(p)
    assert p.mark == Mark.IN_PROCESS and s["qualified"] == StepState.DONE and s["booked"] == StepState.CURRENT
    assert s["hired"] == StepState.LEFT


def test_a_candidate_with_an_interview_waits_for_the_hiring_decision():
    p = path(screening(*ANSWERS), outcome="QUALIFIED", booked=True)
    assert states(p)["booked"] == StepState.DONE and states(p)["hired"] == StepState.CURRENT


def test_a_hired_candidate_has_done_everything_including_the_steps_before_it():
    p = path(screening(*ANSWERS), outcome="QUALIFIED", booked=True, status=S.HIRED, history=[S.HIRED])
    assert p.mark == Mark.HIRED and all(step.state == StepState.DONE for step in p.steps)


def test_a_candidate_rejected_after_the_interview_stopped_at_the_hiring_decision():
    p = path(screening(*ANSWERS), outcome="QUALIFIED", booked=True, status=S.REJECTED, history=[S.REJECTED])
    s = states(p)
    assert p.mark == Mark.OUT and s["booked"] == StepState.DONE and s["hired"] == StepState.STOPPED


def test_when_a_recruiter_takes_over_what_the_agent_did_not_finish_is_skipped_not_done():
    p = path(screening("name", "experience"), outcome="DISQUALIFIED", reasons=["NO_LICENSE"], status=S.QUALIFIED)
    s = states(p)
    assert p.mark == Mark.IN_PROCESS
    assert s["name"] == StepState.DONE and s["license"] == s["qualified"] == s["booked"] == StepState.SKIPPED
    assert s["hired"] == StepState.CURRENT


def test_a_client_that_books_no_calls_has_no_call_step():
    p = path(screening(*ANSWERS), outcome="QUALIFIED", calls=False)
    assert "booked" not in states(p) and states(p)["hired"] == StepState.CURRENT


def test_the_steps_have_their_labels_in_the_recruiters_language():
    p = path(screening())
    labels = {step.key: step.label for step in p.steps}
    assert labels["started"] == "Conversación iniciada" and labels["hired"] == "Contratado"
    assert labels["name"] == SAZON.say(SAZON.field("name").label, ES)  # a question's name comes from the client's spec


def test_the_second_client_runs_through_the_same_pipeline_with_its_own_questions_and_no_calls():
    from tests.support.toy_spec import TOY, TOY_CLIENT
    toy = Screening(TOY_CLIENT.areas, TOY)
    toy.record_consent(True)
    toy.submit("name", "Ann Lee", TODAY)
    labels = {**LABELS, "booked": "unused"}
    p = path_of(toy, outcome="IN_PROGRESS", status=S.NEW, reasons=[], booked=False, history=[], with_calls=False,
                spec=TOY, language=Language.EN, labels=labels)
    assert [step.key for step in p.steps] == ["started", "consent", "name", "shift", "can_lift", "qualified", "hired"]
    assert {s.key: s.state for s in p.steps}["shift"] == StepState.CURRENT


# --- one definition of the steps and of "closed" (D88) --------------------------------------------------------------

def test_the_order_of_the_steps_and_the_closed_set_are_defined_once_and_every_reader_agrees():
    from screener.model import CLOSED_BY_RECRUITER, RECRUITER_STEPS, reached_by
    from screener.recruiter_rules import closed_by_recruiter
    from screener.store import _REACHED_BY

    class Rec:
        def __init__(self, status):
            self.status = status
    assert [s.value for s in RECRUITER_STEPS] == list(_REACHED_BY)  # the funnel's SQL counts the same steps, in order
    assert all(_REACHED_BY[s.value] == tuple(x.value for x in reached_by(s)) for s in RECRUITER_STEPS)
    for status in RecruiterStatus:
        in_closed = status in CLOSED_BY_RECRUITER
        assert closed_by_recruiter(Rec(status)) is in_closed
        assert (mark_of(None, status) in (Mark.OUT, Mark.HIRED)) is in_closed, status  # the pipeline reads the same set


def test_a_path_can_be_made_from_a_saved_record_without_the_page_building_a_screening():
    from datetime import datetime
    from screener.pipeline import path_for
    from screener.store import Store
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(pathlib.Path(tmp) / "s.db", calendar=SAZON_CLIENT.calendar)
        s = screening("name", "experience")
        store.commit_turn("c1", datetime(2026, 10, 25, 10, 0), s.to_state(), s.extracted(), "IN_PROGRESS", [], [])
        record = store.get("c1")
        made = path_for(record, [], client=SAZON_CLIENT, language=ES, labels=LABELS)
        assert made == path(s) and states(made)["name"] == StepState.DONE
