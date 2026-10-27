"""D48: offering, booking and confirming a call slot through handle_message."""
from datetime import datetime

import pytest

from tests.support.clients import client_for
from sazon.client import SAZON_CALENDAR
from screener import turn
from screener.store import Store
from tests.support.fakes import ScriptedLLM
from tests.support.booking import AREAS, ES_SLOTS, MX_SLOT, NOW, NOW_AWARE, add_slots, booked, qualify, say

@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "sazon.db", calendar=SAZON_CALENDAR)


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
    qualify(store, language="yes", english=True)
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
    reloaded = Store(store._path, calendar=SAZON_CALENDAR)
    reply = turn.handle_message(ScriptedLLM(), reloaded, client_for(AREAS), "c1", "2", NOW)
    assert "queda reservada" in reply


def test_a_candidate_is_not_offered_slots_before_qualifying(store):
    add_slots(store)
    turn.start(store, client_for(AREAS), "c1", NOW)
    reply, _ = say(store, "sí")
    assert "1)" not in reply
    reply, _ = say(store, "Soy Juan Pérez", {"name": "Juan Pérez"})
    assert "1)" not in reply


def test_a_rejected_candidate_never_gets_slots(store):
    add_slots(store)
    turn.start(store, client_for(AREAS), "c1", NOW)
    say(store, "sí")
    say(store, "no tengo licencia", {"has_license": False})
    reply, _ = say(store, "sí, correcto", {"confirms_rejection": True})
    assert "1)" not in reply and "licencia" in reply


def test_a_retry_after_a_failed_save_finds_the_existing_booking_whatever_the_candidate_says(store):
    ids = add_slots(store)
    qualify(store)
    store.book_slot(ids[0], "c1", NOW_AWARE)  # the booking landed, but the turn that made it was never saved
    reply, _ = say(store, "ninguna")
    assert "ya está reservada" in reply and "mar 3 nov, 10:00" in reply
    assert booked(store).slot_id == ids[0]
    assert "ya está reservada" in say(store, "gracias")[0]


def test_withdrawing_while_slots_are_offered_withdraws_the_candidate_and_does_not_repeat_the_list(store):
    add_slots(store)
    qualify(store)
    reply, _ = say(store, "me retiro, gracias")
    assert "«continuar»" in reply and "1)" not in reply and booked(store) is None
    assert store.get("c1").outcome == "WITHDRAWN"


def test_declining_every_slot_without_withdrawing_still_gets_the_48_hour_promise(store):
    add_slots(store)
    qualify(store)
    reply, _ = say(store, "ninguna me viene bien")
    assert "48 horas" in reply and "1)" not in reply and store.get("c1").outcome == "QUALIFIED"


def test_after_three_unclear_replies_the_offer_stops_and_the_48_hour_promise_applies(store):
    add_slots(store)
    qualify(store)
    for _ in range(3):
        assert "1)" in say(store, "¿qué tal?")[0]
    reply, _ = say(store, "¿qué tal?")
    assert "48 horas" in reply and "1)" not in reply and booked(store) is None


def test_two_slots_at_the_same_time_are_offered_once(store):
    add_slots(store, times=[ES_SLOTS[0], ES_SLOTS[0], ES_SLOTS[1]])
    options = [l for l in qualify(store).splitlines() if l[:2] in ("1)", "2)", "3)")]
    assert options == ["1) mar 3 nov, 10:00", "2) mié 4 nov, 09:30"]
