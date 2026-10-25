import pytest

from sazon.llm import LLMError
from sazon.model import Field, Outcome
from sazon.phrasing import Directive, Kind, consent_message, phrase
from tests.fakes import FakeLLM


def test_the_consent_message_is_fixed_bilingual_and_discloses_the_ai():
    text = consent_message()
    assert "asistente virtual" in text and "virtual assistant" in text
    assert text.count("?") == 2


def test_a_good_llm_reply_is_used_as_is():
    llm = FakeLLM("¿Cómo te llamas? Necesito nombre y apellido.")
    out = phrase(llm, Directive(Kind.ASK, field=Field.NAME), "es")
    assert out == "¿Cómo te llamas? Necesito nombre y apellido."


def test_the_prompt_names_the_directive_and_language_and_holds_no_candidate_text():
    llm = FakeLLM("What is your last name?")
    phrase(llm, Directive(Kind.FOLLOW_UP, field=Field.NAME, reason="need first and last name"), "en")
    call = llm.calls[0]
    assert "name" in call["user"] and "need first and last name" in call["user"]
    assert "English" in call["user"] and call["json_mode"] is False
    assert "tú" in call["system"] and "one question" in call["system"]


@pytest.mark.parametrize("bad", [
    "", "   ", "x" * 400, "¿Cuál es tu nombre? ¿Y tu ciudad?", "Mira https://example.com ahora", "Ok\n\n\nlargo\n\n\ntexto",
])
def test_unusable_llm_text_falls_back_to_the_template(bad):
    out = phrase(FakeLLM(bad), Directive(Kind.ASK, field=Field.CITY), "es")
    assert out and out != bad and "ciudad" in out.lower()


def test_an_unreachable_llm_falls_back_to_the_template_in_the_right_language():
    out = phrase(FakeLLM(LLMError("429")), Directive(Kind.ASK, field=Field.LICENSE), "en")
    assert "license" in out.lower()


def test_a_city_confirmation_names_the_suggested_city_even_in_the_fallback():
    out = phrase(FakeLLM(LLMError("x")), Directive(Kind.CONFIRM_CITY, suggestion="Guadalajara"), "es")
    assert "Guadalajara" in out


def test_every_ask_has_a_template_in_both_languages():
    for lang in ("es", "en"):
        for field in Field:
            if field is Field.CONSENT:
                continue
            assert phrase(FakeLLM(LLMError("x")), Directive(Kind.ASK, field=field), lang)


def test_the_qualified_close_is_fixed_and_never_invents_a_call_time():
    llm = FakeLLM("¡Perfecto! Te llamamos mañana a las 10.")
    out = phrase(llm, Directive(Kind.CLOSE, outcome=Outcome.QUALIFIED), "es")
    assert llm.calls == [] and "48" in out


def test_a_disqualification_close_is_polite_and_gives_the_reason():
    out = phrase(FakeLLM(LLMError("x")), Directive(Kind.CLOSE, outcome=Outcome.DISQUALIFIED,
                                                   reasons=["NO_LICENSE"]), "en")
    assert "license" in out.lower()
