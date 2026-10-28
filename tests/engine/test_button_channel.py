"""D90: a channel that has a button to choose a time (the browser chat, the service's picker) is asked to book with it, and
is given no numbered list; every other channel keeps the list. The channel is told when the candidate starts and is saved
with them, so the reminders and the re-offers speak the same way."""
from datetime import datetime

import pytest

from sazon import config
from sazon.client import SAZON_CALENDAR
from screener import reminders, turn
from screener.store import Store
from tests.support.booking import NOW, hire, qualify, say
from tests.support.clients import client_for

CLIENT = client_for(config.AREAS)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "s.db", calendar=SAZON_CALENDAR)
    hire(s, "Ana")
    return s


def test_a_candidate_with_a_button_is_asked_to_book_with_it_and_is_given_no_list(store):
    reply = qualify(store, buttons=True)
    assert reply == "¡Genial, tu perfil encaja! Reserva una llamada para hablar con un reclutador con el botón de abajo."
    assert store.get("c1").state["buttons"] is True


def test_the_same_in_english_and_a_candidate_without_a_button_keeps_the_numbered_list(store):
    assert qualify(store, "c1", english=True, buttons=True).startswith("Great, your profile fits! Please book a call")
    assert "1)" not in qualify(store, "c2", english=True, buttons=True)
    plain = qualify(store, "c3")
    assert "1) " in plain and "Reserva una llamada" in plain and "número" in plain


def test_what_follows_speaks_the_same_way_a_re_offer_and_the_reminder_job_name_the_button_not_numbers(store):
    qualify(store, buttons=True)
    unclear, _ = say(store, "no sé, déjame pensar")
    assert "1)" not in unclear and "botón" in unclear
    reminders.run_once(store, CLIENT, datetime(2026, 10, 26, 12, 0))
    told = store.outbox_pending("c1")[-1].text
    assert "1)" not in told and "botón" in told


def test_typing_a_number_still_books_for_a_candidate_who_has_the_button(store):
    qualify(store, buttons=True)
    reply, _ = say(store, "2")
    assert "queda reservada" in reply and store.booking_of("c1").starts_at == datetime(2026, 10, 26, 9, 15)
