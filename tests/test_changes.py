"""D54: a changed answer is confirmed with the candidate."""
import json
from datetime import date, datetime

import pytest

from sazon import config, turn
from sazon.extraction import Extraction, StartDate
from sazon.model import Field
from sazon.phrasing import Kind, phrase
from sazon.screening import Screening
from sazon.store import Store
from tests.fakes import FakeLLM, ScriptedLLM

TODAY = date(2026, 10, 25)
NOW = datetime(2026, 10, 25, 10, 0)


def accepted(**overrides):
    s = Screening(config.AREAS)
    s.record_consent(True)
    values = {"name": "Juan Pérez", "experience": (2, ["Glovo"]), "availability": ["full_time"], "schedule": "morning",
              "start_date": date(2026, 11, 1), "city": "Madrid"}
    values.update(overrides)
    for field, value in values.items():
        s.submit(field, value, TODAY)
    return s


def ask(s, text, **fields):
    return s.apply(Extraction(**fields), text, TODAY)


def text_of(directive, language="es"):
    return phrase(FakeLLM(), directive, language)


# --- what counts as a change ---------------------------------------------------------------------------------

def test_a_different_valid_value_for_an_accepted_field_is_asked_about_not_applied():
    s = accepted()
    directive = ask(s, "mi nombre es Carlos López", name="Carlos López")
    assert directive.kind == Kind.CONFIRM_CHANGE and s.awaiting_change
    assert s.values["name"] == "Juan Pérez"
    assert text_of(directive) == "Antes me dijiste Juan Pérez. ¿Lo cambio a Carlos López?"


@pytest.mark.parametrize("field,payload", [
    ("name", {"name": "juan  pérez"}), ("name", {"name": "JUAN PEREZ"}),
    ("availability", {"availability": ["full_time"]}), ("schedule", {"schedule": "morning"}),
    ("experience", {"experience_years": 2}), ("experience", {"experience_years": 2.0, "platforms": ["glovo"]}),
    ("experience", {"platforms": ["GLOVO"]}), ("city", {"city": "madrid"}), ("city", {"city": "Chamberí"}),
    ("start_date", {"start_date": StartDate(iso=date(2026, 11, 1))}),
])
def test_saying_the_same_thing_again_in_other_words_is_not_a_change(field, payload):
    s = accepted()
    directive = ask(s, "como te dije", **payload)
    assert not s.awaiting_change and directive.kind != Kind.CONFIRM_CHANGE


def test_the_same_availability_in_another_order_is_not_a_change():
    s = accepted(availability=["part_time", "weekends"])
    ask(s, "fines de semana y medio tiempo", availability=["weekends", "part_time"])
    assert not s.awaiting_change


def test_an_invalid_new_value_is_ignored_and_does_not_count_as_an_unclear_answer():
    s = accepted()
    ask(s, "mi jefe es Pepe", name="Pepe")
    assert not s.awaiting_change and s.values["name"] == "Juan Pérez"
    assert [kind for kind, _ in s.events].count("follow_up") == 0


def test_a_new_value_for_a_field_not_yet_accepted_is_taken_normally():
    s = accepted()
    ask(s, "tengo licencia", has_license=True)
    assert s.values["license"] is True and not s.awaiting_change


def test_only_one_change_is_asked_at_a_time():
    s = accepted()
    directive = ask(s, "soy Carlos López y vivo en Barcelona", name="Carlos López", city="Barcelona")
    assert directive.kind == Kind.CONFIRM_CHANGE and directive.field == Field.NAME


def test_a_message_with_a_change_and_a_new_answer_keeps_the_new_answer():
    s = accepted()
    ask(s, "soy Carlos López y sí tengo licencia", name="Carlos López", has_license=True)
    assert s.values["license"] is True and s.awaiting_change


# --- answering the question -------------------------------------------------------------------------------------

def test_yes_applies_the_change_says_so_and_goes_on_with_the_next_question():
    s = accepted()
    ask(s, "soy Carlos López", name="Carlos López")
    directive = s.resolve_change(True, TODAY)
    assert s.values["name"] == "Carlos López" and not s.awaiting_change
    out = phrase(FakeLLM("¿Tienes licencia?"), directive, "es")
    assert out.startswith("Hecho, lo he cambiado.") and out.endswith("¿Tienes licencia?")
    assert ("field_changed", "name") in s.events


def test_no_keeps_the_old_value_and_says_so():
    s = accepted()
    ask(s, "mi jefe se llama Carlos López", name="Carlos López")
    directive = s.resolve_change(False, TODAY)
    assert s.values["name"] == "Juan Pérez"
    assert phrase(FakeLLM("¿Tienes licencia?"), directive, "es").startswith("De acuerdo, lo dejo como estaba.")
    assert ("field_changed", "name") not in s.events


