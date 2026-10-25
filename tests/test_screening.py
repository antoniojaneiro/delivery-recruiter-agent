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


def test_after_three_follow_ups_the_raw_answer_is_kept_for_review(consented):
    statuses = [consented.submit("name", "Juan", TODAY).status for _ in range(4)]
    assert statuses == ["follow_up", "follow_up", "follow_up", "review"]
    assert consented.values["name"] == "Juan"
    assert consented.review_fields == {"name"}
    assert consented.next_field() == "experience"


def test_a_valid_answer_after_follow_ups_clears_the_counter(consented):
    consented.submit("name", "Juan", TODAY)
    assert consented.submit("name", "Juan Pérez", TODAY).status == "ok"
    assert consented.review_fields == set()


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


def test_city_outside_service_area_is_recorded_not_a_follow_up(consented):
    result = consented.submit("city", "Sevilla", TODAY)
    assert result.status == "ok"
    assert consented.out_of_area


def test_city_review_keeps_what_the_candidate_typed_not_our_suggestion(consented):
    for _ in range(4):
        consented.submit("city", "Guadalajra", TODAY)
        result = consented.confirm_city(False)
    assert result.status == "review"
    assert consented.values["city"] == "Guadalajra"


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
    assert consented.decide().outcome == "DISQUALIFIED"


def test_unclear_eligibility_field_after_cap_needs_review_not_qualified(consented):
    decision = fill(consented, license=None).decide()
    assert decision.outcome == "NEEDS_REVIEW" and decision.reasons == ["LICENSE_UNCLEAR"]


def test_disqualifier_wins_over_unclear_eligibility(consented):
    decision = fill(consented, city="Sevilla", license=None).decide()
    assert decision.outcome == "DISQUALIFIED" and decision.reasons == ["OUT_OF_AREA"]


def test_unclear_non_eligibility_field_still_qualifies_but_is_flagged(consented):
    decision = fill(consented, name="Juan").decide()
    assert decision.outcome == "QUALIFIED"
    assert decision.flags == ["NAME_NEEDS_REVIEW"]
