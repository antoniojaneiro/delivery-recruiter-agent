"""D93: the endpoint ElevenLabs calls for every spoken turn (an OpenAI-style chat completions call, streamed). It runs the same
engine as the text chat, with the spoken channel; the words it returns are the words spoken. It only believes a call that
carries our shared secret and a live voice session, takes only the last thing the candidate said (never the history it is
sent), and runs each turn once even if the call is repeated."""
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from sazon import config
from sazon.client import SAZON_CALENDAR
from screener import turn
from screener.store import Store
from screener.voice_service import create_voice_app, session_of
from tests.support.booking import NOW, hire
from tests.support.clients import client_for
from tests.support.fakes import ScriptedLLM

CLIENT = client_for(config.AREAS)
SECRET = "voice-secret-for-the-tests"
FIRST = turn.start  # the opening disclosure is spoken by the agent itself, so it is the first assistant message


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "s.db", calendar=SAZON_CALENDAR)
    hire(s, "Ana")
    return s


def make(store, llm=None):
    llm = llm or ScriptedLLM()
    http = TestClient(create_voice_app(CLIENT, store, llm, secret=SECRET, clock=lambda: NOW))
    return http, llm


def started(store, cid="c1"):
    turn.start(store, CLIENT, cid, NOW)
    return store.new_voice_session(cid, NOW)


def call(http, session, said, *, history=(), stream=True, secret=SECRET, where="extra"):
    """What ElevenLabs sends: the system prompt, every message so far, and the new thing the candidate said."""
    system = {"role": "system", "content": "You are Sofía. " + (f"voice_session={session}" if where == "prompt" else "")}
    messages = [system, {"role": "assistant", "content": "Hola, soy Sofía"}, *history, {"role": "user", "content": said}]
    body = {"model": "sazon-engine", "messages": messages, "stream": stream, "temperature": 0.5}
    if where == "extra":
        body["elevenlabs_extra_body"] = {"voice_session": session}
    return http.post("/v1/chat/completions", json=body, headers={"Authorization": f"Bearer {secret}"})


def spoken(response) -> str:
    """The words in a streamed answer, and a check that it is well formed: data lines, then [DONE]."""
    lines = [line for line in response.text.split("\n") if line.startswith("data: ")]
    assert lines[-1] == "data: [DONE]" and response.headers["content-type"].startswith("text/event-stream")
    parts = [json.loads(line[6:])["choices"][0]["delta"].get("content", "") for line in lines[:-1]]
    return "".join(parts)


def test_a_spoken_turn_runs_the_engine_and_the_answer_is_streamed_as_chat_completions(store):
    http, _ = make(store)
    session = started(store)
    reply = spoken(call(http, session, "sí"))
    assert "nombre" in reply.lower()
    assert [m.text for m in store.messages("c1")][1:3] == ["sí", reply]  # the same transcript the dashboard shows


def test_a_call_without_the_secret_or_with_a_wrong_one_is_refused_and_nothing_runs(store):
    http, llm = make(store)
    session = started(store)
    assert call(http, session, "sí", secret="wrong").status_code == 401
    assert http.post("/v1/chat/completions", json={"messages": []}).status_code == 401
    assert len(store.messages("c1")) == 1 and llm.calls == []


def test_the_session_is_read_from_the_extra_body_or_from_the_prompt_in_one_place():
    assert session_of({"elevenlabs_extra_body": {"voice_session": "abc"}, "messages": []}) == "abc"
    assert session_of({"messages": [{"role": "system", "content": "You are Sofía. voice_session=xyz_-9 and more"}]}) == "xyz_-9"
    assert session_of({"messages": [{"role": "system", "content": "nothing here"}]}) is None
    assert session_of({"elevenlabs_extra_body": "not a dict", "messages": "nope"}) is None


def test_the_session_can_arrive_in_the_prompt_instead(store):
    http, _ = make(store)
    session = started(store)
    assert "nombre" in spoken(call(http, session, "sí", where="prompt")).lower()


