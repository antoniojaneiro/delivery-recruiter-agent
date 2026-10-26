"""D63: the engine takes its fields and rules from a spec, so a second client needs no engine change."""
from datetime import date

from sazon.model import Outcome, Status
from sazon.screening import Screening
from tests.toy_spec import TOY

TODAY = date(2026, 10, 25)


def toy() -> Screening:
    s = Screening({}, spec=TOY)
    s.record_consent(True)
    return s


def test_the_engine_asks_the_fields_of_the_spec_in_order():
    s = toy()
    assert s.missing_fields() == ["name", "shift", "can_lift"]
    assert s.submit("name", "Jo Smith", TODAY).status == Status.OK
    assert s.next_field() == "shift"
    assert s.submit("shift", "night", TODAY).status == Status.OK
    assert s.next_field() == "can_lift"
    assert s.submit("can_lift", True, TODAY).status == Status.OK
    assert s.decide().outcome == Outcome.QUALIFIED


def test_a_field_of_the_spec_is_validated_by_the_spec():
    s = toy()
    result = s.submit("shift", "dawn", TODAY)
    assert result.status == Status.FOLLOW_UP
    assert "shift" not in s.values


def test_a_rejecting_answer_is_confirmed_and_then_a_rule_of_the_spec_disqualifies():
    s = toy()
    assert s.submit("can_lift", False, TODAY).status == Status.CONFIRM_REJECT
    assert s.decide().outcome == Outcome.IN_PROGRESS
    s.confirm_rejection(True)
    decision = s.decide()
    assert decision.outcome == Outcome.DISQUALIFIED
    assert decision.reasons == ["CANNOT_LIFT"]


def test_a_field_the_spec_does_not_have_is_refused():
    s = toy()
    try:
        s.submit("license", True, TODAY)
    except ValueError:
        return
    raise AssertionError("a Sazón field was accepted by the toy spec")
