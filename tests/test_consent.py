"""D44: the consent reply is read in plain code, so nothing reaches the model before a yes."""
import pytest

from sazon.consent import read_consent
from sazon.model import Language


@pytest.mark.parametrize("text", [
    "sí", "Sí.", "si", "SÍ!", "vale", "claro", "ok", "OK", "okay", "dale", "adelante", "por supuesto",
    "de acuerdo", "sí, claro", "claro que sí", "me parece bien", "sí por favor", "acepto", "perfecto",
    "yes", "Yes!", "yeah", "yep", "sure", "of course", "that's fine", "yes please", "sounds fine, ok",
    # ways of saying yes that contain the word "no"
    "no hay problema", "No hay problema.", "sin problema", "no pasa nada", "no tengo inconveniente",
    "no problem", "No problem!", "no worries", "ok, no problem",
])
def test_clear_agreement_is_read_as_yes(text):
    assert read_consent(text).answer is True


@pytest.mark.parametrize("text", [
    "no", "No.", "NO", "no gracias", "No, gracias", "no thanks", "No thank you", "no quiero", "no acepto",
    "prefiero que no", "nope", "stop", "para", "no quiero continuar",
])
def test_short_clear_refusals_are_read_as_no(text):
    assert read_consent(text).answer is False


@pytest.mark.parametrize("text", [
    "", "   ", "no sé", "¿no?", "¿sí?", "¿quién eres?", "who are you?", "hola", "hello", "gracias", "ya veremos",
    "depende", "maybe", "sí pero no quiero que guardes nada", "yes but I'd rather you didn't store anything",
    "no, pero sí puedo seguir", "si me aceptan cuánto pagan",
    "me llamo Juan, mi teléfono es 600123123", "no estoy seguro de qué hacéis con mis datos",
    "no hay problema pero no quiero",
    "x" * 300,
])
def test_anything_ambiguous_mixed_long_or_a_question_is_unclear(text):
    assert read_consent(text).answer is None


@pytest.mark.parametrize("text,language", [
    ("sí", Language.ES), ("vale", Language.ES), ("claro", Language.ES), ("no gracias", Language.ES),
    ("no hay problema", Language.ES), ("yes", Language.EN), ("sure", Language.EN), ("no thanks", Language.EN),
    ("no problem", Language.EN), ("ok", None), ("no", None), ("okay", None), ("hello", None),
])
def test_the_language_is_taken_from_the_reply_only_when_it_is_obvious(text, language):
    assert read_consent(text).language == language


@pytest.mark.parametrize("text", [
    "sí, soy Juan Pérez y vivo en Madrid", "Sí. Me llamo Ana", "claro, tengo 3 años de experiencia",
    "yes, I'm John Smith from Madrid", "vale, estoy disponible por las mañanas", "ok, soy Luis",
])
def test_a_clear_yes_followed_by_more_information_is_a_yes_and_the_rest_is_ignored(text):
    assert read_consent(text).answer is True


@pytest.mark.parametrize("text", [
    "sí, pero ¿qué hacéis con mis datos?", "sí, pero no quiero que guardes mi teléfono",
    "yes, but please don't keep my phone number", "sí, no sé", "claro, nunca doy mis datos",
    "si me aceptan, cuánto pagan", "sí, soy Juan y no quiero que se guarde",
])
def test_a_yes_with_a_condition_a_question_or_a_no_is_unclear(text):
    assert read_consent(text).answer is None


from sazon.consent import is_stop_request


@pytest.mark.parametrize("text", [
    "para", "Para.", "stop", "STOP!", "basta", "me retiro", "me retiro, gracias", "me doy de baja", "cancelar",
    "no quiero continuar", "ya no quiero continuar", "no quiero seguir", "ya no me interesa", "please stop",
    "I want to stop", "I want to withdraw", "I quit", "unsubscribe", "cancel my application",
])
def test_clear_stop_requests_are_recognised_without_the_model(text):
    assert is_stop_request(text) is True


@pytest.mark.parametrize("text", [
    "", "para ser sincero tengo 2 años de experiencia", "para trabajar de mañanas", "no quiero continuar sin saber el sueldo",
    "no sé", "stop by tomorrow", "mi nombre es Pablo Stop Gil", "¿puedo parar un momento?", "cancelar la cita de ayer",
    "sí", "Madrid", "I can start stopping by", "me retiro del trabajo anterior hace dos años",
])
def test_ordinary_messages_that_contain_stop_words_are_not_stop_requests(text):
    assert is_stop_request(text) is False
