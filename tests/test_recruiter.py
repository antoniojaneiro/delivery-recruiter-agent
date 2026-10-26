"""D42: the recruiter's data is separate from the agent's, so neither can overwrite the other."""
import sqlite3
from datetime import date, datetime

import pytest

from tests.clients import client_for
from sazon import session
from sazon.model import RecruiterStatus
from sazon.screening import Screening
from sazon.store import Store

AREAS = {"Madrid": []}
T1 = datetime(2026, 10, 25, 10, 0)
T2 = datetime(2026, 10, 25, 11, 0)
T3 = datetime(2026, 10, 25, 12, 0)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "sazon.db")


def turn(store, cid="c1", now=T1, outcome="QUALIFIED", extracted=None, reasons=(), flags=()):
    store.commit_turn(cid, now, {}, extracted or {}, outcome, [], [], reasons=list(reasons), flags=list(flags))


def test_reasons_and_flags_are_stored_with_each_turn_for_the_dashboard(store):
    turn(store, outcome="BLOCKED", reasons=["BLOCKED_ON_NAME"], flags=["START_DATE_FAR"])
    record = store.get("c1")
    assert record.reasons == ["BLOCKED_ON_NAME"] and record.flags == ["START_DATE_FAR"]


def test_the_session_stores_the_decision_reasons_and_flags(store):
    screening = session.load(store, "c1", client_for(AREAS))
    screening.record_consent(True)
    for _ in range(6):
        screening.submit("name", "Juan", date(2026, 10, 25))
    session.commit(store, "c1", screening, T1)
    record = store.get("c1")
    assert record.outcome == "BLOCKED" and record.reasons == ["BLOCKED_ON_NAME"]


def test_a_new_candidate_starts_with_the_new_status_and_nobody_assigned(store):
    turn(store)
    recruiter = store.recruiter("c1")
    assert recruiter.status == RecruiterStatus.NEW and recruiter.assignee is None


def test_a_recruiter_can_set_a_status_assign_and_add_notes(store):
    turn(store)
    store.set_status("c1", RecruiterStatus.CONTACTED, "Ana", T2)
    store.assign("c1", "Ana", "Ana", T2)
    store.add_note("c1", "Llamé, volverá a llamar", "Ana", T2)
    store.add_note("c1", "Segunda llamada: confirmado", "Luis", T3)
    recruiter = store.recruiter("c1")
    assert (recruiter.status, recruiter.assignee) == (RecruiterStatus.CONTACTED, "Ana")
    assert [(n.author, n.text, n.at) for n in store.notes("c1")] == [
        ("Ana", "Llamé, volverá a llamar", T2), ("Luis", "Segunda llamada: confirmado", T3)]


def test_a_chat_turn_never_touches_the_recruiters_data(store):
    turn(store, outcome="IN_PROGRESS", extracted={"city": "Madrid"})
    store.set_status("c1", RecruiterStatus.INTERVIEW_SCHEDULED, "Ana", T2)
    store.add_note("c1", "entrevista el martes", "Ana", T2)
    turn(store, outcome="QUALIFIED", extracted={"city": "Madrid", "name": "Juan Pérez"}, now=T3)
    assert store.recruiter("c1").status == RecruiterStatus.INTERVIEW_SCHEDULED
    assert [n.text for n in store.notes("c1")] == ["entrevista el martes"]
    assert store.get("c1").outcome == "QUALIFIED"


def test_a_recruiter_action_never_changes_what_the_agent_stored(store):
    turn(store, outcome="DISQUALIFIED", extracted={"city": "Sevilla"}, reasons=["OUT_OF_AREA"])
    store.set_status("c1", RecruiterStatus.CONTACTED, "Ana", T2)
    record = store.get("c1")
    assert (record.outcome, record.extracted, record.reasons) == ("DISQUALIFIED", {"city": "Sevilla"}, ["OUT_OF_AREA"])


def test_a_recruiter_may_override_the_agents_rejection_and_it_is_all_logged(store):
    turn(store, outcome="DISQUALIFIED", reasons=["NO_LICENSE"])
    store.set_status("c1", RecruiterStatus.INTERVIEW_SCHEDULED, "Ana", T2)
    event = [e for e in store.events("c1") if e.type == "recruiter_status"][0]
    assert (event.actor, event.detail, event.at) == ("recruiter:Ana", "interview_scheduled", T2)


def test_agent_events_carry_the_agent_as_actor(store):
    store.commit_turn("c1", T1, {}, {}, "IN_PROGRESS", [("consent_given", "")], [])
    assert store.events("c1")[0].actor == "agent"


def test_every_recruiter_action_is_an_audit_event_with_who_and_when(store):
    turn(store)
    store.set_status("c1", RecruiterStatus.HIRED, "Ana", T2)
    store.assign("c1", "Luis", "Ana", T2)
    store.add_note("c1", "contrato firmado", "Luis", T3)
    logged = [(e.type, e.actor) for e in store.events("c1") if e.actor != "agent"]
    assert logged == [("recruiter_status", "recruiter:Ana"), ("recruiter_assigned", "recruiter:Ana"),
                      ("recruiter_note", "recruiter:Luis")]


def test_an_unknown_status_or_candidate_or_empty_name_is_refused(store):
    turn(store)
    with pytest.raises(ValueError):
        store.set_status("c1", "Dancing", "Ana", T2)
    with pytest.raises(ValueError):
        store.set_status("c1", RecruiterStatus.HIRED, "  ", T2)
    with pytest.raises(ValueError):
        store.add_note("c1", "   ", "Ana", T2)
    with pytest.raises(LookupError):
        store.set_status("ghost", RecruiterStatus.HIRED, "Ana", T2)
    assert store.recruiter("c1").status == RecruiterStatus.NEW


def test_candidates_can_be_filtered_by_outcome_and_by_recruiter_status(store):
    turn(store, "c1", outcome="QUALIFIED", now=T1)
    turn(store, "c2", outcome="QUALIFIED", now=T2)
    turn(store, "c3", outcome="BLOCKED", now=T3)
    store.set_status("c2", RecruiterStatus.CONTACTED, "Ana", T3)
    ids = lambda **kw: [r.candidate_id for r in store.list_candidates(**kw)]
    assert ids(outcome="QUALIFIED", status=RecruiterStatus.NEW) == ["c1"]
    assert ids(status=RecruiterStatus.CONTACTED) == ["c2"]
    assert ids(outcome="BLOCKED") == ["c3"]
    assert {r.candidate_id: r.status for r in store.list_candidates()}["c2"] == RecruiterStatus.CONTACTED


def test_a_database_created_before_these_columns_is_upgraded_in_place(tmp_path):
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE candidates (candidate_id TEXT PRIMARY KEY, state TEXT NOT NULL DEFAULT '{}',
            extracted TEXT NOT NULL DEFAULT '{}', summary TEXT, outcome TEXT, updated_at TEXT NOT NULL);
        CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id TEXT NOT NULL,
            type TEXT NOT NULL, detail TEXT NOT NULL, at TEXT NOT NULL);
        INSERT INTO candidates (candidate_id, outcome, updated_at) VALUES ('old1', 'QUALIFIED', '2026-10-01T10:00:00');
        INSERT INTO events (candidate_id, type, detail, at) VALUES ('old1', 'decision', '{}', '2026-10-01T10:00:00');
    """)
    db.commit()
    db.close()
    store = Store(path)
    assert store.get("old1").outcome == "QUALIFIED" and store.get("old1").reasons == []
    assert store.events("old1")[0].actor == "agent"
    store.set_status("old1", RecruiterStatus.CONTACTED, "Ana", T2)
