"""D79: the call-times page is a calendar: a week grid per country, and a form to organise a call for a candidate (only the
candidates a call can be organised for), which books or moves the call, tells the candidate and logs it."""
from datetime import date, datetime, timedelta

import pytest
from streamlit.testing.v1 import AppTest

from sazon.client import SAZON_CALENDAR
from screener.calendar_view import week_start
from screener.model import RecruiterStatus as S
from screener.store import Store
from tests.support.dash import login, seed_accounts
from tests.support.paths import DASHBOARD

NOW = datetime(2026, 10, 25, 10, 0)
TUESDAY = datetime(2027, 6, 15, 10, 0)
MONDAY = week_start(TUESDAY.date())
APP = str(DASHBOARD)


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "sazon.db"
    monkeypatch.setenv("SAZON_DB", str(path))
    monkeypatch.setenv("SAZON_ACCOUNTS", str(tmp_path / "recruiters.json"))
    seed_accounts(tmp_path / "recruiters.json")
    return Store(path, calendar=SAZON_CALENDAR)


def add(store, cid, city, outcome="QUALIFIED", name=None):
    store.commit_turn(cid, NOW, {"consent": True, "language": "es"}, {"name": name or f"Persona {cid}", "city": city},
                      outcome, [], [("agent", "hola")])


def slot(store, country, when):
    return store.add_slot(country, when, "Ana", "Ana", NOW.astimezone())


def opened(language="es", week=MONDAY):
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["ui_language"] = language
    at.session_state["cal_week"] = week
    at.run()
    login(at)
    at.switch_page("views/slots.py").run()
    assert not at.exception, at.exception
    return at


def chips(at):
    return " ".join(str(m.value) for m in at.markdown)


# --- the grid ----------------------------------------------------------------------------------------------------------

def test_the_week_grid_shows_free_and_booked_times_of_the_chosen_country(db):
    add(db, "c1", "Madrid", name="Juan Pérez")
    free = slot(db, "ES", TUESDAY)
    booked = slot(db, "ES", TUESDAY.replace(hour=16))
    db.book_slot(booked, "c1", NOW.astimezone())
    slot(db, "MX", TUESDAY)
    text = chips(opened())
    assert ":green-badge[10:00]" in text and "16:00 · Juan Pérez" in text
    assert text.count("10:00") == 1  # the Mexican 10:00 is not in the Spanish grid


def test_the_other_country_has_its_own_grid_in_its_own_clock(db):
    slot(db, "ES", TUESDAY)
    slot(db, "MX", TUESDAY.replace(hour=9, minute=30))
    at = opened()
    at.segmented_control(key="cal_country").set_value("MX").run()
    text = chips(at)
    assert "09:30" in text and "10:00" not in text


def test_the_week_buttons_move_the_grid_and_today_brings_it_back(db):
    slot(db, "ES", TUESDAY)
    at = opened()
    assert "10:00" in chips(at)
    at.button(key="week_next").click().run()
    assert at.session_state["cal_week"] == MONDAY + timedelta(days=7) and "10:00" not in chips(at)
    at.button(key="week_prev").click().run()
    at.button(key="week_prev").click().run()
    assert at.session_state["cal_week"] == MONDAY - timedelta(days=7)
    at.button(key="week_today").click().run()
    assert at.session_state["cal_week"] == week_start(date.today())


def test_an_empty_week_says_so_and_a_page_with_no_times_keeps_its_hint(db):
    at = opened()
    assert any("No hay horarios" in str(i.value) for i in at.info)


# --- organising a call -------------------------------------------------------------------------------------------------

def schedule_picker(at):
    return at.selectbox(key="sched_candidate")


def test_only_candidates_a_call_can_be_organised_for_can_be_picked(db):
    add(db, "c1", "Madrid")
    add(db, "c2", "Guadalajara")
    add(db, "c3", "Madrid", outcome="DISQUALIFIED")
    add(db, "c4", "Madrid")
    db.set_status("c4", S.HIRED, "Ana", NOW)
    add(db, "c5", "Madrid")
    db.set_status("c5", S.REJECTED, "Ana", NOW)
    add(db, "c6", "Madrid", outcome="STALLED")
    slot(db, "ES", TUESDAY)
    options = schedule_picker(opened()).options
    assert sorted(o.split("(")[-1].split(")")[0] for o in options) == ["c1", "c2"]


def test_the_candidate_picker_is_short_and_a_search_narrows_it(db):
    for n in range(120):
        add(db, f"c{n:03d}", "Madrid")
    slot(db, "ES", TUESDAY)
    at = opened()
    assert len(schedule_picker(at).options) <= 20
    at.text_input(key="sched_search").set_value("c077").run()
    assert any("c077" in option for option in schedule_picker(at).options)


def test_only_free_times_in_the_candidates_country_are_offered(db):
    add(db, "c1", "Madrid")
    add(db, "c2", "Guadalajara")
    slot(db, "ES", TUESDAY)
    slot(db, "MX", TUESDAY.replace(hour=11))
    taken = slot(db, "ES", TUESDAY.replace(hour=16))
    add(db, "c9", "Madrid")
    db.book_slot(taken, "c9", NOW.astimezone())
    at = opened()
    schedule_picker(at).select(next(o for o in schedule_picker(at).options if "(c1)" in o)).run()
    spanish = at.selectbox(key="sched_slot").options
    assert len(spanish) == 1 and "10:00" in spanish[0]  # the 16:00 is taken and the Mexican 11:00 is another country
    schedule_picker(at).select(next(o for o in schedule_picker(at).options if "(c2)" in o)).run()
    mexican = at.selectbox(key="sched_slot").options
    assert len(mexican) == 1 and "11:00" in mexican[0]


