"""D68: "no experience" is something the candidate says; a plain yes to the experience question is not a number."""
from datetime import date

from sazon.spec import SAZON
from screener.spec import MISSING

TODAY = date(2026, 10, 26)
read = SAZON.field("experience").read
reply = SAZON.extraction_model


def test_a_zero_the_model_made_up_for_a_plain_yes_is_not_read_as_no_experience():
    assert read(reply(experience_years=0.0), TODAY, None) is MISSING


def test_the_candidate_saying_they_have_none_is_zero_years():
    assert read(reply(no_experience=True), TODAY, None) == (0, [])
    assert read(reply(no_experience=True, experience_years=0.0), TODAY, None) == (0, [])


def test_stated_years_and_platforms_still_come_through():
    assert read(reply(experience_years=2.0, platforms=["Uber"]), TODAY, None) == (2.0, ["Uber"])
    assert read(reply(experience_years=0.5), TODAY, None) == (0.5, [])
    assert read(reply(platforms=["Glovo"]), TODAY, {"years": 3, "platforms": []}) == (3, ["Glovo"])


def test_no_experience_is_one_of_the_things_the_model_is_asked_to_report():
    from sazon.spec import SYSTEM
    assert "no_experience" in SYSTEM and "plain yes" in SYSTEM
