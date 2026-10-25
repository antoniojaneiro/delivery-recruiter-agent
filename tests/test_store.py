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
    store.save("c1", state={"outcome": "QUALIFIED"}, now=T1)
    store.save("c2", state={"outcome": "DISQUALIFIED"}, now=T1)
    assert [r.candidate_id for r in store.list_candidates(outcome="QUALIFIED")] == ["c1"]
    assert {r.candidate_id for r in store.list_candidates()} == {"c1", "c2"}
