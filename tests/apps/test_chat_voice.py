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
    html = call_html("wss://signed.example/a?sig=1", "sess_1", "es")
    assert "wss://signed.example/a?sig=1" in html and "sess_1" in html and "key-123" not in html
    hostile = call_html('wss://x"</script><script>alert(1)</script>', "s'\"<", "en")
    assert "</script><script>alert(1)" not in hostile and hostile.count("</script>") == 1
    assert "Listening" in call_html("wss://x", "s", "en") and "Escuchando" in call_html("wss://x", "s", "es")
