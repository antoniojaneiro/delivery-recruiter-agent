"""D66: the Streamlit chat for trying the agent. It runs the engine's own turn code against a demo database."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tests.support.paths import CHAT_APP
from screener.llm import LLMError
from screener.store import Store
from tests.support.fakes import ScriptedLLM

APP = str(CHAT_APP)


@pytest.fixture
def demo(tmp_path, monkeypatch):
    monkeypatch.setenv("SAZON_DB", str(tmp_path / "real.db"))
    llm = ScriptedLLM(extractions=[{"name": "Juan Pérez"}, {"name": "Pedro Gil"}])
    monkeypatch.setattr("screener.gemini.from_env", lambda: llm)
    return llm


def start(language=None):
    at = AppTest.from_file(APP, default_timeout=10)
    if language:
        at.session_state["ui_language"] = language
    return at.run()


def saved_store(tmp_path):
    from sazon.client import SAZON_CLIENT
    return Store(tmp_path / "real.db", calendar=SAZON_CLIENT.calendar)


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
    store = saved_store(tmp_path)
    assert [(m.role, "una IA" in m.text) for m in store.messages(candidate_id(at))] == [("agent", True)]
    assert len(at.chat_message) == 1


def test_a_message_is_answered_by_the_real_turn_code_and_saved_in_the_recruiters_database(demo, tmp_path):
    at = say(start(), "sí")
    texts = [m.text for m in saved_store(tmp_path).messages(candidate_id(at))]
    assert texts[1] == "sí" and "nombre" in texts[2].lower()
    assert len(at.chat_message) == 3
    assert not at.sidebar.toggle  # there is no switch: the chat always saves where the dashboard reads


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
    assert "sigues interesado" in saved_store(tmp_path).messages(candidate_id(at))[-1].text


def test_the_screen_can_be_in_english_and_the_agent_still_speaks_the_candidates_language(demo):
    at = start("en")
    assert at.title[0].value == "Try the assistant"
    assert "una IA" in bubbles(at)[0]  # the disclosure is the bilingual text, whatever the screen language


def test_a_missing_model_key_is_explained_not_a_crash(tmp_path, monkeypatch):

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


# --- the optional CV upload (D71) ------------------------------------------------------------------------------

def test_the_uploader_appears_after_consent_with_its_notice_and_goes_away_once_the_candidate_types_an_answer(demo):
    at = start()
    assert at.get("file_uploader") == []  # nothing to upload before consent
    at = say(at, "sí")
    [uploader] = at.get("file_uploader")
    assert "PDF" in uploader.proto.label
    assert any("2 MB" in str(c.value) and "borre" in str(c.value) for c in at.caption)
    at = say(at, "Me llamo Juan Pérez")
    assert at.get("file_uploader") == []


def test_the_uploader_notice_follows_the_language_of_the_candidate(demo):
    at = say(start(), "yes")
    assert any("recruiting team" in str(c.value) for c in at.caption)


def upload(at, data, name="cv.pdf"):
    at.file_uploader[0].set_value((name, data, "application/pdf")).run()
    assert not at.exception, at.exception
    return at


def test_uploading_a_cv_in_the_browser_fills_answers_reads_them_back_and_removes_the_uploader(demo, tmp_path):
    from tests.support.pdfs import pdf_with_text
    at = upload(say(start(), "sí"), pdf_with_text("Juan Perez", "Madrid"))
    assert any("He leído tu CV" in text for text in bubbles(at))
    assert at.get("file_uploader") == []  # the offer is over: a second file cannot be sent
    store = saved_store(tmp_path)
    assert store.cv(candidate_id(at)) is not None and store.get(candidate_id(at)).extracted["name"] == "Juan Pérez"


def test_a_text_file_renamed_to_pdf_is_refused_once_with_a_warning_and_the_offer_stays(demo, tmp_path):
    at = upload(say(start(), "sí"), b"just some words, not a pdf", name="cv.pdf")
    assert any("PDF de hasta 2 MB" in str(w.value) for w in at.warning)
    assert len(at.get("file_uploader")) == 1 and saved_store(tmp_path).cv(candidate_id(at)) is None
    at.run()  # nothing is said again on the next rerun
    assert not any("PDF de hasta 2 MB" in str(w.value) for w in at.warning)


def test_a_scanned_pdf_is_kept_and_the_questions_go_on(demo, tmp_path):
    from tests.support.pdfs import pdf_without_text
    at = upload(say(start(), "sí"), pdf_without_text())
    assert any("No he podido sacar datos" in text for text in bubbles(at))
    assert saved_store(tmp_path).cv(candidate_id(at)) is not None


# --- sharing candidates with the dashboard (D73) ---------------------------------------------------------------

def test_a_candidate_who_finishes_in_the_shared_chat_shows_up_in_the_dashboard(tmp_path, monkeypatch):
    """Both apps, one database file: the whole conversation in the chat, then the recruiter's table."""
    from tests.support.dash import login, seed_accounts
    from tests.support.paths import DASHBOARD
    monkeypatch.setenv("SAZON_DB", str(tmp_path / "real.db"))
    monkeypatch.setenv("SAZON_ACCOUNTS", str(tmp_path / "recruiters.json"))
    everything = {"name": "Juan Pérez", "experience_years": 2, "platforms": ["glovo"], "availability": ["full_time"],
                  "schedule": "morning", "start_date": {"in_weeks": 1}, "city": "Madrid", "has_license": True}
    monkeypatch.setattr("screener.gemini.from_env", lambda: ScriptedLLM(extractions=[everything]))
    at = start()
    shared = candidate_id(at)
    say(say(at, "sí"), "Me llamo Juan Pérez, 2 años en Glovo, tiempo completo, mañanas, en una semana, vivo en Madrid y tengo licencia")
    assert saved_store(tmp_path).get(shared).outcome == "QUALIFIED"

    seed_accounts(tmp_path / "recruiters.json")
    dashboard = AppTest.from_file(str(DASHBOARD), default_timeout=10).run()
    login(dashboard, "Ana")
    assert not dashboard.exception, dashboard.exception
    row = next(r for _, r in dashboard.dataframe[0].value.iterrows() if r["Id"] == shared)
    assert row["Nombre"] == "Juan Pérez" and row["Agente"] == "Cualificado"


@pytest.fixture
def spinners(monkeypatch):
    """The texts shown while the agent is working (a spinner is gone by the time a run ends, so they are recorded)."""
    from contextlib import contextmanager
    import streamlit as st
    shown = []

    @contextmanager
    def recording(text="", **kwargs):
        shown.append(text)
        yield

    monkeypatch.setattr(st, "spinner", recording)
    return shown


def test_the_typing_text_follows_the_language_of_the_message_even_on_the_first_one(demo, spinners):
    at = start("es")  # the page is in Spanish; nothing is saved yet about the candidate's language
    say(at, "yes")
    assert spinners and spinners[-1] == "The assistant is typing…"


def test_the_typing_text_follows_the_language_the_candidate_switches_to(demo, spinners):
    at = say(start("en"), "sí")
    say(at, "Me llamo Juan Pérez")
    assert spinners[-1] == "El asistente está escribiendo…"


def test_a_failed_turn_is_told_in_the_language_of_the_message(demo, monkeypatch, tmp_path):
    monkeypatch.setattr("sazon.config.LOG_PATH", tmp_path / "errors.log")  # not the real log
    at = start("es")
    monkeypatch.setattr("screener.turn.handle_message", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    at.chat_input[0].set_value("yes please").run()
    from sazon.ui_pack import PACK
    assert PACK.get("chat.failed", "en") in [str(e.value) for e in at.error]
