"""D84: on the calendar page a recruiter edits their own week and days off (the hiring manager can edit anyone's), sees their
booked calls (or everyone's), and a change that takes away a booked call moves it to another recruiter or releases it."""
from datetime import date, datetime, time, timedelta

import pytest
from streamlit.testing.v1 import AppTest

from sazon.client import SAZON_CALENDAR
from screener.store import Store
from tests.support.dash import book_as_candidate, MANAGER_EMAIL, email_of, login, login_manager, seed_accounts, set_manager
from tests.support.paths import DASHBOARD

APP = str(DASHBOARD)
TODAY = date.today()


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "sazon.db"
    monkeypatch.setenv("SAZON_DB", str(path))
    seed_accounts(None, "Ana", "Luis", available=True)  # their default week: Monday to Friday, 9:00 to 17:00
    return Store(path, calendar=SAZON_CALENDAR)


def opened(name="Ana", language="es"):
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["ui_language"] = language
    at.run()
    login(at, name)
    at.switch_page("views/slots.py").run()
    assert not at.exception, at.exception
    return at


def save_week(at, **changes):
    for key, value in changes.items():
        widget = at.checkbox(key=key) if key.startswith("avail_on_") else at.time_input(key=key)
        widget.set_value(value)
    at.button(key="avail_save").click().run()
    assert not at.exception, at.exception
    return at


def test_a_recruiter_edits_their_week_from_the_default_and_can_go_back_to_it(db):
    at = opened()
    assert [at.checkbox(key=f"avail_on_{d}").value for d in range(7)] == [True] * 5 + [False] * 2  # Monday to Friday...
    assert at.time_input(key="avail_start_0").value == time(9, 0) and at.time_input(key="avail_end_0").value == time(17, 0)
    save_week(at, avail_start_0=time(17, 0), avail_end_0=time(9, 0))  # an end before the start is refused
    assert at.error and not db.is_custom(email_of("Ana"))
    save_week(at, avail_start_0=time(9, 0), avail_end_0=time(17, 0), avail_on_4=False, avail_start_1=time(10, 0),
              avail_end_1=time(12, 0))  # corrected, and their own hours are saved exactly
    assert db.is_custom(email_of("Ana")) and at.success
    assert sorted(db.weekly(email_of("Ana"))) == [(0, 540, 1020), (1, 600, 720), (2, 540, 1020), (3, 540, 1020)]
    at.button(key="avail_reset").click().run()  # and going back to the default
    assert not db.is_custom(email_of("Ana")) and at.checkbox(key="avail_on_4").value is True


def test_a_day_off_is_added_and_taken_back(db):
    at = opened()
    monday = TODAY + timedelta(days=(7 - TODAY.weekday()) % 7 or 7)
    at.date_input(key="off_day").set_value(monday)
    at.button(key="off_add").click().run()
    assert db.days_off(email_of("Ana")) == [monday]
    at.button(key=f"off_remove_{monday.isoformat()}").click().run()
    assert db.days_off(email_of("Ana")) == []


def test_a_change_that_takes_away_a_booked_call_moves_it_to_the_other_recruiter_and_says_so(db):
    now = datetime.now()
    db.commit_turn("c1", now, {"consent": True, "language": "es"}, {"name": "Juan Pérez", "city": "Madrid"}, "QUALIFIED", [], [])
    day = min(db.free_days("ES", now.date(), now.astimezone()))
    first = db.free_slots_on("ES", day, now.astimezone())[0]
    book_as_candidate(db, first.id, "c1")
    owner = db.slot(db.booking_of("c1").slot_id).recruiter
    name = "Ana" if owner == email_of("Ana") else "Luis"
    at = opened(name)
    for day in range(7):  # the whole week off
        at.checkbox(key=f"avail_on_{day}").set_value(False)
    at.button(key="avail_save").click().run()
    assert not at.exception, at.exception
    assert db.booking_of("c1") is not None and db.slot(db.booking_of("c1").slot_id).recruiter != owner
    assert any("1" in str(m.value) and "otro reclutador" in str(m.value) for m in [*at.success, *at.info, *at.warning])


def test_only_the_hiring_manager_can_choose_whose_week_to_edit(db, monkeypatch):
    assert not [s for s in opened().selectbox if s.key == "avail_who"]
    set_manager(monkeypatch)
    at = AppTest.from_file(APP, default_timeout=30).run()
    login_manager(at)
    at.switch_page("views/slots.py").run()
    assert not at.exception, at.exception
    at.selectbox(key="avail_who").select(email_of("Luis")).run()
    at.checkbox(key="avail_on_0").set_value(False)
    at.button(key="avail_save").click().run()
    assert [w[0] for w in db.weekly(email_of("Luis"))] == [1, 2, 3, 4] and not db.is_custom(email_of("Ana"))
    assert [e.actor for e in db.admin_log() if e.action == "availability_changed"] == [MANAGER_EMAIL]


def test_a_recruiter_sees_their_own_calls_by_default_and_everyones_when_they_ask(db):
    now = datetime.now()
    for cid in ("c1", "c2"):
        db.commit_turn(cid, now, {"consent": True}, {"name": f"Persona {cid}", "city": "Madrid"}, "QUALIFIED", [], [])
    day = min(db.free_days("ES", now.date(), now.astimezone()))
    slots = db.free_slots_on("ES", day, now.astimezone())
    book_as_candidate(db, slots[0].id, "c1")
    book_as_candidate(db, slots[0].id, "c2")  # the same minute: one for each recruiter
    at = opened("Ana")
    at.session_state["cal_week"] = day - timedelta(days=day.weekday())
    at.run()
    mine = " ".join(str(m.value) for m in at.markdown)
    at.segmented_control(key="cal_scope").set_value("all").run()
    everyone = " ".join(str(m.value) for m in at.markdown)
    assert mine.count("Persona") == 1 and everyone.count("Persona") == 2
