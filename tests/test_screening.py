from datetime import date

import pytest

from sazon.screening import ConsentRequired, Screening

AREAS = {"Madrid": [], "Ciudad de México": ["CDMX"], "Guadalajara": []}
TODAY = date(2026, 10, 25)


@pytest.fixture
def screening():
    return Screening(AREAS)


def test_consent_is_the_first_thing_asked(screening):
    assert screening.next_field() == "consent"


def test_answers_before_consent_are_refused(screening):
    with pytest.raises(ConsentRequired):
        screening.submit("name", "Juan Pérez", TODAY)


def test_after_consent_fields_are_asked_in_friendly_order(screening):
    screening.record_consent(True)
    assert screening.next_field() == "name"
    screening.submit("name", "Juan Pérez", TODAY)
    assert screening.next_field() == "experience"


def test_hybrid_answers_skip_already_filled_fields(screening):
    screening.record_consent(True)
    screening.submit("city", "Madrid", TODAY)
    screening.submit("license", True, TODAY)
    order = []
    while (field := screening.next_field()) is not None:
        order.append(field)
        screening.submit(field, {
            "name": "Juan Pérez",
            "experience": (0, []),
            "availability": ["weekends"],
            "schedule": "flexible",
            "start_date": date(2026, 11, 1),
        }[field], TODAY)
    assert order == ["name", "experience", "availability", "schedule", "start_date"]


@pytest.fixture
def consented(screening):
    screening.record_consent(True)
    return screening


def test_valid_answer_is_accepted_and_normalised(consented):
    result = consented.submit("name", "  Juan   Pérez ", TODAY)
    assert result.status == "ok"
    assert consented.values["name"] == "Juan Pérez"


def test_invalid_answer_asks_a_follow_up_with_the_reason(consented):
    result = consented.submit("name", "Juan", TODAY)
    assert result.status == "follow_up" and result.reason
    assert consented.next_field() == "name"



def test_a_valid_answer_after_follow_ups_clears_the_counter(consented):
    consented.submit("name", "Juan", TODAY)
    assert consented.submit("name", "Juan Pérez", TODAY).status == "ok"
    assert consented.blocked_on is None


def test_city_typo_asks_for_confirmation_then_accepts_on_yes(consented):
    result = consented.submit("city", "Guadalajra", TODAY)
    assert result.status == "confirm" and result.suggestion == "Guadalajara"
    assert consented.confirm_city(True).status == "ok"
    assert consented.values["city"] == "Guadalajara"


def test_city_confirmation_declined_counts_as_a_follow_up(consented):
    consented.submit("city", "Guadalajra", TODAY)
    result = consented.confirm_city(False)
    assert result.status == "follow_up"
    assert "city" not in consented.values




def fill(s, **overrides):
    answers = {
        "name": "Juan Pérez",
        "experience": (2, ["glovo"]),
        "availability": ["full_time"],
        "schedule": "morning",
        "start_date": date(2026, 11, 1),
        "city": "Madrid",
        "license": True,
    }
    answers.update(overrides)
    for field, value in answers.items():
        for _ in range(4):
            if s.submit(field, value, TODAY).status != "follow_up":
                break
        if s.awaiting_rejection:
            s.confirm_rejection(True)
    return s


def test_decision_is_in_progress_while_fields_are_missing(consented):
    assert consented.decide().outcome == "IN_PROGRESS"


def test_all_fields_valid_with_license_and_area_is_qualified(consented):
    decision = fill(consented).decide()
    assert decision.outcome == "QUALIFIED" and decision.reasons == []


def test_declined_consent_is_disqualified_with_no_consent(screening):
    screening.record_consent(False)
    decision = screening.decide()
    assert decision.outcome == "DISQUALIFIED" and decision.reasons == ["NO_CONSENT"]


def test_no_license_is_disqualified(consented):
    decision = fill(consented, license=False).decide()
    assert decision.outcome == "DISQUALIFIED" and decision.reasons == ["NO_LICENSE"]


