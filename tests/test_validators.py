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
