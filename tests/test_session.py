import json
from datetime import date, datetime

import pytest

from sazon import session
from sazon.store import Store

AREAS = {"Madrid": [], "Guadalajara": []}
TODAY = date(2026, 10, 25)
T1 = datetime(2026, 10, 25, 10, 0)
T2 = datetime(2026, 10, 25, 10, 5)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "sazon.db")


def test_loading_an_unknown_candidate_starts_a_fresh_screening(store):
    screening = session.load(store, "c1", AREAS)
    assert screening.next_field() == "consent"


def test_a_half_finished_screening_resumes_where_it_stopped(store):
    screening = session.load(store, "c1", AREAS)
    screening.record_consent(True)
    screening.submit("name", "Juan", TODAY)
    screening.submit("city", "Guadalajra", TODAY)
    session.commit(store, "c1", screening, T1)

    resumed = session.load(store, "c1", AREAS)
    assert resumed.confirm_city(True).status == "ok"
    assert resumed.submit("name", "Juan", TODAY).status == "follow_up"
    assert resumed.submit("name", "Juan", TODAY).status == "follow_up"
    assert resumed.submit("name", "Juan", TODAY).status == "review"


def test_commit_stores_extracted_json_and_the_outcome_for_the_dashboard(store):
    screening = session.load(store, "c1", AREAS)
    screening.record_consent(True)
    screening.submit("start_date", date(2026, 11, 1), TODAY)
    session.commit(store, "c1", screening, T1)
    record = store.get("c1")
    assert record.extracted == {"start_date": "2026-11-01"}
    assert record.outcome == "IN_PROGRESS"
    assert [r.candidate_id for r in store.list_candidates(outcome="IN_PROGRESS")] == ["c1"]


def test_screening_events_reach_the_audit_log_once_with_a_timestamp(store):
    screening = session.load(store, "c1", AREAS)
    screening.record_consent(True)
    screening.human_requested()
    session.commit(store, "c1", screening, T1)
    session.commit(store, "c1", screening, T2)
    again = session.load(store, "c1", AREAS)
    again.off_topic()
    session.commit(store, "c1", again, T2)
    events = [(e.type, e.at) for e in store.events("c1") if e.type in ("human_requested", "off_topic")]
    assert events == [("human_requested", T1), ("off_topic", T2)]


def test_a_decision_event_is_logged_only_when_the_outcome_changes(store):
    screening = session.load(store, "c1", AREAS)
    screening.record_consent(True)
    session.commit(store, "c1", screening, T1)
    session.commit(store, "c1", screening, T2)
    screening.submit("license", False, TODAY)
    screening.confirm_rejection(True)
    session.commit(store, "c1", screening, T2)
    decisions = [json.loads(e.detail) for e in store.events("c1") if e.type == "decision"]
    assert [d["outcome"] for d in decisions] == ["IN_PROGRESS", "DISQUALIFIED"]
    assert decisions[1]["reasons"] == ["NO_LICENSE"]


def test_messages_are_saved_with_the_turn(store):
    screening = session.load(store, "c1", AREAS)
    session.commit(store, "c1", screening, T1,
                   messages=[("agent", "Hola, soy el asistente virtual."), ("candidate", "Sí")])
    assert [(m.role, m.text) for m in store.messages("c1")] == [
        ("agent", "Hola, soy el asistente virtual."), ("candidate", "Sí")]


def test_a_failed_commit_does_not_lose_events_on_retry(store):
    screening = session.load(store, "c1", AREAS)
    screening.record_consent(True)
    screening.human_requested()
    with pytest.raises(Exception):
        session.commit(store, "c1", screening, T1, messages=[(None, "x")])
    session.commit(store, "c1", screening, T2)
    assert [e.type for e in store.events("c1") if e.type in ("human_requested", "off_topic")] == ["human_requested"]


def test_a_start_date_kept_for_review_as_raw_text_can_be_reloaded(store):
    screening = session.load(store, "c1", AREAS)
    screening.record_consent(True)
    for _ in range(4):
        screening.submit("start_date", "next week", TODAY)
    session.commit(store, "c1", screening, T1)
    resumed = session.load(store, "c1", AREAS)
    assert resumed.values["start_date"] == "next week"
    assert resumed.review_fields == {"start_date"}
