"""D63: service areas, time zones, notice and offer size belong to the client, not to Sazón's config."""
from datetime import datetime, timedelta, timezone

import pytest

from screener import turn
from screener.store import InputError, Store
from tests.support.fakes import ScriptedLLM
from tests.support.toy_spec import TOY, TOY_UK, UK_CALENDAR

NOW = datetime(2026, 10, 26, 9, 0)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "uk.db", calendar=UK_CALENDAR)


def talk(store, llm, *messages):
    replies = []
    for message in messages:
        replies.append(turn.handle_message(llm, store, TOY_UK, "c1", message, NOW))
    return replies


def qualify(store, town="Headingley"):
    turn.start(store, TOY_UK, "c1", NOW)
    llm = ScriptedLLM(extractions=[{"name": "Jo Smith"}, {"town": town}, {"can_lift": True}])
    return talk(store, llm, "yes", "Jo Smith", town, "yes")


def test_a_store_without_a_calendar_does_not_book_calls(tmp_path):
    plain = Store(tmp_path / "plain.db")
    with pytest.raises(InputError):
        plain.add_slot("GB", NOW + timedelta(days=2), None, "Ana", NOW)


def test_the_clients_own_countries_and_notice_rules_apply(store):
    assert store.add_slot("GB", datetime(2026, 10, 28, 10, 0), None, "Ana", NOW) > 0
    with pytest.raises(InputError) as error:
        store.add_slot("ES", datetime(2026, 10, 28, 10, 0), None, "Ana", NOW)
    assert error.value.code == "unknown_country"
    now = datetime(2026, 10, 26, 9, 0, tzinfo=timezone.utc)  # London is on GMT that day
    with pytest.raises(InputError) as error:
        store.add_slot("GB", datetime(2026, 10, 26, 8, 30), None, "Ana", now)
    assert error.value.code == "in_the_past"
    store.add_slot("GB", datetime(2026, 10, 27, 12, 0), None, "Ana", now)
    store.add_slot("GB", datetime(2026, 10, 28, 12, 0), None, "Ana", now)
    assert [s.starts_at for s in store.free_slots("GB", now)] == [datetime(2026, 10, 28, 10, 0), datetime(2026, 10, 28, 12, 0)]  # this client books from two days on


def test_a_qualified_candidate_is_offered_slots_in_their_towns_country_up_to_the_clients_offer_size(store):
    for day in (28, 29, 30):
        store.add_slot("GB", datetime(2026, 10, day, 10, 0), None, "Ana", NOW)
    replies = qualify(store)
    assert replies[-1].splitlines() == [
        "You are through! Pick a time for a call:", "1) Wed 28 Oct, 10:00", "2) Thu 29 Oct, 10:00",
        "Reply with the number, or 'none'."]


def test_picking_a_slot_books_it_in_the_clients_words(store):
    store.add_slot("GB", datetime(2026, 10, 28, 10, 0), None, "Ana", NOW)
    qualify(store)
    reply = talk(store, ScriptedLLM(), "1")[0]
    assert reply == "Booked: Wed 28 Oct, 10:00."
    assert store.booking_of("c1").country == "GB"


def test_a_town_next_door_counts_and_a_stranger_is_confirmed_first(store):
    replies = qualify(store, town="Headingly")  # a typo of an alias
    assert replies[2] == "Do you mean Leeds?"


def test_the_cancel_message_uses_the_clients_wording_and_areas(store):
    from screener import slot_flow
    store.add_slot("GB", datetime(2026, 10, 28, 10, 0), None, "Ana", NOW)
    qualify(store)
    talk(store, ScriptedLLM(), "1")
    store.cancel_slot(store.booking_of("c1").slot_id, "Ana", NOW)
    assert slot_flow.notify_cancelled(store, TOY_UK, "c1", NOW) is True
    assert store.messages("c1")[-1].text == "Your call was cancelled. Write to us when you want to book."  # no other time is free


def test_the_reminder_clock_is_the_clients(store):
    from dataclasses import replace

    from screener import reminders
    client = replace(TOY_UK, remind_after=timedelta(hours=6))
    turn.start(store, client, "c1", NOW)
    talk(store, ScriptedLLM(), "yes")
    assert reminders.run_once(store, client, NOW + timedelta(hours=5)) == []
    assert [a.kind for a in reminders.run_once(store, client, NOW + timedelta(hours=7))] == ["reminder"]
    assert store.messages("c1")[-1].text == "Still interested in the picker job?"


def test_the_words_that_may_follow_a_place_name_are_the_clients(store):
    replies = qualify(store, town="Leeds, England")
    assert "through" in replies[-1]  # matched at once, no question about the town
    assert store.get("c1").extracted["town"] == "Leeds"


# --- a client that promises calls must be able to keep the promise ---------------------------------------------

def test_the_client_carries_its_calendar_and_a_store_for_it_is_built_from_it(tmp_path):
    from tests.support.toy_spec import TOY_UK
    assert TOY_UK.calendar is UK_CALENDAR
    assert Store(tmp_path / "x.db", calendar=TOY_UK.calendar).calendar is UK_CALENDAR


def test_a_client_with_call_texts_but_no_calendar_is_refused():
    from dataclasses import replace

    from screener.client import Client, ClientError
    with pytest.raises(ClientError) as error:
        replace(TOY_UK, calendar=None)
    assert "calendar" in str(error.value)
    with pytest.raises(ClientError):
        Client(spec=TOY, areas={}, calendar=UK_CALENDAR)  # a calendar for a client that never offers calls


def test_an_area_without_a_country_or_a_country_without_a_zone_is_refused():
    from dataclasses import replace

    from screener.client import ClientError
    from screener.slot_calendar import SlotCalendar
    with pytest.raises(ClientError) as error:
        replace(TOY_UK, areas={**TOY_UK.areas, "Bristol": []})
    assert "Bristol" in str(error.value)
    with pytest.raises(ClientError) as error:
        replace(TOY_UK, calendar=SlotCalendar(timezones={}, country_of=UK_CALENDAR.country_of))
    assert "GB" in str(error.value)


def test_a_client_with_no_button_texts_keeps_the_numbered_list_whatever_the_channel(store):
    store.add_slot("GB", datetime(2026, 10, 28, 10, 0), None, "Ana", NOW)
    turn.start(store, TOY_UK, "c1", NOW, buttons=True)
    llm = ScriptedLLM(extractions=[{"name": "Jo Smith"}, {"town": "Headingley"}, {"can_lift": True}])
    last = talk(store, llm, "yes", "Jo Smith", "Headingley", "yes")[-1]
    assert "1) Wed 28 Oct, 10:00" in last
