"""What the service keeps in the store: the hash of each candidate's secret token, the reply to each message id (so a
resend does the work once) and the counts the rate limit reads. All of it is erased with the candidate."""
import sqlite3
from datetime import datetime, timedelta

import pytest

from screener.store import Store

NOW = datetime(2026, 10, 28, 10, 0)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "s.db")


def say(store, cid, text, at, role="candidate"):
    store.commit_turn(cid, at, {}, {}, "IN_PROGRESS", [], [(role, text)])


def test_a_token_hash_matches_only_its_own_candidate(store):
    store.set_token("c1", "hash-1")
    store.set_token("c2", "hash-2")
    assert store.token_matches("c1", "hash-1")
    assert not store.token_matches("c1", "hash-2")
    assert not store.token_matches("c1", "")
    assert not store.token_matches("nobody", "hash-1")


def test_a_new_message_id_is_claimed_once_and_a_second_claim_is_busy(store):
    assert store.claim_message("c1", "m1", NOW).state == "new"
    assert store.claim_message("c1", "m1", NOW).state == "busy"
    assert store.claim_message("c1", "m2", NOW).state == "new"
    assert store.claim_message("c2", "m1", NOW).state == "new"


def test_a_finished_message_returns_the_stored_reply_to_every_resend(store):
    store.claim_message("c1", "m1", NOW)
    store.finish_message("c1", "m1", "Hola, ¿cómo te llamas?")
    for _ in range(3):
        claim = store.claim_message("c1", "m1", NOW)
        assert (claim.state, claim.reply) == ("done", "Hola, ¿cómo te llamas?")


def test_a_released_claim_can_be_taken_again(store):
    store.claim_message("c1", "m1", NOW)
    store.release_message("c1", "m1")
    assert store.claim_message("c1", "m1", NOW).state == "new"


def test_a_claim_nobody_finished_can_be_taken_over_after_a_while(store):
    store.claim_message("c1", "m1", NOW)
    assert store.claim_message("c1", "m1", NOW + timedelta(seconds=90)).state == "busy"  # a model call can take a minute
    assert store.claim_message("c1", "m1", NOW + timedelta(minutes=5, seconds=1)).state == "new"


def test_only_the_candidates_own_messages_are_counted(store):
    say(store, "c1", "hola", NOW - timedelta(seconds=90))
    say(store, "c1", "bot", NOW - timedelta(seconds=80), role="agent")
    say(store, "c1", "uno", NOW - timedelta(seconds=30))
    say(store, "c1", "dos", NOW - timedelta(seconds=5))
    say(store, "c2", "otro", NOW - timedelta(seconds=5))
    assert store.candidate_message_counts("c1", NOW - timedelta(seconds=60)) == (2, 3)
    assert store.candidate_message_counts("nobody", NOW - timedelta(seconds=60)) == (0, 0)


def test_erasing_a_candidate_removes_the_token_and_the_stored_replies(store, tmp_path):
    say(store, "c1", "hola", NOW)
    store.set_token("c1", "hash-1")
    store.claim_message("c1", "m1", NOW)
    store.finish_message("c1", "m1", "REPLY-MARKER")
    store.erase_candidate("c1", "rec", NOW, "request")
    assert not store.token_matches("c1", "hash-1")
    assert store.claim_message("c1", "m1", NOW).state == "new"
    raw = open(tmp_path / "s.db", "rb").read()
    assert b"REPLY-MARKER" not in raw and b"hash-1" not in raw


def test_an_old_database_is_upgraded_without_losing_anything(tmp_path):
    path = tmp_path / "old.db"
    old = Store(path)
    say(old, "c1", "hola", NOW)
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE tokens")
        db.execute("DROP TABLE replies")
    upgraded = Store(path)
    upgraded.set_token("c1", "h")
    assert upgraded.token_matches("c1", "h") and len(upgraded.messages("c1")) == 1
