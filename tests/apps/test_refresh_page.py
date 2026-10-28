"""The candidates page watches the database: it reloads itself when nothing is open, and only offers the update when a
recruiter has a candidate open. A timer cannot be run in a test, so the counter is faked to change during one run."""
from datetime import datetime

import pytest
from streamlit.testing.v1 import AppTest

from sazon.client import SAZON_CALENDAR
from screener.store import Store
from tests.support.dash import login, seed_accounts
from tests.support.paths import DASHBOARD

NOW = datetime(2026, 10, 25, 10, 0)


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "sazon.db"
    monkeypatch.setenv("SAZON_DB", str(path))
    monkeypatch.setenv("SAZON_ACCOUNTS", str(tmp_path / "recruiters.json"))
    seed_accounts(tmp_path / "recruiters.json")
    store = Store(path, calendar=SAZON_CALENDAR)
    store.commit_turn("c1", NOW, {}, {"name": "Juan Pérez", "city": "Madrid"}, "QUALIFIED", [], [("candidate", "hola")])
    return store


def opened():
    at = AppTest.from_file(str(DASHBOARD), default_timeout=20).run()
    login(at)
    assert not at.exception, at.exception
    return at


def revisions(monkeypatch, *values):
    """The change counter returns these in turn, then keeps the last."""
    seq = list(values)
    monkeypatch.setattr(Store, "revision", lambda self: seq.pop(0) if len(seq) > 1 else seq[0])


def test_the_page_notes_the_revision_its_list_was_drawn_at(db):
    at = opened()
    assert at.session_state["_seen_revision"] == db.revision()


def test_with_no_candidate_open_a_change_reloads_the_page_by_itself(db, monkeypatch):
    reads = []
    real = Store.list_candidates
    monkeypatch.setattr(Store, "list_candidates", lambda self, *a, **k: (reads.append(1), real(self, *a, **k))[1])
    at = opened()
    before = len(reads)
    revisions(monkeypatch, 100, 101, 101)  # drawn at 100; the watcher then sees 101
    at.run()
    assert not at.exception and len(reads) == before + 2  # one list for revision 100, one more after the reload
    assert at.session_state["_seen_revision"] == 101


def test_with_a_candidate_open_a_change_is_only_offered_and_the_page_is_not_reloaded(db, monkeypatch):
    reads = []
    real = Store.list_candidates
    monkeypatch.setattr(Store, "list_candidates", lambda self, *a, **k: (reads.append(1), real(self, *a, **k))[1])
    at = opened()
    at.selectbox(key="candidate").select("c1").run()
    before = len(reads)
    revisions(monkeypatch, 200, 201, 201)
    at.run()
    assert not at.exception and len(reads) == before + 1  # the list is not reloaded, so a draft in the form is untouched
    assert at.button(key="load_updates")  # the offer is there
    at.button(key="load_updates").click().run()
    assert not at.exception


def test_without_a_change_nothing_is_offered(db):
    at = opened()
    at.selectbox(key="candidate").select("c1").run()
    assert not [b for b in at.button if b.key == "load_updates"]
