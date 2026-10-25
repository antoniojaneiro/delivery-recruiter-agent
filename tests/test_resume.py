"""D56: who can come back to a closed chat, and the applications switch."""
from datetime import datetime

import pytest

from sazon import config, turn
from sazon.consent import is_resume_request
from sazon.phrasing import closed_message, consent_message
from sazon.store import Store
from tests.fakes import ScriptedLLM

NOW = datetime(2026, 10, 25, 10, 0)
AWARE = NOW.astimezone()


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "s.db")


def say(store, message, *extractions, cid="c1", phrases=()):
    llm = ScriptedLLM(extractions, phrases)
    return turn.handle_message(llm, store, config.AREAS, cid, message, NOW), llm


def started(store, cid="c1"):
    turn.start(store, config.AREAS, cid, NOW)
    say(store, "sí", cid=cid)


def outcome(store, cid="c1"):
    return store.get(cid).outcome


# --- who asks to come back --------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "continuar", "Continuar.", "quiero continuar", "retomar", "quiero retomar mi solicitud", "sigamos",
    "continue", "I want to continue", "resume", "let's continue",
])
def test_an_explicit_request_to_continue_is_recognised(text):
    assert is_resume_request(text) is True


@pytest.mark.parametrize("text", ["", "vale", "ok", "gracias", "adiós", "hola", "sí", "no", "stop", "no quiero continuar",
                                  "I don't want to continue", "¿puedo continuar?"])
def test_an_acknowledgement_or_a_refusal_is_not_a_request_to_continue(text):
    assert is_resume_request(text) is False


# --- withdrawn: they can come back, politely ---------------------------------------------------------

def test_a_withdrawn_candidate_stays_withdrawn_when_they_only_say_thanks(store):
    started(store)
    say(store, "me retiro")
    for message in ["vale", "gracias", "ok", "adiós"]:
        reply, llm = say(store, message)
        assert "«continuar»" in reply and llm.calls == []
        assert outcome(store) == "WITHDRAWN"


def test_a_withdrawn_candidate_who_asks_to_continue_is_back_where_they_stopped(store):
    started(store)
    say(store, "Juan Pérez", {"name": "Juan Pérez"})
    say(store, "me retiro")
    reply, llm = say(store, "continuar", phrases=["¿Tienes experiencia repartiendo?"])
    assert outcome(store) == "IN_PROGRESS" and "experiencia" in reply.lower()
    assert "resumed" in [e.type for e in store.events("c1")]
    assert store.get("c1").extracted == {"name": "Juan Pérez"}
    assert not [c for c in llm.calls if c["json_mode"]]


def test_the_english_way_back(store):
    turn.start(store, config.AREAS, "c1", NOW)
    say(store, "yes")
    say(store, "stop")
    reply, _ = say(store, "I want to continue")
    assert outcome(store) == "IN_PROGRESS" and "name" in reply.lower()


# --- declined consent: a later yes starts it ------------------------------------------------------------

def test_a_candidate_who_declined_consent_can_say_yes_later_and_start(store):
    turn.start(store, config.AREAS, "c1", NOW)
    say(store, "no gracias")
    assert outcome(store) == "DISQUALIFIED"
    reply, _ = say(store, "sí", phrases=["¿Cómo te llamas?"])
    assert outcome(store) == "IN_PROGRESS" and "llamas" in reply
    kinds = [e.type for e in store.events("c1")]
    assert kinds.index("consent_declined") < kinds.index("consent_given")


def test_after_declining_other_messages_get_a_reminder_of_how_to_start(store):
    turn.start(store, config.AREAS, "c1", NOW)
    say(store, "no gracias")
    reply, llm = say(store, "hola, ¿qué tal?")
    assert "«sí»" in reply and llm.calls == [] and outcome(store) == "DISQUALIFIED"


def test_nothing_the_candidate_writes_while_declined_is_stored(store):
    turn.start(store, config.AREAS, "c1", NOW)
    say(store, "no gracias")
    say(store, "mi teléfono es 600123123")
    assert all("600123123" not in m.text for m in store.messages("c1"))


# --- the closes that stay closed ----------------------------------------------------------------------------

def test_a_rejected_candidate_cannot_continue_by_writing_again(store):
    started(store)
    say(store, "no tengo licencia", {"has_license": False})
    say(store, "sí", {"confirms_rejection": True})
    reply, _ = say(store, "continuar")
    assert outcome(store) == "DISQUALIFIED" and "ya está cerrada" in reply


def test_the_off_topic_exit_stays_closed_even_if_the_candidate_asks_to_continue(store):
    started(store)
    for message in ["chiste", "otro chiste", "y otro"]:
        say(store, message, {"off_topic": True})
    assert outcome(store) == "ENDED_OFF_TOPIC"
    reply, _ = say(store, "continuar")
    assert outcome(store) == "ENDED_OFF_TOPIC" and "cerrada" in reply


def test_a_stalled_or_blocked_candidate_returns_by_just_writing(store):
    started(store)
    turn.wait_24h(ScriptedLLM(), store, config.AREAS, "c1", NOW)
    turn.wait_24h(ScriptedLLM(), store, config.AREAS, "c1", NOW)
    assert outcome(store) == "STALLED"
    say(store, "Juan Pérez", {"name": "Juan Pérez"})
    assert outcome(store) == "IN_PROGRESS"


# --- the applications switch ------------------------------------------------------------------------------------

def test_applications_are_open_unless_someone_closed_them(store):
    assert store.accepting_applications() is True


def test_closing_applications_stops_new_and_current_candidates_without_touching_the_model(store):
    started(store)
    say(store, "Juan Pérez", {"name": "Juan Pérez"})
    before = (store.get("c1").state, len(store.messages("c1")))
    store.set_accepting(False, "Ana", AWARE)
    reply, llm = say(store, "mi teléfono es 600123123", {"name": "Otro Nombre"})
    assert reply == closed_message() and llm.calls == []
    assert (store.get("c1").state, len(store.messages("c1"))) == before
    assert turn.start(store, config.AREAS, "new", NOW) == closed_message()
    assert store.get("new") is None
    assert turn.wait_24h(ScriptedLLM(), store, config.AREAS, "c1", NOW) is None


def test_reopening_lets_everyone_continue_from_where_they_were(store):
    started(store)
    say(store, "Juan Pérez", {"name": "Juan Pérez"})
    store.set_accepting(False, "Ana", AWARE)
    store.set_accepting(True, "Ana", AWARE)
    reply, _ = say(store, "2 años con Glovo", {"experience_years": 2, "platforms": ["Glovo"]},
                   phrases=["¿Qué disponibilidad tienes?"])
    assert "disponibilidad" in reply.lower() and store.get("c1").extracted["experience"]["years"] == 2


def test_the_switch_is_logged_with_who_and_when(store):
    store.set_accepting(False, "Ana", AWARE)
    store.set_accepting(True, "Luis", AWARE)
    log = store.admin_log()
    assert [(e.actor, e.action) for e in log] == [("recruiter:Ana", "applications_closed"),
                                                  ("recruiter:Luis", "applications_opened")]


def test_the_switch_needs_a_name(store):
    with pytest.raises(ValueError):
        store.set_accepting(False, "  ", AWARE)
    assert store.accepting_applications() is True


def test_the_closed_notice_is_bilingual_because_the_language_is_not_known_yet():
    text = closed_message()
    assert "no estamos aceptando solicitudes" in text and "not accepting applications" in text
