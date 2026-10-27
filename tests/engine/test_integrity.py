"""Found by the architecture review: races, migrations, erasure and the reminder job's edge cases (D61)."""
import sqlite3
import threading
import time
from datetime import datetime, timedelta

import pytest

from sazon.spec import SAZON
from sazon.client import SAZON_CALENDAR, SAZON_CLIENT
from screener import reminders, session, slot_flow, turn
from screener.phrasing import consent_message
from screener.store import ConflictError, Store
from tests.support.fakes import ScriptedLLM

NOW = datetime(2026, 10, 25, 10, 0)
HOUR = timedelta(hours=1)


@pytest.fixture
def path(tmp_path):
    return tmp_path / "s.db"


@pytest.fixture
def store(path):
    return Store(path, calendar=SAZON_CALENDAR)


def started(store, cid="c1"):
    turn.start(store, SAZON_CLIENT, cid, NOW)
    turn.handle_message(ScriptedLLM(), store, SAZON_CLIENT, cid, "sí", NOW)


# --- the version is checked while holding the write lock -------------------------------------------------------

def test_a_save_that_waits_for_another_writer_notices_it_was_overtaken(store, path):
    started(store)
    stale = session.load(store, "c1", SAZON_CLIENT)
    stale.submit("name", "Juan Pérez", NOW.date())

    rival = sqlite3.connect(path, timeout=10)
    rival.execute("BEGIN IMMEDIATE")  # another process is in the middle of saving this candidate
    rival.execute("UPDATE candidates SET version = version + 1, summary = 'RIVAL' WHERE candidate_id = 'c1'")
    outcome = {}

    def save():
        try:
            session.commit(store, "c1", stale, NOW)
            outcome["result"] = "saved"
        except ConflictError:
            outcome["result"] = "conflict"

    thread = threading.Thread(target=save)
    thread.start()
    time.sleep(0.4)           # the save is now waiting for the lock...
    rival.commit()            # ...and the rival finishes first
    rival.close()
    thread.join(timeout=15)
    assert outcome["result"] == "conflict"
    assert store.get("c1").summary == "RIVAL" and "name" not in store.get("c1").extracted


# --- old databases open ---------------------------------------------------------------------------------------------