def test_scheduling_books_the_call_tells_the_candidate_and_logs_it(db):
    add(db, "c1", "Madrid")
    chosen = slot(db, "ES", TUESDAY)
    at = opened()
    schedule_picker(at).select(schedule_picker(at).options[0]).run()
    at.selectbox(key="sched_slot").select(chosen).run()
    at.button(key="sched_submit").click().run()
    assert not at.exception, at.exception
    assert db.booking_of("c1").slot_id == chosen
    assert len(db.outbox_pending("c1")) == 1 and "reservado tu llamada" in db.outbox_pending("c1")[0].text
    assert [e.actor for e in db.events("c1") if e.type == "slot_booked"] == ["recruiter:Ana"]
    assert at.success and "Persona c1" in " ".join(str(s.value) for s in at.success)


def test_a_candidate_with_a_call_can_be_moved_to_another_time(db):
    add(db, "c1", "Madrid")
    first, second = slot(db, "ES", TUESDAY), slot(db, "ES", TUESDAY.replace(hour=16))
    db.book_slot(first, "c1", NOW.astimezone())
    at = opened()
    assert "10:00" in schedule_picker(at).options[0]  # the picker shows the call they already have
    schedule_picker(at).select(schedule_picker(at).options[0]).run()
    at.selectbox(key="sched_slot").select(second).run()
    at.button(key="sched_submit").click().run()
    assert db.booking_of("c1").slot_id == second and first in [s.id for s in db.free_slots("ES", NOW)]
    assert "cambiado" in db.outbox_pending("c1")[0].text


def test_a_time_someone_else_booked_meanwhile_disappears_from_the_list_and_nothing_is_booked(db):
    add(db, "c1", "Madrid")
    add(db, "c2", "Madrid")
    chosen = slot(db, "ES", TUESDAY)
    at = opened()
    schedule_picker(at).select(next(o for o in schedule_picker(at).options if "(c1)" in o)).run()
    at.selectbox(key="sched_slot").select(chosen).run()
    db.book_slot(chosen, "c2", NOW.astimezone())  # someone else got it first
    at.run()
    assert at.selectbox(key="sched_slot").value is None and not at.selectbox(key="sched_slot").options
    assert db.booking_of("c1") is None and db.outbox_pending("c1") == []  # (the store itself refuses it too)


def test_the_page_is_in_english_when_the_recruiter_picks_english(db):
    add(db, "c1", "Madrid")
    slot(db, "ES", TUESDAY)
    at = opened("en")
    headings = [str(h.value) for h in at.subheader]
    assert "Organise a call" in headings and not any("Organizar" in h for h in headings)
    assert "Organizar" not in chips(at) and "Horario" not in chips(at)


# --- a new time, created while booking ------------------------------------------------------------------------------------

def pick(at, cid):
    schedule_picker(at).select(next(o for o in schedule_picker(at).options if f"({cid})" in o)).run()


def test_a_call_can_be_booked_at_a_new_time_which_is_created_in_the_candidates_country(db):
    add(db, "c1", "Madrid")
    add(db, "c2", "Guadalajara")
    slot(db, "ES", TUESDAY)  # some other time exists; this one is not used
    at = opened()
    pick(at, "c2")
    at.date_input(key="sched_new_day").set_value(TUESDAY.date() + timedelta(days=1))
    at.time_input(key="sched_new_hour").set_value(TUESDAY.time().replace(hour=9, minute=30))
    at.button(key="sched_submit_new").click().run()
    assert not at.exception, at.exception
    held = db.booking_of("c2")
    assert held.country == "MX" and held.starts_at == datetime(2027, 6, 16, 9, 30)
    assert [e.actor for e in db.events("c2") if e.type == "slot_booked"] == ["recruiter:Ana"]
    assert len(db.outbox_pending("c2")) == 1 and at.success


def test_a_new_time_that_is_too_soon_is_refused_and_nothing_is_left_behind(db):
    add(db, "c1", "Madrid")
    at = opened()
    pick(at, "c1")
    at.date_input(key="sched_new_day").set_value(date.today())
    at.time_input(key="sched_new_hour").set_value(datetime.now().time())
    at.button(key="sched_submit_new").click().run()
    assert at.error and db.booking_of("c1") is None and db.slots(datetime.now().astimezone(), include_past=True) == []


def test_when_the_candidate_cannot_be_told_the_booking_stands_and_the_recruiter_is_warned(db, monkeypatch):
    from screener import slot_flow
    from screener.store import ConflictError
    add(db, "c1", "Madrid")
    chosen = slot(db, "ES", TUESDAY)
    at = opened()
    pick(at, "c1")
    at.selectbox(key="sched_slot").select(chosen).run()

    def lost(*args, **kwargs):
        raise ConflictError("c1")

    monkeypatch.setattr(slot_flow.conversation, "run", lost)
    at.button(key="sched_submit").click().run()
    assert not at.exception, at.exception
    assert db.booking_of("c1").slot_id == chosen and at.success
    assert any("aviso" in str(w.value).lower() for w in at.warning)
