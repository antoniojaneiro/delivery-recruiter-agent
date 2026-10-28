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
          "booked": "Llamada reservada", "contacted": "Contactado", "interview_scheduled": "Entrevista",
          "hired": "Contratado"}
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
    assert all(s[k] == StepState.LEFT for k in ("experience", "city", "license", "qualified", "booked", "contacted",
                                                "interview_scheduled", "hired"))


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
    assert s["contacted"] == StepState.LEFT


def test_a_booked_candidate_waits_for_the_recruiter_to_make_contact():
    p = path(screening(*ANSWERS), outcome="QUALIFIED", booked=True)
    assert states(p)["booked"] == StepState.DONE and states(p)["contacted"] == StepState.CURRENT


def test_the_recruiters_steps_are_done_up_to_the_status_and_the_next_one_is_current():
    p = path(screening(*ANSWERS), outcome="QUALIFIED", booked=True, status=S.CONTACTED, history=[S.CONTACTED])
    s = states(p)
    assert s["contacted"] == StepState.DONE and s["interview_scheduled"] == StepState.CURRENT
    assert s["hired"] == StepState.LEFT


def test_a_hired_candidate_has_done_everything_including_the_steps_before_it():
    p = path(screening(*ANSWERS), outcome="QUALIFIED", booked=True, status=S.HIRED, history=[S.HIRED])
    assert p.mark == Mark.HIRED and all(step.state == StepState.DONE for step in p.steps)


def test_a_candidate_rejected_after_contact_stopped_at_the_interview():
    p = path(screening(*ANSWERS), outcome="QUALIFIED", booked=True, status=S.REJECTED, history=[S.CONTACTED, S.REJECTED])
    s = states(p)
    assert p.mark == Mark.OUT and s["contacted"] == StepState.DONE and s["interview_scheduled"] == StepState.STOPPED
    assert s["hired"] == StepState.LEFT


def test_when_a_recruiter_takes_over_what_the_agent_did_not_finish_is_skipped_not_done():
    p = path(screening("name", "experience"), outcome="DISQUALIFIED", reasons=["NO_LICENSE"], status=S.CONTACTED,
             history=[S.CONTACTED])
    s = states(p)
    assert p.mark == Mark.IN_PROCESS
    assert s["name"] == StepState.DONE and s["license"] == s["qualified"] == s["booked"] == StepState.SKIPPED
    assert s["contacted"] == StepState.DONE and s["interview_scheduled"] == StepState.CURRENT


def test_a_client_that_books_no_calls_has_no_call_step():
    p = path(screening(*ANSWERS), outcome="QUALIFIED", calls=False)
    assert "booked" not in states(p) and states(p)["contacted"] == StepState.CURRENT


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
    assert [step.key for step in p.steps] == ["started", "consent", "name", "shift", "can_lift", "qualified", "contacted",
                                             "interview_scheduled", "hired"]
    assert {s.key: s.state for s in p.steps}["shift"] == StepState.CURRENT
