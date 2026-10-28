"""D78: the funnel page shows how far candidates get through the whole process (the agent's screening and then the
recruiter's steps), how many are still in it, and, below, the path one chosen candidate has taken and what is left."""
from datetime import date, datetime

import pytest
from streamlit.testing.v1 import AppTest

from sazon.client import SAZON_CALENDAR, SAZON_CLIENT
from sazon.spec import SAZON
from screener.model import RecruiterStatus as S
from screener.screening import Screening
from screener.store import Store
from tests.support.dash import login, seed_accounts
from tests.support.paths import DASHBOARD

NOW = datetime(2026, 10, 25, 10, 0)
TODAY = date(2026, 10, 25)
APP = str(DASHBOARD)
ANSWERS = {"name": "Juan Pérez", "experience": (2, ["glovo"]), "availability": ["full_time"], "schedule": "morning",
           "start_date": date(2026, 11, 1), "city": "Madrid", "license": True}


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "sazon.db"
    monkeypatch.setenv("SAZON_DB", str(path))
    monkeypatch.setenv("SAZON_ACCOUNTS", str(tmp_path / "recruiters.json"))
    seed_accounts(tmp_path / "recruiters.json")
    return Store(path, calendar=SAZON_CALENDAR)


def add(store, cid, outcome, *fields, reasons=(), consent=True):
    s = Screening(SAZON_CLIENT.areas, SAZON)
    s.record_consent(consent)
    for field in fields:
        s.submit(field, ANSWERS[field], TODAY)
    store.commit_turn(cid, NOW, s.to_state(), s.extracted(), outcome, [], [], reasons=list(reasons))


def populate(store):
    add(store, "new1", "IN_PROGRESS", "name")                                         # in process
    add(store, "stall", "STALLED", "name", "experience")                              # paused
    add(store, "nolic", "DISQUALIFIED", *list(ANSWERS)[:-1], reasons=["NO_LICENSE"])  # out
    add(store, "done", "QUALIFIED", *ANSWERS)                                         # hired
    store.set_status("done", S.CONTACTED, "Ana", NOW)
    store.set_status("done", S.HIRED, "Ana", NOW)
    add(store, "talk", "QUALIFIED", *ANSWERS)                                         # in process, contacted
    store.set_status("talk", S.CONTACTED, "Ana", NOW)
    add(store, "lost", "QUALIFIED", *ANSWERS)                                         # contacted, then rejected: out
    store.set_status("lost", S.CONTACTED, "Ana", NOW)
    store.set_status("lost", S.REJECTED, "Ana", NOW)


def opened(language="es"):
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["ui_language"] = language
    at.run()
    login(at)
    at.switch_page("views/funnel.py").run()
    assert not at.exception, at.exception
    return at


def metric(at, label):
    return next(m.value for m in at.metric if m.label == label)


def test_the_funnel_says_how_many_are_in_the_process_paused_out_and_how_many_went_through_all_of_it(db):
    populate(db)
    at = opened()
    assert [metric(at, label) for label in ("En proceso", "En pausa", "Fuera del proceso", "Recorrieron todo el proceso")] ==         ["2", "1", "2", "1"]


def test_the_chart_table_has_the_recruiters_steps_after_the_agents(db):
    populate(db)
    at = opened()
    rows = [list(row) for frame in at.dataframe for row in frame.value.values.tolist()]
    names = [row[0] for row in rows]
    assert names.index("Cualificaron") < names.index("Contactado") < names.index("Entrevista programada") < names.index("Contratado")
    assert dict(rows)["Contactado"] == 3 and dict(rows)["Contratado"] == 1


def test_a_chosen_candidate_shows_the_steps_done_and_the_ones_left(db):
    populate(db)
    at = opened()
    at.selectbox(key="path_candidate").select("talk").run()
    assert not at.exception, at.exception
    text = " ".join(str(m.value) for m in at.markdown)
    assert "En proceso" in text and "check_circle" in text and "radio_button_unchecked" in text
    steps = [line for m in at.markdown for line in str(m.value).split("\n")]  # one line per step
    assert any("Nombre" in line and "check_circle" in line for line in steps)  # a step starts with a capital
    assert any("Contactado" in line and "check_circle" in line for line in steps)
    assert any("Entrevista programada" in line and "ahora" in line for line in steps)  # the next step to happen
    assert any("Contratado" in line and "radio_button_unchecked" in line for line in steps)  # still ahead


def test_a_candidate_who_is_out_shows_where_and_why_they_stopped(db):
    populate(db)
    at = opened()
    at.selectbox(key="path_candidate").select("nolic").run()
    text = " ".join(str(m.value) for m in at.markdown)
    assert "Fuera del proceso" in text
    assert any("se detuvo aquí" in str(m.value) for m in at.markdown)
    assert "licencia" in text.lower()


def test_the_picker_holds_a_short_list_that_a_search_narrows(db):
    for n in range(120):
        add(db, f"c{n:03d}", "IN_PROGRESS", "name")
    at = opened()
    assert len(at.selectbox(key="path_candidate").options) <= 20
    at.text_input(key="path_search").set_value("c042").run()
    assert any("c042" in option for option in at.selectbox(key="path_candidate").options)


def test_the_page_is_in_english_when_the_recruiter_picks_english(db):
    populate(db)
    at = opened("en")
    assert metric(at, "In process") == "2" and metric(at, "Went through the whole process") == "1"
    at.selectbox(key="path_candidate").select("talk").run()
    assert not at.exception, at.exception
    text = " ".join(str(m.value) for m in at.markdown)
    assert "Interview scheduled" in text and "En proceso" not in text


def test_the_whole_process_number_and_the_charts_last_bar_are_the_same_even_after_a_later_change(db):
    populate(db)
    db.set_status("done", S.REJECTED, "Ana", NOW)  # hired, then the recruiter changed their mind
    at = opened()
    assert metric(at, "Recorrieron todo el proceso") == "1"  # they did go through all of it
    rows = dict(row for frame in at.dataframe for row in frame.value.values.tolist())
    assert rows["Contratado"] == 1