def test_out_of_area_is_disqualified_and_both_reasons_are_listed(consented):
    decision = fill(consented, city="Sevilla", license=False).decide()
    assert decision.outcome == "DISQUALIFIED"
    assert decision.reasons == ["NO_LICENSE", "OUT_OF_AREA"]


def test_disqualifier_known_early_decides_before_all_fields_are_filled(consented):
    consented.submit("license", False, TODAY)
    consented.confirm_rejection(True)
    assert consented.decide().outcome == "DISQUALIFIED"





from datetime import datetime, timedelta



def test_two_off_topic_messages_in_a_row_end_the_chat(consented):
    consented.off_topic()
    assert consented.decide().outcome == "IN_PROGRESS"
    consented.off_topic()
    assert consented.decide().outcome == "ENDED_OFF_TOPIC"


def test_a_valid_answer_between_off_topic_messages_resets_the_count(consented):
    consented.off_topic()
    consented.submit("name", "Juan Pérez", TODAY)
    consented.off_topic()
    assert consented.decide().outcome == "IN_PROGRESS"


def test_human_request_is_logged_as_an_event_and_screening_continues(consented):
    consented.human_requested()
    assert ("human_requested", "") in consented.events
    assert consented.decide().outcome == "IN_PROGRESS"


def test_off_topic_messages_are_logged_as_events(consented):
    consented.off_topic()
    assert ("off_topic", "") in consented.events






def test_correcting_an_out_of_area_city_clears_the_disqualifier(consented):
    consented.submit("city", "Sevilla", TODAY)
    consented.submit("city", "Madrid", TODAY)
    assert not consented.out_of_area
    assert "OUT_OF_AREA" not in consented.decide().reasons


def test_nothing_is_asked_after_consent_is_declined(screening):
    screening.record_consent(False)
    assert screening.next_field() is None


def test_stray_confirmation_with_nothing_pending_is_a_follow_up_not_a_crash(consented):
    assert consented.confirm_city(True).status == "follow_up"




import json


def test_extracted_is_json_serialisable_with_iso_dates(consented):
    fill(consented)
    extracted = consented.extracted()
    assert json.loads(json.dumps(extracted)) == extracted
    assert extracted["start_date"] == "2026-11-01"
    assert extracted["city"] == "Madrid"


def test_half_finished_screening_survives_a_save_and_reload(consented):
    consented.submit("name", "Juan", TODAY)
    consented.submit("name", "Juan", TODAY)
    consented.submit("city", "Guadalajra", TODAY)
    consented.off_topic()
    consented.human_requested()
    state = json.loads(json.dumps(consented.to_state()))

    restored = Screening.from_state(AREAS, state)

    restored.off_topic()
    assert restored.decide().outcome == "ENDED_OFF_TOPIC"
    assert restored.confirm_city(True).status == "ok"
    assert restored.values["city"] == "Guadalajara"
    statuses = [restored.submit("name", "Juan", TODAY).status for _ in range(4)]
    assert statuses == ["follow_up", "follow_up", "follow_up", "blocked"]
    assert ("human_requested", "") in restored.events


def test_reloaded_screening_keeps_dates_and_consent(consented):
    fill(consented)
    restored = Screening.from_state(AREAS, json.loads(json.dumps(consented.to_state())))
    assert restored.values["start_date"] == date(2026, 11, 1)
    assert restored.decide() == consented.decide()


def test_withdrawing_ends_the_chat_asks_nothing_more_and_is_logged(consented):
    consented.submit("name", "Juan Pérez", TODAY)
    consented.withdraw()
    assert consented.decide().outcome == "WITHDRAWN"
    assert consented.next_field() is None
    assert ("withdrawn", "") in consented.events


def test_withdrawing_wins_over_a_known_disqualifier(consented):
    consented.submit("license", False, TODAY)
    consented.withdraw()
    assert consented.decide().outcome == "WITHDRAWN"


