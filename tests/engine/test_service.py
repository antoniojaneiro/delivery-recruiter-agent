"""D75: the HTTP service over the engine: who may call, one answer per message id, the rate limit, uploads and the
queued messages. Run in process; the load test (tests/load) runs the same app on a real server."""
import sqlite3
import threading
import time
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from screener.llm import LLMError
from screener.phrasing import consent_message
from screener.service import Limits, create_app
from screener.store import Store
from sazon.spec import SAZON
from tests.support.clients import client_for
from tests.support.fakes import ScriptedLLM
from tests.support.pdfs import pdf_with_text

AREAS = {"Madrid": [], "Guadalajara": []}
CLIENT = client_for(AREAS)
YES = {"consent": True, "language": "es"}


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 28, 10, 0)

    def __call__(self):
        return self.now


class SlowYes:
    """Answers every call as consent, after a delay, and counts the calls."""

    def __init__(self, delay=0.0):
        self.delay, self.calls = delay, 0
        self.lock = threading.Lock()

    def complete(self, system, user, json_mode=False):
        with self.lock:
            self.calls += 1
        time.sleep(self.delay)
        if json_mode:
            return '{"consent": true, "language": "es"}'
        raise LLMError("no wording in this test")


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "s.db")


@pytest.fixture
def clock():
    return Clock()


def build(store, clock, llm=None, raise_errors=True, **options):
    llm = llm if llm is not None else ScriptedLLM([YES] * 50)
    app = create_app(CLIENT, store, llm, clock=clock, **options)
    return TestClient(app, raise_server_exceptions=raise_errors), llm


def start(http, **headers):
    response = http.post("/candidates", headers=headers)
    assert response.status_code == 201
    body = response.json()
    return body["candidate_id"], {"Authorization": f"Bearer {body['token']}"}, body


def send(http, cid, auth, text="sí", message_id="m1"):
    return http.post(f"/candidates/{cid}/messages", json={"message_id": message_id, "text": text}, headers=auth)


def test_starting_a_candidate_returns_the_fixed_disclosure_and_a_secret_token(store, clock):
    http, _ = build(store, clock)
    cid, auth, body = start(http)
    assert body["reply"] == consent_message(SAZON)
    assert len(body["token"]) >= 32 and store.get(cid) is not None
    assert body["token"] not in open(store._path, "rb").read().decode("latin-1")  # only a hash is kept


def test_a_message_gets_a_reply_and_is_saved(store, clock):
    http, _ = build(store, clock)
    cid, auth, _ = start(http)
    response = send(http, cid, auth)
    assert response.status_code == 200 and "llamas" in response.json()["reply"]
    assert [m.role for m in store.messages(cid)] == ["agent", "candidate", "agent"]


@pytest.mark.parametrize("headers", [
    {}, {"Authorization": "Bearer wrong"}, {"Authorization": "wrong"}, {"X-API-Key": "wrong"}])
def test_a_wrong_or_missing_token_looks_the_same_as_an_unknown_candidate(store, clock, headers):
    http, llm = build(store, clock, api_key="secret")
    cid, auth, _ = start(http, **{"X-API-Key": "secret"})
    unknown = send(http, "nobody", auth)
    wrong = send(http, cid, headers)
    assert unknown.status_code == wrong.status_code == 404 and unknown.json() == wrong.json()
    assert llm.calls == [] and len(store.messages(cid)) == 1


def test_one_candidates_token_does_not_open_another_candidate(store, clock):
    http, _ = build(store, clock)
    first, _, _ = start(http)
    _, other_auth, _ = start(http)
    assert send(http, first, other_auth).status_code == 404
    assert http.get(f"/candidates/{first}/outbox", headers=other_auth).status_code == 404


