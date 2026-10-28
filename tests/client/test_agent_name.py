"""D72: the agent introduces itself as Sofía, and still says plainly that it is an AI."""
from sazon.pack import PACK
from sazon.spec import SAZON
from screener.model import Language
from screener.phrasing import consent_message


def test_the_first_message_names_the_agent_and_still_says_it_is_an_ai():
    assert "soy Sofía" in PACK.consent[Language.ES] and "una IA" in PACK.consent[Language.ES]
    assert "I'm Sofía" in PACK.consent[Language.EN] and "an AI" in PACK.consent[Language.EN]
    assert consent_message(SAZON).count("Sofía") == 2


def test_the_answer_to_a_request_for_a_person_keeps_the_name_and_the_honesty():
    assert "Sofía" in PACK.notices["human"][Language.ES] and "Sofía" in PACK.notices["human"][Language.EN]
    assert "virtual" in PACK.notices["human"][Language.ES]


def test_the_model_is_told_its_name_so_it_never_invents_another():
    assert "Sofía" in SAZON.persona
    from screener.phrasing import _system_prompt
    assert "Sofía" in _system_prompt(SAZON)