def test_withdrawal_survives_a_save_and_reload(consented):
    consented.withdraw()
    restored = Screening.from_state(AREAS, json.loads(json.dumps(consented.to_state())))
    assert restored.decide().outcome == "WITHDRAWN"


def test_declined_confirmation_does_not_clear_an_earlier_out_of_area_city(consented):
    consented.submit("city", "Sevilla", TODAY)
    consented.confirm_rejection(True)
    consented.submit("city", "Guadalajra", TODAY)
    consented.confirm_city(False)
    assert consented.decide().outcome == "DISQUALIFIED"
    assert consented.decide().reasons == ["OUT_OF_AREA"]


def test_stale_pending_city_cannot_overwrite_a_later_city(consented):
    consented.submit("city", "Guadalajra", TODAY)
    consented.submit("city", "Madrid", TODAY)
    assert consented.confirm_city(True).status == "follow_up"
    assert consented.values["city"] == "Madrid"


def test_far_start_date_reaches_the_decision_flags_and_clears_when_corrected(consented):
    consented.submit("start_date", date(2027, 6, 1), TODAY)
    assert "START_DATE_FAR" in consented.decide().flags
    consented.submit("start_date", date(2026, 11, 1), TODAY)
    assert "START_DATE_FAR" not in consented.decide().flags


def test_far_start_date_flag_survives_a_save_and_reload(consented):
    consented.submit("start_date", date(2027, 6, 1), TODAY)
    restored = Screening.from_state(AREAS, json.loads(json.dumps(consented.to_state())))
    assert "START_DATE_FAR" in restored.decide().flags


@pytest.mark.parametrize("field,garbage", [
    ("name", None), ("name", 42), ("experience", None), ("experience", ("x", [])),
    ("experience", (True, [])), ("availability", None), ("availability", "full_time"),
    ("schedule", None), ("start_date", "2026-11-01"), ("start_date", 5), ("license", "yes"),
])
def test_garbage_from_extraction_is_a_follow_up_never_a_crash(consented, field, garbage):
    assert consented.submit(field, garbage, TODAY).status == "follow_up"


def test_garbage_city_is_a_follow_up_never_a_crash(consented):
    assert consented.submit("city", None, TODAY).status == "follow_up"
    assert consented.submit("city", 7, TODAY).status == "follow_up"


from sazon.model import EventType, Field, Outcome, Status


def test_outcomes_statuses_and_events_are_typed_but_stay_plain_strings_in_json(consented):
    assert isinstance(consented.decide().outcome, Outcome)
    assert consented.submit("name", "Juan Pérez", TODAY).status is Status.OK
    consented.withdraw()
    assert consented.events[-1][0] is EventType.WITHDRAWN
    assert json.dumps(consented.to_state())
    assert Field.LICENSE == "license" and Outcome.QUALIFIED == "QUALIFIED"


def test_a_pending_city_confirmation_is_visible_to_the_caller(consented):
    assert consented.awaiting_confirmation is None
    consented.submit("city", "Guadalajra", TODAY)
    assert consented.awaiting_confirmation == "Guadalajara"
    consented.confirm_city(True)
    assert consented.awaiting_confirmation is None


def test_nothing_more_is_asked_once_a_disqualifier_is_known(consented):
    consented.submit("license", False, TODAY)
    consented.confirm_rejection(True)
    assert consented.next_field() is None


def test_nothing_more_is_asked_after_the_chat_ended_off_topic(consented):
    consented.off_topic()
    consented.off_topic()
    assert consented.next_field() is None


def test_nothing_more_is_asked_once_qualified(consented):
    assert fill(consented).next_field() is None



def test_language_is_conversation_state_and_survives_reload(consented):
    assert consented.language == "es"
    consented.language = "en"
    restored = Screening.from_state(AREAS, json.loads(json.dumps(consented.to_state())))
    assert restored.language == "en"


