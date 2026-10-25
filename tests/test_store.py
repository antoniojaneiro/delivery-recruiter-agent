import sqlite3
from datetime import datetime

import pytest

from sazon.store import Store

T1 = datetime(2026, 10, 25, 10, 0)
T2 = datetime(2026, 10, 25, 10, 5)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "sazon.db")


def turn(store, cid="c1", now=T1, state=None, extracted=None, outcome="IN_PROGRESS", events=(), messages=()):
    store.commit_turn(cid, now, state or {}, extracted or {}, outcome, list(events), list(messages))


def test_unknown_candidate_returns_none(store):
    assert store.get("nope") is None


def test_state_extracted_json_and_outcome_are_stored_separately(store):
    turn(store, state={"stage": "name"}, extracted={"name": "Juan Pérez"}, outcome="QUALIFIED", now=T2)
    record = store.get("c1")
    assert record.state == {"stage": "name"}
    assert record.extracted == {"name": "Juan Pérez"}
    assert (record.outcome, record.updated_at, record.summary) == ("QUALIFIED", T2, None)


def test_a_later_turn_replaces_the_state_but_keeps_earlier_history(store):
    turn(store, state={"n": 1}, events=[("a", "")], messages=[("agent", "hola")], now=T1)
    turn(store, state={"n": 2}, events=[("b", "x")], messages=[("candidate", "qué tal")], now=T2)
    assert store.get("c1").state == {"n": 2}
    assert [(e.type, e.detail, e.at) for e in store.events("c1")] == [("a", "", T1), ("b", "x", T2)]
    assert [(m.role, m.text, m.at) for m in store.messages("c1")] == [
        ("agent", "hola", T1), ("candidate", "qué tal", T2)]


def test_data_survives_reopening_the_database(tmp_path):
    turn(Store(tmp_path / "s.db"), extracted={"name": "Ana Ruiz"})
    assert Store(tmp_path / "s.db").get("c1").extracted == {"name": "Ana Ruiz"}


def test_events_and_messages_of_other_candidates_are_not_mixed(store):
    turn(store, "c1", events=[("a", "")], messages=[("candidate", "uno")])
    turn(store, "c2", events=[("b", "")], messages=[("candidate", "dos")])
    assert [e.type for e in store.events("c2")] == ["b"]
    assert [m.text for m in store.messages("c2")] == ["dos"]


def test_list_candidates_filters_by_outcome_newest_first(store):
    turn(store, "c1", outcome="QUALIFIED", now=T1)
    turn(store, "c2", outcome="DISQUALIFIED", now=T1)
    turn(store, "c3", outcome="QUALIFIED", now=T2)
    assert [r.candidate_id for r in store.list_candidates(outcome="QUALIFIED")] == ["c3", "c1"]
    assert {r.candidate_id for r in store.list_candidates()} == {"c1", "c2", "c3"}


def test_a_failing_turn_leaves_nothing_behind(store):
    with pytest.raises(sqlite3.IntegrityError):
        turn(store, events=[("consent_given", "")], messages=[(None, "hola")])
    assert store.get("c1") is None
    assert store.events("c1") == []


def test_the_summary_is_saved_with_the_turn_and_kept_when_a_later_turn_has_none(store):
    store.commit_turn("c1", T1, {}, {}, "QUALIFIED", [], [], summary="Cualificado en Madrid.")
    assert store.get("c1").summary == "Cualificado en Madrid."
    turn(store, outcome="QUALIFIED", now=T2)
    assert store.get("c1").summary == "Cualificado en Madrid."
    store.commit_turn("c1", T2, {}, {}, "QUALIFIED", [], [], summary="Actualizado.")
    assert store.get("c1").summary == "Actualizado."
