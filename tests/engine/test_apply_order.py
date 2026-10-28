"""D70: the order in which one message is processed, as a table: given what is saved and what is waiting, and what the
model read in the message, the directive that follows and what changed. Most bugs here hide in how the small steps are
called one after the other, not in the steps."""
from datetime import date

import pytest

from sazon.spec import SAZON
from screener.directive import Kind
from screener.model import EventType, Outcome
from screener.screening import Screening

TODAY = date(2026, 10, 26)
AREAS = {"Madrid": [], "Barcelona": [], "Guadalajara": []}
FULL = {"name": "Juan Pérez", "experience": (2, ["glovo"]), "availability": ["full_time"], "schedule": "morning",
        "start_date": date(2026, 11, 2)}


def screening(**answers) -> Screening:
    s = Screening(AREAS, SAZON)
    s.record_consent(True)
    for field, value in answers.items():
        s.submit(field, value, TODAY)
    return s


def waiting_for_area_confirmation() -> Screening:
    s = screening(**FULL)
    s.submit("city", "Madri", TODAY)  # a near miss: "do you mean Madrid?" waits
    assert s.awaiting_confirmation == "Madrid"
    return s


def waiting_for_rejection_confirmation() -> Screening:
    s = screening(**FULL, city="Madrid")
    s.submit("license", False, TODAY)
    assert s.awaiting_rejection == "license"
    return s


def waiting_for_change_confirmation() -> Screening:
    s = screening(**FULL, city="Madrid")
    s.apply(SAZON.extraction_model(name="Carlos López"), "mi nombre es Carlos López", TODAY)
    assert s.awaiting_change
    return s


def read(**fields):
    return SAZON.extraction_model(**fields)


# (what is saved/waiting, what the model read, the message, expected directive kind, expected field, notices)
ROWS = {
    "area confirmed with a yes": (waiting_for_area_confirmation, dict(confirms_city=True), "sí", Kind.ASK, "license", ()),
    "area refused and another given in the same message": (
        waiting_for_area_confirmation, dict(confirms_city=False, city="Barcelona"), "no, vivo en Barcelona",
        Kind.ASK, "license", ()),
    "off-topic while an area waits": (
        waiting_for_area_confirmation, dict(off_topic=True), "cuéntame un chiste", Kind.CONFIRM_AREA, None, ("offtopic",)),
    "a reply that does not answer the waiting place drops the suggestion and asks for the place again": (
        waiting_for_area_confirmation, dict(name="Pedro Gil"), "me llamo Pedro Gil", Kind.FOLLOW_UP, "city", ()),
    "rejection confirmed": (
        waiting_for_rejection_confirmation, dict(confirms_rejection=True), "sí, no tengo", Kind.CLOSE, None, ()),
    "rejection contradicted by a clear yes to the license": (
        waiting_for_rejection_confirmation, dict(has_license=True), "en realidad sí tengo", Kind.CLOSE, None, ()),
    "a reply that does not confirm a waiting rejection clears it and asks the license again": (
        waiting_for_rejection_confirmation, dict(city="Madrid"), "vivo en Madrid", Kind.FOLLOW_UP, "license", ()),
    "a pending change is asked once even if another differs": (
        waiting_for_change_confirmation, dict(schedule="evening"), "mejor por la noche", Kind.CONFIRM_CHANGE, "name", ()),
    "withdraw wins over a pending change": (
        waiting_for_change_confirmation, dict(withdraw=True), "me retiro", Kind.CLOSE, None, ()),
    "several fields in one message": (
        lambda: screening(name="Juan Pérez"),
        dict(experience_years=2.0, platforms=["glovo"], availability=["full_time"]), "2 años con Glovo, tiempo completo",
        Kind.ASK, "start_date", ()),  # full time is the whole day, so the schedule is not asked (D81)
    "a person and pay with a valid answer": (
        lambda: screening(), dict(name="Juan Pérez", wants_human=True, asks_pay=True), "soy Juan Pérez, ¿cuánto pagan?",
        Kind.ASK, "experience", ("human", "pay")),
    "a person alone is not an unclear answer": (
        lambda: screening(), dict(wants_human=True), "quiero hablar con alguien", Kind.ASK, "name", ("human",)),
    "an unclear answer is followed up": (
        lambda: screening(), dict(name="Juan"), "Juan", Kind.FOLLOW_UP, "name", ()),
    "hesitation is a follow-up, never a strike": (
        lambda: screening(), dict(off_topic=True), "mmm", Kind.FOLLOW_UP, "name", ()),
    "an off-topic message gets a redirect and the same question": (
        lambda: screening(), dict(off_topic=True), "cuéntame un chiste", Kind.ASK, "name", ("offtopic",)),
}


@pytest.mark.parametrize("name", list(ROWS))
def test_the_next_directive_follows_the_order_of_the_steps(name):
    setup, fields, message, kind, field, notices = ROWS[name]
    s = setup()
    directive = s.apply(read(**fields), message, TODAY)
    assert (directive.kind, directive.field, directive.notices) == (kind, field, notices)


def test_an_area_refused_and_replaced_in_one_message_is_accepted_and_nothing_is_followed_up():
    s = waiting_for_area_confirmation()
    s.apply(read(confirms_city=False, city="Barcelona"), "no, vivo en Barcelona", TODAY)
    assert s.values["city"] == "Barcelona" and not s.awaiting_confirmation
    assert EventType.FOLLOW_UP not in [kind for kind, _ in s.events[-3:]]


def test_a_rejection_contradicted_by_a_yes_clears_the_wait_and_keeps_the_candidate():
    s = waiting_for_rejection_confirmation()
    s.apply(read(has_license=True), "en realidad sí tengo", TODAY)
    assert s.values["license"] is True and s.awaiting_rejection is None
    assert s.decide().outcome != Outcome.DISQUALIFIED


def test_two_rejecting_answers_in_one_message_ask_for_one_confirmation_at_a_time():
    s = screening(**FULL)
    directive = s.apply(read(has_license=False, city="Sevilla"), "no tengo licencia y vivo en Sevilla", TODAY)
    assert directive.kind == Kind.CONFIRM_REJECTION
    s.confirm_rejection(True)
    assert s.decide().outcome == Outcome.DISQUALIFIED


def test_the_third_off_topic_message_in_total_ends_the_chat_even_after_good_answers():
    s = screening()
    s.apply(read(off_topic=True), "chiste", TODAY)
    s.apply(read(name="Juan Pérez"), "Juan Pérez", TODAY)
    s.apply(read(off_topic=True), "otro chiste", TODAY)
    directive = s.apply(read(off_topic=True), "y otro", TODAY)
    assert directive.kind == Kind.CLOSE and directive.outcome == Outcome.ENDED_OFF_TOPIC


def test_withdrawing_clears_everything_that_was_waiting():
    s = waiting_for_change_confirmation()
    s.apply(read(withdraw=True), "me retiro", TODAY)
    assert not s.awaiting_change and s.decide().outcome == Outcome.WITHDRAWN
