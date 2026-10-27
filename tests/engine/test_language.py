"""D67: the language of the chat changes only when the candidate's words show it. A name or a place says nothing."""
from datetime import date

import pytest

from screener.language import language_of
from screener.model import Language
from sazon.spec import SAZON
from screener.screening import Screening

ES, EN = Language.ES, Language.EN


@pytest.mark.parametrize("message", ["Madrid", "Madrid, Spain", "Maria Lopez", "Guadalajara", "42", "Zapopan", "CDMX"])
def test_a_name_a_place_or_a_number_never_changes_the_language(message):
    assert language_of(message, ES, EN) == EN and language_of(message, EN, ES) == ES


@pytest.mark.parametrize("message", ["I live in Madrid", "Full time please", "I can work 2 days a week",
                                     "I have three years of experience", "Part time", "next Monday please"])
def test_english_words_switch_to_english_even_if_the_model_said_spanish(message):
    assert language_of(message, ES, ES) == EN and language_of(message, EN, ES) == EN


@pytest.mark.parametrize("message", ["Vivo en Madrid", "Tiempo completo, por favor", "Tengo tres años de experiencia",
                                     "Puedo empezar el lunes", "Por las mañanas"])
def test_spanish_words_switch_to_spanish_even_if_the_model_said_english(message):
    assert language_of(message, EN, EN) == ES and language_of(message, ES, EN) == ES


def test_a_longer_message_in_a_language_with_no_known_word_follows_the_model():
    assert language_of("ich wohne seit langem sehr nahe einer kleinen stadt", EN, ES) == EN  # nothing to check it against
    assert language_of("ich wohne seit langem sehr nahe einer kleinen stadt", None, ES) == ES


def test_a_tie_keeps_the_current_language():
    assert language_of("tiempo full", EN, ES) == ES and language_of("tiempo full", ES, EN) == EN


TODAY = date(2026, 10, 26)


def chat_in(language):
    s = Screening({"Madrid": []}, SAZON)
    s.record_consent(True)
    s.language = language
    return s


def test_the_chat_stays_in_english_when_the_candidate_names_a_place():
    s = chat_in(EN)
    s.apply(SAZON.extraction_model(language=ES), "Madrid", TODAY)
    assert s.language == EN


def test_the_chat_switches_back_when_the_candidate_writes_in_the_other_language():
    s = chat_in(ES)
    s.apply(SAZON.extraction_model(), "I can work 2 days a week", TODAY)
    assert s.language == EN


# --- the shared helpers (D70) -------------------------------------------------------------------------------------

from screener.language import fold, pick, plain, strip_accents  # noqa: E402


def test_accents_and_case_are_removed_in_one_way_everywhere():
    assert strip_accents("Ñandú Álvarez") == "Nandu Alvarez"
    assert fold("  Ñandú   ÁLVAREZ ") == "nandu alvarez"
    assert plain("¡Sí, claro!  ¿Vale?") == "si claro vale"
    assert plain("Part-Time") == "part time" and plain("") == ""


def test_a_text_is_picked_in_the_language_asked_for_else_in_the_default():
    text = {ES: "hola", EN: "hello"}
    assert pick(text, EN, ES) == "hello" and pick(text, "es", EN) == "hola"
    assert pick({ES: "hola"}, EN, ES) == "hola"      # no English: the client's default
    assert pick({ES: "hola"}, None, ES) == "hola"    # no language known yet
    with pytest.raises(KeyError):
        pick({EN: "hello"}, ES, ES)                    # the default itself is missing: a spec problem, not a fallback


def test_the_terminal_chat_apologises_in_the_clients_default_language_not_always_spanish(tmp_path, monkeypatch):
    from datetime import datetime

    from screener import chat, turn
    from screener.store import Store
    from tests.support.fakes import ScriptedLLM
    from tests.support.toy_spec import TOY_CLIENT

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(turn, "handle_message", boom)
    lines, out = iter(["hello", "/quit"]), []
    chat.run(ScriptedLLM(), Store(tmp_path / "t.db"), TOY_CLIENT, read=lambda prompt: next(lines), write=out.append,
             clock=lambda: datetime(2026, 10, 26, 10, 0))
    assert any("Something went wrong" in line for line in out)
