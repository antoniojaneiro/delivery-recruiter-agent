"""D71: what a CV may do to a screening. It offers answers; it never decides, never closes and never speaks for
the candidate beyond the fields the client allows."""
from datetime import date

import pytest

from sazon.spec import SAZON, Extraction
from screener.directive import Kind
from screener.model import EventType, Language, Outcome
from screener.screening import Screening

AREAS = {"Madrid": [], "Barcelona": [], "Ciudad de México": ["CDMX"], "Guadalajara": []}
TODAY = date(2026, 10, 25)


def reading(**fields):
    return Extraction.model_validate(fields)


GOOD = dict(name="Juan Pérez", city="Madrid", has_license=True, experience_years=3, platforms=["glovo"])


@pytest.fixture
def screening():
    s = Screening(AREAS, SAZON)
    s.apply_consent_reply(type("R", (), {"answer": True, "language": None})())
    return s


def kinds(s):
    return [kind for kind, _ in s.events]


# --- the offer -----------------------------------------------------------------------------------------------

def test_consent_is_followed_by_the_cv_offer_when_the_client_takes_cvs():
    s = Screening(AREAS, SAZON)
    directive = s.apply_consent_reply(type("R", (), {"answer": True, "language": None})())
    assert directive.kind == Kind.CV_OFFER and s.cv_offered


def test_a_client_without_cv_texts_goes_straight_to_the_first_question():
    from tests.support.toy_spec import TOY
    s = Screening({"Leeds": []}, TOY)
    directive = s.apply_consent_reply(type("R", (), {"answer": True, "language": None})())
    assert directive.kind == Kind.ASK and not s.cv_offered


def test_any_typed_message_at_the_offer_is_a_skip(screening):
    screening.skip_cv()
    assert not screening.cv_offered and EventType.CV_SKIPPED in kinds(screening)


def test_a_skip_when_nothing_was_offered_changes_nothing(screening):
    screening.skip_cv()
    before = list(screening.events)
    screening.skip_cv()
    assert screening.events == before


# --- what is taken from a CV ---------------------------------------------------------------------------------

def test_clear_values_from_the_cv_are_taken_and_marked_as_from_the_cv(screening):
    taken, directive = screening.apply_cv(reading(**GOOD), TODAY, size=1000, digest="abc")
    assert screening.values["name"] == "Juan Pérez" and screening.values["city"] == "Madrid"
    assert screening.values["license"] is True and screening.values["experience"] == {"years": 3, "platforms": ["glovo"]}
    assert screening.sources == {k: "cv" for k in ("name", "city", "license", "experience")}
    assert directive.kind == Kind.ASK and directive.field == "availability"
    assert len(taken) == 4 and any("Madrid" in line for line in taken)
    assert not screening.cv_offered


def test_the_cv_event_names_the_fields_but_never_the_content(screening):
    screening.apply_cv(reading(**GOOD), TODAY, size=1000, digest="abc123")
    events = dict((k, d) for k, d in screening.events if k in (EventType.CV_UPLOADED, EventType.CV_PREFILLED))
    assert "size=1000 sha256=abc123 notice_sha256=" in events[EventType.CV_UPLOADED]
    assert events[EventType.CV_PREFILLED] == "name,experience,city,license"
    assert "Pérez" not in str(screening.events) and "Madrid" not in str(screening.events)


def test_fields_a_cv_may_not_fill_are_ignored(screening):
    screening.apply_cv(reading(**GOOD, availability=["full_time"], schedule="morning",
                               start_date={"iso": "2026-11-01"}), TODAY, 1, "x")
    for key in ("availability", "schedule", "start_date"):
        assert key not in screening.values


def test_a_value_that_does_not_pass_validation_is_asked_normally_and_costs_no_follow_up(screening):
    screening.apply_cv(reading(name="Juan", city="Madrid"), TODAY, 1, "x")
    assert "name" not in screening.values and screening.values["city"] == "Madrid"
    assert screening._follow_ups == {} and EventType.FOLLOW_UP not in kinds(screening)


