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
