"""D93: the endpoint ElevenLabs calls for every spoken turn (an OpenAI-style chat completions call, streamed). It runs the same
engine as the text chat, with the spoken channel; the words it returns are the words spoken. It only believes a call that
carries our shared secret and a live voice session, takes only the last thing the candidate said (never the history it is
sent), and runs each turn once even if the call is repeated."""
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from sazon.areas import AREAS
from sazon.client import SAZON_CALENDAR
from screener import turn
from screener.store import Store
from screener.voice_service import create_voice_app, request_shape, session_of
from tests.support.booking import NOW, hire
from tests.support.clients import client_for
from tests.support.fakes import ScriptedLLM

CLIENT = client_for(AREAS)
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


def call(http, session, said, *, history=(), stream=True, secret=SECRET, where="extra", tools=None):
    """What ElevenLabs sends: the system prompt, every message so far, and the new thing the candidate said."""
    system = {"role": "system", "content": "You are Sofía. " + (f"voice_session={session}" if where == "prompt" else "")}
    messages = [system, {"role": "assistant", "content": "Hola, soy Sofía"}, *history, {"role": "user", "content": said}]
    body = {"model": "screening-engine", "messages": messages, "stream": stream, "temperature": 0.5}
    if where == "extra":
        body["elevenlabs_extra_body"] = {"voice_session": session}
    if tools is not None:
        body["tools"] = tools
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
    apology = turn.technical_error_message(CLIENT.spec, CLIENT.spec.pack.default_language, voice=True)
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
    assert spoken(response) == turn.technical_error_message(CLIENT.spec, CLIENT.spec.pack.default_language, voice=True)


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


def test_the_shape_of_a_request_has_no_words_in_it():
    body = {"model": "m", "stream": True, "messages": [{"role": "system", "content": "voice_session=abc"},
                                                       {"role": "user", "content": "mi nombre es Juan"}],
            "elevenlabs_extra_body": {"voice_session": "abc", "other": 1}}
    shape = request_shape(body)
    assert shape == {"keys": ["elevenlabs_extra_body", "messages", "model", "stream"], "extra_keys": ["other", "voice_session"],
                     "roles": ["system", "user"], "user_turns": 1, "session_from": "extra"}
    assert "Juan" not in json.dumps(shape) and "abc" not in json.dumps(shape)
    assert request_shape({"messages": [{"role": "system", "content": "voice_session=zz"}]})["session_from"] == "prompt"
    assert request_shape({"messages": "nope"})["session_from"] is None


def test_shapes_are_logged_only_when_asked_and_never_the_words(store, tmp_path):
    session = started(store)
    log = tmp_path / "shapes.log"
    quiet = TestClient(create_voice_app(CLIENT, store, ScriptedLLM(), secret=SECRET, clock=lambda: NOW, shapes_log=None))
    call(quiet, session, "sí")
    assert not log.exists()
    loud = TestClient(create_voice_app(CLIENT, store, ScriptedLLM(), secret=SECRET, clock=lambda: NOW, shapes_log=log))
    call(loud, session, "mi nombre es Juan Pérez", history=[{"role": "user", "content": "sí"}])
    line = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert line["user_turns"] == 2 and line["session_from"] == "extra" and "Juan" not in log.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", ["/v1/chat/completions", "/chat/completions", "/v1/chat/completions/chat/completions"])
def test_the_address_may_be_asked_for_with_or_without_chat_completions_added_again(store, path):
    http, _ = make(store)
    session = started(store)
    body = {"messages": [{"role": "system", "content": f"voice_session={session}"}, {"role": "user", "content": "sí"}], "stream": False}
    ok = http.post(path, json=body, headers={"Authorization": f"Bearer {SECRET}"})
    assert ok.status_code == 200 and "nombre" in ok.json()["choices"][0]["message"]["content"].lower()
    assert http.post(path, json=body).status_code == 401  # whatever the path, the secret is still needed


