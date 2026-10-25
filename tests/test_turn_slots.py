"""D48: offering, booking and confirming a call slot through handle_message."""
from datetime import datetime

import pytest

from sazon import config, turn
from sazon.phrasing import consent_message
from sazon.store import Store
from tests.fakes import ScriptedLLM

AREAS = config.AREAS
NOW = datetime(2026, 10, 25, 10, 0)
NOW_AWARE = NOW.astimezone()  # the same instant, for the store-level calls

ES_SLOTS = [datetime(2026, 11, 3, 10, 0), datetime(2026, 11, 4, 9, 30), datetime(2026, 11, 5, 16, 0)]
MX_SLOT = datetime(2026, 11, 3, 9, 0)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "sazon.db")


def say(store, message, *extractions, cid="c1"):
    llm = ScriptedLLM(extractions)
    return turn.handle_message(llm, store, AREAS, cid, message, NOW), llm


def qualify(store, cid="c1", city="Madrid", language="sí"):
    turn.start(store, AREAS, cid, NOW)
    say(store, language, cid=cid)
    say(store, "Soy Juan Pérez", {"name": "Juan Pérez"}, cid=cid)
    say(store, "2 años con Glovo", {"experience_years": 2, "platforms": ["Glovo"]}, cid=cid)
    say(store, "tiempo completo", {"availability": ["full_time"]}, cid=cid)
    say(store, "mañanas", {"schedule": "morning"}, cid=cid)
    say(store, "ya mismo", {"start_date": {"now": True}}, cid=cid)
    say(store, city, {"city": city}, cid=cid)
    return say(store, "sí tengo", {"has_license": True}, cid=cid)[0]


def add_slots(store, country="ES", times=ES_SLOTS):
    return [store.add_slot(country, t, "Ana", "Ana", NOW_AWARE) for t in times]


def booked(store, cid="c1"):
    return store.booking_of(cid)


def test_a_qualified_candidate_is_offered_the_next_three_slots_with_the_fallback_inside(store):
    add_slots(store)
    reply = qualify(store)
    lines = reply.splitlines()
    assert "tu perfil encaja" in lines[0]
    assert [l for l in lines if l[:2] in ("1)", "2)", "3)")] == ["1) mar 3 nov, 10:00", "2) mié 4 nov, 09:30", "3) jue 5 nov, 16:00"]
    assert "ninguna" in reply and "48 horas" in reply
    assert store.get("c1").outcome == "QUALIFIED" and booked(store) is None


def test_only_three_slots_are_offered_even_when_more_are_free(store):
    add_slots(store, times=ES_SLOTS + [datetime(2026, 11, 6, 10, 0), datetime(2026, 11, 9, 10, 0)])
    reply = qualify(store)
    assert "4)" not in reply and "3)" in reply


def test_with_no_free_slot_the_candidate_gets_the_48_hour_promise(store):
    reply = qualify(store)
    assert "48 horas" in reply and "1)" not in reply and booked(store) is None


def test_picking_a_number_books_that_slot_and_confirms_the_time(store):
    ids = add_slots(store)
    qualify(store)
    reply, llm = say(store, "la 2")
    assert "queda reservada" in reply and "mié 4 nov, 09:30" in reply
    assert booked(store).slot_id == ids[1]
    assert not [c for c in llm.calls if not c["json_mode"]]  # no model-written text
    assert not [c for c in llm.calls if c["json_mode"]]      # and nothing sent for extraction


def test_the_reply_to_the_offer_is_never_sent_to_the_model(store):
    add_slots(store)
    qualify(store)
    _, llm = say(store, "mi número de teléfono es 600123123, quiero la 1")
    assert llm.calls == []


def test_picking_by_word_works_in_english_too(store):
    add_slots(store)
    qualify(store, language="yes")
    reply, _ = say(store, "the first one")
    assert "booked" in reply.lower() and "Tue 3 Nov, 10:00" in reply


