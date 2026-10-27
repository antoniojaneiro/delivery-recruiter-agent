"""D63: a spec that is incomplete fails when it is built, with every problem named, not in the middle of a chat."""
from dataclasses import replace

import pytest

from screener.model import Outcome
from sazon.spec import SAZON
from screener.spec import SpecError, check_spec
from tests.support.toy_spec import EN, TOY, say


def problems(**changes) -> str:
    """Builds the toy spec with the changes and returns what the check says is wrong with it."""
    with pytest.raises(SpecError) as error:
        replace(TOY, **changes)
    return str(error.value)


def first_field(**changes):
    return (replace(TOY.fields[0], **changes), *TOY.fields[1:])


def test_both_real_specs_are_complete():
    check_spec(SAZON)
    check_spec(TOY)


def test_a_field_nobody_can_read_from_the_model_reply_is_refused():
    message = problems(fields=first_field(read=None))
    assert "name" in message and "read" in message


def test_a_field_with_no_validator_is_refused_unless_it_is_the_area_field():
    assert "validate" in problems(fields=first_field(validate=None))


def test_the_same_key_twice_is_refused():
    assert "twice" in problems(fields=(*TOY.fields, TOY.fields[0]))


def test_an_area_or_title_field_the_spec_does_not_have_is_refused():
    assert "area_field" in problems(area_field="city")
    assert "title_field" in problems(title_field="surname")


def test_a_card_line_with_no_card_function_is_refused():
    assert "card" in problems(card_order=("name",))


def test_a_rejecting_answer_needs_the_question_that_confirms_it():
    assert "confirm_rejection" in problems(fields=(*TOY.fields[:2], replace(TOY.fields[2], confirm_rejection=None)))


def test_two_rules_with_one_reason_are_refused():
    assert "CANNOT_LIFT" in problems(rules=(*TOY.rules, *TOY.rules))


def test_wording_missing_in_the_default_language_is_refused():
    message = problems(fields=first_field(ask={}))
    assert "ask" in message and "name" in message


def test_a_pack_without_the_closes_the_engine_uses_is_refused():
    close = {k: v for k, v in TOY.pack.close.items() if k != Outcome.QUALIFIED}
    assert "QUALIFIED" in problems(pack=replace(TOY.pack, close=close))


def test_a_pack_without_a_notice_the_engine_uses_is_refused():
    notices = {k: v for k, v in TOY.pack.notices.items() if k != "pay"}
    assert "pay" in problems(pack=replace(TOY.pack, notices=notices))


def test_two_fields_adding_the_same_reply_attribute_are_refused():
    twin = replace(TOY.fields[1], key="shift2")
    assert "shift" in problems(fields=(*TOY.fields, twin))


def test_every_problem_is_listed_at_once():
    message = problems(area_field="city", title_field="surname", card_order=("name",))
    assert "area_field" in message and "title_field" in message and "card" in message


def test_a_spec_that_is_incomplete_cannot_even_be_built():
    from screener.spec import ScreeningSpec
    with pytest.raises(SpecError):
        ScreeningSpec(fields=(), pack=TOY.pack, recruiter=TOY.recruiter, area_field="city")
    assert say("x") == {EN: "x"}
