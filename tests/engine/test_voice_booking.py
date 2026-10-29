"""D93: booking a call by voice. There is no list and no button: the agent asks which day, then which time; a day or a time
that is free is taken, one that is not gets the closest one offered, and a yes books it. The channel is per turn, so the same
candidate can switch between speaking and writing."""
from datetime import datetime

import pytest

from sazon import config
from sazon.client import SAZON_CALENDAR
from screener import turn
from screener.store import Store
from tests.support.booking import NOW, hire, qualify, say
from tests.support.clients import client_for

CLIENT = client_for(config.AREAS)  # NOW is Sunday 25 Oct 2026: the first day a candidate can book is Monday the 26th


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "s.db", calendar=SAZON_CALENDAR)
    hire(s, "Ana")  # Monday to Friday, 9:00 to 17:00, 15-minute calls
    return s


def speak(store, text, cid="c1"):
    return say(store, text, cid=cid, voice=True)[0]


def stage(store, cid="c1"):
    state = store.get(cid).state.get("voice_booking")
    return state and state["stage"]


def test_a_candidate_who_qualifies_by_voice_is_asked_which_day_and_given_no_list(store):
    reply = qualify(store, voice=True)
    assert reply == "¡Genial, tu perfil encaja! Por favor, reserva una llamada para hablar con un reclutador. ¿Qué día te vendría bien?"
    assert stage(store) == "day" and not store.get("c1").state["slot_offer"]


def test_a_free_day_then_a_free_time_books_the_call(store):
    qualify(store, voice=True)
    asked = speak(store, "el martes")
    assert asked == "Para el martes 27 de octubre tengo horarios libres. ¿A qué hora te viene bien?" and stage(store) == "time"
    done = speak(store, "a las 10")
    assert done == "Listo, queda reservada tu llamada: el martes 27 de octubre a las 10. Un reclutador te llamará a esa hora."
    assert store.booking_of("c1").starts_at == datetime(2026, 10, 27, 10, 0) and stage(store) is None


def test_a_day_with_no_times_gets_the_closest_day_and_a_yes_goes_on_to_the_time(store):
    qualify(store, voice=True)
    proposal = speak(store, "el sábado")  # a weekend: Friday is one day away, Monday two
    assert "El día más cercano es el viernes 30 de octubre. ¿Te viene bien?" in proposal and stage(store) == "confirm_day"
    assert "Para el viernes 30 de octubre tengo horarios libres" in speak(store, "sí")
    assert stage(store) == "time"


def test_saying_no_to_the_proposed_day_asks_for_another(store):
    qualify(store, voice=True)
    speak(store, "el sábado")
    assert speak(store, "no") == "De acuerdo. ¿Qué otro día prefieres?" and stage(store) == "day"
    assert "Para el lunes 26 de octubre tengo horarios libres" in speak(store, "el lunes")


def test_today_is_never_offered_the_closest_day_is_tomorrow(store):
    qualify(store, voice=True)
    assert "El día más cercano es el lunes 26 de octubre" in speak(store, "hoy")


def test_a_time_that_is_taken_gets_the_closest_free_one_and_a_yes_books_it(store):
    qualify(store, "c2", voice=True)
    speak(store, "el martes", "c2")
    speak(store, "a las 10", "c2")  # the only recruiter now has 10:00 on Tuesday
    qualify(store, "c1", voice=True)
    speak(store, "el martes")
    proposal = speak(store, "a las 10")  # 9:45 and 10:15 are equally close: the earlier
    assert "A esa hora no tengo. La más cercana es a las 9:45. ¿Te viene bien?" in proposal and stage(store) == "confirm_time"
    assert "queda reservada" in speak(store, "sí") and store.booking_of("c1").starts_at == datetime(2026, 10, 27, 9, 45)


def test_a_time_before_the_first_one_gets_the_first_and_a_part_of_the_day_gets_its_earliest(store):
    qualify(store, voice=True)
    speak(store, "el martes")
    assert "La más cercana es a las 9." in speak(store, "a las 8")
    assert "no" and speak(store, "no") == "De acuerdo. ¿Qué otra hora prefieres?" and stage(store) == "time"
    assert "La más cercana es a las 12." in speak(store, "por la tarde")  # 12:00 is where the afternoon starts


def test_an_answer_that_is_not_a_day_is_asked_again_and_after_three_the_candidate_is_told_to_write_to_book_later(store):
    qualify(store, voice=True)
    for _ in range(3):
        assert speak(store, "no sé").startswith("No te he entendido. ¿Qué día")
    ending = speak(store, "no sé")
    assert "cuando quieras reservar tu llamada" in ending.lower() and stage(store) is None and store.booking_of("c1") is None


def test_declining_every_time_ends_the_booking_politely(store):
    qualify(store, voice=True)
    assert "cuando quieras reservar tu llamada" in speak(store, "ninguno").lower() and stage(store) is None


def test_the_same_in_english(store):
    reply = qualify(store, english=True, voice=True)
    assert reply == "Great, your profile fits! Please book a call to talk with a recruiter. Which day suits you?"
    assert speak(store, "tomorrow") == "I have free times on Monday, October 26. What time suits you?"
    assert speak(store, "at 2") == ("Done, your call is booked: Monday, October 26 at 2 PM. A recruiter will call you then.")
    assert store.booking_of("c1").starts_at == datetime(2026, 10, 26, 14, 0)


def test_switching_to_writing_gives_the_usual_offer_and_back_to_speaking_asks_the_day_again(store):
    qualify(store, voice=True)
    written = say(store, "hola")[0]
    assert "1) " in written and stage(store) is None and store.get("c1").state["slot_offer"]
    assert speak(store, "hola de nuevo").endswith("¿Qué día te vendría bien?")
    assert stage(store) == "day" and not store.get("c1").state["slot_offer"]


def test_a_candidate_who_is_already_booked_hears_the_call_they_have(store):
    qualify(store, voice=True)
    speak(store, "el martes")
    speak(store, "a las 10")
    assert "ya está reservada" in speak(store, "hola") and "martes 27 de octubre a las 10" in speak(store, "hola")


def test_voice_never_offers_the_cv_upload(store):
    turn.start(store, CLIENT, "c3", NOW)
    reply = say(store, "sí", {"consent": True}, cid="c3", voice=True)[0]
    assert "CV" not in reply and "PDF" not in reply and not store.get("c3").state.get("cv")


def test_a_spoken_turn_makes_one_model_call_to_read_the_answer_and_none_to_word_the_reply(store):
    turn.start(store, CLIENT, "c4", NOW)
    say(store, "sí", {"consent": True}, cid="c4", voice=True)
    _, spoken = say(store, "Me llamo Juan Pérez", {"name": "Juan Pérez"}, cid="c4", voice=True)
    _, written = say(store, "Me llamo Juan Pérez", {"name": "Juan Pérez"}, cid="c4")
    assert [c["json_mode"] for c in spoken.calls] == [True]  # the free model allows 15 calls a minute: speech needs fewer
    assert [c["json_mode"] for c in written.calls] == [True, False]
