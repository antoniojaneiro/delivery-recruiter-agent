"""D58: funnel analytics. Counts what the chat already stores; nothing is guessed."""
from datetime import datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tests.support.paths import DASHBOARD
from sazon.client import SAZON_CALENDAR
from sazon.spec import SAZON
from screener.funnel import build_funnel
from screener.store import Store
from tests.support.dash import login, seed_accounts

NOW = datetime(2026, 10, 25, 10, 0)
FIELDS = {"name": "Juan Pérez", "experience": {"years": 1, "platforms": ["glovo"]}, "availability": ["full_time"],
          "schedule": "morning", "start_date": "2026-11-01", "city": "Madrid", "license": True}


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "s.db", calendar=SAZON_CALENDAR)


def add(store, cid, outcome, fields=0, consent=True, reasons=(), booked=False):
    extracted = dict(list(FIELDS.items())[:fields])
    store.commit_turn(cid, NOW, {"consent": consent}, extracted, outcome, [], [], reasons=list(reasons))
    if booked:
        slot = store.add_slot("ES", datetime(2027, 6, 15, 10, 0), "Ana", "Ana", NOW.astimezone())
        store.book_slot(slot, cid, NOW.astimezone())


def populate(store):
    add(store, "a", "IN_PROGRESS", consent=None)                       # just started, has not answered the consent yet
    add(store, "b", "DISQUALIFIED", consent=False, reasons=["NO_CONSENT"])
    add(store, "c", "IN_PROGRESS", fields=0)                           # consented, nothing answered yet
    add(store, "d", "IN_PROGRESS", fields=3)
    add(store, "e", "STALLED", fields=3)
    add(store, "f", "BLOCKED", fields=1, reasons=["BLOCKED_ON_EXPERIENCE"])
    add(store, "g", "DISQUALIFIED", fields=7, reasons=["NO_LICENSE"])
    add(store, "h", "DISQUALIFIED", fields=6, reasons=["OUT_OF_AREA"])
    add(store, "i", "QUALIFIED", fields=7)
    add(store, "j", "QUALIFIED", fields=7, booked=True)
    add(store, "k", "WITHDRAWN", fields=2)
    add(store, "l", "ENDED_OFF_TOPIC", fields=1)


def test_an_empty_database_gives_zeros_and_no_division_by_zero(store):
    f = build_funnel(store, SAZON)
    assert f.total == 0 and f.consented == 0 and f.qualified == 0
    assert all(count == 0 for _, count in f.stages) and f.rates["qualified"] == 0


def test_the_stages_count_how_far_candidates_got(store):
    populate(store)
    f = build_funnel(store, SAZON)
    stages = dict(f.stages)
    assert stages["Empezaron"] == 12
    assert stages["Dieron su consentimiento"] == 10          # all but a and b
    assert stages["Respondieron: nombre"] == 9               # c has consented but answered nothing
    assert stages["Respondieron: experiencia"] == 7          # d, e, g, h, i, j, k have fields >= 2
    assert stages["Respondieron: licencia"] == 3             # g, i, j answered all seven
    assert stages["Cualificaron"] == 2 and stages["Reservaron una llamada"] == 1


def test_the_stages_never_grow_as_the_conversation_goes_on(store):
    populate(store)
    counts = [count for _, count in build_funnel(store, SAZON).stages[:-2]]
    assert counts == sorted(counts, reverse=True)


def test_the_outcomes_and_the_reasons_are_counted(store):
    populate(store)
    f = build_funnel(store, SAZON)
    assert f.outcomes["QUALIFIED"] == 2 and f.outcomes["DISQUALIFIED"] == 3 and f.outcomes["WITHDRAWN"] == 1
    assert f.reasons == {"NO_CONSENT": 1, "NO_LICENSE": 1, "OUT_OF_AREA": 1, "BLOCKED_ON_EXPERIENCE": 1}


