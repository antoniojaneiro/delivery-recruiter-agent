from datetime import datetime

import pytest

from sazon import chat
from sazon.phrasing import consent_message
from sazon.store import Store
from tests.fakes import ScriptedLLM

AREAS = {"Madrid": []}
NOW = datetime(2026, 10, 25, 10, 0)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "sazon.db")


def run(store, lines, llm=None):
    out = []
    feed = iter(lines)

    def read(prompt=""):
        try:
            return next(feed)
        except StopIteration:
            raise EOFError

    chat.run(llm or ScriptedLLM(), store, AREAS, read=read, write=out.append, clock=lambda: NOW)
    return out


def test_the_chat_opens_with_the_disclosure_and_quits_on_command(store):
    out = run(store, ["/quit"])
    assert consent_message() in "\n".join(out)
    assert len(store.list_candidates()) == 1


def test_a_candidate_message_goes_through_the_agent_and_the_reply_is_printed(store):
    llm = ScriptedLLM([{"consent": True}])
    out = run(store, ["sí", "/quit"], llm)
    assert any("llamas" in line for line in out)


def test_blank_lines_are_ignored_and_end_of_input_exits_cleanly(store):
    out = run(store, ["", "   "])
    assert out and store.list_candidates()


def test_wait24h_prints_the_reminder_then_stalls(store):
    run(store, ["/wait24h", "/wait24h", "/quit"])
    record = store.list_candidates()[0]
    assert record.outcome == "STALLED"


def test_resume_continues_an_existing_candidate_and_unknown_ids_are_reported(store):
    run(store, ["/quit"])
    cid = store.list_candidates()[0].candidate_id
    out = run(store, [f"/resume {cid}", "/resume nope", "/quit"])
    text = "\n".join(out)
    assert "nope" in text and "not found" in text.lower()
    assert len(store.list_candidates()) == 2


def test_new_starts_another_candidate_and_unknown_commands_are_explained(store):
    out = run(store, ["/new", "/bogus", "/quit"])
    assert len(store.list_candidates()) == 2
    assert any("/bogus" in line and "/quit" in line for line in out)


def test_a_crash_in_the_agent_never_kills_the_loop(store, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(chat.turn, "handle_message", boom)
    out = run(store, ["hola", "/quit"])
    assert any("problema técnico" in line for line in out)
