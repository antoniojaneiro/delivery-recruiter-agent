"""D95: on a call a failure is said as what the caller can act on ("I couldn't hear you, please repeat"), in the language of the
call, not as a technical problem. The written chat keeps its own text. A client without spoken texts says the usual one."""
from screener import turn
from screener.channel import VOICE
from screener.llm import LLMError
from sazon.areas import AREAS
from tests.support.booking import NOW, say
from tests.support.clients import client_for
from tests.support.fakes import FakeLLM
from tests.support.tables import table
from tests.support.toy_spec import TOY_UK

SAZON = client_for(AREAS)


@table("language,text", [("es", "No te he oído bien. ¿Puedes repetirlo, por favor?"),
                         ("en", "I couldn't hear you. Could you repeat please?")])
def test_the_spoken_apology_asks_to_repeat_in_the_language_of_the_call(language, text):
    assert turn.technical_error_message(SAZON.spec, language, voice=True) == text


def test_the_written_chat_keeps_saying_it_had_a_technical_problem():
    assert "problema técnico" in turn.technical_error_message(SAZON.spec, "es")


def test_a_client_without_spoken_texts_says_the_usual_one_on_a_call_too():
    assert (turn.technical_error_message(TOY_UK.spec, "en", voice=True) == turn.technical_error_message(TOY_UK.spec, "en"))


def test_when_the_model_fails_on_a_call_the_caller_is_asked_to_repeat(tmp_path):
    from screener.store import Store
    store = Store(tmp_path / "s.db")
    turn.start(store, SAZON, "c1", NOW)
    say(store, "sí", {"consent": True, "language": "es"}, voice=True)
    broken = FakeLLM(LLMError("timeout"))
    reply = turn.handle_message(broken, store, SAZON, "c1", "Juan Pérez", NOW, channel=VOICE)
    assert reply == "No te he oído bien. ¿Puedes repetirlo, por favor?"
