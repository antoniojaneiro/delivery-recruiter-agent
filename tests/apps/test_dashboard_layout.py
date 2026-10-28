"""D77: the candidates page is one column of full-width parts: the filters, then the table (it grows with the number
of rows up to a height, then scrolls inside itself), then the chosen candidate's details below."""
from datetime import datetime, timedelta

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from sazon.client import SAZON_CALENDAR
from screener import recruiter_view
from screener.recruiter_view import PAGE_SIZE, TABLE_MAX_ROWS, table_height
from screener.store import Store
from tests.support.dash import login, seed_accounts
from tests.support.paths import DASHBOARD

NOW = datetime(2026, 10, 25, 10, 0)
APP = str(DASHBOARD)


def test_the_table_is_as_tall_as_its_rows_until_the_cap_and_then_stays_that_tall():
    heights = [table_height(n) for n in range(0, TABLE_MAX_ROWS + 3)]
    assert heights[0] < heights[1] < heights[TABLE_MAX_ROWS]          # grows with every row...
    assert heights[TABLE_MAX_ROWS] == heights[TABLE_MAX_ROWS + 1] == heights[TABLE_MAX_ROWS + 2]  # ...then it scrolls
    assert table_height(PAGE_SIZE) == table_height(TABLE_MAX_ROWS)
    steps = {heights[i + 1] - heights[i] for i in range(1, TABLE_MAX_ROWS)}
    assert len(steps) == 1                                            # one row is always the same height


@pytest.fixture
def make(tmp_path, monkeypatch):
    path = tmp_path / "sazon.db"
    monkeypatch.setenv("SAZON_DB", str(path))
    monkeypatch.setenv("SAZON_ACCOUNTS", str(tmp_path / "recruiters.json"))
    seed_accounts(tmp_path / "recruiters.json")
    store = Store(path, calendar=SAZON_CALENDAR)

    def add(count):
        for n in range(count):
            store.commit_turn(f"c{n:03d}", NOW + timedelta(minutes=n), {}, {"name": f"Persona {n}", "city": "Madrid"},
                              "QUALIFIED", [], [("candidate", "hola")])
        return store
    return add


@pytest.fixture
def tables(monkeypatch):
    """The heights the page asks for when it draws a table (the test tool cannot read them back)."""
    asked = []
    real = st.dataframe

    def spy(*args, **kwargs):
        asked.append(kwargs.get("height"))
        return real(*args, **kwargs)

    monkeypatch.setattr(st, "dataframe", spy)
    return asked


def opened():
    at = AppTest.from_file(APP, default_timeout=30).run()
    login(at)
    assert not at.exception, at.exception
    return at


@pytest.mark.parametrize("count", [1, 4, 9])
def test_a_short_list_gets_a_table_just_tall_enough_for_its_rows(make, tables, count):
    make(count)
    opened()
    assert tables[0] == table_height(count)


def test_a_long_list_gets_the_capped_height_so_the_table_scrolls(make, tables):
    make(120)
    opened()
    assert tables[0] == table_height(TABLE_MAX_ROWS) and table_height(TABLE_MAX_ROWS) < table_height(PAGE_SIZE) + 1


def test_the_table_does_not_share_the_row_with_the_details(make):
    store = make(3)
    at = opened()
    at.selectbox(key="candidate").select("c001").run()
    assert not at.exception, at.exception
    assert all(not column.dataframe for column in at.columns)  # no table sits in a column beside the details
    assert at.subheader and at.text_area(key="note")           # the details are on the page, below


def test_the_filters_and_the_table_come_before_the_details(make):
    make(3)
    at = opened()
    at.selectbox(key="candidate").select("c001").run()
    order = [type(e).__name__ for e in at.main]
    assert order.index("Multiselect") < order.index("Dataframe") < order.index("Subheader")
