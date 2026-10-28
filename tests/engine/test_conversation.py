"""D70: one place loads a candidate's screening, lets the caller change it, saves it, and decides what a lost race
means. The callers only say what to change and what to do when somebody else saved first."""
from datetime import date, datetime

import pytest

from tests.support.tables import table

from sazon.client import SAZON_CLIENT
from screener import conversation, session
from screener.conversation import RAISE, RETRY_ONCE, SKIP, Turn
from screener.store import ConflictError, Store

NOW = datetime(2026, 10, 25, 10, 0)
TODAY = date(2026, 10, 25)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "s.db", calendar=SAZON_CLIENT.calendar)


def run(store, work, on_conflict=RAISE, default=None, cid="c1"):
    return conversation.run(store, SAZON_CLIENT, cid, NOW, work, on_conflict=on_conflict, default=default)


def say_name(name):
    def work(screening):
        screening.record_consent(True)
        screening.submit("name", name, TODAY)
        return Turn("done", messages=[("agent", "ok")])
    return work


def rival_saves(store):
    """Another writer saves the same candidate between our load and our save."""
    other = session.load(store, "c1", SAZON_CLIENT)
    other.submit("name", "Rival Persona", TODAY)
    session.commit(store, "c1", other, NOW)


def test_it_loads_lets_the_work_change_it_saves_and_returns_the_works_value(store):
    assert run(store, say_name("Juan Pérez")) == "done"
    record = store.get("c1")
    assert record.extracted == {"name": "Juan Pérez"} and [m.text for m in store.messages("c1")] == ["ok"]


def test_the_decision_is_logged_once_when_the_outcome_changes_and_not_again_when_it_does_not(store):
    run(store, say_name("Juan Pérez"))
    run(store, say_name("Juan Pérez"))
    decisions = [e for e in store.events("c1") if e.type == "decision"]
    assert len(decisions) == 1


def test_a_candidate_who_does_not_exist_yet_is_created(store):
    assert store.get("c1") is None
    run(store, say_name("Ana Ruiz"))
    assert store.get("c1") is not None


def test_a_lost_race_is_retried_once_with_a_fresh_copy_and_saved_once(store):
    run(store, say_name("Juan Pérez"))
    calls = []

    def work(screening):
        calls.append(screening.values.get("name"))
        if len(calls) == 1:
            rival_saves(store)  # the rival wins the first time only
        screening.submit("name", "Juan Pérez", TODAY)
        return Turn(len(calls), messages=[("agent", "reply")])

    assert run(store, work, on_conflict=RETRY_ONCE) == 2
    assert calls == ["Juan Pérez", "Rival Persona"]  # the second attempt saw the rival's save
    assert [m.text for m in store.messages("c1")].count("reply") == 1


def test_losing_the_race_twice_raises_the_conflict(store):
    run(store, say_name("Juan Pérez"))

    def work(screening):
        rival_saves(store)
        return Turn("x", messages=[("agent", "never saved")])

    with pytest.raises(ConflictError):
        run(store, work, on_conflict=RETRY_ONCE)
    assert all(m.text != "never saved" for m in store.messages("c1"))


def test_skip_gives_the_default_and_saves_nothing(store):
    run(store, say_name("Juan Pérez"))

    def work(screening):
        rival_saves(store)
        return Turn("x", messages=[("agent", "never saved")])

    assert run(store, work, on_conflict=SKIP, default="skipped") == "skipped"
    assert all(m.text != "never saved" for m in store.messages("c1"))


def test_raise_lets_the_conflict_through_at_once(store):
    run(store, say_name("Juan Pérez"))
    calls = []

    def work(screening):
        calls.append(1)
        rival_saves(store)
        return Turn("x")

    with pytest.raises(ConflictError):
        run(store, work, on_conflict=RAISE)
    assert calls == [1]


@table("policy", [RAISE, RETRY_ONCE, SKIP])
def test_a_candidate_erased_meanwhile_is_never_recreated(store, policy):
    run(store, say_name("Juan Pérez"))

    def work(screening):
        store.erase_candidate("c1", "recruiter:Ana", NOW, "request")
        return Turn("x", messages=[("agent", "ghost")])

    try:
        run(store, work, on_conflict=policy, default="gone")
    except ConflictError:
        pass
    assert store.get("c1") is None and store.messages("c1") == []


def test_work_that_changed_nothing_worth_saving_is_not_saved(store):
    run(store, say_name("Juan Pérez"))
    version = store.get("c1").version
    assert run(store, lambda screening: Turn("looked", save=False)) == "looked"
    assert store.get("c1").version == version
