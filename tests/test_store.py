from datetime import datetime

import pytest

from sazon.store import Store

T1 = datetime(2026, 10, 25, 10, 0)
T2 = datetime(2026, 10, 25, 10, 5)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "sazon.db")


def test_unknown_candidate_returns_none(store):
    assert store.get("nope") is None


def test_state_extracted_json_and_summary_are_stored_separately(store):
    store.save("c1", state={"outcome": "IN_PROGRESS", "stage": "name"}, now=T1)
    store.save("c1", extracted={"name": "Juan Pérez", "years": 2}, now=T1)
    store.save("c1", summary="Qualified driver in Madrid.", now=T2)
    record = store.get("c1")
    assert record.state == {"outcome": "IN_PROGRESS", "stage": "name"}
    assert record.extracted == {"name": "Juan Pérez", "years": 2}
    assert record.summary == "Qualified driver in Madrid."
    assert record.updated_at == T2


def test_saving_one_part_keeps_the_others(store):
    store.save("c1", state={"outcome": "QUALIFIED"}, extracted={"name": "A B"}, now=T1)
    store.save("c1", state={"outcome": "NEEDS_REVIEW"}, now=T2)
    assert store.get("c1").extracted == {"name": "A B"}


def test_data_survives_reopening_the_database(tmp_path):
    Store(tmp_path / "s.db").save("c1", state={"outcome": "QUALIFIED"}, now=T1)
    assert Store(tmp_path / "s.db").get("c1").state == {"outcome": "QUALIFIED"}


def test_events_are_kept_in_order_and_survive_later_saves(store):
    store.add_event("c1", "consent_given", "", now=T1)
    store.add_event("c1", "decision", "QUALIFIED", now=T2)
    store.save("c1", state={"outcome": "QUALIFIED"}, now=T2)
    events = store.events("c1")
    assert [(e.type, e.detail, e.at) for e in events] == [
        ("consent_given", "", T1),
        ("decision", "QUALIFIED", T2),
    ]


def test_list_candidates_filters_by_outcome(store):
    store.save("c1", outcome="QUALIFIED", now=T1)
    store.save("c2", outcome="DISQUALIFIED", now=T1)
    assert [r.candidate_id for r in store.list_candidates(outcome="QUALIFIED")] == ["c1"]
    assert {r.candidate_id for r in store.list_candidates()} == {"c1", "c2"}


def test_conversation_history_is_kept_in_order_apart_from_audit_events(store):
    store.add_message("c1", "agent", "Hola, soy el asistente virtual de Grupo Sazón.", now=T1)
    store.add_message("c1", "candidate", "Hola, ¿qué tal?", now=T2)
    store.add_event("c1", "consent_given", "", now=T2)
    messages = store.messages("c1")
    assert [(m.role, m.text, m.at) for m in messages] == [
        ("agent", "Hola, soy el asistente virtual de Grupo Sazón.", T1),
        ("candidate", "Hola, ¿qué tal?", T2),
    ]
    assert [e.type for e in store.events("c1")] == ["consent_given"]


def test_messages_of_other_candidates_are_not_mixed(store):
    store.add_message("c1", "candidate", "uno", now=T1)
    store.add_message("c2", "candidate", "dos", now=T1)
    assert [m.text for m in store.messages("c2")] == ["dos"]


def test_a_real_screening_can_be_filtered_by_its_decided_outcome(store):
    from datetime import date

    from sazon.screening import Screening

    areas = {"Madrid": []}
    qualified = Screening(areas)
    qualified.record_consent(True)
    for field, value in [("name", "Juan Pérez"), ("experience", (0, [])), ("availability", ["weekends"]),
                         ("schedule", "flexible"), ("start_date", date(2026, 11, 1)),
                         ("city", "Madrid"), ("license", True)]:
        qualified.submit(field, value, date(2026, 10, 25))
    declined = Screening(areas)
    declined.record_consent(False)
    for cid, s in (("q", qualified), ("d", declined)):
        store.save(cid, state=s.to_state(), extracted=s.extracted(),
                   outcome=s.decide().outcome, now=T1)
    assert [r.candidate_id for r in store.list_candidates(outcome="QUALIFIED")] == ["q"]
    assert [r.candidate_id for r in store.list_candidates(outcome="DISQUALIFIED")] == ["d"]
    assert store.get("q").outcome == "QUALIFIED"


import sqlite3


def test_commit_turn_saves_everything_in_one_transaction(store):
    store.commit_turn("c1", now=T1, state={"s": 1}, extracted={"name": "A B"}, outcome="IN_PROGRESS",
                      events=[("consent_given", ""), ("decision", "IN_PROGRESS")],
                      messages=[("candidate", "hola"), ("agent", "¿Tu nombre?")])
    record = store.get("c1")
    assert (record.state, record.extracted, record.outcome) == ({"s": 1}, {"name": "A B"}, "IN_PROGRESS")
    assert [e.type for e in store.events("c1")] == ["consent_given", "decision"]
    assert [m.text for m in store.messages("c1")] == ["hola", "¿Tu nombre?"]


def test_a_failing_commit_turn_leaves_nothing_behind(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.commit_turn("c1", now=T1, state={"s": 1}, extracted={}, outcome="IN_PROGRESS",
                          events=[("consent_given", "")], messages=[(None, "hola")])
    assert store.get("c1") is None
    assert store.events("c1") == []
