"""D93: the chat page's "Talk to Sofía" button. It only works when the live voice agent has been set up (a key and an agent), makes
a voice session for the current candidate, asks ElevenLabs for a signed address and shows the call; ending the call or
starting another candidate removes it. The spoken turns themselves arrive through the voice endpoint, not this page."""
import json
from datetime import datetime

import pytest
from streamlit.testing.v1 import AppTest

from sazon import config
from sazon.client import SAZON_CLIENT
from sazon.voice_component import call_html
from screener.phrasing import consent_message
from screener.store import Store
from screener.voice_agent import ElevenLabs, VoiceSetupError
from tests.support.fakes import ScriptedLLM
from tests.support.paths import CHAT_APP

APP = str(CHAT_APP)


@pytest.fixture
def chat(tmp_path, monkeypatch):
    monkeypatch.setenv("SAZON_DB", str(tmp_path / "real.db"))
    monkeypatch.setenv("ELEVENLABS_API_KEY", "key-123")
    monkeypatch.setattr("screener.gemini.from_env", lambda: ScriptedLLM())
    monkeypatch.setattr(config, "VOICE_STATE_PATH", tmp_path / "voice.json")
    monkeypatch.setattr(ElevenLabs, "signed_url", lambda self, agent_id: f"wss://signed.example/{agent_id}?sig=abc")
    return Store(tmp_path / "real.db", calendar=SAZON_CLIENT.calendar), tmp_path


def set_up(tmp_path):
    (tmp_path / "voice.json").write_text(json.dumps({"agent_id": "agent_1", "secret_id": "s1", "secret": "shh"}), encoding="utf-8")


def opened(language="es"):
    at = AppTest.from_file(APP, default_timeout=20)
    at.session_state["ui_language"] = language
    return at.run()


def test_the_button_is_off_and_says_how_to_set_it_up_until_the_voice_agent_exists(chat):
    at = opened()
    assert at.sidebar.button(key="voice_start").disabled and any("voice_launch" in str(c.value) for c in at.sidebar.caption)


def test_the_button_is_off_without_the_elevenlabs_key_even_with_an_agent(chat, monkeypatch):
    set_up(chat[1])
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    assert opened().sidebar.button(key="voice_start").disabled


def test_starting_a_call_makes_a_session_for_this_candidate_and_ending_it_removes_the_call(chat):
    store, tmp_path = chat
    set_up(tmp_path)
    at = opened()
    assert not at.sidebar.button(key="voice_start").disabled
    at.sidebar.button(key="voice_start").click().run()
    assert not at.exception, at.exception
    call = at.session_state["voice_call"]
    assert call["opening"] == consent_message(SAZON_CLIENT.spec) and call["language"] is None  # a new candidate: the disclosure
    assert store.voice_session_candidate(call["session"], datetime.now()) == at.session_state["chat_id"]
    assert call["url"] == "wss://signed.example/agent_1?sig=abc"
    assert [b for b in at.sidebar.button if b.key == "voice_end"] and not [b for b in at.sidebar.button if b.key == "voice_start"]
    at.sidebar.button(key="voice_end").click().run()
    assert "voice_call" not in at.session_state


def test_another_candidate_ends_the_call(chat):
    set_up(chat[1])
    at = opened()
    at.sidebar.button(key="voice_start").click().run()
    first = at.session_state["chat_id"]
    at.sidebar.button(key="new_candidate").click().run()
    assert at.session_state["chat_id"] != first and "voice_call" not in at.session_state


def test_a_refusal_from_elevenlabs_is_explained_and_no_call_starts(chat, monkeypatch):
    set_up(chat[1])

    def refuse(self, agent_id):
        raise VoiceSetupError("ElevenLabs answered 401")

    monkeypatch.setattr(ElevenLabs, "signed_url", refuse)
    at = opened()
    at.sidebar.button(key="voice_start").click().run()
    assert not at.exception, at.exception
    assert "voice_call" not in at.session_state and any("voz" in str(w.value).lower() for w in at.warning)