def test_reminder_is_sent_once_then_the_candidate_is_stalled_then_resumes(consented):
    consented.send_reminder()
    assert consented.reminder_sent and ("reminder_sent", "") in consented.events
    assert consented.decide().outcome == "IN_PROGRESS"
    consented.mark_stalled()
    assert consented.decide().outcome == "STALLED" and consented.next_field() is None
    consented.resume()
    assert consented.decide().outcome == "IN_PROGRESS" and ("resumed", "") in consented.events
    assert consented.next_field() == "name"


def test_stalled_never_overrides_a_final_outcome(consented):
    consented.submit("license", False, TODAY)
    consented.confirm_rejection(True)
    consented.mark_stalled()
    assert consented.decide().outcome == "DISQUALIFIED"


def test_stall_state_survives_reload(consented):
    consented.send_reminder()
    consented.mark_stalled()
    restored = Screening.from_state(AREAS, json.loads(json.dumps(consented.to_state())))
    assert restored.decide().outcome == "STALLED" and restored.reminder_sent


def test_a_qualified_candidate_is_never_marked_stalled(consented):
    fill(consented)
    consented.mark_stalled()
    assert consented.decide().outcome == "QUALIFIED"


REJECTIONS = [("license", False, "NO_LICENSE", "license"), ("city", "Sevilla", "OUT_OF_AREA", "city")]


@pytest.mark.parametrize("field,value,reason,asked", REJECTIONS)
def test_a_rejecting_answer_is_not_final_until_the_candidate_confirms(consented, field, value, reason, asked):
    result = consented.submit(field, value, TODAY)
    assert result.status == "confirm_reject"
    assert consented.awaiting_rejection == asked
    assert field not in consented.values
    assert consented.decide().outcome == "IN_PROGRESS"


@pytest.mark.parametrize("field,value,reason,asked", REJECTIONS)
def test_confirming_the_rejection_disqualifies(consented, field, value, reason, asked):
    consented.submit(field, value, TODAY)
    assert consented.confirm_rejection(True).status == "ok"
    assert consented.decide().outcome == "DISQUALIFIED" and consented.decide().reasons == [reason]
    assert consented.awaiting_rejection is None
    assert consented.next_field() is None


@pytest.mark.parametrize("field,value,reason,asked", REJECTIONS)
def test_denying_the_rejection_keeps_screening_and_asks_the_question_again(consented, field, value, reason, asked):
    consented.submit(field, value, TODAY)
    consented.confirm_rejection(False)
    assert consented.decide().outcome == "IN_PROGRESS"
    assert field not in consented.values and consented.awaiting_rejection is None


@pytest.mark.parametrize("field,value,reason,asked", REJECTIONS)
def test_repeating_the_same_rejecting_answer_counts_as_confirming(consented, field, value, reason, asked):
    consented.submit(field, value, TODAY)
    consented.submit(field, value, TODAY)
    assert consented.decide().outcome == "DISQUALIFIED"


def test_a_contradicting_answer_clears_the_pending_rejection(consented):
    consented.submit("license", False, TODAY)
    consented.submit("license", True, TODAY)
    assert consented.awaiting_rejection is None and consented.values["license"] is True
    consented.submit("city", "Sevilla", TODAY)
    consented.submit("city", "Madrid", TODAY)
    assert consented.awaiting_rejection is None and consented.values["city"] == "Madrid"


def test_a_stray_rejection_confirmation_is_a_follow_up_not_a_crash(consented):
    assert consented.confirm_rejection(True).status == "follow_up"


def test_a_pending_rejection_survives_a_save_and_reload(consented):
    consented.submit("license", False, TODAY)
    restored = Screening.from_state(AREAS, json.loads(json.dumps(consented.to_state())))
    assert restored.awaiting_rejection == "license"
    restored.confirm_rejection(True)
    assert restored.decide().outcome == "DISQUALIFIED"
