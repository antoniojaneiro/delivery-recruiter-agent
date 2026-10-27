"""D70: what the terminal chat and the browser chat both do: start a new candidate, and hand over queued messages."""
from datetime import datetime

from sazon.client import SAZON_CLIENT
from screener import dialog
from screener.phrasing import consent_message
from screener.store import Store

NOW = datetime(2026, 10, 26, 10, 0)


def make(tmp_path):
    return Store(tmp_path / "s.db", calendar=SAZON_CLIENT.calendar)


def test_a_new_candidate_gets_the_disclosure_and_a_record(tmp_path):
    store = make(tmp_path)
    candidate_id, text = dialog.new_candidate(store, SAZON_CLIENT, NOW)
    assert text == consent_message(SAZON_CLIENT.spec) and store.get(candidate_id) is not None


def test_a_new_candidate_never_reuses_an_existing_id(tmp_path, monkeypatch):
    draws = iter(["aaaaaaaaaaaa", "aaaaaaaaaaaa", "aaaaaaaaaaaa", "bbbbbbbbbbbb"])
    monkeypatch.setattr(dialog, "draw_id", lambda: next(draws))
    store = make(tmp_path)
    first, _ = dialog.new_candidate(store, SAZON_CLIENT, NOW)
    second, _ = dialog.new_candidate(store, SAZON_CLIENT, NOW)
    assert (first, second) == ("aaaaaaaaaaaa", "bbbbbbbbbbbb")


def test_ids_are_long_enough_to_make_collisions_negligible():
    assert len(dialog.draw_id()) >= 12 and dialog.draw_id() != dialog.draw_id()


def test_queued_messages_are_handed_over_once_and_marked_delivered(tmp_path):
    store = make(tmp_path)
    candidate_id, _ = dialog.new_candidate(store, SAZON_CLIENT, NOW)
    store.commit_turn(candidate_id, NOW, {}, {}, "IN_PROGRESS", [], [], outbox=["one", "two"])
    assert dialog.deliver_queued(store, candidate_id, NOW) == ["one", "two"]
    assert dialog.deliver_queued(store, candidate_id, NOW) == [] and store.outbox_pending(candidate_id) == []
