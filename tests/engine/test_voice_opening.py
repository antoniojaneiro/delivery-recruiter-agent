"""D93: what Sofía says first when a call starts. It is what the engine would say now on the voice channel: the disclosure for
someone who has not agreed yet, the open question for someone midway, the day question for someone qualified, never the
consent question again for someone who already answered it. What is said is saved as the agent's message, so the transcript
shows what was heard."""
from datetime import datetime

import pytest

from sazon.areas import AREAS
from sazon.client import SAZON_CALENDAR
from screener import turn
from screener.phrasing import consent_message
from screener.store import Store
from tests.support.booking import NOW, hire, qualify, say
from tests.support.clients import client_for

CLIENT = client_for(AREAS)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "s.db", calendar=SAZON_CALENDAR)
    hire(s, "Ana")
    return s


def opening(store, cid="c1"):
    return turn.voice_opening(store, CLIENT, cid, NOW)


def texts(store, cid="c1"):
    return [(m.role, m.text) for m in store.messages(cid)]


def test_someone_who_has_not_answered_the_consent_question_hears_the_disclosure_and_nothing_is_saved_twice(store):
    turn.start(store, CLIENT, "c1", NOW)
    words, language = opening(store)
    assert words == consent_message(CLIENT.spec) and language is None  # the language is not known yet
    assert texts(store) == [("agent", consent_message(CLIENT.spec))]  # the text chat already showed it


def test_someone_midway_hears_where_they_were_and_never_the_consent_question_again(store):
    turn.start(store, CLIENT, "c1", NOW)
    say(store, "sí", {"consent": True, "language": "es"})
    say(store, "Soy Juan Pérez", {"name": "Juan Pérez"})
    words, language = opening(store)
    assert words.startswith("Sigamos con tu solicitud.") and "IA" not in words and language == "es"
    assert texts(store)[-1] == ("agent", words)  # what was heard is in the transcript
    again, _ = opening(store)
    assert again == words and texts(store).count(("agent", words)) == 1  # a second call is not saved twice in a row


def test_a_qualified_candidate_with_no_call_is_asked_the_day_and_the_spoken_booking_starts(store):
    qualify(store)
    words, _ = opening(store)
    assert words.endswith("¿Qué día te vendría bien?")
    assert store.get("c1").state["voice_booking"]["stage"] == "day"
    assert say(store, "el martes", voice=True)[0].startswith("Para el martes 27 de octubre")


def test_a_candidate_who_already_has_a_call_hears_it(store):
    qualify(store)
    say(store, "1")
    words, _ = opening(store)
    assert "ya está reservada" in words and "10:00" not in words and "a las" in words  # said aloud, not "09:00"


def test_a_candidate_the_agent_closed_hears_the_short_closing(store):
    turn.start(store, CLIENT, "c1", NOW)
    say(store, "sí", {"consent": True})
    say(store, "no tengo licencia", {"has_license": False})
    say(store, "correcto", {"confirms_rejection": True})
    words, _ = opening(store)
    assert words and "IA" not in words and store.get("c1").outcome == "DISQUALIFIED"


def test_in_english_the_opening_and_the_language_follow_the_candidate(store):
    turn.start(store, CLIENT, "c1", NOW)
    say(store, "yes", {"consent": True, "language": "en"})
    say(store, "I'm John Smith", {"name": "John Smith"})
    words, language = opening(store)
    assert words.startswith("Let's continue with your application.") and language == "en"


def test_an_unknown_candidate_gets_the_disclosure_without_a_record_being_made(store):
    words, language = opening(store, "nobody")
    assert words == consent_message(CLIENT.spec) and language is None and store.get("nobody") is None
