import sqlite3
from datetime import datetime

import pytest

from sazon.client import SAZON_CALENDAR
from screener.store import Store

T1 = datetime(2026, 10, 25, 10, 0)
T2 = datetime(2026, 10, 25, 10, 5)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "sazon.db", calendar=SAZON_CALENDAR)


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
    turn(Store(tmp_path / "s.db", calendar=SAZON_CALENDAR), extracted={"name": "Ana Ruiz"})
    assert Store(tmp_path / "s.db", calendar=SAZON_CALENDAR).get("c1").extracted == {"name": "Ana Ruiz"}


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


def test_the_store_creates_its_own_folder_so_a_clean_machine_can_start_with_the_dashboard(tmp_path):
    path = tmp_path / "data" / "nested" / "sazon.db"
    turn(Store(path, calendar=SAZON_CALENDAR))
    assert path.exists() and Store(path, calendar=SAZON_CALENDAR).get("c1") is not None


def test_every_timestamp_is_stored_as_naive_local_time_whatever_the_caller_passes(tmp_path):
    from datetime import timezone
    store = Store(tmp_path / "t.db")
    aware = datetime(2026, 10, 25, 10, 0, tzinfo=timezone.utc)
    local = aware.astimezone().replace(tzinfo=None)
    store.commit_turn("c1", aware, {}, {}, "IN_PROGRESS", [("e", "x")], [("agent", "hi")], outbox=["note"])
    store.add_note("c1", "n", "Ana", aware)
    assert store.get("c1").updated_at == local
    assert store.messages("c1")[0].at == local and store.events("c1")[0].at == local
    assert store.notes("c1")[0].at == local
    assert store.outbox_pending()[0].created_at == local


def test_an_old_row_stamped_with_a_time_zone_is_read_as_naive_local_time(tmp_path):
    import sqlite3
    from datetime import timezone
    store = Store(tmp_path / "t.db")
    store.commit_turn("c1", datetime(2026, 10, 25, 10, 0), {}, {}, "IN_PROGRESS", [], [])
    with sqlite3.connect(tmp_path / "t.db") as db:
        db.execute("UPDATE candidates SET updated_at = '2026-10-25T10:00:00+00:00'")
    expected = datetime(2026, 10, 25, 10, 0, tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
    assert store.get("c1").updated_at == expected