def test_the_call_page_holds_the_address_and_the_session_safely_and_no_api_key():
    html = call_html("wss://signed.example/a?sig=1", "sess_1", "es", "Hola, sigamos", "es")
    assert "wss://signed.example/a?sig=1" in html and "sess_1" in html and "key-123" not in html
    assert "Hola, sigamos" in html and 'language: "es"' in html  # what is said first, and the language to say it in
    assert "customLlmExtraBody" not in html  # ElevenLabs refuses a call that sends it: the agent does not allow that override
    assert "voice_session: session" in html  # the session goes as a dynamic variable, which the prompt carries to our endpoint
    assert "onError: (message)" in html and "onDisconnect: (details)" in html  # the reason a call ended is shown, not hidden
    hostile = call_html('wss://x"</script><script>alert(1)</script>', "s'\"<", "en", "x</script><b>", None)
    assert "</script><script>alert(1)" not in hostile and hostile.count("</script>") == 1 and "overrides" not in hostile
    assert "Listening" in call_html("wss://x", "s", "en", "o", None) and "Escuchando" in call_html("wss://x", "s", "es", "o", None)


def test_a_call_started_midway_opens_with_where_they_were_not_with_the_consent_question(chat):
    from tests.support.booking import say
    store, tmp_path = chat
    set_up(tmp_path)
    at = opened()
    cid = at.session_state["chat_id"]
    say(store, "sí", {"consent": True, "language": "es"}, cid=cid)
    say(store, "Soy Juan Pérez", {"name": "Juan Pérez"}, cid=cid)
    at.run()
    at.sidebar.button(key="voice_start").click().run()
    call = at.session_state["voice_call"]
    assert call["opening"].startswith("Sigamos con tu solicitud.") and call["language"] == "es"
    assert [m.text for m in store.messages(cid)][-1] == call["opening"]  # saved: the transcript shows what was heard


def test_when_the_conversation_is_over_the_button_is_off_and_says_so(chat):
    from tests.support.booking import say
    store, tmp_path = chat
    set_up(tmp_path)
    at = opened()
    cid = at.session_state["chat_id"]
    say(store, "sí", {"consent": True}, cid=cid)
    say(store, "no tengo licencia", {"has_license": False}, cid=cid)
    say(store, "correcto", {"confirms_rejection": True}, cid=cid)  # turned down by text: nothing left to say
    at.run()
    button = at.sidebar.button(key="voice_start")
    assert button.disabled and button.label == "Conversación terminada"


def test_after_a_voice_call_that_finished_the_button_says_the_call_was_already_made(chat):
    from tests.support.booking import say
    store, tmp_path = chat
    set_up(tmp_path)
    at = opened()
    cid = at.session_state["chat_id"]
    store.new_voice_session(cid, datetime.now())  # a call was held
    say(store, "sí", {"consent": True}, cid=cid)
    say(store, "me retiro", {}, cid=cid)
    at.run()
    button = at.sidebar.button(key="voice_start")
    assert button.disabled and button.label == "Llamada ya realizada"
    assert "voice_call" not in at.session_state


def test_a_conversation_that_is_over_cannot_start_a_call_even_if_the_button_is_pressed_late(chat):
    from tests.support.booking import say
    store, tmp_path = chat
    set_up(tmp_path)
    at = opened()
    cid = at.session_state["chat_id"]
    say(store, "sí", {"consent": True}, cid=cid)
    say(store, "me retiro", {}, cid=cid)  # over after the page was drawn: the button still looked pressable
    at.sidebar.button(key="voice_start").click().run()
    assert "voice_call" not in at.session_state and not store.voice_session_candidate("x", datetime.now())


def test_the_call_page_closes_the_call_on_the_page_when_the_call_ends_by_itself():
    html = call_html("wss://x", "s", "es", "o", None)
    assert ".st-key-voice_end button" in html and 'reason === "agent"' in html and 'reason === "user"' in html
    assert 'reason === "error"' not in html  # an error stays on screen so its reason can be read


def test_the_page_closes_a_finished_call_itself_after_a_short_grace_if_the_call_page_could_not():
    from datetime import timedelta
    from sazon.voice_component import call_should_close
    started = datetime(2026, 10, 29, 12, 0, 0)
    assert call_should_close(None, started) is False  # the conversation is not over
    assert call_should_close(started, started + timedelta(seconds=10)) is False  # the farewell may still be being spoken
    assert call_should_close(started, started + timedelta(seconds=31)) is True