def test_changing_the_city_to_one_outside_the_area_still_asks_before_rejecting():
    s = accepted()
    ask(s, "me mudé a Sevilla", city="Sevilla")
    directive = s.resolve_change(True, TODAY)
    assert directive.kind == Kind.CONFIRM_REJECTION and s.decide().outcome == "IN_PROGRESS"
    s.confirm_rejection(True)
    assert s.decide().outcome == "DISQUALIFIED"


def test_changing_the_city_to_a_typo_asks_the_city_question_next():
    s = accepted()
    ask(s, "ahora vivo en Barcelnoa", city="Barcelnoa")
    directive = s.resolve_change(True, TODAY)
    assert directive.kind == Kind.CONFIRM_CITY and directive.suggestion == "Barcelona"


def test_changing_experience_keeps_the_platform_when_only_the_years_are_given():
    s = accepted()
    directive = ask(s, "en realidad 3 años", experience_years=3)
    assert text_of(directive) == "Antes me dijiste 2 años (glovo). ¿Lo cambio a 3 años (glovo)?"
    s.resolve_change(True, TODAY)
    assert s.values["experience"] == {"years": 3, "platforms": ["glovo"]}


def test_the_question_is_in_english_with_english_labels():
    s = accepted()
    s.language = "en"
    directive = ask(s, "I work weekends", availability=["weekends"])
    assert text_of(directive, "en") == "Earlier you told me full-time. Shall I change it to weekends?"
    partly = Screening(config.AREAS)
    partly.record_consent(True)
    partly.language = "en"
    partly.submit("license", True, TODAY)
    assert text_of(ask(partly, "no license", has_license=False), "en") == "Earlier you told me yes. Shall I change it to no?"


def test_the_pending_change_survives_a_save_and_reload():
    s = accepted()
    ask(s, "en realidad empiezo el 15 de noviembre", start_date=StartDate(iso=date(2026, 11, 15)))
    restored = Screening.from_state(config.AREAS, json.loads(json.dumps(s.to_state())))
    assert restored.awaiting_change
    restored.resolve_change(True, TODAY)
    assert restored.values["start_date"] == date(2026, 11, 15)


def test_a_long_or_multiline_value_is_cleaned_before_it_is_echoed():
    s = accepted()
    name = "Carlos " + "Lopezzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"
    out = text_of(ask(s, "soy otro", name=name))
    assert "\n" not in out and len(out) < 160


# --- the whole conversation ----------------------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "s.db")


def talk(store, message, *extractions, phrases=()):
    llm = ScriptedLLM(extractions, phrases)
    return turn.handle_message(llm, store, config.AREAS, "c1", message, NOW), llm


def chat_until_city(store):
    turn.start(store, config.AREAS, "c1", NOW)
    talk(store, "sí")
    talk(store, "Juan Pérez", {"name": "Juan Pérez"})
    talk(store, "2 años Glovo", {"experience_years": 2, "platforms": ["Glovo"]})
    talk(store, "tiempo completo", {"availability": ["full_time"]})
    talk(store, "mañana", {"schedule": "morning"})
    talk(store, "ya", {"start_date": {"now": True}})
    talk(store, "Madrid", {"city": "Madrid"})


def test_a_correction_is_confirmed_in_plain_code_and_then_applied(store):
    chat_until_city(store)
    asked, _ = talk(store, "perdona, vivo en Barcelona", {"city": "Barcelona"})
    assert asked == "Antes me dijiste Madrid. ¿Lo cambio a Barcelona?"
    assert store.get("c1").extracted["city"] == "Madrid"
    reply, llm = talk(store, "sí", phrases=["¿Tienes licencia?"])
    assert not [c for c in llm.calls if c["json_mode"]]  # the yes was read in plain code
    assert reply.startswith("Hecho, lo he cambiado.") and store.get("c1").extracted["city"] == "Barcelona"


def test_a_no_keeps_the_old_answer(store):
    chat_until_city(store)
    talk(store, "mi hermano vive en Barcelona", {"city": "Barcelona"})
    reply, _ = talk(store, "no", phrases=["¿Tienes licencia?"])
    assert reply.startswith("De acuerdo, lo dejo como estaba.") and store.get("c1").extracted["city"] == "Madrid"


def test_an_unclear_reply_drops_the_question_and_is_read_as_a_normal_message(store):
    chat_until_city(store)
    talk(store, "vivo en Barcelona", {"city": "Barcelona"})
    reply, llm = talk(store, "tengo licencia", {"has_license": True})
    assert store.get("c1").extracted["city"] == "Madrid" and store.get("c1").extracted["license"] is True
    assert [c for c in llm.calls if c["json_mode"]]
    assert "Antes me dijiste" not in reply


def test_the_change_is_logged_without_the_values(store):
    chat_until_city(store)
    talk(store, "vivo en Barcelona", {"city": "Barcelona"})
    talk(store, "sí", phrases=["¿Tienes licencia?"])
    [event] = [e for e in store.events("c1") if e.type == "field_changed"]
    assert event.detail == "city" and "Barcelona" not in event.detail and "Madrid" not in event.detail
