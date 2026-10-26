import re
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


def run(store, lines, llm=None, log_path=None):
    out = []
    feed = iter(lines)

    def read(prompt=""):
        try:
            return next(feed)
        except StopIteration:
            raise EOFError

    chat.run(llm or ScriptedLLM(), store, AREAS, read=read, write=out.append, clock=lambda: NOW,
             log_path=log_path)
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


def boom(*args, **kwargs):
    raise RuntimeError("secret-detail-xyz")


def error_id(out):
    match = re.search(r"\[error (\w{6}): see", "\n".join(out))
    assert match, out
    return match.group(1)


class FailsOnCall:
    """Wraps a function and raises on the given 1-based call number."""

    def __init__(self, function, fail_on):
        self.function, self.fail_on, self.calls = function, fail_on, 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.calls == self.fail_on:
            raise RuntimeError("secret-detail-xyz")
        return self.function(*args, **kwargs)


def test_an_unexpected_error_in_a_message_apologises_logs_and_shows_an_error_id(store, tmp_path, monkeypatch):
    log = tmp_path / "sazon.log"
    monkeypatch.setattr(chat.turn, "handle_message", boom)
    out = run(store, ["mi teléfono es 600123123", "/quit"], log_path=log)
    assert any("problema técnico" in line for line in out)
    text = log.read_text(encoding="utf-8")
    assert error_id(out) in text and "RuntimeError" in text and "Traceback" in text
    assert "600123123" not in text


def test_a_failing_wait24h_is_reported_and_the_loop_carries_on(store, tmp_path, monkeypatch):
    log = tmp_path / "sazon.log"
    monkeypatch.setattr(chat.turn, "wait_24h", boom)
    out = run(store, ["/wait24h", "hola", "/quit"], log_path=log)
    assert error_id(out) in log.read_text(encoding="utf-8")
    assert any(line.startswith("bot>") for line in out[out.index(next(l for l in out if "[error" in l)):])


def test_a_failing_new_keeps_the_current_candidate(store, tmp_path, monkeypatch):
    log = tmp_path / "sazon.log"
    monkeypatch.setattr(chat.turn, "start", FailsOnCall(chat.turn.start, fail_on=2))
    out = run(store, ["/new", "/quit"], log_path=log)
    assert error_id(out) in log.read_text(encoding="utf-8")
    assert len(store.list_candidates()) == 1


def test_a_failing_resume_is_reported(store, tmp_path, monkeypatch):
    log = tmp_path / "sazon.log"
    monkeypatch.setattr(store, "get", boom)
    out = run(store, ["/resume abc123", "/quit"], log_path=log)
    assert error_id(out) in log.read_text(encoding="utf-8")


def test_a_failure_while_opening_the_chat_does_not_kill_the_program(store, tmp_path, monkeypatch):
    log = tmp_path / "sazon.log"
    monkeypatch.setattr(chat.turn, "start", boom)
    out = run(store, ["hola", "/quit"], log_path=log)
    assert error_id(out) in log.read_text(encoding="utf-8")
    assert any("/new" in line for line in out)


def test_an_unwritable_log_never_makes_things_worse(store, monkeypatch, tmp_path):
    monkeypatch.setattr(chat.turn, "handle_message", boom)
    out = run(store, ["hola", "/quit"], log_path=tmp_path / "missing_dir" / "x" / "sazon.log")
    assert any("problema técnico" in line for line in out)
    assert error_id(out)


def test_an_unopenable_database_exits_with_a_clear_message(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    monkeypatch.setattr(chat.config, "DB_PATH", blocker / "x.db")
    monkeypatch.setattr("sazon.gemini.from_env", lambda: type("L", (), {"model": "m"})())
    monkeypatch.setattr("sys.argv", ["sazon.chat"])
    with pytest.raises(SystemExit) as exit_info:
        chat.main()
    assert "database" in str(exit_info.value).lower()


def test_state_shows_what_the_agent_has_understood_so_far(store):
    llm = ScriptedLLM([{"name": "Juan Pérez"}])
    out = run(store, ["sí", "Juan Pérez", "/state", "/quit"], llm)
    text = "\n".join(out)
    assert "outcome: IN_PROGRESS" in text
    assert '"name": "Juan Pérez"' in text
    assert "Juan Pérez · En curso" in text


def test_state_before_anything_is_said_does_not_crash(store):
    out = run(store, ["/state", "/quit"])
    assert any("outcome:" in line for line in out)


def test_help_lists_the_commands(store):
    out = run(store, ["/help", "/quit"])
    assert any("/state" in line and "/wait24h" in line for line in out)


def test_inbox_shows_the_queued_messages_for_the_current_candidate_once(store):
    out = run(store, ["/quit"])
    cid = store.list_candidates()[0].candidate_id
    store.commit_turn(cid, NOW, {}, {}, "IN_PROGRESS", [], [], outbox=["Hola, ¿sigues interesado?"])
    shown = run_resume(store, cid, ["/inbox", "/inbox", "/quit"])
    assert sum("Hola, ¿sigues interesado?" in line for line in shown) == 1
    assert any("no queued messages" in line.lower() for line in shown)


def run_resume(store, cid, lines):
    return run(store, [f"/resume {cid}", *lines])
