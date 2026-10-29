"""D83: the picker. A candidate who qualified is shown the days of a month that have free times, then that day's 15-minute
times, and choosing one books it: through the same path as typing a number, so the transcript, the offer and the reminders
stay consistent. Channels without buttons keep the numbered list."""
from datetime import date, datetime

import pytest

from sazon.areas import AREAS
from sazon.client import SAZON_CALENDAR
from screener import reminders, slot_offers, turn
from screener.store import Store
from tests.support.booking import NOW, NOW_AWARE, qualify, say
from tests.support.clients import client_for

CLIENT = client_for(AREAS)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "s.db", calendar=SAZON_CALENDAR)
    for name in ("Ana", "Luis"):
        s.add_recruiter(f"{name.lower()}@sazon.test", name, "ES", "contraseña-segura-1", "boss@sazon.test", NOW)
    return s


def pick(store, time_id, cid="c1", now=NOW):
    return turn.handle_slot(store, CLIENT, cid, time_id, now)


def test_the_days_of_a_month_with_free_times_are_listed_with_how_many_times_each_has(store):
    days = store.free_days("ES", date(2026, 11, 1), NOW_AWARE)
    assert min(days) == date(2026, 11, 2) and days[date(2026, 11, 2)] == 32
    assert date(2026, 11, 7) not in days and date(2026, 11, 8) not in days  # a weekend
    assert max(days) == date(2026, 11, 20)  # four weeks from the 25th, a Friday
    assert store.free_days("MX", date(2026, 11, 1), NOW_AWARE) == {}


def test_the_days_stop_where_the_horizon_stops_and_the_current_month_starts_today(store):
    october = store.free_days("ES", date(2026, 10, 1), NOW_AWARE)
    assert min(october) == date(2026, 10, 26)  # NOW is Sunday the 25th
    assert store.free_days("ES", date(2026, 12, 1), NOW_AWARE) == {}


def test_a_day_with_every_time_full_is_no_longer_listed(store):
    first_day = date(2026, 10, 26)
    for n, slot in enumerate(store.free_slots_on("ES", first_day, NOW_AWARE)):
        store.commit_turn(f"x{n}", NOW, {}, {}, "QUALIFIED", [], [])
        store.book_slot(slot.id, f"x{n}", NOW_AWARE)
        store.commit_turn(f"y{n}", NOW, {}, {}, "QUALIFIED", [], [])
        store.book_slot(slot.id, f"y{n}", NOW_AWARE)  # the second recruiter
    assert first_day not in store.free_days("ES", date(2026, 10, 1), NOW_AWARE)


def test_choosing_a_time_books_it_and_the_transcript_shows_the_choice_and_the_confirmation(store):
    qualify(store)
    chosen = store.free_slots_on("ES", date(2026, 10, 27), NOW_AWARE)[8]  # 11:00 on Tuesday
    reply = pick(store, chosen.id)
    assert "queda reservada" in reply and "11:00" in reply
    assert store.booking_of("c1").starts_at == datetime(2026, 10, 27, 11, 0)
    roles = [(m.role, m.text) for m in store.messages("c1")][-2:]
    assert roles[0] == ("candidate", "mar 27 oct, 11:00") and "queda reservada" in roles[1][1]


def test_choosing_closes_the_open_offer_so_a_late_number_gets_the_booked_time(store):
    qualify(store)
    pick(store, store.free_slots_on("ES", date(2026, 10, 27), NOW_AWARE)[0].id)
    late, _ = say(store, "1")
    assert "ya está reservada" in late and "09:00" in late
    assert reminders.run_once(store, CLIENT, datetime(2026, 10, 27, 12, 0)) == []


def test_a_time_that_filled_up_meanwhile_gets_a_fresh_offer_not_an_error(store):
    qualify(store, "c1")
    qualify(store, "c2")
    target = store.free_slots_on("ES", date(2026, 10, 27), NOW_AWARE)[0]
    pick(store, target.id, "c1")
    pick(store, target.id, "c2")  # two recruiters: both fit
    qualify(store, "c3")
    reply = pick(store, target.id, "c3")  # a third does not
    assert "ya no está libre" in reply and "1)" in reply and store.booking_of("c3") is None


def test_only_a_qualified_candidate_without_a_call_can_choose_a_time(store):
    turn.start(store, CLIENT, "new", NOW)
    time_id = store.free_slots_on("ES", date(2026, 10, 27), NOW_AWARE)[0].id
    assert "reservar" not in pick(store, time_id, "new").lower() and store.booking_of("new") is None
    qualify(store, "c1")
    pick(store, time_id, "c1")
    again = pick(store, store.free_slots_on("ES", date(2026, 10, 27), NOW_AWARE)[1].id, "c1")
    assert "ya está reservada" in again and store.booking_of("c1").starts_at == datetime(2026, 10, 27, 9, 0)


def test_a_time_in_another_country_cannot_be_chosen(store):
    store.add_recruiter("marta@sazon.test", "Marta", "MX", "contraseña-segura-1", "boss@sazon.test", NOW)
    mexican = store.free_slots_on("MX", date(2026, 10, 27), NOW_AWARE)[0].id
    qualify(store, "c1")  # Madrid
    pick(store, mexican, "c1")
    assert store.booking_of("c1") is None


def test_the_candidates_country_comes_from_their_place(store):
    qualify(store, "c1")
    qualify(store, "c2", city="Guadalajara")
    assert slot_offers.country_of(store, CLIENT, "c1") == "ES" and slot_offers.country_of(store, CLIENT, "c2") == "MX"
    assert slot_offers.country_of(store, CLIENT, "nobody") is None
