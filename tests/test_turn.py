from datetime import datetime

import pytest

from sazon import turn
from sazon.llm import LLMError
from sazon.phrasing import consent_message
from sazon.store import Store
from tests.fakes import ScriptedLLM

AREAS = {"Madrid": [], "Guadalajara": [], "Ciudad de México": ["CDMX"]}
NOW = datetime(2026, 10, 25, 10, 0)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "sazon.db")


def say(store, message, *extractions, id="c1", now=NOW, phrases=()):
    llm = ScriptedLLM(extractions, phrases)
    reply = turn.handle_message(llm, store, AREAS, id, message, now)
    return reply, llm


def outcome(store, id="c1"):
    return store.get(id).outcome


def test_the_first_message_is_the_fixed_disclosure_and_is_saved(store):
    assert turn.start(store, AREAS, "c1", NOW) == consent_message()
    assert [(m.role, m.text) for m in store.messages("c1")] == [("agent", consent_message())]
    assert outcome(store) == "IN_PROGRESS"


def test_consent_yes_moves_on_to_the_first_question(store):
    turn.start(store, AREAS, "c1", NOW)
    reply, _ = say(store, "sí", {"consent": True, "language": "es"})
    assert "llamas" in reply
    assert store.get("c1").state["consent"] is True


def test_consent_no_closes_politely_and_nothing_is_kept(store):
    turn.start(store, AREAS, "c1", NOW)
    reply, _ = say(store, "no", {"consent": False, "language": "es", "name": "Juan Pérez"})
    assert outcome(store) == "DISQUALIFIED" and "permiso" in reply
    assert store.get("c1").extracted == {}


def test_data_in_the_consent_reply_is_used_only_after_a_yes(store):
    turn.start(store, AREAS, "c1", NOW)
    reply, _ = say(store, "sí, soy Juan Pérez de Madrid",
                   {"consent": True, "name": "Juan Pérez", "city": "Madrid"})
    assert store.get("c1").extracted == {"name": "Juan Pérez", "city": "Madrid"}
    assert "ciudad" not in reply and "años" in reply  # next missing field is experience


def test_an_unanswered_consent_question_is_asked_again(store):
    turn.start(store, AREAS, "c1", NOW)
    reply, _ = say(store, "¿quién eres?", {"language": "es"})
    assert reply == consent_message()
    assert store.get("c1").extracted == {}


def test_one_message_can_answer_several_fields_and_the_rest_are_asked_in_order(store):
    turn.start(store, AREAS, "c1", NOW)
    say(store, "sí", {"consent": True})
    reply, _ = say(store, "Soy Juan Pérez, tengo licencia y vivo en CDMX",
                   {"name": "Juan Pérez", "has_license": True, "city": "CDMX"})
    assert store.get("c1").extracted == {"name": "Juan Pérez", "license": True, "city": "Ciudad de México"}
    assert "años" in reply


def test_a_start_date_given_as_weeks_is_computed_in_code(store):
    turn.start(store, AREAS, "c1", NOW)
    say(store, "sí", {"consent": True})
    say(store, "en dos semanas", {"start_date": {"in_weeks": 2}})
    assert store.get("c1").extracted["start_date"] == "2026-11-08"


def test_the_reply_follows_the_candidates_language_when_they_switch(store):
    turn.start(store, AREAS, "c1", NOW)
    say(store, "yes", {"consent": True, "language": "en"})
    reply, _ = say(store, "John Smith", {"name": "John Smith", "language": "en"})
    assert "experience" in reply.lower()
    reply, _ = say(store, "vale, 2 años en Glovo", {"experience_years": 2, "platforms": ["Glovo"], "language": "es"})
    assert "disponibilidad" in reply


def test_no_license_ends_the_chat_at_once_with_the_reason(store):
    turn.start(store, AREAS, "c1", NOW)
    say(store, "sí", {"consent": True})
    reply, _ = say(store, "no tengo licencia", {"has_license": False})
    assert outcome(store) == "DISQUALIFIED" and "licencia" in reply


def test_an_out_of_area_city_ends_the_chat_at_once(store):
    turn.start(store, AREAS, "c1", NOW)
    say(store, "sí", {"consent": True})
    reply, _ = say(store, "vivo en Sevilla", {"city": "Sevilla"})
    assert outcome(store) == "DISQUALIFIED" and "zona" in reply


def test_withdrawing_closes_the_chat_and_asks_nothing_more(store):
    turn.start(store, AREAS, "c1", NOW)
    say(store, "sí", {"consent": True})
    reply, _ = say(store, "mejor no, para", {"withdraw": True})
    assert outcome(store) == "WITHDRAWN" and "no te haré más preguntas" in reply


def test_messages_after_the_chat_has_ended_get_the_close_again_without_calling_the_llm(store):
    turn.start(store, AREAS, "c1", NOW)
    say(store, "sí", {"consent": True})
    say(store, "no tengo licencia", {"has_license": False})
    reply, llm = say(store, "espera, sí tengo")
    assert llm.calls == [] and "licencia" in reply
    assert outcome(store) == "DISQUALIFIED"


def test_every_turn_stores_both_sides_of_the_conversation_in_order(store):
    turn.start(store, AREAS, "c1", NOW)
    reply, _ = say(store, "sí", {"consent": True})
    messages = [(m.role, m.text) for m in store.messages("c1")]
    assert messages == [("agent", consent_message()), ("candidate", "sí"), ("agent", reply)]
