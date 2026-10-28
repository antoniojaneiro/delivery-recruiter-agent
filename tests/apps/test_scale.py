"""D62: the dashboard stays quick with many candidates: a cheap change counter, a cached list, paged tables."""
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tests.support.paths import DASHBOARD
from sazon.client import SAZON_CALENDAR
from screener import recruiter_view
from screener.model import RecruiterStatus
from screener.store import Store
from tests.support.dash import login, seed_accounts

NOW = datetime(2026, 10, 25, 10, 0)
FUTURE = datetime(2027, 6, 15, 10, 0)
APP = str(DASHBOARD)


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "sazon.db"
    monkeypatch.setenv("SAZON_DB", str(path))
    monkeypatch.setenv("SAZON_ACCOUNTS", str(tmp_path / "recruiters.json"))
    seed_accounts(tmp_path / "recruiters.json")
    return Store(path, calendar=SAZON_CALENDAR)


def add(store, cid, minutes=0, outcome="QUALIFIED"):
    store.commit_turn(cid, NOW + timedelta(minutes=minutes), {}, {"name": f"Persona {cid}", "city": "Madrid"},
                      outcome, [], [("candidate", "hola")])


# --- the change counter ---------------------------------------------------------------------------------------

def test_the_revision_moves_when_anything_a_candidate_list_shows_changes(db):
    seen = [db.revision()]

    def moved(label):
        seen.append(db.revision())
        assert seen[-1] != seen[-2], label

    add(db, "c1"); moved("a new candidate")
    add(db, "c1", 1, "BLOCKED"); moved("a new turn")
    db.set_status("c1", RecruiterStatus.CONTACTED, "Ana", NOW); moved("a status")
    db.assign("c1", "Luis", "Ana", NOW); moved("an assignee")
    slot = db.add_slot("ES", FUTURE, "Ana", "Ana", NOW.astimezone())
    db.book_slot(slot, "c1", NOW.astimezone()); moved("a booking")
    db.cancel_slot(slot, "Ana", NOW.astimezone()); moved("a cancelled booking")
    db.erase_candidate("c1", "recruiter:Ana", NOW, "request"); moved("an erase")


def test_reading_does_not_move_the_revision(db):
    add(db, "c1")
    before = db.revision()
    db.get("c1"); db.list_candidates(); db.messages("c1"); db.events("c1"); db.slots(NOW)
    assert db.revision() == before


def test_a_database_without_the_counter_gets_it_when_opened(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("CREATE TABLE candidates (candidate_id TEXT PRIMARY KEY, state TEXT NOT NULL DEFAULT '{}', "
                      "extracted TEXT NOT NULL DEFAULT '{}', summary TEXT, updated_at TEXT NOT NULL);")
    old.commit(); old.close()
    store = Store(path, calendar=SAZON_CALENDAR)
    before = store.revision()
    add(store, "c1")
    assert store.revision() != before


# --- paging ----------------------------------------------------------------------------------------------------

def test_a_page_is_a_slice_with_the_page_count_and_a_clamped_page_number():
    items = list(range(120))
    assert recruiter_view.page_of(items, 1, 50) == (items[:50], 3, 1)
    assert recruiter_view.page_of(items, 3, 50) == (items[100:], 3, 3)
    assert recruiter_view.page_of(items, 99, 50) == (items[100:], 3, 3)
    assert recruiter_view.page_of(items, 0, 50) == (items[:50], 3, 1)
    assert recruiter_view.page_of([], 1, 50) == ([], 1, 1)


def run():
    at = AppTest.from_file(APP, default_timeout=20).run()
    login(at)
    assert not at.exception, at.exception
    return at


def test_the_table_shows_one_page_and_says_how_many_there_are(db):
    for n in range(120):
        add(db, f"c{n:03d}", n)
    at = run()
    assert len(at.dataframe[0].value) == recruiter_view.PAGE_SIZE
    assert any("1–50 de 120" in str(c.value) for c in at.caption)
    at.number_input(key="page").set_value(3).run()
    assert len(at.dataframe[0].value) == 20
    assert any("101–120 de 120" in str(c.value) for c in at.caption)


def test_the_candidate_list_is_not_read_again_when_nothing_changed_but_is_when_it_did(db, monkeypatch):
    add(db, "c1")
    calls = []
    real = Store.list_candidates

    def counting(self, *args, **kwargs):
        calls.append(1)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Store, "list_candidates", counting)
    at = run()
    first = len(calls)
    at.run()
    assert len(calls) == first                       # same revision: served from the cache
    add(db, "c2", 5)
    at.run()
    assert len(calls) > first and len(at.dataframe[0].value) == 2   # a change shows up


def test_the_pick_a_candidate_list_holds_one_page_not_every_candidate(db):
    for n in range(120):
        add(db, f"c{n:03d}", n)
    at = run()
    assert len(at.selectbox(key="candidate").options) == recruiter_view.PAGE_SIZE
    at.number_input(key="page").set_value(3).run()
    assert len(at.selectbox(key="candidate").options) == 20


def test_a_candidate_from_another_page_stays_pickable_when_a_link_names_it(db):
    for n in range(120):
        add(db, f"c{n:03d}", n)
    at = AppTest.from_file(APP, default_timeout=20)
    at.query_params["candidate"] = "c010"  # the newest first, so c010 is on the third page
    at.run()
    login(at)
    assert not at.exception, at.exception
    options = at.selectbox(key="candidate").options  # (AppTest does not pre-select from the URL, so only the list)
    assert len(options) == recruiter_view.PAGE_SIZE + 1 and "(c010)" in options[-1]