def test_the_api_key_acts_for_any_candidate_and_is_needed_to_start_when_set(store, clock):
    http, _ = build(store, clock, api_key="secret")
    assert http.post("/candidates").status_code == 401
    assert http.post("/candidates", headers={"X-API-Key": "wrong"}).status_code == 401
    cid, _, _ = start(http, **{"X-API-Key": "secret"})
    assert send(http, cid, {"X-API-Key": "secret"}).status_code == 200


def test_a_resent_message_id_gets_the_stored_reply_without_calling_the_model(store, clock):
    http, llm = build(store, clock)
    cid, auth, _ = start(http)
    first = send(http, cid, auth).json()["reply"]
    calls = len(llm.calls)
    again = send(http, cid, auth, text="otra cosa distinta")
    assert again.json()["reply"] == first and len(llm.calls) == calls
    assert [m.role for m in store.messages(cid)] == ["agent", "candidate", "agent"]


def test_the_same_message_sent_many_times_at_once_is_processed_once(store, clock):
    llm = SlowYes(delay=0.3)
    http, _ = build(store, clock, llm=llm)
    base, base_auth, _ = start(http)
    send(http, base, base_auth, message_id="c")  # the consent answer is read in code
    send(http, base, base_auth, text="me llamo Juan Pérez", message_id="one")
    per_message = llm.calls
    cid, auth, _ = start(http)
    send(http, cid, auth, message_id="c")
    replies, errors = [], []

    def go():
        try:
            replies.append(send(http, cid, auth, text="me llamo Juan Pérez", message_id="one").json()["reply"])
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=go) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors and len(set(replies)) == 1 and len(replies) == 8
    assert per_message >= 1 and llm.calls == 2 * per_message
    assert len([m for m in store.messages(cid) if m.role == "candidate"]) == 2


def test_a_failed_message_can_be_sent_again_with_the_same_id(store, clock):
    class Boom:
        calls = 0

        def complete(self, system, user, json_mode=False):
            Boom.calls += 1
            if Boom.calls == 1:
                raise RuntimeError("unexpected")
            return '{"consent": true, "language": "es"}'

    http, _ = build(store, clock, llm=Boom())
    cid, auth, _ = start(http)
    send(http, cid, auth, message_id="c")  # the consent answer is read in code
    failed = send(http, cid, auth, text="me llamo Juan Pérez", message_id="one")
    assert failed.status_code == 500 and "Traceback" not in failed.text and "unexpected" not in failed.text
    assert send(http, cid, auth, text="me llamo Juan Pérez", message_id="one").status_code == 200


def test_too_many_messages_in_a_minute_are_refused_before_the_model_and_before_saving(store, clock):
    http, llm = build(store, clock, limits=Limits(per_minute=3, total=100))
    cid, auth, _ = start(http)
    for n in range(3):
        assert send(http, cid, auth, message_id=f"m{n}").status_code == 200
    calls, saved = len(llm.calls), len(store.messages(cid))
    refused = send(http, cid, auth, message_id="m3")
    assert refused.status_code == 429 and int(refused.headers["Retry-After"]) >= 1
    assert len(llm.calls) == calls and len(store.messages(cid)) == saved
    clock.now += timedelta(seconds=61)
    assert send(http, cid, auth, message_id="m3").status_code == 200  # the refused id was released


def test_a_candidate_has_a_total_cap_and_a_resend_of_an_answered_message_is_still_free(store, clock):
    http, _ = build(store, clock, limits=Limits(per_minute=100, total=2))
    cid, auth, _ = start(http)
    first = send(http, cid, auth, message_id="m0")
    send(http, cid, auth, message_id="m1")
    clock.now += timedelta(hours=1)
    assert send(http, cid, auth, message_id="m2").status_code == 429
    assert send(http, cid, auth, message_id="m0").json() == first.json()


def test_an_overlong_message_or_a_bad_body_is_refused(store, clock):
    http, llm = build(store, clock)
    cid, auth, _ = start(http)
    assert send(http, cid, auth, text="x" * 5000).status_code == 422
    assert http.post(f"/candidates/{cid}/messages", json={"text": "hola"}, headers=auth).status_code == 422
    assert send(http, cid, auth, message_id="").status_code == 422
    assert llm.calls == []