@pytest.mark.parametrize("flags", [
    dict(withdraw=True), dict(wants_human=True), dict(asks_pay=True), dict(off_topic=True),
    dict(language="en"), dict(confirms_city=True), dict(confirms_rejection=True),
])
def test_what_a_cv_says_about_the_conversation_is_thrown_away(screening, flags):
    screening.language = Language.ES
    before = list(screening.events)
    screening.apply_cv(reading(**flags), TODAY, 1, "x")
    assert not screening.withdrawn and screening.language == Language.ES and screening._off_topic == 0
    assert [e for e in screening.events if e not in before and e[0] != EventType.CV_UPLOADED] == []
    assert screening.decide().outcome == Outcome.IN_PROGRESS


def test_a_cv_that_says_it_has_no_license_cannot_disqualify_alone(screening):
    taken, directive = screening.apply_cv(reading(has_license=False), TODAY, 1, "x")
    assert directive.kind == Kind.CONFIRM_REJECTION and directive.field == "license"
    assert "license" not in screening.values and screening.decide().outcome == Outcome.IN_PROGRESS
    assert taken == []


def test_after_the_candidate_confirms_it_the_rejection_stands(screening):
    screening.apply_cv(reading(has_license=False), TODAY, 1, "x")
    screening.confirm_rejection(True)
    assert screening.decide().outcome == Outcome.DISQUALIFIED


def test_a_city_outside_the_area_in_a_cv_waits_for_the_candidate(screening):
    taken, directive = screening.apply_cv(reading(**{**GOOD, "city": "Sevilla"}), TODAY, 1, "x")
    assert directive.kind == Kind.CONFIRM_REJECTION and directive.field == "city"
    assert "city" not in screening.values and not screening.out_of_area
    assert screening.decide().outcome == Outcome.IN_PROGRESS


def test_only_one_question_waits_at_a_time_so_later_cv_values_are_asked_normally(screening):
    screening.apply_cv(reading(city="Sevilla", has_license=False), TODAY, 1, "x")
    assert screening.awaiting_rejection == "city" and "license" not in screening.values


def test_a_near_miss_city_in_a_cv_is_confirmed_like_one_typed_in_the_chat(screening):
    taken, directive = screening.apply_cv(reading(city="Madird"), TODAY, 1, "x")
    assert directive.kind == Kind.CONFIRM_AREA and directive.suggestion == "Madrid"
    assert "city" not in screening.values


def test_a_value_the_candidate_later_changes_is_no_longer_marked_as_from_the_cv(screening):
    screening.apply_cv(reading(**GOOD), TODAY, 1, "x")
    screening.submit("name", "Pedro Gil", TODAY)
    assert "name" not in screening.sources and screening.sources.get("city") == "cv"


def test_an_unreadable_cv_is_recorded_and_the_questions_go_on(screening):
    directive = screening.cv_unreadable(size=500, digest="d1")
    assert directive.kind == Kind.ASK and directive.field == "name" and not screening.cv_offered
    assert EventType.CV_UPLOADED in kinds(screening) and EventType.CV_UNREADABLE in kinds(screening)
    assert screening.sources == {}


# --- saved state ---------------------------------------------------------------------------------------------

def test_the_cv_state_survives_saving_and_loading(screening):
    screening.apply_cv(reading(**GOOD), TODAY, 1, "x")
    loaded = Screening.from_state(AREAS, screening.to_state(), SAZON)
    assert loaded.sources == screening.sources and not loaded.cv_offered


def test_an_offer_waiting_for_the_candidate_survives_saving_and_loading():
    s = Screening(AREAS, SAZON)
    s.apply_consent_reply(type("R", (), {"answer": True, "language": None})())
    assert Screening.from_state(AREAS, s.to_state(), SAZON).cv_offered


def test_a_state_saved_before_cvs_existed_loads_with_nothing_offered():
    s = Screening.from_state(AREAS, {"consent": True, "values": {"name": "Juan Pérez"}}, SAZON)
    assert not s.cv_offered and s.sources == {}


def test_withdrawing_ends_the_offer(screening):
    screening.apply_stop_request()
    assert not screening.cv_offered


def test_what_was_taken_is_listed_with_the_name_of_each_field(screening):
    taken, _ = screening.apply_cv(reading(**GOOD), TODAY, 1, "x")
    assert "licencia: sí" in taken and "ciudad: Madrid" in taken and "nombre: Juan Pérez" in taken
    assert any(line.startswith("experiencia: 3 años") for line in taken)
