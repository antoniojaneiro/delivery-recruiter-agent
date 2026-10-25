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
