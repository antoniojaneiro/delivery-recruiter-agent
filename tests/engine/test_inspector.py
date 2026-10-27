"""D66: what a screen can show about one candidate, read from the store and never written."""
from datetime import date, datetime

from sazon.client import SAZON_CLIENT
from screener import session
from screener.inspector import inspect
from screener.model import Language
from screener.screening import Screening
from screener.store import Store

NOW = datetime(2026, 10, 25, 10, 0)


def store_with(tmp_path):
    store = Store(tmp_path / "s.db", calendar=SAZON_CLIENT.calendar)
    s = Screening(SAZON_CLIENT.areas, SAZON_CLIENT.spec)
    s.record_consent(True)
    s.submit("name", "Juan Pérez", date(2026, 10, 25))
    session.commit(store, "c1", s, NOW, outbox=["hello again"])
    return store


def test_an_unknown_candidate_has_nothing_to_inspect(tmp_path):
    assert inspect(Store(tmp_path / "s.db"), SAZON_CLIENT, "nobody") is None


def test_the_inspection_holds_the_outcome_the_data_the_card_and_the_queue(tmp_path):
    store = store_with(tmp_path)
    found = inspect(store, SAZON_CLIENT, "c1", Language.EN)
    assert found.outcome == "IN_PROGRESS" and found.extracted == {"name": "Juan Pérez"}
    assert found.card.splitlines()[0] == "Juan Pérez · In progress"
    assert [e.text for e in found.queued] == ["hello again"] and found.booking is None


def test_looking_changes_nothing(tmp_path):
    store = store_with(tmp_path)
    before = (store.get("c1").version, store.revision())
    inspect(store, SAZON_CLIENT, "c1")
    assert (store.get("c1").version, store.revision()) == before
