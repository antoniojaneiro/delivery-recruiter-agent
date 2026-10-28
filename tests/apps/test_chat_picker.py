"""D83: in the browser chat a candidate who qualified sees a button; it opens a month with only the days that have free times
clickable, then that day's 15-minute times; choosing one books it, as typing its number would."""
from datetime import date, datetime, timedelta

import pytest
from streamlit.testing.v1 import AppTest

from sazon.client import SAZON_CLIENT
from screener.store import Store
from tests.support.booking import say as engine_say
from tests.support.fakes import ScriptedLLM
from tests.support.paths import CHAT_APP

APP = str(CHAT_APP)
ANSWERS = [("Soy Juan Pérez", {"name": "Juan Pérez"}), ("2 años con Glovo", {"experience_years": 2, "platforms": ["Glovo"]}),
           ("tiempo completo", {"availability": ["full_time"]}), ("ya mismo", {"start_date": {"now": True}}),
           ("Madrid", {"city": "Madrid"}), ("sí tengo", {"has_license": True})]


@pytest.fixture
def chat(tmp_path, monkeypatch):
    monkeypatch.setenv("SAZON_DB", str(tmp_path / "real.db"))
    monkeypatch.setattr("screener.gemini.from_env", lambda: ScriptedLLM())
    store = Store(tmp_path / "real.db", calendar=SAZON_CLIENT.calendar)
    for name in ("Ana", "Luis"):
        store.add_recruiter(f"{name.lower()}@sazon.test", name, "ES", "contraseña-segura-1", "boss@sazon.test", datetime.now())
    return store


def opened(language="es"):
    at = AppTest.from_file(APP, default_timeout=20)
    at.session_state["ui_language"] = language
    return at.run()


def qualify_in_the_chat(at, store):
    """The chat's own candidate answers everything, so the agent qualifies them (the engine's turn code, scripted model)."""
    cid = at.session_state["chat_id"]
    engine_say(store, "sí", {"consent": True, "language": "es"}, cid=cid)
    for message, extraction in ANSWERS:
        engine_say(store, message, extraction, cid=cid)
    assert store.get(cid).outcome == "QUALIFIED"
    at.run()
    return cid


def enabled_days(at):
    return [b for b in at.button if b.key.startswith("pick_day_") and not b.disabled]


def test_the_button_appears_when_the_candidate_qualifies_and_opens_a_month_with_only_the_free_days_clickable(chat):
    at = opened()
    assert not [b for b in at.button if b.key == "pick_open"]  # nothing to pick before they qualify
    cid = qualify_in_the_chat(at, chat)
    offer = chat.messages(cid)[-1].text  # the message says to use the button; there is no numbered list beside it
    assert "reserva una llamada" in offer and "1)" not in offer
    assert [b.label for b in at.button if b.key == "pick_open"] == ["Elegir día y hora"]
    at.button(key="pick_open").click().run()
    assert not at.exception, at.exception
    days = enabled_days(at)
    assert days and all(date.fromisoformat(b.key.removeprefix("pick_day_")).weekday() < 5 for b in days)  # Monday to Friday
    free = chat.free_days("ES", date.today().replace(day=1), datetime.now().astimezone())
    assert {date.fromisoformat(b.key.removeprefix("pick_day_")) for b in days} == set(free)
    assert [b for b in at.button if b.key.startswith("pick_day_") and b.disabled]  # weekends and past days are greyed


def test_choosing_a_day_shows_its_fifteen_minute_times_and_choosing_one_books_it(chat):
    at = opened()
    cid = qualify_in_the_chat(at, chat)
    at.button(key="pick_open").click().run()
    day = enabled_days(at)[0]
    day.click().run()
    times = [b for b in at.button if b.key.startswith("pick_time_")]
    assert len(times) >= 20 and times[0].label[2] == ":" and times[1].label[-2:] in ("15", "30", "45", "00")
    times[2].click().run()
    assert not at.exception, at.exception
    held = chat.booking_of(cid)
    assert held is not None and held.starts_at.date() == date.fromisoformat(day.key.removeprefix("pick_day_"))
    assert any("queda reservada" in str(m.text[0].value) for m in at.chat_message if m.text)
    assert not [b for b in at.button if b.key == "pick_open"] and not enabled_days(at)  # nothing more to pick


def test_the_picker_speaks_the_candidates_language(chat):
    at = opened("en")
    cid = at.session_state["chat_id"]
    engine_say(chat, "yes", {"consent": True, "language": "en"}, cid=cid)
    english = ("My name is John Smith", "2 years with Glovo", "full time", "right now", "Madrid", "yes I do")
    for message, (_, extraction) in zip(english, ANSWERS):
        engine_say(chat, message, extraction, cid=cid)
    at.run()
    assert [b.label for b in at.button if b.key == "pick_open"] == ["Choose a day and time"]
    at.button(key="pick_open").click().run()
    assert any(date.today().strftime("%Y") in str(m.value) and "Monday" not in str(m.value) for m in at.markdown)


def test_the_month_buttons_move_the_calendar(chat):
    at = opened()
    qualify_in_the_chat(at, chat)
    at.button(key="pick_open").click().run()
    first = at.session_state["picker_month"]
    at.button(key="pick_next").click().run()
    assert at.session_state["picker_month"] > first
    at.button(key="pick_prev").click().run()
    assert at.session_state["picker_month"] == first


@pytest.fixture
def bare(tmp_path, monkeypatch):
    """A chat whose database has no recruiters at all, as on the first run."""
    monkeypatch.setenv("SAZON_DB", str(tmp_path / "real.db"))
    monkeypatch.setattr("screener.gemini.from_env", lambda: ScriptedLLM())
    return Store(tmp_path / "real.db", calendar=SAZON_CLIENT.calendar), tmp_path


def test_with_no_recruiters_yet_the_hiring_manager_takes_the_calls_so_there_are_times_to_book(bare, monkeypatch):
    from tests.support.dash import MANAGER_EMAIL, set_manager
    set_manager(monkeypatch)
    store, _ = bare
    at = opened()
    at.run()
    assert [r.email for r in store.recruiters()] == [MANAGER_EMAIL]  # made once, a rerun does not add them again
    qualify_in_the_chat(at, store)
    at.button(key="pick_open").click().run()
    assert enabled_days(at)  # a candidate trying the chat can book a call straight away


def test_without_a_manager_and_without_recruiters_there_are_no_times_and_nobody_is_invented(bare):
    store, _ = bare
    at = opened()
    assert store.recruiters() == []  # no fictional people are put among the real recruiters
