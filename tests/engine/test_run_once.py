"""D94: running a message exactly once is one module for every channel (the HTTP service, the voice endpoint). It claims the
message id, waits for a first copy still running, runs the work, and records the reply; what each channel does with a refusal,
a failure or a busy wait is the channel's own, so the result says which of them happened."""
import sqlite3
from datetime import datetime

import pytest

from screener.run_once import run_once
from screener.store import Store

NOW = datetime(2026, 10, 25, 10, 0)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "s.db")


def run(store, work, message_id="m1", **options):
    return run_once(store, "c1", message_id, work, clock=lambda: NOW, wait=0.2, **options)


def test_the_work_runs_once_and_a_resend_gets_the_stored_reply(store):
    calls = []
    first = run(store, lambda: calls.append(1) or "hola")
    again = run(store, lambda: calls.append(1) or "other")
    assert (first.status, first.reply) == ("ran", "hola") and (again.status, again.reply) == ("replayed", "hola")
    assert len(calls) == 1


def test_a_resend_while_the_first_copy_is_still_running_gives_up_after_the_wait(store):
    store.claim_message("c1", "m1", NOW)  # a first copy that never finishes
    result = run(store, lambda: "never")
    assert result.status == "busy" and result.reply is None


def test_a_refusal_before_the_work_releases_the_claim_and_says_why(store):
    refused = run(store, lambda: "never", before=lambda: "too many")
    assert (refused.status, refused.refusal) == ("refused", "too many")
    assert run(store, lambda: "now it runs").status == "ran"  # the same id may be tried again


def test_a_failure_in_the_work_releases_the_claim_and_hands_back_the_error(store):
    boom = ValueError("boom")

    def work():
        raise boom

    failed = run(store, work)
    assert failed.status == "failed" and failed.error is boom
    assert run(store, lambda: "retry").reply == "retry"


class FlakyFinish:
    """A store whose recording of the reply is locked a few times."""

    def __init__(self, real, locked):
        self.real, self.locked = real, locked

    def __getattr__(self, name):
        return getattr(self.real, name)

    def finish_message(self, *args):
        if self.locked:
            self.locked -= 1
            raise sqlite3.OperationalError("database is locked")
        return self.real.finish_message(*args)


def test_recording_the_reply_is_retried_as_often_as_the_channel_allows(store):
    assert run(FlakyFinish(store, 2), lambda: "hola", finish_attempts=3, retry_pause=0).status == "ran"


def test_a_reply_that_could_not_be_recorded_still_comes_back_with_the_error(store):
    result = run(FlakyFinish(store, 5), lambda: "hola", finish_attempts=2, retry_pause=0)
    assert (result.status, result.reply) == ("unrecorded", "hola") and isinstance(result.error, sqlite3.OperationalError)