def test_an_unknown_or_expired_session_is_answered_with_the_fixed_apology_and_runs_nothing(store):
    http, llm = make(store)
    session = started(store)
    apology = turn.technical_error_message(CLIENT.spec, CLIENT.spec.pack.default_language)
    assert spoken(call(http, "no-such-session", "sí")) == apology
    late = TestClient(create_voice_app(CLIENT, store, llm, secret=SECRET, clock=lambda: NOW + timedelta(hours=2)))
    assert spoken(call(late, session, "sí")) == apology
    assert len(store.messages("c1")) == 1


def test_only_the_last_thing_said_counts_the_history_sent_along_is_ignored(store):
    http, _ = make(store)
    session = started(store)
    spoken(call(http, session, "sí"))
    history = [{"role": "user", "content": "sí"}, {"role": "assistant", "content": "¿Cómo te llamas?"}]
    spoken(call(http, session, "Juan Pérez", history=history))
    said = [m.text for m in store.messages("c1") if m.role == "candidate"]
    assert said == ["sí", "Juan Pérez"]


def test_a_repeated_call_gets_the_same_answer_and_the_turn_runs_once(store):
    http, llm = make(store, ScriptedLLM([{"consent": True}]))
    session = started(store)
    first, again = spoken(call(http, session, "sí")), spoken(call(http, session, "sí"))
    assert first == again and [m.role for m in store.messages("c1")].count("candidate") == 1


def test_the_same_word_said_in_two_turns_is_two_turns_not_a_repeat(store):
    http, _ = make(store)
    session = started(store)
    spoken(call(http, session, "sí"))
    history = [{"role": "user", "content": "sí"}, {"role": "assistant", "content": "…"}]
    spoken(call(http, session, "sí", history=history))  # the second yes answers the next question, it is not the first one again
    assert [m.role for m in store.messages("c1")].count("candidate") == 2


def test_an_answer_that_is_not_streamed_comes_back_as_one_chat_completion(store):
    http, _ = make(store)
    session = started(store)
    body = call(http, session, "sí", stream=False).json()
    assert body["object"] == "chat.completion" and "nombre" in body["choices"][0]["message"]["content"].lower()


def test_whatever_goes_wrong_inside_is_spoken_as_the_fixed_apology_never_a_server_error(store, monkeypatch):
    http, _ = make(store)
    session = started(store)

    def boom(*args, **kwargs):
        raise RuntimeError("the engine broke")

    monkeypatch.setattr(turn, "handle_message", boom)
    response = call(http, session, "sí")
    assert response.status_code == 200
    assert spoken(response) == turn.technical_error_message(CLIENT.spec, CLIENT.spec.pack.default_language)


def test_a_qualified_candidate_books_a_call_through_the_endpoint_by_saying_a_day_and_a_time(store):
    from tests.support.booking import qualify
    qualify(store)  # the written chat took them to the offer of times
    session = store.new_voice_session("c1", NOW)
    http, _ = make(store)
    ask = spoken(call(http, session, "hola"))
    assert ask.endswith("¿Qué día te vendría bien?")
    history = [{"role": "user", "content": "hola"}, {"role": "assistant", "content": ask}]
    second = spoken(call(http, session, "el martes", history=history))
    history += [{"role": "user", "content": "el martes"}, {"role": "assistant", "content": second}]
    assert "queda reservada" in spoken(call(http, session, "a las 10", history=history))
    assert store.booking_of("c1").starts_at == datetime(2026, 10, 27, 10, 0)


def test_a_voice_session_belongs_to_one_candidate_expires_and_is_erased_with_them(store):
    turn.start(store, CLIENT, "c2", NOW)
    session = store.new_voice_session("c2", NOW)
    assert store.voice_session_candidate(session, NOW + timedelta(minutes=29)) == "c2"
    assert store.voice_session_candidate(session, NOW + timedelta(minutes=31)) is None
    assert store.voice_session_candidate("guess", NOW) is None
    assert session not in open(store._path, "rb").read().decode("latin-1")  # only a hash is kept
    store.erase_candidate("c2", "recruiter:Ana", NOW, "request")
    assert store.voice_session_candidate(session, NOW) is None
