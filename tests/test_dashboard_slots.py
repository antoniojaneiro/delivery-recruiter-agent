"""The 'Horarios' page and the booking shown on the candidate page (D48)."""
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from sazon.store import Store
from tests.dash import login, logout, seed_accounts

APP = str(Path(__file__).resolve().parent.parent / "dashboard.py")
SLOTS_PAGE = "app_pages/slots.py"
NOW = datetime.now().astimezone()
FUTURE = date.today() + timedelta(days=40)


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "sazon.db"
    monkeypatch.setenv("SAZON_DB", str(path))
    monkeypatch.setenv("SAZON_ACCOUNTS", str(tmp_path / "recruiters.json"))
    seed_accounts(tmp_path / "recruiters.json")
    return Store(path)


def candidate(store, cid, name, city="Madrid", outcome="QUALIFIED"):
    store.commit_turn(cid, NOW, {}, {"name": name, "city": city}, outcome, [], [],
                      summary=f"{name} · {city} · Cualificado")


def run(as_user="Ana"):
    at = AppTest.from_file(APP, default_timeout=10).run()
    login(at, as_user)
    assert not at.exception, at.exception
    return at


def slots_page(at):
    at.switch_page(SLOTS_PAGE).run()
    assert not at.exception, at.exception
    return at


def name_as(at, name="Ana"):
    """Signed in as `name` (the tests start as Ana)."""
    if at.session_state["recruiter"] != name:
        logout(at)
        login(at, name)
    return at


def add_slot(at, when=None, country="ES", recruiter=""):
    when = when or datetime.combine(FUTURE, time(10, 0))
    at.selectbox(key="slot_country").select(country)
    at.date_input(key="slot_date").set_value(when.date())
    at.time_input(key="slot_time").set_value(when.time())
    at.text_input(key="slot_recruiter").set_value(recruiter)
    at.form_submit_button(key="save_slot").click().run()
    assert not at.exception, at.exception


def test_the_slots_page_starts_empty_with_a_hint(db):
    at = slots_page(run())
    assert any("No hay horarios" in str(i.value) for i in at.info)


def test_a_recruiter_can_add_a_slot_in_a_countrys_own_time(db):
    at = name_as(slots_page(run()))
    add_slot(at, datetime.combine(FUTURE, time(9, 30)), "MX", "Luis")
    [slot] = db.slots(NOW)
    assert (slot.country, slot.starts_at, slot.recruiter) == ("MX", datetime.combine(FUTURE, time(9, 30)), "Luis")
    table = at.dataframe[0].value
    assert list(table["País"]) == ["México"] and list(table["Estado"]) == ["Libre"]



@pytest.mark.parametrize("when", [
    datetime.combine(date.today() - timedelta(days=3), time(10, 0)),
    datetime(2027, 3, 28, 2, 30),   # does not exist in Spain: the clocks jump from 02:00 to 03:00
])
def test_a_past_or_impossible_time_is_refused_with_a_clear_message(db, when):
    at = name_as(slots_page(run()))
    add_slot(at, when, "ES")
    assert at.error and db.slots(NOW, include_past=True) == []


def test_the_list_shows_who_booked_each_slot(db):
    candidate(db, "c1", "Juan Pérez")
    free = db.add_slot("ES", datetime.combine(FUTURE, time(10, 0)), "Ana", "Ana", NOW)
    booked = db.add_slot("ES", datetime.combine(FUTURE + timedelta(days=1), time(10, 0)), "Ana", "Ana", NOW)
    db.book_slot(booked, "c1", NOW)
    table = slots_page(run()).dataframe[0].value
    states = dict(zip(table["Id"], table["Estado"]))
    assert states[free] == "Libre" and "Juan Pérez" in states[booked]


def test_cancelling_a_free_slot_removes_it(db):
    slot_id = db.add_slot("ES", datetime.combine(FUTURE, time(10, 0)), "Ana", "Ana", NOW)
    at = name_as(slots_page(run()))
    at.selectbox(key="cancel_slot").select(slot_id)
    at.button(key="confirm_cancel").click().run()
    assert not at.exception, at.exception
    assert db.slots(NOW) == [] and not at.warning


def test_cancelling_a_booked_slot_tells_the_recruiter_to_warn_the_candidate(db):
    candidate(db, "c1", "Juan Pérez")
    slot_id = db.add_slot("ES", datetime.combine(FUTURE, time(10, 0)), "Ana", "Ana", NOW)
    db.book_slot(slot_id, "c1", NOW)
    at = name_as(slots_page(run()))
    at.selectbox(key="cancel_slot").select(slot_id)
    at.button(key="confirm_cancel").click().run()
    assert any("Juan Pérez" in str(w.value) and "aviso" in str(w.value).lower() for w in at.warning)
    assert db.booking_of("c1") is None
    assert "ya no está disponible" in db.outbox_pending("c1")[0].text
    assert [e.actor for e in db.events("c1") if e.type == "slot_cancelled"] == ["recruiter:Ana"]



def test_the_candidate_page_and_table_show_the_booked_call(db):
    candidate(db, "c1", "Juan Pérez")
    candidate(db, "c2", "María García")
    slot_id = db.add_slot("ES", datetime.combine(FUTURE, time(10, 0)), "Ana", "Ana", NOW)
    db.book_slot(slot_id, "c1", NOW)
    at = run()
    table = at.dataframe[0].value
    assert dict(zip(table["Id"], table["Llamada"]))["c2"] == ""
    assert "(España)" in dict(zip(table["Id"], table["Llamada"]))["c1"]
    assert {m.label: m.value for m in at.metric}["Cualificados por contactar"] == "1"
    at.selectbox(key="candidate").select("c1").run()
    assert any("Llamada" in str(e.value) and "10:00" in str(e.value) for e in [*at.markdown, *at.text])
    at.selectbox(key="candidate").select("c2").run()
    assert any("Sin llamada reservada" in str(e.value) for e in [*at.markdown, *at.text, *at.caption])
