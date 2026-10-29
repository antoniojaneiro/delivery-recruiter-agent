"""D93: when a spoken call should end. The engine knows when there is nothing more to say: the call is booked, the candidate was
turned down, withdrew, was ended for off-topic messages, or took none of the times. It says so from what is saved, so the answer
is the same on a repeated call."""
from datetime import datetime

import pytest

from sazon.areas import AREAS
from sazon.client import SAZON_CALENDAR
from screener import turn
from screener.store import Store
from tests.support.booking import NOW, hire, qualify, say
from tests.support.clients import client_for

CLIENT = client_for(AREAS)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "s.db", calendar=SAZON_CALENDAR)
    hire(s, "Ana")
    return s


def over(store, cid="c1"):
    return turn.conversation_is_over(store, CLIENT, cid)


def test_a_conversation_still_going_is_not_over(store):
    turn.start(store, CLIENT, "c1", NOW)
    assert not over(store)
    say(store, "sí", {"consent": True}, voice=True)
    say(store, "Soy Juan Pérez", {"name": "Juan Pérez"}, voice=True)
    assert not over(store)


def test_a_qualified_candidate_is_not_done_until_the_call_is_booked_or_they_decline_it(store):
    qualify(store, voice=True)
    assert not over(store)  # asked which day
    say(store, "el martes", voice=True)
    assert not over(store)  # asked which time
    say(store, "a las 10", voice=True)
    assert over(store) and store.booking_of("c1")


def test_declining_every_time_ends_it_too(store):
    qualify(store, voice=True)
    say(store, "ninguno", voice=True)
    assert over(store) and store.booking_of("c1") is None


@pytest.mark.parametrize("answers,outcome", [
    ([("no tengo licencia", {"has_license": False}), ("correcto", {"confirms_rejection": True})], "DISQUALIFIED"),
    ([("me retiro", {})], "WITHDRAWN"),
])
def test_a_candidate_who_is_turned_down_or_withdraws_ends_it(store, answers, outcome):
    turn.start(store, CLIENT, "c1", NOW)
    say(store, "sí", {"consent": True}, voice=True)
    for message, extraction in answers[:-1]:
        say(store, message, extraction, voice=True)
        assert not over(store)  # the confirmation is still to come
    say(store, answers[-1][0], answers[-1][1], voice=True)
    assert store.get("c1").outcome == outcome and over(store)


def test_declining_the_consent_ends_it_and_an_unknown_candidate_is_not_over(store):
    turn.start(store, CLIENT, "c1", NOW)
    say(store, "no", {"consent": False}, voice=True)
    assert over(store) and not over(store, "nobody")
