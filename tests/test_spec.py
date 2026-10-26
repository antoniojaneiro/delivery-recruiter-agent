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


def test_the_reply_shape_and_the_model_prompt_come_from_the_spec():
    from sazon.extraction import build_system_prompt
    model = TOY.extraction_model
    assert {"shift", "can_lift", "off_topic", "language"} <= set(model.model_fields)
    assert not {"city", "has_license", "experience_years"} & set(model.model_fields)
    prompt = build_system_prompt(TOY)
    assert "warehouse-picker screening chat" in prompt
    assert '- shift: "day" or "night"' in prompt
    assert "has_license" not in prompt and "delivery" not in prompt


def test_a_message_is_read_into_the_fields_of_the_spec():
    s = toy()
    reply = TOY.extraction_model(name="Jo Smith", shift="night")
    s.apply(reply, "I'm Jo Smith, nights", TODAY)
    assert s.values == {"name": "Jo Smith", "shift": "night"}
    assert s.next_field() == "can_lift"


def test_an_unclear_answer_is_followed_up_for_the_field_it_belongs_to():
    s = toy()
    directive = s.apply(TOY.extraction_model(name="Jo"), "Jo", TODAY)
    assert directive.field == "name" and directive.kind.value == "follow_up"


def _conversation(tmp_path, lift):
    from datetime import datetime

    from sazon import turn
    from sazon.store import Store
    from tests.fakes import ScriptedLLM
    from tests.toy_spec import TOY_CLIENT

    now = datetime(2026, 10, 25, 10, 0)
    store = Store(tmp_path / "toy.db")
    llm = ScriptedLLM(extractions=[{"name": "Jo Smith"}, {"shift": "night"}, {"can_lift": lift}])
    replies = [turn.start(store, TOY_CLIENT, "c1", now)]
    for message in ("yes", "Jo Smith", "nights", "yes I can" if lift else "no"):
        replies.append(turn.handle_message(llm, store, TOY_CLIENT, "c1", message, now))
    return store, replies


def test_a_second_client_runs_a_whole_conversation_in_its_own_words(tmp_path):
    store, replies = _conversation(tmp_path, lift=True)
    assert replies == [
        TOY_PACK_CONSENT, "What's your full name?", "Do you prefer day or night shifts?", "Can you lift 20 kg?",
        "Thanks, you are through. Our team will call you within 5 days."]
    record = store.get("c1")
    assert record.outcome == "QUALIFIED"
    assert record.summary.splitlines() == [
        "Jo Smith · Qualified", "Shift: night", "Can lift 20 kg: yes", "Chat: language English",
        "Automatic summary: the recruiter decides."]


def test_a_second_client_disqualifies_by_its_own_rule_and_says_so_in_its_own_words(tmp_path):
    store, replies = _conversation(tmp_path, lift=False)
    assert replies[-1] == "Just to confirm: you cannot lift 20 kg?"
    from sazon import turn
    from tests.fakes import ScriptedLLM
    from tests.toy_spec import TOY_CLIENT
    from datetime import datetime
    closing = turn.handle_message(ScriptedLLM(extractions=[{"confirms_rejection": True}]), store, TOY_CLIENT, "c1",
                                  "yes", datetime(2026, 10, 25, 10, 5))
    assert closing.startswith("We need someone who can lift 20 kg")
    record = store.get("c1")
    assert record.outcome == "DISQUALIFIED" and record.reasons == ["CANNOT_LIFT"]
    assert "Motivo" not in record.summary and "Reason: cannot lift 20 kg" in record.summary


def test_nothing_of_sazon_reaches_a_second_clients_candidates(tmp_path):
    store, replies = _conversation(tmp_path, lift=True)
    text = " ".join(replies + [m.text for m in store.messages("c1")] + [store.get("c1").summary])
    for leaked in ("Saz", "repartidor", "delivery", "48", "reclutador", "licen"):
        assert leaked not in text


TOY_PACK_CONSENT = ("Hi, I'm Acme Logistics' virtual assistant (an AI). I'll ask three questions about your picker "
                    "application. A recruiter reviews every answer. May I save your answers?")
