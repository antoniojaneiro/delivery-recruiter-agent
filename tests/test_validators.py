import pytest

from sazon.validators import validate_name


@pytest.mark.parametrize("raw", ["Juan Pérez", "María García-López", "Sean O'Brien", "  Ana   Ruiz "])
def test_name_with_two_words_is_valid(raw):
    result = validate_name(raw)
    assert result.ok


@pytest.mark.parametrize("raw", ["Juan", "", "   ", "Juan 123", "a1 b2", "Juan_Pérez Ruiz"])
def test_name_single_word_or_bad_characters_is_invalid(raw):
    result = validate_name(raw)
    assert not result.ok
    assert result.reason


from sazon.validators import validate_license


@pytest.mark.parametrize("value,expected", [(True, True), (False, False)])
def test_license_bool_is_accepted(value, expected):
    result = validate_license(value)
    assert result.ok and result.value is expected


def test_license_unsure_is_not_valid_and_asks_again():
    result = validate_license(None)
    assert not result.ok
    assert result.reason


from sazon.validators import match_city

AREAS = {
    "Madrid": [],
    "Barcelona": [],
    "Valencia": [],
    "Ciudad de México": ["CDMX", "DF", "Mexico City"],
    "Guadalajara": [],
    "Monterrey": [],
}


@pytest.mark.parametrize("raw,city", [
    ("Madrid", "Madrid"),
    ("  madrid ", "Madrid"),
    ("CDMX", "Ciudad de México"),
    ("ciudad de mexico", "Ciudad de México"),
])
def test_city_exact_after_folding_accents_case_and_aliases(raw, city):
    result = match_city(raw, AREAS)
    assert result.status == "match" and result.city == city


def test_city_close_typo_asks_for_confirmation():
    result = match_city("Guadalajra", AREAS)
    assert result.status == "confirm" and result.city == "Guadalajara"


def test_city_not_in_list_is_out_of_area():
    result = match_city("Sevilla", AREAS)
    assert result.status == "out_of_area" and result.city is None


from sazon.validators import validate_availability, validate_schedule


def test_availability_accepts_one_or_more_known_values_without_duplicates():
    result = validate_availability(["part_time", "weekends", "weekends"])
    assert result.ok and result.value == ["part_time", "weekends"]


@pytest.mark.parametrize("raw", [[], ["sometimes"], ["full_time", "nights"]])
def test_availability_empty_or_unknown_is_invalid(raw):
    assert not validate_availability(raw).ok


@pytest.mark.parametrize("raw", ["morning", "afternoon", "evening", "flexible"])
def test_schedule_accepts_the_four_options(raw):
    assert validate_schedule(raw).value == raw


def test_schedule_unknown_is_invalid():
    assert not validate_schedule("night").ok


from sazon.validators import validate_experience


def test_experience_years_with_known_platform_is_normalised():
    result = validate_experience(2, ["  GLOVO ", "uber eats"])
    assert result.ok and result.value == {"years": 2, "platforms": ["glovo", "uber eats"]}


def test_experience_unknown_platform_becomes_other():
    assert validate_experience(1, ["Mi tío"]).value["platforms"] == ["other"]


def test_experience_zero_years_needs_no_platform():
    result = validate_experience(0, [])
    assert result.ok and result.value == {"years": 0, "platforms": []}


@pytest.mark.parametrize("years,platforms", [(None, []), (-1, ["glovo"]), (3, [])])
def test_experience_missing_negative_or_platformless_years_is_invalid(years, platforms):
    assert not validate_experience(years, platforms).ok


from datetime import date

from sazon.validators import validate_start_date

TODAY = date(2026, 10, 25)


def test_start_date_today_or_soon_is_valid_and_unflagged():
    result = validate_start_date(date(2026, 11, 1), TODAY)
    assert result.ok and result.value == date(2026, 11, 1) and result.flags == ()


def test_start_date_exactly_12_weeks_is_not_flagged():
    assert validate_start_date(date(2027, 1, 17), TODAY).flags == ()


def test_start_date_beyond_12_weeks_is_recorded_and_flagged():
    result = validate_start_date(date(2027, 1, 18), TODAY)
    assert result.ok and result.flags == ("START_DATE_FAR",)


@pytest.mark.parametrize("value", [None, date(2026, 10, 24)])
def test_start_date_missing_or_past_is_invalid(value):
    assert not validate_start_date(value, TODAY).ok
