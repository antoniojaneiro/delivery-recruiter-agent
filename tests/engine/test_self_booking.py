"""D82: a qualified candidate books their own call in the chat, from times made from the recruiters' availability. Many
candidates choosing the same time are spread over the recruiters free then, nobody is booked twice, and a time that is
full is taken off the list."""
from datetime import datetime

import pytest

from sazon import config

from screener.store import Store
from tests.support.booking import NOW_AWARE, hire, qualify, say
from tests.support.clients import client_for
from sazon.client import SAZON_CALENDAR

CLIENT = client_for(config.AREAS)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "s.db", calendar=SAZON_CALENDAR)


def owner(store, cid):
    return next(s.recruiter for s in store.slots(NOW_AWARE) if s.candidate_id == cid)


def test_a_qualified_candidate_is_offered_the_next_three_fifteen_minute_times_of_the_recruiters(store):
    hire(store, "Ana")
    reply = qualify(store)
    options = [line for line in reply.splitlines() if line[:2] in ("1)", "2)", "3)")]
    assert options == ["1) lun 26 oct, 09:00", "2) lun 26 oct, 09:15", "3) lun 26 oct, 09:30"]
    assert "reserva una llamada" in reply.lower()


def test_picking_a_time_books_it_with_a_recruiter_and_it_is_theirs_alone(store):
    hire(store, "Ana", "Luis")
    qualify(store)
    done, _ = say(store, "2")
    assert "queda reservada" in done and "09:15" in done
    assert owner(store, "c1") == "ana@sazon.test" and store.booking_of("c1").starts_at == datetime(2026, 10, 26, 9, 15)


def test_with_no_recruiters_there_are_no_times_and_the_candidate_is_told_to_write_later(store):
    reply = qualify(store)
    assert "no hay horarios libres" in reply and "1)" not in reply and "48" not in reply


def test_a_full_time_leaves_the_list_and_the_next_candidate_is_offered_the_following_ones(store):
    hire(store, "Ana")
    qualify(store, "c1")
    say(store, "1", cid="c1")  # the only recruiter is now busy at 09:00
    second = qualify(store, "c2")
    assert "09:00" not in second and "1) lun 26 oct, 09:15" in second


def test_thirty_candidates_choosing_the_same_time_are_spread_over_the_recruiters_and_all_get_a_call(store):
    hire(store, "Ana", "Luis", "Marta")
    ids = [f"c{n}" for n in range(30)]
    for cid in ids:
        qualify(store, cid)
        say(store, "1", cid=cid)  # everyone wants the first time offered to them
    held = [store.booking_of(cid) for cid in ids]
    assert all(held)
    calls = [(owner(store, cid), store.booking_of(cid).starts_at) for cid in ids]
    assert len(calls) == len(set(calls))  # no recruiter is booked twice at the same minute
    nine = [owner(store, cid) for cid in ids if store.booking_of(cid).starts_at == datetime(2026, 10, 26, 9, 0)]
    assert sorted(nine) == ["ana@sazon.test", "luis@sazon.test", "marta@sazon.test"]  # three recruiters, three calls at 09:00
    per_recruiter = [sum(1 for cid in ids if owner(store, cid) == r) for r in ("ana@sazon.test", "luis@sazon.test", "marta@sazon.test")]
    assert max(per_recruiter) - min(per_recruiter) <= 1  # the load is level


def test_a_recruiter_added_later_adds_capacity_at_once(store):
    hire(store, "Ana")
    ten = datetime(2026, 10, 26, 10, 0)
    assert store.capacity("ES", ten) == 1
    hire(store, "Luis")
    assert store.capacity("ES", ten) == 2


def test_mexican_candidates_are_offered_only_mexican_recruiters(store):
    hire(store, "Ana", country="ES")
    reply = qualify(store, "c1", city="Guadalajara")
    assert "no hay horarios libres" in reply  # Ana is in Spain
    hire(store, "Marta", country="MX")
    assert "1) lun 26 oct, 09:00" in qualify(store, "c2", city="Guadalajara")
