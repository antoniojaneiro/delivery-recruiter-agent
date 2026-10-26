"""D41: five insistences per field, then BLOCKED until the field is provided."""
import json
from datetime import date, datetime

import pytest

from tests.clients import client_for
from sazon.sazon_spec import SAZON
from sazon import session, turn
from sazon.llm import LLMError
from sazon.phrasing import Directive, Kind, phrase
from sazon.model import Field
from sazon.screening import Screening
from sazon.store import Store
from tests.fakes import FakeLLM, ScriptedLLM

AREAS = {"Madrid": [], "Guadalajara": []}
TODAY = date(2026, 10, 25)
NOW = datetime(2026, 10, 25, 10, 0)


@pytest.fixture
def consented():
    s = Screening(AREAS)
    s.record_consent(True)
    return s


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "sazon.db")


def unclear(s, field, value, times):
    return [s.submit(field, value, TODAY).status for _ in range(times)]


def test_five_unclear_answers_get_follow_ups_and_the_sixth_blocks_the_field(consented):
    statuses = unclear(consented, "name", "Juan", 6)
    assert statuses == ["follow_up"] * 5 + ["blocked"]
    decision = consented.decide()
    assert decision.outcome == "BLOCKED" and decision.reasons == ["BLOCKED_ON_NAME"]
    assert "name" not in consented.values
    assert consented.next_field() == "name"


def test_a_blocked_field_stays_blocked_and_nothing_is_stored_for_it(consented):
    unclear(consented, "name", "Juan", 6)
    assert unclear(consented, "name", "Juan", 4) == ["blocked"] * 4
    assert consented.extracted() == {}


def test_a_valid_answer_unblocks_and_resets_the_count(consented):
    unclear(consented, "name", "Juan", 6)
    assert consented.submit("name", "Juan Pérez", TODAY).status == "ok"
    assert consented.decide().outcome == "IN_PROGRESS"
    assert consented.next_field() == "experience"
    assert unclear(consented, "experience", None, 1) == ["follow_up"]


@pytest.mark.parametrize("field,bad", [
    ("experience", None), ("availability", []), ("schedule", "night"), ("start_date", None),
    ("license", None),
])
def test_the_same_rule_applies_to_every_field(consented, field, bad):
    assert unclear(consented, field, bad, 6)[-1] == "blocked"
    assert consented.decide().reasons == [f"BLOCKED_ON_{field.upper()}"]


def test_a_city_confirmation_declined_again_and_again_ends_up_blocked(consented):
    results = []
    for _ in range(6):
        consented.submit("city", "Guadalajra", TODAY)
        results.append(consented.confirm_city(False).status)
    assert results == ["follow_up"] * 5 + ["blocked"]
    assert consented.decide().reasons == ["BLOCKED_ON_CITY"]


def test_being_blocked_is_logged_and_survives_a_save_and_reload(consented):
    unclear(consented, "name", "Juan", 6)
    assert ("blocked", "name") in consented.events
    restored = Screening.from_state(AREAS, json.loads(json.dumps(consented.to_state())))
    assert restored.decide().outcome == "BLOCKED"
    assert restored.submit("name", "Juan", TODAY).status == "blocked"


def test_a_known_disqualifier_wins_over_being_blocked(consented):
    unclear(consented, "name", "Juan", 6)
    consented.submit("license", False, TODAY)
    consented.confirm_rejection(True)
    assert consented.decide().outcome == "DISQUALIFIED"


def test_a_blocked_candidate_can_still_be_stalled_and_comes_back(consented):
    unclear(consented, "name", "Juan", 6)
    consented.mark_stalled()
    assert consented.decide().outcome == "STALLED"
    consented.resume()
    assert consented.decide().outcome == "BLOCKED"


def test_the_extracted_json_never_holds_anything_but_validated_values(consented):
    unclear(consented, "experience", None, 8)
    unclear(consented, "start_date", None, 8)
    assert consented.extracted() == {}


# --- through handle_message ------------------------------------------------

def say(store, message, *extractions, phrases=()):
    llm = ScriptedLLM(extractions, phrases)
    return turn.handle_message(llm, store, client_for(AREAS), "c1", message, NOW), llm


def consented_chat(store):
    turn.start(store, client_for(AREAS), "c1", NOW)
    say(store, "sí", {"consent": True})


def test_the_chat_insists_five_times_then_says_it_cannot_proceed_and_keeps_saying_it(store):
    consented_chat(store)
    for _ in range(5):
        reply, _ = say(store, "Juan", {"name": "Juan"})
        assert "necesito" in reply.lower()
    for _ in range(3):
        reply, llm = say(store, "Juan", {"name": "Juan"})
        assert "no puedo continuar" in reply.lower() and "nombre" in reply.lower()
        assert not [c for c in llm.calls if not c["json_mode"]]
    assert store.get("c1").outcome == "BLOCKED"


def test_providing_the_missing_information_lets_the_chat_carry_on(store):
    consented_chat(store)
    for _ in range(6):
        say(store, "Juan", {"name": "Juan"})
    reply, _ = say(store, "Juan Pérez", {"name": "Juan Pérez"})
    assert "años" in reply and store.get("c1").outcome == "IN_PROGRESS"
    assert store.get("c1").extracted == {"name": "Juan Pérez"}


def test_a_blocked_candidate_who_answers_something_else_is_told_the_same_thing(store):
    consented_chat(store)
    for _ in range(6):
        say(store, "Juan", {"name": "Juan"})
    reply, _ = say(store, "vivo en Madrid", {"city": "Madrid"})
    assert "no puedo continuar" in reply.lower() and "nombre" in reply.lower()
    assert store.get("c1").extracted == {"city": "Madrid"}


def test_a_model_failure_never_counts_toward_being_blocked(store):
    consented_chat(store)
    for _ in range(9):
        say(store, "Juan Pérez", LLMError("429"))
    assert store.get("c1").outcome == "IN_PROGRESS"


def test_a_blocked_candidate_is_reminded_and_can_stall(store):
    consented_chat(store)
    for _ in range(6):
        say(store, "Juan", {"name": "Juan"})
    assert turn.wait_24h(ScriptedLLM(), store, client_for(AREAS), "c1", NOW)
    assert turn.wait_24h(ScriptedLLM(), store, client_for(AREAS), "c1", NOW) is None
    assert store.get("c1").outcome == "STALLED"


# --- phrasing ----------------------------------------------------------------

@pytest.mark.parametrize("field,es,en", [
    (Field.NAME, "nombre", "name"), (Field.EXPERIENCE, "experiencia", "experience"),
    (Field.AVAILABILITY, "disponibilidad", "availability"), (Field.SCHEDULE, "horario", "schedule"),
    (Field.START_DATE, "empezar", "start"), (Field.CITY, "ciudad", "city"),
    (Field.LICENSE, "licencia", "license"),
])
def test_the_blocked_message_is_fixed_and_names_what_is_missing(field, es, en):
    llm = FakeLLM("should never be used")
    assert es in phrase(llm, SAZON, Directive(Kind.BLOCKED, field=field), "es").lower()
    assert en in phrase(llm, SAZON, Directive(Kind.BLOCKED, field=field), "en").lower()
    assert llm.calls == []


def test_the_follow_up_fallback_explains_the_information_is_needed_to_continue():
    out = phrase(FakeLLM("x" * 400), SAZON, Directive(Kind.FOLLOW_UP, field=Field.NAME), "es")
    assert "necesito" in out.lower()