def test_a_database_from_the_first_release_opens_and_keeps_its_data(tmp_path):
    path = tmp_path / "first.db"
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE candidates (candidate_id TEXT PRIMARY KEY, state TEXT NOT NULL DEFAULT '{}',
            extracted TEXT NOT NULL DEFAULT '{}', summary TEXT, updated_at TEXT NOT NULL);
        CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id TEXT NOT NULL, type TEXT NOT NULL,
            detail TEXT NOT NULL, at TEXT NOT NULL);
        CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id TEXT NOT NULL, role TEXT NOT NULL,
            text TEXT NOT NULL, at TEXT NOT NULL);
        INSERT INTO candidates (candidate_id, extracted, updated_at) VALUES ('old1', '{"name": "Ana Ruiz"}', '2026-10-01T10:00:00');
        INSERT INTO messages (candidate_id, role, text, at) VALUES ('old1', 'candidate', 'hola', '2026-10-01T10:00:00');
    """)
    db.commit()
    db.close()
    store = Store(path, calendar=SAZON_CALENDAR)
    record = store.get("old1")
    assert record.extracted == {"name": "Ana Ruiz"} and record.outcome is None and record.version == 0
    assert [m.text for m in store.messages("old1")] == ["hola"]
    db = sqlite3.connect(path)
    names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    db.close()
    assert "idx_candidates_outcome" in names
    store.commit_turn("old1", NOW, {}, {"name": "Ana Ruiz"}, "IN_PROGRESS", [], [], expected_version=0)
    assert store.get("old1").outcome == "IN_PROGRESS"


def test_opening_the_same_old_database_twice_at_once_does_not_crash(tmp_path):
    path = tmp_path / "first.db"
    db = sqlite3.connect(path)
    db.executescript("CREATE TABLE candidates (candidate_id TEXT PRIMARY KEY, state TEXT NOT NULL DEFAULT '{}', "
                     "extracted TEXT NOT NULL DEFAULT '{}', summary TEXT, updated_at TEXT NOT NULL);")
    db.commit()
    db.close()
    errors = []

    def open_it():
        try:
            Store(path, calendar=SAZON_CALENDAR)
        except Exception as error:  # noqa: BLE001
            errors.append(error)

    threads = [threading.Thread(target=open_it) for _ in range(4)]
    [t.start() for t in threads]
    [t.join(timeout=20) for t in threads]
    assert errors == []


# --- erasure --------------------------------------------------------------------------------------------------------------

def test_a_booking_for_a_candidate_who_was_just_erased_is_refused(store):
    started(store)
    slot = store.add_slot("ES", datetime(2027, 6, 15, 10, 0), "Ana", "Ana", NOW.astimezone())
    store.erase_candidate("c1", "recruiter:Ana", NOW, "request")
    assert store.book_slot(slot, "c1", NOW.astimezone(), must_exist=True) is None
    assert store.booking_of("c1") is None and [e for e in store.events("c1")] == []


def test_a_chat_message_for_an_unknown_candidate_shows_the_disclosure_instead_of_being_read_as_consent(store):
    reply = turn.handle_message(ScriptedLLM(), store, SAZON_CLIENT, "never-started", "sí", NOW)
    assert reply == consent_message(SAZON)
    assert store.get("never-started").state["consent"] is None


def test_after_an_erase_the_same_chat_starts_over_with_the_disclosure(store):
    started(store)
    store.erase_candidate("c1", "recruiter:Ana", NOW, "request")
    reply = turn.handle_message(ScriptedLLM(), store, SAZON_CLIENT, "c1", "sí", NOW)
    assert reply == consent_message(SAZON) and store.get("c1").state["consent"] is None


def test_the_erase_says_in_the_log_whether_the_log_file_was_really_emptied(store, monkeypatch):
    started(store)
    store.erase_candidate("c1", "recruiter:Ana", NOW, "request")
    assert "checkpoint=complete" in store.admin_log()[-1].detail
    started(store, "c2")
    monkeypatch.setattr(Store, "_checkpoint", lambda self: False)
    store.erase_candidate("c2", "recruiter:Ana", NOW, "request")
    assert "checkpoint=incomplete" in store.admin_log()[-1].detail


# --- a turn that loses a race is retried once, not lost -------------------------------------------------------------------

def test_a_turn_that_meets_a_conflict_is_run_again_so_the_candidates_message_is_not_lost(store, monkeypatch):
    started(store)
    real = session.commit
    calls = {"n": 0}

    def commit_once_conflicting(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConflictError("c1")
        return real(*args, **kwargs)

    monkeypatch.setattr(turn.session, "commit", commit_once_conflicting)
    reply = turn.handle_message(ScriptedLLM([{"name": "Juan Pérez"}, {"name": "Juan Pérez"}]), store, SAZON_CLIENT,
                                "c1", "Juan Pérez", NOW)
    assert "problema técnico" not in reply and store.get("c1").extracted["name"] == "Juan Pérez"
    assert [m.text for m in store.messages("c1")].count("Juan Pérez") == 1


def test_a_turn_that_keeps_conflicting_gives_the_technical_problem_message(store, monkeypatch):
    started(store)

    def always(*args, **kwargs):
        raise ConflictError("c1")

    monkeypatch.setattr(turn.session, "commit", always)
    reply = turn.handle_message(ScriptedLLM([{"name": "Juan Pérez"}, {"name": "Juan Pérez"}]), store, SAZON_CLIENT,
                                "c1", "Juan Pérez", NOW)
    assert "problema técnico" in reply


# --- the reminder job -------------------------------------------------------------------------------------------------------

def test_a_candidate_who_wrote_while_the_job_was_running_is_not_reminded(store, monkeypatch):
    started(store)
    monkeypatch.setattr(Store, "last_activity", lambda self: {"c1": NOW})  # the job's snapshot is old
    store_msg_time = NOW + 25 * HOUR - timedelta(minutes=5)
    turn.handle_message(ScriptedLLM([{"name": "Juan Pérez"}]), store, SAZON_CLIENT, "c1", "Juan Pérez", store_msg_time)
    assert reminders.run_once(store, SAZON_CLIENT, NOW + 25 * HOUR) == []
    assert store.outbox_pending() == []


def test_one_broken_candidate_does_not_stop_the_job_for_the_others(store, monkeypatch):
    started(store, "c1")
    started(store, "c2")
    real = session.load

    def load(store_, cid, areas):
        if cid == "c1":
            raise ValueError("corrupt row")
        return real(store_, cid, areas)

    monkeypatch.setattr(session, "load", load)
    actions = reminders.run_once(store, SAZON_CLIENT, NOW + 24 * HOUR)
    assert {(a.candidate_id, a.kind) for a in actions} == {("c1", "error"), ("c2", "reminder")}
    assert [e.candidate_id for e in store.outbox_pending()] == ["c2"]


# --- telling a candidate their booking was cancelled ------------------------------------------------------------------------

def test_a_cancelled_booking_queues_a_message_for_the_candidate_in_their_language(store):
    from tests.support.booking import add_slots, qualify
    add_slots(store)
    qualify(store)
    turn.handle_message(ScriptedLLM(), store, SAZON_CLIENT, "c1", "1", NOW)
    slot = store.booking_of("c1").slot_id
    candidate = store.cancel_slot(slot, "Ana", NOW.astimezone())
    assert slot_flow.notify_cancelled(store, SAZON_CLIENT, candidate, NOW) is True
    [entry] = store.outbox_pending("c1")
    assert "ya no está disponible" in entry.text and "reclutador" in entry.text
    assert store.messages("c1")[-1].text == entry.text


def test_notifying_a_candidate_who_was_erased_does_nothing(store):
    started(store)
    store.erase_candidate("c1", "recruiter:Ana", NOW, "request")
    assert slot_flow.notify_cancelled(store, SAZON_CLIENT, "c1", NOW) is False
    assert store.outbox_pending() == []