def test_a_pdf_can_be_uploaded_after_consent(store, clock):
    cv = '{"name": "Juan Pérez", "city": "Madrid", "has_license": true, "experience_years": 3, "platforms": ["Glovo"]}'
    http, _ = build(store, clock, llm=ScriptedLLM([YES, cv]))
    cid, auth, _ = start(http)
    send(http, cid, auth)
    response = http.post(f"/candidates/{cid}/cv", headers=auth, data={"message_id": "cv1"},
                          files={"file": ("cv.pdf", pdf_with_text("Juan Pérez", "Madrid"), "application/pdf")})
    assert response.status_code == 200 and response.json()["reply"]
    assert store.cv(cid) is not None


def test_a_file_over_the_size_limit_is_refused_before_it_is_read_into_the_engine(store, clock):
    http, llm = build(store, clock)
    cid, auth, _ = start(http)
    response = http.post(f"/candidates/{cid}/cv", headers=auth, data={"message_id": "cv1"},
                         files={"file": ("cv.pdf", b"%PDF" + b"0" * (2 * 1024 * 1024 + 10), "application/pdf")})
    assert response.status_code == 413 and llm.calls == [] and store.cv(cid) is None


def test_queued_messages_are_listed_until_the_channel_confirms_them(store, clock):
    http, _ = build(store, clock)
    cid, auth, _ = start(http)
    store.commit_turn(cid, clock.now, {}, {}, "IN_PROGRESS", [], [], outbox=["Recordatorio", "Cancelada"])
    listed = http.get(f"/candidates/{cid}/outbox", headers=auth).json()["messages"]
    assert [m["text"] for m in listed] == ["Recordatorio", "Cancelada"]
    assert len(http.get(f"/candidates/{cid}/outbox", headers=auth).json()["messages"]) == 2  # not lost if unconfirmed
    done = http.post(f"/candidates/{cid}/outbox/ack", json={"ids": [listed[0]["id"]]}, headers=auth)
    assert done.status_code == 200
    assert [m["text"] for m in http.get(f"/candidates/{cid}/outbox", headers=auth).json()["messages"]] == ["Cancelada"]


def test_a_candidate_cannot_confirm_another_candidates_queued_message(store, clock):
    http, _ = build(store, clock)
    cid, auth, _ = start(http)
    other, other_auth, _ = start(http)
    store.commit_turn(other, clock.now, {}, {}, "IN_PROGRESS", [], [], outbox=["Privado"])
    entry = store.outbox_pending(other)[0]
    http.post(f"/candidates/{cid}/outbox/ack", json={"ids": [entry.id]}, headers=auth)
    assert [e.text for e in store.outbox_pending(other)] == ["Privado"]


def test_health_needs_no_token_and_shows_no_data(store, clock):
    http, _ = build(store, clock)
    response = http.get("/health")
    assert response.status_code == 200 and response.json() == {"status": "ok"}


