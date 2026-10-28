"""D83: what a web channel needs to show the picker: the days of a month with free times, the times of a day, and booking
one. Same token, same one-answer-per-message-id rule and same rate limit as the other calls."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from sazon import config
from sazon.client import SAZON_CALENDAR
from screener.service import create_app
from screener.store import Store
from tests.support.booking import NOW, qualify
from tests.support.clients import client_for
from tests.support.fakes import ScriptedLLM

CLIENT = client_for(config.AREAS)
ANA = "ana@sazon.test"


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "s.db", calendar=SAZON_CALENDAR)
    s.add_recruiter(ANA, "Ana", "ES", "contraseña-segura-1", "boss@sazon.test", NOW)
    return s


@pytest.fixture
def http(store):
    return TestClient(create_app(CLIENT, store, ScriptedLLM(), clock=lambda: NOW))


def token_for(store, cid):
    import hashlib
    token = f"token-of-{cid}-" + "x" * 30
    store.set_token(cid, hashlib.sha256(token.encode()).hexdigest())
    return {"Authorization": f"Bearer {token}"}


def qualified(store, cid="c1", city="Madrid"):
    qualify(store, cid, city=city)
    return token_for(store, cid)


def test_the_days_of_a_month_with_free_times_come_with_how_many_times_each_has(store, http):
    auth = qualified(store)
    body = http.get("/candidates/c1/times", params={"month": "2026-11"}, headers=auth).json()
    assert body["days"]["2026-11-02"] == 32 and "2026-11-07" not in body["days"] and "2026-11-08" not in body["days"]


def test_the_times_of_a_day_come_as_ids_with_their_clock(store, http):
    auth = qualified(store)
    times = http.get("/candidates/c1/times", params={"day": "2026-11-03"}, headers=auth).json()["times"]
    assert [t["label"] for t in times][:3] == ["09:00", "09:15", "09:30"] and len(times) == 32 and isinstance(times[0]["id"], int)


def test_only_the_candidates_own_country_is_shown(store, http):
    auth = qualified(store, "c2", "Guadalajara")  # Ana is in Spain
    assert http.get("/candidates/c2/times", params={"month": "2026-11"}, headers=auth).json() == {"days": {}}
    assert http.get("/candidates/c2/times", params={"day": "2026-11-03"}, headers=auth).json() == {"times": []}


@pytest.mark.parametrize("params", [{}, {"month": "november"}, {"month": "2026-13"}, {"day": "03/11/2026"}, {"day": "x"}])
def test_a_missing_or_malformed_date_is_refused(store, http, params):
    auth = qualified(store)
    assert http.get("/candidates/c1/times", params=params, headers=auth).status_code == 422


def test_booking_a_time_gives_the_answer_typing_a_number_would_and_a_resend_gets_the_same(store, http):
    auth = qualified(store)
    time_id = http.get("/candidates/c1/times", params={"day": "2026-11-03"}, headers=auth).json()["times"][4]["id"]
    first = http.post("/candidates/c1/book", json={"message_id": "b1", "slot_id": time_id}, headers=auth)
    again = http.post("/candidates/c1/book", json={"message_id": "b1", "slot_id": time_id}, headers=auth)
    assert first.status_code == 200 and "queda reservada" in first.json()["reply"] and again.json() == first.json()
    assert store.booking_of("c1").starts_at == datetime(2026, 11, 3, 10, 0)
    assert len([m for m in store.messages("c1") if m.role == "candidate" and "10:00" in m.text]) == 1


def test_the_picker_calls_need_the_candidates_own_token(store, http):
    qualified(store)
    other = qualified(store, "c3")
    assert http.get("/candidates/c1/times", params={"month": "2026-11"}, headers=other).status_code == 404
    assert http.post("/candidates/c1/book", json={"message_id": "b", "slot_id": 1}, headers=other).status_code == 404
    assert http.get("/candidates/c1/times", params={"month": "2026-11"}).status_code == 404


def test_a_candidate_made_by_the_service_is_known_to_have_the_button(store, http):
    made = http.post("/candidates").json()
    assert store.get(made["candidate_id"]).state["buttons"] is True  # so its offers name the picker, not a numbered list