def test_other_paths_are_not_found_and_the_path_asked_is_in_the_shape_log_never_the_words(store, tmp_path):
    session = started(store)
    log = tmp_path / "shapes.log"
    http = TestClient(create_voice_app(CLIENT, store, ScriptedLLM(), secret=SECRET, clock=lambda: NOW, shapes_log=log))
    assert http.post("/v1/other", json={}, headers={"Authorization": f"Bearer {SECRET}"}).status_code == 404
    call(http, session, "mi nombre es Juan")
    assert json.loads(log.read_text(encoding="utf-8").splitlines()[0])["path"] == "/v1/chat/completions"


END_CALL = [{"type": "function", "function": {"name": "end_call", "description": "ends the call", "parameters": {"type": "object"}}}]


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: {")]


def rejected_by_voice(store, tools):
    """A candidate who says they have no licence and confirms: the agent turns them down, so the call is over."""
    http, _ = make(store, ScriptedLLM([{"has_license": False}, {"confirms_rejection": True}]))
    turn.start(store, CLIENT, "c1", NOW)
    from tests.support.booking import say
    say(store, "sí", {"consent": True}, voice=True)
    session = store.new_voice_session("c1", NOW)
    first = call(http, session, "no tengo licencia", tools=tools)
    history = [{"role": "user", "content": "no tengo licencia"}, {"role": "assistant", "content": spoken(first)}]
    return http, session, history


def test_when_the_conversation_is_over_the_farewell_is_spoken_and_the_call_is_ended_with_the_end_call_tool(store):
    http, session, history = rejected_by_voice(store, END_CALL)
    last = call(http, session, "correcto", history=history, tools=END_CALL)
    parts = events(last)
    said = "".join(e["choices"][0]["delta"].get("content", "") for e in parts)
    ending = [c for e in parts for c in e["choices"][0]["delta"].get("tool_calls", [])]
    assert said and [c["function"]["name"] for c in ending] == ["end_call"]
    assert json.loads(ending[0]["function"]["arguments"])["reason"]  # the tool needs a reason
    assert parts[-1]["choices"][0]["finish_reason"] == "tool_calls" and spoken(last) == said  # the words come first, then the end


def test_a_turn_that_is_not_the_last_never_ends_the_call(store):
    http, session, _ = rejected_by_voice(store, END_CALL)
    assert not [c for e in events(call(http, started(store, "c2"), "hola", tools=END_CALL))
                for c in e["choices"][0]["delta"].get("tool_calls", [])]
    assert store.get("c1").outcome == "IN_PROGRESS"  # the first turn only asked for the confirmation


def test_without_the_end_call_tool_in_the_request_the_call_is_left_open(store):
    http, session, history = rejected_by_voice(store, None)
    for tools in (None, [], [{"type": "function", "function": {"name": "something_else"}}]):
        last = call(http, session, "correcto", history=history, tools=tools)
        assert not [c for e in events(last) for c in e["choices"][0]["delta"].get("tool_calls", [])]
        assert events(last)[-1]["choices"][0]["finish_reason"] == "stop"


def test_a_repeated_final_call_ends_the_call_again(store):
    http, session, history = rejected_by_voice(store, END_CALL)
    first = call(http, session, "correcto", history=history, tools=END_CALL)
    again = call(http, session, "correcto", history=history, tools=END_CALL)
    names = lambda r: [c["function"]["name"] for e in events(r) for c in e["choices"][0]["delta"].get("tool_calls", [])]
    assert names(first) == names(again) == ["end_call"] and spoken(first) == spoken(again)


def test_a_reply_that_is_not_streamed_carries_the_end_call_too(store):
    http, session, history = rejected_by_voice(store, END_CALL)
    body = call(http, session, "correcto", history=history, stream=False, tools=END_CALL).json()["choices"][0]
    assert body["finish_reason"] == "tool_calls" and body["message"]["tool_calls"][0]["function"]["name"] == "end_call"
    assert body["message"]["content"]


def test_a_voice_call_made_for_a_candidate_is_remembered_and_erased_with_them(store):
    turn.start(store, CLIENT, "c5", NOW)
    assert store.had_voice_call("c5") is False
    store.new_voice_session("c5", NOW)
    assert store.had_voice_call("c5") is True and store.had_voice_call("c6") is False
    store.erase_candidate("c5", "recruiter:Ana", NOW, "request")
    assert store.had_voice_call("c5") is False
