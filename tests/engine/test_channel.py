"""D94: a channel is a small settings value, not a flag passed around. Text, button and voice each say how times are offered, who
words the reply, whether a file can be sent and how a time is said; `effective` is the one place that falls back when the client
lacks what a channel needs (no spoken texts, no button texts). The candidate's usual channel is saved (text or button); voice is
per message, and what runs without a message (the reminder, a cancelled call) never uses it."""
from datetime import datetime

import pytest

from sazon.areas import AREAS
from sazon.client import SAZON_CALENDAR
from screener import reminders, turn
from screener.channel import BUTTON, TEXT, VOICE, effective
from screener.store import Store
from tests.support.booking import NOW, hire, qualify, say
from tests.support.clients import client_for
from tests.support.tables import table
from tests.support.toy_spec import TOY_UK

SAZON = client_for(AREAS)  # has spoken texts and button texts


def test_each_channel_says_how_it_offers_times_who_words_the_reply_and_whether_a_file_can_be_sent():
    assert (TEXT.offer, TEXT.model_words, TEXT.accepts_cv, TEXT.spoken_labels) == ("list", True, True, False)
    assert (BUTTON.offer, BUTTON.model_words, BUTTON.accepts_cv, BUTTON.spoken_labels) == ("button", True, True, False)
    assert (VOICE.offer, VOICE.model_words, VOICE.accepts_cv, VOICE.spoken_labels) == ("spoken", False, False, True)


@table("channel,client,offer", [
    (TEXT, SAZON, "list"), (BUTTON, SAZON, "button"), (VOICE, SAZON, "spoken"),
    (TEXT, TOY_UK, "list"), (BUTTON, TOY_UK, "list"), (VOICE, TOY_UK, "list"),  # the second client has no button or spoken texts
])
def test_a_channel_falls_back_to_the_list_when_the_client_lacks_what_it_needs(channel, client, offer):
    assert effective(channel, client).offer == offer


def test_voice_without_spoken_texts_offers_the_list_named_as_in_writing_but_has_no_model_wording_and_no_cv():
    fallback = effective(VOICE, TOY_UK)
    assert (fallback.offer, fallback.model_words, fallback.accepts_cv, fallback.spoken_labels) == ("list", False, False, False)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "s.db", calendar=SAZON_CALENDAR)
    hire(s, "Ana")
    return s


@pytest.mark.parametrize("home,expect", [(False, "1) "), (True, "botón")])
def test_the_reminder_and_a_cancelled_call_use_the_candidates_usual_channel_never_voice(store, home, expect):
    qualify(store, buttons=home, voice=True)  # they were asked the day by voice
    assert store.get("c1").state["voice_booking"]["stage"] == "day"
    reminders.run_once(store, SAZON, datetime(2026, 10, 26, 12, 0))
    told = store.outbox_pending("c1")[-1].text
    assert expect in told and "qué día" not in told.lower()
    assert store.get("c1").state["voice_booking"] is None  # the written offer replaced the spoken one


def test_the_usual_channel_is_saved_as_before_the_state_key_is_unchanged(store):
    turn.start(store, SAZON, "c1", NOW, channel=BUTTON)
    turn.start(store, SAZON, "c2", NOW)
    assert store.get("c1").state["buttons"] is True and store.get("c2").state["buttons"] is False


def test_a_message_can_name_its_channel_and_otherwise_uses_the_usual_one(store):
    spoken = qualify(store, "c1", buttons=True, voice=True)  # a button candidate who answers by voice is asked the day
    written = qualify(store, "c2", buttons=True)
    assert "día" in spoken.lower() and "1)" not in spoken
    assert "reserva una llamada" in written and "día" not in written.lower()  # the page's button, not a question
