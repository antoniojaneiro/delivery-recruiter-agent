"""D66: the recruiter's side (summary card, funnel labels, reasons) exists in every language the client lists, and
the card shown on screen is rebuilt from the saved state, so it can follow the dashboard's language switch."""
from dataclasses import replace
from datetime import date, datetime

import pytest

from sazon.client import SAZON_CALENDAR
from sazon.spec import SAZON
from screener import session
from screener.funnel import build_funnel
from screener.model import Language
from screener.spec import SpecError
from screener.screening import Screening
from screener.store import Store
from screener.summary import summarise
from tests.support.clients import client_for
from tests.support.toy_spec import EN as TOY_EN, TOY

ES, EN = Language.ES, Language.EN
TODAY = date(2026, 10, 25)
NOW = datetime(2026, 10, 25, 10, 0)
ANSWERS = {"name": "Juan Pérez", "experience": (2, ["glovo", "uber eats"]), "availability": ["full_time"],
           "schedule": "morning", "start_date": date(2026, 11, 1), "city": "Madrid", "license": True}


def screening(**overrides):
    s = Screening({"Madrid": []}, SAZON)
    s.record_consent(True)
    for field, value in {**ANSWERS, **overrides}.items():
        if value is not None:
            s.submit(field, value, TODAY)
    return s


def test_the_card_in_english_says_the_same_things_as_the_spanish_one():
    assert summarise(screening(), EN).splitlines() == [
        "Juan Pérez · Madrid · Qualified", "License: yes", "Experience: 2 years (glovo, uber eats)",
        "Availability: full-time", "Preferred schedule: morning", "Start: 2026-11-01", "Chat: language Spanish"]


def test_the_default_card_is_still_the_spanish_one():
    assert summarise(screening()) == summarise(screening(), ES)
    assert summarise(screening()).splitlines()[0] == "Juan Pérez · Madrid · Cualificado"


def test_a_rejection_and_a_missing_answer_read_well_in_english():
    s = screening(license=False, start_date=None)
    s.confirm_rejection(True)
    lines = summarise(s, EN).splitlines()
    assert lines[1] == "Reason: no driver's license"
    s2 = screening(start_date=None, city=None)
    assert "Missing: city" not in summarise(s2, EN).splitlines()  # the start date comes first in the list
    assert "Missing: start date, city" in summarise(s2, EN).splitlines()


def test_the_card_rebuilt_from_the_saved_state_equals_the_one_that_was_saved(tmp_path):
    store = Store(tmp_path / "s.db", calendar=SAZON_CALENDAR)
    s = screening()
    session.commit(store, "c1", s, NOW)
    saved = store.get("c1")
    rebuilt = Screening.from_state({"Madrid": []}, saved.state, SAZON)
    assert summarise(rebuilt, ES) == saved.summary


def test_the_funnel_and_the_reasons_follow_the_language(tmp_path):
    store = Store(tmp_path / "s.db", calendar=SAZON_CALENDAR)
    session.commit(store, "c1", screening(), NOW)
    stages = dict(build_funnel(store, SAZON, EN).stages)
    assert stages["Started"] == 1 and stages["Answered: preferred schedule"] == 1
    assert dict(build_funnel(store, SAZON).stages)["Empezaron"] == 1
    assert SAZON.reason_text("NO_LICENSE", EN) == "no driver's license"
    assert SAZON.reason_text("NO_CONSENT", ES) == "no dio su consentimiento"
    assert SAZON.reason_text("BLOCKED_ON_CITY", EN) == "has not said their city"


def test_a_label_missing_in_a_recruiter_language_is_refused():
    broken = replace(SAZON.fields[0], label={ES: "nombre"})
    with pytest.raises(SpecError) as error:
        replace(SAZON, fields=(broken, *SAZON.fields[1:]))
    assert "label" in str(error.value) and "en" in str(error.value)


def test_a_recruiter_language_without_texts_is_refused():
    with pytest.raises(SpecError):
        replace(SAZON, recruiter={EN: SAZON.recruiter[EN]})  # the pack's default language has no recruiter texts


def test_the_toy_client_has_one_recruiter_language():
    assert list(TOY.recruiter) == [TOY_EN]
    assert summarise(Screening({}, TOY)).splitlines()[0] == "Unnamed candidate · In progress"
