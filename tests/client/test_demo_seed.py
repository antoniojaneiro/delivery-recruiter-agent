"""D95: the demo database. One command fills an empty database with fictional candidates, recruiters, calls and notes, through the
real engine with scripted answers (no model, no network), so a reviewer opens the dashboard and finds a working hiring pipeline."""
from datetime import datetime

import pytest

from sazon.client import SAZON_CALENDAR
from sazon.demo.seed import PASSWORD, SeedError, seed
from screener.model import Language, Outcome, RecruiterStatus
from screener.store import Store

NOW = datetime(2026, 10, 29, 12, 0)


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    store = Store(tmp_path_factory.mktemp("seed") / "demo.db", calendar=SAZON_CALENDAR)
    summary = seed(store, NOW)
    records = [store.get(row.candidate_id) for row in store.list_candidates()]
    return store, summary, records


def test_the_pipeline_shows_every_way_a_screening_can_end(seeded):
    _, _, records = seeded
    outcomes = {r.outcome for r in records}
    assert {Outcome.QUALIFIED, Outcome.DISQUALIFIED, Outcome.WITHDRAWN, Outcome.IN_PROGRESS} <= outcomes
    assert len(records) >= 24


def test_both_countries_and_both_languages_are_there(seeded):
    _, _, records = seeded
    cities = {r.extracted.get("city") for r in records if r.extracted.get("city")}
    assert {"Madrid", "Barcelona", "Valencia", "Ciudad de México", "Guadalajara", "Monterrey"} <= cities
    languages = {(r.state or {}).get("language") for r in records}
    assert {Language.ES.value, Language.EN.value} <= languages


def test_recruiters_work_through_the_pipeline_with_calls_statuses_and_notes(seeded):
    store, _, records = seeded
    stages = {r.stage for r in records}
    assert {RecruiterStatus.QUALIFIED, RecruiterStatus.INTERVIEW_SCHEDULED, RecruiterStatus.HIRED, RecruiterStatus.REJECTED} <= stages
    assert sum(1 for r in records if r.booking) >= 8
    assert sum(1 for r in records if store.notes(r.candidate_id)) >= 4


def test_nobody_who_answered_is_nameless_and_every_name_is_different(seeded):
    _, _, records = seeded
    names = [r.extracted.get("name") for r in records]
    assert all(names) and len(set(names)) == len(names)


def test_there_are_recruiters_in_both_countries_who_can_sign_in(seeded):
    store, summary, _ = seeded
    assert {r.country for r in summary.recruiters} == {"ES", "MX"} and len(summary.recruiters) >= 4
    assert all(store.verify_recruiter(r.email, PASSWORD, NOW) for r in summary.recruiters)


def test_seeding_a_database_that_has_candidates_is_refused_not_mixed(seeded):
    store, _, _ = seeded
    with pytest.raises(SeedError):
        seed(store, NOW)
