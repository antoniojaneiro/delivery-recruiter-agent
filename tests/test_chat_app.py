"""D66: the Streamlit chat for trying the agent. It runs the engine's own turn code against a demo database."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from screener.llm import LLMError
from screener.store import Store
from tests.fakes import ScriptedLLM

APP = str(Path(__file__).resolve().parent.parent / "chat_app.py")


@pytest.fixture
def demo(tmp_path, monkeypatch):
    monkeypatch.setenv("SAZON_DEMO_DB", str(tmp_path / "demo.db"))
    monkeypatch.setenv("SAZON_DB", str(tmp_path / "real.db"))
    llm = ScriptedLLM(extractions=[{"name": "Juan Pérez"}, {"name": "Pedro Gil"}])
    monkeypatch.setattr("screener.gemini.from_env", lambda: llm)
    return llm


def start(language=None):
    at = AppTest.from_file(APP, default_timeout=10)
    if language:
        at.session_state["ui_language"] = language
    return at.run()


def demo_store(tmp_path):
    from sazon.client import SAZON_CLIENT
    return Store(tmp_path / "demo.db", calendar=SAZON_CLIENT.calendar)


def candidate_id(at):
    return at.session_state["chat_id"]


def say(at, text):
    at.chat_input[0].set_value(text).run()
    assert not at.exception, at.exception
    return at


def bubbles(at):
    return [str(m.text[0].value) if m.text else "" for m in at.chat_message]


def test_it_opens_with_the_disclosure_and_a_rerun_does_not_say_it_again(demo, tmp_path):
    at = start()
    assert not at.exception, at.exception
    at.run()
    store = demo_store(tmp_path)
    assert [(m.role, "una IA" in m.text) for m in store.messages(candidate_id(at))] == [("agent", True)]
    assert len(at.chat_message) == 1


def test_a_message_is_answered_by_the_real_turn_code_and_saved_in_the_demo_database(demo, tmp_path):
    at = say(start(), "sí")
    texts = [m.text for m in demo_store(tmp_path).messages(candidate_id(at))]
    assert texts[1] == "sí" and "nombre" in texts[2].lower()
    assert len(at.chat_message) == 3
    assert not (tmp_path / "real.db").exists()  # the recruiters' database is never opened


def test_the_inspector_shows_what_the_agent_understood(demo):
    at = say(say(start(), "sí"), "Me llamo Juan Pérez")
    inspector = " ".join(str(e.value) for e in at.json) + " " + " ".join(str(e.value) for e in at.text)
    assert "Juan Pérez" in inspector
    assert any("En curso" in str(e.value) for e in at.text)  # the recruiter card, as recruiters would read it


def test_new_candidate_starts_a_fresh_chat_with_the_disclosure(demo, tmp_path):
    at = say(start(), "sí")
    first = candidate_id(at)
    at.button(key="new_candidate").click().run()
    assert candidate_id(at) != first and len(at.chat_message) == 1


def test_simulating_24_hours_of_silence_sends_the_reminder(demo, tmp_path):
    at = say(start(), "sí")
    at.button(key="wait_24h").click().run()
    assert not at.exception, at.exception
    assert "sigues interesado" in demo_store(tmp_path).messages(candidate_id(at))[-1].text


def test_the_screen_can_be_in_english_and_the_agent_still_speaks_the_candidates_language(demo):
    at = start("en")
    assert at.title[0].value == "Try the assistant"
    assert "una IA" in bubbles(at)[0]  # the disclosure is the bilingual text, whatever the screen language


def test_a_missing_model_key_is_explained_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("SAZON_DEMO_DB", str(tmp_path / "demo.db"))

    def no_key():
        raise LLMError("GEMINI_API_KEY is not set")

    monkeypatch.setattr("screener.gemini.from_env", no_key)
    at = start()
    assert not at.exception and at.error and "GEMINI_API_KEY" in at.error[0].value


def test_a_failure_while_answering_is_shown_without_internals_and_written_to_the_log(demo, tmp_path, monkeypatch):
    from screener import turn
    monkeypatch.setattr("sazon.config.LOG_PATH", tmp_path / "chat.log")

    def boom(*args, **kwargs):
        raise RuntimeError("secret detail")

    at = start()
    monkeypatch.setattr(turn, "handle_message", boom)
    at.chat_input[0].set_value("sí").run()
    assert not at.exception and at.error and "secret detail" not in at.error[0].value
    assert "secret detail" in (tmp_path / "chat.log").read_text(encoding="utf-8")


def test_the_candidates_side_of_the_screen_follows_the_language_the_candidate_writes(demo):
    at = start()  # the screen is in Spanish, the default
    assert at.chat_input[0].placeholder == "Escribe un mensaje"
    at = say(at, "yes")
    assert at.chat_input[0].placeholder == "Write a message"  # the candidate writes English, so their side is English
    assert at.sidebar.button(key="new_candidate").label == "Nuevo candidato"  # the operator's side stays as chosen