@pytest.mark.parametrize("where", ["claim_message", "commit_turn", "set_token"])
def test_a_database_too_busy_to_write_is_answered_with_a_retry_later_not_a_server_error(store, clock, where):
    import sqlite3
    http, _ = build(store, clock)
    cid, auth, _ = start(http)
    send(http, cid, auth, message_id="c")  # the consent answer is read in code
    original = getattr(store, where)

    def locked(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    setattr(store, where, locked)
    response = http.post("/candidates") if where == "set_token" else send(http, cid, auth, text="hola", message_id="x")
    setattr(store, where, original)
    assert response.status_code == 503 and int(response.headers["Retry-After"]) >= 1
    assert send(http, cid, auth, text="hola", message_id="x").status_code == 200  # the same id works afterwards


def test_a_reply_that_could_not_be_recorded_is_retried_and_the_message_is_not_processed_twice(store, clock):
    http, llm = build(store, clock)
    cid, auth, _ = start(http)
    send(http, cid, auth, message_id="c")
    original, failures = store.finish_message, [2]

    def flaky(*args):
        if failures[0]:
            failures[0] -= 1
            raise sqlite3.OperationalError("database is locked")
        return original(*args)

    store.finish_message = flaky
    response = send(http, cid, auth, text="me llamo Juan Pérez", message_id="one")
    assert response.status_code == 200 and failures[0] == 0
    assert len([m for m in store.messages(cid) if m.role == "candidate"]) == 2


def test_when_the_reply_can_never_be_recorded_a_resend_does_not_run_the_message_again(store, clock):
    http, llm = build(store, clock, busy_wait=0.2)
    cid, auth, _ = start(http)
    send(http, cid, auth, message_id="c")
    original = store.finish_message

    def locked(*args):
        raise sqlite3.OperationalError("database is locked")

    store.finish_message = locked
    assert send(http, cid, auth, text="me llamo Juan Pérez", message_id="one").status_code == 503
    store.finish_message = original
    calls = len(llm.calls)
    assert send(http, cid, auth, text="me llamo Juan Pérez", message_id="one").status_code == 409
    assert len(llm.calls) == calls and len([m for m in store.messages(cid) if m.role == "candidate"]) == 2


def test_a_candidate_whose_token_could_not_be_saved_is_not_left_behind(store, clock):
    http, _ = build(store, clock)
    before = len(store.list_candidates())
    original = store.set_token

    def locked(*args):
        raise sqlite3.OperationalError("database is locked")

    store.set_token = locked
    assert http.post("/candidates").status_code == 503
    store.set_token = original
    after = len(store.list_candidates())
    assert after == before


def test_an_upload_over_the_limit_is_stopped_before_the_body_is_parsed_even_without_a_valid_token(store, clock, monkeypatch):
    from starlette.requests import Request

    async def never(self, *args, **kwargs):
        raise AssertionError("the body was parsed")

    monkeypatch.setattr(Request, "_get_form", never)
    http, llm = build(store, clock)
    big = b"%PDF" + b"0" * (2 * 1024 * 1024 + 200_000)
    response = http.post("/candidates/nobody/cv", data={"message_id": "x"}, files={"file": ("cv.pdf", big, "application/pdf")})
    assert response.status_code == 413 and llm.calls == []


def test_an_upload_with_no_declared_size_is_stopped_once_it_passes_the_limit(store, clock):
    http, llm = build(store, clock)
    cid, auth, _ = start(http)

    def chunks():
        yield b"--x\r\nContent-Disposition: form-data; name=\"message_id\"\r\n\r\ncv1\r\n"
        yield b"--x\r\nContent-Disposition: form-data; name=\"file\"; filename=\"cv.pdf\"\r\n\r\n%PDF"
        for _ in range(30):
            yield b"0" * 100_000

    response = http.post(f"/candidates/{cid}/cv", content=chunks(), headers={
        **auth, "content-type": "multipart/form-data; boundary=x"})
    assert response.status_code == 413 and llm.calls == [] and store.cv(cid) is None


def test_an_unexpected_error_anywhere_is_logged_with_an_id_and_shows_nothing_technical(store, clock, tmp_path, monkeypatch):
    from screener import dialog
    log = tmp_path / "errors.log"
    http, _ = build(store, clock, raise_errors=False, log_path=log)

    def boom(*args, **kwargs):
        raise RuntimeError("SECRET-DETAIL")

    monkeypatch.setattr(dialog, "new_candidate", boom)
    response = http.post("/candidates")
    body = response.json()
    assert response.status_code == 500 and set(body) == {"error", "error_id"} and len(body["error_id"]) == 6
    assert "SECRET-DETAIL" not in response.text and str(tmp_path) not in response.text
    assert body["error_id"] in log.read_text(encoding="utf-8") and "SECRET-DETAIL" in log.read_text(encoding="utf-8")