def test_candidates_still_open_are_counted_where_they_stopped(store):
    populate(store)
    f = build_funnel(store, SAZON)
    assert f.stopped_at == {"consentimiento": 1, "nombre": 1, "horario preferido": 2, "experiencia": 1}


def test_the_rates_are_shares_of_the_right_group(store):
    populate(store)
    r = build_funnel(store, SAZON).rates
    assert r["consent"] == pytest.approx(10 / 12)
    assert r["qualified"] == pytest.approx(2 / 12)
    assert r["booked_of_qualified"] == pytest.approx(1 / 2)
    assert r["closed_by_agent"] == pytest.approx(3 / 12)      # g, h and l; declining consent or withdrawing is the candidate's choice


# --- the page ----------------------------------------------------------------------------------------------------

def test_the_funnel_page_shows_the_numbers_and_the_stage_table(tmp_path, monkeypatch):
    monkeypatch.setenv("SAZON_DB", str(tmp_path / "s.db"))
    monkeypatch.setenv("SAZON_ACCOUNTS", str(tmp_path / "r.json"))
    seed_accounts(tmp_path / "r.json")
    populate(Store(tmp_path / "s.db", calendar=SAZON_CALENDAR))
    app = str(DASHBOARD)
    at = AppTest.from_file(app, default_timeout=10).run()
    login(at)
    at.switch_page("views/funnel.py").run()
    assert not at.exception, at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Empezaron"] == "12" and metrics["Cualificaron"] == "2"
    table = at.dataframe[0].value
    assert list(table["Etapa"])[0] == "Empezaron" and list(table["Candidatos"])[0] == 12


def test_the_funnel_is_counted_by_the_database_without_loading_every_candidate(store, monkeypatch):
    populate(store)
    expected = build_funnel(store, SAZON)

    def boom(*args, **kwargs):
        raise AssertionError("the funnel loaded the candidates")

    monkeypatch.setattr(Store, "list_candidates", boom)
    assert build_funnel(store, SAZON) == expected


def test_the_key_numbers_are_counted_by_the_database_too(store, monkeypatch):
    populate(store)
    monkeypatch.setattr(Store, "list_candidates", lambda *a, **k: (_ for _ in ()).throw(AssertionError("loaded")))
    assert store.kpi_counts() == {"total": 12, "to_review": 3, "to_contact": 1, "blocked": 1, "stalled": 1}


# --- the recruiter's steps (D78): counted from the audit history, cumulative --------------------------------

RECRUITER_LABELS = {"contacted": "Contactados", "interview_scheduled": "Entrevista", "hired": "Contratados"}


def test_the_recruiters_steps_count_everyone_who_ever_got_that_far_even_if_they_were_rejected_later(store):
    from screener.model import RecruiterStatus as S
    populate(store)
    store.set_status("j", S.CONTACTED, "Ana", NOW)
    store.set_status("j", S.INTERVIEW_SCHEDULED, "Ana", NOW)
    store.set_status("j", S.REJECTED, "Ana", NOW)  # rejected after the interview: still reached it
    store.set_status("i", S.HIRED, "Ana", NOW)     # straight to hired: it passed the steps before
    store.set_status("k", S.UNREACHABLE, "Ana", NOW)
    f = build_funnel(store, SAZON, recruiter_labels=RECRUITER_LABELS)
    assert f.recruiter_stages == [("Contactados", 2), ("Entrevista", 2), ("Contratados", 1)]


def test_an_erased_candidate_is_not_counted_in_the_recruiters_steps(store):
    from screener.model import RecruiterStatus as S
    populate(store)
    store.set_status("i", S.HIRED, "Ana", NOW)
    store.erase_candidate("i", "recruiter:Ana", NOW, "request")
    f = build_funnel(store, SAZON, recruiter_labels=RECRUITER_LABELS)
    assert f.recruiter_stages == [("Contactados", 0), ("Entrevista", 0), ("Contratados", 0)]


def test_without_labels_the_funnel_has_only_the_agents_stages(store):
    populate(store)
    assert build_funnel(store, SAZON).recruiter_stages == []
