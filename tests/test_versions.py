"""A save is refused when the candidate's record changed or vanished since it was loaded (D53)."""
import sqlite3
from datetime import datetime

import pytest

from sazon.sazon_client import SAZON_CLIENT
from sazon import session, turn
from sazon.store import ConflictError, Store
from tests.fakes import ScriptedLLM

NOW = datetime(2026, 10, 25, 10, 0)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "s.db")


def started(store, cid="c1"):
    turn.start(store, SAZON_CLIENT, cid, NOW)
    turn.handle_message(ScriptedLLM(), store, SAZON_CLIENT, cid, "sí", NOW)


def test_two_copies_of_the_same_candidate_cannot_both_save(store):
    started(store)
    first = session.load(store, "c1", SAZON_CLIENT)
    second = session.load(store, "c1", SAZON_CLIENT)
    first.submit("name", "Juan Pérez", NOW.date())
    session.commit(store, "c1", first, NOW)
    second.submit("name", "Otra Persona", NOW.date())
    with pytest.raises(ConflictError):
        session.commit(store, "c1", second, NOW)
    assert store.get("c1").extracted["name"] == "Juan Pérez"


def test_a_copy_can_save_again_after_it_has_saved(store):
    started(store)
    s = session.load(store, "c1", SAZON_CLIENT)
    s.submit("name", "Juan Pérez", NOW.date())
    session.commit(store, "c1", s, NOW)
    s.submit("experience", (2, ["Glovo"]), NOW.date())
    session.commit(store, "c1", s, NOW)
    assert store.get("c1").extracted["experience"]["years"] == 2


def test_recruiter_actions_and_bookings_do_not_make_a_chat_turn_stale(store):
    started(store)
    s = session.load(store, "c1", SAZON_CLIENT)
    store.set_status("c1", "contacted", "Ana", NOW)
    store.add_note("c1", "llamar", "Ana", NOW)
    slot = store.add_slot("ES", datetime(2027, 6, 15, 10, 0), "Ana", "Ana", NOW.astimezone())
    store.book_slot(slot, "c1", NOW.astimezone())
    s.submit("name", "Juan Pérez", NOW.date())
    session.commit(store, "c1", s, NOW)  # no ConflictError
    assert store.get("c1").extracted["name"] == "Juan Pérez"


def test_a_brand_new_candidate_cannot_be_created_twice_from_two_empty_copies(store):
    a = session.load(store, "fresh", SAZON_CLIENT)
    b = session.load(store, "fresh", SAZON_CLIENT)
    session.commit(store, "fresh", a, NOW)
    with pytest.raises(ConflictError):
        session.commit(store, "fresh", b, NOW)


def test_a_save_after_the_candidate_was_erased_does_not_bring_the_record_back(store):
    started(store)
    s = session.load(store, "c1", SAZON_CLIENT)
    s.submit("name", "Juan Pérez", NOW.date())
    store.erase_candidate("c1", "recruiter:Ana", NOW, "request")
    with pytest.raises(ConflictError):
        session.commit(store, "c1", s, NOW, messages=[("candidate", "Juan Pérez")])
    assert store.get("c1") is None and store.messages("c1") == []


def test_a_chat_turn_that_loses_the_race_apologises_and_changes_nothing(store, monkeypatch):
    started(store)
    competing = {}

    def rival_commits_first(llm, spec, directive, language):  # runs between the load and the save of the turn
        other = session.load(store, "c1", SAZON_CLIENT)
        other.submit("name", "Rival Persona", NOW.date())
        session.commit(store, "c1", other, NOW)
        competing["done"] = True
        return "¿Cómo te llamas?"

    monkeypatch.setattr(turn, "phrase", rival_commits_first)
    reply = turn.handle_message(ScriptedLLM([{"name": "Juan Pérez"}]), store, SAZON_CLIENT, "c1", "Juan Pérez", NOW)
    assert competing and "problema técnico" in reply
    assert store.get("c1").extracted["name"] == "Rival Persona"
    assert all(m.text != "Juan Pérez" for m in store.messages("c1"))


def test_a_candidate_erased_during_a_turn_is_not_recreated_and_starts_fresh_next_time(store, monkeypatch):
    started(store)

    def erase_first(llm, spec, directive, language):
        store.erase_candidate("c1", "recruiter:Ana", NOW, "request")
        return "¿Cómo te llamas?"

    monkeypatch.setattr(turn, "phrase", erase_first)
    reply = turn.handle_message(ScriptedLLM([{"name": "Juan Pérez"}]), store, SAZON_CLIENT, "c1", "Juan Pérez", NOW)
    assert "problema técnico" in reply and store.get("c1") is None
    monkeypatch.undo()
    assert turn.handle_message(ScriptedLLM(), store, SAZON_CLIENT, "c1", "hola", NOW).startswith("Hola, soy el asistente")


def test_a_database_from_before_versions_is_upgraded_in_place(tmp_path):
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.executescript("""CREATE TABLE candidates (candidate_id TEXT PRIMARY KEY, state TEXT NOT NULL DEFAULT '{}',
        extracted TEXT NOT NULL DEFAULT '{}', summary TEXT, outcome TEXT, updated_at TEXT NOT NULL);
        INSERT INTO candidates (candidate_id, updated_at) VALUES ('old1', '2026-10-01T10:00:00');""")
    db.commit()
    db.close()
    store = Store(path)
    s = session.load(store, "old1", SAZON_CLIENT)
    session.commit(store, "old1", s, NOW)
    assert store.get("old1").version == 1
