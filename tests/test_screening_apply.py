"""The rules that decide what to say next, tested directly with no model and no store."""
from datetime import date

import pytest

from screener.consent import ConsentReading
from sazon.spec import SAZON, Extraction
from screener.model import Language, Outcome
from sazon.fields import Field, Reason
from screener.phrasing import Kind
from screener.screening import Screening

AREAS = {"Madrid": [], "Guadalajara": []}
TODAY = date(2026, 10, 25)


@pytest.fixture
def consented():
    s = Screening(AREAS, SAZON)
    s.record_consent(True)
    return s


def test_a_clear_yes_asks_the_first_question_and_sets_the_language():
    s = Screening(AREAS, SAZON)
    directive = s.apply_consent_reply(ConsentReading(True, Language.EN))
    assert (directive.kind, directive.field) == (Kind.ASK, Field.NAME) and s.language == Language.EN
    assert not s.needs_consent


def test_a_clear_no_closes_with_no_consent():
    directive = Screening(AREAS, SAZON).apply_consent_reply(ConsentReading(False))
    assert directive.kind == Kind.CLOSE and directive.reasons == [Reason.NO_CONSENT]


def test_an_unclear_reply_changes_nothing_and_asks_the_question_again():
    s = Screening(AREAS, SAZON)
    assert s.apply_consent_reply(ConsentReading(None)) is None
    assert s.needs_consent and s.events == []


def test_a_valid_answer_moves_on_to_the_next_field(consented):
    directive = consented.apply(Extraction(name="Juan Pérez"), "Juan Pérez", TODAY)
    assert (directive.kind, directive.field) == (Kind.ASK, Field.EXPERIENCE)


def test_an_unclear_answer_gets_a_follow_up_naming_the_field_and_the_reason(consented):
    directive = consented.apply(Extraction(name="Juan"), "Juan", TODAY)
    assert (directive.kind, directive.field) == (Kind.FOLLOW_UP, Field.NAME) and directive.reason


def test_a_message_with_nothing_usable_counts_against_the_field_being_asked(consented):
    for _ in range(5):
        assert consented.apply(Extraction(), "mmm", TODAY).kind == Kind.FOLLOW_UP
    directive = consented.apply(Extraction(), "mmm", TODAY)
    assert (directive.kind, directive.field) == (Kind.BLOCKED, Field.NAME)


def test_an_off_topic_message_does_not_count_against_the_field(consented):
    consented.apply(Extraction(off_topic=True), "¿qué tiempo hace?", TODAY)
    assert consented.extracted() == {} and consented.decide().outcome == Outcome.IN_PROGRESS


def test_withdrawing_closes_the_chat(consented):
    directive = consented.apply(Extraction(withdraw=True), "para", TODAY)
    assert directive.kind == Kind.CLOSE and directive.outcome == Outcome.WITHDRAWN


def test_a_rejecting_answer_asks_for_confirmation_first(consented):
    directive = consented.apply(Extraction(has_license=False), "no tengo", TODAY)
    assert (directive.kind, directive.field) == (Kind.CONFIRM_REJECTION, Field.LICENSE)


def test_years_and_platform_given_separately_make_one_experience_answer(consented):
    consented.apply(Extraction(experience_years=2), "2 años", TODAY)
    consented.apply(Extraction(platforms=["Glovo"]), "Glovo", TODAY)
    assert consented.extracted()["experience"] == {"years": 2, "platforms": ["glovo"]}


def test_the_extraction_context_tells_the_model_what_was_asked(consented):
    consented.apply(Extraction(name="Juan"), "Juan", TODAY)
    context = consented.extraction_context()
    assert (context.asking, context.previous_answer) == (Field.NAME, "Juan")
    consented.apply(Extraction(city="Guadalajra"), "Guadalajra", TODAY)
    assert consented.extraction_context().awaiting_confirmation == "Guadalajara"


def test_silence_sends_one_reminder_then_stalls_and_does_nothing_once_closed(consented):
    assert consented.on_silence().kind == Kind.REMINDER
    assert consented.on_silence() is None and consented.decide().outcome == Outcome.STALLED
    done = Screening(AREAS, SAZON)
    done.record_consent(False)
    assert done.on_silence() is None


def test_events_count_as_saved_once_and_are_restored_if_saving_fails(consented):
    consented.human_requested()
    with consented.syncing_events() as new:
        assert [kind for kind, _ in new][-1] == "human_requested"
    with consented.syncing_events() as new:
        assert new == []
    consented.off_topic()
    with pytest.raises(RuntimeError):
        with consented.syncing_events():
            raise RuntimeError("disk full")
    with consented.syncing_events() as new:
        assert [kind for kind, _ in new] == ["off_topic"]