def test_an_unclear_pick_shows_the_same_list_again_and_books_nothing(store):
    add_slots(store)
    first = qualify(store)
    reply, _ = say(store, "¿cuánto pagan?")
    assert booked(store) is None
    assert [l for l in reply.splitlines() if l[:2] in ("1)", "2)", "3)")] == \
           [l for l in first.splitlines() if l[:2] in ("1)", "2)", "3)")]
    assert "ninguna" in reply


def test_declining_every_option_falls_back_to_the_48_hour_promise(store):
    add_slots(store)
    qualify(store)
    reply, _ = say(store, "ninguna")
    assert "48 horas" in reply and booked(store) is None
    later, _ = say(store, "gracias")
    assert "48 horas" in later and "1)" not in later


def test_a_slot_taken_while_the_candidate_decides_gets_a_fresh_offer_not_an_error(store):
    ids = add_slots(store)
    qualify(store)
    store.book_slot(ids[0], "someone-else", NOW_AWARE)
    reply, _ = say(store, "1")
    assert "ya no está libre" in reply and booked(store) is None
    assert "1) mié 4 nov, 09:30" in reply and "2) jue 5 nov, 16:00" in reply
    done, _ = say(store, "1")
    assert "queda reservada" in done and booked(store).slot_id == ids[1]


def test_when_every_offered_slot_is_taken_the_candidate_gets_the_48_hour_promise(store):
    ids = add_slots(store)
    qualify(store)
    for slot_id in ids:
        store.book_slot(slot_id, f"other-{slot_id}", NOW_AWARE)
    reply, _ = say(store, "2")
    assert "48 horas" in reply and booked(store) is None


def test_after_booking_later_messages_repeat_the_booked_time(store):
    add_slots(store)
    qualify(store)
    say(store, "1")
    reply, llm = say(store, "gracias, ¿a qué hora era?")
    assert "ya está reservada" in reply and "mar 3 nov, 10:00" in reply and llm.calls == []


def test_a_mexican_candidate_only_sees_mexican_slots_in_mexican_time(store):
    add_slots(store, "ES")
    add_slots(store, "MX", [MX_SLOT])
    reply = qualify(store, "mx1", city="Guadalajara")
    options = [l for l in reply.splitlines() if l[:2] in ("1)", "2)", "3)")]
    assert options == ["1) mar 3 nov, 09:00"]


def test_past_and_cancelled_slots_are_never_offered(store):
    old = datetime(2026, 11, 3, 10, 0)
    ids = add_slots(store, times=[old, datetime(2026, 11, 4, 10, 0)])
    store.cancel_slot(ids[1], "Ana", NOW_AWARE)
    reply = qualify(store)
    assert "1) mar 3 nov, 10:00" in reply and "2)" not in reply


def test_the_offer_and_the_booking_are_in_the_audit_log(store):
    add_slots(store)
    qualify(store)
    say(store, "3")
    kinds = [e.type for e in store.events("c1")]
    assert "slots_offered" in kinds and "slot_booked" in kinds
    assert kinds.index("slots_offered") < kinds.index("slot_booked")


def test_the_offer_survives_a_restart_because_it_lives_in_the_saved_state(store):
    add_slots(store)
    qualify(store)
    reloaded = Store(store._path)
    reply = turn.handle_message(ScriptedLLM(), reloaded, AREAS, "c1", "2", NOW)
    assert "queda reservada" in reply


def test_a_candidate_is_not_offered_slots_before_qualifying(store):
    add_slots(store)
    turn.start(store, AREAS, "c1", NOW)
    reply, _ = say(store, "sí")
    assert "1)" not in reply
    reply, _ = say(store, "Soy Juan Pérez", {"name": "Juan Pérez"})
    assert "1)" not in reply


def test_a_rejected_candidate_never_gets_slots(store):
    add_slots(store)
    turn.start(store, AREAS, "c1", NOW)
    say(store, "sí")
    say(store, "no tengo licencia", {"has_license": False})
    reply, _ = say(store, "sí, correcto", {"confirms_rejection": True})
    assert "1)" not in reply and "licencia" in reply
