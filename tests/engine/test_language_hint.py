"""D67: the language of the chat changes only when the candidate's words show it. A name or a place says nothing."""
from datetime import date

import pytest

from screener.language_hint import language_of
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
