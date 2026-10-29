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


def test_everyone_shown_as_interview_scheduled_has_a_call_still_to_come(seeded):
    _, _, records = seeded
    scheduled = [r for r in records if r.stage == RecruiterStatus.INTERVIEW_SCHEDULED]
    assert len(scheduled) >= 4 and all(r.booking.starts_at > NOW for r in scheduled)


def test_a_hire_a_rejection_or_a_contact_is_dated_after_the_call_it_follows(seeded):
    store, _, records = seeded
    acted = [r for r in records if r.booking and r.stage in (RecruiterStatus.HIRED, RecruiterStatus.REJECTED,
                                                            RecruiterStatus.UNREACHABLE, RecruiterStatus.CONTACTED)]
    assert len(acted) >= 6
    for record in acted:
        decided = [e.at for e in store.events(record.candidate_id) if e.type == "recruiter_status"]
        assert decided and all(at > record.booking.starts_at for at in decided), record.extracted["name"]


def test_nothing_is_dated_after_the_moment_of_seeding(seeded):
    store, _, records = seeded
    for record in records:
        assert all(e.at <= NOW for e in store.events(record.candidate_id)), record.extracted["name"]
        assert all(m.at <= NOW for m in store.messages(record.candidate_id)), record.extracted["name"]


def test_the_dashboard_opens_on_the_demo_data_page_by_page(tmp_path, monkeypatch):
    """What a reviewer does first: sign in as a seeded recruiter and look at every page, past calls, hires and the erasure included."""
    from streamlit.testing.v1 import AppTest

    from tests.support.paths import DASHBOARD
    path = tmp_path / "demo.db"
    monkeypatch.setenv("SAZON_DB", str(path))
    seed(Store(path, calendar=SAZON_CALENDAR), datetime.now().replace(second=0, microsecond=0))
    at = AppTest.from_file(str(DASHBOARD), default_timeout=20).run()
    at.text_input(key="login_email").set_value("ana@sazon.test")
    at.text_input(key="login_password").set_value(PASSWORD)
    at.form_submit_button(key="login_submit").click().run()
    assert not at.exception, at.exception
    assert len(at.dataframe[0].value) == 27
    for page in ("slots", "funnel"):
        at.switch_page(f"views/{page}.py").run()
        assert not at.exception, (page, at.exception)


def test_resetting_while_the_apps_hold_the_database_says_so_in_one_line(tmp_path, monkeypatch, capsys):
    from pathlib import Path

    from sazon.demo.seed import main
    path = tmp_path / "demo.db"
    path.write_bytes(b"")
    monkeypatch.setenv("SAZON_DB", str(path))

    def locked(self, *args, **kwargs):
        raise PermissionError("in use")

    monkeypatch.setattr(Path, "unlink", locked)
    assert main(["--reset"]) == 1
    assert "stop the chat and the dashboard" in capsys.readouterr().err.lower()
