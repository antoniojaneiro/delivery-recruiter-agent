"""D48: the candidate's pick is read in plain code. A wrong pick books a real call, so it is strict."""
import pytest

from sazon.slot_choice import NONE, read_slot_choice


@pytest.mark.parametrize("text,number", [
    ("1", 1), ("2", 2), ("3", 3), (" 2 ", 2), ("2.", 2), ("1)", 1), ("la 2", 2), ("el 2", 2), ("la opción 3", 3),
    ("opcion 1", 1), ("el primero", 1), ("la primera", 1), ("primero", 1), ("el segundo", 2), ("la segunda opción", 2),
    ("la tercera", 3), ("uno", 1), ("dos", 2), ("la dos por favor", 2), ("el 2 me viene bien", 2), ("vale, la 3", 3),
    ("first", 1), ("the first one", 1), ("second", 2), ("the third", 3), ("option 2", 2), ("number 3", 3),
    ("I'll take the second", 2), ("two", 2), ("3 please", 3),
])
def test_a_clear_pick_is_read_as_that_option(text, number):
    assert read_slot_choice(text, 3) == number


@pytest.mark.parametrize("text", [
    "ninguna", "Ninguno", "ninguna me viene bien", "ninguna de las tres", "no me viene bien ninguna", "none",
    "none of them", "none work for me", "neither", "no", "no gracias", "no, gracias", "no thanks", "stop", "para",
])
def test_declining_every_option_is_read_as_none(text):
    assert read_slot_choice(text, 3) is NONE


@pytest.mark.parametrize("text", [
    "", "   ", "hola", "¿cuánto pagan?", "el martes", "mañana", "4", "0", "10", "1 o 2", "1 y 3", "1 2 3",
    "no sé", "quizá", "2 horas", "la 2 o la 3", "no, la 2", "el cuarto", "third or first", "la 2?", "dame otra",
    "el lunes a las 10", "12", "la 21",
])
def test_anything_else_is_unclear_and_never_picks(text):
    assert read_slot_choice(text, 3) is None


def test_the_number_must_be_one_of_the_options_offered():
    assert read_slot_choice("2", 1) is None and read_slot_choice("el segundo", 1) is None
    assert read_slot_choice("1", 1) == 1
    assert read_slot_choice("3", 2) is None
    assert read_slot_choice("el tercero", 3) == 3


@pytest.mark.parametrize("text", [
    "me retiro", "ya no quiero continuar", "no quiero seguir", "no quiero", "cancelar", "cancela todo",
    "I want to withdraw", "I don't want to continue", "I do not want any", "cancel",
])
def test_wording_for_withdrawing_is_read_as_declining_every_option(text):
    assert read_slot_choice(text, 3) is NONE


def test_wanting_a_particular_option_is_still_a_pick():
    assert read_slot_choice("quiero la 2", 3) == 2 and read_slot_choice("I want the first", 3) == 1
