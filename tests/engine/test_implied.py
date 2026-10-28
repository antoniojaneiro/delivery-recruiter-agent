"""D81: a question whose answer follows from an earlier one is not asked. Full time means the whole day, so the preferred
schedule is flexible and the candidate is never asked "morning, afternoon or evening?"; part-time and weekends are asked."""
from datetime import date, datetime

import pytest

from sazon.client import SAZON_CLIENT
from sazon.spec import SAZON
from screener import turn
from screener.screening import Screening
from screener.store import Store
from tests.support.clients import client_for
from tests.support.fakes import ScriptedLLM

TODAY = date(2026, 10, 25)
NOW = datetime(2026, 10, 25, 10, 0)
AREAS = SAZON_CLIENT.areas


def screening(availability=None):
    s = Screening(AREAS, SAZON)
    s.record_consent(True)
    s.submit("name", "Juan Pérez", TODAY)
    s.submit("experience", (2, ["glovo"]), TODAY)
    if availability is not None:
        s.submit("availability", availability, TODAY)
    return s


def test_full_time_is_the_whole_day_so_the_schedule_is_flexible_and_not_asked():
    s = screening(["full_time"])
    assert s.values["schedule"] == "flexible" and s.sources["schedule"] == "implied"
    assert s.next_field() == "start_date" and "schedule" not in s.missing_fields()


@pytest.mark.parametrize("availability", [["part_time"], ["weekends"], ["part_time", "weekends"]])
def test_part_time_and_weekends_are_still_asked_which_part_of_the_day(availability):
    s = screening(availability)
    assert "schedule" not in s.values and s.next_field() == "schedule"


def test_full_time_together_with_weekends_is_still_the_whole_day():
    assert screening(["full_time", "weekends"]).values["schedule"] == "flexible"


def test_an_answer_the_candidate_gives_themselves_replaces_the_implied_one_without_a_change_question():
    s = screening(["full_time"])
    s.submit("schedule", "morning", TODAY)
    assert s.values["schedule"] == "morning" and "schedule" not in s.sources


def test_changing_full_time_to_part_time_brings_the_schedule_question_back():
    s = screening(["full_time"])
    s.submit("availability", ["part_time"], TODAY)
    assert "schedule" not in s.values and s.next_field() == "schedule"


def test_changing_the_availability_keeps_a_schedule_the_candidate_chose():
    s = screening(["part_time"])
    s.submit("schedule", "evening", TODAY)
    s.submit("availability", ["full_time"], TODAY)
    assert s.values["schedule"] == "evening" and "schedule" not in s.sources


def test_the_implied_answer_survives_saving_and_loading():
    s = screening(["full_time"])
    loaded = Screening.from_state(AREAS, s.to_state(), SAZON)
    assert loaded.values["schedule"] == "flexible" and loaded.sources["schedule"] == "implied"


# --- in the conversation ----------------------------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "s.db", calendar=SAZON_CLIENT.calendar)


def say(store, message, *extractions):
    return turn.handle_message(ScriptedLLM(extractions), store, client_for(AREAS), "c1", message, NOW)


def start(store):
    turn.start(store, client_for(AREAS), "c1", NOW)
    say(store, "sí", {"consent": True, "language": "es"})
    say(store, "Soy Juan Pérez", {"name": "Juan Pérez"})
    say(store, "2 años con Glovo", {"experience_years": 2, "platforms": ["Glovo"]})


def test_after_full_time_the_next_question_is_the_start_date_not_the_schedule(store):
    start(store)
    reply = say(store, "tiempo completo", {"availability": ["full_time"]})
    assert "empezar" in reply and "horario" not in reply.lower()
    assert store.get("c1").extracted["schedule"] == "flexible"


def test_after_part_time_the_schedule_is_asked(store):
    start(store)
    reply = say(store, "medio tiempo", {"availability": ["part_time"]})
    assert "horario" in reply.lower()


def test_a_schedule_given_in_the_same_message_wins_over_the_implied_one(store):
    start(store)
    reply = say(store, "tiempo completo, por las mañanas", {"availability": ["full_time"], "schedule": "morning"})
    assert store.get("c1").extracted["schedule"] == "morning" and "antes me dijiste" not in reply.lower()
