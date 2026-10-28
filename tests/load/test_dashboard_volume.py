"""D76: the dashboard with 5,000 fictional candidates, made by cloning one real candidate with SQL (a thousand real
turns would take a minute of disk writes). The threshold was set before measuring: a rerun of the candidates page
under one second, and a pick-a-candidate list that holds one page, not 5,000 entries.

Run on its own: `python -m pytest -m load -q -s tests/load/test_dashboard_volume.py`."""
import sqlite3
import time
from datetime import datetime, timedelta

import pytest
from streamlit.testing.v1 import AppTest

from sazon.client import SAZON_CLIENT
from screener.recruiter_view import PAGE_SIZE
from screener.store import Store
from tests.support.booking import qualify
from tests.support.dash import login, seed_accounts
from tests.support.paths import DASHBOARD

pytestmark = pytest.mark.load

CANDIDATES = 5000
RERUN_SECONDS = 1.0


@pytest.fixture
def big_database(tmp_path, monkeypatch):
    path = tmp_path / "sazon.db"
    monkeypatch.setenv("SAZON_DB", str(path))
    monkeypatch.setenv("SAZON_ACCOUNTS", str(tmp_path / "recruiters.json"))
    seed_accounts(tmp_path / "recruiters.json")
    store = Store(path, calendar=SAZON_CLIENT.calendar)
    qualify(store, cid="seed0")
    with sqlite3.connect(path) as db:
        for n in range(1, CANDIDATES):
            cid = f"seed{n}"
            db.execute("INSERT INTO candidates SELECT ?, state, extracted, summary, outcome, reasons, flags, version, "
                       "updated_at FROM candidates WHERE candidate_id = 'seed0'", (cid,))
            db.execute("INSERT INTO messages (candidate_id, role, text, at) SELECT ?, role, text, at FROM messages "
                       "WHERE candidate_id = 'seed0'", (cid,))
            db.execute("INSERT INTO events (candidate_id, type, detail, actor, at) SELECT ?, type, detail, actor, at "
                       "FROM events WHERE candidate_id = 'seed0'", (cid,))
    return store


def timed(run):
    started = time.perf_counter()
    run()
    return time.perf_counter() - started


def test_the_candidates_page_stays_quick_with_five_thousand_candidates(big_database):
    at = AppTest.from_file(str(DASHBOARD), default_timeout=120).run()
    login(at)
    assert not at.exception, at.exception
    assert len(at.selectbox(key="candidate").options) == PAGE_SIZE  # one page goes to the browser, not 5,000

    rerun = timed(at.run)
    search = timed(lambda: at.text_input(key="f_search").set_value("juan").run())
    print(f"\nrerun {rerun * 1000:.0f} ms, rerun after a search {search * 1000:.0f} ms, {CANDIDATES} candidates")
    assert not at.exception, at.exception
    assert rerun < RERUN_SECONDS and search < RERUN_SECONDS


@pytest.mark.parametrize("page", ["views/funnel.py", "views/slots.py"])
def test_the_funnel_and_the_calendar_stay_quick_with_five_thousand_candidates(big_database, page):
    now = datetime.now().astimezone()
    for day in range(1, 31):  # 300 call times over a month, a third of them booked (the list shows each booked name)
        for hour in range(9, 14):
            for country in ("ES", "MX"):
                at_time = (datetime.now() + timedelta(days=day)).replace(hour=hour, minute=0, second=0, microsecond=0)
                slot_id = big_database.add_slot(country, at_time, f"Ana {country}", "Ana", now)
                if day % 3 == 0:
                    big_database.book_slot(slot_id, f"seed{day * 10 + hour}", now)
    at = AppTest.from_file(str(DASHBOARD), default_timeout=120).run()
    login(at)
    at.switch_page(page).run()  # the first visit loads the charting library and the candidate list
    assert not at.exception, at.exception
    again = timed(at.run)
    print(f"\n{page}: a rerun takes {again * 1000:.0f} ms with {CANDIDATES} candidates")
    assert not at.exception, at.exception
    assert again < RERUN_SECONDS
    if page.endswith("slots.py"):  # 300 call times were added over a month: the cancel list holds one week of them, not all
        assert len(at.selectbox(key="cancel_slot").options) <= 40
